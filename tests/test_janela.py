"""A janela (F6) e a fronteira que ela não pode cruzar.

O que este arquivo cobra, e a inspeção manual não pegaria: que a janela não
descobre nada sozinha. Executor, relógio, diálogo de arquivo, cabeçalho, lista
de casos, lista de enlaces e velocidades chegam todos por parâmetro, e os
testes passam versões de mentira de todos eles.

A divisão de trabalho com `tests/test_acoplamento.py` vale explicar. Lá se
verifica que `visual.py` **não importa** o núcleo, lendo o arquivo com `ast` e
proibindo os módulos num subprocesso. Aqui se verifica o outro lado da mesma
regra: que a janela **funciona** sem motor nenhum por perto. Um dos dois
sozinho deixaria passar metade do problema — dá para não importar o núcleo e
mesmo assim depender dele, e dá para importar sem depender.

O `ExecutorDeMentira` tem a mesma forma do executor de verdade, devolvendo a
dupla `(eventos, cabecalho)`. Um duplo de teste com forma diferente da coisa
real esconderia justamente o erro que ele deveria pegar.

Executar:  python -m unittest tests.test_janela
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import cabecalho, executar_caso
from visual import Janela, Navegador, carregar_planta

from tests.tela import TelaDeMentira
from tests.test_registro import TextoDeMentira

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")

VELOCIDADES = {"lenta": 1200, "media": 500, "rapida": 150}
ENLACES = ("E-A", "E-R1-R4", "E-R4-R3", "E-R1-R2")


class RelogioDeMentira:
    """Guarda o que foi agendado em vez de esperar o tempo passar.

    É o que torna o ritmo da execução contínua verificável sem display e sem
    espera real: o teste dispara os tempos na mão.

    Cancelar remove **um** agendamento, o da marca dada, e não todos — é o que
    `after_cancel` faz. A diferença importa porque a execução contínua e o
    esmaecer do pulso dividem o mesmo relógio: um duplo que limpasse a fila
    inteira faria um cancelar o outro, e o teste diria que está tudo bem
    justamente onde o programa estaria errado."""

    def __init__(self):
        self._proxima_marca = 0
        self._pendentes: dict[int, tuple[int, object]] = {}
        self.cancelados: list[int] = []

    def __call__(self, atraso, funcao):
        self._proxima_marca += 1
        self._pendentes[self._proxima_marca] = (atraso, funcao)
        return self._proxima_marca

    @property
    def agendados(self) -> list[tuple[int, object]]:
        """Os pendentes, na ordem em que foram agendados."""
        return [self._pendentes[m] for m in sorted(self._pendentes)]

    def cancelar(self, marca):
        self.cancelados.append(marca)
        self._pendentes.pop(marca, None)

    def disparar(self, quantos=1):
        for _ in range(quantos):
            if not self._pendentes:
                return
            marca = min(self._pendentes)
            _, funcao = self._pendentes.pop(marca)
            funcao()


class ExecutorDeMentira:
    """Um motor falso, com a mesma forma do de verdade."""

    def __init__(self, por_caso):
        self.por_caso = por_caso
        self.chamadas: list[tuple[str, tuple]] = []

    def __call__(self, caso, intervencoes=()):
        self.chamadas.append((caso, tuple(intervencoes)))
        return self.por_caso[caso], f"# Caso: {caso}\n#"


def eventos_reais(caso: str):
    return executar_caso(carregar_topologia(TOPOLOGIA), caso)


def telas_de_mentira():
    return {
        "mapa": TelaDeMentira(790, 340),
        "pilhas": TelaDeMentira(490, 340),
        "pdu": TelaDeMentira(1220, 92),
        "enderecos": TelaDeMentira(1220, 76),
    }


def janela_de_teste(caso="C2", relogio=None, executor=None):
    topologia = carregar_topologia(TOPOLOGIA)
    eventos = executar_caso(topologia, caso)
    return Janela(
        planta=carregar_planta(TOPOLOGIA),
        navegador=Navegador(eventos),
        caso=caso,
        executar=executor or ExecutorDeMentira({caso: eventos}),
        cabecalho=cabecalho(topologia, topologia.caso(caso)),
        casos=("C1", "C2", "C5"),
        enlaces=ENLACES,
        velocidades=VELOCIDADES,
        agendar=relogio or RelogioDeMentira(),
    )


def janela_pronta(**kwargs):
    janela = janela_de_teste(**kwargs)
    janela.ligar_telas(**telas_de_mentira())
    return janela


class AJanelaDesenhaSemMotor(unittest.TestCase):
    def test_desenha_as_quatro_regioes_em_telas_de_mentira(self):
        janela = janela_de_teste()
        telas = telas_de_mentira()
        janela.ligar_telas(**telas)
        janela.redesenhar()
        for nome, tela in telas.items():
            with self.subTest(regiao=nome):
                self.assertTrue(tela.itens, f"a região {nome} não desenhou nada")

    def test_o_indice_comeca_no_primeiro_evento(self):
        self.assertEqual(janela_de_teste().navegador.indice, 0)

    def test_as_velocidades_vem_de_fora(self):
        janela = janela_de_teste()
        self.assertEqual(janela.velocidades["media"], 500)
        self.assertEqual(janela.velocidade_corrente, "media")

    def test_a_lista_de_casos_vem_de_fora(self):
        self.assertEqual(janela_de_teste().casos, ("C1", "C2", "C5"))

    def test_a_lista_de_enlaces_vem_de_fora(self):
        self.assertEqual(janela_de_teste().enlaces, ENLACES)

    def test_o_cabecalho_vem_pronto_de_fora(self):
        self.assertIn("# Caso: C2", janela_de_teste().cabecalho)

    def test_desenhar_nao_chama_o_motor(self):
        # A simulação já rodou inteira (issue #32): desenhar é só ler.
        executor = ExecutorDeMentira({"C2": eventos_reais("C2")})
        janela = janela_pronta(executor=executor)
        janela.redesenhar()
        janela.redesenhar()
        self.assertEqual(executor.chamadas, [])


# --------------------------------------------------------------------------
# V5 — os controles de execução (issue #53)
# --------------------------------------------------------------------------


class ControlesSaoIndiceNaoRecalculo(unittest.TestCase):
    """A arquitetura inteira existe para que retroceder seja de graça.

    A simulação roda antes do primeiro desenho (issue #32), então avançar e
    voltar é mover um índice. O executor de mentira conta as chamadas: se
    navegar pedisse mais um passo ao motor, a contagem subiria — e o
    retrocesso, que é o requisito difícil, deixaria de funcionar."""

    def test_proximo_e_anterior_nao_chamam_o_motor(self):
        executor = ExecutorDeMentira({"C2": eventos_reais("C2")})
        janela = janela_pronta(executor=executor)
        janela.proximo()
        janela.proximo()
        janela.anterior()
        self.assertEqual(janela.navegador.indice, 1)
        self.assertEqual(executor.chamadas, [])

    def test_anterior_no_inicio_nao_estoura(self):
        janela = janela_pronta()
        janela.anterior()
        self.assertEqual(janela.navegador.indice, 0)

    def test_proximo_no_fim_nao_estoura(self):
        janela = janela_pronta()
        janela.navegador.ultimo()
        janela.proximo()
        self.assertTrue(janela.navegador.no_fim)

    def test_navegar_redesenha(self):
        janela = janela_de_teste()
        telas = telas_de_mentira()
        janela.ligar_telas(**telas)
        janela.proximo()
        self.assertTrue(telas["pilhas"].itens)


class RitmoDaExecucaoContinua(unittest.TestCase):
    def test_executar_agenda_na_velocidade_corrente(self):
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio)
        janela.executar_continuo()
        self.assertEqual(relogio.agendados[0][0], 500)  # média, o padrão

    def test_cada_velocidade_tem_o_seu_atraso(self):
        for nome, esperado in (("lenta", 1200), ("media", 500), ("rapida", 150)):
            relogio = RelogioDeMentira()
            janela = janela_pronta(relogio=relogio)
            janela.mudar_velocidade(nome)
            janela.executar_continuo()
            with self.subTest(velocidade=nome):
                self.assertEqual(relogio.agendados[0][0], esperado)

    def test_disparar_o_relogio_avanca_um_passo_e_reagenda(self):
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio)
        janela.executar_continuo()
        relogio.disparar()
        self.assertEqual(janela.navegador.indice, 1)
        self.assertTrue(relogio.agendados, "devia ter reagendado o passo seguinte")

    def test_pausar_interrompe_a_cadeia(self):
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio)
        janela.executar_continuo()
        janela.pausar()
        relogio.disparar()
        self.assertEqual(janela.navegador.indice, 0)
        self.assertFalse(janela.em_execucao)

    def test_a_execucao_para_sozinha_no_ultimo_passo(self):
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio)
        janela.navegador.ir_para(janela.navegador.total - 2)
        janela.executar_continuo()
        relogio.disparar()
        self.assertTrue(janela.navegador.no_fim)
        self.assertFalse(janela.em_execucao)

    def test_executar_no_fim_nao_agenda_nada(self):
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio)
        janela.navegador.ultimo()
        janela.executar_continuo()
        self.assertEqual(relogio.agendados, [])

    def test_executar_duas_vezes_nao_duplica_a_cadeia(self):
        # Dois agendamentos vivos fariam o registro andar de dois em dois, e o
        # sintoma seria confundido com defeito do motor.
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio)
        janela.executar_continuo()
        janela.executar_continuo()
        self.assertEqual(len(relogio.agendados), 1)

    def test_velocidade_desconhecida_e_recusada(self):
        janela = janela_pronta()
        with self.assertRaises(ValueError):
            janela.mudar_velocidade("supersonica")

    def test_trocar_de_velocidade_em_execucao_vale_ja_no_proximo_passo(self):
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio)
        janela.executar_continuo()
        janela.mudar_velocidade("rapida")
        self.assertEqual(relogio.agendados[-1][0], 150)


# --------------------------------------------------------------------------
# O pulso e a piscada que a F5 deixou como estado sem animação
# --------------------------------------------------------------------------


class DestaqueEsmaeceSozinho(unittest.TestCase):
    """A dívida assumida ao fechar #49 e #51.

    Lá o destaque foi desenhado estático de propósito: o esmaecer precisa de
    relógio, e o relógio só chegou com o V5. Como o estado já dizia
    `decidiu_rota` e `fisico_mudou`, o que falta aqui é curto — e, por ser o
    relógio injetado, continua verificável sem display."""

    def _no_passo(self, passo, relogio):
        janela = janela_pronta(relogio=relogio)
        indice = next(
            i
            for i, e in enumerate(janela.navegador.eventos)
            if e.passo == passo and not e.secundario
        )
        janela.navegador.ir_para(indice)
        janela.redesenhar()
        return janela

    def test_a_decisao_de_rota_agenda_o_esmaecer(self):
        relogio = RelogioDeMentira()
        janela = self._no_passo(11, relogio)  # R1 | L3 | ROTEIA
        self.assertTrue(janela.destaque_vivo)
        self.assertTrue(relogio.agendados)

    def test_depois_do_tempo_o_destaque_apaga(self):
        relogio = RelogioDeMentira()
        janela = self._no_passo(11, relogio)
        relogio.disparar()
        self.assertFalse(janela.destaque_vivo)

    def test_a_substituicao_de_endereco_tambem_pulsa(self):
        relogio = RelogioDeMentira()
        janela = self._no_passo(12, relogio)  # troca de par físico
        self.assertTrue(janela.destaque_vivo)

    def test_passo_sem_decisao_nem_troca_nao_agenda_nada(self):
        relogio = RelogioDeMentira()
        janela = self._no_passo(13, relogio)
        self.assertFalse(janela.destaque_vivo)
        self.assertEqual(relogio.agendados, [])

    def test_apagado_o_pulso_a_caixa_perde_o_laranja(self):
        from visual import COR_DECISAO

        relogio = RelogioDeMentira()
        janela = janela_de_teste(relogio=relogio)
        telas = telas_de_mentira()
        janela.ligar_telas(**telas)
        indice = next(
            i
            for i, e in enumerate(janela.navegador.eventos)
            if e.passo == 11 and not e.secundario
        )
        janela.navegador.ir_para(indice)
        janela.redesenhar()
        antes = [
            i for i in telas["pilhas"].com("camada:R1:3")
            if i.tipo == "rect"
        ][0]
        self.assertEqual(antes.opcoes.get("outline"), COR_DECISAO)
        relogio.disparar()
        depois = [
            i for i in telas["pilhas"].com("camada:R1:3")
            if i.tipo == "rect"
        ][0]
        self.assertNotEqual(depois.opcoes.get("outline"), COR_DECISAO)

    def test_o_esmaecer_nao_atrapalha_a_execucao_continua(self):
        # Os dois usam o mesmo relógio; um não pode cancelar o outro.
        relogio = RelogioDeMentira()
        janela = self._no_passo(11, relogio)
        janela.executar_continuo()
        self.assertTrue(janela.em_execucao)


# --------------------------------------------------------------------------
# O botão Salvar (issue #54)
# --------------------------------------------------------------------------


class SalvarGravaOQueEstaNaTela(unittest.TestCase):
    """O diálogo entra por injeção, como o relógio e o executor: sem isso, o
    teste do salvamento precisaria abrir janela."""

    def _janela_com_registro(self, destino):
        janela = janela_pronta()
        janela._escolher_arquivo = lambda **_: destino
        janela.ligar_registro(TextoDeMentira())
        janela.redesenhar()
        return janela

    def test_salva_no_caminho_escolhido(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "registro.txt")
            janela = self._janela_com_registro(destino)
            self.assertEqual(janela.salvar(), destino)
            with open(destino, encoding="utf-8") as arquivo:
                gravado = arquivo.read()
            self.assertIn("# Caso: C2", gravado)
            self.assertIn("008 | H1 | L1 | TRANSMITE", gravado)

    def test_o_arquivo_sai_em_utf8_com_quebra_unix(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "registro.txt")
            self._janela_com_registro(destino).salvar()
            with open(destino, "rb") as arquivo:
                cru = arquivo.read()
            # A comparação byte a byte de dois registros não pode depender da
            # plataforma que gerou cada um — mesma razão do modo textual.
            self.assertNotIn(b"\r\n", cru)
            self.assertIn("η".encode("utf-8"), cru)

    def test_cancelar_o_dialogo_nao_grava_nada(self):
        janela = self._janela_com_registro("")
        self.assertIsNone(janela.salvar())

    def test_o_nome_sugerido_tem_caso_e_carimbo_de_tempo(self):
        pedidos = {}
        janela = janela_pronta()
        janela._escolher_arquivo = lambda **opcoes: pedidos.update(opcoes) or ""
        janela.ligar_registro(TextoDeMentira())
        janela.salvar()
        sugerido = pedidos["initialfile"]
        self.assertTrue(sugerido.startswith("registro_C2_"))
        self.assertTrue(sugerido.endswith(".txt"))

    def test_a_caixa_de_descartes_muda_o_que_e_gravado(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "registro.txt")
            janela = self._janela_com_registro(destino)
            janela.alternar_descartes(True)
            janela.salvar()
            with open(destino, encoding="utf-8") as arquivo:
                self.assertIn("IGNORA", arquivo.read())


# --------------------------------------------------------------------------
# Os controles que reexecutam (issue #56)
# --------------------------------------------------------------------------


def executor_com(*casos):
    return ExecutorDeMentira({caso: eventos_reais(caso) for caso in casos})


class SeletorDeCasoReexecuta(unittest.TestCase):
    def test_trocar_de_caso_chama_o_motor_uma_vez(self):
        executor = executor_com("C2", "C5")
        janela = janela_pronta(executor=executor)
        janela.trocar_caso("C5")
        self.assertEqual(executor.chamadas, [("C5", ())])

    def test_trocar_de_caso_volta_ao_indice_zero(self):
        janela = janela_pronta(executor=executor_com("C2", "C5"))
        janela.proximo()
        janela.proximo()
        janela.trocar_caso("C5")
        self.assertEqual(janela.navegador.indice, 0)

    def test_trocar_de_caso_troca_os_eventos(self):
        janela = janela_pronta(executor=executor_com("C2", "C5"))
        antes = janela.navegador.total
        janela.trocar_caso("C5")
        self.assertNotEqual(janela.navegador.total, antes)
        self.assertEqual(janela.caso, "C5")

    def test_trocar_de_caso_pausa_a_execucao_continua(self):
        relogio = RelogioDeMentira()
        janela = janela_pronta(relogio=relogio, executor=executor_com("C2", "C5"))
        janela.executar_continuo()
        janela.trocar_caso("C5")
        self.assertFalse(janela.em_execucao)

    def test_o_cabecalho_acompanha_o_caso_novo(self):
        janela = janela_pronta(executor=executor_com("C2", "C5"))
        janela.trocar_caso("C5")
        self.assertIn("C5", janela.cabecalho)


class IntervencoesReexecutamOCasoCorrente(unittest.TestCase):
    def test_derrubar_enlace_manda_a_intervencao_ao_motor(self):
        executor = executor_com("C2")
        janela = janela_pronta(executor=executor)
        janela.derrubar_enlace("E-R1-R4")
        caso, intervencoes = executor.chamadas[-1]
        self.assertEqual(caso, "C2")
        self.assertEqual(len(intervencoes), 1)
        self.assertEqual(intervencoes[0].tipo, "enlace_fora")
        self.assertEqual(intervencoes[0].enlace, "E-R1-R4")

    def test_injetar_erro_escolhe_o_proximo_quadro_daquele_enlace(self):
        executor = executor_com("C2")
        janela = janela_pronta(executor=executor)
        janela.injetar_erro("E-R4-R3")
        _, intervencoes = executor.chamadas[-1]
        self.assertEqual(intervencoes[0].tipo, "erro_bit")
        self.assertEqual(intervencoes[0].enlace, "E-R4-R3")
        # Q3, e não Q1: cada salto constrói um quadro novo (restrição R2), e
        # quem atravessa E-R4-R3 em C2 é o terceiro. É exatamente o par
        # (enlace, quadro) que o C6 declara no topologia.json — a injeção
        # avulsa reproduz a demonstração conhecida sem precisar dela escrita.
        self.assertEqual(intervencoes[0].quadro, "Q3")
        self.assertEqual(intervencoes[0].bit, 100)

    def test_as_intervencoes_se_acumulam(self):
        executor = executor_com("C2")
        janela = janela_pronta(executor=executor)
        janela.derrubar_enlace("E-R1-R4")
        janela.injetar_erro("E-R4-R3")
        _, intervencoes = executor.chamadas[-1]
        self.assertEqual(len(intervencoes), 2)

    def test_trocar_de_caso_limpa_as_intervencoes(self):
        executor = executor_com("C2", "C5")
        janela = janela_pronta(executor=executor)
        janela.derrubar_enlace("E-R1-R4")
        janela.trocar_caso("C5")
        self.assertEqual(executor.chamadas[-1], ("C5", ()))

    def test_enlace_nao_atravessado_no_caso_nao_reexecuta(self):
        # Reexecutar sem efeito visível pareceria um programa quebrado.
        executor = executor_com("C2")
        janela = janela_pronta(executor=executor)
        janela.injetar_erro("E-R1-R2")  # C2 não passa por aqui
        self.assertEqual(executor.chamadas, [])
        self.assertIn("E-R1-R2", janela.ultimo_aviso)

    def test_derrubar_enlace_volta_ao_indice_zero(self):
        janela = janela_pronta(executor=executor_com("C2"))
        janela.proximo()
        janela.derrubar_enlace("E-R1-R4")
        self.assertEqual(janela.navegador.indice, 0)

    def test_o_aviso_limpa_na_reexecucao_seguinte(self):
        janela = janela_pronta(executor=executor_com("C2"))
        janela.injetar_erro("E-R1-R2")
        self.assertTrue(janela.ultimo_aviso)
        janela.derrubar_enlace("E-R1-R4")
        self.assertEqual(janela.ultimo_aviso, "")


class OQuadroSeguinteSaiDaListaJaProduzida(unittest.TestCase):
    """Não há execução especulativa aqui: só uma varredura do que o motor já
    disse que vai acontecer."""

    def test_no_inicio_e_o_quadro_que_o_c6_declara(self):
        self.assertEqual(janela_pronta().quadro_seguinte_no("E-R4-R3"), "Q3")

    def test_no_primeiro_enlace_e_o_primeiro_quadro(self):
        self.assertEqual(janela_pronta().quadro_seguinte_no("E-A"), "Q1")

    def test_no_fim_nao_ha_mais_quadro(self):
        janela = janela_pronta()
        janela.navegador.ultimo()
        self.assertIsNone(janela.quadro_seguinte_no("E-R4-R3"))

    def test_enlace_fora_do_caso_nao_tem_quadro(self):
        self.assertIsNone(janela_pronta().quadro_seguinte_no("E-R1-R2"))

    def test_em_c7_o_quadro_avanca_com_a_navegacao(self):
        # Doze quadros: corromper sempre o primeiro seria sempre a mesma
        # demonstração.
        janela = janela_pronta(caso="C7", executor=executor_com("C7"))
        primeiro = janela.quadro_seguinte_no("E-R4-R3")
        janela.navegador.ir_para(janela.navegador.total // 2)
        self.assertNotEqual(janela.quadro_seguinte_no("E-R4-R3"), primeiro)


class CaixaDeDescartesSoFiltraExibicao(unittest.TestCase):
    def test_alternar_descartes_nao_chama_o_motor(self):
        executor = executor_com("C2")
        janela = janela_pronta(executor=executor)
        janela.ligar_registro(TextoDeMentira())
        janela.alternar_descartes(True)
        self.assertEqual(executor.chamadas, [])
        self.assertTrue(janela.mostrar_secundarios)

    def test_alternar_descartes_nao_move_o_indice(self):
        janela = janela_pronta(executor=executor_com("C2"))
        janela.ligar_registro(TextoDeMentira())
        janela.proximo()
        janela.proximo()
        janela.alternar_descartes(True)
        self.assertEqual(janela.navegador.indice, 2)


# --------------------------------------------------------------------------
# De ponta a ponta: o botão, o motor de verdade e o registro conhecido
# --------------------------------------------------------------------------


class OsBotoesReproduzemOsCasosDeclarados(unittest.TestCase):
    """O teste que amarra as duas metades.

    Todos os anteriores usam um motor de mentira, que é o que os torna
    rápidos e independentes de display. Este usa o executor de verdade,
    montado por `app.montar_executor`, e cobra o resultado inteiro: apertar
    "derrubar enlace" em C2 tem de produzir, linha por linha, o registro do
    C4 declarado no arquivo; "injetar erro" tem de produzir o do C6 — com o
    quadro escolhido pela própria janela, não escrito no teste."""

    @classmethod
    def setUpClass(cls):
        import app

        cls.topologia = carregar_topologia(TOPOLOGIA)
        cls.executar = staticmethod(app.montar_executor(cls.topologia))

    def _janela(self):
        eventos, cabeca = self.executar("C2")
        janela = Janela(
            planta=carregar_planta(TOPOLOGIA),
            navegador=Navegador(eventos),
            caso="C2",
            executar=self.executar,
            cabecalho=cabeca,
            casos=("C1", "C2"),
            enlaces=ENLACES,
            velocidades=VELOCIDADES,
            agendar=RelogioDeMentira(),
        )
        janela.ligar_telas(**telas_de_mentira())
        return janela

    def _registro(self, janela):
        return [evento.linha() for evento in janela.navegador.eventos]

    def test_derrubar_o_enlace_r1_r4_produz_o_registro_do_c4(self):
        janela = self._janela()
        janela.derrubar_enlace("E-R1-R4")
        self.assertEqual(
            self._registro(janela),
            [e.linha() for e in executar_caso(self.topologia, "C4")],
        )

    def test_injetar_erro_em_r4_r3_produz_o_registro_do_c6(self):
        janela = self._janela()
        janela.injetar_erro("E-R4-R3")
        self.assertEqual(
            self._registro(janela),
            [e.linha() for e in executar_caso(self.topologia, "C6")],
        )

    def test_o_cabecalho_denuncia_o_caso_derivado(self):
        janela = self._janela()
        janela.derrubar_enlace("E-R1-R4")
        self.assertIn("C2*", janela.cabecalho)

    def test_derrubar_um_enlace_sem_caso_declarado_tambem_funciona(self):
        # O ponto da issue: não existe caso no arquivo para esta queda.
        janela = self._janela()
        janela.derrubar_enlace("E-R4-R3")
        linhas = " ".join(self._registro(janela))
        # O registro nomeia o enlace pelo rótulo, não pelo id.
        self.assertIn("ENLACE_FORA", linhas)
        self.assertIn("R4–R3 indisponível", linhas)
        # E a rota some para R1 → R2 → R3, que nenhum caso do arquivo declara.
        self.assertIn("via R2", linhas)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
