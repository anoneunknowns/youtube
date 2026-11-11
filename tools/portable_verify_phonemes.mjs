// Independent acoustic phoneme recognition. This is a review aid, not a human listening claim.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify, parseArgs } from 'node:util';
import path from 'node:path';
import { env, AutoProcessor, Wav2Vec2ForCTC } from '@huggingface/transformers';
import { phonemize } from 'phonemizer';

const exec = promisify(execFile);
const MODEL='onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX';
const REVISION='c69750f5043e5e1f8a71ab95dd3b98338c280c92';
const hash=b=>createHash('sha256').update(b).digest('hex');
async function main() {
  const {values}=parseArgs({options:{manifest:{type:'string'},takes:{type:'string'},out:{type:'string'},numbers:{type:'string'},cache:{type:'string'},ffmpeg:{type:'string',default:'ffmpeg'},help:{type:'boolean',default:false}}});
  if(values.help){console.log('Usage: node tools/portable_verify_phonemes.mjs --manifest manifest.json --out <new-report.json> --cache <prepared-cache> [--ffmpeg ffmpeg]\nAlternatively use --takes takes.json. Prepare the phoneme model with portable_models.py first. Automated CTC is review evidence, not pronunciation approval.');return;}
  if (!values.out || (!values.manifest && !values.takes)) throw new Error('--out and --manifest or --takes required');
  const manifestBytes=values.manifest?await readFile(values.manifest):null;
  const manifest=manifestBytes?JSON.parse(manifestBytes):null;
  let rows=manifest?[...manifest.numbers.map(x=>({...x,role:'number'})),...manifest.dialogue.map(x=>({...x,role:'dialogue'}))]:[];
  if(values.takes) rows.push(...JSON.parse(await readFile(values.takes,'utf8')).map(x=>({...x,role:'candidate',spoken_text:x.spoken_text??x.text??x.phonemes})));
  if(values.numbers){const wanted=new Set(values.numbers.split(',').map(Number));rows=rows.filter(x=>wanted.has(x.number));}
  if(!values.cache)throw new Error('--cache is required; prepare it with portable_models.py');
  env.cacheDir=path.resolve(values.cache);env.allowRemoteModels=false;
  const modelPath=path.join(env.cacheDir,MODEL,'onnx/model_quantized.onnx');
  const modelHash=hash(await readFile(modelPath));
  if(modelHash!=='3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120')throw new Error('Model integrity mismatch');
  const [processor,model]=await Promise.all([
    AutoProcessor.from_pretrained(MODEL),
    Wav2Vec2ForCTC.from_pretrained(MODEL,{dtype:'q8',device:'cpu',session_options:{intraOpNumThreads:4,interOpNumThreads:1}}),
  ]);
  const vocab=JSON.parse(await readFile(path.join(env.cacheDir,MODEL,'vocab.json'),'utf8'));
  const idToToken=Object.fromEntries(Object.entries(vocab).map(([t,i])=>[i,t]));
  const results=[];
  for(const row of rows){
    const sourcePath=path.isAbsolute(row.path)?row.path:path.resolve(values.manifest?path.dirname(values.manifest):'.',row.path);
    const source=await readFile(sourcePath);
    if(row.sha256&&hash(source)!==row.sha256)throw new Error('Audio checksum mismatch');
    const {stdout}=await exec(values.ffmpeg,['-v','error','-i',sourcePath,'-ac','1','-ar','16000','-f','f32le','pipe:1'],{encoding:'buffer',maxBuffer:32*1024*1024,windowsHide:true});
    const raw=new Float32Array(stdout.buffer.slice(stdout.byteOffset,stdout.byteOffset+stdout.byteLength));
    // Normalization belongs to processor; no lexical prompt, no adjacent numbers.
    const inputs=await processor(raw);
    const {logits}=await model(inputs);
    const frames=logits.dims[1], width=logits.dims[2], tokens=[];
    let previous=-1;
    for(let f=0;f<frames;f++){
      let best=0;
      for(let j=1;j<width;j++)if(logits.data[f*width+j]>logits.data[f*width+best])best=j;
      if(best!==0&&best!==previous){
        const max=logits.data[f*width+best];let denominator=0;
        for(let j=0;j<width;j++)denominator+=Math.exp(logits.data[f*width+j]-max);
        tokens.push({token:idToToken[best]??`<${best}>`,start_s:Number((f*.02).toFixed(3)),end_s:Number((f*.02+.025).toFixed(3)),probability:1/denominator});
      }else if(best!==0&&tokens.length)tokens.at(-1).end_s=Number((f*.02+.025).toFixed(3));
      previous=best;
    }
    const text=tokens.map(x=>x.token).filter(x=>!x.startsWith('<')).join(' ');
    const expected=String((await phonemize(row.spoken_text,'en-us')).join(' '));
    const result={role:row.role,number:row.number??null,id:row.id??null,expected_text:row.spoken_text,expected_espeak:expected,source_path:sourcePath,source_sha256:hash(source),duration_s:raw.length/16000,recognized_phonemes:text,tokens};
    results.push(result);
    console.log(JSON.stringify({role:row.role,number:row.number,id:row.id,expected,recognized:text}));
  }
  const report={schema_version:1,kind:'isolated-phoneme-asr',source_manifest_sha256:manifestBytes?hash(manifestBytes):null,model:{id:MODEL,revision:REVISION,dtype:'q8',sha256:modelHash,license:'Apache-2.0'},method:'Independent 16 kHz CTC phoneme recognition, no expected text or neighbor-number prompt; eSpeak expected labels are computed only after inference. Approximate 20ms timestamps. Automated evidence, not proof of perfect pronunciation.',results};
  await mkdir(path.dirname(path.resolve(values.out)),{recursive:true});
  await writeFile(values.out,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({completed:true,count:results.length,out:values.out}));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
