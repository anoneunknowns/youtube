"""Independent content, decoded-raster and waveform checks for Fibonacci delivery.

This verifier does not import a Fibonacci producer, renderer, number formatter or
its returned bounding boxes. Layout rectangles express the agreed design intent;
glyphs, arithmetic, cardinal parsing and observed foreground are derived here.
Reports and decode logs require a new directory and preserve earlier evidence.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat, ImageMath

if __package__:
    from .component_alignment import raster_centering_report
    from . import verify_prime_video as media
    from . import verify_video as technical
else:
    from component_alignment import raster_centering_report
    import verify_prime_video as media
    import verify_video as technical

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/fibonacci-counting-v1'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BACKDROP = ROOT / 'assets/library/worlds/cloud-post-office/backgrounds/v001/cloud-post-office-background.png'
FPS, RATE, SIZE = 30, 48000, (1920, 1080)
INK, TEAL, BLUE, RUST, MUTED = '#284455', '#287d82', '#477aa2', '#b55e46', '#667b86'
PALE, PEACH, CREAM = '#e8f2ed', '#f7e5d5', '#fffaf0'
OPERANDS = ((118, 366, 430, 468), (558, 366, 870, 468), (998, 366, 1310, 468))
CENTERS = (274, 714, 1154)
MAIN = (118, 640, 1310, 794)
READING = (105, 825, 1335, 929)
PROGRESS = (130, 968, 1310, 1016)
CHECKPOINTS = (2, 8, 13, 18, 26, 39)
RECURRENCE_TEXT = 'F_n = F_(n-2) + F_(n-1)'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sample(at):
    return round(at * RATE)


def frame_at(at):
    return math.ceil(at * FPS - 1e-7)


def fibonacci():
    """Binomial identity, independently of the producer's iterative recurrence."""
    return tuple(0 if n == 0 else sum(math.comb(n-k-1, k) for k in range((n-1)//2+1)) for n in range(41))


def cardinal(value):
    small = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = dict(zip(range(20, 100, 10), 'twenty thirty forty fifty sixty seventy eighty ninety'.split()))
    def group(n):
        if n < 20:
            return small[n]
        if n < 100:
            return tens[n // 10 * 10] + ('-' + small[n % 10] if n % 10 else '')
        return small[n // 100] + ' hundred' + (' ' + group(n % 100) if n % 100 else '')
    require(isinstance(value, int) and 0 <= value < 1_000_000_000, 'Unsupported cardinal')
    parts = []
    remainder = value
    for divisor, unit in ((1_000_000, 'million'), (1000, 'thousand')):
        quotient, remainder = divmod(remainder, divisor)
        if quotient:
            parts.append(group(quotient) + ' ' + unit)
    if remainder or not parts:
        parts.append(group(remainder))
    return ' '.join(parts)


def parse_cardinal(text):
    """Strict inverse; reject malformed combinations rather than adding tokens."""
    if not isinstance(text, str) or not re.fullmatch(r'[a-z]+(?:[ -][a-z]+)*', text):
        return None
    small = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(), range(20)))
    tens = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))
    def under_hundred(tokens):
        if len(tokens) == 1:
            return small.get(tokens[0], tens.get(tokens[0]))
        if len(tokens) == 2 and tokens[0] in tens and 1 <= small.get(tokens[1], -1) <= 9:
            return tens[tokens[0]] + small[tokens[1]]
        return None
    def under_thousand(tokens):
        if 'hundred' not in tokens:
            return under_hundred(tokens)
        if len(tokens) < 2 or tokens[1] != 'hundred' or tokens.count('hundred') != 1 or not 1 <= small.get(tokens[0], -1) <= 9:
            return None
        tail = under_hundred(tokens[2:]) if len(tokens) > 2 else 0
        return small[tokens[0]] * 100 + tail if tail is not None and (tail > 0 or len(tokens) == 2) else None
    tokens = text.replace('-', ' ').split()
    total = 0
    for unit, divisor in (('million', 1_000_000), ('thousand', 1000)):
        if unit in tokens:
            if tokens.count(unit) != 1:
                return None
            at = tokens.index(unit)
            head = under_thousand(tokens[:at])
            if not head:
                return None
            total += head * divisor
            tokens = tokens[at+1:]
    tail = under_thousand(tokens) if tokens else 0
    if tail is None or (total and tokens and tail == 0):
        return None
    result = total + tail
    return result if cardinal(result).replace('-', ' ') == text.replace('-', ' ') else None


def checked_design(directory=DESIGN):
    values = fibonacci()
    require(len(values) == 41 and values[:4] == (0, 1, 1, 2) and values[-2:] == (63245986, 102334155), 'Independent Fibonacci invariant failed')
    counts = json.loads((Path(directory)/'count-lines.json').read_text())
    authored = json.loads((Path(directory)/'narration.json').read_text())
    require(len(counts) == 41 and len(authored) == len({r['id'] for r in authored}) == 104, 'Missing/duplicate authored entries')
    by_id = {r['id']: r for r in authored}
    for n, (row, value) in enumerate(zip(counts, values, strict=True)):
        require((row['index'], row['ordinal'], row['value']) == (n, n+1, value), f'Wrong indexed Fibonacci value F{n}')
        require(row['text'] == cardinal(value) and parse_cardinal(row['text']) == value, f'Wrong English cardinal F{n}')
        require(by_id[f'N{n:03}']['text'] == cardinal(value), f'Wrong count narration N{n:03}')
        if n >= 2:
            a, b = values[n-2:n]
            require((row['a'], row['b'], row['a_index'], row['b_index']) == (a, b, n-2, n-1), f'Wrong operands F{n}')
            require(by_id[f'E{n:03}']['text'] == f'{cardinal(a)} plus {cardinal(b)} equals', f'Wrong formula narration E{n:03}')
    return values, by_id, [row['id'] for row in authored]


def event_value(row):
    return row.get('value', row.get('number', row.get('c')))


def event_index(row):
    return row.get('index', row.get('n'))


def validate_schedule(plan):
    values, authored, order = checked_design()
    require(plan['fps'] == FPS and plan['duration_frames'] == frame_at(plan['duration_s']), 'Wrong 30fps frame duration')
    require(480 <= plan['duration_s'] < 1800, 'Non-Shorts runtime must be at least eight minutes')
    events = sorted(plan.get('voice_events', plan.get('events', [])), key=lambda row: row['start_s'])
    require([row['id'] for row in events] == order, 'Voice IDs missing, duplicated or reordered')
    cursor = 0
    for row in events:
        start, end = sample(row['start_s']), sample(row['end_s'])
        require(cursor <= start < end <= sample(plan['duration_s']), f'Overlapping/invalid voice event {row["id"]}')
        require(start % 2 == end % 2 == 0, 'Voice boundaries left the 24kHz source grid')
        require(row['text'] == authored[row['id']]['text'], f'Voice text differs at {row["id"]}')
        if 'duration_s' in row:
            require(abs(end-start-sample(row['duration_s'])) <= 1, f'Voice duration inconsistent at {row["id"]}')
        cursor = end
    by_id = {row['id']: row for row in events}
    states = plan['counted_states']
    require(len(states) == 41 and [event_index(s) for s in states] == list(range(41)), 'Count states omit/reorder a Fibonacci index')
    ordinary = extended = 0
    for n, state in enumerate(states):
        voice = by_id[f'N{n:03}']
        require(event_value(state) == values[n] and event_value(voice) == values[n], f'Wrong display/spoken value F{n}')
        require(sample(voice['start_s']-state['display_start_s']) == sample(.12), f'Visual lead is not .12s F{n}')
        require(sample(state['voice_start_s']) == sample(voice['start_s']) and sample(state['voice_end_s']) == sample(voice['end_s']), f'Count-state speech timing differs F{n}')
        if n >= 2:
            prefix = by_id[f'E{n:03}']
            require(sample(voice['start_s']-prefix['end_s']) == sample(.16), f'Formula/result gap differs F{n}')
            require((state['a'], state['b']) == values[n-2:n], f'State operands differ F{n}')
            require(sample(state['formula_start_s']) == sample(prefix['start_s']) and sample(state['formula_end_s']) == sample(prefix['end_s']), f'Formula-state timing differs F{n}')
        if n < 40:
            next_voice = by_id[f'N{n+1:03}'] if n == 0 else by_id[f'E{n+1:03}']
            if n in CHECKPOINTS:
                explanations = [r for r in events if voice['end_s'] <= r['start_s'] < next_voice['start_s']]
                require(len(explanations) == 2 and all(r['id'].startswith('T') for r in explanations), f'Missing two checkpoint explanations after F{n}')
                require(sample(explanations[0]['start_s']-voice['end_s']) == sample(.6), 'Checkpoint first sentence gap differs')
                require(sample(explanations[1]['start_s']-explanations[0]['end_s']) == sample(.6), 'Checkpoint sentence gap differs')
                require(sample(next_voice['start_s']-explanations[-1]['end_s']) == sample(2.6), 'Checkpoint final settling gap differs')
                extended += 1
            else:
                require(sample(next_voice['start_s']-voice['end_s']) == sample(2), f'Ordinary N-end→next-E-start gap differs after F{n}')
                ordinary += 1
    require(ordinary == 34 and extended == 6, 'Unexpected boundary coverage')
    measured_speech = sum(row['end_s']-row['start_s'] for row in events)
    require(abs(plan['duration_s']-measured_speech-107.04) <= 1/FPS+1/RATE, 'Duration differs from adopted speech plus fixed transitions')
    segments = plan['visual_segments']
    require(segments and segments[0]['start_s'] == 0 and abs(segments[-1]['end_s']-plan['duration_s']) < 1e-6, 'Visual coverage misses endpoints')
    for segment in segments:
        require(segment['start_s'] < segment['end_s'], 'Empty visual segment')
        n = event_index(segment)
        if n is not None:
            require(0 <= n <= 40, 'Visual index outside F0..F40')
        params = segment.get('params', {})
        if segment['mode'] == 'count':
            require(n is not None and n >= 2, 'Generated count mode needs F2..F40 index')
            state = states[n]
            stage = params.get('stage')
            require(stage in ('input-a','input-b','flow','result','transfer'), 'Unknown arithmetic display stage')
            if stage in ('input-a','input-b','flow'):
                require(segment['start_s'] >= state['formula_start_s']-1e-7 and segment['end_s'] <= state['display_start_s']+1e-7,
                        f'Unrevealed stage is outside expression window F{n}')
            elif stage == 'result':
                require(segment['start_s'] >= state['display_start_s']-1e-7, f'Result revealed before N-.12 F{n}')
            else:
                require(state.get('transfer_start_s') is not None and
                        abs(segment['start_s']-state['transfer_start_s']) < 1e-7 and
                        abs(params.get('transfer_end_s', -1)-state['transfer_end_s']) < 1e-7,
                        f'Handoff timing disagrees F{n}')
                require(params.get('next_pair') == [values[n-1], values[n]] and params.get('next_pair_indices') == [n-1,n],
                        f'Handoff keeps the wrong values or labels F{n}')
        if segment['mode'] == 'replay':
            require(params.get('show_replay_label') is True, 'Explanation omits REPLAY designation')
            require(n in CHECKPOINTS and params.get('after_index') == n, 'Replay changed the counted index')
            voice = by_id.get(params.get('voice_event_id'))
            require(voice is not None and voice['id'].startswith('T') and
                    abs(segment['start_s']-(voice['start_s']-.12)) < 1e-7, 'Replay does not match an actual explanation cue')
    for left, right in zip(segments, segments[1:]):
        require(abs(left['end_s']-right['start_s']) < 1e-6, 'Visual segments overlap or leave a hole')
    require(any(row['mode'] == 'finale' for row in segments), 'Missing finale')
    require({event_index(row) for row in segments if row['mode'] == 'count'} == set(range(2,41)), 'Visual schedule omits generated terms')
    require({event_index(row) for row in segments if row['mode'] == 'replay'} == set(CHECKPOINTS), 'Visual schedule omits a required checkpoint')
    finale = next(row for row in segments if row['mode'] == 'finale')
    require(finale.get('params',{}).get('history_indices') == list(range(41)), 'Final history omits an index or deduplicates ones')
    return events, states, segments, {'passed': True, 'terms': 41, 'generated_by_addition': 39, 'voice_events': 104,
        'ordinary_two_second_boundaries': ordinary, 'checkpoint_boundaries': extended,
        'initial_zero_and_distinct_ones': list(values[:3]), 'independent_sequence_method': 'binomial coefficient sum',
        'all_cardinals_inverse_parsed': 41, 'measured_speech_duration_s': measured_speech, 'fixed_transition_seconds': 107.04}


@lru_cache(maxsize=100)
def font(size):
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=100)
def split_reading(text, size=32):
    if font(size).getlength(text) <= 1220:
        return (text,)
    tokens = text.split()
    _, index = min((max(font(size).getlength(' '.join(tokens[:i])), font(size).getlength(' '.join(tokens[i:]))), i) for i in range(1, len(tokens)))
    result = (' '.join(tokens[:index]), ' '.join(tokens[index:]))
    require(max(font(size).getlength(line) for line in result) <= 1220, 'Independent English reading exceeds fixed two-line field')
    return result


