"""Fresh standalone content audit. No imports from production tools or reports."""
from collections import Counter
import csv
from datetime import datetime,timezone
from fractions import Fraction
from hashlib import file_digest
import json
from math import ceil
from pathlib import Path
import re
import subprocess
import wave

ROOT=Path('D:/codex_projects/youtube')
OUT=ROOT/'output/four-base-counting-001-v002-to-200'
DEST=Path(__file__).parent
VIDEO=OUT/'paspla-studio-four-ways-to-count-0-to-200-1080p.mp4'
FFMPEG=Path('D:/dev/FFmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe')
FFPROBE=FFMPEG.with_name('ffprobe.exe')
plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
checks=Counter()
errors=[]

def check(condition,category,detail=''):
    checks[category]+=1
    if not condition:
        errors.append({'category':category,'detail':detail})

def digest(path):
    with path.open('rb') as source:
        return file_digest(source,'sha256').hexdigest()

def numeral(number,base):
    """Repeated division instead of production format/bin/oct/hex helpers."""
    result=[]
    while number:
        number,remainder=divmod(number,base)
        result.append('0123456789ABCDEF'[remainder])
    return ''.join(reversed(result)) or '0'

UNITS='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS='zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()
def english(number):
    if number<20:
        return UNITS[number]
    if number<100:
        tens,unit=divmod(number,10)
        return TENS[tens]+('-'+UNITS[unit] if unit else '')
    hundreds,tail=divmod(number,100)
    return UNITS[hundreds]+' hundred'+(' '+english(tail) if tail else '')

def normalize(text):
    return re.sub('[^a-z0-9]+',' ',text.lower()).strip()

def ticks(seconds,rate=24000):
    return round(Fraction(str(seconds))*rate)

states=plan['counted_states']
counts=sorted((e for e in plan['events'] if e['phase']=='count' and e['type']=='number_voice'),key=lambda e:e['start_sample_24k'])
check(len(states)==len(counts)==201,'coverage')
check([s['decimal_value'] for s in states]==list(range(201)),'ordered_states')
check([e['decimal_value'] for e in counts]==list(range(201)),'ordered_voices')
check(set(plan['numeric_sources'])==set(map(str,range(201))),'source_keys')
check(plan['row_order']==['binary','decimal','octal','hexadecimal'] and plan['narration_base']==10,'row_order_and_narration')
source_stats=[]
gap_counts=Counter()
previous=Fraction(30)
names=[('binary',2),('decimal',10),('octal',8),('hexadecimal',16)]
for n,(state,event) in enumerate(zip(states,counts,strict=True)):
    source=plan['numeric_sources'][str(n)]
    for name,base in names:
        observed=state['representations'][name]
        expected=numeral(n,base)
        check(observed==expected,'independent_804_representations',f'{n}/{name}:{observed}!={expected}')
        check(bool(re.fullmatch('[0123456789ABCDEF]+',observed)) and (n==0 or observed[0]!='0'),'canonical_glyphs_and_no_leading_zeros',f'{n}/{name}')
    for label,observed in [('state',state['spoken_text']),('event',event['text']),('source',source['spoken_text'])]:
        check(normalize(observed)==normalize(english(n)),'natural_decimal_english',f'{n}/{label}:{observed}')
    path=ROOT/source['path']
    check(source['sha256']==state['source_sha256']==event['source_sha256']==digest(path),'source_hash_alignment',str(n))
    check(source['path']==state['source_path']==event['source_path'],'source_path_alignment',str(n))
    with wave.open(str(path),'rb') as track:
        frames=track.getnframes()
        check((track.getframerate(),track.getnchannels(),track.getsampwidth())==(24000,1,2),'source_wav_format',str(n))
        check(len(track.readframes(frames))==frames*2,'source_wav_not_truncated',str(n))
    check(frames==source['sample_frames']==event['end_sample_24k']-event['start_sample_24k'],'whole_number_clip_in_schedule',str(n))
    start,end=state['estimated_display_start_s'],state['estimated_display_end_s']
    check(ticks(start)==ticks(previous),'contiguous_display',str(n))
    check(ticks(start)+2880==event['start_sample_24k'],'display_lead_120ms',str(n))
    check(event['start_sample_24k']==ticks(state['voice_start_s']) and event['end_sample_24k']==ticks(state['voice_end_s']),'measured_voice_binding',str(n))
    check(ticks(start)<event['start_sample_24k']<event['end_sample_24k']<ticks(end),'voice_inside_correct_state',str(n))
    check(state['all_rows_update_together'] is True,'all_rows_together',str(n))
    if n:
        gap=event['start_sample_24k']-counts[n-1]['end_sample_24k']
        expected=120000 if n-1 in (8,16,64) else 48000
        check(gap==expected,'between_whole_numbers',str(n))
        gap_counts[str(Fraction(gap,24000))]+=1
    previous=end
    source_stats.append({'value':n,'expected_english':english(n),'wav_frames':frames,'source_sha256':source['sha256']})

