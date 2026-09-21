"""V6 — o registro de eventos na tela (issue #54).

A regra dura da seção 8.2 é que nenhum outro ponto do programa formata
registro, e é ela que este arquivo cobra: cada linha da tela sai de
`Evento.linha()`, sem exceção. É o que faz T-V6 ser verificável — o arquivo
salvo e a tela têm a mesma origem, então compará-los é comparar duas cadeias,
e não dois formatadores que poderiam divergir em silêncio.

O `TextoDeMentira` faz aqui o que a `TelaDeMentira` faz nas regiões
desenhadas: guarda o que o registro mandou escrever, sem precisar de widget
nem de display.

Executar:  python -m unittest tests.test_registro
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import cabecalho, executar_caso, principais
from visual import RegistroNaTela

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")


class TextoDeMentira:
    """O mínimo de `tkinter.Text` que o registro usa."""

    def __init__(self):
        self.linhas: list[str] = []
        self.marcas: list[tuple[str, str]] = []
        self.visivel: str | None = None
        self.estado = "normal"

    def configure(self, **opcoes):
        self.estado = opcoes.get("state", self.estado)

    config = configure

    def delete(self, inicio, fim=None):
        self.linhas = []

    def insert(self, onde, texto, *etiquetas):
        self.linhas.extend(texto.splitlines())

    def tag_add(self, etiqueta, inicio, fim=None):
        self.marcas.append((etiqueta, inicio))

    def tag_remove(self, etiqueta, inicio, fim=None):
        self.marcas = [marca for marca in self.marcas if marca[0] != etiqueta]

    def tag_configure(self, etiqueta, **opcoes):
        pass

    def see(self, indice):
        self.visivel = indice


def eventos_de(caso="C2"):
    return executar_caso(carregar_topologia(TOPOLOGIA), caso)


def cabecalho_de(caso="C2"):
    topologia = carregar_topologia(TOPOLOGIA)
    return cabecalho(topologia, topologia.caso(caso))


# --------------------------------------------------------------------------
# A formatação é única (seção 8.2)
# --------------------------------------------------------------------------


class CadaLinhaSaiDeEventoLinha(unittest.TestCase):
    def test_a_tela_mostra_exatamente_o_que_evento_linha_produz(self):
        eventos = eventos_de("C2")
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos, indice=0)
        self.assertEqual(alvo.linhas, [e.linha() for e in principais(eventos)])

    def test_a_coluna_de_octetos_do_anexo_b_chega_intacta_a_tela(self):
        # Se alguém remontar a linha à mão aqui, o alinhamento diverge do
        # Anexo B e o T-FMT não pega, porque o T-FMT olha o modo textual.
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos_de("C2"), indice=0)
        self.assertIn(
            "008 | H1 | L1 | TRANSMITE | 736 bits no enlace H1–R1",
            " ".join(alvo.linhas),
        )

    def test_a_tela_e_reconstruida_do_zero_a_cada_desenho(self):
        eventos = eventos_de("C2")
        alvo = TextoDeMentira()
        registro = RegistroNaTela(alvo)
        registro.desenhar(eventos, indice=0)
        quantas = len(alvo.linhas)
        registro.desenhar(eventos, indice=5)
        self.assertEqual(len(alvo.linhas), quantas)

    def test_o_widget_fica_somente_leitura(self):
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos_de("C2"), indice=0)
        self.assertEqual(alvo.estado, "disabled")


# --------------------------------------------------------------------------
# Secundários ocultos por padrão (seção 7.5)
# --------------------------------------------------------------------------


class SecundariosOcultosPorPadrao(unittest.TestCase):
    def test_o_ignora_da_difusao_nao_aparece(self):
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos_de("C2"), indice=0)
        self.assertFalse(any("IGNORA" in linha for linha in alvo.linhas))

    def test_a_caixa_de_descartes_os_revela(self):
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(
            eventos_de("C2"), indice=0, mostrar_secundarios=True
        )
        self.assertTrue(any("IGNORA" in linha for linha in alvo.linhas))

    def test_eles_nunca_saem_da_lista_interna(self):
        # A caixa filtra a exibição; o motor produziu os eventos e eles
        # continuam lá.
        self.assertTrue(any(evento.secundario for evento in eventos_de("C2")))


# --------------------------------------------------------------------------
# O realce acompanha o passo corrente
# --------------------------------------------------------------------------


class RealceAcompanhaOPassoCorrente(unittest.TestCase):
    def test_a_linha_do_passo_corrente_e_realcada(self):
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos_de("C2"), indice=7)
        self.assertTrue(alvo.marcas, "o passo corrente precisa de realce")

    def test_a_area_rola_para_manter_a_linha_visivel(self):
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos_de("C2"), indice=20)
        self.assertIsNotNone(alvo.visivel)

    def test_ha_um_realce_so(self):
        alvo = TextoDeMentira()
        registro = RegistroNaTela(alvo)
        registro.desenhar(eventos_de("C2"), indice=3)
        registro.desenhar(eventos_de("C2"), indice=9)
        self.assertEqual(len(alvo.marcas), 1)

    def test_o_realce_anda_com_o_indice(self):
        eventos = eventos_de("C2")
        alvo = TextoDeMentira()
        registro = RegistroNaTela(alvo)
        registro.desenhar(eventos, indice=3)
        primeira = list(alvo.marcas)
        registro.desenhar(eventos, indice=9)
        self.assertNotEqual(primeira, alvo.marcas)

    def test_a_linha_realcada_e_a_do_evento_corrente(self):
        eventos = eventos_de("C2")
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos, indice=7)
        numero = int(alvo.marcas[0][1].split(".")[0])
        self.assertEqual(alvo.linhas[numero - 1], eventos[7].linha())

    def test_um_evento_secundario_oculto_realca_a_linha_do_seu_passo(self):
        # Passo e índice divergem quando há secundários. Deixar a tela sem
        # realce nenhum pareceria que a navegação travou.
        eventos = eventos_de("C2")
        indice = next(i for i, e in enumerate(eventos) if e.secundario)
        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(eventos, indice=indice)
        self.assertTrue(alvo.marcas)
        numero = int(alvo.marcas[0][1].split(".")[0])
        self.assertEqual(alvo.linhas[numero - 1], eventos[indice - 1].linha())


# --------------------------------------------------------------------------
# T-V6 — o arquivo salvo é idêntico ao que está na tela
# --------------------------------------------------------------------------


class TV6ArquivoIdenticoATela(unittest.TestCase):
    """O critério de aceitação da issue, e a razão de a formatação ser única.

    O arquivo tem o cabeçalho da seção 8.3 e, depois dele, exatamente as
    linhas que estão na tela — nem uma a mais, nem uma a menos, na mesma
    ordem."""

    def _comparar(self, mostrar_secundarios):
        eventos = eventos_de("C2")
        cabeca = cabecalho_de("C2")
        alvo = TextoDeMentira()
        registro = RegistroNaTela(alvo)
        registro.desenhar(
            eventos, indice=0, mostrar_secundarios=mostrar_secundarios
        )
        gravado = registro.texto(
            eventos, cabeca, mostrar_secundarios=mostrar_secundarios
        )
        corpo = gravado.splitlines()[len(cabeca.splitlines()) :]
        self.assertEqual(corpo, alvo.linhas)

    def test_o_corpo_do_arquivo_e_as_linhas_da_tela(self):
        self._comparar(mostrar_secundarios=False)

    def test_a_caixa_de_descartes_vale_para_os_dois(self):
        self._comparar(mostrar_secundarios=True)

    def test_o_arquivo_traz_o_cabecalho_da_secao_8_3(self):
        gravado = RegistroNaTela(TextoDeMentira()).texto(
            eventos_de("C2"), cabecalho_de("C2")
        )
        self.assertIn("# Caso: C2", gravado)
        self.assertIn("# Topologia:", gravado)

    def test_o_arquivo_termina_em_quebra_de_linha(self):
        gravado = RegistroNaTela(TextoDeMentira()).texto(
            eventos_de("C2"), cabecalho_de("C2")
        )
        self.assertTrue(gravado.endswith("\n"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
