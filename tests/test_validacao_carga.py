"""Erros de topologia que só apareciam tarde — pendências de F2 (issue #33).

A regra da seção 5.7 é "mensagem clara, nunca rastreamento de pilha", e ela
vale para a **carga**: quem edita o `topologia.json` ao lado do executável não
tem Python para ler um traceback, e menos ainda para entender um
`AssertionError` que só estoura quando alguém pede uma rota.

Cada arquivo de `tests/fixtures/` abaixo passava pela validação da issue #23
e falhava depois — ou, pior, era aceito em silêncio e produzia rota errada.
Todos param na carga agora. A porta de entrada testada é `carregar_topologia`,
o mesmo caminho de `--topologia caminho.json`.

Executar:  python -m unittest tests.test_validacao_carga
"""

import json
import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from rede import ErroTopologia, analisar_topologia, carregar_topologia

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def carregar(nome: str):
    return carregar_topologia(os.path.join(_FIXTURES, nome))


class ParaNaCarga(unittest.TestCase):
    """Nenhum destes chega a consultar rota: a mensagem sai na carga."""

    def test_ponta_de_enlace_com_interface_de_outra_rede(self):
        """A ponta é o que amarra o enlace à interface; se a interface está
        noutra rede, o endereço lógico do vizinho que a camada 3 resolve não
        pertence ao enlace por onde o quadro vai sair."""
        with self.assertRaises(ErroTopologia) as erro:
            carregar("enlace_ponta_em_outra_rede.json")
        self.assertIn("E-R1-R4", str(erro.exception))
        self.assertIn("R4.e1", str(erro.exception))
        self.assertIn("R1R4", str(erro.exception))

    def test_prefixo_com_octeto_nao_numerico(self):
        with self.assertRaisesRegex(ErroTopologia, "não é um prefixo IPv4 válido"):
            carregar("prefixo_malformado.json")

    def test_prefixo_com_mascara_diferente_de_24(self):
        """Todas as máscaras são /24 (seção 1.2). A interface já era conferida;
        o prefixo da rede passava batido."""
        with self.assertRaisesRegex(ErroTopologia, "/16 não é suportada"):
            carregar("prefixo_mascara_nao_suportada.json")

    def test_duas_redes_com_o_mesmo_prefixo(self):
        """`CamadaRede.roteia` escolhe **uma** rota por prefixo; duas redes com
        o mesmo prefixo tornariam a escolha ambígua no primeiro `ROTEIA`."""
        with self.assertRaisesRegex(ErroTopologia, "Prefixo repetido"):
            carregar("prefixo_repetido.json")

    def test_duas_redes_com_o_mesmo_id(self):
        """Antes, isto saía como "Interface H3.eth0 referencia rede
        inexistente: B" — mensagem que aponta para o lugar errado."""
        with self.assertRaisesRegex(ErroTopologia, "Rede duplicada: A"):
            carregar("rede_id_repetida.json")

    def test_dois_enlaces_com_o_mesmo_id(self):
        """`Topologia.enlace()` devolve o primeiro e `com_enlace_ativo` mexe
        nos dois: derrubar um enlace em C4 derrubaria o outro junto."""
        with self.assertRaisesRegex(ErroTopologia, "Enlace duplicado: E-R1-R4"):
            carregar("enlace_id_repetido.json")


class MensagemDaTabela57(unittest.TestCase):
    """V-06 e V-10 existem, mas respondiam com outra mensagem."""

    def test_custo_fracionario_e_custo_invalido(self):
        with self.assertRaisesRegex(ErroTopologia, "Custo inválido no enlace E-R1-R4"):
            carregar("v06_custo_fracionario.json")

    def test_custo_negativo_em_difusao_e_custo_invalido(self):
        """Custo negativo é custo inválido mesmo num segmento de difusão — a
        mensagem sobre "difusão tem de ter custo 0" fica para o custo positivo,
        que é engano de outra natureza."""
        with self.assertRaisesRegex(ErroTopologia, "Custo inválido no enlace E-A"):
            carregar("v06_custo_negativo_em_difusao.json")

    def test_custo_positivo_em_difusao_mantem_a_mensagem_da_secao_5_2(self):
        """Custo positivo em difusão não é custo inválido: é o engano de quem
        atribuiu peso a um segmento que não tem trânsito (seção 5.2). A
        mensagem própria dele continua de pé."""
        with open(os.path.join(_RAIZ, "topologia.json"), encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        for enlace in dados["enlaces"]:
            if enlace["id"] == "E-A":
                enlace["custo"] = 5

        with self.assertRaisesRegex(ErroTopologia, "custo 0"):
            analisar_topologia(dados)

    def test_caso_unico_que_nao_cabe_no_limite(self):
        """A isenção de V-10 vale para o caso de segmentação, identificado por
        ser o mais longo **entre casos de tamanhos diferentes**. Num arquivo de
        caso único não há contraste, e aí a mensagem tem de caber num
        segmento."""
        with self.assertRaisesRegex(
            ErroTopologia, "limite_segmento incompatível com o caso C7"
        ):
            carregar("v10_caso_unico_nao_cabe.json")


class ReferenciaContinuaValida(unittest.TestCase):
    def test_topologia_de_referencia_passa_pelas_verificacoes_novas(self):
        carregar_topologia(os.path.join(_RAIZ, "topologia.json"))

    def test_topologia_alternativa_passa_pelas_verificacoes_novas(self):
        carregar("topologia_alternativa.json")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
