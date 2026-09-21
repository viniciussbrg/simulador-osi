import zlib
from simulador.pdu import PDU, Mensagem, Segmento, Pacote, Quadro

CHAVE_CIFRA = 42
LIMITE_SEGMENTO = 40
LIMIAR_SEGMENTACAO = 64

def abreviar_mac(mac):
    partes = mac.split(":")
    return f"{partes[0]}:...:{partes[-2]}:{partes[-1]}"

class Camada:
    def __init__(self, dispositivo):
        self.dispositivo = dispositivo

class CamadaAplicacao(Camada):
    def descer(self, mensagem, ip_destino, p_origem, p_destino):
        motor = self.dispositivo.motor
        self.dispositivo.motor.registrar(self.dispositivo.nome, 7, "GERA", f"processo {motor.nome_processo(p_origem)}, destino {motor.nome_processo(p_destino)}", len(mensagem.encode("utf-8")))
        self.dispositivo.camadas[6].descer(PDU(mensagem, 0), ip_destino, p_origem, p_destino)

    def subir(self, pdu, p_destino):
        self.dispositivo.motor.octetos_dados += pdu.tamanho
        self.dispositivo.motor.registrar(self.dispositivo.nome, 7, "ENTREGA", f"processo {self.dispositivo.motor.nome_processo(p_destino)} recebeu a mensagem", pdu.tamanho)

class CamadaApresentacao(Camada):
    def descer(self, pdu, ip_destino, p_origem, p_destino):
        cifrado = bytes(b ^ CHAVE_CIFRA for b in pdu.conteudo.encode("utf-8"))
        pdu = PDU(cifrado)
        self.dispositivo.motor.registrar(self.dispositivo.nome, 6, "CODIFICA", "octetos UTF-8, conteúdo cifrado", pdu.tamanho)
        self.dispositivo.camadas[5].descer(pdu, ip_destino, p_origem, p_destino)

    def subir(self, pdu, p_destino):
        texto = bytes(b ^ CHAVE_CIFRA for b in pdu.conteudo).decode("utf-8", errors="replace")
        pdu = PDU(texto)
        self.dispositivo.motor.registrar(self.dispositivo.nome, 6, "DECODIFICA", "conteúdo decifrado, octetos UTF-8", pdu.tamanho)
        self.dispositivo.camadas[7].subir(pdu, p_destino)

class CamadaSessao(Camada):
    def descer(self, pdu, ip_destino, p_origem, p_destino):
        msg = Mensagem(pdu.conteudo, self.dispositivo.motor.nova_sessao())
        self.dispositivo.motor.registrar(self.dispositivo.nome, 5, "ABRE", f"sessão S-{msg.sessao:04d} estabelecida", msg.tamanho)
        self.dispositivo.camadas[4].descer(msg, ip_destino, p_origem, p_destino)

    def subir(self, dados, p_destino):
        sessao = int(dados[:4])
        pdu = PDU(dados[4:])
        self.dispositivo.motor.registrar(self.dispositivo.nome, 5, "MANTEM", f"sessão S-{sessao:04d} mantida", pdu.tamanho)
        self.dispositivo.camadas[6].subir(pdu, p_destino)
        self.dispositivo.motor.registrar(self.dispositivo.nome, 5, "ENCERRA", f"sessão S-{sessao:04d} encerrada", pdu.tamanho)

class CamadaTransporte(Camada):
    def __init__(self, dispositivo):
        super().__init__(dispositivo)
        self.buffer_remontagem = {}

    def descer(self, pdu, ip_destino, p_origem, p_destino):
        dados = pdu.conteudo
        if len(dados) > LIMIAR_SEGMENTACAO:
            partes = [dados[i:i+LIMITE_SEGMENTO] for i in range(0, len(dados), LIMITE_SEGMENTO)]
        else:
            partes = [dados]

        for i, parte in enumerate(partes):
            segmento = Segmento(PDU(parte), p_origem, p_destino, seq=i+1, total=len(partes))
            self.dispositivo.motor.registrar(self.dispositivo.nome, 4, "SEGMENTA", f"porta {p_origem} → {p_destino}, segmento {segmento.seq} de {segmento.total}", segmento.tamanho)
            self.dispositivo.camadas[3].descer(segmento, ip_destino)

    def subir(self, segmento):
        if segmento.total == 1:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 4, "DEMULTIPLEXA", f"porta {segmento.porta_origem} → {segmento.porta_destino}, entregue à sessão", segmento.conteudo.tamanho)
            self.dispositivo.camadas[5].subir(segmento.conteudo.conteudo, segmento.porta_destino)
            return

        chave = (segmento.porta_origem, segmento.porta_destino)
        if chave not in self.buffer_remontagem: self.buffer_remontagem[chave] = []
        self.buffer_remontagem[chave].append(segmento)
        self.dispositivo.motor.registrar(self.dispositivo.nome, 4, "RECEBE", f"segmento {segmento.seq} de {segmento.total}, aguardando remontagem", segmento.tamanho)

        if len(self.buffer_remontagem[chave]) == segmento.total:
            recebidos = sorted(self.buffer_remontagem[chave], key=lambda s: s.seq)
            dados = b"".join(s.conteudo.conteudo for s in recebidos)
            del self.buffer_remontagem[chave]
            self.dispositivo.motor.registrar(self.dispositivo.nome, 4, "REMONTA", f"{segmento.total} segmentos remontados em ordem, porta {segmento.porta_origem} → {segmento.porta_destino}", len(dados))
            self.dispositivo.camadas[5].subir(dados, segmento.porta_destino)

