"""T-R3 — cardinalidade dos endereços em C2 (issue #37).

A restrição R3 tem duas metades, e uma só faz sentido contra a outra:

- o **par lógico** (`10.0.1.10 → 10.0.3.10`) é gravado uma única vez, na
  camada 3 de H1, e atravessa os quatro enlaces sem ser tocado — cardinalidade
  **1** em toda a execução;
- o **par físico** vale um enlace só, e é refeito em cada salto —
  cardinalidade **4** em C2, um valor por salto (H1↔R1, R1↔R4, R4↔R3, R3↔H4).

É a tabela da seção 3.3 ("muda no percurso? lógico: não; físico: sim, a cada
salto") virada em número, e é o que a seção 4.4/R3 dá como teste da garantia
estrutural — a camada 2 não tem acesso de escrita ao pacote, então não há por
onde o par lógico mudar. Critério de aceitação da seção 10/C2, itens 3 e 4.

Duas frentes, como em T-R5 (issue #15), porque as duas erram de jeitos
diferentes:

- `ParLogicoEmC2` e `ParFisicoEmC2` contam os pares **nos eventos** — é o
  número que a seção 13.3 pede, e é também o que a interface vai desenhar no
  painel de endereços (V4);
- as duas classes conferem além disso o cabeçalho **no fio** (`H3` e `H2` dos
  blocos da PDU), porque `Evento.logico`/`Evento.fisico` são uma cópia do
  contexto: se a L2 reescrevesse o pacote e o campo do evento continuasse
  vindo do contexto da origem, a cardinalidade seguiria 1 e o teste passaria
  por um motivo falso. O cabeçalho é o fato; o campo do evento é o retrato.

`Cardinalidade` fecha o cerco pelo outro lado: o 4 de C2 não é constante, é o
número de enlaces percorridos — C1 tem um e C7 tem os mesmos quatro, com três
segmentos. C4 fica de fora: enquanto o `enlace_fora` do caso não for aplicado
(F4, issue #40), ele percorre a rota de C2 e não contrasta com nada. Quando
chegar, o contraste que ele acrescenta é o mais forte de todos — outros quatro
pares físicos, o mesmo par lógico, porque a origem e o destino não mudaram.

Sobreposição com `tests/test_caso_c2.py`: lá os dois pares aparecem como itens
3 e 4 do critério de aceitação do caso, em duas linhas. Aqui é a restrição que
está sob teste, não o caso — daí o escopo (de onde a onde o par lógico
existe), a origem dos valores (topologia, não literal no código) e o cabeçalho
no fio.

Executar:  python -m unittest tests.test_r3
"""

import os
import sys
import unittest
from unittest import mock

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

import camadas
from rede import Topologia, carregar_topologia
from simulador import comparacao_de_referencia, executar_caso

# Valor de referência da seção 10/C2 — comparado, nunca recalculado.
PAR_LOGICO_C2 = ("10.0.1.10", "10.0.3.10")

# Os quatro saltos da rota R1→R4→R3 (tabela 6.5), na ordem em que o quadro os
# percorre. Só os dispositivos: os endereços físicos de cada um saem da
# topologia, em `fisico_do_salto` — escrevê-los aqui seria copiar o
# `topologia.json` para dentro do teste, e o arquivo é editável por
# especificação (seção 5).
SALTOS_C2 = (("H1", "R1"), ("R1", "R4"), ("R4", "R3"), ("R3", "H4"))


def fisico_do_salto(topo: Topologia, origem: str, destino: str) -> tuple[str, str]:
    """O par físico de um salto: o endereço da interface com que `origem` fala
    e o da interface com que `destino` escuta, no enlace que os liga."""
    enlaces = [
        e for e in topo.enlaces if {origem, destino} <= {p.dispositivo for p in e.pontas}
    ]
    assert len(enlaces) == 1, (
        f"{origem}↔{destino} deveria ter exatamente um enlace em comum, "
        f"tem {len(enlaces)}"
    )
    pontas = {p.dispositivo: p.interface for p in enlaces[0].pontas}
    return (
        _fisico_da_interface(topo, origem, pontas[origem]),
        _fisico_da_interface(topo, destino, pontas[destino]),
    )


def _fisico_da_interface(topo: Topologia, dispositivo: str, interface: str) -> str:
    return next(
        i.fisico for i in topo.dispositivo(dispositivo).interfaces if i.nome == interface
    )


def pares_logicos(eventos) -> set[tuple[str, str]]:
    return {(e.logico.origem, e.logico.destino) for e in eventos if e.logico}


def pares_fisicos(eventos) -> set[tuple[str | None, str | None]]:
    return {(e.fisico.origem, e.fisico.destino) for e in eventos if e.fisico}


