import json
import os
import sys

class LeitorTopologia:
    @staticmethod
    def pasta_do_programa():
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @staticmethod
    def carregar(arquivo="topologia.json"):
        caminho = os.path.join(LeitorTopologia.pasta_do_programa(), arquivo)
        if not os.path.exists(caminho) and hasattr(sys, '_MEIPASS'):
            caminho = os.path.join(sys._MEIPASS, arquivo)

        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)

def interface_para(roteador, vizinho):
    for nome_if, interface in roteador["interfaces"].items():
        if interface.get("vizinho") == vizinho:
            return nome_if
    return None

def calcular_rotas(dados, enlaces_caidos=()):
    roteadores = dados["roteadores"]
    vizinhos = {nome: {} for nome in roteadores}
    for enlace in dados["enlaces"]:
        if f"{enlace['de']}-{enlace['para']}" in enlaces_caidos or f"{enlace['para']}-{enlace['de']}" in enlaces_caidos:
            continue
        vizinhos[enlace["de"]][enlace["para"]] = enlace["custo"]
        vizinhos[enlace["para"]][enlace["de"]] = enlace["custo"]

    todas_rotas = {}
    for origem in roteadores:
        distancia = {origem: 0}
        primeiro_salto = {origem: None}
        visitados = set()
        while len(visitados) < len(distancia):
            atual = min((r for r in distancia if r not in visitados), key=lambda r: (distancia[r], r))
            visitados.add(atual)
            for vizinho, custo in sorted(vizinhos[atual].items()):
                if vizinho not in distancia or distancia[atual] + custo < distancia[vizinho]:
                    distancia[vizinho] = distancia[atual] + custo
                    primeiro_salto[vizinho] = vizinho if atual == origem else primeiro_salto[atual]

        rotas = {}
        for nome in sorted(distancia, key=lambda r: (distancia[r], r)):
            for nome_if, interface in roteadores[nome]["interfaces"].items():
                rede = interface.get("rede")
                if rede is None or rede in rotas:
                    continue
                if nome == origem:
                    rotas[rede] = {"prox_salto": None, "interface": nome_if, "custo": 0}
                else:
                    prox = primeiro_salto[nome]
                    ip_prox = roteadores[prox]["interfaces"][interface_para(roteadores[prox], origem)]["ip"]
                    rotas[rede] = {"prox_salto": prox, "ip_prox": ip_prox, "interface": interface_para(roteadores[origem], prox), "custo": distancia[nome]}
        todas_rotas[origem] = rotas
    return todas_rotas