class CamadaRede(Camada):
    def descer(self, segmento_ou_pacote, ip_destino=None):
        if isinstance(segmento_ou_pacote, Segmento):
            pacote = Pacote(segmento_ou_pacote, self.dispositivo.ip, ip_destino)
            self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ENCAPSULA", f"{pacote.ip_origem} → {pacote.ip_destino}", pacote.tamanho)
        else:
            pacote = segmento_ou_pacote

        ip_alvo = pacote.ip_destino
        rede_destino = self.dispositivo.motor.rede_do_ip(ip_alvo)

        if hasattr(self.dispositivo, 'rotas'):
            if rede_destino in self.dispositivo.rotas:
                rota = self.dispositivo.rotas[rede_destino]
                if rota["prox_salto"] is None:
                    ip_prox = ip_alvo
                    descricao = f"{rede_destino} entrega direta, interface {rota['interface']}"
                else:
                    ip_prox = rota["ip_prox"]
                    descricao = f"{rede_destino} via {rota['prox_salto']}, custo {rota['custo']}, interface {rota['interface']}"
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ROTEIA", descricao, pacote.tamanho)
                self.dispositivo.camadas[2].descer(pacote, rota["interface"], ip_prox)
            else:
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "DESCARTA", f"sem rota para {ip_alvo}, pacote descartado", pacote.tamanho)
        else:
            if rede_destino == self.dispositivo.motor.rede_do_ip(self.dispositivo.ip):
                ip_prox = ip_alvo
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ROTEIA", f"entrega direta a {ip_alvo} pela interface eth0", pacote.tamanho)
            else:
                ip_prox = self.dispositivo.gateway
                self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "ROTEIA", f"próximo salto {ip_prox} pela interface eth0", pacote.tamanho)
            self.dispositivo.camadas[2].descer(pacote, "eth0", ip_prox)

    def subir(self, pacote):
        if hasattr(self.dispositivo, 'rotas'):
            self.descer(pacote)
        elif pacote.ip_destino == self.dispositivo.ip:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 3, "DESENCAPSULA", f"{pacote.ip_origem} → {pacote.ip_destino}, chegou ao destino", pacote.conteudo.tamanho)
            self.dispositivo.camadas[4].subir(pacote.conteudo)

class CamadaEnlace(Camada):
    def descer(self, pacote, interface, ip_prox):
        mac_destino = self.dispositivo.motor.obter_mac_por_ip(ip_prox)
        if mac_destino is None:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 2, "DESCARTA", f"endereço físico de {ip_prox} desconhecido, pacote descartado", pacote.tamanho)
            return
        num_quadro = self.dispositivo.motor.obter_novo_id_quadro()
        quadro = Quadro(pacote, self.dispositivo.macs[interface], mac_destino, num_quadro)
        self.dispositivo.motor.registrar(self.dispositivo.nome, 2, "ENQUADRA", f"{abreviar_mac(quadro.mac_origem)} → {abreviar_mac(quadro.mac_destino)}, quadro Q{quadro.id_quadro}", quadro.tamanho)
        self.dispositivo.camadas[1].descer(quadro)

    def subir(self, quadro):
        recebido = bytes(int(quadro.bits[i:i+8], 2) for i in range(0, len(quadro.bits), 8))
        if zlib.crc32(recebido) != quadro.fcs:
            self.dispositivo.motor.registrar(self.dispositivo.nome, 2, "DESCARTA", f"verificação de erro falhou, quadro Q{quadro.id_quadro} descartado", quadro.tamanho)
            return

        if quadro.mac_destino in self.dispositivo.macs.values():
            self.dispositivo.motor.registrar(self.dispositivo.nome, 2, "DESENQUADRA", f"verificação de erro correta, quadro Q{quadro.id_quadro} descartado", quadro.conteudo.tamanho)
            pacote = quadro.conteudo
            del quadro
            self.dispositivo.camadas[3].subir(pacote)

class CamadaFisica(Camada):
    def descer(self, quadro):
        bits = quadro.tamanho * 8
        quadro.bits = "".join(format(b, "08b") for b in quadro.para_bytes())
        self.dispositivo.motor.octetos_transmitidos += quadro.tamanho
        destino = self.dispositivo.motor.obter_disp_por_mac(quadro.mac_destino)
        enlace = f"{self.dispositivo.nome}-{destino.nome}"
        self.dispositivo.motor.registrar(self.dispositivo.nome, 1, "TRANSMITE", f"{bits} bits no enlace {enlace}", quadro.tamanho)
        if self.dispositivo.motor.enlace_com_erro in (enlace, f"{destino.nome}-{self.dispositivo.nome}"):
            meio = len(quadro.bits) // 2
            bit_trocado = "1" if quadro.bits[meio] == "0" else "0"
            quadro.bits = quadro.bits[:meio] + bit_trocado + quadro.bits[meio+1:]
        destino.camadas[1].subir(quadro, enlace)

    def subir(self, quadro, enlace):
        bits = quadro.tamanho * 8
        self.dispositivo.motor.registrar(self.dispositivo.nome, 1, "RECEBE", f"{bits} bits do enlace {enlace}", quadro.tamanho)
        self.dispositivo.camadas[2].subir(quadro)
