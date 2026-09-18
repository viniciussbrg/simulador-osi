from simulador.pdu import PDU, Mensagem, Segmento, Pacote, Quadro

class Camada:
    def __init__(self, dispositivo):
        self.dispositivo = dispositivo

class CamadaAplicacao(Camada):
    def descer(self, mensagem, ip_destino, p_origem, p_destino):
        self.dispositivo.motor.registrar(self.dispositivo.nome, 7, "GERA", f"processo navegador, destino {ip_destino}", len(mensagem))
        self.dispositivo.camadas[6].descer(PDU(mensagem, 0), ip_destino, p_origem, p_destino)
        
    def subir(self, pdu):
        self.dispositivo.motor.registrar(self.dispositivo.nome, 7, "RECEBE", "mensagem processada", pdu.tamanho)

class CamadaApresentacao(Camada):
    def descer(self, pdu, ip_destino, p_origem, p_destino):
        self.dispositivo.motor.registrar(self.dispositivo.nome, 6, "CODIFICA", "octetos UTF-8, conteúdo cifrado", pdu.tamanho)
        self.dispositivo.camadas[5].descer(pdu, ip_destino, p_origem, p_destino)

    def subir(self, pdu):
        self.dispositivo.motor.registrar(self.dispositivo.nome, 6, "DECODIFICA", "octetos decifrados", pdu.tamanho)
        self.dispositivo.camadas[7].subir(pdu.conteudo)

class CamadaSessao(Camada):
    def descer(self, pdu, ip_destino, p_origem, p_destino):
        msg = Mensagem(pdu)
        self.dispositivo.motor.registrar(self.dispositivo.nome, 5, "ABRE", "sessão estabelecida", msg.tamanho)
        self.dispositivo.camadas[4].descer(msg, ip_destino, p_origem, p_destino)

    def subir(self, pdu):
        self.dispositivo.motor.registrar(self.dispositivo.nome, 5, "MANTEM", "sessão mantida", pdu.tamanho)
        self.dispositivo.camadas[6].subir(pdu.conteudo)

class CamadaTransporte(Camada):
    def __init__(self, dispositivo):
        super().__init__(dispositivo)
        self.buffer_remontagem = {}

    def descer(self, pdu, ip_destino, p_origem, p_destino):
        tamanho_maximo = 40 
        dados_str = str(pdu.conteudo.conteudo) 
        partes = [dados_str[i:i+tamanho_maximo] for i in range(0, len(dados_str), tamanho_maximo)] if len(dados_str) > tamanho_maximo else [dados_str]

        for i, parte in enumerate(partes):
            segmento = Segmento(PDU(parte, pdu.tamanho - len(dados_str)), p_origem, p_destino, seq=i+1, total=len(partes))
            self.dispositivo.motor.registrar(self.dispositivo.nome, 4, "SEGMENTA", f"porta {p_origem}->{p_destino}, seg {segmento.seq} de {segmento.total}", segmento.tamanho)
            self.dispositivo.camadas[3].descer(segmento, ip_destino)

    def subir(self, segmento):
        self.dispositivo.motor.registrar(self.dispositivo.nome, 4, "REMONTA", f"recebeu segmento {segmento.seq}/{segmento.total}", segmento.tamanho)
        chave = (segmento.porta_origem, segmento.porta_destino)
        if chave not in self.buffer_remontagem: self.buffer_remontagem[chave] = []
        self.buffer_remontagem[chave].append(segmento)
        
        if len(self.buffer_remontagem[chave]) == segmento.total:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 4, "ENTREGA", "segmentos remontados", segmento.tamanho * segmento.total)
            self.dispositivo.camadas[5].subir(segmento.conteudo)
            del self.buffer_remontagem[chave]

class CamadaRede(Camada):
    def descer(self, segmento_ou_pacote, ip_destino=None):
        if isinstance(segmento_ou_pacote, Segmento):
            pacote = Pacote(segmento_ou_pacote, self.dispositivo.ip, ip_destino)
            self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ENCAPSULA", f"{pacote.ip_origem} -> {pacote.ip_destino}", pacote.tamanho)
        else:
            pacote = segmento_ou_pacote
            
        ip_alvo = pacote.ip_destino
        rede_destino = ip_alvo.rsplit('.', 1)[0] + '.0/24'
        
        if hasattr(self.dispositivo, 'rotas'):
            if rede_destino in self.dispositivo.rotas:
                rota = self.dispositivo.rotas[rede_destino]
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ROTEIA", f"rede {rede_destino} via {rota['prox_salto']}", pacote.tamanho)
                self.dispositivo.camadas[2].descer(pacote, rota['mac_prox'])
            else:
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "DESCARTA", "Destino inalcançável", pacote.tamanho)
        else:
            rede_origem = self.dispositivo.ip.rsplit('.', 1)[0] + '.0/24'
            if rede_origem == rede_destino:
                mac_prox = self.dispositivo.motor.obter_mac_por_ip(ip_alvo)
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ROTEIA", f"Entrega direta", pacote.tamanho)
            else:
                mac_prox = self.dispositivo.motor.obter_mac_por_ip(self.dispositivo.gateway)
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ROTEIA", f"Para gateway", pacote.tamanho)
            self.dispositivo.camadas[2].descer(pacote, mac_prox)

    def subir(self, pacote):
        if not hasattr(self.dispositivo, 'rotas') and pacote.ip_destino == self.dispositivo.ip:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "DESENCAPSULA", "Chegou ao destino", pacote.tamanho)
            self.dispositivo.camadas[4].subir(pacote.conteudo)
        else:
            self.descer(pacote) 

class CamadaEnlace(Camada):
    def descer(self, pacote, mac_destino):
        num_quadro = self.dispositivo.motor.obter_novo_id_quadro()
        quadro = Quadro(pacote, self.dispositivo.mac, mac_destino, num_quadro)
        self.dispositivo.motor.registrar(self.dispositivo.nome, 2, "ENQUADRA", f"{quadro.mac_origem} -> {quadro.mac_destino}, Q{quadro.id_quadro}", quadro.tamanho)
        self.dispositivo.camadas[1].descer(quadro)

    def subir(self, quadro):
        if not quadro.verificacao_erro:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 2, "DESCARTA", f"Erro CRC, Q{quadro.id_quadro} descartado", quadro.tamanho)
            return 
            
        if quadro.mac_destino == self.dispositivo.mac:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 2, "DESENQUADRA", f"Q{quadro.id_quadro} descartado, extraindo pacote", quadro.conteudo.tamanho)
            pacote = quadro.conteudo
            del quadro 
            self.dispositivo.camadas[3].subir(pacote)

class CamadaFisica(Camada):
    def descer(self, quadro):
        bits = quadro.tamanho * 8
        self.dispositivo.motor.octetos_transmitidos += quadro.tamanho
        destino = self.dispositivo.motor.obter_disp_por_mac(quadro.mac_destino)
        enlace = f"{self.dispositivo.nome}-{destino.nome}"
        self.dispositivo.motor.registrar(self.dispositivo.nome, 1, "TRANSMITE", f"{bits} bits no enlace {enlace}", quadro.tamanho)
        destino.camadas[1].subir(quadro, enlace)

    def subir(self, quadro, enlace):
        bits = quadro.tamanho * 8
        self.dispositivo.motor.registrar(self.dispositivo.nome, 1, "RECEBE", f"{bits} bits do enlace {enlace}", quadro.tamanho)
        self.dispositivo.camadas[2].subir(quadro)