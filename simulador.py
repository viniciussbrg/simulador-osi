"""Motor de eventos do simulador: a fila de prioridade que ordena a execução.

Este é o módulo que transforma *ações de camada* — o que `dispositivos.py`
devolve, um retrato de evento sem `passo`, `fluxo` nem `descricao` — na **lista
de `Evento`** que é a entrega formal de F3 e a única coisa que `visual.py`
enxerga. Nada aqui desenha, e nada aqui conhece tkinter.

O coração é uma fila de prioridade ordenada por `(instante, ordem_de_insercao)`
(seção 7.6 da proposta técnica):

- **`instante`** é o tempo *lógico* da simulação, não um relógio: o motor o usa
  para marcar "isto acontece no salto 3". Não tem unidade e não representa taxa
  de transmissão — as velocidades das interfaces são só exibição.
- **`ordem_de_insercao`** desempata: dois eventos no mesmo instante saem na
  ordem em que foram inseridos. É o que garante determinismo — a mesma
  topologia e o mesmo caso produzem sempre exatamente o mesmo registro, que
  T-FMT (issue #34) cobra caractere a caractere.

Por que uma fila, se um caso de fluxo único (C1, C2, C5, C7) só precisaria de
uma lista? Porque a ordem de *produção* não é a ordem de *registro*. Em C3 dois
fluxos concorrem: o motor executa F1 inteiro e depois F2 inteiro, agendando
cada salto no instante correspondente, e a drenagem intercala os dois,
alternando a cada salto — sem que o código dos casos precise ser reescrito
(decisão D5). Num fluxo único a mesma fila degenera em inserção sequencial,
sem caminho de código diferente.

Duas regras de numeração moram aqui, e só aqui:

1. `passo` é **global e contínuo**, iniciado em 1 — não reinicia por fluxo nem
   por dispositivo. É atribuído na *drenagem*, nunca na inserção: só quem tira
   da fila sabe a posição final do evento no registro.
2. Eventos `secundario` **não consomem** número de passo: recebem o passo do
   último evento principal do seu próprio fluxo. Sem isso o registro padrão,
   que oculta os secundários (seção 7.5), teria buracos — o Anexo B numera 001
   a 031 sem interrupção e passa de `008 | H1 | L1 | TRANSMITE` direto para
   `009 | R1 | L1 | RECEBE`, embora H2 receba e ignore o quadro Q1 no meio.

A simulação é drenada **por inteiro** antes de qualquer desenho (issue #32):
`drenar()` devolve uma tupla imutável, e o controle de execução da interface
(V5) vira navegação por índice nessa tupla.

Sobre a fila mora a **execução de um caso** (`executar_caso`): o percurso que
empurra cada segmento da origem ao destino chamando os métodos de
`dispositivos.py`, e a **redação da descrição** (`descrever`), o único campo do
`Evento` que nenhuma camada sabe escrever — porque depende de enxergar a
execução inteira, não a ação isolada.

No fim do módulo mora o ponto de entrada de linha de comando (issue #33),
`python simulador.py --caso C2 --log saida.txt`: a ferramenta de trabalho de
todo o desenvolvimento até F4 fechar (seção 13.2). Ele só orquestra — carrega,
executa o caso inteiro, formata — e por isso não conhece tkinter tampouco.

Ainda não está aqui: a injeção de falhas de C4/C6 (`ENLACE_FORA`, `CORROMPE`),
a intercalação de fluxos concorrentes de C3 e as métricas (F4).
"""

import argparse
import heapq
import itertools
from functools import lru_cache
import sys
from dataclasses import dataclass, field, fields, replace
from datetime import datetime
from typing import Iterable, Sequence

from camadas import reiniciar_contador_sessoes
from constantes import ACOES_POR_CAMADA, Acao
from dispositivos import (
    AcaoCamada,
    Computador,
    Encaminhamento,
    Envio,
    No,
    Roteador,
    Transmissao,
    logico_do_extremo,
    montar_dispositivos,
)
from evento import Enlace as EnlaceEvento, Evento, Metricas
from pdu import PDU, reiniciar_contador_quadros
from rede import (
    Caso,
    ErroTopologia,
    EventoExterno,
    Fluxo,
    Topologia,
    carregar_topologia,
    limite_de_segmento,
    texto_enlace_fora,
)

# Dispositivo e camada dos eventos de sistema (`CORROMPE`, `ENLACE_FORA`,
# `METRICAS`): não pertencem a nó nenhum nem a camada nenhuma. O Anexo B os
# escreve `0NN | -- | -- | METRICAS | …`; o `--` do campo de camada é o
# `linha()` de `Evento` que produz, a partir de `camada == 0`.
DISPOSITIVO_SISTEMA = "--"
CAMADA_SISTEMA = 0

# Campos do `Evento` que a fila aceita receber. `passo` fica de fora de
# propósito: é a fila que o atribui, e quem o passasse estaria numerando por
# conta própria.
_CAMPOS_DE_EVENTO = frozenset(f.name for f in fields(Evento)) - {"passo"}

# Pares (camada, ação) que legitimamente saem **sem** tamanho. Fora daqui, um
# evento sem tamanho é erro de montagem: a linha do registro perderia o sufixo
# de octetos. Os dois descartes da camada 2 não têm tamanho porque nada foi
# extraído do quadro — é por isso que a linha `DESCARTA` de C6 e o `IGNORA` da
# difusão (seção 10, casos C6 e 7.5) não trazem sufixo. Já o `DESCARTA` da
# camada 3 em C5 traz: ali o pacote existe, com seus 74 B.
_SEM_TAMANHO = frozenset({(2, "DESCARTA"), (2, "IGNORA")})


# Tipos de `eventos_externos` que o motor sabe aplicar: a queda de enlace de C4
# (`enlace_fora`, issue #40) e a inversão de bit de C6 (`erro_bit`, issue #41).
# Um caso que declare intervenção fora desta lista é **recusado** — ver
# `CasoNaoSuportado`. A lista existe para que o motor nunca produza um registro
# que *parece* certo por ignorar em silêncio o que o caso pediu.
TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS: frozenset[str] = frozenset(
    {"enlace_fora", "erro_bit"}
)


class ErroDeSimulacao(RuntimeError):
    """Uso indevido do motor: ação fora do vocabulário da camada que a emitiu,
    campo inexistente no contrato de `Evento`, agendamento no passado, evento
    secundário sem evento principal a que se acoplar.

    É sempre erro de programação — nunca comportamento de rede simulado.
    Descarte por ausência de rota (C5) e por verificação de erro reprovada (C6)
    são eventos normais da fila, com `estado` `descartado`/`erro`, não exceção.
    """


