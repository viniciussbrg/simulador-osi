"""Interface comum das camadas OSI (Contexto, classe-base Camada) e as sete
camadas, da 7 (Aplicação) à 1 (Física), cada uma com descer()/subir()."""

import ipaddress
import itertools
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pdu import PDU, Bloco, Quadro, conferir_camada


@dataclass(frozen=True)
class EntradaRota:
    """Uma linha da tabela de encaminhamento consultada pela L3 (ROTEIA).

    `prefixo` é um endereço de rede CIDR — "10.0.3.0/24" numa entrada de
    roteador (todas as redes reais da topologia são /24, seção 3), ou
    "0.0.0.0/0" na entrada de rota padrão que representa o gateway do
    computador (seção 6.3: "senão, próximo salto = gateway" é só uma rota
    padrão como outra qualquer). A consulta é por prefixo mais longo — no
    computador, isso é exatamente o que faz a rede local (/24, mais
    específica) vencer a rota padrão (/0) quando o destino é local, e a
    rota padrão prevalecer nos demais casos, reproduzindo a decisão
    binária sem um código à parte.

    `proximo_salto` é o endereço lógico do próximo salto (ex.:
    "10.0.14.4", a interface do roteador vizinho — mesmo formato da
    coluna "Próximo salto" da tabela em 6.2), não um rótulo de
    dispositivo; None quando a entrega é direta — tanto a rede local do
    computador quanto a rede diretamente conectada de um roteador caem
    nesse caso, e nos dois o vizinho real é o próprio endereço de
    destino.

    Quem monta esta tabela é `dispositivos.py`, traduzindo a topologia
    (computador: rede própria + gateway) ou a tabela de Dijkstra de
    `rede.py` (issues #18–#20) para este formato — `camadas.py` só
    consome, nunca decide o conteúdo."""

    prefixo: str
    interface: str
    custo: int
    proximo_salto: str | None = None


