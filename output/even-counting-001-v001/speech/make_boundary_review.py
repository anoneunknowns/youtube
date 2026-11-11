"""Read-only waveform review around make / three in I04."""
import array
import hashlib
import json
from pathlib import Path
import sys
import wave

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from verify_terminal_tails import frame_metrics

source = OUT / 'candidates-v001/I04.wav'
with wave.open(str(source), 'rb') as stream:
    rate = stream.getframerate()
    samples = [v / 32768 for v in array.array('h', stream.readframes(stream.getnframes()))]
frames = []
for tick in range(72, 103):
    time = tick / 100
    center = round(time * rate)
    metrics = frame_metrics(samples[center - 240:center + 240], rate)
    frames.append({'time_s': time, **{k: round(v, 5) for k, v in metrics.items()}})
report = {'schema_version': 1, 'kind': 'isolated-acoustic-analysis',
          'id': 'I04', 'source_path': str(source),
          'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'method': 'Unmodified mono PCM24kHz; 20ms windows,10ms hop around make-three boundary. Diagnostic RMS/periodicity/spectral ratios; no text fed to acoustic processing.',
          'frames': frames}
with (OUT / 'make-boundary-signal.json').open('x', encoding='utf-8') as output:
    json.dump(report, output, indent=2)
    output.write('\n')
for row in frames:
    print(row['time_s'], row['rms_dbfs'], row['periodicity'], row['high_ratio_2khz_up'])
