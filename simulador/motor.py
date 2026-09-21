import ipaddress
from simulador.dispositivos import Computador, Roteador
from simulador.rede import LeitorTopologia, calcular_rotas

MENSAGEM_PADRAO = "GET /index.html HTTP/1.1 Host: servidorWeb"
MENSAGEM_LONGA = "Mensagem longa de H1 para H4: a camada 4 divide os dados em tres segmentos e o destino remonta tudo."
PROCESSOS = {443: "servidorWeb", 5210: "navegador", 6120: "navegador"}

class MotorSimulacao:
    def __init__(self):
        self.passo = 1
        self.eventos = []
        self.dispositivos = {}
        self.topologia = {}
        self.contador_quadros = 1
        self.contador_sessoes = 0
        self.octetos_transmitidos = 0
        self.octetos_dados = 0
        self.enlace_com_erro = None
        self.enlaces_caidos = []
        self.carregar_dados()

    def carregar_dados(self, enlaces_caidos=()):
        self.dispositivos.clear()
        dados = LeitorTopologia.carregar()
        self.topologia = dados
        rotas = calcular_rotas(dados, enlaces_caidos)
        for nome, i in dados["computadores"].items():
            self.dispositivos[nome] = Computador(self, nome, i["ip"], i["mac"], i["gateway"])
        for nome, i in dados["roteadores"].items():
            self.dispositivos[nome] = Roteador(self, nome, i["interfaces"], rotas[nome])

    def registrar(self, dispositivo, camada, acao, descricao, tamanho):
        linha = f"{self.passo:03d} | {dispositivo} | L{camada} | {acao} | {descricao}"
        self.eventos.append(f"{linha:<80} {tamanho:>4} B")
        self.passo += 1

    def obter_novo_id_quadro(self):
        id_atual = self.contador_quadros
        self.contador_quadros += 1
        return id_atual

    def nova_sessao(self):
        self.contador_sessoes += 1
        return self.contador_sessoes

    def nome_processo(self, porta):
        return PROCESSOS.get(porta, f"porta {porta}")

    def rede_do_ip(self, ip):
        for rede in self.topologia["redes"]:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(rede):
                return rede
        return None

    def obter_disp_por_mac(self, mac):
        return next((d for d in self.dispositivos.values() if mac in d.macs.values()), None)

    def obter_mac_por_ip(self, ip):
        for d in self.dispositivos.values():
            if isinstance(d, Computador) and d.ip == ip:
                return d.mac
            if isinstance(d, Roteador):
                for interface in d.interfaces.values():
                    if interface["ip"] == ip:
                        return interface["mac"]
        return None

    def reiniciar(self, enlaces_caidos=()):
        self.enlaces_caidos = list(enlaces_caidos)
        self.eventos.clear()
        self.passo = 1
        self.contador_quadros = 1
        self.contador_sessoes = 0
        self.octetos_transmitidos = 0
        self.octetos_dados = 0
        self.enlace_com_erro = None
        self.carregar_dados(enlaces_caidos)

    def simular_cenario(self, cenario):
        self.reiniciar(["R1-R4"] if "C4" in cenario else [])

        if "C1" in cenario:
            self.iniciar_transmissao("H1", "10.0.1.11", 5210, 443, MENSAGEM_PADRAO)
        elif "C2" in cenario:
            self.iniciar_transmissao("H1", "10.0.3.10", 5210, 443, MENSAGEM_PADRAO)
        elif "C3" in cenario:
            self.iniciar_transmissao("H1", "10.0.3.10", 5210, 443, MENSAGEM_PADRAO)
            self.iniciar_transmissao("H2", "10.0.3.10", 6120, 443, MENSAGEM_PADRAO)
        elif "C4" in cenario:
            self.eventos.append("--- | SISTEMA | -- | AVISO | Enlace R1-R4 caiu! Rotas recalculadas pelo menor custo.")
            self.iniciar_transmissao("H1", "10.0.3.10", 5210, 443, MENSAGEM_PADRAO)
        elif "C5" in cenario:
            self.iniciar_transmissao("H1", "10.0.9.10", 5210, 443, MENSAGEM_PADRAO)
        elif "C6" in cenario:
            self.enlace_com_erro = "R4-R3"
            self.eventos.append("--- | SISTEMA | -- | AVISO | Erro de bit ativado no enlace R4-R3.")
            self.iniciar_transmissao("H1", "10.0.3.10", 5210, 443, MENSAGEM_PADRAO)
        elif "C7" in cenario:
            self.iniciar_transmissao("H1", "10.0.3.10", 5210, 443, MENSAGEM_LONGA)

        return self.finalizar()

    def finalizar(self):
        eficiencia = (self.octetos_dados / self.octetos_transmitidos) * 100 if self.octetos_transmitidos > 0 else 0
        quadros = self.contador_quadros - 1
        self.eventos.append(f"--- | SISTEMA | -- | RESULTADO | Dados entregues: {self.octetos_dados} B, Quadros: {quadros}, Transmitidos: {self.octetos_transmitidos} B, Eficiência: {eficiencia:.1f}%, Sobrecarga: {100 - eficiencia:.1f}%")
        return eficiencia

    def iniciar_transmissao(self, origem_nome, destino_ip, p_origem, p_destino, texto):
        origem = self.dispositivos[origem_nome]
        origem.camadas[7].descer(texto, destino_ip, p_origem, p_destino)
