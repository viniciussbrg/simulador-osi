# -*- coding: utf-8 -*-
"""Interface grafica em tkinter.

A interface consome a lista de eventos produzida pelo motor de simulacao.
Ela NUNCA chama metodos de camada: apenas le eventos.

Requisitos de visualizacao atendidos:
V1 - Mapa da rede com destaque do caminho e rotulos de interfaces (e0, e1, eth0...)
V2 - Pilhas de camadas com camada ativa destacada (em destaque especial a L3 dos roteadores)
V3 - Unidade de dados desenhada com blocos de cabecalhos
V4 - Pares de enderecos logicos e fisicos visiveis simultaneamente
V5 - Controle de execucao (passo a passo, continuo, pausa, velocidades)
V6 - Registro de eventos rolavel + salvar em arquivo
V7 - Alternancia entre pilha OSI e pilha TCP/IP
"""

from __future__ import annotations

import math
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Any

from . import config
from .cenarios import CENARIOS, MENSAGEM_CURTA, MENSAGEM_LONGA
from .eventos import Evento, formatar_evento
from .motor import Motor, ResultadoSimulacao
from .rede import ErroTopologia, Topologia


# ---------------------------------------------------------------------------
# Cores e Estilos
# ---------------------------------------------------------------------------

CORES_CAMADAS = {
    7: "#E74C3C",  # vermelho — aplicacao
    6: "#E67E22",  # laranja — apresentacao
    5: "#F1C40F",  # amarelo — sessao
    4: "#2ECC71",  # verde — transporte
    3: "#3498DB",  # azul — rede
    2: "#9B59B6",  # roxo — enlace
    1: "#1ABC9C",  # verde-agua — fisica
}

NOMES_CAMADAS_OSI = {
    7: "Aplicacao",
    6: "Apresentacao",
    5: "Sessao",
    4: "Transporte",
    3: "Rede",
    2: "Enlace",
    1: "Fisica",
}

NOMES_CAMADAS_TCPIP = {
    7: "Aplicacao",
    6: "Aplicacao",
    5: "Aplicacao",
    4: "Transporte",
    3: "Internet",
    2: "Acesso a Rede",
    1: "Acesso a Rede",
}

COR_ATIVO = "#FFD700"          # Dourado vibrante para destaque
COR_ROTA_DESTAQUE = "#FF5722"    # Laranja/vermelho para decisao de rota
COR_FUNDO = "#1E272C"           # Azul escuro grafite
COR_FUNDO_PAINEL = "#263238"    # Tom para paineis
COR_FUNDO_CLARO = "#37474F"     # Tom medio
COR_TEXTO = "#ECEFF1"
COR_ENLACE = "#546E7A"
COR_ENLACE_ATIVO = "#E74C3C"
COR_DISPOSITIVO = "#0288D1"
COR_ROTEADOR = "#7E57C2"

# Fundos escuros dos canvases internos (antes espalhados como hex soltos,
# alguns duplicados). Mantidos como tons ligeiramente distintos entre si,
# apenas nomeados para facilitar reuso e futuras trocas de tema.
COR_FUNDO_CANVAS = "#182226"      # mapa da rede e area de pilhas
COR_FUNDO_CANVAS_ALT = "#162026"  # painel de explicacao pedagogica
COR_FUNDO_PDU = "#1C272C"         # canvas de desenho do PDU
COR_FUNDO_CONSOLE = "#101820"     # barra de status e janela de tabelas
COR_ROTULO_OCTETO = "#1A2429"     # texto do rotulo de octeto no desenho do PDU


OPCOES_CENARIOS = [
    ("C2", "C2 / E2 — Entrega indireta (caso central H1 \u2192 H4)"),
    ("C1", "C1 / E1 — Entrega direta (mesma LAN H1 \u2192 H2)"),
    ("C3", "C3 / E3 — Demultiplexacao (H1 e H2 para H4)"),
    ("C4", "C4 / E4 — Falha de enlace (queda de R1-R4)"),
    ("C5", "C5 / E5 — Destino inalcancavel (10.0.9.10)"),
    ("C6", "C6 / E6 — Erro de transmissao (bit alterado R4-R3)"),
    ("C7", "C7 / E7 — Mensagem longa (3 segmentos 40+40+24B)"),
    ("CUSTOM", "Personalizado — Escolher parametros manualmente"),
]


# ---------------------------------------------------------------------------
# Explicacao Didatica por Evento
# ---------------------------------------------------------------------------


def gerar_explicacao_didatica(evento: Evento) -> str:
    """Produz uma explicacao pedagogica e clara do que ocorre no evento atual."""
    disp = evento.dispositivo
    cam = evento.camada
    acao = evento.acao
    desc = evento.descricao
    tam = evento.tamanho

    if cam == "L7" and acao == "GERA":
        return (
            f"💡 [Camada 7 — Aplicação | {disp}]\n"
            f"O processo de origem gera a mensagem. Esta camada atende diretamente ao "
            f"usuário e identifica a aplicação pelo nome de processo."
        )

    if cam == "L6" and acao == "CODIFICA":
        return (
            f"💡 [Camada 6 — Apresentação | {disp}]\n"
            f"Converte o texto para octetos UTF-8 e aplica cifra simétrica (XOR chave 'OSI'). "
            f"Os dados viajarão cifrados e só serão decifrados pelo destino final (Restrição R5)."
        )

    if cam == "L5" and acao == "ABRE":
        return (
            f"💡 [Camada 5 — Sessão | {disp}]\n"
            f"Abre o diálogo e anexa cabeçalho de 4 octetos com identificador único de sessão "
            f"({desc.split()[-1] if 'S-' in desc else 'S-xxxx'}), gerenciando a conexão."
        )

    if cam == "L4" and acao == "SEGMENTA":
        return (
            f"💡 [Camada 4 — Transporte | {disp}]\n"
            f"Anexa cabeçalho de 8 octetos com portas de origem e destino ({desc}). "
            f"Controla a segmentação e a integridade da entrega processo a processo."
        )

    if cam == "L4" and acao == "ARMAZENA":
        return (
            f"💡 [Camada 4 — Transporte | {disp}]\n"
            f"O nó de destino armazena o segmento recebido e aguarda os demais segmentos "
            f"para realizar a remontagem ordenada completa (Restrição R6)."
        )

    if cam == "L4" and acao == "REMONTA":
        return (
            f"💡 [Camada 4 — Transporte | {disp}]\n"
            f"Todos os segmentos chegaram ao destino! A Camada 4 remonta a mensagem original "
            f"na ordem exata antes de repassar à Camada 5 (Restrição R6)."
        )

    if cam == "L3" and acao == "ENCAPSULA":
        return (
            f"💡 [Camada 3 — Rede | {disp}]\n"
            f"Insere o cabeçalho IP (20 octetos) com o par de endereços lógicos. "
            f"Estes IPs são fixos e permanecem idênticos até o destino (Restrição R3)."
        )

    if cam == "L3" and acao == "ROTEIA":
        if "proximo salto" in desc.lower() or "próximo salto" in desc.lower():
            return (
                f"💡 [Camada 3 — Rede | {disp}]\n"
                f"Host consulta sua tabela de roteamento local e seleciona a interface "
                f"para entrega ao roteador gateway da sub-rede."
            )
        return (
            f"★ [DECISÃO DE ROTA NA CAMADA 3 | {disp}]\n"
            f"O roteador inspeciona apenas o IP de destino e consulta sua tabela Dijkstra. "
            f"O roteador opera estritamente nas Camadas 1 a 3 e jamais lê portas (Restrições R1 e R4)."
        )

    if cam == "L3" and acao == "DESCARTA":
        return (
            f"⚠️ [DESCARTE POR DESTINO INALCANÇÁVEL | {disp}]\n"
            f"O IP de destino não pertence a nenhuma sub-rede alcançável. O pacote é "
            f"descartado na Camada 3 do roteador com registro explícito (Cenário C5)."
        )

    if cam == "L2" and acao == "ENQUADRA":
        return (
            f"💡 [Camada 2 — Enlace | {disp}]\n"
            f"Constrói um NOVO quadro com cabeçalho de 14 octetos (endereços MAC locais deste salto) "
            f"e calcula o finalizador FCS de 4 octetos (CRC-32) para verificação de erro (Restrição R2)."
        )

    if cam == "L2" and acao == "DESENQUADRA":
        return (
            f"💡 [Camada 2 — Enlace | {disp}]\n"
            f"Valida a integridade pelo CRC-32 (sem erros!). O quadro recebido é DESCARTADO "
            f"e o pacote IP interno é entregue intacto à Camada 3 (Restrição R2)."
        )

    if cam == "L2" and acao == "ERRO":
        return (
            f"🛑 [ERRO DE CRC DETECTADO | {disp}]\n"
            f"Inconsistência de bits detectada pela verificação CRC-32! O quadro corrompido é "
            f"descartado na Camada 2 sem que nenhuma camada superior seja acionada (Restrição R9)."
        )

    if cam == "L1" and acao == "TRANSMITE":
        return (
            f"⚡ [Camada 1 — Física | {disp}]\n"
            f"Converte os {tam} octetos do quadro em sequência física de {tam * 8} bits "
            f"e transmite pelo cabo do enlace de rede correspondente."
        )

    if cam == "L1" and acao == "RECEBE":
        return (
            f"⚡ [Camada 1 — Física | {disp}]\n"
            f"A placa física detecta o sinal de {tam * 8} bits no meio físico e reconstrói "
            f"os {tam} octetos do quadro, entregando-o à Camada 2."
        )

    if cam == "L5" and acao in ("RECEBE", "FECHA"):
        return (
            f"💡 [Camada 5 — Sessão | {disp}]\n"
            f"Reconhece o identificador de sessão ativo, valida o diálogo e encerra a conexão."
        )

    if cam == "L6" and acao == "DECODIFICA":
        return (
            f"💡 [Camada 6 — Apresentação | {disp}]\n"
            f"Aplica a chave de decifração simétrica reversível e reconverte os octetos UTF-8 "
            f"no texto original. Somente a Camada 6 do destino decifra a carga útil (Restrição R5)."
        )

    if cam == "L7" and acao == "ENTREGA":
        return (
            f"🎉 [Camada 7 — Aplicação | {disp}]\n"
            f"Mensagem entregue com perfeição ao processo de destino! Comunicação fim a fim "
            f"concluída com êxito."
        )

    return f"ℹ️ [{cam} em {disp} | {acao}]\n{desc} ({tam} octetos)."