@dataclass
class Contexto:
    # Preenchida por dispositivos.py antes de cada ROTEIA: as rotas
    # conhecidas por este dispositivo neste momento (issue #19/#20). A L3
    # só lê — nunca decide sozinha o conteúdo da tabela.
    tabela_encaminhamento: list[EntradaRota] | None = None

    # Preenchido pela L3 na descida (R4): a L2 lê vizinho/interface_saida
    # como parâmetro de entrada, sem acesso à tabela de encaminhamento.
    vizinho: str | None = None
    interface_saida: str | None = None
    fluxo: str | None = None

    # Endereço físico do salto atual. Na descida, preenchido por
    # dispositivos.py antes de cada ENQUADRA — o dispositivo resolve, a
    # partir da decisão da L3 (ctx.vizinho/interface_saida) e da
    # topologia, o MAC da própria interface de saída (origem) e o do
    # vizinho naquele enlace (destino); é o passo análogo a ARP, feito
    # fora da camada. A L2 apenas lê esses dois para montar o cabeçalho
    # H2 (destino antes de origem, seção 3.3) e não tem como tocar no par
    # lógico, que fica no H3 dentro do pacote que ela só encapsula (R3).
    # Na subida, é a própria L2 que os grava, lidos do H2 do quadro
    # recebido, para quem monta o Evento descrever o salto.
    fisico_origem: str | None = None
    fisico_destino: str | None = None

    # MAC da interface pela qual este nó recebeu o quadro (preenchido por
    # dispositivos.py antes de cada DESENQUADRA). A L2 compara o destino
    # físico lido do quadro com este valor: se diferirem, o quadro é de
    # outra estação do mesmo segmento de difusão e a subida vira IGNORA
    # (evento secundário, seção 7.5). None desliga a checagem — enlace
    # ponto-a-ponto ou teste que não exercita difusão — e o quadro é
    # sempre entregue.
    fisico_local: str | None = None

    # Identificador do quadro do salto atual (Q1, Q2, …). Na descida, a L2
    # grava aqui o `id` do `Quadro` recém-construído (que o obteve do
    # contador global — R2); na subida, o `id` lido do quadro recebido.
    # Alimenta o campo `quadro` do Evento (seção 7.2), que só a camada 2
    # preenche.
    quadro: str | None = None

    # Resultado da última subida pela camada 2, escrito por
    # CamadaEnlace.subir e lido por quem monta o Evento para escolher a
    # ação/estado: ENLACE_OK (verificação correta e quadro endereçado a
    # este nó → DESENQUADRA), ENLACE_ERRO_CRC (CRC recalculado diverge do
    # finalizador → DESCARTA com estado "erro", usado por C6) ou
    # ENLACE_ENDERECO_ALHEIO (verificação correta, mas destino físico ≠
    # interface local → IGNORA, secundário).
    resultado_enlace: str | None = None

    # Enlace físico atravessado no salto atual (id "E-A", rótulo "H1–R1").
    # Preenchido por dispositivos.py/simulador.py antes de cada
    # TRANSMITE/RECEBE, a partir da decisão da L3 (ctx.interface_saida) e
    # da topologia — mesmo padrão de fisico_origem/destino: a L1 recebe o
    # enlace como dado de contexto pronto, nunca consulta rede.py. Alimenta
    # os campos enlace.id/enlace.rotulo do Evento (seção 7.2), que só
    # fazem sentido a partir da camada 1.
    enlace_id: str | None = None
    enlace_rotulo: str | None = None

    # Tamanho da PDU do salto atual em bits. Escrito unicamente pela L1
    # (TRANSMITE e RECEBE), como tamanho_em_octetos × 8 — o único cálculo
    # da camada física, que não acrescenta octetos (seção 3.1/3.2). Lido
    # por quem monta o Evento e anexado só a eventos de camada 1 (campo
    # `bits` da seção 7.2). Verificação de referência: quadro de 92 B em
    # C2 → 736 bits, linha 008 do Anexo B.
    bits: int | None = None

    # Preenchido por quem inicia o envio, antes de chamar a L3 (mesmo
    # padrão de ctx.mensagem): o par lógico de ponta a ponta. A L3 da
    # origem grava esse par no cabeçalho H3 uma única vez (restrição R3)
    # e nunca mais é alterado — nem por esta camada em roteadores
    # intermediários, nem por nenhuma outra.
    logico_origem: str | None = None
    logico_destino: str | None = None

    # Gravada pela L3 a cada ROTEIA (origem e roteadores intermediários),
    # para quem monta o Evento descrever a decisão (prefixo, custo,
    # via/diretamente conectada). None quando DESCARTA (ausência de rota).
    rota: EntradaRota | None = None

    # Preenchido por quem inicia o envio, antes de chamar a L7: a mensagem
    # de texto do caso e os nomes de processo de origem/destino. A L7 lê
    # esses campos para "gerar" a PDU inicial na descida.
    mensagem: str | None = None
    processo_origem: str | None = None
    processo_destino: str | None = None

    # Preenchido pela L5: ABRE grava o identificador gerado na descida,
    # ENCERRA grava o identificador lido do cabeçalho na subida — em ambos
    # os casos para quem monta o Evento ler depois (campo só existe em
    # computadores, nunca em roteadores — R1).
    sessao: str | None = None

    # Porta: preenchida por quem inicia o envio, junto de
    # processo_origem/destino — a L4 lê os dois na descida para montar o
    # cabeçalho H4 (campo só existe em computadores — R1). Na subida, é a
    # própria L4 que grava os dois, lidos do cabeçalho do segmento
    # recebido, para quem monta o Evento ler.
    porta_origem: int | None = None
    porta_destino: int | None = None

    # Segmento: preenchido pela L4 nas duas direções. Na descida, grava o
    # total de segmentos em que a mensagem foi partida (decisão D1). Na
    # subida, grava o par (n, total) lido de cada segmento recebido, até a
    # remontagem completar.
    segmento_n: int | None = None
    segmento_total: int | None = None


class Camada(ABC):
    numero: int
    nome: str

    @abstractmethod
    def descer(self, pdu: PDU, ctx: Contexto) -> PDU:
        """Recebe a unidade da camada superior, processa e devolve à inferior."""

    @abstractmethod
    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """Recebe a unidade da camada inferior, processa e devolve à superior.
        Devolve None quando a unidade é descartada nesta camada."""


class CamadaAplicacao(Camada):
    numero = 7
    nome = "Aplicação"

    def descer(self, pdu: PDU, ctx: Contexto) -> PDU:
        """GERA: cria a PDU inicial a partir de ctx.mensagem. Não soma
        octetos além do tamanho da própria mensagem — a camada 7 não
        acrescenta cabeçalho, só metadado (processo.origem/destino), que
        fica em ctx para o motor de eventos ler depois."""
        assert ctx.mensagem is not None, "GERA exige ctx.mensagem preenchida"
        dados = Bloco(
            rotulo="Dados",
            tam=len(ctx.mensagem.encode("utf-8")),
            tipo="dados",
            conteudo=ctx.mensagem,
        )
        return PDU(nome="Mensagem", blocos=[dados])

    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """ENTREGA: confirma a entrega ao processo de destino sem
        transformar o conteúdo — devolve a PDU recebida inalterada."""
        return pdu


_CHAVE_CIFRA_L6 = "REDES"


def _xor_cifra(dados: bytes, chave: str = _CHAVE_CIFRA_L6) -> bytes:
    """XOR com a chave repetida ciclicamente (decisão D2). Autoinverso —
    a mesma operação cifra e decifra — e length-preserving por construção,
    ao contrário de um algoritmo de bloco com preenchimento."""
    chave_bytes = chave.encode("utf-8")
    return bytes(b ^ chave_bytes[i % len(chave_bytes)] for i, b in enumerate(dados))


