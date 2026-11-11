"""Non-destructive exact cells + documented local arm/eye composites.
Generated source RGBA is never edited; output frames are derived composites.
"""
from PIL import Image,ImageDraw,ImageFilter,ImageChops
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[7]
B=Path(__file__).resolve().parents[1]
def rel(p):return p.relative_to(ROOT).as_posix()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bbox(im,t=8):return im.getchannel('A').point(lambda v:255 if v>=t else 0).getbbox()
def align(src,size,scale,offset):
 out=Image.new('RGBA',size);rs=src.resize((round(src.width*scale),round(src.height*scale)),Image.Resampling.LANCZOS);out.paste(rs,tuple(round(v) for v in offset));return out
sheet=Image.open(B/'source/pose-sheet-attempt001.png').convert('RGBA')
ids=['wave_prepare','wave_in','wave_out','notice_prepare','notice_full','watch_blink']
raw=[]
for i,id in enumerate(ids):
 x=(i%3)*512;y=(i//3)*512;rect=[x,y,x+512,y+512];im=sheet.crop(rect);p=B/'candidates'/f'{id}.png';im.save(p)
 raw.append({'id':id,'path':rel(p),'sha256':sha(p),'crop_from_sheet_xyxy':rect,'anchor_px':[253,475],'reference_height_px':456,'exact_source_cell':True,'alpha8_bbox':bbox(im)})
neutralp=ROOT/'assets/library/characters/siamese-cat/sources/v005/neutral.png';watchp=ROOT/'assets/library/characters/siamese-cat/motions/fibonacci-v001/watch_left.png'
neutral=Image.open(neutralp).convert('RGBA');watch=Image.open(watchp).convert('RGBA')
frames=[]
for id in ids:
 src=Image.open(B/'candidates'/f'{id}.png').convert('RGBA')
 if id.startswith('wave_'):
  base=neutral;scale=1070/456;offset=[-25,125];anchor=[611,1189];ref=1070
  aligned=align(src,base.size,scale,offset)
  polygon=[[150,590],[430,590],[520,748],[510,946],[300,962],[210,820]]
  mask=Image.new('L',base.size);ImageDraw.Draw(mask).polygon(polygon,fill=255);mask=mask.filter(ImageFilter.GaussianBlur(3))
  # Head/ears/whiskers remain exactly canonical, including their alpha edges.
  protect=base.getchannel('A').point(lambda v:255 if v>0 else 0)
  limit=Image.new('L',base.size);ImageDraw.Draw(limit).rectangle((0,0,base.width,710),fill=255)
  protect=ImageChops.multiply(protect,limit);mask=ImageChops.subtract(mask,protect)
  result=Image.composite(aligned,base,mask)
  method={'kind':'local-generated-forepaw-overlay','source_to_base':{'scale':scale,'translate_xy':offset},'replace_polygon_xy':polygon,'feather_px':3,'protected_original_nonzero_alpha_region_y_le':710,'base_pose':'neutral','source_body_scale_notes':'Generated cell standing scale is456px; arm overlay has one shared mapping for all three poses. Runtime full-body registration is canonical1070px; no per-pose body scaling.'}
 else:
  base=watch;scale=1.33;offset=[-5,-9.5];anchor=[313.5,588];ref=560
  aligned=align(src,base.size,scale,offset)
  # Two socket patches only. Every head contour/whisker/body/foot pixel stays fixed.
  boxes=[[202,153,272,247],[315,162,389,259]]
  mask=Image.new('L',base.size);d=ImageDraw.Draw(mask)
  for box in boxes:d.rounded_rectangle(box,radius=15,fill=255)
  mask=mask.filter(ImageFilter.GaussianBlur(2))
  result=Image.composite(aligned,base,mask)
  method={'kind':'local-generated-eye-socket-overlay','source_to_base':{'scale':scale,'translate_xy':offset},'replace_boxes_xyxy':boxes,'feather_px':2,'base_pose':'watch_left','source_body_scale_notes':'Local eye registration measured from the two stable socket centers. Only sockets change; standing scale remains adopted watch560px.'}
 p=B/'frames'/f'{id}.png';result.save(p)
 diff=ImageChops.difference(result,base)
 frames.append({'id':id,'path':rel(p),'sha256':sha(p),'anchor_px':anchor,'reference_height_px':ref,'eyes_closed':id=='watch_blink','base_path':rel(neutralp if id.startswith('wave_') else watchp),'base_sha256':sha(neutralp if id.startswith('wave_') else watchp),'source_id':id,'source_path':rel(B/'candidates'/f'{id}.png'),'source_sha256':sha(B/'candidates'/f'{id}.png'),'derivation':method,'changed_bounds_rgba':diff.getbbox(),'alpha8_bbox':bbox(result),'size_px':list(result.size)})
r={'kind':'fibonacci-v002-episode-local-character-art','version':2,'source_sheet':{'path':rel(B/'source/pose-sheet-attempt001.png'),'sha256':sha(B/'source/pose-sheet-attempt001.png'),'size_px':list(sheet.size),'grid':[3,2]},'reservation_id':'fibonacci-recheck-v002-01a1cae3','owner':'codex:local:01a1cae3-5e92-7b31-b0f7-5374c0f76c4a','source_pixels_modified':False,'derived_runtime_composites':True,'raw_cells':raw,'common_reference_height_px':{'wave_family':1070,'watch_family':560},'target_body_height_px':400,'ground_foot_anchor_px':[1655,990],'frames':frames}
(B/'registration.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
# Native-scale front and watching families; title outside every sprite.
font=None
canvas=Image.new('RGB',(7*420,530),'#cbdedb');d=ImageDraw.Draw(canvas)
for i,(id,im,ref,anchor) in enumerate([('canonical neutral',neutral,1070,[611,1189]),*[(f['id'],Image.open(ROOT/f['path']).convert('RGBA'),f['reference_height_px'],f['anchor_px']) for f in frames[:3]],('adopted watch',watch,560,[313.5,588]),*[(f['id'],Image.open(ROOT/f['path']).convert('RGBA'),f['reference_height_px'],f['anchor_px']) for f in frames[3:5]]]):
 scale=400/ref;rs=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS);pos=(round(i*420+210-anchor[0]*scale),round(470-anchor[1]*scale));canvas.paste(rs,pos,rs);d.text((i*420+10,10),id,fill='#253f42');d.line((i*420,470,i*420+420,470),fill='#7a9999')
canvas.save(B/'previews/native-source-composite-comparison.png')
print(json.dumps({'registration':rel(B/'registration.json'),'frames':[{k:f[k] for k in ('id','changed_bounds_rgba','alpha8_bbox')} for f in frames]},indent=2))
