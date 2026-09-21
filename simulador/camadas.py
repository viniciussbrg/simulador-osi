"""As sete classes de camada do modelo OSI.

Cada camada e uma classe com dois metodos de sentido oposto:

``descer``
    recebe a unidade de dados da camada superior, acrescenta o que lhe compete
    e devolve o resultado para ser entregue a camada inferior;
``subir``
    recebe a unidade vinda da camada inferior, interpreta o cabecalho inserido
    pela sua camada par e devolve o resultado para a camada superior.

Nenhuma camada chama outra camada. A travessia da pilha e conduzida pela pilha
do dispositivo, que caminha pelos vinculos de adjacencia ``superior`` e
``inferior``. Os dados que uma camada precisa comunicar a camada imediatamente
adjacente viajam no ``contexto`` da unidade, que representa a primitiva de
servico entre camadas vizinhas e nao e transmitido pela rede.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .pdu import (
    NOME_UNIDADE,
    TAMANHO_CABECALHO,
    TAMANHO_FINALIZADOR,
    Cabecalho,
    ErroDeSegmentacaoError,
    UnidadeDados,
    abreviar_fisico,
    dividir_carga,
)

#: Unidade acima da qual a camada 4 segmenta (octetos de carga, ja incluindo o
#: cabecalho de sessao). Abaixo disso a mensagem viaja em um unico segmento.
LIMITE_SEGMENTACAO = 48

#: Tamanho maximo de cada segmento produzido quando a segmentacao ocorre.
CARGA_POR_SEGMENTO = 40

#: Chave da cifra da camada 6. A cifra preserva o tamanho em octetos.
CHAVE_CIFRA = 0x5A

#: Esquema de codificacao registrado pela camada 6.
ESQUEMA_CODIFICACAO = "UTF-8"


def cifrar(dados: bytes, chave: int = CHAVE_CIFRA) -> bytes:
    """Cifra simetrica que preserva o tamanho, para uso da camada 6."""
    return bytes(octeto ^ chave for octeto in dados)


# Resultado da passagem por uma camada


@dataclass
class Acao:
    """Uma acao registrada por uma camada, que vira uma linha do registro."""

    acao: str
    descricao: str
    unidade: Optional[UnidadeDados] = None
    logicos: Optional[Tuple[str, str]] = None
    fisicos: Optional[Tuple[str, str]] = None
    portas: Optional[Tuple[int, int]] = None
    enlace: Optional[str] = None
    processos: Optional[Tuple[str, str]] = None
    detalhes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Resultado:
    """O que uma camada devolve: unidades produzidas e acoes registradas."""

    unidades: List[UnidadeDados] = field(default_factory=list)
    acoes: List[Acao] = field(default_factory=list)
    descartar: bool = False
    retido: bool = False


# Camada base


class Camada:
    """Classe base das camadas. Conhece apenas as camadas adjacentes."""

    numero: int = 0
    nome: str = ""

    def __init__(self, dispositivo: Any) -> None:
        self.dispositivo = dispositivo
        self.superior: Optional["Camada"] = None
        self.inferior: Optional["Camada"] = None

    # -- adjacencia --------------------------------------------------------

    def ligar_acima(self, camada: "Camada") -> None:
        self.superior = camada

    def ligar_abaixo(self, camada: "Camada") -> None:
        self.inferior = camada

    # -- sentidos ----------------------------------------------------------

    def descer(self, unidade: UnidadeDados) -> Resultado:
        raise NotImplementedError

    def subir(self, unidade: UnidadeDados) -> Resultado:
        raise NotImplementedError

    # -- apoio -------------------------------------------------------------

    @property
    def rotulo(self) -> str:
        return f"L{self.numero}"

    @property
    def unidade_produzida(self) -> str:
        return NOME_UNIDADE[self.numero]

    def _cabecalho(self, **campos: Any) -> Cabecalho:
        return Cabecalho(
            camada=self.numero, campos=campos, tamanho=TAMANHO_CABECALHO[self.numero]
        )

    def __repr__(self) -> str:  # pragma: no cover - apoio a depuracao
        return (
            f"<{self.rotulo} {self.nome} de {getattr(self.dispositivo, 'nome', '?')}>"
        )


# Camada 7 - Aplicacao


class Aplicacao(Camada):
    """Gera a mensagem e identifica o processo pelo nome (endereco especifico)."""

    numero = 7
    nome = "Aplicacao"

    def descer(self, unidade: UnidadeDados) -> Resultado:
        texto = unidade.contexto.get("texto", "")
        processo_origem = unidade.contexto.get("processo_origem", "processo")
        processo_destino = unidade.contexto.get("processo_destino", "processo")
        octetos = texto.encode(ESQUEMA_CODIFICACAO)
        nova = UnidadeDados(
            dados=octetos,
            unidade=self.unidade_produzida,
            identificador=unidade.identificador,
            contexto=dict(unidade.contexto),
        )
        acao = Acao(
            acao="GERA",
            descricao=f"processo {processo_origem}, destino {processo_destino}",
            unidade=nova,
            processos=(processo_origem, processo_destino),
        )
        return Resultado(unidades=[nova], acoes=[acao])

    def subir(self, unidade: UnidadeDados) -> Resultado:
        processo = unidade.contexto.get("processo_destino", "processo")
        texto = unidade.dados.decode(ESQUEMA_CODIFICACAO, errors="replace")
        recorte = texto if len(texto) <= 40 else texto[:37] + "..."
        acao = Acao(
            acao="ENTREGA",
            descricao=f"processo {processo} recebe a mensagem: {recorte}",
            unidade=unidade,
            processos=(unidade.contexto.get("processo_origem", "?"), processo),
            detalhes={"texto": texto},
        )
        return Resultado(unidades=[unidade], acoes=[acao])


# Camada 6 - Apresentacao


class Apresentacao(Camada):
    """Converte texto em octetos, registra a codificacao e cifra o conteudo."""

    numero = 6
    nome = "Apresentacao"

    def descer(self, unidade: UnidadeDados) -> Resultado:
        nova = unidade.com_dados(cifrar(unidade.dados))
        nova = nova.com_contexto(codificacao=ESQUEMA_CODIFICACAO, cifrado=True)
        acao = Acao(
            acao="CODIFICA",
            descricao=f"octetos {ESQUEMA_CODIFICACAO}, conteúdo cifrado",
            unidade=nova,
        )
        return Resultado(unidades=[nova], acoes=[acao])

    def subir(self, unidade: UnidadeDados) -> Resultado:
        nova = unidade.com_dados(cifrar(unidade.dados))
        nova = nova.com_contexto(cifrado=False)
        acao = Acao(
            acao="DECODIFICA",
            descricao=f"conteúdo decifrado, octetos {ESQUEMA_CODIFICACAO}",
            unidade=nova,
        )
        return Resultado(unidades=[nova], acoes=[acao])


# Camada 5 - Sessao


class Sessao(Camada):
    """Abre, mantem e encerra o dialogo, atribuindo um identificador de sessao."""

    numero = 5
    nome = "Sessao"

    def descer(self, unidade: UnidadeDados) -> Resultado:
        identificador = self.dispositivo.servicos.proxima_sessao()
        cabecalho = self._cabecalho(sessao=identificador)
        nova = unidade.acrescentar_cabecalho(cabecalho, self.unidade_produzida)
        acao = Acao(
            acao="ABRE",
            descricao=f"sessão {identificador} estabelecida",
            unidade=nova,
            detalhes={"sessao": identificador},
        )
        return Resultado(unidades=[nova], acoes=[acao])

    def subir(self, unidade: UnidadeDados) -> Resultado:
        cabecalho = unidade.ler_cabecalho(self.numero)
        identificador = cabecalho.campos["sessao"]
        nova = unidade.remover_cabecalho(self.numero, self.unidade_produzida)
        acao = Acao(
            acao="ENCERRA",
            descricao=f"sessão {identificador} entregue e encerrada",
            unidade=nova,
            detalhes={"sessao": identificador},
        )
        return Resultado(unidades=[nova], acoes=[acao])


# Camada 4 - Transporte


class Transporte(Camada):
    """Numera portas, segmenta a mensagem e remonta os segmentos no destino."""

    numero = 4
    nome = "Transporte"

    def __init__(self, dispositivo: Any) -> None:
        super().__init__(dispositivo)
        #: buffers de remontagem, um por fluxo demultiplexado
        self._remontagem: Dict[Tuple[Any, ...], Dict[int, UnidadeDados]] = {}

    # -- descida -----------------------------------------------------------

    def descer(self, unidade: UnidadeDados) -> Resultado:
        porta_origem = int(unidade.contexto["porta_origem"])
        porta_destino = int(unidade.contexto["porta_destino"])

        if unidade.tamanho <= LIMITE_SEGMENTACAO:
            fatias = [unidade.dados]
        else:
            fatias = dividir_carga(unidade, CARGA_POR_SEGMENTO)

        total = len(fatias)
        unidades: List[UnidadeDados] = []
        acoes: List[Acao] = []
        for indice, fatia in enumerate(fatias, start=1):
            base = unidade.com_dados(fatia)
            if indice > 1:
                # O cabecalho de sessao entra uma unica vez, no primeiro segmento.
                base = UnidadeDados(
                    dados=fatia,
                    unidade=unidade.unidade,
                    contexto=dict(unidade.contexto),
                )
            cabecalho = self._cabecalho(
                porta_origem=porta_origem,
                porta_destino=porta_destino,
                segmento=indice,
                total=total,
            )
            segmento = base.acrescentar_cabecalho(
                cabecalho, self.unidade_produzida, identificador=f"S{indice}/{total}"
            )
            unidades.append(segmento)
            acoes.append(
                Acao(
                    acao="SEGMENTA",
                    descricao=(
                        f"porta {porta_origem} \u2192 {porta_destino}, "
                        f"segmento {indice} de {total}"
                        + (
                            f", {segmento.tamanho - TAMANHO_CABECALHO[self.numero]} "
                            f"octetos de carga"
                            if total > 1
                            else ""
                        )
                    ),
                    unidade=segmento,
                    portas=(porta_origem, porta_destino),
                    detalhes={
                        "segmento": indice,
                        "total": total,
                        "carga": segmento.tamanho - TAMANHO_CABECALHO[self.numero],
                    },
                )
            )
        return Resultado(unidades=unidades, acoes=acoes)

    # -- subida ------------------------------------------------------------

    def subir(self, unidade: UnidadeDados) -> Resultado:
        cabecalho = unidade.ler_cabecalho(self.numero)
        porta_origem = cabecalho.campos["porta_origem"]
        porta_destino = cabecalho.campos["porta_destino"]
        indice = cabecalho.campos["segmento"]
        total = cabecalho.campos["total"]
        sem_cabecalho = unidade.remover_cabecalho(self.numero, NOME_UNIDADE[5])

        origem_logica = unidade.contexto.get("origem_logica", "?")
        chave = (origem_logica, porta_origem, porta_destino)

        acoes = [
            Acao(
                acao="DEMULTIPLEXA",
                descricao=(
                    f"porta {porta_destino} recebe de {origem_logica}:{porta_origem}, "
                    f"segmento {indice} de {total}"
                ),
                unidade=sem_cabecalho,
                portas=(porta_origem, porta_destino),
                detalhes={"fluxo": f"{origem_logica}:{porta_origem}->{porta_destino}"},
            )
        ]

        buffer = self._remontagem.setdefault(chave, {})
        buffer[indice] = sem_cabecalho
        if len(buffer) < total:
            acoes.append(
                Acao(
                    acao="AGUARDA",
                    descricao=(
                        f"{len(buffer)} de {total} segmentos recebidos, "
                        f"mensagem ainda não remontada"
                    ),
                    unidade=sem_cabecalho,
                    portas=(porta_origem, porta_destino),
                )
            )
            return Resultado(unidades=[], acoes=acoes, retido=True)

        del self._remontagem[chave]
        ordenados = [buffer[i] for i in sorted(buffer)]
        dados = b"".join(parte.dados for parte in ordenados)
        remontada = ordenados[0].com_dados(dados)
        remontada = remontada.com_contexto(
            porta_origem=porta_origem, porta_destino=porta_destino
        )
        if total > 1:
            acoes.append(
                Acao(
                    acao="REMONTA",
                    descricao=(
                        f"{total} segmentos remontados na ordem 1..{total}, "
                        f"{len(dados)} octetos de dados"
                    ),
                    unidade=remontada,
                    portas=(porta_origem, porta_destino),
                )
            )
        return Resultado(unidades=[remontada], acoes=acoes)


# Camada 3 - Rede


class Rede(Camada):
    """Insere o par de enderecos logicos e consulta a tabela de encaminhamento."""

    numero = 3
    nome = "Rede"

    # -- descida -----------------------------------------------------------

    def descer(self, unidade: UnidadeDados) -> Resultado:
        origem = unidade.contexto["origem_logica"]
        destino = unidade.contexto["destino_logico"]
        identificacao = self.dispositivo.servicos.proximo_pacote()
        cabecalho = self._cabecalho(
            origem=origem, destino=destino, identificacao=identificacao
        )
        pacote = unidade.acrescentar_cabecalho(
            cabecalho, self.unidade_produzida, identificador=identificacao
        )
        acoes = [
            Acao(
                acao="ENCAPSULA",
                descricao=f"{origem} \u2192 {destino}",
                unidade=pacote,
                logicos=(origem, destino),
                detalhes={"pacote": identificacao},
            )
        ]
        decisao = self._decidir(pacote, origem, destino)
        acoes.extend(decisao.acoes)
        if decisao.descartar:
            return Resultado(unidades=[], acoes=acoes, descartar=True)
        return Resultado(unidades=decisao.unidades, acoes=acoes)

    # -- subida ------------------------------------------------------------

    def subir(self, unidade: UnidadeDados) -> Resultado:
        cabecalho = unidade.ler_cabecalho(self.numero)
        origem = cabecalho.campos["origem"]
        destino = cabecalho.campos["destino"]

        if self.dispositivo.possui_endereco(destino):
            entregue = unidade.remover_cabecalho(self.numero, NOME_UNIDADE[4])
            entregue = entregue.com_contexto(
                origem_logica=origem, destino_logico=destino
            )
            acao = Acao(
                acao="DESENCAPSULA",
                descricao=f"pacote {cabecalho.campos['identificacao']} destinado a este nó, {origem} -> {destino}",
                unidade=entregue,
                logicos=(origem, destino),
            )
            return Resultado(unidades=[entregue], acoes=[acao])

        if not self.dispositivo.encaminha:
            acao = Acao(
                acao="DESCARTA",
                descricao=f"destino {destino} não pertence a este dispositivo, pacote descartado",
                unidade=unidade,
                logicos=(origem, destino),
            )
            return Resultado(unidades=[], acoes=[acao], descartar=True)

        decisao = self._decidir(unidade, origem, destino)
        return Resultado(
            unidades=decisao.unidades, acoes=decisao.acoes, descartar=decisao.descartar
        )

    # -- decisao de rota ---------------------------------------------------

    def _decidir(self, pacote: UnidadeDados, origem: str, destino: str) -> Resultado:
        """Escolhe o proximo salto. E a unica camada autorizada a fazer isso."""
        decisao = self.dispositivo.decidir_encaminhamento(destino)
        if decisao is None:
            return Resultado(
                unidades=[],
                acoes=[
                    Acao(
                        acao="DESCARTA",
                        descricao=f"sem rota para {destino}, pacote descartado",
                        unidade=pacote,
                        logicos=(origem, destino),
                    )
                ],
                descartar=True,
            )
        saida = pacote.com_contexto(
            proximo_salto=decisao.proximo_salto,
            interface_saida=decisao.interface.nome,
        )
        return Resultado(
            unidades=[saida],
            acoes=[
                Acao(
                    acao="ROTEIA",
                    descricao=decisao.descricao,
                    unidade=saida,
                    logicos=(origem, destino),
                    detalhes={
                        "interface": decisao.interface.nome,
                        "custo": decisao.custo,
                    },
                )
            ],
        )


# Camada 2 - Enlace


class Enlace(Camada):
    """Insere o par de enderecos fisicos, delimita o quadro e verifica o erro."""

    numero = 2
    nome = "Enlace"

    def descer(self, unidade: UnidadeDados) -> Resultado:
        proximo_salto = unidade.contexto["proximo_salto"]
        interface = self.dispositivo.interface(unidade.contexto["interface_saida"])
        fisico_destino = self.dispositivo.resolver_fisico(interface, proximo_salto)

        if fisico_destino is None:
            acao = Acao(
                acao="DESCARTA",
                descricao=(
                    f"vizinho {proximo_salto} inalcançável pela interface "
                    f"{interface.nome}, quadro nao transmitido"
                ),
                unidade=unidade,
            )
            return Resultado(unidades=[], acoes=[acao], descartar=True)

        numero = self.dispositivo.servicos.proximo_quadro()
        identificador = f"Q{numero}"
        cabecalho = self._cabecalho(
            destino_fisico=fisico_destino,
            origem_fisico=interface.fisico,
            tipo="0x0800",
        )
        quadro = unidade.acrescentar_cabecalho(
            cabecalho, self.unidade_produzida, identificador=identificador
        )
        finalizador = Cabecalho(
            camada=self.numero,
            campos={"verificacao": f"{quadro.verificacao():08X}"},
            tamanho=TAMANHO_FINALIZADOR,
            finalizador=True,
        )
        quadro = quadro.acrescentar_finalizador(finalizador)
        vizinha = self.dispositivo.interface_vizinha(interface, proximo_salto)
        enlace = (
            f"{self.dispositivo.nome}-{vizinha.dispositivo}"
            if vizinha
            else interface.rede
        )
        quadro = quadro.com_contexto(
            enlace=enlace,
            interface_saida=interface.nome,
            vizinho=vizinha.dispositivo if vizinha else None,
            segmento=interface.rede,
        )

        acao = Acao(
            acao="ENQUADRA",
            descricao=(
                f"{abreviar_fisico(interface.fisico)} \u2192 {abreviar_fisico(fisico_destino)}, "
                f"quadro {identificador}"
            ),
            unidade=quadro,
            fisicos=(interface.fisico, fisico_destino),
            enlace=enlace,
            detalhes={"quadro": identificador},
        )
        return Resultado(unidades=[quadro], acoes=[acao])

    def subir(self, unidade: UnidadeDados) -> Resultado:
        cabecalho = unidade.ler_cabecalho(self.numero)
        identificador = unidade.identificador or "Q?"
        esperado = (
            unidade.finalizador.campos["verificacao"] if unidade.finalizador else None
        )
        calculado = f"{unidade.remover_finalizador().verificacao():08X}"

        if esperado != calculado:
            acao = Acao(
                acao="DESCARTA",
                descricao=(
                    f"verificação de erro incorreta, quadro {identificador} descartado; "
                    f"nenhuma camada superior é acionada"
                ),
                unidade=unidade,
                fisicos=(
                    cabecalho.campos["origem_fisico"],
                    cabecalho.campos["destino_fisico"],
                ),
                enlace=unidade.contexto.get("enlace"),
            )
            return Resultado(unidades=[], acoes=[acao], descartar=True)

        pacote = unidade.remover_finalizador().remover_cabecalho(
            self.numero, NOME_UNIDADE[3]
        )
        acao = Acao(
            acao="DESENQUADRA",
            descricao=f"verificação de erro correta, quadro {identificador} descartado",
            unidade=pacote,
            fisicos=(
                cabecalho.campos["origem_fisico"],
                cabecalho.campos["destino_fisico"],
            ),
            enlace=unidade.contexto.get("enlace"),
        )
        return Resultado(unidades=[pacote], acoes=[acao])


# Camada 1 - Fisica


class Fisica(Camada):
    """Converte o quadro em uma sequencia de bits e a transporta pelo enlace."""

    numero = 1
    nome = "Fisica"

    def descer(self, unidade: UnidadeDados) -> Resultado:
        enlace = unidade.contexto.get("enlace", "?")
        acao = Acao(
            acao="TRANSMITE",
            descricao=f"{unidade.tamanho_bits} bits no enlace {enlace}",
            unidade=unidade,
            enlace=enlace,
            detalhes={"bits": unidade.tamanho_bits},
        )
        return Resultado(unidades=[unidade], acoes=[acao])

    def subir(self, unidade: UnidadeDados) -> Resultado:
        enlace = unidade.contexto.get("enlace", "?")
        acao = Acao(
            acao="RECEBE",
            descricao=f"{unidade.tamanho_bits} bits do enlace {enlace}",
            unidade=unidade,
            enlace=enlace,
            detalhes={"bits": unidade.tamanho_bits},
        )
        return Resultado(unidades=[unidade], acoes=[acao])


#: Construtores das camadas, do topo para a base.
CAMADAS_COMPUTADOR = (Aplicacao, Apresentacao, Sessao, Transporte, Rede, Enlace, Fisica)
CAMADAS_ROTEADOR = (Rede, Enlace, Fisica)
