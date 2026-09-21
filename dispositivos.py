"""As pilhas de camadas de cada dispositivo: `Computador` (7 camadas) e
`Roteador` (3 camadas).

É aqui — e não dentro de `camadas.py` — que a ordem das camadas mora: uma
camada não conhece as vizinhas, quem encadeia `descer()`/`subir()` é a pilha
do dispositivo (seção 4.3 da proposta técnica). E é aqui que a restrição R1
deixa de ser convenção:

    Roteador.__init__ instancia apenas L1, L2 e L3. Os objetos das camadas
    4 a 7 não existem naquele dispositivo — nem como None.

Não basta que fiquem sem uso: se não existe um objeto `CamadaTransporte` no
roteador, não há de onde um evento de roteador tirar um número de porta. As
classes usam `__slots__` justamente para fechar a última brecha — um
`roteador.l4 = CamadaTransporte()` em tempo de execução levanta
`AttributeError`, porque o atributo não existe no molde da classe.

Este módulo também resolve, a partir da topologia, tudo o que `camadas.py`
exige pronto no `Contexto` e se recusa a buscar sozinha:

- a **tabela de encaminhamento** que a L3 consulta em `ROTEIA` (R4: a L2 nunca
  a vê) — do roteador, derivada do Dijkstra de `rede.py`; do computador, as
  duas entradas (rede local /24 e rota padrão para o gateway) em que a decisão
  binária da seção 6.3 se traduz;
- o **par de endereços físicos** de cada salto, o passo análogo a ARP: o MAC
  da interface de saída e o do vizinho naquele enlace;
- o **enlace** atravessado (id e rótulo do salto), que a L1 registra.

O que este módulo **não** faz: não numera passos, não escreve descrição, não
monta `Evento` e não decide em que ordem os dispositivos agem. Cada método
devolve as ações de camada que acabaram de ocorrer, na forma de `AcaoCamada`
— o retrato completo do evento menos `passo`, `fluxo` e `descricao`, que são
de quem monta o registro (`simulador.py`, issues #28 a #33).
"""

from dataclasses import dataclass
from typing import Iterable

from camadas import (
    ENLACE_ENDERECO_ALHEIO,
    ENLACE_ERRO_CRC,
    ENLACE_OK,
    CamadaAplicacao,
    CamadaApresentacao,
    CamadaEnlace,
    CamadaFisica,
    CamadaRede,
    CamadaSessao,
    CamadaTransporte,
    Contexto,
    EntradaRota,
    par_fisico_do_h2,
    par_logico_do_h3,
)
from constantes import Acao
from evento import BlocoEvento, Estado, Fisico, Logico, PduInfo, Porta, Processo
from evento import Enlace as EnlaceEvento
from evento import Segmento as SegmentoEvento
from evento import Sentido
from pdu import PDU, Quadro
from rede import Dispositivo as DispositivoTopologia
from rede import Enlace as EnlaceTopologia
from rede import Extremo, Fluxo, InterfaceRede, Topologia

# Prefixo que casa qualquer destino: a rota padrão do computador para o seu
# gateway (seção 6.3 — "senão, próximo salto = gateway" é só a entrada menos
# específica de uma tabela de duas linhas, percorrida pela mesma consulta por
# prefixo mais longo que o roteador usa).
_ROTA_PADRAO = "0.0.0.0/0"

# Separador do rótulo de salto ("H1–R1"): travessão curto (U+2013), como no
# Anexo B e nos rótulos de enlace do topologia.json.
_TRACO = "–"


class ErroDeDispositivo(RuntimeError):
    """Falha ao operar a pilha de um dispositivo: um salto que a topologia não
    sustenta (vizinho inexistente no enlace, interface desconhecida) ou uma
    chamada fora de ordem. Sempre erro de programação ou de topologia mal
    formada — nunca comportamento de rede simulado; descarte por ausência de
    rota (C5) e por erro de verificação (C6) são `AcaoCamada`, não exceção."""


