"""Carga, validação e roteamento do arquivo de topologia (`topologia.json`).

O núcleo do módulo é a **leitura e desserialização** das cinco seções de
primeiro nível — `redes`, `dispositivos`, `enlaces`, `parametros`, `casos`
(issue #16) —, e em volta dela:

- roteamento — o Dijkstra sobre o grafo de enlaces (`menor_caminho`,
  `Topologia.arvore_caminhos`, issue #18), a tabela de encaminhamento por
  roteador (`Topologia.tabela_encaminhamento`, issue #19) e a decisão
  binária da camada 3 do computador (`Topologia.decisao_computador`,
  issue #20) já ficam aqui; o desempate determinístico vive no
  `menor_caminho` (issue #21) e o recálculo por queda de enlace é
  `Topologia.com_enlace_ativo` + `texto_enlace_fora` (issue #22 — o
  roteamento já filtra por `enlace.ativo` e recomputa a cada chamada, então
  basta trocar a topologia). O modelo de enlace como segmento e a expansão
  `Enlace.arestas()` que alimenta o grafo entraram com a issue #17;
- validação semântica — `validar_topologia`, com as dez verificações
  V-01..V-10 da seção 5.7 (nomes duplicados, endereços repetidos, grafo
  conexo, gateway na rede local, etc., issue #23). Roda no fim de
  `analisar_topologia`: nenhum caminho de carga devolve topologia inválida;
- resolução da localização do arquivo sem caminho absoluto — `pasta_base()`
  e `ARQUIVO_TOPOLOGIA` (seção 5.8, issue #24).

O que este módulo garante é o que o enunciado chama de "falha com mensagem
clara, nunca com stack trace" (seção 5.7): todo erro de forma do arquivo
(JSON inválido, seção faltando, campo com o tipo errado, `tipo` de
dispositivo/enlace fora do vocabulário) e todo erro de conteúdo (V-01..V-10)
vira uma `ErroTopologia` com texto legível. Nenhuma exceção nativa de Python
(`KeyError`, `TypeError`, `json.JSONDecodeError`) escapa daqui — numa máquina
sem Python instalado (F7) o rastreamento de pilha seria ilegível.

Regra de dependência (seção 4.1 da proposta técnica): `rede.py` **não importa** `camadas.py`
nem nenhum módulo de interface. Só biblioteca padrão.
"""

import itertools
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Collection, Iterable, Literal, Mapping

TipoDispositivo = Literal["computador", "roteador"]
TipoEnlace = Literal["difusao", "ponto-a-ponto"]
ModoCaso = Literal["sequencial", "concorrente"]
TipoEventoExterno = Literal["enlace_fora", "erro_bit"]

_TIPOS_DISPOSITIVO: frozenset[str] = frozenset(("computador", "roteador"))
_TIPOS_ENLACE: frozenset[str] = frozenset(("difusao", "ponto-a-ponto"))
_MODOS_CASO: frozenset[str] = frozenset(("sequencial", "concorrente"))
_TIPOS_EVENTO_EXTERNO: frozenset[str] = frozenset(("enlace_fora", "erro_bit"))

# O projeto inteiro usa /24 (seção 1.2: "todas as máscaras são /24; sem IPv6,
# sem sub-redes de tamanho variável"). Uma máscara diferente no arquivo é
# quase sempre erro de digitação — vale barrar na carga, com mensagem clara,
# em vez de deixar o roteamento produzir uma rota estranha lá na frente.
_MASCARA_UNICA = 24


class ErroTopologia(Exception):
    """Arquivo de topologia malformado.

    Carrega uma mensagem pronta para ser mostrada ao usuário — em modo
    textual pela saída de erro, em modo gráfico (F5+) numa janela de
    diálogo. Quem chama `carregar_topologia` / `analisar_topologia` trata
    esta exceção e **nunca** deixa vazar o rastreamento de pilha."""


# --------------------------------------------------------------------------
# Estruturas — retratos imutáveis das cinco seções do arquivo
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Rede:
    id: str
    prefixo: str          # CIDR, ex. "10.0.1.0/24" (sempre /24 no projeto)
    rotulo: str


@dataclass(frozen=True)
class InterfaceRede:
    nome: str             # "eth0", "e0"…
    rede: str             # id de uma entrada de `redes`
    logico: str           # endereço lógico (IP)
    mascara: int          # sempre 24 (ver _MASCARA_UNICA)
    fisico: str           # endereço físico (MAC)


@dataclass(frozen=True)
class Posicao:
    x: int
    y: int


@dataclass(frozen=True)
class Dispositivo:
    nome: str
    tipo: TipoDispositivo
    posicao: Posicao
    interfaces: tuple[InterfaceRede, ...]
    # Só computador tem gateway; roteador tem apenas interfaces (issue #16).
    gateway: str | None = None


@dataclass(frozen=True)
class PontaEnlace:
    dispositivo: str      # nome de uma entrada de `dispositivos`
    interface: str        # nome de uma interface daquele dispositivo


@dataclass(frozen=True)
class Aresta:
    """Uma aresta do grafo de roteamento (seção 6.1): a ligação direta entre
    duas pontas de um mesmo enlace, já na forma que o Dijkstra (issue #18)
    consome — o vértice é o dispositivo, o custo é o do segmento.

    É **dirigida**: `Enlace.arestas()` devolve os dois sentidos de cada par,
    para o construtor do grafo não precisar espelhar. As interfaces são a de
    saída em `origem` e a de entrada em `destino` — a tabela de encaminhamento
    (issue #19) precisa da interface local de cada salto."""

    origem: str
    destino: str
    custo: int
    enlace: str            # id do Enlace que a gerou
    interface_origem: str
    interface_destino: str


@dataclass(frozen=True)
class Enlace:
    """Um enlace é um **segmento com lista de pontas**, não um par fixo
    (seção 5.1) — é o que deixa a entrega direta de C1 acontecer (H1→H2 pela
    Rede A, sem roteador) e o descarte por endereço da Aula 2 sair de graça
    (ação `IGNORA`). Dois tipos, com invariantes conferidas na carga
    (issue #17):

    - `difusao` — segmento de rede local, **N ≥ 2 pontas**, **custo sempre 0**
      (seção 5.2: a linha 011 do Anexo B só fecha se o trecho R3→Rede C não
      somar nada);
    - `ponto-a-ponto` — **exatamente 2 pontas**, e entre roteadores (esta
      última conferida em `_verificar_ponto_a_ponto`, que enxerga os tipos).

    `arestas()` expande o segmento para o grafo que o Dijkstra percorre."""

    id: str
    tipo: TipoEnlace
    rede: str             # id de uma entrada de `redes`
    custo: int
    ativo: bool           # C4 derruba um enlace pondo isto em false
    rotulo: str
    pontas: tuple[PontaEnlace, ...]

    def arestas(self) -> tuple[Aresta, ...]:
        """Expande o segmento nas arestas do grafo de roteamento (seção 6.1).

        `ponto-a-ponto` (2 pontas) → 2 arestas, uma por sentido.
        `difusao` (N pontas) → N·(N−1) arestas: no mesmo meio todas as pontas
        se alcançam diretamente, com o custo do segmento (0).

        Não filtra por `ativo` — quem monta o grafo decide isso
        (`Topologia.arestas`); aqui a expansão é puramente estrutural."""
        return tuple(
            Aresta(
                origem=a.dispositivo,
                destino=b.dispositivo,
                custo=self.custo,
                enlace=self.id,
                interface_origem=a.interface,
                interface_destino=b.interface,
            )
            for a, b in itertools.permutations(self.pontas, 2)
        )


@dataclass(frozen=True)
class Salto:
    """Uma entrada da árvore de menor caminho: como uma origem fixa alcança
    o dispositivo `destino` (seção 6.1). É o insumo bruto de que a tabela de
    encaminhamento de um roteador (issue #19) é derivada.

    - `custo` — custo total do caminho (soma dos custos dos enlaces).
    - `proximo_salto` — **nome do dispositivo** do primeiro salto a partir
      da origem. É sobre este campo que incide o desempate lexicográfico da
      seção 6.4 (issue #21). Coincide com `destino` quando o destino já é
      diretamente alcançável.
    - `interface_saida` — a interface **local da origem** por onde esse
      primeiro salto sai; alimenta a coluna "Interface de saída" da tabela
      6.2.
    - `caminho` — a sequência de dispositivos da origem ao destino, ambos
      inclusos (o que a tabela 6.5 chama de "Caminho")."""

    destino: str
    custo: int
    proximo_salto: str
    interface_saida: str
    caminho: tuple[str, ...]


@dataclass(frozen=True)
class ArvoreCaminhos:
    """Resultado do Dijkstra a partir de uma origem (seção 6.1): um `Salto`
    por dispositivo alcançável. A própria origem não entra — não é destino
    de si mesma.

    É a "árvore de menor caminho" antes de virar tabela de encaminhamento:
    a issue #19 traduz uma destas por roteador para o formato prefixo →
    próximo salto → interface → custo; a issue #20 nem chega a usá-la (o
    computador decide por rede local + gateway, sem Dijkstra)."""

    origem: str
    saltos: tuple[Salto, ...]     # ordenada por `destino`

    def salto(self, destino: str) -> "Salto | None":
        """O `Salto` até `destino`, ou `None` se não há caminho (pedir a
        própria origem também devolve `None`)."""
        for s in self.saltos:
            if s.destino == destino:
                return s
        return None

    def alcanca(self, destino: str) -> bool:
        return self.salto(destino) is not None


