# -*- coding: utf-8 -*-
"""Exporta o resultado de uma simulacao em HTML.

Arquivo unico, sem dependencia externa. Le apenas o ResultadoSimulacao.
"""

from __future__ import annotations

import html
from datetime import datetime

from . import config
from .cenarios import Cenario, comparativo_eficiencia
from .motor import ResultadoSimulacao
from .rede import Topologia

_ESTILO = """
:root {
  --fundo: #f6f7f9; --papel: #ffffff; --tinta: #1b1f24; --suave: #5b6672;
  --borda: #d8dee6; --destaque: #1f5fa8; --erro: #b3261e; --ok: #1d7a46;
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px; background: var(--fundo); color: var(--tinta);
       font-family: "Segoe UI", system-ui, sans-serif; line-height: 1.5; }
main { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 32px 0 10px; padding-bottom: 6px;
     border-bottom: 2px solid var(--borda); }
.sub { color: var(--suave); margin: 0 0 24px; font-size: .92rem; }
section { background: var(--papel); border: 1px solid var(--borda);
          border-radius: 10px; padding: 16px 18px; margin-bottom: 18px; }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--borda); }
th { background: #eef2f7; font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
code, .mono { font-family: Consolas, "Courier New", monospace; }
pre { background: #10141a; color: #e6edf3; padding: 14px; border-radius: 8px;
      overflow-x: auto; font-size: .8rem; line-height: 1.45; }
.cartoes { display: flex; flex-wrap: wrap; gap: 12px; }
.cartao { flex: 1 1 160px; background: #eef2f7; border-radius: 8px; padding: 10px 12px; }
.cartao b { display: block; font-size: 1.35rem; }
.cartao span { color: var(--suave); font-size: .8rem; }
.pdu { display: flex; flex-wrap: wrap; gap: 3px; margin: 8px 0 14px; }
.bloco { border: 1px solid var(--borda); border-radius: 5px; padding: 6px 10px;
         font-size: .78rem; text-align: center; min-width: 54px; }
.bloco b { display: block; font-size: .85rem; }
.cab { background: #dce7f5; } .dad { background: #dff3e4; } .fim { background: #f7e3c8; }
.caminho { font-size: 1.05rem; letter-spacing: .04em; }
.erro { color: var(--erro); font-weight: 600; }
.ok { color: var(--ok); font-weight: 600; }
@media (prefers-color-scheme: dark) {
  :root { --fundo: #0f1216; --papel: #171b21; --tinta: #e6edf3; --suave: #9aa7b4;
          --borda: #2b323b; }
  th { background: #1f252d; } .cartao { background: #1f252d; }
  .cab { background: #24405f; } .dad { background: #1f4a30; } .fim { background: #56411d; }
}
"""


def _e(texto: object) -> str:
    return html.escape(str(texto))


def _cartao(valor: str, rotulo: str) -> str:
    return f'<div class="cartao"><b>{_e(valor)}</b><span>{_e(rotulo)}</span></div>'


def _tabela(cabecalho: list[str], linhas: list[list[str]],
            numericas: set[int] | None = None) -> str:
    numericas = numericas or set()
    partes = ["<table><thead><tr>"]
    partes += [f"<th>{_e(c)}</th>" for c in cabecalho]
    partes.append("</tr></thead><tbody>")
    for linha in linhas:
        partes.append("<tr>")
        for indice, celula in enumerate(linha):
            classe = ' class="num"' if indice in numericas else ""
            partes.append(f"<td{classe}>{_e(celula)}</td>")
        partes.append("</tr>")
    partes.append("</tbody></table>")
    return "".join(partes)


def _desenho_pdu(resultado: ResultadoSimulacao) -> str:
    """Desenha a unidade de dados no maior estagio que ela alcancou."""
    maior = None
    for evento in resultado.registro:
        if evento.unidade is not None and evento.acao == "ENQUADRA":
            if maior is None or evento.tamanho > maior.tamanho:
                maior = evento
    if maior is None or maior.unidade is None:
        return "<p>Nenhum quadro foi construido nesta execucao.</p>"

    blocos = []
    for bloco in maior.unidade.blocos():
        classe = {"cabecalho": "cab", "dados": "dad", "finalizador": "fim"}[bloco["tipo"]]
        blocos.append(
            f'<div class="bloco {classe}" title="{_e(bloco["detalhe"])}">'
            f'<b>{_e(bloco["rotulo"])}</b>{bloco["tamanho"]} B</div>'
        )
    return (f'<p class="mono">{_e(maior.unidade.unidade)} '
            f'{_e(maior.unidade.quadro or "")} '
            f'&mdash; {maior.tamanho} octetos</p>'
            f'<div class="pdu">{"".join(blocos)}</div>')


