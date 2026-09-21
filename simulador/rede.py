"""Topologia, enlaces e decisao de rota.

Este modulo responde a duas perguntas, e apenas a elas: como a rede e
formada e por onde um pacote deve seguir. Ele nao conhece camadas, PDUs
nem interface grafica.

A decisao de rota pertence exclusivamente a camada 3, conforme a restricao
R4 do enunciado. As tabelas produzidas aqui sao consultadas por ela; a
camada 2 apenas entrega ao vizinho que a camada 3 indicou.
"""

import json
from dataclasses import dataclass, field

from .recursos import localizar

# Custo devolvido quando nao existe caminho ate a rede procurada.
INALCANCAVEL = float("inf")


@dataclass(frozen=True)
class Interface:
    """Um ponto de conexao de um dispositivo com uma rede."""

    dispositivo: str
    nome: str
    logico: str
    fisico: str
    rede: str

    @property
    def identificador(self):
        return f"{self.dispositivo}:{self.nome}"


@dataclass(frozen=True)
class Enlace:
    """Uma ligacao entre duas interfaces, com o custo usado na escolha de rota."""

    a: str
    b: str
    custo: int
    rede: str

    def outro_lado(self, identificador):
        """Devolve a interface do outro extremo, ou None se nao pertencer a este enlace."""
        if identificador == self.a:
            return self.b
        if identificador == self.b:
            return self.a
        return None


@dataclass
class Rota:
    """Uma linha da tabela de encaminhamento."""

    prefixo: str
    proximo_salto: str
    interface_de_saida: str
    custo: int
    direta: bool = False


