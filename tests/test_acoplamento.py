"""A regra de acoplamento: `visual.py` importa somente `evento.py` (issue #47).

É a regra que sustenta a arquitetura inteira (seção 4.2 da proposta técnica) e
também a que mais barato sai quebrar: basta um `from rede import ...` no meio
de uma função de desenho, numa PR de F5 às onze da noite, para a tela passar a
perguntar ao núcleo o que deveria estar no `Evento`. A proposta técnica lista
isso como risco de probabilidade média e impacto alto (seção 15.3) e pede
exatamente o que está aqui: **verificação automática de importações**, rodando
desde o início da fase e em toda PR seguinte.

Verificar de uma forma só não bastaria, e o arquivo verifica de duas:

- **estática** (`ast`) — lê `visual.py` sem executá-lo e reprova qualquer
  módulo fora de `evento`, stdlib e tkinter. Enxerga o que o interpretador não
  chega a ver: o `import dispositivos` escondido dentro de uma função que a
  tela raramente chama, o `importlib.import_module("rede")`, o import relativo;
- **em execução** (subprocesso) — proíbe os módulos do núcleo no `meta_path` e
  então importa `visual` e navega pelo registro. Pega o que a leitura estática
  não pegaria, como um módulo alcançado por um caminho que o `ast` não
  reconhece, e prova que a fronteira vale de fato, não só no texto.

Um detalhe sobre `constantes.py`: ele é módulo do projeto e portanto está
**proibido** na verificação estática, embora `evento.py` o importe (é de lá que
sai o tipo `Acao`). Chegar a ele por dentro do `Evento` é legítimo; escrever
`import constantes` em `visual.py` não é — se a tela precisar do vocabulário de
ações, o campo vem no evento, como manda o teste do acoplamento. Por isso o
subprocesso não o bloqueia (bloquear quebraria o próprio `import evento`) e a
verificação estática, que distingue as duas coisas, é quem cobra.

Executar:  python -m unittest tests.test_acoplamento
"""

import ast
import os
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from evento import Evento
from visual import Navegador

ARQUIVO_VISUAL = Path(_RAIZ) / "visual.py"

# Levantados do disco, não escritos à mão: um módulo novo na raiz do projeto
# entra na proibição sozinho, sem ninguém lembrar de atualizar esta lista.
MODULOS_DO_PROJETO = frozenset(caminho.stem for caminho in Path(_RAIZ).glob("*.py"))

# A única exceção. A lista de eventos é tudo o que a interface enxerga.
PERMITIDOS_DO_PROJETO = frozenset({"evento"})


@dataclass(frozen=True)
class Importacao:
    """Um módulo trazido para dentro do arquivo, e por qual forma."""

    modulo: str
    linha: int
    forma: str


def _raiz_do_modulo(nome: str) -> str:
    """`os.path` conta como `os`: o que importa é de qual pacote se depende."""
    return nome.split(".")[0]


def _alvo_de_import_dinamico(no: ast.Call) -> str | None:
    """`__import__("rede")` e `importlib.import_module("rede")` são imports com
    outro nome. Devolve o módulo pedido, `"?"` quando o argumento não é literal
    (aí não há o que analisar, e é por isso mesmo que não passa), ou `None` se a
    chamada não for um import."""
    funcao = no.func
    if isinstance(funcao, ast.Name):
        nome = funcao.id
    elif isinstance(funcao, ast.Attribute):
        nome = funcao.attr
    else:
        return None
    if nome not in {"__import__", "import_module"}:
        return None
    primeiro = no.args[0] if no.args else None
    if isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str):
        return _raiz_do_modulo(primeiro.value)
    return "?"


