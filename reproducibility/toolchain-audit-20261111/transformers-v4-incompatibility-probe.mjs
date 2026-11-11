// Reproduce in a SEPARATE candidate installation, never change the main lock:
// npm install --prefix <candidate-dir> @huggingface/transformers@4.3.2 kokoro-js@1.2.1
// node <this-file> <candidate-dir>
// Requires that candidate's native install scripts to have completed.
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
if(!process.argv[2])throw Error('Supply the separate v4 candidate installation directory');
const dir=path.resolve(process.argv[2]);
const src=path.join(dir,'node_modules/@huggingface/transformers/src');
// Source validator and Tensor must share the SAME source import graph.
const {Tensor:Tensor4}=await import(pathToFileURL(path.join(src,'utils/tensor.js')).href);
const {sessionRun}=await import(pathToFileURL(path.join(src,'models/session.js')).href);
const fromCandidate=createRequire(pathToFileURL(path.join(dir,'package.json')));
const resolveKokoro=createRequire(fromCandidate.resolve('kokoro-js'));
const {Tensor:Tensor3}=await import(pathToFileURL(resolveKokoro.resolve('@huggingface/transformers').replace('.cjs','.mjs')).href);
const inputs={input_ids:new Tensor4('int64',BigInt64Array.from([0n,1n,0n]),[1,3]),style:new Tensor3('float32',new Float32Array(256),[1,256]),speed:new Tensor3('float32',new Float32Array([.98]),[1])};
let error='';
try{await sessionRun({inputNames:['input_ids','style','speed']},inputs);}catch(e){error=e.message;}
const expected_rejection=/Missing the following inputs: style, speed/.test(error);
if(!expected_rejection)throw Error(`Expected the v4/3 Tensor mismatch, got: ${error}`);
console.log(JSON.stringify({candidate:'transformers4.3.2 with kokoro-js1.2.1 nested3.8.1',test:'v4 actual session input validator with tensors produced in the versions used by Kokoro',style_is_v4_tensor:inputs.style instanceof Tensor4,error,expected_rejection,model_inference_performed:false},null,2));
