from dataclasses import asdict, dataclass, field
from ipaddress import IPv4Address
from .camadas import CamadaTransporte
from .observacao import detalhar_cabecalhos, resumir_quadros


@dataclass
class Evento:
    passo: int
    dispositivo: str
    camada: int
    acao: str
    descricao: str
    tamanho: int
    pdu: str
    blocos: list
    ip_origem: str
    ip_destino: str
    mac_origem: str = ''
    mac_destino: str = ''
    rota: list = field(default_factory=list)
    enlace_ativo: list = field(default_factory=list)
    fluxo: str = ''
    pacote_id: str = ''
    quadro_id: str = ''
    previa: str = ''
    processo_origem: str = ''
    processo_destino: str = ''
    porta_origem: int = 0
    porta_destino: int = 0
    cabecalhos: list = field(default_factory=list)

    def linha_log(self):
        descricao = self.descricao.replace('\r', r'\r').replace('\n', r'\n').replace('|', r'\u007c')
        return (f'{self.passo:03d} | {self.dispositivo} | L{self.camada} | '
                f'{self.acao} | {descricao} [{self.fluxo}] {self.tamanho} B')


@dataclass
class Metricas:
    dados_uteis: int = 0
    transmitidos: int = 0
    quadros: int = 0
    pacotes: int = 0
    segmentos: int = 0
    mensagens_entregues: int = 0
    dados_entregues: int = 0
    mensagens_total: int = 0

    @property
    def entregue(self):
        return self.mensagens_entregues == self.mensagens_total

    @property
    def eficiencia(self):
        return self.dados_uteis / self.transmitidos if self.transmitidos else 0

    @property
    def sobrecarga(self):
        return 1 - self.eficiencia if self.transmitidos else 0


@dataclass
class ResultadoSimulacao:
    caso: str
    titulo: str
    eventos: list
    metricas: Metricas
    rotas: list
    custos: list
    dispositivos_envolvidos: list
    tabelas: list
    links_inativos: list
    entregas: list
    cargas: list

    def to_dict(self):
        d = asdict(self)
        quadros = resumir_quadros(self.eventos)
        dados_quadros = sum(q['dados'] for q in quadros)
        controle = sum(q['controle'] for q in quadros)
        d['metricas'].update(eficiencia=self.metricas.eficiencia,
                            eficiencia_global=self.metricas.eficiencia,
                            sobrecarga=self.metricas.sobrecarga, entregue=self.metricas.entregue,
                            dados_nos_quadros=dados_quadros, controle_transmitido=controle,
                            eficiencia_quadros=dados_quadros/self.metricas.transmitidos if self.metricas.transmitidos else 0)
        d['quadros_detalhados'] = quadros
        for item, evento in zip(d['eventos'], self.eventos):
            item['linha'] = evento.linha_log()
        d['log'] = '\n'.join(e.linha_log() for e in self.eventos)
        d['comparacao'] = {'eta_e1': 42 / 92, 'eta_e2': 42 / 368}
        return d


