"""Substituto minimo de tkinter, para exercitar a interface sem display.

O container de desenvolvimento nao tem servidor grafico, entao `visual.py` nao
pode ser aberto de verdade durante a conferencia. Este modulo instala um
tkinter falso que aceita as mesmas chamadas e devolve valores plausiveis, o que
permite instanciar a janela, percorrer todos os passos de todos os cenarios e
acionar os botoes. Erros de logica (chave inexistente, indice fora da faixa,
formatacao invalida) aparecem normalmente; apenas o desenho nao acontece.

Nao faz parte do programa entregue: e uma ferramenta de conferencia.

Uso:

    python ferramentas/conferir_interface.py
"""

from __future__ import annotations

import os
import sys
import types

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# -- objetos falsos --------------------------------------------------------


class _Widget:
    """Aceita qualquer configuracao e qualquer metodo de geometria."""

    def __init__(self, master=None, **opcoes):
        self.master = master
        self.opcoes = dict(opcoes)
        self.filhos = []
        if isinstance(master, _Widget):
            master.filhos.append(self)

    # geometria e configuracao
    def grid(self, **_):
        return self

    def pack(self, **_):
        return self

    def place(self, **_):
        return self

    def configure(self, **opcoes):
        self.opcoes.update(opcoes)
        return self

    config = configure

    def cget(self, chave):
        return self.opcoes.get(chave, "")

    def __setitem__(self, chave, valor):
        self.opcoes[chave] = valor

    def __getitem__(self, chave):
        return self.opcoes.get(chave, "")

    def columnconfigure(self, *a, **k):
        return self

    def rowconfigure(self, *a, **k):
        return self

    def bind(self, *a, **k):
        return self

    def bind_all(self, *a, **k):
        return self

    def focus_set(self):
        return self

    def destroy(self):
        return self

    def update_idletasks(self):
        return self

    def winfo_width(self):
        return 520

    def winfo_height(self):
        return 420

    def winfo_reqwidth(self):
        return 120

    def winfo_reqheight(self):
        return 32

    def winfo_containing(self, *_):
        return None

    def after_idle(self, funcao, *args):
        """Agendamentos ociosos so registram a chamada: nao ha laco de eventos."""
        return "idle"

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def tag_configure(self, *a, **k):
        return self

    tag_config = tag_configure

    def tag_add(self, *a, **k):
        return self

    def tag_remove(self, *a, **k):
        return self

    #: Nomes que o tkinter real expõe e que o simulador pode chamar sem que
    #: a conferência precise conhecê-los um a um.
    _TOLERADOS = (
        "winfo_", "wm_", "grid_", "pack_", "place_", "event_", "focus_",
        "attributes", "unbind", "lift", "lower", "itemconfig", "coords",
        "scale", "move", "identify",
    )

    def __getattr__(self, nome):
        # Atributos privados continuam falhando: é assim que erros reais do
        # simulador (campo não inicializado, por exemplo) aparecem.
        if nome.startswith("_") or not nome.startswith(self._TOLERADOS):
            raise AttributeError(nome)
        return lambda *a, **k: None

    def winfo_exists(self):
        return True

    def winfo_children(self):
        return list(self.filhos)

    def set(self, *_):
        """Barras de rolagem recebem `set` do widget que controlam."""
        return None

    def get(self, *_):
        return 0.0

    def state(self, *_):
        return ()

    def instate(self, *_):
        return True

    def add(self, *a, **k):
        """Usado pelo caderno de abas das tabelas de encaminhamento."""
        return None

    def insert(self, *a, **k):
        return None

    def heading(self, *a, **k):
        return None

    def column(self, *a, **k):
        return None

    def yview(self, *a, **k):
        return None

    def xview(self, *a, **k):
        return None

    def yview_moveto(self, *a, **k):
        return None

    def xview_moveto(self, *a, **k):
        return None


