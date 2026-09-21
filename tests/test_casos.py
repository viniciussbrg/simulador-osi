"""T-C1 a T-C7 — o critério de aceitação de cada caso obrigatório (issue #44).

Um método por caso, cada asserção citando o item da seção 10 que verifica.
Este arquivo é o **checklist de auditoria**: quem precisa conferir que os sete
casos do enunciado estão atendidos lê os sete métodos abaixo, não sete
arquivos. O detalhe de cada caso — contabilidade de octetos, ordem das camadas,
endereços salto a salto — mora nos arquivos dedicados, que nasceram junto com
a implementação de cada um:

    C1  tests/test_caso_c1.py      C5  tests/test_caso_c5.py
    C2  tests/test_caso_c2.py      C6  tests/test_caso_c6.py
    C3  tests/test_caso_c3.py      C7  tests/test_caso_c7.py
    C4  tests/test_caso_c4.py

A redundância é deliberada e tem limite: aqui entra só o que a seção 10 escreve
como critério. Dois itens são delegados a quem já os cobre melhor — as doze
primeiras linhas de C2 são T-FMT (`tests/test_formato.py`, issue #34) e os
valores de métricas são T-MET (`tests/test_met.py`, issue #45) —, e repeti-los
aqui criaria dois lugares para atualizar quando o registro mudar.

Executar:  python -m unittest tests.test_casos
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

ROTEADORES = {"R1", "R2", "R3", "R4"}


def desfecho(eventos):
    """O último evento de camada: o `METRICAS` fecha toda execução (issue #43)
    e não faz parte do percurso da mensagem."""
    return next(e for e in reversed(eventos) if e.camada > 0)


class CriteriosDaSecao10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = {
            caso.id: executar_caso(cls.topo, caso.id) for caso in cls.topo.casos
        }
        cls.registro = {
            caso: principais(eventos) for caso, eventos in cls.eventos.items()
        }

    def acoes(self, caso: str) -> Counter:
        return Counter(e.acao for e in self.registro[caso])

    # -- T-C1 --------------------------------------------------------------

    def test_c1_entrega_direta(self):
        """Seção 10/C1: exatamente um `ENQUADRA`; nenhuma linha de dispositivo
        roteador; o `ROTEIA` de H1 registra entrega direta."""
        registro = self.registro["C1"]

        self.assertEqual(self.acoes("C1")["ENQUADRA"], 1)

        for evento in registro:
            self.assertNotIn(evento.dispositivo, ROTEADORES, evento.linha())

        roteia = next(e for e in registro if e.acao == "ROTEIA")
        self.assertEqual(roteia.dispositivo, "H1")
        self.assertEqual(roteia.descricao, "destino na mesma rede, entrega direta")

    # -- T-C2 --------------------------------------------------------------

    def test_c2_entrega_indireta(self):
        """Seção 10/C2: quatro quadros distintos; par lógico de cardinalidade 1
        e par físico de cardinalidade 4; nenhum evento de roteador com porta,
        sessão ou processo; nenhum `ROTEIA` na camada 2.

        As doze primeiras linhas contra o enunciado ficam com T-FMT (issue
        #34), que as compara caractere a caractere."""
        eventos = self.eventos["C2"]

        enquadrados = [e.quadro for e in eventos if e.acao == "ENQUADRA"]
        self.assertEqual(enquadrados, ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(len(set(enquadrados)), 4)

        logicos = {(e.logico.origem, e.logico.destino) for e in eventos if e.logico}
        fisicos = {(e.fisico.origem, e.fisico.destino) for e in eventos if e.fisico}
        self.assertEqual(len(logicos), 1)
        self.assertEqual(len(fisicos), 4)

        for evento in eventos:
            if evento.dispositivo in ROTEADORES:
                self.assertIsNone(evento.porta, evento.linha())
                self.assertIsNone(evento.sessao, evento.linha())
                self.assertIsNone(evento.processo, evento.linha())
            if evento.camada == 2:
                self.assertNotEqual(evento.acao, "ROTEIA", evento.linha())

    # -- T-C3 --------------------------------------------------------------

    def test_c3_demultiplexacao(self):
        """Seção 10/C3: duas linhas `DEMULTIPLEXA` com sessões distintas; o
        campo `fluxo` alterna ao longo do registro; oito quadros no total."""
        registro = self.registro["C3"]

        demultiplexa = [e for e in registro if e.acao == "DEMULTIPLEXA"]
        self.assertEqual(len(demultiplexa), 2)
        self.assertEqual({e.dispositivo for e in demultiplexa}, {"H4"})
        self.assertEqual(len({e.sessao for e in demultiplexa}), 2)

        fluxos = [e.fluxo for e in registro if e.fluxo]
        self.assertIn("F1", fluxos[fluxos.index("F2"):])

        self.assertEqual(self.acoes("C3")["ENQUADRA"], 8)

    # -- T-C4 --------------------------------------------------------------

    def test_c4_falha_de_enlace(self):
        """Seção 10/C4: a linha `ENLACE_FORA` está presente; o `ROTEIA` de R1
        registra custo 3 pela interface e2; nenhuma linha menciona o enlace
        R1–R4."""
        registro = self.registro["C4"]

        fora = [e for e in registro if e.acao == "ENLACE_FORA"]
        self.assertEqual(len(fora), 1)
        self.assertEqual(fora[0].camada, 0)

        roteia = next(e for e in registro if e.dispositivo == "R1" and e.acao == "ROTEIA")
        self.assertEqual(roteia.descricao, "10.0.3.0/24 via R2, custo 3, interface e2")

        for evento in self.eventos["C4"]:
            if evento.acao != "ENLACE_FORA":
                self.assertNotIn("R1–R4", evento.descricao, evento.linha())
            self.assertNotIn("E-R1-R4", evento.caminho)

    # -- T-C5 --------------------------------------------------------------

    def test_c5_destino_inalcancavel(self):
        """Seção 10/C5: o percurso encerra com `DESCARTA` na camada 3 de R1, e
        nenhum evento posterior existe para o fluxo."""
        registro = self.registro["C5"]
        descarte = desfecho(registro)

        self.assertEqual(
            (descarte.dispositivo, descarte.camada, descarte.acao),
            ("R1", 3, "DESCARTA"),
        )
        posteriores = [
            e for e in self.eventos["C5"]
            if e.passo > descarte.passo and e.camada > 0
        ]
        self.assertEqual(posteriores, [])

    # -- T-C6 --------------------------------------------------------------

    def test_c6_erro_de_transmissao(self):
        """Seção 10/C6: a verificação diverge em R3; o descarte acontece na
        camada 2; nenhum evento de camada 3 ou superior existe depois dele."""
        registro = self.registro["C6"]

        descarte = next(e for e in registro if e.acao == "DESCARTA")
        self.assertEqual((descarte.dispositivo, descarte.camada), ("R3", 2))
        self.assertEqual(descarte.estado, "erro")
        self.assertIn("verificação de erro incorreta", descarte.descricao)

        posteriores = [
            e for e in self.eventos["C6"] if e.passo > descarte.passo and e.camada >= 3
        ]
        self.assertEqual(posteriores, [])

    # -- T-C7 --------------------------------------------------------------

    def test_c7_mensagem_longa(self):
        """Seção 10/C7: três `SEGMENTA` numerados 1, 2 e 3 de 3; os quadros
        formam a sequência contínua Q1–Q12; uma única `REMONTA`, com a entrega
        à camada 5 depois dela."""
        registro = self.registro["C7"]

        segmenta = [e for e in registro if e.acao == "SEGMENTA"]
        self.assertEqual(
            [(e.segmento.n, e.segmento.total) for e in segmenta], [(1, 3), (2, 3), (3, 3)]
        )

        enquadrados = [e.quadro for e in registro if e.acao == "ENQUADRA"]
        self.assertEqual(enquadrados, [f"Q{n}" for n in range(1, 13)])

        remonta = [e for e in registro if e.acao == "REMONTA"]
        self.assertEqual(len(remonta), 1)
        encerra = next(e for e in registro if e.acao == "ENCERRA")
        self.assertGreater(encerra.passo, remonta[0].passo)


class CoberturaDoChecklist(unittest.TestCase):
    """Guardas do próprio checklist: sem elas, um caso que sumisse do arquivo
    de topologia deixaria de ser verificado sem que nada acusasse."""

    def test_existe_um_teste_para_cada_caso_da_topologia(self):
        casos = {caso.id for caso in carregar_topologia().casos}
        testados = {
            nome.split("_")[1].upper()
            for nome in dir(CriteriosDaSecao10)
            if nome.startswith("test_c")
        }
        self.assertEqual(testados, casos)

    def test_os_sete_casos_obrigatorios_estao_na_topologia(self):
        casos = {caso.id for caso in carregar_topologia().casos}
        self.assertEqual(casos, {f"C{n}" for n in range(1, 8)})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
