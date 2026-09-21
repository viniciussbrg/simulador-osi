"""Estrutura da PDU (blocos, cabeçalhos, tamanho) e o `Quadro` da camada 2 —
subtipo de PDU que carrega, na própria estrutura, a garantia da restrição R2
(o quadro nunca é reescrito).

Também é aqui que mora a garantia de R5 ("cada camada conversa só com a sua
par", seção 4.4): todo bloco de moldura registra em `Bloco.camada` o número
da camada que o inseriu, e `PDU.remover_cabecalho` — único caminho para tirar
um cabeçalho de uma PDU na subida — confere esse número contra a camada que
está removendo, levantando `CabecalhoAlheio` na divergência."""

import itertools
from dataclasses import dataclass, replace
from typing import Literal

TipoBloco = Literal["cabecalho", "dados", "finalizador"]


@dataclass(frozen=True)
class Bloco:
    rotulo: str
    tam: int
    tipo: TipoBloco
    conteudo: str | bytes | None = None

    # Número da camada que inseriu este bloco (restrição R5, issue #13).
    # Obrigatório em cabeçalho e finalizador: é o que a subida confere antes
    # de remover, para que uma camada só desencapsule o que a sua par (mesmo
    # número, no dispositivo oposto) encapsulou. O bloco de dados não
    # pertence a nenhuma camada — carrega sempre None.
    camada: int | None = None

    def __post_init__(self) -> None:
        if self.tipo == "dados":
            if self.camada is not None:
                raise ValueError(
                    f"bloco de dados {self.rotulo!r} não pertence a nenhuma camada: "
                    "o campo `camada` deve ficar None (R5)"
                )
        elif self.camada is None:
            raise ValueError(
                f"bloco {self.rotulo!r} ({self.tipo}) exige o número da camada que o "
                "inseriu, para a conferência de R5 na subida (issue #13)"
            )


class CabecalhoAlheio(RuntimeError):
    """Uma camada tentou remover, na subida, um cabeçalho ou finalizador que
    não foi inserido pela sua camada par.

    É a trava estrutural de R5 ("cada camada conversa só com a sua par",
    seção 4.4): todo bloco de moldura carrega o número da camada que o
    inseriu (`Bloco.camada`), e a remoção — `PDU.remover_cabecalho` ou a
    conferência explícita da camada 2 sobre o quadro — verifica esse número
    contra a camada que está removendo. Não é uma linha de verificação que
    se possa esquecer numa refatoração: está no caminho de código da
    remoção."""


def conferir_camada(bloco: Bloco, camada_removedora: int) -> None:
    """Confere (R5) que `bloco` foi inserido pela camada par da que agora o
    remove — mesma numeração, no dispositivo oposto — e levanta
    `CabecalhoAlheio` se não. Usada por `PDU.remover_cabecalho` e,
    diretamente, pela camada 2, que lê e retira cabeçalho e finalizador do
    quadro no mesmo passo."""
    if bloco.camada != camada_removedora:
        raise CabecalhoAlheio(
            f"camada {camada_removedora} tentou remover o bloco {bloco.rotulo!r}, "
            f"inserido pela camada {bloco.camada}"
        )


@dataclass
class PDU:
    # Tratada como retrato imutável: cada camada que transforma a PDU cria uma
    # nova instância (nova lista de blocos); nunca muta blocos em memória,
    # senão eventos já emitidos que referenciam esta PDU mudariam depois.
    nome: str
    blocos: list[Bloco]

    def tamanho(self) -> int:
        return sum(bloco.tam for bloco in self.blocos)

    def remover_cabecalho(self, camada: int) -> tuple[Bloco, "PDU"]:
        """Desencapsulamento conferido (R5, issue #13): remove o bloco do topo
        exigindo que tenha sido inserido pela camada par `camada`, e devolve
        `(bloco removido, PDU nova sem ele)`. Levanta `CabecalhoAlheio` na
        divergência.

        É o caminho que as camadas 3 a 5 usam em `subir()` no lugar de fatiar
        `blocos` à mão: a conferência do número de camada deixa de ser uma
        linha que se pode esquecer e passa a estar na estrutura — não há como
        tirar um cabeçalho sem conferi-lo."""
        if not self.blocos:
            raise ValueError("PDU sem blocos: nada a desencapsular")
        topo, *resto = self.blocos
        conferir_camada(topo, camada)
        return topo, PDU(nome=self.nome, blocos=resto)


