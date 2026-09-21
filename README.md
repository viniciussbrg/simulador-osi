# Simulador do Modelo OSI

Projeto prático da disciplina de Comunicação de Dados.

- Setimo semestre
- Professor: Vinicius Borges

## Integrantes
- Acsa Santos Silva - 082230033
- Geni Aparecida de Carvalho - 082230035
- Patrick Nathan Gomes - 082230021
- Yuri Pilatis de Andreade - 082230038

## Como executar

Clique duas vezes em `SimuladorOSI.exe`. O executável deve ser gerado pelo arquivo `build_exe.bat` e colocado na raiz da entrega. Não é necessário instalar Python na máquina em que o executável final será utilizado.

Para executar pelo código-fonte durante o desenvolvimento:

```text
cd src
python main.py
```

## Descrição

O projeto implementa um simulador didático do modelo OSI em Python. A rede contém computadores e roteadores, e a interface permite acompanhar, passo a passo, o encapsulamento e o desencapsulamento das unidades de dados, o roteamento, a troca dos endereços físicos em cada salto, a permanência dos endereços lógicos de ponta a ponta, a segmentação, a remontagem e situações de falha.

A simulação possui sete cenários de validação (C1 a C7), visualização das pilhas OSI/TCP-IP, desenho da PDU, registro de eventos, controles de execução e cálculo de eficiência e sobrecarga.

## Estrutura do repositório

```text
simulador_osi/
|-- SimuladorOSI.exe          Programa final para Windows (gerado para a entrega)
|-- build_exe.bat             Gera o executável com PyInstaller
|-- README.md                 Ponto de entrada da documentação
|-- src/
|   |-- main.py               Inicialização da interface
|   |-- visual.py             Interface gráfica e reprodução dos eventos
|   |-- simulador.py          Coordenação dos cenários e métricas
|   |-- eventos.py            Estrutura e armazenamento dos eventos
|   |-- pdu.py                Estrutura da PDU e tamanhos de cabeçalhos
|   |-- camadas.py            Comportamento das camadas e fluxo da comunicação
|   |-- dispositivos.py       Computadores e roteadores
|   |-- rede.py               Topologia, enlaces e cálculo de rotas
|   `-- topologia.json        Configuração externa da rede
`-- docs/
    |-- tutorial_execucao.pdf
    |-- tutorial_uso.pdf
    `-- documentacao_projeto.pdf
```

## Arquivos de código

- `src/main.py`: cria a janela principal e inicia a interface.
- `src/visual.py`: apresenta mapa, pilhas, PDU, endereçamento, log e controles.
- `src/simulador.py`: executa C1-C7, mantém buffers de remontagem e calcula eficiência.
- `src/eventos.py`: define o formato dos eventos e a numeração dos passos.
- `src/pdu.py`: representa os dados transportados, cabeçalhos, portas, IPs, MACs e quadro.
- `src/camadas.py`: realiza geração, cifra/decifra, sessão, segmentação, roteamento, enquadramento, transmissão e recepção.
- `src/dispositivos.py`: representa hosts e roteadores; o roteador não possui lógica de L4-L7.
- `src/rede.py`: carrega a topologia JSON, mantém enlaces e encontra caminhos de menor custo.
- `src/topologia.json`: descreve dispositivos, interfaces, IPs, MACs, vizinhos, enlaces e custos.

## Requisitos de ambiente

O código-fonte utiliza Python 3 e somente bibliotecas da distribuição padrão (`tkinter`, `json`, `heapq`, `dataclasses`, `copy`, `itertools` e módulos auxiliares). Para gerar o executável é utilizado o PyInstaller, instalado automaticamente pelo `build_exe.bat`.

## Funcionalidades

| Funcionalidade | Implementação principal |
|---|---|
| Encapsulamento e desencapsulamento | `src/camadas.py`, `src/pdu.py` |
| Cifra e decifra didática da camada 6 | `src/camadas.py` |
| Sessão | `src/camadas.py` |
| Portas, segmentação e remontagem | `src/camadas.py`, `src/simulador.py` |
| Endereçamento lógico e roteamento | `src/rede.py`, `src/camadas.py` |
| Quadros e endereçamento físico | `src/camadas.py`, `src/pdu.py` |
| Erro de transmissão e descarte | `src/camadas.py` |
| Registro estruturado de eventos | `src/eventos.py` |
| Cenários C1-C7 | `src/simulador.py` |
| Interface V1-V7 | `src/visual.py` |
| Eficiência e sobrecarga | `src/simulador.py`, `src/visual.py` |
| Topologia externa | `src/topologia.json` |

## Documentação

- `docs/tutorial_execucao.pdf` - como abrir o programa e confirmar o funcionamento.
- `docs/tutorial_uso.pdf` - como utilizar os recursos e reproduzir os cenários.
- `docs/documentacao_projeto.pdf` - referência técnica da implementação.

## Por onde começar

1. Gere ou localize `SimuladorOSI.exe`.
2. Leia `docs/tutorial_execucao.pdf` e abra o programa.
3. Leia `docs/tutorial_uso.pdf` e reproduza C2 e os demais cenários.
4. Consulte `docs/documentacao_projeto.pdf` para compreender ou modificar o código.