class _Canvas(_Widget):
    def __init__(self, master=None, **opcoes):
        super().__init__(master, **opcoes)
        self.itens = []

    def _criar(self, tipo, args, opcoes):
        self.itens.append((tipo, args, opcoes))
        return len(self.itens)

    def create_line(self, *a, **k):
        return self._criar("linha", a, k)

    def create_rectangle(self, *a, **k):
        return self._criar("retangulo", a, k)

    def create_oval(self, *a, **k):
        return self._criar("oval", a, k)

    def create_polygon(self, *a, **k):
        return self._criar("poligono", a, k)

    def create_text(self, *a, **k):
        return self._criar("texto", a, k)

    def delete(self, *_):
        self.itens.clear()

    def create_window(self, *a, **k):
        return self._criar("janela", a, k)

    def bbox(self, *_):
        return (0, 0, 520, 420)

    def yview(self, *a, **k):
        return None

    def xview(self, *a, **k):
        return None


class _Text(_Widget):
    def __init__(self, master=None, **opcoes):
        super().__init__(master, **opcoes)
        self.conteudo = ""
        self.marcas = []

    def insert(self, _indice, texto, *tags):
        self.conteudo += texto
        if tags:
            self.marcas.append((texto, tags))

    def delete(self, *_):
        self.conteudo = ""
        self.marcas.clear()

    def get(self, *_):
        return self.conteudo

    def tag_configure(self, *a, **k):
        return self

    tag_config = tag_configure

    def tag_add(self, *a, **k):
        return self

    def tag_remove(self, *a, **k):
        return self

    def see(self, *_):
        return self

    def yview(self, *a, **k):
        return None

    def xview(self, *a, **k):
        return None

    def index(self, *_):
        return "1.0"


class _Fonte:
    """Medidor de texto: largura proporcional ao numero de caracteres."""

    def __init__(self, *a, **k):
        self.opcoes = k

    def measure(self, texto, *_):
        return 7 * len(str(texto))


class _Variavel:
    def __init__(self, master=None, value=None, **_):
        self._valor = value if value is not None else self.padrao
        self._observadores = []

    def get(self):
        return self._valor

    def set(self, valor):
        self._valor = valor
        for observador in self._observadores:
            observador()

    def trace_add(self, _modo, funcao):
        self._observadores.append(funcao)
        return f"trace{len(self._observadores)}"

    trace = trace_add

    def trace_remove(self, *_):
        return None


class _TextoVar(_Variavel):
    padrao = ""


class _InteiroVar(_Variavel):
    padrao = 0


class _BooleanoVar(_Variavel):
    padrao = False


class _Combobox(_Widget):
    def __init__(self, master=None, **opcoes):
        super().__init__(master, **opcoes)
        self._indice = 0

    def current(self, indice=None):
        if indice is None:
            return self._indice
        self._indice = indice
        valores = self.opcoes.get("values") or []
        variavel = self.opcoes.get("textvariable")
        if variavel is not None and indice < len(valores):
            variavel.set(valores[indice])
        return None

    def set(self, valor):
        variavel = self.opcoes.get("textvariable")
        if variavel is not None:
            variavel.set(valor)


class _Janela(_Widget):
    """Raiz da aplicacao e janelas secundarias."""

    def __init__(self, *a, **k):
        super().__init__(None)
        self.tarefas = []

    def title(self, *_):
        return self

    def geometry(self, *_):
        return self

    def minsize(self, *_):
        return self

    def resizable(self, *_):
        return self

    def transient(self, *_):
        return self

    def grab_set(self):
        return self

    def protocol(self, *_):
        return self

    def option_add(self, *_):
        return self

    def withdraw(self):
        return self

    def deiconify(self):
        return self

    def mainloop(self):
        return None

    def after(self, _ms, funcao=None, *args):
        self.tarefas.append((funcao, args))
        return len(self.tarefas)

    def after_cancel(self, *_):
        return None


class _Estilo:
    def __init__(self, *a, **k):
        self.configuracoes = {}

    def theme_use(self, *_):
        return None

    def theme_names(self):
        return ["clam", "default"]

    def configure(self, nome, **opcoes):
        self.configuracoes.setdefault(nome, {}).update(opcoes)

    def map(self, *a, **k):
        return None

    def layout(self, *a, **k):
        return None


