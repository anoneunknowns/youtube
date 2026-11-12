"""Prepare, adopt and schedule Collatz speech without altering previous productions.

Every PCM source and its decisions are hash-bound. Natural speech is never
stretched; ordinary within-tour number boundaries retain exactly2seconds.
"""
from __future__ import annotations
import argparse
from array import array
import hashlib,json,math,re,shutil,subprocess,wave
from pathlib import Path
from difflib import SequenceMatcher
try:
 from .build_prime_episode import digest,local,resolve,save_new,srt_time,chapter
 from .build_fibonacci_episode import mix_truepeak_scalars
 from .portable_speech_library import resolve_reference,export_library
except ImportError:
 from build_prime_episode import digest,local,resolve,save_new,srt_time,chapter
 from build_fibonacci_episode import mix_truepeak_scalars
 from portable_speech_library import resolve_reference,export_library
ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'design/collatz-counting-v1'
OUT=ROOT/'output/collatz-counting-001-v001'
RATE,FPS=24000,30
VOICE={'voice_id':'af_heart','generation_speed':.98,'dtype':'fp32','model_id':'onnx-community/Kokoro-82M-v1.0-ONNX','sample_rate':24000,'channels':1}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def samp(s):return round(s*RATE)
def ref(p):return {'path':local(p),'sha256':digest(p)}
def authored():
 p=DESIGN/'script/script.json';rows=read(p)['events']
 assert len(rows)==143 and len({r['id'] for r in rows})==143
 return rows

def prepare(out):
 speech=out/'speech';speech.mkdir(parents=True,exist_ok=True)
 export_library(ROOT/'assets/library/audio/speech/kokoro-af-heart/v002',speech/'reuse-verification')
 candidates={r['cue_id']:r for r in read(DESIGN/'math/timing-candidates.json')['candidates']}
 jobs,reuse=[],[];verified={}
 for cue in authored():
  c=candidates.get(cue['id'])
  if not c or c['status']!='existing-measured-source-candidate':
   jobs.append({'id':cue['id'],'text':cue['text']});continue
  src=c['source'];p=resolve(src['path']);g=resolve(src['original_gate_path'])
  if digest(p)!=src['sha256'] or digest(g)!=src['original_gate_sha256']:raise ValueError('Reuse source/gate changed')
  gate=read(g)
  if not gate.get('accepted') or gate.get('unresolved'):raise ValueError('Reuse gate not fully accepted')
  approvals=[a for a in gate['results'] if a.get('number')==cue['value'] and a.get('accepted') and a.get('sha256',a.get('source_sha256'))==src['sha256']]
  if len(approvals)!=1:raise ValueError(f'No individual reuse approval:{cue["id"]}')
  for item in list(gate.get('inputs',{}).values())+approvals[0].get('pronunciation_evidence',[]):
   if not isinstance(item,dict) or 'path' not in item or 'sha256' not in item:continue
   q=resolve_reference(item['path'])
   if not q.is_file():q=resolve(item['path'],g.parent)
   key=(str(q),item['sha256'])
   if key not in verified:
    if digest(q)!=item['sha256']:raise ValueError(f'Reuse proof changed:{q}')
    verified[key]=True
  dest=speech/'reused'/f'{cue["id"]}.wav';dest.parent.mkdir(exist_ok=True)
  with dest.open('xb') as f:f.write(p.read_bytes())
  reuse.append({'id':cue['id'],'source_path':local(p),'path':local(dest),'sha256':src['sha256'],'spoken_text':cue['text'],'number':cue['value'],'original_gate':ref(g),'original_individual_decision':approvals[0],'bytes_preserved':digest(dest)==src['sha256']})
 save_new(speech/'jobs-v001.json',jobs)
 save_new(speech/'source-reuse-record.json',{'kind':'collatz-source-reuse','status':'gate-source-proof-verified','new_pronunciation_assessment':False,'sources':reuse,'occurrences':len(reuse),'unique_sources':len({r['sha256'] for r in reuse}),'proof_files':len(verified)})
 print(json.dumps({'jobs':len(jobs),'reuse':len(reuse),'jobs_path':local(speech/'jobs-v001.json')}))

