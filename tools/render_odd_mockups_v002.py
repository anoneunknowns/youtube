"""Compose the odd-counting v002 reference stills from registered artwork and ticket diagrams."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from render_binary_video import file_hash
from render_four_base_mockups_v002 import centered_text_bounds
from render_octal_mockups import CREAM, INK, MUTED, ROOT, SIZE, TEAL, font, place_text, rounded


BACKGROUND = ROOT / 'assets/library/worlds/mountain-cable-station/backgrounds/v001/mountain-cable-station-background.png'
CHARACTER = ROOT / 'assets/library/characters/red-panda/sources/v001/source-manifest.json'
OUTPUT = ROOT / 'assets/library/references/odd-counting/v002'
BOARD = (60, 220, 1400, 1030)
TITLE_BOX = (60, 30, 1400, 202)
NUMBER_FIELD = (135, 292, 1100, 598)
READING_FIELD = (120, 605, 1340, 665)
TEACHING_FIELD = (120, 687, 1340, 855)
NUMBER_CENTER = (680, 447)
NUMBER_FONT_SIZE = 360
WORD_FONT_SIZE = 42
CARD_CENTERS = (250, 410, 570, 730, 890, 1050, 1210)
CARD_BOX_Y = (910, 1002)
ONE_TO_NINETEEN = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
                  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
                  'seventeen', 'eighteen', 'nineteen')
TENS = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')


@dataclass(frozen=True)
class Shot:
    filename: str
    caption: str
    value: int
    state: str = 'count'


SHOTS = (
    Shot('01-one-ticket.png', '01  One ticket, no partner', 1, 'single'),
    Shot('02-five-tickets.png', '02  Two pairs and one left over', 5, 'five'),
    Shot('03-seven.png', '03  Seven: add two each time', 7),
    Shot('04-nine-tickets.png', '04  Four pairs and one left over', 9, 'nine'),
    Shot('key-visual.png', '05  One hundred forty-nine', 149),
    Shot('06-99-to-101.png', '06  Add two from 99 to 101', 101, 'cross-hundred'),
    Shot('07-two-hundred-one.png', '07  Two hundred one', 201),
    Shot('08-maximum-reading-width.png', '08  Longest natural reading', 277),
    Shot('09-finale.png', '09  Finish at 299', 299, 'finale'),
)


def words(value: int) -> str:
    if not isinstance(value, int) or not 0 <= value <= 299:
        raise ValueError('Expected a decimal integer zero through 299')
    if value < 20:
        return ONE_TO_NINETEEN[value]
    if value < 100:
        return TENS[value // 10] + (f'-{ONE_TO_NINETEEN[value % 10]}' if value % 10 else '')
    return ONE_TO_NINETEEN[value // 100] + ' hundred' + (f' {words(value % 100)}' if value % 100 else '')


def checked_text(draw, text, center, size, color, field=None):
    bounds = centered_text_bounds(text, center, size)
    if field and not (field[0] <= bounds[0] <= bounds[2] <= field[2]
                      and field[1] <= bounds[1] <= bounds[3] <= field[3]):
        raise ValueError(f'Text outside its field: {text}: {bounds}, field={field}')
    place_text(draw, text, center, size, color)
    return {'text': text, 'font_size_px': size, 'ink_bounds_px': list(bounds)}


class RedPanda:
    def __init__(self, height=420, root=(1615, 950)):
        manifest = json.loads(CHARACTER.read_text(encoding='utf-8'))
        registration = manifest['render_registration']
        path = CHARACTER.with_name(registration['neutral_path'])
        if file_hash(path) != registration['neutral_sha256']:
            raise ValueError('Registered red panda source has changed')
        with Image.open(path) as source:
            source = source.convert('RGBA')
            scale = height / registration['neutral_natural_height_px']
            self.sprite = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
        self.position = tuple(round(origin - anchor * scale)
                              for origin, anchor in zip(root, registration['neutral_anchor_px'], strict=True))
        bbox = self.sprite.getchannel('A').point(lambda alpha: 255 if alpha >= 8 else 0).getbbox()
        visible = [bbox[0] + self.position[0], bbox[1] + self.position[1],
                   bbox[2] + self.position[0], bbox[3] + self.position[1]]
        if not (visible[0] > BOARD[2] + 24 and visible[2] < SIZE[0] - 24 and visible[3] < SIZE[1] - 24):
            raise ValueError(f'Red panda tail or body does not fit: {visible}')
        self.root = root
        self.metadata = {'pose': 'neutral', 'height_px': height, 'foot_root_px': list(root),
                         'scale': scale, 'position_px': list(self.position), 'visible_bbox_px': visible,
                         'source': path.relative_to(ROOT).as_posix(), 'source_sha256': file_hash(path),
                         'source_pixels_modified': False, 'mirrored': False, 'tail_retained': True,
                         'pose_scale_policy': 'Only neutral is used; natural body scale and anatomical support are fixed.'}

    def draw(self, image):
        shadow = Image.new('RGBA', SIZE)
        x, y = self.root
        ImageDraw.Draw(shadow).ellipse((x - 135, y - 5, x + 160, y + 20), fill=(76, 62, 43, 30))
        image.alpha_composite(shadow)
        image.alpha_composite(self.sprite, self.position)


def ticket(draw, center, top, width=88, height=30, extra=False):
    left = round(center - width / 2)
    box = (left, top, left + width, top + height)
    fill, edge = ('#f3cf91', '#ac7b37') if extra else ('#dce9dd', '#799884')
    rounded(draw, box, fill, edge, 2, 6)
    for side in (left, left + width):
        # Tiny pale side notches distinguish flat tickets from wooden blocks.
        draw.ellipse((side - 3, top + height / 2 - 3, side + 3, top + height / 2 + 3), fill='#f9f0dd')
    return {'bounds_px': list(box), 'counted_quantity': 1, 'extra': extra}


def draw_ticket_pairs(draw, quantity):
    if quantity not in (1, 5, 9):
        raise ValueError('Ticket illustrations cover one, five, and nine')
    pair_count = quantity // 2
    label = ('1 TICKET  ·  NO PARTNER' if quantity == 1 else
             f'{quantity} TICKETS  ·  {pair_count} PAIRS + 1')
    heading = checked_text(draw, label, (730, 713), 30, TEAL, TEACHING_FIELD)
    centers = (480, 750) if quantity == 5 else (330, 520, 710, 900) if quantity == 9 else ()
    tokens, groups = [], []
    for column, center in enumerate(centers):
        group = (center - 58, 740, center + 58, 839)
        rounded(draw, group, '#f3f2df', '#bac9ae', 2, 14)
        for row, y in enumerate((749, 797)):
            tokens.append({'column': column, 'row': row, **ticket(draw, center, y)})
        groups.append(list(group))
    center = 730 if quantity == 1 else 1040 if quantity == 5 else 1120
    tokens.append({'column': pair_count, 'row': None, **ticket(draw, center, 770, extra=True)})
    checked_text(draw, 'ONE LEFT OVER', (center, 831), 20, '#956a2e', TEACHING_FIELD)
    if len(tokens) != quantity:
        raise ValueError('Ticket diagram quantity is incorrect')
    return {'kind': 'odd-ticket-pairs', 'quantity': quantity, 'pairs': pair_count,
            'left_over': 1, 'tokens': tokens, 'pair_bounds_px': groups, 'label': heading}


def numberline(value):
    if value not in range(1, 300, 2):
        raise ValueError('Only the hundred fifty odd values 1–299 are counted')
    first = max(1, min(293, value - 3))
    return tuple(range(first, first + 7))


def draw_numberline(draw, value, finale=False):
    checked_text(draw, 'FINISHED AT 299' if finale else 'ODD STOPS  ·  ADD TWO',
                 (730, 878), 24, TEAL if finale else MUTED, (120, 861, 1340, 898))
    records = []
    for number, center in zip(numberline(value), CARD_CENTERS, strict=True):
        current, odd = number == value, number % 2 == 1
        box = (center - 65, CARD_BOX_Y[0], center + 65, CARD_BOX_Y[1])
        fill = '#cfe5d5' if current else '#eef2df' if odd else '#f4f0e6'
        edge = '#357d69' if current else '#b4c7ad' if odd else '#d7d1c4'
        color = TEAL if odd else '#aaa596'
        rounded(draw, box, fill, edge, 3 if current else 1, 16)
        text = checked_text(draw, str(number), (center, 955), 46, color, box)
        if current:
            draw.polygon(((center - 8, 902), (center + 8, 902), (center, 909)), fill=TEAL)
        records.append({'value': number, 'odd': odd, 'current': current,
                        'box_px': list(box), 'label': text})
    return {'values': list(numberline(value)), 'cards': records, 'current_value': value,
            'current_index': numberline(value).index(value), 'minimum': 1, 'maximum': 299}


def draw_hundred_bridge(draw, indicator=255):
    checked_text(draw, '99 + 2 = 101', (730, 709), 31, TEAL, TEACHING_FIELD)
    centers = (430, 730, 1030)
    cards = []
    for value, center in zip((99, 100, 101), centers, strict=True):
        even = value == 100
        box = (center - 95, 747, center + 95, 824)
        rounded(draw, box, '#f0eee4' if even else '#e1efdf', '#d8d1c2' if even else '#98b393', 2, 13)
        checked_text(draw, str(value), (center, 775), 42, '#aaa596' if even else TEAL, box)
        checked_text(draw, 'EVEN' if even else 'ODD', (center, 811), 15, '#aaa596' if even else TEAL, box)
        cards.append({'value': value, 'odd': not even, 'box_px': list(box)})
    progress = max(0, min(255, indicator)) / 255
    center = round(430 + 600 * (progress * progress * (3 - 2 * progress)))
    draw.polygon(((center - 9, 733), (center + 9, 733), (center, 744)), fill='#be8b3b')
    return {'kind': 'cross-hundred', 'equation': '99 + 2 = 101', 'cards': cards,
            'intervening_even_not_counted': 100, 'indicator_x_px': center}


def draw_teaching(draw, shot, indicator=255):
    rounded(draw, TEACHING_FIELD, '#f9f0dd', '#e1cfb2', 2, 21)
    if shot.state in ('single', 'five', 'nine'):
        return draw_ticket_pairs(draw, shot.value)
    if shot.state == 'cross-hundred':
        return draw_hundred_bridge(draw, indicator)
    if shot.state == 'finale':
        checked_text(draw, 'WE COUNTED FROM 1 TO 299', (650, 770), 32, TEAL, TEACHING_FIELD)
        stamp = (1145, 726, 1295, 820)
        rounded(draw, stamp, '#e1eddf', '#5c8e76', 3, 14)
        checked_text(draw, '299', (1220, 758), 37, TEAL, stamp)
        checked_text(draw, 'COMPLETE', (1220, 797), 15, TEAL, stamp)
        return {'kind': 'completed-ticket', 'stamp_bounds_px': list(stamp), 'stamp_value': 299}
    return {'kind': 'normal-instruction', 'label': checked_text(draw, 'START AT ONE  ·  ADD TWO',
                                                              (730, 770), 33, TEAL, TEACHING_FIELD)}


def render(background, character, shot, indicator=255):
    if shot.value not in range(1, 300, 2):
        raise ValueError('An odd frame cannot display an even count value')
    image = background.copy()
    character.draw(image)
    draw = ImageDraw.Draw(image)
    rounded(draw, (60, 39, 1400, 211), '#bba485', radius=31)
    rounded(draw, TITLE_BOX, CREAM, '#bba17d', 3, 31)
    title = [checked_text(draw, 'ODD NUMBERS', (730, 90), 70, INK, TITLE_BOX),
             checked_text(draw, '1–299  ·  COUNT BY TWOS', (730, 157), 32, TEAL, TITLE_BOX)]
    rounded(draw, (1450, 40, 1880, 121), '#bca88a', radius=24)
    rounded(draw, (1450, 35, 1880, 116), CREAM, '#bba17d', 2, 24)
    checked_text(draw, 'Num-Num Numbers', (1665, 76), 31, '#654268', (1450, 35, 1880, 116))
    rounded(draw, (60, 229, 1400, 1039), '#ae9979', radius=35)
    rounded(draw, BOARD, '#fffaf0', '#b69c78', 4, 35)
    header = 'ONE LEFT OVER' if shot.state in ('single', 'five', 'nine') else 'ODD NUMBER'
    checked_text(draw, header, (680, 270), 26, MUTED, (120, 242, 1100, 290))
    number = checked_text(draw, str(shot.value), NUMBER_CENTER, NUMBER_FONT_SIZE, INK, NUMBER_FIELD)
    badge = (1160, 383, 1335, 511)
    rounded(draw, badge, '#e1efe4', '#95b6a0', 3, 26)
    checked_text(draw, '+2', (1247, 447), 73, TEAL, badge)
    reading = checked_text(draw, words(shot.value), (730, 635), WORD_FONT_SIZE, TEAL, READING_FIELD)
    teaching = draw_teaching(draw, shot, indicator)
    trail = draw_numberline(draw, shot.value, shot.state == 'finale')
    return image.convert('RGB'), {'filename': shot.filename, 'caption': shot.caption,
                                 'state': shot.state, 'decimal_value': shot.value, 'spoken_text': words(shot.value),
                                 'title': title, 'number': number, 'reading': reading,
                                 'teaching': teaching, 'numberline': trail, 'character_pose': 'neutral'}


def validate_all_values():
    draw = ImageDraw.Draw(Image.new('RGB', SIZE))
    records = []
    for value in range(1, 300, 2):
        numeric = checked_text(draw, str(value), NUMBER_CENTER, NUMBER_FONT_SIZE, INK, NUMBER_FIELD)
        reading = checked_text(draw, words(value), (730, 635), WORD_FONT_SIZE, TEAL, READING_FIELD)
        values = numberline(value)
        if value not in values or any(not 1 <= number <= 299 for number in values):
            raise ValueError('Out-of-range ticket numberline')
        records.append({'decimal_value': value, 'spoken_text': words(value), 'number_ink_bounds_px': numeric['ink_bounds_px'],
                        'reading_ink_bounds_px': reading['ink_bounds_px'],
                        'reading_width_px': reading['ink_bounds_px'][2] - reading['ink_bounds_px'][0],
                        'numberline_values': list(values)})
    return {'all_values_checked': 150, 'start': 1, 'end': 299, 'step': 2,
            'fixed_number_size_px': NUMBER_FONT_SIZE, 'fixed_reading_size_px': WORD_FONT_SIZE,
            'maximum_reading_width': max(records, key=lambda item: item['reading_width_px']),
            'no_zero_300_or_301': True, 'values': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUTPUT)
    parser.add_argument('--background', type=Path, default=BACKGROUND)
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        raise FileExistsError('Choose a new reference version; existing images are never overwritten')
    validation = validate_all_values()
    with Image.open(args.background) as source:
        source_size = source.size
        background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
    panda = RedPanda()
    frames = [render(background, panda, shot) for shot in SHOTS]
    output.mkdir(parents=True)
    sheet = Image.new('RGB', (1800, 1290), '#f5eee0')
    draw = ImageDraw.Draw(sheet)
    checked_text(draw, 'Num-Num Numbers  /  Odd Numbers', (900, 47), 38, INK)
    shots = []
    for index, ((frame, record), shot) in enumerate(zip(frames, SHOTS, strict=True)):
        path = output / shot.filename
        frame.save(path)
        record['sha256'] = file_hash(path)
        x, y = 40 + index % 3 * 580, 110 + index // 3 * 380
        sheet.paste(frame.resize((560, 315), Image.Resampling.LANCZOS), (x, y))
        checked_text(draw, shot.caption, (x + 280, y + 346), 23, INK, (x - 5, y + 325, x + 565, y + 368))
        shots.append(record)
    sheet.save(output / 'storyboard.png')
    manifest = {'schema_version': 1, 'status': 'planning-only-static-stills-prepared', 'episode_id': 'odd-counting-001', 'revision_id': 'odd-counting-v002',
                'planning_only': True, 'measured_timeline_required_for_video': True,
                'theme': 'Mountain Cable Station', 'character': 'red-panda', 'frame_size_px': list(SIZE),
                'background': {'path': args.background.resolve().relative_to(ROOT).as_posix(),
                               'sha256': file_hash(args.background), 'source_size_px': list(source_size)},
                'renderer': Path(__file__).relative_to(ROOT).as_posix(), 'renderer_sha256': file_hash(Path(__file__)),
                'character_source_manifest': CHARACTER.relative_to(ROOT).as_posix(),
                'character_source_manifest_sha256': file_hash(CHARACTER), 'character_registration': panda.metadata,
                'panel_bounds_px': list(BOARD), 'number_field_px': list(NUMBER_FIELD),
                'reading_field_px': list(READING_FIELD), 'teaching_field_px': list(TEACHING_FIELD),
                'layout_validation': validation, 'shots': shots,
                'storyboard': {'path': 'storyboard.png', 'sha256': file_hash(output / 'storyboard.png')},
                'manual_review_pending': True}
    (output / 'reference-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'stills': len(shots), 'validation': validation['maximum_reading_width']}))


if __name__ == '__main__':
    main()
