"""Fresh v004 lesson/audio QA with the adopted short publishing style.

The old media verifiers remain immutable. This finite adapter reuses their
independent mathematics, glyph, transfer and waveform measurements, while
checking the new publishing text and exact audio inheritance explicitly.
Character performance is accepted separately by verify_fibonacci_motion_v004.
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
from fractions import Fraction
import json,multiprocessing,re,subprocess,tempfile
from pathlib import Path

if __package__:
    from . import verify_fibonacci_video_v003 as previous
    from . import verify_fibonacci_motion_v004 as motion
else:
    import verify_fibonacci_video_v003 as previous
    import verify_fibonacci_motion_v004 as motion

old=previous.old
ROOT=old.ROOT


def captions_and_metadata(plan,events,directory,publishing=None):
    directory=Path(directory);publishing=Path(publishing or ROOT/'design/fibonacci-counting-v1/publishing-v002')
    captions=directory/'english-captions.srt'
    blocks=re.split(r'\n\s*\n',captions.read_text(encoding='utf-8-sig').strip())
    old.require(len(blocks)==len(events)==104,'Caption count is not104')
    def stamp(event,edge):
        key='start_sample_24k' if edge=='start_s' else 'end_sample_24k'
        value=Fraction(event[key],24) if key in event else Fraction(str(event[edge]))*1000
        ms=round(value)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    for i,(block,e) in enumerate(zip(blocks,events,strict=True),1):
        lines=block.splitlines()
        old.require(lines==[str(i),f'{stamp(e,"start_s")} --> {stamp(e,"end_s")}',e['text']],f'Caption text/rounded edge mismatch{i}')
    alternatives=[p for p in directory.glob('*.srt') if p!=captions]
    for p in alternatives:old.require(p.read_bytes()==captions.read_bytes(),f'Caption alias differs: {p.name}')
    refs={}
    for name in ('youtube-title.txt','youtube-description.txt','upload-details.txt'):
        delivered=directory/name;adopted=publishing/name
        old.require(delivered.read_bytes()==adopted.read_bytes(),f'Delivery differs from adopted public text: {name}')
        refs[name]={'adopted':str(adopted),'sha256':old.sha(delivered)}
    title=(directory/'youtube-title.txt').read_text().strip()
    description=(directory/'youtube-description.txt').read_text().strip()
    old.require(title=='Count Fibonacci Numbers from 0 to 102,334,155 | Num-Num Numbers','Fibonacci title/signature/range differs')
    paragraphs=description.split('\n\n')
    old.require(len(paragraphs)==4 and paragraphs[-1]=='━━━━━━━━━━━━━━━━━━','Description is not the adopted four-paragraph style')
    old.require(paragraphs[0]=='Count Fibonacci numbers with our Siamese cat guide above the clouds.','Description setting/guide differs')
    for phrase in ('from 0 and 1 to 102,334,155','Add the previous two values','keep the newest pair','both ones','place value and carrying'):
        old.require(phrase in paragraphs[1],f'Description loses accurate lesson meaning: {phrase}')
    old.require(paragraphs[2]=='Num-Num Numbers — Paspla Studio\nhttps://pasplastudio.com/num-num-numbers/','Official signature/URL differs')
    old.require((directory/'upload-details.txt').read_text().strip()==title+'\n\n'+description,'Upload block differs from title/description')
    # Chapters remain a separate delivered file; no chapter block, counts or
    # hashtags are required inside the user's intentionally short description.
    chapters=directory/'chapters.txt';parsed=[]
    for line in chapters.read_text().splitlines():
        m=re.fullmatch(r'(?:(\d+):)?(\d{1,2}):(\d\d)\s+(.+)',line)
        old.require(m is not None,'Malformed chapter line')
        h,mi,s,name=m.groups();parsed.append((int(h or 0)*3600+int(mi)*60+int(s),name))
    old.require(len(parsed)==7 and parsed[0][0]==0 and all(a[0]<b[0] for a,b in zip(parsed,parsed[1:])),'Seven chapter order differs')
    ends=[x[0] for x in parsed[1:]]+[plan['duration_s']]
    old.require(all(end-start[0]>=10 for start,end in zip(parsed,ends)),'Chapter shorter than10 seconds')
    baseline=motion.local_path(plan['source_visual_revision']['path']).parent
    old.require(chapters.read_bytes()==(baseline/'chapters.txt').read_bytes(),'Unchanged cue timing but chapter file changed')
    return {'passed':True,'caption_cues':104,'caption_sha256':old.sha(captions),'caption_aliases':len(alternatives),
        'caption_time_method':'Independent nearest-even millisecond rounding from exact24k source sample grid',
        'title':title,'adopted_publication':refs,'chapters':parsed,'chapter_sha256':old.sha(chapters),
        'description_scope':'Adopted short four-paragraph user style; separate seven-chapter file. No old mandatory count/chapters/hashtags rule.'}


def audio_signature(video,ffprobe,ffmpeg,directory):
    command=[ffprobe,'-v','error','-select_streams','a:0','-show_streams','-show_packets','-show_data_hash','sha256','-of','json',str(video)]
    data=json.loads(subprocess.check_output(command))
    fields=('pts','dts','duration','size','data_hash')
    packets=[{k:p.get(k) for k in fields} for p in data['packets']]
    streamfields=('codec_name','codec_type','sample_fmt','sample_rate','channels','channel_layout','time_base','start_pts','start_time','duration_ts','duration')
    stream={k:data['streams'][0].get(k) for k in streamfields}
    adts=directory/'audio.aac';pcm=directory/'audio-48k-stereo-s24le.pcm'
    subprocess.run([ffmpeg,'-nostdin','-v','error','-xerror','-i',str(video),'-map','0:a:0','-c:a','copy','-f','adts',str(adts)],check=True)
    subprocess.run([ffmpeg,'-nostdin','-v','error','-xerror','-i',str(video),'-map','0:a:0','-ar','48000','-ac','2','-c:a','pcm_s24le','-f','s24le',str(pcm)],check=True)
    return {'packets':packets,'stream':stream,'adts_sha256':old.sha(adts),'decoded_pcm_sha256':old.sha(pcm),'decoded_pcm_bytes':pcm.stat().st_size}


def audio_inheritance(plan,video,ffprobe,ffmpeg,directory):
    source=motion.local_path(plan['source_visual_revision']['path']).parent/video.name
    old.require(source.is_file(),'Missing v003 source movie for exact audio inheritance')
    signatures=[]
    for name,path in [('source-v003',source),('current-v004',video)]:
        target=directory/name;target.mkdir(parents=True,exist_ok=False)
        signatures.append(audio_signature(path,ffprobe,ffmpeg,target))
    a,b=signatures
    old.require(a==b,'V004 AAC packets or decoded audio differ from source v003')
    return {'passed':True,'source_video':str(source),'source_video_sha256':old.sha(source),
        'aac_packets':len(b['packets']),'packet_fields':['payload_sha256','pts','dts','duration','size'],
        'audio_stream':b['stream'],'adts_sha256':b['adts_sha256'],'decoded_pcm_sha256':b['decoded_pcm_sha256'],
        'decoded_pcm_bytes':b['decoded_pcm_bytes'],'new_ASR_CTC_runs':0,
        'scope':'Exact encoded packets, timing, format, ADTS and stereo24bit48k decoded PCM identity; fresh104 stereo waveform comparisons are separately measured in this run. Recognition evidence inherits the identical signal, not a claim of new ASR.'}


def parser():
    p=previous.parser();p.description=__doc__
    p.add_argument('--publishing-dir',type=Path)
    return p


def main(argv=None):
    args=parser().parse_args(argv);old.require(args.ffmpeg and args.ffprobe,'FFmpeg/ffprobe required')
    args.out_dir.mkdir(parents=True,exist_ok=False);plan=json.loads(args.timeline.read_text())
    report={'schema_version':1,'kind':'independent-fibonacci-v004-final-verification',
      'checked_at_utc':datetime.now(timezone.utc).isoformat(),'video':str(args.video.resolve()),
      'video_sha256':old.sha(args.video),'timeline_sha256':old.sha(args.timeline),'verifier_sha256':old.sha(__file__),'passed':False}
    try:
        motion_path=motion.local_path(plan['character_motion']['path']);motion_plan=json.loads(motion_path.read_text())
        _,_,report['lesson_binding']=motion.validate_binding(plan,motion_plan,motion_path)
        events,states,segments,report['schedule']=old.validate_schedule(plan)
        if not args.skip_technical:
            report['technical']=old.technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            old.require(report['technical']['status']=='pass','Technical media checks failed')
            old.require(report['technical']['measurements']['true_peak_dbtp']<=-1.45,'Final AAC true peak exceeds accepted ceiling')
        report['captions_and_metadata']=captions_and_metadata(plan,events,args.delivery_dir or args.video.parent,args.publishing_dir)
        with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
            generic=pool.submit(previous.generic_visual_job,args.video,plan,states,segments,args.ffmpeg,args.out_dir/'visual')
            transfers=pool.submit(previous.transfer_visual_job,args.video,plan,args.ffmpeg,args.out_dir/'all-transfers')
            excerpts=(args.final_aac_clips_dir or args.video.parent/'audio-final-qa'/'clips') if args.extract_final_clips else None
            with tempfile.TemporaryDirectory(prefix='fibonacci-v004-audio-qa-') as work:
                report['audio']=old.media.audio_checks(plan,events,args.video,args.master,args.ffmpeg,Path(work),excerpts)
            report['audio']['scope']=f"All {len(report['audio']['tracks'][0]['events'])} scheduled source waveforms against master and actual AAC, both stereo channels, with guarded silent intervals. No recognition or human-listening claim."
            if excerpts:print(json.dumps({'event':'final_aac_manifest_ready','path':report['audio']['recognition_excerpt_manifest']}),flush=True)
            with tempfile.TemporaryDirectory(prefix='fibonacci-v004-audio-identity-') as work:
                report['exact_audio_inheritance']=audio_inheritance(plan,args.video,args.ffprobe,args.ffmpeg,Path(work))
            report['intro_and_fades']=previous.intro.run(args.video,plan,args.ffmpeg,args.out_dir/'intro-and-fades')
            report['visual']=generic.result();report['all_transfers']=transfers.result()
        old.require(all(report[k]['passed'] for k in ('visual','audio','all_transfers','intro_and_fades','exact_audio_inheritance')),'Independent finished-media checks failed')
        old.require(old.sha(args.video)==report['video_sha256'],'Video changed during verification')
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        report['scope']='Fresh all-frame mathematical/English/raster checks, every native transfer frame, intro-seeds/fades,104 stereo source waveforms/silences, exact audio inheritance and current publishing text. Character performance requires the separate v004 motion report. No human continuous viewing/listening claim.'
        (args.out_dir/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json')}))


if __name__=='__main__':main()
