"""Render Fibonacci preproduction stills and a silent arithmetic motion study.

Exact integers, glyphs, and mathematical diagrams are code-drawn over a generated
clean plate. This is not the production video or an audio/synchronization review.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/fibonacci-counting-v1'
OUT = DESIGN / 'mockups'
QA = DESIGN / 'qa'
BG = ROOT / 'assets/library/worlds/cloud-post-office/backgrounds/v001/cloud-post-office-background.png'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
CAT = ROOT / 'assets/library/characters/siamese-cat/motions/fibonacci-v001/registration.json'
SIZE = (1920, 1080)
INK = '#284455'
TEAL = '#287d82'
BLUE = '#477aa2'
RUST = '#b55e46'
MUTED = '#667b86'
CREAM = '#fffaf0'
PALE = '#e8f2ed'
PEACH = '#f7e5d5'
VALUES = [0, 1]
for _ in range(39):
    VALUES.append(VALUES[-2] + VALUES[-1])


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def words(n):
    ones = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
    if n < 20:
        return ones[n]
    if n < 100:
        return tens[n // 10] + ('-' + ones[n % 10] if n % 10 else '')
    if n < 1000:
        return ones[n // 100] + ' hundred' + (' ' + words(n % 100) if n % 100 else '')
    for divisor, unit in ((1_000_000, 'million'), (1000, 'thousand')):
        if n >= divisor:
            return words(n // divisor) + ' ' + unit + (' ' + words(n % divisor) if n % divisor else '')
    raise ValueError(n)


@lru_cache(maxsize=60)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def text_layer(text, size, color):
    f = font(size)
    b = f.getbbox(text)
    im = Image.new('RGBA', (b[2] - b[0] + 40, b[3] - b[1] + 40))
    ImageDraw.Draw(im).text((20 - b[0], 20 - b[1]), text, font=f, fill=color)
    return im


def visible(im, threshold=128):
    return im.getchannel('A').point(lambda a: 255 if a >= threshold else 0).getbbox()


def split_reading(text, width=1220, size=32):
    # Two lines maximum, one common size; choose the most balanced word boundary.
    if font(size).getlength(text) <= width:
        return [text]
    tokens = text.split()
    options = [(max(font(size).getlength(' '.join(tokens[:i])), font(size).getlength(' '.join(tokens[i:]))), i)
               for i in range(1, len(tokens))]
    best, index = min(options)
    if best > width:
        raise ValueError(f'Reading cannot fit at the fixed font size: {text}')
    return [' '.join(tokens[:index]), ' '.join(tokens[index:])]


class Canvas:
    def __init__(self, plate, scene):
        self.image = plate.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.scene = scene
        self.records = []
        self.absent = []
        self.data = {}

    def center_layer(self, layer, field, ident, opacity=1):
        if not opacity:
            self.absent.append({'id': ident, 'reason': 'intentionally absent in this animation state'})
            return
        if opacity != 1:
            layer = layer.copy()
            layer.putalpha(layer.getchannel('A').point(lambda a: round(a * opacity)))
        threshold = max(1, round(128 * opacity))
        b = visible(layer, threshold)
        if b is None:
            raise ValueError(f'Empty target: {ident}')
        xy = (round((field[0] + field[2] - b[0] - b[2]) / 2),
              round((field[1] + field[3] - b[1] - b[3]) / 2))
        report = raster_centering_report(layer, field, origin_xy=xy,
                                         name=f'{self.scene}/{ident}', tolerance_px=.5,
                                         alpha_threshold=threshold)
        report.update(scene=self.scene, resolution_px=list(SIZE), horizontal='center',
                      vertical='center', opacity=opacity)
        if not report['passed']:
            raise ValueError(report)
        self.records.append(report)
        self.image.alpha_composite(layer, xy)

    def text(self, text, field, size, color=INK, ident=None, opacity=1):
        self.center_layer(text_layer(text, size, color), field, ident or text, opacity)
        if opacity:
            self.records[-1].update(text=text, font_size_px=size)

    def multiline(self, lines, field, size, color=INK, ident='multiline', opacity=1):
        # Measure the whole multiline group, not each baseline or line-height box.
        pieces = [text_layer(line, size, color) for line in lines]
        boxes = [visible(p) for p in pieces]
        width = max(b[2] - b[0] for b in boxes)
        height = sum(b[3] - b[1] for b in boxes) + (len(lines) - 1) * 14
        layer = Image.new('RGBA', (width + 40, height + 40))
        y = 20
        for piece, b in zip(pieces, boxes):
            layer.alpha_composite(piece, (round((width - b[2] + b[0]) / 2) + 20 - b[0], y - b[1]))
            y += b[3] - b[1] + 14
        self.center_layer(layer, field, ident, opacity)
        if opacity:
            self.records[-1].update(text='\n'.join(lines), font_size_px=size)

    def dots(self, colors, field, columns=None, ident='dots'):
        columns = columns or len(colors)
        rows = math.ceil(len(colors) / columns)
        diameter, step = 34, 51
        layer = Image.new('RGBA', ((columns-1)*step+diameter+40, (rows-1)*step+diameter+40))
        draw = ImageDraw.Draw(layer)
        for i, color in enumerate(colors):
            x, y = 20+(i % columns)*step, 20+(i // columns)*step
            draw.ellipse((x, y, x+diameter-1, y+diameter-1), fill=color)
        self.center_layer(layer, field, ident)
        self.data.setdefault('dot_groups', []).append({'id': ident, 'quantity': len(colors), 'colors': colors})

    def left(self, text, xy, size, color=INK):
        # These captions intentionally align left, not to the surrounding center.
        self.draw.text(xy, text, font=font(size), fill=color, anchor='lt')

    def panel(self, bounds, fill=CREAM, outline='#bed0d0', radius=26, width=2):
        self.draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=width)

    def check_foreground_clearance(self):
        # Distinct foreground groups must remain legible throughout the handoff.
        # Parent windows, connecting paths, ground shadows and background are
        # deliberately not targets; a label inside its own window is expected.
        for i, a in enumerate(self.records):
            x1, y1, x2, y2 = a['visible_box_xyxy']
            for b in self.records[i+1:]:
                u1, v1, u2, v2 = b['visible_box_xyxy']
                if max(x1, u1) < min(x2, u2) and max(y1, v1) < min(y2, v2):
                    raise ValueError(f'Foreground groups collide: {a["name"]} / {b["name"]}')
        self.data['foreground_groups_do_not_overlap'] = True


class Siamese:
    def __init__(self):
        # Preserve this proposal's adopted originals even when another production
        # later updates the shared library's current pose selection.
        selection = json.loads((DESIGN / 'character-selection.json').read_text())
        self.character = selection['adopted_character']
        if self.character['id'] != 'siamese-cat':
            raise ValueError('This proposal uses the user-selected Siamese cat')
        self.new = json.loads(CAT.read_text())
        self.height = 400
        self.foot = (1655, 990)
        self.receipts = {}

    @lru_cache(maxsize=16)
    def sprite(self, pose):
        if pose == 'neutral':
            row = self.character['neutral']
            height = row['reference_height_px']
        elif pose in self.character['key_poses']['poses']:
            row = self.character['key_poses']['poses'][pose]
            height = self.character['key_poses']['common_reference_height_px']
        else:
            row = next(x for x in self.new['frames'] if x['id'] == pose)
            height = self.new['common_reference_height_px']
        path = ROOT / row['path']
        if sha(path) != row['sha256']:
            raise ValueError(f'Character hash mismatch: {path}')
        image = Image.open(path).convert('RGBA')
        scale = self.height / height
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
        xy = tuple(round(a - b * scale) for a, b in zip(self.foot, row['anchor_px']))
        b = visible(image, 8)
        bounds = [b[0] + xy[0], b[1] + xy[1], b[2] + xy[0], b[3] + xy[1]]
        if not (bounds[0] >= 1410 and bounds[2] <= 1885 and bounds[1] >= 540 and bounds[3] <= 1020):
            raise ValueError(f'Character cropped or colliding with equation: {pose}: {bounds}')
        self.receipts[pose] = {'pose': pose, 'path': row['path'], 'sha256': sha(path),
                               'body_height_px': self.height, 'source_scale': scale,
                               'foot_anchor_px': list(self.foot), 'visible_box_xyxy': bounds,
                               'source_pixels_modified': False, 'mirrored': False,
                               'placement_intent': 'anatomical foot support; not frame centering'}
        return image, xy

    def draw(self, c, pose='neutral'):
        shadow = Image.new('RGBA', SIZE)
        ImageDraw.Draw(shadow).ellipse((1530, 977, 1815, 1007), fill=(74, 88, 89, 22))
        c.image.alpha_composite(shadow)
        image, xy = self.sprite(pose)
        c.image.alpha_composite(image, xy)


def header(c, subtitle='THE CLOUD POST OFFICE'):
    c.left('FIBONACCI', (100, 75), 76)
    c.left(subtitle, (106, 174), 26, TEAL)
    c.text('Num-Num Numbers', (1450, 74, 1870, 130), 30, INK, 'series')


def recurrence_layer(size=48):
    # True subscript layout, independent of Unicode subscript font coverage.
    items = [('F', False), ('n', True), (' = ', False), ('F', False), ('n−2', True),
             (' + ', False), ('F', False), ('n−1', True)]
    widths = [font(round(size * .57) if sub else size).getlength(text) for text, sub in items]
    im = Image.new('RGBA', (math.ceil(sum(widths)) + 60, round(size * 1.8) + 40))
    d = ImageDraw.Draw(im)
    x = 30
    for (text, sub), width in zip(items, widths):
        d.text((x, 20 + size * (.51 if sub else 0)), text,
               font=font(round(size * .57) if sub else size), fill=INK, anchor='lt')
        x += width
    return im


def rule(c):
    c.center_layer(recurrence_layer(47), (130, 220, 1300, 286), 'recurrence')


FIELDS = [(118, 366, 430, 468), (558, 366, 870, 468), (998, 366, 1310, 468)]
CENTERS = [274, 714, 1154]


def equation(c, n, stage='result', transfer=0, fade=1, show_reading=True):
    a, b, expected = VALUES[n-2:n+1]
    result = a + b
    if result != expected:
        raise ValueError(f'Generated result differs from the sequence at F{n}')
    size = 88 if n <= 20 else 47
    c.data.update(index=n, ordinal=n + 1, operands=[a, b], result=result, equation=f'{a} + {b} = {result}',
                  stage=stage, transfer_progress=transfer, equation_font_px=size)
    rule(c)
    for i, (value, idx, color) in enumerate(((a, n-2, BLUE), (b, n-1, TEAL), (result, n, RUST))):
        x = CENTERS[i]
        c.panel((x-176, 340, x+176, 494), PALE if i != 2 else PEACH,
                color if stage == ('input-a' if i == 0 else 'input-b' if i == 1 else 'result') else '#b9cecf', radius=29, width=3)
        if stage != 'transfer':
            role = ('OLDER', 'NEWER', 'NEW')[i]
            c.text(f'{role} · F{idx}', (x-163, 301, x+163, 332), 23, color, f'index-{i}')
        hidden = stage == 'transfer' and i in (0, 1, 2)
        if hidden:
            c.absent.append({'id': f'operand-{i}', 'reason': 'moving on a registered transfer path'})
        elif i == 2 and stage in ('input-a', 'input-b', 'flow'):
            c.text('?', FIELDS[i], 70, color, 'unknown-result')
        else:
            c.text(f'{value:,}', FIELDS[i], size, color, f'operand-{i}', opacity=fade if i == 2 else 1)
    if stage != 'transfer':
        c.text('+', (454, 367, 534, 466), 62, TEAL, 'plus')
        c.text('=', (894, 367, 974, 466), 62, RUST, 'equals')
    else:
        c.absent.append({'id': 'operators', 'reason': 'memory handoff is not an active addition'})
    if stage == 'flow':
        # A traced path conveys a computation, never a quantity of objects.
        c.draw.line((274, 511, 274, 548, 1154, 548, 1154, 511), fill='#96b8bf', width=4)
        c.draw.line((714, 511, 714, 532, 1154, 532), fill=TEAL, width=4)
        c.draw.polygon([(1146, 519), (1162, 519), (1154, 507)], fill=RUST)
        c.text('ADD THE LAST TWO', (200, 564, 1240, 610), 28, MUTED, 'process-caption')
    if stage == 'transfer':
        # The old right input is kept; the output is copied into the next pair.
        # Every moving label is centered inside its own moving destination box.
        t = transfer
        for i, value in enumerate((b, result)):
            x0, x1 = (714, 274) if i == 0 else (1154, 714)
            x = x0 + (x1-x0) * t
            y = 417 + 135 * math.sin(math.pi * t)
            c.panel((round(x-176), round(y-77), round(x+176), round(y+77)), PALE, TEAL, radius=29)
            c.text(f'{value:,}', (x-156, y-51, x+156, y+51), size, BLUE if i == 0 else TEAL, f'transferred-{i}')
            c.text(f'F{n-1+i}', (x-90, y-118, x+90, y-86), 23, TEAL, f'transferred-index-{i}')
    if stage in ('result', 'transfer'):
        c.text('NEW NUMBER', (140, 575 if stage == 'result' else 645, 1320, 615 if stage == 'result' else 679), 25, RUST, 'new-label')
        c.text(f'{result:,}', (118, 640 if stage == 'result' else 690, 1310, 794 if stage == 'result' else 815), 126 if n <= 20 else 112, INK, 'main-result', opacity=fade)
        if show_reading:
            c.multiline(split_reading(words(result)), (105, 825, 1335, 929), 32, TEAL, 'result-reading', opacity=fade)
    else:
        c.text('The next number is on its way.', (130, 680, 1310, 770), 40, MUTED, 'pending-result')
    progress = f'TERM {n+1} OF 41  ·  INDEX n = {n}'
    c.text('KEEP THE LAST TWO. GO AGAIN.' if stage == 'transfer' else progress if stage == 'result' else 'NEXT: ' + progress,
           (130, 968, 1310, 1016), 25, MUTED, 'transfer-caption' if stage == 'transfer' else 'term-progress')


def opening(c):
    c.left('Watch the next', (105, 305), 76)
    c.left('number take shape.', (105, 414), 76)
    c.left('Two numbers in. A new number out.', (110, 548), 35, TEAL)
    for x, value, color in ((270, '0', BLUE), (660, '1', TEAL), (1050, '1', RUST)):
        c.panel((x-136, 674, x+136, 866), PALE if color != RUST else PEACH, color)
        c.text(value, (x-115, 698, x+115, 846), 112, color, f'opening-{x}')
    c.text('+', (437, 730, 493, 810), 54, TEAL, 'opening-plus')
    c.text('=', (827, 730, 883, 810), 54, RUST, 'opening-equals')
    c.text('START WITH 0 AND 1  ·  FOLLOW THE LAST TWO', (100, 944, 1350, 1004), 30, MUTED, 'opening-range')


def seeds(c):
    c.text('START WITH TWO SEEDS', (95, 280, 1350, 352), 48, TEAL, 'seed-heading')
    for x, value, term, color in ((430, '0', 'F0 · FIRST TERM', BLUE), (1030, '1', 'F1 · SECOND TERM', TEAL)):
        c.panel((x-235, 415, x+235, 755), PALE, color, width=3)
        c.text(value, (x-200, 450, x+200, 661), 200, color, f'seed-value-{value}')
        c.text(term, (x-205, 687, x+205, 733), 27, color, f'seed-term-{value}')
    c.multiline(['Zero and one start the sequence.', 'Every later term comes from addition.'], (120, 821, 1320, 948), 36, INK, 'seed-explanation')


def repeated_one(c):
    equation(c, 2, show_reading=False)
    c.text('REPLAY', (1010, 522, 1320, 566), 24, RUST, 'replay-label')
    c.panel((120, 814, 1320, 943), CREAM, '#d8cbb8')
    c.multiline(['F1 = 1  and  F2 = 1', 'Same value. Two different terms.'], (155, 831, 1285, 926), 35, TEAL, 'repeated-one-explanation')


def general_rule(c):
    c.text('THE RULE THAT KEEPS WORKING', (100, 280, 1340, 345), 43, TEAL, 'rule-heading')
    c.center_layer(recurrence_layer(92), (105, 410, 1335, 565), 'large-recurrence')
    c.text('n ≥ 2', (340, 590, 1100, 650), 43, MUTED, 'rule-domain')
    c.multiline(['Add the two terms just before this one.', 'Then keep the newer pair and repeat.'], (105, 733, 1335, 875), 38, INK, 'rule-explanation')
    c.text('F0 = 0    ·    F1 = 1', (100, 946, 1340, 1004), 37, TEAL, 'rule-initials')


def carry(c, phase='complete'):
    c.text('THE SAME RULE, WITH A CARRY', (100, 272, 1350, 337), 43, TEAL, 'carry-heading')
    c.text('REPLAY · F11 + F12 = F13', (810, 349, 1355, 392), 25, MUTED, 'carry-replay')
    c.panel((145, 386, 780, 941), CREAM, '#bed0d0')
    centers = [380, 510, 640]
    completed = {'ones': 1, 'tens': 2, 'complete': 3}[phase]
    for i in ((1,) if phase == 'ones' else (0, 1)):
        c.text('1', (centers[i]-38, 412, centers[i]+38, 463), 39, RUST, f'carry-{i}')
    for row, number, y, color in ((0, ' 89', 482, BLUE), (1, '144', 621, TEAL), (2, '233', 801, RUST)):
        for col, char in enumerate(number):
            if char != ' ':
                if row == 2 and col < 3-completed:
                    char = '?'
                c.text(char, (centers[col]-49, y, centers[col]+49, y+104), 97, color, f'column-{row}-{col}')
    c.text('+', (206, 621, 296, 725), 67, TEAL, 'column-plus')
    c.draw.line((216, 769, 711, 769), fill=INK, width=4)
    detail = {'ones': ('9 + 4 = 13', ['Write 3 ones.', 'Carry 1 ten.']),
              'tens': ('8 + 4 + 1 = 13', ['Write 3 tens.', 'Carry 1 hundred.']),
              'complete': ('0 + 1 + 1 = 2', ['2 hundreds, 3 tens,', 'and 3 ones.'])}[phase]
    c.text(detail[0], (827, 425, 1340, 492), 38, RUST, 'carry-current-step')
    c.multiline(detail[1], (823, 522, 1345, 665), 34, INK, 'carry-step-detail')
    c.text('89 + 144 = 233' if phase == 'complete' else 'Work from right to left.',
           (815, 730, 1360, 808), 39 if phase == 'complete' else 31, TEAL, 'carry-equation-or-direction')
    c.text(f'STEP {completed} OF 3', (823, 839, 1345, 896), 28, MUTED, 'carry-step-number')
    c.data.update(index=13, operands=[89, 144], result=233, carry_phase=phase,
                  completed_columns_from_right=completed, carries_to_columns=[1, 1, 0] if completed > 1 else [0, 1, 0])


def quantity(c):
    c.text('SEE THE ADDITION', (100, 278, 1350, 344), 47, TEAL, 'quantity-heading')
    for x, value, idx, color in ((400, 3, 4, BLUE), (1030, 5, 5, TEAL)):
        c.text(f'F{idx}', (x-120, 368, x+120, 409), 25, color, f'dot-index-{value}')
        c.text(str(value), (x-120, 419, x+120, 515), 91, color, f'dot-value-{value}')
        c.dots([color]*value, (x-220, 541, x+220, 613), ident=f'source-{value}')
    c.text('+', (668, 453, 762, 568), 67, TEAL, 'dot-plus')
    c.draw.line((400, 645, 400, 673, 715, 673, 715, 707), fill=BLUE, width=4)
    c.draw.line((1030, 645, 1030, 673, 715, 673), fill=TEAL, width=4)
    c.text('8', (510, 711, 920, 823), 104, RUST, 'dot-result-value')
    c.dots([BLUE]*3+[TEAL]*5, (400, 849, 1030, 947), columns=4, ident='combined-eight')
    c.text('F6 · eight', (130, 981, 1310, 1020), 27, TEAL, 'dot-result-reading')
    c.data.update(index=6, operands=[3, 5], result=8, diagram_kind='exact discrete quantities; one dot per unit')


def history(c):
    c.text('TWO SEEDS. 39 ADDITIONS. 41 TERMS.', (95, 272, 1355, 341), 39, TEAL, 'history-heading')
    for n, value in enumerate(VALUES):
        x, y = 108+(n % 6)*207, 376+(n // 6)*78
        color = BLUE if n < 2 else RUST if n == 40 else TEAL
        c.panel((x, y, x+190, y+65), PEACH if n == 40 else CREAM, '#b9cecf', radius=10, width=1)
        c.text(f'F{n}', (x+10, y+7, x+180, y+26), 15, color, f'history-index-{n}')
        c.text(f'{value:,}', (x+8, y+32, x+182, y+59), 22, color, f'history-value-{n}')
    c.text('The two 1s stay. Every term has its own place.', (100, 976, 1350, 1021), 27, MUTED, 'history-duplicate-rule')
    c.data.update(history_values=VALUES, history_indices=list(range(41)), equal_spacing_means='sequence order, not proportional value')


def finale(c):
    c.text('ONE SIMPLE RULE. 41 TERMS.', (100, 278, 1350, 351), 47, TEAL, 'finale-heading')
    c.text('102,334,155', (103, 426, 1348, 594), 124, INK, 'final-value')
    c.text('F40  ·  THE FIRST TERM ABOVE 100 MILLION', (100, 653, 1350, 711), 29, RUST, 'final-threshold')
    c.center_layer(recurrence_layer(53), (130, 781, 1320, 871), 'final-recurrence')
    c.text('The sequence can keep going.', (110, 945, 1340, 1008), 39, TEAL, 'final-infinite')


def build(plate, character, name, mode='count', n=8, stage='result', transfer=0, fade=1):
    c = Canvas(plate, name)
    header(c)
    pose = 'present_full' if mode == 'count' and stage == 'result' else 'watch_left'
    if mode == 'opening':
        pose = 'greet'
        opening(c)
    elif mode == 'seeds':
        pose = 'neutral'
        seeds(c)
    elif mode == 'one':
        pose = 'think'
        repeated_one(c)
    elif mode == 'rule':
        pose = 'present_full'
        general_rule(c)
    elif mode == 'carry':
        pose = 'present_half'
        carry(c)
    elif mode == 'quantity':
        pose = 'watch_left'
        quantity(c)
    elif mode == 'history':
        pose = 'delighted'
        history(c)
    elif mode == 'finale':
        pose = 'delighted'
        finale(c)
    else:
        if mode == 'pending':
            stage = 'flow'
            pose = 'watch_left'
        if stage == 'flow':
            pose = 'present_half'
        equation(c, n, stage, transfer, fade)
    character.draw(c, pose)
    c.check_foreground_clearance()
    return c


def save(c, filename):
    path = OUT / filename
    c.image.convert('RGB').save(path)
    return {'filename': filename, 'sha256': sha(path), 'scene_data': c.data,
            'components': c.records, 'intentional_absences': c.absent}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    plate = ImageOps.fit(Image.open(BG).convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
    character = Siamese()
    longest = max(range(41), key=lambda n: font(32).getlength(words(VALUES[n])))
    shots = [
        ('01-opening.png', 'opening', 0, '01  Welcome · a number takes shape'),
        ('02-seeds.png', 'seeds', 0, '02  Two seeds · zero and one'),
        ('03-two-ones.png', 'one', 2, '03  The repeated one is a different term'),
        ('03b-three-plus-five.png', 'quantity', 6, '04  Three and five · eight exact dots'),
        ('04-rule.png', 'rule', 2, '05  The recurrence · with real subscripts'),
        ('05-add-and-generate.png', 'count', 8, '06  8 + 13 generates 21'),
        ('06-place-value-carry.png', 'carry', 13, '07  Carry complete · 89 + 144 = 233'),
        ('07-four-digits.png', 'count', 17, '08  A new place · 610 + 987 = 1,597'),
        ('08-first-million.png', 'count', 31, '09  Into the millions · same rule'),
        ('09-final-inputs.png', 'pending', 40, '10  Final inputs · result not revealed yet'),
        ('10-final-addition.png', 'count', 40, '11  First result above 100 million'),
        ('11-finale.png', 'finale', 40, '12  41 terms · the rule continues'),
        ('12-all-41-terms.png', 'history', 40, '13  All 41 terms · both ones stay'),
    ]
    reports = []
    sheet_frames = []
    for filename, mode, n, caption in shots:
        c = build(plate, character, filename, mode, n)
        reports.append(save(c, filename))
        sheet_frames.append((c.image.copy(), caption))
    c = build(plate, character, 'longest-reading-validation', 'count', longest)
    reports.append(save(c, '09-longest-reading.png'))
    for phase in ('ones', 'tens', 'complete'):
        c = Canvas(plate, f'carry/{phase}')
        header(c)
        carry(c, phase)
        character.draw(c, 'present_half')
        c.check_foreground_clearance()
        reports.append(save(c, f'carry-{phase}.png'))
    # Every term at its actual layout mode, including all 1/2/3/4/5/6/7/8/9-digit transitions.
    all_terms = []
    for n in range(2, 41):
        for stage in ('input-a', 'input-b', 'flow', 'result'):
            c = build(plate, character, f'all-terms/F{n}/{stage}', 'count', n, stage)
            all_terms.append({'index': n, 'value': VALUES[n], 'stage': stage, 'components': c.records})
    # Transfer samples include the biggest figures and the display-mode boundary.
    transitions = []
    for n in (2, 6, 7, 8, 16, 17, 20, 21, 30, 31, 35, 39):
        for t in (0, .5, 1):
            c = build(plate, character, f'transfer/F{n}/{t}', 'count', n, 'transfer', t)
            transitions.append({'index': n, 'progress': t, 'components': c.records})
            if n == 8:
                reports.append(save(c, f'transfer-{round(t*100):03d}.png'))
        for opacity in (0, .5, 1):
            c = build(plate, character, f'reveal/F{n}/{opacity}', 'count', n, 'result', fade=opacity)
            transitions.append({'index': n, 'reveal_opacity': opacity, 'components': c.records,
                                'intentional_absences': c.absent})
    # Silent 12-second concept loop: three complete arithmetic-and-handoff cycles.
    frames = []
    animation_reports = []
    for n in (6, 7, 8):
        for k in range(40):
            t = k / 10
            if t < .5:
                stage, transfer = 'input-a', 0
            elif t < 1:
                stage, transfer = 'input-b', 0
            elif t < 1.5:
                stage, transfer = 'flow', 0
            elif t < 2.6:
                stage, transfer = 'result', 0
            elif t < 3.6:
                stage, transfer = 'transfer', (t-2.6)
            else:
                # Hold the next input pair, without revealing its answer early.
                c = build(plate, character, f'animation/F{n}/{k}', 'count', n+1, 'input-a')
                frames.append(c.image.convert('RGB').resize((960, 540), Image.Resampling.LANCZOS))
                animation_reports.append({'index': n, 'frame': k, 'stage': 'next-pair', 'components': c.records})
                continue
            c = build(plate, character, f'animation/F{n}/{k}', 'count', n, stage, transfer)
            frames.append(c.image.convert('RGB').resize((960, 540), Image.Resampling.LANCZOS))
            animation_reports.append({'index': n, 'frame': k, 'stage': stage, 'components': c.records})
    frames[0].save(OUT / 'formula-relay-preview.gif', save_all=True, append_images=frames[1:],
                   duration=100, loop=0, disposal=2, optimize=False)
    with Image.open(OUT / 'formula-relay-preview.gif') as gif:
        gif_frames = gif.n_frames
        gif_duration_ms = 0
        for frame in range(gif_frames):
            gif.seek(frame)
            gif_duration_ms += gif.info['duration']
    # Contact sheet and compact 4-scene review.
    cellw, cellh = 960, 594
    sheet = Image.new('RGB', (cellw * 2, math.ceil(len(sheet_frames) / 2) * cellh), '#f9f0e5')
    d = ImageDraw.Draw(sheet)
    for i, (im, caption) in enumerate(sheet_frames):
        x, y = (i % 2) * cellw, (i // 2) * cellh
        sheet.paste(im.convert('RGB').resize((944, 531), Image.Resampling.LANCZOS), (x+8, y+8))
        d.text((x+20, y+558), caption, font=font(21), fill=INK, anchor='lt')
    sheet.save(OUT / 'storyboard.png')
    sheet.resize((1152, round(sheet.height * .6)), Image.Resampling.LANCZOS).save(OUT / 'storyboard-preview.jpg', quality=94)
    overview = Image.new('RGB', (1440, 810), CREAM)
    for j, i in enumerate((0, 5, 6, 10)):
        im = sheet_frames[i][0].convert('RGB').resize((720, 405), Image.Resampling.LANCZOS)
        overview.paste(im, ((j % 2)*720, (j//2)*405))
    overview.save(OUT / 'overview.jpg', quality=95)
    sheet_frames[5][0].convert('RGB').save(OUT / 'key-visual.png')
    component_reports = [r for s in reports for r in s['components']]
    component_reports += [r for s in all_terms + transitions + animation_reports for r in s['components']]
    data = {'schema_version': 1, 'kind': 'fibonacci-preproduction-mockups', 'status': 'draft-for-user-review',
            'video_created': False, 'audio_created': False,
            'scope': 'Static1920x1080 PNGs, exact arithmetic, all fixed states, transfer/reveal samples and silent960x54012s GIF. No production video, TTS, continuous performance or final AAC verification.',
            'resolution_px': list(SIZE), 'fibonacci_values': VALUES, 'indices': [0, 40], 'counted_terms': 41,
            'recurrence': 'F0=0;F1=1;Fn=F(n-2)+F(n-1), n>=2',
            'longest_unwrapped_reading_index': longest, 'reading_font_px': 32,
            'reading_policy': 'one fixed32px size; at most two lines; whole multiline group centered',
            'equation_font_policy': 'F2..F20:88px; planned wide-number mode F21..F40:47px; no per-value fitting',
            'animation': {'sampled_frames': len(frames), 'sampling_fps': 10,
                          'encoded_gif_frames': gif_frames, 'duration_ms': gif_duration_ms,
                          'encoding_note': 'Identical hold frames are losslessly coalesced into longer GIF durations.'},
            'character': {'id': 'siamese-cat', 'body_height_px': 400, 'foot_anchor_px': list(character.foot),
                          'registration_path': str(CAT.relative_to(ROOT)), 'poses': character.receipts},
            'sources': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in (BG, FONT, CAT, DESIGN/'character-selection.json')],
            'shots': reports, 'all_terms': all_terms, 'transitions': transitions, 'animation_frames': animation_reports,
            'alignment': {'measurement': 'actual alpha>=128 glyph/component raster, excluding parent frames, shadows and backdrop; threshold proportional for fades',
                          'tolerance_px': .5, 'measured_components': len(component_reports),
                          'distinct_foreground_group_overlap_checks': 'passed for every rendered canvas, including all120 motion samples',
                          'max_abs_dx_px': max(abs(r['delta_x_px']) for r in component_reports),
                          'max_abs_dy_px': max(abs(r['delta_y_px']) for r in component_reports),
                          'passed': all(r['passed'] for r in component_reports)}}
    (QA / 'mockup-verification.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    (QA / 'mockup-verification.txt').write_text(
        f'Fibonacci preproduction: {len(shots)} still scenes,41terms,120 sampled motion frames;{gif_frames} encoded GIF frames,{gif_duration_ms}ms.\n'
        f'Centered components: {len(component_reports)}; both axes0.5px; all pass={data["alignment"]["passed"]}.\n'
        f'Max |dx|={data["alignment"]["max_abs_dx_px"]}px; max |dy|={data["alignment"]["max_abs_dy_px"]}px.\n'
        'No production video or speech has been generated or verified.\n', encoding='utf-8')
    print(json.dumps({'shots': len(shots), 'terms': len(VALUES), 'alignment': data['alignment'],
                      'longest_reading_index': longest, 'output': str(OUT)}, ensure_ascii=False))


if __name__ == '__main__':
    run()