class CasoNaoSuportado(ErroDeSimulacao):
    """O caso pede uma intervenção externa que o motor ainda não aplica.

    Não é erro de quem chamou nem arquivo inválido: é funcionalidade que
    chegará em F4. Existe como exceção própria porque o tratamento é outro —
    a linha de comando a traduz em mensagem e código de saída, como faz com
    `ErroTopologia`, em vez de deixar estourar.

    A razão de recusar em vez de seguir: C4 sem a queda do enlace e C6 sem a
    inversão do bit produzem um registro que **parece** correto e não é (C4
    roteia pelo enlace que deveria estar fora; C6 entrega a mensagem que
    deveria ser descartada). Resultado errado parecido com o certo é pior do
    que falha, porque quem lê o registro não tem como perceber."""


@dataclass(frozen=True, order=True)
class _Agendado:
    """Uma entrada da fila. A ordem de comparação é exatamente a chave de
    prioridade — `(instante, ordem)`; `campos` fica fora dela
    (`compare=False`), porque é um dicionário e porque o par já é único:
    nenhum desempate precisa olhar a carga."""

    instante: int
    ordem: int
    campos: dict = field(compare=False)


class FilaEventos:
    """Fila de prioridade de eventos, ordenada por `(instante, ordem_de_insercao)`.

    Ciclo de vida: o motor agenda tudo o que o caso produz e depois drena.

        fila = FilaEventos()
        for acao in computador.iniciar_envio(fluxo).acoes:
            fila.agendar_acao(0, acao, "…", fluxo="F1")
        eventos = fila.drenar()   # tupla imutável, passos 1..N

    Agendar e drenar podem ser intercalados — a estrutura é um monte, não uma
    lista ordenada no fim —, com uma única restrição: não se agenda no passado.
    Um evento em instante anterior ao do último já emitido sairia depois dele no
    registro, e a ordenação deixaria de significar algo."""

    __slots__ = ("_monte", "_ordens", "_passo", "_passo_do_fluxo", "_instante_emitido")

    def __init__(self) -> None:
        self._monte: list[_Agendado] = []
        self._ordens = itertools.count()
        self._passo = 0  # nada emitido ainda; o primeiro evento será o 001
        self._passo_do_fluxo: dict[str | None, int] = {}
        self._instante_emitido = 0

    def __repr__(self) -> str:
        return f"FilaEventos(pendentes={len(self._monte)}, emitidos={self._passo})"

    # ------------------------------------------------------------------
    # Inserção
    # ------------------------------------------------------------------

    def agendar(self, instante: int, **campos) -> None:
        """Agenda um evento cru: `campos` são os campos do `Evento` menos
        `passo`. É a porta única de entrada da fila — `agendar_acao()` e
        `agendar_sistema()` são conveniências que desembocam aqui, e é por isso
        que toda a validação estrutural mora neste método."""
        self._validar(instante, campos)
        heapq.heappush(
            self._monte, _Agendado(instante, next(self._ordens), dict(campos))
        )

    def agendar_acao(
        self,
        instante: int,
        acao: AcaoCamada,
        descricao: str,
        *,
        fluxo: str | None = None,
        caminho: tuple[str, ...] = (),
    ) -> None:
        """Agenda o evento de uma ação de camada que acabou de ocorrer.

        `AcaoCamada.campos_de_evento()` traz tudo o que a camada sabe; os três
        campos restantes do contrato vêm de quem enxerga a execução inteira e
        são pedidos aqui: a redação da `descricao`, o rótulo do `fluxo` (`F1`,
        `F2` — indispensável em C3) e o `caminho` acumulado de enlaces já
        percorridos, que o mapa destaca."""
        self.agendar(
            instante,
            descricao=descricao,
            fluxo=fluxo,
            caminho=tuple(caminho),
            **acao.campos_de_evento(),
        )

    def agendar_sistema(
        self,
        instante: int,
        acao: Acao,
        descricao: str,
        *,
        fluxo: str | None = None,
        **campos,
    ) -> None:
        """Agenda um evento de sistema (`CORROMPE`, `ENLACE_FORA`, `METRICAS`):
        camada 0, dispositivo `--`, sem tamanho por padrão. Não vem de camada
        nenhuma — é o motor narrando uma intervenção do caso ou fechando a
        execução com as métricas."""
        self.agendar(
            instante,
            dispositivo=DISPOSITIVO_SISTEMA,
            camada=CAMADA_SISTEMA,
            acao=acao,
            descricao=descricao,
            fluxo=fluxo,
            **campos,
        )

    # ------------------------------------------------------------------
    # Consumo
    # ------------------------------------------------------------------

    def proximo(self) -> Evento | None:
        """Retira o próximo evento da fila e o numera, ou devolve `None` se a
        fila está vazia. É o único ponto do programa que atribui `passo`."""
        if not self._monte:
            return None
        agendado = heapq.heappop(self._monte)
        self._instante_emitido = agendado.instante
        return Evento(passo=self._numerar(agendado.campos), **agendado.campos)

    def drenar(self) -> tuple[Evento, ...]:
        """Consome a fila inteira e devolve o registro na ordem final, com os
        passos já atribuídos.

        A tupla é imutável de propósito: daqui para a frente o registro é dado
        fechado, que a interface percorre por índice (issue #32) — inclusive
        para trás, o que torna o retrocesso de passos gratuito."""
        eventos: list[Evento] = []
        while (evento := self.proximo()) is not None:
            eventos.append(evento)
        return tuple(eventos)

    def pendentes(self) -> tuple[dict, ...]:
        """Os campos dos eventos ainda na fila, em ordem de prioridade, **sem**
        consumi-los.

        Existe para o evento `METRICAS`, que precisa somar o que já aconteceu
        antes de entrar na fila e ser drenado junto com o resto. Devolve os
        dicionários de campos, não `Evento`: o `passo` só é atribuído na
        drenagem, e um `Evento` sem passo não existe.

        Leitura apenas — quem quiser consumir usa `proximo()` ou `drenar()`."""
        return tuple(agendado.campos for agendado in sorted(self._monte))

    @property
    def vazia(self) -> bool:
        return not self._monte

    @property
    def emitidos(self) -> int:
        """O último `passo` atribuído. Eventos secundários não contam, por
        definição (ver `_numerar`)."""
        return self._passo

    def __len__(self) -> int:
        """Quantos eventos ainda estão pendentes na fila."""
        return len(self._monte)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _numerar(self, campos: dict) -> int:
        """O passo de um evento que está saindo da fila.

        Evento principal: o próximo número do contador global, contínuo, sem
        reiniciar por fluxo nem por dispositivo. Evento secundário: o passo do
        último evento principal **do seu próprio fluxo**, porque ele acompanha
        aquele evento em vez de suceder-lhe — o `RECEBE`/`IGNORA` de H2
        acontece no mesmo instante do `TRANSMITE` de H1, pelo mesmo segmento de
        difusão. Assim o registro padrão, que oculta os secundários, numera 001
        a 031 sem buraco, como o Anexo B."""
        fluxo = campos.get("fluxo")
        if not campos.get("secundario"):
            self._passo += 1
            self._passo_do_fluxo[fluxo] = self._passo
            return self._passo
        principal = self._passo_do_fluxo.get(fluxo)
        if principal is None:
            raise ErroDeSimulacao(
                f"evento secundário sem evento principal a que se acoplar: "
                f"{campos.get('dispositivo')} L{campos.get('camada')} "
                f"{campos.get('acao')} (fluxo {fluxo!r}). Um `RECEBE`/`IGNORA` "
                f"de estação alheia acompanha o `TRANSMITE` do mesmo fluxo — "
                f"agende o principal antes."
            )
        return principal

    def _validar(self, instante: int, campos: dict) -> None:
        """As guardas de inserção. Falham na chamada que errou, e não trinta
        eventos depois, na montagem do `Evento`."""
        if not isinstance(instante, int) or isinstance(instante, bool):
            raise ErroDeSimulacao(
                f"instante deve ser int, recebido {type(instante).__name__}"
            )
        if instante < 0:
            raise ErroDeSimulacao(f"instante negativo: {instante}")
        if instante < self._instante_emitido:
            raise ErroDeSimulacao(
                f"agendamento no passado: instante {instante} é anterior ao do "
                f"último evento emitido ({self._instante_emitido}). O evento "
                f"sairia depois dele no registro, e a ordenação deixaria de "
                f"significar algo."
            )

        estranhos = sorted(set(campos) - _CAMPOS_DE_EVENTO)
        if estranhos:
            motivo = (
                " (`passo` é atribuído pela fila, na drenagem)"
                if "passo" in estranhos
                else ""
            )
            raise ErroDeSimulacao(
                f"campo que não existe no contrato de Evento: "
                f"{', '.join(estranhos)}{motivo}"
            )
        for obrigatorio in ("dispositivo", "camada", "acao", "descricao"):
            if obrigatorio not in campos:
                raise ErroDeSimulacao(f"campo obrigatório ausente: {obrigatorio}")

        camada = campos["camada"]
        acao = campos["acao"]
        if camada not in ACOES_POR_CAMADA:
            raise ErroDeSimulacao(
                f"camada inexistente: {camada!r} (1 a 7, ou 0 para sistema)"
            )
        if acao not in ACOES_POR_CAMADA[camada]:
            esperadas = ", ".join(sorted(ACOES_POR_CAMADA[camada]))
            raise ErroDeSimulacao(
                f"ação {acao!r} não pertence ao vocabulário da camada {camada} "
                f"({esperadas}). O vocabulário é fechado: ação nova exige "
                f"atualizar constantes.py e a seção 7.4 da proposta técnica."
            )
        pode_faltar = camada == CAMADA_SISTEMA or (camada, acao) in _SEM_TAMANHO
        if campos.get("tamanho") is None and not pode_faltar:
            raise ErroDeSimulacao(
                f"evento {acao} da camada {camada} sem tamanho: só os eventos "
                f"de sistema e os descartes da camada 2 ficam sem o sufixo de "
                f"octetos no registro"
            )


