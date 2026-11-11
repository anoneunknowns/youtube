"""Render the octal preproduction stills and storyboard."""

import argparse
from dataclasses import dataclass
from functools import lru_cache
import json

from PIL import Image, ImageDraw, ImageOps

from render_binary_video import ROOT, SIZE, file_hash, font, rounded
from render_binary_video_v002 import DecimalSignScene, sign_geometry
from render_counting_video import Bear


THEMES = {
    'aurora-garden': ('Aurora Garden', 'aurora-garden', 'v002', 'v004'),
    'aurora-garden-lapland-bear': ('Aurora Garden', 'aurora-garden', 'v002', 'v003'),
    'aurora-garden-v001': ('Aurora Garden', 'aurora-garden', 'v001', 'v002'),
    'eight-step-garden': ('Eight-Step Garden', 'eight-step-garden', 'v001', 'v001'),
}
RABBIT_REGISTRATION = ROOT / 'assets/library/characters/rabbit-beret/sources/v001/registration.json'
WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven')
WEIGHTS = (64, 8, 1)
RANGES = ('0–7', '10–77', '100–177')
INK = '#51341f'
MUTED = '#756352'
TEAL = '#205b57'
CREAM = '#fff8e8'
PEACH = '#ffead0'


@dataclass(frozen=True)
class Shot:
    filename: str
    caption: str
    value: int
    cue: str = ''
    focus: int | None = None
    carry: bool = False
    pose: str = 'neutral'

    @property
    def octal(self) -> str:
        return format(self.value, 'o')


SHOTS = (
    Shot('01-intro.png', '01   Introduce base eight', 10, 'Read each digit from left to right', 0, pose='wave_2'),
    Shot('02-zero.png', '02   Start counting', 0, 'Use the digits 0 through 7', 0),
    Shot('03-first-carry.png', '03   Carry from 7 to 10', 7, carry=True),
    Shot('04-stretch.png', '04   Stretch break', 31, 'Stretch break', pose='seated_stretch'),
    Shot('05-second-carry.png', '05   Carry from 77 to 100', 63, carry=True),
    Shot('06-read-100.png', '06   Read the zeros in 100', 64, focus=1),
    Shot('key-visual.png', '07   Read a three-digit number', 83, focus=1),
    Shot('08-finale.png', '08   Finish at 177', 127, 'Great counting!', pose='wave_3'),
)


class Rabbit:
    def __init__(self, registration_path):
        registration = json.loads(registration_path.read_text(encoding='utf-8'))
        self.path = registration_path
        self.sheet_path = registration_path.with_name(registration['sheet'])
        self.sheet_sha256 = file_hash(self.sheet_path)
        if self.sheet_sha256 != registration['sheet_sha256']:
            raise ValueError('Rabbit sprite sheet does not match its registration')
        self.sprites = {}
        scale = registration['scale']
        screen_x, screen_y = registration['screen_anchor_px']
        with Image.open(self.sheet_path) as sheet:
            if sheet.mode != 'RGBA' or list(sheet.size) != registration['sheet_size_px']:
                raise ValueError('Rabbit sprite sheet requires its registered size and alpha channel')
            for name, pose in registration['frames'].items():
                crop = sheet.crop(pose['crop_xyxy'])
                left, top, _, _ = pose['crop_xyxy']
                x, y = pose['anchor_xy']
                sprite = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
                self.sprites[name] = (sprite, (round(screen_x - (x - left) * scale),
                                               round(screen_y - (y - top) * scale)))

    @staticmethod
    def pose_name(pose):
        return 'wave' if pose.startswith('wave_') else pose

    def draw(self, frame, pose):
        sprite, position = self.sprites[self.pose_name(pose)]
        frame.alpha_composite(sprite, position)

    @staticmethod
    def draw_grips(frame, pose):
        draw = ImageDraw.Draw(frame)
        for index, box in enumerate(sign_geometry(pose)['grip_paw_bboxes']):
            left, top, _, _ = box
            draw.ellipse(box, fill='#fac5ce', outline='#70420e', width=7)
            x = left + (17 if index == 0 else 4)
            angles = (275, 80) if index == 0 else (100, 265)
            draw.arc((x, top + 15, x + 17, top + 42), *angles, fill='#b87074', width=3)


@lru_cache(maxsize=64)
def ink_bounds(text, size):
    mask, (x, y) = font(size).getmask2(text, mode='L')
    left, top, right, bottom = mask.getbbox()
    return left + x, top + y, right + x, bottom + y


def ink_height(text, size):
    _, top, _, bottom = ink_bounds(text, size)
    return bottom - top


def place_text(draw, text, center, size, color):
    """Center the visible ink so ascenders and descenders keep equal padding."""
    left, top, right, bottom = ink_bounds(text, size)
    x, y = center
    draw.text((round(x - (left + right) / 2), round(y - (top + bottom) / 2)),
              text, font=font(size), fill=color)


