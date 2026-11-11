"""Render the Starry Observatory hexadecimal preproduction stills."""

from dataclasses import dataclass
import json

from PIL import Image, ImageDraw, ImageOps

from render_binary_video import file_hash
from render_binary_video_v002 import DecimalSignScene
from render_octal_mockups import (
    CREAM, INK, MUTED, PEACH, ROOT, SIZE, TEAL,
    font, ink_bounds, place_text, rounded, two_line_shift,
)


BACKGROUND = ROOT / 'assets/library/worlds/starry-observatory/backgrounds/v001/starry-observatory-background.png'
CHARACTER = ROOT / 'assets/library/characters/tora/sources/v001/source-manifest.json'
OUTPUT = ROOT / 'assets/library/references/hexadecimal-counting/v001'
SYMBOLS = '0123456789ABCDEF'
WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
         'A', 'B', 'C', 'D', 'E', 'F')
WEIGHTS = (16, 1)
SLOT_CENTERS = (990, 1470)
READING_BASELINE = 751


class Tora:
    def __init__(self, height=600, root=(308, 870)):
        bundle = json.loads(CHARACTER.read_text(encoding='utf-8'))
        self.registration = bundle['render_registration']
        self.height = height
        self.root = root
        self.sprites = {}
        self.inputs = []
        for kind, field, digest in (
            ('neutral', 'neutral_path', 'neutral_sha256'),
            ('atlas', 'atlas_path', 'atlas_sha256'),
        ):
            path = CHARACTER.with_name(self.registration[field])
            if file_hash(path) != self.registration[digest]:
                raise ValueError(f'Existing Tora artwork changed: {path}')
            with Image.open(path) as source:
                setattr(self, kind, source.convert('RGBA'))
            self.inputs.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': file_hash(path)})

    def sprite(self, pose):
        if pose in self.sprites:
            return self.sprites[pose]
        if pose == 'neutral':
            source = self.neutral
            scale = self.height / self.registration['neutral_natural_height_px']
            anchor = self.registration['neutral_anchor_px']
            shift = (-anchor[0], -anchor[1])
        else:
            row = next(frame for frame in self.registration['frames'] if frame['id'] == pose)
            x, y, width, height = row['region_px']
            source = self.atlas.crop((x, y, x + width, y + height))
            scale = self.height / self.registration['atlas_natural_height_px']
            anchor = self.registration['atlas_anchor_px']
            shift = tuple(change - offset for change, offset in zip(row['translation_px'], anchor, strict=True))
        sprite = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
        position = tuple(round(origin + change * scale) for origin, change in zip(self.root, shift, strict=True))
        self.sprites[pose] = sprite, position
        return self.sprites[pose]

    def draw(self, image, pose):
        sprite, position = self.sprite(pose)
        image.alpha_composite(sprite, position)


@dataclass(frozen=True)
class Shot:
    filename: str
    caption: str
    value: int
    focus: int | None = None
    cue: str = ''
    pose: str = 'neutral'
    letter_table: bool = False
    transition: bool = False

    @property
    def hexadecimal(self):
        return format(self.value, 'X')


SHOTS = (
    Shot('01-letter-values.png', '01   Learn the letter values', 10, 0, 'A stands for ten', 'aha', True),
    Shot('02-zero.png', '02   Start counting at zero', 0, 0),
    Shot('03-nine-to-A.png', '03   Use A after 9', 9, transition=True),
    Shot('04-first-carry.png', '04   Carry from F to 10', 15, transition=True),
    Shot('05-read-10.png', '05   Read the zero in 10', 16, 1),
    Shot('key-visual.png', '06   Read 1A as one, A', 26, 1, 'Read each symbol from left to right'),
    Shot('07-paw-break.png', '07   Take a stretch break', 63, cue='Stretch break', pose='cheer'),
    Shot('08-regular-count.png', '08   Read six, eight', 104, 1),
    Shot('09-finale.png', '09   Finish at 7F', 127, cue='Great counting!', pose='aha'),
)


