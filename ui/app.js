const $ = selector => document.querySelector(selector);
const paths = {
  orbit:'<circle cx="12" cy="12" r="3"/><ellipse cx="12" cy="12" rx="11" ry="6" transform="rotate(-40 12 12)"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  inbox:'<path d="m3 14 4-9h10l4 9v5H3zm0 0h5l2 3h4l2-3h5"/>',
  shield:'<path d="m12 2 8 4v6q0 6-8 10-8-4-8-10V6z"/><path d="m8 12 3 3 5-6"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',x:'<path d="m6 6 12 12M18 6 6 18"/>',
  arrow:'<path d="M4 12h15m-5-5 5 5-5 5"/>',corner:'<path d="M6 18 18 6M7 6h11v11"/>',
  pointer:'<path d="m4 3 6 17 3-7 7-3z"/>',
  merge:'<rect x="8" y="8" width="12" height="14" rx="2"/><path d="M15 5V3H4v14h2m5-3h6m-3-3v6"/>',
  split:'<circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/><path d="m8 15 11-12M16 15 5 3"/>',
  compress:'<path d="m3 3 6 6m0-5v5H4m17 12-6-6m0 5v-5h5M4 15v5h5M20 9V4h-5"/>',
  toimg:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m4 18 5-5 3 2 4-5 5 6"/>',
  fromimg:'<path d="M5 2h9l5 5v15H5zm9 0v6h5M8 17l3-4 2 2 2-3 2 4"/>',
  rotate:'<path d="M3 10a9 9 0 1 1 1 8M3 4v6h6"/>',
  text:'<path d="M4 5h16M4 10h12M4 15h16M4 20h10"/>',
  protect:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M7 10V7a5 5 0 0 1 10 0v3m-5 4v3"/>'
};
const icon = name => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths[name]+'</svg>';
document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon));
const catalog = JSON.parse($('#catalog-data').textContent);
const tools = Object.fromEntries(catalog.groups.flatMap(group =>
  group.tools.map(tool => [tool.id,{...tool,group:group.name,color:group.color}])));
