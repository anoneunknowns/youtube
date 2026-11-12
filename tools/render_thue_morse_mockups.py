"""Deterministic 1080p preproduction stills and a silent working-rule study.

Generated background and bird source pixels are immutable. Equations, digits,
tiles and routes are rendered separately from the verified mathematical states.
This does not produce the full counting episode or adopt speech assets.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

from component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'design/thue-morse-counting-v1'
OUT = D / 'mockups'
QA = D / 'qa'
ACTOR = ROOT / 'assets/library/characters/onagadori/generation-batches/thue-morse-preproduction-20261112-01a1ce1d/registration.json'
BG = D / 'generation-batches/pearl-weaving-20261112-01a1ce1d/source/pearl-weaving-atelier-frontal-v002.png'
OVERHEAD = D / 'generation-batches/pearl-weaving-20261112-01a1ce1d/source/pearl-weaving-overhead.png'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
W, H = 1920, 1080
INK, TEAL, CREAM, APRICOT, PALE, MUTED = '#4e4639', '#357e80', '#fff6de', '#dfac77', '#fffaf0', '#7f8272'
SEQ = json.loads((D / 'math/sequence.json').read_text())['states']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=40)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def visible(layer, threshold=128):
    return layer.getchannel('A').point(lambda x: 255 if x >= threshold else 0).getbbox()


@lru_cache(maxsize=3000)
def glyph(text, size=40, color=INK):
    f = font(size)
    b = f.getbbox(text)
    im = Image.new('RGBA', (b[2]-b[0]+48, b[3]-b[1]+48))
    ImageDraw.Draw(im).text((24-b[0], 24-b[1]), text, font=f, fill=color)
    return im


class Canvas:
    def __init__(self, name, topdown=False):
        self.name = name
        self.im = (TOP_PLATE if topdown else PLATE).copy()
        self.draw = ImageDraw.Draw(self.im)
        self.records, self.actor_records, self.tiles = [], [], []
        self.meta = {'scene': name, 'topdown_teaching_surface': topdown}

    def center(self, im, box, ident):
        b = visible(im)
        if not b:
            raise ValueError(('empty', ident))
        xy = (round((box[0]+box[2]-b[0]-b[2])/2), round((box[1]+box[3]-b[1]-b[3])/2))
        rec = raster_centering_report(im, box, origin_xy=xy, name=f'{self.name}/{ident}', tolerance_px=.5)
        rec.update(component_id=ident, scene=self.name, horizontal='center', vertical='center', resolution_px=[W,H])
        if not rec['passed']:
            raise ValueError(rec)
        self.im.alpha_composite(im, xy)
        self.records.append(rec)

    def text(self, text, box, size=40, color=INK, ident=None):
        self.center(glyph(text, size, color), box, ident or text)
        self.records[-1].update(text=text, font_size_px=size)

    def panel(self, box, fill=PALE, outline='#dacdb6', radius=26):
        self.draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

    def tile(self, value, box, ident, active=False, size=46):
        fill = TEAL if value == 1 else CREAM
        self.panel(box, fill, APRICOT if active else '#b3c6bb', 12)
        if active:
            self.draw.rounded_rectangle(box, radius=12, outline=APRICOT, width=5)
        self.text(str(value), (box[0]+8,box[1]+5,box[2]-8,box[3]-5), size, PALE if value == 1 else INK, ident)
        self.tiles.append({'component_id':ident,'value':value,'box':list(box)})

    def arrow(self, start, end, color=TEAL, width=7):
        x,y=end; self.draw.line([start,end],fill=color,width=width)
        if abs(end[0]-start[0]) >= abs(end[1]-start[1]):
            sign=1 if end[0]>start[0] else -1
            self.draw.polygon([(x,y),(x-sign*17,y-11),(x-sign*17,y+11)],fill=color)
        else:
            sign=1 if end[1]>start[1] else -1
            self.draw.polygon([(x,y),(x-11,y-sign*17),(x+11,y-sign*17)],fill=color)

    def finish(self):
        # Independent foreground groups must not obscure each other.
        rows=self.records+self.actor_records
        for i,a in enumerate(rows):
            x,y,r,b=a['visible_box_xyxy']
            for other in rows[i+1:]:
                u,v,s,t=other['visible_box_xyxy']
                if max(x,u)<min(r,s) and max(y,v)<min(b,t):
                    raise ValueError(('foreground overlap',self.name,a.get('component_id'),other.get('component_id')))
        self.meta['foreground_clearance_passed']=True
        return self


class Actor:
    def __init__(self):
        lib=json.loads((ROOT/'catalogs/character-library-v1.json').read_text())
        neutral=next(c for c in lib['characters'] if c['id']=='onagadori')['neutral']
        self.poses={'neutral':neutral,**json.loads(ACTOR.read_text())['poses']}
        self.receipts={}

    @lru_cache(maxsize=40)
    def sprite(self,pose,height):
        row=self.poses[pose]; p=ROOT/row['path']
        if sha(p)!=row['sha256']:
            raise ValueError(('actor hash',p))
        im=Image.open(p).convert('RGBA'); scale=height/row['reference_height_px']
        im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
        return im,row,scale

    def draw(self,c,pose='neutral',foot=(1180,1030),height=220):
        im,row,scale=self.sprite(pose,height)
        xy=(round(foot[0]-row['anchor_px'][0]*scale),round(foot[1]-row['anchor_px'][1]*scale))
        b=visible(im,8); box=[b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]
        if not (20<box[0]<box[2]<1900 and 20<box[1]<box[3]<1058):
            raise ValueError(('actor clipped',pose,box))
        c.im.alpha_composite(im,xy)
        rec={'component_id':'onagadori','pose':pose,'horizontal':'anatomical support anchor','vertical':'grounded foot support','foot_anchor_px':list(foot),'body_display_height_px':height,'source_reference_height_px':row['reference_height_px'],'display_scale':scale,'visible_box_xyxy':box,'full_tail_contained':True,'mirrored':False,'source_pixels_modified':False,'path':row['path'],'sha256':row['sha256']}
        c.actor_records.append(rec);self.receipts[f'{pose}@{height}']=rec


def header(c,title='THUE–MORSE',sub='THE PEARL WEAVING ATELIER'):
    c.text(title,(230,45,1690,117),51,INK,'title')
    c.text(sub,(200,130,1720,167),23,TEAL,'subtitle')


def footer(c,count,ident='progress'):
    c.text(f'Terms counted: {count} / 256',(140,977,1030,1024),27,MUTED,ident)


def strip(c,values,top=835,index0=0):
    n=len(values);step=68;left=140
    for j,v in enumerate(values):
        x=left+j*step
        c.tile(v,(x,top,x+58,top+65),f'history-{index0+j}',size=36)
    c.text(f'Positions {index0}–{index0+n-1}',(140,top+76,left+max(400,n*step-10),top+108),23,MUTED,'history-range')


def standard(k,phase=1.,counted=True,actor_pose=None):
    s=SEQ[k]; c=Canvas(f'pipeline-{k:03d}-{phase:.2f}')
    header(c)
    result=s['value'];parent=s['parent_index'];pv=s['parent_value']
    final=phase>=.94
    formula=f't({k}) = 0' if k==0 else (f't({k}) = t({parent}) = ' if k%2==0 else f't({k}) = 1 − t({parent}) = ')+ (str(result) if final else '?')
    c.panel((130,199,1790,326))
    c.text(formula,(165,217,1755,309),63,INK,'active-equation')
    if k==0:
        c.text('START WITH ZERO',(390,375,1530,439),38,TEAL,'seed-label')
        c.tile(0,(818,479,1102,696),'seed-value',True,153)
        c.text('ZERO',(700,720,1220,774),35,INK,'result-word')
    else:
        c.text(f'PARENT · position {parent}',(150,373,550,421),29,TEAL,'parent-address')
        c.tile(pv,(230,465,470,665),'parent-value',False,136)
        c.arrow((495,565),(630,565))
        c.panel((660,459,1080,672), '#e8f0e7' if k%2==0 else '#f8e4c5')
        c.text('COPY' if k%2==0 else 'SWAP 0 ↔ 1',(690,477,1050,529),32,TEAL,'gate-title')
        c.text('SAME VALUE' if k%2==0 else f'1 − {pv}',(690,562,1050,639),44,INK,'operation')
        c.arrow((1110,565),(1260,565))
        c.text(f'POSITION {k}',(1265,373,1695,421),29,TEAL,'result-address')
        if final:
            c.tile(result,(1320,465,1560,665),'result-value',True,136)
            c.text('ONE' if result else 'ZERO',(1230,710,1650,766),35,INK,'result-word')
        else:
            c.panel((1320,465,1560,665), '#f6efdf')
            c.text('?',(1340,480,1540,650),117,MUTED,'pending-result')
        if .08<phase<.9:
            # One reference token travels; it is not a new counted term.
            if phase<.5:
                q=(phase-.08)/.42; x=480+q*140;v=pv
            else:
                q=(phase-.5)/.4;x=1110+q*120;v=result
            c.tile(v,(round(x)-22,543,round(x)+22,587),'reference-token',False,27)
        c.meta.update(parent_index=parent,parent_value=pv,operation=s['operation'],reference_is_not_previous_term=parent!=k-1)
    end=k+1 if counted else k
    if end:
        start=max(0,end-16);strip(c,[x['value'] for x in SEQ[start:end]],index0=start)
    footer(c,end)
    actor.draw(c,actor_pose or ('present' if k%2 else 'look_up'),foot=(1450,1035),height=180)
    c.meta.update(index=k,value=result,result_visible=final,phase=phase,completed_count=end,formula=formula)
    return c.finish()


def opening():
    c=Canvas('01-opening');header(c,'THUE–MORSE SEQUENCE')
    c.text('Two tiny values. One growing pattern.',(180,230,1740,326),61,TEAL,'promise')
    c.text('t(0) = 0',(390,390,1530,494),82,INK,'seed-equation')
    c.text('t(2n) = t(n)     ·     t(2n + 1) = 1 − t(n)',(190,535,1730,622),49,INK,'two-rules')
    c.tile(0,(680,664,800,767),'legend-zero',False,67)
    c.tile(1,(1120,664,1240,767),'legend-one',False,67)
    actor.draw(c,'neutral',foot=(610,1040),height=250)
    c.meta.update(completed_count=0,legend_not_counted=True)
    return c.finish()


def complement():
    c=Canvas('05-complement',True);header(c,sub='SAME ORDER · CHANGE EVERY VALUE')
    c.panel((170,205,1750,825),'#f7f0df',radius=40)
    c.text('KEEP',(210,248,1710,300),32,TEAL,'keep-label')
    vals=[s['value'] for s in SEQ[:8]];left=340;step=156
    for j,v in enumerate(vals):
        x=left+j*step
        c.tile(v,(x,338,x+110,438),f'original-{j}',size=58)
        c.arrow((x+55,458),(x+55,532),APRICOT,5)
        c.tile(1-v,(x,554,x+110,654),f'complement-{j}',size=58)
    c.text('SWAP 0 ↔ 1',(380,704,1540,761),38,TEAL,'swap-label')
    c.text('01101001  |  10010110',(300,845,1620,910),50,INK,'joined-word')
    c.text('Append the changed copy after the original.',(340,946,1730,1000),30,MUTED,'append-rule')
    c.text('Replay · Terms counted: 16 / 256',(340,1018,1580,1058),23,MUTED,'replay-progress')
    c.meta.update(replay=True,completed_count=16,same_order=True,original=vals,appended=[1-v for v in vals],character_offscreen='intentional overhead detail; no tiny bird pasted onto working surface')
    return c.finish()


def substitution():
    c=Canvas('06-substitution',True);header(c,sub='ONE PARENT · TWO CHILDREN')
    c.text('0 → 01        1 → 10',(320,220,1600,306),69,INK,'substitution-rules')
    vals=[s['value'] for s in SEQ[:4]]
    for j,v in enumerate(vals):
        x=300+j*350
        c.tile(v,(x+70,394,x+210,514),f'parent-{j}',size=70)
        c.arrow((x+110,537),(x+50,614),TEAL,5);c.arrow((x+170,537),(x+230,614),APRICOT,5)
        c.tile(v,(x,642,x+120,748),f'child-{2*j}',size=62)
        c.tile(1-v,(x+160,642,x+280,748),f'child-{2*j+1}',size=62)
    c.text('t(2n) = t(n)',(230,815,930,900),48,TEAL,'copy-recurrence')
    c.text('t(2n + 1) = 1 − t(n)',(950,815,1750,900),43,TEAL,'swap-recurrence')
    c.text('Replay of the first eight terms · count stays at 32',(270,977,1650,1027),28,MUTED,'replay-note')
    c.meta.update(replay=True,completed_count=32,seed_not_counted_again=True,shown_parent_indices=list(range(4)),child_values=[x['value'] for x in SEQ[:8]])
    return c.finish()


def parity():
    c=Canvas('07-binary-parity');header(c,sub='THE POSITION IN BINARY · COUNT ITS ONES')
    c.text('position 127 = 1111111₂',(230,220,1690,319),70,INK,'binary-position')
    for j in range(7):
        x=485+j*132;c.tile(1,(x,386,x+106,503),f'binary-one-{j}',size=70)
    c.text('7 ones → odd → 1',(270,563,1650,662),71,TEAL,'parity-result')
    c.text('t(127) = s₂(127) mod 2 = 1',(280,710,1640,794),54,INK,'popcount-rule')
    actor.draw(c,'look_up',foot=(1190,1040),height=190)
    footer(c,128)
    c.meta.update(replay=True,completed_count=128,index=127,binary_one_count=7,value=1)
    return c.finish()


def final_loom():
    c=Canvas('10-finished-loom',True);header(c,sub='256 TERMS · READ EACH ROW LEFT TO RIGHT')
    c.panel((170,210,1750,838),'#f4ead7',radius=25)
    for r in range(16):
        for col in range(16):
            k=16*r+col;x=210+col*94;y=236+r*36
            c.tile(SEQ[k]['value'],(x,y,x+84,y+31),f'loom-{k}',active=k==255,size=20)
    c.text('t(255) = 1 − t(127) = 0',(260,859,1660,925),47,INK,'last-equation')
    footer(c,256)
    c.meta.update(completed_count=256,grid_shape=[16,16],grid_order='row-major',grid_index_formula='k = 16r + c',zero_count=128,one_count=128,all_values=[x['value'] for x in SEQ])
    return c.finish()


def closing():
    c=Canvas('12-closing');header(c,sub='TWO VALUES · THE PATTERN KEEPS GROWING')
    c.text('t(255) = 0',(270,246,1650,356),86,INK,'last-value')
    c.text('0, 1, 1, 0, 1, 0, 0, 1, …',(260,446,1660,528),58,TEAL,'prefix')
    c.text('… 1, 0, 0, 1, 0, 1, 1, 0',(260,581,1660,663),58,TEAL,'suffix')
    c.text('128 zeros. 128 ones.',(350,718,1570,784),43,INK,'balanced-counts')
    actor.draw(c,'delight',foot=(610,1040),height=210)
    c.text('Terms counted: 256 / 256',(1240,962,1800,1026),25,MUTED,'progress')
    c.meta.update(replay=True,completed_count=256,last_index=255,value=0,preview_does_not_add_terms=True)
    return c.finish()


def save_still(c,name):
    path=OUT/f'{name}.png';c.im.convert('RGB').save(path)
    return {'path':str(path.relative_to(ROOT)),'sha256':sha(path),'size_px':[W,H],**c.meta,'alignment_observations':len(c.records),'actors':c.actor_records}


def main():
    global PLATE,TOP_PLATE,actor
    ap=argparse.ArgumentParser();ap.add_argument('--video',action='store_true');args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    PLATE=Image.open(BG).convert('RGBA').resize((W,H),Image.Resampling.LANCZOS)
    TOP_PLATE=Image.open(OVERHEAD).convert('RGBA').resize((W,H),Image.Resampling.LANCZOS)
    actor=Actor();records=[];manifest=[]
    scenes=[('01-opening',opening()),('02-seed',standard(0)),('03-copy',standard(2)),('04-swap',standard(3)),('05-complement',complement()),('06-substitution',substitution()),('07-binary-parity',parity()),('08-parent-is-not-previous',standard(4)),('09-index-128',standard(128)),('10-finished-loom',final_loom()),('11-index-255',standard(255)),('12-closing',closing())]
    for name,c in scenes:
        manifest.append(save_still(c,name));records.extend(c.records)
    board=Image.new('RGB',(1920,6*590),'#fff9ed');d=ImageDraw.Draw(board)
    for j,(name,c) in enumerate(scenes):
        x=j%2*960;y=j//2*590
        board.paste(c.im.convert('RGB').resize((960,540),Image.Resampling.LANCZOS),(x,y))
        d.text((x+30,y+551),name,font=font(23),fill=INK)
    board.save(OUT/'storyboard.png');board.resize((960,1770),Image.Resampling.LANCZOS).save(OUT/'storyboard-preview.jpg',quality=94)
    overview=Image.new('RGB',(1920,1080))
    for j,i in enumerate([0,3,4,9]):
        overview.paste(scenes[i][1].im.convert('RGB').resize((960,540),Image.Resampling.LANCZOS),(j%2*960,j//2*540))
    overview.save(OUT/'concept-overview.jpg',quality=96)
    # All fixed states plus input/operation/output phases around decimal index carries.
    for k in range(256):
        c=standard(k);records.extend(c.records)
    transitions=[]
    for k in [1,2,3,4,9,10,15,16,31,32,99,100,127,128,254,255]:
        for p in [0.,.1,.3,.5,.7,.9,.94,1.]:
            c=standard(k,p,counted=False);records.extend(c.records)
            transitions.append(c.meta)
    (QA/'mockup-alignment.json').write_text(json.dumps({'scope':'original 1080p RGBA glyph layers; not final MP4 acceptance','tolerance_px':.5,'all_fixed_states':256,'transition_states':len(transitions),'observations':len(records),'passed':all(x['passed'] for x in records),'max_abs_dx_px':max(abs(x['delta_x_px']) for x in records),'max_abs_dy_px':max(abs(x['delta_y_px']) for x in records),'records':records},ensure_ascii=False,indent=2)+'\n')
    (QA/'mockup-manifest.json').write_text(json.dumps({'video_generated':False,'full_episode_generated':False,'motion_study_generated':args.video or (OUT/'working-formula-study-1080p.mp4').exists(),'stills':manifest,'transitions':transitions,'actor_uses':actor.receipts,'backgrounds':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'source_size_px':list(Image.open(p).size),'display_size_px':[W,H],'scale_xy':[W/Image.open(p).width,H/Image.open(p).height],'status':'preproduction-only; final compressed quality pending'} for p in [BG,OVERHEAD]]},ensure_ascii=False,indent=2)+'\n')
    if args.video:
        ffmpeg=ROOT/'.venv/bin/ffmpeg'
        video=OUT/'working-formula-study-1080p.mp4'
        proc=subprocess.Popen([str(ffmpeg),'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
        for f in range(480):
            k=f//60;p=min(1.,(f%60)/48)
            c=standard(k,p,counted=f%60>=55,actor_pose='neutral')
            proc.stdin.write(c.im.convert('RGB').tobytes())
        proc.stdin.close()
        if proc.wait()!=0: raise RuntimeError('ffmpeg failed')
        subprocess.run([str(ffmpeg),'-v','error','-y','-i',str(video),'-vf','fps=8,scale=768:-1','-loop','0',str(OUT/'working-formula-study.gif')],check=True)
        (QA/'motion-study.json').write_text(json.dumps({'scope':'16 second silent formula-mechanism study only; no speech, not final episode','path':str(video.relative_to(ROOT)),'sha256':sha(video),'resolution_px':[1920,1080],'fps':30,'frames':480,'indices':list(range(8)),'character_motion':'fixed key pose per count; actor interpolation and speech sync pending; this study demonstrates the formula only','zero_reveal':'seed begins at zero; no parent operation','pending_result':'? until generation finishes','count_updates':'only at illustrative completion point near cycle end; real speech end binding pending'},indent=2)+'\n')
    print(json.dumps({'stills':len(scenes),'glyph_observations':len(records),'alignment_passed':all(x['passed'] for x in records),'video':args.video}))


if __name__=='__main__':
    main()
