"""New independent semantic and native-glyph audit of the final odd-number MP4."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path('D:/codex_projects/youtube')
OUT = ROOT / 'output/odd-counting-001-v002'
WORK = Path('D:/temp/odd-recheck-20261111/content')
DEST = ROOT / 'design/odd-counting-v1/production-qa/v002-recheck-20261111/content'
VIDEO = OUT / 'paspla-studio-odd-numbers-1-to-299-1080p.mp4'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SCRIPT = ROOT / 'design/odd-counting-v1/script-and-sound-cues-v002.txt'
for p in (WORK, DEST, WORK / 'frames'):
    p.mkdir(parents=True, exist_ok=True)

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def ref(path):
    return {'path': path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix(),
            'sha256': sha(path), 'bytes': path.stat().st_size}

failures = []
def check(ok, text):
    if not ok:
        failures.append(text)

def words(value):
    low = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
           'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
           'seventeen', 'eighteen', 'nineteen']
    tens = {2: 'twenty', 3: 'thirty', 4: 'forty', 5: 'fifty', 6: 'sixty', 7: 'seventy', 8: 'eighty', 9: 'ninety'}
    hundreds, remainder = divmod(value, 100)
    result = low[hundreds] + ' hundred' if hundreds else ''
    if remainder:
        if result:
            result += ' '
        if remainder < 20:
            result += low[remainder]
        else:
            decade, unit = divmod(remainder, 10)
            result += tens[decade] + ('-' + low[unit] if unit else '')
    return result or 'zero'

plan = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8-sig'))
events = sorted(plan['voice_events'], key=lambda r: r['start_sample_24k'])
numbers = [r for r in events if r['phase'] == 'count']
expected_values = list(range(1, 300, 2))
check([r['decimal_value'] for r in numbers] == expected_values, 'Wrong numeric event sequence')
check(len(events) == 163 and len({r['id'] for r in events}) == 163, 'Voice IDs missing or duplicated')
check(Counter(r['type'] for r in events) == {'number_voice': 150, 'dialogue': 13}, 'Wrong voice types')
check(set(plan['numeric_sources']) == {str(n) for n in expected_values}, 'Wrong numeric source coverage')
scenes = plan['scenes']
states = scenes[1:-1]
check([s['scene'] for s in scenes] == ['intro'] + ['count'] * 150 + ['finale'], 'Wrong scene structure')
check([s['decimal_value'] for s in states] == expected_values, 'Visual state sequence differs')
check(len(plan['counted_states']) == 150, 'Wrong counted-state count')
check(scenes[0]['start_s'] == 0 and scenes[0]['end_s'] == 36, 'Wrong intro duration')
check(all(abs(a['end_s'] - b['start_s']) < 1e-8 for a, b in zip(scenes, scenes[1:])), 'Visual discontinuity')
check(abs(scenes[-1]['end_s'] - scenes[-1]['start_s'] - 14) < 1e-8, 'Wrong finale duration')

numeric_records = []
gaps = Counter()
for n, event, state, counted in zip(expected_values, numbers, states, plan['counted_states'], strict=True):
    expected = words(n)
    check(event['id'] == f'N{n:03d}', f'Wrong ID for {n}')
    for location, text in [('event', event['text']), ('scene', state['spoken_text']),
                           ('state', counted['spoken_text']), ('source', plan['numeric_sources'][str(n)]['spoken_text'])]:
        check(text == expected, f'{n}: {location} text {text!r} != {expected!r}')
    check(abs(event['start_s'] - state['start_s'] - .12) < 1e-8, f'{n}: wrong display lead')
    check(abs(state['voice_start_s'] - event['start_s']) < 1e-8 and abs(state['voice_end_s'] - event['end_s']) < 1e-8,
          f'{n}: voice-to-state mismatch')
    check(state['end_s'] >= event['end_s'], f'{n}: voice outlasts state')
    check(event['start_sample_24k'] == round(event['start_s'] * 24000) and
          event['end_sample_24k'] == round(event['end_s'] * 24000), f'{n}: sample/time mismatch')
    source = ROOT / event['source_path']
    check(sha(source) == event['source_sha256'], f'{n}: source SHA changed')
    with wave.open(str(source), 'rb') as stream:
        check(stream.getnframes() == event['end_sample_24k'] - event['start_sample_24k'], f'{n}: speech duration mismatch')
    if n in (9, 101):
        teaching = state['teaching']
        check(teaching['id'] == f'T{n:03d}', f'{n}: wrong teaching ID')
        check(abs(teaching['start_s'] - event['end_s'] - .4) < 1e-8 and
              abs(teaching['end_s'] - teaching['start_s'] - 8) < 1e-8, f'{n}: wrong teaching window')
    else:
        check('teaching' not in state, f'{n}: unexpected teaching')
    numeric_records.append({'value': n, 'expected_us_cardinal': expected,
                            'voice_start_s': event['start_s'], 'voice_end_s': event['end_s'],
                            'display_start_s': state['start_s'], 'display_end_s': state['end_s']})
for left, right in zip(numbers, numbers[1:]):
    gap = (right['start_sample_24k'] - left['end_sample_24k']) / 24000
    check(gap == (10 if left['decimal_value'] in (9, 101) else 2), f'Incorrect next-number gap after {left["decimal_value"]}')
    gaps[gap] += 1
check(gaps == {2: 147, 10: 2}, 'Wrong aggregate gap counts')
check(abs(scenes[-1]['start_s'] - numbers[-1]['end_s'] - .28) < 1e-8, 'Wrong 299 completion hold')
numeric_duration = sum(e['end_sample_24k'] - e['start_sample_24k'] for e in numbers) / 24000
check(abs(plan['duration_s'] - numeric_duration - 364.4) < 1e-8, 'Wrong computed lesson length')
check(plan['duration_s'] >= 480 and plan['duration_frames'] == math.ceil(plan['duration_s'] * 30 - 1e-7), 'Below eight minutes or wrong frame count')

dialogue = {
 'I01': (0.8, 4.3, "Hi! Let's count odd numbers."),
 'I02': (5, 8.5, 'We start at one and add two.'),
 'I03': (9.2, 12, 'One ticket has no partner.'),
 'I04': (13, 18.5, 'Five tickets make two pairs, with one left over.'),
 'I05': (19.2, 23.7, 'Odd numbers have one left over when we make pairs.'),
 'I06': (25, 29.4, "Our example is finished. Let's start at one."),
 'I07': (30.2, 35, "We'll count all the way to two hundred ninety-nine."),
 'T009': (.7, 6.5, 'Nine tickets make four pairs, with one left over.'),
 'T101': (.5, 7, 'From ninety-nine, adding two takes us to one hundred one.'),
 'F01': (1, 2.3, 'We did it!'),
 'F02': (2.8, 7.8, 'We counted by twos, all the way to two hundred ninety-nine!'),
 'F03': (8.2, 10.5, 'Thanks for counting with me!'),
 'F04': (10.8, 11.8, 'Bye for now!')}
script_lines = {}
for line in SCRIPT.read_text(encoding='utf-8').splitlines():
    cells = line.split(' | ')
    if re.fullmatch(r'I\d\d|T\d\d\d|F\d\d', cells[0]):
        offset = 1 if cells[0][0] == 'T' else 0
        script_lines[cells[0]] = (list(map(float, cells[1 + offset].split('–'))), cells[2 + offset])
check(set(script_lines) == set(dialogue), 'Wrong authored dialogue IDs')
origins = {s['teaching']['id']: s['teaching']['start_s'] for s in states if 'teaching' in s}
for event in events:
    if event['type'] != 'dialogue':
        continue
    begin, end, text = dialogue[event['id']]
    check(event['text'] == text, f'{event["id"]}: authored dialogue differs')
    check(script_lines[event['id']] == ([begin, end], text), f'{event["id"]}: script differs')
    origin = 0 if event['id'][0] == 'I' else scenes[-1]['start_s'] if event['id'][0] == 'F' else origins[event['id']]
    check(abs(event['start_s'] - (origin + begin)) < 1e-8 and event['end_s'] <= origin + end + 1e-8,
          f'{event["id"]}: speech outside its authored window')
check(all(a['end_sample_24k'] <= b['start_sample_24k'] for a, b in zip(events, events[1:])), 'Overlapping speech')

def srt_seconds(value):
    hours, minutes, seconds, millis = map(int, re.split('[:,]', value))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000

srt = []
for block in (OUT / 'english-captions.srt').read_text(encoding='utf-8-sig').strip().split('\n\n'):
    lines = block.splitlines()
    left, right = lines[1].split(' --> ')
    srt.append((int(lines[0]), srt_seconds(left), srt_seconds(right), '\n'.join(lines[2:])))
check(len(srt) == 163, 'Wrong subtitle count')
for ordinal, (caption, event) in enumerate(zip(srt, events, strict=True), 1):
    expected = event['text'][0].upper() + event['text'][1:] + ('.' if event['type'] == 'number_voice' else '')
    check(caption[0] == ordinal and caption[3] == expected, f'Caption {ordinal}: ID/text differs')
    check(abs(caption[1] - event['start_s']) <= .000501 and abs(caption[2] - event['end_s']) <= .000501,
          f'Caption {ordinal}: timestamp differs')

chapter_values = [(0, 'What Are Odd Numbers?'), (36, 'Count by Twos from One'),
                  (math.floor(origins['T009']), 'Nine Tickets, Four Pairs and One Left Over'),
                  (math.floor(origins['T101']), 'From Ninety-Nine to One Hundred One'),
                  (math.floor(scenes[-1]['start_s']), 'We Reached Two Hundred Ninety-Nine')]
expected_chapters = '\n'.join(f'{n // 60:02}:{n % 60:02} {title}' for n, title in chapter_values) + '\n'
check((OUT / 'chapters.txt').read_text(encoding='utf-8') == expected_chapters, 'Chapter mismatch')
upload = (OUT / 'upload-details.txt').read_text(encoding='utf-8')
check('Count Odd Numbers from 1 to 299 | Count by Twos | Num-Num Numbers' in upload, 'Wrong title')
check('from one to two hundred ninety-nine' in upload and expected_chapters in upload, 'Wrong description range/chapters')
check('paspla-studio-odd-numbers-1-to-299-1080p.mp4' in upload, 'Wrong upload filename')

probe = json.loads(subprocess.check_output([shutil.which('ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(VIDEO)]))
check(abs(float(probe['format']['duration']) - 535.8) < .000001, 'Wrong actual movie duration')

# One independently selected native frame during each of the 150 spoken values.
frame_indices = [math.ceil(((e['start_s'] + e['end_s']) / 2) * 30 - 1e-7) for e in numbers]
def select_expression(indices):
    if len(indices) == 1:
        return f'eq(n,{indices[0]})'
    middle = len(indices) // 2
    return f'({select_expression(indices[:middle])}+{select_expression(indices[middle:])})'
expression = select_expression(frame_indices)
with (WORK / 'fresh-extraction.log').open('w', encoding='utf-8') as log:
    subprocess.run([shutil.which('ffmpeg'), '-hide_banner', '-v', 'error', '-n', '-i', str(VIDEO),
                    '-vf', f"select='{expression}'", '-fps_mode', 'vfr',
                    str(WORK / 'frames/value-%03d.png')], stderr=log, check=True)

def ink(image, threshold):
    return image.convert('L').point(lambda v: 255 if v < threshold else 0)

def normalized(image):
    box = image.getbbox()
    return image.crop(box) if box else Image.new('L', (1, 1))

def expected_glyph(text, size, color, background, threshold):
    face = ImageFont.truetype(str(FONT), size)
    canvas = Image.new('RGB', (max(1400, int(face.getlength(text)) + 30), 600), background)
    ImageDraw.Draw(canvas).text((10, 10), text, font=face, fill=color)
    return normalized(ink(canvas, threshold))

def glyph_iou(actual, expected):
    actual, expected = normalized(actual), normalized(expected)
    width, height = max(actual.width, expected.width) + 4, max(actual.height, expected.height) + 4
    a = Image.new('L', (width, height))
    a.paste(actual, (2, 2))
    best = 0
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            b = Image.new('L', (width, height))
            b.paste(expected, (2 + dx, 2 + dy))
            intersection = sum(ImageChops.multiply(a, b).histogram()[255:])
            union = sum(ImageChops.lighter(a, b).histogram()[255:])
            best = max(best, intersection / union if union else 1)
    return best

visual_rows = []
for ordinal, (n, index) in enumerate(zip(expected_values, frame_indices, strict=True), 1):
    path = WORK / f'frames/value-{ordinal:03d}.png'
    with Image.open(path) as original:
        image = original.convert('RGB')
    fields = [('main', str(n), 360, '#51341f', '#fffaf0', (150, 295, 1100, 595), 137),
              ('reading', words(n), 42, '#205b57', '#fffaf0', (120, 600, 1340, 675), 137)]
    start = 1 if n <= 4 else 293 if n >= 296 else n - 3
    window = list(range(start, start + 7))
    for value, center in zip(window, (250, 410, 570, 730, 890, 1050, 1210), strict=True):
        fields.append((f'ticket-{value}', str(value), 46, '#205b57' if value % 2 else '#aaa596',
                       '#cfe5d5' if value == n else '#eef2df' if value % 2 else '#f4f0e6',
                       (center - 55, 932, center + 55, 982), 200))
    scores = {}
    for name, text, size, color, background, box, threshold in fields:
        actual = ink(image.crop(box), threshold)
        expected = expected_glyph(text, size, color, background, threshold)
        score = glyph_iou(actual, expected)
        scores[name] = score
        check(score >= .96, f'Frame {index} value {n} field {name}: glyph IoU {score:.6f}')
    visual_rows.append({'value': n, 'frame_index': index, 'time_s': index / 30,
                        'expected_cardinal': words(n), 'expected_ticket_values': window, 'glyph_iou': scores,
                        'decoded_png_sha256': sha(path)})

# Save a compact 15-state evidence sheet, including both hundred transitions and longest reading.
representatives = [1, 3, 9, 11, 49, 99, 101, 149, 177, 199, 201, 249, 277, 297, 299]
sheet = Image.new('RGB', (1600, 5 * 330), '#fff8e8')
draw = ImageDraw.Draw(sheet)
for j, value in enumerate(representatives):
    ordinal = expected_values.index(value)
    with Image.open(WORK / f'frames/value-{ordinal+1:03d}.png') as source:
        thumb = source.convert('RGB').resize((512, 288))
    x, y = (j % 3) * 533, (j // 3) * 330
    sheet.paste(thumb, (x, y))
    draw.text((x + 8, y + 294), f'{value} / frame {frame_indices[ordinal]} / {frame_indices[ordinal]/30:.3f}s', fill='black')
sheet.save(DEST / 'independent-150-values-contact-sheet.png')

report = {
 'schema_version': 1, 'status': 'pass' if not failures else 'fail',
 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
 'video': ref(VIDEO), 'timeline': ref(OUT / 'timeline.json'), 'script': ref(SCRIPT),
 'source_of_expected_values': 'Own integer sequence, US-cardinal dictionary/algorithm, mathematical facts and authored cue text; producer renderer/verifier functions were not imported.',
 'fresh_extraction': {'source': 'Actual final MP4', 'native_frames': 150, 'glyph_fields': 1350,
                      'method': 'One native frame during every spoken value; independently rendered glyphs compared after bounding-box normalization, with up to one-pixel alignment tolerance.',
                      'minimum_iou': min(v for row in visual_rows for v in row['glyph_iou'].values()),
                      'iou_acceptance': .96},
 'checks': {'odd_values': len(numbers), 'utterances': len(events), 'subtitles': len(srt),
            'ordinary_gaps_2s': gaps[2], 'teaching_gaps_10s': gaps[10], 'minimum_duration_s': 480,
            'actual_video_duration_s': float(probe['format']['duration']),
            'expected_numeric_pcm_s': numeric_duration, 'total_duration_from_pcm_and_waits_s': numeric_duration + 364.4,
            'authored_dialogue_cues': len(script_lines), 'chapters': len(chapter_values)},
 'mathematical_review': {'positive_odds_from_one_by_two': all(n % 2 and n == 1 + 2*i for i, n in enumerate(expected_values)),
                         'pairs': [{'quantity': n, 'pairs': (n-1)//2, 'left_over': 1} for n in (1,5,9)],
                         'ninety_nine_add_two': 99 + 2 == 101, 'comparison_100_even': 100 % 2 == 0,
                         'last_odd_below_300': 299, 'end_never_advances_to_301': True},
 'numeric_records': numeric_records, 'native_visual_records': visual_rows,
 'issues': failures,
 'not_performed': ['Fresh ASR/CTC or acoustic analysis; assigned to the audio audit.',
                   'Continuous human full-video viewing or listening is not claimed.'],
 'unchanged_production_inputs': True
}
(DEST / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(DEST / 'report.txt').write_text(
    f'奇数動画 v002 内容の独立再チェック: {report["status"].upper()}\n\n'
    '1〜299の全150奇数、自然な米国英語、163台詞/発話、163字幕、5チャプターを独立に照合。\n'
    '通常147境界2秒・確認2境界10秒、8分55.8秒、2組+1/4組+1、99+2=101は仕様と整合。\n'
    f'完成MP4から全150値の原寸画像を新たに抽出し、主数値・英語読み・7枚数直線の1350欄を照合。最小IoU {report["fresh_extraction"]["minimum_iou"]:.6f}。\n'
    f'不一致件数: {len(failures)}。音響検査・新規ASR/CTCは別担当の範囲。\n', encoding='utf-8')
print(json.dumps({'status': report['status'], 'report': str(DEST / 'report.json'),
                  'failures': failures[:20], 'minimum_iou': report['fresh_extraction']['minimum_iou']}))
raise SystemExit(0 if not failures else 1)
