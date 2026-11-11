"""Add registered kangaroo acting to the prime film while copying its AAC stream.

The actor-free learning canvas is cached by original scene state. Keyframe
sprites are composited at their measured physical scale and foot anchors. The
math fields, source speech and 30fps scene timings stay byte-bound to v001.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, asdict
from functools import lru_cache
from itertools import groupby
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageDraw

try:
    import render_prime_video as previous
    import kangaroo_animation as animation
    from build_prime_episode import read, save_new, digest, local, ROOT, VIDEO_NAME
except ModuleNotFoundError:
    from tools import render_prime_video as previous
    from tools import kangaroo_animation as animation
    from tools.build_prime_episode import read, save_new, digest, local, ROOT, VIDEO_NAME

FPS = 30
OLD = ROOT / 'output/prime-counting-001-v001'
OUT = ROOT / 'output/prime-counting-001-v002'


@dataclass(frozen=True)
class Frame:
    mode: str
    value: int | None = None
    diagram_alpha: int = 255
    cream: int = 0
    pose: str = 'neutral'
    actor_y: int = 0


class AbsentCharacter:
    def draw(self, image):
        pass


class Scene:
    def __init__(self, plan, registration=None):
        self.plan = plan
        self.base = previous.Scene(plan)
        # Remove the old static character before any image is rendered, rather
        # than covering it with a rectangle or dissolving two full characters.
        self.base.character = AbsentCharacter()
        self.duration = self.base.duration
        self.frame_count = self.base.frame_count
        self.segments = self.base.segments
        self.starts = self.base.starts
        receipt = plan.get('kangaroo_animation', {}).get('registration', {})
        registration = registration or receipt.get('path') or animation.DEFAULT_REGISTRATION
        if receipt.get('sha256') and digest(animation.resolve(registration)) != receipt['sha256']:
            raise ValueError('Animation registration differs from the measured revision')
        self.character = animation.Artwork(registration)
        self.schedule = animation.Schedule(plan, self.character.frames.keys())
        self.cream = Image.new('RGBA', previous.m.SIZE, previous.m.CREAM)
        self.validation = self.base.validation
        self.actor_reports = {}

    def state(self, index):
        base = self.base.state(index)
        actor = self.schedule.state(index)
        return Frame(base.mode, base.value, base.diagram_alpha, base.cream, actor.pose, actor.offset_y)

    @lru_cache(maxsize=32)
    def learning_layer(self, mode, value, diagram_alpha):
        image, report = self.base.image(previous.Frame(mode, value, diagram_alpha, 0))
        return image.convert('RGBA'), report

    def image(self, state):
        background, base_report = self.learning_layer(state.mode, state.value, state.diagram_alpha)
        image = background.copy()
        actor = animation.ActorState(state.pose, state.actor_y)
        self.character.draw(image, actor)
        if state.cream:
            image = Image.blend(image, self.cream, state.cream / 255)
        actor_key = (state.pose, state.actor_y)
        report = self.actor_reports.setdefault(actor_key, {'pose': state.pose, 'offset_y_px': state.actor_y,
            'visible_bounds_px': self.character.bounds(actor), 'foot_root_px': list(self.character.root),
            'source_group_scale': self.character.scales[state.pose], 'grounded': state.actor_y == 0,
            'support': self.character.support(actor)})
        return image.convert('RGB'), {**base_report, 'state': asdict(state), 'actor': report}


def prepare_revision(source_timeline, out, registration, source_movie):
    plan = deepcopy(read(source_timeline))
    if not source_movie.is_file():
        raise ValueError('Original final AAC source movie is required')
    for key in ('speech_manifest', 'speech_acceptance'):
        item = plan[key]
        if digest(animation.resolve(item['path'])) != item['sha256']:
            raise ValueError(f'Frozen adopted speech evidence differs: {key}')
    if digest(animation.resolve(plan['master_audio']['path'])) != plan['master_audio']['sha256']:
        raise ValueError('Original accepted PCM master differs')
    plan['revision_id'] = 'prime-counting-v002'
    plan['renderer_implementation'] = 'tools/render_prime_video_v002.py'
    plan['source_timeline'] = {'path': local(source_timeline), 'sha256': digest(source_timeline)}
    plan['kangaroo_animation'] = {'registration': {'path': local(registration), 'sha256': digest(registration)},
        'schedule': {'path': local(out / 'kangaroo-motion.json')},
        'body_height_px': animation.BODY_HEIGHT, 'foot_root_px': list(animation.FOOT_ROOT)}
    plan['reused_final_aac'] = {'path': local(source_movie), 'sha256': digest(source_movie),
        'method': 'Existing encoded AAC packets copied; no speech synthesis, time stretch, gain or lossy re-encoding.'}
    return plan


def stage(scene, folder):
    folder.mkdir(parents=True, exist_ok=False)
    cache, runs, reports = {}, [], []
    lines = ['ffconcat version 1.0']
    end = 0
    for state, group in groupby(scene.state(i) for i in range(scene.frame_count)):
        if state not in cache:
            name = f'frame-{len(cache):04d}.png'
            image, report = scene.image(state)
            image.save(folder / name, compress_level=1)
            cache[state] = name
            reports.append({**report, 'file': name, 'sha256': digest(folder / name)})
            if len(cache) % 100 == 0:
                print(json.dumps({'staged_images': len(cache), 'at_frame': end}), flush=True)
        name = cache[state]
        start = end
        end += sum(1 for _ in group)
        microseconds = round(end * 1e6 / FPS) - round(start * 1e6 / FPS)
        lines.extend((f"file '{name}'", f'option framerate {FPS}', f'duration {microseconds / 1e6:.6f}'))
        runs.append({'start_frame': start, 'end_frame': end, 'frame_count': end - start,
                     'start_s': start / FPS, 'end_s': end / FPS, 'file': name, **asdict(state)})
    if end != scene.frame_count:
        raise ValueError('Animation staging did not cover the original frame interval')
    lines.extend((f"file '{name}'", f'option framerate {FPS}'))
    index = folder / 'frames.ffconcat'
    index.write_text('\n'.join(lines) + '\n', encoding='ascii')
    return index, runs, reports


def encode(index, original_aac_movie, destination, frames, ffmpeg, preset, crf):
    filters = (f'scale=in_range=full:out_range=limited:out_color_matrix=bt709,'
        f'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,'
        f'fps={FPS},trim=end_frame={frames}')
    command = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-stats', '-stats_period', '10',
        '-nostdin', '-n', '-f', 'concat', '-safe', '0', '-i', str(index), '-i', str(original_aac_movie),
        '-map', '0:v:0', '-map', '1:a:0', '-vf', filters, '-c:v', 'libx264', '-preset', preset,
        '-crf', str(crf), '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-color_primaries', 'bt709',
        '-color_trc', 'bt709', '-colorspace', 'bt709', '-c:a', 'copy', '-movflags', '+faststart', str(destination)]
    with destination.with_suffix('.ffmpeg.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    return command


def aac_hash(movie, ffmpeg):
    command = [ffmpeg, '-nostdin', '-v', 'error', '-i', str(movie), '-map', '0:a:0',
               '-c:a', 'copy', '-f', 'adts', 'pipe:1']
    return __import__('hashlib').sha256(subprocess.check_output(command)).hexdigest()


def preview(scene, out, ffmpeg):
    """A short actual 30fps silent montage for reviewing acting, not the lesson."""
    shots = [
        ('Opening wave', 1.0, 3.0),
        ('Thinking', next(a.start_frame / FPS for a in scene.schedule.actions if a.name == 'factor-thinking'), 2.3),
        ('Milestone hop', next(a.start_frame / FPS for a in scene.schedule.actions if a.name == 'halfway-hop') - .2, 1.7),
        ('Finale joy', scene.plan['finale']['start_s'] + 1.2, 2.0),
        ('Goodbye wave', scene.plan['finale']['start_s'] + 15.9, 2.3),
    ]
    destination = out / 'animation-preview.mp4'
    command = [ffmpeg, '-nostdin', '-v', 'error', '-n', '-f', 'rawvideo', '-pixel_format', 'rgb24',
        '-video_size', '960x540', '-framerate', str(FPS), '-i', 'pipe:0', '-an', '-c:v', 'libx264',
        '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(destination)]
    actor_destination = out / 'animation-actor-preview.mp4'
    actor_command = [ffmpeg, '-nostdin', '-v', 'error', '-n', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '550x680', '-framerate', str(FPS), '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(actor_destination)]
    thumbs = []
    with subprocess.Popen(command, stdin=subprocess.PIPE) as process, subprocess.Popen(actor_command, stdin=subprocess.PIPE) as actor_process:
        for label, start, duration in shots:
            for step in range(round(duration * FPS)):
                index = min(scene.frame_count - 1, round(start * FPS) + step)
                image, _ = scene.image(scene.state(index))
                small = image.resize((960, 540), Image.Resampling.LANCZOS)
                process.stdin.write(small.tobytes())
                actor_process.stdin.write(image.crop((1370,400,1920,1080)).tobytes())
                if step in (0, round(duration * FPS) // 2):
                    thumbs.append((label, small.copy(), index / FPS))
        process.stdin.close()
        actor_process.stdin.close()
        if actor_process.wait():
            raise ValueError('Native-size actor preview encoding failed')
        if process.wait():
            raise ValueError('Animation preview encoding failed')
    sheet = Image.new('RGB', (1920, math.ceil(len(thumbs) / 2) * 580), previous.m.CREAM)
    draw = ImageDraw.Draw(sheet)
    for index, (label, image, at) in enumerate(thumbs):
        x, y = index % 2 * 960, index // 2 * 580
        sheet.paste(image, (x, y))
        draw.text((x + 12, y + 546), f'{label} — {at:.3f}s', font=previous.m.font(22), fill=previous.m.INK)
    sheet.save(out / 'animation-preview-contact-sheet.jpg', quality=92)
    keypose_sheets = []
    groups = [
        ('wave', 'opening-wave', ['neutral','wave_raise','wave_high','wave_left','wave_right','settle','neutral']),
        ('thought', 'nine-discovery', ['neutral','think_raise','think','aha','neutral']),
        ('hop', 'halfway-hop', ['neutral','posture_neutral','crouch_half','crouch_down','takeoff','hop_air','land','crouch_half','posture_neutral','neutral']),
        ('face', 'blink-001', ['neutral','blink_half','blink_closed','blink_half','neutral','smile_open']),
    ]
    for name, action_id, poses in groups:
        action = next(row for row in scene.schedule.actions if row.name == action_id)
        underlying = scene.base.state(action.start_frame)
        board = Image.new('RGB', (1650, math.ceil(len(poses) / 3) * 720), previous.m.CREAM)
        labels = ImageDraw.Draw(board)
        for number, pose in enumerate(poses):
            if pose not in scene.character.frames:
                continue
            lift = -60 if pose == 'hop_air' else 0
            image, _ = scene.image(Frame(underlying.mode, underlying.value, underlying.diagram_alpha, underlying.cream, pose, lift))
            x, y = number % 3 * 550, number // 3 * 720
            board.paste(image.crop((1370,400,1920,1080)), (x,y))
            labels.text((x+12,y+686), f'{number+1}. {pose}  lift={-lift}px', font=previous.m.font(20), fill=previous.m.INK)
        path = out / f'animation-{name}-keyposes-native.png'
        board.save(path)
        keypose_sheets.append({'action':name,'path':local(path),'sha256':digest(path),
                              'native_actor_height_px':430,'poses':poses})
    return {'path': local(destination), 'sha256': digest(destination), 'fps': FPS, 'silent': True,
            'scope': 'Edited short acting-review montage; full production timing/audio are separate.',
            'native_size_actor_preview':{'path':local(actor_destination),'sha256':digest(actor_destination),'body_height_px':430,'crop':[1370,400,1920,1080]},
            'native_size_keypose_contact_sheets':keypose_sheets,
            'clips': [{'name': label, 'source_start_s': start, 'duration_s': duration} for label, start, duration in shots]}


def copy_deliveries(out):
    for name in ('english-captions.srt', 'subtitles.srt', 'chapters.txt', 'youtube-title.txt',
                 'youtube-description.txt', 'upload-details.txt', 'master.wav'):
        with (out / name).open('xb') as target:
            with (OLD / name).open('rb') as source:
                shutil.copyfileobj(source, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-timeline', type=Path, default=OLD / 'timeline.json')
    parser.add_argument('--registration', type=Path, default=animation.DEFAULT_REGISTRATION)
    parser.add_argument('--audio-source', type=Path, default=OLD / VIDEO_NAME)
    parser.add_argument('--out-dir', type=Path, default=OUT)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--preset', default='veryfast')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--preview-only', action='store_true')
    parser.add_argument('--skip-preview', action='store_true')
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    registration = args.registration.resolve()
    timeline_file, motion_file = out / 'timeline.json', out / 'kangaroo-motion.json'
    if any(path.exists() for path in (timeline_file, motion_file, out / 'render-record.json', out / VIDEO_NAME)):
        raise FileExistsError('Choose a new v002 output directory; existing artifacts are preserved')
    plan = prepare_revision(args.source_timeline.resolve(), out, registration, args.audio_source.resolve())
    scene = Scene(plan, registration)
    for action in scene.schedule.actions:
        for state in set(action.frames):
            scene.character.bounds(state)
    motion = {**scene.schedule.receipt(), 'artwork': scene.character.receipt()}
    save_new(motion_file, motion)
    plan['kangaroo_animation']['schedule']['sha256'] = digest(motion_file)
    save_new(timeline_file, plan)
    preview_record = None if args.skip_preview else preview(scene, out, args.ffmpeg)
    if args.preview_only:
        save_new(out / 'preview-record.json', {'kind': 'prime-v002-acting-preview',
            'timeline_sha256': digest(timeline_file), 'motion_sha256': digest(motion_file),
            'artwork': scene.character.receipt(), 'preview': preview_record})
        print(json.dumps({'preview': preview_record, 'motion_actions': len(scene.schedule.actions)}), flush=True)
        return
    copy_deliveries(out)
    begin = time.perf_counter()
    index, runs, reports = stage(scene, out / '.work/frames-v002')
    save_new(out / 'frame-plan.json', {'schema_version': 1, 'fps': FPS,
        'duration_frames': scene.frame_count, 'timeline_sha256': digest(timeline_file),
        'image_directory': local(index.parent), 'runs': runs, 'distinct_images': len(reports), 'images': reports})
    movie = out / VIDEO_NAME
    command = encode(index, args.audio_source.resolve(), movie, scene.frame_count, args.ffmpeg, args.preset, args.crf)
    old_aac = aac_hash(args.audio_source.resolve(), args.ffmpeg)
    new_aac = aac_hash(movie, args.ffmpeg)
    if old_aac != new_aac:
        raise ValueError('AAC stream did not survive the visual-only remux unchanged')
    probe = json.loads(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_streams',
                                               '-show_format', '-of', 'json', str(movie)], text=True))
    record = {'schema_version': 1, 'kind': 'prime-animated-kangaroo-v002-render',
        'source_timeline': {'path': local(args.source_timeline), 'sha256': digest(args.source_timeline)},
        'timeline': local(timeline_file), 'timeline_sha256': digest(timeline_file),
        'motion': local(motion_file), 'motion_sha256': digest(motion_file),
        'renderer': local(Path(__file__)), 'renderer_sha256': digest(Path(__file__)),
        'animation_tool_sha256': digest(Path(animation.__file__)), 'artwork': scene.character.receipt(),
        'source_character': scene.character.receipt(),
        'frames': scene.frame_count, 'duration_s': scene.frame_count / FPS,
        'distinct_images': len(reports), 'holds': len(runs),
        'native_layout_checks_passed': all(report['underlying_layout_passed'] for report in reports),
        'actor_bounds_passed': True, 'original_speech_timing_preserved': True,
        'original_audio_adts_sha256': old_aac, 'output_audio_adts_sha256': new_aac,
        'encoded_audio_bitstream_identical': True, 'audio_codec_copy': True,
        'preview': preview_record, 'encode_command': command,
        'output': local(movie), 'output_sha256': digest(movie), 'probe': probe,
        'elapsed_s': time.perf_counter() - begin}
    save_new(out / 'render-record.json', record)
    print(json.dumps({'output': str(movie), 'frames': scene.frame_count,
        'distinct_images': len(reports), 'holds': len(runs), 'audio_identical': True,
        'elapsed_s': record['elapsed_s']}), flush=True)


if __name__ == '__main__':
    main()
