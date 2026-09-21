"""Confere a topologia e a escolha de rota contra os valores do enunciado.

Os resultados esperados vem da Tabela 3 da especificacao (as tabelas de
encaminhamento de referencia), do log de exemplo e da descricao dos casos
E1, E2, E4 e E5.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulador.rede import Topologia

# Tabela 3 da especificacao, as doze entradas: para cada roteador e cada
# rede, (proximo salto, interface de saida, custo). "direta" indica rede
# diretamente conectada, cujo custo a tabela de referencia nao atribui.
#
#          Rede A (10.0.1.0/24)   Rede B (10.0.2.0/24)   Rede C (10.0.3.0/24)
#   R1     direta, e0             via R2, e2, custo 2    via R4, e1, custo 2
#   R2     via R1, e0, custo 2    direta, e2             via R3, e1, custo 1
#   R3     via R4, e0, custo 2    via R2, e1, custo 1    direta, e2
#   R4     via R1, e0, custo 1    via R3, e1, custo 2    via R3, e1, custo 1
TABELA_3 = {
    "R1": {
        "10.0.1.0/24": ("direta", "e0", 0),
        "10.0.2.0/24": ("R2", "e2", 2),
        "10.0.3.0/24": ("R4", "e1", 2),
    },
    "R2": {
        "10.0.1.0/24": ("R1", "e0", 2),
        "10.0.2.0/24": ("direta", "e2", 0),
        "10.0.3.0/24": ("R3", "e1", 1),
    },
    "R3": {
        "10.0.1.0/24": ("R4", "e0", 2),
        "10.0.2.0/24": ("R2", "e1", 1),
        "10.0.3.0/24": ("direta", "e2", 0),
    },
    "R4": {
        "10.0.1.0/24": ("R1", "e0", 1),
        "10.0.2.0/24": ("R3", "e1", 2),
        "10.0.3.0/24": ("R3", "e1", 1),
    },
}


def conferir_tabela_3(topologia, conferir):
    """Confere as doze entradas da Tabela 3, uma a uma."""
    print("Tabela 3: tabelas de encaminhamento de referencia")
    print("-" * 72)
    print(f"  {'':<4}{'rede':<16}{'proximo salto':<16}{'interface':<12}{'custo':>6}")
    for roteador, esperado_da_rede in TABELA_3.items():
        obtidas = {
            rota.prefixo: (("direta" if rota.direta else rota.proximo_salto),
                           rota.interface_de_saida, rota.custo)
            for rota in topologia.tabela_de_encaminhamento(roteador)
        }
        for prefixo, esperado in esperado_da_rede.items():
            obtido = obtidas.get(prefixo)
            salto, interface, custo = obtido if obtido else ("-", "-", "-")
            print(f"  {roteador:<4}{prefixo:<16}{salto:<16}{interface:<12}{custo:>6}")
            conferir(f"Tabela 3: {roteador} -> {prefixo} "
                     f"({esperado[0]}, {esperado[1]}, custo {esperado[2]})",
                     obtido, esperado)
        # Nenhuma rede a mais nem a menos: a tabela do roteador tem tres linhas.
        conferir(f"Tabela 3: {roteador} tem exatamente as tres redes",
                 sorted(obtidas), sorted(esperado_da_rede))
    print()


def executar():
    topologia = Topologia.carregar()
    falhas = []

    def conferir(descricao, obtido, esperado):
        ok = obtido == esperado
        print(f"{'ok    ' if ok else 'FALHOU'} {descricao}")
        if not ok:
            print(f"       obtido:   {obtido}")
            print(f"       esperado: {esperado}")
            falhas.append(descricao)

    conferir_tabela_3(topologia, conferir)

    # A linha 011 do log da especificacao: 10.0.3.0/24 via R4, custo 2, interface e1.
    rota = topologia.rota_para("R1", "10.0.3.10")
    conferir("R1 alcanca a Rede C via R4, custo 2, interface e1",
             (rota.proximo_salto, rota.custo, rota.interface_de_saida),
             ("R4", 2, "e1"))

    # E1: H1 e H2 estao na mesma rede, e a entrega dispensa roteador.
    conferir("E1 entrega direta de H1 para H2",
             topologia.caminho_de_dispositivos("H1", "10.0.1.11"),
             ["H1", "H2"])

    # E2: caso central, quatro enlaces e tres roteadores.
    conferir("E2 caminho de H1 ate H4 pelo menor custo",
             topologia.caminho_de_dispositivos("H1", "10.0.3.10"),
             ["H1", "R1", "R4", "R3", "H4"])

    caminho = topologia.caminho_de_dispositivos("H1", "10.0.3.10")
    conferir("E2 percorre quatro enlaces", len(caminho) - 1, 4)

    # E5: endereco fora de qualquer prefixo da topologia.
    conferir("E5 destino 10.0.9.10 nao tem prefixo conhecido",
             topologia.prefixo_de("10.0.9.10"), None)
    conferir("E5 R1 nao encontra rota e o pacote e descartado",
             topologia.rota_para("R1", "10.0.9.10"), None)

    # E4: com o enlace R1-R4 fora de servico, o desvio passa por R2, custo 3.
    topologia.derrubar("R1", "R4")
    rota = topologia.rota_para("R1", "10.0.3.10")
    conferir("E4 desvio por R2 com custo 3",
             (rota.proximo_salto, rota.custo), ("R2", 3))
    conferir("E4 caminho passa a ser H1 R1 R2 R3 H4",
             topologia.caminho_de_dispositivos("H1", "10.0.3.10"),
             ["H1", "R1", "R2", "R3", "H4"])
    conferir("E4 continua com quatro enlaces",
             len(topologia.caminho_de_dispositivos("H1", "10.0.3.10")) - 1, 4)

    topologia.restaurar_enlaces()
    conferir("apos restaurar, a rota volta a passar por R4",
             topologia.rota_para("R1", "10.0.3.10").proximo_salto, "R4")

    print()
    print("todos os casos conferem" if not falhas else f"{len(falhas)} caso(s) divergente(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
