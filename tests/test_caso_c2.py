"""Caso C2 — entrega indireta, H1 → H4 via R1→R4→R3 (issue #30).

O caso central do projeto: quatro enlaces, quatro quadros, um pacote, um
segmento. É dele que sai o Anexo B, e é contra ele que as cinco restrições
estruturais são conferidas — C1 não serve para isso porque não tem roteador
nenhum no caminho, e C5 morre no primeiro salto.

A implementação de C2 não custou código próprio: o percurso de `_Execucao`
(issue #29) é o mesmo de C1, e o que muda é a topologia decidir que o destino
está noutra rede. Isto é o esperado — se C2 exigisse um ramo de código só
dele, o motor estaria codificando casos em vez de executá-los (seção 5.5,
"os casos vão no arquivo"). O que este arquivo faz é **prender** o resultado:
as trinta linhas do registro padrão, salto a salto, e os seis critérios da
seção 10/C2.

A comparação caractere a caractere das doze primeiras linhas com o enunciado é
T-FMT (issue #34) — aqui a conferência é por campo, que é o que localiza a
divergência. O trigésimo primeiro evento, `031 | -- | -- | METRICAS`, fecha o
registro desde a issue #43; os valores que ele publica são conferidos por
T-MET.

Executar:  python -m unittest tests.test_caso_c2
"""

import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:  # permite rodar o arquivo direto, além de `-m unittest`
    sys.path.insert(0, _RAIZ)

from rede import carregar_topologia
from simulador import executar_caso, principais

# O registro padrão do Anexo B, linhas 001 a 030, como (dispositivo, camada,
# ação, tamanho). O tamanho entra porque é a contabilidade de octetos da
# seção 7.4: 42 na L7/L6, +4 na L5, +8 na L4, +20 na L3, +14+4 na L2 — e a
# subida desfaz na ordem inversa.
ANEXO_B = (
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
    ("R1", 3, "ROTEIA", 74),
    ("R1", 2, "ENQUADRA", 92),
    ("R1", 1, "TRANSMITE", 92),
    ("R4", 1, "RECEBE", 92),
    ("R4", 2, "DESENQUADRA", 74),
    ("R4", 3, "ROTEIA", 74),
    ("R4", 2, "ENQUADRA", 92),
    ("R4", 1, "TRANSMITE", 92),
    ("R3", 1, "RECEBE", 92),
    ("R3", 2, "DESENQUADRA", 74),
    ("R3", 3, "ROTEIA", 74),
    ("R3", 2, "ENQUADRA", 92),
    ("R3", 1, "TRANSMITE", 92),
    ("H4", 1, "RECEBE", 92),
    ("H4", 2, "DESENQUADRA", 74),
    ("H4", 3, "DESENCAPSULA", 54),
    ("H4", 4, "REMONTA", 46),
    ("H4", 5, "ENCERRA", 42),
    ("H4", 6, "DECIFRA", 42),
    ("H4", 7, "ENTREGA", 42),
    ("--", 0, "METRICAS", None),
)


# O evento `METRICAS` fecha toda execução (issue #43): é de sistema, camada 0,
# sem fluxo. Os testes abaixo falam do percurso da mensagem, então olham o
# último evento **de camada** — `desfecho` — em vez do último da lista.

def desfecho(eventos):
    """O último evento de camada do registro, ignorando o `METRICAS` final."""
    return next(e for e in reversed(eventos) if e.camada > 0)


