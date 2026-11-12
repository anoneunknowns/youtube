"""Exact, layered 1080p planning images for the Glass Gallery of Ratios.

Generated art stays immutable. This checks planning renders, not a finished episode.
"""
from __future__ import annotations
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont
from component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'design/geometric-sequence-counting-v1'
BATCH = 'geometric-preproduction-20261112-01a1cdca'
BG = D / f'generation-batches/{BATCH}/source/glass-salt-plain.png'
CHAR = ROOT / f'assets/library/characters/rabbit-beret/generation-batches/{BATCH}'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
W, H = 1920, 1080
INK, TEAL, CORAL, MUTED = '#573c36', '#367f7b', '#b86458', '#8c7166'
COLORS = ['#e69a83', '#83b8ad', '#b6a1ca']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@lru_cache(maxsize=100)
def font(size):
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=1)
def background_plate():
    return Image.open(BG).convert('RGBA').resize((W,H),Image.Resampling.LANCZOS)


def bounds(im, threshold=128):
    b = im.getchannel('A').point(lambda a: 255 if a >= threshold else 0).getbbox()
    if b is None:
        raise ValueError('Empty foreground')
    return b


@lru_cache(maxsize=1200)
def letters(s, size=40, color=INK):
    b = font(size).getbbox(s)
    im = Image.new('RGBA', (b[2]-b[0]+48, b[3]-b[1]+48))
    ImageDraw.Draw(im).text((24-b[0], 24-b[1]), s, font=font(size), fill=color)
    return im


def group_lines(lines, size=30, color=INK, gap=14):
    ims = [letters(s, size, color) for s in lines]
    bs = [bounds(x) for x in ims]
    width = max(b[2]-b[0] for b in bs)
    height = sum(b[3]-b[1] for b in bs)+gap*(len(bs)-1)
    out = Image.new('RGBA', (width+48, height+48))
    y = 24
    for im, b in zip(ims, bs):
        out.alpha_composite(im, (24+round((width-b[2]+b[0])/2)-b[0], y-b[1]))
        y += b[3]-b[1]+gap
    return out


def typeset(parts):
    """Parts are (literal text, font size, downward offset, color)."""
    out = Image.new('RGBA', (2400, 280))
    x = 30
    for s, size, offset, color in parts:
        im = letters(s, size, color)
        b = bounds(im)
        y = 105-size*.7+offset
        out.alpha_composite(im, (x-b[0], round(y)-b[1]))
        x += b[2]-b[0]+6
    b = bounds(out)
    return out.crop((b[0]-20,b[1]-20,b[2]+20,b[3]+20))


def formula(index='n', exp='n−1', result=None, size=72):
    parts = [('a',size,0,INK),(str(index),round(size*.53),size*.38,TEAL),
             (' = 2 × 3',size,0,INK),(str(exp),round(size*.53),-size*.32,TEAL)]
    if result is not None:
        parts.append((f' = {result}',size,0,INK))
    return typeset(parts)


def power(base, exp, suffix='', size=70):
    parts = [(str(base),size,0,INK),(str(exp),round(size*.55),-size*.32,TEAL)]
    if suffix:
        parts.append((suffix,size,0,INK))
    return typeset(parts)


