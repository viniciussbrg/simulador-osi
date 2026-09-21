"""Interface grafica do simulador, em tkinter.

A janela apenas le o nucleo: cria a Simulacao, pede um evento por vez com
passo() e desenha o evento e a unidade (sim.unidade) que ele descreve.
Nenhuma camada e chamada daqui. O que a tela precisa lembrar entre um passo
e outro (enlaces percorridos, descartes, saltos) fica em Andamento, que so
consome eventos e unidades.

Disposicao da janela:

    barra de controle: passo, execucao, pausa, velocidade (V5), pilha (V7),
                       tamanho do texto
    +-----------+-----------------------+-----------------------+
    | cenario   | mapa da rede (V1)     | pilhas (V2)           |
    | falhas    +-----------------------+-----------------------+
    | resumo    | unidade de dados (V3) | enderecos (V4)        |
    |           +-----------------------------------------------+
    |           | registro de eventos (V6)                      |
    +-----------+-----------------------------------------------+

As pilhas de todos os dispositivos do caminho sao desenhadas antes do
primeiro passo, em cinza enquanto a unidade nao os alcanca: nada muda de
lugar durante a execucao.

O tamanho do texto (Normal, Grande, Projetor) multiplica todas as fontes da
janela. Nos canvas, toda medida que acompanha o texto (altura de linha,
largura da legenda, margem do mapa) sai das metricas da fonte, e nao de um
numero fixo de pixels: e isso que impede um rotulo de sair do canvas.
"""

import itertools
import math
import sys
import tkinter as tk
import tkinter.font as tkfont
import traceback
from dataclasses import dataclass, replace
from tkinter import filedialog, messagebox, ttk

from .recursos import pasta_do_programa
from .registro import formatar
from .simulador import (
    CENARIOS, PASTA_DOS_REGISTROS, Cenario, Falhas, Simulacao,
    gerar_registros_dos_cenarios,
)

# ----------------------------------------------------------------------
# Constantes de apresentacao
# ----------------------------------------------------------------------

LARGURA_MINIMA, ALTURA_MINIMA = 1100, 700
LARGURA_PREFERIDA, ALTURA_PREFERIDA = 1600, 960

# Intervalo entre passos na execucao continua, em milissegundos.
VELOCIDADES = (("Lenta", 1500), ("Normal", 600), ("Rápida", 150))

# Tamanho do texto: (nome, fator das fontes, fator da largura da barra lateral,
# posicao das duas divisorias). No Projetor a barra lateral cresce menos que
# o texto e passa a rolar, e o registro ganha altura da unidade de dados.
ESCALAS = (
    ("Normal", 1.0, 1.0, (0.43, 0.78)),
    ("Grande", 1.25, 1.2, (0.44, 0.76)),
    ("Projetor", 1.6, 1.3, (0.52, 0.74)),
)

NOMES_OSI = {
    7: "Aplicação", 6: "Apresentação", 5: "Sessão", 4: "Transporte",
    3: "Rede", 2: "Enlace", 1: "Física",
}

# Linhas da pilha em cada modo: (nome, camadas OSI que a linha agrupa).
# A simulacao e sempre a mesma; so o desenho muda (V7).
GRUPOS_OSI = tuple((NOMES_OSI[n], (n,)) for n in range(7, 0, -1))
GRUPOS_TCPIP = (
    ("Aplicação", (7, 6, 5)),
    ("Transporte", (4,)),
    ("Internet", (3,)),
    ("Enlace", (2,)),
    ("Física", (1,)),
)

# A mesma cor pinta a caixa da camada na pilha e o bloco dela na unidade.
COR_DA_CAMADA = {
    7: "#f6c6c0", 6: "#fad7ad", 5: "#f5e9a0", 4: "#c6e5bf",
    3: "#b8d5f5", 2: "#d9ccf0", 1: "#d2dce1",
}
COR_ATIVA = {
    7: "#d9534f", 6: "#e0892a", 5: "#b89a00", 4: "#3f9b46",
    3: "#2f7fd6", 2: "#7e57c2", 1: "#5f7d8c",
}
COR_ROTA, BORDA_ROTA, FUNDO_ROTA = "#ff6d00", "#a63c00", "#fff1e0"
COR_DESCARTE, FUNDO_DESCARTE = "#d32f2f", "#fdecea"
CINZA_FUNDO, CINZA_BORDA, CINZA_TEXTO = "#f3f3f3", "#d9d9d9", "#b8b8b8"
COR_ENLACE, COR_PERCORRIDO, COR_TRANSITO = "#a3a3a3", "#1e88e5", "#ff6d00"
COR_LOGICO, FUNDO_LOGICO = "#0d47a1", "#e3eefb"
COR_FISICO, FUNDO_FISICO = "#5e2a9e", "#efe8fa"
COR_TEXTO, COR_TEXTO_FRACO = "#263238", "#78909c"

# Paleta da janela. Nada aqui vem do sistema: a aparencia e a mesma num
# Windows com tema claro, num Windows com tema escuro e num Linux qualquer.
# Todo widget recebe fundo e cor de texto explicitos; nenhum herda o padrao.
FUNDO_JANELA = "#f0f0f0"            # frames, barra de controle, barra lateral
FUNDO_PAINEL = "#ffffff"            # canvas dos paineis desenhados
FUNDO_CAMPO = "#ffffff"             # campos de texto e listas
FUNDO_CAMPO_FIXO = "#eceff1"        # campo so de leitura (lista com escolha fixa)
FUNDO_CAMPO_INATIVO = "#e4e6e7"     # campo desabilitado
FUNDO_REGISTRO = "#fcfcfc"          # area do registro de eventos
FUNDO_SALTOS = "#fafafa"            # lista de saltos
FUNDO_BARRA_RESUMO = "#eeeeee"      # trilho da barra de eficiencia
BORDA_CAMPO = "#9aa4ab"
COR_TEXTO_INATIVO = "#9e9e9e"
FUNDO_BOTAO, FUNDO_BOTAO_SOB, FUNDO_BOTAO_PRESSIONADO = "#e1e4e6", "#d6e6f7", "#c2d8ef"
SELECAO_FUNDO, SELECAO_TEXTO = "#3d6ea8", "#ffffff"
FUNDO_TRILHO, PUXADOR_ROLAGEM, PUXADOR_ROLAGEM_SOB = "#e8e8e8", "#bdc3c7", "#a4acb2"
FUNDO_MENU, FUNDO_MENU_ATIVO = "#f7f7f7", "#3d6ea8"
DESTAQUE_LINHA_ATUAL = "#fff3c4"    # linha do passo atual no registro


# ----------------------------------------------------------------------
# Configuracao escolhida na barra lateral
# ----------------------------------------------------------------------

class ConfiguracaoInvalida(Exception):
    """Um campo da barra lateral que impede a execucao; campo diz qual."""

    def __init__(self, mensagem, campo):
        super().__init__(mensagem)
        self.campo = campo


@dataclass
class Escolhas:
    """O que o usuario preencheu na barra lateral, ainda como texto."""

    base: str
    origem: str
    destino: str
    mensagem: str
    derrubar: bool = False
    enlace_derrubado: tuple = None
    inverter_bit: bool = False
    enlace_do_bit: tuple = None
    posicao_do_bit: str = "0"
    inalcancavel: bool = False
    endereco_inalcancavel: str = ""


def endereco_bem_formado(texto):
    partes = texto.split(".")
    return len(partes) == 4 and all(
        p.isdigit() and len(p) <= 3 and int(p) <= 255 for p in partes
    )


def _parece_endereco(texto):
    return any(ch.isdigit() for ch in texto) and "." in texto


def resolver_destino(topologia, texto, origem):
    """Devolve o computador de destino, dado pelo nome ou pelo endereco logico.

    Roteadores sao recusados pelo nome e pelo endereco: nao tem as camadas 4
    a 7, e o nucleo produziria um evento de entrega enganoso.
    """
    texto = texto.strip()
    computadores = ", ".join(topologia.computadores)
    if not texto:
        raise ConfiguracaoInvalida(
            f"Informe o destino: o nome de um computador ({computadores}) "
            f"ou o endereço lógico dele.", "destino")

    por_nome = {nome.upper(): nome for nome in topologia.computadores}
    roteadores = {nome.upper(): nome for nome in topologia.roteadores}
    if texto.upper() in por_nome:
        nome = por_nome[texto.upper()]
    elif texto.upper() in roteadores:
        raise ConfiguracaoInvalida(
            f"{roteadores[texto.upper()]} é um roteador: roteadores só têm as "
            f"camadas 1 a 3 e não recebem mensagens. Escolha um computador "
            f"({computadores}).", "destino")
    elif _parece_endereco(texto):
        if not endereco_bem_formado(texto):
            raise ConfiguracaoInvalida(
                f"\"{texto}\" não é um endereço lógico válido. Use quatro números "
                f"de 0 a 255 separados por ponto, como 10.0.3.10.", "destino")
        interface = topologia.interface_por_logico(texto)
        if interface is None:
            raise ConfiguracaoInvalida(
                f"{texto} não pertence a nenhum computador da topologia. Para "
                f"simular um destino fora da rede, marque a falha \"Destino "
                f"inalcançável\".", "destino")
        if interface.dispositivo in topologia.roteadores:
            raise ConfiguracaoInvalida(
                f"{texto} é a interface {interface.nome} de {interface.dispositivo}; "
                f"roteadores não têm as camadas 4 a 7 e não podem ser destino "
                f"de uma mensagem.", "destino")
        nome = interface.dispositivo
    else:
        raise ConfiguracaoInvalida(
            f"\"{texto}\" não é um computador da topologia nem um endereço lógico. "
            f"Computadores: {computadores}.", "destino")

    if nome == origem:
        raise ConfiguracaoInvalida(
            f"O destino {nome} é a própria origem. Escolha outro computador.",
            "destino")
    return nome


def validar_inalcancavel(topologia, texto):
    texto = texto.strip()
    if not endereco_bem_formado(texto):
        raise ConfiguracaoInvalida(
            f"\"{texto}\" não é um endereço lógico válido para a falha de destino "
            f"inalcançável. Use, por exemplo, 10.0.9.10.", "inalcancavel")
    interface = topologia.interface_por_logico(texto)
    if interface is not None:
        raise ConfiguracaoInvalida(
            f"{texto} é a interface {interface.nome} de {interface.dispositivo}, que "
            f"existe na topologia. O destino inalcançável precisa ser um endereço "
            f"sem dono, como 10.0.9.10.", "inalcancavel")
    return texto


def _comparavel(falhas):
    """Falhas em forma comparavel: o par de um enlace nao tem ordem."""
    return (
        frozenset(falhas.enlace_derrubado or ()),
        frozenset(falhas.bit_invertido or ()),
        falhas.posicao_do_bit if falhas.bit_invertido else 0,
        falhas.destino_inalcancavel,
    )


def montar_cenario(topologia, escolhas):
    """Transforma as escolhas em Cenario; devolve (cenario, modificado).

    O primeiro fluxo do cenario de partida recebe origem, destino e mensagem;
    os demais fluxos (o de H2 em E3) seguem como estao.
    """
    base = CENARIOS[escolhas.base]
    if escolhas.origem not in topologia.computadores:
        raise ConfiguracaoInvalida(
            f"A origem {escolhas.origem or '(vazia)'} não é um computador da "
            f"topologia.", "origem")
    destino = resolver_destino(topologia, escolhas.destino, escolhas.origem)
    if escolhas.mensagem == "":
        raise ConfiguracaoInvalida("A mensagem está vazia. Escreva ao menos um caractere.",
                                   "mensagem")

    posicao = 0
    if escolhas.inverter_bit:
        texto = escolhas.posicao_do_bit.strip()
        if not texto.isdigit():
            raise ConfiguracaoInvalida(
                f"A posição do bit invertido deve ser um número inteiro a partir "
                f"de 0, e não \"{texto}\".", "bit")
        posicao = int(texto)

    falhas = Falhas(
        enlace_derrubado=escolhas.enlace_derrubado if escolhas.derrubar else None,
        bit_invertido=escolhas.enlace_do_bit if escolhas.inverter_bit else None,
        posicao_do_bit=posicao,
        destino_inalcancavel=(validar_inalcancavel(topologia, escolhas.endereco_inalcancavel)
                              if escolhas.inalcancavel else None),
    )
    primeiro = replace(base.fluxos[0], origem=escolhas.origem, destino=destino,
                       mensagem=escolhas.mensagem)
    fluxos = (primeiro,) + base.fluxos[1:]
    modificado = fluxos != base.fluxos or _comparavel(falhas) != _comparavel(base.falhas)
    nome = f"{base.nome} (modificado)" if modificado else base.nome
    return Cenario(base.codigo, nome, fluxos, falhas), modificado


def _unir_em_ordem(sequencias):
    """Une sequencias de dispositivos preservando a ordem de cada uma.

    Em E3, H1-R1-R4-R3-H4 e H2-R1-R4-R3-H4 viram H1, H2, R1, R4, R3, H4: um
    dispositivo novo entra antes do primeiro seguinte ja conhecido.
    """
    ordem = []
    for sequencia in sequencias:
        for i, nome in enumerate(sequencia):
            if nome in ordem:
                continue
            seguinte = next((s for s in sequencia[i + 1:] if s in ordem), None)
            if seguinte is not None:
                ordem.insert(ordem.index(seguinte), nome)
                continue
            anterior = next((s for s in reversed(sequencia[:i]) if s in ordem), None)
            ordem.insert(ordem.index(anterior) + 1 if anterior else len(ordem), nome)
    return ordem


def dispositivos_do_caminho(topologia, cenario):
    """Dispositivos cujas pilhas aparecem, na ordem da tela, e o total de passos.

    Junta o caminho de menor custo de cada fluxo, que inclui quem a unidade
    nao chega a alcancar (H4 em E6), com os dispositivos que aparecem nos
    eventos de um ensaio da mesma execucao (R1 em E5, que nao tem caminho
    completo). O ensaio e uma Simulacao propria, descartada em seguida.
    """
    ensaio = Simulacao(topologia, cenario)
    eventos = ensaio.executar()
    sequencias = []
    for fluxo in cenario.fluxos:
        destino = (cenario.falhas.destino_inalcancavel
                   or topologia.interface_de(fluxo.destino).logico)
        caminho = ensaio.topologia.caminho_de_dispositivos(fluxo.origem, destino)
        if caminho:
            sequencias.append(caminho)
    sequencias.append(list(dict.fromkeys(e.dispositivo for e in eventos)))
    return _unir_em_ordem(sequencias), len(eventos)


def _dono(identificador):
    return identificador.split(":")[0]


def _enlace_entre(topologia, par):
    if not par:
        return None
    for enlace in topologia.enlaces:
        if {_dono(enlace.a), _dono(enlace.b)} == set(par):
            return enlace
    return None


def rotulos_de_enlace(topologia):
    """Rotulo de cada enlace para as listas de falhas, com o par de dispositivos."""
    return {
        f"{_dono(e.a)}–{_dono(e.b)}": (_dono(e.a), _dono(e.b))
        for e in topologia.enlaces
    }


def porcentagem(fracao):
    return f"{fracao * 100:.1f}%".replace(".", ",")


# ----------------------------------------------------------------------
# O que ja aconteceu na execucao
# ----------------------------------------------------------------------

