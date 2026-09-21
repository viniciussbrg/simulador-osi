"""Executor de testes de reserva, para quando o pytest nao esta instalado.

A ferramenta oficial do projeto e o pytest, e os arquivos de `tests/` sao
escritos para ele. Este script existe apenas para permitir rodar a mesma
bateria em uma maquina sem acesso a internet ou sem permissao de instalacao:
ele descobre as funcoes `test_*`, resolve as fixtures declaradas em
`conftest.py` e oferece o subconjunto de `pytest` que os testes utilizam
(`raises`, `approx`, `fixture` e a fixture `tmp_path`).

Uso:

    python ferramentas/rodar_testes.py
    python ferramentas/rodar_testes.py test_cenarios.py
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import shutil
import sys
import tempfile
import traceback
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_TESTES = os.path.join(RAIZ, "tests")


# -- substituto minimo do modulo pytest -----------------------------------


class _InformacaoDeErro:
    """Equivale ao objeto devolvido por `pytest.raises`."""

    def __init__(self) -> None:
        self.value: BaseException | None = None


class _FalhaDeTeste(AssertionError):
    """Levantada quando a excecao esperada nao ocorre."""


@contextmanager
def _raises(esperada, **_ignorado):
    informacao = _InformacaoDeErro()
    try:
        yield informacao
    except esperada as erro:
        informacao.value = erro
    else:
        nome = getattr(esperada, "__name__", str(esperada))
        raise _FalhaDeTeste(f"a excecao {nome} nao foi levantada")


class _Aproximado:
    """Equivale a `pytest.approx` para numeros isolados."""

    def __init__(self, valor: float, rel: float = 1e-6, abs: float = 1e-12) -> None:
        self.valor = valor
        self.rel = rel
        self.abs = abs

    def __eq__(self, outro: object) -> bool:
        try:
            diferenca = abs(float(outro) - self.valor)
        except (TypeError, ValueError):
            return NotImplemented
        return diferenca <= max(self.abs, self.rel * abs(self.valor))

    def __repr__(self) -> str:  # pragma: no cover - apenas para mensagens
        return f"aproximadamente {self.valor}"


def _fixture(funcao=None, **_ignorado):
    """Marca a funcao como fixture, sem escopo nem finalizacao."""

    def decorar(alvo: Callable[..., Any]) -> Callable[..., Any]:
        alvo.__e_fixture__ = True
        return alvo

    return decorar(funcao) if funcao is not None else decorar


def _instalar_pytest_falso() -> None:
    if "pytest" in sys.modules:
        return
    falso = types.ModuleType("pytest")
    falso.raises = _raises
    falso.approx = _Aproximado
    falso.fixture = _fixture
    falso.skip = lambda *a, **k: None
    sys.modules["pytest"] = falso


# -- descoberta e execucao -------------------------------------------------


def _importar(caminho: str) -> types.ModuleType:
    nome = os.path.splitext(os.path.basename(caminho))[0]
    especificacao = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    sys.modules[nome] = modulo
    especificacao.loader.exec_module(modulo)
    return modulo


def _fixtures_de(modulo: types.ModuleType) -> Dict[str, Callable[..., Any]]:
    return {
        nome: objeto
        for nome, objeto in vars(modulo).items()
        if callable(objeto) and getattr(objeto, "__e_fixture__", False)
    }


def _resolver(
    funcao: Callable[..., Any],
    fixtures: Dict[str, Callable[..., Any]],
    temporarias: List[str],
) -> Dict[str, Any]:
    argumentos: Dict[str, Any] = {}
    for nome in inspect.signature(funcao).parameters:
        if nome == "tmp_path":
            pasta = tempfile.mkdtemp(prefix="simulador-osi-")
            temporarias.append(pasta)
            argumentos[nome] = Path(pasta)
        elif nome in fixtures:
            argumentos[nome] = fixtures[nome]()
        else:
            raise KeyError(f"fixture desconhecida: {nome}")
    return argumentos


def _arquivos(selecao: List[str]) -> List[str]:
    if selecao:
        return [os.path.join(PASTA_TESTES, nome) for nome in selecao]
    return sorted(
        os.path.join(PASTA_TESTES, nome)
        for nome in os.listdir(PASTA_TESTES)
        if nome.startswith("test_") and nome.endswith(".py")
    )


def executar(selecao: List[str]) -> int:
    """Roda a bateria e devolve o codigo de saida do processo."""
    _instalar_pytest_falso()
    sys.path.insert(0, RAIZ)
    sys.path.insert(0, PASTA_TESTES)

    fixtures = _fixtures_de(_importar(os.path.join(PASTA_TESTES, "conftest.py")))
    aprovados = 0
    falhas: List[Tuple[str, str]] = []

    for caminho in _arquivos(selecao):
        modulo = _importar(caminho)
        nome_arquivo = os.path.basename(caminho)
        locais = dict(fixtures)
        locais.update(_fixtures_de(modulo))
        testes = [
            (nome, objeto)
            for nome, objeto in vars(modulo).items()
            if nome.startswith("test_") and callable(objeto)
        ]
        print(f"\n{nome_arquivo} ({len(testes)} testes)")
        for nome, teste in testes:
            temporarias: List[str] = []
            try:
                teste(**_resolver(teste, locais, temporarias))
            except Exception:
                falhas.append((f"{nome_arquivo}::{nome}", traceback.format_exc()))
                print(f"  FALHOU  {nome}")
            else:
                aprovados += 1
                print(f"  ok      {nome}")
            finally:
                for pasta in temporarias:
                    shutil.rmtree(pasta, ignore_errors=True)

    print("\n" + "=" * 70)
    for identificacao, detalhe in falhas:
        print(f"\n{identificacao}\n{detalhe}")
    print(f"{aprovados} aprovados, {len(falhas)} falharam")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar(sys.argv[1:]))
