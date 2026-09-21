import ipaddress
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from simulador.rede import LeitorTopologia, interface_para

class InterfaceSimulador:
    def __init__(self, motor):
        self.motor = motor
        self.root = tk.Tk()
        self.root.title("Simulador OSI - Comunicação de Dados")
        self.root.state('zoomed')
        self.root.report_callback_exception = self.mostrar_erro

        self.evento_atual = 0
        self.rodando = False
        self.modo_tcp = False
        self.velocidade_ms = 1000

        self.dispositivo_recente = "H1"
        self.camada_recente = 7
        self.acao_recente = ""
        self.envolvidos = ["H1"]
        self.enlaces_percorridos = []
        self.ativo_mapa = None

        self.construir()
        self.mostrar_comparacao()
        self.desenhar_mapa(None)
        self.atualizar_pilha("H1", 7)

    def mostrar_erro(self, tipo, valor, rastro):
        self.rodando = False
        messagebox.showerror("Erro", f"Ocorreu um erro, mas o programa continua aberto:\n\n{valor}")

    def mostrar_comparacao(self):
        c1 = self.motor.simular_cenario("C1")
        c2 = self.motor.simular_cenario("C2")
        self.motor.eventos.clear()
        self.lbl_comparacao.config(text=f"Custo do empilhamento: C1 (1 enlace) η = {c1:.1f}%   x   C2 (4 enlaces) η = {c2:.1f}%")

    def construir(self):
        frame_ctrl = tk.Frame(self.root, pady=5)
        frame_ctrl.pack(fill=tk.X, padx=10)
        
        tk.Label(frame_ctrl, text="Cenário:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        self.combo_cenario = ttk.Combobox(frame_ctrl, state="readonly", width=35)
        self.combo_cenario['values'] = [
            "C1. Entrega Direta (H1->H2)", "C2. Caso Central (H1->H4)", 
            "C3. Demultiplexação (H1 e H2 -> H4)", "C4. Falha de Enlace (R1-R4 Caiu)",
            "C5. Destino Inalcançável (Sem rota)", "C6. Erro de Transmissão (CRC)", 
            "C7. Mensagem Longa (Segmentação)"
        ]
        self.combo_cenario.current(1)
        self.combo_cenario.pack(side=tk.LEFT, padx=5)
        tk.Button(frame_ctrl, text="Executar Cenário", command=self.simular_cenario, bg="lightblue").pack(side=tk.LEFT, padx=5)
        
        tk.Label(frame_ctrl, text="  |  Velocidade:").pack(side=tk.LEFT)
        self.combo_vel = ttk.Combobox(frame_ctrl, values=["Lento", "Normal", "Rápido"], state="readonly", width=8)
        self.combo_vel.current(1)
        self.combo_vel.bind("<<ComboboxSelected>>", self.mudar_velocidade)
        self.combo_vel.pack(side=tk.LEFT, padx=5)
        
        tk.Button(frame_ctrl, text="Passo a Passo", command=self.passo).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_ctrl, text="Contínuo", command=self.continuo).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_ctrl, text="Pausar", command=self.pausar).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_ctrl, text="Alternar Pilha OSI/TCP", command=self.alternar).pack(side=tk.LEFT, padx=15)
        tk.Button(frame_ctrl, text="Salvar Registro", command=self.salvar_log, bg="lightgreen").pack(side=tk.RIGHT, padx=10)

        frame_manual = tk.Frame(self.root, pady=5)
        frame_manual.pack(fill=tk.X, padx=10)
        
        tk.Label(frame_manual, text="Envio Personalizado:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        tk.Label(frame_manual, text="Origem:").pack(side=tk.LEFT, padx=2)
        self.combo_origem = ttk.Combobox(frame_manual, state="readonly", width=5)
        self.combo_origem['values'] = ["H1", "H2", "H3", "H4", "H5"]
        self.combo_origem.current(0)
        self.combo_origem.pack(side=tk.LEFT, padx=2)
        
        tk.Label(frame_manual, text="Destino (nome ou IP):").pack(side=tk.LEFT, padx=2)
        self.combo_destino = ttk.Combobox(frame_manual, width=10)
        self.combo_destino['values'] = ["H1", "H2", "H3", "H4", "H5"]
        self.combo_destino.current(3)
        self.combo_destino.pack(side=tk.LEFT, padx=2)
        
        tk.Label(frame_manual, text="Mensagem:").pack(side=tk.LEFT, padx=2)
        self.entry_msg = tk.Entry(frame_manual, width=35)
        self.entry_msg.insert(0, "Escreva a sua mensagem aqui")
        self.entry_msg.pack(side=tk.LEFT, padx=2)
        
        tk.Button(frame_manual, text="Enviar Manualmente", command=self.simular_manual, bg="#ffebcd").pack(side=tk.LEFT, padx=10)

        frame_meio = tk.Frame(self.root)
        frame_meio.pack(fill=tk.BOTH, expand=True)
        
        self.canvas_mapa = tk.Canvas(frame_meio, bg="white", width=600)
        self.canvas_mapa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.canvas_pilha = tk.Canvas(frame_meio, bg="#f9f9f9", width=300)
        self.canvas_pilha.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        self.canvas_mapa.bind("<Configure>", lambda e: self.desenhar_mapa(self.ativo_mapa))
        self.canvas_pilha.bind("<Configure>", lambda e: self.atualizar_pilha(None, None))
        
        frame_base = tk.Frame(self.root)
        frame_base.pack(fill=tk.BOTH, expand=True)
        
        frame_info = tk.Frame(frame_base)
        frame_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        self.lbl_logico = tk.Label(frame_info, text="Endereços Lógicos (fixos da origem ao destino): --", fg="blue", font=("Arial", 11, "bold"))
        self.lbl_logico.pack(anchor="w", pady=5)
        self.lbl_fisico = tk.Label(frame_info, text="Endereços Físicos (mudam a cada salto): --", fg="green", font=("Arial", 11, "bold"))
        self.lbl_fisico.pack(anchor="w", pady=5)
        self.lbl_saltos = tk.Label(frame_info, text="", fg="green", font=("Arial", 9), justify=tk.LEFT)
        self.lbl_saltos.pack(anchor="w")
        
        tk.Label(frame_info, text="Unidade de Dados Corrente (V3):", font=("Arial", 9, "italic")).pack(anchor="w", pady=(10, 0))
        self.canvas_pdu = tk.Canvas(frame_info, height=80, bg="#eaeaea")
        self.canvas_pdu.pack(fill=tk.X, pady=5)

        self.lbl_resultado = tk.Label(frame_info, text="", font=("Arial", 10, "bold"))
        self.lbl_resultado.pack(anchor="w")
        self.lbl_comparacao = tk.Label(frame_info, text="", fg="darkred", font=("Arial", 10, "bold"))
        self.lbl_comparacao.pack(anchor="w")

        self.log = tk.Text(frame_base, height=12, width=65)
        self.log.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

    def desenhar_mapa(self, dispositivo_ativo):
        self.ativo_mapa = dispositivo_ativo
        self.canvas_mapa.delete("all")
        topo = self.motor.topologia
        todos = list(topo["computadores"].items()) + list(topo["roteadores"].items())
        largura = self.canvas_mapa.winfo_width()
        altura = self.canvas_mapa.winfo_height()
        max_x = max(d["posicao"][0] for _, d in todos) + 100
        max_y = max(d["posicao"][1] for _, d in todos) + 100
        escala = min(largura / max_x, altura / max_y, 1.5) if largura > 50 else 1
        nodes = {}
        for nome, d in todos:
            nodes[nome] = ((d["posicao"][0] + 40) * escala, (d["posicao"][1] + 40) * escala)

        links = []
        for nome, d in topo["computadores"].items():
            rede = self.motor.rede_do_ip(d["ip"])
            for r_nome, r in topo["roteadores"].items():
                for nome_if, i in r["interfaces"].items():
                    if i.get("rede") == rede:
                        links.append((nome, r_nome, "", None, nome_if))
        for e in topo["enlaces"]:
            if_de = interface_para(topo["roteadores"][e["de"]], e["para"])
            if_para = interface_para(topo["roteadores"][e["para"]], e["de"])
            links.append((e["de"], e["para"], f"custo {e['custo']}", if_de, if_para))

        for o, d, texto, if_o, if_d in links:
            (x1, y1), (x2, y2) = nodes[o], nodes[d]
            percorrido = f"{o}-{d}" in self.enlaces_percorridos or f"{d}-{o}" in self.enlaces_percorridos
            caido = f"{o}-{d}" in self.motor.enlaces_caidos or f"{d}-{o}" in self.motor.enlaces_caidos
            if caido:
                self.canvas_mapa.create_line(x1, y1, x2, y2, fill="red", width=2, dash=(5, 3))
                self.canvas_mapa.create_text((x1+x2)/2, (y1+y2)/2 + 12, text="CAIU", fill="red", font=("Arial", 8, "bold"))
            else:
                self.canvas_mapa.create_line(x1, y1, x2, y2, fill="red" if percorrido else "gray", width=4 if percorrido else 2)
            if texto:
                self.canvas_mapa.create_text((x1+x2)/2, (y1+y2)/2 - 10, text=texto, font=("Arial", 8))
            for nome_if, (xa, ya), (xb, yb) in ((if_o, (x1, y1), (x2, y2)), (if_d, (x2, y2), (x1, y1))):
                if nome_if:
                    self.canvas_mapa.create_text(xa + (xb-xa)*0.25, ya + (yb-ya)*0.25 - 8, text=nome_if, fill="darkred", font=("Arial", 8))

        for rede, nome_rede in topo["redes"].items():
            hosts = [n for n, d in topo["computadores"].items() if self.motor.rede_do_ip(d["ip"]) == rede]
            if hosts:
                x, y = nodes[hosts[-1]]
                self.canvas_mapa.create_text(x, y + 30, text=f"{nome_rede} {rede}", fill="darkgreen", font=("Arial", 9, "bold"))

        for n, (x, y) in nodes.items():
            if n == dispositivo_ativo:
                cor = "yellow"
                borda = 3
            else:
                cor = "lightblue" if "H" in n else "lightcoral"
                borda = 1
                
            self.canvas_mapa.create_oval(x-20, y-20, x+20, y+20, fill=cor, width=borda)
            self.canvas_mapa.create_text(x, y, text=n, font=("Arial", 10, "bold"))

    def atualizar_pilha(self, dispositivo, camada):
        if dispositivo:
            self.dispositivo_recente = dispositivo
            self.camada_recente = camada
        else:
            dispositivo = self.dispositivo_recente
            camada = self.camada_recente

        self.canvas_pilha.delete("all")
        if not dispositivo: return

        largura = max(self.canvas_pilha.winfo_width(), 300)
        altura = max(self.canvas_pilha.winfo_height(), 200)
        coluna = largura / len(self.envolvidos)
        w = min(coluna - 6, 120)
        passo_y = min(35, (altura - 40) / 7)
        fonte = ("Arial", 9) if w >= 100 else ("Arial", 7)

        for indice, nome in enumerate(self.envolvidos):
            centro = coluna * indice + coluna / 2
            modelo_str = "TCP/IP" if self.modo_tcp and "H" in nome else "OSI"
            titulo_texto = f"{nome} [{modelo_str}]" if "H" in nome else nome

            camadas = ["3 Rede", "2 Enlace", "1 Física"] if "R" in nome else (
                ["Aplicação (L5-L7)", "4 Transporte", "3 Rede", "2 Enlace", "1 Física"] if self.modo_tcp else
                ["7 Aplicação", "6 Apresentação", "5 Sessão", "4 Transporte", "3 Rede", "2 Enlace", "1 Física"])

            y = 35 + (7 - len(camadas)) * passo_y
            self.canvas_pilha.create_text(centro, y - 12, text=titulo_texto, font=("Arial", 9, "bold"))
            for c in camadas:
                num = int(c.split()[0]) if c.split()[0].isdigit() else 7
                destacada = False
                if nome == dispositivo and camada is not None:
                    if num == camada or (self.modo_tcp and num == 7 and camada in [5, 6, 7]):
                        destacada = True
                cor = "yellow" if destacada else "#e6e6fa"
                if destacada and "R" in nome and self.acao_recente in ("ROTEIA", "DESCARTA") and num == 3:
                    cor = "orange"

                self.canvas_pilha.create_rectangle(centro - w/2, y, centro + w/2, y + passo_y - 5, fill=cor, width=3 if destacada else 1)
                self.canvas_pilha.create_text(centro, y + (passo_y - 5)/2, text=c, font=fonte)
                y += passo_y

    def desenhar_pdu(self, camada_atual):
        self.canvas_pdu.delete("all")
        if not camada_atual: return
        
        x, y, w, h = 10, 30, 60, 40
        cores = {2: "#ffd700", 3: "#87ceeb", 4: "#98fb98", 5: "#ffb6c1", "Dados": "#d3d3d3"}
        nomes = {7: "Mensagem", 6: "Mensagem", 5: "Mensagem", 4: "Segmento", 3: "Pacote", 2: "Quadro", 1: "Bits (quadro transmitido)"}
        self.canvas_pdu.create_text(10, 15, text=f"Unidade: {nomes[camada_atual]}", anchor="w", font=("Arial", 10, "bold"))

        if camada_atual <= 2:
            self.canvas_pdu.create_rectangle(x, y, x+w, y+h, fill=cores[2])
            self.canvas_pdu.create_text(x+w/2, y+h/2, text="L2 Hdr")
            x += w
        if camada_atual <= 3:
            self.canvas_pdu.create_rectangle(x, y, x+w, y+h, fill=cores[3])
            self.canvas_pdu.create_text(x+w/2, y+h/2, text="L3 Hdr")
            x += w
        if camada_atual <= 4:
            self.canvas_pdu.create_rectangle(x, y, x+w, y+h, fill=cores[4])
            self.canvas_pdu.create_text(x+w/2, y+h/2, text="L4 Hdr")
            x += w
        if camada_atual <= 5:
            self.canvas_pdu.create_rectangle(x, y, x+w, y+h, fill=cores[5])
            self.canvas_pdu.create_text(x+w/2, y+h/2, text="L5 Hdr")
            x += w

        self.canvas_pdu.create_rectangle(x, y, x+w*2, y+h, fill=cores["Dados"])
        self.canvas_pdu.create_text(x+w, y+h/2, text="Dados (Payload)")
        x += w*2
        
        if camada_atual <= 2:
            self.canvas_pdu.create_rectangle(x, y, x+w, y+h, fill=cores[2])
            self.canvas_pdu.create_text(x+w/2, y+h/2, text="L2 FCS")

    def simular_cenario(self):
        self.log.delete(1.0, tk.END)
        cenario = self.combo_cenario.get()
        self.motor.simular_cenario(cenario)
        self.iniciar_ciclo_animacao()

    def simular_manual(self):
        origem_nome = self.combo_origem.get()
        destino = self.combo_destino.get().strip()
        texto = self.entry_msg.get()

        if destino in self.motor.topologia["computadores"]:
            ip_destino = self.motor.topologia["computadores"][destino]["ip"]
        else:
            try:
                ip_destino = str(ipaddress.IPv4Address(destino))
            except ValueError:
                messagebox.showerror("Destino inválido", f"'{destino}' não é um computador (H1 a H5) nem um endereço IP válido.")
                return
        if ip_destino == self.motor.topologia["computadores"][origem_nome]["ip"]:
            messagebox.showerror("Destino inválido", "O destino não pode ser o próprio computador de origem.")
            return
        if not texto:
            messagebox.showerror("Mensagem vazia", "Digite uma mensagem para enviar.")
            return

        self.log.delete(1.0, tk.END)
        self.motor.reiniciar()
        self.motor.iniciar_transmissao(origem_nome, ip_destino, 5210, 443, texto)
        self.motor.finalizar()
        self.iniciar_ciclo_animacao()

    def iniciar_ciclo_animacao(self):
        self.evento_atual = 0
        self.rodando = False
        self.enlaces_percorridos = []
        self.lbl_saltos.config(text="")
        self.lbl_resultado.config(text="")
        self.lbl_logico.config(text="Endereços Lógicos (fixos da origem ao destino): --")
        self.lbl_fisico.config(text="Endereços Físicos (mudam a cada salto): --")
        self.envolvidos = []
        for evt in self.motor.eventos:
            nome = evt.split('|')[1].strip()
            if nome != "SISTEMA" and nome not in self.envolvidos:
                self.envolvidos.append(nome)
        self.passo()

    def alternar(self):
        self.modo_tcp = not self.modo_tcp
        self.atualizar_pilha(None, None)

    def mudar_velocidade(self, event):
        v = self.combo_vel.get()
        self.velocidade_ms = 2000 if v == "Lento" else 500 if v == "Rápido" else 1000

    def pausar(self): self.rodando = False
    
    def continuo(self): 
        self.rodando = True
        self.executar()
        
    def passo(self):
        self.rodando = False
        self.executar()

    def executar(self):
        if self.evento_atual < len(self.motor.eventos):
            evt = self.motor.eventos[self.evento_atual]
            self.log.insert(tk.END, evt + "\n")
            self.log.see(tk.END)
            
            if "SISTEMA" not in evt:
                partes = [p.strip() for p in evt.split('|')]
                disp, cam, acao = partes[1], int(partes[2].replace('L','')), partes[3]
                desc = partes[4].rsplit(' ', 2)[0].strip()
                self.acao_recente = acao
                if acao == "TRANSMITE": self.enlaces_percorridos.append(desc.split("enlace ")[1])
                self.atualizar_pilha(disp, cam)
                self.desenhar_pdu(cam)
                self.desenhar_mapa(disp)

                if acao == "ENCAPSULA": self.lbl_logico.config(text=f"Endereços Lógicos (fixos da origem ao destino): {desc}")
                if acao == "ENQUADRA":
                    self.lbl_fisico.config(text=f"Endereços Físicos (mudam a cada salto): {desc}")
                    self.lbl_saltos.config(text=self.lbl_saltos.cget("text") + f"{desc.split(', ')[1]}: {desc.split(',')[0]}\n")
            elif "RESULTADO" in evt:
                self.lbl_resultado.config(text=evt.split("RESULTADO | ")[1])

            self.evento_atual += 1
            if self.rodando: self.root.after(self.velocidade_ms, self.executar)
        else: 
            self.rodando = False
            self.desenhar_mapa(None)

    def salvar_log(self):
        if not self.motor.eventos:
            messagebox.showinfo("Salvar Registro", "Execute um cenário antes de salvar o registro.")
            return
        caminho = filedialog.asksaveasfilename(initialdir=LeitorTopologia.pasta_do_programa(), initialfile="registro.txt", defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if caminho:
            with open(caminho, 'w', encoding='utf-8') as f:
                f.write("\n".join(self.motor.eventos) + "\n")