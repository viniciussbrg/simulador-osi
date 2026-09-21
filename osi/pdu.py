from dataclasses import dataclass
from ipaddress import IPv4Address
import struct
import zlib


@dataclass(frozen=True)
class Segmento:
    porta_origem: int
    porta_destino: int
    sequencia: int
    total: int
    payload: bytes
    HEADER_SIZE = 8

    def to_bytes(self):
        return struct.pack('!HHHH', self.porta_origem, self.porta_destino,
                           self.sequencia, self.total) + self.payload

    @classmethod
    def from_bytes(cls, raw):
        if len(raw) < cls.HEADER_SIZE:
            raise ValueError('Segmento truncado: cabeçalho L4 exige 8 B.')
        p1, p2, seq, total = struct.unpack('!HHHH', raw[:8])
        if not (1 <= p1 <= 65535 and 1 <= p2 <= 65535 and 1 <= seq <= total):
            raise ValueError('Portas ou numeração de segmentos inválidas.')
        return cls(p1, p2, seq, total, raw[8:])


@dataclass(frozen=True)
class Pacote:
    ip_origem: str
    ip_destino: str
    payload: bytes
    identificador: int
    HEADER_SIZE = 20

    def to_bytes(self):
        tamanho = self.HEADER_SIZE + len(self.payload)
        return struct.pack('!BBHHHBBH4s4s', 0x45, 0, tamanho,
                           self.identificador, 0, 64, 17, 0,
                           IPv4Address(self.ip_origem).packed,
                           IPv4Address(self.ip_destino).packed) + self.payload

    @classmethod
    def from_bytes(cls, raw):
        if len(raw) < cls.HEADER_SIZE or raw[0] != 0x45:
            raise ValueError('Cabeçalho lógico inválido ou truncado.')
        fields = struct.unpack('!BBHHHBBH4s4s', raw[:20])
        if fields[2] != len(raw):
            raise ValueError('Comprimento do pacote difere do cabeçalho L3.')
        return cls(str(IPv4Address(fields[-2])), str(IPv4Address(fields[-1])),
                   raw[20:], fields[3])


@dataclass(frozen=True)
class Quadro:
    mac_origem: str
    mac_destino: str
    payload: bytes
    HEADER_SIZE = 14
    TRAILER_SIZE = 4

    def to_bytes(self):
        mac = lambda text: bytes(int(p, 16) for p in text.split(':'))
        corpo = mac(self.mac_destino) + mac(self.mac_origem) + b'\x08\x00' + self.payload
        return corpo + struct.pack('!I', zlib.crc32(corpo) & 0xffffffff)

    @classmethod
    def from_bytes(cls, raw):
        if len(raw) < 18:
            raise ValueError('Quadro truncado.')
        if zlib.crc32(raw[:-4]) & 0xffffffff != struct.unpack('!I', raw[-4:])[0]:
            raise ValueError('CRC inválido')
        if raw[12:14] != b'\x08\x00':
            raise ValueError('Tipo de quadro não suportado.')
        mac = lambda data: ':'.join(f'{b:02X}' for b in data)
        return cls(mac(raw[6:12]), mac(raw[:6]), raw[14:-4])


@dataclass(frozen=True)
class Bits:
    sequencia: str

    @property
    def tamanho(self):
        return len(self.sequencia) // 8
