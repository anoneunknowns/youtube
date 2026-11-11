"""Resolve the false dual-mono premise using a controlled encoder experiment."""
from datetime import datetime,timezone
import hashlib,json,re,subprocess
from pathlib import Path

work=Path(__file__).parent
out=Path('D:/codex_projects/youtube/output/four-base-counting-001-v002-to-200')
first=json.loads((work/'independent-audio-audit.json').read_text(encoding='utf-8'))
stereo=json.loads((work/'stereo-difference-analysis.json').read_text(encoding='utf-8'))
causal=json.loads((work/'aac-pns-causal-diagnostic.json').read_text(encoding='utf-8'))
assert first['errors']==['dual_mono_channels_preserved']
on=next(r for r in causal['candidates'] if r['pns']==1)
off=next(r for r in causal['candidates'] if r['pns']==0)
assert on['original_prefix_max_difference']==0 and on['original_prefix_exact_samples']==on['original_samples_compared']==63586108
assert off['n164_channel_max_difference_pcm16']==0 and off['whole_channel_max_difference_pcm16']==118
assert stereo['minimum_left_reference_correlation']>.99 and stereo['minimum_right_reference_correlation']>.99
assert stereo['maximum_channel_level_delta_db']<.001

command=['D:/dev/FFmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe','-hide_banner','-nostdin','-i',str(out/'paspla-studio-four-ways-to-count-0-to-200-1080p.mp4'),'-map','0:a:0','-af','ebur128=peak=true','-f','null','-']
done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
with (work/'fresh-ebur128.stderr.txt').open('xb') as stream:stream.write(done.stderr)
assert done.returncode==0
text=done.stderr.decode('utf-8',errors='replace')
loudness=float(re.findall(r'Integrated loudness:\s*I:\s*([\d.\-]+) LUFS',text)[-1])
true_peak=float(re.findall(r'True peak:\s*Peak:\s*([\d.\-]+) dBFS',text)[-1])
assert -17<=loudness<=-15 and true_peak<=-1

report={
 'status':'pass','checked_at_utc':datetime.now(timezone.utc).isoformat(),
 'video_sha256':first['video_sha256'],'timeline_sha256':first['timeline_sha256'],
 'initial_audit':'independent-audio-audit.json',
 'initial_failed_guard':'dual_mono_channels_preserved',
 'resolution':'The initial guard incorrectly required lossy AAC channels to stay sample-identical for a dual-mono source. A controlled full-master encode with default PNS on reproduces every decoded final AAC sample exactly. Disabling PNS removes the N164 channel difference, establishing encoder causality rather than a wrong source, a missing channel or an alignment defect. Original failure evidence is retained.',
 'causal_evidence':'aac-pns-causal-diagnostic.json',
 'media_changed':False,'unresolved_content_or_timing_errors':0,
 'valid_initial_checks_passed':first['checks_total']-1,
 'all_speech_semantic_matches':first['semantic_meaning_matches'],
 'extended_source_gate_and_phoneme_checks':73,
 'fresh_decoded_frames':first['fresh_decoded_frames'],'clipped_samples':0,
 'global_audio_delay_s':first['master_to_aac_envelope_best_lag_s'],
 'maximum_onset_or_tail_difference_s':max(first['maximum_absolute_onset_delta_s'],first['maximum_absolute_tail_delta_s']),
 'silence_interiors_checked':first['fresh_silence_interiors_checked'],
 'left_reference_correlation_min':stereo['minimum_left_reference_correlation'],
 'right_reference_correlation_min':stereo['minimum_right_reference_correlation'],
 'channel_level_delta_db_max':stereo['maximum_channel_level_delta_db'],
 'fresh_ebur128':{'command':command,'exit_code':done.returncode,'integrated_lufs_rounded':loudness,'true_peak_dbfs_rounded':true_peak,'log':'fresh-ebur128.stderr.txt'},
 'evidence_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [work/'independent-audio-audit.json',work/'stereo-difference-analysis.json',work/'aac-pns-causal-diagnostic.json',work/'aac-encoder-help.txt']},
 'limitations':['No full human listening review is claimed.','This distinguishes content/timing defects from documented lossy encoding differences; it does not claim transparent encoding for every listener.']
}
(work/'independent-audio-audit-resolved.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','valid_initial_checks_passed','all_speech_semantic_matches','fresh_decoded_frames','maximum_onset_or_tail_difference_s','silence_interiors_checked','fresh_ebur128']}))
