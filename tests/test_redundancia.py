"""Redundância visual: nenhuma informação depende só de cor (issue #52).

O checkpoint de acessibilidade que fecha F5. Percorre as nove linhas da tabela
da seção 9.3 e, para cada uma, cobra o **segundo canal**: espessura, contorno,
tracejado, símbolo ou texto. O critério é concreto e vale a pena enunciá-lo do
jeito que os testes o aplicam — *se a tela fosse impressa em preto e branco,
ou lida por quem não distingue as cores em questão, a informação continuaria
lá?*

Não é zelo abstrato. A proposta técnica pede capturas de tela no relatório, e
uma captura vira preto e branco com facilidade; e um estado que só o vermelho
anuncia é um estado que uma parte da turma não vê.

O arquivo é deliberadamente chato: uma classe por linha da tabela, o nome do
teste repetindo o segundo canal exigido. Quando alguém acrescentar uma região
em F6, é para cá que a linha nova vem.

Executar:  python -m unittest tests.test_redundancia
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
    COR_ERRO,
    ETIQUETA_ERRO,
    LARGURA_CAMINHO,
    LARGURA_CAIXA_ATIVA,
    LARGURA_CAIXA_INATIVA,
    LARGURA_DECISAO,
    LARGURA_ENLACE,
    EstadoDasPilhas,
    EstadoDoMapa,
    EstadoDosEnderecos,
    MapaDaRede,
    Navegador,
    PaineisDeEndereco,
    PilhasDosDispositivos,
    UnidadeDeDados,
    carregar_planta,
)

from tests.tela import TelaDeMentira

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")

LARGURA = 900
ALTURA = 340


def _ate(caso: str, passo: int | None = None):
    navegador = Navegador(executar_caso(carregar_topologia(TOPOLOGIA), caso))
    if passo is None:
        navegador.ultimo()
    else:
        navegador.ir_para(
            next(
                i
                for i, evento in enumerate(navegador.eventos)
                if evento.passo == passo and not evento.secundario
            )
        )
    return navegador


def mapa_de(caso: str, passo: int | None = None) -> TelaDeMentira:
    tela = TelaDeMentira(LARGURA, ALTURA)
    MapaDaRede(tela, carregar_planta(TOPOLOGIA)).desenhar(
        EstadoDoMapa.ate(_ate(caso, passo).ate_agora()), LARGURA, ALTURA
    )
    return tela


def pilhas_de(caso: str, passo: int | None = None) -> TelaDeMentira:
    tela = TelaDeMentira(LARGURA, ALTURA)
    PilhasDosDispositivos(tela, carregar_planta(TOPOLOGIA)).desenhar(
        EstadoDasPilhas.ate(_ate(caso, passo).ate_agora()), LARGURA, ALTURA
    )
    return tela


def pdu_de(caso: str, passo: int | None = None) -> TelaDeMentira:
    tela = TelaDeMentira(LARGURA, 92)
    UnidadeDeDados(tela).desenhar(_ate(caso, passo).atual, LARGURA, 92)
    return tela


def enderecos_de(caso: str, passo: int | None = None) -> TelaDeMentira:
    tela = TelaDeMentira(LARGURA, 76)
    PaineisDeEndereco(tela).desenhar(
        EstadoDosEnderecos.ate(_ate(caso, passo).ate_agora()), LARGURA, 76
    )
    return tela


def caixa(tela: TelaDeMentira, dispositivo: str, camada: int):
    return [
        item
        for item in tela.com(f"camada:{dispositivo}:{camada}")
        if item.tipo == "rect"
    ][0]


# --------------------------------------------------------------------------
# Linhas 1 e 2 — camada ativa / camada inativa
# --------------------------------------------------------------------------


class CamadaAtivaTemContornoAlemDoAzul(unittest.TestCase):
    def test_a_ativa_e_mais_grossa_que_a_inativa(self):
        tela = pilhas_de("C2", 8)
        self.assertEqual(caixa(tela, "H1", 1).opcoes["width"], LARGURA_CAIXA_ATIVA)
        self.assertEqual(caixa(tela, "H1", 5).opcoes["width"], LARGURA_CAIXA_INATIVA)
        self.assertGreater(LARGURA_CAIXA_ATIVA, LARGURA_CAIXA_INATIVA)

    def test_ignorando_a_cor_ainda_da_para_achar_a_ativa(self):
        # A simulação do preto e branco: descartadas as cores, sobra a
        # espessura, e ela sozinha aponta uma caixa só.
        tela = pilhas_de("C2", 8)
        grossas = [
            item
            for item in tela.com("pilha:H1")
            if item.tipo == "rect" and item.opcoes["width"] >= LARGURA_CAIXA_ATIVA
        ]
        self.assertEqual(len(grossas), 1)
        self.assertTrue(grossas[0].tem("camada:H1:1"))


# --------------------------------------------------------------------------
# Linha 3 — decisão de rota
# --------------------------------------------------------------------------


class DecisaoDeRotaJaEContorno(unittest.TestCase):
    def test_o_contorno_da_decisao_e_mais_grosso_que_o_da_camada_ativa(self):
        tela = pilhas_de("C2", 11)
        self.assertEqual(caixa(tela, "R1", 3).opcoes["width"], LARGURA_DECISAO)
        self.assertGreater(LARGURA_DECISAO, LARGURA_CAIXA_ATIVA)

    def test_ignorando_a_cor_a_decisao_continua_a_mais_destacada(self):
        tela = pilhas_de("C2", 11)
        mais_grossa = max(
            (item for item in tela.itens if item.tipo == "rect"),
            key=lambda item: item.opcoes["width"],
        )
        self.assertTrue(mais_grossa.tem("camada:R1:3"))


# --------------------------------------------------------------------------
# Linha 4 — descarte / erro (a que mais precisava de um segundo canal)
# --------------------------------------------------------------------------


class DescarteTemSimboloAlemDoVermelho(unittest.TestCase):
    def test_o_descarte_por_crc_em_c6_marca_a_pilha(self):
        # C6, passo 21: R3 descarta o quadro com CRC inválido.
        tela = pilhas_de("C6", 21)
        self.assertTrue(
            tela.com(ETIQUETA_ERRO),
            "o descarte precisa de um símbolo, não só do vermelho",
        )

    def test_o_descarte_sem_rota_em_c5_tambem_marca(self):
        # C5, passo 11: R1 descarta por falta de rota. Não há enlace no
        # evento, então o marcador do mapa não aparece — sem a marca na
        # pilha, o descarte não estaria em lugar nenhum da tela.
        tela = pilhas_de("C5", 11)
        self.assertTrue(tela.com(ETIQUETA_ERRO))

    def test_o_simbolo_do_descarte_e_texto_de_verdade(self):
        tela = pilhas_de("C6", 21)
        simbolos = [item for item in tela.com(ETIQUETA_ERRO) if item.tipo == "text"]
        self.assertTrue(simbolos)
        self.assertTrue(simbolos[0].opcoes.get("text", "").strip())

    def test_um_passo_sem_erro_nao_tem_marca(self):
        self.assertEqual(pilhas_de("C2", 11).com(ETIQUETA_ERRO), [])
        self.assertEqual(pilhas_de("C6", 20).com(ETIQUETA_ERRO), [])

    def test_o_marcador_de_erro_do_mapa_tem_simbolo(self):
        tela = mapa_de("C6", 21)
        vermelhos = [
            item for item in tela.itens if item.opcoes.get("fill") == COR_ERRO
        ]
        self.assertTrue(vermelhos, "C6 deveria pintar o marcador de erro")
        self.assertTrue(
            tela.com(ETIQUETA_ERRO),
            "o marcador vermelho precisa de um símbolo junto",
        )

    def test_a_unidade_de_dados_anuncia_o_descarte_por_extenso(self):
        juntos = " ".join(pdu_de("C6", 21).textos())
        self.assertIn("descartad", juntos.lower())


# --------------------------------------------------------------------------
# Linhas 5 e 6 — caminho percorrido / enlace fora do ar
# --------------------------------------------------------------------------


class CaminhoTemEspessura(unittest.TestCase):
    def test_o_traco_do_caminho_e_mais_grosso_que_o_do_enlace_comum(self):
        tela = mapa_de("C2", 8)
        acesos = [
            item
            for item in tela.com("caminho")
            if item.opcoes.get("width") == LARGURA_CAMINHO
        ]
        self.assertTrue(acesos)
        self.assertGreater(LARGURA_CAMINHO, LARGURA_ENLACE)


class EnlaceForaTemTracejadoEX(unittest.TestCase):
    def test_o_enlace_derrubado_de_c4_sai_tracejado(self):
        tela = mapa_de("C4", 15)
        tracejados = [item for item in tela.itens if item.opcoes.get("dash")]
        self.assertTrue(tracejados, "o enlace fora do ar precisa do tracejado")

    def test_e_ganha_o_x_por_cima(self):
        # O X é o canal que sobrevive ao preto e branco: tracejado sozinho
        # poderia ser confundido com um enlace de outro tipo.
        tela = mapa_de("C4", 15)
        self.assertTrue(tela.com("fora"))


# --------------------------------------------------------------------------
# Linhas 7 a 9 — os três tipos de bloco da PDU
# --------------------------------------------------------------------------


class BlocosTemRotuloAlemDaCor(unittest.TestCase):
    def setUp(self):
        self.tela = pdu_de("C2", 8)

    def _textos_do_bloco(self, rotulo: str) -> str:
        return " ".join(
            item.opcoes.get("text", "")
            for item in self.tela.com(f"bloco:{rotulo}")
            if item.tipo == "text"
        )

    def test_o_cabecalho_diz_o_proprio_nome(self):
        self.assertIn("H2", self._textos_do_bloco("H2"))

    def test_o_finalizador_diz_o_proprio_nome(self):
        self.assertIn("T2", self._textos_do_bloco("T2"))

    def test_o_bloco_de_dados_tem_borda_visivel(self):
        dados = [item for item in self.tela.com("tipo:dados") if item.tipo == "rect"][0]
        self.assertTrue(dados.opcoes.get("outline"))
        self.assertGreaterEqual(dados.opcoes.get("width", 0), 1)

    def test_todo_bloco_tem_texto_dentro(self):
        retangulos = [item for item in self.tela.com("bloco") if item.tipo == "rect"]
        self.assertEqual(len(retangulos), 6)
        for item in retangulos:
            rotulo = next(a for a in item.tags if a.startswith("bloco:")).split(":")[1]
            with self.subTest(bloco=rotulo):
                self.assertTrue(self._textos_do_bloco(rotulo).strip())


# --------------------------------------------------------------------------
# A varredura final: nenhuma região distingue estado só por cor
# --------------------------------------------------------------------------


class NenhumEstadoDependeSoDeCor(unittest.TestCase):
    """A prova por eliminação: apaga todas as cores e compara os desenhos.

    Se dois passos que o usuário precisa distinguir ficam idênticos depois de
    remover `fill` e `outline`, então a diferença entre eles era só cor — e é
    exatamente isso que a issue proíbe."""

    @staticmethod
    def _sem_cor(tela: TelaDeMentira):
        return [
            (
                item.tipo,
                tuple(round(c, 3) for c in item.coordenadas),
                item.opcoes.get("width"),
                item.opcoes.get("dash"),
                item.opcoes.get("text"),
                item.tags,
            )
            for item in tela.itens
        ]

    def test_camada_ativa_e_inativa_diferem_sem_cor(self):
        ativa = pilhas_de("C2", 8)
        outra = pilhas_de("C2", 7)
        self.assertNotEqual(self._sem_cor(ativa), self._sem_cor(outra))

    def test_decisao_de_rota_difere_do_passo_vizinho_sem_cor(self):
        self.assertNotEqual(
            self._sem_cor(pilhas_de("C2", 11)), self._sem_cor(pilhas_de("C2", 10))
        )

    def test_descarte_difere_do_passo_anterior_sem_cor(self):
        self.assertNotEqual(
            self._sem_cor(pilhas_de("C6", 21)), self._sem_cor(pilhas_de("C6", 20))
        )

    def test_substituicao_de_endereco_difere_sem_cor(self):
        self.assertNotEqual(
            self._sem_cor(enderecos_de("C2", 12)),
            self._sem_cor(enderecos_de("C2", 13)),
        )

    def test_enlace_fora_difere_do_enlace_no_ar_sem_cor(self):
        self.assertNotEqual(
            self._sem_cor(mapa_de("C4", 15)), self._sem_cor(mapa_de("C2", 15))
        )


# --------------------------------------------------------------------------
# As linhas que a F6 acrescentou à tabela
# --------------------------------------------------------------------------


class ControlesTemSegundoCanal(unittest.TestCase):
    def test_a_linha_corrente_do_registro_tem_realce_e_rolagem(self):
        # A rolagem automática é o segundo canal do realce de fundo: mesmo sem
        # distinguir o amarelo, a linha corrente é a que está à vista.
        from tests.test_registro import TextoDeMentira
        from visual import RegistroNaTela

        alvo = TextoDeMentira()
        RegistroNaTela(alvo).desenhar(
            executar_caso(carregar_topologia(TOPOLOGIA), "C2"), indice=20
        )
        self.assertTrue(alvo.marcas)
        self.assertIsNotNone(alvo.visivel)

    def test_a_camada_agrupada_do_tcpip_diz_o_proprio_nome(self):
        # No modelo OSI a caixa mostra um algarismo; no TCP/IP, o nome da
        # camada. Nos dois casos há texto dentro — a cor nunca é o único
        # canal (seção 9.3).
        from visual import MODELO_TCPIP

        tela = TelaDeMentira(LARGURA, ALTURA)
        PilhasDosDispositivos(tela, carregar_planta(TOPOLOGIA)).desenhar(
            EstadoDasPilhas.ate(_ate("C2", 8).ate_agora()),
            LARGURA,
            ALTURA,
            modelo=MODELO_TCPIP,
        )
        rotulos = [
            item.opcoes.get("text", "")
            for item in tela.com("pilha:H1")
            if item.tipo == "text"
        ]
        self.assertIn("Aplicação", rotulos)
        self.assertTrue(all(texto.strip() for texto in rotulos))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
