"""T-TOP — carga e validação do arquivo de topologia (issue #25).

Critério de saída de F2 (proposta técnica, seção 13.3): *"arquivo de
referência carrega sem erro; dez arquivos deliberadamente inválidos produzem
a mensagem esperada"*.

A diferença para `tests/test_validacao.py` (issue #23) é o ponto de entrada:
lá as verificações são exercidas com dicionários montados em memória, aqui o
caminho é o do usuário real — um **arquivo** em disco, passando por leitura,
decodificação UTF-8, parse de JSON e validação. É esse caminho que precisa
falhar com mensagem legível e nunca com rastreamento de pilha: quem editar o
`topologia.json` ao lado do executável (seção 5.8) não tem Python instalado
para interpretar um traceback.

Os arquivos inválidos ficam em `tests/fixtures/`, um por verificação, cada um
quebrado num **único** ponto — assim a mensagem que sai identifica a
verificação sem ambiguidade.

`topologia_alternativa.json` cobre o risco registrado no plano de
desenvolvimento ("casos escritos direto no código em vez do
`topologia.json`"): uma rede completamente diferente, com casos próprios,
tem de carregar e rotear sem uma linha de Python mudar.

Executar:  python -m unittest tests.test_topologia
"""

import json
import os
import sys
import tempfile
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from rede import ErroTopologia, carregar_topologia

_REFERENCIA = os.path.join(_RAIZ, "topologia.json")
_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(nome: str) -> str:
    return os.path.join(_FIXTURES, nome)


class ArquivoDeReferencia(unittest.TestCase):
    """O `topologia.json` do Anexo A passa por todas as dez verificações."""

    @classmethod
    def setUpClass(cls):
        cls.topologia = carregar_topologia(_REFERENCIA)

    def test_as_cinco_secoes_chegam_completas(self):
        # Sete redes: as três locais (A, B, C) mais as quatro de trânsito,
        # uma por enlace ponto-a-ponto entre roteadores.
        self.assertEqual(len(self.topologia.redes), 7)
        self.assertEqual([r.id for r in self.topologia.redes][:3], ["A", "B", "C"])
        self.assertEqual(len(self.topologia.dispositivos), 9)
        self.assertEqual(len(self.topologia.enlaces), 7)
        self.assertEqual(len(self.topologia.casos), 7)

    def test_os_sete_casos_obrigatorios_estao_no_arquivo(self):
        self.assertEqual(
            [caso.id for caso in self.topologia.casos],
            ["C1", "C2", "C3", "C4", "C5", "C6", "C7"],
        )

    def test_parametros_de_referencia(self):
        parametros = self.topologia.parametros
        self.assertEqual(parametros.limite_segmento, 64)
        self.assertEqual(parametros.cifra.chave, "REDES")
        self.assertEqual(parametros.verificacao.polinomio, "0xEDB88320")
        self.assertEqual(parametros.cabecalhos.l5, 4)
        self.assertEqual(parametros.cabecalhos.l4, 8)
        self.assertEqual(parametros.cabecalhos.l3, 20)
        self.assertEqual(parametros.cabecalhos.l2, 14)
        self.assertEqual(parametros.cabecalhos.t2, 4)

    def test_mensagem_de_referencia_tem_42_octetos(self):
        """Seção 5.6 — a linha 001 do Anexo B depende deste número."""
        mensagem = self.topologia.caso("C2").fluxos[0].mensagem
        self.assertEqual(len(mensagem.encode("utf-8")), 42)


# Um arquivo por verificação da tabela 5.7, cada um quebrado num único ponto.
ARQUIVOS_INVALIDOS = (
    ("v01_dispositivo_duplicado.json", "Dispositivo duplicado: H1"),
    ("v02_fisico_repetido.json", "Endereço físico repetido: AA:00:00:00:01:0A"),
    ("v03_logico_repetido.json", "Endereço lógico repetido: 10.0.1.10"),
    ("v04_interface_sem_enlace.json", "Interface H1.eth9 não pertence a nenhum enlace"),
    ("v05_logico_fora_do_prefixo.json", "10.0.7.10 não pertence a 10.0.1.0/24"),
    ("v06_custo_negativo.json", "Custo inválido no enlace E-R1-R4"),
    ("v07_grafo_desconexo.json", "A topologia possui dispositivos inalcançáveis: R8, R9"),
    ("v08_caso_com_dispositivo_inexistente.json",
     "O caso C2 referencia dispositivo inexistente: H9"),
    ("v09_gateway_fora_da_rede.json", "Gateway de H1 fora da rede local"),
    ("v10_limite_segmento_pequeno.json", "limite_segmento incompatível com o caso C1"),
)


