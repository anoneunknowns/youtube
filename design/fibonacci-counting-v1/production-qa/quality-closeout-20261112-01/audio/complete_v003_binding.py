"""Validate retained audio evidence and assemble the v003 inheritance receipt."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[5]
QA=Path(__file__).resolve().parent
OUT=ROOT/'output/fibonacci-counting-001-v003'
DEST=OUT/'audio-inheritance-qa/v001'


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def resolve(value):
    path=Path(value)
    return path if path.is_absolute() else ROOT/path
def ref(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)}
def save(name,data):
    with (DEST/name).open('x') as stream:json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n')


proof_path=DEST/'verification.json'
proof=read(proof_path)
assert proof['passed']
checks=[]


def verify_ref(row,role):
    path=resolve(row['path'])
    assert sha(path)==row['sha256'], 'Changed '+role+': '+row['path']
    checks.append({'role':role,**ref(path),'passed':True})


for name in ('audited_v002_movie','final_v003_movie','v002_timeline','v003_timeline',
             'independent_audio_closeout','original_finished_AAC_review','source_speech_acceptance'):
    verify_ref(proof[name],name)
closeout=read(resolve(proof['independent_audio_closeout']['path']))
original=read(resolve(proof['original_finished_AAC_review']['path']))
assert closeout['passed'] and original['passed'] and original['accepted']
assert closeout['audited_movie']==proof['audited_v002_movie']
assert original['video']==proof['audited_v002_movie']
for name,report in [('new_independent_closeout',closeout),('original_stereo_final_AAC_review',original)]:
    for row in report['inputs']:verify_ref(row,name+' input')
plan=read(OUT/'timeline.json')
for name in ('master_audio','source_timeline','speech_manifest','speech_acceptance'):
    verify_ref(plan[name],'v003 '+name)
source_manifest_path=resolve(plan['speech_manifest']['path'])
source_manifest=read(source_manifest_path)
sources={row['id']:row for row in source_manifest['numbers']+source_manifest['dialogue']}
assert len(sources)==len(plan['voice_events'])==104
for event in plan['voice_events']:
    row=sources[event['id']]
    path=Path(row['path']);path=path if path.is_absolute() else source_manifest_path.parent/path
    assert sha(path)==row['sha256']==event['source_sha256']
    assert row['spoken_text']==event['text']
    checks.append({'role':'unchanged accepted original speech '+event['id'],**ref(path),'passed':True})
for channel in ('left','right'):
    manifest_path=ROOT/f'output/fibonacci-counting-001-v002/audio-final-qa/{channel}/measurements.json'
    manifest=read(manifest_path)
    assert manifest['source_video']['sha256']==proof['audited_v002_movie']['sha256']
    assert len(manifest['numbers'])+len(manifest['dialogue'])==104
    for row in manifest['numbers']+manifest['dialogue']:
        path=manifest_path.parent/row['path'];assert sha(path)==row['sha256']
        checks.append({'role':'retained actual-v002-AAC inference input '+channel+' '+row['id'],**ref(path),'passed':True})
save('audited-evidence-integrity.json',{'kind':'retained-audio-evidence-and-actual-clip-integrity-check',
                                     'passed':True,'checked_at_utc':datetime.now(timezone.utc).isoformat(),
                                     'binary_inheritance_proof':ref(proof_path),'file_binding_checks':len(checks),
                                     'accepted_source_clips_verified':104,'retained_actual_final_AAC_clips_verified':208,
                                     'prior_inference_reexecuted':False,'results':checks})
integrity_path=DEST/'audited-evidence-integrity.json'
result={'schema_version':1,'kind':'finished-fibonacci-v003-audio-review-by-exact-bitstream-inheritance',
        'passed':True,'status':'IDENTICAL_AAC_INHERITANCE_BOUND_TO_CLOSED_INDEPENDENT_AUDIO_REVIEW',
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'video':proof['final_v003_movie'],'timeline':proof['v003_timeline'],
        'predecessor_audited_video':proof['audited_v002_movie'],
        'binary_inheritance_proof':ref(proof_path),'retained_evidence_integrity':ref(integrity_path),
        'independent_audio_closeout':proof['independent_audio_closeout'],
        'original_final_stereo_AAC_review':proof['original_finished_AAC_review'],
        'summary':{'AAC_packet_payloads_and_PTS_DTS_durations_sizes_identical':proof['AAC_packet_count'],
                   'AAC_time_base_format_start_duration_identical':True,'ADTS_identical':True,
                   'decoded_PCM48k24bitStereo_identical':True,'voice_cues_and_base_master_identical':104,
                   'verified_accepted_original_clips':104,'verified_retained_final_AAC_inference_clips':208,
                   'fresh_ASR_or_CTC_runs_performed_for_v003':0,'material_audio_defects_identified':0,
                   'unresolved_material_audio_findings':0},
        'inherited_AAC_measurements':original['final_AAC_measurements'],
        'new_audio_inference_for_v003_claim':False,
        'inference_scope':'Original v002 completed208stereo ASR/CTC/acoustics plus the later independent104base.en/104guardedCTC,1221word/1714nucleus and13unadopted-candidate audit are the retained inference evidence. V003 receives that same actual audio signal with identical packet times and complete104voice cues; no new inference is mislabeled as v003.',
        'diagnostic_model_discrepancies':'Reviewed and explained with direct single-clip phonetic/physical evidence; raw warnings preserved, no material audio defect. Not used to claim perfect perception or erase diagnostic logs.',
        'human_full_listening_claim':False,'perfect_pronunciation_claim':False,
        'limitations':'Exact audio inheritance does not certify altered video pixels, which are checked by the separate final-video verifier. No human full-listening session is claimed.',
        'helper':ref(Path(__file__))}
save('final-audio-review.json',result)
text=f'''フィボナッチv003 音声継承検査: 合格

対象MP4 SHA-256: {proof['final_v003_movie']['sha256']}
実際のv003と監査済みv002を新たに比較しました。
AAC全{proof['AAC_packet_count']}パケットのpayload、PTS、DTS、duration、sizeが完全一致。
音声形式・timebase・開始/終了時刻も一致。ADTS全bytesとdecoded48kHz24bitstereo PCMも完全一致です。
ADTS SHA-256: {proof['ADTS']['v003']['sha256']}
全104発話cue、採用原音、base timeline、マスターの束縛は同一。
保持された原音104件と、元完成AAC再認識に使った左右208clip、元gateと今回独立closeoutの全参照SHAも再検証しました。

v003でASR/CTCを新規実行した記録ではありません。
監査済みv002の208件stereo新規解析と、後の別base.en104/guardedCTC104/1221語/1714母音核の独立監査を、同一bitstreamと時刻を根拠にv003へ継承しています。
新単語候補13本は全て未採用。診断モデル差分の原因は確認済み、実質的な未解決音声不備0。
同一信号の音量値は -16.52LUFS / -1.98dBTP。既存原音・媒体・QAは変更していません。

人の全件試聴や完全な発音保証は主張しません。改訂映像の画素・動作検査は別の最終動画QAです。
正本: final-audio-review.json（binary proof: verification.json）
'''
with (DEST/'final-audio-review.txt').open('x') as stream:stream.write(text)
print(json.dumps({'passed':True,'file_binding_checks':len(checks),'report':ref(DEST/'final-audio-review.json'),'proof':ref(proof_path)}))
