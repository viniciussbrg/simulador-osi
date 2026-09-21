"""Os sete casos obrigatorios do enunciado.

O enunciado nomeia os casos de C1 a C7 e os criterios de avaliacao os chamam de
E1 a E7. Sao o mesmo conjunto: cada cenario guarda os dois rotulos e a
interface exibe ambos, para que quem avalia encontre o nome que procura.

Os textos das mensagens tem tamanho fixado de proposito: 42 octetos no caso
central, que produz a eficiencia de 11,4% citada na documentacao, e 100 octetos
no caso da mensagem longa, que produz os tres segmentos de 40, 40 e 24 octetos
exigidos nos criterios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: Mensagem do caso central: 42 octetos em UTF-8.
MENSAGEM_PADRAO = "GET /index.html HTTP/1.1 Host: servidorweb"

#: Mensagem longa: 100 octetos em UTF-8, acima do limite de segmentacao.
MENSAGEM_LONGA = (
    "GET /catalogo/produtos?pagina=10 HTTP/1.1 Host: servidorweb "
    "Accept: text/html Connection: keep-alive"
)


@dataclass(frozen=True)
class Fluxo:
    """Uma comunicacao entre dois processos."""

    origem: str
    destino_logico: str
    processo_origem: str = "navegador"
    processo_destino: str = "servidorWeb"
    porta_origem: int = 5210
    porta_destino: int = 443
    texto: str = MENSAGEM_PADRAO

    @property
    def octetos(self) -> int:
        return len(self.texto.encode("utf-8"))

    @property
    def identificacao(self) -> str:
        return f"{self.origem}:{self.porta_origem}->{self.destino_logico}:{self.porta_destino}"


@dataclass(frozen=True)
class Cenario:
    """Um caso de validacao selecionavel pela interface."""

    codigo: str
    rotulo: str
    titulo: str
    descricao: str
    fluxos: Tuple[Fluxo, ...]
    enlace_derrubado: Optional[str] = None
    erro_de_bit: Optional[str] = None
    esperado: Dict[str, object] = field(default_factory=dict)

    @property
    def nome_exibicao(self) -> str:
        return f"{self.rotulo}/{self.codigo} - {self.titulo}"


def cenarios_padrao() -> List[Cenario]:
    """Devolve os sete cenarios obrigatorios, na ordem do enunciado."""
    return [
        Cenario(
            codigo="C1",
            rotulo="E1",
            titulo="Entrega direta",
            descricao=(
                "H1 envia para H2. Ambos estao na Rede A. A camada 3 reconhece que o "
                "destino compartilha o prefixo de rede e entrega sem roteador. Ha um "
                "unico quadro."
            ),
            fluxos=(Fluxo(origem="H1", destino_logico="10.0.1.11"),),
            esperado={
                "quadros": 1,
                "octetos_transmitidos": 92,
                "eficiencia": "45.7%",
                "roteadores": 0,
            },
        ),
        Cenario(
            codigo="C2",
            rotulo="E2",
            titulo="Entrega indireta (caso central)",
            descricao=(
                "O processo navegador, porta 5210, em H1, envia para o processo "
                "servidorWeb, porta 443, em H4. Tres roteadores, quatro quadros, um "
                "unico pacote pelo caminho de menor custo R1, R4, R3."
            ),
            fluxos=(Fluxo(origem="H1", destino_logico="10.0.3.10"),),
            esperado={
                "quadros": 4,
                "octetos_transmitidos": 368,
                "eficiencia": "11.4%",
                "caminho": ["R1", "R4", "R3"],
            },
        ),
        Cenario(
            codigo="C3",
            rotulo="E3",
            titulo="Demultiplexacao",
            descricao=(
                "H1 e H2 enviam simultaneamente para o mesmo servidorWeb em H4, com "
                "portas de origem distintas. A camada 4 de H4 separa os dois fluxos e "
                "entrega cada um a sessao correta."
            ),
            fluxos=(
                Fluxo(origem="H1", destino_logico="10.0.3.10", porta_origem=5210),
                Fluxo(origem="H2", destino_logico="10.0.3.10", porta_origem=5211),
            ),
            esperado={"quadros": 8, "fluxos": 2, "octetos_transmitidos": 736},
        ),
        Cenario(
            codigo="C4",
            rotulo="E4",
            titulo="Falha de enlace",
            descricao=(
                "O enlace R1-R4 e derrubado pela interface. A mensagem de H1 para H4 "
                "passa a seguir por R2, com custo total 3, e o mapa reflete o novo "
                "caminho."
            ),
            fluxos=(Fluxo(origem="H1", destino_logico="10.0.3.10"),),
            enlace_derrubado="Enlace R1-R4",
            esperado={
                "quadros": 4,
                "octetos_transmitidos": 368,
                "eficiencia": "11.4%",
                "caminho": ["R1", "R2", "R3"],
                "custo": 3,
            },
        ),
        Cenario(
            codigo="C5",
            rotulo="E5",
            titulo="Destino inalcancavel",
            descricao=(
                "H1 envia para 10.0.9.10, endereco que nao pertence a nenhuma rede da "
                "topologia. O pacote e descartado na camada 3 do primeiro roteador que "
                "nao encontra rota, com registro explicito do descarte."
            ),
            fluxos=(Fluxo(origem="H1", destino_logico="10.0.9.10"),),
            esperado={
                "quadros": 1,
                "octetos_transmitidos": 92,
                "descarte_em": "R1",
                "camada_do_descarte": 3,
            },
        ),
        Cenario(
            codigo="C6",
            rotulo="E6",
            titulo="Erro de transmissao",
            descricao=(
                "Durante o caso C2, um bit do quadro e alterado no enlace R4-R3. A "
                "camada 2 do receptor detecta a inconsistencia pela verificacao de "
                "erro, descarta o quadro e registra o descarte, sem acionar nenhuma "
                "camada superior."
            ),
            fluxos=(Fluxo(origem="H1", destino_logico="10.0.3.10"),),
            erro_de_bit="Enlace R3-R4",
            esperado={
                "quadros": 3,
                "octetos_transmitidos": 276,
                "descarte_em": "R3",
                "camada_do_descarte": 2,
                "sem_camada_3_em": "R3",
            },
        ),
        Cenario(
            codigo="C7",
            rotulo="E7",
            titulo="Mensagem longa",
            descricao=(
                "H1 envia para H4 uma mensagem que excede o limite adotado na camada 4 "
                "e e dividida em tres segmentos. Cada segmento percorre a rede por "
                "conta propria, e a camada 4 de H4 so entrega a mensagem a camada 5 "
                "depois de remontar todos eles na ordem correta."
            ),
            fluxos=(
                Fluxo(origem="H1", destino_logico="10.0.3.10", texto=MENSAGEM_LONGA),
            ),
            esperado={
                "segmentos": [40, 40, 24],
                "quadros": 12,
                "octetos_transmitidos": 968,
                "eficiencia": "10.3%",
            },
        ),
    ]


def por_codigo(codigo: str) -> Cenario:
    """Procura um cenario pelo codigo (C1..C7) ou pelo rotulo (E1..E7)."""
    alvo = codigo.strip().upper()
    for cenario in cenarios_padrao():
        if alvo in (cenario.codigo, cenario.rotulo):
            return cenario
    raise KeyError(f"cenario desconhecido: {codigo}")
