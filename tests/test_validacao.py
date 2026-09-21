"""T-TOP — validação semântica da topologia (V-01..V-10, issue #23).

As dez verificações da seção 5.7 da proposta técnica exigem uma mensagem
legível e específica para cada tipo de arquivo inválido — nunca um
rastreamento de pilha (numa máquina Windows sem Python o traceback é
ilegível). Cada teste aqui parte da topologia de referência, quebra **um**
ponto, e confere que a mensagem da `ErroTopologia` é a da tabela 5.7.

Este arquivo é o companheiro de implementação da issue #23; o T-TOP formal
(issue #25) carrega os dez arquivos inválidos de `tests/fixtures/`, mas
exercita exatamente estas mensagens. A localização do arquivo (`pasta_base`,
issue #24) tem testes próprios em `tests/test_localizacao.py`.

Executar:  python -m unittest tests.test_validacao
"""

import copy
import json
import os
import sys
import unittest
from pathlib import Path

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from rede import ErroTopologia, analisar_topologia, carregar_topologia

_ARQUIVO_REFERENCIA = os.path.join(_RAIZ, "topologia.json")

with open(_ARQUIVO_REFERENCIA, encoding="utf-8") as _arquivo:
    _REFERENCIA = json.load(_arquivo)


def topologia_base() -> dict:
    """Cópia fresca da topologia de referência, para cada teste quebrar à
    vontade sem contaminar o teste seguinte."""
    return copy.deepcopy(_REFERENCIA)


def dispositivo(dados: dict, nome: str) -> dict:
    for d in dados["dispositivos"]:
        if d["nome"] == nome:
            return d
    raise AssertionError(f"dispositivo {nome} ausente da topologia de referência")


def enlace(dados: dict, ident: str) -> dict:
    for e in dados["enlaces"]:
        if e["id"] == ident:
            return e
    raise AssertionError(f"enlace {ident} ausente da topologia de referência")


def caso(dados: dict, ident: str) -> dict:
    for c in dados["casos"]:
        if c["id"] == ident:
            return c
    raise AssertionError(f"caso {ident} ausente da topologia de referência")


class TopologiaDeReferencia(unittest.TestCase):
    """A topologia do Anexo A tem de passar por todas as dez verificações."""

    def test_referencia_carrega_sem_erro(self):
        topologia = carregar_topologia(_ARQUIVO_REFERENCIA)
        self.assertEqual(len(topologia.dispositivos), 9)
        self.assertEqual(len(topologia.casos), 7)


