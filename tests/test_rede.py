"""Testes da topologia e do encaminhamento.

Conferem que o arquivo externo reproduz a Figura 1 e a Tabela 1 do enunciado,
que as tabelas de encaminhamento derivadas dos custos coincidem com o unico
valor publicado no enunciado (linha 011 do registro de exemplo) e que a queda
de um enlace altera a rota como o caso C4 descreve.
"""

from __future__ import annotations

import json

import pytest

from simulador.rede import ErroDeTopologiaError, Topologia

ENDERECOS_DA_TABELA_1 = {
    "H1:eth0": ("10.0.1.10", "AA:00:00:00:01:0A"),
    "H2:eth0": ("10.0.1.11", "AA:00:00:00:01:0B"),
    "H3:eth0": ("10.0.2.10", "AA:00:00:00:02:0A"),
    "H4:eth0": ("10.0.3.10", "AA:00:00:00:03:0A"),
    "H5:eth0": ("10.0.3.11", "AA:00:00:00:03:0B"),
    "R1:e0": ("10.0.1.1", "BB:00:00:00:01:00"),
    "R1:e1": ("10.0.14.1", "BB:00:00:00:01:01"),
    "R1:e2": ("10.0.12.1", "BB:00:00:00:01:02"),
    "R2:e0": ("10.0.12.2", "BB:00:00:00:02:00"),
    "R2:e1": ("10.0.23.2", "BB:00:00:00:02:01"),
    "R2:e2": ("10.0.2.1", "BB:00:00:00:02:02"),
    "R3:e0": ("10.0.34.3", "BB:00:00:00:03:00"),
    "R3:e1": ("10.0.23.3", "BB:00:00:00:03:01"),
    "R3:e2": ("10.0.3.1", "BB:00:00:00:03:02"),
    "R4:e0": ("10.0.14.4", "BB:00:00:00:04:00"),
    "R4:e1": ("10.0.34.4", "BB:00:00:00:04:01"),
}


# -- topologia de referencia ----------------------------------------------


def test_topologia_tem_a_composicao_da_figura_1(topologia):
    """Tres redes locais, quatro roteadores e cinco computadores."""
    assert len(topologia.computadores()) == 5
    assert len(topologia.roteadores()) == 4
    locais = [s for s in topologia.segmentos.values() if s.local]
    assert len(locais) == 3


def test_enderecos_conferem_com_a_tabela_1(topologia):
    encontrados = {
        interface.identificador: (interface.logico, interface.fisico)
        for interface in topologia.todas_interfaces()
    }
    assert encontrados == ENDERECOS_DA_TABELA_1


def test_custos_dos_enlaces_entre_roteadores(topologia):
    """Custos que tornam deterministica a escolha de rota."""
    custos = {s.nome: s.custo for s in topologia.segmentos.values() if not s.local}
    assert custos == {
        "Enlace R1-R4": 1,
        "Enlace R3-R4": 1,
        "Enlace R1-R2": 2,
        "Enlace R2-R3": 1,
    }


# -- encaminhamento --------------------------------------------------------


def test_rota_de_r1_para_a_rede_c_confere_com_o_registro_do_enunciado(topologia):
    """Linha 011 do exemplo: 10.0.3.0/24 via R4, custo 2, interface e1."""
    rota = topologia.consultar("R1", "10.0.3.10")
    assert rota.destino == "10.0.3.0/24"
    assert rota.custo == 2
    assert rota.interface == "e1"
    assert rota.proximo_salto == "10.0.14.4"  # interface e0 de R4


def test_rede_conectada_diretamente_nao_tem_proximo_salto(topologia):
    rota = topologia.consultar("R1", "10.0.1.10")
    assert rota.direta
    assert rota.interface == "e0"
    assert rota.custo == 0


def test_queda_do_enlace_r1_r4_leva_a_rota_por_r2_com_custo_3(topologia):
    """Caso C4: com o enlace R1-R4 fora, o caminho passa a custar 3."""
    topologia.derrubar("Enlace R1-R4")
    rota = topologia.consultar("R1", "10.0.3.10")
    assert rota.custo == 3
    assert rota.interface == "e2"
    assert rota.proximo_salto == "10.0.12.2"  # interface e0 de R2

    topologia.restaurar("Enlace R1-R4")
    assert topologia.consultar("R1", "10.0.3.10").custo == 2


def test_destino_fora_da_topologia_nao_tem_rota(topologia):
    """Caso C5: 10.0.9.10 nao pertence a nenhuma rede declarada."""
    assert topologia.consultar("R1", "10.0.9.10") is None


def test_tabela_de_encaminhamento_cobre_todas_as_redes(topologia):
    for roteador in topologia.roteadores():
        destinos = {rota.destino for rota in topologia.tabela_encaminhamento(roteador)}
        assert destinos == {s.prefixo for s in topologia.segmentos.values()}


# -- vizinhanca de enlace --------------------------------------------------


