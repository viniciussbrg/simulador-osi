"""Issue #33 — o ponto de entrada `python simulador.py --caso C2 --log saida.txt`.

É a ferramenta de trabalho de todo o desenvolvimento até F4 fechar (seção 13.2
da proposta técnica) e o único jeito de exercitar o simulador sem tkinter. Os
testes abaixo o invocam como o usuário invoca — por subprocesso, pela linha de
comando — e conferem o formato de salvamento da seção 8.3.

A regra que mais importa aqui não é de formato: **arquivo de topologia
inválido nunca produz rastreamento de pilha** (seção 5.7). Numa máquina
Windows sem Python, traceback é ilegível; o que sai é a mensagem da
`ErroTopologia` e um código de saída diferente de zero.

Executar:  python -m unittest tests.test_cli
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import casos_executaveis, executar_caso, principais

_ARQUIVO_REFERENCIA = os.path.join(_RAIZ, "topologia.json")


def simulador(*argumentos: str, ambiente: dict | None = None) -> subprocess.CompletedProcess:
    """Invoca `python simulador.py ...` como o usuário faria.

    `encoding="utf-8"` porque é em UTF-8 que o programa escreve, sempre — não
    na página de código de quem o chamou. Sem isto, o registro chega aqui como
    `conteÃºdo cifrado` numa máquina com console `cp1252`, e a comparação com
    `Evento.linha()` falha por um defeito do teste, não do programa."""
    return subprocess.run(
        [sys.executable, "simulador.py", *argumentos],
        cwd=_RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ambiente,
    )


def registro_esperado(caso: str) -> list[str]:
    return [e.linha() for e in principais(executar_caso(carregar_topologia(), caso))]


def topologia_quebrada(pasta: str, quebrar) -> str:
    """Grava em `pasta` uma cópia da topologia de referência com um defeito."""
    with open(_ARQUIVO_REFERENCIA, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    quebrar(dados)
    caminho = os.path.join(pasta, "topologia_quebrada.json")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False)
    return caminho


class Argumentos(unittest.TestCase):
    def test_sem_caso_e_erro_de_uso(self):
        resultado = simulador()
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("--caso", resultado.stderr)

    def test_caso_inexistente_explica_quais_existem(self):
        resultado = simulador("--caso", "C9")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("C9", resultado.stderr)
        self.assertIn("C2", resultado.stderr)
        self.assertNotIn("Traceback", resultado.stderr)


class Registro(unittest.TestCase):
    def test_sem_log_o_registro_sai_no_stdout(self):
        resultado = simulador("--caso", "C2")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        linhas = [l for l in resultado.stdout.splitlines() if not l.startswith("#")]
        self.assertEqual(linhas, registro_esperado("C2"))

    def test_com_log_o_registro_vai_para_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "saida.txt")
            resultado = simulador("--caso", "C2", "--log", destino)
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            with open(destino, encoding="utf-8") as arquivo:
                conteudo = arquivo.read()
        linhas = [l for l in conteudo.splitlines() if not l.startswith("#")]
        self.assertEqual(linhas, registro_esperado("C2"))

    def test_cabecalho_de_identificacao_da_secao_8_3(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "saida.txt")
            simulador("--caso", "C2", "--log", destino)
            with open(destino, encoding="utf-8") as arquivo:
                linhas = arquivo.read().splitlines()

        self.assertEqual(linhas[0], "# Simulador do Modelo OSI — Comunicação de Dados")
        self.assertEqual(linhas[1], "# Caso: C2 — Entrega indireta (caso central)")
        self.assertEqual(linhas[2], "# Topologia: Topologia de referência — Projeto 1")
        self.assertRegex(linhas[3], r"^# Data: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(linhas[4], "#")
        self.assertTrue(linhas[5].startswith("001 | H1 | L7 | GERA |"))

    def test_todos_os_casos_da_topologia_rodam_pela_linha_de_comando(self):
        """Os que o motor executa hoje; C4 e C6 dependem de intervenção externa
        de F4 e têm recusa própria em `tests/test_casos_pendentes.py`."""
        for caso in casos_executaveis(carregar_topologia()):
            with self.subTest(caso=caso):
                resultado = simulador("--caso", caso)
                self.assertEqual(resultado.returncode, 0, resultado.stderr)
                self.assertIn("001 | ", resultado.stdout)


class CodificacaoDaSaida(unittest.TestCase):
    """O registro é UTF-8 na saída padrão e no arquivo, qualquer que seja a
    página de código do console.

    Windows entrega `cp1252`, que não tem a seta `→` da linha 004 nem as
    reticências `…` da linha 007. Escrever ali sem tratamento derruba o
    programa com `UnicodeEncodeError` e rastreamento de pilha — e o modo
    textual é a ferramenta de trabalho de todo o desenvolvimento até F4 fechar
    (seção 13.2), além de ser o que roda na máquina limpa do teste de aceitação
    final (seção 13.5)."""

    def console(self, codificacao: str) -> subprocess.CompletedProcess:
        """O programa com a saída padrão presa a uma página de código estreita.
        `PYTHONIOENCODING` é o jeito portátil de simular o console do Windows a
        partir de qualquer sistema."""
        ambiente = dict(os.environ, PYTHONIOENCODING=codificacao)
        return simulador("--caso", "C2", ambiente=ambiente)

    def test_console_cp1252_nao_derruba_o_registro(self):
        resultado = self.console("cp1252")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertNotIn("UnicodeEncodeError", resultado.stderr)
        self.assertNotIn("Traceback", resultado.stderr)

    def test_os_caracteres_do_anexo_b_chegam_inteiros(self):
        resultado = self.console("cp1252")
        self.assertIn("porta 5210 → 443", resultado.stdout)
        self.assertIn("AA:…:01:0A → BB:…:01:00", resultado.stdout)
        self.assertIn("736 bits no enlace H1–R1", resultado.stdout)

    def test_console_ascii_tambem_sobrevive(self):
        """O caso extremo: nem os acentos cabem. O programa impõe UTF-8 na
        saída antes de escrever, então a página de código de quem chamou não
        muda uma linha do registro."""
        resultado = self.console("ascii")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("conteúdo cifrado", resultado.stdout)

    def test_o_arquivo_salvo_e_utf8_com_quebra_de_linha_unix(self):
        """O arquivo tem de sair igual nos dois sistemas: com CRLF, comparar
        dois registros byte a byte passaria a depender da plataforma que gerou
        cada um."""
        with tempfile.TemporaryDirectory() as pasta:
            destino = os.path.join(pasta, "saida.txt")
            simulador("--caso", "C2", "--log", destino)
            with open(destino, "rb") as arquivo:
                cru = arquivo.read()
        cru.decode("utf-8")  # levanta UnicodeDecodeError se não for UTF-8
        self.assertNotIn(b"\r\n", cru)
        self.assertTrue(cru.endswith(b"\n"))


class TopologiaAlternativa(unittest.TestCase):
    def test_topologia_pode_ser_trocada_por_argumento(self):
        alternativa = os.path.join(_RAIZ, "tests", "fixtures", "topologia_alternativa.json")
        with open(alternativa, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        caso = dados["casos"][0]["id"]

        resultado = simulador("--caso", caso, "--topologia", alternativa)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn(f"# Topologia: {dados['nome']}", resultado.stdout)

    def test_topologia_inexistente_e_mensagem_nao_traceback(self):
        resultado = simulador("--caso", "C2", "--topologia", "nao_existe.json")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertNotIn("Traceback", resultado.stderr)
        self.assertIn("não encontrado", resultado.stderr)

    def test_cada_fixture_invalido_sai_so_com_a_mensagem(self):
        """Critério da issue #33: nenhum arquivo inválido produz traceback pela
        linha de comando — nem os que antes só estouravam na consulta de rota."""
        invalidos = (
            "enlace_ponta_em_outra_rede.json",
            "prefixo_malformado.json",
            "prefixo_mascara_nao_suportada.json",
            "prefixo_repetido.json",
            "rede_id_repetida.json",
            "enlace_id_repetido.json",
            "v06_custo_fracionario.json",
            "v06_custo_negativo_em_difusao.json",
            "v10_caso_unico_nao_cabe.json",
        )
        for nome in invalidos:
            with self.subTest(fixture=nome):
                caminho = os.path.join(_RAIZ, "tests", "fixtures", nome)
                resultado = simulador("--caso", "C2", "--topologia", caminho)
                self.assertNotEqual(resultado.returncode, 0)
                self.assertEqual(resultado.stdout, "")
                self.assertNotIn("Traceback", resultado.stderr)
                self.assertEqual(len(resultado.stderr.splitlines()), 1)

    def test_topologia_invalida_sai_com_a_mensagem_de_erro(self):
        def quebrar(dados: dict) -> None:
            dados["dispositivos"][1]["nome"] = dados["dispositivos"][0]["nome"]

        with tempfile.TemporaryDirectory() as pasta:
            caminho = topologia_quebrada(pasta, quebrar)
            resultado = simulador("--caso", "C2", "--topologia", caminho)

        self.assertNotEqual(resultado.returncode, 0)
        self.assertNotIn("Traceback", resultado.stderr)
        self.assertIn("Dispositivo duplicado", resultado.stderr)
        self.assertEqual(resultado.stdout, "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