# --- Camada 2: contador global de quadros e o tipo Quadro (restrição R2) ---
#
# R2 ("o quadro nunca é reescrito") é garantida aqui, pela estrutura, não pela
# disciplina de quem escreve a camada 2. As duas metades da restrição:
#
#   - o identificador (Q1, Q2, …) só nasce do contador de módulo abaixo, de
#     dentro de `Quadro.__init__` — não há parâmetro de id, logo não há como
#     reaproveitar `Q1` nem numerar por dispositivo;
#   - `Quadro.consumir()` torna o objeto inerte; a camada 2 o chama na subida
#     assim que extrai o pacote, então nenhum caminho de código consegue
#     reenviar o mesmo objeto quadro para o salto seguinte.

_PREFIXO_QUADRO = "Q"
_contador_quadros = itertools.count(1)


def reiniciar_contador_quadros() -> None:
    """Reinicia a numeração global de quadros (Q1, Q2, …) para uma nova
    execução de caso.

    Contador de módulo, nunca por dispositivo: R2 exige que os quadros de um
    caso formem uma sequência contínua sem repetição ao longo de toda a rota
    (C2 → exatamente {Q1, Q2, Q3, Q4}; C7 → Q1 a Q12) — dois dispositivos
    jamais podem colidir em Q1. `simulador.py` chama isto uma única vez antes
    de cada caso, nunca no meio de uma execução (nem entre os segmentos de
    C7). Mesmo motivo e mesmo padrão de `camadas.reiniciar_contador_sessoes`."""
    global _contador_quadros
    _contador_quadros = itertools.count(1)


def _proximo_id_quadro() -> str:
    """Próximo identificador do contador global. Único ponto do programa que o
    avança — chamado exatamente uma vez por `ENQUADRA`, de dentro de
    `Quadro.__init__`. `next()` sobre `itertools.count` é atômico sob o GIL,
    então dois enquadramentos nunca recebem o mesmo id."""
    return f"{_PREFIXO_QUADRO}{next(_contador_quadros)}"


class QuadroConsumido(RuntimeError):
    """Acesso ao conteúdo de um `Quadro` que a camada 2 já destruiu na subida.

    É a trava estrutural de R2: depois de `Quadro.consumir()`, ler `blocos`
    ou `tamanho()` — ou consumir de novo — levanta este erro. O quadro não
    sobrevive a uma travessia de camada 2 nem por engano nem por refatoração;
    quem precisar de um quadro para o próximo salto tem de construir um novo
    (id novo) via `CamadaEnlace.descer`."""