class Andamento:
    """Estado da tela derivado dos eventos ja ocorridos e das suas unidades.

    O enlace de um quadro vem do par de enderecos fisicos da unidade, cruzado
    com as interfaces da topologia, e nunca do texto da descricao.
    """

    def __init__(self, topologia):
        self.topologia = topologia
        self.evento = None
        self.unidade = None
        self.alcancados = set()
        self.percorridos = set()
        self.em_transito = None
        self.enlace_perdido = None
        self.descartes = {}          # dispositivo -> camada do descarte
        self.saltos = []             # (quadro, interface de saida, de chegada, fisicos)
        self._por_fisico = {i.fisico: i for i in topologia.interfaces.values()}

    def interfaces_de(self, fisicos):
        return tuple(self._por_fisico.get(f) for f in fisicos)

    def enlace_de(self, fisicos):
        a, b = self.interfaces_de(fisicos)
        if a is None or b is None:
            return None
        extremos = {a.identificador, b.identificador}
        for enlace in self.topologia.enlaces:
            if {enlace.a, enlace.b} == extremos:
                return self.topologia.chave_do_enlace(enlace)
        return None

    def registrar(self, evento, unidade):
        self.evento, self.unidade = evento, unidade
        self.alcancados.add(evento.dispositivo)
        self.em_transito = None
        if evento.acao == "ENQUADRA":
            de, para = self.interfaces_de(unidade.fisicos)
            self.saltos.append((unidade.numero_quadro, de, para, unidade.fisicos))
        if evento.camada == 1:
            enlace = self.enlace_de(unidade.fisicos)
            if evento.acao == "DESCARTA":
                self.enlace_perdido = enlace
            elif enlace is not None:
                self.em_transito = enlace
                self.percorridos.add(enlace)
        elif evento.acao == "DESCARTA":
            self.descartes[evento.dispositivo] = evento.camada


# ----------------------------------------------------------------------
# Apoio ao desenho
# ----------------------------------------------------------------------

class Tipografia:
    """As fontes da janela, todas presas ao mesmo fator de escala.

    Os paineis desenhados pedem aqui as fontes (tipografia["pequena"]), a
    altura de linha de cada uma e as medidas em pixels que crescem junto com
    o texto (px). Mudar o fator reconfigura as fontes no lugar: os widgets
    que as usam, inclusive os ttk, que usam as fontes nomeadas do Tk,
    acompanham sem ser recriados.
    """

    # Fontes nomeadas do Tk: botoes, rotulos, listas e campos ttk.
    NOMEADAS = ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkCaptionFont",
                "TkSmallCaptionFont", "TkTooltipFont", "TkMenuFont")

    def __init__(self):
        familia = tkfont.nametofont("TkDefaultFont").actual("family")
        fixa = tkfont.nametofont("TkFixedFont").actual("family")
        # Tamanhos negativos sao pixels: o desenho fica igual em qualquer sistema.
        self.fontes = {
            "normal": tkfont.Font(family=familia, size=-12),
            "pequena": tkfont.Font(family=familia, size=-11),
            "negrito": tkfont.Font(family=familia, size=-12, weight="bold"),
            "titulo": tkfont.Font(family=familia, size=-13, weight="bold"),
            "mono": tkfont.Font(family=fixa, size=-12),
            "mono_grande": tkfont.Font(family=fixa, size=-14, weight="bold"),
        }
        nomeadas = [tkfont.nametofont(nome) for nome in self.NOMEADAS]
        self._base = [(f, f.cget("size")) for f in list(self.fontes.values()) + nomeadas]
        self.fator = 1.0

    def __getitem__(self, nome):
        return self.fontes[nome]

    def aplicar(self, fator):
        self.fator = fator
        for fonte, tamanho in self._base:
            if tamanho:     # zero e o tamanho padrao do sistema: fica como esta
                fonte.configure(size=round(tamanho * fator))

    def px(self, medida):
        """Uma medida de desenho, em pixels, no tamanho de texto atual."""
        return round(medida * self.fator)

    def linha(self, nome):
        """Altura de uma linha de texto na fonte dada."""
        return self.fontes[nome].metrics("linespace")


def caber(texto, fonte, largura):
    """Corta o texto com reticencias para caber na largura, em pixels."""
    if largura <= 0:
        return ""
    if fonte.measure(texto) <= largura:
        return texto
    baixo, alto = 0, len(texto)
    while baixo < alto:
        meio = (baixo + alto + 1) // 2
        if fonte.measure(texto[:meio] + "…") <= largura:
            baixo = meio
        else:
            alto = meio - 1
    return texto[:baixo] + "…"


def quebrar(texto, fonte, largura, maximo=None):
    """Quebra o texto em linhas que cabem na largura, respeitando os \\n.

    Com maximo, o que nao cabe nas linhas disponiveis vai para a ultima,
    cortada com reticencias. Desenhar as linhas juntas, sem a opcao width do
    canvas, garante a altura: len(linhas) vezes a altura de linha da fonte.
    """
    linhas = []
    for paragrafo in texto.split("\n"):
        atual = ""
        for palavra in paragrafo.split():
            tentativa = f"{atual} {palavra}" if atual else palavra
            if atual and fonte.measure(tentativa) > largura:
                linhas.append(atual)
                atual = palavra
            else:
                atual = tentativa
        linhas.append(atual)
    if maximo is not None and len(linhas) > maximo:
        if maximo <= 0:
            return []
        resto = " ".join(linha for linha in linhas[maximo - 1:] if linha)
        ultima = caber(resto, fonte, largura)
        if ultima == resto:
            ultima = caber(resto + " …", fonte, largura)
        linhas = linhas[:maximo - 1] + [ultima]
    return [caber(linha, fonte, largura) for linha in linhas]


def texto_com_fundo(canvas, x, y, texto, fonte, cor, fundo="white", anchor="center"):
    item = canvas.create_text(x, y, text=texto, font=fonte, fill=cor, anchor=anchor)
    x0, y0, x1, y1 = canvas.bbox(item)
    caixa = canvas.create_rectangle(x0 - 2, y0, x1 + 2, y1, fill=fundo, outline="")
    canvas.tag_lower(caixa, item)
    return item


def marcar_x(canvas, x, y, raio=7, cor=COR_DESCARTE):
    canvas.create_line(x - raio, y - raio, x + raio, y + raio, fill=cor, width=3)
    canvas.create_line(x - raio, y + raio, x + raio, y - raio, fill=cor, width=3)


def marcar_raio(canvas, x, y, escala=1.0):
    """Um relampago pequeno, desenhado com poligono para nao depender de fonte."""
    pontos = [(-2, -10), (6, -10), (1, -2), (6, -2), (-4, 10), (-1, 1), (-6, 1)]
    canvas.create_polygon(
        [c for px, py in pontos for c in (x + px * escala, y + py * escala)],
        fill="#fdd835", outline="#6d4c41", width=1,
    )


def _roteador_do_computador(topologia, computador):
    for enlace in topologia.enlaces:
        extremos = (_dono(enlace.a), _dono(enlace.b))
        if computador in extremos:
            outro = extremos[1] if extremos[0] == computador else extremos[0]
            if outro in topologia.roteadores:
                return outro
    return topologia.roteador_da_rede(topologia.interface_de(computador).rede)


def _ordem_dos_roteadores(topologia):
    """Ordem dos roteadores no circulo com menos cruzamentos entre enlaces."""
    roteadores = list(topologia.roteadores)
    ligacoes = [
        (_dono(e.a), _dono(e.b)) for e in topologia.enlaces
        if _dono(e.a) in roteadores and _dono(e.b) in roteadores
    ]
    if not 4 <= len(roteadores) <= 8:
        return roteadores

    def cruzamentos(ordem):
        posicao = {nome: i for i, nome in enumerate(ordem)}
        total = 0
        for (a, b), (c, d) in itertools.combinations(ligacoes, 2):
            if len({a, b, c, d}) < 4:
                continue
            i, j = sorted((posicao[a], posicao[b]))
            total += (i < posicao[c] < j) != (i < posicao[d] < j)
        return total

    candidatas = ([roteadores[0], *resto] for resto in itertools.permutations(roteadores[1:]))
    return min(candidatas, key=cruzamentos)


def posicoes_no_mapa(topologia, largura, altura, margens=(36, 36, 36, 36)):
    """Coordenadas de cada dispositivo, calculadas da topologia a cada desenho.

    Os roteadores ficam num circulo; os computadores, do lado de fora do
    roteador a que se ligam, na horizontal, que e onde o canvas tem sobra.
    O conjunto e esticado para ocupar o canvas, menos as margens (esquerda,
    topo, direita, base).
    """
    roteadores = _ordem_dos_roteadores(topologia)
    n = len(roteadores)
    pontos = {}
    for i, nome in enumerate(roteadores):
        angulo = math.radians(-135 + 360 * i / max(n, 1))
        pontos[nome] = (math.cos(angulo), math.sin(angulo)) if n > 1 else (0.0, 0.0)

    grupos = {}
    for computador in topologia.computadores:
        grupos.setdefault(_roteador_do_computador(topologia, computador), []).append(computador)
    for roteador, computadores in grupos.items():
        k = len(computadores)
        if roteador in pontos and n > 1:
            cx, cy = pontos[roteador]
            # Para fora do circulo: na horizontal, salvo roteador no eixo vertical.
            if abs(cx) >= 0.2:
                dx, dy = (1 if cx > 0 else -1), 0
            else:
                dx, dy = 0, (1 if cy > 0 else -1)
            for j, nome in enumerate(computadores):
                desvio = (j - (k - 1) / 2) * 0.6
                pontos[nome] = (cx + dx * 1.1 + abs(dy) * desvio, cy + dy * 1.1 + abs(dx) * desvio)
            continue
        cx, cy = pontos.get(roteador, (0.0, 1.2 if n else 0.0))
        for j, nome in enumerate(computadores):
            angulo = math.pi / 2 + (j - (k - 1) / 2) * 2 * math.pi / max(k, 1)
            pontos[nome] = (cx + 0.9 * math.cos(angulo), cy + 0.9 * math.sin(angulo))

    if not pontos:
        return {}
    xs = [p[0] for p in pontos.values()]
    ys = [p[1] for p in pontos.values()]

    def escala(valor, menor, maior, inicio, fim):
        if maior - menor < 1e-9:
            return (inicio + fim) / 2
        return inicio + (valor - menor) / (maior - menor) * (fim - inicio)

    esquerda, topo, direita, base = margens
    return {
        nome: (escala(x, min(xs), max(xs), esquerda, largura - direita),
               escala(y, min(ys), max(ys), topo, altura - base))
        for nome, (x, y) in pontos.items()
    }


# ----------------------------------------------------------------------
# V1: mapa da rede
# ----------------------------------------------------------------------

