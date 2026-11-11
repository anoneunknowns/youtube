// Sparse-cardinal isolated ASR for a newly measured production manifest.
// Recognition is unconstrained: expected words are used only after inference.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify, parseArgs } from 'node:util';
import path from 'node:path';
import { env, pipeline } from '@huggingface/transformers';

const exec = promisify(execFile);
const hash = b => createHash('sha256').update(b).digest('hex');
const SMALL = new Map(['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen'].map((s,i)=>[s,i]));
for(const [s,n] of Object.entries({twenty:20,thirty:30,forty:40,fifty:50,sixty:60,seventy:70,eighty:80,ninety:90})) SMALL.set(s,n);
function under100(a) {
  if(a.length===1 && SMALL.has(a[0])) return SMALL.get(a[0]);
  if(a.length===2 && SMALL.get(a[0])>=20 && SMALL.get(a[0])%10===0 && SMALL.get(a[1])>=1 && SMALL.get(a[1])<=9) return SMALL.get(a[0])+SMALL.get(a[1]);
  return null;
}
function parseNumber(s) {
  s=s.toLowerCase().trim().replace(/^[\s\"'“”‘’]+|[\s.!?,;:\"'“”‘’]+$/g,'');
  if(/^\d{1,4}$/.test(s)) return Number(s);
  let a=s.replace(/-/g,' ').split(/\s+/);
  if(a.at(-1)==='thousand') {const v=parseNumber(a.slice(0,-1).join(' '));return v!==null?v*1000:null;}
  const h=a.indexOf('hundred');
  if(h<0) return under100(a);
  if(h!==1 || !(SMALL.get(a[0])>=1 && SMALL.get(a[0])<=9)) return null;
  let rest=a.slice(2); if(rest[0]==='and') rest=rest.slice(1);
  const r=rest.length?under100(rest):0;
  return r!==null?100*SMALL.get(a[0])+r:null;
}
function normalizedDialogue(s) {
  const a=s.normalize('NFKC').toLowerCase().replace(/let['’]s/g,'let us').replace(/(?<=\d),(?=\d)/g,'').replace(/[^a-z0-9\s-]/g,' ').replace(/-/g,' ').trim().split(/\s+/);
  const out=[];
  for(let i=0;i<a.length;) {
    let chosen=null;
    for(let end=i+1;end<=Math.min(a.length,i+7);end++) {
      const v=parseNumber(a.slice(i,end).join(' '));
      if(v!==null) chosen={v,end};
    }
    if(chosen){out.push(String(chosen.v));i=chosen.end;} else out.push(a[i++]);
  }
  return out.join(' ');
}
async function main(){
 const {values}=parseArgs({options:{manifest:{type:'string'},out:{type:'string'},cache:{type:'string'},ffmpeg:{type:'string',default:'ffmpeg'},ids:{type:'string'},'self-test':{type:'boolean',default:false}}});
 if(values['self-test']){
   for(const [s,n] of [['three',3],['997.',997],['one hundred and one',101],['nine hundred ninety-seven',997],['one and five',null],['one thousand',1000]]) if(parseNumber(s)!==n) throw Error('number parser:'+s);
   if(normalizedDialogue('Two positive factors: one and five.')!==normalizedDialogue('2 positive factors, 1 and 5.')) throw Error('dialogue normalization');
   console.log(JSON.stringify({self_test:'PASS'}));return;
 }
 if(!values.manifest||!values.out||!values.cache)throw Error('--manifest --out --cache required');
 const manifestPath=path.resolve(values.manifest), rawManifest=await readFile(manifestPath), m=JSON.parse(rawManifest);
 if(m.schema_version!==1||m.measurement_status!=='measured')throw Error('Measured schema1 required');
 let rows=[...m.numbers.map(r=>({...r,role:'number'})),...m.dialogue.map(r=>({...r,role:'dialogue'}))];
 if(values.ids){const wanted=new Set(values.ids.split(','));rows=rows.filter(r=>wanted.has(r.id));}
 if(!rows.length||new Set(rows.map(r=>r.id)).size!==rows.length)throw Error('Empty or duplicate IDs');
 const cache=path.resolve(values.cache), manifest=JSON.parse(await readFile(new URL('./portable_models_manifest.json',import.meta.url)));
 for(const entry of manifest.models.asr.files){const b=await readFile(path.join(cache,manifest.models.asr.model_id,entry.path));if(b.length!==entry.bytes||hash(b)!==entry.sha256)throw Error('ASR model integrity:'+entry.path);}
 env.cacheDir=cache;env.allowRemoteModels=false;
 const recognizer=await pipeline('automatic-speech-recognition',manifest.models.asr.model_id,{dtype:'q8',device:'cpu',session_options:{intra_op_num_threads:2,inter_op_num_threads:1}});
 const results=[];
 try{
 for(const row of rows){
  const source=path.isAbsolute(row.path)?row.path:path.resolve(path.dirname(manifestPath),row.path), b=await readFile(source);
  if(hash(b)!==row.sha256)throw Error('Audio hash mismatch:'+row.id);
  const {stdout}=await exec(values.ffmpeg,['-v','error','-nostdin','-i',source,'-ac','1','-ar','16000','-f','f32le','pipe:1'],{encoding:'buffer',maxBuffer:32*1024*1024});
  const audio=new Float32Array(stdout.buffer.slice(stdout.byteOffset,stdout.byteOffset+stdout.byteLength));
  const padded=new Float32Array(audio.length+4800);padded.set(audio,2400);
  const r=await recognizer(padded,{max_new_tokens:128,do_sample:false,num_beams:1});
  const transcript=r.text?.trim()??'', interpreted=parseNumber(transcript);
  const matches=row.role==='number'?interpreted===row.number:normalizedDialogue(transcript)===normalizedDialogue(row.spoken_text);
  const result={id:row.id,role:row.role,number:row.number??null,expected_text:row.spoken_text,recognized_text:transcript,interpreted_number:interpreted,expected_normalized:row.role==='dialogue'?normalizedDialogue(row.spoken_text):String(row.number),recognized_normalized:row.role==='dialogue'?normalizedDialogue(transcript):String(interpreted),status:matches?'asr-match':'warning-review-required',source_path:source,source_sha256:row.sha256,duration_s:row.duration_s};
  results.push(result);if(!matches||results.length%20===0||results.length===rows.length)console.log(JSON.stringify({completed:results.length,total:rows.length,...result}));
 }
 }finally{await recognizer.dispose();}
 const warnings=results.filter(r=>r.status!=='asr-match');
 const report={schema_version:1,kind:'independent-sparse-cardinal-isolated-asr',source_manifest:manifestPath,source_manifest_sha256:hash(rawManifest),model:{...manifest.models.asr,dtype:'q8',runtime:'@huggingface/transformers@3.8.1'},method:{sampling_rate:16000,recognizer_only_edge_padding_s:.15,expected_text_used_as_prompt:false,neighboring_number_context_used:false,dialogue_comparison:'Case/punctuation, contractions and number-word/digit normalization only; missing lexical words remain warnings.'},summary:{clips:results.length,numbers:results.filter(r=>r.role==='number').length,dialogue:results.filter(r=>r.role==='dialogue').length,asr_matches:results.length-warnings.length,warnings:warnings.length},pronunciation_approved:false,limitations:'An isolated lexical match cannot prove articulation. Independent CTC and acoustic review are required. No human full listening claim.',warnings,results};
 await mkdir(path.dirname(path.resolve(values.out)),{recursive:true});await writeFile(values.out,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify(report.summary));
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
