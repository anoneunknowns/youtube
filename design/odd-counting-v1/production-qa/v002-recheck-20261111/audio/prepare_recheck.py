import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import wave

ROOT=Path('D:/codex_projects/youtube')
WORK=Path('D:/temp/odd-recheck-20261111/audio')
OUT=ROOT/'design/odd-counting-v1/production-qa/v002-recheck-20261111/audio'
DELIVERY=ROOT/'output/odd-counting-001-v002'
VIDEO=DELIVERY/'paspla-studio-odd-numbers-1-to-299-1080p.mp4'
TIMELINE=DELIVERY/'timeline.json'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def english(n):
    small=('zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen')
    tens=('','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety')
    if n<20:return small[n]
    if n<100:return tens[n//10]+('-'+small[n%10] if n%10 else '')
    return small[n//100]+' hundred'+(' '+english(n%100) if n%100 else '')

assert sha(VIDEO)=='7b9db137a55d8c35434b39573dd8d3fbf9d76860ac5716897942fd4a2d08710f'
plan=json.loads(TIMELINE.read_text(encoding='utf-8'))
events=plan['voice_events'];assert len(events)==163
assert [e['decimal_value'] for e in events if e['type']=='number_voice']==list(range(1,300,2))
OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
clips=WORK/'clips';clips.mkdir(exist_ok=False)
ffmpeg=shutil.which('ffmpeg')
decoded=WORK/'fresh-decoded-aac.wav';master=WORK/'fresh-master-pcm16.wav'
for src,dest in ((VIDEO,decoded),(DELIVERY/'master.wav',master)):
    subprocess.run([ffmpeg,'-v','error','-xerror','-nostdin','-n','-i',str(src),'-map','0:a:0','-ar','48000','-ac','2','-c:a','pcm_s16le',str(dest)],check=True)
with wave.open(str(decoded),'rb') as stream:
    rate=stream.getframerate();frame_count=stream.getnframes();aac=array.array('h',stream.readframes(frame_count))
with wave.open(str(master),'rb') as stream:
    base=array.array('h',stream.readframes(stream.getnframes()))
numbers=[];dialogue=[];checks=[];silence=[];cursor=0
for e in events:
    start=round(e['start_s']*rate);stop=round(e['end_s']*rate)
    begin=max(0,start-3840);end=min(frame_count,stop+3840)
    if begin>cursor:silence.append({'start_s':cursor/rate,'end_s':begin/rate,'peak_pcm16':max(map(abs,aac[cursor*2:begin*2]),default=0)})
    cursor=end
    samples=aac[begin*2:end*2];left=samples[::2];right=samples[1::2]
    path=clips/f'{e["id"]}.wav'
    with wave.open(str(path),'wb') as stream:
        stream.setparams((1,2,rate,0,'NONE','not compressed'));stream.writeframes(left.tobytes())
    expected=english(e['decimal_value']) if e['type']=='number_voice' else e['text']
    assert expected==e['text']
    row={'id':e['id'],'number':e.get('decimal_value'),'spoken_text':expected,'text':expected,'path':str(path),'sha256':sha(path),
         'duration_s':len(left)/rate,'sample_frames':len(left),'sample_rate':rate,'event_type':e['type'],
         'video_event_window_s':[e['start_s'],e['end_s']],'video_extraction_window_s':[begin/rate,end/rate],
         'event_offset_in_clip_s':(start-begin)/rate,'adopted_source_sha256':e['source_sha256']}
    (numbers if e['type']=='number_voice' else dialogue).append(row)
    channel_correlations=[]
    for channel in (0,1):
        x=aac[start*2+channel:stop*2:2];y=base[start*2+channel:stop*2:2]
        dot=sum(a*b for a,b in zip(x,y));xx=sum(a*a for a in x);yy=sum(b*b for b in y)
        channel_correlations.append(dot/math.sqrt(xx*yy))
    active=[i for i,v in enumerate(left) if abs(v)>104]
    checks.append({'id':e['id'],'clip_sha256':sha(path),'master_correlations':channel_correlations,
        'clipped_samples_both_channels':sum(abs(v)>=32767 for v in samples),
        'head_activity_margin_s':active[0]/rate,'tail_activity_margin_s':(len(left)-active[-1]-1)/rate,
        'first20ms_peak_pcm16':max(map(abs,left[:960]),default=0),'last20ms_peak_pcm16':max(map(abs,left[-960:]),default=0),
        'event_start_step_pcm16':abs(left[start-begin]-left[start-begin-1]),'event_end_step_pcm16':abs(left[stop-begin]-left[stop-begin-1])})
silence.append({'start_s':cursor/rate,'end_s':frame_count/rate,'peak_pcm16':max(map(abs,aac[cursor*2:]),default=0)})
origin={'video':{'path':str(VIDEO),'sha256':sha(VIDEO)},'timeline':{'path':str(TIMELINE),'sha256':sha(TIMELINE)},
        'master':{'path':str(DELIVERY/'master.wav'),'sha256':sha(DELIVERY/'master.wav')},
        'decoded_pcm_sha256':sha(decoded),'sample_rate':rate,'channels':2,'sample_frames':frame_count,
        'method':'New decode of final AAC; unchanged left channel, 80 ms exterior guards; expected numeric words independently constructed.'}
save('fresh-aac-manifest.json',{'schema_version':1,'measurement_status':'measured','numbers':numbers,'dialogue':dialogue,'origin':origin})
save('fresh-signal-checks.json',{'origin':origin,'events':checks,'silence':silence,
    'summary':{'events':len(checks),'silence_intervals':len(silence),'max_silence_peak_pcm16':max(r['peak_pcm16'] for r in silence),
        'min_master_channel_correlation':min(v for r in checks for v in r['master_correlations']),
        'clipped_samples':sum(r['clipped_samples_both_channels'] for r in checks),
        'min_head_activity_margin_s':min(r['head_activity_margin_s'] for r in checks),'min_tail_activity_margin_s':min(r['tail_activity_margin_s'] for r in checks)}})
print(json.dumps({'manifest':str(OUT/'fresh-aac-manifest.json'),'summary':{'numbers':len(numbers),'dialogue':len(dialogue)}}))
