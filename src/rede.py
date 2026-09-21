import json, os, heapq
from dispositivos import Computador, Roteador

_DIR = os.path.dirname(os.path.abspath(__file__))

class Rede:
    def __init__(self, arquivo="topologia.json"):
        caminho = arquivo if os.path.isabs(arquivo) else os.path.join(_DIR, arquivo)
        with open(caminho, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.dispositivos = {}
        for d in self.config["dispositivos"]:
            cls = Computador if d["tipo"] == "host" else Roteador
            self.dispositivos[d["nome"]] = cls(d["nome"], d["interfaces"])
        self.enlaces = self.config["enlaces"]
        self.enlaces_desativados = set()

    def dispositivo(self, nome):
        return self.dispositivos.get(nome)

    def desativar_enlace(self, a, b):
        self.enlaces_desativados.add(tuple(sorted((a,b))))

    def ativar_todos(self):
        self.enlaces_desativados.clear()

    def enlace_ativo(self, a, b):
        return tuple(sorted((a,b))) not in self.enlaces_desativados

    def vizinhos(self, nome):
        out = []
        for e in self.enlaces:
            a,b = e["a"], e["b"]
            if not self.enlace_ativo(a,b): continue
            if a == nome: out.append((b, e["custo"]))
            elif b == nome: out.append((a, e["custo"]))
        return out

    def menor_caminho(self, origem, destino):
        dist={origem:0}; ant={}; fila=[(0,origem)]
        while fila:
            d,u=heapq.heappop(fila)
            if d != dist.get(u): continue
            if u == destino: break
            for v,c in self.vizinhos(u):
                nd=d+c
                if nd < dist.get(v, 10**9):
                    dist[v]=nd; ant[v]=u; heapq.heappush(fila,(nd,v))
        if destino not in dist: return None, None
        cam=[destino]
        while cam[-1] != origem: cam.append(ant[cam[-1]])
        cam.reverse()
        return cam, dist[destino]

    def mesma_lan(self, a, b):
        ia=self.dispositivo(a).interfaces[0]["ip"].split(".")[:3]
        ib=self.dispositivo(b).interfaces[0]["ip"].split(".")[:3]
        return ia == ib

    def caminho_comunicacao(self, origem, destino):
        if self.mesma_lan(origem,destino):
            return [origem,destino], 0
        return self.menor_caminho(origem,destino)

    def interface_para(self, atual, proximo):
        disp=self.dispositivo(atual)
        for i in disp.interfaces:
            if i.get("vizinho") == proximo:
                return i
        if disp.tipo == "host":
            return disp.interfaces[0]
        alvo=self.dispositivo(proximo)
        if alvo and alvo.tipo=="host":
            pref=".".join(alvo.interfaces[0]["ip"].split(".")[:3])
            for i in disp.interfaces:
                if ".".join(i["ip"].split(".")[:3]) == pref:
                    return i
        return None

    def par_interfaces(self, atual, proximo):
        return self.interface_para(atual,proximo), self.interface_para(proximo,atual)
