"""Pilhas de dispositivo: `Computador` (7 camadas) e `Roteador` (3) — issue #27.

Três frentes:

- **R1 estrutural** — `Roteador` não tem objeto de camada 4 a 7, e não há como
  ganhar um: `__slots__` faz `roteador.l4 = ...` levantar `AttributeError`.
  Este é o teste da *estrutura*; T-R1 (issue #35) é o teste do *registro*, que
  só existe depois do motor (F3) e confere que nenhum evento de roteador
  carrega `porta`, `sessao`, `segmento` ou `processo`.
- **Encadeamento** — a ordem das camadas mora na pilha do dispositivo. Um
  percurso completo de C2 (H1 → R1 → R4 → R3 → H4) montado só com os métodos
  de `dispositivos.py` tem de reproduzir a sequência de
  (dispositivo, camada, ação, tamanho) do Anexo B.
- **Resoluções locais** — tabela de encaminhamento, par de endereços físicos
  de cada salto e rótulo de enlace, que `camadas.py` exige prontos no
  `Contexto`.

O percurso de `_percorrer` é um encadeador de teste, não o motor: numeração de
passo, redação e fila de eventos são de `simulador.py` (issues #28 a #33).
Quando F3 fechar, estes testes continuam valendo como oráculo isolado da
camada de dispositivos.

Executar:  python -m unittest tests.test_dispositivos
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

import pdu as _pdu
from camadas import reiniciar_contador_sessoes
from dispositivos import (
    AcaoCamada,
    Computador,
    atualizar_topologia,
    ErroDeDispositivo,
    Roteador,
    logico_do_extremo,
    montar_dispositivos,
)
from evento import Evento
from rede import carregar_topologia, limite_de_segmento

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(nome: str) -> str:
    return os.path.join(_FIXTURES, nome)


# --------------------------------------------------------------------------
# Encadeador de teste — um caso de fluxo único, ponta a ponta
# --------------------------------------------------------------------------


class Percurso:
    """Empurra um fluxo da origem ao destino usando só os métodos das pilhas,
    acumulando as `AcaoCamada` na ordem em que ocorreram.

    Faz o papel que caberá ao motor: escolher a quem entregar cada quadro e
    parar quando um pacote é descartado. Não numera passo nem escreve
    descrição — nada disso é de `dispositivos.py`."""

    def __init__(self, topologia, caso: str):
        _pdu.reiniciar_contador_quadros()
        reiniciar_contador_sessoes()
        self.topo = topologia
        self.caso = topologia.caso(caso)
        # O limite de segmentação vale por caso (seção 8.1), como no motor:
        # sem isso C7 rodaria com o limite global e daria dois segmentos.
        self.dispositivos = montar_dispositivos(
            topologia, limite_de_segmento(topologia, self.caso)
        )
        self.acoes: list[AcaoCamada] = []
        self.descartado_em: str | None = None

    def executar(self) -> list[AcaoCamada]:
        for fluxo in self.caso.fluxos:
            self._executar_fluxo(fluxo)
        return self.acoes

    def _executar_fluxo(self, fluxo) -> None:
        origem = self.dispositivos[fluxo.origem.dispositivo]
        envio = origem.iniciar_envio(fluxo)
        self.acoes.extend(envio.acoes)
        for segmento in envio.segmentos:
            self._percorrer(origem, envio, segmento, fluxo)

    def _percorrer(self, origem, envio, segmento, fluxo) -> None:
        decisao = origem.encapsular(envio, segmento)
        self.acoes.extend(decisao.acoes)
        no, pacote = origem, decisao.pacote

        while True:
            transmissao = no.enquadrar(
                pacote,
                vizinho=decisao.vizinho,
                interface_saida=decisao.interface_saida,
            )
            self.acoes.extend(transmissao.acoes)

            for entrega in transmissao.entregas:
                recepcao = self.dispositivos[entrega.destinatario].receber(entrega)
                self.acoes.extend(recepcao.acoes)
                if entrega.enderecado:
                    aceito, pacote = recepcao.aceito, recepcao.pacote

            proximo = transmissao.entrega_enderecada.destinatario
            if not aceito:
                self.descartado_em = proximo
                return

            no = self.dispositivos[proximo]
            if isinstance(no, Computador) and no.atende(envio.logico_destino):
                self.acoes.extend(no.entregar(pacote, envio.processo))
                return

            decisao = no.encaminhar(pacote)
            self.acoes.extend(decisao.acoes)
            if decisao.descartado:
                self.descartado_em = no.nome
                return
            pacote = decisao.pacote


def principais(acoes) -> list[AcaoCamada]:
    """As ações que o registro mostra por padrão — sem os descartes por
    endereço dos vizinhos de difusão (seção 7.5)."""
    return [a for a in acoes if not a.secundario]


def assinatura(acoes) -> list[tuple]:
    return [(a.dispositivo, a.camada, a.acao, a.tamanho) for a in acoes]


# --------------------------------------------------------------------------
# R1 — estrutural
# --------------------------------------------------------------------------


class RoteadorNaoTemCamadasAltas(unittest.TestCase):
    """A restrição R1 na estrutura: o roteador não tem os objetos, e não pode
    ganhá-los."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.dispositivos = montar_dispositivos(cls.topo)

    def test_roteador_instancia_apenas_l1_l2_l3(self):
        for nome in ("R1", "R2", "R3", "R4"):
            roteador = self.dispositivos[nome]
            self.assertIsInstance(roteador, Roteador)
            for camada in (1, 2, 3):
                with self.subTest(roteador=nome, camada=camada):
                    self.assertIsNotNone(getattr(roteador, f"l{camada}"))
            for camada in (4, 5, 6, 7):
                with self.subTest(roteador=nome, camada=camada):
                    # Não é `is None`: o atributo não existe (nem como None).
                    self.assertFalse(hasattr(roteador, f"l{camada}"))

    def test_nao_da_para_bolar_uma_camada_4_num_roteador_depois(self):
        from camadas import CamadaTransporte

        roteador = self.dispositivos["R1"]
        with self.assertRaises(AttributeError):
            roteador.l4 = CamadaTransporte()
        self.assertFalse(hasattr(roteador, "l4"))

    def test_roteador_nao_tem_dicionario_de_instancia(self):
        """Sem `__dict__` não há atributo improvisado — é o que torna a
        garantia estrutural em vez de convencional."""
        self.assertFalse(hasattr(self.dispositivos["R1"], "__dict__"))

    def test_computador_instancia_as_sete(self):
        for nome in ("H1", "H2", "H3", "H4", "H5"):
            computador = self.dispositivos[nome]
            self.assertIsInstance(computador, Computador)
            for camada in range(1, 8):
                with self.subTest(computador=nome, camada=camada):
                    self.assertIsNotNone(getattr(computador, f"l{camada}"))

    def test_nenhuma_acao_de_roteador_traz_contexto_superior(self):
        """A mesma verificação de T-R1 (issue #35), aqui sobre as ações cruas
        de C2 — quando o motor existir, T-R1 a repete sobre os `Evento`."""
        acoes = Percurso(self.topo, "C2").executar()
        roteadores = {"R1", "R2", "R3", "R4"}
        vistos = 0
        for acao in acoes:
            if acao.dispositivo not in roteadores:
                continue
            vistos += 1
            with self.subTest(dispositivo=acao.dispositivo, acao=acao.acao):
                self.assertIsNone(acao.porta)
                self.assertIsNone(acao.sessao)
                self.assertIsNone(acao.segmento)
                self.assertIsNone(acao.processo)
        self.assertGreater(vistos, 0, "C2 tem de passar por roteadores")


