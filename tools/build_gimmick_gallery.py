"""Build derived gallery cards for the explicitly selected background gimmicks.

Only the gallery HTML, overview, thumbnails and gallery QA are written. Adopted
art, registrations, collection manifests and shared catalogs are never edited.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import quote
import uuid

from PIL import Image, ImageDraw, ImageFont

sys.dont_write_bytecode = True
try:
    from .component_alignment import raster_centering_report
except ImportError:
    from component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = 'assets/library/collections/background-gimmicks/v001'
MANIFEST = COLLECTION + '/manifest.json'
FONT = 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
IDS = ['grass', 'flower-bed', 'airplane', 'rocket', 'helicopter', 'butterfly', 'ladybug', 'rainbow']
LIMITS = {
    'grass': (600, 'neutral patch width', 'visible-width'),
    'flower-bed': (520, 'neutral flower-bed width', 'visible-width'),
    'airplane': (360, 'full level airplane width', 'visible-width'),
    'rocket': (300, 'anatomical body height, excluding flame', 'anatomical-height'),
    'helicopter': (500, 'physical unforeshortened rotor span', 'conservative-canvas-width'),
    'butterfly': (200, 'fully open wingspan', 'visible-width'),
    'ladybug': (140, 'neutral shell width, excluding legs', 'anatomical-width'),
    'rainbow': (1200, 'complete arch width', 'visible-width'),
}


def safe(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts):
        raise ValueError(f'Expected a project-relative path: {relative}')
    path = root
    for part in PurePosixPath(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f'Gallery paths cannot contain symlinks: {relative}')
    return path


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def source(root, relative, guards, expected=None):
    path = safe(root, relative)
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f'Source changed during reading: {relative}')
    observed = checksum(data)
    if expected is not None and observed != expected:
        raise ValueError(f'Selected source hash differs: {relative}')
    if guards.setdefault(relative, observed) != observed:
        raise ValueError(f'Source changed during gallery preparation: {relative}')
    return data


def document(root, relative, guards, expected=None):
    return json.loads(source(root, relative, guards, expected).decode('utf-8-sig'))


def png(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def centered(layer, size, content, name):
    bounds = layer.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
    if bounds is None:
        raise ValueError(f'Empty gallery target: {name}')
    target = ((content[0] + content[2]) / 2, (content[1] + content[3]) / 2)
    offset = (round(target[0] - (bounds[0] + bounds[2]) / 2),
              round(target[1] - (bounds[1] + bounds[3]) / 2))
    result = Image.new('RGBA', size, (0, 0, 0, 0))
    result.alpha_composite(layer, offset)
    report = raster_centering_report(result, content, name=name, tolerance_px=.5, alpha_threshold=8)
    report.update(horizontal_intent='center of actual visible ink', vertical_intent='center of actual visible ink')
    report['not_clipped'] = report['contained'] and not report['touches_measurement_edge']
    if not report['passed']:
        raise ValueError(f'Gallery target failed both-axis alignment: {report}')
    return result, report


def caption(name, identity, pose_count, clip_count, fonts):
    group = Image.new('RGBA', (320, 74), (0, 0, 0, 0))
    draw = ImageDraw.Draw(group)
    pose_word = 'pose' if pose_count == 1 else 'poses'
    lines = [(name, fonts[27], 1), (f'{identity} / {pose_count} {pose_word} / {clip_count} clips', fonts[14], 42)]
    for text, font, top in lines:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((round(160 - (box[0] + box[2]) / 2), top - box[1]), text,
                  font=font, fill=(70, 45, 29, 255))
    return centered(group, (320, 74), (8, 4, 312, 70), identity+'/caption-group')


def thumbnail(image, identity, neutral):
    alpha = image.getchannel('A')
    visible = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
    if visible is None:
        raise ValueError(f'Empty adopted neutral: {identity}')
    width, height = visible[2]-visible[0], visible[3]-visible[1]
    limit, dimension, basis = LIMITS[identity]
    anatomy = neutral.get('anatomical_body_bbox_px', visible)
    native_basis = (anatomy[3]-anatomy[1] if basis=='anatomical-height' else
                    anatomy[2]-anatomy[0] if basis=='anatomical-width' else
                    image.width if basis=='conservative-canvas-width' else width)
    scale = min(1, 296/width, 192/height, limit/native_basis)
    cropped = image.crop(visible)
    resized = cropped.resize((max(1, math.floor(width*scale)), max(1, math.floor(height*scale))),
                             Image.Resampling.LANCZOS)
    actual_scale = max(resized.width/width, resized.height/height)
    result, report = centered(resized, (320, 216), (12, 12, 308, 204), identity+'/neutral')
    output_bounds = report['visible_box_xyxy']
    rendered_basis = (output_bounds[2]-output_bounds[0] if basis=='visible-width' else native_basis*actual_scale)
    flags = {'native_scale_at_most_one': actual_scale <= 1,
             'within_recommended_maximum': rendered_basis <= limit + .5,
             'maximum_recommended_value_px': limit, 'maximum_recommended_dimension': dimension,
             'rendered_dimension_or_conservative_bound_px': rendered_basis,
             'measurement_basis': basis}
    if not all(flags[key] for key in ('native_scale_at_most_one','within_recommended_maximum')):
        raise ValueError(f'Thumbnail violates native/display limit: {identity}')
    report.update(source_canvas_px=list(image.size), source_visible_box_alpha8=list(visible),
                  source_native_visible_size_px=[width,height], derivative_scale=actual_scale,
                  source_has_visible_margin=min(visible[0],visible[1],image.width-visible[2],image.height-visible[3])>=2,
                  independent_neutral_card=True, animation_pose_bbox_fitting=False,
                  maximum_display_flags=flags)
    return result, report


def relative_link(target):
    return quote(os.path.relpath(target, COLLECTION), safe='/.-_')


def atomic_output(root, relative, data):
    if not relative.startswith(COLLECTION + '/') or relative == MANIFEST:
        raise ValueError('Gallery output may not replace a source or manifest')
    path = safe(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(root=ROOT):
    root = Path(root).resolve()
    guards = {}
    collection = document(root, MANIFEST, guards)
    selected = {item['id']:item for item in collection['items']}
    if set(selected) != set(IDS) or len(collection['items']) != 8:
        raise ValueError('Gallery requires the eight explicitly selected gimmicks')
    font_data = source(root, FONT, guards)
    fonts = {size:ImageFont.truetype(io.BytesIO(font_data), size) for size in (14,22,27,42)}
    overview = Image.new('RGBA', (1484, 900), (244, 241, 231, 255))
    outputs, records, links, cards = {}, [], [], []
    for text, size, box in [('背景の小さな動き',42,(32,18,1452,74)),
                            ('草・花壇・乗り物・虫・虹  /  8 assets',22,(32,78,1452,112))]:
        layer=Image.new('RGBA',overview.size,(0,0,0,0));d=ImageDraw.Draw(layer)
        d.text((0,0),text,font=fonts[size],fill=(65,42,26,255))
        layer,record=centered(layer,overview.size,box,'overview/header/'+str(size))
        overview.alpha_composite(layer);records.append(record)
    for i,identity in enumerate(IDS):
        item=selected[identity]
        manifest=document(root,item['source_manifest_path'],guards,item['source_manifest_sha256'])
        registration=document(root,item['registration'],guards,item['registration_sha256'])
        render=manifest['render_registration']
        neutral_path=render['neutral_path']
        if not neutral_path.startswith('assets/'):
            neutral_path=(PurePosixPath(item['source_manifest_path']).parent/neutral_path).as_posix()
        data=source(root,neutral_path,guards,render['neutral_sha256'])
        with Image.open(io.BytesIO(data)) as opened:
            if opened.mode!='RGBA':raise ValueError('Adopted neutral must retain RGBA')
            image=opened.copy()
        neutral_id=registration['canonical_neutral']['frame_id']
        neutral=next(frame for frame in registration['frames'] if frame['id']==neutral_id)
        thumb,report=thumbnail(image,identity,neutral);report.update(source_path=neutral_path,source_sha256=checksum(data));records.append(report)
        cap,report=caption(item['name_ja'],identity,len(registration['frames']),len(registration['clips']),fonts);records.append(report)
        outputs[COLLECTION+f'/thumbnails/{identity}.png']=png(thumb)
        outputs[COLLECTION+f'/thumbnails/{identity}-caption.png']=png(cap)
        x=32+(i%4)*360;y=132+(i//4)*368
        ImageDraw.Draw(overview).rounded_rectangle((x,y,x+340,y+344),radius=18,fill=(255,254,249,255),outline=(224,216,199,255),width=2)
        overview.alpha_composite(thumb,(x+10,y+10));overview.alpha_composite(cap,(x+10,y+234))
        clip_links=[]
        for name,clip in registration['clips'].items():
            path=clip.get('preview')
            if not path:
                path=(PurePosixPath(item['registration']).parent/(name+'.gif')).as_posix()
            source(root,path,guards,clip.get('preview_sha256'))
            links.append({'asset':identity,'kind':'clip','name':name,'path':path,'exists':True})
            clip_links.append('<figure><a href="'+relative_link(path)+'"><img loading="lazy" src="'+relative_link(path)+'" alt="'+html.escape(item['name_ja']+' / '+name)+'"></a><figcaption>'+html.escape(name)+'</figcaption></figure>')
        references=[('姿勢一覧',item['preview']),('動作まとめ',item['motion_preview']),('登録情報',item['registration']),
                    ('原画・生成条件',item['source_manifest_path']),('共通 asset.json',f'assets/library/characters/{identity}/current/asset.json')]
        for title,path in references:
            exists=safe(root,path).is_file()
            if not exists:raise ValueError(f'Missing gallery link: {path}')
            links.append({'asset':identity,'kind':title,'path':path,'exists':exists})
        nav=' · '.join('<a href="'+relative_link(path)+'">'+html.escape(title)+'</a>' for title,path in references)
        limit=LIMITS[identity]
        cards.append('<article><img class="neutral" src="thumbnails/'+identity+'.png" width="320" height="216" alt="'+html.escape(item['name_ja'])+'"><h2><img src="thumbnails/'+identity+'-caption.png" width="320" height="74" alt="'+html.escape(item['name_ja']+' / '+identity)+'"></h2><p class="limit">表示の目安：'+str(limit[0])+'px — '+html.escape(limit[1])+'</p><p class="links">'+nav+'</p><details><summary>動作GIFを見る</summary><div class="clips">'+''.join(clip_links)+'</div></details></article>')
    outputs[COLLECTION+'/overview.png']=png(overview.convert('RGB'))
    markup='''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>背景の小さな動き — Num-Num Numbers</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f1e7;color:#432d20;font-family:system-ui,sans-serif;line-height:1.65}header,main,footer{max-width:1480px;margin:auto;padding:28px}h1{font-size:2rem;margin:0 0 8px}.intro{max-width:850px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:22px}article{background:#fffef9;border:1px solid #ded5c3;border-radius:18px;padding:16px;overflow:hidden}.neutral,h2 img{display:block;max-width:100%;height:auto;margin:auto}h2{margin:0}.limit{font-size:.85rem;color:#705c46}.links{font-size:.9rem}a{color:#69502a;text-underline-offset:3px}details{border-top:1px solid #e9e1d1;padding-top:12px}summary{cursor:pointer}.clips{display:grid;gap:14px;margin-top:14px}figure{margin:0}figure img{display:block;width:100%;height:auto;border-radius:8px}figcaption{font-size:.85rem}.notice{font-size:.92rem}footer{font-size:.85rem}@media(max-width:420px){header,main,footer{padding:16px}.grid{grid-template-columns:1fr}article{padding:12px}}
</style></head><body><header><h1>背景の小さな動き</h1><p class="intro">草、花壇、飛行機、ロケット、ヘリコプター、蝶、てんとう虫、虹。キャラクターと合わせる水彩の背景素材です。各カードから実際の動作GIFと登録情報を確認できます。</p><p><a href="overview.png">8種類の一覧PNG</a> · <a href="../../../../../catalogs/asset-library-current-v1.json">新旧19種類の共通台帳</a> · <a href="qa-evidence/gallery-alignment-v001.json">一覧の配置検査</a></p><p class="notice">画像は一覧表示用の派生サムネイルです。実際の動作では登録済みの身体基準と支点を使い、姿勢や翼・炎・ローターの外接矩形へ個別に合わせません。数字・字幕との余白、補間、場面内の動作は作品ごとに確認してください。</p></header><main><div class="grid">'''+''.join(cards)+'''</div></main><footer>原画の画素・透過と過去の採用を保全した素材集です。素材ごとの生成条件、確認範囲と表示上限は登録資料を参照してください。</footer></body></html>'''
    outputs[COLLECTION+'/index.html']=markup.encode('utf-8')
    for relative,expected in guards.items():
        if checksum(safe(root,relative).read_bytes())!=expected:
            raise ValueError(f'Input changed before gallery publication: {relative}')
    qa={'schema_version':1,'kind':'gimmick-gallery-raster-alignment','status':'pass',
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'assets':len(IDS),'cards':len(IDS),
        'pose_count':sum(len(document(root,selected[x]['registration'],guards)['frames']) for x in IDS),
        'clip_links':sum(row['kind']=='clip' for row in links),'alpha_threshold':8,'tolerance_px':.5,
        'records':records,'links':links,'source_hashes_before_after':guards,
        'source_artwork_modified':False,'independent_neutral_thumbnails_only':True,
        'scope':'Thumbnail/caption/overview raster alignment and explicit local links; browser responsive flow and completed-video quality are separate.',
        'outputs':[{'path':path,'sha256':checksum(data),'bytes':len(data)} for path,data in outputs.items()]}
    outputs[COLLECTION+'/qa-evidence/gallery-alignment-v001.json']=(json.dumps(qa,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    for relative,data in outputs.items():atomic_output(root,relative,data)
    return {'status':'pass','assets':8,'poses':qa['pose_count'],'clip_links':qa['clip_links'],
            'alignment_records':len(records),'index':COLLECTION+'/index.html','overview':COLLECTION+'/overview.png'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args(argv)
    try:
        print(json.dumps(build(args.root),ensure_ascii=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Gimmick gallery failed: {error}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
