"""Testes do registro de eventos e do quadro numerico da comunicacao."""

from __future__ import annotations

import os

import pytest

from simulador.cenarios import por_codigo
from simulador.motor import comparar_eficiencias, executar_cenario
from simulador.registro import Evento, ResumoComunicacao, montar_texto, salvar


# -- formato da linha ------------------------------------------------------


def test_linha_tem_cinco_campos_separados_por_barra_e_termina_no_tamanho():
    evento = Evento(
        passo=1,
        dispositivo="H1",
        camada=7,
        acao="GERA",
        descricao="processo navegador, destino servidorWeb",
        tamanho=42,
        unidade="Mensagem",
    )
    linha = evento.linha
    campos = [parte.strip() for parte in linha.split("|")]
    assert len(campos) == 5
    assert campos[0] == "001"
    assert campos[1] == "H1"
    assert campos[2] == "L7"
    assert campos[3] == "GERA"
    assert campos[4].startswith("processo navegador")
    assert linha.rstrip().endswith("42 B")


def test_passo_e_escrito_com_tres_digitos():
    evento = Evento(1, "H1", 1, "X", "y", 0, "Bits")
    assert evento.linha.startswith("001 |")
    evento = Evento(123, "H1", 1, "X", "y", 0, "Bits")
    assert evento.linha.startswith("123 |")


def test_todas_as_linhas_de_um_cenario_tem_o_mesmo_formato(topologia):
    for evento in executar_cenario(topologia, por_codigo("C7")).eventos:
        assert len(evento.linha.split("|")) == 5
        assert evento.linha.rstrip().endswith(" B")


# -- eficiencia ------------------------------------------------------------


def test_eficiencia_e_a_razao_entre_dados_e_transmitido():
    resumo = ResumoComunicacao(
        cenario="E2/C2", titulo="teste", octetos_uteis=42, octetos_transmitidos=368
    )
    assert resumo.eficiencia == pytest.approx(42 / 368)
    assert resumo.sobrecarga == pytest.approx(1 - 42 / 368)
    assert resumo.eficiencia_percentual == "11.4%"


def test_eficiencia_de_transmissao_vazia_nao_divide_por_zero():
    resumo = ResumoComunicacao(cenario="X", titulo="t")
    assert resumo.eficiencia == 0.0
    assert resumo.sobrecarga == 1.0


def test_comparacao_c1_c2_exigida_no_enunciado(topologia):
    """O enunciado pede os dois valores na tela."""
    valores = comparar_eficiencias(topologia)
    assert valores["C1"].eficiencia > valores["C2"].eficiencia
    assert valores["C1"].eficiencia_percentual == "45.7%"
    assert valores["C2"].eficiencia_percentual == "11.4%"
    assert valores["C1"].enlaces == 1
    assert valores["C2"].enlaces == 4


def test_resumo_explica_a_mensagem_nao_entregue(topologia):
    resumo = executar_cenario(topologia, por_codigo("C6")).resumo
    assert not resumo.entregue
    assert "descarte em R3" in resumo.observacao


# -- gravacao --------------------------------------------------------------


def test_texto_do_registro_traz_cabecalho_linhas_e_resumo(topologia):
    resultado = executar_cenario(topologia, por_codigo("C2"))
    texto = montar_texto(resultado.eventos, resultado.resumo)
    assert "DESCRIÇÃO" in texto
    assert "Custo do empilhamento" in texto
    assert "11.4%" in texto
    assert texto.count("\n") >= len(resultado.eventos)


def test_registro_e_gravado_em_arquivo(topologia, tmp_path):
    resultado = executar_cenario(topologia, por_codigo("C2"))
    destino = str(tmp_path / "registro.txt")
    caminho = salvar(destino, resultado.eventos, resultado.resumo)
    assert os.path.isfile(caminho)
    conteudo = open(caminho, encoding="utf-8").read()
    assert "001 | H1 | L7" in conteudo
    assert "Eficiência" in conteudo


def test_gravacao_cria_a_pasta_de_destino(topologia, tmp_path):
    resultado = executar_cenario(topologia, por_codigo("C1"))
    destino = str(tmp_path / "nova" / "registro.txt")
    assert os.path.isfile(salvar(destino, resultado.eventos, resultado.resumo))
