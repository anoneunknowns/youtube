from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT=Path('D:/codex_projects/youtube')
DEST=Path(__file__).parent/'current-files.json'
def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
record_path=ROOT/'design/four-base-counting-v1/production-run-v002.json'
record=read(record_path)
catalog=read(ROOT/'catalogs/library-v1.json')
problems=[]
checks=[]
def verify(condition,description):
    checks.append(description)
    if not condition:
        problems.append(description)

for entry in record['files']:
    path=ROOT/entry['path']
    verify(path.is_file(),f'exists: {entry["path"]}')
    if path.is_file():
        verify(path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256'],f'bytes/hash: {entry["path"]}')
video=ROOT/record['output']
verify(sha(video)==record['video_sha256'],'video matches completed production record')
verify(video.stat().st_size==record['video_bytes'],'video bytes match completed record')
verify(record['decimal_range']==[0,200] and record['duration_s']>=480,'range and eight-minute requirement')
verify(record['catalog_id'] in catalog['active_production_set_ids'],'v002 is current adopted production')
current=catalog['production_sets'][record['catalog_id']]
verify(current['output']==record['output'] and current['video_sha256']==record['video_sha256'],'catalog matches completed video')
verify(record['reference_set_id'] in catalog['active_reference_set_ids'],'v004 is current visual reference')
plan=read(ROOT/record['timeline']['path'])
verify(sha(ROOT/record['timeline']['path'])==record['timeline']['sha256'],'timeline matches record')
for name in ['technical','visual','audio']:
    report=read(ROOT/record['qa_paths'][name])
    passed=report.get('status')=='pass' if name!='audio' else report.get('passed') is True
    verify(passed,f'original {name} QA has passed')
    if name=='technical':
        verify(report['sha256']==record['video_sha256'] and report['timeline']['sha256']==record['timeline']['sha256'],'technical QA binds this exact media and timeline')
    elif name=='visual':
        verify(report['video_sha256']==record['video_sha256'] and report['timeline_sha256']==record['timeline']['sha256'],'visual QA binds this exact media and timeline')
    else:
        verify(report['encoded_audio']['sha256']==record['video_sha256'] and report['timeline_sha256']==record['timeline']['sha256'],'audio QA binds this exact media and timeline')
for filename in ['README.txt','design/four-base-counting-v1/CURRENT.txt']:
    verify(record['output'] in (ROOT/filename).read_text(encoding='utf-8'),f'current documentation points at v002: {filename}')
verify(len(plan['counted_states'])==201 and plan['counted_states'][-1]['decimal_value']==200,'plan covers 201 values ending at 200')
verify(len({entry['path'] for entry in record['files']})==len(record['files']),'production dependency inventory has no duplicate paths')
result={
    'status':'pass' if not problems else 'fail',
    'checked_at_utc':datetime.now(timezone.utc).isoformat(),
    'video':record['output'],'video_sha256':sha(video),'video_bytes':video.stat().st_size,
    'production_record_sha256':sha(record_path),'dependency_files':len(record['files']),
    'checks':len(checks),'failures':problems,
    'completed_production_records':[p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'design/four-base-counting-v1').glob('production-run-v*.json'))],
}
with DEST.open('x',encoding='utf-8') as f:
    json.dump(result,f,ensure_ascii=False,indent=2)
    f.write('\n')
print(json.dumps(result))
raise SystemExit(bool(problems))
