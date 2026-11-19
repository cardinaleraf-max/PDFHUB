import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [folder,port,host]=process.argv.slice(2);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let target;
for(let i=0;i<50&&!target;i++){
  target=(await(await fetch('http://127.0.0.1:'+port+'/json/list')).json()).find(t=>t.url.includes(host));
  await delay(100);
}
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let seq=0;
const pending=new Map(),downloads=[],completed=new Set();
ws.onmessage=event=>{
  const msg=JSON.parse(event.data);
  if(msg.method==='Browser.downloadWillBegin')downloads.push(msg.params);
  if(msg.method==='Browser.downloadProgress'&&msg.params.state==='completed')completed.add(msg.params.guid);
  if(pending.has(msg.id)){pending.get(msg.id)(msg);pending.delete(msg.id)}
};
function send(method,params={}){
  return new Promise(resolve=>{pending.set(++seq,resolve);ws.send(JSON.stringify({id:seq,method,params}))});
}
async function evaluate(expression){
  const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  if(result.error||result.result.exceptionDetails)throw Error(JSON.stringify(result));
  return result.result.result.value;
}
const downloadsFolder=path.join(folder,'downloads');fs.mkdirSync(downloadsFolder);
await send('Browser.setDownloadBehavior',{behavior:'allowAndName',downloadPath:downloadsFolder,eventsEnabled:true});
const samples=JSON.parse(fs.readFileSync(path.join(folder,'cases.json'),'utf8'));
try {
  for(let i=0;i<40&&!await evaluate("typeof filterCatalog==='function'");i++)await delay(100);
  assert.equal(await evaluate("document.querySelectorAll('.sat').length"),8);
  // Il selettore file usa lo stesso input del comando Studio > Scegli file.
  const example=path.join(folder,'Selezione manuale.pdf');
  fs.writeFileSync(example,Buffer.from(samples[0].files[0].raw,'base64'));
  await send('Page.setInterceptFileChooserDialog',{enabled:true});
  await evaluate("document.querySelector('#browse').click()");
  const documentNode=(await send('DOM.getDocument')).result.root.nodeId;
  const pickerNode=(await send('DOM.querySelector',{nodeId:documentNode,selector:'#picker'})).result.nodeId;
  await send('DOM.setFileInputFiles',{nodeId:pickerNode,files:[example]});
  assert.equal(await evaluate("document.querySelector('#operation').value"),'compress');
  assert.equal(await evaluate("document.querySelector('#editor').open&&document.querySelector('#files').textContent.includes('Selezione manuale.pdf')"),true);
  await evaluate("document.querySelector('#close').click();document.querySelector('.sat[data-op=merge]').click();let d=new DataTransfer();for(let n of ['Primo.pdf','Secondo.pdf'])d.items.add(new File(['x'],n));document.querySelector('dialog').dispatchEvent(new DragEvent('drop',{dataTransfer:d}));document.querySelectorAll('.filerow')[1].querySelector('button').click()");
  assert.equal(await evaluate("document.querySelector('.filerow span').textContent"),'Secondo.pdf');
  await evaluate("document.querySelector('.filerow button:last-child').click();document.querySelector('#run').click()");
  assert.equal(await evaluate("document.querySelector('#status').textContent.includes('File richiesti')"),true);
  await evaluate("document.querySelector('#close').click()");
  assert.equal(await evaluate("document.querySelectorAll('#catalog .card').length"),37);
  assert.equal(await evaluate("document.querySelector('[data-view=tools]').click();document.querySelector('#search').value='filigrana';filterCatalog();document.querySelectorAll('#catalog .card').length"),1);
  await evaluate("document.querySelector('#search').value='';filterCatalog();window.showSaveFilePicker=undefined");
  for(const item of samples){
    const status=await evaluate('('+ (async function(sample){
      const q=s=>document.querySelector(s);
      q('nav [data-view=tools]').click();
      q('#catalog [data-op='+sample.op+']').click();
      const transfer=new DataTransfer();
      for(const f of sample.files)transfer.items.add(new File([Uint8Array.from(atob(f.raw),c=>c.charCodeAt(0))],f.name));
      if(transfer.files.length)q('dialog').dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:transfer}));
      for(const [key,value] of Object.entries(sample.options)){
        const el=q('[name='+key+']');el.value=value;el.dispatchEvent(new Event('change'));
      }
      q('#run').click();
      for(let i=0;i<3200&&q('#form').inert;i++)await new Promise(r=>setTimeout(r,100));
      if(q('dialog').open){const error=q('#status').textContent;q('#close').click();return {error}}
      const name=q('.result strong').textContent;q('.result button').click();return {name};
    }).toString()+')('+JSON.stringify(item)+')');
    if(!status.error){
      let output;
      for(let i=0;i<100&&!output;i++){
        const last=downloads.at(-1);
        if(last&&completed.has(last.guid)&&last.suggestedFilename===status.name&&fs.existsSync(path.join(downloadsFolder,last.guid)))output=path.join(downloadsFolder,last.guid);
        if(!output)await delay(50);
      }
      assert.ok(output,'Salvataggio '+item.label);
      fs.renameSync(output,path.join(folder,item.label+'.bin'));
    }
    fs.writeFileSync(path.join(folder,item.label+'.json'),JSON.stringify(status));
    console.log(item.label,status.error||'salvato');
  }
}finally{ws.close()}
