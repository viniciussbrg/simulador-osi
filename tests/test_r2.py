"""T-R2 — quadros distintos, um por enlace (issue #36).

R2: o quadro nunca é reescrito. Na subida, a camada 2 **destrói** o quadro;
na descida cria um objeto novo, com identificador novo, tirado de um contador
global (seções 4.4/R2 e 5.3). O que o registro tem de mostrar é a consequência
disso: tantos identificadores quantos enlaces percorridos, nenhum repetido,
nenhum reaproveitado de um salto para o seguinte.

É a diferença entre "o quadro viajou de H1 a H4" (errado — o quadro morre em
cada ponta) e "quatro quadros carregaram o mesmo pacote" (certo). Em C2 são
{Q1, Q2, Q3, Q4} nos quatro enlaces da rota R1→R4→R3, o item 2 do critério de
aceitação da seção 10/C2.

O arquivo confere isso por três ângulos, porque quatro identificadores
distintos sozinhos não bastam: cada um tem de aparecer **exatamente uma vez**
sendo criado (`ENQUADRA`) e uma vez sendo removido (`DESENQUADRA`), e a conta
tem de casar com o número de enlaces que o caso percorreu — em C7, onde três
segmentos atravessam os mesmos quatro enlaces, são doze quadros, não quatro.

Executar:  python -m unittest tests.test_r2
"""

import os
import sys
import unittest
from collections import Counter

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import casos_executaveis, executar_caso

# Quantos quadros cada caso constrói: um por enlace percorrido, vezes o número
# de segmentos. C1 tem um enlace só; C5 morre na camada 3 do primeiro roteador,
# depois de um único salto; C7 são três segmentos pelos quatro enlaces de C2.
# C4 e C6 não entram: o motor os recusa enquanto a intervenção externa que
# eles declaram não existir (F4), e com ela a contagem de C6 muda — o quadro
# corrompido é descartado sem `DESENQUADRA`.
QUADROS_POR_CASO = {"C1": 1, "C2": 4, "C3": 8, "C5": 1, "C7": 12}


def numero(identificador: str) -> int:
    """`"Q12"` → `12`, para ordenar por criação em vez de por texto."""
    return int(identificador.lstrip("Q"))


class QuadrosDistintos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = {
            caso: executar_caso(cls.topo, caso)
            for caso in casos_executaveis(cls.topo)
        }

    def quadros(self, caso: str) -> list[str]:
        return [e.quadro for e in self.eventos[caso] if e.quadro is not None]

    def acoes(self, caso: str, acao: str) -> list[str]:
        return [e.quadro for e in self.eventos[caso] if e.acao == acao]

    # -- critério de aceitação da issue -----------------------------------

    def test_c2_tem_exatamente_os_quatro_quadros_da_rota(self):
        self.assertEqual(set(self.quadros("C2")), {"Q1", "Q2", "Q3", "Q4"})

    def test_c2_enquadra_quatro_vezes_e_desenquadra_quatro(self):
        self.assertEqual(self.acoes("C2", "ENQUADRA"), ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(self.acoes("C2", "DESENQUADRA"), ["Q1", "Q2", "Q3", "Q4"])

    # -- a mesma regra em todos os casos ----------------------------------

    def test_cada_caso_constroi_um_quadro_por_enlace_percorrido(self):
        for caso, esperado in QUADROS_POR_CASO.items():
            with self.subTest(caso=caso):
                self.assertEqual(len(set(self.quadros(caso))), esperado)
                self.assertEqual(len(self.acoes(caso, "ENQUADRA")), esperado)

    def test_nenhum_identificador_e_criado_duas_vezes(self):
        """O coração de R2: se um salto reescrevesse o quadro em vez de criar
        outro, um identificador apareceria duas vezes em `ENQUADRA`."""
        for caso in self.eventos:
            with self.subTest(caso=caso):
                criados = Counter(self.acoes(caso, "ENQUADRA"))
                repetidos = [q for q, vezes in criados.items() if vezes > 1]
                self.assertEqual(repetidos, [])

    def test_todo_quadro_criado_e_destruido_uma_vez(self):
        """Criação e destruição andam em par em todo caso que chega ao fim.

        C6 é a exceção prevista, e agora real (issue #41): o quadro Q3 chega
        corrompido a R3 e é descartado na camada 2 — destruído como qualquer
        outro, mas sem `DESENQUADRA`, porque nada foi extraído dele. A linha
        que sai é `DESCARTA`."""
        for caso in self.eventos:
            with self.subTest(caso=caso):
                destruidos = Counter(self.acoes(caso, "DESENQUADRA"))
                destruidos += Counter(
                    e.quadro
                    for e in self.eventos[caso]
                    if e.acao == "DESCARTA" and e.camada == 2
                )
                self.assertEqual(Counter(self.acoes(caso, "ENQUADRA")), destruidos)

    def test_a_numeracao_e_global_continua_e_comeca_em_q1(self):
        """Um contador só, para o programa inteiro: sem reinício por salto, por
        segmento ou por fluxo (C3 vai de Q1 a Q8 com dois fluxos concorrentes)."""
        for caso, esperado in QUADROS_POR_CASO.items():
            with self.subTest(caso=caso):
                self.assertEqual(
                    sorted({numero(q) for q in self.quadros(caso)}),
                    list(range(1, esperado + 1)),
                )

    def test_o_contador_reinicia_a_cada_execucao(self):
        """Executar o mesmo caso duas vezes dá os mesmos identificadores — o
        contador global é zerado no início da execução, e não acumula entre
        casos (é o que faz o Anexo B falar de Q1 a Q4 sempre)."""
        primeira = [e.quadro for e in executar_caso(self.topo, "C2")]
        segunda = [e.quadro for e in executar_caso(self.topo, "C2")]
        self.assertEqual(primeira, segunda)

    def test_os_quadros_de_c7_nao_se_confundem_entre_segmentos(self):
        """Três segmentos, quatro enlaces cada: doze quadros, e o segundo
        segmento não reaproveita os identificadores do primeiro."""
        criados = self.acoes("C7", "ENQUADRA")
        self.assertEqual([numero(q) for q in criados], list(range(1, 13)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
