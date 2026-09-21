"""V2 — as pilhas de camadas por dispositivo (issue #49).

O critério de aceitação da issue é inspeção manual no passo 8 de C2. Este
arquivo cobre o outro lado: o que é verificável sem olhar e que numa inspeção
visual passaria batido — se as colunas são mesmo as cinco do layout da seção
9.1, se o roteador tem três caixas e não sete, se a caixa laranja aparece no
roteador e **não** no computador que também executa `ROTEIA`.

A afirmação central do arquivo é a da restrição R1. O enunciado pede que a
ausência das camadas 4 a 7 no roteador seja evidente "sem precisar de texto
explicativo", e é isso que `RoteadorNaoTemCamadaSuperior` cobra: três caixas,
alinhadas pela base com as do computador, de modo que o buraco fique em cima,
onde se vê. Um roteador desenhado com sete caixas e quatro apagadas passaria
numa leitura distraída da tela e contaria uma mentira sobre a arquitetura.

Executar:  python -m unittest tests.test_pilhas
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso
from visual import (
    COR_CAMADA_ATIVA,
    MODELO_OSI,
    MODELO_TCPIP,
    COR_CAMADA_INATIVA,
    COR_DECISAO,
    COR_TEXTO_ATIVO,
    ETIQUETA_PILHAS,
    LARGURA_DECISAO,
    EstadoDasPilhas,
    Navegador,
    PilhasDosDispositivos,
    carregar_planta,
)

from tests.tela import TelaDeMentira

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")

LARGURA = 490  # os ~38% de 1280 que o Anexo C reserva às pilhas
ALTURA = 340


def estado_de(caso: str, passo: int | None = None) -> EstadoDasPilhas:
    """O retrato das pilhas no passo pedido (o último, se nenhum)."""
    navegador = Navegador(executar_caso(carregar_topologia(TOPOLOGIA), caso))
    if passo is None:
        navegador.ultimo()
    else:
        navegador.ir_para(
            next(
                i
                for i, evento in enumerate(navegador.eventos)
                if evento.passo == passo
            )
        )
    return EstadoDasPilhas.ate(navegador.ate_agora())


def desenhar(caso: str, passo: int | None = None, tela: TelaDeMentira | None = None):
    """Executa o caso, para no passo pedido e desenha as pilhas.

    A ordem é a da arquitetura: a simulação roda inteira, vira eventos, e só
    então o desenho começa — navegar é mover um índice, nunca pedir mais um
    passo ao motor."""
    tela = tela or TelaDeMentira(LARGURA, ALTURA)
    pilhas = PilhasDosDispositivos(tela, carregar_planta(TOPOLOGIA))
    pilhas.desenhar(estado_de(caso, passo), LARGURA, ALTURA)
    return tela


def caixas_de(tela: TelaDeMentira, dispositivo: str):
    """As caixas (retângulos) da coluna de um dispositivo, de baixo para cima."""
    caixas = [
        item
        for item in tela.com(f"pilha:{dispositivo}")
        if item.tipo == "rect"
    ]
    return sorted(caixas, key=lambda item: -item.coordenadas[1])


def caixa(tela: TelaDeMentira, dispositivo: str, camada: int):
    encontradas = tela.com(f"camada:{dispositivo}:{camada}")
    retangulos = [item for item in encontradas if item.tipo == "rect"]
    assert len(retangulos) == 1, f"esperava uma caixa, achei {len(retangulos)}"
    return retangulos[0]


# --------------------------------------------------------------------------
# As colunas saem dos eventos, não da topologia
# --------------------------------------------------------------------------


class ColunasVemDosEventos(unittest.TestCase):
    """Quem aparece na tela é quem participou do caso.

    A alternativa — nove colunas fixas, quatro delas apagadas em C2 — foi
    descartada: a região tem ~38% da largura, e colunas mortas espremeriam as
    vivas. O layout da seção 9.1 desenha cinco colunas para C2, e é isso que
    estes testes cobram."""

    def test_c2_traz_as_cinco_colunas_do_layout(self):
        self.assertEqual(
            estado_de("C2").colunas, ("H1", "R1", "R4", "R3", "H4")
        )

    def test_a_ordem_e_a_da_travessia_e_nao_a_do_arquivo(self):
        # R4 antes de R3 porque o quadro passa por R4 primeiro (tabela 6.5),
        # e não porque o topologia.json os lista nessa ordem.
        colunas = estado_de("C2").colunas
        self.assertLess(colunas.index("R4"), colunas.index("R3"))

    def test_a_estacao_que_so_ouviu_nao_ganha_coluna(self):
        # H2 e H5 recebem o quadro no segmento de difusão e o descartam por
        # endereço (`IGNORA`, secundário). Ouvir não é participar.
        colunas = estado_de("C2").colunas
        self.assertNotIn("H2", colunas)
        self.assertNotIn("H5", colunas)

    def test_evento_de_sistema_nao_vira_coluna(self):
        # O `METRICAS` final tem dispositivo `--` e camada 0.
        self.assertNotIn("--", estado_de("C2").colunas)

    def test_c1_nao_tem_roteador_nenhum(self):
        self.assertEqual(estado_de("C1").colunas, ("H1", "H2"))

    def test_c5_para_no_roteador_que_descarta(self):
        # Sem rota: o pacote morre em R1 e nenhum dispositivo adiante aparece.
        self.assertEqual(estado_de("C5").colunas, ("H1", "R1"))

    def test_c3_traz_as_duas_origens_concorrentes(self):
        self.assertEqual(
            estado_de("C3").colunas, ("H1", "H2", "R1", "R4", "R3", "H4")
        )

    def test_a_coluna_aparece_no_passo_em_que_o_dispositivo_age(self):
        # No passo 8 de C2, H1 acabou de transmitir e R1 ainda não recebeu.
        self.assertEqual(estado_de("C2", 8).colunas, ("H1",))

    def test_sem_eventos_nao_ha_retrato(self):
        with self.assertRaises(ValueError):
            EstadoDasPilhas.ate(())


# --------------------------------------------------------------------------
# A camada ativa
# --------------------------------------------------------------------------


class CamadaAtivaSaiDoEventoCorrente(unittest.TestCase):
    def test_no_passo_8_de_c2_a_ativa_e_a_camada_1_de_h1(self):
        estado = estado_de("C2", 8)
        self.assertEqual(estado.dispositivo, "H1")
        self.assertEqual(estado.camada, 1)

    def test_no_passo_7_de_c2_a_ativa_e_a_camada_2_de_h1(self):
        estado = estado_de("C2", 7)
        self.assertEqual(estado.dispositivo, "H1")
        self.assertEqual(estado.camada, 2)

    def test_so_o_dispositivo_do_evento_corrente_tem_camada_acesa(self):
        estado = estado_de("C2", 11)
        self.assertEqual(estado.dispositivo, "R1")
        self.assertFalse(estado.acesa("H1", 2))
        self.assertTrue(estado.acesa("R1", 3))

    def test_o_sentido_vem_do_evento(self):
        self.assertEqual(estado_de("C2", 8).sentido, "desce")
        self.assertEqual(estado_de("C2", 9).sentido, "sobe")
        self.assertEqual(estado_de("C2", 11).sentido, "meio")

    def test_evento_de_sistema_nao_acende_camada_nenhuma(self):
        # O `METRICAS` final é de camada 0: a pilha fica toda apagada, e não
        # com a última camada de alguém acesa por inércia.
        estado = estado_de("C2")
        self.assertIsNone(estado.dispositivo)
        self.assertFalse(any(estado.acesa(nome, 1) for nome in estado.colunas))


# --------------------------------------------------------------------------
# A restrição R1 desenhada (o coração da issue)
# --------------------------------------------------------------------------


class RoteadorNaoTemCamadaSuperior(unittest.TestCase):
    def test_computador_tem_sete_caixas_e_roteador_tres(self):
        tela = desenhar("C2", 11)
        self.assertEqual(len(caixas_de(tela, "H1")), 7)
        self.assertEqual(len(caixas_de(tela, "R1")), 3)

    def test_o_roteador_nao_desenha_caixa_de_camada_4_a_7(self):
        tela = desenhar("C2", 11)
        for camada in (4, 5, 6, 7):
            self.assertEqual(
                tela.com(f"camada:R1:{camada}"),
                [],
                f"roteador não pode ter camada {camada} na tela (R1)",
            )

    def test_as_pilhas_sao_alinhadas_pela_base(self):
        # É o alinhamento que faz o buraco aparecer em cima, onde se vê.
        tela = desenhar("C2", 11)
        base_computador = caixa(tela, "H1", 1).coordenadas[3]
        base_roteador = caixa(tela, "R1", 1).coordenadas[3]
        self.assertAlmostEqual(base_computador, base_roteador, places=6)

    def test_a_caixa_de_uma_camada_tem_a_mesma_altura_nas_duas_pilhas(self):
        # Caixas de alturas diferentes esconderiam o buraco: um roteador com
        # três caixas altas encheria a coluna toda.
        tela = desenhar("C2", 11)
        altura_h1 = caixa(tela, "H1", 1).coordenadas[3] - caixa(tela, "H1", 1).coordenadas[1]
        altura_r1 = caixa(tela, "R1", 1).coordenadas[3] - caixa(tela, "R1", 1).coordenadas[1]
        self.assertAlmostEqual(altura_h1, altura_r1, places=6)

    def test_o_topo_do_roteador_fica_abaixo_do_topo_do_computador(self):
        tela = desenhar("C2", 11)
        topo_computador = caixa(tela, "H1", 7).coordenadas[1]
        topo_roteador = caixa(tela, "R1", 3).coordenadas[1]
        self.assertGreater(topo_roteador, topo_computador)

    def test_cada_caixa_mostra_o_numero_da_camada(self):
        tela = desenhar("C2", 11)
        rotulos = [
            item.opcoes.get("text")
            for item in tela.com("pilha:R1")
            if item.tipo == "text"
        ]
        for numero in ("1", "2", "3"):
            self.assertIn(numero, rotulos)

    def test_o_nome_do_dispositivo_encabeca_a_coluna(self):
        tela = desenhar("C2", 11)
        self.assertIn("R1", tela.textos())
        self.assertIn("H1", tela.textos())


# --------------------------------------------------------------------------
# Cores e o segundo canal (seção 9.3)
# --------------------------------------------------------------------------


class CoresDaPilha(unittest.TestCase):
    def test_a_camada_ativa_e_azul_solido_com_texto_branco(self):
        tela = desenhar("C2", 8)
        self.assertEqual(caixa(tela, "H1", 1).opcoes.get("fill"), COR_CAMADA_ATIVA)
        texto = [
            item
            for item in tela.com("camada:H1:1")
            if item.tipo == "text"
        ]
        self.assertTrue(texto, "a caixa ativa precisa do número dentro")
        self.assertEqual(texto[0].opcoes.get("fill"), COR_TEXTO_ATIVO)

    def test_as_demais_camadas_ficam_cinza_claro(self):
        tela = desenhar("C2", 8)
        self.assertEqual(caixa(tela, "H1", 5).opcoes.get("fill"), COR_CAMADA_INATIVA)

    def test_a_camada_ativa_tem_contorno_adicional(self):
        # Seção 9.3: nenhuma informação depende só de cor. A ativa é mais
        # grossa que a inativa, e continua distinguível em preto e branco.
        tela = desenhar("C2", 8)
        ativa = caixa(tela, "H1", 1)
        inativa = caixa(tela, "H1", 5)
        self.assertGreater(ativa.opcoes.get("width", 1), inativa.opcoes.get("width", 1))


# --------------------------------------------------------------------------
# A decisão de rota
# --------------------------------------------------------------------------


class DecisaoDeRotaMarcaACamada3(unittest.TestCase):
    def test_roteia_em_roteador_reforca_o_contorno_da_camada_3(self):
        tela = desenhar("C2", 11)  # R1 | L3 | ROTEIA
        alvo = caixa(tela, "R1", 3)
        self.assertEqual(alvo.opcoes.get("outline"), COR_DECISAO)
        self.assertEqual(alvo.opcoes.get("width"), LARGURA_DECISAO)

    def test_roteia_em_computador_nao_acende_o_laranja(self):
        # H1 também executa ROTEIA (passo 6), mas a decisão que a issue quer
        # evidenciar é a do roteador — é lá que a restrição R1 se manifesta.
        tela = desenhar("C2", 6)
        self.assertNotEqual(caixa(tela, "H1", 3).opcoes.get("outline"), COR_DECISAO)

    def test_fora_de_roteia_a_camada_3_do_roteador_fica_normal(self):
        tela = desenhar("C2", 10)  # R1 | L2 | DESENQUADRA
        self.assertNotEqual(caixa(tela, "R1", 3).opcoes.get("outline"), COR_DECISAO)

    def test_o_estado_marca_a_decisao(self):
        self.assertTrue(estado_de("C2", 11).decidiu_rota)
        self.assertFalse(estado_de("C2", 10).decidiu_rota)
        self.assertFalse(estado_de("C2", 6).decidiu_rota)


# --------------------------------------------------------------------------
# Convivência com as outras regiões
# --------------------------------------------------------------------------


class RegiaoNaoInvadeAsOutras(unittest.TestCase):
    def test_redesenhar_apaga_so_a_etiqueta_das_pilhas(self):
        tela = TelaDeMentira(LARGURA, ALTURA)
        pilhas = PilhasDosDispositivos(tela, carregar_planta(TOPOLOGIA))
        pilhas.desenhar(estado_de("C2", 8), LARGURA, ALTURA)
        pilhas.desenhar(estado_de("C2", 11), LARGURA, ALTURA)
        self.assertEqual(set(tela.apagou), {ETIQUETA_PILHAS})

    def test_tudo_leva_a_etiqueta_da_regiao(self):
        tela = desenhar("C2", 11)
        self.assertTrue(tela.itens)
        for item in tela.itens:
            self.assertTrue(
                item.tem(ETIQUETA_PILHAS),
                f"{item!r} escaparia da limpeza da região",
            )

    def test_nada_e_desenhado_fora_da_tela(self):
        tela = desenhar("C3", 20)
        for item in tela.itens:
            xs = item.coordenadas[0::2]
            ys = item.coordenadas[1::2]
            self.assertGreaterEqual(min(xs), 0)
            self.assertGreaterEqual(min(ys), 0)
            self.assertLessEqual(max(xs), LARGURA)
            self.assertLessEqual(max(ys), ALTURA)

    def test_seis_colunas_ainda_cabem(self):
        # C3 tem duas origens concorrentes: a coluna não pode vazar por isso.
        tela = desenhar("C3")
        self.assertEqual(len(estado_de("C3").colunas), 6)
        for item in tela.itens:
            self.assertLessEqual(max(item.coordenadas[0::2]), LARGURA)


# --------------------------------------------------------------------------
# V7 — a alternância OSI / TCP-IP (issue #55)
# --------------------------------------------------------------------------


def desenhar_no_modelo(caso, passo, modelo):
    tela = TelaDeMentira(LARGURA, ALTURA)
    pilhas = PilhasDosDispositivos(tela, carregar_planta(TOPOLOGIA))
    pilhas.desenhar(estado_de(caso, passo), LARGURA, ALTURA, modelo=modelo)
    return tela


class ModeloTcpIpAgrupaAsCamadasDeCima(unittest.TestCase):
    def test_o_computador_passa_de_sete_caixas_para_cinco(self):
        self.assertEqual(len(caixas_de(desenhar_no_modelo("C2", 8, MODELO_TCPIP), "H1")), 5)

    def test_o_roteador_continua_com_tres(self):
        # 1, 2 e 3 não se agrupam: só 5, 6 e 7 viram uma caixa, e o roteador
        # nunca teve nenhuma delas.
        self.assertEqual(len(caixas_de(desenhar_no_modelo("C2", 11, MODELO_TCPIP), "R1")), 3)

    def test_os_rotulos_sao_os_da_secao_7_3(self):
        tela = desenhar_no_modelo("C2", 8, MODELO_TCPIP)
        rotulos = [
            item.opcoes.get("text")
            for item in tela.com("pilha:H1")
            if item.tipo == "text"
        ]
        for esperado in (
            "Aplicação", "Transporte", "Internet", "Enlace de dados", "Física"
        ):
            self.assertIn(esperado, rotulos)

    def test_um_evento_de_camada_6_acende_a_caixa_de_aplicacao(self):
        # Passo 2 de C2 é H1 | L6 | CODIFICA. No modelo TCP/IP a camada acesa
        # é a agrupada, e continua sendo uma só.
        tela = desenhar_no_modelo("C2", 2, MODELO_TCPIP)
        acesas = [
            item
            for item in tela.com("pilha:H1")
            if item.tipo == "rect" and item.opcoes.get("fill") == COR_CAMADA_ATIVA
        ]
        self.assertEqual(len(acesas), 1)
        self.assertTrue(acesas[0].tem("camada:H1:7"))

    def test_uma_camada_de_baixo_acende_a_propria_caixa(self):
        tela = desenhar_no_modelo("C2", 8, MODELO_TCPIP)  # H1 | L1 | TRANSMITE
        acesas = [
            item
            for item in tela.com("pilha:H1")
            if item.tipo == "rect" and item.opcoes.get("fill") == COR_CAMADA_ATIVA
        ]
        self.assertEqual(len(acesas), 1)
        self.assertTrue(acesas[0].tem("camada:H1:1"))

    def test_as_caixas_ficam_encostadas_sem_buraco(self):
        # A caixa agrupada é desenhada com o número 7, mas é a **quinta** de
        # baixo para cima. Posicioná-la pelo número deixaria um vão de duas
        # caixas embaixo dela, e a pilha pareceria ter camadas invisíveis.
        tela = desenhar_no_modelo("C2", 8, MODELO_TCPIP)
        empilhadas = caixas_de(tela, "H1")
        self.assertEqual(len(empilhadas), 5)
        for baixo, cima in zip(empilhadas, empilhadas[1:]):
            folga = baixo.coordenadas[1] - cima.coordenadas[3]
            altura = baixo.coordenadas[3] - baixo.coordenadas[1]
            with self.subTest(folga=folga):
                self.assertGreaterEqual(folga, 0)
                self.assertLess(folga, altura / 2)

    def test_a_pilha_agrupada_e_mais_baixa_que_a_osi(self):
        topo_osi = caixa(desenhar_no_modelo("C2", 8, MODELO_OSI), "H1", 7)
        topo_tcpip = caixa(desenhar_no_modelo("C2", 8, MODELO_TCPIP), "H1", 7)
        self.assertGreater(topo_tcpip.coordenadas[1], topo_osi.coordenadas[1])

    def test_as_caixas_continuam_alinhadas_pela_base(self):
        tela = desenhar_no_modelo("C2", 11, MODELO_TCPIP)
        self.assertAlmostEqual(
            caixa(tela, "H1", 1).coordenadas[3],
            caixa(tela, "R1", 1).coordenadas[3],
            places=6,
        )

    def test_o_modelo_osi_continua_com_sete_caixas(self):
        self.assertEqual(len(caixas_de(desenhar_no_modelo("C2", 8, MODELO_OSI), "H1")), 7)

    def test_o_padrao_e_osi(self):
        tela = TelaDeMentira(LARGURA, ALTURA)
        PilhasDosDispositivos(tela, carregar_planta(TOPOLOGIA)).desenhar(
            estado_de("C2", 8), LARGURA, ALTURA
        )
        self.assertEqual(len(caixas_de(tela, "H1")), 7)

    def test_nada_e_desenhado_fora_da_tela_no_modelo_agrupado(self):
        tela = desenhar_no_modelo("C3", 20, MODELO_TCPIP)
        for item in tela.itens:
            self.assertGreaterEqual(min(item.coordenadas[0::2]), 0)
            self.assertLessEqual(max(item.coordenadas[0::2]), LARGURA)


class AAlternanciaNaoTocaNaSimulacao(unittest.TestCase):
    """O teste negativo, que é o que a issue realmente exige.

    "A simulação subjacente não se altera: muda apenas o agrupamento mostrado
    na tela" — então o agrupamento não pode virar campo do evento nem mudar
    uma vírgula do registro."""

    def test_o_registro_continua_dizendo_l6_e_nao_aplicacao(self):
        linhas = " ".join(
            evento.linha()
            for evento in executar_caso(carregar_topologia(TOPOLOGIA), "C2")
        )
        self.assertIn("| L6 |", linhas)
        self.assertNotIn("Aplicação |", linhas)

    def test_o_estado_das_pilhas_nao_conhece_modelo(self):
        # Se `modelo` virasse campo do estado, seria a interface contaminando
        # o retrato que sai dos eventos.
        self.assertFalse(hasattr(estado_de("C2", 8), "modelo"))

    def test_os_dois_modelos_desenham_o_mesmo_estado(self):
        estado = estado_de("C2", 2)
        for modelo in (MODELO_OSI, MODELO_TCPIP):
            tela = TelaDeMentira(LARGURA, ALTURA)
            PilhasDosDispositivos(tela, carregar_planta(TOPOLOGIA)).desenhar(
                estado, LARGURA, ALTURA, modelo=modelo
            )
            with self.subTest(modelo=modelo):
                self.assertTrue(tela.com("pilha:H1"))
        # O estado é imutável e não foi tocado por nenhum dos dois desenhos.
        self.assertEqual(estado, estado_de("C2", 2))


# --------------------------------------------------------------------------
# A mesma coisa contra um Canvas de verdade
# --------------------------------------------------------------------------


def _tela_de_verdade():
    """Um `Canvas` real, ou `None` quando não há tkinter nem display."""
    try:
        import tkinter
    except ImportError:  # pragma: no cover — depende do ambiente
        return None
    try:
        raiz = tkinter.Tk()
    except tkinter.TclError:  # pragma: no cover — sem display
        return None
    raiz.withdraw()
    return raiz, tkinter.Canvas(raiz, width=LARGURA, height=ALTURA)


class ContraOTkinterDeVerdade(unittest.TestCase):
    """As opções que a tela de mentira engoliria caladas.

    `fill`, `outline`, `width`, `font`, `tags`: a tela de mentira aceita
    qualquer palavra, o `Canvas` não. Sem esta classe, um nome de opção
    inventado só apareceria na inspeção manual — tarde demais."""

    @classmethod
    def setUpClass(cls):
        cls.ambiente = _tela_de_verdade()
        if cls.ambiente is None:
            raise unittest.SkipTest("sem tkinter ou sem display")
        cls.raiz, cls.tela = cls.ambiente

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "ambiente", None) is not None:
            cls.raiz.destroy()

    def test_as_pilhas_desenham_num_canvas_real(self):
        pilhas = PilhasDosDispositivos(self.tela, carregar_planta(TOPOLOGIA))
        pilhas.desenhar(estado_de("C2", 11), LARGURA, ALTURA)
        # caixa + número por camada, mais o nome no alto da coluna
        self.assertEqual(len(self.tela.find_withtag("pilha:R1")), 3 * 2 + 1)
        self.assertEqual(len(self.tela.find_withtag("pilha:H1")), 7 * 2 + 1)

    def test_o_contorno_da_decisao_e_aceito_pelo_canvas_real(self):
        pilhas = PilhasDosDispositivos(self.tela, carregar_planta(TOPOLOGIA))
        pilhas.desenhar(estado_de("C2", 11), LARGURA, ALTURA)
        alvo = [
            item
            for item in self.tela.find_withtag("camada:R1:3")
            if self.tela.type(item) == "rectangle"
        ]
        self.assertEqual(len(alvo), 1)
        self.assertEqual(self.tela.itemcget(alvo[0], "outline"), COR_DECISAO)
        self.assertEqual(int(float(self.tela.itemcget(alvo[0], "width"))), LARGURA_DECISAO)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
