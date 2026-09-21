"""Trocar a topologia sem tocar em código (F7, issue #60).

A promessa central do projeto, e o teste que a cobra de ponta a ponta: um
`topologia.json` diferente ao lado do executável carrega, desenha e executa,
sem uma linha de código alterada. A seção 5.5 diz "os casos vão no arquivo"; é
aqui que essa frase vira verificação.

O que torna o teste forte não é o caminho feliz — é a **ausência**. Cada
afirmação de que algo do arquivo novo aparece vem acompanhada da afirmação de
que nada do arquivo de referência sobrou: nem `H1`, nem `R1`, nem `C2`. Um
seletor que listasse C1–C7 numa topologia que não os declara, ou um mapa que
desenhasse nove nós onde há quatro, seriam exatamente o sintoma de código
sabendo demais sobre a rede de referência — e é o tipo de coisa que só aparece
quando se troca o arquivo.

Este arquivo é de **aceitação**, não de TDD: verifica comportamento que as
fases anteriores já deviam ter produzido, e o seu valor é justamente passar
sem que nada precise mudar.

Executar:  python -m unittest tests.test_troca_de_topologia
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

import app
from rede import carregar_topologia
from simulador import cabecalho, casos_executaveis, executar_caso
from visual import Janela, Navegador, carregar_planta

from tests.tela import TelaDeMentira

REFERENCIA = os.path.join(_RAIZ, "topologia.json")
ALTERNATIVA = os.path.join(_RAIZ, "exemplos", "topologia-alternativa.json")

# Nomes que só existem na topologia de referência. Nenhum deles pode aparecer
# quando o arquivo carregado é outro.
DA_REFERENCIA = ("H1", "H2", "H4", "H5", "R1", "R2", "R3", "R4")


def telas():
    return {
        "mapa": TelaDeMentira(790, 340),
        "pilhas": TelaDeMentira(490, 340),
        "pdu": TelaDeMentira(1220, 92),
        "enderecos": TelaDeMentira(1220, 76),
    }


def janela_da(caminho: str):
    """Monta a janela inteira sobre uma topologia qualquer, como o `app` faria."""
    topologia = carregar_topologia(caminho)
    executar = app.montar_executor(topologia)
    casos = casos_executaveis(topologia)
    eventos, cabeca = executar(casos[0])
    janela = Janela(
        planta=carregar_planta(caminho),
        navegador=Navegador(eventos),
        caso=casos[0],
        executar=executar,
        cabecalho=cabeca,
        casos=casos,
        enlaces=tuple(enlace.id for enlace in topologia.enlaces),
        velocidades={"lenta": 1200, "media": 500, "rapida": 150},
        agendar=lambda atraso, funcao: None,
    )
    quadros = telas()
    janela.ligar_telas(**quadros)
    janela.redesenhar()
    return janela, quadros


class OArquivoAlternativoExisteEEValido(unittest.TestCase):
    def test_o_exemplo_esta_versionado_no_repositorio(self):
        # Sem um arquivo pronto para trocar, a promessa é só uma afirmação.
        self.assertTrue(
            os.path.exists(ALTERNATIVA),
            "o exemplo de topologia alternativa precisa vir junto do programa",
        )

    def test_carrega_sem_erro(self):
        topologia = carregar_topologia(ALTERNATIVA)
        self.assertTrue(topologia.nome)
        self.assertTrue(topologia.dispositivos)

    def test_e_mesmo_uma_rede_diferente(self):
        alternativa = carregar_topologia(ALTERNATIVA)
        referencia = carregar_topologia(REFERENCIA)
        self.assertNotEqual(alternativa.nome, referencia.nome)
        self.assertNotEqual(
            {d.nome for d in alternativa.dispositivos},
            {d.nome for d in referencia.dispositivos},
        )


class OsCasosVemDoArquivo(unittest.TestCase):
    """Seção 5.5. O seletor da issue #56 é alimentado pelo arquivo carregado."""

    def test_o_seletor_lista_os_casos_do_arquivo_novo(self):
        janela, _ = janela_da(ALTERNATIVA)
        self.assertEqual(janela.casos, ("X1",))

    def test_nenhum_caso_da_referencia_sobra(self):
        janela, _ = janela_da(ALTERNATIVA)
        for caso in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            self.assertNotIn(caso, janela.casos)

    def test_o_caso_do_arquivo_novo_roda_do_inicio_ao_fim(self):
        topologia = carregar_topologia(ALTERNATIVA)
        eventos = executar_caso(topologia, "X1")
        acoes = [evento.acao for evento in eventos]
        self.assertEqual(acoes[0], "GERA")
        self.assertIn("ENTREGA", acoes)
        self.assertEqual(acoes[-1], "METRICAS")

    def test_o_registro_do_arquivo_novo_e_coerente(self):
        topologia = carregar_topologia(ALTERNATIVA)
        eventos = executar_caso(topologia, "X1")
        linhas = " ".join(evento.linha() for evento in eventos)
        for nome in DA_REFERENCIA:
            self.assertNotIn(f"| {nome} |", linhas)
        self.assertIn("| PC-A |", linhas)

    def test_o_cabecalho_nomeia_a_topologia_nova(self):
        topologia = carregar_topologia(ALTERNATIVA)
        texto = cabecalho(topologia, topologia.caso("X1"))
        self.assertIn(topologia.nome, texto)
        self.assertIn("X1", texto)