# --------------------------------------------------------------------------
# Ação de camada — o evento antes de virar Evento
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AcaoCamada:
    """Uma ação de camada já ocorrida, com tudo que o `Evento` correspondente
    (seção 7.2) precisa **menos** `passo`, `fluxo`, `descricao` e `caminho`:
    numeração global contínua, rótulo de fluxo, redação e acúmulo de enlaces
    percorridos são de quem monta o registro, que enxerga a execução inteira.

    `campos_de_evento()` devolve exatamente os campos do `Evento`; os quatro
    últimos atributos abaixo ficam de fora — são o contexto da **decisão**,
    de que `simulador.py` precisa para escrever a descrição ("via R4, custo 2"
    contra "diretamente conectada"), não campos do contrato.

    R1 se lê aqui: `porta`, `sessao`, `segmento` e `processo` só são
    preenchidos pelos métodos de `Computador`, os únicos que têm objetos de
    camada 4 a 7 de onde tirar esses valores."""

    dispositivo: str
    camada: int
    acao: Acao
    sentido: Sentido
    tamanho: int | None = None
    estado: Estado = "ok"
    secundario: bool = False
    pdu: PduInfo | None = None

    logico: Logico | None = None
    fisico: Fisico | None = None

    enlace: EnlaceEvento | None = None
    quadro: str | None = None
    bits: int | None = None

    # Contexto superior — só computadores (R1).
    porta: Porta | None = None
    sessao: str | None = None
    segmento: SegmentoEvento | None = None
    processo: Processo | None = None

    # --- contexto da decisão, para a redação da descrição (não é do Evento) ---
    rota: EntradaRota | None = None
    entrega_direta: bool | None = None
    vizinho: str | None = None        # endereço lógico do próximo salto
    vizinho_nome: str | None = None   # nome do dispositivo do próximo salto ("via R4")

    def campos_de_evento(self) -> dict:
        """Os campos do `Evento` desta ação, prontos para

            Evento(passo=n, fluxo="F1", descricao=..., caminho=...,
                   **acao.campos_de_evento())

        Nenhum campo do contrato é omitido: se algo precisa aparecer na tela e
        não está aqui, o campo entra no `Evento` — nunca é buscado no núcleo
        pela interface (seção 4.2)."""
        return {
            "dispositivo": self.dispositivo,
            "camada": self.camada,
            "acao": self.acao,
            "tamanho": self.tamanho,
            "sentido": self.sentido,
            "estado": self.estado,
            "secundario": self.secundario,
            "pdu": self.pdu,
            "logico": self.logico,
            "fisico": self.fisico,
            "enlace": self.enlace,
            "quadro": self.quadro,
            "bits": self.bits,
            "porta": self.porta,
            "sessao": self.sessao,
            "segmento": self.segmento,
            "processo": self.processo,
        }


def _retrato(unidade: PDU) -> PduInfo:
    """Cópia dos blocos da PDU no instante da ação (seção 7.1: o evento é um
    retrato imutável). Cópia, e não referência: o quadro é destruído logo
    adiante (R2) e um evento já emitido não pode mudar depois."""
    return PduInfo(
        nome=unidade.nome,
        blocos=tuple(
            BlocoEvento(rotulo=b.rotulo, tam=b.tam, tipo=b.tipo, conteudo=b.conteudo)
            for b in unidade.blocos
        ),
    )


def _par_logico(unidade: PDU) -> Logico | None:
    """O par lógico gravado no cabeçalho H3, se a unidade o carrega.

    É lido do próprio pacote, nunca de um parâmetro: o par é escrito uma única
    vez, na L3 da origem (R3), e daí em diante todo evento que o exibe o está
    lendo de onde ele realmente está. Por isso vale de `ENCAPSULA` (origem) a
    `DESENCAPSULA` (destino) — inclusive nos eventos de camada 1 e 2 dos
    roteadores, que só transportam o pacote — e não vale nos eventos de camada
    4 a 7, onde o H3 ainda não existe ou já foi removido (seção 7.2)."""
    for bloco in unidade.blocos:
        if bloco.rotulo == "H3" and isinstance(bloco.conteudo, str):
            origem, destino = par_logico_do_h3(bloco.conteudo)
            return Logico(origem=origem, destino=destino)
    return None


def _par_fisico(quadro: PDU) -> Fisico:
    """O par físico do cabeçalho H2 do quadro, na ordem do evento (origem
    antes de destino; no H2 a ordem é a da Aula 2, destino antes de origem)."""
    cabecalho = quadro.blocos[0]
    assert cabecalho.rotulo == "H2" and isinstance(cabecalho.conteudo, str), (
        "quadro sem cabeçalho H2 legível"
    )
    origem, destino = par_fisico_do_h2(cabecalho.conteudo)
    return Fisico(origem=origem, destino=destino)


# --------------------------------------------------------------------------
# Resultados dos métodos de pilha
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Vizinho:
    """A outra ponta de um salto, resolvida na topologia: quem recebe, por
    qual interface, com quais endereços. É o resultado do passo análogo a ARP
    — feito aqui, fora da camada 2, que recebe o par físico pronto (R4)."""

    dispositivo: str
    interface: str
    logico: str
    fisico: str


@dataclass(frozen=True)
class Entrega:
    """Um quadro tal como chega a **uma** das pontas do enlace.

    Num segmento de difusão o quadro chega a todas as estações (issue #10):
    `enderecado` distingue aquela a quem o H2 se dirige das demais, que vão
    descartá-lo por endereço (`IGNORA`, evento secundário — seção 7.5). Cada
    estação recebe o seu próprio objeto quadro, com o **mesmo** identificador
    (`Quadro.copia_recebida`), porque a camada 2 destrói o quadro que sobe e
    um objeto só não sobreviveria à segunda estação.

    `enlace.rotulo` é o rótulo do **salto** ("H1–R1"), não o do segmento
    ("Rede A"): é o que o Anexo B mostra na linha 008."""

    quadro: Quadro
    destinatario: str
    interface: str
    enlace: EnlaceEvento
    enderecado: bool


@dataclass(frozen=True)
class Transmissao:
    """Resultado de pôr um pacote no enlace: `ENQUADRA` + `TRANSMITE`, o quadro
    construído e as entregas que o motor deve encaminhar às pontas, a
    endereçada primeiro."""

    acoes: tuple[AcaoCamada, ...]
    quadro: Quadro
    entregas: tuple[Entrega, ...]

    @property
    def entrega_enderecada(self) -> Entrega:
        return self.entregas[0]


