'use strict';
const $ = id => document.getElementById(id);
const state = {model:null, token:'', scenarios:{}, result:null, index:0, timer:null, current:null, configVersion:0, busy:false};
const names = {7:'Aplicação',6:'Apresentação',5:'Sessão',4:'Transporte',3:'Rede',2:'Enlace',1:'Física'};
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n).toLocaleString('pt-BR',{maximumFractionDigits:2,minimumFractionDigits:2});
const ipHost = name => Object.values(state.model.dispositivos.find(d=>d.nome===name).interfaces)[0].ip;
function alertMessage(text) { $('alert').textContent=text; $('alert').hidden=!text; }
async function api(path, body) {
  const response=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-OSI-Token':state.token},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(data.erro || 'Falha na operação.');
  return data;
}
function guard(fn) { return async (...args)=>{try{alertMessage('');await fn(...args);}catch(err){pause();alertMessage(err.message);}}; }
function options(node, values, selected) {
  node.replaceChildren(...values.map(([value,label])=>{const op=document.createElement('option');op.value=value;op.textContent=label;return op;}));
  if(selected!==undefined) node.value=selected;
}
function selectTab(id) {
  document.querySelectorAll('.tab').forEach(e=>e.hidden=e.id!==id);
  document.querySelectorAll('[data-tab]').forEach(e=>e.classList.toggle('selected',e.dataset.tab===id));
}
function pause() { if(state.timer!==null)clearTimeout(state.timer);state.timer=null;$('play').disabled=false; }
function invalidate() {
  pause();state.result=null;state.index=0;state.current=null;
  $('log').textContent='';$('progress').value=0;$('identity').textContent='—';
  $('status').textContent='Configuração alterada. Clique em Preparar.';
  $('current').textContent='Prepare a simulação e avance um passo.';
  $('pdu').replaceChildren();$('pduTitle').textContent='';
  renderAddresses(null);
  $('metrics').replaceChildren();$('routesResult').replaceChildren();$('comparison').replaceChildren();$('deliveries').replaceChildren();
  if(state.model){renderMap();renderStacks();renderTables();}
}
function byteCount() {$('byteCount').textContent=new TextEncoder().encode($('message').value).length+' B em UTF-8';}
async function loadConfig() {
  const version=++state.configVersion;
  const cfg=await api('configuracao',{caso:$('scenario').value});
  if(version!==state.configVersion)return;
  const map={source:'origem',destination:'destino',message:'mensagem',sourceProcess:'processo_origem',targetProcess:'processo_destino',sourcePort:'porta_origem',targetPort:'porta_destino',limit:'limite',source2:'origem2',sourcePort2:'porta_origem2'};
  for(const [id,key] of Object.entries(map)) $(id).value=cfg[key]??(id==='sourcePort2'?5310:'');
  $('linkDown').value=cfg.links_inativos[0]??'';$('bitError').value=cfg.enlace_erro??'';$('reverse').checked=cfg.ordem_inversa;
  $('secondSourceLabel').hidden=$('scenario').value!=='E3';$('secondPortLabel').hidden=$('scenario').value!=='E3';
  $('profile').textContent=$('scenario').value==='E7'?'Perfil E7: 100 B úteis · cargas 40 / 40 / 24 B':'Perfil padrão: 42 B úteis · limite L4 de 64 B';
  byteCount();invalidate();
}
function config() {
  const c={origem:$('source').value,destino:$('destination').value.trim(),mensagem:$('message').value,
    processo_origem:$('sourceProcess').value.trim(),processo_destino:$('targetProcess').value.trim(),
    porta_origem:Number($('sourcePort').value),porta_destino:Number($('targetPort').value),limite:Number($('limit').value),
    links_inativos:$('linkDown').value?[$('linkDown').value]:[],enlace_erro:$('bitError').value,ordem_inversa:$('reverse').checked};
  if($('scenario').value==='E3'){c.origem2=$('source2').value;c.porta_origem2=Number($('sourcePort2').value);}
  return c;
}
async function prepare() {
  if(state.busy)return false;
  invalidate();state.busy=true;$('prepare').disabled=true;
  try {
    const version=state.configVersion;
    const result=await api('simular',{caso:$('scenario').value,configuracao:config()});
    if(version!==state.configVersion)return false;
    state.result=result;
    $('progress').max=state.result.eventos.length;
    $('status').textContent=`${state.result.caso} · ${state.result.titulo} · 0/${state.result.eventos.length} passos`;
    renderStacks();renderTables();selectTab('events');return true;
  } finally {state.busy=false;$('prepare').disabled=false;}
}
function showEvent(e) {
  state.current=e;
  $('log').textContent += e.linha+'\n';
  $('log').scrollTop=$('log').scrollHeight;
  $('current').textContent=`${e.dispositivo} · L${e.camada} ${names[e.camada]} · ${e.acao}: ${e.descricao}`;
  $('identity').textContent=[e.pacote_id,e.quadro_id].filter(Boolean).join(' / ')||'—';
  renderAddresses(e);
  $('pduTitle').textContent=`${e.pdu} · ${e.tamanho} B`;
  $('pdu').replaceChildren(...e.blocos.map(([label,size])=>{const d=document.createElement('div');d.className='block '+label;
    const b=document.createElement('b');b.textContent=label==='F2'?'F2 / T2':label;const span=document.createElement('span');span.textContent=size+' B';d.append(b,span);return d;}));
  $('status').textContent=`${state.result.caso} · ${state.index}/${state.result.eventos.length} passos · ${e.dispositivo} L${e.camada}`;
  $('progress').value=state.index;renderMap();renderStacks();
}
function renderAddresses(e) {
  $('applicationAddress').textContent=e?`${e.processo_origem} → ${e.processo_destino}`:'—';
  $('transportAddress').textContent=e?`${e.porta_origem} → ${e.porta_destino}`:'—';
  $('logical').textContent=e?`${e.ip_origem} → ${e.ip_destino}`:'—';
  $('physical').textContent=e?.mac_origem?`${e.mac_origem} → ${e.mac_destino}`:'Ainda não há quadro neste fluxo.';
}
async function step() {
  if(state.busy)return;
  if(!state.result && !(await prepare()))return;
  pause();advance();
}
function advance() {
  if(!state.result || state.index>=state.result.eventos.length)return;
  showEvent(state.result.eventos[state.index++]);
  if(state.index===state.result.eventos.length){pause();renderResults();selectTab('results');$('status').textContent='Simulação concluída. A janela permanece aberta.';}
}
async function play() {
  if(state.busy || state.timer!==null)return;
  if(!state.result && !(await prepare()))return;
  if(state.index>=state.result.eventos.length)return;
  function tick(){state.timer=null;advance();if(state.index<state.result.eventos.length){$('play').disabled=true;state.timer=setTimeout(tick,Number($('speed').value));}}
  tick();
}
async function finish() {
  if(state.busy)return;
  if(!state.result && !(await prepare()))return;
  pause();const r=state.result;state.index=r.eventos.length;
  // Atualiza a mesma lista de eventos; nenhuma camada é chamada pela interface.
  $('log').textContent='';showEvent(r.eventos.at(-1));$('log').textContent=r.log+'\n';
  renderResults();selectTab('results');$('status').textContent='Simulação concluída. A janela permanece aberta.';
}
function renderResults() {
  if(!state.result){$('metrics').textContent='Prepare e execute uma simulação.';return;}
  const m=state.result.metricas;
  const cards=[['Dados úteis',m.dados_uteis+' B','gerados na origem'],['Transmitidos',m.transmitidos+' B','soma de todos os enlaces'],['Quadros',m.quadros,'independentes, numerados'],['Segmentos / pacotes',m.segmentos+' / '+m.pacotes,'cargas: '+state.result.cargas.map(c=>c.join('/')).join(' · ')+' B'],['Eficiência global',fmt(m.eficiencia_global*100)+'%','sobrecarga global '+fmt(m.sobrecarga*100)+'%'],['Eficiência dos quadros',fmt(m.eficiencia_quadros*100)+'%',m.dados_nos_quadros+' B de aplicação / '+m.transmitidos+' B'],['Controle nos quadros',m.controle_transmitido+' B','H5 + H4 + H3 + H2 + F2'],['Entregas',m.mensagens_entregues+'/'+m.mensagens_total,m.dados_entregues+' B chegaram à aplicação']];
  if(!m.transmitidos)for(const card of cards)if(card[0].startsWith('Eficiência')){card[1]='—';card[2]='nenhum quadro transmitido';}
  $('metrics').innerHTML=cards.map(([label,value,detail])=>`<div class="metric"><span>${escapeText(label)}</span><b>${escapeText(value)}</b><span>${escapeText(detail)}</span></div>`).join('');
  
  $('frameMetrics').innerHTML=table(['Quadro','Enlace','Dados de aplicação','Controle','Total','Eficiência'],state.result.quadros_detalhados.map(q=>[q.quadro,q.enlace.join(' → '),q.dados+' B',q.controle+' B',q.total+' B',fmt(q.eficiencia*100)+'%']));
  
  $('routesResult').textContent=state.result.rotas.map((r,i)=>`${r.join(' → ')} · custo entre roteadores: ${state.result.custos[i]}`).join(' | ');
  $('comparison').textContent='Referência E1 × E2 (42 B, rede original): entrega direta 42/92 = 45,65% · indireta 42/368 = 11,41%.';
  $('deliveries').replaceChildren(...state.result.entregas.map(d=>{const p=document.createElement('p');p.textContent=`${d.destino} / ${d.processo}: ${d.texto}`;return p;}));
  if(!state.result.entregas.length)$('deliveries').textContent='Nenhuma mensagem chegou à aplicação. Consulte o descarte no registro.';
}
function table(headers, rows) {return '<table><thead><tr>'+headers.map(h=>'<th>'+escapeText(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(c=>'<td>'+escapeText(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';}
function renderTables() {
  const rows=state.result?.tabelas??state.model.tabelas;
  $('routes').innerHTML=table(['Roteador','Prefixo de destino','Próximo salto','Interface','Custo'],rows.map(r=>[r.roteador,r.prefixo,r.proximo,r.interface,r.custo??'—']));
  const interfaces=state.model.dispositivos.flatMap(d=>Object.entries(d.interfaces).map(([name,i])=>[d.nome,d.tipo==='host'?'Computador':'Roteador',name,i.ip,i.mac,i.rede??'ponto a ponto']));
  $('interfaces').innerHTML=table(['Dispositivo','Tipo','Interface','IPv4','MAC','Rede'],interfaces);
}
function renderStacks() {
  const involved=state.result?.dispositivos_envolvidos??[$('source').value,$('destination').value].filter(n=>state.model.dispositivos.some(d=>d.nome===n));
  const mode=$('stackMode').value;
  $('stackExplanation').textContent=mode==='OSI'?'OSI: sete camadas nos computadores, três nos roteadores.':'TCP/IP de cinco camadas (Aula 2): L5–L7 formam Aplicação; Enlace e Física permanecem separados. O agrupamento muda a exibição, preservando a simulação.';
  $('stacks').replaceChildren(...[...new Set(involved)].map(name=>{
    const d=state.model.dispositivos.find(x=>x.nome===name),router=d.tipo==='router';
    const groups=mode==='OSI'?(router?[3,2,1]:[7,6,5,4,3,2,1]).map(n=>[`${n} ${names[n]}`,[n]]):
      (router?[['Internet · L3',[3]],['Enlace · L2',[2]],['Física · L1',[1]]]:[['Aplicação · L7–L5',[7,6,5]],['Transporte · L4',[4]],['Internet · L3',[3]],['Enlace · L2',[2]],['Física · L1',[1]]]);
    const box=document.createElement('div');box.className='stack'+(router?' router':'')+(mode==='TCP/IP'?' tcp':'');
    const title=document.createElement('h3');title.textContent=name;const layers=document.createElement('div');layers.className='layers';
    for(const [label,ns] of groups){const el=document.createElement('div');el.textContent=label;el.className='layer';
      const active=state.current?.dispositivo===name&&ns.includes(state.current?.camada);
      if(active)el.classList.add('active');if(active&&router&&ns.includes(3)&&state.current.acao==='ROTEIA')el.classList.add('routing');layers.append(el);}
    box.append(title,layers);return box;
  }));
}
const svgNS='http://www.w3.org/2000/svg';
function svg(tag,attrs,text){const e=document.createElementNS(svgNS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
function renderMap() {
  if(!state.model)return;
  const s=$('network');s.replaceChildren();
  const ds=state.model.dispositivos, positions=Object.fromEntries(ds.map(d=>[d.nome,d.posicao]));
  const xs=ds.map(d=>d.posicao[0]),ys=ds.map(d=>d.posicao[1]);
  const xMin=Math.min(...xs)-100,yMin=Math.min(...ys)-48;
  s.setAttribute('viewBox',`${xMin} ${yMin} ${Math.max(...xs)-xMin+100} ${Math.max(...ys)-yMin+65}`);
  const disabled=state.result?.links_inativos??($('linkDown').value?[$('linkDown').value]:[]);
  function line(a,b,attrs){const [x1,y1]=positions[a],[x2,y2]=positions[b];s.append(svg('line',{x1,y1,x2,y2,...attrs}));}
  for(const seg of state.model.segmentos){
    const members=seg.membros.map(m=>m.dispositivo);
    const off=disabled.includes(seg.nome),color=off?'#bd3434':'#aec1cf';
    if(seg.tipo==='p2p'){
      line(...members,{stroke:color,'stroke-width':3,'stroke-dasharray':off?'7 4':'none'});
      const [x1,y1]=positions[members[0]],[x2,y2]=positions[members[1]];
      s.append(svg('text',{x:(x1+x2)/2,y:(y1+y2)/2-10,'text-anchor':'middle','font-size':13,fill:color},off?'INATIVO':'custo '+seg.custo));
    }else{
      const router=members.find(n=>ds.find(d=>d.nome===n).tipo==='router');
      for(const name of members)if(name!==router)line(router,name,{stroke:color,'stroke-width':2,'stroke-dasharray':'3 4'});
      const host=members.find(n=>n!==router),[x,y]=positions[host];
      const lan=state.model.redes_lan.find(r=>r.prefixo===seg.prefixo);
      s.append(svg('text',{x,y:y-36,'text-anchor':'middle','font-size':12,fill:'#487187'},(lan?.nome??seg.nome)+' · '+seg.prefixo));
    }
  }
  // Destaca somente enlaces já TRANSMITIDOS, incluindo os dois fluxos de E3.
  const traversed=new Set();
  for(const e of state.result?.eventos.slice(0,state.index)??[]){if(e.acao==='TRANSMITE'&&e.enlace_ativo.length){const k=e.enlace_ativo.join('|');if(!traversed.has(k)){line(...e.enlace_ativo,{stroke:'#2085c6','stroke-width':5});traversed.add(k);}}}
  const active=state.current?.enlace_ativo;
  if(active?.length && state.current.camada<=2){line(...active,{stroke:'#efaa28','stroke-width':7});const [a,b]=active;const x=(positions[a][0]+positions[b][0])/2,y=(positions[a][1]+positions[b][1])/2;
    s.append(svg('rect',{x:x-23,y:y+5,width:46,height:20,rx:4,fill:'#fff3d5'}));s.append(svg('text',{x,y:y+20,'text-anchor':'middle','font-size':13,fill:'#6d4c08'},state.current.quadro_id));}
  for(const d of ds){const [x,y]=d.posicao;const router=d.tipo==='router',on=state.current?.dispositivo===d.nome;
    s.append(svg('rect',{x:x-48,y:y-25,width:96,height:50,rx:router?18:5,fill:on?'#fff0c5':router?'#e1f2ec':'#e7f0fa',stroke:on?'#ba8b20':router?'#5e9b88':'#648fac','stroke-width':on?3:1.5}));
    s.append(svg('text',{x,y:y-4,'text-anchor':'middle','font-size':16,'font-weight':700,fill:'#173a51'},d.nome));
    s.append(svg('text',{x,y:y+13,'text-anchor':'middle','font-size':12,fill:'#496578'},Object.keys(d.interfaces).join(' · ')));
    if(!router)s.append(svg('text',{x,y:y+41,'text-anchor':'middle','font-size':11,fill:'#557286'},Object.values(d.interfaces)[0].ip));
  }
}
function saveLog() {
  if(!state.result)throw new Error('Prepare uma simulação antes de salvar.');
  const m=state.result.metricas;
  const text=state.result.log+`\n\nRESUMO ${state.result.caso}\nDados úteis: ${m.dados_uteis} B\nTransmitidos: ${m.transmitidos} B\nQuadros: ${m.quadros}\nEficiência global: ${fmt(m.eficiencia_global*100)}%\nEficiência dos quadros: ${fmt(m.eficiencia_quadros*100)}%\nControle nos quadros: ${m.controle_transmitido} B\nDados entregues: ${m.dados_entregues} B\n\n`;
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));a.download='log_'+state.result.caso+'.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
async function installState(data) {
  pause();state.token=data.token;state.model=data.topologia;state.scenarios=data.cenarios;
  if(!state.model){alertMessage('Não foi possível carregar topologia.json: '+data.erro+'. Use Abrir topologia para corrigir.');$('status').textContent='Aguardando topologia válida.';return;}
  $('topologyName').textContent=state.model.nome;
  const hosts=state.model.dispositivos.filter(d=>d.tipo==='host').map(d=>[d.nome,d.nome]);
  options($('source'),hosts);options($('source2'),hosts);
  $('hosts').replaceChildren(...hosts.map(([n])=>{const op=document.createElement('option');op.value=n;return op;}));
  const links=[['','Nenhum'],...state.model.segmentos.map(s=>[s.nome,s.nome])];options($('linkDown'),links);options($('bitError'),links);
  const cases=Object.entries(data.casos).filter(([id])=>id==='PERSONALIZADO'||Object.hasOwn(data.cenarios,id));
  options($('scenario'),cases.map(([id,label])=>[id,id==='PERSONALIZADO'?'Personalizado':id+' / C'+id.slice(1)+' — '+label]),data.cenarios.E2?'E2':'PERSONALIZADO');
  await loadConfig();alertMessage(data.erro||'');
}
$('prepare').onclick=guard(prepare);$('step').onclick=guard(step);$('play').onclick=guard(play);$('pause').onclick=()=>{pause();$('status').textContent='Pausado. Use Próximo passo ou Executar para continuar.';};$('finish').onclick=guard(finish);$('saveLog').onclick=guard(saveLog);
$('scenario').onchange=guard(loadConfig);$('restore').onclick=guard(loadConfig);$('stackMode').onchange=renderStacks;
for(const id of ['source','destination','message','sourceProcess','targetProcess','sourcePort','targetPort','limit','source2','sourcePort2','linkDown','bitError','reverse'])$(id).addEventListener('input',()=>{state.configVersion++;invalidate();byteCount();$('profile').textContent='Parâmetros editados · Restaurar cenário repõe os valores de referência.';});
$('loadTopology').onclick=()=>$('fileTopology').click();
$('fileTopology').onchange=guard(async()=>{const file=$('fileTopology').files[0];if(!file)return;if(file.size>250000)throw new Error('JSON deve ter até 250 kB.');await installState(await api('topologia',{dados:JSON.parse(await file.text())}));$('fileTopology').value='';});
$('reloadTopology').onclick=guard(async()=>installState(await api('recarregar',{})));
$('shutdown').onclick=guard(async()=>{pause();await api('encerrar',{});alertMessage('Simulador encerrado. Esta aba pode ser fechada.');document.body.classList.add('closed');});
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{if(b.dataset.tab==='results')renderResults();selectTab(b.dataset.tab);});
window.addEventListener('pagehide',pause);
guard(async()=>{const response=await fetch('/api/estado');if(!response.ok)throw new Error('Falha ao abrir a interface local.');await installState(await response.json());})();
