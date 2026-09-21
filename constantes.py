"""Vocabulário fechado de ações do contrato de evento (proposta técnica, seção 7.4).

Fonte única da verdade: nenhum código deve emitir uma string de ação que não
esteja listada aqui. Ação nova exige atualizar este arquivo E a seção 7.4 da
proposta técnica — nunca só um dos dois (issue #1).
"""

from typing import Literal

AcaoL7 = Literal["GERA", "ENTREGA"]
AcaoL6 = Literal["CODIFICA", "DECIFRA"]
AcaoL5 = Literal["ABRE", "ENCERRA"]
AcaoL4 = Literal["SEGMENTA", "DEMULTIPLEXA", "REMONTA"]
AcaoL3 = Literal["ENCAPSULA", "ROTEIA", "DESENCAPSULA", "DESCARTA"]
AcaoL2 = Literal["ENQUADRA", "DESENQUADRA", "DESCARTA", "IGNORA"]
AcaoL1 = Literal["TRANSMITE", "RECEBE"]
AcaoSistema = Literal["CORROMPE", "ENLACE_FORA", "METRICAS"]

# Tipo do campo Evento.acao — união de todas as camadas + sistema.
Acao = AcaoL7 | AcaoL6 | AcaoL5 | AcaoL4 | AcaoL3 | AcaoL2 | AcaoL1 | AcaoSistema

# Vocabulário por camada (0 = sistema), para validação estrutural
# (ex.: T-VOC — "toda ação pertence ao vocabulário da camada que a emitiu").
ACOES_POR_CAMADA: dict[int, frozenset[str]] = {
    7: frozenset(("GERA", "ENTREGA")),
    6: frozenset(("CODIFICA", "DECIFRA")),
    5: frozenset(("ABRE", "ENCERRA")),
    4: frozenset(("SEGMENTA", "DEMULTIPLEXA", "REMONTA")),
    3: frozenset(("ENCAPSULA", "ROTEIA", "DESENCAPSULA", "DESCARTA")),
    2: frozenset(("ENQUADRA", "DESENQUADRA", "DESCARTA", "IGNORA")),
    1: frozenset(("TRANSMITE", "RECEBE")),
    0: frozenset(("CORROMPE", "ENLACE_FORA", "METRICAS")),
}

ACOES_VALIDAS: frozenset[str] = frozenset().union(*ACOES_POR_CAMADA.values())

# IGNORA (L2): estação do segmento de difusão que descarta por endereço não
# coincidente — emitida com Evento.secundario = True (seção 7.5), oculta por
# padrão no registro.
ACOES_SECUNDARIAS: frozenset[str] = frozenset(("IGNORA",))