@dataclass(frozen=True)
class Recepcao:
    """Resultado de tirar um quadro do enlace: `RECEBE` e, conforme o desfecho
    da camada 2, `DESENQUADRA`, `DESCARTA` (verificação reprovada — C6) ou
    `IGNORA` (endereço alheio — secundário).

    `pacote` é None nos dois desfechos de descarte; `resultado` traz a
    constante de `camadas.py` (`ENLACE_OK`, `ENLACE_ERRO_CRC`,
    `ENLACE_ENDERECO_ALHEIO`) para quem precisar ramificar sem reinspecionar
    as ações."""

    acoes: tuple[AcaoCamada, ...]
    pacote: PDU | None
    resultado: str

    @property
    def aceito(self) -> bool:
        return self.resultado == ENLACE_OK


@dataclass(frozen=True)
class Encaminhamento:
    """Resultado de uma decisão de camada 3: `ROTEIA` (com `ENCAPSULA` antes,
    quando é a origem) ou `DESCARTA` por ausência de rota (C5).

    `pacote` é None só no descarte — e aí nenhuma camada superior é acionada e
    nenhum quadro é construído (seção 6.6). `vizinho` é o endereço lógico do
    próximo salto, como a camada 2 vai recebê-lo (R4)."""

    acoes: tuple[AcaoCamada, ...]
    pacote: PDU | None
    vizinho: str | None = None
    interface_saida: str | None = None
    vizinho_nome: str | None = None

    @property
    def descartado(self) -> bool:
        return self.pacote is None


@dataclass(frozen=True)
class Envio:
    """O que a metade alta da pilha da origem produziu antes de o primeiro
    pacote existir: as ações de `GERA` a `SEGMENTA` e os segmentos a empurrar,
    um a um, pela L3 (`Computador.encapsular`).

    Carrega também o endereçamento e a identificação do fluxo, para que cada
    segmento seja encapsulado com o mesmo par lógico (R3) sem que o motor
    precise guardá-lo por fora."""

    acoes: tuple[AcaoCamada, ...]
    segmentos: tuple[PDU, ...]
    logico_origem: str
    logico_destino: str
    porta: Porta
    processo: Processo
    sessao: str


# --------------------------------------------------------------------------
# A pilha baixa — comum a computador e roteador
# --------------------------------------------------------------------------