@dataclass(frozen=True)
class RotaEncaminhamento:
    """Uma linha da tabela de encaminhamento de um roteador (seção 6.2):
    para onde repassar um pacote cujo destino cai no prefixo `prefixo`.

    - `prefixo` — CIDR do destino, sempre /24 no projeto ("10.0.3.0/24").
    - `proximo_salto` — **endereço lógico** do roteador vizinho para quem
      repassar, ou `None` quando a rede é **diretamente conectada**: aí a
      entrega é local, não há salto seguinte (a linha "—" da tabela 6.2).
    - `interface_saida` — nome da interface **local do roteador** por onde
      o pacote sai ("e1").
    - `custo` — custo total do caminho até a rede; 0 quando diretamente
      conectada."""

    prefixo: str
    proximo_salto: str | None
    interface_saida: str
    custo: int

    @property
    def diretamente_conectada(self) -> bool:
        return self.proximo_salto is None


@dataclass(frozen=True)
class TabelaEncaminhamento:
    """A tabela de encaminhamento de um roteador (seção 6.2), derivada da
    sua árvore de menor caminho (issue #19).

    É o que a camada 3 do roteador consulta na ação `ROTEIA` — recebida via
    `Contexto`, nunca buscada aqui pela camada 2 (restrição R4). `rotas` traz
    **uma entrada por rede alcançável** da topologia, ordenada por prefixo.
    Uma rede sem caminho (partição depois de um enlace cair) simplesmente
    não aparece: `consulta` devolve `None`, o que a camada 3 traduz em
    `DESCARTA` (seção 6.6, comportamento de C5)."""

    roteador: str
    rotas: tuple[RotaEncaminhamento, ...]

    def consulta(self, logico: str) -> "RotaEncaminhamento | None":
        """A rota para um endereço lógico de destino, ou `None` se nenhum
        prefixo casa.

        Como toda máscara é /24 (seção 1.2), o "prefixo mais longo" da seção
        6.2 se reduz à igualdade dos três primeiros octetos; e como os
        prefixos da topologia não se sobrepõem, no máximo uma linha casa."""
        alvo = _rede_24(logico)
        for rota in self.rotas:
            if _rede_24(rota.prefixo) == alvo:
                return rota
        return None


@dataclass(frozen=True)
class DecisaoComputador:
    """O resultado da decisão de roteamento de um computador (seção 6.3),
    devolvido por `Topologia.decisao_computador`.

    Ao contrário da `RotaEncaminhamento` de um roteador, não traz `prefixo`
    nem `custo`: o computador não consulta prefixo nenhum além da própria
    rede /24 e não conhece o custo do caminho completo — só sabe entregar
    ao vizinho imediato (o próprio destino, se local) ou empurrar o pacote
    para o gateway.

    - `destino` — o endereço lógico consultado, ecoado para quem monta o
      evento `ROTEIA`.
    - `entrega_direta` — `True` no ramo "destino na mesma rede", `False` no
      ramo "via gateway". É o único bit que o evento `ROTEIA` do computador
      precisa distinguir (seção 10, C1 vs. Anexo B).
    - `proximo_salto` — endereço lógico do próximo salto: o próprio
      `destino` na entrega direta, o gateway do computador caso contrário.
      É o que a L2 recebe como `ctx.vizinho` (R4).
    - `interface_saida` — nome da interface local por onde o pacote sai
      ("eth0")."""

    destino: str
    entrega_direta: bool
    proximo_salto: str
    interface_saida: str

    @property
    def via_gateway(self) -> bool:
        return not self.entrega_direta


@dataclass(frozen=True)
class Cabecalhos:
    """Octetos de cada cabeçalho (seção 11.2). Chaves do arquivo: L7, L6,
    L5, L4, L3, L2 (cabeçalho de enlace) e T2 (finalizador de enlace)."""

    l7: int
    l6: int
    l5: int
    l4: int
    l3: int
    l2: int
    t2: int


@dataclass(frozen=True)
class Cifra:
    algoritmo: str        # "xor" (decisão D2)
    chave: str            # "REDES"


@dataclass(frozen=True)
class Verificacao:
    algoritmo: str        # "crc32" (decisão D3)
    polinomio: str        # "0xEDB88320" — texto; a conversão é de quem usa


@dataclass(frozen=True)
class Sessao:
    prefixo: str          # "S-"
    digitos: int          # 4  →  S-0001


@dataclass(frozen=True)
class Velocidades:
    lenta: int
    media: int
    rapida: int


@dataclass(frozen=True)
class Parametros:
    cabecalhos: Cabecalhos
    limite_segmento: int
    codificacao: str
    cifra: Cifra
    verificacao: Verificacao
    sessao: Sessao
    velocidades_ms: Velocidades


@dataclass(frozen=True)
class Extremo:
    """Uma ponta de um `Fluxo`. A origem sempre traz `dispositivo`,
    `processo` e `porta`; o destino traz `dispositivo`+`processo`
    (C1–C3, C7) ou apenas `logico` (C5, destino inalcançável). `porta`
    está sempre presente."""

    porta: int
    dispositivo: str | None = None
    processo: str | None = None
    logico: str | None = None


@dataclass(frozen=True)
class Fluxo:
    id: str
    origem: Extremo
    destino: Extremo
    mensagem: str


@dataclass(frozen=True)
class EventoExterno:
    """Intervenção agendada de um caso (seção 5.5). `enlace_fora` (C4) traz
    só `enlace`; `erro_bit` (C6) traz também `quadro` e `bit`."""

    tipo: TipoEventoExterno
    enlace: str
    quadro: str | None = None
    bit: int | None = None


@dataclass(frozen=True)
class Caso:
    """Um caso obrigatório (C1–C7), lido inteiro do arquivo — nunca
    codificado em Python (seção 5.5). `fluxos` já vem resolvido: se o
    arquivo usa `herda`, os fluxos do caso pai são copiados aqui na carga,
    e o campo `herda` fica preservado só como registro da origem."""

    id: str
    titulo: str
    modo: ModoCaso
    fluxos: tuple[Fluxo, ...]
    eventos_externos: tuple[EventoExterno, ...]
    padrao: bool = False
    herda: str | None = None
    # Limite de segmentação só deste caso, quando ele precisa de um diferente
    # do global (seção 8.1: a convenção C2 pede 40 em E7 e os valores de
    # E1–E6 exigem 46 ou mais). `None` = usa `parametros.limite_segmento`.
    limite_segmento: int | None = None


