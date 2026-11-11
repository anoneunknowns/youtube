"""Measure visible text centering in decoded video frames; save compact QA crops."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw


def ink_measure(frame, box, target):
    x, y, w, h = box
    # Avoid the curved wooden/pill outlines while retaining the selected glyphs.
    inset_x, inset_y = (45, 45) if w > 600 else (40, 18)
    crop_box = (x + inset_x, y + inset_y, x + w - inset_x, y + h - inset_y)
    crop = frame.crop(crop_box)
    mask = Image.new('1', crop.size)
    rgb = crop.tobytes()
    mask.putdata([rgb[i] < 155 and rgb[i + 1] < 110 and rgb[i + 2] < 70 for i in range(0, len(rgb), 3)])
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError('Text ink not found')
    bounds = [bounds[0] + crop_box[0], bounds[1] + crop_box[1], bounds[2] + crop_box[0], bounds[3] + crop_box[1]]
    center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
    delta = [center[i] - target[i] for i in range(2)]
    return {'ink_bbox_xyxy': bounds, 'ink_center': center, 'target_center': target, 'delta_px': delta,
            'within_one_pixel': max(abs(v) for v in delta) <= 1}, frame.crop((x, y, x + w, y + h))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--timeline', required=True, type=Path)
    parser.add_argument('--theme', required=True, type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    timeline = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    theme = json.loads(args.theme.read_text(encoding='utf-8-sig'))
    fields = theme['board']
    header, inner = fields['header_bbox_xywh'], fields['inner_bbox_xywh']
    targets = {'header': [header[0] + header[2] / 2, header[1] + header[3] / 2],
               'number': [inner[0] + inner[2] / 2, inner[1] + inner[3] / 2]}
    displays = {row['number']: row for row in timeline['number_displays']}
    results, crops = [], []
    for number in [1, 6, 10, 100, 128, 300]:
        display = displays[number]
        when = display['start_s'] + min(.22, (display['end_s'] - display['start_s']) / 2)
        completed = subprocess.run([args.ffmpeg, '-v', 'error', '-ss', str(when), '-i', str(args.video),
                                    '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'],
                                   check=True, capture_output=True)
        frame = Image.open(io.BytesIO(completed.stdout)).convert('RGB')
        if number == 1:
            measure, crop = ink_measure(frame, header, targets['header'])
            results.append({'element': 'header', 'time_s': when, **measure})
            crops.append(('1 -> 300', crop))
        measure, crop = ink_measure(frame, inner, targets['number'])
        results.append({'element': f'number-{number}', 'time_s': when, **measure})
        crops.append((str(number), crop))
    sheet = Image.new('RGB', (960, 4 * 230), '#f5f0e5')
    draw = ImageDraw.Draw(sheet)
    for i, (label, crop) in enumerate(crops):
        crop.thumbnail((450, 195), Image.Resampling.LANCZOS)
        x, y = (i % 2) * 480, (i // 2) * 230
        sheet.paste(crop, (x + (480 - crop.width) // 2, y + 25))
        draw.text((x + 15, y + 7), label, fill='#4e260b')
    sheet.save(args.out_dir / 'layout-check.png')
    with args.video.open('rb') as source:
        video_hash = hashlib.file_digest(source, 'sha256').hexdigest()
    report = {'schema_version': 1, 'kind': 'decoded-video-text-centering-review',
              'video_path': str(args.video.resolve()), 'video_sha256': video_hash,
              'theme_path': str(args.theme), 'method': 'Bounding box of decoded dark-brown visible ink inside component fields. Pixel quantization tolerance: 1px.',
              'passed': all(x['within_one_pixel'] for x in results), 'results': results}
    (args.out_dir / 'layout-review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'components': len(results), 'maximum_delta_px': max(abs(d) for x in results for d in x['delta_px'])}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