class No:
    """Metade baixa da pilha: camadas 1, 2 e 3, mais as resoluções locais que
    `camadas.py` exige prontas no `Contexto`.

    Existe para que `Roteador` seja exatamente isto e nada mais — a classe não
    tem um só atributo de camada 4 a 7, e `__slots__` impede que ganhe um
    depois. `Computador` herda esta metade e acrescenta as quatro camadas de
    cima.

    Cada operação cria o seu próprio `Contexto`: nenhum estado de fluxo é
    compartilhado entre dispositivos. É a segunda metade de R1 — um roteador
    não teria como copiar `porta`/`sessao` de um contexto alheio nem por
    engano, porque nunca vê um."""

    __slots__ = ("nome", "tipo", "_disp", "_topo", "_tabela", "l1", "l2", "l3")

    def __init__(self, dispositivo: DispositivoTopologia, topologia: Topologia) -> None:
        self.nome = dispositivo.nome
        self.tipo = dispositivo.tipo
        self._disp = dispositivo
        self._topo = topologia
        self.l1 = CamadaFisica()
        self.l2 = CamadaEnlace()
        self.l3 = CamadaRede()
        self._tabela = self._montar_tabela()

    def __repr__(self) -> str:
        camadas = " ".join(
            f"L{n}" for n in (7, 6, 5, 4, 3, 2, 1) if hasattr(self, f"l{n}")
        )
        return f"{type(self).__name__}({self.nome!r}, camadas=[{camadas}])"

    # -- topologia ---------------------------------------------------------

    @property
    def tabela_encaminhamento(self) -> tuple[EntradaRota, ...]:
        """As rotas que a L3 deste dispositivo consulta em `ROTEIA`. Só a
        camada 3 a recebe, via `Contexto` — a camada 2 não tem como alcançá-la
        (R4)."""
        return self._tabela

    def atualizar_topologia(self, topologia: Topologia) -> None:
        """Troca a topologia corrente e **recalcula** a tabela.

        É o que fecha o recálculo de rota de C4 (seção 6.1, issue #22): o motor
        derruba o enlace (`Topologia.com_enlace_ativo`) e chama isto em cada
        dispositivo; o próximo `ROTEIA` de R1 já sai por R2. Recalcular na
        troca, e não a cada pacote, deixa claro que a rota muda por um evento
        de rede, não por consulta."""
        self._disp = topologia.dispositivo(self.nome)
        self._topo = topologia
        self._tabela = self._montar_tabela()

    def _montar_tabela(self) -> tuple[EntradaRota, ...]:
        raise NotImplementedError

    def _interface(self, nome: str) -> InterfaceRede:
        for iface in self._disp.interfaces:
            if iface.nome == nome:
                return iface
        raise ErroDeDispositivo(
            f"{self.nome} não tem interface {nome!r}"
        )

    def _enlace_da_interface(self, interface: str) -> EnlaceTopologia:
        for enlace in self._topo.enlaces:
            for ponta in enlace.pontas:
                if ponta.dispositivo == self.nome and ponta.interface == interface:
                    return enlace
        raise ErroDeDispositivo(
            f"interface {interface!r} de {self.nome} não está em nenhum enlace"
        )

    def _pontas_vizinhas(self, enlace: EnlaceTopologia) -> tuple[Vizinho, ...]:
        """As outras pontas do enlace, com endereços resolvidos. Uma só num
        enlace ponto-a-ponto; N−1 num segmento de difusão."""
        vizinhos = []
        for ponta in enlace.pontas:
            if ponta.dispositivo == self.nome:
                continue
            disp = self._topo.dispositivo(ponta.dispositivo)
            iface = next(i for i in disp.interfaces if i.nome == ponta.interface)
            vizinhos.append(
                Vizinho(
                    dispositivo=disp.nome,
                    interface=iface.nome,
                    logico=iface.logico,
                    fisico=iface.fisico,
                )
            )
        return tuple(vizinhos)

    def _resolver_vizinho(self, interface_saida: str, logico: str) -> Vizinho:
        """O passo análogo a ARP: quem, no enlace da interface de saída, atende
        pelo endereço lógico `logico`.

        É feito aqui, fora das camadas, porque nem a 2 nem a 3 podem consultar
        a topologia — a camada 3 decide o próximo salto (um endereço lógico) e
        a camada 2 recebe o par de MACs já resolvido (R4)."""
        enlace = self._enlace_da_interface(interface_saida)
        for vizinho in self._pontas_vizinhas(enlace):
            if vizinho.logico == logico:
                return vizinho
        raise ErroDeDispositivo(
            f"{self.nome} não alcança {logico} pela interface {interface_saida!r} "
            f"(enlace {enlace.id}): nenhuma ponta do enlace tem esse endereço"
        )

    # -- camada 3 ----------------------------------------------------------

    def _rotear(self, pacote: PDU, sentido: Sentido) -> Encaminhamento:
        """`ROTEIA` — ou `DESCARTA`, quando a tabela não tem prefixo para o
        destino (C5). Única porta de entrada da camada 3 em trânsito: o pacote
        não é desencapsulado nem alterado, só o próximo salto é decidido.

        Roteador e computador chamam o mesmo método com a mesma camada 3; o
        que difere é a tabela que cada um monta (seções 6.2 e 6.3)."""
        ctx = Contexto(tabela_encaminhamento=list(self._tabela))
        logico = _par_logico(pacote)
        roteado = self.l3.roteia(pacote, ctx)

        if roteado is None:  # seção 6.6 — ausência de rota
            descarte = AcaoCamada(
                dispositivo=self.nome,
                camada=self.l3.numero,
                acao="DESCARTA",
                sentido=sentido,
                tamanho=pacote.tamanho(),
                estado="descartado",
                pdu=_retrato(pacote),
                logico=logico,
            )
            return Encaminhamento(acoes=(descarte,), pacote=None)

        assert ctx.vizinho is not None and ctx.interface_saida is not None
        vizinho = self._resolver_vizinho(ctx.interface_saida, ctx.vizinho)
        acao = AcaoCamada(
            dispositivo=self.nome,
            camada=self.l3.numero,
            acao="ROTEIA",
            sentido=sentido,
            tamanho=roteado.tamanho(),
            pdu=_retrato(roteado),
            logico=logico,
            rota=ctx.rota,
            entrega_direta=ctx.rota.proximo_salto is None,
            vizinho=ctx.vizinho,
            vizinho_nome=vizinho.dispositivo,
        )
        return Encaminhamento(
            acoes=(acao,),
            pacote=roteado,
            vizinho=ctx.vizinho,
            interface_saida=ctx.interface_saida,
            vizinho_nome=vizinho.dispositivo,
        )

    # -- camadas 2 e 1 -----------------------------------------------------

    def enquadrar(
        self, pacote: PDU, *, vizinho: str, interface_saida: str
    ) -> Transmissao:
        """A descida pelas camadas 2 e 1: `ENQUADRA` + `TRANSMITE`.

        `vizinho` e `interface_saida` vêm da decisão da camada 3 (o
        `Encaminhamento` devolvido por `encaminhar`/`encapsular`) — a camada 2
        os recebe como parâmetro de entrada, sem enxergar tabela alguma (R4).
        O par de MACs e o enlace do salto são resolvidos aqui e entregues
        prontos no `Contexto`.

        Devolve também a quem o quadro chega: a ponta endereçada e, num
        segmento de difusão, as demais estações, cada uma com a sua cópia
        (mesmo id — ver `Quadro.copia_recebida`)."""
        iface = self._interface(interface_saida)
        enlace = self._enlace_da_interface(interface_saida)
        if not enlace.ativo:
            # Não deveria acontecer: um enlace fora já não gera aresta, então
            # a camada 3 nunca escolhe a sua interface (C4). A guarda existe
            # para que uma decisão velha vire erro, e não um quadro fantasma
            # num enlace derrubado.
            raise ErroDeDispositivo(
                f"{self.nome} tentou transmitir pelo enlace {enlace.id}, que "
                f"está fora ({enlace.rotulo})"
            )
        destinatario = self._resolver_vizinho(interface_saida, vizinho)

        ctx = Contexto(
            vizinho=vizinho,
            interface_saida=interface_saida,
            fisico_origem=iface.fisico,
            fisico_destino=destinatario.fisico,
            enlace_id=enlace.id,
            enlace_rotulo=self._rotulo_do_salto(destinatario.dispositivo),
        )
        logico = _par_logico(pacote)
        fisico = Fisico(origem=iface.fisico, destino=destinatario.fisico)
        enlace_enderecado = EnlaceEvento(id=enlace.id, rotulo=ctx.enlace_rotulo)

        quadro = self.l2.descer(pacote, ctx)
        octetos = quadro.tamanho()
        retrato = _retrato(quadro)
        enquadra = AcaoCamada(
            dispositivo=self.nome,
            camada=self.l2.numero,
            acao="ENQUADRA",
            sentido="desce",
            tamanho=octetos,
            pdu=retrato,
            logico=logico,
            fisico=fisico,
            enlace=enlace_enderecado,
            quadro=quadro.id,
        )

        self.l1.descer(quadro, ctx)
        assert ctx.bits == octetos * 8, "a camada 1 só converte octetos em bits"
        transmite = AcaoCamada(
            dispositivo=self.nome,
            camada=self.l1.numero,
            acao="TRANSMITE",
            sentido="desce",
            tamanho=octetos,
            pdu=retrato,
            logico=logico,
            fisico=fisico,
            enlace=enlace_enderecado,
            quadro=quadro.id,
            bits=ctx.bits,
        )

        entregas = [
            Entrega(
                quadro=quadro,
                destinatario=destinatario.dispositivo,
                interface=destinatario.interface,
                enlace=enlace_enderecado,
                enderecado=True,
            )
        ]
        for outra in self._pontas_vizinhas(enlace):
            if outra.dispositivo == destinatario.dispositivo:
                continue
            entregas.append(
                Entrega(
                    quadro=quadro.copia_recebida(),
                    destinatario=outra.dispositivo,
                    interface=outra.interface,
                    enlace=EnlaceEvento(
                        id=enlace.id, rotulo=self._rotulo_do_salto(outra.dispositivo)
                    ),
                    enderecado=False,
                )
            )

        return Transmissao(
            acoes=(enquadra, transmite), quadro=quadro, entregas=tuple(entregas)
        )

    def receber(self, entrega: Entrega) -> Recepcao:
        """A subida pelas camadas 1 e 2: `RECEBE` e, conforme o desfecho da
        verificação e do endereço, `DESENQUADRA`, `DESCARTA` ou `IGNORA`.

        O MAC da interface de chegada é passado à camada 2 em
        `ctx.fisico_local`: é o que faz uma estação de difusão que não é o
        destino emitir `IGNORA` em vez de subir o pacote. Os dois desfechos de
        descarte não têm PDU nem tamanho — nada foi extraído do quadro, e é por
        isso que a linha de `DESCARTA` de C6 não traz sufixo de octetos. A
        identificação do quadro (`Q3`) fica, para a descrição nomeá-lo.

        Numa estação não endereçada, `RECEBE` e `IGNORA` saem os dois marcados
        `secundario` — ocultos por padrão no registro, que assim salta de
        "H1 TRANSMITE" direto para "R1 RECEBE" como no Anexo B, sem que o
        comportamento de difusão deixe de existir (seção 7.5)."""
        quadro = entrega.quadro
        iface = self._interface(entrega.interface)

        # Lidos antes de a camada 2 destruir o quadro (R2).
        octetos = quadro.tamanho()
        retrato = _retrato(quadro)
        identificador = quadro.id
        fisico = _par_fisico(quadro)
        logico = _par_logico(quadro)
        secundario = not entrega.enderecado

        ctx = Contexto(
            fisico_local=iface.fisico,
            enlace_id=entrega.enlace.id,
            enlace_rotulo=entrega.enlace.rotulo,
        )

        self.l1.subir(quadro, ctx)
        recebe = AcaoCamada(
            dispositivo=self.nome,
            camada=self.l1.numero,
            acao="RECEBE",
            sentido="sobe",
            tamanho=octetos,
            secundario=secundario,
            pdu=retrato,
            logico=logico,
            fisico=fisico,
            enlace=entrega.enlace,
            quadro=identificador,
            bits=ctx.bits,
        )

        pacote = self.l2.subir(quadro, ctx)
        if ctx.resultado_enlace == ENLACE_OK:
            assert pacote is not None
            desfecho = AcaoCamada(
                dispositivo=self.nome,
                camada=self.l2.numero,
                acao="DESENQUADRA",
                sentido="sobe",
                tamanho=pacote.tamanho(),
                pdu=_retrato(pacote),
                logico=logico,
                fisico=fisico,
                enlace=entrega.enlace,
                quadro=identificador,
            )
        elif ctx.resultado_enlace == ENLACE_ERRO_CRC:
            desfecho = AcaoCamada(
                dispositivo=self.nome,
                camada=self.l2.numero,
                acao="DESCARTA",
                sentido="sobe",
                estado="erro",
                secundario=secundario,
                logico=logico,
                fisico=fisico,
                enlace=entrega.enlace,
                quadro=identificador,
            )
        elif ctx.resultado_enlace == ENLACE_ENDERECO_ALHEIO:
            desfecho = AcaoCamada(
                dispositivo=self.nome,
                camada=self.l2.numero,
                acao="IGNORA",
                sentido="sobe",
                estado="descartado",
                secundario=True,
                logico=logico,
                fisico=fisico,
                enlace=entrega.enlace,
                quadro=identificador,
            )
        else:  # pragma: no cover — vocabulário fechado de `camadas.py`
            raise ErroDeDispositivo(
                f"desfecho de enlace desconhecido: {ctx.resultado_enlace!r}"
            )

        return Recepcao(
            acoes=(recebe, desfecho),
            pacote=pacote,
            resultado=ctx.resultado_enlace,
        )

    def _rotulo_do_salto(self, receptor: str) -> str:
        """O rótulo do salto como o Anexo B o escreve: "H1–R1", "R4–R3" — as
        duas pontas deste salto, não o nome do segmento. Num enlace
        ponto-a-ponto coincide com o `rotulo` do enlace na topologia; num
        segmento de difusão não (a Rede A rende "H1–R1" e "H1–H2")."""
        return f"{self.nome}{_TRACO}{receptor}"


