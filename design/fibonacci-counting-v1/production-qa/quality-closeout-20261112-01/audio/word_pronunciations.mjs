// Expected US dictionary/stress labels, computed after acoustic inference.
import { readFile, writeFile } from 'node:fs/promises';
import { phonemize } from 'phonemizer';
import { createHash } from 'node:crypto';
const bytes=await readFile('design/fibonacci-counting-v1/narration.json');
const rows=JSON.parse(bytes);
const words=[...new Set(rows.flatMap(row=>row.text.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g)??[]))];
const results=[];
for(const word of words) results.push({word,ipa:String((await phonemize(word,'en-us')).join(' '))});
await writeFile(new URL('./expected-word-pronunciations.json',import.meta.url),JSON.stringify({kind:'dictionary-labels-not-observed-speech',source_script_sha256:createHash('sha256').update(bytes).digest('hex'),method:'eSpeak en-us isolated word phonemization computed only after independent ASR/CTC; stress labels are expected dictionary labels, not measured or asserted perceived stress.',results},null,2)+'\n',{flag:'wx'});
console.log({unique_words:words.length});
