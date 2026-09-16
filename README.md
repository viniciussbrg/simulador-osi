**# Simulador OSI**

## Autoria, orientação e escopo

O projeto descrito abaixo foi desenvolvido para a disciplina de Comunicação de Dados ministrada pelo professor Vinícius Borges durante o 7º semestre de Engenharia da Computação da Faculdade Engenheiro Salvador Arena

Grupo:

| **Integrantes** | **RA** |
|---|---|
| Lucas Junqueira | 082230029 |
| Murilo Umbelino | 082230013 |
| Victor Mendes | 082230015 |
| Guilherme Alves | 082220014 |

O Simulador OSI é um programa desenvolvido em Python para demonstrar a comunicação entre computadores e roteadores em uma rede. A interface permite acompanhar o percurso de uma mensagem, seu encapsulamento na origem, o encaminhamento pelos roteadores e o desencapsulamento no destino. Cada computador possui as sete camadas do modelo OSI, enquanto os roteadores operam com as camadas física, enlace e rede.

O programa permite executar a simulação passo a passo ou de forma contínua, visualizar os endereços utilizados e acompanhar a segmentação e a remontagem das mensagens. Também apresenta cenários de falha de enlace, destino inalcançável e erro de transmissão. Os acontecimentos ficam registrados em um log, e os resultados mostram o volume de dados transmitidos e a eficiência da comunicação. A rede simulada é definida em um arquivo JSON externo, permitindo alterar a topologia sem modificar o código.

## Execução do programa

Baixe o zip do projeto no GitHub e extraia-o completamente. Abra a nova pasta e execute o arquivo **SimuladorOSI.exe** com dois cliques

Mantenha **topologia.json** na mesma pasta 

É necessário Windows 10/11 e um navegador com JavaScript

Não é necessário instalar Python ou acessar a internet durante o uso

Escolha **E2 / C2 - Entrega indireta**, clique em **Preparar** e escolha uma das opções para cada necessidade:

**Ir ao resultado**: Verificar o resultado final imediatamente
**Executar**: Verificar de forma contínua o progresso de transmissão da mensagem pela rede e em que camada está sendo executada cada etapa
**Próximo passo**: Exibe cada um dos passos executados porém são demonstrados pausadamente e a cada clique no botão

No final: Confira 42 B úteis, 368 B transmitidos, quatro quadros e eficiência global de 11,41%. 

Use **Encerrar** para finalizar pois apenas fechar a aba do navegador mantém o programa ativo.

## Projeto

O programa demonstra as sete camadas OSI, encapsulamento, rotas de menor custo, endereços, segmentação, cifra didática, falhas e métricas. 

Computadores processam L1–L7

Roteadores processam L1–L3

| Arquivo ou pasta | Responsabilidade |
|---|---|
| SimuladorOSI.exe | Programa compilado, com o interpretador e a interface incorporados |
| topologia.json | Dispositivos, endereços, enlaces, custos e cenários. Pode ser substituído sem recompilar |
| main.py | Inicia o servidor local e abre o navegador |
| osi/__init__.py | Número da versão |
| osi/camadas.py | Sete classes de camada, cifra, segmentação, remontagem e encaminhamento |
| osi/pdu.py | Formatos binários de segmento, pacote, quadro e bits |
| osi/dispositivos.py | Hosts, roteadores e interfaces |
| osi/rede.py | Validação do JSON, tabelas e transmissão pelo enlace |
| osi/simulador.py | Eventos, coordenação dos cenários e métricas |
| osi/observacao.py | Detalhes didáticos dos cabeçalhos e contagem por quadro |
| osi/visual.py | Servidor HTTP local e comandos da interface |
| interface/index.html | Campos e painéis da tela |
| interface/styles.css | Aparência da interface |
| interface/app.js | Desenho, reprodução, pilhas OSI/TCP-IP e exportação do log |
