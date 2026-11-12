"""Canonical-body acting for the arithmetic episode, using new local artwork.

Only recorded arm/eye/mouth masks move. Canonical head, spines, trunk and feet
stay on the registered body. No whole-body crossfade or per-pose fit is used.
"""
from __future__ import annotations
from functools import lru_cache
import hashlib
import json
import math
import statistics
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[1]
BATCH=ROOT/'assets/library/characters/hedgehog/generation-batches/arithmetic-production-20261112-01a1cdca-b'
CANONICAL=ROOT/'assets/library/characters/hedgehog/sources/v003/neutral.png'
STATES=('neutral','blink','greet','offer','present_left','present_right','think','surprise','relax','stretch','goodbye')
REFERENCE_HEIGHT=560.0
WORK_SIZE=(800,800)
WORK_FOOT=(400.,740.)
SCALE=REFERENCE_HEIGHT/1039.
ORIGIN=(WORK_FOOT[0]-611*SCALE,WORK_FOOT[1]-1166*SCALE)
REST_POLYGONS={
 'left':[(448,707),(408,734),(379,766),(369,795),(379,825),(405,849),(439,869),(470,880),(499,876),(516,857),(524,833),(518,807),(497,780),(469,754)],
 'right':[(786,707),(825,734),(855,766),(867,795),(857,825),(832,849),(798,869),(768,880),(739,876),(721,857),(712,833),(718,807),(739,780),(766,754)]}
REST_ROOTS={'left':(448,714),'right':(786,714)}
REST_TIPS={'left':(470,854),'right':(759,854)}
GOALS={
 'wave':(1,[(202,320),(174,301),(154,283),(133,276),(118,281),(113,296),(120,320),(139,342),(163,356),(185,364),(202,355)],(195,341),(135,304)),
 'open_left':(3,[(207,319),(185,325),(151,332),(131,341),(122,354),(126,367),(145,379),(170,381),(190,374),(207,365)],(201,347),(148,359)),
 'open_right':(3,[(366,319),(392,328),(421,333),(446,341),(455,354),(452,368),(434,380),(408,381),(385,374),(366,363)],(373,347),(429,359)),
 'point':(2,[(389,303),(420,290),(451,269),(476,251),(496,249),(513,258),(518,273),(509,290),(488,309),(455,330),(417,345),(397,336)],(406,324),(485,277))}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def smooth(t):
 t=max(0.,min(1.,t));return t*t*(3-2*t)
def point(xy):return (ORIGIN[0]+xy[0]*SCALE,ORIGIN[1]+xy[1]*SCALE)
def envelope(p):
 if p<.25:return smooth(p/.25)
 if p<.68:return 1.
 return smooth((1-p)/.32)
def part(im,poly):
 mask=Image.new('L',im.size);ImageDraw.Draw(mask).polygon(poly,fill=255)
 out=im.copy();out.putalpha(ImageChops.multiply(im.getchannel('A'),mask));return out

@lru_cache(maxsize=1)
def resources():
 original=Image.open(CANONICAL).convert('RGBA');canonical=Image.new('RGBA',WORK_SIZE)
 small=original.resize((round(original.width*SCALE),round(original.height*SCALE)),Image.Resampling.LANCZOS)
 canonical.alpha_composite(small,tuple(round(v) for v in ORIGIN))
 arms=[Image.open(BATCH/'frames'/f'arms-{i}.png').convert('RGBA') for i in range(4)]
 faces=[Image.open(BATCH/'frames'/f'faces-{i}.png').convert('RGBA') for i in range(4)]
 clean=Image.new('RGBA',WORK_SIZE);cs=REFERENCE_HEIGHT/538.
 clean_sprite=arms[0].resize((round(627*cs),round(627*cs)),Image.Resampling.LANCZOS)
 clean.alpha_composite(clean_sprite,(round(WORK_FOOT[0]-330*cs),round(WORK_FOOT[1]-565*cs)))
 # Match the generated clean skin to the canonical belly at each height.
 # This is a runtime component color transform; the source stays unchanged.
 cp=canonical.load();np=clean.load()
 corrections=[]
 for yy in range(480,615):
  wanted=[statistics.median(cp[xx,yy][cc] for xx in range(380,435)) for cc in range(3)]
  donor=[statistics.median(np[xx,yy][cc] for xx in range(380,435)) for cc in range(3)]
  corrections.append([wanted[cc]-donor[cc] for cc in range(3)])
 for yy,delta in zip(range(480,615),corrections):
  for xx in range(245,560):
   pixel=np[xx,yy];np[xx,yy]=tuple(round(max(0,min(255,pixel[cc]+delta[cc]))) for cc in range(3))+(pixel[3],)
 mask=Image.new('L',WORK_SIZE);d=ImageDraw.Draw(mask)
 for box in [(355,700,543,904),(694,700,886,904)]:d.rounded_rectangle((*point(box[:2]),*point(box[2:])),radius=12,fill=255)
 mask=mask.filter(ImageFilter.GaussianBlur(3.5))
 body=canonical.copy();body.paste(clean,(0,0),mask)
 goals={name:(part(arms[i],poly),root,tip) for name,(i,poly,root,tip) in GOALS.items()}
 rest={side:part(original,poly) for side,poly in REST_POLYGONS.items()}
 return {'canonical':canonical,'body':body,'rest':rest,'goals':goals,'faces':faces}

