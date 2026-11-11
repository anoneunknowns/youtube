"""Read-only LPC comparison of ambiguous pair vowels; not a listening claim."""
import array
import cmath
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

OUT = Path(__file__).resolve().parent

def roots(coeff):
    degree = len(coeff) - 1
    values = [0.97 * cmath.exp(2j * math.pi * (k + 0.17) / degree) for k in range(degree)]
    for _ in range(150):
        updated = []
        for i, value in enumerate(values):
            numerator = coeff[0]
            for c in coeff[1:]:
                numerator = numerator * value + c
            denominator = 1 + 0j
            for j, other in enumerate(values):
                if i != j:
                    denominator *= value - other
            updated.append(value - numerator / (denominator or 1e-30))
        delta = max(abs(a - b) for a, b in zip(updated, values))
        values = updated
        if delta < 1e-9:
            break
    return values

def formants(samples, rate):
    emphasized = [samples[0]] + [samples[i] - 0.97 * samples[i - 1] for i in range(1, len(samples))]
    window = [v * (0.54 - 0.46 * math.cos(2 * math.pi * i / (len(samples) - 1)))
              for i, v in enumerate(emphasized)]
    order = 14
    correlations = [sum(window[i] * window[i - lag] for i in range(lag, len(window)))
                    for lag in range(order + 1)]
    a = [1.0]
    error = correlations[0]
    if error < 1e-12:
        return []
    for k in range(1, order + 1):
        reflection = -(correlations[k] + sum(a[j] * correlations[k - j] for j in range(1, k))) / error
        old = a
        a = old + [reflection]
        for j in range(1, k):
            a[j] = old[j] + reflection * old[k - j]
        error *= max(1e-8, 1 - reflection * reflection)
    found = []
    for root in roots(a):
        if root.imag <= 0:
            continue
        frequency = cmath.phase(root) * rate / (2 * math.pi)
        bandwidth = -math.log(abs(root)) * rate / math.pi
        if 100 < frequency < 5500 and 0 < bandwidth < 450:
            found.append((frequency, bandwidth))
    return sorted(found)

def main():
    cases = [('I03', 'candidates-v001/I03.wav', 1.16, 1.38),
             ('I05', 'candidates-v001/I05.wav', 1.58, 1.82),
             ('I03-stress', 'targeted-v002/I03-stress.wav', 1.16, 1.38),
             ('I05-stress', 'targeted-v002/I05-stress.wav', 1.60, 1.84)]
    rows = []
    for identity, relative, start, end in cases:
        path = OUT / relative
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-ac', '1',
                                       '-ar', '12000', '-f', 'f32le', 'pipe:1'])
        samples = array.array('f', raw)
        frames = []
        for center in range(round(start * 12000), round(end * 12000), 120):
            f = formants(samples[center - 240:center + 240], 12000)
            frames.append({'time_s': center / 12000,
                           'formants_hz_bw': [[round(x, 1), round(y, 1)] for x, y in f]})
        rows.append({'id': identity, 'source_path': str(path),
                     'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'region_s': [start, end], 'frames': frames})
    report = {'schema_version': 1, 'kind': 'isolated-acoustic-analysis',
              'method': 'Unmodified WAV decoded at 12kHz. 40ms Hamming windows, 10ms hop, 0.97 pre-emphasis, autocorrelation LPC order14; positive roots with bandwidth<450Hz. Read-only diagnostic, not proof of pronunciation or human listening.',
              'results': rows}
    with (OUT / 'pair-vowel-formants.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    for row in rows:
        print(row['id'], [(f['time_s'], f['formants_hz_bw'][:4]) for f in row['frames'][::4]])

if __name__ == '__main__':
    main()
