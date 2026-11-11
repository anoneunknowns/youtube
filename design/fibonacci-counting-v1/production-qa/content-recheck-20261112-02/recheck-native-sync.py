"""Fresh native content/synchronization samples from the adopted v003 movie."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
import hashlib,json,math,sys,subprocess
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from tools import verify_fibonacci_video as old
from tools import verify_fibonacci_video_v003 as current
from tools import verify_fibonacci_intro_seed as intro
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent;OUT=ROOT/'output/fibonacci-counting-001-v003'
video=OUT/'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4';timeline=OUT/'timeline.json'
plan=json.loads(timeline.read_text());events,states,segments,schedule=old.validate_schedule(plan)
folder=HERE/'native-sync';folder.mkdir(exist_ok=False)
frames=defaultdict(list)
for e in events:frames[old.frame_at((e['start_s']+e['end_s'])/2)].append({'kind':'voice_midpoint','id':e['id'],'text':e['text']})
for s in states:
 if s['index']>=2:
  at=old.frame_at(s['display_start_s'])
  frames[at-1].append({'kind':'before_result_reveal','index':s['index']})
  frames[at].append({'kind':'first_result_reveal','index':s['index']})
 if s.get('transfer_end_s') is not None:frames[old.frame_at(s['transfer_end_s'])].append({'kind':'handoff_arrival','index':s['index']})
seed_rows,_=intro.contract();records=[];thumbnails=[]
with current.v003_labels():
 for frame,image in old.media.decoded_frames(video,str(ROOT/'.venv/bin/ffmpeg'),folder/'decode.log',1,sorted(frames)):
  segment=old.segment_at(segments,frame/30)
  if segment['mode']=='seeds' and segment.get('index') is None:components=intro.inspect(image,seed_rows,frame)
  else:components=old.inspect_labels(image,old.labels_for_segment(segment,frame/30,plan),frame)
  absent=old.unrevealed_reading_check(image,segment,frame/30)
  row={'frame':frame,'time_s':frame/30,'requests':frames[frame],'observed_mode':segment['mode'],'observed_stage':old.stage_at(segment,frame/30)[0],'components':components,'unrevealed_result_reading':absent,'decoded_RGB_sha256':hashlib.sha256(image.tobytes()).hexdigest(),'passed':bool(components) and all(c['passed'] for c in components) and (absent is None or absent['passed'])}
  p=folder/f'frame-{frame:06d}.jpg';image.save(p,quality=96,subsampling=0);row['image']={'path':str(p.relative_to(ROOT)),'sha256':old.sha(p)};records.append(row)
  if any(r['kind']=='voice_midpoint' and r['id'].startswith('N') for r in frames[frame]):thumbnails.append((frame,image.resize((480,270),Image.Resampling.LANCZOS)))
for page in range(math.ceil(len(thumbnails)/16)):
 group=thumbnails[page*16:(page+1)*16];sheet=Image.new('RGB',(1920,math.ceil(len(group)/4)*300),'#fffaf0');d=ImageDraw.Draw(sheet)
 for k,(frame,thumb) in enumerate(group):
  x=k%4*480;y=k//4*300;sheet.paste(thumb,(x,y));n=next(r['id'] for r in frames[frame] if r.get('id','').startswith('N'));d.text((x+6,y+278),f'{n}  {frame/30:.3f}s',fill='#284455')
 sheet.save(folder/f'counts-page-{page+1}.jpg',quality=94,subsampling=0)
components=[c for r in records for c in r['components']]
report={'kind':'fresh-v003-native-content-and-reveal-synchronization-recheck','checked_at_utc':datetime.now(timezone.utc).isoformat(),'passed':len(records)==len(frames) and all(r['passed'] for r in records),'video':{'path':str(video.relative_to(ROOT)),'sha256':old.sha(video)},'timeline':{'path':str(timeline.relative_to(ROOT)),'sha256':old.sha(timeline)},'schedule':schedule,'sample_requests':{'all_utterance_midpoints':104,'generated_result_reveal_boundaries_both_sides':78,'all_handoff_arrivals':38},'unique_native_frames':len(records),'native_component_observations':len(components),'max_abs_dx_px':max(abs(c['delta_x_px']) for c in components),'max_abs_dy_px':max(abs(c['delta_y_px']) for c in components),'tolerance_per_axis_px':1,'errors':[{'frame':r['frame'],'requests':r['requests']} for r in records if not r['passed']],'verifier_sources':[{'path':str(Path(p).relative_to(ROOT)),'sha256':old.sha(Path(p))} for p in (old.__file__,current.__file__,intro.__file__,__file__)],'records':records,'scope':'Fresh selected native decoded frames, glyph identity and both-axis placement/containment plus all39 result reveal boundaries and38 arrivals. Independent numerical binomial/cardinal helpers; no producer renderer imported. This is not a new full-video or speech-recognition pass.'}
(folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('records','verifier_sources')},ensure_ascii=False));assert report['passed']
