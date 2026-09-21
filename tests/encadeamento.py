"""Encadeador mínimo de camadas para os testes de núcleo (F1).

`simulador.py` — a fila de eventos real — só nasce em F3 (issue #33). Enquanto
isso, os testes de F1 (T-PDU, issue #14; T-R5, issue #15) precisam de *uma
lista de `Evento`* para verificar suas invariantes. Este módulo produz essa
lista encadeando à mão as chamadas `descer()`/`subir()` de `camadas.py` para
os casos C1, C2 e C7, na mesma ordem em que a pilha de um dispositivo as
faria (seção 4.3 da proposta técnica: "quem encadeia as chamadas é a pilha do dispositivo").

O que este módulo **não** é:

- Não é o motor. Não tem fila de prioridade, não intercala fluxos (C3), não
  injeta falhas (C4/C6) e não emite `METRICAS`. É o suficiente para exercer
  a contabilidade de octetos e a simetria de cabeçalhos, nada além disso.
- Não conhece `rede.py`. A tabela de encaminhamento passada à L3 é uma rota
  padrão (`0.0.0.0/0`) que casa qualquer destino — os testes de F1 verificam
  tamanho e simetria, não roteamento (isso é T-ROTA, issue #26). Os endereços
  físicos de cada salto são rótulos sintéticos; o `tam` do cabeçalho H2 é
  fixo (14) e não depende do conteúdo.

Quando F3 fechar, T-PDU e T-R5 devem passar a consumir a lista real de
`simulador.py`; este encadeador continua servindo como oráculo isolado de F1.
"""

import itertools
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite `python tests/test_pdu.py` além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from dataclasses import dataclass

import pdu as _pdu
from camadas import (
    CamadaAplicacao,
    CamadaApresentacao,
    CamadaEnlace,
    CamadaFisica,
    CamadaRede,
    CamadaSessao,
    CamadaTransporte,
    Contexto,
    EntradaRota,
    reiniciar_contador_sessoes,
)
from evento import BlocoEvento, Evento, Fisico, Logico, Porta, Processo, PduInfo, Segmento
from pdu import PDU


@dataclass(frozen=True)
class ConfiguracaoCaso:
    nome: str
    mensagem: str
    rota: tuple[str, ...]  # origem, roteadores intermediários..., destino
    porta_origem: int = 5210
    porta_destino: int = 443
    logico_origem: str = "10.0.1.10"
    logico_destino: str = "10.0.3.10"
    processo_origem: str = "navegador"
    processo_destino: str = "servidorWeb"


# Mensagem de referência do Anexo B (exatamente 42 octetos).
_MSG_42B = "GET /index.html HTTP/1.1 Host: fesa.edu.br"
# C7 pede 180 octetos (seção 10). O conteúdo é irrelevante para o tamanho —
# só o comprimento importa —, então um preenchimento ASCII determinístico basta.
_MSG_180B = "M" * 180

CASOS: dict[str, ConfiguracaoCaso] = {
    "C1": ConfiguracaoCaso(
        "C1", _MSG_42B, ("H1", "H2"), logico_destino="10.0.1.11"
    ),
    "C2": ConfiguracaoCaso(
        "C2", _MSG_42B, ("H1", "R1", "R4", "R3", "H4")
    ),
    "C7": ConfiguracaoCaso(
        "C7", _MSG_180B, ("H1", "R1", "R4", "R3", "H4")
    ),
}


def _rota_padrao() -> list[EntradaRota]:
    """Uma tabela de encaminhamento de uma linha só que casa qualquer destino.
    A L3 exige `ctx.tabela_encaminhamento` preenchida e um casamento de
    prefixo; os testes de F1 não avaliam a escolha da rota."""
    return [EntradaRota(prefixo="0.0.0.0/0", interface="e0", custo=1, proximo_salto="10.0.0.1")]


def _pdu_info(unidade: PDU) -> PduInfo:
    """Retrato imutável dos blocos da PDU no instante do evento — cópia
    profunda para `BlocoEvento`, para que consumo posterior do quadro (R2)
    não altere um evento já emitido."""
    return PduInfo(
        nome=unidade.nome,
        blocos=tuple(
            BlocoEvento(rotulo=b.rotulo, tam=b.tam, tipo=b.tipo, conteudo=b.conteudo)
            for b in unidade.blocos
        ),
    )


