"""Independent Lucas delivery verification from completed pixels and waveforms.

No Lucas builder, renderer or animation module is imported. Mathematical truth,
English grammar, glyph masks, expected progress and transition values are
derived here. Shared media helpers only decode bytes or measure technical data.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageMath, ImageOps, ImageStat

if __package__:
    from .component_alignment import raster_centering_report
    from . import verify_video as technical
else:
    from component_alignment import raster_centering_report
    import verify_video as technical

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/lucas-counting-v1'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BACKDROP = DESIGN / 'generation-batches/lucas-preproduction-20261112-01a1ce1d/source/clocktower-clean-plate.png'
FPS, RATE, SIZE = 30, 48000, (1920, 1080)
INK, MUTED, TEAL, CORAL, GOLD = '#604934', '#7e7364', '#327e84', '#ce795f', '#c79949'
CREAM, EDGE = '#fffaf0', '#d9ccb5'
SUB = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
INPUT_FIELDS = ((324, 325, 796, 413), (1124, 325, 1596, 413))
RESULT_FIELD = (465, 603, 1455, 730)
READING_FIELD = (385, 802, 1535, 899)
PROGRESS_FIELD = (55, 47, 305, 114)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def path_of(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sample(at):
    return round(at * RATE)


def frame_at(at):
    return math.ceil(at * FPS - 1e-7)


def lucas_values():
    """Use the binomial Fibonacci identity, not the authored recurrence table."""
    def fib(n):
        return 0 if n == 0 else sum(math.comb(n-k-1, k) for k in range((n-1)//2+1))
    values = tuple(2*fib(n+1)-fib(n) for n in range(41))
    require(values[:6] == (2, 1, 3, 4, 7, 11), 'Lucas seed invariant differs')
    require(values[-3:] == (87403803, 141422324, 228826127), 'Lucas final invariant differs')
    require(all(values[n-2]+values[n-1] == values[n] for n in range(2, 41)), 'Lucas addition invariant differs')
    return values


def cardinal(value):
    small = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = dict(zip(range(20, 100, 10), 'twenty thirty forty fifty sixty seventy eighty ninety'.split()))
    def group(n):
        if n < 20:
            return small[n]
        if n < 100:
            return tens[n//10*10] + ('-'+small[n%10] if n%10 else '')
        return small[n//100]+' hundred'+(' '+group(n%100) if n%100 else '')
    require(type(value) is int and 0 <= value < 10**9, 'Unsupported US cardinal')
    parts = []
    for divisor, unit in ((10**6, 'million'), (1000, 'thousand')):
        head, value = divmod(value, divisor)
        if head:
            parts.append(group(head)+' '+unit)
    if value or not parts:
        parts.append(group(value))
    return ' '.join(parts)


def parse_cardinal(text):
    """Strict inverse grammar; malformed sums of otherwise valid words fail."""
    if not isinstance(text, str) or not re.fullmatch(r'[a-z]+(?:[ -][a-z]+)*', text):
        return None
    lex = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(), range(20)))
    tens = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))
    def under_hundred(words):
        if len(words) == 1:
            return lex.get(words[0], tens.get(words[0]))
        if len(words) == 2 and words[0] in tens and 1 <= lex.get(words[1], -1) <= 9:
            return tens[words[0]]+lex[words[1]]
        return None
    def under_thousand(words):
        if 'hundred' not in words:
            return under_hundred(words)
        if len(words) < 2 or words[1] != 'hundred' or words.count('hundred') != 1 or not 1 <= lex.get(words[0], -1) <= 9:
            return None
        tail = under_hundred(words[2:]) if len(words) > 2 else 0
        return 100*lex[words[0]]+tail if tail is not None and (tail > 0 or len(words) == 2) else None
    words = text.replace('-', ' ').split()
    total = 0
    for unit, multiplier in (('million', 10**6), ('thousand', 1000)):
        if unit in words:
            if words.count(unit) != 1:
                return None
            split = words.index(unit)
            head = under_thousand(words[:split])
            if not head:
                return None
            total += head*multiplier
            words = words[split+1:]
    tail = under_thousand(words) if words else 0
    if tail is None or (total and words and tail == 0):
        return None
    value = total+tail
    return value if cardinal(value).replace('-', ' ') == text.replace('-', ' ') else None


def validate_schedule(plan):
    truth = lucas_values()
    authored = json.loads((DESIGN/'script/speech-script.json').read_text())['cues']
    cues = sorted(plan.get('voice_events', plan.get('events', [])), key=lambda r: r['start_s'])
    require(plan['fps'] == FPS, 'Timeline FPS differs')
    require(plan['duration_frames'] == frame_at(plan['duration_s']), 'Timeline frame grid differs')
    require(480 <= plan['duration_s'] < 1800, 'Long-form duration outside 8..30 minutes')
    require([r['id'] for r in cues] == [r['id'] for r in authored], '104 authored cue order differs')
    require(len(cues) == len({r['id'] for r in cues}) == 104, '104 unique cues required')
    by_id = {r['id']: r for r in cues}
    cursor = 0
    for row, reference in zip(cues, authored, strict=True):
        require(row['text'] == reference['text'], f'Authored speech changed {row["id"]}')
        start, end = sample(row['start_s']), sample(row['end_s'])
        require(cursor <= start < end <= sample(plan['duration_s']), f'Overlapping/invalid cue {row["id"]}')
        require(start-cursor == sample(reference['gap_before_s']), f'Activity-boundary authored gap differs {row["id"]}')
        if 'start_sample_24k' in row:
            require(start == 2*row['start_sample_24k'] and end == 2*row['end_sample_24k'], f'Sample/second mismatch {row["id"]}')
            require(row['start_sample_24k'] == row['clip_start_sample_24k']+row['source_active_start_sample_24k'] and row['end_sample_24k'] == row['clip_start_sample_24k']+row['source_active_end_sample_24k'], f'Speech activity/full-clip placement confused {row["id"]}')
        require(start % 2 == end % 2 == 0, f'24k source grid differs {row["id"]}')
        cursor = end
        if row['id'].startswith('N'):
            n = int(row['id'][1:])
            require(parse_cardinal(row['text']) == truth[n], f'Wrong spoken Lucas value L{n}')
        elif row['id'].startswith('E'):
            n = int(row['id'][1:])
            require(2 <= n <= 40, 'Seed incorrectly generated by addition')
            a, b = row['text'].removesuffix(' equals').split(' plus ')
            require(row['text'].endswith(' equals') and (parse_cardinal(a), parse_cardinal(b)) == truth[n-2:n], f'Wrong formula inputs L{n}')
    states = plan.get('counted_states', plan.get('count_states', []))
    require(len(states) == 41, 'Need 41 counted states')
    state_map = {}
    transfer_count = ordinary = 0
    for n, state in enumerate(states):
        require(state.get('index', state.get('n')) == n and state['value'] == truth[n], f'Wrong indexed state L{n}')
        require(state.get('ordinal', n+1) == n+1, f'Ordinal/index confusion L{n}')
        voice = by_id[f'N{n:03}']
        display = state.get('display_start_s', state.get('result_start_s'))
        require(sample(voice['start_s']-display) == sample(.12), f'Result visual lead differs L{n}')
        require(sample(state['progress_commit_s']) == sample(voice['end_s']), f'Progress must commit at N end L{n}')
        require(sample(state['voice_start_s']) == sample(voice['start_s']) and sample(state['voice_end_s']) == sample(voice['end_s']), f'Count-state activity times differ L{n}')
        if n >= 2:
            require((state['a'], state['b']) == truth[n-2:n], f'Wrong operand state L{n}')
            require(sample(voice['start_s']-by_id[f'E{n:03}']['end_s']) == sample(.16), f'E/N gap differs L{n}')
        if 2 <= n < 40:
            start, end = state['transfer_start_s'], state['transfer_end_s']
            require(start < end <= by_id[f'E{n+1:03}']['start_s'], f'Invalid transfer window L{n}')
            xs = [r for r in cues if r['id'].startswith('X') and r.get('n', r.get('index')) == n]
            if n in (2, 20, 29, 38):
                source = by_id[{2: 'X002b', 20: 'X020b', 29: 'X029b', 38: 'X038'}[n]]
                require(source['start_s'] < start < end < source['end_s'], f'Explanatory transfer outside its cue L{n}')
            else:
                last = xs[-1] if xs else voice
                require(sample(start-last['end_s']) == sample(.25), f'Post-speech transfer start differs L{n}')
                require(sample(end-start) == sample(1.4), f'Transfer duration differs L{n}')
            transfer_count += 1
        if n < 40:
            nxt = by_id[f'N{n+1:03}'] if n == 0 else by_id[f'E{n+1:03}']
            explanations = [r for r in cues if voice['end_s'] <= r['start_s'] < nxt['start_s']]
            if not explanations:
                require(sample(nxt['start_s']-voice['end_s']) == sample(2), f'Ordinary two-second boundary differs L{n}')
                ordinary += 1
        state_map[n] = state
    require(transfer_count == 38, 'Exactly 38 two-value handovers required')
    return truth, cues, by_id, state_map, {'passed': True, 'cue_count': len(cues), 'count_cues': 41, 'formula_cues': 39, 'transfers': transfer_count, 'ordinary_boundaries': ordinary, 'truth_method': '2*F(n+1)-F(n), F from independent binomial identity', 'values': truth}


@lru_cache(maxsize=96)
def font(size):
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=4096)
def glyph_alpha(text, size, gap=12):
    """Rasterize real glyph bounds, then center the entire intended group."""
    masks = []
    for line in text.split('\n'):
        b = font(size).getbbox(line)
        canvas = Image.new('L', (b[2]-b[0]+80, b[3]-b[1]+80))
        ImageDraw.Draw(canvas).text((40-b[0], 40-b[1]), line, fill=255, font=font(size))
        bounds = canvas.point(lambda a: 255 if a >= 128 else 0).getbbox()
        require(bounds is not None, 'Empty expected text')
        masks.append(canvas.crop(bounds))
    width = max(m.width for m in masks)
    height = sum(m.height for m in masks)+gap*(len(masks)-1)
    result = Image.new('L', (width+80, height+80))
    y = 40
    for mask in masks:
        result.paste(mask, (40+round((width-mask.width)/2), y))
        y += mask.height+gap
    return result


def wrap(text, size=32, width=1120):
    lines, current = [], ''
    for word in text.split():
        trial = (current+' '+word).strip()
        if current and font(size).getlength(trial) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return '\n'.join(lines+[current])


def rgb(color):
    return tuple(bytes.fromhex(color.removeprefix('#')))


def scaled_box(field, divisor):
    return tuple(math.floor(v/divisor) for v in field)


@lru_cache(maxsize=4)
def clean_background(divisor=1):
    im = Image.open(BACKDROP).convert('RGB').resize(SIZE, Image.Resampling.LANCZOS)
    return im if divisor == 1 else im.resize((SIZE[0]//divisor, SIZE[1]//divisor), Image.Resampling.BOX)


@lru_cache(maxsize=4)
def transfer_background(divisor=1):
    image=clean_background().copy();draw=ImageDraw.Draw(image)
    for box in ((300,248,820,435),(1100,248,1620,435)):
        draw.rounded_rectangle(box,64,fill=CREAM,outline=EDGE,width=2)
    draw.rounded_rectangle((430,578,1490,755),30,fill=CREAM,outline=GOLD,width=2)
    return image if divisor==1 else image.resize((SIZE[0]//divisor,SIZE[1]//divisor),Image.Resampling.BOX)


def observed_ink(image, field, color, fill=CREAM, divisor=1, method='bt709-luminance'):
    crop = scaled_box(field, divisor)
    actual = image.crop(crop)
    base = transfer_background(divisor).crop(crop) if fill=='transfer-panels' else Image.new('RGB', actual.size, fill) if fill else clean_background(divisor).crop(crop)
    target = rgb(color)
    if method=='bt709-luminance':
        weights=(2126,7152,722)
        args={f'b{i}':ch.convert('I') for i,ch in enumerate(base.split())}
        args.update({f'a{i}':ch.convert('I') for i,ch in enumerate(actual.split())})
        def luma_alpha(env):
            base_y=sum(env[f'b{i}']*weights[i] for i in range(3))
            actual_y=sum(env[f'a{i}']*weights[i] for i in range(3))
            ink_y=sum(target[i]*weights[i] for i in range(3))
            return (base_y-actual_y)*255/(base_y-ink_y+1)
        alpha=ImageMath.lambda_eval(luma_alpha,**args).convert('L').point(lambda a:255 if a>=128 else 0)
        # Inverse alpha is ill-conditioned where backdrop and target have the
        # same luminance (for example distant wooden gear contours outside the
        # equation). Such pixels cannot establish this foreground from luma.
        ink_y=sum(target[i]*weights[i] for i in range(3))
        contrast=ImageMath.lambda_eval(lambda env:(sum(env[f'b{i}']*weights[i] for i in range(3))-ink_y)/10000,**args)
        gate=ImageMath.lambda_eval(lambda env:env['c']*env['c']/4,c=contrast).convert('L').point(lambda v:255 if v>=225 else 0)
        result=ImageChops.darker(alpha,gate)
        if gate.getextrema()!=(255,255):
            # A coloured glyph can cross a darker frame contour with nearly
            # equal luminance yet ample RGB separation. Recover only that
            # well-conditioned colour-vector observation, rather than lowering
            # an IoU/position acceptance threshold for this crossing.
            vector_contrast=ImageMath.lambda_eval(lambda env:sum((env[f'b{i}']-target[i])**2 for i in range(3))/16,**args).convert('L').point(lambda v:255 if v>=157 else 0)
            fallback=observed_ink(image,field,color,fill,divisor,method='rgb-vector')
            fallback=ImageChops.darker(fallback,ImageChops.darker(ImageChops.invert(gate),vector_contrast))
            result=ImageChops.lighter(result,fallback)
        return result
    def inverse(env):
        direction = [env[f'b{i}']-target[i] for i in range(3)]
        difference = [env[f'b{i}']-env[f'a{i}'] for i in range(3)]
        return sum(x*y for x, y in zip(direction, difference))*255/(sum(x*x for x in direction)+1)
    args = {f'b{i}': c.convert('I') for i, c in enumerate(base.split())}
    args.update({f'a{i}': c.convert('I') for i, c in enumerate(actual.split())})
    projection = ImageMath.lambda_eval(inverse, **args).convert('F')
    alpha = projection.convert('L').point(lambda a: 255 if a >= 128 else 0)
    # A gold transfer path must not become coral numeral foreground merely
    # because it is dark. Retain colours lying near the intended alpha line.
    residual = ImageMath.lambda_eval(lambda env: sum((env[f'b{i}']-env[f'a{i}']-(env[f'b{i}']-target[i])*env['p']/255)**2 for i in range(3)), p=projection, **args)
    chroma = ImageMath.lambda_eval(lambda env: env['r']/4, r=residual).convert('L').point(lambda error: 255 if error <= 196 else 0)
    gates = [c.point(lambda v, t=t: 255 if abs(v-t) <= 90 else 0) for c, t in zip(actual.split(), target)]
    return ImageChops.darker(chroma, ImageChops.darker(alpha, ImageChops.darker(gates[0], ImageChops.darker(gates[1], gates[2]))))


@lru_cache(maxsize=8192)
def expected_mask(text, size, field, divisor=1, threshold=128, dx=0, dy=0):
    glyph = glyph_alpha(text, size)
    b = glyph.point(lambda a: 255 if a >= 128 else 0).getbbox()
    crop = scaled_box(field, divisor)
    canvas = Image.new('L', ((crop[2]-crop[0])*divisor, (crop[3]-crop[1])*divisor))
    xy = (round((field[0]+field[2]-b[0]-b[2])/2)-crop[0]*divisor+dx,
          round((field[1]+field[3]-b[1]-b[3])/2)-crop[1]*divisor+dy)
    canvas.paste(glyph, xy)
    if divisor != 1:
        canvas = canvas.resize((canvas.width//divisor, canvas.height//divisor), Image.Resampling.BOX)
    return canvas.point(lambda a: 255 if a >= threshold else 0)


def iou(a, b):
    union = ImageChops.lighter(a, b).histogram()[255]
    return ImageChops.darker(a, b).histogram()[255]/union if union else 1.0


def label(name, text, size, field, color=INK, fill=CREAM, **extra):
    return dict(name=name, text=text, size=size, field=tuple(field), color=color, fill=fill, **extra)


_inspection_cache = {}


def inspect_label(image, row, frame, divisor=1):
    digest = hashlib.sha256(image.crop(scaled_box(row['field'],divisor)).tobytes()).digest()
    cache_key = (row['name'],row['text'],row['size'],row['field'],row['color'],row.get('fill'),divisor,digest)
    if cache_key in _inspection_cache:
        report = dict(_inspection_cache[cache_key]);report['frame']=frame
        report['name']=f'f{frame}/{row["name"]}' if divisor==1 else row['name']
        return report
    actual = observed_ink(image, row['field'], row['color'], row.get('fill'), divisor)
    observation = None
    measurement = actual
    origin = scaled_box(row['field'], divisor)[:2]
    if re.fullmatch(r'[0-9][0-9,]*',row['text']) or row['name'].startswith(('input-role-','transferred-value-','transferred-index-','seed-value-','result-index','addition-operator','carry-group-label')):
        # The input highlight uses the same ink outside the role word. A broad
        # rectangular observation (not a glyph-shaped mask) excludes that
        # spatially separate stroke, while retaining an 8px native clear margin.
        bounds = expected_mask(row['text'],row['size'],row['field'],divisor).getbbox()
        native_margin=3 if row['name'] in ('result-index','addition-operator') or row['name'].startswith('transferred-value-') else 8
        margin = max(1,math.ceil(native_margin/divisor))
        observation = (max(0,bounds[0]-margin),max(0,bounds[1]-margin),min(actual.width,bounds[2]+margin),min(actual.height,bounds[3]+margin))
        measurement = actual.crop(observation)
        isolated = Image.new('L',actual.size)
        isolated.paste(measurement,observation[:2])
        actual = isolated
        origin = (origin[0]+observation[0],origin[1]+observation[1])
    # A small finite edge threshold family accounts for delivery AA/chroma,
    # without changing text, scale, position or the one-pixel center tolerance.
    # Glyph canvases with different even padding can resolve an exact .5px
    # center to either adjacent native pixel. Content alignment remains measured
    # independently from actual ink and is never translated to make it pass.
    _, dx, dy = max((iou(actual, expected_mask(row['text'], row['size'], row['field'], divisor, 128, x, y)), x, y) for x in (-1, 0, 1) for y in (-1, 0, 1))
    thresholds = range(112, 233, 8) if divisor == 1 else (128, 160, 192)
    score, threshold = max((iou(actual, expected_mask(row['text'], row['size'], row['field'], divisor, t, dx, dy)), t) for t in thresholds)
    if divisor == 1:
        try:
            report = raster_centering_report(measurement, row['field'], origin_xy=origin, name=f'f{frame}/{row["name"]}', tolerance_px=1)
        except ValueError as error:
            report = {'name': f'f{frame}/{row["name"]}', 'passed': False, 'failures': [str(error)]}
    else:
        report = {'name': row['name'], 'passed': bool(actual.getbbox())}
    minimum = .93 if divisor == 1 else (.80 if row['size'] < 30 else .88)
    report.update(frame=frame, text=row['text'], font_size_px=row['size'], field=list(row['field']), divisor=divisor,
                  independent_glyph_iou=score, minimum_glyph_iou=minimum, expected_alpha_threshold=threshold, glyph_native_grid_offset=[dx,dy],
                  foreground_measurement='BT709-luma inverse alpha where contrast>=30; low-luma-contrast pixels use RGB-vector inverse alpha only with RGB separation>=50. Components use declared observation rectangles.',
                  horizontal_intent='center visible glyph group', vertical_intent='center visible glyph group')
    if observation:
        report.update(observation_rectangle_local=list(observation),observation_margin_native_px=native_margin,observation_purpose='Independent expected font extent plus declared clear rectangular margin, fixed before observation; excludes distinct pointer/highlight/arrow/role components. Content target remains unchanged; actual observation-edge contact fails')
    report['passed'] = report['passed'] and score >= minimum
    if divisor == 1 and re.fullmatch(r'[0-9][0-9,]*', row['text']):
        expected = expected_mask(row['text'], row['size'], row['field'], 1, threshold, dx, dy)
        raw = Image.new('L', (math.ceil(font(row['size']).getlength(row['text']))+100, row['size']*2+100))
        ImageDraw.Draw(raw).text((40,40),row['text'],font=font(row['size']),fill=255)
        raw_bounds = raw.point(lambda a:255 if a>=threshold else 0).getbbox()
        origin = expected.getbbox()[0]-(raw_bounds[0]-40)
        spans = [(math.floor(origin+font(row['size']).getlength(row['text'][:i]))-1,
                  math.ceil(origin+font(row['size']).getlength(row['text'][:i+1]))+1) for i in range(len(row['text']))]
        digits = []
        if len(spans) == len(row['text']):
            for ch, (a, b) in zip(row['text'], spans):
                crop = (max(0, a), 0, min(actual.width, b), actual.height)
                local = iou(actual.crop(crop), expected.crop(crop))
                good = local >= (.82 if ch == ',' else .90)
                digits.append({'glyph': ch, 'x_interval': [a, b], 'iou': local, 'passed': good})
        report.update(digit_checks=digits, digit_segmentation_expected=len(row['text']), digit_segmentation_observed=len(spans),digit_segmentation_method='independent font advance intervals; commas may share x projection with adjacent digit')
        report['passed'] = report['passed'] and len(digits) == len(row['text']) and all(d['passed'] for d in digits)
    if divisor==1 and re.fullmatch(r'[0-9][0-9,]*',row['text']) and row['color']!=GOLD:
        # IoU alone can miss a thin foreign path drawn through a large glyph.
        # Search opaque glyph interiors for actual gold, a distinct path colour.
        patch=image.crop(scaled_box(row['field'],1))
        gates=[ch.point(lambda v,t=t:255 if abs(v-t)<=20 else 0) for ch,t in zip(patch.split(),rgb(GOLD))]
        gold=ImageChops.darker(gates[0],ImageChops.darker(gates[1],gates[2]))
        interior=expected_mask(row['text'],row['size'],row['field'],1,248,dx,dy)
        foreign=ImageChops.darker(gold,interior).histogram()[255]
        report.update(gold_path_pixels_inside_opaque_glyph=foreign,maximum_foreign_gold_pixels=2)
        report['passed']=report['passed'] and foreign<=2
    if divisor==1 and re.fullmatch(r'(?:=  )?L[₀₁₂₃₄₅₆₇₈₉]+',row['text']):
        classified=index_identification(actual,row['text'],row['size'],threshold)
        report.update(classified)
        # Dictionary discrimination identifies the index despite a lossy small
        # contour, while the actual one-pixel two-axis/clipping checks stand.
        report['passed']=bool(report.get('horizontal_centered')) and bool(report.get('vertical_centered')) and bool(report.get('contained')) and not report.get('touches_measurement_edge',False) and classified['index_identification_passed']
    if len(_inspection_cache)>4096:
        _inspection_cache.clear()
    _inspection_cache[cache_key]=dict(report)
    return report


@lru_cache(maxsize=4096)
def index_shape_score(data,size_xy,text,size,threshold):
    actual=Image.frombytes('L',size_xy,data);glyph=glyph_alpha(text,size).point(lambda a:255 if a>=threshold else 0)
    glyph=glyph.crop(glyph.getbbox());w=max(actual.width,glyph.width)+8;h=max(actual.height,glyph.height)+8
    a=Image.new('L',(w,h));b=Image.new('L',(w,h));a.paste(actual,(round((w-actual.width)/2),round((h-actual.height)/2)));b.paste(glyph,(round((w-glyph.width)/2),round((h-glyph.height)/2)))
    return max(iou(a,ImageChops.offset(b,x,y)) for x in (-1,0,1) for y in (-1,0,1))


def index_identification(actual,text,size,threshold):
    bounds=actual.getbbox()
    if bounds is None:return {'index_identification_passed':False,'index_dictionary':'L0..L40'}
    crop=actual.crop(bounds);data=crop.tobytes();prefix='=  ' if text.startswith('=') else ''
    scores={prefix+indexed(n):index_shape_score(data,crop.size,prefix+indexed(n),size,threshold) for n in range(41)}
    correct=scores[text];wrong,other=max((score,name) for name,score in scores.items() if name!=text)
    return {'index_dictionary':'L0..L40','correct_index_shape_iou':correct,'nearest_wrong_index':other,'nearest_wrong_index_shape_iou':wrong,'correct_index_margin':correct-wrong,'minimum_index_shape_iou':.90,'minimum_index_margin':.01,'index_identification_passed':correct>=.90 and correct-wrong>=.01}


def decoded_frames(video, ffmpeg, log, divisor=1, indices=None):
    w, h = SIZE[0]//divisor, SIZE[1]//divisor
    filters = []
    if indices is not None:
        ranges = []
        for index in indices:
            if ranges and index == ranges[-1][1]+1:
                ranges[-1][1] = index
            else:
                ranges.append([index, index])
        def balanced(terms):
            if len(terms) == 1:
                return terms[0]
            half = len(terms)//2
            return '('+balanced(terms[:half])+'+'+balanced(terms[half:])+')'
        filters.append('select='+balanced([f'between(n\\,{a}\\,{b})' for a, b in ranges]))
    if divisor != 1:
        filters.append(f'scale={w}:{h}:flags=area:in_color_matrix=bt709')
    filters.append('format=rgb24')
    command = [str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(video), '-an', '-vf', ','.join(filters), '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    with Path(log).open('xb') as errors, subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
        iterator = iter(indices) if indices is not None else iter(range(10000000))
        for index in iterator:
            data = process.stdout.read(w*h*3)
            if not data and indices is None:
                break
            require(len(data) == w*h*3, f'Decoder EOF at frame {index}')
            yield index, Image.frombytes('RGB', (w, h), data)
        require(not process.stdout.read(1), 'Extra selected decoded frames')
        require(process.wait() == 0, 'Completed video decode failed')


def pcm16(data):
    values = array('h')
    values.frombytes(data)
    if __import__('sys').byteorder != 'little':
        values.byteswap()
    return values


def correlation(reference, observed, guard=8, stride=16):
    ref = reference[::stride]
    energy = sum(v*v for v in ref)
    best = (-1, 0, 0)
    for lag in range(-guard, guard+1):
        obs = observed[guard+lag:guard+lag+len(reference):stride]
        if len(obs) != len(ref):
            continue
        actual_energy = sum(v*v for v in obs)
        if not energy or not actual_energy:
            continue
        score = sum(a*b for a, b in zip(ref, obs))/math.sqrt(energy*actual_energy)
        if score > best[0]:
            best = (score, lag, 10*math.log10(actual_energy/energy))
    return best


def audio_checks(plan, events, video, master, ffmpeg, directory, export_excerpts=True):
    """Check each source, both output channels and every guarded silent gap."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    refs, outcomes = {}, []
    with tempfile.TemporaryDirectory(prefix='lucas-independent-audio-') as temp:
        temp = Path(temp)
        for row in events:
            source = path_of(row['source_path'])
            require(sha(source) == row['source_sha256'], f'Adopted speech source changed {row["id"]}')
            if source not in refs:
                destination = temp/f'source-{len(refs):03d}.wav'
                # This is the same declared FFmpeg mono/stereo routing, not a
                # hidden gain adjustment. Relative gains are tested separately.
                subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-n', '-i', str(source), '-ar', str(RATE), '-ac', '2', '-c:a', 'pcm_s16le', str(destination)], check=True)
                with wave.open(str(destination), 'rb') as clip:
                    refs[source] = pcm16(clip.readframes(clip.getnframes()))[::2]
            with wave.open(str(source), 'rb') as original:
                require(original.getnchannels() == 1 and original.getframerate() == 24000 and original.getsampwidth() == 2, 'Adopted source must be mono24k PCM16')
                source_pcm = pcm16(original.readframes(original.getnframes()))
            activity = [i for i, value in enumerate(source_pcm) if abs(value) >= 104]
            require(activity and (activity[0], activity[-1]+1) == (row['source_active_start_sample_24k'], row['source_active_end_sample_24k']), f'Independent PCM activity bounds differ {row["id"]}')
        for name, source, lossy in (('master', master, False), ('final-aac', video, True)):
            destination = temp/f'{name}.wav'
            subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-n', '-i', str(source), '-map', '0:a:0', '-ar', str(RATE), '-ac', '2', '-c:a', 'pcm_s16le', str(destination)], check=True)
            rows, silences, cursor = [], [], 0
            guard = sample(.03 if lossy else .002)
            with wave.open(str(destination), 'rb') as track:
                require(abs(track.getnframes()-sample(plan['duration_s'])) <= (2048 if lossy else 1), f'{name} audio endpoint differs')
                for row in events:
                    start, end = sample(row['clip_start_s']), sample(row['clip_end_s'])
                    reference = refs[path_of(row['source_path'])]
                    require(abs(len(reference)-(end-start)) <= 2, f'Adopted source length differs {row["id"]}')
                    a, b = cursor+(guard if cursor else 0), start-guard
                    if b > a:
                        track.setpos(a)
                        silences.append({'start_sample': a, 'end_sample': b, 'peak_pcm16': max(map(abs, pcm16(track.readframes(b-a))), default=0)})
                    require(start >= 8, 'Need leading samples for independent lag window')
                    track.setpos(start-8)
                    actual = pcm16(track.readframes(len(reference)+16))
                    channels = [correlation(reference, actual[c::2]) for c in (0, 1)]
                    require(min(c[0] for c in channels) >= .97, f'{name} waveform mismatch {row["id"]}: {channels}')
                    master_info = plan.get('master_audio', plan.get('master', {}))
                    gain = row.get('mix_gain_db', 0)+master_info.get('common_gain_db', plan.get('common_gain_db', 0))
                    require(all(abs(c[2]-gain) <= (.35 if lossy else .06) for c in channels), f'{name} gain mismatch {row["id"]}: expected {gain}, observed {channels}')
                    rows.append({'id': row['id'], 'source_sha256': row['source_sha256'], 'left_correlation': channels[0][0], 'right_correlation': channels[1][0], 'left_lag_samples': channels[0][1], 'right_lag_samples': channels[1][1], 'left_gain_db': channels[0][2], 'right_gain_db': channels[1][2], 'expected_gain_db': gain, 'left_right_gain_difference_db': abs(channels[0][2]-channels[1][2])})
                    cursor = end
                if cursor+guard < track.getnframes():
                    track.setpos(cursor+guard)
                    silences.append({'start_sample': cursor+guard, 'end_sample': track.getnframes(), 'peak_pcm16': max(map(abs, pcm16(track.readframes(track.getnframes()))), default=0)})
            maximum = max((r['peak_pcm16'] for r in silences), default=0)
            require(maximum <= (3 if lossy else 1), f'Unexpected {name} sound in silent interiors: {maximum} PCM16')
            report = {'passed': True, 'track': name, 'sha256': sha(source), 'events': rows, 'silence_intervals': silences, 'boundary_guard_s': guard/RATE, 'minimum_correlation': min(min(r['left_correlation'], r['right_correlation']) for r in rows), 'maximum_silent_interior_peak_pcm16': maximum, 'source_channel_mapping': 'FFmpeg 48kHz stereo upmix; left reference channel; declared mix/common gain checked separately', 'waveform_stride': 16, 'lag_search_samples': [-8, 8]}
            write_json(directory/f'{name}.json', report)
            outcomes.append(report)
            if lossy and export_excerpts:
                clips = directory/'final-aac-event-clips'
                clips.mkdir(exist_ok=False)
                manifest = {'schema_version': 1, 'measurement_status': 'measured', 'source_video_sha256': sha(video), 'excerpt_format': {'sample_rate_hz': RATE, 'channels': 1, 'sample_width_bits': 16}, 'numbers': [], 'dialogue': [], 'scope': 'Actual final AAC left channel with bounded 80ms context; recognition inputs, no new source adoption or listening claim'}
                with wave.open(str(destination), 'rb') as track:
                    for ordinal, row in enumerate(events):
                        previous = events[ordinal-1]['end_s'] if ordinal else 0
                        following = events[ordinal+1]['start_s'] if ordinal+1 < len(events) else track.getnframes()/RATE
                        a = sample(row['start_s']-min(.08, max(0, (row['start_s']-previous)/2)))
                        b = sample(row['end_s']+min(.08, max(0, (following-row['end_s'])/2)))
                        track.setpos(a)
                        mono = array('h', pcm16(track.readframes(b-a))[::2])
                        path = clips/f'{row["id"]}.wav'
                        with wave.open(str(path), 'wb') as clip:
                            clip.setparams((1, 2, RATE, len(mono), 'NONE', 'not compressed'))
                            clip.writeframes(mono.tobytes())
                        item = {'id': row['id'], 'path': f'{clips.name}/{path.name}', 'spoken_text': row['text'], 'duration_s': len(mono)/RATE, 'clip_duration_s': len(mono)/RATE, 'sha256': sha(path), 'speech_offset_s': row['start_s']-a/RATE, 'nominal_event_duration_s': row['end_s']-row['start_s'], 'event_start_s': row['start_s'], 'event_end_s': row['end_s'], 'excerpt_start_s': a/RATE, 'excerpt_end_s': b/RATE}
                        if row['id'].startswith('N'):
                            item['number'] = lucas_values()[int(row['id'][1:])]
                            manifest['numbers'].append(item)
                        else:
                            manifest['dialogue'].append(item)
                write_json(directory/'final-aac-manifest.json', manifest)
    return {'passed': True, 'tracks': outcomes, 'scope': f'All {len(events)} adopted source hashes/waveforms versus master and actual decoded AAC, both channels and every guarded silent gap; new ASR/CTC and listening are separate'}


