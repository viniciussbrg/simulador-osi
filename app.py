"""O programa: a janela do simulador do modelo OSI.

    python app.py                    abre a janela no primeiro caso
    python app.py --caso C4          abre já no caso escolhido

É o **único** módulo que importa os dois lados. `simulador.py` produz a lista
de eventos e não conhece a tela; `visual.py` desenha a tela e não conhece o
motor (seção 4.2 da proposta técnica). A tradução entre um e outro mora aqui,
e é pequena de propósito: executar um caso, traduzir `Intervencao` em
`EventoExterno`, montar o cabeçalho do registro.

O modo textual continua em `simulador.py --caso C2 --log saida.txt`, sem nunca
enxergar a interface — é por isso que é **este** arquivo que o PyInstaller
empacota, e não aquele:

    pyinstaller --onefile --windowed --name SimuladorOSI app.py

A montagem segue a ordem da arquitetura: carregar a topologia, executar o caso
**inteiro** (issue #32), e só então abrir a janela. Nada é gerado sob demanda
enquanto se navega.

`tkinter` é importado **dentro** de `principal()`, não no topo — a mesma
disciplina de `visual.py`. É o que permite importar este módulo (e testar a
tradução de intervenções e a validação de argumentos) numa máquina sem
tkinter, e o que faz um erro de topologia sair como mensagem legível em vez de
`ModuleNotFoundError`.
"""

import argparse
import sys

from evento import Intervencao
from rede import ErroTopologia, EventoExterno, carregar_topologia, pasta_base
from simulador import (
    CasoNaoSuportado,
    cabecalho,
    casos_executaveis,
    com_intervencao,
    executar,
)
from visual import Janela, Navegador, carregar_planta

ARQUIVO = "topologia.json"
SAIDA_OK = 0
SAIDA_ERRO = 1


def _externo(intervencao: Intervencao) -> EventoExterno:
    """Traduz o pedido da tela no vocabulário do motor.

    As duas estruturas têm os mesmos campos de propósito: a tradução é uma
    linha, e é o preço — baixo — de `visual.py` não importar `rede.py`."""
    return EventoExterno(
        tipo=intervencao.tipo,
        enlace=intervencao.enlace,
        quadro=intervencao.quadro,
        bit=intervencao.bit,
    )


def montar_executor(topologia):
    """A função que a janela chama para (re)executar um caso.

    Devolve os eventos **e** o cabeçalho juntos, porque o cabeçalho nomeia o
    caso e muda a cada reexecução — inclusive o id derivado, quando há
    intervenção (`C2` vira `C2*`). Deixar a janela montar o cabeçalho exigiria
    que ela conhecesse `simulador.cabecalho`, que é exatamente o que a regra
    de acoplamento proíbe."""

    def executar_para_a_tela(caso: str, intervencoes=()):
        alvo = topologia.caso(caso)
        for intervencao in intervencoes:
            alvo = com_intervencao(alvo, _externo(intervencao))
        return executar(topologia, alvo), cabecalho(topologia, alvo)

    return executar_para_a_tela


def avisar_na_tela(mensagem: str) -> None:
    """Mostra o erro ao usuário, com ou sem console.

    O executável é construído com `--windowed` (seção 14.1), e isso apaga a
    saída de erro: no `.exe`, uma topologia ausente faria o programa
    simplesmente não abrir, em silêncio. O item 5 do checklist da seção 14.3
    pede o contrário — mensagem clara, nunca rastreamento de pilha —, e uma
    caixa de diálogo é o único canal que sobra quando não há terminal.

    O `stderr` continua recebendo a mensagem, para quem roda pelo terminal e
    para quem redireciona a saída. Se o tkinter não estiver disponível, resta
    o `stderr`, que é melhor que estourar dentro do tratamento de erro."""
    print(mensagem, file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror("Simulador do Modelo OSI", mensagem)
        raiz.destroy()
    except Exception:  # pragma: no cover — depende do ambiente gráfico
        pass


def _analisar(argv):
    analisador = argparse.ArgumentParser(
        prog="app.py",
        description="Abre a janela do simulador do modelo OSI.",
    )
    analisador.add_argument(
        "--caso", default=None, help="caso inicial (padrão: o primeiro da topologia)"
    )
    analisador.add_argument(
        "--topologia",
        default=None,
        metavar="ARQUIVO",
        help=(
            "usa outra topologia; sem ele, o topologia.json ao lado do "
            "executável (pasta_base(), seção 5.8)"
        ),
    )
    return analisador.parse_args(argv)


def principal(argv=None, avisar=None) -> int:
    """Erro de topologia e caso inexistente saem como **mensagem**, nunca como
    rastreamento de pilha (seção 5.7): numa máquina Windows sem Python, o
    traceback é ilegível para quem editou o arquivo.

    `avisar` é por onde a mensagem chega ao usuário. O padrão mostra uma caixa
    de diálogo **e** escreve no `stderr`, porque o executável não tem console
    (seção 14.1) e o terminal tem. O teste passa um coletor e verifica o texto
    sem abrir janela nenhuma."""
    argumentos = _analisar(argv)
    avisar = avisar if avisar is not None else avisar_na_tela

    caminho = argumentos.topologia or (pasta_base() / ARQUIVO)
    try:
        topologia = carregar_topologia(caminho)
    except ErroTopologia as erro:
        avisar(f"topologia inválida: {erro}")
        return SAIDA_ERRO

    disponiveis = casos_executaveis(topologia)
    if not disponiveis:
        avisar("nenhum caso executável nesta topologia")
        return SAIDA_ERRO

    inicial = argumentos.caso or disponiveis[0]
    if inicial not in disponiveis:
        avisar(
            f"caso {inicial} não está nesta topologia "
            f"(há {', '.join(disponiveis)})"
        )
        return SAIDA_ERRO

    executar_para_a_tela = montar_executor(topologia)
    try:
        eventos, texto_cabecalho = executar_para_a_tela(inicial)
    except CasoNaoSuportado as erro:
        avisar(str(erro))
        return SAIDA_ERRO

    # tkinter entra só aqui, como em `visual.py`: assim `import app` funciona
    # numa máquina sem tkinter, e um erro de topologia ou de caso sai como
    # mensagem legível mesmo onde a janela jamais abriria.
    import tkinter as tk

    raiz = tk.Tk()
    janela = Janela(
        planta=carregar_planta(caminho),
        navegador=Navegador(eventos),
        caso=inicial,
        executar=executar_para_a_tela,
        cabecalho=texto_cabecalho,
        casos=disponiveis,
        enlaces=tuple(enlace.id for enlace in topologia.enlaces),
        velocidades={
            "lenta": topologia.parametros.velocidades_ms.lenta,
            "media": topologia.parametros.velocidades_ms.media,
            "rapida": topologia.parametros.velocidades_ms.rapida,
        },
    )
    janela.montar(raiz)
    janela.redesenhar()
    raiz.mainloop()
    return SAIDA_OK


if __name__ == "__main__":
    raise SystemExit(principal())
