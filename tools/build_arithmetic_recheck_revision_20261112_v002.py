"""Preserve the accepted arithmetic master and replace only the reviewed O003.

The visual candidate is remuxed without video re-encoding. All original media,
manifests and QA remain immutable. This tool requires the new padded source's
separate acoustic acceptance; it does not certify pronunciation itself.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import wave
from array import array

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/arithmetic-sequence-counting-001-v001'
FF = ROOT / '.venv/bin/ffmpeg'

def read(p): return json.loads(Path(p).read_text())
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def rel(p): return str(Path(p).resolve().relative_to(ROOT))
def ref(p): return {'path': rel(p), 'sha256': sha(p), 'bytes': Path(p).stat().st_size}
def save(p, value):
    with Path(p).open('x') as f: json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')
def require(ok, message):
    if not ok: raise ValueError(message)
def source_path(row): return Path(row['path']) if Path(row['path']).is_absolute() else ROOT / row['path']
def decode(p):
    values = array('f')
    values.frombytes(subprocess.check_output([str(FF), '-v', 'error', '-i', str(p), '-ar', '48000', '-ac', '2', '-f', 'f32le', 'pipe:1']))
    return values
def rms(values): return math.sqrt(sum(v*v for v in values)/len(values))
def probe(p):
    result = subprocess.run([str(FF), '-hide_banner', '-i', str(p), '-af', 'loudnorm=I=-16:TP=-2:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True, check=True)
    return json.loads(re.findall(r'\{\s*"input_i"[\s\S]*?\}', result.stderr)[-1])

def build(args):
    timeline = OUT / 'audio-build/timeline.json'; old = read(timeline)
    before = {e['id']: e for e in old['voice_events']}; event = before['O003']
    new_source = args.source.resolve(); proof = read(args.source_proof)
    require(proof.get('accepted') is True and not proof.get('unresolved'), 'New source needs explicit acceptance')
    proof_source = proof.get('padded_source', proof.get('source', {}))
    require(proof_source.get('sha256') == sha(new_source), 'Acoustic acceptance belongs to another source')
    ctc = read(args.source_ctc)
    require(len(ctc['results']) == 1, 'Require the selected source CTC, not a candidate collection')
    source_ctc = ctc['results'][0]
    require(source_ctc['source_sha256'] == sha(new_source), 'Selected source CTC hash differs')
    with wave.open(str(new_source)) as w:
        require((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, event['sample_frames_24k']), 'Preserve the exact O003 slot; padding must be separately reviewed')
        samples = array('h'); samples.frombytes(w.readframes(w.getnframes()))
    revision = args.audio_out.resolve(); require(not revision.exists(), 'Use a fresh audio revision directory'); revision.mkdir(parents=True)
    old_manifest_path = ROOT / old['speech_manifest']['path']; manifest = read(old_manifest_path)
    row = next(r for r in manifest['dialogue'] if r['id'] == 'O003')
    row.update(path=str(new_source), sha256=sha(new_source), raw_source=ref(new_source),
               raw_source_id='O003-selected-padded', origin='new-generated-punctuation-clarified-whole-dialogue',
               raw_sample_range_24k=None, extraction_method='Whole selected WAV, byte-identical; appended pure-silence padding and unpadded generated original are bound by the source-specific review.',
               generation_review=ref(args.source_proof))
    manifest['supersedes_manifest'] = ref(old_manifest_path)
    manifest['source_specific_revision'] = ref(args.source_proof)
    manifest_path = revision / 'measurements.json'; save(manifest_path, manifest)
    old_gate_path = ROOT / old['speech_gate']['path']; old_gate = read(old_gate_path)
    gate = copy.deepcopy(old_gate); gate['kind'] = 'hash-bound-arithmetic-recheck-revision-source-acceptance'
    gate.update(accepted_at_utc=datetime.now(timezone.utc).isoformat(), source_manifest_sha256=sha(manifest_path),
                previous_acceptance=ref(old_gate_path), revision_source_acceptance=ref(args.source_proof))
    gate['inputs']['revision_source_acceptance'] = ref(args.source_proof)
    target = next(r for r in gate['results'] if r['id'] == 'O003')
    target.update(source_path=rel(new_source), source_sha256=sha(new_source), accepted=True, failures=[],
                  decision='Fresh reviewed punctuation-clarified source; prior O003 acceptance preserved separately',
                  notes=['See revision_source_acceptance for fresh lexical/CTC, guard, roundtrip, padding and signal evidence.'],
                  recognized_phonemes=source_ctc['recognized_phonemes'], asr_status='see-fresh-source-specific-review')
    for key in ('asr_transcript', 'phoneme_differences', 'phoneme_comparison_not_acceptance_score', 'waveform'):
        target.pop(key, None)
    gate['raw_asr_warning_resolutions']['O003'] = 'Replaced by a newly generated, independently reviewed source; the prior guard-sensitive source and its previous approval are unchanged historical evidence.'
    gate['scope'] = '214 byte-identical previously accepted sources plus one fresh hash-bound O003 decision. Final AAC has a separate gate.'
    gate_path = revision / 'speech-acceptance.json'; save(gate_path, gate)
    old_ctc_path = ROOT / old['source_phonemes']['path']; phonemes = read(old_ctc_path)
    phonemes['results'] = [dict(source_ctc, id='O003') if r['id'] == 'O003' else r for r in phonemes['results']]
    phonemes['source_manifest_sha256'] = sha(manifest_path)
    phonemes['revision_provenance'] = {'unchanged_214': ref(old_ctc_path), 'fresh_O003': ref(args.source_ctc)}
    ctc_path = revision / 'source-phonemes.json'; save(ctc_path, phonemes)
    old_master = ROOT / old['master_audio']['path']; original = decode(old_master)
    lo = event['start_sample_24k'] * 2; hi = event['end_sample_24k'] * 2
    replacement = decode(new_source); require(len(replacement) == 2*(hi-lo), 'Resampling changed slot length')
    target_rms = rms(original[lo*2:hi*2]); raw_rms = rms(replacement)
    # Measure the same stereo conversion that is actually written. FFmpeg's
    # mono-to-stereo conversion attenuates each channel by about 3 dB.
    resampled = revision / 'O003-resampled-raw48k.wav'
    subprocess.run([str(FF), '-v', 'error', '-i', str(new_source), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s24le', str(resampled)], check=True)
    raw_probe = probe(resampled)
    gain = min(20*math.log10(target_rms/raw_rms), -2.15-float(raw_probe['input_tp']))
    normalized = revision / 'O003-master-level48k.wav'
    subprocess.run([str(FF), '-v', 'error', '-i', str(new_source), '-af', f'volume={gain:.12f}dB:precision=double', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s24le', str(normalized)], check=True)
    with wave.open(str(old_master)) as w:
        params = w.getparams(); original_pcm = w.readframes(w.getnframes())
    with wave.open(str(normalized)) as w:
        require((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (2, 3, 48000, hi-lo), 'Replacement shape changed')
        pcm = w.readframes(w.getnframes())
    data = bytearray(original_pcm); data[lo*6:hi*6] = pcm
    require(data[:lo*6] == original_pcm[:lo*6] and data[hi*6:] == original_pcm[hi*6:], 'Unrelated master PCM changed')
    master = revision / 'master.wav'
    with wave.open(str(master), 'wb') as w: w.setparams(params); w.writeframes(data)
    require(float(probe(normalized)['input_tp']) <= -2.10, 'New source true peak exceeds target')
    revised = copy.deepcopy(old); revised['revision_id'] = 'arithmetic-sequence-counting-v002-recheck'
    source_fields = {k: row[k] for k in ('path', 'sha256', 'raw_source', 'raw_source_id', 'origin', 'extraction_method', 'generation_review')}
    for group in ('events', 'voice_events'):
        e = next(e for e in revised[group] if e['id'] == 'O003')
        e.update(source_fields, source_path=rel(new_source), source_sha256=sha(new_source),
                 source_peak_dbfs=20*math.log10(max(map(abs,samples))/32768),
                 source_rms_dbfs=20*math.log10(rms(samples)/32768),
                 mix_gain_db=gain, master_gain_db=0, per_source_truepeak_calibration_db=0,
                 aac_codec_calibration_gain_db=0, revision_constant_source_to_master_gain_db=gain)
    revised.update(speech_manifest=ref(manifest_path), speech_gate=ref(gate_path), source_phonemes=ref(ctc_path))
    revised['master_audio'] = {**ref(master), 'sample_rate_hz': 48000, 'channels': 2, 'sample_width_bits': 24,
        'duration_s': old['duration_s'], 'method': 'Exact original 48k24bit PCM outside the O003 slot; one constant scalar and the original FFmpeg resampler for the new padded whole source.',
        'previous_master': ref(old_master), 'changed_cue': 'O003', 'source_to_master_gain_db': gain}
    revised_path = revision / 'timeline.json'; save(revised_path, revised)
    receipt = {'status': 'pass', 'previous_timeline': ref(timeline), 'timeline': ref(revised_path),
        'previous_master': ref(old_master), 'master': ref(master), 'new_source': ref(new_source),
        'source_acceptance': ref(args.source_proof), 'source_ctc': ref(args.source_ctc),
        'constant_source_to_master_gain_db': gain, 'target_previous_cue_rms_dbfs': 20*math.log10(target_rms),
        'normalized_cue_probe': probe(normalized), 'master_probe': probe(master),
        'raw_converted_stereo_probe': raw_probe, 'normalized_cue_rms_dbfs': 20*math.log10(rms(decode(normalized))),
        'changed_48k_stereo_pcm_frame_interval': [lo, hi], 'unchanged_pcm_before_and_after': True,
        'unchanged_214_source_sha256': True, 'unchanged_every_event_text_and_time': True,
        'sample_rate': 48000, 'no_time_stretch': True, 'no_source_audio_sample_trim': True,
        'pure_silence_padding_proof': ref(args.source_proof), 'tool': ref(Path(__file__))}
    for a, b in zip(old['voice_events'], revised['voice_events']):
        require(all(a[k] == b[k] for k in ('id', 'text', 'spoken_text', 'subtitle_text', 'start_s', 'end_s', 'duration_s')), 'Text or timing changed')
        if a['id'] != 'O003': require(a == b, 'Unrelated source or metadata changed')
    require(old['counted_states'] == revised['counted_states'], 'Counting state changed')
    save(revision / 'revision-receipt.json', receipt)
    destination = args.render_out.resolve(); require(not destination.exists(), 'Use a fresh render revision directory'); destination.mkdir(parents=True)
    video = destination / args.visual_candidate.name
    subprocess.run([str(FF), '-hide_banner', '-v', 'warning', '-i', str(args.visual_candidate), '-i', str(master),
        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        '-af', f'apad=whole_dur={old["duration_frames"]/30:.9f}', '-t', f'{old["duration_frames"]/30:.9f}', '-movflags', '+faststart', str(video)], check=True)
    for name in ('frame-plan.json.gz', 'character-motion.json', 'scene-plan.json'):
        p = args.visual_candidate.parent / name
        if p.exists(): shutil.copyfile(p, destination / name)
    save(destination / 'revision-remux.json', {'status': 'candidate-awaiting-final-QA', 'video': ref(video),
        'copied_video_candidate': ref(args.visual_candidate), 'new_audio_timeline': ref(revised_path),
        'audio_revision_receipt': ref(revision / 'revision-receipt.json'),
        'original_native_render_report': ref(args.visual_candidate.parent / 'native-layout-verification.json'),
        'explicit_corrected_motion': ref(args.motion), 'video_reencoded': False, 'old_media_preserved': True})
    print(json.dumps({'video': ref(video), 'timeline': ref(revised_path), 'master': ref(master)}))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'source-proof', 'source-ctc', 'visual-candidate', 'audio-out', 'render-out', 'motion'):
        p.add_argument('--'+name, type=Path, required=True)
    build(p.parse_args())
