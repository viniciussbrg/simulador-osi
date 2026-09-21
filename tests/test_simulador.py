import pytest
import json
import struct
from unittest.mock import Mock, patch, mock_open

# Importe suas classes reais aqui (ajuste de acordo com o nome do seu arquivo)
# from topologia import Topologia, Dispositivo, Segmento, Interface, ErroTopologia
# from camada_fisica import CamadaFisica
# from camada_enlace import sobe, calcular_verificacao # (ajuste conforme seu código)

# ====================================================================
# MOCKS AUXILIARES PARA OS TESTES
# ====================================================================

def mock_evento(contexto, camada, acao, mensagem, unidade, **kwargs):
    """Simula a função _evento do seu código."""
    return {
        "camada": camada,
        "acao": acao,
        "mensagem": mensagem,
        **kwargs
    }

# ====================================================================
# TESTES DA CAMADA FÍSICA (L1)
# ====================================================================

@patch("seu_modulo.camada_fisica._evento", side_effect=mock_evento)
def test_camada_fisica_desce(mock_evento_func):
    camada = CamadaFisica()
    
    # Simula a PDU (Unidade de Dados)
    unidade_mock = Mock()
    unidade_mock.tamanho_bits.return_value = 128
    
    # Simula o contexto de descida
    contexto = {
        "dispositivo": "PC1",
        "saida": {"proximo_dispositivo": "R1"}
    }
    
    nova_unidade, eventos = camada.desce(unidade_mock, contexto)
    
    assert nova_unidade == unidade_mock
    assert len(eventos) == 1
    assert eventos[0]["camada"] == "L1"
    assert eventos[0]["acao"] == "TRANSMITE"
    assert eventos[0]["enlace"] == ("PC1", "R1")

@patch("seu_modulo.camada_fisica._evento", side_effect=mock_evento)
def test_camada_fisica_sobe_com_erro(mock_evento_func):
    camada = CamadaFisica()
    
    unidade_mock = Mock()
    unidade_mock.tamanho_bits.return_value = 128
    # Injetando um erro de bit
    unidade_mock.metadados = {"bit_alterado": True}
    
    contexto = {
        "dispositivo": "R1",
        "enlace_origem": "PC1"
    }
    
    nova_unidade, eventos = camada.sobe(unidade_mock, contexto)
    
    assert nova_unidade == unidade_mock
    assert eventos[0]["acao"] == "RECEBE"
    assert eventos[0]["estado"] == "erro"
    assert "um bit foi alterado" in eventos[0]["mensagem"]

# ====================================================================
# TESTES DA CAMADA DE ENLACE (L2) - FUNÇÃO SOBE (CRC)
# ====================================================================

@patch("seu_modulo.camada_enlace._evento", side_effect=mock_evento)
@patch("seu_modulo.camada_enlace.calcular_verificacao")
def test_camada_enlace_sobe_descarte_por_crc_invalido(mock_calcular_crc, mock_evento_func):
    # O mock de CRC dirá que a soma esperada é diferente da recebida
    mock_calcular_crc.return_value = 0x12345678
    
    unidade_mock = Mock()
    unidade_mock.quadro = "FRAME_01"
    unidade_mock.cabecalho_da_camada.return_value = Mock()
    
    # Simulando um finalizador com o CRC recebido errado (0x99999999)
    unidade_mock.finalizador = Mock()
    unidade_mock.finalizador.octetos = struct.pack(">I", 0x99999999)
    
    # Importe a função 'sobe' da L2 ou passe a classe instanciada dependendo do seu design
    # Aqui chamaremos como se fosse uma função avulsa para fins do snippet
    nova_unidade, eventos = sobe(Mock(), unidade_mock, contexto={})
    
    # O quadro deve ser descartado (retorna None)
    assert nova_unidade is None
    assert eventos[0]["camada"] == "L2"
    assert eventos[0]["acao"] == "DESCARTA"
    assert "verificacao de erro inconsistente" in eventos[0]["mensagem"]

# ====================================================================
# TESTES DA TOPOLOGIA E ROTEAMENTO
# ====================================================================

JSON_TOPOLOGIA_SIMPLES = """
{
    "nome": "Rede Teste",
    "dispositivos": [
        {
            "nome": "PC1", "tipo": "computador", "gateway": "192.168.1.254",
            "interfaces": [{"nome": "eth0", "logico": "192.168.1.1", "fisico": "AA:BB:CC:DD:EE:01"}]
        },
        {
            "nome": "R1", "tipo": "roteador",
            "interfaces": [
                {"nome": "eth0", "logico": "192.168.1.254", "fisico": "AA:BB:CC:DD:EE:02"},
                {"nome": "eth1", "logico": "10.0.0.1", "fisico": "AA:BB:CC:DD:EE:03"}
            ]
        }
    ],
    "segmentos": [
        {
            "id": "LAN1", "prefixo": "192.168.1.0/24", "tipo": "lan", "custo": 0,
            "membros": [{"dispositivo": "PC1", "interface": "eth0"}, {"dispositivo": "R1", "interface": "eth0"}]
        }
    ]
}
"""

def test_topologia_carregamento_com_sucesso():
    # Enganamos o Python para achar que o arquivo de topologia tem nosso JSON mockado
    with patch("builtins.open", mock_open(read_data=JSON_TOPOLOGIA_SIMPLES)):
        topologia = Topologia("fake.json")
        
        assert topologia.nome == "Rede Teste"
        assert len(topologia.dispositivos) == 2
        assert "PC1" in topologia.dispositivos
        assert len(topologia.segmentos) == 1
        
        # Testa a resolução ARP interna (Física)
        segmento = topologia.segmento_por_id("LAN1")
        mac = topologia.resolver_fisico("192.168.1.254", segmento)
        assert mac == "AA:BB:CC:DD:EE:02"

def test_topologia_rota_padrao_computador():
    with patch("builtins.open", mock_open(read_data=JSON_TOPOLOGIA_SIMPLES)):
        topologia = Topologia("fake.json")
        
        tabela_pc1 = topologia.tabela_encaminhamento("PC1")
        # Deve ter a rota direta da LAN e a rota padrão (0.0.0.0/0)
        assert len(tabela_pc1) == 2
        rota_padrao = next(r for r in tabela_pc1 if r.destino_prefixo == "0.0.0.0/0")
        assert rota_padrao.proximo_salto == "192.168.1.254"
        assert rota_padrao.interface_saida == "eth0"

def test_topologia_falha_json_invalido():
    json_quebrado = "{ invalido: true }"
    with patch("builtins.open", mock_open(read_data=json_quebrado)):
        with pytest.raises(ErroTopologia) as excinfo:
            Topologia("fake.json")
        assert "JSON valido" in str(excinfo.value)