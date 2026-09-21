import zlib

class PDU:
    def __init__(self, conteudo, tamanho_cabecalho=0):
        self.conteudo = conteudo
        if isinstance(conteudo, PDU):
            tamanho = conteudo.tamanho
        elif isinstance(conteudo, bytes):
            tamanho = len(conteudo)
        else:
            tamanho = len(str(conteudo).encode("utf-8"))
        self.tamanho = tamanho + tamanho_cabecalho

class Mensagem(PDU):
    def __init__(self, dados, sessao):
        super().__init__(f"{sessao:04d}".encode() + dados)
        self.sessao = sessao

class Segmento(PDU):
    def __init__(self, mensagem, p_origem, p_destino, seq=1, total=1):
        super().__init__(mensagem, 8) 
        self.porta_origem = p_origem
        self.porta_destino = p_destino
        self.seq = seq
        self.total = total

class Pacote(PDU):
    def __init__(self, segmento, ip_origem, ip_destino):
        super().__init__(segmento, 20) 
        self.ip_origem = ip_origem
        self.ip_destino = ip_destino

class Quadro(PDU):
    def __init__(self, pacote, mac_origem, mac_destino, id_quadro):
        super().__init__(pacote, 18) # 14 header + 4 trailer
        self.mac_origem = mac_origem
        self.mac_destino = mac_destino
        self.id_quadro = id_quadro
        self.fcs = zlib.crc32(self.para_bytes())
        self.bits = ""

    def para_bytes(self):
        return f"{self.mac_destino}{self.mac_origem}Q{self.id_quadro}{self.tamanho}".encode()