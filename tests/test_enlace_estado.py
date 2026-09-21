"""Recálculo de rotas ao mudar o estado de um enlace (issue #22).

Seção 6.1 da proposta técnica: o Dijkstra é "executado novamente sempre que
um enlace mude de estado", e é esse mecanismo que sustenta C4 — derrubar
`E-R1-R4` sobre o caso C2 obriga a rota de R1 para a Rede C a trocar de
`R1→R4→R3` (custo 2, interface e1) para `R1→R2→R3` (custo 3, interface e2).

`Topologia.com_enlace_ativo` devolve uma cópia da topologia com o enlace
marcado ativo/inativo; como todo o roteamento já filtra por `enlace.ativo` e
recomputa a cada chamada, "recalcular" é só consultar a topologia devolvida.
Aqui verifica-se: a rota de C4 depois da queda, a ausência de qualquer
menção ao enlace derrubado, a imutabilidade da topologia original, a volta
da rota curta ao reativar, e o texto do evento de sistema `ENLACE_FORA`.

A validação ampla das rotas da tabela 6.5 é T-ROTA (issue #26); este arquivo
cobre só a troca de estado.

Executar:  python -m unittest tests.test_enlace_estado
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia, texto_enlace_fora

_TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")
_ENLACE_C4 = "E-R1-R4"


def _rota_rede_c(topo, roteador="R1"):
    """A `RotaEncaminhamento` de `roteador` para a Rede C (10.0.3.0/24)."""
    return topo.tabela_encaminhamento(roteador).consulta("10.0.3.10")


class TestQuedaDeEnlace(unittest.TestCase):
    def setUp(self):
        self.topo = carregar_topologia(_TOPOLOGIA)

    def test_rota_de_C2_antes_da_queda(self):
        # Ponto de partida: com E-R1-R4 no ar, R1 alcança a Rede C por R4.
        rota = _rota_rede_c(self.topo)
        self.assertEqual(rota.custo, 2)
        self.assertEqual(rota.interface_saida, "e1")
        self.assertEqual(rota.proximo_salto, "10.0.14.4")

    def test_queda_recalcula_para_a_rota_de_C4(self):
        caido = self.topo.com_enlace_ativo(_ENLACE_C4, ativo=False)
        rota = _rota_rede_c(caido)
        self.assertEqual(rota.custo, 3)
        self.assertEqual(rota.interface_saida, "e2")
        self.assertEqual(rota.proximo_salto, "10.0.12.2")  # R2 na rede R1–R2

    def test_nenhuma_rota_cita_o_enlace_derrubado(self):
        caido = self.topo.com_enlace_ativo(_ENLACE_C4, ativo=False)

        # O grafo do Dijkstra não vê mais o enlace...
        self.assertNotIn(_ENLACE_C4, {a.enlace for a in caido.arestas()})

        # ...e nenhuma tabela de encaminhamento sai pela rede R1–R4 (e1 de R1,
        # e0 de R4) nem aponta um próximo salto 10.0.14.x.
        for roteador, tabela in caido.tabelas_encaminhamento().items():
            for rota in tabela.rotas:
                salto = rota.proximo_salto or ""
                self.assertFalse(
                    salto.startswith("10.0.14."),
                    f"{roteador}: {rota} ainda salta pela rede R1–R4",
                )

    def test_nenhuma_rota_sai_pela_interface_do_enlace_derrubado(self):
        """A outra metade do critério "nenhuma linha menciona o enlace R1–R4":
        além do próximo salto, a **interface de saída**.

        Uma rede diretamente conectada não passa pelo Dijkstra, e por isso
        escapava da conferência anterior: R1 continuava anunciando 10.0.14.0/24
        por e1, com custo 0, por um enlace fora do ar."""
        caido = self.topo.com_enlace_ativo(_ENLACE_C4, ativo=False)
        proibidas = {("R1", "e1"), ("R4", "e0")}  # as duas pontas do enlace

        for roteador, tabela in caido.tabelas_encaminhamento().items():
            for rota in tabela.rotas:
                with self.subTest(roteador=roteador, prefixo=rota.prefixo):
                    self.assertNotIn(
                        (roteador, rota.interface_saida),
                        proibidas,
                        f"{roteador}: {rota} sai por interface de enlace fora do ar",
                    )

    def test_a_rede_do_enlace_derrubado_deixa_de_ser_diretamente_conectada(self):
        """Com o enlace fora, 10.0.14.0/24 não é mais entrega local: ou some da
        tabela, ou é alcançada como qualquer rede remota, dando a volta por
        R2 → R3 → R4."""
        caido = self.topo.com_enlace_ativo(_ENLACE_C4, ativo=False)

        for roteador in ("R1", "R4"):
            rota = caido.tabela_encaminhamento(roteador).consulta("10.0.14.1")
            with self.subTest(roteador=roteador):
                if rota is not None:
                    self.assertFalse(
                        rota.diretamente_conectada,
                        f"{roteador}: {rota} continua diretamente conectada",
                    )
                    self.assertGreater(rota.custo, 0)

    def test_topologia_original_fica_intacta(self):
        self.topo.com_enlace_ativo(_ENLACE_C4, ativo=False)
        # A cópia não deve ter mexido no objeto original.
        self.assertTrue(self.topo.enlace(_ENLACE_C4).ativo)
        self.assertEqual(_rota_rede_c(self.topo).custo, 2)

    def test_reativar_volta_a_rota_curta(self):
        caido = self.topo.com_enlace_ativo(_ENLACE_C4, ativo=False)
        restaurado = caido.com_enlace_ativo(_ENLACE_C4, ativo=True)
        rota = _rota_rede_c(restaurado)
        self.assertEqual((rota.custo, rota.interface_saida), (2, "e1"))

    def test_estado_ja_no_alvo_devolve_a_mesma_topologia(self):
        # E-R1-R4 já nasce ativo — pedir ativo=True não gera cópia.
        self.assertIs(self.topo.com_enlace_ativo(_ENLACE_C4, ativo=True), self.topo)

    def test_enlace_inexistente_levanta_keyerror(self):
        with self.assertRaises(KeyError):
            self.topo.com_enlace_ativo("E-NAO-EXISTE", ativo=False)


class TestTextoEnlaceFora(unittest.TestCase):
    def test_usa_o_rotulo_e_a_redacao_do_criterio_de_C4(self):
        topo = carregar_topologia(_TOPOLOGIA)
        texto = texto_enlace_fora(topo.enlace(_ENLACE_C4))
        self.assertEqual(texto, "enlace R1–R4 indisponível, rotas recalculadas")


if __name__ == "__main__":
    unittest.main()
