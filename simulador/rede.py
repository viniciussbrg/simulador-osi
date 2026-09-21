# -*- coding: utf-8 -*-
"""Topologia, enlaces e tabelas de encaminhamento.

A rede vem de um JSON externo; trocar o arquivo troca a rede simulada.

Um segmento e um dominio de enlace: dois membros do mesmo segmento trocam
quadros diretamente. Redes locais custam 0 e os enlaces entre roteadores
carregam o custo declarado, que e a metrica do menor caminho.
"""

from __future__ import annotations

import heapq
import json
import re
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network
from typing import Any

from . import config
from .pdu import bits_do_prefixo, ip_valido, pertence_ao_prefixo

ROTA_PADRAO = "0.0.0.0/0"


# Estruturas de dados


@dataclass
class Interface:
    """Uma interface de rede de um dispositivo."""

    nome: str
    logico: str          # endereco logico (IP)
    fisico: str          # endereco fisico (MAC)
    descricao: str = ""


@dataclass
class Dispositivo:
    """Um computador ou um roteador da topologia."""

    nome: str
    tipo: str            # "computador" ou "roteador"
    rotulo: str = ""
    posicao: tuple[float, float] = (0.5, 0.5)
    gateway: str = ""    # endereco logico do roteador padrao (so computadores)
    interfaces: list[Interface] = field(default_factory=list)

    def interface_por_nome(self, nome: str) -> Interface | None:
        for interface in self.interfaces:
            if interface.nome == nome:
                return interface
        return None

    def possui_ip(self, ip: str) -> bool:
        return any(interface.logico == ip for interface in self.interfaces)

    @property
    def ip_principal(self) -> str:
        return self.interfaces[0].logico if self.interfaces else ""

    @property
    def numero_camadas(self) -> int:
        """Computadores implementam sete camadas; roteadores, apenas tres."""
        return 7 if self.tipo == "computador" else 3


@dataclass
class Segmento:
    """Um dominio de enlace: rede local ou enlace ponto a ponto."""

    id: str
    rotulo: str
    prefixo: str         # CIDR, por exemplo "10.0.1.0/24"
    tipo: str            # "lan" ou "ponto_a_ponto"
    custo: int
    membros: list[tuple[str, str]] = field(default_factory=list)
    ativo: bool = True   # falso quando o enlace foi derrubado pela interface
    # Posicao normalizada do ponto de concentracao da rede local no mapa.
    # Quando ausente, a interface usa o centro geometrico dos membros.
    posicao: tuple[float, float] | None = None

    def contem(self, dispositivo: str) -> bool:
        return any(nome == dispositivo for nome, _ in self.membros)

    def interface_de(self, dispositivo: str) -> str | None:
        for nome, interface in self.membros:
            if nome == dispositivo:
                return interface
        return None


@dataclass
class EntradaRota:
    """Uma linha da tabela de encaminhamento de um dispositivo."""

    destino_prefixo: str
    tipo: str                # "direto" ou "remoto"
    proximo_salto: str       # endereco logico do proximo salto ("-" se direto)
    interface_saida: str
    custo: int
    via: str = "direto"      # nome do proximo dispositivo, para exibicao

    def como_linha(self) -> tuple[str, str, str, str, str]:
        """Devolve a entrada como tupla de texto, para a tabela da interface."""
        return (
            self.destino_prefixo,
            self.proximo_salto,
            self.interface_saida,
            str(self.custo),
            self.via,
        )


class ErroTopologia(Exception):
    """Levantada quando o arquivo de topologia esta ausente ou malformado."""


# Topologia