@lru_cache(maxsize=2000)
def glyph_alpha(text, size):
    if text == RECURRENCE_TEXT:
        # Independent typesetting of the mathematically required recurrence.
        pieces = [('F',False),('n',True),(' = ',False),('F',False),('n−2',True),(' + ',False),('F',False),('n−1',True)]
        lengths = [font(round(size*.57) if sub else size).getlength(piece) for piece,sub in pieces]
        mask = Image.new('L',(math.ceil(sum(lengths))+80,round(size*1.8)+80))
        draw = ImageDraw.Draw(mask);x = 40
        for (piece,sub),length in zip(pieces,lengths):
            draw.text((x,40+size*(.51 if sub else 0)),piece,font=font(round(size*.57) if sub else size),fill=255,anchor='lt')
            x += length
        return mask
    lines = text.split('\n')
    masks = []
    for line in lines:
        box = font(size).getbbox(line)
        canvas = Image.new('L', (box[2]-box[0]+80, box[3]-box[1]+80))
        ImageDraw.Draw(canvas).text((40-box[0], 40-box[1]), line, font=font(size), fill=255)
        bounds = canvas.point(lambda x: 255 if x >= 128 else 0).getbbox()
        require(bounds is not None, 'Empty expected glyph')
        masks.append(canvas.crop(bounds))
    width = max(mask.width for mask in masks)
    height = sum(mask.height for mask in masks)+14*(len(masks)-1)
    group = Image.new('L', (width+80, height+80))
    top = 40
    for mask in masks:
        group.paste(mask, (40+round((width-mask.width)/2), top))
        top += mask.height+14
    return group


