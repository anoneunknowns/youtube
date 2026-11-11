"""Bind measured hexadecimal voices and produce the exact stereo narration master."""

from __future__ import annotations

import argparse
from array import array
from collections import Counter
import copy
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import wave

if __package__:
    from . import build_audio_mix as audio
    from .build_octal_episode import checked_wav, dialogue_key, event, local_path, mix, read, write
    from .prepare_hexadecimal_episode import (
        LETTER_GUIDES, OUTPUT as DESIGN, PAUSE_DURATIONS, PRONUNCIATIONS, SCRIPT,
        count_rows, estimate, numeric_clips, scripted_cues,
    )
    from .prepare_octal_episode import LIBRARY, ROOT, SAMPLE_RATE, frames, seconds
else:
    import build_audio_mix as audio
    from build_octal_episode import checked_wav, dialogue_key, event, local_path, mix, read, write
    from prepare_hexadecimal_episode import (
        LETTER_GUIDES, OUTPUT as DESIGN, PAUSE_DURATIONS, PRONUNCIATIONS, SCRIPT,
        count_rows, estimate, numeric_clips, scripted_cues,
    )
    from prepare_octal_episode import LIBRARY, ROOT, SAMPLE_RATE, frames, seconds


OUTPUT = ROOT / 'output/hexadecimal-counting-001-v001'
OCTAL = ROOT / 'output/octal-counting-001-v001'
SPLIT_EXAMPLE = {'I05A': 'This says', 'I05B': 'Its value is twenty-six.'}
LETTER_EQUIVALENTS = {
    'A': {'a', 'ay'}, 'B': {'b', 'be', 'bee'}, 'C': {'c', 'see', 'sea'},
    'D': {'d', 'dee'}, 'E': {'e', 'ee'}, 'F': {'f', 'ef', 'eff'},
}
NUMBER_EQUIVALENTS = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five',
    '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten', '11': 'eleven',
    '12': 'twelve', '13': 'thirteen', '14': 'fourteen', '15': 'fifteen', '16': 'sixteen',
    '26': 'twenty six',
}


def adopted_dialogue(expected: dict[str, str]) -> dict:
    manifest_path = LIBRARY / 'v002/measurements.json'
    manifest = read(manifest_path)
    acceptance_path = manifest_path.with_name('speech-acceptance.json')
    accepted = read(acceptance_path)
    if accepted['accepted'] is not True or accepted['inputs']['manifest']['sha256'] != audio.file_hash(manifest_path):
        raise ValueError('The previous dialogue library lacks matching acceptance')
    octal_measurements = OCTAL / 'speech/measurements.json'
    production = read(ROOT / 'design/octal-counting-v1/production-run-v001.json')
    if production['files'][local_path(octal_measurements)] != audio.file_hash(octal_measurements):
        raise ValueError('The previously completed octal voice manifest changed')
    octal = read(octal_measurements)
    adopted = {}
    for cue_id, text in expected.items():
        prior, = ([row for row in manifest['dialogue'] if row['spoken_text'] == text] or [None])
        if prior:
            approved, = (
                row for row in accepted['results']
                if row['role'] == 'dialogue' and row['expected_text'] == text and row['accepted'] is True
            )
            if any(prior[key] != approved[key] for key in ('path', 'sha256', 'duration_s', 'spoken_text')):
                raise ValueError(f'Previous dialogue approval differs for {cue_id}')
            path = manifest_path.parent / prior['path']
            record = {**prior, 'acceptance_record': local_path(acceptance_path),
                      'acceptance_record_sha256': audio.file_hash(acceptance_path)}
        else:
            prior, = ([row for row in octal['new_dialogue'].values() if row['text'] == text] or [None])
            if not prior:
                continue
            if prior['asr_status'] not in ('text-match', 'numeric-format-equivalent'):
                raise ValueError(f'Previous octal dialogue has unresolved review for {cue_id}')
            path = ROOT / prior['path']
            record = {**prior, 'previous_production_record': local_path(ROOT / 'design/octal-counting-v1/production-run-v001.json'),
                      'previous_measurements': local_path(octal_measurements)}
        count = checked_wav(path, record['sha256'], record['duration_s'], SAMPLE_RATE, 1)
        adopted[cue_id] = {
            **record, 'text': text, 'path': local_path(path), 'sample_frames': count,
            'duration_s': count / SAMPLE_RATE,
        }
    return adopted