# --------------------------------------------------------------------------
# Roteador — três camadas, e só
# --------------------------------------------------------------------------


class Roteador(No):
    """Três camadas: L1, L2 e L3. **Nenhum atributo de camada 4 a 7 existe** —
    não é que fiquem sem uso, é que não há objeto (R1).

    `__slots__ = ()` sela a garantia: como nem esta classe nem `No` declaram
    `__dict__`, um `roteador.l4 = CamadaTransporte()` em tempo de execução
    levanta `AttributeError`. Não há, em lugar nenhum do programa, um caminho
    que faça um evento de roteador ganhar `porta`, `sessao`, `segmento` ou
    `processo` — é o que T-R1 (issue #35) confere sobre o registro pronto.

    O fluxo de uma mensagem em trânsito é `receber` (L1↑ L2↑) → `encaminhar`
    (L3) → `enquadrar` (L2↓ L1↓), sem nunca tocar L4–L7."""

    __slots__ = ()

    def _montar_tabela(self) -> tuple[EntradaRota, ...]:
        """A tabela da seção 6.2, traduzida do Dijkstra de `rede.py` para o
        formato que a camada 3 consome. Uma linha por rede alcançável; rede
        sem caminho simplesmente não aparece, e é dessa ausência que nasce o
        `DESCARTA` de C5 (seção 6.6)."""
        tabela = self._topo.tabela_encaminhamento(self.nome)
        return tuple(
            EntradaRota(
                prefixo=rota.prefixo,
                interface=rota.interface_saida,
                custo=rota.custo,
                proximo_salto=rota.proximo_salto,
            )
            for rota in tabela.rotas
        )

    def encaminhar(self, pacote: PDU) -> Encaminhamento:
        """`ROTEIA` o pacote em trânsito — ou `DESCARTA`, se a tabela não tem
        prefixo para o destino (C5). Sentido `meio`: a pilha do roteador não
        desce nem sobe além da camada 3, ela dá meia-volta ali."""
        return self._rotear(pacote, sentido="meio")


