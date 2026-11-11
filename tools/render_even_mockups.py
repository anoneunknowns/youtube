"""Render nine even-number planning stills from the registered bird and workshop."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from render_four_base_mockups_v002 import LittleBird, centered_text_bounds
from render_octal_mockups import CREAM, INK, MUTED, ROOT, SIZE, TEAL, font, ink_bounds, place_text, rounded
from render_binary_video import file_hash


BACKGROUND = ROOT / 'assets/library/worlds/wooden-toy-workshop/backgrounds/v001/wooden-toy-workshop-background.png'
CHARACTER = ROOT / 'assets/library/characters/little-bird/sources/v002/source-manifest.json'
OUTPUT = ROOT / 'assets/library/references/even-counting/v002'
BOARD = (60, 220, 1440, 1030)
TITLE_BOX = (60, 30, 1440, 202)
NUMBER_FIELD = (135, 292, 1100, 598)
READING_FIELD = (120, 605, 1380, 665)
TEACHING_FIELD = (120, 687, 1380, 855)
NUMBER_CENTER = (680, 447)
NUMBER_FONT_SIZE = 360
WORD_FONT_SIZE = 42
ONE_TO_NINETEEN = (
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
    'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
    'seventeen', 'eighteen', 'nineteen',
)
TENS = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')


@dataclass(frozen=True)
class Shot:
    filename: str
    caption: str
    value: int
    state: str = 'count'


SHOTS = (
    Shot('01-introduction.png', '01  Six blocks, three pairs', 6, 'pairs'),
    Shot('02-zero.png', '02  Zero is even', 0, 'zero'),
    Shot('03-eight.png', '03  Count by twos: 6, 8, 10', 8),
    Shot('04-twenty-pairs.png', '04  Twenty blocks, ten pairs', 20, 'twenty-pairs'),
    Shot('key-visual.png', '05  Forty-eight', 48),
    Shot('06-98-to-100.png', '06  From 98 to 100: add two', 100, 'hundred-step'),
    Shot('07-hundred-rule.png', '07  Even final digits', 100, 'final-digit-rule'),
    Shot('08-maximum-reading-width.png', '08  One hundred seventy-eight', 178),
    Shot('09-finale.png', '09  Finish at 200', 200, 'finale'),
)


def words(value: int) -> str:
    """Use the series' natural US-English reading, without 'and'."""
    if not 0 <= value <= 200:
        raise ValueError('This planning episode covers zero through two hundred')
    if value < 20:
        return ONE_TO_NINETEEN[value]
    if value < 100:
        return TENS[value // 10] + (f'-{ONE_TO_NINETEEN[value % 10]}' if value % 10 else '')
    if value < 200:
        return 'one hundred' + (f' {words(value % 100)}' if value % 100 else '')
    return 'two hundred'


def checked_text(draw, text: str, center, size: int, color: str, field=None) -> dict:
    bounds = centered_text_bounds(text, center, size)
    if field is not None and not (field[0] <= bounds[0] and field[1] <= bounds[1]
                                  and bounds[2] <= field[2] and bounds[3] <= field[3]):
        raise ValueError(f'Text outside its field: {text}: {bounds} outside {field}')
    place_text(draw, text, center, size, color)
    return {'text': text, 'font_size_px': size, 'ink_bounds_px': list(bounds)}


def draw_block(draw, x: int, y: int, width: int = 44, height: int = 38) -> dict:
    """A deterministic toy token, independent of generated background objects."""
    rounded(draw, (x + 2, y + 4, x + width + 2, y + height + 4), '#d5bc95', radius=7)
    rounded(draw, (x, y, x + width, y + height), '#eabf82', '#9c6e3f', 2, 7)
    draw.line((x + 9, y + 9, x + width - 9, y + 9), fill='#f5d7aa', width=2)
    return {'bounds_px': [x, y, x + width + 2, y + height + 4], 'counted_quantity': 1}


def draw_pair_demo(draw, value: int) -> dict:
    if value != 6:
        raise ValueError('The introductory demonstration must contain exactly six blocks')
    label = checked_text(draw, '6 BLOCKS  ·  3 PAIRS', (750, 716), 31, TEAL, TEACHING_FIELD)
    blocks, pair_boxes = [], []
    for index, center in enumerate((485, 750, 1015)):
        box = (center - 56, 740, center + 56, 844)
        rounded(draw, box, '#fff0d8', '#c6a174', 2, 16)
        for row, y in enumerate((750, 800)):
            blocks.append({'pair_index': index, 'row': row, 'column': index,
                           **draw_block(draw, center - 25, y, 50, 30)})
        pair_boxes.append(list(box))
    return {'kind': 'three-pairs', 'label': label, 'blocks': blocks, 'block_count': len(blocks),
            'pair_count': len(pair_boxes), 'pair_boxes_px': pair_boxes,
            'arrangement': 'Two rows of three; each outlined column is one vertical pair.',
            'meaning': 'All six visible toy tokens are counted; each outlined column contains two.'}


def draw_twenty_demo(draw) -> dict:
    label = checked_text(draw, '20 BLOCKS  ·  10 PAIRS', (750, 711), 30, TEAL, TEACHING_FIELD)
    blocks, pair_brackets = [], []
    for column in range(10):
        x = 345 + 82 * column
        for row, y in enumerate((740, 799)):
            blocks.append({'row': row, 'column': column, **draw_block(draw, x, y, 38, 32)})
        bracket_x = x + 48
        draw.line((bracket_x - 6, 755, bracket_x, 755, bracket_x, 815, bracket_x - 6, 815),
                  fill='#6c9180', width=3)
        pair_brackets.append({'column': column, 'bounds_px': [bracket_x - 6, 755, bracket_x, 815],
                              'counted_quantity': 2})
    if len(blocks) != 20 or len(pair_brackets) != 10:
        raise ValueError('The twenty demonstration must contain exactly ten vertical pairs')
    return {'kind': 'twenty-as-ten-pairs', 'label': label, 'blocks': blocks,
            'block_count': len(blocks), 'pair_count': len(pair_brackets),
            'pair_brackets': pair_brackets, 'arrangement': 'Two rows of ten; each column is one pair.'}


def progression(value: int) -> tuple[int | None, int, int | None]:
    if value not in range(0, 201, 2):
        raise ValueError('The progression accepts only even values zero through two hundred')
    return (value - 2 if value >= 2 else None, value, value + 2 if value < 200 else None)


def draw_progression(draw, value: int, finale: bool) -> dict:
    checked_text(draw, 'FINISHED 0–200' if finale else 'COUNT BY TWOS', (750, 878), 24,
                 TEAL if finale else MUTED, (120, 860, 1380, 896))
    values = progression(value)
    cards = []
    for index, (center, number) in enumerate(zip((460, 750, 1040), values, strict=True)):
        box = (center - 118, 904, center + 118, 1002)
        current = index == 1
        rounded(draw, box, '#e0efe4' if current else '#f6efdf',
                '#397f6f' if current else '#d2b993', 3 if current else 2, 20)
        node = {'role': ('previous', 'current', 'next')[index], 'value': number,
                'bounds_px': list(box), 'current': current}
        if number is not None:
            node['label'] = checked_text(draw, str(number), (center, 953), 61,
                                         TEAL if current else MUTED, box)
        else:
            node['label'] = checked_text(draw, 'START' if value == 0 else 'END', (center, 953),
                                         25, MUTED, box)
        cards.append(node)
    for center in (605, 895):
        # A fixed directional cue between equal-style number cards.
        draw.line((center - 12, 953, center + 12, 953), fill='#9b896d', width=3)
        draw.line((center + 4, 945, center + 12, 953, center + 4, 961), fill='#9b896d', width=3)
    return {'values': list(values), 'cards': cards, 'step': 2,
            'beyond_episode_value_shown': any(n is not None and n > 200 for n in values)}


def draw_teaching(draw, shot: Shot) -> dict:
    rounded(draw, TEACHING_FIELD, '#f9f0dd', '#e1cfb2', 2, 21)
    if shot.state == 'pairs':
        return draw_pair_demo(draw, shot.value)
    if shot.state == 'twenty-pairs':
        return draw_twenty_demo(draw)
    if shot.state == 'zero':
        label = checked_text(draw, 'ZERO IS EVEN', (750, 718), 34, TEAL, TEACHING_FIELD)
        tray = (478, 757, 1022, 825)
        rounded(draw, tray, '#efdfc1', '#b08b5d', 3, 15)
        rounded(draw, (489, 767, 1011, 814), '#fff8e8', '#d1b68c', 2, 11)
        return {'kind': 'empty-tray', 'label': label, 'tray_bounds_px': list(tray),
                'block_count': 0, 'pair_count': 0, 'counted_quantity': 0}
    if shot.state == 'hundred-step':
        label = checked_text(draw, '98 + 2 = 100', (750, 751), 52, TEAL, TEACHING_FIELD)
        note = checked_text(draw, 'THE STEP STAYS TWO', (750, 815), 25, MUTED, TEACHING_FIELD)
        return {'kind': 'hundred-step', 'label': label, 'note': note, 'step': 2}
    if shot.state == 'final-digit-rule':
        label = checked_text(draw, 'EVEN NUMBERS END IN', (750, 713), 29, TEAL, TEACHING_FIELD)
        chips = []
        for digit, center in zip((0, 2, 4, 6, 8), (530, 640, 750, 860, 970), strict=True):
            box = (center - 39, 749, center + 39, 829)
            rounded(draw, box, '#e1efe2', '#9eba9e', 2, 15)
            chips.append({'digit': digit, 'label': checked_text(draw, str(digit), (center, 788), 51, TEAL, box)})
        return {'kind': 'final-digit-rule', 'label': label, 'chips': chips,
                'chips_represent_total_quantity': False, 'main_quantity': shot.value}
    label = checked_text(draw, 'ADD TWO EACH TIME' if shot.state != 'finale' else 'WE COUNTED FROM 0 TO 200',
                         (750, 770), 36, TEAL, TEACHING_FIELD)
    record = {'kind': 'text-cue', 'label': label}
    if shot.state == 'finale':
        checkmark = [(1256, 774), (1272, 790), (1304, 752)]
        draw.line(checkmark, fill='#488b72', width=7, joint='curve')
        record['completion_checkmark'] = {'path_px': [list(point) for point in checkmark],
                                          'stroke_width_px': 7, 'count': 1,
                                          'bounds_px': [1252, 748, 1308, 794]}
    return record


def render(background, bird: LittleBird, shot: Shot) -> tuple[Image.Image, dict]:
    frame = background.copy()
    bird.draw(frame)
    draw = ImageDraw.Draw(frame)
    rounded(draw, (60, 39, 1440, 211), '#bba485', radius=31)
    rounded(draw, TITLE_BOX, CREAM, '#bba17d', 3, 31)
    title = [checked_text(draw, 'EVEN NUMBERS', (750, 90), 70, INK, TITLE_BOX),
             checked_text(draw, '0–200  ·  COUNT BY TWOS', (750, 157), 32, TEAL, TITLE_BOX)]
    rounded(draw, (1470, 40, 1880, 121), '#bca88a', radius=24)
    rounded(draw, (1470, 35, 1880, 116), CREAM, '#bba17d', 2, 24)
    checked_text(draw, 'Num-Num Numbers', (1675, 76), 31, '#654268', (1470, 35, 1880, 116))
    rounded(draw, (60, 229, 1440, 1039), '#ae9979', radius=35)
    rounded(draw, BOARD, '#fffaf0', '#b69c78', 4, 35)
    checked_text(draw, 'PAIR CHECK' if shot.state in ('pairs', 'twenty-pairs') else 'EVEN NUMBER',
                 (680, 270), 26, MUTED, (120, 242, 1100, 290))
    number = checked_text(draw, str(shot.value), NUMBER_CENTER, NUMBER_FONT_SIZE, INK, NUMBER_FIELD)
    final_digit_mark = None
    if shot.state == 'final-digit-rule':
        text = str(shot.value)
        left, top, right, bottom = ink_bounds(text, NUMBER_FONT_SIZE)
        origin_x = round(NUMBER_CENTER[0] - (left + right) / 2)
        origin_y = round(NUMBER_CENTER[1] - (top + bottom) / 2)
        glyph_left, glyph_top, glyph_right, glyph_bottom = ink_bounds(text[-1], NUMBER_FONT_SIZE)
        glyph_x = origin_x + font(NUMBER_FONT_SIZE).getlength(text[:-1])
        glyph_box = (round(glyph_x + glyph_left), origin_y + glyph_top,
                     round(glyph_x + glyph_right), origin_y + glyph_bottom)
        ring = (glyph_box[0] - 10, glyph_box[1] - 9, glyph_box[2] + 10, glyph_box[3] + 9)
        rounded(draw, ring, None, '#9cbcaa', 5, 29)
        final_digit_mark = {'digit': text[-1], 'glyph_ink_bounds_px': list(glyph_box),
                            'outline_bounds_px': list(ring), 'outline_width_px': 5,
                            'number_position_or_font_changed': False}
    badge = (1170, 383, 1362, 511)
    rounded(draw, badge, '#e1efe4', '#95b6a0', 3, 26)
    checked_text(draw, '+2', (1266, 447), 73, TEAL, badge)
    reading = checked_text(draw, words(shot.value), (750, 635), WORD_FONT_SIZE, TEAL, READING_FIELD)
    teaching = draw_teaching(draw, shot)
    trail = draw_progression(draw, shot.value, shot.state == 'finale')
    return frame.convert('RGB'), {'filename': shot.filename, 'caption': shot.caption,
            'state': shot.state, 'decimal_value': shot.value, 'spoken_text': words(shot.value),
            'title': title, 'number': number, 'reading': reading, 'teaching': teaching,
            'progression': trail, 'character_pose': 'neutral', 'step_badge': '+2',
            'final_digit_mark': final_digit_mark}


def validate_all_values() -> dict:
    draw = ImageDraw.Draw(Image.new('RGB', SIZE))
    records = []
    for index, value in enumerate(range(0, 201, 2)):
        if value != index * 2 or value % 2:
            raise ValueError('Even-number sequence has a mathematical error')
        number = checked_text(draw, str(value), NUMBER_CENTER, NUMBER_FONT_SIZE, INK, NUMBER_FIELD)
        reading = checked_text(draw, words(value), (750, 635), WORD_FONT_SIZE, TEAL, READING_FIELD)
        neighbors = progression(value)
        if any(n is not None and (n % 2 or not 0 <= n <= 200) for n in neighbors):
            raise ValueError('An invalid value appears in the progression')
        records.append({'decimal_value': value, 'spoken_text': words(value),
                        'number_ink_bounds_px': number['ink_bounds_px'],
                        'reading_ink_bounds_px': reading['ink_bounds_px'],
                        'reading_ink_width_px': reading['ink_bounds_px'][2] - reading['ink_bounds_px'][0],
                        'progression_values': list(neighbors)})
    maximum = max(records, key=lambda row: row['reading_ink_width_px'])
    plan_path = ROOT / 'design/even-counting-v1/count-lines.json'
    plan_consistency = 'not-present-at-render-time'
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
        lines = plan if isinstance(plan, list) else plan.get('counted_states', plan.get('count_lines', plan.get('lines', [])))
        if len(lines) != 101:
            raise ValueError('The authored count-lines plan must contain 101 values')
        for expected, line in zip(range(0, 201, 2), lines, strict=True):
            actual = line.get('decimal_value', line.get('number', line.get('value')))
            if actual != expected:
                raise ValueError(f'The authored count-lines plan disagrees at {expected}: {actual}')
            if line.get('spoken_text', words(expected)).lower().rstrip('.') != words(expected):
                raise ValueError(f'The authored reading disagrees at {expected}')
        plan_consistency = 'all-101-values-and-natural-readings-match'
    return {'all_values_checked': 101, 'start': 0, 'end': 200, 'step': 2,
            'fixed_number_font_size_px': NUMBER_FONT_SIZE, 'fixed_word_font_size_px': WORD_FONT_SIZE,
            'dynamic_font_shrinking': False, 'maximum_reading_width': maximum,
            'no_value_202': True, 'zero_demonstration_has_zero_blocks': True,
            'six_demonstration_exact_blocks': 6, 'twenty_demonstration_exact_blocks': 20,
            'plan_consistency': plan_consistency, 'values': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', '--output-dir', dest='out', type=Path, default=OUTPUT)
    parser.add_argument('--background', type=Path, default=BACKGROUND)
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        raise FileExistsError('Choose a new output folder; reference artifacts are never overwritten')
    validation = validate_all_values()
    background_path = args.background.resolve()
    with Image.open(background_path) as source:
        source_size = source.size
        background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
    bird = LittleBird(height=280, root=(1675, 950), character_manifest=CHARACTER)
    frames_and_records = [render(background, bird, shot) for shot in SHOTS]
    output.mkdir(parents=True, exist_ok=False)
    sheet = Image.new('RGB', (1800, 1290), '#f5eee0')
    draw = ImageDraw.Draw(sheet)
    checked_text(draw, 'Num-Num Numbers  /  Even Numbers', (900, 47), 38, INK)
    records = []
    for index, ((frame, record), shot) in enumerate(zip(frames_and_records, SHOTS, strict=True)):
        path = output / shot.filename
        frame.save(path)
        record['sha256'] = file_hash(path)
        x, y = 40 + index % 3 * 580, 110 + index // 3 * 380
        rounded(draw, (x - 2, y - 2, x + 562, y + 317), '#b59b7c', radius=5)
        sheet.paste(frame.resize((560, 315), Image.Resampling.LANCZOS), (x, y))
        checked_text(draw, shot.caption, (x + 280, y + 346), 23, INK,
                     (x - 5, y + 325, x + 565, y + 368))
        records.append(record)
    sheet_path = output / 'storyboard.png'
    sheet.save(sheet_path)
    manifest = {
        'schema_version': 1, 'version': 'v002', 'status': 'prepared-for-user-review', 'episode_id': 'even-counting-001',
        'series': 'Num-Num Numbers', 'title': 'Even Numbers', 'theme': 'Wooden Toy Workshop',
        'frame_size_px': list(SIZE), 'count_range': [0, 200], 'step': 2, 'counted_values': 101,
        'renderer': Path(__file__).relative_to(ROOT).as_posix(), 'renderer_sha256': file_hash(Path(__file__)),
        'background': {'path': background_path.relative_to(ROOT).as_posix(), 'sha256': file_hash(background_path),
                       'source_size_px': list(source_size), 'fit': 'cover, centered, isotropic'},
        'character_source_manifest': CHARACTER.relative_to(ROOT).as_posix(),
        'character_source_manifest_sha256': file_hash(CHARACTER), 'character_registration': bird.metadata,
        'panel_bounds_px': list(BOARD), 'title_bounds_px': list(TITLE_BOX),
        'number_field_px': list(NUMBER_FIELD), 'reading_field_px': list(READING_FIELD),
        'teaching_field_px': list(TEACHING_FIELD), 'layout_validation': validation,
        'quantity_token_policy': 'Only code-drawn blocks inside the teaching tray are counted. Background toys are decorative.',
        'shots': records, 'storyboard': {'path': 'storyboard.png', 'size_px': list(sheet.size),
                                        'sha256': file_hash(sheet_path)},
        'manual_stills_review_pending': True, 'audio_generated': False, 'video_generated': False,
    }
    (output / 'reference-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'stills': len(records),
                      'all_values_checked': validation['all_values_checked'],
                      'maximum_reading_width': validation['maximum_reading_width'],
                      'manual_stills_review_pending': True}))


if __name__ == '__main__':
    main()