def review_status(cue_id: str, candidate: dict, recognized: str) -> str:
    heard = dialogue_key(recognized)
    expected = dialogue_key(candidate['text'])
    if heard == expected:
        return 'text-match'
    if cue_id.startswith('LETTER-'):
        symbol = cue_id[-1]
        if heard in LETTER_EQUIVALENTS[symbol]:
            return 'letter-name-homophone'
        raise ValueError(f'Unresolved isolated letter {symbol}: {recognized}')
    spaced = re.sub(r'([0-9])([a-f])\b', r'\1 \2', heard)
    tokens = spaced.split()
    if re.fullmatch(r'I03[A-F]', cue_id) and tokens:
        symbol = cue_id[-1]
        if tokens[0] in LETTER_EQUIVALENTS[symbol]:
            tokens[0] = symbol.lower()
    normalized = ' '.join(NUMBER_EQUIVALENTS.get(token, token) for token in tokens)
    if normalized == expected:
        return 'number-or-letter-format-equivalent'
    raise ValueError(f'Unresolved dialogue transcription for {cue_id}: {recognized}')


def inherited_speech(timeline_path: Path | None, replacement_ids: set[str]) -> tuple[dict, dict | None]:
    if timeline_path is None:
        return {}, None
    timeline = read(timeline_path)
    manifest_path = ROOT / timeline['speech_measurements']['path']
    checksum = audio.file_hash(manifest_path)
    if checksum != timeline['speech_measurements']['sha256']:
        raise ValueError('Inherited speech manifest differs from its prior measured timeline')
    manifest = read(manifest_path)
    records = {
        **manifest['new_dialogue'],
        **{f'LETTER-{symbol}': manifest['symbol_clips'][symbol] for symbol in LETTER_GUIDES},
    }
    inherited = {}
    for cue_id, record in records.items():
        if cue_id in replacement_ids:
            continue
        if record['asr_status'] not in (
            'text-match', 'letter-name-homophone', 'number-or-letter-format-equivalent',
            'independent-acoustic-review-with-asr-warning',
        ):
            raise ValueError(f'Inherited cue has unresolved lexical review: {cue_id}')
        inherited[cue_id] = {
            **record,
            'review_inherited_from': {
                'timeline_path': local_path(timeline_path), 'timeline_sha256': audio.file_hash(timeline_path),
                'speech_measurements_path': local_path(manifest_path), 'speech_measurements_sha256': checksum,
            },
        }
    return inherited, manifest


