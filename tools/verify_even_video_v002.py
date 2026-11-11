"""Run the independent even verifier with the v002 transition renderer reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import render_even_video as base_renderer
from render_even_video_v002 import Scene
import verify_even_video as verifier


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--timeline', type=Path)
    parser.add_argument('--output-dir', type=Path)
    args, _ = parser.parse_known_args()
    if args.timeline:
        timeline = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
        if timeline.get('revision_id') != 'even-counting-v002':
            raise ValueError('This verifier is for the reviewed v002 recipe')
    original = base_renderer.Scene
    try:
        # Only the reference for rendered diagrams changes. Mathematical,
        # independent glyph, waveform, caption and media checks are unchanged.
        base_renderer.Scene = Scene
        status = verifier.main()
    finally:
        base_renderer.Scene = original
    if args.output_dir:
        report = args.output_dir / 'even-final-qa.json'
        record = {'kind': 'even-v002-verifier-wrapper', 'status': 'pass' if status == 0 else 'fail',
                  'core_report': str(report), 'core_report_sha256': verifier.technical.sha256_file(report),
                  'core_verifier_sha256': verifier.technical.sha256_file(Path(verifier.__file__)),
                  'wrapper_sha256': verifier.technical.sha256_file(Path(__file__)),
                  'v002_renderer_sha256': verifier.technical.sha256_file(Path(__file__).with_name('render_even_video_v002.py'))}
        with (args.output_dir / 'even-v002-verifier-wrapper.json').open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2)
            stream.write('\n')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
