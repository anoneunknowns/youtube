"""Render the four-base counting preproduction stills from registered artwork."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from render_binary_video import file_hash
from render_octal_mockups import (
    CREAM, INK, MUTED, ROOT, SIZE, TEAL, font, ink_bounds, place_text, rounded,
)


BACKGROUND = ROOT / 'assets/library/worlds/seaside-lighthouse/backgrounds/v001/seaside-lighthouse-background.png'
CHARACTER = ROOT / 'assets/library/characters/little-bird/sources/v002/source-manifest.json'
OUTPUT = ROOT / 'assets/library/references/four-base-counting/v003'
BOARD = (60, 230, 1440, 1030)
TITLE_BOX = (60, 30, 1440, 202)
LABEL_CENTER_X = 280
DIVIDER_X = 500
LAST_SYMBOL_CENTER_X = 1315
SYMBOL_STEP = 104
NUMBER_FONT_SIZE = 118
LABEL_FONT_SIZE = 43
BASE_FONT_SIZE = 27
ROWS = (
    ('binary', 'BINARY', 2, (82, 248, 1418, 423)),
    ('decimal', 'DECIMAL', 10, (82, 443, 1418, 618)),
    ('octal', 'OCTAL', 8, (82, 638, 1418, 813)),
    ('hexadecimal', 'HEXADECIMAL', 16, (82, 833, 1418, 1008)),
)


@dataclass(frozen=True)
class Shot:
    filename: str
    caption: str
    value: int
    voice_active: bool = False
    teaching_marks: tuple[tuple[str, int], ...] = ()
    state: str = 'count'


SHOTS = (
    Shot('01-introduction.png', '01  One value, four number systems', 10, state='introduction'),
    Shot('02-zero.png', '02  Begin at zero', 0, True),
    Shot('03-octal-new-place.png', '03  Eight: a new octal place', 8,
         teaching_marks=(('octal', 0),), state='octal-new-place'),
    Shot('04-hex-new-place.png', '04  Sixteen: a new hexadecimal place', 16,
         teaching_marks=(('hexadecimal', 0),), state='hexadecimal-new-place'),
    Shot('key-visual.png', '05  Twenty-six in all four systems', 26, True),
    Shot('06-double-carry.png', '06  Sixty-four: two new places', 64,
         teaching_marks=(('binary', 0), ('octal', 0)), state='double-new-place'),
    Shot('07-maximum-width.png', '07  One hundred twenty-seven', 127, True),
    Shot('08-finale.png', '08  Finish together at 127', 127, state='finale'),
)


def representations(value: int) -> dict[str, str]:
    if not 0 <= value <= 127:
        raise ValueError('Four-base preproduction covers decimal 0 through 127')
    return {'binary': format(value, 'b'), 'decimal': str(value),
            'octal': format(value, 'o'), 'hexadecimal': format(value, 'X')}


def centered_text_bounds(text: str, center: tuple[float, float], size: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = ink_bounds(text, size)
    origin = (round(center[0] - (left + right) / 2), round(center[1] - (top + bottom) / 2))
    return (origin[0] + left, origin[1] + top, origin[0] + right, origin[1] + bottom)


def baseline_ink_bounds(text: str, size: int) -> tuple[int, int, int, int]:
    mask, (offset_x, offset_y) = font(size).getmask2(text, mode='L', anchor='ls')
    left, top, right, bottom = mask.getbbox()
    return left + offset_x, top + offset_y, right + offset_x, bottom + offset_y


ZERO_INK = baseline_ink_bounds('0', NUMBER_FONT_SIZE)


def row_baseline(box: tuple[int, int, int, int]) -> int:
    return round((box[1] + box[3]) / 2 - (ZERO_INK[1] + ZERO_INK[3]) / 2)


def draw_label_block(draw, label: str, base: int, box, spoken: bool) -> dict:
    nodes = [(label, LABEL_FONT_SIZE, 'text'), (f'BASE {base}', BASE_FONT_SIZE, 'text')]
    if spoken:
        nodes.append(('SPOKEN', 20, 'pill'))
    heights = [28 if kind == 'pill' else ink_bounds(text, size)[3] - ink_bounds(text, size)[1]
               for text, size, kind in nodes]
    gap = 10
    block_height = sum(heights) + gap * (len(nodes) - 1)
    center_y = (box[1] + box[3]) / 2
    cursor = center_y - block_height / 2
    records = []
    for (text, size, kind), height in zip(nodes, heights, strict=True):
        node_center = (LABEL_CENTER_X, cursor + height / 2)
        color = TEAL if text == label or kind == 'pill' else MUTED
        bounds = centered_text_bounds(text, node_center, size)
        node_bounds = bounds
        if kind == 'pill':
            node_bounds = (LABEL_CENTER_X - 65, round(node_center[1] - 14),
                           LABEL_CENTER_X + 65, round(node_center[1] + 14))
            rounded(draw, node_bounds, '#fff8ea', '#cfb28d', 1, 12)
        place_text(draw, text, node_center, size, color)
        records.append({'text': text, 'font_size': size, 'ink_bounds_px': list(bounds),
                        'element_bounds_px': list(node_bounds), 'kind': kind})
        cursor += height + gap
    top = min(row['element_bounds_px'][1] for row in records)
    bottom = max(row['element_bounds_px'][3] for row in records)
    error = (top + bottom) / 2 - center_y
    if abs(error) > .5:
        raise ValueError(f'Label block not vertically centered: {label} ({error})')
    if any(row['ink_bounds_px'][0] < box[0] + 24 or row['ink_bounds_px'][2] > DIVIDER_X - 24
           for row in records):
        raise ValueError(f'Label does not fit its field: {label}')
    return {'nodes': records, 'block_top_bottom_px': [top, bottom],
            'vertical_center_error_px': error}


def draw_value(draw, text: str, box, active: bool, marked_indices: set[int]) -> dict:
    baseline = row_baseline(box)
    centers = [LAST_SYMBOL_CENTER_X - SYMBOL_STEP * (len(text) - 1 - index) for index in range(len(text))]
    symbols = []
    for index, (symbol, center) in enumerate(zip(text, centers, strict=True)):
        marked = index in marked_indices
        if marked:
            rounded(draw, (center - 47, box[1] + 24, center + 47, box[3] - 24),
                    '#e1efda', '#c7a262', 2, 18)
        left, top, right, bottom = baseline_ink_bounds(symbol, NUMBER_FONT_SIZE)
        origin_x = round(center - (left + right) / 2)
        bounds = (origin_x + left, baseline + top, origin_x + right, baseline + bottom)
        if bounds[0] < DIVIDER_X + 35 or bounds[2] > box[2] - 28:
            raise ValueError(f'Numeric symbol does not fit the fixed-width field: {text}')
        if bounds[1] < box[1] + 18 or bounds[3] > box[3] - 18:
            raise ValueError(f'Numeric symbol does not fit vertically: {text}')
        draw.text((origin_x, baseline), symbol, font=font(NUMBER_FONT_SIZE),
                  fill=TEAL if active or marked else INK, anchor='ls')
        symbols.append({'symbol': symbol, 'index': index, 'center_x_px': center,
                        'actual_ink_center_x_px': (bounds[0] + bounds[2]) / 2,
                        'ink_bounds_px': list(bounds), 'marked_new_place': marked})
    return {'text': text, 'font_size': NUMBER_FONT_SIZE, 'baseline_y_px': baseline,
            'last_symbol_center_x_px': LAST_SYMBOL_CENTER_X, 'symbol_step_px': SYMBOL_STEP,
            'symbols': symbols, 'voice_active': active,
            'zero_ink_center_error_px': baseline + (ZERO_INK[1] + ZERO_INK[3]) / 2 - (box[1] + box[3]) / 2}


class LittleBird:
    def __init__(self, height: int = 280, root: tuple[int, int] = (1675, 950), character_manifest: Path = CHARACTER):
        bundle = json.loads(character_manifest.read_text(encoding='utf-8'))
        registration = bundle['render_registration']
        path = character_manifest.with_name(registration['neutral_path'])
        if file_hash(path) != registration['neutral_sha256']:
            raise ValueError('Existing Little Bird neutral does not match its registration')
        with Image.open(path) as source:
            neutral = source.convert('RGBA')
        scale = height / registration['neutral_natural_height_px']
        self.sprite = neutral.resize((round(neutral.width * scale), round(neutral.height * scale)), Image.Resampling.LANCZOS)
        self.position = tuple(round(coordinate - anchor * scale)
                              for coordinate, anchor in zip(root, registration['neutral_anchor_px'], strict=True))
        self.root = root
        bbox = self.sprite.getchannel('A').point(lambda alpha: 255 if alpha >= 8 else 0).getbbox()
        visible = [bbox[0] + self.position[0], bbox[1] + self.position[1],
                   bbox[2] + self.position[0], bbox[3] + self.position[1]]
        if visible[0] <= BOARD[2] or visible[2] >= SIZE[0] or visible[3] >= SIZE[1]:
            raise ValueError(f'Bird overlaps the panel or frame edge: {visible}')
        self.metadata = {'pose': 'neutral', 'height_px': height, 'foot_root_px': list(root),
                         'scale': scale, 'position_px': list(self.position), 'visible_bbox_px': visible,
                         'mirrored': False, 'new_art_generated': False,
                         'source': path.relative_to(ROOT).as_posix(), 'source_sha256': file_hash(path)}

    def draw(self, image):
        shadow = Image.new('RGBA', SIZE)
        draw = ImageDraw.Draw(shadow)
        x, y = self.root
        ratio = self.metadata['height_px'] / 430
        draw.ellipse((x - 145 * ratio, y - 3 * ratio, x + 145 * ratio, y + 25 * ratio), fill=(82, 69, 57, 33))
        image.alpha_composite(shadow)
        image.alpha_composite(self.sprite, self.position)


def draw_title(draw) -> dict:
    items = [('FOUR WAYS TO COUNT', 62, 91), ('0–127 IN DECIMAL', 31, 157)]
    target_center = (TITLE_BOX[1] + TITLE_BOX[3]) / 2
    before = [centered_text_bounds(text, (750, y), size) for text, size, y in items]
    shift = target_center - (min(box[1] for box in before) + max(box[3] for box in before)) / 2
    records = []
    for index, (text, size, y) in enumerate(items):
        center = (750, y + shift)
        place_text(draw, text, center, size, INK if index == 0 else TEAL)
        records.append({'text': text, 'font_size': size,
                        'ink_bounds_px': list(centered_text_bounds(text, center, size))})
    top = min(row['ink_bounds_px'][1] for row in records)
    bottom = max(row['ink_bounds_px'][3] for row in records)
    error = (top + bottom) / 2 - target_center
    if abs(error) > .5:
        raise ValueError('Title ink block is not vertically centered')
    return {'lines': records, 'ink_block_top_bottom_px': [top, bottom],
            'vertical_center_error_px': error}


def render(background, bird: LittleBird, shot: Shot) -> tuple[Image.Image, dict]:
    values = representations(shot.value)
    image = background.copy()
    bird.draw(image)
    draw = ImageDraw.Draw(image)
    rounded(draw, (60, 39, 1440, 211), '#bca88a', radius=31)
    rounded(draw, TITLE_BOX, CREAM, '#bba17d', 3, 31)
    title_metadata = draw_title(draw)
    rounded(draw, (1470, 40, 1880, 121), '#bca88a', radius=24)
    rounded(draw, (1470, 35, 1880, 116), CREAM, '#bba17d', 2, 24)
    place_text(draw, 'Num-Num Numbers', (1675, 76), 31, '#654268')
    rounded(draw, (60, 239, 1440, 1039), '#ae9979', radius=35)
    rounded(draw, BOARD, '#fffaf0', '#b69c78', 4, 35)
    rows = []
    for row_id, label, base, box in ROWS:
        spoken = row_id == 'decimal'
        active = spoken and shot.voice_active
        fill = '#ffead0' if active else '#fff0de' if spoken else CREAM
        edge = '#bc8c55' if active else '#cfb48e' if spoken else '#d8c8af'
        rounded(draw, box, fill, edge, 3 if active else 2, 21)
        draw.line((DIVIDER_X, box[1] + 25, DIVIDER_X, box[3] - 25), fill='#e3d4bd', width=2)
        label_metadata = draw_label_block(draw, label, base, box, spoken)
        marked = {index for target, index in shot.teaching_marks if target == row_id}
        if any(index < 0 or index >= len(values[row_id]) for index in marked):
            raise ValueError('Teaching mark is outside the displayed representation')
        value_metadata = draw_value(draw, values[row_id], box, active, marked)
        rows.append({'id': row_id, 'base': base, 'box_px': list(box), 'spoken': spoken,
                     'label': label_metadata, 'value': value_metadata})
    return image.convert('RGB'), {'filename': shot.filename, 'caption': shot.caption,
            'state': shot.state, 'decimal_value': shot.value, 'representations': values,
            'voice_base': 10, 'voice_active': shot.voice_active,
            'teaching_marks': [{'base': name, 'symbol_index': index} for name, index in shot.teaching_marks],
            'rows': rows, 'title': title_metadata, 'character_pose': 'neutral'}


def validate_all_values() -> dict:
    # Validate data and typographic fit before any requested artifact is written.
    scratch = ImageDraw.Draw(Image.new('RGB', SIZE))
    minimum_padding = 10000
    maximum_center_error = 0
    for value in range(128):
        values = representations(value)
        for row_id, _, base, box in ROWS:
            if int(values[row_id], base) != value:
                raise ValueError(f'Incorrect conversion: {value}, {row_id}')
            record = draw_value(scratch, values[row_id], box, False, set())
            for symbol in record['symbols']:
                bounds = symbol['ink_bounds_px']
                maximum_center_error = max(maximum_center_error,
                                           abs(symbol['actual_ink_center_x_px'] - symbol['center_x_px']))
                minimum_padding = min(minimum_padding, bounds[0] - DIVIDER_X, box[2] - bounds[2],
                                      bounds[1] - box[1], box[3] - bounds[3])
    return {'all_decimal_values_checked': 128, 'representations_checked': 512,
            'font_size_fixed': NUMBER_FONT_SIZE, 'no_fit_clamping': True,
            'minimum_numeric_padding_px': minimum_padding,
            'maximum_numeric_horizontal_center_error_px': maximum_center_error,
            'digit_alignment': 'Fixed rightmost glyph center and equal symbol pitch; common baseline within each row.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', '--output-dir', dest='out', type=Path, default=OUTPUT)
    parser.add_argument('--character-manifest', type=Path, default=CHARACTER)
    parser.add_argument('--bird-height', type=int, default=280)
    parser.add_argument('--bird-root', type=int, nargs=2, default=(1675, 950))
    args = parser.parse_args()
    output = args.out.resolve()
    names = [shot.filename for shot in SHOTS] + ['storyboard.png', 'reference-manifest.json']
    if any((output / name).exists() for name in names):
        raise FileExistsError('Choose a new output folder; existing reference artifacts are never overwritten')
    validation = validate_all_values()
    with Image.open(BACKGROUND) as source:
        background_size = source.size
        background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
    character_manifest = args.character_manifest.resolve()
    bird = LittleBird(height=args.bird_height, root=tuple(args.bird_root), character_manifest=character_manifest)
    frames_and_records = [render(background, bird, shot) for shot in SHOTS]
    output.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGB', (1800, 1290), '#f5eee0')
    draw = ImageDraw.Draw(sheet)
    place_text(draw, 'Num-Num Numbers  /  Four Ways to Count', (900, 47), 38, INK)
    records = []
    for index, ((frame, record), shot) in enumerate(zip(frames_and_records, SHOTS, strict=True)):
        path = output / shot.filename
        frame.save(path)
        record['sha256'] = file_hash(path)
        x, y = 40 + (index % 3) * 580, 110 + (index // 3) * 380
        rounded(draw, (x - 2, y - 2, x + 562, y + 317), '#b59b7c', radius=5)
        sheet.paste(frame.resize((560, 315), Image.Resampling.LANCZOS), (x, y))
        place_text(draw, shot.caption, (x + 280, y + 346), 23, INK)
        records.append(record)
    sheet_path = output / 'storyboard.png'
    sheet.save(sheet_path)
    manifest = {
        'schema_version': 1, 'status': 'prepared-for-user-review', 'series': 'Num-Num Numbers',
        'episode_id': 'four-base-counting-001', 'title': 'Four Ways to Count',
        'theme': 'Seaside Lighthouse', 'character': 'Little Bird', 'frame_size_px': list(SIZE),
        'renderer': 'tools/render_four_base_mockups.py', 'renderer_sha256': file_hash(Path(__file__)),
        'background': {'path': BACKGROUND.relative_to(ROOT).as_posix(), 'sha256': file_hash(BACKGROUND),
                       'source_size_px': list(background_size), 'fit': 'cover, centered, isotropic',
                       'generation_record': BACKGROUND.with_name('generation-record.json').relative_to(ROOT).as_posix()},
        'character_source_manifest': character_manifest.relative_to(ROOT).as_posix(),
        'character_source_manifest_sha256': file_hash(character_manifest), 'character_registration': bird.metadata,
        'panel_bounds_px': list(BOARD), 'title_bounds_px': list(TITLE_BOX),
        'base_order': [row[2] for row in ROWS], 'voice_base': 10,
        'layout_validation': validation, 'shots': records,
        'storyboard': {'path': 'storyboard.png', 'size_px': list(sheet.size), 'sha256': file_hash(sheet_path)},
        'omitted_displays': ['separate decimal sign', 'read-aloud duplicate line', 'place weights', 'digit-range footer'],
    }
    (output / 'reference-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'stills': len(records), 'validation': validation}))


if __name__ == '__main__':
    main()
