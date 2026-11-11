// Static HTML/CSS educational mockups only. No voice or video generation.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir,mkdtemp} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const sha=b=>createHash('sha256').update(b).digest('hex');

async function main(){
 const {values}=parseArgs({options:{html:{type:'string',default:'design/binary-counting-v1/mockup/index.html'},out:{type:'string',default:'assets/library/references/binary-counting/v001'},chrome:{type:'string',default:'C:/Program Files/Google/Chrome/Application/chrome.exe'}}});
 const out=path.resolve(values.out),html=path.resolve(values.html);
 await mkdir(out,{recursive:true});await mkdir('D:/temp',{recursive:true});
 const profile=await mkdtemp('D:/temp/binary-mockup-browser-');
 const browser=spawn(values.chrome,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-extensions','--disable-background-networking','--hide-scrollbars','--allow-file-access-from-files','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
 let stderr='';browser.stderr.on('data',b=>{stderr=(stderr+b.toString()).slice(-1500);});
 let ws;
 try{
  let port;
  for(let i=0;i<200;i++){try{port=Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);if(port>0)break;}catch(e){if(!['ENOENT','EBUSY','EPERM'].includes(e.code))throw e;}if(browser.exitCode!==null)throw new Error(stderr);await sleep(100);}
  if(!port)throw new Error('Headless browser did not become ready');
  const version=await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  ws=new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  let next=1;const pending=new Map(),events=new Map();
  ws.addEventListener('message',event=>{const m=JSON.parse(String(event.data));if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}}else{const k=`${m.sessionId}:${m.method}`;for(const callback of events.get(k)??[])callback(m.params);events.delete(k);}});
  function send(method,params={},sessionId){const id=next++;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
  function waitEvent(method,sessionId){return new Promise((resolve,reject)=>{const key=`${sessionId}:${method}`;const timer=setTimeout(()=>reject(new Error(`Timeout ${method}`)),30000);const list=events.get(key)??[];list.push(p=>{clearTimeout(timer);resolve(p);});events.set(key,list);});}
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  await send('Page.enable',{},sessionId);
  const jobs=[
   {scene:'intro',n:2,focus:-1,file:'01-intro.png',caption:'01  How to read: 10 is one zero'},
   {scene:'zero',n:0,focus:0,file:'02-zero.png',caption:'02  Start at zero; unused places stay blank'},
   {scene:'carry',n:8,focus:-1,file:'03-carry.png',caption:'03  A new place: 111 + 1 = 1000'},
   {scene:'break',n:31,focus:-1,file:'04-stretch.png',caption:'04  Stretch after 11111 (decimal 31)'},
   {scene:'normal',n:45,focus:2,file:'key-visual.png',caption:'05  Count 101101 (decimal 45)'},
   {scene:'finale',n:127,focus:-1,file:'06-finale.png',caption:'06  Finish with seven ones (decimal 127)'},
  ];
  const results=[];
  async function navigate(url,width,height,expression){
   await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false},sessionId);
   const loaded=waitEvent('Page.loadEventFired',sessionId);
   await send('Page.navigate',{url},sessionId);await loaded;
   const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true},sessionId);
   if(result.exceptionDetails)throw new Error(result.exceptionDetails.text+' '+JSON.stringify(result.exceptionDetails.exception));
   return result.result.value;
  }
  for(const job of jobs){
   const url=pathToFileURL(html);url.search=new URLSearchParams({scene:job.scene,n:String(job.n),focus:String(job.focus)}).toString();
   const state=await navigate(url.href,1920,1080,`(async()=>{await window.mockupReady;const s=window.getMockupState();s.glyphRasterQa=[...document.querySelectorAll('canvas.bit-value')].flatMap(c=>{const ctx=c.getContext('2d'),d=ctx.getImageData(0,0,c.width,c.height).data;let l=c.width,t=c.height,r=-1,b=-1;for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++)if(d[(y*c.width+x)*4+3]){l=Math.min(l,x);t=Math.min(t,y);r=Math.max(r,x);b=Math.max(b,y)}if(r<0)return[];const box=c.getBoundingClientRect(),dx=((l+r+1)/2-c.width/2)*box.width/c.width,dy=((t+b+1)/2-c.height/2)*box.height/c.height;return[{digit:c.getAttribute('aria-label'),delta_css_px:[dx,dy],passed:Math.max(Math.abs(dx),Math.abs(dy))<=.501}]});s.overflowQa=[...document.querySelectorAll('.title-pill,.range-plaque,.say-line')].map(e=>({className:e.className,passed:e.scrollWidth<=e.clientWidth+1}));return s;})()`);
   if(state.n!==job.n||state.bits!==job.n.toString(2)||state.tokenwords.join(' ')!==[...job.n.toString(2)].map(b=>b==='1'?'one':'zero').join(' '))throw new Error('Mockup math/reading mismatch');
   if(!state.glyphRasterQa.every(x=>x.passed)||!state.overflowQa.every(x=>x.passed))throw new Error('Mockup ink centering or text overflow QA failed');
   const captured=await send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false},sessionId);
   const bytes=Buffer.from(captured.data,'base64');await writeFile(path.join(out,job.file),bytes,{flag:'wx'});
   results.push({...job,url:url.href,state,sha256:sha(bytes),bytes:bytes.length});console.log(JSON.stringify({file:job.file,n:state.n,bits:state.bits,bytes:bytes.length}));
  }
  const font=path.relative(path.dirname(html),path.resolve('assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf')).replaceAll('\\','/');
  const story=path.join(path.dirname(html),'storyboard.html');
  const source=`<!doctype html><meta charset="utf-8"><title>Binary Counting Storyboard</title><style>@font-face{font-family:round;src:url('${font}')}*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1900px;overflow:hidden;background:#f4eedf;color:#563718;font-family:round,sans-serif}header{height:112px;padding:24px 36px}h1{margin:0;font-size:34px}header p{margin:5px 0;font:20px round}main{display:grid;grid-template-columns:repeat(2,918px);gap:20px;margin:0 32px}.card{height:568px;background:#fff9eb;border-radius:14px;overflow:hidden;border:2px solid #d2b28c}.view{height:516.375px;width:918px;overflow:hidden}.view iframe{width:1920px;height:1080px;border:0;transform:scale(.478125);transform-origin:top left}.caption{height:48px;font:22px round;padding:9px 15px}</style><header><h1>Num-Num Numbers — Binary Lantern Garden</h1><p>Preproduction storyboard · proposed range 0–1111111₂ · decimal 0–127 · timing not measured</p></header><main>${results.map(j=>`<section class="card"><div class="view"><iframe src="${path.basename(html)}?${new URLSearchParams({scene:j.scene,n:String(j.n),focus:String(j.focus)}).toString().replaceAll('&','&amp;')}"></iframe></div><div class="caption">${j.caption}</div></section>`).join('')}</main><script>window.storyReady=Promise.all([...document.querySelectorAll('iframe')].map(f=>new Promise((resolve,reject)=>{f.onload=()=>Promise.resolve(f.contentWindow.mockupReady).then(resolve,reject);f.onerror=reject}))).then(()=>document.fonts.ready);</script>`;
  await writeFile(story,source);
  await navigate(pathToFileURL(story).href,1920,1900,'(async()=>{await window.storyReady; return true;})()');
  const captured=await send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false},sessionId);
  const bytes=Buffer.from(captured.data,'base64');await writeFile(path.join(out,'storyboard.png'),bytes,{flag:'wx'});
  const report={schema_version:1,kind:'static-binary-preproduction-mockups',status:'generated-pending-image-review',browser:version.Browser,source_html:html,profile_directory:profile,generated_audio:false,generated_video:false,results,storyboard:{path:path.join(out,'storyboard.png'),sha256:sha(bytes),bytes:bytes.length}};
  await writeFile(path.join(out,'mockup-render.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  await send('Browser.close');ws.close();console.log(JSON.stringify({completed:true,frames:results.length,storyboard:true,out,profile}));
 }finally{if(ws&&ws.readyState===WebSocket.OPEN)ws.close();if(browser.exitCode===null)browser.kill();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
