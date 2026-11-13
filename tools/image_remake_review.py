"""Local image comparisons and append-only choices; never changes asset adoption."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import socketserver
import stat
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit
import uuid

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
FORMATS = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP', '.gif': 'GIF'}
MAX_BODY = 32 * 1024
MAX_NOTE = 4000
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_PREVIEW_SIDE = 4096
ALPHA_THRESHOLD = 8
PREVIEW_PADDING = 24
SUPPORT_TOLERANCE = .5


class ReviewError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_path(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative
            or Path(relative).is_absolute() or PureWindowsPath(relative).drive
            or any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ReviewError('パスはプロジェクト内の正規相対パスで指定してください。')
    here = Path(root).resolve()
    for part in relative.split('/'):
        here /= part
        if here.is_symlink():
            raise ReviewError('シンボリックリンクは使用できません。')
    return here


def read_bytes(root, relative, maximum=MAX_IMAGE_BYTES):
    path = safe_path(root, relative)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                raise ReviewError('ファイル形式またはファイル容量を確認してください。')
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        check = safe_path(root, relative).stat()
    except OSError as exc:
        raise ReviewError('指定したファイルを読み込めません。') from exc
    signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if len(data) > maximum or signature(before) != signature(after) or signature(after) != signature(check):
        raise ReviewError('読み込み中にファイルが変わりました。', 409)
    return data


def read_json(root, relative):
    try:
        value = json.loads(read_bytes(root, relative, 2 * 1024 * 1024).decode('utf-8-sig'),
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, ReviewError):
            raise
        raise ReviewError('JSONの形式を確認してください。') from exc
    if not isinstance(value, dict):
        raise ReviewError('JSONオブジェクトが必要です。')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
        raise ReviewError('IDには英数字・ハイフン・下線を使用してください。')
    return value


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ReviewError(f'{name} は有限の数値で指定してください。')
    return value


def vector(value, length, name):
    if not isinstance(value, list) or len(value) != length:
        raise ReviewError(f'{name} の座標数を確認してください。')
    return [number(item, name) for item in value]


def text(value, name, maximum=1000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ReviewError(f'{name} の文字数・形式を確認してください。')
    return value


def visible_bbox(image):
    return image.getchannel('A').point([0] * ALPHA_THRESHOLD + [255] * (256 - ALPHA_THRESHOLD)).getbbox()


def decode_image(data, relative):
    suffix = Path(relative).suffix.lower()
    if suffix not in FORMATS:
        raise ReviewError('PNG・JPEG・WebP・GIFの画像を指定してください。')
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format != FORMATS[suffix] or source.width * source.height > MAX_PIXELS:
                raise ReviewError('画像形式または画像寸法を確認してください。')
            frames = getattr(source, 'n_frames', 1)
            mode = source.mode
            source.seek(0)
            result = source.convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ReviewError('画像を開けません。') from exc
    if not visible_bbox(result):
        raise ReviewError('可視部分のない画像は比較できません。')
    return result, mode, frames


def variant_record(root, value):
    if not isinstance(value, dict):
        raise ReviewError('候補の形式を確認してください。')
    name = identifier(value.get('id'))
    relative = value.get('path')
    data = read_bytes(root, relative)
    image, mode, frames = decode_image(data, relative)
    width, height = image.size
    bbox = list(visible_bbox(image))
    body = vector(value.get('body_bbox_px', bbox), 4, 'body_bbox_px')
    if not (0 <= body[0] < body[2] <= width and 0 <= body[1] < body[3] <= height):
        raise ReviewError('身体範囲が画像の外にあります。')
    anchor = vector(value.get('anchor_px', [(body[0] + body[2]) / 2, body[3]]), 2, 'anchor_px')
    if not (0 <= anchor[0] <= width and 0 <= anchor[1] <= height):
        raise ReviewError('支点が画像の外にあります。')
    reference = number(value.get('reference_height_px', body[3] - body[1]), 'reference_height_px')
    if reference <= 0:
        raise ReviewError('身体基準高は正の数値で指定してください。')
    details = value.get('details', [])
    if not isinstance(details, list) or len(details) > 30:
        raise ReviewError('詳細は文字列の配列で指定してください。')
    result = {'id': name, 'label': text(value.get('label', name), 'label'), 'path': relative,
              'sha256': digest(data), 'bytes': len(data), 'size_px': [width, height],
              'mode': mode, 'format': FORMATS[Path(relative).suffix.lower()], 'frame_count': frames,
              'preview_frame_index': 0, 'alpha_extrema': list(image.getchannel('A').getextrema()),
              'visible_alpha_threshold': ALPHA_THRESHOLD, 'visible_bbox_px': bbox,
              'body_bbox_px': body, 'anchor_px': anchor, 'reference_height_px': reference,
              'geometry_basis': {key: 'provided' if key in value else 'visible-silhouette-fallback'
                                 for key in ('body_bbox_px', 'anchor_px', 'reference_height_px')},
              'details': [text(item, 'details') for item in details]}
    if 'summary' in value:
        result['summary'] = text(value['summary'], 'summary', 4000)
    if value.get('sha256') is not None and value['sha256'] != result['sha256']:
        raise ReviewError('候補画像のSHA-256が一致しません。', 409)
    return result


def check_document(document):
    if type(document.get('schema_version')) is not int or document['schema_version'] != 1:
        raise ReviewError('対応していない比較データです。')
    identifier(document.get('id'))
    text(document.get('title'), 'title')
    if document.get('asset_id') is not None:
        identifier(document['asset_id'])
    variants = document.get('variants')
    if not isinstance(variants, list) or not 2 <= len(variants) <= 30:
        raise ReviewError('比較候補は2～30件で指定してください。')
    names = [identifier(item.get('id')) for item in variants if isinstance(item, dict)]
    if len(names) != len(variants) or len(set(names)) != len(names):
        raise ReviewError('候補IDが重複しているか形式が不正です。')
    if document.get('previous_variant_id') not in names or document.get('recommended_variant_id') not in names:
        raise ReviewError('前バージョンとAIおすすめを各1件指定してください。')
    reference = number(document.get('display_reference_height_px', 430), 'display_reference_height_px')
    if not 16 <= reference <= 1600:
        raise ReviewError('比較用身体高は16～1600pxで指定してください。')


def atomic_new(root, relative, data):
    path = safe_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(root, relative)
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix='.review-write-', dir=path.parent)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        safe_path(root, relative)
        os.link(temporary, path)  # Atomic publication; an existing event is never replaced.
    except FileExistsError as exc:
        raise ReviewError('出力先のファイルは既に存在します。', 409) from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return path


def prepare_review(root, spec_path, output_path):
    safe_path(root, output_path)
    if safe_path(root, output_path).exists():
        raise ReviewError('既存の比較データは上書きできません。', 409)
    source = read_bytes(root, spec_path, 2 * 1024 * 1024)
    spec = read_json(root, spec_path)
    check_document(spec)
    result = {key: spec[key] for key in ('schema_version', 'id', 'title', 'previous_variant_id', 'recommended_variant_id')}
    result.update(kind='image-remake-review', asset_id=spec.get('asset_id'), prepared_at_utc=utc_now(),
                  source_spec={'path': spec_path, 'sha256': digest(source)},
                  display_reference_height_px=spec.get('display_reference_height_px', 430), variants=[])
    for value in spec['variants']:
        item = variant_record(root, value)
        item['is_previous'] = item['id'] == result['previous_variant_id']
        item['is_recommended'] = item['id'] == result['recommended_variant_id']
        result['variants'].append(item)
    # Check geometry and every frozen input before publishing a new manifest.
    _geometry(root, result)
    if read_bytes(root, spec_path, 2 * 1024 * 1024) != source:
        raise ReviewError('準備中に比較仕様が変わりました。', 409)
    for item in result['variants']:
        _variant_bytes(root, item)
    data = payload(result)
    atomic_new(root, output_path, data)
    return {**result, 'review_sha256': digest(data)}


def load_review(root, review_path):
    data = read_bytes(root, review_path, 2 * 1024 * 1024)
    review = read_json(root, review_path)
    if read_bytes(root, review_path, 2 * 1024 * 1024) != data:
        raise ReviewError('比較データが変わりました。再読込してください。', 409)
    check_document(review)
    if review.get('kind') != 'image-remake-review':
        raise ReviewError('prepareで作成した比較データが必要です。')
    for item in review['variants']:
        _variant_bytes(root, item)
        actual = variant_record(root, item)
        for key in ('sha256', 'bytes', 'size_px', 'visible_bbox_px', 'alpha_extrema',
                    'body_bbox_px', 'anchor_px', 'reference_height_px'):
            if item.get(key) != actual[key]:
                raise ReviewError('画像または比較用座標が変わりました。作り直してください。', 409)
        if (item.get('is_previous') is not (item['id'] == review['previous_variant_id'])
                or item.get('is_recommended') is not (item['id'] == review['recommended_variant_id'])):
            raise ReviewError('比較データのラベルが一致しません。')
    return {**review, 'review_sha256': digest(data)}


def _variant_bytes(root, item):
    relative = item.get('path')
    safe_path(root, relative)
    expected = item.get('sha256')
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ReviewError('候補画像のSHA-256を確認してください。')
    try:
        data = read_bytes(root, relative)
    except ReviewError as exc:
        raise ReviewError('比較対象の画像を読み込めません。状態を確認してください。', 409) from exc
    if digest(data) != expected:
        raise ReviewError('画像が変更されています。比較データを作り直してください。', 409)
    return data


def _geometry(root, review):
    reference = review['display_reference_height_px']
    spans = []
    for item in review['variants']:
        scale = reference / item['reference_height_px']
        anchor = item['anchor_px']
        bbox = item['visible_bbox_px']
        spans.append([(bbox[i] - anchor[i % 2]) * scale for i in range(4)])
    left = math.floor(min(box[0] for box in spans))
    top = math.floor(min(box[1] for box in spans))
    right = math.ceil(max(box[2] for box in spans))
    bottom = math.ceil(max(box[3] for box in spans))
    size = [right - left + 2 * PREVIEW_PADDING, bottom - top + 2 * PREVIEW_PADDING]
    if min(size) <= 0 or max(size) > MAX_PREVIEW_SIDE or size[0] * size[1] > 8_000_000:
        raise ReviewError('共通比較枠が大きすぎます。身体基準高を確認してください。')
    raster_scale = 4 if size[0] * size[1] <= 2_000_000 else 2
    return {'canvas_size_px': size, 'anchor_px': [PREVIEW_PADDING - left, PREVIEW_PADDING - top],
            'raster_scale': raster_scale, 'raster_canvas_size_px': [v * raster_scale for v in size],
            'display_reference_height_px': reference, 'padding_px': PREVIEW_PADDING,
            'horizontal_intent': 'shared registered anchor x',
            'vertical_intent': 'shared registered support anchor y',
            'scale_policy': 'display reference height / each declared source reference height; no pose bbox fitting'}


def _preview(root, review, item, geometry):
    image, _, _ = decode_image(_variant_bytes(root, item), item['path'])
    density = geometry['raster_scale']
    scale = geometry['display_reference_height_px'] / item['reference_height_px'] * density
    anchor = [v * density for v in geometry['anchor_px']]
    correction = [0., 0.]
    measurements = []
    for attempt in range(3):
        inverse = (1 / scale, 0, item['anchor_px'][0] - (anchor[0] + correction[0] * density) / scale,
                   0, 1 / scale, item['anchor_px'][1] - (anchor[1] + correction[1] * density) / scale)
        rendered = image.transform(tuple(geometry['raster_canvas_size_px']), Image.Transform.AFFINE, inverse,
                                   resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
        check = _support_raster_check(root, item, rendered, geometry)
        measurements.append({'delta_px': check.get('delta_px'), 'passed': check['passed']})
        if check['passed'] or not check['available'] or attempt == 2:
            break
        proposed = [correction[i] - check['delta_px'][i] for i in (0, 1)]
        # This is bounded preview placement calibration, never source editing or
        # a new support/scale definition. Large registration errors remain failures.
        if any(abs(value) > 1.5 for value in proposed):
            break
        correction = proposed
    rendered.info['placement_calibration'] = {
        'method': 'bounded raster placement correction to the fixed projected source feature; source bytes, scale and declared anchors unchanged',
        'correction_px': correction, 'maximum_correction_px': 1.5,
        'measurements': measurements, 'target_region_changed': False,
    }
    return rendered


def _support_raster_check(root, item, rendered, geometry):
    """Compare an actual source silhouette feature with its rendered counterpart.

    For a registered ground anchor, this band contains the soles. Its horizontal
    midpoint need not equal the anatomical anchor: asymmetric feet are retained.
    A centre/pivot anchor measures its local silhouette instead, not a claimed foot.
    """
    source, _, _ = decode_image(_variant_bytes(root, item), item['path'])
    anchor = item['anchor_px']
    body = item['body_bbox_px']
    reference = item['reference_height_px']
    roi = [math.floor(body[0]), max(0, math.floor(anchor[1] - max(2, reference * .02))),
           math.ceil(body[2]), min(source.height, math.ceil(anchor[1] + max(2, reference * .005)))]
    result = {'method': 'alpha>=8 in source anchor-neighbourhood band; bbox midpoint x and bottom y; foot meaning requires a registered ground anchor',
              'source_roi_px': roi, 'tolerance_px': SUPPORT_TOLERANCE,
              'visible_alpha_threshold': ALPHA_THRESHOLD,
              'coordinates': 'logical comparison pixels; raster pixel edges divided by raster_scale'}
    bounds = visible_bbox(source.crop(tuple(roi))) if roi[1] < roi[3] else None
    if bounds is None:
        # An airborne pose can declare a virtual ground below its drawn feet.
        # Measure the lowest visible feature and preserve its offset from that
        # anchor; never move the declared ground onto the foot to make QA pass.
        lowest = item['visible_bbox_px'][3]
        roi = [math.floor(body[0]), max(0, math.floor(lowest - max(2, reference * .02))),
               math.ceil(body[2]), min(source.height, math.ceil(lowest + max(2, reference * .005)))]
        bounds = visible_bbox(source.crop(tuple(roi))) if roi[1] < roi[3] else None
        result.update(method='alpha>=8 at lowest drawn silhouette; bbox midpoint x and bottom y; offset from virtual ground is preserved',
                      source_roi_px=roi, anchor_band_empty=True)
        if bounds is None:
            return {**result, 'available': False, 'passed': False}
    source_bounds = [bounds[i] + roi[i % 2] for i in range(4)]
    source_point = [(source_bounds[0] + source_bounds[2]) / 2, source_bounds[3]]
    scale = geometry['display_reference_height_px'] / reference
    target = geometry['anchor_px']
    density = geometry['raster_scale']
    projected = [(source_point[i] - anchor[i]) * scale + target[i] for i in (0, 1)]
    projected_roi = [(roi[i] - anchor[i % 2]) * scale + target[i % 2] for i in range(4)]
    # Keep the band's top boundary; allow antialiased pixels beyond its side edges.
    rendered_roi = [max(0, math.floor((projected_roi[0] - 2) * density)),
                    max(0, math.floor(projected_roi[1] * density)),
                    min(rendered.width, math.ceil((projected_roi[2] + 2) * density)),
                    min(rendered.height, math.ceil((projected_roi[3] + 2) * density))]
    actual_bounds = visible_bbox(rendered.crop(tuple(rendered_roi)))
    if actual_bounds is None:
        return {**result, 'available': False, 'passed': False}
    actual_bounds = [(actual_bounds[i] + rendered_roi[i % 2]) / density for i in range(4)]
    actual_point = [(actual_bounds[0] + actual_bounds[2]) / 2, actual_bounds[3]]
    delta = [actual_point[i] - projected[i] for i in (0, 1)]
    return {**result, 'available': True, 'source_visible_bbox_px': source_bounds,
            'source_point_px': source_point, 'projected_point_px': projected,
            'source_offset_from_declared_anchor_px': [source_point[i] - anchor[i] for i in (0, 1)],
            'actual_visible_bbox_px': actual_bounds, 'actual_point_px': actual_point,
            'delta_px': delta, 'horizontal_delta_px': delta[0], 'vertical_delta_px': delta[1],
            'actual_to_declared_anchor_delta_px': [actual_point[i] - target[i] for i in (0, 1)],
            'passed': all(abs(v) <= SUPPORT_TOLERANCE for v in delta)}


def preview_geometry(root, review_path):
    review = load_review(root, review_path)
    geometry = _geometry(root, review)
    geometry['variants'] = {}
    for item in review['variants']:
        image = _preview(root, review, item, geometry)
        raster_bbox = visible_bbox(image)
        density = geometry['raster_scale']
        bbox = [v / density for v in raster_bbox] if raster_bbox else None
        scale = geometry['display_reference_height_px'] / item['reference_height_px']
        inverse_offset = [item['anchor_px'][i] - geometry['anchor_px'][i] / scale for i in (0, 1)]
        transformed = [(item['anchor_px'][i] - inverse_offset[i]) * scale for i in (0, 1)]
        deltas = [transformed[i] - geometry['anchor_px'][i] for i in (0, 1)]
        source_bbox = item['visible_bbox_px']
        projected = [(source_bbox[i] - item['anchor_px'][i % 2]) * scale
                     + geometry['anchor_px'][i % 2] for i in range(4)]
        width, height = geometry['canvas_size_px']
        contained = bool(bbox and bbox[0] > 0 and bbox[1] > 0 and bbox[2] < width
                         and bbox[3] < height and projected[0] >= 0 and projected[1] >= 0
                         and projected[2] <= width and projected[3] <= height)
        support = _support_raster_check(root, item, image, geometry)
        geometry['variants'][item['id']] = {'scale': scale, 'source_anchor_px': item['anchor_px'],
            'actual_anchor_px': transformed, 'anchor_delta_px': deltas,
            'horizontal_delta_px': support.get('horizontal_delta_px'),
            'vertical_delta_px': support.get('vertical_delta_px'),
            'visible_bbox_px': bbox, 'raster_visible_bbox_px': list(raster_bbox) if raster_bbox else None,
            'projected_visible_bbox_px': projected,
            'contained': contained, 'empty': bbox is None, 'clipping': not contained,
            'support_raster_check': support,
            'placement_calibration': image.info.get('placement_calibration'),
            'alignment_passed': contained and support['passed'],
            'anchor_check_basis': 'coordinate transform only; alignment_passed also requires independent rendered-alpha support_raster_check on both axes'}
    return geometry


def render_preview(root, review_path, variant_id):
    review = load_review(root, review_path)
    item = _find_variant(review, variant_id)
    output = io.BytesIO()
    _preview(root, review, item, _geometry(root, review)).save(output, format='PNG')
    return output.getvalue()


def _find_variant(review, name):
    if not isinstance(name, str):
        raise ReviewError('候補を選択してください。')
    for item in review['variants']:
        if item['id'] == name:
            return item
    raise ReviewError('登録されていない候補です。')


def _decision_directory(root, review_path):
    safe_path(root, review_path)
    relative = (Path(review_path).parent / 'decisions').as_posix()
    return relative, safe_path(root, relative)


def _event_prefix(review_path):
    return 'review-' + digest(review_path.encode('utf-8'))[:20] + '-'


def _events(root, review_path, review):
    relative, directory = _decision_directory(root, review_path)
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob(_event_prefix(review_path) + '*.json')):
        event = read_json(root, relative + '/' + path.name)
        if event.get('review_path') != review_path or event.get('review_sha256') != review['review_sha256']:
            raise ReviewError('選択履歴と比較データが一致しません。', 409)
        revision = event.get('revision')
        if type(revision) is not int or revision != len(result) + 1:
            raise ReviewError('選択履歴の連番を確認してください。', 409)
        name = event.get('variant_id')
        if name is not None:
            item = _find_variant(review, name)
            if event.get('image_sha256') != item['sha256'] or event.get('selected_path') != item['path']:
                raise ReviewError('選択履歴の画像が一致しません。', 409)
        result.append(event)
    return result


def latest_decision(root, review_path):
    review = load_review(root, review_path)
    events = _events(root, review_path, review)
    return events[-1] if events else None


@contextmanager
def _decision_lock(root, review_path):
    relative, directory = _decision_directory(root, review_path)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = safe_path(root, relative + '/.decision.lock')
    owner = secrets.token_hex(32).encode('ascii')
    deadline = time.monotonic() + 5
    while True:
        try:
            safe_path(root, relative + '/.decision.lock')
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ReviewError('別の保存処理が実行中です。少し待って再試行してください。', 409) from exc
            time.sleep(.02)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(owner)
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        # Never delete a replacement lock owned by another process.
        try:
            if read_bytes(root, relative + '/.decision.lock', 1024) == owner:
                safe_path(root, relative + '/.decision.lock').unlink()
        except (ReviewError, OSError):
            pass


def save_decision(root, review_path, variant_id, expected_review_sha256,
                  expected_image_sha256, note='', request_id=None):
    text(note, 'note', MAX_NOTE)
    request_id = request_id if request_id is not None else str(uuid.uuid4())
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', request_id):
        raise ReviewError('request_id の形式を確認してください。')
    with _decision_lock(root, review_path):
        review = load_review(root, review_path)
        if expected_review_sha256 != review['review_sha256']:
            raise ReviewError('比較データが更新されています。再読込してください。', 409)
        item = _find_variant(review, variant_id) if variant_id is not None else None
        if expected_image_sha256 != (item['sha256'] if item else None):
            raise ReviewError('選択画像が更新されています。再読込してください。', 409)
        events = _events(root, review_path, review)
        for event in events:
            if event.get('request_id') == request_id:
                if event.get('variant_id') != variant_id or event.get('note') != note:
                    raise ReviewError('同じrequest_idで異なる選択は保存できません。', 409)
                return event
        snapshot = lambda entry: {key: entry[key] for key in ('id', 'label', 'path', 'sha256')}
        event = {'schema_version': 1, 'review_id': review['id'], 'review_path': review_path,
                 'review_sha256': review['review_sha256'], 'manifest_sha256': review['review_sha256'],
                 'revision': len(events) + 1, 'created_at_utc': utc_now(), 'request_id': request_id,
                 'variant_id': variant_id, 'image_sha256': item['sha256'] if item else None,
                 'selected_path': item['path'] if item else None,
                 'selected_sha256': item['sha256'] if item else None, 'note': note,
                 'previous_variant': snapshot(_find_variant(review, review['previous_variant_id'])),
                 'recommended_variant': snapshot(_find_variant(review, review['recommended_variant_id'])),
                 'adoption_changed': False}
        # Recheck manifest and source immediately before making the new event visible.
        fresh = load_review(root, review_path)
        if fresh['review_sha256'] != review['review_sha256']:
            raise ReviewError('保存前に比較データが変わりました。', 409)
        directory, _ = _decision_directory(root, review_path)
        name = f'{_event_prefix(review_path)}{event["revision"]:08d}-{digest(request_id.encode())[:24]}.json'
        atomic_new(root, directory + '/' + name, payload(event))
        return event


def load_collection(root, collection_path):
    """Freeze a named set of independent reviews, each with its own ledger."""
    before = digest(read_bytes(root, collection_path))
    collection = read_json(root, collection_path)
    identifier(collection.get('id'))
    text(collection.get('title'), 'title')
    entries = collection.get('reviews')
    if collection.get('schema_version') != 1 or not isinstance(entries, list) or not 1 <= len(entries) <= 200:
        raise ReviewError('比較一覧の形式を確認してください。')
    contexts = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReviewError('比較一覧の項目を確認してください。')
        identity = identifier(entry.get('id'))
        if identity in contexts:
            raise ReviewError('比較一覧のIDが重複しています。')
        path = entry.get('review')
        document = load_review(root, path)
        if document['id'] != identity:
            raise ReviewError('比較一覧と比較設定のIDが一致しません。')
        contexts[identity] = {'path': path, 'initial': document,
                              'group': text(entry.get('group', ''), 'group', 100)}
    if digest(read_bytes(root, collection_path)) != before:
        raise ReviewError('読み込み中に比較一覧が変わりました。', 409)
    return collection, contexts, before


def collection_page(root, collection, contexts):
    rows = []
    for identity, context in contexts.items():
        current = load_review(root, context['path'])
        if current['review_sha256'] != context['initial']['review_sha256']:
            raise ReviewError('比較データが変わりました。サーバーを起動し直してください。', 409)
        decision = latest_decision(root, context['path'])
        if decision is None:
            status = '未選択'
        elif decision['variant_id'] is None:
            status = '保留'
        else:
            chosen = _find_variant(context['initial'], decision['variant_id'])
            status = '選択済み：' + chosen['label']
        label = context['initial']['title']
        rows.append(f'<li><a href="/r/{identity}/">{escape(label)}</a>'
                    f'<span>{escape(context["group"])} · {escape(status)}</span></li>')
    title = escape(collection['title'])
    return (f'<!doctype html><html lang="ja"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>'
            '<style>body{margin:0;background:#f5f1e9;color:#302b25;font:16px/1.7 system-ui,sans-serif}'
            'main{max-width:900px;margin:auto;padding:32px 24px}h1{line-height:1.4}'
            'ul{list-style:none;padding:0}li{padding:18px 0;border-bottom:1px solid #d9d1c4}'
            'a{color:#315b47;font-weight:700}span{display:block;color:#655e55;font-size:14px}</style>'
            f'<main><h1>{title}</h1><p>ポーズごとに前バージョンと再生成版を比較して選べます。'
            '各比較に「前バージョン」「AIおすすめ」の印があります。</p>'
            '<p>選択はポーズごとに保存されます。保留もできます。'
            '一覧の選択状況は画面を再読込すると更新されます。</p>'
            f'<ul>{"".join(rows)}</ul></main></html>').encode('utf-8')


def make_server(root, review_path=None, port=0, *, collection_path=None):
    root = Path(root).resolve()
    if (review_path is None) == (collection_path is None):
        raise ReviewError('比較設定または比較一覧を一つ指定してください。')
    if collection_path is None:
        contexts = {'': {'path': review_path, 'initial': load_review(root, review_path)}}
    else:
        collection, contexts, collection_sha = load_collection(root, collection_path)
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ReviewError('ポート番号を確認してください。')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'LocalImageReview/1'

        def log_message(self, format, *args):
            return

        def check_origin(self):
            if len(self.headers.get_all('Host', [])) != 1 or len(self.headers.get_all('Origin', [])) > 1:
                raise ReviewError('送信元の形式を確認してください。', 403)
            host = self.headers.get('Host', '')
            actual_port = self.server.server_address[1]
            if host not in (f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'):
                raise ReviewError('localhostの画面から接続してください。', 403)
            origin = self.headers.get('Origin')
            if origin is not None and origin != 'http://' + host:
                raise ReviewError('この送信元からは操作できません。', 403)
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                raise ReviewError('localhostの画面から操作してください。', 403)

        def send(self, status, data, content_type):
            try:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # A closed browser tab is not an application failure, and cannot
                # receive a second JSON error response on the same connection.
                self.close_connection = True

        def send_json(self, status, value):
            self.send(status, payload(value), 'application/json; charset=utf-8')

        def route_context(self):
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment:
                raise ReviewError('不明なリクエストです。', 404)
            route = unquote(parsed.path)
            self.route_prefix = ''
            if collection_path is not None:
                if digest(read_bytes(root, collection_path)) != collection_sha:
                    raise ReviewError('比較一覧が変わりました。サーバーを起動し直してください。', 409)
                if route in ('/', '/favicon.ico'):
                    return route
                match = re.fullmatch(r'/r/([A-Za-z0-9_-]+)/(.*)', route)
                if not match or match[1] not in contexts:
                    raise ReviewError('比較ページが見つかりません。', 404)
                context = contexts[match[1]]
                self.route_prefix = '/r/' + match[1]
                route = '/' + match[2]
            else:
                context = contexts['']
            self.review_file = context['path']
            self.initial_hash = context['initial']['review_sha256']
            return route

        def current_review(self):
            review = load_review(root, self.review_file)
            if review['review_sha256'] != self.initial_hash:
                raise ReviewError('比較データが変わりました。サーバーを起動し直してください。', 409)
            return review

        def handle_error(self, exc):
            if isinstance(exc, ReviewError):
                self.send_json(exc.status, {'error': str(exc)})
            else:
                self.send_json(500, {'error': '処理できませんでした。ファイルの状態を確認してください。'})

        def do_GET(self):
            try:
                self.check_origin()
                route = self.route_context()
                if route == '/':
                    if collection_path is not None and not self.route_prefix:
                        self.send(200, collection_page(root, collection, contexts), 'text/html; charset=utf-8')
                        return
                    data = read_bytes(root, 'tools/image_remake_review.html', 2 * 1024 * 1024)
                    if self.route_prefix:
                        navigation = '<nav style="padding:16px 32px"><a href="../../">← ポーズ一覧へ</a></nav>'
                        data = data.replace(b'<main', navigation.encode('utf-8') + b'<main', 1)
                    self.send(200, data, 'text/html; charset=utf-8')
                    return
                if route == '/favicon.ico':
                    self.send(204, b'', 'image/x-icon')
                    return
                review = self.current_review()
                if route == '/api/review':
                    value = {key: review.get(key) for key in ('schema_version', 'id', 'title', 'asset_id', 'review_sha256', 'display_reference_height_px')}
                    value.update(token=self.server.review_token, latest_decision=latest_decision(root, self.review_file), variants=[])
                    for item in review['variants']:
                        value['variants'].append({**item, 'preview_url': self.route_prefix + '/preview/' + item['id'] + '.png',
                                                  'original_url': self.route_prefix + '/original/' + item['id']})
                    self.send_json(200, value)
                    return
                match = re.fullmatch(r'/preview/([A-Za-z0-9_-]+)\.png', route)
                if match:
                    self.send(200, render_preview(root, self.review_file, match[1]), 'image/png')
                    return
                match = re.fullmatch(r'/original/([A-Za-z0-9_-]+)', route)
                if match:
                    item = _find_variant(review, match[1])
                    self.send(200, _variant_bytes(root, item), {'PNG': 'image/png', 'JPEG': 'image/jpeg',
                              'WEBP': 'image/webp', 'GIF': 'image/gif'}[item['format']])
                    return
                raise ReviewError('ページが見つかりません。', 404)
            except (ValueError, OSError) as exc:
                self.handle_error(exc)

        def do_POST(self):
            try:
                self.check_origin()
                if self.route_context() != '/api/decision':
                    raise ReviewError('ページが見つかりません。', 404)
                supplied = self.headers.get('X-Review-Token', '')
                if (len(self.headers.get_all('X-Review-Token', [])) != 1
                        or not secrets.compare_digest(supplied.encode('utf-8'), self.server.review_token.encode('ascii'))):
                    raise ReviewError('画面を再読込してから保存してください。', 403)
                if self.headers.get('Transfer-Encoding'):
                    raise ReviewError('分割転送には対応していません。')
                if self.headers.get_content_type() != 'application/json':
                    raise ReviewError('JSON形式で送信してください。', 415)
                try:
                    length = int(self.headers.get('Content-Length', ''))
                except ValueError as exc:
                    raise ReviewError('送信データの長さを確認してください。') from exc
                if not 0 < length <= MAX_BODY:
                    raise ReviewError('送信データが大きすぎます。', 413)
                try:
                    value = json.loads(self.rfile.read(length).decode('utf-8'))
                except (UnicodeError, ValueError) as exc:
                    raise ReviewError('JSONの形式を確認してください。') from exc
                allowed = {'variant_id', 'note', 'request_id', 'review_sha256', 'image_sha256'}
                if (not isinstance(value, dict) or set(value) - allowed
                        or not {'variant_id', 'request_id', 'review_sha256'} <= set(value)):
                    raise ReviewError('選択データの形式を確認してください。')
                self.current_review()
                event = save_decision(root, self.review_file, value['variant_id'], value['review_sha256'],
                                      value.get('image_sha256'), value.get('note', ''), value['request_id'])
                self.send_json(200, {'saved': True, 'decision': event})
            except (ValueError, OSError) as exc:
                self.handle_error(exc)

    class LocalReviewServer(ThreadingHTTPServer):
        def server_bind(self):
            # HTTPServer's default getfqdn() can block on unavailable local DNS.
            # The listener is fixed to a numeric loopback address and needs no lookup.
            socketserver.TCPServer.server_bind(self)
            self.server_name = 'localhost'
            self.server_port = self.server_address[1]

    server = LocalReviewServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.review_token = secrets.token_urlsafe(32)
    server.review_path = review_path
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--spec', required=True)
    prepare.add_argument('--output', required=True)
    for name in ('serve', 'show'):
        command = commands.add_parser(name)
        if name == 'serve':
            target = command.add_mutually_exclusive_group(required=True)
            target.add_argument('--review')
            target.add_argument('--collection')
            command.add_argument('--port', type=int, default=8765)
        else:
            command.add_argument('--review', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            review = prepare_review(args.root, args.spec, args.output)
            print(json.dumps({'prepared': args.output, 'review_sha256': review['review_sha256']}, ensure_ascii=False))
        elif args.command == 'show':
            review = load_review(args.root, args.review)
            decision = latest_decision(args.root, args.review)
            print(json.dumps({'id': review['id'], 'title': review['title'], 'review_sha256': review['review_sha256'],
                              'status': 'unselected' if decision is None else ('deferred' if decision['variant_id'] is None else 'selected'),
                              'latest_decision': decision}, ensure_ascii=False, indent=2))
        else:
            server = make_server(args.root, args.review, args.port, collection_path=args.collection)
            print(f'http://127.0.0.1:{server.server_address[1]}/', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except (ReviewError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
