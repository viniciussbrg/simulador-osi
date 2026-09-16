from dataclasses import dataclass
from .pdu import Bits, Pacote, Quadro, Segmento


@dataclass(frozen=True)
class ResultadoCamada:
    valor: object
    acao: str
    descricao: str


class CamadaAplicacao:
    numero, nome = 7, 'Aplicação'

    def descendo(self, texto, processo_origem, processo_destino):
        return ResultadoCamada(texto, 'GERA',
            f'processo {processo_origem}, destino {processo_destino}')

    def subindo(self, texto, processo_destino):
        return ResultadoCamada(texto, 'ENTREGA',
            f'mensagem entregue ao processo {processo_destino}: {texto!r}')


class CamadaApresentacao:
    numero, nome = 6, 'Apresentação'

    def __init__(self, chave=0x5A):
        self.chave = chave

    def _xor(self, dados):
        return bytes(b ^ self.chave for b in dados)

    def descendo(self, texto):
        return ResultadoCamada(self._xor(texto.encode('utf-8')), 'CODIFICA',
            'codificação UTF-8; cifra XOR didática, chave 0x5A')

    def subindo(self, dados):
        return ResultadoCamada(self._xor(dados).decode('utf-8'), 'DECODIFICA',
            'conteúdo decifrado e convertido de UTF-8 em texto no destino')


class CamadaSessao:
    numero, nome, HEADER_SIZE = 5, 'Sessão', 4

    def __init__(self):
        self.ativas = set()

    def descendo(self, dados, numero_sessao):
        self.ativas.add(numero_sessao)
        return ResultadoCamada(numero_sessao.to_bytes(4, 'big') + dados,
            'ABRE', f'sessão S-{numero_sessao:04d} estabelecida')

    def manter(self, dados):
        if len(dados) < 4:
            raise ValueError('Cabeçalho de sessão truncado.')
        sid = int.from_bytes(dados[:4], 'big')
        self.ativas.add(sid)
        return ResultadoCamada(dados, 'MANTEM', f'diálogo S-{sid:04d} ativo')

    def encerrar(self, sid, sucesso=True):
        self.ativas.discard(sid)
        estado = 'concluído' if sucesso else 'abortado, sem retransmissão'
        return ResultadoCamada(None, 'ENCERRA', f'sessão S-{sid:04d} encerrada ({estado})')

    def subindo(self, dados):
        self.manter(dados)
        sid = int.from_bytes(dados[:4], 'big')
        self.ativas.discard(sid)
        return ResultadoCamada(dados[4:], 'ENCERRA',
            f'sessão S-{sid:04d} recebida e encerrada; H5 removido')


class CamadaTransporte:
    numero, nome, HEADER_SIZE = 4, 'Transporte', 8

    def __init__(self, limite_payload=64):
        self.limite_payload = limite_payload
        self.buffers = {}

    def descendo(self, dados, porta_origem, porta_destino):
        if not 4 <= self.limite_payload <= 1400:
            raise ValueError('Limite L4 deve estar entre 4 e 1400 B.')
        if not all(1 <= p <= 65535 for p in (porta_origem, porta_destino)):
            raise ValueError('Portas devem estar entre 1 e 65535.')
        partes = [dados[i:i+self.limite_payload]
                  for i in range(0, len(dados), self.limite_payload)] or [b'']
        segmentos = [Segmento(porta_origem, porta_destino, i, len(partes), p)
                     for i, p in enumerate(partes, 1)]
        return ResultadoCamada(segmentos, 'SEGMENTA', f'{len(segmentos)} segmentos')

    def subindo(self, raw, ip_origem, ip_destino):
        seg = Segmento.from_bytes(raw)
        chave = (ip_origem, seg.porta_origem, ip_destino, seg.porta_destino)
        total, partes = self.buffers.setdefault(chave, (seg.total, {}))
        if total != seg.total:
            raise ValueError('Total de segmentos inconsistente no mesmo fluxo.')
        if seg.sequencia in partes and partes[seg.sequencia] != seg.payload:
            raise ValueError('Segmento duplicado com conteúdo diferente.')
        partes[seg.sequencia] = seg.payload
        completo = set(partes) == set(range(1, total + 1))
        mensagem = b''.join(partes[n] for n in range(1, total + 1)) if completo else None
        if completo:
            del self.buffers[chave]
        return ResultadoCamada((seg, chave, mensagem), 'DEMULTIPLEXA',
            f'fluxo {ip_origem}:{seg.porta_origem} -> {ip_destino}:{seg.porta_destino}; '
            f'segmento {seg.sequencia}/{total}, {len(seg.payload)} B de carga; '
            f'{len(partes)}/{total} recebido(s)')


