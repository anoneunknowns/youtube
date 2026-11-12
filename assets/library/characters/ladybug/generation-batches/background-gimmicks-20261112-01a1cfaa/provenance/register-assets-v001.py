"""Register only butterfly, ladybug and rainbow; preserve every canonical pixel."""
from __future__ import annotations
import hashlib, json, math, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.dont_write_bytecode = True
ROOT = Path('/Users/support/codex/youtube')
sys.path.insert(0, str(ROOT))
from tools.component_alignment import raster_centering_report
from tools import character_library as library

BATCH = 'generation-batches/background-gimmicks-20261112-01a1cfaa'
ORDER = {
 'butterfly':['folded_up','quarter_open','half_open','three_quarters_open','fully_open','downstroke','glide','bank'],
 'ladybug':['neutral','walk_a','walk_b','walk_c','elytra_half_open','elytra_full_open','fly','landing'],
 'rainbow':['full_arch'],
}
NAMES = {'butterfly':('蝶','Butterfly'), 'ladybug':('てんとう虫','Ladybug'), 'rainbow':('虹','Rainbow')}
# Manually reviewed native-ink landmarks. These exclude antennae and moving
# wings; they are not the whole sprite centroid or a per-pose fitting scale.
THORAX_ROIS = {
 'folded_up':[568,547,684,692], 'quarter_open':[237,197,276,245],
 'half_open':[239,188,277,238], 'three_quarters_open':[235,189,275,235],
 'fully_open':[235,172,278,223], 'downstroke':[235,173,276,224],
 'glide':[238,185,277,232], 'bank':[244,175,288,231],
}
CORE_BOXES = {
 'butterfly':{'folded_up':[566,455,685,915], 'quarter_open':[235,162,279,336],
  'half_open':[235,157,281,321], 'three_quarters_open':[232,153,278,315],
  'fully_open':[233,140,281,309], 'downstroke':[232,139,280,305],
  'glide':[233,148,281,308], 'bank':[236,141,305,308]},
 'ladybug':{'neutral':[153,88,376,329], 'walk_a':[132,87,355,326],
  'walk_b':[151,80,375,321], 'walk_c':[134,83,360,325],
  'elytra_half_open':[193,82,339,309], 'elytra_full_open':[186,79,336,301],
  'fly':[190,72,337,283], 'landing':[187,88,337,298]},
}
LADY_ABDOMEN = {'neutral':[156,136,374,327], 'walk_a':[134,134,354,324],
 'walk_b':[153,126,373,320], 'walk_c':[135,131,359,323],
 'elytra_half_open':[197,152,335,307], 'elytra_full_open':[192,146,332,298],
 'fly':[195,137,333,281], 'landing':[194,155,333,295]}

def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(path):return Path(path).relative_to(ROOT).as_posix()
def write(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def bbox(image, threshold=8):return image.getchannel('A').point(lambda a:255 if a>=threshold else 0).getbbox()

def anatomy(identity, name, image):
 mask=Image.new('L',image.size,0)
 if identity=='rainbow':return mask,None,None
 roi=THORAX_ROIS[name] if identity=='butterfly' else LADY_ABDOMEN[name]
 source=image.load();target=mask.load()
 for y in range(roi[1],roi[3]):
  for x in range(roi[0],roi[2]):
   r,g,b,a=source[x,y]
   # Butterfly thorax uses warm brown ink only. Ladybug abdomen/shell is
   # measured as the central body volume, never the opened wing silhouette.
   if a>=128 and (identity=='ladybug' or (r<210 and g<155 and b<115)):
    target[x,y]=255
 box=mask.getbbox()
 if box is None:raise ValueError((identity,name,'empty anatomical landmark'))
 return mask,[(box[0]+box[2])/2,(box[1]+box[3])/2],box

def transform(image,size,anchor,target,scale,dy=0):
 tx=target[0]-anchor[0]*scale;ty=target[1]-anchor[1]*scale+dy
 return image.transform(size,Image.Transform.AFFINE,(1/scale,0,-tx/scale,0,1/scale,-ty/scale),
   resample=Image.Resampling.BICUBIC if image.mode=='RGBA' else Image.Resampling.NEAREST)

def label(draw,xy,text,fill):
 b=draw.textbbox((0,0),text)
 draw.text((xy[0]-b[0],xy[1]-b[1]),text,fill=fill)

def save_gif(path,frames,durations,loop):
 # One fixed palette for the whole clip avoids palette flicker on static ink.
 sampler=Image.new('RGB',(frames[0].width,len(frames)*12))
 for i,im in enumerate(frames):sampler.paste(im.resize((im.width,12)),(0,i*12))
 palette=sampler.quantize(colors=256)
 encoded=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in frames]
 kwargs={'save_all':True,'append_images':encoded[1:],'duration':durations,'disposal':2,'optimize':False}
 if loop:kwargs['loop']=0
 encoded[0].save(path,**kwargs)