class Topologia:
    """A rede simulada, carregada de um arquivo externo."""

    def __init__(self, dados):
        self.nome = dados.get("nome", "topologia")
        self.convencoes = dados["convencoes"]
        self.redes = {r["nome"]: r["prefixo"] for r in dados["redes"]}

        self.interfaces = {}
        self.computadores = []
        self.roteadores = []

        for maquina in dados["computadores"]:
            interface = Interface(
                maquina["nome"], maquina["interface"], maquina["logico"],
                maquina["fisico"], maquina["rede"],
            )
            self.interfaces[interface.identificador] = interface
            self.computadores.append(maquina["nome"])

        for roteador in dados["roteadores"]:
            for descricao in roteador["interfaces"]:
                interface = Interface(
                    roteador["nome"], descricao["nome"], descricao["logico"],
                    descricao["fisico"], descricao["rede"],
                )
                self.interfaces[interface.identificador] = interface
            self.roteadores.append(roteador["nome"])

        self.enlaces = [
            Enlace(e["a"], e["b"], e["custo"], e["rede"]) for e in dados["enlaces"]
        ]

        # Enlaces derrubados pela interface do simulador. Ficam fora da
        # escolha de rota enquanto estiverem aqui, e o caso E4 depende disso.
        self.enlaces_derrubados = set()

        # De onde esta topologia foi lida (R10). Preenchido por carregar();
        # fica None quando a topologia e montada direto de um dicionario.
        self.origem = None

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------

    @classmethod
    def carregar(cls, nome_do_arquivo="topologia.json"):
        """Le a topologia ao lado do programa ou, na falta dela, a embutida (R10).

        A topologia lida guarda em .origem de qual das duas ela veio, para que
        a interface possa dizer isso ao usuario: um arquivo editado ao lado do
        executavel e uma copia embutida produzem redes diferentes, e quem
        avalia precisa saber qual esta em uso.
        """
        origem = localizar(nome_do_arquivo)
        with open(origem.caminho, encoding="utf-8") as arquivo:
            topologia = cls(json.load(arquivo))
        topologia.origem = origem
        return topologia

    # ------------------------------------------------------------------
    # Enderecos
    # ------------------------------------------------------------------

    def interface_de(self, dispositivo, nome=None):
        """Devolve uma interface pelo nome, ou a primeira do dispositivo."""
        if nome:
            return self.interfaces[f"{dispositivo}:{nome}"]
        for interface in self.interfaces.values():
            if interface.dispositivo == dispositivo:
                return interface
        raise KeyError(f"dispositivo desconhecido: {dispositivo}")

    def interface_por_logico(self, endereco):
        for interface in self.interfaces.values():
            if interface.logico == endereco:
                return interface
        return None

    def prefixo_de(self, endereco_logico):
        """Devolve o prefixo da rede a que um endereco pertence, ou None.

        A comparacao usa os tres primeiros octetos porque todas as redes da
        topologia sao /24. Um endereco fora de qualquer prefixo conhecido
        devolve None, e e assim que o caso E5 e reconhecido.
        """
        inicio = ".".join(endereco_logico.split(".")[:3])
        for prefixo in self.redes.values():
            if prefixo.startswith(inicio + "."):
                return prefixo
        return None

    def mesma_rede(self, um, outro):
        """Informa se dois enderecos logicos compartilham o prefixo de rede.

        E o teste que a camada 3 faz para decidir entre entrega direta e
        entrega indireta, e o que sustenta o caso E1.
        """
        prefixo = self.prefixo_de(um)
        return prefixo is not None and prefixo == self.prefixo_de(outro)

    def rede_do_prefixo(self, prefixo):
        for nome, valor in self.redes.items():
            if valor == prefixo:
                return nome
        return None

    def roteador_da_rede(self, nome_da_rede):
        """Devolve o roteador conectado a uma rede local."""
        for interface in self.interfaces.values():
            if interface.rede == nome_da_rede and interface.dispositivo in self.roteadores:
                return interface.dispositivo
        return None

    # ------------------------------------------------------------------
    # Enlaces
    # ------------------------------------------------------------------

    def chave_do_enlace(self, enlace):
        return tuple(sorted((enlace.a, enlace.b)))

    def ativo(self, enlace):
        return self.chave_do_enlace(enlace) not in self.enlaces_derrubados

    def derrubar(self, dispositivo_a, dispositivo_b):
        """Retira de servico o enlace entre dois dispositivos.

        Usado pelo caso E4: com o enlace R1-R4 fora, a rota de menor custo
        ate a Rede C passa a ser a que atravessa R2.
        """
        for enlace in self.enlaces:
            extremos = {enlace.a.split(":")[0], enlace.b.split(":")[0]}
            if extremos == {dispositivo_a, dispositivo_b}:
                self.enlaces_derrubados.add(self.chave_do_enlace(enlace))
                return True
        return False

    def restaurar_enlaces(self):
        self.enlaces_derrubados.clear()

    def enlace_entre(self, dispositivo_a, dispositivo_b):
        for enlace in self.enlaces:
            extremos = {enlace.a.split(":")[0], enlace.b.split(":")[0]}
            if extremos == {dispositivo_a, dispositivo_b} and self.ativo(enlace):
                return enlace
        return None

    def vizinhos(self, roteador):
        """Devolve os roteadores adjacentes, com custo e interface de saida."""
        encontrados = []
        for enlace in self.enlaces:
            if not self.ativo(enlace):
                continue
            for local, remoto in ((enlace.a, enlace.b), (enlace.b, enlace.a)):
                if not local.startswith(roteador + ":"):
                    continue
                outro = remoto.split(":")[0]
                if outro in self.roteadores:
                    encontrados.append((outro, enlace.custo, local.split(":")[1]))
        # A ordenacao torna deterministico o desempate entre caminhos de
        # mesmo custo: vence o vizinho de menor identificador.
        return sorted(encontrados, key=lambda v: (v[1], v[0]))

    # ------------------------------------------------------------------
    # Escolha de rota
    # ------------------------------------------------------------------

    def _custos_a_partir_de(self, origem):
        """Menor custo de um roteador ate cada outro, com o primeiro salto.

        Implementa Dijkstra sobre o grafo de roteadores. Cada entrada guarda
        o custo total e o vizinho pelo qual o caminho comeca, que e o que a
        tabela de encaminhamento precisa registrar.
        """
        custos = {origem: 0}
        primeiro_salto = {origem: (origem, None)}
        visitados = set()

        while True:
            # Entre os nao visitados, toma o de menor custo; o nome desempata.
            pendentes = [(c, n) for n, c in custos.items() if n not in visitados]
            if not pendentes:
                break
            custo_atual, atual = min(pendentes)
            visitados.add(atual)

            for vizinho, custo, interface in self.vizinhos(atual):
                candidato = custo_atual + custo
                if vizinho in custos and custos[vizinho] <= candidato:
                    continue
                custos[vizinho] = candidato
                if atual == origem:
                    primeiro_salto[vizinho] = (vizinho, interface)
                else:
                    primeiro_salto[vizinho] = primeiro_salto[atual]

        return custos, primeiro_salto

    def tabela_de_encaminhamento(self, roteador):
        """Monta a tabela de um roteador: uma rota para cada rede local.

        As redes diretamente conectadas entram com custo zero e entrega
        direta. As demais entram com o primeiro salto do caminho de menor
        custo ate o roteador que atende a rede.
        """
        custos, primeiro_salto = self._custos_a_partir_de(roteador)
        tabela = []

        for nome_da_rede, prefixo in self.redes.items():
            local = [
                i for i in self.interfaces.values()
                if i.dispositivo == roteador and i.rede == nome_da_rede
            ]
            if local:
                tabela.append(
                    Rota(prefixo, "entrega direta", local[0].nome, 0, direta=True)
                )
                continue

            dono = self.roteador_da_rede(nome_da_rede)
            if dono is None or dono not in custos:
                continue

            salto, interface = primeiro_salto[dono]
            tabela.append(Rota(prefixo, salto, interface, custos[dono]))

        return sorted(tabela, key=lambda r: r.prefixo)

    def rota_para(self, roteador, endereco_destino):
        """Devolve a rota que um roteador usa para um destino, ou None.

        None significa destino inalcancavel: e o que faz a camada 3
        descartar o pacote e registrar o descarte, no caso E5.
        """
        prefixo = self.prefixo_de(endereco_destino)
        if prefixo is None:
            return None
        for rota in self.tabela_de_encaminhamento(roteador):
            if rota.prefixo == prefixo:
                return rota
        return None

    def caminho_de_dispositivos(self, origem, destino):
        """Devolve a sequencia de dispositivos percorrida, do origem ao destino.

        Serve ao mapa da interface, que destaca o caminho efetivamente
        seguido, e a contagem de enlaces usada no quadro de eficiencia.
        Devolve None quando o destino e inalcancavel.
        """
        interface_origem = self.interface_de(origem)
        interface_destino = self.interface_por_logico(destino)
        if interface_destino is None:
            return None

        if self.mesma_rede(interface_origem.logico, destino):
            return [origem, interface_destino.dispositivo]

        atual = self.roteador_da_rede(interface_origem.rede)
        if atual is None:
            return None

        percurso = [origem, atual]
        while True:
            rota = self.rota_para(atual, destino)
            if rota is None:
                return None
            if rota.direta:
                percurso.append(interface_destino.dispositivo)
                return percurso
            atual = rota.proximo_salto
            if atual in percurso:  # laco de roteamento
                return None
            percurso.append(atual)
