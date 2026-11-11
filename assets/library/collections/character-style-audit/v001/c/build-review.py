from pathlib import Path
import json,math
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('/Users/support/codex/youtube');OUT=ROOT/'output/character-style-audit-v001/c'
index=json.loads((ROOT/'catalogs/character-library-v1.json').read_text());ids=['bear-beret','rabbit-beret','little-bird','fairy-pitta','onagadori'];manifest=[]
for c in index['characters']:
 if c['id'] not in ids:continue
 n=c['neutral'];orig=Image.open(ROOT/n['path']).crop(n['image_region_px']);anchor=[n['anchor_px'][0]-n['image_region_px'][0],n['anchor_px'][1]-n['image_region_px'][1]];neutral={'id':'CANONICAL','image':orig,'anchor_px':anchor,'reference_height_px':n['reference_height_px']}
 for block in ['expanded_key_poses','eyecatch_key_poses']:
  if block not in c:continue
  r=json.loads((ROOT/c[block]['registration']).read_text())
  for sheet in r['sheets']:
   frames=[neutral]+[{**f,'image':Image.open(ROOT/f['path'])} for f in r['frames'] if f['sheet_id']==sheet['id']]
   target=280;scaled=[];l=t=rr=b=0
   for f in frames:
    im=f['image'];vb=im.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox();scale=target/f['reference_height_px'];sprite=im.crop(vb).resize((max(1,round((vb[2]-vb[0])*scale)),max(1,round((vb[3]-vb[1])*scale))),Image.Resampling.LANCZOS);off=[round((vb[0]-f['anchor_px'][0])*scale),round((vb[1]-f['anchor_px'][1])*scale)];scaled.append((f['id'],sprite,off));l=min(l,off[0]);t=min(t,off[1]);rr=max(rr,off[0]+sprite.width);b=max(b,off[1]+sprite.height)
   tw,th=rr-l+60,b-t+95;cols=2 if c['id']=='onagadori' else 5;rows=math.ceil(len(frames)/cols);support=[30-l,55-t]
   for mode,bg in [('light','#fff8e8'),('dark','#203b3e')]:
    page=Image.new('RGB',(tw*cols,th*rows),bg)
    for i,(id,sp,off) in enumerate(scaled):
     tile=Image.new('RGBA',(tw,th),bg);tile.alpha_composite(sp,(support[0]+off[0],support[1]+off[1]));ImageDraw.Draw(tile).text((8,10),id,fill='#63390d' if mode=='light' else '#fff8e8');page.paste(tile.convert('RGB'),(i%cols*tw,i//cols*th))
    name=c['id']+'-'+block+'-'+sheet['id']+'-'+mode+'.jpg';page.save(OUT/name,quality=95);manifest.append({'id':c['id'],'block':block,'sheet':sheet['id'],'mode':mode,'path':str((OUT/name).relative_to(ROOT)),'poses':[f['id'] for f in frames],'target_body_height':target,'placement':'shared anatomical support; not centered','resolution':[page.width,page.height]})
(OUT/'review-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(len(manifest),'pages',sum(len(x['poses'])-1 for x in manifest if x['mode']=='light'),'newposes')