def _instalar() -> None:
    tk = types.ModuleType("tkinter")
    for nome in (
        "Frame",
        "Label",
        "Button",
        "Entry",
        "Listbox",
        "Scrollbar",
        "Scale",
        "Toplevel",
        "PanedWindow",
        "LabelFrame",
        "Menu",
        "Spinbox",
        "Checkbutton",
        "Radiobutton",
    ):
        setattr(tk, nome, _Janela if nome == "Toplevel" else _Widget)
    tk.Tk = _Janela
    tk.Canvas = _Canvas
    tk.Text = _Text
    tk.StringVar = _TextoVar
    tk.IntVar = _InteiroVar
    tk.DoubleVar = _InteiroVar
    tk.BooleanVar = _BooleanoVar
    tk.TclError = Exception
    for constante in ("END", "N", "S", "E", "W", "NW", "SE", "LEFT", "RIGHT", "BOTH", "X", "Y"):
        setattr(tk, constante, constante.lower())

    ttk = types.ModuleType("tkinter.ttk")
    for nome in (
        "Frame",
        "Label",
        "Button",
        "Entry",
        "Labelframe",
        "LabelFrame",
        "Scrollbar",
        "Separator",
        "Progressbar",
        "Notebook",
        "Radiobutton",
        "Checkbutton",
        "Scale",
        "Treeview",
    ):
        setattr(ttk, nome, _Widget)
    ttk.Combobox = _Combobox
    ttk.Style = _Estilo
    tk.ttk = ttk

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.askopenfilename = lambda **_: ""
    filedialog.asksaveasfilename = lambda **_: ""

    messagebox = types.ModuleType("tkinter.messagebox")
    registro = []
    for nome in ("showerror", "showwarning", "showinfo"):
        setattr(messagebox, nome, lambda *a, **k: registro.append(a))
    messagebox.askyesno = lambda *a, **k: True
    messagebox.registro = registro

    tk.filedialog = filedialog
    tk.messagebox = messagebox

    fonte = types.ModuleType("tkinter.font")
    fonte.families = lambda *a, **k: (
        "Segoe UI", "Consolas", "DejaVu Sans", "DejaVu Sans Mono",
    )
    fonte.nametofont = lambda *a, **k: _Widget()
    fonte.Font = _Fonte
    tk.font = fonte
    tk.Misc = _Widget
    tk.Widget = _Widget

    sys.modules.update(
        {
            "tkinter": tk,
            "tkinter.ttk": ttk,
            "tkinter.font": fonte,
            "tkinter.filedialog": filedialog,
            "tkinter.messagebox": messagebox,
        }
    )


def conferir() -> int:
    _instalar()
    sys.path.insert(0, RAIZ)
    from tkinter import messagebox  # o falso, ja instalado

    from simulador.cenarios import cenarios_padrao
    from simulador.visual import AplicacaoSimulador

    janela = AplicacaoSimulador(os.path.join(RAIZ, "topologia.json"))
    print("janela construida")

    for indice, cenario in enumerate(cenarios_padrao()):
        janela._combo_cenario.current(indice)
        janela._carregar_cenario()
        total = len(janela._resultado.eventos) if janela._resultado else 0
        for _ in range(total + 3):  # tres passos alem do fim, de proposito
            janela._passo()
        janela._reiniciar()
        print(f"  {cenario.codigo}: {total} passos percorridos")

    # botoes e alternancias
    janela._alternar_pilha()
    janela._alternar_pilha()
    janela._alternar_tema()          # tema escuro
    janela._alternar_tema()          # de volta ao claro
    janela._alternar_registro()      # recolhe o registro
    janela._alternar_registro()      # e mostra de novo
    janela._aplicar_layout("compacto")
    janela._aplicar_layout("amplo")
    janela._zoom_central(1.2)
    janela._resetar_visualizacao()
    janela._mostrar_tabelas()
    janela._derrubar_enlace()
    janela._injetar_erro()
    janela._simular()
    janela._restaurar_rede()
    janela._executar()
    janela._pausar()
    janela._escolher_topologia()
    janela._salvar_registro()
    print("controles acionados")

    # parametros invalidos nao podem derrubar o programa
    janela._var_porta_origem.set("abc")
    janela._simular()
    janela._var_porta_origem.set("5210")
    janela._var_destino.set("10.0.999.1")
    janela._simular()
    janela._var_destino.set("10.0.3.10")
    janela._var_mensagem.set("")
    janela._simular()
    janela._var_mensagem.set("teste")
    janela._simular()
    print(f"entradas invalidas tratadas ({len(messagebox.registro)} avisos)")

    assert janela._resultado is not None
    print("\nconferencia concluida sem erro")
    return 0


if __name__ == "__main__":
    sys.exit(conferir())
