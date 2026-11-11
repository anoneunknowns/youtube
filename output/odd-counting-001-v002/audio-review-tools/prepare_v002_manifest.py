import copy,hashlib,json,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OLD=ROOT/'output/odd-counting-001-v001/speech';OUT=ROOT/'output/odd-counting-001-v002/speech';WORK=Path('D:/temp/odd-audio-production')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,obj):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
old=json.loads((OLD/'measurements.json').read_text(encoding='utf-8'))
assert sha(OLD/'measurements.json')=='39d2d195a25f774728281225d65612248b31c1e1e0f3187d8da26311743ae0a2'
assert sha(OLD/'speech-acceptance.json')=='972b7c84f6e871dd1ffda0d7d76ed47a7896bc8bddb5314e21ac5fd1da405aa3'
takes=json.loads((OUT/'candidates-v001/takes.json').read_text(encoding='utf-8'))
assert len(takes)==52
fresh={r['id']:r for r in takes}
def measured(t):
    p=Path(t['path']);assert sha(p)==t['sha256']
    with wave.open(str(p),'rb') as w:
        assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,24000)
        count=w.getnframes()
    row={'id':t['id'],'spoken_text':t['text'],'text':t['text'],'path':str(p.resolve()),'sha256':t['sha256'],
         'sample_frames':count,'duration_s':count/24000,'voice_id':'af_heart','generation_speed':.98,
         'generation':t['generation'],'provenance':{'type':'new-unreviewed-v002-candidate','sidecar':str(p)+'.json','sidecar_sha256':sha(str(p)+'.json')}}
    if 'number' in t:row['number']=t['number']
    return row
manifest={k:copy.deepcopy(v) for k,v in old.items() if k not in ('numbers','dialogue')}
manifest['revision_id']='odd-counting-v002'
manifest['acceptance_policy']='All163 current exact sources require fresh isolated ASR, unprompted CTC, edge/onset/tail signal checks and per-difference analytical review. Prior source gates alone approve none of these current rows.'
manifest['numbers']=copy.deepcopy(old['numbers'])+[measured(fresh[f'N{n:03d}']) for n in range(201,300,2)]
manifest['dialogue']=[measured(fresh[r['id']]) if r['id'] in ('I07','F02') else copy.deepcopy(r) for r in old['dialogue']]
assert len(manifest['numbers'])==150 and [r['number'] for r in manifest['numbers']]==list(range(1,300,2)) and len(manifest['dialogue'])==13
for r in manifest['numbers']+manifest['dialogue']:
    assert sha(r['path'])==r['sha256']
    with wave.open(r['path'],'rb') as w:assert w.getnframes()==r['sample_frames']
save('initial-measurements-v001.json',manifest)
asr=copy.deepcopy(manifest);asr['dialogue']=asr['numbers']+asr['dialogue'];asr['numbers']=[]
asr['inference_input_note']='Input-only flattening to dialogue bypasses legacy numeric CLI contiguous1..max requirement; raw unprompted recognized text will be independently compared to ID→number after inference.'
save('isolated-input-v001.json',asr)
for original,new in [('screen_initial_v002.py','screen_v002_sources.py'),('analyze_sources.py','analyze_v002_sources.py')]:
    text=(WORK/original).read_text(encoding='utf-8').replace('output/odd-counting-001-v001/speech','output/odd-counting-001-v002/speech')
    with (WORK/new).open('x',encoding='utf-8') as f:f.write(text)
print(json.dumps({'numbers':150,'dialogue':13,'numeric_duration_s':sum(r['duration_s'] for r in manifest['numbers']),
                  'changed_dialogue_duration_s':{r['id']:r['duration_s'] for r in manifest['dialogue'] if r['id'] in ('I07','F02')}}))
