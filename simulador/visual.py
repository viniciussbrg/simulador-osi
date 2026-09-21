"""Interface grafica do simulador, construida com tkinter.

A interface le a lista de eventos produzida pelo motor e desenha a tela
correspondente ao evento corrente. Ela nao instancia camadas, nao chama
metodos de camada e nao conhece a implementacao do encapsulamento: tudo o que
aparece na tela vem de um objeto ``Evento``.

Os sete requisitos de visualizacao do enunciado estao distribuidos assim:

======  ======================================================================
V1      cartao "Mapa da rede", com o caminho percorrido em destaque
V2      cartao "Pilhas de protocolos", com a camada ativa em destaque
V3      cartao "Unidade de dados", com os blocos do encapsulamento
V4      cartao "Enderecos vigentes", com os dois pares visiveis ao mesmo tempo
V5      barra de controles, com passo a passo, execucao continua e pausa
V6      cartao "Registro de eventos", rolavel e com gravacao em arquivo
V7      alternancia entre a pilha OSI e a TCP/IP na barra superior
======  ======================================================================

Notas de construcao da camada visual:

* toda a cor sai de ``PALETA``, um dicionario trocado em tempo de execucao
  pelos temas claro e escuro; nenhum literal de cor aparece nos desenhos;
* o layout se reorganiza sozinho em dois modos ("amplo" e "compacto"), de
  forma que a janela continue legivel em telas menores;
* nenhuma dependencia externa e necessaria: apenas a biblioteca padrao.
"""

from __future__ import annotations

import sys
import os
import platform
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .ambiente import pasta_do_programa, topologia_padrao
from .camadas import CARGA_POR_SEGMENTO, LIMITE_SEGMENTACAO
from .cenarios import Cenario, Fluxo, cenarios_padrao
from .motor import (
    ErroDeSimulacaoError,
    ResultadoSimulacao,
    Simulacao,
    comparar_eficiencias,
)
from .pdu import TAMANHO_CABECALHO, TAMANHO_FINALIZADOR
from .rede import ErroDeTopologiaError, Topologia
from .registro import Evento, salvar


# ---------------------------------------------------------------------------
# Identidade visual
# ---------------------------------------------------------------------------

TEMA_CLARO: Dict[str, str] = {
    "fundo": "#F3F6F9",
    "fundo_alt": "#E7EDF3",
    "painel": "#FFFFFF",
    "painel_alt": "#F5F8FB",
    "borda": "#DCE4EC",
    "borda_forte": "#BDCAD6",
    "tinta": "#0F1E28",
    "tinta_fraca": "#5A7183",
    "tinta_suave": "#8DA1B0",
    "estrutura": "#0B6E8F",
    "estrutura_clara": "#DDEDF5",
    "ativo": "#C87A12",
    "ativo_claro": "#FCF0DA",
    "erro": "#BB3626",
    "erro_claro": "#FAE5E2",
    "entrega": "#2E7D5B",
    "inativo": "#AEBCC8",
    "dados": "#2E7D5B",
    "dados_claro": "#E0F1E8",
    "sombra": "#DAE2EA",
    "grade": "#EAF0F5",
    "contraste": "#FFFFFF",
}

TEMA_ESCURO: Dict[str, str] = {
    "fundo": "#0D151E",
    "fundo_alt": "#16222E",
    "painel": "#15202B",
    "painel_alt": "#1B2937",
    "borda": "#25374A",
    "borda_forte": "#34495F",
    "tinta": "#E9F1F7",
    "tinta_fraca": "#9DB2C3",
    "tinta_suave": "#6E8698",
    "estrutura": "#3FAED6",
    "estrutura_clara": "#123B4D",
    "ativo": "#EFB248",
    "ativo_claro": "#3C2D12",
    "erro": "#EF7A6D",
    "erro_claro": "#3B1D1A",
    "entrega": "#5FC08D",
    "inativo": "#49606F",
    "dados": "#5FC08D",
    "dados_claro": "#12301F",
    "sombra": "#090F16",
    "grade": "#1A2734",
    "contraste": "#0D151E",
}

#: Cores vigentes. O dicionario e trocado em bloco na alternancia de tema.
PALETA: Dict[str, str] = dict(TEMA_CLARO)

#: Tons dos cabecalhos por camada, do topo da pilha para a base.
CAMADAS_CLARO: Dict[int, str] = {
    7: "#6252A4",
    6: "#3A6BA8",
    5: "#0B6E8F",
    4: "#0D8576",
    3: "#3C8046",
    2: "#8A6D1F",
    1: "#63788C",
}

CAMADAS_ESCURO: Dict[int, str] = {
    7: "#A697E6",
    6: "#7DA8E2",
    5: "#49B6DC",
    4: "#42C1AD",
    3: "#7CC787",
    2: "#DBB65E",
    1: "#9FB5C7",
}

COR_CAMADA: Dict[int, str] = dict(CAMADAS_CLARO)

NOME_CAMADA: Dict[int, str] = {
    7: "Aplicação",
    6: "Apresentação",
    5: "Sessão",
    4: "Transporte",
    3: "Rede",
    2: "Enlace",
    1: "Física",
}

VELOCIDADES: Tuple[Tuple[str, int], ...] = (
    ("Lenta", 1200),
    ("Normal", 500),
    ("Rápida", 150),
)

#: Largura, em pixels a 96 dpi, a partir da qual as tres colunas cabem lado a
#: lado. Na janela ela e multiplicada pela escala de tela do sistema.
LARGURA_MODO_AMPLO = 1360

#: Divisao da altura entre a area central e o registro de eventos. O registro
#: e uma faixa de consulta: fica perto do minimo e cede espaco ao resto.
PESO_AREA_CENTRAL = 5
PESO_REGISTRO = 1
ALTURA_MINIMA_CENTRO = 150
#: Altura da janela (a 96 dpi) abaixo da qual o subtitulo da marca some.
ALTURA_MINIMA_SUBTITULO = 860
ALTURA_MINIMA_REGISTRO = 118

_FAMILIAS_UI = ("Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", "Ubuntu", "DejaVu Sans")
_FAMILIAS_MONO = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono")

_dpi_preparado = False


# ---------------------------------------------------------------------------
# Utilitarios de baixo nivel
# ---------------------------------------------------------------------------


