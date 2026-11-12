"""Triangular v002: retain v001 actor art and restore the visible N053 notice."""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter,ImageFont

ROOT=Path(__file__).resolve().parents[1]
FPS=30
PREVIEW_REG=ROOT/'assets/library/characters/meerkat/generation-batches/triangular-20261112-01a1cd42/registration.json'


def resolve(path):
    p=Path(path)
    return p if p.is_absolute() else ROOT/p


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(path):
    return str(Path(path).resolve().relative_to(ROOT))


class Artwork:
    def __init__(self,registry=None):
        self.registry_path=resolve(registry) if registry else PREVIEW_REG
        self.registration=json.loads(self.registry_path.read_text())
        rows=self.registration.get('poses',self.registration.get('frames'))
        self.poses=rows if isinstance(rows,dict) else {r['id']:r for r in rows}
        self.poses={k:dict(v) for k,v in self.poses.items()}
        if self.registry_path!=PREVIEW_REG and not self.registration.get('runtime_composited'):
            previous=json.loads(PREVIEW_REG.read_text())
            self.poses={**previous.get('poses',previous['frames']),**self.poses}
        neutral=next(x for x in json.loads((ROOT/'catalogs/character-library-v1.json').read_text())['characters'] if x['id']=='meerkat')['neutral']
        self.poses.setdefault('neutral',dict(neutral))
        self.images={}
        for ident,row in self.poses.items():
            path=resolve(row['path'])
            if sha(path)!=row['sha256']:raise ValueError(f'Actor source hash mismatch: {ident}')
            row.setdefault('reference_height_px',self.registration.get('common_reference_height_px'))
            if not row.get('reference_height_px') or not row.get('anchor_px'):
                raise ValueError(f'Actor lacks scale or support: {ident}')
            self.images[ident]=Image.open(path).convert('RGBA')
        self.overlay_reports={}
        if self.registry_path!=PREVIEW_REG and not self.registration.get('runtime_composited'):
            self.compose_stable_actor()
        for ident,config in self.registration.get('local_overlays',self.registration.get('arm_overlays',{})).items():
            base_id=config.get('base_pose','neutral');source_id=config.get('source_pose',ident)
            base=self.images[base_id].copy();source=self.images[source_id]
            tr=config['source_to_base'];scale=float(tr['scale'])
            aligned=Image.new('RGBA',base.size)
            resized=source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.LANCZOS)
            aligned.paste(resized,tuple(round(v) for v in tr['translate_xy']))
            mask=Image.new('L',base.size)
            ImageDraw.Draw(mask).polygon([tuple(p) for p in config['replace_polygon_xy']],fill=255)
            feather=float(config.get('feather_px',0))
            if feather:mask=mask.filter(ImageFilter.GaussianBlur(feather))
            image=Image.composite(aligned,base,mask)
            self.images[ident]=image
            self.poses[ident]={**self.poses[base_id],'derived_from_pose':source_id}
            self.overlay_reports[ident]={'base_pose':base_id,'source_pose':source_id,
                'changed_bounds_px':ImageChops.difference(image,base).convert('RGB').getbbox(),
                'source_pngs_modified':False,'whole_actor_crossfade':False}

    def compose_stable_actor(self):
        """Keep the adopted 1254px head/body; replace only authored local art."""
        base=self.images['neutral'];canonical=self.poses['neutral']
        body_h=canonical['reference_height_px'];anchor=canonical['anchor_px']
        source_rows={k:dict(v) for k,v in self.poses.items()}
        source_images=dict(self.images)
        # Raised fingers extend just in front of the lower cheek. This measured
        # shoulder/palm envelope keeps the complete hand, including its top.
        left=[(70,190),(205,190),(225,215),(285,235),(310,265),(310,405),(210,420),(70,420)]
        right=[(630-x,y) for x,y in left]
        aliases={'wave_prepare':'wave_raise','guide_prepare':'look_up_prepare',
                 'guide_extend':'guide_up_extend','guide_return':'guide_half','gaze_up':'look_up_prepare'}
        names=set(source_rows)-{'neutral'}
        names.update(aliases)
        for ident in sorted(names):
            source_id=aliases.get(ident,ident)
            if source_id not in source_rows:continue
            row=source_rows[source_id];source=source_images[source_id]
            scale=body_h/row['reference_height_px']
            translate=[anchor[i]-row['anchor_px'][i]*scale for i in (0,1)]
            aligned=Image.new('RGBA',base.size)
            resized=source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.LANCZOS)
            aligned.paste(resized,tuple(round(v) for v in translate))
            mask=Image.new('L',base.size);draw=ImageDraw.Draw(mask)
            def point(x,y):return (anchor[0]+(x-315)*body_h/579,anchor[1]+(y-593)*body_h/579)
            regions=[]
            if ident.startswith('neck_'):
                self.images[ident]=source
                self.poses[ident]=row
                self.overlay_reports[ident]={'source_pose':source_id,'method':'complete original registered drawing',
                    'reason':'Intentional neck extension; no alpha blend that could duplicate forearms',
                    'source_pngs_modified':False,'whole_actor_crossfade':False}
                continue
            else:
                if ident.startswith('wave_') or ident.startswith('guide_') or ident in ('look_up_prepare','two_groups','delighted'):
                    arm=([(70,210),(272,210),(285,240),(310,265),(310,405),(210,420),(70,420)]
                         if source_id in ('wave_half','wave_in') else left)
                    draw.polygon([point(x,y) for x,y in arm],fill=255);regions.append('left forearm and adjacent chest')
                if ident in ('two_groups','delighted'):
                    draw.polygon([point(x,y) for x,y in right],fill=255);regions.append('right forearm and adjacent chest')
                if not ident.startswith('wave_'):
                    for box in ((215,75,309,204),(327,75,424,204)):
                        p0,p1=point(box[0],box[1]),point(box[2],box[3])
                        draw.ellipse((*p0,*p1),fill=255)
                    regions.append('two eye patches; outer head silhouette unchanged')
                if ident=='delighted':
                    p0,p1=point(265,170),point(370,225);draw.ellipse((*p0,*p1),fill=255)
                    regions.append('mouth expression')
                mask=mask.filter(ImageFilter.GaussianBlur(2.5))
            image=Image.composite(aligned,base,mask)
            self.images[ident]=image
            self.poses[ident]={**row,'reference_height_px':body_h,'anchor_px':list(anchor),
                'original_source_anchor_px':row['anchor_px'],'original_source_reference_height_px':row['reference_height_px'],
                'derived_from_pose':source_id,'runtime_composited':True}
            self.overlay_reports[ident]={'base_pose':'neutral','source_pose':source_id,
                'source_to_base':{'scale':scale,'translate_xy':translate},'regions':regions,
                'arm_polygon_reference_579':left if regions and 'forearm' in regions[0] else None,
                'changed_bounds_px':ImageChops.difference(image,base).getbbox(),
                'source_pngs_modified':False,'whole_actor_crossfade':False}
        if 'gaze_left' in self.images:
            eye_mask=Image.new('L',base.size);eye_draw=ImageDraw.Draw(eye_mask)
            for box in ((215,75,309,204),(327,75,424,204)):
                eye_draw.ellipse((*point(box[0],box[1]),*point(box[2],box[3])),fill=255)
            eye_mask=eye_mask.filter(ImageFilter.GaussianBlur(2.5))
            for pose in ('guide_prepare','guide_return','two_groups','delighted'):
                if pose not in self.images:continue
                ident=pose+'_left';image=Image.composite(self.images['gaze_left'],self.images[pose],eye_mask)
                self.images[ident]=image;self.poses[ident]={**self.poses[pose],
                    'additional_source':{'path':source_rows['gaze_left']['path'],'sha256':source_rows['gaze_left']['sha256']},
                    'derived_gaze_variant_of':pose}
                self.overlay_reports[ident]={'base_pose':pose,'eye_source_pose':'gaze_left','method':'only two measured eye patches',
                    'changed_bounds_px':ImageChops.difference(image,self.images[pose]).convert('RGB').getbbox(),
                    'source_pngs_modified':False,'whole_actor_crossfade':False}

    def write_runtime(self,directory,reviewed=False):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        rows={}
        for ident,image in self.images.items():
            p=directory/f'{ident}.png';image.save(p)
            rows[ident]={**self.poses[ident],'path':local(p),'sha256':sha(p),
                         'size_px':list(image.size),
                         'raw_source_size_px':list(Image.open(resolve(self.poses[ident]['path'])).size),
                         'original_source':{'path':self.poses[ident]['path'],'sha256':self.poses[ident]['sha256'],
                             'anchor_px':self.poses[ident].get('original_source_anchor_px',self.poses[ident]['anchor_px']),
                             'reference_height_px':self.poses[ident].get('original_source_reference_height_px',self.poses[ident]['reference_height_px'])}}
        path=directory/'registration.json'
        path.write_text(json.dumps({'schema_version':1,'kind':'triangular-meerkat-runtime-composited-art',
            'character_id':'meerkat','runtime_composited':True,'production_ready':reviewed,
            'scope':'triangular-counting-001-v001-only','poses':rows,
            'source_registrations':[{'path':local(PREVIEW_REG),'sha256':sha(PREVIEW_REG)},
                                    {'path':local(self.registry_path),'sha256':sha(self.registry_path)}],
            'local_compositing':self.overlay_reports,'source_pngs_modified':False,
            'inventory_counts':{'new_production_raw_frames':12,'reused_preproduction_raw_frames':4,
                'canonical_neutral_sources':1,'runtime_sprites_including_aliases':len(rows),
                'derived_alias_names':['wave_prepare','guide_prepare','guide_extend','guide_return','gaze_up'],
                'gaze_variant_names':['guide_prepare_left','guide_return_left','two_groups_left','delighted_left']},
            'review_evidence':([{'path':local(p),'sha256':sha(p)} for p in [
                ROOT/'design/triangular-counting-v1/production-qa/root-review/render-input-review.json',
                ROOT/'design/triangular-counting-v1/production-qa/final-v001/runtime-preview-001/review-inputs.json'] if p.exists()] if reviewed else []),
            'review_scope':'render-input acceptance only; completed episode inspection is separate',
            'notes':'Stable adopted neutral base. Local original arm/eye art and purposeful neck extension; no whole-character morph or bbox fit.'},
            ensure_ascii=False,indent=2)+'\n')
        order=['neutral','wave_prepare','wave_raise','wave_half','wave_out','wave_in',
               'guide_prepare','guide_half','guide_extend','guide_return','gaze_up','gaze_left',
               'gaze_right','blink_up','neck_prepare','neck_half','neck_full','neck_return',
               'look_up_prepare','guide_up_extend','two_groups','delighted']
        order+=['guide_prepare_left','guide_return_left','two_groups_left','delighted_left']
        order=[k for k in order if k in self.images]
        sheet=Image.new('RGB',(2400,math.ceil(len(order)/6)*450),'#fff9eb');draw=ImageDraw.Draw(sheet)
        f=ImageFont.truetype(str(ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'),18)
        for i,ident in enumerate(order):
            im,row,scale=self.sprite(ident,350);x,y=(i%6)*400,(i//6)*450
            xy=(round(x+180-row['anchor_px'][0]*scale),round(y+420-row['anchor_px'][1]*scale))
            sheet.paste(im,xy,im);draw.text((x+12,y+10),ident,font=f,fill='#544b42')
        contact=directory/'runtime-contact-sheet.png';sheet.save(contact)
        (directory/'runtime-review-inputs.json').write_text(json.dumps({'registry':{'path':local(path),'sha256':sha(path)},
            'contact_sheet':{'path':local(contact),'sha256':sha(contact)},'poses':[
                {'id':k,'path':rows[k]['path'],'sha256':rows[k]['sha256']} for k in order],
            'generated_from_current_sprites':True,'production_ready':reviewed},ensure_ascii=False,indent=2)+'\n')
        return path

    def choose(self,*candidates):
        return next((p for p in candidates if p in self.poses),'neutral')

    @lru_cache(maxsize=128)
    def sprite(self,pose,height):
        row=self.poses[pose];im=self.images[pose];scale=height/row['reference_height_px']
        return im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS),row,scale

    def draw(self,canvas,pose,foot,height):
        im,row,scale=self.sprite(pose,height)
        xy=tuple(round(a-b*scale) for a,b in zip(foot,row['anchor_px']))
        b=im.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox()
        box=[b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]
        if not (24<=box[0]<box[2]<=1896 and 24<=box[1]<box[3]<=1056):
            raise ValueError(f'Character clipping: {pose}: {box}')
        shadow=Image.new('RGBA',(1920,1080))
        ImageDraw.Draw(shadow).ellipse((foot[0]-height*.26,foot[1]-5,foot[0]+height*.36,foot[1]+8),fill=(70,58,42,25))
        canvas.image.alpha_composite(shadow);canvas.image.alpha_composite(im,xy)
        canvas.layers['character']=(im,xy)
        actual=[xy[0]+row['anchor_px'][0]*scale,xy[1]+row['anchor_px'][1]*scale]
        rec={'name':f'{canvas.scene}/character','component_id':'character','pose':pose,
             'horizontal':'anatomical-support-x','vertical':'ground-contact-y','not_centering_target':True,
             'visible_box_xyxy':box,'target_anchor_px':list(foot),'actual_anchor_px':actual,
             'delta_x_px':actual[0]-foot[0],'delta_y_px':actual[1]-foot[1],'tolerance_px':.5,
             'passed':all(abs(a-b)<=.5 for a,b in zip(actual,foot)),'contained':True}
        if not rec['passed']:raise ValueError(rec)
        canvas.records.append(rec)
        canvas.data['character']={**rec,'source_path':row['path'],'source_sha256':row['sha256'],
            'body_reference_height_px':row['reference_height_px'],'display_body_height_px':height,
            'scale':scale,'source_anchor_px':row['anchor_px'],'source_pixels_modified':False,
            'per_pose_fit':False,'whole_actor_crossfade':False}

    def receipt(self):
        return {'registry':{'path':local(self.registry_path),'sha256':sha(self.registry_path)},
            'scope':self.registration.get('scope'),'production_ready':self.registration.get('production_ready',False),
            'sources':[{'id':k,'path':r['path'],'sha256':r['sha256']} for k,r in self.poses.items()],
            'overlays':self.overlay_reports}


class Schedule:
    def __init__(self,plan,art):
        self.plan,self.art=plan,art
        events=plan['voice_events'];self.by={e['id']:e for e in events}
        self.actions=[]
        def add(ident,cue,edge,offset,poses,lengths,reason):
            e=self.by.get(cue)
            if not e:return
            start=math.ceil((e[edge]+offset)*FPS);cursor=start;keys=[]
            for pose,duration in zip(poses,lengths):
                keys.append({'start_frame':cursor,'end_frame':cursor+duration,'pose':pose});cursor+=duration
            if any(start<a['end_frame'] and a['start_frame']<cursor for a in self.actions):
                raise ValueError(f'Actor action overlap: {ident}')
            self.actions.append({'id':ident,'source_cue':cue,'source_edge':edge,'start_frame':start,
                'end_frame':cursor,'keys':keys,'reason':reason,'interpolation':'registered original key drawings; no actor dissolve'})
        a=art
        rest=a.choose('neutral')
        wave=[a.choose('wave_prepare','look_up_prepare'),a.choose('wave_half','wave_raise','guide_up_extend'),
              a.choose('wave_out','two_groups'),a.choose('wave_in','guide_up_extend'),a.choose('wave_out','two_groups'),
              a.choose('wave_half','wave_raise','guide_up_extend'),a.choose('wave_prepare','look_up_prepare'),rest]
        add('opening-greeting','I01','start_s',.15,wave,[5,6,8,8,8,6,5,6],'Open greeting, deliberate two sweeps, explicit return.')
        add('closing-greeting','O01','end_s',-2.20,wave,[5,6,8,8,8,6,5,6],'Closing greeting and settled return before the final fade.')
        guide=[a.choose('guide_prepare','look_up_prepare'),a.choose('guide_half','guide_up_extend'),
               a.choose('guide_extend','guide_up_extend'),a.choose('guide_return','guide_half','guide_up_extend'),
               a.choose('guide_prepare','look_up_prepare'),rest]
        add('row-meaning','I02','start_s',.35,guide,[5,7,18,7,5,6],'Point from n toward rows, then lower the forepaw.')
        for n in (20,30,40):
            add(f'show-row-{n:03d}',f'N{n:03d}','end_s',.08,guide,[5,7,12,7,5,6],
                'One short row presentation inside the existing two-second quiet gap.')
        neck=[a.choose('neck_prepare','look_up_prepare'),a.choose('neck_half','look_up_prepare'),
              a.choose('neck_full','look_up_prepare'),a.choose('neck_return','neck_half','look_up_prepare'),rest]
        add('look-over-the-pattern','N027','end_s',.10,neck,[6,8,15,8,8],
            'One purposeful neck extension, grounded feet, continuous return; does not add silence.')
        for n in (7,18,33,43,53):
            if n==53:
                required=('guide_prepare_left','guide_return_left','gaze_left')
                missing=[p for p in required if p not in a.poses]
                if missing:raise ValueError(f'Missing left-facing presentation drawings: {missing}')
                poses=['guide_prepare_left','guide_return_left','guide_prepare_left','gaze_left']
                reason='One short left-facing forepaw presentation and return; restore the visible reaction inside the unchanged40-frame quiet gap.'
            else:
                poses=[a.choose('gaze_up','look_up_prepare'),a.choose('gaze_right','look_up_prepare'),
                       a.choose('gaze_up','look_up_prepare'),rest]
                reason='Eyes follow the completed pattern and return during an existing gap.'
            add(f'notice-{n:03d}',f'N{n:03d}','end_s',.12,poses,[8,15,9,8],reason)
        if 'blink_up' in a.poses:
            for n in (12,24,36,48,58):
                add(f'quiet-blink-{n:03d}',f'N{n:03d}','end_s',.30,
                    [a.choose('gaze_left' if n>=45 else 'gaze_up','look_up_prepare'),'blink_up',
                     a.choose('gaze_left' if n>=45 else 'gaze_up','look_up_prepare')],
                    [2,3,4],'One short blink inside an existing quiet gap; head, body and feet remain fixed.')
        # Explanation gestures are tied to the mathematical action, not looped.
        for cue in ('X004a','X005','X014','X045'):
            add(f'explain-{cue}',cue,'start_s',.35,guide,[6,9,24,9,6,8],
                'Guide the replay and return with the same body scale and feet.')
        final=self.by.get('N060')
        if final:
            add('finish-the-triangle','N060','end_s',.15,
                [a.choose('guide_prepare','look_up_prepare'),a.choose('two_groups','guide_extend','guide_up_extend'),
                 a.choose('delighted'),a.choose('guide_return','guide_half','guide_up_extend'),rest],
                [7,15,20,8,8],'A completed-result presentation after the last number is spoken; follows the scene cut to the central outro with upward-facing original eyes.')
        self.actions.sort(key=lambda a:a['start_frame']);self.starts=[a['start_frame'] for a in self.actions]
        for action in self.actions:
            if action['source_cue'].startswith('N') and action['source_cue']!='N060':
                n=int(action['source_cue'][1:]);next_e=self.by[f'E{n+1:03d}']
                if action['end_frame']>math.floor(next_e['start_s']*FPS):
                    raise ValueError(f'Actor action exceeds quiet gap: {action["id"]}')

    def pose(self,frame,mode,phase,n=0):
        i=bisect_right(self.starts,frame)-1
        if i>=0 and frame<self.actions[i]['end_frame']:
            pose=next(k['pose'] for k in reversed(self.actions[i]['keys']) if frame>=k['start_frame'])
            if mode=='count' and n>=45:
                if pose+'_left' in self.art.poses:return pose+'_left'
                if pose in ('neutral','gaze_up','gaze_right'):return self.art.choose('gaze_left','look_up_prepare')
            return pose
        if mode=='count' and n>=45:return self.art.choose('gaze_left','look_up_prepare')
        if mode=='count' and phase in ('copy','rotate','pair'):
            return self.art.choose('gaze_right','look_up_prepare')
        if mode=='count' and phase in ('build','half','result'):
            return self.art.choose('gaze_up','look_up_prepare')
        return 'neutral'

    def receipt(self):
        return {'fps':FPS,'actions':self.actions,'timing_changed':False,'full_actor_crossfade':False,
                'registration':self.art.receipt(),'support':'anatomical feet; source sheet common physical standing reference',
                'target_policy':'count n>=45 actor is right of both copies: gaze_left, plus local left-eye variants for final presentation; replay n45 actor is central and uses upward gaze'}
