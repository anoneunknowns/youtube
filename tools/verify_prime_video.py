"""Independently inspect the prime delivery: decoded pixels, schedule and audio.

Expected prime values come from an Eratosthenes sieve, English labels are parsed
back to integers, and glyph masks are drawn here without importing a producer
renderer. Layout rectangles describe design intent; actual bounds are measured
from decoded foreground pixels. Reports never overwrite previous evidence.
"""
from __future__ import annotations

import argparse
from array import array
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
import subprocess
import tempfile
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat

if __package__:
    from . import verify_video as technical
    from .component_alignment import raster_centering_report
    from .verify_binary_production import _pcm_values, waveform_correlation
else:
    import verify_video as technical
    from component_alignment import raster_centering_report
    from verify_binary_production import _pcm_values, waveform_correlation

ROOT = Path(__file__).resolve().parents[1]
FPS, RATE, SIZE = 30, 48000, (1920, 1080)
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
DESIGN = ROOT / 'design/prime-counting-v1'
CREAM = '#fffaf0'
MAIN = (170, 346, 1240, 590)
READING = (135, 625, 1292, 683)
FACTOR_ONE = (533, 774, 667, 832)
FACTOR_N = (758, 774, 892, 832)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sample(at):
    return round(at * RATE)


def frame_at(at):
    return math.ceil(at * FPS - 1e-7)


def sieve(limit=1000):
    flags = bytearray([1]) * limit
    flags[:2] = b'\0\0'
    for divisor in range(2, math.isqrt(limit - 1) + 1):
        if flags[divisor]:
            first = divisor * divisor
            flags[first:limit:divisor] = b'\0' * len(range(first, limit, divisor))
    return tuple(i for i, prime in enumerate(flags) if prime)