def bounds_record(layer,content,name):
 box=bbox(layer)
 return {'name':name,'visible_box_xyxy':list(box) if box else None,
  'content_box_xyxy':list(content),'empty':box is None,
  'contained':bool(box and content[0]<=box[0] and content[1]<=box[1] and box[2]<=content[2] and box[3]<=content[3]),
  'touches_measurement_edge':bool(box and (box[0]==0 or box[1]==0 or box[2]==layer.width or box[3]==layer.height))}

def make_effect(image,effect,index,total):
 out=image.copy()
 if not effect:return out
 kind=effect['type']
 if kind=='angular_reveal':
  p=effect['progress'][index]
  if p>=1:return out
  mask=Image.new('L',out.size,0)
  if p>0:
   cx,cy=effect['center_px'];radius=max(out.size)*2
   ImageDraw.Draw(mask).pieslice((cx-radius,cy-radius,cx+radius,cy+radius),180,180+180*p,fill=255)
  out.putalpha(ImageChops.multiply(out.getchannel('A'),mask))
 elif kind=='opacity':out.putalpha(out.getchannel('A').point(lambda a:round(a*effect['opacity'][index])))
 elif kind=='light_sweep':
  # Playback-only highlight; the PNG and its alpha remain untouched on disk.
  center=effect['center_fraction'][index]*out.width;width=effect['width_fraction']*out.width
  stripe=Image.new('L',out.size,0);d=ImageDraw.Draw(stripe)
  d.polygon([(center-width,0),(center,0),(center+width,out.height),(center,out.height)],fill=round(effect['strength']*255))
  stripe=stripe.filter(ImageFilter.GaussianBlur(width/3))
  alpha=out.getchannel('A');rgb=Image.composite(Image.new('RGBA',out.size,'white'),out,stripe)
  rgb.putalpha(alpha);out=rgb
 return out

def clips_for(identity):
 if identity=='butterfly':return {
  'flap':{'frames':['folded_up','quarter_open','half_open','three_quarters_open','fully_open','downstroke','fully_open','three_quarters_open','half_open','quarter_open'],'durations_ms':[80,60,60,60,80,70,60,60,60,60],'loop':True},
  'glide':{'frames':['glide','fully_open','glide'],'durations_ms':[500,170,500],'loop':True},
  'bank':{'frames':['glide','bank','glide'],'durations_ms':[180,300,180],'loop':True}}
 if identity=='ladybug':return {
  'walk':{'frames':['neutral','walk_a','walk_b','walk_c','walk_b','walk_a'],'durations_ms':[160,120,120,120,120,120],'loop':True},
  'wing_open':{'frames':['neutral','elytra_half_open','elytra_full_open'],'durations_ms':[220,180,350],'loop':False},
  'takeoff':{'frames':['neutral','elytra_half_open','elytra_full_open','fly'],'durations_ms':[180,150,180,300],'loop':False,'translation_y_reference_fraction':[0,0,-.05,-.18]},
  'land':{'frames':['fly','landing','neutral'],'durations_ms':[180,210,300],'loop':False,'translation_y_reference_fraction':[-.18,-.03,0]}}
 p=[i/20 for i in range(21)]
 op=[i/8 for i in range(9)]+[i/8 for i in range(7,-1,-1)]
 return {
  'reveal':{'frames':['full_arch']*len(p),'durations_ms':[60]*20+[400],'loop':False,'procedural_effect':{'type':'angular_reveal','progress':p,'center_px':[759.5,899],'direction':'left_to_right','source_pixels_modified':False}},
  'fade':{'frames':['full_arch']*len(op),'durations_ms':[90]*len(op),'loop':True,'procedural_effect':{'type':'opacity','opacity':op,'source_pixels_modified':False}},
  'shimmer':{'frames':['full_arch']*25,'durations_ms':[70]*25,'loop':True,'procedural_effect':{'type':'light_sweep','center_fraction':[-.15+i*1.3/24 for i in range(25)],'width_fraction':.12,'strength':.18,'source_pixels_modified':False}}}

