import hashlib,json,math,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path('D:/codex_projects/youtube/tools')))
from verify_octal_video import decoded_native_frame
ROOT=Path('D:/codex_projects/youtube')
BASE=ROOT/'output/hexadecimal-counting-001-v002-clear-A'
VIDEO=BASE/'paspla-studio-hexadecimal-count-0-to-7F-1080p.mp4'
OUT=Path('D:/temp/hex-visual-recheck-v002-clear-A')
plan=json.loads((BASE/'timeline.json').read_text())
events=plan['events']
def first(t):return math.ceil(t*30-1e-7)
def mid(e):return first((e['start_s']+e['end_s'])/2)
def digit(value,token):return next(e for e in events if e.get('phase')=='count' and e.get('decimal_value')==value and e.get('token')==token)
a=digit(10,'A')
states=plan['counted_states']
cases=[
('01-intro-A',mid(next(e for e in events if e['id']=='I05-A')),'1A/26, A highlighted'),
('02-count-A-onset',first(a['start_s']),'A/10, A highlighted'),
('03-count-A-release',first(a['end_s']),'A/10, word and symbol highlight released'),
('04-count-1A',mid(digit(26,'A')),'1A/26, A highlighted'),
('05-next-1B-cut',first(states[27]['estimated_display_start_s']),'1B/27, no highlight yet'),
('06-last-3F-check',first(states[64]['estimated_display_start_s'])-1,'3F/63 with full equation'),
('07-first-40',first(states[64]['estimated_display_start_s']),'40/64, no equation/banner'),
('08-68-eight',mid(digit(104,'eight')),'68/104, eight highlighted'),
('09-7F',mid(digit(127,'F')),'7F/127, F highlighted'),
('10-final-cream',first(plan['duration_s'])-1,'Uniform cream fade endpoint'),
]
video_hash=hashlib.file_digest(VIDEO.open('rb'),'sha256').hexdigest()
rows=[]
for name,index,expected in cases:
    image=decoded_native_frame(VIDEO,shutil.which('ffmpeg'),index)
    target=OUT/f'{name}.png'
    image.save(target)
    rows.append({'frame':index,'time_s':index/30,'expected':expected,'image':str(target),'image_sha256':hashlib.file_digest(target.open('rb'),'sha256').hexdigest()})
assert hashlib.file_digest(VIDEO.open('rb'),'sha256').hexdigest()==video_hash
report={'kind':'v002-targeted-visual-recheck','video':str(VIDEO),'video_sha256':video_hash,'timeline_sha256':hashlib.file_digest((BASE/'timeline.json').open('rb'),'sha256').hexdigest(),'native_frames':rows,'assistant_visual_review_pending':True}
(OUT/'selection.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'video_sha256':video_hash,'frames':len(rows),'evidence':str(OUT/'selection.json')}))
