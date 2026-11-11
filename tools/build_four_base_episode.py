"""Bind reviewed decimal narration and build the measured four-base audio master."""
from __future__ import annotations

import argparse
from array import array
from collections import Counter
import copy
import json
import math
from pathlib import Path
import shutil
import tempfile
import wave

if __package__:
    from . import build_audio_mix as audio
    from . import prepare_four_base_episode as prep
    from .build_octal_episode import checked_wav, dialogue_key, event, local_path, measure, mix, read, write
    from .build_hexadecimal_episode import adopted_dialogue
else:
    import build_audio_mix as audio
    import prepare_four_base_episode as prep
    from build_octal_episode import checked_wav, dialogue_key, event, local_path, measure, mix, read, write
    from build_hexadecimal_episode import adopted_dialogue

ROOT=prep.ROOT
DESIGN=prep.OUTPUT
RATE=24000
OUTPUT=ROOT/'output/four-base-counting-001-v001'


def frames(seconds):return round(seconds*RATE)
def seconds(count):return count/RATE


def fresh_dialogue(candidates, reports, phoneme_reports, expected, staging, destination):
    asr={}
    for path in reports:
        report=read(path)
        if report['kind']!='independent-local-asr-review' or audio.file_hash(Path(report['source_manifest']))!=report['source_manifest_sha256']:
            raise ValueError('ASR source manifest has changed')
        asr.update((row['source_sha256'],row) for row in report['results'])
    phonemes={}
    for path in phoneme_reports:
        report=read(path)
        if report['kind']!='isolated-phoneme-asr':raise ValueError('Wrong acoustic review kind')
        phonemes.update((row['source_sha256'],row) for row in report['results'])
    if Counter(row['id'] for row in candidates)!=Counter(expected.keys()):
        raise ValueError('Fresh narration IDs differ from the required script')
    result={}
    for candidate in candidates:
        cue_id=candidate['id']
        source=Path(candidate['path'])
        lexical=asr[candidate['sha256']]
        acoustic=phonemes[candidate['sha256']]
        if candidate['text']!=expected[cue_id] or lexical['expected_text']!=candidate['text']:
            raise ValueError(f'Wrong candidate text for {cue_id}')
        if dialogue_key(lexical['recognized_text'])!=dialogue_key(candidate['text']):
            raise ValueError(f'Unresolved exact dialogue recognition for {cue_id}: {lexical["recognized_text"]}')
        if Path(lexical.get('path',lexical.get('source_path',''))).resolve()!=source.resolve():
            raise ValueError(f'ASR is not bound to source path {cue_id}')
        count=checked_wav(source,candidate['sha256'],candidate['duration_s'],RATE,1)
        if audio.file_hash(Path(acoustic['source_path']))!=acoustic['source_sha256']:
            raise ValueError(f'Acoustic source changed for {cue_id}')
        target=staging/f'{cue_id}.wav'
        shutil.copyfile(source,target)
        result[cue_id]={
            'text':candidate['text'],'path':local_path(destination/target.name),'sha256':candidate['sha256'],
            'sample_frames':count,'duration_s':seconds(count),'generation':{k:v for k,v in candidate['generation'].items() if k!='status'},
            'trim':candidate['trim'],'asr_status':'text-match','asr_transcript':lexical['recognized_text'],
            'independent_phoneme_transcript':acoustic['recognized_phonemes'],
            'review_method':'Unprompted Whisper tiny.en plus independent CTC phonemes; no human listening claim.'}
    return result,phonemes


