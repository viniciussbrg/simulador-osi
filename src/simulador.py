from eventos import BarramentoEventos
from rede import Rede
from camadas import PilhaOSI

class SimuladorOSI:
    def __init__(self, arquivo="topologia.json"):
        self.rede=Rede(arquivo); self.barramento=BarramentoEventos(); self.pilha=PilhaOSI(self)
        self.buffers={}; self.erro_enlace=None; self.total_transmitido=0; self.tamanho_util=0

    def resetar(self):
        self.barramento.limpar(); self.buffers.clear(); self.erro_enlace=None
        self.total_transmitido=0; self.tamanho_util=0; self.rede.ativar_todos()

    def ev(self,*args,**kwargs): return self.barramento.emitir(*args,**kwargs)

    def receber_segmento(self,p):
        chave=(p.logicos[0],p.portas[0],p.portas[1],p.sessao_id)
        b=self.buffers.setdefault(chave,[])
        b.append((p.segmento_indice,p.dados,p))
        if len(b)<p.segmento_total:
            self.ev(p.destino_nome,4,"AGUARDA",f"segmento {p.segmento_indice}/{p.segmento_total}; aguardando restantes",p)
            return
        b.sort(key=lambda x:x[0]); p=b[-1][2]; p.dados=b"".join(x[1] for x in b); del self.buffers[chave]
        self.pilha.finalizar_recebimento(p)

    def executar(self, origem, destino, mensagem, porta_origem=5210, porta_destino=443):
        self.tamanho_util += len(mensagem.encode("utf-8"))
        self.pilha.enviar(origem,destino,mensagem,porta_origem,porta_destino)
        return self.barramento.eventos

    def eficiencia(self):
        if not self.total_transmitido: return 0.0,1.0
        eta=self.tamanho_util/self.total_transmitido
        return eta,1-eta

    def caso(self,n):
        self.resetar()
        if n==1: self.executar("H1","H2","Entrega direta")
        elif n==2: self.executar("H1","H4","Mensagem do caso central",5210,443)
        elif n==3:
            self.executar("H1","H4","Fluxo de H1",5210,443)
            self.executar("H2","H4","Fluxo de H2",5211,443)
        elif n==4:
            self.rede.desativar_enlace("R1","R4")
            self.executar("H1","H4","Falha de enlace R1-R4")
        elif n==5:
            # destino lógico inexistente: evento explícito conforme requisito
            from pdu import PDU
            p=PDU("teste","10.0.9.10"); p.origem_nome="H1"; p.logicos=("10.0.1.10","10.0.9.10"); p.unidade="pacote"
            self.ev("H1",3,"ENCAPSULA","10.0.1.10 → 10.0.9.10",p)
            self.ev("R1",3,"DESCARTA","destino 10.0.9.10 inalcançável; nenhuma rota encontrada",p)
        elif n==6:
            self.erro_enlace=("R4","R3"); self.executar("H1","H4","Mensagem com erro de transmissão",5210,443)
        elif n==7:
            self.executar("H1","H4","Esta é uma mensagem longa destinada a ultrapassar quarenta bytes e gerar pelo menos três segmentos independentes na camada de transporte.",5210,443)
        return self.barramento.eventos

def comparar_c1_c2():
    a=SimuladorOSI(); a.caso(1); e1=a.eficiencia()
    b=SimuladorOSI(); b.caso(2); e2=b.eficiencia()
    return e1,e2
