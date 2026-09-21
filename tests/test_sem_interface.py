"""Issue #32 — a simulação roda inteira **antes** de qualquer desenho.

Esta é a pré-condição arquitetural de F5/F6: `visual.py` nunca pede "mais um
passo" a uma camada, ele recebe a lista de eventos pronta e navega nela por
índice (seções 4.2 e 13.1 da proposta técnica, "de baixo para cima").

Uma garantia dessas não se demonstra lendo o código — demonstra-se **negando
o tkinter** e mostrando que o registro completo sai assim mesmo. É o que os
testes de subprocesso abaixo fazem: instalam um localizador de módulos que
estoura se alguém importar tkinter, e só então executam C2 de ponta a ponta.

Executar:  python -m unittest tests.test_sem_interface
"""

import os
import subprocess
import sys
import tempfile
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from evento import Evento
from rede import carregar_topologia
from simulador import executar_caso, principais

# Prólogo injetado nos subprocessos: qualquer `import tkinter` (ou submódulo)
# vira ImportError antes de chegar ao interpretador gráfico. Se o motor
# dependesse de tela, o processo morreria aqui.
_SEM_TKINTER = """
import sys

class _SemTkinter:
    def find_module(self, nome, caminho=None):
        return self.find_spec(nome, caminho)

    def find_spec(self, nome, caminho=None, alvo=None):
        if nome == "tkinter" or nome.startswith("tkinter."):
            raise ImportError("tkinter proibido: o motor textual nao pode depender de tela")
        return None

sys.meta_path.insert(0, _SemTkinter())
"""


def _sem_tkinter(corpo: str) -> subprocess.CompletedProcess:
    """Roda `corpo` num Python novo, com tkinter proibido e a raiz no path."""
    return subprocess.run(
        [sys.executable, "-c", _SEM_TKINTER + corpo],
        cwd=_RAIZ,
        capture_output=True,
        text=True,
    )


class ListaCompleta(unittest.TestCase):
    """A execução devolve uma lista **finalizada**, nunca um gerador."""

    def test_executar_caso_devolve_tupla_imutavel(self):
        eventos = executar_caso(carregar_topologia(), "C2")
        self.assertIsInstance(eventos, tuple)
        self.assertTrue(all(isinstance(e, Evento) for e in eventos))

    def test_registro_de_c2_ja_esta_completo_ao_retornar(self):
        """Do primeiro `GERA` ao `METRICAS` que fecha a execução, sem ninguém
        pedir mais."""
        eventos = principais(executar_caso(carregar_topologia(), "C2"))
        self.assertEqual(eventos[0].acao, "GERA")
        self.assertEqual(eventos[-1].acao, "METRICAS")
        self.assertEqual(eventos[-2].acao, "ENTREGA")
        self.assertEqual(eventos[-2].dispositivo, "H4")

    def test_passos_sao_contiguos_de_1_a_n(self):
        """Navegar por índice só funciona se o passo N estiver no índice N-1."""
        eventos = principais(executar_caso(carregar_topologia(), "C2"))
        self.assertEqual(
            [e.passo for e in eventos], list(range(1, len(eventos) + 1))
        )

    def test_duas_execucoes_do_mesmo_caso_dao_o_mesmo_registro(self):
        """Determinismo: a lista é fruto da topologia e do caso, não de estado
        acumulado entre execuções (contadores de quadro e de sessão zerados)."""
        topologia = carregar_topologia()
        primeira = [e.linha() for e in executar_caso(topologia, "C2")]
        segunda = [e.linha() for e in executar_caso(topologia, "C2")]
        self.assertEqual(primeira, segunda)


class SemTela(unittest.TestCase):
    """Nada do núcleo depende de tkinter — nem por importação, nem em execução."""

    def test_importar_o_nucleo_nao_puxa_tkinter(self):
        resultado = _sem_tkinter(
            "import camadas, dispositivos, evento, pdu, rede, simulador\n"
            "print('ok')\n"
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("ok", resultado.stdout)

    def test_c2_roda_inteiro_com_tkinter_proibido(self):
        resultado = _sem_tkinter(
            "from rede import carregar_topologia\n"
            "from simulador import executar_caso, principais\n"
            "eventos = principais(executar_caso(carregar_topologia(), 'C2'))\n"
            "print(len(eventos))\n"
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        esperado = len(principais(executar_caso(carregar_topologia(), "C2")))
        self.assertEqual(resultado.stdout.strip(), str(esperado))

    def test_ponto_de_entrada_salva_o_registro_sem_abrir_janela(self):
        """Critério de aceitação da issue #32, verificado pelo comando da #33:
        `--caso C2 --log saida.txt` produz o registro inteiro em arquivo com o
        tkinter proibido."""
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "saida.txt")
            resultado = _sem_tkinter(
                "import sys\n"
                "import simulador\n"
                f"sys.argv = ['simulador.py', '--caso', 'C2', '--log', {destino!r}]\n"
                "sys.exit(simulador.principal())\n"
            )
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            with open(destino, encoding="utf-8") as arquivo:
                linhas = arquivo.read().splitlines()

        registro = [linha for linha in linhas if not linha.startswith("#")]
        esperado = principais(executar_caso(carregar_topologia(), "C2"))
        self.assertEqual(registro, [e.linha() for e in esperado])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