@dataclass(frozen=True)
class Topologia:
    versao: str
    nome: str
    redes: tuple[Rede, ...]
    dispositivos: tuple[Dispositivo, ...]
    enlaces: tuple[Enlace, ...]
    parametros: Parametros
    casos: tuple[Caso, ...]

    # Acessos por identificador. São varreduras lineares — a topologia de
    # referência tem 9 dispositivos e 7 enlaces —, e levantam KeyError
    # (não ErroTopologia) porque a esta altura o arquivo já está bem
    # formado: pedir um id que não existe é erro de quem chama.
    def rede(self, id: str) -> Rede:
        return _por_id(self.redes, "id", id, "rede")

    def dispositivo(self, nome: str) -> Dispositivo:
        return _por_id(self.dispositivos, "nome", nome, "dispositivo")

    def enlace(self, id: str) -> Enlace:
        return _por_id(self.enlaces, "id", id, "enlace")

    def caso(self, id: str) -> Caso:
        return _por_id(self.casos, "id", id, "caso")

    def com_enlace_ativo(self, enlace_id: str, *, ativo: bool) -> "Topologia":
        """Uma nova `Topologia`, cópia desta, com o enlace `enlace_id`
        marcado `ativo`. É o ponto de entrada do recálculo de rota de C4
        (seção 6.1, issue #22): "Dijkstra executado novamente sempre que um
        enlace mude de estado".

        Não há recálculo a disparar aqui de forma explícita — todo o
        roteamento (`arestas`, `arvore_caminhos`, `tabela_encaminhamento`,
        `decisao_computador`) já filtra por `enlace.ativo` e recomputa do
        zero a cada chamada. "Disparar o recálculo" é, então, o motor (F3)
        passar a consultar a topologia devolvida: ao processar um
        `eventos_externos` do tipo `enlace_fora`, ele troca a topologia
        corrente por `topo.com_enlace_ativo("E-R1-R4", ativo=False)`, emite
        o evento de sistema `ENLACE_FORA` (texto em `texto_enlace_fora`)
        e só então reprocessa o primeiro `ROTEIA` afetado — em C4, a
        próxima consulta de R1 a `10.0.3.0/24` passa a sair por R2 (custo 3,
        interface e2) e nenhuma rota volta a citar `E-R1-R4`.

        Reverter (`ativo=True`) percorre o mesmo caminho e recalcula igual —
        não é exigido por nenhum caso obrigatório, mas cai de graça. Se o
        enlace já está no estado pedido, devolve `self` sem cópia.

        Levanta `KeyError` se `enlace_id` não existe — a esta altura a
        topologia já está bem formada."""
        alvo = self.enlace(enlace_id)  # KeyError se o id não existe
        if alvo.ativo == ativo:
            return self
        enlaces = tuple(
            replace(e, ativo=ativo) if e.id == enlace_id else e
            for e in self.enlaces
        )
        return replace(self, enlaces=enlaces)

    def arestas(self, incluir_inativos: bool = False) -> tuple[Aresta, ...]:
        """Todas as arestas do grafo de roteamento, prontas para o Dijkstra
        (issue #18). Por padrão omite os enlaces com `ativo == False`: é assim
        que o recálculo de rota de C4 enxerga a rede depois que um enlace cai."""
        return tuple(
            aresta
            for enlace in self.enlaces
            if incluir_inativos or enlace.ativo
            for aresta in enlace.arestas()
        )

    def arvore_caminhos(
        self, origem: str, incluir_inativos: bool = False
    ) -> ArvoreCaminhos:
        """Árvore de menor caminho a partir de `origem` (seção 6.1), sobre os
        enlaces ativos por padrão. Derrubar um enlace (`ativo = False`) e
        chamar de novo é o que sustenta o recálculo de rota de C4.

        Os computadores entram como **folhas**: podem ser origem ou destino
        de um caminho, nunca trânsito (é o que `nao_encaminham` diz ao
        Dijkstra). Computador não encaminha pacote — não tem tabela, só rede
        local e gateway (seção 6.3) —, e sem essa restrição um host de nome
        lexicograficamente pequeno ganharia o desempate da seção 6.4 num
        segmento de difusão de custo 0 e viraria próximo salto na tabela de
        um roteador."""
        return menor_caminho(
            origem, self.arestas(incluir_inativos), self._nao_encaminham()
        )

    def _nao_encaminham(self) -> frozenset[str]:
        """Os vértices que o roteamento trata como folha: os computadores."""
        return frozenset(
            d.nome for d in self.dispositivos if d.tipo == "computador"
        )

    def arvores_de_roteamento(
        self, incluir_inativos: bool = False
    ) -> dict[str, ArvoreCaminhos]:
        """Uma árvore de menor caminho por roteador — a base de que a tabela
        de encaminhamento de cada um (issue #19) é derivada. O computador não
        entra: ele decide por rede local + gateway, não por Dijkstra (seção
        6.3, issue #20)."""
        return {
            d.nome: self.arvore_caminhos(d.nome, incluir_inativos)
            for d in self.dispositivos
            if d.tipo == "roteador"
        }

    def tabela_encaminhamento(
        self, roteador: str, incluir_inativos: bool = False
    ) -> TabelaEncaminhamento:
        """Deriva a tabela de encaminhamento de `roteador` (seção 6.2) da sua
        árvore de menor caminho. Sobre os enlaces ativos por padrão — marcar
        um enlace `ativo = False` e chamar de novo é o recálculo de rota de C4
        (issue #22).

        Levanta `KeyError` se `roteador` não existe ou não é roteador: a esta
        altura a topologia já está bem formada, e o computador não tem tabela
        (decide por rede local + gateway, seção 6.3)."""
        disp = self.dispositivo(roteador)
        if disp.tipo != "roteador":
            raise KeyError(
                f"{roteador!r} é {disp.tipo}, não roteador — computador não "
                f"tem tabela de encaminhamento (seção 6.3)"
            )

        arvore = self.arvore_caminhos(roteador, incluir_inativos)
        # Só conta como local a interface cujo enlace está no ar. Uma rede
        # diretamente conectada não passa pelo Dijkstra, então sem esta
        # filtragem o enlace derrubado de C4 continuaria anunciado: R1 com
        # 10.0.14.0/24 por e1, custo 0, por um cabo que caiu — e um pacote para
        # 10.0.14.4 seria "entregue direto" em vez de dar a volta por R2. Com o
        # enlace fora, a rede vira remota como qualquer outra, ou some da
        # tabela se não houver caminho (seção 6.6).
        redes_locais = {
            iface.rede: iface
            for iface in disp.interfaces
            if incluir_inativos or self._enlace_da_interface(roteador, iface.nome).ativo
        }

        rotas: list[RotaEncaminhamento] = []
        for rede in self.redes:
            iface_local = redes_locais.get(rede.id)
            if iface_local is not None:
                rotas.append(
                    RotaEncaminhamento(
                        prefixo=rede.prefixo,
                        proximo_salto=None,
                        interface_saida=iface_local.nome,
                        custo=0,
                    )
                )
                continue

            salto = self._salto_ate_rede(arvore, rede.id, roteador)
            if salto is None:
                continue  # rede sem caminho — sem entrada (seção 6.6)
            rotas.append(
                RotaEncaminhamento(
                    prefixo=rede.prefixo,
                    proximo_salto=self._logico_do_vizinho(disp, salto),
                    interface_saida=salto.interface_saida,
                    custo=salto.custo,
                )
            )

        rotas.sort(key=lambda r: _octetos(r.prefixo))
        return TabelaEncaminhamento(roteador=roteador, rotas=tuple(rotas))

    def tabelas_encaminhamento(
        self, incluir_inativos: bool = False
    ) -> dict[str, TabelaEncaminhamento]:
        """Uma tabela de encaminhamento por roteador (issue #19). O
        computador não entra — decide por rede local + gateway, sem tabela
        (seção 6.3, issue #20)."""
        return {
            d.nome: self.tabela_encaminhamento(d.nome, incluir_inativos)
            for d in self.dispositivos
            if d.tipo == "roteador"
        }

    def decisao_computador(self, computador: str, destino: str) -> DecisaoComputador:
        """A decisão de roteamento de um computador para `destino` (seção 6.3).

        O computador não tem tabela de encaminhamento nem roda Dijkstra: só
        compara o prefixo /24 da sua interface local com o do endereço de
        destino e escolhe um de dois ramos —

            destino ∈ minha rede  →  entrega direta (próximo salto = destino)
            senão                 →  próximo salto = gateway

        É essa bifurcação, e nenhuma outra lógica, que separa C1 (H1→H2,
        mesma rede) de C2 (H1→H4, via R1); por isso o evento `ROTEIA` do
        computador tem de dizer qual ramo foi tomado (campo `entrega_direta`).

        O computador **nunca descarta por conta própria**: a rota para o
        gateway sempre serve de saída, mesmo para um destino que acabará
        descartado num roteador adiante (C5). Só o roteador, com tabela
        genuinamente incompleta, descobre a ausência de rota (seção 6.6).

        `dispositivos.py` (issue #27) consome esta decisão para preencher o
        `Contexto` antes do `ROTEIA` da L3 — se quiser, traduzindo-a nas duas
        entradas (`minha /24` e `0.0.0.0/0` para o gateway) que a consulta
        por prefixo mais longo da L3 percorre sem distinguir roteador de
        computador; a L3 não tem ramo condicional por tipo de dispositivo, a
        bifurcação mora aqui.

        Levanta `KeyError` se `computador` não existe ou é um roteador — a
        esta altura a topologia já está bem formada, e o roteador decide por
        `tabela_encaminhamento` (seção 6.2)."""
        disp = self.dispositivo(computador)
        if disp.tipo != "computador":
            raise KeyError(
                f"{computador!r} é {disp.tipo}, não computador — o roteador "
                f"decide por tabela de encaminhamento (seção 6.2), não pela "
                f"bifurcação binária da seção 6.3"
            )
        assert disp.gateway is not None, (
            "o parser garante 'gateway' preenchido para todo computador"
        )

        alvo = _rede_24(destino)
        local = next(
            (i for i in disp.interfaces if _rede_24(i.logico) == alvo), None
        )
        if local is not None:
            return DecisaoComputador(
                destino=destino,
                entrega_direta=True,
                proximo_salto=destino,
                interface_saida=local.nome,
            )

        saida = next(
            (i for i in disp.interfaces if _rede_24(i.logico) == _rede_24(disp.gateway)),
            None,
        )
        assert saida is not None, (
            f"gateway {disp.gateway!r} de {computador!r} não cai em nenhuma de "
            f"suas redes locais — topologia inválida (validação V-08, issue #23)"
        )
        return DecisaoComputador(
            destino=destino,
            entrega_direta=False,
            proximo_salto=disp.gateway,
            interface_saida=saida.nome,
        )

    def _enlace_da_interface(self, dispositivo: str, interface: str) -> Enlace:
        """O enlace em que a interface está ligada. V-04 garante que existe um,
        e só um (`validar_topologia`), então a busca não tem caso de ausência."""
        for enlace in self.enlaces:
            for ponta in enlace.pontas:
                if ponta.dispositivo == dispositivo and ponta.interface == interface:
                    return enlace
        raise KeyError(  # pragma: no cover — V-04 impede
            f"interface {dispositivo}.{interface} não pertence a enlace nenhum"
        )

    def _salto_ate_rede(
        self, arvore: ArvoreCaminhos, rede_id: str, roteador: str
    ) -> "Salto | None":
        """O melhor `Salto` para alcançar a rede `rede_id`: entre os
        dispositivos que têm interface nela, o de menor custo a partir do
        roteador. Empate resolvido como no Dijkstra (seção 6.4) — menor nome
        de próximo salto —, com `destino` como desempate final só para a
        escolha ser estável entre execuções."""
        melhor: Salto | None = None
        for d in self.dispositivos:
            if d.nome == roteador:
                continue
            if not any(iface.rede == rede_id for iface in d.interfaces):
                continue
            salto = arvore.salto(d.nome)
            if salto is None:
                continue
            if melhor is None or (
                salto.custo,
                salto.proximo_salto,
                salto.destino,
            ) < (melhor.custo, melhor.proximo_salto, melhor.destino):
                melhor = salto
        return melhor

    def _logico_do_vizinho(self, roteador: Dispositivo, salto: Salto) -> str:
        """O endereço lógico do próximo salto, na forma que a tabela 6.2
        mostra (um IP, não o nome do dispositivo): o endereço do vizinho
        `salto.proximo_salto` na mesma rede da interface de saída local."""
        # `interface_saida` sempre nomeia uma interface da origem — garantia
        # de `menor_caminho`.
        iface_saida = next(
            i for i in roteador.interfaces if i.nome == salto.interface_saida
        )
        vizinho = self.dispositivo(salto.proximo_salto)
        iface_vizinho = next(
            (i for i in vizinho.interfaces if i.rede == iface_saida.rede), None
        )
        assert iface_vizinho is not None, (
            f"{salto.proximo_salto!r} é próximo salto de {roteador.nome!r} "
            f"pela rede {iface_saida.rede!r}, mas não tem interface nela"
        )
        return iface_vizinho.logico


def _por_id(itens: tuple, atributo: str, valor: str, rotulo: str):
    for item in itens:
        if getattr(item, atributo) == valor:
            return item
    raise KeyError(f"{rotulo} {valor!r} não existe na topologia")


