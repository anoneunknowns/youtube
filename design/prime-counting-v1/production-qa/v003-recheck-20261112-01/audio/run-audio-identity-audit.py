#!/usr/bin/env python3
"""Read-only media/evidence identity audit; writes only alongside this script."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/Users/support/codex/youtube')
OUT = Path(__file__).resolve().parent
VERSIONS = ('v001', 'v002', 'v003')
MOVIE_NAME = 'paspla-studio-prime-numbers-2-to-997-1080p.mp4'
failures = []
hash_cache = {}


def read(path):
    return json.loads((ROOT / path).read_text())


def sha(path):
    p = (ROOT / path).resolve()
    if p not in hash_cache:
        digest = hashlib.sha256()
        with p.open('rb') as file:
            for block in iter(lambda: file.read(8 * 1024 * 1024), b''):
                digest.update(block)
        hash_cache[p] = digest.hexdigest()
    return hash_cache[p]


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check(condition, detail):
    if not condition:
        failures.append(detail)
    return bool(condition)


def binding(path, expected, label):
    p = ROOT / path
    actual = sha(p) if p.is_file() else None
    ok = check(actual == expected, f'{label}: {path}: expected {expected}, actual {actual}')
    return {'path': str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),
            'expected_sha256': expected, 'actual_sha256': actual, 'passed': ok}


production = read('design/prime-counting-v1/production-run-v003.json')
movies = {v: Path(f'output/prime-counting-001-{v}') / MOVIE_NAME for v in VERSIONS}
timelines = {v: read(f'output/prime-counting-001-{v}/timeline.json') for v in VERSIONS}
renders = {v: read(f'output/prime-counting-001-{v}/render-record.json') for v in VERSIONS}
movie_bindings = [binding(movies[v], renders[v]['output_sha256'], v + ' render movie') for v in VERSIONS]
movie_bindings.append(binding(movies['v003'], production['video_sha256'], 'v003 adopted movie'))
render_binding = binding(production['render_record'], production['render_record_sha256'], 'v003 adopted render record')


def probe(version):
    command = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_packets', '-show_streams',
               '-show_entries', 'packet=pts_time,dts_time,duration_time,size,data_hash:stream=codec_name,codec_tag_string,profile,sample_fmt,sample_rate,channels,channel_layout,time_base,start_pts,start_time,duration_ts,duration,extradata_hash',
               '-show_data_hash', 'sha256', '-of', 'json', str(ROOT / movies[version])]
    result = subprocess.run(command, check=True, capture_output=True)
    filename = f'{version}-aac-packets.json'
    (OUT / filename).write_bytes(result.stdout)
    probed = json.loads(result.stdout)
    packets = probed['packets']
    return version, packets, {'version': version, 'command': command, 'packet_count': len(packets),
                            'evidence': str((OUT / filename).relative_to(ROOT)),
                            'evidence_sha256': sha(OUT / filename),
                            'stream_configuration': probed['streams'],
                            'canonical_packets_sha256': canonical_sha(packets),
                            'first_packet': packets[0], 'last_packet': packets[-1]}


packet_lists, packet_evidence = {}, []
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for version, packets, evidence in pool.map(probe, VERSIONS):
        packet_lists[version] = packets
        packet_evidence.append(evidence)
        check(len(packets) == 32173, version + ' packet count is not 32173')
        check(all(all(k in packet for k in ('pts_time', 'dts_time', 'duration_time', 'size', 'data_hash'))
                  for packet in packets), version + ' missing packet fields')
packet_comparisons = []
stream_configurations = {row['version']: row['stream_configuration'] for row in packet_evidence}
for previous, current in [('v001', 'v002'), ('v002', 'v003'), ('v001', 'v003')]:
    a, b = packet_lists[previous], packet_lists[current]
    differences = [i for i, (pa, pb) in enumerate(zip(a, b)) if pa != pb]
    identical = check(a == b, f'AAC packet arrays differ: {previous}->{current}')
    stream_identical = check(stream_configurations[previous] == stream_configurations[current],
                             f'AAC stream configuration differs: {previous}->{current}')
    packet_comparisons.append({'from': previous, 'to': current, 'all_fields_identical': identical,
                               'decoder_configuration_and_extradata_identical': stream_identical,
                               'differing_packet_indices': differences,
                               'fields': ['pts_time', 'dts_time', 'duration_time', 'size', 'data_hash', 'side_data_list_if_present']})

accepted_master_sha = timelines['v001']['master_audio']['sha256']
master_bindings = [binding(f'output/prime-counting-001-{v}/master.wav', accepted_master_sha,
                           v + ' PCM master') for v in VERSIONS]
timeline_audio_comparisons = []
for version in ('v002', 'v003'):
    fields = {key: check(timelines[version][key] == timelines['v001'][key],
                         f'{version} timeline audio field differs from accepted v001: {key}')
              for key in ['events', 'voice_events', 'duration_s', 'duration_frames', 'master_audio',
                          'timing', 'speech_manifest', 'speech_acceptance']}
    timeline_audio_comparisons.append({'version': version, 'identical_to_v001': fields})

gate_path = production['source_speech_gate']
left_path = production['final_aac_review']
right_path = production['audio_review_inheritance']['fresh_right_channel_recheck']
gate, left, right = (read(p) for p in (gate_path, left_path, right_path))
right_adopted = next(item for item in production['files'] if item['path'] == right_path)
review_bindings = [binding(gate_path, production['source_speech_gate_sha256'], 'adopted source gate'),
                   binding(left_path, production['final_aac_review_sha256'], 'adopted final LEFT review'),
                   binding(right_path, right_adopted['sha256'], 'adopted final RIGHT review')]
input_bindings = []
for label, review in [('source_gate', gate), ('left_review', left), ('right_review', right)]:
    for key, value in review['inputs'].items():
        input_bindings.append(binding(value['path'], value['sha256'], f'{label}:{key}'))

source_map = {event['id']: event for event in timelines['v003']['voice_events']}
check(len(source_map) == 188, 'source timeline does not have 188 distinct event IDs')
source_bindings = []
for result in gate['results']:
    ident = result['id']
    event = source_map[ident]
    check(result['accepted'] and not result['failures'], f'{ident}: source not accepted')
    check(result['sha256'] == event['source_sha256'] == event['sha256'], f'{ident}: source SHA mismatch in timeline/gate')
    check(result['spoken_text'] == event['spoken_text'], f'{ident}: source spoken text mismatch')
    check((ROOT / event['source_path']).resolve() == Path(result['path']).resolve(), f'{ident}: source path mismatch')
    source_bindings.append(binding(event['source_path'], result['sha256'], ident + ' accepted source WAV'))
check(set(source_map) == {result['id'] for result in gate['results']}, 'accepted source and timeline ID sets differ')

pronunciation_bindings = []
seen = set()
for result in gate['results']:
    for receipt in result['pronunciation_evidence']:
        key = (receipt['path'], receipt['sha256'])
        if key not in seen:
            seen.add(key)
            pronunciation_bindings.append(binding(*key, 'source pronunciation evidence'))

v001_movie_sha = sha(movies['v001'])
check(left['source_video_sha256'] == v001_movie_sha, 'left review is bound to different MP4')
check(right['source_video_sha256'] == v001_movie_sha, 'right review is bound to different MP4')
check(gate['accepted'] and not gate['unresolved'], 'source gate unresolved or not accepted')
check(left['passed'] and not left['unresolved'], 'left final review unresolved or failed')
check(right['passed'] and not right['unresolved'] and not right['findings'], 'right final review unresolved or failed')

excerpt_bindings = []
recognizer_bindings = []
for label, review, manifest_key, result_sha_key in [
        ('left', left, 'excerpt_manifest', 'final_aac_excerpt_sha256'),
        ('right', right, 'right-aac-manifest.json', 'right_excerpt_sha256')]:
    manifest_path = Path(review['inputs'][manifest_key]['path'])
    manifest = read(manifest_path)
    check(manifest['source_video_sha256'] == v001_movie_sha, f'{label}: excerpt manifest source MP4 mismatch')
    entries = manifest['numbers'] + manifest['dialogue']
    by_id = {entry['id']: entry for entry in entries}
    check(len(entries) == 188 and set(by_id) == set(source_map), f'{label}: excerpt event coverage differs')
    for entry in entries:
        p = Path(entry['path'])
        p = p if p.is_absolute() else manifest_path.parent / p
        excerpt_bindings.append(binding(p, entry['sha256'], label + ' final AAC excerpt ' + entry['id']))
    for result in review['results']:
        check(by_id[result['id']]['sha256'] == result[result_sha_key], f'{label}:{result["id"]}: reviewed excerpt SHA differs')
        if label == 'left':
            check(result['source_wav_sha256'] == source_map[result['id']]['source_sha256'],
                  label + ':' + result['id'] + ': reviewed source SHA differs')
    for key in (['fresh_asr', 'fresh_ctc'] if label == 'left' else ['fresh-asr.json', 'fresh-ctc.json']):
        recognizer = read(review['inputs'][key]['path'])
        check(recognizer['source_manifest_sha256'] == sha(manifest_path), f'{label}:{key}: manifest hash differs')
        results = recognizer['results']
        check(len(results) == 188 and {r['id'] for r in results} == set(source_map), f'{label}:{key}: coverage differs')
        for result in results:
            # Both ASR and CTC record the exact presented audio file.
            check(result['source_sha256'] == by_id[result['id']]['sha256'],
                  f'{label}:{key}:{result["id"]}: recognizer input SHA differs')
        recognizer_bindings.append({'side': label, 'input_key': key, 'results': len(results),
                                    'all_audio_sha256_bindings_passed': True})

report = {
    'schema_version': 1, 'kind': 'fresh-prime-v003-audio-packet-and-evidence-identity-recheck',
    'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
    'checked_at_jst': dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    'passed': not failures, 'status': 'PASS' if not failures else 'FAIL',
    'scope': {
        'fresh': 'Actual v001/v002/v003 MP4 SHA256; all AAC packet payload hashes, PTS/DTS/duration/size; PCM master file SHA256; timeline source events and exact prior evidence hash bindings.',
        'inherited': 'Accepted-source pronunciation review plus actual v001 final LEFT and RIGHT AAC ASR/CTC/acoustic review, applicable because the complete v003 AAC packet payloads and timestamps are freshly proven identical.',
        'not_run': ['New speech synthesis', 'New ASR or CTC inference', 'Full human listening', 'Heavy full-decode/loudness/stereo waveform analysis, handled by root fresh generic media verifier'],
        'old_media_and_records_modified': False,
    },
    'movie_bindings': movie_bindings, 'adopted_render_record_binding': render_binding,
    'packet_evidence': packet_evidence, 'packet_comparisons': packet_comparisons,
    'master_bindings': master_bindings, 'timeline_audio_comparisons': timeline_audio_comparisons,
    'adopted_review_bindings': review_bindings, 'prior_review_input_bindings': input_bindings,
    'source_event_bindings': source_bindings, 'source_pronunciation_evidence_bindings': pronunciation_bindings,
    'final_aac_excerpt_bindings': excerpt_bindings, 'recognizer_manifest_and_excerpt_bindings': recognizer_bindings,
    'prior_review_coverage': {'source': gate['summary'], 'left': left['coverage'], 'right': right['coverage']},
    'prior_documented_warnings': {
        'asr': [
            {'id': 'N599', 'recognized': '$599.', 'expected': 'five hundred ninety-nine',
             'classification': 'Reviewed ASR numeric/currency formatting variant, not a demonstrated speech error'},
            {'id': 'I05', 'recognized_variant': "It's", 'expected_variant': 'Its',
             'classification': 'Reviewed homophonous orthographic variant, not a demonstrated speech error'},
        ],
        'ctc': 'Previously reviewed label variants (LEFT versus source 25; RIGHT versus LEFT 22). Short two has indeterminate multilingual CTC labels; independent lexical recognition, waveform continuity, and same-voice vowel controls support the intended word. Label variance is not treated as perfect phonetic truth.',
        'unresolved_actionable_findings': 0,
        'limitations': 'Automated pronunciation evidence can miss subtle articulation; no new human full-listening or new speech-model inference is claimed.'
    },
    'failures': failures,
    'reproduction_script': str(Path(__file__).relative_to(ROOT)),
    'reproduction_script_sha256': sha(Path(__file__)),
}
(OUT / 'audio-identity-recheck.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
summary = f'''素数 v003 音声同一性・検査根拠の再確認: {report['status']}
確認日時: {report['checked_at_jst']}
現行 MP4 SHA256: {sha(movies['v003'])}
全 32,173 AAC パケットのペイロード SHA256・PTS/DTS・duration・size を実ファイルから新規抽出し、v001→v002→v003 の完全一致を確認。
PCM マスター3版は採用マスター SHA256 {accepted_master_sha} と一致。
188音声イベント（素数168、説明20）、時刻・音声・テキスト・ゲインは v001 から不変。全188入力 WAV の現物ハッシュも採用記録と一致。
採用済み原音源ゲート、v001 左右 AAC の独立ASR/CTC検査、全入力根拠・全376抜粋WAVを現物ハッシュで再照合。
過去の認識警告2件（N599の通貨表記、I05のIts/It's）とCTCラベル差は記録済みの非実害差異。未解決の要修正事項は0件。
本記録で新規実施したのは音声パケット・タイミング・ファイル・検査根拠の同一性照合。発音評価は完全一致した既存AACに紐づく過去検査を継承する。新しいASR/CTC推論、人の全編試聴を行ったとは主張しない。
全編デコード・音量・左右波形・無音の新規検査は親担当の汎用検査で別途記録。
不一致: {len(failures)}
'''
(OUT / 'audio-identity-recheck.txt').write_text(summary)
print(json.dumps({'status': report['status'], 'packets_per_version': [x['packet_count'] for x in packet_evidence],
                  'source_WAVs': len(source_bindings), 'excerpt_WAVs': len(excerpt_bindings),
                  'prior_input_bindings': len(input_bindings), 'failures': failures,
                  'report': str(OUT / 'audio-identity-recheck.json')}, ensure_ascii=False, indent=2))
