"""Bind every current cue to a newly decoded native finished-v003 frame."""
from pathlib import Path
import sys,json,math,hashlib
ROOT=Path(__file__).resolve().parents[5];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw
from tools import verify_fibonacci_video as verify
from tools import verify_fibonacci_intro_seed as intro

HERE=Path(__file__).parent;OUT=ROOT/'output/fibonacci-counting-001-v003'
video=OUT/'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4';plan=json.loads((OUT/'timeline.json').read_text())
events=plan['voice_events'];frames={verify.frame_at((e['start_s']+e['end_s'])/2):e for e in events}
folder=HERE/'v003-cue-observations';folder.mkdir(exist_ok=False)
seed_rows,_=intro.contract();records=[];thumbnails={}
for frame,image in verify.media.decoded_frames(video,str(ROOT/'.venv/bin/ffmpeg'),folder/'cue-native-decode.log',1,sorted(frames)):
    event=frames[frame];segment=verify.segment_at(plan['visual_segments'],frame/30)
    if segment['mode']=='seeds' and segment.get('index') is None:
        components=intro.inspect(image,seed_rows,frame)
    else:
        labels=verify.labels_for_segment(segment,frame/30,plan)
        components=verify.inspect_labels(image,labels,frame)
    record={'cue_id':event['id'],'text':event['text'],'voice_start_s':event['start_s'],'voice_end_s':event['end_s'],
        'frame':frame,'time_s':frame/30,'actual_decoded_RGB_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
        'observed_mode':segment['mode'],'components':components,'passed':bool(components) and all(c['passed'] for c in components)}
    path=folder/(event['id']+'.jpg');image.save(path,quality=96,subsampling=0)
    record['full_native_image']={'path':str(path.relative_to(ROOT)),'sha256':verify.sha(path),'format_note':'JPEG full-frame visual evidence; measurements use the unmodified freshly decodedRGB above.'}
    records.append(record);thumbnails[event['id']]=image.resize((640,360),Image.Resampling.LANCZOS)
for name,ids in [('dialogue',[e['id'] for e in events if e['id'][0] in 'ITO']),('counts',[e['id'] for e in events if e['id'][0]=='N']),('expressions',[e['id'] for e in events if e['id'][0]=='E'])]:
    sheet=Image.new('RGB',(2560,math.ceil(len(ids)/4)*390),'#fffaf0');draw=ImageDraw.Draw(sheet)
    for i,ident in enumerate(ids):
        x=i%4*640;y=i//4*390;sheet.paste(thumbnails[ident],(x,y));draw.text((x+10,y+368),ident,fill='#284455')
    sheet.save(folder/(name+'-contact.jpg'),quality=94,subsampling=0)
components=[c for r in records for c in r['components']]
report={'kind':'all104-finished-v003-cue-native-observation','passed':len(records)==104 and all(r['passed'] for r in records),
 'video':{'path':str(video.relative_to(ROOT)),'sha256':verify.sha(video)},'timeline':{'path':str((OUT/'timeline.json').relative_to(ROOT)),'sha256':verify.sha(OUT/'timeline.json')},
 'cues':104,'native_components':len(components),'max_abs_dx_px':max(abs(c['delta_x_px']) for c in components),'max_abs_dy_px':max(abs(c['delta_y_px']) for c in components),
 'records':records,'scope':'Each of104measured utterance midpoints is newly decoded and independently inspected at native size. Intro-seed labels use the frozen preproduction design fields; other labels use the preserved independent content/cardinal/glyph verifier. This binds cue semantics to selected actual frames and does not claim continuous human whole-video viewing.'}
(folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('records','scope')},ensure_ascii=False))
raise SystemExit(not report['passed'])