def warp(art,root,tip,target_root,target_vector):
 sx,sy=tip[0]-root[0],tip[1]-root[1];dx,dy=target_vector;den=sx*sx+sy*sy
 a=(sx*dx+sy*dy)/den;b=(sx*dy-sy*dx)/den;det=a*a+b*b
 tx=target_root[0]-a*root[0]+b*root[1];ty=target_root[1]-b*root[0]-a*root[1]
 return art.transform(WORK_SIZE,Image.Transform.AFFINE,(a/det,b/det,(-a*tx-b*ty)/det,-b/det,a/det,(b*tx-a*ty)/det),Image.Resampling.BICUBIC)

def arm(side,goal,amount,target_vector,wag=0.):
 r=resources();root,tip=REST_ROOTS[side],REST_TIPS[side]
 rest=((tip[0]-root[0])*SCALE,(tip[1]-root[1])*SCALE)
 aa,bb=math.atan2(rest[1],rest[0]),math.atan2(target_vector[1],target_vector[0]);delta=(bb-aa+math.pi)%(2*math.pi)-math.pi
 angle=aa+delta*amount+math.radians(wag)*amount
 length=math.hypot(*rest)*(1-amount)+math.hypot(*target_vector)*amount
 vector=(math.cos(angle)*length,math.sin(angle)*length)
 old=warp(r['rest'][side],root,tip,point(root),vector)
 if goal is None:result=old
 else:
  art,gr,gt=r['goals'][goal];new=warp(art,gr,gt,point(root),vector)
  # Shared shoulder and paw endpoints prevent two hands in the local art blend.
  result=Image.blend(old.convert('RGBa'),new.convert('RGBa'),amount).convert('RGBA')
 if amount>0:
  # Fade the shoulder insert along its bone, rather than exposing the hard
  # polygon cut across the canonical neck/belly. Original PNGs stay untouched.
  rr=point(root);length=math.hypot(*vector);ux,uy=vector[0]/length,vector[1]/length
  ramp=Image.new('L',(2,4096),255);dr=ImageDraw.Draw(ramp)
  for yy in range(256):dr.line((0,yy,1,yy),fill=round(255*smooth((yy-128)/128)))
  width=min(12.,length*.2);factor=128/width
  feather=ramp.transform(WORK_SIZE,Image.Transform.AFFINE,(0,0,.5,factor*ux,factor*uy,128-factor*(rr[0]*ux+rr[1]*uy)),Image.Resampling.BICUBIC)
  feather=Image.blend(Image.new('L',WORK_SIZE,255),feather,amount)
  result.putalpha(ImageChops.multiply(result.getchannel('A'),feather))
 return result

def cream_patch(im,box,shape='ellipse'):
 x0,y0,x1,y1=[round(v) for v in box]
 patch=resources()['canonical'].crop((390,455,414,475)).resize((x1-x0,y1-y0),Image.Resampling.BICUBIC)
 mask=Image.new('L',patch.size);md=ImageDraw.Draw(mask)
 if shape=='ellipse':md.ellipse((1,1,patch.width-2,patch.height-2),fill=255)
 else:md.rounded_rectangle((1,1,patch.width-2,patch.height-2),radius=5,fill=255)
 im.paste(patch,(x0,y0),mask.filter(ImageFilter.GaussianBlur(2.5)))

