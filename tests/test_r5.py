"""T-R5 — simetria de inserção/remoção de cabeçalhos (issue #15).

Cada cabeçalho que uma camada insere na descida é removido **exatamente uma
vez**, pela mesma camada (mesmo número gravado em `Bloco.camada`), e no
**escopo certo** (proposta técnica, seções 4.4/R5, 7.4 e 13.3):

- o cabeçalho de enlace (H2 e o finalizador T2) é criado e destruído a cada
  salto — removido no vizinho imediato;
- os cabeçalhos das camadas 3 a 5 (H3, H4, H5) só são removidos no destino
  final, nunca num roteador intermediário — que não tem sequer as camadas
  4 a 7 para isso (reforço de R1).

As camadas 1, 6 e 7 não participam: `TRANSMITE`/`RECEBE`,
`CODIFICA`/`DECIFRA` e `GERA`/`ENTREGA` não inserem moldura (o que produzem
é metadado, não octeto — contabilidade da seção 3.2 da proposta técnica).

Duas frentes, conforme os dois caminhos que a própria issue sugere
("instrumentar (ou usar diretamente) os eventos gerados"):

- `TestSimetriaEstrutural` instrumenta o ponto exato onde R5 é garantida —
  `conferir_camada`, chamada em toda remoção de moldura: por
  `pdu.PDU.remover_cabecalho` para as camadas 3 a 5 e, diretamente, pela
  camada 2 para H2 e T2. Conta as remoções reais e as confronta com as
  inserções (uma por `ABRE`/`SEGMENTA`/`ENCAPSULA`/`ENQUADRA`). Vale para
  C1, C2 e C7 — inclusive a segmentação, em que a remontagem funde as N
  remoções de H4 numa única linha `REMONTA`.
- `TestSimetriaNosEventos` usa a lista de eventos: pareia cada quadro pelo
  identificador (Q1, Q2, …) e verifica o dispositivo de cada remoção.

A fonte dos eventos é o **motor** (`simulador.executar_caso`), fechado em F3 —
é o que o programa realmente produz. O encadeador de `tests/encadeamento.py`
segue como oráculo isolado de F1. A rota de cada caso, usada para conferir o
escopo das remoções, é derivada da **topologia** (tabela de encaminhamento e
decisão da seção 6.3), nunca do registro sob teste: tirá-la dos próprios
eventos tornaria a verificação circular.

Executar:  python -m unittest tests.test_r5
"""

import os
import sys
import unittest
from collections import Counter
from unittest import mock

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

import camadas
import pdu
from dispositivos import logico_do_extremo
from rede import Topologia, carregar_topologia
from simulador import comparacao_de_referencia, executar_caso

_TOPOLOGIA = carregar_topologia()


def eventos_do_caso(caso: str) -> tuple:
    """O registro completo do caso, direto do motor."""
    return executar_caso(_TOPOLOGIA, caso)


def _dono_do_logico(topologia: Topologia, logico: str) -> str:
    for dispositivo in topologia.dispositivos:
        for interface in dispositivo.interfaces:
            if interface.logico == logico:
                return dispositivo.nome
    raise AssertionError(f"nenhum dispositivo tem o endereço lógico {logico}")


def rota_do_caso(caso: str) -> tuple[str, ...]:
    """A sequência de dispositivos de um fluxo, da origem ao destino, derivada
    da topologia: a decisão binária da seção 6.3 no computador e a tabela de
    encaminhamento em cada roteador — o mesmo que a camada 3 consultaria."""
    fluxo = _TOPOLOGIA.caso(caso).fluxos[0]
    destino = logico_do_extremo(_TOPOLOGIA, fluxo.destino)
    atual = fluxo.origem.dispositivo
    rota = [atual]
    while not any(
        i.logico == destino for i in _TOPOLOGIA.dispositivo(atual).interfaces
    ):
        if _TOPOLOGIA.dispositivo(atual).tipo == "roteador":
            entrada = _TOPOLOGIA.tabela_encaminhamento(atual).consulta(destino)
            assert entrada is not None, f"{atual} sem rota para {destino}"
            proximo = entrada.proximo_salto or destino
        else:
            proximo = _TOPOLOGIA.decisao_computador(atual, destino).proximo_salto
        atual = _dono_do_logico(_TOPOLOGIA, proximo)
        rota.append(atual)
    return tuple(rota)

