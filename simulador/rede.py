"""Topologia da rede simulada, enlaces, custos e tabelas de encaminhamento.

A topologia e lida integralmente de um arquivo externo, por padrao
``topologia.json``, localizado ao lado do programa. Nenhum endereco, custo ou
nome de dispositivo aparece escrito no codigo: trocar o arquivo troca a rede
simulada.

Modelo adotado
--------------
A rede e descrita por *segmentos*. Um segmento agrupa as interfaces que se
enxergam diretamente na camada 2 e possui um prefixo e um custo. Segmentos com
duas interfaces representam enlaces ponto a ponto entre roteadores; segmentos
com mais interfaces representam redes locais. Dois dispositivos ligados ao
mesmo segmento sao vizinhos de enlace, o que permite a entrega direta do caso
C1 sem passar por roteador.
"""

from __future__ import annotations

import heapq
import ipaddress
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CUSTO_INFINITO = float("inf")


class ErroDeTopologiaError(ValueError):
    """Arquivo de topologia ausente, malformado ou inconsistente."""


# Estruturas


@dataclass(frozen=True)
class Interface:
    """Uma interface de rede de um dispositivo."""

    dispositivo: str
    nome: str
    logico: str
    mascara: int
    fisico: str
    rede: str

    @property
    def identificador(self) -> str:
        return f"{self.dispositivo}:{self.nome}"

    @property
    def prefixo(self) -> str:
        return str(ipaddress.ip_network(f"{self.logico}/{self.mascara}", strict=False))


@dataclass
class Segmento:
    """Conjunto de interfaces que se alcancam diretamente na camada 2."""

    nome: str
    prefixo: str
    custo: int
    tipo: str
    posicao: Optional[Tuple[float, float]] = None
    interfaces: List[Interface] = field(default_factory=list)
    ativo: bool = True

    @property
    def dispositivos(self) -> List[str]:
        return [i.dispositivo for i in self.interfaces]

    @property
    def local(self) -> bool:
        return self.tipo == "local"


@dataclass(frozen=True)
class Rota:
    """Uma linha da tabela de encaminhamento de um roteador."""

    destino: str
    proximo_salto: Optional[str]
    custo: int
    interface: str

    @property
    def direta(self) -> bool:
        return self.proximo_salto is None


@dataclass(frozen=True)
class DescricaoDispositivo:
    """Dados de um dispositivo lidos do arquivo de topologia."""

    nome: str
    tipo: str
    interfaces: Tuple[Interface, ...]
    gateway: Optional[str] = None
    posicao: Optional[Tuple[float, float]] = None


# Topologia


