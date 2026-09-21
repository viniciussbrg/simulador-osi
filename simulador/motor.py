"""Nucleo da simulacao: percorre as pilhas e produz a lista de eventos.

O motor e o unico componente que conhece a rede inteira. Ele conduz a unidade
de dados pelas camadas de cada dispositivo, transporta os quadros de um
dispositivo ao vizinho e transforma cada acao relatada por uma camada em um
evento do registro.

A travessia e conduzida por uma fila de tarefas atendida na ordem de chegada.
Com isso, varios segmentos e varios fluxos convivem na rede e se intercalam
naturalmente, que e o que os casos C3 e C7 exigem.

A interface grafica le a lista de eventos devolvida por ``executar`` e nunca
chama metodos das camadas.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Sequence, Tuple

from .camadas import Acao, Camada
from .cenarios import Cenario, Fluxo
from .dispositivos import Dispositivo, ServicosDaSimulacao, construir_dispositivos
from .pdu import UnidadeDados
from .rede import Topologia
from .registro import Evento, ResumoComunicacao

#: Limite de tarefas processadas, para que uma topologia com laco nao trave.
LIMITE_DE_TAREFAS = 5000


class ErroDeSimulacaoError(RuntimeError):
    """Parametros de simulacao invalidos."""


@dataclass
class Tarefa:
    """Uma unidade de trabalho pendente na fila do motor."""

    tipo: str  # "enviar" ou "receber"
    dispositivo: str
    unidade: UnidadeDados
    fluxo: str


@dataclass
class ResultadoSimulacao:
    """Tudo o que a interface precisa para reproduzir a simulacao."""

    cenario: Cenario
    eventos: List[Evento] = field(default_factory=list)
    resumo: Optional[ResumoComunicacao] = None
    caminho: Tuple[Tuple[str, str], ...] = ()
    dispositivos_envolvidos: Tuple[str, ...] = ()
    tabelas: Dict[str, list] = field(default_factory=dict)
    avisos: List[str] = field(default_factory=list)

    @property
    def total_de_passos(self) -> int:
        return len(self.eventos)


class Simulacao:
    """Executa um cenario sobre uma topologia e devolve a lista de eventos."""

    def __init__(
        self,
        topologia: Topologia,
        cenario: Cenario,
        fluxos: Optional[Sequence[Fluxo]] = None,
        enlaces_derrubados: Optional[Sequence[str]] = None,
        erro_de_bit: Optional[str] = None,
    ) -> None:
        self.topologia = topologia
        self.cenario = cenario
        self.fluxos: Tuple[Fluxo, ...] = tuple(
            fluxos if fluxos is not None else cenario.fluxos
        )
        derrubados = list(enlaces_derrubados) if enlaces_derrubados is not None else []
        if cenario.enlace_derrubado and cenario.enlace_derrubado not in derrubados:
            derrubados.append(cenario.enlace_derrubado)
        self.enlaces_derrubados = tuple(derrubados)
        self.erro_de_bit = erro_de_bit or cenario.erro_de_bit

        self.servicos = ServicosDaSimulacao()
        self.dispositivos: Dict[str, Dispositivo] = {}
        self._eventos: List[Evento] = []
        self._passo = 0
        self._caminho: List[Tuple[str, str]] = []
        self._envolvidos: List[str] = []
        self._avisos: List[str] = []
        self._erro_ja_injetado = False

        # estado corrente propagado para a tela
        self._logicos: Optional[Tuple[str, str]] = None
        self._fisicos: Optional[Tuple[str, str]] = None
        self._portas: Optional[Tuple[int, int]] = None
        self._processos: Optional[Tuple[str, str]] = None

        self._octetos_transmitidos = 0
        self._quadros = 0
        self._octetos_entregues = 0
        self._enlaces_usados: List[str] = []

    # -- execucao ----------------------------------------------------------

    def executar(self) -> ResultadoSimulacao:
        """Roda o cenario inteiro e devolve eventos, resumo e caminho."""
        self._validar_fluxos()
        estado_anterior = {
            nome: s.ativo for nome, s in self.topologia.segmentos.items()
        }
        try:
            for enlace in self.enlaces_derrubados:
                self.topologia.derrubar(enlace)
                self._avisos.append(f"enlace {enlace} derrubado")
            self.dispositivos = construir_dispositivos(self.topologia, self.servicos)
            self._processar_fila()
            resumo = self._montar_resumo()
            tabelas = {
                nome: self.topologia.tabela_encaminhamento(nome)
                for nome in self.topologia.roteadores()
            }
            return ResultadoSimulacao(
                cenario=self.cenario,
                eventos=list(self._eventos),
                resumo=resumo,
                caminho=tuple(self._caminho),
                dispositivos_envolvidos=tuple(self._envolvidos),
                tabelas=tabelas,
                avisos=list(self._avisos),
            )
        finally:
            for nome, ativo in estado_anterior.items():
                if ativo:
                    self.topologia.restaurar(nome)
                else:
                    self.topologia.derrubar(nome)

    def _validar_fluxos(self) -> None:
        if not self.fluxos:
            raise ErroDeSimulacaoError("o cenario precisa de ao menos um fluxo")
        for fluxo in self.fluxos:
            if fluxo.origem not in self.topologia.dispositivos:
                raise ErroDeSimulacaoError(f"origem desconhecida: {fluxo.origem}")
            if self.topologia.dispositivos[fluxo.origem].tipo != "computador":
                raise ErroDeSimulacaoError(
                    f"a origem {fluxo.origem} nao e um computador"
                )
            if not self.topologia.endereco_valido(fluxo.destino_logico):
                raise ErroDeSimulacaoError(
                    f"endereco de destino invalido: {fluxo.destino_logico}"
                )
            if not fluxo.texto:
                raise ErroDeSimulacaoError("a mensagem nao pode ser vazia")
            if not (0 < fluxo.porta_origem < 65536 and 0 < fluxo.porta_destino < 65536):
                raise ErroDeSimulacaoError("as portas devem estar entre 1 e 65535")

    def _processar_fila(self) -> None:
        fila: Deque[Tarefa] = deque()
        for fluxo in self.fluxos:
            unidade = UnidadeDados(
                contexto={
                    "texto": fluxo.texto,
                    "processo_origem": fluxo.processo_origem,
                    "processo_destino": fluxo.processo_destino,
                    "porta_origem": fluxo.porta_origem,
                    "porta_destino": fluxo.porta_destino,
                    "origem_logica": self._logico_de(fluxo.origem),
                    "destino_logico": fluxo.destino_logico,
                }
            )
            fila.append(Tarefa("enviar", fluxo.origem, unidade, fluxo.identificacao))

        atendidas = 0
        while fila:
            atendidas += 1
            if atendidas > LIMITE_DE_TAREFAS:
                self._avisos.append(
                    "limite de tarefas atingido; verifique se a topologia possui laco"
                )
                break
            tarefa = fila.popleft()
            dispositivo = self.dispositivos[tarefa.dispositivo]
            self._marcar_envolvido(dispositivo.nome)

            if tarefa.tipo == "enviar":
                quadros = self._descer(
                    dispositivo, dispositivo.pilha.topo, [tarefa.unidade], tarefa.fluxo
                )
            else:
                quadros = self._receber(dispositivo, tarefa.unidade, tarefa.fluxo)

            for quadro in quadros:
                proxima = self._transportar(dispositivo, quadro, tarefa.fluxo)
                if proxima is not None:
                    fila.append(proxima)

    # -- travessia das pilhas ---------------------------------------------

    def _descer(
        self,
        dispositivo: Dispositivo,
        camada_inicial: Camada,
        unidades: Sequence[UnidadeDados],
        fluxo: str,
    ) -> List[UnidadeDados]:
        """Desce a pilha a partir de ``camada_inicial`` e devolve os quadros prontos."""
        camada: Optional[Camada] = camada_inicial
        atuais = list(unidades)
        while camada is not None and atuais:
            produzidas: List[UnidadeDados] = []
            for unidade in atuais:
                resultado = camada.descer(unidade)
                self._registrar_acoes(
                    dispositivo, camada.numero, resultado.acoes, fluxo
                )
                produzidas.extend(resultado.unidades)
            atuais = produzidas
            camada = camada.inferior
        return atuais

    def _receber(
        self, dispositivo: Dispositivo, quadro: UnidadeDados, fluxo: str
    ) -> List[UnidadeDados]:
        """Sobe a pilha do receptor e, se for roteador, desce novamente."""
        camada: Optional[Camada] = dispositivo.pilha.base
        atuais = [quadro]
        while camada is not None and atuais:
            produzidas: List[UnidadeDados] = []
            for unidade in atuais:
                resultado = camada.subir(unidade)
                self._registrar_acoes(
                    dispositivo, camada.numero, resultado.acoes, fluxo
                )
                produzidas.extend(resultado.unidades)
            atuais = produzidas
            if camada.numero == 3 and dispositivo.encaminha and atuais:
                # A decisao de rota ja foi tomada pela camada 3. O pacote volta a
                # descer, e um quadro novo e construido pela camada 2.
                return self._descer(dispositivo, camada.inferior, atuais, fluxo)
            camada = camada.superior
        return []

    # -- meio de transmissao ----------------------------------------------

    def _transportar(
        self, dispositivo: Dispositivo, quadro: UnidadeDados, fluxo: str
    ) -> Optional[Tarefa]:
        """Contabiliza a transmissao, injeta erro se pedido e entrega ao vizinho."""
        vizinho = quadro.contexto.get("vizinho")
        enlace = quadro.contexto.get("enlace", "?")
        segmento = quadro.contexto.get("segmento")

        self._quadros += 1
        self._octetos_transmitidos += quadro.tamanho
        if enlace not in self._enlaces_usados:
            self._enlaces_usados.append(enlace)
        if vizinho:
            par = (dispositivo.nome, vizinho)
            if par not in self._caminho and (par[1], par[0]) not in self._caminho:
                self._caminho.append(par)

        if vizinho is None:
            self._avisos.append(f"quadro sem vizinho no enlace {enlace}")
            return None

        if (
            self.erro_de_bit
            and segmento == self.erro_de_bit
            and not self._erro_ja_injetado
        ):
            quadro = self._corromper(quadro)
            self._erro_ja_injetado = True
            self._registrar_acoes(
                dispositivo,
                1,
                [
                    Acao(
                        acao="ERRO",
                        descricao=(
                            f"bit alterado no enlace {enlace} por injeção de erro na "
                            f"interface do simulador"
                        ),
                        unidade=quadro,
                        enlace=enlace,
                    )
                ],
                fluxo,
            )

        self._marcar_envolvido(vizinho)
        return Tarefa("receber", vizinho, quadro, fluxo)

    @staticmethod
    def _corromper(quadro: UnidadeDados) -> UnidadeDados:
        """Inverte um bit da carga do quadro, sem recalcular a verificacao."""
        dados = quadro.dados
        if not dados:
            return quadro
        alterados = bytes([dados[0] ^ 0x01]) + dados[1:]
        return quadro.com_dados(alterados).com_contexto(corrompido=True)

    # -- registro ----------------------------------------------------------

    def _registrar_acoes(
        self, dispositivo: Dispositivo, camada: int, acoes: Sequence[Acao], fluxo: str
    ) -> None:
        for acao in acoes:
            self._registrar(dispositivo, camada, acao, fluxo)

    def _registrar(
        self, dispositivo: Dispositivo, camada: int, acao: Acao, fluxo: str
    ) -> None:
        self._passo += 1
        unidade = acao.unidade
        if acao.logicos:
            self._logicos = acao.logicos
        if acao.fisicos:
            self._fisicos = acao.fisicos
        if acao.portas:
            self._portas = acao.portas
        if acao.processos:
            self._processos = acao.processos
        if acao.acao == "ENTREGA":
            texto = acao.detalhes.get("texto", "")
            self._octetos_entregues += len(texto.encode("utf-8"))

        self._eventos.append(
            Evento(
                passo=self._passo,
                dispositivo=dispositivo.nome,
                camada=camada,
                acao=acao.acao,
                descricao=acao.descricao,
                tamanho=unidade.tamanho if unidade is not None else 0,
                unidade=unidade.unidade if unidade is not None else "",
                identificador=unidade.identificador if unidade is not None else "",
                blocos=tuple(unidade.blocos()) if unidade is not None else (),
                logicos=self._logicos,
                fisicos=self._fisicos,
                portas=self._portas,
                processos=self._processos,
                enlace=acao.enlace,
                caminho=tuple(self._caminho),
                fluxo=fluxo,
                descarte=acao.acao == "DESCARTA",
            )
        )

    def _marcar_envolvido(self, nome: str) -> None:
        if nome not in self._envolvidos:
            self._envolvidos.append(nome)

    def _logico_de(self, dispositivo: str) -> str:
        return self.topologia.interfaces_de(dispositivo)[0].logico

    # -- resumo ------------------------------------------------------------

    def _montar_resumo(self) -> ResumoComunicacao:
        gerados = sum(fluxo.octetos for fluxo in self.fluxos)
        entregue = self._octetos_entregues > 0
        observacao = ""
        if not entregue:
            descartes = [e for e in self._eventos if e.descarte]
            if descartes:
                ultimo = descartes[-1]
                observacao = (
                    f"mensagem não entregue: descarte em {ultimo.dispositivo} na camada "
                    f"L{ultimo.camada}; os {gerados} octetos gerados não chegaram ao destino"
                )
            else:
                observacao = "mensagem não entregue ao processo de destino"
        return ResumoComunicacao(
            cenario=f"{self.cenario.rotulo}/{self.cenario.codigo}",
            titulo=self.cenario.titulo,
            octetos_uteis=self._octetos_entregues,
            octetos_transmitidos=self._octetos_transmitidos,
            quadros=self._quadros,
            enlaces=len(self._enlaces_usados),
            entregue=entregue,
            observacao=observacao,
        )


def executar_cenario(
    topologia: Topologia,
    cenario: Cenario,
    fluxos: Optional[Sequence[Fluxo]] = None,
    enlaces_derrubados: Optional[Sequence[str]] = None,
    erro_de_bit: Optional[str] = None,
) -> ResultadoSimulacao:
    """Atalho para executar um cenario em uma unica chamada."""
    return Simulacao(
        topologia,
        cenario,
        fluxos=fluxos,
        enlaces_derrubados=enlaces_derrubados,
        erro_de_bit=erro_de_bit,
    ).executar()


def comparar_eficiencias(topologia: Topologia) -> Dict[str, ResumoComunicacao]:
    """Compara a eficiencia do caso C1, de um unico enlace, com a do caso C2.

    O enunciado pede que os dois valores sejam apresentados na tela.
    """
    from .cenarios import por_codigo

    return {
        codigo: executar_cenario(topologia, por_codigo(codigo)).resumo
        for codigo in ("C1", "C2")
    }
