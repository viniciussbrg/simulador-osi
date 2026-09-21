"""Testes das camadas e da pilha de cada dispositivo.

Verificam o escopo minimo da Tabela 2 do enunciado e as cinco restricoes de
projeto: o roteador nao implementa as camadas superiores, o quadro e
reconstruido a cada salto, os enderecos logicos permanecem, a camada 2 nao
escolhe rota e cada camada so interpreta o cabecalho da sua par.
"""

from __future__ import annotations

import pytest

from simulador.camadas import (
    CARGA_POR_SEGMENTO,
    LIMITE_SEGMENTACAO,
    Aplicacao,
    Enlace,
    Fisica,
    Rede,
    Sessao,
    Transporte,
    cifrar,
)
from simulador.dispositivos import (
    Computador,
    Roteador,
    ServicosDaSimulacao,
    construir_dispositivos,
)
from simulador.pdu import UnidadeDados, ViolacaoDeCamadaError


def _dispositivos(topologia):
    return construir_dispositivos(topologia, ServicosDaSimulacao())


# -- composicao das pilhas -------------------------------------------------


def test_computador_tem_sete_camadas_e_roteador_tres(topologia):
    """Requisito R2 dos criterios de avaliacao."""
    dispositivos = _dispositivos(topologia)
    assert dispositivos["H1"].numero_de_camadas == 7
    assert dispositivos["R1"].numero_de_camadas == 3
    assert dispositivos["H1"].pilha.numeros == [7, 6, 5, 4, 3, 2, 1]
    assert dispositivos["R1"].pilha.numeros == [3, 2, 1]


def test_roteador_nao_possui_camadas_superiores(topologia):
    """Restricao R1: nao ha caminho de codigo ate a camada 4 em um roteador."""
    roteador = _dispositivos(topologia)["R1"]
    for numero in (4, 5, 6, 7):
        assert numero not in roteador.pilha
        with pytest.raises(KeyError):
            roteador.pilha.camada(numero)


def test_camadas_conhecem_apenas_as_adjacentes(topologia):
    """Nenhuma camada acessa uma camada que nao lhe seja adjacente."""
    pilha = _dispositivos(topologia)["H1"].pilha
    assert pilha.camada(7).superior is None
    assert pilha.camada(7).inferior is pilha.camada(6)
    assert pilha.camada(4).superior is pilha.camada(5)
    assert pilha.camada(4).inferior is pilha.camada(3)
    assert pilha.camada(1).inferior is None


# -- camada 6: codificacao e cifra ----------------------------------------


def test_cifra_preserva_o_tamanho_e_e_reversivel():
    """A cifra nao pode alterar a contagem de octetos do registro."""
    original = "GET /index.html HTTP/1.1 Host: servidorweb".encode("utf-8")
    cifrado = cifrar(original)
    assert len(cifrado) == len(original)
    assert cifrado != original
    assert cifrar(cifrado) == original


def test_apresentacao_cifra_na_descida_e_decifra_na_subida(topologia):
    camada = _dispositivos(topologia)["H1"].pilha.camada(6)
    entrada = UnidadeDados(dados=b"mensagem clara")
    descida = camada.descer(entrada).unidades[0]
    assert descida.dados != entrada.dados
    subida = camada.subir(descida).unidades[0]
    assert subida.dados == entrada.dados


# -- camada 4: segmentacao e remontagem ------------------------------------


def _segmentar(topologia, texto: str):
    computador = _dispositivos(topologia)["H1"]
    sessao = computador.pilha.camada(5)
    transporte = computador.pilha.camada(4)
    mensagem = UnidadeDados(
        dados=texto.encode("utf-8"),
        contexto={"porta_origem": 5210, "porta_destino": 443},
    )
    com_sessao = sessao.descer(mensagem).unidades[0]
    return transporte, transporte.descer(com_sessao).unidades


def test_mensagem_curta_viaja_em_um_unico_segmento(topologia):
    """42 octetos mais 4 de sessao cabem no limite adotado."""
    _, segmentos = _segmentar(topologia, "GET /index.html HTTP/1.1 Host: servidorweb")
    assert len(segmentos) == 1
    assert segmentos[0].tamanho == 54


def test_mensagem_longa_gera_tres_segmentos_de_40_40_e_24(topologia):
    """Requisito R6 dos criterios de avaliacao."""
    _, segmentos = _segmentar(topologia, "x" * 100)
    cargas = [segmento.tamanho - 8 for segmento in segmentos]
    assert cargas == [40, 40, 24]
    assert sum(cargas) == 104  # 100 octetos de dados mais o cabecalho de sessao


def test_limite_de_segmentacao_e_a_convencao_documentada():
    assert LIMITE_SEGMENTACAO == 48
    assert CARGA_POR_SEGMENTO == 40


def test_remontagem_ordena_segmentos_recebidos_fora_de_ordem(topologia):
    """A camada 4 do destino entrega a mensagem na ordem correta."""
    _, segmentos = _segmentar(topologia, "x" * 100)
    destino = _dispositivos(topologia)["H4"].pilha.camada(4)
    entregues = []
    for segmento in reversed(segmentos):  # chegada na ordem 3, 2, 1
        resultado = destino.subir(segmento.com_contexto(origem_logica="10.0.1.10"))
        entregues.extend(resultado.unidades)
    assert len(entregues) == 1
    assert entregues[0].dados == b"x" * 100


