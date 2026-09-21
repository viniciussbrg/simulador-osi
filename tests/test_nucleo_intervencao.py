"""Intervenções avulsas sobre um caso declarado (F6, issue #56).

A interface precisa rodar coisas que o `topologia.json` não declara: o caso
corrente com um enlace derrubado, o caso corrente com um erro de bit. O motor
já sabia fazer isso — C4 **é** "C2 com E-R1-R4 fora" e C6 **é** "C2 com erro
de bit em E-R4-R3" —, só não tinha porta de entrada: `executar_caso` recebe o
nome de um caso do arquivo.

A afirmação central deste arquivo é que a porta nova não é um caminho
paralelo. Montar C4 pela intervenção avulsa tem de dar o mesmo registro que
pedir C4 pelo nome; se der outra coisa, há dois motores no programa, e o que
a tela mostra deixou de ser o que o modo textual mostraria.

A igualdade é cobrada sobre o **registro**, e não sobre a tupla de objetos,
porque o caso derivado troca de id e de título de propósito — ver
`OCasoDerivadoNaoRoubaAReferencia`, logo abaixo, que é o teste do porquê.

Executar:  python -m unittest tests.test_nucleo_intervencao
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import EventoExterno, carregar_topologia
from simulador import com_intervencao, executar, executar_caso

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")

# O η do C2 como declarado no arquivo (tabela 11.3). É o valor que a linha de
# referência tem de continuar mostrando mesmo quando se executa um derivado.
ETA_DO_C2_INTEGRO = 0.11413043478260869


def _registro(eventos):
    return [evento.linha() for evento in eventos]


class IntervencaoAvulsaReproduzOsCasosDeclarados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topologia = carregar_topologia(TOPOLOGIA)

    def test_enlace_fora_sobre_c2_reproduz_o_registro_do_c4(self):
        derivado = com_intervencao(
            self.topologia.caso("C2"),
            EventoExterno(tipo="enlace_fora", enlace="E-R1-R4"),
        )
        self.assertEqual(
            _registro(executar(self.topologia, derivado)),
            _registro(executar_caso(self.topologia, "C4")),
        )

    def test_erro_bit_sobre_c2_reproduz_o_registro_do_c6(self):
        derivado = com_intervencao(
            self.topologia.caso("C2"),
            EventoExterno(tipo="erro_bit", enlace="E-R4-R3", quadro="Q3", bit=100),
        )
        self.assertEqual(
            _registro(executar(self.topologia, derivado)),
            _registro(executar_caso(self.topologia, "C6")),
        )

    def test_a_rota_alternativa_aparece_mesmo_sem_o_caso_c4_existir(self):
        # O que a interface realmente vai fazer: derrubar um enlace qualquer,
        # sem que exista caso declarado para aquela queda.
        derivado = com_intervencao(
            self.topologia.caso("C2"),
            EventoExterno(tipo="enlace_fora", enlace="E-R4-R3"),
        )
        linhas = " ".join(_registro(executar(self.topologia, derivado)))
        self.assertIn("ENLACE_FORA", linhas)


class OCasoDerivadoNaoRoubaAReferencia(unittest.TestCase):
    """Por que o derivado troca de id.

    `_Execucao._comparacao` substitui, de propósito, a linha do caso em
    execução pelo η daquela execução — é o que faz o `METRICAS` mostrar o η
    real do que se acabou de rodar. Um derivado que continuasse se chamando
    `C2` cairia nessa regra, e a comparação lado a lado da seção 11.4 passaria
    a exibir o C2 quebrado (η = 0,0%) no lugar do C2 íntegro (η = 11,4%),
    perdendo justamente o seu ponto de referência."""

    @classmethod
    def setUpClass(cls):
        cls.topologia = carregar_topologia(TOPOLOGIA)

    def test_o_id_derivado_marca_que_o_caso_foi_alterado(self):
        derivado = com_intervencao(
            self.topologia.caso("C2"),
            EventoExterno(tipo="enlace_fora", enlace="E-R1-R4"),
        )
        self.assertEqual(derivado.id, "C2*")
        self.assertIn("E-R1-R4", derivado.titulo)

    def test_derivar_duas_vezes_nao_empilha_asteriscos(self):
        # Derrubar um enlace **e** injetar um erro é um caso derivado só, com
        # duas intervenções — não um "C2**".
        uma = com_intervencao(
            self.topologia.caso("C2"),
            EventoExterno(tipo="enlace_fora", enlace="E-R1-R4"),
        )
        duas = com_intervencao(
            uma, EventoExterno(tipo="erro_bit", enlace="E-R4-R3", bit=100)
        )
        self.assertEqual(duas.id, "C2*")
        self.assertEqual(len(duas.eventos_externos), 2)

    def test_a_linha_de_referencia_do_c2_continua_integra(self):
        derivado = com_intervencao(
            self.topologia.caso("C2"),
            EventoExterno(tipo="enlace_fora", enlace="E-R1-R4"),
        )
        metricas = executar(self.topologia, derivado)[-1].metricas
        self.assertAlmostEqual(metricas.comparacao["C2"], ETA_DO_C2_INTEGRO)

    def test_o_caso_declarado_continua_sobrescrevendo_a_propria_linha(self):
        # O comportamento que motivou tudo isto continua valendo para quem
        # executa o C2 de verdade: a linha do C2 mostra o η desta execução.
        metricas = executar_caso(self.topologia, "C2")[-1].metricas
        self.assertAlmostEqual(metricas.comparacao["C2"], ETA_DO_C2_INTEGRO)

    def test_a_intervencao_nao_muda_o_caso_recebido(self):
        original = self.topologia.caso("C2")
        com_intervencao(
            original, EventoExterno(tipo="enlace_fora", enlace="E-R1-R4")
        )
        self.assertEqual(original.id, "C2")
        self.assertEqual(original.eventos_externos, ())

    def test_o_titulo_derivado_diz_o_que_foi_feito(self):
        erro = com_intervencao(
            self.topologia.caso("C2"),
            EventoExterno(tipo="erro_bit", enlace="E-R4-R3", quadro="Q3", bit=100),
        )
        self.assertIn("erro de bit", erro.titulo)
        self.assertIn("E-R4-R3", erro.titulo)


class APortaAntigaContinuaIgual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topologia = carregar_topologia(TOPOLOGIA)

    def test_executar_caso_ainda_aceita_nome(self):
        self.assertEqual(
            _registro(executar_caso(self.topologia, "C2")),
            _registro(executar(self.topologia, self.topologia.caso("C2"))),
        )

    def test_caso_inexistente_continua_levantando_keyerror(self):
        with self.assertRaises(KeyError):
            executar_caso(self.topologia, "C99")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