def measured_candidates(
    candidates: list, reports: list[Path], expected: dict, staging: Path, final: Path, inherited: dict,
    independent_review: dict | None,
) -> dict:
    results = {}
    for report_path in reports:
        report = read(report_path)
        if (
            report['kind'] != 'independent-local-asr-review'
            or audio.file_hash(Path(report['source_manifest'])) != report['source_manifest_sha256']
        ):
            raise ValueError(f'ASR report has no matching source manifest: {report_path}')
        results.update((item['source_sha256'], item) for item in report['results'])
    by_id = {candidate['id']: candidate for candidate in candidates}
    if len(by_id) != len(candidates) or set(by_id) & set(inherited) or set(by_id) | set(inherited) != set(expected):
        raise ValueError('New and inherited speech IDs do not match the required hexadecimal cues')
    clips = {}
    for cue_id in expected:
        inherited_record = inherited.get(cue_id)
        candidate = inherited_record if inherited_record is not None else by_id[cue_id]
        original = Path(candidate['path'])
        if not original.is_absolute():
            original = ROOT / original
        if candidate['text'] != expected[cue_id]:
            raise ValueError(f'Speech text differs from the current cue {cue_id}')
        if inherited_record is None:
            row = results.get(candidate['sha256'])
            if row is None or row['expected_text'] != candidate['text'] or Path(row['path']).resolve() != original.resolve():
                raise ValueError(f'Fresh speech does not match reviewed cue {cue_id}')
            try:
                status = review_status(cue_id, candidate, row['recognized_text'])
            except ValueError:
                if (
                    independent_review is None or independent_review.get('accepted') is not True
                    or cue_id != f'LETTER-{independent_review.get("letter")}'
                    or independent_review.get('candidate_sha256') != candidate['sha256']
                ):
                    raise
                status = 'independent-acoustic-review-with-asr-warning'
            transcript = row['recognized_text']
        else:
            status, transcript = candidate['asr_status'], candidate['asr_transcript']
        count = checked_wav(original, candidate['sha256'], candidate['duration_s'], SAMPLE_RATE, 1)
        target = staging / f'{cue_id}.wav'
        with original.open('rb') as source, target.open('xb') as output:
            shutil.copyfileobj(source, output)
        clips[cue_id] = {
            'text': candidate['text'], 'path': local_path(final / target.name),
            'sha256': candidate['sha256'], 'sample_frames': count, 'duration_s': count / SAMPLE_RATE,
            'generation': {key: value for key, value in candidate['generation'].items() if key != 'status'},
            'trim': candidate['trim'], 'asr_status': status, 'asr_transcript': transcript,
        }
        if inherited_record is not None:
            clips[cue_id]['review_inherited_from'] = candidate['review_inherited_from']
        if 'phonemes' in candidate:
            clips[cue_id]['phonemes'] = candidate['phonemes']
        if 'extraction' in candidate:
            extraction = dict(candidate['extraction'])
            phrase = Path(extraction['source_path'])
            if not phrase.is_absolute():
                phrase = ROOT / phrase
            if audio.file_hash(phrase) != extraction['source_sha256']:
                raise ValueError(f'Extraction source changed for {cue_id}')
            phrase_target = staging / f'{cue_id}-source-phrase.wav'
            with phrase.open('rb') as source, phrase_target.open('xb') as output:
                shutil.copyfileobj(source, output)
            extraction['source_path'] = local_path(final / phrase_target.name)
            clips[cue_id]['extraction'] = extraction
        if 'processing' in candidate:
            processing = dict(candidate['processing'])
            raw_path = Path(processing['input_path'])
            if not raw_path.is_absolute():
                raw_path = ROOT / raw_path
            checked_wav(raw_path, processing['input_sha256'], candidate['duration_s'], SAMPLE_RATE, 1)
            with wave.open(str(raw_path), 'rb') as source:
                raw_samples = array('h', source.readframes(source.getnframes()))
            with wave.open(str(original), 'rb') as source:
                processed_samples = array('h', source.readframes(source.getnframes()))
            factor = 10 ** (processing['gain_db'] / 20)
            ceiling = processing['peak_ceiling_pcm16']
            reproduced = array('h', (
                max(-ceiling, min(ceiling, round(value * factor))) for value in raw_samples
            ))
            capped = [index for index, value in enumerate(raw_samples) if abs(round(value * factor)) > ceiling]
            if reproduced != processed_samples or capped != processing['peak_capped_sample_indices']:
                raise ValueError(f'Derived speech does not match its registered processing for {cue_id}')
            raw_target = staging / f'{cue_id}-processing-input.wav'
            with raw_path.open('rb') as source, raw_target.open('xb') as target:
                shutil.copyfileobj(source, target)
            processing['input_path'] = local_path(final / raw_target.name)
            clips[cue_id]['processing'] = processing
    return clips


