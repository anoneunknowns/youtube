"""Independent audit of the encoded 0..200 video, without production verifier imports."""
from array import array
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave

ROOT=Path('D:/codex_projects/youtube')
OUT=ROOT/'output/four-base-counting-001-v002-to-200'
WORK=Path(__file__).parent
VIDEO=OUT/'paspla-studio-four-ways-to-count-0-to-200-1080p.mp4'
FFMPEG=Path('D:/dev/FFmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe')
RATE=48000
ERRORS=[]
CHECKS=Counter()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def test(condition,label):
    CHECKS[label]+=1
    if not condition: ERRORS.append(label)

def local_path(text):
    path=Path(text)
    return path if path.is_absolute() else ROOT/path

def norm(text):
    return ' '.join(re.sub('[^a-z0-9 ]',' ',text.lower().replace("let's",'let us')).split())

SMALL='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS=dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(),range(20,100,10)))
def cardinal(text):
    clean=norm(text)
    if re.fullmatch(r'[0-9]+',clean): return int(clean)
    words=clean.replace('-',' ').split()
    if words in (['a','hundred'],['one','hundred']): return 100
    if len(words)>2 and words[0] in ('a','one','two') and words[1]=='hundred':
        tail=words[2:]
        if tail and tail[0]=='and': tail=tail[1:]
        if not tail: return None
        rest=cardinal(' '.join(tail))
        return (100 if words[0] in ('a','one') else 200)+rest if rest is not None and 0<rest<100 else None
    if words==['two','hundred']: return 200
    if len(words)==1:
        if words[0] in SMALL: return SMALL.index(words[0])
        return TENS.get(words[0])
    if len(words)==2 and words[0] in TENS and words[1] in SMALL[1:10]:
        return TENS[words[0]]+SMALL.index(words[1])
    return None

plan=read(OUT/'timeline.json')
record=read(ROOT/'design/four-base-counting-v1/production-run-v002.json')
video_sha=digest(VIDEO)
test(video_sha==record['video_sha256']=='3a84d9aa0861fd16958676140c3c8506fbdf305679f405b021be7d35f1fd886a','current_video_identity')
speech=[e for e in plan['events'] if e['type']!='sfx']
test(len(speech)==215,'speech_coverage')
events=sorted(plan['events'],key=lambda e:e['start_s'])
test(len(events)==216,'all_event_coverage')
asr=read(OUT/'encoded-speech-review/fresh-asr.json')
asr_manifest=Path(asr['source_manifest'])
test(digest(asr_manifest)==asr['source_manifest_sha256'],'asr_manifest_hash')
test(asr['method']['expected_text_used_as_recognition_prompt'] is False,'unprompted_asr')
rows={Path(r['path']).stem:r for r in asr['results']}
test(len(rows)==len(asr['results'])==215 and set(rows)=={e['id'] for e in speech},'asr_exact_event_coverage')
warnings=[]
for event in speech:
    row=rows[event['id']]
    test(digest(Path(row['path']))==row['source_sha256'],'asr_clip_hash')
    test(abs(row['source_duration_s']-(event['end_s']-event['start_s']))<1/RATE,'asr_clip_duration')
    test(norm(row['expected_text'])==norm(event['text']),'asr_expected_matches_schedule')
    if event['type']=='number_voice':
        test(cardinal(event['text'])==event['decimal_value'],'planned_cardinal_meaning')
        test(cardinal(row['recognized_text'])==event['decimal_value'],'recognized_cardinal_meaning')
    else:
        test(norm(row['recognized_text'])==norm(event['text']),'recognized_dialogue_meaning')
    if row['status']!='asr-match':
        warnings.append({'id':event['id'],'recognized':row['recognized_text'],'expected':event['text'],'same_value':cardinal(row['recognized_text'])==event.get('decimal_value')})
test({r['id'] for r in warnings}=={'I04-TEN','N000'} and all(r['same_value'] for r in warnings),'only_numeric_spelling_asr_warnings')

library=ROOT/'assets/library/audio/speech/kokoro-af-heart/v002'
gate=read(library/'speech-acceptance.json')
test(gate['accepted'] is True and not gate['unresolved'],'extended_source_gate_accepted')
for reference in gate['inputs'].values():
    if reference is not None: test(digest(local_path(reference['path']))==reference['sha256'],'extended_gate_evidence_hash')
