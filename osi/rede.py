from dataclasses import dataclass
from pathlib import Path
from ipaddress import IPv4Address, IPv4Network
import heapq
import json
import math
import re
from .dispositivos import Computador, Interface, Roteador
from .pdu import Bits


@dataclass(frozen=True)
class SegmentoRede:
    nome: str
    tipo: str
    membros: tuple
    custo: int = 0
    prefixo: str | None = None


class Topologia:
    def __init__(self, caminho_json=None, *, dados=None):
        self.caminho = Path(caminho_json) if caminho_json else None
        if dados is None:
            dados = json.loads(self.caminho.read_text(encoding='utf-8-sig'))
        self.validar(dados)
        self.dados = dados
        self.nome = dados.get('nome', 'Topologia')
        self.redes_lan = dados['redes_lan']
        self.dispositivos = {}
        for item in dados['dispositivos']:
            interfaces = {n: Interface(n, i['ip'], i['mac'].upper(), i.get('rede'))
                          for n, i in item['interfaces'].items()}
            cls = Computador if item['tipo'] == 'host' else Roteador
            self.dispositivos[item['nome']] = cls(item['nome'], interfaces, item['posicao'])
        self.segmentos = {s['nome']: SegmentoRede(s['nome'], s['tipo'],
            tuple((m['dispositivo'], m['interface']) for m in s['membros']),
            s.get('custo', 0), s.get('prefixo')) for s in dados['segmentos']}

    @staticmethod
    def validar(d):
        try:
            if not isinstance(d, dict):
                raise ValueError('A raiz deve ser um objeto JSON.')
            if not 2 <= len(d['dispositivos']) <= 24:
                raise ValueError('Use de 2 a 24 dispositivos.')
            dispositivos, ips, macs = {}, set(), set()
            for dev in d['dispositivos']:
                nome = dev['nome']
                if not isinstance(nome, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,24}', nome):
                    raise ValueError('Nomes de dispositivo: letras, números, _ ou -, até 24 caracteres.')
                if nome in dispositivos or dev['tipo'] not in ('host', 'router'):
                    raise ValueError('Dispositivo duplicado ou tipo diferente de host/router.')
                dispositivos[nome] = dev
                if len(dev['posicao']) != 2 or not all(isinstance(n, (int, float))
                    and not isinstance(n, bool) and math.isfinite(n) and 0 <= n <= 2000
                    for n in dev['posicao']):
                    raise ValueError(f'Posição inválida em {nome}: use x,y de 0 a 2000.')
                if not dev['interfaces'] or (dev['tipo'] == 'host' and len(dev['interfaces']) != 1):
                    raise ValueError('Cada host utiliza uma interface; roteadores, uma ou mais.')
                for iface, info in dev['interfaces'].items():
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,20}', iface):
                        raise ValueError('Nome de interface inválido.')
                    ip = str(IPv4Address(info['ip']))
                    mac = info['mac'].upper()
                    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', mac):
                        raise ValueError(f'MAC inválido em {nome}/{iface}.')
                    if ip in ips or mac in macs:
                        raise ValueError('IPs e MACs devem ser únicos na topologia.')
                    ips.add(ip); macs.add(mac)
            redes, prefixos = {}, []
            for rede in d['redes_lan']:
                net = IPv4Network(rede['prefixo'])
                if any(net.overlaps(other) for other in prefixos):
                    raise ValueError('Prefixos LAN sobrepostos.')
                prefixos.append(net)
                if rede['nome'] in redes:
                    raise ValueError('Nome de LAN duplicado.')
                redes[rede['nome']] = rede
                if dispositivos[rede['roteador']]['tipo'] != 'router':
                    raise ValueError('Gateway da LAN deve ser um roteador.')
            ocupadas, pares, seg_nomes, lans = set(), set(), set(), set()
            for seg in d['segmentos']:
                if seg['nome'] in seg_nomes or seg['tipo'] not in ('lan', 'p2p'):
                    raise ValueError('Segmento duplicado ou tipo inválido.')
                seg_nomes.add(seg['nome'])
                custo = seg.get('custo', 0)
                if isinstance(custo, bool) or not isinstance(custo, int) or not 0 <= custo <= 100000:
                    raise ValueError('Custo deve ser inteiro de 0 a 100000.')
                membros = seg['membros']
                if len(membros) < 2 or (seg['tipo'] == 'p2p' and len(membros) != 2):
                    raise ValueError('LAN exige ao menos dois membros; p2p exige dois.')
                nomes = [m['dispositivo'] for m in membros]
                if len(set(nomes)) != len(nomes):
                    raise ValueError('Dispositivo repetido no segmento.')
                for i, a in enumerate(nomes):
                    for b in nomes[i+1:]:
                        par = tuple(sorted((a, b)))
                        if par in pares:
                            raise ValueError('Enlaces paralelos entre o mesmo par não são suportados.')
                        pares.add(par)
                for m in membros:
                    key = (m['dispositivo'], m['interface'])
                    info = dispositivos[key[0]]['interfaces'][key[1]]
                    if key in ocupadas:
                        raise ValueError('Uma interface não pode participar de dois segmentos.')
                    ocupadas.add(key)
                    if seg['tipo'] == 'p2p' and dispositivos[key[0]]['tipo'] != 'router':
                        raise ValueError('Segmentos p2p conectam somente roteadores.')
                    if seg['tipo'] == 'lan':
                        net = IPv4Network(seg['prefixo'])
                        ip = IPv4Address(info['ip'])
                        if ip not in net or ip in (net.network_address, net.broadcast_address):
                            raise ValueError('Endereço de interface fora da LAN ou reservado.')
                        rede = redes[info['rede']]
                        if rede['prefixo'] != seg['prefixo'] or rede['roteador'] not in nomes:
                            raise ValueError('LAN, prefixo e gateway inconsistentes.')
                if seg['tipo'] == 'lan':
                    if seg['prefixo'] in lans:
                        raise ValueError('Cada prefixo LAN deve ter um único segmento.')
                    lans.add(seg['prefixo'])
                    if sum(dispositivos[n]['tipo'] == 'router' for n in nomes) != 1:
                        raise ValueError('Cada LAN deve ter exatamente um gateway.')
                elif any(dispositivos[m['dispositivo']]['interfaces'][m['interface']].get('rede')
                         for m in membros):
                    raise ValueError('Interface p2p não deve declarar rede LAN.')
            todas = {(n, i) for n, dev in dispositivos.items() for i in dev['interfaces']}
            if ocupadas != todas or lans != {r['prefixo'] for r in redes.values()}:
                raise ValueError('Toda interface e toda LAN devem participar de um segmento.')
            if sum(dev['tipo'] == 'host' for dev in dispositivos.values()) < 2:
                raise ValueError('A topologia precisa de pelo menos dois computadores.')
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f'Estrutura JSON incompleta ou inválida: {exc}') from exc

    @property
    def hosts(self):
        return {n: d for n, d in self.dispositivos.items() if isinstance(d, Computador)}

    @property
    def roteadores(self):
        return {n: d for n, d in self.dispositivos.items() if isinstance(d, Roteador)}

    def interface(self, dispositivo, nome_if):
        return self.dispositivos[dispositivo].interfaces[nome_if]

    def ip_host(self, nome):
        return next(iter(self.hosts[nome].interfaces.values())).ip

    def host_por_ip(self, ip):
        return next((n for n in self.hosts if self.ip_host(n) == ip), None)

    def rede_do_ip(self, ip):
        return next((r for r in self.redes_lan if IPv4Address(ip) in IPv4Network(r['prefixo'])), None)

    def rede_do_host(self, host):
        return self.rede_do_ip(self.ip_host(host))

    def segmento_entre(self, a, b):
        return next((s for s in self.segmentos.values()
                     if {a, b} <= {n for n, _ in s.membros}), None)

    def interfaces_entre(self, a, b):
        s = self.segmento_entre(a, b)
        if s is None:
            raise ValueError(f'Não há enlace entre {a} e {b}.')
        mapa = dict(s.membros)
        return self.interface(a, mapa[a]), self.interface(b, mapa[b]), s

    def menor_caminho_roteadores(self, origem, destino, links_inativos=()):
        g = {n: [] for n in self.roteadores}
        for s in self.segmentos.values():
            if s.tipo == 'p2p' and s.nome not in links_inativos:
                a, b = [n for n, _ in s.membros]
                g[a].append((b, s.custo)); g[b].append((a, s.custo))
        fila, vistos = [(0, (origem,))], set()
        while fila:
            custo, caminho = heapq.heappop(fila)
            atual = caminho[-1]
            if atual in vistos:
                continue
            vistos.add(atual)
            if atual == destino:
                return list(caminho), custo
            for vizinho, peso in sorted(g[atual]):
                if vizinho not in vistos:
                    heapq.heappush(fila, (custo + peso, caminho + (vizinho,)))
        raise ValueError(f'Sem caminho entre {origem} e {destino}.')

    def _rota_prefixo(self, roteador, rede, inativos):
        gateway = rede['roteador']
        if gateway == roteador:
            for s in self.segmentos.values():
                if s.tipo == 'lan' and s.prefixo == rede['prefixo'] and s.nome not in inativos:
                    return {'proximo': 'conectada', 'custo': 0,
                            'interface': dict(s.membros)[roteador], 'segmento': s.nome}
            return None
        try:
            caminho, custo = self.menor_caminho_roteadores(roteador, gateway, inativos)
        except ValueError:
            return None
        saida, chegada, seg = self.interfaces_entre(roteador, caminho[1])
        return {'proximo': caminho[1], 'custo': custo, 'interface': saida.nome,
                'segmento': seg.nome, 'ip_proximo': chegada.ip}

    def decisao_rota(self, dispositivo, destino_ip, links_inativos=()):
        destino = self.host_por_ip(destino_ip)
        rede = self.rede_do_ip(destino_ip)
        if dispositivo in self.hosts:
            origem = self.rede_do_host(dispositivo)
            direto = rede is not None and rede['nome'] == origem['nome']
            proximo = destino if direto else origem['roteador']
            if proximo is None or proximo == dispositivo:
                return None
            custo = 0
        else:
            if rede is None:
                return None
            row = self._rota_prefixo(dispositivo, rede, links_inativos)
            if row is None:
                return None
            direto = row['proximo'] == 'conectada'
            proximo = destino if direto else row['proximo']
            custo = row['custo']
            if proximo is None:
                return None
        saida, chegada, seg = self.interfaces_entre(dispositivo, proximo)
        if seg.nome in links_inativos:
            return None
        return {'proximo': proximo, 'ip_proximo': chegada.ip, 'custo': custo,
                'interface': saida.nome, 'segmento': seg.nome, 'direta': direto,
                'prefixo': rede['prefixo'] if rede else '0.0.0.0/0'}

    def tabelas_encaminhamento(self, links_inativos=()):
        linhas = []
        for router in sorted(self.roteadores):
            for rede in self.redes_lan:
                row = self._rota_prefixo(router, rede, links_inativos)
                linhas.append({'roteador': router, 'prefixo': rede['prefixo'],
                               **(row or {'proximo': 'sem rota', 'custo': None,
                                          'interface': '-', 'segmento': '-'})})
        return linhas

    @staticmethod
    def transmitir(bits, injetar_erro=False):
        if not injetar_erro:
            return Bits(bits.sequencia)
        sequencia = bits.sequencia
        indice = 14 * 8  # primeiro bit da carga, depois dos 14 B de cabeçalho L2
        return Bits(sequencia[:indice] + ('0' if sequencia[indice] == '1' else '1')
                    + sequencia[indice+1:])

    def modelo_visual(self):
        return {'nome': self.nome, 'redes_lan': self.redes_lan,
                'dispositivos': self.dados['dispositivos'], 'segmentos': self.dados['segmentos'],
                'tabelas': self.tabelas_encaminhamento()}