# Independently read the script's 201-row tabular manuscript.
with (ROOT/'design/four-base-counting-v1/count-to-200-v002/count-lines.tsv').open(encoding='utf-8',newline='') as f:
    manuscript=list(csv.DictReader(f,delimiter='\t'))
check(len(manuscript)==201,'manuscript_coverage')
for n,row in enumerate(manuscript):
    check(int(row['decimal_value'])==n,'manuscript_order',str(n))
    check(all(row[name]==numeral(n,base) for name,base in names),'manuscript_representations',str(n))
    check(normalize(row['spoken_text'])==normalize(english(n)),'manuscript_english',str(n))

def srt_ms(text):
    hours,minutes,seconds,millis=map(int,re.split('[:,]',text))
    return (((hours*60)+minutes)*60+seconds)*1000+millis

blocks=re.split(r'\n\s*\n',(OUT/'english-captions.srt').read_text(encoding='utf-8').strip())
speech=sorted((e for e in plan['events'] if e['type']!='sfx'),key=lambda e:e['start_sample_24k'])
check(len(blocks)==len(speech)==215,'caption_coverage')
previous_ms=0
caption_time_errors=[]
for n,(block,event) in enumerate(zip(blocks,speech,strict=True),1):
    lines=block.splitlines()
    start,end=map(srt_ms,lines[1].split(' --> '))
    text=' '.join(lines[2:])
    check(int(lines[0])==n,'caption_numbering',str(n))
    check(previous_ms<=start<end<=round(plan['duration_s']*1000),'caption_boundaries',str(n))
    deviations=[abs(Fraction(start)-Fraction(event['start_sample_24k'],24)),abs(Fraction(end)-Fraction(event['end_sample_24k'],24))]
    caption_time_errors.extend(deviations)
    check(max(deviations)<=Fraction(1,2),'caption_matches_sample_times_within_half_millisecond',event['id'])
    check(normalize(text)==normalize(event['text']),'caption_exact_speech',event['id'])
    if event['type']=='number_voice':
        check(normalize(text)==normalize(english(event['decimal_value'])),'caption_decimal_meaning',event['id'])
    previous_ms=end

intro=plan['intro']['example']
check(intro['decimal_value']==10 and all(intro['representations'][name]==numeral(10,base) for name,base in names),'intro_ten_conversions')
ten=next(e for e in plan['events'] if e['id']=='I04-TEN')
check(intro['display_start_s']<=ten['start_s']<ten['end_s']<intro['display_end_s'],'intro_ten_display_coverage')
teaching=[]
for pause in plan['pauses']:
    value=pause['after_decimal_value']
    changed=[name for name,base in names if len(numeral(value,base))>len(numeral(value-1,base))]
    check(set(pause['focus_rows']).issubset(changed),'new_place_claim_math',str(value))
    if value==8:
        check(len(numeral(value,8))==2 and pause['dialogue']['text']=='The octal row now has two places.','spoken_teaching_claim','8')
    elif value==16:
        check(len(numeral(value,16))==2 and pause['dialogue']['text']=='Hexadecimal now has two places.','spoken_teaching_claim','16')
    elif value==64:
        check({'binary','octal'}.issubset(changed) and pause['dialogue']['text']=='Both binary and octal add a new place.','spoken_teaching_claim','64')
    else:
        check(False,'unexpected_teaching_value',str(value))
    line=next(e for e in plan['events'] if e['id']==pause['dialogue']['id'])
    check(states[value]['estimated_display_start_s']<=line['start_s']<line['end_s']<states[value]['estimated_display_end_s'],'teaching_on_correct_value',str(value))
    teaching.append({'decimal_value':value,'grew_rows':changed,'text':pause['dialogue']['text']})

check(states[-1]['representations']==dict(zip([x[0] for x in names],['11001000','200','310','C8'])),'final_values')
check(ticks(previous)==ticks(plan['finale']['estimated_start_s']),'count_reaches_finale')
check(ticks(previous)-counts[-1]['end_sample_24k']==6720,'final_hold_280ms')
check(ticks(plan['duration_s'])-ticks(plan['finale']['estimated_start_s'])==288000,'finale_12_seconds')
check(next(e for e in plan['events'] if e['id']=='F04')['end_s']<plan['finale']['estimated_start_s']+10,'last_words_finish_before_fade')
check(480<=plan['duration_s']<900,'eight_minute_minimum')
expected_frames=ceil(Fraction(str(plan['duration_s']))*30)

