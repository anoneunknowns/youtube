"""Episode-local Onagadori acting with a canonical body, tail and feet.

A preserved preproduction open-wing drawing supplies a back-layer far wing.
New closed-eyelid artwork supplies the blink and unmarked cheek insert.
No full-body crossfades are used.
All image sources remain immutable; masks/affines are runtime compositing.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / 'assets/library/characters/onagadori/generation-batches/thue-morse-production-20261112-01a1ce1d'
CANONICAL = ROOT / 'assets/library/characters/onagadori/sources/v002/neutral.png'
REFERENCE_HEIGHT = 368.
SOURCE_HEIGHT = 736.
SOURCE_FOOT = (350., 819.)
WORK_SIZE = (1080, 500)
WORK_FOOT = (300., 460.)
SOURCE_SCALE = .5
ORIGIN = (125., 50.5)
STATES = ('neutral','blink','greet','source_look','result_look','present','think','aha','relax','stretch','goodbye')
EYE_BOX = (238,228,286,280)
DONOR = ROOT / 'assets/library/characters/onagadori/generation-batches/thue-morse-preproduction-20261112-01a1ce1d/frames/present.png'
FAR_WING_ROOT = (326.,493.)
FAR_WING_TARGET = (320.,500.)
FAR_WING_POLYGON = [(332,486),(312,466),(281,433),(248,393),(214,352),(175,310),(136,264),(116,239),(108,232),(99,235),(93,247),(96,271),(108,300),(129,331),(111,324),(98,323),(91,329),(88,343),(94,365),(108,389),(131,412),(153,426),(130,420),(116,420),(108,429),(110,446),(125,465),(145,481),(164,490),(181,498),(172,506),(178,521),(199,536),(225,544),(253,545),(278,539),(294,525),(311,506),(329,492)]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def smooth(x):
    x = max(0., min(1., x))
    return x*x*(3-2*x)


def envelope(p):
    if p < .24:
        return smooth(p/.24)
    if p < .67:
        return 1.
    return smooth((1-p)/.33)


def point(p):
    return ORIGIN[0]+p[0]*SOURCE_SCALE, ORIGIN[1]+p[1]*SOURCE_SCALE


def part(im, polygon):
    m = Image.new('L',im.size)
    ImageDraw.Draw(m).polygon(polygon,fill=255)
    out = im.copy()
    out.putalpha(ImageChops.multiply(im.getchannel('A'),m))
    return out


def work_source(im):
    result = Image.new('RGBA',WORK_SIZE)
    small = im.resize((round(im.width*.5),round(im.height*.5)),Image.Resampling.LANCZOS)
    result.alpha_composite(small,(round(ORIGIN[0]),round(ORIGIN[1])))
    return result


@lru_cache(maxsize=1)
def resources():
    original=Image.open(CANONICAL).convert('RGBA')
    canonical=work_source(original)
    face=Image.open(BATCH/'source/blink-source.png').convert('RGBA')
    # The generated eyelid is isolated as a component: source images are not
    # cleaned or changed. Dark warm ink inside this small facial ROI is used.
    lid=face.crop((402,520,555,611)).convert('RGBA')
    px=lid.load()
    for y in range(lid.height):
        for x in range(lid.width):
            r,g,b,a=px[x,y]
            px[x,y]=(r,g,b,a if r<180 and g<135 and b<100 else 0)
    lid=lid.crop(lid.getchannel('A').getbbox())
    eye=original.crop(EYE_BOX).convert('RGBA')
    ep=eye.load()
    for y in range(eye.height):
        for x in range(eye.width):
            r,g,b,a=ep[x,y]
            ep[x,y]=(r,g,b,a if r<180 and g<135 and b<100 else 0)
    far_wing=part(Image.open(DONOR).convert('RGBA'),FAR_WING_POLYGON)
    return {'original':original,'canonical':canonical,'far_wing':far_wing,'lid':lid,'eye':eye,'face_source':face}


def blink(im,amount):
    if amount<.01:
        return
    res=resources();x0,y0=point(EYE_BOX[:2]);x1,y1=point(EYE_BOX[2:])
    # Skin donor is unmarked cheek from the newly generated closed-eye face.
    patch=res['face_source'].crop((580,465,640,540)).resize((round(x1-x0)+8,round(y1-y0)+8),Image.Resampling.LANCZOS)
    mask=Image.new('L',patch.size);ImageDraw.Draw(mask).ellipse((1,1,patch.width-2,patch.height-2),fill=255)
    im.paste(patch,(round(x0)-4,round(y0)-4),mask.filter(ImageFilter.GaussianBlur(1.5)))
    if amount>.78:
        art=res['lid'];width=22;height=9
    else:
        art=res['eye'];width=20;height=max(2,round(23*(1-amount)))
    art=art.resize((width,height),Image.Resampling.LANCZOS)
    im.alpha_composite(art,(round((x0+x1-width)/2),round((y0+y1-height)/2)))


def gaze(im,dx,dy):
    """Move the preserved plain oval eye locally over new unmarked face skin."""
    if abs(dx)+abs(dy)<.02:
        return im
    res=resources();x0,y0=point(EYE_BOX[:2]);x1,y1=point(EYE_BOX[2:])
    patch=res['face_source'].crop((580,465,640,540)).resize((round(x1-x0)+8,round(y1-y0)+8),Image.Resampling.LANCZOS)
    mask=Image.new('L',patch.size);ImageDraw.Draw(mask).ellipse((1,1,patch.width-2,patch.height-2),fill=255)
    im.paste(patch,(round(x0)-4,round(y0)-4),mask.filter(ImageFilter.GaussianBlur(1.5)))
    art=res['eye'].resize((20,23),Image.Resampling.LANCZOS)
    im.alpha_composite(art,(round((x0+x1-20)/2+dx),round((y0+y1-23)/2+dy)))
    return im


def far_wing(amount,degrees):
    """A single far wing emerges from behind the unchanged canonical body."""
    scale=SOURCE_SCALE*(736./637.)*smooth(min(1.,amount/.35))
    if scale<.0001:
        return Image.new('RGBA',WORK_SIZE)
    angle=math.radians(100*(1-amount)+degrees*amount)
    a=scale*math.cos(angle);b=scale*math.sin(angle)
    dest=point(FAR_WING_TARGET)
    tx=dest[0]-a*FAR_WING_ROOT[0]+b*FAR_WING_ROOT[1]
    ty=dest[1]-b*FAR_WING_ROOT[0]-a*FAR_WING_ROOT[1]
    det=a*a+b*b
    return resources()['far_wing'].transform(WORK_SIZE,Image.Transform.AFFINE,(a/det,b/det,(-a*tx-b*ty)/det,-b/det,a/det,(b*tx-a*ty)/det),Image.Resampling.BICUBIC)


@lru_cache(maxsize=260)
def actor(state,tick):
    if state not in STATES:
        raise ValueError(state)
    p=max(0.,min(1.,tick/120.));r=resources()
    if state=='neutral':
        return r['canonical']
    if state=='blink':
        im=r['canonical'].copy();blink(im,math.sin(p*math.pi)**2);return im
    amount=envelope(p)
    if amount<.00001:
        return r['canonical']
    goals={'greet':-30,'goodbye':-30,'present':0,'aha':-18,'stretch':-5}
    if state in goals:
        wag=0.
        if state in ('greet','goodbye') and .25<p<.67:
            wag=8*math.sin((p-.25)/.42*math.pi*4)
        im=far_wing(amount,goals[state]+wag)
        # Front body covers the near shoulder and the inward/folded part of
        # the far wing. A second wing is anatomically intentional, not ghosts.
        im.alpha_composite(r['canonical'])
    else:
        im=r['canonical'].copy()
    shift={'source_look':(-2.,-2.),'result_look':(1.,-3.),'present':(-1.,-2.),'think':(0.,3.),'aha':(-1.,-2.),'stretch':(0.,-2.)}.get(state,(0.,0.))
    im=gaze(im,shift[0]*amount,shift[1]*amount)
    if state=='relax' and .30<p<.72:
        blink(im,math.sin((p-.30)/.42*math.pi)**2)
    return im


@lru_cache(maxsize=800)
def sprite(state,tick,height):
    im=actor(state,int(tick));scale=height/REFERENCE_HEIGHT
    out=im.resize((round(WORK_SIZE[0]*scale),round(WORK_SIZE[1]*scale)),Image.Resampling.LANCZOS)
    bbox=out.getchannel('A').point(lambda v:255 if v>=8 else 0).getbbox()
    return out,bbox


def draw_character(image,state='neutral',phase=0.,height=180,foot=(1450,1035)):
    if state not in STATES or not 0<=phase<=1 or not 0<height<=320:
        raise ValueError((state,phase,height))
    tick=round(phase*120)
    if state=='neutral':tick=0
    im,bbox=sprite(state,tick,float(height));scale=height/REFERENCE_HEIGHT
    xy=(round(foot[0]-WORK_FOOT[0]*scale),round(foot[1]-WORK_FOOT[1]*scale))
    if image.mode=='RGBA':image.alpha_composite(im,xy)
    else:image.paste(im,xy,im)
    b=[bbox[0]+xy[0],bbox[1]+xy[1],bbox[2]+xy[0],bbox[3]+xy[1]]
    return {'state':state,'phase':tick/120.,'body_display_height_px':height,'registered_body_height_px':height,
            'source_reference_height_px':736,'working_reference_height_px':REFERENCE_HEIGHT,'foot_anchor_px':list(foot),
            'visible_box_xyxy':b,'visible_bbox':b,'visible_bbox_px':b,'raster_scale':scale,
            'whole_body_crossfade':False,'canonical_trunk_feet_tail_retained':True,
            'local_head_tilt_degrees':0.,'local_eye_gaze':state in ('source_look','result_look','think','aha','present','stretch'),
            'new_source_roles':['closed eyelid and cheek skin'],'reused_source_role':'preproduction open wing as far-wing back layer','mirrored':False}


class Actor:
    """Convenience adapter with the same public draw arguments as the module."""
    def draw(self,image,state='neutral',phase=0.,height=180,foot=(1450,1035)):
        return draw_character(image,state,phase,height,foot)


def registration():
    return {'schema_version':1,'id':'thue-morse-canonical-local-articulation-v001',
        'owner':'codex:thue-morse-production:01a1ce1d','character_id':'onagadori','state':'production_motion_candidate',
        'canonical':{'path':str(CANONICAL.relative_to(ROOT)),'sha256':sha(CANONICAL),'reference_height_px':736,'anchor_px':[350,819]},
        'working_canvas_px':list(WORK_SIZE),'working_body_height_px':REFERENCE_HEIGHT,'working_foot_anchor_px':list(WORK_FOOT),
        'maximum_display_body_height_px':320,'maximum_scale':320/REFERENCE_HEIGHT,'states':list(STATES),
        'source_images':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in [BATCH/'source/clean-source.png',BATCH/'source/blink-source.png']],
        'reused_source_images':[{'path':str(DONOR.relative_to(ROOT)),'sha256':sha(DONOR),'role':'far wing only; never a whole-body replacement'}],
        'new_generated_images':2,'new_full_body_drawing':1,'new_head_drawing':1,
        'used_regions':{'blink-source.png':'closed eyelid ROI and white cheek skin'},
        'unused_new_regions':{'clean-source.png':'retained candidate; canonical folded-wing extraction had cut upper-back contours and was not selected'},
        'canonical_parts_retained':['comb/head geometry','neck','body contour','folded wing artwork','feet','entire long tail'],
        'head_tilt':'none; early neck rotation candidate rejected for compositing seam. Quiet gaze uses the same canonical oval eye locally moved over generated cheek skin.',
        'far_wing':'one reused open-wing insert below canonical body; near wing remains folded and unchanged; ingression is occluded behind body',
        'wing_polygon_source_px':FAR_WING_POLYGON,'wing_pivot_source_px':list(FAR_WING_ROOT),'wing_target_source_px':list(FAR_WING_TARGET),
        'whole_body_crossfade':False,'tail_width_used_for_scale':False,'mirrored':False,
        'pose_phase':'0..1; neutral at both endpoints; smooth ingress, hold, smooth return; blink has symmetric sine envelope',
        'runtime_compositing':'crop/mask/affine only, immutable original source preserved',
        'full_episode_quality_acceptance':'pending completed MP4'}


if __name__=='__main__':
    (BATCH/'registration.json').write_text(json.dumps(registration(),ensure_ascii=False,indent=2)+'\n')
    for color,tag in [('#fff8eb','light'),('#263f43','dark')]:
        out=Image.new('RGBA',(1800,6*365),color);d=ImageDraw.Draw(out)
        for j,state in enumerate(STATES):
            x=j%2*900;y=j//2*365
            draw_character(out,state,.5,280,(x+170,y+325))
            d.text((x+20,y+12),state,fill='#7a5538' if tag=='light' else '#fff4df')
        out.convert('RGB').save(BATCH/f'previews/all-states-280-{tag}.jpg',quality=95)
    print(json.dumps({'registration':str((BATCH/'registration.json').relative_to(ROOT)),'states':list(STATES)}))