class Canvas:
    def __init__(self, ident):
        self.ident = ident
        self.image = background_plate().copy()
        self.draw = ImageDraw.Draw(self.image)
        self.records = []
        self.notes = {}

    def put(self, layer, box, ident):
        b = bounds(layer)
        xy = (round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
        report = raster_centering_report(layer,box,origin_xy=xy,name=f'{self.ident}/{ident}',tolerance_px=.5)
        report.update(scene=self.ident,component_id=ident,resolution_px=[W,H],horizontal='center',vertical='center')
        if not report['passed']:
            raise ValueError(report)
        self.records.append(report)
        self.image.alpha_composite(layer,xy)

    def text(self,s,box,size=40,color=INK,ident='text'):
        self.put(letters(s,size,color),box,ident)
        self.records[-1].update(text=s,font_size_px=size)

    def lines(self,lines,box,size=30,color=INK,ident='lines'):
        self.put(group_lines(lines,size,color),box,ident)
        self.records[-1].update(text='\n'.join(lines),font_size_px=size,group='whole multiline visible glyph group')

    def panel(self,box,fill='#fff9ef',outline='#d5bbaa',radius=35):
        self.draw.rounded_rectangle(box,fill=fill,outline=outline,width=2,radius=radius)

    def arrow(self,a,b,color=TEAL,width=6):
        self.draw.line((a,b),fill=color,width=width)
        angle=math.atan2(b[1]-a[1],b[0]-a[0]); length=17
        tip1=(b[0]-length*math.cos(angle-.5),b[1]-length*math.sin(angle-.5))
        tip2=(b[0]-length*math.cos(angle+.5),b[1]-length*math.sin(angle+.5))
        self.draw.polygon([b,tip1,tip2],fill=color)

    def header(self,s,sub=''):
        self.text(s,(160,64,1760,140),48,ident='heading')
        if sub:
            self.text(sub,(150,155,1770,205),27,MUTED,'subheading')


class Rabbit:
    def __init__(self):
        c=next(c for c in json.loads((ROOT/'catalogs/character-library-v1.json').read_text())['characters'] if c['id']=='rabbit-beret')
        self.neutral=c['neutral']
        self.poses=json.loads((CHAR/'registration.json').read_text())['poses']
        self.used={}

    @lru_cache(maxsize=50)
    def sprite(self,pose,height):
        row=self.neutral if pose=='neutral' else self.poses[pose]
        p=ROOT/row['path']
        assert sha(p)==row['sha256']
        im=Image.open(p).convert('RGBA')
        anchor=list(row['anchor_px'])
        if pose=='neutral':
            region=row['image_region_px']; im=im.crop(region)
            anchor=[anchor[0]-region[0],anchor[1]-region[1]]
        scale=height/row['reference_height_px']
        return im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS),row,anchor,scale

    def draw(self,c,pose='neutral',height=280,foot=(960,1035)):
        im,row,anchor,scale=self.sprite(pose,height)
        xy=(round(foot[0]-anchor[0]*scale),round(foot[1]-anchor[1]*scale))
        b=bounds(im)
        visible=[b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]
        delta=[xy[i]+anchor[i]*scale-foot[i] for i in (0,1)]
        contained=20<=visible[0] and 20<=visible[1] and visible[2]<=1900 and visible[3]<=1065
        rec=dict(scene=c.ident,component_id='rabbit',horizontal='foot-anchor-x',vertical='anatomical-foot-support-y',
                 visible_box_xyxy=visible,target_anchor_px=list(foot),delta_x_px=delta[0],delta_y_px=delta[1],
                 tolerance_px=.5,contained=contained,passed=contained and all(abs(x)<=.5 for x in delta),
                 reference_height_px=row['reference_height_px'],display_reference_height_px=height,scale=scale,pose=pose,source=row['path'])
        assert rec['passed'],rec
        c.records.append(rec); c.image.alpha_composite(im,xy)
        self.used[row['path']]=dict(sha256=row['sha256'],native_reference_height_px=row['reference_height_px'],
                                   maximum_display_reference_height_px=max(height,self.used.get(row['path'],{}).get('maximum_display_reference_height_px',0)))


