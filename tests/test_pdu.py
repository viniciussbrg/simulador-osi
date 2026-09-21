"""Testes da unidade de dados de protocolo.

Verificam as convencoes de tamanho fixadas no enunciado, o desenho da unidade
em blocos e, sobretudo, o guarda de acesso aos cabecalhos, que e o mecanismo
que implementa as restricoes R1 e R5.
"""

from __future__ import annotations

import pytest

from simulador.pdu import (
    TAMANHO_CABECALHO,
    TAMANHO_FINALIZADOR,
    Cabecalho,
    ErroDeSegmentacaoError,
    UnidadeDados,
    ViolacaoDeCamadaError,
    abreviar_fisico,
    dividir_carga,
)


# -- convencoes de tamanho ------------------------------------------------


def test_tamanhos_dos_cabecalhos_seguem_o_enunciado():
    """4 octetos para a camada 5, 8 para a 4, 20 para a 3, 14 mais 4 para a 2."""
    assert TAMANHO_CABECALHO == {5: 4, 4: 8, 3: 20, 2: 14}
    assert TAMANHO_FINALIZADOR == 4


def test_tamanho_acumula_dados_cabecalhos_e_finalizador():
    """A unidade cresce exatamente o tamanho de cada cabecalho acrescentado."""
    unidade = UnidadeDados(dados=b"x" * 42, unidade="Mensagem")
    assert unidade.tamanho == 42

    unidade = unidade.acrescentar_cabecalho(
        Cabecalho(5, {"sessao": "S-0001"}, TAMANHO_CABECALHO[5]), "Mensagem"
    )
    assert unidade.tamanho == 46

    unidade = unidade.acrescentar_cabecalho(
        Cabecalho(4, {"porta_origem": 5210}, TAMANHO_CABECALHO[4]), "Segmento"
    )
    assert unidade.tamanho == 54

    unidade = unidade.acrescentar_cabecalho(
        Cabecalho(3, {"destino": "10.0.3.10"}, TAMANHO_CABECALHO[3]), "Pacote"
    )
    assert unidade.tamanho == 74

    unidade = unidade.acrescentar_cabecalho(
        Cabecalho(2, {"tipo": "0x0800"}, TAMANHO_CABECALHO[2]), "Quadro"
    )
    unidade = unidade.acrescentar_finalizador(
        Cabecalho(2, {"verificacao": "0"}, TAMANHO_FINALIZADOR, finalizador=True)
    )
    assert unidade.tamanho == 92
    assert unidade.tamanho_bits == 736


def test_unidade_e_imutavel_ao_receber_cabecalho():
    """Acrescentar um cabecalho produz um objeto novo, nunca altera o original."""
    original = UnidadeDados(dados=b"abc")
    derivada = original.acrescentar_cabecalho(Cabecalho(5, {}, 4), "Mensagem")
    assert original.tamanho == 3
    assert derivada.tamanho == 7
    assert original is not derivada


# -- restricoes R1 e R5 ---------------------------------------------------


def test_camada_le_apenas_o_proprio_cabecalho():
    """Uma camada so interpreta o cabecalho inserido pela sua camada par."""
    unidade = UnidadeDados(dados=b"dados")
    unidade = unidade.acrescentar_cabecalho(Cabecalho(4, {"porta_origem": 5210}, 8), "Segmento")
    unidade = unidade.acrescentar_cabecalho(Cabecalho(3, {"destino": "10.0.3.10"}, 20), "Pacote")

    assert unidade.ler_cabecalho(3).campos["destino"] == "10.0.3.10"
    with pytest.raises(ViolacaoDeCamadaError):
        unidade.ler_cabecalho(4)


def test_roteador_nao_alcanca_a_porta_do_segmento():
    """Restricao R1: com o cabecalho da camada 3 no topo, a porta e inacessivel."""
    pacote = (
        UnidadeDados(dados=b"conteudo")
        .acrescentar_cabecalho(Cabecalho(5, {"sessao": "S-0001"}, 4), "Mensagem")
        .acrescentar_cabecalho(Cabecalho(4, {"porta_destino": 443}, 8), "Segmento")
        .acrescentar_cabecalho(Cabecalho(3, {"destino": "10.0.3.10"}, 20), "Pacote")
    )
    for camada_indevida in (4, 5, 6, 7):
        with pytest.raises(ViolacaoDeCamadaError):
            pacote.ler_cabecalho(camada_indevida)


def test_remover_cabecalho_exige_a_camada_correta():
    unidade = UnidadeDados(dados=b"x").acrescentar_cabecalho(Cabecalho(3, {}, 20), "Pacote")
    with pytest.raises(ViolacaoDeCamadaError):
        unidade.remover_cabecalho(2, "Quadro")
    assert unidade.remover_cabecalho(3, "Segmento").tamanho == 1


def test_ler_cabecalho_de_unidade_sem_cabecalhos_falha():
    with pytest.raises(ViolacaoDeCamadaError):
        UnidadeDados(dados=b"x").ler_cabecalho(3)


# -- verificacao de erro --------------------------------------------------


def test_verificacao_muda_quando_um_bit_e_alterado():
    """Base da deteccao de erro do caso C6."""
    quadro = UnidadeDados(dados=b"mensagem").acrescentar_cabecalho(
        Cabecalho(2, {"tipo": "0x0800"}, 14), "Quadro"
    )
    original = quadro.verificacao()
    corrompido = quadro.com_dados(bytes([quadro.dados[0] ^ 0x01]) + quadro.dados[1:])
    assert corrompido.verificacao() != original


# -- exibicao -------------------------------------------------------------


def test_blocos_colocam_cabecalhos_a_esquerda_e_finalizador_a_direita():
    """Requisito V3: a ordem de desenho da unidade de dados."""
    quadro = (
        UnidadeDados(dados=b"d" * 10)
        .acrescentar_cabecalho(Cabecalho(3, {}, 20), "Pacote")
        .acrescentar_cabecalho(Cabecalho(2, {}, 14), "Quadro")
        .acrescentar_finalizador(Cabecalho(2, {}, 4, finalizador=True))
    )
    rotulos = [bloco["rotulo"] for bloco in quadro.blocos()]
    assert rotulos == ["H2", "H3", "Dados", "T2"]


def test_abreviacao_do_endereco_fisico_segue_o_registro_do_enunciado():
    assert abreviar_fisico("AA:00:00:00:01:0A") == "AA:...:01:0A"
    assert abreviar_fisico("BB:00:00:00:04:00") == "BB:...:04:00"
    assert abreviar_fisico("invalido") == "invalido"


# -- segmentacao ----------------------------------------------------------


def test_divisao_reserva_espaco_para_o_cabecalho_ja_presente():
    """O cabecalho de sessao entra uma unica vez, no primeiro segmento."""
    unidade = UnidadeDados(dados=b"x" * 100).acrescentar_cabecalho(
        Cabecalho(5, {"sessao": "S-0001"}, 4), "Mensagem"
    )
    fatias = dividir_carga(unidade, 40)
    assert [len(f) for f in fatias] == [36, 40, 24]
    assert sum(len(f) for f in fatias) == 100


def test_divisao_recusa_segmento_menor_que_o_cabecalho():
    unidade = UnidadeDados(dados=b"x" * 50).acrescentar_cabecalho(Cabecalho(5, {}, 4), "Mensagem")
    with pytest.raises(ErroDeSegmentacaoError):
        dividir_carga(unidade, 4)