class Simulador:
    MENSAGEM_PADRAO = 'GET /index.html HTTP/1.1 Host: servidorWeb'
    CASOS = {'E1': 'Entrega direta', 'E2': 'Entrega indireta',
             'E3': 'Demultiplexação', 'E4': 'Falha de enlace',
             'E5': 'Destino inalcançável', 'E6': 'Erro de transmissão',
             'E7': 'Mensagem longa', 'PERSONALIZADO': 'Comunicação personalizada'}

    def __init__(self, topologia):
        self.topologia = topologia

    def configuracao(self, caso):
        caso = self.normalizar_caso(caso)
        hosts = list(self.topologia.hosts)
        base = {'origem': hosts[0], 'destino': hosts[-1], 'mensagem': self.MENSAGEM_PADRAO,
                'porta_origem': 5210, 'porta_destino': 443,
                'processo_origem': 'navegador', 'processo_destino': 'servidorWeb',
                'limite': 64, 'links_inativos': [], 'enlace_erro': '', 'ordem_inversa': False}
        cenarios = self.topologia.dados.get('cenarios', {})
        if caso != 'PERSONALIZADO' and caso not in cenarios:
            raise ValueError('Esta topologia não define esse cenário. Selecione Personalizado.')
        base.update(cenarios.get(caso, {}))
        return base

    @classmethod
    def normalizar_caso(cls, caso):
        if len(caso) == 2 and caso.startswith('C'):
            caso = 'E' + caso[1]
        if caso not in cls.CASOS:
            raise ValueError('Cenário inválido.')
        return caso

    def _validar_config(self, cfg):
        if cfg['origem'] not in self.topologia.hosts:
            raise ValueError('Escolha um computador de origem válido.')
        dest = cfg['destino']
        dest_ip = self.topologia.ip_host(dest) if dest in self.topologia.hosts else str(IPv4Address(dest))
        if dest_ip == self.topologia.ip_host(cfg['origem']):
            raise ValueError('Origem e destino devem ser computadores distintos.')
        cfg['destino_ip'] = dest_ip
        for key in ('porta_origem', 'porta_destino'):
            if isinstance(cfg[key], bool) or not isinstance(cfg[key], int) or not 1 <= cfg[key] <= 65535:
                raise ValueError('Portas devem ser inteiros de 1 a 65535.')
        if isinstance(cfg['limite'], bool) or not isinstance(cfg['limite'], int) or not 4 <= cfg['limite'] <= 1400:
            raise ValueError('Limite L4 deve ser inteiro de 4 a 1400 B.')
        if not isinstance(cfg['mensagem'], str) or not 1 <= len(cfg['mensagem'].encode('utf-8')) <= 4096:
            raise ValueError('A mensagem deve conter de 1 a 4096 bytes em UTF-8.')
        for key in ('processo_origem', 'processo_destino'):
            if not isinstance(cfg[key], str) or not cfg[key].strip() or len(cfg[key]) > 60:
                raise ValueError('Informe os processos, com até 60 caracteres.')
        if not isinstance(cfg['links_inativos'], list):
            raise ValueError('Lista de enlaces inativos inválida.')
        for link in cfg['links_inativos'] + ([cfg['enlace_erro']] if cfg['enlace_erro'] else []):
            if link not in self.topologia.segmentos:
                raise ValueError(f'Enlace inexistente: {link}')
        return cfg

    def simular(self, caso='E2', configuracao=None):
        caso = self.normalizar_caso(caso)
        cfg = self.configuracao(caso)
        permitidos = set(cfg) | {'origem2', 'porta_origem2'}
        if configuracao:
            if set(configuracao) - permitidos:
                raise ValueError('Parâmetro de simulação desconhecido.')
            cfg.update(configuracao)
        configs = [self._validar_config(dict(cfg))]
        if caso == 'E3':
            c2 = dict(cfg, origem=cfg['origem2'], porta_origem=cfg['porta_origem2'])
            configs.append(self._validar_config(c2))
            if (c2['origem'], c2['porta_origem']) == (cfg['origem'], cfg['porta_origem']):
                raise ValueError('E3 exige dois fluxos distintos.')
        self.metricas = Metricas(mensagens_total=len(configs))
        self._quadro, self._pacote, self._erro_injetado = 0, 0, False
        self.entregas, self.cargas, self.rotas, self.custos = [], [], [], []
        for h in self.topologia.hosts.values():
            h.camadas[4].buffers.clear()
            h.camadas[5].ativas.clear()
        geradores = [self._fluxo(c, n) for n, c in enumerate(configs, 1)]
        eventos = []
        while geradores:
            ativos = []
            for gerador in geradores:
                try:
                    ev = next(gerador)
                    ev.passo = len(eventos) + 1
                    eventos.append(ev)
                    ativos.append(gerador)
                except StopIteration:
                    pass
            geradores = ativos
        for h in self.topologia.hosts.values():
            h.camadas[4].buffers.clear()
        envolvidos = list(dict.fromkeys(e.dispositivo for e in eventos))

        return ResultadoSimulacao(
            caso, self.CASOS[caso], eventos, self.metricas,
            self.rotas, self.custos, envolvidos,
            self.topologia.tabelas_encaminhamento(cfg['links_inativos']),
            cfg['links_inativos'], self.entregas, self.cargas
        )

    def _fluxo(self, cfg, sid):
        top = self.topologia
        origem, destino_ip = cfg['origem'], cfg['destino_ip']
        ip_origem = top.ip_host(origem)
        fonte = top.hosts[origem]
        fluxo = f'{ip_origem}:{cfg["porta_origem"]} -> {destino_ip}:{cfg["porta_destino"]}'
        rota, custo, sucesso = [origem], 0, False
        qid, pid, macs, enlace = '', '', ('', ''), []
        def evento(dev, n, r, raw, unidade, blocos, *, detalhe=''):
            tamanho = len(raw.encode('utf-8')) if isinstance(raw, str) else len(raw)
            previa = raw[:64] if isinstance(raw, str) else raw[:64].hex(' ')
            return Evento(0, dev, n, r.acao, r.descricao + detalhe, tamanho, unidade,
                list(blocos), ip_origem, destino_ip, *macs, list(rota), list(enlace),
                fluxo, pid, qid, previa,
                processo_origem=cfg['processo_origem'], processo_destino=cfg['processo_destino'],
                porta_origem=cfg['porta_origem'], porta_destino=cfg['porta_destino'],
                cabecalhos=detalhar_cabecalhos(raw, blocos))
        def registro(dev, n, acao, desc, raw, unidade, blocos):
            from .camadas import ResultadoCamada
            return evento(dev, n, ResultadoCamada(None, acao, desc), raw, unidade, blocos)

        n = len(cfg['mensagem'].encode('utf-8'))
        self.metricas.dados_uteis += n
        r7 = fonte.camadas[7].descendo(cfg['mensagem'], cfg['processo_origem'], cfg['processo_destino'])
        yield evento(origem, 7, r7, r7.valor, 'Mensagem', [('DADOS', n)])
        r6 = fonte.camadas[6].descendo(r7.valor)
        yield evento(origem, 6, r6, r6.valor, 'Mensagem cifrada', [('DADOS', n)])
        r5 = fonte.camadas[5].descendo(r6.valor, sid)
        yield evento(origem, 5, r5, r5.valor, 'Mensagem de sessão', [('H5', 4), ('DADOS', n)])
        fonte.camadas[4].limite_payload = cfg['limite']
        r4 = fonte.camadas[4].descendo(r5.valor, cfg['porta_origem'], cfg['porta_destino'])
        segmentos = r4.valor
        self.metricas.segmentos += len(segmentos)
        self.cargas.append([len(s.payload) for s in segmentos])
        offsets, off = {}, 0
        for s in segmentos:
            offsets[s.sequencia] = off
            off += len(s.payload)
        if cfg['ordem_inversa']:
            segmentos = list(reversed(segmentos))
        for seg in segmentos:
            inner = [('H5', 4), ('DADOS', len(seg.payload) - 4)] if offsets[seg.sequencia] == 0 else [('DADOS', len(seg.payload))]
            inner = [(label, size) for label, size in inner if size]
            sb = [('H4', 8)] + inner
            rota, custo = [origem], 0
            qid, pid, macs, enlace = '', '', ('', ''), []
            yield registro(origem, 4, 'SEGMENTA',
                f'porta {seg.porta_origem} -> {seg.porta_destino}, segmento {seg.sequencia}/{seg.total}; '
                f'carga {len(seg.payload)} B, limite {cfg["limite"]} B', seg.to_bytes(), 'Segmento', sb)
            self._pacote += 1
            r3 = fonte.camadas[3].descendo(seg.to_bytes(), ip_origem, destino_ip, self._pacote)
            pacote = r3.valor
            pid = f'P{pacote.identificador}'
            self.metricas.pacotes += 1
            pb = [('H3', 20)] + sb
            yield evento(origem, 3, r3, pacote.to_bytes(), 'Pacote', pb)
            atual, interrompido = origem, False
            while True:
                dev = top.dispositivos[atual]
                rr = dev.camadas[3].encaminhar(pacote, top, atual, cfg['links_inativos'])
                yield evento(atual, 3, rr, pacote.to_bytes(), 'Pacote', pb)
                if rr.valor is None:
                    interrompido = True
                    break
                proximo = rr.valor['proximo']
                a, b, link = top.interfaces_entre(atual, proximo)
                macs, enlace = (a.mac, b.mac), [atual, proximo]
                self._quadro += 1
                qid = f'Q{self._quadro}'
                rq = dev.camadas[2].descendo(pacote.to_bytes(), a.mac, b.mac)
                qb = [('H2', 14)] + pb + [('F2', 4)]
                yield evento(atual, 2, rq, rq.valor, 'Quadro', qb, detalhe=f'; novo {qid}, contém {pid}')
                rb = dev.camadas[1].descendo(rq.valor)
                erro = cfg['enlace_erro'] == link.nome and not self._erro_injetado
                bits = top.transmitir(rb.valor, erro)
                self._erro_injetado |= erro
                self.metricas.transmitidos += bits.tamanho
                self.metricas.quadros += 1
                rota.append(proximo)
                custo += link.custo if link.tipo == 'p2p' else 0
                raw_observado = int(bits.sequencia, 2).to_bytes(bits.tamanho, 'big') if erro else rq.valor
                tx = evento(atual, 1, rb, raw_observado, 'Bits', qb,
                    detalhe=f' no enlace {atual}-{proximo}; {qid}' + ('; 1 bit alterado' if erro else ''))
                tx.previa = bits.sequencia[:128]
                yield tx
                recv = top.dispositivos[proximo]
                r1 = recv.camadas[1].subindo(bits)
                rx = evento(proximo, 1, r1, r1.valor, 'Bits', qb, detalhe=f'; {qid}')
                rx.previa = bits.sequencia[:128]
                yield rx
                r2 = recv.camadas[2].subindo(r1.valor, b.mac)
                if r2.valor is None:
                    yield evento(proximo, 2, r2, r1.valor, 'Quadro descartado', qb, detalhe=f'; {qid}')
                    interrompido = True
                    break
                yield evento(proximo, 2, r2, r2.valor, 'Pacote', pb, detalhe=f'; {qid}')
                final = proximo in top.hosts
                recebido = recv.camadas[3].subindo(r2.valor, destino_final=final)
                if not final:
                    pacote = recebido.valor
                    atual = proximo
                    continue
                yield evento(proximo, 3, recebido, recebido.valor, 'Segmento', sb)
                transporte = recv.camadas[4].subindo(recebido.valor, ip_origem, destino_ip)
                seg_recebido, chave, remontada = transporte.valor
                yield evento(proximo, 4, transporte, seg_recebido.payload, 'Carga recebida', inner)
                if remontada is not None:
                    yield registro(proximo, 4, 'REMONTA',
                        f'{seg_recebido.total} segmento(s) ordenados e remontados; libera mensagem à L5',
                        remontada, 'Mensagem remontada', [('H5', 4), ('DADOS', len(remontada)-4)])
                    sessao = recv.camadas[5].manter(remontada)
                    yield evento(proximo, 5, sessao, remontada, 'Mensagem de sessão', [('H5', 4), ('DADOS', n)])
                    sessao = recv.camadas[5].subindo(remontada)
                    yield evento(proximo, 5, sessao, sessao.valor, 'Mensagem cifrada', [('DADOS', n)])
                    apresentacao = recv.camadas[6].subindo(sessao.valor)
                    yield evento(proximo, 6, apresentacao, apresentacao.valor, 'Mensagem', [('DADOS', n)])
                    aplicacao = recv.camadas[7].subindo(apresentacao.valor, cfg['processo_destino'])
                    yield evento(proximo, 7, aplicacao, aplicacao.valor, 'Mensagem', [('DADOS', n)])
                    sucesso = True
                    self.metricas.mensagens_entregues += 1
                    self.metricas.dados_entregues += len(aplicacao.valor.encode('utf-8'))
                    self.entregas.append({'fluxo': fluxo, 'texto': aplicacao.valor,
                                          'destino': proximo, 'processo': cfg['processo_destino']})
                break
            if interrompido:
                break
        self.rotas.append(list(rota)); self.custos.append(custo)
        fim = fonte.camadas[5].encerrar(sid, sucesso)
        yield evento(origem, 5, fim, b'', 'Controle local', [],
                     detalhe='; evento local do experimento, sem bytes adicionais no enlace')
