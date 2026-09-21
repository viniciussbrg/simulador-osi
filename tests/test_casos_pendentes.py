"""Caso que depende de intervenção externa ainda não implementada (F4).

C4 derruba um enlace e C6 inverte um bit de um quadro: os dois declaram o
gatilho em `eventos_externos`, no `topologia.json`, e o motor de F3 ainda não
os aplica. Executá-los assim produz um registro **plausível e errado** — C4
sai roteando pelo enlace que deveria estar fora, C6 sai sem `CORROMPE` e sem
descarte —, indistinguível de C2 para quem lê a saída.

Um resultado errado que se parece com o certo é pior do que uma falha: quem
usa o modo textual como ferramenta de trabalho (seção 13.2) não tem como
notar. Então o motor recusa o caso enquanto a intervenção não existir, com a
mesma disciplina da carga de topologia (seção 5.7): mensagem legível, nenhum
rastreamento de pilha, código de saída diferente de zero.

Quando F4 implementar `ENLACE_FORA` e `CORROMPE`, o tipo correspondente entra
em `TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS` e estes testes passam a cobrir apenas
o que ainda não existir — nenhum deles precisa ser apagado.

Executar:  python -m unittest tests.test_casos_pendentes
"""

import os
import subprocess
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import (
    TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS,
    CasoNaoSuportado,
    casos_executaveis,
    executar_caso,
)


def simulador(*argumentos: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "simulador.py", *argumentos],
        cwd=_RAIZ,
        capture_output=True,
        text=True,
    )


class RecusaDoMotor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()

    def test_c4_recusado_enquanto_enlace_fora_nao_existir(self):
        if "enlace_fora" in TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS:
            self.skipTest("F4 já aplica enlace_fora")
        with self.assertRaises(CasoNaoSuportado) as erro:
            executar_caso(self.topo, "C4")
        mensagem = str(erro.exception)
        self.assertIn("C4", mensagem)
        self.assertIn("enlace_fora", mensagem)
        self.assertIn("E-R1-R4", mensagem)

    def test_c6_recusado_enquanto_erro_de_bit_nao_existir(self):
        if "erro_bit" in TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS:
            self.skipTest("F4 já aplica erro_bit")
        with self.assertRaises(CasoNaoSuportado) as erro:
            executar_caso(self.topo, "C6")
        self.assertIn("erro_bit", str(erro.exception))

    def test_os_casos_sem_intervencao_continuam_executando(self):
        for caso in ("C1", "C2", "C3", "C5", "C7"):
            with self.subTest(caso=caso):
                self.assertTrue(executar_caso(self.topo, caso))

    def test_casos_executaveis_lista_exatamente_o_que_roda(self):
        """A lista que os testes de restrição usam para varrer "todos os
        casos" sem tropeçar nos pendentes.

        Derivada do que o motor declara suportar, e não escrita à mão: cada
        intervenção implementada em F4 move um caso de um lado para o outro, e
        o teste acompanha sozinho."""
        executaveis = casos_executaveis(self.topo)
        for caso in self.topo.casos:
            pendentes = [
                e.tipo for e in caso.eventos_externos
                if e.tipo not in TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS
            ]
            with self.subTest(caso=caso.id):
                if pendentes:
                    self.assertNotIn(caso.id, executaveis)
                else:
                    self.assertIn(caso.id, executaveis)
                    self.assertTrue(executar_caso(self.topo, caso.id))


class RecusaNaLinhaDeComando(unittest.TestCase):
    def test_c4_sai_com_mensagem_e_codigo_diferente_de_zero(self):
        if "enlace_fora" in TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS:
            self.skipTest("F4 já aplica enlace_fora")
        resultado = simulador("--caso", "C4")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertEqual(resultado.stdout, "")
        self.assertNotIn("Traceback", resultado.stderr)
        self.assertIn("C4", resultado.stderr)
        self.assertIn("enlace_fora", resultado.stderr)

    def test_c6_sai_com_mensagem_e_codigo_diferente_de_zero(self):
        if "erro_bit" in TIPOS_DE_EVENTO_EXTERNO_SUPORTADOS:
            self.skipTest("F4 já aplica erro_bit")
        resultado = simulador("--caso", "C6")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertEqual(resultado.stdout, "")
        self.assertIn("erro_bit", resultado.stderr)

    def test_c2_continua_saindo_com_codigo_zero(self):
        """Contraprova: a recusa é do caso pendente, não de qualquer caso."""
        resultado = simulador("--caso", "C2")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
