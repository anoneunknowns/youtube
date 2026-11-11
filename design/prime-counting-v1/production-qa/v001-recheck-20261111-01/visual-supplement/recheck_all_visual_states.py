"""Supplement independent semantic checks with every encoded raster state.

No production renderer or formatter is imported. A state is derived from the
measured timeline, then checked against the retained frame-plan. Retained PNGs
are secondary pixel references, not independent mathematical ground truth;
the separate full verifier supplies independent prime/word/factor checks.
"""
from pathlib import Path
from bisect import bisect_right
from collections import Counter,defaultdict
import hashlib,json,math,sys
from PIL import Image,ImageChops,ImageStat,ImageDraw
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from tools import verify_prime_video as v
BASE=ROOT/'design/prime-counting-v1/production-qa/v001-recheck-20261111-01/visual-supplement'
OUT=ROOT/'output/prime-counting-001-v001'
VIDEO=OUT/'paspla-studio-prime-numbers-2-to-997-1080p.mp4'
FFMPEG=ROOT/'.venv/bin/ffmpeg'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
plan=load(OUT/'timeline.json');fp=load(OUT/'frame-plan.json');segments=plan['visual_segments'];starts=[s['start_s'] for s in segments]
assert sha(VIDEO)=='ed506ca4305e4bf367fa8c69c826b18907a9264482b46db18fe06b6653b01b5f'
assert fp['timeline_sha256']==sha(OUT/'timeline.json')
runs=fp['runs'];frame_run=[];cursor=0
for row in runs:
 assert row['start_frame']==cursor and row['end_frame']>cursor
 assert row['frame_count']==row['end_frame']-cursor
 frame_run.extend([row]*(row['end_frame']-cursor));cursor=row['end_frame']
assert cursor==plan['duration_frames']==20590
state_errors=[]
for index,row in enumerate(frame_run):
 t=index/30+1e-9;seg=segments[bisect_right(starts,t)-1]
 a=min(1,(t-seg['start_s'])/seg['diagram_fade_in_s'] if seg.get('diagram_fade_in_s') else 1,(seg['end_s']-t)/seg['diagram_fade_out_s'] if seg.get('diagram_fade_out_s') else 1)
 alpha=max(0,min(255,round(a*255)));cream=0
 if t<.8:cream=round(255*(1-t/.8))
 elif t>=plan['duration_s']-2:
  cream=round(255*(t-plan['duration_s']+2)/((cursor-1)/30-plan['duration_s']+2))
 cream=max(0,min(255,cream))
 if row['mode']!=seg['mode'] or row['value']!=seg.get('value') or abs(row['diagram_alpha']-alpha)>1 or abs(row['cream']-cream)>1:state_errors.append(index)
assert not state_errors
refs={};reference_hashes=[];folder=ROOT/fp['image_directory']
for row in fp['images']:
 p=folder/row['file'];h=sha(p);assert h==row['sha256']
 with Image.open(p) as im:refs[row['file']]=im.convert('RGB').resize((480,270),Image.Resampling.BOX)
 reference_hashes.append({'file':row['file'],'sha256':h})
assert len(refs)==353
errors=[];modes=Counter();maximum=[0.,0.,0.];actor_max=[0.,0.,0.];per_ref=defaultdict(lambda:{'frames':0,'max_rgb_mae':[0.,0.,0.]})
for index,image in v.decoded_frames(VIDEO,str(FFMPEG),BASE/'all-frame-state-decode.log',4):
 row=frame_run[index];expected=refs[row['file']];error=ImageStat.Stat(ImageChops.difference(image,expected)).mean
 actor=ImageStat.Stat(ImageChops.difference(image.crop((362,132,474,257)),expected.crop((362,132,474,257)))).mean
 maximum=[max(a,b) for a,b in zip(maximum,error)];actor_max=[max(a,b) for a,b in zip(actor_max,actor)]
 entry=per_ref[row['file']];entry['frames']+=1;entry['max_rgb_mae']=[max(a,b) for a,b in zip(entry['max_rgb_mae'],error)]
 modes[row['mode']]+=1
 if max(error)>4:errors.append({'frame':index,'kind':'full-frame-state-difference','rgb_mae':error})
 if max(actor)>4:errors.append({'frame':index,'kind':'character-tail-region-difference','rgb_mae':actor})
