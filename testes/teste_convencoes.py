"""Confere as convencoes de simulacao contra a tabela oficial de validacao.

Os valores esperados sao os publicados no repositorio da disciplina. Este
teste nao executa a simulacao completa: verifica apenas que as convencoes
adotadas (tamanho de cada cabecalho, limite de segmentacao e posicao do
cabecalho de sessao) produzem os octetos transmitidos e a eficiencia
esperados em cada caso.

Executar com:  python testes/teste_convencoes.py
"""

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

with open(os.path.join(RAIZ, "topologia.json"), encoding="utf-8") as arquivo:
    CONVENCOES = json.load(arquivo)["convencoes"]

CAB = CONVENCOES["cabecalhos"]
FINALIZADOR = CONVENCOES["finalizador_camada_2"]
LIMITE = CONVENCOES["limite_segmento_octetos"]
LIMIAR = CONVENCOES["limiar_segmentacao_octetos"]

# Sobrecarga que acompanha cada segmento em cada enlace:
# transporte + rede + enlace (cabecalho e finalizador).
POR_SEGMENTO = CAB["4"] + CAB["3"] + CAB["2"] + FINALIZADOR


def segmentar(mensagem_em_octetos):
    """Divide a mensagem em segmentos de ate LIMITE octetos.

    O cabecalho de sessao entra uma unica vez, antes da segmentacao, e e
    dividido junto com os dados. E essa convencao que faz uma mensagem de
    100 octetos produzir segmentos de 40, 40 e 24, e nao de 40, 40 e 28.
    """
    total = mensagem_em_octetos + CAB["5"]

    # Abaixo do limiar a mensagem segue inteira, em um unico segmento. E o
    # que ocorre com a mensagem de referencia de 42 octetos, que chega a
    # camada 4 com 46 e e registrada como "segmento 1 de 1".
    if total <= LIMIAR:
        return [total]

    segmentos = []
    while total > 0:
        pedaco = min(LIMITE, total)
        segmentos.append(pedaco)
        total -= pedaco
    return segmentos


def octetos_transmitidos(mensagem, enlaces):
    """Soma os octetos que trafegam em todos os enlaces percorridos."""
    return sum((s + POR_SEGMENTO) * enlaces for s in segmentar(mensagem))


def eficiencia(entregues, transmitidos):
    """Fracao da transmissao ocupada por dados uteis que chegaram ao destino.

    O numerador e a mensagem original entregue, sem o cabecalho de sessao: o
    que o usuario quis enviar, e nao o que a pilha acrescentou. Quando nada
    e entregue, o numerador e zero e a eficiencia tambem: e assim que E5 e E6
    valem eta = 0 na tabela de validacao, apesar de terem transmitido
    octetos pela rede.
    """
    return entregues / transmitidos


# Caso: (descricao, octetos da mensagem, octetos entregues ao destino,
#        enlaces percorridos por segmento, quadros esperados, octetos
#        esperados, eficiencia esperada)
CASOS = [
    ("E1 entrega direta",            42,  42, 1, 1,  92, 45.7),
    ("E2 entrega indireta",          42,  42, 4, 4, 368, 11.4),
    ("E3 demultiplexacao",           84,  84, 4, 8, 736, 11.4),
    ("E4 falha de enlace",           42,  42, 4, 4, 368, 11.4),
    # E5 descarta na camada 3 de R1 e E6 na camada 2 de R3: transmitem
    # octetos, mas nao entregam nenhum.
    ("E5 destino inalcancavel",      42,   0, 1, 1,  92,  0.0),
    ("E6 erro de bit",               42,   0, 3, 3, 276,  0.0),
    ("E7 mensagem longa",           100, 100, 4, 12, 968, 10.3),
]


def executar():
    falhas = 0
    print(f"{'Caso':<26}{'Quadros':>8}{'Octetos':>10}{'Eficiencia':>13}   ")
    print("-" * 62)

    for nome, mensagem, entregues, enlaces, quadros_esp, octetos_esp, efic_esp in CASOS:
        # E3 sao dois fluxos independentes; cada um segmenta por conta propria.
        fluxos = 2 if nome.startswith("E3") else 1
        por_fluxo = mensagem // fluxos

        segmentos = segmentar(por_fluxo)
        quadros = len(segmentos) * enlaces * fluxos
        octetos = octetos_transmitidos(por_fluxo, enlaces) * fluxos
        efic = round(eficiencia(entregues, octetos) * 100, 1)

        ok_quadros = quadros == quadros_esp
        ok_octetos = octetos == octetos_esp
        ok_efic = efic == efic_esp
        passou = ok_quadros and ok_octetos and ok_efic
        falhas += 0 if passou else 1

        exibida = f"{efic:.1f}%"
        marca = "ok" if passou else "FALHOU"
        print(f"{nome:<26}{quadros:>8}{octetos:>10}{exibida:>13}   {marca}")

        if not passou:
            print(f"   esperado: {quadros_esp} quadros, {octetos_esp} octetos, {efic_esp}%")

    print("-" * 62)
    print(f"segmentacao de 100 octetos: {segmentar(100)}  (esperado [40, 40, 24])")
    print(f"segmentacao de 42 octetos:  {segmentar(42)}  (esperado [46], um unico segmento)")
    print(f"sobrecarga por segmento por enlace: {POR_SEGMENTO} octetos")
    print("todos os casos conferem" if falhas == 0 else f"{falhas} caso(s) divergente(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