def count_schedule(plan: dict, symbols: dict) -> tuple[dict, list]:
    plan = copy.deepcopy(plan)
    cursor = frames(plan['intro']['duration_s'])
    previous_end = None
    states, carries, pauses, events = [], [], [], []
    pause_dialogue = {pause['after_decimal_value']: pause for pause in plan['pauses']}
    sfx = []
    for row in count_rows():
        value, start = row['decimal_value'], cursor
        cursor += frames(.12)
        if previous_end is not None:
            if cursor - previous_end != frames(2 + PAUSE_DURATIONS.get(value - 1, 0)):
                raise ValueError(f'Count gap differs before decimal {value}')
            if value % 16 == 0:
                carries.append({
                    'after_decimal_value': value - 1, 'before_decimal_value': value,
                    'from_hexadecimal': format(value - 1, 'X'), 'to_hexadecimal': row['display_hexadecimal'],
                    'estimated_start_s': seconds(max(previous_end + frames(.015), start - frames(.45))),
                    'estimated_end_s': seconds(start + frames(.10)), 'spoken': False,
                })
        highlights = []
        for ordinal, symbol in enumerate(row['display_hexadecimal']):
            if ordinal:
                cursor += frames(.90)
            token = row['spoken_tokens'][ordinal]
            item = event(symbols[symbol], f'D{value:03d}-{ordinal+1}', 'digit_voice', 'count', cursor, token,
                         token=token, symbol=symbol, pronunciation_guide=PRONUNCIATIONS[symbol],
                         decimal_value=value, slot_index=row['active_slot_indices'][ordinal])
            events.append(item)
            cursor = item['end_sample_24k']
            highlights.append({
                'symbol': symbol, 'token': token, 'pronunciation_guide': PRONUNCIATIONS[symbol],
                'ordinal': ordinal, 'slot_index': row['active_slot_indices'][ordinal],
                'duration_measured': True, 'estimated_start_s': item['start_s'], 'estimated_end_s': item['end_s'],
            })
        previous_end = cursor
        cursor += frames(.28 if value == 127 else 1.88)
        if value in pause_dialogue:
            pause = {**pause_dialogue[value], 'estimated_start_s': seconds(cursor)}
            pauses.append(pause)
            cursor += frames(pause['duration_s'])
        states.append({
            'decimal_value': value, 'display_hexadecimal': row['display_hexadecimal'],
            'estimated_display_start_s': seconds(start), 'estimated_speech_end_s': seconds(previous_end),
            'estimated_display_end_s': seconds(cursor), 'digit_highlights': highlights,
        })
        if value == 16:
            original = next(cue for cue in plan['sfx_events'] if cue['id'] == 'SE_PLACE')
            sfx.append({**original, 'estimated_start_s': seconds(start + frames(.01)),
                        'estimated_end_s': seconds(start + frames(.09))})
    finale_start = cursor
    cursor += frames(plan['finale']['duration_s'])
    original = next(cue for cue in plan['sfx_events'] if cue['id'] == 'SE_FINISH')
    sfx.append({**original, 'estimated_start_s': seconds(finale_start + frames(.08)),
                'estimated_end_s': seconds(finale_start + frames(1.08))})
    plan.update(
        kind='measured-hexadecimal-counting-timeline', status='measured-audio',
        measurement_status='all-symbol-dialogue-and-sfx-clips-measured', audio_generated=True,
        duration_s=seconds(cursor), fps=30, master_sample_rate_hz=48000, master_channels=2,
        counted_states=states, pauses=pauses, carry_cues=carries, sfx_events=sfx,
    )
    plan['finale']['estimated_start_s'] = seconds(finale_start)
    for symbol in LETTER_GUIDES:
        plan['letter_voice_estimates'][symbol].update(
            measured=True, audio_generated=True, measured_duration_s=symbols[symbol]['duration_s'],
        )
    return plan, events