class CasoC2(unittest.TestCase):
    """O registro inteiro de C2, executado uma vez para a classe — a execução é
    determinística e nenhum teste a altera."""

    @classmethod
    def setUpClass(cls):
        cls.topo = carregar_topologia()
        cls.eventos = executar_caso(cls.topo, "C2")
        cls.registro = principais(cls.eventos)
        cls.roteadores = {d.nome for d in cls.topo.dispositivos if d.tipo == "roteador"}

    def linha_de(self, passo: int):
        return next(e for e in self.registro if e.passo == passo)

    # -- o registro do Anexo B --------------------------------------------

    def test_o_registro_padrao_tem_as_trinta_e_uma_linhas_do_anexo_b(self):
        """Trinta linhas de camada mais o `METRICAS`; os `IGNORA` de H2 e H5
        existem na execução e ficam de fora do registro padrão."""
        self.assertEqual(len(self.registro), len(ANEXO_B))

    def test_cada_linha_bate_com_o_anexo_b(self):
        obtido = [
            (e.dispositivo, e.camada, e.acao, e.tamanho) for e in self.registro
        ]
        self.assertEqual(obtido, list(ANEXO_B))

    def test_a_mensagem_do_caso_tem_42_octetos(self):
        """A linha 001 depende deste número; o arquivo é a fonte, não o código."""
        mensagem = self.topo.caso("C2").fluxos[0].mensagem
        self.assertEqual(mensagem, "GET /index.html HTTP/1.1 Host: fesa.edu.br")
        self.assertEqual(len(mensagem.encode("utf-8")), 42)

    def test_as_tres_decisoes_de_rota_dos_roteadores(self):
        """As três linhas `ROTEIA` de roteador escritas por extenso na seção
        10/C2: duas por tabela, custo decrescente, e a última diretamente
        conectada — é a rota R1→R4→R3 de custo 2 da tabela 6.5."""
        self.assertEqual(
            self.linha_de(11).descricao, "10.0.3.0/24 via R4, custo 2, interface e1"
        )
        self.assertEqual(
            self.linha_de(16).descricao, "10.0.3.0/24 via R3, custo 1, interface e1"
        )
        self.assertEqual(
            self.linha_de(21).descricao,
            "10.0.3.0/24 diretamente conectada, interface e2",
        )

    def test_o_quadro_percorre_os_quatro_enlaces_da_rota(self):
        self.assertEqual(
            desfecho(self.registro).caminho, ("E-A", "E-R1-R4", "E-R4-R3", "E-C")
        )

    def test_um_unico_pacote_e_um_unico_segmento(self):
        """Quatro quadros, mas um pacote só: a camada 3 encapsula uma vez na
        origem e desencapsula uma vez no destino, e o que os roteadores fazem
        no meio é rotear — nunca reencapsular."""
        acoes = [e.acao for e in self.eventos]
        self.assertEqual(acoes.count("ENCAPSULA"), 1)
        self.assertEqual(acoes.count("DESENCAPSULA"), 1)
        self.assertEqual(acoes.count("SEGMENTA"), 1)
        self.assertEqual(acoes.count("REMONTA"), 1)

    def test_os_quatro_quadros_transmitem_368_octetos(self):
        """368 B = 4 × 92, o total transmitido da tabela 11.3 — a conta que o
        evento `METRICAS` de F4 vai publicar."""
        transmitidos = [e.tamanho for e in self.eventos if e.acao == "TRANSMITE"]
        self.assertEqual(transmitidos, [92, 92, 92, 92])
        self.assertEqual(sum(transmitidos), 368)

    # -- critério de aceitação da seção 10/C2 ------------------------------

    def test_r2_quatro_quadros_distintos_sem_repeticao(self):
        """R2: o quadro é destruído na subida e criado com identificador novo na
        descida — quatro enlaces, quatro identificadores, nenhum reaproveitado."""
        enquadrados = [e.quadro for e in self.eventos if e.acao == "ENQUADRA"]
        self.assertEqual(enquadrados, ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(len(set(enquadrados)), 4)

    def test_r3_par_logico_unico_em_toda_a_execucao(self):
        """R3, metade fixa: gravado uma vez pela camada 3 da origem, nenhum
        roteador o reescreve."""
        pares = {(e.logico.origem, e.logico.destino) for e in self.eventos if e.logico}
        self.assertEqual(pares, {("10.0.1.10", "10.0.3.10")})

    def test_r3_par_fisico_muda_a_cada_salto(self):
        """R3, metade local: quatro enlaces, quatro pares físicos distintos."""
        pares = {(e.fisico.origem, e.fisico.destino) for e in self.eventos if e.fisico}
        self.assertEqual(len(pares), 4)

    def test_r1_nenhum_evento_de_roteador_tem_contexto_superior(self):
        """R1: o roteador não tem as camadas 4 a 7, então porta, sessão e
        processo não têm de onde sair num evento dele."""
        for evento in self.eventos:
            if evento.dispositivo in self.roteadores:
                self.assertIsNone(evento.porta, evento.linha())
                self.assertIsNone(evento.sessao, evento.linha())
                self.assertIsNone(evento.processo, evento.linha())

    def test_r4_nenhuma_linha_de_camada_2_roteia(self):
        """R4: quem escolhe rota é a camada 3; a camada 2 recebe o vizinho
        pronto, pelo contexto."""
        for evento in self.eventos:
            if evento.camada == 2:
                self.assertNotEqual(evento.acao, "ROTEIA", evento.linha())

    def test_as_estacoes_alheias_do_segmento_de_difusao_ignoram_o_quadro(self):
        """H2 (Rede A) e H5 (Rede C) recebem o quadro fisicamente e o descartam
        por endereço: eventos secundários, fora do registro padrão, sem
        consumir número de passo (seção 7.5)."""
        secundarios = [e for e in self.eventos if e.secundario]
        self.assertEqual(
            [(e.dispositivo, e.acao) for e in secundarios],
            [("H2", "RECEBE"), ("H2", "IGNORA"), ("H5", "RECEBE"), ("H5", "IGNORA")],
        )
        self.assertEqual([e.passo for e in secundarios], [8, 8, 23, 23])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