def assemble(out,candidate_dir,selection_path=None,manifest_name='measurements.json'):
 speech=out/'speech';takes=read(candidate_dir/'takes.json');chosen={x['id']:x for x in takes}
 if selection_path:
  for x in read(selection_path):chosen[x['id']]=x
 reused={r['id']:r for r in read(speech/'source-reuse-record.json')['sources']}
 numbers,dialogue=[],[]
 for cue in authored():
  if cue['id'] in chosen:
   take=chosen[cue['id']];p=resolve(take['path']);origin='new-generated-candidate'
   if take['text']!=cue['text']:raise ValueError('Generation text changed')
   sha=take['sha256']
  elif cue['id'] in reused:
   take=reused[cue['id']];p=resolve(take['path']);sha=take['sha256'];origin='inherited-accepted-source'
  else:raise ValueError(f'Missingsource:{cue["id"]}')
  if digest(p)!=sha:raise ValueError('Source hash mismatch')
  with wave.open(str(p)) as w:
   assert(w.getframerate(),w.getnchannels(),w.getsampwidth())==(RATE,1,2)
   frames=w.getnframes()
  row={'id':cue['id'],'spoken_text':cue['text'],'path':str(p.resolve()),'sha256':sha,'duration_s':frames/RATE,'sample_frames_24k':frames,'origin':origin}
  if cue['kind']=='count':row.update(number=cue['value'],index=cue['index'],sequence_id=cue['sequence_id']);numbers.append(row)
  else:dialogue.append(row)
 manifest={'schema_version':1,'measurement_status':'measured','kind':'collatz-143-cue-source-manifest','voice':VOICE,'numbers':numbers,'dialogue':dialogue,'source_script':ref(DESIGN/'script/script.json'),'source_reuse_record':ref(speech/'source-reuse-record.json'),'candidates':ref(candidate_dir/'takes.json'),'source_acceptance':'not-yet-adopted'}
 path=speech/manifest_name;save_new(path,manifest)
 print(json.dumps({'manifest':local(path),'numbers':len(numbers),'dialogue':len(dialogue),'speech_sum_s':sum(r['duration_s'] for r in numbers+dialogue),'full_duration_s':sum(r['duration_s'] for r in numbers+dialogue)+262.9}))
 return manifest

def sources_from_manifest(path,gate_path=None):
 m=read(path)
 if m.get('measurement_status')!='measured' or m['voice']!=VOICE:raise ValueError('Changed voice or nonmeasured sources')
 rows={r['id']:r for r in m['numbers']+m['dialogue']}
 expected={r['id']:r for r in authored()}
 if set(rows)!=set(expected) or len(m['numbers'])!=129:raise ValueError('Wrong speech coverage')
 if gate_path:
  gate=read(gate_path)
  if not gate.get('accepted') or gate.get('unresolved') or gate.get('source_manifest_sha256')!=digest(path):raise ValueError('Exact accepted gate required')
  approvals={r['id']:r for r in gate['results']}
  for item in gate['inputs'].values():
   if isinstance(item,dict) and 'path' in item and digest(resolve(item['path']))!=item['sha256']:raise ValueError('Changed gate evidence')
 else:approvals={}
 result={}
 for ident,row in rows.items():
  cue=expected[ident];p=resolve(row['path'],path.parent)
  if digest(p)!=row['sha256'] or row['spoken_text']!=cue['text']:raise ValueError('Source bytes/text changed')
  with wave.open(str(p)) as w:
   if (w.getframerate(),w.getnchannels(),w.getsampwidth())!=(RATE,1,2):raise ValueError('Changed PCM format')
   frames=w.getnframes()
  if abs(frames/RATE-row['duration_s'])>1/RATE:raise ValueError('Wrong measured duration')
  if gate_path:
   a=approvals.get(ident,{})
   if not a.get('accepted') or a.get('source_sha256')!=row['sha256'] or a.get('failures'):raise ValueError('Missing individual approval')
  result[ident]={**row,'text':row['spoken_text'],'source_path':local(p),'source_sha256':row['sha256'],'sample_frames_24k':frames,'duration_s':frames/RATE}
 return result

