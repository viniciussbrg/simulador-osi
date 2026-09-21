"""Dispositivos da rede: a pilha de camadas e o seu encadeamento.

As camadas nao se conhecem (camadas.py). Quem as poe em ordem e as percorre
e o dispositivo: descer() leva as unidades da camada mais alta ate a 1, e
subir() faz o caminho inverso. Cada dispositivo tem o seu Contexto, que e o
unico estado que as suas camadas compartilham.

Computador e roteador diferem apenas na lista de camadas. O roteador e
montado com [Rede, Enlace, Fisica]: nele nao existe objeto capaz de ler uma
porta ou o nome de um processo. A restricao R1 vale por construcao, e nao
pela disciplina de quem escreve o codigo.

Convencao de retorno: descer(), subir() e receber() devolvem, alem das
unidades que saem, a lista de passos (evento, unidade), em que a unidade e a
PDU que o evento descreve. O registro usa so o evento; a interface usa a
unidade para desenhar os blocos e os pares de enderecos de cada passo.
"""

from .camadas import (
    Aplicacao, Apresentacao, Contexto, Enlace, Fisica, Rede, Sessao, Transporte,
)
from .pdu import PDU


def _parear(eventos, saidas, recebida):
    """Associa cada evento de uma chamada de camada a unidade que ele descreve.

    Quando a camada devolve uma unidade por evento (a camada 4 ao segmentar),
    a correspondencia e um a um. Nos demais casos, todos os eventos descrevem
    a ultima unidade produzida, ou a recebida quando nada seguiu adiante
    (descarte, segmento aguardando os demais).
    """
    if len(saidas) == len(eventos):
        return list(zip(eventos, saidas))
    unidade = saidas[-1] if saidas else recebida
    return [(evento, unidade) for evento in eventos]


class Dispositivo:
    """Uma pilha de camadas, da mais alta para a mais baixa, e o seu contexto.

    Os contadores (passos, quadros, sessoes) sao repassados ao Contexto e
    devem ser os mesmos em todos os dispositivos de uma simulacao.
    """

    CAMADAS = ()

    def __init__(self, nome, topologia, **contadores):
        self.nome = nome
        self.contexto = Contexto(nome, topologia, **contadores)
        self.pilha = [classe() for classe in self.CAMADAS]

    @property
    def numeros_das_camadas(self):
        return [camada.numero for camada in self.pilha]

    def descer(self, unidades):
        """Leva as unidades da camada mais alta da pilha ate a camada 1."""
        return self._percorrer("descer", self.pilha, unidades)

    def subir(self, unidades):
        """Leva as unidades da camada 1 ate a camada mais alta da pilha."""
        return self._percorrer("subir", reversed(self.pilha), unidades)

    def _percorrer(self, sentido, camadas, unidades):
        passos = []
        for camada in camadas:
            saidas = []
            for unidade in unidades:
                novas, eventos = getattr(camada, sentido)(unidade, self.contexto)
                saidas.extend(novas)
                passos.extend(_parear(eventos, novas, unidade))
            unidades = saidas
        return unidades, passos

    def receber(self, quadro):
        """Trata um quadro que chegou pelo meio fisico.

        Devolve (entregues, a_transmitir, passos): as mensagens que chegaram
        a camada 7 e os quadros novos que devem seguir para o meio.
        """
        raise NotImplementedError


class Computador(Dispositivo):
    """As sete camadas: origem ou destino de uma mensagem."""

    CAMADAS = (Aplicacao, Apresentacao, Sessao, Transporte, Rede, Enlace, Fisica)

    def escutar(self, porta, processo):
        """Associa um processo a uma porta, para a demultiplexacao da camada 4."""
        self.contexto.processos[porta] = processo

    def enviar(self, mensagem, destino, portas, processo):
        """Entrega a mensagem a camada 7 e a leva ate a camada 1.

        destino e o endereco logico que a camada 3 pora no pacote; portas e o
        par (origem, destino) que a camada 4 pora no segmento.
        """
        self.contexto.processo = processo
        self.contexto.portas = portas
        self.contexto.destino = destino
        return self.descer([PDU(dados=mensagem)])

    def receber(self, quadro):
        entregues, passos = self.subir([quadro])
        return entregues, [], passos


class Roteador(Dispositivo):
    """Apenas as camadas 3, 2 e 1."""

    CAMADAS = (Rede, Enlace, Fisica)

    def receber(self, quadro):
        """Sobe ate a camada 3, que decide a rota, e desce de novo.

        O quadro recebido termina na camada 2 da subida; o que desce e o
        pacote, intacto, e a camada 2 constroi em volta dele um quadro novo,
        com o par de enderecos fisicos do proximo enlace.
        """
        pacotes, passos = self.subir([quadro])
        # Um pacote enderecado ao proprio roteador sobe para a camada 4, que
        # ele nao tem: nada segue adiante.
        em_transito = [p for p in pacotes if p.camada == 3]
        quadros, passos_da_descida = self.descer(em_transito)
        return [], quadros, passos + passos_da_descida


def criar_dispositivo(nome, topologia, **contadores):
    """Monta o dispositivo certo para o nome, conforme a topologia."""
    classe = Roteador if nome in topologia.roteadores else Computador
    return classe(nome, topologia, **contadores)
