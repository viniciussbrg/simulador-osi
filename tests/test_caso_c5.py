"""Caso C5 — destino inalcançável, H1 → 10.0.9.10 (issue #31).

O caso que prova que o motor sabe **parar**. A mensagem desce a pilha inteira
de H1, atravessa o segmento de difusão da Rede A e morre na camada 3 de R1: a
consulta à tabela de encaminhamento não encontra prefixo compatível com
`10.0.9.0/24`, a camada 3 devolve `None`, o pacote é destruído e o percurso
acaba ali (seção 6.6).

O que a seção 10/C5 cobra, e este arquivo prende:

- o registro **encerra** com `DESCARTA` na camada 3 de R1, com o pacote ainda
  medindo seus 74 B — ao contrário dos dois descartes da camada 2, aqui há PDU
  para medir, e a linha traz sufixo de octetos;
- **nenhum evento existe depois dela**: nenhum quadro Q2 é construído, nenhuma
  camada superior é acionada (nem existiria em R1, que é roteador — R1);
- 1 enlace percorrido, 1 quadro, 92 B transmitidos e **0 B entregues**.

Dois pontos de estrutura que o caso ilumina de lado:

- **quem descarta é o roteador, nunca o computador de origem.** A tabela de H1
  tem rota padrão `0.0.0.0/0`, que casa com qualquer destino — por isso H1
  encaminha 10.0.9.10 ao gateway sem hesitar. Só R1, com tabela genuinamente
  incompleta, descobre a ausência de rota.
- **destino sem dispositivo é destino legítimo.** C5 é o único caso cujo fluxo
  aponta para um endereço lógico solto, sem processo de destino a nomear: o
  `GERA` da camada 7 sai com a cláusula de destino ausente.

T-C5 (issue #44) acrescenta a conferência das métricas (92 B transmitidos,
η indefinida exibida como 0%) quando o evento `METRICAS` existir (issue #43),
em F4.

Executar:  python -m unittest tests.test_caso_c5
"""

import ipaddress
import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from dispositivos import montar_dispositivos
from rede import carregar_topologia
from simulador import executar_caso, principais

DESTINO_INALCANCAVEL = "10.0.9.10"


def assinatura(eventos) -> list[tuple]:
    return [(e.dispositivo, e.camada, e.acao, e.tamanho) for e in eventos]


# O evento `METRICAS` fecha toda execução (issue #43): é de sistema, camada 0,
# sem fluxo. Os testes abaixo falam do percurso da mensagem, então olham o
# último evento **de camada** — `desfecho` — em vez do último da lista.

def desfecho(eventos):
    """O último evento de camada do registro, ignorando o `METRICAS` final."""
    return next(e for e in reversed(eventos) if e.camada > 0)