def texto_enlace_fora(enlace: Enlace) -> str:
    """A `descricao` canônica do evento de sistema `ENLACE_FORA` (camada 0,
    seções 7.4 e 10/C4):

        0NN | -- | -- | ENLACE_FORA | enlace R1–R4 indisponível, rotas recalculadas

    Identifica o enlace pelo `rotulo` da topologia ("R1–R4"), não pelo id
    ("E-R1-R4"). Fica em `rede.py`, junto do modelo de `Enlace`, e não no
    motor (F3): assim a redação exigida caractere a caractere pelo critério
    de C4 mora num lugar só e já é verificável em F2. `rede.py` não monta o
    `Evento` — devolve só o texto, e por isso não importa `evento.py`."""
    return f"enlace {enlace.rotulo} indisponível, rotas recalculadas"


# --------------------------------------------------------------------------
# Localização do arquivo (seção 5.8, issue #24)
# --------------------------------------------------------------------------


def pasta_base() -> Path:
    """A pasta onde `topologia.json` é procurado — a única resolução de
    caminho do programa inteiro (seção 5.8).

    Dois modos de execução, e a diferença entre eles é justamente o que o
    enunciado exige:

    - **executável PyInstaller** (`--onefile`): `sys.frozen` está definido e
      `sys.executable` é o próprio `SimuladorOSI.exe`. A pasta é a dele — o
      `topologia.json` fica **ao lado do executável**, editável pelo usuário,
      nunca embutido no pacote (seção 5.8: "é assim que a troca de topologia
      sem recompilar funciona"). `__file__`, neste modo, apontaria para a
      pasta temporária que o PyInstaller descompacta, que some ao fechar.
    - **execução a partir do código** (`python simulador.py`): a pasta do
      próprio módulo.

    Nenhum caminho absoluto aparece escrito no código (T-PATH); ambos os
    ramos derivam do ambiente em tempo de execução, o que também deixa o
    programa rodar de pasta com espaço ou acento no nome (checklist 14.3)."""
    if getattr(sys, "frozen", False):  # executável PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent  # execução a partir do código


ARQUIVO_TOPOLOGIA = pasta_base() / "topologia.json"


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------


def carregar_topologia(caminho: str | os.PathLike | None = None) -> Topologia:
    """Lê `caminho`, faz o parse do JSON, valida e devolve a `Topologia`.

    Sem argumento usa `ARQUIVO_TOPOLOGIA`, isto é, o `topologia.json` ao lado
    do executável (seção 5.8, issue #24); um caminho explícito serve aos
    testes e à troca de topologia por linha de comando.

    Levanta `ErroTopologia` (mensagem legível, sem stack trace) se o
    arquivo não existe, não é UTF-8 válido, não é JSON válido, não tem a
    forma esperada ou não passa nas dez verificações da seção 5.7. Não
    calcula rotas — isso é sob demanda (`arvore_caminhos`, issue #18)."""
    caminho = os.fspath(ARQUIVO_TOPOLOGIA if caminho is None else caminho)
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            texto = arquivo.read()
    except FileNotFoundError:
        raise ErroTopologia(f"Arquivo de topologia não encontrado: {caminho}") from None
    except OSError as erro:
        raise ErroTopologia(f"Não foi possível ler {caminho}: {erro.strerror}") from None
    except UnicodeDecodeError:
        raise ErroTopologia(
            f"{caminho} não está em UTF-8 — salve o arquivo com essa codificação"
        ) from None

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ErroTopologia(
            f"JSON inválido em {caminho}, linha {erro.lineno}, coluna {erro.colno}: {erro.msg}"
        ) from None

    return analisar_topologia(dados)


def analisar_topologia(dados: Mapping[str, Any]) -> Topologia:
    """Constrói a `Topologia` a partir do JSON já desserializado (um dict).

    Separada de `carregar_topologia` para poder ser exercida com dicionários
    montados em memória (fixtures de T-TOP, issue #25) sem passar por
    arquivo. Mesma garantia: só `ErroTopologia`, nunca exceção nativa."""
    raiz = _dict(dados, "topologia")

    versao = _texto(_campo(raiz, "versao", "topologia"), "topologia.versao")
    nome = _texto(_campo(raiz, "nome", "topologia"), "topologia.nome")

    redes = tuple(
        _rede(item, f"redes[{i}]")
        for i, item in enumerate(_lista(_campo(raiz, "redes", "topologia"), "topologia.redes"))
    )
    dispositivos = tuple(
        _dispositivo(item, f"dispositivos[{i}]")
        for i, item in enumerate(
            _lista(_campo(raiz, "dispositivos", "topologia"), "topologia.dispositivos")
        )
    )
    enlaces = tuple(
        _enlace(item, f"enlaces[{i}]")
        for i, item in enumerate(_lista(_campo(raiz, "enlaces", "topologia"), "topologia.enlaces"))
    )
    _verificar_ponto_a_ponto(enlaces, dispositivos)
    parametros = _parametros(_campo(raiz, "parametros", "topologia"), "parametros")
    casos = _casos(_lista(_campo(raiz, "casos", "topologia"), "topologia.casos"))

    topologia = Topologia(
        versao=versao,
        nome=nome,
        redes=redes,
        dispositivos=dispositivos,
        enlaces=enlaces,
        parametros=parametros,
        casos=casos,
    )
    validar_topologia(topologia)
    return topologia


# --------------------------------------------------------------------------
# Validação semântica — as dez verificações da seção 5.7 (issue #23)
# --------------------------------------------------------------------------
#
# A diferença entre esta seção e os "verificadores de forma" logo abaixo é de
# escopo: lá se confere um valor isolado (é texto? é um dos tipos previstos?);
# aqui se confere a topologia inteira, cruzando seções — um endereço repetido
# entre dois dispositivos, um enlace que cita interface que não existe, uma
# ilha desligada do resto do grafo. Toda falha vira `ErroTopologia` com a
# mensagem exata da tabela 5.7, que a interface (F5) mostra em janela de
# diálogo: numa máquina Windows sem Python, um traceback não diz nada ao
# usuário.
#
# A ordem importa. As verificações de referência (`_referencias_resolvem`)
# vêm antes de V-02..V-10 porque todas elas pressupõem que nome de
# dispositivo, de interface e de rede resolvem para alguma coisa: sem isso,
# V-04 acusaria "interface órfã" quando o erro real é um nome digitado errado
# na ponta do enlace.


def validar_topologia(topologia: Topologia) -> None:
    """Roda V-01..V-10 sobre uma topologia já bem-formada (seção 5.7).

    Chamada no fim de `analisar_topologia`, de modo que nenhum caminho de
    carga devolva topologia inválida. É pública para que o T-TOP (issue #25)
    possa exercitar as verificações isoladamente."""
    _v01_nomes_de_dispositivo_unicos(topologia)
    _ids_de_rede_unicos(topologia)
    _ids_de_enlace_unicos(topologia)
    _prefixos_unicos(topologia)
    _referencias_resolvem(topologia)
    _v02_enderecos_fisicos_unicos(topologia)
    _v03_enderecos_logicos_unicos(topologia)
    _v04_cada_interface_em_exatamente_um_enlace(topologia)
    _pontas_na_rede_do_enlace(topologia)
    _v05_logico_dentro_do_prefixo(topologia)
    _v06_custos_nao_negativos(topologia)
    _v07_grafo_conexo(topologia)
    _v08_casos_citam_o_que_existe(topologia)
    _v09_gateway_na_rede_local(topologia)
    _v10_limite_segmento_comporta_os_casos(topologia)


def _v01_nomes_de_dispositivo_unicos(topologia: Topologia) -> None:
    """V-01. O nome é a chave de tudo o que vem depois — pontas de enlace,
    fluxos dos casos, vértices do Dijkstra. Dois dispositivos com o mesmo
    nome fariam um deles sumir silenciosamente da simulação."""
    vistos: set[str] = set()
    for dispositivo in topologia.dispositivos:
        if dispositivo.nome in vistos:
            raise ErroTopologia(f"Dispositivo duplicado: {dispositivo.nome}")
        vistos.add(dispositivo.nome)


def _ids_de_rede_unicos(topologia: Topologia) -> None:
    """Duas redes com o mesmo id fazem uma delas sumir: interface, enlace e
    prefixo passam a resolver para a primeira.

    Antes desta verificação o erro aparecia deslocado — a rede engolida virava
    "Interface H3.eth0 referencia rede inexistente: B" em
    `_referencias_resolvem`, apontando para a interface inocente em vez da
    declaração duplicada. Por isso roda antes dela."""
    vistos: set[str] = set()
    for rede in topologia.redes:
        if rede.id in vistos:
            raise ErroTopologia(f"Rede duplicada: {rede.id}")
        vistos.add(rede.id)


def _ids_de_enlace_unicos(topologia: Topologia) -> None:
    """`Topologia.enlace()` devolve o primeiro que casa e `com_enlace_ativo`
    altera todos os que casam: com id repetido, derrubar um enlace em C4
    derrubaria o outro junto, e o registro mostraria um `ENLACE_FORA` que não
    corresponde ao que saiu do grafo."""
    vistos: set[str] = set()
    for enlace in topologia.enlaces:
        if enlace.id in vistos:
            raise ErroTopologia(f"Enlace duplicado: {enlace.id}")
        vistos.add(enlace.id)


