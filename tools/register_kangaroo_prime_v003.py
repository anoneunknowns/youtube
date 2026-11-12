"""Bind reviewed prime v003 source cells and fixed-body arm registration.

Extraction is lossless RGBA. The renderer performs only the declared source
transforms and masks; generated originals and the previous registration remain
unchanged. Per-source-group reference heights are shared by every member.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'assets/library/characters/kangaroo/animations/prime-v002'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def bounds(image, threshold=8):
    return image.getchannel('A').point(lambda value: 255 if value >= threshold else 0).getbbox()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    config_path = DEST / 'registration-input.json'
    config = json.loads(config_path.read_text())
    output = DEST / 'registration.json'
    if output.exists():
        raise FileExistsError('Preserve an existing registered revision')
    old_path = ROOT / config['previous_registration']['path']
    assert digest(old_path) == config['previous_registration']['sha256']
    old = json.loads(old_path.read_text())
    rows = {row['id']: deepcopy(row) for row in old['frames']}
    groups = {name: deepcopy(old['source_groups'][name]) for name in ('expressions', 'postures')}
    frames_dir = DEST / 'frames'
    frames_dir.mkdir(exist_ok=True)
    for name, group in config['new_source_groups'].items():
        sheet_path = ROOT / group['sheet']
        assert digest(sheet_path) == group['sheet_sha256']
        with Image.open(sheet_path) as opened:
            assert opened.mode == 'RGBA'
            sheet = opened.copy()
        width, height = sheet.width // 3, sheet.height // 2
        assert sheet.width % 3 == 0 and sheet.height % 2 == 0
        groups[name] = {key: value for key, value in group.items() if key != 'frames'}
        groups[name].update(columns=3, rows=2, source_size_px=list(sheet.size), source_mode='RGBA',
                            scale_at_430px=430/group['reference_height_px'],
                            scale_at_470px=470/group['reference_height_px'])
        for index, pose in enumerate(group['frames']):
            box = [index % 3 * width, index // 3 * height,
                   (index % 3 + 1) * width, (index // 3 + 1) * height]
            image = sheet.crop(box)
            visible = bounds(image)
            assert visible and visible[0] > 0 and visible[1] > 0 and visible[2] < width and visible[3] < height
            path = frames_dir / (pose['id'] + '.png')
            if path.exists():
                raise FileExistsError(path)
            image.save(path)
            with Image.open(path) as check:
                assert check.mode == 'RGBA' and check.tobytes() == image.tobytes()
            rows[pose['id']] = {**pose, 'scale_group': name, 'cell_index': index,
                'path': local(path), 'sha256': digest(path), 'source_sheet': group['sheet'],
                'source_sheet_sha256': group['sheet_sha256'], 'source_cell_box_xyxy': box,
                'reference_height_px': group['reference_height_px'], 'source_size_px': list(image.size),
                'body_bbox_px': list(visible), 'visible_bbox_px': list(visible),
                'visible_bbox_alpha128_px': list(bounds(image, 128)),
                'alpha_extrema': list(image.getchannel('A').getextrema()),
                'rgba_pixels_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
                'lossless_source_cell_match': True, 'all_cell_edges_clear_at_alpha8': True}
    rest = config['rest_source']
    rest_path = ROOT / rest['registration']
    assert digest(rest_path) == rest['sha256']
    rest_registration = json.loads(rest_path.read_text())
    rest_sheet = next(sheet for sheet in rest_registration['sheets'] if sheet['id'] == 'postures')
    groups['expanded_rest'] = {'sheet': rest_sheet['source_sheet'], 'sheet_sha256': rest_sheet['source_sheet_sha256'],
        'columns': 3, 'rows': 3, 'reference_height_px': rest_sheet['reference_height_px'],
        'physical_calibration': rest_sheet['calibration'], 'scale_at_470px': 470/rest_sheet['reference_height_px']}
    for pose_id in rest['pose_ids']:
        row = deepcopy(next(row for row in rest_registration['frames'] if row['id'] == pose_id))
        assert digest(ROOT / row['path']) == row['sha256']
        row['scale_group'] = 'expanded_rest'
        row['source_cell_box_xyxy'] = row['crop_from_sheet_xyxy']
        row['source_size_px'] = row['size_px']
        rows[pose_id] = row
    for alias, source in config['source_pose_aliases'].items():
        rows[alias] = {**deepcopy(rows[source]), 'id': alias, 'source_pose_alias': source,
                       'alias_note': 'Explicit reuse of a reviewed hand drawing; no new pixels or pose scaling.'}
    registration = {**deepcopy(old), 'kind': 'prime-kangaroo-fixed-body-registration-v003',
        'config_path': local(config_path), 'config_sha256': digest(config_path),
        'body_height_at_render_px': 470, 'ground_foot_anchor_at_render_px': [1625, 1014],
        'previous_registration': config['previous_registration'], 'source_groups': groups,
        'frames': list(rows.values()), 'face_overlays': old['face_overlays'],
        'arm_overlays': config['arm_overlays'], 'source_pose_aliases': config['source_pose_aliases'],
        'arm_registration_policy': config['arm_registration_policy'], 'source_pixels_modified': False,
        'per_pose_fit': False, 'registration_tool': local(Path(__file__)),
        'registration_tool_sha256': digest(Path(__file__)),
        'acceptance_scope': 'Reviewed source cells and local arm registration. Final native scene and encoded-motion QA are separate.'}
    registration.pop('known_proportion_observation', None)
    registration.pop('candidate_exclusions', None)
    write(output, registration)
    print(json.dumps({'registration': local(output), 'sha256': digest(output), 'frames': len(rows),
                      'arm_rig_states': len(config['arm_overlays'])}))


if __name__ == '__main__':
    main()
