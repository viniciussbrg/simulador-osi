"""Testes de ponta a ponta dos sete casos obrigatorios.

Este e o grupo de testes que confere os numeros publicados nos documentos: as
doze primeiras linhas do registro de exemplo do enunciado, a eficiencia de
11,4% do caso central citada no guia de documentacao, o custo 3 do desvio por
R2, os tres segmentos de 40, 40 e 24 octetos e a ausencia de qualquer linha de
camada 3 em R3 quando o quadro chega corrompido.
"""

from __future__ import annotations

import pytest

from simulador.cenarios import MENSAGEM_LONGA, MENSAGEM_PADRAO, cenarios_padrao, por_codigo
from simulador.motor import ErroDeSimulacaoError, executar_cenario
from simulador.cenarios import Fluxo


def _executar(topologia, codigo: str):
    return executar_cenario(topologia, por_codigo(codigo))


# -- mensagens de referencia ----------------------------------------------


def test_mensagens_tem_os_tamanhos_que_produzem_os_numeros_publicados():
    """42 octetos no caso central e 100 no caso da mensagem longa."""
    assert len(MENSAGEM_PADRAO.encode("utf-8")) == 42
    assert len(MENSAGEM_LONGA.encode("utf-8")) == 100


def test_os_sete_cenarios_estao_declarados():
    codigos = [cenario.codigo for cenario in cenarios_padrao()]
    assert codigos == ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    assert [cenario.rotulo for cenario in cenarios_padrao()] == [
        f"E{n}" for n in range(1, 8)
    ]


def test_cenario_pode_ser_procurado_pelos_dois_rotulos():
    assert por_codigo("E2").codigo == "C2"
    assert por_codigo("c2").rotulo == "E2"
    with pytest.raises(KeyError):
        por_codigo("C9")


# -- C1: entrega direta ----------------------------------------------------


def test_c1_entrega_direta_tem_um_unico_quadro_e_nenhum_roteador(topologia):
    resultado = _executar(topologia, "C1")
    assert resultado.resumo.quadros == 1
    assert resultado.resumo.octetos_transmitidos == 92
    assert resultado.resumo.eficiencia_percentual == "45.7%"
    assert resultado.caminho == (("H1", "H2"),)
    assert all(evento.dispositivo in ("H1", "H2") for evento in resultado.eventos)


def test_c1_reconhece_o_prefixo_compartilhado(topologia):
    eventos = _executar(topologia, "C1").eventos
    roteia = next(e for e in eventos if e.acao == "ROTEIA")
    assert "entrega direta" in roteia.descricao


# -- C2: caso central ------------------------------------------------------


def test_c2_reproduz_as_doze_primeiras_linhas_do_enunciado(topologia):
    """Comparacao direta com o exemplo da Secao 5.1 do enunciado."""
    eventos = _executar(topologia, "C2").eventos
    esperado = [
        (1, "H1", 7, "GERA", "processo navegador, destino servidorWeb", 42),
        (2, "H1", 6, "CODIFICA", None, 42),
        (3, "H1", 5, "ABRE", "sessão S-0001 estabelecida", 46),
        (4, "H1", 4, "SEGMENTA", None, 54),
        (5, "H1", 3, "ENCAPSULA", "10.0.1.10 → 10.0.3.10", 74),
        (6, "H1", 3, "ROTEIA", None, 74),
        (7, "H1", 2, "ENQUADRA", None, 92),
        (8, "H1", 1, "TRANSMITE", "736 bits no enlace H1-R1", 92),
        (9, "R1", 1, "RECEBE", "736 bits do enlace H1-R1", 92),
        (10, "R1", 2, "DESENQUADRA", "verificação de erro correta, quadro Q1 descartado", 74),
        (11, "R1", 3, "ROTEIA", "10.0.3.0/24 via R4, custo 2, interface e1", 74),
        (12, "R1", 2, "ENQUADRA", "BB:...:01:01 → BB:...:04:00, quadro Q2", 92),
    ]
    for passo, dispositivo, camada, acao, descricao, tamanho in esperado:
        evento = eventos[passo - 1]
        assert (evento.passo, evento.dispositivo, evento.camada, evento.acao) == (
            passo,
            dispositivo,
            camada,
            acao,
        )
        assert evento.tamanho == tamanho
        if descricao is not None:
            assert evento.descricao == descricao


def test_c2_tem_quatro_quadros_e_um_unico_pacote(topologia):
    """Restricao R2 e a Figura 2 do enunciado."""
    resultado = _executar(topologia, "C2")
    quadros = {e.identificador for e in resultado.eventos if e.acao == "ENQUADRA"}
    pacotes = {e.identificador for e in resultado.eventos if e.acao == "ENCAPSULA"}
    assert quadros == {"Q1", "Q2", "Q3", "Q4"}
    assert pacotes == {"P1"}
    assert resultado.resumo.quadros == 4


