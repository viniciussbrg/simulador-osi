"""V1 — o mapa da rede (issue #48).

O critério de aceitação da issue é inspeção manual contra o Anexo C, e isso
cobre o que só o olho julga: se o desenho está bonito, se os rótulos cabem, se
a tela lembra um analisador de protocolos. Este arquivo cobre o outro lado —
tudo o que é verificável sem olhar, e que numa inspeção visual passaria batido
com facilidade: se são nove nós mesmo, se o custo no círculo é o do arquivo, se
a perna verde é a do dispositivo que transmitiu e não a do vizinho que ouviu.

A ferramenta que torna isso possível é a `TelaDeMentira`: `MapaDaRede` desenha
em qualquer objeto que responda como um `Canvas`, então o teste passa um que só
anota o que foi pedido. Nada de tkinter, nada de display — a mesma regra que a
seção 13.1 impõe ao resto da suíte, agora valendo também para a interface. A
última classe do arquivo repete uma parte contra um `Canvas` de verdade, e é
pulada quando não há tkinter ou não há tela: é o que garante que os nomes de
opção usados (`dash`, `anchor`, `outline`) são os que o tkinter aceita, e não
uma invenção que só a tela de mentira engole.

Executar:  python -m unittest tests.test_mapa
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from evento import Evento
from rede import carregar_topologia
from simulador import executar_caso
from visual import (
    COR_CAMINHO,
    COR_ERRO,
    COR_FORA,
    ETIQUETA,
    LARGURA_CAMINHO,
    LARGURA_ENLACE,
    Escala,
    ErroDePlanta,
    EstadoDoMapa,
    MapaDaRede,
    Navegador,
    Planta,
    Ponto,
    carregar_planta,
)

from tests.tela import ALTURA, LARGURA, TelaDeMentira

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")
ALTERNATIVA = os.path.join(_RAIZ, "tests", "fixtures", "topologia_alternativa.json")

def desenhar(caso: str, passo: int, tela: TelaDeMentira | None = None):
    """Executa o caso, para no passo pedido e desenha o mapa.

    A ordem é a da arquitetura e a do `app.py`: a simulação roda inteira
    (issue #32), vira eventos, e só então o desenho começa."""
    tela = tela or TelaDeMentira()
    navegador = Navegador(executar_caso(carregar_topologia(TOPOLOGIA), caso))
    navegador.ir_para(
        next(i for i, evento in enumerate(navegador.eventos) if evento.passo == passo)
    )
    mapa = MapaDaRede(tela, carregar_planta(TOPOLOGIA))
    mapa.desenhar(EstadoDoMapa.ate(navegador.ate_agora()))
    return tela, navegador


def estado_de(caso: str, passo: int | None = None) -> EstadoDoMapa:
    eventos = executar_caso(carregar_topologia(TOPOLOGIA), caso)
    navegador = Navegador(eventos)
    if passo is None:
        navegador.ultimo()
    else:
        navegador.ir_para(
            next(i for i, evento in enumerate(eventos) if evento.passo == passo)
        )
    return EstadoDoMapa.ate(navegador.ate_agora())


# --------------------------------------------------------------------------
# A planta lida do arquivo (seções 5.4 e 5.5)
# --------------------------------------------------------------------------


class PlantaLidaDoArquivo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planta = carregar_planta(TOPOLOGIA)

    def test_nove_nos_com_as_formas_do_anexo_c(self):
        self.assertEqual(len(self.planta.nos), 9)
        computadores = {no.nome for no in self.planta.nos if not no.roteador}
        roteadores = {no.nome for no in self.planta.nos if no.roteador}
        self.assertEqual(computadores, {"H1", "H2", "H3", "H4", "H5"})
        self.assertEqual(roteadores, {"R1", "R2", "R3", "R4"})

    def test_as_coordenadas_sao_as_do_arquivo(self):
        """A interface **lê** o `posicao`, não o inventa (seção 5.4)."""
        self.assertEqual(self.planta.no("H1").posicao, Ponto(60.0, 60.0))
        self.assertEqual(self.planta.no("R4").posicao, Ponto(380.0, 50.0))
        self.assertEqual(self.planta.moldura(), (60.0, 50.0, 700.0, 280.0))

    def test_as_redes_sombreadas_saem_dos_segmentos_de_difusao(self):
        """As três do Anexo C, e só elas: as quatro redes de trânsito entre
        roteadores não são rede local e não ganham área sombreada."""
        self.assertEqual(
            [rede.legenda for rede in self.planta.redes_locais()],
            ["Rede A 10.0.1.0/24", "Rede B 10.0.2.0/24", "Rede C 10.0.3.0/24"],
        )

    def test_cada_rede_local_agrupa_os_dispositivos_certos(self):
        self.assertEqual(self.planta.dispositivos_da_rede("A"), ("H1", "H2", "R1"))
        self.assertEqual(self.planta.dispositivos_da_rede("B"), ("H3", "R2"))
        self.assertEqual(self.planta.dispositivos_da_rede("C"), ("H4", "H5", "R3"))

    def test_centro_de_ponto_a_ponto_e_o_meio_da_reta(self):
        centro = self.planta.centro(self.planta.enlace("E-R1-R4"))
        self.assertEqual(centro, Ponto(300.0, 80.0))

    def test_centro_de_difusao_e_o_ponto_comum_das_tres_pontas(self):
        """O segmento é um meio compartilhado (seção 5.1), e o desenho o trata
        como tal: uma estrela, não uma linha entre dois escolhidos."""
        centro = self.planta.centro(self.planta.enlace("E-A"))
        self.assertAlmostEqual(centro.x, (60 + 60 + 220) / 3)
        self.assertAlmostEqual(centro.y, (60 + 160 + 110) / 3)

    def test_topologia_trocada_desenha_sem_recompilar(self):
        """A promessa da seção 5.5 valendo também para o mapa: outra rede, com
        outros nomes e outra quantidade de nós, e nada no código a mudar."""
        outra = carregar_planta(ALTERNATIVA)
        self.assertEqual({no.nome for no in outra.nos}, {"PC-A", "PC-B", "RT-1", "RT-2"})
        self.assertEqual(
            [rede.legenda for rede in outra.redes_locais()],
            ["LAN 1 192.168.10.0/24", "LAN 2 192.168.20.0/24"],
        )

    def test_dispositivo_sem_posicao_diz_o_que_falta(self):
        with self.assertRaises(ErroDePlanta) as erro:
            Planta.de_dados({"dispositivos": [{"nome": "H9", "tipo": "computador"}]})
        self.assertIn("H9", str(erro.exception))
        self.assertIn("posicao", str(erro.exception))

    def test_topologia_ausente_ou_ilegivel_nao_estoura_cru(self):
        with self.assertRaises(ErroDePlanta):
            carregar_planta(os.path.join(_RAIZ, "nao_existe.json"))

    def test_consulta_a_nome_inexistente_diz_qual(self):
        for consulta, alvo in (
            (self.planta.no, "H9"),
            (self.planta.enlace, "E-X"),
            (self.planta.rede, "Z"),
        ):
            with self.subTest(alvo=alvo):
                with self.assertRaises(ErroDePlanta) as erro:
                    consulta(alvo)
                self.assertIn(alvo, str(erro.exception))


# --------------------------------------------------------------------------
# O estado do mapa, extraído só de eventos
# --------------------------------------------------------------------------


class EstadoVemDosEventos(unittest.TestCase):
    def test_no_passo_8_de_c2_so_a_perna_de_h1_acendeu(self):
        """O passo do Anexo C: H1 já transmitiu, R1 ainda não recebeu. Meio
        enlace aceso é a informação certa — o quadro está no meio da Rede A."""
        estado = estado_de("C2", 8)
        self.assertEqual(estado.pernas, frozenset({("E-A", "H1")}))
        self.assertEqual(estado.percorridos, frozenset({"E-A"}))
        self.assertEqual(estado.em_curso, "E-A")
        self.assertEqual(estado.fora, frozenset())

    def test_a_estacao_que_so_ouviu_nao_acende_perna(self):
        """H2 recebe o quadro da difusão e o descarta por endereço (`IGNORA`,
        evento secundário — seção 7.5). Ouvir não é encaminhar, e o traço de H2
        tem de continuar ocioso."""
        estado = estado_de("C2", 9)
        self.assertNotIn(("E-A", "H2"), estado.pernas)
        self.assertIn(("E-A", "R1"), estado.pernas)

    def test_no_fim_de_c2_o_caminho_e_o_da_tabela_6_5(self):
        """H1 → R1 → R4 → R3 → H4: quatro enlaces, oito pernas."""
        estado = estado_de("C2")
        self.assertEqual(
            estado.percorridos,
            frozenset({"E-A", "E-R1-R4", "E-R4-R3", "E-C"}),
        )
        self.assertEqual(
            estado.pernas,
            frozenset(
                {
                    ("E-A", "H1"),
                    ("E-A", "R1"),
                    ("E-R1-R4", "R1"),
                    ("E-R1-R4", "R4"),
                    ("E-R4-R3", "R4"),
                    ("E-R4-R3", "R3"),
                    ("E-C", "R3"),
                    ("E-C", "H4"),
                }
            ),
        )

    def test_c4_marca_o_enlace_derrubado_desde_o_primeiro_passo(self):
        """O `ENLACE_FORA` abre o registro, e o mapa tem de tracejar o R1–R4
        antes de qualquer quadro andar."""
        estado = estado_de("C4", 1)
        self.assertEqual(estado.fora, frozenset({"E-R1-R4"}))
        self.assertEqual(estado.percorridos, frozenset())

    def test_c4_percorre_a_rota_alternativa(self):
        estado = estado_de("C4")
        self.assertEqual(
            estado.percorridos,
            frozenset({"E-A", "E-R1-R2", "E-R2-R3", "E-C"}),
        )
        self.assertEqual(estado.fora, frozenset({"E-R1-R4"}))

    def test_c5_nao_passa_da_primeira_rede(self):
        """Sem rota, o descarte é em R1 e o mapa não acende mais nada."""
        estado = estado_de("C5")
        self.assertEqual(estado.percorridos, frozenset({"E-A"}))

    def test_c6_para_no_enlace_do_descarte(self):
        estado = estado_de("C6")
        self.assertEqual(
            estado.percorridos, frozenset({"E-A", "E-R1-R4", "E-R4-R3"})
        )
        self.assertNotIn("E-C", estado.percorridos)

    def test_o_estado_do_passo_corrente_acompanha_o_evento(self):
        self.assertEqual(estado_de("C2", 8).estado, "ok")
        self.assertEqual(estado_de("C6", 21).estado, "erro")

    def test_sem_eventos_nao_ha_retrato(self):
        with self.assertRaises(ValueError):
            EstadoDoMapa.ate(())

    def test_enlace_do_caminho_sem_evento_de_camada_1_acende_inteiro(self):
        """A rede de segurança: se um enlace consta do `caminho` mas a fatia
        não traz nenhum evento de camada 1 dele, acendem-se todas as pernas —
        melhor um enlace inteiro verde do que um percurso com buraco."""
        evento = Evento(
            passo=1,
            dispositivo="H4",
            camada=3,
            acao="DESENCAPSULA",
            descricao="amostra",
            tamanho=42,
            caminho=("E-C",),
        )
        estado = EstadoDoMapa.ate((evento,))
        self.assertTrue(estado.perna_acesa("E-C", "H4"))
        self.assertTrue(estado.perna_acesa("E-C", "R3"))
        self.assertFalse(estado.perna_acesa("E-A", "H1"))


# --------------------------------------------------------------------------
# A escala (seção 5.4: "ajusta a escala ao tamanho da janela")
# --------------------------------------------------------------------------


class EscalaEncaixaNaJanela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planta = carregar_planta(TOPOLOGIA)

    def test_a_planta_inteira_cabe_na_tela(self):
        for largura, altura in ((790, 340), (1280, 800), (420, 260)):
            with self.subTest(tela=(largura, altura)):
                escala = Escala.ajustar(self.planta, largura, altura)
                pontos = [escala.converter(no.posicao) for no in self.planta.nos]
                self.assertGreaterEqual(min(x for x, _ in pontos), 0)
                self.assertGreaterEqual(min(y for _, y in pontos), 0)
                self.assertLessEqual(max(x for x, _ in pontos), largura)
                self.assertLessEqual(max(y for _, y in pontos), altura)

    def test_um_fator_so_para_os_dois_eixos(self):
        """Esticar x e y de forma diferente entortaria os círculos dos
        roteadores, que deixariam de ser círculos."""
        escala = Escala.ajustar(self.planta, 1600, 300)
        x0, y0 = escala.converter(Ponto(0.0, 0.0))
        x1, y1 = escala.converter(Ponto(100.0, 100.0))
        self.assertAlmostEqual(x1 - x0, y1 - y0)

    def test_a_planta_fica_centralizada_na_sobra(self):
        escala = Escala.ajustar(self.planta, 1200, 600)
        xs = [escala.converter(no.posicao)[0] for no in self.planta.nos]
        ys = [escala.converter(no.posicao)[1] for no in self.planta.nos]
        self.assertAlmostEqual(min(xs), 1200 - max(xs), delta=1.0)
        self.assertAlmostEqual(min(ys), 600 - max(ys), delta=1.0)

    def test_janela_minuscula_nao_zera_o_desenho(self):
        escala = Escala.ajustar(self.planta, 60, 40)
        self.assertGreaterEqual(escala.fator, Escala.FATOR_MINIMO)
        self.assertGreaterEqual(escala.fonte(10)[1], 7)

    def test_topologia_de_um_no_so_nao_divide_por_zero(self):
        planta = Planta.de_dados(
            {"dispositivos": [{"nome": "H1", "posicao": {"x": 5, "y": 5}}]}
        )
        escala = Escala.ajustar(planta, 400, 300)
        self.assertEqual(escala.converter(Ponto(5.0, 5.0)), (200.0, 150.0))


# --------------------------------------------------------------------------
# O desenho
# --------------------------------------------------------------------------


class MapaDesenhado(unittest.TestCase):
    """O requisito V1, item por item, contra o que foi realmente desenhado."""

    @classmethod
    def setUpClass(cls):
        cls.tela, cls.navegador = desenhar("C2", 8)

    def test_todos_os_dispositivos_aparecem(self):
        nomes = {
            item.opcoes["text"]
            for item in self.tela.com("no")
            if item.tipo == "text"
        }
        self.assertEqual(
            nomes, {"H1", "H2", "H3", "H4", "H5", "R1", "R2", "R3", "R4"}
        )

    def test_computador_e_retangulo_e_roteador_e_circulo(self):
        formas = {
            item.tipo
            for item in self.tela.com("no:H1")
            if item.tipo != "text"
        }
        self.assertEqual(formas, {"rect"})
        formas = {
            item.tipo
            for item in self.tela.com("no:R1")
            if item.tipo != "text"
        }
        self.assertEqual(formas, {"oval"})

    def test_tres_redes_sombreadas_com_o_prefixo_no_rotulo(self):
        areas = [item for item in self.tela.com("rede") if item.tipo == "rect"]
        rotulos = [item.opcoes["text"] for item in self.tela.com("rede") if item.tipo == "text"]
        self.assertEqual(len(areas), 3)
        self.assertEqual(
            rotulos,
            ["Rede A 10.0.1.0/24", "Rede B 10.0.2.0/24", "Rede C 10.0.3.0/24"],
        )

    def test_a_area_da_rede_abraca_os_seus_dispositivos(self):
        """O sombreado é agrupamento, então tem de conter quem agrupa — e não
        conter quem não é da rede."""
        area = next(item for item in self.tela.com("rede:A") if item.tipo == "rect")
        x0, y0, x1, y1 = area.coordenadas
        escala = Escala.ajustar(carregar_planta(TOPOLOGIA), LARGURA, ALTURA)
        planta = carregar_planta(TOPOLOGIA)
        for nome in ("H1", "H2", "R1"):
            x, y = escala.converter(planta.no(nome).posicao)
            with self.subTest(dentro=nome):
                self.assertTrue(x0 < x < x1 and y0 < y < y1)
        for nome in ("R4", "H4"):
            x, y = escala.converter(planta.no(nome).posicao)
            with self.subTest(fora=nome):
                self.assertFalse(x0 < x < x1 and y0 < y < y1)

    def test_o_custo_aparece_nos_enlaces_entre_roteadores(self):
        custos = sorted(
            item.opcoes["text"]
            for item in self.tela.com("custo")
            if item.tipo == "text"
        )
        self.assertEqual(custos, ["1", "1", "1", "2"])
        self.assertEqual(
            next(
                item.opcoes["text"]
                for item in self.tela.do_enlace("E-R1-R2")
                if item.tem("custo") and item.tipo == "text"
            ),
            "2",
        )

    def test_segmento_de_difusao_nao_ganha_circulo_de_custo(self):
        """Custo 0 por decisão da seção 5.2 — um "0" no meio da Rede A
        sugeriria uma rota que não existe."""
        for identificador in ("E-A", "E-B", "E-C"):
            with self.subTest(enlace=identificador):
                self.assertEqual(
                    [
                        item
                        for item in self.tela.do_enlace(identificador)
                        if item.tem("custo")
                    ],
                    [],
                )

    def test_cada_ponta_de_enlace_tem_o_nome_da_interface(self):
        rotulos = [item.opcoes["text"] for item in self.tela.com("interface")]
        self.assertEqual(len(rotulos), 16)  # a soma das pontas dos sete enlaces
        self.assertEqual(rotulos.count("eth0"), 5)
        self.assertEqual(sorted(set(rotulos)), ["e0", "e1", "e2", "eth0"])

    def test_no_passo_8_o_caminho_verde_e_so_a_perna_de_h1(self):
        verdes = self.tela.com("caminho")
        self.assertEqual(len(verdes), 1)
        self.assertTrue(verdes[0].tem("enlace:E-A"))
        self.assertEqual(verdes[0].opcoes["fill"], COR_CAMINHO)

    def test_o_marcador_fica_sobre_o_enlace_em_uso(self):
        marcadores = self.tela.com("marcador")
        self.assertEqual(len(marcadores), 1)
        self.assertTrue(marcadores[0].tem("enlace:E-A"))
        self.assertEqual(marcadores[0].opcoes["fill"], COR_CAMINHO)

    def test_no_fim_de_c2_os_quatro_enlaces_do_caminho_estao_verdes(self):
        tela, _ = desenhar("C2", 30)
        verdes = tela.com("caminho")
        self.assertEqual(len(verdes), 8)  # duas pernas por enlace
        self.assertEqual(
            {item.tags[2] for item in verdes},
            {"enlace:E-A", "enlace:E-R1-R4", "enlace:E-R4-R3", "enlace:E-C"},
        )

    def test_o_caminho_nao_depende_so_de_cor(self):
        """Redundância visual (seção 9.3, issue #52): verde **e** mais grosso.
        Em tons de cinza, a espessura continua dizendo por onde a mensagem
        passou."""
        verde = self.tela.com("caminho")[0]
        ocioso = self.tela.com("ocioso")[0]
        self.assertEqual(verde.opcoes["width"], LARGURA_CAMINHO)
        self.assertEqual(ocioso.opcoes["width"], LARGURA_ENLACE)
        self.assertGreater(verde.opcoes["width"], ocioso.opcoes["width"] * 2)

    def test_nada_e_desenhado_fora_da_tela(self):
        for item in self.tela.itens:
            with self.subTest(item=item):
                xs = item.coordenadas[0::2]
                ys = item.coordenadas[1::2]
                self.assertGreaterEqual(min(xs), 0)
                self.assertGreaterEqual(min(ys), 0)
                self.assertLessEqual(max(xs), LARGURA)
                self.assertLessEqual(max(ys), ALTURA)

    def test_redesenhar_apaga_o_desenho_anterior(self):
        """Cada passo refaz o mapa do zero; sem o `delete`, navegar empilharia
        desenho sobre desenho."""
        tela = TelaDeMentira()
        mapa = MapaDaRede(tela, carregar_planta(TOPOLOGIA))
        estado = estado_de("C2", 8)
        mapa.desenhar(estado)
        quantos = len(tela.itens)
        mapa.desenhar(estado)
        self.assertEqual(len(tela.itens), quantos)
        self.assertEqual(tela.apagou, [ETIQUETA, ETIQUETA])

    def test_tudo_leva_a_etiqueta_do_mapa(self):
        """É por ela que o mapa apaga só o que é seu — as outras regiões da
        tela (V2 a V4) dividirão o mesmo `Canvas`."""
        for item in self.tela.itens:
            self.assertTrue(item.tem(ETIQUETA), item)

    def test_o_desenho_segue_a_topologia_trocada(self):
        tela = TelaDeMentira()
        MapaDaRede(tela, carregar_planta(ALTERNATIVA)).desenhar(
            EstadoDoMapa.ate(
                (
                    Evento(
                        passo=1,
                        dispositivo="PC-A",
                        camada=7,
                        acao="GERA",
                        descricao="amostra",
                        tamanho=42,
                    ),
                )
            )
        )
        nomes = {
            item.opcoes["text"] for item in tela.com("no") if item.tipo == "text"
        }
        self.assertEqual(nomes, {"PC-A", "PC-B", "RT-1", "RT-2"})
        self.assertEqual(len([i for i in tela.com("rede") if i.tipo == "rect"]), 2)


class EnlaceForaDoAr(unittest.TestCase):
    """C4 no mapa: tracejado, cinza e com X (seção 9.3)."""

    @classmethod
    def setUpClass(cls):
        # Passo 15: R2 acabou de receber pelo desvio, então o mapa já tem o
        # que comparar — o R1–R2 aceso e o R1–R4 tracejado, lado a lado.
        cls.tela, cls.navegador = desenhar("C4", 15)

    def test_o_enlace_derrubado_sai_tracejado_e_cinza(self):
        pernas = [item for item in self.tela.do_enlace("E-R1-R4") if item.tem("enlace")]
        self.assertEqual(len(pernas), 2)
        for perna in pernas:
            self.assertEqual(perna.opcoes["fill"], COR_FORA)
            self.assertIn("dash", perna.opcoes)

    def test_o_x_e_a_redundancia_que_o_tracejado_sozinho_nao_da(self):
        xis = self.tela.com("x", "enlace:E-R1-R4")
        self.assertEqual(len(xis), 2)  # duas linhas cruzadas

    def test_enlace_no_ar_nao_sai_tracejado(self):
        for perna in self.tela.do_enlace("E-R1-R2"):
            if perna.tem("enlace"):
                self.assertNotIn("dash", perna.opcoes)

    def test_o_caminho_verde_desvia_pelo_r2(self):
        verdes = {item.tags[2] for item in self.tela.com("caminho")}
        self.assertIn("enlace:E-R1-R2", verdes)
        self.assertNotIn("enlace:E-R1-R4", verdes)

    def test_o_enlace_fora_nunca_fica_verde(self):
        """Mesmo que um evento antigo o tivesse percorrido, um enlace fora do
        ar não pode aparecer como caminho — as duas leituras se contradiriam."""
        for item in self.tela.do_enlace("E-R1-R4"):
            self.assertNotEqual(item.opcoes.get("fill"), COR_CAMINHO)


class DescarteNoMapa(unittest.TestCase):
    """C6: o percurso para sobre um enlace, e o mapa mostra onde."""

    def test_o_marcador_fica_vermelho_no_descarte(self):
        tela, navegador = desenhar("C6", 21)
        self.assertEqual(navegador.atual.acao, "DESCARTA")
        marcador = tela.com("marcador")[0]
        self.assertTrue(marcador.tem("enlace:E-R4-R3"))
        self.assertEqual(marcador.opcoes["fill"], COR_ERRO)

    def test_antes_do_descarte_o_marcador_e_verde(self):
        tela, _ = desenhar("C6", 20)
        self.assertEqual(tela.com("marcador")[0].opcoes["fill"], COR_CAMINHO)

    def test_passo_sem_enlace_nao_tem_marcador(self):
        """`GERA` acontece dentro de H1; não há enlace onde pôr o disco."""
        tela, navegador = desenhar("C2", 1)
        self.assertEqual(navegador.atual.acao, "GERA")
        self.assertEqual(tela.com("marcador"), [])


# --------------------------------------------------------------------------
# A mesma coisa contra um Canvas de verdade
# --------------------------------------------------------------------------


def _tela_de_verdade():
    """Um `Canvas` real, ou `None` quando não há tkinter nem display.

    O resto da suíte roda sem tkinter por exigência da seção 13.1, e este
    arquivo continua rodando: a classe abaixo é pulada, não quebrada."""
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

    `dash`, `anchor`, `outline`, `width`, `tags`: a tela de mentira aceita
    qualquer palavra, o `Canvas` não. Sem esta classe, um erro de nome de opção
    só apareceria na inspeção manual — tarde demais."""

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

    def test_o_mapa_desenha_num_canvas_real(self):
        mapa = MapaDaRede(self.tela, carregar_planta(TOPOLOGIA))
        mapa.desenhar(estado_de("C2", 8), LARGURA, ALTURA)
        self.assertEqual(len(self.tela.find_withtag("no")), 18)  # forma + rótulo
        self.assertEqual(len(self.tela.find_withtag("caminho")), 1)
        self.assertEqual(len(self.tela.find_withtag("marcador")), 1)

    def test_o_enlace_fora_sai_tracejado_no_canvas_real(self):
        mapa = MapaDaRede(self.tela, carregar_planta(TOPOLOGIA))
        mapa.desenhar(estado_de("C4", 15), LARGURA, ALTURA)
        pernas = [
            item
            for item in self.tela.find_withtag("enlace:E-R1-R4")
            if "enlace" in self.tela.gettags(item)
        ]
        self.assertEqual(len(pernas), 2)
        for perna in pernas:
            self.assertTrue(str(self.tela.itemcget(perna, "dash")))

    def test_o_desenho_cabe_na_area_visivel(self):
        mapa = MapaDaRede(self.tela, carregar_planta(TOPOLOGIA))
        mapa.desenhar(estado_de("C2", 30), LARGURA, ALTURA)
        x0, y0, x1, y1 = self.tela.bbox(ETIQUETA)
        folga = 4  # a espessura dos traços transborda alguns pixels
        self.assertGreaterEqual(x0, -folga)
        self.assertGreaterEqual(y0, -folga)
        self.assertLessEqual(x1, LARGURA + folga)
        self.assertLessEqual(y1, ALTURA + folga)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