def test_fluxos_com_portas_distintas_sao_demultiplexados(topologia):
    """Caso C3: cada fluxo e remontado no seu proprio buffer."""
    computador = _dispositivos(topologia)["H1"]
    transporte_destino = _dispositivos(topologia)["H4"].pilha.camada(4)
    sessao = computador.pilha.camada(5)
    transporte = computador.pilha.camada(4)

    def segmento_de(porta: int, texto: bytes):
        mensagem = UnidadeDados(
            dados=texto, contexto={"porta_origem": porta, "porta_destino": 443}
        )
        return transporte.descer(sessao.descer(mensagem).unidades[0]).unidades[0]

    primeiro = transporte_destino.subir(
        segmento_de(5210, b"fluxo A").com_contexto(origem_logica="10.0.1.10")
    )
    segundo = transporte_destino.subir(
        segmento_de(5211, b"fluxo B").com_contexto(origem_logica="10.0.1.11")
    )
    assert primeiro.unidades[0].dados == b"fluxo A"
    assert segundo.unidades[0].dados == b"fluxo B"
    assert primeiro.acoes[0].acao == "DEMULTIPLEXA"


# -- camada 3: decisao de rota --------------------------------------------


def test_camada_3_do_computador_reconhece_a_entrega_direta(topologia):
    computador = _dispositivos(topologia)["H1"]
    decisao = computador.decidir_encaminhamento("10.0.1.11")
    assert decisao.proximo_salto == "10.0.1.11"
    assert "entrega direta" in decisao.descricao


def test_camada_3_do_computador_usa_o_gateway_fora_da_rede(topologia):
    computador = _dispositivos(topologia)["H1"]
    decisao = computador.decidir_encaminhamento("10.0.3.10")
    assert decisao.proximo_salto == "10.0.1.1"


def test_roteador_sem_rota_devolve_nada(topologia):
    """Caso C5: o descarte nasce da ausencia de rota."""
    assert _dispositivos(topologia)["R1"].decidir_encaminhamento("10.0.9.10") is None


def test_endereco_invalido_nao_produz_decisao(topologia):
    assert _dispositivos(topologia)["H1"].decidir_encaminhamento("999.999.1.1") is None


# -- camada 2: enquadramento e verificacao ---------------------------------


def _pacote_pronto(topologia, dispositivo="H1"):
    computador = _dispositivos(topologia)[dispositivo]
    rede = computador.pilha.camada(3)
    unidade = UnidadeDados(
        dados=b"conteudo",
        contexto={"origem_logica": "10.0.1.10", "destino_logico": "10.0.3.10"},
    )
    return computador, rede.descer(unidade).unidades[0]


def test_camada_2_recebe_o_vizinho_ja_decidido(topologia):
    """Restricao R4: a camada 2 apenas entrega ao vizinho indicado pela camada 3."""
    computador, pacote = _pacote_pronto(topologia)
    assert pacote.contexto["proximo_salto"] == "10.0.1.1"
    quadro = computador.pilha.camada(2).descer(pacote).unidades[0]
    assert quadro.contexto["vizinho"] == "R1"
    with pytest.raises(ViolacaoDeCamadaError):
        quadro.ler_cabecalho(3)  # o cabecalho da camada 3 ja nao e o mais externo


def test_quadro_corrompido_e_descartado_sem_acionar_camada_superior(topologia):
    """Caso C6: a verificacao de erro impede a subida."""
    computador, pacote = _pacote_pronto(topologia)
    enlace = computador.pilha.camada(2)
    quadro = enlace.descer(pacote).unidades[0]
    corrompido = quadro.com_dados(bytes([quadro.dados[0] ^ 0x01]) + quadro.dados[1:])

    receptor = _dispositivos(topologia)["R1"].pilha.camada(2)
    resultado = receptor.subir(corrompido)
    assert resultado.descartar
    assert resultado.unidades == []
    assert resultado.acoes[0].acao == "DESCARTA"


def test_quadro_integro_sobe_como_pacote(topologia):
    computador, pacote = _pacote_pronto(topologia)
    quadro = computador.pilha.camada(2).descer(pacote).unidades[0]
    resultado = _dispositivos(topologia)["R1"].pilha.camada(2).subir(quadro)
    assert not resultado.descartar
    assert resultado.unidades[0].unidade == "Pacote"
    assert resultado.acoes[0].acao == "DESENQUADRA"


def test_quadros_sucessivos_recebem_numeros_distintos(topologia):
    """Restricao R2: cada enlace exibe um quadro proprio e numerado."""
    computador, pacote = _pacote_pronto(topologia)
    enlace = computador.pilha.camada(2)
    primeiro = enlace.descer(pacote).unidades[0]
    segundo = enlace.descer(pacote).unidades[0]
    assert primeiro.identificador == "Q1"
    assert segundo.identificador == "Q2"
    assert primeiro is not segundo


# -- camada 1 --------------------------------------------------------------


def test_camada_1_relata_o_tamanho_em_bits(topologia):
    computador, pacote = _pacote_pronto(topologia)
    quadro = computador.pilha.camada(2).descer(pacote).unidades[0]
    acao = computador.pilha.camada(1).descer(quadro).acoes[0]
    assert acao.acao == "TRANSMITE"
    assert f"{quadro.tamanho * 8} bits" in acao.descricao


# -- camada 7 --------------------------------------------------------------


def test_camada_7_identifica_o_processo_pelo_nome(topologia):
    camada = _dispositivos(topologia)["H1"].pilha.camada(7)
    unidade = UnidadeDados(
        contexto={
            "texto": "ola",
            "processo_origem": "navegador",
            "processo_destino": "servidorWeb",
        }
    )
    acao = camada.descer(unidade).acoes[0]
    assert acao.acao == "GERA"
    assert "navegador" in acao.descricao and "servidorWeb" in acao.descricao