assert sum(modes.values())==20590
# Every planned hold onset includes all353 unique states and every layout cut.
indices=sorted({r['start_frame'] for r in runs});native=[];labels_seen=0;tile_samples=0;components_seen=0;diagram_alpha_samples=defaultdict(list)
for index,image in v.decoded_frames(VIDEO,str(FFMPEG),BASE/'all-state-native-decode.log',1,indices):
 row=frame_run[index];mode=row['mode'];cream=row['cream'];t=index/30
 seg=segments[bisect_right(starts,t+1e-9)-1]
 entry={'frame':index,'at_s':t,'mode':mode,'value':row['value'],'diagram_alpha':row['diagram_alpha'],'cream':cream}
 if cream==0:
  labels=v.count_extra_labels(row['value']) if mode=='count' else v.approved_teacher_labels().get(mode,[])
  measured=v.native_labels(image,labels,index,mode);labels_seen+=len(measured);entry['centered_labels']=measured
  for c in measured:
   if not c['passed']:errors.append({'frame':index,'kind':'label','label':c})
  if mode in v.TILE_FIELDS:
   alpha=v.diagram_alpha(seg,t);entry['diagrams']=[]
   for name,field,color,quantity in v.TILE_FIELDS[mode]:
    op=v.opacity_checks(image,name,field,color,alpha);tile_samples+=1;diagram_alpha_samples[mode].append(alpha)
    data={'name':name,'expected_quantity':quantity,'opacity':op}
    if not op['passed']:errors.append({'frame':index,'kind':'tile-opacity','name':name,'max_rgb_error':op['max_rgb_error']})
    if .45<=alpha<=1:
     comps=v.tile_components(image,field,color,name=name,alpha=alpha);data['observed_quantity']=len(comps);components_seen+=len(comps)
     if len(comps)!=quantity:errors.append({'frame':index,'kind':'tile-count','name':name,'observed':len(comps),'expected':quantity})
     if comps:
      mask=Image.new('L',(field[2]-field[0],field[3]-field[1]));draw=ImageDraw.Draw(mask)
      for c in comps:
       b=c['bbox'];draw.rectangle((b[0]-field[0],b[1]-field[1],b[2]-1-field[0],b[3]-1-field[1]),fill=255)
      center=v.raster_centering_report(mask,field,origin_xy=field[:2],name=f'allstates{index}/{name}',tolerance_px=1);data['group_center']=center
      if not center['passed']:errors.append({'frame':index,'kind':'tile-center','name':name,'report':center})
    entry['diagrams'].append(data)
 native.append(entry)
report={'schema_version':1,'kind':'fresh-all-raster-states-and-transition-recheck','passed':not errors,'video_sha256':sha(VIDEO),'timeline_sha256':sha(OUT/'timeline.json'),'frame_plan_sha256':sha(OUT/'frame-plan.json'),'independently_derived_timeline_states_checked':20590,'actual_decoded_frames':sum(modes.values()),'hold_runs':len(runs),'distinct_reference_rasters':len(refs),'all_reference_png_hashes_match_retained_render_receipt':True,'full_frame_reference_rgb_mae_tolerance':4,'full_frame_max_rgb_mae':maximum,'character_body_tail_region_max_rgb_mae':actor_max,'native_hold_onsets_checked':len(indices),'actual_centered_label_measurements':labels_seen,'actual_tile_group_samples':tile_samples,'actual_connected_tile_components':components_seen,'mode_frame_counts':dict(modes),'diagram_alpha_coverage':{k:{'samples':len(values),'minimum':min(values),'maximum':max(values),'mid_fade_samples':sum(.01<a<.99 for a in values)} for k,values in diagram_alpha_samples.items()},'errors':errors,'native_samples':native,'per_reference_frames':dict(per_ref),'reference_sha256':reference_hashes,'limitations':['Retained producer PNG comparison is supplementary continuity/freeze/cut evidence, not the independent semantic ground truth. Separate fresh full media verifier independently constructs primes, inverse parses cardinals and verifies glyphs/factors.','Pixel tolerance accounts for expected H264/limited-range conversion; every actual hold-onset label center and all diagram opacity steps are also measured separately without relaxing1px bounds.','No human continuous full-video viewing/listening claim.']}
(BASE/'all-visual-states.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['passed','actual_decoded_frames','hold_runs','distinct_reference_rasters','native_hold_onsets_checked','actual_centered_label_measurements','actual_tile_group_samples','full_frame_max_rgb_mae','character_body_tail_region_max_rgb_mae']}),flush=True)
if errors:print(json.dumps(errors[:8],ensure_ascii=False),flush=True)
raise SystemExit(bool(errors))