def _prefixos_unicos(topologia: Topologia) -> None:
    """Duas redes com o mesmo prefixo tornam o encaminhamento ambíguo: como
    tudo é /24, `CamadaRede.roteia` casa o destino por prefixo e espera **uma**
    rota (`assert len(escolhidas) <= 1`). O erro apareceria no primeiro
    `ROTEIA`, já dentro da simulação, e não na carga.

    Roda antes de V-05 porque a duplicata costuma arrastar um endereço para
    fora do prefixo, e a mensagem de V-05 apontaria a interface em vez da
    rede."""
    dona_de: dict[str, str] = {}
    for rede in topologia.redes:
        anterior = dona_de.get(rede.prefixo)
        if anterior is not None:
            raise ErroTopologia(
                f"Prefixo repetido em duas redes: {rede.prefixo} "
                f"(redes {anterior} e {rede.id})"
            )
        dona_de[rede.prefixo] = rede.id


def _pontas_na_rede_do_enlace(topologia: Topologia) -> None:
    """A ponta amarra o enlace a uma interface; as duas têm de estar na mesma
    rede.

    Se não estiverem, o enlace continua bem formado para V-04 (cada interface
    aparece em exatamente um enlace) e o grafo continua conexo — mas o endereço
    lógico que a camada 3 resolve para o vizinho (`_logico_do_vizinho`) não
    pertence à rede por onde o quadro vai sair. Era daí que vinha o
    `AssertionError` cru, na primeira `tabela_encaminhamento`, bem longe do
    ponto realmente errado do arquivo.

    Roda depois de V-04, e não antes: interface citada por dois enlaces é o
    defeito mais básico dos dois, e a mensagem de V-04 é a que aponta para
    ele. Depende também de `_referencias_resolvem` — a interface citada
    precisa existir antes de se perguntar em que rede ela está."""
    rede_da_interface = {
        (dispositivo.nome, interface.nome): interface.rede
        for dispositivo in topologia.dispositivos
        for interface in dispositivo.interfaces
    }
    for enlace in topologia.enlaces:
        for ponta in enlace.pontas:
            rede = rede_da_interface[(ponta.dispositivo, ponta.interface)]
            if rede != enlace.rede:
                raise ErroTopologia(
                    f"Enlace {enlace.id} cita a interface {ponta.dispositivo}."
                    f"{ponta.interface}, que está na rede {rede}, e não na rede "
                    f"{enlace.rede} do enlace"
                )


def _referencias_resolvem(topologia: Topologia) -> None:
    """Pré-requisito de V-04 e V-05: todo nome citado existe.

    Não está na tabela 5.7 como linha própria porque é o que torna as outras
    verificações possíveis — mas falha com a mesma clareza, apontando o
    enlace e a ponta exatos."""
    redes = {rede.id for rede in topologia.redes}
    interfaces_de = {
        dispositivo.nome: {interface.nome for interface in dispositivo.interfaces}
        for dispositivo in topologia.dispositivos
    }

    for dispositivo in topologia.dispositivos:
        for interface in dispositivo.interfaces:
            if interface.rede not in redes:
                raise ErroTopologia(
                    f"Interface {dispositivo.nome}.{interface.nome} referencia "
                    f"rede inexistente: {interface.rede}"
                )

    for enlace in topologia.enlaces:
        if enlace.rede not in redes:
            raise ErroTopologia(
                f"Enlace {enlace.id} referencia rede inexistente: {enlace.rede}"
            )
        for ponta in enlace.pontas:
            if ponta.dispositivo not in interfaces_de:
                raise ErroTopologia(
                    f"Enlace {enlace.id} cita o dispositivo {ponta.dispositivo}, "
                    f"que não existe"
                )
            if ponta.interface not in interfaces_de[ponta.dispositivo]:
                raise ErroTopologia(
                    f"Enlace {enlace.id} cita a interface {ponta.dispositivo}."
                    f"{ponta.interface}, que não existe"
                )


def _v02_enderecos_fisicos_unicos(topologia: Topologia) -> None:
    """V-02. Endereço físico repetido quebraria o descarte por endereço da
    camada 2 (ação `IGNORA`): duas estações no mesmo segmento aceitariam o
    mesmo quadro."""
    vistos: set[str] = set()
    for dispositivo in topologia.dispositivos:
        for interface in dispositivo.interfaces:
            if interface.fisico in vistos:
                raise ErroTopologia(f"Endereço físico repetido: {interface.fisico}")
            vistos.add(interface.fisico)


def _v03_enderecos_logicos_unicos(topologia: Topologia) -> None:
    """V-03. O par lógico é fixo da origem ao destino (R3); um endereço
    repetido tornaria o destino ambíguo."""
    vistos: set[str] = set()
    for dispositivo in topologia.dispositivos:
        for interface in dispositivo.interfaces:
            if interface.logico in vistos:
                raise ErroTopologia(f"Endereço lógico repetido: {interface.logico}")
            vistos.add(interface.logico)


def _v04_cada_interface_em_exatamente_um_enlace(topologia: Topologia) -> None:
    """V-04. Interface fora de qualquer enlace é uma placa sem cabo: a camada
    1 não teria por onde transmitir. Interface em dois enlaces tornaria o
    vizinho ambíguo, e é a L3 que escolhe o vizinho (R4)."""
    enlaces_de: dict[tuple[str, str], list[str]] = {}
    for enlace in topologia.enlaces:
        for ponta in enlace.pontas:
            enlaces_de.setdefault((ponta.dispositivo, ponta.interface), []).append(
                enlace.id
            )

    for dispositivo in topologia.dispositivos:
        for interface in dispositivo.interfaces:
            ids = enlaces_de.get((dispositivo.nome, interface.nome), [])
            if not ids:
                raise ErroTopologia(
                    f"Interface {dispositivo.nome}.{interface.nome} não pertence "
                    f"a nenhum enlace"
                )
            if len(ids) > 1:
                raise ErroTopologia(
                    f"Interface {dispositivo.nome}.{interface.nome} pertence a "
                    f"mais de um enlace: {', '.join(ids)}"
                )


def _v05_logico_dentro_do_prefixo(topologia: Topologia) -> None:
    """V-05. Como tudo é /24 (seção 1.2), "pertencer à rede" é ter os três
    primeiros octetos do prefixo. É esta coincidência que a decisão binária
    da camada 3 do computador usa (issue #20) — um endereço fora do prefixo
    mandaria o tráfego local para o gateway."""
    prefixo_de = {rede.id: rede.prefixo for rede in topologia.redes}
    for dispositivo in topologia.dispositivos:
        for interface in dispositivo.interfaces:
            prefixo = prefixo_de[interface.rede]
            if _rede_24(interface.logico) != _rede_24(prefixo):
                raise ErroTopologia(f"{interface.logico} não pertence a {prefixo}")


def _v06_custos_nao_negativos(topologia: Topologia) -> None:
    """V-06. Dijkstra só vale com custos não negativos; um custo negativo
    produziria rota "mais barata" quanto mais longa. (Que difusão tenha custo
    exatamente 0 já é conferido na carga, seção 5.2.)"""
    for enlace in topologia.enlaces:
        if enlace.custo < 0:
            raise ErroTopologia(f"Custo inválido no enlace {enlace.id}")


def _v07_grafo_conexo(topologia: Topologia) -> None:
    """V-07. Um dispositivo inalcançável nunca receberia mensagem nenhuma, e
    o caso que o citasse terminaria em descarte sem explicação.

    A busca usa **todos** os enlaces, inclusive os marcados `ativo: false`:
    o que se confere aqui é a topologia como projetada. Derrubar um enlace é
    intervenção de caso (C4), e aí a rota sumir é justamente o que se quer
    demonstrar."""
    if not topologia.dispositivos:
        raise ErroTopologia("A topologia não declara nenhum dispositivo")

    vizinhos: dict[str, set[str]] = {d.nome: set() for d in topologia.dispositivos}
    for enlace in topologia.enlaces:
        for aresta in enlace.arestas():
            vizinhos[aresta.origem].add(aresta.destino)

    raiz = topologia.dispositivos[0].nome
    alcancados = {raiz}
    fila = [raiz]
    while fila:
        atual = fila.pop()
        for vizinho in vizinhos[atual]:
            if vizinho not in alcancados:
                alcancados.add(vizinho)
                fila.append(vizinho)

    inalcancaveis = sorted(
        d.nome for d in topologia.dispositivos if d.nome not in alcancados
    )
    if inalcancaveis:
        raise ErroTopologia(
            f"A topologia possui dispositivos inalcançáveis: {', '.join(inalcancaveis)}"
        )


def _v08_casos_citam_o_que_existe(topologia: Topologia) -> None:
    """V-08. Os casos vão no arquivo (seção 5.5), então trocar a topologia sem
    atualizar os casos é o erro mais provável de quem edita o arquivo — e o
    que mais destruiria a promessa de "outra rede só trocando o arquivo".

    Uma ponta com apenas `logico` não é erro: é o destino inalcançável de C5,
    que existe como endereço e de propósito não existe como dispositivo."""
    nomes = {d.nome for d in topologia.dispositivos}
    enlaces = {e.id for e in topologia.enlaces}
    for caso in topologia.casos:
        for fluxo in caso.fluxos:
            for extremo in (fluxo.origem, fluxo.destino):
                if extremo.dispositivo is not None and extremo.dispositivo not in nomes:
                    raise ErroTopologia(
                        f"O caso {caso.id} referencia dispositivo inexistente: "
                        f"{extremo.dispositivo}"
                    )
        for evento in caso.eventos_externos:
            if evento.enlace not in enlaces:
                raise ErroTopologia(
                    f"O caso {caso.id} referencia enlace inexistente: {evento.enlace}"
                )


def _v09_gateway_na_rede_local(topologia: Topologia) -> None:
    """V-09. A decisão binária da camada 3 do computador (seção 6.3) só fecha
    se o gateway estiver na rede local: fora dela, o computador precisaria de
    um gateway para alcançar o próprio gateway."""
    for dispositivo in topologia.dispositivos:
        if dispositivo.tipo != "computador" or dispositivo.gateway is None:
            continue
        redes_locais = {_rede_24(i.logico) for i in dispositivo.interfaces}
        if _rede_24(dispositivo.gateway) not in redes_locais:
            raise ErroTopologia(f"Gateway de {dispositivo.nome} fora da rede local")


