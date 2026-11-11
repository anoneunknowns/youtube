"""Check each digit cell separately around four late carry boundaries."""
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image,ImageChops,ImageDraw,ImageFont

ROOT=Path('D:/codex_projects/youtube')
OUT=Path(__file__).parent/'additional'
proof=json.loads((OUT/'additional-visual-checks.json').read_text(encoding='utf-8'))
face=ImageFont.truetype(str(ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'),118)
rows=[('binary',2,248,423),('decimal',10,443,618),('octal',8,638,813),('hexadecimal',16,833,1008)]

def digits(value,base):
    if value==0:return '0'
    result=''
    while value:
        value,rem=divmod(value,base)
        result='0123456789ABCDEF'[rem]+result
    return result

def inkbox(symbol):
    mask,offset=face.getmask2(symbol,mode='L',anchor='ls')
    bbox=mask.getbbox()
    return tuple(bbox[i]+offset[i%2] for i in range(4))

def mask(image):
    return image.convert('L').point(lambda px:255 if px<137 else 0)

def similarity(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 1

@lru_cache(maxsize=200)
def expected(symbol,row,index):
    row_name,_,top,bottom=rows[row]
    center=1315-104*(7-index)
    crop=(center-52,top+20,center+52,bottom-16)
    im=Image.new('RGB',(104,crop[3]-crop[1]),'#fff0de' if row_name=='decimal' else '#fff8e8')
    if symbol!=' ':
        zero=inkbox('0')
        baseline=round((top+bottom)/2-(zero[1]+zero[3])/2)
        left,_,right,_=inkbox(symbol)
        origin=round(center-(left+right)/2)
        ImageDraw.Draw(im).text((origin-crop[0],baseline-crop[1]),symbol,font=face,fill='#51341f',anchor='ls')
    return mask(im)

records=[]
errors=[]
minimum=1
nonblank=blank=0
guard=None
for probe in proof['probes']:
    if probe['group']!='boundary':continue
    value=probe['expected_decimal_value']
    with Image.open(probe['path']) as im:
        for row,(row_name,base,top,bottom) in enumerate(rows):
            text=digits(value,base).rjust(8)
            for slot,symbol in enumerate(text):
                center=1315-104*(7-slot)
                actual=mask(im.crop((center-52,top+20,center+52,bottom-16)))
                target=expected(symbol,row,slot)
                score=similarity(actual,target)
                if symbol==' ':
                    blank+=1
                    passed=actual.histogram()[255]==0
                else:
                    nonblank+=1
                    minimum=min(minimum,score)
                    passed=score>=.97
                rec={'frame':probe['frame'],'decimal_value':value,'row':row_name,'slot_left_to_right':slot,
                     'expected_symbol':symbol,'iou':round(score,8),'passed':passed}
                records.append(rec)
                if not passed:errors.append(rec)
                if guard is None and row_name=='binary' and symbol=='0':
                    wrong=similarity(actual,expected('1',row,slot))
                    guard={'frame':probe['frame'],'actual_symbol':'0','deliberately_wrong_expected_symbol':'1',
                           'wrong_symbol_iou':wrong,'rejected':wrong<.97}
assert guard and guard['rejected']
report={'status':'pass' if not errors else 'fail','method':'Repeated integer division and independent font rendering; no production renderer or verifier imports.',
        'boundaries':[[127,128],[159,160],[191,192],[199,200]],'frames':20,'cells':len(records),'nonblank_cells':nonblank,'empty_cells':blank,
        'minimum_nonblank_cell_iou':minimum,'minimum_required_iou':.97,'guard':guard,'errors':errors,'results':records}
(OUT/'per-symbol-cells.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({key:report[key] for key in ['status','frames','cells','nonblank_cells','empty_cells','minimum_nonblank_cell_iou','guard','errors']}))
raise SystemExit(bool(errors))
