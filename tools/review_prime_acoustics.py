"""Read-only source waveform and initial-fricative screens for prime speech.

Heuristic signal evidence; this never approves a clip by itself or edits audio.
The existing terminal-tail tool supplies complementary final-consonant evidence.
"""
from __future__ import annotations
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave

from verify_terminal_tails import frame_metrics


def review(manifest_path, phonemes_path):
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    ctc = json.loads(phonemes_path.read_text())
    by_id = {r['id']: r for r in ctc['results']}
    results = []
    for row in manifest['numbers'] + manifest['dialogue']:
        p = Path(row['path'])
        if not p.is_absolute():
            p = manifest_path.parent / p
        b = p.read_bytes()
        if hashlib.sha256(b).hexdigest() != row['sha256']:
            raise ValueError(f'WAV hash mismatch: {row["id"]}')
        with wave.open(str(p)) as w:
            rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            if channels != 1 or width != 2:
                raise ValueError('Expected mono PCM16 WAV')
            samples = array.array('h', w.readframes(frames))
        if sys.byteorder != 'little':
            samples.byteswap()
        values = [v / 32768 for v in samples]
        peak = max(abs(v) for v in samples)
        activity = [i for i, v in enumerate(samples) if abs(v) >= 104]
        if not activity or abs(frames/rate - row['duration_s']) > 1/rate:
            raise ValueError('Empty or incorrectly measured clip')
        first = ''.join(c for c in by_id[row['id']]['expected_espeak'] if c.isalpha())[0]
        head = []
        if first in ('f', 's', 'θ'):
            window, hop = round(.020*rate), round(.010*rate)
            for start in range(0, min(len(values)-window, round(.280*rate))+1, hop):
                m = frame_metrics(values[start:start+window], rate)
                noise = m['high_ratio_2khz_up'] >= .35 and m['periodicity'] < .35 and m['rms_dbfs'] > -45
                voiced = m['rms_dbfs'] > -45 and m['periodicity'] >= .60 and m['low_ratio_under_1khz'] >= .60
                head.append({'start_s':start/rate, 'center_s':(start+window/2)/rate,
                             **{k: round(v,6) for k,v in m.items()},
                             'unvoiced_frication':noise, 'voiced':voiced})
        noise_index = next((i for i,m in enumerate(head) if m['unvoiced_frication']), None)
        prefix = [m for i,m in enumerate(head) if (noise_index is None or i<noise_index) and m['voiced']]
        result = {'id':row['id'],'source_path':str(p),'source_sha256':row['sha256'],
                  'duration_s':frames/rate,'samples':frames,'sample_rate':rate,
                  'peak_pcm16':peak,'rms_dbfs':20*math.log10(math.sqrt(sum(v*v for v in values)/len(values))+1e-15),
                  'clipped_samples':sum(abs(v)>=32767 for v in samples),
                  'first_sample':samples[0],'last_sample':samples[-1],
                  'head_margin_at_minus50db_s':activity[0]/rate,
                  'tail_margin_at_minus50db_s':(frames-1-activity[-1])/rate,
                  'initial_expected_phone':first,'fricative_screen_applies':bool(head),
                  'first_unvoiced_frication_s':head[noise_index]['center_s'] if noise_index is not None else None,
                  'voiced_prefix_before_frication_ms':len(prefix)*10,
                  'voiced_prefix_warning':bool(prefix),
                  'initial_fricative_not_resolved':bool(head) and noise_index is None,
                  'head_frames':head}
        results.append(result)
    warnings = [r['id'] for r in results if r['clipped_samples'] or r['voiced_prefix_warning'] or r['initial_fricative_not_resolved']]
    return {'schema_version':1,'kind':'prime-source-waveform-acoustic-screen',
            'source_manifest_sha256':hashlib.sha256(raw).hexdigest(),
            'method':{'onset':'20ms windows/10ms hop in first280ms; unvoiced frication high2kHz>=.35,periodicity<.35,RMS>-45dBFS; preceding voiced windows require lowband>=.60,periodicity>=.60,RMS>-45dBFS.',
                      'edge':'Activity threshold104/32768 (~-50dBFS), exact endpoint samples, clipping samples.',
                      'limitation':'Heuristic source screening, not a listening claim or independent pronunciation approval. Speech onset/tail CTC and per-case review are separate.'},
            'summary':{'clips':len(results),'fricative_initial_targets':sum(r['fricative_screen_applies'] for r in results),
                       'voiced_prefix_warnings':sum(r['voiced_prefix_warning'] for r in results),
                       'fricative_unresolved':sum(r['initial_fricative_not_resolved'] for r in results),
                       'clipped_samples':sum(r['clipped_samples'] for r in results)},
            'warning_ids':warnings,'results':results,'pronunciation_approved':False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--phonemes',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a = p.parse_args()
    r = review(a.manifest,a.phonemes)
    with a.out.open('x') as f:
        json.dump(r,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(r['summary']))
