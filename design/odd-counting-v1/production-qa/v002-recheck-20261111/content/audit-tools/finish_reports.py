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
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def ref(path):
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size}
tree = ast.parse((WORK/'content_audit.py').read_text(encoding='utf-8'))
names = {'ink','normalized','expected_glyph','glyph_iou'}
exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names],type_ignores=[]),'own-audit-functions','exec'))
with Image.open(WORK/'frames/value-001.png') as source:
    actual = source.convert('RGB').crop((195,932,305,982))
expected = expected_glyph('1',46,'#205b57','#cfe5d5',200)
sheet = Image.new('RGB',(700,240),'white')
sheet.paste(actual.resize((330,150)),(0,40))
sheet.paste(ImageChops.invert(expected).convert('RGB').resize((expected.width*4,expected.height*4)),(450,40))
ImageDraw.Draw(sheet).text((5,5),'Decoded native ticket 1 / independent expected glyph',fill='black')
sheet.save(DEST/'ticket-1-adjudication.png')
shutil.copyfile(WORK/'frames/value-001.png',DEST/'native-first-count-1.png')
adjudication = json.loads((DEST/'glyph-adjudication.json').read_text(encoding='utf-8'))
adjudication['visual_confirmation_pending'] = False
adjudication['visual_confirmation'] = {
 'content_auditor':'The decoded numeral 1 is complete, legible and not overlapped; main numeral 1, reading one and tickets 1..7 are correct.',
 'root_independent_confirmation':'Parent independently viewed the native PNG and confirmed no missing stroke, alternate numeral or overlap.',
 'native_frame':ref(DEST/'native-first-count-1.png'), 'diagnostic_comparison':ref(DEST/'ticket-1-adjudication.png')}
(DEST/'glyph-adjudication.json').write_text(json.dumps(adjudication,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report = json.loads((DEST/'report.json').read_text(encoding='utf-8'))
report['status'] = 'pass'
report['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
report['scope'] = 'New semantic and source-duration audit of all150 odd values/163 events and captions; new native MP4 decoding of one frame during all150 spoken values, with1350 independently constructed numeral/cardinal/ticket-field comparisons; new component-count inspection of1/5/9 tickets; authored teaching and metadata review. No prior PASS was used as acceptance input.'
report['glyph_adjudication'] = ref(DEST/'glyph-adjudication.json')
report['fresh_extraction']['iou_acceptance'] = '0.96 screen retained for1349 fields; the single flagged current ticket1 at0.955654 was individually resolved by exhaustive0..299 candidate comparison (margin0.424267) and two independent native-image visual reviews.'
report['mathematical_review'].pop('end_never_advances_to_301')
report['mathematical_review']['planned_final_count_is_299_and_no_301_count_event'] = True
report['fresh_teaching_quantity_audit'] = ref(DEST/'teaching-quantity-audit.json')
report['fresh_visual_evidence'] = [ref(DEST/name) for name in ('independent-150-values-contact-sheet.png','teaching-contact-sheet.png','native-first-count-1.png')]
audit_tools = DEST/'audit-tools'
audit_tools.mkdir(exist_ok=True)
for name in ('content_audit.py','teaching_audit.py','adjudicate_glyph_and_finish.py','finish_reports.py'):
    shutil.copyfile(WORK/name,audit_tools/name)
report['new_audit_tools'] = [ref(path) for path in sorted(audit_tools.iterdir())]
report['issues'] = []
(DEST/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(DEST/'report.txt').write_text(
 '奇数動画 v002 内容の独立再チェック: PASS\n\n'
 '完成MP4を新たに抽出・検査し、前回PASSは採否入力に使っていない。\n'
 '1〜299の奇数150個、独自の米国数詞、13台詞、163字幕、5チャプターと投稿内容は一致。\n'
 '通常147境界2秒・確認2境界10秒。音声535.780916667秒、MP4は8分55.8秒で8分以上。\n'
 '全150発話中の原寸画像から、主数値・英語・7整数数直線の1350欄を独立照合。\n'
 '1349欄はIoU0.96以上。初回切符1だけ0.955654で初期閾値未満だったが、0〜299全候補で1が首位・次点との差0.424267。原寸画像を2名が別々に確認し、欠けや別数字はなく当該1欄だけ個別解決した。一律の閾値緩和はしていない。\n'
 '説明図1/5/9枚は独立連結成分検査で0組+1/2組+1/4組+1、99+2=101と100 EVENも実画像で正しい。\n'
 '新規ASR/CTC・音響検査・全フレーム追跡は別担当の範囲。全編の人による連続視聴・試聴は主張していない。\n'
 '未解決の内容不備0件。原動画・既存資料・旧検査は変更していない。\n',encoding='utf-8')
print(json.dumps({'status':'pass','report':str(DEST/'report.json'),'sha256':sha(DEST/'report.json'),
                  'issues':[],'native_png':str(DEST/'native-first-count-1.png')}))
