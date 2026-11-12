"""Catalan v003: preserve gestures across scene-scale cuts and speech meaning.

The rendered body has one adopted head silhouette, trunk, feet and tail.  New
authored arms, eyes and mouth are registered as local derived layers; source
PNGs are immutable.  Discrete drawings are exposed without whole-body fades.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FPS = 30
BATCH = ROOT / 'assets/library/characters/tora/generation-batches/catalan-production-20261112-01a1cd57'
DEFAULT_REGISTRATION = BATCH / 'runtime/registration.json'
CANONICAL = ROOT / 'assets/library/characters/tora/sources/v001/neutral.png'
CANONICAL_SHA256 = 'e71d1805327afea9077cfa0398f19fa994ad057588df6a085b373025afec3ee6'


def resolve(path):
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(path):
    return str(Path(path).resolve().relative_to(ROOT))


def hold(pose, frames):
    return [pose] * frames


def wave_sequence():
    """One greeting: raise, two small wrist sweeps, return along the same arm."""
    return (hold('neutral', 3) + hold('wave_raise', 5)
            + hold('wave_high_in', 5) + hold('wave_high_out', 5)
            + hold('wave_high_in', 5) + hold('wave_high_out', 5)
            + hold('wave_high_in', 5) + hold('wave_raise', 5)
            + hold('neutral', 6))


def present_sequence(side='inside', hold_frames=30):
    mid = 'present_left_half' if side == 'inside' else 'wave_raise'
    final = 'guide_inside' if side == 'inside' else 'guide_after'
    return (hold('watch_up', 4) + hold(mid, 5) + hold(final, hold_frames)
            + hold(mid, 5) + hold('watch_up', 5))


def two_groups_sequence():
    return (hold('neutral', 3) + hold('two_half', 5)
            + hold('explain_two', 28) + hold('two_half', 5)
            + hold('neutral', 5))


def realise_sequence():
    return (hold('watch_up', 5) + hold('realise_half', 5)
            + hold('realise', 16) + hold('realise_half', 5)
            + hold('neutral', 6))


def blink_sequence():
    return hold('blink_half', 2) + hold('blink_closed', 3) + hold('blink_half', 2)


@dataclass(frozen=True)
class Action:
    ident: str
    start_frame: int
    poses: tuple[str, ...]
    reason: str

    @property
    def end_frame(self):
        return self.start_frame + len(self.poses)


class Artwork:
    def __init__(self, registration=None):
        self.path = resolve(registration or DEFAULT_REGISTRATION)
        if not self.path.exists():
            raise FileNotFoundError(f'Catalan runtime registration is not ready: {self.path}')
        self.registration = json.loads(self.path.read_text())
        if not self.registration.get('runtime_composited'):
            raise ValueError('Catalan actor requires the explicitly reviewed local-art runtime')
        self.rows = self.registration['poses']
        self.images = {}
        for ident, row in self.rows.items():
            path = resolve(row['path'])
            if sha(path) != row['sha256']:
                raise ValueError(f'Catalan actor source hash mismatch: {ident}')
            if row['reference_height_px'] <= 0 or len(row['anchor_px']) != 2:
                raise ValueError(f'Catalan actor lacks scale/support: {ident}')
            self.images[ident] = Image.open(path).convert('RGBA')
        required = {'neutral', 'watch_up', 'wave_raise', 'wave_high_in',
                    'wave_high_out', 'guide_inside', 'guide_after', 'gaze_up_left',
                    'blink_half', 'blink_closed', 'explain_two', 'realise',
                    'realise_half', 'two_half', 'present_left_half'}
        missing = required - self.rows.keys()
        if missing:
            raise ValueError(f'Missing Catalan acting drawings: {sorted(missing)}')

    @lru_cache(maxsize=256)
    def sprite(self, pose, height):
        row = self.rows[pose]
        scale = height / row['reference_height_px']
        image = self.images[pose]
        return image.resize((round(image.width * scale), round(image.height * scale)),
                            Image.Resampling.LANCZOS), row, scale

    def receipt(self):
        return {'registration': {'path': local(self.path), 'sha256': sha(self.path)},
                'runtime_composited': True,
                'body_base': self.registration.get('body_base'),
                'local_compositing': self.registration.get('local_compositing'),
                'source_pngs_modified': False, 'whole_actor_crossfade': False}


class Schedule:
    def __init__(self, plan=None):
        self.plan = plan or {}
        events = self.plan.get('voice_events', [])
        if not events:
            self.actions, self.starts = [], []
            return
        ordered = sorted(events, key=lambda row: row['start_s'])
        by = {row['id']: row for row in ordered}
        actions = []
        self.optional_overlap_skips = []

        def add(ident, seconds, poses, reason, optional=False):
            action = Action(ident, max(0, round(seconds * FPS)), tuple(poses), reason)
            conflicts = [a.ident for a in actions
                         if action.start_frame < a.end_frame and a.start_frame < action.end_frame]
            if conflicts:
                if optional:
                    self.optional_overlap_skips.append({'id': ident, 'start_frame': action.start_frame,
                                                        'conflicts': conflicts})
                    return False
                raise ValueError(f'Required Catalan gesture {ident} overlaps {conflicts}')
            if any(a.ident == ident for a in actions):
                raise ValueError(f'Duplicate Catalan gesture ID: {ident}')
            actions.append(action)
            return True

        def at(ident, poses, reason, offset=.25, action_id=None):
            if ident in by:
                add(action_id or ident + '-gesture', by[ident]['start_s'] + offset, poses, reason)

        at('I01', wave_sequence(), 'Welcome with a raised arm, two sweeps and grounded return.')
        at('I03', two_groups_sequence(), 'Introduce an up/down pair with two open forearms.')
        at('T000a', present_sequence('inside', 35), 'Guide attention to the incoming value and multiplier.')
        # Existing independent CTC tokens place "Then divide" at +4.26..4.865s
        # and the verb divide at +4.48s. Before that, the renderer targets the
        # central whole-product window; the actor remains quietly watch_up.
        at('T000b', present_sequence('after', 35),
           'Show equal division only when Then divide is actually spoken.', offset=4.48)
        at('T001a', two_groups_sequence(), 'Keep the two equal values in their distinct places.')
        at('T002a', two_groups_sequence(), 'Present two different paths with the same pair count.')
        # Explanation IDs are stable script identities; no modulo loop is used
        # to repeat the same arm movement at each counted value.
        at('T003b', present_sequence('inside', 28), 'Show the smaller path inside the first arch.')
        at('T003b', present_sequence('after', 28), 'Then show the path after the first return.',
           offset=4.0, action_id='T003b-after-gesture')
        at('T003c', present_sequence('inside', 28), 'Show the zero-pair inside group and its continuation.')
        at('T003d', present_sequence('after', 28), 'Show the remaining inside/after split groups.')
        at('T003e', two_groups_sequence(), 'Present the sum of the three disjoint first-return groups.')
        for n in (5, 10, 16, 24, 30):
            ident = f'N{n:03d}'
            if ident in by:
                # T010a cuts from the 220px count to its 280px explanation only
                # 0.6s after the read. Start the entire gesture after that cut;
                # do not enlarge a partly completed realization by27 percent.
                start = (by['T010a']['start_s'] + .35
                         if n == 10 and 'T010a' in by else by[ident]['end_s'] + .23)
                add(f'value-{n:03d}-acknowledge', start, realise_sequence(),
                    'A short acknowledgement after the whole value; N10 stays within its new explanation scale.')
        outros = [row for row in ordered if row['id'].startswith('O')]
        if outros:
            opening = outros[0]
            prior = next((a for a in actions if a.ident == 'value-030-acknowledge'), None)
            history_start = max(opening['start_s'] + .25, prior.end_frame / FPS + .18 if prior else 0)
            if history_start + len(two_groups_sequence()) / FPS > opening['end_s']:
                raise ValueError('Completed-history gesture does not fit its existing speech window')
            add(opening['id'] + '-gesture', history_start, two_groups_sequence(),
                'Present the completed history after N30 realization returns; never silently discard a collision.')
            last = outros[-1]
            add('goodbye-wave', last['start_s'] + .2, wave_sequence(),
                'A final two-sweep wave and return without changing the count cadence.')

        next_blink = 5.4
        spacing = (6.1, 7.3, 5.9, 8.2, 6.8, 7.7)
        blink_index = 0
        for current, following in zip(ordered, ordered[1:]):
            when = max(current['end_s'] + .12, next_blink)
            if following['start_s'] - when < len(blink_sequence()) / FPS + .1:
                continue
            if add(f'quiet-blink-{blink_index + 1:03d}', when, blink_sequence(),
                   'One brief irregular blink in an already existing quiet gap.', optional=True):
                next_blink = when + spacing[blink_index % len(spacing)]
                blink_index += 1
        self.actions = sorted(actions, key=lambda row: row.start_frame)
        self.starts = [row.start_frame for row in self.actions]

    def action_at(self, frame):
        index = bisect_right(self.starts, frame) - 1
        if index >= 0 and frame < self.actions[index].end_frame:
            return self.actions[index]
        return None

    def state(self, time_s):
        frame = round(time_s * FPS)
        action = self.action_at(frame)
        if action is None:
            return None, None
        return action.poses[frame - action.start_frame], action

    def receipt(self):
        return {'fps': FPS, 'scope': 'Catalan ribbon-plaza guide acting',
                'audio_timing_changed': False, 'continuous_idle_loop': False,
                'revision': 'v003', 'required_gesture_collisions_rejected': True,
                'optional_overlap_skips': getattr(self, 'optional_overlap_skips', []),
                'actions': [{'id': row.ident, 'start_frame': row.start_frame,
                             'end_frame': row.end_frame, 'start_s': row.start_frame / FPS,
                             'end_s': row.end_frame / FPS, 'poses': list(row.poses),
                             'reason': row.reason} for row in self.actions]}


_artwork = None
_schedule = None


def configure_animation(plan=None, registration_path=None):
    """Bind the immutable artwork and measured timeline once before rendering."""
    global _artwork, _schedule
    _artwork = Artwork(registration_path)
    _schedule = Schedule(plan)
    return {'artwork': _artwork.receipt(), 'schedule': _schedule.receipt()}


def _baseline_pose(scene_id, target, foot, cue):
    if target is not None and target[1] < foot[1] - 100:
        if target[0] < foot[0] - 100:
            return 'gaze_up_left'
        if target[0] > foot[0] + 100 and _artwork and 'gaze_up_right' in _artwork.rows:
            return 'gaze_up_right'
        return 'watch_up'
    if scene_id in {'multiply', 'divide', 'coefficient', 'recurrence', 'first_return',
                    'equal_groups', 'five_paths', 'history'}:
        return 'watch_up'
    return 'neutral'


def draw_character(image, time_s, scene_id, scene_start_s=0, scene_end_s=None,
                   cue=None, body_height=240, foot=(960, 1030), target=None):
    """Alpha-composite one guide and return actual placement/provenance.

    ``target`` controls a meaningful gaze; it never moves the actor or mirrors
    the adopted tiger.  ``foot`` and ``body_height`` are independent scene design
    inputs.  Support placement is tested on both axes, never by sprite bbox fit.
    """
    global _artwork, _schedule
    if image.mode != 'RGBA':
        raise ValueError('Catalan character target image must be RGBA')
    if not math.isfinite(time_s) or body_height <= 0:
        raise ValueError('Invalid Catalan actor time/height')
    if _artwork is None:
        configure_animation()
    cue = cue or {}
    pose, action = _schedule.state(time_s) if _schedule else (None, None)
    if pose is None:
        if not _schedule or not _schedule.actions:
            elapsed = max(0, time_s - scene_start_s)
            if scene_id in {'intro', 'ending'} and .25 <= elapsed < .25 + len(wave_sequence()) / FPS:
                pose = wave_sequence()[min(len(wave_sequence()) - 1, int((elapsed - .25) * FPS))]
        pose = pose or _baseline_pose(scene_id, target, foot, cue)
    sprite, row, scale = _artwork.sprite(pose, round(body_height, 6))
    xy = tuple(round(foot[i] - row['anchor_px'][i] * scale) for i in (0, 1))
    visible = sprite.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
    if visible is None:
        raise ValueError(f'Empty Catalan actor: {pose}')
    box = [visible[0] + xy[0], visible[1] + xy[1], visible[2] + xy[0], visible[3] + xy[1]]
    if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
        raise ValueError(f'Clipped Catalan actor: {pose}: {box}')
    actual = [xy[i] + row['anchor_px'][i] * scale for i in (0, 1)]
    delta = [actual[i] - foot[i] for i in (0, 1)]
    if any(abs(value) > .5 + 1e-6 for value in delta):
        raise ValueError('Actor support placement exceeds pixel rounding tolerance')
    image.alpha_composite(sprite, xy)
    return {'pose': pose, 'time_s': time_s, 'scene_id': scene_id,
            'action_id': action.ident if action else None,
            'target_px': list(target) if target is not None else None,
            'scene_start_s': scene_start_s, 'scene_end_s': scene_end_s,
            'cue_id': cue.get('id'), 'visible_box_xyxy': box,
            'origin_xy': list(xy), 'foot_target_px': list(foot),
            'actual_anchor_px': actual, 'delta_x_px': delta[0], 'delta_y_px': delta[1],
            'horizontal': 'anatomical-support-x', 'vertical': 'ground-contact-y',
            'not_centering_target': True, 'tolerance_px': .5, 'contained': True,
            'passed': True, 'display_body_height_px': body_height,
            'source_body_reference_height_px': row['reference_height_px'], 'scale': scale,
            'source_path': row['path'], 'source_sha256': row['sha256'],
            'local_derivation': row.get('local_derivation'),
            'whole_actor_crossfade': False, 'per_pose_fit': False,
            'source_pngs_modified': False}


def animation_receipt():
    if _artwork is None:
        configure_animation()
    return {'artwork': _artwork.receipt(), 'schedule': _schedule.receipt()}


def _immutable_png(image, path):
    path = Path(path)
    if path.exists():
        previous = Image.open(path).convert('RGBA')
        if previous.size != image.size or previous.tobytes() != image.tobytes():
            raise FileExistsError(f'Refusing to overwrite different Catalan artwork: {path}')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)


def build_art(output):
    """Register exact source cells and derive one canonical-body candidate.

    Raw physical scale is grouped per sheet.  Local eye-window/shoulder
    registration below is an explicitly documented edit, not per-pose body fit.
    A new output directory is mandatory so failed candidates remain reviewable.
    """
    output = resolve(output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    if sha(CANONICAL) != CANONICAL_SHA256:
        raise ValueError('Adopted Catalan tiger neutral changed')
    base = Image.open(CANONICAL).convert('RGBA')
    definitions = [
        ('acting-a', 'acting-a.png', [0, 599, 1199], [0, 656, 1312], 565,
         [('wave_raise', (295, 587)), ('wave_high_in', (296, 587)),
          ('wave_high_out', (295, 587)), ('guide_inside', (296, 587))]),
        ('acting-b', 'acting-b.png', [0, 608, 1217], [0, 646, 1292], 569,
         [('guide_after', (304, 585)), ('gaze_up_left', (297, 585)),
          ('blink_half', (304, 607)), ('blink_closed', (297, 607))]),
    ]
    raw, sources = {}, []
    for sheet_id, filename, xs, ys, height, entries in definitions:
        source = BATCH / 'source' / filename
        image = Image.open(source).convert('RGBA')
        if image.size != (xs[-1], ys[-1]):
            raise ValueError(f'Source dimensions changed: {filename}')
        sources.append({'id': sheet_id, 'path': local(source), 'sha256': sha(source),
                        'size_px': list(image.size), 'reference_height_px': height,
                        'calibration': 'One shared standing body scale; translated foot supports measured per cell.'})
        for index, (ident, anchor) in enumerate(entries):
            col, row = index % 2, index // 2
            box = (xs[col], ys[row], xs[col + 1], ys[row + 1])
            cell = image.crop(box)
            path = BATCH / 'frames' / f'{ident}.png'
            _immutable_png(cell, path)
            b = cell.getchannel('A').point(lambda a: 255 if a >= 128 else 0).getbbox()
            raw[ident] = {'path': local(path), 'sha256': sha(path), 'source_path': local(source),
                          'source_sha256': sha(source), 'crop_xyxy': list(box),
                          'size_px': list(cell.size), 'reference_height_px': height,
                          'anchor_px': list(anchor), 'anchor_kind': 'anatomical-foot-support',
                          'anchor_method': 'Foot-contact center in full original cell; tail excluded.',
                          'sheet_id': sheet_id, 'visible_box_alpha128': list(b)}
    single = BATCH / 'source/gaze-up-right.png'
    image = Image.open(single).convert('RGBA')
    path = BATCH / 'frames/gaze_up_right.png'
    _immutable_png(image, path)
    raw['gaze_up_right'] = {'path': local(path), 'sha256': sha(path), 'source_path': local(single),
                           'source_sha256': sha(single), 'crop_xyxy': [0, 0, *image.size],
                           'size_px': list(image.size), 'reference_height_px': 1116,
                           'anchor_px': [575, 1243], 'anchor_kind': 'anatomical-foot-support',
                           'anchor_method': 'Foot-contact center, original single image; tail excluded.',
                           'sheet_id': 'gaze-right-single',
                           'visible_box_alpha128': list(image.getchannel('A').point(lambda a: 255 if a >= 128 else 0).getbbox())}
    sources.append({'id': 'gaze-right-single', 'path': local(single), 'sha256': sha(single),
                    'size_px': list(image.size), 'reference_height_px': 1116})
    previous_path = ROOT / 'assets/library/characters/tora/generation-batches/catalan-20261112-01a1cd57/registration.json'
    previous = json.loads(previous_path.read_text())
    for ident, row in previous['frames'].items():
        raw[ident] = dict(row, source_class='reused-preproduction',
                          source_path=previous['source_sheet'], source_sha256=previous['source_sha256'])
    raw_registration = BATCH / 'registration.json'
    raw_record = {'schema_version': 1, 'kind': 'catalan-original-acting-cells', 'character_id': 'tora',
                  'owner': 'codex:catalan-production:01a1cd57', 'raw_source_pixels_modified': False,
                  'neutral_original_modified': False, 'raw_new_drawings': 9,
                  'reused_preproduction_drawings': 4, 'sheets': sources,
                  'poses': raw, 'status': 'original-cells-registered-runtime-review-separate',
                  'scale_policy': 'One common physical scale within each raw sheet. No pose bbox fit.',
                  'reused_registration': {'path': local(previous_path), 'sha256': sha(previous_path)}}
    if raw_registration.exists():
        if json.loads(raw_registration.read_text()) != raw_record:
            raise FileExistsError('Raw Catalan registration already differs')
    else:
        raw_registration.write_text(json.dumps(raw_record, ensure_ascii=False, indent=2) + '\n')

    cache = {key: Image.open(resolve(row['path'])).convert('RGBA') for key, row in raw.items()}
    reports = {}

    # Arm regions are in the adopted 1254px canvas.  A neutral head is always
    # in front of raised arms, and its tail remains behind the unchanged trunk.
    right_polygon = [(720, 715), (810, 675), (895, 600), (1030, 520),
                     (1130, 585), (1080, 755), (925, 885), (880, 940), (720, 955)]
    left_polygon = [(1244 - x, y) for x, y in right_polygon]
    protect_head = Image.new('L', base.size)
    ImageDraw.Draw(protect_head).rectangle((0, 0, 1254, 706), fill=255)
    tail_protection = Image.new('L', base.size)
    ImageDraw.Draw(tail_protection).polygon([(916, 710), (1100, 710), (1100, 1100),
                                           (815, 1100), (850, 987), (886, 938),
                                           (913, 880), (917, 805), (906, 760)], fill=255)
    authored_arm_polygons = {
        'wave_raise': [(365, 323), (385, 303), (408, 287), (432, 291), (447, 308),
                       (446, 331), (435, 350), (412, 366), (382, 376), (365, 371)],
        'wave_high_in': [(365, 322), (386, 300), (397, 274), (400, 253), (416, 246),
                         (434, 247), (449, 259), (454, 281), (448, 305), (438, 329),
                         (425, 349), (404, 363), (382, 374), (365, 371)],
        'wave_high_out': [(365, 323), (390, 305), (403, 283), (416, 271), (437, 273),
                          (453, 286), (458, 305), (452, 325), (439, 345), (416, 365),
                          (386, 379), (365, 372)],
        'guide_after': [(363, 320), (397, 303), (443, 277), (466, 272), (483, 281),
                        (488, 299), (477, 317), (452, 335), (419, 355), (386, 370), (366, 365)],
        'guide_inside': [(232, 323), (201, 310), (175, 293), (143, 280), (114, 270),
                         (94, 279), (86, 295), (90, 313), (110, 331), (145, 349),
                         (180, 367), (213, 375), (232, 365)],
        'explain_left': [(266, 332), (230, 320), (210, 320), (190, 335), (177, 326),
                         (164, 316), (147, 310), (136, 317), (135, 337), (121, 344),
                         (113, 359), (115, 374), (128, 384), (153, 390), (185, 389),
                         (210, 385), (235, 375), (263, 350)],
        'realise': [(266, 340), (250, 318), (235, 315), (216, 322), (201, 345),
                    (194, 367), (204, 386), (224, 386), (246, 371), (268, 349)],
    }

    def arm_mask(side):
        mask = Image.new('L', base.size)
        draw = ImageDraw.Draw(mask)
        if side in ('left', 'both'):
            draw.polygon(left_polygon, fill=255)
        if side in ('right', 'both'):
            draw.polygon(right_polygon, fill=255)
        mask = ImageChops.subtract(mask, protect_head)
        mask = ImageChops.subtract(mask, tail_protection)
        return mask.filter(ImageFilter.GaussianBlur(1.3))

    def transform(ident):
        if raw[ident].get('source_class') == 'reused-preproduction':
            return 1.90, (23, 77)
        if raw[ident]['sheet_id'] == 'acting-a':
            return 1.95, (37, 79)
        return 1.956, (31 if ident != 'gaze_up_left' else 45, 91)

    def arms(ident, side, initial=None):
        result = (initial or base).copy()
        source_ident = 'wave_high_in' if ident == 'wave_high_out' else ident
        scale, shift = transform(source_ident)
        source = cache[source_ident]
        aligned = Image.new('RGBA', base.size)
        source = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
        aligned.paste(source, shift)
        # The generated sheet's tail is farther left than the adopted tail.
        # Remove that source tail from this local repair, then restore the
        # adopted tail in its own anatomical envelope before the arm overlay.
        if side in ('right', 'both'):
            clear_tail = Image.new('L', base.size)
            ImageDraw.Draw(clear_tail).polygon([(860, 735), (1254, 735), (1254, 1100),
                                                (810, 1100), (860, 950)], fill=255)
            aligned.putalpha(ImageChops.subtract(aligned.getchannel('A'), clear_tail))
        mask = arm_mask(side)
        result = Image.composite(aligned, result, mask)
        if side in ('right', 'both'):
            result = Image.composite(base, result, tail_protection)
        # Only an explicitly traced forearm may cover the head.  Copying the
        # whole source cheek here would duplicate whiskers/face contours.
        source_mask = Image.new('L', cache[source_ident].size)
        draw_mask = ImageDraw.Draw(source_mask)
        if ident == 'explain_two':
            if side in ('left', 'both'):
                draw_mask.polygon(authored_arm_polygons['explain_left'], fill=255)
            if side in ('right', 'both'):
                draw_mask.polygon([(626 - x, y) for x, y in authored_arm_polygons['explain_left']], fill=255)
        else:
            draw_mask.polygon(authored_arm_polygons[source_ident], fill=255)
        source_mask = source_mask.filter(ImageFilter.MaxFilter(17))
        if raw[source_ident]['sheet_id'] == 'acting-a' and side == 'right':
            # Exclude whisker tips above the raised paw while retaining its
            # complete antialiased contour below/right of the cheek.
            ImageDraw.Draw(source_mask).rectangle((453, 0, source_mask.width, 272), fill=0)
            ImageDraw.Draw(source_mask).rectangle((440, 335, source_mask.width, source_mask.height), fill=0)
        elif ident == 'guide_after':
            ImageDraw.Draw(source_mask).rectangle((452, 342, source_mask.width, source_mask.height), fill=0)
        elif ident == 'explain_two' and side in ('right', 'both'):
            ImageDraw.Draw(source_mask).rectangle((450, 392, source_mask.width, source_mask.height), fill=0)
        source_mask = source_mask.filter(ImageFilter.GaussianBlur(3.0))
        foreground = cache[source_ident].copy()
        foreground.putalpha(ImageChops.multiply(foreground.getchannel('A'), source_mask))
        foreground = foreground.resize((round(foreground.width * scale), round(foreground.height * scale)), Image.Resampling.LANCZOS)
        arm_layer = Image.new('RGBA', base.size)
        arm_layer.alpha_composite(foreground, shift)
        if ident == 'wave_high_out':
            arm_layer = arm_layer.rotate(-7, resample=Image.Resampling.BICUBIC,
                                         center=(765, 775), expand=False)
        result.alpha_composite(arm_layer)
        reports.setdefault(ident, {})['arms'] = {'side': side, 'source_to_canonical': {'scale': scale, 'translate_xy': list(shift)},
                                              'replace_polygon_canonical': right_polygon if side == 'right' else left_polygon,
                                              'head_silhouette_protected': True, 'tail_protected': True,
                                              'authored_forearm_only_above_neck': True, 'feather_px': 1.3,
                                              'actual_source_id': source_ident,
                                              'local_forearm_rotation_deg': -7 if ident == 'wave_high_out' else 0,
                                              'rotation_pivot_canonical_px': [765, 775] if ident == 'wave_high_out' else None,
                                              'whole_actor_rotation': False}
        return result

    targets = [(435, 363, 567, 541), (679, 363, 811, 541)]
    eye_windows = {
        'watch_up': [(217, 129, 291, 223), (340, 129, 414, 223)],
        'gaze_up_left': [(196, 142, 272, 238), (324, 142, 400, 238)],
        'gaze_up_right': [(370, 374, 521, 575), (618, 374, 769, 575)],
        'blink_half': [(206, 164, 282, 260), (333, 164, 409, 260)],
        'blink_closed': [(198, 169, 274, 265), (326, 169, 402, 265)],
    }

    def eyes(ident, initial=None):
        result = (initial or base).copy()
        regions = []
        for source_box, target_box in zip(eye_windows[ident], targets):
            size = (target_box[2] - target_box[0], target_box[3] - target_box[1])
            patch = cache[ident].crop(source_box).resize(size, Image.Resampling.LANCZOS)
            aligned = base.copy()
            mask = Image.new('L', base.size)
            if ident == 'blink_closed':
                # Replace the open eye with unmarked adopted cheek paper, then
                # transfer only the authored eyelid ink.  Generated skin is
                # deliberately not pasted as a visible pale oval.
                clear_box = (target_box[0] - 20, target_box[1] - 20,
                             target_box[2] + 20, target_box[3] + 20)
                clear_size = (clear_box[2] - clear_box[0], clear_box[3] - clear_box[1])
                paper = base.crop((555, 580, 685, 680)).resize(clear_size, Image.Resampling.LANCZOS)
                channels = list(paper.split())
                channels[1] = channels[1].point(lambda value: min(255, value + 3))
                channels[2] = channels[2].point(lambda value: min(255, value + 8))
                paper = Image.merge('RGBA', channels)
                aligned.paste(paper, clear_box[:2])
                ImageDraw.Draw(mask).ellipse(clear_box, fill=255)
                mask = mask.filter(ImageFilter.GaussianBlur(8.0))
                protected_mouth = Image.new('L', base.size)
                mouth = base.crop((548, 470, 700, 566))
                ink = Image.new('L', mouth.size)
                ink.putdata([255 if a >= 128 and r < 180 and g < 125 and b < 95 else 0
                             for r, g, b, a in mouth.getdata()])
                protected_mouth.paste(ink, (548, 470))
                mask = ImageChops.subtract(mask, protected_mouth)
                result = Image.composite(aligned, result, mask)
                alpha = Image.new('L', patch.size)
                alpha.putdata([max(0, min(255, round((190 - (r + g + b) / 3) * 4)))
                               if 75 < y < 125 else 0
                               for y in range(patch.height)
                               for r, g, b, a in list(patch.crop((0, y, patch.width, y + 1)).getdata())])
                patch.putalpha(ImageChops.multiply(patch.getchannel('A'), alpha))
                result.alpha_composite(patch, target_box[:2])
            else:
                aligned.paste(patch, target_box[:2])
                ImageDraw.Draw(mask).ellipse(target_box, fill=255)
                mask = mask.filter(ImageFilter.GaussianBlur(1.0))
                result = Image.composite(aligned, result, mask)
            regions.append({'source_xyxy': source_box, 'canonical_xyxy': list(target_box),
                            'resized_px': list(size), 'feather_px': 8 if ident == 'blink_closed' else 1,
                            'canonical_paper_fill_and_authored_ink_only': ident == 'blink_closed'})
        reports.setdefault(ident, {})['eyes'] = regions
        return result

    images = {'neutral': base, 'watch_up': eyes('watch_up'),
              'gaze_up_left': eyes('gaze_up_left'), 'gaze_up_right': eyes('gaze_up_right'),
              'blink_half': eyes('blink_half'), 'blink_closed': eyes('blink_closed')}
    for ident in ('wave_raise', 'wave_high_in', 'wave_high_out', 'guide_after'):
        images[ident] = arms(ident, 'right')
    images['guide_inside'] = arms('guide_inside', 'left')
    images['explain_two'] = arms('explain_two', 'both')
    images['present_left_half'] = arms('explain_two', 'left')
    images['realise_half'] = arms('realise', 'left')
    images['two_half'] = arms('wave_raise', 'right', images['realise_half'])
    # A short open-mouth reaction keeps the exact canonical eye artwork.
    mouth_source = (275, 213, 353, 300)
    mouth_target = (548, 470, 700, 640)
    patch = cache['realise'].crop(mouth_source).resize((152, 170), Image.Resampling.LANCZOS)
    aligned = base.copy()
    aligned.paste(patch, mouth_target[:2])
    mask = Image.new('L', base.size)
    ImageDraw.Draw(mask).ellipse(mouth_target, fill=255)
    images['realise'] = Image.composite(aligned, images['realise_half'], mask.filter(ImageFilter.GaussianBlur(1.1)))
    reports['realise']['mouth'] = {'source_xyxy': list(mouth_source), 'canonical_xyxy': list(mouth_target)}
    derivations = {
        'neutral': [], 'watch_up': ['watch_up'], 'gaze_up_left': ['gaze_up_left'],
        'gaze_up_right': ['gaze_up_right'], 'blink_half': ['blink_half'], 'blink_closed': ['blink_closed'],
        'wave_raise': ['wave_raise'], 'wave_high_in': ['wave_high_in'], 'wave_high_out': ['wave_high_in'],
        'guide_inside': ['guide_inside'], 'guide_after': ['guide_after'],
        'explain_two': ['explain_two'], 'present_left_half': ['explain_two'],
        'realise_half': ['realise'], 'two_half': ['realise', 'wave_raise'], 'realise': ['realise']}
    rows = {}
    for ident, image in images.items():
        path = output / f'{ident}.png'
        image.save(path)
        difference = ImageChops.difference(base, image)
        changed = ImageChops.lighter(*difference.split()[:2])
        for channel in difference.split()[2:]:
            changed = ImageChops.lighter(changed, channel)
        rows[ident] = {'path': local(path), 'sha256': sha(path), 'size_px': list(image.size),
                       'reference_height_px': 1057, 'anchor_px': [646, 1181],
                       'anchor_kind': 'canonical-anatomical-foot-support',
                       'local_derivation': {'base_path': local(CANONICAL), 'base_sha256': CANONICAL_SHA256,
                                            'source_ids': derivations[ident],
                                            'source_rows': [raw[key] for key in derivations[ident]],
                                            'changed_bbox_xyxy': list(changed.getbbox()) if changed.getbbox() else None,
                                            'source_pngs_modified': False, 'whole_actor_fade': False}}
    record = {'schema_version': 1, 'kind': 'catalan-canonical-body-local-art-runtime', 'character_id': 'tora',
              'scope': 'catalan-counting-001-v001', 'runtime_composited': True,
              'status': 'candidate-awaiting-native-review', 'production_ready': False,
              'body_base': {'path': local(CANONICAL), 'sha256': CANONICAL_SHA256, 'reference_height_px': 1057,
                            'anchor_px': [646, 1181]},
              'raw_registration': {'path': local(raw_registration), 'sha256': sha(raw_registration)},
              'poses': rows, 'local_compositing': reports, 'source_pngs_modified': False,
              'raw_new_drawings': 9, 'reused_preproduction_drawings': 4,
              'runtime_sprites': len(rows), 'notes': 'Runtime images are explicit edited derivatives, not independent generated drawings. Canonical head outline, trunk, feet and tail retained.'}
    registration = output / 'registration.json'
    registration.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    order = list(images)
    font = ImageFont.truetype(str(ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'), 21)
    for variant, color in [('light', '#fff8eb'), ('dark', '#33414a')]:
        sheet = Image.new('RGBA', (2400, math.ceil(len(order) / 5) * 500), color)
        draw = ImageDraw.Draw(sheet)
        for i, ident in enumerate(order):
            scale = 400 / 1057
            sprite = images[ident].resize((round(1254 * scale), round(1254 * scale)), Image.Resampling.LANCZOS)
            x, y = (i % 5) * 480, (i // 5) * 500
            xy = (round(x + 240 - 646 * scale), round(y + 470 - 1181 * scale))
            sheet.alpha_composite(sprite, xy)
            draw.text((x + 12, y + 10), ident, font=font, fill='#544b42' if variant == 'light' else '#fff8eb')
        sheet.convert('RGB').save(output / f'contact-{variant}-400px.png')
    return registration


def preview_art(registration, output, timeline=None):
    """Write a native 30fps acting study and meaningful local-art checks."""
    import subprocess
    output = resolve(output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    plan = json.loads(resolve(timeline).read_text()) if timeline else None
    configure_animation(plan, registration)
    schedule = _schedule
    font = ImageFont.truetype(str(ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'), 30)
    named = [('wave-round-trip', wave_sequence()),
             ('inside-presentation-and-return', present_sequence('inside', 18)),
             ('after-presentation-and-return', present_sequence('after', 18)),
             ('two-groups-and-return', two_groups_sequence()),
             ('realisation-and-return', realise_sequence()),
             ('blink-both-directions', hold('neutral', 6) + blink_sequence() + hold('neutral', 6)),
             ('ribbon-tip-gaze', hold('gaze_up_left', 10) + hold('watch_up', 7)
              + hold('gaze_up_right', 10) + hold('neutral', 7))]
    frames, records, strips = [], [], []
    for label, poses in named:
        poses = hold('neutral', 6) + poses + hold('neutral', 6)
        start = len(frames)
        selected = set(round(j * (len(poses) - 1) / 8) for j in range(9))
        strip = Image.new('RGB', (1920, 1155), 'white')
        sd = ImageDraw.Draw(strip)
        selected_index = 0
        for index, pose in enumerate(poses):
            frame = Image.new('RGBA', (1920, 1080), '#fff8eb')
            # Use the public sprite placement, with explicit overridden drawing
            # for this finite action reel; the exact pose sequence is recorded.
            sprite, row, scale = _artwork.sprite(pose, 400)
            foot = (960, 1010)
            xy = tuple(round(foot[j] - row['anchor_px'][j] * scale) for j in (0, 1))
            frame.alpha_composite(sprite, xy)
            ImageDraw.Draw(frame).text((80, 70), f'{label} | {pose}', font=font, fill='#544b42')
            ImageDraw.Draw(frame).text((80, 120), '400 px body / fixed anatomical foot / 30 fps / silent art study', font=font, fill='#766f60')
            actual = [xy[j] + row['anchor_px'][j] * scale for j in (0, 1)]
            records.append({'reel_frame': len(frames), 'pose': pose, 'action': label,
                            'target_foot': list(foot), 'actual_foot': actual,
                            'delta_x': actual[0] - foot[0], 'delta_y': actual[1] - foot[1]})
            rgb = frame.convert('RGB')
            if index in selected:
                x, y = selected_index % 3 * 640, selected_index // 3 * 385
                strip.paste(rgb.resize((640, 360), Image.Resampling.LANCZOS), (x, y))
                sd.text((x + 8, y + 363), f'{index / FPS:.3f}s | {pose}', fill='black')
                selected_index += 1
            frames.append(rgb)
        strip.save(output / f'{label}-contact.jpg', quality=95)
        strips.append({'action': label, 'start_frame': start, 'end_frame': len(frames),
                       'pose_frames': poses, 'contact': local(output / f'{label}-contact.jpg')})
    video = output / 'acting-native-400px-30fps.mp4'
    command = [str(ROOT / '.venv/bin/ffmpeg'), '-v', 'error', '-y', '-f', 'rawvideo',
               '-pixel_format', 'rgb24', '-video_size', '1920x1080', '-framerate', str(FPS),
               '-i', '-', '-an', '-c:v', 'libx264', '-crf', '17', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(video)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in frames:
            process.stdin.write(frame.tobytes())
    finally:
        process.stdin.close()
    if process.wait():
        raise RuntimeError('Native Catalan acting preview encoding failed')
    base = Image.open(CANONICAL).convert('RGBA')
    invariants = []
    for ident, image in _artwork.images.items():
        checks = {}
        for key, box in {'anatomical_feet_and_legs': (0, 1060, 1254, 1254),
                         'upper_head_outline': (0, 0, 1254, 320),
                         'central_trunk': (560, 850, 680, 1040)}.items():
            difference = ImageChops.difference(base.crop(box), image.crop(box))
            checks[key] = all(channel.getbbox() is None for channel in difference.split())
        if ident in {'wave_raise', 'wave_high_in', 'wave_high_out', 'guide_after', 'two_half'}:
            checks['floating_old_arm_absent'] = image.getchannel('A').crop((891, 815, 908, 875)).point(lambda a: 255 if a >= 64 else 0).getbbox() is None
        invariants.append({'pose': ident, 'checks': checks, 'passed': all(checks.values())})
    negative = []
    old = BATCH / 'runtime-candidates/v001/wave_high_in.png'
    if old.exists():
        image = Image.open(old).convert('RGBA')
        detected = image.getchannel('A').crop((891, 815, 908, 875)).point(lambda a: 255 if a >= 64 else 0).getbbox() is not None
        negative.append({'fixture': local(old), 'fixture_sha256': sha(old),
                         'defect': 'floating obsolete arm contour inside tail gap', 'detected': detected})
    report = {'kind': 'catalan-native-art-study', 'status': 'native-preview-rendered-pending-final-episode',
              'registration': {'path': local(resolve(registration)), 'sha256': sha(resolve(registration))},
              'renderer': {'path': local(Path(__file__)), 'sha256': sha(Path(__file__))},
              'video': {'path': local(video), 'sha256': sha(video), 'frames': len(frames), 'fps': FPS,
                        'resolution_px': [1920, 1080], 'duration_s': len(frames) / FPS},
              'actions': strips, 'frame_placement': records, 'invariants': invariants,
              'negative_controls': negative, 'all_invariants_passed': all(row['passed'] for row in invariants),
              'both_axis_support_passed': all(abs(row['delta_x']) <= .5 and abs(row['delta_y']) <= .5 for row in records),
              'schedule': schedule.receipt(),
              'not_checked': ['finished episode encoding', 'speech synchronisation', 'long count continuity', 'all-frame human viewing']}
    (output / 'native-preview.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-art', action='store_true')
    parser.add_argument('--preview-art', action='store_true')
    parser.add_argument('--out-dir')
    parser.add_argument('--registration')
    parser.add_argument('--timeline')
    args = parser.parse_args()
    if args.build_art:
        if not args.out_dir:
            parser.error('--build-art requires a new --out-dir')
        print(build_art(args.out_dir))
    elif args.preview_art:
        if not args.out_dir or not args.registration:
            parser.error('--preview-art requires --out-dir and --registration')
        result = preview_art(args.registration, args.out_dir, args.timeline)
        print(json.dumps({key: result[key] for key in ['video', 'all_invariants_passed', 'both_axis_support_passed']}, ensure_ascii=False))
