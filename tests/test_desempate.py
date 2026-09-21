"""Desempate determinístico de rotas (issue #21).

Seção 6.4 da proposta técnica: quando dois caminhos empatam em custo, vence o
de **menor nome de próximo salto em ordem lexicográfica**. A regra é
arbitrária, mas precisa ser determinística — sem ela a mesma topologia
produziria árvores de menor caminho diferentes entre execuções (e mesmo entre
duas ordens de leitura do `topologia.json`), quebrando a reprodutibilidade que
T-ROTA (issue #26) e T-C1..T-C7 exigem.

A topologia de referência (Anexo A) não tem empate nos casos C1–C7, então o
desempate não aparece nos testes de caso. Aqui ele é exercido direto sobre
grafos sintéticos: monta-se um punhado de `Aresta`, roda-se `menor_caminho`
sob a ordem natural, a inversa e centenas de embaralhamentos de um RNG
semeado, e verifica-se que o resultado é sempre o mesmo — e é de fato o menor
nome, não um artefato da ordem em que as arestas aparecem.

Executar:  python -m unittest tests.test_desempate
"""

import os
import random
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import Aresta, menor_caminho


def _liga(a: str, b: str, custo: int) -> list[Aresta]:
    """Os dois sentidos de um enlace `a`—`b`, como `Enlace.arestas()` os
    entregaria. O id de enlace e os nomes de interface são rótulos sintéticos:
    `menor_caminho` só lê origem, destino e custo."""
    enlace = f"E:{a}-{b}"
    return [
        Aresta(a, b, custo, enlace, f"{a}->{b}", f"{b}<-{a}"),
        Aresta(b, a, custo, enlace, f"{b}->{a}", f"{a}<-{b}"),
    ]


def _grafo(*ligacoes: tuple[str, str, int]) -> list[Aresta]:
    arestas: list[Aresta] = []
    for a, b, custo in ligacoes:
        arestas += _liga(a, b, custo)
    return arestas


def _ordens(arestas: list[Aresta], n: int = 300, semente: int = 20260910):
    """Amostra determinística de ordens da lista de arestas: a natural, a
    inversa e `n` embaralhamentos de um RNG semeado. `menor_caminho` tem de
    devolver exatamente a mesma árvore para todas."""
    yield list(arestas)
    yield list(reversed(arestas))
    rng = random.Random(semente)
    for _ in range(n):
        copia = list(arestas)
        rng.shuffle(copia)
        yield copia


class TestProximoSaltoEmpatado(unittest.TestCase):
    """O empate que a seção 6.4 nomeia: dois caminhos de mesmo custo com
    primeiros saltos diferentes."""

    def test_vence_o_menor_nome_de_proximo_salto(self):
        # origem --1--> M --1--> D   e   origem --1--> N --1--> D
        # Custo 2 nos dois; primeiros saltos "M" e "N"; a regra escolhe "M".
        grafo = _grafo(("origem", "M", 1), ("M", "D", 1),
                       ("origem", "N", 1), ("N", "D", 1))
        for ordem in _ordens(grafo):
            salto = menor_caminho("origem", ordem).salto("D")
            self.assertEqual(salto.custo, 2)
            self.assertEqual(salto.proximo_salto, "M")
            self.assertEqual(salto.caminho, ("origem", "M", "D"))

    def test_a_escolha_segue_o_nome_nao_a_ordem_das_arestas(self):
        # Mesmo grafo com "M" renomeado para "Z": agora "N" < "Z" e a rota
        # inverte. Se a escolha dependesse da ordem das arestas, algum
        # embaralhamento devolveria "Z".
        grafo = _grafo(("origem", "Z", 1), ("Z", "D", 1),
                       ("origem", "N", 1), ("N", "D", 1))
        escolhidos = {
            menor_caminho("origem", ordem).salto("D").proximo_salto
            for ordem in _ordens(grafo)
        }
        self.assertEqual(escolhidos, {"N"})

    def test_empate_com_aresta_de_custo_zero_no_meio(self):
        # Segmento de difusão {origem, A, B} a custo 0, e A--1-->D, B--1-->D.
        # Caminhos até D custam 1 pelos dois lados; primeiro salto "A" ou "B".
        grafo = _grafo(("origem", "A", 0), ("origem", "B", 0), ("A", "B", 0),
                       ("A", "D", 1), ("B", "D", 1))
        for ordem in _ordens(grafo):
            salto = menor_caminho("origem", ordem).salto("D")
            self.assertEqual(salto.custo, 1)
            self.assertEqual(salto.proximo_salto, "A")


class TestProximoSaltoIgualPelosDoisLados(unittest.TestCase):
    """Quando os dois caminhos de menor custo saem pelo mesmo primeiro salto e
    só divergem adiante, a *rota* já está decidida — `(custo, próximo salto)`
    não varia. O campo `caminho` é cosmético (seção 6.4): pode ser qualquer um
    dos caminhos de menor custo, mas sempre um deles."""

    def test_custo_e_proximo_salto_ficam_estaveis(self):
        # origem --1--> A ; A --1--> M --1--> D  e  A --1--> N --1--> D.
        # Próximo salto de D é "A" pelos dois lados, custo 3.
        grafo = _grafo(("origem", "A", 1),
                       ("A", "M", 1), ("M", "D", 1),
                       ("A", "N", 1), ("N", "D", 1))
        caminhos_validos = {("origem", "A", "M", "D"), ("origem", "A", "N", "D")}
        for ordem in _ordens(grafo):
            salto = menor_caminho("origem", ordem).salto("D")
            self.assertEqual((salto.custo, salto.proximo_salto), (3, "A"))
            self.assertIn(salto.caminho, caminhos_validos)


class TestArvoreInteiraReprodutivel(unittest.TestCase):
    """Não é só o salto até um vértice: a `ArvoreCaminhos` inteira tem de sair
    idêntica, execução após execução e ordem após ordem."""

    def test_grafo_com_varios_empates_da_sempre_a_mesma_arvore(self):
        grafo = _grafo(
            ("origem", "A", 1), ("origem", "B", 1),   # empate de 1º salto
            ("A", "C", 1), ("B", "C", 1),
            ("A", "D", 2), ("B", "D", 2),
            ("C", "E", 0), ("D", "E", 0),             # empate com custo 0
            ("E", "F", 1),
        )
        arvores = [menor_caminho("origem", ordem) for ordem in _ordens(grafo)]
        primeira = arvores[0]
        for outra in arvores[1:]:
            self.assertEqual(outra, primeira)

    def test_execucoes_repetidas_da_mesma_entrada_sao_identicas(self):
        # Guarda contra qualquer dependência de estado global ou de ordenação
        # de dict: mesma lista, 50 chamadas, um único resultado.
        grafo = _grafo(("origem", "M", 1), ("M", "D", 1),
                       ("origem", "N", 1), ("N", "D", 1))
        resultados = {menor_caminho("origem", grafo) for _ in range(50)}
        self.assertEqual(len(resultados), 1)


if __name__ == "__main__":
    unittest.main()
