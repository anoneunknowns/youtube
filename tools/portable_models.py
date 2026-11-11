"""Download or verify the pinned optional CPU speech/ASR/CTC model cache."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen

MANIFEST = Path(__file__).with_name('portable_models_manifest.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(cache_root, selection, check_only=False):
    receipt = json.loads(MANIFEST.read_text(encoding='utf-8'))
    cache = Path(cache_root).expanduser().resolve()
    names = list(receipt['models']) if selection == 'all' else [selection]
    checked = []
    for name in names:
        model = receipt['models'][name]
        directory = (cache / model['model_id']).resolve()
        for entry in model['files']:
            target = (directory / entry['path']).resolve()
            if not target.is_relative_to(directory):
                raise ValueError('Model manifest escapes its cache directory')
            if not target.is_file():
                if check_only:
                    raise ValueError(f'Model file missing: {target}')
                target.parent.mkdir(parents=True, exist_ok=True)
                url = f'https://huggingface.co/{model["model_id"]}/resolve/{model["revision"]}/{quote(entry["path"], safe="/")}?download=true'
                request = Request(url, headers={'User-Agent': 'youtube-production-portable-model-setup/1'})
                descriptor, temporary = tempfile.mkstemp(prefix='model-download-', suffix='.part', dir=target.parent)
                temporary = Path(temporary)
                try:
                    with os.fdopen(descriptor, 'wb') as output, urlopen(request, timeout=120) as response:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                    if temporary.stat().st_size != entry['bytes'] or digest(temporary) != entry['sha256']:
                        raise ValueError(f'Download did not match the pinned model receipt: {target}')
                    if target.exists():
                        raise FileExistsError(f'Model appeared during download; refusing replacement: {target}')
                    temporary.rename(target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            if target.stat().st_size != entry['bytes'] or digest(target) != entry['sha256']:
                raise ValueError(f'Existing model is not the pinned version; preserve and inspect: {target}')
            checked.append({'model': name, 'path': str(target), 'sha256': entry['sha256']})
            print(json.dumps({'model': name, 'verified': entry['path']}), flush=True)
    return {'status': 'pass', 'cache_root': str(cache), 'models': names, 'files_verified': len(checked),
            'check_only': check_only, 'manifest_sha256': digest(MANIFEST),
            'note': 'Rendering existing adopted productions needs no AI models. npm ci supplies the pinned speech runtime and voice data.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-root', required=True, type=Path)
    parser.add_argument('--model', choices=['all', 'kokoro', 'asr', 'phoneme'], default='all')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.cache_root, args.model, args.check_only), indent=2))


if __name__ == '__main__':
    main()
