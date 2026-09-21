"""Confere as sete camadas sobre a topologia real de topologia.json.

As pilhas e o meio fisico sao os do simulador (dispositivos.py e
simulador.py); este teste apenas monta cenarios e le o registro. Alem dos
tamanhos pedidos (42 -> 92 e a segmentacao 40/40/24), confere a remontagem
no destino, o caso central E2 com a linha 011 do log da especificacao, os
casos E5 e E6, o tamanho em octetos de texto acentuado e o formato do
registro.

Executar com:  python testes/teste_camadas.py
"""

import os
import sys
import tempfile
from dataclasses import replace

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from simulador.rede import Topologia  # noqa: E402
from simulador.simulador import CENARIOS, FLUXO_CENTRAL, Cenario, Simulacao  # noqa: E402

TOPOLOGIA = Topologia.carregar()
MENSAGEM_100 = ("Mensagem longa que precisa ser segmentada. " * 3)[:100]


def rodar(cenario, classe=Simulacao):
    sim = classe(TOPOLOGIA, cenario)
    sim.executar()
    return sim


def envio(destino, mensagem):
    """Cenario de um unico fluxo do caso central, com outro destino e outra mensagem."""
    fluxo = replace(FLUXO_CENTRAL, destino=destino, mensagem=mensagem)
    return Cenario("teste", f"H1 -> {destino}", (fluxo,))


def eventos(sim, **filtro):
    return [e for e in sim.eventos
            if all(getattr(e, k) == v for k, v in filtro.items())]


def imprimir(linhas):
    for linha in linhas:
        print(f"   {linha}")


class SimulacaoComErroNoCabecalho(Simulacao):
    """Erro de bit que cai no cabecalho da camada 3, e nao nos dados."""

    def corromper(self, quadro):
        cabecalho = quadro.cabecalho_da_camada(3)
        destino = cabecalho.campos["destino"]
        alterado = destino[:-1] + chr(ord(destino[-1]) ^ 0x01)
        novo = replace(cabecalho, campos={**cabecalho.campos, "destino": alterado})
        return replace(quadro, cabecalhos=tuple(
            novo if c is cabecalho else c for c in quadro.cabecalhos
        ))


# ----------------------------------------------------------------------
# Casos
# ----------------------------------------------------------------------

def caso_tamanhos_42():
    sim = rodar(CENARIOS["E1"])
    descida = eventos(sim, dispositivo="H1")
    imprimir(sim.registro.linhas()[:len(descida)])

    # Tamanho com que a unidade sai de cada camada, da 7 a 1.
    por_numero = {e.camada: e.tamanho for e in descida}
    por_camada = [por_numero[n] for n in range(7, 0, -1)]
    esperado = [42, 42, 46, 54, 74, 92]
    print(f"   L7..L2: {por_camada[:6]}  (esperado {esperado});  L1: {por_camada[6]} B")
    linha_004 = sim.registro.linhas()[3]
    print(f"   linha 004 e SEGMENTA: {linha_004.startswith('004 | H1 | L4 | SEGMENTA | ')}")
    return (por_camada[:6] == esperado and por_camada[6] == 92
            and linha_004.startswith("004 | H1 | L4 | SEGMENTA | ")
            and linha_004.endswith(" 54 B"))


def caso_segmentacao_100():
    sim = rodar(envio("H2", MENSAGEM_100))
    segmenta = eventos(sim, dispositivo="H1", camada=4)
    imprimir(sim.registro.linhas()[:7])

    cabecalho_l4 = sim.topologia.convencoes["cabecalhos"]["4"]
    cargas = [e.tamanho - cabecalho_l4 for e in segmenta]
    print(f"   carga dos segmentos: {cargas}  (esperado [40, 40, 24]);"
          f"  com cabecalho L4: {[e.tamanho for e in segmenta]}")
    return cargas == [40, 40, 24] and [e.acao for e in segmenta] == ["SEGMENTA"] * 3


def caso_remontagem_100():
    sim = rodar(envio("H2", MENSAGEM_100))
    imprimir(sim.registro.linhas()[-6:])

    l4_h2 = [e.acao for e in eventos(sim, dispositivo="H2", camada=4)]
    ok = (l4_h2 == ["RECEBE", "RECEBE", "REMONTA"]
          and len(sim.entregas) == 1 and sim.entregas[0].mensagem == MENSAGEM_100
          and sim.entregas[0].processo == "servidorWeb")
    processo = sim.entregas[0].processo if sim.entregas else None
    print(f"   L4 em H2: {l4_h2};  entregue a '{processo}': {ok}")
    return ok


def caso_central_e2():
    cenario = CENARIOS["E2"]
    mensagem = cenario.fluxos[0].mensagem
    sim = rodar(cenario)
    imprimir(sim.registro.linhas())

    quadros = sim.quadros
    for q in quadros:
        print(f"   {q.numero_quadro}: {q.fisicos[0]} -> {q.fisicos[1]}   "
              f"logicos {q.logicos[0]} -> {q.logicos[1]}   portas {q.portas}   {q.tamanho} B")

    linha_011 = sim.registro.linhas()[10]
    esperado_011 = "011 | R1 | L3 | ROTEIA | 10.0.3.0/24 via R4, custo 2, interface e1"
    r2 = (len({id(q) for q in quadros}) == 4
          and len({q.numero_quadro for q in quadros}) == 4
          and len({q.fisicos for q in quadros}) == 4)
    r3 = len({q.logicos for q in quadros}) == 1
    portas = all(q.portas == (5210, 443) for q in quadros)
    entrega = (len(sim.entregas) == 1 and sim.entregas[0].mensagem == mensagem
               and sim.entregas[0].dispositivo == "H4"
               and sim.entregas[0].processo == "servidorWeb")
    total = sum(q.tamanho for q in quadros)
    print(f"   mensagem: {mensagem!r} ({len(mensagem.encode('utf-8'))} octetos)")
    print(f"   linha 011 confere: {linha_011.startswith(esperado_011)};  R2: {r2};  R3: {r3};"
          f"  portas 5210->443: {portas};  entregue: {entrega};  {total} octetos (esperado 368)")
    return (linha_011.startswith(esperado_011) and r2 and r3 and portas and entrega
            and total == 368 and len(mensagem.encode("utf-8")) == 42 and "H4" in mensagem)


