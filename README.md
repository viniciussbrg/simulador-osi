# **Simulador OSI**

## Autoria, orientação e escopo

Este projeto foi desenvolvido como parte das atividades da disciplina de Comunicação de Dados, ministrada pelo Prof. Vinícius Borges no 7º semestre do curso de Engenharia da Computação da Faculdade Engenheiro Salvador Arena.

Autoria:

| **Integrantes** | **RA** |
|---|---|
| Lucas Junqueira Gonçalves | 082230029 |
| Murilo Umbelino Oliveira dos Santos | 082230013 |
| Victor Mendes de Andrade Ferreira | 082230015 |
| Guilherme Alves Barbosa | 082220014 |

O Simulador OSI é um programa desenvolvido em Python para demonstrar a comunicação entre computadores e roteadores em uma rede. A interface permite acompanhar o percurso de uma mensagem, seu encapsulamento na origem, o encaminhamento pelos roteadores e o desencapsulamento no destino. Cada computador possui as sete camadas do modelo OSI, enquanto os roteadores operam com as camadas física, enlace e rede.

O programa permite executar a simulação passo a passo ou de forma contínua, visualizar os endereços utilizados e acompanhar a segmentação e a remontagem das mensagens. Também apresenta cenários de falha de enlace, destino inalcançável e erro de transmissão. Os acontecimentos ficam registrados em um log, e os resultados mostram o volume de dados transmitidos e a eficiência da comunicação. A rede simulada é definida em um arquivo JSON externo, permitindo alterar a topologia sem modificar o código.

## Execução do programa

Baixe o zip do projeto no GitHub e extraia-o completamente. Abra a nova pasta gerada após a extração e execute o arquivo **SimuladorOSI.exe** com dois cliques

Mantenha **topologia.json** na mesma pasta 

É necessário Windows 10/11 e um navegador com JavaScript

Não é necessário instalar Python ou acessar a internet durante o uso

Na área superior direita da tela, em cenário escolha o cenário desejado para observação, como por exemplo **E2 / C2 - Entrega indireta** 

Após isso, na parte central da tela clique em **Preparar** e escolha uma das opções para cada necessidade:

- **Ir ao resultado**: Verificar o resultado final imediatamente

- **Executar**: Verificar de forma contínua o progresso de transmissão da mensagem pela rede e em que camada está sendo executada cada etapa

- **Próximo passo**: Exibe cada um dos passos executados porém são demonstrados pausadamente e a cada clique no botão

No final da tela confira os resultados: 42 B úteis, 368 B transmitidos, quatro quadros e eficiência global de 11,41%. 

Na área superior esquerda da tela use o botão **Encerrar** para finalizar o programa pois apenas fechar a aba do navegador mantém o programa ativo.

## 🌳 Estrutura do repositório