class CasoC5(unittest.TestCase):
    """O registro inteiro de C5, executado uma vez para a classe — a execução é
    determinística e nenhum teste a altera."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C5")
        cls.registro = principais(cls.eventos)

    # -- critério de aceitação da seção 10/C5 ------------------------------

    def test_o_registro_encerra_com_o_descarte_na_camada_3_de_r1(self):
        """A linha que a seção 10/C5 escreve por extenso — e o fato de ela ser a
        última do registro."""
        descarte = desfecho(self.registro)
        self.assertEqual(
            (descarte.dispositivo, descarte.camada, descarte.acao,
             descarte.descricao, descarte.tamanho, descarte.estado),
            ("R1", 3, "DESCARTA",
             f"sem rota para {DESTINO_INALCANCAVEL}, pacote descartado",
             74, "descartado"),
        )
        self.assertEqual(
            descarte.linha(),
            f"{descarte.passo:03d} | R1 | L3 | DESCARTA | "
            f"sem rota para {DESTINO_INALCANCAVEL}, pacote descartado      74 B",
        )

    def test_nenhum_evento_existe_depois_do_descarte(self):
        """Nem no registro padrão nem entre os secundários: o `DESCARTA` é o
        último evento produzido pela execução, ponto."""
        self.assertIs(desfecho(self.eventos), desfecho(self.registro))
        self.assertEqual(desfecho(self.eventos).acao, "DESCARTA")

    def test_nenhum_segundo_quadro_e_construido(self):
        """Descarte na camada 3 não reenquadra nada: um `ENQUADRA` só, e o
        identificador de quadro nunca passa de Q1."""
        enquadra = [e for e in self.eventos if e.acao == "ENQUADRA"]
        self.assertEqual(len(enquadra), 1)
        self.assertEqual(enquadra[0].quadro, "Q1")
        self.assertEqual({e.quadro for e in self.eventos if e.quadro}, {"Q1"})

    def test_nenhuma_camada_superior_e_acionada_apos_o_descarte(self):
        """Nada acima da camada 3 age em R1 — e nada volta a agir em lugar
        nenhum depois dele."""
        de_r1 = [e for e in self.eventos if e.dispositivo == "R1"]
        self.assertEqual([e.camada for e in de_r1], [1, 2, 3])
        self.assertEqual([e for e in self.eventos if e.acao == "ENTREGA"], [])

    def test_um_enlace_percorrido(self):
        """O quadro atravessou só a Rede A — o mapa destaca um enlace, e o
        caminho não cresce depois do descarte."""
        self.assertEqual(desfecho(self.registro).caminho, ("E-A",))
        self.assertEqual(
            {enlace for e in self.eventos for enlace in e.caminho}, {"E-A"}
        )

    def test_o_total_transmitido_e_92_octetos_e_o_entregue_e_zero(self):
        """Os dois números da tabela 11.3 para C5: 92 B no ar, 0 B entregues —
        η indefinida, que a interface exibe como 0%."""
        transmitido = sum(e.tamanho for e in self.eventos if e.acao == "TRANSMITE")
        entregue = sum(e.tamanho for e in self.eventos if e.acao == "ENTREGA")
        self.assertEqual(transmitido, 92)
        self.assertEqual(entregue, 0)

    # -- percurso ----------------------------------------------------------

    def test_a_sequencia_de_acoes_e_a_de_uma_descida_interrompida(self):
        self.assertEqual(
            assinatura(self.registro),
            [
                ("H1", 7, "GERA", 42),
                ("H1", 6, "CODIFICA", 42),
                ("H1", 5, "ABRE", 46),
                ("H1", 4, "SEGMENTA", 54),
                ("H1", 3, "ENCAPSULA", 74),
                ("H1", 3, "ROTEIA", 74),
                ("H1", 2, "ENQUADRA", 92),
                ("H1", 1, "TRANSMITE", 92),
                ("R1", 1, "RECEBE", 92),
                ("R1", 2, "DESENQUADRA", 74),
                ("R1", 3, "DESCARTA", 74),
                ("--", 0, "METRICAS", None),
            ],
        )

    def test_so_o_evento_do_descarte_carrega_estado_anormal(self):
        """Até a camada 3 de R1 tudo corre normalmente: o quadro é bem formado,
        a verificação de erro passa. O único desfecho anormal do registro é o
        descarte — é ele que a interface pinta de vermelho."""
        self.assertEqual(
            [e.estado for e in self.registro],
            # O `METRICAS` final volta ao estado normal: não é parte do
            # percurso, é o fechamento da execução.
            ["ok"] * (len(self.registro) - 2) + ["descartado", "ok"],
        )

    def test_o_par_logico_do_descarte_e_o_gravado_na_origem(self):
        """R3: o par lógico é escrito uma única vez, na camada 3 de H1, e chega
        intacto ao roteador que descarta o pacote."""
        encapsula = next(e for e in self.registro if e.acao == "ENCAPSULA")
        descarte = desfecho(self.registro)
        self.assertEqual(encapsula.logico, descarte.logico)
        self.assertEqual(
            descarte.logico.origem, self.topo.dispositivo("H1").interfaces[0].logico
        )
        self.assertEqual(descarte.logico.destino, DESTINO_INALCANCAVEL)

    # -- quem descarta é o roteador, não a origem --------------------------

    def test_a_tabela_de_r1_nao_tem_prefixo_para_o_destino(self):
        """A causa do descarte, conferida na tabela e não só no texto da linha:
        nenhuma das entradas de R1 contém 10.0.9.10."""
        dispositivos = montar_dispositivos(self.topo)
        destino = ipaddress.ip_address(DESTINO_INALCANCAVEL)
        for entrada in dispositivos["R1"].tabela_encaminhamento:
            rede = ipaddress.ip_network(entrada.prefixo, strict=False)
            self.assertNotIn(destino, rede, entrada.prefixo)

    def test_h1_encaminha_ao_gateway_em_vez_de_descartar(self):
        """A origem nunca descarta por conta própria: a rota padrão 0.0.0.0/0 da
        tabela de H1 casa com qualquer destino, inclusive um que não existe."""
        roteia = next(e for e in self.registro if e.acao == "ROTEIA")
        self.assertEqual(roteia.dispositivo, "H1")
        self.assertEqual(
            roteia.descricao, "próximo salto 10.0.1.1 pela interface eth0"
        )
        self.assertEqual(
            [e for e in self.eventos
             if e.dispositivo == "H1" and e.acao == "DESCARTA"],
            [],
        )

    # -- destino sem dispositivo -------------------------------------------

    def test_o_gera_sai_sem_processo_de_destino(self):
        """C5 é o único caso cujo destino é um endereço lógico solto: não há
        processo de destino a nomear, e a cláusula cai em vez de sair vazia."""
        gera = self.registro[0]
        self.assertEqual(gera.acao, "GERA")
        self.assertEqual(gera.descricao, "processo navegador")
        self.assertEqual(gera.processo.origem, "navegador")
        self.assertEqual(gera.processo.destino, "")

    # -- difusão: H2 recebe e ignora ---------------------------------------

    def test_h2_recebe_pelo_segmento_e_ignora_por_endereco(self):
        """H2 está no mesmo segmento de difusão e recebe o quadro fisicamente,
        mas o descarta por endereço — dois eventos secundários, ocultos no
        registro padrão (seção 7.5)."""
        de_h2 = [e for e in self.eventos if e.dispositivo == "H2"]
        self.assertEqual(
            [(e.camada, e.acao, e.secundario) for e in de_h2],
            [(1, "RECEBE", True), (2, "IGNORA", True)],
        )
        self.assertEqual(de_h2[1].estado, "descartado")
        self.assertEqual(de_h2[1].quadro, "Q1")

    def test_a_numeracao_do_registro_segue_sem_buraco(self):
        """Evento secundário não consome passo: o `IGNORA` de H2 acompanha o
        `TRANSMITE` de H1, e os passos vão de 1 a N sem interrupção."""
        transmite = next(e for e in self.registro if e.acao == "TRANSMITE")
        for evento in (e for e in self.eventos if e.secundario):
            self.assertEqual(evento.passo, transmite.passo)
        self.assertEqual(
            [e.passo for e in self.registro], list(range(1, len(self.registro) + 1))
        )

    # -- determinismo ------------------------------------------------------

    def test_duas_execucoes_produzem_o_mesmo_registro(self):
        outra = executar_caso(carregar_topologia(), "C5")
        self.assertEqual([e.linha() for e in outra], [e.linha() for e in self.eventos])

    def test_todo_evento_pertence_ao_fluxo_f1(self):
        """Um fluxo só, e todo evento de camada o carrega. O `METRICAS` final
        resume a execução inteira e não pertence a fluxo nenhum."""
        for evento in self.eventos:
            if evento.camada == 0:
                self.assertIsNone(evento.fluxo, evento.linha())
                continue
            self.assertEqual(evento.fluxo, "F1")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
