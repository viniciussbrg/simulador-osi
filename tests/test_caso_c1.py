"""Caso C1 — entrega direta, H1 → H2 na mesma rede (issue #29).

O primeiro caso a rodar de ponta a ponta no motor: `executar_caso` empurra a
mensagem pela pilha de H1, pelo segmento de difusão da Rede A e pela pilha de
H2, devolvendo o registro pronto — sem tkinter e sem o encadeador de teste.

O que a seção 10/C1 cobra, e este arquivo prende:

- **exatamente uma** ocorrência de `ENQUADRA` — um enlace, um quadro;
- **nenhuma linha de roteador** no registro padrão, embora R1 esteja no mesmo
  segmento de difusão e receba o quadro fisicamente: ele o descarta por endereço
  (`IGNORA`), evento secundário, que fica oculto;
- as linhas 005 e 006, que registram a decisão de entrega direta da camada 3 de
  H1 — o ramo da seção 6.3 em que a rede local (/24) vence a rota padrão e o
  próximo salto é o próprio destino.

T-C1 (issue #44) acrescenta a conferência das métricas (92 B transmitidos,
η = 45,7%) quando o evento `METRICAS` existir, em F4.

Executar:  python -m unittest tests.test_caso_c1
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais


def assinatura(eventos) -> list[tuple]:
    return [(e.dispositivo, e.camada, e.acao, e.tamanho) for e in eventos]


# O evento `METRICAS` fecha toda execução (issue #43): é de sistema, camada 0,
# sem fluxo. Os testes abaixo falam do percurso da mensagem, então olham o
# último evento **de camada** — `desfecho` — em vez do último da lista.

def desfecho(eventos):
    """O último evento de camada do registro, ignorando o `METRICAS` final."""
    return next(e for e in reversed(eventos) if e.camada > 0)


class CasoC1(unittest.TestCase):
    """O registro inteiro de C1, executado uma vez para a classe — a execução é
    determinística e nenhum teste a altera."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C1")
        cls.registro = principais(cls.eventos)

    def linha_de(self, passo: int):
        return next(e for e in self.registro if e.passo == passo)

    # -- critério de aceitação da seção 10/C1 ------------------------------

    def test_um_unico_enquadra(self):
        """Um enlace, um quadro: nada reenquadra a mensagem, porque não há salto
        nenhum entre H1 e H2."""
        enquadra = [e for e in self.eventos if e.acao == "ENQUADRA"]
        self.assertEqual(len(enquadra), 1)
        self.assertEqual(enquadra[0].quadro, "Q1")

    def test_nenhuma_linha_de_roteador_no_registro(self):
        """R1 está no segmento de difusão da Rede A e recebe o quadro, mas
        nenhuma linha do registro padrão é dele."""
        roteadores = {d.nome for d in self.topo.dispositivos if d.tipo == "roteador"}
        for evento in self.registro:
            self.assertNotIn(evento.dispositivo, roteadores, evento.linha())

    def test_a_camada_3_de_h1_registra_entrega_direta(self):
        """As duas linhas que a seção 10/C1 escreve por extenso."""
        encapsula, roteia = self.linha_de(5), self.linha_de(6)
        self.assertEqual(
            (encapsula.dispositivo, encapsula.camada, encapsula.acao,
             encapsula.descricao, encapsula.tamanho),
            ("H1", 3, "ENCAPSULA", "10.0.1.10 → 10.0.1.11", 74),
        )
        self.assertEqual(
            (roteia.dispositivo, roteia.camada, roteia.acao,
             roteia.descricao, roteia.tamanho),
            ("H1", 3, "ROTEIA", "destino na mesma rede, entrega direta", 74),
        )

    def test_o_proximo_salto_e_o_proprio_destino(self):
        """Entrega direta não é só o texto da linha: o quadro que sai em seguida
        é endereçado ao MAC de H2, não ao do gateway."""
        enquadra = next(e for e in self.registro if e.acao == "ENQUADRA")
        h2 = self.topo.dispositivo("H2").interfaces[0]
        self.assertEqual(enquadra.fisico.destino, h2.fisico)
        self.assertEqual(enquadra.logico.destino, h2.logico)

    # -- percurso ----------------------------------------------------------

    def test_a_sequencia_de_acoes_e_a_de_uma_entrega_direta(self):
        self.assertEqual(
            assinatura(self.registro),
            [
                ("H1", 7, "GERA", 42),
                ("H1", 6, "CODIFICA", 42),
                ("H1", 5, "ABRE", 46),
                ("H1", 4, "SEGMENTA", 54),
                ("H1", 3, "ENCAPSULA", 74),
                ("H1", 3, "ROTEIA", 74),
                ("H1", 2, "ENQUADRA", 92),
                ("H1", 1, "TRANSMITE", 92),
                ("H2", 1, "RECEBE", 92),
                ("H2", 2, "DESENQUADRA", 74),
                ("H2", 3, "DESENCAPSULA", 54),
                ("H2", 4, "REMONTA", 46),
                ("H2", 5, "ENCERRA", 42),
                ("H2", 6, "DECIFRA", 42),
                ("H2", 7, "ENTREGA", 42),
                ("--", 0, "METRICAS", None),
            ],
        )

    def test_um_pacote_um_segmento_um_enlace(self):
        self.assertEqual(len([e for e in self.registro if e.acao == "SEGMENTA"]), 1)
        self.assertEqual(len([e for e in self.registro if e.acao == "ENCAPSULA"]), 1)
        self.assertEqual({e.quadro for e in self.eventos if e.quadro}, {"Q1"})
        self.assertEqual(desfecho(self.registro).caminho, ("E-A",))

    def test_o_total_transmitido_e_92_octetos(self):
        """Um único quadro de 92 B no ar — o valor da tabela 11.3 para C1."""
        transmitido = sum(e.tamanho for e in self.eventos if e.acao == "TRANSMITE")
        self.assertEqual(transmitido, 92)

    def test_os_736_bits_do_quadro(self):
        transmite = next(e for e in self.registro if e.acao == "TRANSMITE")
        self.assertEqual(transmite.bits, 92 * 8)
        self.assertEqual(transmite.descricao, "736 bits no enlace H1–H2")

    def test_a_mensagem_chega_inteira_ao_processo_de_destino(self):
        entrega = desfecho(self.registro)
        self.assertEqual(entrega.acao, "ENTREGA")
        self.assertEqual(entrega.processo.destino, "servidorWeb")
        self.assertEqual(
            entrega.pdu.blocos[0].conteudo, self.topo.caso("C1").fluxos[0].mensagem
        )

    # -- difusão: R1 recebe e ignora --------------------------------------

    def test_r1_recebe_pelo_segmento_e_ignora_por_endereco(self):
        """O comportamento existe, só não aparece: os dois eventos de R1 são
        secundários (seção 7.5)."""
        de_r1 = [e for e in self.eventos if e.dispositivo == "R1"]
        self.assertEqual(
            [(e.camada, e.acao, e.secundario) for e in de_r1],
            [(1, "RECEBE", True), (2, "IGNORA", True)],
        )
        self.assertEqual(de_r1[1].estado, "descartado")
        self.assertEqual(de_r1[1].quadro, "Q1")

    def test_o_ignora_de_r1_acompanha_o_transmite_de_h1(self):
        """Evento secundário não consome passo: R1 ignora o quadro no mesmo
        passo em que H1 o transmite, e a numeração do registro segue sem
        buraco."""
        transmite = next(e for e in self.registro if e.acao == "TRANSMITE")
        for evento in (e for e in self.eventos if e.secundario):
            self.assertEqual(evento.passo, transmite.passo)
        self.assertEqual(
            [e.passo for e in self.registro], list(range(1, len(self.registro) + 1))
        )

    def test_nenhum_evento_de_roteador_traz_contexto_superior(self):
        """R1 age em C1, ainda que só para descartar — e continua sem porta,
        sessão, segmento ou processo (R1)."""
        for evento in (e for e in self.eventos if e.dispositivo == "R1"):
            self.assertIsNone(evento.porta)
            self.assertIsNone(evento.sessao)
            self.assertIsNone(evento.segmento)
            self.assertIsNone(evento.processo)

    # -- determinismo ------------------------------------------------------

    def test_duas_execucoes_produzem_o_mesmo_registro(self):
        """Mesma topologia, mesmo caso, mesmo registro — inclusive o
        identificador do quadro e o da sessão, que vêm de contadores globais
        reiniciados a cada execução."""
        outra = executar_caso(carregar_topologia(), "C1")
        self.assertEqual([e.linha() for e in outra], [e.linha() for e in self.eventos])

    def test_todo_evento_pertence_ao_fluxo_f1(self):
        """Um fluxo só, e todo evento de camada o carrega. O `METRICAS` final
        não: ele resume a execução inteira, não um fluxo (mesma razão do
        `ENLACE_FORA` de C4)."""
        for evento in self.eventos:
            if evento.camada == 0:
                self.assertIsNone(evento.fluxo, evento.linha())
                continue
            self.assertEqual(evento.fluxo, "F1")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
