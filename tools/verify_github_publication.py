"""Verify the selected current files in the non-video GitHub snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'catalogs/github-publication-v1.json'
RECEIPT = 'reproducibility/github-publication-files-v1.json'
VIDEO = {'.mp4', '.m4v', '.mov', '.mkv', '.webm', '.avi', '.wmv', '.flv',
         '.f4v', '.mpeg', '.mpg', '.mpe', '.3gp', '.3g2', '.mts', '.m2ts',
         '.vob', '.ogv', '.m2v', '.divx', '.mxf', '.asf', '.qt', '.rm', '.rmvb'}


def video(path):
    return (Path(path).suffix.lower() in VIDEO or
            (Path(path).suffix.lower() == '.ts' and path.startswith(('assets/', 'output/', 'design/'))))


def safe_file(root, name):
    if (not isinstance(name, str) or not name or '\\' in name or
            PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts):
        raise ValueError(f'Invalid publication path: {name}')
    path = root
    for part in PurePosixPath(name).parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f'Publication path contains a symlink: {name}')
    return path


def verify(root=ROOT, check_git=False):
    root = Path(root).resolve()
    profile = json.loads(safe_file(root, PROFILE).read_text(encoding='utf-8'))
    if profile.get('schema_version') != 1 or profile.get('scope') != 'current-only-nonvideo':
        raise ValueError('Expected the current-only non-video publication profile')
    paths = profile['files']
    if not isinstance(paths, list) or len(paths) != len(set(paths)) or paths != sorted(paths):
        raise ValueError('Publication paths must be sorted and unique')
    if PROFILE not in paths or RECEIPT not in paths:
        raise ValueError('Publication profile and hash receipt must be included')
    receipt = json.loads(safe_file(root, RECEIPT).read_text(encoding='utf-8'))
    rows = receipt['files']
    entries = {row['path']: row for row in rows}
    if len(entries) != len(rows) or set(entries) != set(paths) - {RECEIPT}:
        raise ValueError('Hash receipt must cover every published file except itself')
    total = 0
    for name in paths:
        if video(name):
            raise ValueError(f'Video file is outside the publication scope: {name}')
        path = safe_file(root, name)
        if not path.is_file():
            raise ValueError(f'Missing published file: {name}')
        total += path.stat().st_size
        if name == RECEIPT:
            continue
        with path.open('rb') as source:
            if source.read(44).startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise ValueError(f'Fetch the LFS file content: {name}')
            source.seek(0)
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        row = entries[name]
        if path.stat().st_size != row['bytes'] or digest != row['sha256']:
            raise ValueError(f'Published file differs from its frozen receipt: {name}')
    if check_git:
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
        if set(filter(None, tracked)) != set(paths):
            raise ValueError('Git index does not match the selected publication paths')
    return {'status': 'pass', 'scope': profile['scope'], 'files': len(paths),
            'bytes': total, 'video_files': 0, 'git_index_checked': check_git,
            'active_productions': len(profile.get('active_production_set_ids', []))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check-git', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root, args.check_git), ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Publication verification failed: {error}\n')


if __name__ == '__main__':
    main()
