"""Fresh canonical-v003 decoding and producer-raster-only preservation proof."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
import hashlib,json,math,subprocess
ROOT=Path(__file__).resolve().parents[5];HERE=Path(__file__).resolve().parent;OUT=HERE/'v003-encoded';OUT.mkdir(exist_ok=False);P=ROOT/'output/fibonacci-counting-001-v003';V=P/'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4';FF=ROOT/'.venv/bin/ffmpeg'
def ref(p):return {'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def decode(start,end,box):
 w,h=box[2]-box[0],box[3]-box[1];stride=w*h*3;raw=subprocess.check_output([str(FF),'-v','error','-ss',f'{start/30:.9f}','-i',str(V),'-frames:v',str(end-start),'-vf',f'crop={w}:{h}:{box[0]}:{box[1]}','-pix_fmt','rgb24','-f','rawvideo','pipe:1']);assert len(raw)==(end-start)*stride
 return [Image.frombytes('RGB',(w,h),raw[i*stride:(i+1)*stride]) for i in range(end-start)]
def contact(ims,labels,path,cols):
 w,h=ims[0].size;o=Image.new('RGB',(w*cols,(h+30)*math.ceil(len(ims)/cols)),'#fff8ed');d=ImageDraw.Draw(o)
 for j,(im,label) in enumerate(zip(ims,labels)):
  x=j%cols*w;y=j//cols*(h+30);o.paste(im,(x,y+30));d.text((x+8,y+7),label,fill='#244149')
 o.save(path)
plan=json.load(open(P/'timeline.json'));n20=next(x for x in plan['counted_states'] if x['index']==20);n21=next(x for x in plan['counted_states'] if x['index']==21);start=math.ceil(n20['transfer_start_s']*30-1e-7);finish=math.ceil(n20['transfer_end_s']*30-1e-7);boundary=math.ceil(n21['formula_start_s']*30-1e-7);end=boundary+10;ims=decode(start,end,(80,280,1360,640));inds=sorted({start,start+6,start+12,round((start+finish)/2),finish-3,finish-1,finish,boundary-2,boundary-1,boundary,boundary+1,boundary+9});contact([ims[i-start] for i in inds],[f'{i/30:.6f}s f{i}' for i in inds],OUT/'actual-F20-full-handoff-native.png',3);contact([ims[i-start].crop((0,0,1280,350)) for i in range(boundary-2,boundary+2)],[f'{i/30:.6f}s f{i}' for i in range(boundary-2,boundary+2)],OUT/'actual-arrived-F20-to-E21-four-consecutive.png',2)
# Silent excerpt from the completed MP4, including every actual30fpsframe.
clip=OUT/'actual-F20-handoff-native-30fps.mp4'
with subprocess.Popen([str(FF),'-v','error','-n','-f','rawvideo','-pixel_format','rgb24','-video_size','1280x360','-framerate','30','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(clip)],stdin=subprocess.PIPE) as p:
 for im in ims:p.stdin.write(im.tobytes())
 p.stdin.close();assert p.wait()==0
full_indices=[start,round((start+finish)/2),finish,boundary,16043,16059,16074,16089,16103]
for i in full_indices:decode(i,i+1,(0,0,1920,1080))[0].save(OUT/f'actual-full-f{i:05}.png')
# This proof deliberately concerns native producer PNGs, NOT encoded fullframe
# bytes. H264 may produce different local quantization after the type change.
a=json.load(open(ROOT/'output/fibonacci-counting-001-v002/frame-plan.json'));b=json.load(open(P/'frame-plan.json'));ignore={'file'}
keys=('start_frame','end_frame','frame_count','mode','n','stage','transfer_tick','carry_column','carry_stage','carry_tick','pose','cream','legend')
assert len(a['runs'])==len(b['runs']);same_runs=all(all(x[k]==y[k] for k in keys) for x,y in zip(a['runs'],b['runs']));old={json.dumps(q['state'],sort_keys=True):q for q in a['images']};changed=[];unexpected=[];outside=[];unchanged=0
for q in b['images']:
 oq=old[json.dumps(q['state'],sort_keys=True)]
 if q['sha256']==oq['sha256']:unchanged+=1;continue
 state=q['state'];changed.append(state)
 if not(state['mode']=='count' and state['n']==20 and state['stage']=='transfer'):unexpected.append(state)
 oldimg=Image.open(ROOT/a['image_directory']/oq['file']).convert('RGB');newimg=Image.open(ROOT/b['image_directory']/q['file']).convert('RGB');diff=ImageChops.difference(oldimg,newimg);mask=Image.new('L',diff.size,255);d=ImageDraw.Draw(mask)
 for c in q['components']:
  if c['name'].split('/')[-1] in ('transferred-0','transferred-1'):d.rectangle(c['content_box_xyxy'],fill=0)
 mx=ImageChops.lighter(diff.getchannel('R'),ImageChops.lighter(diff.getchannel('G'),diff.getchannel('B')))
 if ImageChops.multiply(mx,mask).getbbox():outside.append(state)
report={'kind':'fibonacci-v003-final-type-continuity-and-preservation-closeout','video':ref(V),'source_timeline':ref(P/'timeline.json'),'source_policy':ref(P/'source-policy.json'),'actual_encoded_F20_frame_range_inclusive':[start,end-1],'actual_encoded_F20_contiguous_frames':len(ims),'actual_encoded_easing_end_frame':finish,'actual_next_expression_frame':boundary,'actual_four_consecutive':ref(OUT/'actual-arrived-F20-to-E21-four-consecutive.png'),'actual_full_handoff_contact':ref(OUT/'actual-F20-full-handoff-native.png'),'actual_silent_native_excerpt':ref(clip),'actual_native_fullscreens':[{**ref(OUT/f'actual-full-f{i:05}.png'),'frame':i} for i in full_indices],'producer_PNG_preservation_only':{'same_complete_state_and_actor_timing_runs':same_runs,'holds':len(b['runs']),'unchanged_byte_identical_native_images':unchanged,'changed_native_images':len(changed),'all_changed_states':changed,'unexpected_changed_states':unexpected,'changed_pixels_outside_two_copied_glyph_fields':outside,'comparison_is_not_encoded_H264_identity':True},'decoded_visual_judgment':'Pending viewing newly extracted actual native contacts/fullscreens; independent full-video QA is separate.'};(OUT/'encoded-evidence-and-preservation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'actual_frames':len(ims),'source_range':[start,end-1],'unchanged_png':unchanged,'changed_png':len(changed),'unexpected':len(unexpected),'outside_glyphs':len(outside),'same_run_timing':same_runs,'video':report['video']},indent=2))