# ---------------------------------------------------------------------------
# Janela Principal
# ---------------------------------------------------------------------------


class JanelaPrincipal:
    """Interface grafica completa, intuitiva e didatica do simulador OSI."""

    def __init__(self) -> None:
        self.raiz = tk.Tk()
        self.raiz.title("Simulador do Modelo OSI — Comunicação de Dados")

        # Geometria ergonômica centralizada adaptada à resolução da tela
        largura_tela = self.raiz.winfo_screenwidth()
        altura_tela = self.raiz.winfo_screenheight()
        largura_janela = min(1360, max(1100, largura_tela - 80))
        altura_janela = min(840, max(680, altura_tela - 90))
        pos_x = max(10, (largura_tela - largura_janela) // 2)
        pos_y = max(10, (altura_tela - altura_janela) // 2)
        self.raiz.geometry(f"{largura_janela}x{altura_janela}+{pos_x}+{pos_y}")
        self.raiz.minsize(1050, 620)
        self.raiz.configure(bg=COR_FUNDO)

        # Estado
        self.topologia: Topologia | None = None
        self.resultado: ResultadoSimulacao | None = None
        self.eventos: list[Evento] = []
        self.passo_atual = 0
        self.executando = False
        self.modo_pilha = "OSI"  # ou "TCP/IP"
        self._timer_id: str | None = None
        self._posicoes_mapa: dict[str, tuple[int, int]] = {}
        self._erro_topologia = ""

        # Carrega topologia
        try:
            self.topologia = Topologia()
        except ErroTopologia as e:
            self._erro_topologia = str(e)
        except (OSError, ValueError, TypeError) as e:
            self._erro_topologia = (
                f"Falha inesperada ao carregar a topologia: "
                f"{type(e).__name__}: {e}"
            )
            traceback.print_exc()

        self._configurar_estilos()
        self._criar_interface()

        if self._erro_topologia:
            self._marcar_topologia_indisponivel(self._erro_topologia)

    def _controles_dependentes_da_topologia(self) -> list[tk.Misc]:
        """Devolve controles que exigem uma topologia valida."""
        controles = [
            self.btn_carregar, self.btn_voltar, self.btn_passo,
            self.btn_continuo, self.btn_reiniciar, self.cb_origem,
            self.cb_destino, self.cb_queda, self.cb_erro,
        ]
        if hasattr(self, "btn_pausa"):
            controles.append(self.btn_pausa)
        return controles

    def _marcar_topologia_indisponivel(self, mensagem: str) -> None:
        """Mantem a janela aberta e bloqueia somente operacoes impossiveis."""
        self.topologia = None
        self._erro_topologia = mensagem
        self._pausar()

        for controle in self._controles_dependentes_da_topologia():
            try:
                controle.configure(state=tk.DISABLED)
            except tk.TclError:
                pass

        self.lbl_descricao.config(
            text="Topologia indisponivel. Use 'Trocar Topologia JSON'."
        )
        self.lbl_explicacao.config(
            text=(
                "Nao foi possivel carregar a topologia.\n\n"
                f"{mensagem}\n\n"
                "Selecione outro arquivo JSON para continuar."
            )
        )
        self.canvas_mapa.delete("all")
        self.canvas_pilhas.delete("all")
        self._limpar_pdu()
        self._limpar_enderecos()

        messagebox.showerror(
            "Topologia indisponivel",
            f"{mensagem}\n\nA janela continuara aberta para recuperacao.",
            parent=self.raiz,
        )

    def _marcar_topologia_disponivel(self) -> None:
        """Reabilita a interface depois de carregar uma topologia valida."""
        self._erro_topologia = ""
        for controle in self._controles_dependentes_da_topologia():
            try:
                controle.configure(
                    state=tk.DISABLED if controle is self.btn_pausa else tk.NORMAL
                )
            except tk.TclError:
                pass
        self._ao_selecionar_cenario()
        self._desenhar_mapa()
        self._desenhar_pilhas_vazias()
        self.lbl_explicacao.config(
            text="Topologia carregada. Escolha um cenário e clique em 'Iniciar'."
        )

    def _configurar_estilos(self) -> None:
        """Configura aparencia moderna dos componentes ttk."""
        estilo = ttk.Style(self.raiz)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass

        estilo.configure("TLabel", background=COR_FUNDO_PAINEL, foreground=COR_TEXTO)
        estilo.configure("TLabelframe", background=COR_FUNDO_PAINEL, foreground=COR_TEXTO)
        estilo.configure("TLabelframe.Label", background=COR_FUNDO_PAINEL, foreground="#90CAF9",
                         font=("Arial", 10, "bold"))
        estilo.configure("TFrame", background=COR_FUNDO_PAINEL)
        estilo.configure("TRadiobutton", background=COR_FUNDO_PAINEL, foreground=COR_TEXTO)
        estilo.configure("TButton", font=("Arial", 9, "bold"))

    # ===================================================================
    # Construcao da interface
    # ===================================================================

    def _criar_interface(self) -> None:
        """Monta o leiaute de tres colunas."""
        self.frame_principal = ttk.PanedWindow(self.raiz, orient=tk.HORIZONTAL)
        self.frame_principal.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Coluna 1: Controles, parametros manuais e registro de eventos
        self.frame_esquerda = ttk.Frame(self.frame_principal, width=380)
        self.frame_principal.add(self.frame_esquerda, weight=1)

        # Coluna 2: Mapa da rede + Explicacao didatica + PDU desenhada + Enderecos vigentes
        self.frame_central = ttk.Frame(self.frame_principal, width=640)
        self.frame_principal.add(self.frame_central, weight=2)

        # Coluna 3: Pilhas de camadas + Eficiencia comparativa
        self.frame_direita = ttk.Frame(self.frame_principal, width=360)
        self.frame_principal.add(self.frame_direita, weight=1)

        self._criar_controles()
        self._criar_mapa()
        self._criar_explicacao_didatica()
        self._criar_area_pdu()
        self._criar_area_enderecos()
        self._criar_pilhas()
        self._criar_registro()
        self._criar_eficiencia()

    # -- Controles (Coluna Esquerda) ---------------------------------------

    def _criar_controles(self) -> None:
        """Painel de controle: cenario, parametros manuais, execucao e velocidade."""
        frame = ttk.LabelFrame(self.frame_esquerda, text="  1. Painel de Controle  ", padding=10)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # Atalhos rápidos para cada cenário oficial (1 clique)
        ttk.Label(frame, text="Atalhos Rápidos de Cenário:").pack(anchor=tk.W)
        f_quick = ttk.Frame(frame)
        f_quick.pack(fill=tk.X, pady=(2, 5))
        for cid in ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]:
            b = tk.Button(
                f_quick, text=cid, width=3, font=("Segoe UI", 8, "bold"),
                bg="#37474F", fg="#ECEFF1", activebackground="#0288D1", activeforeground="white",
                relief=tk.RAISED, bd=1, cursor="hand2",
                command=lambda c=cid: self._selecionar_cenario_rapido(c)
            )
            b.pack(side=tk.LEFT, padx=1)

        # Seletor de Cenario
        ttk.Label(frame, text="Lista de Cenários:").pack(anchor=tk.W, pady=(2, 0))
        self.var_cenario_ext = tk.StringVar(value=OPCOES_CENARIOS[0][1])
        nomes_combo = [desc for _, desc in OPCOES_CENARIOS]
        combo_cen = ttk.Combobox(frame, textvariable=self.var_cenario_ext, state="readonly",
                                 values=nomes_combo, width=42)
        combo_cen.pack(fill=tk.X, pady=2)
        combo_cen.bind("<<ComboboxSelected>>", self._ao_selecionar_cenario)

        self.lbl_descricao = ttk.Label(frame, text="", wraplength=340, foreground="#B0BEC5",
                                       font=("Arial", 8))
        self.lbl_descricao.pack(anchor=tk.W, pady=(2, 6))

        # Parametros Manuais / Personalizados
        self.frame_custom = ttk.LabelFrame(frame, text="  Parametros da Comunicacao  ", padding=6)
        self.frame_custom.pack(fill=tk.X, pady=4)

        # Linha Origem e Destino
        f_od = ttk.Frame(self.frame_custom)
        f_od.pack(fill=tk.X, pady=2)

        ttk.Label(f_od, text="Origem:").pack(side=tk.LEFT)
        self.var_origem = tk.StringVar(value="H1")
        self.cb_origem = ttk.Combobox(f_od, textvariable=self.var_origem, width=5, state="readonly",
                                      values=["H1", "H2", "H3", "H4", "H5"])
        self.cb_origem.pack(side=tk.LEFT, padx=3)

        ttk.Label(f_od, text="Destino:").pack(side=tk.LEFT, padx=(6, 0))
        self.var_destino = tk.StringVar(value="10.0.3.10")
        self.cb_destino = ttk.Combobox(f_od, textvariable=self.var_destino, width=13,
                                       values=["10.0.1.10 (H1)", "10.0.1.11 (H2)", "10.0.2.10 (H3)",
                                               "10.0.3.10 (H4)", "10.0.3.11 (H5)", "10.0.9.10 (Inalcancavel)"])
        self.cb_destino.pack(side=tk.LEFT, padx=3)

        # Linha Falhas e Injeção
        f_falhas = ttk.Frame(self.frame_custom)
        f_falhas.pack(fill=tk.X, pady=2)

        ttk.Label(f_falhas, text="Queda Enlace:").pack(side=tk.LEFT)
        self.var_queda_enlace = tk.StringVar(value="Nenhum")
        self.cb_queda = ttk.Combobox(f_falhas, textvariable=self.var_queda_enlace, width=8, state="readonly",
                                     values=["Nenhum", "R1-R4", "R1-R2", "R2-R3", "R3-R4"])
        self.cb_queda.pack(side=tk.LEFT, padx=2)

        ttk.Label(f_falhas, text="Erro CRC:").pack(side=tk.LEFT, padx=(4, 0))
        self.var_erro_crc = tk.StringVar(value="Nenhum")
        self.cb_erro = ttk.Combobox(f_falhas, textvariable=self.var_erro_crc, width=8, state="readonly",
                                     values=["Nenhum", "R3-R4", "R1-R4", "R1-R2", "R2-R3"])
        self.cb_erro.pack(side=tk.LEFT, padx=2)

        # Mensagem
        ttk.Label(self.frame_custom, text="Mensagem de Carga Util:").pack(anchor=tk.W, pady=(4, 0))
        self.entrada_mensagem = ttk.Entry(self.frame_custom, width=42)
        self.entrada_mensagem.insert(0, MENSAGEM_CURTA)
        self.entrada_mensagem.pack(fill=tk.X, pady=2)

        # Botoes de execucao (V5)
        frame_botoes = ttk.Frame(frame)
        frame_botoes.pack(fill=tk.X, pady=6)

        self.btn_carregar = ttk.Button(frame_botoes, text="▶ Iniciar",
                                       command=self._executar_simulacao)
        self.btn_carregar.pack(side=tk.LEFT, padx=2)

        self.btn_voltar = ttk.Button(frame_botoes, text="⏮ Voltar",
                                     command=self._passo_anterior)
        self.btn_voltar.pack(side=tk.LEFT, padx=2)

        self.btn_passo = ttk.Button(frame_botoes, text="⏭ Avançar",
                                     command=self._proximo_passo)
        self.btn_passo.pack(side=tk.LEFT, padx=2)

        self.btn_continuo = ttk.Button(frame_botoes, text="⏩ Contínuo",
                                        command=self._executar_continuo)
        self.btn_continuo.pack(side=tk.LEFT, padx=2)

        self.btn_pausa = ttk.Button(frame_botoes, text="⏸ Pausa",
                                     command=self._pausar, state=tk.DISABLED)
        self.btn_pausa.pack(side=tk.LEFT, padx=2)

        self.btn_reiniciar = ttk.Button(frame_botoes, text="↺ Reiniciar",
                                         command=self._reiniciar)
        self.btn_reiniciar.pack(side=tk.LEFT, padx=2)

        # Velocidade de Reproducao (V5)
        ttk.Label(frame, text="Velocidade de Reproducao:").pack(anchor=tk.W, pady=(4, 0))
        self.var_velocidade = tk.IntVar(value=config.VELOCIDADE_PADRAO)
        frame_vel = ttk.Frame(frame)
        frame_vel.pack(fill=tk.X)
        for idx, (rotulo, _) in enumerate(config.VELOCIDADES):
            rb = ttk.Radiobutton(frame_vel, text=rotulo, value=idx,
                                 variable=self.var_velocidade)
            rb.pack(side=tk.LEFT, padx=2)

        # Alternancia entre pilhas OSI e TCP/IP (V7)
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        f_pilha_sel = ttk.Frame(frame)
        f_pilha_sel.pack(fill=tk.X)
        ttk.Label(f_pilha_sel, text="Pilha:").pack(side=tk.LEFT)
        self.var_pilha = tk.StringVar(value="OSI")
        ttk.Radiobutton(f_pilha_sel, text="OSI (7 camadas)", value="OSI",
                        variable=self.var_pilha,
                        command=self._trocar_pilha).pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(f_pilha_sel, text="TCP/IP (4 camadas)", value="TCP/IP",
                        variable=self.var_pilha,
                        command=self._trocar_pilha).pack(side=tk.LEFT, padx=6)

        # Acoes adicionais: Topologia externa (R1) e Tabelas de Roteamento (R5)
        f_extras = ttk.Frame(frame)
        f_extras.pack(fill=tk.X, pady=(6, 2))
        ttk.Button(f_extras, text="📋 Tabelas de Roteamento",
                   command=self._abrir_tabelas_roteamento).pack(side=tk.LEFT, padx=2)
        ttk.Button(f_extras, text="📁 Trocar Topologia JSON",
                   command=self._trocar_arquivo_topologia).pack(side=tk.LEFT, padx=2)

        # Barra de progresso
        self.lbl_progresso = ttk.Label(frame, text="Passo: 0 / 0", font=("Consolas", 9, "bold"))
        self.lbl_progresso.pack(anchor=tk.W, pady=(5, 0))
        self.barra_progresso = ttk.Progressbar(frame, mode="determinate")
        self.barra_progresso.pack(fill=tk.X, pady=2)

        self._ao_selecionar_cenario()

    # -- Mapa da Rede (Coluna Central - V1) --------------------------------

    def _criar_mapa(self) -> None:
        """Canvas com o mapa da rede, interfaces e caminho destacado (V1)."""
        frame = ttk.LabelFrame(self.frame_central, text="  2. Mapa da Topologia de Rede (Figura 1)  ", padding=5)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas_mapa = tk.Canvas(frame, bg=COR_FUNDO_CANVAS, highlightthickness=0)
        self.canvas_mapa.pack(fill=tk.BOTH, expand=True)
        self.canvas_mapa.bind("<Configure>", lambda e: self._desenhar_mapa())

    # -- Explicação Didática (Coluna Central) -------------------------------

    def _criar_explicacao_didatica(self) -> None:
        """Card didatico destacando a explicacao em linguagem simples do passo corrente."""
        frame = ttk.LabelFrame(self.frame_central, text="  💡 O que está acontecendo agora (Didática do Passo)  ", padding=6)
        frame.pack(fill=tk.X, padx=5, pady=3)

        self.lbl_explicacao = tk.Label(
            frame,
            text="Escolha um cenário acima e clique em '▶ Iniciar' ou use os atalhos C1..C7.",
            font=("Segoe UI", 9, "bold"),
            bg=COR_FUNDO_CANVAS_ALT,
            fg="#FFE082",
            justify=tk.LEFT,
            anchor="w",
            wraplength=600,
            padx=8,
            pady=6,
        )
        self.lbl_explicacao.pack(fill=tk.X, expand=True)

    # -- Unidade de Dados (Coluna Central - V3) -----------------------------

    def _criar_area_pdu(self) -> None:
        """Desenho da unidade de dados com blocos de cabecalhos (V3)."""
        frame = ttk.LabelFrame(self.frame_central, text="  3. Unidade de Dados de Protocolo (PDU - V3)  ", padding=5)
        frame.pack(fill=tk.X, padx=5, pady=4)

        self.lbl_nome_unidade = ttk.Label(frame, text="Unidade: —", font=("Consolas", 10, "bold"),
                                          foreground="#80D8FF")
        self.lbl_nome_unidade.pack(anchor=tk.W, pady=(0, 2))

        self.canvas_pdu = tk.Canvas(frame, bg=COR_FUNDO_PDU, height=65, highlightthickness=0)
        self.canvas_pdu.pack(fill=tk.X)

    # -- Enderecos Logicos e Fisicos (Coluna Central - V4) ------------------

    def _criar_area_enderecos(self) -> None:
        """Exibicao simultanea dos dois pares de enderecos (V4)."""
        frame = ttk.LabelFrame(self.frame_central, text="  4. Enderecamento Vigente (V4)  ", padding=5)
        frame.pack(fill=tk.X, padx=5, pady=4)

        f_grid = ttk.Frame(frame)
        f_grid.pack(fill=tk.X)

        # Logicos (Origem ao Destino - Fixos)
        f_log = ttk.LabelFrame(f_grid, text="Enderecos Logicos (Camada 3 — Fixos)", padding=5)
        f_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.lbl_ip_origem = ttk.Label(f_log, text="Origem:  —", font=("Consolas", 9, "bold"),
                                        foreground="#4FC3F7")
        self.lbl_ip_origem.pack(anchor=tk.W)
        self.lbl_ip_destino = ttk.Label(f_log, text="Destino: —", font=("Consolas", 9, "bold"),
                                         foreground="#4FC3F7")
        self.lbl_ip_destino.pack(anchor=tk.W)

        # Fisicos (Salto a Salto - Variaveis)
        f_fis = ttk.LabelFrame(f_grid, text="Enderecos Fisicos (Camada 2 — Salto Atual)", padding=5)
        f_fis.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.lbl_mac_origem = ttk.Label(f_fis, text="Origem:  —", font=("Consolas", 9, "bold"),
                                         foreground="#CE93D8")
        self.lbl_mac_origem.pack(anchor=tk.W)
        self.lbl_mac_destino = ttk.Label(f_fis, text="Destino: —", font=("Consolas", 9, "bold"),
                                          foreground="#CE93D8")
        self.lbl_mac_destino.pack(anchor=tk.W)

    # -- Pilhas de Camadas (Coluna Direita - V2) ----------------------------

    def _criar_pilhas(self) -> None:
        """Area para exibir as pilhas de camadas dos dispositivos participantes (V2)."""
        frame = ttk.LabelFrame(self.frame_direita, text="  5. Pilhas de Camadas nos Dispositivos (V2)  ", padding=5)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas_pilhas = tk.Canvas(frame, bg=COR_FUNDO_CANVAS, highlightthickness=0)
        self.canvas_pilhas.pack(fill=tk.BOTH, expand=True)
        self.canvas_pilhas.bind("<Configure>", lambda e: self._redesenhar_pilhas_atual())

    # -- Registro de Eventos (Coluna Esquerda - V6) -------------------------

    def _criar_registro(self) -> None:
        """Area de texto rolavel para o registro oficial de eventos (V6)."""
        frame = ttk.LabelFrame(self.frame_esquerda, text="  6. Registro Oficial de Eventos (V6)  ", padding=5)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.texto_registro = scrolledtext.ScrolledText(
            frame, height=13, font=("Consolas", 8), bg=COR_FUNDO_CONSOLE,
            fg="#69F0AE", insertbackground="#69F0AE", state=tk.DISABLED,
            wrap=tk.NONE,
        )
        self.texto_registro.pack(fill=tk.BOTH, expand=True)

        f_btns = ttk.Frame(frame)
        f_btns.pack(fill=tk.X, pady=3)
        ttk.Button(f_btns, text="💾 Salvar em Arquivo (.txt)",
                   command=self._salvar_registro).pack(side=tk.LEFT, padx=2)
        ttk.Button(f_btns, text="Limpar",
                   command=self._limpar_registro).pack(side=tk.LEFT, padx=2)

    # -- Eficiencia e Comparativo (Coluna Direita) -------------------------

    def _criar_eficiencia(self) -> None:
        """Painel com metricas do empilhamento e comparativo do enunciado."""
        frame = ttk.LabelFrame(self.frame_direita, text="  7. Custo do Empilhamento (Secao 6)  ", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        self.lbl_dados = ttk.Label(frame, text="Dados uteis da mensagem: — octetos", font=("Arial", 9))
        self.lbl_dados.pack(anchor=tk.W)
        self.lbl_transmitidos = ttk.Label(frame, text="Total transmitido nos enlaces: — octetos", font=("Arial", 9))
        self.lbl_transmitidos.pack(anchor=tk.W)
        self.lbl_eficiencia = ttk.Label(frame, text="Eficiencia (η = dados / transmitidos): —",
                                         font=("Consolas", 10, "bold"), foreground="#69F0AE")
        self.lbl_eficiencia.pack(anchor=tk.W, pady=2)
        self.lbl_sobrecarga = ttk.Label(frame, text="Sobrecarga (1 - η): —", font=("Arial", 9))
        self.lbl_sobrecarga.pack(anchor=tk.W)

        # Secao comparativa exigida na secao 6
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        ttk.Label(frame, text="Comparativo de Referencia (Enunciado):", font=("Arial", 8, "bold"),
                  foreground="#90CAF9").pack(anchor=tk.W)
        ttk.Label(frame, text="• Cenario C1 (1 enlace direto):  η = 45.7% (Sobrecarga 54.3%)",
                  font=("Consolas", 8), foreground="#B0BEC5").pack(anchor=tk.W)
        ttk.Label(frame, text="• Cenario C2 (4 enlaces centrais): η = 11.4% (Sobrecarga 88.6%)",
                  font=("Consolas", 8), foreground="#B0BEC5").pack(anchor=tk.W)

    # ===================================================================
    # Logica de Selecao e Execucao de Cenarios
    # ===================================================================

    def _selecionar_cenario_rapido(self, cid: str) -> None:
        """Seleciona e inicializa o cenario com um unico clique."""
        for c_id, desc in OPCOES_CENARIOS:
            if c_id == cid:
                self.var_cenario_ext.set(desc)
                self._ao_selecionar_cenario()
                self._executar_simulacao()
                break

    def _obter_chave_cenario(self) -> str:
        """Extrai o codigo C1..C7 ou CUSTOM da descricao selecionada."""
        texto = self.var_cenario_ext.get()
        for cid, desc in OPCOES_CENARIOS:
            if desc == texto:
                return cid
        return "C2"

    def _ao_selecionar_cenario(self, event=None) -> None:
        """Preenche automaticamente os controles conforme o cenario escolhido."""
        cid = self._obter_chave_cenario()

        if cid == "CUSTOM":
            self.lbl_descricao.config(text="Modo livre: ajuste os campos de origem, destino, falhas e mensagem.")
            return

        info = CENARIOS.get(cid, {})
        self.lbl_descricao.config(text=info.get("descricao", ""))

        # Preenchimento padrao conforme o cenario
        if cid == "C1":
            self.var_origem.set("H1")
            self.var_destino.set("10.0.1.11 (H2)")
            self.var_queda_enlace.set("Nenhum")
            self.var_erro_crc.set("Nenhum")
            self.entrada_mensagem.delete(0, tk.END)
            self.entrada_mensagem.insert(0, MENSAGEM_CURTA)
        elif cid == "C2":
            self.var_origem.set("H1")
            self.var_destino.set("10.0.3.10 (H4)")
            self.var_queda_enlace.set("Nenhum")
            self.var_erro_crc.set("Nenhum")
            self.entrada_mensagem.delete(0, tk.END)
            self.entrada_mensagem.insert(0, MENSAGEM_CURTA)
        elif cid == "C3":
            self.var_origem.set("H1")
            self.var_destino.set("10.0.3.10 (H4)")
            self.var_queda_enlace.set("Nenhum")
            self.var_erro_crc.set("Nenhum")
            self.entrada_mensagem.delete(0, tk.END)
            self.entrada_mensagem.insert(0, "Demultiplexacao H1 e H2 -> H4")
        elif cid == "C4":
            self.var_origem.set("H1")
            self.var_destino.set("10.0.3.10 (H4)")
            self.var_queda_enlace.set("R1-R4")
            self.var_erro_crc.set("Nenhum")
            self.entrada_mensagem.delete(0, tk.END)
            self.entrada_mensagem.insert(0, MENSAGEM_CURTA)
        elif cid == "C5":
            self.var_origem.set("H1")
            self.var_destino.set("10.0.9.10 (Inalcancavel)")
            self.var_queda_enlace.set("Nenhum")
            self.var_erro_crc.set("Nenhum")
            self.entrada_mensagem.delete(0, tk.END)
            self.entrada_mensagem.insert(0, MENSAGEM_CURTA)
        elif cid == "C6":
            self.var_origem.set("H1")
            self.var_destino.set("10.0.3.10 (H4)")
            self.var_queda_enlace.set("Nenhum")
            self.var_erro_crc.set("R3-R4")
            self.entrada_mensagem.delete(0, tk.END)
            self.entrada_mensagem.insert(0, MENSAGEM_CURTA)
        elif cid == "C7":
            self.var_origem.set("H1")
            self.var_destino.set("10.0.3.10 (H4)")
            self.var_queda_enlace.set("Nenhum")
            self.var_erro_crc.set("Nenhum")
            self.entrada_mensagem.delete(0, tk.END)
            self.entrada_mensagem.insert(0, MENSAGEM_LONGA)

    def _executar_simulacao(self) -> None:
        """Dispara a simulacao, aplicando os parametros configurados."""
        if self.topologia is None:
            messagebox.showerror("Erro", "Topologia nao carregada.")
            return

        self._pausar()
        self.topologia.ativar_todos()

        cid = self._obter_chave_cenario()
        msg_digitada = self.entrada_mensagem.get().strip()

        try:
            if cid == "C3":
                # Caso especial demultiplexacao multi-fluxo
                resultados = CENARIOS["C3"]["funcao"](self.topologia)
                self.resultado = resultados[0]
                for r in resultados[1:]:
                    self.resultado.eventos.extend(r.eventos)
                    self.resultado.octetos_transmitidos += r.octetos_transmitidos
                self.resultado.calcular_eficiencia()
                # Renumera passos
                self.resultado.registro.limpar()
                for idx, ev in enumerate(self.resultado.eventos, start=1):
                    ev.passo = idx
                    self.resultado.registro.adicionar(ev)
            elif cid in CENARIOS and not msg_digitada != (MENSAGEM_LONGA if cid == "C7" else MENSAGEM_CURTA):
                # Executa funcao padrao do cenario
                self.resultado = CENARIOS[cid]["funcao"](self.topologia)
            else:
                # Executa com parametros da interface (personalizado ou mensagem customizada)
                origem = self.var_origem.get()
                dest_str = self.var_destino.get().split()[0].strip()
                queda = self.var_queda_enlace.get()
                if queda == "Nenhum":
                    queda = ""
                erro = self.var_erro_crc.get()
                if erro == "Nenhum":
                    erro = ""
                texto = msg_digitada if msg_digitada else MENSAGEM_CURTA

                motor = Motor(self.topologia)
                self.resultado = motor.executar(
                    origem=origem,
                    destino_ip=dest_str,
                    texto=texto,
                    enlace_derrubado=queda,
                    enlace_com_erro=erro,
                )
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Erro na Execucao", f"Falha durante a simulacao:\n{e}")
            return

        self.eventos = self.resultado.eventos
        self.passo_atual = 0

        self.barra_progresso["maximum"] = len(self.eventos)
        self.barra_progresso["value"] = 0
        self.lbl_progresso.config(text=f"Passo: 0 / {len(self.eventos)}")

        self._limpar_registro()
        self._desenhar_mapa()
        self._atualizar_eficiencia()
        self._limpar_pdu()
        self._limpar_enderecos()
        self._desenhar_pilhas_vazias()

        if hasattr(self, "lbl_explicacao"):
            info_c = CENARIOS.get(cid, {})
            desc_c = info_c.get("descricao", "Cenário configurado.")
            self.lbl_explicacao.config(
                text=f"📌 {cid}: {desc_c}\n"
                     f"Simulação pronta no Passo 0 ({len(self.eventos)} eventos). Clique em '⏭ Avançar' ou '⏩ Contínuo'."
            )

    # -- Passos e Animacao -------------------------------------------------

    def _atualizar_explicacao(self, evento: Evento) -> None:
        """Atualiza o card didatico com explicacao em portugues claro."""
        if hasattr(self, "lbl_explicacao"):
            texto = gerar_explicacao_didatica(evento)
            self.lbl_explicacao.config(text=texto)

    def _proximo_passo(self) -> None:
        """Avanca um evento na simulacao."""
        if not self.eventos or self.passo_atual >= len(self.eventos):
            self._pausar()
            return

        evento = self.eventos[self.passo_atual]
        self.passo_atual += 1

        self._adicionar_ao_registro(evento)
        self._atualizar_mapa(evento)
        self._atualizar_pdu(evento)
        self._atualizar_enderecos(evento)
        self._atualizar_pilhas(evento)
        self._atualizar_explicacao(evento)

        self.barra_progresso["value"] = self.passo_atual
        self.lbl_progresso.config(text=f"Passo: {self.passo_atual} / {len(self.eventos)}")

        if self.passo_atual >= len(self.eventos):
            self._pausar()
            if self.resultado and hasattr(self, "lbl_explicacao"):
                status = "Concluída com Sucesso!" if self.resultado.sucesso else f"Finalizada ({self.resultado.mensagem_erro})"
                self.lbl_explicacao.config(
                    text=f"🏁 Fim da simulação: {status}\n"
                         f"Dados úteis: {self.resultado.octetos_dados}B | Transmitidos: {self.resultado.octetos_transmitidos}B | "
                         f"Eficiência η = {self.resultado.eficiencia:.1%} (Sobrecarga {self.resultado.sobrecarga:.1%})"
                )

    def _passo_anterior(self) -> None:
        """Retorna um evento na simulacao (permite rever o passo anterior)."""
        if not self.eventos or self.passo_atual <= 1:
            self._reiniciar()
            return

        self._pausar()
        self.passo_atual -= 1
        evento = self.eventos[self.passo_atual - 1]

        # Reconstroi o registro ate o passo atual
        self._limpar_registro()
        for ev in self.eventos[:self.passo_atual]:
            self._adicionar_ao_registro(ev)

        self._atualizar_mapa(evento)
        self._atualizar_pdu(evento)
        self._atualizar_enderecos(evento)
        self._atualizar_pilhas(evento)
        self._atualizar_explicacao(evento)

        self.barra_progresso["value"] = self.passo_atual
        self.lbl_progresso.config(text=f"Passo: {self.passo_atual} / {len(self.eventos)}")

    def _executar_continuo(self) -> None:
        """Inicia reproducao automatica continua."""
        if not self.eventos:
            self._executar_simulacao()
        if not self.eventos:
            return
        self.executando = True
        self.btn_pausa.config(state=tk.NORMAL)
        self.btn_continuo.config(state=tk.DISABLED)
        self._passo_continuo()

    def _passo_continuo(self) -> None:
        """Executa um passo continuo e agenda o proximo pelo relogio do tkinter."""
        if not self.executando or self.passo_atual >= len(self.eventos):
            self._pausar()
            return

        self._proximo_passo()
        intervalo = config.VELOCIDADES[self.var_velocidade.get()][1]
        self._timer_id = self.raiz.after(intervalo, self._passo_continuo)

    def _pausar(self) -> None:
        """Pausa a simulacao."""
        self.executando = False
        if self._timer_id:
            self.raiz.after_cancel(self._timer_id)
            self._timer_id = None
        self.btn_pausa.config(state=tk.DISABLED)
        self.btn_continuo.config(state=tk.NORMAL)

    def _reiniciar(self) -> None:
        """Reinicia o ponteiro de passos para 0."""
        self._pausar()
        self.passo_atual = 0
        self.barra_progresso["value"] = 0
        self.lbl_progresso.config(text=f"Passo: 0 / {len(self.eventos)}")
        self._limpar_registro()
        self._desenhar_mapa()
        self._limpar_pdu()
        self._limpar_enderecos()
        self._desenhar_pilhas_vazias()
        if hasattr(self, "lbl_explicacao"):
            self.lbl_explicacao.config(
                text="Simulação reposicionada no Passo 0. Clique em '⏭ Avançar' para dar o primeiro passo."
            )

    def _trocar_pilha(self) -> None:
        """Troca a visualizacao entre pilhas OSI e TCP/IP (V7)."""
        self.modo_pilha = self.var_pilha.get()
        self._redesenhar_pilhas_atual()

    def _redesenhar_pilhas_atual(self) -> None:
        """Redesenha as pilhas com base no estado atual."""
        if self.eventos and self.passo_atual > 0:
            evento = self.eventos[self.passo_atual - 1]
            self._atualizar_pilhas(evento)
        else:
            self._desenhar_pilhas_vazias()

    # ===================================================================
    # Mapa da Topologia de Rede (V1)
    # ===================================================================

    def _desenhar_mapa(self) -> None:
        """Renderiza os dispositivos, enlaces, custos e interfaces na tela."""
        self.canvas_mapa.delete("all")
        if self.topologia is None:
            return

        w = self.canvas_mapa.winfo_width()
        h = self.canvas_mapa.winfo_height()
        if w < 20 or h < 20:
            return

        margem_x = 55
        margem_y = 55
        self._posicoes_mapa.clear()

        for nome, disp in self.topologia.dispositivos.items():
            x = int(margem_x + disp.posicao[0] * (w - 2 * margem_x))
            y = int(margem_y + disp.posicao[1] * (h - 2 * margem_y))
            self._posicoes_mapa[nome] = (x, y)

        # Enlaces do caminho ativo
        caminho_pares = set()
        if self.resultado and self.resultado.caminho:
            for i in range(len(self.resultado.caminho) - 1):
                p = tuple(sorted([self.resultado.caminho[i], self.resultado.caminho[i + 1]]))
                caminho_pares.add(p)

        # Desenho dos enlaces
        for seg in self.topologia.segmentos:
            if len(seg.membros) < 2:
                continue

            membros_nomes = [m[0] for m in seg.membros]
            for i in range(len(membros_nomes)):
                for j in range(i + 1, len(membros_nomes)):
                    d1, d2 = membros_nomes[i], membros_nomes[j]
                    if d1 not in self._posicoes_mapa or d2 not in self._posicoes_mapa:
                        continue

                    x1, y1 = self._posicoes_mapa[d1]
                    x2, y2 = self._posicoes_mapa[d2]
                    par = tuple(sorted([d1, d2]))

                    esta_no_caminho = par in caminho_pares
                    cor_linha = COR_ENLACE_ATIVO if esta_no_caminho else COR_ENLACE
                    espessura = 3 if esta_no_caminho else 1
                    traco = () if seg.ativo else (5, 3)

                    self.canvas_mapa.create_line(x1, y1, x2, y2, fill=cor_linha,
                                                 width=espessura, dash=traco)

                    # Indicador de custo para ponto-a-ponto
                    if seg.custo > 0 and seg.tipo == "ponto_a_ponto":
                        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
                        self.canvas_mapa.create_oval(mx - 10, my - 10, mx + 10, my + 10,
                                                     fill="#263238", outline="#FFB300")
                        self.canvas_mapa.create_text(mx, my, text=str(seg.custo),
                                                     fill="#FFD54F", font=("Consolas", 9, "bold"))

                    # Rotulos das interfaces nas pontas (V1)
                    iface1 = next((m[1] for m in seg.membros if m[0] == d1), "")
                    iface2 = next((m[1] for m in seg.membros if m[0] == d2), "")

                    if iface1:
                        px1 = int(x1 + 0.22 * (x2 - x1))
                        py1 = int(y1 + 0.22 * (y2 - y1))
                        self.canvas_mapa.create_text(px1, py1, text=iface1,
                                                     fill="#90A4AE", font=("Consolas", 7))
                    if iface2:
                        px2 = int(x1 + 0.78 * (x2 - x1))
                        py2 = int(y1 + 0.78 * (y2 - y1))
                        self.canvas_mapa.create_text(px2, py2, text=iface2,
                                                     fill="#90A4AE", font=("Consolas", 7))

        # Rotulos de Redes Locais (LANs)
        for seg in self.topologia.segmentos:
            if seg.tipo == "lan":
                xs = [self._posicoes_mapa[m[0]][0] for m in seg.membros if m[0] in self._posicoes_mapa]
                ys = [self._posicoes_mapa[m[0]][1] for m in seg.membros if m[0] in self._posicoes_mapa]
                if xs and ys:
                    cx = sum(xs) // len(xs)
                    cy = min(ys) - 34
                    self.canvas_mapa.create_text(
                        cx, cy, text=f"{seg.rotulo} ({seg.prefixo})",
                        fill="#80CBC4", font=("Arial", 9, "bold"),
                    )

        # Desenho dos Dispositivos (Computadores e Roteadores)
        for nome, (x, y) in self._posicoes_mapa.items():
            disp = self.topologia.dispositivos[nome]
            e_roteador = (disp.tipo == "roteador")
            raio = 22 if e_roteador else 20
            cor_corpo = COR_ROTEADOR if e_roteador else COR_DISPOSITIVO

            # Halo de selecao no caminho
            if self.resultado and nome in (self.resultado.caminho or []):
                self.canvas_mapa.create_oval(
                    x - raio - 4, y - raio - 4, x + raio + 4, y + raio + 4,
                    fill="", outline=COR_ENLACE_ATIVO, width=2,
                )

            # Forma do dispositivo
            self.canvas_mapa.create_oval(
                x - raio, y - raio, x + raio, y + raio,
                fill=cor_corpo, outline="#ECEFF1", width=2,
            )
            self.canvas_mapa.create_text(
                x, y, text=nome, fill="white", font=("Arial", 10, "bold"),
            )

            # Endereco IP principal logo abaixo
            if disp.interfaces:
                ip_principal = disp.interfaces[0].logico
                self.canvas_mapa.create_text(
                    x, y + raio + 12, text=ip_principal,
                    fill="#CFD8DC", font=("Consolas", 8),
                )

    def _atualizar_mapa(self, evento: Evento) -> None:
        """Destaca o dispositivo ativo no mapa e desenha o pacote no enlace vigente."""
        self._desenhar_mapa()

        nome = evento.dispositivo
        if nome in self._posicoes_mapa:
            x, y = self._posicoes_mapa[nome]
            self.canvas_mapa.create_oval(
                x - 28, y - 28, x + 28, y + 28,
                fill="", outline=COR_ATIVO, width=3,
            )
            # Etiqueta de acao atual sobre o no
            self.canvas_mapa.create_text(
                x, y - 32, text=f"{evento.camada}:{evento.acao}",
                fill=COR_ATIVO, font=("Arial", 8, "bold"),
            )

        # Destaca o enlace e desenha o pacote/quadro em transito fisico
        if evento.camada in ("L1", "L2"):
            desc = evento.descricao
            no1, no2 = None, None
            for d in self._posicoes_mapa:
                if f"-{d}" in desc or f"–{d}" in desc or f"{d}-" in desc or f"{d}–" in desc:
                    if no1 is None:
                        no1 = d
                    elif no2 is None and d != no1:
                        no2 = d

            if (not no1 or not no2) and self.resultado and self.resultado.caminho:
                caminho = self.resultado.caminho
                if nome in caminho:
                    idx = caminho.index(nome)
                    if evento.acao in ("TRANSMITE", "ENQUADRA") and idx + 1 < len(caminho):
                        no1, no2 = nome, caminho[idx + 1]
                    elif evento.acao in ("RECEBE", "DESENQUADRA", "ERRO") and idx - 1 >= 0:
                        no1, no2 = caminho[idx - 1], nome

            if no1 and no2 and no1 in self._posicoes_mapa and no2 in self._posicoes_mapa:
                x1, y1 = self._posicoes_mapa[no1]
                x2, y2 = self._posicoes_mapa[no2]
                self.canvas_mapa.create_line(x1, y1, x2, y2, fill=COR_ATIVO, width=4)

                mx, my = (x1 + x2) // 2, (y1 + y2) // 2
                rotulo_pct = "Quadro"
                if evento.unidade and evento.unidade.quadro:
                    rotulo_pct = f"{evento.unidade.quadro} ({evento.tamanho}B)"
                elif "bits" in desc:
                    rotulo_pct = f"{evento.tamanho * 8}b"

                self.canvas_mapa.create_rectangle(
                    mx - 36, my - 11, mx + 36, my + 11,
                    fill="#FFD54F", outline="#ECEFF1", width=2,
                )
                self.canvas_mapa.create_text(
                    mx, my, text=rotulo_pct,
                    fill=COR_ROTULO_OCTETO, font=("Consolas", 8, "bold"),
                )

    # ===================================================================
    # Desenho da PDU (V3)
    # ===================================================================

    def _limpar_pdu(self) -> None:
        self.canvas_pdu.delete("all")
        self.lbl_nome_unidade.config(text="Unidade: —")

    def _atualizar_pdu(self, evento: Evento) -> None:
        """Desenha a unidade de dados como sequencia de blocos de cabecalhos (V3)."""
        self.canvas_pdu.delete("all")
        if evento.unidade is None:
            self.lbl_nome_unidade.config(text="Unidade: —")
            return

        unidade = evento.unidade
        blocos = unidade.blocos()
        self.lbl_nome_unidade.config(
            text=f"PDU: {unidade.unidade} | Tamanho: {unidade.tamanho()} octetos ({unidade.tamanho_bits()} bits)"
        )

        if not blocos:
            return

        w = self.canvas_pdu.winfo_width()
        h = 56
        x = 8
        y = 6
        altura_bloco = 42

        total_tam = sum(b["tamanho"] for b in blocos)
        if total_tam == 0:
            return

        largura_disponivel = max(100, w - 16)
        escala = largura_disponivel / total_tam

        for b in blocos:
            largura = max(36, int(b["tamanho"] * escala))
            cor = CORES_CAMADAS.get(b["camada"], "#78909C")
            if b["tipo"] == "dados":
                cor = "#2E7D32"
            elif b["tipo"] == "finalizador":
                cor = "#C62828"

            self.canvas_pdu.create_rectangle(
                x, y, x + largura, y + altura_bloco,
                fill=cor, outline="white", width=1,
            )
            self.canvas_pdu.create_text(
                x + largura // 2, y + altura_bloco // 2,
                text=f"{b['rotulo']}\n{b['tamanho']}B",
                fill="white", font=("Consolas", 8, "bold"),
            )
            x += largura

    # ===================================================================
    # Enderecos Vigentes (V4)
    # ===================================================================

    def _limpar_enderecos(self) -> None:
        self.lbl_ip_origem.config(text="Origem:  —")
        self.lbl_ip_destino.config(text="Destino: —")
        self.lbl_mac_origem.config(text="Origem:  —")
        self.lbl_mac_destino.config(text="Destino: —")

    def _atualizar_enderecos(self, evento: Evento) -> None:
        """Atualiza simultaneamente enderecos logicos e fisicos vigentes (V4)."""
        if evento.unidade is None:
            return

        u = evento.unidade
        if u.logicos:
            self.lbl_ip_origem.config(text=f"Origem:  {u.logicos[0]}")
            self.lbl_ip_destino.config(text=f"Destino: {u.logicos[1]}")

        if u.fisicos:
            self.lbl_mac_origem.config(text=f"Origem:  {u.fisicos[0]}")
            self.lbl_mac_destino.config(text=f"Destino: {u.fisicos[1]}")
        else:
            self.lbl_mac_origem.config(text="Origem:  (sem quadro)")
            self.lbl_mac_destino.config(text="Destino: (sem quadro)")

    # ===================================================================
    # Pilhas de Camadas (V2 e V7)
    # ===================================================================

    def _desenhar_pilhas_vazias(self) -> None:
        """Desenha as pilhas de camadas sem destaque ativo."""
        self.canvas_pilhas.delete("all")
        if self.topologia is None:
            return

        if self.resultado and self.resultado.caminho:
            dispositivos = self.resultado.caminho
        else:
            dispositivos = ["H1", "R1", "R4", "R3", "H4"]

        self._desenhar_pilhas_dispositivos(dispositivos, "", "")

    def _atualizar_pilhas(self, evento: Evento) -> None:
        """Desenha as pilhas destacando a camada ativa no dispositivo correspondente (V2)."""
        self.canvas_pilhas.delete("all")
        if self.resultado and self.resultado.caminho:
            dispositivos = self.resultado.caminho
        else:
            dispositivos = [evento.dispositivo]

        self._desenhar_pilhas_dispositivos(dispositivos, evento.dispositivo, evento.camada)

    def _desenhar_pilhas_dispositivos(self, dispositivos: list[str],
                                       disp_ativo: str, camada_ativa: str) -> None:
        """Desenha pilhas lado a lado para cada dispositivo do percurso."""
        canvas = self.canvas_pilhas
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 10 or h < 10 or not dispositivos:
            return

        n = len(dispositivos)
        largura_pilha = min(78, max(42, (w - 20) // n))
        espaco = max(6, (w - n * largura_pilha) // (n + 1))

        nomes = NOMES_CAMADAS_OSI if self.modo_pilha == "OSI" else NOMES_CAMADAS_TCPIP

        for idx, nome in enumerate(dispositivos):
            x = espaco + idx * (largura_pilha + espaco)
            y_base = 32

            # Rotulo do dispositivo no topo
            cor_disp = "#80D8FF" if nome == disp_ativo else "white"
            canvas.create_text(
                x + largura_pilha // 2, 16, text=nome,
                fill=cor_disp, font=("Arial", 10, "bold"),
            )

            disp = self.topologia.dispositivos.get(nome) if self.topologia else None
            e_roteador = (disp is not None and disp.tipo == "roteador")

            if self.modo_pilha == "TCP/IP":
                camadas_tcp = [
                    (7, "Aplicacao", [7, 6, 5]),
                    (4, "Transporte", [4]),
                    (3, "Internet", [3]),
                    (1, "Acesso Rede", [2, 1]),
                ]
                altura_cam = min(36, (h - 60) // 4)

                for ci, (num_cam, rotulo, sub_camadas) in enumerate(camadas_tcp):
                    if e_roteador and num_cam > 3:
                        continue

                    y = y_base + ci * (altura_cam + 4)
                    cor = CORES_CAMADAS.get(num_cam, "#90A4AE")

                    ativo = False
                    if nome == disp_ativo:
                        try:
                            num_at = int(camada_ativa.replace("L", ""))
                            if num_at in sub_camadas:
                                ativo = True
                        except ValueError:
                            pass

                    # Destaque especial para decisao de rota no roteador (V2)
                    destaque_rota = (e_roteador and num_cam == 3 and ativo)

                    if destaque_rota:
                        canvas.create_rectangle(
                            x - 3, y - 3, x + largura_pilha + 3, y + altura_cam + 3,
                            fill=COR_ROTA_DESTAQUE, outline=COR_ATIVO, width=2,
                        )
                    elif ativo:
                        canvas.create_rectangle(
                            x - 2, y - 2, x + largura_pilha + 2, y + altura_cam + 2,
                            fill=COR_ATIVO, outline=COR_ATIVO, width=2,
                        )

                    canvas.create_rectangle(
                        x, y, x + largura_pilha, y + altura_cam,
                        fill=cor, outline="white",
                    )
                    txt = "ROTEIA" if destaque_rota else rotulo[:10]
                    canvas.create_text(
                        x + largura_pilha // 2, y + altura_cam // 2,
                        text=txt, fill="white", font=("Consolas", 7, "bold"),
                    )
            else:
                # Modelo OSI de 7 Camadas
                camadas = list(range(7, 0, -1))
                if e_roteador:
                    camadas = list(range(3, 0, -1))

                altura_cam = min(28, (h - 60) // len(camadas))

                for ci, num in enumerate(camadas):
                    y = y_base + ci * (altura_cam + 3)
                    cor = CORES_CAMADAS.get(num, "#90A4AE")
                    ativo = (nome == disp_ativo and camada_ativa == f"L{num}")

                    # Destaque especial evidente para a Camada 3 do roteador (V2)
                    destaque_rota = (e_roteador and num == 3 and ativo)

                    if destaque_rota:
                        canvas.create_rectangle(
                            x - 3, y - 3, x + largura_pilha + 3, y + altura_cam + 3,
                            fill=COR_ROTA_DESTAQUE, outline=COR_ATIVO, width=3,
                        )
                    elif ativo:
                        canvas.create_rectangle(
                            x - 2, y - 2, x + largura_pilha + 2, y + altura_cam + 2,
                            fill=COR_ATIVO, outline=COR_ATIVO, width=2,
                        )

                    canvas.create_rectangle(
                        x, y, x + largura_pilha, y + altura_cam,
                        fill=cor, outline="white",
                    )
                    rotulo = "L3 ROTA!" if destaque_rota else f"L{num} {nomes[num][:4]}"
                    canvas.create_text(
                        x + largura_pilha // 2, y + altura_cam // 2,
                        text=rotulo, fill="white", font=("Consolas", 7, "bold"),
                    )

    # ===================================================================
    # Registro de Eventos (V6)
    # ===================================================================

    def _adicionar_ao_registro(self, evento: Evento) -> None:
        """Insere uma linha no registro e rola automaticamente."""
        linha = formatar_evento(evento)
        self.texto_registro.config(state=tk.NORMAL)
        self.texto_registro.insert(tk.END, linha + "\n")
        self.texto_registro.see(tk.END)
        self.texto_registro.config(state=tk.DISABLED)

    def _limpar_registro(self) -> None:
        self.texto_registro.config(state=tk.NORMAL)
        self.texto_registro.delete("1.0", tk.END)
        self.texto_registro.config(state=tk.DISABLED)

    def _salvar_registro(self) -> None:
        """Grava o registro de eventos em arquivo texto (V6)."""
        caminho = filedialog.asksaveasfilename(
            title="Salvar Registro de Eventos",
            defaultextension=".txt",
            filetypes=[("Arquivo de Texto", "*.txt"), ("Todos os Arquivos", "*.*")],
            initialfile=config.ARQUIVO_REGISTRO_PADRAO,
        )
        if caminho:
            try:
                if self.resultado:
                    self.resultado.registro.salvar(caminho)
                    messagebox.showinfo("Sucesso", f"Registro gravado com sucesso em:\n{caminho}")
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Erro ao Salvar", f"Nao foi possivel gravar o arquivo:\n{e}")

    # ===================================================================
    # Eficiencia e Metricas
    # ===================================================================

    def _atualizar_eficiencia(self) -> None:
        """Atualiza os indicadores de eficiencia e sobrecarga."""
        if self.resultado is None:
            return

        r = self.resultado
        self.lbl_dados.config(text=f"Dados uteis da mensagem: {r.octetos_dados} octetos")
        self.lbl_transmitidos.config(text=f"Total transmitido nos enlaces: {r.octetos_transmitidos} octetos")
        self.lbl_eficiencia.config(text=f"Eficiencia (η = dados / transmitidos): {r.eficiencia:.1%}")
        self.lbl_sobrecarga.config(text=f"Sobrecarga de empilhamento (1 - η): {r.sobrecarga:.1%}")

    # ===================================================================
    # Funcionalidades Extras: Tabelas de Roteamento e Troca de Topologia
    # ===================================================================

    def _abrir_tabelas_roteamento(self) -> None:
        """Exibe a janela com as Tabelas de Encaminhamento calculadas por Dijkstra (R5 / Tabela 3)."""
        if self.topologia is None:
            return

        janela_tab = tk.Toplevel(self.raiz)
        janela_tab.title("Tabelas de Encaminhamento (Dijkstra) — Tabela 3")
        janela_tab.geometry("780x560")
        janela_tab.configure(bg=COR_FUNDO)

        frame_t = ttk.Frame(janela_tab, padding=10)
        frame_t.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame_t, text="Tabelas de Encaminhamento de Referencia (Menor Caminho)",
                  font=("Arial", 11, "bold"), foreground="#90CAF9").pack(anchor=tk.W, pady=(0, 6))

        txt_tabelas = scrolledtext.ScrolledText(
            frame_t, font=("Consolas", 9), bg=COR_FUNDO_CONSOLE, fg=COR_TEXTO, wrap=tk.NONE
        )
        txt_tabelas.pack(fill=tk.BOTH, expand=True, pady=4)

        conteudo = []
        for r_nome in self.topologia.roteadores():
            conteudo.append(f"==================================================")
            conteudo.append(f"  Roteador {r_nome} — Tabela de Encaminhamento")
            conteudo.append(f"==================================================")
            conteudo.append(f" {'Prefixo Destino':<16} | {'Proximo Salto':<15} | {'Iface':<6} | {'Custo':<5} | {'Via':<6}")
            conteudo.append(f"-----------------+-----------------+--------+-------+-------")
            tabela = self.topologia.tabela_encaminhamento(r_nome)
            for entrada in tabela:
                conteudo.append(
                    f" {entrada.destino_prefixo:<16} | {entrada.proximo_salto:<15} | {entrada.interface_saida:<6} | {entrada.custo:<5} | {entrada.via:<6}"
                )
            conteudo.append("")

        txt_tabelas.insert(tk.END, "\n".join(conteudo))
        txt_tabelas.config(state=tk.DISABLED)

    def _trocar_arquivo_topologia(self) -> None:
        """Permite carregar outro arquivo JSON sem fechar a interface."""
        caminho = filedialog.askopenfilename(
            parent=self.raiz,
            title="Selecionar Arquivo de Topologia",
            filetypes=[("Arquivos JSON", "*.json"), ("Todos os Arquivos", "*.*")],
        )
        if not caminho:
            return

        self._pausar()
        try:
            nova_topologia = Topologia(caminho)
        except ErroTopologia as e:
            self._marcar_topologia_indisponivel(str(e))
            return
        except (OSError, ValueError, TypeError) as e:
            traceback.print_exc()
            self._marcar_topologia_indisponivel(
                f"Falha inesperada ao ler a topologia: {type(e).__name__}: {e}"
            )
            return

        self.topologia = nova_topologia
        self.resultado = None
        self.eventos = []
        self.passo_atual = 0
        self._limpar_registro()
        self._limpar_pdu()
        self._limpar_enderecos()
        self.barra_progresso["maximum"] = 0
        self.barra_progresso["value"] = 0
        self.lbl_progresso.config(text="Passo: 0 / 0")
        self._marcar_topologia_disponivel()

        messagebox.showinfo(
            "Topologia carregada",
            f"Topologia carregada com sucesso a partir de:\n{caminho}",
            parent=self.raiz,
        )

    # ===================================================================
    # Execucao do Loop Principal
    # ===================================================================

    def executar(self) -> None:
        """Inicia o laco de eventos da interface grafica."""
        self.raiz.mainloop()