# --------------------------------------------------------------------------
# Computador — as sete camadas
# --------------------------------------------------------------------------


class Computador(No):
    """As sete camadas. Acrescenta à metade baixa de `No` as camadas 4 a 7 e
    os três trechos de pilha que só um computador percorre: a descida completa
    da origem (`iniciar_envio`), o encapsulamento de cada segmento
    (`encapsular`) e a subida completa do destino (`entregar`).

    A camada 4 guarda estado de remontagem por porta de origem — é o que
    demultiplexa dois fluxos concorrentes em C3 —, então há **uma instância
    por computador**, viva entre os segmentos de C7."""

    __slots__ = ("l4", "l5", "l6", "l7")

    def __init__(
        self,
        dispositivo: DispositivoTopologia,
        topologia: Topologia,
        limite_segmento: int | None = None,
    ) -> None:
        super().__init__(dispositivo, topologia)
        # `limite_segmento` é o limite do caso em execução (`rede.limite_de
        # _segmento`). Sem ele, vale o global do arquivo — é o que mantém
        # `montar_dispositivos(topologia)` utilizável fora de uma execução.
        self.l4 = CamadaTransporte(
            limite_segmento
            if limite_segmento is not None
            else topologia.parametros.limite_segmento
        )
        self.l5 = CamadaSessao()
        self.l6 = CamadaApresentacao()
        self.l7 = CamadaAplicacao()

    # -- tabela ------------------------------------------------------------

    def _montar_tabela(self) -> tuple[EntradaRota, ...]:
        """A decisão binária da seção 6.3 escrita como tabela:

            minha rede /24  →  entrega direta (sem próximo salto)
            0.0.0.0/0       →  gateway

        A consulta por prefixo mais longo da camada 3 faz o resto: quando o
        destino é local, a /24 vence a /0 e o próximo salto é o próprio
        destino; nos demais casos só a rota padrão casa, e o pacote vai ao
        gateway. É por isso que a camada 3 não tem ramo condicional por tipo
        de dispositivo — e por isso o computador nunca descarta por conta
        própria: a /0 casa sempre (só um roteador, com tabela genuinamente
        incompleta, descobre a ausência de rota — C5)."""
        assert self._disp.gateway is not None, (
            "o parser garante 'gateway' preenchido para todo computador"
        )
        entradas = [
            EntradaRota(
                prefixo=self._topo.rede(iface.rede).prefixo,
                interface=iface.nome,
                custo=0,
                proximo_salto=None,
            )
            for iface in self._disp.interfaces
        ]
        # Por onde se fala com o próprio gateway: a mesma bifurcação da seção
        # 6.3, consultada com o gateway como destino — ele está sempre numa
        # rede local (V-09), então o ramo é o da entrega direta e a interface
        # devolvida é a da rota padrão.
        saida = self._topo.decisao_computador(self.nome, self._disp.gateway)
        entradas.append(
            EntradaRota(
                prefixo=_ROTA_PADRAO,
                interface=saida.interface_saida,
                custo=0,
                proximo_salto=self._disp.gateway,
            )
        )
        return tuple(entradas)

    # -- origem: descida completa -----------------------------------------

    def iniciar_envio(self, fluxo: Fluxo) -> Envio:
        """A descida de `GERA` a `SEGMENTA`: camadas 7, 6, 5 e 4 da origem.

        Produz um `SEGMENTA` por segmento — um só na maioria dos casos, três
        em C7 —, todos antes de o primeiro pacote existir. Os segmentos são
        devolvidos na ordem em que devem percorrer a rota (decisão D5:
        numeração de quadro contínua, um trajeto completo por segmento)."""
        destino = logico_do_extremo(self._topo, fluxo.destino)
        origem = logico_do_extremo(self._topo, fluxo.origem)
        porta = Porta(origem=fluxo.origem.porta, destino=fluxo.destino.porta)
        processo = Processo(
            origem=fluxo.origem.processo or "", destino=fluxo.destino.processo or ""
        )

        ctx = Contexto(
            mensagem=fluxo.mensagem,
            processo_origem=processo.origem,
            processo_destino=processo.destino,
            porta_origem=porta.origem,
            porta_destino=porta.destino,
            logico_origem=origem,
            logico_destino=destino,
        )

        acoes: list[AcaoCamada] = []
        unidade = self.l7.descer(PDU(nome="", blocos=[]), ctx)
        acoes.append(self._acao_alta(7, "GERA", unidade, processo=processo))

        unidade = self.l6.descer(unidade, ctx)
        acoes.append(self._acao_alta(6, "CODIFICA", unidade))

        unidade = self.l5.descer(unidade, ctx)
        sessao = ctx.sessao
        assert sessao is not None, "ABRE grava o identificador de sessão em ctx"
        acoes.append(self._acao_alta(5, "ABRE", unidade, sessao=sessao))

        segmentos = self.l4.descer(unidade, ctx)
        total = len(segmentos)
        for n, segmento in enumerate(segmentos, start=1):
            acoes.append(
                self._acao_alta(
                    4,
                    "SEGMENTA",
                    segmento,
                    porta=porta,
                    segmento=SegmentoEvento(n=n, total=total),
                    sessao=sessao,
                )
            )

        return Envio(
            acoes=tuple(acoes),
            segmentos=tuple(segmentos),
            logico_origem=origem,
            logico_destino=destino,
            porta=porta,
            processo=processo,
            sessao=sessao,
        )

    def encapsular(self, envio: Envio, segmento: PDU) -> Encaminhamento:
        """`ENCAPSULA` + `ROTEIA` para um dos segmentos de `envio`.

        O par lógico é gravado aqui, na camada 3 da origem, uma única vez por
        pacote e nunca mais alterado (R3) — os dois endereços vêm do `Envio`,
        idênticos para todos os segmentos da mesma mensagem."""
        ctx = Contexto(
            logico_origem=envio.logico_origem,
            logico_destino=envio.logico_destino,
        )
        pacote = self.l3.descer(segmento, ctx)
        encapsula = AcaoCamada(
            dispositivo=self.nome,
            camada=self.l3.numero,
            acao="ENCAPSULA",
            sentido="desce",
            tamanho=pacote.tamanho(),
            pdu=_retrato(pacote),
            logico=_par_logico(pacote),
        )
        decisao = self._rotear(pacote, sentido="desce")
        assert not decisao.descartado, (
            "o computador não descarta por conta própria: a rota padrão casa "
            "qualquer destino (seção 6.3)"
        )
        return Encaminhamento(
            acoes=(encapsula, *decisao.acoes),
            pacote=decisao.pacote,
            vizinho=decisao.vizinho,
            interface_saida=decisao.interface_saida,
            vizinho_nome=decisao.vizinho_nome,
        )

    # -- destino: subida completa -----------------------------------------

    def entregar(
        self,
        pacote: PDU,
        processo: Processo,
        *,
        demultiplexa: bool = False,
        sessao: str | None = None,
    ) -> tuple[AcaoCamada, ...]:
        """A subida de `DESENCAPSULA` a `ENTREGA`: camadas 3, 4, 5, 6 e 7 do
        destino.

        Enquanto faltar segmento, a camada 4 não entrega nada à 5 e a subida
        para em `DESENCAPSULA` — é o que faz C7 ter **uma única** linha da
        camada 4 no destino, emitida só quando o último pedaço chega, e a
        entrega à camada 5 vir depois dela.

        `demultiplexa` escolhe o rótulo dessa linha: `DEMULTIPLEXA` quando há
        mais de um fluxo concorrente chegando a este computador (C3),
        `REMONTA` no caso comum. A distinção é do caso, não do pacote — quem
        sabe que dois fluxos disputam o mesmo destino é o motor (issue #39).

        `sessao` acompanha o mesmo raciocínio: a linha `DEMULTIPLEXA` nomeia a
        sessão a que a porta de origem pertence, e nesta altura da subida a
        camada 5 ainda não agiu — o H5 continua dentro da PDU, e lê-lo aqui
        seria a camada 4 abrindo cabeçalho alheio (R5). O identificador vem de
        quem o viu nascer no `ABRE` da origem: o motor. Fora de C3 é `None` e
        a linha é `REMONTA`, que não menciona sessão.

        `processo` vem do caso: nomes de processo não trafegam em cabeçalho
        nenhum, o simulador não tem serviço de nomes."""
        ctx = Contexto()
        logico = _par_logico(pacote)

        conteudo = self.l3.subir(pacote, ctx)
        acoes = [
            AcaoCamada(
                dispositivo=self.nome,
                camada=self.l3.numero,
                acao="DESENCAPSULA",
                sentido="sobe",
                tamanho=conteudo.tamanho(),
                pdu=_retrato(conteudo),
                logico=logico,
            )
        ]

        remontada = self.l4.subir(conteudo, ctx)
        if remontada is None:
            return tuple(acoes)  # faltam segmentos — nada sobe à camada 5

        assert ctx.porta_origem is not None and ctx.porta_destino is not None
        assert ctx.segmento_total is not None
        porta = Porta(origem=ctx.porta_origem, destino=ctx.porta_destino)
        total = ctx.segmento_total
        acoes.append(
            self._acao_alta(
                4,
                "DEMULTIPLEXA" if demultiplexa else "REMONTA",
                remontada,
                sentido="sobe",
                porta=porta,
                segmento=SegmentoEvento(n=total, total=total),
                sessao=sessao if demultiplexa else None,
            )
        )

        unidade = self.l5.subir(remontada, ctx)
        acoes.append(self._acao_alta(5, "ENCERRA", unidade, sentido="sobe",
                                     sessao=ctx.sessao))
        unidade = self.l6.subir(unidade, ctx)
        acoes.append(self._acao_alta(6, "DECIFRA", unidade, sentido="sobe"))
        unidade = self.l7.subir(unidade, ctx)
        acoes.append(self._acao_alta(7, "ENTREGA", unidade, sentido="sobe",
                                     processo=processo))
        return tuple(acoes)

    def atende(self, logico: str) -> bool:
        """Se algum endereço deste computador é `logico` — o que distingue o
        destino final de uma estação qualquer do segmento."""
        return any(iface.logico == logico for iface in self._disp.interfaces)

    # -- emissão -----------------------------------------------------------

    def _acao_alta(
        self,
        camada: int,
        acao: Acao,
        unidade: PDU,
        *,
        sentido: Sentido = "desce",
        **campos,
    ) -> AcaoCamada:
        """Uma ação das camadas 4 a 7. Sem `logico` e sem `fisico`: acima da
        camada 3 o cabeçalho H3 ainda não existe (na descida) ou já foi
        removido (na subida), e o par físico só existe nas camadas 1 e 2
        (seção 7.2)."""
        return AcaoCamada(
            dispositivo=self.nome,
            camada=camada,
            acao=acao,
            sentido=sentido,
            tamanho=unidade.tamanho(),
            pdu=_retrato(unidade),
            **campos,
        )