chapter_lines=(OUT/'chapters.txt').read_text(encoding='utf-8').strip().splitlines()
times=[]
for line in chapter_lines:
    mm,ss=map(int,line.split()[0].split(':'))
    times.append(mm*60+ss)
check(times==[0,30,int(plan['pauses'][0]['estimated_start_s']),int(plan['pauses'][1]['estimated_start_s']),int(plan['pauses'][2]['estimated_start_s']),int(plan['finale']['estimated_start_s'])],'chapter_times')
check(all(b-a>=10 for a,b in zip(times,times[1:]+[plan['duration_s']])),'chapter_minimum_duration')
check(chapter_lines[-1].endswith('Four Ways to Write 200'),'chapter_final_value')
upload=(OUT/'upload-details.txt').read_text(encoding='utf-8')
check('Four Ways to Count to 200 | Binary, Decimal, Octal & Hexadecimal | Num-Num Numbers' in upload,'english_title')
check('Count from zero to 200 in four number systems at once: binary, decimal, octal, and hexadecimal.' in upload,'english_description_range')
check('Listen to the decimal number while every row shows the same value in a different base.' in upload,'description_explains_narration')
check(all(line in upload for line in chapter_lines),'upload_chapters')
check(VIDEO.name in upload and '127' not in upload,'upload_new_filename_and_no_old_range')

probe=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-show_entries','format=duration,size:stream=codec_type,duration,nb_frames,r_frame_rate','-of','json',str(VIDEO)],text=True))
video=next(s for s in probe['streams'] if s['codec_type']=='video')
check(int(video['nb_frames'])==expected_frames==19871,'delivered_frame_count')
check(abs(float(video['duration'])-expected_frames/30)<.000001,'delivered_duration')

# Encode-free single-pass extraction at the exact first frame of each new state,
# and the frame immediately before; expectation derives only from arithmetic.
boundaries=[]
indices=[]
for value in [128,160,192,200]:
    first=ceil(Fraction(str(states[value]['estimated_display_start_s']))*30)
    for idx,shown in [(first-1,value-1),(first,value)]:
        indices.append(idx)
        boundaries.append({'frame':idx,'time_s':idx/30,'expected_decimal':shown,
                           'expected_rows':{name:numeral(shown,base) for name,base in names}})
filters='select='+ '+'.join(f'eq(n\\,{idx})' for idx in indices)
command=[str(FFMPEG),'-nostdin','-v','error','-xerror','-i',str(VIDEO),'-map','0:v:0','-an','-vf',filters,'-fps_mode','passthrough',str(DEST/'boundary-%02d.png')]
images=sorted(DEST.glob('boundary-*.png'))
if images:
    previous_report=json.loads((DEST/'initial-rounding-check.json').read_text(encoding='utf-8'))
    check(previous_report['video_sha256']==digest(VIDEO) and all(digest(Path(row['image']))==row['sha256'] for row in previous_report['boundaries']),'fresh_boundary_images_bound_to_same_video')
else:
    completed=subprocess.run(command,capture_output=True,text=True)
    check(completed.returncode==0 and not completed.stderr,'boundary_decode',completed.stderr)
    images=sorted(DEST.glob('boundary-*.png'))
check(len(images)==len(boundaries)==8,'boundary_image_coverage')
for row,path in zip(boundaries,images,strict=True):
    row['image']=str(path)
    row['sha256']=digest(path)

report={'status':'pass' if not errors else 'fail','checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'method':'Fresh standard-library arithmetic, English number construction, WAV headers, independent SRT parser and exact boundary frame extraction. No production renderer/verifier imports.',
        'video_sha256':digest(VIDEO),'timeline_sha256':digest(OUT/'timeline.json'),'checks':dict(checks),'total_checks':sum(checks.values()),
        'counted_values':201,'representations':804,'captions':215,'maximum_caption_quantization_error_ms':float(max(caption_time_errors)),
        'rounding_review':'An initial exact ties-to-even test flagged N079 at 257.4095s. The SRT uses 257.409s, exactly 0.5ms away, so either adjacent millisecond is equally nearest. All 430 caption endpoints are within 0.5ms of source sample times. This is not a synchronization fault.',
        'gaps':dict(gap_counts),'teaching_claims':teaching,
        'boundaries':boundaries,'errors':errors,'scope_limit':'Counts/source metadata and raw decoded boundary images; visual interpretation of extracted images recorded separately. Audio semantics/acoustics are another audit.'}
(DEST/'content-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':sum(checks.values()),'errors':errors,'boundaries':boundaries,'report':str(DEST/'content-audit.json')}))
raise SystemExit(bool(errors))
