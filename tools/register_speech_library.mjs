// Adopt reviewed candidate sources into an immutable, portable library version.
// This does not approve pronunciation. Run isolated checks and the acceptance gate afterward.
import {readFile,writeFile,mkdir,cp,stat} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
const sha=b=>createHash('sha256').update(b).digest('hex');
async function main(){
  const {values}=parseArgs({options:{source:{type:'string'},corrections:{type:'string'},out:{type:'string'},'prior-profile':{type:'string'}}});
  if(!values.source||!values.corrections||!values.out||!values['prior-profile'])throw new Error('source, corrections, out, prior-profile required');
  const sourceBytes=await readFile(values.source),source=JSON.parse(sourceBytes);
  const correctionsBytes=await readFile(values.corrections), corrections=JSON.parse(correctionsBytes);
  const patches=new Map(corrections.map(x=>[x.number,x]));
  if(patches.size!==corrections.length)throw new Error('Duplicate correction number');
  const out=path.resolve(values.out);
  try{await stat(out);throw new Error('Refusing to replace existing library version');}catch(e){if(e.code!=='ENOENT')throw e;}
  await mkdir(path.join(out,'clips'),{recursive:true});
  await cp(path.join(values['prior-profile'],'licenses'),path.join(out,'licenses'),{recursive:true,errorOnExist:true,force:false});
  for(const name of ['model-files.json','model-card.md','kokoro-js-source-readme.md'])await cp(path.join(values['prior-profile'],name),path.join(out,name),{errorOnExist:true,force:false});
  const provenance=[];
  async function adopt(row,role){
    const replacement=role==='number'?patches.get(row.number):null;
    const input=replacement??row;
    const inputPath=path.isAbsolute(input.path)?input.path:path.resolve(path.dirname(replacement?values.corrections:values.source),input.path);
    const bytes=await readFile(inputPath),hash=sha(bytes);
    if(hash!==input.sha256)throw new Error('Source checksum mismatch');
    if(bytes.toString('ascii',0,4)!=='RIFF'||bytes.toString('ascii',8,12)!=='WAVE'||bytes.readUInt16LE(20)!==1||bytes.readUInt16LE(22)!==1||bytes.readUInt32LE(24)!==24000||bytes.readUInt16LE(34)!==16||bytes.toString('ascii',36,40)!=='data')throw new Error('Expected canonical PCM16 mono 24k WAV');
    const duration=bytes.readUInt32LE(40)/2/24000;
    if(Math.abs(duration-input.duration_s)>1/24000)throw new Error('Duration measurement mismatch');
    const name=role==='number'?`number-${String(row.number).padStart(3,'0')}-${hash.slice(0,12)}.wav`:`dialogue-${hash.slice(0,16)}.wav`;
    const result={...row,...input,spoken_text:row.spoken_text,path:`clips/${name}`,sha256:hash,duration_s:duration,measurement_status:'measured'};
    delete result.role;
    if(replacement){
      delete result.cache_key;
      result.trim={method:'reviewed-context-extraction',edge_fade_ms:replacement.generation?.edge_fade_ms??2,silence_pad_ms:replacement.generation?.silence_pad_ms??15};
    }
    if(replacement?.generation?.context_source_path){
      const context=await readFile(replacement.generation.context_source_path);
      if(sha(context)!==replacement.generation.context_source_sha256)throw new Error('Context source checksum mismatch');
      const contextName=`provenance/context-${row.number}-${sha(context).slice(0,12)}.wav`;
      await mkdir(path.join(out,'provenance'),{recursive:true});
      await writeFile(path.join(out,contextName),context,{flag:'wx'});
      result.generation={...replacement.generation,context_source_path:contextName,acceptance:'requires-current-speech-acceptance-receipt'};
    }
    if(result.generation?.source_take_path){
      if(result.generation.source_take_sha256!==hash)throw new Error('Explicit source take differs from adopted clip; retain and register its full source before adoption');
      result.generation={...result.generation,source_take_path:result.path};
    }
    await writeFile(path.join(out,result.path),bytes,{flag:'wx'});
    await writeFile(path.join(out,result.path+'.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
    provenance.push({role,number:row.number??null,spoken_text:row.spoken_text,source_sha256:hash,previous_source_sha256:row.sha256,changed:hash!==row.sha256,origin:replacement?'context-generated-corrected-take':'unchanged-original-take',generation:result.generation??null});
    return result;
  }
  const numbers=[];for(const row of source.numbers)numbers.push(await adopt(row,'number'));
  const dialogue=[];for(const row of source.dialogue)dialogue.push(await adopt(row,'dialogue'));
  if([...patches.keys()].some(n=>!numbers.some(x=>x.number===n)))throw new Error('Correction outside source manifest');
  const manifest={...source,numbers,dialogue,library_id:'kokoro-af-heart-en-us-v002',storage_policy:'Immutable version; portable clip paths relative to this manifest. Only reuse with a current successful speech-acceptance.json.',measurement_method:'Actual adopted PCM sample count / 24000 Hz. No playback-speed change. Individual generation provenance recorded separately.'};
  await writeFile(path.join(out,'measurements.json'),JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
  await writeFile(path.join(out,'provenance.json'),JSON.stringify({schema_version:1,source_manifest_sha256:sha(sourceBytes),correction_manifest_sha256:sha(correctionsBytes),clips:provenance},null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({out,numbers:numbers.length,dialogue:dialogue.length,changed:provenance.filter(x=>x.changed).map(x=>x.number),status:'registered-pending-acceptance'}));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