# C1 e C2 são o critério de aceitação da issue; C7 ("idealmente, uma vez que
# F4 esteja disponível") já passa porque o encadeador de F1 percorre a
# segmentação por inteiro.
CASOS_TESTADOS = ("C1", "C2", "C7")

# Ação de descida que insere moldura -> número da camada que a inseriu.
INSERCAO_POR_ACAO = {"ABRE": 5, "SEGMENTA": 4, "ENCAPSULA": 3, "ENQUADRA": 2}

# Ação de subida que remove moldura -> número da camada que a remove. A
# camada 4 aparece com dois rótulos porque a escolha entre `REMONTA` e
# `DEMULTIPLEXA` cabe a quem monta o Evento, não à `CamadaTransporte` (ver
# docstring de `CamadaTransporte.subir`).
REMOCAO_POR_ACAO = {
    "ENCERRA": 5,
    "REMONTA": 4,
    "DEMULTIPLEXA": 4,
    "DESENCAPSULA": 3,
    "DESENQUADRA": 2,
}

# Blocos de moldura que cada camada tira por remoção: a camada 2 retira o
# cabeçalho H2 **e** o finalizador T2 no mesmo `DESENQUADRA`; as demais, um
# cabeçalho só.
BLOCOS_DE_MOLDURA_POR_REMOCAO = {5: 1, 4: 1, 3: 1, 2: 2}

# Ações de subida que removem moldura de enlace (camada 2, a cada salto) e
# moldura superior (camadas 3 a 5, só no destino) — derivadas de
# REMOCAO_POR_ACAO para não haver duas listas a manter em sincronia.
REMOCOES_DE_ENLACE = frozenset(a for a, c in REMOCAO_POR_ACAO.items() if c == 2)
REMOCOES_SUPERIORES = frozenset(a for a, c in REMOCAO_POR_ACAO.items() if c >= 3)


class _RegistroDeRemocoes:
    """Espião em `conferir_camada` — a trava estrutural de R5 (issue #13),
    chamada em **toda** remoção de moldura. Fica nos dois módulos que
    referenciam o nome: `pdu` (via `PDU.remover_cabecalho`, camadas 3 a 5) e
    `camadas` (diretamente na `CamadaEnlace.subir`, para H2 e T2).

    Não altera comportamento: encaminha a chamada para a função real (a
    conferência de R5 continua ativa) e só contabiliza qual camada removeu."""

    def __enter__(self) -> "_RegistroDeRemocoes":
        self.por_camada: Counter[int] = Counter()
        real = pdu.conferir_camada

        def espiao(bloco, camada_removedora):
            real(bloco, camada_removedora)  # mantém a trava de R5 de pé
            self.por_camada[camada_removedora] += 1

        self._patches = [
            mock.patch.object(pdu, "conferir_camada", espiao),
            mock.patch.object(camadas, "conferir_camada", espiao),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc) -> None:
        for p in self._patches:
            p.stop()


def _remocoes_esperadas(eventos) -> Counter:
    """Quantas remoções de moldura cada camada deve fazer, deduzidas das
    inserções: uma por ação de descida, vezes o nº de blocos que a camada par
    retira (2 na camada de enlace, 1 nas demais).

    Mais as remoções que **não** têm inserção correspondente: num segmento de
    difusão, cada estação não endereçada também sobe o quadro pela camada 2 —
    é lendo o H2 que ela descobre que o destino físico não é o seu e emite
    `IGNORA` (secundário, seção 7.5). A moldura é removida ali como em
    qualquer subida; o que não acontece é a entrega do pacote à camada 3.

    Estes eventos não existiam no encadeador de F1, que não modelava difusão:
    apareceram quando a fonte passou a ser o motor, e são a razão de C2 ter
    doze remoções de camada 2, e não oito — quatro saltos entregues mais dois
    quadros inspecionados e descartados por endereço."""
    insercoes: Counter[int] = Counter()
    alheias = 0
    for ev in eventos:
        camada = INSERCAO_POR_ACAO.get(ev.acao)
        if camada is not None:
            insercoes[camada] += 1
        if ev.acao == "IGNORA":
            alheias += 1
    esperadas = Counter(
        {c: n * BLOCOS_DE_MOLDURA_POR_REMOCAO[c] for c, n in insercoes.items()}
    )
    if alheias:
        esperadas[2] += alheias * BLOCOS_DE_MOLDURA_POR_REMOCAO[2]
    return esperadas


