"""Portable entry point for adopted productions; original tools stay unchanged.

Run from any directory. Reproduction uses the adopted master and source assets,
so rendering does not require Node or speech models. Existing deliverables are
never overwritten. Generated previews, movies and QA go to a new --out-dir.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
ALIASES = {
    'decimal': 'counting-garden-blue-sky-production-v002',
    'binary': 'binary-counting-production-v005',
    'octal': 'octal-counting-production-v002',
    'hexadecimal': 'hexadecimal-counting-production-v002',
    'four-base': 'four-base-counting-production-v002',
    'even': 'even-counting-production-v002',
    'odd': 'odd-counting-production-v002',
    'prime': 'prime-counting-production-v003',
    'fibonacci': 'fibonacci-counting-production-v003',
}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def new_directory(value):
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def work_directory(value=None):
    candidate = value or os.environ.get('YOUTUBE_WORK_DIR')
    if candidate:
        path = Path(candidate).expanduser().resolve()
    elif os.name == 'nt' and Path('D:/temp').is_dir():
        path = Path('D:/temp').resolve()
    else:
        path = Path(tempfile.gettempdir()) / 'youtube-production'
    path.mkdir(parents=True, exist_ok=True)
    return path


def executable(name, explicit=None):
    requested = explicit or os.environ.get(name.upper()) or name
    found = shutil.which(requested)
    if not found:
        raise ValueError(f'{name} is unavailable: {requested}. Install it on PATH or pass --{name}.')
    return str(Path(found).resolve())


def module(name):
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    return importlib.import_module(name)


def production(value):
    catalog = read(ROOT / 'catalogs/library-v1.json')
    key = ALIASES.get(value, value)
    if key not in catalog['active_production_set_ids']:
        raise ValueError(f'Choose an adopted production: {", ".join(ALIASES)}')
    row = catalog['production_sets'][key]
    kind = next((alias for alias, item in ALIASES.items() if item == key), None)
    if kind is None:
        raise ValueError(f'This entry point has no adapter for {key}')
    return key, kind, row


def adopted_aliases():
    active = read(ROOT / 'catalogs/library-v1.json')['active_production_set_ids']
    return {alias: key for alias, key in ALIASES.items() if key in active}


def inputs(row, args):
    video = project_path(row['output'])
    timeline = project_path(args.timeline or row['timeline'])
    audio = project_path(args.audio or row.get('master') or video.with_name('master.wav'))
    motion = getattr(args, 'motion_manifest', None) or row.get('motion_manifest')
    return timeline, audio, project_path(motion) if motion else None


def require_file(path, expected=None):
    if not path.is_file():
        raise ValueError(f'Missing input: {path}. Restore the reproduction pack / run git lfs pull.')
    with path.open('rb') as stream:
        header = stream.read(128)
    if header.startswith(b'version https://git-lfs.github.com/spec/v1'):
        raise ValueError(f'Git LFS pointer has not been downloaded: {path}. Run git lfs pull.')
    if expected and sha256(path) != expected:
        raise ValueError(f'Input checksum differs from its adopted record: {path}')


def prime_renderer_name(row, plan):
    name = Path(plan.get('renderer_implementation',
                         row.get('render_implementation', 'render_prime_video'))).stem
    if name not in ('render_prime_video', 'render_prime_video_v002', 'render_prime_video_v003'):
        raise ValueError('Unknown adopted prime-number renderer')
    return name


def fibonacci_renderer_name(row, plan):
    name = Path(plan.get('renderer_implementation',
                         row.get('render_implementation', 'render_fibonacci_video'))).stem
    if name not in ('render_fibonacci_video', 'render_fibonacci_video_v002', 'render_fibonacci_video_v003'):
        raise ValueError('Unknown adopted Fibonacci-number renderer')
    return name


def fibonacci_motion_source(plan):
    """Bind new actor actions to the immutable measured audio timeline."""
    source = plan['source_timeline']
    base_path = project_path(source['path'])
    require_file(base_path, source['sha256'])
    base = read(base_path)
    for field in ('events', 'voice_events', 'counted_states', 'visual_segments', 'scenes',
                  'duration_s', 'duration_frames', 'master_audio', 'timing'):
        if plan[field] != base[field]:
            raise ValueError(f'Fibonacci motion revision changes measured audio/content: {field}')
    receipt = plan['character_motion']
    motion = project_path(receipt['path'])
    require_file(motion, receipt['sha256'])
    if read(motion).get('source_timeline') != source:
        raise ValueError('Fibonacci motion is bound to a different measured base')
    return motion


def fibonacci_aac_source(plan, audio):
    require_file(audio, plan['master_audio']['sha256'])
    receipt = plan['encoded_audio_acceptance']
    gate_path = project_path(receipt['path'])
    require_file(gate_path, receipt['sha256'])
    gate = read(gate_path)
    if gate.get('passed') is not True:
        raise ValueError('Fibonacci encoded audio has no passed acceptance record')
    if gate['master']['sha256'] != sha256(audio) or gate['source_timeline'] != plan['source_timeline']:
        raise ValueError('Fibonacci encoded audio is bound to a different master or measured base')
    source = gate['encoded_aac']
    encoded = project_path(source['path'])
    require_file(encoded, source['sha256'])
    return encoded


def prime_aac_source(plan, audio):
    """The visual revision can only reuse its hash-bound, accepted soundtrack."""
    master = plan['master_audio']
    require_file(audio, master['sha256'])
    source_receipt = plan['source_timeline']
    source_timeline = project_path(source_receipt['path'])
    require_file(source_timeline, source_receipt['sha256'])
    original = read(source_timeline)
    for field in ('events', 'voice_events', 'duration_s', 'master_audio', 'timing'):
        if plan[field] != original[field]:
            raise ValueError(f'Copied AAC requires unchanged accepted speech: {field}')
    receipt = plan['reused_final_aac']
    source = project_path(receipt['path'])
    require_file(source, receipt['sha256'])
    return source


def make_scene(kind, row, plan, motion):
    if kind == 'decimal':
        renderer = module('render_counting_video')
        episode = read(ROOT / 'episodes/counting-garden-001.json')
        cues = read(project_path(episode['cue_sheet']))
        theme = read(project_path(row['theme']))
        timeline = renderer.Timeline(plan, cues)
        scene = renderer.Scene(timeline, renderer.Artwork(read(project_path(row['render_asset_manifest'])),
                               theme.get('sprite_overrides')), project_path(theme['background']), theme)
        scene.duration = timeline.duration
    elif kind == 'binary':
        renderer = module('render_binary_video_v003')
        scene = renderer.BinaryScene(renderer.BinaryTimeline(plan))
    elif kind == 'octal':
        renderer = module('render_octal_video')
        scene = renderer.Scene(plan, 'common-baseline')
    elif kind == 'hexadecimal':
        renderer = module('render_hexadecimal_video')
        scene = renderer.Scene(plan)
    elif kind == 'fibonacci':
        renderer = module(fibonacci_renderer_name(row, plan))
        scene = renderer.Scene(plan)
    elif kind == 'prime':
        renderer = module(prime_renderer_name(row, plan))
        scene = renderer.Scene(plan)
    elif kind in ('even', 'odd'):
        default = f'render_{kind}_video'
        name = Path(plan.get('renderer_implementation', row.get('render_implementation', default))).stem
        allowed = ('render_even_video', 'render_even_video_v002') if kind == 'even' else ('render_odd_video', 'render_odd_video_v002')
        if name not in allowed:
            raise ValueError(f'Unknown adopted {kind}-number renderer')
        renderer = module(name)
        scene = renderer.Scene(plan)
    else:
        renderer = module('render_four_base_video_v002')
        scene = renderer.Scene(plan, motion)
    return renderer, scene


def scene_image(kind, scene, at):
    if not math.isfinite(at) or not 0 <= at < scene.duration:
        raise ValueError(f'Preview time must be in 0 <= t < {scene.duration}: {at}')
    if kind in ('decimal', 'binary'):
        return scene.frame(at)
    result = scene.image(scene.state(min(scene.frame_count - 1, math.ceil(at * 30 - 1e-7))))
    return result[0] if kind in ('prime', 'fibonacci') else result


def check_inputs(kind, row, timeline_path, audio, motion, custom=False):
    record = read(project_path(row['production_record']))
    inventory = record.get('files', [])
    expected = record_hashes(inventory)
    archive_path = ROOT / 'reproducibility/production-inputs.json'
    if not custom:
        require_file(archive_path)
        for entry in read(archive_path)['files']:
            previous = expected.get(entry['path'])
            if previous is not None and previous != entry['sha256']:
                raise ValueError(f'Conflicting adopted input hashes: {entry["path"]}')
            expected[entry['path']] = entry['sha256']
    for path in [timeline_path, audio] + ([motion] if motion else []):
        relative = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else None
        if not custom and relative not in expected:
            raise ValueError(f'Adopted input is not covered by its checksum archive: {path}')
        require_file(path, None if custom else expected.get(relative))
    plan = read(timeline_path)
    events = plan['voice_events'] if kind in ('even', 'odd') else plan['events']
    speech = [e for e in events if e.get('source_path') and e.get('source_sha256')]
    seen = set()
    for event in speech:
        key = (event['source_path'], event['source_sha256'])
        if key not in seen:
            require_file(project_path(key[0]), key[1])
            seen.add(key)
    fibonacci_acting_revision = kind == 'fibonacci' and fibonacci_renderer_name(row, plan) != 'render_fibonacci_video'
    if fibonacci_acting_revision:
        declared = fibonacci_motion_source(plan)
        fibonacci_aac_source(plan, audio)
        if motion is not None and motion.resolve() != declared.resolve():
            raise ValueError('Fibonacci motion override differs from the accepted schedule')
    if motion and not fibonacci_acting_revision:
        motions = read(motion)
        if motions.get('timeline_sha256') != sha256(timeline_path):
            raise ValueError('The motion manifest is bound to a different timeline')
        for pose in motions.get('poses', {}).values():
            require_file(project_path(pose['path']), pose['sha256'])
    with wave.open(str(audio), 'rb') as track:
        expected_frames = round(plan['duration_s'] * track.getframerate())
        if abs(track.getnframes() - expected_frames) > 1:
            raise ValueError('Master length does not match the measured timeline')
    if kind == 'prime' and prime_renderer_name(row, plan) != 'render_prime_video':
        prime_aac_source(plan, audio)
        schedule = plan['kangaroo_animation']['schedule']
        require_file(project_path(schedule['path']), schedule['sha256'])
    renderer, scene = make_scene(kind, row, plan, motion)
    return plan, renderer, scene, len(seen)


def record_hashes(inventory):
    """Historical records use both [{path,sha256}] and {path:sha256}."""
    expected = {}
    entries = inventory.items() if isinstance(inventory, dict) else [(None, entry) for entry in inventory]
    for key, entry in entries:
        if isinstance(entry, dict) and 'path' in entry and 'sha256' in entry:
            expected[entry['path']] = entry['sha256']
        elif key is not None and isinstance(entry, str) and len(entry) == 64:
            expected[key] = entry
    return expected


def copy_delivery(source, destination):
    for name in ['english-captions.srt', 'chapters.txt', 'upload-details.txt']:
        require_file(source / name)
        with (destination / name).open('xb') as output:
            output.write((source / name).read_bytes())
    for name in ['subtitles.srt', 'youtube-title.txt', 'youtube-description.txt']:
        if (source / name).is_file():
            with (destination / name).open('xb') as output:
                output.write((source / name).read_bytes())


def render_or_preview(args):
    key, kind, row = production(args.production)
    timeline_path, audio, motion = inputs(row, args)
    plan, renderer, scene, checked = check_inputs(kind, row, timeline_path, audio, motion,
                                                bool(args.timeline or args.audio or args.motion_manifest))
    renderer_path = (f'tools/{prime_renderer_name(row, plan)}.py' if kind == 'prime'
                     else f'tools/{fibonacci_renderer_name(row, plan)}.py' if kind == 'fibonacci'
                     else row['render_implementation'])
    destination = new_directory(args.out_dir)
    if args.command == 'preview':
        positions = args.at or [2, min(30.5, scene.duration / 2), scene.duration - 12.5, scene.duration - 3]
        for ordinal, at in enumerate(positions, 1):
            scene_image(kind, scene, at).save(destination / f'{ordinal:02d}-{at:.3f}s.png')
        receipt = {'kind': 'portable-production-preview', 'production_id': key, 'source_voices_checked': checked,
                   'times_s': positions, 'timeline_sha256': sha256(timeline_path), 'master_sha256': sha256(audio),
                   'renderer': renderer_path, 'original_sources_modified': False,
                   'custom_timeline': bool(args.timeline)}
        save_new(destination / 'preview-receipt.json', receipt)
        return receipt
    ffmpeg = executable('ffmpeg', args.ffmpeg)
    video = destination / Path(row['output']).name
    if kind == 'prime':
        # The prime master already includes its measured delivery gain.
        copied_aac = prime_renderer_name(row, plan) != 'render_prime_video'
        encoded_audio = prime_aac_source(plan, audio) if copied_aac else audio
        with tempfile.TemporaryDirectory(prefix='youtube-prime-render-', dir=work_directory(args.work_dir)) as temporary:
            index, runs, images = renderer.stage(scene, Path(temporary) / 'frames')
            renderer.encode(index, encoded_audio, video, scene.frame_count, ffmpeg, args.preset, args.crf)
        result = {'audio_mux_gain_db': 0, 'frames': scene.frame_count,
                  'distinct_images': len(images), 'holds': len(runs)}
        if copied_aac:
            source_hash = renderer.aac_hash(encoded_audio, ffmpeg)
            output_hash = renderer.aac_hash(video, ffmpeg)
            if source_hash != output_hash:
                raise ValueError('Copied prime AAC stream differs from its accepted source')
            result.update(audio_codec_copy=True, encoded_audio_bitstream_identical=True,
                          copied_aac_source=str(encoded_audio), copied_aac_source_sha256=sha256(encoded_audio),
                          original_audio_adts_sha256=source_hash, output_audio_adts_sha256=output_hash)
    elif kind == 'fibonacci':
        copied_aac = fibonacci_renderer_name(row, plan) != 'render_fibonacci_video'
        encoded_audio = fibonacci_aac_source(plan, audio) if copied_aac else audio
        with tempfile.TemporaryDirectory(prefix='youtube-fibonacci-render-', dir=work_directory(args.work_dir)) as temporary:
            index, runs, images = renderer.stage(scene, Path(temporary) / 'frames')
            renderer.encode(index, encoded_audio, video, scene.frame_count, ffmpeg, args.preset, args.crf)
        result = {'audio_mux_gain_db': 0, 'frames': scene.frame_count,
                  'distinct_images': len(images), 'holds': len(runs)}
        if copied_aac:
            source_hash = renderer.aac_hash(encoded_audio, ffmpeg)
            output_hash = renderer.aac_hash(video, ffmpeg)
            if source_hash != output_hash:
                raise ValueError('Copied Fibonacci AAC stream differs from its accepted source')
            result.update(audio_codec_copy=True, encoded_audio_bitstream_identical=True,
                          copied_aac_source=str(encoded_audio), copied_aac_source_sha256=sha256(encoded_audio),
                          original_audio_adts_sha256=source_hash, output_audio_adts_sha256=output_hash)
    elif kind in ('decimal', 'binary'):
        shared = module('render_counting_video')
        result = shared.encode(scene, [shared.Segment(0, scene.duration, 'portable adopted reproduction')],
                               video, ffmpeg, audio, args.crf, args.preset)
    else:
        shared = module('render_octal_video')
        gain = float(plan['delivery_gain_db']) if kind in ('even', 'odd') else {'octal': .8, 'hexadecimal': 0, 'four-base': .8}[kind]
        if not math.isfinite(gain):
            raise ValueError('Delivery gain must be finite')
        with tempfile.TemporaryDirectory(prefix='youtube-render-', dir=work_directory(args.work_dir)) as temporary:
            index, unique, holds = shared.stage_frames(scene, Path(temporary))
            print(f'Staged {unique} images in {holds} holds.', flush=True)
            result_path = Path(temporary) / 'render.mp4'
            shared.encode(index, audio, result_path, scene.frame_count, ffmpeg, args.crf, args.preset, gain)
            shutil.move(result_path, video)
        result = {'audio_mux_gain_db': gain, 'frames': scene.frame_count}
    if not args.timeline:
        copy_delivery(project_path(row['output']).parent, destination)
    with (destination / 'timeline.json').open('xb') as output:
        output.write(timeline_path.read_bytes())
    if motion:
        motion_name = 'character-motion.json' if kind == 'fibonacci' else 'bird-motions.json'
        with (destination / motion_name).open('xb') as output:
            output.write(motion.read_bytes())
    receipt = {**result, 'kind': 'portable-adopted-production-render', 'production_id': key,
               'output': str(video), 'video_sha256': sha256(video), 'timeline': str(timeline_path),
               'timeline_sha256': sha256(timeline_path), 'audio_sha256': sha256(audio),
               'renderer': renderer_path, 'renderer_sha256': sha256(project_path(renderer_path)),
               'portable_launcher_sha256': sha256(Path(__file__)), 'ffmpeg': ffmpeg,
               'original_sources_modified': False, 'custom_timeline': bool(args.timeline)}
    if kind == 'binary':
        receipt.update(base_binary_renderer_sha256=sha256(TOOLS / 'render_binary_video.py'),
                       base_decimal_renderer_sha256=sha256(TOOLS / 'render_binary_video_v002.py'),
                       shared_encoder_and_bear_sha256=sha256(TOOLS / 'render_counting_video.py'),
                       source_assets=renderer.previous.original.source_receipts())
    save_new(video.with_suffix('.render.json'), receipt)
    return receipt


def verify(args):
    key, kind, row = production(args.production)
    timeline_path, audio, motion = inputs(row, args)
    plan = read(timeline_path)
    video = Path(args.video).expanduser().resolve()
    require_file(video)
    ffmpeg, ffprobe = executable('ffmpeg', args.ffmpeg), executable('ffprobe', args.ffprobe)
    destination = new_directory(args.out_dir)
    if kind == 'prime':
        require_file(audio)
        evidence_dir = destination / 'prime-media'
        command = [sys.executable, '-B', str(TOOLS / 'verify_prime_video.py'),
                   '--timeline', str(timeline_path), '--video', str(video), '--master', str(audio),
                   '--out-dir', str(evidence_dir), '--ffmpeg', ffmpeg, '--ffprobe', ffprobe]
        if args.delivery_dir:
            command += ['--delivery-dir', str(args.delivery_dir)]
        subprocess.run(command, cwd=ROOT, check=True)
        evidence = read(evidence_dir / 'verification.json')
        if evidence.get('passed') is not True:
            raise ValueError('Prime final media checks did not pass')
        result = {'status': 'pass', 'production_id': key, 'video_sha256': sha256(video),
                  'timeline_sha256': sha256(timeline_path), 'master_sha256': sha256(audio),
                  'evidence': 'prime-media/verification.json',
                  'checks_performed': ['full decode, all 168 prime states and teaching diagrams, '
                                       '188 source voices versus both master/AAC channels, silence and captions'],
                  'not_performed': ['Fresh ASR/CTC inference and full human listening are separate checks.'],
                  'checked_at_utc': datetime.now(timezone.utc).isoformat()}
        save_new(destination / 'portable-verification.json', result)
        return result
    if kind == 'fibonacci':
        require_file(audio)
        evidence_dir = destination / 'fibonacci-media'
        revision = fibonacci_renderer_name(row, plan)
        verifier_name = 'verify_fibonacci_video_v003.py' if revision == 'render_fibonacci_video_v003' else 'verify_fibonacci_video.py'
        command = [sys.executable, '-B', str(TOOLS / verifier_name),
                   '--timeline', str(timeline_path), '--video', str(video), '--master', str(audio),
                   '--out-dir', str(evidence_dir), '--ffmpeg', ffmpeg, '--ffprobe', ffprobe]
        if args.delivery_dir:
            command += ['--delivery-dir', str(args.delivery_dir)]
        subprocess.run(command, cwd=ROOT, check=True)
        evidence = read(evidence_dir / 'verification.json')
        if evidence.get('passed') is not True:
            raise ValueError('Fibonacci final media checks did not pass')
        motion_evidence = None
        if revision != 'render_fibonacci_video':
            motion_dir = destination / 'fibonacci-motion'
            motion_name = 'verify_fibonacci_motion_v003.py' if revision == 'render_fibonacci_video_v003' else 'verify_fibonacci_motion_v002.py'
            command = [sys.executable, '-B', str(TOOLS / motion_name),
                       '--timeline', str(timeline_path), '--video', str(video),
                       '--out-dir', str(motion_dir), '--ffmpeg', ffmpeg, '--ffprobe', ffprobe]
            if motion:
                command += ['--motion-plan', str(motion)]
            subprocess.run(command, cwd=ROOT, check=True)
            motion_evidence = read(motion_dir / 'verification.json')
            if motion_evidence.get('passed') is not True:
                raise ValueError('Fibonacci character motion checks did not pass')
        result = {'status': 'pass', 'production_id': key, 'video_sha256': sha256(video),
                  'timeline_sha256': sha256(timeline_path), 'master_sha256': sha256(audio),
                  'evidence': 'fibonacci-media/verification.json',
                  'checks_performed': ['full decode;41terms,39additions, input handoffs and teaching diagrams; '
                                       '104source voices versus both master/AAC channels, silence and captions'],
                  'not_performed': ['Fresh ASR/CTC inference and full human listening are separate checks.'],
                  'checked_at_utc': datetime.now(timezone.utc).isoformat()}
        if motion_evidence is not None:
            result['motion_evidence'] = 'fibonacci-motion/verification.json'
            result['checks_performed'].append('measured audio-base binding, new character-art geometry and decoded motion windows')
        save_new(destination / 'portable-verification.json', result)
        return result
    if kind in ('even', 'odd'):
        require_file(audio)
        default = f'verify_{kind}_video'
        name = Path(plan.get('verifier_implementation', row.get('verifier_implementation', default))).stem
        allowed = ('verify_even_video', 'verify_even_video_v002') if kind == 'even' else ('verify_odd_video',)
        if name not in allowed:
            raise ValueError(f'Unknown adopted {kind}-number verifier')
        command = [sys.executable, '-B', str(TOOLS / f'{name}.py'),
                   '--timeline', str(timeline_path), '--video', str(video), '--master', str(audio),
                   '--output-dir', str(destination), '--delivery-dir', str(args.delivery_dir or video.parent),
                   '--ffmpeg', ffmpeg, '--ffprobe', ffprobe, '--work-dir', str(work_directory(args.work_dir))]
        subprocess.run(command, cwd=ROOT, check=True)
        evidence_name = f'{kind}-final-qa.json'
        evidence = read(destination / evidence_name)
        if evidence['status'] != 'pass':
            raise ValueError(f'{kind.capitalize()}-number final media checks did not pass')
        if kind == 'even':
            number_count, voice_count = 101, 115
        else:
            number_count = (plan['count_end'] - plan['count_start']) // plan['count_step'] + 1
            voice_count = len(plan['voice_events'])
        result = {'status': 'pass', 'production_id': key, 'video_sha256': sha256(video),
                  'timeline_sha256': sha256(timeline_path), 'master_sha256': sha256(audio),
                  'checks_performed': [
                      'full decode, media format, frame grid/duration, final AAC loudness and peak',
                      f'all {number_count} {kind} values, natural readings, progression, synchronization and teaching diagrams',
                      f'all {voice_count} voices versus adopted sources in master and final AAC stereo channels, silence and captions'],
                  'evidence': evidence_name,
                  'not_performed': ['Fresh ASR/CTC inference and full human listening are separate checks.'],
                  'checked_at_utc': datetime.now(timezone.utc).isoformat()}
        save_new(destination / 'portable-verification.json', result)
        return result
    bounds = (480, 1440) if kind == 'binary' else (480, 900)
    technical = module('verify_video').verify_video(video, destination, timeline_path, ffmpeg, ffprobe,
                                                   duration_bounds=bounds)
    checked = ['full decode, media format, frame grid/duration, final AAC loudness and peak']
    if kind in ('four-base', 'octal', 'hexadecimal'):
        names = {'four-base': 'verify_four_base_video_v002', 'octal': 'verify_octal_video',
                 'hexadecimal': 'verify_hexadecimal_video'}
        command = [sys.executable, '-B', str(TOOLS / f'{names[kind]}.py'), '--timeline', str(timeline_path),
                   '--video', str(video), '--output-dir', str(destination), '--delivery-dir', str(args.delivery_dir or video.parent),
                   '--technical-report', str(destination / 'technical-qa.json'), '--ffmpeg', ffmpeg, '--ffprobe', ffprobe]
        if kind == 'four-base':
            command += ['--motion-manifest', str(motion)]
        if kind == 'octal':
            command += ['--reading-layout', 'common-baseline']
        subprocess.run(command, cwd=ROOT, check=True)
        checked.append('complete base-specific sampled values, labels, synchronization and captions')
        audio_names = {'four-base': 'verify_four_base_audio_v002', 'octal': 'verify_octal_audio',
                       'hexadecimal': 'verify_hexadecimal_audio'}
        verifier = module(audio_names[kind])
        events, schedule = verifier.validate_schedule(plan)
        source = module('verify_octal_audio')
        with tempfile.TemporaryDirectory(prefix='youtube-audio-qa-', dir=work_directory(args.work_dir)) as temporary:
            folder = Path(temporary)
            refs = source.source_references(events, ffmpeg, folder)
            waveform = source.verify_track(video, events, refs, source.sample(plan['duration_s']), ffmpeg, folder, lossy=True)
        save_new(destination / 'portable-audio-qa.json', {'passed': True, 'schedule': schedule, 'encoded_audio': waveform})
        checked.append('all final AAC events versus adopted source waveforms and silent intervals')
    elif kind == 'binary':
        baseline = ROOT / 'output/binary-counting-001-v002'
        for path in [baseline / 'decoded-visual-qa/06-pause-1.png',
                     baseline / 'paspla-studio-binary-count-slower-decimal-sign-1080p.mp4']:
            require_file(path)
        module('verify_binary_visual_v003').verify(video, timeline_path, destination / 'binary-frames',
                                                  destination / 'binary-visual-qa.json', ffmpeg)
        checked.append('all 770 spoken-bit image midpoints, sign and alignment')
    else:
        subprocess.run([sys.executable, '-B', str(TOOLS / 'verify_layout.py'), '--video', str(video),
                        '--timeline', str(timeline_path), '--theme', str(project_path(row['theme'])),
                        '--out-dir', str(destination / 'decimal-layout'), '--ffmpeg', ffmpeg], cwd=ROOT, check=True)
        checked.append('decoded decimal label/number centering at seven representative components')
    if kind in ('decimal', 'binary'):
        scratch = work_directory(args.work_dir)
        environment = dict(os.environ)
        # These are child-only settings; the registered OS PATH is unchanged.
        media_directories = [str(Path(ffmpeg).parent), str(Path(ffprobe).parent)]
        environment['PATH'] = os.pathsep.join(dict.fromkeys(media_directories + environment.get('PATH', '').split(os.pathsep)))
        for name in ('TMP', 'TEMP', 'TMPDIR'):
            environment[name] = str(scratch)
        command = [sys.executable, '-B', str(TOOLS / 'portable_audio.py'), '--production', kind,
                   '--timeline', str(timeline_path), '--video', str(video), '--out', str(destination / 'portable-audio-qa.json'),
                   '--work-dir', str(scratch), '--ffmpeg', ffmpeg]
        if kind == 'binary':
            command += ['--captions', str((args.delivery_dir or video.parent) / 'english-captions.srt')]
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
        checked.append('all final AAC speech/source waveforms and silent intervals' if kind == 'decimal' else
                       'all final AAC speech waveforms, 642 internal digit gaps, 127 number boundaries and captions')
    if technical['status'] != 'pass':
        raise ValueError('Technical media checks did not pass')
    result = {'status': 'pass', 'production_id': key, 'video_sha256': sha256(video),
              'timeline_sha256': sha256(timeline_path), 'checks_performed': checked,
              'not_performed': ['Fresh ASR/CTC inference and full human listening are separate checks.'],
              'checked_at_utc': datetime.now(timezone.utc).isoformat()}
    save_new(destination / 'portable-verification.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    subparsers.add_parser('list')
    build = subparsers.add_parser('build-four-base', help='Build a fresh timeline/master/design using adopted speech and relocated proof paths')
    build.add_argument('--out-dir', required=True, type=Path)
    build.add_argument('--design-dir', required=True, type=Path)
    build.add_argument('--work-dir')
    for command in ['doctor', 'preview', 'render', 'verify']:
        sub = subparsers.add_parser(command)
        sub.add_argument('--production', default='all' if command == 'doctor' else 'four-base')
        sub.add_argument('--timeline')
        sub.add_argument('--audio')
        sub.add_argument('--motion-manifest')
        sub.add_argument('--ffmpeg')
        sub.add_argument('--ffprobe')
        sub.add_argument('--work-dir')
        if command != 'doctor':
            sub.add_argument('--out-dir', required=True)
        if command == 'preview':
            sub.add_argument('--at', type=float, nargs='+')
        if command == 'render':
            sub.add_argument('--crf', type=int, default=18)
            sub.add_argument('--preset', default='veryfast')
        if command == 'verify':
            sub.add_argument('--video', required=True)
            sub.add_argument('--delivery-dir', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'build-four-base':
        destination, design = args.out_dir.resolve(), args.design_dir.resolve()
        if not destination.is_relative_to(ROOT) or not design.is_relative_to(ROOT):
            raise ValueError('New production/design folders must be inside this checkout for relative source records')
        if destination.exists() or design.exists():
            raise FileExistsError('Choose new production and design directories')
        builder = module('build_four_base_episode_v002')
        resolver = module('portable_speech_library').resolve_reference
        original_resolver = builder.source_path
        try:
            # Narrow compatibility injection into this recipe's declared path resolver.
            # No original file or standard-library filesystem function is changed.
            builder.source_path = resolver
            receipt = builder.build(destination, design, work_directory(args.work_dir))
            result = {'status': 'pass', 'output': str(destination), 'design': str(design),
                      'duration_s': receipt['duration_s'], 'master_sha256': receipt['master_sha256'],
                      'required_delivery_gain_db': receipt['required_delivery_gain_db']}
        finally:
            builder.source_path = original_resolver
    elif args.command == 'list':
        result = [{'alias': alias, 'production_id': key, 'duration_s': production(alias)[2]['duration_s']}
                  for alias, key in adopted_aliases().items()]
    elif args.command == 'doctor':
        executable('ffmpeg', args.ffmpeg)
        executable('ffprobe', args.ffprobe)
        archive_path = ROOT / 'reproducibility/production-inputs.json'
        archived_files = 0
        if archive_path.is_file():
            archive = read(archive_path)
            for entry in archive['files']:
                require_file(project_path(entry['path']), entry['sha256'])
                if project_path(entry['path']).stat().st_size != entry['bytes']:
                    raise ValueError(f'Archived input length changed: {entry["path"]}')
                archived_files += 1
        rows = []
        for choice in list(adopted_aliases()) if args.production == 'all' else [args.production]:
            key, kind, row = production(choice)
            timeline, audio, motion = inputs(row, args)
            _, _, scene, sources = check_inputs(kind, row, timeline, audio, motion,
                                                bool(args.timeline or args.audio or args.motion_manifest))
            rows.append({'production_id': key, 'duration_s': scene.duration, 'source_clips_verified': sources})
        result = {'status': 'pass', 'project_root': str(ROOT), 'work_dir': str(work_directory(args.work_dir)),
                  'adopted_productions': rows, 'models_required_for_reproduction': False,
                  'archived_input_files_verified': archived_files,
                  'scope': 'Render-time inputs, master duration, registered artwork and source hashes; historical machine paths in QA provenance are not execution prerequisites.'}
    elif args.command == 'verify':
        result = verify(args)
    else:
        result = render_or_preview(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Portable production failed: {error}', file=sys.stderr)
        raise SystemExit(1) from error
