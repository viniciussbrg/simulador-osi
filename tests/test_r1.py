"""T-R1 — isolamento do roteador (issue #35).

A restrição R1 diz que o roteador não lê o que não lhe pertence, e a garantia
estrutural é `Roteador.__init__` instanciar apenas L1, L2 e L3 (issue #27):
os objetos das camadas 4 a 7 não existem naquele dispositivo, e `__slots__`
impede que apareçam depois.

Isso prova que a informação é inalcançável; **não** prova que ninguém a
colocou no evento por outro caminho — um contexto compartilhado copiado
errado, um campo herdado de uma ação anterior, um valor de origem carregado
junto com o pacote. É por isso que a issue pede este teste sobre o registro
pronto: o que se confere aqui é o retrato final, campo a campo.

Dois lados, e o segundo é o que impede o teste de ser vácuo:

- nenhum evento de roteador tem `porta`, `sessao`, `processo` ou `segmento`;
- os eventos de **computador** têm esses campos preenchidos, nos mesmos casos.
  Sem esta segunda metade, apagar os quatro campos do `Evento` inteiro deixaria
  T-R1 verde.

Vale para todos os casos que o motor executa hoje (`casos_executaveis`), não
só C2: C3 concorre dois fluxos e C7 segmenta — situações em que um campo de
camada alta teria mais chance de vazar para um roteador. C4 e C6 entram
quando F4 aplicar a queda de enlace e o erro de bit que eles declaram.

Executar:  python -m unittest tests.test_r1
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import casos_executaveis, executar_caso

# Os quatro campos que só um computador tem como preencher: porta e sessão
# vêm das camadas 4 e 5, o segmento é a numeração da camada 4, o processo é da
# camada 7 (seção 7.2).
CAMPOS_DE_CAMADA_ALTA = ("porta", "sessao", "processo", "segmento")


class IsolamentoDoRoteador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.roteadores = {d.nome for d in cls.topo.dispositivos if d.tipo == "roteador"}
        # C4 e C6 ficam de fora enquanto a intervenção externa deles não
        # existir: o motor os recusa (`CasoNaoSuportado`).
        cls.casos = casos_executaveis(cls.topo)
        cls.eventos = {
            caso: executar_caso(cls.topo, caso) for caso in cls.casos
        }

    def test_a_topologia_tem_roteadores_para_conferir(self):
        """Guarda do próprio teste: uma topologia sem roteador tornaria todas as
        asserções abaixo verdadeiras por ausência."""
        self.assertEqual(self.roteadores, {"R1", "R2", "R3", "R4"})

    def test_nenhum_evento_de_roteador_tem_campo_de_camada_alta(self):
        """O critério de aceitação da issue, medido em cada caso da topologia."""
        for caso, eventos in self.eventos.items():
            do_roteador = [e for e in eventos if e.dispositivo in self.roteadores]
            for evento in do_roteador:
                for campo in CAMPOS_DE_CAMADA_ALTA:
                    with self.subTest(caso=caso, campo=campo, passo=evento.passo):
                        self.assertIsNone(getattr(evento, campo), evento.linha())

    def test_c2_tem_eventos_de_roteador_para_conferir(self):
        """Em C2 o pacote atravessa três roteadores; se nenhum evento fosse
        deles, o teste acima não estaria olhando para nada."""
        do_roteador = [
            e for e in self.eventos["C2"] if e.dispositivo in self.roteadores
        ]
        self.assertEqual(len(do_roteador), 15)
        self.assertEqual(
            sorted({e.dispositivo for e in do_roteador}), ["R1", "R3", "R4"]
        )

    def test_os_computadores_preenchem_os_quatro_campos(self):
        """A outra metade: os campos existem e são usados por quem tem as
        camadas 4 a 7. É o que distingue "o roteador não preenche" de "ninguém
        preenche"."""
        for campo in CAMPOS_DE_CAMADA_ALTA:
            with self.subTest(campo=campo):
                preenchidos = [
                    e
                    for e in self.eventos["C2"]
                    if e.dispositivo not in self.roteadores
                    and getattr(e, campo) is not None
                ]
                self.assertTrue(preenchidos, f"nenhum evento preenche {campo}")

    def test_as_camadas_altas_aparecem_so_nas_pontas(self):
        """Reforço pelo outro ângulo: nenhum evento de camada 4 a 7 é emitido
        por roteador — ele não tem essas camadas para agir."""
        for caso, eventos in self.eventos.items():
            for evento in eventos:
                if evento.camada >= 4:
                    with self.subTest(caso=caso, passo=evento.passo):
                        self.assertNotIn(evento.dispositivo, self.roteadores)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