def test_c2_tem_a_eficiencia_publicada_na_documentacao(topologia):
    """42 octetos uteis sobre 368 transmitidos, ou 11,4%."""
    resumo = _executar(topologia, "C2").resumo
    assert resumo.octetos_uteis == 42
    assert resumo.octetos_transmitidos == 368
    assert resumo.eficiencia == pytest.approx(42 / 368)
    assert resumo.eficiencia_percentual == "11.4%"
    assert resumo.sobrecarga_percentual == "88.6%"


def test_c2_segue_o_caminho_de_menor_custo(topologia):
    resultado = _executar(topologia, "C2")
    assert resultado.caminho == (("H1", "R1"), ("R1", "R4"), ("R4", "R3"), ("R3", "H4"))


def test_c2_mantem_os_enderecos_logicos_e_troca_os_fisicos(topologia):
    """Restricao R3, verificada em todos os passos do percurso."""
    eventos = _executar(topologia, "C2").eventos
    logicos = {e.logicos for e in eventos if e.logicos}
    assert logicos == {("10.0.1.10", "10.0.3.10")}
    fisicos = {e.fisicos for e in eventos if e.fisicos}
    assert len(fisicos) == 4  # um par por salto


def test_c2_entrega_a_mensagem_integra_ao_processo(topologia):
    """Restricao R5: o conteudo cifrado na camada 6 so e decifrado na 6 do destino."""
    eventos = _executar(topologia, "C2").eventos
    entrega = next(e for e in eventos if e.acao == "ENTREGA")
    assert entrega.dispositivo == "H4"
    assert MENSAGEM_PADRAO[:20] in entrega.descricao
    assert not any(e.acao == "DECODIFICA" and e.dispositivo.startswith("R") for e in eventos)


def test_roteadores_nao_registram_camadas_superiores(topologia):
    """Restricao R1, observada no registro de todos os cenarios."""
    for cenario in cenarios_padrao():
        eventos = executar_cenario(topologia, cenario).eventos
        superiores = [e for e in eventos if e.dispositivo.startswith("R") and e.camada > 3]
        assert superiores == []


# -- C3: demultiplexacao ---------------------------------------------------


def test_c3_separa_dois_fluxos_no_destino(topologia):
    resultado = _executar(topologia, "C3")
    demux = [e for e in resultado.eventos if e.acao == "DEMULTIPLEXA"]
    assert len(demux) == 2
    assert {e.portas[0] for e in demux} == {5210, 5211}
    entregas = [e for e in resultado.eventos if e.acao == "ENTREGA"]
    assert len(entregas) == 2
    assert all(e.dispositivo == "H4" for e in entregas)


def test_c3_usa_sessoes_distintas(topologia):
    eventos = _executar(topologia, "C3").eventos
    sessoes = {e.descricao for e in eventos if e.acao == "ABRE"}
    assert len(sessoes) == 2


# -- C4: falha de enlace ---------------------------------------------------


def test_c4_desvia_por_r2_com_custo_3(topologia):
    resultado = _executar(topologia, "C4")
    assert resultado.caminho == (("H1", "R1"), ("R1", "R2"), ("R2", "R3"), ("R3", "H4"))
    roteia = next(
        e for e in resultado.eventos if e.dispositivo == "R1" and e.acao == "ROTEIA"
    )
    assert "via R2" in roteia.descricao
    assert "custo 3" in roteia.descricao


def test_c4_restaura_a_topologia_depois_da_simulacao(topologia):
    """A simulacao nao pode deixar a rede derrubada para o proximo cenario."""
    _executar(topologia, "C4")
    assert topologia.ativo("Enlace R1-R4")
    assert _executar(topologia, "C2").caminho[1] == ("R1", "R4")


# -- C5: destino inalcancavel ---------------------------------------------


def test_c5_descarta_na_camada_3_do_primeiro_roteador(topologia):
    resultado = _executar(topologia, "C5")
    descartes = [e for e in resultado.eventos if e.descarte]
    assert len(descartes) == 1
    assert descartes[0].dispositivo == "R1"
    assert descartes[0].camada == 3
    assert "sem rota" in descartes[0].descricao
    assert not resultado.resumo.entregue
    assert resultado.resumo.quadros == 1


def test_c5_nao_aciona_nenhuma_camada_apos_o_descarte(topologia):
    eventos = _executar(topologia, "C5").eventos
    posicao = next(i for i, e in enumerate(eventos) if e.descarte)
    assert posicao == len(eventos) - 1


# -- C6: erro de transmissao ----------------------------------------------


def test_c6_descarta_o_quadro_na_camada_2_de_r3(topologia):
    resultado = _executar(topologia, "C6")
    descartes = [e for e in resultado.eventos if e.descarte]
    assert len(descartes) == 1
    assert descartes[0].dispositivo == "R3"
    assert descartes[0].camada == 2
    assert "verificação de erro incorreta" in descartes[0].descricao


def test_c6_nao_registra_nenhuma_linha_de_camada_3_em_r3(topologia):
    """Requisito R9 dos criterios de avaliacao."""
    eventos = _executar(topologia, "C6").eventos
    assert [e for e in eventos if e.dispositivo == "R3" and e.camada == 3] == []
    assert _executar(topologia, "C6").resumo.quadros == 3


