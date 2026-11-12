"""Arithmetic-sequence planning stills and a silent working-formula study.

The generated plate and character drawings remain immutable. Mathematical marks,
groups and moving counters are deterministic raster layers. This is preproduction
evidence; it is not the completed counting episode or an audio acceptance gate.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

try:
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/arithmetic-sequence-counting-v1'
OUT = DESIGN / 'mockups'
QA = DESIGN / 'qa/layout'
BG = DESIGN / 'generation-batches/wind-organ-hall-20261112-01a1cdca/source/wind-organ-hall.png'
NEW_ACTOR = ROOT / 'assets/library/characters/hedgehog/generation-batches/arithmetic-preproduction-20261112-01a1cdca/registration.json'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE = (1920, 1080)
INK, TEAL, GOLD, PALE, MUTED = '#364c4a', '#357e7b', '#c9823e', '#fffaf0', '#73877c'
MINT, SAND = '#d9eee6', '#f3d8a8'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=90)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def words(n):
    ones = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
    if n < 20:
        return ones[n]
    if n < 100:
        return tens[n // 10] + ('-' + ones[n % 10] if n % 10 else '')
    return ones[n // 100] + ' hundred' + (' ' + words(n % 100) if n % 100 else '')


def bbox(layer, threshold=128):
    return layer.getchannel('A').point(lambda p: 255 if p >= threshold else 0).getbbox()


def glyphs(text, size, color=INK):
    f = font(size)
    b = f.getbbox(text)
    im = Image.new('RGBA', (b[2] - b[0] + 60, b[3] - b[1] + 60))
    ImageDraw.Draw(im).text((30 - b[0], 30 - b[1]), text, font=f, fill=color)
    return im


def indexed_formula(tail, size=65, index='n'):
    """Draw actual a-subscript-index, avoiding font-dependent subscript glyphs."""
    lead = glyphs('a', size)
    sub = glyphs(str(index), round(size * .52), TEAL)
    rest = glyphs(tail, size)
    bl, bs, br = [bbox(x) for x in (lead, sub, rest)]
    wl, ws, wr = [b[2] - b[0] for b in (bl, bs, br)]
    h = max(bl[3] - bl[1] + 20, br[3] - br[1])
    im = Image.new('RGBA', (wl + ws + wr + 88, h + 70))
    im.alpha_composite(lead, (25 - bl[0], 25 - bl[1]))
    im.alpha_composite(sub, (25 + wl - bs[0], 25 + round(size * .55) - bs[1]))
    im.alpha_composite(rest, (42 + wl + ws - br[0], 25 - br[1]))
    return im


class Canvas:
    def __init__(self, plate, scene, time=None):
        self.image = plate.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.scene, self.time = scene, time
        self.records, self.actors, self.absent = [], [], []
        self.data = {}

    def center(self, layer, box, ident, opacity=1):
        if opacity <= 0:
            self.absent.append({'component_id': ident, 'reason': 'intentionally not yet generated'})
            return
        if opacity < 1:
            layer = layer.copy()
            layer.putalpha(layer.getchannel('A').point(lambda a: round(a * opacity)))
        threshold = max(1, round(128 * opacity))
        b = bbox(layer, threshold)
        if b is None:
            raise ValueError(f'Empty component {self.scene}/{ident}')
        xy = (round((box[0] + box[2] - b[0] - b[2]) / 2),
              round((box[1] + box[3] - b[1] - b[3]) / 2))
        rec = raster_centering_report(layer, box, origin_xy=xy,
                                     name=f'{self.scene}/{ident}', tolerance_px=.5,
                                     alpha_threshold=threshold)
        rec.update(component_id=ident, scene=self.scene, time_s=self.time,
                   horizontal='center', vertical='center', resolution_px=list(SIZE), opacity=opacity)
        if not rec['passed']:
            raise ValueError(rec)
        self.records.append(rec)
        self.image.alpha_composite(layer, xy)

    def text(self, text, box, size=38, color=INK, ident=None, opacity=1):
        self.center(glyphs(text, size, color), box, ident or text, opacity)
        if opacity > 0:
            self.records[-1].update(text=text, font_size_px=size)

    def panel(self, box, fill=PALE, outline='#d8cfb9', radius=35):
        self.draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

    def multiline(self, lines, box, size=38, color=INK, ident='multiline', gap=15):
        parts = [glyphs(x, size, color) for x in lines]
        boxes = [bbox(x) for x in parts]
        width = max(b[2] - b[0] for b in boxes)
        height = sum(b[3] - b[1] for b in boxes) + gap * (len(lines) - 1)
        im = Image.new('RGBA', (width + 60, height + 60))
        y = 30
        for p, b in zip(parts, boxes):
            im.alpha_composite(p, (round((width - b[2] + b[0]) / 2) + 30 - b[0], y - b[1]))
            y += b[3] - b[1] + gap
        self.center(im, box, ident)
        self.records[-1].update(text='\n'.join(lines), font_size_px=size,
                                group='whole intended multiline glyph group')

    def counter(self, x, y, radius=18, seed=False):
        self.draw.ellipse((x-radius, y-radius, x+radius, y+radius),
                          fill=MINT if seed else SAND,
                          outline=TEAL if seed else GOLD, width=3)

    def clearance(self):
        rows = self.records + self.actors
        for i, a in enumerate(rows):
            x1, y1, x2, y2 = a['visible_box_xyxy']
            for b in rows[i+1:]:
                u1, v1, u2, v2 = b['visible_box_xyxy']
                if max(x1, u1) < min(x2, u2) and max(y1, v1) < min(y2, v2):
                    raise ValueError(f'Foreground groups collide: {a.get("component_id")} / {b.get("component_id")}')
        self.data['independent_text_and_actor_clearance'] = True


class Actor:
    def __init__(self):
        lib = json.loads((ROOT / 'catalogs/character-library-v1.json').read_text())
        self.char = next(c for c in lib['characters'] if c['id'] == 'hedgehog')
        self.poses = {'neutral': self.char['neutral'], **self.char['key_poses']['poses']}
        if NEW_ACTOR.exists():
            reg = json.loads(NEW_ACTOR.read_text())
            for k, v in reg.get('poses', {}).items():
                self.poses[k] = v
        self.receipts = {}

    @lru_cache(maxsize=60)
    def sprite(self, pose, height):
        row = self.poses.get(pose, self.poses['neutral'])
        path = ROOT / row['path']
        if sha(path) != row['sha256']:
            raise ValueError(f'Actor hash mismatch {path}')
        im = Image.open(path).convert('RGBA')
        region = row.get('image_region_px')
        ox, oy = (0, 0)
        if region and tuple(region) != (0, 0, im.width, im.height):
            ox, oy = region[:2]
            im = im.crop(tuple(region))
        scale = height / row['reference_height_px']
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
        anchor = [(row['anchor_px'][0] - ox)*scale, (row['anchor_px'][1] - oy)*scale]
        return im, anchor, row, scale

    def draw(self, c, pose='neutral', foot=(960, 1010), height=280):
        im, anchor, row, scale = self.sprite(pose, height)
        xy = (round(foot[0]-anchor[0]), round(foot[1]-anchor[1]))
        b = bbox(im, 8)
        absolute = [b[0]+xy[0], b[1]+xy[1], b[2]+xy[0], b[3]+xy[1]]
        if not (18 < absolute[0] < absolute[2] < 1902 and 18 < absolute[1] < absolute[3] < 1058):
            raise ValueError(f'Actor cut off {pose}: {absolute}')
        c.draw.ellipse((foot[0]-90, foot[1]-7, foot[0]+90, foot[1]+10), fill=(78,91,75,24))
        c.image.alpha_composite(im, xy)
        rec = {'component_id': 'hedgehog', 'pose': pose, 'path': row['path'], 'sha256': row['sha256'],
               'horizontal': 'anatomical foot anchor', 'vertical': 'grounded support anchor',
               'reference_height_px': row['reference_height_px'], 'display_body_height_px': height,
               'source_scale': scale, 'foot_anchor_px': list(foot), 'visible_box_xyxy': absolute,
               'contained': True, 'clipped': False, 'not_centering_target': True, 'mirrored': False,
               'source_pixels_modified': False}
        c.actors.append(rec)
        self.receipts[f'{pose}@{height}'] = rec


def header(c, subtitle='NUM-NUM NUMBERS · THE MORNING WIND ORGAN'):
    c.text('ARITHMETIC SEQUENCE', (250, 42, 1670, 116), 53, INK, 'series-title')
    c.text(subtitle, (220, 126, 1700, 162), 22, TEAL, 'scene-subtitle')


def footer(c, n, counted=True):
    c.text(f'Terms counted: {n if counted else n-1} / 101', (500, 1033, 1420, 1063), 22, MUTED, 'progress')


def opening(plate, actor):
    c = Canvas(plate, '01-opening')
    header(c)
    c.text('A little breeze. Three more.', (300, 224, 1620, 314), 65, TEAL, 'opening-promise')
    c.center(indexed_formula(' = 2 + (n − 1) × 3', 64), (320, 353, 1600, 465), 'general-rule')
    c.text('2,  5,  8,  11,  14, …', (450, 531, 1470, 612), 55, GOLD, 'sequence-preview')
    actor.draw(c, 'greet', height=350)
    c.data.update(scene_role='wide opening', upcoming_values_are_preview=True,
                  character_relation='front-center greets, then looks up to the active rule')
    c.clearance()
    return c


def ordinary(plate, actor, n=2, phase='result', progress=1, name=None, time=None, actor_pose='neutral'):
    value = 2 + 3*(n-1)
    previous = value-3
    c = Canvas(plate, name or f'count-{n}-{phase}', time)
    header(c, 'THE SAME DIFFERENCE · ADD THREE')
    c.panel((345, 190, 1575, 325))
    c.text(f'{previous} + 3 = ' + (str(value) if phase == 'result' else ''),
           (370, 206, 1550, 305), 80, INK, 'working-equation')
    c.text('THREE MORE', (360, 367, 700, 410), 28, TEAL, 'fixed-addend-label')
    # These are the three units of the addend, not decoration or the total.
    start, finish = 500, 1000
    for j in range(3):
        x = start + j*58 + (finish-start)*progress
        y = 580 - math.sin(math.pi*progress)*40
        c.counter(x, y, radius=18)
    c.data.update(n=n, previous_value=previous, value=value, increment=3,
                  actual_unit_counters=3, counters_represent='only the +3 increment', phase=phase,
                  result_committed=phase == 'result', counter_travel_fraction=progress)
    # Result is not placed over the moving counters; the units land beneath it.
    if phase == 'result':
        c.text(str(value), (740, 363, 1360, 592), 180, GOLD, 'generated-value')
        c.text(words(value), (330, 610, 1590, 663), 36, INK, 'natural-reading')
    else:
        c.text('Watch three arrive.', (730, 360, 1500, 421), 39, TEAL, 'process-caption')
        c.absent.append({'component_id': 'generated-value', 'reason': 'not shown before the three arrive'})
    # Recent values are a window, not all units or terms in the sequence.
    values = [2+3*(j-1) for j in range(max(1, n-4), n if phase != 'result' else n+1)]
    c.text('   →   '.join(map(str, values)), (420, 680, 1500, 722), 29, TEAL, 'recent-terms')
    actor.draw(c, actor_pose, height=280)
    footer(c, n, phase == 'result')
    c.clearance()
    return c


def groups(plate, actor, n=4, stage='complete', progress=1, name=None, time=None):
    value = 2+3*(n-1)
    c = Canvas(plate, name or f'general-{n}-{stage}', time)
    header(c, 'ONE LESS THAN n · GROUPS OF THREE' if n == 1 else 'REPLAY · (n − 1) GROUPS OF THREE')
    c.panel((280, 190, 1640, 330))
    tail = f' = 2 + ({n} − 1) × 3'
    if stage in ('multiply', 'join', 'complete'):
        tail = f' = 2 + {n-1} × 3'
    if stage in ('join', 'complete'):
        tail += f' = {value}'
    c.center(indexed_formula(tail, 65, str(n)), (306, 212, 1614, 313), 'working-general-formula')
    c.text(f'n = {n}', (760, 350, 1160, 402), 39, TEAL, 'input-term-number')
    if n == 1:
        c.text('0 groups of three', (930, 460, 1510, 514), 39, TEAL, 'group-count')
        for x in (650,710):
            c.counter(x, 505, radius=22, seed=True)
        c.text('Start with 2', (530, 568, 850, 615), 31, TEAL, 'seed-label')
        c.text('No group is added.', (850, 575, 1610, 625), 37, INK, 'zero-groups-explanation')
    else:
        # Exact 2 + three groups containing three units each.
        seed_x, row_y = 610, 526
        for x in (seed_x-27, seed_x+27):
            c.counter(x, row_y, radius=21, seed=True)
        c.text('START: 2', (440, 606, 780, 649), 28, TEAL, 'seed-label')
        count = 3 if n == 4 else n-1
        if count == 3:
            for k,x in enumerate((870, 1120, 1370)):
                c.draw.rounded_rectangle((x-91, 436, x+91, 584),radius=28, fill='#fffcf4',outline='#dfcbaa',width=2)
                visible_units = 3 if stage in ('multiply','join','complete') else 0
                if stage == 'multiply':
                    visible_units = min(3, max(0, math.ceil(progress*9 - 3*k)))
                for j in range(visible_units):
                    c.counter(x+(j-1)*48, row_y, radius=17)
            c.text('3 GROUPS × 3', (790, 606, 1490, 649), 30, GOLD, 'groups-label')
        else:
            # Each outlined small group contains exactly three visible units.
            for row in range(10):
                for col in range(10):
                    x,y = 840+col*58, 438+row*24
                    c.draw.rounded_rectangle((x-23,y-9,x+23,y+9),radius=6,outline='#d5b88b',width=1)
                    for off in (-13,0,13):
                        c.counter(x+off,y,radius=4)
            c.text('100 groups of three = 300', (740, 710, 1510, 757), 29, GOLD, 'groups-label')
    if stage in ('join', 'complete'):
        c.text(str(value), (1110, 791, 1530, 951), 123, GOLD, 'generated-value')
        c.text(words(value), (640, 971, 1710, 1015), 31, INK, 'natural-reading')
    else:
        c.text('Find the number of groups.', (650, 805, 1590, 875), 40, TEAL, 'process-caption')
    actor.draw(c, 'present' if 'present' in actor.poses else 'think', foot=(395, 1010), height=260)
    footer(c,n)
    c.data.update(n=n,value=value,seed_unit_count=2,group_count=n-1,units_per_group=3,
                  exact_total=2+3*(n-1), stage=stage, scene_role='organized mathematical plane with lower-corner guide; background camera is unchanged',
                  explanation_replay_does_not_add_terms=True)
    c.clearance()
    return c


def carry(plate, actor):
    c = ordinary(plate,actor,34, name='06-carry-98-to-101')
    # Reveal the actual regrouping independently from the three addend counters.
    # Labels describe tens and ones; no false 101-object illustration is used.
    c.panel((1450, 405, 1780, 625), fill='#f5faf4',radius=24)
    c.multiline(['REPLAY', '98 + 2 = 100', '100 + 1 = 101'], (1466, 428, 1764, 605), 29, TEAL,'carry-explanation')
    c.data.update(carry_split=[2,1],split_sum=3,source_value=98,result_value=101)
    c.clearance()
    return c


def finale(plate, actor):
    c = Canvas(plate,'08-finale')
    header(c,'ONE RULE · THE SEQUENCE KEEPS GOING')
    c.center(indexed_formula(' = 2 + (n − 1) × 3',65), (300,218,1620,340),'general-rule')
    c.text('2, 5, 8, 11, 14, …', (330,425,1590,497),55,TEAL,'beginning-values')
    c.text('…, 296, 299, 302', (330,547,1590,632),65,GOLD,'ending-values')
    c.text('101 terms. The same difference: +3.',(330,667,1590,721),34,INK,'completed-count')
    actor.draw(c,'greet',height=260)
    footer(c,101)
    c.data.update(first_values=[2,5,8,11,14],last_values=[296,299,302],count=101,
                  continuation_beyond_movie=True)
    c.clearance()
    return c


def animation(plate,actor,k,fps=15):
    t=k/fps
    if t < 2.5:
        return groups(plate,actor,4,'input',name='animation-general-input',time=t)
    if t < 5.0:
        return groups(plate,actor,4,'multiply',(t-2.5)/2.5,name='animation-three-groups',time=t)
    if t < 7.5:
        return groups(plate,actor,4,'join',name='animation-general-output',time=t)
    if t < 9.0:
        return ordinary(plate,actor,4,'input',0,name='animation-recurrence-input',time=t)
    if t < 11.7:
        return ordinary(plate,actor,4,'travel',(t-9)/2.7,name='animation-three-in-flight',time=t)
    return ordinary(plate,actor,4,'result',1,name='animation-generated-eleven',time=t)


def validate_all_states(plate,actor):
    records=[]
    for n in range(2,102):
        c=ordinary(plate,actor,n)
        records.extend(c.records)
    # n=1 uses the zero-group mode rather than a nonexistent previous term.
    for n in (1,4,101):
        c=groups(plate,actor,n)
        records.extend(c.records)
    for phase,p in [('input',0),('travel',.25),('travel',.5),('travel',.75),('result',1)]:
        c=ordinary(plate,actor,34,phase,p)
        records.extend(c.records)
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-animation',action='store_true')
    args=parser.parse_args()
    if not BG.is_file():
        raise SystemExit(f'Generated background has not arrived: {BG}')
    OUT.mkdir(parents=True,exist_ok=True)
    QA.mkdir(parents=True,exist_ok=True)
    original=Image.open(BG).convert('RGB')
    if original.width/original.height < 1.70:
        raise ValueError('Wide background expected; do not stretch the plate')
    # Cover scaling preserves aspect ratio; crop only the nonessential extreme edges.
    scale=max(SIZE[0]/original.width,SIZE[1]/original.height)
    scaled=original.resize((round(original.width*scale),round(original.height*scale)),Image.Resampling.LANCZOS)
    left,top=(scaled.width-SIZE[0])//2,(scaled.height-SIZE[1])//2
    plate=scaled.crop((left,top,left+SIZE[0],top+SIZE[1])).convert('RGBA')
    actor=Actor()
    shots=[opening(plate,actor),ordinary(plate,actor,2,'travel',.5,'02-three-in-flight',actor_pose='offer'),
           groups(plate,actor,1,name='03-first-term-zero-groups'),
           groups(plate,actor,4,name='04-general-term-three-groups'),
           ordinary(plate,actor,4,name='05-eight-plus-three'),carry(plate,actor),
           groups(plate,actor,101,name='07-maximum-302'),finale(plate,actor)]
    records=[]
    for c in shots:
        path=OUT/f'{c.scene}.png'
        c.image.convert('RGB').save(path)
        records.extend(c.records)
        (QA/f'{c.scene}.json').write_text(json.dumps({'scene':c.scene,'native_image':str(path.relative_to(ROOT)),
            'image_sha256':sha(path),'components':c.records,'actors':c.actors,'intentional_absences':c.absent,
            'mathematical_and_composition_metadata':c.data},ensure_ascii=False,indent=2)+'\n')
    all_states=validate_all_states(plate,actor)
    records.extend(all_states)
    captions=['01  Welcome to the wind organ','02  The same three units travel',
              '03  First term: zero groups','04  n = 4: three groups of three',
              '05  Eight plus three makes eleven','06  A carry: ninety-eight to 101',
              '07  101 terms: the value 302','08  One rule, a sequence continues']
    thumb_w,thumb_h=960,540
    sheet=Image.new('RGB',(1968,4*620+24),'#fcf7ed')
    sd=ImageDraw.Draw(sheet)
    for i,(c,caption) in enumerate(zip(shots,captions)):
        x,y=16+(i%2)*976,16+(i//2)*620
        sheet.paste(c.image.convert('RGB').resize((thumb_w,thumb_h),Image.Resampling.LANCZOS),(x,y))
        sd.text((x+10,y+552),caption,font=font(25),fill=INK)
    sheet.save(OUT/'storyboard.png')
    sheet.resize((1181,1502),Image.Resampling.LANCZOS).save(OUT/'storyboard-preview.jpg',quality=94)
    animation_records=[]
    decoded_times=[]
    if not args.skip_animation:
        ffmpeg=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg')
        target=OUT/'working-formula-silent-preview.mp4'
        process=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
            '-s','1920x1080','-r','15','-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',
            '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',str(target)],stdin=subprocess.PIPE)
        for k in range(210):
            c=animation(plate,actor,k)
            process.stdin.write(c.image.convert('RGB').tobytes())
            animation_records.extend(c.records)
            if k in (0,36,38,56,74,76,112,114,134,136,155,174,176,209):
                c.image.convert('RGB').save(QA/f'animation-frame-{k:03d}.png')
        process.stdin.close()
        if process.wait():
            raise RuntimeError('FFmpeg preview encoding failed')
        subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-i',str(target),'-f','null','-'],check=True)
        decoded_times=[0,2.6,4.9,7,8.9,10.6,11.7,13.9]
        contact=Image.new('RGB',(1600,550),'#fcf7ed')
        cd=ImageDraw.Draw(contact)
        for i,t in enumerate(decoded_times):
            decoded=subprocess.run([ffmpeg,'-v','error','-ss',str(t),'-i',str(target),'-frames:v','1',
                '-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True)
            native=Image.open(io.BytesIO(decoded.stdout)).convert('RGB')
            native.save(QA/f'preview-decoded-{str(t).replace(".","-")}s.png')
            x,y=(i%4)*400,(i//4)*275
            contact.paste(native.resize((400,225),Image.Resampling.LANCZOS),(x,y))
            cd.text((x+10,y+235),f'{t:.1f}s',font=font(22),fill=INK)
        contact.save(QA/'preview-decoded-contact.jpg',quality=95)
        records.extend(animation_records)
    report = {'status':'passed','scope':'planning raster masks only; completed episode not generated',
        'counted_values':101,'ordinary_completed_states':100,'zero_group_state':1,
        'fixed_layout_components':all_states,'animation_components':animation_records,
        'observations':len(records),'maximum_absolute_dx_px':max(abs(x['delta_x_px']) for x in records),
        'maximum_absolute_dy_px':max(abs(x['delta_y_px']) for x in records),
        'tolerance_px':.5,'all_contained':all(x['contained'] for x in records),
        'no_empty_components':True,'no_measurement_edge_clipping':all(not x['touches_measurement_edge'] for x in records),
        'actual_glyph_bounds_measured':True,
        'background':{'path':str(BG.relative_to(ROOT)),'sha256':sha(BG),'source_size_px':list(original.size),
                      'display_size_px':list(SIZE),'uniform_scale':scale,'cover_crop_ltrb_px':[left,top,left+1920,top+1080]},
        'actor_usage':list(actor.receipts.values()),
        'limitations':['Silent study is 14 seconds at 15fps; completed episode target is 30fps.',
                      'Decoded final-episode alignment/audio/acting gates remain future production work.',
                      'Continuous character motion is not proven by these separate key poses.',
                      'The group diagram is organized as a mathematical plane; the background camera has not been transformed to an overhead view.']}
    (QA/'all-state-alignment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    receipts = [{'scene':c.scene, 'native_image':str((OUT/f'{c.scene}.png').relative_to(ROOT)),
                 'image_sha256':sha(OUT/f'{c.scene}.png'), 'component_observations':len(c.records),
                 'actors':c.actors, 'scene_metadata':c.data,
                 'qa_receipt':str((QA/f'{c.scene}.json').relative_to(ROOT))} for c in shots]
    summary = {'status':'passed', 'scope':'preproduction raster mocks and silent working-formula study',
               'resolution_px':list(SIZE), 'static_native_stills':len(shots),
               'static_component_observations':sum(len(c.records) for c in shots),
               'all_state_component_observations':len(all_states),
               'animation_component_observations':len(animation_records),
               'total_component_observations':len(records),
               'ordinary_completed_values':100,'zero_group_first_term':1,
               'additional_general_term_modes':[1,4,101],
               'additional_carry_transition_phases':['input','travel 25%','travel 50%','travel 75%','result'],
               'maximum_absolute_dx_px':report['maximum_absolute_dx_px'],
               'maximum_absolute_dy_px':report['maximum_absolute_dy_px'], 'tolerance_px':.5,
               'all_contained':report['all_contained'],
               'scene_receipts':receipts, 'background':report['background'],
               'character_quality_scope':'Separate key poses, not finished continuous acting; same pose held inside each animation shot.',
               'camera_scope':'Frontal background throughout; mathematical group plane is arranged for an overhead explanation, with no actual camera transform.',
               'silent_preview':{'generated':not args.skip_animation,'duration_s':14,'fps':15,'frames':210,
                                 'audio':'intentionally absent','full_decode':'passed' if not args.skip_animation else 'not run',
                                 'native_decoded_visual_samples_s':decoded_times},
               'limitations':report['limitations']}
    (QA/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    deliverables=[OUT/f'{c.scene}.png' for c in shots]
    deliverables.extend([OUT/'storyboard.png',OUT/'storyboard-preview.jpg',QA/'summary.json',
                         QA/'all-state-alignment.json',Path(__file__)])
    if not args.skip_animation:
        deliverables.extend([OUT/'working-formula-silent-preview.mp4',QA/'preview-decoded-contact.jpg'])
    manifest={'scope':'final preproduction deliverables; replay labels included',
              'sha256':{str(path.relative_to(ROOT)):sha(path) for path in deliverables}}
    (QA/'final-deliverable-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'passed','stills':len(shots),'alignment_observations':len(records),
        'storyboard':str(OUT/'storyboard-preview.jpg'),'silent_preview':not args.skip_animation},ensure_ascii=False))


if __name__=='__main__':
    main()
