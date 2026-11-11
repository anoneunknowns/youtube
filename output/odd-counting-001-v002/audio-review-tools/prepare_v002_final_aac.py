"""Extract actual delivery AAC once and bind 113 independent-recognition inputs."""
import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import wave

ROOT=Path('D:/codex_projects/youtube')
OUT=ROOT/'output/odd-counting-001-v002/audio-final-qa'
WORK=Path('D:/temp/odd-audio-production/final-aac-v002')
VIDEO=OUT.parent/'paspla-studio-odd-numbers-1-to-299-1080p.mp4'
TIMELINE=OUT.parent/'timeline.json'
SOURCE_MANIFEST=OUT.parent/'speech/measurements.json'
SOURCE_GATE=OUT.parent/'speech/speech-acceptance.json'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

assert VIDEO.exists(),'Wait for completed final MP4 before running'
assert sha(SOURCE_MANIFEST)=='f0f68370ac4e76d46f3a4cf206f6fade6369e05d60ce8ba86137c29474af647a'
assert sha(SOURCE_GATE)=='80fdf9c7d7eb7f11c06c00ac877e0eab57ef36466b5f861342578a3a45779159'
plan=json.loads(TIMELINE.read_text(encoding='utf-8'))
assert len(plan['voice_events'])==163
assert [e['decimal_value'] for e in plan['voice_events'] if e['type']=='number_voice']==list(range(1,300,2))
OUT.mkdir(exist_ok=False)
WORK.mkdir(exist_ok=False)
ffmpeg=shutil.which('ffmpeg')
full=WORK/'decoded-final-aac-stereo.wav'
subprocess.run([ffmpeg,'-v','error','-xerror','-nostdin','-n','-i',str(VIDEO),'-map','0:a:0','-c:a','pcm_s16le','-ar','48000','-ac','2',str(full)],check=True)
clips=OUT/'clips';clips.mkdir()
rows=[];sides=[];silence=[]
with wave.open(str(full),'rb') as track:
    rate=track.getframerate();n=track.getnframes()
    assert (rate,track.getnchannels(),track.getsampwidth())==(48000,2,2)
    assert abs(n-round(plan['duration_s']*rate))<=2048
    cursor=0
    for event in plan['voice_events']:
        start=round(event['start_s']*rate);stop=round(event['end_s']*rate)
        begin=max(0,start-round(.08*rate));end=min(n,stop+round(.08*rate))
        if begin>cursor:
            track.setpos(cursor);quiet=array.array('h',track.readframes(begin-cursor))
            silence.append({'begin_s':cursor/rate,'end_s':begin/rate,'peak_pcm16':max(map(abs,quiet),default=0)})
        cursor=end
        track.setpos(begin);data=array.array('h',track.readframes(end-begin));left=data[::2];right=data[1::2]
        destination=clips/f'{event["id"]}.wav'
        with wave.open(str(destination),'wb') as out:
            out.setparams((1,2,rate,0,'NONE','not compressed'));out.writeframes(left.tobytes())
        dot=sum(a*b for a,b in zip(left,right));el=sum(v*v for v in left);er=sum(v*v for v in right)
        corr=dot/math.sqrt(el*er) if el and er else None
        rows.append({'id':event['id'],'number':event.get('decimal_value'),'event_type':event['type'],
                     'spoken_text':event['text'],'text':event['text'],'path':str(destination),
                     'sha256':sha(destination),'duration_s':len(left)/rate,
                     'video_event_window_s':[event['start_s'],event['end_s']],
                     'video_extraction_window_s':[begin/rate,end/rate],
                     'event_offset_in_clip_s':(start-begin)/rate,
                     'source_channel':'decoded final AAC left; no averaging','sample_rate':rate,'sample_frames':len(left),
                     'adopted_source_sha256':event['source_sha256']})
        sides.append({'id':event['id'],'source_sha256':sha(destination),'left_right_correlation':corr,
                      'left_right_max_abs_difference_pcm16':max((abs(a-b) for a,b in zip(left,right)),default=0),
                      'peak_left_pcm16':max(map(abs,left),default=0),'peak_right_pcm16':max(map(abs,right),default=0),
                      'clipped_samples_left':sum(abs(v)>=32767 for v in left),
                      'clipped_samples_right':sum(abs(v)>=32767 for v in right)})
    track.setpos(cursor);quiet=array.array('h',track.readframes(n-cursor))
    silence.append({'begin_s':cursor/rate,'end_s':n/rate,'peak_pcm16':max(map(abs,quiet),default=0)})
origin={'video':{'path':str(VIDEO),'sha256':sha(VIDEO)},'timeline':{'path':str(TIMELINE),'sha256':sha(TIMELINE)},
        'source_manifest':{'path':str(SOURCE_MANIFEST),'sha256':sha(SOURCE_MANIFEST)},
        'source_gate':{'path':str(SOURCE_GATE),'sha256':sha(SOURCE_GATE)},
        'decoded_aac':{'sha256':sha(full),'sample_frames':n,'rate':48000,'channels':2},
        'method':'Decode actual final MP4 AAC once, extract each scheduled utterance with 80ms guards, retain left channel unchanged. No reference substitution, time stretch, gain, neighbor utterance or ASR prompting.',
        'utterances':163}
save('final-aac-manifest.json',{'schema_version':1,'measurement_status':'measured','numbers':[],'dialogue':rows,'origin':origin})
save('channel-and-silence-checks.json',{'origin':origin,'checks':sides,'minimum_left_right_correlation':min(r['left_right_correlation'] for r in sides),
    'clipped_samples':sum(r['clipped_samples_left']+r['clipped_samples_right'] for r in sides),
    'outside_event_guard_s':.08,'maximum_non_event_interior_peak_pcm16':max(r['peak_pcm16'] for r in silence),'non_event_intervals':silence})
print(json.dumps({'clips':163,'manifest':str(OUT/'final-aac-manifest.json'),'video_sha256':origin['video']['sha256']}))
