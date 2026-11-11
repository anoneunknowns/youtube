"""Fresh narrow signal checks for internal consonant CTC-label differences."""
from pathlib import Path
import hashlib
import json
import array
import cmath
import math
import statistics
import wave

ROOT = Path(__file__).resolve().parents[3]
QA = Path(__file__).resolve().parent
OUT = QA.parent


def load(path):
    with wave.open(str(path)) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (24000, 1, 2)
        pcm = array.array('h', wav.readframes(wav.getnframes()))
    return [sample/32768 for sample in pcm]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fft(values):
    if len(values) == 1:
        return values
    even, odd = fft(values[::2]), fft(values[1::2])
    phased = [cmath.exp(-2j*math.pi*i/len(values))*value for i, value in enumerate(odd)]
    return [a+b for a, b in zip(even, phased)] + [a-b for a, b in zip(even, phased)]


def feature(samples):
    windowed = [sample*(.5-.5*math.cos(2*math.pi*i/(len(samples)-1))) for i, sample in enumerate(samples)]
    size = 1 << (len(samples)-1).bit_length()
    spectrum = fft(windowed + [0]*(size-len(samples)))
    powers = [(i*24000/size, abs(value)**2) for i, value in enumerate(spectrum[:size//2+1])]
    band = [(frequency, power) for frequency, power in powers if 200 <= frequency <= 10000]
    energy = sum(power for frequency, power in band)
    return {'rms_dbfs': 20*math.log10(max(1e-12, math.sqrt(sum(sample**2 for sample in samples)/len(samples)))),
            'spectral_centroid_200_to10000_hz': sum(frequency*power for frequency, power in band)/energy,
            'energy_ratio_3000_to10000_over200_to10000': sum(power for frequency, power in band if frequency >= 3000)/energy}


source_manifest = OUT / 'speech/measurements.json'
data = json.loads(source_manifest.read_text())
source = {row['id']: row for row in data['numbers']+data['dialogue']}
targets = [('E028', 4.48, 4.54, 'six onset; source CTC s / final nominal CTC theta'),
           ('E028', 1.10, 1.16, 'within-same-utterance thousand theta control'),
           ('E039', 3.49, 3.55, 'seventeen onset; final nominal CTC omits s'),
           ('T013a', .71, .78, 'make final k before thirteen; final CTC omits k')]
results = []
for ident, start, end, reason in targets:
    src_path = source_manifest.parent / source[ident]['path']
    original = load(src_path)[round(start*24000):round(end*24000)]
    row = {'id': ident, 'start_s': start, 'end_s': end, 'reason': reason,
           'source': {'path': src_path.relative_to(ROOT).as_posix(), 'sha256': sha(src_path), 'features': feature(original)},
           'final_channels': []}
    for channel in ('left', 'right'):
        path = QA / channel / 'clips' / (ident+'.wav')
        current = load(path)[round(start*24000):round(end*24000)]
        correlation = statistics.correlation(original, current)
        row['final_channels'].append({'channel': channel, 'source_sha256': sha(path),
                                       'local_source_correlation': correlation, 'features': feature(current)})
    results.append(row)
report = {'kind': 'fresh-internal-phone-label-difference-signal-controls',
          'source_manifest_sha256': sha(source_manifest), 'results': results,
          'method': 'New fixed60/70ms waveform and spectrum measurements of source and each actual finished-AAC channel at the same local times. No text/neighbor context and no phoneme repair. Windows are diagnostic and not a universal fricative classifier.',
          'human_listening_claim': False,
          'interpretation': 'The physical source consonant regions remain in the AAC despite fallible CTC-label omission/substitution. This supports codec preservation; raw pronunciation/model warnings remain visible, and no perfect articulation claim is made.'}
with (QA / 'internal-phone-signal-controls.json').open('x') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
print([(row['id'], row['start_s'], min(ch['local_source_correlation'] for ch in row['final_channels'])) for row in results])
