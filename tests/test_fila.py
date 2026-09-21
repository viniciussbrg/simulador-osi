"""Fila de eventos do motor (issue #28).

A issue não pede teste dedicado — ela é cobrada indiretamente por T-FMT (issue
#34, ordem exata das primeiras linhas de C2) e pelo critério de C3 (issue #44,
campo `fluxo` alternando entre F1 e F2). Só que nenhum dos dois existe ainda, e
as três garantias que a fila vende — desempate por ordem de inserção,
intercalação por salto e numeração global contínua — são exatamente do tipo que
passa desapercebido até o registro sair torto. Este arquivo as prende agora, em
eventos sintéticos, sem depender de `rede.py` nem da topologia.

Quando T-FMT e T-C3 chegarem, eles cobrem a fila *em uso*; este teste continua
cobrindo a fila *isolada*, inclusive os casos que nenhum caso obrigatório
exercita (agendamento no passado, ação fora do vocabulário da camada).

Executar:  python -m unittest tests.test_fila
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from dispositivos import AcaoCamada
from evento import Enlace, Evento
from simulador import CAMADA_SISTEMA, DISPOSITIVO_SISTEMA, ErroDeSimulacao, FilaEventos


def _campos(dispositivo="H1", camada=7, acao="GERA", descricao="…", **extras) -> dict:
    """Os campos mínimos de um evento válido, para agendar sem ruído."""
    base = {
        "dispositivo": dispositivo,
        "camada": camada,
        "acao": acao,
        "descricao": descricao,
        "tamanho": 42,
    }
    base.update(extras)
    return base


def _salto(fila: FilaEventos, instante: int, dispositivo: str, fluxo: str) -> None:
    """Um salto estilizado — `TRANSMITE` na origem, `RECEBE` no destino —, o
    suficiente para observar a intercalação sem montar a pilha inteira."""
    fila.agendar(
        instante, **_campos(dispositivo, 1, "TRANSMITE", "736 bits", fluxo=fluxo)
    )


class TestOrdenacao(unittest.TestCase):
    def test_mesmo_instante_sai_na_ordem_de_insercao(self):
        fila = FilaEventos()
        for camada, acao in ((7, "GERA"), (6, "CODIFICA"), (5, "ABRE")):
            fila.agendar(0, **_campos(camada=camada, acao=acao))
        self.assertEqual(
            [e.acao for e in fila.drenar()], ["GERA", "CODIFICA", "ABRE"]
        )

    def test_instante_menor_sai_primeiro_ainda_que_inserido_depois(self):
        fila = FilaEventos()
        fila.agendar(5, **_campos(descricao="tarde"))
        fila.agendar(1, **_campos(descricao="cedo"))
        self.assertEqual([e.descricao for e in fila.drenar()], ["cedo", "tarde"])

    def test_ordem_de_insercao_desempata_entre_instantes_iguais(self):
        """Dois eventos no mesmo instante nunca podem trocar de lugar entre
        execuções — é o que torna o registro reproduzível (T-FMT)."""
        for _ in range(50):
            fila = FilaEventos()
            for i in range(12):
                fila.agendar(3, **_campos(descricao=f"evento {i}"))
            self.assertEqual(
                [e.descricao for e in fila.drenar()],
                [f"evento {i}" for i in range(12)],
            )

    def test_agendar_e_drenar_podem_ser_intercalados(self):
        fila = FilaEventos()
        fila.agendar(0, **_campos(descricao="primeiro"))
        primeiro = fila.proximo()
        fila.agendar(1, **_campos(descricao="segundo"))
        segundo = fila.proximo()
        self.assertEqual((primeiro.passo, segundo.passo), (1, 2))
        self.assertIsNone(fila.proximo())
        self.assertTrue(fila.vazia)

    def test_agendar_no_passado_e_erro(self):
        fila = FilaEventos()
        fila.agendar(4, **_campos())
        fila.proximo()
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(3, **_campos())
        fila.agendar(4, **_campos())  # o mesmo instante continua válido


class TestIntercalacaoDeFluxos(unittest.TestCase):
    """C3: dois fluxos concorrentes, intercalados pelo mesmo mecanismo de fila,
    alternando a cada salto — sem que o código do caso mude (decisão D5)."""

    def test_fluxos_agendados_em_bloco_saem_intercalados_por_salto(self):
        fila = FilaEventos()
        # O motor executa F1 inteiro e só depois F2: a ordem de produção é
        # F1,F1,F1,F2,F2,F2 — a de registro, não.
        for fluxo in ("F1", "F2"):
            for salto, dispositivo in enumerate(("H1", "R1", "R4")):
                _salto(fila, salto, dispositivo, fluxo)
        self.assertEqual(
            [(e.fluxo, e.dispositivo) for e in fila.drenar()],
            [
                ("F1", "H1"), ("F2", "H1"),
                ("F1", "R1"), ("F2", "R1"),
                ("F1", "R4"), ("F2", "R4"),
            ],
        )

    def test_fluxo_unico_degenera_em_sequencial(self):
        """C1, C2, C5 e C7 usam a mesma fila sem nenhuma intercalação: a ordem
        de saída é a ordem de inserção, salto a salto."""
        fila = FilaEventos()
        esperado = [("H1", 0), ("R1", 1), ("R4", 2), ("R3", 3), ("H4", 4)]
        for dispositivo, salto in esperado:
            _salto(fila, salto, dispositivo, "F1")
        eventos = fila.drenar()
        self.assertEqual([e.dispositivo for e in eventos], [d for d, _ in esperado])
        self.assertEqual([e.passo for e in eventos], [1, 2, 3, 4, 5])


class TestNumeracaoDePassos(unittest.TestCase):
    def test_passo_e_global_continuo_iniciado_em_1(self):
        fila = FilaEventos()
        for salto, dispositivo in enumerate(("H1", "R1", "H4")):
            for camada in (3, 2, 1):
                fila.agendar(
                    salto,
                    **_campos(dispositivo, camada, {3: "ROTEIA", 2: "ENQUADRA", 1: "TRANSMITE"}[camada]),
                )
        eventos = fila.drenar()
        self.assertEqual([e.passo for e in eventos], list(range(1, 10)))

    def test_numeracao_nao_reinicia_por_fluxo(self):
        fila = FilaEventos()
        for fluxo in ("F1", "F2"):
            _salto(fila, 0, "H1", fluxo)
        self.assertEqual([e.passo for e in fila.drenar()], [1, 2])

    def test_evento_secundario_nao_consome_passo(self):
        """Seção 7.5 e Anexo B: o quadro que H2 recebe e ignora não pode
        empurrar a numeração, senão o registro padrão salta de 008 para 010 e
        deixa de bater com o enunciado."""
        fila = FilaEventos()
        fila.agendar(0, **_campos("H1", 1, "TRANSMITE", "736 bits", fluxo="F1"))
        fila.agendar(
            0,
            **_campos("H2", 1, "RECEBE", "736 bits", fluxo="F1", secundario=True),
        )
        fila.agendar(
            0,
            **_campos(
                "H2", 2, "IGNORA", "endereço alheio",
                tamanho=None, fluxo="F1", secundario=True, estado="descartado",
            ),
        )
        fila.agendar(0, **_campos("R1", 1, "RECEBE", "736 bits", fluxo="F1"))

        eventos = fila.drenar()
        self.assertEqual([e.passo for e in eventos], [1, 1, 1, 2])
        principais = [e for e in eventos if not e.secundario]
        self.assertEqual([e.passo for e in principais], [1, 2])
        self.assertEqual(fila.emitidos, 2)

    def test_secundario_herda_o_passo_do_proprio_fluxo(self):
        fila = FilaEventos()
        _salto(fila, 0, "H1", "F1")   # passo 1
        _salto(fila, 0, "H2", "F2")   # passo 2
        fila.agendar(
            0, **_campos("H3", 1, "RECEBE", "alheio", fluxo="F1", secundario=True)
        )
        eventos = fila.drenar()
        self.assertEqual([e.passo for e in eventos], [1, 2, 1])

    def test_secundario_sem_principal_e_erro(self):
        fila = FilaEventos()
        fila.agendar(
            0, **_campos("H2", 1, "RECEBE", "alheio", fluxo="F1", secundario=True)
        )
        with self.assertRaises(ErroDeSimulacao):
            fila.drenar()


class TestGuardasDeInsercao(unittest.TestCase):
    def test_acao_fora_do_vocabulario_da_camada(self):
        """Vocabulário fechado (seção 7.4): `ROTEIA` é da camada 3, e a fila é o
        funil por onde todo evento passa — logo é onde a regra se cobra."""
        fila = FilaEventos()
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(0, **_campos("R1", 2, "ROTEIA", "não pode (R4)"))
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(0, **_campos("H1", 7, "INVENTA", "ação inexistente"))

    def test_camada_inexistente(self):
        fila = FilaEventos()
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(0, **_campos("H1", 8, "GERA", "não existe camada 8"))

    def test_campo_fora_do_contrato_de_evento(self):
        fila = FilaEventos()
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(0, **_campos(velocidade="100 Mbps"))

    def test_passo_nao_pode_ser_agendado(self):
        """Quem passasse `passo` estaria numerando por conta própria."""
        fila = FilaEventos()
        with self.assertRaisesRegex(ErroDeSimulacao, "passo"):
            fila.agendar(0, **_campos(passo=7))

    def test_campo_obrigatorio_ausente(self):
        fila = FilaEventos()
        campos = _campos()
        del campos["descricao"]
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(0, **campos)

    def test_evento_de_camada_sem_tamanho_e_erro(self):
        fila = FilaEventos()
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(0, **_campos("H1", 3, "ENCAPSULA", "sem octetos", tamanho=None))

    def test_descartes_da_camada_2_podem_nao_ter_tamanho(self):
        """C6: `R3 | L2 | DESCARTA` sai sem sufixo de octetos — nada foi
        extraído do quadro (seção 10)."""
        fila = FilaEventos()
        fila.agendar(
            0,
            **_campos(
                "R3", 2, "DESCARTA", "verificação de erro incorreta, quadro Q3 descartado",
                tamanho=None, estado="erro", fluxo="F1",
            ),
        )
        (evento,) = fila.drenar()
        self.assertEqual(
            evento.linha(),
            "001 | R3 | L2 | DESCARTA | verificação de erro incorreta, "
            "quadro Q3 descartado",
        )

    def test_instante_negativo_e_nao_inteiro(self):
        fila = FilaEventos()
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(-1, **_campos())
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar(1.5, **_campos())


class TestConveniencias(unittest.TestCase):
    def test_agendar_acao_completa_os_campos_que_a_camada_nao_sabe(self):
        acao = AcaoCamada(
            dispositivo="H1",
            camada=1,
            acao="TRANSMITE",
            sentido="desce",
            tamanho=92,
            bits=736,
            enlace=Enlace("E-A", "H1–R1"),
            quadro="Q1",
        )
        fila = FilaEventos()
        fila.agendar_acao(
            0, acao, "736 bits no enlace H1–R1", fluxo="F1", caminho=("E-A",)
        )
        (evento,) = fila.drenar()
        self.assertEqual(evento.passo, 1)
        self.assertEqual(evento.fluxo, "F1")
        self.assertEqual(evento.descricao, "736 bits no enlace H1–R1")
        self.assertEqual(evento.caminho, ("E-A",))
        # E nada do que a camada sabia se perdeu no caminho:
        self.assertEqual(evento.bits, 736)
        self.assertEqual(evento.quadro, "Q1")
        self.assertEqual(evento.enlace.rotulo, "H1–R1")
        self.assertEqual(evento.sentido, "desce")

    def test_agendar_acao_nao_deixa_campo_do_contrato_de_fora(self):
        """Se um campo entrar no `Evento` sem entrar em `AcaoCamada` nem na
        assinatura de `agendar_acao`, é aqui que se descobre — e não na tela,
        depois de F4."""
        acao = AcaoCamada(
            dispositivo="H1", camada=7, acao="GERA", sentido="desce", tamanho=42
        )
        fila = FilaEventos()
        fila.agendar_acao(0, acao, "…", fluxo="F1")
        (evento,) = fila.drenar()
        preenchiveis = {"passo", "descricao", "fluxo", "caminho", "metricas"}
        for campo in acao.campos_de_evento():
            self.assertTrue(hasattr(evento, campo))
        ausentes = {
            f for f in Evento.__dataclass_fields__
            if f not in acao.campos_de_evento() and f not in preenchiveis
        }
        self.assertEqual(ausentes, set(), f"campos sem quem os preencha: {ausentes}")

    def test_agendar_sistema(self):
        fila = FilaEventos()
        fila.agendar_sistema(
            9, "ENLACE_FORA", "enlace R1–R4 indisponível, rotas recalculadas"
        )
        (evento,) = fila.drenar()
        self.assertEqual(evento.dispositivo, DISPOSITIVO_SISTEMA)
        self.assertEqual(evento.camada, CAMADA_SISTEMA)
        self.assertIsNone(evento.tamanho)
        self.assertEqual(
            evento.linha(),
            "001 | -- | -- | ENLACE_FORA | enlace R1–R4 indisponível, "
            "rotas recalculadas",
        )

    def test_fila_vazia(self):
        fila = FilaEventos()
        self.assertTrue(fila.vazia)
        self.assertEqual(len(fila), 0)
        self.assertEqual(fila.drenar(), ())
        self.assertIsNone(fila.proximo())

    def test_len_conta_pendentes(self):
        fila = FilaEventos()
        fila.agendar(0, **_campos())
        fila.agendar(1, **_campos())
        self.assertEqual(len(fila), 2)
        fila.proximo()
        self.assertEqual(len(fila), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
