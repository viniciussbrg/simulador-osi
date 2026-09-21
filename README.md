# 🌐 Simulador do Modelo OSI

> **Projeto 1** da disciplina de Comunicação de Dados (Semestre 2026/2)
> Ministrada pelo Prof. Vinícius S. Borges

O simulador reproduz o percurso completo de uma mensagem entre dois computadores em uma topologia contendo três redes locais, quatro roteadores e cinco computadores. Ele exibe, passo a passo, o encapsulamento na origem, a decisão de rota em cada roteador, a substituição do par de endereços físicos a cada enlace e o desencapsulamento no destino.

## 🚀 Por onde começar

1. **Abra o programa** (veja as instruções de execução abaixo).

2. **Siga o [Tutorial de Execução](./docs/tutorial_execucao.pdf)** para entender a interface.

3. **Reproduza o cenário E2** guiando-se pelo [Tutorial de Uso](./docs/tutorial_uso.pdf) e confira a eficiência de 11,4%.

4. **Leia a [Documentação Técnica](./docs/documentacao_projeto.pdf)** para entender a arquitetura, a separação entre as camadas e as convenções matemáticas do simulador.

## 💻 Como executar

O simulador foi desenhado para ser acessível tanto para usuários finais quanto para desenvolvedores.

### Opção A: Executável (Windows)

A maneira mais rápida. Não requer instalação de Python ou preparação de ambiente.

1. Dê dois cliques em `SimuladorOSI.exe`.

2. O programa abre em janela única com o cenário **E2** pré-carregado.

3. Clique em **Simular** e depois em **Executar**.

### Opção B: A partir do código-fonte

Requer **Python 3.10 ou superior**. Não há dependências externas (o simulador usa apenas a biblioteca padrão do Python).

Para abrir a interface gráfica:

```bash
python main.py
```

Para executar os sete cenários de teste diretamente no terminal:

```bash
python main.py --texto
```

*Dica para Windows:* Dê dois cliques no arquivo `executar_codigo_fonte.bat`. Ele faz o mesmo processo e avisa caso o Python não esteja instalado na máquina.

## ⚙️ Arquitetura e Funcionamento

Cada uma das sete camadas do modelo OSI é representada por uma classe separada com operações de sentidos opostos (`desce` e `sobe`). **Nenhuma camada alcança outra que não lhe seja adjacente.**

Os roteadores implementam apenas as três primeiras camadas — eles não têm como ler uma porta (Camada 4) ou o nome de um processo. A interface gráfica opera de forma desacoplada: ela desconhece a lógica das camadas e apenas renderiza a lista de eventos produzida pelo motor da simulação.

### 📋 Funcionalidades Implementadas

| **Funcionalidade** | **Onde está implementado** | 
| --- | --- |
| **Encapsulamento e desencapsulamento** nas sete camadas | `simulador/camadas.py` | 
| **Segmentação** (L4) e remontagem em ordem no destino | `simulador/camadas.py` (CamadaTransporte) | 
| **Cifra** (L6), desfeita apenas na L6 do destino | `simulador/camadas.py` (CamadaApresentacao) | 
| **Verificação de erro** do quadro por CRC-32 | `simulador/pdu.py`, `camadas.py` (CamadaEnlace) | 
| **Encaminhamento** por menor custo (Dijkstra) e tabelas | `simulador/rede.py` | 
| **Entrega direta** sem roteador na mesma rede | `simulador/camadas.py` (CamadaRede._decidir) | 
| **Reconstrução do quadro** a cada salto | `simulador/dispositivos.py` (Roteador.encaminhar) | 
| **Queda de enlace, erro de bit e destino inalcançável** | `simulador/motor.py` (acionados pela interface) | 
| **Demultiplexação** de fluxos concorrentes pelas portas | `simulador/camadas.py` (CamadaTransporte.sobe) | 
| **Registro de eventos** e gravação em arquivo | `simulador/eventos.py` | 
| **Cálculo da eficiência e sobrecarga** | `simulador/motor.py` (ResultadoSimulacao) | 
| **Mapa, pilhas, PDU e endereços** | `simulador/visual.py` | 
| **Alternância OSI / TCP/IP** na interface | `simulador/visual.py` (_linhas_da_pilha) | 
| **Troca da rede simulada** sem recompilar | `simulador/rede.py`, `simulador/config.py` | 
| **Exportação do resultado** em HTML | `simulador/relatorio.py` | 

