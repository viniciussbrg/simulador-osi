"""Caso C7 — mensagem longa: segmentação e remontagem (issue #42).

A mensagem tem 100 octetos e chega à camada 4 com 104, já com o H5; o caso
declara `limite_segmento` 40 (convenção C2 do enunciado, seção 8.1 da
documentação), então a camada 4 da origem parte a mensagem em três e a do
destino a remonta. É o caso que separa duas coisas que os outros confundem,
porque neles coincidem: **a mensagem** e **a unidade que trafega**. Aqui uma
mensagem vira três pacotes, doze quadros e uma única entrega.

O que a seção 10/C7 cobra, e este arquivo prende:

- três `SEGMENTA` numerados `1 de 3`, `2 de 3`, `3 de 3`, com o corte 40+40+24
  visível nos tamanhos (48, 48 e 32 octetos, já com o H4 de 8);
- `Q1` a `Q12` em sequência contínua — o contador de quadros não reinicia a
  cada segmento (R2);
- **uma única** linha `REMONTA` em H4, e a entrega à camada 5 depois dela: a
  camada 4 não entrega nada enquanto faltar pedaço, e é por isso que H4 tem
  três `DESENCAPSULA` e uma só linha de camada 4;
- a travessia é sequencial (decisão D5): o segmento 2 só começa quando o 1
  chegou — não há entrelaçamento, que é o que distingue C7 de C3.

A contabilidade de referência (seção 4.7 do enunciado): cada segmento carrega
8 (L4) + 20 (L3) + 18 (L2) = 46 octetos de controle, dando quadros de 86, 86
e 70 — 242 por travessia, 968 nos quatro enlaces, η = 100/968 = 10,3%.

Executar:  python -m unittest tests.test_caso_c7
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

ROTA = ["H1", "R1", "R4", "R3"]  # quem enquadra, em cada travessia


class CasoC7(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C7")
        cls.registro = principais(cls.eventos)

    def acoes(self, acao: str, dispositivo: str | None = None):
        return [
            e for e in self.registro
            if e.acao == acao and (dispositivo is None or e.dispositivo == dispositivo)
        ]

    # -- as três linhas escritas por extenso na seção 10/C7 ----------------

    def test_a_mensagem_do_caso_tem_100_octetos(self):
        mensagem = self.topo.caso("C7").fluxos[0].mensagem
        self.assertEqual(len(mensagem.encode("utf-8")), 100)

    def test_tres_segmenta_numerados_de_1_a_3(self):
        """O corte 40+40+24 aparece nos tamanhos: 48, 48 e 32 octetos, cada um
        já com os 8 do cabeçalho H4."""
        segmenta = self.acoes("SEGMENTA", "H1")
        self.assertEqual(
            [(e.segmento.n, e.segmento.total) for e in segmenta],
            [(1, 3), (2, 3), (3, 3)],
        )
        self.assertEqual([e.tamanho for e in segmenta], [48, 48, 32])
        self.assertEqual(
            segmenta[0].descricao, "porta 5210 → 443, segmento 1 de 3"
        )

    def test_uma_unica_remonta_com_os_tres_segmentos(self):
        remonta = self.acoes("REMONTA", "H4")
        self.assertEqual(len(remonta), 1)
        self.assertEqual(remonta[0].descricao, "3 segmentos remontados em ordem")
        self.assertEqual(remonta[0].tamanho, 104)

    def test_a_entrega_a_camada_5_vem_depois_da_remontagem(self):
        """Ordem exigida pelo critério: enquanto faltar segmento, a subida para
        na camada 3 e nada chega à sessão."""
        remonta = self.acoes("REMONTA", "H4")[0]
        encerra = self.acoes("ENCERRA", "H4")[0]
        self.assertEqual(encerra.passo, remonta.passo + 1)
        self.assertEqual(encerra.tamanho, 100)

    # -- a camada 4 do destino só age quando a mensagem fecha --------------

    def test_h4_desencapsula_tres_vezes_e_sobe_uma_so(self):
        """Três pacotes chegam e são desencapsulados; a camada 4 emite uma
        única linha. É a diferença entre receber pedaço e receber mensagem."""
        por_acao = Counter(e.acao for e in self.registro if e.dispositivo == "H4")
        self.assertEqual(por_acao["DESENCAPSULA"], 3)
        self.assertEqual(por_acao["REMONTA"], 1)
        self.assertEqual(por_acao["ENTREGA"], 1)

    def test_nenhuma_linha_de_camada_5_ou_acima_antes_da_remontagem(self):
        remonta = self.acoes("REMONTA", "H4")[0]
        antes = [
            e for e in self.registro
            if e.dispositivo == "H4" and e.camada >= 5 and e.passo < remonta.passo
        ]
        self.assertEqual(antes, [])

    # -- quadros: numeração contínua e travessia sequencial ----------------

    def test_doze_quadros_em_sequencia_continua(self):
        enquadrados = [e.quadro for e in self.acoes("ENQUADRA")]
        self.assertEqual(enquadrados, [f"Q{n}" for n in range(1, 13)])

    def test_cada_segmento_atravessa_a_rota_inteira_antes_do_seguinte(self):
        """Decisão D5: registro sequencial, não intercalado — é o que separa
        C7 de C3. Se os segmentos viajassem entrelaçados, a sequência de quem
        enquadra não seria a rota repetida três vezes."""
        self.assertEqual(
            [e.dispositivo for e in self.acoes("ENQUADRA")], ROTA * 3
        )

    def test_tamanho_dos_quadros_por_segmento(self):
        """86, 86 e 70: os dois primeiros segmentos levam 40 octetos de
        dados, o último 24 (seção 4.7 do enunciado)."""
        tamanhos = [e.tamanho for e in self.acoes("ENQUADRA")]
        self.assertEqual(tamanhos, [86] * 8 + [70] * 4)

    def test_total_transmitido_de_968_octetos(self):
        transmitidos = [e.tamanho for e in self.eventos if e.acao == "TRANSMITE"]
        self.assertEqual(len(transmitidos), 12)
        self.assertEqual(sum(transmitidos), 968)

    def test_um_unico_par_logico_e_uma_unica_sessao(self):
        """Três pacotes, mas uma conversa só: o par lógico é gravado uma vez na
        origem (R3) e a sessão é aberta e encerrada uma vez."""
        pares = {(e.logico.origem, e.logico.destino) for e in self.eventos if e.logico}
        self.assertEqual(pares, {("10.0.1.10", "10.0.3.10")})
        self.assertEqual(len(self.acoes("ABRE", "H1")), 1)
        self.assertEqual(len(self.acoes("ENCERRA", "H4")), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
