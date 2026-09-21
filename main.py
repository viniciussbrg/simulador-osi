"""Ponto de entrada do simulador.

Abre sem argumento algum, como acontece num duplo clique (R10), e mostra a
janela grafica de simulador/visual.py. Com o argumento --texto, a escolha
do cenario, a execucao, o registro e o quadro resumo ficam num menu no
terminal; o mesmo menu assume quando o tkinter nao consegue abrir a janela.
A topologia vem de topologia.json, procurado ao lado do programa por
recursos.py e, so na falta dele, na copia embutida no executavel (R10);
trocar esse arquivo troca a rede sem gerar outro executavel. Os dois modos
dizem qual das duas origens esta em uso.

Nenhum dos modos fecha sozinho. No terminal, ao sair pelo menu, diante de um
erro ou de um Ctrl+C, o programa sempre termina pedindo Enter.
"""

import json
import os
import sys
import traceback

from simulador.recursos import caminho_de, pasta_do_programa, pasta_embutida
from simulador.rede import Topologia
from simulador.simulador import (
    CENARIOS, PASTA_DOS_REGISTROS, Simulacao, gerar_registros_dos_cenarios,
)

ARQUIVO_DA_TOPOLOGIA = "topologia.json"


class TopologiaInvalida(Exception):
    """topologia.json ausente ou ilegivel; a mensagem ja vem pronta para o usuario."""


# ----------------------------------------------------------------------
# Topologia
# ----------------------------------------------------------------------

def carregar_topologia():
    caminho = caminho_de(ARQUIVO_DA_TOPOLOGIA)
    try:
        return Topologia.carregar(ARQUIVO_DA_TOPOLOGIA)
    except FileNotFoundError:
        # So chega aqui quando nem o arquivo ao lado do programa nem a copia
        # embutida existem: sem empacotamento, a copia embutida nao existe.
        embutida = pasta_embutida()
        reserva = (f"A copia embutida tambem nao foi encontrada em: {embutida}\n"
                   if embutida else
                   "Esta execucao vem do codigo-fonte e nao tem copia embutida.\n")
        raise TopologiaInvalida(
            f"Arquivo nao encontrado: {ARQUIVO_DA_TOPOLOGIA}\n"
            f"Procurado em: {pasta_do_programa()}\n"
            f"{reserva}"
            f"Coloque o {ARQUIVO_DA_TOPOLOGIA} na mesma pasta do programa e abra-o de novo."
        ) from None
    except json.JSONDecodeError as erro:
        raise TopologiaInvalida(
            f"{ARQUIVO_DA_TOPOLOGIA} nao e um JSON valido.\n"
            f"Arquivo: {caminho}\n"
            f"Linha {erro.lineno}, coluna {erro.colno}: {erro.msg}"
        ) from None
    except KeyError as erro:
        raise TopologiaInvalida(
            f"{ARQUIVO_DA_TOPOLOGIA} esta incompleto: falta o campo {erro}.\n"
            f"Arquivo: {caminho}"
        ) from None
    except (TypeError, ValueError, AttributeError, OSError) as erro:
        raise TopologiaInvalida(
            f"Nao foi possivel ler {ARQUIVO_DA_TOPOLOGIA}: {erro}\n"
            f"Arquivo: {caminho}"
        ) from None


# ----------------------------------------------------------------------
# Apresentacao
# ----------------------------------------------------------------------

def perguntar(texto):
    """input() que devolve None quando a entrada acaba (EOF), em vez de lancar."""
    try:
        return input(texto).strip()
    except EOFError:
        return None


def titulo(texto):
    print()
    print(texto)
    print("-" * len(texto))


def porcentagem(fracao):
    return f"{fracao * 100:.1f}%".replace(".", ",")


