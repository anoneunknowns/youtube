from pathlib import Path
import sys
root=Path(__file__).resolve().parents[6]
sys.path.insert(0,str(root))
import json,hashlib
from PIL import Image,ImageDraw,ImageFont
from tools.register_character_expansion import cells
from tools.component_alignment import raster_centering_report
root=Path(__file__).resolve().parents[6]
idx=json.loads((root/'catalogs/character-library-v1.json').read_text())
chars=[c for c in idx['characters'] if c['id']!='bear-beret']
W,H=1520,2360
page=Image.new('RGB',(W,H),'#fff8e8')
d=ImageDraw.Draw(page)
fontpath=root/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
title=ImageFont.truetype(str(fontpath),34);label=ImageFont.truetype(str(fontpath),23);small=ImageFont.truetype(str(fontpath),17)
d.text((30,18),'キャラクター表情・動作拡充　10種類 × 27姿勢',font=title,fill='#63390d')
d.text((30,65),'採用通常姿 ／ 考える ／ 手振り ／ 座った伸び　（一覧用の縮小表示）',font=label,fill='#63390d')
reports=[]
for n,c in enumerate(chars):
 x0=(n%2)*760;y0=120+(n//2)*448
 d.rounded_rectangle((x0+12,y0+4,x0+748,y0+436),radius=20,fill='#f3e8d4')
 d.text((x0+30,y0+15),c['name_ja'],font=label,fill='#63390d')
 canonical=c['neutral'];im=Image.open(root/canonical['path']).crop(canonical['image_region_px'])
 pics=[('採用通常姿',im,'canonical')]
 for group,pose,ja in [('reactions','think','考える'),('actions','wave_high_in','手振り'),('postures','seated_stretch','座った伸び')]:
  _,fs=cells(root/'assets/library/characters'/c['id']/'motions/v002/source-sheets'/(group+'.png'),group)
  fr=next(f for f in fs if f['id']==pose);pics.append((ja,fr['image'],pose))
 for j,(ja,im,pose) in enumerate(pics):
  box=(x0+24+j*180,y0+62,x0+194+j*180,y0+390)
  b=im.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox();crop=im.crop(b)
  scale=min((box[2]-box[0]-8)/crop.width,(box[3]-box[1]-8)/crop.height)
  spr=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))),Image.Resampling.LANCZOS)
  actual=spr.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox()
  x=round((box[0]+box[2]-actual[0]-actual[2])/2);y=round((box[1]+box[3]-actual[1]-actual[3])/2)
  layer=Image.new('RGBA',(W,H),0);layer.alpha_composite(spr,(x,y))
  r=raster_centering_report(layer,box,name=c['id']+'/'+pose,alpha_threshold=8)
  assert r['passed'],r
  reports.append(r)
  page.paste(Image.alpha_composite(page.convert('RGBA'),layer).convert('RGB'))
  d=ImageDraw.Draw(page);d.text((box[0],y0+400),ja,font=small,fill='#63390d')
page.save(str(root/'character-expansion-overview.png'))
Path(str(root/'character-expansion-overview-alignment.json')).write_text(json.dumps({'status':'pass','scope':'40 overview illustrations. Centering is for contact-sheet comparison only; actual playback uses registered support and sheet calibration. Labels are left aligned.','resolution_px':[W,H],'alpha_threshold':8,'tolerance_px':.5,'records':reports},ensure_ascii=False,indent=2)+'\n')
print('overview created; all40 image components centered on both axes')