def limite_de_segmento(topologia: Topologia, caso: Caso) -> int:
    """O limite de carga útil da camada 4 que vale **neste** caso.

    O arquivo declara um limite global em `parametros.limite_segmento`, e um
    caso pode sobrescrevê-lo. A razão está na seção 8.1 da documentação: a
    convenção C2 do enunciado fixa 40 octetos, mas os valores publicados de
    E1 a E6 só existem com segmento único, o que exige 46 ou mais. Nenhum
    valor único atende aos dois lados, e é por isso que C7 — o caso que existe
    para demonstrar segmentação — declara o seu."""
    return (
        caso.limite_segmento
        if caso.limite_segmento is not None
        else topologia.parametros.limite_segmento
    )


def _v10_limite_segmento_comporta_os_casos(topologia: Topologia) -> None:
    """V-10. `limite_segmento` é o limite de carga útil da camada 4 (decisão
    D1: 64 octetos, "maior que 46, porque C2 gera segmento único").

    O arquivo não marca quais casos devem segmentar, então a leitura adotada
    é estrutural: **o caso de mensagem mais longa é o caso de segmentação**
    (C7, 180 octetos) e todos os demais são de segmento único. Baixar o
    limite a ponto de fatiar a mensagem de referência de 42 octetos mudaria o
    registro do Anexo B sem que ninguém pedisse — é isso que esta verificação
    barra.

    **Decisão sobre a isenção (issue #33).** A regra original isentava sempre a
    maior mensagem, e num arquivo de caso único isso isentava o arquivo
    inteiro: a verificação não conferia nada. A isenção passa a exigir
    contraste — só existe "caso de segmentação" quando há **mais de um tamanho
    de mensagem** no arquivo. Com todas as mensagens do mesmo tamanho, caso
    único incluído, não há como distinguir "mensagem longa de propósito" de
    "limite errado", e então todas têm de caber num segmento. Quem quiser um
    arquivo de caso único que segmente declara um segundo caso mais curto — o
    mesmo contraste que a topologia de referência tem entre C7 e C1.

    O que conta é a mensagem **mais o cabeçalho de sessão** (seção 5.6:
    42 + 4 = 46), porque a camada 5 age antes da camada 4."""
    mensagens = [
        len(fluxo.mensagem.encode("utf-8"))
        for caso in topologia.casos
        for fluxo in caso.fluxos
    ]
    if not mensagens:
        return

    l5 = topologia.parametros.cabecalhos.l5
    # Sem dois tamanhos diferentes não há caso de segmentação a isentar.
    isento = max(mensagens) if len(set(mensagens)) > 1 else None
    for caso in topologia.casos:
        if caso.limite_segmento is not None:
            # O caso declarou o seu limite: segmentar (ou não) ali é intenção
            # escrita no arquivo, não efeito colateral de mexer no global.
            continue
        for fluxo in caso.fluxos:
            octetos = len(fluxo.mensagem.encode("utf-8"))
            if octetos == isento:
                continue  # o caso de segmentação — segmentar é o objetivo dele
            if octetos + l5 > topologia.parametros.limite_segmento:
                raise ErroTopologia(
                    f"limite_segmento incompatível com o caso {caso.id}"
                )


# --------------------------------------------------------------------------
# Verificadores de forma — toda falha vira ErroTopologia
# --------------------------------------------------------------------------


def _tipo_json(valor: Any) -> str:
    if valor is None:
        return "nulo"
    if isinstance(valor, bool):
        return "booleano"
    if isinstance(valor, (int, float)):
        return "número"
    if isinstance(valor, str):
        return "texto"
    if isinstance(valor, list):
        return "lista"
    if isinstance(valor, dict):
        return "objeto"
    return type(valor).__name__


def _dict(valor: Any, onde: str) -> dict:
    if not isinstance(valor, dict):
        raise ErroTopologia(f"{onde}: esperava um objeto JSON, veio {_tipo_json(valor)}")
    return valor


def _lista(valor: Any, onde: str) -> list:
    if not isinstance(valor, list):
        raise ErroTopologia(f"{onde}: esperava uma lista, veio {_tipo_json(valor)}")
    return valor


def _texto(valor: Any, onde: str) -> str:
    if not isinstance(valor, str):
        raise ErroTopologia(f"{onde}: esperava texto, veio {_tipo_json(valor)}")
    return valor


def _inteiro(valor: Any, onde: str) -> int:
    # bool é subclasse de int em Python — true/false não são inteiros aqui.
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroTopologia(f"{onde}: esperava um número inteiro, veio {_tipo_json(valor)}")
    return valor


def _booleano(valor: Any, onde: str) -> bool:
    if not isinstance(valor, bool):
        raise ErroTopologia(f"{onde}: esperava booleano (true/false), veio {_tipo_json(valor)}")
    return valor


def _campo(obj: dict, chave: str, onde: str) -> Any:
    if chave not in obj:
        raise ErroTopologia(f"{onde}: campo obrigatório ausente: {chave!r}")
    return obj[chave]


def _um_de(valor: str, permitidos: frozenset[str], onde: str) -> str:
    if valor not in permitidos:
        opcoes = ", ".join(repr(o) for o in sorted(permitidos))
        raise ErroTopologia(f"{onde}: valor {valor!r} inválido — esperava um de {opcoes}")
    return valor


# --------------------------------------------------------------------------
# Parsers de cada seção
# --------------------------------------------------------------------------


def _rede(item: Any, onde: str) -> Rede:
    obj = _dict(item, onde)
    return Rede(
        id=_texto(_campo(obj, "id", onde), f"{onde}.id"),
        prefixo=_prefixo(_texto(_campo(obj, "prefixo", onde), f"{onde}.prefixo"), f"{onde}.prefixo"),
        rotulo=_texto(_campo(obj, "rotulo", onde), f"{onde}.rotulo"),
    )


def _prefixo(valor: str, onde: str) -> str:
    """O prefixo de uma rede, em `a.b.c.d/24`.

    Conferido aqui, na carga, e não onde é usado: `_rede_24` recorta os três
    primeiros octetos como texto e não repara em `10.0.1.x/24`, de modo que um
    octeto não numérico atravessava a validação inteira e só estourava em
    `_octetos`, um `ValueError` cru, quando a tabela de encaminhamento fosse
    ordenada. A máscara é conferida pelo mesmo motivo da máscara de interface:
    o projeto é todo /24 (seção 1.2)."""
    corpo, barra, mascara = valor.partition("/")
    octetos = corpo.split(".")
    bem_formado = (
        barra
        and mascara.isdigit()
        and len(octetos) == 4
        and all(o.isdigit() and int(o) <= 255 for o in octetos)
    )
    if not bem_formado:
        raise ErroTopologia(
            f"{onde}: {valor!r} não é um prefixo IPv4 válido — esperado a.b.c.d/24"
        )
    if int(mascara) != _MASCARA_UNICA:
        raise ErroTopologia(
            f"{onde}: máscara /{mascara} não é suportada — o projeto usa apenas /24"
        )
    return valor


def _interface(item: Any, onde: str) -> InterfaceRede:
    obj = _dict(item, onde)
    mascara = _inteiro(_campo(obj, "mascara", onde), f"{onde}.mascara")
    if mascara != _MASCARA_UNICA:
        raise ErroTopologia(
            f"{onde}.mascara: máscara /{mascara} não é suportada — o projeto usa apenas /24"
        )
    return InterfaceRede(
        nome=_texto(_campo(obj, "nome", onde), f"{onde}.nome"),
        rede=_texto(_campo(obj, "rede", onde), f"{onde}.rede"),
        logico=_texto(_campo(obj, "logico", onde), f"{onde}.logico"),
        mascara=mascara,
        fisico=_texto(_campo(obj, "fisico", onde), f"{onde}.fisico"),
    )


def _posicao(item: Any, onde: str) -> Posicao:
    obj = _dict(item, onde)
    return Posicao(
        x=_inteiro(_campo(obj, "x", onde), f"{onde}.x"),
        y=_inteiro(_campo(obj, "y", onde), f"{onde}.y"),
    )


def _dispositivo(item: Any, onde: str) -> Dispositivo:
    obj = _dict(item, onde)
    nome = _texto(_campo(obj, "nome", onde), f"{onde}.nome")
    tipo = _um_de(
        _texto(_campo(obj, "tipo", onde), f"{onde}.tipo"), _TIPOS_DISPOSITIVO, f"{onde}.tipo"
    )
    interfaces = tuple(
        _interface(sub, f"{onde}.interfaces[{i}]")
        for i, sub in enumerate(
            _lista(_campo(obj, "interfaces", onde), f"{onde}.interfaces")
        )
    )
    if not interfaces:
        raise ErroTopologia(f"{onde}.interfaces: um dispositivo precisa de ao menos uma interface")

    gateway_bruto = obj.get("gateway")
    if tipo == "computador":
        if gateway_bruto is None:
            raise ErroTopologia(f"{onde}: computador {nome!r} não declara 'gateway'")
        gateway = _texto(gateway_bruto, f"{onde}.gateway")
    else:  # roteador
        if gateway_bruto is not None:
            raise ErroTopologia(
                f"{onde}: roteador {nome!r} não deve declarar 'gateway' — roteador só tem interfaces"
            )
        gateway = None

    return Dispositivo(
        nome=nome,
        tipo=tipo,  # type: ignore[arg-type]
        posicao=_posicao(_campo(obj, "posicao", onde), f"{onde}.posicao"),
        interfaces=interfaces,
        gateway=gateway,
    )


