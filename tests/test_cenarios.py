# -*- coding: utf-8 -*-
"""Testes dos sete cenarios de validacao.

Executar da raiz do projeto:

    python -m unittest discover -s tests -v

Cada teste confere um valor que o enunciado ou os criterios de avaliacao
fixam. Se um deles falhar, o simulador deixou de ser comparavel com o
material da aula.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulador import cenarios, config                          # noqa: E402
from simulador.pdu import ip_valido, pertence_ao_prefixo        # noqa: E402
from simulador.rede import ErroTopologia, Topologia             # noqa: E402


class BaseCenarios(unittest.TestCase):
    """Carrega a topologia de referencia uma unica vez."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.topologia = Topologia()

    def executar(self, identificador: str):
        return cenarios.executar(self.topologia, identificador)

    def acoes(self, resultado, dispositivo: str, camada: str) -> list[str]:
        return [e.acao for e in resultado.registro
                if e.dispositivo == dispositivo and e.camada == camada]


class TestMensagensDeReferencia(BaseCenarios):

    def test_mensagem_curta_tem_42_octetos(self):
        self.assertEqual(len(cenarios.MENSAGEM_CURTA.encode(config.CODIFICACAO)), 42)

    def test_mensagem_longa_tem_100_octetos(self):
        self.assertEqual(len(cenarios.MENSAGEM_LONGA.encode(config.CODIFICACAO)), 100)

    def test_quadro_de_referencia_tem_92_octetos(self):
        comparativo = cenarios.comparativo_eficiencia(self.topologia)
        self.assertEqual(comparativo["quadro"], 92)


class TestTopologia(BaseCenarios):

    def test_tem_cinco_computadores_e_quatro_roteadores(self):
        self.assertEqual(len(self.topologia.computadores()), 5)
        self.assertEqual(len(self.topologia.roteadores()), 4)

    def test_enderecos_da_tabela_1(self):
        esperado = {
            "H1": "10.0.1.10", "H2": "10.0.1.11", "H3": "10.0.2.10",
            "H4": "10.0.3.10", "H5": "10.0.3.11",
        }
        for nome, ip in esperado.items():
            self.assertEqual(self.topologia.dispositivos[nome].ip_principal, ip)

    def test_r1_alcanca_rede_c_por_r4_com_custo_2(self):
        rota = self.topologia.consultar_rota("R1", "10.0.3.10")
        self.assertIsNotNone(rota)
        self.assertEqual(rota.via, "R4")
        self.assertEqual(rota.custo, 2)
        self.assertEqual(rota.interface_saida, "e1")

    def test_desvio_por_r2_custa_3_quando_r1_r4_cai(self):
        self.topologia.definir_estado_enlace("R1-R4", False)
        try:
            rota = self.topologia.consultar_rota("R1", "10.0.3.10")
            self.assertEqual(rota.via, "R2")
            self.assertEqual(rota.custo, 3)
        finally:
            self.topologia.restaurar_enlaces()

    def test_topologia_ausente_levanta_erro_legivel(self):
        with self.assertRaises(ErroTopologia):
            Topologia("arquivo_que_nao_existe.json")

    def test_prefixo_reconhece_rede_local(self):
        self.assertTrue(pertence_ao_prefixo("10.0.1.11", "10.0.1.0/24"))
        self.assertFalse(pertence_ao_prefixo("10.0.3.10", "10.0.1.0/24"))

    def test_endereco_invalido_e_recusado(self):
        for texto in ("10.0.9", "10.0.0.300", "abc", ""):
            self.assertFalse(ip_valido(texto))


class TestE1EntregaDireta(BaseCenarios):

    def test_um_unico_quadro_sem_roteador(self):
        resultado = self.executar("E1")
        self.assertEqual(resultado.caminho, ["H1", "H2"])
        self.assertEqual(resultado.total_quadros, 1)
        self.assertTrue(resultado.entregue)

    def test_eficiencia_de_um_enlace(self):
        resultado = self.executar("E1")
        self.assertEqual(resultado.octetos_dados, 42)
        self.assertEqual(resultado.octetos_transmitidos, 92)
        self.assertAlmostEqual(resultado.eficiencia, 42 / 92, places=6)