# --------------------------------------------------------------------------
# Redação da descrição
# --------------------------------------------------------------------------

# Reticências de um caractere (U+2026), como no Anexo B.
_RETICENCIAS = "…"


def _mac(endereco: str | None) -> str:
    """O endereço físico como o registro o escreve: primeiro octeto, reticências
    e os dois últimos — `AA:00:00:00:01:0A` vira `AA:…:01:0A`, a forma da linha
    007 do Anexo B. Os quatro octetos do meio são constantes na topologia de
    referência e só empurrariam a linha para a direita."""
    assert endereco is not None, "evento de camada 2 sem par físico"
    octetos = endereco.split(":")
    if len(octetos) <= 3:
        return endereco
    return f"{octetos[0]}:{_RETICENCIAS}:{octetos[-2]}:{octetos[-1]}"


def _redacao_roteia(acao: AcaoCamada) -> str:
    """A linha `ROTEIA` tem quatro redações — duas do computador de origem, duas
    de roteador em trânsito.

    Quem separa as duas famílias é o `sentido`: na origem a camada 3 está
    *descendo* a pilha; no roteador ela dá meia-volta (`meio`). A origem fala do
    destino ("na mesma rede", "próximo salto"), porque a decisão da seção 6.3 é
    binária e olha um endereço; o roteador fala da *rota* (prefixo, via quem,
    custo), porque a dele é uma consulta de tabela — Anexo B, linhas 006 e 011."""
    rota = acao.rota
    assert rota is not None, "ROTEIA sem a rota escolhida"
    if acao.sentido == "desce":  # camada 3 da origem — seção 6.3
        if acao.entrega_direta:
            return "destino na mesma rede, entrega direta"
        return f"próximo salto {acao.vizinho} pela interface {rota.interface}"
    if acao.entrega_direta:  # rede de destino no próprio enlace do roteador
        return f"{rota.prefixo} diretamente conectada, interface {rota.interface}"
    return (
        f"{rota.prefixo} via {acao.vizinho_nome}, custo {rota.custo}, "
        f"interface {rota.interface}"
    )


def _redacao_remonta(acao: AcaoCamada) -> str:
    """`REMONTA` tem duas redações porque a proposta técnica traz duas: o Anexo B
    (linha 027, um segmento só) nomeia a porta; a seção 10/C7 (três segmentos)
    conta os pedaços. O total de segmentos escolhe."""
    porta, segmento = acao.porta, acao.segmento
    assert porta is not None and segmento is not None, "REMONTA sem porta/segmento"
    if segmento.total == 1:
        return f"porta {porta.destino}, segmento 1 de 1 remontado"
    return f"{segmento.total} segmentos remontados em ordem"


def _redacao_gera(acao: AcaoCamada) -> str:
    """`GERA` nomeia os dois processos — menos quando não há processo de destino
    a nomear: em C5 o fluxo aponta para um endereço lógico solto (10.0.9.10), sem
    dispositivo e sem processo, e a cláusula cai em vez de sair vazia. Nomes de
    processo não trafegam em cabeçalho nenhum; vêm do caso."""
    processo = acao.processo
    assert processo is not None, "GERA sem processo"
    if not processo.destino:
        return f"processo {processo.origem}"
    return f"processo {processo.origem}, destino {processo.destino}"