def gerar_html(resultado: ResultadoSimulacao, cenario: Cenario | None,
               topologia: Topologia) -> str:
    """Monta o relatorio completo como uma unica pagina HTML."""
    comparativo = comparativo_eficiencia(topologia)
    titulo = cenario.rotulo if cenario else "Simulacao personalizada"
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    partes: list[str] = [
        "<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_e(config.NOME_PROGRAMA)} - {_e(titulo)}</title>",
        f"<style>{_ESTILO}</style></head><body><main>",
        f"<h1>{_e(config.NOME_PROGRAMA)}</h1>",
        f'<p class="sub">{_e(config.DISCIPLINA)} &middot; {_e(config.AUTORIA)}'
        f" &middot; rede {_e(topologia.nome)} &middot; gerado em {_e(agora)}<br>"
        f"{_e(', '.join(config.INTEGRANTES))}</p>",
    ]

    # cenario
    partes.append("<section><h2 style='margin-top:0'>Cenario</h2>")
    partes.append(f"<p><b>{_e(titulo)}</b><br>{_e(cenario.descricao if cenario else '')}</p>")
    if resultado.observacao:
        partes.append(f"<p>{_e(resultado.observacao)}</p>")
    if resultado.enlaces_derrubados:
        partes.append("<p>Enlaces derrubados: "
                      f"<code>{_e(', '.join(resultado.enlaces_derrubados))}</code></p>")
    if resultado.enlace_com_erro:
        partes.append("<p>Erro de bit injetado no enlace "
                      f"<code>{_e(resultado.enlace_com_erro)}</code></p>")
    partes.append("</section>")

    # quadro numerico
    estado = ('<span class="ok">mensagem entregue</span>' if resultado.entregue
              else '<span class="erro">mensagem nao entregue</span>')
    partes.append("<section><h2 style='margin-top:0'>Custo do empilhamento</h2>")
    partes.append('<div class="cartoes">')
    partes.append(_cartao(f"{resultado.octetos_dados} B", "octetos de dados"))
    partes.append(_cartao(f"{resultado.octetos_transmitidos} B", "octetos transmitidos"))
    partes.append(_cartao(str(resultado.total_quadros), "quadros construidos"))
    partes.append(_cartao(f"{resultado.eficiencia:.1%}", "eficiencia"))
    partes.append(_cartao(f"{resultado.sobrecarga:.1%}", "sobrecarga"))
    partes.append("</div>")
    partes.append(f"<p>{estado}. Comparacao de referencia: "
                  f"E1 com um enlace, {comparativo['E1_eficiencia']:.1%}; "
                  f"E2 com quatro enlaces, {comparativo['E2_eficiencia']:.1%}.</p>")
    partes.append("</section>")

    # percurso
    partes.append("<section><h2 style='margin-top:0'>Percurso e quadros</h2>")
    for fluxo in resultado.fluxos:
        partes.append(f"<p class='caminho mono'>Fluxo {_e(fluxo.rotulo)}: "
                      f"{_e(' → '.join(fluxo.caminho))}</p>")
        if fluxo.segmentos and len(fluxo.segmentos) > 1:
            partes.append("<p>Segmentos da camada 4: "
                          f"{_e(', '.join(f'{s} B' for s in fluxo.segmentos))}</p>")
        if fluxo.motivo:
            partes.append(f'<p class="erro">{_e(fluxo.motivo)}</p>')
        linhas = [
            [q["rotulo"], q["enlace"], f"{q['de']} → {q['para']}",
             (q["fisicos"] or ("", ""))[0], (q["fisicos"] or ("", ""))[1],
             (q["logicos"] or ("", ""))[0], (q["logicos"] or ("", ""))[1],
             str(q["octetos"])]
            for q in fluxo.quadros
        ]
        partes.append(_tabela(
            ["Quadro", "Enlace", "Salto", "Fisico origem", "Fisico destino",
             "Logico origem", "Logico destino", "Octetos"],
            linhas, numericas={7},
        ))
    partes.append("<p>O par de enderecos logicos e o mesmo em todas as linhas; "
                  "o par de enderecos fisicos muda a cada salto.</p>")
    partes.append("</section>")

    # unidade de dados
    partes.append("<section><h2 style='margin-top:0'>Unidade de dados</h2>")
    partes.append(_desenho_pdu(resultado))
    partes.append("</section>")

    # tabelas de encaminhamento
    partes.append("<section><h2 style='margin-top:0'>Tabelas de encaminhamento</h2>")
    for nome in sorted(resultado.tabelas):
        if topologia.dispositivos[nome].tipo != "roteador":
            continue
        partes.append(f"<h3 class='mono'>{_e(nome)}</h3>")
        partes.append(_tabela(
            ["Rede de destino", "Proximo salto", "Interface", "Custo", "Via"],
            [list(entrada.como_linha()) for entrada in resultado.tabelas[nome]],
            numericas={3},
        ))
    partes.append("</section>")

    # registro
    partes.append("<section><h2 style='margin-top:0'>Registro de eventos</h2>")
    partes.append(f"<pre>{_e(resultado.registro.texto())}</pre>")
    partes.append("</section>")

    # convencoes
    partes.append("<section><h2 style='margin-top:0'>Convencoes de simulacao</h2>")
    partes.append(_tabela(["Parametro", "Valor"],
                          [list(par) for par in config.resumo_convencoes()]))
    partes.append("</section>")

    partes.append("</main></body></html>")
    return "".join(partes)


def salvar(caminho: str, resultado: ResultadoSimulacao,
           cenario: Cenario | None, topologia: Topologia) -> None:
    """Grava o relatorio HTML no caminho indicado."""
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(gerar_html(resultado, cenario, topologia))
