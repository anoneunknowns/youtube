"""Stable-body, locally articulated hedgehog acting for the Collatz episode.

The canonical head, spines and feet remain on one registered body. New generated
limbs are aligned by shoulder and paw landmarks, then warped to a shared moving
bone before their local artwork changes. No whole-character crossfade is used.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / 'assets/library/characters/hedgehog/generation-batches/collatz-production-20261112-01a1cd57'
CANONICAL = ROOT / 'assets/library/characters/hedgehog/sources/v003/neutral.png'
STATES = ('neutral', 'greet', 'even', 'odd', 'think', 'surprise', 'nod', 'cheer', 'stretch', 'goodbye')
REFERENCE_HEIGHT = 560.0
WORK_SIZE = (800, 800)
WORK_FOOT = (400.0, 740.0)
CANONICAL_SCALE = REFERENCE_HEIGHT / 1039.0
SOURCE_ANCHOR = (611, 1166)
ORIGIN = (WORK_FOOT[0] - SOURCE_ANCHOR[0] * CANONICAL_SCALE,
          WORK_FOOT[1] - SOURCE_ANCHOR[1] * CANONICAL_SCALE)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _smooth(t):
    t = min(1., max(0., t))
    return t*t*(3.-2.*t)


def _envelope(p):
    if p < .28:
        return _smooth(p/.28)
    if p <= .70:
        return 1.
    return _smooth((1.-p)/.30)


def _canonical_point(xy):
    return (ORIGIN[0] + xy[0]*CANONICAL_SCALE,
            ORIGIN[1] + xy[1]*CANONICAL_SCALE)


REST_POLYGONS = {
    'left': [(448,707),(408,734),(379,766),(369,795),(379,825),
             (405,849),(439,869),(470,880),(499,876),(516,857),
             (524,833),(518,807),(497,780),(469,754)],
    'right': [(786,707),(825,734),(855,766),(867,795),(857,825),
              (832,849),(798,869),(768,880),(739,876),(721,857),
              (712,833),(718,807),(739,780),(766,754)]
}
REST_ROOTS = {'left': (438,744), 'right': (795,744)}
REST_TIPS = {'left': (470,854), 'right': (759,854)}
GOAL_PARTS = {
    'wave': (2, [(128,235),(112,229),(100,219),(94,203),(96,190),
                 (106,186),(118,191),(128,203),(140,221),(146,230)],
             (138,232), (108,203)),
    'open_left': (5, [(137,220),(116,216),(100,218),(91,226),(91,238),
                      (105,247),(121,248),(140,243),(153,236)],
                  (145,234), (108,234)),
    'open_right': (5, [(247,221),(266,216),(284,218),(297,224),(301,236),
                       (291,246),(274,249),(254,246),(239,238)],
                   (247,235), (282,234)),
    'point': (7, [(252,240),(262,225),(278,211),(290,205),(302,207),
                  (309,218),(306,231),(291,246),(273,257),(260,257)],
              (260,249), (292,220)),
    'cheek_left': (8, [(127,237),(125,223),(132,211),(145,206),(157,211),
                       (163,224),(155,240),(144,250),(132,249)],
                   (134,242), (145,222)),
    'cheek_right': (8, [(246,237),(246,223),(239,211),(226,206),(214,211),
                        (208,224),(216,240),(227,250),(240,249)],
                    (237,242), (225,222)),
}


def _polygon_part(im, points):
    mask = Image.new('L', im.size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    out = im.copy()
    out.putalpha(ImageChops.multiply(out.getchannel('A'), mask))
    return out


@lru_cache(maxsize=1)
def _resources():
    original = Image.open(CANONICAL).convert('RGBA')
    work = Image.new('RGBA', WORK_SIZE)
    original_small = original.resize((round(original.width*CANONICAL_SCALE),
                                      round(original.height*CANONICAL_SCALE)), Image.Resampling.LANCZOS)
    work.alpha_composite(original_small, (round(ORIGIN[0]), round(ORIGIN[1])))
    sheet = Image.open(BATCH/'source/arms-9-source.png').convert('RGBA')
    cells = [sheet.crop((i%3*418, i//3*418, (i%3+1)*418, (i//3+1)*418)) for i in range(9)]
    rest = {side: _polygon_part(original, pts) for side,pts in REST_POLYGONS.items()}
    # Local clean skin under each moving arm, from the generated armless source.
    # Only the explicitly recorded arm masks replace pixels; the face/spines/feet
    # of the adopted neutral are never replaced by a generated whole body.
    clean = Image.new('RGBA', WORK_SIZE)
    clean_scale = REFERENCE_HEIGHT/373.0
    armless = cells[0].resize((round(418*clean_scale),round(418*clean_scale)),Image.Resampling.LANCZOS)
    clean.alpha_composite(armless,(round(WORK_FOOT[0]-216.5*clean_scale),round(WORK_FOOT[1]-382*clean_scale)))
    body = work.copy()
    mask = Image.new('L',WORK_SIZE,0)
    d=ImageDraw.Draw(mask)
    for box in [(365,710,532,892),(704,710,875,892)]:
        d.rectangle((*_canonical_point(box[:2]),*_canonical_point(box[2:])),fill=255)
    body.paste(clean,(0,0),mask)
    goals={name:(_polygon_part(cells[i],poly),root,tip) for name,(i,poly,root,tip) in GOAL_PARTS.items()}
    faces=Image.open(BATCH/'source/faces-6-source.png').convert('RGBA')
    face_cells=[faces.crop((i%3*512,i//3*512,(i%3+1)*512,(i//3+1)*512)) for i in range(6)]
    return {'canonical':work,'body':body,'rest':rest,'goals':goals,'faces':face_cells}


def _warp_bone(part, source_root, source_tip, destination_root, destination_vector):
    sx,sy=source_tip[0]-source_root[0],source_tip[1]-source_root[1]
    dx,dy=destination_vector
    denom=sx*sx+sy*sy
    a=(sx*dx+sy*dy)/denom
    b=(sx*dy-sy*dx)/denom
    determinant=a*a+b*b
    tx=destination_root[0]-a*source_root[0]+b*source_root[1]
    ty=destination_root[1]-b*source_root[0]-a*source_root[1]
    coeff=(a/determinant,b/determinant,(-a*tx-b*ty)/determinant,
           -b/determinant,a/determinant,(b*tx-a*ty)/determinant)
    return part.transform(WORK_SIZE,Image.Transform.AFFINE,coeff,Image.Resampling.BICUBIC)


def _interpolated_vector(rest,goal,amount,wag=0.):
    ar,ag=math.atan2(rest[1],rest[0]),math.atan2(goal[1],goal[0])
    delta=(ag-ar+math.pi)%(2*math.pi)-math.pi
    angle=ar+delta*amount+math.radians(wag)*amount
    length=math.hypot(*rest)*(1-amount)+math.hypot(*goal)*amount
    return (math.cos(angle)*length,math.sin(angle)*length)


def _arm(side,goal_name,amount,wag=0.,override_vector=None):
    r=_resources()
    source_root,source_tip=REST_ROOTS[side],REST_TIPS[side]
    destination_root=_canonical_point(source_root)
    rest_vector=((source_tip[0]-source_root[0])*CANONICAL_SCALE,
                 (source_tip[1]-source_root[1])*CANONICAL_SCALE)
    if goal_name is None:
        return _warp_bone(r['rest'][side],source_root,source_tip,destination_root,
                          _interpolated_vector(rest_vector,override_vector or rest_vector,amount,wag))
    part,gr,gt=r['goals'][goal_name]
    factor=REFERENCE_HEIGHT/371.0
    goal_vector=override_vector or ((gt[0]-gr[0])*factor,(gt[1]-gr[1])*factor)
    vector=_interpolated_vector(rest_vector,goal_vector,amount,wag)
    rest_drawn=_warp_bone(r['rest'][side],source_root,source_tip,destination_root,vector)
    new_drawn=_warp_bone(part,gr,gt,destination_root,vector)
    # Both art pieces share shoulder AND paw center before this local blend.
    # This prevents two distinct hands during the artwork transition.
    return Image.blend(rest_drawn.convert('RGBa'),new_drawn.convert('RGBa'),amount).convert('RGBA')


def _cream_patch(im,box):
    # A texture insert sampled from the canonical clear forehead. It only sits
    # inside the face, behind one mouth/eye component, never over its outline.
    x0,y0,x1,y1=box
    source=_resources()['canonical'].crop((385,455,415,480))
    patch=source.resize((x1-x0,y1-y0),Image.Resampling.BICUBIC)
    mask=Image.new('L',patch.size,0)
    ImageDraw.Draw(mask).rounded_rectangle((1,1,patch.width-2,patch.height-2),radius=8,fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(2))
    im.paste(patch,(x0,y0),mask)


def _feature(cell,box,kind):
    piece=cell.crop(box).convert('RGBA')
    pixels=piece.load()
    for y in range(piece.height):
        for x in range(piece.width):
            red,green,blue,alpha=pixels[x,y]
            # The intended component contains brown strokes and coral mouth.
            # Cream paper is excluded by a soft luminance selection; originals
            # stay unchanged. This is an animation layer, not alpha clean-up.
            luminosity=(red+2*green+blue)/4
            if kind=='mouth':
                keep=(luminosity<150 or (red>green*1.38 and green<170))
            else:
                keep=luminosity<130
            pixels[x,y]=(red,green,blue,alpha if keep else 0)
    return piece


def _mouth(im,kind,amount):
    if amount<=.01:return
    r=_resources()
    cell=r['faces'][3 if kind=='small' else 4]
    box=(265,220,292,250) if kind=='small' else (235,216,286,263)
    art=_feature(cell,box,'mouth')
    center=_canonical_point((627,591))
    _cream_patch(im,(center[0].__round__()-44,center[1].__round__()-24,
                     center[0].__round__()+44,center[1].__round__()+29))
    target_width=17 if kind=='small' else 55
    target_height=(18 if kind=='small' else 48)*max(0.,(amount-.3)/.7)
    if amount<.3:
        original=Image.open(CANONICAL).convert('RGBA')
        art=_feature(original,(548,558,704,622),'mouth')
        target_width=round(156*CANONICAL_SCALE)
        target_height=max(1,64*CANONICAL_SCALE*(1-amount/.3))
    art=art.resize((max(1,round(target_width)),max(1,round(target_height))),Image.Resampling.LANCZOS)
    im.alpha_composite(art,(round(center[0]-art.width/2),round(center[1]-art.height/2+2)))


def _blink(im,amount):
    if amount<=.01:return
    # Vertically compress each original eye, retaining the canonical white and
    # brown design. At closure a generated calm eyelid stroke is used.
    source=_resources()['canonical']
    for index,box in enumerate([(314,343,389,422),(444,343,512,422)]):
        _cream_patch(im,box)
        if amount>.72:
            source_box=(145,173,212,207) if index==0 else (266,173,333,207)
            eye=_feature(_resources()['faces'][2],source_box,'eye')
            eye=eye.resize((55,21),Image.Resampling.LANCZOS)
        else:
            eye=source.crop(box)
        h=eye.height if amount>.72 else max(3,round(eye.height*(1-.96*amount)))
        eye=eye.resize((eye.width,h),Image.Resampling.LANCZOS)
        im.alpha_composite(eye,(round((box[0]+box[2]-eye.width)/2),round((box[1]+box[3]-h)/2)))


@lru_cache(maxsize=8)
def _actor(state,phase_tick):
    p=phase_tick/180.0
    r=_resources()
    amount=0. if state=='neutral' else _envelope(p)
    if state=='neutral':
        actor=r['canonical'].copy()
        if .88<p<.96:_blink(actor,math.sin((p-.88)/.08*math.pi)**2)
        return actor
    if amount<.0001:return r['canonical'].copy()
    result=r['body'].copy()
    left_goal=right_goal=None
    left_vector=right_vector=None
    wag_left=wag_right=0.
    if state in ('greet','goodbye'):
        left_vector=(-48,-51)
        wag_left=12*math.sin((p-.28)/.42*math.pi*4) if .28<p<.7 else 0
    elif state=='even':
        left_vector,right_vector=(-64,-3),(64,-3)
    elif state=='odd':
        right_vector=(59,-50)
    elif state=='think':
        left_vector=(64,-29)
    elif state=='surprise':
        left_vector,right_vector=(38,-38),(-38,-38)
    elif state=='cheer':
        left_vector,right_vector=(-52,-57),(52,-57)
    elif state=='stretch':
        left_vector,right_vector=(-67,-70),(67,-70)
    result.alpha_composite(_arm('left',left_goal,amount,wag_left,left_vector))
    result.alpha_composite(_arm('right',right_goal,amount,wag_right,right_vector))
    if state=='surprise':
        _mouth(result,'happy',amount)
    elif state=='cheer':
        _mouth(result,'happy',amount)
    elif state=='stretch':
        _blink(result,amount)
    elif state=='nod':
        # One intentional 2.5px cranial dip at 280px display; feet/body stay.
        head_box=(160,160,640,500)
        head=result.crop(head_box)
        result.paste((0,0,0,0),head_box)
        shift=round(5*amount*math.sin(p*math.pi)**2)
        result.paste(head,(head_box[0],head_box[1]+shift),head)
    return result


@lru_cache(maxsize=256)
def _sprite(state,tick,height):
    actor=_actor(state,tick)
    scale=height/REFERENCE_HEIGHT
    size=(max(1,round(WORK_SIZE[0]*scale)),max(1,round(WORK_SIZE[1]*scale)))
    sprite=actor.resize(size,Image.Resampling.LANCZOS)
    return sprite,sprite.getchannel('A').point(lambda v:255 if v>=16 else 0).getbbox()


def draw_character(image,state,phase,height=260,foot=(960,1030)):
    """Draw one complete returning gesture and return measured render metadata.

    ``phase`` is 0..1 over the entire gesture, including return. ``height`` is
    the standing physical body reference height, never the pose bounding box.
    The API accepts an RGBA or RGB Pillow canvas and does not draw a shadow.
    """
    if state not in STATES:raise ValueError(f'Unknown Collatz acting state: {state}')
    if not 0<=phase<=1:raise ValueError('phase must be within 0..1')
    if not 0<height<=280:raise ValueError('Production body height must be in (0,280]')
    tick=round(phase*180)
    if state=='neutral' and not .88<tick/180<.96:tick=0
    scale=height/REFERENCE_HEIGHT
    sprite,bbox=_sprite(state,tick,float(height))
    size=sprite.size
    at=(round(foot[0]-WORK_FOOT[0]*scale),round(foot[1]-WORK_FOOT[1]*scale))
    if image.mode=='RGBA':image.alpha_composite(sprite,at)
    else:image.paste(sprite,at,sprite)
    visible=None if bbox is None else [bbox[0]+at[0],bbox[1]+at[1],bbox[2]+at[0],bbox[3]+at[1]]
    delta_y=None if visible is None else visible[3]-foot[1]
    return {'state':state,'phase':tick/180,'registered_body_height_px':height,
            'registration_body_height_px':REFERENCE_HEIGHT,'foot_anchor_px':list(foot),
            'supporting_feet_px':[list(foot)],'visible_bbox_px':visible,
            'visible_bbox':visible,'visible_box_xyxy':visible,
            'foot_delta_x_px':0.0,'foot_delta_y_px':delta_y,
            'support_baseline_method':'bottom visible alpha>=16; x follows registered anatomical midpoint',
            'source_ids':['hedgehog-canonical-v003','collatz-production-arms-9','collatz-production-faces-6'],
            'whole_body_crossfade':False,'local_bone_alignment':True,
            'raster_scale':scale,'sprite_size_px':list(size)}


def registration():
    return {'schema_version':1,'kind':'collatz-stable-body-local-articulation',
            'character_id':'hedgehog','owner':'codex:collatz-production:01a1cd57',
            'canonical':{'path':str(CANONICAL.relative_to(ROOT)),'sha256':sha(CANONICAL),
                         'body_reference_height_px':1039,'foot_anchor_px':list(SOURCE_ANCHOR)},
            'working_canvas_px':list(WORK_SIZE),'working_body_height_px':REFERENCE_HEIGHT,
            'working_foot_anchor_px':list(WORK_FOOT),'maximum_display_body_height_px':280,
            'source_sheets':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'cells':n}
                             for p,n in [(BATCH/'source/arms-9-source.png',9),(BATCH/'source/faces-6-source.png',6)]],
            'new_generated_full_pose_cells':15,'new_original_sheets':2,
            'generated_cells_used_for_animation_regions':[
                {'sheet':'arms-9-source.png','cell':0,'role':'clean armless skin under canonical articulated paws'},
                {'sheet':'faces-6-source.png','cell':2,'role':'calm blink eyelid strokes'},
                {'sheet':'faces-6-source.png','cell':4,'role':'open happy/surprised mouth'}],
            'unused_generated_cells_status':'candidate source art preserved; not counted as adopted independent acting poses',
            'moving_paw_art':'two local cutouts from adopted canonical, continuously transformed by anatomical shoulder/paw landmarks',
            'reused_canonical_originals':1,'derived_local_parts_are_not_new_original_poses':True,
            'states':list(STATES),'semantic_reuse':{'goodbye':'greet, same art and motion; separate schedule'},
            'common_sheet_body_reference_px':{'arms':371.0,'face':474.0},
            'limb_source_polygons':{k:{'cell':v[0],'polygon':v[1],'shoulder':v[2],'paw':v[3]} for k,v in GOAL_PARTS.items()},
            'rest_source_polygons':REST_POLYGONS,'rest_shoulders':REST_ROOTS,'rest_paws':REST_TIPS,
            'policy':'Common standing body scale and anatomical feet. Articulated canonical paws and generated local skin/mouth/eyelids; canonical spines/feet retained. Nod is one intentional cranial dip. No per-pose fit, whole-body fade or air displacement.'}


if __name__=='__main__':
    (BATCH/'registration.json').write_text(json.dumps(registration(),ensure_ascii=False,indent=2)+'\n')
    out=Image.new('RGBA',(2000,1600),'#fff8eb')
    d=ImageDraw.Draw(out)
    for i,state in enumerate(STATES):
        x,y=i%5*400,i//5*800
        draw_character(out,state,.5,280,(x+200,y+400))
        d.text((x+10,y+420),state,fill='#442211')
        dark=Image.new('RGBA',(400,330),'#273c42')
        draw_character(dark,state,.5,280,(200,310))
        out.alpha_composite(dark,(x,y+450))
    out.convert('RGB').save(BATCH/'previews/light-dark-all-states.png')
    print(json.dumps({'registration':str((BATCH/'registration.json').relative_to(ROOT)),
                      'preview':str((BATCH/'previews/light-dark-all-states.png').relative_to(ROOT))}))
