# -*- coding: utf-8 -*-
"""Convencoes de simulacao.

Reune os numeros que determinam o resultado de uma execucao. Mudar um valor
aqui muda os tamanhos na tela e a eficiencia calculada.

A pasta de trabalho e descoberta em `diretorio_base()`, sem caminho absoluto.
"""

from __future__ import annotations

import os
import sys

# Identificacao
NOME_PROGRAMA = "Simulador do Modelo OSI"
VERSAO = "1.0"
AUTORIA = "Grupo 8"
INTEGRANTES = (
    "Arthur Benevides 082230016",
    "Fernando Montanher 082230010",
    "Guilherme Costa 081240041",
    "Juan Haddad 081240043",
    "Murillo Ando 082240042",
)
DISCIPLINA = "Comunicacao de Dados - Prof. Vinicius S. Borges"

# Tamanhos de cabecalho, em octetos
# Fixados pelo enunciado (secao "Custo do empilhamento"). Sao os mesmos para
# todos os projetos da turma, de modo que os numeros sejam comparaveis.
TAMANHO_CABECALHO_SESSAO = 4       # camada 5
TAMANHO_CABECALHO_TRANSPORTE = 8   # camada 4
TAMANHO_CABECALHO_REDE = 20        # camada 3
TAMANHO_CABECALHO_ENLACE = 14      # camada 2, cabecalho
TAMANHO_FINALIZADOR_ENLACE = 4     # camada 2, finalizador (verificacao de erro)

# As camadas 7 e 6 nao acrescentam octetos: a camada 7 gera o texto e a
# camada 6 converte esse texto em octetos e o cifra, e a cifra adotada
# preserva o comprimento.
TAMANHO_CABECALHO_APLICACAO = 0
TAMANHO_CABECALHO_APRESENTACAO = 0

# Camada 4: segmentacao
# A camada 4 recebe da camada 5 um bloco formado pelo cabecalho de sessao
# seguido do conteudo cifrado. Se esse bloco nao passa do limiar, viaja em um
# unico segmento; se passa, e fatiado em pedacos de, no maximo,
# CARGA_MAXIMA_SEGMENTO octetos cada.
#
# Os dois parametros sao distintos de proposito:
#   - LIMIAR_SEGMENTACAO = 64 mantem o cenario E2 (4 + 42 = 46 octetos) inteiro;
#   - CARGA_MAXIMA_SEGMENTO = 40 faz o cenario E7 (4 + 100 = 104 octetos)
#     render exatamente tres segmentos de 40, 40 e 24 octetos.
LIMIAR_SEGMENTACAO = 64
CARGA_MAXIMA_SEGMENTO = 40

# Camada 6: codificacao e cifra
CODIFICACAO = "utf-8"
# Cifra de fluxo por ou-exclusivo com chave repetida. E reversivel, preserva o
# comprimento em octetos e so e desfeita na camada 6 do destino.
CHAVE_CIFRA = b"OSI"

# Camada 5: sessao
PREFIXO_SESSAO = "S-"        # identificador impresso como S-0001, S-0002, ...

# Camada 3: rede
TTL_INICIAL = 64             # campo informativo; nao e decrementado
PROTOCOLO_TRANSPORTE = 6     # numero de protocolo gravado no cabecalho
VERSAO_IHL = 0x45            # versao 4, cabecalho de 5 palavras de 32 bits
PREFIXO_PACOTE = "P"         # pacotes sao numerados P1, P2, P3, ...

# Camada 2: enlace
TIPO_PROTOCOLO_ENLACE = 0x0800   # indica que a carga e um pacote da camada 3
PREFIXO_QUADRO = "Q"             # quadros sao numerados Q1, Q2, Q3, ...

# Camada 1: fisica
BITS_POR_OCTETO = 8

# Interface
# (rotulo, intervalo entre passos em milissegundos). O requisito V5 pede pelo
# menos tres velocidades; sao oferecidas quatro.
VELOCIDADES = (
    ("Muito lenta", 1400),
    ("Lenta", 800),
    ("Normal", 350),
    ("Rapida", 120),
)
VELOCIDADE_PADRAO = 2   # indice de "Normal"

ARQUIVO_TOPOLOGIA_PADRAO = "topologia.json"
ARQUIVO_REGISTRO_PADRAO = "registro_eventos.txt"
ARQUIVO_RELATORIO_PADRAO = "relatorio_simulacao.html"

# Descoberta de diretorio


def diretorio_base() -> str:
    """Devolve a pasta em que o programa procura `topologia.json`.

    Quando o programa roda como executavel gerado pelo PyInstaller, a pasta e
    a do proprio executavel, de modo que substituir o arquivo de topologia ao
    lado dele troca a rede simulada. Quando roda a partir do codigo-fonte, a
    pasta e a raiz do projeto, um nivel acima deste modulo.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def caminho_no_projeto(*partes: str) -> str:
    """Monta um caminho relativo a `diretorio_base()`."""
    return os.path.join(diretorio_base(), *partes)


def resumo_convencoes() -> list[tuple[str, str]]:
    """Lista legivel das convencoes, exibida pela interface e pelo modo texto."""
    return [
        ("Cabecalho da camada 5 (sessao)", f"{TAMANHO_CABECALHO_SESSAO} octetos"),
        ("Cabecalho da camada 4 (transporte)", f"{TAMANHO_CABECALHO_TRANSPORTE} octetos"),
        ("Cabecalho da camada 3 (rede)", f"{TAMANHO_CABECALHO_REDE} octetos"),
        ("Cabecalho da camada 2 (enlace)", f"{TAMANHO_CABECALHO_ENLACE} octetos"),
        ("Finalizador da camada 2", f"{TAMANHO_FINALIZADOR_ENLACE} octetos"),
        ("Limiar de segmentacao", f"{LIMIAR_SEGMENTACAO} octetos"),
        ("Carga maxima por segmento", f"{CARGA_MAXIMA_SEGMENTO} octetos"),
        ("Cabecalho de sessao", "entra uma unica vez, no primeiro segmento"),
        ("Desempate entre rotas de mesmo custo", "menor nome de proximo salto"),
        ("Campo TTL", "informativo; nao e decrementado"),
        ("Octetos transmitidos", "somados a cada quadro que entra em um enlace"),
        ("Octetos de dados", "contados apenas quando a mensagem e entregue"),
    ]