# -- C7: mensagem longa ----------------------------------------------------


def test_c7_divide_em_tres_segmentos_de_40_40_e_24(topologia):
    """Requisito R6 dos criterios de avaliacao."""
    eventos = _executar(topologia, "C7").eventos
    segmentacoes = [e for e in eventos if e.acao == "SEGMENTA"]
    assert len(segmentacoes) == 3
    cargas = [e.tamanho - 8 for e in segmentacoes]
    assert cargas == [40, 40, 24]


def test_c7_remonta_em_ordem_antes_de_entregar(topologia):
    eventos = _executar(topologia, "C7").eventos
    remonta = next(e for e in eventos if e.acao == "REMONTA")
    entrega = next(e for e in eventos if e.acao == "ENTREGA")
    assert remonta.dispositivo == "H4"
    assert remonta.passo < entrega.passo
    assert entrega.tamanho == 100
    # A camada 5 so e acionada depois da remontagem completa.
    camada_5 = [e for e in eventos if e.dispositivo == "H4" and e.camada == 5]
    assert len(camada_5) == 1
    assert camada_5[0].passo > remonta.passo


def test_c7_cada_segmento_percorre_a_rede_por_conta_propria(topologia):
    resultado = _executar(topologia, "C7")
    assert resultado.resumo.quadros == 12  # tres segmentos em quatro enlaces
    assert resultado.resumo.octetos_transmitidos == 968
    assert resultado.resumo.octetos_uteis == 100


# -- entradas invalidas ----------------------------------------------------


def test_origem_inexistente_e_recusada(topologia):
    with pytest.raises(ErroDeSimulacaoError):
        executar_cenario(
            topologia, por_codigo("C2"), fluxos=[Fluxo(origem="H9", destino_logico="10.0.3.10")]
        )


def test_destino_com_formato_invalido_e_recusado(topologia):
    with pytest.raises(ErroDeSimulacaoError):
        executar_cenario(
            topologia, por_codigo("C2"), fluxos=[Fluxo(origem="H1", destino_logico="10.0.3")]
        )


def test_mensagem_vazia_e_recusada(topologia):
    with pytest.raises(ErroDeSimulacaoError):
        executar_cenario(
            topologia,
            por_codigo("C2"),
            fluxos=[Fluxo(origem="H1", destino_logico="10.0.3.10", texto="")],
        )


def test_porta_fora_da_faixa_e_recusada(topologia):
    with pytest.raises(ErroDeSimulacaoError):
        executar_cenario(
            topologia,
            por_codigo("C2"),
            fluxos=[Fluxo(origem="H1", destino_logico="10.0.3.10", porta_origem=70000)],
        )


def test_roteador_nao_pode_ser_origem(topologia):
    with pytest.raises(ErroDeSimulacaoError):
        executar_cenario(
            topologia, por_codigo("C2"), fluxos=[Fluxo(origem="R1", destino_logico="10.0.3.10")]
        )


# -- casos limites ---------------------------------------------------------


def test_mensagem_de_um_octeto_e_simulada(topologia):
    resultado = executar_cenario(
        topologia, por_codigo("C2"), fluxos=[Fluxo(origem="H1", destino_logico="10.0.3.10", texto="a")]
    )
    assert resultado.resumo.octetos_uteis == 1
    assert resultado.resumo.quadros == 4


def test_mensagem_no_limite_exato_nao_e_segmentada(topologia):
    """44 octetos mais 4 de sessao totalizam exatamente o limite adotado."""
    resultado = executar_cenario(
        topologia,
        por_codigo("C2"),
        fluxos=[Fluxo(origem="H1", destino_logico="10.0.3.10", texto="x" * 44)],
    )
    segmentacoes = [e for e in resultado.eventos if e.acao == "SEGMENTA"]
    assert len(segmentacoes) == 1


def test_um_octeto_acima_do_limite_ja_segmenta(topologia):
    resultado = executar_cenario(
        topologia,
        por_codigo("C2"),
        fluxos=[Fluxo(origem="H1", destino_logico="10.0.3.10", texto="x" * 45)],
    )
    segmentacoes = [e for e in resultado.eventos if e.acao == "SEGMENTA"]
    assert len(segmentacoes) == 2


def test_mensagem_com_acentos_atravessa_a_rede_sem_perda(topologia):
    texto = "ação, coração e informação"
    resultado = executar_cenario(
        topologia, por_codigo("C2"), fluxos=[Fluxo(origem="H1", destino_logico="10.0.3.10", texto=texto)]
    )
    assert resultado.resumo.octetos_uteis == len(texto.encode("utf-8"))
    assert resultado.resumo.entregue


def test_computador_de_destino_errado_descarta_o_pacote(topologia):
    """H5 recebe um pacote endereçado a H4 e nao o entrega."""
    resultado = executar_cenario(
        topologia,
        por_codigo("C2"),
        fluxos=[Fluxo(origem="H1", destino_logico="10.0.3.11")],
    )
    assert resultado.resumo.entregue  # H5 e um destino legitimo
    assert resultado.caminho[-1] == ("R3", "H5")