def preparar_dpi() -> None:
    """Evita a janela borrada em telas de alta densidade no Windows."""
    global _dpi_preparado
    if _dpi_preparado:
        return
    _dpi_preparado = True
    if platform.system() != "Windows":
        return
    try:  # pragma: no cover - depende do sistema
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("simuladorosi.comunicacaodados")
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def mesclar(cor_a: str, cor_b: str, proporcao: float) -> str:
    """Retorna a cor entre ``cor_a`` e ``cor_b``; 0 devolve a primeira."""
    proporcao = min(1.0, max(0.0, proporcao))
    a = tuple(int(cor_a[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(cor_b[i : i + 2], 16) for i in (1, 3, 5))
    canais = (round(x + (y - x) * proporcao) for x, y in zip(a, b))
    return "#%02X%02X%02X" % tuple(canais)


def familia_disponivel(candidatas: Sequence[str], reserva: str) -> str:
    """Primeira familia tipografica instalada, ou ``reserva``."""
    try:
        instaladas = {nome.lower() for nome in tkfont.families()}
    except tk.TclError:  # pragma: no cover - sem servidor grafico
        return reserva
    for nome in candidatas:
        if nome.lower() in instaladas:
            return nome
    return reserva


def escala_da_tela(janela: tk.Misc) -> float:
    """Fator de escala do sistema: 1.0 em 96 dpi, 1.25 em 125% e assim por diante."""
    try:
        return max(1.0, float(janela.tk.call("tk", "scaling")) * 72 / 96)
    except (tk.TclError, AttributeError, TypeError, ValueError):
        return 1.0


def retangulo(canvas: tk.Canvas, x0, y0, x1, y1, raio: float = 8, **opcoes) -> int:
    """Desenha um retangulo de cantos arredondados no canvas."""
    raio = max(0.0, min(raio, abs(x1 - x0) / 2, abs(y1 - y0) / 2))
    pontos = [
        x0 + raio, y0,
        x1 - raio, y0,
        x1, y0,
        x1, y0 + raio,
        x1, y1 - raio,
        x1, y1,
        x1 - raio, y1,
        x0 + raio, y1,
        x0, y1,
        x0, y1 - raio,
        x0, y0 + raio,
        x0, y0,
    ]
    return canvas.create_polygon(pontos, smooth=True, **opcoes)


class Dica:
    """Balao de ajuda exibido ao pousar o ponteiro sobre um widget."""

    ATRASO = 550

    def __init__(self, widget: tk.Misc, texto: str, fonte=None) -> None:
        self._widget = widget
        self._texto = texto
        self._fonte = fonte
        self._balao: Optional[tk.Toplevel] = None
        self._agendado: Optional[str] = None
        widget.bind("<Enter>", self._agendar, add="+")
        widget.bind("<Leave>", self._ocultar, add="+")
        widget.bind("<ButtonPress>", self._ocultar, add="+")

    def _agendar(self, _evento=None) -> None:
        self._cancelar()
        self._agendado = self._widget.after(self.ATRASO, self._exibir)

    def _cancelar(self) -> None:
        if self._agendado is not None:
            try:
                self._widget.after_cancel(self._agendado)
            except tk.TclError:  # pragma: no cover
                pass
            self._agendado = None

    def _exibir(self) -> None:
        if self._balao is not None or not self._texto:
            return
        x = self._widget.winfo_rootx() + 14
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 8
        self._balao = tk.Toplevel(self._widget)
        self._balao.wm_overrideredirect(True)
        self._balao.wm_geometry(f"+{x}+{y}")
        rotulo = tk.Label(
            self._balao,
            text=self._texto,
            background=PALETA["tinta"],
            foreground=PALETA["contraste"],
            padx=9,
            pady=5,
            bd=0,
            justify="left",
        )
        if self._fonte:
            rotulo.configure(font=self._fonte)
        rotulo.pack()

    def _ocultar(self, _evento=None) -> None:
        self._cancelar()
        if self._balao is not None:
            self._balao.destroy()
            self._balao = None


class Cartao(ttk.Frame):
    """Painel com cabecalho, area de acoes e corpo.

    O contorno de um pixel vem do proprio quadro externo: ele usa a cor de
    borda como fundo e um preenchimento de 1, o que dispensa relevos do tema
    nativo e mantem o mesmo tracado nos dois temas.
    """

    def __init__(self, pai: tk.Misc, titulo: str, nota: str = "") -> None:
        super().__init__(pai, style="Cartao.TFrame", padding=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        topo = ttk.Frame(self, style="CartaoTopo.TFrame", padding=(14, 7))
        topo.grid(row=0, column=0, sticky="ew")
        topo.columnconfigure(1, weight=1)
        self._topo = topo

        self._titulo = ttk.Label(topo, text=titulo, style="CartaoTitulo.TLabel")
        self._titulo.grid(row=0, column=0, sticky="w")
        self.rotulo_nota = ttk.Label(topo, text=nota, style="CartaoNota.TLabel")
        self.rotulo_nota.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.acoes = ttk.Frame(topo, style="CartaoTopo.TFrame")
        self.acoes.grid(row=0, column=2, sticky="e")
        topo.bind("<Configure>", self._ajustar_nota)

        self.corpo = ttk.Frame(self, style="CartaoCorpo.TFrame", padding=(14, 10))
        self.corpo.grid(row=1, column=0, sticky="nsew")

    def _ajustar_nota(self, _evento=None) -> None:
        """Oculta a nota quando o cabeçalho é estreito demais para ela inteira.

        Uma nota cortada no meio da palavra é pior do que nenhuma nota.
        """
        largura = self._topo.winfo_width()
        if largura <= 1 or not self.rotulo_nota.cget("text"):
            return
        necessario = (
            self._titulo.winfo_reqwidth()
            + self.rotulo_nota.winfo_reqwidth()
            + self.acoes.winfo_reqwidth()
            + 28  # preenchimento lateral do cabeçalho
            + 10  # espaço entre o título e a nota
        )
        if necessario > largura:
            self.rotulo_nota.grid_remove()
        else:
            self.rotulo_nota.grid()


class LinhasFlexiveis(ttk.Frame):
    """Quadro que passa os itens para a linha de baixo quando não cabem.

    Os itens são filhos deste quadro e entram em ordem; ao faltar largura, o
    seguinte começa uma nova linha. Um item ``a_direita`` encosta na borda
    direita da linha em que cair, e um separador só aparece entre dois itens
    da mesma linha. A disposição é recalculada quando a largura muda ou
    quando algum item muda de tamanho, então nenhum botão sai da janela.
    """

    def __init__(
        self,
        pai: tk.Misc,
        estilo: str,
        margem_x: int = 0,
        margem_y: int = 0,
        folga: int = 8,
        folga_linha: int = 8,
    ) -> None:
        super().__init__(pai, style=estilo, padding=(margem_x, margem_y))
        self._estilo_linha = estilo
        self._margem_x = margem_x
        self._folga = folga
        self._folga_linha = folga_linha
        self._itens: List[Tuple[tk.Widget, bool, bool]] = []
        self._linhas: List[ttk.Frame] = []
        self._disposicao: Optional[tuple] = None
        self._agendado: Optional[str] = None
        self.columnconfigure(0, weight=1)
        self.bind("<Configure>", self._agendar, add="+")

    def adicionar(
        self, widget: tk.Widget, a_direita: bool = False, separador: bool = False
    ) -> None:
        """Registra um item, que deve ter sido criado com este quadro como pai."""
        self._itens.append((widget, a_direita, separador))
        widget.bind("<Configure>", self._agendar, add="+")
        self._agendar()

    def _agendar(self, _evento=None) -> None:
        if self._agendado is None:
            self._agendado = self.after_idle(self.reorganizar)

    def _quadro_da_linha(self, indice: int) -> ttk.Frame:
        while len(self._linhas) <= indice:
            self._linhas.append(ttk.Frame(self, style=self._estilo_linha))
        return self._linhas[indice]

    def reorganizar(self) -> None:
        self._agendado = None
        largura = self.winfo_width() - 2 * self._margem_x
        # Enquanto a janela ainda nao tem tamanho, tudo cabe numa linha so.
        limite = largura if largura > 1 else 10**6

        linhas: List[List[Tuple[tk.Widget, bool, bool]]] = [[]]
        usado = 0
        for item in self._itens:
            # Cada item leva consigo a folga que o separa do vizinho, como o
            # empacotamento abaixo faz; contar so as folgas *entre* itens
            # subestima a linha e deixa o ultimo item sem lugar.
            pedido = item[0].winfo_reqwidth() + self._folga
            atual = linhas[-1]
            if atual and usado + pedido > limite:
                linhas.append([item])
                usado = pedido
            else:
                usado += pedido
                atual.append(item)
        for linha in linhas:  # separador na ponta de uma linha nao separa nada
            while linha and linha[0][2]:
                linha.pop(0)
            while linha and linha[-1][2]:
                linha.pop()
        linhas = [linha for linha in linhas if linha]

        disposicao = tuple(tuple(id(item[0]) for item in linha) for linha in linhas)
        if disposicao == self._disposicao:
            return
        self._disposicao = disposicao

        # Desempacota tudo antes de reempacotar: a ordem de empacotamento de um
        # quadro nao muda sozinha quando um item volta a ele.
        for widget, _direita, _separador in self._itens:
            widget.pack_forget()
        for indice, linha in enumerate(linhas):
            quadro = self._quadro_da_linha(indice)
            quadro.grid(
                row=indice,
                column=0,
                sticky="ew",
                pady=(self._folga_linha if indice else 0, 0),
            )
            esquerda = [i for i in linha if not i[1]]
            direita = [i for i in linha if i[1]]
            for widget, _d, separador in esquerda:
                widget.pack(
                    in_=quadro,
                    side="left",
                    fill="y" if separador else "none",
                    padx=(0, self._folga),
                )
                widget.lift()
            for widget, _d, separador in reversed(direita):
                widget.pack(in_=quadro, side="right", padx=(self._folga, 0))
                widget.lift()
        for sobra in self._linhas[len(linhas):]:
            sobra.grid_remove()


class AreaRolavel(ttk.Frame):
    """Área com rolagem vertical que só aparece quando o conteúdo não cabe.

    O conteúdo (``self.conteudo``) recebe, no mínimo, a altura da área
    visível, de modo que os cartões elásticos continuam ocupando a janela
    inteira, e passa a rolar quando o que ele pede é maior do que isso. A
    área pede à janela a altura do conteúdo, mas pode ser encolhida por ela.
    """

    #: Pixels por passo da roda do mouse.
    PASSO = 24
    _CLASSES_COM_ROLAGEM_PROPRIA = ("Text", "Treeview", "Listbox", "TCombobox")

    def __init__(self, pai: tk.Misc, padding=0) -> None:
        super().__init__(pai)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(
            self,
            background=PALETA["fundo"],
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=self.PASSO,
        )
        self._barra = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._barra.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self.conteudo = ttk.Frame(self._canvas, padding=padding)
        self._janela = self._canvas.create_window(0, 0, window=self.conteudo, anchor="nw")
        self._barra_visivel = False
        self._estado: Optional[Tuple[int, int, int]] = None
        self._ajuste_agendado = False
        self._sem_rolagem: set = set()

        self._canvas.bind("<Configure>", self.verificar)
        self.conteudo.bind("<Configure>", self.verificar)

    def pintar(self) -> None:
        self._canvas.configure(background=PALETA["fundo"])

    def ignorar_roda(self, widget: tk.Widget) -> None:
        """A roda do mouse sobre ``widget`` nao rola a area (ele a usa de outro modo)."""
        self._sem_rolagem.add(widget)

    def ligar_roda(self) -> None:
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(evento, self._ao_rolar, add="+")

    def verificar(self, _evento=None) -> None:
        """Pede a conferencia do tamanho do conteudo, feita quando a fila esvazia.

        Precisa ser chamada quando o conteudo pode ter mudado de altura sem que
        nenhum widget desta area receba ``<Configure>`` (por exemplo, ao
        reorganizar os cartoes ou quebrar um texto em mais linhas).
        """
        if not self._ajuste_agendado:
            self._ajuste_agendado = True
            self.after_idle(self._ajustar)

    def _ajustar(self) -> None:
        self._ajuste_agendado = False
        largura = self._canvas.winfo_width()
        altura = self._canvas.winfo_height()
        if altura <= 1:
            return
        pedida = self.conteudo.winfo_reqheight()
        if (largura, altura, pedida) == self._estado:
            return
        self._estado = (largura, altura, pedida)

        self._canvas.configure(height=pedida)
        # O conteudo so tem a altura forcada quando precisa ser esticado ate o
        # fim da area visivel. Quando ele e maior, altura 0 o deixa no tamanho
        # que pede:
        # uma altura forcada esconderia o encolhimento do conteudo (nenhum
        # ``<Configure>`` chegaria) e a area ficaria com rolagem sobrando.
        self._canvas.itemconfigure(
            self._janela, width=largura, height=altura if pedida < altura else 0
        )
        self._canvas.configure(scrollregion=(0, 0, largura, max(altura, pedida)))

        precisa = pedida > altura
        if precisa != self._barra_visivel:
            self._barra_visivel = precisa
            if precisa:
                self._barra.grid(row=0, column=1, sticky="ns")
            else:
                self._barra.grid_remove()
                self._canvas.yview_moveto(0)
        # Mexer na geometria pode mudar o que os filhos pedem: confere de novo.
        # A conferencia seguinte encerra sozinha se nada mudou.
        self.verificar()

    def _contem(self, widget: tk.Misc) -> bool:
        while widget is not None:
            if widget is self:
                return True
            widget = widget.master
        return False

    def _ao_rolar(self, evento: tk.Event) -> None:
        if not self._barra_visivel:
            return
        try:
            alvo = self.winfo_containing(evento.x_root, evento.y_root)
        except (KeyError, tk.TclError):  # lista suspensa de um combobox aberto
            return
        if (
            alvo is None
            or alvo in self._sem_rolagem
            or alvo.winfo_class() in self._CLASSES_COM_ROLAGEM_PROPRIA
            or not self._contem(alvo)
        ):
            return
        subindo = getattr(evento, "num", None) == 4 or getattr(evento, "delta", 0) > 0
        self._canvas.yview_scroll(-3 if subindo else 3, "units")


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------


class AplicacaoSimulador(tk.Tk):
    """Janela principal do simulador."""

    def __init__(self, caminho_topologia: Optional[str] = None) -> None:
        preparar_dpi()
        super().__init__()
        self._definir_icone()
        self.title("Simulador do modelo OSI — Comunicação de Dados")
        self.minsize(1024, 680)

        # -- estado da simulacao -------------------------------------------
        self._cenarios: List[Cenario] = cenarios_padrao()
        self._topologia: Optional[Topologia] = None
        self._resultado: Optional[ResultadoSimulacao] = None
        self._indice = -1
        self._modo_pilha = "OSI"
        self._reproduzindo = False
        self._agendamento: Optional[str] = None
        self._derrubados: List[str] = []
        self._erro_de_bit: Optional[str] = None
        self._eficiencias_referencia: Dict[str, object] = {}

        # -- estado da visualizacao ----------------------------------------
        # Preferencias persistidas em config.toml: tema e visibilidade do
        # registro sao lidas juntas para que uma unica leitura do arquivo
        # baste, e para que salva-las depois nunca apague uma a outra.
        config_interface = self._ler_config_interface()
        self._tema = config_interface["tema"]
        PALETA.update(TEMA_ESCURO if self._tema == "escuro" else TEMA_CLARO)
        COR_CAMADA.update(CAMADAS_ESCURO if self._tema == "escuro" else CAMADAS_CLARO)

        # As larguras de referencia (breakpoints, alturas minimas) foram
        # pensadas para 96 dpi; em telas ampliadas as fontes crescem e os
        # mesmos elementos precisam de mais pixels.
        self._escala_ui = escala_da_tela(self)
        self._limite_amplo = int(LARGURA_MODO_AMPLO * self._escala_ui)
        self._medidores: Dict[tuple, tkfont.Font] = {}

        self._modo_layout = ""
        self._subtitulo_visivel: Optional[bool] = None
        self._registro_visivel = config_interface["registro_visivel"]
        self._mapa_zoom = 1.0
        self._mapa_pan_x = 0.0
        self._mapa_pan_y = 0.0
        self._arrasto_x = 0
        self._arrasto_y = 0

        self._definir_fontes()
        self._preparar_estilos()
        self._construir_layout()
        self._aplicar_visibilidade_registro()
        self._aplicar_layout("amplo")
        self._registrar_atalhos()
        self._posicionar_janela()

        self.bind("<Configure>", self._ao_redimensionar)
        self.protocol("WM_DELETE_WINDOW", self._encerrar)

        self._carregar_topologia(caminho_topologia or topologia_padrao(), inicial=True)

    # ------------------------------------------------------------------
    # Janela
    # ------------------------------------------------------------------

    def _posicionar_janela(self) -> None:
        self.update_idletasks()
        tela_largura = self.winfo_screenwidth()
        tela_altura = self.winfo_screenheight()
        largura = min(1680, int(tela_largura * 0.92))
        altura = min(1000, int(tela_altura * 0.90))
        x = max(0, (tela_largura - largura) // 2)
        y = max(0, (tela_altura - altura) // 2 - 16)
        self.geometry(f"{largura}x{altura}+{x}+{y}")
        self._maximizar()

    def _maximizar(self) -> None:
        for tentativa in (
            lambda: self.state("zoomed"),
            lambda: self.attributes("-zoomed", True),
        ):
            try:  # pragma: no cover - depende do gerenciador de janelas
                tentativa()
                return
            except tk.TclError:
                continue

    def _encerrar(self) -> None:
        self._pausar()
        self.destroy()

    def _ler_config_interface(self) -> Dict[str, object]:
        """Lê as preferências de interface salvas em ``config.toml``.

        Reúne, numa só leitura do arquivo, tanto o tema quanto a
        visibilidade do registro de eventos. Qualquer problema — arquivo
        ausente, corrompido ou com uma chave faltando — cai de volta nos
        valores padrão, para que a aplicação sempre abra normalmente.
        """
        padrao: Dict[str, object] = {"tema": "claro", "registro_visivel": True}
        arquivo = os.path.join(pasta_do_programa(), "config.toml")
        if not os.path.exists(arquivo):
            return padrao
        try:
            if sys.version_info >= (3, 11):
                import tomllib
                with open(arquivo, "rb") as f:
                    secao = tomllib.load(f).get("interface", {})
                tema = secao.get("tema", padrao["tema"])
                registro_visivel = secao.get("registro_visivel", padrao["registro_visivel"])
            else:
                # Fallback sem dependência para Python < 3.11: leitura
                # linha a linha das duas únicas chaves que esta tela grava.
                tema, registro_visivel = padrao["tema"], padrao["registro_visivel"]
                with open(arquivo, "r", encoding="utf-8") as f:
                    for linha in f:
                        linha = linha.strip()
                        if linha.startswith("tema"):
                            tema = "escuro" if "escuro" in linha else "claro"
                        elif linha.startswith("registro_visivel"):
                            registro_visivel = "true" in linha.lower()
            return {
                "tema": tema if tema in ("claro", "escuro") else padrao["tema"],
                "registro_visivel": bool(registro_visivel),
            }
        except Exception:
            return padrao

    def _salvar_config_interface(self) -> None:
        """Grava as preferências de interface correntes em ``config.toml``.

        Sempre escreve as duas chaves juntas, a partir do estado atual da
        janela — assim, alternar o tema nunca apaga a preferência do
        registro salva antes, e vice-versa.
        """
        arquivo = os.path.join(pasta_do_programa(), "config.toml")
        try:
            with open(arquivo, "w", encoding="utf-8") as f:
                f.write("[interface]\n")
                f.write(f'tema = "{self._tema}"\n')
                f.write(f"registro_visivel = {str(self._registro_visivel).lower()}\n")
        except OSError:
            pass  # Ignora se a pasta for somente leitura

    # ------------------------------------------------------------------
    # Aparencia
    # ------------------------------------------------------------------

    def _definir_fontes(self) -> None:
        self.familia_ui = familia_disponivel(_FAMILIAS_UI, "TkDefaultFont")
        self.familia_mono = familia_disponivel(_FAMILIAS_MONO, "TkFixedFont")
        self.fonte_base = (self.familia_ui, 10)
        self.fonte_titulo = (self.familia_ui, 10, "bold")
        self.fonte_rotulo = (self.familia_ui, 9)
        self.fonte_mini = (self.familia_ui, 8)
        self.fonte_marca = (self.familia_ui, 15, "bold")
        self.fonte_mono = (self.familia_mono, 9)
        self.fonte_mono_pequena = (self.familia_mono, 8)

    def _preparar_estilos(self) -> None:
        """Configura o tema ttk a partir de ``PALETA``.

        O metodo e reexecutado na troca de tema: como os widgets referenciam
        estilos por nome, reconfigurar o estilo repinta a janela inteira sem
        que nada precise ser reconstruido.
        """
        estilo = getattr(self, "_estilo", None) or ttk.Style(self)
        self._estilo = estilo
        try:
            estilo.theme_use("clam")
        except tk.TclError:  # pragma: no cover - depende do sistema
            pass

        self.configure(background=PALETA["fundo"])

        estilo.configure(
            ".",
            background=PALETA["fundo"],
            foreground=PALETA["tinta"],
            fieldbackground=PALETA["painel"],
            font=self.fonte_base,
        )

        # Quadros e cartoes
        estilo.configure("TFrame", background=PALETA["fundo"])
        estilo.configure("Barra.TFrame", background=PALETA["painel"])
        estilo.configure("Cartao.TFrame", background=PALETA["borda"])
        estilo.configure("CartaoTopo.TFrame", background=PALETA["painel_alt"])
        estilo.configure("CartaoCorpo.TFrame", background=PALETA["painel"])
        estilo.configure("Segmentado.TFrame", background=PALETA["fundo_alt"])
        estilo.configure("Estado.TFrame", background=PALETA["fundo_alt"])

        # Textos
        estilo.configure("TLabel", background=PALETA["fundo"], foreground=PALETA["tinta"])
        estilo.configure("Barra.TLabel", background=PALETA["painel"], foreground=PALETA["tinta"])
        estilo.configure(
            "Marca.TLabel",
            background=PALETA["painel"],
            foreground=PALETA["tinta"],
            font=self.fonte_marca,
        )
        estilo.configure(
            "MarcaNota.TLabel",
            background=PALETA["painel"],
            foreground=PALETA["tinta_suave"],
            font=self.fonte_mini,
        )
        estilo.configure(
            "CartaoTitulo.TLabel",
            background=PALETA["painel_alt"],
            foreground=PALETA["tinta"],
            font=self.fonte_titulo,
        )
        estilo.configure(
            "CartaoNota.TLabel",
            background=PALETA["painel_alt"],
            foreground=PALETA["tinta_suave"],
            font=self.fonte_mini,
        )
        estilo.configure("Painel.TLabel", background=PALETA["painel"], foreground=PALETA["tinta"])
        estilo.configure(
            "Rotulo.TLabel",
            background=PALETA["painel"],
            foreground=PALETA["tinta_fraca"],
            font=self.fonte_rotulo,
        )
        estilo.configure(
            "Fraco.TLabel",
            background=PALETA["painel"],
            foreground=PALETA["tinta_fraca"],
            font=self.fonte_rotulo,
        )
        estilo.configure(
            "Estado.TLabel",
            background=PALETA["fundo_alt"],
            foreground=PALETA["tinta_fraca"],
            font=self.fonte_rotulo,
        )
        estilo.configure(
            "Passo.TLabel",
            background=PALETA["painel"],
            foreground=PALETA["tinta"],
            font=self.fonte_rotulo,
        )

        # Botoes
        estilo.configure(
            "TButton",
            background=PALETA["painel"],
            foreground=PALETA["tinta"],
            bordercolor=PALETA["borda_forte"],
            lightcolor=PALETA["painel"],
            darkcolor=PALETA["painel"],
            focuscolor=PALETA["estrutura"],
            borderwidth=1,
            relief="flat",
            padding=(13, 7),
            font=self.fonte_base,
        )
        estilo.map(
            "TButton",
            background=[
                ("disabled", PALETA["painel"]),
                ("pressed", PALETA["fundo_alt"]),
                ("active", PALETA["estrutura_clara"]),
            ],
            foreground=[
                ("disabled", PALETA["tinta_suave"]),
                ("active", PALETA["estrutura"]),
            ],
            bordercolor=[
                ("disabled", PALETA["borda"]),
                ("active", PALETA["estrutura"]),
            ],
        )

        estilo.configure(
            "Acao.TButton",
            background=PALETA["estrutura"],
            foreground=PALETA["contraste"],
            bordercolor=PALETA["estrutura"],
            lightcolor=PALETA["estrutura"],
            darkcolor=PALETA["estrutura"],
            padding=(16, 8),
            font=self.fonte_titulo,
        )
        estilo.map(
            "Acao.TButton",
            background=[
                ("disabled", PALETA["inativo"]),
                ("pressed", mesclar(PALETA["estrutura"], PALETA["tinta"], 0.25)),
                ("active", mesclar(PALETA["estrutura"], PALETA["contraste"], 0.18)),
            ],
            foreground=[("disabled", PALETA["painel"])],
            bordercolor=[("disabled", PALETA["inativo"])],
        )

        # ``width=0`` desliga a largura minima de 11 caracteres do tema, que
        # transformaria os botoes "-", "+" e "ajustar" em blocos largos.
        estilo.configure("Icone.TButton", padding=(9, 5), font=self.fonte_base, width=0)
        estilo.configure("Discreto.TButton", padding=(10, 5), font=self.fonte_rotulo)

        # Controle segmentado (radiobuttons em forma de abas)
        estilo.configure(
            "Segmento.Toolbutton",
            background=PALETA["fundo_alt"],
            foreground=PALETA["tinta_fraca"],
            bordercolor=PALETA["fundo_alt"],
            lightcolor=PALETA["fundo_alt"],
            darkcolor=PALETA["fundo_alt"],
            borderwidth=0,
            relief="flat",
            padding=(13, 5),
            font=self.fonte_rotulo,
            anchor="center",
        )
        estilo.map(
            "Segmento.Toolbutton",
            background=[
                ("selected", PALETA["estrutura"]),
                ("active", PALETA["estrutura_clara"]),
            ],
            foreground=[
                ("selected", PALETA["contraste"]),
                ("active", PALETA["estrutura"]),
            ],
        )

        # Campos
        for nome in ("TEntry", "TCombobox"):
            estilo.configure(
                nome,
                fieldbackground=PALETA["painel"],
                background=PALETA["painel"],
                foreground=PALETA["tinta"],
                bordercolor=PALETA["borda_forte"],
                lightcolor=PALETA["borda_forte"],
                darkcolor=PALETA["borda_forte"],
                insertcolor=PALETA["tinta"],
                arrowcolor=PALETA["tinta_fraca"],
                selectbackground=PALETA["estrutura_clara"],
                selectforeground=PALETA["tinta"],
                padding=(8, 6),
            )
            estilo.map(
                nome,
                bordercolor=[("focus", PALETA["estrutura"]), ("hover", PALETA["estrutura"])],
                lightcolor=[("focus", PALETA["estrutura"])],
                darkcolor=[("focus", PALETA["estrutura"])],
                fieldbackground=[("readonly", PALETA["painel"]), ("disabled", PALETA["fundo_alt"])],
                foreground=[("disabled", PALETA["tinta_suave"])],
                arrowcolor=[("active", PALETA["estrutura"])],
            )
        self.option_add("*TCombobox*Listbox.background", PALETA["painel"])
        self.option_add("*TCombobox*Listbox.foreground", PALETA["tinta"])
        self.option_add("*TCombobox*Listbox.selectBackground", PALETA["estrutura"])
        self.option_add("*TCombobox*Listbox.selectForeground", PALETA["contraste"])

        # Barras de rolagem e progresso
        estilo.configure(
            "TScrollbar",
            background=PALETA["borda"],
            troughcolor=PALETA["painel_alt"],
            bordercolor=PALETA["painel_alt"],
            arrowcolor=PALETA["tinta_fraca"],
            borderwidth=0,
            relief="flat",
        )
        estilo.map("TScrollbar", background=[("active", PALETA["borda_forte"])])
        estilo.configure(
            "Progresso.Horizontal.TProgressbar",
            background=PALETA["estrutura"],
            troughcolor=PALETA["fundo_alt"],
            bordercolor=PALETA["fundo_alt"],
            lightcolor=PALETA["estrutura"],
            darkcolor=PALETA["estrutura"],
            borderwidth=0,
            thickness=6,
        )

        estilo.configure("TSeparator", background=PALETA["borda"])
        estilo.configure("TRadiobutton", background=PALETA["painel"], foreground=PALETA["tinta"])
        estilo.configure("TCheckbutton", background=PALETA["painel"], foreground=PALETA["tinta"])

        # Janela de tabelas
        estilo.configure("TNotebook", background=PALETA["fundo"], borderwidth=0)
        estilo.configure(
            "TNotebook.Tab",
            background=PALETA["fundo_alt"],
            foreground=PALETA["tinta_fraca"],
            bordercolor=PALETA["borda"],
            padding=(16, 8),
            borderwidth=0,
            font=self.fonte_rotulo,
        )
        estilo.map(
            "TNotebook.Tab",
            background=[("selected", PALETA["painel"])],
            foreground=[("selected", PALETA["estrutura"])],
        )
        estilo.configure(
            "Treeview",
            background=PALETA["painel"],
            fieldbackground=PALETA["painel"],
            foreground=PALETA["tinta"],
            bordercolor=PALETA["borda"],
            borderwidth=0,
            rowheight=27,
        )
        estilo.map(
            "Treeview",
            background=[("selected", PALETA["estrutura_clara"])],
            foreground=[("selected", PALETA["tinta"])],
        )
        estilo.configure(
            "Treeview.Heading",
            background=PALETA["fundo_alt"],
            foreground=PALETA["tinta_fraca"],
            relief="flat",
            padding=(9, 7),
            font=self.fonte_rotulo,
        )
        estilo.map("Treeview.Heading", background=[("active", PALETA["estrutura_clara"])])

    def _alternar_tema(self) -> None:
        """Troca entre o tema claro e o escuro."""
        self._tema = "escuro" if self._tema == "claro" else "claro"
        PALETA.update(TEMA_ESCURO if self._tema == "escuro" else TEMA_CLARO)
        COR_CAMADA.update(CAMADAS_ESCURO if self._tema == "escuro" else CAMADAS_CLARO)
        self._preparar_estilos()
        self._aplicar_cores_nativas()
        self._botao_tema.configure(
            text="Tema claro" if self._tema == "escuro" else "Tema escuro"
        )
        self._salvar_config_interface()
        self._redesenhar()

    def _aplicar_cores_nativas(self) -> None:
        """Repinta os widgets classicos, que nao seguem os estilos ttk."""
        for canvas in (
            self._canvas_mapa,
            self._canvas_pilhas,
            self._canvas_unidade,
            self._canvas_enderecos,
        ):
            canvas.configure(background=PALETA["painel"])
        for divisor in self._divisores:
            divisor.configure(background=PALETA["borda"])
        self._rolagem.pintar()
        for texto in (self._texto_eficiencia, self._texto_registro):
            texto.configure(
                background=PALETA["painel"],
                foreground=PALETA["tinta"],
                insertbackground=PALETA["tinta"],
                selectbackground=PALETA["estrutura_clara"],
                selectforeground=PALETA["tinta"],
            )
        self._texto_registro.tag_configure(
            "atual", background=PALETA["ativo_claro"], foreground=PALETA["tinta"]
        )
        self._texto_registro.tag_configure("alternada", background=PALETA["painel_alt"])
        self._texto_registro.tag_configure("descarte", foreground=PALETA["erro"])
        self._texto_registro.tag_configure("futuro", foreground=PALETA["inativo"])
        self._atualizar_tamanho_mensagem()

    # ------------------------------------------------------------------
    # Construcao do layout
    # ------------------------------------------------------------------

    def _construir_layout(self) -> None:
        self._divisores: List[tk.Frame] = []

        # A linha 2 (area central) e a 4 (registro) dividem a altura que sobra;
        # os pesos da linha 4 sao definidos em _aplicar_visibilidade_registro.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(
            2,
            weight=PESO_AREA_CENTRAL,
            minsize=int(ALTURA_MINIMA_CENTRO * self._escala_ui),
        )

        self._construir_barra_superior()

        divisor = tk.Frame(self, height=1, background=PALETA["borda"])
        divisor.grid(row=1, column=0, sticky="ew")
        self._divisores.append(divisor)

        # Quando o conteudo nao cabe na altura da janela, a area central rola
        # em vez de ter cartoes cortados ou empurrados para fora da tela.
        self._rolagem = AreaRolavel(self, padding=(14, 14, 14, 0))
        self._rolagem.grid(row=2, column=0, sticky="nsew")
        self._rolagem.ligar_roda()
        self._area_central = self._rolagem.conteudo

        self._coluna_mapa = ttk.Frame(self._area_central)
        self._coluna_pilhas = ttk.Frame(self._area_central)
        self._coluna_dados = ttk.Frame(self._area_central)

        self._construir_coluna_mapa()
        self._construir_coluna_pilhas()
        self._construir_coluna_dados()
        self._construir_controles()
        self._construir_registro()
        self._construir_barra_estado()

    # -- barra superior ----------------------------------------------------

    def _construir_barra_superior(self) -> None:
        barra = LinhasFlexiveis(
            self, "Barra.TFrame", margem_x=16, margem_y=12, folga=14, folga_linha=10
        )
        barra.grid(row=0, column=0, sticky="ew")
        self._barra_superior = barra

        marca = ttk.Frame(barra, style="Barra.TFrame", padding=(0, 0, 8, 0))
        ttk.Label(marca, text="Simulador do modelo OSI", style="Marca.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self._rotulo_subtitulo = ttk.Label(
            marca,
            text="Encapsulamento, endereçamento e encaminhamento, passo a passo",
            style="MarcaNota.TLabel",
        )
        self._rotulo_subtitulo.grid(row=1, column=0, sticky="w")
        barra.adicionar(marca)

        seletor = ttk.Frame(barra, style="Barra.TFrame")
        ttk.Label(seletor, text="Cenário", style="Barra.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self._var_cenario = tk.StringVar()
        self._combo_cenario = ttk.Combobox(
            seletor,
            textvariable=self._var_cenario,
            state="readonly",
            width=40,
            values=[c.nome_exibicao for c in self._cenarios],
        )
        self._combo_cenario.grid(row=0, column=1, sticky="w")
        if len(self._cenarios) > 1:
            self._combo_cenario.current(1)
        elif self._cenarios:
            self._combo_cenario.current(0)
        self._combo_cenario.bind(
            "<<ComboboxSelected>>", lambda _e: self._carregar_cenario()
        )

        barra.adicionar(seletor)

        botao_topologia = ttk.Button(
            barra, text="Abrir topologia", command=self._escolher_topologia
        )
        Dica(botao_topologia, "Carrega outro arquivo JSON de topologia", self.fonte_mini)
        barra.adicionar(botao_topologia)

        botao_tabelas = ttk.Button(
            barra, text="Tabelas de encaminhamento", command=self._mostrar_tabelas
        )
        Dica(botao_tabelas, "Rotas calculadas para cada roteador", self.fonte_mini)
        barra.adicionar(botao_tabelas)

        direita = ttk.Frame(barra, style="Barra.TFrame")
        barra.adicionar(direita, a_direita=True)

        ttk.Label(direita, text="Exibir pilha", style="Barra.TLabel").pack(
            side="left", padx=(0, 8)
        )
        self._var_pilha = tk.StringVar(value="OSI")
        self._segmentado(
            direita,
            self._var_pilha,
            (("OSI", "OSI"), ("TCP/IP", "TCP/IP")),
            self._alternar_pilha,
        ).pack(side="left")

        # Define qual texto o botão deve exibir ao iniciar
        texto_botao = "Tema claro" if self._tema == "escuro" else "Tema escuro"
        self._botao_tema = ttk.Button(
            direita, text=texto_botao, style="Discreto.TButton", command=self._alternar_tema
        )
        self._botao_tema.pack(side="left", padx=(14, 0))
        Dica(self._botao_tema, "Alterna entre o tema claro e o escuro", self.fonte_mini)

    def _segmentado(
        self,
        pai: tk.Misc,
        variavel: tk.Variable,
        opcoes: Sequence[Tuple[str, object]],
        comando: Optional[Callable[[], None]] = None,
    ) -> ttk.Frame:
        """Controle segmentado: um grupo de opcoes em forma de abas."""
        caixa = ttk.Frame(pai, style="Segmentado.TFrame", padding=2)
        for texto, valor in opcoes:
            ttk.Radiobutton(
                caixa,
                text=texto,
                value=valor,
                variable=variavel,
                command=comando,
                style="Segmento.Toolbutton",
            ).pack(side="left")
        return caixa

    # -- coluna 1: mapa e falhas ------------------------------------------

    def _construir_coluna_mapa(self) -> None:
        coluna = self._coluna_mapa
        coluna.columnconfigure(0, weight=1)
        coluna.rowconfigure(0, weight=1)

        cartao = Cartao(coluna, "Mapa da rede", "caminho do quadro em destaque")
        cartao.grid(row=0, column=0, sticky="nsew")
        cartao.corpo.columnconfigure(0, weight=1)
        cartao.corpo.rowconfigure(0, weight=1)

        for texto, dica, acao in (
            ("−", "Reduzir", lambda: self._zoom_central(1 / 1.2)),
            ("+", "Ampliar", lambda: self._zoom_central(1.2)),
            ("⛶", "Ajustar à área visível", self._resetar_visualizacao),
        ):
            botao = ttk.Button(cartao.acoes, text=texto, style="Icone.TButton", command=acao)
            botao.pack(side="left", padx=(4, 0))
            Dica(botao, dica, self.fonte_mini)

        self._canvas_mapa = tk.Canvas(
            cartao.corpo,
            background=PALETA["painel"],
            highlightthickness=0,
            height=280,
            cursor="hand2",
        )
        self._canvas_mapa.grid(row=0, column=0, sticky="nsew")
        self._ligar_desenho(self._canvas_mapa, self._desenhar_mapa)
        self._rolagem.ignorar_roda(self._canvas_mapa)  # a roda aqui e o zoom
        self._canvas_mapa.bind("<ButtonPress-1>", self._iniciar_arrasto)
        self._canvas_mapa.bind("<B1-Motion>", self._arrastar)
        self._canvas_mapa.bind("<ButtonRelease-1>", self._encerrar_arrasto)
        self._canvas_mapa.bind("<Double-Button-1>", lambda _e: self._resetar_visualizacao())
        self._canvas_mapa.bind("<MouseWheel>", self._aplicar_zoom)
        self._canvas_mapa.bind("<Button-4>", self._aplicar_zoom)
        self._canvas_mapa.bind("<Button-5>", self._aplicar_zoom)

        falhas = Cartao(coluna, "Provocar falhas", "para observar o comportamento da rede")
        falhas.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        corpo = falhas.corpo
        corpo.columnconfigure(0, weight=1)

        self._var_enlace = tk.StringVar()
        ttk.Label(corpo, text="Enlace", style="Rotulo.TLabel").grid(row=0, column=0, sticky="w")
        self._combo_enlace = ttk.Combobox(
            corpo, textvariable=self._var_enlace, state="readonly", width=10
        )
        self._combo_enlace.grid(row=1, column=0, sticky="ew", pady=(3, 10))

        botoes = LinhasFlexiveis(corpo, "CartaoCorpo.TFrame", folga=8, folga_linha=8)
        botoes.grid(row=2, column=0, sticky="ew")
        for texto, comando in (
            ("Derrubar enlace", self._derrubar_enlace),
            ("Injetar erro de bit", self._injetar_erro),
            ("Restaurar rede", self._restaurar_rede),
        ):
            botoes.adicionar(ttk.Button(botoes, text=texto, command=comando))

        self._rotulo_falhas = ttk.Label(
            corpo,
            text="Rede íntegra.",
            style="Fraco.TLabel",
            wraplength=360,
            justify="left",
        )
        self._rotulo_falhas.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self._quebrar_no_espaco(self._rotulo_falhas, corpo, margem=28)

    # -- coluna 2: pilhas --------------------------------------------------

    def _construir_coluna_pilhas(self) -> None:
        coluna = self._coluna_pilhas
        coluna.columnconfigure(0, weight=1)
        coluna.rowconfigure(0, weight=1)

        cartao = Cartao(coluna, "Pilhas de protocolos", "camada ativa em destaque")
        cartao.grid(row=0, column=0, sticky="nsew")
        self._cartao_pilhas = cartao
        cartao.corpo.columnconfigure(0, weight=1)
        cartao.corpo.rowconfigure(0, weight=1)

        self._canvas_pilhas = tk.Canvas(
            cartao.corpo, background=PALETA["painel"], highlightthickness=0, height=190
        )
        self._canvas_pilhas.grid(row=0, column=0, sticky="nsew")
        self._ligar_desenho(self._canvas_pilhas, self._desenhar_pilhas)

        rodape = ttk.Frame(cartao.corpo, style="CartaoCorpo.TFrame")
        rodape.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        rodape.columnconfigure(0, weight=1)
        self._rotulo_passo = ttk.Label(
            rodape,
            text="Carregue um cenário e pressione Passo para começar.",
            style="Passo.TLabel",
            wraplength=430,
            justify="left",
        )
        self._rotulo_passo.grid(row=0, column=0, sticky="w")
        self._quebrar_no_espaco(self._rotulo_passo, rodape)

    # -- coluna 3: parametros, unidade, enderecos, eficiencia --------------

    def _construir_coluna_dados(self) -> None:
        # Os quatro cartoes trocam de coluna conforme o modo do layout, por
        # isso nascem no quadro central e sao encaixados por _aplicar_layout.
        pai = self._area_central

        self._cartao_parametros = Cartao(pai, "Parâmetros da simulação")
        self._cartao_unidade = Cartao(pai, "Unidade de dados", "cabeçalhos e carga útil")
        self._cartao_enderecos = Cartao(pai, "Endereços vigentes", "lógicos e físicos")
        self._cartao_eficiencia = Cartao(pai, "Custo do empilhamento")

        self._construir_formulario(self._cartao_parametros.corpo)

        corpo_unidade = self._cartao_unidade.corpo
        corpo_unidade.columnconfigure(0, weight=1)
        corpo_unidade.rowconfigure(0, weight=1)
        self._canvas_unidade = tk.Canvas(
            corpo_unidade, background=PALETA["painel"], highlightthickness=0, height=100
        )
        self._canvas_unidade.grid(row=0, column=0, sticky="nsew")
        self._ligar_desenho(self._canvas_unidade, self._desenhar_unidade)

        corpo_enderecos = self._cartao_enderecos.corpo
        corpo_enderecos.columnconfigure(0, weight=1)
        corpo_enderecos.rowconfigure(0, weight=1)
        self._canvas_enderecos = tk.Canvas(
            corpo_enderecos, background=PALETA["painel"], highlightthickness=0, height=118
        )
        self._canvas_enderecos.grid(row=0, column=0, sticky="nsew")
        self._ligar_desenho(self._canvas_enderecos, self._desenhar_enderecos)

        corpo_eficiencia = self._cartao_eficiencia.corpo
        corpo_eficiencia.columnconfigure(0, weight=1)
        corpo_eficiencia.rowconfigure(0, weight=1)
        self._texto_eficiencia = tk.Text(
            corpo_eficiencia,
            height=4,
            width=10,
            font=self.fonte_mono,
            background=PALETA["painel"],
            foreground=PALETA["tinta"],
            relief="flat",
            wrap="none",
            borderwidth=0,
            state="disabled",
        )
        self._texto_eficiencia.grid(row=0, column=0, sticky="nsew")
        rolagem = ttk.Scrollbar(
            corpo_eficiencia, orient="vertical", command=self._texto_eficiencia.yview
        )
        rolagem.grid(row=0, column=1, sticky="ns")
        self._texto_eficiencia.configure(yscrollcommand=rolagem.set)

    def _construir_formulario(self, corpo: ttk.Frame) -> None:
        corpo.columnconfigure(0, weight=1, uniform="campos")
        corpo.columnconfigure(1, weight=1, uniform="campos")
        # (grupo, rotulo, linha, coluna, colunas ocupadas) de cada campo, para
        # poder empilha-los quando a coluna dupla fica estreita demais.
        self._campos_formulario: List[Tuple[ttk.Frame, ttk.Label, int, int, int]] = []
        self._formulario_empilhado = False

        self._var_origem = tk.StringVar()
        self._var_destino = tk.StringVar()
        self._var_processo_origem = tk.StringVar(value="navegador")
        self._var_processo_destino = tk.StringVar(value="servidorWeb")
        self._var_porta_origem = tk.StringVar(value="5210")
        self._var_porta_destino = tk.StringVar(value="443")
        self._var_mensagem = tk.StringVar()

        self._combo_origem = self._campo(
            corpo,
            "Computador de origem",
            0,
            0,
            lambda pai: ttk.Combobox(
                pai, textvariable=self._var_origem, state="readonly", width=8
            ),
        )
        self._combo_destino = self._campo(
            corpo,
            "Endereço lógico de destino",
            0,
            1,
            lambda pai: ttk.Combobox(pai, textvariable=self._var_destino, width=8),
        )
        self._campo(
            corpo,
            "Processo de origem",
            1,
            0,
            lambda pai: ttk.Entry(pai, textvariable=self._var_processo_origem, width=8),
        )
        self._campo(
            corpo,
            "Processo de destino",
            1,
            1,
            lambda pai: ttk.Entry(pai, textvariable=self._var_processo_destino, width=8),
        )
        self._campo(
            corpo,
            "Porta de origem",
            2,
            0,
            lambda pai: ttk.Entry(pai, textvariable=self._var_porta_origem, width=8),
        )
        self._campo(
            corpo,
            "Porta de destino",
            2,
            1,
            lambda pai: ttk.Entry(pai, textvariable=self._var_porta_destino, width=8),
        )
        self._campo(
            corpo,
            "Mensagem",
            3,
            0,
            lambda pai: ttk.Entry(pai, textvariable=self._var_mensagem, width=8),
            colspan=2,
        )

        rodape = ttk.Frame(corpo, style="CartaoCorpo.TFrame")
        rodape.grid(row=4, column=0, columnspan=2, sticky="ew")
        rodape.columnconfigure(0, weight=1)
        self._rodape_formulario = rodape
        corpo.bind("<Configure>", lambda _e: self._ajustar_formulario(corpo), add="+")
        self._rotulo_tamanho = ttk.Label(rodape, text="", style="Fraco.TLabel")
        self._rotulo_tamanho.grid(row=0, column=0, sticky="w")
        ttk.Button(
            rodape, text="Simular", style="Acao.TButton", command=self._simular
        ).grid(row=0, column=1, sticky="e")

        self._var_mensagem.trace_add("write", lambda *_a: self._atualizar_tamanho_mensagem())

    def _ajustar_formulario(self, corpo: ttk.Frame) -> None:
        """Empilha os campos numa coluna so quando duas nao comportam os rotulos."""
        util = corpo.winfo_width() - 28  # menos o preenchimento do cartao
        if util <= 1 or not self._campos_formulario:
            return
        maior_rotulo = max(r.winfo_reqwidth() for _g, r, _l, _c, _s in self._campos_formulario)
        empilhar = (util - 12) / 2 < maior_rotulo
        if empilhar == self._formulario_empilhado:
            return
        self._formulario_empilhado = empilhar
        for posicao, (grupo, _r, linha, coluna, colspan) in enumerate(self._campos_formulario):
            if empilhar:
                grupo.grid_configure(row=posicao, column=0, columnspan=2, padx=0)
            else:
                grupo.grid_configure(
                    row=linha,
                    column=coluna,
                    columnspan=colspan,
                    padx=(0, 6) if coluna == 0 and colspan == 1 else (6 if coluna else 0, 0),
                )
        self._rodape_formulario.grid_configure(
            row=len(self._campos_formulario) if empilhar else 4
        )
        self._rolagem.verificar()

    def _campo(
        self,
        pai: ttk.Frame,
        rotulo: str,
        linha: int,
        coluna: int,
        criar: Callable[[tk.Misc], tk.Widget],
        colspan: int = 1,
    ) -> tk.Widget:
        """Rotulo acima do campo: legivel mesmo em colunas estreitas."""
        grupo = ttk.Frame(pai, style="CartaoCorpo.TFrame")
        grupo.grid(
            row=linha,
            column=coluna,
            columnspan=colspan,
            sticky="ew",
            padx=(0, 6) if coluna == 0 and colspan == 1 else (6 if coluna else 0, 0),
            pady=(0, 10),
        )
        grupo.columnconfigure(0, weight=1)
        etiqueta = ttk.Label(grupo, text=rotulo, style="Rotulo.TLabel")
        etiqueta.grid(row=0, column=0, sticky="w")
        self._campos_formulario.append((grupo, etiqueta, linha, coluna, colspan))
        widget = criar(grupo)
        widget.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        widget.bind("<Return>", lambda _e: self._simular())
        return widget

    # -- controles e registro ---------------------------------------------

    def _construir_controles(self) -> None:
        barra = LinhasFlexiveis(
            self, "Barra.TFrame", margem_x=16, margem_y=10, folga=14, folga_linha=8
        )
        barra.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self._barra_controles = barra

        transporte = ttk.Frame(barra, style="Barra.TFrame")
        self._botao_passo = ttk.Button(
            transporte, text="Passo", style="Acao.TButton", command=self._passo
        )
        self._botao_passo.pack(side="left")
        Dica(self._botao_passo, "Avança um evento · barra de espaço", self.fonte_mini)

        self._botao_executar = ttk.Button(transporte, text="Executar", command=self._executar)
        self._botao_executar.pack(side="left", padx=8)
        Dica(self._botao_executar, "Execução contínua · Enter", self.fonte_mini)

        self._botao_pausar = ttk.Button(transporte, text="Pausar", command=self._pausar)
        self._botao_pausar.pack(side="left")
        Dica(self._botao_pausar, "Interrompe a execução · Esc", self.fonte_mini)

        self._botao_reiniciar = ttk.Button(
            transporte, text="Reiniciar", command=self._reiniciar
        )
        self._botao_reiniciar.pack(side="left", padx=8)
        Dica(self._botao_reiniciar, "Volta ao passo 0 · Ctrl+R", self.fonte_mini)
        barra.adicionar(transporte)

        barra.adicionar(ttk.Separator(barra, orient="vertical"), separador=True)

        velocidade = ttk.Frame(barra, style="Barra.TFrame")
        ttk.Label(velocidade, text="Velocidade", style="Barra.TLabel").pack(side="left")
        self._var_velocidade = tk.IntVar(value=VELOCIDADES[1][1])
        self._segmentado(velocidade, self._var_velocidade, VELOCIDADES).pack(
            side="left", padx=(10, 0)
        )
        barra.adicionar(velocidade)

        barra.adicionar(ttk.Separator(barra, orient="vertical"), separador=True)

        andamento = ttk.Frame(barra, style="Barra.TFrame")
        self._rotulo_progresso = ttk.Label(andamento, text="Passo 0 de 0", style="Barra.TLabel")
        self._rotulo_progresso.pack(side="left")
        self._progresso = ttk.Progressbar(
            andamento,
            style="Progresso.Horizontal.TProgressbar",
            mode="determinate",
            length=int(160 * self._escala_ui),
            maximum=1,
        )
        self._progresso.pack(side="left", padx=(12, 0))
        barra.adicionar(andamento)

        acoes = ttk.Frame(barra, style="Barra.TFrame")
        self._botao_registro = ttk.Button(
            acoes, text="Ocultar registro", style="Discreto.TButton", command=self._alternar_registro
        )
        self._botao_registro.pack(side="left", padx=(0, 8))
        ttk.Button(acoes, text="Salvar registro", command=self._salvar_registro).pack(
            side="left"
        )
        barra.adicionar(acoes, a_direita=True)

    def _construir_registro(self) -> None:
        self._cartao_registro = Cartao(
            self, "Registro de eventos", "uma linha por evento do encapsulamento"
        )
        self._cartao_registro.grid(row=4, column=0, sticky="nsew", padx=14, pady=(10, 0))
        corpo = self._cartao_registro.corpo
        corpo.columnconfigure(0, weight=1)
        corpo.rowconfigure(0, weight=1)

        self._texto_registro = tk.Text(
            corpo,
            font=self.fonte_mono_pequena,
            background=PALETA["painel"],
            foreground=PALETA["tinta"],
            relief="flat",
            borderwidth=0,
            wrap="none",
            height=3,
            width=10,
            spacing1=2,
            spacing3=2,
            state="disabled",
        )
        self._texto_registro.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(corpo, orient="vertical", command=self._texto_registro.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(
            corpo, orient="horizontal", command=self._texto_registro.xview
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        self._texto_registro.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set
        )
        self._texto_registro.tag_configure(
            "atual", background=PALETA["ativo_claro"], foreground=PALETA["tinta"]
        )
        self._texto_registro.tag_configure("alternada", background=PALETA["painel_alt"])
        self._texto_registro.tag_configure("descarte", foreground=PALETA["erro"])
        self._texto_registro.tag_configure("futuro", foreground=PALETA["inativo"])

    def _construir_barra_estado(self) -> None:
        barra = LinhasFlexiveis(
            self, "Estado.TFrame", margem_x=16, margem_y=7, folga=16, folga_linha=2
        )
        barra.grid(row=5, column=0, sticky="ew", pady=(8, 0))

        situacao = ttk.Frame(barra, style="Estado.TFrame")
        self._ponto_estado = ttk.Label(
            situacao, text="●", style="Estado.TLabel", foreground=PALETA["entrega"]
        )
        self._ponto_estado.pack(side="left", padx=(0, 8))
        self._barra_estado = ttk.Label(
            situacao, text="Pronto.", style="Estado.TLabel", justify="left"
        )
        self._barra_estado.pack(side="left")
        barra.adicionar(situacao)
        # Mensagens longas quebram na largura da janela em vez de a estourarem.
        self._quebrar_no_espaco(self._barra_estado, barra, margem=32 + 30)

        self._rotulo_contexto = ttk.Label(barra, text="", style="Estado.TLabel")
        barra.adicionar(self._rotulo_contexto, a_direita=True)

    def _alternar_registro(self) -> None:
        self._registro_visivel = not self._registro_visivel
        self._aplicar_visibilidade_registro()
        self._salvar_config_interface()

    def _aplicar_visibilidade_registro(self) -> None:
        """Mostra ou oculta o cartão de registro conforme ``_registro_visivel``.

        Usado tanto pelo botão "Ocultar/Mostrar registro" quanto na
        inicialização da janela, para que a última escolha do usuário seja
        respeitada assim que a aplicação abre.
        """
        if self._registro_visivel:
            self._cartao_registro.grid()
            self.rowconfigure(
                4,
                weight=PESO_REGISTRO,
                minsize=int(ALTURA_MINIMA_REGISTRO * self._escala_ui),
            )
            self._botao_registro.configure(text="Ocultar registro")
        else:
            self._cartao_registro.grid_remove()
            # Sem minsize, a linha vazia continuaria reservando altura.
            self.rowconfigure(4, weight=0, minsize=0)
            self._botao_registro.configure(text="Mostrar registro")

    # ------------------------------------------------------------------
    # Layout responsivo
    # ------------------------------------------------------------------

    def _ao_redimensionar(self, evento: tk.Event) -> None:
        if evento.widget is not self:
            return
        modo = "amplo" if evento.width >= self._limite_amplo else "compacto"
        if modo != self._modo_layout:
            self._aplicar_layout(modo)
        # O subtitulo e decorativo: cede o lugar quando falta largura ou altura
        # (altura medida em pixels a 96 dpi, para valer igual em telas ampliadas).
        mostrar = modo == "amplo" and evento.height >= ALTURA_MINIMA_SUBTITULO * self._escala_ui
        if mostrar != self._subtitulo_visivel:
            self._subtitulo_visivel = mostrar
            if mostrar:
                self._rotulo_subtitulo.grid()
            else:
                self._rotulo_subtitulo.grid_remove()

    def _aplicar_layout(self, modo: str) -> None:
        """Reorganiza as colunas conforme a largura disponivel.

        Em telas largas as tres colunas ficam lado a lado, cada uma com o que
        cabe na altura da janela sem rolar:

        * mapa e falhas;
        * pilhas, unidade de dados e custo do empilhamento (o que muda a
          cada passo do encapsulamento);
        * parametros e enderecos vigentes.

        Abaixo do limite (``LARGURA_MODO_AMPLO`` na escala da tela) o mapa e
        as pilhas dividem a faixa de cima, e os quatro cartoes restantes descem
        para uma faixa inteira, dispostos em tres colunas.
        """
        self._modo_layout = modo
        central = self._area_central
        pilhas = self._coluna_pilhas
        dados = self._coluna_dados

        for indice in range(3):
            central.columnconfigure(indice, weight=0, uniform="")
        for indice in range(2):
            central.rowconfigure(indice, weight=0)
        for indice in range(3):
            pilhas.rowconfigure(indice, weight=0)
        for indice in range(4):
            dados.columnconfigure(indice, weight=0, uniform="")
            dados.rowconfigure(indice, weight=0)

        parametros = self._cartao_parametros
        unidade = self._cartao_unidade
        enderecos = self._cartao_enderecos
        eficiencia = self._cartao_eficiencia

        if modo == "amplo":
            central.columnconfigure(0, weight=36, uniform="colunas")
            central.columnconfigure(1, weight=32, uniform="colunas")
            central.columnconfigure(2, weight=32, uniform="colunas")
            central.rowconfigure(0, weight=1)

            self._coluna_mapa.grid(row=0, column=0, columnspan=1, sticky="nsew", padx=(0, 12), pady=0)
            self._coluna_pilhas.grid(row=0, column=1, columnspan=1, sticky="nsew", padx=(0, 12), pady=0)
            self._coluna_dados.grid(row=0, column=2, columnspan=1, sticky="nsew", padx=0, pady=0)

            pilhas.rowconfigure(0, weight=3)
            unidade.grid(in_=pilhas, row=1, column=0, rowspan=1, columnspan=1, sticky="ew", padx=0, pady=(10, 0))
            eficiencia.grid(in_=pilhas, row=2, column=0, rowspan=1, columnspan=1, sticky="nsew", padx=0, pady=(10, 0))
            pilhas.rowconfigure(2, weight=1)

            dados.columnconfigure(0, weight=1)
            dados.rowconfigure(1, weight=1)
            parametros.grid(in_=dados, row=0, column=0, rowspan=1, columnspan=1, sticky="ew", padx=0, pady=0)
            enderecos.grid(in_=dados, row=1, column=0, rowspan=1, columnspan=1, sticky="new", padx=0, pady=(12, 0))
        else:
            central.columnconfigure(0, weight=1, uniform="colunas")
            central.columnconfigure(1, weight=1, uniform="colunas")
            central.rowconfigure(0, weight=3)
            central.rowconfigure(1, weight=2)

            self._coluna_mapa.grid(row=0, column=0, columnspan=1, sticky="nsew", padx=(0, 12), pady=(0, 12))
            self._coluna_pilhas.grid(row=0, column=1, columnspan=2, sticky="nsew", padx=0, pady=(0, 12))
            self._coluna_dados.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=0, pady=0)

            pilhas.rowconfigure(0, weight=1)
            dados.columnconfigure(0, weight=36, uniform="dados")
            dados.columnconfigure(1, weight=32, uniform="dados")
            dados.columnconfigure(2, weight=32, uniform="dados")
            dados.rowconfigure(0, weight=1)
            dados.rowconfigure(1, weight=1)
            parametros.grid(in_=dados, row=0, column=0, rowspan=2, columnspan=1, sticky="nsew", padx=(0, 12), pady=0)
            unidade.grid(in_=dados, row=0, column=1, rowspan=1, columnspan=1, sticky="nsew", padx=(0, 12), pady=(0, 12))
            enderecos.grid(in_=dados, row=1, column=1, rowspan=1, columnspan=1, sticky="nsew", padx=(0, 12), pady=0)
            eficiencia.grid(in_=dados, row=0, column=2, rowspan=2, columnspan=1, sticky="nsew", padx=0, pady=0)

        # Um widget so aparece se estiver acima do quadro em que foi encaixado
        # na ordem de empilhamento; os cartoes nasceram no quadro central.
        for cartao in (parametros, unidade, enderecos, eficiencia):
            cartao.lift()
        self._rolagem.verificar()

    def _registrar_atalhos(self) -> None:
        self.bind("<space>", self._atalho(self._passo))
        self.bind("<Right>", self._atalho(self._passo))
        self.bind("<Return>", self._atalho(self._executar))
        self.bind("<Escape>", self._atalho(self._pausar))
        self.bind("<Control-r>", self._atalho(self._reiniciar))
        self.bind("<Control-s>", self._atalho(self._salvar_registro))
        self.bind("<Control-l>", self._atalho(self._alternar_registro))

    def _atalho(self, acao: Callable[[], None]):
        """Ignora o atalho quando o foco esta em um campo de texto."""

        def manipulador(_evento=None):
            foco = self.focus_get()
            if isinstance(foco, (ttk.Entry, tk.Entry, tk.Text)):
                return None
            acao()
            return "break"

        return manipulador

    # ------------------------------------------------------------------
    # Topologia e cenarios
    # ------------------------------------------------------------------

    def _carregar_topologia(self, caminho: str, inicial: bool = False) -> None:
        try:
            topologia = Topologia.carregar(caminho)
        except ErroDeTopologiaError as erro:
            messagebox.showerror("Topologia não carregada", str(erro), parent=self)
            if inicial and self._topologia is None:
                self._informar(
                    "Nenhuma topologia carregada. Use “Abrir topologia”.", "erro"
                )
            return

        self._topologia = topologia
        self._derrubados = []
        self._erro_de_bit = None
        self._resetar_visualizacao()

        computadores = sorted(topologia.computadores())
        self._combo_origem.configure(values=computadores)
        self._combo_destino.configure(
            values=[topologia.interfaces_de(c)[0].logico for c in computadores]
        )
        self._combo_enlace.configure(
            values=[topologia.rotulo_enlace(s) for s in topologia.enlaces_derrubaveis()]
        )
        if self._combo_enlace["values"]:
            self._combo_enlace.current(0)

        try:
            self._eficiencias_referencia = comparar_eficiencias(topologia)
        except (ErroDeSimulacaoError, ErroDeTopologiaError):
            # Topologia diferente da de referencia: a comparacao C1 x C2 do
            # enunciado nao se aplica, e apenas o cenario corrente e exibido.
            self._eficiencias_referencia = {}

        self._rotulo_contexto.configure(
            text=(
                f"{topologia.nome} · {len(topologia.dispositivos)} dispositivos · "
                f"{len(topologia.segmentos)} redes"
            )
        )
        self._informar(
            f"Topologia “{topologia.nome}” carregada de {os.path.basename(caminho)}.", "ok"
        )
        self._carregar_cenario()

    def _escolher_topologia(self) -> None:
        caminho = filedialog.askopenfilename(
            parent=self,
            title="Escolher arquivo de topologia",
            initialdir=pasta_do_programa(),
            filetypes=[("Topologia em JSON", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if caminho:
            self._carregar_topologia(caminho)

    def _cenario_selecionado(self) -> Cenario:
        indice = max(0, self._combo_cenario.current())
        return self._cenarios[indice]

    def _carregar_cenario(self) -> None:
        """Preenche os campos com o cenário escolhido e executa a simulação."""
        if self._topologia is None:
            return
        cenario = self._cenario_selecionado()
        fluxo = cenario.fluxos[0]
        computadores = sorted(self._topologia.computadores())
        # O cenario C5 usa de proposito um destino que nao existe na topologia,
        # entao a ausencia do endereco nao o torna incompativel.
        destino_conhecido = (
            self._topologia.interface_por_logico(fluxo.destino_logico) is not None
        )
        compativel = fluxo.origem in computadores and (
            destino_conhecido or cenario.codigo == "C5"
        )

        self._var_origem.set(
            fluxo.origem if fluxo.origem in computadores else computadores[0]
        )
        self._var_destino.set(fluxo.destino_logico)
        self._var_processo_origem.set(fluxo.processo_origem)
        self._var_processo_destino.set(fluxo.processo_destino)
        self._var_porta_origem.set(str(fluxo.porta_origem))
        self._var_porta_destino.set(str(fluxo.porta_destino))
        self._var_mensagem.set(fluxo.texto)

        derrubado = cenario.enlace_derrubado
        self._derrubados = (
            [derrubado] if derrubado and derrubado in self._topologia.segmentos else []
        )
        erro = cenario.erro_de_bit
        self._erro_de_bit = erro if erro and erro in self._topologia.segmentos else None
        self._atualizar_falhas()

        if compativel:
            self._simular(cenario=cenario, usar_fluxos_do_cenario=True, silencioso=True)
        else:
            self._informar(
                f"O cenário {cenario.codigo} foi escrito para a topologia de referência. "
                f"Ajuste origem e destino e pressione Simular.",
                "aviso",
            )
            self._resultado = None
            self._indice = -1
            self._preencher_registro()
            self._redesenhar()

    # ------------------------------------------------------------------
    # Execucao
    # ------------------------------------------------------------------

    def _coletar_fluxos(self) -> Sequence[Fluxo]:
        """Monta o fluxo a partir dos campos da tela, validando as entradas."""
        origem = self._var_origem.get().strip()
        destino = self._var_destino.get().strip()
        mensagem = self._var_mensagem.get()
        if not origem:
            raise ErroDeSimulacaoError("escolha o computador de origem")
        if not destino:
            raise ErroDeSimulacaoError("informe o endereço lógico de destino")
        if not mensagem.strip():
            raise ErroDeSimulacaoError("a mensagem não pode ficar vazia")
        try:
            porta_origem = int(self._var_porta_origem.get())
            porta_destino = int(self._var_porta_destino.get())
        except ValueError:
            raise ErroDeSimulacaoError("as portas devem ser números inteiros") from None
        return (
            Fluxo(
                origem=origem,
                destino_logico=destino,
                processo_origem=self._var_processo_origem.get().strip() or "processo",
                processo_destino=self._var_processo_destino.get().strip() or "processo",
                porta_origem=porta_origem,
                porta_destino=porta_destino,
                texto=mensagem,
            ),
        )

    def _simular(
        self,
        cenario: Optional[Cenario] = None,
        usar_fluxos_do_cenario: bool = False,
        silencioso: bool = False,
    ) -> None:
        """Executa a simulação com os parâmetros da tela.

        :param silencioso: quando verdadeiro, um erro de parâmetro aparece na
            barra de estado em vez de abrir uma caixa de mensagem. E o que se
            usa ao trocar de cenário, para que a troca nunca interrompa o uso.
        """
        if self._topologia is None:
            messagebox.showwarning(
                "Sem topologia",
                "Carregue um arquivo de topologia antes de simular.",
                parent=self,
            )
            return
        self._pausar()
        cenario = cenario or self._cenario_selecionado()
        try:
            fluxos = None if usar_fluxos_do_cenario else self._coletar_fluxos()
            simulacao = Simulacao(
                self._topologia,
                cenario,
                fluxos=fluxos,
                enlaces_derrubados=self._derrubados,
                erro_de_bit=self._erro_de_bit,
            )
            self._resultado = simulacao.executar()
        except (ErroDeSimulacaoError, ErroDeTopologiaError) as erro:
            if silencioso:
                self._informar(f"Não foi possível simular: {erro}", "erro")
            else:
                messagebox.showerror("Não foi possível simular", str(erro), parent=self)
            return
        except Exception as erro:  # pragma: no cover - salvaguarda da janela
            messagebox.showerror(
                "Erro inesperado",
                f"A simulação foi interrompida: {erro}\nA janela continua aberta.",
                parent=self,
            )
            return

        self._indice = -1
        self._preencher_registro()
        self._atualizar_eficiencia()
        self._atualizar_tamanho_mensagem()
        self._redesenhar()
        self._informar(
            f"{cenario.nome_exibicao}: {self._resultado.total_de_passos} passos. "
            f"Use Passo ou Executar.",
            "ok",
        )

    def _passo(self) -> None:
        if not self._resultado:
            return
        if self._indice + 1 >= len(self._resultado.eventos):
            self._pausar()
            self._informar("Fim da simulação. Use Reiniciar para executar novamente.")
            return
        self._indice += 1
        self._redesenhar()

    def _executar(self) -> None:
        if not self._resultado or self._reproduzindo:
            return
        self._reproduzindo = True
        self._atualizar_controles()
        self._agendar()

    def _agendar(self) -> None:
        if not self._reproduzindo:
            return
        self._passo()
        if self._resultado and self._indice + 1 < len(self._resultado.eventos):
            self._agendamento = self.after(self._var_velocidade.get(), self._agendar)
        else:
            self._reproduzindo = False
            self._atualizar_controles()

    def _pausar(self) -> None:
        self._reproduzindo = False
        if self._agendamento is not None:
            try:
                self.after_cancel(self._agendamento)
            except tk.TclError:  # pragma: no cover
                pass
            self._agendamento = None
        self._atualizar_controles()

    def _reiniciar(self) -> None:
        self._pausar()
        self._indice = -1
        self._redesenhar()
        self._informar("Simulação reiniciada no passo 0.")

    def _atualizar_controles(self) -> None:
        """Liga e desliga os botoes conforme o estado da reproducao."""
        if not hasattr(self, "_botao_passo"):
            return
        tem_resultado = bool(self._resultado)
        no_fim = tem_resultado and self._indice + 1 >= len(self._resultado.eventos)

        def alternar(botao: ttk.Button, ativo: bool) -> None:
            botao.state(["!disabled"] if ativo else ["disabled"])

        alternar(self._botao_passo, tem_resultado and not no_fim)
        alternar(self._botao_executar, tem_resultado and not no_fim and not self._reproduzindo)
        alternar(self._botao_pausar, self._reproduzindo)
        alternar(self._botao_reiniciar, tem_resultado)

    # ------------------------------------------------------------------
    # Falhas
    # ------------------------------------------------------------------

    def _segmento_escolhido(self) -> Optional[str]:
        if self._topologia is None:
            return None
        indice = self._combo_enlace.current()
        if indice < 0:
            return None
        return self._topologia.enlaces_derrubaveis()[indice]

    def _derrubar_enlace(self) -> None:
        segmento = self._segmento_escolhido()
        if segmento is None:
            return
        if segmento in self._derrubados:
            self._derrubados.remove(segmento)
        else:
            self._derrubados.append(segmento)
        self._atualizar_falhas()
        self._simular()

    def _injetar_erro(self) -> None:
        segmento = self._segmento_escolhido()
        if segmento is None:
            return
        self._erro_de_bit = None if self._erro_de_bit == segmento else segmento
        self._atualizar_falhas()
        self._simular()

    def _restaurar_rede(self) -> None:
        self._derrubados = []
        self._erro_de_bit = None
        self._atualizar_falhas()
        self._simular()

    def _atualizar_falhas(self) -> None:
        partes = []
        if self._derrubados:
            partes.append("Enlaces derrubados: " + ", ".join(self._derrubados))
        if self._erro_de_bit:
            partes.append(f"Erro de bit injetado em: {self._erro_de_bit}")
        self._rotulo_falhas.configure(
            text="\n".join(partes) if partes else "Rede íntegra."
        )

    # ------------------------------------------------------------------
    # Desenho
    # ------------------------------------------------------------------

    def _evento_atual(self) -> Optional[Evento]:
        if not self._resultado or self._indice < 0:
            return None
        if self._indice >= len(self._resultado.eventos):
            return None
        return self._resultado.eventos[self._indice]

    def _redesenhar(self) -> None:
        self._desenhar_mapa()
        self._desenhar_pilhas()
        self._desenhar_unidade()
        self._desenhar_enderecos()
        self._destacar_registro()
        self._atualizar_progresso()
        self._atualizar_controles()
        self._rolagem.verificar()  # os textos de passo mudam de altura

        evento = self._evento_atual()
        if evento is None:
            self._rotulo_passo.configure(
                text="Passo 0. Nenhuma camada ativa ainda — pressione Passo."
            )
        else:
            self._rotulo_passo.configure(
                text=(
                    f"{evento.dispositivo} · camada {evento.camada} "
                    f"({NOME_CAMADA.get(evento.camada, '')}) · {evento.acao}\n"
                    f"{evento.descricao}"
                )
            )

    def _atualizar_progresso(self) -> None:
        total = len(self._resultado.eventos) if self._resultado else 0
        atual = max(0, self._indice + 1)
        self._rotulo_progresso.configure(text=f"Passo {atual} de {total}")
        self._progresso.configure(maximum=max(total, 1), value=atual)

    def _alternar_pilha(self) -> None:
        self._modo_pilha = self._var_pilha.get()
        self._desenhar_pilhas()

    def _ligar_desenho(self, canvas: tk.Canvas, desenhar: Callable[[], None]) -> None:
        """Redesenha ``canvas`` quando o tamanho dele muda.

        Arrastar a borda da janela gera uma rajada de ``<Configure>``. Cada
        rajada vira um unico desenho, feito quando a fila de eventos esvazia,
        e eventos que nao mudam o tamanho (so a posicao) sao ignorados.
        """
        estado: Dict[str, object] = {"tamanho": None, "agendado": False}

        def executar() -> None:
            estado["agendado"] = False
            desenhar()

        def ao_configurar(evento: tk.Event) -> None:
            tamanho = (evento.width, evento.height)
            if tamanho == estado["tamanho"]:
                return
            estado["tamanho"] = tamanho
            if not estado["agendado"]:
                estado["agendado"] = True
                canvas.after_idle(executar)

        canvas.bind("<Configure>", ao_configurar)

    def _quebrar_no_espaco(
        self, rotulo: ttk.Label, quadro: tk.Misc, margem: int = 0, minimo: int = 140
    ) -> None:
        """Faz o texto de ``rotulo`` quebrar na largura de ``quadro``.

        ``margem`` desconta o preenchimento do quadro. Com um ``wraplength``
        fixo o texto ficava cortado em colunas estreitas e curto em largas.
        """

        def ajustar(evento: tk.Event) -> None:
            largura = max(minimo, evento.width - margem)
            if int(str(rotulo.cget("wraplength")) or 0) != largura:
                rotulo.configure(wraplength=largura)

        quadro.bind("<Configure>", ajustar, add="+")

    def _medir(self, fonte: tuple, texto: str) -> int:
        """Largura em pixels de ``texto`` na ``fonte`` (tupla familia, tamanho...)."""
        medidor = self._medidores.get(fonte)
        if medidor is None:
            medidor = self._medidores[fonte] = tkfont.Font(font=fonte)
        return medidor.measure(texto)

    def _mensagem_vazia(self, canvas: tk.Canvas, texto: str) -> None:
        """Estado vazio: diz o que fazer em vez de deixar a area em branco."""
        largura = canvas.winfo_width()
        altura = canvas.winfo_height()
        retangulo(
            canvas,
            14,
            14,
            largura - 14,
            altura - 14,
            12,
            fill="",
            outline=PALETA["borda"],
            dash=(4, 4),
        )
        canvas.create_text(
            largura / 2,
            altura / 2,
            text=texto,
            fill=PALETA["tinta_suave"],
            font=self.fonte_rotulo,
            width=max(120, largura - 60),
            justify="center",
        )

    # -- mapa --------------------------------------------------------------

    def _iniciar_arrasto(self, evento) -> None:
        self._arrasto_x, self._arrasto_y = evento.x, evento.y
        self._canvas_mapa.configure(cursor="fleur")

    def _arrastar(self, evento) -> None:
        self._mapa_pan_x += evento.x - self._arrasto_x
        self._mapa_pan_y += evento.y - self._arrasto_y
        self._arrasto_x, self._arrasto_y = evento.x, evento.y
        self._desenhar_mapa()

    def _encerrar_arrasto(self, _evento=None) -> None:
        self._canvas_mapa.configure(cursor="hand2")

    def _aplicar_zoom(self, evento) -> None:
        if getattr(evento, "num", None) == 4 or getattr(evento, "delta", 0) > 0:
            fator = 1.12
        elif getattr(evento, "num", None) == 5 or getattr(evento, "delta", 0) < 0:
            fator = 1 / 1.12
        else:
            return
        self._ajustar_zoom(fator, evento.x, evento.y)

    def _zoom_central(self, fator: float) -> None:
        self._ajustar_zoom(
            fator, self._canvas_mapa.winfo_width() / 2, self._canvas_mapa.winfo_height() / 2
        )

    def _ajustar_zoom(self, fator: float, foco_x: float, foco_y: float) -> None:
        """Amplia mantendo fixo o ponto sob o cursor."""
        novo = min(4.0, max(0.4, self._mapa_zoom * fator))
        fator = novo / self._mapa_zoom
        if abs(fator - 1.0) < 1e-6:
            return
        self._mapa_zoom = novo
        self._mapa_pan_x = foco_x - (foco_x - self._mapa_pan_x) * fator
        self._mapa_pan_y = foco_y - (foco_y - self._mapa_pan_y) * fator
        self._desenhar_mapa()

    def _resetar_visualizacao(self) -> None:
        self._mapa_zoom = 1.0
        self._mapa_pan_x = 0.0
        self._mapa_pan_y = 0.0
        self._desenhar_mapa()

    @staticmethod
    def _pares_do_caminho(evento: Optional[Evento]):
        """Separa o caminho em pares orientados e nao orientados."""
        orientados = set()
        conjuntos = set()
        for par in (evento.caminho if evento else ()):
            itens = tuple(par)
            if len(itens) == 2:
                orientados.add(itens)
                conjuntos.add(frozenset(itens))
        return orientados, conjuntos

    def _desenhar_mapa(self) -> None:
        canvas = self._canvas_mapa
        canvas.delete("all")
        largura = canvas.winfo_width()
        altura = canvas.winfo_height()
        if largura < 60 or altura < 60:
            return
        if self._topologia is None:
            self._mensagem_vazia(canvas, "Nenhuma topologia carregada.\nUse “Abrir topologia”.")
            return

        # ``posicao`` (zoom do usuario) diz onde cada dispositivo fica; ``zoom``
        # dimensiona nos, textos e tracos. Numa area pequena os elementos
        # encolhem, em vez de se sobrepor, e o zoom do usuario vale por cima.
        posicao = self._mapa_zoom
        zoom = posicao * max(0.62, min(1.0, largura / 640, altura / 340))
        margem_x, margem_y = 58, 46
        posicoes = self._topologia.posicoes()

        def tela(x: float, y: float) -> Tuple[float, float]:
            return (x * posicao + self._mapa_pan_x, y * posicao + self._mapa_pan_y)

        def ponto(nome: str) -> Tuple[float, float]:
            rx, ry = posicoes[nome]
            return tela(
                margem_x + rx * (largura - 2 * margem_x),
                margem_y + ry * (altura - 2 * margem_y),
            )

        def fonte_ui(tamanho: int, negrito: bool = False) -> tuple:
            corpo = (self.familia_ui, max(6, int(round(tamanho * zoom))))
            return corpo + ("bold",) if negrito else corpo

        def fonte_mono(tamanho: int) -> tuple:
            return (self.familia_mono, max(6, int(round(tamanho * zoom))))

        evento = self._evento_atual()
        orientados, pares = self._pares_do_caminho(evento)

        for ligacao in self._topologia.ligacoes_visuais():
            membros = ligacao["membros"]
            ativo = ligacao["segmento"] not in self._derrubados
            com_erro = ligacao["segmento"] == self._erro_de_bit

            if len(membros) == 2:
                a, b = membros[0]["dispositivo"], membros[1]["dispositivo"]
                pa, pb = ponto(a), ponto(b)
                destacado = frozenset((a, b)) in pares
                sentido = None
                if destacado:
                    sentido = "last" if (a, b) in orientados else "first"
                self._traco(canvas, pa, pb, ativo, destacado, sentido, zoom, com_erro)
                meio = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
                canvas.create_text(
                    meio[0],
                    meio[1] - 11 * zoom,
                    text=(
                        ligacao["prefixo"]
                        if ligacao["tipo"] == "local"
                        else f"custo {ligacao['custo']}"
                    ),
                    font=fonte_mono(8),
                    fill=PALETA["erro"] if not ativo else PALETA["tinta_fraca"],
                )
                self._rotulo_interface(canvas, pa, pb, membros[0]["interface"], fonte_mono(8), zoom)
                self._rotulo_interface(canvas, pb, pa, membros[1]["interface"], fonte_mono(8), zoom)
            else:
                if ligacao["posicao"]:
                    centro = tela(
                        margem_x + ligacao["posicao"][0] * (largura - 2 * margem_x),
                        margem_y + ligacao["posicao"][1] * (altura - 2 * margem_y),
                    )
                else:
                    pontos = [ponto(m["dispositivo"]) for m in membros]
                    centro = (
                        sum(p[0] for p in pontos) / len(pontos),
                        sum(p[1] for p in pontos) / len(pontos),
                    )
                nomes = [m["dispositivo"] for m in membros]
                internos = {
                    par for par in orientados if set(par) <= set(nomes)
                }
                origens = {par[0] for par in internos}
                destinos = {par[1] for par in internos}
                for membro in membros:
                    nome = membro["dispositivo"]
                    destacado = nome in origens or nome in destinos
                    sentido = "last" if nome in origens else ("first" if nome in destinos else None)
                    self._traco(
                        canvas, ponto(nome), centro, ativo, destacado, sentido, zoom, com_erro
                    )
                    self._rotulo_interface(
                        canvas, ponto(nome), centro, membro["interface"], fonte_mono(8), zoom
                    )
                retangulo(
                    canvas,
                    centro[0] - 34 * zoom,
                    centro[1] - 14 * zoom,
                    centro[0] + 34 * zoom,
                    centro[1] + 14 * zoom,
                    12 * zoom,
                    fill=PALETA["estrutura_clara"],
                    outline=PALETA["estrutura"],
                )
                canvas.create_text(
                    centro[0],
                    centro[1],
                    text=ligacao["segmento"].replace("Rede ", ""),
                    font=fonte_mono(8),
                    fill=PALETA["estrutura"],
                )
                canvas.create_text(
                    centro[0],
                    centro[1] + 24 * zoom,
                    text=ligacao["prefixo"],
                    font=fonte_mono(8),
                    fill=PALETA["tinta_fraca"],
                )

        atual = evento.dispositivo if evento else None
        for nome, descricao in self._topologia.dispositivos.items():
            x, y = ponto(nome)
            roteador = descricao.tipo == "roteador"
            logico = descricao.interfaces[0].logico
            texto_largo = max(
                self._medir(fonte_ui(9, True), nome), self._medir(fonte_mono(8), logico)
            )
            # O losango do roteador e mais estreito na altura do texto.
            necessaria = texto_largo * (0.78 if roteador else 0.5) + 8 * zoom
            meia_largura = max((48 if roteador else 44) * zoom, necessaria)
            meia_altura = (30 if roteador else 26) * zoom
            destaque = nome == atual
            cor_fundo = (
                PALETA["ativo_claro"]
                if destaque
                else (PALETA["estrutura_clara"] if roteador else PALETA["painel"])
            )
            cor_borda = PALETA["ativo"] if destaque else (
                PALETA["estrutura"] if roteador else PALETA["borda_forte"]
            )
            espessura = 3 if destaque else 1

            if roteador:
                canvas.create_polygon(
                    x, y - meia_altura,
                    x + meia_largura, y,
                    x, y + meia_altura,
                    x - meia_largura, y,
                    fill=cor_fundo,
                    outline=cor_borda,
                    width=espessura,
                )
            else:
                retangulo(
                    canvas,
                    x - meia_largura + 2 * zoom,
                    y - meia_altura + 3 * zoom,
                    x + meia_largura + 2 * zoom,
                    y + meia_altura + 3 * zoom,
                    10 * zoom,
                    fill=PALETA["sombra"],
                    outline="",
                )
                retangulo(
                    canvas,
                    x - meia_largura,
                    y - meia_altura,
                    x + meia_largura,
                    y + meia_altura,
                    10 * zoom,
                    fill=cor_fundo,
                    outline=cor_borda,
                    width=espessura,
                )
            canvas.create_text(
                x, y - 7 * zoom, text=nome, font=fonte_ui(9, True), fill=PALETA["tinta"]
            )
            canvas.create_text(
                x,
                y + 8 * zoom,
                text=logico,
                font=fonte_mono(8),
                fill=PALETA["tinta_fraca"],
            )

        self._desenhar_legenda_mapa(canvas, largura, altura)

    def _desenhar_legenda_mapa(self, canvas: tk.Canvas, largura: int, altura: int) -> None:
        """Legenda e instrucoes, desenhadas em coordenadas de tela."""
        if altura < 190 or largura < 320:
            return
        itens = (
            (PALETA["ativo"], "caminho atual"),
            (PALETA["inativo"], "enlace disponível"),
            (PALETA["erro"], "enlace derrubado"),
        )
        x = 14.0
        y = altura - 18
        for cor, texto in itens:
            canvas.create_line(x, y, x + 16, y, fill=cor, width=3, capstyle="round")
            canvas.create_text(
                x + 22,
                y,
                text=texto,
                anchor="w",
                font=self.fonte_mini,
                fill=PALETA["tinta_fraca"],
            )
            x += 30 + len(texto) * 5.6
        canvas.create_text(
            largura - 12,
            14,
            anchor="e",
            font=self.fonte_mini,
            fill=PALETA["tinta_suave"],
        )

    def _traco(
        self,
        canvas: tk.Canvas,
        origem,
        destino,
        ativo: bool,
        destacado: bool,
        sentido: Optional[str],
        zoom: float,
        com_erro: bool = False,
    ) -> None:
        if not ativo:
            canvas.create_line(
                *origem, *destino, fill=PALETA["erro"], width=2 * zoom, dash=(6, 5)
            )
            meio = ((origem[0] + destino[0]) / 2, (origem[1] + destino[1]) / 2)
            canvas.create_text(
                meio[0],
                meio[1] + 11 * zoom,
                text="✕",
                fill=PALETA["erro"],
                font=(self.familia_ui, max(7, int(10 * zoom)), "bold"),
            )
            return
        opcoes = {
            "fill": PALETA["ativo"] if destacado else PALETA["inativo"],
            "width": (4.5 if destacado else 1.6) * zoom,
            "capstyle": "round",
        }
        if com_erro:
            opcoes["dash"] = (8, 4)
        if destacado and sentido:
            opcoes["arrow"] = sentido
            opcoes["arrowshape"] = (12 * zoom, 15 * zoom, 5 * zoom)
        canvas.create_line(*origem, *destino, **opcoes)

    def _rotulo_interface(
        self, canvas: tk.Canvas, origem, destino, nome: str, fonte, escala: float
    ) -> None:
        dx, dy = destino[0] - origem[0], destino[1] - origem[1]
        comprimento = max(1.0, (dx * dx + dy * dy) ** 0.5)
        fator = min(0.34, 48 * escala / comprimento)
        canvas.create_text(
            origem[0] + dx * fator,
            origem[1] + dy * fator,
            text=nome,
            font=fonte,
            fill=PALETA["tinta_fraca"],
        )

    # -- pilhas ------------------------------------------------------------

    def _faixas(self, tipo: str) -> List[Tuple[str, set]]:
        """Faixas exibidas na pilha, conforme o modelo escolhido."""
        if self._modo_pilha == "OSI":
            numeros = [7, 6, 5, 4, 3, 2, 1] if tipo == "computador" else [3, 2, 1]
            return [(f"L{n} {NOME_CAMADA[n]}", {n}) for n in numeros]
        if tipo == "computador":
            return [
                ("Aplicação (5-7)", {5, 6, 7}),
                ("L4 Transporte", {4}),
                ("L3 Rede", {3}),
                ("L2 Enlace", {2}),
                ("L1 Física", {1}),
            ]
        return [("L3 Rede", {3}), ("L2 Enlace", {2}), ("L1 Física", {1})]

    def _desenhar_pilhas(self) -> None:
        canvas = self._canvas_pilhas
        canvas.delete("all")
        largura = canvas.winfo_width()
        altura = canvas.winfo_height()
        if largura < 60 or altura < 60:
            return
        if not self._resultado or self._topologia is None:
            self._mensagem_vazia(
                canvas, "As pilhas dos dispositivos aparecem aqui depois da simulação."
            )
            return

        envolvidos = list(self._resultado.dispositivos_envolvidos)
        if not envolvidos:
            return

        evento = self._evento_atual()
        coluna = largura / len(envolvidos)
        topo = 34.0
        altura_util = altura - topo - 12
        bases: List[Tuple[float, float, float]] = []

        for indice, nome in enumerate(envolvidos):
            descricao = self._topologia.dispositivos[nome]
            faixas = self._faixas(descricao.tipo)
            altura_faixa = min(40.0, altura_util / max(len(faixas), 1))
            x0 = indice * coluna + 9
            x1 = (indice + 1) * coluna - 9
            ativo_aqui = evento is not None and evento.dispositivo == nome

            # Identificacao do dispositivo
            retangulo(
                canvas,
                x0,
                4,
                x1,
                26,
                10,
                fill=PALETA["ativo_claro"] if ativo_aqui else PALETA["painel_alt"],
                outline=PALETA["ativo"] if ativo_aqui else PALETA["borda"],
            )
            canvas.create_text(
                (x0 + x1) / 2,
                15,
                text=nome,
                font=self.fonte_titulo,
                fill=PALETA["ativo"] if ativo_aqui else PALETA["tinta"],
            )

            for posicao, (rotulo, numeros) in enumerate(faixas):
                y0 = topo + posicao * altura_faixa
                y1 = y0 + altura_faixa - 4
                ativa = ativo_aqui and evento.camada in numeros
                decisao_de_rota = (
                    ativa and descricao.tipo == "roteador" and evento.camada == 3
                )
                retangulo(
                    canvas,
                    x0,
                    y0,
                    x1,
                    y1,
                    7,
                    fill=PALETA["ativo_claro"] if ativa else PALETA["painel"],
                    outline=PALETA["ativo"] if ativa else PALETA["borda"],
                    width=3 if decisao_de_rota else (2 if ativa else 1),
                )
                # Faixa colorida da camada, a esquerda
                menor = min(numeros)
                retangulo(
                    canvas,
                    x0 + 3,
                    y0 + 4,
                    x0 + 8,
                    y1 - 4,
                    3,
                    fill=COR_CAMADA.get(menor, PALETA["estrutura"]),
                    outline="",
                )
                canvas.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=rotulo if (x1 - x0) > 118 else rotulo.split(" ")[0],
                    font=self.fonte_titulo if ativa else self.fonte_base,
                    fill=PALETA["tinta"] if ativa else PALETA["tinta_fraca"],
                )
                if ativa and (x1 - x0) > 150 and evento is not None:
                    canvas.create_text(
                        x1 - 10,
                        (y0 + y1) / 2,
                        text=evento.acao,
                        anchor="e",
                        font=self.fonte_mini,
                        fill=PALETA["ativo"],
                    )
                if posicao == len(faixas) - 1:
                    bases.append((x0, x1, (y0 + y1) / 2))

        # Meio fisico: liga a base das pilhas vizinhas
        for (_, x1_anterior, y_anterior), (x0_proximo, _, y_proximo) in zip(
            bases, bases[1:]
        ):
            canvas.create_line(
                x1_anterior,
                y_anterior,
                x0_proximo,
                y_proximo,
                fill=PALETA["borda_forte"],
                width=1,
                dash=(3, 3),
            )

    # -- unidade de dados --------------------------------------------------

    def _desenhar_unidade(self) -> None:
        canvas = self._canvas_unidade
        canvas.delete("all")
        largura = canvas.winfo_width()
        altura = canvas.winfo_height()
        if largura < 60 or altura < 40:
            return
        evento = self._evento_atual()
        if evento is None or not evento.blocos:
            self._mensagem_vazia(canvas, "A unidade de dados aparece aqui a cada passo.")
            return

        blocos = list(evento.blocos)
        uteis = sum(b["tamanho"] for b in blocos if b["tipo"] == "dados")
        titulo = f"{evento.unidade}"
        if evento.identificador:
            titulo += f" {evento.identificador}"
        canvas.create_text(
            6, 12, text=titulo, anchor="w", font=self.fonte_titulo, fill=PALETA["tinta"]
        )
        canvas.create_text(
            largura - 6,
            12,
            text=f"{evento.tamanho} octetos · {uteis} úteis",
            anchor="e",
            font=self.fonte_mini,
            fill=PALETA["tinta_fraca"],
        )

        total = sum(max(b["tamanho"], 1) for b in blocos)
        util = largura - 12
        minimo = 34.0
        larguras = [max(minimo, util * max(b["tamanho"], 1) / total) for b in blocos]
        excesso = sum(larguras) - util
        if excesso > 0:
            folgados = [i for i, w in enumerate(larguras) if w > minimo]
            disponivel = sum(larguras[i] - minimo for i in folgados) or 1
            for i in folgados:
                larguras[i] -= (larguras[i] - minimo) * excesso / disponivel

        y0 = 26.0
        y1 = max(y0 + 34, altura - 24)
        x = 6.0
        for bloco, largura_bloco in zip(blocos, larguras):
            if bloco["tipo"] == "dados":
                fundo, borda = PALETA["dados_claro"], PALETA["dados"]
            elif bloco["tipo"] == "finalizador":
                fundo, borda = PALETA["painel_alt"], PALETA["tinta_fraca"]
            else:
                borda = COR_CAMADA.get(bloco.get("camada"), PALETA["estrutura"])
                fundo = (
                    PALETA["ativo_claro"]
                    if bloco.get("camada") == evento.camada
                    else PALETA["painel_alt"]
                )
            retangulo(
                canvas, x, y0, x + largura_bloco, y1, 7, fill=fundo, outline=borda, width=2
            )
            canvas.create_text(
                x + largura_bloco / 2,
                (y0 + y1) / 2 - 8,
                text=bloco["rotulo"],
                font=self.fonte_titulo,
                fill=borda,
            )
            canvas.create_text(
                x + largura_bloco / 2,
                (y0 + y1) / 2 + 9,
                text=f"{bloco['tamanho']} B",
                font=self.fonte_mono_pequena,
                fill=PALETA["tinta_fraca"],
            )
            x += largura_bloco

        canvas.create_text(
            6,
            altura - 9,
            anchor="w",
            text="Cabeçalhos à esquerda dos dados; finalizador da camada 2 à direita.",
            font=self.fonte_mini,
            fill=PALETA["tinta_suave"],
        )

    # -- enderecos ---------------------------------------------------------

    def _desenhar_enderecos(self) -> None:
        canvas = self._canvas_enderecos
        canvas.delete("all")
        largura = canvas.winfo_width()
        altura = canvas.winfo_height()
        if largura < 60 or altura < 40:
            return
        evento = self._evento_atual()
        metade = largura / 2 - 6
        base = max(96.0, altura - 6)

        def caixa(x: float, titulo: str, nota: str, par, cor: str) -> None:
            origem, destino = par if par else ("—", "—")
            linhas = (f"origem   {origem}", f"destino  {destino}")
            fonte_valores = self.fonte_mono
            for tamanho in (9, 8, 7):
                fonte_valores = (self.familia_mono, tamanho)
                if max(self._medir(fonte_valores, t) for t in linhas) <= metade - 22:
                    break
            retangulo(
                canvas,
                x,
                4,
                x + metade,
                base,
                10,
                fill=PALETA["painel"],
                outline=cor,
                width=2,
            )
            retangulo(canvas, x, 4, x + metade, 30, 10, fill=mesclar(PALETA["painel"], cor, 0.12), outline="")
            canvas.create_text(
                x + 11, 17, text=titulo, anchor="w", font=self.fonte_titulo, fill=cor
            )
            canvas.create_text(
                x + 11,
                42,
                text=nota,
                anchor="w",
                font=self.fonte_mini,
                fill=PALETA["tinta_suave"],
                width=metade - 20,
            )
            for deslocamento, linha in ((34, linhas[0]), (14, linhas[1])):
                canvas.create_text(
                    x + 11,
                    base - deslocamento,
                    text=linha,
                    anchor="w",
                    font=fonte_valores,
                    fill=PALETA["tinta"],
                )

        caixa(
            2,
            "Lógicos",
            "inseridos na origem, constantes até o destino",
            evento.logicos if evento else None,
            PALETA["estrutura"],
        )
        caixa(
            largura / 2 + 4,
            "Físicos",
            "substituídos a cada salto"
            + (f" · {evento.enlace}" if evento and evento.enlace else ""),
            evento.fisicos if evento else None,
            PALETA["ativo"],
        )

    # -- registro ----------------------------------------------------------

    def _preencher_registro(self) -> None:
        self._texto_registro.configure(state="normal")
        self._texto_registro.delete("1.0", "end")
        if self._resultado:
            for posicao, evento in enumerate(self._resultado.eventos):
                marcas: Tuple[str, ...] = ()
                if posicao % 2:
                    marcas += ("alternada",)
                if evento.descarte:
                    marcas += ("descarte",)
                self._texto_registro.insert("end", evento.linha + "\n", marcas)
        self._texto_registro.configure(state="disabled")

    def _destacar_registro(self) -> None:
        self._texto_registro.configure(state="normal")
        self._texto_registro.tag_remove("atual", "1.0", "end")
        if self._indice >= 0:
            linha = self._indice + 1
            self._texto_registro.tag_add("atual", f"{linha}.0", f"{linha}.end+1c")
            self._texto_registro.see(f"{linha}.0")
        self._texto_registro.configure(state="disabled")

    def _salvar_registro(self) -> None:
        if not self._resultado:
            messagebox.showinfo(
                "Nada para salvar",
                "Execute uma simulação antes de salvar o registro.",
                parent=self,
            )
            return
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar registro de eventos",
            initialdir=pasta_do_programa(),
            initialfile=f"registro_{self._resultado.cenario.codigo.lower()}.txt",
            defaultextension=".txt",
            filetypes=[("Arquivo de texto", "*.txt"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return
        try:
            destino = salvar(
                caminho,
                self._resultado.eventos,
                self._resultado.resumo,
                titulo=(
                    f"Simulador do modelo OSI — {self._resultado.cenario.nome_exibicao}"
                ),
            )
        except OSError as erro:
            messagebox.showerror("Registro não salvo", str(erro), parent=self)
            return
        self._informar(f"Registro salvo em {destino}", "ok")

    # -- eficiencia --------------------------------------------------------

    def _atualizar_eficiencia(self) -> None:
        self._texto_eficiencia.configure(state="normal")
        self._texto_eficiencia.delete("1.0", "end")
        linhas: List[str] = []
        if self._resultado and self._resultado.resumo:
            linhas.extend(self._resultado.resumo.como_linhas())
            linhas.append("")
        referencia = self._eficiencias_referencia
        if referencia:
            c1, c2 = referencia.get("C1"), referencia.get("C2")
            if c1 and c2:
                linhas.append("Comparação exigida no enunciado")
                linhas.append(
                    f"  C1 (1 enlace)   {c1.octetos_uteis} B úteis / "
                    f"{c1.octetos_transmitidos} B transmitidos = {c1.eficiencia_percentual}"
                )
                linhas.append(
                    f"  C2 (4 enlaces)  {c2.octetos_uteis} B úteis / "
                    f"{c2.octetos_transmitidos} B transmitidos = {c2.eficiencia_percentual}"
                )
        linhas.append("")
        linhas.append(
            f"Cabeçalhos: L5={TAMANHO_CABECALHO[5]} L4={TAMANHO_CABECALHO[4]} "
            f"L3={TAMANHO_CABECALHO[3]} L2={TAMANHO_CABECALHO[2]}+{TAMANHO_FINALIZADOR}"
        )
        linhas.append(
            f"Segmentação: acima de {LIMITE_SEGMENTACAO} B, "
            f"{CARGA_POR_SEGMENTO} B por segmento"
        )
        self._texto_eficiencia.insert("1.0", "\n".join(linhas))
        self._texto_eficiencia.configure(state="disabled")

    def _atualizar_tamanho_mensagem(self) -> None:
        octetos = len(self._var_mensagem.get().encode("utf-8"))
        segmentada = octetos + TAMANHO_CABECALHO[5] > LIMITE_SEGMENTACAO
        self._rotulo_tamanho.configure(
            text=f"{octetos} octetos" + (" · será segmentada" if segmentada else ""),
            foreground=PALETA["ativo"] if segmentada else PALETA["tinta_fraca"],
        )

    # -- tabelas -----------------------------------------------------------

    def _mostrar_tabelas(self) -> None:
        if self._topologia is None:
            return
        janela = tk.Toplevel(self)
        janela.title("Tabelas de encaminhamento")
        janela.configure(background=PALETA["fundo"])
        janela.geometry("620x500")
        janela.transient(self)

        caderno = ttk.Notebook(janela)
        caderno.pack(fill="both", expand=True, padx=14, pady=(14, 6))
        for roteador in sorted(self._topologia.roteadores()):
            aba = ttk.Frame(caderno, padding=8)
            caderno.add(aba, text=roteador)
            aba.columnconfigure(0, weight=1)
            aba.rowconfigure(0, weight=1)
            tabela = ttk.Treeview(
                aba,
                columns=("destino", "salto", "custo", "interface"),
                show="headings",
                height=12,
            )
            for coluna, titulo, largura, alinhamento in (
                ("destino", "Rede de destino", 170, "w"),
                ("salto", "Próximo salto", 150, "w"),
                ("custo", "Custo", 70, "center"),
                ("interface", "Interface", 110, "w"),
            ):
                tabela.heading(coluna, text=titulo)
                tabela.column(coluna, width=largura, anchor=alinhamento)
            for posicao, rota in enumerate(self._topologia.tabela_encaminhamento(roteador)):
                tabela.insert(
                    "",
                    "end",
                    values=(
                        rota.destino,
                        rota.proximo_salto or "entrega direta",
                        rota.custo,
                        rota.interface,
                    ),
                    tags=("par",) if posicao % 2 else (),
                )
            tabela.tag_configure("par", background=PALETA["painel_alt"])
            tabela.grid(row=0, column=0, sticky="nsew")
            rolagem = ttk.Scrollbar(aba, orient="vertical", command=tabela.yview)
            rolagem.grid(row=0, column=1, sticky="ns")
            tabela.configure(yscrollcommand=rolagem.set)

        ttk.Label(
            janela,
            text=(
                "Rotas calculadas a partir dos custos do arquivo de topologia, "
                "pelo algoritmo de menor custo."
            ),
            wraplength=580,
            padding=(14, 0, 14, 14),
        ).pack(anchor="w")

    # -- estado ------------------------------------------------------------

    def _informar(self, mensagem: str, tipo: str = "info") -> None:
        cores = {
            "info": PALETA["estrutura"],
            "ok": PALETA["entrega"],
            "aviso": PALETA["ativo"],
            "erro": PALETA["erro"],
        }
        self._ponto_estado.configure(foreground=cores.get(tipo, PALETA["estrutura"]))
        self._barra_estado.configure(text=mensagem)

    def _definir_icone(self) -> None:
        """Aplica o ícone da janela e da barra de tarefas."""
        if getattr(sys, "_MEIPASS", None):
            # Empacotado: o arquivo foi extraído para dentro do _MEIPASS.
            candidatos = [
                os.path.join(sys._MEIPASS, "recursos", "icone.ico"),
                os.path.join(sys._MEIPASS, "icone.ico"),
            ]
        else:
            # Código-fonte: recursos/ fica ao lado do pacote simulador/.
            raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidatos = [os.path.join(raiz, "recursos", "icone.ico")]

        for caminho in candidatos:
            if os.path.exists(caminho):
                try:
                    self.iconbitmap(caminho)
                except tk.TclError:  # .ico não é aceito fora do Windows
                    pass
                return


def executar(caminho_topologia: Optional[str] = None) -> None:
    """Abre a janela do simulador."""
    preparar_dpi()
    aplicacao = AplicacaoSimulador(caminho_topologia)
    aplicacao.mainloop()
