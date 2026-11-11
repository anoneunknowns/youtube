from pathlib import Path
import json,sys
from PIL import Image,ImageDraw,ImageFont
root=Path.cwd()
if not (root/'catalogs/character-library-v1.json').exists():root=Path(__file__).resolve().parents[6]
sys.path.insert(0,str(root))
from tools.register_character_eyecatches import cells,TARGETS,GROUPS
from tools.component_alignment import raster_centering_report
out=Path(sys.argv[1]) if len(sys.argv)>1 else root/'eyecatch-overview.png'
if out.exists():raise FileExistsError(out)
idx={c['id']:c for c in json.loads((root/'catalogs/character-library-v1.json').read_text())['characters']}
W,H=1520,1912;page=Image.new('RGB',(W,H),'#fff8e8');d=ImageDraw.Draw(page)
fp=root/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
title=ImageFont.truetype(str(fp),34);label=ImageFont.truetype(str(fp),23);small=ImageFont.truetype(str(fp),18)
d.text((30,18),'アイキャッチ素材　紅茶・ジャンプ・おじぎ・ダンス',font=title,fill='#63390d')
d.text((30,65),'8キャラクター ／ 32動作 ／ 144姿勢　（一覧用の縮小表示）',font=label,fill='#63390d')
reports=[];source=[]
for n,id in enumerate(TARGETS):
 c=idx[id];x0=n%2*760;y0=120+n//2*448
 d.rounded_rectangle((x0+12,y0+4,x0+748,y0+436),radius=20,fill='#f3e8d4')
 d.text((x0+30,y0+15),c['name_ja'],font=label,fill='#63390d')
 allframes={}
 for group in GROUPS:
  p=root/'assets/library/characters'/id/'eyecatches/v001/source-sheets'/(group+'.png')
  detail,fs=cells(p,group);allframes.update({f['id']:f for f in fs})
  source.append({'id':id,'group':group,'size_px':detail['size_px'],'sha256':detail['sha256'],'frames':[{'id':f['id'],'visible_bbox_px':f['visible_bbox_px'],'margins_px':f['visible_alpha8_margins_px']} for f in fs]})
 for j,(pose,ja) in enumerate([('tea_sip','紅茶'),('jump_air','ジャンプ'),('bow_deep','おじぎ'),('dance_finish','ダンス')]):
  f=allframes[pose];im=f['image'];box=(x0+24+j*180,y0+62,x0+194+j*180,y0+390)
  crop=im.crop(f['visible_bbox_px']);scale=min((box[2]-box[0]-8)/crop.width,(box[3]-box[1]-8)/crop.height)
  spr=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))),Image.Resampling.LANCZOS)
  b=spr.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox()
  x=round((box[0]+box[2]-b[0]-b[2])/2);y=round((box[1]+box[3]-b[1]-b[3])/2)
  layer=Image.new('RGBA',(W,H),0);layer.alpha_composite(spr,(x,y))
  r=raster_centering_report(layer,box,name=id+'/'+pose,alpha_threshold=8);assert r['passed'],r;reports.append(r)
  page=Image.alpha_composite(page.convert('RGBA'),layer).convert('RGB');d=ImageDraw.Draw(page);d.text((box[0],y0+400),ja,font=small,fill='#63390d')
page.save(out)
out.with_suffix('.alignment.json').write_text(json.dumps({'status':'pass','scope':'32 centered overview illustrations, both axes measured. Labels left aligned. Actual motion playback uses fixed support and calibrated sheet scale.','alpha_threshold':8,'tolerance_px':.5,'resolution_px':[W,H],'records':reports},ensure_ascii=False,indent=2)+'\n')
out.with_suffix('.sources.json').write_text(json.dumps({'status':'pass','source_sheets':16,'pose_cells':144,'alpha_threshold':8,'minimum_allowed_margin_px':2,'records':source},ensure_ascii=False,indent=2)+'\n')
print('144 source cells pass; 32 overview illustrations centered on both axes')