class OMapaDesenhaARedeDoArquivo(unittest.TestCase):
    """As coordenadas são lidas, não inventadas — é o que o campo `posicao`
    da seção 5.4 existe para permitir."""

    def test_desenha_os_dispositivos_do_arquivo_novo(self):
        _, quadros = janela_da(ALTERNATIVA)
        textos = quadros["mapa"].textos()
        for nome in ("PC-A", "PC-B", "RT-1", "RT-2"):
            self.assertIn(nome, textos)

    def test_nao_desenha_nenhum_dispositivo_da_referencia(self):
        _, quadros = janela_da(ALTERNATIVA)
        textos = quadros["mapa"].textos()
        for nome in DA_REFERENCIA:
            self.assertNotIn(nome, textos)

    def test_a_planta_respeita_as_coordenadas_declaradas(self):
        planta = carregar_planta(ALTERNATIVA)
        self.assertEqual(
            {no.nome: (no.posicao.x, no.posicao.y) for no in planta.nos},
            {
                "PC-A": (100, 200),
                "PC-B": (700, 200),
                "RT-1": (300, 200),
                "RT-2": (500, 200),
            },
        )

    def test_as_quatro_regioes_desenham_com_a_topologia_nova(self):
        _, quadros = janela_da(ALTERNATIVA)
        for nome, tela in quadros.items():
            with self.subTest(regiao=nome):
                self.assertTrue(tela.itens, f"a região {nome} não desenhou nada")

    def test_as_pilhas_distinguem_computador_de_roteador_na_rede_nova(self):
        # A restrição R1 não é sobre H1 e R1: é sobre a estrutura. Numa
        # topologia qualquer, computador tem sete caixas e roteador tem três.
        janela, quadros = janela_da(ALTERNATIVA)
        janela.navegador.ultimo()
        janela.redesenhar()
        caixas = lambda nome: [
            item
            for item in quadros["pilhas"].com(f"pilha:{nome}")
            if item.tipo == "rect"
        ]
        self.assertEqual(len(caixas("PC-A")), 7)
        self.assertEqual(len(caixas("RT-1")), 3)


class NadaExigeAlterarCodigo(unittest.TestCase):
    """O critério de aceitação da issue, dito como teste."""

    def test_a_mesma_janela_serve_as_duas_topologias(self):
        # O mesmo código, dois arquivos, dois resultados diferentes e
        # corretos. Se algo precisasse de `if topologia == ...`, este teste
        # é onde apareceria.
        primeira, _ = janela_da(REFERENCIA)
        segunda, _ = janela_da(ALTERNATIVA)
        self.assertNotEqual(primeira.casos, segunda.casos)
        self.assertNotEqual(primeira.enlaces, segunda.enlaces)
        self.assertNotEqual(primeira.navegador.total, segunda.navegador.total)

    def test_os_controles_funcionam_na_topologia_nova(self):
        janela, _ = janela_da(ALTERNATIVA)
        janela.proximo()
        janela.proximo()
        self.assertEqual(janela.navegador.indice, 2)
        janela.anterior()
        self.assertEqual(janela.navegador.indice, 1)

    def test_derrubar_enlace_funciona_na_topologia_nova(self):
        janela, _ = janela_da(ALTERNATIVA)
        janela.derrubar_enlace("E-RT1-RT2")
        linhas = " ".join(e.linha() for e in janela.navegador.eventos)
        self.assertIn("ENLACE_FORA", linhas)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
