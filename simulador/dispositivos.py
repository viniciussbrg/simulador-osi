from simulador.camadas import CamadaFisica, CamadaEnlace, CamadaRede, CamadaTransporte, CamadaSessao, CamadaApresentacao, CamadaAplicacao

class Dispositivo:
    def __init__(self, motor, nome, ip, mac):
        self.motor = motor
        self.nome = nome
        self.ip = ip
        self.mac = mac
        self.camadas = {}

class Computador(Dispositivo):
    def __init__(self, motor, nome, ip, mac, gateway):
        super().__init__(motor, nome, ip, mac)
        self.gateway = gateway
        self.macs = {"eth0": mac}
        self.camadas = {1: CamadaFisica(self), 2: CamadaEnlace(self), 3: CamadaRede(self), 4: CamadaTransporte(self), 5: CamadaSessao(self), 6: CamadaApresentacao(self), 7: CamadaAplicacao(self)}

class Roteador(Dispositivo):
    def __init__(self, motor, nome, interfaces, rotas):
        super().__init__(motor, nome, None, None)
        self.interfaces = interfaces
        self.macs = {nome_if: i["mac"] for nome_if, i in interfaces.items()}
        self.rotas = rotas
        self.camadas = {1: CamadaFisica(self), 2: CamadaEnlace(self), 3: CamadaRede(self)} 