class Topologia:
    """Rede simulada: dispositivos, segmentos, processos e rotas."""

    def __init__(self, caminho_json: str | None = None) -> None:
        self.caminho: str = caminho_json or config.caminho_no_projeto(
            config.ARQUIVO_TOPOLOGIA_PADRAO
        )
        self.nome: str = ""
        self.descricao: str = ""
        self.dispositivos: dict[str, Dispositivo] = {}
        self.segmentos: list[Segmento] = []
        self.processos: dict[str, int] = {}
        self.processos_por_porta: dict[int, str] = {}
        self.carregar(self.caminho)

    # carregamento

    def carregar(self, caminho: str) -> None:
        """Le o arquivo JSON e reconstroi as estruturas internas.

        Levanta `ErroTopologia` com uma mensagem legivel em vez de deixar
        escapar uma excecao crua: a interface mostra essa mensagem ao usuario
        sem fechar a janela.
        """
        try:
            # "utf-8-sig" aceita tanto UTF-8 puro quanto UTF-8 com marca de
            # ordem de octetos, que varios editores do Windows acrescentam ao
            # salvar. Sem isso, trocar a topologia em um editor comum
            # quebraria a leitura.
            with open(caminho, "r", encoding="utf-8-sig") as arquivo:
                dados = json.load(arquivo)
        except FileNotFoundError:
            raise ErroTopologia(
                f"Arquivo de topologia nao encontrado:\n{caminho}\n\n"
                "Coloque um arquivo topologia.json ao lado do programa."
            ) from None
        except json.JSONDecodeError as erro:
            raise ErroTopologia(
                f"O arquivo de topologia nao e um JSON valido:\n{caminho}\n\n{erro}"
            ) from None

        try:
            self._montar(dados)
        except (KeyError, TypeError, ValueError) as erro:
            raise ErroTopologia(
                f"Topologia invalida em {caminho}:\n{erro}"
            ) from None

        self.caminho = caminho
        self._validar()

    def _montar(self, dados: dict[str, Any]) -> None:
        self.nome = dados.get("nome", "Rede simulada")
        self.descricao = dados.get("descricao", "")

        self.dispositivos = {}
        for bruto in dados["dispositivos"]:
            interfaces = [
                Interface(
                    nome=item["nome"],
                    logico=item["logico"],
                    fisico=item["fisico"],
                    descricao=item.get("descricao", ""),
                )
                for item in bruto.get("interfaces", [])
            ]
            posicao = bruto.get("posicao", [0.5, 0.5])
            dispositivo = Dispositivo(
                nome=bruto["nome"],
                tipo=bruto["tipo"],
                rotulo=bruto.get("rotulo", bruto["nome"]),
                posicao=(float(posicao[0]), float(posicao[1])),
                gateway=bruto.get("gateway", ""),
                interfaces=interfaces,
            )
            self.dispositivos[dispositivo.nome] = dispositivo

        self.segmentos = []
        for bruto in dados["segmentos"]:
            posicao = bruto.get("posicao")
            self.segmentos.append(Segmento(
                id=bruto["id"],
                rotulo=bruto.get("rotulo", bruto["id"]),
                prefixo=bruto["prefixo"],
                tipo=bruto["tipo"],
                custo=int(bruto["custo"]),
                membros=[(m["dispositivo"], m["interface"]) for m in bruto["membros"]],
                posicao=(float(posicao[0]), float(posicao[1])) if posicao else None,
            ))

        self.processos = {}
        self.processos_por_porta = {}
        for bruto in dados.get("processos", []):
            self.processos[bruto["nome"]] = int(bruto["porta"])
            self.processos_por_porta[int(bruto["porta"])] = bruto["nome"]

    def _validar(self) -> None:
        """Confere a coerencia estrutural e semantica da topologia."""
        if not self.dispositivos:
            raise ErroTopologia("A topologia nao declara nenhum dispositivo.")
        if not self.segmentos:
            raise ErroTopologia("A topologia nao declara nenhum segmento.")

        interfaces: set[tuple[str, str]] = set()
        ips: dict[str, str] = {}
        macs: dict[str, str] = {}

        for dispositivo in self.dispositivos.values():
            if dispositivo.tipo not in ("computador", "roteador"):
                raise ErroTopologia(
                    f"Dispositivo {dispositivo.nome}: tipo desconhecido "
                    f"{dispositivo.tipo!r} (use 'computador' ou 'roteador')."
                )
            if not dispositivo.interfaces:
                raise ErroTopologia(
                    f"Dispositivo {dispositivo.nome}: nenhuma interface foi declarada."
                )
            x, y = dispositivo.posicao
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ErroTopologia(
                    f"Dispositivo {dispositivo.nome}: posicao fora do intervalo [0, 1]."
                )

            nomes_locais: set[str] = set()
            for item in dispositivo.interfaces:
                chave = (dispositivo.nome, item.nome)
                if not item.nome.strip() or item.nome in nomes_locais:
                    raise ErroTopologia(
                        f"Dispositivo {dispositivo.nome}: nome de interface vazio ou duplicado."
                    )
                nomes_locais.add(item.nome)
                interfaces.add(chave)

                if not ip_valido(item.logico):
                    raise ErroTopologia(
                        f"Endereco logico invalido em {dispositivo.nome}/{item.nome}: "
                        f"{item.logico!r}"
                    )
                if item.logico in ips:
                    raise ErroTopologia(
                        f"Endereco logico duplicado: {item.logico} em "
                        f"{ips[item.logico]} e {dispositivo.nome}/{item.nome}."
                    )
                ips[item.logico] = f"{dispositivo.nome}/{item.nome}"

                if not re.fullmatch(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}", item.fisico):
                    raise ErroTopologia(
                        f"Endereco fisico invalido em {dispositivo.nome}/{item.nome}: "
                        f"{item.fisico!r}. Use o formato MAC xx:xx:xx:xx:xx:xx."
                    )
                mac = item.fisico.upper()
                if mac in macs:
                    raise ErroTopologia(
                        f"Endereco fisico duplicado: {item.fisico} em "
                        f"{macs[mac]} e {dispositivo.nome}/{item.nome}."
                    )
                macs[mac] = f"{dispositivo.nome}/{item.nome}"

            if dispositivo.tipo == "computador":
                if not dispositivo.gateway or not ip_valido(dispositivo.gateway):
                    raise ErroTopologia(
                        f"Computador {dispositivo.nome}: gateway invalido "
                        f"{dispositivo.gateway!r}."
                    )

        interfaces_segmentos: dict[tuple[str, str], str] = {}
        prefixos: set[str] = set()
        for segmento in self.segmentos:
            if not segmento.id.strip():
                raise ErroTopologia("Existe um segmento sem identificador.")
            if segmento.tipo not in ("lan", "ponto_a_ponto"):
                raise ErroTopologia(
                    f"Segmento {segmento.id}: tipo invalido {segmento.tipo!r}."
                )
            if segmento.custo < 0:
                raise ErroTopologia(
                    f"Segmento {segmento.id}: custo nao pode ser negativo."
                )
            try:
                rede = IPv4Network(segmento.prefixo, strict=False)
            except ValueError:
                raise ErroTopologia(
                    f"Segmento {segmento.id}: prefixo invalido {segmento.prefixo!r}."
                ) from None
            prefixo = str(rede)
            if prefixo in prefixos:
                raise ErroTopologia(
                    f"Prefixo de rede duplicado: {prefixo}."
                )
            prefixos.add(prefixo)

            if segmento.tipo == "ponto_a_ponto" and len(segmento.membros) != 2:
                raise ErroTopologia(
                    f"Segmento {segmento.id}: enlace ponto a ponto deve ter dois membros."
                )
            if segmento.tipo == "lan" and len(segmento.membros) < 2:
                raise ErroTopologia(
                    f"Segmento {segmento.id}: uma LAN deve ter pelo menos dois membros."
                )
            if segmento.posicao is not None:
                x, y = segmento.posicao
                if not (0 <= x <= 1 and 0 <= y <= 1):
                    raise ErroTopologia(
                        f"Segmento {segmento.id}: posicao fora do intervalo [0, 1]."
                    )

            membros: set[tuple[str, str]] = set()
            for nome, nome_interface in segmento.membros:
                chave = (nome, nome_interface)
                if chave in membros:
                    raise ErroTopologia(
                        f"Segmento {segmento.id}: membro duplicado {nome}/{nome_interface}."
                    )
                membros.add(chave)
                dispositivo = self.dispositivos.get(nome)
                if dispositivo is None:
                    raise ErroTopologia(
                        f"Segmento {segmento.id} cita o dispositivo inexistente {nome!r}."
                    )
                item = dispositivo.interface_por_nome(nome_interface)
                if item is None:
                    raise ErroTopologia(
                        f"Segmento {segmento.id}: o dispositivo {nome} nao tem "
                        f"a interface {nome_interface!r}."
                    )
                if chave in interfaces_segmentos:
                    raise ErroTopologia(
                        f"Interface {nome}/{nome_interface} pertence aos segmentos "
                        f"{interfaces_segmentos[chave]} e {segmento.id}."
                    )
                interfaces_segmentos[chave] = segmento.id
                if IPv4Address(item.logico) not in rede:
                    raise ErroTopologia(
                        f"Interface {nome}/{nome_interface}: endereco {item.logico} "
                        f"nao pertence ao prefixo {segmento.prefixo}."
                    )

        for chave in interfaces:
            if chave not in interfaces_segmentos:
                raise ErroTopologia(
                    f"Interface {chave[0]}/{chave[1]} nao pertence a nenhum segmento."
                )

        for dispositivo in self.dispositivos.values():
            if dispositivo.tipo != "computador":
                continue
            gateway = self.dispositivo_por_ip(dispositivo.gateway)
            if gateway is None or gateway.tipo != "roteador":
                raise ErroTopologia(
                    f"Computador {dispositivo.nome}: gateway {dispositivo.gateway} "
                    "nao existe ou nao pertence a um roteador."
                )
            if not any(
                (segmento := self.segmento_ativo_de(dispositivo.nome, item.nome))
                and segmento.contem(gateway.nome)
                for item in dispositivo.interfaces
            ):
                raise ErroTopologia(
                    f"Computador {dispositivo.nome}: gateway {dispositivo.gateway} "
                    "nao esta em uma rede diretamente conectada."
                )

        if len(self.processos) != len(self.processos_por_porta):
            raise ErroTopologia("Existem processos ou portas duplicados.")
        for nome, porta in self.processos.items():
            if not nome.strip() or not (1 <= porta <= 65535):
                raise ErroTopologia(
                    f"Processo {nome!r}: nome ou porta invalida ({porta})."
                )

    # consultas basicas

    def computadores(self) -> list[str]:
        return [d.nome for d in self.dispositivos.values() if d.tipo == "computador"]

    def roteadores(self) -> list[str]:
        return [d.nome for d in self.dispositivos.values() if d.tipo == "roteador"]

    def segmento_por_id(self, identificador: str) -> Segmento | None:
        for segmento in self.segmentos:
            if segmento.id == identificador:
                return segmento
        return None

    def segmento_ativo_de(self, dispositivo: str, interface: str) -> Segmento | None:
        """Segmento ativo a que pertence uma interface de um dispositivo."""
        for segmento in self.segmentos:
            if not segmento.ativo:
                continue
            if (dispositivo, interface) in segmento.membros:
                return segmento
        return None

    def segmento_entre(self, um: str, outro: str) -> Segmento | None:
        """Segmento ativo que liga dois dispositivos, se houver."""
        for segmento in self.segmentos:
            if segmento.ativo and segmento.contem(um) and segmento.contem(outro):
                return segmento
        return None

    def dispositivo_por_ip(self, ip: str) -> Dispositivo | None:
        for dispositivo in self.dispositivos.values():
            if dispositivo.possui_ip(ip):
                return dispositivo
        return None

    def resolver_fisico(self, ip: str, segmento: Segmento) -> str | None:
        """Descobre o endereco fisico associado a um endereco logico.

        Equivale a uma consulta ARP simplificada, restrita ao segmento: so
        resolve o endereco de quem compartilha o mesmo dominio de enlace.
        """
        for nome, nome_interface in segmento.membros:
            dispositivo = self.dispositivos.get(nome)
            if dispositivo is None:
                continue
            interface = dispositivo.interface_por_nome(nome_interface)
            if interface is not None and interface.logico == ip:
                return interface.fisico
        return None

    def porta_do_processo(self, nome: str) -> int | None:
        return self.processos.get(nome)

    def processo_da_porta(self, porta: int) -> str | None:
        return self.processos_por_porta.get(porta)

    # estado dos enlaces

    def enlaces_comutaveis(self) -> list[Segmento]:
        """Segmentos que a interface permite derrubar ou restaurar."""
        return list(self.segmentos)

    def definir_estado_enlace(self, identificador: str, ativo: bool) -> None:
        segmento = self.segmento_por_id(identificador)
        if segmento is not None:
            segmento.ativo = ativo

    def restaurar_enlaces(self) -> None:
        for segmento in self.segmentos:
            segmento.ativo = True

    def enlaces_derrubados(self) -> list[str]:
        return [s.id for s in self.segmentos if not s.ativo]

    # encaminhamento

    def _grafo_roteadores(self) -> dict[str, list[tuple[str, int]]]:
        """Grafo de adjacencia entre roteadores sobre os segmentos ativos."""
        grafo: dict[str, list[tuple[str, int]]] = {
            nome: [] for nome in self.roteadores()
        }
        for segmento in self.segmentos:
            if not segmento.ativo:
                continue
            roteadores = [
                nome for nome, _ in segmento.membros
                if self.dispositivos[nome].tipo == "roteador"
            ]
            for um in roteadores:
                for outro in roteadores:
                    if um != outro:
                        grafo[um].append((outro, segmento.custo))
        return grafo

    def _distancias(self, origem: str) -> dict[str, tuple[int, str]]:
        """Dijkstra a partir de um roteador.

        Devolve {roteador: (custo, primeiro_salto)}. A chave da fila e a
        tripla (custo, primeiro_salto, no): o segundo campo faz o desempate
        entre caminhos de mesmo custo pela ordem lexicografica do nome do
        proximo salto, que e a convencao adotada no projeto.
        """
        grafo = self._grafo_roteadores()
        melhor: dict[str, tuple[int, str]] = {}
        fila: list[tuple[int, str, str]] = [(0, "", origem)]

        while fila:
            custo, primeiro, atual = heapq.heappop(fila)
            if atual in melhor:
                continue
            melhor[atual] = (custo, primeiro)
            for vizinho, peso in grafo.get(atual, []):
                if vizinho in melhor:
                    continue
                proximo_primeiro = vizinho if atual == origem else primeiro
                heapq.heappush(fila, (custo + peso, proximo_primeiro, vizinho))

        melhor.pop(origem, None)
        return melhor

    def tabela_encaminhamento(self, dispositivo: str) -> list[EntradaRota]:
        """Constroi a tabela de encaminhamento de um dispositivo.

        Computadores tem as redes diretamente conectadas e uma rota padrao
        pelo roteador configurado. Roteadores tem as redes diretamente
        conectadas e, para cada rede remota, a rota de menor custo obtida por
        Dijkstra sobre os enlaces ativos.
        """
        alvo = self.dispositivos.get(dispositivo)
        if alvo is None:
            return []

        tabela: list[EntradaRota] = []

        # Redes diretamente conectadas, comuns aos dois tipos de dispositivo.
        for segmento in self.segmentos:
            if not segmento.ativo or not segmento.contem(dispositivo):
                continue
            tabela.append(EntradaRota(
                destino_prefixo=segmento.prefixo,
                tipo="direto",
                proximo_salto="-",
                interface_saida=segmento.interface_de(dispositivo) or "",
                custo=0,
                via="direto",
            ))

        if alvo.tipo == "computador":
            if alvo.gateway:
                interface = self._interface_para_ip(alvo, alvo.gateway)
                tabela.append(EntradaRota(
                    destino_prefixo=ROTA_PADRAO,
                    tipo="remoto",
                    proximo_salto=alvo.gateway,
                    interface_saida=interface or (
                        alvo.interfaces[0].nome if alvo.interfaces else ""
                    ),
                    custo=0,
                    via="padrao",
                ))
            return tabela

        # Roteadores: uma entrada por rede remota alcancavel.
        distancias = self._distancias(dispositivo)
        conhecidos = {entrada.destino_prefixo for entrada in tabela}

        for segmento in self.segmentos:
            if not segmento.ativo or segmento.prefixo in conhecidos:
                continue
            candidatos: list[tuple[int, str]] = []
            for nome, _ in segmento.membros:
                if self.dispositivos[nome].tipo != "roteador":
                    continue
                if nome in distancias:
                    custo, primeiro = distancias[nome]
                    candidatos.append((custo, primeiro))
            if not candidatos:
                continue

            custo, primeiro = min(candidatos)
            saida = self.segmento_entre(dispositivo, primeiro)
            if saida is None:
                continue
            interface = saida.interface_de(dispositivo) or ""
            ip_proximo = self._ip_do_vizinho(primeiro, saida)
            tabela.append(EntradaRota(
                destino_prefixo=segmento.prefixo,
                tipo="remoto",
                proximo_salto=ip_proximo,
                interface_saida=interface,
                custo=custo,
                via=primeiro,
            ))
            conhecidos.add(segmento.prefixo)

        tabela.sort(key=lambda e: (-bits_do_prefixo(e.destino_prefixo),
                                   e.destino_prefixo))
        return tabela

    def consultar_rota(self, dispositivo: str, ip_destino: str) -> EntradaRota | None:
        """Escolhe a entrada de rota aplicavel a um endereco logico.

        O criterio e o prefixo mais longo que cobre o destino; em caso de
        empate de prefixo, o menor custo. Devolve `None` quando nenhuma
        entrada cobre o destino, que e o caso do cenario de destino
        inalcancavel.
        """
        melhor: EntradaRota | None = None
        for entrada in self.tabela_encaminhamento(dispositivo):
            if not pertence_ao_prefixo(ip_destino, entrada.destino_prefixo):
                continue
            if melhor is None:
                melhor = entrada
                continue
            bits_nova = bits_do_prefixo(entrada.destino_prefixo)
            bits_melhor = bits_do_prefixo(melhor.destino_prefixo)
            if (bits_nova, -entrada.custo) > (bits_melhor, -melhor.custo):
                melhor = entrada
        return melhor

    def caminho_previsto(self, origem: str, ip_destino: str) -> list[str] | None:
        """Percorre as tabelas e devolve a sequencia de dispositivos ate o destino.

        Serve para a interface antecipar o percurso ao carregar um cenario e
        para os testes automatizados. A simulacao propriamente dita nao usa
        este metodo: la cada roteador consulta a sua propria tabela no
        momento em que o pacote chega.
        """
        atual = origem
        caminho = [origem]
        visitados = {origem}

        while True:
            entrada = self.consultar_rota(atual, ip_destino)
            if entrada is None:
                return None
            if entrada.tipo == "direto":
                segmento = self.segmento_ativo_de(atual, entrada.interface_saida)
                if segmento is None:
                    return None
                destino = self.dispositivo_por_ip(ip_destino)
                if destino is None or not segmento.contem(destino.nome):
                    return None
                caminho.append(destino.nome)
                return caminho
            proximo = self.dispositivo_por_ip(entrada.proximo_salto)
            if proximo is None or proximo.nome in visitados:
                return None
            visitados.add(proximo.nome)
            caminho.append(proximo.nome)
            atual = proximo.nome

    # auxiliares

    def _interface_para_ip(self, dispositivo: Dispositivo, ip: str) -> str | None:
        """Interface do dispositivo que alcanca diretamente um endereco logico."""
        for interface in dispositivo.interfaces:
            segmento = self.segmento_ativo_de(dispositivo.nome, interface.nome)
            if segmento is not None and pertence_ao_prefixo(ip, segmento.prefixo):
                return interface.nome
        return None

    def _ip_do_vizinho(self, vizinho: str, segmento: Segmento) -> str:
        """Endereco logico do vizinho na interface que ele expoe no segmento."""
        nome_interface = segmento.interface_de(vizinho)
        dispositivo = self.dispositivos.get(vizinho)
        if dispositivo is None or nome_interface is None:
            return ""
        interface = dispositivo.interface_por_nome(nome_interface)
        return interface.logico if interface else ""