def two_line_shift(field_center, top_y, top_height, bottom_y, bottom_height):
    return field_center - ((top_y - top_height / 2) + (bottom_y + bottom_height / 2)) / 2


def draw_digits(draw, shot):
    slots = shot.octal.rjust(3)
    next_place = len(slots) - len(shot.octal) - 1 if shot.carry else None
    for index, (digit, weight) in enumerate(zip(slots, WEIGHTS, strict=True)):
        x = 687 + index * 370
        current = shot.focus is not None and index == len(slots) - len(shot.octal) + shot.focus
        used = digit != ' '
        fill = '#aee5ce' if current else '#e5f2df' if used else '#f3eee3'
        edge = '#2e7e71' if current else '#94b79c' if used else '#d9d0c0'
        if index == next_place:
            fill, edge = PEACH, '#b27943'
        rounded(draw, (x, 323, x + 346, 582), '#e4d6c0', radius=30)
        rounded(draw, (x, 315, x + 346, 574), fill, edge, 5 if current or index == next_place else 2, 30)
        if used:
            place_text(draw, digit, (x + 173, 412), 140, INK)
        weight_color = INK if index == next_place else TEAL if used else MUTED
        place_text(draw, str(weight), (x + 173, 532), 34, weight_color)
    place_text(draw, 'PLACE VALUE', (1230, 610), 23, MUTED)


def draw_legacy_reading(draw, shot):
    words = [WORDS[int(digit)] for digit in shot.octal]
    widths = [round(font(43).getlength(word)) + 42 for word in words]
    gap = 12
    x = (2460 - sum(widths) - gap * (len(words) - 1)) / 2
    label = 'READ ALOUD'
    label_y, word_y = 683, 748
    shift = two_line_shift(719.5, label_y, ink_height(label, 25),
                           word_y, max(ink_height(word, 43) for word in words))
    place_text(draw, label, (1230, label_y + shift), 25, MUTED)
    for index, (word, width) in enumerate(zip(words, widths, strict=True)):
        if index == shot.focus:
            rounded(draw, (x, word_y + shift - 33, x + width, word_y + shift + 33), '#d3eddf', radius=21)
        place_text(draw, word, (x + width / 2, word_y + shift), 43, TEAL if index == shot.focus else INK)
        x += width + gap


def draw_reading(draw, shot):
    words = [WORDS[int(digit)] for digit in shot.octal]
    word_font = font(43)
    # Keep the ink and the active badge balanced around the field's center.
    place_text(draw, 'READ ALOUD', (1230, 680), 25, MUTED)
    for index, word in enumerate(words):
        center = 1230 + 170 * (index - (len(words) - 1) / 2)
        active = index == shot.focus
        if active:
            rounded(draw, (center - 79, 727, center + 79, 771), '#d3eddf', radius=17)
        left, _, right, _ = ink_bounds(word, 43)
        draw.text((round(center - (left + right) / 2), 765), word, font=word_font,
                  fill=TEAL if active else INK, anchor='ls')


def draw_ranges(draw, width, footer_badge):
    if footer_badge:
        rounded(draw, (74, 912, 280, 943), CREAM, radius=11)
    place_text(draw, 'IN THIS VIDEO', (177, 928), 24, INK)
    for index, span in enumerate(RANGES):
        x = 74 + index * 596
        current = index + 1 == width
        rounded(draw, (x, 952, x + 580, 1045), '#999477', radius=22)
        rounded(draw, (x, 946, x + 580, 1039), '#e2f3e6' if current else CREAM,
                '#357a67' if current else '#b5a48d', 4 if current else 2, 22)
        unit = 'digit' if index == 0 else 'digits'
        label = f'{index + 1} {unit}'
        shift = two_line_shift(992.5, 975, ink_height(label, 27), 1010, ink_height(span, 25))
        place_text(draw, label, (x + 290, 975 + shift), 27, TEAL if current else INK)
        place_text(draw, span, (x + 290, 1010 + shift), 25, INK)