* **SimuladorOSI/** — pasta principal do projeto

  * `SimuladorOSI.exe`
  * `topologia.json`
  * `main.py`
  * `README.md`
  * **osi/** — módulos Python da simulação e do servidor local

    * `__init__.py`
    * `camadas.py`
    * `pdu.py`
    * `dispositivos.py`
    * `rede.py`
    * `simulador.py`
    * `observacao.py`
    * `visual.py`
  * **interface/** — arquivos da interface exibida no navegador

    * `index.html`
    * `styles.css`
    * `app.js`
  * **docs/** — documentação técnica e tutoriais

    * `documentacao_projeto.pdf`
    * `tutorial_execucao.pdf`
    * `tutorial_uso.pdf`

## 📁 Arquivos e responsabilidades

| Arquivo                | Responsabilidade                                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `SimuladorOSI.exe`     | Executável Windows com o interpretador Python e os arquivos da interface incorporados.                                                     |
| `topologia.json`       | Define dispositivos, interfaces, endereços, enlaces, custos e cenários. Pode ser substituído sem gerar outro executável.                   |
| `main.py`              | Localiza a topologia, inicia o servidor local e abre o navegador.                                                                          |
| `osi/__init__.py`      | Identifica a pasta `osi` como um pacote Python.                                                                                            |
| `osi/camadas.py`       | Implementa as sete camadas, incluindo codificação, cifra, sessões, segmentação, remontagem, encaminhamento e operações de enlace e física. |
| `osi/pdu.py`           | Define as estruturas de segmento, pacote, quadro e bits, sua serialização e a verificação de integridade dos quadros.                      |
| `osi/dispositivos.py`  | Define computadores, roteadores e interfaces de rede, criando as camadas de cada dispositivo.                                              |
| `osi/rede.py`          | Carrega e valida a topologia, calcula rotas, fornece tabelas de encaminhamento e representa a transmissão pelos enlaces.                   |
| `osi/simulador.py`     | Coordena os cenários e as chamadas das camadas, registra eventos e reúne as métricas da simulação.                                         |
| `osi/observacao.py`    | Analisa informações dos eventos e contabiliza dados e controle por quadro para os resultados.                                              |
| `osi/visual.py`        | Implementa o servidor HTTP local, recebe comandos da interface e devolve configurações e resultados.                                       |
| `interface/index.html` | Define os campos, botões e painéis da página.                                                                                              |
| `interface/styles.css` | Define a aparência e a organização visual da interface.                                                                                    |
| `interface/app.js`     | Envia configurações ao servidor, reproduz os eventos, desenha a rede e as pilhas e permite exportar o log.                                 |

## Requisitos de ambiente

### Execução pelo executável

* Windows 10 ou 11, de 64 bits.
* Navegador atualizado com JavaScript habilitado.
* Arquivo `topologia.json` na mesma pasta de `SimuladorOSI.exe`.
* Não é necessário instalar Python ou bibliotecas adicionais.
* Não é necessária conexão com a internet durante o uso. A comunicação entre a interface e o servidor ocorre no próprio computador.

## Funcionalidades

| Funcionalidade                                                                                                                                                | Arquivo(s) principal(is)                                            |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Carregamento e validação de uma rede definida em JSON, permitindo substituir a topologia sem modificar o código.                                              | `osi/rede.py` e `osi/visual.py`                                     |
| Representação das camadas dos computadores e roteadores, com encapsulamento e desencapsulamento das unidades de dados.                                        | `osi/dispositivos.py`, `osi/camadas.py` e `osi/pdu.py`              |
| Codificação UTF-8, cifra didática XOR e controle de abertura, manutenção e encerramento das sessões.                                                          | `osi/camadas.py`                                                    |
| Segmentação, remontagem das mensagens e separação dos fluxos pelos endereços IP e portas.                                                                     | `osi/camadas.py`                                                    |
| Entrega direta ou por roteadores, seleção de rotas de menor custo e criação de novos quadros com os MACs de cada salto.                                       | `osi/rede.py`, `osi/camadas.py` e `osi/simulador.py`                |
| Execução dos cenários E1 a E7, incluindo falha de enlace, destino inalcançável e erro de transmissão detectado por CRC32.                                     | `osi/simulador.py`, `osi/rede.py`, `osi/camadas.py` e `osi/pdu.py`  |
| Visualização do mapa, percurso da mensagem, camadas ativas, unidades de dados e endereços utilizados.                                                         | `interface/app.js`, `interface/index.html` e `interface/styles.css` |
| Reprodução passo a passo ou contínua, pausa, ajuste de velocidade e alternância visual entre OSI e TCP/IP.                                                    | `interface/app.js`                                                  |
| Geração, exibição e exportação do registro de eventos para arquivo de texto.                                                                                  | `osi/simulador.py` e `interface/app.js`                             |
| Apresentação das métricas de transmissão, eficiência e sobrecarga, com comparação de referência entre E1 e E2 para uma mensagem de 42 bytes na rede original. | `osi/simulador.py`, `osi/observacao.py` e `interface/app.js`        |


## Tutoriais e Documentação do Projeto

[Tutorial de Execução](https://github.com/vmafdev/simulador-osi/blob/main/docs/Tutorial%20de%20Execução%20-%20SimuladorOSI.pdf)

[Tutorial de Uso](https://github.com/vmafdev/simulador-osi/blob/main/docs/Tutorial%20de%20Uso%20-%20SimuladorOSI.pdf)

[Documentação]()

## Primeiros passos

1. Abra o programa com dois cliques em SimuladorOSI.exe e siga o arquivo de tutorial de execução para validar o programa
2. Reproduza o cenário E2 pelo tutorial de uso e aprenda a utilizar as demais funcionalidades presentes
3. Consulte a documentação técnica para entender o código e a implementação do projeto
