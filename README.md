# Simulador do Modelo OSI

## Como Executar
Clique duas vezes no arquivo `SimuladorOSI.exe`, na raiz do repositório. Não é necessário instalar o Python nem nenhuma biblioteca.

O arquivo `topologia.json` deve ficar na mesma pasta do executável. Se ele não for encontrado, o programa usa uma cópia embutida no próprio executável.

---

**Instituição:** Faculdade Engenheiro Salvador Arena (FESA)  
**Disciplina:** Comunicação de Dados  
**Professor:** Prof. Vinícius S. Borges  
**Semestre:** 7º Semestre  

**Autoria (Equipe):**
* Guilherme de Oliveira Mattos - RA: 082230009
* Luigi Guilherme Pereira Silva - RA: 082230025
* Paulo Henrique de Carvalho Santos - RA: 082230006
* Pedro Henrique de Holanda Carvalho - RA: 082230005
* Tayson Moises Costa do Carmo - RA: 082230008

## Descrição do Projeto
Simulador visual do modelo OSI de sete camadas em uma rede com três redes locais, quatro roteadores (R1 a R4) e cinco computadores (H1 a H5). O programa mostra passo a passo o percurso de uma mensagem: o encapsulamento na origem, a decisão de rota na camada 3 de cada roteador, a troca do quadro e dos endereços físicos a cada salto e o desencapsulamento no destino.

Os sete casos do enunciado (C1 a C7) podem ser escolhidos na interface, incluindo queda de enlace, destino inalcançável e erro de bit. Ao final de cada execução o programa mostra os octetos transmitidos e a eficiência (η), e compara a eficiência do caso C1 (um enlace) com a do caso C2 (quatro enlaces).

## Requisitos de Ambiente
* Para usar o executável: Windows, sem nenhuma instalação.
* Para rodar pelo código-fonte: Python 3 (testado com Python 3.14), executando `python main.py`.
* Bibliotecas: apenas as da biblioteca padrão do Python (`tkinter`, `json`, `os`, `sys`, `ipaddress`, `zlib`). Nenhuma biblioteca externa.
* O executável foi gerado com **PyInstaller**, em arquivo único e com o `topologia.json` embutido como cópia de reserva:

      pyinstaller --onefile --windowed --name SimuladorOSI --add-data "topologia.json;." main.py

## Estrutura do Repositório

    simulador-osi/
    |-- SimuladorOSI.exe        Programa pronto para executar (duplo clique)
    |-- topologia.json          Rede simulada: redes, endereços, interfaces, custos e posições no mapa
    |-- main.py                 Ponto de entrada do código-fonte
    |-- README.md               Este arquivo
    |-- registros/              Registros de eventos dos sete casos
    |   `-- registro_C1.txt a registro_C7.txt
    |-- simulador/              Código-fonte do simulador
    |   |-- pdu.py
    |   |-- camadas.py
    |   |-- dispositivos.py
    |   |-- rede.py
    |   |-- motor.py
    |   `-- visual.py
    `-- docs/                   Especificação, guia de documentação, tutoriais e documentação técnica
        |-- especificacao.pdf
        |-- guia_de_documentacao.pdf
        |-- tutorial_execucao.pdf
        |-- tutorial_uso.pdf
        `-- documentacao_projeto.pdf

## Arquivos de Código
* `main.py`: cria o motor e a interface e inicia o programa. Se houver erro ao iniciar, mostra uma janela com a mensagem em vez de fechar.
* `simulador/pdu.py`: unidades de dados (Mensagem, Segmento, Pacote e Quadro) com o tamanho de cada cabeçalho. O Quadro calcula a verificação de erro (CRC32).
* `simulador/camadas.py`: as sete classes de camada, cada uma com os métodos `descer` e `subir`. Inclui a cifragem (camada 6), o identificador de sessão (camada 5), a segmentação e remontagem (camada 4), o encaminhamento (camada 3), o enquadramento e a verificação de erro (camada 2) e a transmissão em bits (camada 1).
* `simulador/dispositivos.py`: Computador (camadas 1 a 7) e Roteador (camadas 1 a 3, com uma interface e um endereço físico para cada enlace).
* `simulador/rede.py`: leitura do `topologia.json` ao lado do executável (ou da cópia embutida) e cálculo das tabelas de encaminhamento pelo caminho de menor custo.
* `simulador/motor.py`: registro de eventos, contadores de quadros e sessões, execução dos casos C1 a C7 e cálculo da eficiência.
* `simulador/visual.py`: interface gráfica em Tkinter. Apenas lê a lista de eventos gerada pelo motor.

## Funcionalidades
| O que faz | Onde está implementado |
| :--- | :--- |
| Leitura da topologia a partir de arquivo externo | `simulador/rede.py` |
| Tabelas de encaminhamento pelo menor custo (desempate pelo menor nome de roteador) | `simulador/rede.py` |
| Pilha de 7 camadas nos computadores e 3 camadas nos roteadores | `simulador/dispositivos.py` |
| Encapsulamento e desencapsulamento com os tamanhos de cabeçalho fixos | `simulador/camadas.py` e `simulador/pdu.py` |
| Cifragem na camada 6 da origem e decifragem só na camada 6 do destino | `simulador/camadas.py` |
| Identificador de sessão (S-0001, S-0002...) | `simulador/camadas.py` e `simulador/motor.py` |
| Segmentação em até 40 octetos e remontagem em ordem | `simulador/camadas.py` |
| Quadro novo e numerado a cada salto (Q1, Q2...) | `simulador/camadas.py` |
| Verificação de erro (CRC) e descarte do quadro com erro de bit | `simulador/camadas.py` e `simulador/pdu.py` |
| Queda de enlace com recálculo das rotas (caso C4) | `simulador/motor.py` e `simulador/rede.py` |
| Registro de eventos, quadros transmitidos e eficiência | `simulador/motor.py` |
| Mapa, pilhas, unidade de dados, endereços, controles e registro na tela | `simulador/visual.py` |
| Alternância entre a pilha OSI e a pilha TCP/IP | `simulador/visual.py` |
| Salvar o registro completo em arquivo `.txt` | `simulador/visual.py` |

## Resultados de Referência
Valores produzidos pelo simulador, iguais ao quadro resumo da especificação:

| Caso | Quadros | Octetos transmitidos | Eficiência |
| :--- | :---: | :---: | :---: |
| C1 Entrega direta | 1 | 92 | 45,7% |
| C2 Entrega indireta | 4 | 368 | 11,4% |
| C3 Demultiplexação | 8 | 736 | 11,4% |
| C4 Falha de enlace | 4 | 368 | 11,4% |
| C5 Destino inalcançável | 1 | 92 | 0 |
| C6 Erro de transmissão | 3 | 276 | 0 |
| C7 Mensagem longa | 12 | 968 | 10,3% |

## Documentação
* [Tutorial de Execução](./docs/tutorial_execucao.pdf)
* [Tutorial de Uso](./docs/tutorial_uso.pdf)
* [Documentação Técnica](./docs/documentacao_projeto.pdf)
* [Especificação do projeto](./docs/especificacao.pdf)

## Por onde começar
1. Abra o `SimuladorOSI.exe` seguindo o **Tutorial de Execução**.
2. Escolha o caso **C2. Caso Central (H1->H4)**, clique em **Executar Cenário** e confira os quatro quadros e a eficiência de 11,4% com o **Tutorial de Uso**.
3. Consulte a **Documentação Técnica** para entender a separação entre as camadas e as convenções de simulação.
