# Simulador do Modelo OSI

Projeto prático da disciplina de Comunicação de Dados, ministrada pelo Prof. Vinícius S. Borges. Semestre 2026/2. Grupo 1.

## Autoria

| Integrante | RA |
|---|---|
| Eduardo Souza Urbanovicz Bastiani | 082230018 |
| Ronaldo de Oliveira Santos | 082230031 |
| João Vitor Maciel Nai | 082230004 |

## Como executar

Clique duas vezes em `SimuladorOSI.exe`. Não é necessário instalar nada.

O arquivo `topologia.json` precisa estar na mesma pasta do executável. Se ele não for encontrado, o programa usa a cópia embutida e informa isso na tela.

Para executar a partir do código-fonte, com Python 3.13 instalado:

```
python main.py            # abre a interface gráfica
python main.py --texto    # executa em modo texto, sem janela
```

### Gerar o executável

O `SimuladorOSI.spec` já está pronto e é o mesmo nos dois sistemas:

```
pyinstaller SimuladorOSI.spec
```

O `topologia.json` entra embutido como cópia de reserva. O separador de
`--add-data` (`:` no macOS e no Linux, `;` no Windows) não aparece aqui porque
o spec usa pares `(origem, destino)`, que o PyInstaller resolve sozinho — por
isso não há nada a editar ao trocar de sistema. O equivalente em linha de
comando, caso se prefira, seria `--add-data "topologia.json:."` no macOS e
`--add-data "topologia.json;."` no Windows.

## Descrição

O simulador transporta uma mensagem entre dois computadores de uma rede com três redes locais, quatro roteadores e cinco computadores, e exibe passo a passo o que cada camada de cada dispositivo faz com a unidade de dados que recebe. Os computadores implementam as sete camadas do modelo OSI; os roteadores implementam apenas as três primeiras.

A cada passo a tela mostra o mapa da rede com o caminho percorrido, as pilhas de camadas com a camada ativa em destaque, a unidade de dados desenhada com seus cabeçalhos e o par de endereços lógicos ao lado do par de endereços físicos, deixando visível que o primeiro permanece constante enquanto o segundo é substituído a cada salto. Ao final de cada execução o programa apresenta os octetos transmitidos e a eficiência da comunicação.

## Estrutura do repositório

```
simulador-osi_Grupo1/
├── SimuladorOSI.exe      Programa pronto para executar
├── topologia.json        Rede simulada, editável, ao lado do executável
├── main.py               Ponto de entrada do código-fonte
├── simulador/            Código-fonte do simulador
├── SimuladorOSI.spec     Receita do PyInstaller, igual no Windows e no macOS
├── testes/               Verificação dos valores de referência
├── registros/            Registros de eventos dos sete cenários
└── docs/                 Tutoriais, documentação técnica e capturas
```

Os arquivos de `registros/` são gerados pelo próprio programa, e não à mão:
**Arquivo → Gerar registros dos sete cenários** na interface, ou a opção 7 do
menu em modo texto. Regerá-los depois de qualquer mudança no código garante
que nunca fiquem defasados. Eles são gravados ao lado do executável, nunca na
pasta temporária do empacotador.

## Arquivos de código

| Arquivo | O que faz |
|---|---|
| `main.py` | Ponto de entrada: abre a interface gráfica ou o modo texto |
| `simulador/pdu.py` | Unidade de dados de protocolo e seus cabeçalhos |
| `simulador/camadas.py` | As sete classes de camada, com os dois métodos de sentido oposto |
| `simulador/dispositivos.py` | Pilhas do computador e do roteador |
| `simulador/rede.py` | Topologia, enlaces e tabelas de encaminhamento |
| `simulador/simulador.py` | Motor da simulação e definição dos sete cenários |
| `simulador/registro.py` | Formatação e gravação do registro de eventos |
| `simulador/visual.py` | Interface gráfica em tkinter |
| `simulador/recursos.py` | Topologia ao lado do programa, com a cópia embutida de reserva |

## Requisitos de ambiente

Python 3.13, apenas a biblioteca padrão. A interface usa `tkinter`, que acompanha a instalação oficial do Python.

**Nenhuma biblioteca externa é necessária para executar o programa.** O PyInstaller é usado apenas para gerar o executável e não faz parte da execução.

## Funcionalidades

| O que faz | Onde |
|---|---|
| Encapsulamento e desencapsulamento | `simulador/camadas.py` |
| Cifragem na camada 6, decifrada apenas no destino | `simulador/camadas.py` |
| Segmentação e remontagem em ordem | `simulador/camadas.py` |
| Verificação de erro e descarte do quadro | `simulador/camadas.py` |
| Pilha de sete camadas e pilha de três camadas | `simulador/dispositivos.py` |
| Encaminhamento pelo caminho de menor custo | `simulador/rede.py` |
| Troca da rede simulada por arquivo externo | `simulador/rede.py`, `simulador/recursos.py` |
| Os sete cenários de validação | `simulador/simulador.py` |
| Queda de enlace, erro de bit e destino inalcançável | `simulador/simulador.py` |
| Registro de eventos e cálculo da eficiência | `simulador/registro.py`, `simulador/simulador.py` |
| Mapa da rede, pilhas e unidade de dados desenhada | `simulador/visual.py` |
| Alternância entre a pilha OSI e a pilha TCP/IP | `simulador/visual.py` |

## Cenários de validação

Os sete cenários da especificação são selecionáveis na interface e reproduzem os valores de referência:

| Cenário | Quadros | Octetos transmitidos | Eficiência |
|---|---|---|---|
| E1 Entrega direta | 1 | 92 | 45,7% |
| E2 Entrega indireta | 4 | 368 | 11,4% |
| E3 Demultiplexação | 8 | 736 | 11,4% |
| E4 Falha de enlace | 4 | 368 | 11,4% |
| E5 Destino inalcançável | 1 | 92 | 0,0% |
| E6 Erro de transmissão | 3 | 276 | 0,0% |
| E7 Mensagem longa | 12 | 968 | 10,3% |

Em E5 e E6 nenhum octeto útil chega ao destino: a eficiência é **0**, e é esse
valor que aparece no quadro resumo, na interface e no modo texto.

Os quadros são numerados na ordem de transmissão e reiniciam a cada mensagem
(convenção C5). Em E3, que tem duas mensagens simultâneas, cada uma vai de Q1
a Q4; no registro, o pacote (`H1-P1` e `H2-P1`) diz de qual fluxo é cada
quadro. A porta de origem de cada fluxo (5210 e 6120) aparece nas linhas de
camada 4 de H1, H2 e H4 — os roteadores não a leem, porque não têm camada 4.

A conferência é automatizada. Com o código-fonte, `python testes/teste_cenarios.py` executa os sete cenários e compara cada valor com a tabela acima.

## Documentação

- [Tutorial de execução](./docs/tutorial_execucao.pdf) — como abrir o programa
- [Tutorial de uso](./docs/tutorial_uso.pdf) — como operar cada função
- [Documentação técnica](./docs/documentacao_projeto.pdf) — como o simulador funciona por dentro

## Por onde começar

1. Abra o programa e siga o tutorial de execução
2. Reproduza o cenário E2 pelo tutorial de uso e confira a eficiência de 11,4%
3. Consulte a documentação técnica para entender a separação entre as camadas e as convenções de simulação adotadas