def _ponta(item: Any, onde: str) -> PontaEnlace:
    obj = _dict(item, onde)
    return PontaEnlace(
        dispositivo=_texto(_campo(obj, "dispositivo", onde), f"{onde}.dispositivo"),
        interface=_texto(_campo(obj, "interface", onde), f"{onde}.interface"),
    )


def _enlace(item: Any, onde: str) -> Enlace:
    obj = _dict(item, onde)
    ident = _texto(_campo(obj, "id", onde), f"{onde}.id")
    tipo = _um_de(
        _texto(_campo(obj, "tipo", onde), f"{onde}.tipo"), _TIPOS_ENLACE, f"{onde}.tipo"
    )
    custo = _custo(_campo(obj, "custo", onde), ident)
    pontas = tuple(
        _ponta(sub, f"{onde}.pontas[{i}]")
        for i, sub in enumerate(_lista(_campo(obj, "pontas", onde), f"{onde}.pontas"))
    )

    # Invariantes do modelo de segmento (issue #17, seções 5.1 e 5.2). São da
    # forma do próprio enlace; referência cruzada (a interface existe, o
    # dispositivo existe, o grafo é conexo) fica em `validar_topologia`
    # (V-01..V-10, issue #23). Que ponto-a-ponto ligue dois roteadores depende da lista de
    # dispositivos, então mora em `_verificar_ponto_a_ponto`.
    if tipo == "ponto-a-ponto":
        if len(pontas) != 2:
            raise ErroTopologia(
                f"{onde}: enlace ponto-a-ponto {ident!r} precisa de exatamente "
                f"2 pontas, veio {len(pontas)}"
            )
    else:  # difusao
        if len(pontas) < 2:
            raise ErroTopologia(
                f"{onde}: segmento de difusão {ident!r} precisa de ao menos "
                f"2 pontas, veio {len(pontas)}"
            )
        if custo != 0:
            raise ErroTopologia(
                f"{onde}.custo: segmento de difusão {ident!r} tem de ter custo 0 "
                f"(seção 5.2), veio {custo}"
            )

    return Enlace(
        id=ident,
        tipo=tipo,  # type: ignore[arg-type]
        rede=_texto(_campo(obj, "rede", onde), f"{onde}.rede"),
        custo=custo,
        ativo=_booleano(_campo(obj, "ativo", onde), f"{onde}.ativo"),
        rotulo=_texto(_campo(obj, "rotulo", onde), f"{onde}.rotulo"),
        pontas=pontas,
    )


