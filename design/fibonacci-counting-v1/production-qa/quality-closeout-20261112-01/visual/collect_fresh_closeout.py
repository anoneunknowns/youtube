"""New closeout decoding of actor boundaries and teaching transitions.
No producer renderer is imported. Plan fields only choose source frame windows.
"""
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageStat
import subprocess,json,math,hashlib
ROOT=Path(__file__).resolve().parents[5];HERE=Path(__file__).resolve().parent;V=ROOT/'output/fibonacci-counting-001-v002/paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4';FF=ROOT/'.venv/bin/ffmpeg';ACT=(1405,510,1905,1040)
def ref(p):return {'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def seq(start,end,box):
 w,h=box[2]-box[0],box[3]-box[1];stride=w*h*3;raw=subprocess.check_output([str(FF),'-v','error','-ss',f'{start/30:.9f}','-i',str(V),'-frames:v',str(end-start),'-vf',f'crop={w}:{h}:{box[0]}:{box[1]}','-f','rawvideo','-pix_fmt','rgb24','pipe:1']);assert len(raw)==(end-start)*stride
 return [Image.frombytes('RGB',(w,h),raw[i*stride:(i+1)*stride]) for i in range(end-start)]
def contact(ims,labels,path,cols):
 w,h=ims[0].size;out=Image.new('RGB',(w*cols,(h+30)*math.ceil(len(ims)/cols)),'#fff8ed');d=ImageDraw.Draw(out)
 for j,(im,label) in enumerate(zip(ims,labels)):
  x=j%cols*w;y=j//cols*(h+30);out.paste(im,(x,y+30));d.text((x+8,y+6),label,fill='#254049')
 out.save(path)
def diff(a,b,box):
 d=ImageChops.difference(a.crop(box),b.crop(box));chs=d.split();mx=ImageChops.lighter(chs[0],ImageChops.lighter(chs[1],chs[2]));mask=mx.point(lambda v:255 if v>20 else 0)
 return {'mean_absolute_rgb_difference':sum(ImageStat.Stat(d).mean)/3,'pixels_max_rgb_delta_gt20':mask.histogram()[255],'region_actor_relative':list(box)}
def irises(im):
 region=(145,120,365,300);f=im.crop(region);pixels=[]
 for y in range(f.height):
  for x in range(f.width):
   r,g,b=f.getpixel((x,y))
   if b-r>=20 and b-g>=4 and 45<=r<=170 and g<=190:pixels.append((x+region[0]+ACT[0],y+region[1]+ACT[1]))
 if not pixels:return None
 return {'centroid_xy':[sum(p[i] for p in pixels)/len(pixels) for i in [0,1]],'count':len(pixels),'bbox':[min(p[0] for p in pixels),min(p[1] for p in pixels),max(p[0] for p in pixels)+1,max(p[1] for p in pixels)+1]}
fp=json.loads((ROOT/'output/fibonacci-counting-001-v002/frame-plan.json').read_text());tl=json.loads((ROOT/'output/fibonacci-counting-001-v002/timeline.json').read_text());motion=json.loads((ROOT/'output/fibonacci-counting-001-v002/character-motion.json').read_text());motion_boundaries={k['at_frame'] for w in motion['windows'] for k in w['keyframes'][1:]};adir=HERE/'actor-boundaries';adir.mkdir(exist_ok=False);boundaries=[];last=None
for row in fp['runs']:
 if last is not None and row['pose']!=last:boundaries.append({'frame':row['start_frame'],'before':last,'after':row['pose']})
 last=row['pose']
for b in boundaries:
 i=b['frame'];ims=seq(i-3,i+4,ACT);p=adir/f'f{i:05}-{b["before"]}-to-{b["after"]}.png';contact(ims,[f'f{i-3+j} {(i-3+j)/30:.6f}s' for j in range(7)],p,4)
 b.update({'at_s':i/30,'new_four_windows_boundary':i in motion_boundaries,'native_contiguous_frames':[i-3,i+3],'evidence':ref(p),'head_interior_diff':diff(ims[2],ims[3],(145,80,385,280)),'torso_interior_diff':diff(ims[2],ims[3],(205,340,315,440)),'blue_iris_before':irises(ims[2]),'blue_iris_after':irises(ims[3])})
 # Before/after/next at native physical size, compact enough to inspect directly.
 contact([ims[j] for j in [2,3,4]],[f'f{i-1}',f'f{i}',f'f{i+1}'],adir/f'f{i:05}-inspection.png',3)
# Every transfer has native entry/middle/exit/settled observations, not just all
# values in one static resultant state.
tdir=HERE/'handoffs';tdir.mkdir(exist_ok=False);transfers=[]
for row in tl['counted_states']:
 if row.get('transfer_start_s') is None:continue
 begin,finish=row['transfer_start_s'],row['transfer_end_s'];indices=[math.ceil(begin*30-1e-7),round((begin+finish)/2*30),math.ceil(finish*30-1e-7)-1,math.ceil(finish*30-1e-7)];ims=[seq(i,i+1,(80,280,1360,640))[0] for i in indices];p=tdir/f'F{row["index"]:02}-native.png';contact(ims,[f'f{i} {i/30:.6f}s' for i in indices],p,2);transfers.append({'index':row['index'],'values':[row['a'],row['b'],row['c']],'frames':indices,'evidence':ref(p)})
# Every unique decimal-column phase in all3replays, selecting actual frame-plan
# switches. Quantized movement remains one state family, with midpoint samples.
cdir=HERE/'carry';cdir.mkdir(exist_ok=False);carry=[];last=None
for row in fp['runs']:
 if row['mode']!='replay' or row['n'] not in [8,13,18]:continue
 key=(row['n'],row['carry_column'],row['carry_stage'])
 if key==last:continue
 last=key;i=row['start_frame'];im=seq(i,i+1,(80,220,1360,960))[0];p=cdir/f'F{key[0]}-col{key[1]}-{key[2]}-f{i:05}.png';im.save(p);carry.append({'index':key[0],'column':key[1],'phase':key[2],'frame':i,'at_s':i/30,'evidence':ref(p)})
# Full final fade, including the final decoded frame, sampled at exact frame
# boundaries, and the longest9digit result and final two-line English reading.
fdir=HERE/'finale';fdir.mkdir(exist_ok=False);fade=[]
for i in [15242,15243,15244,15490,15526,15991,16024,16043,16044,16059,16074,16089,16103]:
 im=seq(i,i+1,(0,0,1920,1080))[0];p=fdir/f'f{i:05}.png';im.save(p);fade.append({'frame':i,'at_s':i/30,'evidence':ref(p),'rgb_channel_extrema':[list(x) for x in im.getextrema()]})
r={'kind':'fibonacci-v002-quality-closeout-fresh-visual-evidence','video':ref(V),'fps':30,'actor_native_crop':list(ACT),'actor_boundaries':boundaries,'all_actor_boundary_count':len(boundaries),'new_four_window_boundary_count':sum(b['new_four_windows_boundary'] for b in boundaries),'all_actor_native_contiguous_frames':7*len(boundaries),'handoffs':transfers,'carry_phase_observations':carry,'finale_and_fade':fade,'source_renderer_imported':False,'scope':'New actual-MP4 decodes: all52pose boundaries, including22new-motion boundaries,38handoffs, all3carry phase switches, final fade/long-number frames. Static measurements are observation aids, not automatic judgments of acting quality.'};(HERE/'fresh-evidence.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'actor_boundaries':len(boundaries),'new_motion_boundaries':r['new_four_window_boundary_count'],'native_actor_frames':r['all_actor_native_contiguous_frames'],'handoffs':len(transfers),'carry_phase_observations':len(carry),'finale_frames':len(fade)}),flush=True)
