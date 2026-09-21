# Simulador Visual do Modelo OSI

Simulador didático que mostra, passo a passo, o caminho de uma mensagem entre
dois computadores de redes diferentes: o empilhamento de cabeçalhos na origem,
o tratamento em cada roteador do percurso e o desempilhamento no destino.

> **Disciplina:** COMUNICAÇÃO DE DADOS <br/>
> **Professor(a):** VINÍCIUS S. BORGES <br/>

> **ALUNO:** EMANUEL CARNEIRO DA SILVA - 082230017<br/>
> **ALUNO:** JOSÉ GABRIEL DE MORAIS SOUZA - 082230001<br/>
> **ALUNO:** LUCAS DAIKI HONDA KUNIYOSI - 082230020<br/>

---

## 1. Como executar

### Caminho mais curto (Windows, sem instalar nada)

1. Baixe a versão mais recente do arquivo na seção [*Releases*](https://github.com/Gabriieu/simulador-osi/releases)
   do repositório.
2. Extraia o arquivo.
2. Dê um duplo clique no executável.

Não é preciso ter Python instalado. Se o Windows exibir o aviso *"O Windows
protegeu o computador"*, clique em **Mais informações → Executar assim mesmo**:
o aviso aparece porque o arquivo não tem assinatura digital paga, não porque o
programa seja perigoso.

### Caminho com Python (qualquer sistema)

```bash
python main.py
```

No Windows também funciona o duplo clique em `SimuladorOSI.bat`.

O programa **não usa nenhuma biblioteca externa**: tudo o que ele precisa vem na
instalação padrão do Python 3.10 ou superior. Não há `pip install` a fazer, não
há `requirements.txt` com dependências de terceiros.

Instruções detalhadas, incluindo a geração do executável e a solução dos erros
mais comuns, estão em [`docs/tutorial_execucao.md`](docs/tutorial_execucao.md).

---

## 2. O que o programa faz

A partir de uma rede com cinco computadores e quatro roteadores, o simulador:

- desenha a topologia e destaca o enlace que está sendo usado a cada instante;
- desenha as sete camadas do computador de origem, as três camadas de cada
  roteador e as sete camadas do destino, acendendo a camada ativa;
- desenha a unidade de dados em blocos, mostrando cada cabeçalho entrar e sair;
- exibe os endereços lógicos (que não mudam) ao lado dos endereços físicos (que
  mudam a cada salto);
- escreve um registro textual numerado, uma linha por ação de camada;
- calcula a eficiência da comunicação e a compara com a de uma entrega local;
- executa sete casos de demonstração, entre eles queda de enlace, destino
  inalcançável, erro de transmissão e mensagem longa segmentada.

Você pode avançar passo a passo, deixar rodar sozinho em três velocidades,
reiniciar, salvar o registro em arquivo e trocar a rede inteira substituindo o
arquivo `topologia.json`.

> 📸 **Captura de tela 1 — janela principal.**
> ![Tela Principal](docs/images/tela-principal.png)

---

## 3. Estrutura de pastas

```
simulador-osi/
├── main.py                     ponto de entrada: é este arquivo que se executa
├── SimuladorOSI.bat            atalho de duplo clique para Windows
├── build_exe.py                gera o executável com PyInstaller
├── topologia.json              a rede simulada, em texto editável
├── pytest.ini                  configuração da bateria de testes
├── .gitignore
├── README.md                   este arquivo
│
├── simulador/                  o programa propriamente dito
│   ├── __init__.py             mapa do pacote e versão
│   ├── ambiente.py             onde encontrar os arquivos, no código e no .exe
│   ├── pdu.py                  a unidade de dados e as regras de acesso a ela
│   ├── rede.py                 topologia, rotas e tabelas de encaminhamento
│   ├── camadas.py              as sete camadas e o que cada uma faz
│   ├── dispositivos.py         computadores e roteadores, montando as pilhas
│   ├── cenarios.py             os sete casos de demonstração
│   ├── motor.py                executa a simulação e produz a lista de eventos
│   ├── registro.py             formata o registro textual e a eficiência
│   └── visual.py               a interface gráfica (tkinter)
│
├── tests/                      bateria automatizada (91 testes)
│   ├── conftest.py
│   ├── test_pdu.py
│   ├── test_rede.py
│   ├── test_camadas.py
│   ├── test_cenarios.py
│   └── test_registro.py
│
├── ferramentas/
│   ├── rodar_testes.py         executa os testes sem precisar instalar pytest
│   └── conferir_interface.py   exercita a interface sem servidor gráfico
│
└── docs/
    ├── documentacao_projeto.md documentação técnica
    ├── tutorial_execucao.md    como instalar e executar
    ├── tutorial_uso.md         como usar a interface
    ├── entrega_github.md       fork, commits e pull request
    ├── exemplo_registro_C2.txt registro completo do caso central
    └── exemplo_registro_C7.txt registro completo da mensagem longa
```

---

## 4. Arquivos de código, um a um

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Abre a interface e garante que a janela não feche sozinha diante de um erro. |
| `simulador/ambiente.py` | Descobre a pasta do programa, funcionando tanto em `.py` quanto dentro do `.exe`. |
| `simulador/pdu.py` | Unidade de dados imutável, tamanhos dos cabeçalhos, verificação de erro e o guarda que impede uma camada de ler o cabeçalho de outra. |
| `simulador/rede.py` | Lê e valida `topologia.json`, calcula rotas de menor custo, monta as tabelas de encaminhamento e simula queda de enlaces. |
| `simulador/camadas.py` | As sete camadas, cada uma com a sua descida e a sua subida. |
| `simulador/dispositivos.py` | Monta a pilha de sete camadas nos computadores e de três nos roteadores. |
| `simulador/cenarios.py` | Declara os sete casos obrigatórios e os valores que cada um deve produzir. |
| `simulador/motor.py` | Fila de processamento, aplicação de falhas e geração da lista de eventos. |
| `simulador/registro.py` | Formata cada linha do registro e calcula o quadro de eficiência. |
| `simulador/visual.py` | Toda a interface: mapa, pilhas, unidade de dados, controles e registro. |


---

## 5. Funcionalidades e onde cada uma está

| Funcionalidade pedida no enunciado | Onde está implementada |
|---|---|
| Topologia com 5 computadores e 4 roteadores | `topologia.json`, `simulador/rede.py` |
| Pilha de 7 camadas no computador, 3 no roteador | `simulador/dispositivos.py`, `simulador/camadas.py` |
| Empilhamento e desempilhamento de cabeçalhos | `simulador/pdu.py`, `simulador/camadas.py` |
| Quadro reconstruído a cada enlace | `Enlace.descer` em `simulador/camadas.py` |
| Endereços lógicos fixos, físicos variáveis | `Rede.descer` e `Enlace.descer` em `simulador/camadas.py` |
| Tabelas de encaminhamento e menor custo | `Topologia.tabela_encaminhamento` em `simulador/rede.py` |
| Registro textual numerado | `simulador/registro.py` |
| Cálculo e comparação de eficiência | `ResumoComunicacao` em `simulador/registro.py`, `comparar_eficiencias` em `simulador/motor.py` |
| Sete casos de demonstração | `simulador/cenarios.py` |
| Execução passo a passo, automática e reinício | `simulador/visual.py` |
| Alternância entre os modelos OSI e TCP/IP | `simulador/visual.py` |
| Salvar o registro em arquivo | `salvar` em `simulador/registro.py` |

---

## 6. Requisitos de ambiente

| Item | Versão | Observação |
|---|---|---|
| Python | 3.10 ou superior | Só para executar a partir do código-fonte. |
| tkinter | incluso no Python | No Windows e no macOS vem junto; no Linux pode exigir `sudo apt install python3-tk`. |
| Bibliotecas externas | nenhuma | Não há `import` de pacote de terceiros no programa. |
| pytest | 7 ou superior | Apenas para rodar os testes. Existe uma alternativa sem instalação, descrita abaixo. |
| PyInstaller | 6 ou superior | Apenas para gerar o `.exe`. |

---

## 7. Testes

Com o pytest instalado:

```bash
python -m pip install pytest
python -m pytest
```

Sem instalar nada:

```bash
python ferramentas/rodar_testes.py
```

---

## 8. Documentação complementar

- [`docs/documentacao_projeto.md`](docs/documentacao_projeto.md) — decisões de
  arquitetura, convenções de simulação, formato do registro e limitações.
- [`docs/tutorial_execucao.md`](docs/tutorial_execucao.md) — instalação,
  execução, geração do executável e solução de problemas.
- [`docs/tutorial_uso.md`](docs/tutorial_uso.md) — passeio pela interface e
  roteiro dos sete casos de demonstração.
- `docs/exemplo_registro_C2.txt` e `docs/exemplo_registro_C7.txt` — saídas
  completas, geradas pelo próprio programa.

---
