from copy import deepcopy

TAM_C5 = 4
TAM_C4 = 8
TAM_C3 = 20
TAM_C2 = 14
TAM_F2 = 4

class PDU:
    def __init__(self, mensagem, destino_nome, processo_origem=5210, processo_destino=443):
        self.dados = mensagem if isinstance(mensagem, bytes) else mensagem.encode("utf-8")
        self.destino_nome = destino_nome
        self.origem_nome = None
        self.processo_origem = processo_origem
        self.processo_destino = processo_destino
        self.codificacao = "UTF-8"
        self.cifrado = False
        self.sessao_id = None
        self.portas = None
        self.logicos = None
        self.fisicos = None
        self.quadro_id = None
        self.verificacao = None
        self.segmento_indice = 1
        self.segmento_total = 1
        self.unidade = "mensagem"
        self.proximo_dispositivo = None
        self.iface_saida = None
        self.iface_entrada = None
        self.cabecalhos = []
        self.tem_trailer_l2 = False

    def clonar_para_segmento(self, fatia, indice, total):
        novo = deepcopy(self)
        novo.dados = fatia
        novo.segmento_indice = indice
        novo.segmento_total = total
        novo.unidade = "segmento"
        novo.cabecalhos = [c for c in self.cabecalhos if c[0] == "L5"]
        novo.tem_trailer_l2 = False
        novo.fisicos = None
        novo.quadro_id = None
        return novo

    def adicionar_cabecalho(self, nome, tamanho):
        if not any(c[0] == nome for c in self.cabecalhos):
            self.cabecalhos.append((nome, tamanho))

    def remover_cabecalho(self, nome):
        self.cabecalhos = [c for c in self.cabecalhos if c[0] != nome]

    def tamanho_atual(self):
        return len(self.dados) + sum(t for _, t in self.cabecalhos) + (TAM_F2 if self.tem_trailer_l2 else 0)

    def blocos_visuais(self):
        blocos = [{"nome": n, "bytes": t, "tipo": "cabecalho"} for n, t in self.cabecalhos]
        blocos.append({"nome": "DADOS", "bytes": len(self.dados), "tipo": "dados"})
        if self.tem_trailer_l2:
            blocos.append({"nome": "F2", "bytes": TAM_F2, "tipo": "trailer"})
        return blocos
