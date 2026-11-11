#!/usr/bin/env python3
"""Independent source-art, decoded motion, continuity and mosaic QA for prime v003.

Imports only the earlier independent verifier's generic media helpers. No movie
renderer or staged full-frame PNG is imported. References are reconstructed
from hash-bound original character cells and explicit face/arm registrations.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import csv
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

try:
    import verify_prime_animation as media
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools import verify_prime_animation as media
    from tools.component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
ACTOR = (1370, 510, 1896, 1056)
REGIONS = {
    'complete_actor_corridor': ACTOR,
    'eyes': (1568, 622, 1683, 684),
    'mouth': (1555, 672, 1641, 731),
    'standing_hand_gestures': (1460, 704, 1710, 870),
    'lower_pouch_and_legs': (1490, 855, 1778, 1028),
    'full_tail': (1690, 900, 1860, 1028),
}
CONTINUITY = {
    'ears_hair_and_upper_head': (1530, 540, 1710, 619),
    'lower_pouch': (1578, 875, 1660, 930),
    'tail_tip': (1735, 962, 1826, 1004),
}
THRESHOLD = 4.0


def rect(box):
    return tuple(box[i] - ACTOR[i % 2] for i in range(4))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def schedule(plan, motion):
    total = plan['duration_frames']
    states = [('neutral', 0)] * total
    previous, summaries = -1, []
    for action in motion['actions']:
        a, b = action['start_frame'], action['end_frame']
        sequence = [(f['pose'], f.get('offset_y_px', 0)) for f in action['frames']]
        if a < previous or b - a != len(sequence) or not 0 <= a < b <= total:
            raise ValueError('Invalid or overlapping acting schedule')
        if action['id'].startswith('blink-'):
            if sequence != [('blink_half', 0)] * 2 + [('blink_closed', 0)] * 3 + [('blink_half', 0)] * 2:
                raise ValueError('Recurring blink lacks its three physical phases')
        previous = b
        states[a:b] = sequence
        summaries.append({'id': action['id'], 'start_frame': a, 'end_frame': b,
                          'poses': sorted({x[0] for x in sequence})})
    counts = Counter(pose for pose, _ in states)
    if len(counts) < 20 or not any('rest' in p or 'seated' in p for p in counts):
        raise ValueError('v003 acting lacks the promised extended posture repertoire')
    return states, summaries, counts


class SourceArtwork:
    """Independent implementation of registered source-cell and patch geometry."""

    def __init__(self, registration, motion, panel, ffmpeg):
        self.registration, self.ffmpeg = registration, ffmpeg
        self.height = float(motion.get('body_height_px', 470))
        self.root = tuple(motion.get('ground_foot_anchor_px', [1625, 1014]))
        if self.height != 470 or self.root != (1625, 1014):
            raise ValueError('Review the provisional 470px/root geometry before changing it')
        self.rows = {f['id']: f for f in registration['frames']}
        self.raw, self.geometry = {}, {}
        source_sheets = {}
        for identity, row in self.rows.items():
            path = media.resolve(row['path'])
            if media.sha(path) != row['sha256']:
                raise ValueError(f'Adopted original image hash differs: {identity}')
            source_path = row.get('source_sheet')
            box = row.get('source_cell_box_xyxy', row.get('crop_from_sheet_xyxy'))
            with Image.open(path) as opened:
                image = opened.copy()
            if image.mode != 'RGBA':
                raise ValueError('Character material must retain original RGBA')
            if source_path and box:
                if source_path not in source_sheets:
                    group = registration['source_groups'][row['scale_group']]
                    expected_hash = row.get('source_sheet_sha256', group.get('sheet_sha256', group.get('source_sheet_sha256')))
                    if expected_hash and media.sha(media.resolve(source_path)) != expected_hash:
                        raise ValueError('A hash-bound generated source sheet changed')
                    with Image.open(media.resolve(source_path)) as sheet:
                        source_sheets[source_path] = sheet.copy()
                crop = source_sheets[source_path].crop(box)
                if crop.mode != image.mode or crop.size != image.size or crop.tobytes() != image.tobytes():
                    raise ValueError(f'Adopted image is not its lossless source cell: {identity}')
            else:
                raise ValueError(f'No original source-cell provenance: {identity}')
            group = registration['source_groups'][row['scale_group']]
            reference = float(group['reference_height_px'])
            if abs(float(row['reference_height_px']) - reference) > 1e-6:
                raise ValueError('Detected individual pose fitting')
            self.raw[identity] = image
            self.geometry[identity] = (self.height / reference, list(row['anchor_px']))
        self.images = dict(self.raw)
        self.rig_checks = {}
        self.apply_faces()
        self.apply_arms()
        path = media.resolve('assets/library/worlds/sunlit-mosaic-museum/backgrounds/v001/sunlit-mosaic-museum-background.png')
        self.background_path = path
        background = ImageOps.fit(Image.open(path).convert('RGBA'), (1920, 1080), Image.Resampling.LANCZOS)
        box = panel.get('panel_inner_xyxy', [1523, 320, 1795, 522])
        color = panel.get('panel_color', '#f8edd7')
        # The grid ends at509, while this actor reference starts at510. Only
        # its constant cream backing intersects the actor crop; no producer
        # mosaic pixels are borrowed as an animation reference.
        ImageDraw.Draw(background).rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=color)
        self.background = background.crop(ACTOR)

    def apply_faces(self):
        for identity, config in self.registration.get('face_overlays', {}).items():
            base_id = config['base_pose']
            base = self.raw[base_id].copy()
            source = self.raw[identity]
            for patch in config['patches']:
                src, dst = patch['source_box_xyxy'], patch['target_box_xyxy']
                image = source.crop(src).resize((dst[2] - dst[0], dst[3] - dst[1]), Image.Resampling.LANCZOS)
                radius = patch.get('feather_px', 2)
                mask = Image.new('L', image.size)
                inset = math.ceil(radius * 1.5)
                ImageDraw.Draw(mask).rectangle((inset, inset, image.width - inset - 1, image.height - inset - 1), fill=255)
                if radius:
                    mask = mask.filter(ImageFilter.GaussianBlur(radius))
                if patch.get('clip_to_base_alpha'):
                    skin = self.raw[base_id].getchannel('A').crop(dst).point(lambda a: 255 if a >= patch.get('base_alpha_threshold', 128) else 0)
                    margin = patch.get('base_alpha_inset_px', 2)
                    if margin:
                        skin = skin.filter(ImageFilter.MinFilter(2 * margin + 1))
                    mask = ImageChops.multiply(mask, skin)
                image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
                base.alpha_composite(image, dst[:2])
            self.images[identity] = base
            self.geometry[identity] = self.geometry[base_id]
            self.rig_checks[identity] = {'kind': 'generated-eye-or-mouth-overlay',
                'body_and_tail_rgba_identical': base.crop((0, 252, base.width, base.height)).tobytes() == self.raw[base_id].crop((0, 252, base.width, base.height)).tobytes()}
            if not self.rig_checks[identity]['body_and_tail_rgba_identical']:
                raise ValueError('Facial change moved the coherent body/tail')

    def apply_arms(self):
        self.arm_poses = set(self.registration.get('arm_overlays', {}))
        for identity, config in self.registration.get('arm_overlays', {}).items():
            base_id = config.get('base_pose', 'neutral')
            source_id = config.get('source_pose', identity)
            base, source = self.raw[base_id].copy(), self.raw[source_id]
            transform = config['source_to_base']
            scale = transform['scale']
            # Physical source scaling must be shared by its sheet, never fitted
            # individually by visible pose height.
            expected = self.rows[base_id]['reference_height_px'] / self.rows[source_id]['reference_height_px']
            if abs(scale - expected) > 1e-6:
                raise ValueError('Arm source was independently fitted instead of physically calibrated')
            image = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
            aligned = Image.new('RGBA', base.size)
            aligned.paste(image, tuple(round(v) for v in transform['translate_xy']))
            mask = Image.new('L', base.size)
            ImageDraw.Draw(mask).polygon([tuple(p) for p in config['replace_polygon_xy']], fill=255)
            radius = config.get('feather_px', 2)
            if radius:
                mask = mask.filter(ImageFilter.GaussianBlur(radius))
            if config.get('lower_body_fade_y'):
                top, bottom = config['lower_body_fade_y']
                fade = Image.new('L', (1, base.height))
                fade.putdata([255 if y <= top else 0 if y >= bottom else round(255 * (bottom - y) / (bottom - top)) for y in range(base.height)])
                mask = ImageChops.multiply(mask, fade.resize(base.size))
            final = Image.composite(aligned, base, mask)
            unchanged = ImageChops.multiply(ImageChops.difference(final, base).convert('L'), ImageChops.invert(mask.point(lambda a: 255 if a else 0))).getbbox() is None
            # Ear/head and lower pouch/tail are independently protected against
            # the exact unrelated drawing pop found in v002.
            protected = {'ears': (80, 0, 350, 130), 'lower_body_and_tail': (0, 410, base.width, base.height)}
            stability = {name: final.crop(box).tobytes() == base.crop(box).tobytes() for name, box in protected.items()}
            if not unchanged or not all(stability.values()):
                raise ValueError(f'Arm rig changes protected base pixels: {identity}: {stability}')
            self.images[identity] = final
            self.geometry[identity] = self.geometry[base_id]
            self.rig_checks[identity] = {'kind': 'generated-arm-replacement', 'unchanged_outside_feather_mask': unchanged,
                'protected_region_pixel_identity': stability, 'mask_visible_bounds': mask.getbbox()}

    @lru_cache(maxsize=512)
    def image(self, pose, offset, cream):
        scale, anchor = self.geometry[pose]
        raw = self.images[pose]
        image = raw.resize((round(raw.width * scale), round(raw.height * scale)), Image.Resampling.LANCZOS)
        pos = (round(self.root[0] - anchor[0] * scale), round(self.root[1] + offset - anchor[1] * scale))
        bb = image.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
        visible = tuple(bb[i] + pos[i % 2] for i in range(4))
        if not (ACTOR[0] < visible[0] < visible[2] < ACTOR[2] and ACTOR[1] < visible[1] < visible[3] < ACTOR[3]):
            raise ValueError(f'Visible actor/tail leaves native clear crop: {pose}/{offset}: {visible}')
        layer = Image.new('RGBA', self.background.size)
        lift, x, y = max(0, -offset), self.root[0] - ACTOR[0], self.root[1] - ACTOR[1]
        w = 1 - lift / 200
        ImageDraw.Draw(layer).ellipse((x - 92 * w, y - 9, x + 135 * w, y + 14), fill=(77, 61, 44, round(24 * w)))
        layer.alpha_composite(image, (pos[0] - ACTOR[0], pos[1] - ACTOR[1]))
        result = self.background.copy()
        result.alpha_composite(layer)
        if cream:
            result = Image.blend(result, Image.new('RGBA', result.size, '#fffaf0'), cream / 255)
        return result.convert('RGB')

    @lru_cache(maxsize=512)
    def reference(self, pose, offset, cream):
        image = self.image(pose, offset, cream)
        command = [self.ffmpeg, '-nostdin', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
            '-s', f'{image.width}x{image.height}', '-i', 'pipe:0', '-vf', 'format=yuv420p,format=rgb24',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
        raw = subprocess.check_output(command, input=image.tobytes())
        return Image.frombytes('RGB', image.size, raw)


def decision(actual, expected):
    metrics, rgb_metrics = {}, {}
    for name, box in REGIONS.items():
        a, b = actual.crop(rect(box)), expected.crop(rect(box))
        rgb = media.delta(a, b)
        rgb_metrics[name] = rgb
        metrics[name] = max(rgb) if name == 'complete_actor_corridor' else media.luma_delta(a, b)
    return metrics, rgb_metrics


def actor_check(movie, ffmpeg, plan, states, artwork, out, frame_indices=None, origin=(0, 0)):
    w, h = ACTOR[2] - ACTOR[0], ACTOR[3] - ACTOR[1]
    command = [ffmpeg, '-nostdin', '-v', 'error', '-i', str(movie), '-an', '-vf', f'crop={w}:{h}:{ACTOR[0]-origin[0]}:{ACTOR[1]-origin[1]}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    frame_indices = list(range(len(states))) if frame_indices is None else frame_indices
    worst = {k: 0.0 for k in REGIONS}
    worst_rgb = {k: [0, 0, 0] for k in REGIONS}
    worst_continuity = {k: 0.0 for k in CONTINUITY}
    failures, counts, negative = [], Counter(), {}
    actual_neutral = None
    seen_images = {}
    contacts = {}
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process, (out / 'decoded-actor-frames.csv').open('w') as log:
        writer = csv.writer(log)
        writer.writerow(['decoded_frame', 'source_frame', 'pose', 'lift_px', 'cream', 'maximum_reference_error', 'continuity_error', 'passed'])
        for decoded_index, index in enumerate(frame_indices):
            pose, offset = states[index]
            raw = media.read_exact(process.stdout, w * h * 3)
            if raw is None:
                raise ValueError('Actual actor movie ended early')
            actual = Image.frombytes('RGB', (w, h), raw)
            cream = media.cream_at(index, plan)
            expected = artwork.reference(pose, offset, cream)
            metrics, rgb = decision(actual, expected)
            for k in REGIONS:
                worst[k] = max(worst[k], metrics[k])
                worst_rgb[k] = [max(a, b) for a, b in zip(worst_rgb[k], rgb[k])]
            passed = max(metrics.values()) <= THRESHOLD
            if not passed and len(failures) < 30:
                failures.append({'frame': index, 'pose': pose, 'reference_errors': metrics})
            counts[pose] += 1
            if pose == 'neutral' and cream == 0 and actual_neutral is None:
                actual_neutral = actual.copy()
                actual_neutral.save(out / 'actual-neutral-reference.png')
            continuity_error = 0.0
            if pose in artwork.arm_poses and cream == 0 and offset == 0:
                if actual_neutral is None:
                    raise ValueError('No actual unfaded neutral precedes standing gestures')
                errors = {name: media.luma_delta(actual.crop(rect(box)), actual_neutral.crop(rect(box))) for name, box in CONTINUITY.items()}
                continuity_error = max(errors.values())
                for k, value in errors.items():
                    worst_continuity[k] = max(worst_continuity[k], value)
                if continuity_error > THRESHOLD:
                    passed = False
                    if len(failures) < 30:
                        failures.append({'frame': index, 'pose': pose, 'unrelated_body_pop_errors': errors})
            if pose != 'neutral' and cream == 0 and (pose, offset) not in negative:
                # The real decoded neutral, not just its source drawing, must
                # fail exactly the same criterion as every active state.
                control, _ = decision(actual_neutral, expected)
                negative[pose, offset] = {'pose': pose, 'offset_y_px': offset, 'same_rule_errors': control,
                    'static_neutral_rejected': max(control.values()) > THRESHOLD}
                contacts[pose, offset] = actual.copy()
            writer.writerow([decoded_index, index, pose, offset, cream, round(max(metrics.values()), 6), round(continuity_error, 6), passed])
            if (decoded_index + 1) % 3000 == 0:
                print(json.dumps({'actor_frames': decoded_index + 1, 'max_error': max(worst.values()), 'max_continuity_error': max(worst_continuity.values())}), flush=True)
        if process.stdout.read(1):
            raise ValueError('Actual movie has extra actor frames')
        process.stdout.close()
        error = process.stderr.read().decode()
        if process.wait():
            raise ValueError(error)
    negative_rows = list(negative.values())
    controls_pass = bool(negative_rows) and all(x['static_neutral_rejected'] for x in negative_rows)
    save(out / 'actual-static-neutral-negative-controls.json', {'threshold': THRESHOLD, 'same_rule': 'globalRGB/localLuma identical to positive frames', 'controls': negative_rows, 'passed': controls_pass})
    chosen = [(('neutral', 0), actual_neutral)] + list(contacts.items())
    sheet = Image.new('RGB', (w * 4, math.ceil(len(chosen) / 4) * (h + 30)), '#fffaf0')
    draw = ImageDraw.Draw(sheet)
    for i, ((pose, offset), image) in enumerate(chosen):
        x, y = i % 4 * w, i // 4 * (h + 30)
        sheet.paste(image, (x, y)); draw.text((x + 8, y + h + 5), f'{pose} lift={offset}', fill='#332b22')
    sheet.save(out / 'actual-decoded-pose-contact.jpg', quality=93)
    return {'frames_checked': len(frame_indices), 'native_crop_xyxy': list(ACTOR), 'threshold': THRESHOLD,
        'reference_metrics': 'full-corridor maximum perRGB-channel MAE; local feature luma MAE',
        'worst_decision_errors': worst, 'local_rgb_measurements_retained': worst_rgb,
        'actual_standing_continuity_regions_xyxy': CONTINUITY, 'worst_actual_neutral_to_standing_body_errors_luma': worst_continuity,
        'static_neutral_control_count': len(negative_rows), 'all_actual_static_neutral_controls_rejected': controls_pass,
        'minimum_strongest_negative_error': min(max(r['same_rule_errors'].values()) for r in negative_rows),
        'pose_frame_counts': dict(counts), 'failures': failures, 'passed': not failures and controls_pass}


def ordinal_frames(plan):
    # A tile is earned only after its spoken prime is complete. The number
    # display precedes the voice, so display_start_s would be an early reward.
    times = [row['voice_end_s'] for row in plan['counted_states']]
    for index in range(plan['duration_frames']):
        t = index / 30 + 1e-9
        ordinal = bisect_right(times, t)
        yield ordinal


def active_mask(image, cream=0):
    # Active teal and inactive ivory remain separated in luma throughout the
    # declared warm global fade. Independent per-channel teal tests would
    # wrongly reject a fading teal because the cream itself has R>G>B.
    opacity = 1 - cream / 255
    active = Image.new('RGB', (1, 1), '#2d736b').convert('L').getpixel((0, 0))
    inactive = Image.new('RGB', (1, 1), '#f4e9d4').convert('L').getpixel((0, 0))
    fade = Image.new('RGB', (1, 1), '#fffaf0').convert('L').getpixel((0, 0))
    midpoint = (active + inactive) / 2 * opacity + fade * (1 - opacity)
    return image.convert('L').point(lambda value: 255 if value < midpoint else 0)


def components(mask):
    w, h = mask.size
    remaining = bytearray(mask.tobytes())
    sizes = []
    for start in range(w * h):
        if not remaining[start]:
            continue
        remaining[start] = 0
        stack, count = [start], 0
        while stack:
            p = stack.pop(); count += 1
            x, y = p % w, p // w
            for q in ((p - 1 if x else -1), (p + 1 if x < w - 1 else -1), (p - w if y else -1), (p + w if y < h - 1 else -1)):
                if q >= 0 and remaining[q]:
                    remaining[q] = 0; stack.append(q)
        if count >= 36:
            sizes.append(count)
    return sizes


def visible_slot_mask(image):
    """Select both actual active fills and inactive brown slot outlines.

    A luminance-difference-only mask also selects codec ringing around the
    cream panel. Requiring all three channels to cross the declared outline /
    backing midpoints isolates the actual palette without a geometric crop to
    the expected grid bounds.
    """
    channels = image.split()
    outline, backing = (214, 196, 165), (248, 237, 215)
    masks = [channel.point(lambda value, edge=(a + b) / 2: 255 if value < edge else 0)
             for channel, a, b in zip(channels, outline, backing)]
    return ImageChops.multiply(ImageChops.multiply(masks[0], masks[1]), masks[2])


def progress_check(movie, ffmpeg, plan, panel, out):
    columns = panel.get('columns', 14); rows = panel.get('rows', 12)
    tile = panel.get('tile_size_px', [12, 11]); gap = panel.get('gap_px', 4)
    box = panel.get('grid_xyxy', [1549, 333, 1769, 509])
    if [columns, rows, tile, gap] != [14, 12, [12, 11], 4] or columns * rows != 168:
        raise ValueError('Unexpected unreviewed mosaic geometry')
    pitch_x, pitch_y = tile[0] + gap, tile[1] + gap
    panel_box = panel.get('panel_inner_xyxy', [1523, 320, 1795, 522])
    w, h = panel_box[2] - panel_box[0], panel_box[3] - panel_box[1]
    gx, gy = box[0] - panel_box[0], box[1] - panel_box[1]
    centers = [(gy + row * pitch_y + tile[1] // 2) * w + gx + col * pitch_x + tile[0] // 2 for row in range(rows) for col in range(columns)]
    # The half-open panel starts at odd x=1523. Cropping YUV420P first would
    # silently round it to1522 and add an unrelated outside column. Decode to
    # RGB before the exact native crop so visible centers use actual pixels.
    command = [ffmpeg, '-nostdin', '-v', 'error', '-i', str(movie), '-an', '-vf', f'format=rgb24,crop={w}:{h}:{panel_box[0]}:{panel_box[1]}:exact=1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    failures, samples, seen, checked, faded = [], [], set(), 0, 0
    centering_frames, centering_worst = 0, [0.0, 0.0]
    background_luma = Image.new('RGB', (1, 1), panel.get('panel_color', '#f8edd7')).convert('L').getpixel((0, 0))
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process, (out / 'decoded-mosaic-frames.csv').open('w') as log:
        writer = csv.writer(log); writer.writerow(['frame', 'ordinal', 'active_cells', 'passed'])
        for index, ordinal in enumerate(ordinal_frames(plan)):
            raw = media.read_exact(process.stdout, w * h * 3)
            if raw is None:
                raise ValueError('Progress movie ended early')
            image = Image.frombytes('RGB', (w, h), raw)
            cream = media.cream_at(index, plan)
            if cream >= 224:
                faded += 1; continue
            mask = active_mask(image, cream)
            # Average each actual tile's 5x5 core at native resolution on an
            # independently authored16x15px grid. No image fitting or renderer
            # grid implementation supplies the actual tile count.
            values = mask.filter(ImageFilter.BoxBlur(2)).tobytes()
            cell_values = [values[p] for p in centers]
            active = [value >= 230 for value in cell_values]
            ambiguous = [i for i, value in enumerate(cell_values) if 25 < value < 230]
            expected = [i < ordinal for i in range(168)]
            passed = active == expected and not ambiguous
            centered = None
            if cream == 0:
                # Both active fills and inactive outlines are visibly darker
                # than the cream replacement. Measure their actual decoded
                # union, not the expected geometric grid box or the panel.
                visible = visible_slot_mask(image)
                centered = raster_centering_report(visible, panel_box, origin_xy=panel_box[:2], name='actual-decoded/all-168-mosaic-slots', tolerance_px=1, alpha_threshold=128)
                centering_frames += 1
                centering_worst = [max(centering_worst[0], abs(centered['delta_x_px'])), max(centering_worst[1], abs(centered['delta_y_px']))]
                passed = passed and centered['passed']
                if not centered['passed'] and len(failures) < 30:
                    failures.append({'frame': index, 'ordinal': ordinal, 'decoded_visible_group_centering': centered})
            checked += 1
            if not passed and len(failures) < 30:
                failures.append({'frame': index, 'ordinal': ordinal, 'active_cells': sum(active), 'wrong_cells': [i for i, (a, b) in enumerate(zip(active, expected)) if a != b], 'ambiguous_cells': ambiguous})
            writer.writerow([index, ordinal, sum(active), passed])
            if cream == 0 and ordinal not in seen:
                cc = components(mask)
                cc_pass = len(cc) == ordinal
                if not cc_pass and len(failures) < 30:
                    failures.append({'frame': index, 'ordinal': ordinal, 'connected_components': len(cc)})
                image.save(out / f'progress-{ordinal:03d}.png')
                samples.append({'ordinal': ordinal, 'frame': index, 'independent_connected_components': len(cc), 'component_sizes': cc, 'decoded_slot_union_centering': centered, 'passed': cc_pass and centered['passed']})
                seen.add(ordinal)
        if process.stdout.read(1):
            raise ValueError('Progress movie contains extra frames')
        process.stdout.close(); error = process.stderr.read().decode()
        if process.wait():
            raise ValueError(error)
    return {'native_grid_xyxy': box, 'columns': columns, 'rows': rows, 'tile_size_px': tile, 'gap_px': gap,
        'frames_checked': checked, 'near_white_declared_global_fade_frames': faded,
        'native_visible_slot_group_centering': {'target_panel_xyxy': panel_box, 'frames_checked': centering_frames, 'foreground_palette_midpoint_rgb': [231, 216.5, 190], 'max_abs_delta_xy_px': centering_worst, 'tolerance_each_axis_px': 1, 'source_grid_tolerance_px': .5, 'declared_global_fade_frames_not_centered_from_low_contrast_pixels': plan['duration_frames'] - centering_frames, 'method': 'Actual decoded RGB palette contrast mask includes active fills and inactive outlines; raster_centering_report checks horizontal/vertical independently, containment, nonempty and edge clearance.'},
        'ordinal_states_seen': sorted(seen), 'native_component_samples': samples, 'failures': failures,
        'method': 'Native active-teal mask; every fixed tile core tested against independently timed row-major ordinal; separate four-connected components for all 169 ordinal states including zero.',
        'passed': not failures and seen == set(range(169))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('movie', 'timeline', 'motion', 'registration', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--old-movie', required=True)
    parser.add_argument('--preview-record', help='Map a native 550x680 acting montage to original source-frame times; actor-only calibration.')
    parser.add_argument('--ffmpeg', default='ffmpeg'); parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args()
    out = media.resolve(args.out); out.mkdir(parents=True, exist_ok=False)
    movie, old = media.resolve(args.movie), media.resolve(args.old_movie)
    plan, motion, registration = [media.read(x) for x in (args.timeline, args.motion, args.registration)]
    panel = plan.get('progress_mosaic', motion.get('progress_mosaic', {}))
    states, summary, counts = schedule(plan, motion)
    artwork = SourceArtwork(registration, motion, panel, args.ffmpeg)
    report = {'kind': 'independent-prime-v003-motion-continuity-progress-qa',
        'inputs': {name: {'path': media.local(value), 'sha256': media.sha(media.resolve(value))} for name, value in {'movie': movie, 'timeline': args.timeline, 'motion': args.motion, 'registration': args.registration, 'old_movie': old, 'verifier': __file__, 'independent_media_helper': media.__file__}.items()},
        'scope': 'Native actual decoded frames; independent original-cell/registered patch reconstruction, explicit continuity checks, independently timed mosaic occupancy and components, old/new learning-region comparison and AAC packet/timestamp identity. No renderer or staged full-frame PNG import; selected contacts, not a human continuous-playback claim.',
        'actions': summary, 'source_rig_checks': artwork.rig_checks}
    try:
        indices = None
        origin = (0, 0)
        if args.preview_record:
            clips = media.read(args.preview_record)['preview']['clips']
            indices = [round(clip['source_start_s'] * 30) + i for clip in clips for i in range(round(clip['duration_s'] * 30))]
            origin = (1370, 400)
        report['actor'] = actor_check(movie, args.ffmpeg, plan, states, artwork, out, indices, origin)
        if not args.preview_record:
            report['progress'] = progress_check(movie, args.ffmpeg, plan, panel, out)
            report['learning_region'] = media.learning_check(old, movie, args.ffmpeg, plan['duration_frames'], out)
            before, after = media.aac_packets(old, args.ffprobe), media.aac_packets(movie, args.ffprobe)
            report['aac'] = {'packet_count': len(after), 'payload_hash_and_pts_dts_duration_size_identical': before == after, 'passed': before == after}
        report['passed'] = all(report[key]['passed'] for key in ('actor', 'progress', 'learning_region', 'aac') if key in report)
    except Exception as error:
        report['passed'] = False; report['error'] = str(error)
        raise
    finally:
        save(out / 'verification.json', report)
    print(json.dumps({'passed': report['passed'], 'report': media.local(out / 'verification.json')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
