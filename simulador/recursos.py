"""Localizacao de arquivos ao lado do programa, com copia embutida de reserva.

Este modulo existe por causa do R10 da especificacao. A rede simulada e lida
de um arquivo externo que deve poder ser trocado ao lado do executavel, sem
gerar outro executavel e sem caminho absoluto no codigo.

Quando o programa e empacotado em arquivo unico, o carregador extrai os
modulos e os dados embutidos numa pasta temporaria e apaga essa pasta ao
sair. Nesse estado ha dois caminhos possiveis, e eles nao sao intercambiaveis:

    pasta_do_programa()   onde o usuario ve o executavel: e ali que ele troca
                          o topologia.json e e ali que o registro e gravado,
                          porque a pasta temporaria deixa de existir;
    pasta_embutida()      a pasta temporaria do empacotador, que guarda a
                          copia de reserva do topologia.json (--add-data).

A ordem do R10 e obrigatoria: procura-se primeiro ao lado do programa e so
entao a copia embutida. Trocar essa ordem faria o arquivo editado pelo
usuario ser ignorado, que e exatamente o que o requisito proibe.
"""

import os
import sys
from dataclasses import dataclass


def pasta_do_programa():
    """Devolve a pasta em que o usuario ve o programa.

    Empacotado, e a pasta do executavel. Executado a partir do codigo-fonte,
    e a raiz do projeto, um nivel acima deste modulo.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pasta_embutida():
    """Pasta onde o empacotador descompactou os dados embutidos, ou None.

    None quando o programa roda a partir do codigo-fonte: ali nao existe
    copia embutida, e o arquivo ao lado do programa e o unico.
    """
    return getattr(sys, "_MEIPASS", None)


def caminho_de(nome_do_arquivo):
    """Monta o caminho de um arquivo ao lado do programa."""
    return os.path.join(pasta_do_programa(), nome_do_arquivo)


@dataclass(frozen=True)
class Origem:
    """De onde um arquivo de dados foi lido, para a tela informar ao usuario."""

    caminho: str
    embutida: bool
    ao_lado: str        # onde o arquivo foi procurado primeiro

    @property
    def descricao(self):
        if self.embutida:
            return "cópia embutida no executável"
        return "arquivo ao lado do programa"

    def __str__(self):
        return f"{self.caminho} ({self.descricao})"


def localizar(nome_do_arquivo):
    """Procura o arquivo ao lado do programa e, so entao, na copia embutida.

    Devolve sempre uma Origem, mesmo quando nada foi encontrado: nesse caso
    ela aponta para o caminho ao lado do programa, que e o que a mensagem de
    erro precisa mostrar ao usuario ("coloque o arquivo aqui").
    """
    ao_lado = caminho_de(nome_do_arquivo)
    if os.path.isfile(ao_lado):
        return Origem(ao_lado, embutida=False, ao_lado=ao_lado)

    embutida = pasta_embutida()
    if embutida:
        caminho = os.path.join(embutida, nome_do_arquivo)
        if os.path.isfile(caminho):
            return Origem(caminho, embutida=True, ao_lado=ao_lado)

    return Origem(ao_lado, embutida=False, ao_lado=ao_lado)
