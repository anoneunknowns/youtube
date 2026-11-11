"""Bind the closed v002 audio audit to an actual v003 movie by signal identity.

Read-only media check. The output folder must not exist; no inference or media
rewrite is performed. Voice cues/base/master must also remain identical.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[5]
QA=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.remux_fibonacci_audio import packets, pcm_digest


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def ref(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)}
def save(path,data):
    with path.open('x') as stream:json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n')


def adts(path,ffmpeg):
    command=[ffmpeg,'-v','error','-nostdin','-i',str(path),'-map','0:a:0','-c:a','copy','-f','adts','pipe:1']
    process=subprocess.Popen(command,stdout=subprocess.PIPE);digest=hashlib.sha256();length=0
    while block:=process.stdout.read(1024*1024):digest.update(block);length+=len(block)
    if process.wait():raise RuntimeError('ADTS extraction failed')
    return {'sha256':digest.hexdigest(),'bytes':length,'command':command}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    final,timeline,dest=args.video.resolve(),args.timeline.resolve(),args.out_dir.resolve()
    closeout=QA/'audio-closeout.json'
    closeout_data=read(closeout)
    assert closeout_data['passed']
    old=ROOT/'output/fibonacci-counting-001-v002/paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
    old_timeline=ROOT/'output/fibonacci-counting-001-v002/timeline.json'
    before,after=read(old_timeline),read(timeline)
    assert closeout_data['audited_movie']==ref(old), 'Closeout did not audit this predecessor'
    assert closeout_data['audited_timeline']==ref(old_timeline), 'Closeout timeline changed'
    original_final_review=old.parent/'audio-final-qa/final-aac-review.json'
    original_review=read(original_final_review)
    assert original_review['passed'] and original_review['accepted']
    assert original_review['video']==ref(old) and original_review['timeline']==ref(old_timeline)
    assert before['voice_events']==after['voice_events'], 'Voice events changed'
    assert before['master_audio']==after['master_audio'], 'Master binding changed'
    for key in ('source_timeline','speech_manifest','speech_acceptance'):
        assert before[key]==after[key],key+' changed'
    dest.mkdir(parents=True,exist_ok=False)
    ffmpeg,ffprobe=str(ROOT/'.venv/bin/ffmpeg'),str(ROOT/'.venv/bin/ffprobe')
    def stream_contract(path):
        output=subprocess.check_output([ffprobe,'-v','error','-select_streams','a:0','-show_streams',
                '-show_data_hash','sha256','-of','json',str(path)],text=True)
        stream=json.loads(output)['streams'][0]
        keys=('codec_name','profile','codec_tag_string','sample_fmt','sample_rate','channels',
              'channel_layout','time_base','start_pts','start_time','duration_ts','duration','extradata_hash')
        return {key:stream.get(key) for key in keys}
    old_stream,new_stream=stream_contract(old),stream_contract(final)
    assert old_stream==new_stream, 'AAC stream format, time base, start or duration changed'
    with ThreadPoolExecutor(max_workers=2) as pool:
        old_packets,new_packets=list(pool.map(lambda path:packets(path,'a:0',ffprobe),(old,final)))
    save(dest/'v002-audio-packets.json',old_packets);save(dest/'v003-audio-packets.json',new_packets)
    assert old_packets==new_packets,'AAC payload or pts/dts/duration/size changed'
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(adts,path,ffmpeg) for path in (old,final)]
        futures+=[pool.submit(pcm_digest,path,ffmpeg) for path in (old,final)]
        old_adts,new_adts,old_pcm,new_pcm=[future.result() for future in futures]
    assert old_adts['sha256']==new_adts['sha256'] and old_adts['bytes']==new_adts['bytes']
    assert old_pcm==new_pcm
    contract=hashlib.sha256(json.dumps(old_packets,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result={'schema_version':1,'kind':'final-v003-identical-AAC-audio-audit-binding','passed':True,
            'checked_at_utc':datetime.now(timezone.utc).isoformat(),'audited_v002_movie':ref(old),
            'final_v003_movie':ref(final),'v002_timeline':ref(old_timeline),'v003_timeline':ref(timeline),
            'independent_audio_closeout':ref(closeout),
            'original_finished_AAC_review':ref(original_final_review),
            'source_speech_acceptance':before['speech_acceptance'],
            'AAC_stream_format_time_base_start_duration_identical':True,'AAC_stream_contract':new_stream,
            'AAC_all_payloads_pts_dts_durations_sizes_identical':True,'AAC_packet_count':len(new_packets),
            'AAC_packet_contract_sha256':contract,'ADTS':{'v002':old_adts,'v003':new_adts},
            'decoded_PCM48k24bitStereo':new_pcm,'complete_voice_cues_and_source_base_master_identical':True,
            'new_ASR_CTC_inference_performed_for_v003':False,
            'inference_inheritance_basis':'The actual final AAC signal, packet times and complete voice cue/source/master contracts are identical to the independently audited v002 signal.',
            'human_full_listening_claim':False,'helper':ref(Path(ROOT/'tools/remux_fibonacci_audio.py'))}
    save(dest/'verification.json',result)
    print(json.dumps({'passed':True,'AAC_packet_count':len(new_packets),'report':str(dest/'verification.json'),'video':ref(final)}))


if __name__=='__main__':main()
