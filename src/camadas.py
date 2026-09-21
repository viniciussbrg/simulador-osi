from pdu import PDU, TAM_C5, TAM_C4, TAM_C3, TAM_C2
import itertools

def xor_bytes(data, chave=0x5A):
    return bytes(b ^ chave for b in data)

class PilhaOSI:
    LIMITE_SEGMENTO = 40
    _sessao = itertools.count(1)
    _quadro = itertools.count(1)

    def __init__(self, simulador):
        self.s = simulador

    def enviar(self, origem, destino, mensagem, porta_origem=5210, porta_destino=443):
        p=PDU(mensagem,destino,porta_origem,porta_destino); p.origem_nome=origem
        self.s.ev(origem,7,"GERA",f"processo navegador, destino servidorWeb",p)
        p.dados=xor_bytes(p.dados); p.cifrado=True
        self.s.ev(origem,6,"CODIFICA","octetos UTF-8, conteúdo cifrado XOR",p)
        p.sessao_id=f"S-{next(self._sessao):04d}"; p.adicionar_cabecalho("L5",TAM_C5)
        self.s.ev(origem,5,"ABRE",f"sessão {p.sessao_id} estabelecida",p)

        fatias=[p.dados[i:i+self.LIMITE_SEGMENTO] for i in range(0,len(p.dados),self.LIMITE_SEGMENTO)] or [b""]
        total=len(fatias)
        for idx,fatia in enumerate(fatias,1):
            seg=p.clonar_para_segmento(fatia,idx,total)
            seg.portas=(porta_origem,porta_destino); seg.adicionar_cabecalho("L4",TAM_C4)
            self.s.ev(origem,4,"SEGMENTA",f"porta {porta_origem} → {porta_destino}, segmento {idx} de {total}",seg)
            self._transportar_segmento(seg)

    def _transportar_segmento(self,p):
        caminho,custo=self.s.rede.caminho_comunicacao(p.origem_nome,p.destino_nome)
        if not caminho:
            self.s.ev(p.origem_nome,3,"DESCARTA",f"destino {p.destino_nome} inalcançável",p)
            return
        ip_o=self.s.rede.dispositivo(p.origem_nome).interfaces[0]["ip"]
        ip_d=self.s.rede.dispositivo(p.destino_nome).interfaces[0]["ip"]
        p.logicos=(ip_o,ip_d); p.adicionar_cabecalho("L3",TAM_C3); p.unidade="pacote"
        self.s.ev(p.origem_nome,3,"ENCAPSULA",f"{ip_o} → {ip_d}",p,caminho=caminho)
        if len(caminho)>2:
            self.s.ev(p.origem_nome,3,"ROTEIA",f"próximo salto {caminho[1]}; caminho {' → '.join(caminho)}, custo {custo}",p,caminho=caminho)
        else:
            self.s.ev(p.origem_nome,3,"ROTEIA",f"entrega direta para {p.destino_nome}",p,caminho=caminho)

        for salto in range(len(caminho)-1):
            atual,prox=caminho[salto],caminho[salto+1]
            ia,ib=self.s.rede.par_interfaces(atual,prox)
            p.fisicos=(ia["mac"],ib["mac"]); p.quadro_id=f"Q{next(self._quadro)}"
            p.adicionar_cabecalho("L2",TAM_C2); p.tem_trailer_l2=True; p.unidade="quadro"
            p.verificacao=sum(p.dados)%256
            self.s.ev(atual,2,"ENQUADRA",f"{p.fisicos[0]} → {p.fisicos[1]}, quadro {p.quadro_id}",p,caminho=caminho)
            self.s.ev(atual,1,"TRANSMITE",f"{p.tamanho_atual()*8} bits no enlace {atual}–{prox}",p,caminho=caminho)
            self.s.total_transmitido += p.tamanho_atual()
            if self.s.erro_enlace == (atual,prox):
                if p.dados: p.dados=bytes([p.dados[0]^1])+p.dados[1:]
                self.s.erro_enlace=None
                self.s.ev(atual,1,"ERRO",f"1 bit alterado no enlace {atual}–{prox}",p,caminho=caminho)
            self.s.ev(prox,1,"RECEBE",f"{p.tamanho_atual()*8} bits do enlace {atual}–{prox}",p,caminho=caminho)
            if sum(p.dados)%256 != p.verificacao:
                self.s.ev(prox,2,"DESCARTA",f"verificação de erro falhou; quadro {p.quadro_id} descartado",p,caminho=caminho)
                return
            p.remover_cabecalho("L2"); p.tem_trailer_l2=False; p.unidade="pacote"
            self.s.ev(prox,2,"DESENQUADRA",f"verificação correta; quadro {p.quadro_id} descartado",p,caminho=caminho)
            if prox != p.destino_nome:
                # Roteador só interpreta L3.
                seguinte=caminho[salto+2]
                self.s.ev(prox,3,"ROTEIA",f"{p.logicos[1]} via {seguinte}; decisão na camada 3",p,caminho=caminho)

        p.remover_cabecalho("L3"); p.unidade="segmento"
        self.s.ev(p.destino_nome,3,"ENTREGA","pacote chegou ao destino final",p,caminho=caminho)
        self.s.receber_segmento(p)

    def finalizar_recebimento(self,p):
        p.remover_cabecalho("L4")
        self.s.ev(p.destino_nome,4,"REMONTA",f"fluxo {p.logicos[0]}:{p.portas[0]} → {p.portas[1]} completo",p)
        p.remover_cabecalho("L5")
        self.s.ev(p.destino_nome,5,"FECHA",f"sessão {p.sessao_id} encerrada",p)
        p.dados=xor_bytes(p.dados); p.cifrado=False
        self.s.ev(p.destino_nome,6,"DECODIFICA","conteúdo decifrado e UTF-8 restaurado",p)
        texto=p.dados.decode("utf-8",errors="replace")
        self.s.ev(p.destino_nome,7,"ENTREGA",f"processo servidorWeb recebeu: {texto}",p)
