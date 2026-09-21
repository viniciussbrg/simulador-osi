"""Caso C6 — erro de transmissão detectado pelo CRC-32 (issue #41).

C6 é C2 com um bit trocado no meio do caminho: o mesmo fluxo H1 → H4, a mesma
rota, até que o quadro Q3 atravessa o enlace R4–R3 com o bit 100 invertido. O
CRC-32 recalculado em R3 diverge do finalizador recebido, e o quadro morre ali.

É o caso que mostra o que a camada de enlace faz de verdade: ela não conserta
nem pede retransmissão — **detecta e descarta**. A consequência é o critério
mais severo da seção 10/C6, e o que este arquivo mais persegue: depois do
descarte, **nenhum evento de camada 3 ou superior existe**. O pacote nunca é
desencapsulado, H4 nunca recebe nada, a mensagem simplesmente não chega.

Executar:  python -m unittest tests.test_caso_c6
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais


# O evento `METRICAS` fecha toda execução (issue #43): é de sistema, camada 0,
# sem fluxo. Os testes abaixo falam do percurso da mensagem, então olham o
# último evento **de camada** — `desfecho` — em vez do último da lista.

def desfecho(eventos):
    """O último evento de camada do registro, ignorando o `METRICAS` final."""
    return next(e for e in reversed(eventos) if e.camada > 0)


class CasoC6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C6")
        cls.registro = principais(cls.eventos)

    def unico(self, acao: str):
        achados = [e for e in self.registro if e.acao == acao]
        self.assertEqual(len(achados), 1, f"esperava um só {acao}")
        return achados[0]

    # -- as três linhas escritas por extenso na seção 10/C6 ----------------

    def test_a_injecao_e_narrada_antes_da_recepcao(self):
        corrompe = self.unico("CORROMPE")
        self.assertEqual(corrompe.camada, 0)
        self.assertEqual(corrompe.dispositivo, "--")
        self.assertEqual(
            corrompe.descricao, "bit 100 invertido no enlace R4–R3, quadro Q3"
        )
        self.assertIsNone(corrompe.tamanho)

        recebe = next(
            e for e in self.registro
            if e.dispositivo == "R3" and e.acao == "RECEBE"
        )
        self.assertEqual(corrompe.passo + 1, recebe.passo)
        self.assertEqual(recebe.tamanho, 92)

    def test_r3_descarta_na_camada_2(self):
        descarta = self.unico("DESCARTA")
        self.assertEqual(descarta.dispositivo, "R3")
        self.assertEqual(descarta.camada, 2)
        self.assertEqual(
            descarta.descricao,
            "verificação de erro incorreta, quadro Q3 descartado",
        )
        self.assertEqual(descarta.estado, "erro")
        # Nada foi extraído do quadro: a linha não traz sufixo de octetos.
        self.assertIsNone(descarta.tamanho)

    def test_o_descarte_e_o_ultimo_evento_do_registro(self):
        self.assertEqual(desfecho(self.registro).acao, "DESCARTA")

    # -- o critério mais severo: nada acontece depois ----------------------

    def test_nenhum_evento_de_camada_3_ou_acima_depois_do_descarte(self):
        descarta = self.unico("DESCARTA")
        posteriores = [
            e for e in self.eventos if e.passo > descarta.passo and e.camada >= 3
        ]
        self.assertEqual(posteriores, [])

    def test_h4_nunca_recebe_nada(self):
        """O destino não aparece no registro: a mensagem não chegou."""
        self.assertNotIn("H4", {e.dispositivo for e in self.eventos})

    def test_nenhum_desencapsula_acontece_em_r3(self):
        """O quadro é destruído na camada 2; a camada 3 de R3 não é acionada."""
        de_r3 = [(e.camada, e.acao) for e in self.registro if e.dispositivo == "R3"]
        self.assertEqual(de_r3, [(1, "RECEBE"), (2, "DESCARTA")])

    # -- os saltos anteriores acontecem normalmente -----------------------

    def test_os_dois_primeiros_quadros_atravessam_intactos(self):
        """A injeção é de um enlace só: Q1 e Q2 são desenquadrados sem erro."""
        desenquadrados = [e.quadro for e in self.registro if e.acao == "DESENQUADRA"]
        self.assertEqual(desenquadrados, ["Q1", "Q2"])

    def test_tres_enlaces_percorridos_e_276_octetos_transmitidos(self):
        """3 quadros × 92 B: o quarto salto nunca acontece (tabela 11.3)."""
        transmitidos = [e.tamanho for e in self.eventos if e.acao == "TRANSMITE"]
        self.assertEqual(len(transmitidos), 3)
        self.assertEqual(sum(transmitidos), 276)
        self.assertEqual(
            desfecho(self.registro).caminho, ("E-A", "E-R1-R4", "E-R4-R3")
        )

    def test_tres_quadros_construidos(self):
        enquadrados = [e.quadro for e in self.eventos if e.acao == "ENQUADRA"]
        self.assertEqual(enquadrados, ["Q1", "Q2", "Q3"])


class InjecaoAtingeUmQuadroSo(unittest.TestCase):
    """A injeção nomeia **um** quadro, não um enlace.

    C6 sozinho não distingue as duas coisas: o enlace R4–R3 é atravessado uma
    vez só, então "corromper Q3" e "corromper tudo que passa por ali" dão o
    mesmo registro. C7 atravessa o mesmo enlace três vezes, uma por segmento —
    é o caso que separa as duas leituras, e por isso o teste monta um caso
    derivado dele, com o erro declarado no quadro do **segundo** segmento."""

    @classmethod
    def setUpClass(cls):
        from dataclasses import replace

        from rede import EventoExterno

        topo = carregar_topologia()
        derivado = replace(
            topo.caso("C7"),
            id="C7-ERRO",
            eventos_externos=(
                EventoExterno(
                    tipo="erro_bit", enlace="E-R4-R3", quadro="Q7", bit=100
                ),
            ),
        )
        cls.registro = principais(
            executar_caso(replace(topo, casos=topo.casos + (derivado,)), "C7-ERRO")
        )

    def test_so_o_quadro_declarado_e_corrompido(self):
        corrompidos = [e for e in self.registro if e.acao == "CORROMPE"]
        self.assertEqual(len(corrompidos), 1)
        self.assertIn("quadro Q7", corrompidos[0].descricao)

    def test_os_outros_segmentos_atravessam_o_mesmo_enlace_intactos(self):
        """Q3 e Q11 cruzam R4–R3 antes e depois de Q7, e chegam inteiros."""
        descartados = [e.quadro for e in self.registro if e.acao == "DESCARTA"]
        self.assertEqual(descartados, ["Q7"])
        desenquadrados = {e.quadro for e in self.registro if e.acao == "DESENQUADRA"}
        self.assertIn("Q3", desenquadrados)
        self.assertIn("Q11", desenquadrados)

    def test_a_mensagem_nao_e_remontada_sem_o_segmento_perdido(self):
        """Perder um segmento não é perder um quadro: a camada 4 do destino
        fica esperando para sempre, e `REMONTA` nunca acontece. O simulador não
        retransmite (seção 1.2)."""
        self.assertEqual([e for e in self.registro if e.acao == "REMONTA"], [])
        self.assertEqual([e for e in self.registro if e.acao == "ENTREGA"], [])


class CorrupcaoDoQuadro(unittest.TestCase):
    """A inversão em si: um bit, o mesmo quadro, CRC diferente."""

    def test_a_copia_corrompida_mantem_o_identificador(self):
        """É o mesmo quadro atravessando o enlace, não outro: R2 continua
        valendo, e o registro nomeia Q3 dos dois lados da corrupção."""
        from pdu import Bloco, Quadro, reiniciar_contador_quadros

        reiniciar_contador_quadros()
        quadro = Quadro([
            Bloco(rotulo="H2", tam=14, tipo="cabecalho", conteudo="AA;BB", camada=2),
            Bloco(rotulo="Dados", tam=4, tipo="dados", conteudo=b"\x00\x00\x00\x00"),
            Bloco(rotulo="T2", tam=4, tipo="finalizador", conteudo="00000000", camada=2),
        ])
        corrompido = quadro.com_bit_invertido(3)

        self.assertEqual(corrompido.id, quadro.id)
        self.assertIsNot(corrompido, quadro)

    def test_exatamente_um_bit_muda(self):
        from pdu import Bloco, Quadro, reiniciar_contador_quadros

        reiniciar_contador_quadros()
        original = b"\x00\xff\x0f\x55"
        quadro = Quadro([
            Bloco(rotulo="H2", tam=14, tipo="cabecalho", conteudo="AA;BB", camada=2),
            Bloco(rotulo="Dados", tam=4, tipo="dados", conteudo=original),
            Bloco(rotulo="T2", tam=4, tipo="finalizador", conteudo="00000000", camada=2),
        ])
        corrompido = quadro.com_bit_invertido(9)
        dados = next(b for b in corrompido.blocos if b.rotulo == "Dados").conteudo

        diferentes = sum(
            bin(a ^ b).count("1") for a, b in zip(original, dados)
        )
        self.assertEqual(diferentes, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
