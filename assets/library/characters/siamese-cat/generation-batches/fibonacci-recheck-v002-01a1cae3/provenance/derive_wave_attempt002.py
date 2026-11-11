from PIL import Image,ImageDraw,ImageFilter,ImageChops
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[7];B=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.relative_to(ROOT).as_posix()
def bounds(im):
 d=im.getchannel('R');
 for c in ['G','B','A']:d=ImageChops.lighter(d,im.getchannel(c))
 return d.getbbox()
reg=json.loads((B/'registration.json').read_text());sheet=Image.open(B/'source/pose-sheet-attempt002.png').convert('RGBA');neutralp=ROOT/'assets/library/characters/siamese-cat/sources/v005/neutral.png';base=Image.open(neutralp).convert('RGBA')
new=[]
for i,id in enumerate(['wave_prepare','wave_in','wave_out']):
 rect=[i*724,0,(i+1)*724,724];src=sheet.crop(rect);srcp=B/'candidates'/f'{id}-attempt002.png';src.save(srcp)
 scale=1070/654;offset=[77,40];aligned=Image.new('RGBA',base.size);rs=src.resize((round(src.width*scale),round(src.height*scale)),Image.Resampling.LANCZOS);aligned.paste(rs,tuple(offset))
 polygon=[[720,620],[975,560],[1000,750],[925,850],[900,960],[840,1090],[735,1090]]
 mask=Image.new('L',base.size);ImageDraw.Draw(mask).polygon(polygon,fill=255);mask=mask.filter(ImageFilter.GaussianBlur(4))
 protect=Image.new('L',base.size);pd=ImageDraw.Draw(protect);pd.rectangle((0,0,1280,710),fill=255);pd.polygon([(923,690),(1100,690),(1100,1100),(788,1100),(790,1035),(842,1035),(885,980),(905,900),(916,820)],fill=255)
 protect=ImageChops.multiply(protect,base.getchannel('A').point(lambda a:255 if a>0 else 0));mask=ImageChops.subtract(mask,protect)
 result=Image.composite(aligned,base,mask);p=B/'frames'/f'{id}-attempt002.png';result.save(p)
 new.append({'id':id,'path':rel(p),'sha256':sha(p),'anchor_px':[611,1189],'reference_height_px':1070,'eyes_closed':False,'base_path':rel(neutralp),'base_sha256':sha(neutralp),'source_path':rel(srcp),'source_sha256':sha(srcp),'crop_from_sheet_xyxy':rect,'raw_source_body_reference_height_px':654,'raw_source_anchor_px':[343.5,702],'derivation':{'kind':'local-generated-right-forepaw-overlay','source_to_base':{'scale':scale,'translate_xy':offset},'replace_polygon_xy':polygon,'feather_px':4,'protected_regions':'Original nonzero-alpha head including whiskers y<=710; original anatomical tail polygon. Both feet and left arm unchanged.'},'changed_bounds_rgba_all_channels':bounds(ImageChops.difference(result,base)),'size_px':list(result.size)})
reg['source_sheet_attempt002']={'path':rel(B/'source/pose-sheet-attempt002.png'),'sha256':sha(B/'source/pose-sheet-attempt002.png'),'size_px':list(sheet.size),'grid':[3,1]};reg['frames']=new+reg['frames'][3:];(B/'registration-attempt002.json').write_text(json.dumps(reg,indent=2)+'\n')
canvas=Image.new('RGB',(4*440,530),'#cbdedb');d=ImageDraw.Draw(canvas)
for i,(id,im) in enumerate([('neutral',base),*[(f['id'],Image.open(ROOT/f['path']).convert('RGBA')) for f in new]]):
 s=400/1070;rs=im.resize((round(im.width*s),round(im.height*s)),Image.Resampling.LANCZOS);canvas.paste(rs,(round(i*440+215-611*s),round(470-1189*s)),rs);d.text((i*440+10,10),id,fill='#253f42');d.line((i*440,470,i*440+440,470),fill='#7a9999')
canvas.save(B/'previews/wave-attempt002-native.png')
