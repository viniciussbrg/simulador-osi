# Simulador do Modelo OSI

Especificacao aberta, com casos de validacao numericos, para construir um
simulador do modelo OSI de sete camadas sobre uma rede com multiplos
roteadores.

O simulador transporta uma mensagem entre dois computadores e mostra, passo a
passo, o que cada camada de cada dispositivo faz com a unidade de dados que
recebe: os cabecalhos sendo acrescentados na descida e removidos na subida, o
par de enderecos fisicos sendo trocado a cada salto enquanto o par de
enderecos logicos permanece fixo, e a decisao de rota acontecendo na camada 3
de cada roteador.

A linguagem e livre, assim como a arquitetura interna e a forma de
apresentacao. O que esta fixado sao os numeros: quem seguir a especificacao
produz os mesmos resultados de qualquer outra implementacao, em qualquer
linguagem.

## A rede

Tres redes locais, quatro roteadores, cinco computadores. Os custos de enlace
tornam deterministica a escolha de rota, e os enderecos sao fixos, de modo que
duas implementacoes distintas possam ser comparadas linha a linha.

## Casos de validacao

Uma implementacao correta reproduz estes valores. A mensagem de referencia tem
42 octetos, exceto em E7.

| # | Caso | Quadros | Octetos transmitidos | Eficiencia |
|---|------|---------|----------------------|------------|
| E1 | Entrega direta | 1 | 92 | 45,7% |
| E2 | Entrega indireta, tres roteadores | 4 | 368 | 11,4% |
| E3 | Demultiplexacao por porta | 8 | 736 | 11,4% |
| E4 | Falha de enlace e desvio de rota | 4 | 368 | 11,4% |
| E5 | Destino inalcancavel | 1 | 92 | sem entrega |
| E6 | Erro de bit detectado na camada 2 | 3 | 276 | sem entrega |
| E7 | Mensagem longa, tres segmentos | 12 | 968 | 10,3% |

E1 e E2 transportam exatamente a mesma mensagem e diferem apenas no numero de
enlaces. A eficiencia cai de 45,7% para 11,4% sem que um unico octeto de dado
a mais tenha sido enviado. Essa diferenca e o custo do empilhamento, e e o que
o projeto existe para tornar visivel.

## Documentos

| Documento | Conteudo |
|-----------|----------|
| [Especificacao](./docs/especificacao.pdf) | Topologia, enderecos, requisitos, convencoes, os sete casos de validacao com os valores esperados e o passo a passo da entrega |
| [Guia de documentacao](./docs/guia_de_documentacao.pdf) | O que escrever no README, nos tutoriais e na documentacao tecnica |

## Como participar

O fluxo e **fork + pull request**. A `main` guarda apenas a especificacao;
cada implementacao vive na branch do proprio grupo.

1. Fazer o **fork** deste repositorio;
2. Clonar o fork na maquina local (apenas um integrante do grupo precisa);
3. Desenvolver o projeto inteiro no fork, seguindo a estrutura sugerida na
   especificacao;
4. Enviar commits ao longo do desenvolvimento, e nao em um unico envio no
   final;
5. Abrir um **Pull Request** do fork para a **branch do seu grupo** neste
   repositorio, com o titulo no formato
   `Entrega - Grupo X - Nome dos integrantes`;
6. Aguardar a revisao. Apos aprovacao, o trabalho e incorporado a branch
   dedicada do grupo, preservando a autoria de todos os commits.

O passo a passo detalhado, com os comandos e as telas, esta na
[especificacao](./docs/especificacao.pdf).

## Branches

| Branch | Conteudo |
|--------|----------|
| `main` | Especificacao, guia de documentacao e este README |
| `grupo1` a `grupo8` | Uma branch por grupo, com a entrega aprovada |

Nenhum grupo faz commit direto neste repositorio, abre Pull Request para a
`main` ou altera a branch de outro grupo. Uma entrega nessas condicoes e
devolvida sem analise.

## Estrutura

    simulador-osi/
    |-- README.md
    |-- .gitignore
    `-- docs/
        |-- especificacao.pdf
        `-- guia_de_documentacao.pdf

A estrutura do projeto em si, dentro do fork de cada grupo, esta descrita na
especificacao.

## Duvidas e discussao

Abra uma **Issue**. Perguntas sobre a especificacao, casos ambiguos e
divergencias de valores sao discutidos ali, ficam visiveis para todos e evitam
que a mesma questao seja respondida varias vezes.
