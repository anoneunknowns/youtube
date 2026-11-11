"""Extract an acoustically reviewed word from a natural context take.

Boundaries must be chosen from acoustic/phonetic review, never ASR token peaks alone.
The extracted clip must receive fresh isolated recognition before adoption.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--number', required=True, type=int)
    parser.add_argument('--text', required=True)
    parser.add_argument('--context-text', required=True)
    parser.add_argument('--start', required=True, type=float)
    parser.add_argument('--end', required=True, type=float)
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    with wave.open(str(args.source), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
            raise ValueError('Expected PCM16 mono 24kHz source')
        raw = array('h', wav.readframes(wav.getnframes()))
    if sys.byteorder != 'little':
        raw.byteswap()
    start, end = round(args.start * 24000), round(args.end * 24000)
    if not 0 <= start < end <= len(raw):
        raise ValueError('Cut bounds outside source')
    cut = raw[start:end]
    fade, pad = 48, 360
    for i in range(len(cut)):
        cut[i] = round(cut[i] * min(1, i / fade, (len(cut) - 1 - i) / fade))
    samples = array('h', [0] * pad) + cut + array('h', [0] * pad)
    if sys.byteorder != 'little':
        samples.byteswap()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('xb') as output:
        with wave.open(output, 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(samples.tobytes())
    metadata = {
        'number': args.number, 'spoken_text': args.text,
        'path': args.out.resolve().as_posix(), 'duration_s': len(samples) / 24000,
        'sha256': hashlib.sha256(args.out.read_bytes()).hexdigest(),
        'measurement_status': 'measured',
        'generation': {
            'strategy': 'acoustically-reviewed-context-word-extraction',
            'context_text': args.context_text,
            'context_source_path': args.source.resolve().as_posix(),
            'context_source_sha256': hashlib.sha256(source_bytes).hexdigest(),
            'cut_start_s': start / 24000, 'cut_end_s': end / 24000,
            'edge_fade_ms': 2, 'silence_pad_ms': 15,
            'voice_id': 'af_heart', 'speed': .98, 'dtype': 'fp32',
            'model_id': 'onnx-community/Kokoro-82M-v1.0-ONNX',
            'model_sha256': '8fbea51ea711f2af382e88c833d9e288c6dc82ce5e98421ea61c058ce21a34cb',
            'acceptance': 'pending-fresh-isolated-review',
        },
    }
    args.out.with_suffix('.wav.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