# Uma redação por par (camada, ação) do vocabulário fechado da seção 7.4. O
# texto é literal, e não uma montagem genérica a partir dos campos, porque é
# exatamente este texto que T-FMT (issue #34) compara caractere a caractere com
# o Anexo B.
_REDACOES: dict[tuple[int, str], object] = {
    (7, "GERA"): _redacao_gera,
    (7, "ENTREGA"): lambda a: f"mensagem entregue ao processo {a.processo.destino}",
    (6, "CODIFICA"): lambda a: "octetos UTF-8, conteúdo cifrado",
    (6, "DECIFRA"): lambda a: "conteúdo decifrado, octetos UTF-8",
    (5, "ABRE"): lambda a: f"sessão {a.sessao} estabelecida",
    (5, "ENCERRA"): lambda a: f"sessão {a.sessao} encerrada",
    (4, "SEGMENTA"): lambda a: (
        f"porta {a.porta.origem} → {a.porta.destino}, "
        f"segmento {a.segmento.n} de {a.segmento.total}"
    ),
    (4, "REMONTA"): _redacao_remonta,
    (4, "DEMULTIPLEXA"): lambda a: (
        f"porta origem {a.porta.origem} → sessão {a.sessao}"
    ),
    (3, "ENCAPSULA"): lambda a: f"{a.logico.origem} → {a.logico.destino}",
    (3, "ROTEIA"): _redacao_roteia,
    (3, "DESENCAPSULA"): lambda a: (
        f"{a.logico.origem} → {a.logico.destino}, destino local"
    ),
    (3, "DESCARTA"): lambda a: f"sem rota para {a.logico.destino}, pacote descartado",
    (2, "ENQUADRA"): lambda a: (
        f"{_mac(a.fisico.origem)} → {_mac(a.fisico.destino)}, quadro {a.quadro}"
    ),
    (2, "DESENQUADRA"): lambda a: (
        f"verificação de erro correta, quadro {a.quadro} descartado"
    ),
    (2, "DESCARTA"): lambda a: (
        f"verificação de erro incorreta, quadro {a.quadro} descartado"
    ),
    (2, "IGNORA"): lambda a: (
        f"endereço físico de destino diverge, quadro {a.quadro} ignorado"
    ),
    (1, "TRANSMITE"): lambda a: f"{a.bits} bits no enlace {a.enlace.rotulo}",
    (1, "RECEBE"): lambda a: f"{a.bits} bits do enlace {a.enlace.rotulo}",
}


def descrever(acao: AcaoCamada) -> str:
    """A `descricao` da linha do registro para uma ação de camada.

    É o único campo do `Evento` que nenhuma camada escreve — a proposta técnica
    fixa a redação palavra por palavra (Anexo B e os critérios da seção 10), e
    escrevê-la exige saber coisas que a camada não sabe: que a `ROTEIA` de um
    roteador fala de prefixo e custo enquanto a da origem fala de entrega
    direta, que `REMONTA` muda de forma quando há mais de um segmento.

    Fica aqui, e não em `evento.py`, porque `linha()` formata *o que já está no
    evento* — contexto de execução não é estrutura de evento."""
    redacao = _REDACOES.get((acao.camada, acao.acao))
    if redacao is None:  # pragma: no cover — vocabulário fechado (seção 7.4)
        raise ErroDeSimulacao(
            f"sem redação para {acao.acao} na camada {acao.camada}: o vocabulário "
            f"é fechado (constantes.py e seção 7.4 da proposta técnica)"
        )
    return redacao(acao)


# --------------------------------------------------------------------------
# Execução de um caso
# --------------------------------------------------------------------------


