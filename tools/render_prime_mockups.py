"""Compose the prime-counting preproduction stills; does not generate a video.

The generated museum plate stays free of labels and characters. Educational
labels, exact tile quantities and the registered kangaroo are separate layers.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report


ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
BACKGROUND = ROOT / 'assets/library/worlds/sunlit-mosaic-museum/backgrounds/v001/sunlit-mosaic-museum-background.png'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
CATALOG = ROOT / 'catalogs/character-library-v1.json'
OUT = ROOT / 'design/prime-counting-v1/mockups'
QA = ROOT / 'design/prime-counting-v1/qa'
INK = '#423b32'
TEAL = '#246c65'
MUTED = '#817669'
TERRACOTTA = '#a95c43'
CREAM = '#fffaf0'
LINE = '#d5c5ad'
PALE = '#e4efe6'
PEACH = '#f3e1d2'
PRIMES = tuple(n for n in range(2, 1000) if all(n % k for k in range(2, math.isqrt(n) + 1)))
ONES = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
        'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
        'seventeen', 'eighteen', 'nineteen')
TENS = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def words(n):
    if not isinstance(n, int) or not 0 <= n <= 999:
        raise ValueError('Expected a whole number from zero through 999')
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ('-' + ONES[n % 10] if n % 10 else '')
    return ONES[n // 100] + ' hundred' + (' ' + words(n % 100) if n % 100 else '')


@lru_cache(maxsize=64)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def box(draw, bounds, fill=CREAM, outline=LINE, radius=4, width=2):
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=width)


def glyph_layer(text, size, color):
    """Render with generous margins, then center the measured visible glyphs."""
    face = font(size)
    b = face.getbbox(text)
    layer = Image.new('RGBA', (b[2] - b[0] + 80, b[3] - b[1] + 80))
    ImageDraw.Draw(layer).text((40 - b[0], 40 - b[1]), text, font=face, fill=color)
    visible = layer.getchannel('A').point(lambda a: 255 if a >= 128 else 0).getbbox()
    if not visible:
        raise ValueError('Empty label')
    padded = (visible[0] - 4, visible[1] - 4, visible[2] + 4, visible[3] + 4)
    return layer.crop(padded)


class Canvas:
    def __init__(self, background, name):
        self.image = background.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.name = name
        self.records = []
        self.diagrams = []

    def centered(self, text, field, size, color=INK, ident=None):
        layer = glyph_layer(text, size, color)
        b = layer.getchannel('A').point(lambda a: 255 if a >= 128 else 0).getbbox()
        cx, cy = (field[0] + field[2]) / 2, (field[1] + field[3]) / 2
        xy = (round(cx - (b[0] + b[2]) / 2), round(cy - (b[1] + b[3]) / 2))
        report = raster_centering_report(layer, field, origin_xy=xy,
                                         name=f'{self.name}/{ident or text}', tolerance_px=.5)
        report.update(text=text, font_size_px=size, horizontal='center', vertical='center',
                      scene=self.name, resolution_px=list(SIZE))
        if not report['passed']:
            raise ValueError(json.dumps(report))
        self.records.append(report)
        self.image.alpha_composite(layer, xy)
        return report

    def left(self, text, xy, size, color=INK):
        # These labels intentionally align to the exhibit's left baseline.
        self.draw.text(xy, text, font=font(size), fill=color, anchor='lt')

    def tiles(self, rows, columns, field, *, color=TEAL, size=62, gap=12,
              ident='tiles', opacity=1):
        width, height = columns * size + (columns - 1) * gap, rows * size + (rows - 1) * gap
        tile = Image.new('RGBA', (width + 16, height + 16))
        d = ImageDraw.Draw(tile)
        for r in range(rows):
            for col in range(columns):
                x, y = 8 + col * (size + gap), 8 + r * (size + gap)
                box(d, (x, y, x + size - 1, y + size - 1), color, color, radius=5, width=1)
                d.line((x + 7, y + 7, x + size - 9, y + 7), fill='#ffffff', width=1)
        b = tile.getchannel('A').getbbox()
        xy = (round((field[0] + field[2] - b[0] - b[2]) / 2),
              round((field[1] + field[3] - b[1] - b[3]) / 2))
        if opacity:
            tile.putalpha(tile.getchannel('A').point(lambda a: round(a * opacity)))
            report = raster_centering_report(tile, field, origin_xy=xy, name=f'{self.name}/{ident}',
                                             tolerance_px=.5, alpha_threshold=max(1, round(128 * opacity)))
            report.update(scene=self.name, resolution_px=list(SIZE), opacity=opacity,
                          horizontal='center', vertical='center')
            if not report['passed']:
                raise ValueError(report)
            self.records.append(report)
            self.image.alpha_composite(tile, xy)
        self.diagrams.append({'id':ident, 'rows':rows, 'columns':columns,
                              'quantity':rows * columns, 'opacity':opacity,
                              'intentional_absence':opacity == 0})


class Kangaroo:
    def __init__(self):
        c = next(c for c in json.loads(CATALOG.read_text())['characters'] if c['id'] == 'kangaroo')
        n = c['neutral']
        self.path = ROOT / n['path']
        if sha(self.path) != n['sha256']:
            raise ValueError('Canonical kangaroo SHA-256 mismatch')
        self.scale = 430 / n['reference_height_px']
        self.root = (1625, 982)
        with Image.open(self.path) as source:
            if source.mode != 'RGBA':
                raise ValueError('Kangaroo must retain RGBA')
            self.sprite = source.resize((round(source.width * self.scale), round(source.height * self.scale)), Image.Resampling.LANCZOS)
        self.position = tuple(round(root - anchor * self.scale) for root, anchor in zip(self.root, n['anchor_px']))
        b = self.sprite.getchannel('A').point(lambda a:255 if a >= 8 else 0).getbbox()
        self.bounds = [b[0] + self.position[0], b[1] + self.position[1], b[2] + self.position[0], b[3] + self.position[1]]
        if not (self.bounds[0] > 1400 and self.bounds[2] < 1900 and self.bounds[3] < 1040):
            raise ValueError(f'Kangaroo clearance failed: {self.bounds}')

    def draw(self, image):
        shadow = Image.new('RGBA', SIZE)
        ImageDraw.Draw(shadow).ellipse((self.root[0]-92, self.root[1]-9, self.root[0]+135, self.root[1]+14), fill=(77,61,44,24))
        image.alpha_composite(shadow)
        image.alpha_composite(self.sprite, self.position)

    def receipt(self):
        return {'path':self.path.relative_to(ROOT).as_posix(), 'sha256':sha(self.path),
                'pose':'neutral', 'body_height_px':430, 'foot_anchor_px':list(self.root),
                'source_scale':self.scale, 'visible_bbox_px':self.bounds,
                'source_pixels_modified':False, 'mirrored':False,
                'policy':'Registered body scale and foot anchor; original full canvas and tail retained.'}


def header(c, subtitle='THE SUNLIT MOSAIC MUSEUM'):
    c.left('PRIME NUMBERS', (105, 79), 76)
    c.left(subtitle, (110, 174), 26, TEAL)
    c.centered('Num-Num Numbers', (1450, 72, 1875, 125), 30, TEAL, 'series')


def exhibit(c):
    # A broad flat museum mount, with a restrained double keyline rather than a dashboard card.
    box(c.draw, (89, 251, 1352, 1004), '#bba98f', '#bba98f', radius=5)
    box(c.draw, (82, 244, 1345, 997), CREAM, '#bba98f', radius=5, width=3)
    c.draw.rectangle((98, 260, 1329, 981), outline='#e8dac5', width=2)


def factors(c, n):
    c.centered('POSITIVE FACTORS', (170, 708, 1240, 748), 23, MUTED, 'factor-caption')
    for v, x in ((1, 600), (n, 825)):
        bounds = (x-79, 766, x+79, 840)
        box(c.draw, bounds, PALE, '#b3c7ba', radius=7)
        c.centered(str(v), (x-67, 774, x+67, 832), 41, TEAL, f'factor-{v}')
    c.centered('Exactly two: 1 and itself', (170, 857, 1240, 903), 31, TEAL, 'factor-rule')


def count(c, n, label=None):
    exhibit(c)
    i = PRIMES.index(n)
    c.centered(label or f'PRIME {i+1} OF 168', (170, 280, 1240, 327), 27, MUTED, 'count-progress')
    c.centered(str(n), (170, 346, 1240, 590), 285, INK, 'main-number')
    c.centered(words(n), (135, 625, 1292, 683), 42, TEAL, 'reading')
    factors(c, n)
    if n == 2:
        c.centered('2 is the only even prime.', (170, 923, 1240, 965), 30, TERRACOTTA, 'only-even')
    elif n == 997:
        c.centered('All 168 primes below 1000', (170, 923, 1240, 965), 30, TERRACOTTA, 'last-number')
    else:
        before = PRIMES[max(0, i-2):i]
        after = PRIMES[i+1:i+3]
        s = '   ·   '.join(str(p) for p in (*before, n, *after))
        c.centered(s, (170, 923, 1240, 965), 28, MUTED, 'prime-sequence')


def opening(c):
    c.left('Let’s count the primes', (110, 290), 64, TEAL)
    c.left('2–997', (105, 389), 132)
    c.left('168 discoveries, one at a time', (110, 562), 37, MUTED)
    for n, x in zip((2,3,5,7,11),(215,440,665,890,1115)):
        # Discrete prime tiles are exhibits, not a proportional number line.
        box(c.draw, (x-82, 686, x+82, 856), PALE, '#b3c7ba', radius=9, width=3)
        c.centered(str(n), (x-68, 700, x+68, 843), 82, TEAL, f'opening-prime-{n}')
        c.draw.rectangle((x-94, 880, x+94, 887), fill='#b8a489')


def comparison(c, opacity=1):
    # Two separate shallow exhibits let the tile arrangements lead this shot.
    c.centered('EXACTLY TWO POSITIVE FACTORS', (105, 273, 1325, 330), 42, TEAL, 'comparison-title')
    for x, title, prime in ((416, '5  ·  PRIME', True), (1015, '6  ·  NOT PRIME', False)):
        c.centered(title, (x-270, 367, x+270, 423), 40, TEAL if prime else TERRACOTTA, f'comparison-{prime}')
        bounds=(x-285,451,x+285,759)
        box(c.draw,bounds,'#d9bd91','#ae8b62',radius=8,width=3)
        box(c.draw,(bounds[0]+15,bounds[1]+15,bounds[2]-15,bounds[3]-15),'#f7ebd6','#bc9d74',radius=3,width=2)
        c.draw.line((x-280,766,x+280,766),fill='#bda482',width=5)
    c.tiles(1, 5, (158, 475, 674, 735), size=81, gap=17, opacity=opacity, ident='five-1x5')
    c.tiles(2, 3, (757, 475, 1273, 735), color=TERRACOTTA, size=81, gap=17, opacity=opacity, ident='six-2x3')
    for x in (416,1015):
        box(c.draw,(x-264,815,x+264,994),CREAM,LINE,radius=3)
    c.centered('1 × 5 = 5', (195, 831, 637, 882), 43, TEAL, 'five-equation')
    c.centered('2 × 3 = 6', (794, 831, 1236, 882), 43, TERRACOTTA, 'six-equation')
    c.centered('Factors: 1, 5', (155, 934, 677, 975), 30, TEAL, 'five-factors')
    c.centered('Factors: 1, 2, 3, 6', (750, 934, 1280, 975), 30, TERRACOTTA, 'six-factors')


def rotation(c):
    # Two orientations use the same factor pair; they are not new factors.
    c.centered('TURN THE ROW. KEEP THE SAME FACTORS.', (90, 271, 1350, 330), 39, TEAL, 'rotation-title')
    c.tiles(1,5,(125,429,740,759),size=70,gap=16,ident='horizontal-five')
    c.tiles(5,1,(905,366,1240,850),size=70,gap=16,ident='vertical-five')
    for x in (432,1072):
        box(c.draw,(x-160,867,x+160,950),CREAM,LINE,radius=3)
    c.centered('1 × 5', (159, 879, 705, 941), 49, TEAL, 'rotation-horizontal-equation')
    c.centered('5 × 1', (843, 879, 1300, 941), 49, TEAL, 'rotation-vertical-equation')
    box(c.draw,(120,960,1310,1029),CREAM,LINE,radius=3)
    c.centered('The positive factors are still 1 and 5.', (120, 966, 1310, 1015), 33, MUTED, 'rotation-rule')


def one(c):
    exhibit(c)
    c.centered('WHY NOT ONE?', (170, 285, 1240, 335), 35, TERRACOTTA, 'one-heading')
    c.centered('1', (220, 397, 680, 677), 285, INK, 'one-number')
    c.tiles(1, 1, (831, 444, 1136, 634), size=104, color=TERRACOTTA, ident='one-tile')
    c.centered('1 × 1', (800, 685, 1165, 744), 42, TERRACOTTA, 'one-equation')
    c.centered('Only one positive factor: 1', (150, 806, 1280, 857), 36, TERRACOTTA, 'one-factor')
    c.centered('1 is not prime.', (150, 918, 1280, 964), 34, TEAL, 'one-rule')


def nine(c):
    exhibit(c)
    c.centered('NOT EVERY ODD NUMBER IS PRIME', (135, 285, 1290, 337), 34, TERRACOTTA, 'nine-heading')
    c.centered('9', (220, 396, 680, 681), 285, INK, 'nine-number')
    c.tiles(3, 3, (789, 399, 1215, 721), size=68, gap=13, color=TERRACOTTA, ident='nine-3x3')
    c.centered('3 × 3 = 9', (779, 744, 1225, 801), 42, TERRACOTTA, 'nine-equation')
    c.centered('Positive factors: 1, 3, 9', (150, 842, 1280, 886), 33, MUTED, 'nine-factors')
    c.centered('9 is odd, but it is not prime.', (150, 918, 1280, 965), 32, TEAL, 'nine-rule')


def bridge(c):
    exhibit(c)
    c.centered('PRIMES DO NOT HAVE A FIXED STEP', (130, 285, 1300, 335), 34, TEAL, 'bridge-title')
    for n,x in zip((97,98,99,100,101),(245,478,711,944,1177)):
        prime=n in (97,101)
        c.centered(str(n), (x-111, 435, x+111, 583), 94, TEAL if prime else MUTED, f'bridge-{n}')
        c.centered('PRIME' if prime else 'NOT PRIME', (x-109, 644, x+109, 689), 24,
                   TEAL if prime else TERRACOTTA, f'bridge-status-{n}')
    c.centered('97 + 4 = 101', (150, 744, 1280, 801), 46, TEAL, 'bridge-gap')
    for text,x in (('98 = 2 × 49',322),('99 = 9 × 11',714),('100 = 10 × 10',1106)):
        c.centered(text, (x-189, 837, x+189, 880), 26, TERRACOTTA, f'bridge-{text}')
    c.centered('Count 97, then 101. The gaps can change.', (130, 916, 1300, 965), 31, TEAL, 'bridge-rule')


def finale(c):
    # The finished horizontal gallery mosaic replaces the normal number mount.
    c.centered('168 PRIMES BELOW 1000', (105, 280, 1325, 349), 55, TEAL, 'finale-heading')
    c.centered('2–997', (195, 387, 1235, 533), 119, INK, 'finale-range')
    box(c.draw,(93,567,1338,886),'#e6cda6','#ae8b62',radius=4,width=3)
    box(c.draw,(108,582,1323,871),'#f6ebd6','#bc9d74',radius=2,width=2)
    c.tiles(6,28,(135,596,1296,857),size=32,gap=8,ident='168-discoveries')
    c.draw.rectangle((78,896,1355,910),fill='#b89b73')
    box(c.draw,(165,930,1265,1000),CREAM,LINE,radius=3)
    c.centered('One tile for each prime we counted.', (120, 941, 1310, 984), 30, MUTED, 'finale-map')


def longest_value():
    return max(PRIMES, key=lambda n:glyph_layer(words(n),42,TEAL).width)


def build(background, kangaroo, name, mode, value=None, opacity=1):
    c = Canvas(background, name)
    kangaroo.draw(c.image)
    header(c, 'TEACHING EXAMPLE · THE MOSAIC MUSEUM' if mode in ('comparison','rotation','one','nine','bridge')
           else 'THE SUNLIT MOSAIC MUSEUM')
    if mode == 'opening': opening(c)
    elif mode == 'count': count(c,value)
    elif mode == 'comparison': comparison(c,opacity)
    elif mode == 'rotation': rotation(c)
    elif mode == 'one': one(c)
    elif mode == 'nine': nine(c)
    elif mode == 'bridge': bridge(c)
    elif mode == 'finale': finale(c)
    else: raise ValueError(mode)
    return c


def overview(out):
    """A small four-scene review image, in addition to the complete storyboard."""
    image=Image.new('RGB',(1152,648),CREAM)
    for i,name in enumerate(('01-opening.png','03-five-and-six.png','key-visual.png','10-finale.png')):
        with Image.open(out/name) as source:
            image.paste(source.convert('RGB').resize((576,324),Image.Resampling.LANCZOS),
                        ((i%2)*576,(i//2)*324))
    draw=ImageDraw.Draw(image)
    draw.line((576,0,576,648),fill=CREAM,width=4)
    draw.line((0,324,1152,324),fill=CREAM,width=4)
    image.save(out/'overview.jpg',quality=95)


def run(out=OUT, qa=QA):
    out.mkdir(parents=True, exist_ok=True)
    qa.mkdir(parents=True, exist_ok=True)
    with Image.open(BACKGROUND) as source:
        background = ImageOps.fit(source.convert('RGBA'),SIZE,Image.Resampling.LANCZOS)
    kangaroo = Kangaroo()
    longest = longest_value()
    shots = [
        ('01-opening.png','opening',None,'01  Welcome to the mosaic museum'),
        ('03-five-and-six.png','comparison',None,'02  Prime 5 / composite 6'),
        ('03b-turning-a-row.png','rotation',None,'03  A rotation adds no new factors'),
        ('04-one-is-not-prime.png','one',None,'04  One has only one positive factor'),
        ('02-only-even-prime.png','count',2,'05  Two is the only even prime'),
        ('05-nine-is-not-prime.png','nine',None,'06  Nine is odd, but not prime'),
        ('06-97-to-101.png','bridge',None,'07  Prime gaps can change'),
        ('07-three-digit-101.png','count',101,'08  Three-digit prime: 101'),
        ('08-longest-reading.png','count',longest,f'09  Longest rendered reading: {longest}'),
        ('09-last-prime-997.png','count',997,'10  Last prime below 1000: 997'),
        ('10-finale.png','finale',None,'11  168 prime discoveries'),
    ]
    reports=[]
    images=[]
    for filename,mode,value,caption in shots:
        c = build(background,kangaroo,filename,mode,value)
        path=out/filename
        c.image.convert('RGB').save(path)
        reports.append({'filename':filename,'mode':mode,'value':value,'caption':caption,
                        'sha256':sha(path),'components':c.records,'diagrams':c.diagrams})
        images.append((c.image.convert('RGB'),caption))
    # A mid fade is explicitly a diagram-only fade: labels and all other geometry stay fixed.
    for opacity in (0,.5,1):
        filename=f'transition-tiles-{round(opacity*100):03d}.png'
        c=build(background,kangaroo,filename,'comparison',opacity=opacity)
        c.image.convert('RGB').save(out/filename)
        reports.append({'filename':filename,'mode':'comparison-diagram-transition','opacity':opacity,
                        'sha256':sha(out/filename),'components':c.records,'diagrams':c.diagrams})
    # Every prime at the same number/word font sizes, plus all factor labels and progress fields.
    all_values=[]
    for n in PRIMES:
        c=build(background,kangaroo,f'validation-{n}','count',n)
        all_values.append({'value':n,'words':words(n),'passed':all(r['passed'] for r in c.records),
                           'components':c.records})
    # The clean plate completes the review sheet without implying an extra video scene.
    images.append((background.convert('RGB'),'Background plate  ·  no labels or character'))
    cols=2; cellw=960; cellh=590
    rows=math.ceil(len(images)/cols)
    sheet=Image.new('RGB',(cols*cellw,rows*cellh),'#f4ecdf')
    sd=ImageDraw.Draw(sheet)
    for i,(im,caption) in enumerate(images):
        x,y=(i%cols)*cellw,(i//cols)*cellh
        sheet.paste(im.resize((944,531),Image.Resampling.LANCZOS),(x+8,y+8))
        sd.text((x+20,y+552),caption,font=font(23),fill=INK,anchor='lt')
    sheet.save(out/'storyboard.png')
    # A second compact overview is convenient in review conversations.
    sheet.resize((1152,rows*354),Image.Resampling.LANCZOS).save(out/'storyboard-preview.jpg',quality=93)
    (out/'07-three-digit-101.png').replace(out/'key-visual.png')
    # Preserve the numbered board path as well as the conventional key visual.
    with Image.open(out/'key-visual.png') as im: im.save(out/'07-three-digit-101.png')
    overview(out)
    data={'schema_version':1,'kind':'prime-preproduction-mockups','status':'draft-for-user-review',
          'video_created':False,'resolution_px':list(SIZE),'scope':'Static PNG stills and diagram-only fade samples; no continuous video or audio QA.',
          'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in (BACKGROUND,FONT,CATALOG)],
          'character':kangaroo.receipt(),'prime_range':[2,997],'prime_count':len(PRIMES),
          'primes':list(PRIMES),'longest_rendered_reading_value':longest,
          'number_font_px':285,'reading_font_px':42,'shots':reports,
          'alignment':{'measurement':'Actual raster alpha>=128, excluding parent frame/shadows; fade uses proportional alpha threshold.',
                       'tolerance_px':.5,'all_prime_values':all_values,
                       'passed':all(v['passed'] for v in all_values) and all(r['passed'] for s in reports for r in s['components'])}}
    (qa/'mockup-verification.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (qa/'mockup-verification.txt').write_text(
        'Prime preproduction mockup checks\n'
        f'{len(PRIMES)} primes from 2 to 997; same 285px number / 42px reading sizes.\n'
        f'Longest rendered reading: {longest} ({words(longest)}).\n'
        'Both horizontal and vertical visible-ink centers: tolerance 0.5px.\n'
        'All count states plus teaching/opening/finale and 0/50/100% diagram fades measured.\n'
        'Kangaroo source SHA-256 verified; fixed 430px body height and registered foot anchor; full tail retained.\n'
        'No audio or video was generated or tested. Static composition checks do not validate continuous animation.\n'
        f'PASS: {data["alignment"]["passed"]}\n')
    print(json.dumps({'output':str(out),'qa':str(qa),'longest_reading':longest,'alignment_passed':data['alignment']['passed']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,default=OUT)
    parser.add_argument('--qa-dir',type=Path,default=QA)
    args=parser.parse_args()
    run(args.out_dir,args.qa_dir)
