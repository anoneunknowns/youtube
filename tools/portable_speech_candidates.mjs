import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { parseArgs } from 'node:util';
import path from 'node:path';
import { KokoroTTS } from 'kokoro-js';
import { env, AutoTokenizer, StyleTextToSpeech2Model } from '@huggingface/transformers';

function encode(samples, rate) {
  const threshold = 10 ** (-50 / 20);
  let first = 0, last = samples.length - 1;
  while (first <= last && Math.abs(samples[first]) < threshold) first++;
  while (last >= first && Math.abs(samples[last]) < threshold) last--;
  if (first >= last) throw new Error('No speech');
  first = Math.max(0, first - Math.round(rate * .015));
  last = Math.min(samples.length - 1, last + Math.round(rate * .015));
  const n = last - first + 1;
  const b = Buffer.alloc(44 + n * 2);
  b.write('RIFF'); b.writeUInt32LE(36 + n * 2, 4); b.write('WAVEfmt ', 8);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22);
  b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28); b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34); b.write('data', 36); b.writeUInt32LE(n * 2, 40);
  let peak = 0;
  for (let i = first; i <= last; i++) peak = Math.max(peak, Math.abs(samples[i]));
  const gain = peak > .85 ? .85 / peak : 1;
  for (let i = 0; i < n; i++) {
    const fade = Math.min(1, i / (rate * .002), (n - 1 - i) / (rate * .002));
    b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, samples[first + i] * gain * fade)) * 32767), 44 + i * 2);
  }
  return { buffer: b, duration_s: n / rate, trim: {raw_duration_s:samples.length/rate,leading_s:first/rate,trailing_s:(samples.length-last-1)/rate,peak_normalization_gain:gain} };
}
async function main() {
  const {values}=parseArgs({options:{jobs:{type:'string'},out:{type:'string'},cache:{type:'string'},help:{type:'boolean',default:false}}});
  if(values.help){console.log('Usage: node tools/portable_speech_candidates.mjs --jobs jobs.json --out <new-folder> --cache <prepared-model-cache>\nGenerates unreviewed WAV candidates, takes.json and an ASR manifest.json for jobs with text. Use portable_models.py --model kokoro first.');return;}
  if(!values.jobs||!values.out)throw new Error('--jobs and --out are required; all generated candidates require independent review');
  if(!values.cache)throw new Error('--cache is required; prepare it with portable_models.py');
  env.cacheDir = path.resolve(values.cache);
  env.allowRemoteModels = false;
  const [model, tokenizer] = await Promise.all([
    StyleTextToSpeech2Model.from_pretrained('onnx-community/Kokoro-82M-v1.0-ONNX', {dtype:'fp32',device:'cpu',session_options:{intraOpNumThreads:4,interOpNumThreads:1}}),
    AutoTokenizer.from_pretrained('onnx-community/Kokoro-82M-v1.0-ONNX'),
  ]);
  const tts = new KokoroTTS(model,tokenizer);
  const out = path.resolve(values.out);
  await mkdir(out,{recursive:true});
  const takes = JSON.parse(await readFile(values.jobs,'utf8'));
  if(!Array.isArray(takes)||takes.length===0||takes.some(t=>!/^[a-zA-Z0-9_-]+$/.test(t.id)||(!t.text&&!t.phonemes)))throw new Error('Each job requires a safe id and text or explicit phonemes');
  const rows=[];
  for (const take of takes) {
    const options={voice:'af_heart',speed:.98};
    const a = take.phonemes
      ? await tts.generate_from_ids(tts.tokenizer(take.phonemes,{truncation:true}).input_ids,options)
      : await tts.generate(take.text,options);
    const result=encode(a.audio,a.sampling_rate);
    const file=`${out}/${take.id}.wav`;
    await writeFile(file,result.buffer,{flag:'wx'});
    const row={...take,path:file,duration_s:result.duration_s,sha256:createHash('sha256').update(result.buffer).digest('hex'),trim:result.trim,generation:{provider:'local-kokoro',model_id:'onnx-community/Kokoro-82M-v1.0-ONNX',voice_id:'af_heart',speed:.98,dtype:'fp32',status:'unreviewed-candidate'}};
    await writeFile(file+'.json',JSON.stringify(row,null,2)+'\n',{flag:'wx'});
    rows.push(row);console.log(JSON.stringify(row));
  }
  await writeFile(out+'/takes.json',JSON.stringify(rows,null,2)+'\n',{flag:'wx'});
  const dialogue=rows.filter(row=>typeof row.text==='string'&&row.text.trim()).map(row=>({
    id:row.id,path:path.basename(row.path),spoken_text:row.text,duration_s:row.duration_s,sha256:row.sha256,
  }));
  if(dialogue.length){
    await writeFile(out+'/manifest.json',JSON.stringify({schema_version:1,measurement_status:'measured',numbers:[],dialogue},null,2)+'\n',{flag:'wx'});
  }
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
