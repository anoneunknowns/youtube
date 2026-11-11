"""Portable source-audio checks for decimal and binary adopted productions.

The launcher starts this as a child with explicit media tools on PATH and the
chosen scratch directory in TEMP/TMP/TMPDIR. Historical recipe files are kept
byte-for-byte; only the binary recipe's declared baseline resolver is adapted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile

import portable_production as portable
from portable_speech_library import resolve_reference


def decimal_source_events(plan, manifest_path, sfx_dir):
    mixer = portable.module('build_audio_mix')
    manifest = portable.read(manifest_path)
    rows = mixer._speech_rows(manifest, manifest_path)
    total_frames, raw_events = mixer._timeline_events(plan, rows, sfx_dir)
    registration = portable.read(sfx_dir / 'generation-spec.json')
    sounds = {row['id']: row for row in registration['assets']}
    events = []
    for ordinal, raw in enumerate(raw_events, 1):
        role, identifier = raw['key']
        path = Path(raw['path'])
        expected = sounds[identifier]['sha256'] if role == 'sfx' else rows[raw['key']]['sha256']
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f'The audio source has no SHA-256 identity: {path}')
        portable.require_file(path, expected)
        kind = 'sfx' if role == 'sfx' else 'number_voice' if role == 'number' else 'dialogue'
        events.append({'id': f'{role}-{ordinal:04d}', 'type': kind,
                       'start_s': raw['start_s'], 'end_s': raw['end_s'],
                       'source_path': str(path.resolve()), 'source_sha256': expected})
    return total_frames, events


def verify_decimal(args):
    plan = portable.read(args.timeline)
    manifest_path = portable.ROOT / 'assets/library/audio/speech/kokoro-af-heart/v002/measurements.json'
    sfx_dir = portable.ROOT / 'assets/library/audio/sfx/garden/v001'
    expected_frames, events = decimal_source_events(plan, manifest_path, sfx_dir)
    verifier = portable.module('verify_octal_audio')
    with tempfile.TemporaryDirectory(prefix='decimal-audio-qa-', dir=args.work_dir) as temporary:
        directory = Path(temporary)
        references = verifier.source_references(events, args.ffmpeg, directory)
        encoded = verifier.verify_track(args.video, events, references, expected_frames,
                                         args.ffmpeg, directory, lossy=True)
    result = {'passed': True, 'kind': 'portable-decimal-source-audio-qa',
              'timeline_sha256': portable.sha256(args.timeline), 'encoded_audio': encoded,
              'scope': 'All 300 number utterances, scheduled dialogue and SFX versus source WAVs; all non-event interiors silent.',
              'asr_or_human_listening_claimed': False}
    portable.save_new(args.out, result)
    return result


def verify_binary(args):
    verifier = portable.module('verify_binary_production_v005')
    previous = verifier.previous
    original = previous.read_bound_baseline
    def read_baseline(plan):
        path = resolve_reference(plan.get('baseline_timeline', ''))
        portable.require_file(path, plan.get('baseline_timeline_sha256'))
        return portable.read(path), path.resolve()
    previous.read_bound_baseline = read_baseline
    try:
        status = verifier.main(['--timeline', str(args.timeline), '--speech-manifest',
                                str(portable.ROOT / 'assets/library/audio/speech/kokoro-af-heart/binary-v001/measurements.json'),
                                '--video', str(args.video), '--captions', str(args.captions), '--out', str(args.out)])
    finally:
        previous.read_bound_baseline = original
    if status:
        raise ValueError('The binary source-audio/pause verifier failed')
    return {'passed': True, 'kind': 'portable-binary-source-audio-qa', 'report': str(args.out),
            'scope': 'Existing v005 full speech waveform, 642 internal 0.9s gaps, 127 complete-number boundaries and caption checks.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', choices=['decimal', 'binary'], required=True)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--captions', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--ffmpeg', required=True)
    args = parser.parse_args(argv)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    # The legacy verifiers pass D:/temp if it exists; otherwise their standard
    # tempfile fallback uses this explicit per-process scratch location.
    tempfile.tempdir = str(args.work_dir.resolve())
    if args.production == 'binary' and args.captions is None:
        parser.error('binary verification requires --captions')
    result = verify_binary(args) if args.production == 'binary' else verify_decimal(args)
    summary = {'passed': result['passed'], 'kind': result['kind'], 'report': str(args.out)}
    if 'encoded_audio' in result:
        summary.update({key: result['encoded_audio'][key] for key in
                        ['clips_checked', 'speech_clips_checked', 'sfx_clips_checked', 'minimum_speech_correlation',
                         'maximum_silent_interior_peak_pcm16']})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
