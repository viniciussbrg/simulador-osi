# -*- coding: utf-8 -*-
"""Unidade de dados de protocolo (PDU) e cabecalhos.

Cada cabecalho e uma sequencia real de octetos, com o tamanho definido em
config.py. O tamanho mostrado na tela e o comprimento efetivo, e o CRC da
camada 2 e calculado sobre esses octetos.

Os cabecalhos ficam na ordem em que aparecem no enlace:

    [ L2 | L3 | L4 | L5 | dados | finalizador L2 ]
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

from . import config

# Conversoes de endereco


def ip_para_octetos(ip: str) -> bytes:
    """Converte "10.0.1.10" em quatro octetos."""
    partes = ip.strip().split(".")
    if len(partes) != 4:
        raise ValueError(f"endereco logico invalido: {ip!r}")
    valores = []
    for parte in partes:
        if not parte.isdigit():
            raise ValueError(f"endereco logico invalido: {ip!r}")
        valor = int(parte)
        if not 0 <= valor <= 255:
            raise ValueError(f"endereco logico invalido: {ip!r}")
        valores.append(valor)
    return bytes(valores)


def ip_valido(ip: str) -> bool:
    """Informa se o texto e um endereco logico bem formado."""
    try:
        ip_para_octetos(ip)
    except ValueError:
        return False
    return True


def octetos_para_ip(octetos: bytes) -> str:
    """Converte quatro octetos em "10.0.1.10"."""
    return ".".join(str(o) for o in octetos)


def mac_para_octetos(mac: str) -> bytes:
    """Converte "AA:00:00:00:01:0A" em seis octetos."""
    partes = mac.strip().split(":")
    if len(partes) != 6:
        raise ValueError(f"endereco fisico invalido: {mac!r}")
    return bytes(int(parte, 16) for parte in partes)


def octetos_para_mac(octetos: bytes) -> str:
    """Converte seis octetos em "AA:00:00:00:01:0A"."""
    return ":".join(f"{o:02X}" for o in octetos)


def mac_curto(mac: str) -> str:
    """Forma abreviada usada no registro de eventos: "AA:...:01:0A"."""
    partes = mac.split(":")
    if len(partes) != 6:
        return mac
    return f"{partes[0]}:...:{partes[4]}:{partes[5]}"


def endereco_de_rede(ip: str, prefixo_bits: int) -> str:
    """Aplica a mascara e devolve o endereco de rede de `ip`."""
    valor = int.from_bytes(ip_para_octetos(ip), "big")
    mascara = (0xFFFFFFFF << (32 - prefixo_bits)) & 0xFFFFFFFF
    return octetos_para_ip((valor & mascara).to_bytes(4, "big"))


def pertence_ao_prefixo(ip: str, prefixo: str) -> bool:
    """Informa se `ip` pertence ao prefixo CIDR "10.0.1.0/24"."""
    rede, _, bits = prefixo.partition("/")
    if not bits:
        return False
    try:
        return endereco_de_rede(ip, int(bits)) == endereco_de_rede(rede, int(bits))
    except ValueError:
        return False


def bits_do_prefixo(prefixo: str) -> int:
    """Devolve o comprimento em bits de um prefixo CIDR; -1 se malformado."""
    _, _, bits = prefixo.partition("/")
    return int(bits) if bits.isdigit() else -1


# Cabecalho


@dataclass
class Cabecalho:
    """Um cabecalho (ou finalizador) acrescentado por uma camada."""

    camada: int               # 2 a 5
    nome: str                 # rotulo mostrado na figura da unidade
    octetos: bytes            # conteudo real; len(octetos) e o tamanho
    campos: dict[str, Any] = field(default_factory=dict)
    finalizador: bool = False

    def __len__(self) -> int:
        return len(self.octetos)

    def descricao_campos(self) -> str:
        return ", ".join(f"{chave}={valor}" for chave, valor in self.campos.items())


# Construtores de cabecalho, um por camada


def cabecalho_sessao(identificador: str) -> Cabecalho:
    """Cabecalho de sessao: quatro octetos com o numero da sessao em ASCII.

    O identificador "S-0001" e gravado como os quatro octetos "0001". Isso
    permite que a camada 5 do destino recupere o numero da sessao a partir dos
    octetos recebidos, sem depender de nenhum campo auxiliar.
    """
    numero = identificador.replace(config.PREFIXO_SESSAO, "")
    octetos = numero.encode("ascii")[: config.TAMANHO_CABECALHO_SESSAO]
    octetos = octetos.rjust(config.TAMANHO_CABECALHO_SESSAO, b"0")
    return Cabecalho(5, "L5", octetos, {"sessao": identificador})


def sessao_do_cabecalho(cabecalho: Cabecalho) -> str:
    """Le o identificador de sessao gravado nos octetos do cabecalho L5."""
    return config.PREFIXO_SESSAO + cabecalho.octetos.decode("ascii", errors="replace")


def cabecalho_transporte(porta_origem: int, porta_destino: int,
                         numero: int, total: int) -> Cabecalho:
    """Cabecalho de transporte: portas, numero do segmento e total de segmentos.

    As portas sao o endereco de processo a processo: sao elas que a camada 4
    do destino usa para demultiplexar fluxos concorrentes (cenario E3).
    """
    octetos = struct.pack(">HHHH", porta_origem, porta_destino, numero, total)
    assert len(octetos) == config.TAMANHO_CABECALHO_TRANSPORTE
    return Cabecalho(4, "L4", octetos, {
        "porta_origem": porta_origem,
        "porta_destino": porta_destino,
        "segmento": f"{numero} de {total}",
    })


def cabecalho_rede(origem: str, destino: str, identificacao: int,
                   comprimento: int) -> Cabecalho:
    """Cabecalho de rede: par de enderecos logicos, identificacao e TTL.

    O par de enderecos logicos entra aqui uma unica vez, na origem, e nao e
    reescrito em nenhum salto (restricao R3 do enunciado).
    """
    octetos = struct.pack(
        ">BBHHHBBH4s4s",
        config.VERSAO_IHL,            # 1 octeto
        0,                            # 1 octeto: tipo de servico
        comprimento,                  # 2 octetos: comprimento total
        identificacao,                # 2 octetos: identificacao do pacote
        0,                            # 2 octetos: sinalizadores e deslocamento
        config.TTL_INICIAL,           # 1 octeto
        config.PROTOCOLO_TRANSPORTE,  # 1 octeto
        0,                            # 2 octetos: verificacao do cabecalho
        ip_para_octetos(origem),      # 4 octetos
        ip_para_octetos(destino),     # 4 octetos
    )
    assert len(octetos) == config.TAMANHO_CABECALHO_REDE
    return Cabecalho(3, "L3", octetos, {
        "logico_origem": origem,
        "logico_destino": destino,
        "identificacao": identificacao,
        "ttl": config.TTL_INICIAL,
    })


def cabecalho_enlace(fisico_origem: str, fisico_destino: str) -> Cabecalho:
    """Cabecalho de enlace: par de enderecos fisicos do salto corrente."""
    octetos = (mac_para_octetos(fisico_destino)
               + mac_para_octetos(fisico_origem)
               + struct.pack(">H", config.TIPO_PROTOCOLO_ENLACE))
    assert len(octetos) == config.TAMANHO_CABECALHO_ENLACE
    return Cabecalho(2, "L2", octetos, {
        "fisico_origem": fisico_origem,
        "fisico_destino": fisico_destino,
    })


def calcular_verificacao(conteudo: bytes) -> int:
    """Verificacao de erro da camada 2: CRC-32 sobre cabecalho e carga."""
    return zlib.crc32(conteudo) & 0xFFFFFFFF


def finalizador_enlace(conteudo: bytes) -> Cabecalho:
    """Finalizador de enlace: verificacao de erro de quatro octetos.

    Qualquer bit alterado durante o transporte muda o resultado do calculo
    refeito pelo receptor, que entao descarta o quadro.
    """
    soma = calcular_verificacao(conteudo)
    octetos = struct.pack(">I", soma)
    assert len(octetos) == config.TAMANHO_FINALIZADOR_ENLACE
    return Cabecalho(2, "FCS", octetos, {"verificacao": f"0x{soma:08X}"},
                     finalizador=True)


# Unidade de dados


@dataclass
class UnidadeDados:
    """A unidade de dados que atravessa a pilha.

    O mesmo objeto muda de nome conforme a camada em que se encontra:
    mensagem (7 a 5), segmento (4), pacote (3), quadro (2) e bits (1).
    Os campos descritivos existem para o registro de eventos e para a
    interface; nenhuma camada le um campo que nao lhe pertence.
    """

    dados: bytes                                   # carga util deste nivel
    unidade: str = "Mensagem"                      # nome da unidade corrente
    cabecalhos: list[Cabecalho] = field(default_factory=list)
    finalizador: Cabecalho | None = None

    logicos: tuple[str, str] | None = None         # par de enderecos logicos
    fisicos: tuple[str, str] | None = None         # par de enderecos fisicos
    portas: tuple[int, int] | None = None          # par de portas
    processos: tuple[str, str] | None = None       # par de processos
    sessao: str | None = None
    pacote: str | None = None                      # rotulo P1, P2, ...
    quadro: str | None = None                      # rotulo Q1, Q2, ...
    numero_segmento: int = 1
    total_segmentos: int = 1
    fluxo: str = "A"                               # identifica o fluxo no E3
    texto_original: str | None = None              # so existe nos extremos
    metadados: dict[str, Any] = field(default_factory=dict)

    # medidas
    def tamanho(self) -> int:
        """Tamanho corrente em octetos: cabecalhos + dados + finalizador."""
        total = len(self.dados) + sum(len(c) for c in self.cabecalhos)
        if self.finalizador is not None:
            total += len(self.finalizador)
        return total

    def tamanho_bits(self) -> int:
        return self.tamanho() * config.BITS_POR_OCTETO

    def serializar(self) -> bytes:
        """Concatena tudo na ordem em que os octetos viajam pelo enlace."""
        partes = [c.octetos for c in self.cabecalhos]
        partes.append(self.dados)
        if self.finalizador is not None:
            partes.append(self.finalizador.octetos)
        return b"".join(partes)

    def conteudo_protegido(self) -> bytes:
        """Octetos cobertos pela verificacao de erro: tudo menos o finalizador."""
        return b"".join(c.octetos for c in self.cabecalhos) + self.dados

    # manipulacao de cabecalhos
    def com_cabecalho(self, cabecalho: Cabecalho) -> "UnidadeDados":
        """Devolve uma copia com `cabecalho` acrescentado a esquerda."""
        nova = self.copia()
        nova.cabecalhos.insert(0, cabecalho)
        return nova

    def cabecalho_da_camada(self, camada: int) -> Cabecalho | None:
        """Devolve o cabecalho inserido pela camada indicada, se presente."""
        for cabecalho in self.cabecalhos:
            if cabecalho.camada == camada and not cabecalho.finalizador:
                return cabecalho
        return None

    def sem_cabecalho(self, camada: int) -> tuple[Cabecalho | None, "UnidadeDados"]:
        """Remove e devolve o cabecalho da camada indicada."""
        nova = self.copia()
        for indice, cabecalho in enumerate(nova.cabecalhos):
            if cabecalho.camada == camada and not cabecalho.finalizador:
                return nova.cabecalhos.pop(indice), nova
        return None, nova

    def copia(self) -> "UnidadeDados":
        """Copia rasa segura: listas e dicionarios sao duplicados."""
        return UnidadeDados(
            dados=self.dados,
            unidade=self.unidade,
            cabecalhos=list(self.cabecalhos),
            finalizador=self.finalizador,
            logicos=self.logicos,
            fisicos=self.fisicos,
            portas=self.portas,
            processos=self.processos,
            sessao=self.sessao,
            pacote=self.pacote,
            quadro=self.quadro,
            numero_segmento=self.numero_segmento,
            total_segmentos=self.total_segmentos,
            fluxo=self.fluxo,
            texto_original=self.texto_original,
            metadados=dict(self.metadados),
        )

    # desenho
    def blocos(self) -> list[dict[str, Any]]:
        """Descreve a unidade como blocos, para o requisito V3.

        Devolve uma lista de dicionarios com rotulo, tamanho, camada e tipo.
        A interface apenas le essa lista; nao precisa conhecer a PDU nem
        chamar metodo algum das camadas.
        """
        desenho: list[dict[str, Any]] = []
        for cabecalho in self.cabecalhos:
            desenho.append({
                "rotulo": cabecalho.nome,
                "tamanho": len(cabecalho),
                "camada": cabecalho.camada,
                "tipo": "cabecalho",
                "detalhe": cabecalho.descricao_campos(),
            })
        desenho.append({
            "rotulo": "DADOS",
            "tamanho": len(self.dados),
            "camada": 7,
            "tipo": "dados",
            "detalhe": f"{len(self.dados)} octetos de carga util",
        })
        if self.finalizador is not None:
            desenho.append({
                "rotulo": self.finalizador.nome,
                "tamanho": len(self.finalizador),
                "camada": self.finalizador.camada,
                "tipo": "finalizador",
                "detalhe": self.finalizador.descricao_campos(),
            })
        return desenho

    def __repr__(self) -> str:   # pragma: no cover - auxilio de depuracao
        return (f"UnidadeDados({self.unidade}, {self.tamanho()} B, "
                f"cabecalhos={[c.nome for c in self.cabecalhos]})")