def imprimir_resumo(sim):
    resumo = sim.resumo()
    cenario = sim.cenario
    titulo(f"Quadro resumo - {cenario.codigo} {cenario.nome}")
    print(f"  Quadros transmitidos ......... {resumo.quadros}")
    print(f"  Tamanho da mensagem .......... {resumo.octetos_da_mensagem} B")
    print(f"  Octetos uteis entregues ...... {resumo.octetos_uteis} B")
    print(f"  Octetos transmitidos ......... {resumo.octetos_transmitidos} B")
    # Sem entrega, a eficiencia e zero, e nao "indefinida": e o que a tabela
    # de validacao traz para E5 e E6 (eta = 0).
    print(f"  Eficiencia ................... {porcentagem(resumo.eficiencia)}")
    print(f"  Sobrecarga ................... {porcentagem(resumo.sobrecarga)}")
    if resumo.octetos_uteis == 0:
        print("  (nenhuma mensagem chegou ao destino: nenhum octeto util entregue)")


def imprimir_enlaces(sim):
    """Os enlaces percorridos, na ordem em que os quadros foram postos no meio."""
    if not sim.transmissoes:
        print("  Nenhum quadro foi transmitido.")
        return
    print("  Enlaces percorridos:")
    for numero, t in enumerate(sim.transmissoes, 1):
        print(f"    {numero:>2}. {t.de} -> {t.para}  (quadro {t.quadro.numero_quadro})")


# ----------------------------------------------------------------------
# Acoes do menu
# ----------------------------------------------------------------------

class Menu:
    def __init__(self, topologia):
        self.topologia = topologia
        self.codigo = "E1"
        self.sim = None

    @property
    def cenario(self):
        return CENARIOS[self.codigo]

    def cabecalho(self):
        origem = self.topologia.origem
        print()
        print("=" * 60)
        print(" Simulador do modelo OSI")
        print("=" * 60)
        print(f" Topologia: {self.topologia.nome}")
        # Qual das duas origens de R10 esta em uso, sempre a vista.
        print(f" Origem:    {origem.descricao if origem else 'desconhecida'}")
        print(f" Arquivo:   {origem.caminho if origem else caminho_de(ARQUIVO_DA_TOPOLOGIA)}")
        if origem and origem.embutida:
            print(f"            (nao ha {ARQUIVO_DA_TOPOLOGIA} em {pasta_do_programa()})")
        situacao = "executado" if self.sim else "ainda nao executado"
        print(f" Cenario:   {self.codigo} {self.cenario.nome} ({situacao})")
        print()
        print("  1. Escolher cenario")
        print("  2. Executar cenario")
        print("  3. Ver registro completo")
        print("  4. Ver quadro resumo")
        print("  5. Salvar registro em arquivo")
        print(f"  6. Recarregar {ARQUIVO_DA_TOPOLOGIA}")
        print(f"  7. Regerar {PASTA_DOS_REGISTROS}/ com os sete cenarios")
        print("  0. Sair")

    def escolher_cenario(self):
        titulo("Cenarios")
        for codigo, cenario in CENARIOS.items():
            print(f"  {codigo[1:]}. {codigo} {cenario.nome}")
        resposta = perguntar("Numero do cenario (Enter mantem o atual): ")
        if not resposta:
            return
        codigo = resposta.upper()
        if not codigo.startswith("E"):
            codigo = "E" + codigo
        if codigo not in CENARIOS:
            print(f"  Opcao invalida: {resposta!r}. Cenario mantido: {self.codigo}.")
            return
        if codigo != self.codigo:
            self.codigo = codigo
            self.sim = None
        print(f"  Cenario selecionado: {self.codigo} {self.cenario.nome}")

    def executar(self):
        self.sim = Simulacao(self.topologia, self.cenario)
        self.sim.executar()
        titulo(f"{self.codigo} {self.cenario.nome}: {len(self.sim.eventos)} eventos")
        imprimir_enlaces(self.sim)
        for entrega in self.sim.entregas:
            print(f"  Entregue a '{entrega.processo}' em {entrega.dispositivo}: "
                  f"{entrega.mensagem!r}")
        if not self.sim.entregas:
            print("  Nenhuma mensagem chegou ao destino.")
        imprimir_resumo(self.sim)

    def exigir_execucao(self):
        if self.sim is None:
            print(f"  Execute o cenario {self.codigo} primeiro (opcao 2).")
        return self.sim is not None

    def ver_registro(self):
        if self.exigir_execucao():
            titulo(f"Registro de eventos - {self.codigo} {self.cenario.nome}")
            print(self.sim.registro)

    def ver_resumo(self):
        if self.exigir_execucao():
            imprimir_resumo(self.sim)

    def salvar_registro(self):
        if not self.exigir_execucao():
            return
        # Ao lado do programa, e nunca na pasta temporaria do empacotador (R10).
        caminho = caminho_de(f"registro_{self.codigo}.txt")
        self.sim.registro.salvar_em_arquivo(caminho)
        print(f"  Registro salvo em: {caminho}")

    def regerar_registros(self):
        caminhos = gerar_registros_dos_cenarios(self.topologia)
        titulo(f"Registros regerados em {caminho_de(PASTA_DOS_REGISTROS)}")
        for codigo, caminho, eventos in caminhos:
            print(f"  {codigo}: {eventos:>3} eventos -> {os.path.basename(caminho)}")

    def recarregar(self):
        try:
            self.topologia = carregar_topologia()
        except TopologiaInvalida as erro:
            print("  " + str(erro).replace("\n", "\n  "))
            print("  A topologia anterior continua em uso.")
            return
        self.sim = None
        origem = self.topologia.origem
        print(f"  Topologia recarregada: {self.topologia.nome}")
        print(f"  Origem: {origem.descricao if origem else 'desconhecida'}")

    def rodar(self):
        acoes = {
            "1": self.escolher_cenario,
            "2": self.executar,
            "3": self.ver_registro,
            "4": self.ver_resumo,
            "5": self.salvar_registro,
            "6": self.recarregar,
            "7": self.regerar_registros,
        }
        while True:
            self.cabecalho()
            opcao = perguntar("Opcao: ")
            if opcao is None or opcao == "0":
                return
            acao = acoes.get(opcao)
            if acao is None:
                print(f"  Opcao invalida: {opcao!r}. Digite um numero de 0 a 7.")
                continue
            # Um erro numa acao volta ao menu em vez de encerrar o programa.
            try:
                acao()
            except Exception as erro:
                print(f"\n  Erro: {type(erro).__name__}: {erro}")
                print("  A operacao foi interrompida; o menu continua disponivel.")
            if perguntar("\nEnter para voltar ao menu...") is None:
                return