class _Encadeador:
    """Percorre uma única mensagem da L7 da origem à L7 do destino, emitindo
    um `Evento` por ação de camada. Um objeto por caso."""

    def __init__(self, cfg: ConfiguracaoCaso) -> None:
        self.cfg = cfg
        # Contadores globais reiniciados por caso: C2 → {Q1..Q4}, C7 → Q1..Q12,
        # sessão sempre S-0001 (mesma disciplina de `simulador.py`, R2).
        _pdu.reiniciar_contador_quadros()
        reiniciar_contador_sessoes()

        self.eventos: list[Evento] = []
        self._passo = itertools.count(1)
        self._caminho: list[str] = []

        self.L7 = CamadaAplicacao()
        self.L6 = CamadaApresentacao()
        self.L5 = CamadaSessao()
        self.L3 = CamadaRede()
        self.L2 = CamadaEnlace()
        self.L1 = CamadaFisica()
        # A L4 guarda estado de remontagem: uma instância para a origem
        # (só segmenta) e outra para o destino (acumula os segmentos).
        self.L4_origem = CamadaTransporte()
        self.L4_destino = CamadaTransporte()

        self.ctx = Contexto(
            mensagem=cfg.mensagem,
            processo_origem=cfg.processo_origem,
            processo_destino=cfg.processo_destino,
            porta_origem=cfg.porta_origem,
            porta_destino=cfg.porta_destino,
            logico_origem=cfg.logico_origem,
            logico_destino=cfg.logico_destino,
        )

    # -- emissão -----------------------------------------------------------
    def _emitir(self, dispositivo, camada, acao, unidade, *, sentido, tamanho=None, **campos):
        if tamanho is None:
            tamanho = unidade.tamanho()
        self.eventos.append(
            Evento(
                passo=next(self._passo),
                dispositivo=dispositivo,
                camada=camada,
                acao=acao,
                descricao=acao,
                tamanho=tamanho,
                fluxo="F1",
                sentido=sentido,
                pdu=_pdu_info(unidade),
                caminho=tuple(self._caminho),
                **campos,
            )
        )

    # -- percurso --------------------------------------------------------
    def executar(self) -> list[Evento]:
        cfg = self.cfg
        origem = cfg.rota[0]
        ctx = self.ctx

        vazio = PDU(nome="", blocos=[])
        msg = self.L7.descer(vazio, ctx)
        self._emitir(origem, 7, "GERA", msg, sentido="desce",
                     processo=Processo(cfg.processo_origem, cfg.processo_destino))
        msg = self.L6.descer(msg, ctx)
        self._emitir(origem, 6, "CODIFICA", msg, sentido="desce")
        msg = self.L5.descer(msg, ctx)
        self._emitir(origem, 5, "ABRE", msg, sentido="desce", sessao=ctx.sessao)

        segmentos = self.L4_origem.descer(msg, ctx)
        total = len(segmentos)
        for n, seg in enumerate(segmentos, start=1):
            self._emitir(origem, 4, "SEGMENTA", seg, sentido="desce",
                         porta=Porta(cfg.porta_origem, cfg.porta_destino),
                         segmento=Segmento(n, total), sessao=ctx.sessao)
        # D5: os segmentos percorrem a rota em sequência — quadros contínuos
        # por segmento (C7 → Q1..Q4, Q5..Q8, Q9..Q12).
        for n, seg in enumerate(segmentos, start=1):
            self._encaminhar_segmento(seg, n, total)

        return self.eventos

    def _encaminhar_segmento(self, seg: PDU, n: int, total: int) -> None:
        cfg = self.cfg
        ctx = self.ctx
        nos = cfg.rota
        origem, destino = nos[0], nos[-1]
        roteadores = set(nos[1:-1])
        par_logico = Logico(cfg.logico_origem, cfg.logico_destino)

        pacote = self.L3.descer(seg, ctx)
        self._emitir(origem, 3, "ENCAPSULA", pacote, sentido="desce", logico=par_logico)
        ctx.tabela_encaminhamento = _rota_padrao()
        assert self.L3.roteia(pacote, ctx) is not None
        self._emitir(origem, 3, "ROTEIA", pacote, sentido="desce", logico=par_logico)

        for i in range(len(nos) - 1):
            pacote = self._saltar(nos[i], nos[i + 1], pacote)
            if nos[i + 1] in roteadores:
                ctx.tabela_encaminhamento = _rota_padrao()
                assert self.L3.roteia(pacote, ctx) is not None
                self._emitir(nos[i + 1], 3, "ROTEIA", pacote, sentido="meio", logico=par_logico)

        pacote = self.L3.subir(pacote, ctx)
        self._emitir(destino, 3, "DESENCAPSULA", pacote, sentido="sobe", logico=par_logico)

        remontada = self.L4_destino.subir(pacote, ctx)
        if remontada is None:
            return  # segmento intermediário — REMONTA só fecha no último (D5/C7)
        self._emitir(destino, 4, "REMONTA", remontada, sentido="sobe",
                     porta=Porta(ctx.porta_origem, ctx.porta_destino),
                     segmento=Segmento(total, total))
        m = self.L5.subir(remontada, ctx)
        self._emitir(destino, 5, "ENCERRA", m, sentido="sobe", sessao=ctx.sessao)
        m = self.L6.subir(m, ctx)
        self._emitir(destino, 6, "DECIFRA", m, sentido="sobe")
        m = self.L7.subir(m, ctx)
        self._emitir(destino, 7, "ENTREGA", m, sentido="sobe",
                     processo=Processo(cfg.processo_origem, cfg.processo_destino))

    def _saltar(self, remetente: str, receptor: str, pacote: PDU) -> PDU:
        """Um salto completo: ENQUADRA + TRANSMITE no remetente, RECEBE +
        DESENQUADRA no receptor. Devolve o pacote extraído do quadro."""
        ctx = self.ctx
        ctx.fisico_origem = f"MAC:{remetente}>{receptor}"
        ctx.fisico_destino = f"MAC:{receptor}<{remetente}"
        ctx.fisico_local = None  # desliga a checagem de difusão (sem IGNORA nos testes de F1)
        ctx.enlace_id = f"E:{remetente}-{receptor}"
        ctx.enlace_rotulo = f"{remetente}–{receptor}"

        quadro = self.L2.descer(pacote, ctx)
        fis = Fisico(ctx.fisico_origem, ctx.fisico_destino)
        self._emitir(remetente, 2, "ENQUADRA", quadro, sentido="desce", quadro=ctx.quadro, fisico=fis)
        self.L1.descer(quadro, ctx)
        self._emitir(remetente, 1, "TRANSMITE", quadro, sentido="desce",
                     tamanho=ctx.bits // 8, bits=ctx.bits, quadro=ctx.quadro, fisico=fis)

        if ctx.enlace_id not in self._caminho:
            self._caminho.append(ctx.enlace_id)

        self.L1.subir(quadro, ctx)
        self._emitir(receptor, 1, "RECEBE", quadro, sentido="sobe",
                     tamanho=ctx.bits // 8, bits=ctx.bits, quadro=ctx.quadro, fisico=fis)
        pacote_extraido = self.L2.subir(quadro, ctx)
        assert pacote_extraido is not None, (
            f"quadro {ctx.quadro} não deveria ser descartado no encadeador de F1"
        )
        self._emitir(receptor, 2, "DESENQUADRA", pacote_extraido, sentido="sobe",
                     quadro=ctx.quadro, fisico=Fisico(ctx.fisico_origem, ctx.fisico_destino))
        return pacote_extraido


def eventos_do_caso(caso: str) -> list[Evento]:
    """Lista de `Evento` que o motor produziria para `caso` ("C1", "C2" ou
    "C7"), na ordem de execução. Cada chamada é independente: os contadores
    globais de quadro e de sessão são reiniciados no início."""
    try:
        cfg = CASOS[caso]
    except KeyError:
        raise ValueError(
            f"caso {caso!r} não suportado pelo encadeador de F1 (disponíveis: "
            f"{', '.join(sorted(CASOS))})"
        ) from None
    return _Encadeador(cfg).executar()
