"""Fresh semantic-motion evidence from actual encoded movies, not a renderer."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageStat
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[5];HERE=Path(__file__).resolve().parent
FF=ROOT/'.venv/bin/ffmpeg';BOX=(1405,510,1905,1040)
def ref(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def sequence(video,start,end,box):
 w,h=box[2]-box[0],box[3]-box[1];stride=w*h*3
 raw=subprocess.check_output([str(FF),'-v','error','-ss',f'{start/30:.9f}','-i',str(video),'-frames:v',str(end-start),'-vf',f'crop={w}:{h}:{box[0]}:{box[1]}','-pix_fmt','rgb24','-f','rawvideo','pipe:1']);assert len(raw)==(end-start)*stride
 return [Image.frombytes('RGB',(w,h),raw[i*stride:(i+1)*stride]) for i in range(end-start)]
def differences(a,b,box):
 a=a.crop(box);b=b.crop(box);diff=ImageChops.difference(a,b);c=diff.split();maximum=ImageChops.lighter(c[0],ImageChops.lighter(c[1],c[2]));mask=maximum.point(lambda v:255 if v>20 else 0)
 return {'mean_absolute_rgb_difference':sum(ImageStat.Stat(diff).mean)/3,'pixels_max_rgb_difference_gt20':mask.histogram()[255],'measurement_region_relative_to_actor':list(box),'measurement_threshold':20}
def contact(images,labels,path,columns=4):
 w,h=images[0].size;o=Image.new('RGB',(w*columns,(h+30)*((len(images)+columns-1)//columns)),'#f9f3e8');d=ImageDraw.Draw(o)
 for i,(im,label) in enumerate(zip(images,labels)):
  x=i%columns*w;y=i//columns*(h+30);o.paste(im,(x,y+30));d.text((x+5,y+5),label,fill='#284049')
 o.save(path)
def encode(images,path):
 w,h=images[0].size
 with subprocess.Popen([str(FF),'-v','error','-n','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{w}x{h}','-framerate','30','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(path)],stdin=subprocess.PIPE) as p:
  for im in images:p.stdin.write(im.tobytes())
  p.stdin.close();assert p.wait()==0

def main():
 global HERE
 parser=argparse.ArgumentParser();parser.add_argument('--video',type=Path,required=True);parser.add_argument('--out-dir',type=Path);args=parser.parse_args();video=args.video.resolve()
 if args.out_dir:HERE=args.out_dir.resolve();HERE.mkdir(parents=True,exist_ok=False)
 motionp=ROOT/'output/fibonacci-counting-001-v002/character-motion.json';motion=json.loads(motionp.read_text());windows=[]
 for w in motion['windows']:
  start=w['start_frame']-9;end=w['end_frame']+9;ims=sequence(video,start,end,BOX);clip=HERE/f'{w["id"]}-actual-native-30fps.mp4';encode(ims,clip);selected=sorted({start,end-1,*[k['at_frame'] for k in w['keyframes']]});contact([ims[i-start] for i in selected],[f'{i/30:.3f}s / f{i}' for i in selected],HERE/f'{w["id"]}-actual-native.png')
  transitions=[]
  for k in w['keyframes'][1:]:
   i=k['at_frame'];seven=[ims[j-start] for j in range(i-3,i+4)];p=HERE/f'{w["id"]}-transition-f{i:05}.png';contact(seven,[f'f{j}' for j in range(i-3,i+4)],p,4);transitions.append({'frame':i,'pose_after':k['pose_id'],'decoded_native_contiguous_frames':[i-3,i+3],'evidence':ref(p)})
  measurements={}
  if w['kind']=='wave':
   inside=next(k['at_frame'] for k in w['keyframes'] if k['pose_id']=='wave_in');outside=next(k['at_frame'] for k in w['keyframes'] if k['pose_id']=='wave_out');a,b=ims[inside-start],ims[outside-start]
   measurements={'wave_in_out_actual_frame_indices':[inside,outside],'forepaw':differences(a,b,(75,250,230,430)),'head_interior':differences(a,b,(145,80,385,280)),'torso_interior':differences(a,b,(205,340,315,440)),'same_image_negative_control':differences(a,a,(75,250,230,430))}
  windows.append({'id':w['id'],'actual_source_frame_range':[start,end-1],'actual_frame_count':len(ims),'decoded_source_native_crop_xyxy':list(BOX),'silent_clip':ref(clip),'contact':ref(HERE/f'{w["id"]}-actual-native.png'),'transitions':transitions,'measurements':measurements})
 # Fresh actual past movie windows, complete actor+hat for the bear. Keep their
 # existing physical pixel size, no normalization or altered past media.
 past=[]
 for name,p,begin,finish,box in [('bear',ROOT/'output/counting-garden-001-bright-v002/paspla-studio-count-1-to-300-blue-sky-1080p.mp4',90,144,(100,80,780,1040)),('prime-kangaroo',ROOT/'output/prime-counting-001-v003/paspla-studio-prime-numbers-2-to-997-1080p.mp4',27,87,(1390,500,1910,1050))]:
  ims=sequence(p,begin,finish,box);clip=HERE/f'past-{name}-fresh-native-30fps.mp4';encode(ims,clip);indices=sorted({0,6,12,18,24,30,36,42,len(ims)-1});contact([ims[i] for i in indices],[f'{(begin+i)/30:.3f}s' for i in indices],HERE/f'past-{name}-fresh-native.png',3);past.append({'id':name,'source':ref(p),'actual_source_frames':[begin,finish-1],'native_complete_actor_crop_xyxy':list(box),'resized':False,'silent_excerpt':ref(clip),'contact':ref(HERE/f'past-{name}-fresh-native.png')})
 report={'kind':'fibonacci-v002-fresh-decoded-motion-evidence','video':ref(video),'motion_plan_used_only_to_choose_source_windows':ref(motionp),'fps':30,'windows':windows,'fresh_past_actual_comparison':past,'total_new_episode_contiguous_native_frames':sum(w['actual_frame_count'] for w in windows),'source_renderer_imported':False,'scope':'Every contiguous decoded frame of4short actor windows, plus7-frame native contacts at their internal keypose boundaries. Two fresh native past-wave excerpts. This is evidence collection for semantic/visual review, not a claim that a human watched all16104frames.'};(HERE/'decoded-motion-evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'video':report['video'],'frames':report['total_new_episode_contiguous_native_frames'],'windows':len(windows),'past':len(past)}),flush=True)
if __name__=='__main__':main()
