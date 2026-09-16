# Simulador OSI

## Executar

Extraia o ZIP completo e abra **SimuladorOSI.exe** com dois cliques. 

Mantenha **topologia.json** na mesma pasta. 

É necessário Windows 10/11 e um navegador com JavaScript

Não é necessário instalar Python ou acessar a internet durante o uso.

Escolha **E2**, clique **Preparar** e **Ir ao resultado**. Confira 42 B úteis, 368 B transmitidos, quatro quadros e eficiência global de 11,41%. 

Use **Encerrar** para finalizar pois apenas fechar a aba do navegador mantém o programa ativo.

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