SCENE_ROLES={'I01':'welcome','I02':'positive-integers','I03':'even-demo','I04':'odd-demo','I05':'values-not-volume','I06':'seed-seven','B01':'new-seed-27','T27_001':'intermediate-81','T27_036':'four-digits','T27_077':'peak-9232','T27_103':'familiar-ending','O01':'stop-and-continue-loop','O02':'unproved-conjecture','O03':'goodbye'}
def make_plan(sources,adopted=False):
 rows=authored();events=[];cursor=samp(.8)
 for i,cue in enumerate(rows):
  src=sources[cue['id']];start=cursor;end=start+src['sample_frames_24k'];is_count=cue['kind']=='count'
  e={**src,'id':cue['id'],'kind':'count' if is_count else 'narration','authored_kind':cue['kind'],'scene':cue['id'] if not is_count else 'count','scene_role':SCENE_ROLES.get(cue['id'],'count'),'text':cue['text'],'spoken_text':cue['text'],'subtitle_text':cue['text'],'start_s':start/RATE,'end_s':end/RATE,'start_sample_24k':start,'end_sample_24k':end,'sequence_id':cue.get('sequence_id'),'seed':cue.get('seed'),'index':cue.get('index'),'value':cue.get('value'),'display':cue.get('display')}
  if is_count:e.update(result_start_s=(start-samp(.12))/RATE,result_display_s=(start-samp(.12))/RATE,term_ordinal=cue['term_ordinal'],step_number=cue['step_number'])
  events.append(e)
  nxt=rows[i+1] if i+1<len(rows) else None
  if not nxt:gap=.8
  elif is_count:gap=2 if nxt['kind']=='count' else .5
  elif cue['kind'] in ('explanation','chapter_bridge'):gap=1.5
  else:gap=.6
  cursor=end+samp(gap)
 duration=cursor/RATE
 counts=[e for e in events if e['kind']=='count'];by_id={e['id']:e for e in events};states=[]
 for j,e in enumerate(counts):
  prev=counts[j-1] if j else None;same=prev and prev['sequence_id']==e['sequence_id']
  preceding=events[events.index(e)-1] if events.index(e) else None
  if same:
   origin=preceding['end_s'] if preceding and preceding['authored_kind']=='explanation' else prev['end_s']
   operation=origin+.22
   e.update(operation_start_s=operation,calculation_start_s=operation,previous_value=prev['value'],previous_index=prev['index'],incoming_rule='even' if prev['value']%2==0 else 'odd',intermediate_value=prev['value']//2 if prev['value']%2==0 else prev['value']*3)
  else:e.update(operation_start_s=None,calculation_start_s=None,previous_value=None,previous_index=None,incoming_rule=None,intermediate_value=None)
  next_count=counts[j+1] if j+1<len(counts) and counts[j+1]['sequence_id']==e['sequence_id'] else None
  display_end=next_count['result_start_s'] if next_count else by_id['B01' if e['seed']==7 else 'O01']['start_s']-.12
  e['display_end_s']=display_end
  states.append({**{k:e.get(k) for k in ['id','sequence_id','seed','index','value','display','text','term_ordinal','step_number','result_start_s','operation_start_s','previous_value','previous_index','incoming_rule','intermediate_value']},'voice_event_id':e['id'],'voice_start_s':e['start_s'],'voice_end_s':e['end_s'],'start_s':e['result_start_s'],'end_s':display_end,'display_start_s':e['result_start_s'],'display_end_s':display_end,'progress_commit_s':e['end_s']})
 visual=[]
 for i,e in enumerate(events):
  start=0 if i==0 else e.get('result_start_s',e['start_s']-.12)
  nxt=events[i+1] if i+1<len(events) else None
  end=(nxt.get('result_start_s',nxt['start_s']-.12) if nxt else duration)
  visual.append({'scene':e['scene'],'scene_role':e['scene_role'],'kind':e['kind'],'mode':e['authored_kind'],'voice_event_id':e['id'],'start_s':start,'end_s':end,'sequence_id':e['sequence_id'],'index':e['index'],'value':e['value']})
 plan={'schema_version':1,'kind':'measured-collatz-timeline','episode_id':'collatz-counting-001','revision_id':'collatz-counting-v001','status':'accepted-measured-speech' if adopted else 'unreviewed-measured-candidate-draft','speech_adopted':adopted,'fps':FPS,'width':1920,'height':1080,'duration_s':duration,'duration':duration,'duration_frames':math.ceil(duration*FPS-1e-8),'frame_count':math.ceil(duration*FPS-1e-8),'voice_events':events,'events':events,'counted_states':states,'visual_segments':visual,'scenes':visual,'teaching':[v for v in visual if v['mode']=='explanation'],'counted_values':129,'voice_event_count':143,'seed_ranges':[{'seed':7,'terms':17,'steps':16},{'seed':27,'terms':112,'steps':111}],'source_sample_rate_hz':RATE,'master_sample_rate_hz':48000,'master_channels':2,'voice_sum_s':sum(e['duration_s'] for e in events),'fixed_silence_s':262.9,'source_script':ref(DESIGN/'script/script.json'),'source_math':ref(DESIGN/'math/verified-sequences.json'),'timing':{'normal_end_to_next_start_s':2,'result_display_lead_s':.12,'explicit_extended_boundary_after_ids':['C27_001','C27_036','C27_077','C27_103'],'teaching_boundary':'0.5s + explanation speech +1.5s','intro_gap_s':.6,'bridge':'0.5s + B01 speech +1.5s; separate journeys, no1to27 operation'},'bgm':False,'sound_effects':[],'intro':{'start_s':0,'end_s':counts[0]['result_start_s'],'fade_in_s':.6},'finale':{'start_s':by_id['O01']['start_s']-.12,'end_s':duration,'fade_last_s':.8}}
 validate(plan)
 return plan

def validate(plan):
 rows=plan['voice_events'];by_id={r['id']:r for r in rows};counts=[r for r in rows if r['kind']=='count']
 if len(rows)!=143 or len(counts)!=129 or len(by_id)!=143:raise ValueError('Wrong utterance count')
 truth=read(DESIGN/'math/verified-sequences.json')
 for seq in truth['sequences']:
  es=[e for e in counts if e['seed']==seq['seed']]
  if [e['value'] for e in es]!=[t['value'] for t in seq['terms']]:raise ValueError('Mathorder mismatch')
  for a,b in zip(es,es[1:]):
   extra=by_id.get('T27_'+f'{a["index"]:03d}') if a['seed']==27 else None
   expected=2+(extra['duration_s'] if extra else 0)
   if abs(b['start_s']-a['end_s']-expected)>1/RATE:raise ValueError('Changednumber boundary')
   if b['operation_start_s']>=b['result_start_s']:raise ValueError('Operation mustprecede result')
 for a,b in zip(rows,rows[1:]):
  if a['end_sample_24k']>b['start_sample_24k']:raise ValueError('Speech overlap')
 if abs(plan['duration_s']-plan['voice_sum_s']-262.9)>1e-7:raise ValueError('Wrong fixedsilence sum')
 if plan['duration_s']<480:raise ValueError('Measured natural speech below8minutes; revise scope withroot')
 return {'passed':True,'speech_events':143,'counted_values':129,'normal_boundaries':123,'teaching_boundaries':4,'duration_s':plan['duration_s'],'frames':plan['duration_frames'],'voice_sum_s':plan['voice_sum_s'],'fixed_silence_s':262.9}

def deliveries(plan,out):
 captions=out/'captions';captions.mkdir(exist_ok=True)
 text='\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n' for i,e in enumerate(plan['voice_events'],1))
 for p in [out/'subtitles.srt',out/'english-captions.srt',captions/'english.srt']:
  with p.open('x',encoding='utf-8') as f:f.write(text)
 e={r['id']:r for r in plan['voice_events']}
 marks=[(0,'Welcome to Collatz Waterworks'),(e['C7_000']['result_start_s'],'Start with seven'),(e['C27_000']['result_start_s'],'A new trip from twenty-seven'),(e['T27_036']['start_s'],'The first four-digit value'),(e['T27_077']['start_s'],'The highest value: 9,232'),(e['T27_103']['start_s'],'A familiar ending'),(plan['finale']['start_s'],'One, and an unsolved question')]
 stamps=[int(t) for t,_ in marks]
 if any(b-a<10 for a,b in zip(stamps,stamps[1:])) or plan['duration_s']-stamps[-1]<10:raise ValueError('Chapters require at least10seconds each')
 chapters='\n'.join(f'{chapter(t)} {label}' for t,label in marks)+'\n'
 title='Collatz Sequence: Watch the Formula Work | 7 and 27 to 1 | Num-Num Numbers'
 description=('Follow our hedgehog through Collatz Waterworks and watch two rules generate every next value.\n\n'
 'For a positive whole number n: if n is even, use n ÷ 2. If n is odd, use 3n + 1. We count every term, without combining steps. '
 'The trip from 7 reaches 1 in 16 steps (17 terms). The trip from 27 reaches 1 in 111 steps (112 terms), peaking at 9,232. '
 'Each trip stops at its first 1. Continuing from 1 would repeat 1 → 4 → 2 → 1.\n\n'
 'These two finite trips do not prove convergence for every positive integer. The general Collatz conjecture remains unproved. '
 'Intermediate values such as 81 in 27 × 3 = 81, then 81 + 1 = 82 belong inside a calculation; they are not extra sequence terms. '
 'The mirrors show number values, not physical water volumes.\n\n'
 'Natural American English counting. No background music or sound effects.\n\n'
 'Mathematical background: Terence Tao, Almost all orbits of the Collatz map attain almost bounded values: https://arxiv.org/abs/1909.03562\n\n'
 'CHAPTERS\n'+chapters+'\nPaspla Studio — Num-Num Numbers\n#CollatzSequence #MathForKids #NumberPatterns\n')
 for name,value in [('chapters.txt',chapters),('youtube-title.txt',title+'\n'),('youtube-description.txt',description),('upload-details.txt',title+'\n\n'+description)]:
  with(out/name).open('x',encoding='utf-8')as f:f.write(value)