class _Execucao:
    """Um caso sendo executado: empurra cada segmento da origem ao destino,
    agendando na fila o evento de cada ação de camada.

    Aqui não há regra de rede nenhuma. Quem decide a rota é a camada 3, quem
    monta o quadro é a camada 2, quem resolve o vizinho é `dispositivos.py`;
    este laço só escolhe **a quem entregar o quadro em seguida** e **quando
    parar** — no descarte por erro de verificação (C6), no descarte por ausência
    de rota (C5) ou na chegada ao destino.

    As três coisas que ele acrescenta a cada ação são exatamente as três que
    faltam no `AcaoCamada`: o rótulo do fluxo, a descrição e o caminho de
    enlaces já percorridos."""

    __slots__ = (
        "topologia",
        "_topologia_original",
        "caso",
        "dispositivos",
        "fila",
        "_caminho",
        "_instante",
    )

    def __init__(self, topologia: Topologia, caso: Caso) -> None:
        # Os dois contadores globais zerados uma única vez por execução, antes
        # de qualquer camada agir: é o que faz C2 render {Q1..Q4} e a sessão
        # sair S-0001 a cada chamada (R2, e o Anexo B linha 003).
        reiniciar_contador_quadros()
        reiniciar_contador_sessoes()
        # A topologia original, intocada: é o que a comparação com C1/C2
        # (seção 11.4) precisa usar, nunca a versão com intervenções deste
        # caso aplicadas — ver `_comparacao`.
        self._topologia_original = topologia
        # A topologia desta execução, já com as intervenções do caso aplicadas:
        # em C4, sem o enlace R1–R4. `com_enlace_ativo` devolve cópia, de modo
        # que o objeto do chamador segue intacto e rodar C2 depois de C4 volta
        # a dar a rota de custo 2. As tabelas de encaminhamento nascem daqui —
        # por isso a queda é aplicada **antes** de `montar_dispositivos`, e não
        # há recálculo no meio da execução a coordenar.
        self.topologia = topologia_do_caso(topologia, caso)
        self.caso = caso
        # O limite de segmentação vale por caso (seção 8.1): C7 declara o seu,
        # os demais usam o global. Resolver aqui, antes de montar as pilhas,
        # é o que faz a camada 4 de cada computador nascer já com o valor
        # certo — não há troca de limite no meio de uma execução.
        self.dispositivos = montar_dispositivos(
            self.topologia, limite_de_segmento(self.topologia, caso)
        )
        self.fila = FilaEventos()
        self._caminho: list[str] = []
        self._instante = 0

    def executar(self, *, com_metricas: bool = True) -> tuple[Evento, ...]:
        self._narrar_intervencoes()
        for fluxo in self.caso.fluxos:
            if self.caso.modo == "concorrente":
                # Cada fluxo recomeça a contar o tempo lógico: o primeiro salto
                # de F2 acontece no mesmo instante que o primeiro de F1, e a
                # drenagem, ordenada por `(instante, ordem_de_inserção)`,
                # intercala os dois salto a salto (C3, decisão D5). A produção
                # continua fluxo a fluxo — o que muda é a ordem do registro,
                # não a ordem em que as camadas agem.
                self._instante = 0
            self._executar_fluxo(fluxo)
        if com_metricas:
            self._fechar_com_metricas()
        return self.fila.drenar()

    # -- fluxo -------------------------------------------------------------

    def _executar_fluxo(self, fluxo: Fluxo) -> None:
        """Um fluxo inteiro: a descida alta da origem (uma vez) e depois cada
        segmento percorrendo a rota do começo ao fim (decisão D5 — os segmentos
        de C7 não viajam entrelaçados)."""
        origem = self.dispositivos.get(fluxo.origem.dispositivo or "")
        if not isinstance(origem, Computador):
            raise ErroDeSimulacao(
                f"o fluxo {fluxo.id} do caso {self.caso.id} precisa partir de um "
                f"computador nomeado, e {fluxo.origem.dispositivo!r} não é um: só "
                f"um computador tem as camadas 4 a 7 para originar mensagem (R1). "
                f"Um endereço lógico solto, sem dispositivo, só vale como destino "
                f"(é assim que C5 aponta para uma rede que não existe)."
            )
        envio = origem.iniciar_envio(fluxo)
        self._agendar(envio.acoes, fluxo)
        for segmento in envio.segmentos:
            self._percorrer(origem, envio, segmento, fluxo)

    def _percorrer(
        self, origem: Computador, envio: Envio, segmento: PDU, fluxo: Fluxo
    ) -> None:
        """Um segmento, da camada 3 da origem até onde ele chegar."""
        decisao = origem.encapsular(envio, segmento)
        self._agendar(decisao.acoes, fluxo)

        no: No = origem
        pacote = decisao.pacote
        while True:
            assert pacote is not None, "só se salta com pacote — descarte encerra"
            recebido = self._saltar(no, pacote, decisao, fluxo)
            if recebido is None:
                return  # verificação de erro reprovada na camada 2 (C6)

            no, pacote = recebido
            if isinstance(no, Computador) and no.atende(envio.logico_destino):
                self._agendar(
                    no.entregar(
                        pacote,
                        envio.processo,
                        demultiplexa=self._concorrem_no_destino(envio.logico_destino),
                        sessao=envio.sessao,
                    ),
                    fluxo,
                )
                return

            if not isinstance(no, Roteador):  # pragma: no cover — topologia coerente
                raise ErroDeSimulacao(
                    f"o quadro chegou a {no.nome}, que não é o destino "
                    f"({envio.logico_destino}) nem um roteador: nenhuma camada 3 "
                    f"de computador encaminha pacote alheio"
                )
            decisao = no.encaminhar(pacote)
            self._agendar(decisao.acoes, fluxo)
            if decisao.descartado:
                return  # sem rota para o destino (C5) — nada mais acontece
            pacote = decisao.pacote

    def _narrar_intervencoes(self) -> None:
        """As linhas de sistema que explicam o que o caso mudou na rede, antes
        do primeiro evento de camada.

        A queda já está aplicada na topologia desde a construção; o que se
        agenda aqui é a **narração** dela, no instante 0, para que o registro
        comece explicando por que a rota é outra — o primeiro `ROTEIA` já sai
        com o custo novo, e não haveria como o leitor saber de onde veio.

        O evento leva o `enlace` preenchido, e não só o rótulo dentro da
        descrição, porque é dele que o mapa (V1, issue #48) descobre qual
        traço desenhar tracejado com X. A alternativa seria a interface
        garimpar o id no meio do texto da linha — exatamente o que a regra de
        acoplamento proíbe: o dado que falta na tela entra no `Evento`. O
        campo já existia no contrato (seção 7.2, contexto de enlace); o que
        muda aqui é passar a preenchê-lo também no evento de sistema."""
        for intervencao in self.caso.eventos_externos:
            if intervencao.tipo == "enlace_fora":
                derrubado = self.topologia.enlace(intervencao.enlace)
                self.fila.agendar_sistema(
                    self._instante,
                    "ENLACE_FORA",
                    texto_enlace_fora(derrubado),
                    enlace=EnlaceEvento(id=derrubado.id, rotulo=derrubado.rotulo),
                )

    def _fechar_com_metricas(self) -> None:
        """O evento `METRICAS`, último da execução (seções 7.7 e 11.1).

        Lê o que já está na fila em vez de contabilizar durante o percurso: o
        registro é o retrato do que aconteceu, e derivar as métricas dele
        garante que os números batam com as linhas que o usuário vê. Uma
        contagem paralela poderia divergir do registro sem que nada acusasse.

        `dados_uteis` conta a carga de cada fluxo uma vez, e `dados_entregues`
        só a dos fluxos que chegaram: é o que faz C5 e C6 terem η = 0% com a
        rede inteira gasta (tabela 11.3). `enlaces_percorridos` conta
        **travessias**, não enlaces distintos — em C7 são 4 × 3 e em C3, 4 + 4,
        como a tabela escreve."""
        pendentes = self.fila.pendentes()
        transmitidos = [e for e in pendentes if e.get("acao") == "TRANSMITE"]
        entregues = {
            e.get("fluxo") for e in pendentes if e.get("acao") == "ENTREGA"
        }

        dados_uteis = sum(_octetos_da_mensagem(f) for f in self.caso.fluxos)
        dados_entregues = sum(
            _octetos_da_mensagem(f) for f in self.caso.fluxos if f.id in entregues
        )
        total = sum(e.get("tamanho") or 0 for e in transmitidos)
        eta = dados_entregues / total if total else 0.0

        metricas = Metricas(
            dados_uteis=dados_uteis,
            dados_entregues=dados_entregues,
            total_transmitido=total,
            eta=eta,
            sobrecarga=1.0 - eta,
            enlaces_percorridos=len(transmitidos),
            quadros_construidos=sum(
                1 for e in pendentes if e.get("acao") == "ENQUADRA"
            ),
            comparacao=self._comparacao(eta),
        )
        self.fila.agendar_sistema(
            self._instante,
            "METRICAS",
            _texto_metricas(metricas),
            metricas=metricas,
        )

    def _comparacao(self, eta_deste_caso: float) -> dict[str, float]:
        """Os η de C1 e C2 lado a lado, em qualquer caso executado (seção 11.4).

        Usa a topologia **original**, sem as intervenções deste caso: C1 e C2
        são a referência íntegra, e não deveriam piorar só porque o caso em
        execução derrubou um enlace que nem faz parte da rota deles."""
        comparacao = dict(comparacao_de_referencia(self._topologia_original))
        if self.caso.id in comparacao:
            # O caso em execução responde por si: seu η já está calculado, e
            # reaproveitá-lo evita divergência entre a linha e a comparação.
            comparacao[self.caso.id] = eta_deste_caso
        return comparacao

    def _corromper_no_enlace(self, transmissao: Transmissao, fluxo: Fluxo) -> Transmissao:
        """A inversão de bit de C6, aplicada ao quadro **em trânsito**.

        Diferente da queda de enlace, que muda a rede antes de tudo (C4), o
        erro de bit não tem como ser aplicado na partida: ele atinge um quadro
        específico num enlace específico, e o quadro só existe depois que a
        camada 2 o constrói. Daí o lugar — entre o `TRANSMITE` do remetente e
        a recepção do outro lado, que é onde a corrupção acontece de fato.

        Todas as pontas do enlace recebem a versão corrompida: o que foi
        alterado foi o sinal no cabo, não a cópia de alguém. Nenhum código
        daqui sabe o que é CRC; quem descobre a divergência é a camada 2 de
        quem recebe, recalculando (decisão D3) — e é por isso que o descarte
        de C6 sai como comportamento de rede e não como exceção."""
        entrega = transmissao.entrega_enderecada
        injecao = next(
            (
                externo
                for externo in self.caso.eventos_externos
                if externo.tipo == "erro_bit"
                and externo.enlace == entrega.enlace.id
                and externo.quadro == transmissao.quadro.id
            ),
            None,
        )
        if injecao is None:
            return transmissao

        assert injecao.bit is not None, "erro_bit declara a posição do bit"
        self.fila.agendar_sistema(
            self._instante,
            "CORROMPE",
            f"bit {injecao.bit} invertido no enlace {entrega.enlace.rotulo}, "
            f"quadro {transmissao.quadro.id}",
            fluxo=fluxo.id,
        )
        return replace(
            transmissao,
            entregas=tuple(
                replace(e, quadro=e.quadro.com_bit_invertido(injecao.bit))
                for e in transmissao.entregas
            ),
        )

    def _concorrem_no_destino(self, logico_destino: str) -> bool:
        """Se mais de um fluxo do caso termina neste endereço lógico.

        É o que distingue `DEMULTIPLEXA` de `REMONTA` na camada 4 do destino:
        demultiplexar é separar conversas que chegaram juntas, e só existe
        quando há mais de uma. Quem sabe disso é o caso inteiro — o pacote não
        carrega essa informação, e o computador de destino, sozinho, veria
        apenas mais um segmento chegando."""
        destinos = [
            logico_do_extremo(self.topologia, fluxo.destino)
            for fluxo in self.caso.fluxos
        ]
        return destinos.count(logico_destino) > 1

    # -- salto -------------------------------------------------------------

    def _saltar(
        self, no: No, pacote: PDU, decisao: Encaminhamento, fluxo: Fluxo
    ) -> tuple[No, PDU] | None:
        """Um salto completo, num instante lógico só: `ENQUADRA`/`TRANSMITE` no
        remetente e a recepção em cada ponta do enlace.

        Devolve quem recebeu o quadro e o pacote extraído, ou `None` se a
        verificação de erro reprovou (C6) — e aí o percurso acaba ali.

        As estações **não endereçadas** do segmento de difusão são agendadas
        logo depois do `TRANSMITE`, antes da estação destinatária: elas recebem
        o quadro no mesmo instante, e assim herdam o passo do `TRANSMITE` em vez
        do passo da recepção alheia (ver `FilaEventos._numerar`). É o que faz o
        registro do Anexo B ir de `008 | H1 | L1 | TRANSMITE` a
        `009 | R1 | L1 | RECEBE` com o `IGNORA` de H2 no meio, sem buraco na
        numeração."""
        assert decisao.vizinho is not None and decisao.interface_saida is not None
        self._instante += 1
        transmissao = no.enquadrar(
            pacote, vizinho=decisao.vizinho, interface_saida=decisao.interface_saida
        )
        self._agendar(transmissao.acoes, fluxo)

        # O enlace entra no caminho quando o quadro é posto nele: a partir do
        # `RECEBE` da outra ponta, o mapa já o destaca como percorrido.
        enderecada = transmissao.entrega_enderecada
        if enderecada.enlace.id not in self._caminho:
            self._caminho.append(enderecada.enlace.id)

        transmissao = self._corromper_no_enlace(transmissao, fluxo)
        enderecada = transmissao.entrega_enderecada

        for entrega in transmissao.entregas:
            if entrega.enderecado:
                continue
            alheia = self.dispositivos[entrega.destinatario].receber(entrega)
            self._agendar(alheia.acoes, fluxo)

        destinatario = self.dispositivos[enderecada.destinatario]
        recepcao = destinatario.receber(enderecada)
        self._agendar(recepcao.acoes, fluxo)
        if not recepcao.aceito:
            return None
        assert recepcao.pacote is not None
        return destinatario, recepcao.pacote

    # -- emissão -----------------------------------------------------------

    def _agendar(self, acoes: Iterable[AcaoCamada], fluxo: Fluxo) -> None:
        for acao in acoes:
            self.fila.agendar_acao(
                self._instante,
                acao,
                descrever(acao),
                fluxo=fluxo.id,
                caminho=tuple(self._caminho),
            )