def _custo(valor: Any, ident: str) -> int:
    """V-06 na forma: custo inteiro e não negativo (tabela 5.7).

    Mora aqui, e não só em `_v06_custos_nao_negativos`, porque `1.5` nem chega
    a virar `Enlace`: sem isto a mensagem que sairia seria a genérica de tipo
    ("esperava um número inteiro, veio número"), que não diz qual enlace. Custo
    **positivo** em segmento de difusão é outro engano — esse continua com a
    mensagem da seção 5.2, logo abaixo."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise ErroTopologia(f"Custo inválido no enlace {ident}")
    return valor


def _verificar_ponto_a_ponto(
    enlaces: tuple[Enlace, ...], dispositivos: tuple[Dispositivo, ...]
) -> None:
    """Invariante da seção 5.1: um enlace `ponto-a-ponto` liga dois roteadores.
    Precisa da lista de dispositivos para saber o tipo de cada ponta, por isso
    roda aqui e não dentro de `_enlace`.

    Só reclama de ponta que resolve para um dispositivo conhecido — apontar
    para um nome inexistente é assunto de `_referencias_resolvem`
    (issue #23)."""
    tipo_por_nome = {d.nome: d.tipo for d in dispositivos}
    for i, enlace in enumerate(enlaces):
        if enlace.tipo != "ponto-a-ponto":
            continue
        for ponta in enlace.pontas:
            tipo = tipo_por_nome.get(ponta.dispositivo)
            if tipo is not None and tipo != "roteador":
                raise ErroTopologia(
                    f"enlaces[{i}]: enlace ponto-a-ponto {enlace.id!r} inclui "
                    f"{ponta.dispositivo!r}, que é {tipo} — ponto-a-ponto é só "
                    f"entre roteadores (seção 5.1)"
                )


def _cabecalhos(item: Any, onde: str) -> Cabecalhos:
    obj = _dict(item, onde)
    return Cabecalhos(
        l7=_inteiro(_campo(obj, "L7", onde), f"{onde}.L7"),
        l6=_inteiro(_campo(obj, "L6", onde), f"{onde}.L6"),
        l5=_inteiro(_campo(obj, "L5", onde), f"{onde}.L5"),
        l4=_inteiro(_campo(obj, "L4", onde), f"{onde}.L4"),
        l3=_inteiro(_campo(obj, "L3", onde), f"{onde}.L3"),
        l2=_inteiro(_campo(obj, "L2", onde), f"{onde}.L2"),
        t2=_inteiro(_campo(obj, "T2", onde), f"{onde}.T2"),
    )


def _parametros(item: Any, onde: str) -> Parametros:
    obj = _dict(item, onde)
    cifra_obj = _dict(_campo(obj, "cifra", onde), f"{onde}.cifra")
    verif_obj = _dict(_campo(obj, "verificacao", onde), f"{onde}.verificacao")
    sessao_obj = _dict(_campo(obj, "sessao", onde), f"{onde}.sessao")
    veloc_obj = _dict(_campo(obj, "velocidades_ms", onde), f"{onde}.velocidades_ms")
    return Parametros(
        cabecalhos=_cabecalhos(_campo(obj, "cabecalhos", onde), f"{onde}.cabecalhos"),
        limite_segmento=_inteiro(
            _campo(obj, "limite_segmento", onde), f"{onde}.limite_segmento"
        ),
        codificacao=_texto(_campo(obj, "codificacao", onde), f"{onde}.codificacao"),
        cifra=Cifra(
            algoritmo=_texto(_campo(cifra_obj, "algoritmo", f"{onde}.cifra"), f"{onde}.cifra.algoritmo"),
            chave=_texto(_campo(cifra_obj, "chave", f"{onde}.cifra"), f"{onde}.cifra.chave"),
        ),
        verificacao=Verificacao(
            algoritmo=_texto(
                _campo(verif_obj, "algoritmo", f"{onde}.verificacao"),
                f"{onde}.verificacao.algoritmo",
            ),
            polinomio=_texto(
                _campo(verif_obj, "polinomio", f"{onde}.verificacao"),
                f"{onde}.verificacao.polinomio",
            ),
        ),
        sessao=Sessao(
            prefixo=_texto(_campo(sessao_obj, "prefixo", f"{onde}.sessao"), f"{onde}.sessao.prefixo"),
            digitos=_inteiro(
                _campo(sessao_obj, "digitos", f"{onde}.sessao"), f"{onde}.sessao.digitos"
            ),
        ),
        velocidades_ms=Velocidades(
            lenta=_inteiro(_campo(veloc_obj, "lenta", f"{onde}.velocidades_ms"), f"{onde}.velocidades_ms.lenta"),
            media=_inteiro(_campo(veloc_obj, "media", f"{onde}.velocidades_ms"), f"{onde}.velocidades_ms.media"),
            rapida=_inteiro(
                _campo(veloc_obj, "rapida", f"{onde}.velocidades_ms"), f"{onde}.velocidades_ms.rapida"
            ),
        ),
    )


def _extremo(item: Any, onde: str) -> Extremo:
    obj = _dict(item, onde)
    dispositivo = obj.get("dispositivo")
    logico = obj.get("logico")
    if dispositivo is None and logico is None:
        raise ErroTopologia(
            f"{onde}: uma ponta de fluxo precisa de 'dispositivo' ou 'logico'"
        )
    processo = obj.get("processo")
    return Extremo(
        porta=_inteiro(_campo(obj, "porta", onde), f"{onde}.porta"),
        dispositivo=None if dispositivo is None else _texto(dispositivo, f"{onde}.dispositivo"),
        processo=None if processo is None else _texto(processo, f"{onde}.processo"),
        logico=None if logico is None else _texto(logico, f"{onde}.logico"),
    )


def _fluxo(item: Any, onde: str) -> Fluxo:
    obj = _dict(item, onde)
    return Fluxo(
        id=_texto(_campo(obj, "id", onde), f"{onde}.id"),
        origem=_extremo(_campo(obj, "origem", onde), f"{onde}.origem"),
        destino=_extremo(_campo(obj, "destino", onde), f"{onde}.destino"),
        mensagem=_texto(_campo(obj, "mensagem", onde), f"{onde}.mensagem"),
    )


def _evento_externo(item: Any, onde: str) -> EventoExterno:
    obj = _dict(item, onde)
    tipo = _um_de(
        _texto(_campo(obj, "tipo", onde), f"{onde}.tipo"),
        _TIPOS_EVENTO_EXTERNO,
        f"{onde}.tipo",
    )
    enlace = _texto(_campo(obj, "enlace", onde), f"{onde}.enlace")
    if tipo == "erro_bit":
        quadro = _texto(_campo(obj, "quadro", onde), f"{onde}.quadro")
        bit = _inteiro(_campo(obj, "bit", onde), f"{onde}.bit")
    else:  # enlace_fora
        quadro = None
        bit = None
    return EventoExterno(tipo=tipo, enlace=enlace, quadro=quadro, bit=bit)  # type: ignore[arg-type]


def _caso_bruto(item: Any, onde: str) -> Caso:
    obj = _dict(item, onde)
    ident = _texto(_campo(obj, "id", onde), f"{onde}.id")

    modo_bruto = obj.get("modo", "sequencial")
    modo = _um_de(_texto(modo_bruto, f"{onde}.modo"), _MODOS_CASO, f"{onde}.modo")

    herda_bruto = obj.get("herda")
    herda = None if herda_bruto is None else _texto(herda_bruto, f"{onde}.herda")

    fluxos_bruto = obj.get("fluxos", [])
    fluxos = tuple(
        _fluxo(sub, f"{onde}.fluxos[{i}]")
        for i, sub in enumerate(_lista(fluxos_bruto, f"{onde}.fluxos"))
    )

    eventos = tuple(
        _evento_externo(sub, f"{onde}.eventos_externos[{i}]")
        for i, sub in enumerate(
            _lista(obj.get("eventos_externos", []), f"{onde}.eventos_externos")
        )
    )

    limite_bruto = obj.get("limite_segmento")
    limite = (
        None
        if limite_bruto is None
        else _inteiro(limite_bruto, f"{onde}.limite_segmento")
    )
    if limite is not None and limite <= 0:
        raise ErroTopologia(f"{onde}.limite_segmento: deve ser positivo")

    return Caso(
        id=ident,
        titulo=_texto(_campo(obj, "titulo", onde), f"{onde}.titulo"),
        modo=modo,  # type: ignore[arg-type]
        fluxos=fluxos,
        eventos_externos=eventos,
        padrao=_booleano(obj.get("padrao", False), f"{onde}.padrao"),
        herda=herda,
        limite_segmento=limite,
    )


def _casos(itens: list) -> tuple[Caso, ...]:
    """Lê a seção `casos` e resolve o `herda`: um caso sem `fluxos` próprios
    copia os do caso pai (C4 e C6 herdam de C2). O campo `herda` continua
    preenchido só como registro de onde os fluxos vieram."""
    brutos = [_caso_bruto(item, f"casos[{i}]") for i, item in enumerate(itens)]

    por_id: dict[str, Caso] = {}
    for caso in brutos:
        if caso.id in por_id:
            raise ErroTopologia(f"casos: identificador de caso repetido: {caso.id!r}")
        por_id[caso.id] = caso

    resolvidos: list[Caso] = []
    for caso in brutos:
        if caso.fluxos:
            resolvidos.append(caso)
            continue
        if caso.herda is None:
            raise ErroTopologia(
                f"casos: o caso {caso.id!r} não define 'fluxos' nem 'herda'"
            )
        pai = por_id.get(caso.herda)
        if pai is None:
            raise ErroTopologia(
                f"casos: o caso {caso.id!r} herda de {caso.herda!r}, que não existe"
            )
        if not pai.fluxos:
            raise ErroTopologia(
                f"casos: o caso {caso.id!r} herda de {caso.herda!r}, que também não define 'fluxos'"
            )
        resolvidos.append(replace(caso, fluxos=pai.fluxos))

    return tuple(resolvidos)


# --------------------------------------------------------------------------
# Roteamento — Dijkstra sobre o grafo de enlaces (seção 6.1, issue #18)
# --------------------------------------------------------------------------

_CUSTO_INALCANCAVEL = float("inf")


def menor_caminho(
    origem: str,
    arestas: Iterable[Aresta],
    nao_encaminham: Collection[str] = (),
) -> ArvoreCaminhos:
    """Dijkstra a partir de `origem` sobre o grafo dirigido descrito por
    `arestas` (seção 6.1): vértices são dispositivos, o custo de cada aresta
    é o do enlace que a gerou. Cada `Aresta` já vem com um sentido e um
    enlace inativo já deve ter sido filtrado por quem monta a lista
    (`Topologia.arestas`) — aqui todas as arestas contam.

    `nao_encaminham` lista os vértices que **não repassam pacotes**: um
    caminho pode nascer ou morrer neles, nunca atravessá-los. É por onde
    `Topologia.arvore_caminhos` informa quais dispositivos são computadores
    (seção 6.3: o computador tem rede local e gateway, não tabela de
    encaminhamento). Sem isso, num segmento de difusão com dois roteadores
    e um computador, o caminho `RA → H1 → RB` (custo 0, todo o segmento é
    de custo 0) empata com `RA → RB` e o desempate lexicográfico da seção
    6.4 elege o computador — a tabela de RA passaria a apontar um host como
    próximo salto. A origem é sempre isenta: ela é o ponto de partida, não
    trânsito, então `arvore_caminhos("H1")` continua saindo de H1
    normalmente.

    Um segmento de difusão de N pontas chega como N·(N−1) arestas de custo 0
    (via `Enlace.arestas()`), então "estar na mesma rede local" já é, para o
    Dijkstra, um conjunto de vizinhos a custo 0 — sem tratamento especial.

    **Desempate determinístico (seção 6.4, issue #21):** quando dois
    caminhos até o mesmo dispositivo empatam em custo, vence o de menor
    **nome de próximo salto** em ordem lexicográfica — e essa é a *única*
    regra de desempate (não há critério secundário por número de saltos).
    Sem ela a mesma topologia produziria árvores diferentes entre
    execuções — e mesmo entre duas ordens de leitura do `topologia.json` —,
    quebrando a reprodutibilidade que T-ROTA e T-C1..T-C7 exigem. O que a
    regra congela é o par `(custo, próximo salto)` de cada vértice, isto é, a
    decisão de encaminhamento; nos raros casos em que dois caminhos de mesmo
    custo saem pelo mesmo primeiro salto e só divergem adiante, qual dos dois
    o campo `caminho` mostra pode depender da ordem das arestas — é
    cosmético, não altera rota nem tabela (issue #19). Entre vértices que
    encaminham não há consequência colateral: com `nao_encaminham`
    preenchido, nenhum caminho atravessa um computador, então nem o
    `proximo_salto` da árvore nem a tabela de encaminhamento derivada dela
    (issue #19) podem citar um host.

    A implementação é um relaxamento até ponto fixo (estilo Bellman-Ford), e
    não o Dijkstra com fila de prioridade clássico: o grafo é minúsculo (a
    topologia de referência tem 9 vértices) e o ponto fixo trata sem caso
    especial as arestas de custo 0, onde dois vértices de mesma distância
    podem reescrever o próximo salto um do outro — um desempate que a poda
    antecipada do Dijkstra clássico deixaria escapar. O objetivo minimizado
    por vértice é o par `(custo, nome do próximo salto)`, que só decresce a
    cada relaxamento; como é limitado inferiormente, o laço termina."""
    arestas = tuple(arestas)
    # A origem encaminha o que ela mesma emite, esteja ou não na lista.
    bloqueados = frozenset(nao_encaminham) - {origem}

    dist: dict[str, float] = {origem: 0}
    prox: dict[str, str] = {}
    iface: dict[str, str] = {}
    pred: dict[str, str] = {}

    mudou = True
    while mudou:
        mudou = False
        for a in arestas:
            if a.origem in bloqueados:
                continue  # folha do grafo: origem ou destino, nunca trânsito
            base = dist.get(a.origem, _CUSTO_INALCANCAVEL)
            if base == _CUSTO_INALCANCAVEL:
                continue
            destino = a.destino
            if destino == origem:
                continue  # a origem não é destino de si mesma

            candidato = base + a.custo
            if a.origem == origem:
                salto_prox, salto_if = destino, a.interface_origem
            else:
                salto_prox, salto_if = prox[a.origem], iface[a.origem]

            atual = dist.get(destino, _CUSTO_INALCANCAVEL)
            if candidato < atual or (candidato == atual and salto_prox < prox[destino]):
                dist[destino] = candidato
                prox[destino] = salto_prox
                iface[destino] = salto_if
                pred[destino] = a.origem
                mudou = True

    saltos = tuple(
        Salto(
            destino=destino,
            custo=int(dist[destino]),
            proximo_salto=prox[destino],
            interface_saida=iface[destino],
            caminho=_reconstruir_caminho(origem, destino, pred),
        )
        for destino in sorted(dist)
        if destino != origem
    )
    return ArvoreCaminhos(origem=origem, saltos=saltos)


def _reconstruir_caminho(
    origem: str, destino: str, pred: Mapping[str, str]
) -> tuple[str, ...]:
    """Sobe a cadeia de predecessores de `destino` até `origem`. O desempate
    lexicográfico impede ciclo na árvore (cada troca de próximo salto é uma
    queda estrita em ordem de nome) — o `assert` só documenta essa garantia."""
    caminho = [destino]
    atual = destino
    while atual != origem:
        atual = pred[atual]
        assert atual not in caminho, (
            f"ciclo na árvore de menor caminho de {origem!r} até {destino!r}"
        )
        caminho.append(atual)
    caminho.reverse()
    return tuple(caminho)


# --------------------------------------------------------------------------
# Tabela de encaminhamento por roteador (seção 6.2, issue #19)
# --------------------------------------------------------------------------
#
# `Topologia.tabela_encaminhamento` traduz a árvore de menor caminho de um
# roteador (issue #18) para o formato prefixo → próximo salto → interface →
# custo. As estruturas `RotaEncaminhamento` / `TabelaEncaminhamento` e a
# lógica de derivação vivem junto de `Topologia`, mais acima; aqui fica só o
# utilitário de comparação de prefixo que ambos usam.


def _rede_24(endereco: str) -> str:
    """Os três primeiros octetos de um endereço IPv4, seja ele de host
    ("10.0.3.10") ou um CIDR ("10.0.3.0/24").

    É a chave de comparação de prefixo do projeto: como tudo é /24 (seção 1.2),
    dois endereços estão na mesma rede exatamente quando este prefixo coincide
    — não é preciso o longest-prefix-match genérico com máscaras variáveis."""
    return ".".join(endereco.split("/", 1)[0].split(".")[:3])


def _octetos(endereco: str) -> tuple[int, ...]:
    """Os octetos de um endereço/prefixo como inteiros, para ordenar a tabela
    numericamente (10.0.2.0 antes de 10.0.12.0, não o contrário da ordem de
    texto)."""
    return tuple(int(o) for o in endereco.split("/", 1)[0].split("."))
