"""Independent whole-frame presence scan and boundary-frame evidence."""
from datetime import datetime, timezone
from hashlib import file_digest
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageStat

ROOT=Path('D:/codex_projects/youtube')
DELIVERY=ROOT/'output/four-base-counting-001-v002-to-200'
VIDEO=DELIVERY/'paspla-studio-four-ways-to-count-0-to-200-1080p.mp4'
OUT=Path(__file__).parent/'additional'
OUT.mkdir(exist_ok=True)
FFMPEG='D:/dev/FFmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe'
plan=json.loads((DELIVERY/'timeline.json').read_text(encoding='utf-8'))
def first_frame(t):
    return math.ceil(t*30-1e-7)
def checksum(path):
    with path.open('rb') as f:return file_digest(f,'sha256').hexdigest()
before=checksum(VIDEO)

# At 1/10 resolution these independent crop boxes contain only numeric fields.
# A full-video scan checks that every numeric field remains present, not merely
# the state boundaries sampled by the production glyph verifier.
boxes=[(55,27,138,41),(55,46,138,61),(55,66,138,80),(55,86,138,100)]
size=(192,108)
command=[FFMPEG,'-nostdin','-v','error','-xerror','-i',str(VIDEO),'-map','0:v:0','-an',
         '-vf','scale=192:108:flags=area,format=gray','-fps_mode','passthrough',
         '-f','rawvideo','-pix_fmt','gray','pipe:1']
start=first_frame(30)
fade_start=first_frame(plan['finale']['estimated_start_s']+10)
minimum=[999999]*4
empty=[]
black=[]
count=0
fade_means=[]
with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as proc:
    while raw:=proc.stdout.read(size[0]*size[1]):
        if len(raw)!=size[0]*size[1]:raise RuntimeError('Incomplete grayscale frame')
        image=Image.frombytes('L',size,raw)
        if image.getextrema()[1]<20:black.append(count)
        if start<=count<fade_start:
            for row,box in enumerate(boxes):
                hist=image.crop(box).histogram()
                dark=sum(hist[:180])
                minimum[row]=min(minimum[row],dark)
                if dark<8:empty.append({'frame':count,'row':row,'dark_pixels':dark})
        if count>=fade_start:fade_means.append(ImageStat.Stat(image).mean[0])
        count+=1
    stderr=proc.stderr.read().decode('utf-8','replace')
    code=proc.wait()
if code or stderr:raise RuntimeError(f'Whole-frame decoder {code}: {stderr}')
expected_frames=math.ceil(plan['duration_s']*30-1e-7)
assert count==expected_frames==19871
assert not empty and not black,(empty[:5],black[:5])
assert all(b>=a-.5 for a,b in zip(fade_means,fade_means[1:]))

probes=[]
for value in (128,160,192,200):
    boundary=first_frame(plan['counted_states'][value]['estimated_display_start_s'])
    for offset in (-2,-1,0,1,2):
        probes.append({'frame':boundary+offset,'label':f'{value-1} to {value}, frame {offset:+d}',
                       'group':'boundary','expected_decimal_value':value-1 if offset<0 else value})
voices={e['decimal_value']:e for e in plan['events'] if e['type']=='number_voice' and e['phase']=='count'}
last=voices[200]
extra=[('200 before voice',first_frame(last['start_s'])-1),
       ('200 speaking',first_frame((last['start_s']+last['end_s'])/2)),
       ('200 after voice',first_frame(last['end_s'])),
       ('Finale start',first_frame(plan['finale']['estimated_start_s'])),
       ('Before fade',fade_start-1),('Fade midpoint',first_frame(plan['finale']['estimated_start_s']+11)),
       ('Last cream frame',count-1),('Wing half',101),('Wing up',104),
       ('Peck half',5018),('Peck down',5028),('Hop apex',9180)]
probes.extend({'label':label,'frame':index,'group':'finale-and-motion'} for label,index in extra)
indices=sorted(set(p['frame'] for p in probes))
expression='+'.join(f'eq(n\\,{index})' for index in indices)
pattern=OUT/'native-%03d.png'
command=[FFMPEG,'-nostdin','-v','error','-xerror','-n','-i',str(VIDEO),'-map','0:v:0','-an',
         '-vf',f'select={expression}','-fps_mode','passthrough',str(pattern)]
subprocess.run(command,check=True)
mapping={index:OUT/f'native-{ordinal:03d}.png' for ordinal,index in enumerate(indices,1)}
for probe in probes:
    probe['path']=mapping[probe['frame']].as_posix()
    probe['at_s']=probe['frame']/30
    probe['sha256']=checksum(mapping[probe['frame']])

def sheet(group,columns,output):
    rows=[p for p in probes if p['group']==group]
    w,h=384,240
    canvas=Image.new('RGB',(columns*w,math.ceil(len(rows)/columns)*h),(255,248,230))
    draw=ImageDraw.Draw(canvas)
    for order,p in enumerate(rows):
        with Image.open(p['path']) as im:
            image=im.convert('RGB').resize((384,216),Image.Resampling.LANCZOS)
        x,y=order%columns*w,order//columns*h
        canvas.paste(image,(x,y))
        draw.text((x+4,y+219),p['label'],fill=(65,45,30))
    canvas.save(OUT/output)
sheet('boundary',5,'boundaries-contact-sheet.png')
sheet('finale-and-motion',4,'finale-motion-contact-sheet.png')
assert checksum(VIDEO)==before
report={'status':'pass','checked_at_utc':datetime.now(timezone.utc).isoformat(),'video_sha256':before,
        'scope':'Whole-video reduced grayscale presence/black scan plus native boundary/finale/motion evidence; no renderer imports.',
        'decoded_frames':count,'numeric_presence_frames':fade_start-start,'numeric_presence_fields':4*(fade_start-start),
        'minimum_dark_pixels_by_row':minimum,'numeric_presence_threshold_pixels':8,
        'unexpected_empty_numeric_fields':empty,'black_frames':black,'fade_mean_monotonic_with_half_luma_tolerance':True,
        'native_frames':len(indices),'probes':probes,
        'note':'Presence scanning does not identify glyphs; exact glyph correctness is separately checked with the fresh production verifier and native image review.'}
(OUT/'additional-visual-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','decoded_frames','numeric_presence_fields','minimum_dark_pixels_by_row','native_frames']}))
