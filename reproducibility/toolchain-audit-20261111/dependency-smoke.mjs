// Small native/JS smoke check. Does not download models or generate speech.
import { KokoroTTS } from 'kokoro-js';
import { Tensor, AutoTokenizer, StyleTextToSpeech2Model, AutoProcessor, Wav2Vec2ForCTC, pipeline } from '@huggingface/transformers';
import { phonemize } from 'phonemizer';
import sharp from 'sharp';
import * as ort from 'onnxruntime-node';
import { readFile } from 'node:fs/promises';
const lock=JSON.parse(await readFile(new URL('../../package-lock.json',import.meta.url),'utf8'));
const imports={KokoroTTS, AutoTokenizer,StyleTextToSpeech2Model,AutoProcessor,Wav2Vec2ForCTC,pipeline};
for(const [name,value] of Object.entries(imports))if(typeof value!=='function')throw Error(`${name} unavailable`);
const tensor=new Tensor('float32',new Float32Array([1,2,3,4]),[2,2]);
if(JSON.stringify(tensor.tolist())!=='[[1,2],[3,4]]')throw Error('Tensor roundtrip failed');
const resized=await sharp({create:{width:3,height:3,channels:4,background:'#123456'}}).resize(6,6).png().toBuffer({resolveWithObject:true});
if(resized.info.width!==6||resized.info.height!==6||!resized.data.length)throw Error('Sharp native PNG resize failed');
const phonemes=await phonemize('Two, three, five, seven.','en-us');
if(phonemes.length!==4||phonemes.some(x=>!x.trim()))throw Error('Phonemizer four-word check failed');
console.log(JSON.stringify({status:'PASS',node:process.version,npm_lock_versions:Object.fromEntries(['@huggingface/transformers','@huggingface/jinja','kokoro-js','onnxruntime-node','onnxruntime-web','protobufjs','sharp','phonemizer'].map(name=>[name,lock.packages[`node_modules/${name}`].version])),imports:Object.keys(imports),tensor_roundtrip:tensor.tolist(),sharp_resize:resized.info,phonemizer_input:'Two, three, five, seven.',phonemes,onnx_native_versions:ort.env.versions,scope:'Imports, native tensor, native image encode/resize, phonemization. No model inference, TTS/ASR/CTC, video rendering or production-media QA.'},null,2));
