"""Fresh independent elementary-math/content check; no producer imports."""
from pathlib import Path
from math import isqrt, floor
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
DELIVERY = ROOT / 'output/prime-counting-001-v003'
DESIGN = ROOT / 'design/prime-counting-v1'
errors = []
checks = []

def check(label, passed, detail=None):
    checks.append({'check': label, 'passed': bool(passed), 'detail': detail})
    if not passed:
        errors.append(label)

def load(path):
    return json.loads(path.read_text())

def divisors(n):
    return [d for d in range(1, n + 1) if n % d == 0]

def is_prime(n):
    if n < 2:
        return False
    return all(n % d for d in range(2, isqrt(n) + 1))

ONES = ('zero one two three four five six seven eight nine ten eleven twelve '
        'thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split()
TENS = 'zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()

def cardinal(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ('-' + ONES[n % 10] if n % 10 else '')
    return ONES[n // 100] + ' hundred' + (' ' + cardinal(n % 100) if n % 100 else '')

def stamp_seconds(s):
    h, m, rest = s.split(':')
    sec, ms = rest.split(',')
    return 3600 * int(h) + 60 * int(m) + int(sec) + int(ms) / 1000

def parse_srt(path):
    cues = []
    for block in re.split(r'\n\s*\n', path.read_text().strip()):
        rows = block.splitlines()
        start, end = rows[1].split(' --> ')
        cues.append({'number': int(rows[0]), 'start_s': stamp_seconds(start),
                     'end_s': stamp_seconds(end), 'text': '\n'.join(rows[2:])})
    return cues

timeline = load(DELIVERY / 'timeline.json')
count_lines = load(DESIGN / 'count-lines.json')
narration = load(DESIGN / 'narration.json')
primes = [n for n in range(0, 1000) if is_prime(n)]
check('independent trial-division result',
      len(primes) == 168 and sum(primes) == 76127 and primes[0] == 2 and primes[-1] == 997,
      {'count': len(primes), 'sum': sum(primes), 'first': primes[0], 'last': primes[-1]})

sources = {
    'design count lines': (count_lines, 'value', 'text'),
    'design narration count lines': ([e for e in narration if e['kind'] == 'count'], 'value', 'text'),
    'timeline counted states': (timeline['counted_states'], 'decimal_value', 'spoken_text'),
    'timeline count voice events': ([e for e in timeline['voice_events'] if e['kind'] == 'count'], 'decimal_value', 'text'),
}
for label, (rows, value_field, text_field) in sources.items():
    check(label + ' exhaustive ordered values', [e[value_field] for e in rows] == primes)
    check(label + ' 1..168 ordinals', [e['ordinal'] for e in rows] == list(range(1, 169)))
    check(label + ' all American English cardinal strings',
          all(e[text_field] == cardinal(e[value_field]) for e in rows))
    factor_rows = [e for e in rows if 'positive_factors' in e]
    if factor_rows:
        check(label + ' exhaustive positive factors',
              all(e['positive_factors'] == divisors(e[value_field]) for e in factor_rows),
              {'rows': len(factor_rows)})

check('timeline published range/count',
      (timeline['count_start'], timeline['count_end'], timeline['upper_bound_exclusive'], timeline['counted_values'])
      == (2, 997, 1000, 168))
events = timeline['voice_events']
check('188 utterances with exact script text and order',
      len(events) == 188 and [(e['id'], e['text']) for e in events] == [(e['id'], e['text']) for e in narration])
check('all voice events ordered without overlaps and inside duration',
      all(0 <= e['start_s'] < e['end_s'] <= timeline['duration_s'] for e in events)
      and all(a['end_s'] <= b['start_s'] for a, b in zip(events, events[1:])))
check('all count display windows contain whole voice',
      all(e['display_start_s'] <= e['voice_start_s'] < e['voice_end_s'] <= e['display_end_s']
          for e in timeline['counted_states']))

captions = parse_srt(DELIVERY / 'english-captions.srt')
check('caption copies identical',
      (DELIVERY / 'subtitles.srt').read_bytes() == (DELIVERY / 'english-captions.srt').read_bytes())
check('188 sequential captions match utterance text',
      len(captions) == 188 and [c['number'] for c in captions] == list(range(1, 189))
      and [c['text'] for c in captions] == [e['text'] for e in events])
max_caption_error = max(abs(c[k] - e[k]) for c, e in zip(captions, events) for k in ['start_s', 'end_s'])
check('caption timings match timeline to millisecond rounding', max_caption_error <= 0.000500001,
      {'maximum_error_s': max_caption_error})
check('captions ordered, nonoverlapping, within timeline',
      all(0 <= c['start_s'] < c['end_s'] <= timeline['duration_s'] for c in captions)
      and all(a['end_s'] <= b['start_s'] for a, b in zip(captions, captions[1:])))

chapter_rows = (DELIVERY / 'chapters.txt').read_text().strip().splitlines()
chapter_specs = [
    (0, 'Welcome to the Mosaic Museum'),
    (timeline['counted_states'][0]['display_start_s'], 'Start counting primes'),
    (next(e['start_s'] for e in timeline['teaching'] if e['mode'] == 'nine'), 'Why nine is not prime'),
    (next(e['start_s'] for e in timeline['teaching'] if e['mode'] == 'bridge'), 'From 97 to 101'),
    (next(e['display_start_s'] for e in timeline['counted_states'] if e['value'] == 101), 'Three-digit primes'),
    (timeline['finale']['start_s'], 'All 168 primes below 1000'),
]
expected_chapters = [f'{floor(s) // 60:02d}:{floor(s) % 60:02d} {label}' for s, label in chapter_specs]
check('all 6 chapter starts match scene start integer seconds', chapter_rows == expected_chapters,
      [{'published': line, 'actual_boundary_s': spec[0], 'lead_s': spec[0] - floor(spec[0])}
       for line, spec in zip(chapter_rows, chapter_specs)])
title = (DELIVERY / 'youtube-title.txt').read_text().strip()
description = (DELIVERY / 'youtube-description.txt').read_text().strip()
check('description chapter block matches chapter file', '\n'.join(chapter_rows) in description)
check('combined upload details match current title plus description',
      (DELIVERY / 'upload-details.txt').read_text().strip() == title + '\n\n' + description)
check('description no music/SFX matches declared timeline',
      'No background music or sound effects.' in description
      and timeline['bgm'] is False and timeline['sound_effects'] == [])

factor_cases = {n: divisors(n) for n in [1, 2, 5, 6, 9, 97, 98, 99, 100, 101]}
check('teaching examples independently factored', factor_cases == {
    1: [1], 2: [1, 2], 5: [1, 5], 6: [1, 2, 3, 6], 9: [1, 3, 9],
    97: [1, 97], 98: [1, 2, 7, 14, 49, 98], 99: [1, 3, 9, 11, 33, 99],
    100: [1, 2, 4, 5, 10, 20, 25, 50, 100], 101: [1, 101]})
check('97 to 101 are consecutive primes', primes[primes.index(97) + 1] == 101)
check('only even counted prime is 2', [p for p in primes if p % 2 == 0] == [2])
mosaic = timeline['progress_mosaic']
check('14 by 12 mosaic has one space for each prime',
      mosaic['rows'] * mosaic['columns'] == mosaic['capacity'] == len(primes))

inputs = [DELIVERY / 'paspla-studio-prime-numbers-2-to-997-1080p.mp4',
          DELIVERY / 'timeline.json', DESIGN / 'count-lines.json', DESIGN / 'narration.json',
          DELIVERY / 'youtube-title.txt', DELIVERY / 'youtube-description.txt',
          DELIVERY / 'chapters.txt', DELIVERY / 'english-captions.srt', DELIVERY / 'subtitles.srt',
          DELIVERY / 'upload-details.txt']
report = {
    'reviewed_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'PASS' if not errors else 'FAIL',
    'method': 'New independent trial division of every integer 0..999; exhaustive positive factors; own American English cardinal formatter. No producer/verifier imports.',
    'inputs': [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in inputs],
    'checks': checks, 'errors': errors,
    'expected_primes': primes, 'factor_examples': factor_cases,
    'dialogue_lines_reviewed': [{'id': e['id'], 'text': e['text']} for e in narration if e['kind'] != 'count'],
    'title': title, 'title_characters': len(title), 'description': description,
    'mathematical_claim_review': {
        'definition': 'Correct: a whole number greater than one with exactly two positive factors, one and itself.',
        'one': 'Correct: one has only the single positive divisor one.',
        'two': 'Correct generally: for every even n>2, 1,2,n are distinct factors, so n is composite.',
        'rotation': 'Correct: rotating a rectangular array does not add distinct positive divisors.',
        'nine': 'Correct: odd does not imply prime; 9=3*3 and has divisors 1,3,9.',
        '97_to_101': 'Correct: 98=2*49,99=9*11,100=10*10, while 97 and101 are prime.',
        'range_total_finale': 'Correct: 168 primes under1000; first2 and last997.',
        'English': 'All20 non-count lines, title and description reviewed; no material grammar issue or contradictory claim. one hundred one is standard American English.',
    },
    'material_limits': ['This content report does not itself perform a new ASR or auditory review.',
                        'Caption timing compared with declared utterance windows, not new acoustic alignment.',
                        'Full-frame rendering, motion adequacy and whole-clip audio/video checks belong to parallel review reports.',
                        'Mosaic metadata cardinality is checked here; decoded raster tiles are checked separately.'],
}
(OUT / 'content-data-recheck.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'checks': len(checks), 'errors': errors,
                  'maximum_caption_error_s': max_caption_error,
                  'report': str(OUT / 'content-data-recheck.json')}, ensure_ascii=False))