def gate_sources(manifest_path,asr_path,phonemes_path,acoustics_path,decisions_path,out_path):
 m=read(manifest_path);asr=read(asr_path);ctc=read(phonemes_path);ac=read(acoustics_path);decisions=read(decisions_path)
 if any(d.get('source_manifest_sha256')!=digest(manifest_path) for d in [asr,ctc,ac,decisions]):raise ValueError('Fresh evidence mustbind manifest')
 src={r['id']:r for r in m['numbers']+m['dialogue']};a={r['id']:r for r in asr['results']};c={r['id']:r for r in ctc['results']};w={r['id']:r for r in ac['results']};d={r['id']:r for r in decisions['results']}
 if any(set(t)!=set(src) for t in [a,c,w,d]):raise ValueError('Full143 evidence/decision coverage required')
 results=[]
 for ident,row in src.items():
  failures=[];decision=d[ident]
  for t in [a[ident],c[ident],w[ident],decision]:
   if t.get('source_sha256')!=row['sha256']:failures.append('evidence-source-hash-mismatch')
  if not decision.get('accepted') or not decision.get('notes') or decision.get('unresolved'):failures.append('individual-decision-not-complete')
  if a[ident]['status']!='asr-match' and not decision.get('asr_warning_resolution'):failures.append('isolated-asr-warning-not-resolved')
  if w[ident]['clipped_samples']:failures.append('source-clipping')
  if row['origin']=='inherited-accepted-source' and not decision.get('inherited_gate'):failures.append('missing-inherited-proof')
  results.append({'id':ident,'number':row.get('number'),'expected_text':row['spoken_text'],'source_path':row['path'],'source_sha256':row['sha256'],'origin':row['origin'],'accepted':not failures,'failures':failures,'asr_status':a[ident]['status'],'asr_transcript':a[ident]['recognized_text'],'expected_espeak':c[ident]['expected_espeak'],'recognized_phonemes':c[ident]['recognized_phonemes'],'decision':decision})
 unresolved=[r for r in results if not r['accepted']]
 gate={'schema_version':1,'kind':'collatz-hash-bound-source-speech-acceptance','accepted':not unresolved,'source_manifest_sha256':digest(manifest_path),'scope':'Exact-source inherited acceptance plus fresh isolated lexical/CTC/acoustic agent review. This does not claim human whole-listening or guarantee flawless articulation. Final AAC needs separate verification.','inputs':{'manifest':ref(manifest_path),'isolated_asr':ref(asr_path),'isolated_phonemes':ref(phonemes_path),'acoustics':ref(acoustics_path),'decisions':ref(decisions_path),'reuse_record':ref(OUT/'speech/source-reuse-record.json'),**decisions.get('inputs',{})},'policy':{'context_asr_can_clear_pronunciation':False,'human_whole_listening_performed':False,'source_files_modified':False,'per_cue_source_binding':True},'summary':{'clips':len(results),'numbers':129,'dialogue':14,'new_sources':sum(r['origin']=='new-generated-candidate' for r in results),'inherited_occurrences':sum(r['origin']=='inherited-accepted-source' for r in results),'unresolved':len(unresolved)},'unresolved':unresolved,'results':results}
 save_new(out_path,gate)
 if unresolved:raise ValueError(f'{len(unresolved)} sources unresolved')
 print(json.dumps(gate['summary']))
 return gate


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','assemble','draft','build','gate']);p.add_argument('--out-dir',type=Path,default=OUT);p.add_argument('--candidates',type=Path);p.add_argument('--selection',type=Path);p.add_argument('--manifest-name',default='measurements.json');p.add_argument('--manifest',type=Path,default=OUT/'speech/measurements.json');p.add_argument('--gate',type=Path,default=OUT/'speech/speech-acceptance.json');p.add_argument('--asr',type=Path);p.add_argument('--phonemes',type=Path);p.add_argument('--acoustics',type=Path);p.add_argument('--decisions',type=Path);p.add_argument('--draft-path',type=Path,default=OUT/'speech/measured-draft-timeline.json');p.add_argument('--audio-out',type=Path,default=OUT/'audio-build');p.add_argument('--ffmpeg',default='ffmpeg');a=p.parse_args();out=a.out_dir.resolve()
 if a.command=='prepare':prepare(out)
 elif a.command=='assemble':assemble(out,a.candidates.resolve(),a.selection,a.manifest_name)
 elif a.command=='gate':gate_sources(a.manifest,a.asr,a.phonemes,a.acoustics,a.decisions,a.gate)
 else:
  sources=sources_from_manifest(a.manifest,None if a.command=='draft' else a.gate);plan=make_plan(sources,a.command=='build');plan['speech_manifest']=ref(a.manifest)
  if a.command=='draft':save_new(a.draft_path,plan);print(json.dumps(validate(plan)));return
  audio=a.audio_out.resolve();audio.mkdir(parents=True,exist_ok=True)
  for name in ['master.wav','timeline.json','build-record.json']:
   if(audio/name).exists():raise FileExistsError('Refusingtooverwrite audio-build')
  levels=mix_truepeak_scalars(plan,audio,a.ffmpeg,-19)
  plan.update(master_audio=levels,master=levels,audio=levels,master_path=levels['path'],speech_acceptance=ref(a.gate))
  save_new(audio/'timeline.json',plan);deliveries(plan,audio)
  save_new(audio/'build-record.json',{'kind':'collatz-audio-production-build','status':'accepted-sources-measured-timeline-master-built','timeline':ref(audio/'timeline.json'),'master':levels,'speech_manifest':ref(a.manifest),'speech_gate':ref(a.gate),'validation':validate(plan),'video_rendered':False,'source_files_modified':False,'builder':ref(Path(__file__))})
  print(json.dumps({'duration_s':plan['duration_s'],'frames':plan['duration_frames'],'master':levels['after']}))
if __name__=='__main__':main()
