import hashlib,json,shutil
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');EP=ROOT/'output/odd-counting-001-v002';SP=EP/'speech';WORK=Path('D:/temp/odd-audio-production')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ref(p):
    p=Path(p).resolve();return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
manifest=json.loads((SP/'measurements.json').read_text(encoding='utf-8'));gate=json.loads((SP/'speech-acceptance.json').read_text(encoding='utf-8'))
assert sha(SP/'measurements.json')=='f0f68370ac4e76d46f3a4cf206f6fade6369e05d60ce8ba86137c29474af647a'
assert sha(SP/'speech-acceptance.json')=='80fdf9c7d7eb7f11c06c00ac877e0eab57ef36466b5f861342578a3a45779159'
assert gate['accepted'] and gate['summary']['accepted']==163 and not gate['unresolved']
refs={}
def add(p):r=ref(p);refs[r['path']]=r
def visit(x):
    if isinstance(x,dict):
        if 'path' in x and 'sha256' in x:
            p=Path(x['path']);p=p if p.is_absolute() else ROOT/p
            assert sha(p)==x['sha256'];add(p)
        for v in x.values():visit(v)
    elif isinstance(x,list):
        for v in x:visit(v)
visit(gate)
for name in ('measurements.json','speech-acceptance.json','initial-measurements-v001.json','isolated-input-v001.json','isolated-asr-raw-v001.json','isolated-asr.json','isolated-phonemes-v001.json','pronunciation-review.json','dialogue-window-fit-v001.json','generation-jobs.json','candidates-v001/manifest.json','candidates-v001/takes.json'):
    add(SP/name)
for p in (SP/'candidates-v001').glob('*.wav.json'):add(p)
for p in (SP/'candidates-v001').glob('*.wav'):add(p)
tools=EP/'audio-review-tools';tools.mkdir(exist_ok=False)
for name in ('prepare_v002_jobs.py','prepare_v002_manifest.py','screen_v002_sources.py','analyze_v002_sources.py','extended_v002_acoustics.py','finalize_v002_acceptance.py','inventory_v002_source_proof.py'):
    target=tools/name;shutil.copyfile(WORK/name,target);add(target)
for name in ('portable_speech_candidates.mjs','verify_speech.mjs','portable_verify_phonemes.mjs','review_speech_acceptance.mjs','verify_terminal_tails.py','classify_terminal_phonemes.mjs'):
    add(ROOT/'tools'/name)
add(ROOT/'output/even-counting-001-v001/speech/acoustic_formants.py')
add(ROOT/'design/odd-counting-v1/script-and-sound-cues-v002.txt')
clips=[]
for r in manifest['numbers']+manifest['dialogue']:
    source=ref(r['path']);assert source['sha256']==r['sha256'];clips.append({'id':r['id'],'number':r.get('number'),'spoken_text':r['spoken_text'],'sample_frames':r['sample_frames'],'duration_s':r['duration_s'],**source})
data={'schema_version':1,'kind':'durable-source-speech-proof-inventory','status':'all-references-rehashed',
      'scope':'Accepted163 sources for odd-counting-v002. Every current source was freshly independently recognized and reviewed; an older gate alone does not approve it. Final delivery AAC is audited separately. No full human listening is claimed.',
      'accepted_manifest':ref(SP/'measurements.json'),'accepted_gate':ref(SP/'speech-acceptance.json'),'active_pronunciation_receipt':ref(SP/'pronunciation-review.json'),
      'summary':{'accepted_clips':163,'number_clips':150,'dialogue_clips':13,'unresolved':0,'numeric_pcm_duration_s':sum(r['duration_s'] for r in manifest['numbers']),'new_generation_jobs':52},
      'durable_clips':clips,'proof_generation_and_tool_files':list(refs.values())}
with (SP/'source-proof-inventory.json').open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'clips':len(clips),'proof_generation_and_tool_files':len(refs),'out':str(SP/'source-proof-inventory.json'),'sha256':sha(SP/'source-proof-inventory.json')}))
