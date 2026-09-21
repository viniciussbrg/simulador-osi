"""T-MET — as métricas dos sete casos batem com a tabela 11.3 (issue #45).

A tabela 11.3 é critério de aceitação, não resultado esperado: os valores estão
escritos aqui **literalmente**, copiados do documento, e o teste compara contra
eles. Recalcular a conta dentro do teste provaria apenas que o motor concorda
consigo mesmo — se a contabilidade de uma camada estiver errada, a fórmula
repetida no teste erraria junto.

    | Caso | Dados | Enlaces | Transmitido |     η | Sobrecarga |
    |------|-------|---------|-------------|-------|------------|
    | C1   |  42 B |       1 |        92 B | 45,7% |      54,3% |
    | C2   |  42 B |       4 |       368 B | 11,4% |      88,6% |
    | C3   |  84 B |   4 + 4 |       736 B | 11,4% |      88,6% |
    | C4   |  42 B |       4 |       368 B | 11,4% |      88,6% |
    | C5   |  42 B |       1 |        92 B |    0% |          — |
    | C6   |  42 B |       3 |       276 B |    0% |          — |
    | C7   | 100 B |   4 × 3 |       968 B | 10,3% |      89,7% |

O que cada linha demonstra, e por isso a tabela inteira importa: C1 e C2 são a
mesma mensagem em um enlace e em quatro — a eficiência cai de 45,7% para 11,4%
não porque os cabeçalhos cresceram, mas porque o quadro é reconstruído a cada
salto (seção 11.4). C7 sobe para 14,0% porque segmentos maiores diluem melhor
o mesmo controle. C3 tem o dobro de tudo e o mesmo η, já que são duas cópias
do percurso de C2. C5 e C6 gastaram rede e não entregaram nada.

A estrutura do evento `METRICAS` — posição no registro, redação da linha,
campos — é conferida em `tests/test_metricas.py` (issue #43); aqui só os
números.

Executar:  python -m unittest tests.test_met
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais

# Tolerância de ponto flutuante para η e sobrecarga: a tabela publica uma casa
# decimal em pontos percentuais (45,7%), então a comparação é contra o valor
# arredondado, com folga de um milésimo.
TOLERANCIA = 0.001

# A tabela 11.3, transcrita. Os dois últimos números são fração, não
# porcentagem. Em C5 e C6 a tabela escreve "—" na sobrecarga: nada foi
# entregue, logo todo o tráfego foi controle — 100% (decisão registrada na
# issue #43, junto com o campo `dados_entregues`).
TABELA_11_3 = {
    "C1": {"dados": 42, "enlaces": 1, "transmitido": 92, "eta": 0.457, "sobrecarga": 0.543},
    "C2": {"dados": 42, "enlaces": 4, "transmitido": 368, "eta": 0.114, "sobrecarga": 0.886},
    "C3": {"dados": 84, "enlaces": 8, "transmitido": 736, "eta": 0.114, "sobrecarga": 0.886},
    "C4": {"dados": 42, "enlaces": 4, "transmitido": 368, "eta": 0.114, "sobrecarga": 0.886},
    "C5": {"dados": 42, "enlaces": 1, "transmitido": 92, "eta": 0.0, "sobrecarga": 1.0},
    "C6": {"dados": 42, "enlaces": 3, "transmitido": 276, "eta": 0.0, "sobrecarga": 1.0},
    "C7": {"dados": 100, "enlaces": 12, "transmitido": 968, "eta": 0.103, "sobrecarga": 0.897},
}

# Quantos quadros cada caso constrói. Não está na tabela 11.3, mas é o par do
# número de travessias: o quadro é destruído e reconstruído a cada salto (R2),
# e é justamente essa reconstrução que explica a queda de eficiência.
QUADROS = {"C1": 1, "C2": 4, "C3": 8, "C4": 4, "C5": 1, "C6": 3, "C7": 12}


class ValoresDaTabela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        topo = carregar_topologia()
        cls.metricas = {
            caso: principais(executar_caso(topo, caso))[-1].metricas
            for caso in TABELA_11_3
        }

    def test_todos_os_casos_publicam_metricas(self):
        for caso in TABELA_11_3:
            with self.subTest(caso=caso):
                self.assertIsNotNone(self.metricas[caso])

    def test_dados_uteis(self):
        """Contados uma vez, não por segmento nem por travessia: C7 tem 100 B
        repartidos em três segmentos que cruzam quatro enlaces cada, e continua
        sendo 100."""
        for caso, esperado in TABELA_11_3.items():
            with self.subTest(caso=caso):
                self.assertEqual(self.metricas[caso].dados_uteis, esperado["dados"])

    def test_total_transmitido(self):
        """A soma de todos os quadros postos em todos os enlaces — o número que
        cresce a cada salto."""
        for caso, esperado in TABELA_11_3.items():
            with self.subTest(caso=caso):
                self.assertEqual(
                    self.metricas[caso].total_transmitido, esperado["transmitido"]
                )

    def test_enlaces_percorridos(self):
        """Travessias, não enlaces distintos: a tabela escreve 4 + 4 em C3 e
        4 × 3 em C7 justamente por isso."""
        for caso, esperado in TABELA_11_3.items():
            with self.subTest(caso=caso):
                self.assertEqual(
                    self.metricas[caso].enlaces_percorridos, esperado["enlaces"]
                )

    def test_quadros_construidos(self):
        for caso, esperado in QUADROS.items():
            with self.subTest(caso=caso):
                self.assertEqual(self.metricas[caso].quadros_construidos, esperado)

    def test_eta(self):
        for caso, esperado in TABELA_11_3.items():
            with self.subTest(caso=caso):
                self.assertAlmostEqual(
                    self.metricas[caso].eta, esperado["eta"], delta=TOLERANCIA
                )

    def test_sobrecarga(self):
        for caso, esperado in TABELA_11_3.items():
            with self.subTest(caso=caso):
                self.assertAlmostEqual(
                    self.metricas[caso].sobrecarga,
                    esperado["sobrecarga"],
                    delta=TOLERANCIA,
                )


class ComparacaoExigida(unittest.TestCase):
    """Seção 11.4: C1 e C2 lado a lado, em todo caso executado, para que a
    barra inferior os exiba simultaneamente sem chamar o núcleo."""

    @classmethod
    def setUpClass(cls):
        topo = carregar_topologia()
        cls.metricas = {
            caso: principais(executar_caso(topo, caso))[-1].metricas
            for caso in TABELA_11_3
        }

    def test_a_comparacao_esta_em_todos_os_casos(self):
        for caso in TABELA_11_3:
            with self.subTest(caso=caso):
                self.assertEqual(set(self.metricas[caso].comparacao), {"C1", "C2"})

    def test_os_valores_comparados_sao_os_da_tabela(self):
        for caso in TABELA_11_3:
            comparacao = self.metricas[caso].comparacao
            for referencia in ("C1", "C2"):
                with self.subTest(caso=caso, referencia=referencia):
                    self.assertAlmostEqual(
                        comparacao[referencia],
                        TABELA_11_3[referencia]["eta"],
                        delta=TOLERANCIA,
                    )

    def test_a_queda_de_eficiencia_entre_um_enlace_e_quatro(self):
        """O ponto conceitual da seção 11.4, medido: mesma mensagem, quatro
        vezes mais rede, eficiência quatro vezes menor."""
        comparacao = self.metricas["C2"].comparacao
        self.assertGreater(comparacao["C1"], comparacao["C2"])
        self.assertAlmostEqual(
            comparacao["C1"] / comparacao["C2"], 4.0, delta=0.01
        )
        self.assertEqual(
            self.metricas["C2"].total_transmitido,
            self.metricas["C1"].total_transmitido * 4,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