class Topologia:
    """Rede carregada do arquivo externo, com consultas de rota e vizinhanca."""

    def __init__(self, dados: dict, origem: str = "<memoria>") -> None:
        self.origem = origem
        self.nome: str = dados.get("nome", "Rede sem nome")
        self.descricao: str = dados.get("descricao", "")
        self.segmentos: Dict[str, Segmento] = {}
        self.dispositivos: Dict[str, DescricaoDispositivo] = {}
        self._interfaces_por_logico: Dict[str, Interface] = {}
        self._construir(dados)
        self._validar()
        self._cache_tabelas: Dict[str, List[Rota]] = {}

    # -- construcao --------------------------------------------------------

    @classmethod
    def carregar(cls, caminho: str) -> "Topologia":
        """Le a topologia de um arquivo JSON.

        :raises ErroDeTopologiaError: arquivo ausente, JSON invalido ou
            conteudo inconsistente.
        """
        if not os.path.isfile(caminho):
            raise ErroDeTopologiaError(
                f"arquivo de topologia nao encontrado: {caminho}\n"
                f"Coloque o arquivo topologia.json ao lado do programa."
            )
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except json.JSONDecodeError as erro:
            raise ErroDeTopologiaError(
                f"o arquivo {os.path.basename(caminho)} nao e um JSON valido "
                f"(linha {erro.lineno}, coluna {erro.colno}): {erro.msg}"
            ) from erro
        except OSError as erro:
            raise ErroDeTopologiaError(
                f"nao foi possivel ler {caminho}: {erro}"
            ) from erro
        return cls(dados, origem=caminho)

    def _construir(self, dados: dict) -> None:
        if not isinstance(dados.get("redes"), list) or not dados["redes"]:
            raise ErroDeTopologiaError("a topologia precisa da lista 'redes'")
        if not isinstance(dados.get("dispositivos"), list) or not dados["dispositivos"]:
            raise ErroDeTopologiaError("a topologia precisa da lista 'dispositivos'")

        for bruto in dados["redes"]:
            nome = self._exigir(bruto, "nome", "rede")
            prefixo = self._exigir(bruto, "prefixo", f"rede {nome}")
            try:
                prefixo = str(ipaddress.ip_network(prefixo, strict=False))
            except ValueError as erro:
                raise ErroDeTopologiaError(
                    f"prefixo invalido em {nome}: {erro}"
                ) from erro
            posicao = bruto.get("posicao")
            self.segmentos[nome] = Segmento(
                nome=nome,
                prefixo=prefixo,
                custo=int(bruto.get("custo", 1)),
                tipo=bruto.get("tipo", "ponto-a-ponto"),
                posicao=tuple(posicao) if posicao else None,
            )

        for bruto in dados["dispositivos"]:
            nome = self._exigir(bruto, "nome", "dispositivo")
            tipo = bruto.get("tipo", "computador")
            if tipo not in ("computador", "roteador"):
                raise ErroDeTopologiaError(
                    f"tipo invalido em {nome}: {tipo!r}; use 'computador' ou 'roteador'"
                )
            interfaces = []
            for bruta in bruto.get("interfaces", []):
                interface = Interface(
                    dispositivo=nome,
                    nome=self._exigir(bruta, "nome", f"interface de {nome}"),
                    logico=self._exigir(bruta, "logico", f"interface de {nome}"),
                    mascara=int(bruta.get("mascara", 24)),
                    fisico=self._exigir(bruta, "fisico", f"interface de {nome}"),
                    rede=self._exigir(bruta, "rede", f"interface de {nome}"),
                )
                if interface.rede not in self.segmentos:
                    raise ErroDeTopologiaError(
                        f"a interface {interface.identificador} referencia a rede "
                        f"{interface.rede!r}, que nao esta declarada em 'redes'"
                    )
                interfaces.append(interface)
                self.segmentos[interface.rede].interfaces.append(interface)
            if not interfaces:
                raise ErroDeTopologiaError(
                    f"o dispositivo {nome} nao possui interfaces"
                )
            posicao = bruto.get("posicao")
            self.dispositivos[nome] = DescricaoDispositivo(
                nome=nome,
                tipo=tipo,
                interfaces=tuple(interfaces),
                gateway=bruto.get("gateway"),
                posicao=tuple(posicao) if posicao else None,
            )

    @staticmethod
    def _exigir(bruto: dict, chave: str, contexto: str) -> str:
        valor = bruto.get(chave)
        if not valor:
            raise ErroDeTopologiaError(
                f"campo obrigatorio ausente: '{chave}' em {contexto}"
            )
        return str(valor)

    def _validar(self) -> None:
        logicos: Dict[str, str] = {}
        fisicos: Dict[str, str] = {}
        for interface in self.todas_interfaces():
            if interface.logico in logicos:
                raise ErroDeTopologiaError(
                    f"endereco logico repetido: {interface.logico} em "
                    f"{logicos[interface.logico]} e {interface.identificador}"
                )
            if interface.fisico in fisicos:
                raise ErroDeTopologiaError(
                    f"endereco fisico repetido: {interface.fisico} em "
                    f"{fisicos[interface.fisico]} e {interface.identificador}"
                )
            try:
                ipaddress.ip_address(interface.logico)
            except ValueError as erro:
                raise ErroDeTopologiaError(
                    f"endereco logico invalido em {interface.identificador}: {erro}"
                ) from erro
            logicos[interface.logico] = interface.identificador
            fisicos[interface.fisico] = interface.identificador
            self._interfaces_por_logico[interface.logico] = interface

        for computador in self.computadores():
            descricao = self.dispositivos[computador]
            if (
                descricao.gateway
                and descricao.gateway not in self._interfaces_por_logico
            ):
                raise ErroDeTopologiaError(
                    f"o gateway {descricao.gateway} de {computador} nao corresponde "
                    f"a nenhuma interface da topologia"
                )

        vazios = [s.nome for s in self.segmentos.values() if not s.interfaces]
        if vazios:
            raise ErroDeTopologiaError(
                f"redes sem interfaces associadas: {', '.join(vazios)}"
            )

    # -- consultas basicas -------------------------------------------------

    def todas_interfaces(self) -> List[Interface]:
        return [i for d in self.dispositivos.values() for i in d.interfaces]

    def computadores(self) -> List[str]:
        return [n for n, d in self.dispositivos.items() if d.tipo == "computador"]

    def roteadores(self) -> List[str]:
        return [n for n, d in self.dispositivos.items() if d.tipo == "roteador"]

    def interfaces_de(self, dispositivo: str) -> Tuple[Interface, ...]:
        if dispositivo not in self.dispositivos:
            raise ErroDeTopologiaError(f"dispositivo desconhecido: {dispositivo}")
        return self.dispositivos[dispositivo].interfaces

    def interface_por_logico(self, logico: str) -> Optional[Interface]:
        return self._interfaces_por_logico.get(logico)

    def interface_por_nome(self, dispositivo: str, nome: str) -> Interface:
        for interface in self.interfaces_de(dispositivo):
            if interface.nome == nome:
                return interface
        raise ErroDeTopologiaError(f"interface {nome} nao existe em {dispositivo}")

    def gateway_de(self, computador: str) -> Optional[str]:
        return self.dispositivos[computador].gateway

    def prefixo_de(self, logico: str, mascara: int) -> str:
        return str(ipaddress.ip_network(f"{logico}/{mascara}", strict=False))

    def mesmo_prefixo(self, origem: Interface, destino_logico: str) -> bool:
        """Indica se o destino pertence a rede da interface de origem."""
        try:
            rede = ipaddress.ip_network(
                f"{origem.logico}/{origem.mascara}", strict=False
            )
            return ipaddress.ip_address(destino_logico) in rede
        except ValueError:
            return False

    def endereco_valido(self, logico: str) -> bool:
        try:
            ipaddress.ip_address(logico)
            return True
        except ValueError:
            return False

    # -- vizinhanca de enlace ---------------------------------------------

    def vizinhos_de_enlace(self, interface: Interface) -> List[Interface]:
        """Interfaces alcancaveis diretamente a partir de ``interface``."""
        segmento = self.segmentos[interface.rede]
        if not segmento.ativo:
            return []
        return [
            i for i in segmento.interfaces if i.identificador != interface.identificador
        ]

    def resolver_fisico(self, interface: Interface, logico: str) -> Optional[str]:
        """Traduz um endereco logico vizinho no endereco fisico correspondente.

        Equivale a consulta de uma tabela de resolucao de enderecos, restrita
        ao segmento ao qual a interface pertence.
        """
        for vizinha in self.vizinhos_de_enlace(interface):
            if vizinha.logico == logico:
                return vizinha.fisico
        return None

    def interface_vizinha(
        self, interface: Interface, logico: str
    ) -> Optional[Interface]:
        for vizinha in self.vizinhos_de_enlace(interface):
            if vizinha.logico == logico:
                return vizinha
        return None

    def nome_enlace(self, origem: str, destino: str) -> str:
        return f"{origem}-{destino}"

    # -- falhas ------------------------------------------------------------

    def enlaces_derrubaveis(self) -> List[str]:
        """Segmentos que podem ser derrubados pela interface do simulador."""
        return sorted(self.segmentos)

    def rotulo_enlace(self, segmento: str) -> str:
        membros = self.segmentos[segmento].dispositivos
        return f"{segmento} ({', '.join(sorted(set(membros)))})"

    def derrubar(self, segmento: str) -> None:
        if segmento not in self.segmentos:
            raise ErroDeTopologiaError(f"segmento desconhecido: {segmento}")
        self.segmentos[segmento].ativo = False
        self._cache_tabelas.clear()

    def restaurar(self, segmento: str) -> None:
        if segmento not in self.segmentos:
            raise ErroDeTopologiaError(f"segmento desconhecido: {segmento}")
        self.segmentos[segmento].ativo = True
        self._cache_tabelas.clear()

    def restaurar_todos(self) -> None:
        for segmento in self.segmentos.values():
            segmento.ativo = True
        self._cache_tabelas.clear()

    def ativo(self, segmento: str) -> bool:
        return self.segmentos[segmento].ativo

    # -- encaminhamento ----------------------------------------------------

    def _grafo_de_roteadores(self) -> Dict[str, List[Tuple[str, int, str]]]:
        """Monta o grafo entre roteadores: vizinho, custo e interface de saida."""
        grafo: Dict[str, List[Tuple[str, int, str]]] = {
            r: [] for r in self.roteadores()
        }
        for segmento in self.segmentos.values():
            if not segmento.ativo:
                continue
            roteadores = [
                i
                for i in segmento.interfaces
                if self.dispositivos[i.dispositivo].tipo == "roteador"
            ]
            for local in roteadores:
                for remota in roteadores:
                    if local.dispositivo == remota.dispositivo:
                        continue
                    grafo[local.dispositivo].append(
                        (remota.dispositivo, segmento.custo, local.nome)
                    )
        return grafo

    def _dijkstra(
        self, origem: str
    ) -> Dict[str, Tuple[int, Optional[str], Optional[str]]]:
        """Menor custo de ``origem`` a cada roteador.

        :returns: mapa roteador -> (custo, proximo salto, interface de saida).
            O desempate entre caminhos de mesmo custo usa o nome do proximo
            salto em ordem alfabetica, o que torna a escolha deterministica.
        """
        grafo = self._grafo_de_roteadores()
        melhor: Dict[str, Tuple[int, Optional[str], Optional[str]]] = {
            origem: (0, None, None)
        }
        fila: List[Tuple[int, str, str, Optional[str], Optional[str]]] = [
            (0, "", origem, None, None)
        ]
        visitados = set()
        while fila:
            custo, _, atual, salto, interface = heapq.heappop(fila)
            if atual in visitados:
                continue
            visitados.add(atual)
            for vizinho, peso, interface_saida in sorted(grafo.get(atual, [])):
                if vizinho in visitados:
                    continue
                novo_custo = custo + peso
                novo_salto = vizinho if atual == origem else salto
                nova_interface = interface_saida if atual == origem else interface
                candidato = (novo_custo, novo_salto or "")
                conhecido = melhor.get(vizinho)
                if conhecido is None or candidato < (conhecido[0], conhecido[1] or ""):
                    melhor[vizinho] = (novo_custo, novo_salto, nova_interface)
                    heapq.heappush(
                        fila,
                        (
                            novo_custo,
                            novo_salto or "",
                            vizinho,
                            novo_salto,
                            nova_interface,
                        ),
                    )
        return melhor

    def tabela_encaminhamento(self, roteador: str) -> List[Rota]:
        """Tabela de encaminhamento do roteador, derivada dos custos da topologia.

        Cada rede da topologia vira uma linha: redes conectadas diretamente
        aparecem com custo zero e sem proximo salto; as demais apontam o
        vizinho de menor custo.
        """
        if roteador in self._cache_tabelas:
            return self._cache_tabelas[roteador]
        if self.dispositivos[roteador].tipo != "roteador":
            raise ErroDeTopologiaError(f"{roteador} nao e um roteador")

        distancias = self._dijkstra(roteador)
        conectadas = {i.rede: i for i in self.interfaces_de(roteador)}
        rotas: List[Rota] = []

        for segmento in self.segmentos.values():
            if segmento.nome in conectadas:
                if not segmento.ativo:
                    continue
                interface = conectadas[segmento.nome]
                rotas.append(
                    Rota(segmento.prefixo, None, segmento.custo, interface.nome)
                )
                continue
            if not segmento.ativo:
                continue
            melhor: Optional[Tuple[int, str, str]] = None
            for interface in segmento.interfaces:
                dono = interface.dispositivo
                if self.dispositivos[dono].tipo != "roteador" or dono == roteador:
                    continue
                if dono not in distancias:
                    continue
                custo_ate_dono, salto, interface_saida = distancias[dono]
                if salto is None or interface_saida is None:
                    continue
                ip_salto = self._logico_do_salto(roteador, interface_saida, salto)
                if ip_salto is None:
                    continue
                candidato = (custo_ate_dono + segmento.custo, ip_salto, interface_saida)
                if melhor is None or (candidato[0], candidato[1]) < (
                    melhor[0],
                    melhor[1],
                ):
                    melhor = candidato
            if melhor is not None:
                rotas.append(Rota(segmento.prefixo, melhor[1], melhor[0], melhor[2]))

        rotas.sort(
            key=lambda r: (ipaddress.ip_network(r.destino).network_address, r.destino)
        )
        self._cache_tabelas[roteador] = rotas
        return rotas

    def _logico_do_salto(
        self, roteador: str, interface_saida: str, salto: str
    ) -> Optional[str]:
        """Endereco logico do vizinho ``salto`` alcancado por ``interface_saida``."""
        interface = self.interface_por_nome(roteador, interface_saida)
        for vizinha in self.vizinhos_de_enlace(interface):
            if vizinha.dispositivo == salto:
                return vizinha.logico
        return None

    def consultar(self, roteador: str, destino_logico: str) -> Optional[Rota]:
        """Procura a rota mais especifica para o endereco de destino."""
        if not self.endereco_valido(destino_logico):
            return None
        alvo = ipaddress.ip_address(destino_logico)
        escolhida: Optional[Rota] = None
        for rota in self.tabela_encaminhamento(roteador):
            rede = ipaddress.ip_network(rota.destino)
            if alvo in rede:
                if (
                    escolhida is None
                    or rede.prefixlen
                    > ipaddress.ip_network(escolhida.destino).prefixlen
                ):
                    escolhida = rota
        return escolhida

    # -- apoio a visualizacao ---------------------------------------------

    def ligacoes_visuais(self) -> List[dict]:
        """Descreve os tracos do mapa: segmentos com seus membros e custos."""
        ligacoes = []
        for segmento in self.segmentos.values():
            ligacoes.append(
                {
                    "segmento": segmento.nome,
                    "prefixo": segmento.prefixo,
                    "custo": segmento.custo,
                    "tipo": segmento.tipo,
                    "ativo": segmento.ativo,
                    "posicao": segmento.posicao,
                    "membros": [
                        {"dispositivo": i.dispositivo, "interface": i.nome}
                        for i in segmento.interfaces
                    ],
                }
            )
        return ligacoes

    def posicoes(self) -> Dict[str, Tuple[float, float]]:
        """Posicoes relativas dos dispositivos, com disposicao automatica de reserva."""
        posicoes: Dict[str, Tuple[float, float]] = {}
        sem_posicao = []
        for nome, descricao in self.dispositivos.items():
            if descricao.posicao:
                posicoes[nome] = descricao.posicao
            else:
                sem_posicao.append(nome)
        if sem_posicao:
            import math

            total = len(sem_posicao)
            for indice, nome in enumerate(sorted(sem_posicao)):
                angulo = 2 * math.pi * indice / total
                posicoes[nome] = (
                    0.5 + 0.38 * math.cos(angulo),
                    0.5 + 0.38 * math.sin(angulo),
                )
        return posicoes