class TestSimetriaEstrutural(unittest.TestCase):
    """Critério 1 da issue: toda inserção de cabeçalho de camada N tem
    exatamente uma remoção de camada N."""

    @classmethod
    def setUpClass(cls):
        # Executar um caso executa também os de referência de C1/C2, para a
        # comparação da seção 11.4 que viaja no evento `METRICAS` — uma vez por
        # topologia, memoizada. Instrumentar as camadas sem aquecer esse cache
        # contaria as execuções auxiliares junto com a que se quer medir.
        comparacao_de_referencia(_TOPOLOGIA)

    def test_toda_insercao_tem_uma_remocao_da_mesma_camada(self):
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                with _RegistroDeRemocoes() as reg:
                    eventos = eventos_do_caso(caso)

                self.assertEqual(
                    dict(reg.por_camada),
                    dict(_remocoes_esperadas(eventos)),
                    f"{caso}: remoções de moldura não batem com as inserções",
                )

    def test_so_as_camadas_2_a_5_mexem_em_moldura(self):
        # L1, L6 e L7 não inserem nem removem cabeçalho — o que produzem é
        # metadado, não octeto (seção 3.2 da proposta técnica). Se `conferir_camada`
        # fosse chamada para camada 1, 6 ou 7, haveria moldura onde não
        # deveria existir.
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                with _RegistroDeRemocoes() as reg:
                    eventos_do_caso(caso)
                self.assertEqual(
                    set(reg.por_camada) - {2, 3, 4, 5},
                    set(),
                    f"{caso}: remoção de moldura fora das camadas 2 a 5",
                )

    def test_c2_contagem_de_referencia(self):
        # Anexo B: 1 sessão, 1 segmento, 1 pacote, 4 quadros. A camada 2 tira
        # H2+T2 em cada um dos 4 saltos (8 remoções) e mais uma vez em cada
        # estação que inspeciona o quadro e o ignora por endereço — H2 na Rede
        # A e H5 na Rede C (4 remoções). Cada camada superior, uma só, no
        # destino.
        with _RegistroDeRemocoes() as reg:
            eventos_do_caso("C2")
        self.assertEqual(dict(reg.por_camada), {5: 1, 4: 1, 3: 1, 2: 12})

    def test_c7_segmentacao_nao_perde_nenhum_h4(self):
        # 3 segmentos: 3 inserções de H4 (SEGMENTA) e 3 remoções reais de H4,
        # ainda que a remontagem só emita uma linha REMONTA (D5). 4 saltos por
        # segmento -> 12 quadros -> 24 remoções na camada 2, mais 12 das seis
        # inspeções por endereço (duas por segmento, uma em cada ponta).
        with _RegistroDeRemocoes() as reg:
            eventos_do_caso("C7")
        self.assertEqual(dict(reg.por_camada), {5: 1, 4: 3, 3: 3, 2: 36})


