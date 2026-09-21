"""T-PATH — localização do arquivo de topologia (`pasta_base()`, issue #24).

A seção 5.8 da proposta técnica exige que nenhum caminho absoluto apareça
escrito no código e que o `topologia.json` fique **ao lado do executável**,
editável sem recompilar. Os dois modos de execução — código e executável
PyInstaller — são exercitados aqui, o segundo simulando `sys.frozen`.

Executar:  python -m unittest tests.test_localizacao
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

import rede
from rede import carregar_topologia


class LocalizacaoDoArquivo(unittest.TestCase):
    """`pasta_base()` (seção 5.8, issue #24) e o T-PATH: nenhum caminho
    absoluto escrito no código."""

    def test_pasta_base_no_codigo_e_a_pasta_do_modulo(self):
        self.assertEqual(rede.pasta_base(), Path(rede.__file__).resolve().parent)

    def test_pasta_base_congelado_e_a_pasta_do_executavel(self):
        executavel = os.path.join("qualquer", "pasta", "SimuladorOSI.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", executavel):
            self.assertEqual(rede.pasta_base(), Path(executavel).resolve().parent)

    def test_arquivo_topologia_fica_ao_lado_do_executavel(self):
        self.assertEqual(rede.ARQUIVO_TOPOLOGIA.name, "topologia.json")
        self.assertEqual(rede.ARQUIVO_TOPOLOGIA.parent, rede.pasta_base())

    def test_carregar_topologia_sem_argumento_usa_o_arquivo_padrao(self):
        self.assertEqual(
            carregar_topologia().nome, carregar_topologia(rede.ARQUIVO_TOPOLOGIA).nome
        )

    def test_nenhum_caminho_absoluto_no_codigo(self):
        import re

        absoluto = re.compile(r"""["'](?:/home/|/Users/|/mnt/|[A-Za-z]:\\\\)""")
        for arquivo in sorted(Path(_RAIZ).glob("*.py")):
            with self.subTest(arquivo=arquivo.name):
                self.assertIsNone(
                    absoluto.search(arquivo.read_text(encoding="utf-8")),
                    f"caminho absoluto escrito em {arquivo.name}",
                )


if __name__ == "__main__":
    unittest.main()
