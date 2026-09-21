"""Caso C3 — demultiplexação: dois fluxos concorrentes para o mesmo destino
(issue #39).

C3 é o único caso em que duas conversas disputam a mesma máquina ao mesmo
tempo, e é dele que sai a diferença entre *entrega origem-destino* e *entrega
processo a processo*: os dois pacotes chegam a H4 com o mesmo par lógico de
destino e o mesmo processo servidor; o que os separa é a **porta de origem**
(5210 e 5311), e é a camada 4 que faz essa separação — a ação `DEMULTIPLEXA`.

Duas coisas precisam ser verdade ao mesmo tempo, e nenhuma das duas basta
sozinha:

- **a intercalação é real** — o campo `fluxo` alterna ao longo do registro
  porque a fila ordena por `(instante, ordem_de_inserção)` e cada fluxo começa
  no instante zero (issue #28). Rodar F1 inteiro, depois F2 inteiro, e rotular
  os eventos depois produziria o mesmo conjunto de linhas na ordem errada —
  é o que a issue proíbe explicitamente;
- **cada fluxo continua íntegro** — intercalar não pode embaralhar a ordem das
  camadas dentro de um fluxo: visto isoladamente, cada um tem de ser o mesmo
  percurso de C2.

Executar:  python -m unittest tests.test_caso_c3
"""

import os
import sys
import unittest
from collections import Counter

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais


class CasoC3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C3")
        cls.registro = principais(cls.eventos)

    def do_fluxo(self, fluxo: str):
        return [e for e in self.registro if e.fluxo == fluxo]

    # -- critério de aceitação da seção 10/C3 ------------------------------

    def test_h4_emite_duas_linhas_demultiplexa(self):
        """As duas linhas escritas por extenso na seção 10/C3, com a porta de
        origem e a sessão de destino de cada conversa."""
        linhas = [
            e for e in self.registro
            if e.acao == "DEMULTIPLEXA" and e.dispositivo == "H4"
        ]
        self.assertEqual(len(linhas), 2)
        self.assertEqual(
            [e.descricao for e in linhas],
            [
                "porta origem 5210 → sessão S-0001",
                "porta origem 5311 → sessão S-0002",
            ],
        )
        for linha in linhas:
            self.assertEqual(linha.camada, 4)
            # 46 B: a ação de subida registra a PDU **depois** de remover o
            # H4, como DESENQUADRA (74) e DESENCAPSULA (54) nas suas. É a
            # mesma posição que o Anexo B ocupa com `REMONTA | ... 46 B`.
            self.assertEqual(linha.tamanho, 46)

    def test_nenhuma_linha_remonta_em_c3(self):
        """Com dois fluxos concorrentes, a camada 4 de H4 demultiplexa; não há
        mensagem partida a remontar (isso é C7)."""
        self.assertEqual([e.acao for e in self.registro].count("REMONTA"), 0)

    def test_as_duas_sessoes_sao_distintas(self):
        sessoes = {e.sessao for e in self.registro if e.sessao}
        self.assertEqual(sessoes, {"S-0001", "S-0002"})

    def test_o_campo_fluxo_alterna_ao_longo_do_registro(self):
        """O que distingue intercalação real de dois blocos rotulados: existe
        evento de F1 **depois** de evento de F2."""
        fluxos = [e.fluxo for e in self.registro]
        primeiro_f2 = fluxos.index("F2")
        self.assertIn("F1", fluxos[primeiro_f2:])

    def test_a_alternancia_acontece_a_cada_salto(self):
        """Nove trocas de fluxo: a descida alta de cada origem e os quatro
        saltos de cada fluxo se alternam em blocos, não em duas metades."""
        fluxos = [e.fluxo for e in self.registro]
        trocas = sum(1 for a, b in zip(fluxos, fluxos[1:]) if a != b)
        self.assertGreaterEqual(trocas, 9)

    # -- cada fluxo, visto sozinho, é o percurso de C2 ---------------------

    def test_cada_fluxo_isolado_tem_o_percurso_completo(self):
        for fluxo, origem, porta in (("F1", "H1", 5210), ("F2", "H2", 5311)):
            with self.subTest(fluxo=fluxo):
                eventos = self.do_fluxo(fluxo)
                self.assertEqual(eventos[0].acao, "GERA")
                self.assertEqual(eventos[0].dispositivo, origem)
                self.assertEqual(eventos[-1].acao, "ENTREGA")
                self.assertEqual(eventos[-1].dispositivo, "H4")
                segmenta = next(e for e in eventos if e.acao == "SEGMENTA")
                self.assertEqual(segmenta.porta.origem, porta)

    def test_cada_fluxo_percorre_os_quatro_enlaces_da_rota_de_c2(self):
        for fluxo in ("F1", "F2"):
            with self.subTest(fluxo=fluxo):
                eventos = self.do_fluxo(fluxo)
                enquadrados = [e.quadro for e in eventos if e.acao == "ENQUADRA"]
                self.assertEqual(len(enquadrados), 4)
                self.assertEqual(len(set(enquadrados)), 4)

    # -- totais do caso ----------------------------------------------------

    def test_oito_quadros_distintos_no_caso_inteiro(self):
        enquadrados = [e.quadro for e in self.eventos if e.acao == "ENQUADRA"]
        self.assertEqual(len(enquadrados), 8)
        self.assertEqual(len(set(enquadrados)), 8)

    def test_cada_fluxo_recebe_quatro_identificadores_contiguos(self):
        """F1 fica com Q1–Q4 e F2 com Q5–Q8, e não alternados.

        O identificador vem do contador global na **ordem de criação**, e a
        criação continua acontecendo fluxo a fluxo — o que a intercalação muda
        é a ordem do registro, não a ordem em que as camadas agem. O efeito
        visível é que os identificadores aparecem fora de ordem numérica no
        registro (Q1, Q5, Q2, Q6, …): cada um está no instante lógico do seu
        próprio fluxo. Numerá-los na ordem do registro exigiria executar os
        dois fluxos em lockstep, salto a salto, e R2 pede ordem de criação,
        não ordem de exibição."""
        por_fluxo = {
            fluxo: [e.quadro for e in self.do_fluxo(fluxo) if e.acao == "ENQUADRA"]
            for fluxo in ("F1", "F2")
        }
        self.assertEqual(por_fluxo["F1"], ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(por_fluxo["F2"], ["Q5", "Q6", "Q7", "Q8"])

    def test_duas_entregas_e_duas_sessoes_abertas(self):
        acoes = Counter(e.acao for e in self.registro)
        self.assertEqual(acoes["GERA"], 2)
        self.assertEqual(acoes["ABRE"], 2)
        self.assertEqual(acoes["ENCERRA"], 2)
        self.assertEqual(acoes["ENTREGA"], 2)

    def test_total_transmitido_de_736_octetos(self):
        """736 B = 8 quadros × 92 B, o total da tabela 11.3 para C3."""
        transmitidos = [e.tamanho for e in self.eventos if e.acao == "TRANSMITE"]
        self.assertEqual(len(transmitidos), 8)
        self.assertEqual(sum(transmitidos), 736)

    def test_passos_contiguos_no_registro_padrao(self):
        self.assertEqual(
            [e.passo for e in self.registro], list(range(1, len(self.registro) + 1))
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