class Mapa:
    """Os dispositivos, os enlaces com interfaces e custos, e o caminho percorrido."""

    def __init__(self, canvas, fontes):
        self.canvas = canvas
        self.fontes = fontes
        self._ajuste = None         # (chave, topologia, margens) do ultimo ajuste

    # Tamanho dos dispositivos: cresce com o texto, para o nome caber dentro.
    @property
    def raio_do_roteador(self):
        return self.fontes.px(17)

    @property
    def meio_computador(self):
        return self.fontes.px(20), self.fontes.px(12)     # meia largura, meia altura

    def _altura_da_legenda(self):
        return self.fontes.linha("pequena") + self.fontes.px(10)

    def desenhar(self, topologia, falhas, andamento, erro=None):
        c = self.canvas
        c.delete("all")
        largura, altura = c.winfo_width(), c.winfo_height()
        if erro:
            fonte = self.fontes["negrito"]
            linhas = quebrar(f"Não foi possível abrir a topologia.\n\n{erro}\n\n"
                             f"Corrija o arquivo e use Arquivo → Recarregar topologia.",
                             fonte, largura - 32, (altura - 32) // self.fontes.linha("negrito"))
            c.create_text(16, 16, anchor="nw", text="\n".join(linhas), font=fonte, fill=COR_DESCARTE)
            return
        if topologia is None or largura < 80 or altura < 80:
            return

        altura_util = altura - self._altura_da_legenda()
        margens = self._margens_que_cabem(topologia, largura, altura_util)
        if margens is None:
            fonte = self.fontes["normal"]
            linhas = quebrar("O mapa não cabe neste espaço com este tamanho de texto. Aumente o "
                             "painel arrastando a divisória, ou escolha um texto menor.",
                             fonte, largura - 16, (altura - 8) // self.fontes.linha("normal"))
            c.create_text(largura / 2, altura / 2, text="\n".join(linhas), font=fonte,
                          fill=COR_TEXTO_FRACO, justify="center")
            return
        pos = posicoes_no_mapa(topologia, largura, altura_util, margens)
        derrubados = andamento.topologia.enlaces_derrubados if andamento else set()
        enlace_do_bit = _enlace_entre(topologia, falhas.bit_invertido if falhas else None)
        self._desenhar_rede(topologia, pos, altura_util, derrubados, enlace_do_bit, andamento)
        self._legenda(largura, altura)

    def _desenhar_rede(self, topologia, pos, altura_util, derrubados, enlace_do_bit, andamento,
                       limitar=True):
        for enlace in topologia.enlaces:
            self._enlace(topologia, enlace, pos, derrubados, enlace_do_bit, andamento)
        self._rotulos_de_interface(topologia, pos)
        self._rotulos_de_rede(topologia, pos, altura_util, limitar)
        for nome in topologia.roteadores + topologia.computadores:
            self._dispositivo(topologia, nome, pos, andamento)

    def _margens_que_cabem(self, topologia, largura, altura):
        """Margens (esquerda, topo, direita, base) com que nada do mapa sai do canvas.

        Parte de uma margem pequena, desenha a rede sem andamento e alarga
        cada lado pelo tanto que o desenho passou dele, contando o anel do
        dispositivo ativo: a rede ocupa todo o espaco que os rotulos deixam.
        O resultado so depende da topologia e dos tamanhos do canvas e do
        texto; por isso fica guardado, e o mapa nao se mexe de um passo para
        outro. None quando nenhuma margem basta: o canvas e pequeno demais.
        """
        chave = (largura, altura, self.fontes.fator)
        if self._ajuste and self._ajuste[0] == chave and self._ajuste[1] is topologia:
            return self._ajuste[2]
        c = self.canvas
        anel = self.fontes.px(6) + 3 + self.fontes.px(4)     # anel ativo e um respiro
        margens = [self.fontes.px(12)] * 4
        cabe = False
        for _ in range(6):
            if margens[0] + margens[2] >= largura - 20 or margens[1] + margens[3] >= altura - 20:
                break
            c.delete("all")
            pos = posicoes_no_mapa(topologia, largura, altura, margens)
            self._desenhar_rede(topologia, pos, altura, set(), None, None, limitar=False)
            x0, y0, x1, y1 = c.bbox("all") or (0, 0, 0, 0)
            for nome, (x, y) in pos.items():
                mw, mh = ((self.raio_do_roteador,) * 2 if nome in topologia.roteadores
                          else self.meio_computador)
                x0, y0 = min(x0, x - mw - anel), min(y0, y - mh - anel)
                x1, y1 = max(x1, x + mw + anel), max(y1, y + mh + anel)
            # O respiro so entra quando ha excesso: o nome da rede, preso a
            # borda na horizontal, encosta nela sem nunca passar.
            excesso = (-x0, -y0, x1 - largura, y1 - altura)
            if all(e <= 0 for e in excesso):
                cabe = True
                break
            margens = [m + e + 3 if e > 0 else m for m, e in zip(margens, excesso)]
        c.delete("all")
        self._ajuste = (chave, topologia, margens if cabe else None)
        return self._ajuste[2]

    def _borda(self, topologia, nome, ux, uy):
        """Distancia do centro do dispositivo ate a borda, na direcao (ux, uy)."""
        if nome in topologia.roteadores:
            return self.raio_do_roteador
        mw, mh = self.meio_computador
        return min(mw / abs(ux) if ux else math.inf, mh / abs(uy) if uy else math.inf)

    def _enlace(self, topologia, enlace, pos, derrubados, enlace_do_bit, andamento):
        c = self.canvas
        a, b = _dono(enlace.a), _dono(enlace.b)
        if a not in pos or b not in pos:
            return
        (xa, ya), (xb, yb) = pos[a], pos[b]
        chave = topologia.chave_do_enlace(enlace)
        fora = chave in derrubados
        if fora:
            c.create_line(xa, ya, xb, yb, fill=COR_DESCARTE, width=2, dash=(6, 4))
        elif andamento and chave == andamento.em_transito:
            c.create_line(xa, ya, xb, yb, fill=COR_TRANSITO, width=6)
        elif andamento and chave in andamento.percorridos:
            c.create_line(xa, ya, xb, yb, fill=COR_PERCORRIDO, width=4)
        else:
            c.create_line(xa, ya, xb, yb, fill=COR_ENLACE, width=2)

        mx, my = (xa + xb) / 2, (ya + yb) / 2
        comprimento = math.hypot(xb - xa, yb - ya) or 1
        ux, uy = (xb - xa) / comprimento, (yb - ya) / comprimento
        px = self.fontes.px
        if enlace.custo:
            # Ao lado da linha, para nao disputar lugar com os nomes de interface.
            afastamento = self.fontes.linha("pequena") * 0.8
            texto_com_fundo(c, mx - uy * afastamento, my + ux * afastamento, str(enlace.custo),
                            self.fontes["pequena"], COR_TEXTO_FRACO)
        if fora or (andamento and chave == andamento.enlace_perdido):
            marcar_x(c, mx, my, raio=px(7))
        if enlace is enlace_do_bit:
            marcar_raio(c, mx + ux * px(18), my + uy * px(18), self.fontes.fator)

    def _rotulos_de_interface(self, topologia, pos):
        """Um rotulo por interface, junto ao dispositivo, na direcao media dos seus enlaces.

        A e0 de R1 atende H1 e H2: aparece uma vez so, entre as duas linhas.
        """
        direcoes = {}
        for enlace in topologia.enlaces:
            a, b = _dono(enlace.a), _dono(enlace.b)
            if a not in pos or b not in pos:
                continue
            (xa, ya), (xb, yb) = pos[a], pos[b]
            comprimento = math.hypot(xb - xa, yb - ya) or 1
            ux, uy = (xb - xa) / comprimento, (yb - ya) / comprimento
            direcoes.setdefault(enlace.a, []).append((ux, uy))
            direcoes.setdefault(enlace.b, []).append((-ux, -uy))

        fonte = self.fontes["pequena"]
        meia_altura = self.fontes.linha("pequena") / 2
        for identificador, vetores in direcoes.items():
            dono, nome = identificador.split(":")
            sx, sy = sum(v[0] for v in vetores), sum(v[1] for v in vetores)
            norma = math.hypot(sx, sy)
            ux, uy = (sx / norma, sy / norma) if norma > 1e-6 else vetores[0]
            meia_largura = fonte.measure(nome) / 2
            distancia = (self._borda(topologia, dono, ux, uy) + meia_largura * abs(ux)
                         + meia_altura * abs(uy) + self.fontes.px(3))
            x, y = pos[dono]
            texto_com_fundo(self.canvas, x + ux * distancia, y + uy * distancia, nome, fonte, "#546e7a")

    def _rotulos_de_rede(self, topologia, pos, altura_util, limitar=True):
        """Nome e prefixo de cada rede, acima ou abaixo dos seus computadores.

        Sem limitar, o rotulo pode sair pelo topo ou pela base: e assim que o
        ajuste das margens descobre quanto espaco ele pede.
        """
        c = self.canvas
        fonte = self.fontes["pequena"]
        meia_altura = self.fontes.linha("pequena") / 2
        distancia = self.meio_computador[1] + meia_altura + self.fontes.px(5)
        largura = c.winfo_width()
        for nome_da_rede, prefixo in topologia.redes.items():
            membros = [pos[n] for n in topologia.computadores
                       if n in pos and topologia.interface_de(n).rede == nome_da_rede]
            if not membros:
                continue
            x = sum(p[0] for p in membros) / len(membros)
            acima = sum(p[1] for p in membros) / len(membros) < altura_util / 2
            y = (min(p[1] for p in membros) - distancia) if acima \
                else (max(p[1] for p in membros) + distancia)
            texto = f"{nome_da_rede} · {prefixo}"
            meia = fonte.measure(texto) / 2 + 4
            x = min(max(x, meia), largura - meia)
            if limitar:
                y = min(max(y, meia_altura + 1), altura_util - meia_altura - 1)
            c.create_text(x, y, text=texto, font=fonte, fill=COR_TEXTO_FRACO)

    def _dispositivo(self, topologia, nome, pos, andamento):
        c = self.canvas
        if nome not in pos:
            return
        x, y = pos[nome]
        alcancado = andamento is not None and nome in andamento.alcancados
        ativo = andamento is not None and andamento.evento is not None \
            and andamento.evento.dispositivo == nome
        borda = COR_PERCORRIDO if alcancado else "#607d8b"
        largura_da_borda = 3 if alcancado else 1.5
        anel = self.fontes.px(6)
        if nome in topologia.roteadores:
            r = self.raio_do_roteador
            if ativo:
                c.create_oval(x - r - anel, y - r - anel, x + r + anel, y + r + anel,
                              outline=COR_TRANSITO, width=3)
            c.create_oval(x - r, y - r, x + r, y + r, fill="#eceff1", outline=borda,
                          width=largura_da_borda)
        else:
            mw, mh = self.meio_computador
            if ativo:
                c.create_rectangle(x - mw - anel, y - mh - anel, x + mw + anel, y + mh + anel,
                                   outline=COR_TRANSITO, width=3)
            c.create_rectangle(x - mw, y - mh, x + mw, y + mh, fill="white", outline=borda,
                               width=largura_da_borda)
        c.create_text(x, y, text=nome, font=self.fontes["negrito"], fill=COR_TEXTO)
        if andamento is not None and nome in andamento.descartes:
            px = self.fontes.px
            marcar_x(c, x + px(14), y - px(14), raio=px(6))

    def _legenda(self, largura, altura):
        c = self.canvas
        fonte = self.fontes["pequena"]
        px = self.fontes.px
        y = altura - self._altura_da_legenda() / 2
        x = 10
        traco = px(20)
        itens = (
            ("percorrido", px(26), lambda x: c.create_line(x, y, x + traco, y, fill=COR_PERCORRIDO,
                                                           width=4)),
            ("em trânsito", px(26), lambda x: c.create_line(x, y, x + traco, y, fill=COR_TRANSITO,
                                                            width=6)),
            ("fora", px(26), lambda x: c.create_line(x, y, x + traco, y, fill=COR_DESCARTE, width=2,
                                                     dash=(6, 4))),
            ("erro de bit", px(14), lambda x: marcar_raio(c, x + px(5), y, self.fontes.fator)),
            ("número = custo", 0, None),
        )
        # Na janela minima os ultimos itens ficam de fora, e nao cortados.
        for texto, amostra, desenhar in itens:
            fim = x + amostra + fonte.measure(texto)
            if fim > largura - 6:
                break
            if desenhar:
                desenhar(x)
            c.create_text(x + amostra, y, text=texto, anchor="w", font=fonte, fill=COR_TEXTO_FRACO)
            x = fim + px(14)


# ----------------------------------------------------------------------
# V2 e V7: pilhas de camadas
# ----------------------------------------------------------------------

class Pilhas:
    """Uma pilha por dispositivo do caminho, alinhadas pela camada."""

    def __init__(self, canvas, fontes):
        self.canvas = canvas
        self.fontes = fontes

    def _altura_do_balao(self, linhas_de_descricao):
        f = self.fontes
        return (f.px(5) + f.linha("negrito") + f.px(2)
                + linhas_de_descricao * f.linha("pequena") + f.px(5))

    def _topo(self):
        """Altura do cabecalho das colunas: nome do dispositivo e papel."""
        f = self.fontes
        return f.px(2) + f.linha("negrito") + f.linha("pequena") + f.px(4)

    def altura_minima(self):
        """Altura do canvas com as sete camadas da altura do rotulo e o balao so com o titulo."""
        return self._topo() + 7 * (self.fontes.linha("pequena") + 4) + self._altura_do_balao(0) + 12

    def desenhar(self, dispositivos, papeis, roteadores, andamento, modo, aviso):
        c = self.canvas
        c.delete("all")
        largura, altura = c.winfo_width(), c.winfo_height()
        if largura < 80 or altura < 120:
            return
        f = self.fontes
        fonte = f["pequena"]
        if not dispositivos:
            linhas = quebrar(aviso, f["normal"], largura - 40, (altura - 16) // f.linha("normal"))
            c.create_text(largura / 2, altura / 2, text="\n".join(linhas),
                          font=f["normal"], fill=COR_TEXTO_FRACO, justify="center")
            return

        grupos = GRUPOS_TCPIP if modo == "TCP/IP" else GRUPOS_OSI
        margem = 8
        # Cabecalho de cada coluna: o nome do dispositivo e, embaixo, o papel.
        y_do_nome = f.px(2) + f.linha("negrito") / 2
        y_do_papel = f.px(2) + f.linha("negrito") + f.linha("pequena") / 2
        topo = self._topo()
        # O balao perde linhas de descricao antes de as camadas ficarem mais
        # baixas que o proprio rotulo.
        for linhas_do_balao in (2, 1, 0):
            base = altura - self._altura_do_balao(linhas_do_balao) - 12
            if (base - topo) / 7 >= f.linha("pequena") + 4:
                break
        linha = (base - topo) / 7
        rotulos = [r for r, _ in grupos] + [f"(L{min(n)}–L{max(n)})" for _, n in grupos if len(n) > 1]
        necessaria = max(fonte.measure(r) for r in rotulos) + margem + f.px(8)
        legenda = max(necessaria, min(f.px(110), int(largura * 0.2)))
        coluna = (largura - legenda - margem) / len(dispositivos)
        caixa = max(f.px(20), min(coluna - f.px(10), f.px(96)))

        def faixa(camadas):
            return topo + (7 - max(camadas)) * linha, topo + (8 - min(camadas)) * linha

        meia_linha = f.linha("pequena") / 2
        for i, (rotulo, camadas) in enumerate(grupos):
            y0, y1 = faixa(camadas)
            if i % 2 == 0:
                c.create_rectangle(margem, y0, largura - margem, y1, fill="#fafafa", outline="")
            meio = (y0 + y1) / 2
            if len(camadas) > 1:
                c.create_text(legenda - 6, meio - meia_linha, text=rotulo, anchor="e",
                              font=fonte, fill=COR_TEXTO)
                c.create_text(legenda - 6, meio + meia_linha,
                              text=f"(L{min(camadas)}–L{max(camadas)})",
                              anchor="e", font=fonte, fill=COR_TEXTO_FRACO)
            else:
                c.create_text(legenda - 6, meio, text=rotulo, anchor="e", font=fonte, fill=COR_TEXTO)

        # Quando os papeis nao cabem nas colunas, o dos roteadores sai (a pilha
        # de tres camadas ja diz o que eles sao) e o de origem e destino se
        # estende sobre as colunas vizinhas que ficaram vazias.
        papeis_visiveis = [papeis.get(nome, "") for nome in dispositivos]
        vao = f.px(6)           # entre os papeis de colunas vizinhas
        if any(fonte.measure(p) > coluna - vao for p in papeis_visiveis):
            papeis_visiveis = ["" if nome in roteadores else papel
                               for nome, papel in zip(dispositivos, papeis_visiveis)]

        evento = andamento.evento if andamento else None
        centros = {}
        for i, nome in enumerate(dispositivos):
            x = legenda + coluna * (i + 0.5)
            centros[nome] = x
            alcancado = andamento is not None and nome in andamento.alcancados
            c.create_text(x, y_do_nome, text=caber(nome, f["negrito"], coluna - 2),
                          font=f["negrito"], fill=COR_TEXTO if alcancado else CINZA_TEXTO)
            esquerda = (margem if i == 0
                        else x - coluna / 2 - (0 if papeis_visiveis[i - 1] else coluna / 2))
            direita = (largura - margem if i == len(dispositivos) - 1
                       else x + coluna / 2 + (0 if papeis_visiveis[i + 1] else coluna / 2))
            papel = caber(papeis_visiveis[i], fonte, direita - esquerda - vao)
            meia = fonte.measure(papel) / 2
            c.create_text(min(max(x, esquerda + meia + 1), direita - meia - 1), y_do_papel, text=papel,
                          font=fonte, fill=COR_TEXTO_FRACO if alcancado else CINZA_TEXTO)
            proprias = (3, 2, 1) if nome in roteadores else (7, 6, 5, 4, 3, 2, 1)
            for rotulo, camadas in grupos:
                visiveis = [n for n in camadas if n in proprias]
                if visiveis:
                    y0, y1 = faixa(visiveis)
                    self._caixa(nome, visiveis, x - caixa / 2, y0 + 2, x + caixa / 2, y1 - 2,
                                alcancado, evento, andamento, nome in roteadores)

        self._balao(evento, centros, roteadores, largura, base, altura, aviso, linhas_do_balao)

    def _caixa(self, nome, camadas, x0, y0, x1, y1, alcancado, evento, andamento, roteador):
        c = self.canvas
        rotulo = f"L{camadas[0]}" if len(camadas) == 1 else f"L{camadas[-1]}–{camadas[0]}"
        ativa = evento is not None and evento.dispositivo == nome and evento.camada in camadas
        descartada = andamento is not None and andamento.descartes.get(nome) in camadas
        fonte = self.fontes["pequena"]
        cabe = x1 - x0 + 4           # o rotulo pode tocar a borda, e nunca passar dela

        if not alcancado:
            c.create_rectangle(x0, y0, x1, y1, fill=CINZA_FUNDO, outline=CINZA_BORDA)
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=caber(rotulo, fonte, cabe), font=fonte,
                          fill=CINZA_TEXTO)
            return
        if ativa and evento.acao == "ROTEIA" and roteador:
            # A decisao de rota: a caixa cresce, muda de cor e ganha borda grossa.
            c.create_rectangle(x0 - 6, y0 - 4, x1 + 6, y1 + 4, fill=COR_ROTA,
                               outline=BORDA_ROTA, width=4)
            negrito = self.fontes["negrito"]
            if y1 - y0 >= 2 * negrito.metrics("linespace") + 2:
                texto = f"{rotulo}\nROTA"
            elif negrito.measure(f"{rotulo} ROTA") <= x1 - x0 + 8:
                texto = f"{rotulo} ROTA"
            else:
                texto = caber("ROTA", negrito, cabe + 8)
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=texto, font=negrito, fill="white",
                          justify="center")
            return
        if ativa:
            cor = COR_DESCARTE if evento.acao == "DESCARTA" else COR_ATIVA[camadas[0]]
            c.create_rectangle(x0 - 3, y0 - 2, x1 + 3, y1 + 2, fill=cor, outline="#1b1b1b", width=3)
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=caber(rotulo, self.fontes["negrito"], cabe),
                          font=self.fontes["negrito"], fill="white")
            return
        c.create_rectangle(x0, y0, x1, y1, fill=COR_DA_CAMADA[camadas[0]],
                           outline=COR_DESCARTE if descartada else "#9e9e9e",
                           width=3 if descartada else 1)
        c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=caber(rotulo, fonte, cabe), font=fonte,
                      fill=COR_DESCARTE if descartada else COR_TEXTO)

    def _balao(self, evento, centros, roteadores, largura, base, altura, aviso, linhas_do_balao):
        c = self.canvas
        f = self.fontes
        fonte = f["pequena"]
        x0, y0, x1, y1 = 8, base + 8, largura - 8, altura - 4
        if evento is None:
            linhas = quebrar(aviso, fonte, x1 - x0 - 12, int(y1 - y0) // f.linha("pequena"))
            c.create_text(largura / 2, (y0 + y1) / 2, text="\n".join(linhas),
                          font=fonte, fill=COR_TEXTO_FRACO, justify="center")
            return

        rota = evento.acao == "ROTEIA" and evento.dispositivo in roteadores
        if rota:
            titulo = f"DECISÃO DE ROTA em {evento.dispositivo} (camada 3)"
            fundo, borda, cor = FUNDO_ROTA, COR_ROTA, BORDA_ROTA
        elif evento.acao == "DESCARTA":
            titulo = f"DESCARTE em {evento.dispositivo} (camada {evento.camada})"
            fundo, borda, cor = FUNDO_DESCARTE, COR_DESCARTE, COR_DESCARTE
        else:
            titulo = f"{evento.passo:03d} · {evento.dispositivo} · L{evento.camada} · {evento.acao}"
            fundo, borda, cor = "white", CINZA_BORDA, COR_TEXTO

        x = centros.get(evento.dispositivo, largura / 2)
        c.create_rectangle(x0, y0, x1, y1, fill=fundo, outline=borda, width=2 if borda != CINZA_BORDA else 1)
        c.create_polygon(x - 7, y0 + 1, x + 7, y0 + 1, x, y0 - 8, fill=fundo, outline=borda)
        c.create_line(x - 6, y0 + 1, x + 6, y0 + 1, fill=fundo, width=2)
        negrito = f["negrito"]
        c.create_text(x0 + 8, y0 + f.px(5), anchor="nw", text=caber(titulo, negrito, x1 - x0 - 16),
                      font=negrito, fill=cor)
        if linhas_do_balao:
            linhas = quebrar(evento.descricao, fonte, x1 - x0 - 16, linhas_do_balao)
            c.create_text(x0 + 8, y0 + f.px(5) + f.linha("negrito") + f.px(2), anchor="nw",
                          text="\n".join(linhas), font=fonte, fill=COR_TEXTO)


# ----------------------------------------------------------------------
# V3: unidade de dados em blocos
# ----------------------------------------------------------------------

def _cor_do_bloco(rotulo):
    if rotulo == "Dados":
        return COR_DA_CAMADA[7]
    return COR_DA_CAMADA[int(rotulo[1:])]


def _titulo_da_unidade(unidade, octetos):
    nome = unidade.nome_da_unidade
    if nome == "Segmento":
        nome += f" {unidade.numero_segmento} de {unidade.total_segmentos}"
    elif nome == "Pacote" and unidade.id_pacote:
        nome += f" {unidade.id_pacote}"
    elif nome == "Quadro" and unidade.numero_quadro:
        nome += f" {unidade.numero_quadro}"
    elif nome == "Bits" and unidade.numero_quadro:
        nome += f" do quadro {unidade.numero_quadro}"
    if unidade.nome_da_unidade == "Bits":
        return f"{nome} · {octetos * 8} bits ({octetos} B)"
    return f"{nome} · {octetos} B"


def _descrever_dados(unidade):
    dados = unidade.dados
    if isinstance(dados, str):
        return f"Dados em texto: {dados!r}"
    amostra = " ".join(f"{o:02x}" for o in dados[:24])
    estado = "cifrados com XOR" if unidade.cifrado else "em octetos"
    return f"Dados {estado}: {amostra}{' …' if len(dados) > 24 else ''}"


def _campos_do_cabecalho(cabecalho):
    """Os campos de um Cabecalho como chave=valor; a soma de verificacao em hexadecimal."""
    return [f"{chave}={valor:#010x}" if chave == "soma" else f"{chave}={valor}"
            for chave, valor in cabecalho.campos.items()]


def _rotulo_do_cabecalho(cabecalho, com_nome):
    rotulo = f"{'T' if cabecalho.finalizador else 'H'}{cabecalho.camada}"
    if not com_nome:
        return rotulo
    return f"{rotulo} {'finalizador' if cabecalho.finalizador else NOMES_OSI[cabecalho.camada]}"


class Blocos:
    """Cabecalhos a esquerda, dados no meio, finalizador a direita, com os tamanhos.

    Abaixo dos blocos, uma faixa por cabecalho presente, na cor da camada,
    com os campos dele.
    """

    def __init__(self, canvas, fontes):
        self.canvas = canvas
        self.fontes = fontes

    def altura_minima(self):
        """Altura do canvas para o titulo, os blocos, a legenda e uma faixa."""
        f = self.fontes
        return (f.px(10) + f.linha("titulo") + f.linha("negrito") + 2 * f.linha("pequena")
                + f.px(18) + 2 + max(f.linha("mono"), f.linha("negrito")) + 2 * f.px(3))

    def desenhar(self, unidade, evento):
        c = self.canvas
        c.delete("all")
        largura, altura = c.winfo_width(), c.winfo_height()
        if largura < 80 or altura < 60:
            return
        f = self.fontes
        margem = 10
        disponivel = largura - 2 * margem
        if unidade is None:
            linhas = quebrar("A unidade de dados aparece aqui a partir do primeiro passo.",
                             f["normal"], disponivel, altura // f.linha("normal"))
            c.create_text(largura / 2, altura / 2, font=f["normal"], fill=COR_TEXTO_FRACO,
                          text="\n".join(linhas), justify="center")
            return

        blocos = unidade.em_blocos()
        octetos = sum(b["octetos"] for b in blocos)
        fonte, negrito = f["pequena"], f["negrito"]
        # O titulo tem a largura toda; onde a unidade esta fica com o que sobrar.
        y = f.px(4) + f.linha("titulo") / 2
        titulo = caber(_titulo_da_unidade(unidade, octetos), f["titulo"], disponivel)
        c.create_text(margem, y, anchor="w", text=titulo, font=f["titulo"], fill=COR_TEXTO)
        onde = caber(f"em {evento.dispositivo}, camada {evento.camada} ({NOMES_OSI[evento.camada]})",
                     fonte, disponivel - f["titulo"].measure(titulo) - f.px(16))
        if onde.strip("…"):
            c.create_text(largura - margem, y, anchor="e", font=fonte, fill=COR_TEXTO_FRACO, text=onde)

        # Blocos com rotulo e tamanho em duas linhas; sem altura para isso,
        # numa linha so ("H3 20 B"), para os blocos nunca sumirem.
        y0 = f.px(10) + f.linha("titulo")
        compactos = y0 + f.linha("negrito") + f.linha("pequena") + f.px(8) > altura
        if compactos:
            y0 = f.px(6) + f.linha("titulo")
            y1 = y0 + f.linha("negrito") + f.px(6)
            if y1 > altura:
                return
        else:
            y1 = y0 + f.linha("negrito") + f.linha("pequena") + f.px(8)

        # Largura proporcional aos octetos, com um minimo que caiba o texto.
        if compactos:
            minimas = [negrito.measure(f"{b['rotulo']} {b['octetos']} B") + f.px(12) for b in blocos]
        else:
            minimas = [max(negrito.measure(b["rotulo"]), fonte.measure(f"{b['octetos']} B")) + f.px(12)
                       for b in blocos]
        sobra = max(0, disponivel - sum(minimas))
        larguras = [m + sobra * b["octetos"] / max(octetos, 1) for m, b in zip(minimas, blocos)]
        if sum(larguras) > disponivel:
            fator = disponivel / sum(larguras)
            larguras = [w * fator for w in larguras]

        y_do_rotulo = y0 + f.px(4) + f.linha("negrito") / 2
        y_do_tamanho = y0 + f.px(4) + f.linha("negrito") + f.linha("pequena") / 2
        x = margem
        regioes = {}
        for bloco, w in zip(blocos, larguras):
            c.create_rectangle(x, y0, x + w, y1, fill=_cor_do_bloco(bloco["rotulo"]), outline="#616161")
            if compactos:
                c.create_text(x + w / 2, (y0 + y1) / 2, font=negrito, fill=COR_TEXTO,
                              text=caber(f"{bloco['rotulo']} {bloco['octetos']} B", negrito, w - 4))
            else:
                c.create_text(x + w / 2, y_do_rotulo, text=caber(bloco["rotulo"], negrito, w - 4),
                              font=negrito, fill=COR_TEXTO)
                c.create_text(x + w / 2, y_do_tamanho, text=caber(f"{bloco['octetos']} B", fonte, w - 4),
                              font=fonte, fill=COR_TEXTO)
            tipo = ("dados" if bloco["rotulo"] == "Dados"
                    else "finalizador" if bloco["rotulo"].startswith("T") else "cabeçalhos")
            inicio, _ = regioes.get(tipo, (x, x))
            regioes[tipo] = (inicio, x + w)
            x += w

        faixas = self._arranjar_faixas(unidade, disponivel) if unidade.cabecalhos else None
        primeira = faixas[0][0][2] if faixas else f.linha("mono")
        # Com pouca altura, a legenda das regioes cede o lugar a primeira linha.
        y_do_traco = y1 + f.px(4)
        topo = y_do_traco + 2 + f.linha("pequena") + f.px(6)
        if topo + primeira > altura and y1 + f.px(6) + primeira <= altura:
            topo = y1 + f.px(6)
        elif y_do_traco + 2 + f.linha("pequena") > altura:
            return
        else:
            y_da_regiao = y_do_traco + 2 + f.linha("pequena") / 2
            for tipo, (inicio, fim) in regioes.items():
                c.create_line(inicio + 2, y_do_traco, fim - 2, y_do_traco, fill=COR_TEXTO_FRACO)
                c.create_text((inicio + fim) / 2, y_da_regiao, text=caber(tipo, fonte, fim - inicio),
                              font=fonte, fill=COR_TEXTO_FRACO)

        if faixas:
            self._desenhar_faixas(unidade, faixas, margem, topo, disponivel, altura)
        elif topo + f.linha("mono") <= altura:
            # So o bloco Dados: a descricao dele, numa linha.
            c.create_text(margem, topo + f.linha("mono") / 2, anchor="w", font=f["mono"],
                          fill=COR_TEXTO, text=caber(_descrever_dados(unidade), f["mono"], disponivel))

    def _arranjar_faixas(self, unidade, largura):
        """Uma faixa por cabecalho, na ordem dos blocos; a linha dos dados no lugar do bloco Dados.

        Os campos de cada Cabecalho seguem da esquerda para a direita e mudam
        de linha onde nao cabem. Devolve os itens como (cabecalho ou None,
        linhas de campos, altura), com a largura da coluna dos rotulos, a da
        area dos campos e se os rotulos levam o nome da camada.
        """
        f = self.fontes
        negrito, mono = f["negrito"], f["mono"]
        altura_da_linha = max(f.linha("mono"), f.linha("negrito"))
        recuo = f.px(6)
        espaco = mono.measure("  ")

        cabecalhos = [cab for cab in unidade.cabecalhos if not cab.finalizador]
        finalizadores = [cab for cab in unidade.cabecalhos if cab.finalizador]
        presentes = cabecalhos + finalizadores

        # O nome da camada acompanha o rotulo quando sobra largura para os campos.
        mais_largo = max((mono.measure(campo) for cab in presentes
                          for campo in _campos_do_cabecalho(cab)), default=0)
        for com_nome in (True, False):
            coluna = max(negrito.measure(_rotulo_do_cabecalho(cab, com_nome)) for cab in presentes)
            coluna += 2 * recuo
            area = largura - coluna - recuo
            if not com_nome or area >= max(mais_largo, largura * 0.5):
                break

        itens = []
        for cab in cabecalhos + [None] + finalizadores:
            if cab is None:
                itens.append((None, [], f.linha("mono")))
                continue
            linhas, usado = [[]], 0
            for campo in _campos_do_cabecalho(cab):
                w = mono.measure(campo)
                if linhas[-1] and usado + espaco + w > area:
                    linhas.append([])
                    usado = 0
                usado += (espaco if linhas[-1] else 0) + w
                linhas[-1].append(campo)
            itens.append((cab, linhas, len(linhas) * altura_da_linha + 2 * f.px(3)))
        return itens, coluna, area, com_nome

    def _desenhar_faixas(self, unidade, faixas, x0, topo, largura, altura):
        """Desenha as faixas de cima para baixo. O que nao cabe na altura do
        canvas e anunciado numa linha final, e nunca cortado pela borda."""
        c = self.canvas
        f = self.fontes
        negrito, mono = f["negrito"], f["mono"]
        altura_da_linha = max(f.linha("mono"), f.linha("negrito"))
        folga, recuo = f.px(3), f.px(6)
        itens, coluna, area, com_nome = faixas
        y = topo
        for i, (cab, linhas, altura_do_item) in enumerate(itens):
            if y + altura_do_item > altura:
                faltam = ["Dados" if resto is None else _rotulo_do_cabecalho(resto, False)
                          for resto, _, _ in itens[i:]]
                aviso = caber(f"… sem espaço para {', '.join(faltam)}", f["pequena"], largura)
                if y + f.linha("pequena") <= altura:
                    c.create_text(x0, y + f.linha("pequena") / 2, anchor="w", text=aviso,
                                  font=f["pequena"], fill=COR_TEXTO_FRACO)
                return
            if cab is None:
                c.create_text(x0, y + altura_do_item / 2, anchor="w", font=mono, fill=COR_TEXTO,
                              text=caber(_descrever_dados(unidade), mono, largura))
            else:
                c.create_rectangle(x0, y, x0 + largura, y + altura_do_item,
                                   fill=COR_DA_CAMADA[cab.camada], outline=COR_ATIVA[cab.camada])
                c.create_text(x0 + recuo, y + folga + altura_da_linha / 2, anchor="w",
                              text=caber(_rotulo_do_cabecalho(cab, com_nome), negrito, coluna - recuo),
                              font=negrito, fill=COR_TEXTO)
                for j, campos in enumerate(linhas):
                    c.create_text(x0 + coluna, y + folga + (j + 0.5) * altura_da_linha, anchor="w",
                                  text=caber("  ".join(campos), mono, area),
                                  font=mono, fill=COR_TEXTO)
            y += altura_do_item + f.px(4)


# ----------------------------------------------------------------------
# Janela
# ----------------------------------------------------------------------

class JanelaIndisponivel(Exception):
    """O tkinter nao conseguiu abrir uma janela (sem tela grafica, por exemplo)."""


class Janela:
    """A janela do simulador: monta os paineis e conduz a execucao."""

    # Na barra lateral, no tamanho de texto Normal: largura da lista de
    # cenarios, em caracteres, e das notas com quebra de linha, em pixels.
    LARGURA_DO_CENARIO = 20
    LARGURA_DAS_NOTAS = 220

    def __init__(self, raiz, carregar_topologia):
        self.raiz = raiz
        self.carregar_topologia = carregar_topologia
        self.topologia = None
        self.erro_de_topologia = None

        self.cenario = None
        self.modificado = False
        self.erro_de_configuracao = None
        self.sim = None
        self.andamento = None
        self.dispositivos = []
        self.papeis = {}
        self.total_de_passos = 0

        self.rodando = False
        self._agendado = None
        self._desenho_agendado = None
        self._preenchendo = False
        self._enlaces = {}
        self._quebraveis = []       # rotulos da barra lateral com quebra de linha

        self.fontes = Tipografia()
        self._construir()
        raiz.report_callback_exception = self._erro_inesperado
        raiz.protocol("WM_DELETE_WINDOW", self.fechar)
        self._dimensionar()
        self._abrir_topologia(primeira_vez=True)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _dimensionar(self):
        """Tamanho adaptado a tela, com minimo de 1100x700 (ou a tela, se menor)."""
        raiz = self.raiz
        tela_l, tela_a = raiz.winfo_screenwidth(), raiz.winfo_screenheight()
        minima_l, minima_a = min(LARGURA_MINIMA, tela_l), min(ALTURA_MINIMA, tela_a)
        raiz.minsize(minima_l, minima_a)
        # Folga para a barra de titulo e a barra de tarefas ou o menu do sistema.
        largura = max(minima_l, min(LARGURA_PREFERIDA, tela_l - 60))
        altura = max(minima_a, min(ALTURA_PREFERIDA, tela_a - 120))
        x = max(0, (tela_l - largura) // 2)
        y = max(0, (tela_a - altura) // 2 - 20)
        raiz.geometry(f"{largura}x{altura}+{x}+{y}")
        if tela_a - altura < 120 or tela_l - largura < 40:
            # Numa tela de 1366x768 so maximizada a janela cabe inteira.
            try:
                raiz.state("zoomed")
            except tk.TclError:
                try:
                    raiz.attributes("-zoomed", True)
                except tk.TclError:
                    pass

    def _construir(self):
        raiz = self.raiz
        raiz.title("Simulador do modelo OSI")
        raiz.option_add("*tearOff", False)
        estilo = self._fixar_paleta()
        estilo.configure("Invalido.TEntry", foreground=COR_DESCARTE)
        estilo.configure("Invalido.TCombobox", foreground=COR_DESCARTE)
        estilo.configure("Titulo.TLabel", font=self.fontes["titulo"])
        estilo.configure("Fraco.TLabel", foreground=COR_TEXTO_FRACO, font=self.fontes["pequena"])
        estilo.configure("Erro.TLabel", foreground=COR_DESCARTE, font=self.fontes["pequena"])

        self._menu()
        barra = ttk.Frame(raiz, padding=(8, 6, 8, 6))
        barra.pack(side="top", fill="x")
        self._barra_de_controle(barra)

        corpo = ttk.Frame(raiz, padding=(8, 0, 8, 8))
        corpo.pack(side="top", fill="both", expand=True)
        self._barra_lateral(self._lateral_com_rolagem(corpo))

        self.paineis = ttk.PanedWindow(corpo, orient="vertical")
        self.paineis.pack(side="left", fill="both", expand=True)
        linhas = []
        for peso in (5, 3):
            linha = ttk.Frame(self.paineis)
            linha.columnconfigure(0, weight=1, uniform="colunas")
            linha.columnconfigure(1, weight=1, uniform="colunas")
            linha.rowconfigure(0, weight=1)
            self.paineis.add(linha, weight=peso)
            linhas.append(linha)

        self.mapa = Mapa(self._painel_de_canvas(linhas[0], 0, "Mapa da rede"), self.fontes)
        self.pilhas = Pilhas(self._painel_de_canvas(linhas[0], 1, "Pilhas de camadas"), self.fontes)
        self.blocos = Blocos(self._painel_de_canvas(linhas[1], 0, "Unidade de dados"), self.fontes)
        self._painel_de_enderecos(linhas[1])

        registro = ttk.Frame(self.paineis)
        self.paineis.add(registro, weight=3)
        self._painel_de_registro(registro)
        self.raiz.after(60, self._posicionar_divisorias)

        raiz.bind("<space>", self._tecla_espaco)
        raiz.bind("<Right>", self._tecla_direita)

    def _fixar_paleta(self):
        """Prende a janela inteira a paleta deste modulo, ignorando o tema do sistema.

        Duas coisas sao precisas para isso. Primeiro o tema 'clam', o unico
        que acompanha o Tk em todo sistema e desenha os widgets ttk com as
        cores pedidas: os temas nativos ('vista' no Windows, 'aqua' no macOS)
        pintam por conta propria e mudam com a aparencia do sistema. Depois,
        cada estilo recebe fundo e cor de texto explicitos, inclusive nos
        estados (desabilitado, so de leitura, sob o ponteiro, pressionado),
        que no clam sao clareados a partir do fundo se ficarem de fora.

        As opcoes de option_add valem para os widgets tk que o Tk cria por
        dentro e que nao podem ser configurados daqui: a lista suspensa de
        cada Combobox e os menus. Por isso este metodo vem antes de qualquer
        widget da janela.
        """
        raiz = self.raiz
        # A propria janela: o padrao de option_add ("*...") nao alcanca a raiz.
        raiz.configure(bg=FUNDO_JANELA, highlightbackground=FUNDO_JANELA,
                       highlightcolor=BORDA_CAMPO)
        for opcao, valor in (
            # Lista suspensa dos Combobox (um tk.Listbox criado pelo proprio Tk).
            ("*TCombobox*Listbox.background", FUNDO_CAMPO),
            ("*TCombobox*Listbox.foreground", COR_TEXTO),
            ("*TCombobox*Listbox.selectBackground", SELECAO_FUNDO),
            ("*TCombobox*Listbox.selectForeground", SELECAO_TEXTO),
            # Qualquer Listbox ou Text que venha a existir sem cor propria.
            ("*Listbox.background", FUNDO_CAMPO),
            ("*Listbox.foreground", COR_TEXTO),
            ("*Listbox.selectBackground", SELECAO_FUNDO),
            ("*Listbox.selectForeground", SELECAO_TEXTO),
            ("*Text.background", FUNDO_CAMPO),
            ("*Text.foreground", COR_TEXTO),
            ("*Text.insertBackground", COR_TEXTO),
            ("*Text.selectBackground", SELECAO_FUNDO),
            ("*Text.selectForeground", SELECAO_TEXTO),
            ("*Entry.background", FUNDO_CAMPO),
            ("*Entry.foreground", COR_TEXTO),
            ("*Entry.insertBackground", COR_TEXTO),
            ("*Entry.selectBackground", SELECAO_FUNDO),
            ("*Entry.selectForeground", SELECAO_TEXTO),
            # Um Canvas tambem tem cursor e selecao proprios, que no macOS vem
            # de systemSelectedTextColor e mudam com o tema mesmo sem uso.
            ("*Canvas.insertBackground", COR_TEXTO),
            ("*Canvas.selectBackground", SELECAO_FUNDO),
            ("*Canvas.selectForeground", SELECAO_TEXTO),
            ("*Label.activeBackground", FUNDO_JANELA),
            ("*Label.activeForeground", COR_TEXTO),
            ("*Label.disabledForeground", COR_TEXTO_INATIVO),
            # O anel de foco de qualquer widget tk. Onde a espessura e zero ele
            # nao aparece, mas o padrao ainda era uma cor do sistema.
            ("*highlightBackground", FUNDO_JANELA),
            ("*highlightColor", BORDA_CAMPO),
            # Menus: a barra e desenhada pelo sistema no Windows, os menus nao.
            ("*Menu.background", FUNDO_MENU),
            ("*Menu.foreground", COR_TEXTO),
            ("*Menu.activeBackground", FUNDO_MENU_ATIVO),
            ("*Menu.activeForeground", SELECAO_TEXTO),
            ("*Menu.disabledForeground", COR_TEXTO_INATIVO),
            ("*Menu.selectColor", COR_TEXTO),
        ):
            raiz.option_add(opcao, valor)

        estilo = ttk.Style(raiz)
        try:
            estilo.theme_use("clam")
        except tk.TclError:      # Tk sem o clam: segue com o tema em uso
            pass

        estilo.configure(
            ".", background=FUNDO_JANELA, foreground=COR_TEXTO,
            fieldbackground=FUNDO_CAMPO, insertcolor=COR_TEXTO,
            troughcolor=FUNDO_TRILHO, bordercolor=BORDA_CAMPO,
            lightcolor=FUNDO_JANELA, darkcolor=FUNDO_JANELA,
            focuscolor=SELECAO_FUNDO, arrowcolor=COR_TEXTO,
            selectbackground=SELECAO_FUNDO, selectforeground=SELECAO_TEXTO,
        )
        estilo.map(".", foreground=[("disabled", COR_TEXTO_INATIVO)])

        estilo.configure("TFrame", background=FUNDO_JANELA)
        estilo.configure("TLabel", background=FUNDO_JANELA, foreground=COR_TEXTO)
        estilo.configure("TLabelframe", background=FUNDO_JANELA, bordercolor=BORDA_CAMPO,
                         lightcolor=FUNDO_JANELA, darkcolor=FUNDO_JANELA)
        estilo.configure("TLabelframe.Label", background=FUNDO_JANELA, foreground=COR_TEXTO)
        estilo.configure("TSeparator", background=BORDA_CAMPO)
        estilo.configure("TPanedWindow", background=FUNDO_JANELA)
        estilo.configure("Sash", background=FUNDO_JANELA, lightcolor=FUNDO_JANELA,
                         bordercolor=BORDA_CAMPO, gripcount=10)

        estilo.configure("TButton", background=FUNDO_BOTAO, foreground=COR_TEXTO,
                         bordercolor=BORDA_CAMPO, lightcolor=FUNDO_BOTAO,
                         darkcolor=FUNDO_BOTAO, focuscolor=COR_TEXTO)
        estilo.map("TButton",
                   background=[("disabled", FUNDO_JANELA), ("pressed", FUNDO_BOTAO_PRESSIONADO),
                               ("active", FUNDO_BOTAO_SOB)],
                   lightcolor=[("pressed", FUNDO_BOTAO_PRESSIONADO), ("active", FUNDO_BOTAO_SOB)],
                   darkcolor=[("pressed", FUNDO_BOTAO_PRESSIONADO), ("active", FUNDO_BOTAO_SOB)],
                   foreground=[("disabled", COR_TEXTO_INATIVO)])

        for classe in ("TCheckbutton", "TRadiobutton"):
            estilo.configure(classe, background=FUNDO_JANELA, foreground=COR_TEXTO,
                             indicatorbackground=FUNDO_CAMPO, indicatorforeground=COR_TEXTO,
                             bordercolor=BORDA_CAMPO, lightcolor=FUNDO_JANELA,
                             darkcolor=FUNDO_JANELA, focuscolor=COR_TEXTO)
            estilo.map(classe,
                       background=[("active", FUNDO_JANELA)],
                       foreground=[("disabled", COR_TEXTO_INATIVO)],
                       indicatorbackground=[("disabled", FUNDO_CAMPO_INATIVO),
                                            ("pressed", FUNDO_BOTAO_PRESSIONADO),
                                            ("selected", FUNDO_CAMPO), ("active", FUNDO_CAMPO)],
                       indicatorforeground=[("disabled", COR_TEXTO_INATIVO),
                                            ("selected", COR_TEXTO)])

        for classe in ("TEntry", "TCombobox", "TSpinbox"):
            estilo.configure(classe, foreground=COR_TEXTO, fieldbackground=FUNDO_CAMPO,
                             background=FUNDO_BOTAO, insertcolor=COR_TEXTO,
                             bordercolor=BORDA_CAMPO, lightcolor=FUNDO_CAMPO,
                             darkcolor=FUNDO_CAMPO, arrowcolor=COR_TEXTO,
                             selectbackground=SELECAO_FUNDO, selectforeground=SELECAO_TEXTO)
            estilo.map(classe,
                       fieldbackground=[("disabled", FUNDO_CAMPO_INATIVO),
                                        ("readonly", FUNDO_CAMPO_FIXO)],
                       foreground=[("disabled", COR_TEXTO_INATIVO)],
                       background=[("disabled", FUNDO_CAMPO_INATIVO),
                                   ("pressed", FUNDO_BOTAO_PRESSIONADO),
                                   ("active", FUNDO_BOTAO_SOB)],
                       arrowcolor=[("disabled", COR_TEXTO_INATIVO)],
                       lightcolor=[("disabled", FUNDO_CAMPO_INATIVO),
                                   ("readonly", FUNDO_CAMPO_FIXO)],
                       darkcolor=[("disabled", FUNDO_CAMPO_INATIVO),
                                  ("readonly", FUNDO_CAMPO_FIXO)],
                       # Num Combobox so de leitura o texto aparece selecionado
                       # enquanto o campo tem o foco; aqui ele fica igual ao resto.
                       selectbackground=[("readonly", FUNDO_CAMPO_FIXO),
                                         ("disabled", FUNDO_CAMPO_INATIVO)],
                       selectforeground=[("readonly", COR_TEXTO),
                                         ("disabled", COR_TEXTO_INATIVO)])

        estilo.configure("TScrollbar", background=PUXADOR_ROLAGEM, troughcolor=FUNDO_TRILHO,
                         bordercolor=FUNDO_TRILHO, lightcolor=PUXADOR_ROLAGEM,
                         darkcolor=PUXADOR_ROLAGEM, arrowcolor=COR_TEXTO)
        estilo.map("TScrollbar",
                   background=[("disabled", FUNDO_TRILHO), ("active", PUXADOR_ROLAGEM_SOB)],
                   lightcolor=[("active", PUXADOR_ROLAGEM_SOB)],
                   darkcolor=[("active", PUXADOR_ROLAGEM_SOB)],
                   arrowcolor=[("disabled", COR_TEXTO_INATIVO)])
        return estilo

    def _menu(self):
        cores = dict(bg=FUNDO_MENU, fg=COR_TEXTO, activebackground=FUNDO_MENU_ATIVO,
                     activeforeground=SELECAO_TEXTO, disabledforeground=COR_TEXTO_INATIVO,
                     selectcolor=COR_TEXTO, borderwidth=1, activeborderwidth=1)
        barra = tk.Menu(self.raiz, **cores)
        arquivo = tk.Menu(barra, **cores)
        arquivo.add_command(label="Recarregar topologia", command=self.recarregar_topologia)
        arquivo.add_command(label="Salvar registro…", command=self.salvar_registro)
        arquivo.add_command(label="Gerar registros dos sete cenários",
                            command=self.regerar_registros)
        arquivo.add_separator()
        arquivo.add_command(label="Sair", command=self.fechar)
        barra.add_cascade(label="Arquivo", menu=arquivo)
        self.raiz.config(menu=barra)

    def _barra_de_controle(self, barra):
        self.barra = barra
        # As linhas vem antes dos grupos: criados depois, os grupos ficam por
        # cima delas na ordem de empilhamento e aparecem.
        self._linhas_da_barra = [ttk.Frame(barra) for _ in range(5)]
        self._grupos = []           # (separador antes do grupo, grupo)
        self._arranjo = None

        def grupo():
            separador = ttk.Separator(barra, orient="vertical") if self._grupos else None
            conteudo = ttk.Frame(barra)
            self._grupos.append((separador, conteudo))
            return conteudo

        controles = grupo()
        self.botoes = {}
        for chave, texto, comando in (
            ("passo", "Passo", self.passo),
            ("executar", "Executar", self.executar),
            ("pausar", "Pausar", self.pausar),
            ("fim", "Até o fim", self.ate_o_fim),
            ("reiniciar", "Reiniciar", self.reiniciar),
        ):
            botao = ttk.Button(controles, text=texto, command=comando, takefocus=False)
            botao.pack(side="left", padx=(0, 4))
            self.botoes[chave] = botao

        controles = grupo()
        ttk.Label(controles, text="Velocidade:").pack(side="left", padx=(0, 4))
        self.velocidade = tk.StringVar(value="Normal")
        for nome, _ in VELOCIDADES:
            ttk.Radiobutton(controles, text=nome, value=nome, variable=self.velocidade,
                            takefocus=False).pack(side="left")

        controles = grupo()
        ttk.Label(controles, text="Pilha:").pack(side="left", padx=(0, 4))
        self.modo = tk.StringVar(value="OSI")
        for nome in ("OSI", "TCP/IP"):
            ttk.Radiobutton(controles, text=nome, value=nome, variable=self.modo, takefocus=False,
                            command=self._agendar_desenho).pack(side="left")

        controles = grupo()
        ttk.Label(controles, text="Texto:").pack(side="left", padx=(0, 4))
        self.escala = tk.StringVar(value=ESCALAS[0][0])
        for nome, *_ in ESCALAS:
            ttk.Radiobutton(controles, text=nome, value=nome, variable=self.escala, takefocus=False,
                            command=self._escala_mudou).pack(side="left")

        self.situacao = tk.StringVar()
        self.rotulo_da_situacao = ttk.Label(barra, textvariable=self.situacao)
        barra.bind("<Configure>", self._arrumar_barra)

    def _arrumar_barra(self, _evento=None):
        """Distribui os grupos de controles em linhas, na ordem, conforme a largura.

        Um grupo que nao cabe desce inteiro para a linha seguinte. A situacao
        ocupa o resto da ultima linha, ou uma linha propria quando sobra pouco.
        """
        largura = self.barra.winfo_width()
        if largura <= 1:
            return
        linhas, x = [[]], 0
        for separador, conteudo in self._grupos:
            extra = 18 if linhas[-1] else 0         # separador e seu espacamento
            if linhas[-1] and x + extra + conteudo.winfo_reqwidth() > largura:
                linhas.append([])
                x, extra = 0, 0
            linhas[-1].append((separador, conteudo))
            x += extra + conteudo.winfo_reqwidth()
        ao_lado = largura - x >= self.fontes.px(300)
        arranjo = (tuple(len(linha) for linha in linhas), ao_lado)
        if arranjo == self._arranjo:
            return
        self._arranjo = arranjo

        for separador, conteudo in self._grupos:
            if separador is not None:
                separador.pack_forget()
            conteudo.pack_forget()
        self.rotulo_da_situacao.pack_forget()
        for quadro in self._linhas_da_barra:
            quadro.pack_forget()
        usadas = self._linhas_da_barra[:len(linhas) + (0 if ao_lado else 1)]
        for i, quadro in enumerate(usadas):
            quadro.pack(side="top", fill="x", pady=(4 if i else 0, 0))
        for quadro, linha in zip(usadas, linhas):
            for j, (separador, conteudo) in enumerate(linha):
                if j:
                    separador.pack(in_=quadro, side="left", fill="y", padx=8)
                conteudo.pack(in_=quadro, side="left")
        self.rotulo_da_situacao.configure(anchor="e" if ao_lado else "w")
        self.rotulo_da_situacao.pack(in_=usadas[-1], side="left", fill="x", expand=True,
                                     padx=(12, 0) if ao_lado else 0)

    def _lateral_com_rolagem(self, corpo):
        """Moldura da barra lateral, que rola na vertical quando o conteudo nao cabe.

        A largura acompanha o conteudo. A barra de rolagem so aparece quando
        falta altura, o que acontece nos tamanhos de texto maiores.
        """
        moldura = ttk.Frame(corpo)
        moldura.pack(side="left", fill="y", padx=(0, 8))
        tela = tk.Canvas(moldura, highlightthickness=0, borderwidth=0, width=10, height=10,
                         yscrollincrement=12, bg=FUNDO_JANELA)
        rolagem = ttk.Scrollbar(moldura, orient="vertical", command=tela.yview)
        tela.configure(yscrollcommand=rolagem.set)
        tela.pack(side="left", fill="y")
        lateral = ttk.Frame(tela)
        tela.create_window(0, 0, window=lateral, anchor="nw")

        def ajustar(_evento=None):
            largura, altura = lateral.winfo_reqwidth(), lateral.winfo_reqheight()
            tela.configure(width=largura, scrollregion=(0, 0, largura, altura))
            if altura > tela.winfo_height():
                rolagem.pack(side="left", fill="y", padx=(2, 0))
            else:
                rolagem.pack_forget()
                tela.yview_moveto(0)

        lateral.bind("<Configure>", ajustar)
        tela.bind("<Configure>", ajustar)
        self._tela_lateral, self._rolagem_lateral = tela, rolagem
        return lateral

    def _rolar_lateral(self, evento):
        """Roda do mouse sobre a barra lateral: rola a barra, e nunca troca o valor
        de uma lista ou do campo numerico sob o ponteiro."""
        if self._rolagem_lateral.winfo_ismapped():
            para_cima = evento.num == 4 or getattr(evento, "delta", 0) > 0
            self._tela_lateral.yview_scroll(-2 if para_cima else 2, "units")
        return "break"

    def _ligar_roda_da_lateral(self, widget):
        for sequencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequencia, self._rolar_lateral)
        for filho in widget.winfo_children():
            self._ligar_roda_da_lateral(filho)

    def _barra_lateral(self, lateral):
        # Qual das duas origens de R10 esta em uso, sempre a vista: um
        # topologia.json editado ao lado do executavel e a copia embutida
        # descrevem redes possivelmente diferentes.
        self.origem_da_topologia = ttk.Label(lateral, style="Fraco.TLabel", justify="left")
        self.origem_da_topologia.pack(fill="x", pady=(0, 6))
        self._quebraveis.append(self.origem_da_topologia)

        quadro = ttk.LabelFrame(lateral, text="Cenário", padding=(8, 4, 8, 6))
        quadro.pack(fill="x")
        quadro.columnconfigure(1, weight=1)
        self.escolha_do_cenario = ttk.Combobox(
            quadro, state="readonly", width=self.LARGURA_DO_CENARIO,
            values=[f"{c.codigo} · {c.nome}" for c in CENARIOS.values()])
        self.escolha_do_cenario.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.escolha_do_cenario.bind("<<ComboboxSelected>>", self._cenario_escolhido)
        self.marca_de_modificado = ttk.Label(quadro, style="Fraco.TLabel")
        self.marca_de_modificado.grid(row=1, column=0, columnspan=2, sticky="w")

        self.var = {nome: tk.StringVar() for nome in (
            "origem", "destino", "mensagem", "enlace_derrubado", "enlace_do_bit",
            "posicao_do_bit", "endereco_inalcancavel")}
        self.var.update({nome: tk.BooleanVar() for nome in ("derrubar", "inverter_bit", "inalcancavel")})

        ttk.Label(quadro, text="Origem").grid(row=2, column=0, sticky="w", pady=2)
        self.campo = {}
        self.campo["origem"] = ttk.Combobox(quadro, state="readonly", width=12,
                                            textvariable=self.var["origem"])
        self.campo["origem"].grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Label(quadro, text="Destino").grid(row=3, column=0, sticky="w", pady=2)
        self.campo["destino"] = ttk.Combobox(quadro, width=12, textvariable=self.var["destino"])
        self.campo["destino"].grid(row=3, column=1, sticky="ew", pady=2)
        ttk.Label(quadro, text="nome ou endereço lógico",
                  style="Fraco.TLabel").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(quadro, text="Mensagem").grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.campo["mensagem"] = ttk.Entry(quadro, textvariable=self.var["mensagem"])
        self.campo["mensagem"].grid(row=6, column=0, columnspan=2, sticky="ew")
        self.tamanho_da_mensagem = ttk.Label(quadro, style="Fraco.TLabel", justify="left")
        self.tamanho_da_mensagem.grid(row=7, column=0, columnspan=2, sticky="w")
        self.outros_fluxos = ttk.Label(quadro, style="Fraco.TLabel", justify="left")
        self.outros_fluxos.grid(row=8, column=0, columnspan=2, sticky="w")
        self.aviso = ttk.Label(quadro, style="Erro.TLabel", justify="left")
        self.aviso.grid(row=9, column=0, columnspan=2, sticky="w")
        self._quebraveis += [self.tamanho_da_mensagem, self.outros_fluxos, self.aviso]

        falhas = ttk.LabelFrame(lateral, text="Falhas", padding=(8, 4, 8, 6))
        falhas.pack(fill="x", pady=(8, 0))
        falhas.columnconfigure(1, weight=1)
        ttk.Checkbutton(falhas, text="Derrubar enlace", variable=self.var["derrubar"]).grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.campo["enlace_derrubado"] = ttk.Combobox(
            falhas, state="readonly", width=10, textvariable=self.var["enlace_derrubado"])
        self.campo["enlace_derrubado"].grid(row=1, column=1, sticky="w", padx=(20, 0), pady=(0, 4))
        ttk.Checkbutton(falhas, text="Injetar erro de bit", variable=self.var["inverter_bit"]).grid(
            row=2, column=0, columnspan=3, sticky="w")
        self.campo["enlace_do_bit"] = ttk.Combobox(
            falhas, state="readonly", width=10, textvariable=self.var["enlace_do_bit"])
        self.campo["enlace_do_bit"].grid(row=3, column=1, sticky="w", padx=(20, 0), pady=(0, 4))
        linha_do_bit = ttk.Frame(falhas)
        linha_do_bit.grid(row=3, column=2, sticky="e", pady=(0, 4))
        ttk.Label(linha_do_bit, text="bit").pack(side="left", padx=(6, 2))
        self.campo["bit"] = ttk.Spinbox(linha_do_bit, from_=0, to=9999, width=4,
                                        textvariable=self.var["posicao_do_bit"])
        self.campo["bit"].pack(side="left")
        ttk.Checkbutton(falhas, text="Destino inalcançável", variable=self.var["inalcancavel"]).grid(
            row=4, column=0, columnspan=3, sticky="w")
        self.campo["inalcancavel"] = ttk.Entry(falhas, width=14,
                                               textvariable=self.var["endereco_inalcancavel"])
        self.campo["inalcancavel"].grid(row=5, column=1, columnspan=2, sticky="w", padx=(20, 0))

        for variavel in self.var.values():
            variavel.trace_add("write", self._campo_alterado)

        self._painel_de_resumo(lateral)
        for rotulo in self._quebraveis:
            rotulo.configure(wraplength=self.LARGURA_DAS_NOTAS)
        self._ligar_roda_da_lateral(self._tela_lateral)

    def _painel_de_resumo(self, lateral):
        resumo = ttk.LabelFrame(lateral, text="Quadro resumo", padding=(8, 4, 8, 6))
        resumo.pack(fill="x", pady=(8, 0))
        resumo.columnconfigure(1, weight=1)
        self.valores_do_resumo = {}
        for i, (chave, texto) in enumerate((
            ("quadros", "Quadros transmitidos"),
            ("mensagem", "Tamanho da mensagem"),
            ("uteis", "Octetos úteis entregues"),
            ("transmitidos", "Octetos transmitidos"),
            ("eficiencia", "Eficiência"),
            ("sobrecarga", "Sobrecarga"),
        )):
            ttk.Label(resumo, text=texto).grid(row=i, column=0, sticky="w")
            valor = ttk.Label(resumo, text="—", anchor="e")
            valor.grid(row=i, column=1, sticky="e")
            self.valores_do_resumo[chave] = valor
        self.barra_do_resumo = tk.Canvas(resumo, width=10, height=12, highlightthickness=0,
                                         borderwidth=0, bg=FUNDO_BARRA_RESUMO)
        self.barra_do_resumo.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        self.entregas = ttk.Label(resumo, text="Aparece ao fim da execução.", style="Fraco.TLabel",
                                  justify="left")
        self.entregas.grid(row=7, column=0, columnspan=2, sticky="w")
        self._quebraveis.append(self.entregas)

    def _painel_de_canvas(self, pai, coluna, titulo):
        quadro = ttk.LabelFrame(pai, text=titulo, padding=2)
        quadro.grid(row=0, column=coluna, sticky="nsew", padx=(0, 4) if coluna == 0 else (4, 0),
                    pady=(0, 6))
        canvas = tk.Canvas(quadro, bg=FUNDO_PAINEL, highlightthickness=0, borderwidth=0,
                           width=10, height=10)
        canvas.pack(fill="both", expand=True)
        canvas.bind("<Configure>", lambda _e: self._agendar_desenho())
        canvas.bind("<Button-1>", lambda _e: canvas.focus_set())
        return canvas

    def _painel_de_enderecos(self, pai):
        quadro = ttk.LabelFrame(pai, text="Endereços", padding=4)
        quadro.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=(0, 6))

        self._caixas_de_endereco = []

        def caixa(titulo, cor, fundo):
            # Titulo e donos das interfaces em cima, o par embaixo. Sem largura
            # para os dois na mesma linha, os donos descem para baixo do par.
            moldura = tk.Frame(quadro, bg=fundo, highlightthickness=1, highlightbackground=cor,
                               highlightcolor=cor, borderwidth=0, padx=8, pady=2)
            moldura.pack(fill="x", pady=(0, 4))
            moldura.columnconfigure(0, weight=1)
            rotulo = tk.Label(moldura, text=titulo, bg=fundo, fg=cor, font=self.fontes["negrito"],
                              anchor="w", justify="left")
            rotulo.grid(row=0, column=0, sticky="w")
            detalhe = tk.Label(moldura, bg=fundo, fg=COR_TEXTO_FRACO, font=self.fontes["pequena"],
                               anchor="e", justify="left")
            par = tk.Label(moldura, bg=fundo, fg=cor, font=self.fontes["mono_grande"], anchor="w",
                           justify="left")
            par.grid(row=1, column=0, columnspan=2, sticky="w")
            self._caixas_de_endereco.append((moldura, rotulo, detalhe, par))
            moldura.bind("<Configure>", lambda _e: self._acomodar_enderecos())
            return par, detalhe

        self.par_logico, self.detalhe_logico = caixa(
            "LÓGICO · camada 3 · fixo de ponta a ponta", COR_LOGICO, FUNDO_LOGICO)
        self.par_fisico, self.detalhe_fisico = caixa(
            "FÍSICO · camada 2 · troca a cada salto", COR_FISICO, FUNDO_FISICO)

        self.nota_dos_saltos = ttk.Label(
            quadro, text="Saltos: um quadro novo, com outro par físico, em cada enlace",
            style="Fraco.TLabel")
        self.nota_dos_saltos.pack(fill="x")
        moldura = ttk.Frame(quadro)
        moldura.pack(fill="both", expand=True)
        # Todas as cores explicitas: sem elas o Tk usa as do sistema, e num tema
        # escuro o texto sai claro sobre o fundo claro definido aqui.
        self.lista_de_saltos = tk.Text(moldura, height=2, wrap="none", font=self.fontes["mono"],
                                       relief="flat", borderwidth=0, highlightthickness=0,
                                       state="disabled", cursor="arrow",
                                       bg=FUNDO_SALTOS, fg=COR_TEXTO,
                                       insertbackground=COR_TEXTO,
                                       selectbackground=SELECAO_FUNDO,
                                       selectforeground=SELECAO_TEXTO,
                                       inactiveselectbackground=SELECAO_FUNDO)
        rolagem = ttk.Scrollbar(moldura, orient="vertical", command=self.lista_de_saltos.yview)
        self.lista_de_saltos.configure(yscrollcommand=rolagem.set)
        rolagem.pack(side="right", fill="y")
        self.lista_de_saltos.pack(side="left", fill="both", expand=True)
        self.lista_de_saltos.tag_configure("atual", background=FUNDO_FISICO, foreground=COR_FISICO)

    def _acomodar_enderecos(self):
        """Quebra os textos das caixas de endereco na largura delas, em vez de corta-los."""
        largura = 0
        for moldura, rotulo, detalhe, par in self._caixas_de_endereco:
            largura = moldura.winfo_width() - 2 * 8 - 2
            if largura < 40:
                return
            texto = detalhe.cget("text")
            lado_a_lado = (self.fontes["negrito"].measure(rotulo.cget("text"))
                           + self.fontes["pequena"].measure(texto) + 12 <= largura)
            if not texto:
                detalhe.grid_remove()
            elif lado_a_lado:
                detalhe.grid(row=0, column=1, sticky="e")
            else:
                detalhe.grid(row=2, column=0, columnspan=2, sticky="w")
            for widget in (rotulo, detalhe, par):
                if str(widget.cget("wraplength")) != str(largura):
                    widget.configure(wraplength=largura)
        if largura and str(self.nota_dos_saltos.cget("wraplength")) != str(largura):
            self.nota_dos_saltos.configure(wraplength=largura)

    def _painel_de_registro(self, pai):
        # Sem moldura com titulo: a linha do botao ja faz esse papel e poupa
        # altura para as linhas do registro na janela minima.
        quadro = ttk.Frame(pai, padding=(0, 2, 0, 0))
        quadro.pack(fill="both", expand=True)
        topo = ttk.Frame(quadro)
        topo.pack(fill="x", pady=(0, 3))
        # O botao entra primeiro: sem largura, quem perde espaco e a nota do formato.
        ttk.Button(topo, text="Salvar em arquivo…", command=self.salvar_registro,
                   takefocus=False).pack(side="right")
        ttk.Label(topo, text="Registro de eventos", font=self.fontes["negrito"]).pack(side="left")
        ttk.Label(topo, text="formato oficial: NNN | DISP | LN | AÇÃO | descrição  TAM B",
                  style="Fraco.TLabel").pack(side="left", padx=(10, 0))

        moldura = ttk.Frame(quadro)
        moldura.pack(fill="both", expand=True)
        moldura.rowconfigure(0, weight=1)
        moldura.columnconfigure(0, weight=1)
        self.registro = tk.Text(moldura, height=4, wrap="none", font=self.fontes["mono"],
                                state="disabled", relief="flat", borderwidth=0,
                                highlightthickness=0,
                                bg=FUNDO_REGISTRO, fg=COR_TEXTO,
                                insertbackground=COR_TEXTO,
                                selectbackground=SELECAO_FUNDO,
                                selectforeground=SELECAO_TEXTO,
                                inactiveselectbackground=SELECAO_FUNDO)
        vertical = ttk.Scrollbar(moldura, orient="vertical", command=self.registro.yview)
        horizontal = ttk.Scrollbar(moldura, orient="horizontal", command=self.registro.xview)
        self.registro.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.registro.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        # As etiquetas so mexem no fundo ou so na cor do texto: o que elas nao
        # definem vem do fg e do bg do proprio widget, ambos fixados acima.
        self.registro.tag_configure("descarte", foreground=COR_DESCARTE)
        self.registro.tag_configure("atual", background=DESTAQUE_LINHA_ATUAL)
        # O token Ln com o fundo da camada, a mesma cor da pilha e do bloco.
        # Criadas depois de "atual", essas etiquetas prevalecem na linha atual;
        # a selecao volta para cima de todas.
        for camada, cor in COR_DA_CAMADA.items():
            self.registro.tag_configure(f"camada{camada}", background=cor)
        self.registro.tag_raise("sel")

    def _nivel(self):
        """A linha de ESCALAS do tamanho de texto escolhido."""
        return next(e for e in ESCALAS if e[0] == self.escala.get())

    def _posicionar_divisorias(self):
        altura = self.paineis.winfo_height()
        if altura < 100:
            self.raiz.after(60, self._posicionar_divisorias)
            return
        primeira, segunda = self._nivel()[3]
        primeira, segunda = altura * primeira, altura * segunda
        # Em janela pequena com texto grande, as proporcoes nao bastam. Na
        # ordem: as pilhas (e com elas o mapa) com todas as camadas legiveis,
        # o registro com quatro linhas, a unidade com os blocos e uma faixa;
        # a unidade fica com o que sobrar se nao houver para os tres.
        def moldura(widget, conteudo):
            return widget.winfo_height() - conteudo.winfo_height()

        pilhas = self.pilhas.canvas
        topo = moldura(pilhas.master, pilhas) + self.pilhas.altura_minima() + 8
        registro = (moldura(self.registro.master.master, self.registro)
                    + 4 * self.fontes.linha("mono") + 8)
        unidade = moldura(self.blocos.canvas.master, self.blocos.canvas) + self.blocos.altura_minima() + 8
        primeira = max(primeira, topo)
        segunda = min(segunda, altura - registro)
        if segunda - primeira < unidade:
            primeira = max(topo, segunda - unidade)
        segunda = max(segunda, primeira + 1)
        self.paineis.sashpos(0, int(primeira))
        self.paineis.sashpos(1, int(segunda))

    def _escala_mudou(self):
        """Aplica o tamanho de texto escolhido a janela inteira."""
        _, fator, fator_da_lateral, _ = self._nivel()
        self.fontes.aplicar(fator)
        # A barra lateral cresce pelo seu proprio fator, e nao pelo do texto:
        # a lista de cenarios e medida em caracteres, que ja cresceram.
        self.escolha_do_cenario.configure(
            width=round(self.LARGURA_DO_CENARIO * fator_da_lateral / fator))
        for rotulo in self._quebraveis:
            rotulo.configure(wraplength=round(self.LARGURA_DAS_NOTAS * fator_da_lateral))
        self.raiz.after(30, self._arrumar_barra)
        self.raiz.after(60, self._posicionar_divisorias)
        self.raiz.after(60, self._atualizar_resumo)
        self._agendar_desenho()

    # ------------------------------------------------------------------
    # Topologia
    # ------------------------------------------------------------------

    def _abrir_topologia(self, primeira_vez=False):
        try:
            topologia = self.carregar_topologia()
        except Exception as erro:
            if primeira_vez:
                self.topologia, self.erro_de_topologia = None, str(erro)
                self._habilitar_configuracao(False)
                self._descartar_execucao()
                self.situacao.set("Sem topologia: veja o erro no mapa.")
                self._agendar_desenho()
            else:
                messagebox.showerror("Topologia", f"{erro}\n\nA topologia anterior continua em uso.",
                                     parent=self.raiz)
            return

        self.topologia, self.erro_de_topologia = topologia, None
        self._mostrar_origem_da_topologia(topologia)
        self._enlaces = rotulos_de_enlace(topologia)
        self.campo["origem"]["values"] = topologia.computadores
        self.campo["destino"]["values"] = topologia.computadores
        self.campo["enlace_derrubado"]["values"] = list(self._enlaces)
        self.campo["enlace_do_bit"]["values"] = list(self._enlaces)
        self.raiz.title(f"Simulador do modelo OSI — {topologia.nome}")
        self._habilitar_configuracao(True)
        self._aplicar_cenario_base(getattr(self, "_codigo_base", next(iter(CENARIOS))))

    def _mostrar_origem_da_topologia(self, topologia):
        """Diz de onde a topologia veio: o arquivo ao lado ou a copia embutida."""
        origem = getattr(topologia, "origem", None)
        if origem is None:
            self.origem_da_topologia.configure(text="")
            return
        if origem.embutida:
            texto = (f"⚠ Topologia: cópia embutida no executável. "
                     f"Não há topologia.json em {pasta_do_programa()}.")
            estilo = "Erro.TLabel"
        else:
            texto = f"Topologia: topologia.json ao lado do programa ({origem.caminho})"
            estilo = "Fraco.TLabel"
        self.origem_da_topologia.configure(text=texto, style=estilo)

    def regerar_registros(self):
        """Regera a pasta registros/ com os sete cenarios, no formato oficial."""
        if self.topologia is None:
            messagebox.showinfo("Sem topologia",
                                "Carregue uma topologia antes de gerar os registros.",
                                parent=self.raiz)
            return
        try:
            caminhos = gerar_registros_dos_cenarios(self.topologia)
        except OSError as erro:
            messagebox.showerror("Registros não gerados",
                                 f"Não foi possível gravar a pasta "
                                 f"{PASTA_DOS_REGISTROS}:\n{erro}", parent=self.raiz)
            return
        lista = "\n".join(f"{codigo}: {eventos} eventos" for codigo, _, eventos in caminhos)
        messagebox.showinfo(
            "Registros gerados",
            f"{len(caminhos)} registros gravados em:\n"
            f"{pasta_do_programa()}/{PASTA_DOS_REGISTROS}\n\n{lista}",
            parent=self.raiz)

    def recarregar_topologia(self):
        self.pausar()
        self._abrir_topologia(primeira_vez=self.topologia is None)

    def _habilitar_configuracao(self, habilitar):
        self.escolha_do_cenario.configure(state="readonly" if habilitar else "disabled")
        for chave, campo in self.campo.items():
            if not habilitar:
                campo.configure(state="disabled")
        if habilitar:
            self._sincronizar_campos_de_falha()

    # ------------------------------------------------------------------
    # Configuracao
    # ------------------------------------------------------------------

    def _rotulo_do_par(self, par):
        for rotulo, extremos in self._enlaces.items():
            if par and set(extremos) == set(par):
                return rotulo
        roteadores = self.topologia.roteadores
        entre_roteadores = [r for r, (a, b) in self._enlaces.items()
                            if a in roteadores and b in roteadores]
        return (entre_roteadores or list(self._enlaces) or [""])[0]

    def _cenario_escolhido(self, _evento=None):
        codigo = self.escolha_do_cenario.get().split(" · ")[0]
        self._aplicar_cenario_base(codigo)

    def _aplicar_cenario_base(self, codigo):
        """Preenche a barra lateral com um dos sete cenarios da tabela."""
        cenario = CENARIOS[codigo]
        fluxo, falhas = cenario.fluxos[0], cenario.falhas
        self._codigo_base = codigo
        self._preenchendo = True
        try:
            self.escolha_do_cenario.set(f"{cenario.codigo} · {cenario.nome}")
            self.var["origem"].set(fluxo.origem)
            self.var["destino"].set(fluxo.destino)
            self.var["mensagem"].set(fluxo.mensagem)
            self.var["derrubar"].set(bool(falhas.enlace_derrubado))
            self.var["enlace_derrubado"].set(self._rotulo_do_par(falhas.enlace_derrubado))
            self.var["inverter_bit"].set(bool(falhas.bit_invertido))
            self.var["enlace_do_bit"].set(self._rotulo_do_par(falhas.bit_invertido))
            self.var["posicao_do_bit"].set(str(falhas.posicao_do_bit))
            self.var["inalcancavel"].set(bool(falhas.destino_inalcancavel))
            self.var["endereco_inalcancavel"].set(falhas.destino_inalcancavel or "10.0.9.10")
        finally:
            self._preenchendo = False
        outros = [f"Fluxo {i}, fixo: {f.origem} → {f.destino}, portas {f.portas[0]} → "
                  f"{f.portas[1]}, {len(f.mensagem.encode('utf-8'))} B"
                  for i, f in enumerate(cenario.fluxos[1:], start=2)]
        self.outros_fluxos.configure(text="\n".join(outros))
        if outros:
            self.outros_fluxos.grid()
        else:
            self.outros_fluxos.grid_remove()
        self._configuracao_mudou()

    def _campo_alterado(self, *_args):
        if not self._preenchendo:
            self._configuracao_mudou()

    def _sincronizar_campos_de_falha(self):
        for chave, campos in (("derrubar", ("enlace_derrubado",)),
                              ("inverter_bit", ("enlace_do_bit", "bit")),
                              ("inalcancavel", ("inalcancavel",))):
            ligado = self.var[chave].get()
            for campo in campos:
                combo = isinstance(self.campo[campo], ttk.Combobox)
                estado = ("readonly" if combo else "normal") if ligado else "disabled"
                self.campo[campo].configure(state=estado)
        self.campo["origem"].configure(state="readonly")
        self.campo["destino"].configure(state="normal")
        self.campo["mensagem"].configure(state="normal")

    def _escolhas(self):
        v = self.var
        return Escolhas(
            base=self._codigo_base,
            origem=v["origem"].get(),
            destino=v["destino"].get(),
            mensagem=v["mensagem"].get(),
            derrubar=v["derrubar"].get(),
            enlace_derrubado=self._enlaces.get(v["enlace_derrubado"].get()),
            inverter_bit=v["inverter_bit"].get(),
            enlace_do_bit=self._enlaces.get(v["enlace_do_bit"].get()),
            posicao_do_bit=v["posicao_do_bit"].get(),
            inalcancavel=v["inalcancavel"].get(),
            endereco_inalcancavel=v["endereco_inalcancavel"].get(),
        )

    def _configuracao_mudou(self):
        """Qualquer mudanca na barra lateral recomeca a execucao do zero."""
        if self.topologia is None:
            return
        self.pausar()
        self._sincronizar_campos_de_falha()
        self._mostrar_tamanho_da_mensagem()
        self._marcar_campo(None)
        try:
            self.cenario, self.modificado = montar_cenario(self.topologia, self._escolhas())
            self.erro_de_configuracao = None
            self._preparar()
        except ConfiguracaoInvalida as erro:
            self._recusar(erro)
        except Exception as erro:
            # O nucleo recusou a configuracao: a janela continua aberta.
            self._recusar(ConfiguracaoInvalida(
                f"O simulador não aceitou esta configuração: {type(erro).__name__}: {erro}",
                None))

    def _recusar(self, erro):
        self.erro_de_configuracao = erro
        self._descartar_execucao()
        self._marcar_campo(erro.campo)
        self.aviso.configure(text=str(erro))
        self.aviso.grid()
        self.marca_de_modificado.configure(text="")
        self.situacao.set("Configuração inválida: corrija o campo em vermelho.")
        self._atualizar_botoes()
        self._agendar_desenho()

    def _marcar_campo(self, campo):
        for chave, widget in self.campo.items():
            if isinstance(widget, ttk.Combobox):
                widget.configure(style="Invalido.TCombobox" if chave == campo else "TCombobox")
            elif isinstance(widget, ttk.Entry) and not isinstance(widget, ttk.Spinbox):
                widget.configure(style="Invalido.TEntry" if chave == campo else "TEntry")
        if campo is None:
            self.aviso.configure(text="")
            self.aviso.grid_remove()

    def _mostrar_tamanho_da_mensagem(self):
        octetos = len(self.var["mensagem"].get().encode("utf-8"))
        limiar = self.topologia.convencoes.get("limiar_segmentacao_octetos")
        texto = f"{octetos} octetos"
        if limiar is not None and octetos > limiar:
            texto += f" · acima de {limiar}: a camada 4 segmenta"
        self.tamanho_da_mensagem.configure(text=texto)

    def _descartar_execucao(self):
        self.sim = None
        self.andamento = None
        self.dispositivos, self.papeis, self.total_de_passos = [], {}, 0
        self._limpar_registro()
        self._atualizar_resumo()

    def _preparar(self):
        """Cria a Simulacao do cenario configurado e desenha tudo em cinza."""
        self._limpar_registro()
        self.dispositivos, self.total_de_passos = dispositivos_do_caminho(self.topologia, self.cenario)
        self.sim = Simulacao(self.topologia, self.cenario)
        self.andamento = Andamento(self.sim.topologia)

        origens = {f.origem for f in self.cenario.fluxos}
        destinos = set() if self.cenario.falhas.destino_inalcancavel else \
            {f.destino for f in self.cenario.fluxos}
        self.papeis = {}
        for nome in self.dispositivos:
            if nome in self.topologia.roteadores:
                self.papeis[nome] = "roteador"
            else:
                papel = [p for p, grupo in (("origem", origens), ("destino", destinos)) if nome in grupo]
                self.papeis[nome] = "/".join(papel)

        self.marca_de_modificado.configure(
            text="modificado: difere da tabela de validação" if self.modificado
            else "como na tabela de validação")
        self._atualizar_resumo()
        self._atualizar_situacao()
        self._atualizar_botoes()
        self._agendar_desenho()

    # ------------------------------------------------------------------
    # Controle de execucao (V5)
    # ------------------------------------------------------------------

    def _pode_executar(self):
        if self.topologia is None:
            messagebox.showerror("Sem topologia", self.erro_de_topologia or "Nenhuma topologia carregada.",
                                 parent=self.raiz)
            return False
        if self.erro_de_configuracao is not None:
            self.pausar()
            messagebox.showerror("Configuração inválida", str(self.erro_de_configuracao),
                                 parent=self.raiz)
            campo = self.campo.get(self.erro_de_configuracao.campo)
            if campo is not None:
                campo.focus_set()
            return False
        return self.sim is not None

    def passo(self):
        if not self._pode_executar() or self.sim.terminou:
            return False
        self._avancar()
        self._agendar_desenho()
        if self.sim.terminou:
            self._ao_terminar()
        self._atualizar_situacao()
        self._atualizar_botoes()
        return True

    def _avancar(self):
        evento = self.sim.passo()
        if evento is None:
            return None
        self.andamento.registrar(evento, self.sim.unidade)
        self._acrescentar_ao_registro(evento)
        return evento

    def executar(self):
        if not self._pode_executar() or self.sim.terminou or self.rodando:
            return
        self.rodando = True
        self._atualizar_botoes()
        self._tique()

    def _tique(self):
        self._agendado = None
        if not self.rodando:
            return
        if not self.passo() or self.sim is None or self.sim.terminou:
            self.pausar()
            return
        intervalo = dict(VELOCIDADES)[self.velocidade.get()]
        self._agendado = self.raiz.after(intervalo, self._tique)

    def pausar(self):
        self.rodando = False
        if self._agendado is not None:
            self.raiz.after_cancel(self._agendado)
            self._agendado = None
        self._atualizar_botoes()

    def ate_o_fim(self):
        self.pausar()
        if not self._pode_executar() or self.sim.terminou:
            return
        while self._avancar() is not None:
            pass
        self._ao_terminar()
        self._atualizar_situacao()
        self._atualizar_botoes()
        self._agendar_desenho()

    def reiniciar(self):
        self.pausar()
        if self.topologia is None or self.erro_de_configuracao is not None:
            self._pode_executar()
            return
        self._preparar()

    def _ao_terminar(self):
        self._atualizar_resumo()

    def _atualizar_botoes(self):
        fim = self.sim is not None and self.sim.terminou
        estados = {
            "passo": not fim and not self.rodando,
            "executar": not fim and not self.rodando,
            "pausar": self.rodando,
            "fim": not fim,
            "reiniciar": self.topologia is not None,
        }
        for chave, ligado in estados.items():
            self.botoes[chave].state(["!disabled"] if ligado else ["disabled"])

    def _atualizar_situacao(self):
        if self.sim is None:
            return
        rotulo = f"{self.cenario.codigo} {self.cenario.nome}"
        feitos = len(self.sim.eventos)
        if self.sim.terminou:
            entregas = len(self.sim.entregas)
            fim = f"{entregas} entrega(s)" if entregas else "nenhuma entrega"
            self.situacao.set(f"{rotulo} · concluído em {feitos} passos · {fim}")
        elif feitos == 0:
            self.situacao.set(f"{rotulo} · pronto · {self.total_de_passos} passos")
        else:
            e = self.andamento.evento
            self.situacao.set(f"{rotulo} · passo {feitos:03d} de {self.total_de_passos:03d} · "
                              f"{e.dispositivo} L{e.camada} {e.acao}")

    def _tecla_espaco(self, evento):
        if self._foco_em_campo(evento):
            return None
        if self.rodando:
            self.pausar()
        else:
            self.executar()
        return "break"

    def _tecla_direita(self, evento):
        if self._foco_em_campo(evento):
            return None
        self.pausar()
        self.passo()
        return "break"

    @staticmethod
    def _foco_em_campo(evento):
        """Espaco e seta pertencem ao campo de texto ou botao que estiver em foco."""
        if not hasattr(evento.widget, "winfo_class"):
            return True     # a lista aberta de um Combobox chega como texto
        return evento.widget.winfo_class() in (
            "TEntry", "TCombobox", "TSpinbox", "Entry", "Text", "Spinbox",
            "TCheckbutton", "TRadiobutton", "TButton", "Button")

    # ------------------------------------------------------------------
    # Desenho
    # ------------------------------------------------------------------

    def _agendar_desenho(self):
        if self._desenho_agendado is None:
            self._desenho_agendado = self.raiz.after_idle(self._redesenhar)

    def _redesenhar(self):
        self._desenho_agendado = None
        falhas = self.cenario.falhas if (self.cenario and self.sim) else None
        self.mapa.desenhar(self.topologia, falhas, self.andamento, self.erro_de_topologia)
        if self.erro_de_configuracao is not None:
            aviso = "Configuração inválida: corrija o campo em vermelho na barra lateral."
        elif self.topologia is None:
            aviso = "Sem topologia carregada."
        else:
            aviso = (f"Pronto: {self.total_de_passos} passos. Em cinza, os dispositivos que a "
                     f"unidade ainda não alcançou. Use Passo (→) ou Executar (espaço).")
        self.pilhas.desenhar(self.dispositivos, self.papeis,
                             self.topologia.roteadores if self.topologia else [],
                             self.andamento, self.modo.get(), aviso)
        evento = self.andamento.evento if self.andamento else None
        self.blocos.desenhar(self.andamento.unidade if self.andamento else None, evento)
        self._atualizar_enderecos()

    def _atualizar_enderecos(self):
        andamento = self.andamento
        unidade = andamento.unidade if andamento else None
        topologia = self.topologia

        def nome_da_interface(interface):
            return f"{interface.dispositivo} {interface.nome}" if interface else "?"

        def ausente(rotulo, detalhe, explicacao):
            rotulo.configure(text=f"— {explicacao}", fg=COR_TEXTO_FRACO, font=self.fontes["pequena"])
            detalhe.configure(text="")

        logicos = unidade.logicos if unidade else (None, None)
        if logicos[0]:
            self.par_logico.configure(text=f"{logicos[0]}  →  {logicos[1]}", fg=COR_LOGICO,
                                      font=self.fontes["mono_grande"])
            donos = [topologia.interface_por_logico(e) for e in logicos]
            destino = nome_da_interface(donos[1]) if donos[1] else "fora da topologia"
            self.detalhe_logico.configure(text=f"{nome_da_interface(donos[0])} → {destino}")
        else:
            ausente(self.par_logico, self.detalhe_logico,
                    "a camada 3 da origem insere o par, que segue igual até o destino")

        fisicos = unidade.fisicos if unidade else (None, None)
        if fisicos[0]:
            de, para = andamento.interfaces_de(fisicos)
            self.par_fisico.configure(text=f"{fisicos[0]} → {fisicos[1]}", fg=COR_FISICO,
                                      font=self.fontes["mono_grande"])
            self.detalhe_fisico.configure(
                text=f"{unidade.numero_quadro}: {nome_da_interface(de)} → {nome_da_interface(para)}")
        elif andamento and andamento.saltos:
            ausente(self.par_fisico, self.detalhe_fisico,
                    "sem quadro agora: o anterior foi desfeito e o próximo ainda não existe")
        else:
            ausente(self.par_fisico, self.detalhe_fisico,
                    "o quadro só existe a partir da camada 2 da origem")

        lista = self.lista_de_saltos
        lista.configure(state="normal")
        lista.delete("1.0", "end")
        atual = unidade.numero_quadro if unidade is not None and fisicos[0] else None
        for i, (quadro, de, para, (fisico_de, fisico_para)) in enumerate(andamento.saltos if andamento else ()):
            linha = (f"{quadro:<4}{nome_da_interface(de):<9}→ {nome_da_interface(para):<9}"
                     f"{fisico_de} → {fisico_para}")
            lista.insert("end", ("\n" if i else "") + linha, ("atual",) if quadro == atual else ())
        lista.configure(state="disabled")
        if atual:
            intervalo = lista.tag_ranges("atual")
            if intervalo:
                lista.see(intervalo[0])
        else:
            lista.see("end")
        self._acomodar_enderecos()

    def _atualizar_resumo(self):
        valores = self.valores_do_resumo
        barra = self.barra_do_resumo
        barra.delete("all")
        if self.sim is None or not self.sim.terminou:
            for rotulo in valores.values():
                rotulo.configure(text="—", foreground=COR_TEXTO)
            self.entregas.configure(text="Aparece ao fim da execução.", style="Fraco.TLabel")
            return

        resumo = self.sim.resumo()
        valores["quadros"].configure(text=str(resumo.quadros))
        valores["mensagem"].configure(text=f"{resumo.octetos_da_mensagem} B")
        valores["uteis"].configure(text=f"{resumo.octetos_uteis} B")
        valores["transmitidos"].configure(text=f"{resumo.octetos_transmitidos} B")
        # Sem entrega a eficiencia e zero, e nao "indefinida": e o valor que a
        # tabela de validacao traz para E5 e E6 (eta = 0). O vermelho apenas
        # chama atencao; o numero exibido e o mesmo que o quadro resumo calcula.
        sem_entrega = resumo.octetos_uteis == 0
        valores["eficiencia"].configure(
            text=porcentagem(resumo.eficiencia),
            foreground=COR_DESCARTE if sem_entrega else COR_TEXTO)
        valores["sobrecarga"].configure(text=porcentagem(resumo.sobrecarga))

        barra.update_idletasks()
        largura = barra.winfo_width()
        util = largura * resumo.eficiencia
        barra.create_rectangle(0, 0, util, 12, fill=COR_ATIVA[4], outline="")
        barra.create_rectangle(util, 0, largura, 12, fill="#cfd8dc", outline="")

        if self.sim.entregas:
            texto = "\n".join(f"Entregue a '{e.processo}' em {e.dispositivo}"
                              for e in self.sim.entregas)
            self.entregas.configure(text=texto, style="TLabel")
        else:
            self.entregas.configure(text="Nenhuma mensagem chegou ao destino.", style="Erro.TLabel")

    # ------------------------------------------------------------------
    # Registro (V6)
    # ------------------------------------------------------------------

    def _limpar_registro(self):
        self.registro.configure(state="normal")
        self.registro.delete("1.0", "end")
        self.registro.configure(state="disabled")

    def _acrescentar_ao_registro(self, evento):
        texto = self.registro
        texto.configure(state="normal")
        texto.tag_remove("atual", "1.0", "end")
        if texto.index("end-1c") != "1.0":
            texto.insert("end", "\n")
        etiquetas = ["atual"] + (["descarte"] if evento.acao == "DESCARTA" else [])
        linha, inicio = formatar(evento), texto.index("end-1c")
        texto.insert("end", linha, tuple(etiquetas))
        # So a cor muda: o texto inserido e a linha oficial, e copiar ou salvar
        # o registro devolve exatamente o que formatar() produz.
        token = f"L{evento.camada}"
        coluna = linha.find(f" | {token} | ")
        if coluna >= 0:
            comeco = f"{inicio} + {coluna + 3} chars"
            texto.tag_add(f"camada{evento.camada}", comeco, f"{comeco} + {len(token)} chars")
        texto.configure(state="disabled")
        # Com o texto grande a linha passa da largura: o inicio dela (passo,
        # dispositivo, camada, acao) e o que fica a vista, e nao o fim.
        texto.see("end")
        texto.xview_moveto(0)

    def salvar_registro(self):
        if self.sim is None or not self.sim.eventos:
            messagebox.showinfo("Registro vazio", "Execute ao menos um passo antes de salvar o registro.",
                                parent=self.raiz)
            return
        sufixo = "_modificado" if self.modificado else ""
        caminho = filedialog.asksaveasfilename(
            parent=self.raiz, title="Salvar registro de eventos",
            initialdir=pasta_do_programa(),
            initialfile=f"registro_{self.cenario.codigo}{sufixo}.txt",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos os arquivos", "*")],
        )
        if not caminho:
            return
        try:
            self.sim.registro.salvar_em_arquivo(caminho)
        except OSError as erro:
            messagebox.showerror("Registro não salvo", f"Não foi possível gravar {caminho}:\n{erro}",
                                 parent=self.raiz)
            return
        parcial = "" if self.sim.terminou else " (execução ainda incompleta)"
        messagebox.showinfo("Registro salvo",
                            f"{len(self.sim.eventos)} eventos gravados{parcial} em:\n{caminho}",
                            parent=self.raiz)

    # ------------------------------------------------------------------
    # Erros e encerramento
    # ------------------------------------------------------------------

    def _erro_inesperado(self, tipo, valor, rastro):
        """Qualquer erro num tratador de evento pausa a execucao; a janela fica aberta."""
        traceback.print_exception(tipo, valor, rastro, file=sys.stderr)
        self.rodando = False
        if self._agendado is not None:
            self.raiz.after_cancel(self._agendado)
            self._agendado = None
        try:
            self._atualizar_botoes()
        except Exception:
            pass
        messagebox.showerror(
            "Erro inesperado",
            f"{tipo.__name__}: {valor}\n\nA execução foi pausada e a janela continua aberta. "
            f"Use Reiniciar ou escolha outro cenário.",
            parent=self.raiz)

    def fechar(self):
        self.pausar()
        self.raiz.destroy()


def executar(carregar_topologia):
    """Abre a janela e so retorna quando o usuario a fecha.

    carregar_topologia e chamado sem argumentos e deve devolver uma Topologia
    ou lancar uma excecao cuja mensagem ja sirva ao usuario.
    """
    try:
        raiz = tk.Tk()
    except tk.TclError as erro:
        raise JanelaIndisponivel(str(erro)) from None
    Janela(raiz, carregar_topologia)
    raiz.mainloop()
