from collections import deque
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw

ROOT = Path('D:/codex_projects/youtube')
OUT = ROOT / 'output/odd-counting-001-v002'
VIDEO = OUT / 'paspla-studio-odd-numbers-1-to-299-1080p.mp4'
DEST = ROOT / 'design/odd-counting-v1/production-qa/v002-recheck-20261111/content'
plan = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8'))
teach = {s['decimal_value']: s['teaching'] for s in plan['scenes'] if 'teaching' in s}
points = [(1, 6.2), (5, 15.0), (9, teach[9]['start_s'] + 2), ('99-to-101', teach[101]['start_s'] + 2)]
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
rows = []
for name, at in points:
    frame = math.ceil(at * 30 - 1e-7)
    path = DEST / f'teaching-{name}.png'
    subprocess.run([shutil.which('ffmpeg'), '-hide_banner', '-v', 'error', '-n', '-ss', f'{frame/30:.9f}',
                    '-i', str(VIDEO), '-frames:v', '1', '-update', '1', str(path)], check=True)
    row = {'name': name, 'frame_index': frame, 'time_s': frame / 30, 'path': path.relative_to(ROOT).as_posix(),
           'sha256': sha(path)}
    if isinstance(name, int):
        with Image.open(path) as source:
            crop = source.convert('RGB').crop((120, 735, 1340, 838))
        components = {}
        for label, target in [('paired-green', (220,233,221)), ('left-over-amber', (243,207,145))]:
            pixels = crop.load()
            mask = {(x,y) for y in range(crop.height) for x in range(crop.width)
                    if all(abs(a-b) <= 8 for a,b in zip(pixels[x,y], target))}
            groups = []
            while mask:
                start = mask.pop()
                group, queue = [start], deque([start])
                while queue:
                    x,y = queue.popleft()
                    for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                        if point in mask:
                            mask.remove(point)
                            group.append(point)
                            queue.append(point)
                if len(group) >= 500:
                    groups.append({'pixels':len(group),
                                   'bounds_px':[120+min(p[0] for p in group),735+min(p[1] for p in group),
                                                121+max(p[0] for p in group),736+max(p[1] for p in group)]})
            components[label] = sorted(groups, key=lambda g: (g['bounds_px'][0],g['bounds_px'][1]))
        row['detected_ticket_components'] = components
        row['correct_quantity'] = len(components['paired-green']) == name-1 and len(components['left-over-amber']) == 1
        row['paired_columns'] = len({round((g['bounds_px'][0]+g['bounds_px'][2])/2) for g in components['paired-green']})
        row['correct_pairs_plus_one'] = row['correct_quantity'] and row['paired_columns'] == (name-1)//2
    rows.append(row)
sheet = Image.new('RGB',(1280,760),'#fff8e8')
for index, row in enumerate(rows):
    with Image.open(ROOT / row['path']) as im:
        sheet.paste(im.resize((640,360)),((index%2)*640,(index//2)*380))
    ImageDraw.Draw(sheet).text(((index%2)*640+8,(index//2)*380+362),str(row['name']),fill='black')
sheet.save(DEST / 'teaching-contact-sheet.png')
report = {'status':'pass' if all(r.get('correct_pairs_plus_one',True) for r in rows) else 'fail',
          'video_sha256':sha(VIDEO), 'scope':'Fresh MP4 teaching-frame extraction and independent connected-component ticket count, plus visual review of 99/100/101 labels.',
          'method':'RGB fill neighborhoods on decoded native images, four-connected components >=500 pixels; no producer ticket geometry or render output was used as expected data.',
          'rows':rows}
(DEST / 'teaching-quantity-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