def register(identity):
 base=ROOT/'assets/library/characters'/identity;motion=base/'motions/v001';source_dir=base/'sources/v001';batch=base/BATCH
 initial=batch/'source/generated-v001.png';ids=ORDER[identity]
 images={name:Image.open(motion/(name+'.png')).copy() for name in ids}
 neutral_id='fully_open' if identity=='butterfly' else ('neutral' if identity=='ladybug' else 'full_arch')
 common_ref=169 if identity=='butterfly' else (241 if identity=='ladybug' else 713)
 masks={};anchors={};landmarks={}
 for name,image in images.items():
  mask,anchor,box=anatomy(identity,name,image)
  if identity=='rainbow':anchor=[759.5,899]
  masks[name]=mask;anchors[name]=anchor;landmarks[name]=box
 sheets=[{'id':'initial-v001','source_sheet':rel(initial),'source_sheet_sha256':sha(initial),'reference_height_px':common_ref,'generation_prompt':rel(batch/'provenance/generation-prompt.txt'),'generation_input':rel(batch/'provenance/generation-input.json')}]
 if identity=='butterfly':
  fixed=batch/'source/generated-v003-folded-up.png'
  sheets.append({'id':'folded-standalone-v003','source_sheet':rel(fixed),'source_sheet_sha256':sha(fixed),'reference_height_px':460,'generation_prompt':rel(batch/'provenance/folded-standalone-prompt-v003.txt'),'generation_input':rel(batch/'provenance/folded-standalone-input-v003.json')})
 frames=[]
 for i,name in enumerate(ids):
  im=images[name];visible=list(bbox(im));sheet=sheets[1] if identity=='butterfly' and name=='folded_up' else sheets[0]
  crop=[0,0,*im.size] if identity=='rainbow' or sheet['id']=='folded-standalone-v003' else [(i%2)*512,(i//2)*384,(i%2+1)*512,(i//2+1)*384]
  frame={'id':name,'path':rel(motion/(name+'.png')),'sha256':sha(motion/(name+'.png')),'size_px':list(im.size),'crop_from_sheet_xyxy':crop,
   'sheet_id':sheet['id'],'source_sheet':sheet['source_sheet'],'source_sheet_sha256':sheet['source_sheet_sha256'],
   'anchor_px':anchors[name],'anchor_kind':'base' if identity=='rainbow' else 'center','physical_anchor_kind':'base' if identity=='rainbow' else 'center',
   'body_bbox_px':visible,'subject_bbox_px':visible,'source_bbox_px':visible,'tail_bbox_px':None,'reference_height_px':sheet['reference_height_px'],
   'anchor_measurement':{'method':'manually isolated anatomical ink ROI and alpha>=128 bounds, measured before rendering' if identity!='rainbow' else 'midpoint of complete arch baseline; invariant for partial reveal',
    'landmark':'thorax center' if identity=='butterfly' else ('abdomen/shell core center, excluding opened cases/wings/legs' if identity=='ladybug' else 'complete-arch baseline'),
    'ink_bbox_px':list(landmarks[name]) if landmarks[name] else None,'roi_px':THORAX_ROIS[name] if identity=='butterfly' else (LADY_ABDOMEN[name] if identity=='ladybug' else None)},
   'anatomical_body_bbox_px':CORE_BOXES[identity][name] if identity!='rainbow' else visible,
   'alignment_intent':{'horizontal':'anatomical center anchor' if identity!='rainbow' else 'full arch baseline midpoint','vertical':'same anatomical center anchor' if identity!='rainbow' else 'full arch baseline'},
   'source_pixels_modified':False}
  frames.append(frame)
 neutral=next(f for f in frames if f['id']==neutral_id)
 assert sha(source_dir/'neutral.png')==neutral['sha256']
 common_scale=(200/434 if identity=='butterfly' else (140/223 if identity=='ladybug' else 1200/1371))
 target_reference=common_ref*common_scale
 clips=clips_for(identity)
 for clip_name,clip in clips.items():clip['preview']=rel(motion/f'clip-{clip_name}.gif')
 registration={'schema_version':3,'category':'gimmick','character_id':identity,'version':'v001',
  'common_reference_height_px':common_ref,'reference_height_policy':'One fixed anatomical reference per source sheet; never fit changing individual pose or wing bounds.',
  'reference_calibration':{'neutral_reference_basis':'head-through-abdomen native anatomical length, manually reviewed' if identity!='rainbow' else 'complete arch native visible height at alpha 8',
   'neutral_anatomical_bbox_px':neutral['anatomical_body_bbox_px'],'neutral_sheet_reference_px':common_ref,
   'fixed_per_sheet':True,'per_pose_fit':False,'support_or_center_is_not_whole_wing_centroid':True},
  'source_sheet':rel(initial),'source_sheet_sha256':sha(initial),'sheets':sheets,
  'canonical_neutral':{'frame_id':neutral_id,'path':rel(source_dir/'neutral.png'),'sha256':neutral['sha256']},
  'frames':frames,'clips':clips,'preview':rel(motion/'preview.png'),'motion_preview':rel(motion/'motion-preview.gif'),
  'display_guidance':{'maximum_recommended':{'fully_open_wing_width_px':200} if identity=='butterfly' else ({'neutral_shell_width_px':140} if identity=='ladybug' else {'complete_arch_width_px':1200}),
   'example_loader_height_px':math.floor(target_reference),'maximum_target_anatomical_reference_height_px':target_reference,
   'example_note':'CLI --height uses integer anatomical reference height; floor keeps the rendered width within the recommended cap.',
   'formula':'scale = desired_anatomical_reference_height / frame.reference_height_px; draw at registered anchor. Width recommendations are separate from --height.',
   'native_reference_dimensions':{'neutral_subject_width_px':neutral['body_bbox_px'][2]-neutral['body_bbox_px'][0],'reference_height_px':common_ref},'actual_scene_review_required':True},
  'notes':['Original PNG pixels and alpha are preserved. GIFs are runtime previews, not replacement canonical artworks.','Contact sheets show exact source poses with one physical scale per calibrated sheet; source-specific size calibration preserves the repaired folded butterfly anatomy.']}
 write(motion/'registration.json',registration)
 # Common maximum-display contact sheets: actual subject bounds are measured
 # separately from the anatomical support marker on BOTH axes.
 cell=(320,280) if identity=='butterfly' else ((360,300) if identity=='ladybug' else (1600,940))
 columns=4 if identity!='rainbow' else 1;rows=math.ceil(len(frames)/columns)
 pose_qa=[];boards=[]
 for theme,bg,fg in [('light',(249,247,238,255),(65,42,22,255)),('dark',(35,49,60,255),(249,242,221,255))]:
  board=Image.new('RGBA',(columns*cell[0],rows*cell[1]),bg)
  for i,frame in enumerate(frames):
   name=frame['id'];scale=target_reference/frame['reference_height_px']
   target=(cell[0]/2,cell[1]/2+13) if identity!='rainbow' else (cell[0]/2,820)
   layer=transform(images[name],cell,frame['anchor_px'],target,scale)
   offset=((i%columns)*cell[0],(i//columns)*cell[1])
   board.alpha_composite(layer,offset)
   d=ImageDraw.Draw(board);label(d,(offset[0]+12,offset[1]+10),name,fg)
   content=(12,38,cell[0]-12,cell[1]-12)
   row=bounds_record(layer,content,identity+'/'+name+'/'+theme)
   if identity!='rainbow':
    measured=transform(masks[name],cell,frame['anchor_px'],target,scale)
    # Support marker alignment uses raster ink, never the padded cell box.
    support_box=(target[0]-120,target[1]-100,target[0]+120,target[1]+100)
    report=raster_centering_report(measured,support_box,name=identity+'/'+name+'/anatomical-anchor',tolerance_px=.5,alpha_threshold=128)
    row['anatomical_anchor_alignment']=report
   else:
    actual=[(row['visible_box_xyxy'][0]+row['visible_box_xyxy'][2])/2,row['visible_box_xyxy'][3]]
    dx,dy=actual[0]-target[0],actual[1]-target[1]
    row['baseline_alignment']={'target_px':list(target),'actual_px':actual,'delta_x_px':dx,'delta_y_px':dy,'horizontal_passed':abs(dx)<=.5,'vertical_passed':abs(dy)<=.5,'tolerance_px':.5,'method':'measured full foreground raster: midpoint between outer feet extents and baseline bottom edge; not the empty inner opening'}
   support_pass=(row['baseline_alignment']['horizontal_passed'] and row['baseline_alignment']['vertical_passed']) if identity=='rainbow' else row['anatomical_anchor_alignment']['passed']
   row['scale']=scale;row['no_upscale']=scale<=1;row['passed']=row['contained'] and not row['touches_measurement_edge'] and row['no_upscale'] and support_pass
   pose_qa.append(row)
  board.convert('RGB').save(motion/f'pose-review-{theme}.png');boards.append(board.convert('RGB'))
 boards[0].save(motion/'preview.png')
 # Actual clip GIFs have light and dark panes and stable body supports.
 animation_qa=[];combined=[];combined_durations=[]
 for clip_name,clip in clips.items():
  rendered=[]
  for i,name in enumerate(clip['frames']):
   frame=next(f for f in frames if f['id']==name)
   scale=(340/1371 if identity=='rainbow' else common_scale)
   if identity=='butterfly' and frame['sheet_id']=='folded-standalone-v003':scale=target_reference/frame['reference_height_px']
   panel=(432,360);target=(216,205) if identity!='rainbow' else (216,320)
   reference_dy=clip.get('translation_y_reference_fraction',[0]*len(clip['frames']))[i]
   image=make_effect(images[name],clip.get('procedural_effect'),i,len(clip['frames']))
   layer=transform(image,panel,frame['anchor_px'],target,scale,reference_dy*target_reference)
   out=Image.new('RGB',(864,360));draw=ImageDraw.Draw(out)
   for pane,bg,fg in [(0,(249,247,238),(65,42,22)),(1,(35,49,60),(249,242,221))]:
    tile=Image.new('RGBA',panel,(*bg,255));tile.alpha_composite(layer);out.paste(tile.convert('RGB'),(pane*432,0));label(draw,(pane*432+12,12),identity+' / '+clip_name,fg)
   row=bounds_record(layer,(12,46,420,348),identity+'/'+clip_name+'/'+str(i))
   expected_empty=identity=='rainbow' and ((clip_name=='reveal' and i==0) or (clip_name=='fade' and clip['procedural_effect']['opacity'][i]==0))
   row['expected_invisible_transition']=expected_empty
   row['passed']=(row['empty'] and expected_empty) or (row['contained'] and not row['touches_measurement_edge'])
   animation_qa.append(row);rendered.append(out)
  save_gif(motion/f'clip-{clip_name}.gif',rendered,clip['durations_ms'],clip['loop'])
  clip['preview_sha256']=sha(motion/f'clip-{clip_name}.gif')
  combined.extend(rendered);combined_durations.extend(clip['durations_ms'])
 save_gif(motion/'motion-preview.gif',combined,combined_durations,True)
 registration['preview_sha256']=sha(motion/'preview.png')
 registration['motion_preview_sha256']=sha(motion/'motion-preview.gif')
 write(motion/'registration.json',registration)
 # Current required raw/provenance only: rejected correction and obsolete
 # folded-cell candidates stay preserved locally but are not adopted here.
 current=[initial,batch/'provenance/generation-prompt.txt',batch/'provenance/generation-input.json',batch/'provenance/generated-source-v001.json',batch/'provenance/qa-source-v001.json',batch/'provenance/register-assets-v001.py']
 if identity=='butterfly':current.extend([batch/'source/generated-v003-folded-up.png',batch/'provenance/folded-standalone-prompt-v003.txt',batch/'provenance/folded-standalone-input-v003.json',batch/'provenance/folded-standalone-output-v003.json'])
 manifest={'schema_version':3,'category':'gimmick','character_id':identity,'version':'v001','kind':'adopted-background-gimmick-source-manifest',
  'files':[{'path':rel(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in current],
  'render_registration':{'neutral_path':'neutral.png','neutral_sha256':neutral['sha256'],'size_px':neutral['size_px'],'body_bbox_px':neutral['body_bbox_px'],'neutral_anchor_px':neutral['anchor_px'],'anchor_kind':neutral['anchor_kind'],'physical_anchor_kind':neutral['anchor_kind'],'neutral_natural_height_px':common_ref},
  'registration':rel(motion/'registration.json'),'source_pixels_modified':False,
  'selection_policy':'Only explicitly selected current source files are required. Unselected original cells and rejected generation candidates remain local provenance.'}
 write(source_dir/'source-manifest.json',manifest)
 item={'id':identity,'category':'gimmick','name_ja':NAMES[identity][0],'name_en':NAMES[identity][1],
  'source_manifest_path':rel(source_dir/'source-manifest.json'),'source_manifest_sha256':sha(source_dir/'source-manifest.json'),
  'registration':rel(motion/'registration.json'),'registration_sha256':sha(motion/'registration.json'),
  'preview':rel(motion/'preview.png'),'motion_preview':rel(motion/'motion-preview.gif')}
 # Direct private validation is intentional: shared reservations remain active
 # and only root may release them or refresh global inventories.
 library._verify_pose_registration_locked(ROOT,registration,identity,pending=[])
 library._gimmick_index_item_locked(ROOT,item,pending=[])
 qa={'schema_version':1,'asset_id':identity,'checked_at_utc':datetime.now(timezone.utc).isoformat(),
  'status':'pass' if all(row['passed'] for row in pose_qa+animation_qa) else 'needs_review',
  'scope':'new source/crop/registration/native and recommended-size preview checks; no completed production MP4 is claimed',
  'source_and_crop_byte_pixels_verified':True,'neutral_png_byte_identical_to_selected_frame':True,'source_alpha_preserved':True,
  'individual_schema3_and_collection_item_validation':'pass with explicit pending=[]; no global locks/refresh',
  'pose_count':len(frames),'clip_count':len(clips),'pose_alignment':pose_qa,'animation_bounds':animation_qa,
  'maximum_recommended_display':registration['display_guidance'],'notes':['Body/subject bounds cover the full visible subject for schema compatibility; anatomical calibration and support landmarks are recorded separately.','GIFs are discrete key-pose and procedural-effect previews; scene timing, paths, number/subtitle clearance and final continuous-video review are separate.']}
 write(motion/'qa-registration-v001.json',qa)
 return item,{'id':identity,'status':qa['status'],'poses':len(frames),'clips':list(clips),'pose_failures':[r['name'] for r in pose_qa if not r['passed']],'animation_failures':[r['name'] for r in animation_qa if not r['passed']]}

if __name__=='__main__':
 items=[]
 for identity in ORDER:
  item,summary=register(identity);items.append(item);print(json.dumps(summary,ensure_ascii=False),flush=True)
 write(Path('/tmp/gimmick-items-butterfly-ladybug-rainbow.json'),items)