class ValidacoesSemanticas(unittest.TestCase):
    """Uma quebra por teste; a mensagem é a da tabela 5.7."""

    def quebra(self, dados: dict) -> str:
        with self.assertRaises(ErroTopologia) as capturado:
            analisar_topologia(dados)
        return str(capturado.exception)

    # V-01 — nomes de dispositivo únicos
    def test_v01_nome_de_dispositivo_duplicado(self):
        dados = topologia_base()
        copia = copy.deepcopy(dispositivo(dados, "H2"))
        copia["nome"] = "H1"
        dados["dispositivos"].append(copia)
        self.assertIn("Dispositivo duplicado: H1", self.quebra(dados))

    # V-02 — endereços físicos únicos em toda a topologia
    def test_v02_endereco_fisico_repetido(self):
        dados = topologia_base()
        fisico = dispositivo(dados, "H1")["interfaces"][0]["fisico"]
        dispositivo(dados, "H2")["interfaces"][0]["fisico"] = fisico
        self.assertIn(f"Endereço físico repetido: {fisico}", self.quebra(dados))

    # V-03 — endereços lógicos únicos
    def test_v03_endereco_logico_repetido(self):
        dados = topologia_base()
        logico = dispositivo(dados, "H1")["interfaces"][0]["logico"]
        dispositivo(dados, "H2")["interfaces"][0]["logico"] = logico
        self.assertIn(f"Endereço lógico repetido: {logico}", self.quebra(dados))

    # V-04 — cada interface citada em exatamente um enlace
    def test_v04_interface_sem_enlace(self):
        dados = topologia_base()
        dispositivo(dados, "H1")["interfaces"].append(
            {
                "nome": "eth9",
                "rede": "A",
                "logico": "10.0.1.99",
                "mascara": 24,
                "fisico": "AA:BB:CC:00:00:99",
            }
        )
        self.assertIn(
            "Interface H1.eth9 não pertence a nenhum enlace", self.quebra(dados)
        )

    def test_v04_interface_em_dois_enlaces(self):
        dados = topologia_base()
        difusao = enlace(dados, "E-A")
        ponta = copy.deepcopy(difusao["pontas"][0])
        enlace(dados, "E-B")["pontas"].append(ponta)
        mensagem = self.quebra(dados)
        self.assertIn(
            f"Interface {ponta['dispositivo']}.{ponta['interface']}", mensagem
        )
        self.assertIn("mais de um enlace", mensagem)

    def test_v04_enlace_cita_interface_inexistente(self):
        dados = topologia_base()
        enlace(dados, "E-A")["pontas"][0]["interface"] = "eth9"
        self.assertIn("eth9", self.quebra(dados))

    # V-05 — endereço lógico contido no prefixo da sua rede
    def test_v05_logico_fora_do_prefixo_da_rede(self):
        dados = topologia_base()
        dispositivo(dados, "H1")["interfaces"][0]["logico"] = "10.0.7.10"
        self.assertIn("10.0.7.10 não pertence a 10.0.1.0/24", self.quebra(dados))

    # V-06 — custos inteiros >= 0
    def test_v06_custo_negativo(self):
        dados = topologia_base()
        enlace(dados, "E-R1-R4")["custo"] = -1
        self.assertIn("Custo inválido no enlace E-R1-R4", self.quebra(dados))

    # V-07 — grafo conexo
    def test_v07_dispositivo_inalcancavel(self):
        dados = topologia_base()
        dados["redes"].append(
            {"id": "Z", "prefixo": "10.0.8.0/24", "rotulo": "Ilha"}
        )
        for i, nome in enumerate(("R8", "R9"), start=1):
            dados["dispositivos"].append(
                {
                    "nome": nome,
                    "tipo": "roteador",
                    "posicao": {"x": 900, "y": 900},
                    "interfaces": [
                        {
                            "nome": "s0",
                            "rede": "Z",
                            "logico": f"10.0.8.{i}",
                            "mascara": 24,
                            "fisico": f"AA:BB:CC:88:88:0{i}",
                        }
                    ],
                }
            )
        dados["enlaces"].append(
            {
                "id": "E-R8-R9",
                "tipo": "ponto-a-ponto",
                "rede": "Z",
                "custo": 1,
                "ativo": True,
                "rotulo": "Ilha",
                "pontas": [
                    {"dispositivo": "R8", "interface": "s0"},
                    {"dispositivo": "R9", "interface": "s0"},
                ],
            }
        )
        mensagem = self.quebra(dados)
        self.assertIn("A topologia possui dispositivos inalcançáveis:", mensagem)
        self.assertIn("R8", mensagem)
        self.assertIn("R9", mensagem)

    # V-08 — todo dispositivo citado em `casos` existe
    def test_v08_caso_referencia_dispositivo_inexistente(self):
        dados = topologia_base()
        caso(dados, "C2")["fluxos"][0]["destino"]["dispositivo"] = "H9"
        self.assertIn(
            "O caso C2 referencia dispositivo inexistente: H9", self.quebra(dados)
        )

    def test_v08_caso_com_destino_so_logico_e_valido(self):
        """C5 aponta para 10.0.9.10, um endereço sem dispositivo — é o caso de
        destino inalcançável, não um erro de arquivo."""
        topologia = analisar_topologia(topologia_base())
        self.assertEqual(topologia.caso("C5").fluxos[0].destino.logico, "10.0.9.10")

    # V-09 — todo computador tem `gateway` em sua própria rede
    def test_v09_gateway_fora_da_rede_local(self):
        dados = topologia_base()
        dispositivo(dados, "H1")["gateway"] = "10.0.2.1"
        self.assertIn("Gateway de H1 fora da rede local", self.quebra(dados))

    # V-10 — limite_segmento comporta os casos de segmento único
    def test_v10_limite_segmento_pequeno_demais(self):
        dados = topologia_base()
        dados["parametros"]["limite_segmento"] = 40  # 42 + 4 de L5 = 46 não cabe
        mensagem = self.quebra(dados)
        self.assertIn("limite_segmento incompatível com o caso", mensagem)

    def test_v10_limite_de_referencia_aceita_c7(self):
        """C7 (180 octetos) segmenta de propósito — não pode disparar V-10."""
        topologia = analisar_topologia(topologia_base())
        self.assertEqual(topologia.parametros.limite_segmento, 64)


if __name__ == "__main__":
    unittest.main()
