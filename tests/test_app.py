"""A ponte entre motor e tela (F6).

`app.py` é o único módulo que importa os dois lados, e é pequeno de propósito:
executar um caso, traduzir `Intervencao` em `EventoExterno`, montar o
cabeçalho. Este arquivo cobra as três coisas — e mais uma que custou um
defeito para aparecer.

O defeito: a primeira versão importava `tkinter` no topo do módulo. Numa
máquina sem tkinter (a que roda esta suíte, por exemplo), `import app`
estourava com `ModuleNotFoundError`, e um erro de topologia — que deveria sair
como mensagem legível, pela seção 5.7 — virava rastreamento de pilha sobre um
módulo que nem era o assunto. `ImportarAppNaoExigeTkinter` é a regressão.

Executar:  python -m unittest tests.test_app
"""

import os
import subprocess
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

import app
from evento import Intervencao
from rede import carregar_topologia
from simulador import executar_caso

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")


def _registro(eventos):
    return [evento.linha() for evento in eventos]


class ImportarAppNaoExigeTkinter(unittest.TestCase):
    """A regra que `visual.py` já seguia e que `app.py` passou a seguir.

    Verificada em subprocesso com o tkinter **proibido**, e não só com ele
    ausente: na máquina de quem tiver tkinter instalado, um `import` no topo
    voltaria a passar despercebido."""

    def test_o_modulo_carrega_com_tkinter_proibido(self):
        programa = (
            "import sys\n"
            "class Bloqueio:\n"
            "    def find_module(self, nome, caminho=None):\n"
            "        if nome.split('.')[0] == 'tkinter':\n"
            "            raise ImportError('tkinter proibido')\n"
            "        return None\n"
            "sys.meta_path.insert(0, Bloqueio())\n"
            "import app\n"
            "print('ok')\n"
        )
        resultado = subprocess.run(
            [sys.executable, "-c", programa],
            capture_output=True,
            text=True,
            cwd=_RAIZ,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("ok", resultado.stdout)

    def test_erro_de_topologia_sai_como_mensagem(self):
        self.assertEqual(app.principal(["--topologia", "nao-existe.json"]), 1)

    def test_caso_inexistente_sai_como_mensagem(self):
        self.assertEqual(app.principal(["--caso", "C99"]), 1)


class ATraducaoParaOVocabularioDoMotor(unittest.TestCase):
    def test_todos_os_campos_atravessam(self):
        externo = app._externo(
            Intervencao(tipo="erro_bit", enlace="E-R4-R3", quadro="Q3", bit=100)
        )
        self.assertEqual(externo.tipo, "erro_bit")
        self.assertEqual(externo.enlace, "E-R4-R3")
        self.assertEqual(externo.quadro, "Q3")
        self.assertEqual(externo.bit, 100)

    def test_a_queda_de_enlace_deixa_quadro_e_bit_nulos(self):
        externo = app._externo(
            Intervencao(tipo="enlace_fora", enlace="E-R1-R4")
        )
        self.assertIsNone(externo.quadro)
        self.assertIsNone(externo.bit)


class OExecutorEntregaEventosECabecalho(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topologia = carregar_topologia(TOPOLOGIA)
        # `staticmethod` porque uma função guardada num atributo de classe
        # vira método ligado, e `self` entraria como o nome do caso.
        cls.executar = staticmethod(app.montar_executor(cls.topologia))

    def test_devolve_a_dupla(self):
        eventos, cabecalho = self.executar("C2")
        self.assertTrue(eventos)
        self.assertIn("# Caso: C2", cabecalho)

    def test_sem_intervencao_e_o_caso_declarado(self):
        eventos, _ = self.executar("C2")
        self.assertEqual(
            _registro(eventos), _registro(executar_caso(self.topologia, "C2"))
        )

    def test_a_queda_de_enlace_reproduz_o_c4(self):
        eventos, _ = self.executar(
            "C2", (Intervencao(tipo="enlace_fora", enlace="E-R1-R4"),)
        )
        self.assertEqual(
            _registro(eventos), _registro(executar_caso(self.topologia, "C4"))
        )

    def test_o_erro_de_bit_reproduz_o_c6(self):
        eventos, _ = self.executar(
            "C2",
            (
                Intervencao(
                    tipo="erro_bit", enlace="E-R4-R3", quadro="Q3", bit=100
                ),
            ),
        )
        self.assertEqual(
            _registro(eventos), _registro(executar_caso(self.topologia, "C6"))
        )

    def test_o_cabecalho_denuncia_o_caso_derivado(self):
        # O arquivo salvo não pode dizer "C2" para um C2 que não é o do
        # arquivo (seção 8.3).
        _, cabecalho = self.executar(
            "C2", (Intervencao(tipo="enlace_fora", enlace="E-R1-R4"),)
        )
        self.assertIn("C2*", cabecalho)
        self.assertIn("E-R1-R4", cabecalho)

    def test_duas_intervencoes_se_acumulam_num_caso_so(self):
        _, cabecalho = self.executar(
            "C2",
            (
                Intervencao(tipo="enlace_fora", enlace="E-R1-R4"),
                Intervencao(
                    tipo="erro_bit", enlace="E-R4-R3", quadro="Q1", bit=100
                ),
            ),
        )
        self.assertIn("C2*", cabecalho)
        self.assertNotIn("C2**", cabecalho)

    def test_reexecutar_nao_contamina_a_execucao_seguinte(self):
        # O caso derivado é uma cópia; o declarado continua intacto para a
        # próxima chamada.
        self.executar("C2", (Intervencao(tipo="enlace_fora", enlace="E-R1-R4"),))
        eventos, cabecalho = self.executar("C2")
        self.assertIn("# Caso: C2 ", cabecalho + " ")
        self.assertEqual(
            _registro(eventos), _registro(executar_caso(self.topologia, "C2"))
        )


# --------------------------------------------------------------------------
# O erro precisa chegar ao usuário mesmo sem console (F7, issues #57 e #58)
# --------------------------------------------------------------------------


class ErroChegaAoUsuarioSemConsole(unittest.TestCase):
    """O empacotamento usa `--windowed`, e isso apaga a saída de erro.

    Enquanto o programa roda pelo terminal, `print(..., file=sys.stderr)`
    basta. No `.exe` com `console=False` não há terminal: uma topologia
    ausente faria o programa simplesmente não abrir, em silêncio, e o item 5
    do checklist da seção 14.3 — "produz mensagem clara, não rastreamento de
    pilha" — estaria reprovado sem que nada acusasse.

    Por isso `principal` recebe `avisar`, e o teste passa um coletor."""

    def test_topologia_ausente_avisa_o_usuario(self):
        avisos = []
        self.assertEqual(
            app.principal(["--topologia", "nao-existe.json"], avisar=avisos.append),
            1,
        )
        self.assertEqual(len(avisos), 1)
        self.assertIn("nao-existe.json", avisos[0])

    def test_o_aviso_explica_em_vez_de_mostrar_pilha(self):
        avisos = []
        app.principal(["--topologia", "nao-existe.json"], avisar=avisos.append)
        self.assertNotIn("Traceback", avisos[0])
        self.assertIn("topologia", avisos[0].lower())

    def test_json_invalido_avisa_com_a_linha_do_erro(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "quebrado.json")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write('{ "versao": "1.0"')
            avisos = []
            self.assertEqual(
                app.principal(["--topologia", caminho], avisar=avisos.append), 1
            )
            self.assertIn("linha", avisos[0])

    def test_caso_inexistente_avisa_quais_existem(self):
        avisos = []
        app.principal(["--caso", "C99"], avisar=avisos.append)
        self.assertIn("C99", avisos[0])
        self.assertIn("C1", avisos[0])

    def test_sem_avisar_o_erro_continua_saindo_no_stderr(self):
        # O modo terminal não regride: quem roda `python app.py` continua
        # vendo a mensagem onde sempre a viu.
        import contextlib
        import io

        capturado = io.StringIO()
        with contextlib.redirect_stderr(capturado):
            app.principal(["--topologia", "nao-existe.json"])
        self.assertIn("nao-existe.json", capturado.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
