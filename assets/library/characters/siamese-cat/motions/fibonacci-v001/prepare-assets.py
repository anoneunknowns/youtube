"""Register exact generated cells and compose non-destructive pose previews.

Run from any directory with the project venv Python. Original generation and
adopted stock are never repainted, alpha-cleaned, or resized in place.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
ORIGINAL = Path('/Users/support/.codex/generated_images/01a1cae3-5e92-7b31-b0f7-5374c0f76c4a/exec-13f64b42-c3eb-43f7-ab00-1ea68562c76b.png')
EXPECTED_SOURCE_SHA256 = '062d770da283fd81688418a9c6f8a88cf12b1ee5d074cdfd38c5209b2b8d2b55'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
IDS = ('watch_left', 'present_half', 'present_full', 'delighted')
# Manually reviewed toe supports: the midpoint of the two planted paw footprint
# union, not the whole-sprite bbox center (which would include arm and tail).
ANCHORS = ((313.5, 588), (287.5, 588), (313.5, 588), (287.5, 588))
FOOT_ROIS = ((200, 531, 425, 601), (175, 531, 400, 601),
             (200, 531, 425, 601), (175, 531, 400, 601))
COMMON_HEIGHT = 560


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path):
    return Path(path).relative_to(ROOT).as_posix()


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def metrics(image):
    alpha = image.getchannel('A')
    bbox = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
    bbox128 = alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
    edges = [alpha.crop(box).getextrema()[1] for box in (
        (0, 0, image.width, 1), (image.width-1, 0, image.width, image.height),
        (0, image.height-1, image.width, image.height), (0, 0, 1, image.height))]
    assert bbox and bbox128 and max(edges) <= 1
    return {'size_px': list(image.size), 'visible_bbox_alpha8_px': list(bbox),
            'visible_bbox_alpha128_px': list(bbox128),
            'alpha_extrema': list(alpha.getextrema()), 'edge_alpha_max_trbl': edges,
            'rgba_pixel_sha256': hashlib.sha256(image.tobytes()).hexdigest()}


def pose(image, anchor, reference_height, height=400):
    scale = height / reference_height
    # Resampling only occurs in this disposable preview, never in saved stock.
    sprite = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    return sprite, [v * scale for v in anchor]


def place(canvas, image, anchor, reference_height, root, height=400):
    sprite, local = pose(image, anchor, reference_height, height)
    origin = tuple(round(r - a) for r, a in zip(root, local))
    bbox = sprite.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
    absolute = [bbox[0]+origin[0], bbox[1]+origin[1], bbox[2]+origin[0], bbox[3]+origin[1]]
    assert 0 < absolute[0] < absolute[2] < canvas.width
    assert 0 < absolute[1] < absolute[3] < canvas.height
    canvas.alpha_composite(sprite, origin)
    return absolute


def main():
    source = HERE / 'source-sheet.png'
    if not source.exists():
        shutil.copyfile(ORIGINAL, source)
    assert sha(source) == EXPECTED_SOURCE_SHA256, 'Preserved generator output does not match the registered original'
    if ORIGINAL.is_file():
        assert sha(source) == sha(ORIGINAL), 'Original generator output must be copied byte-for-byte'
    sheet = Image.open(source)
    assert sheet.mode == 'RGBA' and sheet.size == (1254, 1254)
    catalog = json.loads((ROOT / 'catalogs/character-library-v1.json').read_text())
    character = next(c for c in catalog['characters'] if c['id'] == 'siamese-cat')
    neutral = character['neutral']
    neutral_path = ROOT / neutral['path']
    assert sha(neutral_path) == neutral['sha256']
    neutral_image = Image.open(neutral_path).copy()
    now = datetime.now(timezone.utc).isoformat()
    frames, cell_images = [], {}
    for index, (ident, anchor, roi) in enumerate(zip(IDS, ANCHORS, FOOT_ROIS)):
        x, y = index % 2 * 627, index // 2 * 627
        crop = (x, y, x+627, y+627)
        image = sheet.crop(crop)
        path = HERE / f'{ident}.png'
        image.save(path)
        reopened = Image.open(path)
        assert reopened.mode == 'RGBA' and reopened.tobytes() == image.tobytes()
        info = metrics(image)
        frame = {'id': ident, 'index': index, 'path': rel(path), 'sha256': sha(path),
                 'crop_from_sheet_xyxy': list(crop), 'anchor_px': list(anchor),
                 'reference_height_px': COMMON_HEIGHT,
                 'body_bbox_px': info['visible_bbox_alpha8_px'],
                 'body_bbox_scope': 'Complete visible pose footprint; art scale comes from shared standing ear-to-toe calibration, not this bbox.',
                 'tail_bbox_px': None, 'foot_roi_px': list(roi),
                 'foot_support_method': 'Manual anatomical inspection of both planted feet; footprint x-midpoint and common toe support y=588. Tail and presenting arm excluded.',
                 'exact_cell_pixel_match': True, **info}
        assert image.getchannel('A').crop(roi).getbbox()
        frames.append(frame)
        cell_images[ident] = image
    references = [{'role': 'canonical-identity-reference', 'path': neutral['path'],
                   'sha256': sha(neutral_path)}]
    prompt_path = HERE / 'generation-prompt.txt'
    prompt = prompt_path.read_text().strip()
    input_record = {'schema_version': 1, 'tool': 'image_gen.imagegen',
                    'created_at_utc': now, 'prompt_file': rel(prompt_path),
                    'prompt_file_sha256': sha(prompt_path),
                    'submitted_prompt': prompt,
                    'submitted_arguments': {'prompt': prompt, 'transparent_background': True,
                                            'referenced_image_paths': [str(neutral_path)]},
                    'input_references': references,
                    'historical_tool_output_path': str(ORIGINAL),
                    'saved_original': rel(source), 'saved_original_sha256': sha(source),
                    'output_size_px': list(sheet.size),
                    'requested_size_note': 'Prompt requested 1024x1024/512px cells; actual tool returned1254x1254. Exact627px cells are used and recorded.'}
    write('generation-input.json', input_record)
    registration = {'schema_version': 1, 'kind': 'episode-specific-generated-character-key-poses',
                    'character_id': 'siamese-cat', 'version': 'fibonacci-v001',
                    'status': 'episode-specific-key-poses-reviewed', 'production_asset': False,
                    'created_at_utc': now, 'source_pixels_modified': False,
                    'source_sheet': rel(source), 'source_sheet_sha256': sha(source),
                    'source_sheet_details': metrics(sheet),
                    'neutral_reference': references[0],
                    'grid': {'columns': 2, 'rows': 2, 'cell_size_px': [627, 627]},
                    'common_reference_height_px': COMMON_HEIGHT,
                    'body_calibration': {'method': 'Common standing ear-tip-to-anatomical-toe span from watch_left and both presenting poses. Alpha128 ear top28 and toe support588 =>560px.',
                                         'ear_top_px': 28, 'toe_support_px': 588,
                                         'per_pose_rescaling_allowed': False,
                                         'delighted_note': 'Ear-top31; a3px/0.54percent shorter drawn pose is retained at common scale. At400px target this is about2.14px.'},
                    'scale_policy': 'One isotropic scale target_body_height /560 for all four generated poses; no per-pose bbox fitting. Neutral keeps its separate adopted1070px registration.',
                    'support_policy': 'Use each manually reviewed anatomical foot anchor; half/delighted shift26px within their generated cells and must not use cell-center anchoring.',
                    'frames': frames,
                    'preview': {'target_body_height_px': 400,
                                'one_common_scale': 400 / COMMON_HEIGHT,
                                'preview_files': ['pose-review.png', 'pose-review-dark.png', 'presentation-keyposes.gif'],
                                'playback_note': 'Discrete key-pose review only. No interpolated animation, final episode timing or voice synchronization is claimed.'},
                    'generation_input': rel(HERE / 'generation-input.json'),
                    'generation_prompt': rel(prompt_path),
                    'pixel_processing': 'Byte-identical source copy and lossless exact cell extraction only. No alpha cleaning, repainting, color/contour processing, mirroring or creative resizing.',
                    'scope': 'Additional poses for Fibonacci preproduction only; adopted neutral, six existing stock poses and all global active/catalog entries remain unchanged.'}
    write('registration.json', registration)
    old_cheer = character['key_poses']['poses']['cheer']
    old_cheer_image = Image.open(ROOT / old_cheer['path']).copy()
    assert sha(ROOT / old_cheer['path']) == old_cheer['sha256']
    for existing in character['key_poses']['poses'].values():
        assert sha(ROOT / existing['path']) == existing['sha256'], 'Existing adopted key poses must remain unchanged'
    display = [('adopted neutral', neutral_image, neutral['anchor_px'], neutral['reference_height_px']),
               *[(ident, cell_images[ident], frames[i]['anchor_px'], COMMON_HEIGHT) for i, ident in enumerate(IDS)],
               ('existing cheer', old_cheer_image, old_cheer['anchor_px'], old_cheer['reference_height_px'])]
    font = ImageFont.truetype(str(FONT), 26)
    small = ImageFont.truetype(str(FONT), 20)
    preview_records = []
    for name, background, ink, guide in (
        ('pose-review.png', '#fff8e9', '#754318', '#e2d5bc'),
        ('pose-review-dark.png', '#173b40', '#fff4df', '#527176')):
        canvas = Image.new('RGBA', (1800, 1200), background)
        d = ImageDraw.Draw(canvas)
        for index, (label, image, anchor, height) in enumerate(display):
            x, y = index % 3 * 600, index // 3 * 600
            d.text((x+22, y+18), label, font=font, fill=ink)
            d.text((x+22, y+55), 'body400px / planted-foot anchor', font=small, fill=ink)
            d.line((x+95, y+551, x+490, y+551), fill=guide, width=1)
            bounds = place(canvas, image, anchor, height, (x+285, y+550))
            preview_records.append({'preview': name, 'pose': label, 'visible_bbox_alpha8_px': bounds,
                                    'support_root_px': [x+285, y+550],
                                    'horizontal_intent': 'anatomical-support alignment; not bbox centering',
                                    'vertical_intent': 'foot support on common ground line'})
        canvas.save(HERE / name)
    sequence = [('neutral', 600), ('watch_left', 450), ('present_half', 250),
                ('present_full', 650), ('present_half', 250), ('watch_left', 450),
                ('neutral', 450), ('delighted', 650), ('neutral', 600)]
    gifs, durations = [], []
    for ident, duration in sequence:
        canvas = Image.new('RGBA', (900, 720), '#fff8e9')
        d = ImageDraw.Draw(canvas)
        d.text((24, 20), ident + ' | discrete key pose', font=font, fill='#754318')
        d.text((24, 60), '400px common body scale; no interpolation', font=small, fill='#754318')
        d.line((310, 631, 720, 631), fill='#e2d5bc', width=1)
        if ident == 'neutral':
            image, anchor, height = neutral_image, neutral['anchor_px'], neutral['reference_height_px']
        else:
            frame = frames[IDS.index(ident)]
            image, anchor, height = cell_images[ident], frame['anchor_px'], COMMON_HEIGHT
        place(canvas, image, anchor, height, (520, 630))
        gifs.append(canvas.convert('RGB'))
        durations.append(duration)
    gifs[0].save(HERE / 'presentation-keyposes.gif', save_all=True, append_images=gifs[1:],
                 duration=durations, loop=0, disposal=2)
    scene_records = []
    for frame in frames:
        scene = Image.new('RGBA', (1920, 1080), '#fff8e9')
        bounds = place(scene, cell_images[frame['id']], frame['anchor_px'], COMMON_HEIGHT, (1655, 990))
        scene_records.append({'pose': frame['id'], 'resolution_px': [1920, 1080],
                              'body_height_px': 400, 'anatomical_foot_root_px': [1655, 990],
                              'visible_bbox_alpha8_px': bounds, 'contained': True,
                              'alignment_intent': 'anatomical foot support; not foreground-bbox centering'})
        if frame['id'] == 'present_full':
            scene.save(HERE / 'scene-scale-check.png')
    write('preview-metrics.json', {'resolution_px': [1800, 1200], 'target_body_height_px': 400,
                                  'layout_intent': 'Both feet aligned to common support, labels intentionally left aligned.',
                                  'records': preview_records,
                                  'intended_episode_scale': scene_records,
                                  'keypose_sequence': [{'id': ident, 'duration_ms': duration} for ident, duration in sequence]})
    record = {'schema_version': 1, 'kind': 'fibonacci-siamese-cat-generation-and-registration-record',
              'created_at_utc': now, 'generator': 'built-in image_gen.imagegen',
              'canonical_identity_reference': references[0],
              'generation_input': rel(HERE / 'generation-input.json'),
              'generation_input_sha256': sha(HERE / 'generation-input.json'),
              'prompt_file': rel(prompt_path), 'prompt_sha256': sha(prompt_path),
              'source_sheet': rel(source), 'source_sha256': sha(source),
              'registration': rel(HERE / 'registration.json'),
              'registration_sha256': sha(HERE / 'registration.json'),
              'exact_cell_extraction': True, 'original_pixels_modified': False,
              'source_copy_byte_identical': True,
              'scope': 'Fibonacci episode-specific supplementary stock; global catalog and active production sets untouched.',
              'reference_comparison': {'existing_six_pose_review': character['key_poses']['preview'],
                                       'bear_reactions': 'assets/library/characters/bear-beret/sources/v001/reactions-v2.png',
                                       'finding': 'Existing cat six poses cover greeting/thinking/aha/cheer; compared with bear twelve-reaction atlas they lack equation-directed gaze/presentation and an open-to-closed-eye pleased expression. Four new poses fill these specific uses.'},
              'checks': {'exact_cell_rgba_match': True, 'source_RGBA': sheet.mode == 'RGBA',
                         'cell_edge_alpha_max_at_most1': all(max(f['edge_alpha_max_trbl']) <= 1 for f in frames),
                         'body_scale_common': True, 'foot_anchors_individually_registered': True,
                         'canonical_sha_matches_adopted_catalog': True,
                         'all_six_existing_pose_sha_match_adopted_catalog': True,
                         'full_continuous_animation_verified': False,
                         'final_episode_audio_sync_verified': False},
              'artifacts': [{'path': rel(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
                            for path in sorted(HERE.iterdir()) if path.is_file() and path.name != 'generation-record.json']}
    write('generation-record.json', record)
    print(json.dumps({'source_size_px': list(sheet.size), 'common_reference_height_px': COMMON_HEIGHT,
                      'anchors': {f['id']: f['anchor_px'] for f in frames},
                      'exact_pixel_extraction': True, 'preview_paths': [str(HERE / p) for p in
                        ('pose-review.png', 'pose-review-dark.png', 'presentation-keyposes.gif')]}))


if __name__ == '__main__':
    main()