def srt_time(value):
    hour, minute, second, milli = map(int, re.split('[:,]', value))
    return 3600*hour+60*minute+second+milli/1000


def subtitle_checks(events, paths):
    reports = []
    for path in paths:
        path = path_of(path)
        blocks = re.split(r'\n\s*\n', path.read_text().strip())
        require(len(blocks) == len(events), f'Subtitle cue count differs {path}')
        records = []
        for index, (block, event) in enumerate(zip(blocks, events, strict=True), 1):
            lines = block.splitlines()
            require(int(lines[0]) == index, f'Subtitle order differs {index}')
            start, end = [srt_time(x.strip()) for x in lines[1].split('-->')]
            text = ' '.join(lines[2:])
            require(text == event['text'], f'Subtitle text differs {event["id"]}')
            require(abs(start-event['start_s']) <= .00101 and abs(end-event['end_s']) <= .00101, f'Subtitle timing differs {event["id"]}')
            records.append({'id': event['id'], 'start_delta_s': start-event['start_s'], 'end_delta_s': end-event['end_s'], 'passed': True})
        reports.append({'path': str(path), 'sha256': sha(path), 'passed': True, 'cues': records})
    return {'passed': bool(reports), 'files': reports}


def verifier_controls(directory):
    """Real altered raster counterexamples, including one wrong final digit."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    row = label('control-nine-digits', '228,826,127', 109, RESULT_FIELD, TEAL)
    base = Image.new('RGB', SIZE, CREAM)
    mask = expected_mask(row['text'], row['size'], row['field'])
    base.paste(TEAL, row['field'], mask)
    reference = inspect_label(base, row, -1)
    require(reference['passed'], f'Positive native glyph control failed: {reference}')
    results = [{'id': 'correct-native-nine-digits', 'expected_pass': True, 'observed_pass': reference['passed']}]
    for name, variant in [('wrong-final-digit', '228,826,128'), ('wrong-first-digit', '328,826,127')]:
        image = Image.new('RGB', SIZE, CREAM)
        image.paste(TEAL, row['field'], expected_mask(variant, row['size'], row['field']))
        report = inspect_label(image, row, -1)
        require(not report['passed'], f'Wrong-digit negative control escaped: {name}')
        image.save(directory/f'{name}.png')
        results.append({'id': name, 'expected_pass': False, 'observed_pass': report['passed'], 'observation': report})
    for name, delta in [('horizontal-two-pixels', (2, 0)), ('vertical-two-pixels', (0, 2))]:
        image = Image.new('RGB', SIZE, CREAM)
        image.paste(TEAL, (row['field'][0]+delta[0], row['field'][1]+delta[1], row['field'][2]+delta[0], row['field'][3]+delta[1]), mask)
        report = inspect_label(image, row, -1)
        require(not report['passed'], f'One-axis negative control escaped: {name}')
        image.save(directory/f'{name}.png')
        results.append({'id': name, 'expected_pass': False, 'observed_pass': report['passed'], 'observation': report})
    report = inspect_label(Image.new('RGB', SIZE, CREAM), row, -1)
    require(not report['passed'], 'Empty foreground negative control escaped')
    results.append({'id': 'empty-number', 'expected_pass': False, 'observed_pass': report['passed']})
    index_row=label('control-index',indexed(39),25,(1124,264,1596,300),CORAL)
    for name,text,expected_pass in [('correct-index',indexed(39),True),('wrong-index',indexed(38),False)]:
        image=Image.new('RGB',SIZE,CREAM);image.paste(CORAL,index_row['field'],expected_mask(text,25,index_row['field']))
        result=inspect_label(image,index_row,-1)
        require(result['passed']==expected_pass,f'Index-dictionary control failed: {name}')
        results.append({'id':name,'expected_pass':expected_pass,'observed_pass':result['passed'],'observation':result})
    report = {'passed': True, 'controls': results, 'scope': 'Independent glyph raster: numeral/index positive controls and real counterexamples; no finished-video or acting acceptance'}
    write_json(directory/'verification.json', report)
    return report


def clamp(value):
    return min(1., max(0., value))


def smooth(value):
    value = clamp(value)
    return value*value*(3-2*value)


def indexed(n):
    return 'L'+str(n).translate(SUB)


def semantic_state(events, states, at):
    """Derive presentation and progress from cue times, not renderer logs."""
    starts = [r['start_s'] for r in events]
    cue = events[max(0, bisect_right(starts, at)-1)]
    ident = cue['id']
    n = cue.get('n', cue.get('index'))
    p = clamp((at-cue['start_s'])/(cue['end_s']-cue['start_s']))
    state = {'mode': 'count', 'n': n, 'cue_id': ident, 'stage': 'result', 'tick': round(p*90), 'progress': sum(s['progress_commit_s'] <= at for s in states.values())}
    if ident.startswith('I'):
        state.update(mode='seeds' if ident == 'I04' else 'intro', stage=ident)
    elif ident.startswith('O'):
        state.update(mode='history', n=40, stage=ident)
    elif n < 2:
        state.update(mode='seeds', stage=ident)
    else:
        row = states[n]
        a, b = row.get('transfer_start_s'), row.get('transfer_end_s')
        if a is not None and at >= a:
            if at < b:
                state.update(mode='transfer', stage='handoff', tick=round(smooth((at-a)/(b-a))*90))
            else:
                state.update(mode='count', n=n+1, stage='ready', tick=0)
        elif ident.startswith('X'):
            modes = {'X002a': 'units', 'X005a': 'ten', 'X005b': 'value-tags', 'X010a': 'carry-ones', 'X010b': 'carry-tens', 'X010c': 'carry-result', 'X020a': 'midpoint', 'X020b': 'midpoint', 'X029a': 'millions', 'X029b': 'millions', 'X038': 'last-inputs', 'X039': 'hundred-million'}
            state.update(mode=modes.get(ident, 'count'), stage=ident)
        elif at < row.get('display_start_s', row.get('result_start_s')):
            formula = next(r for r in events if r['id'] == f'E{n:03}')
            timing = formula.get('highlight_timing', {})
            # Production must provide measured phonetic timings. Fallbacks are
            # intentionally unavailable to the independent final verifier.
            require(all(k in timing for k in ('a_start_s', 'plus_start_s', 'b_start_s', 'equals_start_s')), f'Measured input highlights missing E{n:03}')
            a0, plus, b0, equals = (timing[k] for k in ('a_start_s', 'plus_start_s', 'b_start_s', 'equals_start_s'))
            stage = 'older' if at < plus else 'plus' if at < b0 else 'newer' if at < equals else 'equals'
            low, high = {'older': (a0, plus), 'plus': (plus, b0), 'newer': (b0, equals), 'equals': (equals, row.get('display_start_s', row.get('result_start_s')))}[stage]
            state.update(stage=stage, tick=round(clamp((at-low)/max(.001, high-low))*90))
    if state['mode'] == 'count' and state['stage'] == 'result':
        state['tick'] = 0
    return state


def common_labels(state, rule=True):
    result = [label('title', 'LUCAS NUMBERS', 43, (395, 39, 1525, 84)),
              label('completed-progress', f'COMPLETED\n{state["progress"]} / 41', 22, PROGRESS_FIELD, MUTED)]
    if rule:
        result.append(label('general-rule', 'L₀ = 2     L₁ = 1     L(n) = L(n − 2) + L(n − 1)   (n ≥ 2)', 33, (300, 151, 1620, 205), MUTED, '#fff9e9'))
    return result


def normal_labels(state, truth, reading=True):
    n = state['n']
    require(2 <= n <= 40, 'Normal generated state out of range')
    large = n >= 20
    output = common_labels(state)
    for k, value in enumerate(truth[n-2:n]):
        x = (300, 1100)[k]
        color = (TEAL, CORAL)[k]
        output += [label(f'input-role-{k}', ('OLDER', 'NEWER')[k], 21, (x+20, 267, x+155, 301), color),
                   label(f'input-index-{k}', indexed(n-2+k), 25, (x+180, 264, x+340, 300), color),
                   label(f'input-value-{k}', f'{value:,}', 60 if large else 86, INPUT_FIELDS[k], color)]
    output += [label('addition-operator', '+', 52, (928, 464, 992, 515)),
               label('result-index', '=  '+indexed(n), 29, (1050, 540, 1390, 576), MUTED, None)]
    pending = state['stage'] in ('older', 'plus', 'newer', 'equals', 'ready')
    output.append(label('uncommitted-output' if pending else 'result-value', '?' if pending else f'{truth[n]:,}', 109 if large else 126, RESULT_FIELD, TEAL))
    if not pending and reading:
        output.append(label('english-reading', wrap(cardinal(truth[n])), 32, READING_FIELD, MUTED, None))
    return output


def transfer_labels(state, truth):
    n, p = state['n'], state['tick']/90
    source = 86 if n < 20 else 60
    target = 86 if n+1 < 20 else 60
    size = round(source+(target-source)*p)
    output = common_labels(state)
    output += [label('next-role-0','NEXT OLDER',17,(316,217,474,241),TEAL,None),
               label('next-role-1','NEXT NEWER',17,(1116,217,1274,241),CORAL,None)]
    output.append(label('held-result', f'{truth[n]:,}', 109 if n >= 20 else 126, RESULT_FIELD, TEAL))
    centers = ((1360-800*p, 369-40*math.sin(math.pi*p)), (1660-300*p, 665-296*p))
    for k, ((x, y), value, index, color) in enumerate(zip(centers, truth[n-1:n+1], (n-1, n), (TEAL, CORAL))):
        output += [label(f'transferred-value-{k}', f'{value:,}', size, (x-250, y-65, x+250, y+65), color),
                   label(f'transferred-index-{k}', indexed(index), 25, (x-130, y-101, x+130, y-73), color, 'transfer-panels')]
    return output


def seed_labels(state, states, at):
    output = common_labels(state, False)
    for x, n, value, color in ((395, 0, 2, TEAL), (1125, 1, 1, CORAL)):
        output.append(label(f'seed-index-{n}', indexed(n), 40, (x+40, 342, x+360, 400), color))
        if at >= states[n].get('display_start_s', states[n].get('result_start_s')):
            output.append(label(f'seed-value-{n}', str(value), 152, (x+40, 431, x+360, 586), color))
    return output


def carry_labels(state):
    output = common_labels(state, False)
    output.append(label('replay-equation', '47 + 76 = 123', 65, (420, 166, 1500, 239), TEAL, None))
    xs = (520, 720, 920)
    for j, name in enumerate(('hundreds', 'tens', 'ones')):
        output.append(label('place-'+name, name, 22, (xs[j]-90, 301, xs[j]+90, 340), MUTED))
    for ri, (number, y) in enumerate((('47', 435), ('76', 550))):
        for ci, char in enumerate(number.rjust(3)):
            if char != ' ':
                output.append(label(f'carry-addend-{ri}-{ci}', char, 79, (xs[ci]-73, y, xs[ci]+73, y+84)))
    mode, p = state['mode'], state['tick']/90
    visible = (mode == 'carry-result', mode == 'carry-result' or mode == 'carry-tens' and p > .93, mode != 'carry-ones' or p > .93)
    for ci, show in enumerate(visible):
        if show:
            output.append(label(f'carry-result-{ci}', str((1, 2, 3)[ci]), 79, (xs[ci]-73, 715, xs[ci]+73, 799), TEAL))
    if mode in ('carry-ones', 'carry-tens'):
        color = CORAL if mode == 'carry-ones' else GOLD
        output.append(label('carry-group-label', '13 ONES' if mode == 'carry-ones' else '12 TENS', 30, (1200, 340, 1645, 380), color))
        if mode == 'carry-tens':
            output.append(label('carry-unit-meaning','4 + 7 + 1 = 12 tens\n10 tens = 1 hundred\n2 tens remain',25,(1200,636,1645,761),MUTED))
        q = smooth((p-.62)/.3)
        if q > .75:
            target_x = 720 if mode == 'carry-ones' else 520
            x, y = 1384+(target_x-1384)*q, 467-81*q-35*math.sin(math.pi*q)
            output.append(label('moving-carry', '1', 36, (x-27, y-22, x+27, y+22), color))
    else:
        output.append(label('final-carry-hundred', '1', 36, (470, 365, 570, 407), CORAL))
    return output


def history_labels(state, truth):
    output = common_labels(state, False)
    compact = state['stage'] in ('O03', 'O04')
    for n, value in enumerate(truth):
        x, y = 178+224*(n % 7), (157+74*(n//7) if compact else 177+110*(n//7))
        output += [label(f'history-index-{n}', indexed(n), 14 if compact else 18, (x+12, y+5, x+204, y+(23 if compact else 31)), MUTED, '#f9f2e4'),
                   label(f'history-value-{n}', f'{value:,}', 25 if compact else 26, (x+10, y+(30 if compact else 44), x+206, y+(59 if compact else 85)), TEAL if n in (0, 1, 39, 40) else INK, '#f9f2e4')]
    if state['stage'] == 'O03':
        output += [label('lucas-comparison-values', '2 → 1 → 3 → 4', 37, (850, 760, 1480, 805), TEAL),
                   label('fibonacci-comparison-values', '0 → 1 → 1 → 2', 37, (850, 843, 1480, 888), CORAL)]
    return output


def labels_for(state, truth, states, at):
    mode = state['mode']
    if mode == 'intro':
        return common_labels(state, False)
    if mode == 'seeds':
        return seed_labels(state, states, at)
    if mode == 'transfer':
        return transfer_labels(state, truth)
    if mode.startswith('carry-'):
        return carry_labels(state)
    if mode == 'ten':
        result = common_labels(state, False)+[label('ten-equation', '4 + 7 = 11', 65, (400, 164, 1520, 237), TEAL, None)]
        if state['tick']/90 > .88:
            result += [label('tens-digit', '1', 68, (670, 824, 850, 900), TEAL), label('ones-digit', '1', 68, (1070, 824, 1250, 900), TEAL)]
        return result
    if mode == 'history':
        return history_labels(state, truth)
    if mode == 'units':
        return normal_labels({**state, 'stage': 'result'}, truth, False)
    if mode == 'count':
        return normal_labels(state, truth)
    result = normal_labels({**state, 'stage': 'result'}, truth, False)
    if mode == 'millions':
        for i, part in enumerate(f'{truth[state["n"]]:,}'.split(',')):
            x = 510+i*300
            result.append(label(f'three-digit-group-{i}', part, 43, (x+12, 853, x+268, 908), TEAL))
    return result


def quantity_circles(state):
    """Independent exact-unit geometry, preserving all quantity identities."""
    mode, tick = state['mode'], state['tick']
    result = []
    if mode == 'units':
        p = clamp(tick/60)
        stops = (((510,488),(330,520),(330,810),(870,845)),
                 ((590,488),(390,520),(390,870),(960,845)),
                 ((1360,488),(1550,520),(1550,810),(1050,845)))
        boundaries = (0, .2, .65, 1)
        segment = 0 if p < .2 else 1 if p < .65 else 2
        q = smooth((p-boundaries[segment])/(boundaries[segment+1]-boundaries[segment]))
        for i, path in enumerate(stops):
            a, b = path[segment:segment+2]
            result.append({'id':i,'x':a[0]+(b[0]-a[0])*q,'y':a[1]+(b[1]-a[1])*q,'r':26,'filled':i<2,'color':TEAL if i<2 else CORAL,'outline':INK if i<2 else CORAL,'width':4})
    elif mode == 'ten':
        p = tick/90
        arrange, drop = smooth(p/.5), smooth((p-.48)/.4)
        for i in range(11):
            a = (560+72*(i%5),390+80*(i//5)) if i < 10 else (1160,470)
            b = (660+48*(i%5),440+60*(i//5)) if i < 10 else (1160,470)
            result.append({'id':i,'x':a[0]+(b[0]-a[0])*arrange,'y':a[1]+(b[1]-a[1])*arrange+285*drop,'r':17,'filled':i<4,'color':TEAL if i<4 else CORAL,'outline':TEAL if i<4 else CORAL,'width':3})
    elif mode in ('carry-ones','carry-tens'):
        p, count = tick/90, 13 if mode == 'carry-ones' else 12
        q = smooth((p-.62)/.3)
        color = CORAL if mode == 'carry-ones' else GOLD
        center = (1384+((720 if mode == 'carry-ones' else 520)-1384)*q,467-81*q-35*math.sin(math.pi*q))
        for i in range(count):
            x, y, radius = 1230+77*(i%5),435+64*(i//5),15
            if i < 10 and q > 0:
                if q > .75:
                    continue
                x, y, radius = center[0]+(x-1384)*(1-q),center[1]+(y-467)*(1-q),15*(1-q)
            result.append({'id':i,'x':x,'y':y,'r':radius,'filled':i<(7 if mode == 'carry-ones' else 4),'color':color,'outline':color,'width':2 if radius<10 else 3})
    return result


def inspect_quantities(image, state, frame):
    circles = quantity_circles(state)
    if not circles:
        return []
    results = []
    for circle in circles:
        x,y,r = (circle[k] for k in ('x','y','r'))
        box = (math.floor(x-r-2),math.floor(y-r-2),math.ceil(x+r+3),math.ceil(y+r+3))
        colors = {circle['outline']}
        if circle['filled']:
            colors.add(circle['color'])
        actual = Image.new('L',(box[2]-box[0],box[3]-box[1]))
        for color in colors:
            actual = ImageChops.lighter(actual,observed_ink(image,box,color,None))
        expected = Image.new('L',actual.size)
        ImageDraw.Draw(expected).ellipse((x-r-box[0],y-r-box[1],x+r-box[0],y+r-box[1]),fill=255 if circle['filled'] else 0,outline=255,width=circle['width'])
        score = max(iou(actual,ImageChops.offset(expected,dx,dy)) for dx in (-1,0,1) for dy in (-1,0,1))
        try:
            alignment = raster_centering_report(actual,(x-r-2,y-r-2,x+r+2,y+r+2),origin_xy=box[:2],name=f'f{frame}/unit-{circle["id"]}',tolerance_px=1)
        except ValueError as error:
            alignment = {'passed':False,'failures':[str(error)]}
        minimum = .78 if r < 10 else (.82 if not circle['filled'] else .88)
        alignment.update(frame=frame,unit_id=circle['id'],expected_circle=circle,independent_shape_iou=score,minimum_iou=minimum,source_quantity=3 if state['mode']=='units' else 11 if state['mode']=='ten' else 13 if state['mode']=='carry-ones' else 12)
        alignment['passed'] = alignment['passed'] and score >= minimum
        results.append(alignment)
    for a, first in enumerate(circles):
        for second in circles[a+1:]:
            distance = math.hypot(first['x']-second['x'],first['y']-second['y'])
            require(distance+1e-6 >= first['r']+second['r']+8, f'Quantity targets collide f{frame}: {first["id"]}/{second["id"]}')
    return results


def highlight_checks(image, state, frame):
    if state['mode'] != 'count' or state['stage'] not in ('older','plus','newer','equals'):
        return []
    checks = []
    for name,box,color in [('older',(294,310,303,370),TEAL),('newer',(1094,310,1103,370),CORAL),('plus',(950,437,970,444),GOLD)]:
        crop = image.crop(box)
        channels = crop.split()
        gates = [c.point(lambda v,t=t:255 if abs(v-t)<=32 else 0) for c,t in zip(channels,rgb(color))]
        mask = ImageChops.darker(gates[0],ImageChops.darker(gates[1],gates[2]))
        fraction = mask.histogram()[255]/(mask.width*mask.height)
        active = state['stage']==name
        passed = fraction > .45 if active else fraction < .15
        checks.append({'frame':frame,'highlight':name,'expected_active':active,'observed_colored_fraction':fraction,'passed':passed,'probe':box})
    return checks


def expected_actor_geometry(state):
    mode,n = state['mode'],state.get('n')
    if mode=='intro':return 340,(960,1045)
    if mode=='history':
        return (210,(250,1040)) if state['stage']=='O03' else (340,(960,1045)) if state['stage']=='O04' else (125,(960,1050))
    if mode.startswith('carry-'):return 215,(1720,1040)
    if mode=='ten':return 235,(1740,1040)
    if mode=='units':return 240,(190,1030)
    if mode=='seeds':return 280,(250,1040)
    return (260,(1700,1030)) if n is not None and n>=20 else (280,(250,1030))


LOG_ACTORS = {}


@lru_cache(maxsize=192)
def actor_reference(path,digest,height,anchor,reference_height,foot,divisor):
    source=path_of(path);require(sha(source)==digest,'Runtime actor source hash differs')
    art=Image.open(source).convert('RGBA');scale=height/reference_height
    art=art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.LANCZOS)
    xy=(round(foot[0]-anchor[0]*scale),round(foot[1]-anchor[1]*scale))
    box=(math.floor(xy[0]/divisor)*divisor,math.floor(xy[1]/divisor)*divisor,
         math.ceil((xy[0]+art.width)/divisor)*divisor,math.ceil((xy[1]+art.height)/divisor)*divisor)
    expected=clean_background().crop(box).convert('RGBA');expected.alpha_composite(art,(xy[0]-box[0],xy[1]-box[1]))
    neutral=Image.open(ROOT/'assets/library/characters/meerkat/sources/v004/neutral.png').convert('RGBA')
    neutral=neutral.resize(art.size,Image.Resampling.LANCZOS)
    baseline=clean_background().crop(box).convert('RGBA');baseline.alpha_composite(neutral,(xy[0]-box[0],xy[1]-box[1]))
    alpha=Image.new('L',expected.size);alpha.paste(art.getchannel('A'),(xy[0]-box[0],xy[1]-box[1]))
    if divisor!=1:
        size=(expected.width//divisor,expected.height//divisor)
        expected=expected.resize(size,Image.Resampling.BOX);baseline=baseline.resize(size,Image.Resampling.BOX);alpha=alpha.resize(size,Image.Resampling.BOX)
    expected=expected.convert('RGB');baseline=baseline.convert('RGB')
    difference=ImageChops.difference(expected,baseline)
    maximum=ImageChops.lighter(difference.getchannel('R'),ImageChops.lighter(difference.getchannel('G'),difference.getchannel('B')))
    discriminative=maximum.point(lambda value:255 if value>40 else 0)
    return expected,alpha.point(lambda a:255 if a>=128 else 0),discriminative,tuple(v//divisor for v in box)


def inspect_actor(image,state,frame,divisor):
    actor=LOG_ACTORS.get(frame)
    if actor is None:return None
    height,foot=expected_actor_geometry(state)
    expected,mask,discriminative,box=actor_reference(actor['source_path'],actor['source_sha256'],height,tuple(actor['source_anchor_px']),actor['reference_height_px'],tuple(foot),divisor)
    actual=image.crop(box);difference=ImageChops.difference(actual,expected)
    means=ImageStat.Stat(difference,mask).mean
    maximum=ImageChops.lighter(difference.getchannel('R'),ImageChops.lighter(difference.getchannel('G'),difference.getchannel('B')))
    matched=ImageChops.darker(maximum.point(lambda value:255 if value<=35 else 0),discriminative)
    count=discriminative.histogram()[255];fraction=matched.histogram()[255]/count if count else 1.
    return {'frame':frame,'pose':actor['pose'],'action_id':actor.get('action_id'),'divisor':divisor,'display_body_height_px':height,'expected_foot_anchor':foot,'mean_absolute_rgb_error':means,'pose_specific_pixels':count,'pose_specific_match_fraction':fraction,'minimum_pose_specific_match':.80,'passed':max(means)<=7 and (count<8 or fraction>=.80),'scope':'Actual actor pixels versus immutable registered pose at independently required scene scale/foot; non-neutral pixel mask distinguishes static replacement from intended pose'}


def native_frame_indices(plan, events, states):
    result = {0,plan['duration_frames']-1}
    for row in events:
        for at in (row['start_s'],row['end_s'],(row['start_s']+row['end_s'])/2):
            result.update(frame_at(at)+d for d in (-1,0,1))
        if row['id'].startswith(('I','X','O')):
            result.update(frame_at(row['start_s']+(row['end_s']-row['start_s'])*p) for p in (.02,.2,.4,.6,.8,.98))
        if row['id'] in ('X002a','X005a','X010a','X010b','X010c'):
            result.update(range(frame_at(row['start_s'])-1,frame_at(row['end_s'])+1))
        for at in row.get('highlight_timing',{}).values():
            if type(at) in (int,float):result.update(frame_at(at)+d for d in (-1,0,1))
    for state in states.values():
        result.update(frame_at(state['display_start_s'])+d for d in (-1,0,1))
        if state.get('transfer_start_s') is not None:
            result.update(range(frame_at(state['transfer_start_s'])-1,frame_at(state['transfer_end_s'])+1))
    return sorted(f for f in result if 0<=f<plan['duration_frames'])


def compare_render_log(path,events,states,duration_frames):
    errors,counts = [],Counter()
    with gzip.open(path,'rt') as stream:
        records = 0
        for line in stream:
            record = json.loads(line)
            expected = semantic_state(events,states,record['source_frame']/FPS)
            actual = record['state']
            for key in ('mode','n','stage','progress','tick'):
                if actual[key]!=expected[key] and len(errors)<100:
                    errors.append({'frame':record['frame'],'field':key,'expected':expected[key],'observed':actual[key]})
            height,foot = expected_actor_geometry(expected)
            actor = record['actor']
            LOG_ACTORS[record['frame']]=actor
            if actor.get('display_body_height_px')!=height or list(actor.get('target_anchor_px',[]))!=list(foot):
                if len(errors)<100:errors.append({'frame':record['frame'],'actor_geometry_expected':[height,foot],'observed':[actor.get('display_body_height_px'),actor.get('target_anchor_px')]})
            counts[expected['mode']]+=1
            records+=1
    require(records==duration_frames,'Render declaration frame count differs')
    return {'passed':not errors,'frames':records,'mode_counts':dict(counts),'errors':errors,'scope':'Renderer declarations versus independent cue/progress/scene-geometry contract; completed pixels are separately inspected'}


def visual_checks(video,plan,truth,events,states,ffmpeg,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    native=set(native_frame_indices(plan,events,states));coarse_failures=[];counts=Counter();minimums=defaultdict(lambda:1.);decoded=0;actor_count=0;actor_failures=[]
    for frame,image in decoded_frames(video,ffmpeg,directory/'all-frame-half-decode.log',2):
        decoded+=1;at=frame/FPS
        if at<.4 or at>plan['duration_s']-.8:continue
        state=semantic_state(events,states,at)
        actor=inspect_actor(image,state,frame,2)
        if actor:
            actor_count+=1
            if not actor['passed']:
                native.add(frame)
                if len(actor_failures)<100:actor_failures.append(actor)
        if state['mode'] in ('transfer','units','ten','carry-ones','carry-tens','carry-result'):continue
        for row in labels_for(state,truth,states,at):
            if row['size']<30:continue
            report=inspect_label(image,row,frame,2);counts[state['n']]+=1;minimums[row['name']]=min(minimums[row['name']],report['independent_glyph_iou'])
            if not report['passed']:
                native.add(frame);coarse_failures.append({'frame':frame,'component':row['name'],'iou':report['independent_glyph_iou']})
    require(decoded==plan['duration_frames'],'Full-frame decoded count differs')
    failures=[];records=0;components=quantities=highlight_count=0;native_failures={};thumbs=[]
    midpoint_frames={frame_at((r['voice_start_s']+r['voice_end_s'])/2) for r in states.values()}
    with gzip.open(directory/'native-observations.jsonl.gz','wt') as stream:
        for frame,image in decoded_frames(video,ffmpeg,directory/'native-decode.log',1,sorted(native)):
            at=frame/FPS;state=semantic_state(events,states,at)
            if at<.4 or at>plan['duration_s']-.8:
                continue
            reports=[inspect_label(image,row,frame) for row in labels_for(state,truth,states,at)]
            qs=inspect_quantities(image,state,frame);hs=highlight_checks(image,state,frame);actor=inspect_actor(image,state,frame,1)
            bad=[r for r in reports+qs+hs+([actor] if actor else []) if not r['passed']]
            native_failures[frame]=[r.get('name',r.get('highlight')) for r in bad]
            if bad:
                failures.append({'frame':frame,'at_s':at,'state':state,'failures':bad})
            record={'frame':frame,'at_s':at,'state':state,'components':reports,'quantities':qs,'highlights':hs,'actor':actor,'passed':not bad}
            stream.write(json.dumps(record,ensure_ascii=False)+'\n');records+=1;components+=len(reports);quantities+=len(qs);highlight_count+=len(hs)
            if frame in midpoint_frames or state['mode'] not in ('count','transfer') and frame%15==0 or bad and len(failures)<=12:
                image.save(directory/f'native-{frame:06d}-{state["mode"]}.png')
                if len(thumbs)<180:thumbs.append((frame,state['mode'],image.resize((480,270),Image.Resampling.LANCZOS)))
    unresolved=[r for r in coarse_failures if r['component'] in ' '.join(str(x) for x in native_failures.get(r['frame'],[]))]
    sheet=Image.new('RGB',(1440,max(1,math.ceil(len(thumbs)/3))*295),CREAM);draw=ImageDraw.Draw(sheet)
    for i,(frame,mode,thumb) in enumerate(thumbs):
        x,y=i%3*480,i//3*295;sheet.paste(thumb,(x,y));draw.text((x+6,y+273),f'{frame/FPS:.3f}s {mode}',fill=INK)
    sheet.save(directory/'scene-contact-sheet.jpg',quality=92)
    report={'passed':not failures and not unresolved,'decoded_full_frames':decoded,'half_resolution_components':sum(counts.values()),'half_resolution_minimums':dict(minimums),'all_frame_actor_observations':actor_count,'coarse_actor_flags':actor_failures,'native_frames':records,'native_components':components,'native_quantity_observations':quantities,'native_highlight_observations':highlight_count,'native_alignment_tolerance_px':1,'coarse_flags':len(coarse_failures),'unresolved_coarse_flags':unresolved,'failures':failures[:100],'failure_count':len(failures),'scope':'Actual completed MP4: all-frame half-grid tracking plus independent native glyph/each-digit/two-axis/quantity/highlight checks at boundaries, all handover and quantity-motion frames; fade intervals excluded from glyph centering'}
    write_json(directory/'verification.json',report)
    return report


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--video',type=Path)
    result.add_argument('--timeline',type=Path,default=ROOT/'output/lucas-counting-001-v001/audio-build/timeline.json')
    result.add_argument('--master',type=Path,default=ROOT/'output/lucas-counting-001-v001/audio-build/master.wav')
    result.add_argument('--out-dir',type=Path,required=True)
    result.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'))
    result.add_argument('--ffprobe',default=str(ROOT/'.venv/bin/ffprobe'))
    result.add_argument('--render-log',type=Path)
    result.add_argument('--phase',choices=('all','plan','technical','audio','visual'),default='all')
    result.add_argument('--self-test',action='store_true')
    return result


def main(argv=None):
    args=parser().parse_args(argv)
    directory=args.out_dir.resolve()
    require(not directory.exists(),'Choose an unused QA output directory; past evidence is never overwritten')
    directory.mkdir(parents=True)
    shutil.copy2(Path(__file__),directory/'verifier-source.py')
    report={'schema_version':1,'phase':args.phase,'status':'running','checked_at_utc':datetime.now(timezone.utc).isoformat(),'verifier_sha256':sha(Path(__file__)),'errors':[],'scope':'Independent Lucas content, actual decoded pixels and actual stereo waveforms; artistic viewing and phonetic audit are reported separately'}
    try:
        if args.self_test:
            report['negative_controls']=verifier_controls(directory/'negative-controls')
            if args.video is None:
                report.update(status='pass',scope='Verifier positive/negative raster controls only; no episode inspected')
                write_json(directory/'verification.json',report)
                print(json.dumps({'status':report['status'],'path':str(directory/'verification.json')}))
                return 0
        plan=json.loads(args.timeline.read_text())
        truth,events,by,states,schedule=validate_schedule(plan)
        require(plan.get('production_audio_accepted') is True,'Final inspection needs accepted, measured speech')
        report.update(timeline={'path':str(args.timeline),'sha256':sha(args.timeline)},schedule=schedule)
        if args.phase!='plan':
            require(args.video is not None and args.video.is_file(),'Completed video required')
            initial_stat=args.video.stat();initial_sha=sha(args.video)
            report['video']={'path':str(args.video),'sha256':initial_sha,'bytes':initial_stat.st_size}
        for key in ('source_script','source_truth','speech_manifest','speech_acceptance','phonemes'):
            pointer=plan.get(key)
            if isinstance(pointer,dict) and pointer.get('path') and pointer.get('sha256'):
                require(sha(path_of(pointer['path']))==pointer['sha256'],f'Frozen input changed: {key}')
        print('Independent 41-term / 39-expression activity-boundary schedule passed.',flush=True)
        if args.phase in ('all','technical'):
            report['technical']=technical.verify_video(args.video,directory/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            require(report['technical']['status']=='pass','Technical completed-media checks failed')
            require(report['technical']['measurements']['true_peak_dbtp']<=-1.45,'Encoded AAC true peak exceeds accepted -1.5dBTP ceiling')
            print('Full decode / technical checks passed.',flush=True)
        if args.phase in ('all','audio'):
            report['audio']=audio_checks(plan,events,args.video,args.master,args.ffmpeg,directory/'audio')
            report['subtitles']=subtitle_checks(events,[args.timeline.parent/'subtitles.srt',args.timeline.parent/'english-captions.srt'])
            print('All104 source/master/AAC stereo waveforms, silent gaps and subtitle cues passed.',flush=True)
        if args.phase in ('all','visual'):
            log=args.render_log or args.video.parent/'frame-state.jsonl.gz'
            if log.exists():
                report['render_declaration_crosscheck']=compare_render_log(log,events,states,plan['duration_frames'])
            report['visual']=visual_checks(args.video,plan,truth,events,states,args.ffmpeg,directory/'visual')
            require(report['visual']['passed'],'Actual decoded visual checks failed; see visual/verification.json')
            if 'render_declaration_crosscheck' in report:
                require(report['render_declaration_crosscheck']['passed'],'Renderer state/actor geometry declarations disagree with independent timeline')
            print('All-frame / native glyph, each-digit, handover, quantity and highlight checks passed.',flush=True)
        if args.phase!='plan':
            final_stat=args.video.stat()
            require(initial_stat.st_size==final_stat.st_size and initial_stat.st_mtime_ns==final_stat.st_mtime_ns and initial_sha==sha(args.video),'Video changed during inspection')
        report['status']='pass'
    except Exception as error:
        report['status']='fail';report['errors'].append(str(error))
    report['limitations']=['No human continuous full-episode viewing/listening claim','Waveform agreement is not a new ASR/CTC recognition audit','Rendering logs express declarations; actual completed pixel checks are separate','A phase other than all does not constitute complete delivery acceptance']
    write_json(directory/'verification.json',report)
    print(json.dumps({'status':report['status'],'phase':args.phase,'errors':report['errors'],'report':str(directory/'verification.json')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
