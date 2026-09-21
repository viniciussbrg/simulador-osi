from dataclasses import dataclass, asdict

@dataclass
class Evento:
    passo: int
    dispositivo: str
    camada: int
    acao: str
    descricao: str
    tamanho: int
    unidade: str = ""
    logicos: tuple | None = None
    fisicos: tuple | None = None
    quadro: str | None = None
    caminho: list | None = None
    pdu_blocos: list | None = None

    def linha(self):
        return f"{self.passo:03d} | {self.dispositivo} | L{self.camada} | {self.acao} | {self.descricao} {self.tamanho} B"

    def dict(self):
        return asdict(self)

class BarramentoEventos:
    def __init__(self):
        self.eventos = []
        self._passo = 0

    def limpar(self):
        self.eventos.clear()
        self._passo = 0

    def emitir(self, dispositivo, camada, acao, descricao, pdu=None, tamanho=None, caminho=None):
        self._passo += 1
        if tamanho is None:
            tamanho = pdu.tamanho_atual() if pdu else 0
        ev = Evento(
            self._passo, dispositivo, camada, acao, descricao, tamanho,
            getattr(pdu, "unidade", "") if pdu else "",
            getattr(pdu, "logicos", None) if pdu else None,
            getattr(pdu, "fisicos", None) if pdu else None,
            getattr(pdu, "quadro_id", None) if pdu else None,
            list(caminho) if caminho else None,
            pdu.blocos_visuais() if pdu else None,
        )
        self.eventos.append(ev)
        return ev