# --------------------------------------------------------------------------
# Encadeamento — C2, o caso central
# --------------------------------------------------------------------------


class EncadeamentoDeC2(unittest.TestCase):
    """As 30 ações de camada do Anexo B (a 031 é o `METRICAS` do motor), na
    ordem e com os tamanhos exatos."""

    # (dispositivo, camada, ação, tamanho) das linhas 001 a 030 do Anexo B.
    ESPERADO = [
        ("H1", 7, "GERA", 42),
        ("H1", 6, "CODIFICA", 42),
        ("H1", 5, "ABRE", 46),
        ("H1", 4, "SEGMENTA", 54),
        ("H1", 3, "ENCAPSULA", 74),
        ("H1", 3, "ROTEIA", 74),
        ("H1", 2, "ENQUADRA", 92),
        ("H1", 1, "TRANSMITE", 92),
        ("R1", 1, "RECEBE", 92),
        ("R1", 2, "DESENQUADRA", 74),
        ("R1", 3, "ROTEIA", 74),
        ("R1", 2, "ENQUADRA", 92),
        ("R1", 1, "TRANSMITE", 92),
        ("R4", 1, "RECEBE", 92),
        ("R4", 2, "DESENQUADRA", 74),
        ("R4", 3, "ROTEIA", 74),
        ("R4", 2, "ENQUADRA", 92),
        ("R4", 1, "TRANSMITE", 92),
        ("R3", 1, "RECEBE", 92),
        ("R3", 2, "DESENQUADRA", 74),
        ("R3", 3, "ROTEIA", 74),
        ("R3", 2, "ENQUADRA", 92),
        ("R3", 1, "TRANSMITE", 92),
        ("H4", 1, "RECEBE", 92),
        ("H4", 2, "DESENQUADRA", 74),
        ("H4", 3, "DESENCAPSULA", 54),
        ("H4", 4, "REMONTA", 46),
        ("H4", 5, "ENCERRA", 42),
        ("H4", 6, "DECIFRA", 42),
        ("H4", 7, "ENTREGA", 42),
    ]

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.acoes = Percurso(cls.topo, "C2").executar()
        cls.visiveis = principais(cls.acoes)

    def test_sequencia_e_tamanhos_do_anexo_b(self):
        self.assertEqual(assinatura(self.visiveis), self.ESPERADO)

    def test_a_rota_e_r1_r4_r3(self):
        roteia = [a for a in self.visiveis if a.acao == "ROTEIA"]
        self.assertEqual(
            [(a.dispositivo, a.vizinho_nome) for a in roteia],
            [("H1", "R1"), ("R1", "R4"), ("R4", "R3"), ("R3", "H4")],
        )
        # O último salto é a rede diretamente conectada de R3 (Anexo B, 021).
        self.assertTrue(roteia[-1].entrega_direta)
        self.assertEqual(roteia[-1].rota.prefixo, "10.0.3.0/24")
        self.assertEqual(roteia[-1].rota.interface, "e2")
        # R1 alcança 10.0.3.0/24 via R4 a custo 2, pela e1 (Anexo B, 011).
        self.assertEqual(roteia[1].rota.prefixo, "10.0.3.0/24")
        self.assertEqual(roteia[1].rota.custo, 2)
        self.assertEqual(roteia[1].rota.interface, "e1")
        # H1 não entrega direto: sai pelo gateway (Anexo B, 006).
        self.assertFalse(roteia[0].entrega_direta)
        self.assertEqual(roteia[0].vizinho, "10.0.1.1")
        self.assertEqual(roteia[0].rota.interface, "eth0")

    def test_quatro_quadros_distintos_um_por_enlace(self):
        """R2 antecipado: cada salto constrói um quadro novo, com id novo."""
        quadros = [a.quadro for a in self.visiveis if a.acao == "ENQUADRA"]
        self.assertEqual(quadros, ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(
            {a.quadro for a in self.acoes if a.quadro is not None},
            {"Q1", "Q2", "Q3", "Q4"},
        )

    def test_par_logico_unico_e_par_fisico_por_salto(self):
        """R3 antecipado: o lógico é gravado uma vez na origem; o físico é
        local a cada salto."""
        logicos = {(a.logico.origem, a.logico.destino)
                   for a in self.acoes if a.logico is not None}
        self.assertEqual(logicos, {("10.0.1.10", "10.0.3.10")})

        fisicos = {(a.fisico.origem, a.fisico.destino)
                   for a in self.visiveis if a.fisico is not None}
        self.assertEqual(len(fisicos), 4)
        self.assertIn(("AA:00:00:00:01:0A", "BB:00:00:00:01:00"), fisicos)  # H1→R1
        self.assertIn(("BB:00:00:00:03:02", "AA:00:00:00:03:0A"), fisicos)  # R3→H4

    def test_o_par_logico_aparece_de_encapsula_ate_desencapsula(self):
        """Seção 7.2: o par lógico existe a partir da L3 da origem — antes
        dela (L7–L4 da origem) e depois de removido (L4–L7 do destino) não há
        H3 de onde lê-lo."""
        for acao in self.visiveis:
            with self.subTest(dispositivo=acao.dispositivo, acao=acao.acao):
                if acao.camada >= 4 and acao.acao != "ENCAPSULA":
                    self.assertIsNone(acao.logico)
                else:
                    self.assertIsNotNone(acao.logico)

    def test_fisico_so_nas_camadas_1_e_2(self):
        for acao in self.visiveis:
            with self.subTest(dispositivo=acao.dispositivo, acao=acao.acao):
                if acao.camada in (1, 2):
                    self.assertIsNotNone(acao.fisico)
                    self.assertIsNotNone(acao.enlace)
                else:
                    self.assertIsNone(acao.fisico)
                    self.assertIsNone(acao.enlace)

    def test_bits_so_na_camada_1_e_sempre_tamanho_vezes_oito(self):
        for acao in self.visiveis:
            with self.subTest(dispositivo=acao.dispositivo, acao=acao.acao):
                if acao.camada == 1:
                    self.assertEqual(acao.bits, 736)
                    self.assertEqual(acao.bits, acao.tamanho * 8)
                else:
                    self.assertIsNone(acao.bits)

    def test_rotulos_de_enlace_sao_os_do_anexo_b(self):
        rotulos = [a.enlace.rotulo for a in self.visiveis if a.acao == "TRANSMITE"]
        self.assertEqual(rotulos, ["H1–R1", "R1–R4", "R4–R3", "R3–H4"])
        ids = [a.enlace.id for a in self.visiveis if a.acao == "TRANSMITE"]
        self.assertEqual(ids, ["E-A", "E-R1-R4", "E-R4-R3", "E-C"])

    def test_soma_dos_blocos_bate_com_o_tamanho(self):
        for acao in self.visiveis:
            with self.subTest(dispositivo=acao.dispositivo, acao=acao.acao):
                self.assertIsNotNone(acao.pdu)
                self.assertEqual(sum(b.tam for b in acao.pdu.blocos), acao.tamanho)

    def test_as_acoes_viram_evento_sem_campo_faltando(self):
        """A fronteira com `simulador.py`: `campos_de_evento()` mais passo,
        fluxo e descrição montam um `Evento` completo, e a linha sai formatada
        pelo método único de `evento.py`."""
        acao = self.visiveis[0]
        ev = Evento(passo=1, fluxo="F1", descricao="processo navegador, destino "
                    "servidorWeb", **acao.campos_de_evento())
        self.assertEqual(
            ev.linha(),
            "001 | H1 | L7 | GERA | processo navegador, destino servidorWeb             42 B",
        )


# --------------------------------------------------------------------------
# Difusão, entrega direta e descarte
# --------------------------------------------------------------------------


class DifusaoNaRedeA(unittest.TestCase):
    """O quadro chega a todas as estações do segmento; as que não são o
    destino descartam por endereço (`IGNORA`, secundário — seção 7.5)."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.acoes = Percurso(cls.topo, "C2").executar()

    def test_as_estacoes_alheias_dos_dois_segmentos_ignoram_o_quadro(self):
        """H2 recebe Q1 pela Rede A (é o descarte que a seção 7.5 cita) e H5
        recebe Q4 pela Rede C — os dois únicos segmentos de difusão com uma
        terceira estação no trajeto de C2."""
        ignorados = [a for a in self.acoes if a.acao == "IGNORA"]
        self.assertEqual([(a.dispositivo, a.quadro) for a in ignorados],
                         [("H2", "Q1"), ("H5", "Q4")])
        for acao in ignorados:
            with self.subTest(dispositivo=acao.dispositivo):
                self.assertTrue(acao.secundario)
                self.assertEqual(acao.estado, "descartado")
                # Sem PDU e sem tamanho: nada foi extraído do quadro.
                self.assertIsNone(acao.pdu)
                self.assertIsNone(acao.tamanho)

    def test_o_recebe_da_estacao_alheia_tambem_e_secundario(self):
        """É o que faz o registro padrão saltar de 008 (H1 TRANSMITE) para
        009 (R1 RECEBE), sem linha de H2 no meio."""
        de_h2 = [a for a in self.acoes if a.dispositivo == "H2"]
        self.assertEqual([a.acao for a in de_h2], ["RECEBE", "IGNORA"])
        self.assertTrue(all(a.secundario for a in de_h2))
        self.assertEqual(principais(de_h2), [])

    def test_cada_estacao_recebe_a_sua_copia_com_o_mesmo_identificador(self):
        """R2 continua de pé: as cópias de difusão não consomem numeração —
        C2 usa exatamente quatro identificadores."""
        recebidos = {a.quadro for a in self.acoes if a.acao in ("RECEBE", "IGNORA")}
        self.assertEqual(recebidos, {"Q1", "Q2", "Q3", "Q4"})

    def test_o_enlace_do_descarte_e_o_salto_ate_a_estacao_alheia(self):
        """O rótulo do salto é por par de pontas: o mesmo segmento E-A rende
        "H1–R1" para o destinatário e "H1–H2" para a estação que ignora."""
        ignorados = {a.dispositivo: a.enlace for a in self.acoes
                     if a.acao == "IGNORA"}
        self.assertEqual((ignorados["H2"].id, ignorados["H2"].rotulo),
                         ("E-A", "H1–H2"))
        self.assertEqual((ignorados["H5"].id, ignorados["H5"].rotulo),
                         ("E-C", "R3–H5"))


class EntregaDiretaEmC1(unittest.TestCase):
    """C1: H1 → H2 na mesma Rede A. Um quadro só, nenhum roteador na pilha de
    processamento — R1 está no segmento e recebe fisicamente, mas descarta por
    endereço."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.percurso = Percurso(cls.topo, "C1")
        cls.acoes = cls.percurso.executar()
        cls.visiveis = principais(cls.acoes)

    def test_um_unico_enquadra(self):
        self.assertEqual(len([a for a in self.acoes if a.acao == "ENQUADRA"]), 1)

    def test_nenhuma_acao_visivel_de_roteador(self):
        dispositivos = {a.dispositivo for a in self.visiveis}
        self.assertEqual(dispositivos, {"H1", "H2"})

    def test_r1_recebe_pelo_segmento_mas_ignora_por_endereco(self):
        de_r1 = [a for a in self.acoes if a.dispositivo == "R1"]
        self.assertEqual([a.acao for a in de_r1], ["RECEBE", "IGNORA"])
        self.assertTrue(all(a.secundario for a in de_r1))

    def test_a_camada_3_de_h1_escolhe_entrega_direta(self):
        roteia = next(a for a in self.visiveis if a.acao == "ROTEIA")
        self.assertTrue(roteia.entrega_direta)
        self.assertEqual(roteia.vizinho, "10.0.1.11")  # o próprio H2
        self.assertEqual(roteia.rota.prefixo, "10.0.1.0/24")

    def test_o_par_logico_e_o_da_rede_a(self):
        encapsula = next(a for a in self.visiveis if a.acao == "ENCAPSULA")
        self.assertEqual(
            (encapsula.logico.origem, encapsula.logico.destino),
            ("10.0.1.10", "10.0.1.11"),
        )

    def test_total_transmitido_de_92_octetos(self):
        transmitidos = [a.tamanho for a in self.visiveis if a.acao == "TRANSMITE"]
        self.assertEqual(transmitidos, [92])


class DescarteSemRotaEmC5(unittest.TestCase):
    """C5: H1 → 10.0.9.10. R1 não tem prefixo que case; o pacote morre na
    camada 3 e nenhum evento posterior existe."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.percurso = Percurso(cls.topo, "C5")
        cls.acoes = cls.percurso.executar()
        cls.visiveis = principais(cls.acoes)

    def test_o_registro_encerra_com_descarta_na_camada_3_de_r1(self):
        ultima = self.visiveis[-1]
        self.assertEqual(
            (ultima.dispositivo, ultima.camada, ultima.acao, ultima.estado),
            ("R1", 3, "DESCARTA", "descartado"),
        )
        self.assertEqual(ultima.tamanho, 74)  # o pacote descartado
        self.assertEqual(self.percurso.descartado_em, "R1")

    def test_um_unico_quadro_e_nenhum_q2(self):
        self.assertEqual(
            {a.quadro for a in self.acoes if a.quadro is not None}, {"Q1"}
        )

    def test_o_computador_nao_descarta_por_conta_propria(self):
        """Seção 6.3: a rota padrão casa qualquer destino, então H1 despacha
        para o gateway mesmo sabendo que 10.0.9.10 não existe."""
        roteia = next(a for a in self.visiveis
                      if a.dispositivo == "H1" and a.acao == "ROTEIA")
        self.assertFalse(roteia.entrega_direta)
        self.assertEqual(roteia.vizinho, "10.0.1.1")

    def test_total_transmitido_de_92_octetos(self):
        transmitidos = [a.tamanho for a in self.visiveis if a.acao == "TRANSMITE"]
        self.assertEqual(transmitidos, [92])


class SegmentacaoEmC7(unittest.TestCase):
    """C7: mensagem de 100 octetos, três segmentos, doze quadros, **uma
    única** linha de camada 4 no destino."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.acoes = Percurso(cls.topo, "C7").executar()
        cls.visiveis = principais(cls.acoes)

    def test_tres_segmenta_numerados_na_origem(self):
        segmentacoes = [a for a in self.visiveis if a.acao == "SEGMENTA"]
        self.assertEqual([(a.segmento.n, a.segmento.total) for a in segmentacoes],
                         [(1, 3), (2, 3), (3, 3)])
        self.assertEqual([a.tamanho for a in segmentacoes], [48, 48, 32])

    def test_doze_quadros_em_sequencia_continua(self):
        quadros = [a.quadro for a in self.visiveis if a.acao == "ENQUADRA"]
        self.assertEqual(quadros, [f"Q{n}" for n in range(1, 13)])

    def test_uma_unica_remonta_e_a_entrega_a_camada_5_vem_depois(self):
        no_destino = [a for a in self.visiveis if a.dispositivo == "H4"]
        camada_4 = [a for a in no_destino if a.camada == 4]
        self.assertEqual([a.acao for a in camada_4], ["REMONTA"])
        self.assertEqual(camada_4[0].tamanho, 104)

        acoes = [a.acao for a in no_destino]
        self.assertLess(acoes.index("REMONTA"), acoes.index("ENCERRA"))

    def test_a_mensagem_volta_inteira_com_100_octetos(self):
        entrega = next(a for a in self.visiveis if a.acao == "ENTREGA")
        self.assertEqual(entrega.tamanho, 100)


# --------------------------------------------------------------------------
# Tabelas e resoluções locais
# --------------------------------------------------------------------------


class TabelasDeEncaminhamento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.dispositivos = montar_dispositivos(cls.topo)

    def test_o_computador_tem_a_rede_local_e_a_rota_padrao(self):
        tabela = self.dispositivos["H1"].tabela_encaminhamento
        self.assertEqual(
            [(e.prefixo, e.proximo_salto, e.interface) for e in tabela],
            [("10.0.1.0/24", None, "eth0"), ("0.0.0.0/0", "10.0.1.1", "eth0")],
        )

    def test_a_tabela_do_roteador_e_a_da_secao_6_2(self):
        tabela = self.dispositivos["R1"].tabela_encaminhamento
        por_prefixo = {e.prefixo: e for e in tabela}
        self.assertIsNone(por_prefixo["10.0.1.0/24"].proximo_salto)  # conectada
        self.assertEqual(por_prefixo["10.0.1.0/24"].interface, "e0")
        self.assertEqual(por_prefixo["10.0.2.0/24"].proximo_salto, "10.0.12.2")
        self.assertEqual(por_prefixo["10.0.2.0/24"].interface, "e2")
        self.assertEqual(por_prefixo["10.0.2.0/24"].custo, 2)
        self.assertEqual(por_prefixo["10.0.3.0/24"].proximo_salto, "10.0.14.4")
        self.assertEqual(por_prefixo["10.0.3.0/24"].interface, "e1")
        self.assertEqual(por_prefixo["10.0.3.0/24"].custo, 2)

    def test_nenhuma_tabela_de_roteador_aponta_um_computador(self):
        """A correção herdada de F2 vista de dentro do dispositivo: o próximo
        salto de um roteador é sempre outro roteador."""
        hosts = {i.logico for d in self.topo.dispositivos if d.tipo == "computador"
                 for i in d.interfaces}
        for nome in ("R1", "R2", "R3", "R4"):
            for entrada in self.dispositivos[nome].tabela_encaminhamento:
                with self.subTest(roteador=nome, prefixo=entrada.prefixo):
                    self.assertNotIn(entrada.proximo_salto, hosts)

    def test_derrubar_o_enlace_recalcula_a_tabela_de_r1(self):
        """C4: `atualizar_topologia` refaz o Dijkstra — R1 passa a alcançar a
        Rede C por R2, a custo 3, pela interface e2."""
        r1 = self.dispositivos["R1"]
        antes = {e.prefixo: e for e in r1.tabela_encaminhamento}["10.0.3.0/24"]
        self.assertEqual((antes.interface, antes.custo), ("e1", 2))

        r1.atualizar_topologia(self.topo.com_enlace_ativo("E-R1-R4", ativo=False))
        depois = {e.prefixo: e for e in r1.tabela_encaminhamento}["10.0.3.0/24"]
        self.assertEqual((depois.interface, depois.custo), ("e2", 3))
        self.assertEqual(depois.proximo_salto, "10.0.12.2")

        r1.atualizar_topologia(self.topo)  # volta ao estado original

    def test_atualizar_topologia_propaga_a_todos_os_dispositivos(self):
        """Um só ponto de entrada refaz a tabela de toda a rede — é assim que
        o motor aplica o `enlace_fora` de C4."""
        dispositivos = montar_dispositivos(self.topo)
        atualizar_topologia(
            dispositivos.values(),
            self.topo.com_enlace_ativo("E-R1-R4", ativo=False),
        )

        def rota(nome: str, prefixo: str):
            tabela = dispositivos[nome].tabela_encaminhamento
            return next(e for e in tabela if e.prefixo == prefixo)

        # R1 desvia pela e2 (R2) a custo 3, e R4 responde pelo outro lado.
        self.assertEqual(rota("R1", "10.0.3.0/24").interface, "e2")
        self.assertEqual(rota("R1", "10.0.3.0/24").custo, 3)
        # R4 volta para a Rede A pelo caminho longo: R3 (1) + R2 (1) + R1 (2).
        self.assertEqual(rota("R4", "10.0.1.0/24").interface, "e1")
        self.assertEqual(rota("R4", "10.0.1.0/24").custo, 4)
        # Ninguém mais sai pela rede do enlace derrubado.
        for nome in ("R1", "R4"):
            for entrada in dispositivos[nome].tabela_encaminhamento:
                if entrada.prefixo == "10.0.14.0/24":
                    continue  # a rede do próprio enlace segue conectada
                with self.subTest(roteador=nome, prefixo=entrada.prefixo):
                    self.assertNotEqual(
                        (nome, entrada.interface), ("R1", "e1")
                    )
                    self.assertNotEqual(
                        (nome, entrada.interface), ("R4", "e0")
                    )

    def test_a_rota_de_c4_percorre_r1_r2_r3(self):
        topo = self.topo.com_enlace_ativo("E-R1-R4", ativo=False)
        acoes = Percurso(topo, "C4").executar()
        roteia = [a for a in principais(acoes) if a.acao == "ROTEIA"]
        self.assertEqual([a.dispositivo for a in roteia], ["H1", "R1", "R2", "R3"])
        self.assertEqual(roteia[1].rota.custo, 3)
        self.assertEqual(roteia[1].rota.interface, "e2")
        rotulos = {a.enlace.rotulo for a in acoes if a.acao == "TRANSMITE"}
        self.assertNotIn("R1–R4", rotulos)


class ResolucaoDeEnderecoFisico(unittest.TestCase):
    """O passo análogo a ARP, feito fora das camadas: a camada 2 recebe o par
    de MACs pronto (R4)."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.dispositivos = montar_dispositivos(cls.topo)

    def test_vizinho_desconhecido_no_enlace_e_erro_de_dispositivo(self):
        h1 = self.dispositivos["H1"]
        envio = h1.iniciar_envio(self.topo.caso("C2").fluxos[0])
        decisao = h1.encapsular(envio, envio.segmentos[0])
        with self.assertRaises(ErroDeDispositivo):
            h1.enquadrar(decisao.pacote, vizinho="10.0.1.99", interface_saida="eth0")

    def test_transmitir_por_enlace_derrubado_e_erro_de_dispositivo(self):
        """Nenhum quadro fantasma num enlace fora: a decisão velha vira erro
        em vez de linha no registro (C4)."""
        caido = self.topo.com_enlace_ativo("E-R1-R4", ativo=False)
        r1 = montar_dispositivos(self.topo)["R1"]  # tabela do estado anterior
        h1 = montar_dispositivos(self.topo)["H1"]
        envio = h1.iniciar_envio(self.topo.caso("C2").fluxos[0])
        decisao = h1.encapsular(envio, envio.segmentos[0])
        recepcao = montar_dispositivos(self.topo)["R1"].receber(
            h1.enquadrar(
                decisao.pacote,
                vizinho=decisao.vizinho,
                interface_saida=decisao.interface_saida,
            ).entrega_enderecada
        )
        r1.atualizar_topologia(caido)
        with self.assertRaises(ErroDeDispositivo):
            r1.enquadrar(recepcao.pacote, vizinho="10.0.14.4", interface_saida="e1")

    def test_interface_inexistente_e_erro_de_dispositivo(self):
        h1 = self.dispositivos["H1"]
        envio = h1.iniciar_envio(self.topo.caso("C2").fluxos[0])
        decisao = h1.encapsular(envio, envio.segmentos[0])
        with self.assertRaises(ErroDeDispositivo):
            h1.enquadrar(decisao.pacote, vizinho="10.0.1.1", interface_saida="eth9")


class ExtremosDeFluxo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()

    def test_destino_por_dispositivo(self):
        destino = self.topo.caso("C2").fluxos[0].destino
        self.assertEqual(logico_do_extremo(self.topo, destino), "10.0.3.10")

    def test_destino_so_por_endereco_como_em_c5(self):
        destino = self.topo.caso("C5").fluxos[0].destino
        self.assertIsNone(destino.dispositivo)
        self.assertEqual(logico_do_extremo(self.topo, destino), "10.0.9.10")


class OutraTopologia(unittest.TestCase):
    """Trocar o arquivo troca a rede simulada, sem alterar uma linha de
    código — as pilhas saem da topologia carregada, não de nomes fixos."""

    def test_a_topologia_alternativa_percorre_ponta_a_ponta(self):
        topo = carregar_topologia(fixture("topologia_alternativa.json"))
        caso = topo.casos[0]
        acoes = principais(Percurso(topo, caso.id).executar())
        self.assertEqual(acoes[0].acao, "GERA")
        self.assertEqual(acoes[-1].acao, "ENTREGA")
        dispositivos = [a.dispositivo for a in acoes]
        self.assertEqual(dispositivos[0], caso.fluxos[0].origem.dispositivo)
        self.assertEqual(dispositivos[-1], caso.fluxos[0].destino.dispositivo)

    def test_o_computador_do_meio_nunca_encaminha(self):
        """A topologia em que um host está no mesmo segmento que dois
        roteadores: o trajeto H1 → H2 passa por RA e RB, nunca por um host."""
        topo = carregar_topologia(fixture("topologia_computador_transito.json"))
        acoes = principais(Percurso(topo, "T1").executar())
        roteia = [(a.dispositivo, a.vizinho_nome) for a in acoes if a.acao == "ROTEIA"]
        self.assertEqual(roteia, [("H1", "RA"), ("RA", "RB"), ("RB", "H2")])


if __name__ == "__main__":
    unittest.main()