class TestE2CasoCentral(BaseCenarios):

    def test_caminho_de_menor_custo(self):
        resultado = self.executar("E2")
        self.assertEqual(resultado.caminho, ["H1", "R1", "R4", "R3", "H4"])

    def test_quatro_quadros_e_um_pacote(self):
        resultado = self.executar("E2")
        self.assertEqual(resultado.total_quadros, 4)
        rotulos = [q["rotulo"] for q in resultado.fluxos[0].quadros]
        self.assertEqual(rotulos, ["Q1", "Q2", "Q3", "Q4"])
        pacotes = {e.unidade.pacote for e in resultado.registro
                   if e.unidade is not None and e.unidade.pacote}
        self.assertEqual(pacotes, {"P1"})

    def test_eficiencia_de_11_4_por_cento(self):
        resultado = self.executar("E2")
        self.assertEqual(resultado.octetos_transmitidos, 368)
        self.assertEqual(f"{resultado.eficiencia:.1%}", "11.4%")

    def test_enderecos_logicos_nao_mudam_e_fisicos_mudam(self):
        resultado = self.executar("E2")
        quadros = resultado.fluxos[0].quadros
        logicos = {q["logicos"] for q in quadros}
        fisicos = [q["fisicos"] for q in quadros]
        self.assertEqual(logicos, {("10.0.1.10", "10.0.3.10")})
        self.assertEqual(len(set(fisicos)), 4)

    def test_tamanhos_da_convencao_de_cabecalhos(self):
        resultado = self.executar("E2")
        por_acao = {}
        for evento in resultado.registro:
            por_acao.setdefault((evento.dispositivo, evento.acao), evento.tamanho)
        self.assertEqual(por_acao[("H1", "GERA")], 42)
        self.assertEqual(por_acao[("H1", "ABRE")], 46)
        self.assertEqual(por_acao[("H1", "SEGMENTA")], 54)
        self.assertEqual(por_acao[("H1", "ENCAPSULA")], 74)
        self.assertEqual(por_acao[("H1", "ENQUADRA")], 92)

    def test_roteadores_nao_acionam_camadas_acima_da_3(self):
        resultado = self.executar("E2")
        for evento in resultado.registro:
            if evento.dispositivo.startswith("R"):
                self.assertLessEqual(evento.numero_camada, 3,
                                     f"roteador acionou {evento.camada}")

    def test_mensagem_chega_intacta(self):
        resultado = self.executar("E2")
        self.assertEqual(resultado.fluxos[0].texto_recebido, cenarios.MENSAGEM_CURTA)


class TestE3Demultiplexacao(BaseCenarios):

    def test_dois_fluxos_com_portas_de_origem_distintas(self):
        resultado = self.executar("E3")
        self.assertEqual(len(resultado.fluxos), 2)
        self.assertEqual(resultado.total_quadros, 8)

    def test_camada_4_do_destino_separa_os_fluxos(self):
        resultado = self.executar("E3")
        linhas = [e.descricao for e in resultado.registro
                  if e.dispositivo == "H4" and e.acao == "DEMULTIPLEXA"]
        self.assertEqual(len(linhas), 2)
        self.assertTrue(any("5210" in linha for linha in linhas))
        self.assertTrue(any("5310" in linha for linha in linhas))

    def test_cada_fluxo_recebe_a_propria_sessao(self):
        resultado = self.executar("E3")
        sessoes = {e.descricao.split()[1] for e in resultado.registro
                   if e.acao == "ABRE"}
        self.assertEqual(sessoes, {"S-0001", "S-0002"})


class TestE4FalhaDeEnlace(BaseCenarios):

    def test_caminho_alternativo_por_r2(self):
        resultado = self.executar("E4")
        self.assertEqual(resultado.caminho, ["H1", "R1", "R2", "R3", "H4"])
        self.assertTrue(resultado.entregue)

    def test_registro_indica_custo_3(self):
        resultado = self.executar("E4")
        rotas = [e.descricao for e in resultado.registro
                 if e.dispositivo == "R1" and e.acao == "ROTEIA"]
        self.assertTrue(any("custo 3" in d and "via R2" in d for d in rotas), rotas)

    def test_enlace_e_restaurado_apos_a_execucao(self):
        self.executar("E4")
        self.assertEqual(self.topologia.enlaces_derrubados(), [])


class TestE5DestinoInalcancavel(BaseCenarios):

    def test_descarte_no_primeiro_roteador_sem_rota(self):
        resultado = self.executar("E5")
        descartes = [e for e in resultado.registro if e.acao == "DESCARTA"]
        self.assertEqual(len(descartes), 1)
        self.assertEqual(descartes[0].dispositivo, "R1")
        self.assertEqual(descartes[0].camada, "L3")

    def test_origem_entrega_ao_roteador_padrao(self):
        resultado = self.executar("E5")
        self.assertEqual(resultado.caminho, ["H1", "R1"])
        self.assertFalse(resultado.entregue)


