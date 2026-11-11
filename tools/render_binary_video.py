"""Render the measured binary episode using the registered first-episode artwork.

The numeric row changes atomically. Spoken bits highlight left to right; a
separate cue strip shows carry direction only outside digit speech.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    from render_counting_video import Bear, Segment, encode, find_ffmpeg
except ModuleNotFoundError:
    from tools.render_counting_video import Bear, Segment, encode, find_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
FPS = 30
CREAM = (255, 245, 221)
INK = (86, 55, 24)
TEAL = (37, 125, 140)
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BACKGROUND = ROOT / 'assets/library/worlds/binary-lantern-garden/backgrounds/v001/lantern-garden-background.png'
WEIGHTS = (64, 32, 16, 8, 4, 2, 1)
RANGES = ('0–1', '10–11', '100–111', '1000–1111', '10000–11111', '100000–111111', '1000000–1111111')


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def source_receipts():
    paths = [BACKGROUND, FONT,
             ROOT/'assets/library/characters/bear-beret/references/canonical-neutral-v001.png']
    directory = ROOT/'assets/library/characters/bear-beret/sources/v001'
    paths.extend(directory/name for name in ('reactions-v2.png', 'playful-v1.png',
                                            'reactions-registration-v4.json', 'idle-registration-v1.json'))
    for kind, sheet in (('wave', 'wave-sheet.png'), ('postures', 'postures-sheet.png')):
        directory = ROOT/f'assets/library/characters/bear-beret/animations/{kind}/v001'
        paths.extend((directory/sheet, directory/'registration.json'))
    return [{'path':path.relative_to(ROOT).as_posix(), 'sha256':file_hash(path)} for path in paths]


@lru_cache(maxsize=32)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def text_center(draw, text, center, size, fill=INK):
    face = font(size)
    box = draw.textbbox((0, 0), text, font=face)
    xy = (center[0] - (box[0] + box[2]) / 2, center[1] - (box[1] + box[3]) / 2)
    draw.text(xy, text, font=face, fill=fill)
    return [xy[0] + box[0], xy[1] + box[1], xy[0] + box[2], xy[1] + box[3]]


def fit_size(draw, text, maximum, width):
    for size in range(maximum, 11, -1):
        if draw.textbbox((0, 0), text, font=font(size))[2] <= width:
            return size
    raise ValueError(f'Text cannot fit safe area: {text}')


def rounded(draw, box, fill, outline=None, width=1, radius=24):
    draw.rounded_rectangle(tuple(round(v) for v in box), radius=radius, fill=fill, outline=outline, width=width)


class BinaryTimeline:
    def __init__(self, plan):
        self.plan = plan
        self.duration = float(plan['duration_s'])
        if not math.isfinite(self.duration) or self.duration <= 0:
            raise ValueError('Timeline duration must be finite and positive')
        if plan.get('fps', FPS) != FPS:
            raise ValueError('Binary delivery uses 30fps')
        self.events = plan['events']
        self.counts = sorted((e for e in self.events if e['type'] == 'count'), key=lambda e: e['start_s'])
        values = [e.get('decimal_value', e.get('number')) for e in self.counts]
        if values != list(range(128)):
            raise ValueError('Binary timeline must show all 128 states in order, including zero')
        self.starts = [float(e['start_s']) for e in self.counts]
        if any(a >= b for a, b in zip(self.starts, self.starts[1:])):
            raise ValueError('Count starts must strictly increase')
        self.by_type = {}
        for event in self.events:
            self.by_type.setdefault(event['type'], []).append(event)
            a, b = float(event['start_s']), float(event['end_s'])
            if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= self.duration + 1e-6):
                raise ValueError(f'Event outside timeline: {event.get("id", event["type"])}')
        self.digits = self.by_type.get('digit_voice', [])
        for value, row in enumerate(self.counts):
            if row['display_binary'] != format(value, 'b'):
                raise ValueError(f'Incorrect displayed binary value: {value}')
            nested = row.get('bit_events') or [e for e in self.digits if e['decimal_value'] == value]
            if len(nested) != len(row['display_binary']):
                raise ValueError(f'Missing digit speech events: {value}')
            for index, (event, bit) in enumerate(zip(nested, row['display_binary'])):
                if (event['bit_index'] != index or event['slot_index'] != 7 - len(nested) + index
                        or event['token'] != ('one' if bit == '1' else 'zero')):
                    raise ValueError(f'Digit event/display mismatch: {value}/{index}')
            row['bit_events'] = nested
        self.finale = next(iter(self.by_type.get('finale', [])), None)

    def count_at(self, seconds):
        index = bisect_right(self.starts, seconds) - 1
        return self.counts[index] if index >= 0 else None

    def active(self, event_type, seconds):
        return next((e for e in self.by_type.get(event_type, []) if e['start_s'] <= seconds < e['end_s']), None)

    def focus_at(self, row, seconds):
        return next((e['bit_index'] for e in row['bit_events'] if e['start_s'] <= seconds < e['end_s']), None)


class BinaryScene:
    def __init__(self, timeline):
        self.timeline = timeline
        self.duration = timeline.duration
        self.bear = Bear(547.26, (308.0, 870.0))
        self.background = ImageOps.fit(Image.open(BACKGROUND).convert('RGB'), SIZE, method=Image.Resampling.LANCZOS)
        # Match the lightly washed static composition; retain the original PNG.
        self.background = Image.blend(self.background, Image.new('RGB', SIZE, (229, 232, 255)), .045)
        self.cream = Image.new('RGB', SIZE, CREAM)
        self._last_key = None
        self._last_frame = None

    def state(self, seconds):
        row = self.timeline.count_at(seconds)
        pause = self.timeline.active('pause', seconds)
        carry = self.timeline.active('carry', seconds)
        dialogue = self.timeline.active('dialogue', seconds)
        finale = self.timeline.active('finale', seconds)
        if row is None:
            number, focus, mode = 2, None, 'intro'
        else:
            number = int(row.get('decimal_value', row['number']))
            focus = self.timeline.focus_at(row, seconds)
            mode = 'zero' if number == 0 else 'normal'
        if pause:
            mode = 'stretch' if pause['kind'] == 'stretch' else 'place'
        if finale:
            mode = 'finale'
        # During carry, the main numeric row stays on the previous valid state.
        # No right-to-left highlight can be mistaken for spoken left-to-right bits.
        if carry and focus is not None:
            raise ValueError('Carry animation overlaps spoken digit')
        return {'number': number, 'focus': focus, 'mode': mode, 'pause': pause,
                'carry': carry, 'dialogue': dialogue, 'finale': finale}

    def pose(self, seconds, state):
        pause = state['pause']
        if pause and pause['kind'] == 'stretch':
            age, length = seconds - pause['start_s'], pause['end_s'] - pause['start_s']
            if 1.45 <= age < 1.9:
                return 'half_seated'
            if 1.9 <= age < max(2.0, length - 2.5):
                return 'seated_stretch' if age < length - 3.0 else 'seated_neutral'
            if length - 2.5 <= age < length - 1.8:
                return 'half_seated'
        if state['mode'] == 'place':
            return 'think'
        finale = state['finale']
        if finale:
            age, length = seconds - finale['start_s'], finale['end_s'] - finale['start_s']
            if 1.0 <= age < 1.9:
                return 'cheer' if int(age * 5) % 2 else 'success_ready'
            if max(3, length - 6) <= age < length - 1.2:
                return self.bear.wave_pose((age - max(3, length - 6)) % 1.2)
        if state['mode'] == 'intro' and .9 <= seconds < 2.1:
            return self.bear.wave_pose(seconds - .9)
        if state['mode'] == 'intro' and 9.0 <= seconds < 11.3:
            return 'think'
        return 'blink' if seconds > 3 and 2.8 <= seconds % 5.7 < 2.96 else 'neutral'

    @lru_cache(maxsize=20)
    def composition(self, number, focus, mode):
        frame = self.background.copy()
        draw = ImageDraw.Draw(frame)
        draw.text((65, 40), 'Num-Num Numbers', font=font(38), fill=(118, 82, 160))
        rounded(draw, (65, 99, 150, 106), '#eec764', radius=4)
        rounded(draw, (890, 46, 1570, 163), '#aaa0bd', radius=42)
        rounded(draw, (890, 39, 1570, 156), '#fff9ee', '#b6a3cc', 5, 42)
        text_center(draw, 'BINARY COUNT', (1230, 82), 38)
        text_center(draw, '0 → 1111111₂', (1230, 126), 27, '#7a5c85')
        tags = {'intro': 'HOW TO READ', 'zero': 'START WITH ZERO', 'place': 'A NEW PLACE',
                'stretch': "LET'S STRETCH", 'finale': 'SEVEN PLACES'}
        if mode in tags:
            label = tags[mode]
            w = draw.textlength(label, font=font(26)) + 54
            rounded(draw, (1230-w/2, 176, 1230+w/2, 220), '#fffdf1', '#cadad9', 3, 22)
            text_center(draw, label, (1230, 198), 26, '#356c79')
        draw.ellipse((180, 866, 450, 900), fill='#a8a9b0')
        rounded(draw, (610, 240, 1850, 820), '#a09591', radius=48)
        rounded(draw, (610, 228, 1850, 808), '#fff8ea', '#b88d56', 8, 48)
        rounded(draw, (620, 238, 1840, 798), None, '#ffe5ad', 4, 38)
        text_center(draw, 'BINARY', (1230, 285), 34)
        bits = format(number, 'b')
        width, gap, cell_y, cell_h = (1160-14*6)/7, 14, 330, 234
        for slot, weight in enumerate(WEIGHTS):
            index = slot - (7-len(bits))
            used = index >= 0
            bit = bits[index] if used else None
            x = 650 + slot*(width+gap)
            border = '#d7a13a' if bit == '1' else '#baadd0' if used else '#ddd4dd'
            fill = '#ffd15d' if bit == '1' else '#ddd5ef' if used else '#f6f0e7'
            rounded(draw, (x, cell_y+6, x+width, cell_y+cell_h+6), '#e8dfd6', radius=29)
            rounded(draw, (x, cell_y, x+width, cell_y+cell_h), fill, border, 4 if used else 2, 29)
            if used:
                # The visible glyph, rather than font metrics, is centered.
                text_center(draw, bit, (x+width/2, 426), 116, '#573411')
            if mode != 'intro':
                text_center(draw, str(weight), (x+width/2, 529), 30, '#69523f' if used else '#cfc4ca')
            if used and index == focus:
                rounded(draw, (x-10, cell_y-10, x+width+10, cell_y+cell_h+10), None, TEAL, 7, 36)
        if mode != 'intro':
            text_center(draw, 'PLACE VALUE', (1230, 590), 20, '#8a7463')
        draw.line((658, 622, 1802, 622), fill='#d7c7aa', width=3)
        label = 'EVERYDAY NUMBER · DECIMAL' if mode == 'intro' else 'DECIMAL'
        labelw = draw.textlength(label, font=font(27))
        valuew = draw.textlength(str(number), font=font(49))
        total = labelw+20+valuew
        text_center(draw, label, (1230-total/2+labelw/2, 671), 27, '#806c55')
        text_center(draw, str(number), (1230+total/2-valuew/2, 671), 49)
        tokens = [('one' if b == '1' else 'zero') for b in bits]
        if mode == 'stretch':
            text_center(draw, "Let's stretch!", (1230, 745), 32)
        else:
            widths = [draw.textlength(token, font=font(32))+12 for token in tokens]
            total = sum(widths)+9*(len(tokens)-1)+70
            x = 1230-total/2
            text_center(draw, 'Say:', (x+28, 745), 28, '#826a53')
            x += 70
            for index, (token, width_token) in enumerate(zip(tokens, widths)):
                if index == focus:
                    rounded(draw, (x, 718, x+width_token, 772), '#d5edeb', radius=12)
                    draw.line((x+7, 768, x+width_token-7, 768), fill='#64a9af', width=4)
                text_center(draw, token, (x+width_token/2, 745), 32, '#236575' if index == focus else INK)
                x += width_token+9
        captions = {'intro': 'Read each digit from left to right.', 'zero': 'Zero is off. One is on.',
                    'stretch': 'Take a little counting break.', 'finale': 'Seven places, all ones!'}
        if mode in captions:
            caption = captions[mode]
            w = draw.textlength(caption, font=font(31))+50
            rounded(draw, (1230-w/2, 830, 1230+w/2, 886), '#fffaf0', radius=23)
            text_center(draw, caption, (1230, 858), 31)
        elif mode != 'place':
            for x, bit, name in ((1020, '0', 'OFF'), (1270, '1', 'ON')):
                rounded(draw, (x, 832, x+216, 886), '#fffaf0', radius=20)
                rounded(draw, (x+20, 845, x+49, 874), '#ddd5ef' if bit=='0' else '#ffcf58', '#a497b5', 3, 9)
                text_center(draw, f'{bit} {name}', (x+126, 858), 27)
        draw.text((74, 900), 'BINARY RANGES', font=font(22), fill='#665275')
        pw = (1772-18*6)/7
        for index, value_range in enumerate(RANGES):
            x = 74+index*(pw+18)
            active = index+1 == len(bits)
            rounded(draw, (x, 941, x+pw, 1052), '#bdb2b8', radius=24)
            rounded(draw, (x, 935, x+pw, 1046), '#fff1bd' if active else '#fff8ee', '#337f88' if active else '#a695b6', 5 if active else 3, 24)
            if active:
                rounded(draw, (x+pw/2-18, 935, x+pw/2+18, 941), TEAL, radius=3)
            text_center(draw, f'{index+1} {"digit" if index==0 else "digits"}', (x+pw/2, 971), 28, '#286a73' if active else '#6a526d')
            text_center(draw, value_range, (x+pw/2, 1010), 22, '#6c4f32')
        return frame

    def carry_strip(self, frame, carry, seconds):
        draw = ImageDraw.Draw(frame)
        source = carry.get('from_binary', format(carry['from_decimal'], 'b'))
        target = carry.get('to_binary', format(carry['to_decimal'], 'b'))
        label = f'{source} + 1 → {target}'
        size = fit_size(draw, label, 33, 1060)
        rounded(draw, (670, 823, 1790, 893), '#fffaf0', '#c4b89c', 2, 22)
        text_center(draw, label, (1230, 844), size)
        # Separate tiny markers progress from the rightmost addend to the left.
        steps = min(7, len(source)+1)
        u = (seconds-carry['start_s'])/(carry['end_s']-carry['start_s'])
        active = min(steps-1, int(u*steps))
        for index in range(steps):
            x = 1305-index*25
            draw.ellipse((x-5, 875, x+5, 885), fill=TEAL if index==active else '#d9d1bd')

    def checkpoint_effect(self, frame, checkpoint, seconds):
        if checkpoint is None:
            return
        age = seconds-checkpoint['start_s']
        duration = checkpoint['end_s']-checkpoint['start_s']
        u = age/duration
        draw = ImageDraw.Draw(frame)
        kind = checkpoint.get('visual', '')
        if kind in ('stretch', 'finale', 'new-place-comparison'):
            return
        # All moving items are confined to the clear sky above the character and
        # board. Numeric cards and the bear's face are never covered.
        if 'rainbow' in kind:
            for index, color in enumerate(('#ef9b9a', '#eec56f', '#c4d697', '#a8cddb', '#c5b6db')):
                inset = index*7
                draw.arc((320+inset, 20+inset, 700-inset, 220-inset), 185, 355, fill=color, width=6)
        elif 'cloud' in kind:
            x = 470 + 85*math.sin(u*math.pi)
            for ox, oy, radius in ((0,0,28),(32,-10,35),(65,0,27)):
                draw.ellipse((x+ox-radius, 145+oy-radius, x+ox+radius, 145+oy+radius), fill='#f6f2fa')
        elif 'pond' in kind:
            for index in range(3):
                radius = 25+(u*65+index*20)%75
                draw.arc((150-radius, 760-radius/4, 150+radius, 760+radius/4), 0, 330, fill='#a7d6ce', width=3)
        else:
            x = 540 + 130*(u-.5)
            y = 160 - 24*math.sin(u*math.pi)
            if 'moth' in kind:
                wing = 14+6*math.sin(age*15)
                draw.ellipse((x-wing, y-10, x, y+10), fill='#ffe7a8', outline='#b8a378', width=2)
                draw.ellipse((x, y-10, x+wing, y+10), fill='#ffe7a8', outline='#b8a378', width=2)
            else:
                draw.ellipse((x-12, y-6, x+12, y+6), fill='#b8d7b0', outline='#8fab84', width=2)

    def frame(self, seconds):
        state = self.state(seconds)
        checkpoint = self.timeline.active('checkpoint', seconds)
        carry = state['carry']
        pose = self.pose(seconds, state)
        intro_alpha = min(1, max(0, seconds/.8))
        fade_start = float(self.timeline.plan.get('fade_out_start_s', self.duration-2))
        fade_length = self.duration-fade_start
        if fade_length <= 0:
            raise ValueError('Fade-out must begin before the timeline ends')
        outro_alpha = min(1, max(0, (self.duration-seconds)/fade_length))
        alpha = min(intro_alpha, outro_alpha)
        # Repeated stable frames return the same object, allowing encode() to
        # reuse its byte buffer instead of repacking identical 1080p pixels.
        motion = round(seconds*FPS) if checkpoint or carry or state['mode']=='place' or alpha<1 else None
        key = (state['number'], state['focus'], state['mode'], pose, motion)
        if key == self._last_key:
            return self._last_frame
        frame = self.composition(state['number'], state['focus'], state['mode']).copy()
        self.checkpoint_effect(frame, checkpoint, seconds)
        if carry:
            self.carry_strip(frame, carry, seconds)
        elif state['mode'] == 'place':
            pause = state['pause']
            source = int(pause['after_decimal_value'])
            fake = {'from_decimal': source, 'to_decimal': source+1, 'start_s': pause['start_s'], 'end_s': pause['end_s']}
            self.carry_strip(frame, fake, seconds)
        self.bear.draw(frame, [(pose, 1)])
        if alpha < 1:
            frame = Image.blend(self.cream, frame, alpha)
        self._last_key, self._last_frame = key, frame
        return frame

    def sample_times(self):
        samples = [('opening', 1.2), ('read-example', 14.0)]
        for value in (0, 2, 7, 8, 31, 32, 45, 63, 64, 127):
            row = self.timeline.counts[value]
            bit = row['bit_events'][min(2, len(row['bit_events'])-1)]
            samples.append((f'count-{value:03d}', (bit['start_s']+bit['end_s'])/2))
        for index, event in enumerate(self.timeline.by_type.get('pause', [])):
            samples.append((f'pause-{index+1}', event['start_s']+min(3, (event['end_s']-event['start_s'])/2)))
        for index, event in enumerate(self.timeline.by_type.get('carry', [])):
            if event.get('to_decimal') in (8, 32, 64):
                samples.append((f'carry-{index+1}', (event['start_s']+event['end_s'])/2))
        if self.timeline.finale:
            finale = self.timeline.finale
            samples.append(('finale-wave', max(finale['start_s'], finale['end_s']-4)))
        samples.append(('closing-fade', self.duration-.5))
        return samples


def previews(scene, frames_dir=None, sheet=None):
    samples = scene.sample_times()
    if frames_dir:
        frames_dir.mkdir(parents=True, exist_ok=False)
    if sheet:
        sheet.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new('RGB', (1920, math.ceil(len(samples)/3)*402), CREAM)
        draw = ImageDraw.Draw(image)
    records = []
    for index, (label, seconds) in enumerate(samples):
        frame = scene.frame(seconds)
        state = scene.state(seconds)
        record = {'label':label, 'time_s':seconds, 'decimal_value':state['number'], 'display_binary':format(state['number'],'b'),
                  'focus_bit_index':state['focus'], 'mode':state['mode'], 'bear_pose':scene.pose(seconds,state)}
        if frames_dir:
            path = frames_dir/f'{index+1:02d}-{label}.png'
            frame.save(path)
            record['path'] = str(path)
        if sheet:
            x, y = index%3*640, index//3*402
            image.paste(frame.resize((640,360),Image.Resampling.LANCZOS),(x,y))
            draw.text((x+10,y+367),f'{label} / {seconds:.3f}s',font=font(20),fill=INK)
        records.append(record)
    if sheet:
        image.save(sheet)
    if frames_dir:
        (frames_dir/'preview-manifest.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preset', default='veryfast')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--ffmpeg')
    parser.add_argument('--frames-dir', type=Path)
    parser.add_argument('--contact-sheet', type=Path)
    parser.add_argument('--sample-reel', action='store_true')
    args = parser.parse_args()
    if not any((args.output, args.frames_dir, args.contact_sheet)):
        parser.error('Provide --output, --frames-dir or --contact-sheet')
    for target in (args.output, args.frames_dir, args.contact_sheet):
        if target and target.exists():
            raise ValueError(f'Refusing to overwrite existing artifact: {target}')
    plan = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    timeline = BinaryTimeline(plan)
    scene = BinaryScene(timeline)
    records = previews(scene,args.frames_dir,args.contact_sheet) if args.frames_dir or args.contact_sheet else []
    if args.output:
        if args.sample_reel:
            segments = [Segment(max(0,t-.4), min(1.6,scene.duration-max(0,t-.4)), label) for label,t in scene.sample_times()]
        else:
            if not args.audio or not args.audio.is_file():
                raise ValueError('Full binary movie requires the measured final master WAV')
            segments = [Segment(0,scene.duration,'binary counting 0–127')]
        report = encode(scene, segments, args.output, find_ffmpeg(args.ffmpeg), None if args.sample_reel else args.audio, args.crf,args.preset)
        report.update({'timeline':str(args.timeline),'timeline_sha256':file_hash(args.timeline),
                       'renderer':'tools/render_binary_video.py', 'renderer_sha256':file_hash(__file__),
                       'shared_encoder_and_bear_sha256':file_hash(ROOT/'tools/render_counting_video.py'),
                       'source_assets':source_receipts(),
                       'audio_sha256':file_hash(args.audio) if args.audio and not args.sample_reel else None,
                       'synthetic_timing':False,'sample_reel':args.sample_reel,
                       'counted_states':128,'spoken_bit_words':sum(len(r['bit_events']) for r in timeline.counts),
                       'layout':{'bit_grid_xywh':[650,330,1160,234], 'cell_gap_px':14,
                                 'digit_visible_ink_center_y':426, 'digit_font_size':116,
                                 'place_weights_y':529,'slot_order':list(WEIGHTS)}})
        args.output.with_suffix('.render.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2),flush=True)
    elif records:
        print(json.dumps({'preview_frames':len(records),'duration_s':scene.duration},indent=2),flush=True)


if __name__ == '__main__':
    main()
