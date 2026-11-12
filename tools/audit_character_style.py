"""Read-only contour/palette screening of explicitly adopted new character art.

Measurements support visual review; they do not certify design consistency.
No source pixels, registrations, catalogs, or historical QA files are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def lab(rgb):
    linear = [v / 3294.6 if v <= 10.31475 else ((v / 255 + .055) / 1.055) ** 2.4 for v in rgb]
    r, g, b = linear
    xyz = [(.4124564*r+.3575761*g+.1804375*b)/.95047,
           .2126729*r+.7151522*g+.072175*b,
           (.0193339*r+.119192*g+.9503041*b)/1.08883]
    f = [v ** (1/3) if v > (6/29)**3 else v/(3*(6/29)**2)+4/29 for v in xyz]
    return [116*f[1]-16, 500*(f[0]-f[1]), 200*(f[1]-f[2])]


def delta_e(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(lab(a), lab(b))))


def luma(rgb):
    return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]


def contours(image, reference_height, target_height):
    """Horizontal light-fill side profiles, corrected for silhouette slope.

    Dark fur, narrow limbs, near-horizontal boundaries, and weak color contrast
    are rejected, so these are comparable light-region contour samples only.
    """
    alpha = image.getchannel('A')
    bbox = alpha.point(lambda a: 255 if a >= 230 else 0).getbbox()
    if bbox is None:
        return {'sample_count': 0, 'status': 'unmeasurable'}
    pixels = image.load()
    cached = {}
    def ends(y):
        if y not in cached:
            row = alpha.crop((0, y, image.width, y+1)).point(lambda a: 255 if a >= 230 else 0).getbbox()
            cached[y] = None if row is None else (row[0], row[2]-1)
        return cached[y]
    samples = []
    stride = max(1, round((bbox[3]-bbox[1])/100))
    reach = max(12, round(reference_height*.14))
    for y in range(max(bbox[1]+3, 3), min(bbox[3]-3, image.height-3), stride):
        row, prev, nxt = ends(y), ends(y-2), ends(y+2)
        if not row or not prev or not nxt:
            continue
        for side, direction in [(0, 1), (1, -1)]:
            x = row[side]
            slope = (nxt[side]-prev[side])/4
            if abs(slope) > .75 or not 2 <= x < image.width-2:
                continue
            run = []
            for k in range(reach):
                xx = x+direction*k
                if not 0 <= xx < image.width:
                    break
                value = pixels[xx, y]
                if value[3] < 230:
                    break
                run.append(value[:3])
            if len(run) < 10:
                continue
            values = [luma(p) for p in run]
            darkest = min(values[:min(5, len(values))])
            bright = sorted(values)[round((len(values)-1)*.8)]
            if bright-darkest < 55 or darkest > 125:
                continue
            threshold = darkest+(bright-darkest)*.45
            boundary = next((k for k in range(1, len(values)-2)
                             if all(v > threshold for v in values[k:k+3])), None)
            if boundary is None or boundary < 1 or boundary > reference_height*.045:
                continue
            dark = [run[k] for k in range(boundary) if values[k] <= darkest+(bright-darkest)*.25]
            if not dark:
                continue
            color = [median(v[c] for v in dark) for c in range(3)]
            width = (boundary-.5)/math.sqrt(1+slope*slope)
            samples.append({'x':x, 'y':y, 'side':'left' if side == 0 else 'right',
                            'source_width_px':round(width, 3),
                            'display_width_px':round(width*target_height/reference_height, 3),
                            'rgb':color})
    if not samples:
        return {'sample_count': 0, 'status': 'unmeasurable'}
    widths = sorted(s['display_width_px'] for s in samples)
    return {'status':'measured', 'sample_count':len(samples),
            'median_display_width_px':median(widths),
            'display_width_p25_p75_px':[widths[len(widths)//4], widths[3*len(widths)//4]],
            'median_rgb':[median(s['rgb'][c] for s in samples) for c in range(3)],
            'samples':samples}


def palette(image):
    """Opaque-subject palette; pose/marking proportions and props affect it."""
    pix = image.load()
    step = max(1, round(max(image.size)/350))
    rgb = bytearray()
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            p = pix[x, y]
            if p[3] >= 245:
                rgb.extend(p[:3])
    if not rgb:
        return []
    sample = Image.frombytes('RGB', (len(rgb)//3, 1), bytes(rgb))
    quantized = sample.quantize(colors=12, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    colors = quantized.getpalette()
    total = sample.width
    return [{'rgb':colors[index*3:index*3+3], 'fraction':count/total}
            for count,index in sorted(quantized.getcolors(), reverse=True)]


def inspect(root, output):
    output.mkdir(parents=True, exist_ok=True)
    index_path = root/'catalogs/character-library-v1.json'
    index = json.loads(index_path.read_text())
    records, references, groups, original_hashes = [], [], [], {}
    for c in index['characters']:
        identity, target = c['id'], c['comparison_body_height_px']
        n = c['neutral']; p = root/n['path']; original_hashes[n['path']] = sha(p)
        with Image.open(p) as opened:
            im = opened.crop(n['image_region_px'])
        base_contour = contours(im, n['reference_height_px'], target)
        base_palette = palette(im)
        references.append({'character_id':identity, 'source':n['path'], 'target_body_height_px':target,
                           'reference_height_px':n['reference_height_px'],
                           'contour':base_contour, 'palette':base_palette})
        for block, prefix in [('expanded_key_poses','expanded'), ('eyecatch_key_poses','eyecatch')]:
            if block not in c:
                continue
            rpath = c[block]['registration']; original_hashes[rpath] = sha(root/rpath)
            registration = json.loads((root/rpath).read_text())
            for frame in registration['frames']:
                path = root/frame['path']; original_hashes[frame['path']] = sha(path)
                with Image.open(path) as opened:
                    image = opened.copy()
                measure = contours(image, frame['reference_height_px'], target)
                colors = palette(image)
                ratio = color_delta = None
                if measure['sample_count'] >= 8 and base_contour['sample_count'] >= 8:
                    ratio = measure['median_display_width_px']/base_contour['median_display_width_px']
                    color_delta = delta_e(measure['median_rgb'], base_contour['median_rgb'])
                palette_distance = sum(p['fraction']*min(delta_e(p['rgb'], q['rgb']) for q in base_palette) for p in colors)
                records.append({'character_id':identity,'set':prefix,'sheet':frame['sheet_id'],
                                'pose':frame['id'],'path':frame['path'],
                                'source_sha256':frame['sha256'], 'reference_height_px':frame['reference_height_px'],
                                'target_body_height_px':target, 'contour':measure,
                                'contour_width_ratio_to_canonical':ratio,
                                'contour_color_delta_e76_to_canonical':color_delta,
                                'opaque_palette':colors,
                                'weighted_nearest_canonical_palette_delta_e76':palette_distance,
                                'screening_flags':(['contour_width_review'] if ratio is not None and not .75 <= ratio <= 1.35 else [])+
                                                  (['contour_color_review'] if color_delta is not None and color_delta > 6 else [])})
            for sheet in registration['sheets']:
                subset = [x for x in records if x['character_id']==identity and x['set']==prefix and x['sheet']==sheet['id']]
                ratios = [x['contour_width_ratio_to_canonical'] for x in subset if x['contour_width_ratio_to_canonical'] is not None]
                deltas = [x['contour_color_delta_e76_to_canonical'] for x in subset if x['contour_color_delta_e76_to_canonical'] is not None]
                groups.append({'character_id':identity,'set':prefix,'sheet':sheet['id'],
                               'pose_count':len(subset),'measurable_pose_count':len(ratios),
                               'median_contour_width_ratio':median(ratios) if ratios else None,
                               'median_contour_color_delta_e76':median(deltas) if deltas else None,
                               'flagged_poses':sum(bool(x['screening_flags']) for x in subset)})
    changed = [p for p,h in original_hashes.items() if sha(root/p) != h]
    if changed:
        raise ValueError(f'Source files changed during read-only audit: {changed}')
    result = {'scope':'414 newly generated adopted pose PNGs only; 11 canonical neutrals are comparison references.',
              'method':'Light-fill external silhouette side profiles, alpha>=230, silhouette slope<=0.75; darkness-to-interior contrast>=55, width crossing45% of luminance contrast, slope-normal correction. Scale uses registered sheet height; no per-pose fit. RGB medians and CIE Lab deltaE76; 12-color opaque palette nearest-reference distance.',
              'interpretation':'Screening, not automatic acceptance. Width flags below0.75/above1.35 and contour-color deltaE76>6 only request visual review. Dark fur and near-horizontal edges are excluded. Source texture, pose, low sample counts, accessories, species marks and registration proxies can bias estimates. Palette proportions are not required to match between poses.',
              'new_pose_count':len(records),'source_group_count':len(groups),
              'read_only_source_files_checked':len(original_hashes),'changed_source_files':changed,
              'references':references,'groups':groups,'records':records}
    path = output/'metrics.json'
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return {'new_poses':len(records),'groups':len(groups),'source_files_unchanged':len(original_hashes),'output':str(path)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True,help='New diagnostic output directory')
    args=parser.parse_args()
    print(json.dumps(inspect(args.root.resolve(),args.output.resolve()),ensure_ascii=False))