accepted={r['number']:r for r in gate['results'] if r['role']=='number'}
phonemes=read(library/'isolated-phonemes.json')
phoneme_rows={r['number']:r for r in phonemes['results'] if r['role']=='number'}
notes=read(library/'qa/pronunciation-decision-notes.json')
note_rows={r['number']:r for r in notes['results'] if r['role']=='number'}
source_details=[]
evidence_checked={}
for value in range(128,201):
    source=plan['numeric_sources'][str(value)]
    accepted_row=accepted[value]
    path=ROOT/source['path']
    source_sha=digest(path)
    test(source_sha==source['sha256']==accepted_row['sha256']==phoneme_rows[value]['source_sha256']==note_rows[value]['source_sha256'],'extended_source_and_phoneme_identity')
    test(accepted_row['accepted'] and accepted_row['pronunciation_decision']=='pass' and note_rows[value]['decision']=='pass','extended_pronunciation_accepted')
    test(cardinal(source['spoken_text'])==value and cardinal(accepted_row['expected_text'])==value,'extended_source_text_meaning')
    for proof in source['pronunciation_evidence']:
        p=local_path(proof['path'])
        if p not in evidence_checked:
            evidence_checked[p]=digest(p)
        test(evidence_checked[p]==proof['sha256'],'extended_phoneme_proof_hash')
    with wave.open(str(path),'rb') as f:
        test((f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,24000),'extended_source_pcm_format')
        test(f.getnframes()==source['sample_frames'] and abs(f.getnframes()/24000-source['duration_s'])<1e-9,'extended_source_pcm_length')
    source_details.append({'number':value,'source_sha256':source_sha,'recognized_phonemes':phoneme_rows[value]['recognized_phonemes'],'review_category':note_rows[value]['category']})

count=[e for e in events if e.get('phase')=='count' and e['type']=='number_voice']
test([e['decimal_value'] for e in count]==list(range(201)),'number_order')
gaps=Counter()
for prev,event in zip(count,count[1:]):
    gap=round(event['start_s']*RATE)-round(prev['end_s']*RATE)
    test(gap==(5 if prev['decimal_value'] in (8,16,64) else 2)*RATE,'exact_scheduled_completed_number_gap')
    gaps[gap/RATE]+=1
for event,state in zip(count,plan['counted_states'],strict=True):
    test(state['decimal_value']==event['decimal_value'] and state['source_sha256']==event['source_sha256'],'state_source_sync')
    test(round(event['start_s']*RATE)-round(state['estimated_display_start_s']*RATE)==5760,'display_leads_voice_120ms')
    test(state['estimated_display_start_s']<event['start_s']<event['end_s']<state['estimated_display_end_s'],'speech_contained_in_its_display')

def run_job(name,args):
    command=[str(FFMPEG),'-hide_banner','-nostdin','-v','error','-xerror','-n',*args]
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    (WORK/f'{name}.stderr.txt').write_bytes(result.stderr)
    test(result.returncode==0 and not result.stderr,f'{name}_fresh_decode')
    return command

with ThreadPoolExecutor(max_workers=2) as pool:
    actual_job=pool.submit(run_job,'aac',['-i',str(VIDEO),'-map','0:a:0','-ar','48000','-ac','2','-c:a','pcm_s16le','-f','s16le',str(WORK/'aac-stereo.s16le')])
    reference_job=pool.submit(run_job,'master',['-i',str(OUT/'master.wav'),'-map','0:a:0','-af','volume=0.8dB:precision=double','-ar','48000','-ac','2','-c:a','pcm_s16le','-f','s16le',str(WORK/'master-gained-stereo.s16le')])
    commands=[actual_job.result(),reference_job.result()]

