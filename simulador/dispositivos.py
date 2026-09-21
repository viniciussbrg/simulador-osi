"""Computador e roteador, e a pilha de camadas de cada um.

O computador monta as sete camadas; o roteador monta apenas as tres primeiras.
E essa diferenca de construcao que garante a restricao R1 do enunciado: o
objeto que representa o roteador nao possui nenhuma referencia as camadas 4 a
7, de modo que nao ha caminho de codigo capaz de alcancar uma porta ou o nome
de um processo.

O dispositivo tambem oferece as camadas os servicos que nao pertencem a
nenhuma delas: a consulta a tabela de encaminhamento, a traducao de um
endereco logico vizinho em endereco fisico e os contadores de quadro, pacote e
sessao.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .camadas import CAMADAS_COMPUTADOR, CAMADAS_ROTEADOR, Camada
from .rede import Interface, Topologia


class ServicosDaSimulacao:
    """Contadores compartilhados por todos os dispositivos de uma simulacao.

    Os identificadores de quadro, pacote e sessao precisam ser unicos em toda a
    rede para que o registro permaneca legivel quando dois fluxos convivem, como
    no caso C3.
    """

    def __init__(self) -> None:
        self._quadros = 0
        self._pacotes = 0
        self._sessoes = 0

    def proximo_quadro(self) -> int:
        self._quadros += 1
        return self._quadros

    def proximo_pacote(self) -> str:
        self._pacotes += 1
        return f"P{self._pacotes}"

    def proxima_sessao(self) -> str:
        self._sessoes += 1
        return f"S-{self._sessoes:04d}"

    def reiniciar(self) -> None:
        self._quadros = self._pacotes = self._sessoes = 0


@dataclass(frozen=True)
class DecisaoEncaminhamento:
    """Resultado da consulta de rota, devolvido a camada 3."""

    proximo_salto: str
    interface: Interface
    custo: int
    descricao: str


class Pilha:
    """A pilha de camadas de um dispositivo, ligada apenas por adjacencia."""

    def __init__(
        self, dispositivo: "Dispositivo", construtores: Tuple[type, ...]
    ) -> None:
        self._camadas: Dict[int, Camada] = {}
        anteriores: List[Camada] = []
        for construtor in construtores:
            camada = construtor(dispositivo)
            self._camadas[camada.numero] = camada
            if anteriores:
                anteriores[-1].ligar_abaixo(camada)
                camada.ligar_acima(anteriores[-1])
            anteriores.append(camada)
        self._ordem = [c.numero for c in anteriores]

    @property
    def topo(self) -> Camada:
        return self._camadas[self._ordem[0]]

    @property
    def base(self) -> Camada:
        return self._camadas[self._ordem[-1]]

    @property
    def numeros(self) -> List[int]:
        """Numeros das camadas, do topo para a base."""
        return list(self._ordem)

    def camada(self, numero: int) -> Camada:
        if numero not in self._camadas:
            raise KeyError(f"este dispositivo nao implementa a camada {numero}")
        return self._camadas[numero]

    def __contains__(self, numero: int) -> bool:
        return numero in self._camadas

    def __len__(self) -> int:
        return len(self._camadas)


class Dispositivo:
    """Base comum a computadores e roteadores."""

    encaminha = False

    def __init__(
        self, nome: str, topologia: Topologia, servicos: ServicosDaSimulacao
    ) -> None:
        self.nome = nome
        self.topologia = topologia
        self.servicos = servicos
        self.descricao = topologia.dispositivos[nome]
        self.pilha = Pilha(self, self._construtores())

    def _construtores(self) -> Tuple[type, ...]:
        raise NotImplementedError

    # -- interfaces --------------------------------------------------------

    @property
    def interfaces(self) -> Tuple[Interface, ...]:
        return self.descricao.interfaces

    def interface(self, nome: str) -> Interface:
        return self.topologia.interface_por_nome(self.nome, nome)

    def possui_endereco(self, logico: str) -> bool:
        return any(i.logico == logico for i in self.interfaces)

    def resolver_fisico(self, interface: Interface, logico: str) -> Optional[str]:
        return self.topologia.resolver_fisico(interface, logico)

    def interface_vizinha(
        self, interface: Interface, logico: str
    ) -> Optional[Interface]:
        return self.topologia.interface_vizinha(interface, logico)

    # -- encaminhamento ----------------------------------------------------

    def decidir_encaminhamento(self, destino: str) -> Optional[DecisaoEncaminhamento]:
        raise NotImplementedError

    @property
    def numero_de_camadas(self) -> int:
        return len(self.pilha)

    def __repr__(self) -> str:  # pragma: no cover - apoio a depuracao
        return f"<{type(self).__name__} {self.nome}>"


class Computador(Dispositivo):
    """Dispositivo de extremidade, com as sete camadas."""

    encaminha = False

    def _construtores(self) -> Tuple[type, ...]:
        return CAMADAS_COMPUTADOR

    @property
    def interface_padrao(self) -> Interface:
        return self.interfaces[0]

    @property
    def endereco_logico(self) -> str:
        return self.interface_padrao.logico

    @property
    def gateway(self) -> Optional[str]:
        return self.descricao.gateway

    def decidir_encaminhamento(self, destino: str) -> Optional[DecisaoEncaminhamento]:
        """Entrega direta quando o destino compartilha o prefixo; senao, gateway."""
        interface = self.interface_padrao
        if not self.topologia.endereco_valido(destino):
            return None
        if self.topologia.mesmo_prefixo(interface, destino):
            if self.topologia.resolver_fisico(interface, destino) is None:
                return None
            return DecisaoEncaminhamento(
                proximo_salto=destino,
                interface=interface,
                custo=0,
                descricao=(
                    f"destino {destino} na mesma rede {interface.prefixo}, "
                    f"entrega direta pela interface {interface.nome}"
                ),
            )
        if not self.gateway:
            return None
        if self.topologia.resolver_fisico(interface, self.gateway) is None:
            return None
        return DecisaoEncaminhamento(
            proximo_salto=self.gateway,
            interface=interface,
            custo=0,
            descricao=(
                f"destino {destino} fora da rede local, próximo salto "
                f"{self.gateway} pela interface {interface.nome}"
            ),
        )


class Roteador(Dispositivo):
    """Dispositivo intermediario, com apenas as camadas 1 a 3."""

    encaminha = True

    def _construtores(self) -> Tuple[type, ...]:
        return CAMADAS_ROTEADOR

    @property
    def tabela(self):
        return self.topologia.tabela_encaminhamento(self.nome)

    def decidir_encaminhamento(self, destino: str) -> Optional[DecisaoEncaminhamento]:
        rota = self.topologia.consultar(self.nome, destino)
        if rota is None:
            return None
        interface = self.interface(rota.interface)
        if rota.direta:
            if self.topologia.resolver_fisico(interface, destino) is None:
                return None
            return DecisaoEncaminhamento(
                proximo_salto=destino,
                interface=interface,
                custo=rota.custo,
                descricao=(
                    f"{rota.destino} conectada diretamente, entrega direta a "
                    f"{destino}, interface {interface.nome}"
                ),
            )
        vizinha = self.topologia.interface_vizinha(interface, rota.proximo_salto)
        if vizinha is None:
            return None
        return DecisaoEncaminhamento(
            proximo_salto=rota.proximo_salto,
            interface=interface,
            custo=rota.custo,
            descricao=(
                f"{rota.destino} via {vizinha.dispositivo}, custo {rota.custo}, "
                f"interface {interface.nome}"
            ),
        )


def construir_dispositivos(
    topologia: Topologia, servicos: ServicosDaSimulacao
) -> Dict[str, Dispositivo]:
    """Instancia todos os dispositivos descritos na topologia."""
    dispositivos: Dict[str, Dispositivo] = {}
    for nome, descricao in topologia.dispositivos.items():
        classe = Computador if descricao.tipo == "computador" else Roteador
        dispositivos[nome] = classe(nome, topologia, servicos)
    return dispositivos
