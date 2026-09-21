"""Estrutura imutável de Evento e formatação do registro (linha())."""

from dataclasses import dataclass
from typing import Literal

from constantes import Acao

# Coluna em que o número de octetos termina, e separação mínima entre ele e a
# descrição (seção 8.1). Os 77 saem do Anexo B: com o sufixo " B", a linha
# fecha em 79 colunas, que é o que cabe num terminal de 80 sem dobrar.
_COLUNA_TAMANHO = 77
_ESPACOS_MINIMOS = 2

Sentido = Literal["desce", "sobe", "meio"]
Estado = Literal["ok", "descartado", "erro"]
TipoBlocoEvento = Literal["cabecalho", "dados", "finalizador"]


@dataclass(frozen=True)
class BlocoEvento:
    rotulo: str
    tam: int
    tipo: TipoBlocoEvento
    conteudo: str | bytes | None = None


@dataclass(frozen=True)
class PduInfo:
    nome: str
    blocos: tuple[BlocoEvento, ...]


@dataclass(frozen=True)
class Logico:
    origem: str
    destino: str


@dataclass(frozen=True)
class Fisico:
    origem: str | None = None
    destino: str | None = None


@dataclass(frozen=True)
class Enlace:
    id: str
    rotulo: str


@dataclass(frozen=True)
class Intervencao:
    """O que a tela pede ao motor quando alguém derruba um enlace ou injeta
    um erro (issue #56).

    É o primeiro dado do contrato que viaja da interface **para** o motor —
    até aqui tudo ia na direção oposta, e é por isso que ele merece uma nota.
    Mora em `evento.py` pelo mesmo motivo que o `Evento`: esta é a fronteira
    que os dois lados podem importar, e `visual.py` não pode conhecer o
    `EventoExterno` de `rede.py`. Quem traduz uma coisa na outra é o `app.py`.

    `quadro` e `bit` só valem para `erro_bit`; `enlace_fora` os deixa nulos."""

    tipo: str
    enlace: str
    quadro: str | None = None
    bit: int | None = None


@dataclass(frozen=True)
class Porta:
    origem: int
    destino: int


@dataclass(frozen=True)
class Segmento:
    n: int
    total: int


@dataclass(frozen=True)
class Processo:
    origem: str
    destino: str


@dataclass(frozen=True)
class Metricas:
    # `dados_uteis` é o que a camada 7 gerou, contado uma vez (seção 11.1);
    # `dados_entregues` é quanto disso chegou ao destino. Os dois só diferem
    # quando a mensagem morre no caminho — sem rota (C5) ou com verificação
    # reprovada (C6) —, e é dessa diferença que sai o η = 0% da tabela 11.3:
    # a eficiência mede o que chegou, não o que partiu. Sem o segundo campo, a
    # interface teria de adivinhar se um η zerado é "não entregue" ou
    # arredondamento.
    dados_uteis: int
    dados_entregues: int
    total_transmitido: int
    eta: float
    sobrecarga: float
    enlaces_percorridos: int
    quadros_construidos: int
    comparacao: dict[str, float]


@dataclass(frozen=True)
class Evento:
    # Identificação — sempre presentes, sem default
    passo: int
    dispositivo: str
    camada: int
    acao: Acao
    descricao: str

    # Contexto de execução
    tamanho: int | None = None  # None só nos eventos de sistema (camada 0)
    fluxo: str | None = None
    sentido: Sentido | None = None
    estado: Estado = "ok"
    secundario: bool = False

    # Composição da PDU
    pdu: PduInfo | None = None

    # Endereços
    logico: Logico | None = None
    fisico: Fisico | None = None

    # Contexto de enlace
    enlace: Enlace | None = None
    quadro: str | None = None
    bits: int | None = None
    caminho: tuple[str, ...] = ()

    # Contexto superior — só computadores
    porta: Porta | None = None
    sessao: str | None = None
    segmento: Segmento | None = None
    processo: Processo | None = None

    # Evento final de métricas
    metricas: Metricas | None = None

    def linha(self) -> str:
        """A linha do registro, na gramática da seção 8.1:

            NNN | DISP | LN | ACAO | descrição livre              TTT B

        O tamanho fecha na coluna `_COLUNA_TAMANHO`, e não a uma distância
        fixa do fim da descrição: os campos que vêm antes têm largura variável
        (`GERA` e `DESENQUADRA` não medem o mesmo), de modo que só a coluna
        absoluta deixa a pilha de octetos legível em fonte monoespaçada, na
        tela e no arquivo salvo. É o alinhamento do Anexo B, conferido
        caractere a caractere por T-FMT (issue #34).

        Descrição que passa da coluna não é truncada — o registro existe para
        ser lido, e cortar a descrição esconderia justamente o evento mais
        informativo. Ela empurra o tamanho para a direita, guardado o mínimo
        de `_ESPACOS_MINIMOS` espaços de separação (linha 010 do Anexo B)."""
        campo_camada = "--" if self.camada == 0 else f"L{self.camada}"
        base = " | ".join([
            f"{self.passo:03d}",
            self.dispositivo,
            campo_camada,
            self.acao,
            self.descricao,
        ])
        if self.tamanho is None:
            return base
        octetos = str(self.tamanho)
        espacos = max(
            _COLUNA_TAMANHO - len(base) - len(octetos), _ESPACOS_MINIMOS
        )
        return f"{base}{' ' * espacos}{octetos} B"
