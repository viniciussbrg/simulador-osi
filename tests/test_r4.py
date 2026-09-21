"""T-R4 — a camada de enlace nunca escolhe rota (issue #38).

R4 separa duas perguntas que a Aula 2 insiste em distinguir: *por onde o
pacote segue* (camada 3, com a tabela de encaminhamento na mão) e *para qual
placa deste segmento entregá-lo agora* (camada 2, que recebe o vizinho pronto
e só escreve o par de endereços físicos do salto).

O critério da issue — nenhum evento com `camada == 2` e ação `ROTEIA` — é
necessário, mas sozinho seria quase tautológico: `ROTEIA` nem pertence ao
vocabulário da camada 2 em `constantes.py`, e a fila recusa o agendamento.
Um teste que só conferisse isso ficaria verde mesmo que a camada 2 passasse a
consultar a tabela por conta própria e a emitir a decisão sob outro nome.

Por isso o arquivo confere R4 em três alturas:

- **vocabulário e estrutura** — `ROTEIA` fora da camada 2, `CamadaEnlace` sem
  método de roteamento, e a guarda da fila recusando de fato o agendamento
  proibido (guarda ativa, não comentário);
- **registro** — o critério literal da issue, em todos os casos da topologia;
- **comportamento** — o par de endereços físicos que a camada 2 grava em cada
  `ENQUADRA` é exatamente o do salto que a camada 3 decidiu, recalculado aqui
  de forma independente a partir de `rede.py`. Se a camada 2 escolhesse o
  vizinho sozinha, é aqui que a divergência apareceria.

Executar:  python -m unittest tests.test_r4
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from camadas import CamadaEnlace, CamadaRede
from constantes import ACOES_POR_CAMADA
from dispositivos import AcaoCamada
from rede import Topologia, carregar_topologia
from simulador import (
    ErroDeSimulacao,
    FilaEventos,
    casos_executaveis,
    executar_caso,
    topologia_do_caso,
)


def fisico_da_interface(topologia: Topologia, dispositivo: str, interface: str) -> str:
    alvo = topologia.dispositivo(dispositivo)
    return next(i.fisico for i in alvo.interfaces if i.nome == interface)


def fisico_do_logico(topologia: Topologia, logico: str) -> str:
    for dispositivo in topologia.dispositivos:
        for interface in dispositivo.interfaces:
            if interface.logico == logico:
                return interface.fisico
    raise AssertionError(f"nenhuma interface tem o endereço lógico {logico}")


def salto_da_camada_3(
    topologia: Topologia, dispositivo: str, destino: str
) -> tuple[str, str]:
    """O par físico do próximo salto, derivado **só** do que a camada 3 teria
    consultado: a tabela de encaminhamento, no roteador, e a decisão binária da
    seção 6.3, no computador. Nenhum dado do registro entra nesta conta."""
    alvo = topologia.dispositivo(dispositivo)
    if alvo.tipo == "roteador":
        rota = topologia.tabela_encaminhamento(dispositivo).consulta(destino)
        assert rota is not None, f"{dispositivo} não tem rota para {destino}"
        # Rede diretamente conectada: o próximo salto é o próprio destino.
        proximo = rota.proximo_salto or destino
        interface = rota.interface_saida
    else:
        decisao = topologia.decisao_computador(dispositivo, destino)
        proximo, interface = decisao.proximo_salto, decisao.interface_saida
    return (
        fisico_da_interface(topologia, dispositivo, interface),
        fisico_do_logico(topologia, proximo),
    )


class VocabularioEEstrutura(unittest.TestCase):
    """R4 antes da execução: a ação não existe para a camada 2."""

    def test_roteia_pertence_a_camada_3_e_nao_a_camada_2(self):
        self.assertIn("ROTEIA", ACOES_POR_CAMADA[3])
        self.assertNotIn("ROTEIA", ACOES_POR_CAMADA[2])

    def test_a_camada_de_enlace_nao_tem_metodo_de_roteamento(self):
        """A camada 3 tem `roteia`; a 2 não tem método nenhum equivalente —
        não é que ele exista sem uso, é que não existe."""
        self.assertTrue(hasattr(CamadaRede, "roteia"))
        self.assertFalse(hasattr(CamadaEnlace, "roteia"))

    def test_a_fila_recusa_agendar_roteia_na_camada_2(self):
        """A guarda é ativa: a tentativa falha na chamada que errou, não trinta
        eventos depois."""
        fila = FilaEventos()
        acao = AcaoCamada(
            dispositivo="R1", camada=2, acao="ROTEIA", sentido="desce", tamanho=92
        )
        with self.assertRaises(ErroDeSimulacao):
            fila.agendar_acao(0, acao, "rota escolhida pelo enlace", fluxo="F1")

    def test_a_fila_aceita_as_acoes_legitimas_da_camada_2(self):
        """Contraprova da guarda anterior: o que a camada 2 realmente emite
        passa, de modo que a recusa acima é da ação e não do agendamento."""
        fila = FilaEventos()
        for nome in sorted(ACOES_POR_CAMADA[2]):
            acao = AcaoCamada(
                dispositivo="R1", camada=2, acao=nome, sentido="desce", tamanho=92
            )
            fila.agendar_acao(0, acao, f"ação {nome}", fluxo="F1")
        self.assertEqual(len(fila), len(ACOES_POR_CAMADA[2]))


class RegistroDosCasos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        # C6 depende de intervenção externa ainda não aplicada e é
        # recusado pelo motor até lá.
        cls.eventos = {
            caso: executar_caso(cls.topo, caso)
            for caso in casos_executaveis(cls.topo)
        }
        # A rota tem de ser recalculada sobre a topologia que o caso usou: em
        # C4 o enlace R1–R4 está fora, e a topologia original daria o salto que
        # o caso justamente não fez.
        cls.topologia_de = {
            caso: topologia_do_caso(cls.topo, cls.topo.caso(caso))
            for caso in cls.eventos
        }

    def test_nenhum_evento_de_camada_2_roteia(self):
        """O critério de aceitação da issue, em todos os casos que rodam hoje —
        C3 concorre dois fluxos e C7 repete o percurso três vezes."""
        for caso, eventos in self.eventos.items():
            for evento in eventos:
                if evento.camada == 2:
                    with self.subTest(caso=caso, passo=evento.passo):
                        self.assertNotEqual(evento.acao, "ROTEIA", evento.linha())

    def test_toda_acao_de_camada_2_pertence_ao_vocabulario_dela(self):
        """Fecha a porta lateral: rotear sob outro nome também violaria R4, e
        qualquer ação nova teria de passar por `constantes.py`."""
        for caso, eventos in self.eventos.items():
            for evento in eventos:
                if evento.camada == 2:
                    with self.subTest(caso=caso, passo=evento.passo):
                        self.assertIn(evento.acao, ACOES_POR_CAMADA[2])

    def test_todo_enquadra_vem_depois_de_uma_decisao_de_camada_3(self):
        """A ordem que R4 impõe ao registro: o dispositivo decide na camada 3 e
        só então enquadra. Um `ENQUADRA` sem decisão anterior no mesmo
        dispositivo seria a camada 2 escolhendo sozinha."""
        for caso, eventos in self.eventos.items():
            for posicao, evento in enumerate(eventos):
                if evento.acao != "ENQUADRA":
                    continue
                anteriores = [
                    e
                    for e in eventos[:posicao]
                    if e.dispositivo == evento.dispositivo
                    and e.camada == 3
                    and e.fluxo == evento.fluxo
                ]
                with self.subTest(caso=caso, passo=evento.passo):
                    self.assertTrue(anteriores, evento.linha())
                    self.assertIn(
                        anteriores[-1].acao, ("ROTEIA", "ENCAPSULA")
                    )

    def test_o_par_fisico_e_o_salto_que_a_camada_3_escolheu(self):
        """O coração do teste: para cada `ENQUADRA`, o par de endereços físicos
        gravado pela camada 2 é recalculado a partir da tabela de
        encaminhamento e da decisão da seção 6.3 — sem olhar para o registro."""
        for caso, eventos in self.eventos.items():
            for evento in eventos:
                if evento.acao != "ENQUADRA":
                    continue
                esperado = salto_da_camada_3(
                    self.topologia_de[caso],
                    evento.dispositivo,
                    evento.logico.destino,
                )
                with self.subTest(caso=caso, passo=evento.passo):
                    self.assertEqual(
                        (evento.fisico.origem, evento.fisico.destino), esperado
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
