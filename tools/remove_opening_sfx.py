"""Silence the sole opening SFX in a PCM master while preserving every later byte.

This targets a known, separately scheduled intro cue, not general noise reduction.
No speech, other SFX, normalization, timing or WAV headers are rewritten.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import wave


def digest_range(path, start=0):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        source.seek(start)
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def data_region(path):
    with Path(path).open('rb') as source:
        riff = source.read(12)
        if riff[:4] != b'RIFF' or riff[8:] != b'WAVE':
            raise ValueError('Expected RIFF/WAVE')
        while header := source.read(8):
            if len(header) != 8:
                raise ValueError('Truncated WAV chunk header')
            name, size = struct.unpack('<4sI', header)
            if name == b'data':
                return source.tell(), size
            source.seek(size + (size % 2), 1)
    raise ValueError('WAV data chunk missing')


def remove_opening_sfx(master_path, timeline_path, out_path):
    timeline = json.loads(Path(timeline_path).read_text(encoding='utf-8-sig'))
    events = sorted(timeline['events'], key=lambda row: row['start_s'])
    first = events[0]
    if not (first.get('kind') == 'sfx' and first.get('source') == 'intro'
            and first.get('id') == 'SE_WIND' and 0 <= first['start_s'] < first['end_s'] < 1):
        raise ValueError('First event is not the expected isolated opening SE_WIND')
    if any(row['start_s'] < first['end_s'] for row in events[1:]):
        raise ValueError('Another audio event overlaps the removal window')
    with wave.open(str(master_path), 'rb') as source:
        rate, channels, width, frames = source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getnframes()
        if (rate, channels, width) != (48000, 2, 3):
            raise ValueError('Expected adopted PCM24 stereo 48kHz master')
    offset, size = data_region(master_path)
    frame_size = channels * width
    end_frame = math.ceil(first['end_s'] * rate - 1e-9)
    if size != frames * frame_size or not 0 < end_frame < frames:
        raise ValueError('WAV length or edit bounds invalid')
    if Path(out_path).exists():
        raise ValueError('Refusing to replace an existing master')
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(master_path, out_path)
    byte_count = end_frame * frame_size
    with Path(out_path).open('r+b') as target:
        target.seek(offset)
        target.write(bytes(byte_count))
    with Path(out_path).open('rb') as check:
        check.seek(offset)
        silent = check.read(byte_count) == bytes(byte_count)
    unchanged_tail = digest_range(master_path, offset + byte_count) == digest_range(out_path, offset + byte_count)
    with Path(master_path).open('rb') as old, Path(out_path).open('rb') as new:
        unchanged_header = old.read(offset) == new.read(offset)
    same_size = Path(master_path).stat().st_size == Path(out_path).stat().st_size
    if not all([silent, unchanged_tail, unchanged_header, same_size]):
        raise ValueError('Targeted edit verification failed')
    return {'schema_version': 1, 'kind': 'targeted-opening-sfx-removal',
            'removed_cue': first, 'source_master_sha256': digest_range(master_path),
            'master_sha256': digest_range(out_path), 'master_path': str(Path(out_path).resolve()),
            'sample_rate': rate, 'channels': channels, 'pcm_bits': width * 8,
            'duration_s': frames / rate, 'silenced_frames': [0, end_frame],
            'silenced_seconds': [0, end_frame / rate], 'wav_data_offset': offset,
            'unchanged_pcm_tail_sha256': digest_range(out_path, offset + byte_count),
            'verification': {'opening_is_silent': silent, 'later_pcm_bytes_identical': unchanged_tail,
                             'wav_header_identical': unchanged_header, 'file_length_identical': same_size},
            'normalization_reapplied': False, 'speech_regenerated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', required=True, type=Path)
    parser.add_argument('--timeline', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError('Refusing to replace an existing edit receipt')
    receipt = remove_opening_sfx(args.master, args.timeline, args.out)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x', encoding='utf-8') as output:
        json.dump(receipt, output, indent=2)
        output.write('\n')
    print(json.dumps({'removed': receipt['removed_cue'], **receipt['verification'], 'duration_s': receipt['duration_s']}))


if __name__ == '__main__':
    main()