def feature(cell,box,kind='stroke'):
 out=cell.crop(box).convert('RGBA');pix=out.load()
 for y in range(out.height):
  for x in range(out.width):
   rr,gg,bb,aa=pix[x,y];lum=(rr+2*gg+bb)/4
   keep=lum<150 or (kind=='mouth' and rr>1.35*gg and gg<175)
   pix[x,y]=(rr,gg,bb,aa if keep else 0)
 return out

def blink(im,amount):
 if amount<.01:return
 source=resources()['canonical']
 for i,original_box in enumerate([(442,421,560,579),(691,421,807,579)]):
  box=tuple(round(v) for v in (*point(original_box[:2]),*point(original_box[2:])))
  cream_patch(im,(box[0]-4,box[1]-4,box[2]+4,box[3]+4))
  if amount>.76:
   eye=feature(resources()['faces'][1],(180,305,270,355) if i==0 else (350,305,445,355))
   eye=eye.resize((60,20),Image.Resampling.LANCZOS)
  else:
   eye=source.crop(box).convert('RGBA');px=eye.load()
   # Keep only the actual brown/white eye, never an opaque rectangular skin
   # crop: compressing the latter produced a horizontal cream band mid-blink.
   for yy in range(eye.height):
    for xx in range(eye.width):
     rr,gg,bb,aa=px[xx,yy];lum=(rr+2*gg+bb)/4
     keep=lum<165 or (rr>244 and gg>244 and bb>232)
     px[xx,yy]=(rr,gg,bb,aa if keep else 0)
   eye_mask=Image.new('L',eye.size);ImageDraw.Draw(eye_mask).ellipse((0,0,eye.width-1,eye.height-1),fill=255)
   eye.putalpha(ImageChops.multiply(eye.getchannel('A'),eye_mask))
  h=eye.height if amount>.76 else max(3,round(eye.height*(1-.96*amount)))
  eye=eye.resize((eye.width,h),Image.Resampling.LANCZOS)
  im.alpha_composite(eye,(round((box[0]+box[2]-eye.width)/2),round((box[1]+box[3]-h)/2)))

def delighted_mouth(im,amount):
 if amount<.01:return
 box=(*point((530,552)),*point((720,642)));cream_patch(im,box,shape='rounded')
 center=point((626,595))
 if amount<.3:
  art=resources()['canonical'].crop(tuple(round(v) for v in box));width=art.width;height=max(2,round(art.height*(1-amount/.3)))
 else:
  art=feature(resources()['faces'][2],(276,375,349,425),'mouth');width=38;height=max(2,round(36*(amount-.3)/.7))
 art=art.resize((width,height),Image.Resampling.LANCZOS)
 im.alpha_composite(art,(round(center[0]-width/2),round(center[1]-height/2)))
 # Retain the exact nose and its short stem above the new small mouth.
 nose_box=tuple(round(v) for v in (*point((579,512)),*point((667,572))))
 im.alpha_composite(resources()['canonical'].crop(nose_box),nose_box[:2])

@lru_cache(maxsize=512)
def actor(state,tick):
 p=tick/120.;r=resources()
 if state=='neutral':return r['canonical']
 if state=='blink':
  result=r['canonical'].copy();blink(result,math.sin(p*math.pi)**2);return result
 amount=envelope(p)
 if amount<.0001:return r['canonical']
 result=r['body'].copy();lg=rg=None;lv=(12,75);rv=(-15,75);wag=0.
 if state in ('greet','goodbye'):
  lg='wave';lv=(-55,-57);wag=10*math.sin((p-.25)/.43*math.pi*4) if .25<p<.68 else 0
 elif state=='offer':lg,rg='open_left','open_right';lv,rv=(-67,-3),(67,-3)
 elif state=='present_left':lg='wave';lv=(-70,-68)
 elif state=='present_right':rg='point';rv=(70,-68)
 elif state=='think':lg='wave';lv=(54,-40)
 elif state=='surprise':lg,rg='open_left','open_right';lv,rv=(-53,-20),(53,-20)
 elif state=='relax':lv,rv=(6,68),(-6,68)
 elif state=='stretch':lg,rg='open_left','open_right';lv,rv=(-65,-74),(65,-74)
 # New whole-arm drawings remain candidates: their shoulder cuts did not
 # preserve the canonical contour. Articulate the proven canonical paws over
 # the newly generated clean skin instead of accepting those cut seams.
 result.alpha_composite(arm('left',None,amount,lv,wag));result.alpha_composite(arm('right',None,amount,rv))
 # A quiet carry reaction retains the canonical smile. The generated open
 # mouth remains an unselected candidate: its return did not read naturally.
 if state=='stretch':blink(result,.9*amount)
 if state=='relax' and .38<p<.58:blink(result,math.sin((p-.38)/.20*math.pi)**2)
 return result