@lru_cache(maxsize=8)
def background(divisor=1):
    im = ImageOps.fit(Image.open(BACKDROP).convert('RGB'), SIZE, Image.Resampling.LANCZOS)
    return im if divisor == 1 else im.resize((SIZE[0]//divisor, SIZE[1]//divisor), Image.Resampling.BOX)


def rgb(color):
    return tuple(bytes.fromhex(color.removeprefix('#')))


def crop_box(field, divisor):
    return tuple(math.floor(v/divisor) for v in field)


def field_background(field, fill, divisor=1):
    if fill:
        box = crop_box(field, divisor)
        return Image.new('RGB', (box[2]-box[0], box[3]-box[1]), fill)
    return background(divisor).crop(crop_box(field, divisor))


def observed_ink(image, field, color, fill=None, divisor=1):
    """Actual decoded half-contrast foreground; no expected text/shape in mask."""
    actual = image.crop(crop_box(field, divisor))
    base = field_background(field, fill, divisor)
    color = rgb(color) if isinstance(color, str) else color
    def inverse_alpha(env):
        direction = [env[f'b{i}']-color[i] for i in range(3)]
        difference = [env[f'b{i}']-env[f'c{i}'] for i in range(3)]
        numerator = sum(d*v for d,v in zip(direction,difference))
        denominator = sum(d*d for d in direction)+1
        return numerator*255/denominator
    inputs = {f'b{i}':c.convert('I') for i,c in enumerate(base.split())}
    inputs.update({f'c{i}':c.convert('I') for i,c in enumerate(actual.split())})
    alpha = ImageMath.lambda_eval(inverse_alpha,**inputs).convert('L')
    mask = alpha.point(lambda v:255 if v >= 128 else 0)
    # Gate colour to reject unrelated backdrop texture, borders and nearby paths.
    gates = [c.point(lambda v, target=t: 255 if abs(v-target) <= 90 else 0) for c, t in zip(actual.split(), color)]
    return ImageChops.darker(mask, ImageChops.darker(gates[0], ImageChops.darker(gates[1], gates[2])))


def overlap(actual, expected):
    union = ImageChops.lighter(actual, expected).histogram()[255]
    return ImageChops.darker(actual, expected).histogram()[255]/union if union else 1.


@lru_cache(maxsize=2400)
def expected_mask(text, size, field, divisor=1, dx=0, dy=0, alpha_threshold=128):
    alpha = glyph_alpha(text, size)
    bounds = alpha.point(lambda v: 255 if v >= 128 else 0).getbbox()
    origin = crop_box(field, divisor)
    # Work on the absolute native grid before the full-frame scale, including
    # fields whose edges are not multiples of the scale divisor.
    canvas = Image.new('L', ((origin[2]-origin[0])*divisor, (origin[3]-origin[1])*divisor))
    x = round((field[0]+field[2]-bounds[0]-bounds[2])/2)-origin[0]*divisor+dx
    y = round((field[1]+field[3]-bounds[1]-bounds[3])/2)-origin[1]*divisor+dy
    canvas.paste(alpha, (x, y))
    if divisor != 1:
        canvas = canvas.resize((canvas.width//divisor, canvas.height//divisor), Image.Resampling.BOX)
    return canvas.point(lambda v: 255 if v >= alpha_threshold else 0)


_placement = {}


def glyph_score(actual, text, size, field, divisor=1):
    # Dictionary alternatives are scored against other observed strings too;
    # their alignment cache must never leak into a later correct observation.
    key = text, size, tuple(field), divisor, hashlib.sha256(actual.tobytes()).digest()
    if key not in _placement:
        _placement[key] = max((overlap(actual, expected_mask(text, size, tuple(field), divisor, x, y)), x, y)
                              for y in (-1, 0, 1) for x in (-1, 0, 1))[1:]
    dx, dy = _placement[key]
    score = overlap(actual, expected_mask(text, size, tuple(field), divisor, dx, dy))
    if divisor in (1,2) and score < .975:
        # H.264 4:2:0 alters the AA edge, especially on 15px history labels.
        # The finite AA thresholds change only the same independently authored
        # glyph's contour; no alternate string, scale or center tolerance is
        # introduced. Native centers are still measured separately at <=1px.
        score = max([score]+[overlap(actual,expected_mask(text,size,tuple(field),divisor,dx,dy,t))
                             for t in range(112,233,8)])
    return score


def label(name, text, size, field, color=INK, fill=None):
    return {'name': name, 'text': text, 'size': size, 'field': tuple(field), 'color': color, 'fill': fill}


def count_labels(n, stage='result', transfer=0):
    require(2 <= n <= 40, 'Generated-term label index outside domain')
    values = fibonacci()
    a, b, c = values[n-2:n+1]
    small = n <= 20
    equation_size = 88 if small else 47
    labels = [label('recurrence',RECURRENCE_TEXT,47,(130,220,1300,286))]
    if stage == 'transfer':
        for i, value in enumerate((b, c)):
            x = (714 if i == 0 else 1154)-440*transfer
            y = 417+135*math.sin(math.pi*transfer)
            # Dynamic fields share the exact finite destination region; expected
            # values still come exclusively from the independent binomial sum.
            labels.append(label(f'transferred-{i}', f'{value:,}', equation_size,
                                (x-156, y-51, x+156, y+51), BLUE if i == 0 else TEAL, PALE))
            labels.append(label(f'transferred-index-{i}', f'F{n-1+i}', 23,
                                (x-90, y-118, x+90, y-86), TEAL))
    else:
        for i, (value, index, color) in enumerate(((a, n-2, BLUE), (b, n-1, TEAL), (c, n, RUST))):
            x = CENTERS[i]
            role = ('OLDER', 'NEWER', 'NEW')[i]
            labels.append(label(f'index-{i}', f'{role} · F{index}', 23, (x-163, 301, x+163, 332), color))
            hidden = i == 2 and stage in ('input-a', 'input-b', 'flow')
            labels.append(label(f'operand-{i}', '?' if hidden else f'{value:,}', 70 if hidden else equation_size,
                                OPERANDS[i], color, PALE if i != 2 else PEACH))
        labels += [label('plus', '+', 62, (454,367,534,466), TEAL), label('equals', '=', 62, (894,367,974,466), RUST)]
    if stage in ('result', 'transfer'):
        labels.append(label('new-label', 'NEW NUMBER', 25,
                            (140,645,1320,679) if stage == 'transfer' else (140,575,1320,615), RUST))
        labels.append(label('main-result', f'{c:,}', 126 if small else 112,
                            (118,690,1310,815) if stage == 'transfer' else MAIN))
        labels.append(label('result-reading', '\n'.join(split_reading(cardinal(c))), 32, READING, TEAL))
    else:
        labels.append(label('pending-result', 'The next number is on its way.', 40, (130,680,1310,770), MUTED))
    progress = f'TERM {n+1} OF 41  ·  INDEX n = {n}'
    progress = 'KEEP THE LAST TWO. GO AGAIN.' if stage == 'transfer' else progress if stage == 'result' else 'NEXT: '+progress
    labels.append(label('term-progress', progress, 25, PROGRESS, MUTED))
    return labels


_identifications = {}


def numeric_identification(actual, row, correct_score):
    """Reject a wrong digit even when a long string's global IoU is high."""
    text = row['text']
    key = (hashlib.sha256(actual.tobytes()).digest(),text,row['size'],row['field'])
    if key in _identifications:
        return _identifications[key]
    alternatives = set()
    if re.fullmatch(r'[0-9][0-9,]*',text):
        for i,char in enumerate(text):
            if char.isdigit():
                alternatives.update(text[:i]+digit+text[i+1:] for digit in '0123456789' if digit != char)
    else:
        value = parse_cardinal(text.replace('\n',' '))
        if value is None:
            return None
        def reading(v):
            return '\n'.join(split_reading(cardinal(v),row['size'])) if '\n' in text else cardinal(v)
        alternatives.update(reading(v) for v in fibonacci() if v != value)
        for power in range(len(str(value))):
            alternatives.update(reading(v) for v in (value-10**power,value+10**power) if 0 <= v < 1_000_000_000 and v != value)
    other_score,other_text = max((glyph_score(actual,other,row['size'],row['field']),other) for other in alternatives)
    margin = correct_score-other_score
    result = {'nearest_wrong_text':other_text,'nearest_wrong_text_iou':other_score,
              'correct_text_margin':margin,'minimum_correct_text_margin':.005,
              'minimum_identification_iou':.90,'numeric_identification_passed':correct_score >= .90 and margin >= .005,
              'candidate_method':'All one-digit substitutions in the exact numeral, or independent Fibonacci/adjacent-place-value English cardinals.'}
    _identifications[key] = result
    return result


def inspect_labels(image, labels, frame, divisor=1):
    results = []
    for row in labels:
        if divisor != 1 and row['size'] < 30:
            # Fine labels/history are measured and identified at native size.
            # The full-frame scale pass tracks primary numerals, English
            # readings, operators and carry digits rather than tiny captions.
            continue
        actual = observed_ink(image, row['field'], row['color'], row['fill'], divisor)
        score = glyph_score(actual, row['text'], row['size'], row['field'], divisor)
        if divisor == 1:
            report = raster_centering_report(actual, row['field'], origin_xy=crop_box(row['field'],1)[:2],
                                            name=f'frame{frame}/{row["name"]}', tolerance_px=1)
        else:
            report = {'name': row['name'], 'passed': actual.getbbox() is not None}
        minimum = .94 if divisor == 1 else ((.87 if row['size'] < 35 else .90) if divisor == 2 else (.76 if row['size'] < 35 else .83))
        report.update(text=row['text'], font_size_px=row['size'], independent_glyph_iou=score,
                      minimum_glyph_iou=minimum, foreground_rgb=rgb(row['color']), divisor=divisor)
        shape_pass = score >= minimum
        if divisor == 1 and (re.fullmatch(r'[0-9][0-9,]*',row['text']) or row['name'] == 'result-reading'):
            identified = numeric_identification(actual,row,score)
            if identified is not None:
                report.update(identified)
                shape_pass = identified['numeric_identification_passed']
        if divisor == 1 and row['size'] == 15 and re.fullmatch(r'F(?:[0-9]|[1-3][0-9]|40)',row['text']):
            # Encoded small labels must identify the right F-index among the
            # complete independent 0..40 dictionary, not merely resemble text.
            # This is required even if the absolute overlap already passes.
            alternatives = [(glyph_score(actual,f'F{n}',15,row['field']),f'F{n}')
                            for n in range(41) if f'F{n}' != row['text']]
            other_score,other_text = max(alternatives)
            margin = score-other_score
            identified = score >= .90 and margin >= .03
            report.update(index_dictionary='F0..F40',nearest_wrong_index=other_text,
                          nearest_wrong_index_iou=other_score,correct_index_margin=margin,
                          minimum_correct_index_margin=.03,minimum_identification_iou=.90,
                          index_identification_passed=identified)
            shape_pass = identified
        report['passed'] = report['passed'] and shape_pass
        results.append(report)
    if divisor == 1:
        for i, first in enumerate(results):
            if not first.get('visible_box_xyxy'):
                continue
            x1, y1, x2, y2 = first['visible_box_xyxy']
            for second in results[i+1:]:
                if not second.get('visible_box_xyxy'):
                    continue
                a, b, c, d = second['visible_box_xyxy']
                if max(x1, a) < min(x2, c) and max(y1, b) < min(y2, d):
                    first['passed'] = second['passed'] = False
                    first.setdefault('collisions', []).append(second['name'])
    return results


def segment_at(segments, at):
    starts = [row['start_s'] for row in segments]
    return segments[max(0, bisect_right(starts, at+1e-9)-1)]


def stage_at(segment, at):
    params = segment.get('params', {})
    stage = params.get('stage', segment.get('stage', 'result'))
    if stage == 'transfer':
        start = params.get('transfer_start_s', segment['start_s'])
        end = params.get('transfer_end_s', segment['end_s'])
        raw = max(0, min(1, (at-start)/(end-start)))
        # Agreed motion design uses smoothstep quantized to 30 registered
        # positions. This governs placement only, never numerical expectations.
        return stage, round(raw*raw*(3-2*raw)*30)/30
    return stage, 0


def seed_labels(n):
    value = fibonacci()[n]
    return [label('seed-index',f'F{n}',49,(120,408,1320,477),BLUE),
            label('seed-value',str(value),190,(118,530,1310,740)),
            label('result-reading',cardinal(value),32,READING,TEAL),
            label('term-progress',f'TERM {n+1} OF 41 · INDEX n = {n}',25,PROGRESS,MUTED)]


def history_labels():
    rows = []
    for n,value in enumerate(fibonacci()):
        x,y = 108+n%6*207,376+n//6*78
        color = BLUE if n < 2 else RUST if n == 40 else TEAL
        fill = PEACH if n == 40 else CREAM
        rows += [label(f'history-index-{n}',f'F{n}',15,(x+10,y+7,x+180,y+26),color,fill),
                 label(f'history-value-{n}',f'{value:,}',22,(x+8,y+32,x+182,y+59),color,fill)]
    return rows


def carry_operations(n):
    a,b,c = fibonacci()[n-2:n+1]
    columns = len(str(c))
    operations = []
    incoming = 0
    for power in range(columns):
        left,right = (a//10**power)%10,(b//10**power)%10
        total = left+right+incoming
        operations.append({'power':power,'a':left,'b':right,'incoming':incoming,'total':total,
                           'digit':total%10,'outgoing':total//10})
        incoming = total//10
    require(sum(op['digit']*10**op['power'] for op in operations) == c and incoming == 0,'Independent column reconstruction failed')
    return operations


def carry_spans(n, events):
    first,second = events[f'T{n:03}a'],events[f'T{n:03}b']
    if n == 8:
        return [(first['start_s']+.20,first['end_s']), (second['start_s'],second['end_s']-.20)]
    if n == 13:
        pivot = first['start_s']+(first['end_s']-first['start_s'])*.56
        pivot2 = second['start_s']+(second['end_s']-second['start_s'])*.43
        return [(first['start_s']+.15,pivot),(pivot,pivot2),(pivot2,second['end_s']-.20)]
    start,end = second['start_s'],second['end_s']-.20
    return [(start+(end-start)*p/4,start+(end-start)*(p+1)/4) for p in range(4)]


def carry_phase(n, at, events):
    spans = carry_spans(n,events)
    if at < spans[0][0]:
        return -1,'align',0
    if at >= spans[-1][1]:
        return len(spans)-1,'complete',1
    column = next(i for i,(_,end) in enumerate(spans) if at < end)
    start,end = spans[column]
    fraction = max(0,min(1,(at-start)/(end-start)))
    if fraction < .38:
        return column,'compute',0
    if fraction < .60:
        return column,'write',0
    fraction = (fraction-.60)/.40
    return column,'move',round(fraction*fraction*(3-2*fraction)*30)/30


def carry_labels(n, at, events):
    a,b,c = fibonacci()[n-2:n+1]
    operations = carry_operations(n)
    columns = len(operations)
    centers = {2:(450,610),3:(380,510,640),4:(300,420,540,660)}[columns]
    column,phase,fraction = carry_phase(n,at,events)
    processed = columns if phase == 'complete' else max(0,column+(phase in ('write','move')))
    rows = [label('replay-label','REPLAY',25,(980,220,1330,270),RUST),
            label('carry-indices',f'F{n-2} + F{n-1} = F{n}',25,(780,357,1350,395),MUTED),
            label('carry-replay-progress',f'REPLAY · TERM {n+1} ALREADY COUNTED',24,PROGRESS,MUTED)]
    for row,value,top,color in (('a',a,482,BLUE),('b',b,621,TEAL),('c',c,801,RUST)):
        for i,char in enumerate(str(value).rjust(columns)):
            if char == ' ':
                continue
            power = columns-1-i
            if row == 'c' and power >= processed:
                char = '?'
            x = centers[i]
            rows.append(label(f'column-{row}-{i}',char,97,(x-49,top,x+49,top+104),color,CREAM))
    for op in operations:
        power = op['power']
        if not op['outgoing'] or power >= columns-1:
            continue
        generated = phase == 'complete' or power < column or (power == column and phase == 'move')
        if not generated:
            continue
        if phase != 'complete' and power < column and (power != column-1 or phase in ('write','move')):
            continue
        x,y = centers[columns-2-power],437.5
        if phase == 'move' and power == column:
            origin = centers[columns-1-power]
            x = origin+(x-origin)*fraction
            y = 437-25*math.sin(math.pi*fraction)
        rows.append(label(f'carry-to-power-{power+1}',str(op['outgoing']),39,(x-36,y-25.5,x+36,y+25.5),RUST,CREAM))
    if phase == 'complete':
        rows += [label('carry-complete-inputs',f'{a:,} + {b:,}',42,(808,545,1360,621)),
                 label('carry-complete-result',f'= {c:,}',54,(808,655,1360,748),TEAL)]
    elif column >= 0:
        op = operations[column]
        text = f'{op["a"]} + {op["b"]}' + (f' + {op["incoming"]}' if op['incoming'] else '') + f' = {op["total"]}'
        rows.append(label('carry-current-step',text,37,(812,423,1360,497),RUST))
        rows.append(label('carry-step-number',f'STEP {column+1} OF {columns}',27,(814,844,1350,897),MUTED))
    return rows


def group_labels():
    rows = [label('replay-label','REPLAY',25,(980,220,1330,270),RUST)]
    centers = (400,490,580,715,805,895)
    for name,value,top,color in (('a',46368,465,BLUE),('b',75025,610,TEAL),('c',121393,805,RUST)):
        for i,char in enumerate(str(value).rjust(6)):
            if char != ' ':
                x = centers[i]
                rows.append(label(f'group-{name}-{i}',char,91,(x-41,top,x+41,top+104),color))
        rows.append(label(f'group-comma-{name}',',',69,(632,top+31,662,top+104),color))
    return rows


def labels_for_segment(segment, at, plan=None):
    mode,n = segment['mode'],event_index(segment)
    if mode == 'count' and n is not None and n >= 2:
        stage, transfer = stage_at(segment, at)
        return count_labels(n, stage, transfer)
    if mode == 'seeds' and n in (0,1):
        return seed_labels(n)
    if plan is None:
        return []
    events = {event['id']:event for event in plan['voice_events']}
    if mode == 'replay':
        if n in (8,13,18):
            return carry_labels(n,at,events)
        if n == 2:
            rows = [row for row in count_labels(2) if row['name'] != 'result-reading']
            rows += [label('replay-label','REPLAY',24,(1010,522,1320,566),RUST),
                     label('repeated-one','F1 = 1  and  F2 = 1\nSame value. Two different terms.',35,(155,831,1285,926),TEAL,CREAM)]
            return rows
        if n == 26:
            return group_labels()
        if n == 39:
            return count_labels(40,'input-a')+[label('final-pair-replay','REPLAY · THE FINAL PAIR',22,(932,220,1342,272),RUST)]
    if mode == 'finale':
        focus = 'history'
        for ident,name in (('O01','history'),('O02','finale'),('O03','history'),('O04','finale')):
            if at >= events[ident]['start_s']-.12:
                focus = name
        if focus == 'history':
            return history_labels()
        return [label('final-value',f'{fibonacci()[-1]:,}',124,(103,426,1348,594)),
                label('final-recurrence',RECURRENCE_TEXT,53,(130,781,1320,871)),
                label('final-threshold','F40  ·  THE FIRST TERM ABOVE 100 MILLION',29,(100,653,1350,711),RUST)]
    if mode == 'opening' and at < events['I08']['start_s']-.12:
        rows = []
        for x,value,name,color in ((410,0,'F0',BLUE),(1020,1,'F1',TEAL)):
            rows += [label(f'opening-seed-{value}',str(value),112,(x-175,694,x+175,815),color,PALE),
                     label(f'opening-index-{value}',name,25,(x-150,831,x+150,867),color,PALE)]
        return rows
    if mode == 'opening':
        return [label('range-threshold','100,000,000',113,(100,590,1340,749))]
    if mode == 'legend' and at >= events['I07']['start_s']-.12:
        return [label('value-example','1,000',142,(350,493,1090,666),INK,PALE)]
    if mode == 'legend':
        return count_labels(2,'input-a' if at < events['I06']['start_s']-.12 else 'flow')
    if mode == 'rule' and at >= events['I04']['start_s']-.12:
        rows = []
        for x,n,color in ((300,0,BLUE),(715,1,TEAL),(1130,2,RUST)):
            rows += [label(f'index-example-{n}',f'F{n}',68,(x-140,464,x+140,557),color,PALE),
                     label(f'index-value-{n}',str(fibonacci()[n]),95,(x-140,580,x+140,691),INK,PALE)]
        return rows
    if mode == 'rule':
        return [label('large-recurrence',RECURRENCE_TEXT,92,(105,410,1335,565)),
                label('rule-domain','n ≥ 2',43,(340,590,1100,650),MUTED),
                label('rule-initials','F0 = 0    ·    F1 = 1',37,(100,946,1340,1004),TEAL)]
    return []


def unrevealed_reading_check(image, segment, at, divisor=1):
    """An output may not leak through its English reading before N-.12."""
    if segment['mode'] != 'count' or stage_at(segment,at)[0] not in ('input-a','input-b','flow'):
        return None
    mask = observed_ink(image,READING,TEAL,None,divisor)
    pixels = mask.histogram()[255]
    return {'name':'unrevealed-result-reading','foreground_pixels':pixels,
            'allowed_pixels':0,'passed':pixels == 0,'field':list(READING),
            'extraction':'Independent backdrop/teal half-contrast mask; no expected result glyph is used.'}


def visual_checks(video, plan, states, segments, ffmpeg, directory):
    errors, native_records, minimums = [], [], defaultdict(lambda: 1.)
    decoded, tracked = 0, Counter()
    native_indices = {plan['duration_frames']-1}
    for state in states:
        native_indices.add(frame_at((state['voice_start_s']+state['voice_end_s'])/2))
        for key in ('display_start_s', 'transfer_start_s', 'transfer_end_s'):
            if state.get(key) is not None:
                for delta in (-1/FPS, 0, 1/FPS):
                    native_indices.add(frame_at(state[key]+delta))
        if state.get('transfer_start_s') is not None:
            native_indices.add(frame_at((state['transfer_start_s']+state['transfer_end_s'])/2))
    for segment in segments:
        native_indices.add(frame_at((segment['start_s']+segment['end_s'])/2))
    voice_by_id = {row['id']:row for row in plan['voice_events']}
    for n in (8,13,18):
        spans = carry_spans(n,voice_by_id)
        native_indices.add(frame_at(spans[0][0]-.04))
        for start,end in spans:
            for fraction in (0,.19,.39,.49,.61,.80,.99,1):
                native_indices.add(frame_at(start+(end-start)*fraction))
        native_indices.add(frame_at(spans[-1][1]+.04))
    for ident in ('I04','I06','I07','I08','O01','O02','O03','O04'):
        native_indices.add(frame_at(voice_by_id[ident]['start_s']+.2))
    # The shared helper only decodes pixels; it supplies no Fibonacci labels.
    for frame, image in media.decoded_frames(video, ffmpeg, directory/'all-frame-decode.log', 2):
        decoded += 1
        at = frame/FPS
        segment = segment_at(segments, at)
        if at < .8 or at >= plan['duration_s']-2:
            continue
        labels = labels_for_segment(segment, at, plan)
        # Dynamic native glyph placement is checked below; half-grid tracking
        # focuses on fixed frames so moving subpixel edges do not hide faults.
        if stage_at(segment, at)[0] == 'transfer':
            continue
        absent = unrevealed_reading_check(image,segment,at,2)
        if absent is not None and not absent['passed'] and len(errors)<100:
            errors.append(f'Frame{frame}: English result appeared before its reveal ({absent["foreground_pixels"]} pixels)')
        for report in inspect_labels(image, labels, frame, 2):
            tracked[event_index(segment)] += 1
            key = report['name']
            minimums[key] = min(minimums[key], report['independent_glyph_iou'])
            if not report['passed'] and len(errors) < 100:
                errors.append(f'Frame{frame}/{key}/{report["text"]}: IoU={report["independent_glyph_iou"]:.6f}')
    require(decoded == plan['duration_frames'], 'Full decode has wrong frame count')
    require(set(tracked) >= set(range(41)), 'All-frame glyph tracking failed to cover all indexed terms')
    native_indices = sorted(i for i in native_indices if 0 <= i < plan['duration_frames'])
    thumbnails = []
    for frame, image in media.decoded_frames(video, ffmpeg, directory/'native-decode.log', 1, native_indices):
        at = frame/FPS
        segment = segment_at(segments, at)
        labels = labels_for_segment(segment, at, plan) if .8 <= at < plan['duration_s']-2 else []
        reports = inspect_labels(image, labels, frame)
        absent = unrevealed_reading_check(image,segment,at) if .8 <= at < plan['duration_s']-2 else None
        failures = [r for r in reports if not r['passed']]
        errors.extend(f'Native{frame}/{r["name"]}/{r["text"]}: glyph or two-axis alignment failed' for r in failures)
        if absent is not None and not absent['passed']:
            errors.append(f'Native{frame}: English result exposed before reveal')
        native_records.append({'frame':frame, 'at_s':at, 'mode':segment['mode'], 'index':event_index(segment), 'components':reports,
                               'intentional_absence_checks':[absent] if absent is not None else []})
        if failures or segment['mode'] != 'count' or frame in {frame_at((s['voice_start_s']+s['voice_end_s'])/2) for s in states}:
            image.save(directory/f'native-frame-{frame:06d}.png')
            thumbnails.append((frame, segment['mode'], image.resize((480,270), Image.Resampling.LANCZOS)))
    sheet = Image.new('RGB', (1440, max(1, math.ceil(len(thumbnails)/3))*300), CREAM)
    draw = ImageDraw.Draw(sheet)
    for i, (frame, mode, thumbnail) in enumerate(thumbnails):
        x, y = i%3*480, i//3*300
        sheet.paste(thumbnail, (x,y));draw.text((x+8,y+274), f'{frame/FPS:.3f}s {mode}', fill=INK)
    sheet.save(directory/'scene-contact-sheet.jpg', quality=92)
    return {'passed':not errors,'decoded_frames':decoded,'half_resolution_field_checks_per_index':dict(tracked),
            'minimum_half_resolution_glyph_iou':dict(minimums),'native_samples':native_records,
            'native_centering_tolerance_px':1,'producer_renderer_imported':False,'errors':errors}


def captions_and_metadata(plan, events, directory):
    directory = Path(directory)
    captions = directory/'english-captions.srt'
    require(captions.is_file(), 'Missing English captions')
    blocks = re.split(r'\n\s*\n', captions.read_text(encoding='utf-8-sig').strip())
    require(len(blocks) == len(events) == 104, 'Caption count differs from 104 adopted events')
    def stamp(at):
        ms = round(at*1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    for i, (block, event) in enumerate(zip(blocks, events, strict=True), 1):
        lines = block.splitlines()
        require(len(lines) == 3 and lines[0] == str(i), f'Invalid caption cue {i}')
        require(lines[1] == f'{stamp(event["start_s"])} --> {stamp(event["end_s"])}', f'Caption timing mismatch {i}')
        require(lines[2] == event['text'], f'Caption text mismatch {i}')
    title, description, chapters = (directory/name for name in ('youtube-title.txt','youtube-description.txt','chapters.txt'))
    for path in (title, description, chapters):
        require(path.is_file() and path.stat().st_size, f'Missing metadata {path.name}')
    require('Fibonacci' in title.read_text() and '102,334,155' in title.read_text(), 'Title does not identify Fibonacci endpoint')
    text = description.read_text()
    require('41' in text and '39' in text and '102,334,155' in text, 'Description omits indexed range/addition count')
    parsed = []
    for line in chapters.read_text().splitlines():
        match = re.match(r'(?:(\d+):)?(\d{1,2}):(\d\d)\s+(.+)', line)
        if match:
            hour, minute, second, name = match.groups()
            parsed.append((int(hour or 0)*3600+int(minute)*60+int(second), name))
    require(parsed and parsed[0][0] == 0 and all(a[0] < b[0] for a,b in zip(parsed,parsed[1:])), 'Invalid chapter order')
    require(parsed[-1][0] < plan['duration_s'], 'Chapter beyond delivery')
    require(len(parsed) >= 3,'YouTube manual chapters require at least three entries')
    ends = [row[0] for row in parsed[1:]]+[plan['duration_s']]
    require(all(end-row[0] >= 10 for row,end in zip(parsed,ends)), 'Every chapter, including the last, must last at least 10 seconds')
    require(chapters.read_text().strip() in text,'Description chapters differ from delivery chapters file')
    return {'passed':True,'caption_cues':104,'caption_sha256':sha(captions),'title':title.read_text().strip(),'chapters':parsed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--delivery-dir', type=Path)
    parser.add_argument('--final-aac-clips-dir', type=Path)
    parser.add_argument('--extract-final-clips', action='store_true')
    parser.add_argument('--skip-technical', action='store_true')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    args = parser.parse_args(argv)
    require(args.ffmpeg and args.ffprobe, 'FFmpeg/ffprobe required')
    args.out_dir.mkdir(parents=True, exist_ok=False)
    plan = json.loads(args.timeline.read_text())
    report = {'schema_version':1,'kind':'independent-fibonacci-final-verification',
              'checked_at_utc':datetime.now(timezone.utc).isoformat(),
              'video':str(args.video.resolve()),'video_sha256':sha(args.video),'timeline_sha256':sha(args.timeline),
              'verifier_sha256':sha(Path(__file__)), 'passed':False}
    try:
        events, states, segments, report['schedule'] = validate_schedule(plan)
        if not args.skip_technical:
            report['technical'] = technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            require(report['technical']['status'] == 'pass', 'Technical media checks failed')
            require(report['technical']['measurements']['true_peak_dbtp'] <= -1.45, 'Final AAC peak exceeds -1.5dBTP with .05dB measurement tolerance')
        report['captions_and_metadata'] = captions_and_metadata(plan,events,args.delivery_dir or args.video.parent)
        excerpts = (args.final_aac_clips_dir or args.video.parent/'audio-final-qa'/'clips') if args.extract_final_clips else None
        with tempfile.TemporaryDirectory(prefix='fibonacci-audio-qa-') as work:
            report['audio'] = media.audio_checks(plan,events,args.video,args.master,args.ffmpeg,Path(work),excerpts)
            report['audio']['scope'] = 'All104 adopted source waveforms versus master and final AAC, both channels, and guarded silent interiors. Gain-invariant correlation; recognition and listening are separate.'
        if excerpts:
            print(json.dumps({'event':'final_aac_manifest_ready','path':report['audio']['recognition_excerpt_manifest']}),flush=True)
        report['visual'] = visual_checks(args.video,plan,states,segments,args.ffmpeg,args.out_dir)
        require(report['visual']['passed'], 'Decoded-pixel visual checks failed')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['scope'] = 'Automated full decode, independently derived indexed Fibonacci/cardinal schedule, decoded raster samples and source/master/AAC stereo waveform agreement. No claim of human continuous viewing or listening.'
        (args.out_dir/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json')}))


if __name__ == '__main__':
    main()
