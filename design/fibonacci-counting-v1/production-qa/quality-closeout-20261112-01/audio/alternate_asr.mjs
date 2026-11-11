// Fresh isolated lexical ASR for measured schema1 manifests, including millions.
// Expected text and neighboring terms never enter recognizer inference.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify, parseArgs } from 'node:util';
import path from 'node:path';
import { env, pipeline } from '@huggingface/transformers';

const exec = promisify(execFile);
const hash = b => createHash('sha256').update(b).digest('hex');
const SMALL = new Map('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(' ').map((s,i)=>[s,i]));
for (const [s,n] of Object.entries({twenty:20,thirty:30,forty:40,fifty:50,sixty:60,seventy:70,eighty:80,ninety:90})) SMALL.set(s,n);
function under100(a) {
  if(a.length===1 && SMALL.has(a[0])) return SMALL.get(a[0]);
  if(a.length===2 && SMALL.get(a[0])>=20 && SMALL.get(a[0])%10===0 && SMALL.get(a[1])>=1 && SMALL.get(a[1])<=9) return SMALL.get(a[0])+SMALL.get(a[1]);
  return null;
}
function under1000(a) {
  if(a.length===1&&/^\d{1,3}$/.test(a[0]))return Number(a[0]);
  if(!a.includes('hundred'))return under100(a);
  if(a[1]!=='hundred'||a.filter(x=>x==='hundred').length!==1||!(SMALL.get(a[0])>=1&&SMALL.get(a[0])<=9))return null;
  let rest=a.slice(2);if(rest[0]==='and')rest=rest.slice(1);
  const r=rest.length?under100(rest):0;
  return r!==null?SMALL.get(a[0])*100+r:null;
}
function parseNumber(text) {
  const text0=text.toLowerCase().trim().replace(/^[\s"'“”‘’]+|[\s.!?;:"'“”‘’]+$/g,'');
  if(/^(?:\d{1,3}(?:,\d{3})+|\d{1,9})$/.test(text0))return Number(text0.replaceAll(',',''));
  const a=text0.replace(/-/g,' ').split(/\s+/);let total=0;let from=0;let previous=Infinity;
  for(let i=0;i<a.length;i++){
    const scale={million:1_000_000,thousand:1000}[a[i]];
    if(!scale)continue;
    if(scale>=previous)return null;
    const v=under1000(a.slice(from,i));
    if(v===null||v===0)return null;
    total+=v*scale;from=i+1;previous=scale;
  }
  const remainder=a.slice(from);
  const tail=remainder.length?under1000(remainder):0;
  return tail!==null && (from||remainder.length)?total+tail:null;
}
function normalizedDialogue(text) {
  const replacements={"let's":'let us',"we'll":'we will',"we've":'we have',"it's":'it is',"don't":'do not',"that's":'that is'};
  let s=text.normalize('NFKC').toLowerCase().replace(/[’]/g,"'");
  for(const [a,b] of Object.entries(replacements))s=s.replaceAll(a,b);
  s=s.replace(/\bone's\b/g,'ones').replace(/\+/g,' plus ').replace(/=/g,' equals ');
  s=s.replace(/\bf\s*(\d+)\b/g,'f $1').replace(/(?<=\d),(?=\d)/g,'').replace(/[$]/g,' dollars ').replace(/[£]/g,' pounds ').replace(/[€]/g,' euros ');
  const out=[];
  // Sentence boundaries prevent “F forty. Two starting...” from becoming42.
  for(const sentence of s.split(/[.!?;:\n]+/)){
  if(!sentence.trim())continue;
  const a=sentence.replace(/[^a-z0-9\s-]/g,' ').replace(/-/g,' ').trim().split(/\s+/);
  for(let i=0;i<a.length;){
    let chosen=null;
    for(let end=i+1;end<=Math.min(a.length,i+18);end++){
      const v=parseNumber(a.slice(i,end).join(' '));if(v!==null)chosen={v,end};
    }
    if(chosen){out.push(String(chosen.v));i=chosen.end;}else{out.push(a[i]);i++;}
  }
  }
  return out.join(' ');
}
async function main(){
 const {values}=parseArgs({options:{manifest:{type:'string'},out:{type:'string'},cache:{type:'string'},ffmpeg:{type:'string',default:'ffmpeg'},ids:{type:'string'},'self-test':{type:'boolean',default:false}}});
 if(values['self-test']){
  for(const [s,n] of [['one',1],['1,597.',1597],['one hundred one',101],['one hundred and one',101],['one and one',null],['one thousand five hundred ninety-seven',1597],['one hundred two million three hundred thirty-four thousand one hundred fifty-five',102334155],['thirty-nine million eighty-eight thousand one hundred sixty-nine',39088169]])if(parseNumber(s)!==n)throw Error('number parser: '+s);
  if(normalizedDialogue('F zero and F forty.')!==normalizedDialogue('F0 and F40.'))throw Error('index normalization');
  if(normalizedDialogue('Eight plus thirteen equals')!==normalizedDialogue('8 plus 13 equals.'))throw Error('expression normalization');
  if(normalizedDialogue('One plus one equals')===normalizedDialogue('One one equals'))throw Error('missing operator masked');
  if(normalizedDialogue('F forty. Two starting values.')!==normalizedDialogue('F40. 2 starting values.'))throw Error('sentence-crossing number merge');
  if(normalizedDialogue('one hundred million')!==normalizedDialogue('100 million'))throw Error('hybrid scale spelling');
  console.log(JSON.stringify({self_test:'PASS'}));return;
 }
 if(!values.manifest||!values.out||!values.cache)throw Error('--manifest --out --cache required');
 const manifestPath=path.resolve(values.manifest),rawManifest=await readFile(manifestPath),m=JSON.parse(rawManifest);
 if(m.schema_version!==1||m.measurement_status!=='measured')throw Error('Measured schema1 required');
 let rows=[...m.numbers.map(r=>({...r,role:'number'})),...m.dialogue.map(r=>({...r,role:'dialogue'}))];
 if(values.ids){const wanted=new Set(values.ids.split(','));rows=rows.filter(r=>wanted.has(r.id));}
 if(!rows.length||new Set(rows.map(r=>r.id)).size!==rows.length)throw Error('Empty or duplicate IDs');
 const cache=path.resolve(values.cache),models=JSON.parse(await readFile(path.join(values.cache,'models.json')));
 for(const entry of models.models.asr.files){const b=await readFile(path.join(cache,models.models.asr.model_id,entry.path));if(b.length!==entry.bytes||hash(b)!==entry.sha256)throw Error('ASR model integrity:'+entry.path);}
 env.cacheDir=cache;env.allowRemoteModels=false;
 const recognizer=await pipeline('automatic-speech-recognition',models.models.asr.model_id,{dtype:'q8',device:'cpu',session_options:{intra_op_num_threads:2,inter_op_num_threads:1}});
 const results=[];
 try{
  for(const row of rows){
   const source=path.isAbsolute(row.path)?row.path:path.resolve(path.dirname(manifestPath),row.path),bytes=await readFile(source);
   if(hash(bytes)!==row.sha256)throw Error('Audio hash mismatch:'+row.id);
   const {stdout}=await exec(values.ffmpeg,['-v','error','-nostdin','-i',source,'-ac','1','-ar','16000','-f','f32le','pipe:1'],{encoding:'buffer',maxBuffer:32*1024*1024});
   const audio=new Float32Array(stdout.buffer.slice(stdout.byteOffset,stdout.byteOffset+stdout.byteLength)),padded=new Float32Array(audio.length+4800);padded.set(audio,2400);
   const r=await recognizer(padded,{max_new_tokens:192,do_sample:false,num_beams:1,return_timestamps:'word'});
   const transcript=r.text?.trim()??'',interpreted=parseNumber(transcript);
   const matches=row.role==='number'?interpreted===row.number:normalizedDialogue(transcript)===normalizedDialogue(row.spoken_text);
   const result={id:row.id,index:row.index??null,role:row.role,number:row.number??null,expected_text:row.spoken_text,recognized_text:transcript,word_timings:r.chunks??[],interpreted_number:interpreted,expected_normalized:row.role==='dialogue'?normalizedDialogue(row.spoken_text):String(row.number),recognized_normalized:row.role==='dialogue'?normalizedDialogue(transcript):String(interpreted),status:matches?'asr-match':'warning-review-required',source_path:source,source_sha256:row.sha256,duration_s:row.duration_s};
   results.push(result);if(!matches||results.length%20===0||results.length===rows.length)console.log(JSON.stringify({completed:results.length,total:rows.length,...result}));
  }
 }finally{await recognizer.dispose();}
 const warnings=results.filter(r=>r.status!=='asr-match');
 const report={schema_version:1,kind:'new-alternate-whisper-base-en-isolated-closeout-ASR',source_manifest:manifestPath,source_manifest_sha256:hash(rawManifest),model:{...models.models.asr,dtype:'q8',runtime:'@huggingface/transformers@3.8.1'},method:{sampling_rate:16000,recognizer_only_edge_padding_s:.15,word_timestamps:true,expected_text_used_as_prompt:false,neighboring_number_context_used:false,dialogue_comparison:'Case/punctuation, explicitly listed contractions, F-index spelling and cardinal word/digit normalization. Missing operators or lexical words remain warnings.'},summary:{clips:results.length,numbers:results.filter(r=>r.role==='number').length,dialogue:results.filter(r=>r.role==='dialogue').length,asr_matches:results.length-warnings.length,warnings:warnings.length},pronunciation_approved:false,limitations:'An isolated lexical match cannot prove articulation. Independent CTC and acoustic review are required; this is not a full-listening record.',warnings,results};
 await mkdir(path.dirname(path.resolve(values.out)),{recursive:true});await writeFile(values.out,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(report.summary));
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
