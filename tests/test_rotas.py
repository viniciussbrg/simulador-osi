"""T-ROTA — rotas da tabela 6.5 (issue #26).

Seção 6.5 da proposta técnica: para a topologia de referência (Anexo A), o
roteamento tem de produzir exatamente estes caminhos e custos —

    | Caso | Origem → Destino          | Caminho        | Custo |
    | C1   | H1 → H2                   | direto na Rede A | 0   |
    | C2   | H1 → H4                   | R1 → R4 → R3    | 2     |
    | C4   | H1 → H4, sem enlace R1–R4 | R1 → R2 → R3    | 3     |
    | C5   | H1 → 10.0.9.10            | sem rota (descarte em R1) | — |

Cada verificação é feita por dois caminhos independentes que precisam
concordar:

- **pelas tabelas de encaminhamento (issue #19)** — percorre-se a topologia
  como um pacote: a decisão binária da seção 6.3 no computador de origem e,
  a cada roteador, a consulta por prefixo mais longo da seção 6.2, até a
  rede de destino ficar diretamente conectada (ou a consulta não casar
  nenhum prefixo, que é o "sem rota" de C5 — seção 6.6);
- **pela árvore de menor caminho (issue #18)** — lê-se o `caminho` e o
  `custo` direto do resultado do Dijkstra entre o roteador de entrada e o
  último roteador do trajeto.

Origem, destino e eventos externos saem do próprio `topologia.json` (bloco
`casos`) — não são recodificados aqui. C4 herda os fluxos de C2 e traz um
evento `enlace_fora` sobre `E-R1-R4`; o teste aplica esse evento
(`com_enlace_ativo`, issue #22) e confere que a rota **muda** de C2 para C4,
que é o que garante o recálculo dinâmico e não só o cálculo inicial.

A validação do desempate determinístico é T-ROTA vizinha em espírito mas
mora em `test_desempate.py` (issue #21); a troca de estado de enlace em si,
em `test_enlace_estado.py` (issue #22). Aqui o foco é a tabela 6.5.

Executar:  python -m unittest tests.test_rotas
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia

_DESTINO_SEM_REDE = "10.0.9.10"  # C5: nenhuma rede da topologia contém este /24


class _SemRota(Exception):
    """Um roteador do trajeto não encontrou prefixo compatível para o destino
    (seção 6.6) — na camada 3 isso vira `DESCARTA`. Carrega o roteador onde o
    trajeto morreu."""

    def __init__(self, roteador: str):
        super().__init__(roteador)
        self.roteador = roteador


def _logico(topo, dispositivo: str, interface: str = "eth0") -> str:
    """O endereço lógico de uma interface de um dispositivo da topologia."""
    disp = topo.dispositivo(dispositivo)
    return next(i.logico for i in disp.interfaces if i.nome == interface)


def _roteador_por_logico(topo, logico: str) -> str:
    """O nome do dispositivo dono da interface de endereço `logico`. Traduz o
    próximo salto de uma `RotaEncaminhamento` — que é um IP — no nome do
    roteador seguinte, para remontar o trajeto salto a salto."""
    for d in topo.dispositivos:
        if any(i.logico == logico for i in d.interfaces):
            return d.nome
    raise KeyError(logico)


def _destino_logico(topo, fluxo) -> str:
    """O endereço lógico de destino de um fluxo: o da interface do dispositivo
    de destino (C1–C4) ou o literal `logico` quando o destino é só um endereço
    inalcançável (C5)."""
    if fluxo.destino.logico is not None:
        return fluxo.destino.logico
    return _logico(topo, fluxo.destino.dispositivo)


def _com_eventos_externos(topo, caso):
    """A topologia com os `eventos_externos` do caso já aplicados. Só
    `enlace_fora` afeta rota (C4); `erro_bit` (C6) é transmissão, não
    roteamento, e é ignorado aqui."""
    for evento in caso.eventos_externos:
        if evento.tipo == "enlace_fora":
            topo = topo.com_enlace_ativo(evento.enlace, ativo=False)
    return topo


def _trajeto_por_tabelas(topo, origem: str, destino_logico: str):
    """Percorre a topologia como um pacote de `origem` (um computador) até
    `destino_logico`, seguindo a seção 6.3 no computador e as tabelas de
    encaminhamento (seção 6.2) em cada roteador.

    Devolve `(roteadores, custo)`:
      - `roteadores` — nomes dos roteadores atravessados, em ordem; lista
        vazia quando o computador entrega direto (C1);
      - `custo` — o custo que a tabela do **primeiro** roteador atribui à
        rede de destino (a coluna "Custo" da tabela 6.5); 0 na entrega direta.

    Levanta `_SemRota` quando um roteador do trajeto não casa nenhum prefixo
    (C5)."""
    decisao = topo.decisao_computador(origem, destino_logico)
    if decisao.entrega_direta:
        return [], 0

    atual = _roteador_por_logico(topo, decisao.proximo_salto)
    roteadores = [atual]
    custo_entrada = None
    while True:
        rota = topo.tabela_encaminhamento(atual).consulta(destino_logico)
        if rota is None:
            raise _SemRota(atual)
        if custo_entrada is None:
            custo_entrada = rota.custo
        if rota.diretamente_conectada:
            return roteadores, custo_entrada
        atual = _roteador_por_logico(topo, rota.proximo_salto)
        if atual in roteadores:
            raise AssertionError(f"laço de encaminhamento: {roteadores + [atual]}")
        roteadores.append(atual)


class RotasPelasTabelasDeEncaminhamento(unittest.TestCase):
    """Cada linha da tabela 6.5, percorrida salto a salto pelas tabelas de
    encaminhamento (issue #19). Origem, destino e eventos externos vêm do
    bloco `casos` do `topologia.json`."""

    def setUp(self):
        self.topo = carregar_topologia()

    def _trajeto(self, caso_id: str):
        caso = self.topo.caso(caso_id)
        topo = _com_eventos_externos(self.topo, caso)
        fluxo = caso.fluxos[0]
        return _trajeto_por_tabelas(
            topo, fluxo.origem.dispositivo, _destino_logico(topo, fluxo)
        )

    def test_c1_entrega_direta_na_rede_a_custo_zero(self):
        # H1 e H2 estão na mesma Rede A: o computador entrega direto, nenhum
        # roteador entra no caminho.
        roteadores, custo = self._trajeto("C1")
        self.assertEqual(roteadores, [])
        self.assertEqual(custo, 0)

    def test_c2_r1_r4_r3_custo_2(self):
        roteadores, custo = self._trajeto("C2")
        self.assertEqual(roteadores, ["R1", "R4", "R3"])
        self.assertEqual(custo, 2)

    def test_c4_recalcula_de_r1_r4_r3_para_r1_r2_r3(self):
        # Sem evento externo, C4 herda o fluxo de C2 e daria o mesmo trajeto...
        self.assertEqual(self._trajeto("C2"), (["R1", "R4", "R3"], 2))
        # ...mas com E-R1-R4 fora (evento externo de C4) o recálculo desvia
        # por R2, e o custo sobe de 2 para 3.
        roteadores, custo = self._trajeto("C4")
        self.assertEqual(roteadores, ["R1", "R2", "R3"])
        self.assertEqual(custo, 3)

    def test_c5_sem_rota_trajeto_morre_em_r1(self):
        caso = self.topo.caso("C5")
        destino = caso.fluxos[0].destino.logico
        self.assertEqual(destino, _DESTINO_SEM_REDE)
        # A consulta de R1 a 10.0.9.10 não casa nenhum prefixo (seção 6.6)...
        self.assertIsNone(self.topo.tabela_encaminhamento("R1").consulta(destino))
        # ...e o percurso termina em R1, sem nenhum roteador posterior.
        with self.assertRaises(_SemRota) as ctx:
            self._trajeto("C5")
        self.assertEqual(ctx.exception.roteador, "R1")


class CaminhoDoDijkstra(unittest.TestCase):
    """A mesma tabela 6.5 lida direto da árvore de menor caminho (issue #18),
    sem passar pelas tabelas de encaminhamento — as duas visões do roteamento
    têm de concordar."""

    def setUp(self):
        self.topo = carregar_topologia()

    def test_c1_h1_alcanca_h2_pela_rede_a_a_custo_zero(self):
        salto = self.topo.arvore_caminhos("H1").salto("H2")
        self.assertEqual(salto.custo, 0)
        self.assertEqual(salto.caminho, ("H1", "H2"))

    def test_c2_r1_alcanca_r3_por_r4_a_custo_2(self):
        # R3 é o último roteador do trajeto de C2 (entrega H4 localmente pela
        # Rede C); o caminho entre roteadores é R1 → R4 → R3.
        salto = self.topo.arvore_caminhos("R1").salto("R3")
        self.assertEqual(salto.caminho, ("R1", "R4", "R3"))
        self.assertEqual(salto.custo, 2)
        # E o custo total até o próprio H4 também é 2 (a Rede C não soma).
        self.assertEqual(self.topo.arvore_caminhos("R1").salto("H4").custo, 2)

    def test_c4_com_e_r1_r4_fora_r1_alcanca_r3_por_r2_a_custo_3(self):
        caido = self.topo.com_enlace_ativo("E-R1-R4", ativo=False)
        salto = caido.arvore_caminhos("R1").salto("R3")
        self.assertEqual(salto.caminho, ("R1", "R2", "R3"))
        self.assertEqual(salto.custo, 3)
        # A topologia original fica intacta — o trajeto curto de C2 continua lá.
        self.assertEqual(
            self.topo.arvore_caminhos("R1").salto("R3").caminho, ("R1", "R4", "R3")
        )

    def test_c5_nenhum_roteador_tem_rota_para_a_rede_inexistente(self):
        # 10.0.9.0/24 não é rede da topologia: nenhuma tabela a resolve.
        for nome, tabela in self.topo.tabelas_encaminhamento().items():
            with self.subTest(roteador=nome):
                self.assertIsNone(tabela.consulta(_DESTINO_SEM_REDE))


if __name__ == "__main__":
    unittest.main()
