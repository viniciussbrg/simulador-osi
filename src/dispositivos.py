class Dispositivo:
    def __init__(self, nome, interfaces):
        self.nome = nome
        self.interfaces = interfaces

class Computador(Dispositivo):
    tipo = "host"

class Roteador(Dispositivo):
    tipo = "roteador"
