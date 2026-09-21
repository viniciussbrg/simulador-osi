# Simulador do Modelo OSI

Projeto prático da disciplina de **Comunicação de Dados**, ministrada pelo
Prof. **Vinícius S. Borges**. 2º semestre de 2026.

## Como executar

Na raiz do projeto, clique duas vezes em **`SimuladorOSI.exe`**. Não é
necessário instalar nada. O executável lê a rede do `topologia.json`, que fica
na mesma pasta.

O passo a passo, com capturas de tela, está no
[Tutorial de execução](docs/tutorial_execucao.pdf).

A partir do código-fonte, com Python 3.11 ou mais recente:

```bash
python app.py
```

## Autoria

| RA | Nome |
|---|---|
| 082230002 | Diogo Santos Rodrigues |
| 082230012 | Leonardo Rosário Teixeira |
| 082230019 | Bianca Ricci Lima |
| 082230024 | Ryan Corazza Alvarenga |
| 082230028 | Gustavo Sgrignoli Marmo |

## Descrição

Simulador do modelo OSI numa rede com três redes locais, quatro roteadores e
cinco computadores. O programa mostra, passo a passo, o percurso de uma
mensagem entre dois computadores: o encapsulamento camada a camada na origem, a
troca de endereços físicos a cada salto, a decisão de rota em cada roteador e o
desencapsulamento e a remontagem no destino. Cada passo é um evento que
registra quem agiu, em que camada, o que fez e quanto a unidade de dados passou
a ocupar.

A rede e os sete cenários de validação vêm do arquivo `topologia.json`, que é
editável: trocar a rede não exige gerar um novo executável. A simulação roda
inteira em memória, num único processo e de forma determinística, sem tráfego
de rede real. Os cabeçalhos têm tamanho fixo e conteúdo simbólico, e todas as
máscaras de rede são /24.

## Estrutura do repositório

```
simulador-modelo-osi/
|-- SimuladorOSI.exe         Programa pronto para executar (duplo clique)
|-- topologia.json           Rede simulada e casos C1 a C7, editável
|-- app.py                   Ponto de entrada da interface gráfica (alvo do executável)
|-- simulador.py             Motor de eventos e modo textual
|-- camadas.py               As sete camadas
|-- dispositivos.py          Computador e roteador
|-- rede.py                  Topologia, validação e rotas
|-- pdu.py                   Unidade de dados, blocos e quadro
|-- evento.py                Estrutura do evento e linha do registro
|-- constantes.py            Vocabulário de ações
|-- visual.py                Desenho da janela e controles
|-- exemplos/
|   `-- topologia-alternativa.json   Outra rede, para testar a troca de topologia
|-- docs/
|   |-- tutorial_execucao.pdf        Como colocar o programa para funcionar
|   |-- tutorial_uso.pdf             Como operar cada função
|   `-- documentacao_projeto.pdf     Como o simulador funciona internamente
`-- tests/                           Testes automáticos (unittest)
```

O `SimuladorOSI.exe` é versionado junto com o código e gerado a partir de
`app.py` com o comando descrito na seção 9 da
[documentação do projeto](docs/documentacao_projeto.pdf). Depois de qualquer
mudança no código, ele deve ser gerado de novo e copiado para a raiz.

## Arquivos de código

- `app.py`: monta a janela, carrega a topologia, executa o caso escolhido e
  entrega a lista de eventos à interface; é o único módulo que conhece o motor e
  a tela.
- `simulador.py`: fila de eventos, execução dos casos, injeção de falhas,
  métricas de eficiência e modo textual (`python simulador.py --caso C2 --log saida.txt`).
- `camadas.py`: as sete classes de camada, cada uma com `descer()` e `subir()`,
  incluindo a cifra XOR, a segmentação, o roteamento por prefixo e o CRC-32.
- `dispositivos.py`: as pilhas do `Computador` (sete camadas) e do `Roteador`
  (três camadas), que encadeiam as chamadas às camadas.
- `rede.py`: leitura e validação do `topologia.json`, cálculo de menor caminho e
  tabelas de encaminhamento.
- `pdu.py`: estrutura da unidade de dados (`PDU`, `Bloco`) e do `Quadro`, com a
  numeração global de quadros.
- `evento.py`: o `Evento` imutável que descreve cada passo e a formatação da
  linha do registro.
- `constantes.py`: o vocabulário fechado de ações de cada camada.
- `visual.py`: mapa da rede, pilhas, unidade de dados, painéis de endereço,
  registro e controles da janela.

## Requisitos de ambiente

- **Executável:** Windows 10 ou 11, 64 bits. Nenhuma instalação.
- **Código-fonte:** Python 3.11 ou mais recente, com `tkinter` (incluído no
  instalador oficial do Python para Windows). Nenhuma biblioteca externa: só a
  biblioteca padrão.
- **Testes:** `python -m unittest discover -s tests`, sem interface gráfica nem
  dependências.

## Funcionalidades

| O que faz | Onde |
|---|---|
| Encapsulamento e desencapsulamento nas sete camadas | `camadas.py` |
| Cifra XOR na camada 6 e sessão na camada 5 | `camadas.py` |
| Segmentação e remontagem na camada 4 | `camadas.py` |
| Detecção de erro por CRC-32 na camada 2 | `camadas.py` |
| Roteador com apenas três camadas; computador com sete | `dispositivos.py` |
| Troca de endereços físicos e novo quadro a cada salto | `dispositivos.py`, `pdu.py` |
| Encaminhamento por menor custo e recálculo de rota | `rede.py` |
| Leitura e validação da topologia editável | `rede.py` |
| Execução dos sete casos, com falhas de enlace e erro de bit | `simulador.py` |
| Registro de eventos e cálculo de eficiência (η) | `simulador.py`, `evento.py` |
| Modo textual com gravação do registro | `simulador.py` |
| Mapa, pilhas, unidade de dados e endereços na tela | `visual.py` |
| Passo a passo, execução contínua, pausa e três velocidades | `visual.py` |
| Alternância entre os modelos OSI e TCP/IP | `visual.py` |
| Derrubar enlace, injetar erro e salvar o registro | `visual.py`, `app.py` |

## Documentação

- [Tutorial de execução](docs/tutorial_execucao.pdf): abrir o programa e
  confirmar que funciona.
- [Tutorial de uso](docs/tutorial_uso.pdf): operar cada função, provocar falhas
  e conferir o cenário E2.
- [Documentação do projeto](docs/documentacao_projeto.pdf): separação entre as
  camadas, módulos, estrutura de dados, parâmetros e convenções.

## Por onde começar

1. Abra o programa seguindo o **Tutorial de execução**.
2. Reproduza o cenário E2 (caso C2) pelo **Tutorial de uso**, seção 9, e
   confira os quatro quadros e a eficiência de 11,4%.
3. Consulte a **Documentação do projeto** para entender o código, começando
   pela seção 2 (separação entre as camadas).
4. No código, leia na ordem `pdu.py`, `camadas.py`, `dispositivos.py`,
   `rede.py`, `simulador.py`, `evento.py` e, por fim, `visual.py` e `app.py`.