def executar(topologia: Topologia, caso: Caso) -> tuple[Evento, ...]:
    """Executa um caso **já resolvido** e devolve o registro pronto: a tupla
    imutável de `Evento`, numerada de 001 em diante, na ordem final.

    Recebe o `Caso` em vez do nome porque a interface (issue #56) precisa
    rodar casos que não estão declarados no arquivo — o caso corrente mais uma
    queda de enlace, o caso corrente mais um erro de bit. Montar esses casos é
    trabalho de `com_intervencao`; executá-los é o mesmo trabalho de sempre, e
    é essa igualdade que impede o programa de ter dois motores.

    O registro inclui os eventos secundários (seção 7.5); quem exibe filtra
    com `principais()`."""
    _recusar_intervencao_pendente(caso)
    return _Execucao(topologia, caso).executar()


def executar_caso(topologia: Topologia, caso: str) -> tuple[Evento, ...]:
    """Executa um caso declarado na topologia, pelo id.

    Esta é a entrega formal de F3 e a fronteira com a interface — `visual.py`
    recebe esta tupla e navega nela por índice, sem chamar camada, dispositivo
    ou roteador nenhum. A simulação roda inteira antes do primeiro desenho
    (issue #32).

    Levanta `KeyError` se o caso não existir na topologia e `CasoNaoSuportado`
    se ele depender de uma intervenção externa que o motor não aplica."""
    return executar(topologia, topologia.caso(caso))