class CamadaRede:
    numero, nome, HEADER_SIZE = 3, 'Rede', 20

    def descendo(self, dados, ip_origem, ip_destino, identificador):
        return ResultadoCamada(Pacote(ip_origem, ip_destino, dados, identificador),
            'ENCAPSULA', f'{ip_origem} -> {ip_destino}, pacote P{identificador}')

    def subindo(self, raw, destino_final=False):
        pacote = Pacote.from_bytes(raw)
        return ResultadoCamada(pacote.payload if destino_final else pacote,
            'DECAPSULA' if destino_final else 'RECEBE',
            f'P{pacote.identificador}; {pacote.ip_origem} -> {pacote.ip_destino}'
            + ('; H3 removido no destino' if destino_final else '; payload opaco'))

    def encaminhar(self, pacote, topologia, dispositivo, links_inativos=()):
        decisao = topologia.decisao_rota(dispositivo, pacote.ip_destino, links_inativos)
        if decisao is None:
            return ResultadoCamada(None, 'DESCARTA',
                f'nenhuma rota/vizinho alcançável para {pacote.ip_destino}; '
                f'pacote P{pacote.identificador} descartado')
        return ResultadoCamada(decisao, 'ROTEIA',
            f'{decisao["prefixo"]} via {decisao["proximo"]} '
            f'({decisao["ip_proximo"]}), custo {decisao["custo"]}, '
            f'interface {decisao["interface"]}'
            + ('; entrega direta' if decisao['direta'] else ''))


class CamadaEnlace:
    numero, nome, HEADER_SIZE, TRAILER_SIZE = 2, 'Enlace', 14, 4

    def descendo(self, dados, mac_origem, mac_destino):
        raw = Quadro(mac_origem, mac_destino, dados).to_bytes()
        return ResultadoCamada(raw, 'ENQUADRA',
            f'{mac_origem} -> {mac_destino}; H2=14 B e F2/CRC32=4 B')

    def subindo(self, raw, mac_receptor):
        try:
            quadro = Quadro.from_bytes(raw)
            if quadro.mac_destino != mac_receptor:
                raise ValueError('Endereço físico diferente do receptor')
        except ValueError as exc:
            return ResultadoCamada(None, 'DESCARTA', f'{exc}; quadro descartado')
        return ResultadoCamada(quadro.payload, 'DESENQUADRA',
            'verificação de erro correta; quadro descartado, H2 e F2 removidos')


class CamadaFisica:
    numero, nome = 1, 'Física'

    def descendo(self, raw):
        bits = Bits(''.join(f'{octeto:08b}' for octeto in raw))
        return ResultadoCamada(bits, 'TRANSMITE', f'{len(bits.sequencia)} bits')

    def subindo(self, bits):
        if len(bits.sequencia) % 8 or set(bits.sequencia) - {'0', '1'}:
            raise ValueError('Sequência de bits inválida.')
        raw = bytes(int(bits.sequencia[i:i+8], 2)
                    for i in range(0, len(bits.sequencia), 8))
        return ResultadoCamada(raw, 'RECEBE', f'{len(bits.sequencia)} bits recebidos')
