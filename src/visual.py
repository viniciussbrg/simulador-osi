import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from simulador import SimuladorOSI, comparar_c1_c2

class GUI:
    def __init__(self,root):
        self.root=root; root.title("Simulador OSI"); root.geometry("1450x850")
        self.sim=SimuladorOSI(); self.eventos=[]; self.i=0; self.rodando=False; self.after_id=None
        self.modo_pilha=tk.StringVar(value="OSI"); self.vel=tk.StringVar(value="Normal")
        self._ui(); self._mapa()

    def _ui(self):
        top=ttk.Frame(self.root); top.pack(fill="x",padx=8,pady=6)
        ttk.Label(top,text="Caso:").pack(side="left")
        self.caso=ttk.Combobox(top,state="readonly",width=38,values=[
            "C1 Entrega direta","C2 Entrega indireta","C3 Demultiplexação","C4 Falha de enlace",
            "C5 Destino inalcançável","C6 Erro de transmissão","C7 Mensagem longa"])
        self.caso.current(1); self.caso.pack(side="left",padx=4)
        ttk.Button(top,text="Carregar caso",command=self.carregar).pack(side="left",padx=3)
        ttk.Button(top,text="Passo ▶",command=self.passo).pack(side="left",padx=3)
        ttk.Button(top,text="Contínuo",command=self.play).pack(side="left",padx=3)
        ttk.Button(top,text="Pausa",command=self.pausa).pack(side="left",padx=3)
        ttk.Label(top,text="Velocidade:").pack(side="left",padx=(12,2))
        ttk.Combobox(top,textvariable=self.vel,state="readonly",width=10,values=["Lenta","Normal","Rápida"]).pack(side="left")
        ttk.Button(top,text="OSI/TCP-IP",command=self.alternar).pack(side="left",padx=8)
        ttk.Button(top,text="Salvar log",command=self.salvar).pack(side="right")

        main=ttk.Panedwindow(self.root,orient="horizontal"); main.pack(fill="both",expand=True,padx=8,pady=4)
        esq=ttk.Frame(main); meio=ttk.Frame(main); dir=ttk.Frame(main)
        main.add(esq,weight=3); main.add(meio,weight=4); main.add(dir,weight=3)

        ttk.Label(esq,text="V1 — Mapa da rede",font=("Segoe UI",11,"bold")).pack(anchor="w")
        self.canvas=tk.Canvas(esq,bg="white",height=390); self.canvas.pack(fill="both",expand=True)
        self.lbl_caminho=ttk.Label(esq,text="Caminho: —"); self.lbl_caminho.pack(anchor="w",pady=4)
        self.lbl_metricas=ttk.Label(esq,text="Eficiência: —"); self.lbl_metricas.pack(anchor="w")

        ttk.Label(meio,text="V2 — Pilhas dos dispositivos",font=("Segoe UI",11,"bold")).pack(anchor="w")
        self.pilhas=tk.Canvas(meio,bg="#fafafa",height=310); self.pilhas.pack(fill="x")
        ttk.Label(meio,text="V3 — Unidade de dados (PDU)",font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(6,0))
        self.pdu=tk.Canvas(meio,bg="white",height=120); self.pdu.pack(fill="x")
        ttk.Label(meio,text="V4 — Endereçamento",font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(6,0))
        self.lbl_ip=ttk.Label(meio,text="Lógicos (fixos): —"); self.lbl_ip.pack(anchor="w")
        self.lbl_mac=ttk.Label(meio,text="Físicos (por salto): —"); self.lbl_mac.pack(anchor="w")

        ttk.Label(dir,text="V6 — Registro de eventos",font=("Segoe UI",11,"bold")).pack(anchor="w")
        self.log=scrolledtext.ScrolledText(dir,font=("Consolas",9)); self.log.pack(fill="both",expand=True)
        self.status=ttk.Label(self.root,text="Carregue um caso para iniciar."); self.status.pack(fill="x",padx=8,pady=4)

    def _mapa(self):
        self.coords={"H1":(45,70),"H2":(45,190),"R1":(160,130),"R4":(290,65),"R2":(290,200),
                     "R3":(420,130),"H3":(290,315),"H4":(545,70),"H5":(545,190)}
        self.arestas={}
        for e in self.sim.rede.enlaces:
            a,b=e["a"],e["b"]; x1,y1=self.coords[a]; x2,y2=self.coords[b]
            lid=self.canvas.create_line(x1,y1,x2,y2,fill="#888",width=2)
            self.arestas[tuple(sorted((a,b)))]=lid
            if e["custo"]:
                self.canvas.create_text((x1+x2)//2,(y1+y2)//2-8,text=str(e["custo"]))
        self.nos={}
        for n,(x,y) in self.coords.items():
            fill="#d9ecff" if n.startswith("H") else "#ffe0e0"
            o=self.canvas.create_oval(x-22,y-22,x+22,y+22,fill=fill,outline="#333",width=2)
            self.canvas.create_text(x,y,text=n,font=("Segoe UI",9,"bold")); self.nos[n]=o
        for nome,disp in self.sim.rede.dispositivos.items():
            x,y=self.coords[nome]
            txt=" / ".join(i["nome"] for i in disp.interfaces)
            self.canvas.create_text(x,y+31,text=txt,font=("Segoe UI",7))

    def carregar(self):
        self.pausa(); self.sim=SimuladorOSI(); n=self.caso.current()+1
        self.eventos=list(self.sim.caso(n)); self.i=0; self.log.delete("1.0","end")
        self._reset_visual()
        eta,sob=self.sim.eficiencia()
        self.lbl_metricas.config(text=f"Execução: dados úteis={self.sim.tamanho_util} B | transmitidos={self.sim.total_transmitido} B | η={eta:.3f} | sobrecarga={sob:.3f}")
        self.status.config(text=f"Caso C{n} carregado — {len(self.eventos)} eventos.")
        if n in (1,2):
            c1,c2=comparar_c1_c2()
            self.lbl_metricas.config(text=self.lbl_metricas.cget("text")+f" | comparação C1 η={c1[0]:.3f} × C2 η={c2[0]:.3f}")

    def _reset_visual(self):
        for n,o in self.nos.items():
            self.canvas.itemconfig(o,fill="#d9ecff" if n.startswith("H") else "#ffe0e0",outline="#333",width=2)
        for lid in self.arestas.values(): self.canvas.itemconfig(lid,fill="#888",width=2)
        self.pilhas.delete("all"); self.pdu.delete("all")
        self.lbl_ip.config(text="Lógicos (fixos): —"); self.lbl_mac.config(text="Físicos (por salto): —"); self.lbl_caminho.config(text="Caminho: —")

    def passo(self):
        if self.i>=len(self.eventos): self.status.config(text="Execução concluída."); return
        ev=self.eventos[self.i]; self.i+=1; self._mostrar(ev)
        if self.i>=len(self.eventos): self.status.config(text="Execução concluída.")

    def play(self):
        self.rodando=True; self._tick()

    def _tick(self):
        if not self.rodando or self.i>=len(self.eventos): self.rodando=False; return
        self.passo(); ms={"Lenta":1200,"Normal":600,"Rápida":180}[self.vel.get()]
        self.after_id=self.root.after(ms,self._tick)

    def pausa(self):
        self.rodando=False
        if self.after_id:
            try:self.root.after_cancel(self.after_id)
            except:pass
            self.after_id=None

    def alternar(self):
        self.modo_pilha.set("TCP/IP" if self.modo_pilha.get()=="OSI" else "OSI")
        if self.i: self._desenhar_pilhas(self.eventos[self.i-1])

    def _mostrar(self,ev):
        self.log.insert("end",ev.linha()+"\n"); self.log.see("end")
        for n,o in self.nos.items():
            self.canvas.itemconfig(o,fill="#d9ecff" if n.startswith("H") else "#ffe0e0",outline="#333",width=2)
        if ev.dispositivo in self.nos:self.canvas.itemconfig(self.nos[ev.dispositivo],fill="#fff59d",outline="#d32f2f",width=3)
        if ev.caminho:
            self.lbl_caminho.config(text="Caminho: "+" → ".join(ev.caminho))
            for a,b in zip(ev.caminho,ev.caminho[1:]):
                lid=self.arestas.get(tuple(sorted((a,b))))
                if lid:self.canvas.itemconfig(lid,fill="#1976d2",width=5)
        if ev.logicos:self.lbl_ip.config(text=f"Lógicos (fixos): {ev.logicos[0]} → {ev.logicos[1]}")
        if ev.fisicos:self.lbl_mac.config(text=f"Físicos (salto atual): {ev.fisicos[0]} → {ev.fisicos[1]}")
        self._desenhar_pilhas(ev); self._desenhar_pdu(ev)
        self.status.config(text=f"Passo {ev.passo}: {ev.dispositivo} L{ev.camada} {ev.acao}")

    def _desenhar_pilhas(self,ev):
        self.pilhas.delete("all")
        caminho=ev.caminho or [ev.dispositivo]
        nomes=[]
        for n in caminho:
            if n not in nomes: nomes.append(n)
        if ev.dispositivo not in nomes: nomes.append(ev.dispositivo)
        w=max(90, int(self.pilhas.winfo_width()/max(1,len(nomes))))
        modo=self.modo_pilha.get()
        for j,n in enumerate(nomes):
            x=10+j*w; self.pilhas.create_text(x+35,15,text=n,font=("Segoe UI",9,"bold"))
            roteador=n.startswith("R")
            if modo=="OSI":
                camadas=[7,6,5,4,3,2,1] if not roteador else [3,2,1]
                labels={7:"Aplic.",6:"Apres.",5:"Sessão",4:"Transp.",3:"Rede",2:"Enlace",1:"Física"}
            else:
                camadas=[7,4,3,2] if not roteador else [3,2]
                labels={7:"Aplic. (7–5)",4:"Transporte",3:"Internet",2:"Acesso (2–1)"}
            for k,c in enumerate(camadas):
                y=30+k*31; ativo=(n==ev.dispositivo and (c==ev.camada or (modo=="TCP/IP" and ((c==7 and ev.camada in (5,6,7)) or (c==2 and ev.camada in (1,2))))))
                self.pilhas.create_rectangle(x,y,x+75,y+25,fill="#b9f6ca" if ativo else "white",outline="#555",width=2 if ativo else 1)
                self.pilhas.create_text(x+37,y+12,text=labels[c],font=("Segoe UI",7))

    def _desenhar_pdu(self,ev):
        self.pdu.delete("all"); blocos=ev.pdu_blocos or []
        x=10
        for b in blocos:
            largura=max(55,min(130,30+b["bytes"]*2))
            fill={"cabecalho":"#d7e8ff","dados":"#e8f5e9","trailer":"#ffe0b2"}[b["tipo"]]
            self.pdu.create_rectangle(x,30,x+largura,78,fill=fill,outline="#444")
            self.pdu.create_text(x+largura/2,48,text=b["nome"],font=("Segoe UI",8,"bold"))
            self.pdu.create_text(x+largura/2,66,text=f'{b["bytes"]} B',font=("Segoe UI",7))
            x+=largura+3
        self.pdu.create_text(10,100,anchor="w",text=f"Unidade: {ev.unidade or '—'} | quadro: {ev.quadro or '—'}")

    def salvar(self):
        arq=filedialog.asksaveasfilename(defaultextension=".txt",filetypes=[("Texto","*.txt")])
        if arq:
            with open(arq,"w",encoding="utf-8") as f:f.write(self.log.get("1.0","end"))
            messagebox.showinfo("Log","Registro salvo.")

if __name__=="__main__":
    root=tk.Tk(); GUI(root); root.mainloop()