def importacoes(fonte: str, arquivo: str = "<amostra>") -> list[Importacao]:
    """Toda importação do arquivo, em qualquer profundidade.

    `ast.walk` é deliberado: um import dentro de método, de `if`, de `try` ou de
    função aninhada conta igual a um import no topo do arquivo — esconder não é
    obedecer.
    """
    encontradas: list[Importacao] = []
    for no in ast.walk(ast.parse(fonte, filename=arquivo)):
        if isinstance(no, ast.Import):
            for apelido in no.names:
                encontradas.append(
                    Importacao(_raiz_do_modulo(apelido.name), no.lineno, "import")
                )
        elif isinstance(no, ast.ImportFrom):
            if no.level:  # from . import x / from ..pdu import PDU
                relativo = "." * no.level + (no.module or "")
                encontradas.append(Importacao(relativo, no.lineno, "import relativo"))
            else:
                encontradas.append(
                    Importacao(_raiz_do_modulo(no.module or ""), no.lineno, "from-import")
                )
        elif isinstance(no, ast.Call):
            alvo = _alvo_de_import_dinamico(no)
            if alvo is not None:
                encontradas.append(Importacao(alvo, no.lineno, "import dinâmico"))
    return encontradas


def proibidas(fonte: str, arquivo: str = "<amostra>") -> list[tuple[Importacao, str]]:
    """As importações que violam a regra, cada uma com o motivo por extenso.

    Lista vazia significa arquivo em conformidade. A ordem de classificação
    importa: `evento` primeiro, porque é a exceção; módulo do projeto antes da
    stdlib, para que um arquivo local que ofusque nome de biblioteca padrão não
    entre de carona.
    """
    recusadas: list[tuple[Importacao, str]] = []
    for uso in importacoes(fonte, arquivo):
        modulo = uso.modulo
        if uso.forma == "import relativo":
            recusadas.append(
                (uso, "import relativo: só alcançaria módulo do próprio projeto")
            )
        elif modulo == "?":
            recusadas.append(
                (uso, "import dinâmico com alvo não literal: ilegível para a verificação")
            )
        elif modulo in PERMITIDOS_DO_PROJETO:
            continue
        elif modulo in MODULOS_DO_PROJETO:
            recusadas.append(
                (uso, "módulo do projeto: o dado que falta na tela entra no Evento")
            )
        elif modulo in sys.stdlib_module_names:  # inclui tkinter
            continue
        else:
            recusadas.append(
                (uso, "dependência externa: o projeto roda só com a biblioteca padrão")
            )
    return recusadas


def _relato(recusadas: list[tuple[Importacao, str]]) -> str:
    return "\n".join(
        f"  linha {uso.linha}: {uso.forma} de {uso.modulo!r} — {motivo}"
        for uso, motivo in recusadas
    )


