"""Render the measured Fibonacci episode, including arithmetic and memory motion.

The accepted preproduction plate, character snapshot and type hierarchy are
retained. New results commit together with their English reading 0.12 seconds
before speech. Arithmetic replays generate decimal columns right to left.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass
from functools import lru_cache
from itertools import groupby
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageDraw, ImageOps

try:
    import render_fibonacci_mockups as m
except ModuleNotFoundError:
    from tools import render_fibonacci_mockups as m

ROOT, DESIGN, FPS, SIZE = m.ROOT, m.DESIGN, 30, m.SIZE
VIDEO_NAME = 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
CHECKPOINTS = (2, 8, 13, 18, 26, 39)
CARRY_INDICES = (8, 13, 18)
CARRY_CENTERS = {2: (450, 610), 3: (380, 510, 640), 4: (300, 420, 540, 660)}
CARRY_ROWS = {'carry': (412, 463), 'a': (482, 586), 'b': (621, 725), 'c': (801, 905)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(path):
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def frame_at(seconds):
    return math.ceil(seconds * FPS - 1e-7)


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def carry_steps(a, b):
    """Exact decimal column operations; units first and commas never count."""
    if not (isinstance(a, int) and isinstance(b, int) and a >= 0 and b >= 0):
        raise ValueError('Carry inputs must be nonnegative integers')
    count = len(str(a + b))
    steps, incoming = [], 0
    for power in range(count):
        aa, bb = (a // (10 ** power)) % 10, (b // (10 ** power)) % 10
        total = aa + bb + incoming
        outgoing, digit = divmod(total, 10)
        steps.append({'power': power, 'a_digit': aa, 'b_digit': bb,
                      'carry_in': incoming, 'total': total, 'digit': digit,
                      'carry_out': outgoing})
        incoming = outgoing
    if incoming or sum(s['digit'] * 10 ** s['power'] for s in steps) != a + b:
        raise ValueError('Decimal carry reconstruction differs from the sum')
    return steps


@dataclass(frozen=True)
class Frame:
    mode: str
    n: int | None = None
    stage: str = 'result'
    transfer_tick: int = 0
    carry_column: int = -1
    carry_stage: str = 'align'
    carry_tick: int = 0
    pose: str = 'watch_left'
    cream: int = 0
    legend: str = ''


@lru_cache(maxsize=2400)
def glyph(text, size, color):
    return m.text_layer(text, size, color)


@lru_cache(maxsize=16)
def recurrence(size):
    return m.recurrence_layer(size)


class Canvas(m.Canvas):
    def text(self, text, field, size, color=m.INK, ident=None, opacity=1):
        self.center_layer(glyph(text, size, color), field, ident or text, opacity)
        if opacity:
            self.records[-1].update(text=text, font_size_px=size)


def replay_tag(c, label='REPLAY'):
    c.text(label, (980, 220, 1330, 270), 25, m.RUST, 'replay-label')
    c.data['replay'] = True


def opening(c):
    c.left('Watch the next', (105, 305), 76)
    c.left('number take shape.', (105, 414), 76)
    c.left('Two numbers in. A new number out.', (110, 548), 35, m.TEAL)
    for x, value, label, color in ((410, 0, 'F0', m.BLUE), (1020, 1, 'F1', m.TEAL)):
        c.panel((x-200, 676, x+200, 879), m.PALE, color)
        c.text(str(value), (x-175, 694, x+175, 815), 112, color, f'opening-seed-{value}')
        c.text(label, (x-150, 831, x+150, 867), 25, color, f'opening-index-{value}')
    c.text('START WITH 0 AND 1 · FOLLOW THE LAST TWO', (100, 944, 1350, 1004), 30, m.MUTED, 'opening-rule')
    c.data.update(mode='opening', initial_conditions=[0, 1], final_result_revealed=False)


def seed_count(c, n):
    value = m.VALUES[n]
    c.text('A STARTING VALUE', (110, 286, 1330, 354), 45, m.TEAL, 'seed-label')
    c.text(f'F{n}', (120, 408, 1320, 477), 49, m.BLUE, 'seed-index')
    c.text(str(value), (118, 530, 1310, 740), 190, m.INK, 'seed-value')
    c.text(m.words(value), (105, 825, 1335, 929), 32, m.TEAL, 'result-reading')
    c.text(f'TERM {n+1} OF 41 · INDEX n = {n}', (130, 968, 1310, 1016), 25, m.MUTED, 'term-progress')
    c.data.update(index=n, ordinal=n+1, result=value, stage='seed', initial_value=True)


def equation(c, n, stage, progress=0):
    # Retain every accepted count rectangle, font size and whole-reading group.
    # In transfer the prior result remains below, while copies form the next pair.
    m.equation(c, n, stage=stage, transfer=progress)
    if stage == 'input-a':
        field, color = (98, 340, 450, 494), m.BLUE
    elif stage == 'input-b':
        field, color = (538, 340, 890, 494), m.TEAL
    else:
        field, color = None, None
    if field:
        c.draw.rounded_rectangle(field, radius=29, outline=color, width=5)
    if stage == 'input-b':
        # Emphasis stays outside the operator's glyph measurement rectangle.
        c.draw.line((470, 480, 518, 480), fill=m.TEAL, width=4)
    elif stage == 'flow':
        c.draw.line((910, 480, 958, 480), fill=m.RUST, width=4)
    c.data['active_emphasis'] = {'input-a': ['older'], 'input-b': ['plus', 'newer'],
                                'flow': ['equals', 'computation-path'],
                                'result': ['new-value'], 'transfer': ['newest-pair']}[stage]
    c.data['result_known_on_screen'] = stage in ('result', 'transfer')


def legend(c, name):
    if name in ('range', 'I08'):
        c.text('THE SAME RULE, ALL THE WAY', (100, 296, 1340, 380), 45, m.TEAL, 'range-heading')
        c.text('FIRST PAST', (100, 472, 1340, 542), 42, m.MUTED, 'range-label')
        c.text('100,000,000', (100, 590, 1340, 749), 113, m.INK, 'range-threshold')
        c.text('The final value is still to come.', (110, 899, 1330, 990), 36, m.TEAL, 'range-future')
        c.data.update(threshold=100_000_000, final_result_revealed=False)
    elif name in ('postal-metaphor', 'I07'):
        c.text('A WINDOW SHOWS A VALUE', (100, 286, 1340, 376), 44, m.TEAL, 'value-heading')
        c.panel((310, 463, 1130, 696), m.PALE, m.TEAL)
        c.text('1,000', (350, 493, 1090, 666), 142, m.INK, 'value-example')
        c.multiline(['This is the number one thousand.', 'The window is not a pile of objects.'], (110, 795, 1330, 953), 35, m.MUTED, 'value-meaning')
        c.data.update(example_only=True, quantity_model=False)
    elif name in ('input-legend', 'output-legend', 'I05', 'I06'):
        equation(c, 2, 'input-a' if name in ('input-legend', 'I05') else 'flow')
        c.text('EXAMPLE · INPUTS AND OUTPUT', (950, 220, 1340, 275), 21, m.RUST, 'legend-example')
        c.data['example_only'] = True
    elif name in ('indices', 'I04'):
        c.text('EVERY TERM HAS ITS OWN PLACE', (100, 285, 1340, 366), 42, m.TEAL, 'indices-heading')
        for x, n, role, color in ((300, 0, 'FIRST', m.BLUE), (715, 1, 'SECOND', m.TEAL), (1130, 2, 'THIRD', m.RUST)):
            c.panel((x-170, 440, x+170, 743), m.PALE, color)
            c.text(f'F{n}', (x-140, 464, x+140, 557), 68, color, f'index-example-{n}')
            c.text(str(m.VALUES[n]), (x-140, 580, x+140, 691), 95, m.INK, f'index-value-{n}')
            c.text(role, (x-140, 814, x+140, 868), 29, color, f'index-role-{n}')
        c.text('The index starts at zero.', (110, 941, 1330, 1000), 34, m.MUTED, 'indices-zero')
        c.data['example_only'] = True
    else:
        m.general_rule(c)


def carry(c, n, column=-1, phase='align', progress=0):
    a, b, result = m.VALUES[n-2:n+1]
    steps = carry_steps(a, b)
    columns = len(steps)
    centers = CARRY_CENTERS[columns]
    replay_tag(c)
    c.text('THE SAME RULE, WITH A CARRY', (100, 285, 1350, 349), 43, m.TEAL, 'carry-heading')
    c.text(f'F{n-2} + F{n-1} = F{n}', (780, 357, 1350, 395), 25, m.MUTED, 'carry-indices')
    c.panel((145, 398, 780, 941), m.CREAM, '#bed0d0')
    complete = phase == 'complete'
    processed = columns if complete else max(0, column + (phase in ('write', 'move')))
    current = min(columns-1, max(0, column))
    active_col = columns - 1 - current
    if not complete and column >= 0:
        x = centers[active_col]
        c.draw.rounded_rectangle((x-55, 472, x+55, 914), radius=14, outline='#cc9973', width=3)
    for row, number, color in (('a', a, m.BLUE), ('b', b, m.TEAL)):
        digits = str(number).rjust(columns)
        top, bottom = CARRY_ROWS[row]
        for col, char in enumerate(digits):
            if char != ' ':
                x = centers[col]
                c.text(char, (x-49, top, x+49, bottom), 97, color, f'column-{row}-{col}')
    for col, char in enumerate(str(result).rjust(columns)):
        power = columns - 1 - col
        x = centers[col]
        c.text(char if power < processed else '?', (x-49, 801, x+49, 905), 97, m.RUST, f'column-c-{col}')
    # A carry is only shown once generated by the column immediately to its right.
    for step in steps:
        p = step['power']
        if not step['carry_out'] or p >= columns-1:
            continue
        generated = complete or p < column or (p == column and phase == 'move')
        if not generated:
            continue
        if not complete and p < column:
            # The incoming carry is consumed by this column before its own
            # outgoing carry is generated; two different ones must not occupy
            # the same carry position during the transfer's entry frame.
            if p != column-1 or phase in ('write', 'move'):
                continue
        target = centers[columns - 2 - p]
        if not complete and p == column and phase == 'move':
            source = centers[columns - 1 - p]
            x = source + (target-source) * progress
            y = 437 - 25 * math.sin(math.pi * progress)
        else:
            x, y = target, 437.5
        c.text(str(step['carry_out']), (x-36, y-25.5, x+36, y+25.5), 39, m.RUST, f'carry-to-power-{p+1}')
    c.text('+', (172, 621, 239, 725), 62, m.TEAL, 'column-plus')
    c.draw.line((211, 769, 720, 769), fill=m.INK, width=4)
    names = ('ones', 'tens', 'hundreds', 'thousands')
    if complete:
        c.text('ADDITION COMPLETE', (814, 418, 1350, 489), 32, m.RUST, 'carry-complete-label')
        c.text(f'{a:,} + {b:,}', (808, 545, 1360, 621), 42, m.INK, 'carry-complete-inputs')
        c.text(f'= {result:,}', (808, 655, 1360, 748), 54, m.TEAL, 'carry-complete-result')
        c.text('Keep the newest pair.', (814, 839, 1350, 900), 28, m.MUTED, 'carry-complete-caption')
    elif column < 0:
        c.multiline(['Line up matching places.', 'Start with the ones.'], (815, 425, 1360, 610), 34, m.INK, 'carry-align-instruction')
        c.text('RIGHT TO LEFT', (815, 755, 1360, 825), 31, m.TEAL, 'carry-direction')
    else:
        s = steps[current]
        expression = f"{s['a_digit']} + {s['b_digit']}" + (f" + {s['carry_in']}" if s['carry_in'] else '') + f" = {s['total']}"
        c.text(expression, (812, 423, 1360, 497), 37, m.RUST, 'carry-current-step')
        detail = [f"Write {s['digit']} in the", f"{names[current]} place."]
        if s['carry_out']:
            next_name = ('ten', 'hundred', 'thousand')[current]
            detail.append(f"Carry {s['carry_out']} {next_name}.")
        else:
            detail.append('No further carry.')
        c.multiline(detail, (810, 540, 1360, 687), 32, m.INK, 'carry-step-detail')
        action = ('CALCULATE', 'WRITE THE DIGIT', 'MOVE THE CARRY')[('compute', 'write', 'move').index(phase)]
        if phase == 'move' and not s['carry_out']:
            action = 'COLUMN COMPLETE'
        c.text(action,
               (812, 740, 1360, 810), 27, m.TEAL, 'carry-action')
        c.text(f'STEP {current+1} OF {columns}', (814, 844, 1350, 897), 27, m.MUTED, 'carry-step-number')
    c.text(f'REPLAY · TERM {n+1} ALREADY COUNTED', (130, 968, 1310, 1016), 24, m.MUTED, 'carry-replay-progress')
    c.data.update(index=n, operands=[a, b], result=result, carry_column_from_right=column,
                  carry_phase=phase, carry_progress=progress, completed_columns_from_right=processed,
                  column_steps=steps, column_centers_px=list(centers), replay=True,
                  result_digits_visible=[i for i in range(columns) if columns-1-i < processed])


def place_groups(c):
    replay_tag(c)
    c.text('MORE DIGITS. THE SAME PLACES.', (100, 290, 1350, 358), 42, m.TEAL, 'group-heading')
    centers = (400, 490, 580, 715, 805, 895)
    for top, number, ident, color in ((465, 46368, 'a', m.BLUE), (610, 75025, 'b', m.TEAL), (805, 121393, 'c', m.RUST)):
        chars = str(number).rjust(6)
        for col, char in enumerate(chars):
            if char != ' ':
                x = centers[col]
                c.text(char, (x-41, top, x+41, top+104), 91, color, f'group-{ident}-{col}')
        c.text(',', (632, top+31, 662, top+104), 69, color, f'group-comma-{ident}')
    c.text('THOUSANDS', (315, 392, 635, 440), 25, m.MUTED, 'group-thousands')
    c.text('ONES', (675, 392, 935, 440), 25, m.MUTED, 'group-ones')
    c.text('+', (219, 610, 294, 714), 62, m.TEAL, 'group-plus')
    c.draw.line((305, 761, 946, 761), fill=m.INK, width=4)
    c.multiline(['COMMAS', 'SEPARATE', 'GROUPS'], (1004, 450, 1355, 677), 31, m.TEAL, 'group-meaning')
    c.multiline(['They are not', 'extra digits.'], (1002, 744, 1355, 876), 29, m.MUTED, 'group-not-digits')
    c.text('ONES COLUMNS STAY LINED UP ON THE RIGHT', (130, 968, 1310, 1016), 25, m.MUTED, 'group-alignment')
    c.data.update(index=26, operands=[46368, 75025], result=121393, replay=True,
                  decimal_digit_centers_px=list(centers), comma_is_digit=False)


def replay(c, state):
    n = state.n
    if n in CARRY_INDICES:
        carry(c, n, state.carry_column, state.carry_stage, state.carry_tick / 30)
    elif n == 2:
        m.repeated_one(c)
        c.data.update(index=2, replay=True, terms_with_value_one=[1, 2])
    elif n == 26:
        place_groups(c)
    elif n == 39:
        equation(c, 40, 'input-a')
        c.text('REPLAY · THE FINAL PAIR', (932, 220, 1342, 272), 22, m.RUST, 'final-pair-replay')
        c.data.update(replay=True, after_index=39, future_result_revealed=False)
    else:
        raise ValueError(f'Unsupported checkpoint index: {n}')


def validate_plan(plan):
    if plan['fps'] != FPS or plan.get('width', 1920) != 1920 or plan.get('height', 1080) != 1080:
        raise ValueError('The production requires1920x1080 at30fps')
    if plan['duration_frames'] != frame_at(plan['duration_s']):
        raise ValueError('Duration does not match the30fps frame grid')
    counted = plan['counted_states']
    if len(counted) != 41 or [s.get('index', s.get('n')) for s in counted] != list(range(41)):
        raise ValueError('Expected every indexF0 throughF40, including both ones')
    for n, row in enumerate(counted):
        if row['value'] != m.VALUES[n]:
            raise ValueError(f'Wrong Fibonacci value atF{n}')
        if abs(row['display_start_s'] - (row['voice_start_s']-.12)) > 1e-7:
            raise ValueError('Results must display0.12seconds before their spoken name')
        if n >= 2 and (row.get('a') != m.VALUES[n-2] or row.get('b') != m.VALUES[n-1]):
            raise ValueError('Incorrect input pair')
        if n >= 2 and row['a'] + row['b'] != row['value']:
            raise ValueError('Arithmetic does not produce the counted result')
    cursor = 0.0
    for seg in plan['visual_segments']:
        if abs(seg['start_s']-cursor) > 1e-6 or seg['end_s'] <= seg['start_s']:
            raise ValueError(f'Visual coverage gap/overlap: {seg}')
        cursor = seg['end_s']
    if abs(cursor - plan['duration_s']) > 1e-6:
        raise ValueError('Visual segments do not cover the episode')
    return {'all41_terms': True, 'exact39_additions': True,
            'display_lead_seconds': .12, 'complete_visual_coverage': True}


def frozen_assets():
    """Bind this episode to its accepted proposal rather than a changing stock."""
    manifest_path = DESIGN/'preproduction-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    expected = {r['path']: r['sha256'] for r in manifest['files']}
    qa_path = DESIGN/'qa/mockup-verification.json'
    if local(qa_path) in expected and digest(qa_path) != expected[local(qa_path)]:
        raise ValueError('Accepted preproduction QA receipt changed')
    qa = json.loads(qa_path.read_text())
    expected.update({r['path']: r['sha256'] for r in qa['sources']})
    paths = (m.BG, m.FONT, m.CAT, DESIGN/'character-selection.json', Path(m.__file__))
    receipts = []
    for path in paths:
        relative = local(path)
        if relative not in expected or digest(path) != expected[relative]:
            raise ValueError(f'Accepted Fibonacci preproduction source changed: {relative}')
        receipts.append({'path': relative, 'sha256': expected[relative]})
    return receipts


class Scene:
    def __init__(self, plan):
        self.plan = plan
        self.duration = plan['duration_s']
        self.frame_count = plan['duration_frames']
        self.segments = plan['visual_segments']
        self.starts = [s['start_s'] for s in self.segments]
        self.validation = validate_plan(plan)
        self.frozen_sources = frozen_assets()
        self.counted = {s.get('index', s.get('n')): s for s in plan['counted_states']}
        self.voice = {e['id']: e for e in plan['voice_events']}
        with Image.open(m.BG) as image:
            self.background = ImageOps.fit(image.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
        self.character = m.Siamese()
        self.cream = Image.new('RGBA', SIZE, m.CREAM)
        self.replays = {}
        for n in CHECKPOINTS:
            matches = [s for s in self.segments if s['mode'] == 'replay' and
                       s.get('params', {}).get('after_index', s.get('index', s.get('n'))) == n]
            if matches:
                self.replays[n] = (min(s['start_s'] for s in matches), max(s['end_s'] for s in matches))

    def state(self, index):
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        t = index / FPS + 1e-9
        seg = self.segments[bisect_right(self.starts, t)-1]
        params = seg.get('params', {})
        mode = seg['mode']
        n = seg.get('index', seg.get('n'))
        phase = params.get('stage', seg.get('stage', 'result'))
        elapsed, length = t-seg['start_s'], seg['end_s']-seg['start_s']
        tick, col, carry_phase, carry_tick = 0, -1, 'align', 0
        legend_name = params.get('scene_id', seg.get('scene', ''))
        if mode == 'count' and n is not None:
            row = self.counted[n]
            if n >= 2:
                display = row['display_start_s']
                transfer_start = row.get('transfer_start_s')
                transfer_end = row.get('transfer_end_s')
                if t < display:
                    # Segments supplied by the builder may use exact word-aligned
                    # boundaries; this does not derive speech timing from pixels.
                    if phase not in ('input-a', 'input-b', 'flow'):
                        phase = self.formula_phase(row, t)
                elif transfer_start is not None and transfer_start <= t:
                    phase = 'transfer'
                    tick = round(smooth((t-transfer_start)/(transfer_end-transfer_start))*30)
                else:
                    phase = 'result'
            else:
                phase = 'seed'
        if mode == 'replay':
            n = params.get('after_index', n)
            if n in CARRY_INDICES:
                start, end = self.replays[n]
                col, carry_phase, carry_tick = self.carry_state(n, t, start, end)
        # The builder groups introductory/outro paragraphs into broad scenes.
        # Select their actual educational focus from the measured voice cues.
        if mode == 'rule' and 'I04' in self.voice and t >= self.voice['I04']['start_s']-.12:
            legend_name = 'indices'
        if mode == 'legend':
            legend_name = 'input-legend'
            for ident, focus in (('I05', 'input-legend'), ('I06', 'output-legend'), ('I07', 'postal-metaphor')):
                if ident in self.voice and t >= self.voice[ident]['start_s']-.12:
                    legend_name = focus
        if mode == 'opening' and 'I08' in self.voice and t >= self.voice['I08']['start_s']-.12:
            mode, legend_name = 'legend', 'range'
        if mode == 'finale':
            legend_name = 'history'
            for ident, focus in (('O01', 'history'), ('O02', 'finale'), ('O03', 'history'), ('O04', 'goodbye')):
                if ident in self.voice and t >= self.voice[ident]['start_s']-.12:
                    legend_name = focus
        pose = self.pose_for(mode, n, elapsed, length, t, seg)
        cream = 0
        if t < .8:
            cream = round(255*(1-t/.8))
        elif t >= self.duration-2:
            final_t = (self.frame_count-1)/FPS
            cream = round(255*(t-self.duration+2)/(final_t-self.duration+2))
        return Frame(mode, n, phase, tick, col, carry_phase, carry_tick,
                     pose, max(0, min(255, cream)), legend_name)

    def formula_phase(self, row, t):
        start = row.get('formula_start_s', row.get('expression_start_s'))
        end = row.get('formula_end_s', row.get('expression_end_s'))
        if start is None or end is None:
            return 'input-a'
        event = self.voice.get(f"E{row.get('index', row.get('n')):03d}", {})
        if event.get('highlight_timing'):
            timing = event['highlight_timing']
            if t < timing['plus_start_s']:
                return 'input-a'
            if t < timing['equals_start_s']:
                return 'input-b'
            return 'flow'
        timings = event.get('word_timings', [])
        plus = next((w['start_s'] for w in timings if w.get('word', '').lower() == 'plus'), None)
        equals = next((w['start_s'] for w in timings if w.get('word', '').lower() == 'equals'), None)
        if plus is None or equals is None:
            a_words = len(m.words(row['a']).replace('-', ' ').split())
            b_words = len(m.words(row['b']).replace('-', ' ').split())
            plus = start + (end-start)*a_words/(a_words+b_words+2)
            equals = start + (end-start)*(a_words+b_words+1)/(a_words+b_words+2)
        if t < plus:
            return 'input-a'
        if t < equals:
            return 'input-b'
        return 'flow'

    def carry_state(self, n, t, start, end):
        steps = carry_steps(*m.VALUES[n-2:n])
        first, second = self.voice.get(f'T{n:03d}a'), self.voice.get(f'T{n:03d}b')
        if first and second and self.replays.get(n) == (start, end):
            # Constrain the column progression by the two actual explanation
            # events. Fractions within a sentence are editorial cues, not a
            # claim of independently measured word alignment.
            first_length = first['end_s']-first['start_s']
            second_length = second['end_s']-second['start_s']
            if n == 8:
                spans = [(first['start_s']+.20, first['end_s']),
                         (second['start_s'], second['end_s']-.20)]
            elif n == 13:
                spans = [(first['start_s']+.15, first['start_s']+first_length*.56),
                         (first['start_s']+first_length*.56, second['start_s']+second_length*.43),
                         (second['start_s']+second_length*.43, second['end_s']-.20)]
            else:
                begin, finish = second['start_s'], second['end_s']-.20
                spans = [(begin+(finish-begin)*p/4, begin+(finish-begin)*(p+1)/4) for p in range(4)]
            if t < spans[0][0]:
                return -1, 'align', 0
            if t >= spans[-1][1]:
                return len(steps)-1, 'complete', 30
            column = next((i for i, (_, finish) in enumerate(spans) if t < finish), len(steps)-1)
            begin, finish = spans[column]
            progress = max(0, min(1, (t-begin)/(finish-begin)))
            if progress < .38:
                return column, 'compute', 0
            if progress < .60:
                return column, 'write', 0
            return column, 'move', round(smooth((progress-.60)/.40)*30)
        total = end-start
        u = max(0, min(1, (t-start)/total))
        if u < .10:
            return -1, 'align', 0
        if u >= .90:
            return len(steps)-1, 'complete', 30
        step = (u-.10)/.80*len(steps)
        col = min(len(steps)-1, int(step))
        p = step-col
        if p < .38:
            return col, 'compute', 0
        if p < .60:
            return col, 'write', 0
        return col, 'move', round(smooth((p-.60)/.40)*30)

    def pose_for(self, mode, n, elapsed, length, t, seg):
        if mode == 'opening':
            return 'greet' if .9 <= elapsed < 2.7 else 'neutral'
        if mode in ('rule', 'legend'):
            if mode == 'rule':
                if elapsed < .4 or elapsed > length-.25:
                    return 'watch_left'
                if elapsed < .65 or elapsed > length-.5:
                    return 'present_half'
                return 'present_full'
            return 'watch_left'
        if mode == 'replay':
            # Expression changes belong to a few explanations, not every term.
            if n == 2:
                return 'think'
            start, end = self.replays.get(n, (seg['start_s'], seg['end_s']))
            p = t-start
            if p < .4:
                return 'watch_left'
            if p < .7:
                return 'present_half'
            if p < 2.2:
                return 'present_full'
            if p < 2.5:
                return 'present_half'
            return 'watch_left'
        if mode == 'finale':
            return 'delighted' if elapsed > .5 else 'neutral'
        return 'watch_left' if mode == 'count' and (n or 0) >= 2 else 'neutral'

    def image(self, state):
        c = Canvas(self.background, json.dumps(asdict(state), sort_keys=True))
        m.header(c)
        if state.mode == 'opening':
            opening(c)
        elif state.mode == 'seeds':
            if state.n is None:
                m.seeds(c)
            else:
                seed_count(c, state.n)
        elif state.mode == 'rule':
            if state.legend in ('indices', 'I04'):
                legend(c, 'indices')
            else:
                m.general_rule(c)
        elif state.mode == 'legend':
            legend(c, state.legend)
        elif state.mode == 'count':
            if state.n < 2:
                seed_count(c, state.n)
            else:
                equation(c, state.n, state.stage, state.transfer_tick/30)
        elif state.mode == 'replay':
            replay(c, state)
        elif state.mode == 'finale':
            if state.legend in ('history', 'recap', 'O01', 'O03'):
                m.history(c)
            else:
                m.finale(c)
        else:
            raise ValueError(f'Unknown visual mode: {state.mode}')
        self.character.draw(c, state.pose)
        c.check_foreground_clearance()
        image = Image.blend(c.image, self.cream, state.cream/255) if state.cream else c.image
        report = {'state': asdict(state), 'components': c.records,
                  'intentional_absences': c.absent, 'scene_data': c.data,
                  'native_layout_tolerance_px': .5,
                  'underlying_layout_passed': all(r['passed'] for r in c.records),
                  'foreground_groups_do_not_overlap': c.data['foreground_groups_do_not_overlap'],
                  'whole_frame_fade': bool(state.cream)}
        return image.convert('RGB'), report


def stage(scene, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    cache, runs, reports = {}, [], []
    lines, end = ['ffconcat version 1.0'], 0
    for state, group in groupby(scene.state(i) for i in range(scene.frame_count)):
        if state not in cache:
            name = f'frame-{len(cache):05d}.png'
            im, report = scene.image(state)
            im.save(folder/name, compress_level=1)
            cache[state] = name
            report.update(file=name, sha256=digest(folder/name))
            reports.append(report)
            if len(cache) % 100 == 0:
                print(json.dumps({'staged_images': len(cache), 'at_frame': end}), flush=True)
        name = cache[state]
        start = end
        end += sum(1 for _ in group)
        microseconds = round(end*1e6/FPS)-round(start*1e6/FPS)
        lines.extend((f"file '{name}'", f'option framerate {FPS}', f'duration {microseconds/1e6:.6f}'))
        runs.append({'start_frame': start, 'end_frame': end, 'frame_count': end-start,
                     'start_s': start/FPS, 'end_s': end/FPS, 'file': name, **asdict(state)})
    if end != scene.frame_count:
        raise ValueError('Incomplete frame coverage')
    lines.extend((f"file '{name}'", f'option framerate {FPS}'))
    index = folder/'frames.ffconcat'
    index.write_text('\n'.join(lines)+'\n', encoding='ascii')
    return index, runs, reports


def encode(index, audio, output, frames, ffmpeg, preset='veryfast', crf=18):
    filters = (f'scale=in_range=full:out_range=limited:out_color_matrix=bt709,'
               f'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,'
               f'fps={FPS},trim=end_frame={frames}')
    command = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-stats', '-stats_period', '10',
               '-nostdin', '-n', '-f', 'concat', '-safe', '0', '-i', str(index), '-i', str(audio),
               '-map', '0:v:0', '-map', '1:a:0', '-vf', filters, '-c:v', 'libx264', '-preset', preset,
               '-crf', str(crf), '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-color_primaries', 'bt709',
               '-color_trc', 'bt709', '-colorspace', 'bt709', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
               '-ac', '2', '-movflags', '+faststart', str(output)]
    with Path(output).with_suffix('.ffmpeg.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    return command


def preview_states():
    states = [Frame('opening', pose='greet'), Frame('seeds', pose='neutral'),
              Frame('rule', pose='present_full'), Frame('count', 0, pose='neutral'),
              Frame('count', 1, pose='neutral'), Frame('replay', 2, pose='think')]
    for n in (2, 8, 13, 18, 20, 21, 26, 31, 39, 40):
        states.extend(Frame('count', n, stage) for stage in ('input-a', 'input-b', 'flow', 'result'))
    for n in CARRY_INDICES:
        states.append(Frame('replay', n, carry_column=-1, carry_stage='align'))
        for col in range(len(carry_steps(*m.VALUES[n-2:n]))):
            states.extend(Frame('replay', n, carry_column=col, carry_stage=phase, carry_tick=tick)
                          for phase, tick in (('compute', 0), ('write', 0), ('move', 0), ('move', 15), ('move', 30)))
        states.append(Frame('replay', n, carry_column=col, carry_stage='complete'))
    states.extend((Frame('replay', 26), Frame('replay', 39),
                   Frame('finale', 40, pose='delighted'),
                   Frame('finale', 40, pose='delighted', legend='history')))
    return states


def layout_qa(scene, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    reports, shots = [], []
    # All fixed arithmetic states and every30fps transfer sample are measured.
    states = list(preview_states())
    states.extend(Frame('count', n, stage) for n in range(2, 41)
                  for stage in ('input-a', 'input-b', 'flow', 'result'))
    states.extend(Frame('count', n, 'transfer', tick) for n in range(2, 40) for tick in range(31))
    seen = set()
    for i, state in enumerate(states):
        if state in seen:
            continue
        seen.add(state)
        image, report = scene.image(state)
        save_image = (state in preview_states() and state.stage == 'result') or (
            state.mode == 'count' and state.n in (8, 20, 21, 39) and state.stage == 'transfer' and state.transfer_tick in (0, 15, 30))
        if save_image:
            name = f'{len(shots)+1:03d}-{state.mode}-F{state.n}-{state.stage}-{state.carry_stage}-{state.carry_column}-{state.transfer_tick}.png'
            image.save(out/name)
            report['reference_image'] = local(out/name)
            if len(shots) < 35:
                shots.append((image, name))
        reports.append(report)
    components = [r for report in reports for r in report['components']]
    summary = {'schema_version': 1, 'kind': 'fibonacci-production-native-layout-qa',
               'status': 'PASS', 'sampled_states': len(reports), 'measured_components': len(components),
               'resolution_px': list(SIZE), 'renderer': local(Path(__file__)),
               'renderer_sha256': digest(Path(__file__)), 'frozen_sources': scene.frozen_sources,
               'tolerance_px': .5, 'max_abs_dx_px': max(abs(r['delta_x_px']) for r in components),
               'max_abs_dy_px': max(abs(r['delta_y_px']) for r in components),
               'all_centered_contained_nonempty': all(r['passed'] for r in components),
               'all_foreground_groups_do_not_overlap': all(r['foreground_groups_do_not_overlap'] for r in reports),
               'scope': 'Native production foreground glyphs/groups, all39fixed arithmetic states and all31sampled positions for38handoffs, carry phases, seeds, history and9digit reading. This does not claim final encoded-pixel or audio QA.',
               'states': reports, 'character_poses': scene.character.receipts}
    save_new(out/'layout-verification.json', summary)
    cols, cellw, cellh = 3, 640, 390
    sheet = Image.new('RGB', (1920, math.ceil(len(shots)/cols)*cellh), m.CREAM)
    draw = ImageDraw.Draw(sheet)
    for i, (image, name) in enumerate(shots):
        x, y = i % cols*cellw, i//cols*cellh
        sheet.paste(image.resize((624, 351), Image.Resampling.LANCZOS), (x+8, y+8))
        draw.text((x+10, y+365), name[:64], font=m.font(15), fill=m.INK, anchor='lt')
    sheet.save(out/'production-layout-contact.jpg', quality=92)
    return summary


def smoke_plan():
    """One short representative contract for layout and motion testing only."""
    counted = []
    for n, value in enumerate(m.VALUES):
        counted.append({'index': n, 'n': n, 'value': value,
                        'a': m.VALUES[n-2] if n >= 2 else None,
                        'b': m.VALUES[n-1] if n >= 2 else None,
                        'display_start_s': n*5+.88, 'voice_start_s': n*5+1,
                        'voice_end_s': n*5+2,
                        'formula_start_s': n*5 if n >= 2 else None,
                        'formula_end_s': n*5+.84 if n >= 2 else None,
                        'transfer_start_s': n*5+2.35, 'transfer_end_s': n*5+3.55})
    return {'fps': 30, 'width': 1920, 'height': 1080, 'duration_s': 205,
            'duration_frames': 6150, 'counted_states': counted, 'voice_events': [],
            'visual_segments': [{'mode': 'count', 'index': n, 'start_s': n*5, 'end_s': (n+1)*5,
                                 'params': {'stage': 'input-a'}} for n in range(41)]}


def motion_samples(scene, out, ffmpeg):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    frames = []
    for n in (6, 7, 8):
        for i in range(120):
            t = i/30
            if t < .45:
                state = Frame('count', n, 'input-a')
            elif t < .9:
                state = Frame('count', n, 'input-b')
            elif t < 1.3:
                state = Frame('count', n, 'flow')
            elif t < 2.25:
                state = Frame('count', n, 'result')
            elif t < 3.45:
                state = Frame('count', n, 'transfer', round(smooth((t-2.25)/1.2)*30))
            else:
                state = Frame('count', n+1, 'input-a')
            frames.append(state)
    for n in CARRY_INDICES:
        for i in range(240):
            column, phase, tick = scene.carry_state(n, i/30, 0, 8)
            frames.append(Frame('replay', n, carry_column=column, carry_stage=phase, carry_tick=tick,
                                pose='present_half'))
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-f', 'rawvideo',
               '-pix_fmt', 'rgb24', '-s', '1920x1080', '-r', '30', '-i', '-', '-an',
               '-vf', 'scale=in_range=full:out_range=limited:out_color_matrix=bt709',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p',
               '-color_range', 'tv', '-color_primaries', 'bt709', '-color_trc', 'bt709',
               '-colorspace', 'bt709', '-movflags', '+faststart', str(out/'arithmetic-motion-sample.mp4')]
    @lru_cache(maxsize=16)
    def sample_pixels(state):
        image, _ = scene.image(state)
        return image.tobytes()
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for state in frames:
            process.stdin.write(sample_pixels(state))
        process.stdin.close()
        if process.wait():
            raise RuntimeError('Motion sample encoding failed')
    finally:
        if process.poll() is None:
            process.kill()
    save_new(out/'sample-record.json', {'scope': 'Silent arithmetic motion study; not final narration or production timing',
                                       'frames': len(frames), 'fps': 30, 'duration_s': len(frames)/30,
                                       'counts': [6, 7, 8], 'carry_replays': list(CARRY_INDICES),
                                       'sha256': digest(out/'arithmetic-motion-sample.mp4')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, default=ROOT/'output/fibonacci-counting-001-v001/timeline.json')
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe') or str(ROOT/'.venv/bin/ffprobe'))
    parser.add_argument('--preset', default='veryfast')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--work-dir', type=Path, help='A new frame staging directory; never replaces an earlier attempt.')
    parser.add_argument('--stage-only', action='store_true')
    parser.add_argument('--layout-only', action='store_true')
    parser.add_argument('--motion-samples', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.timeline.read_text()) if args.timeline.exists() else smoke_plan()
    if not args.timeline.exists() and not args.layout_only:
        raise FileNotFoundError('A measured accepted timeline is required for production')
    out = (args.out_dir or args.timeline.parent).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scene = Scene(plan)
    start = time.perf_counter()
    if args.layout_only:
        report = layout_qa(scene, out/'native-layout-qa')
        if args.motion_samples:
            motion_samples(scene, out/'motion-samples', args.ffmpeg)
        print(json.dumps({k: report[k] for k in ('status', 'sampled_states', 'measured_components', 'max_abs_dx_px', 'max_abs_dy_px')}), flush=True)
        return
    destination = out/VIDEO_NAME
    for file in (destination, out/'frame-plan.json', out/'render-record.json'):
        if file.exists():
            raise FileExistsError(file)
    audio_record = plan.get('master_audio')
    if not args.stage_only:
        for name in ('speech_manifest', 'speech_acceptance'):
            receipt = plan.get(name)
            if not receipt:
                raise ValueError(f'Timeline has no bound {name} receipt')
            source = Path(receipt['path'])
            source = source if source.is_absolute() else ROOT/source
            if digest(source) != receipt['sha256']:
                raise ValueError(f'Accepted speech receipt changed: {name}')
        if not audio_record:
            raise ValueError('Measured timeline has no accepted master audio')
        audio = Path(audio_record['path'])
        audio = audio if audio.is_absolute() else ROOT/audio
        if digest(audio) != audio_record['sha256']:
            raise ValueError('Accepted audio master hash mismatch')
    work = args.work_dir.resolve() if args.work_dir else out/'.work/frames-v001'
    index, runs, reports = stage(scene, work)
    save_new(out/'frame-plan.json', {'schema_version': 1, 'fps': FPS,
                                   'duration_frames': scene.frame_count, 'timeline_sha256': digest(args.timeline),
                                   'image_directory': local(work), 'runs': runs, 'images': reports,
                                   'distinct_images': len(reports),
                                   'arithmetic_policy': 'Reveal result and reading together atN-.12; handoff copies b,c to next inputs; carry replays compute/write/move each column from ones leftward.'})
    command = None
    if not args.stage_only:
        command = encode(index, audio, destination, scene.frame_count, args.ffmpeg, args.preset, args.crf)
    record = {'schema_version': 1, 'kind': 'fibonacci-production-video-render',
              'stage_only': args.stage_only, 'timeline': local(args.timeline),
              'timeline_sha256': digest(args.timeline), 'renderer': local(Path(__file__)),
              'renderer_sha256': digest(Path(__file__)), 'mockup_adapter_sha256': digest(Path(m.__file__)),
              'frame_plan': local(out/'frame-plan.json'), 'frame_plan_sha256': digest(out/'frame-plan.json'),
              'frames': scene.frame_count, 'duration_s': scene.frame_count/FPS,
              'distinct_images': len(reports), 'holds': len(runs),
              'native_layout_checks_passed': all(r['underlying_layout_passed'] for r in reports),
              'foreground_clearance_passed': all(r['foreground_groups_do_not_overlap'] for r in reports),
              'source_character': {'id': 'siamese-cat', 'source_snapshot': local(DESIGN/'character-selection.json'),
                                   'poses': scene.character.receipts},
              'sources': scene.frozen_sources,
              'encode_command': command, 'elapsed_s': time.perf_counter()-start,
              'output': local(destination) if destination.exists() else None,
              'output_sha256': digest(destination) if destination.exists() else None}
    if destination.exists():
        record['probe'] = json.loads(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(destination)], text=True))
    save_new(out/'render-record.json', record)
    print(json.dumps({'output': str(destination), 'frames': scene.frame_count,
                      'distinct_images': len(reports), 'native_layout_passed': record['native_layout_checks_passed'],
                      'elapsed_s': record['elapsed_s']}), flush=True)


if __name__ == '__main__':
    main()