class TestSimetriaNosEventos(unittest.TestCase):
    """Critério 2 da issue: cada remoção acontece no escopo correto —
    vizinho imediato para a camada 2, destino final para as camadas 3 a 5."""

    def _eventos_e_rota(self, caso):
        return eventos_do_caso(caso), rota_do_caso(caso)

    def test_cada_quadro_enquadrado_e_desenquadrado_uma_vez(self):
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                eventos, _ = self._eventos_e_rota(caso)
                enquadrados = [ev.quadro for ev in eventos if ev.acao == "ENQUADRA"]
                desenquadrados = [
                    ev.quadro for ev in eventos if ev.acao in REMOCOES_DE_ENLACE
                ]

                self.assertCountEqual(
                    enquadrados, desenquadrados,
                    f"{caso}: conjunto de quadros enquadrados ≠ desenquadrados",
                )
                self.assertEqual(
                    len(enquadrados), len(set(enquadrados)),
                    f"{caso}: mesmo identificador de quadro enquadrado duas vezes (R2)",
                )
                self.assertEqual(
                    len(desenquadrados), len(set(desenquadrados)),
                    f"{caso}: mesmo quadro desenquadrado duas vezes",
                )

    def test_quadro_removido_no_vizinho_imediato(self):
        # Escopo de R5 na camada 2: ENQUADRA num nó, DESENQUADRA no nó
        # seguinte da rota — o cabeçalho de enlace não atravessa um salto.
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                eventos, rota = self._eventos_e_rota(caso)
                saltos = set(zip(rota, rota[1:]))

                origem_do_quadro = {
                    ev.quadro: ev.dispositivo
                    for ev in eventos
                    if ev.acao == "ENQUADRA"
                }
                for ev in eventos:
                    if ev.acao != "DESENQUADRA":
                        continue
                    origem = origem_do_quadro[ev.quadro]
                    self.assertIn(
                        (origem, ev.dispositivo), saltos,
                        f"{caso}: quadro {ev.quadro} enquadrado em {origem}, "
                        f"desenquadrado em {ev.dispositivo} — não é um salto",
                    )

    def test_cabecalhos_superiores_removidos_so_no_destino_final(self):
        # Escopo de R5 nas camadas 3 a 5 e, pela mesma tabela, reforço de R1:
        # DESENCAPSULA / ENCERRA / REMONTA / DEMULTIPLEXA só no destino, nunca
        # num roteador intermediário.
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                eventos, rota = self._eventos_e_rota(caso)
                destino = rota[-1]
                intermediarios = set(rota[1:-1])

                for ev in eventos:
                    if ev.acao not in REMOCOES_SUPERIORES:
                        continue
                    self.assertEqual(
                        ev.dispositivo, destino,
                        f"{caso}: {ev.acao} em {ev.dispositivo}, esperado só em {destino}",
                    )
                    self.assertNotIn(
                        ev.dispositivo, intermediarios,
                        f"{caso}: {ev.acao} num roteador intermediário viola R5/R1",
                    )

    def test_sessao_abre_e_encerra_exatamente_uma_vez(self):
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                eventos, _ = self._eventos_e_rota(caso)
                abre = [ev.sessao for ev in eventos if ev.acao == "ABRE"]
                encerra = [ev.sessao for ev in eventos if ev.acao == "ENCERRA"]
                self.assertEqual(abre, ["S-0001"], f"{caso}: ABRE não emitido uma vez só")
                self.assertEqual(encerra, ["S-0001"], f"{caso}: ENCERRA não pareia com ABRE")

    def test_l3_encapsula_e_desencapsula_pareiam(self):
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                eventos, _ = self._eventos_e_rota(caso)
                encapsula = sum(1 for ev in eventos if ev.acao == "ENCAPSULA")
                desencapsula = sum(1 for ev in eventos if ev.acao == "DESENCAPSULA")
                self.assertEqual(
                    encapsula, desencapsula,
                    f"{caso}: {encapsula} ENCAPSULA para {desencapsula} DESENCAPSULA",
                )

    def test_l4_todas_as_insercoes_de_h4_consumidas_na_remontagem(self):
        # A camada 4 insere um H4 por segmento (SEGMENTA) e os remove todos na
        # subida. O encadeador de F1 — como o motor, D5 — funde essas remoções
        # numa única linha REMONTA, cujo `segmento` (total, total) atesta que
        # todos os `total` segmentos (logo todos os H4) foram vistos.
        for caso in CASOS_TESTADOS:
            with self.subTest(caso=caso):
                eventos, _ = self._eventos_e_rota(caso)
                segmenta = [ev for ev in eventos if ev.acao == "SEGMENTA"]
                totais = {ev.segmento.total for ev in segmenta}
                self.assertEqual(len(totais), 1, f"{caso}: total de segmentos inconsistente")
                total = totais.pop()
                self.assertEqual(
                    len(segmenta), total,
                    f"{caso}: {len(segmenta)} SEGMENTA para um total declarado de {total}",
                )

                remonta = [ev for ev in eventos if ev.acao == "REMONTA"]
                self.assertEqual(len(remonta), 1, f"{caso}: REMONTA deve ser uma única linha (D5)")
                self.assertEqual((remonta[0].segmento.n, remonta[0].segmento.total), (total, total))


if __name__ == "__main__":
    unittest.main()