class VerificacaoEstatica(unittest.TestCase):
    """O verificador conferido contra amostras, antes de servir de juiz.

    Sem esta classe, `proibidas()` poderia estar simplesmente devolvendo lista
    vazia para tudo e o critério de aceitação da issue passaria sozinho, verde e
    inútil — o mesmo cuidado que T-R4 toma com a sua guarda.
    """

    def test_aceita_evento_stdlib_e_tkinter(self):
        fonte = (
            "import tkinter as tk\n"
            "from tkinter import ttk\n"
            "from collections.abc import Sequence\n"
            "import json\n"
            "from evento import Evento, PduInfo\n"
        )
        self.assertEqual(proibidas(fonte), [])

    def test_recusa_modulo_do_nucleo(self):
        for fonte in (
            "import rede\n",
            "import simulador as motor\n",
            "from camadas import CamadaRede\n",
            "from dispositivos import Computador\n",
            "from pdu import PDU\n",
        ):
            with self.subTest(fonte=fonte.strip()):
                recusadas = proibidas(fonte)
                self.assertEqual(len(recusadas), 1, fonte)
                self.assertIn("módulo do projeto", recusadas[0][1])

    def test_recusa_constantes_apesar_de_evento_usar(self):
        """O vocabulário de ações chega pelo `Evento`, não por importação."""
        self.assertEqual(len(proibidas("from constantes import ACOES_VALIDAS\n")), 1)

    def test_recusa_import_escondido_dentro_de_funcao(self):
        fonte = (
            "from evento import Evento\n"
            "\n"
            "def desenhar(tela, evento):\n"
            "    if evento.acao == 'ROTEIA':\n"
            "        import rede\n"
            "        return rede.dijkstra(evento.dispositivo)\n"
        )
        recusadas = proibidas(fonte)
        self.assertEqual([uso.modulo for uso, _ in recusadas], ["rede"])
        self.assertEqual(recusadas[0][0].linha, 5)

    def test_recusa_import_relativo(self):
        for fonte in ("from .pdu import PDU\n", "from . import camadas\n"):
            with self.subTest(fonte=fonte.strip()):
                recusadas = proibidas(fonte)
                self.assertEqual(len(recusadas), 1)
                self.assertIn("import relativo", recusadas[0][1])

    def test_recusa_import_dinamico(self):
        recusadas = proibidas(
            "import importlib\n"
            "rede = importlib.import_module('rede')\n"
            "pdu = __import__('pdu')\n"
        )
        self.assertEqual(sorted(uso.modulo for uso, _ in recusadas), ["pdu", "rede"])

    def test_recusa_import_dinamico_de_alvo_calculado(self):
        recusadas = proibidas("import importlib\nm = importlib.import_module(nome)\n")
        self.assertEqual(len(recusadas), 1)
        self.assertIn("não literal", recusadas[0][1])

    def test_recusa_dependencia_externa(self):
        recusadas = proibidas("import numpy\n")
        self.assertEqual(len(recusadas), 1)
        self.assertIn("dependência externa", recusadas[0][1])

    def test_conta_todas_as_violacoes_de_uma_vez(self):
        """O relatório mostra o arquivo inteiro; quem corrige não descobre uma
        violação por execução."""
        fonte = "import rede\nfrom camadas import CamadaRede\nimport numpy\n"
        self.assertEqual(len(proibidas(fonte)), 3)


class VisualSoImportaEvento(unittest.TestCase):
    """O critério de aceitação da issue #47, aplicado ao arquivo real."""

    def test_visual_existe(self):
        self.assertTrue(
            ARQUIVO_VISUAL.is_file(), f"{ARQUIVO_VISUAL.name} não existe na raiz"
        )

    def test_nenhum_import_proibido_em_visual(self):
        recusadas = proibidas(
            ARQUIVO_VISUAL.read_text(encoding="utf-8"), ARQUIVO_VISUAL.name
        )
        self.assertEqual(
            recusadas,
            [],
            f"\n{ARQUIVO_VISUAL.name} fere a regra de acoplamento "
            f"(seção 4.2):\n{_relato(recusadas)}",
        )

    def test_visual_importa_evento(self):
        """A regra tem dois lados: nada do núcleo, e o `Evento` de fato — um
        `visual.py` que não lesse evento nenhum passaria no teste acima sem
        cumprir contrato algum."""
        modulos = {
            uso.modulo
            for uso in importacoes(
                ARQUIVO_VISUAL.read_text(encoding="utf-8"), ARQUIVO_VISUAL.name
            )
        }
        self.assertIn("evento", modulos)


# As outras cinco linhas da tabela de dependências da proposta técnica
# (seção 4.1) — `visual.py` já tem,
# acima, a verificação mais estrita (só `evento`); esta cobre o resto do
# núcleo, cada módulo com sua própria lista de módulos do projeto que não
# pode importar. "interface" ali vira `visual`/`app` aqui; "motor de eventos"
# vira `simulador`.
_TABELA_DE_DEPENDENCIAS = {
    "pdu": frozenset({"rede", "dispositivos", "visual", "app"}),
    "camadas": frozenset({"visual", "app", "simulador"}),
    "dispositivos": frozenset({"visual", "app"}),
    "rede": frozenset({"camadas", "visual", "app"}),
    "simulador": frozenset({"visual", "app"}),
}