def pares_fisicos_em_ordem(eventos) -> tuple[tuple[str | None, str | None], ...]:
    """Os pares físicos distintos na ordem da primeira aparição — é o que
    permite casar cada valor com o seu salto, e não apenas contá-los."""
    ordem: list[tuple[str | None, str | None]] = []
    for evento in eventos:
        if evento.fisico is None:
            continue
        par = (evento.fisico.origem, evento.fisico.destino)
        if par not in ordem:
            ordem.append(par)
    return tuple(ordem)


def bloco(evento, rotulo: str):
    """O cabeçalho `rotulo` da PDU do evento, ou None se ela não o carrega."""
    if evento.pdu is None:
        return None
    return next((b for b in evento.pdu.blocos if b.rotulo == rotulo), None)


class ParLogicoEmC2(unittest.TestCase):
    """Cardinalidade 1: um par lógico só, do `ENCAPSULA` de H1 ao
    `DESENCAPSULA` de H4."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        # A comparação da seção 11.4 executa C1 e C2 uma vez por topologia,
        # memoizada, para o evento `METRICAS`. O teste que instrumenta
        # `CamadaRede.descer` aquece esse cache antes, senão contaria as
        # gravações de par lógico das execuções auxiliares.
        comparacao_de_referencia(cls.topo)
        cls.eventos = executar_caso(cls.topo, "C2")

    def test_o_conjunto_de_pares_logicos_tem_cardinalidade_um(self):
        """O critério da seção 13.3, na letra."""
        self.assertEqual(pares_logicos(self.eventos), {PAR_LOGICO_C2})

    def test_o_par_logico_e_o_das_interfaces_de_h1_e_h4(self):
        """O valor não é escolha do motor: são os endereços que o
        `topologia.json` dá às interfaces das duas pontas do fluxo de C2."""
        fluxo = self.topo.caso("C2").fluxos[0]
        origem, destino = fluxo.origem.dispositivo, fluxo.destino.dispositivo
        self.assertEqual((origem, destino), ("H1", "H4"))
        da_topologia = (
            self.topo.dispositivo(origem).interfaces[0].logico,
            self.topo.dispositivo(destino).interfaces[0].logico,
        )
        self.assertEqual(da_topologia, PAR_LOGICO_C2)

    def test_o_par_logico_vai_do_encapsula_de_h1_ao_desencapsula_de_h4(self):
        """Cardinalidade 1 sozinha também passaria se o par aparecesse em dois
        eventos apenas. O par existe do instante em que a L3 da origem o grava
        até o instante em que a L3 do destino o remove — e em nenhum evento
        fora dessa janela, porque fora dela não há pacote."""
        com_logico = [i for i, e in enumerate(self.eventos) if e.logico]
        primeiro, ultimo = com_logico[0], com_logico[-1]

        self.assertEqual(
            (self.eventos[primeiro].dispositivo, self.eventos[primeiro].acao),
            ("H1", "ENCAPSULA"),
        )
        self.assertEqual(
            (self.eventos[ultimo].dispositivo, self.eventos[ultimo].acao),
            ("H4", "DESENCAPSULA"),
        )
        self.assertEqual(com_logico, list(range(primeiro, ultimo + 1)))

    def test_o_cabecalho_h3_no_fio_carrega_sempre_o_mesmo_par(self):
        """O fato, não o retrato: `H3` viaja dentro da PDU e é o que os
        roteadores leem para decidir a rota. Se algum salto o reescrevesse, a
        cardinalidade seria a mesma nos eventos e diferente aqui."""
        conteudos = {bloco(e, "H3").conteudo for e in self.eventos if bloco(e, "H3")}
        self.assertEqual(conteudos, {"{}:{}".format(*PAR_LOGICO_C2)})

    def test_o_cabecalho_h3_acompanha_o_pacote_por_todos_os_saltos(self):
        """A contrapartida da cardinalidade: o mesmo par em poucos eventos não
        provaria travessia. `H3` está presente nos cinco dispositivos da rota
        — e nas duas estações que só escutam o segmento de difusão."""
        dispositivos = {e.dispositivo for e in self.eventos if bloco(e, "H3")}
        self.assertEqual(
            sorted(dispositivos), ["H1", "H2", "H4", "H5", "R1", "R3", "R4"]
        )

    def test_a_camada_3_grava_o_par_logico_uma_unica_vez(self):
        """A garantia estrutural da seção 4.4/R3, no ponto exato em que ela
        vale: `CamadaRede.descer` é o único código que escreve o par lógico num
        pacote, e em C2 ele roda uma vez. Os três roteadores chamam `roteia`,
        que lê o cabeçalho e não o toca."""
        original = camadas.CamadaRede.descer
        gravacoes = []

        def contando(self, pdu, ctx):
            gravacoes.append((ctx.logico_origem, ctx.logico_destino))
            return original(self, pdu, ctx)

        with mock.patch.object(camadas.CamadaRede, "descer", contando):
            executar_caso(carregar_topologia(), "C2")

        self.assertEqual(gravacoes, [PAR_LOGICO_C2])


class ParFisicoEmC2(unittest.TestCase):
    """Cardinalidade 4: um par físico por salto, nenhum reaproveitado."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C2")

    def test_o_conjunto_de_pares_fisicos_tem_cardinalidade_quatro(self):
        """O critério da seção 13.3, na letra."""
        self.assertEqual(len(pares_fisicos(self.eventos)), 4)

    def test_cada_par_fisico_e_o_das_interfaces_do_seu_salto(self):
        """Cardinalidade 4 diria só que os pares são quatro. Estes quatro: as
        interfaces que a topologia põe em cada ponta de cada enlace da rota, na
        ordem em que o quadro os percorre."""
        esperado = tuple(
            fisico_do_salto(self.topo, origem, destino) for origem, destino in SALTOS_C2
        )
        self.assertEqual(pares_fisicos_em_ordem(self.eventos), esperado)

    def test_nenhum_endereco_fisico_de_um_salto_reaparece_noutro(self):
        """Não só os pares são distintos: as oito pontas também são oito
        interfaces diferentes. Um par novo montado com a interface de saída do
        salto anterior seria um quadro reescrito, não refeito (R2)."""
        pontas = [p for par in pares_fisicos_em_ordem(self.eventos) for p in par]
        self.assertEqual(len(pontas), 8)
        self.assertEqual(len(set(pontas)), 8)

    def test_o_cabecalho_h2_no_fio_concorda_com_o_par_fisico_do_evento(self):
        """`H2` grava destino antes de origem (seção 3.3); o par do evento é
        (origem, destino). A inversão é a conferência: se o evento espelhasse
        outra coisa que não o cabeçalho, os dois lados não casariam."""
        conferidos = 0
        for evento in self.eventos:
            cabecalho = bloco(evento, "H2")
            if cabecalho is None or evento.fisico is None:
                continue
            destino, origem = cabecalho.conteudo.split(";")
            self.assertEqual(
                (origem, destino),
                (evento.fisico.origem, evento.fisico.destino),
                evento.linha(),
            )
            conferidos += 1
        self.assertEqual(conferidos, 14)

    def test_o_par_fisico_so_aparece_nas_camadas_1_e_2(self):
        """O endereço físico vale um enlace: quem o vê é quem o usa. As três
        linhas `ROTEIA` de roteador decidem o salto seguinte sem par físico
        nenhum — ele só nasce no `ENQUADRA` que vem depois."""
        for evento in self.eventos:
            if evento.fisico is not None:
                self.assertIn(evento.camada, (1, 2), evento.linha())

    def test_as_estacoes_que_ignoram_o_quadro_nao_criam_um_quinto_par(self):
        """H2 e H5 recebem o quadro do seu segmento de difusão e o descartam
        por endereço (seção 7.5). Elas leem o par físico do salto em que estão
        — não o reescrevem —, então ficarem de fora do registro padrão não muda
        a conta: 4 com elas, 4 sem elas."""
        secundarios = [e for e in self.eventos if e.secundario]
        principais = [e for e in self.eventos if not e.secundario]
        self.assertTrue(secundarios)
        self.assertEqual(pares_fisicos(secundarios) - pares_fisicos(principais), set())
        self.assertEqual(len(pares_fisicos(principais)), 4)


class Cardinalidade(unittest.TestCase):
    """O 4 de C2 é o número de enlaces da rota, não uma constante do motor — e
    o 1 do par lógico é o número de fluxos. Sem este contraste, um motor que
    devolvesse sempre quatro pares físicos passaria em T-R3."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()

    def cardinalidades(self, caso: str) -> tuple[int, int]:
        eventos = executar_caso(self.topo, caso)
        return len(pares_logicos(eventos)), len(pares_fisicos(eventos))

    def test_c1_um_enlace_um_par_fisico(self):
        """Entrega direta H1→H2: um salto só, e nenhum roteador no caminho para
        refazer o quadro."""
        self.assertEqual(self.cardinalidades("C1"), (1, 1))

    def test_c2_quatro_enlaces_quatro_pares_fisicos(self):
        self.assertEqual(self.cardinalidades("C2"), (1, 4))

    def test_c7_tres_segmentos_nao_multiplicam_os_pares(self):
        """Doze quadros pelos mesmos quatro enlaces: a cardinalidade conta
        valores distintos, não travessias. Cada segmento repete os quatro pares
        — e o par lógico continua um, porque o fluxo é um."""
        self.assertEqual(self.cardinalidades("C7"), (1, 4))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