_DESCRICOES_DE_INTERVENCAO = {
    "enlace_fora": "{enlace} fora",
    "erro_bit": "erro de bit em {enlace}",
}


def _descricao_da_intervencao(nova: EventoExterno) -> str:
    modelo = _DESCRICOES_DE_INTERVENCAO.get(nova.tipo, "{enlace} alterado")
    return modelo.format(enlace=nova.enlace)


def com_intervencao(caso: Caso, nova: EventoExterno) -> Caso:
    """Uma cópia do caso com mais uma intervenção externa agendada.

    O id derivado (`C2` vira `C2*`) não é enfeite, e a razão merece ficar
    escrita onde quem mexer vai ler. `_Execucao._comparacao` substitui, de
    propósito, a linha do caso em execução pelo η daquela execução — é o que
    faz o `METRICAS` mostrar o η real do que se acabou de rodar. Um derivado
    que continuasse se chamando `C2` cairia nessa regra, e a comparação lado a
    lado da seção 11.4 passaria a exibir o C2 quebrado no lugar do C2 íntegro,
    perdendo justamente o seu ponto de referência.

    O título derivado aparece no cabeçalho do registro salvo (seção 8.3), de
    modo que o arquivo não minta sobre o que foi executado.

    Derivar duas vezes não empilha asteriscos: derrubar um enlace **e**
    injetar um erro é um caso derivado só, com duas intervenções — e o título
    encadeia as duas descrições em vez de descartar a primeira, para que o
    cabeçalho do registro salvo não minta sobre a intervenção mais antiga."""
    ja_derivado = caso.id.endswith("*")
    conectivo = " e " if ja_derivado else " com "
    return replace(
        caso,
        id=caso.id if ja_derivado else f"{caso.id}*",
        titulo=f"{caso.titulo}{conectivo}{_descricao_da_intervencao(nova)}",
        eventos_externos=caso.eventos_externos + (nova,),
    )


# Os dois casos que o enunciado manda exibir lado a lado (seção 11.4): a mesma
# mensagem num enlace e em quatro.
_CASOS_DE_REFERENCIA = ("C1", "C2")


def _octetos_da_mensagem(fluxo: Fluxo) -> int:
    return len(fluxo.mensagem.encode("utf-8"))


def _texto_metricas(metricas: Metricas) -> str:
    """A linha 031 do Anexo B: `42 B úteis, 368 B transmitidos, η = 11,4%`.

    O η sai com uma casa decimal e vírgula, como o resto do documento e a barra
    inferior da interface (seção 9.1)."""
    eta = f"{metricas.eta * 100:.1f}".replace(".", ",")
    return (
        f"{metricas.dados_uteis} B úteis, "
        f"{metricas.total_transmitido} B transmitidos, η = {eta}%"
    )


@lru_cache(maxsize=8)
def comparacao_de_referencia(topologia: Topologia) -> tuple[tuple[str, float], ...]:
    """Os η dos casos de referência desta topologia — C1 (um enlace) e C2
    (quatro) —, que o enunciado manda exibir lado a lado (seção 11.4).

    Viajam no evento `METRICAS` de **todo** caso, para que a interface nunca
    precise executar nada por conta própria (regra de acoplamento, seção 4.2).
    São recalculados e não escritos à mão: numa topologia diferente C1 e C2 são
    outros casos, e o contraste continua verdadeiro. Caso de referência ausente
    do arquivo simplesmente não entra.

    Duas consequências que valem saber, porque são visíveis de fora:

    - executar um caso qualquer executa também os de referência, **uma vez por
      topologia** — daí o cache. Quem instrumenta as camadas para medir uma
      execução (T-R3, T-R5) precisa aquecer o cache antes de começar a medir,
      ou contará também as execuções auxiliares;
    - elas rodam **sem** métricas, que é o que impede C1 de pedir a comparação
      que pediria C1 de novo.

    Devolve tuplas em vez de dicionário porque o resultado é memoizado e não
    deve ser mutável por quem recebe."""
    valores = []
    for referencia in _CASOS_DE_REFERENCIA:
        try:
            caso = topologia.caso(referencia)
        except KeyError:
            continue  # topologia sem este caso — nada a comparar
        valores.append((referencia, _eta_de(topologia, caso)))
    return tuple(valores)


def _eta_de(topologia: Topologia, caso: Caso) -> float:
    """O η de um caso, executado à parte só para a comparação da seção 11.4."""
    eventos = _Execucao(topologia, caso).executar(com_metricas=False)
    transmitidos = [e for e in eventos if e.acao == "TRANSMITE"]
    entregues = {e.fluxo for e in eventos if e.acao == "ENTREGA"}
    total = sum(e.tamanho or 0 for e in transmitidos)
    if not total:
        return 0.0
    dados = sum(
        _octetos_da_mensagem(f) for f in caso.fluxos if f.id in entregues
    )
    return dados / total


def topologia_do_caso(topologia: Topologia, caso: Caso) -> Topologia:
    """A topologia como o caso a quer: cópia com as intervenções aplicadas.

    Hoje só `enlace_fora`. O erro de bit de C6 não mexe na topologia — corrompe
    um quadro em trânsito —, e por isso entrará noutro ponto (issue #41).

    É pública porque quem quiser saber por onde o caso **realmente** passa
    precisa dela: o mapa de F5, que desenha o enlace caído de C4 em traço
    cortado, e qualquer verificação que recalcule rotas por fora do registro
    (T-R4). Consultar a topologia original daria a rota que o caso não usou."""
    efetiva = topologia
    for intervencao in caso.eventos_externos:
        if intervencao.tipo == "enlace_fora":
            efetiva = efetiva.com_enlace_ativo(intervencao.enlace, ativo=False)
    return efetiva


def intervencoes_pendentes(caso: Caso) -> tuple[EventoExterno, ...]:
    """As intervenções que o caso declara e o motor ainda não sabe aplicar."""
    return tuple(
        evento
        for evento in caso.eventos_externos
        if evento.tipo not in TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS
    )


def casos_executaveis(topologia: Topologia) -> tuple[str, ...]:
    """Os casos da topologia que o motor executa por inteiro, na ordem do
    arquivo. É o que os testes de restrição usam para varrer "todos os casos"
    sem tropeçar nos que dependem de F4 — e o que a interface, em F5, usará
    para montar o seletor de caso sem oferecer o que não roda."""
    return tuple(
        caso.id for caso in topologia.casos if not intervencoes_pendentes(caso)
    )


