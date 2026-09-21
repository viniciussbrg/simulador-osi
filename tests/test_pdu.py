"""T-PDU — invariante de tamanho da PDU (issue #14).

Verifica, para todo evento produzido, que a soma dos `tam` dos blocos da PDU
é igual ao campo `tamanho` do evento (proposta técnica, seções 3.2 e 13.3).

Os eventos vêm do **motor** (`simulador.executar_caso`), fechado em F3: é o
que o programa realmente produz, e é sobre ele que a invariante precisa valer.
Antes de F3 a fonte era o encadeador de F1 (`tests/encadeamento.py`), que
segue existindo como oráculo isolado daquela fase — as asserções não mudaram
na troca, e os dois concordam evento a evento em C1, C2 e C7.

Executar:  python -m unittest tests.test_pdu
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais

_TOPOLOGIA = carregar_topologia()


def eventos_do_caso(caso: str) -> tuple:
    """O registro padrão do caso, direto do motor.

    Sem os secundários, para que as sequências de referência abaixo continuem
    sendo as do registro que o usuário lê (seção 7.5). A invariante sobre o
    registro **completo**, secundários inclusive, tem teste próprio — é o que
    a troca do encadeador pelo motor acrescenta: o encadeador de F1 não emitia
    evento secundário nenhum."""
    return principais(executar_caso(_TOPOLOGIA, caso))


def eventos_completos(caso: str) -> tuple:
    """Tudo o que a execução produziu, inclusive as estações de difusão que
    receberam o quadro e o ignoraram por endereço."""
    return executar_caso(_TOPOLOGIA, caso)

# Casos exigidos pelo critério de aceitação da issue: C1, C2 e C7 (este último
# cobre a PDU dividida em várias instâncias simultâneas — segmentação/remontagem).
CASOS = ("C1", "C2", "C7")

# Progressão de tamanhos da descida na origem para uma mensagem de 42 B —
# linhas 001–008 do Anexo B / tabela da seção 3.2. É a referência fixa: se a
# implementação produzir outros números, há erro de contabilidade em alguma
# camada.
PROGRESSAO_DESCIDA_42B = [
    ("GERA", 42),
    ("CODIFICA", 42),
    ("ABRE", 46),
    ("SEGMENTA", 54),
    ("ENCAPSULA", 74),
    ("ROTEIA", 74),
    ("ENQUADRA", 92),
    ("TRANSMITE", 92),
]


class TestInvarianteTamanhoPDU(unittest.TestCase):
    """Σ(bloco.tam) == evento.tamanho, para todo evento com PDU."""

    def test_soma_dos_blocos_igual_ao_tamanho(self):
        for caso in CASOS:
            with self.subTest(caso=caso):
                eventos = eventos_do_caso(caso)
                self.assertTrue(eventos, f"{caso}: nenhum evento produzido")

                divergentes = []
                for ev in eventos:
                    if ev.pdu is None:  # eventos de sistema (camada 0) não têm PDU
                        continue
                    soma = sum(bloco.tam for bloco in ev.pdu.blocos)
                    if soma != ev.tamanho:
                        blocos = ", ".join(f"{b.rotulo}={b.tam}" for b in ev.pdu.blocos)
                        divergentes.append(
                            f"passo {ev.passo:03d} | {ev.dispositivo} L{ev.camada} "
                            f"{ev.acao}: soma dos blocos={soma} != tamanho={ev.tamanho}  [{blocos}]"
                        )

                if divergentes:
                    self.fail(
                        f"T-PDU violado em {caso} ({len(divergentes)} evento(s)):\n  "
                        + "\n  ".join(divergentes)
                    )

    def test_todo_evento_com_pdu_tem_tamanho(self):
        # Corolário: nenhum evento de camada 1–7 fica sem `tamanho` (só os de
        # sistema, camada 0, podem — e esses não têm PDU).
        for caso in CASOS:
            with self.subTest(caso=caso):
                for ev in eventos_do_caso(caso):
                    if ev.camada == 0:
                        continue
                    self.assertIsNotNone(
                        ev.tamanho,
                        f"{caso} passo {ev.passo:03d} ({ev.acao}) sem tamanho",
                    )
                    self.assertIsNotNone(
                        ev.pdu,
                        f"{caso} passo {ev.passo:03d} ({ev.acao}) sem PDU",
                    )


class TestProgressaoDeTamanhos(unittest.TestCase):
    """A invariante só tem valor se os tamanhos batem com a referência escrita.
    Aqui as progressões são comparadas contra o Anexo B e a seção 11."""

    def test_descida_na_origem_c2(self):
        h1_desce = [
            (ev.acao, ev.tamanho)
            for ev in eventos_do_caso("C2")
            if ev.dispositivo == "H1" and ev.sentido == "desce"
        ]
        self.assertEqual(h1_desce, PROGRESSAO_DESCIDA_42B)

    def test_descida_na_origem_c1(self):
        h1_desce = [
            (ev.acao, ev.tamanho)
            for ev in eventos_do_caso("C1")
            if ev.dispositivo == "H1" and ev.sentido == "desce"
        ]
        self.assertEqual(h1_desce, PROGRESSAO_DESCIDA_42B)

    def test_c2_progressao_completa_de_tamanhos(self):
        # (dispositivo, camada, ação, tamanho) das 30 linhas de camada do
        # Anexo B — a coluna de octetos ponta a ponta. O texto exato de cada
        # descrição é escopo de T-FMT (issue #34); aqui só o tamanho.
        esperado = [
            ("H1", 7, "GERA", 42), ("H1", 6, "CODIFICA", 42), ("H1", 5, "ABRE", 46),
            ("H1", 4, "SEGMENTA", 54), ("H1", 3, "ENCAPSULA", 74), ("H1", 3, "ROTEIA", 74),
            ("H1", 2, "ENQUADRA", 92), ("H1", 1, "TRANSMITE", 92),
            ("R1", 1, "RECEBE", 92), ("R1", 2, "DESENQUADRA", 74), ("R1", 3, "ROTEIA", 74),
            ("R1", 2, "ENQUADRA", 92), ("R1", 1, "TRANSMITE", 92),
            ("R4", 1, "RECEBE", 92), ("R4", 2, "DESENQUADRA", 74), ("R4", 3, "ROTEIA", 74),
            ("R4", 2, "ENQUADRA", 92), ("R4", 1, "TRANSMITE", 92),
            ("R3", 1, "RECEBE", 92), ("R3", 2, "DESENQUADRA", 74), ("R3", 3, "ROTEIA", 74),
            ("R3", 2, "ENQUADRA", 92), ("R3", 1, "TRANSMITE", 92),
            ("H4", 1, "RECEBE", 92), ("H4", 2, "DESENQUADRA", 74), ("H4", 3, "DESENCAPSULA", 54),
            ("H4", 4, "REMONTA", 46), ("H4", 5, "ENCERRA", 42), ("H4", 6, "DECIFRA", 42),
            ("H4", 7, "ENTREGA", 42),
            ("--", 0, "METRICAS", None),
        ]
        obtido = [(ev.dispositivo, ev.camada, ev.acao, ev.tamanho) for ev in eventos_do_caso("C2")]
        self.assertEqual(obtido, esperado)

    def test_c1_transmite_um_unico_quadro_de_92_B(self):
        eventos = eventos_do_caso("C1")
        quadros = [ev.quadro for ev in eventos if ev.acao == "ENQUADRA"]
        self.assertEqual(quadros, ["Q1"])
        transmitidos = [ev.tamanho for ev in eventos if ev.acao == "TRANSMITE"]
        self.assertEqual(transmitidos, [92])  # total transmitido de C1 (tabela 11.3)

    def test_c2_quatro_quadros_distintos_de_92_B(self):
        eventos = eventos_do_caso("C2")
        quadros = [ev.quadro for ev in eventos if ev.acao == "ENQUADRA"]
        self.assertEqual(quadros, ["Q1", "Q2", "Q3", "Q4"])
        transmitidos = [ev.tamanho for ev in eventos if ev.acao == "TRANSMITE"]
        self.assertEqual(transmitidos, [92, 92, 92, 92])
        self.assertEqual(sum(transmitidos), 368)  # tabela 11.3

    def test_c7_tres_segmentos_e_doze_quadros(self):
        eventos = eventos_do_caso("C7")

        segmentacoes = [ev.tamanho for ev in eventos if ev.acao == "SEGMENTA"]
        self.assertEqual(segmentacoes, [48, 48, 32])  # 40/40/24 de dados + H4

        quadros = [ev.quadro for ev in eventos if ev.acao == "ENQUADRA"]
        self.assertEqual(quadros, [f"Q{i}" for i in range(1, 13)])

        # Quadros de 86, 86 e 70 octetos, um tamanho por segmento (seção 4.7).
        tam_por_quadro = {
            ev.quadro: ev.tamanho for ev in eventos if ev.acao == "ENQUADRA"
        }
        self.assertEqual([tam_por_quadro[f"Q{i}"] for i in range(1, 5)], [86, 86, 86, 86])
        self.assertEqual([tam_por_quadro[f"Q{i}"] for i in range(5, 9)], [86, 86, 86, 86])
        self.assertEqual([tam_por_quadro[f"Q{i}"] for i in range(9, 13)], [70, 70, 70, 70])

        transmitidos = [ev.tamanho for ev in eventos if ev.acao == "TRANSMITE"]
        self.assertEqual(sum(transmitidos), 968)  # secao 4.7 do enunciado

        remontagens = [ev for ev in eventos if ev.acao == "REMONTA"]
        self.assertEqual(len(remontagens), 1, "C7 emite uma única linha REMONTA (D5)")
        self.assertEqual(remontagens[0].tamanho, 104)
        entregas = [ev.tamanho for ev in eventos if ev.acao == "ENTREGA"]
        self.assertEqual(entregas, [100])  # mensagem original recuperada inteira


class TestCamadaFisicaEmBits(unittest.TestCase):
    """A L1 é a única a converter octetos em bits (× 8). O `tamanho` do evento
    permanece em octetos e continua batendo com a soma dos blocos."""

    def test_bits_sao_octetos_vezes_oito(self):
        for caso in CASOS:
            with self.subTest(caso=caso):
                for ev in eventos_do_caso(caso):
                    if ev.camada != 1:
                        continue
                    self.assertEqual(ev.bits, ev.tamanho * 8)
                    self.assertEqual(ev.bits, sum(b.tam for b in ev.pdu.blocos) * 8)

    def test_c2_quadro_de_92_B_da_736_bits(self):
        # Linha 008 do Anexo B: verificação de referência 92 × 8 = 736.
        bits = {ev.bits for ev in eventos_do_caso("C2") if ev.camada == 1}
        self.assertEqual(bits, {736})


class InvarianteNosEventosSecundarios(unittest.TestCase):
    """O que a migração do encadeador para o motor acrescenta.

    As estações alheias de um segmento de difusão recebem o quadro e o
    descartam por endereço (`RECEBE`/`IGNORA`, secundários). Esses eventos não
    existiam no encadeador de F1 e carregam PDU como qualquer outro: se a
    cópia recebida fosse montada com blocos de outro tamanho, só aqui
    apareceria."""

    def test_secundarios_existem_e_respeitam_a_invariante(self):
        for caso in CASOS:
            with self.subTest(caso=caso):
                secundarios = [
                    ev for ev in eventos_completos(caso) if ev.secundario
                ]
                self.assertTrue(secundarios, f"{caso}: nenhum evento secundário")
                for ev in secundarios:
                    if ev.pdu is None or ev.tamanho is None:
                        continue
                    self.assertEqual(
                        sum(b.tam for b in ev.pdu.blocos),
                        ev.tamanho,
                        f"{caso}: blocos e tamanho divergem em {ev.linha()}",
                    )


if __name__ == "__main__":
    unittest.main()