class RestricoesDeImportacaoDoNucleo(unittest.TestCase):
    """Sem isto, um `import camadas` esquecido dentro de `rede.py`, ou um
    `import visual` dentro de `pdu.py`, passaria pela suíte inteira sem
    ninguém perceber — só a linha de `visual.py` na tabela tinha guarda
    automática até aqui."""

    def test_tabela_cobre_todo_modulo_do_nucleo(self):
        """Controle: um módulo novo no núcleo que não entrar nesta tabela faz
        este teste falhar, em vez de deixar a lacuna passar em silêncio."""
        nucleo = MODULOS_DO_PROJETO - {"evento", "constantes", "visual", "app"}
        self.assertEqual(set(_TABELA_DE_DEPENDENCIAS), nucleo)

    def test_nenhum_modulo_do_nucleo_importa_o_que_a_tabela_proibe(self):
        for modulo, proibidos in _TABELA_DE_DEPENDENCIAS.items():
            arquivo = Path(_RAIZ) / f"{modulo}.py"
            with self.subTest(modulo=modulo):
                fonte = arquivo.read_text(encoding="utf-8")
                recusadas = [
                    (uso, f"{modulo}.py não pode importar {uso.modulo!r} (seção 4.1)")
                    for uso in importacoes(fonte, arquivo.name)
                    if _raiz_do_modulo(uso.modulo.lstrip(".")) in proibidos
                ]
                self.assertEqual(
                    recusadas,
                    [],
                    f"\n{arquivo.name} fere a tabela de dependências da "
                    f"proposta técnica, seção 4.1:\n{_relato(recusadas)}",
                )


# Módulos do núcleo negados no subprocesso. `constantes` fica de fora porque
# `evento.py` o importa para o tipo `Acao`: bloqueá-lo derrubaria o import
# legítimo. Quem cobra o `import constantes` direto é a verificação estática.
_NUCLEO_FECHADO = tuple(
    sorted(MODULOS_DO_PROJETO - PERMITIDOS_DO_PROJETO - {"constantes", "visual"})
)

_SEM_NUCLEO = f"""
import sys

_PROIBIDOS = {_NUCLEO_FECHADO!r}

class _SemNucleo:
    def find_module(self, nome, caminho=None):
        return self.find_spec(nome, caminho)

    def find_spec(self, nome, caminho=None, alvo=None):
        if nome.split(".")[0] in _PROIBIDOS:
            raise ImportError(nome + " proibido: visual.py so enxerga evento.py")
        return None

sys.meta_path.insert(0, _SemNucleo())
"""

_SEM_TKINTER = """
import sys

class _SemTkinter:
    def find_module(self, nome, caminho=None):
        return self.find_spec(nome, caminho)

    def find_spec(self, nome, caminho=None, alvo=None):
        if nome.split(".")[0] == "tkinter":
            raise ImportError("tkinter proibido")
        return None

sys.meta_path.insert(0, _SemTkinter())
"""


def _num_processo(prologo: str, corpo: str) -> subprocess.CompletedProcess:
    """Roda `corpo` num Python novo, com o prólogo de proibições e a raiz no path."""
    return subprocess.run(
        [sys.executable, "-c", prologo + corpo],
        cwd=_RAIZ,
        capture_output=True,
        text=True,
    )