def draw_symbols(draw, shot):
    slots = shot.hexadecimal.rjust(2)
    for index, (symbol, weight, center) in enumerate(zip(slots, WEIGHTS, SLOT_CENTERS, strict=True)):
        active = shot.focus is not None and index == 2 - len(shot.hexadecimal) + shot.focus
        used = symbol != ' '
        new_place = shot.transition and shot.value == 15 and index == 0
        fill = '#aee5ce' if active else '#e5f2df' if used else '#f3eee3'
        edge = '#2e7e71' if active else '#94b79c' if used else '#d9d0c0'
        if new_place:
            fill, edge = PEACH, '#b27943'
        box = (center - 225, 315, center + 225, 574)
        rounded(draw, (box[0], 323, box[2], 582), '#e4d6c0', radius=30)
        rounded(draw, box, fill, edge, 5 if active or new_place else 2, 30)
        if used:
            place_text(draw, symbol, (center, 412), 144, INK)
        place_text(draw, str(weight), (center, 532), 34, TEAL if used else MUTED)
    place_text(draw, 'PLACE VALUE', (1230, 610), 23, MUTED)


def draw_reading(draw, shot):
    tokens = [WORDS[SYMBOLS.index(symbol)] for symbol in shot.hexadecimal]
    place_text(draw, 'READ ALOUD', (1230, 682), 25, MUTED)
    for index, token in enumerate(tokens):
        center = 1230 + 170 * (index - (len(tokens) - 1) / 2)
        active = index == shot.focus
        if active:
            rounded(draw, (center - 79, 712, center + 79, 768), '#d3eddf', radius=17)
        left, _, right, _ = ink_bounds(token, 43)
        draw.text((round(center - (left + right) / 2), READING_BASELINE), token,
                  font=font(43), fill=TEAL if active else INK, anchor='ls')


def draw_footer(draw, shot):
    if shot.letter_table:
        rounded(draw, (74, 912, 470, 943), CREAM, radius=11)
        place_text(draw, 'LETTER VALUES IN DECIMAL', (272, 928), 23, INK)
        for index, letter in enumerate('ABCDEF'):
            x = 74 + 298 * index
            active = letter == shot.hexadecimal
            rounded(draw, (x, 952, x + 282, 1045), '#999477', radius=22)
            rounded(draw, (x, 946, x + 282, 1039), '#e2f3e6' if active else CREAM,
                    '#357a67' if active else '#b5a48d', 4 if active else 2, 22)
            place_text(draw, letter, (x + 141, 974), 30, TEAL if active else INK)
            place_text(draw, str(index + 10), (x + 141, 1010), 27, INK)
        return
    rounded(draw, (74, 912, 280, 943), CREAM, radius=11)
    place_text(draw, 'IN THIS VIDEO', (177, 928), 24, INK)
    for index, span in enumerate(('0–F', '10–7F')):
        x = 74 + 894 * index
        active = len(shot.hexadecimal) == index + 1
        rounded(draw, (x, 952, x + 878, 1045), '#999477', radius=22)
        rounded(draw, (x, 946, x + 878, 1039), '#e2f3e6' if active else CREAM,
                '#357a67' if active else '#b5a48d', 4 if active else 2, 22)
        title = '1 digit' if index == 0 else '2 digits'
        top = ink_bounds(title, 27)
        bottom = ink_bounds(span, 25)
        shift = two_line_shift(992.5, 975, top[3] - top[1], 1010, bottom[3] - bottom[1])
        place_text(draw, title, (x + 439, 975 + shift), 27, TEAL if active else INK)
        place_text(draw, span, (x + 439, 1010 + shift), 25, INK)


