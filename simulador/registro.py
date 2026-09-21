"""Eventos do registro e sua formatacao oficial.

As camadas apenas produzem eventos; este modulo e o unico que os transforma
em texto. Cada evento vira uma linha no formato do enunciado:

    NNN | DISP | LN | ACAO | descricao<espacos>TAM B

O passo tem tres digitos com zeros a esquerda e o tamanho fica alinhado a
direita, no fim da linha, para que a coluna de octetos possa ser lida de
cima a baixo.
"""

from dataclasses import dataclass

# Nomes de acao do registro, conforme o enunciado.
ACOES = frozenset({
    "GERA", "CODIFICA", "ABRE", "SEGMENTA", "ENCAPSULA", "ROTEIA", "ENQUADRA",
    "TRANSMITE", "RECEBE", "DESENQUADRA", "DESCARTA", "REMONTA", "DECIFRA",
    "ENTREGA",
})

# Coluna em que termina o "TAM B". Descricoes mais longas empurram o
# tamanho para a direita, sempre com ao menos um espaco antes dele.
LARGURA_DA_LINHA = 108


@dataclass(frozen=True)
class Evento:
    """Uma linha do registro: o que uma camada fez em um dispositivo."""

    passo: int
    dispositivo: str
    camada: int
    acao: str
    descricao: str
    tamanho: int


def formatar(evento):
    """Devolve a linha oficial de um evento."""
    inicio = (
        f"{evento.passo:03d} | {evento.dispositivo} | L{evento.camada} | "
        f"{evento.acao} | {evento.descricao}"
    )
    fim = f"{evento.tamanho} B"
    espacos = max(1, LARGURA_DA_LINHA - len(inicio) - len(fim))
    return inicio + " " * espacos + fim


class Registro:
    """Acumula os eventos de uma simulacao, na ordem em que ocorreram."""

    def __init__(self, eventos=()):
        self.eventos = list(eventos)

    def registrar(self, eventos):
        self.eventos.extend(eventos)

    def linhas(self):
        return [formatar(evento) for evento in self.eventos]

    def __str__(self):
        return "\n".join(self.linhas())

    def salvar_em_arquivo(self, caminho):
        """Grava o registro formatado, uma linha por evento, em UTF-8."""
        with open(caminho, "w", encoding="utf-8") as arquivo:
            for linha in self.linhas():
                arquivo.write(linha + "\n")
