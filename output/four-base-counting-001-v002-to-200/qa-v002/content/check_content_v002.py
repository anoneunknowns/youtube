"""Independent delivered metadata/content audit; no renderer imports."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path('D:/codex_projects/youtube')
OUT = ROOT / 'output/four-base-counting-001-v002-to-200'
DEST = Path(__file__).parent / 'content-check-v002.json'
plan = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8'))
errors = []
checks = Counter()

def require(condition, label):
    checks[label] += 1
    if not condition:
        errors.append(label)

def base_digits(value, base):
    if value == 0:
        return '0'
    digits = ''
    while value:
        value, remainder = divmod(value, base)
        digits = '0123456789ABCDEF'[remainder] + digits
    return digits

small = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
tens = {word: n * 10 for n, word in enumerate('zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split())}
def parse_english_number(text):
    tokens = re.sub(r'[^a-z ]', ' ', text.lower()).split()
    if len(tokens) == 1 and tokens[0] in small:
        return small.index(tokens[0])
    if len(tokens) >= 2 and tokens[0] in small[1:10] and tokens[1] == 'hundred':
        return 100 * small.index(tokens[0]) + (parse_english_number(' '.join(tokens[2:])) if len(tokens) > 2 else 0)
    if 1 <= len(tokens) <= 2 and tokens[0] in tens and tens[tokens[0]] >= 20:
        if len(tokens) == 1:
            return tens[tokens[0]]
        if tokens[1] in small[1:10]:
            return tens[tokens[0]] + small.index(tokens[1])
    raise ValueError(text)

voices = sorted((e for e in plan['events'] if e['type'] == 'number_voice' and e['phase'] == 'count'), key=lambda e: e['start_s'])
states = plan['counted_states']
require(len(voices) == len(states) == 201, 'count_coverage')
gap_counts = Counter()
previous_display_end = 30.0
for value, (state, event) in enumerate(zip(states, voices, strict=True)):
    require(state['decimal_value'] == event['decimal_value'] == value, 'strict_count_sequence')
    for name, base in [('binary', 2), ('decimal', 10), ('octal', 8), ('hexadecimal', 16)]:
        require(state['representations'][name] == base_digits(value, base), 'independent_base_conversion')
    require(parse_english_number(event['text']) == value, 'independent_decimal_spoken_text')
    start, end = state['estimated_display_start_s'], state['estimated_display_end_s']
    require(abs(start - previous_display_end) < 1e-7, 'continuous_display_states')
    require(start < event['start_s'] < event['end_s'] < end, 'speech_within_display')
    require(abs(event['start_s'] - start - .12) < 1e-7, 'display_precedes_speech_120ms')
    if value:
        gap = round(event['start_s'] - voices[value-1]['end_s'], 8)
        require(abs(gap - (5 if value-1 in (8,16,64) else 2)) < 1e-7, 'between_number_gap')
        gap_counts[str(round(gap, 3))] += 1
    previous_display_end = end
require(abs(previous_display_end - plan['finale']['estimated_start_s']) < 1e-7, 'last_state_reaches_finale')

def srt_time(text):
    h,m,s,ms = map(int, re.split('[:,]', text))
    return ((h*60+m)*60+s)*1000+ms

blocks = re.split(r'\r?\n\s*\r?\n', (OUT / 'english-captions.srt').read_text(encoding='utf-8').strip())
speech = sorted((e for e in plan['events'] if e['type'] != 'sfx'), key=lambda e:e['start_s'])
require(len(blocks) == len(speech) == 215, 'caption_coverage')
prev_ms = 0
caption_lengths = []
for index, (block, event) in enumerate(zip(blocks, speech, strict=True), 1):
    lines = block.splitlines()
    require(int(lines[0]) == index, 'caption_sequence')
    begin, end = [srt_time(t) for t in lines[1].split(' --> ')]
    require(prev_ms <= begin < end <= round(plan['duration_s']*1000), 'caption_order_and_bounds')
    require(begin == round(event['start_s']*1000) and end == round(event['end_s']*1000), 'caption_event_times')
    actual_text = ' '.join(lines[2:])
    norm = lambda s: re.sub(r'[^a-z0-9]+', ' ', s.casefold()).strip()
    require(norm(actual_text) == norm(event['text']), 'caption_speech_text')
    if event['phase'] == 'count':
        require(parse_english_number(actual_text) == event['decimal_value'], 'caption_decimal_value')
    prev_ms = end
    caption_lengths.append(len(actual_text))

chapters = (OUT / 'chapters.txt').read_text(encoding='utf-8').strip().splitlines()
chapter_times = []
for chapter in chapters:
    minute, second = map(int, chapter.split()[0].split(':'))
    chapter_times.append(minute*60+second)
require(len(chapters) == 6 and chapter_times[0] == 0, 'chapter_coverage')
require(all(b-a >= 10 for a,b in zip(chapter_times,chapter_times[1:] + [plan['duration_s']])), 'chapter_durations')
require(chapter_times[1] == int(states[0]['estimated_display_start_s']) and chapter_times[-1] == int(plan['finale']['estimated_start_s']), 'chapter_count_and_finale')
for pause, chapter_s in zip(plan['pauses'], chapter_times[2:5], strict=True):
    require(chapter_s == int(pause['estimated_start_s']), 'chapter_teaching_times')

intro = plan['intro']['example']
intro_ten = next(e for e in plan['events'] if e['id']=='I04-TEN')
require(intro['display_start_s'] <= intro_ten['start_s'] < intro_ten['end_s'] < intro['display_end_s'], 'intro_ten_display')
require(parse_english_number(intro_ten['text']) == 10, 'intro_ten_reading')
report = {
    'status': 'pass' if not errors else 'fail',
    'checked_at_utc': datetime.now(timezone.utc).isoformat(),
    'method': 'No production renderer/verifier imports; repeated integer division, separate English number grammar, independent SRT parser.',
    'checks': dict(checks),
    'checks_total': sum(checks.values()),
    'gaps_seconds': dict(gap_counts),
    'caption_cues': len(blocks),
    'maximum_caption_characters': max(caption_lengths),
    'inputs': {name: sha256((OUT/name).read_bytes()).hexdigest() for name in ['timeline.json','english-captions.srt','chapters.txt','upload-details.txt']},
    'errors': errors,
}
DEST.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'checks_total':report['checks_total'],'checks':report['checks'],'gaps_seconds':report['gaps_seconds'],'errors':errors,'report':str(DEST)}))
raise SystemExit(bool(errors))