def beads(n,color=TEAL,size=24,columns=3):
    rows=math.ceil(n/columns); columns=min(n,columns); step=size+16
    im=Image.new('RGBA',(columns*step+48,rows*step+48)); d=ImageDraw.Draw(im)
    for i in range(n):
        x,y=24+(i%columns)*step,24+(i//columns)*step
        d.ellipse((x,y,x+size,y+size),fill=color,outline=INK,width=2)
    return im


def triple(rabbit,phase=1,previous=6,ident='04-three-equal-groups'):
    c=Canvas(ident); result=previous*3
    c.header('THE SAME MULTIPLIER, EVERY TIME','r = 3  •  each group holds the previous value')
    c.text(f'{previous:,} × 3 = '+(f'{result:,}' if phase>=1 else '?'),(320,235,1600,330),82,ident='operation')
    for i,x in enumerate((510,960,1410)):
        c.panel((x-175,388,x+175,650),fill=['#fff1e8','#edf5ee','#f4edf7'][i])
        c.text(f'GROUP {i+1}',(x-150,402,x+150,450),27,MUTED,f'group-{i+1}-label')
        if phase>=1 or i==0:
            c.put(beads(previous,COLORS[i],30,3),(x-140,470,x+140,610),f'group-{i+1}-units')
    c.text('1 bead = 1', (720,670,1200,714),28,MUTED,'unit-legend')
    if phase>=1:
        c.text(f'{result:,}',(680,740,1240,880),124,TEAL,'result')
        c.text('18 beads in total' if result==18 else f'{result} beads in total',(650,892,1270,944),29,MUTED,'total-description')
    else:
        c.text('Three equal groups are forming.',(470,753,1450,825),38,TEAL,'phase-caption')
    rabbit.draw(c,'three_way_wonder' if phase>=1 else 'control_ready',260,(350,1038))
    c.notes.update(previous=previous,result=str(result) if phase>=1 else None,exact_bead_count=result if phase>=1 else previous,
                   groups_complete=phase>=1,not_a_physical_optical_experiment=True)
    return c


def large(rabbit,n,ident=None):
    c=Canvas(ident or f'count-{n:02d}')
    v=2*3**(n-1); previous=v//3
    c.header('GEOMETRIC SEQUENCES',f'Term {n}  •  a = 2  •  r = 3')
    c.text(f'{previous:,} × 3 =',(180,238,1740,328),55,ident='operand')
    c.text(f'{v:,}',(130,368,1790,504),82,TEAL,'result')
    row=TERMS[n-1]
    words=row.get('english') or row.get('result_text') or row.get('spoken_text')
    if not words:
        words=row.get('english_result',str(v))
    c.lines(textwrap.wrap(words,88),(150,540,1770,724),28,INK,'english-reading')
    c.text(f'Three equal value groups of {previous:,}',(170,735,1750,775),29,MUTED,'symbolic-groups')
    c.text('VALUE DIAGRAM  •  not a picture of every unit',(350,785,1570,823),23,MUTED,'diagram-legend')
    rabbit.draw(c,'follow_up' if n==41 else 'neutral',220,(960,1060))
    c.notes.update(n=n,value=str(v),previous=str(previous),main_term=True,visual_mode='labeled_value_groups')
    return c


def ratio_loop(rabbit,n=25):
    c=Canvas('10-the-ratio-loop');v=2*3**(n-1);previous=v//3
    c.header('THE RESULT BECOMES THE NEXT INPUT',f'Term {n}  •  VALUE GROUPS  •  keep the multiplier fixed at three')
    c.panel((320,260,800,402),fill='#fff7eb')
    c.text('PREVIOUS VALUE',(350,270,770,312),25,MUTED,'previous-label')
    c.text(f'{previous:,}',(340,327,780,385),36,INK,'previous-value')
    c.draw.ellipse((870,245,1050,425),fill='#edf5ee',outline=TEAL,width=3)
    c.text('×3',(880,276,1040,394),68,TEAL,'fixed-multiplier')
    c.arrow((810,335),(855,335))
    for i,x in enumerate((510,960,1410)):
        c.panel((x-195,475,x+195,615),fill=['#fff1e8','#edf5ee','#f4edf7'][i])
        c.text(f'GROUP {i+1}',(x-170,485,x+170,525),25,MUTED,f'loop-group-label-{i}')
        c.text(f'{previous:,}',(x-177,541,x+177,595),31,INK,f'loop-group-value-{i}')
        c.arrow((960,432),(x,463),COLORS[i],5)
    c.draw.line([(510,625),(510,649),(1410,649),(1410,625)],fill=TEAL,width=5)
    c.arrow((960,625),(960,664))
    c.text(f'{v:,}',(270,680,1650,810),82,TEAL,'loop-result')
    words=TERMS[n-1]['english']
    c.lines(textwrap.wrap(words,70),(370,815,1500,942),26,INK,'loop-english')
    c.draw.line([(290,745),(233,745),(233,335),(304,335)],fill=TEAL,width=5)
    c.arrow((267,335),(304,335))
    c.text('Reuse the whole result. Keep ×3.',(400,955,1500,1007),28,MUTED,'feedback-label')
    rabbit.draw(c,'neutral',220,(1720,1045))
    c.notes.update(n=n,value=str(v),previous=str(previous),visual_mode='value_group_feedback_loop',
                   editorial_role='Example of the larger-value loop used between general-formula and full-width modes')
    return c


def scenes(rabbit):
    out=[]
    c=Canvas('01-introduction')
    c.text('GEOMETRIC SEQUENCES',(120,100,1800,210),70,ident='title')
    c.text('The Glass Gallery of Ratios',(220,230,1700,292),36,TEAL,'subtitle')
    c.put(formula(size=96),(360,340,1560,492),'general-formula')
    c.text('2   →   6   →   18   →   54   →   …',(250,550,1670,648),65,ident='preview-path')
    c.text('One starting value. One repeating multiplier.',(260,674,1660,730),34,MUTED,'promise')
    rabbit.draw(c,'control_ready',300,(960,1050));out.append(c)

    c=Canvas('02-first-term')
    c.header('START WITH TWO','Term 1  •  zero multiplications so far')
    c.put(formula('1','0','2',80),(350,254,1570,370),'seed-formula')
    c.put(beads(2,TEAL,82,2),(710,421,1210,571),'seed-beads')
    c.text('2',(650,616,1270,766),138,TEAL,'seed-value')
    c.text('The zero exponent keeps the starting value.',(350,805,1570,865),33,MUTED,'zero-exponent')
    rabbit.draw(c,'neutral',280,(1470,1040));out.append(c)
    out.extend([triple(rabbit,1,previous=2,ident='03-two-to-six'),triple(rabbit)])

    c=Canvas('05-value-groups')
    c.header('THE GROUPS NOW CARRY VALUES','From term 3 to term 4  •  a diagram, not individual beads')
    c.text('18 × 3 = 54',(350,250,1570,350),86,ident='operation')
    for i,x in enumerate((510,960,1410)):
        c.panel((x-180,420,x+180,660),fill=['#fff1e8','#edf5ee','#f4edf7'][i])
        c.text('VALUE',(x-150,445,x+150,492),27,MUTED,f'label-{i}')
        c.text('18',(x-150,515,x+150,625),94,COLORS[i],f'group-value-{i}')
    c.text('54',(680,735,1240,870),124,TEAL,'result')
    c.text('3 groups of 18',(650,899,1270,949),31,MUTED,'legend')
    rabbit.draw(c,'control_open',260,(1620,1040));out.append(c)

    for complete in (False,True):
        c=Canvas('07-general-formula-result' if complete else '06-general-formula-input')
        c.header('PUT A TERM NUMBER INTO THE FORMULA','A direct route to term 4')
        c.put(formula(size=88),(380,245,1540,375),'general-formula')
        boxes=[(130,460,470,590),(570,460,910,590),(1010,460,1350,590),(1450,460,1790,590)]
        labels=['n = 4','4 − 1 = 3','3 cubed = 27','2 × 27 = 54']
        for i,b in enumerate(boxes):
            c.panel((b[0]-10,b[1]-20,b[2]+10,b[3]+20),fill='#fffaf0')
            if i<2 or complete:
                if i==2:
                    c.put(power(3,3,' = 27',59),b,f'formula-step-{i}')
                else:
                    c.text(labels[i],b,43,TEAL if i==3 else INK,f'formula-step-{i}')
            else:
                c.text('?',b,56,MUTED,f'pending-step-{i}')
            if i<3:c.arrow((b[2]+24,525),(boxes[i+1][0]-24,525))
        c.lines(['27 is an intermediate value.', 'The fourth term is 54.'] if complete else ['The term number chooses the exponent.', 'The starting value is multiplied last.'],(480,675,1560,804),36,MUTED,'explanation')
        rabbit.draw(c,'follow_up',300,(370,1040));out.append(c)

    c=Canvas('08-compare-ratios');c.header('CHANGE THE MULTIPLIER','Same starting value  •  two different sequences')
    for y,r,vals in [(370,2,[2,4,8,16]),(645,3,[2,6,18,54])]:
        c.text(f'r = {r}',(170,y-50,440,y+35),60,TEAL if r==2 else CORAL,f'ratio-{r}')
        for j,v in enumerate(vals):
            x=640+j*315
            c.text(str(v),(x-115,y-65,x+115,y+65),88,ident=f'r{r}-n{j+1}')
            if j<3:c.arrow((x+127,y),(x+185,y),TEAL if r==2 else CORAL)
        c.text(f'×{r} at every step',(610,y+88,1650,y+144),31,MUTED,f'r{r}-caption')
    rabbit.draw(c,'three_way_wonder',250,(420,1045));out.append(c)

    c=Canvas('09-halving-sequence');c.header('A GEOMETRIC SEQUENCE CAN SHRINK','A new sequence  •  starting value 16  •  r = 1/2')
    c.text('16   →   8   →   4   →   2   →   1   →   1/2',(180,260,1740,390),66,ident='halving-values')
    for x,half in [(710,False),(1210,True)]:
        c.draw.ellipse((x-100,485,x+100,685),fill='#e2e4d4',outline=INK,width=3)
        if half:c.draw.pieslice((x-100,485,x+100,685),-90,90,fill=TEAL,outline=INK,width=3)
        else:c.draw.ellipse((x-100,485,x+100,685),fill=TEAL,outline=INK,width=3)
        c.text('1/2 of a whole' if half else '1 whole',(x-220,720,x+220,775),34,ident=f'whole-{half}')
    c.arrow((850,585),(1060,585));c.text('× 1/2',(845,465,1065,520),38,TEAL,'half-operator')
    c.text('Each step keeps half the previous value.',(320,828,1400,886),30,MUTED,'caption')
    rabbit.draw(c,'control_open',260,(1570,1040));out.append(c)

    out.extend([ratio_loop(rabbit,25),large(rabbit,41,'11-final-term')])
    c=Canvas('12-ending');c.header('THE SAME RATIO CONNECTS EVERY STEP','41 terms  •  40 multiplications by three')
    c.text('2   →   6   →   18   →   54   →   …',(200,260,1720,360),66,ident='recap-path')
    c.text('24,315,330,918,113,857,602',(130,425,1790,555),78,TEAL,'last-value')
    c.put(formula(size=68),(430,635,1490,740),'recap-formula')
    rabbit.draw(c,'three_way_wonder',280,(960,1050));out.append(c)
    return out


def animation(rabbit):
    """A silent equation study, not the production narration timing."""
    out=D/'mockups/formula-motion-study.mp4'
    ffmpeg=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg')
    ff=subprocess.Popen([ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
                         '-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-color_primaries','bt709',
                         '-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',str(out)],stdin=subprocess.PIPE)
    samples=[]
    for frame in range(360):
        t=frame/30; local=t%6; previous=6 if t<6 else 18; result=previous*3
        c=Canvas('motion-study')
        c.header(f'{previous} × 3 = '+(str(result) if local>=4 else '?'),'SILENT MOTION STUDY  •  timing is for preview only')
        stage=min(1,max(0,(local-.5)/2.5)); ease=stage*stage*(3-2*stage)
        # The first group starts at the source. The other equal groups move out
        # from the same source. No partially formed numerical result is shown.
        for j,target in enumerate((510,960,1410)):
            x=960+(target-960)*ease
            y=350+(520-350)*ease
            if j==0 or stage>0:
                if previous==6:
                    c.put(beads(6,COLORS[j],30,3),(x-125,y-80,x+125,y+80),f'moving-group-{j}')
                else:
                    c.panel((x-120,y-80,x+120,y+80),fill=['#fff1e8','#edf5ee','#f4edf7'][j])
                    c.text('18',(x-100,y-50,x+100,y+50),68,INK,f'moving-value-group-{j}')
            if stage>=1:
                c.text(f'GROUP {j+1}',(target-150,382,target+150,428),27,MUTED,f'completed-group-label-{j}')
        if local<5:
            c.text(str(previous),(740,235,1180,310),64,ident='input-value')
        else:
            # The completed result becomes the next input, as a whole numeral.
            p=(local-5);e=p*p*(3-2*p);y=787+(273-787)*e;x=960+800*math.sin(math.pi*p)
            size=round(138+(64-138)*e)
            c.text(str(result),(x-260,y-80,x+260,y+80),size,TEAL,'result-returning-to-input')
            c.text('The result becomes the next input.',(390,885,1530,942),33,MUTED,'feedback-caption')
        if 4<=local<5:
            c.text(str(result),(670,710,1250,865),138,TEAL,'completed-result')
            c.text('Three equal groups of '+str(previous)+'.',(520,885,1400,942),36,MUTED,'completion-caption')
        elif 3<=local<4:
            c.text(f'{previous} + {previous} + {previous}',(550,730,1370,845),72,ident='same-quantity')
        elif local<3:
            c.text('×3 makes three equal value groups',(350,760,1570,830),37,TEAL,'moving-caption')
        if previous==18:
            c.text('VALUE GROUPS  •  not individual units',(570,636,1550,690),28,MUTED,'diagram-mode')
        rabbit.draw(c,'control_ready',260,(1570,1040))
        if frame in (0,15,45,75,90,119,120,150,179,180,195,225,255,270,299,300,330,359):
            c.image.save(D/f'qa/motion-{frame:03d}.png');samples.extend(c.records)
        ff.stdin.write(c.image.convert('RGB').tobytes())
    ff.stdin.close(); assert ff.wait()==0
    return samples


def main():
    global TERMS
    data=json.loads((D/'math/sequence.json').read_text())
    TERMS=data['terms'] if isinstance(data,dict) else data
    (D/'mockups').mkdir(exist_ok=True);(D/'qa').mkdir(exist_ok=True)
    rabbit=Rabbit(); rendered=scenes(rabbit);records=[];occlusions=[]
    def check_occlusion(c):
        char=next(r for r in c.records if r['component_id']=='rabbit')
        a=char['visible_box_xyxy'];hits=[]
        for row in c.records:
            if row is char:continue
            b=row['visible_box_xyxy']
            area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            if area:hits.append({'component_id':row['component_id'],'intersection_area_px2':area})
        occlusions.append({'scene':c.ident,'method':'actual visible foreground bounding-box intersections; conservative extent check',
                           'character_visible_box':a,'unintended_intersections':hits,'passed':not hits})
        assert not hits,(c.ident,hits)
    sheet=Image.new('RGB',(1920,4*390),'#f1e7d7')
    sd=ImageDraw.Draw(sheet)
    for i,c in enumerate(rendered):
        p=D/f'mockups/{c.ident}.png';c.image.convert('RGB').save(p)
        records.extend(c.records)
        check_occlusion(c)
        thumb=c.image.convert('RGB').resize((640,360),Image.Resampling.LANCZOS)
        x=(i%3)*640;y=(i//3)*390
        sheet.paste(thumb,(x,y));sd.text((x+18,y+364),c.ident,font=font(18),fill=INK)
    sheet.save(D/'mockups/storyboard.png');sheet.resize((1440,1170),Image.Resampling.LANCZOS).save(D/'mockups/storyboard-preview.jpg',quality=92)
    # Fixed large-number layouts are checked for every main term, including
    # shortest, longest, carry boundaries and long multi-line English readings.
    for n in range(2,42):
        c=large(rabbit,n);records.extend(c.records);check_occlusion(c)
    for n in range(5,33):
        c=ratio_loop(rabbit,n);records.extend(c.records);check_occlusion(c)
    records.extend(animation(rabbit))
    assert all(x['passed'] for x in records)
    bg=Image.open(BG)
    quality=dict(stage='preproduction_only',not_finished_episode_qa=True,
                 background=dict(path=str(BG.relative_to(ROOT)),sha256=sha(BG),native_size_px=list(bg.size),
                                 maximum_display_px=[W,H],scale=max(W/bg.width,H/bg.height),
                                 reason='Intentionally soft peripheral watercolor; precise math is separate native raster.',
                                 final_compressed_video_quality='not_yet_tested'),
                 character_sources=rabbit.used,model_name='not_disclosed_by_tool',
                 generated_assets='built-in image_gen',typography_font=str(FONT.relative_to(ROOT)),
                 alignment_observations=len(records),all_observations_passed=True,
                 motion_study=dict(seconds=12,fps=30,frames=360,audio=False,
                                   scope='6 to 18 to 54: equal groups, delayed result, return to input, symbolic mode. Character is a held operation pose.',
                                   not_production_timing=True,not_character_motion_acceptance=True))
    (D/'qa/mockup-alignment.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    (D/'qa/character-teaching-occlusion.json').write_text(json.dumps(occlusions,ensure_ascii=False,indent=2)+'\n')
    counts=[]
    for n in (2,6):
        mask=beads(n).getchannel('A').point(lambda a:255 if a>=128 else 0);actual=0
        while (b:=mask.getbbox()) is not None:
            y=b[1];x=next(x for x in range(b[0],b[2]) if mask.getpixel((x,y)))
            ImageDraw.floodfill(mask,(x,y),0);actual+=1
        counts.append({'individual_group_expected':n,'foreground_connected_components':actual,
                       'three_groups_total':3*actual,'passed':actual==n})
        assert actual==n
    (D/'qa/exact-bead-counts.json').write_text(json.dumps(counts,indent=2)+'\n')
    (D/'qa/mockup-manifest.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'frames':len(rendered),'alignment_observations':len(records),'passed':True,'storyboard':str(D/'mockups/storyboard.png')}))


if __name__=='__main__':main()
