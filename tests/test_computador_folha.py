"""Computador é folha no grafo de roteamento (pendência de F2, issue #27).

Seção 6.3 da proposta técnica: o computador não tem tabela de
encaminhamento — tem a sua rede e o seu gateway. Ele é ponta de um caminho,
nunca trecho do meio. `menor_caminho` (`rede.py`), porém, relaxava as arestas
que *saem* de um computador como se ele repassasse pacotes; num segmento de
difusão (custo 0) com dois roteadores e um host, o caminho `RA → H1 → RB`
empatava com `RA → RB` e o desempate lexicográfico da seção 6.4 elegia o
host, porque `"H1" < "RB"`. Com a convenção de nomes H*/R* do projeto o
computador ganha *sempre* esse empate — e a tabela de RA passava a mandar
pacotes para um host.

A topologia de referência não exibe o defeito (cada rede local tem um único
roteador), então o teste roda sobre `fixtures/topologia_computador_transito.json`,
montada só para isso: rede local `L` em difusão com H1, RA e RB, cada
roteador levando a uma rede própria do outro lado.

Aqui não se verifica só o caso construído: as duas invariantes gerais —
nenhum próximo salto é endereço de computador, nenhum caminho tem computador
no meio — são conferidas também na topologia de referência e na alternativa,
para que a correção não seja um remendo do fixture.

Executar:  python -m unittest tests.test_computador_folha
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import Topologia, carregar_topologia

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(nome: str) -> str:
    return os.path.join(_FIXTURES, nome)


def _computadores(topo: Topologia) -> frozenset[str]:
    return frozenset(d.nome for d in topo.dispositivos if d.tipo == "computador")


def _logicos_de_computador(topo: Topologia) -> frozenset[str]:
    """Todos os endereços lógicos que pertencem a computadores — o que um
    `RotaEncaminhamento.proximo_salto` jamais pode ser."""
    return frozenset(
        iface.logico
        for d in topo.dispositivos
        if d.tipo == "computador"
        for iface in d.interfaces
    )


class ComputadorNuncaEhTransito(unittest.TestCase):
    """As duas invariantes, sobre as três topologias disponíveis. Cada uma
    é rodada com os enlaces todos ativos e, depois, com cada enlace derrubado
    de uma vez — o recálculo de C4 não pode reabrir a brecha."""

    def topologias(self):
        yield "referência", carregar_topologia()
        yield "alternativa", carregar_topologia(fixture("topologia_alternativa.json"))
        yield "computador no meio", carregar_topologia(
            fixture("topologia_computador_transito.json")
        )

    def variacoes(self, topo: Topologia):
        """A topologia como está, e cada versão dela com um enlace fora."""
        yield "todos os enlaces ativos", topo
        for enlace in topo.enlaces:
            yield f"sem {enlace.id}", topo.com_enlace_ativo(enlace.id, ativo=False)

    def test_nenhuma_tabela_aponta_um_computador_como_proximo_salto(self):
        for rotulo, topo in self.topologias():
            hosts = _logicos_de_computador(topo)
            for variacao, t in self.variacoes(topo):
                for roteador, tabela in t.tabelas_encaminhamento().items():
                    for rota in tabela.rotas:
                        with self.subTest(topologia=rotulo, variacao=variacao,
                                          roteador=roteador, prefixo=rota.prefixo):
                            self.assertNotIn(rota.proximo_salto, hosts)

    def test_nenhum_caminho_tem_computador_em_posicao_intermediaria(self):
        for rotulo, topo in self.topologias():
            hosts = _computadores(topo)
            for variacao, t in self.variacoes(topo):
                for d in t.dispositivos:
                    arvore = t.arvore_caminhos(d.nome)
                    for salto in arvore.saltos:
                        intermediarios = set(salto.caminho[1:-1])
                        with self.subTest(topologia=rotulo, variacao=variacao,
                                          origem=d.nome, destino=salto.destino):
                            self.assertEqual(intermediarios & hosts, set())

    def test_computador_continua_valendo_como_origem_e_como_destino(self):
        """A restrição é de trânsito, não de alcance: a árvore de um host
        continua saindo dele, e todo host continua alcançável."""
        for rotulo, topo in self.topologias():
            hosts = _computadores(topo)
            for host in sorted(hosts):
                arvore = topo.arvore_caminhos(host)
                with self.subTest(topologia=rotulo, origem=host):
                    # Origem: alcança pelo menos o próprio gateway/vizinhança.
                    self.assertNotEqual(arvore.saltos, ())
                # Destino: alcançado a partir de todo roteador (grafo conexo, V-07).
                for d in topo.dispositivos:
                    if d.nome == host or d.tipo != "roteador":
                        continue
                    with self.subTest(topologia=rotulo, origem=d.nome, destino=host):
                        self.assertTrue(topo.arvore_caminhos(d.nome).alcanca(host))


class SegmentoDeDifusaoComDoisRoteadores(unittest.TestCase):
    """O caso exato da reprodução: `RA → H1 → RB` não pode vencer `RA → RB`,
    mesmo com `"H1" < "RB"` e custo 0 nos dois."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia(fixture("topologia_computador_transito.json"))

    def test_o_host_do_meio_perde_o_desempate_por_nao_encaminhar(self):
        salto = self.topo.arvore_caminhos("RA").salto("RB")
        self.assertEqual(salto.proximo_salto, "RB")
        self.assertEqual(salto.caminho, ("RA", "RB"))
        self.assertEqual(salto.custo, 0)

    def test_ra_alcanca_a_rede_de_rb_pelo_endereco_de_rb(self):
        rota = self.topo.tabela_encaminhamento("RA").consulta("10.1.3.10")
        self.assertIsNotNone(rota)
        self.assertEqual(rota.prefixo, "10.1.3.0/24")
        self.assertEqual(rota.proximo_salto, "10.1.1.2")  # RA.e0 → RB.e0, não H1
        self.assertEqual(rota.interface_saida, "e0")

    def test_o_trajeto_h1_ate_h2_passa_pelos_dois_roteadores(self):
        """A leitura de ponta a ponta: H1 manda ao gateway RA, RA repassa a
        RB, RB entrega localmente. Nenhum host no meio."""
        decisao = self.topo.decisao_computador("H1", "10.1.3.10")
        self.assertFalse(decisao.entrega_direta)
        self.assertEqual(decisao.proximo_salto, "10.1.1.1")  # gateway = RA

        em_ra = self.topo.tabela_encaminhamento("RA").consulta("10.1.3.10")
        self.assertEqual(em_ra.proximo_salto, "10.1.1.2")  # RB

        em_rb = self.topo.tabela_encaminhamento("RB").consulta("10.1.3.10")
        self.assertTrue(em_rb.diretamente_conectada)
        self.assertEqual(em_rb.interface_saida, "e1")


if __name__ == "__main__":
    unittest.main()
