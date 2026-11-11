#!/usr/bin/env python3
"""Losslessly register explicitly reviewed prime-lesson kangaroo sprite cells.

This tool extracts complete RGBA cells without changing source pixels. Physical
scale is calibrated once per source sheet, never from a crouched pose's height.
The input configuration contains the human-reviewed anatomical support anchors,
head measurement bands, and optional skin-backed facial replacement rectangles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def bounds(image, threshold):
    return image.getchannel('A').point(lambda a: 255 if a >= threshold else 0).getbbox()


def widest_head_row(image, roi):
    alpha = image.getchannel('A')
    rows = []
    for y in range(roi[1], roi[3]):
        xs = [x for x in range(roi[0], roi[2]) if alpha.getpixel((x, y)) >= 128]
        if xs:
            rows.append((max(xs) - min(xs) + 1, y, min(xs), max(xs) + 1))
    if not rows:
        raise ValueError('Head calibration band is empty')
    width, y, left, right = max(rows)
    return {'method': 'maximum alpha>=128 span inside ear-free face band',
            'roi_px': roi, 'width_px': width, 'row_y_px': y,
            'row_extent_px': [left, right]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--qa-dir', required=True)
    args = parser.parse_args()
    config_path, output, qa = map(resolve, (args.config, args.output, args.qa_dir))
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite registration: {output}')
    config = json.loads(config_path.read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    qa.mkdir(parents=True, exist_ok=True)
    frame_dir = output.parent / 'frames'
    frame_dir.mkdir(exist_ok=True)
    groups, sheets, cells = {}, {}, {}
    for name, row in config['source_groups'].items():
        sheet_path = resolve(row['sheet'])
        image = Image.open(sheet_path)
        if image.mode != 'RGBA':
            raise ValueError(f'Sheet must retain genuine RGBA: {sheet_path}')
        image.load()
        sheets[name] = image
        cols, rows = row['columns'], row['rows']
        x = [round(i * image.width / cols) for i in range(cols + 1)]
        y = [round(i * image.height / rows) for i in range(rows + 1)]
        for index in range(cols * rows):
            c, r = index % cols, index // cols
            box = (x[c], y[r], x[c + 1], y[r + 1])
            cells[name, index] = (image.crop(box), box)
        reference = float(row['reference_height_px'])
        if not math.isfinite(reference) or reference <= 0:
            raise ValueError(f'Invalid source-group reference height: {name}')
        group = {**row, 'sheet': relative(sheet_path), 'sheet_sha256': sha(sheet_path),
                 'source_size_px': list(image.size), 'source_mode': image.mode,
                 'cell_boundary_x_px': x, 'cell_boundary_y_px': y,
                 'reference_height_px': reference,
                 'scale_at_430px': 430 / reference}
        if 'head_measurement' in row:
            measurement = row['head_measurement']
            cell = cells[name, measurement['cell_index']][0]
            group['measured_head'] = widest_head_row(cell, measurement['roi_px'])
        groups[name] = group
    frames = []
    for row in config['frames']:
        identity, group = row['id'], row['scale_group']
        if any(previous['id'] == identity for previous in frames):
            raise ValueError(f'Duplicate frame ID: {identity}')
        image, box = cells[group, row['cell_index']]
        visible = bounds(image, 8)
        if visible is None:
            raise ValueError(f'Empty cell: {identity}')
        if visible[0] <= 0 or visible[1] <= 0 or visible[2] >= image.width or visible[3] >= image.height:
            raise ValueError(f'Cell touches extraction boundary: {identity}: {visible}')
        anchor = row['anchor_px']
        if len(anchor) != 2 or not (0 < anchor[0] < image.width and 0 < anchor[1] < image.height):
            raise ValueError(f'Invalid anatomical support anchor: {identity}')
        frame_path = frame_dir / f'{identity}.png'
        if frame_path.exists():
            raise FileExistsError(f'Refusing to overwrite extracted frame: {frame_path}')
        image.save(frame_path)
        reopened = Image.open(frame_path)
        exact = reopened.mode == image.mode and reopened.size == image.size and reopened.tobytes() == image.tobytes()
        if not exact:
            raise ValueError(f'Extraction was not pixel-lossless: {identity}')
        body_roi = row['body_roi_px']
        body = bounds(image.crop(body_roi), 8)
        if body is None:
            raise ValueError(f'Empty body region: {identity}')
        body = [body[i] + body_roi[i % 2] for i in range(4)]
        frames.append({**row, 'path': relative(frame_path), 'sha256': sha(frame_path),
                       'source_sheet': groups[group]['sheet'],
                       'source_sheet_sha256': groups[group]['sheet_sha256'],
                       'source_cell_box_xyxy': list(box),
                       'reference_height_px': groups[group]['reference_height_px'],
                       'source_size_px': list(image.size), 'body_bbox_px': body,
                       'visible_bbox_px': list(visible),
                       'visible_bbox_alpha128_px': list(bounds(image, 128)),
                       'alpha_extrema': list(image.getchannel('A').getextrema()),
                       'rgba_pixels_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
                       'lossless_source_cell_match': exact,
                       'all_cell_edges_clear_at_alpha8': True})
    registration = {**config, 'kind': 'prime-kangaroo-animation-registration',
                    'config_path': relative(config_path), 'config_sha256': sha(config_path),
                    'source_groups': groups, 'frames': frames,
                    'source_pixels_modified': False, 'per_pose_fit': False,
                    'extraction': 'Full original RGBA cells; no trimming, recoloring, alpha cleanup or resampling.',
                    'registration_tool': relative(Path(__file__)),
                    'registration_tool_sha256': sha(Path(__file__))}
    output.write_text(json.dumps(registration, ensure_ascii=False, indent=2) + '\n')
    # This is a review rendering only; registered original PNGs remain untouched.
    for group, meta in groups.items():
        rows = [row for row in frames if row['scale_group'] == group]
        cols = 3
        board = Image.new('RGB', (1500, 560 * math.ceil(len(rows) / cols)), '#eee6d8')
        draw = ImageDraw.Draw(board)
        for index, row in enumerate(rows):
            im = Image.open(resolve(row['path']))
            scale = meta['scale_at_430px']
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
            tile = Image.new('RGBA', (500, 560), '#eee6d8')
            target = (220, 500)
            position = (round(target[0] - row['anchor_px'][0] * scale),
                        round(target[1] - row['anchor_px'][1] * scale))
            tile.alpha_composite(im, position)
            d = ImageDraw.Draw(tile)
            d.line((0, 500, 499, 500), fill=(40, 100, 100, 100))
            d.text((12, 523), row['id'], fill='black')
            board.paste(tile.convert('RGB'), ((index % cols) * 500, (index // cols) * 560))
        board.save(qa / f'{group}-target-430px.png')
    receipt = {'registration': relative(output), 'registration_sha256': sha(output),
               'frame_count': len(frames), 'all_extractions_pixel_lossless': True,
               'all_cell_edges_clear_at_alpha8': True, 'source_groups': groups,
               'review_rendering_height_px': 430,
               'scope': 'Extraction and geometry receipt. Motion/facial acceptance requires rendered preview and final decoded video.'}
    (qa / 'asset-registration.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'registration': relative(output), 'frames': len(frames), 'sha256': sha(output)}))


if __name__ == '__main__':
    main()