## 📊 Cenários de Validação

Os sete casos exigidos no enunciado estão pré-configurados na lista **Cenário** da tela principal. Os valores abaixo são reproduzidos a cada execução e servem de gabarito.

| **Cenário** | **Descrição** | **Caminho** | **Quadros** | **Dados** | **Transmitido** | **Eficiência** | 
| :---: | --- | --- | :---: | :---: | :---: | :---: |
| **E1** | Entrega direta | H1 - H2 | 1 | 42 B | 92 B | 45,7 % | 
| **E2** | Entrega indireta | H1 - R1 - R4 - R3 - H4 | 4 | 42 B | 368 B | 11,4 % | 
| **E3** | Demultiplexação | *Dois fluxos até H4* | 8 | 84 B | 736 B | 11,4 % | 
| **E4** | Falha de enlace | H1 - R1 - R2 - R3 - H4 | 4 | 42 B | 368 B | 11,4 % | 
| **E5** | Destino inalcançável | H1 - R1 *(descarte)* | 1 | 0 B | 92 B | 0 % | 
| **E6** | Erro de transmissão | H1 - R1 - R4 - R3 *(descarte)* | 3 | 0 B | 276 B | 0 % | 
| **E7** | Mensagem longa | H1 - R1 - R4 - R3 - H4 | 12 | 100 B | 968 B | 10,3 % | 

## 🧪 Testes Automatizados e Logs

São **41 testes automatizados** que cobrem os endereços da topologia, custos de rota, tamanhos de cabeçalho, a tabela de eficiência acima e as cinco restrições de projeto do enunciado.

Para rodar a suíte de testes:

```bash
python -m unittest discover -s tests -v
```

A pasta `registros/` contém os logs completos (`E1.txt` a `E7.txt`) no formato exigido pela Seção 5.1 do enunciado. Você pode regerar esses logs na interface pelo botão **Salvar registro** ou executando o modo texto no terminal (`--texto`).

## 📂 Estrutura do Repositório e Código

```text
simulador-osi/
├── SimuladorOSI.exe              # Executável compilado
├── topologia.json                # Configuração da rede (editável)
├── main.py                       # Ponto de entrada do simulador
├── executar_codigo_fonte.bat     # Script de inicialização facilitada
├── requirements.txt              # Vazio (sem dependências externas)
├── simulador/                    # Núcleo da aplicação
├── tests/                        # Suíte de testes unitários
├── registros/                    # Logs dos cenários E1 a E7
└── docs/                         # Manuais e especificações do projeto
```

### Mapa de Arquivos (`simulador/`)

| **Arquivo** | **Responsabilidade** | 
| --- | --- |
| `config.py` | Convenções: tamanhos de cabeçalho, limiares e velocidades. | 
| `pdu.py` | Unidade de Dados de Protocolo (PDU) e construtores de cabeçalho. | 
| `camadas.py` | As 7 classes de camada, isoladas com métodos `desce()` e `sobe()`. | 
| `dispositivos.py` | `Computador` (pilha de 7 camadas) e `Roteador` (pilha de 3 camadas). | 
| `rede.py` | Topologia, enlaces e tabelas de encaminhamento por menor custo. | 
| `eventos.py` | Modelagem de eventos; atua como fronteira entre o núcleo e a interface. | 
| `motor.py` | Relógio interno e laço de simulação (avaliação salto a salto). | 
| `cenarios.py` | Definição dos sete casos de validação (E1 a E7). | 
| `visual.py` | Interface gráfica construída em `tkinter`. | 
| `relatorio.py` | Geração e exportação dos resultados em formato HTML. | 

## 👥 Autoria

**Grupo 8**

* Arthur Benevides - `082230016`
* Fernando Montanher - `082230010`
* Guilherme Costa - `081240041`
* Juan Haddad - `081240043`
* Murillo Ando - `082240042`