def _recusar_intervencao_pendente(caso: Caso) -> None:
    pendentes = intervencoes_pendentes(caso)
    if not pendentes:
        return
    descricao = ", ".join(
        f"{evento.tipo} no enlace {evento.enlace}" for evento in pendentes
    )
    raise CasoNaoSuportado(
        f"O caso {caso.id} depende de intervenção externa que o motor ainda "
        f"não aplica ({descricao}): o registro sairia sem ela, parecido com o "
        f"de um caso sem falha nenhuma. Implementação prevista para F4."
    )


def principais(eventos: Iterable[Evento]) -> tuple[Evento, ...]:
    """O registro como ele aparece por padrão: sem os eventos secundários — as
    estações de difusão que receberam o quadro e o descartaram por endereço
    (seção 7.5). Eles não são removidos da execução, só ocultados na exibição,
    e por isso não consomem número de passo."""
    return tuple(e for e in eventos if not e.secundario)


# --------------------------------------------------------------------------
# Ponto de entrada de linha de comando (seções 8.3 e 13.2, issue #33)
# --------------------------------------------------------------------------

# Cabeçalho de identificação do arquivo salvo (seção 8.3). Vai comentado com
# `#` para que o próprio arquivo continue legível como registro: quem compara
# com o Anexo B (T-FMT, issue #34) descarta as linhas de `#` e o que sobra é o
# registro puro, linha 001 em diante.
_TITULO = "Simulador do Modelo OSI — Comunicação de Dados"
_FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

# Códigos de saída. Qualquer coisa diferente de 0 serve ao critério de
# aceitação ("termina com código diferente de zero"); vale separá-los porque um
# roteiro de teste sabe distinguir arquivo inválido de caso inexistente sem ler
# a mensagem. O 2 é o que o `argparse` já usa para erro de uso.
SAIDA_OK = 0
SAIDA_ERRO = 1


def cabecalho(topologia: Topologia, caso: Caso, agora: datetime | None = None) -> str:
    """As cinco linhas de identificação da seção 8.3, sem o registro."""
    instante = (agora or datetime.now()).strftime(_FORMATO_DATA)
    return "\n".join(
        [
            f"# {_TITULO}",
            f"# Caso: {caso.id} — {caso.titulo}",
            f"# Topologia: {topologia.nome}",
            f"# Data: {instante}",
            "#",
        ]
    )


def formatar_registro(
    topologia: Topologia,
    caso: Caso,
    eventos: Iterable[Evento],
    agora: datetime | None = None,
) -> str:
    """Cabeçalho mais uma linha de `Evento.linha()` por evento.

    Recebe os eventos já filtrados por quem chama: é decisão de exibição
    mostrar ou não os secundários (seção 7.5), não de formatação."""
    linhas = [cabecalho(topologia, caso, agora)]
    linhas.extend(evento.linha() for evento in eventos)
    return "\n".join(linhas) + "\n"


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    analisador = argparse.ArgumentParser(
        prog="simulador.py",
        description=(
            "Executa um caso do simulador do modelo OSI e imprime o registro "
            "de eventos. Modo textual, sem interface gráfica (seção 13.2)."
        ),
    )
    analisador.add_argument(
        "--caso",
        required=True,
        metavar="ID",
        help="identificador do caso a executar, como declarado no topologia.json (C1…C7)",
    )
    analisador.add_argument(
        "--log",
        metavar="ARQUIVO",
        help="salva o registro neste arquivo (UTF-8); sem ele, o registro sai na saída padrão",
    )
    analisador.add_argument(
        "--topologia",
        metavar="ARQUIVO",
        help=(
            "usa outra topologia; sem ele, o topologia.json ao lado do "
            "executável (pasta_base(), seção 5.8)"
        ),
    )
    analisador.add_argument(
        "--descartes",
        action="store_true",
        help="inclui no registro os eventos secundários — as estações que ignoram o quadro por endereço (seção 7.5)",
    )
    return analisador.parse_args(argv)


def _saida_em_utf8() -> None:
    """Põe a saída padrão e a de erro em UTF-8, antes de qualquer escrita.

    O registro é cheio de caractere que não cabe em `cp1252`, que é o que o
    console do Windows entrega: a seta de `10.0.1.10 → 10.0.3.10`, na linha
    004. Sem isto, `python simulador.py --caso C2` — a forma padrão, sem
    `--log` — morre de `UnicodeEncodeError` com rastreamento de pilha, o que a
    seção 5.7 proíbe justamente na máquina em que o programa vai rodar (F7,
    Windows sem Python instalado).

    Vale para a saída de erro pelo mesmo motivo: as mensagens de `ErroTopologia`
    são em português e o `cp1252` cobre os acentos por acaso, não por garantia.

    Um fluxo redirecionado por teste (`io.StringIO`) não tem `reconfigure` e é
    deixado como está — ele já guarda texto, não octetos."""
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if reconfigurar is not None:
            reconfigurar(encoding="utf-8")


def principal(argv: Sequence[str] | None = None) -> int:
    """`python simulador.py --caso C2 --log saida.txt`.

    Carrega a topologia, valida, executa o caso **inteiro** (issue #32) e só
    então formata: nada aqui desenha, e nenhuma janela é aberta.

    Erro de topologia e caso inexistente saem como **mensagem** na saída de
    erro, nunca como rastreamento de pilha (seção 5.7) — numa máquina Windows
    sem Python o traceback é ilegível para quem editou o arquivo."""
    opcoes = _argumentos(argv)
    _saida_em_utf8()

    try:
        topologia = carregar_topologia(opcoes.topologia)
    except ErroTopologia as erro:
        print(erro, file=sys.stderr)
        return SAIDA_ERRO

    try:
        caso = topologia.caso(opcoes.caso)
    except KeyError:
        existentes = ", ".join(c.id for c in topologia.casos)
        print(
            f"Caso {opcoes.caso} não existe nesta topologia. Casos declarados: {existentes}",
            file=sys.stderr,
        )
        return SAIDA_ERRO

    try:
        eventos = executar_caso(topologia, caso.id)
    except CasoNaoSuportado as erro:
        print(erro, file=sys.stderr)
        return SAIDA_ERRO

    if not opcoes.descartes:
        eventos = principais(eventos)
    texto = formatar_registro(topologia, caso, eventos)

    if opcoes.log is None:
        sys.stdout.write(texto)
        return SAIDA_OK

    try:
        # `newline="\n"` para o arquivo sair igual nos dois sistemas: sem isto
        # o Windows grava CRLF e a comparação byte a byte de dois registros
        # passa a depender da plataforma que gerou cada um.
        with open(opcoes.log, "w", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(texto)
    except OSError as erro:
        print(f"Não foi possível escrever {opcoes.log}: {erro.strerror}", file=sys.stderr)
        return SAIDA_ERRO
    return SAIDA_OK


if __name__ == "__main__":
    sys.exit(principal())
