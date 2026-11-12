"""Square-number preproduction stills and a silent working-equation study.

All mathematical marks are deterministic raster layers.  These deliverables are
planning evidence, not a finished episode or a completed production audio gate.
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

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

try:
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/square-counting-v1'
OUT = DESIGN / 'mockups'
QA = DESIGN / 'qa'
BG = DESIGN / 'generation-batches/lake-square-20261112-a/source/frozen-lake-clean-plate.png'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE = (1920, 1080)
INK, TEAL, BLUE, GOLD, MUTED = '#29475b', '#237e83', '#4c88b4', '#cb8450', '#6b8190'
ICE, PALE, WARM = '#f5fbfa', '#dcf0ee', '#fff3da'
GRID_BOX = (720, 402, 1200, 882)


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
    return layer.getchannel('A').point(lambda v: 255 if v >= threshold else 0).getbbox()


def text_layer(text, size, color=INK):
    f = font(size)
    b = f.getbbox(text)
    layer = Image.new('RGBA', (b[2] - b[0] + 40, b[3] - b[1] + 40))
    ImageDraw.Draw(layer).text((20-b[0], 20-b[1]), text, font=f, fill=color)
    return layer


class Canvas:
    def __init__(self, plate, scene):
        self.image = plate.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.scene = scene
        self.records, self.absent = [], []
        self.data = {}
        self.foreground = {}

    def center(self, layer, box, ident, opacity=1):
        if not opacity:
            self.absent.append({'id': ident, 'reason': 'intentionally hidden before result commitment'})
            return
        if opacity != 1:
            layer = layer.copy()
            layer.putalpha(layer.getchannel('A').point(lambda a: round(a * opacity)))
        threshold = max(1, round(128 * opacity))
        b = visible(layer, threshold)
        if not b:
            raise ValueError(f'Empty component {ident}')
        xy = (round((box[0]+box[2]-b[0]-b[2])/2), round((box[1]+box[3]-b[1]-b[3])/2))
        report = raster_centering_report(layer, box, origin_xy=xy, name=f'{self.scene}/{ident}',
                                         tolerance_px=.5, alpha_threshold=threshold)
        report.update(horizontal='center', vertical='center', scene=self.scene, resolution_px=list(SIZE),
                      component_id=ident, opacity=opacity)
        if not report['passed']:
            raise ValueError(report)
        self.records.append(report)
        self.foreground[ident]=(layer,xy,threshold)
        self.image.alpha_composite(layer, xy)

    def text(self, text, box, size=34, color=INK, ident=None, opacity=1):
        self.center(text_layer(text, size, color), box, ident or text, opacity)
        if opacity:
            self.records[-1].update(text=text, font_size_px=size)

    def panel(self, box, fill=ICE, outline='#bdd3d5', radius=28, width=2):
        checks=self.data.setdefault('opaque_panel_occlusion_checks',[])
        for rec in self.records:
            a=rec['visible_box_xyxy']
            overlap=max(a[0],box[0])<min(a[2],box[2]) and max(a[1],box[1])<min(a[3],box[3])
            checks.append({'foreground_id':rec['component_id'],'later_panel_box':list(box),'occluded':overlap})
            if overlap:
                raise ValueError(f'Later opaque panel covers existing foreground: {rec["name"]}: {box}')
        self.draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

    def multiline(self, lines, box, size=34, color=INK, ident='multiline'):
        pieces = [text_layer(x, size, color) for x in lines]
        boxes = [visible(x) for x in pieces]
        width = max(b[2]-b[0] for b in boxes)
        height = sum(b[3]-b[1] for b in boxes) + (len(lines)-1)*14
        layer = Image.new('RGBA', (width+40, height+40))
        y = 20
        for p, b in zip(pieces, boxes):
            layer.alpha_composite(p, (round((width-b[2]+b[0])/2)+20-b[0], y-b[1]))
            y += b[3]-b[1]+14
        self.center(layer, box, ident)
        self.records[-1].update(text='\n'.join(lines), font_size_px=size, group='whole multiline visible glyph group')

    def clearance(self):
        for i, a in enumerate(self.records):
            x1,y1,x2,y2 = a['visible_box_xyxy']
            for b in self.records[i+1:]:
                # The mathematical plane intentionally contains its zero /
                # schematic annotation; it is not a glyph collision.
                if a['component_id']=='square-array' and b['component_id'] in ('zero-empty-label','schematic-mark','schematic-explanation'):
                    continue
                u1,v1,u2,v2 = b['visible_box_xyxy']
                if max(x1,u1) < min(x2,u2) and max(y1,v1) < min(y2,v2):
                    moving = b if b['component_id'].startswith('moving-copy-') else a if a['component_id'].startswith('moving-copy-') else None
                    formula_rec=a if a['component_id']=='working-equation' else b if b['component_id']=='working-equation' else None
                    if moving and formula_rec:
                        # Only actual overlapping formula glyph pixels count.
                        # The known source factor is the sole permitted contact.
                        mid=moving['component_id'];index=int(mid.rsplit('-',1)[1])
                        fl,fo,ft=self.foreground['working-equation'];ml,mo,mt=self.foreground[mid]
                        crop=(max(x1,u1),max(y1,v1),min(x2,u2),min(y2,v2))
                        masks=[]
                        for layer,origin,threshold in ((fl,fo,ft),(ml,mo,mt)):
                            masks.append(layer.getchannel('A').point(lambda z:255 if z>=threshold else 0).crop(
                                (crop[0]-origin[0],crop[1]-origin[1],crop[2]-origin[0],crop[3]-origin[1])))
                        intersection=ImageChops.multiply(*masks)
                        contact=intersection.getbbox()
                        allowed=self.data['multiplication_input_boxes_px'][index]
                        ImageDraw.Draw(intersection).rectangle((math.floor(allowed[0]-crop[0]),math.floor(allowed[1]-crop[1]),
                                                               math.ceil(allowed[2]-crop[0])-1,math.ceil(allowed[3]-crop[1])-1),fill=0)
                        if not intersection.getbbox():
                            self.data.setdefault('source_contact_checks',[]).append({'moving_component':mid,'source_factor':index,
                                'source_box_px':allowed,'actual_source_contact':bool(contact),'other_formula_glyph_contact':False})
                            continue
                    raise ValueError(f'Foreground collision: {a["name"]} / {b["name"]}')
        self.data['foreground_groups_do_not_overlap'] = True


class Panda:
    def __init__(self):
        library = json.loads((ROOT/'catalogs/character-library-v1.json').read_text())
        self.character = next(x for x in library['characters'] if x['id']=='red-panda')
        reg = json.loads((ROOT/'assets/library/characters/red-panda/motions/v001/registration.json').read_text())
        self.poses = {x['id']: x for x in reg['frames']}
        new = DESIGN/'generation-batches/lake-square-20261112-a/registration.json'
        if new.exists():
            nreg=json.loads(new.read_text())
            self.poses.update(nreg.get('poses',{}))
        self.receipts = {}

    @lru_cache(maxsize=64)
    def sprite(self, pose, height):
        row = self.character['neutral'] if pose=='neutral' else self.poses[pose]
        path = ROOT/row['path']
        if sha(path) != row['sha256']:
            raise ValueError(f'Panda hash mismatch {path}')
        original = Image.open(path).convert('RGBA')
        scale = height/row['reference_height_px']
        sprite = original.resize((round(original.width*scale), round(original.height*scale)), Image.Resampling.LANCZOS)
        return sprite, row, scale

    def draw(self, c, pose='neutral', foot=(1460, 1007), height=310):
        sprite,row,scale = self.sprite(pose,height)
        xy = (round(foot[0]-row['anchor_px'][0]*scale), round(foot[1]-row['anchor_px'][1]*scale))
        b = visible(sprite, 8)
        absolute = [b[0]+xy[0], b[1]+xy[1], b[2]+xy[0], b[3]+xy[1]]
        if not (24<absolute[0] and 24<absolute[1] and absolute[2]<1896 and absolute[3]<1056):
            raise ValueError(f'Panda clipped {pose}: {absolute}')
        shadow = Image.new('RGBA', SIZE)
        ImageDraw.Draw(shadow).ellipse((foot[0]-110,foot[1]-10,foot[0]+130,foot[1]+12),fill=(46,79,92,23))
        c.image.alpha_composite(shadow)
        c.image.alpha_composite(sprite,xy)
        receipt = {'pose':pose,'path':row['path'],'sha256':row['sha256'], 'body_reference_height_px':row['reference_height_px'],
                   'display_body_height_px':height,'source_scale':scale,'foot_anchor_px':list(foot),
                   'visible_box_xyxy':absolute,'horizontal':'anatomical foot x','vertical':'grounded support y',
                   'not_centering_target':True,'source_pixels_modified':False,'mirrored':False}
        c.data['character'] = receipt
        self.receipts[f'{pose}@{height}'] = receipt
        # The character also participates in actual visible-foreground clearance.
        c.records.append({'name':f'{c.scene}/character','component_id':'character','scene':c.scene,
                          'visible_box_xyxy':absolute,'horizontal':'foot-support','vertical':'foot-support',
                          'passed':True,'not_centering_target':True,'contained':True})


def header(c, subtitle='THE FROZEN LAKE · SQUARE NUMBERS'):
    # The teaching overlay is a calm, legible plane over the illustrated lake.
    c.panel((70,30,1850,154), fill='#f5faf7', outline='#d4e3df', radius=30, width=1)
    c.text('SQUARE NUMBERS', (100,49,1820,107),48,INK,'episode-title')
    c.text(subtitle,(100,113,1820,143),22,TEAL,'episode-subtitle')


def formula(c,n,result=True,opacity=1,blank=False):
    c.panel((240,178,1680,310), fill='#fffaf0',outline='#d8d1be')
    text = f'{n}² = {n} × {n} = ' + (f'{n*n:,}' if result else '?')
    if blank:
        text = 'n² = n × n'
    c.text(text,(264,190,1656,292),82,INK,'working-equation',opacity)
    c.data.update(n=n,value=n*n,operands=[n,n],equation=text,equation_font_px=82,
                  result_committed=result and not blank)
    # Locate both concrete multiplication inputs in the rendered formula so
    # the motion study copies those visible glyphs rather than inventing an
    # unrelated start point elsewhere on the screen.
    if not blank:
        rec=c.records[-1]
        bound=font(82).getbbox(text)
        draw_x=rec['visible_box_xyxy'][0]-bound[0]
        prefixes=[f'{n}² = ',f'{n}² = {n} × ']
        nb=font(82).getbbox(str(n))
        centers=[draw_x+font(82).getlength(prefix)+(nb[0]+nb[2])/2 for prefix in prefixes]
        c.data['multiplication_input_centers_px']=[[round(x,3),241] for x in centers]
        draw_y=rec['visible_box_xyxy'][1]-bound[1]
        c.data['multiplication_input_boxes_px']=[[draw_x+font(82).getlength(prefix)+nb[0],draw_y+nb[1],
                                                draw_x+font(82).getlength(prefix)+nb[2],draw_y+nb[3]] for prefix in prefixes]


def grid_layer(n,progress=1,lshape=False,block=False):
    # 480px exact square, with extra measurement margins retained around it.
    layer = Image.new('RGBA',(520,520))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((20,20,499,499),radius=10,fill='#f1fbfb',outline='#86afb9',width=3)
    cells = []
    if n==0:
        # The outline denotes the empty demonstration field, not one unit tile.
        d.line((70,70,449,449),fill='#c5d9de',width=2)
        d.line((449,70,70,449),fill='#c5d9de',width=2)
        return layer,cells,'empty field; no unit cell rendered'
    if n<=10 or block:
        count = 10 if block else n
        pitch = 480/count
        for row in range(count):
            for col in range(count):
                complete = row < math.floor(count*progress+1e-9)
                old = lshape and row<count-1 and col<count-1
                corner = lshape and row==count-1 and col==count-1
                new = lshape and not old
                fill = '#c7e2e9' if not complete else '#75bdc8'
                if lshape:
                    fill = '#96c8d1' if old else '#f4cf90' if corner else '#e5aa6f'
                x0,y0 = round(20+col*pitch),round(20+row*pitch)
                x1,y1 = round(20+(col+1)*pitch)-1,round(20+(row+1)*pitch)-1
                d.rectangle((x0+2,y0+2,x1-2,y1-2),fill=fill)
                cells.append({'row':row,'col':col,'lit':complete,'old':old,'new':new,'corner':corner,
                              'units':100 if block else 1})
        return layer,cells,'100 exact blocks, each 10 by 10 units' if block else 'one exact square cell per unit'
    # Beyond ten units per side this is deliberately an ungridded schematic.
    # No decorative dots/cells can be mistaken for a counted quantity.
    y = round(20+480*progress)
    if y>20:
        d.rectangle((24,24,495,min(y,495)),fill='#9acbd4')
    return layer,cells,'ungridded schematic; side labels specify units'


def diagram(c,n,progress=1,lshape=False,block=False,side_labels=True):
    layer,cells,kind = grid_layer(n,progress,lshape,block)
    c.center(layer,GRID_BOX,'square-array')
    c.data.update(diagram_kind=kind,diagram_unit_cells=cells,lit_row_fraction=progress,
                  diagram_counted_quantity=sum(x['units'] for x in cells),square_side_units=n,
                  conceptual_fill_not_unit_count=n>10 and not block)
    # These rulers annotate the mathematical plane, not perspective lake objects.
    c.draw.line((720,388,1200,388),fill=TEAL,width=3)
    c.draw.line((720,379,720,398),fill=TEAL,width=3)
    c.draw.line((1200,379,1200,398),fill=TEAL,width=3)
    c.draw.line((694,402,694,882),fill=BLUE,width=3)
    c.draw.line((684,402,704,402),fill=BLUE,width=3)
    c.draw.line((684,882,704,882),fill=BLUE,width=3)
    if side_labels:
        c.text(str(n),(850,331,1070,375),35,TEAL,'horizontal-side')
        c.text(str(n),(592,606,672,676),35,BLUE,'vertical-side')
    else:
        c.absent.append({'id':'side-labels','reason':'the two moving input copies become the side labels at arrival'})
    if n==0:
        c.text('NO UNIT TILES',(730,600,1190,664),40,MUTED,'zero-empty-label')
    if n>10 and not block:
        c.text('SCHEMATIC',(740,558,1180,608),35,TEAL,'schematic-mark')
        c.text('dimensions in units',(738,627,1182,674),28,INK,'schematic-explanation')
    if block:
        c.panel((1245,397,1780,888),fill='#f8fbf6',radius=20)
        c.text('1 BLOCK = 100 UNITS',(1265,427,1760,477),29,TEAL,'block-key-title')
        c.text('10 × 10 unit squares',(1270,495,1755,540),28,INK,'block-key-subtitle')
        sample=Image.new('RGBA',(260,260))
        sd=ImageDraw.Draw(sample)
        for row in range(10):
            for col in range(10):
                xx,yy=20+col*22,20+row*22
                sd.rectangle((xx+1,yy+1,xx+20,yy+20),fill='#75bdc8')
        c.center(sample,(1385,570,1635,820),'one-block-unit-zoom')
        # Parent-to-detail connector: this is one existing block, not an
        # additional group of one hundred units beside the counted array.
        c.draw.rectangle((1154,405,1197,447),outline=GOLD,width=3)
        c.draw.line((1202,426,1225,426,1225,695,1392,695),fill=GOLD,width=3)
        c.text('ZOOM KEY · THE SAME BLOCK',(1260,840,1765,875),22,MUTED,'block-key-no-addition')
        c.data['block_zoom_key']={'visible_unit_cells':100,'rows':10,'columns':10,'units_per_cell':1,
                                   'source_block_row':0,'source_block_col':9,'adds_to_counted_total':False,
                                   'role':'magnified detail of one already counted parent block'}
    return cells


def reading(c,value):
    text = words(value)
    c.text(text,(350,922,1570,977),35,INK,'natural-reading')


def footer(c,label):
    c.text(label,(180,1027,1740,1061),22,MUTED,'planning-note')


def standard(plate,panda,name,n,stage='result',progress=1,reveal=1):
    c = Canvas(plate,name)
    header(c)
    formula(c,n,result=stage=='result')
    diagram(c,n,progress)
    c.text('ROW × COLUMN → SQUARE',(320,922,1600,977),31,TEAL,'process-caption') if stage!='result' else reading(c,n*n)
    panda.draw(c,'think' if stage=='input' else 'aha' if stage=='result' and n in (4,10,32) else 'neutral',
               foot=(1460,1007),height=280)
    footer(c,f'PLANNING STUDY · n = {n} · {stage.upper()}')
    c.clearance()
    return c


def opening(plate,panda):
    c = Canvas(plate,'01-opening')
    header(c,'NUM-NUM NUMBERS · A NUMBER TAKES SHAPE')
    formula(c,0,result=True)
    zero,_,_=grid_layer(0)
    c.center(zero.resize((320,320),Image.Resampling.LANCZOS),(800,350,1120,670),'empty-zero-field')
    c.text('NO UNIT TILES',(700,677,1220,713),29,MUTED,'zero-empty-label')
    panda.draw(c,'greet',foot=(960,1007),height=260)
    c.multiline(['One rule.', 'A lake of squares.'],(170,440,700,590),38,TEAL,'opening-line')
    c.multiline(['Start at zero.', 'Watch both sides grow.'],(1240,440,1790,590),34,TEAL,'opening-promise')
    footer(c,'PLANNING STUDY · 0² → 100² · Count the generated answers')
    c.clearance()
    return c


def l_shape(plate,panda,progress=1):
    c = Canvas(plate,'04-l-shape')
    header(c,'GROW THE NEXT SQUARE · KEEP THE OLD SIXTEEN')
    c.panel((240,178,1680,310),fill='#fffaf0',outline='#d8d1be')
    c.text('4² + (4 + 4 + 1) = 5²',(264,190,1656,292),78,INK,'l-growth-equation')
    cells = diagram(c,5,progress=progress,lshape=True)
    assert len([x for x in cells if x['old']])==16
    assert len([x for x in cells if x['new']])==9
    c.panel((125,421,610,651),fill='#fff7e8',radius=20)
    c.multiline(['16 old tiles', '+ 9 new tiles', 'The next square'],(145,448,590,625),36,GOLD,'l-count-explanation')
    panda.draw(c,'trace_extend' if 'trace_extend' in panda.poses else 'aha',foot=(1500,1007),height=320)
    c.text('4 along one side + 4 along the other + 1 corner',(180,925,1340,978),28,INK,'l-corner-not-double-counted')
    footer(c,'LOOK AHEAD · 5² − 4² = 9 · the next result waits for its count')
    c.data.update(n=5,value=25,old_quantity=16,new_quantity=9,corner_quantity=1,result_committed=False)
    c.clearance()
    return c


def threshold(plate,panda):
    c = Canvas(plate,'06-thousand-threshold')
    header(c,'THE SAME RULE · A NEW DIGIT')
    formula(c,32)
    # 32=30+2 on both axes, with true 30:2 lengths. The four areas
    # demonstrate the multiplication instead of painting 1,024 tiny units.
    x,y,side=720,402,480
    split=450
    c.draw.rectangle((x,y,x+split-1,y+split-1),fill='#92c6cf')
    c.draw.rectangle((x+split,y,x+side-1,y+split-1),fill='#e3b179')
    c.draw.rectangle((x,y+split,x+split-1,y+side-1),fill='#e3b179')
    c.draw.rectangle((x+split,y+split,x+side-1,y+side-1),fill='#f3d692')
    c.draw.rectangle((x,y,x+side-1,y+side-1),outline=TEAL,width=2)
    c.text('900',(x+15,y+20,x+split-15,y+split-20),78,INK,'area-900')
    # The narrow two-unit bands keep their exact proportions. Their values are
    # legible callouts in the external margin, not tiny digits inside a strip.
    c.draw.line((1196,627,1223,627,1243,532),fill=GOLD,width=3)
    c.draw.ellipse((1181,622,1189,630),fill=GOLD)
    c.text('60',(1248,500,1408,565),42,GOLD,'area-60-right')
    c.draw.line((945,877,945,902,1281,902,1281,875),fill=GOLD,width=3)
    c.draw.ellipse((941,863,949,871),fill=GOLD)
    c.text('60',(1225,812,1345,874),42,GOLD,'area-60-bottom')
    c.draw.line((1197,867,1212,867,1212,727,1230,727),fill=INK,width=3)
    c.draw.ellipse((1181,863,1189,871),fill=INK)
    c.text('4',(1235,695,1335,760),42,INK,'area-4')
    c.text('30',(x+15,341,x+split-15,381),32,TEAL,'top-thirty')
    c.text('2',(x+split,341,x+side,381),30,GOLD,'top-two')
    c.text('30',(650,y+20,704,y+split-20),30,BLUE,'left-thirty')
    c.text('2',(650,y+split,704,y+side),30,GOLD,'left-two')
    c.panel((125,420,635,654),fill='#fff7e8',radius=20)
    c.multiline(['31² = 961', '32 = 30 + 2', '900 + 60 + 60 + 4'],(145,443,615,630),32,GOLD,'threshold-comparison')
    panda.draw(c,'trace_up' if 'trace_up' in panda.poses else 'aha',foot=(1490,1007),height=315)
    reading(c,1024)
    footer(c,'PLANNING STUDY · exact area split · 900 + 60 + 60 + 4 = 1,024')
    c.data.update(previous_n=31,previous_value=961,first_square_over_1000=1024,
                  split_side_units=[30,2],area_parts=[900,60,60,4],area_sum=1024,
                  diagram_kind='exact 30:2 area decomposition, not 1,024 painted unit cells')
    c.clearance()
    return c


def maximum(plate,panda):
    c = Canvas(plate,'07-maximum')
    header(c,'ONE HUNDRED ON EACH SIDE')
    formula(c,100)
    cells = diagram(c,100,block=True)
    assert len(cells)==100 and sum(x['units'] for x in cells)==10000
    panda.draw(c,'present_square' if 'present_square' in panda.poses else 'cheer',foot=(425,1007),height=320)
    reading(c,10000)
    footer(c,'PLANNING STUDY · 100 blocks × 100 unit squares = 10,000')
    c.data.update(block_count=100,units_per_block=100,total_units=10000)
    c.clearance()
    return c


def finale(plate,panda):
    c = Canvas(plate,'08-finale')
    header(c,'THE SQUARE-NUMBER SEQUENCE KEEPS GOING')
    formula(c,100,blank=True)
    values=[0,1,4,9,16,25,36,49,64,81,100]
    # Compact beginning is legible; ellipsis explicitly bridges the omitted terms.
    c.text('0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100, …',(180,369,1740,440),52,TEAL,'sequence-beginning')
    c.text('…, 9,604, 9,801, 10,000',(310,511,1610,595),65,INK,'sequence-ending')
    c.text('101 terms counted. The rule keeps going.',(280,653,1640,715),39,GOLD,'finale-total')
    panda.draw(c,'greet',foot=(960,1010),height=260)
    footer(c,'PLANNING STUDY · n = 0, 1, 2, …, 100 · no term skipped in the count')
    c.data.update(first_values=values,last_values=[9604,9801,10000],total_terms=101)
    c.clearance()
    return c


def animation_frame(plate,panda,k,fps=15):
    """12 s: same input copied to two side rulers, four rows, then sixteen."""
    t=k/fps
    if t<1.8:
        phase='input'
        progress=0
    elif t<4:
        phase='travel'
        progress=0
    elif t<7:
        phase='fill'
        progress=min(1,(t-4)/3)
    else:
        phase='result'
        progress=1
    c=Canvas(plate,f'animation/{k:04d}')
    header(c,'ONE INPUT → TWO EQUAL SIDES → ONE SQUARE NUMBER')
    formula(c,4,result=phase=='result')
    diagram(c,4,progress,side_labels=phase!='travel')
    if phase=='travel':
        u=(t-1.8)/2.2
        # Copies of one n travel along different dimensions; they are not added.
        for i,(endx,endy,color) in enumerate(((960,351,TEAL),(632,641,BLUE))):
            startx,starty=c.data['multiplication_input_centers_px'][i]
            # Depart straight downward from each source glyph. Separated
            # horizontal lanes prevent the copies from crossing one another.
            if i==0:
                if u<.4:
                    x,y=startx,starty+(351-starty)*u/.4
                else:
                    x,y=startx+(endx-startx)*(u-.4)/.6,351
            elif u<.25:
                x,y=startx,starty+(300-starty)*u/.25
            elif u<.6:
                x,y=startx+(632-startx)*(u-.25)/.35,300
            else:
                x,y=632,300+(641-300)*(u-.6)/.4
            c.text('4',(x-28,y-28,x+28,y+28),42,color,f'moving-copy-{i}')
    if phase=='result':
        reading(c,16)
    else:
        caption={'input':'The same number sets both sides.','travel':'Copy 4 into the width and the height.','fill':'Four rows. Four in each row.'}[phase]
        c.text(caption,(360,922,1560,977),34,TEAL,'animation-explanation')
    panda.draw(c,'trace_extend' if 'trace_extend' in panda.poses else 'neutral',
               foot=(1460,1007),height=280)
    footer(c,'SILENT PLANNING STUDY · motion of the equation only · not the episode')
    c.data.update(animation_time_seconds=round(t,6),animation_phase=phase,lit_rows=math.floor(progress*4+1e-9))
    # Side-ruler text is absent during travel, so destination contact is never
    # a doubled glyph. All travel frames pass the same clearance check, with
    # only exact same-value source-factor pixels allowed at departure.
    c.clearance()
    return c


def save(c,filename):
    path=OUT/filename
    c.image.convert('RGB').save(path)
    return {'filename':filename,'sha256':sha(path),'scene_data':c.data,
            'components':c.records,'intentional_absences':c.absent}


def run(no_video=False,allow_placeholder=False):
    OUT.mkdir(parents=True,exist_ok=True)
    QA.mkdir(parents=True,exist_ok=True)
    if not BG.exists() and not allow_placeholder:
        raise FileNotFoundError(f'Generated clean plate pending: {BG}')
    plate=ImageOps.fit(Image.open(BG).convert('RGBA'),SIZE,Image.Resampling.LANCZOS) if BG.exists() else Image.new('RGBA',SIZE,'#edf6f8')
    panda=Panda()
    shots=[(opening(plate,panda),'01-opening.png','01 · Begin at zero'),
           (standard(plate,panda,'02-input',4,'input',0),'02-input-four.png','02 · One input sets two sides'),
           (standard(plate,panda,'03-result',4),'03-result-sixteen.png','03 · Four rows generate sixteen'),
           (l_shape(plate,panda),'04-l-shape-nine.png','04 · Keep sixteen, add an L of nine'),
           (standard(plate,panda,'05-hundred',10),'05-hundred.png','05 · Ten by ten makes one hundred'),
           (threshold(plate,panda),'06-thousand-threshold.png','06 · Same rule, first square over 1,000'),
           (maximum(plate,panda),'07-ten-thousand.png','07 · 100 blocks of 100 units'),
           (finale(plate,panda),'08-finale.png','08 · The sequence keeps going')]
    reports=[save(c,filename) for c,filename,_ in shots]
    sheet=Image.new('RGB',(1920,4*575),'#f2f4ed')
    sd=ImageDraw.Draw(sheet)
    for i,(c,_,caption) in enumerate(shots):
        x=(i%2)*960;y=(i//2)*575
        sheet.paste(c.image.convert('RGB').resize((928,522),Image.Resampling.LANCZOS),(x+16,y+7))
        sd.text((x+24,y+540),caption,font=font(22),fill=INK)
    sheet.save(OUT/'storyboard.png')
    sheet.resize((1440,1725),Image.Resampling.LANCZOS).save(OUT/'storyboard-preview.jpg',quality=94)
    all_states=[]
    for n in range(101):
        for stage,progress in [('input',0),('fill',.5),('result',1)]:
            c=standard(plate,panda,f'all/{n}/{stage}',n,stage,progress)
            all_states.append({'n':n,'value':n*n,'stage':stage,'components':c.records,'scene_data':c.data})
    longest=max(range(101),key=lambda n:font(35).getlength(words(n*n)))
    reports.append(save(standard(plate,panda,'longest-reading',longest),'09-longest-reading.png'))
    animation_reports=[]
    if not no_video:
        ffmpeg=str(ROOT/'.venv/bin/ffmpeg') if (ROOT/'.venv/bin/ffmpeg').exists() else shutil.which('ffmpeg')
        if not ffmpeg:
            raise FileNotFoundError('Provide FFmpeg through .venv/bin/ffmpeg or PATH')
        frame_dir=QA/'motion-samples'
        frame_dir.mkdir(exist_ok=True)
        gif=[]
        with (QA/'motion-ffmpeg.log').open('wb') as log:
            process=subprocess.Popen([ffmpeg,'-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','15','-i','-',
                                      '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-r','30','-movflags','+faststart',
                                      str(OUT/'working-equation-study.mp4')],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            for k in range(180):
                c=animation_frame(plate,panda,k)
                rgb=c.image.convert('RGB')
                process.stdin.write(rgb.tobytes())
                if k in (0,27,40,59,60,80,104,105,179):
                    rgb.save(frame_dir/f'{k:04d}.png')
                animation_reports.append({'frame':k,'time_seconds':k/15,'components':c.records,'data':c.data})
                if k%3==0:
                    gif.append(rgb.resize((960,540),Image.Resampling.LANCZOS))
            process.stdin.close()
            if process.wait():
                raise RuntimeError('Motion MP4 encoding failed; inspect motion-ffmpeg.log')
        gif[0].save(OUT/'working-equation-study.gif',save_all=True,append_images=gif[1:],duration=200,loop=0)
    centered=[x for r in reports for x in r['components'] if not x.get('not_centering_target')]
    centered += [x for r in all_states for x in r['components'] if not x.get('not_centering_target')]
    centered += [x for r in animation_reports for x in r['components'] if not x.get('not_centering_target')]
    travel=[r for r in animation_reports if r['data']['animation_phase']=='travel']
    source_contacts=[{'frame':r['frame'],'time_seconds':r['time_seconds'],**contact}
                     for r in travel for contact in r['data'].get('source_contact_checks',[]) if contact['actual_source_contact']]
    technical=None
    if not no_video:
        ffprobe=str(ROOT/'.venv/bin/ffprobe') if (ROOT/'.venv/bin/ffprobe').exists() else shutil.which('ffprobe')
        if not ffprobe:
            raise FileNotFoundError('Provide ffprobe through .venv/bin/ffprobe or PATH')
        video=OUT/'working-equation-study.mp4'
        probe=json.loads(subprocess.run([ffprobe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)],
                                       check=True,capture_output=True,text=True).stdout)
        stream=probe['streams'][0]
        assert stream['width']==1920 and stream['height']==1080
        assert stream['r_frame_rate']=='30/1' and int(stream['nb_read_frames'])==360
        assert abs(float(stream['duration'])-12)<.001
        decoded=subprocess.run([ffmpeg,'-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True)
        assert decoded.returncode==0 and not decoded.stderr.strip(),decoded.stderr
        technical={'kind':'arithmetic-study-technical-verification','production_video':False,'video':str(video.relative_to(ROOT)),
                   'sha256':sha(video),'all_360_frames_decoded':True,'duration_seconds':12,'fps':30,
                   'source_arithmetic_frames':180,'audio_present':False,'full_decode_stderr':decoded.stderr,'probe':probe,
                   'scope':'12-second silent arithmetic planning study only; not finished episode QA'}
        (QA/'study-technical-verification.json').write_text(json.dumps(technical,ensure_ascii=False,indent=2)+'\n')
    summary={'kind':'preproduction-square-mockup-verification','production_ready':False,'video_generated':False,
             'production_video_generated':False,'arithmetic_study_video_generated':not no_video,
             'background_placeholder':not BG.exists(),'resolution_px':list(SIZE),'count_range_n':[0,100],
             'term_count':101,'all_state_count':len(all_states),'animation_frame_count':len(animation_reports),
             'centered_component_observations':len(centered),'max_abs_dx_px':max(abs(x['delta_x_px']) for x in centered),
             'max_abs_dy_px':max(abs(x['delta_y_px']) for x in centered),'all_centered_components_pass':all(x['passed'] for x in centered),
             'longest_reading_n':longest,'longest_reading':words(longest*longest),
             'travel_frames_checked':len(travel),'all_travel_frames_clear':all(r['data']['foreground_groups_do_not_overlap'] for r in travel),
             'travel_collision_policy':'all foreground pairs checked; actual glyph-mask contact allowed only within the identical original source factor; side labels absent until arrival',
             'permitted_actual_source_contacts':source_contacts,'study_technical_verification':technical,
             'character_source_policy':'canonical neutral + reviewed motions/v001 + episode-local static gesture candidates; no shared selection changed',
             'character_placements':panda.receipts,'stills':reports,
             'all_states':all_states,'animation':animation_reports,
             'limitations':['No production speech, subtitle timing, or finished MP4 QA.','Animation is an arithmetic concept study; character key-pose changes are not production motion acceptance.',
                            'Illustration plate must be visually inspected at final native size.']}
    (QA/'mockup-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (QA/'mockup-verification.txt').write_text(
        f'Square-number preproduction only\n101 terms; {len(all_states)} state layouts; {len(animation_reports)} animation frames.\n'
        f'{len(centered)} foreground component observations. Both axes ≤0.5px: {summary["all_centered_components_pass"]}.\n'
        f'Max |dx|={summary["max_abs_dx_px"]} px; max |dy|={summary["max_abs_dy_px"]} px.\n'
        f'Longest reading: n={longest}, {words(longest*longest)}.\n'
        f'Generated background in use: {BG.exists()}.\nProduction MP4/audio/subtitles: not produced or accepted.\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('stills','all_states','animation','character_placements','study_technical_verification','permitted_actual_source_contacts')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-video',action='store_true')
    parser.add_argument('--allow-placeholder',action='store_true')
    args=parser.parse_args()
    run(args.no_video,args.allow_placeholder)
