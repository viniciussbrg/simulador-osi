"""Evento final `METRICAS` (issue #43).

Toda execução termina com uma linha de sistema que quantifica o custo do
empilhamento — o objetivo O5 do enunciado, e a única saída do programa que
responde "quanto da rede foi gasto com controle".

Duas definições da seção 11.1 governam tudo, e a diferença entre elas é o que
este arquivo mais persegue:

- **dados úteis** é a carga gerada pela camada 7, contada **uma vez**, não
  importa em quantos segmentos ela se parta nem quantos enlaces atravesse;
- **octetos transmitidos** é a soma de todos os quadros postos em todos os
  enlaces — é ela que cresce a cada salto, e é dessa razão que sai a queda de
  eficiência de 45,7% (C1, um enlace) para 11,4% (C2, quatro).

Casos sem entrega são o ponto delicado. A fórmula crua daria 45,7% para C5,
que não entregou nada: η mede o que **chegou**, não o que partiu. Daí
`dados_entregues`, que separa "0% porque nada chegou" de "0% por
arredondamento" sem que a interface precise inferir.

A conferência dos sete casos contra a tabela 11.3 é T-MET (issue #45); aqui
ficam a estrutura do evento, a posição dele no registro e a redação da linha.

Executar:  python -m unittest tests.test_metricas
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais


def metricas_de(topo, caso: str):
    registro = principais(executar_caso(topo, caso))
    return registro[-1]


class EventoFinal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()

    def test_toda_execucao_termina_com_metricas(self):
        for caso in (c.id for c in self.topo.casos):
            with self.subTest(caso=caso):
                ultimo = metricas_de(self.topo, caso)
                self.assertEqual(ultimo.acao, "METRICAS")
                self.assertEqual(ultimo.camada, 0)
                self.assertEqual(ultimo.dispositivo, "--")
                self.assertIsNone(ultimo.tamanho)
                self.assertIsNotNone(ultimo.metricas)

    def test_o_evento_aparece_uma_unica_vez(self):
        eventos = executar_caso(self.topo, "C2")
        self.assertEqual([e.acao for e in eventos].count("METRICAS"), 1)

    def test_o_passo_e_sequencial_ao_ultimo_evento_de_dados(self):
        registro = principais(executar_caso(self.topo, "C2"))
        self.assertEqual(registro[-1].passo, registro[-2].passo + 1)

    def test_a_linha_e_a_031_do_anexo_b(self):
        self.assertEqual(
            metricas_de(self.topo, "C2").linha(),
            "031 | -- | -- | METRICAS | 42 B úteis, 368 B transmitidos, η = 11,4%",
        )


class Contabilidade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()

    def test_dados_uteis_contam_a_mensagem_uma_vez_so(self):
        """C7 parte 100 octetos em três segmentos que atravessam quatro enlaces
        cada: os dados continuam sendo 100, não 300 nem 400."""
        self.assertEqual(metricas_de(self.topo, "C7").metricas.dados_uteis, 100)

    def test_dados_uteis_somam_os_fluxos_concorrentes(self):
        """C3 são duas mensagens de 42 octetos chegando ao mesmo destino."""
        self.assertEqual(metricas_de(self.topo, "C3").metricas.dados_uteis, 84)

    def test_total_transmitido_soma_todos_os_quadros_de_todos_os_enlaces(self):
        for caso, esperado in (("C1", 92), ("C2", 368), ("C7", 968)):
            with self.subTest(caso=caso):
                self.assertEqual(
                    metricas_de(self.topo, caso).metricas.total_transmitido, esperado
                )

    def test_eta_e_sobrecarga_sao_complementares(self):
        for caso in (c.id for c in self.topo.casos):
            with self.subTest(caso=caso):
                m = metricas_de(self.topo, caso).metricas
                self.assertAlmostEqual(m.eta + m.sobrecarga, 1.0, places=6)

    def test_enlaces_percorridos_e_quadros_construidos(self):
        """Uma travessia, um quadro: o quadro é reconstruído a cada salto (R2),
        então os dois números coincidem — e é justamente essa coincidência que
        explica a queda de eficiência."""
        for caso, esperado in (("C1", 1), ("C2", 4), ("C3", 8), ("C6", 3), ("C7", 12)):
            with self.subTest(caso=caso):
                m = metricas_de(self.topo, caso).metricas
                self.assertEqual(m.enlaces_percorridos, esperado)
                self.assertEqual(m.quadros_construidos, esperado)


class CasosSemEntrega(unittest.TestCase):
    """C5 morre por falta de rota, C6 por erro de verificação. A mensagem
    partiu e não chegou — η mede o que chegou."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()

    def test_eta_zero_quando_nada_e_entregue(self):
        for caso in ("C5", "C6"):
            with self.subTest(caso=caso):
                m = metricas_de(self.topo, caso).metricas
                self.assertEqual(m.eta, 0.0)
                self.assertEqual(m.sobrecarga, 1.0)

    def test_dados_uteis_registram_o_que_partiu(self):
        """A mensagem foi gerada: 42 octetos saíram de H1 em ambos os casos."""
        for caso in ("C5", "C6"):
            with self.subTest(caso=caso):
                self.assertEqual(metricas_de(self.topo, caso).metricas.dados_uteis, 42)

    def test_dados_entregues_distinguem_zero_de_arredondamento(self):
        for caso, entregues in (("C1", 42), ("C2", 42), ("C3", 84), ("C5", 0), ("C6", 0), ("C7", 100)):
            with self.subTest(caso=caso):
                self.assertEqual(
                    metricas_de(self.topo, caso).metricas.dados_entregues, entregues
                )

    def test_a_rede_foi_usada_mesmo_sem_entrega(self):
        """C6 gastou 276 octetos de rede para não entregar nada — é o que a
        sobrecarga de 100% quer dizer."""
        m = metricas_de(self.topo, "C6").metricas
        self.assertEqual(m.total_transmitido, 276)


class ComparacaoC1C2(unittest.TestCase):
    """Seção 11.4: os dois valores lado a lado, em qualquer caso executado."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()

    def test_todo_caso_traz_a_comparacao(self):
        for caso in (c.id for c in self.topo.casos):
            with self.subTest(caso=caso):
                comparacao = metricas_de(self.topo, caso).metricas.comparacao
                self.assertEqual(set(comparacao), {"C1", "C2"})

    def test_os_valores_da_comparacao_sao_os_da_tabela(self):
        comparacao = metricas_de(self.topo, "C7").metricas.comparacao
        self.assertAlmostEqual(comparacao["C1"], 0.4565, places=3)
        self.assertAlmostEqual(comparacao["C2"], 0.1141, places=3)

    def test_a_comparacao_de_c1_e_c2_bate_com_o_proprio_eta_deles(self):
        """Não são números escritos à mão: é o η que o próprio caso produz."""
        for caso in ("C1", "C2"):
            with self.subTest(caso=caso):
                m = metricas_de(self.topo, caso).metricas
                self.assertAlmostEqual(m.comparacao[caso], m.eta, places=6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
