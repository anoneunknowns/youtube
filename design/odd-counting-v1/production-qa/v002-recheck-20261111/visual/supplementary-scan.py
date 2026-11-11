"""Supplementary encoded-frame integrity scan; no production artifact mutation."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from PIL import Image, ImageChops, ImageDraw, ImageStat

ROOT = Path('D:/codex_projects/youtube')
OUT = ROOT / 'output/odd-counting-001-v002'
DEST = ROOT / 'design/odd-counting-v1/production-qa/v002-recheck-20261111/visual'
DEST.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'tools'))
from render_odd_video_v002 import Scene

VIDEO = OUT / 'paspla-studio-odd-numbers-1-to-299-1080p.mp4'
PLAN = OUT / 'timeline.json'
plan = json.loads(PLAN.read_text(encoding='utf-8'))
fps = 30
frames = plan['duration_frames']
ffmpeg = shutil.which('ffmpeg')

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def ref(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}

def read_frame(pipe, size):
    parts = bytearray()
    while len(parts) < size:
        chunk = pipe.read(size - len(parts))
        if not chunk:
            return None if not parts else (_ for _ in ()).throw(ValueError('Truncated raw frame'))
        parts.extend(chunk)
    return bytes(parts)

# Every decoded frame is examined here using a small full-frame luma image.
# Large main-number changes must occur at each of the 149 planned updates.
starts = {math.ceil(row['start_s'] * fps - 1e-7): row['decimal_value']
          for row in plan['counted_states'][1:]}
proc = subprocess.Popen([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(VIDEO),
    '-map', '0:v:0', '-vf', 'scale=160:90:flags=area', '-pix_fmt', 'gray',
    '-f', 'rawvideo', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
previous = None
count_changes = []
black = []
frozen_runs = []
run_start = 0
minimum_mean = 255
decoded = 0
while payload := read_frame(proc.stdout, 160 * 90):
    image = Image.frombytes('L', (160, 90), payload)
    mean = ImageStat.Stat(image).mean[0]
    minimum_mean = min(minimum_mean, mean)
    if mean < 25 or image.getextrema()[1] < 60:
        black.append(decoded)
    if previous is not None:
        change = ImageStat.Stat(ImageChops.difference(image, previous)).mean[0]
        if change > 0:
            if decoded - run_start >= 75:
                frozen_runs.append({'first': run_start, 'last': decoded - 1,
                    'duration_s': (decoded - run_start) / fps,
                    'required_count_updates_inside': sorted(set(starts).intersection(range(run_start + 1, decoded)))})
            run_start = decoded
        if decoded in starts:
            main = ImageStat.Stat(ImageChops.difference(image.crop((10, 23, 92, 50)),
                                                       previous.crop((10, 23, 92, 50)))).mean[0]
            count_changes.append({'frame': decoded, 'value': starts[decoded], 'main_luma_mean_absolute_change': main})
    previous = image
    decoded += 1
if decoded - run_start >= 75:
    frozen_runs.append({'first': run_start, 'last': decoded - 1, 'duration_s': (decoded - run_start) / fps,
        'required_count_updates_inside': sorted(set(starts).intersection(range(run_start + 1, decoded)))})
stderr = proc.stderr.read().decode('utf-8', errors='replace')
if proc.wait() != 0:
    raise ValueError(stderr)
freeze_errors = [run for run in frozen_runs if run['required_count_updates_inside']]
change_errors = [row for row in count_changes if row['main_luma_mean_absolute_change'] < .05]

# This additional comparison explicitly uses the producer Scene as an encoding
# oracle. It complements, and does not replace, independent numeral/diagram QA.
windows = [('opening-fade', 0, .8), ('intro-five-in', 12.4, 12.9), ('intro-five-out', 24.4, 24.9)]
for row in plan['teaching']:
    at = row['start_s']
    windows += [(row['id'] + '-in', at, at + .5), (row['id'] + '-out', at + 7.4, at + 8)]
finale = plan['finale']['start_s']
windows += [('finale-stamp', finale + .75, finale + 1.25),
            ('closing-fade', plan['duration_s'] - 2, plan['duration_s'])]
selected = set()
labels = {}
for label, start, end in windows:
    for index in range(max(0, math.ceil(start * fps - 1e-7) - 1), min(frames, math.ceil(end * fps - 1e-7) + 2)):
        selected.add(index)
        labels.setdefault(index, []).append(label)
baseline_values = (1, 5, 9, 99, 101, 199, 201, 277, 299)
for value in baseline_values:
    row = next(row for row in plan['counted_states'] if row['decimal_value'] == value)
    index = math.ceil((row['voice_start_s'] + .2) * fps - 1e-7)
    selected.add(index)
    labels.setdefault(index, []).append('count-' + str(value))
selected = sorted(selected)
ranges = []
for index in selected:
    if ranges and ranges[-1][1] + 1 == index:
        ranges[-1][1] = index
    else:
        ranges.append([index, index])
expression = '+'.join(f'between(n,{first},{last})' if first != last else f'eq(n,{first})'
                      for first, last in ranges)
scene = Scene(plan)
proc = subprocess.Popen([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(VIDEO),
    '-map', '0:v:0', '-vf', f"select='{expression}'", '-fps_mode', 'passthrough',
    '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
regions = {'full': (0, 0, 1920, 1080), 'title': (60, 30, 1400, 202),
           'header': (120, 242, 1340, 292), 'teaching': (120, 687, 1340, 855),
           'main_reading': (120, 292, 1340, 668), 'character': (1450, 510, 1880, 980)}
thresholds = {'full': 2, 'title': 2, 'header': 2, 'teaching': 3, 'main_reading': 3, 'character': 4}
maximums = {key: 0 for key in regions}
measurements = []
errors = []
snapshots = []
wanted_snapshots = {round(12.65 * fps), round(24.65 * fps)}
wanted_snapshots.update(math.ceil((row['start_s'] + .25) * fps - 1e-7) for row in plan['teaching'])
wanted_snapshots.update(math.ceil((row['voice_start_s'] + .2) * fps - 1e-7)
                        for row in plan['counted_states'] if row['decimal_value'] in (199, 201, 277, 299))
wanted_snapshots.update((math.ceil((finale + .95) * fps - 1e-7), math.ceil((finale + 1.05) * fps - 1e-7), frames - 1))
selected_extra = sorted(wanted_snapshots - set(selected))
if selected_extra:
    raise ValueError(f'Snapshot frames absent from selected scan: {selected_extra}')
for index in selected:
    payload = read_frame(proc.stdout, 1920 * 1080 * 3)
    if payload is None:
        details = proc.stderr.read().decode('utf-8', errors='replace')
        result = proc.wait()
        raise ValueError(f'Missing selected encoded frame {index}; ffmpeg exit {result}: {details}')
    actual = Image.frombytes('RGB', (1920, 1080), payload)
    expected = scene.image(scene.state(index)).convert('RGB')
    difference = ImageChops.difference(actual, expected)
    scores = {key: sum(ImageStat.Stat(difference.crop(box)).mean) / 3 for key, box in regions.items()}
    for key, score in scores.items():
        maximums[key] = max(maximums[key], score)
        if score > thresholds[key]:
            errors.append({'frame': index, 'region': key, 'mean_rgb_absolute_error': score, 'threshold': thresholds[key]})
    measurements.append({'frame': index, 'pts_s': index / fps, 'phases': labels[index], 'mean_rgb_absolute_error': scores})
    if index in wanted_snapshots:
        path = DEST / f'supplement-native-{index:06d}.png'
        actual.save(path)
        thumb = actual.copy()
        thumb.thumbnail((640, 360))
        snapshots.append((index, thumb))
if read_frame(proc.stdout, 1920 * 1080 * 3) is not None:
    raise ValueError('Unexpected extra selected frame')
stderr = proc.stderr.read().decode('utf-8', errors='replace')
if proc.wait() != 0:
    raise ValueError(stderr)
contact = Image.new('RGB', (1280, math.ceil(len(snapshots) / 2) * 390), '#fff8e8')
draw = ImageDraw.Draw(contact)
for ordinal, (index, image) in enumerate(snapshots):
    x, y = ordinal % 2 * 640, ordinal // 2 * 390
    contact.paste(image, (x, y))
    draw.text((x + 10, y + 362), f'frame {index} / {index / fps:.3f}s', fill='black')
contact.save(DEST / 'supplement-contact-sheet.png')
report = {'schema_version': 1, 'status': 'pass' if decoded == frames and not (black or freeze_errors or change_errors or errors) else 'fail',
    'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'video': ref(VIDEO), 'timeline': ref(PLAN),
    'all_frame_signal_screen': {'decoded_frames': decoded, 'black_frame_definition': 'mean luma below 25/255 or max below 60/255 at 160x90 area-scaled decode',
        'black_frames': black, 'minimum_global_luma_mean': minimum_mean,
        'static_runs_at_least_2_5_s': frozen_runs, 'frozen_runs_spanning_required_count_updates': freeze_errors,
        'count_updates_checked': len(count_changes), 'count_update_change_threshold': .05,
        'count_update_changes': count_changes, 'missing_or_unchanged_updates': change_errors,
        'interpretation': 'Static holds within one count/intro/teaching are intentional. This scan rejects a freeze crossing a planned count update.'},
    'producer_based_encode_integrity': {'scope': 'All frames of opening/closing fades, six teaching/intro fades, completion-stamp neighborhood, and nine numeric baseline values. Expected pixels use existing production Scene, so this is complementary to the separate independently constructed glyph/math oracle.',
        'frames_checked': len(selected), 'windows': [{'label': label, 'start_s': a, 'end_s': b} for label, a, b in windows],
        'thresholds_mean_rgb_absolute_error_0_255': thresholds, 'maximum_mean_rgb_absolute_errors': maximums,
        'regions': regions, 'records': measurements, 'errors': errors,
        'criterion': 'Mean absolute RGB error tolerates H264 YUV420 chroma/quantization changes; thresholds bound full and individual instruction/header areas rather than using byte equality.',
        'producer_oracle': ref(ROOT / 'tools/render_odd_video_v002.py')},
    'assistant_visual_review_pending': True, 'full_continuous_human_viewing_claimed': False}
with (DEST / 'supplementary-frame-scan.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'status': report['status'], 'decoded': decoded, 'selected': len(selected), 'errors': len(errors),
    'black': len(black), 'missing_updates': len(change_errors), 'maxima': maximums, 'snapshots': len(snapshots)}))