# --------------------------------------------------------------------------
# Montagem
# --------------------------------------------------------------------------


def logico_do_extremo(topologia: Topologia, extremo: Extremo) -> str:
    """O endereço lógico de uma ponta de fluxo: o da interface do dispositivo
    nomeado, ou o endereço cru quando o caso só dá um IP — que é como C5
    aponta para uma rede que não existe (10.0.9.10)."""
    if extremo.logico is not None:
        return extremo.logico
    assert extremo.dispositivo is not None, (
        "o parser garante 'dispositivo' ou 'logico' em toda ponta de fluxo"
    )
    interfaces = topologia.dispositivo(extremo.dispositivo).interfaces
    return interfaces[0].logico


def montar_dispositivos(
    topologia: Topologia, limite_segmento: int | None = None
) -> dict[str, No]:
    """Um objeto de pilha por dispositivo da topologia, indexado pelo nome:
    `Computador` para os computadores, `Roteador` para os roteadores.

    Montar tudo de uma vez, na carga, é o que permite `atualizar_topologia`
    depois — a queda de um enlace em C4 recalcula as tabelas sem reconstruir
    as pilhas, preservando o estado de remontagem da camada 4.

    `limite_segmento` é o limite de segmentação do caso que vai rodar; só os
    computadores o usam, porque só eles têm camada 4. Omitido, vale o global
    do arquivo."""
    return {
        d.nome: (
            Computador(d, topologia, limite_segmento)
            if d.tipo == "computador"
            else Roteador(d, topologia)
        )
        for d in topologia.dispositivos
    }


def atualizar_topologia(dispositivos: Iterable[No], topologia: Topologia) -> None:
    """Propaga uma nova topologia (tipicamente `com_enlace_ativo`, C4) a todos
    os dispositivos, recalculando cada tabela de encaminhamento."""
    for no in dispositivos:
        no.atualizar_topologia(topologia)
