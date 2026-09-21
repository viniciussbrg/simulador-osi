"""T-CRC — inversão de bit único é sempre detectada (issue #46).

A decisão D3 escolheu CRC-32 com o polinômio 0xEDB88320, calculado no próprio
código, e apoia C6 numa garantia matemática: **qualquer** erro de bit único é
detectado, para qualquer tamanho de quadro. O teste existe para que essa
garantia não dependa de sorte — se C6 funcionasse só porque o bit 100 do
quadro Q3 é um bit de sorte, a demonstração não valeria nada.

Três frentes, da mais isolada à mais realista:

- **a função contra um oráculo externo** — `zlib.crc32`, da biblioteca padrão,
  usa o mesmo polinômio. Comparar contra ela prova que a implementação caseira
  está certa, e não apenas consistente consigo mesma. Um CRC errado mas
  determinístico passaria em todos os outros testes deste arquivo;
- **varredura exaustiva de bits** — cada bit de um buffer do tamanho de um
  quadro real de C2 é invertido, um de cada vez, e o CRC recalculado tem de
  divergir. São 736 inversões, nenhum falso negativo tolerado;
- **a camada 2 de verdade** — quadro montado por `CamadaEnlace.descer`,
  corrompido bit a bit no bloco de dados e entregue a `subir`, que precisa
  reprovar em todas as vezes, sem entregar pacote à camada 3.

Executar:  python -m unittest tests.test_crc
"""

import os
import random
import sys
import unittest
import zlib

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

import camadas
from camadas import ENLACE_ERRO_CRC, ENLACE_OK, CamadaEnlace, Contexto, crc32
from pdu import PDU, Bloco, reiniciar_contador_quadros

# Um quadro de C2 tem 92 octetos; o buffer da varredura tem o mesmo porte, para
# que o número de inversões (736) seja o do caso real.
OCTETOS_DE_QUADRO = 92


def com_bit_invertido(dados: bytes, bit: int) -> bytes:
    octetos = bytearray(dados)
    octetos[bit // 8] ^= 1 << (7 - bit % 8)
    return bytes(octetos)


class ContraOraculoExterno(unittest.TestCase):
    """A implementação caseira contra `zlib.crc32`, mesmo polinômio."""

    def test_bate_com_zlib_em_entradas_conhecidas(self):
        for dados in (
            b"",
            b"\x00",
            b"a",
            b"123456789",
            b"GET /index.html HTTP/1.1 Host: fesa.edu.br",
            bytes(range(256)),
        ):
            with self.subTest(dados=dados[:16]):
                self.assertEqual(crc32(dados), zlib.crc32(dados))

    def test_bate_com_zlib_em_entradas_aleatorias(self):
        """Semente fixa: o teste é determinístico como o resto da suíte."""
        sorteio = random.Random(20260911)
        for _ in range(200):
            dados = bytes(sorteio.randrange(256) for _ in range(sorteio.randrange(1, 200)))
            self.assertEqual(crc32(dados), zlib.crc32(dados), dados.hex())

    def test_o_resultado_cabe_em_32_bits(self):
        self.assertTrue(0 <= crc32(b"qualquer coisa") <= 0xFFFFFFFF)


class VarreduraExaustivaDeBits(unittest.TestCase):
    """Nenhuma inversão de bit único passa despercebida."""

    @classmethod
    def setUpClass(cls):
        sorteio = random.Random(20260911)
        cls.dados = bytes(sorteio.randrange(256) for _ in range(OCTETOS_DE_QUADRO))
        cls.crc = crc32(cls.dados)

    def test_todo_bit_invertido_muda_o_crc(self):
        falsos_negativos = [
            bit
            for bit in range(len(self.dados) * 8)
            if crc32(com_bit_invertido(self.dados, bit)) == self.crc
        ]
        self.assertEqual(falsos_negativos, [], "bits não detectados")

    def test_a_varredura_cobriu_os_736_bits_do_quadro(self):
        """Guarda do próprio teste: uma varredura vazia passaria em silêncio."""
        self.assertEqual(len(self.dados) * 8, 736)

    def test_inverter_dois_bits_tambem_e_detectado_no_quadro_de_c6(self):
        """Não é garantia matemática do CRC-32 (erro duplo pode escapar em
        teoria), mas vale registrar o caso concreto: o bit 100 de C6 e o seu
        vizinho, juntos, continuam sendo pegos."""
        duplo = com_bit_invertido(com_bit_invertido(self.dados, 100), 101)
        self.assertNotEqual(crc32(duplo), self.crc)


class CamadaDeEnlaceRejeita(unittest.TestCase):
    """O caminho real: quadro montado pela camada 2, corrompido, e subido."""

    def quadro_novo(self):
        reiniciar_contador_quadros()
        pacote = PDU(
            nome="Pacote",
            blocos=[
                Bloco(rotulo="H3", tam=20, tipo="cabecalho", conteudo="10.0.1.10:10.0.3.10", camada=3),
                Bloco(rotulo="Dados", tam=54, tipo="dados", conteudo=bytes(range(54))),
            ],
        )
        ctx = Contexto(
            fisico_origem="AA:00:00:00:01:0A", fisico_destino="BB:00:00:00:01:00"
        )
        return CamadaEnlace().descer(pacote, ctx)

    def test_o_quadro_intacto_passa(self):
        """Contraprova: sem corrupção, a camada 2 entrega o pacote. Sem isto,
        um `subir` que reprovasse sempre passaria nos testes abaixo."""
        quadro = self.quadro_novo()
        ctx = Contexto()
        pacote = CamadaEnlace().subir(quadro, ctx)
        self.assertEqual(ctx.resultado_enlace, ENLACE_OK)
        self.assertIsNotNone(pacote)

    def test_todo_bit_dos_dados_invertido_e_reprovado(self):
        """Um quadro novo por bit — a camada 2 destrói o quadro na subida (R2),
        então nenhum objeto pode ser reaproveitado entre as tentativas."""
        bits = len(bytes(range(54))) * 8
        escaparam = []
        for bit in range(bits):
            quadro = self.quadro_novo().com_bit_invertido(bit)
            ctx = Contexto()
            pacote = CamadaEnlace().subir(quadro, ctx)
            if ctx.resultado_enlace != ENLACE_ERRO_CRC or pacote is not None:
                escaparam.append(bit)
        self.assertEqual(escaparam, [], "bits aceitos pela camada 2")

    def test_o_pacote_nao_sobe_quando_a_verificacao_reprova(self):
        """É o que sustenta o critério de C6: sem pacote, a camada 3 não é
        acionada e nada acontece depois do descarte."""
        quadro = self.quadro_novo().com_bit_invertido(100)
        ctx = Contexto()
        self.assertIsNone(CamadaEnlace().subir(quadro, ctx))
        self.assertEqual(ctx.resultado_enlace, ENLACE_ERRO_CRC)


class PolinomioDeclarado(unittest.TestCase):
    def test_a_tabela_e_construida_com_0xedb88320(self):
        """Decisão D3: o polinômio é o do enunciado, e a tabela é construída no
        próprio código — sem biblioteca externa (decisão D3, seção 3.4)."""
        esperada = []
        for octeto in range(256):
            acc = octeto
            for _ in range(8):
                acc = (acc >> 1) ^ (0xEDB88320 if acc & 1 else 0)
            esperada.append(acc)
        self.assertEqual(list(camadas._TABELA_CRC32), esperada)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