def dialogue_schedule(plan: dict, symbols: dict, dialogue: dict, events: list) -> dict:
    sections = [('intro', 0, plan['intro']['dialogue'])]
    sections += [('pause', p['estimated_start_s'], p['dialogue']) for p in plan['pauses']]
    sections += [('finale', plan['finale']['estimated_start_s'], plan['finale']['dialogue'])]
    for phase, origin, cues in sections:
        for cue in cues:
            cue_id = cue['id']
            start, limit = (frames(origin) + frames(value) for value in cue['relative_window_s'])
            if cue_id == 'I05':
                first = event(dialogue['I05A'], 'I05A', 'dialogue', phase, start + frames(.035), SPLIT_EXAMPLE['I05A'])
                one = event(symbols['1'], 'I05-ONE', 'digit_voice', phase,
                            first['end_sample_24k'] + frames(.06), 'one',
                            token='one', symbol='1', decimal_value=26, slot_index=0, cue_id_parent='I05')
                letter = event(symbols['A'], 'I05-A', 'digit_voice', phase,
                               one['end_sample_24k'] + frames(.90), 'A',
                               token='A', symbol='A', decimal_value=26, slot_index=1, cue_id_parent='I05')
                last = event(dialogue['I05B'], 'I05B', 'dialogue', phase,
                             letter['end_sample_24k'] + frames(.14), SPLIT_EXAMPLE['I05B'])
                if last['end_sample_24k'] > limit:
                    raise ValueError('Measured I05 example exceeds its editing window')
                events.extend((first, one, letter, last))
                plan['intro']['example_reading'].update(measured=True, digit_event_ids=['I05-ONE', 'I05-A'])
            else:
                extra = {'letter_mapping_symbol': cue_id[-1]} if re.fullmatch(r'I03[A-F]', cue_id) else {}
                item = event(dialogue[cue_id], cue_id, 'dialogue', phase, start, cue['text'], **extra)
                if item['end_sample_24k'] > limit:
                    raise ValueError(f'Fresh dialogue exceeds the editing window for {cue_id}')
                events.append(item)
    for sound in plan['sfx_events']:
        path = ROOT / sound['path']
        record, = (row for row in read(path.with_name('generation-spec.json'))['assets'] if row['id'] == sound['id'])
        count = checked_wav(path, record['sha256'], record['duration_s'], 48000, 2)
        if count % 2:
            raise ValueError('Sound effect does not fit the timing grid')
        source = {'path': sound['path'], 'sha256': record['sha256'], 'sample_frames': count // 2}
        phase, cue_id = ('count', 'SE_PLACE-016') if sound['id'] == 'SE_PLACE' else ('finale', 'SE_FINISH')
        item = event(source, cue_id, 'sfx', phase, frames(sound['estimated_start_s']), sound['id'])
        if item['end_s'] != sound['estimated_end_s']:
            raise ValueError('Sound effect length differs from the schedule')
        events.append(item)
    events.sort(key=lambda item: item['start_sample_24k'])
    if Counter(item['type'] for item in events) != {'digit_voice': 242, 'dialogue': 21, 'sfx': 2}:
        raise ValueError('Unexpected hexadecimal audio event counts')
    if len({item['id'] for item in events}) != len(events):
        raise ValueError('Duplicate audio cue ID')
    if any(a['end_sample_24k'] > b['start_sample_24k'] for a, b in zip(events, events[1:])):
        raise ValueError('Hexadecimal audio cues overlap')
    if events[0]['start_sample_24k'] < 0 or events[-1]['end_sample_24k'] > frames(plan['duration_s']):
        raise ValueError('Hexadecimal audio exceeds the episode schedule')
    plan['events'] = events
    return plan


def mix_balanced(plan: dict, master: Path, work: Path, ffmpeg: str, staged: dict) -> dict:
    """Use only linear source gains before the shared peak-safe mastering pass."""
    render_plan = copy.deepcopy(plan)
    source_paths = dict(staged)
    replacements, gains = {}, {}
    quiet_symbols = {plan['measured_symbol_clips'][symbol]['sha256'] for symbol in ('6', 'A', 'E')}
    for cue in plan['events']:
        original_hash = cue['source_sha256']
        if cue['type'] == 'sfx' or original_hash in replacements:
            continue
        path = staged.get(original_hash, ROOT / cue['source_path'])
        if audio.file_hash(path) != original_hash:
            raise ValueError(f'Source changed before speech balancing: {path}')
        with wave.open(str(path), 'rb') as source:
            if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (SAMPLE_RATE, 1, 2):
                raise ValueError(f'Unexpected speech format during linear balancing: {path}')
            samples = array('h', source.readframes(source.getnframes()))
        peak = max(map(abs, samples))
        rms = math.sqrt(sum(value * value for value in samples) / len(samples))
        peak_db = 20 * math.log10(peak / 32768)
        rms_db = 20 * math.log10(rms / 32768)
        desired = max(0, -20.5 - rms_db) if original_hash in quiet_symbols else 0
        gain_db = min(desired, -4.5 - peak_db)
        gain = 10 ** (gain_db / 20)
        transformed = path
        transformed_hash = original_hash
        if abs(gain_db) > 1e-9:
            transformed = work / f'balanced-{original_hash}.wav'
            adjusted = array('h', (round(value * gain) for value in samples))
            with wave.open(str(transformed), 'wb') as output:
                output.setparams((1, 2, SAMPLE_RATE, 0, 'NONE', 'not compressed'))
                output.writeframes(adjusted.tobytes())
            transformed_hash = audio.file_hash(transformed)
        replacements[original_hash] = transformed_hash
        source_paths[transformed_hash] = transformed
        gains[original_hash] = {
            'source_path': cue['source_path'], 'gain_db': gain_db,
            'raw_peak_before_dbfs': peak_db, 'raw_rms_before_dbfs': rms_db,
            'raw_peak_after_dbfs': peak_db + gain_db, 'raw_rms_after_dbfs': rms_db + gain_db,
        }
    for cue in render_plan['events']:
        if cue['type'] != 'sfx':
            cue['source_sha256'] = replacements[cue['source_sha256']]
    receipt = mix(render_plan, master, work, ffmpeg, source_paths)
    if not -17 <= receipt['loudness_lufs'] <= -15 or receipt['true_peak_dbtp'] > -1.95:
        raise ValueError('Balanced master does not meet the hexadecimal loudness and peak targets')
    receipt['speech_balancing'] = {
        'method': 'Uniform linear gain per unique speech source; source WAVs and all timing are preserved.',
        'raw_speech_peak_cap_dbfs': -4.5, 'quiet_symbol_target_rms_dbfs': -20.5,
        'quiet_symbols': ['6', 'A', 'E'],
        'sources': gains,
    }
    return receipt


def build(
    output: Path, work_root: Path, candidates: list, reports: list[Path], phoneme_reports: list[Path],
    independent_review: Path | None = None,
    inherit_timeline: Path | None = None,
    publish_schedule_first: bool = False,
    additional_evidence: list[Path] | None = None,
) -> dict:
    if any((output / name).exists() for name in ('speech', 'timeline.json', 'master.wav', 'audio-qa.json')):
        raise ValueError('Choose an output location without an existing hexadecimal audio build')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('Registered FFmpeg is required')
    numerals, cues = numeric_clips(), scripted_cues()
    original = read(DESIGN / 'estimated-timeline.json')
    if original != estimate(count_rows(), numerals, cues):
        raise ValueError('Stored hexadecimal estimate differs from the current script')
    expected = {key: cue[1] for key, cue in cues.items() if key != 'I05'}
    expected.update(SPLIT_EXAMPLE)
    adopted = adopted_dialogue(expected)
    fresh_expected = {key: text for key, text in expected.items() if key not in adopted}
    fresh_expected.update({f'LETTER-{symbol}': symbol for symbol in LETTER_GUIDES})
    inherited, previous_manifest = inherited_speech(inherit_timeline, {item['id'] for item in candidates})
    destination = output / 'speech'
    with tempfile.TemporaryDirectory(prefix='hexadecimal-master-', dir=work_root) as work:
        work = Path(work)
        staging = work / 'speech'
        staging.mkdir()
        independent = read(independent_review) if independent_review is not None else None
        fresh = measured_candidates(
            candidates, reports, fresh_expected, staging, destination, inherited, independent,
        )
        symbols = {**numerals, **{symbol: fresh[f'LETTER-{symbol}'] for symbol in LETTER_GUIDES}}
        dialogue = {**adopted, **{key: clip for key, clip in fresh.items() if not key.startswith('LETTER-')}}
        plan, events = count_schedule(original, symbols)
        plan = dialogue_schedule(plan, symbols, dialogue, events)
        plan['measured_symbol_clips'] = symbols
        frequencies = Counter(symbol for row in count_rows() for symbol in row['display_hexadecimal'])
        plan['timing']['measured_symbol_clip_duration_s_total'] = seconds(
            sum(symbols[symbol]['sample_frames'] * count for symbol, count in frequencies.items())
        )
        staged_clips = {clip['sha256']: staging / f'{cue_id}.wav' for cue_id, clip in fresh.items()}
        master = work / 'master.wav'
        acoustic_records = []
        inherited_review = {}
        evidence_records = []
        if previous_manifest is not None:
            previous_review = previous_manifest['review']
            for record in previous_review.get('independent_acoustic_reports', []):
                source = ROOT / record['path']
                if audio.file_hash(source) != record['sha256']:
                    raise ValueError('Inherited acoustic proof has changed')
                target = staging / f'phoneme-review-{len(acoustic_records)+1:02d}.json'
                with source.open('rb') as original_report, target.open('xb') as copied_report:
                    shutil.copyfileobj(original_report, copied_report)
                acoustic_records.append({**record, 'path': local_path(destination / target.name)})
            for symbol in LETTER_GUIDES:
                key = f'independent_{symbol}_review'
                if key not in previous_review or f'LETTER-{symbol}' not in inherited:
                    continue
                record = previous_review[key]
                source = ROOT / record['path']
                if audio.file_hash(source) != record['sha256']:
                    raise ValueError(f'Inherited independent {symbol} proof has changed')
                target = staging / f'independent-{symbol}-review.json'
                with source.open('rb') as original_report, target.open('xb') as copied_report:
                    shutil.copyfileobj(original_report, copied_report)
                inherited_review[key] = {**record, 'path': local_path(destination / target.name)}
                proof = read(source)
                diagnostic_record = proof.get('lpc_comparison', {})
                if 'source_report_sha256' in diagnostic_record:
                    diagnostic = source.parent / Path(diagnostic_record['source_report_path']).name
                    if audio.file_hash(diagnostic) != diagnostic_record['source_report_sha256']:
                        raise ValueError('Inherited spectral evidence has changed')
                    diagnostic_target = staging / f'inherited-{diagnostic.name}'
                    with diagnostic.open('rb') as origin, diagnostic_target.open('xb') as copied:
                        shutil.copyfileobj(origin, copied)
                    evidence_records.append({
                        'path': local_path(destination / diagnostic_target.name), 'sha256': audio.file_hash(diagnostic_target),
                    })
        for source in phoneme_reports:
            report = read(source)
            if report['kind'] != 'isolated-phoneme-asr':
                raise ValueError(f'Unexpected independent acoustic report {source}')
            for row in report['results']:
                if audio.file_hash(Path(row['source_path'])) != row['source_sha256']:
                    raise ValueError(f'Acoustic report source has changed: {row["source_path"]}')
            target = staging / f'phoneme-review-{len(acoustic_records)+1:02d}.json'
            with source.open('rb') as original_report, target.open('xb') as copied_report:
                shutil.copyfileobj(original_report, copied_report)
            acoustic_records.append({
                'path': local_path(destination / target.name), 'sha256': audio.file_hash(target),
                'model': report['model'], 'method': report['method'],
            })
        for index, source in enumerate(additional_evidence or [], 1):
            target = staging / f'evidence-{index:02d}-{source.name}'
            with source.open('rb') as origin, target.open('xb') as copied:
                shutil.copyfileobj(origin, copied)
            evidence_records.append({
                'path': local_path(destination / target.name), 'sha256': audio.file_hash(target),
            })
        measurements = {
            'schema_version': 1, 'measurement_status': 'measured',
            'symbol_clips': symbols, 'reused_dialogue': adopted, 'new_dialogue': {
                key: value for key, value in fresh.items() if not key.startswith('LETTER-')
            },
            'review': {
                'method': 'Offline isolated Whisper tiny.en q8 without expected text prompts; '
                          'hash-bound comparison accepts documented letter-name homophones and numeral formatting. '
                          'Bound independent acoustic review can resolve a recorded isolated ASR warning.',
                'human_listening_performed': False,
                'letter_name_homophones': {key: sorted(value) for key, value in LETTER_EQUIVALENTS.items()},
                'source_reports_sha256': [audio.file_hash(path) for path in reports],
                'statuses': dict(Counter(clip['asr_status'] for clip in fresh.values())),
                'independent_acoustic_reports': acoustic_records,
                'additional_evidence': evidence_records,
                'selected_E_review': {
                    'source': 'Natural phrase vowel extracted without time stretching',
                    'isolated_whisper': 'E.',
                    'phoneme_context': 'iː before the independently recognized phrase tail',
                    'rejected_initial_E': 'The initial E waveform was recognized as eɪ in the same context fixture',
                    'isolated_CTC_warning_retained_in_report': True,
                },
                **inherited_review,
            },
        }
        if inherit_timeline is not None:
            measurements['review']['inheritance'] = {
                'prior_timeline': local_path(inherit_timeline), 'prior_timeline_sha256': audio.file_hash(inherit_timeline),
                'inherited_clip_count': len(inherited), 'replacement_clip_ids': [item['id'] for item in candidates],
            }
        if independent_review is not None:
            reviewed_symbol = independent.get('letter', 'E')
            if (
                independent['kind'] != 'independent-extracted-letter-acoustic-review'
                or independent['candidate_sha256'] != symbols[reviewed_symbol]['sha256']
                or audio.file_hash(Path(independent['candidate_path'])) != symbols[reviewed_symbol]['sha256']
            ):
                raise ValueError(f'Independent acoustic review does not match selected {reviewed_symbol}')
            review_copy = staging / f'independent-{reviewed_symbol}-review.json'
            with independent_review.open('rb') as source, review_copy.open('xb') as target:
                shutil.copyfileobj(source, target)
            measurements['review'][f'independent_{reviewed_symbol}_review'] = {
                'path': local_path(destination / review_copy.name), 'sha256': audio.file_hash(review_copy),
            }
        speech_manifest = staging / 'measurements.json'
        write(speech_manifest, measurements)
        plan['speech_measurements'] = {
            'path': local_path(destination / speech_manifest.name), 'sha256': audio.file_hash(speech_manifest),
        }
        timeline = work / 'timeline.json'
        write(timeline, plan)
        if publish_schedule_first:
            output.mkdir(parents=True, exist_ok=True)
            staging.rename(destination)
            timeline.rename(output / timeline.name)
            speech_manifest = destination / speech_manifest.name
            timeline = output / timeline.name
            staged_clips = {}
            print(json.dumps({
                'schedule_ready': local_path(timeline), 'timeline_sha256': audio.file_hash(timeline),
                'duration_s': plan['duration_s'], 'audio_master_pending': True,
            }), flush=True)
        receipt = mix_balanced(plan, master, work, ffmpeg, staged_clips)
        receipt.update(
            kind='hexadecimal-audio-master-qa', schema_version=1, timeline_sha256=audio.file_hash(timeline),
            speech_measurements_sha256=audio.file_hash(speech_manifest),
        )
        qa = work / 'audio-qa.json'
        write(qa, receipt)
        output.mkdir(parents=True, exist_ok=True)
        publish = (master, qa) if publish_schedule_first else (staging, master, qa, timeline)
        for path in publish:
            path.rename(output / path.name)
    return receipt


def rebalance_from_timeline(timeline_path: Path, output: Path, work_root: Path) -> dict:
    if any((output / name).exists() for name in ('master.wav', 'audio-qa.json')):
        raise ValueError('Choose a fresh output location for reproduced audio')
    plan = read(timeline_path)
    manifest = ROOT / plan['speech_measurements']['path']
    if audio.file_hash(manifest) != plan['speech_measurements']['sha256']:
        raise ValueError('The measured speech manifest has changed')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('Registered FFmpeg is required')
    with tempfile.TemporaryDirectory(prefix='hexadecimal-audio-rebuild-', dir=work_root) as work:
        work = Path(work)
        master = work / 'master.wav'
        receipt = mix_balanced(plan, master, work, ffmpeg, {})
        receipt.update(
            kind='hexadecimal-audio-master-qa', schema_version=1,
            timeline_path=local_path(timeline_path), timeline_sha256=audio.file_hash(timeline_path),
            speech_measurements_sha256=audio.file_hash(manifest),
        )
        qa = work / 'audio-qa.json'
        write(qa, receipt)
        output.mkdir(parents=True, exist_ok=True)
        master.rename(output / master.name)
        qa.rename(output / qa.name)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--takes', type=Path)
    parser.add_argument('--asr', action='append', type=Path, default=[])
    parser.add_argument('--phonemes', action='append', type=Path, default=[])
    parser.add_argument('--independent-review', type=Path)
    parser.add_argument('--inherit-timeline', type=Path)
    parser.add_argument('--publish-schedule-first', action='store_true')
    parser.add_argument('--evidence', action='append', type=Path, default=[])
    parser.add_argument('--rebalance-timeline', type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--out', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.rebalance_timeline is not None:
        if (
            args.takes is not None or args.asr or args.phonemes or args.independent_review is not None
            or args.inherit_timeline is not None or args.publish_schedule_first
            or args.evidence
        ):
            parser.error('--rebalance-timeline uses the recorded speech references in that timeline')
        receipt = rebalance_from_timeline(
            args.rebalance_timeline.resolve(), args.out.resolve(), args.work_dir.resolve(),
        )
    else:
        if args.takes is None or not args.asr:
            parser.error('A fresh speech build requires --takes and --asr')
        receipt = build(
            args.out.resolve(), args.work_dir.resolve(), read(args.takes), args.asr, args.phonemes,
            args.independent_review,
            args.inherit_timeline,
            args.publish_schedule_first,
            args.evidence,
        )
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