def test_computadores_da_mesma_rede_sao_vizinhos_de_enlace(topologia):
    """Base da entrega direta do caso C1."""
    h1 = topologia.interface_por_nome("H1", "eth0")
    assert topologia.resolver_fisico(h1, "10.0.1.11") == "AA:00:00:00:01:0B"
    assert topologia.resolver_fisico(h1, "10.0.3.10") is None


def test_enlace_derrubado_apaga_a_vizinhanca(topologia):
    h1 = topologia.interface_por_nome("H1", "eth0")
    topologia.derrubar("Rede A")
    assert topologia.vizinhos_de_enlace(h1) == []
    topologia.restaurar_todos()
    assert topologia.vizinhos_de_enlace(h1)


def test_mesmo_prefixo_reconhece_a_rede_local(topologia):
    h1 = topologia.interface_por_nome("H1", "eth0")
    assert topologia.mesmo_prefixo(h1, "10.0.1.11")
    assert not topologia.mesmo_prefixo(h1, "10.0.3.10")
    assert not topologia.mesmo_prefixo(h1, "nao-e-um-endereco")


# -- validacao de arquivos invalidos --------------------------------------


def _gravar(tmp_path, dados) -> str:
    caminho = tmp_path / "topologia.json"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return str(caminho)


def test_arquivo_ausente_produz_erro_claro(tmp_path):
    with pytest.raises(ErroDeTopologiaError) as erro:
        Topologia.carregar(str(tmp_path / "inexistente.json"))
    assert "nao encontrado" in str(erro.value)


def test_json_invalido_produz_erro_claro(tmp_path):
    caminho = tmp_path / "topologia.json"
    caminho.write_text("{ isto nao e json", encoding="utf-8")
    with pytest.raises(ErroDeTopologiaError):
        Topologia.carregar(str(caminho))


def test_interface_que_referencia_rede_inexistente_e_recusada(tmp_path):
    dados = {
        "redes": [{"nome": "Rede A", "prefixo": "10.0.1.0/24"}],
        "dispositivos": [
            {
                "nome": "H1",
                "tipo": "computador",
                "interfaces": [
                    {
                        "nome": "eth0",
                        "logico": "10.0.1.10",
                        "mascara": 24,
                        "fisico": "AA:00:00:00:01:0A",
                        "rede": "Rede Z",
                    }
                ],
            }
        ],
    }
    with pytest.raises(ErroDeTopologiaError):
        Topologia.carregar(_gravar(tmp_path, dados))


def test_enderecos_logicos_repetidos_sao_recusados(tmp_path):
    interface = {
        "nome": "eth0",
        "logico": "10.0.1.10",
        "mascara": 24,
        "fisico": "AA:00:00:00:01:0A",
        "rede": "Rede A",
    }
    outra = dict(interface, fisico="AA:00:00:00:01:0B")
    dados = {
        "redes": [{"nome": "Rede A", "prefixo": "10.0.1.0/24"}],
        "dispositivos": [
            {"nome": "H1", "tipo": "computador", "interfaces": [interface]},
            {"nome": "H2", "tipo": "computador", "interfaces": [outra]},
        ],
    }
    with pytest.raises(ErroDeTopologiaError) as erro:
        Topologia.carregar(_gravar(tmp_path, dados))
    assert "logico repetido" in str(erro.value)


def test_topologia_alternativa_e_simulavel(tmp_path):
    """Trocar o arquivo troca a rede: dois computadores e um roteador."""
    dados = {
        "nome": "Rede minima",
        "redes": [
            {"nome": "LAN 1", "prefixo": "192.168.0.0/24", "custo": 0, "tipo": "local"},
            {"nome": "LAN 2", "prefixo": "192.168.1.0/24", "custo": 0, "tipo": "local"},
        ],
        "dispositivos": [
            {
                "nome": "PC1",
                "tipo": "computador",
                "gateway": "192.168.0.1",
                "interfaces": [
                    {
                        "nome": "eth0",
                        "logico": "192.168.0.10",
                        "mascara": 24,
                        "fisico": "AA:00:00:00:00:01",
                        "rede": "LAN 1",
                    }
                ],
            },
            {
                "nome": "PC2",
                "tipo": "computador",
                "gateway": "192.168.1.1",
                "interfaces": [
                    {
                        "nome": "eth0",
                        "logico": "192.168.1.10",
                        "mascara": 24,
                        "fisico": "AA:00:00:00:00:02",
                        "rede": "LAN 2",
                    }
                ],
            },
            {
                "nome": "RT1",
                "tipo": "roteador",
                "interfaces": [
                    {
                        "nome": "e0",
                        "logico": "192.168.0.1",
                        "mascara": 24,
                        "fisico": "BB:00:00:00:00:01",
                        "rede": "LAN 1",
                    },
                    {
                        "nome": "e1",
                        "logico": "192.168.1.1",
                        "mascara": 24,
                        "fisico": "BB:00:00:00:00:02",
                        "rede": "LAN 2",
                    },
                ],
            },
        ],
    }
    outra = Topologia.carregar(_gravar(tmp_path, dados))
    rota = outra.consultar("RT1", "192.168.1.10")
    assert rota.direta and rota.interface == "e1"