class ArquivosInvalidos(unittest.TestCase):
    """Os dez arquivos deliberadamente inválidos do critério de saída."""

    def test_dez_arquivos_dez_mensagens(self):
        self.assertEqual(len(ARQUIVOS_INVALIDOS), 10)
        for nome, esperada in ARQUIVOS_INVALIDOS:
            with self.subTest(arquivo=nome):
                with self.assertRaises(ErroTopologia) as capturado:
                    carregar_topologia(fixture(nome))
                self.assertIn(esperada, str(capturado.exception))

    def test_cada_arquivo_invalido_e_json_bem_formado(self):
        """A quebra tem de ser semântica, não de sintaxe — senão o arquivo
        estaria testando o parser de JSON, não a verificação da tabela 5.7."""
        for nome, _ in ARQUIVOS_INVALIDOS:
            with self.subTest(arquivo=nome):
                with open(fixture(nome), encoding="utf-8") as arquivo:
                    self.assertIsInstance(json.load(arquivo), dict)


class ErroDeArquivo(unittest.TestCase):
    """"Falha com mensagem clara, nunca com stack trace" (seção 5.7) vale
    também antes do JSON virar dicionário."""

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

    def escrever(self, nome: str, conteudo: bytes) -> str:
        caminho = os.path.join(self.pasta.name, nome)
        with open(caminho, "wb") as arquivo:
            arquivo.write(conteudo)
        return caminho

    def test_arquivo_ausente(self):
        caminho = os.path.join(self.pasta.name, "nao_existe.json")
        with self.assertRaises(ErroTopologia) as capturado:
            carregar_topologia(caminho)
        self.assertIn("Arquivo de topologia não encontrado", str(capturado.exception))

    def test_json_malformado_aponta_linha_e_coluna(self):
        caminho = self.escrever("quebrado.json", b'{"versao": "1.0",\n "nome": }\n')
        with self.assertRaises(ErroTopologia) as capturado:
            carregar_topologia(caminho)
        self.assertIn("JSON inválido", str(capturado.exception))

    def test_arquivo_fora_de_utf8(self):
        caminho = self.escrever("latin1.json", '{"nome": "Topologia"}'.encode("latin-1")
                                .replace(b"Topologia", b"Topolog\xeda"))
        with self.assertRaises(ErroTopologia) as capturado:
            carregar_topologia(caminho)
        self.assertIn("UTF-8", str(capturado.exception))

    def test_secao_faltando(self):
        with open(_REFERENCIA, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        del dados["enlaces"]
        caminho = self.escrever(
            "sem_enlaces.json", json.dumps(dados, ensure_ascii=False).encode("utf-8")
        )
        with self.assertRaises(ErroTopologia) as capturado:
            carregar_topologia(caminho)
        self.assertIn("enlaces", str(capturado.exception))


class TopologiaAlternativa(unittest.TestCase):
    """Trocar o arquivo troca a rede simulada, sem tocar em código — a
    promessa central da seção 5.5 e do checklist 14.3."""

    @classmethod
    def setUpClass(cls):
        cls.topologia = carregar_topologia(fixture("topologia_alternativa.json"))

    def test_carrega_uma_rede_diferente_da_de_referencia(self):
        self.assertNotEqual(self.topologia.nome, "Topologia de referência — Projeto 1")
        self.assertEqual(
            [d.nome for d in self.topologia.dispositivos],
            ["PC-A", "PC-B", "RT-1", "RT-2"],
        )

    def test_os_casos_vem_do_arquivo(self):
        self.assertEqual([caso.id for caso in self.topologia.casos], ["X1"])
        fluxo = self.topologia.caso("X1").fluxos[0]
        self.assertEqual(fluxo.origem.dispositivo, "PC-A")
        self.assertEqual(fluxo.destino.dispositivo, "PC-B")

    def test_roteamento_funciona_sobre_a_topologia_nova(self):
        decisao = self.topologia.decisao_computador("PC-A", "192.168.20.10")
        self.assertFalse(decisao.entrega_direta)
        tabela = self.topologia.tabela_encaminhamento("RT-1")
        rota = tabela.consulta("192.168.20.10")
        self.assertIsNotNone(rota)
        # Próximo salto é o endereço lógico do vizinho (tabela 6.2), não o
        # nome do dispositivo — aqui a ponta de RT-2 no enlace de trânsito.
        self.assertEqual(rota.proximo_salto, "10.10.10.2")
        self.assertEqual(rota.interface_saida, "e1")


if __name__ == "__main__":
    unittest.main()