class VerificacaoEmExecucao(unittest.TestCase):
    """A fronteira exercitada, não só lida."""

    def test_a_proibicao_do_nucleo_e_de_fato_ativa(self):
        """Controle negativo: sem isto, os testes abaixo passariam mesmo com o
        bloqueio desligado."""
        resultado = _num_processo(_SEM_NUCLEO, "import rede\n")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("proibido", resultado.stderr)

    def test_importar_visual_nao_puxa_o_nucleo(self):
        resultado = _num_processo(_SEM_NUCLEO, "import visual\nprint('ok')\n")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("ok", resultado.stdout)

    def test_navegar_o_registro_inteiro_sem_o_nucleo(self):
        """Nenhum import tardio escondido em método: a navegação roda de ponta a
        ponta com o núcleo fora do alcance."""
        resultado = _num_processo(
            _SEM_NUCLEO,
            "from evento import Evento\n"
            "from visual import Navegador\n"
            "eventos = [Evento(passo=i, dispositivo='H1', camada=7,\n"
            "                  acao='GERA', descricao='amostra', tamanho=42)\n"
            "           for i in range(1, 6)]\n"
            "n = Navegador(eventos)\n"
            "while not n.no_fim:\n"
            "    n.proximo()\n"
            "while not n.no_inicio:\n"
            "    n.anterior()\n"
            "n.ultimo(); n.primeiro(); n.ir_para(3)\n"
            "print(n.atual.linha())\n",
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("004 | H1 | L7 | GERA | amostra", resultado.stdout)

    def test_importar_visual_nao_abre_janela(self):
        """Importar o módulo não pode ter efeito de tela — é o que permite a
        estes testes, e a toda a suíte, rodarem sem tkinter (seção 13.1). Quando
        V1 trouxer o tkinter, ele entra dentro da função que abre a janela."""
        resultado = _num_processo(_SEM_TKINTER, "import visual\nprint('ok')\n")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("ok", resultado.stdout)


def _evento(passo: int, acao: str = "GERA") -> Evento:
    return Evento(
        passo=passo,
        dispositivo="H1",
        camada=7,
        acao=acao,
        descricao=f"evento {passo}",
        tamanho=42,
    )


class NavegacaoPorIndice(unittest.TestCase):
    """O outro lado da regra: a interface *navega* a lista, não a produz.

    Tudo o que a F6 chama de controle de execução (V5) é operação sobre o
    índice desta classe — testável sem tela, como exige a seção 13.1.
    """

    def setUp(self):
        self.eventos = [_evento(i) for i in range(1, 6)]
        self.navegador = Navegador(self.eventos)

    def test_comeca_no_primeiro_evento(self):
        self.assertEqual(self.navegador.indice, 0)
        self.assertEqual(self.navegador.atual, self.eventos[0])
        self.assertTrue(self.navegador.no_inicio)
        self.assertFalse(self.navegador.no_fim)

    def test_total_e_o_tamanho_do_registro(self):
        self.assertEqual(self.navegador.total, 5)

    def test_guarda_uma_copia_imutavel_do_registro(self):
        """A lista de fora pode mudar; o registro navegado, não."""
        self.eventos.append(_evento(6))
        self.assertEqual(self.navegador.total, 5)
        self.assertIsInstance(self.navegador.eventos, tuple)

    def test_proximo_e_anterior_andam_um_passo(self):
        self.assertEqual(self.navegador.proximo(), self.eventos[1])
        self.assertEqual(self.navegador.proximo(), self.eventos[2])
        self.assertEqual(self.navegador.anterior(), self.eventos[1])
        self.assertEqual(self.navegador.indice, 1)

    def test_limites_saturam_em_vez_de_estourar(self):
        self.navegador.ultimo()
        self.assertTrue(self.navegador.no_fim)
        self.assertEqual(self.navegador.proximo(), self.eventos[-1])
        self.navegador.primeiro()
        self.assertEqual(self.navegador.anterior(), self.eventos[0])

    def test_ir_para_recusa_indice_fora_da_faixa(self):
        for indice in (-1, 5, 99):
            with self.subTest(indice=indice):
                with self.assertRaises(IndexError):
                    self.navegador.ir_para(indice)
        self.assertEqual(self.navegador.indice, 0, "posição preservada após erro")

    def test_ate_agora_acumula_do_inicio_ao_corrente(self):
        self.navegador.ir_para(2)
        self.assertEqual(self.navegador.ate_agora(), tuple(self.eventos[:3]))
        self.navegador.primeiro()
        self.assertEqual(self.navegador.ate_agora(), (self.eventos[0],))

    def test_registro_vazio_nao_se_navega(self):
        with self.assertRaises(ValueError):
            Navegador([])

    def test_navegar_nao_altera_o_evento(self):
        """`Evento` é imutável (contrato, seção 7) e a navegação não o toca."""
        antes = self.navegador.atual
        self.navegador.ultimo()
        self.navegador.primeiro()
        self.assertIs(self.navegador.atual, antes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