class CamadaApresentacao(Camada):
    numero = 6
    nome = "Apresentação"

    def descer(self, pdu: PDU, ctx: Contexto) -> PDU:
        """CODIFICA: registra os octetos UTF-8 da mensagem (já produzidos
        pela camada 7) e cifra o conteúdo com XOR (D2). Não soma octetos —
        esquema de codificação e cifra são metadado, não payload."""
        dados = pdu.blocos[0]
        assert isinstance(dados.conteudo, str), "CODIFICA espera texto vindo da L7"
        octetos = dados.conteudo.encode("utf-8")
        cifrado = Bloco(
            rotulo=dados.rotulo,
            tam=dados.tam,
            tipo=dados.tipo,
            conteudo=_xor_cifra(octetos),
        )
        return PDU(nome=pdu.nome, blocos=[cifrado])

    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """DECIFRA: aplica o mesmo XOR (autoinverso) para recuperar o
        texto original em UTF-8."""
        dados = pdu.blocos[0]
        assert isinstance(dados.conteudo, bytes), "DECIFRA espera bytes cifrados vindos da L5"
        texto = _xor_cifra(dados.conteudo).decode("utf-8")
        decifrado = Bloco(
            rotulo=dados.rotulo,
            tam=dados.tam,
            tipo=dados.tipo,
            conteudo=texto,
        )
        return PDU(nome=pdu.nome, blocos=[decifrado])


_PREFIXO_SESSAO = "S-"
_DIGITOS_SESSAO = 4
_TAM_CABECALHO_SESSAO = 4  # H5 — referenciado também por CamadaTransporte.subir ao remontar
_contador_sessoes = itertools.count(1)


def reiniciar_contador_sessoes() -> None:
    """Reinicia a numeração de sessões (S-0001…) para uma nova execução.

    Contador global (módulo), não por instância/dispositivo: a unicidade
    exigida (C3 — dois fluxos concorrentes originados em hosts diferentes
    precisam de sessões distintas, S-0001 e S-0002) vale para a execução
    inteira, não por computador. O contador análogo de quadros (R2) fica em
    `pdu.py` (`pdu.reiniciar_contador_quadros`)."""
    global _contador_sessoes
    _contador_sessoes = itertools.count(1)


class CamadaSessao(Camada):
    numero = 5
    nome = "Sessão"

    def descer(self, pdu: PDU, ctx: Contexto) -> PDU:
        """ABRE: gera um identificador de sessão novo (contador global,
        formato S-NNNN conforme parametros.sessao do topologia.json),
        grava em ctx.sessao para o motor de eventos usar na descrição, e
        acrescenta o cabeçalho H5 — primeiro a pesar na contagem de
        octetos (+4, fixo e simbólico, como todo cabeçalho do simulador)."""
        sessao = f"{_PREFIXO_SESSAO}{next(_contador_sessoes):0{_DIGITOS_SESSAO}d}"
        ctx.sessao = sessao
        cabecalho = Bloco(
            rotulo="H5", tam=_TAM_CABECALHO_SESSAO, tipo="cabecalho",
            conteudo=sessao, camada=self.numero,
        )
        return PDU(nome=pdu.nome, blocos=[cabecalho, *pdu.blocos])

    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """ENCERRA: remove o cabeçalho H5 — conferindo que foi a camada 5 par
        quem o inseriu (R5, issue #13) — e grava o identificador lido em
        ctx.sessao. No motor, ocorre depois que a camada 4 já
        remontou/entregou o conteúdo à camada 5 (ordem exigida em C7,
        issue #42)."""
        cabecalho, resto = pdu.remover_cabecalho(self.numero)
        assert cabecalho.rotulo == "H5", "ENCERRA espera cabeçalho H5 no topo da PDU"
        ctx.sessao = cabecalho.conteudo
        return resto


_TAM_CABECALHO_L4 = 8
_LIMITE_SEGMENTO_PADRAO = 64  # decisão D1; sobrescrito por parametros.limite_segmento do
                              # topologia.json quando dispositivos.py montar a pilha


def _bytes_dos_dados(bloco: Bloco) -> bytes:
    """Octetos reais do bloco de dados. Ao contrário de um cabeçalho — cujo
    `tam` é uma convenção fixa e simbólica, desacoplada do conteúdo (H5
    declara 4 octetos mesmo carregando a string "S-0001", 6 caracteres) —
    o bloco de dados tem `tam` sempre igual ao comprimento real do
    conteúdo (GERA mede a mensagem codificada; CODIFICA preserva o
    comprimento por construção do XOR). É por isso que só o bloco de
    dados pode ser fatiado byte a byte; cabeçalhos são sempre atômicos."""
    conteudo = bloco.conteudo
    return conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo


class CamadaTransporte(Camada):
    numero = 4
    nome = "Transporte"

    def __init__(self, limite_segmento: int = _LIMITE_SEGMENTO_PADRAO) -> None:
        self._limite = limite_segmento
        # Pedaços já recebidos de cada fluxo em remontagem, por porta de
        # origem — é essa chave que resolve a demultiplexação (C3): dois
        # fluxos concorrentes chegando a este destino nunca se misturam,
        # porque cada um acumula no seu próprio balde. Guarda também os
        # cabeçalhos superiores (H5...) vistos no primeiro segmento, para
        # devolvê-los intactos na PDU remontada.
        self._pendentes: dict[int, dict[int, bytes]] = {}
        self._cabecalhos_superiores: dict[int, list[Bloco]] = {}

    def descer(self, pdu: PDU, ctx: Contexto) -> list[PDU]:
        """SEGMENTA: fatia a carga útil (o bloco de dados recebido da L5)
        em pedaços de até `limite_segmento` octetos (D1) e monta um
        Segmento por pedaço, cada um com o cabeçalho H4 (+8 octetos,
        portas de origem/destino e numeração). Os cabeçalhos superiores
        (H5...) que vieram com a PDU não são fatiados — são símbolos
        atômicos, não uma sequência de octetos real — e viajam inteiros
        no primeiro segmento, contando pelo `tam` declarado no orçamento
        dos 64 octetos: é o que faz 184 B (4 de H5 + 180 de dados) virar
        64+64+56 em C7 (60 de dados no primeiro segmento, para caber ao
        lado dos 4 B de H5).

        Único método de camada que devolve uma **lista** em vez de uma
        PDU só — é a própria natureza da segmentação: uma mensagem vira N
        quadros independentes (D5, numeração global contínua). Quem
        chama (a pilha do dispositivo, ainda não implementada — issue
        #27) deve empurrar cada elemento da lista pela L3→L1 na ordem
        devolvida, um quadro por segmento."""
        assert ctx.porta_origem is not None and ctx.porta_destino is not None, (
            "SEGMENTA exige ctx.porta_origem/porta_destino preenchidas"
        )
        *cabecalhos_superiores, dados = pdu.blocos
        orcamento_cabecalhos = sum(c.tam for c in cabecalhos_superiores)
        buffer_dados = _bytes_dos_dados(dados)

        limite_primeiro = max(self._limite - orcamento_cabecalhos, 0)
        fatias = []
        cursor = 0
        fim = min(limite_primeiro, len(buffer_dados))
        fatias.append(buffer_dados[cursor:fim])
        cursor = fim
        while cursor < len(buffer_dados):
            fim = min(cursor + self._limite, len(buffer_dados))
            fatias.append(buffer_dados[cursor:fim])
            cursor = fim
        total = len(fatias)

        segmentos = []
        for n, fatia in enumerate(fatias, start=1):
            ctx.segmento_n = n
            ctx.segmento_total = total
            cabecalho_l4 = Bloco(
                rotulo="H4",
                tam=_TAM_CABECALHO_L4,
                tipo="cabecalho",
                conteudo=f"{ctx.porta_origem}:{ctx.porta_destino}:{n}:{total}",
                camada=self.numero,
            )
            blocos_segmento = [cabecalho_l4]
            if n == 1:
                blocos_segmento.extend(cabecalhos_superiores)
            blocos_segmento.append(Bloco(rotulo="Dados", tam=len(fatia), tipo="dados", conteudo=fatia))
            segmentos.append(PDU(nome="Segmento", blocos=blocos_segmento))
        return segmentos

    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """DEMULTIPLEXA / REMONTA: remove o cabeçalho H4 de um segmento
        recebido e grava porta e numeração em ctx para quem monta o
        Evento descrever (DEMULTIPLEXA quando há mais de um fluxo
        concorrente chegando a este destino, REMONTA ao fechar a
        mensagem — a escolha do rótulo da ação cabe a quem monta o
        Evento, não a esta classe). Acumula os pedaços de dados por porta
        de origem; devolve None enquanto faltar segmento (mesma
        convenção de descarte da interface, aqui reaproveitada para
        "ainda não completo"), e devolve a PDU remontada — cabeçalhos
        superiores intactos (vindos do primeiro segmento) seguidos do
        bloco de dados reunido — pronta para a L5, só quando o último
        pedaço chega, nunca antes (ordem exigida em C7, issue #42)."""
        cabecalho, pdu_sem_h4 = pdu.remover_cabecalho(self.numero)  # R5 (issue #13)
        assert cabecalho.rotulo == "H4", "REMONTA espera cabeçalho H4 no topo do segmento"
        assert isinstance(cabecalho.conteudo, str), "cabeçalho H4 deve ter conteúdo textual"
        origem_str, destino_str, n_str, total_str = cabecalho.conteudo.split(":")
        porta_origem, porta_destino, n, total = (
            int(origem_str), int(destino_str), int(n_str), int(total_str),
        )

        ctx.porta_origem = porta_origem
        ctx.porta_destino = porta_destino
        ctx.segmento_n = n
        ctx.segmento_total = total

        *cabecalhos_superiores, dados = pdu_sem_h4.blocos
        if n == 1:
            self._cabecalhos_superiores[porta_origem] = cabecalhos_superiores
            # Um novo fluxo começando nesta porta descarta qualquer resto de
            # uma remontagem anterior abandonada (ex.: segmento perdido por
            # erro de CRC, C6) — sem isto, pedaços de um fluxo morto podiam
            # se misturar com os de um fluxo novo que reusasse a porta.
            self._pendentes[porta_origem] = {}

        pedacos_recebidos = self._pendentes.setdefault(porta_origem, {})
        pedacos_recebidos[n] = _bytes_dos_dados(dados)
        if any(i not in pedacos_recebidos for i in range(1, total + 1)):
            return None

        buffer_dados = b"".join(pedacos_recebidos[i] for i in range(1, total + 1))
        del self._pendentes[porta_origem]
        cabecalhos_superiores = self._cabecalhos_superiores.pop(porta_origem)

        dados_remontados = Bloco(rotulo="Dados", tam=len(buffer_dados), tipo="dados", conteudo=buffer_dados)
        return PDU(nome="Mensagem", blocos=[*cabecalhos_superiores, dados_remontados])


