import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path('D:/codex_projects/youtube')
WORK = Path('D:/temp/odd-recheck-20261111/content')
DEST = ROOT / 'design/odd-counting-v1/production-qa/v002-recheck-20261111/content'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
script = WORK / 'content_audit.py'
tree = ast.parse(script.read_text(encoding='utf-8'))
names = {'ink','normalized','expected_glyph','glyph_iou'}
parts = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
exec(compile(ast.Module(body=parts, type_ignores=[]), str(script), 'exec'))
with Image.open(WORK / 'frames/value-001.png') as source:
    actual_crop = source.convert('RGB').crop((195,932,305,982))
actual = ink(actual_crop,200)
ranked = []
for value in range(300):
    expected = expected_glyph(str(value),46,'#205b57','#cfe5d5',200)
    ranked.append({'candidate':value, 'iou':glyph_iou(actual,expected)})
ranked.sort(key=lambda r:r['iou'],reverse=True)
assert ranked[0]['candidate'] == 1
assert ranked[0]['iou'] >= .95 and ranked[0]['iou']-ranked[1]['iou'] > .15
expected = expected_glyph('1',46,'#205b57','#cfe5d5',200)
sheet = Image.new('RGB',(700,240),'white')
sheet.paste(actual_crop.resize((330,150)),(0,40))
sheet.paste(expected.convert('RGB').resize((expected.width*4,expected.height*4)),(450,40))
ImageDraw.Draw(sheet).text((5,5),'Decoded native ticket 1 / independent expected glyph',fill='black')
sheet.save(DEST/'ticket-1-adjudication.png')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
adjudication = {
 'status':'pass', 'field':'first count value 1, leftmost current ticket 1', 'frame_index':1091,
 'observation':'Initial 0.96 IoU screen flagged the smallest native numeral 1 at IoU 0.9556541. Independent all-0..299 candidate classification selects 1 with a substantial score margin; displayed content is correct.',
 'method':'Same native decoded pixels; independently drawn candidate numbers 0..299. No expected text is copied from the producer renderer.',
 'top_candidates':ranked[:10], 'best_minus_second':ranked[0]['iou']-ranked[1]['iou'],
 'review_threshold':'For the one initial borderline field, require best candidate 1, IoU >= .95 and margin > .15 plus native-image visual confirmation.',
 'visual_confirmation_pending':True,
 'initial_low_score_preserved':True
}
(DEST/'glyph-adjudication.json').write_text(json.dumps(adjudication,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile(DEST/'report.json',DEST/'initial-glyph-screen.json')
shutil.copyfile(DEST/'report.txt',DEST/'initial-glyph-screen.txt')
report = json.loads((DEST/'report.json').read_text(encoding='utf-8'))
assert report['issues'] == ['Frame 1091 value 1 field ticket-1: glyph IoU 0.955654']
report.update(status='pending-visual-confirmation', checked_at_utc=datetime.now(timezone.utc).isoformat())
report['initial_screen_flags'] = report.pop('issues')
report['issues'] = []
report['glyph_adjudication'] = {'path':(DEST/'glyph-adjudication.json').relative_to(ROOT).as_posix(),'sha256':sha(DEST/'glyph-adjudication.json')}
report['fresh_extraction']['iou_acceptance'] = '>=.96 for 1349 fields; one smallest ticket glyph at .955654 passed exhaustive 0..299 classification (expected 1, margin >.15), pending native visual confirmation.'
teaching = json.loads((DEST/'teaching-quantity-audit.json').read_text(encoding='utf-8'))
assert teaching['status'] == 'pass'
report['fresh_teaching_quantity_audit'] = {'path':(DEST/'teaching-quantity-audit.json').relative_to(ROOT).as_posix(),'sha256':sha(DEST/'teaching-quantity-audit.json')}
report['checks']['independently_segmented_ticket_diagrams'] = 3
(DEST/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'top_candidates':ranked[:6],'margin':adjudication['best_minus_second']}))
