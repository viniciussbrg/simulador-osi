"""V4 — os dois painéis de endereço lado a lado (issue #51).

A região 5 do layout (seção 9.1). Os dois painéis existem para tornar visível
a restrição R3: o par lógico é gravado uma única vez, na camada 3 da origem, e
atravessa a rede inteiro; o par físico é substituído a cada salto. Em C2 isso
dá um lógico constante do passo 5 ao 26 contra quatro pares físicos
diferentes, e é exatamente essa contagem que `OContrasteEntreOsDoisPares`
cobra — a afirmação mais forte do arquivo, porque é a que quebraria se alguém
passasse a escrever o par lógico em cada salto.

O outro lado é o do valor obsoleto. Nos passos em que a PDU é um pacote
(camada 3 para cima) não há par físico ativo, e o enunciado é explícito:
indicar isso, nunca deixar na tela o endereço do salto anterior. Um painel que
mantivesse o último MAC visível ensinaria o oposto do que a região existe para
ensinar.

Executar:  python -m unittest tests.test_enderecos
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
    AUSENTE,
    COR_DESTAQUE_FISICO,
    ETIQUETA_ENDERECOS,
    EstadoDosEnderecos,
    Navegador,
    PaineisDeEndereco,
)

from tests.tela import TelaDeMentira

TOPOLOGIA = os.path.join(_RAIZ, "topologia.json")

LARGURA = 1220  # a região 5 ocupa a largura toda, dividida em dois painéis
ALTURA = 76


def _navegador(caso: str) -> Navegador:
    return Navegador(executar_caso(carregar_topologia(TOPOLOGIA), caso))


def estado_de(caso: str, passo: int | None = None) -> EstadoDosEnderecos:
    navegador = _navegador(caso)
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
    return EstadoDosEnderecos.ate(navegador.ate_agora())


def desenhar(caso: str, passo: int | None = None, tela: TelaDeMentira | None = None):
    tela = tela or TelaDeMentira(LARGURA, ALTURA)
    PaineisDeEndereco(tela).desenhar(estado_de(caso, passo), LARGURA, ALTURA)
    return tela


def textos_do_painel(tela: TelaDeMentira, painel: str) -> list[str]:
    return [
        item.opcoes.get("text", "")
        for item in tela.com(f"painel:{painel}")
        if item.tipo == "text"
    ]


# --------------------------------------------------------------------------
# O contraste que a região existe para mostrar (restrição R3)
# --------------------------------------------------------------------------


class OContrasteEntreOsDoisPares(unittest.TestCase):
    def test_em_c2_o_par_logico_e_um_so_do_inicio_ao_fim(self):
        distintos = {
            estado_de("C2", evento.passo).logico
            for evento in _navegador("C2").eventos
            if evento.logico is not None and not evento.secundario
        }
        self.assertEqual(distintos, {("10.0.1.10", "10.0.3.10")})

    def test_em_c2_os_pares_fisicos_sao_quatro(self):
        # Um por salto: H1–R1, R1–R4, R4–R3, R3–H4 (tabela 6.5).
        distintos = {
            evento.fisico
            for evento in _navegador("C2").eventos
            if evento.fisico is not None and not evento.secundario
        }
        self.assertEqual(len(distintos), 4)

    def test_o_logico_da_origem_sobrevive_ate_o_destino(self):
        # Passo 5 é a camada 3 de H1, que grava o par; passo 26 é a camada 3
        # de H4, que o lê. R3 em uma linha.
        self.assertEqual(estado_de("C2", 5).logico, estado_de("C2", 26).logico)

    def test_o_fisico_da_primeira_perna_nao_e_o_da_ultima(self):
        self.assertNotEqual(estado_de("C2", 8).fisico, estado_de("C2", 23).fisico)


# --------------------------------------------------------------------------
# A troca de par físico
# --------------------------------------------------------------------------


class TrocaDeParFisico(unittest.TestCase):
    def test_os_quatro_passos_de_substituicao_de_c2(self):
        trocaram = [
            evento.passo
            for evento in _navegador("C2").eventos
            if not evento.secundario
            and estado_de("C2", evento.passo).fisico_mudou
        ]
        self.assertEqual(trocaram, [7, 12, 17, 22])

    def test_repetir_o_mesmo_par_nao_conta_como_troca(self):
        # 8 transmite com o mesmo par que 7 enquadrou.
        self.assertTrue(estado_de("C2", 7).fisico_mudou)
        self.assertFalse(estado_de("C2", 8).fisico_mudou)
        self.assertFalse(estado_de("C2", 9).fisico_mudou)

    def test_o_primeiro_evento_do_caso_nao_e_uma_troca(self):
        self.assertFalse(estado_de("C2", 1).fisico_mudou)

    def test_sem_eventos_nao_ha_retrato(self):
        with self.assertRaises(ValueError):
            EstadoDosEnderecos.ate(())


# --------------------------------------------------------------------------
# O valor ausente, que nunca vira valor obsoleto
# --------------------------------------------------------------------------


class ParFisicoAusente(unittest.TestCase):
    def test_na_camada_3_nao_ha_par_fisico(self):
        self.assertIsNone(estado_de("C2", 11).fisico)
        self.assertTrue(estado_de("C2", 11).fisico_ausente)

    def test_o_painel_nao_mostra_o_mac_do_salto_anterior(self):
        # Passo 10 tem AA:…:01:0A; o passo 11 não pode exibi-lo.
        anterior = estado_de("C2", 10)
        self.assertIsNotNone(anterior.fisico)
        tela = desenhar("C2", 11)
        juntos = " ".join(textos_do_painel(tela, "fisico"))
        for endereco in anterior.fisico:
            self.assertNotIn(endereco, juntos)

    def test_o_painel_ausente_diz_que_esta_ausente(self):
        tela = desenhar("C2", 11)
        self.assertIn(AUSENTE, " ".join(textos_do_painel(tela, "fisico")))

    def test_o_logico_tambem_some_quando_nao_ha(self):
        # Camadas 4 a 7: a PDU ainda não tem par lógico. Mostrar o último
        # seria o mesmo erro do painel físico, do outro lado da tela.
        self.assertIsNone(estado_de("C2", 2).logico)
        tela = desenhar("C2", 30)
        self.assertIn(AUSENTE, " ".join(textos_do_painel(tela, "logico")))
        self.assertNotIn("10.0.1.10", " ".join(textos_do_painel(tela, "logico")))


# --------------------------------------------------------------------------
# O desenho dos dois painéis
# --------------------------------------------------------------------------


class DoisPaineisLadoALado(unittest.TestCase):
    def test_o_logico_fica_a_esquerda_do_fisico(self):
        tela = desenhar("C2", 8)
        moldura_logico = [i for i in tela.com("painel:logico") if i.tipo == "rect"][0]
        moldura_fisico = [i for i in tela.com("painel:fisico") if i.tipo == "rect"][0]
        self.assertLess(moldura_logico.coordenadas[0], moldura_fisico.coordenadas[0])
        self.assertLessEqual(
            moldura_logico.coordenadas[2], moldura_fisico.coordenadas[0]
        )

    def test_os_dois_titulos_aparecem(self):
        tela = desenhar("C2", 8)
        juntos = " ".join(tela.textos())
        self.assertIn("lógicos", juntos)
        self.assertIn("físicos", juntos)

    def test_os_subtitulos_dizem_a_diferenca_por_extenso(self):
        # O contraste não pode depender da borda amarela: o texto é o canal
        # que sobrevive a uma impressão em preto e branco (seção 9.3).
        tela = desenhar("C2", 8)
        juntos = " ".join(tela.textos())
        self.assertIn("constantes de ponta a ponta", juntos)
        self.assertIn("substituídos a cada salto", juntos)

    def test_o_painel_logico_tem_cadeado(self):
        tela = desenhar("C2", 8)
        self.assertIn("🔒", " ".join(textos_do_painel(tela, "logico")))

    def test_os_enderecos_saem_em_fonte_monoespacada(self):
        tela = desenhar("C2", 8)
        valores = [
            item
            for item in tela.com("painel:logico", "valor")
            if item.tipo == "text"
        ]
        self.assertTrue(valores)
        for item in valores:
            self.assertEqual(item.opcoes.get("font", ("",))[0], "TkFixedFont")

    def test_os_valores_desenhados_sao_os_do_evento(self):
        estado = estado_de("C2", 8)
        tela = desenhar("C2", 8)
        juntos = " ".join(tela.textos())
        for endereco in estado.logico + estado.fisico:
            self.assertIn(endereco, juntos)

    def test_origem_e_destino_sao_rotulados(self):
        tela = desenhar("C2", 8)
        juntos = " ".join(textos_do_painel(tela, "fisico"))
        self.assertIn("origem", juntos)
        self.assertIn("destino", juntos)


class DestaqueDaSubstituicao(unittest.TestCase):
    def test_a_moldura_do_fisico_acende_na_troca(self):
        tela = desenhar("C2", 12)
        moldura = [i for i in tela.com("painel:fisico") if i.tipo == "rect"][0]
        self.assertEqual(moldura.opcoes.get("outline"), COR_DESTAQUE_FISICO)

    def test_fora_da_troca_a_moldura_nao_fica_acesa(self):
        tela = desenhar("C2", 13)
        moldura = [i for i in tela.com("painel:fisico") if i.tipo == "rect"][0]
        self.assertNotEqual(moldura.opcoes.get("outline"), COR_DESTAQUE_FISICO)

    def test_a_troca_tem_aviso_de_texto_alem_da_cor(self):
        # Segundo canal: quem não distingue o amarelo ainda lê o aviso. Ele
        # vem em elemento próprio (etiqueta `aviso`) porque embutido no
        # subtítulo seria indistinguível do "substituídos a cada salto" que
        # está sempre lá.
        aceso = desenhar("C2", 12).com("painel:fisico", "aviso")
        self.assertEqual(len(aceso), 1)
        self.assertIn("substituído", aceso[0].opcoes.get("text", ""))
        self.assertEqual(desenhar("C2", 13).com("painel:fisico", "aviso"), [])

    def test_o_painel_logico_nunca_tem_aviso_de_substituicao(self):
        for passo in (5, 7, 12, 17, 22, 26):
            with self.subTest(passo=passo):
                self.assertEqual(
                    desenhar("C2", passo).com("painel:logico", "aviso"), []
                )

    def test_o_painel_logico_nunca_acende(self):
        for passo in (5, 7, 12, 17, 22, 26):
            tela = desenhar("C2", passo)
            moldura = [i for i in tela.com("painel:logico") if i.tipo == "rect"][0]
            with self.subTest(passo=passo):
                self.assertNotEqual(
                    moldura.opcoes.get("outline"), COR_DESTAQUE_FISICO
                )


class RegiaoNaoInvadeAsOutras(unittest.TestCase):
    def test_redesenhar_apaga_so_a_etiqueta_dos_enderecos(self):
        tela = TelaDeMentira(LARGURA, ALTURA)
        regiao = PaineisDeEndereco(tela)
        regiao.desenhar(estado_de("C2", 8), LARGURA, ALTURA)
        regiao.desenhar(estado_de("C2", 12), LARGURA, ALTURA)
        self.assertEqual(set(tela.apagou), {ETIQUETA_ENDERECOS})

    def test_tudo_leva_a_etiqueta_da_regiao(self):
        tela = desenhar("C2", 8)
        self.assertTrue(tela.itens)
        for item in tela.itens:
            self.assertTrue(
                item.tem(ETIQUETA_ENDERECOS),
                f"{item!r} escaparia da limpeza da região",
            )

    def test_nada_e_desenhado_fora_da_tela(self):
        for caso, passo in (("C2", 8), ("C2", 11), ("C5", 6), ("C7", 8)):
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
    """Aqui há uma razão a mais que nas outras regiões: o cadeado e a seta do
    aviso são caracteres fora do ASCII, e é bom saber que o `Canvas` os aceita
    antes da inspeção manual."""

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

    def test_os_paineis_desenham_num_canvas_real(self):
        PaineisDeEndereco(self.tela).desenhar(estado_de("C2", 8), LARGURA, ALTURA)
        # moldura + título + subtítulo + (rótulo + valor) x2, por painel
        self.assertEqual(len(self.tela.find_withtag("painel:logico")), 7)
        self.assertEqual(len(self.tela.find_withtag("painel:fisico")), 7)

    def test_o_cadeado_e_a_moldura_acesa_sao_aceitos(self):
        PaineisDeEndereco(self.tela).desenhar(estado_de("C2", 12), LARGURA, ALTURA)
        moldura = [
            item
            for item in self.tela.find_withtag("painel:fisico")
            if self.tela.type(item) == "rectangle"
        ][0]
        self.assertEqual(self.tela.itemcget(moldura, "outline"), COR_DESTAQUE_FISICO)
        textos = [
            self.tela.itemcget(item, "text")
            for item in self.tela.find_withtag("painel:logico")
            if self.tela.type(item) == "text"
        ]
        self.assertTrue(any("🔒" in texto for texto in textos))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
