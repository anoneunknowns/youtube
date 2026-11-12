"""Deterministic triangular-number preproduction stills and equation study.

The generated clean plate and character art are immutable inputs. Mathematical
symbols, counts, point IDs and motion are drawn here. This is not episode QA.
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

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/triangular-counting-v1'
OUT, QA = DESIGN / 'mockups', DESIGN / 'qa'
BATCH = 'triangular-20261112-01a1cd42'
BG = DESIGN / f'generation-batches/{BATCH}/source/cave-clean-plate.png'
REG = ROOT / f'assets/library/characters/meerkat/generation-batches/{BATCH}/registration.json'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE = (1920, 1080)
FFMPEG = shutil.which('ffmpeg') or str(ROOT / '.venv/bin/ffmpeg')
INK, MUTED = '#544b42', '#766f60'
AMBER, EDGE, TEAL, CREAM = '#edbc62', '#a66c32', '#478b88', '#fffaf0'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=64)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def words(n):
    ones = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
    if n < 20:
        return ones[n]
    if n < 100:
        return tens[n // 10] + ('-' + ones[n % 10] if n % 10 else '')
    if n < 1000:
        return ones[n // 100] + ' hundred' + (' ' + words(n % 100) if n % 100 else '')
    return words(n // 1000) + ' thousand' + (' ' + words(n % 1000) if n % 1000 else '')


def visible(layer, threshold=128):
    return layer.getchannel('A').point(lambda a: 255 if a >= threshold else 0).getbbox()


def text_layer(text, size, color=INK):
    if 'ₙ' in text:
        # This project font lacks the Unicode subscript-n glyph. Render an
        # actual smaller n on a lowered baseline, then measure the whole group.
        parts=text.split('ₙ')
        width=sum(font(size).getlength(p) for p in parts)+(len(parts)-1)*font(round(size*.64)).getlength('n')
        scratch=Image.new('RGBA',(math.ceil(width)+80,size*2+80))
        draw=ImageDraw.Draw(scratch);x=40
        for i,part in enumerate(parts):
            draw.text((x,30),part,font=font(size),fill=color)
            x+=font(size).getlength(part)
            if i<len(parts)-1:
                draw.text((x,30+size*.39),'n',font=font(round(size*.64)),fill=color)
                x+=font(round(size*.64)).getlength('n')
        b=visible(scratch)
        return scratch.crop((b[0]-20,b[1]-20,b[2]+20,b[3]+20))
    box = font(size).getbbox(text)
    layer = Image.new('RGBA', (box[2] - box[0] + 40, box[3] - box[1] + 40))
    ImageDraw.Draw(layer).text((20 - box[0], 20 - box[1]), text, font=font(size), fill=color)
    return layer


def colored_text_layer(parts, size):
    w=math.ceil(sum(font(size).getlength(text) for text,color in parts))
    layer=Image.new('RGBA',(w+80,size*2+80))
    draw=ImageDraw.Draw(layer);x=40
    for text,color in parts:
        draw.text((x,30),text,font=font(size),fill=color)
        x+=font(size).getlength(text)
    b=visible(layer)
    return layer.crop((b[0]-20,b[1]-20,b[2]+20,b[3]+20))


class Canvas:
    def __init__(self, plate, scene):
        self.image, self.scene = plate.copy(), scene
        self.draw = ImageDraw.Draw(self.image)
        self.records, self.data, self.layers = [], {}, {}

    def panel(self, box, fill=CREAM, outline='#d8cfb9', radius=28):
        self.draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

    def center(self, layer, box, ident, opacity=1):
        if opacity <= 0:
            self.data.setdefault('intentional_absences', []).append(ident)
            return
        if opacity != 1:
            layer = layer.copy()
            layer.putalpha(layer.getchannel('A').point(lambda a: round(a * opacity)))
        threshold = max(1, round(128 * opacity))
        b = visible(layer, threshold)
        if b is None:
            raise ValueError(f'Empty foreground: {ident}')
        xy = (round((box[0] + box[2] - b[0] - b[2]) / 2),
              round((box[1] + box[3] - b[1] - b[3]) / 2))
        rec = raster_centering_report(layer, box, origin_xy=xy, name=f'{self.scene}/{ident}',
                                     tolerance_px=.5, alpha_threshold=threshold)
        rec.update(scene=self.scene, component_id=ident, resolution_px=list(SIZE),
                   horizontal='center', vertical='center', opacity=opacity)
        if not rec['passed']:
            raise ValueError(rec)
        self.records.append(rec)
        self.layers[ident] = (layer, xy)
        self.image.alpha_composite(layer, xy)

    def text(self, text, box, size=34, color=INK, ident='text', opacity=1):
        self.center(text_layer(text, size, color), box, ident, opacity)
        if opacity > 0:
            self.records[-1].update(text=text, font_size_px=size)

    def multiline(self, lines, box, size=30, color=INK, ident='multiline'):
        pieces = [text_layer(x, size, color) for x in lines]
        boxes = [visible(x) for x in pieces]
        w = max(b[2] - b[0] for b in boxes)
        h = sum(b[3] - b[1] for b in boxes) + (len(lines) - 1) * 12
        layer = Image.new('RGBA', (w + 40, h + 40))
        y = 20
        for piece, b in zip(pieces, boxes):
            layer.alpha_composite(piece, (round((w - b[2] + b[0]) / 2) + 20 - b[0], y - b[1]))
            y += b[3] - b[1] + 12
        self.center(layer, box, ident)
        self.records[-1].update(text='\n'.join(lines), font_size_px=size, group='whole multiline glyph group')

    def fixed(self, layer, xy, ident, target, kind='motion', threshold=128):
        b = visible(layer, threshold)
        if b is None:
            raise ValueError(f'Empty moving foreground {ident}')
        box = [b[0] + xy[0], b[1] + xy[1], b[2] + xy[0], b[3] + xy[1]]
        contained = box[0] >= 24 and box[1] >= 24 and box[2] <= 1896 and box[3] <= 1056
        if not contained:
            raise ValueError(f'Clipped foreground {ident}: {box}')
        # The independent target is the mathematical group trajectory, while
        # the actual center comes from the rendered foreground's alpha mask.
        actual = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
        delta = [actual[0] - target[0], actual[1] - target[1]]
        passed = all(abs(z) <= .5 for z in delta)
        rec = dict(name=f'{self.scene}/{ident}', scene=self.scene, component_id=ident,
                   resolution_px=list(SIZE), horizontal='trajectory-x', vertical='trajectory-y',
                   visible_box_xyxy=box, target_center_px=list(target), visible_center_px=actual,
                   delta_x_px=delta[0], delta_y_px=delta[1], tolerance_px=.5,
                   passed=passed, contained=contained, alignment_kind=kind,
                   alpha_threshold=threshold, measurement='actual-raster-foreground')
        if not passed:
            raise ValueError(rec)
        self.records.append(rec)
        self.layers[ident] = (layer, xy)
        self.image.alpha_composite(layer, xy)


class Meerkat:
    def __init__(self):
        lib = json.loads((ROOT / 'catalogs/character-library-v1.json').read_text())
        self.char = next(x for x in lib['characters'] if x['id'] == 'meerkat')
        reg = json.loads((ROOT / 'assets/library/characters/meerkat/motions/v001/registration.json').read_text())
        self.poses = {p['id']: p for p in reg['frames']}
        if REG.exists():
            new = json.loads(REG.read_text())
            self.poses.update(new.get('poses', {}))
            if 'frames' in new:
                frames=new['frames']
                self.poses.update(frames if isinstance(frames,dict) else {p['id']:p for p in frames})
        self.receipts = {}

    @lru_cache(maxsize=32)
    def sprite(self, pose, height):
        row = self.char['neutral'] if pose == 'neutral' else self.poses[pose]
        path = ROOT / row['path']
        if sha(path) != row['sha256']:
            raise ValueError(f'Character hash mismatch: {path}')
        im = Image.open(path).convert('RGBA')
        scale = height / row['reference_height_px']
        return im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS), row, scale

    def draw(self, c, pose='neutral', height=230, foot=(960, 1044)):
        requested = pose
        pose={'look_up':'look_up_prepare','trace_row':'guide_up_extend',
              'invite_pair':'two_groups','reveal_half':'guide_up_extend'}.get(pose,pose)
        if pose != 'neutral' and pose not in self.poses:
            pose = 'neutral'
        im, row, scale = self.sprite(pose, height)
        xy = (round(foot[0] - row['anchor_px'][0] * scale), round(foot[1] - row['anchor_px'][1] * scale))
        b = visible(im, 8)
        absolute = [b[0] + xy[0], b[1] + xy[1], b[2] + xy[0], b[3] + xy[1]]
        if absolute[0] < 24 or absolute[1] < 24 or absolute[2] > 1896 or absolute[3] > 1056:
            raise ValueError(f'Character clipping: {absolute}')
        shadow = Image.new('RGBA', SIZE)
        ImageDraw.Draw(shadow).ellipse((foot[0] - height * .26, foot[1] - 5,
                                       foot[0] + height * .36, foot[1] + 8), fill=(70, 58, 42, 25))
        c.image.alpha_composite(shadow)
        c.image.alpha_composite(im, xy)
        rec = dict(pose=pose, requested_pose=requested, path=row['path'], sha256=row['sha256'],
                   body_reference_height_px=row['reference_height_px'], display_body_height_px=height,
                   scale=scale, anatomical_foot_target_px=list(foot), visible_box_xyxy=absolute,
                   horizontal='anatomical foot x', vertical='ground support y',
                   foot_delta_x_px=xy[0] + row['anchor_px'][0] * scale - foot[0],
                   foot_delta_y_px=xy[1] + row['anchor_px'][1] * scale - foot[1],
                   passed=True, mirrored=False, source_pixels_modified=False, not_centering_target=True)
        c.data['character'] = rec
        self.receipts[f'{pose}@{height}'] = rec


def header(c, subtitle='LIGHT-PEBBLE GROTTO · NUM-NUM NUMBERS'):
    c.panel((210, 26, 1710, 119), fill='#fffaf1', outline='#e5d7ba')
    c.text('TRIANGULAR NUMBERS', (240, 37, 1680, 82), 41, INK, 'title')
    c.text(subtitle, (240, 90, 1680, 110), 18, MUTED, 'subtitle')


def formula(c, n, committed=True, text=None, active=None):
    c.panel((340, 139, 1580, 250))
    text = text or f'{n} × {n+1} ÷ 2 = ' + (f'{n*(n+1)//2:,}' if committed else '?')
    if active and text.startswith(f'{n} ×'):
        parts=[(f'{n}',EDGE if active=='multiply' else INK),(' × ',INK),
               (f'{n+1}',TEAL if active=='multiply' else INK),
               (' ÷ 2',TEAL if active=='half' else INK),
               (' = '+(f'{n*(n+1)//2:,}' if committed else '?'),INK)]
        c.center(colored_text_layer(parts,65),(363,153,1557,233),'working-equation')
        c.records[-1].update(text=text,font_size_px=65,active_operation=active)
    else:
        c.text(text, (363, 153, 1557, 233), 65, INK, 'working-equation')
    c.data.update(n=n, value=n*(n+1)//2, operands=[n, n+1], divisor=2,
                  formula=text, result_committed=committed)


def result(c, n, top=265, committed=True):
    value = n * (n+1) // 2
    c.text(f'{value:,}' if committed else '?', (600, top, 1320, top+115), 108, INK, 'result')
    c.text(words(value) if committed else 'watch the formula work',
           (300, top+124, 1620, top+165), 31, MUTED, 'result-reading')


def dots(n, mode='triangle', pitch=None, radius=None, new_row=False, opacity_b=1):
    """Return an actual foreground dot layer plus independent point IDs.

    A(r,c): 0<=c<=r<n. Rotate A by 180 degrees to get B(r,c): r<c<=n.
    Every rectangle cell belongs to exactly one copy.
    """
    if not n:
        raise ValueError('Zero is an intentionally empty diagram, not an empty centering target')
    p = pitch or min(62, 435/max(1,n-1), 810/max(1,n))
    r = radius or min(17, p * .32)
    w, h = math.ceil(n*p+2*r+40), math.ceil((n-1)*p+2*r+40)
    layer = Image.new('RGBA', (w, h))
    d = ImageDraw.Draw(layer)
    points = []
    for row in range(n):
        for col in range(n+1):
            group = 'A' if col <= row else 'B'
            if mode == 'triangle' and group == 'B':
                continue
            if mode == 'copy' and group == 'A':
                continue
            x, y = 20+r+col*p, 20+r+row*p
            box = (round(x-r), round(y-r), round(x+r), round(y+r))
            if group == 'A':
                fill = TEAL if new_row and row == n-1 else AMBER
                d.ellipse(box, fill=fill, outline=EDGE if fill==AMBER else '#2c6667', width=max(1,round(r*.12)))
                if r >= 10:
                    d.ellipse((x-r*.47,y-r*.55,x-r*.06,y-r*.15),fill='#fff3c9')
            else:
                alpha = round(255*opacity_b)
                # Outline B gives a redundant shape distinction as well as color.
                d.ellipse(box, fill=(225,244,238,round(150*opacity_b)),
                          outline=(71,139,136,alpha), width=max(1,round(r*.23)))
            points.append(dict(id=f'{group}-{row}-{col}', group=group, row=row, col=col,
                               center_px=[x,y], radius_px=r))
    return layer, points, dict(pitch_px=p, radius_px=r, point_count=len(points), n=n, mode=mode,
                               A=sum(p['group']=='A' for p in points), B=sum(p['group']=='B' for p in points))


def diagram(c, n, mode='triangle', box=(460, 454, 1460, 815), new_row=False):
    # Local usable rectangle is chosen before rasterization. Small n uses large
    # pebbles; larger n still draws every point rather than a fictitious sample.
    max_h = box[3]-box[1]-12
    max_w = box[2]-box[0]-50
    pitch = min(62, max_h/max(1,n-.36), max_w/max(1,n+.64))
    layer, points, data = dots(n,mode,pitch=pitch,new_row=new_row)
    c.center(layer,box,'point-array')
    c.data['diagram']=data
    c.data['diagram'].update(expected_A=n*(n+1)//2,
                            expected_B=0 if mode=='triangle' else n*(n+1)//2,
                            all_points_drawn=True, individual_counting_expected=n<=10,
                            foreground_excludes_background=True)
    assert data['A'] == (0 if mode=='copy' else n*(n+1)//2)
    assert data['B'] == (0 if mode=='triangle' else n*(n+1)//2)
    if n>10:
        c.text('ALL DOTS SHOWN · FOLLOW THE ROWS AND FORMULA',
               (300, box[3]+9, 1620, box[3]+35), 19, MUTED, 'density-note')


def caption(c, text, y=938):
    c.panel((180, y-3, 1740, y+52), fill='#fff9eb', outline='#e3d4b8', radius=20)
    c.text(text,(202,y+6,1718,y+42),29,INK,'caption')


def make_stills(plate, meerkat):
    scenes=[]
    c=Canvas(plate,'01-intro');header(c,'BUILD · PAIR · TAKE HALF')
    c.text('A new row. A bigger triangle.',(220,156,1700,226),52,INK,'intro-line')
    c.text('Tₙ = n × (n + 1) ÷ 2',(340,266,1580,346),66,INK,'general-formula')
    diagram(c,4,box=(660,388,1260,603))
    meerkat.draw(c,'look_up',height=356,foot=(960,1044))
    c.text('0, 1, 3, 6, 10, 15, …',(380,624,1540,675),42,TEAL,'intro-sequence')
    c.data['direction']='中央で見上げる。視線→玉→式。頭だけを急に跳ねさせない。'
    scenes.append(c)

    c=Canvas(plate,'02-zero');header(c,'START WITH NOTHING IN THE TRIANGLE')
    formula(c,0);result(c,0)
    # Empty state is visibly bounded, and excluded from foreground centering.
    c.draw.rounded_rectangle((690,496,1230,738),radius=28,outline='#bca989',width=3)
    c.text('NO ROWS · NO DOTS',(720,575,1200,654),37,MUTED,'zero-label')
    c.data['diagram']=dict(n=0,point_count=0,intentionally_empty=True,reason='T0 is an empty set')
    meerkat.draw(c,'look_up',height=218)
    c.data['direction']='空の枠を両目で確認。玉を出さず0を読む。'
    scenes.append(c)

    c=Canvas(plate,'03-new-row');header(c,'REPLAY · THE NEXT ROW HAS FIVE NEW DOTS')
    formula(c,5,text='10 + 5 = 15');result(c,5)
    diagram(c,5,new_row=True,box=(650,460,1270,727))
    c.text('old rows: 10',(300,548,620,584),30,EDGE,'old-label')
    c.text('new row: +5',(1300,675,1650,712),30,TEAL,'new-label')
    meerkat.draw(c,'trace_row',height=235)
    c.data['direction']='新しい最下段5個へ視線を追わせる。片手を低く水平に案内し戻す。'
    scenes.append(c)

    c=Canvas(plate,'04-pair');header(c,'REPLAY · PAIR TWO MATCHING TRIANGLES')
    formula(c,5,committed=False);result(c,5,committed=False)
    diagram(c,5,mode='rectangle',box=(650,458,1270,754))
    c.text('A: filled dots',(220,510,610,551),29,EDGE,'A-legend')
    c.text('B: ring dots',(1320,665,1700,706),29,TEAL,'B-legend')
    c.text('5 rows × 6 dots = 30 dots',(510,779,1410,820),33,MUTED,'rectangle-dimensions')
    meerkat.draw(c,'invite_pair',height=215)
    c.data['direction']='もう一組を迎える両手の準備→組合せへ開く。A/Bは同形。答え15はまだ出さない。'
    scenes.append(c)

    c=Canvas(plate,'05-take-half');header(c,'REPLAY · TAKE ONE OF THE TWO EQUAL COPIES')
    formula(c,5);result(c,5)
    diagram(c,5,mode='triangle',box=(650,458,1270,754))
    c.text('KEEP A',(350,560,630,609),36,EDGE,'half-label')
    c.multiline(['30 dots ÷ 2','15 dots remain'],(1290,556,1710,670),31,TEAL,'half-explanation')
    meerkat.draw(c,'reveal_half',height=215)
    c.data['direction']='Bを一組として退避。玉の大きさを半分にしない。残ったAを片手で見せて笑顔。'
    scenes.append(c)

    c=Canvas(plate,'06-three-digits');header(c,'14 ROWS · EVERY DOT IS STILL HERE')
    formula(c,14);result(c,14)
    diagram(c,14,box=(580,451,1340,791))
    c.text('T₁₄',(310,583,560,651),58,TEAL,'term-index')
    meerkat.draw(c,'look_up',height=201)
    c.data['direction']='14段目へ短い頷き。100を越えても数値・読み・添字を同じ状態へ固定。'
    scenes.append(c)

    c=Canvas(plate,'07-four-digits');header(c,'REPLAY · A NEW ROW TAKES US PAST ONE THOUSAND')
    formula(c,45,text='990 + 45 = 1,035');result(c,45)
    diagram(c,45,new_row=True,box=(540,447,1380,790))
    c.text('45 × 46 ÷ 2 = 1,035',(440,840,1480,885),37,INK,'closed-form-check')
    meerkat.draw(c,'reveal_half',height=150,foot=(960,1050))
    c.data['direction']='990の後で次の45個が増える。桁上がりを見て軽く目を開き、体全体を跳ばさない。'
    scenes.append(c)

    c=Canvas(plate,'08-largest');header(c,'60 ROWS · THE FINAL TRIANGULAR NUMBER')
    formula(c,60);result(c,60)
    # Special maximum close-up prioritizes actual point separation. It is a
    # different scene scale; character source registration is unchanged.
    diagram(c,60,box=(490,447,1430,883))
    c.text('60 × 61 = 3,660   →   one equal half = 1,830',
           (170,945,1750,981),29,MUTED,'largest-check')
    meerkat.draw(c,'delighted',height=164,foot=(1637,1046))
    c.data['direction']='最大図では教材を寄りで見せ、ミーアキャットは右下の低い位置へ場面切替。読了後に完成を両手で提示。'
    scenes.append(c)

    c=Canvas(plate,'09-ending');header(c,'61 TERMS · FROM T₀ TO T₆₀')
    c.text('Tₙ = 1 + 2 + … + n = n × (n + 1) ÷ 2',
           (170,155,1750,229),52,INK,'ending-formula')
    c.text('Sum for n >= 1; T₀ = 0',(350,243,1570,270),22,MUTED,'ending-sum-domain')
    values=[f'{n*(n+1)//2:,}' for n in range(61)]
    c.panel((260,279,1660,700),fill='#fffaf1',outline='#ddcfb1')
    for row in range(7):
        vals=values[row*9:row*9+9]
        if not vals:continue
        c.text('   '.join(vals),(290,300+row*54,1630,342+row*54),29,INK,f'history-row-{row}')
    c.text('Each new row makes the next number.',(240,731,1680,784),39,TEAL,'ending-line')
    meerkat.draw(c,'delighted',height=231)
    c.data['direction']='中央へ戻り、全列から視聴者へ視線。短い挨拶→開眼の通常姿へ戻す。'
    scenes.append(c)
    return scenes


def motion_frame(plate, meerkat, t):
    """Silent 12-second proof of one n=5 assembly, not narration timing."""
    c=Canvas(plate,f'motion-{t:.3f}')
    if t<2: phase='BUILD A'; committed=False
    elif t<4: phase='MAKE A MATCHING COPY'; committed=False
    elif t<7: phase='PAIR: 5 ROWS × 6 DOTS'; committed=False
    elif t<9.5: phase='÷ 2: KEEP ONE EQUAL COPY'; committed=False
    else: phase='15'; committed=True
    header(c,phase);formula(c,5,committed=committed,active='multiply' if t<7 else 'half');result(c,5,committed=committed)
    p,r=63,18
    a,ap,adata=dots(5,'triangle',pitch=p,radius=r)
    b,bp,bdata=dots(5,'copy',pitch=p,radius=r)
    # Same local canvas for both copies: fixed rectangle placement is known
    # from the count grid, rather than fitting each copy independently.
    origin=(785,494)
    ab=visible(a); bb=visible(b)
    axy=origin
    if t<2:
        rows=max(1,min(5,1+int(t/2*5)))
        a,ap,adata=dots(rows,'triangle',pitch=p,radius=r)
        axy=origin
        ab=visible(a)
        target=(origin[0]+20+r+(rows-1)*p/2+.5,origin[1]+20+r+(rows-1)*p/2+.5)
        c.fixed(a,axy,'triangle-A',target,kind='row-growth')
    else:
        target=(origin[0]+20+r+2*p+.5,origin[1]+20+r+2*p+.5)
        c.fixed(a,axy,'triangle-A',target,kind='fixed-grid')
    show_b=t>=2 and t<9.5
    if show_b:
        if t<4:
            # The original A copy is reflected through the rectangle center
            # by a real continuous 180-degree rigid rotation. Dot identities
            # are preserved by the point map (r,c)->(4-r,5-c).
            u=min(1,(t-2)/2);angle=math.pi*u
            copy=Image.new('RGBA',(600,600));draw=ImageDraw.Draw(copy)
            rc=(2.5*p,2*p)
            rotated=[]
            for point in ap:
                x=(point['col']*p)-rc[0];y=(point['row']*p)-rc[1]
                qx=300+x*math.cos(angle)-y*math.sin(angle)
                qy=300+x*math.sin(angle)+y*math.cos(angle)
                draw.ellipse((round(qx-r),round(qy-r),round(qx+r),round(qy+r)),
                             fill='#e1f4ee',outline=TEAL,width=4)
                rotated.append([qx,qy])
            pivot=(origin[0]+20+r+370+rc[0],origin[1]+20+r+rc[1])
            xy=(round(pivot[0]-300),round(pivot[1]-300))
            # Pillow ellipse boxes include their last pixel; half-open raster
            # bounds therefore have a fixed +0.5px center offset, specified
            # here before any raster measurement (not a post-hoc correction).
            target=((min(q[0] for q in rotated)+max(q[0] for q in rotated))/2+xy[0]+.5,
                    (min(q[1] for q in rotated)+max(q[1] for q in rotated))/2+xy[1]+.5)
            c.fixed(copy,xy,'triangle-B-rotating',target,kind='rigid-rotation-copy')
            c.data['rotation_radians']=angle
        else:
            if t<7:
                u=min(1,(t-4)/2);u=u*u*(3-2*u)
                shift=round(370*(1-u))
            else:
                u=min(1,(t-7)/2.5);u=u*u*(3-2*u)
                shift=round(370*u)
            xy=(origin[0]+shift,origin[1])
            target=(origin[0]+shift+20+r+3*p+.5,origin[1]+20+r+2*p+.5)
            c.fixed(b,xy,'triangle-B-translating',target,kind='copy-pair-or-half-removal')
            c.data['B_shift_px']=shift
    c.text('A: filled dots',(250,572,660,612),30,EDGE,'motion-A-label')
    c.text('B: ring dots',(1280,799,1730,841),30,TEAL,'motion-B-label')
    meerkat.draw(c,'invite_pair' if t<7 else 'reveal_half',height=205)
    visible_a=len(ap)
    c.data.update(n=5,A=visible_a,B=15 if show_b else 0,expected_full_A=15,
                  observed_visible_A=visible_a,build_visible_count=visible_a,
                  visible_rows=rows if t<2 else 5,answer=15,result_committed=committed,
                  study_only=True,narration_sync_measured=False,original_point_radius_px=r,
                  half_operation='remove one entire equal copy; never shrink dots')
    return c


def count_raster_components(layer):
    """Four-neighbor connected components, independent of the point list."""
    im=layer.getchannel('A').point(lambda a:1 if a>=128 else 0)
    w,h=im.size
    pixels=im.tobytes();seen=bytearray(len(pixels));count=0
    for i,v in enumerate(pixels):
        if not v or seen[i]:continue
        count+=1;stack=[i];seen[i]=1
        while stack:
            j=stack.pop();x=j%w
            for k in ((j-1 if x else -1),(j+1 if x<w-1 else -1),j-w,j+w):
                if 0<=k<len(pixels) and pixels[k] and not seen[k]:
                    seen[k]=1;stack.append(k)
    return count


def raster_count_verification():
    observations=[]
    for n in range(1,61):
        p=min(62,435/max(1,n-.36),810/max(1,n+.64))
        for mode in ('triangle','rectangle'):
            layer,points,data=dots(n,mode,pitch=p)
            measured=count_raster_components(layer)
            expected=sum(range(1,n+1))*(2 if mode=='rectangle' else 1)
            row=dict(n=n,mode=mode,expected_count=expected,connected_components=measured,
                     passed=measured==expected,threshold=128,connectivity=4,
                     point_diameter_px=data['radius_px']*2,pitch_px=p,
                     source='actual raster foreground alpha, independent of point-ID list')
            if not row['passed']:raise ValueError(row)
            observations.append(row)
    return observations


def all_state_typography(plate):
    recs=[]
    for n in range(61):
        c=Canvas(plate,f'all-state-{n:02d}')
        formula(c,n);result(c,n)
        recs.extend(c.records)
    # General form and longest multiline explanation use their own intended
    # groups and sizes rather than falsely treating individual lines as centered.
    c=Canvas(plate,'multiline-stress')
    c.multiline(['one thousand eight hundred thirty', '60 rows · 61 terms including zero'],
                (240,300,1680,470),38,INK,'longest-multiline-group')
    recs.extend(c.records)
    return recs


def run(skip_motion=False,qa_only=False):
    OUT.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    if not BG.exists():raise FileNotFoundError(f'Generated clean plate not yet present: {BG}')
    source=Image.open(BG).convert('RGBA')
    plate=ImageOps.fit(source,SIZE,method=Image.Resampling.LANCZOS)
    meerkat=Meerkat()
    scenes=make_stills(plate,meerkat)
    if not qa_only:
        for c in scenes:
            c.image.convert('RGB').save(OUT/f'{c.scene}.png')
    sheet=Image.new('RGB',(1920,1215),'#f2ecdf')
    d=ImageDraw.Draw(sheet)
    for i,c in enumerate(scenes):
        x,y=(i%3)*640,(i//3)*405
        sheet.paste(c.image.convert('RGB').resize((624,351),Image.Resampling.LANCZOS),(x+8,y+8))
        d.text((x+18,y+367),c.scene,font=font(20),fill=INK)
    if not qa_only:
        sheet.save(OUT/'storyboard.png');sheet.save(OUT/'storyboard-preview.jpg',quality=93)
    records=[r for c in scenes for r in c.records]
    records+=all_state_typography(plate)
    motion_records=[]
    checkpoints=[]
    # Entry, midpoint and exit of rotation, pairing, removal and commitment.
    for t in [0,1,1.99,2,3,3.99,4,5,6,6.99,7,8.25,9.49,9.5,10.5,11.9]:
        c=motion_frame(plate,meerkat,t)
        c.image.convert('RGB').save(QA/f'motion-{t:05.2f}s.png')
        checkpoints.append(dict(time_s=t,**c.data))
        motion_records+=c.records
    if not skip_motion and not qa_only:
        frames=OUT/'motion-frames';frames.mkdir(exist_ok=True)
        for frame in range(180):
            c=motion_frame(plate,meerkat,frame/15)
            c.image.convert('RGB').save(frames/f'{frame:04d}.png')
        subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y','-framerate','15',
                        '-i',str(frames/'%04d.png'),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p',
                        '-movflags','+faststart',str(OUT/'working-equation.mp4')],check=True)
        # Small GIF is an inline motion preview; the 1080p MP4 is the primary study.
        subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(OUT/'working-equation.mp4'),
                        '-filter_complex','fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse',
                        str(OUT/'working-equation.gif')],check=True)
        for path in frames.glob('*.png'):path.unlink()
        frames.rmdir()
    all_records=records+motion_records
    dot_counts=raster_count_verification()
    (QA/'dot-count-verification.json').write_text(json.dumps(dict(status='pass',
        scope='all n=1..60, both one-copy and paired rectangle, independent alpha connected components',
        intentionally_empty_zero=dict(expected_count=0,drawn_count=0),observations=dot_counts),
        ensure_ascii=False,indent=2)+'\n')
    report=dict(status='pass' if all(r['passed'] for r in all_records) else 'fail',
                scope='preproduction raster stills and silent n=5 motion study only; no final episode or audio QA',
                output_resolution_px=list(SIZE),alpha_threshold=128,tolerance_px=.5,
                static_observations=len(records),motion_checkpoint_observations=len(motion_records),
                full_n_range=list(range(61)),shortest_value=0,longest_value=1830,
                digit_boundaries=[dict(before=6,after=10),dict(before=91,after=105),dict(before=990,after=1035)],
                backgrounds=dict(path=str(BG.relative_to(ROOT)),sha256=sha(BG),source_size_px=list(source.size),
                                 output_size_px=list(SIZE),resize_factor=max(SIZE[0]/source.width,SIZE[1]/source.height)),
                characters=meerkat.receipts,scenes=[dict(scene=c.scene,**c.data) for c in scenes],
                observations=all_records,motion_checkpoints=checkpoints,
                dot_count_verification='design/triangular-counting-v1/qa/dot-count-verification.json',
                fades=dict(applied=False,reason='Study uses rigid motion and committed text switches; no fading glyph transition'),
                exclusions=['No adopted narration generated or measured','No finished count episode',
                            'No assertion of finished MP4 animation adequacy','No human full-episode playback'])
    (QA/'mockup-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (QA/'mockup-verification.txt').write_text(
        f"三角数モック配置検査: {report['status']}\n1920×1080 / 字形・図の実描画前景 / 両軸各0.5px以内。\n"
        f"静止・全n状態 {len(records)}件、動作チェックポイント {len(motion_records)}件。\n"
        "0は意図した空の個数で、空の図を中央揃え合格にしていない。\n"
        "Aは塗り玉、Bは輪玉。n×(n+1)の各セルをA/Bへ一意に割当。÷2はB全体の退避。\n"
        "全61項の式・主結果・英語読み、最長複数行、1→2→3→4桁、最大n60の実点描画を確認。\n"
        "図の個別数唱はn10まで。n11以降も全点描画するが辺・行数・式を読み取る表示。\n"
        "動作サンプルは回転・組合せ・半分退避の入口／中間／出口を実マスクで測定。\n"
        "キャラクターは登録身体高と足支点による描画。移動・接地を中央揃え判定に置換しない。\n"
        "無音12秒の動作研究は本編音声尺・同期・完成MP4の品質検査ではない。\n")
    print(json.dumps({k:report[k] for k in ['status','static_observations','motion_checkpoint_observations']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--skip-motion',action='store_true')
    parser.add_argument('--qa-only',action='store_true',help='Regenerate QA evidence without touching mockup media')
    args=parser.parse_args();run(args.skip_motion,args.qa_only)