@lru_cache(maxsize=1024)
def sprite(state,tick,height):
 im=actor(state,tick);scale=height/REFERENCE_HEIGHT
 out=im.resize((round(800*scale),round(800*scale)),Image.Resampling.LANCZOS)
 return out,out.getchannel('A').point(lambda v:255 if v>=16 else 0).getbbox()

def draw_character(image,state,phase,height=280,foot=(960,1010)):
 if state not in STATES:raise ValueError(f'Unknown arithmetic acting state: {state}')
 if not 0<=phase<=1 or not 0<height<=350:raise ValueError('Actor phase/height outside accepted design')
 tick=round(phase*120)
 if state=='neutral':tick=0
 im,bbox=sprite(state,tick,float(height));scale=height/REFERENCE_HEIGHT
 xy=(round(foot[0]-WORK_FOOT[0]*scale),round(foot[1]-WORK_FOOT[1]*scale))
 if image.mode=='RGBA':image.alpha_composite(im,xy)
 else:image.paste(im,xy,im)
 visible=[bbox[0]+xy[0],bbox[1]+xy[1],bbox[2]+xy[0],bbox[3]+xy[1]]
 return {'state':state,'phase':tick/120,'registered_body_height_px':height,'registration_body_height_px':REFERENCE_HEIGHT,
  'foot_anchor_px':list(foot),'visible_bbox':visible,'visible_box_xyxy':visible,'visible_bbox_px':visible,
  'foot_delta_x_px':0.,'foot_delta_y_px':visible[3]-foot[1],'raster_scale':scale,
  'whole_body_crossfade':False,'canonical_head_trunk_feet_retained':True,'local_bone_alignment':True,
  'source_ids':['hedgehog-canonical-v003','arithmetic-production-arms-4','arithmetic-production-faces-4']}

def registration():
 return {'schema_version':1,'kind':'arithmetic-stable-body-local-articulation','owner':'codex:arithmetic-production:01a1cdca',
  'character_id':'hedgehog','canonical':{'path':str(CANONICAL.relative_to(ROOT)),'sha256':sha(CANONICAL),'reference_height_px':1039,'anchor_px':[611,1166]},
  'working_canvas_px':list(WORK_SIZE),'working_body_height_px':REFERENCE_HEIGHT,'working_foot_anchor_px':list(WORK_FOOT),
  'maximum_display_body_height_px':350,'maximum_scale':350/REFERENCE_HEIGHT,
  'states':list(STATES),'new_source_full_body_drawings':4,'new_source_head_drawings':4,
  'source_sheets':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'cells':4} for p in (BATCH/'source/arms-source.png',BATCH/'source/faces-source.png')],
  'common_full_body_sheet_reference_height_px':538.,'rest_polygons':REST_POLYGONS,'candidate_goal_parts_not_used':GOALS,
  'used_new_drawing_regions':[{'sheet':'arms-source.png','cell':0,'role':'clean cream skin under moving canonical arms'},
   {'sheet':'faces-source.png','cell':1,'role':'calm closed eyelid strokes'}],
  'unused_new_drawings':'arms1/2/3 retain shoulder-cut seam findings; faces0/3 are optional gaze candidates; face2 mouth return had an unnatural compressed contour and is not runtime adopted',
  'selection_policy':'Episode-local masks only; full generated heads/torso/feet are not used as whole-character replacements. Neutral remains canonical.',
  'airborne':False,'independent_pose_scaling':False,'whole_body_crossfade':False}

if __name__=='__main__':
 (BATCH/'registration.json').write_text(json.dumps(registration(),ensure_ascii=False,indent=2)+'\n')
 out=Image.new('RGBA',(2200,1150),'#fff8eb');d=ImageDraw.Draw(out)
 for i,state in enumerate(STATES):
  x=i%6*360;y=i//6*560
  draw_character(out,state,.5,350,(x+180,y+420));d.text((x+20,y+440),state,fill='#442211')
 out.convert('RGB').save(BATCH/'previews/all-states-native350.png')
 print(json.dumps({'module':str(Path(__file__).relative_to(ROOT)),'registration':str((BATCH/'registration.json').relative_to(ROOT))}))
