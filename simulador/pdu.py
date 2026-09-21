"""Unidade de dados de protocolo e seus cabecalhos.

Este modulo define a estrutura que atravessa a pilha de camadas. Ele nao
conhece camadas, dispositivos nem topologia: apenas representa o que esta
sendo transportado em um dado instante e sabe informar o proprio tamanho.

Duas decisoes de modelagem sustentam o restante do projeto:

1. A PDU e imutavel. Encapsular e desencapsular nao alteram o objeto
   recebido: devolvem um objeto novo. E isso que permite exibir quadros
   distintos em cada enlace, conforme a restricao R2 do enunciado, e
   permite que o registro guarde o estado exato de cada passo.

2. O tamanho e sempre derivado, nunca armazenado. Ele resulta da soma dos
   dados com os cabecalhos presentes, de modo que a conta exibida na tela
   e a estrutura desenhada nao possam divergir.
"""

from dataclasses import dataclass, field, replace

# Nome da unidade de dados em cada camada, conforme a Tabela 2 do enunciado.
NOMES_DE_UNIDADE = {
    7: "Mensagem",
    6: "Mensagem",
    5: "Mensagem",
    4: "Segmento",
    3: "Pacote",
    2: "Quadro",
    1: "Bits",
}


@dataclass(frozen=True)
class Cabecalho:
    """Um cabecalho acrescentado por uma camada.

    O tamanho e fixo e vem das convencoes de simulacao, e nao do conteudo
    dos campos: os campos existem para exibicao e para o registro, enquanto
    o tamanho e o que entra na conta de eficiencia.
    """

    camada: int
    tamanho: int
    campos: dict = field(default_factory=dict)
    finalizador: bool = False

    def resumo(self):
        """Devolve os campos em uma linha, para o desenho e o registro."""
        return ", ".join(f"{chave}={valor}" for chave, valor in self.campos.items())


@dataclass(frozen=True)
class PDU:
    """A unidade de dados corrente.

    Os pares de enderecos ficam na PDU, e nao dentro de um cabecalho, porque
    a interface precisa exibir os dois ao mesmo tempo (requisito V4) sem
    percorrer a lista de cabecalhos a cada quadro desenhado.
    """

    dados: bytes
    cabecalhos: tuple = ()
    camada: int = 7

    # Par de enderecos logicos: inserido na origem, constante ate o destino.
    logicos: tuple = (None, None)
    # Par de enderecos fisicos: substituido a cada salto.
    fisicos: tuple = (None, None)
    # Par de portas: identifica os processos nas pontas.
    portas: tuple = (None, None)

    # Identificacao para a tela e o registro.
    sessao: str = ""
    id_pacote: str = ""
    numero_quadro: str = ""
    numero_segmento: int = 1
    total_segmentos: int = 1
    cifrado: bool = False

    # ------------------------------------------------------------------
    # Tamanho
    # ------------------------------------------------------------------

    @property
    def tamanho(self):
        """Tamanho corrente em octetos: dados mais todos os cabecalhos."""
        return len(self.dados) + sum(c.tamanho for c in self.cabecalhos)

    @property
    def tamanho_em_bits(self):
        """Tamanho corrente em bits, usado pela camada 1 no registro."""
        return self.tamanho * 8

    @property
    def nome_da_unidade(self):
        """Nome da unidade na camada em que a PDU se encontra."""
        return NOMES_DE_UNIDADE[self.camada]

    # ------------------------------------------------------------------
    # Encapsulamento
    # ------------------------------------------------------------------

    def encapsular(self, cabecalho, camada=None):
        """Acrescenta um cabecalho e devolve uma PDU nova.

        O cabecalho da camada 2 e inserido no inicio da lista porque e o
        ultimo a ser acrescentado e o primeiro a ser lido; o finalizador
        e mantido no fim, que e onde ele viaja no quadro real.
        """
        if cabecalho.finalizador:
            novos = self.cabecalhos + (cabecalho,)
        else:
            novos = (cabecalho,) + self.cabecalhos
        return replace(
            self,
            cabecalhos=novos,
            camada=camada if camada is not None else self.camada,
        )

    def desencapsular(self, camada_do_cabecalho, camada=None):
        """Remove os cabecalhos de uma camada e devolve uma PDU nova.

        Remove tambem o finalizador da mesma camada, quando existir. A PDU
        original permanece intacta: e ela que o registro exibe como o quadro
        que acabou de ser descartado.
        """
        restantes = tuple(
            c for c in self.cabecalhos if c.camada != camada_do_cabecalho
        )
        return replace(
            self,
            cabecalhos=restantes,
            camada=camada if camada is not None else self.camada,
        )

    def cabecalho_da_camada(self, numero):
        """Devolve o cabecalho de uma camada, ou None se ele nao estiver presente.

        E por aqui que uma camada le o que a sua par inseriu no outro extremo.
        Uma camada que precise chamar este metodo com um numero que nao seja
        o seu proprio esta lendo o que nao lhe pertence.
        """
        for c in self.cabecalhos:
            if c.camada == numero and not c.finalizador:
                return c
        return None

    # ------------------------------------------------------------------
    # Apoio a interface
    # ------------------------------------------------------------------

    def em_blocos(self):
        """Descreve a unidade como blocos, da esquerda para a direita.

        A interface desenha esta lista diretamente (requisito V3): os
        cabecalhos ja acrescentados a esquerda, os dados no meio e o
        finalizador da camada 2 a direita.

        Nas camadas 7 e 6 os dados ainda sao texto: o bloco mede os octetos
        UTF-8, e nao os caracteres, para bater com o tamanho do evento.
        """
        blocos = [
            {"rotulo": f"H{c.camada}", "octetos": c.tamanho, "campos": c.campos}
            for c in self.cabecalhos
            if not c.finalizador
        ]
        if isinstance(self.dados, str):
            octetos_dos_dados = len(self.dados.encode("utf-8"))
        else:
            octetos_dos_dados = len(self.dados)
        blocos.append(
            {"rotulo": "Dados", "octetos": octetos_dos_dados, "campos": {}}
        )
        blocos += [
            {"rotulo": f"T{c.camada}", "octetos": c.tamanho, "campos": c.campos}
            for c in self.cabecalhos
            if c.finalizador
        ]
        return blocos

    def com_fisicos(self, origem, destino, numero_quadro):
        """Devolve uma PDU nova com outro par de enderecos fisicos.

        Usado a cada salto: o quadro que sai de um roteador e um objeto
        distinto do que entrou, com outro par de enderecos e outro numero.
        """
        return replace(
            self, fisicos=(origem, destino), numero_quadro=numero_quadro
        )

    def __str__(self):
        return f"{self.nome_da_unidade} {self.tamanho} B"
