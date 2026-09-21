"""V3 — a PDU corrente como sequência de blocos proporcionais (issue #50).

A região 4 do layout (seção 9.1). O critério de aceitação da issue é o teste
T-V3 da matriz de rastreabilidade — a soma dos `tam` desenhados bate com
`evento.tamanho` — mais a inspeção visual contra o Anexo C.

O que este arquivo cobra, e a inspeção visual não pegaria: que a interface
**não reordena** nada. A lista de blocos já chega na ordem certa da esquerda
para a direita (issue #2), cabeçalhos à esquerda e finalizador à direita, e
essa ordem é uma afirmação do núcleo sobre o encapsulamento. Uma região que
ordenasse por conta própria — por tamanho, por tipo, pelo que fosse — passaria
despercebida no passo 8 de C2, onde a ordem por acaso coincide, e mentiria em
qualquer outro.

Executar:  python -m unittest tests.test_unidade_dados
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
    COR_BLOCO_CABECALHO,
    COR_BLOCO_DADOS,
    COR_BLOCO_FINALIZADOR,
    ETIQUETA_PDU,
    Navegador,
    UnidadeDeDados,
)

from tests.tela import TelaDeMentira

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")

LARGURA = 1220  # a região 4 ocupa a largura toda da janela
ALTURA = 92


def evento_de(caso: str, passo: int | None = None):
    """O evento do passo pedido (o último, se nenhum)."""
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
    return navegador.atual


def desenhar(caso: str, passo: int | None = None, tela: TelaDeMentira | None = None):
    tela = tela or TelaDeMentira(LARGURA, ALTURA)
    UnidadeDeDados(tela).desenhar(evento_de(caso, passo), LARGURA, ALTURA)
    return tela


def blocos_de(tela: TelaDeMentira):
    """Os retângulos de bloco, da esquerda para a direita."""
    retangulos = [item for item in tela.com("bloco") if item.tipo == "rect"]
    return sorted(retangulos, key=lambda item: item.coordenadas[0])


def largura_de(item) -> float:
    return item.coordenadas[2] - item.coordenadas[0]


def rotulos_desenhados(tela: TelaDeMentira) -> list[str]:
    """Os rótulos dos blocos, na ordem em que aparecem na tela."""
    ordenados = []
    for retangulo in blocos_de(tela):
        etiqueta = next(
            alvo for alvo in retangulo.tags if alvo.startswith("bloco:")
        )
        textos = [
            item.opcoes.get("text", "")
            for item in tela.com(etiqueta)
            if item.tipo == "text"
        ]
        ordenados.append(textos)
    return ordenados


# --------------------------------------------------------------------------
# A ordem é do núcleo, não da interface
# --------------------------------------------------------------------------


class AInterfaceNaoReordena(unittest.TestCase):
    def test_o_passo_8_de_c2_tem_os_seis_blocos_do_enunciado(self):
        tela = desenhar("C2", 8)
        self.assertEqual(len(blocos_de(tela)), 6)

    def test_a_ordem_desenhada_e_a_ordem_recebida(self):
        evento = evento_de("C2", 8)
        tela = desenhar("C2", 8)
        esperada = [bloco.rotulo for bloco in evento.pdu.blocos]
        self.assertEqual(esperada, ["H2", "H3", "H4", "H5", "Dados", "T2"])
        desenhada = [
            next(alvo for alvo in item.tags if alvo.startswith("bloco:")).split(":")[1]
            for item in blocos_de(tela)
        ]
        self.assertEqual(desenhada, esperada)

    def test_cabecalhos_a_esquerda_e_finalizador_a_direita(self):
        tela = desenhar("C2", 8)
        desenhados = blocos_de(tela)
        self.assertTrue(desenhados[0].tem("tipo:cabecalho"))
        self.assertTrue(desenhados[-1].tem("tipo:finalizador"))

    def test_os_blocos_nao_se_sobrepoem_nem_deixam_buraco(self):
        tela = desenhar("C2", 8)
        desenhados = blocos_de(tela)
        for anterior, seguinte in zip(desenhados, desenhados[1:]):
            self.assertAlmostEqual(
                anterior.coordenadas[2], seguinte.coordenadas[0], places=6
            )


# --------------------------------------------------------------------------
# T-V3: a soma dos blocos desenhados é o tamanho do evento
# --------------------------------------------------------------------------


class SomaDosBlocosBateComOTamanho(unittest.TestCase):
    """O critério de aceitação da issue, aplicado a todos os casos.

    Vale para toda PDU de todo passo, e não só para o quadro de 92 B do
    enunciado: a região desenha o que o evento diz que existe."""

    def test_em_todo_evento_com_pdu_de_todos_os_casos(self):
        topologia = carregar_topologia(TOPOLOGIA)
        for caso in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            for evento in executar_caso(topologia, caso):
                if evento.pdu is None:
                    continue
                with self.subTest(caso=caso, passo=evento.passo):
                    soma = sum(bloco.tam for bloco in evento.pdu.blocos)
                    self.assertEqual(soma, evento.tamanho)

    def test_a_referencia_do_enunciado_bate(self):
        evento = evento_de("C2", 8)
        self.assertEqual(
            [(bloco.rotulo, bloco.tam) for bloco in evento.pdu.blocos],
            [("H2", 14), ("H3", 20), ("H4", 8), ("H5", 4), ("Dados", 42), ("T2", 4)],
        )
        self.assertEqual(evento.tamanho, 92)


# --------------------------------------------------------------------------
# A largura é proporcional ao tamanho
# --------------------------------------------------------------------------


class LarguraProporcionalAoTam(unittest.TestCase):
    def test_dados_e_duas_vezes_o_h3_porque_42_e_o_dobro_de_20(self):
        # Escolhidos dois blocos grandes de propósito: é onde o piso mínimo
        # não interfere e a proporção pode ser cobrada com folga.
        tela = desenhar("C2", 8)
        por_rotulo = {
            next(a for a in item.tags if a.startswith("bloco:")).split(":")[1]: item
            for item in blocos_de(tela)
        }
        proporcao = largura_de(por_rotulo["Dados"]) / largura_de(por_rotulo["H3"])
        self.assertAlmostEqual(proporcao, 42 / 20, delta=0.08)

    def test_os_blocos_ocupam_a_largura_util_inteira(self):
        tela = desenhar("C2", 8)
        desenhados = blocos_de(tela)
        ocupado = desenhados[-1].coordenadas[2] - desenhados[0].coordenadas[0]
        self.assertGreater(ocupado, LARGURA * 0.8)

    def test_o_bloco_menor_nao_some(self):
        # H5 tem 4 B contra os 42 B dos dados: sem piso, viraria um risco
        # ilegível e o rótulo não caberia.
        tela = desenhar("C2", 8)
        menores = [item for item in blocos_de(tela) if largura_de(item) > 0]
        self.assertEqual(len(menores), 6)
        self.assertGreaterEqual(min(largura_de(item) for item in menores), 18)

    def test_numa_janela_estreita_o_piso_entra_em_acao(self):
        # É para isto que o piso existe: com 260 px, os 4 B do H5 dariam uns
        # 8 px proporcionais e o rótulo não caberia.
        estreita = TelaDeMentira(260, ALTURA)
        UnidadeDeDados(estreita).desenhar(evento_de("C2", 8), 260, ALTURA)
        desenhados = blocos_de(estreita)
        self.assertEqual(len(desenhados), 6)
        self.assertGreaterEqual(min(largura_de(item) for item in desenhados), 18)

    def test_mesmo_com_piso_a_soma_fecha_na_largura_util(self):
        estreita = TelaDeMentira(260, ALTURA)
        UnidadeDeDados(estreita).desenhar(evento_de("C2", 8), 260, ALTURA)
        desenhados = blocos_de(estreita)
        for anterior, seguinte in zip(desenhados, desenhados[1:]):
            self.assertAlmostEqual(
                anterior.coordenadas[2], seguinte.coordenadas[0], places=6
            )
        self.assertLessEqual(desenhados[-1].coordenadas[2], 260)

    def test_o_bloco_grande_continua_o_maior_na_janela_estreita(self):
        # O piso não pode inverter a ordem de grandeza: `Dados` (42 B) segue
        # mais largo que qualquer cabeçalho.
        estreita = TelaDeMentira(260, ALTURA)
        UnidadeDeDados(estreita).desenhar(evento_de("C2", 8), 260, ALTURA)
        por_rotulo = {
            next(a for a in item.tags if a.startswith("bloco:")).split(":")[1]: item
            for item in blocos_de(estreita)
        }
        maior = max(por_rotulo.values(), key=largura_de)
        self.assertIs(maior, por_rotulo["Dados"])

    def test_uma_pdu_de_bloco_unico_ocupa_tudo(self):
        tela = desenhar("C2", 1)  # Mensagem, só o bloco de dados
        desenhados = blocos_de(tela)
        self.assertEqual(len(desenhados), 1)
        self.assertGreater(largura_de(desenhados[0]), LARGURA * 0.8)


# --------------------------------------------------------------------------
# Rótulos, título e cores (seções 9.1 e 9.3)
# --------------------------------------------------------------------------


class RotulosETitulo(unittest.TestCase):
    def test_cada_bloco_mostra_rotulo_e_tamanho(self):
        tela = desenhar("C2", 8)
        for textos in rotulos_desenhados(tela):
            self.assertTrue(textos, "todo bloco precisa de rótulo")
        juntos = " ".join(" ".join(t) for t in rotulos_desenhados(tela))
        for esperado in ("H2", "14", "H3", "20", "Dados", "42", "T2", "4"):
            self.assertIn(esperado, juntos)

    def test_o_titulo_nomeia_a_unidade_e_o_quadro(self):
        tela = desenhar("C2", 8)
        self.assertTrue(
            any("Quadro Q1" in texto for texto in tela.textos()),
            f"o título deveria dizer 'Quadro Q1'; achei {tela.textos()}",
        )

    def test_o_titulo_sem_quadro_mostra_so_o_nome_da_unidade(self):
        tela = desenhar("C2", 1)  # Mensagem — ainda não há quadro
        self.assertTrue(any("Mensagem" in texto for texto in tela.textos()))
        self.assertFalse(any("None" in texto for texto in tela.textos()))

    def test_o_tamanho_total_aparece(self):
        tela = desenhar("C2", 8)
        self.assertTrue(
            any("92 B" in texto for texto in tela.textos()),
            f"faltou o total '92 B'; achei {tela.textos()}",
        )


class CoresPorTipoDeBloco(unittest.TestCase):
    def test_cabecalho_dados_e_finalizador_tem_cores_distintas(self):
        tela = desenhar("C2", 8)
        por_tipo = {}
        for item in blocos_de(tela):
            tipo = next(a for a in item.tags if a.startswith("tipo:")).split(":")[1]
            por_tipo[tipo] = item.opcoes.get("fill")
        self.assertEqual(por_tipo["cabecalho"], COR_BLOCO_CABECALHO)
        self.assertEqual(por_tipo["dados"], COR_BLOCO_DADOS)
        self.assertEqual(por_tipo["finalizador"], COR_BLOCO_FINALIZADOR)

    def test_o_bloco_de_dados_tem_borda_visivel(self):
        # Seção 9.3: o bloco de dados é branco, e é a borda que o separa do
        # fundo numa impressão em preto e branco.
        tela = desenhar("C2", 8)
        dados = [item for item in blocos_de(tela) if item.tem("tipo:dados")]
        self.assertEqual(len(dados), 1)
        self.assertTrue(dados[0].opcoes.get("outline"))
        self.assertGreaterEqual(dados[0].opcoes.get("width", 0), 1)

    def test_todo_bloco_tem_rotulo_alem_da_cor(self):
        # O segundo canal da seção 9.3 para os três tipos de bloco.
        tela = desenhar("C2", 8)
        for textos in rotulos_desenhados(tela):
            self.assertTrue(any(texto.strip() for texto in textos))


# --------------------------------------------------------------------------
# Eventos sem PDU e convivência com as outras regiões
# --------------------------------------------------------------------------


class EventoSemPdu(unittest.TestCase):
    def test_o_metricas_final_nao_mostra_a_pdu_do_passo_anterior(self):
        # Mostrar o quadro obsoleto seria pior que não mostrar nada: o leitor
        # não teria como saber que aquilo não é mais a unidade corrente.
        tela = desenhar("C2")
        self.assertEqual(blocos_de(tela), [])

    def test_o_evento_sem_pdu_ainda_rotula_a_regiao(self):
        tela = desenhar("C2")
        self.assertTrue(
            tela.textos(), "a região não pode sumir: fica rotulada e vazia"
        )


class RegiaoNaoInvadeAsOutras(unittest.TestCase):
    def test_redesenhar_apaga_so_a_etiqueta_da_pdu(self):
        tela = TelaDeMentira(LARGURA, ALTURA)
        regiao = UnidadeDeDados(tela)
        regiao.desenhar(evento_de("C2", 8), LARGURA, ALTURA)
        regiao.desenhar(evento_de("C2", 11), LARGURA, ALTURA)
        self.assertEqual(set(tela.apagou), {ETIQUETA_PDU})

    def test_tudo_leva_a_etiqueta_da_regiao(self):
        tela = desenhar("C2", 8)
        self.assertTrue(tela.itens)
        for item in tela.itens:
            self.assertTrue(
                item.tem(ETIQUETA_PDU), f"{item!r} escaparia da limpeza da região"
            )

    def test_nada_e_desenhado_fora_da_tela(self):
        for caso, passo in (("C2", 8), ("C7", 8), ("C2", 1)):
            tela = desenhar(caso, passo)
            for item in tela.itens:
                with self.subTest(caso=caso, passo=passo, item=repr(item)):
                    self.assertGreaterEqual(min(item.coordenadas[0::2]), 0)
                    self.assertLessEqual(max(item.coordenadas[0::2]), LARGURA)
                    self.assertGreaterEqual(min(item.coordenadas[1::2]), 0)
                    self.assertLessEqual(max(item.coordenadas[1::2]), ALTURA)


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
    """`anchor`, `outline`, `width`, `font`: a tela de mentira aceita qualquer
    palavra, o `Canvas` não."""

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

    def test_a_pdu_desenha_num_canvas_real(self):
        UnidadeDeDados(self.tela).desenhar(evento_de("C2", 8), LARGURA, ALTURA)
        # caixa + rótulo + tamanho por bloco, mais título e total da região
        self.assertEqual(len(self.tela.find_withtag("bloco")), 6 * 3)
        self.assertEqual(len(self.tela.find_withtag("titulo")), 1)
        self.assertEqual(len(self.tela.find_withtag("total")), 1)

    def test_a_ancora_do_titulo_e_aceita_pelo_canvas_real(self):
        UnidadeDeDados(self.tela).desenhar(evento_de("C2", 8), LARGURA, ALTURA)
        titulo = self.tela.find_withtag("titulo")[0]
        self.assertEqual(self.tela.itemcget(titulo, "anchor"), "w")
        total = self.tela.find_withtag("total")[0]
        self.assertEqual(self.tela.itemcget(total, "anchor"), "e")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
