"""T-FMT — o formato exato do registro (issue #34).

Seção 8.4: *"as doze primeiras linhas do caso C2 devem reproduzir caractere a
caractere o exemplo apresentado na Seção 5.1 do enunciado"*. É o teste que
converte o enunciado em suíte — igualdade de string, não comparação
aproximada, porque o que está sendo conferido é justamente o preenchimento
entre a descrição e o tamanho.

A gramática está na seção 8.1: `NNN | DISP | LN | ACAO | descrição   TTT B`.
O tamanho é alinhado numa **coluna fixa** — é isso que faz o registro ficar
legível em fonte monoespaçada, na tela e no arquivo salvo. Linha cuja
descrição passa da coluna cede: recebe o mínimo de dois espaços e empurra o
tamanho para a direita, como a linha 010.

O oráculo é duplo, de propósito: as doze linhas do enunciado ficam escritas
aqui, à mão, e as trinta do registro são comparadas com o registro esperado
de C2 guardado em `tests/fixtures/registro_c2_esperado.txt`. Uma especificação
editada sem o código junto quebra o teste, que é o comportamento desejado — o
registro esperado é especificação, não ilustração.

Executar:  python -m unittest tests.test_formato
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais

_REGISTRO_ESPERADO = os.path.join(_RAIZ, "tests", "fixtures", "registro_c2_esperado.txt")

# As doze primeiras linhas do exemplo do enunciado (seção 5.1), copiadas à mão
# porque são o critério, não um resultado. Se o motor mudar o que quer que seja
# — passo, ação, descrição, contabilidade de octetos, preenchimento — é aqui
# que a mudança aparece.
DOZE_PRIMEIRAS = """\
001 | H1 | L7 | GERA | processo navegador, destino servidorWeb             42 B
002 | H1 | L6 | CODIFICA | octetos UTF-8, conteúdo cifrado                 42 B
003 | H1 | L5 | ABRE | sessão S-0001 estabelecida                          46 B
004 | H1 | L4 | SEGMENTA | porta 5210 → 443, segmento 1 de 1               54 B
005 | H1 | L3 | ENCAPSULA | 10.0.1.10 → 10.0.3.10                          74 B
006 | H1 | L3 | ROTEIA | próximo salto 10.0.1.1 pela interface eth0        74 B
007 | H1 | L2 | ENQUADRA | AA:…:01:0A → BB:…:01:00, quadro Q1              92 B
008 | H1 | L1 | TRANSMITE | 736 bits no enlace H1–R1                       92 B
009 | R1 | L1 | RECEBE | 736 bits do enlace H1–R1                          92 B
010 | R1 | L2 | DESENQUADRA | verificação de erro correta, quadro Q1 descartado  74 B
011 | R1 | L3 | ROTEIA | 10.0.3.0/24 via R4, custo 2, interface e1         74 B
012 | R1 | L2 | ENQUADRA | BB:…:01:01 → BB:…:04:00, quadro Q2              92 B"""


def anexo_b() -> list[str]:
    """As linhas do registro esperado de C2 (Anexo B), lidas do arquivo."""
    with open(_REGISTRO_ESPERADO, encoding="utf-8") as arquivo:
        return arquivo.read().strip().splitlines()


class FormatoDoRegistro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A mesma chamada do ponto de entrada `--caso C2` (issue #33), sem
        # subprocesso: o que se confere é o formato, não a linha de comando.
        cls.registro = principais(executar_caso(carregar_topologia(), "C2"))

    def test_as_doze_primeiras_linhas_batem_caractere_a_caractere(self):
        obtidas = [evento.linha() for evento in self.registro[:12]]
        for numero, (obtida, esperada) in enumerate(
            zip(obtidas, DOZE_PRIMEIRAS.splitlines()), 1
        ):
            with self.subTest(linha=numero):
                self.assertEqual(obtida, esperada)

    def test_as_doze_primeiras_linhas_como_um_bloco_unico(self):
        """A mesma comparação em bloco: uma linha a mais ou a menos no registro
        também é divergência de formato."""
        self.assertEqual(
            "\n".join(e.linha() for e in self.registro[:12]), DOZE_PRIMEIRAS
        )

    def test_o_registro_inteiro_bate_com_o_anexo_b(self):
        """As trinta e uma linhas do registro padrão contra o documento,
        inclusive o `METRICAS` final (issue #43)."""
        esperadas = anexo_b()
        obtidas = [evento.linha() for evento in self.registro]
        self.assertEqual(obtidas, esperadas)

    def test_o_tamanho_termina_sempre_na_mesma_coluna(self):
        """A regra por trás do preenchimento, medida no resultado: o ` B` final
        fecha na mesma coluna em toda linha que não estourou a largura."""
        colunas = {
            len(evento.linha())
            for evento in self.registro
            # Linha sem tamanho não tem coluna de octetos a alinhar: é o caso
            # do `METRICAS`, que fecha o registro com texto corrido.
            if evento.tamanho is not None and len(evento.linha()) <= 79
        }
        self.assertEqual(colunas, {79})

    def test_descricao_longa_empurra_o_tamanho_em_vez_de_truncar(self):
        """Linha 010: a descrição passa da coluna do tamanho. Nada é cortado —
        o tamanho vai para a direita com o mínimo de dois espaços."""
        linha = self.registro[9].linha()
        self.assertTrue(linha.startswith("010 | R1 | L2 | DESENQUADRA |"))
        self.assertTrue(linha.endswith("quadro Q1 descartado  74 B"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