_TAM_CABECALHO_L3 = 20


def par_logico_do_h3(conteudo: str) -> tuple[str, str]:
    """(origem, destino) gravados no conteúdo de um cabeçalho H3 — o formato
    que `CamadaRede.descer`/`roteia` escrevem e leem, exposto aqui para que
    quem só precisa ler o par (dispositivos.py, para o Evento) não precise
    reimplementar o formato do cabeçalho."""
    origem, destino = conteudo.split(":")
    return origem, destino


class CamadaRede(Camada):
    numero = 3
    nome = "Rede"

    def descer(self, pdu: PDU, ctx: Contexto) -> PDU:
        """ENCAPSULA: grava o par lógico de ponta a ponta — uma única vez,
        aqui, na L3 da origem (restrição R3) — no cabeçalho H3 (+20
        octetos, conteúdo simbólico) e nunca mais é alterado dali em
        diante, nem por esta mesma camada em roteadores intermediários
        (que não chamam `descer`/`subir`, só `roteia`). Só quem inicia o
        envio preenche ctx.logico_origem/logico_destino (mesmo padrão de
        ctx.mensagem); esta camada apenas lê e grava no pacote."""
        assert ctx.logico_origem is not None and ctx.logico_destino is not None, (
            "ENCAPSULA exige ctx.logico_origem/logico_destino preenchidas"
        )
        cabecalho = Bloco(
            rotulo="H3",
            tam=_TAM_CABECALHO_L3,
            tipo="cabecalho",
            conteudo=f"{ctx.logico_origem}:{ctx.logico_destino}",
            camada=self.numero,
        )
        return PDU(nome="Pacote", blocos=[cabecalho, *pdu.blocos])

    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """DESENCAPSULA: no destino final, remove o cabeçalho H3 pelo caminho
        conferido de R5 (issue #13) — `remover_cabecalho` só entrega o bloco
        se o número gravado nele (`Bloco.camada`) for o desta camada, o que
        só a camada 3 par, na origem, gravou. Um roteador intermediário nunca
        chega aqui: sua pilha só tem L1–L3 e chama `roteia`, não `subir`
        (R1)."""
        cabecalho, resto = pdu.remover_cabecalho(self.numero)
        assert cabecalho.rotulo == "H3", "DESENCAPSULA espera cabeçalho H3 no topo do pacote"
        return resto

    def roteia(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """ROTEIA: consulta ctx.tabela_encaminhamento pelo prefixo mais
        longo que contém o endereço lógico de destino lido do cabeçalho
        H3. Roteador e computador usam a mesma consulta aqui — a
        "decisão binária" do computador (seção 6.3) é só uma tabela de
        duas entradas (rede local /24 e rota padrão 0.0.0.0/0 para o
        gateway) sob o mesmo algoritmo de prefixo mais longo do roteador
        (seção 6.2); é por isso que o computador nunca descarta por
        conta própria (0.0.0.0/0 sempre casa) — só o roteador, com tabela
        genuinamente incompleta, descobre a ausência de rota (C5).

        Grava a decisão em ctx.vizinho/ctx.interface_saida — parâmetro de
        entrada que a L2 lê sem acesso à tabela (R4) — e em ctx.rota,
        para quem monta o Evento descrever.

        Roda nos dois sentidos: na origem, logo após ENCAPSULA; e em
        qualquer roteador intermediário, sem passar por `descer`/`subir`
        (o pacote nunca é desencapsulado nem alterado aqui — só o próximo
        salto é decidido). Por não existir em CamadaEnlace, esta ação é
        estruturalmente impossível na camada 2 (R4, testada em T-R4).

        DESCARTA: quando nenhuma entrada da tabela contém o destino,
        zera ctx.rota/vizinho/interface_saida e devolve None — o pacote é
        destruído aqui e nenhuma camada superior é acionada a partir daí
        (C5, issue #31); quem chama deve interromper a pilha do
        dispositivo ao ver None, do mesmo jeito que a L4 sinaliza
        remontagem incompleta."""
        assert ctx.tabela_encaminhamento is not None, (
            "ROTEIA exige ctx.tabela_encaminhamento preenchida antes da chamada"
        )
        cabecalho = pdu.blocos[0]
        assert cabecalho.rotulo == "H3", "ROTEIA espera cabeçalho H3 no topo do pacote"
        assert isinstance(cabecalho.conteudo, str), "cabeçalho H3 deve ter conteúdo textual"
        _, destino_str = par_logico_do_h3(cabecalho.conteudo)
        destino = ipaddress.ip_address(destino_str)

        correspondentes = [
            entrada for entrada in ctx.tabela_encaminhamento
            if destino in ipaddress.ip_network(entrada.prefixo, strict=False)
        ]
        if not correspondentes:
            ctx.rota = None
            ctx.vizinho = None
            ctx.interface_saida = None
            return None

        mais_especifica = max(
            ipaddress.ip_network(entrada.prefixo, strict=False).prefixlen
            for entrada in correspondentes
        )
        escolhidas = [
            entrada for entrada in correspondentes
            if ipaddress.ip_network(entrada.prefixo, strict=False).prefixlen == mais_especifica
        ]
        assert len(escolhidas) <= 1, (
            "tabela de encaminhamento não deveria ter mais de um prefixo igualmente específico "
            "para o mesmo destino (desempate é responsabilidade de quem monta a tabela — issue #21)"
        )

        escolhida = escolhidas[0]
        ctx.rota = escolhida
        ctx.vizinho = escolhida.proximo_salto or destino_str
        ctx.interface_saida = escolhida.interface
        return pdu


_TAM_CABECALHO_L2 = 14


def par_fisico_do_h2(conteudo: str) -> tuple[str, str]:
    """(origem, destino) gravados no conteúdo de um cabeçalho H2 — já na
    ordem do evento (origem antes de destino); no H2 em si a ordem é a da
    Aula 2 (destino antes de origem), convertida aqui uma vez só para quem
    só precisa ler o par (dispositivos.py, para o Evento)."""
    destino, origem = conteudo.split(";")
    return origem, destino
_TAM_FINALIZADOR_L2 = 4

# O identificador do quadro e a numeração global (Q1, Q2, …) vivem em `pdu.py`,
# dentro do próprio tipo `Quadro` (restrição R2): ver `Quadro` e
# `pdu.reiniciar_contador_quadros`. A camada 2 não numera nada por conta
# própria — só constrói `Quadro` na descida e o consome na subida.


# Valores possíveis de ctx.resultado_enlace depois de CamadaEnlace.subir —
# quem monta o Evento traduz cada um em ação/estado (ver docstring de
# subir e o comentário do campo em Contexto).
ENLACE_OK = "ok"
ENLACE_ERRO_CRC = "erro"
ENLACE_ENDERECO_ALHEIO = "endereco_alheio"


_POLINOMIO_CRC32 = 0xEDB88320


def _tabela_crc32() -> tuple[int, ...]:
    """Tabela de 256 entradas do CRC-32 refletido, polinômio 0xEDB88320
    (decisão D3), construída no próprio código — sem zlib nem qualquer
    biblioteca externa. É a mesma tabela do CRC-32/ISO-HDLC de Ethernet."""
    tabela = []
    for octeto in range(256):
        acc = octeto
        for _ in range(8):
            acc = (acc >> 1) ^ (_POLINOMIO_CRC32 if acc & 1 else 0)
        tabela.append(acc)
    return tuple(tabela)


_TABELA_CRC32 = _tabela_crc32()


def crc32(dados: bytes) -> int:
    """CRC-32 de `dados` — polinômio 0xEDB88320, valores inicial e final
    invertidos, como em Ethernet/zlib. Resultado em 32 bits sem sinal.

    Detecta com garantia matemática qualquer erro de bit único,
    independentemente do tamanho do quadro (qualquer polinômio com mais
    de um termo o faz). É o cálculo que reprova o quadro corrompido de C6
    e que T-CRC (issue #46) verifica exaustivamente."""
    acc = 0xFFFFFFFF
    for octeto in dados:
        acc = (acc >> 8) ^ _TABELA_CRC32[(acc ^ octeto) & 0xFF]
    return acc ^ 0xFFFFFFFF


def _octetos_do_quadro(blocos: list[Bloco]) -> bytes:
    """Serialização determinística e sem ambiguidade dos blocos para o
    cálculo do CRC: cada bloco entra com rótulo, `tam` declarado e
    conteúdo real, todos precedidos do próprio comprimento. Cabeçalhos
    carregam texto simbólico (`str`); o bloco de dados carrega os octetos
    cifrados (`bytes`); ambos são normalizados para octetos aqui. O
    finalizador T2 nunca é passado a esta função — o CRC cobre tudo que
    vem antes dele (cabeçalho H2 inclusive, como o FCS de Ethernet)."""
    buffer = bytearray()
    for bloco in blocos:
        conteudo = bloco.conteudo
        if conteudo is None:
            octetos = b""
        elif isinstance(conteudo, bytes):
            octetos = conteudo
        else:
            octetos = conteudo.encode("utf-8")
        rotulo = bloco.rotulo.encode("utf-8")
        buffer += len(rotulo).to_bytes(1, "big") + rotulo
        buffer += bloco.tam.to_bytes(2, "big")
        buffer += len(octetos).to_bytes(4, "big") + octetos
    return bytes(buffer)


class CamadaEnlace(Camada):
    numero = 2
    nome = "Enlace"

    # Sem método roteia() e com AcaoL2 fechado em ENQUADRA/DESENQUADRA/
    # DESCARTA/IGNORA (constantes.py): a ação ROTEIA é estruturalmente
    # inalcançável nesta camada — é assim que R4 deixa de ser convenção
    # (T-R4, issue #38).

    def descer(self, pdu: PDU, ctx: Contexto) -> Quadro:
        """ENQUADRA: cria um quadro **novo** envolvendo o pacote recebido da
        L3 no cabeçalho H2 (+14 octetos) e no finalizador T2 (+4 octetos),
        este carregando o CRC-32 calculado sobre H2 + pacote.

        R2 ("o quadro nunca é reescrito") é estrutural, não de disciplina: o
        único caminho aqui é construir um `Quadro`, e o `Quadro` tira sozinho
        o identificador novo (`Q1`, `Q2`, …) do contador global de `pdu.py`
        — esta camada não tem como reaproveitar um id nem devolver um objeto
        quadro já existente. O id gerado fica em ctx.quadro para quem monta o
        Evento (é atributo do objeto, não campo do H2: numeração de quadro é
        rótulo de simulação, não dado que trafega no enlace).

        O par de endereços físicos do salto chega pronto em
        ctx.fisico_origem/ctx.fisico_destino (resolvido por dispositivos.py a
        partir da decisão da L3 e da topologia — R4: a L2 recebe o salto como
        parâmetro, não consulta tabela alguma). Esta camada grava esse par no
        H2 na ordem da Aula 2 (destino antes de origem); o par lógico, no H3
        dentro do pacote, permanece intocável (R3)."""
        assert ctx.fisico_origem is not None and ctx.fisico_destino is not None, (
            "ENQUADRA exige ctx.fisico_origem/fisico_destino preenchidas "
            "(resolvidas por dispositivos.py a partir da decisão da L3)"
        )
        cabecalho = Bloco(
            rotulo="H2",
            tam=_TAM_CABECALHO_L2,
            tipo="cabecalho",
            conteudo=f"{ctx.fisico_destino};{ctx.fisico_origem}",
            camada=self.numero,
        )
        blocos_sem_crc = [cabecalho, *pdu.blocos]
        finalizador = Bloco(
            rotulo="T2",
            tam=_TAM_FINALIZADOR_L2,
            tipo="finalizador",
            conteudo=f"{crc32(_octetos_do_quadro(blocos_sem_crc)):08X}",
            camada=self.numero,
        )
        quadro = Quadro([*blocos_sem_crc, finalizador])
        ctx.quadro = quadro.id
        return quadro

    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """DESENQUADRA / DESCARTA / IGNORA: lê o quadro recebido, **destrói-o**
        (`Quadro.consumir()` — R2) e grava o desfecho em ctx.resultado_enlace
        para quem monta o Evento:

        - recalcula o CRC-32 sobre tudo que precede o finalizador e compara
          com o valor guardado em T2. Divergiu → ENLACE_ERRO_CRC, devolve
          None, a L3 não é acionada (C6);
        - confere o endereço: se ctx.fisico_local está definido e não é o
          destino físico do quadro, este nó é só mais uma estação do segmento
          de difusão → ENLACE_ENDERECO_ALHEIO, devolve None (IGNORA,
          secundário);
        - caso contrário → ENLACE_OK: o pacote extraído (PDU nova, blocos
          entre H2 e T2) segue para a L3.

        Antes de qualquer desfecho, `conferir_camada` exige que H2 e T2
        tenham sido inseridos pela camada 2 par deste salto (R5, issue #13):
        o cabeçalho de enlace é criado e destruído a cada enlace, então a
        conferência é sempre contra a L2 do salto atual, nunca de ponta a
        ponta.

        O quadro é consumido nos três desfechos — um quadro descartado
        também não sobrevive. Depois de `subir` o objeto está inerte:
        qualquer tentativa de reenviá-lo levanta `QuadroConsumido`, e o
        próximo salto é obrigado a enquadrar um quadro novo.

        ctx.quadro/fisico_origem/fisico_destino são preenchidos com o que foi
        lido do quadro antes da verificação, para que a descrição do descarte
        também nomeie o quadro (C6: "quadro Q3 descartado")."""
        assert isinstance(pdu, Quadro), (
            "DESENQUADRA só atua sobre um Quadro — o objeto construído por um "
            "ENQUADRA anterior e entregue intacto pela camada 1"
        )
        cabecalho = pdu.blocos[0]
        finalizador = pdu.blocos[-1]
        assert cabecalho.rotulo == "H2", "DESENQUADRA espera cabeçalho H2 no topo do quadro"
        assert finalizador.rotulo == "T2", "DESENQUADRA espera finalizador T2 no fim do quadro"
        assert isinstance(cabecalho.conteudo, str), "cabeçalho H2 deve ter conteúdo textual"
        assert isinstance(finalizador.conteudo, str), "finalizador T2 deve ter conteúdo textual"
        conferir_camada(cabecalho, self.numero)    # R5 (issue #13): só a L2 par
        conferir_camada(finalizador, self.numero)  # deste salto tira H2 e T2

        fisico_origem, fisico_destino = par_fisico_do_h2(cabecalho.conteudo)
        ctx.fisico_origem = fisico_origem
        ctx.fisico_destino = fisico_destino
        ctx.quadro = pdu.id

        crc_recebido = int(finalizador.conteudo, 16)
        crc_calculado = crc32(_octetos_do_quadro(pdu.blocos[:-1]))

        if crc_calculado != crc_recebido:
            ctx.resultado_enlace = ENLACE_ERRO_CRC
            pacote = None
        elif ctx.fisico_local is not None and ctx.fisico_local != fisico_destino:
            ctx.resultado_enlace = ENLACE_ENDERECO_ALHEIO
            pacote = None
        else:
            ctx.resultado_enlace = ENLACE_OK
            pacote = PDU(nome="Pacote", blocos=pdu.blocos[1:-1])

        pdu.consumir()
        return pacote


class CamadaFisica(Camada):
    numero = 1
    nome = "Física"

    # Sem cabeçalho, sem finalizador, sem contador: a camada 1 é a única
    # que não transforma a PDU. Não existe uma ação de "escolher enlace"
    # aqui (o enlace chega decidido em ctx, resolvido a partir da L3) —
    # simetricamente ao que R4 faz com a L2, a física só registra o
    # trânsito, nunca o encaminha.

    def descer(self, pdu: PDU, ctx: Contexto) -> PDU:
        """TRANSMITE: converte o quadro recebido da L2 em bits
        (tamanho_em_octetos × 8, gravado em ctx.bits) e o coloca no enlace
        físico do salto, cujo id/rótulo chegam prontos em
        ctx.enlace_id/ctx.enlace_rotulo — resolvidos por dispositivos.py a
        partir de ctx.interface_saida e da topologia, no mesmo molde de
        fisico_origem/destino (a L1 não importa rede.py).

        Não acrescenta octetos e não transforma a PDU: devolve o **mesmo**
        objeto quadro, que atravessa o enlace inalterado — a inversão de
        bit de C6 é injetada por simulador.py sobre o quadro em trânsito,
        nunca por esta camada. Não há temporização: o evento apenas
        registra que N bits transitaram pelo enlace Y."""
        ctx.bits = pdu.tamanho() * 8
        return pdu

    def subir(self, pdu: PDU, ctx: Contexto) -> PDU | None:
        """RECEBE: contrapartida exata de `descer` no nó seguinte do
        enlace — recalcula o tamanho em bits (ctx.bits = tamanho × 8) do
        quadro que chegou pelo enlace físico do salto
        (ctx.enlace_id/ctx.enlace_rotulo, preenchidos por dispositivos.py)
        e entrega esse mesmo quadro à L2 sem tocá-lo. O octeto do
        enunciado ("preâmbulo") entra só na descrição do evento, nunca na
        contagem."""
        ctx.bits = pdu.tamanho() * 8
        return pdu
