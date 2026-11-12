"""Export native reference frames from an actual completed Powers of Two MP4."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rel(path):return str(Path(path).resolve().relative_to(ROOT))
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--video',type=Path,required=True)
 parser.add_argument('--timeline',type=Path,required=True)
 parser.add_argument('--out-dir',type=Path,required=True)
 args=parser.parse_args()
 video=args.video.resolve();timeline=args.timeline.resolve();target=args.out_dir.resolve()
 if target.exists():raise SystemExit('Reference export refuses an existing output directory')
 t=json.loads(timeline.read_text());states={s['index']:s for s in t['counted_states']};events={e['id']:e for e in t.get('voice_events',t.get('events'))}
 points=[('01-intro',7.5),('02-seed',states[0]['voice_start_s']+.2),('03-eight',states[3]['voice_start_s']+.2),('04-exponent',events['X003']['start_s']+1),('05-two-groups',states[6]['operation_start_s']+1),('06-thousand',states[10]['voice_start_s']+.4),('07-trillion',states[40]['voice_end_s']+.1),('08-last-value',states[64]['voice_end_s']+.08),('09-ending',t['finale']['start_s']+4)]
 selection=sorted((round(sec*30),name) for name,sec in points)
 target.mkdir(parents=True);(target/'native').mkdir()
 expression='+'.join('eq(n\\,'+str(frame)+')' for frame,name in selection)
 ffmpeg=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg')
 command=[ffmpeg,'-hide_banner','-loglevel','error','-i',str(video),'-vf','select='+expression,'-fps_mode','vfr',str(target/'native/frame-%02d.png')]
 result=subprocess.run(command,capture_output=True,text=True)
 (target/'extraction.log').write_text(result.stdout+result.stderr)
 if result.returncode:raise RuntimeError(result.stderr)
 receipts=[]
 for i,(frame,name) in enumerate(selection,1):
  old=target/'native'/f'frame-{i:02d}.png';new=target/'native'/f'{name}.png';old.replace(new)
  if Image.open(new).size!=(1920,1080):raise ValueError('Native extraction resolution mismatch')
  receipts.append({'id':name,'path':rel(new),'sha256':sha(new),'frame':frame,'time_s':frame/30,'size_px':[1920,1080]})
 canvas=Image.new('RGB',(1920,1230),'#f2eadc');draw=ImageDraw.Draw(canvas)
 font=ImageFont.truetype(str(ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'),23)
 for i,row in enumerate(sorted(receipts,key=lambda row:row['id'])):
  image=Image.open(ROOT/row['path']).convert('RGB');col,line=i%3,i//3
  canvas.paste(image.resize((624,351),Image.Resampling.LANCZOS),(col*640+8,line*410+8))
  draw.text((col*640+16,line*410+365),row['id'],font=font,fill='#51453f')
 canvas.save(target/'storyboard.jpg',quality=93)
 Image.open(target/'native/01-intro.png').save(target/'key-visual.png')
 report={'schema_version':1,'kind':'completed-mp4-native-reference-export','owner':'codex:powers-of-two-production:01a1cd56','status':'native-export; episode-adoption-is-separate','source_video':rel(video),'source_video_sha256':sha(video),'timeline':rel(timeline),'timeline_sha256':sha(timeline),'frames':receipts,'storyboard':rel(target/'storyboard.jpg'),'key_visual':rel(target/'key-visual.png'),'method':'one complete FFmpeg decode with absolute frame-index selection; source PNGs native1920x1080, separate resized collage','exporter':{'path':rel(__file__),'sha256':sha(__file__)},'command_argv_json':json.dumps(command,ensure_ascii=False),'numbered_output_provenance':'frame-%02d.png is a temporary numbered output pattern; all final required images are explicitly named in frames.'}
 (target/'reference-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':'exported','frames':len(receipts),'output':rel(target),'source_video_sha256':report['source_video_sha256']}))

if __name__=='__main__':main()
