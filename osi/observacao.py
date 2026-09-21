from ipaddress import IPv4Address
import struct
import zlib


def detalhar_cabecalhos(raw, blocos):
    if not isinstance(raw, bytes):
        return []
    detalhes, offset = [], 0
    for bloco, tamanho in blocos:
        trecho = raw[offset:offset+tamanho]
        campos = []
        nota = ''

        def campo(nome, inicio, quantidade, valor):
            campos.append({'nome': nome, 'inicio': offset+inicio,
                           'bytes': quantidade, 'valor': str(valor)})

        if len(trecho) != tamanho:
            break
        if bloco == 'H2' and tamanho == 14:
            mac = lambda data: ':'.join(f'{b:02X}' for b in data)
            campo('MAC de destino', 0, 6, mac(trecho[:6]))
            campo('MAC de origem', 6, 6, mac(trecho[6:12]))
            campo('Tipo', 12, 2, f'0x{int.from_bytes(trecho[12:14], "big"):04X}')
            nota = 'Enlace: destino antes da origem. Os MACs identificam as interfaces deste salto.'
        elif bloco == 'H3' and tamanho == 20:
            f = struct.unpack('!BBHHHBBH4s4s', trecho)
            campo('Versão / IHL', 0, 1, f'{f[0] >> 4} / {f[0] & 15}')
            campo('Tipo de serviço', 1, 1, f[1])
            campo('Comprimento total', 2, 2, f[2])
            campo('Identificador do pacote', 4, 2, f'P{f[3]}')
            campo('Flags / fragmentação IP', 6, 2, f[4])
            campo('TTL fixo', 8, 1, f[5])
            campo('Protocolo (valor didático)', 9, 1, f[6])
            campo('Checksum IP não modelado', 10, 2, f[7])
            campo('IP de origem', 12, 4, IPv4Address(f[8]))
            campo('IP de destino', 16, 4, IPv4Address(f[9]))
            nota = 'Cabeçalho IPv4 didático: IP de origem antes do destino. TTL e checksum não são simulados integralmente.'
        elif bloco == 'H4' and tamanho == 8:
            f = struct.unpack('!HHHH', trecho)
            for i, nome in enumerate(('Porta de origem', 'Porta de destino', 'Sequência', 'Total de segmentos')):
                campo(nome, i*2, 2, f[i])
            nota = 'Transporte: porta de origem antes do destino. O formato de 8 B é próprio do simulador.'
        elif bloco == 'H5' and tamanho == 4:
            campo('Identificador de sessão', 0, 4, f'S-{int.from_bytes(trecho, "big"):04d}')
            nota = 'H5 é inserido uma vez por mensagem, antes da segmentação, e removido em L5 após a remontagem.'
        elif bloco == 'F2' and tamanho == 4:
            recebido = int.from_bytes(trecho, 'big')
            calculado = zlib.crc32(raw[:offset]) & 0xffffffff
            campo('CRC32 transportado', 0, 4, f'0x{recebido:08X}')
            nota = (f'F2 corresponde a T2 na aula. CRC calculado: 0x{calculado:08X}; '
                    + ('válido.' if recebido == calculado else 'INVÁLIDO: difere do transportado.'))
        if campos:
            detalhes.append({'bloco': bloco, 'tamanho': tamanho,
                             'campos': campos, 'nota': nota})
        offset += tamanho
    return detalhes


def resumir_quadros(eventos):
    resumo = []
    for e in eventos:
        if e.acao != 'TRANSMITE':
            continue
        dados = sum(tamanho for nome, tamanho in e.blocos if nome == 'DADOS')
        resumo.append({'quadro': e.quadro_id, 'enlace': list(e.enlace_ativo),
                       'fluxo': e.fluxo, 'dados': dados,
                       'controle': e.tamanho-dados, 'total': e.tamanho,
                       'eficiencia': dados/e.tamanho if e.tamanho else 0})
    return resumo
