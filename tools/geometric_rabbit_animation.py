"""Stable local-arm rabbit rig for Geometric Sequences.

The adopted face, asymmetric ears, beret and feet stay fixed. Source originals
are immutable; rendered native sprite records are explicit derived artwork.
"""
from __future__ import annotations
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT/'assets/library/characters/rabbit-beret/generation-batches/geometric-production-20261112-01a1cdca-rabbit'
NEUTRAL = ROOT/'assets/library/characters/rabbit-beret/eyecatches/v001/source-sheets/identity-reference-crop.png'
BLINK = ROOT/'assets/library/characters/rabbit-beret/motions/v002/blink.png'
PREVIOUS = ROOT/'assets/library/characters/rabbit-beret/generation-batches/geometric-preproduction-20261112-01a1cdca/frames'
SIZE = (800,800)
OFFSET = (210,100)
REFERENCE_HEIGHT = 585.0
ANCHOR = (370.0,680.0)
PHASE_STEPS = 32
STATES = ('neutral','wave','operate','present','wonder','think','blink')
GAZES = ('forward','up','left','right','upper_left','upper_right','down')
TORSO_PROFILE = [(380,90,229),(400,85,236),(430,73,247),(460,64,252),
                 (480,63,251),(490,64,250),(500,66,248),(514,74,240)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixel_sha(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def smooth(x):
    x=max(0.0,min(1.0,x))
    return x*x*(3-2*x)


def envelope(p):
    if p<.25:return smooth(p/.25)
    if p>.75:return smooth((1-p)/.25)
    return 1.0


def visible(image,threshold=128):
    return image.getchannel('A').point(lambda a:255 if a>=threshold else 0).getbbox()


def _multiply_alpha(image,mask):
    out=image.copy()
    out.putalpha(ImageChops.multiply(out.getchannel('A'),mask))
    return out


def _torso_limits(y):
    for a,b in zip(TORSO_PROFILE,TORSO_PROFILE[1:]):
        if a[0]<=y<=b[0]:
            p=(y-a[0])/(b[0]-a[0])
            return round(a[1]*(1-p)+b[1]*p),round(a[2]*(1-p)+b[2]*p)
    raise ValueError(y)


def _eye_object(image,region):
    """Select one connected brown/white eye, excluding cream muzzle pixels."""
    crop=image.crop(region);mask=Image.new('L',crop.size);mp=mask.load();cp=crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            red,green,blue,alpha=cp[x,y]
            if alpha>=128 and ((red<180 and green<150 and blue<125) or (red>235 and green>235 and blue>238)):
                mp[x,y]=255
    working=mask.copy();best=None;best_count=0
    while (b:=working.getbbox()) is not None:
        y=b[1];x=next(x for x in range(b[0],b[2]) if working.getpixel((x,y)))
        before=working.copy();ImageDraw.floodfill(working,(x,y),0)
        component=ImageChops.subtract(before,working);count=component.histogram()[255]
        if count>best_count:best,best_count=component,count
    if best is None:raise ValueError('No eye object')
    # The warm grey paper inside a white opening can fall outside the colour
    # seed. Fill holes enclosed by the selected outer eye, retaining its RGB.
    holes=ImageChops.invert(best)
    ImageDraw.floodfill(holes,(0,0),0)
    best=ImageChops.lighter(best,holes)
    return crop,best


class Artwork:
    def __init__(self,record_sprites=True):
        self.record_sprites=record_sprites
        self.source_refs=[]
        for p,role in [(NEUTRAL,'exact adopted-neutral lossless crop'),
                       (BATCH/'source/production-arm-poses.png','new generated four-pose source; local arm pixels'),
                       (BATCH/'source/torso-underlay.png','new generated arms-behind-back torso clean plate'),
                       (BLINK,'existing registered blink; local closed-eye strokes only'),
                       (PREVIOUS/'control_open.png','prior generated upper-left eye drawings; local eye pixels only'),
                       (PREVIOUS/'follow_up.png','prior generated upward eye drawings; local eye pixels only')]:
            self.source_refs.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'role':role})
        self.neutral=Image.open(NEUTRAL).convert('RGBA')
        self.base=Image.new('RGBA',SIZE)
        self.base.alpha_composite(self.neutral,OFFSET)
        sheet=Image.open(BATCH/'source/production-arm-poses.png').convert('RGBA')
        under=Image.open(BATCH/'source/torso-underlay.png').convert('RGBA')
        self.body=self._body_underlay(under)
        self.arms=[]
        arm_specs=[('left',(627,0,1254,627),[(228,363),(210,339),(183,324),(160,322),(147,332),(145,353),(163,375),(205,406),(219,405)],(222,384),(305,492))]
        self.arm_recipe=[]
        for side,cellbox,polygon,pivot,shoulder in arm_specs:
            cell=sheet.crop(cellbox)
            mask=Image.new('L',(627,627))
            ImageDraw.Draw(mask).polygon(polygon,fill=255)
            mask=mask.filter(ImageFilter.GaussianBlur(3))
            arm=_multiply_alpha(cell,mask)
            scale=1.12
            arm=arm.convert('RGBa').resize((round(627*scale),round(627*scale)),Image.Resampling.LANCZOS).convert('RGBA')
            layer=Image.new('RGBA',SIZE)
            translation=(round(shoulder[0]-pivot[0]*scale),round(shoulder[1]-pivot[1]*scale))
            layer.alpha_composite(arm,translation)
            self.arms.append((layer,shoulder))
            self.arm_recipe.append({'side':side,'source_cell_xyxy':list(cellbox),'source_mask_polygon_xy':polygon,
                                    'mask_feather_px':3,'local_source_scale':scale,'source_pivot_px':pivot,
                                    'fixed_canvas_shoulder_px':shoulder,'source_translate_xy':translation})
        # The adopted right arm already supplies a good relaxed shape. Rotate
        # those original pixels rather than adopting a differently bent paw.
        rpolygon=[(243,377),(258,390),(278,420),(291,454),(287,474),(268,483),(251,478),(240,457),(230,419),(226,400)]
        rm=Image.new('L',SIZE)
        ImageDraw.Draw(rm).polygon([(x+OFFSET[0],y+OFFSET[1]) for x,y in rpolygon],fill=255)
        rm=rm.filter(ImageFilter.GaussianBlur(2))
        self.arms.append((_multiply_alpha(self.base,rm),(449,491)))
        self.arm_recipe.append({'side':'right','source_path':str(NEUTRAL.relative_to(ROOT)),
                                'source_mask_polygon_xy':rpolygon,'mask_feather_px':2,'local_source_scale':1,
                                'fixed_canvas_shoulder_px':[449,491],'source_translate_xy':list(OFFSET)})
        headmask=Image.new('L',SIZE)
        ImageDraw.Draw(headmask).rectangle((0,0,SIZE[0],OFFSET[1]+380),fill=255)
        self.head=_multiply_alpha(self.base,headmask)
        self.blink_patch=self._blink_layer()
        self.gaze_patches=self._gaze_layers()
        self.used={}

    def _body_underlay(self,source):
        torso=Image.new('RGBA',SIZE)
        # The clean plate's torso is mapped between measured neck and hip
        # landmarks. This same local underlay is fixed in every animation frame.
        for y in range(380,515):
            sy=round(970+(y-380)*(1348-970)/(514-380))
            row=source.crop((0,sy,source.width,sy+1))
            alpha=row.getchannel('A')
            xs=[x for x in range(source.width) if alpha.getpixel((x,0))>=128]
            left,right=_torso_limits(y)
            strip=row.crop((min(xs)-3,0,max(xs)+4,1)).convert('RGBa').resize((right-left+7,1),Image.Resampling.LANCZOS).convert('RGBA')
            if y>490:strip.putalpha(strip.getchannel('A').point(lambda a:round(a*(514-y)/24)))
            torso.alpha_composite(strip,(OFFSET[0]+left-3,OFFSET[1]+y))
        body=self.base.copy()
        keep=Image.new('L',SIZE,255)
        ImageDraw.Draw(keep).rectangle((0,OFFSET[1]+381,SIZE[0],OFFSET[1]+489),fill=0)
        body=_multiply_alpha(body,keep)
        body.alpha_composite(torso)
        return body

    def _blink_layer(self):
        source=Image.open(BLINK).convert('RGBA')
        layer=Image.new('RGBA',SIZE)
        for box,crop in [((74,234,134,309),(155,208,190,232)),((187,234,247,309),(218,208,253,232))]:
            # Pink texture from a clear reference cheek area erases the open
            # eye; only the stock closed-eye stroke is then inserted locally.
            patch=self.neutral.crop((140,239,174,274)).resize((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS)
            mask=Image.new('L',patch.size)
            ImageDraw.Draw(mask).ellipse((0,0,patch.width-1,patch.height-1),fill=255)
            mask=mask.filter(ImageFilter.GaussianBlur(1.3))
            patch=_multiply_alpha(patch,mask)
            layer.alpha_composite(patch,(OFFSET[0]+box[0],OFFSET[1]+box[1]))
            line=source.crop(crop).convert('RGBa').resize((60,41),Image.Resampling.LANCZOS).convert('RGBA')
            lm=Image.new('L',line.size)
            ImageDraw.Draw(lm).ellipse((0,0,59,40),fill=255)
            lm=lm.filter(ImageFilter.GaussianBlur(3))
            line=_multiply_alpha(line,lm)
            layer.alpha_composite(line,(OFFSET[0]+box[0],OFFSET[1]+253))
        return layer

    def _gaze_layers(self):
        result={};self.eye_recipe=[]
        for name,source_name,regions in [('left','control_open',[(205,220,276,294),(308,235,378,312)]),
                                         ('up','follow_up',[(224,214,287,284),(327,232,393,304)])]:
            source=Image.open(PREVIOUS/f'{source_name}.png').convert('RGBA')
            layer=Image.new('RGBA',SIZE)
            for region,target in zip(regions,[(77,236,131,306),(190,236,244,306)]):
                crop,object_mask=_eye_object(source,region);b=object_mask.getbbox();assert b
                eye_box=(b[0]-3,b[1]-3,b[2]+3,b[3]+3)
                destination=(target[0]-3,target[1]-3,target[2]+3,target[3]+3)
                # Erase only the original connected eye opening, leaving the
                # original muzzle and cheek untouched.
                old_region=(target[0]-5,target[1]-5,target[2]+5,target[3]+5)
                old,old_mask=_eye_object(self.neutral,old_region)
                pink=self.neutral.crop((140,239,174,274)).resize(old.size,Image.Resampling.LANCZOS)
                erase_mask=old_mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(.8))
                layer.alpha_composite(_multiply_alpha(pink,erase_mask),(OFFSET[0]+old_region[0],OFFSET[1]+old_region[1]))
                object_mask=object_mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(.7))
                patch=_multiply_alpha(crop,object_mask).crop(eye_box).convert('RGBa').resize((destination[2]-destination[0],destination[3]-destination[1]),Image.Resampling.LANCZOS).convert('RGBA')
                layer.alpha_composite(patch,(OFFSET[0]+destination[0],OFFSET[1]+destination[1]))
                self.eye_recipe.append({'gaze':name,'source_path':str((PREVIOUS/f'{source_name}.png').relative_to(ROOT)),
                                        'source_crop_xyxy':[region[0]+eye_box[0],region[1]+eye_box[1],region[0]+eye_box[2],region[1]+eye_box[3]],'target_canonical_xyxy':list(destination),
                                        'feather_px':.7,'method':'largest connected brown/white eye object only; cream muzzle excluded; original connected eye erased locally before one eye is inserted'})
            result[name]=layer
        return result

    def _gaze(self,image,gaze):
        if gaze in ('forward','down'):return image
        out=image.copy()
        out.alpha_composite(self.gaze_patches['left' if gaze in ('left','upper_left') else 'up'])
        return out

    @lru_cache(maxsize=1024)
    def native(self,state='neutral',step=0,gaze='forward'):
        if state not in STATES:raise ValueError(state)
        if gaze not in GAZES:raise ValueError(gaze)
        step=max(0,min(PHASE_STEPS-1,int(step)));p=step/(PHASE_STEPS-1)
        env=envelope(p) if state!='neutral' else 0
        left,right=65.0,0.0
        if state in ('operate','present'):left-=65*env
        elif state=='wave':left-=(65+9*math.sin(p*math.pi*6))*env
        elif state=='wonder':left-=65*env;right+=50*env
        elif state=='think':left-=32*env
        image=self.body.copy()
        for (arm,pivot),angle in zip(self.arms,(left,right)):
            rotated=arm.convert('RGBa').rotate(angle,resample=Image.Resampling.BICUBIC,center=pivot).convert('RGBA')
            image.alpha_composite(rotated)
        image.alpha_composite(self.head)
        if state=='blink' and .34<=p<=.66:image.alpha_composite(self.blink_patch)
        else:image=self._gaze(image,gaze)
        bounds=visible(image)
        assert bounds and 0<bounds[0] and 0<bounds[1] and bounds[2]<SIZE[0] and bounds[3]<SIZE[1]
        native_id=f'{state}-p{step:02d}-{gaze}'
        native_path=BATCH/'frames/rig-native'/f'{native_id}-{pixel_sha(image)[:12]}.png'
        if self.record_sprites:
            native_path.parent.mkdir(parents=True,exist_ok=True)
            if not native_path.exists():
                temporary=native_path.with_name(native_path.name+f'.{os.getpid()}.tmp')
                image.save(temporary,format='PNG');os.replace(temporary,native_path)
        meta={'native_sprite_id':native_id,'native_pixel_sha256':pixel_sha(image),'native_size_px':list(SIZE),
              'native_visible_box_xyxy':list(bounds),'native_anchor_px':list(ANCHOR),'native_reference_height_px':REFERENCE_HEIGHT,
              'state':state,'phase_step':step,'phase':p,'gaze':gaze,'left_arm_degrees':left,'right_arm_degrees':right,
              'effective_gaze':('forward' if gaze=='down' else 'upper_left' if gaze in ('left','upper_left') else 'upper_right' if gaze in ('right','upper_right','up') else 'forward'),
              'source_refs':self.source_refs,'native_sprite_path':str(native_path.relative_to(ROOT)) if self.record_sprites else None,
              'native_file_sha256':sha(native_path) if self.record_sprites else None,
              'fixed_head_except_eyes_xyxy':[OFFSET[0],OFFSET[1],OFFSET[0]+352,OFFSET[1]+380],
              'fixed_feet_xyxy':[OFFSET[0],OFFSET[1]+515,OFFSET[0]+352,OFFSET[1]+585],
              'local_eye_regions_xyxy':[[OFFSET[0]+70,OFFSET[1]+229,OFFSET[0]+139,OFFSET[1]+313],
                                       [OFFSET[0]+183,OFFSET[1]+229,OFFSET[0]+252,OFFSET[1]+313]],
              'head_body_bounce':False,'whole_character_crossfade':False}
        self.used[native_id]=meta
        return image,meta

    @lru_cache(maxsize=2048)
    def _sprite(self,state,step,height,gaze):
        native,meta=self.native(state,step,gaze)
        scale=height/REFERENCE_HEIGHT
        image=native.convert('RGBa').resize((round(native.width*scale),round(native.height*scale)),Image.Resampling.LANCZOS).convert('RGBA')
        anchor=(ANCHOR[0]*scale,ANCHOR[1]*scale)
        b=visible(image)
        return image,anchor,{**meta,'display_reference_height_px':height,'scale':scale,
                             'sprite_pixel_sha256':pixel_sha(image),'sprite_size_px':list(image.size),
                             'sprite_visible_box_xyxy':list(b),'foot_relative_visible_box_xyxy':[b[0]-anchor[0],b[1]-anchor[1],b[2]-anchor[0],b[3]-anchor[1]]}

    def sprite(self,state='neutral',phase=0.0,height=280,gaze='forward'):
        step=round(max(0,min(1,float(phase)))*(PHASE_STEPS-1))
        return self._sprite(state,step,float(height),gaze)

    def draw(self,canvas,*,state='neutral',phase=0.0,height=280,foot=(960,1035),gaze='forward',scene_mode=None,**unused):
        image,anchor,meta=self.sprite(state,phase,height,gaze)
        xy=(round(foot[0]-anchor[0]),round(foot[1]-anchor[1]))
        b=meta['sprite_visible_box_xyxy'];absolute=[b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]
        actual=[xy[0]+anchor[0],xy[1]+anchor[1]]
        contained=0<=absolute[0] and 0<=absolute[1] and absolute[2]<=canvas.width and absolute[3]<=canvas.height
        if not contained:raise ValueError({'rabbit_clipped':absolute,'canvas':canvas.size})
        canvas.alpha_composite(image,xy)
        return {**meta,'component_id':'rabbit','scene_mode':scene_mode,'horizontal':'foot-anchor-x','vertical':'anatomical-foot-support-y',
                'visible_box_xyxy':absolute,'target_anchor_px':list(foot),'foot':list(foot),'actual_anchor_px':actual,
                'delta_x_px':actual[0]-foot[0],'delta_y_px':actual[1]-foot[1],'tolerance_px':.5,
                'contained':contained,'passed':contained and abs(actual[0]-foot[0])<=.5 and abs(actual[1]-foot[1])<=.5,
                'composite_origin_xy':list(xy)}

    def receipt(self):
        return {'kind':'geometric-rabbit-local-arm-rig-v001','reference_height_px':REFERENCE_HEIGHT,'native_canvas_size_px':list(SIZE),
                'native_foot_anchor_px':list(ANCHOR),'phase_steps':PHASE_STEPS,'states':list(STATES),'gazes':list(GAZES),
                'source_refs':self.source_refs,'arm_recipe':self.arm_recipe,'eye_recipe':self.eye_recipe,'torso_profile':TORSO_PROFILE,
                'torso_source_y_range':[970,1348],'torso_target_y_range':[380,514],'torso_lower_blend_y':[490,514],
                'source_originals_modified':False,'canonical_head_and_feet_preserved':True,
                'artwork_module_sha256':sha(Path(__file__)),
                'gaze_aliases':{'left':'upper_left','up':'upper_right/upward from prior generated eyes','right':'upper_right','down':'forward; not used for this episode'},
                'source_drawings':'4 new arm pose drawings plus 1 new torso clean plate. Runtime uses a local crop from new pose 2 plus the adopted right arm; remaining new pose originals are preserved candidates.',
                'used_native_sprites':list(self.used.values())}