# ----------------------------------------------------------------------
# Entrada
# ----------------------------------------------------------------------

def esperar_enter():
    try:
        input("\nPressione Enter para fechar...")
    except (EOFError, KeyboardInterrupt):
        pass


def abrir_janela():
    """Abre a interface grafica; devolve o motivo quando ela nao pode ser aberta."""
    try:
        from simulador.visual import JanelaIndisponivel, executar
    except ImportError as erro:
        return f"o tkinter nao esta disponivel ({erro})"
    try:
        # A interface recebe a funcao de carga, e nao a importa de main.py.
        executar(carregar_topologia)
    except JanelaIndisponivel as erro:
        return str(erro)
    except Exception as erro:
        traceback.print_exc(file=sys.stdout)
        return f"erro inesperado ao montar a janela: {type(erro).__name__}: {erro}"
    return None


def main():
    # Um nome com acento no topologia.json nao pode derrubar um console
    # que nao saiba exibi-lo.
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    if "--texto" not in sys.argv[1:]:
        motivo = abrir_janela()
        if motivo is None:
            return
        print(f"Nao foi possivel abrir a janela: {motivo}")
        print("O simulador continua em modo texto.")

    try:
        topologia = carregar_topologia()
        Menu(topologia).rodar()
        print("\nSimulador encerrado.")
    except TopologiaInvalida as erro:
        print("\nNao foi possivel abrir a topologia.")
        print(erro)
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuario.")
    except Exception as erro:
        print("\nErro inesperado; o simulador foi encerrado.")
        print(f"{type(erro).__name__}: {erro}")
        traceback.print_exc(file=sys.stdout)
    finally:
        esperar_enter()


if __name__ == "__main__":
    main()