def measured_schedule(estimate,numbers,dialogue,phonemes):
    plan=copy.deepcopy(estimate)
    events=[]
    for state in plan['counted_states']:
        value=state['decimal_value']
        source=numbers[value]
        item=event(source,f'N{value:03d}','number_voice','count',frames(state['estimated_voice_start_s']),source['spoken_text'],decimal_value=value,narration_base=10)
        if frames(state['estimated_voice_end_s'])!=item['end_sample_24k']:
            raise ValueError(f'Count duration differs for {value}')
        events.append(item)
        state.update(display_start_s=state['estimated_display_start_s'],display_end_s=state['estimated_display_end_s'],
                     voice_start_s=item['start_s'],voice_end_s=item['end_s'],voice_event_id=item['id'])
    sections=[('intro',0,plan['intro']['dialogue'])]
    sections.extend(('pause',pause['estimated_start_s'],[pause['dialogue']]) for pause in plan['pauses'])
    sections.append(('finale',plan['finale']['estimated_start_s'],plan['finale']['dialogue']))
    for phase,origin,cues in sections:
        for cue in cues:
            cue_id=cue['id']
            source=numbers[10] if cue_id=='I04-TEN' else dialogue[cue_id]
            start,limit=(frames(origin)+frames(point) for point in cue['relative_window_s'])
            extra={'decimal_value':10,'narration_base':10} if cue_id=='I04-TEN' else {}
            item=event(source,cue_id,'number_voice' if cue_id=='I04-TEN' else 'dialogue',phase,start,cue['text'],**extra)
            if item['end_sample_24k']>limit:raise ValueError(f'Dialogue exceeds its editorial window: {cue_id}')
            events.append(item)
            cue.update(audio_status='measured-and-reviewed',actual_start_s=item['start_s'],actual_end_s=item['end_s'],
                       source_path=item['source_path'],source_sha256=item['source_sha256'])
    # These visual holds follow independent CTC boundaries for the adopted I02.
    # Holds include the natural pauses until the next base name begins.
    row=next(row for row in phonemes.values() if row['id']=='I02' and row['source_sha256']==dialogue['I02']['sha256'])
    tokens=row['tokens']
    if not row['recognized_phonemes'].startswith('w iː j uː z b aɪ'):
        raise ValueError('Recheck base-name timing before reusing the I02 visual segmentation')
    i02=next(item for item in events if item['id']=='I02')
    segments=[('binary',.36,1.06,.725),('decimal',1.06,1.72,1.425),('octal',1.72,2.32,2.085),('hexadecimal',2.32,dialogue['I02']['duration_s'],2.945)]
    plan['intro']['base_name_cues']=[{'row':name,'start_s':i02['start_s']+start,'end_s':i02['start_s']+end,
                                     'speech_end_s':i02['start_s']+speech_end,'basis':'Independent source CTC,20ms token grid; hold until next name.'}
                                    for name,start,end,speech_end in segments]
    plan['intro']['example']={'decimal_value':10,'representations':plan['counted_states'][10]['representations'],
                              'display_start_s':15.18,'display_end_s':25.88,'voice_event_id':'I04-TEN'}
    sound_path=ROOT/'assets/library/audio/sfx/binary/v001/SE_FINISH.wav'
    record,=(row for row in read(sound_path.with_name('generation-spec.json'))['assets'] if row['id']=='SE_FINISH')
    count=checked_wav(sound_path,record['sha256'],record['duration_s'],48000,2)
    if count%2:raise ValueError('SFX does not fit24k schedule grid')
    sound=event({'path':local_path(sound_path),'sha256':record['sha256'],'sample_frames':count//2},
                'SE_FINISH','sfx','finale',frames(plan['finale']['estimated_start_s'])+frames(.08),'SE_FINISH')
    events.append(sound)
    plan['sound_effects']=[{'id':'SE_FINISH','source_path':sound['source_path'],'source_sha256':sound['source_sha256'],
                           'estimated_start_s':sound['start_s'],'estimated_end_s':sound['end_s'],'required':True}]
    events.sort(key=lambda item:item['start_sample_24k'])
    if Counter(item['type'] for item in events)!={'number_voice':129,'dialogue':13,'sfx':1}:
        raise ValueError('Unexpected four-base event coverage')
    if len({item['id'] for item in events})!=len(events):raise ValueError('Duplicate event ID')
    if any(a['end_sample_24k']>b['start_sample_24k'] for a,b in zip(events,events[1:])):
        raise ValueError('Audio events overlap')
    duration=seconds(frames(plan['duration_s_estimate']))
    if events[0]['start_sample_24k']<frames(.8) or events[-1]['end_sample_24k']>frames(duration):
        raise ValueError('Events outside episode')
    plan.update(kind='measured-four-base-counting-timeline',status='measured-and-reviewed-speech',audio_generated=True,
                video_generated=False,duration_s=duration,fps=30,master_sample_rate_hz=48000,master_channels=2,
                measurement_status='all-number-dialogue-and-sfx-source-wavs-measured',events=events,
                measured_number_clips=numbers)
    return plan


def mix_balanced(plan,master,work,ffmpeg,staged):
    """Uniform source gain only; preserve every word's duration and waveform shape."""
    render_plan=copy.deepcopy(plan)
    inputs=dict(staged)
    replacements,gains={},{}
    for cue in plan['events']:
        original=cue['source_sha256']
        if cue['type']=='sfx' or original in replacements:continue
        source=staged.get(original,ROOT/cue['source_path'])
        if audio.file_hash(source)!=original:raise ValueError('Source changed before mix')
        with wave.open(str(source),'rb') as track:
            if (track.getnchannels(),track.getsampwidth(),track.getframerate())!=(1,2,RATE):raise ValueError('Speech PCM format changed')
            samples=array('h',track.readframes(track.getnframes()))
        peak=max(map(abs,samples))
        rms=math.sqrt(sum(v*v for v in samples)/len(samples))
        peak_db=20*math.log10(peak/32768)
        rms_db=20*math.log10(rms/32768)
        gain_db=min(max(0,-20.5-rms_db),-4.5-peak_db)
        transformed=source
        checksum=original
        if abs(gain_db)>1e-9:
            gain=10**(gain_db/20)
            transformed=work/f'balanced-{original}.wav'
            with wave.open(str(transformed),'wb') as out:
                out.setparams((1,2,RATE,0,'NONE','not compressed'))
                out.writeframes(array('h',(round(v*gain) for v in samples)).tobytes())
            checksum=audio.file_hash(transformed)
        inputs[checksum]=transformed
        replacements[original]=checksum
        gains[original]={'source_path':cue['source_path'],'gain_db':gain_db,'raw_peak_before_dbfs':peak_db,
                         'raw_rms_before_dbfs':rms_db,'raw_peak_after_dbfs':peak_db+gain_db,'raw_rms_after_dbfs':rms_db+gain_db}
    for cue in render_plan['events']:
        if cue['type']!='sfx':cue['source_sha256']=replacements[cue['source_sha256']]
    receipt=mix(render_plan,master,work,ffmpeg,inputs)
    delivery_gain=.8
    if (not -17<=receipt['loudness_lufs']+delivery_gain<=-15
            or receipt['true_peak_dbtp']>-1.95 or receipt['true_peak_dbtp']+delivery_gain>-1.15):
        raise ValueError(f'Master cannot meet the documented delivery gain budget: {receipt["loudness_lufs"]}/{receipt["true_peak_dbtp"]}')
    receipt['speech_balancing']={'method':'One uniform linear gain per unique speech source. No time stretch, pitch change or dynamics shaping.',
                                  'quiet_source_target_rms_dbfs':-20.5,'raw_source_peak_ceiling_dbfs':-4.5,'sources':gains}
    receipt['master_status']='peak-safe-intermediate-requires-delivery-gain'
    receipt['required_delivery_gain_db']=delivery_gain
    return receipt


def delivery_probe(master,work,ffmpeg,output):
    probe=work/'delivery-aac-probe.m4a'
    audio.run_ffmpeg(ffmpeg,['-v','error','-n','-i',str(master),'-af','volume=0.8dB:precision=double',
                            '-c:a','aac','-b:a','192k','-ar','48000','-ac','2',str(probe)])
    actual=measure(ffmpeg,probe)
    loudness,peak=float(actual['input_i']),float(actual['input_tp'])
    if not -17<=loudness<=-15 or peak>-1.0:
        raise ValueError(f'Actual encoded AAC probe fails delivery target: {loudness}/{peak}')
    review=output/'audio-review'
    review.mkdir(parents=True,exist_ok=True)
    destination=review/probe.name
    if destination.exists():raise FileExistsError(destination)
    probe.rename(destination)
    return {'status':'pass','path':local_path(destination),'sha256':audio.file_hash(destination),
            'gain_db':.8,'codec':'AAC192kbps,48kHz stereo','loudness_lufs':loudness,'true_peak_dbtp':peak,
            'acceptance':'Actual AAC input metrics: -17..-15LUFS and truepeak <=-1.0dBTP. Final video AAC must be checked separately.'}


def rebalance_from_timeline(timeline_path,output,work_root):
    if any((output/name).exists() for name in ('master.wav','audio-qa.json')):
        raise FileExistsError('Choose an output without an existing master or receipt')
    plan=read(timeline_path)
    manifest=ROOT/plan['speech_measurements']['path']
    if audio.file_hash(manifest)!=plan['speech_measurements']['sha256']:
        raise ValueError('The measured speech manifest changed')
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise ValueError('Registered FFmpeg is required')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fourbase-audio-rebuild-',dir=work_root) as folder:
        work=Path(folder)
        master=work/'master.wav'
        receipt=mix_balanced(plan,master,work,ffmpeg,{})
        receipt['delivery_probe']=delivery_probe(master,work,ffmpeg,output)
        receipt.update(kind='four-base-audio-master-qa',schema_version=1,timeline_sha256=audio.file_hash(timeline_path),
                       speech_measurements_sha256=audio.file_hash(manifest),timeline_path=local_path(timeline_path))
        qa=work/'audio-qa.json'
        write(qa,receipt)
        master.rename(output/master.name)
        qa.rename(output/qa.name)
    return receipt


def build(output,work_root,candidates,reports,phoneme_reports):
    if any((output/name).exists() for name in ('speech','timeline.json','master.wav','audio-qa.json')):
        raise FileExistsError('Use a fresh four-base audio destination')
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise ValueError('Registered FFmpeg is required')
    numbers=prep.clips()
    cues=prep.script_cues()
    expected={cue['id']:cue['text'] for cue in cues if cue['id']!='I04-TEN'}
    reused=adopted_dialogue(expected)
    fresh_expected={key:text for key,text in expected.items() if key not in reused}
    estimate=read(DESIGN/'estimated-timeline.json')
    if estimate['source_script_sha256']!=audio.file_hash(prep.SCRIPT):raise ValueError('Preproduction script binding is stale')
    with tempfile.TemporaryDirectory(prefix='fourbase-master-',dir=work_root) as temporary:
        work=Path(temporary)
        staging=work/'speech'
        staging.mkdir()
        final=output/'speech'
        fresh,phonemes=fresh_dialogue(candidates,reports,phoneme_reports,fresh_expected,staging,final)
        sources={clip['sha256']:staging/f'{key}.wav' for key,clip in fresh.items()}
        plan=measured_schedule(estimate,numbers,{**reused,**fresh},phonemes)
        evidence=[]
        for kind,paths in (('asr',reports),('phoneme',phoneme_reports)):
            for index,source in enumerate(paths,1):
                target=staging/f'{kind}-review-{index:02d}.json'
                shutil.copyfile(source,target)
                evidence.append({'kind':kind,'path':local_path(final/target.name),'sha256':audio.file_hash(target)})
        measurements={'schema_version':1,'measurement_status':'measured','numeric_clips':numbers,'new_dialogue':fresh,
                      'reused_dialogue':reused,'review':{'method':'Fresh unprompted Whisper tiny.en q8 and independent16kHz CTC for all new dialogue; source-bound existing acceptance for reused decimal numbers and outro.',
                        'human_listening_performed':False,'statuses':dict(Counter(row['asr_status'] for row in fresh.values())),
                        'clarity_refinements':{'I02':'Prefix We use gives a clear initial b in binary.','T64':'Prefix Both clarifies conjunction and preservesboth namedbases.'},
                        'independent_acoustic_review':'CTC confirms binary/b aɪ/, decimal/d ɛ s/, octal/ɑː k t əl/ and hexadecimal/h ɛ k s ɪ d ɛ s ɪ m əl/ in adopted sources.',
                        'evidence':evidence,'raw_isolated_warnings_retained':'Initial T64 and I02 takes are rejected; raw first-pass reports retained, not adopted.'}}
        manifest=staging/'measurements.json'
        write(manifest,measurements)
        plan['speech_measurements']={'path':local_path(final/manifest.name),'sha256':audio.file_hash(manifest)}
        timeline=work/'timeline.json'
        write(timeline,plan)
        output.mkdir(parents=True,exist_ok=True)
        staging.rename(final)
        timeline.rename(output/'timeline.json')
        sources={clip['sha256']:output/'speech'/f'{key}.wav' for key,clip in fresh.items()}
        print(json.dumps({'schedule_published':local_path(output/'timeline.json'),'timeline_sha256':audio.file_hash(output/'timeline.json'),
                          'duration_s':plan['duration_s'],'events':len(plan['events'])}),flush=True)
        master=work/'master.wav'
        receipt=mix_balanced(plan,master,work,ffmpeg,sources)
        receipt['delivery_probe']=delivery_probe(master,work,ffmpeg,output)
        receipt.update(kind='four-base-audio-master-qa',schema_version=1,timeline_sha256=audio.file_hash(output/'timeline.json'),
                       speech_measurements_sha256=audio.file_hash(final/'measurements.json'))
        report=work/'audio-qa.json'
        write(report,receipt)
        master.rename(output/'master.wav')
        report.rename(output/'audio-qa.json')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--takes',type=Path)
    parser.add_argument('--asr',type=Path,action='append',default=[])
    parser.add_argument('--phonemes',type=Path,action='append',default=[])
    parser.add_argument('--rebalance-timeline',type=Path)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=OUTPUT)
    args=parser.parse_args()
    if args.rebalance_timeline:
        if args.takes or args.asr or args.phonemes:parser.error('Rebalance mode reuses existing timeline sources')
        receipt=rebalance_from_timeline(args.rebalance_timeline.resolve(),args.out.resolve(),args.work_dir.resolve())
    else:
        if not args.takes or not args.asr or not args.phonemes:parser.error('Fresh builds require takes,ASR and phoneme reports')
        receipt=build(args.out.resolve(),args.work_dir.resolve(),read(args.takes),args.asr,args.phonemes)
    print(json.dumps({'output':local_path(args.out.resolve()),'duration_s':receipt['duration_s'],
        'master_sha256':receipt['master_sha256'],'master_loudness_lufs':receipt['loudness_lufs'],
        'master_true_peak_dbtp':receipt['true_peak_dbtp'],'required_delivery_gain_db':receipt['required_delivery_gain_db'],
        'actual_delivery_probe_loudness_lufs':receipt['delivery_probe']['loudness_lufs'],
        'actual_delivery_probe_true_peak_dbtp':receipt['delivery_probe']['true_peak_dbtp']}))


if __name__=='__main__':main()
