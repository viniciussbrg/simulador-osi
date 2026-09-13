# Simulador OSI

## Executar

Extraia o ZIP completo e abra **SimuladorOSI.exe** com dois cliques. Mantenha **topologia.json** na mesma pasta. É necessário Windows 10/11 e um navegador com JavaScript; não é necessário instalar Python ou acessar a internet durante o uso.

Escolha **E2**, clique **Preparar** e **Ir ao resultado**. Confira 42 B úteis, 368 B transmitidos, quatro quadros e eficiência global de 11,41%. Use **Encerrar** para finalizar; fechar apenas a aba mantém o programa ativo.

## Compilar

Na máquina de desenvolvimento, instale Python 3.10 ou superior e execute **build_windows.bat**. O script também reconhece o Python instalado pela Microsoft Store. A primeira compilação exige internet para instalar o PyInstaller 6.22.2.

O resultado fica em **release**, em uma nova pasta e um ZIP com data e hora. Abra o executável dessa nova pasta para testar as alterações. A distribuição inclui o código e os scripts para repetir o build. Para executar os fontes diretamente, use `python main.py`.

O build cria um ambiente em `.venv-build` e arquivos temporários em `build`. Eles não entram no ZIP; podem ser apagados após a compilação. Apagar o ambiente exige instalar novamente a dependência no próximo build. Os builds anteriores permanecem em `release`.

## Projeto

Comunicação de Dados, professor Vinícius S. Borges.

O programa demonstra as sete camadas OSI, encapsulamento, rotas de menor custo, endereços, segmentação, cifra didática, falhas e métricas. 

Computadores processam L1–L7

Roteadores processam L1–L3

| Arquivo ou pasta | Responsabilidade |
|---|---|
| SimuladorOSI.exe | Programa compilado, com o interpretador e a interface incorporados |
| topologia.json | Dispositivos, endereços, enlaces, custos e cenários; pode ser substituído sem recompilar |
| main.py | Inicia o servidor local e abre o navegador |
| osi/__init__.py | Número da versão |
| osi/camadas.py | Sete classes de camada, cifra, segmentação, remontagem e encaminhamento |
| osi/pdu.py | Formatos binários de segmento, pacote, quadro e bits |
| osi/dispositivos.py | Hosts, roteadores e interfaces |
| osi/rede.py | Validação do JSON, Dijkstra, tabelas e transmissão pelo enlace |
| osi/simulador.py | Eventos, coordenação dos cenários e métricas |
| osi/observacao.py | Detalhes didáticos dos cabeçalhos e contagem por quadro |
| osi/visual.py | Servidor HTTP local e comandos da interface |
| interface/index.html | Campos e painéis da tela |
| interface/styles.css | Aparência da interface |
| interface/app.js | Desenho, reprodução, pilhas OSI/TCP-IP e exportação do log |
| build.py | Compilação e montagem do ZIP |
| build_windows.bat | Localização do Python e início do build |
| requirements-build.txt | Dependência de compilação |