class TestE6ErroDeTransmissao(BaseCenarios):

    def test_quadro_descartado_pela_camada_2_de_r3(self):
        resultado = self.executar("E6")
        descartes = [e for e in resultado.registro if e.acao == "DESCARTA"]
        self.assertEqual(len(descartes), 1)
        self.assertEqual(descartes[0].dispositivo, "R3")
        self.assertEqual(descartes[0].camada, "L2")

    def test_nenhuma_linha_de_camada_3_em_r3(self):
        self.assertEqual(self.acoes(self.executar("E6"), "R3", "L3"), [])

    def test_h4_nunca_e_acionado(self):
        resultado = self.executar("E6")
        self.assertNotIn("H4", {e.dispositivo for e in resultado.registro})
        self.assertFalse(resultado.entregue)

    def test_tres_quadros_construidos(self):
        self.assertEqual(self.executar("E6").total_quadros, 3)


class TestE7MensagemLonga(BaseCenarios):

    def test_tres_segmentos_de_40_40_e_24(self):
        resultado = self.executar("E7")
        self.assertEqual(resultado.fluxos[0].segmentos, [40, 40, 24])

    def test_remontagem_em_ordem_no_destino(self):
        resultado = self.executar("E7")
        self.assertEqual(self.acoes(resultado, "H4", "L4"),
                         ["ARMAZENA", "ARMAZENA", "ARMAZENA", "REMONTA"])
        self.assertEqual(resultado.fluxos[0].texto_recebido,
                         cenarios.MENSAGEM_LONGA)

    def test_camada_5_so_e_acionada_apos_a_remontagem(self):
        resultado = self.executar("E7")
        passos_l4 = [e.passo for e in resultado.registro
                     if e.dispositivo == "H4" and e.acao == "REMONTA"]
        passos_l5 = [e.passo for e in resultado.registro
                     if e.dispositivo == "H4" and e.camada == "L5"]
        self.assertTrue(passos_l4 and passos_l5)
        self.assertLess(passos_l4[0], passos_l5[0])

    def test_doze_quadros_e_tres_pacotes(self):
        resultado = self.executar("E7")
        self.assertEqual(resultado.total_quadros, 12)
        pacotes = {e.unidade.pacote for e in resultado.registro
                   if e.unidade is not None and e.unidade.pacote}
        self.assertEqual(pacotes, {"P1", "P2", "P3"})


class TestCifraDaCamada6(BaseCenarios):

    def test_conteudo_viaja_cifrado_e_so_e_decifrado_no_destino(self):
        resultado = self.executar("E2")
        original = cenarios.MENSAGEM_CURTA.encode(config.CODIFICACAO)
        # Nenhum evento entre a codificacao na origem e a decodificacao no
        # destino pode carregar o texto legivel.
        for evento in resultado.registro:
            if evento.acao in ("GERA", "DECODIFICA", "ENCERRA", "ENTREGA"):
                continue
            if evento.unidade is not None:
                self.assertNotIn(original, evento.unidade.dados)

    def test_decodificacao_ocorre_apenas_na_camada_6(self):
        resultado = self.executar("E2")
        decodificacoes = [(e.dispositivo, e.camada) for e in resultado.registro
                          if e.acao == "DECODIFICA"]
        self.assertEqual(decodificacoes, [("H4", "L6")])


class TestRegistroDeEventos(BaseCenarios):

    def test_formato_da_linha(self):
        resultado = self.executar("E2")
        primeira = resultado.registro[0].linha
        campos = [parte.strip() for parte in primeira.split("|")]
        self.assertEqual(campos[0], "001")
        self.assertEqual(campos[1], "H1")
        self.assertEqual(campos[2], "L7")
        self.assertEqual(campos[3], "GERA")
        self.assertTrue(campos[4].endswith("42 B"))

    def test_passos_sao_sequenciais(self):
        resultado = self.executar("E2")
        passos = [e.passo for e in resultado.registro]
        self.assertEqual(passos, list(range(1, len(passos) + 1)))

    def test_todo_salto_registra_o_descarte_do_quadro(self):
        resultado = self.executar("E2")
        descartados = [e.descricao for e in resultado.registro
                       if e.acao == "DESENQUADRA"]
        self.assertEqual(len(descartados), 4)
        for descricao in descartados:
            self.assertIn("descartado", descricao)


class TestRelatorio(BaseCenarios):

    def test_html_contem_os_numeros_do_cenario(self):
        from simulador import relatorio

        resultado = self.executar("E2")
        pagina = relatorio.gerar_html(resultado, cenarios.obter("E2"),
                                      self.topologia)
        self.assertIn("11.4%", pagina)
        self.assertIn("Q4", pagina)
        self.assertIn("10.0.3.10", pagina)
        self.assertTrue(pagina.startswith("<!DOCTYPE html>"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
