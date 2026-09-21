"""Caso C4 — falha de enlace e recálculo de rota (issue #40).

C4 é C2 com um cabo a menos: o mesmo fluxo H1 → H4, a mesma mensagem, o mesmo
destino — só que o enlace R1–R4 está fora do ar. É o caso que mostra que a
rota não é desenho fixo da topologia e sim resultado de um cálculo: sem
R1–R4, o Dijkstra acha R1 → R2 → R3, custo 3 em vez de 2, e o registro inteiro
muda de caminho sem que uma linha de código saiba o que é "C4".

O critério da seção 10/C4 tem três partes, e a terceira é a mais exigente:
**nenhuma linha menciona o enlace R1–R4**. Não basta o pacote não passar por
ele — nenhuma tabela pode anunciá-lo, nem como rede diretamente conectada,
que é a parte que escapava do Dijkstra (pendência de F2, coberta em
`tests/test_enlace_estado.py`).

Executar:  python -m unittest tests.test_caso_c4
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais

ENLACE_DERRUBADO = "E-R1-R4"
ROTULO_DERRUBADO = "R1–R4"


# O evento `METRICAS` fecha toda execução (issue #43): é de sistema, camada 0,
# sem fluxo. Os testes abaixo falam do percurso da mensagem, então olham o
# último evento **de camada** — `desfecho` — em vez do último da lista.

def desfecho(eventos):
    """O último evento de camada do registro, ignorando o `METRICAS` final."""
    return next(e for e in reversed(eventos) if e.camada > 0)


class CasoC4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C4")
        cls.registro = principais(cls.eventos)

    # -- critério de aceitação da seção 10/C4 ------------------------------

    def test_o_registro_abre_com_a_queda_do_enlace(self):
        """A intervenção vem antes de tudo: a queda é o gatilho do caso, e o
        primeiro `ROTEIA` já tem de enxergar a topologia nova."""
        primeiro = self.registro[0]
        self.assertEqual(primeiro.acao, "ENLACE_FORA")
        self.assertEqual(primeiro.camada, 0)
        self.assertEqual(primeiro.dispositivo, "--")
        self.assertEqual(
            primeiro.descricao, "enlace R1–R4 indisponível, rotas recalculadas"
        )
        self.assertIsNone(primeiro.tamanho)

    def test_a_linha_de_sistema_aparece_uma_unica_vez(self):
        self.assertEqual(
            [e.acao for e in self.registro].count("ENLACE_FORA"), 1
        )

    def test_r1_roteia_pela_rota_alternativa_de_custo_3(self):
        """A linha escrita por extenso no critério."""
        roteia = next(
            e for e in self.registro if e.dispositivo == "R1" and e.acao == "ROTEIA"
        )
        self.assertEqual(
            roteia.descricao, "10.0.3.0/24 via R2, custo 3, interface e2"
        )
        self.assertEqual(roteia.tamanho, 74)

    def test_nenhuma_linha_menciona_o_enlace_derrubado(self):
        """Fora da linha que anuncia a queda, o enlace derrubado não aparece
        em lugar nenhum — nem no texto, nem no campo `enlace`, nem no caminho.

        A própria `ENLACE_FORA` é a exceção nas duas formas, e por construção:
        ela existe para nomear o enlace que caiu, na descrição (critério da
        seção 10/C4) e no campo estrutural, que é de onde o mapa tira o traço
        tracejado com X (V1, issue #48). Tráfego sobre o enlace é o que o
        teste proíbe — mencioná-lo para dizer que está fora, não."""
        for evento in self.eventos:
            with self.subTest(passo=evento.passo):
                if evento.acao != "ENLACE_FORA":
                    self.assertNotIn(ROTULO_DERRUBADO, evento.descricao)
                    if evento.enlace is not None:
                        self.assertNotEqual(evento.enlace.id, ENLACE_DERRUBADO)
                self.assertNotIn(ENLACE_DERRUBADO, evento.caminho)

    def test_a_queda_identifica_o_enlace_em_campo_proprio(self):
        """O outro lado: a interface não precisa ler a descrição para saber
        qual enlace desenhar fora do ar (regra de acoplamento, seção 4.2)."""
        queda = self.registro[0]
        self.assertIsNotNone(queda.enlace)
        self.assertEqual(queda.enlace.id, ENLACE_DERRUBADO)
        self.assertEqual(queda.enlace.rotulo, ROTULO_DERRUBADO)

    def test_r4_fica_fora_do_percurso(self):
        """O roteador não sumiu da topologia — sumiu do caminho."""
        dispositivos = {e.dispositivo for e in self.registro}
        self.assertNotIn("R4", dispositivos)
        self.assertLessEqual({"H1", "R1", "R2", "R3", "H4"}, dispositivos)

    def test_o_caminho_percorrido_e_a_rota_alternativa(self):
        self.assertEqual(
            desfecho(self.registro).caminho, ("E-A", "E-R1-R2", "E-R2-R3", "E-C")
        )

    # -- o resto é C2, do qual C4 herda o fluxo ---------------------------

    def test_quatro_quadros_e_368_octetos_transmitidos(self):
        """Mesma quantidade de saltos de C2, por caminho diferente: o total
        transmitido não muda (tabela 11.3)."""
        enquadrados = [e.quadro for e in self.eventos if e.acao == "ENQUADRA"]
        self.assertEqual(enquadrados, ["Q1", "Q2", "Q3", "Q4"])
        transmitidos = [e.tamanho for e in self.eventos if e.acao == "TRANSMITE"]
        self.assertEqual(sum(transmitidos), 368)

    def test_o_fluxo_e_o_mesmo_de_c2(self):
        """C4 herda o fluxo de C2 (`herda` no arquivo): mesma origem, mesmo
        destino, mesmo par lógico de ponta a ponta."""
        pares = {(e.logico.origem, e.logico.destino) for e in self.eventos if e.logico}
        self.assertEqual(pares, {("10.0.1.10", "10.0.3.10")})
        self.assertEqual(desfecho(self.registro).acao, "ENTREGA")
        self.assertEqual(desfecho(self.registro).dispositivo, "H4")

    def test_a_topologia_original_nao_e_alterada(self):
        """A queda vale para esta execução; o objeto de topologia que o
        chamador passou continua com o enlace no ar — executar C2 depois de C4
        tem de dar a rota de custo 2 de novo."""
        self.assertTrue(self.topo.enlace(ENLACE_DERRUBADO).ativo)
        depois = principais(executar_caso(self.topo, "C2"))
        roteia = next(
            e for e in depois if e.dispositivo == "R1" and e.acao == "ROTEIA"
        )
        self.assertEqual(
            roteia.descricao, "10.0.3.0/24 via R4, custo 2, interface e1"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