def caso_inalcancavel_e5():
    sim = rodar(CENARIOS["E5"])
    imprimir(sim.registro.linhas()[-4:])
    ultimo = sim.eventos[-1]
    total = sum(q.tamanho for q in sim.quadros)
    print(f"   quadros: {len(sim.quadros)};  {total} octetos (esperado 92)")
    return (sim.entregas == [] and len(sim.quadros) == 1 and total == 92
            and (ultimo.dispositivo, ultimo.camada, ultimo.acao) == ("R1", 3, "DESCARTA"))


def caso_erro_de_bit_e6():
    sim = rodar(CENARIOS["E6"], SimulacaoComErroNoCabecalho)
    imprimir(sim.registro.linhas()[-3:])
    ultimo = sim.eventos[-1]
    total = sum(q.tamanho for q in sim.quadros)
    print(f"   bit invertido no cabecalho L3 do enlace R4-R3;  quadros: {len(sim.quadros)};"
          f"  {total} octetos (esperado 276)")
    return (sim.entregas == [] and len(sim.quadros) == 3 and total == 276
            and (ultimo.dispositivo, ultimo.camada, ultimo.acao) == ("R3", 2, "DESCARTA"))


def caso_texto_acentuado():
    texto = "Olá, H2! Comunicação de Dados"
    octetos = len(texto.encode("utf-8"))
    sim = rodar(envio("H2", texto))
    gera = eventos(sim, acao="GERA")[0].tamanho
    codifica = eventos(sim, acao="CODIFICA")[0].tamanho
    entrega = eventos(sim, camada=7, acao="ENTREGA")[0].tamanho
    print(f"   {len(texto)} caracteres, {octetos} octetos;  "
          f"L7 GERA {gera} B, L6 CODIFICA {codifica} B, L7 ENTREGA {entrega} B")
    return gera == codifica == entrega == octetos


def caso_blocos_com_texto_acentuado():
    """O bloco Dados de em_blocos() mede octetos, como o evento, e nao caracteres."""
    texto = "Olá, H2! Comunicação de Dados"
    octetos = len(texto.encode("utf-8"))
    sim = Simulacao(TOPOLOGIA, envio("H2", texto))
    divergentes, conferidos = [], 0
    while (evento := sim.passo()) is not None:
        blocos = sim.unidade.em_blocos()
        dados = next(b["octetos"] for b in blocos if b["rotulo"] == "Dados")
        # Nas camadas 7 e 6 nao ha cabecalho: o bloco Dados e a unidade inteira.
        sem_cabecalho = len(blocos) == 1
        if sem_cabecalho:
            conferidos += 1
        if (sem_cabecalho and dados != evento.tamanho) or dados != octetos:
            divergentes.append(f"{evento.passo:03d} {evento.dispositivo} L{evento.camada} "
                               f"{evento.acao}: bloco {dados} B, evento {evento.tamanho} B")
    imprimir(divergentes)
    print(f"   {len(texto)} caracteres, {octetos} octetos;  {conferidos} passos sem "
          f"cabecalho conferidos contra o evento;  divergentes: {len(divergentes)}")
    return conferidos >= 4 and not divergentes


def caso_registro_em_arquivo():
    sim = rodar(CENARIOS["E1"])
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, "registro.txt")
        sim.registro.salvar_em_arquivo(caminho)
        with open(caminho, encoding="utf-8") as arquivo:
            gravadas = arquivo.read().splitlines()
    formato = all(
        len(partes := linha.split(" | ", 4)) == 5
        and len(partes[0]) == 3 and partes[0].isdigit()
        and partes[2].startswith("L") and linha.endswith(" B")
        for linha in gravadas
    )
    print(f"   {len(gravadas)} linhas gravadas;  iguais ao registro: "
          f"{gravadas == sim.registro.linhas()};  formato NNN | DISP | LN | ACAO | ... TAM B: {formato}")
    return gravadas == sim.registro.linhas() and formato and gravadas[0].startswith("001 | H1 | L7 | GERA | ")


CASOS = [
    ("descida de 42 octetos (E1)", caso_tamanhos_42),
    ("segmentacao de 100 octetos", caso_segmentacao_100),
    ("remontagem no destino", caso_remontagem_100),
    ("caso central E2: H1 -> R1 -> R4 -> R3 -> H4", caso_central_e2),
    ("E5 destino inalcancavel", caso_inalcancavel_e5),
    ("E6 erro de bit em cabecalho", caso_erro_de_bit_e6),
    ("L7 reporta octetos, nao caracteres", caso_texto_acentuado),
    ("bloco Dados em octetos com texto acentuado", caso_blocos_com_texto_acentuado),
    ("registro salvo em arquivo", caso_registro_em_arquivo),
]


def executar():
    falhas = 0
    for nome, caso in CASOS:
        print(f"\n{nome}")
        passou = caso()
        falhas += 0 if passou else 1
        print(f"   -> {'ok' if passou else 'FALHOU'}")
    print("\n" + ("todos os casos conferem" if falhas == 0 else f"{falhas} caso(s) divergente(s)"))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
