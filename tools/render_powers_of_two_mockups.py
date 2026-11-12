"""Paper & Shadow Doubling Theatre: deterministic preproduction images.

Generated plate/character sources remain immutable. Mathematics, typography and
paper-unit geometry are separate raster layers. This is NOT completed-episode QA.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

try:
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/powers-of-two-counting-v1'
OUT, QA = DESIGN / 'mockups', DESIGN / 'qa'
BATCH = 'powers-of-two-20261112-01a1cd56'
BG = DESIGN / f'generation-batches/{BATCH}/source/theatre-clean-plate.png'
REG = ROOT / f'assets/library/characters/fairy-pitta/generation-batches/{BATCH}/registration.json'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE = (1920, 1080)
INK, MUTED, TEAL, RED, CREAM = '#51453f', '#807267', '#317e79', '#a45e61', '#fff9ea'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=32)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def number_words(n):
    small = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
    if n < 20:
        return small[n]
    if n < 100:
        return tens[n // 10] + ('-' + small[n % 10] if n % 10 else '')
    if n < 1000:
        return small[n // 100] + ' hundred' + (' ' + number_words(n % 100) if n % 100 else '')
    for scale, label in reversed([(1000, 'thousand'), (10**6, 'million'), (10**9, 'billion'), (10**12, 'trillion'), (10**15, 'quadrillion'), (10**18, 'quintillion'), (10**21, 'sextillion')]):
        if n >= scale:
            return number_words(n // scale) + ' ' + label + (' ' + number_words(n % scale) if n % scale else '')
    raise ValueError(n)


def bbox(layer, threshold=128):
    return layer.getchannel('A').point(lambda a: 255 if a >= threshold else 0).getbbox()


def trim(layer):
    b = bbox(layer)
    if b is None:
        raise ValueError('Empty foreground')
    return layer.crop((b[0]-20, b[1]-20, b[2]+20, b[3]+20))


@lru_cache(maxsize=512)
def text_layer(text, size, color=INK):
    b = font(size).getbbox(text)
    layer = Image.new('RGBA', (b[2]-b[0]+40, b[3]-b[1]+40))
    ImageDraw.Draw(layer).text((20-b[0], 20-b[1]), text, font=font(size), fill=color)
    return layer


def exponent_layer(n, size=96, suffix=''):
    base, power = text_layer('2', size), text_layer(str(n), round(size*.53), TEAL)
    bb, pb = bbox(base), bbox(power)
    layer = Image.new('RGBA', (500, size*2+80))
    # A raised glyph, rather than Unicode superscript coverage in the font.
    layer.alpha_composite(base, (20-bb[0], 38-bb[1]))
    x = 20 + bb[2]-bb[0] + 7
    layer.alpha_composite(power, (x-pb[0], 12-pb[1]))
    if suffix:
        s = text_layer(suffix, size)
        layer.alpha_composite(s, (x+pb[2]-pb[0]+12-bbox(s)[0], 38-bbox(s)[1]))
    return trim(layer)


def multiline_layer(lines, size, color=INK, spacing=12):
    pieces = [text_layer(t, size, color) for t in lines]
    bounds = [bbox(p) for p in pieces]
    w = max(b[2]-b[0] for b in bounds)
    h = sum(b[3]-b[1] for b in bounds) + spacing*(len(lines)-1)
    layer = Image.new('RGBA', (w+40, h+40))
    y = 20
    for piece, b in zip(pieces, bounds):
        x = round((w - (b[2]-b[0]))/2) + 20
        layer.alpha_composite(piece, (x-b[0], y-b[1]))
        y += b[3]-b[1] + spacing
    return layer


def diamonds(count, size=40, columns=8, color=INK, outline=False):
    columns = min(columns, count)
    rows = math.ceil(count/columns)
    step = size+18
    layer = Image.new('RGBA', (columns*step+40, rows*step+40))
    d = ImageDraw.Draw(layer)
    for k in range(count):
        x, y = 20+(k % columns)*step, 20+(k // columns)*step
        d.polygon([(x+size//2,y), (x+size,y+size//2), (x+size//2,y+size), (x,y+size//2)], fill=None if outline else color, outline=color, width=4)
    return trim(layer)


def connected_unit_count(layer):
    """Independently count disconnected unit silhouettes in the rendered alpha."""
    mask=layer.getchannel('A').point(lambda a:255 if a>=128 else 0)
    count=0
    while (b:=mask.getbbox()) is not None:
        y=b[1]
        x=next(x for x in range(b[0],b[2]) if mask.getpixel((x,y)))
        ImageDraw.floodfill(mask,(x,y),0)
        count+=1
    return count


class Canvas:
    def __init__(self, plate, scene):
        self.image, self.scene = plate.copy(), scene
        self.draw = ImageDraw.Draw(self.image)
        self.records, self.notes = [], {}

    def center(self, layer, box, ident, opacity=1):
        if opacity <= 0:
            self.notes.setdefault('intentionally_absent', []).append(ident)
            return
        layer = layer.copy()
        if opacity < 1:
            layer.putalpha(layer.getchannel('A').point(lambda a: round(a*opacity)))
        threshold = max(1, round(128*opacity))
        b = bbox(layer, threshold)
        if b is None:
            raise ValueError(f'Empty foreground: {ident}')
        xy = (round((box[0]+box[2]-b[0]-b[2])/2), round((box[1]+box[3]-b[1]-b[3])/2))
        report = raster_centering_report(layer, box, origin_xy=xy, name=f'{self.scene}/{ident}', tolerance_px=.5, alpha_threshold=threshold)
        report.update(scene=self.scene, component_id=ident, resolution_px=list(SIZE), horizontal='center', vertical='center', opacity=opacity)
        if not report['passed']:
            raise ValueError(report)
        self.records.append(report)
        self.image.alpha_composite(layer, xy)

    def text(self, text, box, size=32, color=INK, ident='text', opacity=1):
        self.center(text_layer(text, size, color), box, ident, opacity)
        if opacity > 0:
            self.records[-1].update(text=text, font_size_px=size)

    def lines(self, lines, box, size=30, color=INK, ident='lines'):
        self.center(multiline_layer(lines,size,color), box, ident)
        self.records[-1].update(text='\n'.join(lines), font_size_px=size, group='whole multiline glyph group')

    def panel(self, box, fill=CREAM, outline='#cfbd9e'):
        self.draw.rounded_rectangle(box, radius=22, fill=fill, outline=outline, width=2)


class Pitta:
    def __init__(self):
        library = json.loads((ROOT/'catalogs/character-library-v1.json').read_text())
        self.char = next(c for c in library['characters'] if c['id']=='fairy-pitta')
        self.poses = {}
        if REG.exists():
            registration = json.loads(REG.read_text())
            self.poses = registration.get('poses', registration.get('frames',{}))
            if isinstance(self.poses,list):
                self.poses = {x['id']:x for x in self.poses}
        self.used = {}

    @lru_cache(maxsize=64)
    def sprite(self, pose, height):
        row = self.char['neutral'] if pose=='neutral' or pose not in self.poses else self.poses[pose]
        path = ROOT/row['path']
        if sha(path) != row['sha256']:
            raise ValueError(f'Character source changed: {path}')
        scale = height/row['reference_height_px']
        image = Image.open(path).convert('RGBA')
        image = image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
        return image,row,scale

    def draw(self,c,pose='neutral',height=244,foot=(960,1020)):
        pose = {'cue':'cue_up','watch':'cue_half','open':'wonder_open','rest':'settle'}.get(pose,pose)
        im,row,scale = self.sprite(pose,height)
        anchor = row['anchor_px']
        xy = (round(foot[0]-anchor[0]*scale), round(foot[1]-anchor[1]*scale))
        b = bbox(im)
        visible = [b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]
        contained = 20<=visible[0] and 20<=visible[1] and visible[2]<=1900 and visible[3]<=1060
        if not contained:
            raise ValueError(f'Character clipped: {visible}')
        actual_anchor = [xy[0]+anchor[0]*scale,xy[1]+anchor[1]*scale]
        dx,dy = actual_anchor[0]-foot[0],actual_anchor[1]-foot[1]
        rec = dict(scene=c.scene,component_id='pitta',horizontal='foot-anchor-x',vertical='anatomical-foot-anchor-y',target_anchor_px=list(foot),actual_anchor_px=actual_anchor,delta_x_px=dx,delta_y_px=dy,tolerance_px=.5,contained=contained,passed=contained and abs(dx)<=.5 and abs(dy)<=.5,visible_box_xyxy=visible,reference_height_px=row['reference_height_px'],scene_body_height_px=height,scale=scale,source=row['path'],requested_pose=pose,used_pose=pose if pose in self.poses else 'neutral')
        c.records.append(rec)
        c.image.alpha_composite(im,xy)
        self.used[row['path']] = dict(sha256=row['sha256'],native_reference_height_px=row['reference_height_px'],max_display_reference_height_px=max(height,self.used.get(row['path'],{}).get('max_display_reference_height_px',0)))


def header(c, subtitle):
    c.text('POWERS OF 2', (400,72,1520,138), 45, ident='title')
    c.text(subtitle, (320,148,1600,188), 25, MUTED, 'subtitle')


def early_scene(plate,pitta,n,phase=1,scene=None):
    c = Canvas(plate,scene or f'count-{n:02d}')
    caption=f'Doublings: {n}' if phase>=1 or n==0 else f'Doublings: {n-1} → {n}'
    c.text(caption,(330,156,820,208),29,MUTED,'doublings')
    c.center(exponent_layer(n,88),(760,236,1160,356),'power')
    if n==0:
        c.text('= 1',(720,370,1200,462),86,ident='seed-equation')
        c.center(diamonds(1,86),(730,498,1190,638),'single-paper-unit')
        c.text('No doubling yet. Start with one.',(400,698,1520,760),33,TEAL,'seed-explanation')
        pitta.draw(c,'cue',288,(1300,1044))
        c.notes.update(exponent=0,value=1,exact_unit_count=1)
        return c
    value = 1<<n
    prev = value//2
    unresolved = phase<1
    c.text(f'{prev:,} × 2'+('' if unresolved else f' = {value:,}'),(420,376,1500,466),72,ident='operation')
    # Every diamond is one exact unit. The copy remains in its own group.
    c.center(diamonds(prev,42 if n<=4 else 26,columns=8),(390,504,860,650),'old-units')
    if phase>0:
        c.center(diamonds(prev,42 if n<=4 else 26,columns=8,color=TEAL,outline=True),(1060,504,1530,650),'new-units',min(1,phase))
    # Hinged paper shutter opens as the second group is revealed.
    aperture=math.sin(min(1,phase)*math.pi/2)
    w=round(84*(1-aperture))+4
    c.draw.rectangle((956-w,512,956,642),fill='#d7c7ac',outline='#a98a64',width=2)
    c.draw.rectangle((964,512,964+w,642),fill='#e8d9bf',outline='#a98a64',width=2)
    c.text('× 2',(868,534,1052,614),48,TEAL,'doubling-gate')
    c.text('same group',(420,674,830,714),28,MUTED,'old-caption')
    c.text('one more copy',(1090,674,1500,714),28,TEAL,'copy-caption')
    c.text('?' if unresolved else str(value),(700,728,1100,822),84,TEAL,'answer')
    c.text('Copy forming…' if unresolved else number_words(value),(470,830,1330,864),28,MUTED,'number-name')
    pitta.draw(c,'watch' if unresolved else 'open',220,(1430,1048))
    c.notes.update(exponent=n,value=value,previous=prev,phase=phase,exact_old_count=prev,exact_new_count=prev if phase>0 else 0,interpretation='one diamond equals one unit; accent outline marks the new copy')
    return c


def grouped_scene(plate,pitta,n,scene=None):
    c = Canvas(plate,scene or f'count-{n:02d}')
    value,prev = 1<<n,1<<(n-1)
    c.text('DOUBLE THE WHOLE GROUP',(350,156,1570,208),36,TEAL,'group-mode-title')
    c.center(exponent_layer(n,72),(700,212,1220,304),'power')
    c.text('Each box represents a whole group.',(420,328,1500,378),30,MUTED,'symbolic-caption')
    for ident,x,color in [('original',400,INK),('copy',1080,TEAL)]:
        c.panel((x,414,x+440,564),outline=color)
        c.text(f'{prev:,}',(x+20,432,x+420,526),48,color,f'{ident}-quantity')
        c.text('units',(x+80,528,x+360,556),22,color,f'{ident}-units')
    c.text('+',(870,444,1050,540),58,MUTED,'plus')
    c.text(f'{prev:,} × 2 = {value:,}',(340,612,1580,698),60,ident='operation')
    c.text(f'{value:,}',(360,728,1560,826),86,TEAL,'answer')
    c.text(number_words(value),(380,848,1540,898),28,MUTED,'number-name')
    pitta.draw(c,'open',175,(960,1052))
    c.notes.update(exponent=n,value=value,previous=prev,mode='two-labelled-whole-groups',exact_individual_units_shown=False)
    return c


def long_scene(plate,pitta,n,scene=None):
    c = Canvas(plate,scene or f'count-{n:02d}')
    value,prev = 1<<n,1<<(n-1)
    c.text(f'Doublings: {n}',(330,156,740,208),29,MUTED,'doublings')
    c.center(exponent_layer(n,74),(690,215,1230,312),'power')
    c.text('previous value',(520,328,1400,364),26,MUTED,'input-label')
    c.text(f'{prev:,}',(300,384,1620,466),62,ident='input-value')
    c.panel((834,470,1086,550),fill='#f3e7cc',outline='#b89461')
    c.text('× 2',(856,478,1064,544),56,TEAL,'doubling-gate')
    c.text('=',(900,570,1020,614),46,MUTED,'equals')
    c.text(f'{value:,}',(260,642,1660,756),76,TEAL,'answer')
    # Common type size and wrap width for ALL values in this long-number mode.
    lines=textwrap.wrap(number_words(value),width=68,break_long_words=False,break_on_hyphens=False)
    c.lines(lines,(280,778,1640,886),25,MUTED,'number-name')
    pitta.draw(c,'rest',132,(1440,1060))
    c.notes.update(exponent=n,value=value,previous=prev,mode='vertical-operation',no_quantity_decorations=True)
    return c


def intro_scene(plate,pitta):
    c=Canvas(plate,'01-intro')
    header(c,'ONE RULE. AN EVER-BIGGER NUMBER.')
    c.text('Start with one.',(400,218,1520,286),48,ident='intro-line')
    c.center(exponent_layer('n',130),(650,314,1270,498),'generic-power')
    c.text('Copy the whole group. Double it.',(340,548,1580,618),42,TEAL,'intro-rule')
    c.text('1   2   4   8   16   32   …',(330,655,1590,714),46,ident='preview-sequence')
    pitta.draw(c,'cue',320,(960,1050))
    return c


def ending_scene(plate,pitta,max_n):
    c=Canvas(plate,'09-ending')
    header(c,'KEEP THE RULE. KEEP GOING.')
    c.text('Next value = previous value × 2',(340,262,1580,340),48,ident='recurrence')
    c.center(exponent_layer('n',94),(690,370,1230,506),'general-power')
    c.text('1   2   4   8   16   32   …',(340,570,1580,638),48,TEAL,'ribbon')
    c.text(f'{max_n+1} terms • {max_n} doublings • starting at 1',(340,672,1580,730),32,MUTED,'ending-count')
    pitta.draw(c,'open',300,(960,1050))
    return c


def exponent_detail_scene(plate,pitta):
    """An off-center close view: the raised exponent counts operations."""
    c=Canvas(plate,'10-exponent-detail')
    c.center(exponent_layer(3,240),(330,218,900,478),'large-exponent')
    c.lines(['The raised 3 counts','three doubling steps.'],(980,248,1550,414),34,TEAL,'exponent-explanation')
    positions=[400,700,1000,1300]
    for k,(value,x) in enumerate(zip([1,2,4,8],positions)):
        c.text(str(value),(x-70,564,x+70,656),74,TEAL if k==3 else INK,f'step-value-{k}')
    arrow=Image.new('RGBA',(186,48))
    d=ImageDraw.Draw(arrow)
    d.line((20,24,158,24),fill=MUTED,width=4)
    d.polygon([(145,13),(166,24),(145,35)],fill=MUTED)
    for k in range(3):
        x=(positions[k]+positions[k+1])//2
        c.center(arrow,(x-94,584,x+94,632),f'doubling-arrow-{k+1}')
        c.text('× 2',(x-75,512,x+75,556),32,TEAL,f'doubling-label-{k+1}')
    c.text('3 doublings from 1',(330,722,1170,790),44,TEAL,'step-count')
    pitta.draw(c,'cue',320,(1400,1035))
    c.notes.update(exponent=3,start_value=1,result=8,exact_operation_count=3,sequence=[1,2,4,8],composition='large exponent left-mid; three operation arrows across stage; bird cues upper-left from lower right')
    return c


def load_plate(allow_fallback):
    if BG.exists():
        im=Image.open(BG).convert('RGBA')
        # Aspect-preserving crop is composition only; raw generated source is retained.
        target=SIZE[0]/SIZE[1]
        if im.width/im.height>target:
            w=round(im.height*target);x=(im.width-w)//2;im=im.crop((x,0,x+w,im.height))
        else:
            h=round(im.width/target);y=(im.height-h)//2;im=im.crop((0,y,im.width,y+h))
        return im.resize(SIZE,Image.Resampling.LANCZOS),False
    if not allow_fallback:
        raise FileNotFoundError(BG)
    im=Image.new('RGBA',SIZE,'#efe1c3');d=ImageDraw.Draw(im)
    d.rectangle((245,55,1675,970),fill='#fff9ea')
    return im,True


def storyboard(stills):
    sheet=Image.new('RGB',(1920,3*410),'#f2eadc')
    d=ImageDraw.Draw(sheet)
    for i,(name,image) in enumerate(stills):
        x,y=(i%3)*640,(i//3)*410
        sheet.paste(image.convert('RGB').resize((624,351),Image.Resampling.LANCZOS),(x+8,y+8))
        d.text((x+15,y+366),name,font=font(23),fill=INK)
    sheet.save(OUT/'storyboard.png')
    sheet.save(OUT/'storyboard-preview.jpg',quality=92)


def render_motion(plate,pitta,records):
    ffmpeg=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg')
    path=OUT/'doubling-motion-study-1080p.mp4'
    command=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-','-an','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(path)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE)
    gif=[]
    observations=[]
    # 12 seconds: 2 seconds old group; 3 seconds open and reveal; 7 seconds result.
    for frame in range(360):
        t=frame/30
        phase=0 if t<2 else min(1,(t-2)/3)
        c=early_scene(plate,pitta,3,phase,scene=f'motion-{frame:03d}')
        c.notes['time_sec']=t
        process.stdin.write(c.image.convert('RGB').tobytes())
        if frame%3==0:
            gif.append(c.image.convert('RGB').resize((960,540),Image.Resampling.LANCZOS))
        # All 360 frames are checked before encoding, not only the keyframes.
        observations.extend(c.records)
        if frame in [0,59,60,61,90,105,120,149,150,151,359]:
            c.image.convert('RGB').save(QA/f'motion-{frame:03d}.png')
            records.extend(c.records)
    process.stdin.close()
    if process.wait()!=0:
        raise RuntimeError('FFmpeg motion encode failed')
    gif[0].save(OUT/'doubling-motion-study.gif',save_all=True,append_images=gif[1:],duration=100,loop=0,optimize=False)
    decoded=subprocess.run([ffmpeg,'-hide_banner','-i',str(path),'-f','null','-'],capture_output=True,text=True)
    (QA/'motion-decode.log').write_text(decoded.stdout+decoded.stderr)
    if decoded.returncode or 'frame=  360' not in decoded.stderr:
        raise RuntimeError('Motion full decode/frame count failed; inspect motion-decode.log')
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),frames=360,fps=30,duration_sec=12,source_component_observations=len(observations),all_source_components_passed=all(r['passed'] for r in observations),full_decode_passed=True,decode_log=str((QA/'motion-decode.log').relative_to(ROOT)),audio=False,scope='slowed silent formula proof; 3sec reveal and 7sec answer hold do not specify episode cadence; normal episode gap remains2sec; not episode preview or final MP4 acceptance; character uses discrete keyposes, not final interpolated acting')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--max-exponent',type=int,default=64)
    ap.add_argument('--allow-fallback-plate',action='store_true')
    ap.add_argument('--skip-motion',action='store_true')
    args=ap.parse_args()
    if not 10<=args.max_exponent<=69:
        raise ValueError('Preproduction layout supports exponents 10 through 69')
    OUT.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    plate,fallback=load_plate(args.allow_fallback_plate)
    pitta=Pitta();records=[]
    scenes=[('01-intro',intro_scene(plate,pitta)),('02-zero-exponent',early_scene(plate,pitta,0)),('03-copy-in-motion',early_scene(plate,pitta,3,.5)),('04-four-times-two',early_scene(plate,pitta,3)),('05-whole-group-mode',grouped_scene(plate,pitta,6)),('06-one-thousand',grouped_scene(plate,pitta,10)),('07-long-number',long_scene(plate,pitta,40)),('08-largest-number',long_scene(plate,pitta,args.max_exponent)),('09-ending',ending_scene(plate,pitta,args.max_exponent))]
    for name,c in scenes:
        c.image.convert('RGB').save(OUT/f'{name}.png')
        records.extend(c.records)
    storyboard([(name,c.image) for name,c in scenes])
    detail=exponent_detail_scene(plate,pitta)
    detail.image.convert('RGB').save(OUT/'10-exponent-detail.png')
    records.extend(detail.records)
    # All fixed states, including the smallest/longest English names and digit crossings.
    state_notes=[]
    for n in range(args.max_exponent+1):
        c=early_scene(plate,pitta,n) if n<=5 else grouped_scene(plate,pitta,n) if n<=10 else long_scene(plate,pitta,n)
        records.extend(c.records);state_notes.append(c.notes)
        if n in [3,4,9,10,11,60,63,args.max_exponent]:
            c.image.convert('RGB').save(QA/f'count-{n:02d}.png')
    unit_checks=[]
    for n in range(6):
        expected=1 if n==0 else 1<<(n-1)
        for outline in [False,True]:
            actual=connected_unit_count(diamonds(expected,42 if n<=4 else 26,columns=8,outline=outline))
            unit_checks.append(dict(exponent=n,expected_per_group=expected,outline=outline,measured_connected_units=actual,passed=actual==expected))
    if not all(r['passed'] for r in unit_checks):
        raise ValueError('Rendered unit geometry count mismatch')
    motion=None if args.skip_motion else render_motion(plate,pitta,records)
    plate_size=list(Image.open(BG).size) if BG.exists() else None
    report=dict(schema_version=1,status='pass' if all(r['passed'] for r in records) else 'fail',scope='preproduction source-raster mockups; no completed episode, speech synchronization, decoded video alignment, or human continuous review',resolution_px=list(SIZE),source_plate_fallback=fallback,plate_native_size_px=plate_size,plate_display_scale=max(SIZE[0]/plate_size[0],SIZE[1]/plate_size[1]) if plate_size else None,plate_quality_status='soft-watercolor preproduction plate; upscale recorded; final compressed-video acceptance pending',max_exponent=args.max_exponent,term_count=args.max_exponent+1,math_state_count=len(state_notes),static_states=state_notes,unit_geometry_checks=unit_checks,measurement='independent foreground alpha threshold 128; parent/background excluded; rounded pixel placement; .5px each axis',component_observations=len(records),max_abs_dx_px=max(abs(r['delta_x_px']) for r in records),max_abs_dy_px=max(abs(r['delta_y_px']) for r in records),records=records,character_assets=pitta.used,motion=motion,inputs={str(p.relative_to(ROOT)):sha(p) for p in [BG,FONT,REG] if p.exists()})
    (QA/'mockup-alignment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    manifest=dict(schema_version=1,kind='preproduction-mockup-output',completed_episode=False,source_plate_fallback=fallback,outputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.iterdir()) if p.is_file()],renderer=dict(path=str(Path(__file__).relative_to(ROOT)),sha256=sha(__file__)),qa=str((QA/'mockup-alignment.json').relative_to(ROOT)))
    (QA/'mockup-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','component_observations','max_abs_dx_px','max_abs_dy_px','term_count','source_plate_fallback']},ensure_ascii=False))


if __name__=='__main__':
    main()
