"""Interface gráfica: o único módulo que desenha, e o único que não conhece o núcleo.

A regra que este arquivo existe para obedecer está na seção 4.2 da proposta
técnica e vale para toda a F5/F6 (issue #47):

    `visual.py` importa **apenas** `evento.py`.

Não é estilo, é estrutura. A interface recebe uma **lista de eventos já
pronta** e navega nela por índice; nunca chama uma camada, um dispositivo ou o
roteador para descobrir o que desenhar. A simulação roda inteira antes do
primeiro desenho (issue #32), e é daí que vem a consequência prática que faz a
F6 ser simples: passo a passo, pausa, retrocesso e as três velocidades (V5)
viram operações sobre um inteiro — um índice de lista —, não sobre um relógio.

O teste do acoplamento, quando faltar informação na tela: **o campo entra no
`Evento`** (o que exige reabrir o contrato, issue #1). O dado jamais é buscado
direto no núcleo. `tests/test_acoplamento.py` cobra a regra de duas formas,
estática e em execução, e roda junto com o resto da suíte — inclusive nas PRs
seguintes de interface, que é onde o risco mora (seção 15.3, "interface
acessar camadas para desenhar").

Estado nesta issue (#48): a fronteira — `Navegador`, a navegação por índice
sobre a tupla de eventos — e o **mapa da rede** (V1): `Planta` (o desenho lido
do `topologia.json`), `EstadoDoMapa` (o que os eventos até o passo corrente
dizem sobre traços e enlaces) e `MapaDaRede` (o desenho em si). As pilhas, a
PDU e os endereços entram em V2–V4 (issues #49 a #51); os controles, o
registro rolável e a alternância OSI/TCP-IP em V5–V7 (#53 a #56).

Duas coisas que o mapa deixa explícitas, e valem para o resto da F5:

- **tkinter não é importado aqui.** `MapaDaRede` recebe a tela já pronta e só
  chama métodos de `Canvas` (`create_line`, `create_text`, `delete`). Isso não
  é preciosismo: é o que mantém `import visual` sem efeito de tela, como
  `test_acoplamento.test_importar_visual_nao_abre_janela` cobra, e é o que
  permite desenhar contra uma tela de mentira nos testes, sem abrir janela;
- **o `topologia.json` é lido, não o núcleo.** A seção 5.4 é explícita: as
  coordenadas de cada dispositivo vêm do arquivo, e a interface as lê e ajusta
  à janela. `json` é biblioteca padrão, e ler um arquivo de dados não é
  conhecer `rede.py` — o que a regra proíbe é perguntar ao motor, não abrir o
  mesmo arquivo que o usuário edita. Sem isso, trocar a topologia deixaria o
  mapa sem onde desenhar e a promessa da seção 5.5 seria falsa.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from evento import Evento, Intervencao


class Navegador:
    """Uma tupla de eventos e um índice sobre ela. Nada mais.

    É a tradução literal da regra de acoplamento: tudo o que a tela precisa
    saber está no `Evento` sob o índice corrente, e mudar de passo é mudar um
    inteiro. Por não depender de tkinter, o controle de execução inteiro é
    testável sem abrir janela — a mesma exigência que o T-SEM-TELA (issue #32)
    faz do motor.

    Os limites **saturam** em vez de estourar: `proximo()` no último evento
    devolve o último evento de novo. Um botão mantido pressionado no fim do
    registro não é um erro de programa, é um botão que deveria estar
    desabilitado — e `no_fim` / `no_inicio` existem justamente para a tela
    saber disso. `ir_para()`, ao contrário, recusa índice fora da faixa: ali o
    valor veio de código, não do dedo do usuário.
    """

    def __init__(self, eventos: Sequence[Evento]):
        if not eventos:
            raise ValueError("registro vazio: não há evento para navegar")
        self._eventos: tuple[Evento, ...] = tuple(eventos)
        self._indice = 0

    # — leitura ————————————————————————————————————————————————————————

    @property
    def eventos(self) -> tuple[Evento, ...]:
        """O registro completo, imutável, como o motor o entregou."""
        return self._eventos

    @property
    def total(self) -> int:
        return len(self._eventos)

    @property
    def indice(self) -> int:
        """Posição corrente, de 0 a `total - 1`.

        Cuidado com a diferença para `Evento.passo`, que conta de 1: no
        registro sem secundários o passo N mora no índice N-1 (garantido por
        `test_sem_interface.test_passos_sao_contiguos_de_1_a_n`), mas com os
        descartes visíveis (#56) os secundários repetem o passo do principal
        anterior e a correspondência se perde. Quem navega é o índice.
        """
        return self._indice

    @property
    def atual(self) -> Evento:
        return self._eventos[self._indice]

    @property
    def no_inicio(self) -> bool:
        return self._indice == 0

    @property
    def no_fim(self) -> bool:
        return self._indice == self.total - 1

    def ate_agora(self) -> tuple[Evento, ...]:
        """Do primeiro evento ao corrente, inclusive — o que o registro na tela
        (V6) mostra e o que o mapa (V1) usa para acumular o caminho."""
        return self._eventos[: self._indice + 1]

    # — navegação ——————————————————————————————————————————————————————

    def ir_para(self, indice: int) -> Evento:
        if not 0 <= indice < self.total:
            raise IndexError(
                f"índice {indice} fora do registro (0 a {self.total - 1})"
            )
        self._indice = indice
        return self.atual

    def proximo(self) -> Evento:
        if not self.no_fim:
            self._indice += 1
        return self.atual

    def anterior(self) -> Evento:
        if not self.no_inicio:
            self._indice -= 1
        return self.atual

    def primeiro(self) -> Evento:
        return self.ir_para(0)

    def ultimo(self) -> Evento:
        return self.ir_para(self.total - 1)


# ==========================================================================
# V1 — mapa da rede (issue #48)
# ==========================================================================
#
# Três peças, deliberadamente separadas, porque só a última precisa de tela:
#
#   `Planta`        — o que a rede é: nós, redes locais, enlaces, coordenadas.
#                     Vem do `topologia.json` (seção 5.4) e não muda ao navegar.
#   `EstadoDoMapa`  — o que os eventos até o passo corrente dizem: que enlaces
#                     já foram atravessados, qual está em uso agora, quais
#                     caíram. Vem só do `Evento`, e muda a cada passo.
#   `MapaDaRede`    — o desenho de um sobre o outro.
#
# A divisão é o que torna o requisito testável sem abrir janela: as duas
# primeiras são dados puros, e a terceira desenha em qualquer objeto que
# responda como um `Canvas` (ver `tests/test_mapa.py`).


# — paleta e medidas (seções 9.3 e 5.4) ——————————————————————————————————
#
# Nenhuma informação depende só de cor (issue #52), e no mapa isso tem dois
# lugares concretos: o caminho percorrido é verde **e** três vezes mais grosso
# que um enlace ocioso; o enlace fora do ar é cinza, tracejado **e** marcado
# com um X. Quem enxergar a tela em tons de cinza continua lendo as duas
# coisas.

COR_FUNDO = "#f7f8fa"
COR_REDE_LOCAL = "#e6edf4"
COR_BORDA_REDE = "#c3cedb"
COR_ROTULO_REDE = "#63717f"
COR_NO = "#ffffff"
COR_BORDA_NO = "#39434f"
COR_TEXTO = "#1d2530"
COR_ENLACE = "#8a94a0"
COR_ROTULO = "#69737f"
COR_CAMINHO = "#1f9d55"
COR_FORA = "#98a1ab"
COR_ERRO = "#c62828"

# O segundo canal do vermelho, e o único que sobrevive a uma captura em preto
# e branco: todo estado de descarte ou erro também desenha este símbolo, com
# esta etiqueta, na região em que aconteceu (issue #52).
ETIQUETA_ERRO = "erro"
SIMBOLO_ERRO = "✕"

LARGURA_ENLACE = 2
LARGURA_CAMINHO = 6
TRACEJADO_FORA = (7, 5)

# Medidas em coordenadas da topologia — a escala converte todas de uma vez.
LARGURA_COMPUTADOR = 52.0
ALTURA_COMPUTADOR = 34.0
RAIO_ROTEADOR = 20.0
RAIO_CUSTO = 11.0
RAIO_MARCADOR = 7.0
FOLGA_REDE = 34.0
BRACO_DO_X = 8.0


class ErroDePlanta(ValueError):
    """Topologia que existe mas não dá para desenhar.

    Separada de um `KeyError` cru de propósito: quem trocar o `topologia.json`
    (seção 5.5) e esquecer o `posicao` de um dispositivo precisa ler o que
    falta e em qual dispositivo, não um rastro de pilha."""


@dataclass(frozen=True)
class Ponto:
    x: float
    y: float


@dataclass(frozen=True)
class NoDaPlanta:
    """Um dispositivo como o mapa o vê: nome, forma e onde fica.

    `tipo` decide a forma — retângulo para computador, círculo para roteador
    (Anexo C). É a única distinção que o mapa faz entre os dois: quantas
    camadas cada um tem é assunto das pilhas (V2), e o mapa não pergunta."""

    nome: str
    tipo: str
    posicao: Ponto

    @property
    def roteador(self) -> bool:
        return self.tipo == "roteador"


@dataclass(frozen=True)
class RedeDaPlanta:
    id: str
    rotulo: str
    prefixo: str

    @property
    def legenda(self) -> str:
        """`Rede A 10.0.1.0/24` — o rótulo do Anexo C, montado do arquivo."""
        return f"{self.rotulo} {self.prefixo}".strip()


@dataclass(frozen=True)
class PontaDaPlanta:
    dispositivo: str
    interface: str


@dataclass(frozen=True)
class EnlaceDaPlanta:
    id: str
    tipo: str
    rotulo: str
    custo: int
    rede: str
    pontas: tuple[PontaDaPlanta, ...]

    @property
    def difusao(self) -> bool:
        return self.tipo == "difusao"


class Planta:
    """A topologia do ponto de vista de quem desenha.

    Carregada do `topologia.json` e congelada: navegar pelos eventos não a
    altera. Guarda só o que o mapa usa — nome, tipo, coordenada, pontas,
    custo — e ignora endereços, máscaras, parâmetros e casos, que são assunto
    das outras regiões da tela ou do motor.

    As redes **locais** (as três sombreadas do Anexo C) não estão marcadas no
    arquivo com bandeira nenhuma: são as que têm segmento de difusão, que a
    seção 5.1 já define como o segmento onde várias estações compartilham o
    meio. Deduzir em vez de listar é o que faz o sombreado continuar certo numa
    topologia trocada — o ponto inteiro da seção 5.5."""

    def __init__(
        self,
        nos: Iterable[NoDaPlanta],
        redes: Iterable[RedeDaPlanta],
        enlaces: Iterable[EnlaceDaPlanta],
    ):
        self.nos: tuple[NoDaPlanta, ...] = tuple(nos)
        self.redes: tuple[RedeDaPlanta, ...] = tuple(redes)
        self.enlaces: tuple[EnlaceDaPlanta, ...] = tuple(enlaces)
        if not self.nos:
            raise ErroDePlanta("topologia sem dispositivos: não há o que desenhar")
        self._por_nome = {no.nome: no for no in self.nos}
        self._por_id_de_rede = {rede.id: rede for rede in self.redes}
        self._por_id_de_enlace = {enlace.id: enlace for enlace in self.enlaces}

    # — carga ——————————————————————————————————————————————————————————

    @classmethod
    def de_dados(cls, dados: dict) -> "Planta":
        """A planta a partir do dicionário já lido do arquivo."""
        return cls(
            nos=[_no_da_planta(bruto) for bruto in dados.get("dispositivos", [])],
            redes=[
                RedeDaPlanta(
                    id=bruta.get("id", ""),
                    rotulo=bruta.get("rotulo", bruta.get("id", "")),
                    prefixo=bruta.get("prefixo", ""),
                )
                for bruta in dados.get("redes", [])
            ],
            enlaces=[_enlace_da_planta(bruto) for bruto in dados.get("enlaces", [])],
        )

    # — consulta ———————————————————————————————————————————————————————

    def no(self, nome: str) -> NoDaPlanta:
        try:
            return self._por_nome[nome]
        except KeyError:
            raise ErroDePlanta(
                f"dispositivo {nome!r} não está na topologia"
            ) from None

    def rede(self, identificador: str) -> RedeDaPlanta:
        try:
            return self._por_id_de_rede[identificador]
        except KeyError:
            raise ErroDePlanta(
                f"rede {identificador!r} não está na topologia"
            ) from None

    def enlace(self, identificador: str) -> EnlaceDaPlanta:
        try:
            return self._por_id_de_enlace[identificador]
        except KeyError:
            raise ErroDePlanta(
                f"enlace {identificador!r} não está na topologia"
            ) from None

    def redes_locais(self) -> tuple[RedeDaPlanta, ...]:
        """As redes com segmento de difusão — as sombreadas ao fundo."""
        com_difusao = [
            enlace.rede for enlace in self.enlaces if enlace.difusao and enlace.rede
        ]
        return tuple(
            self.rede(identificador)
            for identificador in dict.fromkeys(com_difusao)
            if identificador in self._por_id_de_rede
        )

    def dispositivos_da_rede(self, identificador: str) -> tuple[str, ...]:
        """Quem o sombreado daquela rede tem de abraçar."""
        nomes: list[str] = []
        for enlace in self.enlaces:
            if enlace.rede != identificador:
                continue
            for ponta in enlace.pontas:
                if ponta.dispositivo not in nomes:
                    nomes.append(ponta.dispositivo)
        return tuple(nomes)

    def centro(self, enlace: EnlaceDaPlanta) -> Ponto:
        """O ponto de encontro do enlace.

        Num enlace de duas pontas é o meio da reta, as duas pernas somadas dão
        a linha inteira, e é ali que o círculo de custo fica. Num segmento de
        difusão de três pontas é o baricentro, e o enlace vira uma estrela:
        cada estação puxa uma perna até o meio compartilhado, que é o que o
        segmento de fato é (seção 5.1). A outra leitura possível — uma linha
        para cada par de pontas — encheria a Rede A de traços que ninguém
        percorre, e o destaque do caminho perderia o sentido."""
        pontos = [self.no(ponta.dispositivo).posicao for ponta in enlace.pontas]
        return Ponto(
            sum(ponto.x for ponto in pontos) / len(pontos),
            sum(ponto.y for ponto in pontos) / len(pontos),
        )

    def moldura(self) -> tuple[float, float, float, float]:
        """O retângulo que contém todos os dispositivos, em coordenadas do
        arquivo. É o que a escala encaixa na janela."""
        xs = [no.posicao.x for no in self.nos]
        ys = [no.posicao.y for no in self.nos]
        return min(xs), min(ys), max(xs), max(ys)


def _no_da_planta(bruto: dict) -> NoDaPlanta:
    nome = bruto.get("nome", "?")
    posicao = bruto.get("posicao")
    if not isinstance(posicao, dict) or "x" not in posicao or "y" not in posicao:
        raise ErroDePlanta(
            f"dispositivo {nome!r} sem `posicao` com `x` e `y`: sem ela o mapa "
            "não tem onde desenhá-lo (seção 5.4)"
        )
    return NoDaPlanta(
        nome=nome,
        tipo=bruto.get("tipo", "computador"),
        posicao=Ponto(float(posicao["x"]), float(posicao["y"])),
    )


def _enlace_da_planta(bruto: dict) -> EnlaceDaPlanta:
    return EnlaceDaPlanta(
        id=bruto.get("id", "?"),
        tipo=bruto.get("tipo", "ponto-a-ponto"),
        rotulo=bruto.get("rotulo", bruto.get("id", "")),
        custo=int(bruto.get("custo", 0)),
        rede=bruto.get("rede", ""),
        pontas=tuple(
            PontaDaPlanta(
                dispositivo=ponta.get("dispositivo", "?"),
                interface=ponta.get("interface", ""),
            )
            for ponta in bruto.get("pontas", [])
        ),
    )


def carregar_planta(caminho: str | Path) -> Planta:
    """Lê o `topologia.json` do caminho dado e devolve a planta.

    Quem resolve o caminho é quem abre a janela, não este módulo: a seção 5.8
    manda que a localização do arquivo tenha **uma** implementação, e ela mora
    em `rede.pasta_base()`, que a interface não pode importar. Receber o
    caminho pronto resolve o impasse sem duplicar a regra nem furar o
    acoplamento."""
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroDePlanta(f"topologia não encontrada em {caminho}") from None
    except json.JSONDecodeError as erro:
        raise ErroDePlanta(f"topologia ilegível ({caminho}): {erro}") from None
    return Planta.de_dados(dados)


# — o que os eventos dizem sobre o mapa ————————————————————————————————


@dataclass(frozen=True)
class EstadoDoMapa:
    """O retrato do mapa no passo corrente, extraído **só** de eventos.

    Nenhum campo aqui é perguntado ao núcleo: `caminho`, `enlace`, `camada`,
    `dispositivo`, `secundario` e `estado` já estão no contrato (seção 7.2), e
    é deles que sai cada traço da tela. O `ENLACE_FORA` passou a trazer o
    `enlace` preenchido por causa desta classe (issue #48): sem ele, saber qual
    traço tracejar exigiria garimpar o rótulo dentro da descrição — que é
    exatamente o acoplamento que a seção 4.2 proíbe.

    `pernas` é o campo que merece explicação. O `caminho` do contrato acumula
    **enlaces**, e num segmento de difusão isso é grosso demais: dizer que a
    Rede A foi percorrida acenderia também o traço de H2, que não transmitiu
    nada. A perna — o par (enlace, dispositivo) — vem dos eventos de camada 1,
    os únicos em que bits de fato atravessam o meio: quem transmitiu acende a
    sua perna, quem recebeu acende a dele, e o caminho aparece avançando meio
    enlace por vez, que é o que o passo 8 de C2 mostra (H1 já transmitiu, R1
    ainda não recebeu). Eventos secundários ficam de fora: a estação que
    descarta por endereço (`IGNORA`) ouviu o quadro, não o encaminhou."""

    percorridos: frozenset[str]
    pernas: frozenset[tuple[str, str]]
    em_curso: str | None
    fora: frozenset[str]
    estado: str

    @classmethod
    def ate(cls, eventos: Sequence[Evento]) -> "EstadoDoMapa":
        """O estado acumulado do primeiro evento ao corrente.

        Recebe o que `Navegador.ate_agora()` devolve. Acumular a cada desenho,
        em vez de guardar estado entre passos, é o que faz o retrocesso (V5)
        funcionar de graça: voltar um passo é desenhar de novo com uma fatia
        menor, e não desfazer nada."""
        if not eventos:
            raise ValueError("sem eventos: o mapa não tem passo para retratar")
        pernas = {
            (evento.enlace.id, evento.dispositivo)
            for evento in eventos
            if evento.enlace is not None
            and evento.camada == 1
            and not evento.secundario
        }
        percorridos = {identificador for identificador, _ in pernas}
        percorridos.update(
            identificador for evento in eventos for identificador in evento.caminho
        )
        fora = {
            evento.enlace.id
            for evento in eventos
            if evento.acao == "ENLACE_FORA" and evento.enlace is not None
        }
        atual = eventos[-1]
        return cls(
            percorridos=frozenset(percorridos),
            pernas=frozenset(pernas),
            em_curso=atual.enlace.id if atual.enlace is not None else None,
            fora=frozenset(fora),
            estado=atual.estado,
        )

    def perna_acesa(self, enlace: str, dispositivo: str) -> bool:
        """A perna acende quando aquele dispositivo transmitiu ou recebeu por
        ali, ou quando o enlace já foi inteiro percorrido — um enlace que
        consta do `caminho` sem evento de camada 1 na fatia (o que acontece ao
        saltar direto para um passo adiantado) acende por completo."""
        return (enlace, dispositivo) in self.pernas or (
            enlace in self.percorridos
            and not any(identificador == enlace for identificador, _ in self.pernas)
        )


# — encaixe na janela (seção 5.4: "ajusta a escala ao tamanho da janela") ——


@dataclass(frozen=True)
class Escala:
    """A conversão entre as coordenadas do arquivo e as pixels da tela.

    Existe porque o `posicao` do `topologia.json` é do autor da topologia, e o
    tamanho da janela é do usuário: a seção 5.4 pede que a interface **ajuste**
    um ao outro, não que exija que coincidam. O fator é único para os dois
    eixos — esticar x e y de forma diferente entortaria os círculos dos
    roteadores — e serve também para as medidas (`medir`), de modo que um nó
    não fique do tamanho de um botão numa janela pequena."""

    fator: float
    dx: float
    dy: float

    FATOR_MINIMO = 0.35
    FATOR_MAXIMO = 2.5

    @classmethod
    def ajustar(
        cls, planta: Planta, largura: float, altura: float, margem: float = 52.0
    ) -> "Escala":
        x0, y0, x1, y1 = planta.moldura()
        util_x = max(largura - 2 * margem, 1.0)
        util_y = max(altura - 2 * margem, 1.0)
        largura_planta = x1 - x0
        altura_planta = y1 - y0
        candidatos = [cls.FATOR_MAXIMO]
        if largura_planta > 0:
            candidatos.append(util_x / largura_planta)
        if altura_planta > 0:
            candidatos.append(util_y / altura_planta)
        fator = max(min(candidatos), cls.FATOR_MINIMO)
        # Centraliza o que sobrou: a planta de referência é mais larga que
        # alta, e sem isto ela encostaria no canto superior esquerdo.
        sobra_x = largura - largura_planta * fator
        sobra_y = altura - altura_planta * fator
        return cls(
            fator=fator,
            dx=sobra_x / 2 - x0 * fator,
            dy=sobra_y / 2 - y0 * fator,
        )

    def converter(self, ponto: Ponto) -> tuple[float, float]:
        return ponto.x * self.fator + self.dx, ponto.y * self.fator + self.dy

    def medir(self, valor: float) -> float:
        return valor * self.fator

    def fonte(self, tamanho: int) -> tuple[str, int]:
        """Tamanho de fonte acompanhando a escala, com piso de legibilidade:
        texto que encolhe sem limite deixa de ser informação."""
        return ("TkDefaultFont", max(int(round(tamanho * self.fator)), 7))


# — o desenho ——————————————————————————————————————————————————————————

# Tudo o que o mapa cria leva esta etiqueta, e é por ela que o desenho
# anterior é apagado antes do próximo. Apagar por etiqueta em vez de limpar a
# tela inteira é o que permitirá às regiões seguintes (V2 a V4) dividirem a
# mesma tela sem uma apagar o desenho da outra.
ETIQUETA = "mapa"


class MapaDaRede:
    """O mapa da rede (V1) desenhado sobre uma tela de `Canvas`.

    A tela chega **pronta**, de fora: este módulo não cria janela nem importa
    tkinter (ver o cabeçalho do arquivo). A consequência boa aparece nos
    testes, que desenham o mapa inteiro contra uma tela de mentira que só
    guarda o que foi pedido — o requisito V1 vira verificável sem display,
    como a seção 13.1 exige do resto do programa.

    Desenhar é sempre **do zero**: `desenhar()` apaga o que havia e refaz.
    Guardar itens e mexer nas coordenadas seria mais rápido e traria de volta o
    problema que a arquitetura inteira evita — um estado de tela que pode
    divergir do registro. Com nove nós e sete enlaces, refazer é instantâneo, e
    o retrocesso (V5) sai sem nenhum código a mais."""

    def __init__(self, tela, planta: Planta, *, margem: float = 52.0):
        self.tela = tela
        self.planta = planta
        self.margem = margem

    # — API ————————————————————————————————————————————————————————————

    def desenhar(
        self,
        estado: EstadoDoMapa,
        largura: float | None = None,
        altura: float | None = None,
    ) -> Escala:
        """Redesenha o mapa no estado dado e devolve a escala usada.

        `largura`/`altura` existem para o teste e para o redimensionamento:
        quando não vêm, são perguntadas à própria tela."""
        largura = float(largura if largura is not None else self.tela.winfo_width())
        altura = float(altura if altura is not None else self.tela.winfo_height())
        escala = Escala.ajustar(self.planta, largura, altura, self.margem)

        self.tela.delete(ETIQUETA)
        self.tela.create_rectangle(
            0, 0, largura, altura, fill=COR_FUNDO, outline="", tags=(ETIQUETA, "fundo")
        )
        for rede in self.planta.redes_locais():
            self._desenhar_rede(rede, escala)
        for enlace in self.planta.enlaces:
            self._desenhar_enlace(enlace, estado, escala)
        for no in self.planta.nos:
            self._desenhar_no(no, escala)
        self._desenhar_marcador(estado, escala)
        return escala

    # — redes locais ———————————————————————————————————————————————————

    def _desenhar_rede(self, rede: RedeDaPlanta, escala: Escala) -> None:
        """A área sombreada ao fundo, com o prefixo por rótulo.

        O retângulo é o que contém os dispositivos da rede, com folga — é o
        agrupamento visual que o Anexo C pede ("H1+H2+R1", "H3+R2",
        "H4+H5+R3") e que nasce das pontas dos enlaces, não de uma lista
        escrita à mão."""
        nomes = self.planta.dispositivos_da_rede(rede.id)
        if not nomes:
            return
        pontos = [self.planta.no(nome).posicao for nome in nomes]
        folga = escala.medir(FOLGA_REDE)
        xs = [escala.converter(ponto)[0] for ponto in pontos]
        ys = [escala.converter(ponto)[1] for ponto in pontos]
        x0, y0 = min(xs) - folga, min(ys) - folga
        x1, y1 = max(xs) + folga, max(ys) + folga
        self.tela.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=COR_REDE_LOCAL,
            outline=COR_BORDA_REDE,
            tags=(ETIQUETA, "rede", f"rede:{rede.id}"),
        )
        # O rótulo vai na borda **de baixo**: é pela de cima que os enlaces
        # entram na rede, e ali ele disputaria espaço com os rótulos de
        # interface — na topologia de referência, o "Rede B 10.0.2.0/24" cai
        # exatamente sobre o "e0" de R2.
        self.tela.create_text(
            x0 + escala.medir(6),
            y1 - escala.medir(4),
            text=rede.legenda,
            anchor="sw",
            fill=COR_ROTULO_REDE,
            font=escala.fonte(9),
            tags=(ETIQUETA, "rede", f"rede:{rede.id}"),
        )

    # — enlaces ————————————————————————————————————————————————————————

    def _desenhar_enlace(
        self, enlace: EnlaceDaPlanta, estado: EstadoDoMapa, escala: Escala
    ) -> None:
        centro = escala.converter(self.planta.centro(enlace))
        fora = enlace.id in estado.fora
        # Duas passagens pelas pontas, e não uma: os traços primeiro, os
        # rótulos depois. Numa passagem só, a linha da segunda ponta passaria
        # por cima do rótulo de interface da primeira — o `eth0` de H1 some
        # debaixo do traço grosso do caminho no passo 8 de C2.
        extremos: list[tuple[tuple[float, float], PontaDaPlanta]] = []
        for ponta in enlace.pontas:
            no = self.planta.no(ponta.dispositivo)
            inicio = self._borda(no, self.planta.centro(enlace), escala)
            extremos.append((inicio, ponta))
            acesa = not fora and estado.perna_acesa(enlace.id, no.nome)
            # `dash` só entra quando há tracejado: o `Canvas` recusa `None`, e
            # um enlace no ar tem de sair com o traço contínuo de fábrica.
            tracejado = {"dash": TRACEJADO_FORA} if fora else {}
            self.tela.create_line(
                inicio[0],
                inicio[1],
                centro[0],
                centro[1],
                fill=COR_FORA if fora else (COR_CAMINHO if acesa else COR_ENLACE),
                width=LARGURA_CAMINHO if acesa else LARGURA_ENLACE,
                tags=(
                    ETIQUETA,
                    "enlace",
                    f"enlace:{enlace.id}",
                    "caminho" if acesa else ("fora" if fora else "ocioso"),
                ),
                **tracejado,
            )
        for inicio, ponta in extremos:
            self._rotular_interface(inicio, centro, ponta, escala, enlace.id)
        if not enlace.difusao:
            self._desenhar_custo(enlace, centro, fora, escala)
        if fora:
            self._desenhar_x(centro, escala, enlace.id)

    def _rotular_interface(
        self,
        inicio: tuple[float, float],
        centro: tuple[float, float],
        ponta: PontaDaPlanta,
        escala: Escala,
        enlace: str,
    ) -> None:
        """O nome da interface junto da ponta a que pertence (`e0`, `eth0`).

        Fica na extremidade do dispositivo, e não no meio do traço, porque a
        interface é do dispositivo: é ela que a linha 011 do Anexo B nomeia ao
        dizer "interface e1". No meio do enlace o rótulo pertenceria aos dois,
        que é justamente o que não é verdade."""
        dx, dy = centro[0] - inicio[0], centro[1] - inicio[1]
        distancia = max((dx * dx + dy * dy) ** 0.5, 1e-9)
        avanco = min(escala.medir(16), distancia * 0.45)
        px, py = dx / distancia, dy / distancia
        self.tela.create_text(
            inicio[0] + px * avanco - py * escala.medir(11),
            inicio[1] + py * avanco + px * escala.medir(11),
            text=ponta.interface,
            fill=COR_ROTULO,
            font=escala.fonte(8),
            tags=(ETIQUETA, "interface", f"enlace:{enlace}"),
        )

    def _desenhar_custo(
        self,
        enlace: EnlaceDaPlanta,
        centro: tuple[float, float],
        fora: bool,
        escala: Escala,
    ) -> None:
        """O custo num pequeno círculo no meio do enlace (Anexo C).

        Só nos enlaces ponto-a-ponto: num segmento de difusão o custo é 0 por
        decisão da seção 5.2 — dentro da mesma rede não há salto a pagar — e um
        círculo com 0 no meio da Rede A sugeriria uma rota que não existe. Lá o
        rótulo que interessa é o da rede, que o sombreado já escreve."""
        raio = escala.medir(RAIO_CUSTO)
        self.tela.create_oval(
            centro[0] - raio,
            centro[1] - raio,
            centro[0] + raio,
            centro[1] + raio,
            fill=COR_FUNDO,
            outline=COR_FORA if fora else COR_ENLACE,
            tags=(ETIQUETA, "custo", f"enlace:{enlace.id}"),
        )
        self.tela.create_text(
            centro[0],
            centro[1],
            text=str(enlace.custo),
            fill=COR_FORA if fora else COR_TEXTO,
            font=escala.fonte(9),
            tags=(ETIQUETA, "custo", f"enlace:{enlace.id}"),
        )

    def _desenhar_x(
        self, centro: tuple[float, float], escala: Escala, enlace: str
    ) -> None:
        """O X do enlace fora do ar — a redundância que o tracejado sozinho não
        daria (seção 9.3 e issue #52)."""
        braco = escala.medir(BRACO_DO_X)
        for sinal in (1, -1):
            self.tela.create_line(
                centro[0] - braco,
                centro[1] - braco * sinal,
                centro[0] + braco,
                centro[1] + braco * sinal,
                fill=COR_FORA,
                width=LARGURA_ENLACE,
                tags=(ETIQUETA, "fora", "x", f"enlace:{enlace}"),
            )

    # — nós ————————————————————————————————————————————————————————————

    def _desenhar_no(self, no: NoDaPlanta, escala: Escala) -> None:
        """Retângulo para computador, círculo para roteador (Anexo C)."""
        x, y = escala.converter(no.posicao)
        etiquetas = (ETIQUETA, "no", f"no:{no.nome}", no.tipo)
        if no.roteador:
            raio = escala.medir(RAIO_ROTEADOR)
            self.tela.create_oval(
                x - raio,
                y - raio,
                x + raio,
                y + raio,
                fill=COR_NO,
                outline=COR_BORDA_NO,
                width=2,
                tags=etiquetas,
            )
        else:
            meia_largura = escala.medir(LARGURA_COMPUTADOR) / 2
            meia_altura = escala.medir(ALTURA_COMPUTADOR) / 2
            self.tela.create_rectangle(
                x - meia_largura,
                y - meia_altura,
                x + meia_largura,
                y + meia_altura,
                fill=COR_NO,
                outline=COR_BORDA_NO,
                width=2,
                tags=etiquetas,
            )
        self.tela.create_text(
            x,
            y,
            text=no.nome,
            fill=COR_TEXTO,
            font=escala.fonte(10),
            tags=etiquetas,
        )

    def _borda(
        self, no: NoDaPlanta, alvo: Ponto, escala: Escala
    ) -> tuple[float, float]:
        """Onde o traço encosta no dispositivo, indo na direção de `alvo`.

        Sem isto a linha entraria por baixo do nó e sairia do outro lado, e o
        rótulo de interface cairia dentro da caixa. O cálculo é o da forma:
        raio no círculo do roteador, lado mais próximo no retângulo do
        computador."""
        origem = no.posicao
        dx, dy = alvo.x - origem.x, alvo.y - origem.y
        distancia = (dx * dx + dy * dy) ** 0.5
        x, y = escala.converter(origem)
        if distancia < 1e-9:
            return x, y
        if no.roteador:
            recuo = RAIO_ROTEADOR
        else:
            meia_largura = LARGURA_COMPUTADOR / 2
            meia_altura = ALTURA_COMPUTADOR / 2
            escalas = []
            if abs(dx) > 1e-9:
                escalas.append(meia_largura / abs(dx))
            if abs(dy) > 1e-9:
                escalas.append(meia_altura / abs(dy))
            recuo = min(escalas) * distancia
        proporcao = min(recuo / distancia, 1.0)
        return escala.converter(
            Ponto(origem.x + dx * proporcao, origem.y + dy * proporcao)
        )

    # — marcador de posição ————————————————————————————————————————————

    def _desenhar_marcador(self, estado: EstadoDoMapa, escala: Escala) -> None:
        """Onde a mensagem está agora: um disco sobre o enlace do passo
        corrente (Anexo C, região 2).

        Vermelho quando o passo não terminou bem — o `DESCARTA` da camada 2 em
        C6 acontece **sobre** um enlace, e é ali que o leitor precisa ver o
        percurso parar. Cor não é o único sinal: o disco vermelho também ganha
        contorno, e o registro logo abaixo diz por extenso o que houve."""
        if estado.em_curso is None or estado.em_curso in estado.fora:
            return
        centro = escala.converter(self.planta.centro(self.planta.enlace(estado.em_curso)))
        raio = escala.medir(RAIO_MARCADOR)
        problema = estado.estado != "ok"
        self.tela.create_oval(
            centro[0] - raio,
            centro[1] - raio,
            centro[0] + raio,
            centro[1] + raio,
            fill=COR_ERRO if problema else COR_CAMINHO,
            outline=COR_BORDA_NO if problema else COR_NO,
            width=2,
            tags=(ETIQUETA, "marcador", f"enlace:{estado.em_curso}"),
        )
        if problema:
            # Cor e contorno não bastam: o disco precisa dizer que é um
            # problema para quem não distingue o vermelho do verde, que é
            # justamente o par de cores em jogo aqui (issue #52).
            self.tela.create_text(
                centro[0],
                centro[1],
                text=SIMBOLO_ERRO,
                fill=COR_NO,
                font=("TkDefaultFont", max(int(round(raio)), 7), "bold"),
                tags=(ETIQUETA, ETIQUETA_ERRO, "marcador"),
            )


# ==========================================================================
# V2 — as pilhas de camadas por dispositivo (issue #49)
# ==========================================================================
#
# A região 3 do layout (seção 9.1). O que ela existe para mostrar é a
# restrição R1: o roteador não tem as camadas 4 a 7, e isso precisa ser
# visível sem legenda nenhuma. Por isso as pilhas são alinhadas **pela base**
# — o buraco aparece em cima, onde o olho vai.

COR_CAMADA_ATIVA = "#1f6feb"
COR_CAMADA_INATIVA = "#e8ecf1"
COR_TEXTO_ATIVO = "#ffffff"
COR_DECISAO = "#e07b1a"

LARGURA_CAIXA_INATIVA = 1
LARGURA_CAIXA_ATIVA = 3  # o segundo canal da camada ativa (seção 9.3)
LARGURA_DECISAO = 4  # contorno laranja reforçado da camada 3 em ROTEIA

ALTURA_CAIXA = 22.0
LARGURA_CAIXA = 34.0
ESPACO_ENTRE_CAIXAS = 3.0
ESPACO_ENTRE_COLUNAS = 20.0
ALTURA_CABECALHO = 20.0

# Cada região da tela apaga só o que é seu: sem isto, redesenhar as pilhas
# levaria o mapa junto.
ETIQUETA_PILHAS = "pilhas"

CAMADAS_DO_COMPUTADOR = 7
CAMADAS_DO_ROTEADOR = 3

# Os dois modelos de exibição da pilha (V7, issue #55). Declarados aqui
# porque a `Janela` já nasce sabendo em qual está; o reagrupamento em si
# chega depois.
MODELO_OSI = "osi"
MODELO_TCPIP = "tcpip"

# Seção 7.3. A chave é o número da camada OSI; o valor, o rótulo TCP/IP. As
# camadas 5, 6 e 7 apontam para o mesmo rótulo, e é isso que as agrupa.
ROTULOS_TCPIP = {
    7: "Aplicação",
    6: "Aplicação",
    5: "Aplicação",
    4: "Transporte",
    3: "Internet",
    2: "Enlace de dados",
    1: "Física",
}

# A caixa agrupada é desenhada com o número 7, a mais alta das três: é assim
# que ela é identificada nas etiquetas, e é a que o usuário lê como "o topo
# da pilha".
CAMADAS_AGRUPADAS = (7, 6, 5)


@dataclass(frozen=True)
class EstadoDasPilhas:
    """O retrato das pilhas no passo corrente, extraído **só** de eventos.

    `colunas` é quem participou do caso até aqui, na ordem em que entrou em
    cena: em C2 dá exatamente as cinco colunas do layout da seção 9.1 (H1, R1,
    R4, R3, H4). Ficam de fora os eventos secundários — H2 e H5 ouvem o quadro
    no segmento de difusão e o descartam por endereço, e ouvir não é
    participar — e os de sistema, cujo dispositivo é `--`.

    `decidiu_rota` merece explicação, porque a issue pede o contorno laranja
    só quando o dispositivo é roteador, e esta classe não tem topologia para
    consultar. O sinal vem do contrato: `ROTEIA` com `sentido` igual a `meio`.
    Um computador rotea **descendo** a própria pilha (`desce`); o roteador
    rotea de passagem, e `meio` é justamente o sentido que diz que a PDU
    entrou e vai sair sem subir até o topo. Conferido nos sete casos: todo
    `meio` é de roteador, e nenhum computador emite `meio`. É o campo do
    evento respondendo, não a interface adivinhando pelo histórico."""

    colunas: tuple[str, ...]
    dispositivo: str | None
    camada: int
    sentido: str | None
    decidiu_rota: bool
    estado: str

    @classmethod
    def ate(cls, eventos: Sequence[Evento]) -> "EstadoDasPilhas":
        """O estado acumulado do primeiro evento ao corrente.

        Recebe o que `Navegador.ate_agora()` devolve. Acumular a cada desenho,
        em vez de guardar estado entre passos, é o que faz o retrocesso (V5)
        sair de graça: voltar um passo é desenhar de novo com uma fatia menor.
        """
        if not eventos:
            raise ValueError("sem eventos: as pilhas não têm passo para retratar")
        colunas = tuple(
            dict.fromkeys(
                evento.dispositivo
                for evento in eventos
                if not evento.secundario and evento.camada != 0
            )
        )
        atual = eventos[-1]
        de_sistema = atual.camada == 0
        return cls(
            colunas=colunas,
            dispositivo=None if de_sistema else atual.dispositivo,
            camada=0 if de_sistema else atual.camada,
            sentido=None if de_sistema else atual.sentido,
            decidiu_rota=atual.acao == "ROTEIA" and atual.sentido == "meio",
            estado=atual.estado,
        )

    def acesa(self, dispositivo: str, camada: int) -> bool:
        """Só uma caixa acende por passo: a do dispositivo que agiu."""
        return dispositivo == self.dispositivo and camada == self.camada


class PilhasDosDispositivos:
    """As pilhas (V2) desenhadas sobre uma tela de `Canvas`.

    Como o mapa, a tela chega pronta de fora e o desenho é sempre do zero:
    `desenhar()` apaga o que havia e refaz. Quantas caixas cada dispositivo
    tem sai da `Planta` — é fato da topologia, não do passo corrente, e uma
    pilha que crescesse conforme o roteador fosse agindo mostraria uma camada
    2 aparecendo do nada, que é o oposto do que a região existe para dizer."""

    def __init__(self, tela, planta: Planta):
        self.tela = tela
        self.planta = planta
        self._realcar = True
        self._modelo = MODELO_OSI

    # — API ————————————————————————————————————————————————————————————

    def desenhar(
        self,
        estado: EstadoDasPilhas,
        largura: float | None = None,
        altura: float | None = None,
        *,
        realcar: bool = True,
        modelo: str = MODELO_OSI,
    ) -> None:
        """`realcar=False` desenha o mesmo estado sem o destaque forte da
        decisão de rota — é o que faz o pulso apagar sem que o estado mude
        (issue #53).

        `modelo` escolhe entre a pilha OSI de sete caixas e a TCP/IP com 5, 6
        e 7 agrupadas (V7, issue #55). É **só** exibição: o mesmo
        `EstadoDasPilhas` desenhado de outro jeito. O estado não sabe que
        modelos existem, e não pode saber — seria a interface contaminando o
        retrato que sai dos eventos.

        Os dois parâmetros têm padrão, de modo que os testes de F5, que não
        conhecem nenhum dos dois, continuem valendo sem retoque."""
        self._realcar = realcar
        self._modelo = modelo
        self.tela.delete(ETIQUETA_PILHAS)
        largura = largura if largura is not None else self.tela.winfo_width()
        altura = altura if altura is not None else self.tela.winfo_height()
        if not estado.colunas:
            return
        escala = self._escala(estado, largura, altura)
        base = altura - escala * ESPACO_ENTRE_COLUNAS
        for indice, nome in enumerate(estado.colunas):
            self._desenhar_coluna(estado, nome, indice, escala, base, largura)

    # — medidas ————————————————————————————————————————————————————————

    def _escala(
        self, estado: EstadoDasPilhas, largura: float, altura: float
    ) -> float:
        """Um fator só, para caber tanto na largura quanto na altura.

        A largura aperta quando o caso tem muitas colunas (C3 tem seis); a
        altura aperta sempre, porque a coluna do computador tem sete caixas.
        Encolher só num eixo deixaria a pilha estourando no outro."""
        colunas = len(estado.colunas)
        pedida_x = colunas * LARGURA_CAIXA + (colunas + 1) * ESPACO_ENTRE_COLUNAS
        pedida_y = (
            CAMADAS_DO_COMPUTADOR * (ALTURA_CAIXA + ESPACO_ENTRE_CAIXAS)
            + ALTURA_CABECALHO
            + 2 * ESPACO_ENTRE_COLUNAS
        )
        return min(1.0, largura / pedida_x, altura / pedida_y)

    def _camadas(self, nome: str) -> int:
        return (
            CAMADAS_DO_ROTEADOR
            if self.planta.no(nome).roteador
            else CAMADAS_DO_COMPUTADOR
        )

    def _camadas_visiveis(self, nome: str) -> tuple[int, ...]:
        """Os números de camada que viram caixa, de baixo para cima.

        No modelo TCP/IP, 5, 6 e 7 viram uma só, representada pelo 7. O
        roteador não muda: ele nunca teve as camadas de cima, e agrupar o que
        não existe não faria diferença nenhuma — o buraco continua sendo o
        assunto da coluna dele."""
        total = self._camadas(nome)
        if self._modelo == MODELO_OSI or total <= 4:
            return tuple(range(1, total + 1))
        return tuple(range(1, 5)) + (7,)

    def _rotulo(self, camada: int) -> str:
        return (
            str(camada)
            if self._modelo == MODELO_OSI
            else ROTULOS_TCPIP[camada]
        )

    def _acesa(self, estado: EstadoDasPilhas, nome: str, camada: int) -> bool:
        """No modelo TCP/IP, a caixa agrupada acende para 5, 6 **ou** 7."""
        if self._modelo == MODELO_TCPIP and camada == 7:
            return any(
                estado.acesa(nome, numero) for numero in CAMADAS_AGRUPADAS
            )
        return estado.acesa(nome, camada)

    # — desenho ————————————————————————————————————————————————————————

    def _desenhar_coluna(
        self,
        estado: EstadoDasPilhas,
        nome: str,
        indice: int,
        escala: float,
        base: float,
        largura: float,
    ) -> None:
        passo_x = (LARGURA_CAIXA + ESPACO_ENTRE_COLUNAS) * escala
        x0 = ESPACO_ENTRE_COLUNAS * escala + indice * passo_x
        x1 = x0 + LARGURA_CAIXA * escala
        altura_caixa = ALTURA_CAIXA * escala
        passo_y = altura_caixa + ESPACO_ENTRE_CAIXAS * escala
        etiquetas_da_coluna = (ETIQUETA_PILHAS, f"pilha:{nome}")

        topo_mais_alto = base
        for posicao, camada in enumerate(self._camadas_visiveis(nome)):
            # Camada 1 embaixo, a mais alta em cima: a pilha é desenhada como
            # se lê, e a base comum é o que revela o buraco do roteador. A
            # altura vem da **posição** e não do número, que deixa de ser
            # contíguo quando 5, 6 e 7 viram uma caixa só.
            y1 = base - posicao * passo_y
            y0 = y1 - altura_caixa
            topo_mais_alto = min(topo_mais_alto, y0)
            self._desenhar_caixa(estado, nome, camada, x0, y0, x1, y1, escala)

        self.tela.create_text(
            (x0 + x1) / 2,
            topo_mais_alto - ALTURA_CABECALHO * escala / 2,
            text=nome,
            fill=COR_TEXTO,
            font=("TkDefaultFont", max(int(round(9 * escala)), 7)),
            tags=etiquetas_da_coluna,
        )

    def _desenhar_caixa(
        self,
        estado: EstadoDasPilhas,
        nome: str,
        camada: int,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        escala: float,
    ) -> None:
        acesa = self._acesa(estado, nome, camada)
        decisao = (
            self._realcar
            and estado.decidiu_rota
            and nome == estado.dispositivo
            and camada == 3
        )
        problema = acesa and estado.estado != "ok"
        if decisao:
            contorno, espessura = COR_DECISAO, LARGURA_DECISAO
        elif acesa:
            contorno, espessura = COR_BORDA_NO, LARGURA_CAIXA_ATIVA
        else:
            contorno, espessura = COR_BORDA_REDE, LARGURA_CAIXA_INATIVA
        if acesa:
            preenchimento = COR_ERRO if problema else COR_CAMADA_ATIVA
        else:
            preenchimento = COR_CAMADA_INATIVA
        etiquetas = (ETIQUETA_PILHAS, f"pilha:{nome}", f"camada:{nome}:{camada}")
        self.tela.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=preenchimento,
            outline=contorno,
            width=espessura,
            tags=etiquetas,
        )
        if problema:
            # O descarte de C5 não tem enlace no evento, então o marcador do
            # mapa não aparece: sem esta marca, o passo em que o pacote morre
            # não estaria em lugar nenhum da tela (issue #52).
            self.tela.create_text(
                x1 + (x1 - x0) * 0.22,
                (y0 + y1) / 2,
                text=SIMBOLO_ERRO,
                fill=COR_ERRO,
                font=("TkDefaultFont", max(int(round(10 * escala)), 7), "bold"),
                tags=etiquetas + (ETIQUETA_ERRO,),
            )
        # "Enlace de dados" não cabe na largura de uma caixa desenhada para o
        # algarismo "2": no modelo agrupado a fonte encolhe.
        corpo = (
            max(int(round(9 * escala)), 7)
            if self._modelo == MODELO_OSI
            else max(int(round(6 * escala)), 5)
        )
        self.tela.create_text(
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            text=self._rotulo(camada),
            fill=COR_TEXTO_ATIVO if acesa else COR_TEXTO,
            font=("TkDefaultFont", corpo),
            tags=etiquetas,
        )


# ==========================================================================
# V3 — a unidade de dados corrente em blocos proporcionais (issue #50)
# ==========================================================================
#
# A região 4 do layout (seção 9.1). Não tem classe de estado, e a ausência é
# deliberada: o mapa e as pilhas acumulam (o caminho percorrido, as colunas
# que já entraram em cena), mas a PDU não acumula nada — ela **é** o evento
# corrente. Um `EstadoDaPdu` seria uma cópia de `evento.pdu` com outro nome.

COR_BLOCO_CABECALHO = "#cfe0f5"
COR_BLOCO_DADOS = "#ffffff"
COR_BLOCO_FINALIZADOR = "#b7c3d1"
COR_BORDA_BLOCO = "#5a6675"

ETIQUETA_PDU = "pdu"

ALTURA_BLOCO = 38.0
LARGURA_MINIMA_BLOCO = 22.0  # piso: um bloco de 4 B não pode virar um risco
MARGEM_PDU = 12.0
ALTURA_TITULO_PDU = 20.0

CORES_DO_BLOCO = {
    "cabecalho": COR_BLOCO_CABECALHO,
    "dados": COR_BLOCO_DADOS,
    "finalizador": COR_BLOCO_FINALIZADOR,
}


class UnidadeDeDados:
    """A PDU corrente (V3) desenhada sobre uma tela de `Canvas`.

    Desenha os blocos **na ordem recebida**, e essa é a regra que governa a
    classe inteira. A lista já chega certa da esquerda para a direita
    (issue #2): cabeçalhos à esquerda, dados no meio, finalizador à direita.
    Essa ordem é uma afirmação do núcleo sobre como o encapsulamento
    aconteceu, e reordenar aqui — por tamanho, por tipo, pelo que fosse —
    seria a interface contando uma história própria sobre a PDU.

    A largura de cada bloco é proporcional ao seu `tam`, com um piso: os 4 B
    do `H5` ao lado dos 42 B dos dados dariam três pixels, e um bloco que não
    cabe o próprio rótulo deixou de informar. O piso distorce a proporção nos
    blocos pequenos, e é uma troca consciente — legibilidade antes de exatidão
    geométrica, já que o número exato está escrito dentro do bloco."""

    def __init__(self, tela):
        self.tela = tela

    # — API ————————————————————————————————————————————————————————————

    def desenhar(
        self,
        evento: Evento,
        largura: float | None = None,
        altura: float | None = None,
    ) -> None:
        self.tela.delete(ETIQUETA_PDU)
        largura = largura if largura is not None else self.tela.winfo_width()
        altura = altura if altura is not None else self.tela.winfo_height()
        self._desenhar_titulo(evento, largura)
        if evento.pdu is None:
            return
        self._desenhar_blocos(evento, largura, altura)

    # — título ————————————————————————————————————————————————————————

    def _desenhar_titulo(self, evento: Evento, largura: float) -> None:
        """`Unidade de dados: Quadro Q1` à esquerda, `92 B` à direita.

        A região continua rotulada mesmo sem PDU — nos eventos de sistema, o
        que se vê é um título dizendo que não há unidade corrente. Deixar o
        quadro anterior na tela seria pior que deixar vazio: o leitor não
        teria como saber que aquilo não vale mais."""
        if evento.pdu is None:
            texto = "Unidade de dados: —"
        elif evento.quadro:
            texto = f"Unidade de dados: {evento.pdu.nome} {evento.quadro}"
        else:
            texto = f"Unidade de dados: {evento.pdu.nome}"
        problema = self._problema(evento)
        if problema:
            texto = f"{texto}  {SIMBOLO_ERRO} {problema}"
        self.tela.create_text(
            MARGEM_PDU,
            ALTURA_TITULO_PDU / 2,
            text=texto,
            anchor="w",
            fill=COR_ERRO if problema else COR_TEXTO,
            font=("TkDefaultFont", 9),
            tags=(ETIQUETA_PDU, "titulo") + ((ETIQUETA_ERRO,) if problema else ()),
        )
        if evento.tamanho is not None:
            self.tela.create_text(
                largura - MARGEM_PDU,
                ALTURA_TITULO_PDU / 2,
                text=f"{evento.tamanho} B",
                anchor="e",
                fill=COR_TEXTO,
                font=("TkDefaultFont", 9),
                tags=(ETIQUETA_PDU, "total"),
            )

    @staticmethod
    def _problema(evento: Evento) -> str:
        """A palavra que descreve o estado ruim, ou vazio quando está tudo bem.

        Vem da ação, e não do `estado`, porque é a ação que o leitor acabou de
        ver no registro: em C6 o evento tem `estado` igual a `erro` e ação
        `DESCARTA`, e "descartado" é o que aconteceu com a unidade que esta
        região está mostrando."""
        if evento.acao in ("DESCARTA", "IGNORA"):
            return "descartado"
        if evento.estado != "ok":
            return evento.estado
        return ""

    # — blocos —————————————————————————————————————————————————————————

    def _larguras(self, blocos, util: float) -> list[float]:
        """As larguras dos blocos: proporcionais ao `tam`, com piso mínimo.

        O piso vale **só para quem precisa dele**. Dar o piso a todos e
        ratear o resto distorceria também os blocos grandes: numa janela
        larga, `Dados` (42 B) e `H3` (20 B) sairiam na razão 2,00 em vez de
        2,10, e a proporcionalidade que a issue pede é justamente o que a
        região existe para mostrar. Aqui os blocos que caberiam abaixo do piso
        são fixados nele, um a um, e os demais dividem o que sobra na
        proporção exata dos seus tamanhos — de modo que numa tela folgada,
        onde ninguém precisa de piso, a proporção é a do `tam` e ponto.

        A distorção que resta é a dos blocos pequenos numa tela apertada, e é
        uma troca consciente: um bloco de 4 B que não cabe o próprio rótulo
        deixou de informar, e o número exato está escrito dentro dele."""
        if not blocos:
            return []
        piso = min(LARGURA_MINIMA_BLOCO, util / len(blocos))
        no_piso: set[int] = set()
        while True:
            livres = [i for i in range(len(blocos)) if i not in no_piso]
            disponivel = util - piso * len(no_piso)
            total = sum(blocos[i].tam for i in livres) or 1
            apertados = [
                i for i in livres if disponivel * blocos[i].tam / total < piso
            ]
            if not apertados or len(no_piso) + len(apertados) == len(blocos):
                no_piso.update(apertados)
                break
            no_piso.update(apertados)
        livres = [i for i in range(len(blocos)) if i not in no_piso]
        disponivel = util - piso * len(no_piso)
        total = sum(blocos[i].tam for i in livres) or 1
        larguras = [
            piso if i in no_piso else disponivel * bloco.tam / total
            for i, bloco in enumerate(blocos)
        ]
        # A última absorve o resíduo de arredondamento: sem isto, a soma pode
        # ficar a um décimo de pixel da borda e o teste de largura útil vira
        # uma loteria.
        larguras[-1] += util - sum(larguras)
        return larguras

    def _desenhar_blocos(self, evento: Evento, largura: float, altura: float) -> None:
        blocos = evento.pdu.blocos
        util = max(largura - 2 * MARGEM_PDU, 1.0)
        topo = ALTURA_TITULO_PDU
        base = min(topo + ALTURA_BLOCO, altura)
        x = MARGEM_PDU
        for bloco, medida in zip(blocos, self._larguras(blocos, util)):
            etiquetas = (
                ETIQUETA_PDU,
                "bloco",
                f"bloco:{bloco.rotulo}",
                f"tipo:{bloco.tipo}",
            )
            self.tela.create_rectangle(
                x,
                topo,
                x + medida,
                base,
                fill=CORES_DO_BLOCO.get(bloco.tipo, COR_BLOCO_DADOS),
                outline=COR_BORDA_BLOCO,
                width=1,
                tags=etiquetas,
            )
            # Rótulo em cima, tamanho embaixo: é o desenho do enunciado, e o
            # texto é o segundo canal que a seção 9.3 exige dos três tipos de
            # bloco — a cor sozinha não os distingue numa impressão cinza.
            self.tela.create_text(
                x + medida / 2,
                topo + ALTURA_BLOCO * 0.32,
                text=bloco.rotulo,
                fill=COR_TEXTO,
                font=("TkDefaultFont", 8),
                tags=etiquetas,
            )
            self.tela.create_text(
                x + medida / 2,
                topo + ALTURA_BLOCO * 0.70,
                text=str(bloco.tam),
                fill=COR_ROTULO,
                font=("TkDefaultFont", 8),
                tags=etiquetas,
            )
            x += medida


# ==========================================================================
# V4 — os dois painéis de endereço (issue #51)
# ==========================================================================
#
# A região 5 do layout (seção 9.1). Os dois painéis existem para tornar
# visível a restrição R3: o par lógico é gravado uma única vez, na camada 3
# da origem, e atravessa a rede inteiro; o par físico é substituído a cada
# salto. Em C2 dá um lógico constante do passo 5 ao 26 contra quatro pares
# físicos — e é o contraste, não cada painel isolado, que ensina.

COR_DESTAQUE_FISICO = "#e8b21a"
COR_MOLDURA_PAINEL = "#c3cedb"
COR_ESMAECIDO = "#9aa4b0"

ETIQUETA_ENDERECOS = "enderecos"

# O que aparece no lugar de um endereço que não existe naquele passo. Um
# travessão é lido como ausência; o endereço do salto anterior seria lido como
# verdade, e é justamente o que o enunciado proíbe.
AUSENTE = "—"

LARGURA_MOLDURA_PAINEL = 1
LARGURA_MOLDURA_ACESA = 3  # o segundo canal do amarelo é a espessura
MARGEM_PAINEL = 12.0
ALTURA_TITULO_PAINEL = 18.0
ALTURA_LINHA_PAINEL = 16.0


@dataclass(frozen=True)
class EstadoDosEnderecos:
    """O retrato dos dois pares no passo corrente, extraído **só** de eventos.

    `fisico_mudou` é o que aciona o destaque, e a regra é a do enunciado: o
    par físico do evento corrente é diferente do par físico do evento anterior
    navegado. Em C2 acende em 7, 12, 17 e 22 — os quatro `ENQUADRA`, um por
    salto —, e fica apagado nos `TRANSMITE` e `RECEBE` seguintes, que repetem
    o mesmo par. Uma troca para ausência (a camada 3, que não tem par físico)
    não é substituição: ali não há endereço novo, há endereço nenhum.

    `fisico_ausente` e o `logico` nulo levam ao mesmo lugar, e de propósito:
    quando o par não existe naquele passo, o painel mostra `AUSENTE`. Manter o
    último valor na tela seria mostrar um endereço que não está em lugar
    nenhum da PDU corrente — o oposto do que a região ensina."""

    logico: tuple[str, str] | None
    fisico: tuple[str, str] | None
    fisico_mudou: bool

    @property
    def fisico_ausente(self) -> bool:
        return self.fisico is None

    @property
    def logico_ausente(self) -> bool:
        return self.logico is None

    @classmethod
    def ate(cls, eventos: Sequence[Evento]) -> "EstadoDosEnderecos":
        if not eventos:
            raise ValueError("sem eventos: os endereços não têm passo para retratar")
        atual = eventos[-1]
        anterior = eventos[-2] if len(eventos) > 1 else None
        fisico = cls._par(atual.fisico)
        antes = cls._par(anterior.fisico) if anterior is not None else None
        return cls(
            logico=cls._par(atual.logico),
            fisico=fisico,
            fisico_mudou=fisico is not None and fisico != antes,
        )

    @staticmethod
    def _par(dado) -> tuple[str, str] | None:
        """O par como duas cadeias, ou `None` quando não há par naquele passo.

        Um `Fisico` com origem ou destino vazio conta como ausência: meia
        dupla de endereços não descreve salto nenhum."""
        if dado is None or dado.origem is None or dado.destino is None:
            return None
        return (dado.origem, dado.destino)


class PaineisDeEndereco:
    """Os dois painéis de endereço (V4) desenhados sobre uma tela de `Canvas`.

    Lado a lado e do mesmo tamanho, porque a comparação é o conteúdo: dois
    painéis de larguras diferentes sugeririam que um importa mais que o outro,
    quando o que a região diz é que os dois valem ao mesmo tempo e se
    comportam de maneiras opostas.

    O destaque da substituição é amarelo **e** mais grosso **e** escrito por
    extenso, os três canais de uma informação só (seção 9.3). O amarelo
    sozinho sumiria para quem não o distingue e numa captura em preto e
    branco para o relatório."""

    def __init__(self, tela):
        self.tela = tela

    # — API ————————————————————————————————————————————————————————————

    def desenhar(
        self,
        estado: EstadoDosEnderecos,
        largura: float | None = None,
        altura: float | None = None,
        *,
        realcar: bool = True,
    ) -> None:
        """`realcar=False` apaga o destaque da substituição sem mexer no
        estado — é assim que a piscada termina (issue #53)."""
        self.tela.delete(ETIQUETA_ENDERECOS)
        largura = largura if largura is not None else self.tela.winfo_width()
        altura = altura if altura is not None else self.tela.winfo_height()
        meio = largura / 2
        self._desenhar_painel(
            painel="logico",
            titulo="🔒 Endereços lógicos",
            subtitulo="constantes de ponta a ponta",
            par=estado.logico,
            aceso=False,
            x0=MARGEM_PAINEL,
            x1=meio - MARGEM_PAINEL / 2,
            altura=altura,
        )
        self._desenhar_painel(
            painel="fisico",
            titulo="Endereços físicos",
            subtitulo="substituídos a cada salto",
            par=estado.fisico,
            aceso=estado.fisico_mudou and realcar,
            x0=meio + MARGEM_PAINEL / 2,
            x1=largura - MARGEM_PAINEL,
            altura=altura,
        )

    # — desenho ————————————————————————————————————————————————————————

    def _desenhar_painel(
        self,
        *,
        painel: str,
        titulo: str,
        subtitulo: str,
        par: tuple[str, str] | None,
        aceso: bool,
        x0: float,
        x1: float,
        altura: float,
    ) -> None:
        etiquetas = (ETIQUETA_ENDERECOS, f"painel:{painel}")
        self.tela.create_rectangle(
            x0,
            MARGEM_PAINEL / 2,
            x1,
            altura - MARGEM_PAINEL / 2,
            fill=COR_FUNDO,
            outline=COR_DESTAQUE_FISICO if aceso else COR_MOLDURA_PAINEL,
            width=LARGURA_MOLDURA_ACESA if aceso else LARGURA_MOLDURA_PAINEL,
            tags=etiquetas,
        )
        topo = MARGEM_PAINEL / 2 + ALTURA_TITULO_PAINEL / 2 + 2
        self.tela.create_text(
            x0 + MARGEM_PAINEL,
            topo,
            text=titulo,
            anchor="w",
            fill=COR_TEXTO,
            font=("TkDefaultFont", 9, "bold"),
            tags=etiquetas,
        )
        self.tela.create_text(
            x1 - MARGEM_PAINEL,
            topo,
            text=subtitulo,
            anchor="e",
            fill=COR_ROTULO,
            font=("TkDefaultFont", 8),
            tags=etiquetas,
        )
        if aceso:
            # O terceiro canal do destaque, e o único que sobrevive a uma
            # captura em preto e branco: o aviso por extenso, em elemento
            # próprio. Embutido no subtítulo ele seria indistinguível do
            # "substituídos a cada salto" que está sempre lá.
            self.tela.create_text(
                x1 - MARGEM_PAINEL,
                altura - MARGEM_PAINEL,
                text="↻ substituído neste salto",
                anchor="e",
                fill=COR_TEXTO,
                font=("TkDefaultFont", 8, "bold"),
                tags=etiquetas + ("aviso",),
            )
        ausente = par is None
        for indice, rotulo in enumerate(("origem", "destino")):
            linha = topo + ALTURA_TITULO_PAINEL + indice * ALTURA_LINHA_PAINEL
            self.tela.create_text(
                x0 + MARGEM_PAINEL,
                linha,
                text=rotulo,
                anchor="w",
                fill=COR_ROTULO,
                font=("TkDefaultFont", 8),
                tags=etiquetas,
            )
            self.tela.create_text(
                x0 + MARGEM_PAINEL + 58,
                linha,
                text=AUSENTE if ausente else par[indice],
                anchor="w",
                fill=COR_ESMAECIDO if ausente else COR_TEXTO,
                font=("TkFixedFont", 9),
                tags=etiquetas + ("valor",),
            )


# ==========================================================================
# V6 — o registro de eventos na tela (issue #54)
# ==========================================================================

# O bit corrompido pela injeção avulsa (issue #56). É convenção da interface,
# não dado da topologia: `parametros.verificacao` guarda `algoritmo` e
# `polinomio`, e mais nada. 100 é o mesmo bit que o C6 declara no arquivo, de
# modo que o botão reproduza a demonstração conhecida.
BIT_DA_INJECAO = 100

ETIQUETA_LINHA_ATUAL = "linha-atual"
COR_REALCE_LINHA = "#fff3c4"


class RegistroNaTela:
    """As linhas do registro num `Text` rolável, com a corrente realçada.

    Toda linha sai de `Evento.linha()`, sem exceção — é a regra dura da seção
    8.2, e a razão de T-V6 poder existir: o arquivo salvo e a tela vêm da
    mesma origem, então compará-los é comparar duas cadeias, e não dois
    formatadores que poderiam divergir em silêncio.

    Os eventos secundários (o `IGNORA` de quem descarta por endereço numa
    difusão) ficam ocultos por padrão. Ocultos, não removidos: a caixa da
    issue #56 os revela sem que nada seja reexecutado, porque eles sempre
    estiveram na lista."""

    def __init__(self, widget):
        self.widget = widget
        self.widget.tag_configure(
            ETIQUETA_LINHA_ATUAL, background=COR_REALCE_LINHA
        )

    @staticmethod
    def _visiveis(eventos, mostrar_secundarios: bool):
        if mostrar_secundarios:
            return list(eventos)
        return [evento for evento in eventos if not evento.secundario]

    def texto(
        self, eventos, cabecalho: str, mostrar_secundarios: bool = False
    ) -> str:
        """O registro completo, do jeito que vai para o arquivo (seção 8.3).

        Mesma fonte da tela, de propósito: é isto que T-V6 compara."""
        linhas = [cabecalho]
        linhas.extend(
            evento.linha()
            for evento in self._visiveis(eventos, mostrar_secundarios)
        )
        return "\n".join(linhas) + "\n"

    def desenhar(
        self, eventos, indice: int, mostrar_secundarios: bool = False
    ) -> None:
        visiveis = self._visiveis(eventos, mostrar_secundarios)
        self.widget.configure(state="normal")
        self.widget.delete("1.0", "end")
        self.widget.insert(
            "1.0", "\n".join(evento.linha() for evento in visiveis)
        )
        self.widget.tag_remove(ETIQUETA_LINHA_ATUAL, "1.0", "end")

        alvo = self._linha_do_indice(eventos, visiveis, indice)
        if alvo is not None:
            self.widget.tag_add(
                ETIQUETA_LINHA_ATUAL, f"{alvo + 1}.0", f"{alvo + 1}.end"
            )
            self.widget.see(f"{alvo + 1}.0")
        self.widget.configure(state="disabled")

    @staticmethod
    def _linha_do_indice(eventos, visiveis, indice: int):
        """Qual linha da tela corresponde ao evento de índice `indice`.

        Índice e número de linha não coincidem quando há secundários ocultos.
        Se o evento corrente for um deles, o realce cai no último evento
        principal antes dele — o passo ainda é aquele, e deixar a tela sem
        realce nenhum pareceria que a navegação travou."""
        if not visiveis or indice >= len(eventos):
            return None
        corrente = eventos[indice]
        if not corrente.secundario:
            return visiveis.index(corrente)
        for anterior in range(indice, -1, -1):
            if not eventos[anterior].secundario:
                return visiveis.index(eventos[anterior])
        return None


# ==========================================================================
# A janela (F6)
# ==========================================================================
#
# Tudo o que vem do motor chega por parâmetro. A janela não carrega topologia,
# não executa caso, não formata cabeçalho e não sabe quais casos ou enlaces
# existem — recebe as cinco coisas prontas. É o que mantém a regra da seção
# 4.2 valendo com os controles da issue #56, que precisam **reexecutar** a
# simulação, e é o que torna esses controles testáveis com um motor de
# mentira, sem display e sem núcleo.


class Janela:
    """A tela inteira: as quatro regiões de F5 mais os controles de F6.

    `executar` é a única porta para o motor, e tem esta forma:

        executar(caso, intervencoes) -> (tuple[Evento, ...], str)

    Devolve os eventos **e** o cabeçalho do registro, porque o cabeçalho
    nomeia o caso e muda a cada reexecução — inclusive o id derivado, quando
    há intervenção (issue #56).

    `agendar` é o relógio, com a forma de `widget.after`; `None` significa
    "use o do próprio widget", que é o que acontece no programa de verdade. O
    teste passa um relógio de mentira e dispara os tempos na mão.

    A assinatura já nasce completa, com `caso` e `enlaces` que só serão usados
    pelos controles das tarefas seguintes: mudar construtor no meio do
    caminho obrigaria a revisitar todos os testes já escritos."""

    def __init__(
        self,
        planta: Planta,
        navegador: Navegador,
        *,
        caso: str,
        executar,
        cabecalho: str,
        casos,
        velocidades,
        enlaces=(),
        agendar=None,
        escolher_arquivo=None,
    ):
        self.planta = planta
        self.navegador = navegador
        self.executar = executar
        self.cabecalho = cabecalho
        self.casos = tuple(casos)
        self.enlaces = tuple(enlaces)
        self.velocidades = dict(velocidades)
        self.velocidade_corrente = "media"
        self.modelo = MODELO_OSI
        self.mostrar_secundarios = False
        self.ultimo_aviso = ""
        self.registro = None
        self._caso_corrente = caso
        self._intervencoes = ()
        self._agendar = agendar
        self._escolher_arquivo = escolher_arquivo
        self._raiz = None
        self._rodape = None
        self._marca_do_relogio = None
        self._marca_do_pulso = None
        self._pulso_apagado = False
        self.mapa = None
        self.pilhas = None
        self.pdu = None
        self.enderecos = None

    @property
    def caso(self) -> str:
        return self._caso_corrente

    # — montagem ———————————————————————————————————————————————————————

    def ligar_telas(self, mapa, pilhas, pdu, enderecos) -> None:
        """Recebe as quatro telas já criadas e monta as regiões sobre elas.

        Separada de `montar()` para o teste poder ligar telas de mentira sem
        abrir janela nenhuma — é o mesmo truque que tornou as regiões de F5
        verificáveis."""
        self.mapa = MapaDaRede(mapa, self.planta)
        self.pilhas = PilhasDosDispositivos(pilhas, self.planta)
        self.pdu = UnidadeDeDados(pdu)
        self.enderecos = PaineisDeEndereco(enderecos)

    def redesenhar(self) -> None:
        """Redesenha tudo a partir dos eventos até o passo corrente.

        Nenhuma chamada ao motor: a simulação rodou inteira antes do primeiro
        desenho (issue #32), e navegar é mover um índice."""
        ate_agora = self.navegador.ate_agora()
        pilhas = EstadoDasPilhas.ate(ate_agora)
        enderecos = EstadoDosEnderecos.ate(ate_agora)
        realcar = not self._pulso_apagado
        self.mapa.desenhar(EstadoDoMapa.ate(ate_agora))
        self.pilhas.desenhar(pilhas, realcar=realcar, modelo=self.modelo)
        self.pdu.desenhar(self.navegador.atual)
        self.enderecos.desenhar(enderecos, realcar=realcar)
        if self._rodape is not None:
            atual = self.navegador.atual
            self._rodape.config(
                text=self.ultimo_aviso
                or f"{self._caso_corrente} · passo {self.navegador.indice + 1}"
                f"/{self.navegador.total} · {atual.linha()}"
            )
        if self.registro is not None:
            self.registro.desenhar(
                self.navegador.eventos,
                self.navegador.indice,
                self.mostrar_secundarios,
            )
        if realcar:
            self._talvez_pulsar(pilhas, enderecos)

    # — os controles que reexecutam (issue #56) ————————————————————————
    #
    # São os únicos métodos da classe que chamam o motor, e chamam através do
    # callback recebido no construtor: a janela não sabe quem executa, nem
    # que existe um `simulador.py`.

    def trocar_caso(self, caso: str) -> None:
        """Roda outro caso do zero e recomeça a navegação no índice 0.

        As intervenções acumuladas caem junto: elas eram do caso anterior, e
        arrastá-las para o novo faria o seletor mentir sobre o que está na
        tela."""
        self._intervencoes = ()
        self._recarregar(caso)

    def derrubar_enlace(self, enlace: str) -> None:
        self._acrescentar(Intervencao(tipo="enlace_fora", enlace=enlace))

    def injetar_erro(self, enlace: str) -> None:
        """Arma a corrupção de bit para o próximo quadro naquele enlace."""
        quadro = self.quadro_seguinte_no(enlace)
        if quadro is None:
            # Reexecutar sem efeito visível pareceria um programa quebrado:
            # melhor dizer por que nada aconteceu.
            self.ultimo_aviso = (
                f"Nenhum quadro atravessa {enlace} a partir daqui neste caso: "
                "a injeção não teria efeito visível."
            )
            return
        self._acrescentar(
            Intervencao(
                tipo="erro_bit",
                enlace=enlace,
                quadro=quadro,
                bit=BIT_DA_INJECAO,
            )
        )

    def quadro_seguinte_no(self, enlace: str) -> str | None:
        """O primeiro quadro que ainda vai atravessar aquele enlace.

        Sai da lista de eventos **já produzida** — não há execução
        especulativa aqui, só uma varredura do que o motor já disse que vai
        acontecer. Em C7, onde há doze quadros, é o que faz o botão armar um
        quadro diferente conforme se navega, em vez de repetir sempre a mesma
        demonstração."""
        for evento in self.navegador.eventos[self.navegador.indice :]:
            if (
                evento.enlace is not None
                and evento.enlace.id == enlace
                and evento.quadro
            ):
                return evento.quadro
        return None

    def _acrescentar(self, intervencao: Intervencao) -> None:
        self._intervencoes = self._intervencoes + (intervencao,)
        self._recarregar(self._caso_corrente)

    def _recarregar(self, caso: str) -> None:
        self.pausar()
        eventos, cabecalho = self.executar(caso, self._intervencoes)
        self._caso_corrente = caso
        self.cabecalho = cabecalho
        self.navegador = Navegador(eventos)
        self.ultimo_aviso = ""
        self.redesenhar()

    def ligar_registro(self, widget) -> None:
        """Liga o registro a um widget já criado (o teste passa um de mentira)."""
        self.registro = RegistroNaTela(widget)

    def salvar(self) -> str | None:
        """Grava o registro completo num arquivo de texto UTF-8 (seção 8.3).

        Devolve o caminho gravado, ou `None` se o diálogo foi cancelado.

        `newline="\\n"` para o arquivo sair igual nos dois sistemas: sem isto
        o Windows grava CRLF, e a comparação byte a byte de dois registros
        passaria a depender da plataforma que gerou cada um — a mesma razão
        que o modo textual já tinha.

        O diálogo entra por injeção, como o relógio e o executor. Sem isso, o
        teste do salvamento precisaria abrir janela, e o T-V6 deixaria de
        rodar na máquina sem display que roda o resto da suíte."""
        from datetime import datetime

        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = self._dialogo(
            title="Salvar registro",
            initialfile=f"registro_{self._caso_corrente}_{carimbo}.txt",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos os arquivos", "*.*")],
        )
        if not destino:
            return None
        conteudo = self.registro.texto(
            self.navegador.eventos, self.cabecalho, self.mostrar_secundarios
        )
        with open(destino, "w", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(conteudo)
        return destino

    def _dialogo(self, **opcoes):
        if self._escolher_arquivo is not None:
            return self._escolher_arquivo(**opcoes)
        from tkinter import filedialog

        return filedialog.asksaveasfilename(**opcoes)

    def alternar_modelo(self, modelo: str) -> None:
        """OSI ou TCP/IP (V7, issue #55).

        Só exibição: a lista de eventos não muda, o registro continua dizendo
        `L6`, e nada é reexecutado."""
        if modelo not in (MODELO_OSI, MODELO_TCPIP):
            raise ValueError(
                f"modelo {modelo!r} não existe; há {MODELO_OSI} e {MODELO_TCPIP}"
            )
        self.modelo = modelo
        self.redesenhar()

    def alternar_descartes(self, mostrar: bool) -> None:
        """Revela ou esconde os eventos secundários no registro.

        Só exibição: a lista de eventos não muda e nada é reexecutado — a
        caixa da issue #56 mexe no que se vê, nunca no que aconteceu."""
        self.mostrar_secundarios = bool(mostrar)
        self.redesenhar()

    # — o pulso e a piscada (a dívida da F5) ———————————————————————————
    #
    # A F5 desenhou os dois destaques de forma estática de propósito: o
    # esmaecer precisa de relógio, e o relógio só chegou com o V5. Como o
    # estado já dizia `decidiu_rota` e `fisico_mudou`, o que falta é curto.

    DURACAO_DO_PULSO = 420  # ms

    @property
    def destaque_vivo(self) -> bool:
        return self._marca_do_pulso is not None

    def _talvez_pulsar(self, pilhas, enderecos) -> None:
        if self._marca_do_pulso is not None:
            self._cancelar(self._marca_do_pulso)
            self._marca_do_pulso = None
        if not (pilhas.decidiu_rota or enderecos.fisico_mudou):
            return
        self._marca_do_pulso = self._relogio(
            self.DURACAO_DO_PULSO, self._apagar_pulso
        )

    def _apagar_pulso(self) -> None:
        """Apaga o realce forte e redesenha sem ele.

        `_pulso_apagado` é lido pelo próprio `redesenhar`; sem a bandeira, o
        redesenho reacenderia o destaque e agendaria outro pulso, e a animação
        nunca terminaria."""
        if self._marca_do_pulso is None:
            return
        self._marca_do_pulso = None
        self._pulso_apagado = True
        try:
            self.redesenhar()
        finally:
            self._pulso_apagado = False

    # — navegação (V5, issue #53) ——————————————————————————————————————
    #
    # Tudo aqui é índice. A simulação já rodou inteira antes do primeiro
    # desenho (issue #32), então "anterior" custa o mesmo que "próximo" — é o
    # ganho que a arquitetura de baixo para cima comprou, e a razão de estes
    # métodos não terem nenhuma chamada ao motor.

    @property
    def em_execucao(self) -> bool:
        return self._marca_do_relogio is not None

    def proximo(self) -> None:
        if not self.navegador.no_fim:
            self.navegador.proximo()
            self.redesenhar()

    def anterior(self) -> None:
        if not self.navegador.no_inicio:
            self.navegador.anterior()
            self.redesenhar()

    def mudar_velocidade(self, nome: str) -> None:
        if nome not in self.velocidades:
            raise ValueError(
                f"velocidade {nome!r} não existe; há "
                f"{', '.join(sorted(self.velocidades))}"
            )
        self.velocidade_corrente = nome
        if self.em_execucao:
            # Vale já no próximo passo, e não só depois de pausar e recomeçar:
            # quem arrasta o seletor no meio da execução espera ver o efeito.
            self.pausar()
            self.executar_continuo()

    def executar_continuo(self) -> None:
        """Avança sozinho até o fim ou até `pausar()`.

        Sai cedo se já houver uma cadeia viva: dois agendamentos em paralelo
        fariam o registro andar de dois em dois passos, e o sintoma seria
        confundido com defeito do motor."""
        if self.em_execucao or self.navegador.no_fim:
            return
        self._agendar_passo()

    def pausar(self) -> None:
        if self._marca_do_relogio is not None:
            self._cancelar(self._marca_do_relogio)
            self._marca_do_relogio = None

    def _agendar_passo(self) -> None:
        atraso = self.velocidades[self.velocidade_corrente]
        self._marca_do_relogio = self._relogio(atraso, self._passo_automatico)

    def _passo_automatico(self) -> None:
        self._marca_do_relogio = None
        self.proximo()
        if not self.navegador.no_fim:
            self._agendar_passo()

    # — o relógio ——————————————————————————————————————————————————————
    #
    # `agendar=None` significa "use o `after` do widget", e o widget só existe
    # depois de `montar()`. Injetado, o teste dispara os tempos na mão e o
    # ritmo das três velocidades vira verificável sem display e sem espera.

    def _relogio(self, atraso: int, funcao):
        if self._agendar is not None:
            return self._agendar(atraso, funcao)
        return self._raiz.after(atraso, funcao)

    def _cancelar(self, marca) -> None:
        if self._agendar is not None:
            cancelar = getattr(self._agendar, "cancelar", None)
            if cancelar is not None:
                cancelar(marca)
            return
        if self._raiz is not None:
            self._raiz.after_cancel(marca)

    def montar(self, raiz) -> None:
        """Cria os widgets e liga as regiões neles.

        É o único ponto do módulo que toca em tkinter, e por isso o importa
        **aqui dentro**: `import visual` continua funcionando numa máquina sem
        tkinter, que é como a suíte roda (seção 13.1)."""
        import tkinter as tk

        from tkinter import ttk

        self._raiz = raiz
        raiz.title("Simulador do Modelo OSI")

        barra = ttk.Frame(raiz)
        barra.pack(side="top", fill="x", padx=6, pady=4)
        ttk.Button(barra, text="◀◀", width=4, command=self.anterior).pack(side="left")
        ttk.Button(barra, text="▶", width=4, command=self.executar_continuo).pack(side="left")
        ttk.Button(barra, text="⏸", width=4, command=self.pausar).pack(side="left")
        ttk.Button(barra, text="▶▶", width=4, command=self.proximo).pack(side="left")

        ttk.Button(barra, text="Salvar", command=self.salvar).pack(side="right")

        self._descartes = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            barra,
            text="mostrar descartes",
            variable=self._descartes,
            command=lambda: self.alternar_descartes(self._descartes.get()),
        ).pack(side="right", padx=(0, 12))

        self._enlace_escolhido = tk.StringVar(
            value=self.enlaces[0] if self.enlaces else ""
        )
        ttk.Button(
            barra,
            text="Injetar erro",
            command=lambda: self.injetar_erro(self._enlace_escolhido.get()),
        ).pack(side="right")
        ttk.Button(
            barra,
            text="Derrubar enlace",
            command=lambda: self.derrubar_enlace(self._enlace_escolhido.get()),
        ).pack(side="right")
        ttk.Combobox(
            barra,
            textvariable=self._enlace_escolhido,
            values=list(self.enlaces),
            state="readonly",
            width=10,
        ).pack(side="right", padx=(12, 4))

        self._modelo_escolhido = tk.StringVar(value=MODELO_OSI)
        ttk.Checkbutton(
            barra,
            text="TCP/IP",
            variable=self._modelo_escolhido,
            onvalue=MODELO_TCPIP,
            offvalue=MODELO_OSI,
            command=lambda: self.alternar_modelo(self._modelo_escolhido.get()),
        ).pack(side="right", padx=(0, 12))

        self._caso_escolhido = tk.StringVar(value=self._caso_corrente)
        seletor = ttk.Combobox(
            barra,
            textvariable=self._caso_escolhido,
            values=list(self.casos),
            state="readonly",
            width=5,
        )
        seletor.pack(side="left", padx=(8, 4))
        seletor.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.trocar_caso(self._caso_escolhido.get()),
        )

        ttk.Label(barra, text="  Velocidade:").pack(side="left")
        self._velocidade_escolhida = tk.StringVar(value=self.velocidade_corrente)
        for nome in ("lenta", "media", "rapida"):
            ttk.Radiobutton(
                barra,
                text=nome,
                value=nome,
                variable=self._velocidade_escolhida,
                command=lambda: self.mudar_velocidade(
                    self._velocidade_escolhida.get()
                ),
            ).pack(side="left")

        corpo = tk.Frame(raiz)
        corpo.pack(side="top", fill="both", expand=True)
        tela_mapa = tk.Canvas(corpo, width=790, height=340, highlightthickness=0)
        tela_mapa.pack(side="left", fill="both", expand=True)
        tela_pilhas = tk.Canvas(corpo, width=490, height=340, highlightthickness=0)
        tela_pilhas.pack(side="right", fill="both", expand=True)
        tela_enderecos = tk.Canvas(raiz, height=76, highlightthickness=0)
        tela_enderecos.pack(side="bottom", fill="x")
        tela_pdu = tk.Canvas(raiz, height=92, highlightthickness=0)
        tela_pdu.pack(side="bottom", fill="x")

        self.ligar_telas(
            mapa=tela_mapa,
            pilhas=tela_pilhas,
            pdu=tela_pdu,
            enderecos=tela_enderecos,
        )
        self._rodape = ttk.Label(raiz, anchor="w")
        self._rodape.pack(side="bottom", fill="x", padx=8, pady=2)

        quadro_registro = ttk.Frame(raiz)
        quadro_registro.pack(side="bottom", fill="both")
        rolagem = ttk.Scrollbar(quadro_registro)
        rolagem.pack(side="right", fill="y")
        texto = tk.Text(
            quadro_registro,
            height=8,
            font=("TkFixedFont", 9),
            wrap="none",
            yscrollcommand=rolagem.set,
        )
        texto.pack(side="left", fill="both", expand=True)
        rolagem.config(command=texto.yview)
        self.ligar_registro(texto)

        for tela in (tela_mapa, tela_pilhas, tela_pdu, tela_enderecos):
            tela.bind("<Configure>", lambda _evento: self.redesenhar())
        raiz.bind("<Left>", lambda _evento: self.anterior())
        raiz.bind("<Right>", lambda _evento: self.proximo())
        raiz.bind(
            "<space>",
            lambda _evento: self.pausar()
            if self.em_execucao
            else self.executar_continuo(),
        )
        raiz.bind("<Escape>", lambda _evento: raiz.destroy())