def render(background, character, shot):
    if not 0 <= shot.value <= 127:
        raise ValueError('The preproduction stills cover decimal 0 through 127')
    image = background.copy()
    shadow = Image.new('RGBA', SIZE)
    ImageDraw.Draw(shadow).ellipse((115, 860, 535, 908), fill=(63, 60, 97, 56))
    image.alpha_composite(shadow)
    sign_pose = 'seated_stretch' if shot.pose == 'cheer' else 'wave_2' if shot.pose == 'aha' else 'neutral'
    DecimalSignScene.sign_support(image, sign_pose)
    character.draw(image, shot.pose)
    DecimalSignScene.draw_decimal_sign(image, shot.value, sign_pose)
    draw = ImageDraw.Draw(image)

    rounded(draw, (55, 24, 422, 95), CREAM, '#c9a984', 2, 25)
    place_text(draw, 'Num-Num Numbers', (238, 60), 31, '#654268')
    rounded(draw, (790, 45, 1670, 174), '#bda88d', radius=37)
    rounded(draw, (790, 36, 1670, 165), CREAM, '#b9a386', 3, 37)
    place_text(draw, 'HEXADECIMAL COUNT', (1230, 85), 44, INK)
    place_text(draw, '0–7F  IN BASE 16', (1230, 132), 27, TEAL)
    rounded(draw, (610, 224, 1850, 817), '#a68965', radius=44)
    rounded(draw, (610, 212, 1850, 805), CREAM, '#b99464', 6, 44)
    rounded(draw, (620, 222, 1840, 795), None, '#ead5ac', 2, 36)
    place_text(draw, 'BASE 16', (1230, 268), 39, INK)
    draw_symbols(draw, shot)
    draw.line((666, 643, 1794, 643), fill='#d8c6a7', width=2)
    draw_reading(draw, shot)
    cue = shot.cue
    if shot.transition:
        cue = f'{shot.hexadecimal} + 1  =  {shot.value + 1:X}   (BASE 16)'
    if cue:
        rounded(draw, (662, 835, 1798, 904), PEACH if shot.transition else CREAM,
                '#c6955e' if shot.transition else '#b5a48d', 2, 23)
        place_text(draw, cue, (1230, 869), 34, INK if shot.transition else TEAL)
    draw_footer(draw, shot)
    return image.convert('RGB')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with Image.open(BACKGROUND) as source:
        background_size = source.size
        background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
    tora = Tora()
    frames = [render(background, tora, shot) for shot in SHOTS]
    sheet = Image.new('RGB', (1720, 1364), '#f5eee0')
    draw = ImageDraw.Draw(sheet)
    place_text(draw, 'Num-Num Numbers  /  Hexadecimal Count', (860, 61), 40, INK)
    rows = []
    for index, (shot, frame) in enumerate(zip(SHOTS, frames, strict=True)):
        path = OUTPUT / shot.filename
        frame.save(path)
        x, y = 50 + (index % 3) * 550, 114 + (index // 3) * 406
        rounded(draw, (x - 3, y - 3, x + 522, y + 295), '#b59b7c', radius=6)
        sheet.paste(frame.resize((520, 293), Image.Resampling.LANCZOS), (x, y))
        place_text(draw, shot.caption, (x + 260, y + 324), 25, INK)
        rows.append({'path': shot.filename, 'caption': shot.caption,
                     'display_hexadecimal': shot.hexadecimal, 'decimal_sign': shot.value,
                     'reading_tokens': [WORDS[SYMBOLS.index(s)] for s in shot.hexadecimal],
                     'highlighted_token_index': shot.focus, 'pose': shot.pose,
                     'next_hexadecimal': format(shot.value + 1, 'X') if shot.transition else None,
                     'sha256': file_hash(path)})
    sheet.save(OUTPUT / 'storyboard.png')
    manifest = {
        'status': 'prepared-for-user-review', 'series': 'Num-Num Numbers',
        'theme': 'Starry Observatory', 'character': 'tora', 'character_source_manifest': CHARACTER.relative_to(ROOT).as_posix(),
        'character_source_manifest_sha256': file_hash(CHARACTER), 'character_artwork': tora.inputs,
        'character_artwork_generated_for_this_episode': False,
        'renderer': 'tools/render_hexadecimal_mockups.py', 'frame_size_px': SIZE,
        'background': {'path': BACKGROUND.relative_to(ROOT).as_posix(), 'size_px': background_size,
                       'sha256': file_hash(BACKGROUND),
                       'generation_record': BACKGROUND.with_name('generation-record.json').relative_to(ROOT).as_posix()},
        'place_weights': WEIGHTS, 'reading_layout': 'common-baseline', 'reading_baseline_y_px': READING_BASELINE,
        'shots': rows, 'storyboard': {'path': 'storyboard.png', 'size_px': sheet.size,
                                    'sha256': file_hash(OUTPUT / 'storyboard.png')},
    }
    (OUTPUT / 'reference-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