def render(background, character, shot, footer_badge=False, *, legacy_reading_layout=True):
    frame = background.copy()
    shadow = Image.new('RGBA', SIZE)
    ImageDraw.Draw(shadow).ellipse((142, 860, 477, 908), fill=(72, 100, 54, 64))
    frame.alpha_composite(shadow)
    DecimalSignScene.sign_support(frame, shot.pose)
    rabbit = isinstance(character, Rabbit)
    if rabbit:
        character.draw(frame, shot.pose)
    else:
        character.draw(frame, [(shot.pose, 1)])
    DecimalSignScene.draw_decimal_sign(frame, shot.value, shot.pose)
    if rabbit:
        character.draw_grips(frame, shot.pose)

    draw = ImageDraw.Draw(frame)
    rounded(draw, (65, 57, 502, 132), CREAM, '#c9a984', 2, 26)
    place_text(draw, 'Num-Num Numbers', (283, 95), 36, '#654268')
    rounded(draw, (904, 45, 1556, 174), '#bda88d', radius=37)
    rounded(draw, (904, 36, 1556, 165), CREAM, '#b9a386', 3, 37)
    place_text(draw, 'OCTAL COUNT', (1230, 85), 49, INK)
    place_text(draw, '0–177  IN BASE 8', (1230, 132), 27, TEAL)

    rounded(draw, (610, 224, 1850, 817), '#a68965', radius=44)
    rounded(draw, (610, 212, 1850, 805), CREAM, '#b99464', 6, 44)
    rounded(draw, (620, 222, 1840, 795), None, '#ead5ac', 2, 36)
    place_text(draw, 'BASE 8', (1230, 268), 39, INK)
    draw_digits(draw, shot)
    draw.line((666, 643, 1794, 643), fill='#d8c6a7', width=2)
    if legacy_reading_layout:
        draw_legacy_reading(draw, shot)
    else:
        draw_reading(draw, shot)

    if shot.carry or shot.cue:
        cue = f'{shot.octal} + 1  =  {shot.value + 1:o}   (BASE 8)' if shot.carry else shot.cue
        rounded(draw, (662, 835, 1798, 904), PEACH if shot.carry else CREAM,
                '#c6955e' if shot.carry else '#b5a48d', 2, 23)
        place_text(draw, cue, (1230, 869), 34, INK if shot.carry else TEAL)
    draw_ranges(draw, len(shot.octal), footer_badge)
    return frame.convert('RGB')


def storyboard(frames):
    sheet = Image.new('RGB', (1720, 1364), '#f5eee0')
    draw = ImageDraw.Draw(sheet)
    place_text(draw, 'Num-Num Numbers  /  Octal Count', (860, 61), 45, INK)
    for index, (shot, frame) in enumerate(zip(SHOTS, frames, strict=True)):
        column, row = index % 3, index // 3
        x = 50 + column * 550 if row < 2 else 325 + column * 550
        y = 114 + row * 406
        thumbnail = frame.resize((520, 293), Image.Resampling.LANCZOS)
        rounded(draw, (x - 3, y - 3, x + 522, y + 295), '#b59b7c', radius=6)
        sheet.paste(thumbnail, (x, y))
        place_text(draw, shot.caption, (x + 260, y + 324), 26, INK)
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--theme', choices=THEMES, default='aurora-garden')
    args = parser.parse_args()
    theme, world, background_version, reference_version = THEMES[args.theme]
    world_path = ROOT / 'assets/library/worlds' / world
    background_path = world_path / 'backgrounds' / background_version / f'{world}-background.png'
    output = ROOT / 'assets/library/references/octal-counting' / reference_version

    output.mkdir(parents=True, exist_ok=True)
    with Image.open(background_path) as source:
        background_size = source.size
        background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
    use_rabbit = args.theme == 'aurora-garden'
    character = Rabbit(RABBIT_REGISTRATION) if use_rabbit else Bear(547.26, (308, 870))
    footer_badge = background_version == 'v002'
    frames = [render(background, character, shot, footer_badge) for shot in SHOTS]
    for shot, frame in zip(SHOTS, frames, strict=True):
        frame.save(output / shot.filename)
    sheet = storyboard(frames)
    sheet.save(output / 'storyboard.png')
    manifest = {
        'status': 'prepared-for-user-review',
        'series': 'Num-Num Numbers',
        'theme': theme,
        'renderer': 'tools/render_octal_mockups.py',
        'background': {
            'path': background_path.relative_to(ROOT).as_posix(),
            'size_px': background_size,
            'sha256': file_hash(background_path),
            'generation_record': background_path.with_name('generation-record.json').relative_to(ROOT).as_posix(),
        },
        'frame_size_px': SIZE,
        'place_weights': WEIGHTS,
        'shots': [
            {
                'path': shot.filename,
                'caption': shot.caption,
                'octal': shot.octal,
                'decimal_sign': shot.value,
                'spoken_words': [WORDS[int(digit)] for digit in shot.octal],
                'highlighted_word_index': shot.focus,
                'carry_to_octal': format(shot.value + 1, 'o') if shot.carry else None,
                'pose': Rabbit.pose_name(shot.pose) if use_rabbit else shot.pose,
                'sha256': file_hash(output / shot.filename),
            }
            for shot in SHOTS
        ],
        'storyboard': {
            'path': 'storyboard.png',
            'size_px': sheet.size,
            'sha256': file_hash(output / 'storyboard.png'),
        },
    }
    if use_rabbit:
        manifest['character'] = {
            'id': 'rabbit-beret-poses-v001',
            'registration': character.path.relative_to(ROOT).as_posix(),
            'registration_sha256': file_hash(character.path),
            'sprite_sheet': character.sheet_path.relative_to(ROOT).as_posix(),
            'sprite_sheet_sha256': character.sheet_sha256,
        }
    else:
        manifest['bear'] = 'assets/library/characters/bear-beret/references/canonical-neutral-v001.png'
    (output / 'reference-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