def parse_cardinal(text):
    """Strict inverse parser, independent of the producer's cardinal formatter."""
    names = ('zero one two three four five six seven eight nine ten eleven twelve '
             'thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split()
    small = {word: i for i, word in enumerate(names)}
    tens = dict(zip(('twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'), range(20, 100, 10)))
    tokens = text.lower().replace('-', ' ').split()
    def under_hundred(words):
        if len(words) == 1:
            return small.get(words[0], tens.get(words[0]))
        if len(words) == 2 and words[0] in tens and 1 <= small.get(words[1], -1) <= 9:
            return tens[words[0]] + small[words[1]]
        return None
    if 'hundred' not in tokens:
        return under_hundred(tokens)
    if len(tokens) < 2 or tokens[1] != 'hundred' or tokens.count('hundred') != 1 or not 1 <= small.get(tokens[0], -1) <= 9:
        return None
    rest = under_hundred(tokens[2:]) if len(tokens) > 2 else 0
    return small[tokens[0]] * 100 + rest if rest is not None and (rest > 0 or len(tokens) == 2) else None


def path_of(value):
    value = Path(value)
    return value if value.is_absolute() else ROOT / value


def event_value(row):
    return row.get('decimal_value', row.get('value', row.get('number')))


def checked_design():
    values = sieve()
    require(len(values) == 168 and values[0] == 2 and values[-1] == 997 and sum(values) == 76127,
            'Independent prime sieve has an unexpected invariant')
    counts = json.loads((DESIGN / 'count-lines.json').read_text())
    require([r['value'] for r in counts] == list(values), 'Authored count list has a missing/composite/duplicate value')
    for row in counts:
        require(parse_cardinal(row['text']) == row['value'], f'Incorrect English cardinal: {row}')
        require([d for d in range(1, row['value'] + 1) if row['value'] % d == 0] == [1, row['value']],
                f'Not exactly two positive factors: {row["value"]}')
        require(row['positive_factors'] == [1, row['value']], 'Authored factor list differs')
    narration = json.loads((DESIGN / 'narration.json').read_text())
    require(len(narration) == len({r['id'] for r in narration}) == 188, 'Authored narration IDs are incomplete')
    return values, {r['value']: r['text'] for r in counts}, {r['id']: r for r in narration}


def validate_schedule(plan):
    values, words, authored = checked_design()
    require(plan['fps'] == FPS and plan['duration_frames'] == frame_at(plan['duration_s']), 'Incorrect 30fps timeline grid')
    require(480 <= plan['duration_s'] < 1800, 'Prime long-form delivery must be at least eight minutes')
    events = sorted(plan.get('voice_events', plan.get('events', [])), key=lambda r: r['start_s'])
    require(len(events) == len({r['id'] for r in events}) == 188 and {r['id'] for r in events} == set(authored),
            'Voice event IDs are missing, repeated or unexpected')
    cursor = 0
    for event in events:
        start, end = sample(event['start_s']), sample(event['end_s'])
        require(cursor <= start < end <= sample(plan['duration_s']), f'Overlapping/invalid voice event: {event["id"]}')
        require(event['text'] == authored[event['id']]['text'], f'Voice text differs from approved script: {event["id"]}')
        require(start % 2 == 0 and end % 2 == 0, 'Speech must preserve the 24kHz source sample grid')
        cursor = end
    counts = [event for event in events if authored[event['id']]['kind'] == 'count']
    require([event_value(r) for r in counts] == list(values), 'Actual audio count sequence differs from independent primes')
    states = plan.get('counted_states') or [s for s in plan['scenes'] if s['scene'] == 'count']
    require([event_value(s) for s in states] == list(values), 'Count display sequence differs from independent primes')
    for state, event in zip(states, counts, strict=True):
        display_start = state.get('display_start_s', state.get('start_s'))
        require(sample(event['start_s'] - display_start) == sample(.12), f'Wrong visual lead at {event["id"]}')
        require(abs(state['voice_start_s'] - event['start_s']) < 1e-7 and abs(state['voice_end_s'] - event['end_s']) < 1e-7,
                'Count state disagrees with measured voice times')
        require(parse_cardinal(event['text']) == event_value(event), 'Spoken cardinal does not match main value')
    gaps = Counter()
    for left, right in zip(counts, counts[1:]):
        expected = 18 if event_value(left) in (2, 7, 97) else 2
        gap = sample(right['start_s']) - sample(left['end_s'])
        require(gap == sample(expected), f'Wrong speech-end-to-next-start interval after {left["id"]}')
        gaps[expected] += 1
    require(gaps == {2: 164, 18: 3}, 'Unexpected count gap coverage')
    scenes = plan['scenes']
    require(scenes[0]['start_s'] == 0 and abs(scenes[-1]['end_s'] - plan['duration_s']) < 1e-7, 'Scene coverage misses an endpoint')
    for left, right in zip(scenes, scenes[1:]):
        require(abs(left['end_s'] - right['start_s']) < 1e-7, 'Scene intervals are discontinuous')
    segments = plan['visual_segments']
    require(segments[0]['start_s'] == 0 and abs(segments[-1]['end_s'] - plan['duration_s']) < 1e-7,
            'Visual segments miss timeline endpoints')
    for segment in segments:
        require(segment['start_s'] < segment['end_s'], 'Empty visual segment')
        if segment['mode'] == 'count':
            require(event_value(segment) in values, 'Composite/one appears in normal prime-count mode')
    for left, right in zip(segments, segments[1:]):
        require(abs(left['end_s'] - right['start_s']) < 1e-7, 'Visual segments overlap or leave a hole')
    require([s['mode'] for s in segments if s['end_s'] <= 70.0000001] ==
            ['opening','definition','comparison','rotation','one','opening'],
            'Intro omits or reorders a required definition/example scene')
    for value, mode in ((2,'count'),(7,'nine'),(97,'bridge')):
        count = next(row for row in counts if event_value(row)==value)
        when = count['end_s']+8
        segment = next(s for s in segments if s['start_s'] <= when < s['end_s'])
        require(segment['mode']==mode, f'Missing required {mode} teaching after {value}')
    require(segments[-1]['mode']=='finale','Missing final completed-mosaic scene')
    numeric_s = sum(r['end_s'] - r['start_s'] for r in counts)
    require(abs(plan['duration_s'] - numeric_s - 474.4) < 1 / RATE,
            'Duration differs from measured count voices plus agreed editing waits')
    return events, states, segments, words, {'passed': True, 'prime_count': len(values), 'prime_sum': sum(values),
        'all_english_cardinals_inverse_parsed': len(values), 'positive_factors_exhaustively_checked': len(values),
        'voice_events': len(events), 'ordinary_two_second_gaps': gaps[2], 'extended_eighteen_second_gaps': gaps[18],
        'numeric_voice_duration_s': numeric_s, 'fixed_editing_duration_s': 474.4}


@lru_cache(maxsize=80)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def darkness(image, threshold=137):
    return image.convert('L').point(lambda value: 255 if value < threshold else 0)


def overlap(actual, expected):
    union = ImageChops.lighter(actual, expected).histogram()[255]
    return ImageChops.darker(actual, expected).histogram()[255] / union if union else 1.0


@lru_cache(maxsize=512)
def reference_mask(text, size, field, divisor=1, threshold=137, dx=0, dy=0):
    """Own full-resolution raster and measured-ink placement, then downsample."""
    face = font(size)
    b = face.getbbox(text)
    layer = Image.new('L', (b[2] - b[0] + 80, b[3] - b[1] + 80))
    ImageDraw.Draw(layer).text((40 - b[0], 40 - b[1]), text, font=face, fill=255)
    bounds = layer.point(lambda a: 255 if a >= 128 else 0).getbbox()
    # Match the absolute pixel grid of the actual whole-frame scale/crop. Field
    # edges need not be divisible by four; resizing an unaligned ROI shifts ink.
    origin = ((field[0] // divisor) * divisor, (field[1] // divisor) * divisor)
    right, bottom = (field[2] // divisor) * divisor, (field[3] // divisor) * divisor
    x = round((field[0] + field[2] - bounds[0] - bounds[2]) / 2) - origin[0] + dx
    y = round((field[1] + field[3] - bounds[1] - bounds[3]) / 2) - origin[1] + dy
    result = Image.new('RGB', (right - origin[0], bottom - origin[1]), '#e4efe6' if size == 41 else '#fffaf0')
    result.paste(Image.new('RGB', layer.size, '#246c65' if size in (41,42) else '#423b32'), (x, y), layer)
    if divisor != 1:
        result = result.resize(((field[2] // divisor) - (field[0] // divisor),
                                (field[3] // divisor) - (field[1] // divisor)), Image.Resampling.BOX)
    return darkness(result, threshold)


_selected_masks = {}


def field_score(actual, text, size, field, divisor):
    """Allow the one native pixel rounding ambiguity; center is checked apart.

The font is rasterized here on its own canvas. A crop-then-position compositor
can pick either integer at a half pixel. This is never a free search for text:
only the independently approved string and at most one original pixel of
placement ambiguity are allowed. Native foreground center still must be <=1px.
"""
    key = text, size, field, divisor
    expected = _selected_masks.get(key)
    if expected is None:
        candidates = [(overlap(actual, reference_mask(text, size, field, divisor, 137, dx, dy)), dx, dy)
                      for dy in (-1,0,1) for dx in (-1,0,1)]
        _, dx, dy = max(candidates)
        expected = reference_mask(text, size, field, divisor, 137, dx, dy)
        _selected_masks[key] = expected
    return overlap(actual, expected)


def count_fields(value, words):
    return [('main-number', str(value), 285, MAIN), ('reading', words[value], 42, READING),
            ('factor-one', '1', 41, FACTOR_ONE), ('factor-value', str(value), 41, FACTOR_N)]


def decoded_frames(video, ffmpeg, log, divisor=4, indices=None):
    w, h = SIZE[0] // divisor, SIZE[1] // divisor
    filters = []
    if indices is not None:
        # Balanced sum of between ranges avoids a very long deeply nested expression.
        def combine(terms):
            if len(terms)==1:return terms[0]
            middle=len(terms)//2
            return f'({combine(terms[:middle])}+{combine(terms[middle:])})'
        filters.append('select=' + combine([f'eq(n\\,{i})' for i in indices]))
    if divisor != 1:
        filters.append(f'scale={w}:{h}:flags=area:in_color_matrix=bt709')
    filters.append('format=rgb24')
    command = [ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', str(video), '-an', '-vf', ','.join(filters),
               '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    with log.open('xb') as errors, subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
        iterator = iter(indices) if indices is not None else iter(range(10000000))
        for index in iterator:
            data = process.stdout.read(w * h * 3)
            if not data and indices is None:
                break
            require(len(data) == w * h * 3, f'Unexpected decoder EOF at frame {index}')
            yield index, Image.frombytes('RGB', (w, h), data)
        require(not process.stdout.read(1), 'Extra selected decode frames')
        require(process.wait() == 0, 'Actual video decode failed')


def segment_at(segments, starts, index):
    return segments[max(0, bisect_right(starts, index / FPS + 1e-9) - 1)]


def tile_components(image, field, color, min_pixels=80, *, name=None, alpha=1):
    crop = image.crop(field)
    width, height = crop.size
    def selected(pixel):
        r, g, b = pixel
        if color == 'teal':
            return g-r > 20 and b-r > 12 and 50 < g < 200 and 40 < b < 195
        return r-g > 35 and g-b > 12 and 125 < r < 225 and 45 < g < 175 and 25 < b < 155
    if name in TILE_GEOMETRY:
        fill = TILE_GEOMETRY[name][4]
        baseline = Image.new('RGB',crop.size,fill) if fill else clean_background().crop(field)
        channels = ImageChops.difference(crop,baseline).split()
        difference = ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
        threshold = max(12,round(45*alpha))
        pending = {i for i, value in enumerate(difference.get_flattened_data()) if value >= threshold}
    else:
        pending = {i for i, pixel in enumerate(crop.get_flattened_data()) if selected(pixel)}
    found = []
    while pending:
        seed = pending.pop()
        todo, points = [seed], [seed]
        while todo:
            at = todo.pop(); x, y = at % width, at // width
            adjacent = ([at-1] if x else []) + ([at+1] if x+1 < width else [])
            adjacent += ([at-width] if y else []) + ([at+width] if y+1 < height else [])
            for other in adjacent:
                if other in pending:
                    pending.remove(other); todo.append(other); points.append(other)
        if len(points) >= min_pixels:
            xs, ys = [p % width for p in points], [p // width for p in points]
            found.append({'pixels': len(points), 'bbox': [min(xs)+field[0], min(ys)+field[1], max(xs)+1+field[0], max(ys)+1+field[1]]})
    return found


TILE_FIELDS = {
    'comparison': [('five', (158,475,674,735), 'teal', 5), ('six', (757,475,1273,735), 'terracotta', 6)],
    'rotation': [('horizontal-five', (125,429,740,759), 'teal', 5), ('vertical-five', (905,366,1240,850), 'teal', 5)],
    'one': [('one', (831,444,1136,634), 'terracotta', 1)],
    'nine': [('nine', (789,399,1215,721), 'terracotta', 9)],
    'finale': [('discovered-primes', (135,596,1296,857), 'teal', 168)],
}

TILE_GEOMETRY = {
    'five': (1,5,81,17,'#f7ebd6'), 'six': (2,3,81,17,'#f7ebd6'),
    'horizontal-five': (1,5,70,16,None), 'vertical-five': (5,1,70,16,None),
    'one': (1,1,104,12,CREAM), 'nine': (3,3,68,13,CREAM),
    'discovered-primes': (6,28,32,8,'#f6ebd6'),
}


@lru_cache(maxsize=1)
def clean_background():
    source = ROOT/'assets/library/worlds/sunlit-mosaic-museum/backgrounds/v001/sunlit-mosaic-museum-background.png'
    with Image.open(source) as image:
        return ImageOps.fit(image.convert('RGB'),SIZE,Image.Resampling.LANCZOS)


def opacity_checks(image, name, field, color, alpha):
    """Read actual tile-center pixels, including intentionally absent endpoints."""
    rows, columns, size, gap, fill = TILE_GEOMETRY[name]
    cx, cy = (field[0]+field[2])/2, (field[1]+field[3])/2
    fg = (36,108,101) if color=='teal' else (169,92,67)
    bg = Image.new('RGB',(1,1),fill).getpixel((0,0)) if fill else None
    measurements=[]
    for row in range(rows):
        for column in range(columns):
            x=round(cx+(column-(columns-1)/2)*(size+gap));y=round(cy+(row-(rows-1)/2)*(size+gap))
            underlying=bg or clean_background().getpixel((x,y))
            expected=[a*alpha+b*(1-alpha) for a,b in zip(fg,underlying)]
            observed=ImageStat.Stat(image.crop((x-2,y-2,x+3,y+3))).mean
            measurements.append({'center_px':[x,y],'observed_rgb_mean':observed,'expected_rgb':expected,
                                 'max_rgb_error':max(abs(a-b) for a,b in zip(observed,expected))})
    maximum=max(m['max_rgb_error'] for m in measurements)
    return {'passed':maximum<=9,'alpha':alpha,'max_rgb_error':maximum,'tolerance_rgb':9,'cells':measurements}


def diagram_alpha(segment, at):
    start, stop = segment['start_s'], segment['end_s']
    fade_in = segment.get('diagram_fade_in_s', 0)
    fade_out = segment.get('diagram_fade_out_s', 0)
    return min(1., (at-start)/fade_in if fade_in else 1., (stop-at)/fade_out if fade_out else 1.)


@lru_cache(maxsize=1)
def approved_teacher_labels():
    """Use the reviewed preproduction specifications, not producer render calls."""
    data=json.loads((DESIGN/'qa/mockup-verification.json').read_text())
    labels={}
    for shot in data['shots']:
        mode=shot['mode']
        if mode not in labels and mode not in ('count','comparison-diagram-transition'):
            labels[mode]=[r for r in shot['components'] if 'text' in r]
    labels['definition']=[{'text':text,'font_size_px':size,'content_box_xyxy':field,'name':name}
        for name,text,size,field in (
            ('series','Num-Num Numbers',30,[1450,72,1875,125]),
            ('definition-heading','WHAT IS A PRIME?',48,[145,284,1285,341]),
            ('definition-greater','GREATER THAN 1',62,[150,401,1280,483]),
            ('definition-two','EXACTLY TWO POSITIVE FACTORS',43,[120,553,1310,613]),
            ('definition-factors','1 AND ITSELF',68,[150,672,1280,758]),
            ('definition-meaning','A factor divides evenly, with no remainder.',34,[125,822,1305,878]),
            ('definition-example','EXAMPLE: 5 has factors 1 and 5.',32,[150,923,1280,967]))]
    return labels


def count_extra_labels(value):
    values=sieve();i=values.index(value)
    footer=('2 is the only even prime.' if value==2 else 'All 168 primes below 1000' if value==997 else
            '   ·   '.join(str(n) for n in values[max(0,i-2):i]+(value,)+values[i+1:i+3]))
    return [{'text':text,'font_size_px':size,'content_box_xyxy':field,'name':name} for name,text,size,field in (
        ('series','Num-Num Numbers',30,[1450,72,1875,125]),
        ('count-progress',f'PRIME {i+1} OF 168',27,[170,280,1240,327]),
        ('factor-caption','POSITIVE FACTORS',23,[170,708,1240,748]),
        ('factor-rule','Exactly two: 1 and itself',31,[170,857,1240,903]),
        ('count-footer',footer,30 if value in (2,997) else 28,[170,923,1240,965]))]


def palette_mask(image,color,tolerance=30):
    channels=[c.point(lambda value,target=target:255 if abs(value-target)<=tolerance else 0)
              for c,target in zip(image.split(),color)]
    return ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2])


def label_background(field,mode,name,text):
    suffix=name.rsplit('/',1)[-1]
    base=clean_background().crop(field)
    if suffix=='series':return base
    fill=None
    if mode in ('count','definition','one','nine','bridge'):fill=CREAM
    elif mode=='opening' and text.isdigit():fill='#e4efe6'
    elif mode=='comparison' and ('equation' in suffix or 'factors' in suffix):
        center=416 if suffix.startswith('five') else 1015
        ImageDraw.Draw(base).rectangle((center-264-field[0],815-field[1],center+264-field[0],994-field[1]),fill=CREAM)
    elif mode=='rotation' and suffix!='rotation-title':
        if suffix=='rotation-rule':
            ImageDraw.Draw(base).rectangle((120-field[0],960-field[1],1310-field[0],1029-field[1]),fill=CREAM)
        else:
            center=432 if suffix=='rotation-horizontal-equation' else 1072
            ImageDraw.Draw(base).rectangle((center-160-field[0],867-field[1],center+160-field[0],950-field[1]),fill=CREAM)
    elif mode=='finale' and suffix=='finale-map':
        ImageDraw.Draw(base).rectangle((165-field[0],930-field[1],1265-field[0],1000-field[1]),fill=CREAM)
    return Image.new('RGB',base.size,fill) if fill else base


def foreground_ink(image,field,mode,name,text):
    crop=image.crop(field)
    palette=((66,59,50),(36,108,101),(129,118,105),(169,92,67))
    color=max(palette,key=lambda candidate:palette_mask(crop,candidate,10).histogram()[255])
    background=label_background(field,mode,name,text)
    contrast=[mean-foreground for mean,foreground in zip(ImageStat.Stat(background).mean,color)]
    channel=max(range(3),key=lambda at:contrast[at])
    boundary=background.getchannel(channel).point(lambda value:round((value+color[channel])/2))
    ink=ImageChops.subtract(boundary,crop.getchannel(channel)).point(lambda value:255 if value>0 else 0)
    contrast_valid=background.getchannel(channel).point(lambda value:255 if value-color[channel]>=20 else 0)
    ink=ImageChops.darker(ink,contrast_valid)
    ink=ImageChops.darker(ink,palette_mask(crop,color,70))
    return ink,color


@lru_cache(maxsize=1500)
def glyph_alpha(text,size):
    face=font(size);b=face.getbbox(text)
    layer=Image.new('L',(b[2]-b[0]+80,b[3]-b[1]+80))
    ImageDraw.Draw(layer).text((40-b[0],40-b[1]),text,font=face,fill=255)
    return layer


def foreground_shape_score(actual,text,size):
    bounds=actual.getbbox()
    if not bounds:return 0
    crop=actual.crop(bounds);alpha=glyph_alpha(text,size);scores=[]
    # Colour-based foreground extraction keeps the dark cores. The finite
    # alpha thresholds cover AA against pale boards and textured wall without
    # guessing different text or resizing a mismatching label to fit.
    for threshold in range(112,233,8):
        expected=alpha.point(lambda value:255 if value>=threshold else 0)
        bbox=expected.getbbox();expected=expected.crop(bbox)
        if abs(expected.width-crop.width)>2 or abs(expected.height-crop.height)>2:continue
        canvas=Image.new('L',crop.size);canvas.paste(expected,(0,0));scores.append(overlap(crop,canvas))
    return max(scores,default=0)


def appearance_mask(image,background):
    channels=ImageChops.difference(image,background).split()
    difference=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
    return ImageChops.darker(darkness(image),difference.point(lambda value:255 if value>=12 else 0))


@lru_cache(maxsize=512)
def label_expected_mask(text,size,field,mode,name,color,dx,dy):
    background=label_background(field,mode,name,text)
    alpha=glyph_alpha(text,size);b=alpha.point(lambda value:255 if value>=128 else 0).getbbox()
    x=round((field[0]+field[2]-b[0]-b[2])/2)-field[0]+dx
    y=round((field[1]+field[3]-b[1]-b[3])/2)-field[1]+dy
    rendered=background.copy();rendered.paste(Image.new('RGB',alpha.size,color),(x,y),alpha)
    return appearance_mask(rendered,background)


_label_masks={}


def label_appearance_score(image,label,mode,color):
    field=tuple(label['content_box_xyxy']);name=label['name'];text=label['text'];size=label['font_size_px']
    actual=appearance_mask(image.crop(field),label_background(field,mode,name,text))
    key=text,size,field,mode,name,color
    if key not in _label_masks:
        _,dx,dy=max((overlap(actual,label_expected_mask(text,size,field,mode,name,color,dx,dy)),dx,dy)
                   for dy in (-1,0,1) for dx in (-1,0,1))
        _label_masks[key]=label_expected_mask(text,size,field,mode,name,color,dx,dy)
    return overlap(actual,_label_masks[key])


def native_labels(image,labels,index,mode='count'):
    reports=[]
    for label in labels:
        field=tuple(label['content_box_xyxy']);actual,color=foreground_ink(image,field,mode,label['name'],label['text'])
        report=raster_centering_report(actual,field,origin_xy=field[:2],tolerance_px=1,
                                        name=f'frame{index}/{label["name"]}')
        score=label_appearance_score(image,label,mode,color)
        # The branding sits on a textured window; the finite palette method
        # loses a few AA pixels there. Its actual two-axis bounds stay strict.
        minimum=.95 if label['text']=='Num-Num Numbers' else .975
        report.update(text=label['text'],font_size_px=label['font_size_px'],independent_glyph_iou=score,
                      minimum_glyph_iou=minimum,foreground_palette_rgb=color,
                      extraction='Bounds: half-contrast between finite foreground and independent wall/board fill, gated by palette distance<=70. Shape: dark actual ink differing>=12RGB from independent background versus own font raster.')
        report['passed']=report['passed'] and score>=minimum
        reports.append(report)
    return reports


def visual_checks(video, plan, states, segments, words, ffmpeg, directory):
    starts = [s['start_s'] for s in segments]
    errors, metrics, per_value = [], defaultdict(lambda: 1.), Counter()
    decoded, field_checks = 0, Counter()
    opening, closing = [], []
    for index, image in decoded_frames(video, ffmpeg, directory/'all-frame-decode.log'):
        decoded += 1
        at = index / FPS
        segment = segment_at(segments, starts, index)
        if segment['mode'] == 'count' and .8 <= at < plan['duration_s'] - 2:
            value = event_value(segment)
            per_value[value] += 1
            for name, text, size, field in count_fields(value, words):
                crop = image.crop(tuple(v // 4 for v in field))
                score = field_score(darkness(crop), text, size, field, 4)
                metrics[name] = min(metrics[name], score); field_checks[name] += 1
                if score < (.92 if name == 'main-number' else .86) and len(errors) < 100:
                    errors.append(f'Frame {index}/{value}/{name}: glyph IoU {score:.6f}')
        if at < .8 or at >= plan['duration_s'] - 2:
            distance = sum(ImageStat.Stat(ImageChops.difference(image, Image.new('RGB', image.size, CREAM))).mean)
            (opening if at < .8 else closing).append(distance)
    require(decoded == plan['duration_frames'], 'Full actual decode frame count differs from timeline')
    require(set(per_value) == set(sieve()), 'All-frame tracking failed to observe each prime')
    # Native frames: every value, shortest/longest and important boundary crossings.
    native = {plan['duration_frames']-1}
    for row in states:
        native.add(frame_at((row['voice_start_s'] + row['voice_end_s'])/2))
        if event_value(row) in (2,3,7,11,97,101,773,997):
            for t in (row['voice_start_s']-1/FPS, row['voice_start_s'], row['voice_end_s']-1/FPS, row['voice_end_s']):
                native.add(frame_at(t))
    for segment in segments:
        if segment['mode'] != 'count':
            native.add(frame_at((segment['start_s']+segment['end_s'])/2))
            if segment['mode'] in TILE_FIELDS:
                for age in (.0,.2,.5):
                    native.add(frame_at(segment['start_s']+age))
                if segment.get('diagram_fade_out_s'):
                    native.add(frame_at(segment['end_s']-.2))
    native = sorted(i for i in native if 0 <= i < plan['duration_frames'])
    records, thumbnails = [], []
    for index, image in decoded_frames(video, ffmpeg, directory/'native-decode.log', 1, native):
        at = index / FPS; segment = segment_at(segments, starts, index); mode = segment['mode']
        record = {'frame':index,'at_s':at,'mode':mode,'components':[],'diagrams':[]}
        if mode == 'count' and .8 <= at < plan['duration_s']-2:
            value = event_value(segment);record['value']=value
            for name,text,size,field in count_fields(value,words):
                actual=darkness(image.crop(field))
                score=field_score(actual,text,size,field,1)
                report=raster_centering_report(actual,field,origin_xy=field[:2],name=f'frame{index}/{name}',tolerance_px=1)
                report.update(text=text,independent_glyph_iou=score,threshold=137)
                record['components'].append(report)
                if not report['passed'] or score < .975:
                    errors.append(f'Native {index}/{value}/{name}: centered={report["passed"]}, IoU={score:.6f}')
        if .8 <= at < plan['duration_s']-2:
            labels=count_extra_labels(event_value(segment)) if mode=='count' else approved_teacher_labels().get(mode,[])
            for report in native_labels(image,labels,index,mode):
                record['components'].append(report)
                if not report['passed']:
                    errors.append(f'Native {index}/{report["text"]}: decoded foreground bounds or glyph shape failed')
        alpha=diagram_alpha(segment,at)
        if mode in TILE_FIELDS and at < plan['duration_s']-2:
            record['opacity_checks']=[]
            for name,field,color,quantity in TILE_FIELDS[mode]:
                opacity=opacity_checks(image,name,field,color,alpha)
                record['opacity_checks'].append({'id':name,**opacity})
                if not opacity['passed']:
                    errors.append(f'Native {index}/{mode}/{name}: tile opacity RGB error {opacity["max_rgb_error"]:.3f}')
        if mode in TILE_FIELDS and .45 <= alpha <= 1 and at < plan['duration_s']-2:
            for name,field,color,quantity in TILE_FIELDS[mode]:
                components=tile_components(image,field,color,name=name,alpha=alpha)
                record['diagrams'].append({'id':name,'expected_quantity':quantity,'observed_quantity':len(components),
                                           'alpha':alpha,'components':components,
                                           'extraction':'Actual decoded RGB difference from independently loaded clean wall or specified tray fill; max-channel threshold=max(12,45*alpha)'})
                if len(components)!=quantity:
                    errors.append(f'Native {index}/{mode}/{name}: {len(components)} actual tiles, expected{quantity}')
                if components:
                    mask=Image.new('L',(field[2]-field[0],field[3]-field[1]));draw=ImageDraw.Draw(mask)
                    for component in components:
                        b=component['bbox'];draw.rectangle((b[0]-field[0],b[1]-field[1],b[2]-1-field[0],b[3]-1-field[1]),fill=255)
                    report=raster_centering_report(mask,field,origin_xy=field[:2],name=f'frame{index}/{name}',tolerance_px=1)
                    record['components'].append(report)
                    if not report['passed']:errors.append(f'Native {index}/{name}: decoded tile group is not centered')
        if index==plan['duration_frames']-1:
            record['cream_max_rgb_error']=[max(c.getextrema()) for c in ImageChops.difference(image,Image.new('RGB',SIZE,CREAM)).split()]
            if max(record['cream_max_rgb_error'])>5:errors.append('Final frame does not end in clean cream')
        important=(mode!='count' or event_value(segment) in (2,97,101,773,997))
        if important:
            image.save(directory/f'native-frame-{index:06d}.png')
            thumbnails.append((index,mode,image.resize((480,270),Image.Resampling.LANCZOS)))
        records.append(record)
    if any(b+.5<a for a,b in zip(opening,opening[1:])):errors.append('Opening cream fade is nonmonotonic')
    if any(b>a+.5 for a,b in zip(closing,closing[1:])):errors.append('Closing cream fade is nonmonotonic')
    contact=Image.new('RGB',(1440,math.ceil(len(thumbnails)/3)*300),CREAM);draw=ImageDraw.Draw(contact)
    for i,(index,mode,image) in enumerate(thumbnails):
        x,y=(i%3)*480,(i//3)*300;contact.paste(image,(x,y));draw.text((x+8,y+274),f'{index/FPS:.3f}s {mode}',fill='#423b32')
    contact.save(directory/'scene-contact-sheet.jpg',quality=92)
    return {'passed':not errors,'decoded_frames':decoded,'all_frame_field_checks':dict(field_checks),
            'minimum_quarter_resolution_glyph_iou':dict(metrics),'per_prime_count_frames':dict(per_value),
            'native_samples':records,'foreground_threshold':137,'final_centering_tolerance_px':1,
            'expected_prime_or_word_function_imported_from_producer':False,'errors':errors}


def audio_checks(plan, events, video, master, ffmpeg, directory, excerpt_directory=None):
    references={}
    for row in events:
        path=path_of(row['source_path']);key=row['source_sha256'];require(sha(path)==key,f'Changed speech source{row["id"]}')
        if path not in references:
            output=directory/f'source-{len(references):03d}.wav'
            subprocess.run([ffmpeg,'-nostdin','-v','error','-xerror','-n','-i',str(path),'-ar',str(RATE),'-ac','1','-c:a','pcm_s16le',str(output)],check=True)
            with wave.open(str(output),'rb') as clip:references[path]=_pcm_values(clip.readframes(clip.getnframes()))
    results=[]
    for name,source,lossy in (('master',master,False),('aac',video,True)):
        target=directory/f'{name}-stereo.wav'
        subprocess.run([ffmpeg,'-nostdin','-v','error','-xerror','-n','-i',str(source),'-map','0:a:0','-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(target)],check=True)
        checks,silence=[],[];guard=sample(.03 if lossy else .002)
        with wave.open(str(target),'rb') as track:
            require(abs(track.getnframes()-sample(plan['duration_s']))<=(2048 if lossy else 0),'Audio duration differs from timeline')
            cursor=0
            for row in events:
                start,end=sample(row['start_s']),sample(row['end_s']);reference=references[path_of(row['source_path'])]
                require(abs(len(reference)-(end-start))<=2,f'Source duration differs at{row["id"]}')
                gap_start=cursor+(guard if cursor else 0);gap_size=start-guard-gap_start
                if gap_size>0:
                    track.setpos(gap_start);silence.append(max(map(abs,_pcm_values(track.readframes(gap_size))),default=0))
                track.setpos(max(0,start-8));actual=_pcm_values(track.readframes(len(reference)+16))
                channels=[waveform_correlation(reference,actual[ch::2],8) for ch in (0,1)]
                require(min(v[0] for v in channels)>=.97,f'Actual{name} audio differs at{row["id"]}:{channels}')
                checks.append({'id':row['id'],'source_sha256':row['source_sha256'],'left_correlation':channels[0][0],
                               'left_lag_samples':channels[0][1],'right_correlation':channels[1][0],'right_lag_samples':channels[1][1]})
                cursor=end
            if cursor+guard<track.getnframes():
                track.setpos(cursor+guard);silence.append(max(map(abs,_pcm_values(track.readframes(track.getnframes()))),default=0))
        peak=max(silence,default=0);require(peak<=(3 if lossy else 1),f'Unexpected{name} sound outside scheduled voices:{peak}PCM16')
        results.append({'kind':name,'sha256':sha(source),'passed':True,'events':checks,'channels_per_event':2,
                        'minimum_correlation':min(min(r['left_correlation'],r['right_correlation']) for r in checks),
                        'silence_intervals_checked':len(silence),'maximum_silent_interior_peak_pcm16':peak,'boundary_guard_s':guard/RATE})
        if lossy and excerpt_directory is not None:
            clips=Path(excerpt_directory);clips.mkdir(parents=True,exist_ok=False)
            manifest={'schema_version':1,'measurement_status':'measured','numbers':[],'dialogue':[],
                'source_video_sha256':sha(video),'excerpt_format':{'sample_rate_hz':RATE,'channels':1,'sample_width_bits':16},
                'scope':'Final AAC event cuts from decoded left channel at 48kHz PCM16 with up to80ms original context on either side, clamped before adjacent speech. Recognition inputs only, not newly adopted source speech.'}
            with wave.open(str(target),'rb') as track:
                for ordinal,row in enumerate(events):
                    previous_end=events[ordinal-1]['end_s'] if ordinal else 0
                    next_start=events[ordinal+1]['start_s'] if ordinal+1<len(events) else track.getnframes()/RATE
                    before=min(.08,max(0,(row['start_s']-previous_end)/2))
                    after=min(.08,max(0,(next_start-row['end_s'])/2))
                    clip_start=sample(row['start_s']-before);clip_end=sample(row['end_s']+after)
                    track.setpos(clip_start);stereo=_pcm_values(track.readframes(clip_end-clip_start))
                    mono=array('h',stereo[::2]);destination=clips/f'{row["id"]}.wav'
                    with wave.open(str(destination),'wb') as clip:
                        clip.setparams((1,2,RATE,len(mono),'NONE','not compressed'));clip.writeframes(mono.tobytes())
                    record={'id':row['id'],'path':destination.name,'spoken_text':row['text'],'duration_s':len(mono)/RATE,
                            'clip_duration_s':len(mono)/RATE,'sha256':sha(destination),
                            'speech_offset_s':row['start_s']-clip_start/RATE,
                            'nominal_event_duration_s':row['end_s']-row['start_s'],
                            'event_start_s':row['start_s'],'event_end_s':row['end_s'],
                            'excerpt_start_s':clip_start/RATE,'excerpt_end_s':clip_end/RATE,
                            'guard_before_s':row['start_s']-clip_start/RATE,
                            'guard_after_s':clip_end/RATE-row['end_s']}
                    if row['id'].startswith('N'):record['number']=event_value(row);manifest['numbers'].append(record)
                    else:manifest['dialogue'].append(record)
            (clips/'measurements.json').write_text(json.dumps(manifest,indent=2)+'\n')
            exported=json.loads(json.dumps(manifest))
            for row in exported['numbers']+exported['dialogue']:
                row['path']=f'{clips.name}/{row["path"]}'
            with (clips.parent/'final-aac-manifest.json').open('x') as stream:
                json.dump(exported,stream,indent=2);stream.write('\n')
    return {'passed':True,'tracks':results,
            'recognition_excerpt_manifest':str(Path(excerpt_directory).parent/'final-aac-manifest.json') if excerpt_directory is not None else None,
            'scope':'All 188 scheduled source waveforms against master and actual AAC, both stereo channels, with guarded silent intervals. No recognition or human-listening claim.'}


def captions_and_metadata(plan, events, directory):
    path=next((directory/n for n in ('subtitles.srt','english-captions.srt') if (directory/n).is_file()),None)
    require(path is not None,'Missing English captions')
    blocks=path.read_text(encoding='utf-8-sig').replace('\r\n','\n').strip().split('\n\n')
    require(len(blocks)==len(events)==188,'Wrong caption count')
    def stamp(at):
        ms=round(at*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    for i,(block,event) in enumerate(zip(blocks,events,strict=True),1):
        lines=block.splitlines();require(len(lines)==3 and lines[0]==str(i),'Wrong SRT cue numbering/shape')
        require(lines[1]==f'{stamp(event["start_s"])} --> {stamp(event["end_s"])}','Caption timing differs from actual voice')
        require(lines[2]==event['text'],'Caption text differs from actual voice')
    title=directory/'youtube-title.txt';description=directory/'youtube-description.txt';chapters=directory/'chapters.txt'
    for file in (title,description,chapters):require(file.is_file() and file.stat().st_size>0,f'Missing delivery metadata:{file.name}')
    require('997' in title.read_text() and '168' in description.read_text(),'Title/description do not match completed prime range')
    parsed=[]
    for line in chapters.read_text().splitlines():
        match=re.match(r'(?:(\d+):)?(\d{1,2}):(\d\d)\s+(.+)',line)
        if match:
            hour,minute,second,label=match.groups();parsed.append(((int(hour or 0)*3600)+int(minute)*60+int(second),label))
    require(parsed and parsed[0][0]==0 and all(a[0]<b[0] for a,b in zip(parsed,parsed[1:])),'Chapter timestamps are missing or unordered')
    require(parsed[-1][0]<plan['duration_s'],'Chapter starts after delivery ends')
    return {'passed':True,'caption_cues':188,'chapters':parsed,'title':title.read_text().strip(),'caption_sha256':sha(path)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video',type=Path,required=True);p.add_argument('--timeline',type=Path,required=True)
    p.add_argument('--master',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--delivery-dir',type=Path,help='Directory containing captions/title/description/chapters; defaults to video.parent')
    p.add_argument('--final-aac-clips-dir',type=Path,help='Persistent excerpt directory; default video.parent/audio-final-qa/clips')
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));p.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    p.add_argument('--extract-final-clips',action='store_true');p.add_argument('--skip-technical',action='store_true')
    args=p.parse_args(argv);require(args.ffmpeg and args.ffprobe,'FFmpeg andffprobe are required')
    args.out_dir.mkdir(parents=True,exist_ok=False)
    plan=json.loads(args.timeline.read_text());events,states,segments,words,schedule=validate_schedule(plan)
    report={'schema_version':1,'kind':'independent-prime-final-video-verification','checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'video':str(args.video.resolve()),'video_sha256':sha(args.video),'timeline_sha256':sha(args.timeline),'schedule':schedule}
    try:
        if not args.skip_technical:
            report['technical']=technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            require(report['technical']['status']=='pass','Technical media checks failed')
            require(report['technical']['measurements']['true_peak_dbtp']<=-1.45,'Finaltruepeak exceeds intended-1.5dBTP with.05dBtolerance')
        report['captions_and_metadata']=captions_and_metadata(plan,events,args.delivery_dir or args.video.parent)
        excerpt_dir=(args.final_aac_clips_dir or args.video.parent/'audio-final-qa'/'clips') if args.extract_final_clips else None
        with tempfile.TemporaryDirectory(prefix='prime-audio-qa-') as work:
            report['audio']=audio_checks(plan,events,args.video,args.master,args.ffmpeg,Path(work),excerpt_dir)
        if excerpt_dir is not None:
            print(json.dumps({'event':'final_aac_manifest_ready','path':report['audio']['recognition_excerpt_manifest']}),flush=True)
        report['visual']=visual_checks(args.video,plan,states,segments,words,args.ffmpeg,args.out_dir)
        require(report['visual']['passed'],'Decoded-pixel visual checks failed')
        report['passed']=True
    except Exception as error:
        report['passed']=False;report['error']=str(error)
        raise
    finally:
        report['scope']='Fullactualdecode; allcountframes independentglyph tracking; native all168values and teaching diagrams;188sourcevoices versus bothmaster/AACchannels; guarded silence; captions/metadata. Automated checks plus extracted stills; no humancontinuousviewing/listening.'
        (args.out_dir/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json'),'video_sha256':report['video_sha256']}))


if __name__=='__main__':main()
