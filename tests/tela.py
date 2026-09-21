"""A tela de mentira: o mínimo de `Canvas` que as regiões da interface usam.

Mora aqui, e não dentro de um arquivo de teste, porque V1 a V4 (issues #48 a
#51) desenham cada um na sua região da mesma tela e todos precisam do mesmo
instrumento. Anotar em vez de desenhar é o que permite afirmar coisas sobre o
desenho — "há quatro círculos de custo", "a caixa da camada 2 de H1 está azul
sólido", "nada foi desenhado fora da tela" — sem display nenhum, que é a regra
da seção 13.1 valendo também para a interface.

Um `Canvas` de verdade responderia ao mesmo (`find_withtag`, `itemcget`), e é
por isso que cada arquivo de teste repete uma parte contra um `Canvas` real,
pulando quando não há tela: é o que garante que os nomes de opção usados
(`dash`, `anchor`, `outline`, `width`) são os que o tkinter aceita, e não uma
invenção que só a tela de mentira engole.
"""

LARGURA = 790  # os ~62% de 1280 que o Anexo C reserva ao mapa
ALTURA = 340


class Item:
    """Uma figura que a região mandou desenhar, com o que mandou junto."""

    def __init__(self, tipo, coordenadas, opcoes):
        self.tipo = tipo
        self.coordenadas = coordenadas
        self.opcoes = opcoes
        self.tags = tuple(opcoes.get("tags", ()))

    def tem(self, etiqueta: str) -> bool:
        return etiqueta in self.tags

    def __repr__(self):  # pragma: no cover — só aparece em falha
        return f"<{self.tipo} {self.tags} {self.opcoes.get('fill', '')}>"


class TelaDeMentira:
    """Guarda o que foi pedido, no lugar de pintar pixel."""

    def __init__(self, largura=LARGURA, altura=ALTURA):
        self.largura = largura
        self.altura = altura
        self.itens: list[Item] = []
        self.apagou: list[str] = []

    # — a parte que imita o Canvas ——————————————————————————————————————

    def winfo_width(self):
        return self.largura

    def winfo_height(self):
        return self.altura

    def delete(self, etiqueta):
        self.apagou.append(etiqueta)
        self.itens = [item for item in self.itens if not item.tem(etiqueta)]

    def create_line(self, *coordenadas, **opcoes):
        return self._criar("line", coordenadas, opcoes)

    def create_oval(self, *coordenadas, **opcoes):
        return self._criar("oval", coordenadas, opcoes)

    def create_rectangle(self, *coordenadas, **opcoes):
        return self._criar("rect", coordenadas, opcoes)

    def create_text(self, *coordenadas, **opcoes):
        return self._criar("text", coordenadas, opcoes)

    def _criar(self, tipo, coordenadas, opcoes):
        self.itens.append(Item(tipo, coordenadas, opcoes))
        return len(self.itens)

    # — a parte que o teste usa ————————————————————————————————————————

    def com(self, *etiquetas) -> list[Item]:
        return [
            item for item in self.itens if all(item.tem(alvo) for alvo in etiquetas)
        ]

    def textos(self) -> list[str]:
        return [
            item.opcoes.get("text", "") for item in self.itens if item.tipo == "text"
        ]

    def do_enlace(self, identificador: str) -> list[Item]:
        return self.com(f"enlace:{identificador}")