const orbit = ['merge','split','compress','toimg','rotate','text','protect','fromimg'];
const groupIcons = ['split','fromimg','toimg','compress','text','protect','orbit'];
function makeCard(id){
  const tool=tools[id], group=catalog.groups.findIndex(g=>g.name===tool.group);
  const fallback=groupIcons[group];
  const card=document.createElement('button');
  card.className='card';card.dataset.op=id;
  card.style.setProperty('--light','color-mix(in srgb,'+tool.color+' 35%,white)');
  card.style.setProperty('--ink-color','color-mix(in srgb,'+tool.color+' 40%,#14251d)');
  card.innerHTML='<span class="tile">'+icon(paths[id]?id:fallback)+'</span><span class="corner">'+icon('corner')+'</span><h3></h3><p></p>';
  card.querySelector('h3').textContent=tool.title;card.querySelector('p').textContent=tool.description;
  return card;
}
const palette=['#ffa074','#bca8ff','#88c8a5','#86c8ea','#edbb79','#e9a6c8','#95cfc6','#a8b8ff'];
orbit.forEach((id,index)=>{
  const angle=index*Math.PI/4, x=50+39*Math.sin(angle), y=50-39*Math.cos(angle);
  const sat=document.createElement('button');
  sat.className='sat';sat.dataset.op=id;sat.style.cssText='--color:'+palette[index]+';--dark:color-mix(in srgb,'+palette[index]+' 20%,#202922);--x:'+x+'%;--y:'+y+'%';
  sat.innerHTML='<span class="tile">'+icon(id)+'</span><small></small>';
  sat.querySelector('small').textContent=tools[id].title;$('#satellites').append(sat);
  if(index<4)$('#quick').append(makeCard(id));
});
for(const group of catalog.groups){
  $('#category').add(new Option(group.name,group.name));
  const section=document.createElement('optgroup');section.label=group.name;
  group.tools.forEach(t=>section.append(new Option(t.title,t.id)));
  $('#operation').append(section);
}
function filterCatalog(){
  const query=$('#search').value.trim().toLocaleLowerCase('it');
  const filtered=Object.values(tools).filter(t=>(!$('#category').value||t.group===$('#category').value)
    &&(t.title+' '+t.description).toLocaleLowerCase('it').includes(query));
  $('#catalog').replaceChildren(...filtered.map(t=>makeCard(t.id)));
  $('#count').textContent=filtered.length+' strumenti';
}
$('#search').oninput=filterCatalog;$('#category').onchange=filterCatalog;filterCatalog();
let files = [], history = [], busy = false, pickingHome = false;
const editor = $('#editor'), picker = $('#picker'), operation = $('#operation');
const current = () => operation.value;
const sizes = n => n < 1024**2 ? Math.max(1,Math.round(n/1024))+' KB' : (n/1024**2).toLocaleString('it-IT',{maximumFractionDigits:1})+' MB';
function show(view){
  for(const name of ['studio','tools','history']) $('#'+name).hidden = name!==view;
  document.querySelectorAll('nav button').forEach(btn=>btn.classList.toggle('active',btn.dataset.view===view));
  window.scrollTo(0,0);
}
document.addEventListener('click',event=>{
  const btn = event.target.closest('[data-view],[data-op]');
  if(!btn) return;
  event.preventDefault();
  if(btn.dataset.view) show(btn.dataset.view);
  else openTool(btn.dataset.op,[]);
});
function selectField(label,name,choices){
  const wrap = document.createElement('label');
  wrap.append(label);
  const select = document.createElement('select');
  select.name=name;
  choices.forEach(([value,text])=>select.add(new Option(text,value)));
  wrap.append(select);
  $('#options').append(wrap);
  return select;
}
function inputField(label,name,type,placeholder){
  const wrap=document.createElement('label'), input=document.createElement('input');
  wrap.append(label,input);input.name=name;input.type=type;input.placeholder=placeholder;input.autocomplete='off';
  $('#options').append(wrap);return wrap;
}
function configure(){
  const op=current();
  const tool=tools[op];
  $('#opTitle').textContent=tool.title;
  $('#opDesc').textContent=tool.description;
  $('#options').replaceChildren();$('#status').textContent='';
  $('#unlock').hidden=tool.accept!=='.pdf';
  $('#add').hidden=tool.max===0;
  for(const key of tool.fields){
    const [label,type,initial,...choices]=catalog.fields[key];
    if(type==='select'){
      const select=selectField(label,key,choices.map(c=>c.split('|')));
      select.value=initial;
    }else{
      const wrap=inputField(label,key,type,choices[0]||'');
      wrap.querySelector('input').value=initial;
    }
  }
  if(op==='split'){
    const mode=$('[name=mode]'), range=$('[name=pages]').parentElement;
    mode.onchange=()=>range.hidden=mode.value==='all';mode.onchange();
  }
  if(op==='summary'){
    const method=$('[name=method]'), model=$('[name=model]').parentElement;
    method.onchange=()=>model.hidden=method.value==='extractive';method.onchange();
  }
  $('#run').textContent=tool.title;
}
function openTool(op,initial){
  $('#form').reset();files=[...initial];operation.value=op;$('#unlock').open=false;
  configure();renderFiles();editor.showModal();
}
operation.onchange=configure;
function renderFiles(){
  const list=$('#files');list.replaceChildren();
  files.forEach((file,index)=>{
    const row=document.createElement('div');row.className='filerow';
    const name=document.createElement('span');name.textContent=file.name;
    const size=document.createElement('small');size.textContent=sizes(file.size);
    row.append(name,size);
    const action=(symbol,title,callback,disabled=false)=>{
      const btn=document.createElement('button');btn.type='button';btn.textContent=symbol;
      btn.setAttribute('aria-label',title+' '+file.name);btn.title=title;btn.disabled=disabled;
      btn.onclick=()=>{callback();renderFiles()};row.append(btn);
    };
    if(files.length>1){
      action('↑','Sposta su',()=>[files[index-1],files[index]]=[file,files[index-1]],index===0);
      action('↓','Sposta giù',()=>[files[index+1],files[index]]=[file,files[index+1]],index===files.length-1);
    }
    action('×','Rimuovi',()=>files.splice(index,1));list.append(row);
  });
}
const allAccept=[...new Set(Object.values(tools).flatMap(t=>t.accept.split(',')))].join(',');
function browse(home){
  pickingHome=home;picker.value='';
  picker.accept=home?allAccept:tools[current()].accept;
  picker.multiple=home||tools[current()].max>1;picker.click();
}
function receive(incoming,home){
  if(!incoming.length||busy)return;
  if(home){
    const suffix=f=>'.'+f.name.split('.').pop().toLowerCase();
    const first=suffix(incoming[0]);
    const op=first==='.pdf'?(incoming.length>1?'merge':'compress'):
      Object.keys(tools).find(id=>tools[id].accept.split(',').includes(first));
    openTool(op||'merge',incoming);
  }else{
    files=files.concat(incoming);renderFiles();$('#status').textContent='';
  }
}
$('#browse').onclick=()=>browse(true);$('#add').onclick=()=>browse(false);
picker.onchange=()=>receive(Array.from(picker.files),pickingHome);
for(const [zone,home] of [[$('#homeDrop'),true],[editor,false]]){
  zone.ondragover=e=>{e.preventDefault();zone.classList.add('drag')};
  zone.ondragleave=e=>{if(!zone.contains(e.relatedTarget))zone.classList.remove('drag')};
  zone.ondrop=e=>{e.preventDefault();zone.classList.remove('drag');receive(Array.from(e.dataTransfer.files),home)};
}
window.addEventListener('dragover',e=>e.preventDefault());
window.addEventListener('drop',e=>e.preventDefault());
$('#close').onclick=()=>editor.close();
editor.oncancel=e=>{if(busy)e.preventDefault()};
async function save(item){
  if(window.showSaveFilePicker){
    const handle=await window.showSaveFilePicker({suggestedName:item.name});
    const destination=await handle.createWritable();
    await destination.write(item.blob);await destination.close();
  }else{
    const link=document.createElement('a');link.download=item.name;link.href=URL.createObjectURL(item.blob);link.click();setTimeout(()=>URL.revokeObjectURL(link.href),60000);
  }
}
function renderHistory(){
  const list=$('#results');list.replaceChildren();
  if(!history.length)list.innerHTML='<p class="empty">Le conversioni completate appariranno qui.</p>';
  history.forEach(item=>{
    const row=document.createElement('div');row.className='result';
    const name=document.createElement('strong');name.textContent=item.name;
    const info=document.createElement('small');info.textContent=tools[item.op].title+' · '+sizes(item.blob.size);
    const btn=document.createElement('button');btn.className='primary';btn.textContent='Salva file';
    btn.onclick=async()=>{try{await save(item)}catch(e){if(e.name!=='AbortError')alert('Salvataggio non riuscito. Riprova.')}};
    row.append(name,info,btn);list.append(row);
  });
}
renderHistory();
$('#form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const status=$('#status'),op=current();
  if(files.length<tools[op].min||files.length>tools[op].max){status.textContent='File richiesti: '+(tools[op].min===tools[op].max?tools[op].min:tools[op].min+'–'+tools[op].max)+'.';return}
  if(files.reduce((n,f)=>n+f.size,0)>200*1024**2){status.textContent='Limite di 200 MB per operazione.';return}
  const data=new FormData();data.append('operation',op);
  data.append('options',JSON.stringify(Object.fromEntries(new FormData(event.target))));
  for(const f of files)data.append('files',f,f.name);
  busy=true;$('#form').inert=true;status.textContent='Elaborazione sul dispositivo…';
  $('#run').classList.add('working');$('#run').textContent='Elaborazione';
  try{
    const response=await fetch('/convert',{method:'POST',headers:{'X-Session':$('meta[name=session]').content},body:data});
    if(!response.ok)throw new Error(await response.text());
    history.unshift({name:decodeURIComponent(response.headers.get('X-Filename')),blob:await response.blob(),op});
    renderHistory();editor.close();files=[];show('history');
  }catch(error){status.textContent=error.message}
  finally{busy=false;$('#form').inert=false;$('#run').classList.remove('working');$('#run').textContent=tools[op].title}
};
fetch('/ready',{method:'POST',headers:{'X-Session':$('meta[name=session]').content}}).catch(()=>{});