class Quadro(PDU):
    """PDU da camada 2 (`nome == "Quadro"`). Difere da PDU-base em dois pontos,
    cada um fechando metade de R2 pela estrutura:

    1. **Id novo, sempre.** `id` (Q1, Q2, …) é obtido no próprio `__init__`,
       do contador global deste módulo. Não há parâmetro de id: é impossível
       construir um `Quadro` reaproveitando um identificador.
    2. **Destruição na subida.** `consumir()` faz o objeto virar inerte —
       depois dele, `blocos`/`tamanho()` levantam `QuadroConsumido`. A camada 2
       chama `consumir()` em `subir()` assim que extrai o pacote.

    O conteúdo continua imutável como o de qualquer PDU (a lista de blocos
    nunca é mutada); a única transição de estado é a trava de consumo, de mão
    única.

    `copia_recebida()` é a única forma de haver dois objetos com o mesmo id, e
    existe só para o segmento de difusão: cada estação destrói a sua cópia na
    subida. Ver a docstring do método."""

    def __init__(self, blocos: list[Bloco]) -> None:
        self.nome = "Quadro"
        self.id = _proximo_id_quadro()
        self._blocos = list(blocos)
        self._consumido = False

    # Um quadro é um objeto físico único (identificado pelo id, não pelo
    # conteúdo): duas travessias nunca produzem "o mesmo quadro". Identidade,
    # não o `__eq__` estrutural que o dataclass PDU traria.
    __eq__ = object.__eq__
    __hash__ = object.__hash__

    # Troca o campo-dado `blocos` da PDU-base por um acesso protegido: depois
    # de consumido, o quadro não entrega mais o conteúdo a ninguém.
    @property
    def blocos(self) -> list[Bloco]:  # type: ignore[override]
        if self._consumido:
            raise QuadroConsumido(
                f"quadro {self.id} foi destruído pela camada 2 na subida (R2); "
                "o próximo salto tem de enquadrar um quadro novo"
            )
        # Cópia defensiva: quem recebe não deve conseguir mutar o quadro em
        # memória por fora — o quadro só muda pelas vias que R2 permite
        # (`copia_recebida`, `com_bit_invertido`), nunca por um `append`/
        # atribuição de índice alheio na lista devolvida aqui.
        return list(self._blocos)

    def consumir(self) -> None:
        """Destrói o quadro. A camada 2 chama isto na subida logo após extrair
        o pacote. Consumir duas vezes é bug de fluxo, não operação idempotente
        — levanta `QuadroConsumido`."""
        if self._consumido:
            raise QuadroConsumido(f"quadro {self.id} já havia sido consumido")
        self._consumido = True

    def copia_recebida(self) -> "Quadro":
        """A cópia deste quadro tal como chega a **outra** estação do mesmo
        segmento de difusão: blocos idênticos, **mesmo identificador**, objeto
        próprio.

        Num segmento de difusão o quadro chega a todas as estações (issue #10)
        e cada uma o processa na sua camada 2 — que o destrói (`consumir`).
        Um único objeto não sobreviveria à segunda estação, e construir um
        `Quadro` novo tiraria um identificador novo do contador global,
        quebrando a contagem que R2 exige (C2 → exatamente {Q1..Q4}). As
        cópias são a mesma transmissão vista em pontas diferentes, não quadros
        novos, e por isso compartilham o `id`.

        Isto **não** afrouxa R2: a cópia nasce de um quadro vivo e já montado,
        nunca de um pacote — encaminhar exige `CamadaEnlace.descer`, que só
        sabe construir um `Quadro` novo, com id novo. Copiar um quadro já
        consumido levanta `QuadroConsumido`, pelo acesso a `blocos`.

        Quem faz a cópia é `dispositivos.py`, ao pôr o quadro no enlace —
        uma por estação do segmento além do destinatário."""
        return self._com_blocos(self.blocos)

    def _com_blocos(self, blocos: list["Bloco"]) -> "Quadro":
        """Um `Quadro` novo, mesmo `nome`/`id`, outra lista de blocos —
        o miolo comum de `copia_recebida` e `com_bit_invertido`. Ambas
        contornam `__init__` de propósito: um id novo do contador global
        aqui quebraria a contagem que R2 exige (a cópia/corrupção é o
        mesmo quadro visto em outro ponto, não um quadro novo)."""
        quadro = object.__new__(Quadro)  # sem __init__: o id não é renumerado
        quadro.nome = self.nome
        quadro.id = self.id
        quadro._blocos = blocos
        quadro._consumido = False
        return quadro

    def com_bit_invertido(self, bit: int) -> "Quadro":
        """Este mesmo quadro depois de um bit ser invertido no enlace (C6).

        Mesmo identificador, pelo mesmo motivo de `copia_recebida`: o que
        atravessou o cabo continua sendo o quadro Q3, e o registro o nomeia dos
        dois lados da corrupção. Objeto novo porque a PDU é imutável.

        O bit é contado **dentro do bloco de dados**, a única parte do quadro
        cujo conteúdo é octeto de verdade: cabeçalho e finalizador carregam
        texto simbólico (seção 1.2, "os cabeçalhos têm conteúdo simbólico"), e
        inverter um bit ali corromperia uma representação, não uma
        transmissão. A posição é reduzida ao tamanho dos dados, de modo que
        qualquer valor declarado no arquivo aponte para um bit existente — o
        `bit: 100` de C6 cai no quinto bit do décimo terceiro octeto da
        mensagem.

        Nada aqui sabe o que é CRC: a divergência é consequência, e quem a
        descobre é a camada 2 do próximo nó, recalculando (decisão D3)."""
        blocos = self.blocos  # já uma cópia nova (a property nunca devolve a viva)
        posicao = next(
            (i for i, b in enumerate(blocos) if b.tipo == "dados"), None
        )
        if posicao is None:  # pragma: no cover — todo quadro carrega dados
            raise ValueError(f"quadro {self.id} não tem bloco de dados a corromper")

        dados = blocos[posicao].conteudo
        if not isinstance(dados, bytes) or not dados:  # pragma: no cover
            raise ValueError(f"quadro {self.id} tem bloco de dados vazio")

        alvo = bit % (len(dados) * 8)
        octetos = bytearray(dados)
        octetos[alvo // 8] ^= 1 << (7 - alvo % 8)
        blocos[posicao] = replace(blocos[posicao], conteudo=bytes(octetos))

        return self._com_blocos(blocos)

    def __repr__(self) -> str:
        estado = "consumido" if self._consumido else f"{len(self._blocos)} blocos"
        return f"Quadro(id={self.id!r}, {estado})"