def load_pcm(path):
    samples=array('h')
    with path.open('rb') as stream: samples.fromfile(stream,path.stat().st_size//2)
    return samples

actual=load_pcm(WORK/'aac-stereo.s16le')
reference=load_pcm(WORK/'master-gained-stereo.s16le')
expected_frames=round(plan['duration_s']*RATE)
test(len(actual)==len(reference)==expected_frames*2,'fresh_pcm_exact_sample_count')
maximum=max(map(abs,actual))
clips=sum(v in (-32768,32767) for v in actual)
test(clips==0 and maximum<32767,'stereo_pcm_no_digital_clipping')
left,right=actual[::2],actual[1::2]
ref_left,ref_right=reference[::2],reference[1::2]
diff_max=max(abs(a-b) for a,b in zip(left,right,strict=True))
ref_diff_max=max(abs(a-b) for a,b in zip(ref_left,ref_right,strict=True))
test(diff_max<=2 and ref_diff_max==0,'dual_mono_channels_preserved')

BLOCK=240 # Independent 5ms RMS grid, not the production waveform comparator.
def envelope(samples):
    return [math.sqrt(sum(x*x for x in samples[i:i+BLOCK])/len(samples[i:i+BLOCK])) for i in range(0,len(samples),BLOCK)]
act_env=envelope(left)
ref_env=envelope(ref_left)
lag_scores=[]
for lag in range(-6,7):
    a=act_env[max(0,lag):len(act_env)+min(0,lag)]
    b=ref_env[max(0,-lag):len(ref_env)+min(0,-lag)]
    score=sum(x*y for x,y in zip(a,b,strict=True))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    lag_scores.append((lag,score))
best_lag,best_score=max(lag_scores,key=lambda r:r[1])
test(best_lag==0 and best_score>.995,'zero_global_audio_delay_5ms_grid')

boundaries=[]
for event in events:
    first=max(0,math.floor(event['start_s']*RATE/BLOCK)-6)
    last=min(len(act_env),math.ceil(event['end_s']*RATE/BLOCK)+6)
    active=[i for i in range(first,last) if act_env[i]>32]
    expected=[i for i in range(first,last) if ref_env[i]>32]
    test(bool(active) and bool(expected),'all_events_audibly_nonempty')
    onset=(active[0]-expected[0])*BLOCK/RATE
    tail=(active[-1]-expected[-1])*BLOCK/RATE
    test(abs(onset)<=.03 and abs(tail)<=.03,'event_onset_and_tail_preserved_within_30ms')
    boundaries.append({'id':event['id'],'onset_delta_s':onset,'tail_delta_s':tail})

silences=[]
cursor=0
for event in events+[{'id':'END','start_s':plan['duration_s'],'end_s':plan['duration_s']}]:
    begin=cursor+round(.03*RATE)
    end=round(event['start_s']*RATE)-round(.03*RATE)
    if begin<end:
        peak=max(map(abs,left[begin:end]))
        test(peak==0,'fresh_silent_interiors_exact_zero')
        silences.append({'before':event['id'],'frames':end-begin,'peak_pcm16':peak})
    cursor=round(event['end_s']*RATE)

report={
    'status':'pass' if not ERRORS else 'fail',
    'checked_at_utc':datetime.now(timezone.utc).isoformat(),
    'scope':'Independent raw ASR/gate audit and fresh AAC stereo decode; no production verifier imports and no original outputs changed.',
    'video_sha256':video_sha,'timeline_sha256':digest(OUT/'timeline.json'),
    'checks_total':sum(CHECKS.values()),'checks':dict(CHECKS),'errors':ERRORS,
    'raw_asr_rows':len(rows),'semantic_meaning_matches':len(speech) if not any('meaning' in e for e in ERRORS) else None,
    'raw_asr_warnings':warnings,'extended_sources_checked':len(source_details),
    'source_phoneme_details':source_details,'count_gaps_s':dict(gaps),
    'fresh_decoded_frames':len(actual)//2,'fresh_decoded_duration_s':len(actual)/2/RATE,
    'peak_pcm16':maximum,'clipped_samples':clips,
    'stereo_channel_max_delta_pcm16':diff_max,'master_channel_max_delta_pcm16':ref_diff_max,
    'master_to_aac_envelope_best_lag_s':best_lag*BLOCK/RATE,'master_to_aac_envelope_cosine':best_score,
    'onset_tail_checks':len(boundaries),'maximum_absolute_onset_delta_s':max(abs(r['onset_delta_s']) for r in boundaries),
    'maximum_absolute_tail_delta_s':max(abs(r['tail_delta_s']) for r in boundaries),'event_boundaries':boundaries,
    'fresh_silence_interiors_checked':len(silences),'silence_records':silences,
    'commands':commands,
    'limitations':['ASR and phoneme evidence do not replace full human listening.','5ms RMS boundary checks use a conservative 30ms AAC guard.'],
}
(WORK/'independent-audio-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','checks_total','errors','semantic_meaning_matches','extended_sources_checked','fresh_decoded_frames','peak_pcm16','clipped_samples','stereo_channel_max_delta_pcm16','master_to_aac_envelope_best_lag_s','master_to_aac_envelope_cosine','maximum_absolute_onset_delta_s','maximum_absolute_tail_delta_s','fresh_silence_interiors_checked']}))
raise SystemExit(bool(ERRORS))
