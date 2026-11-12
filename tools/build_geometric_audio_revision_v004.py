"""Revise only D016 to use the reviewed clear Six; preserve all old media/evidence."""
from pathlib import Path
import array,copy,json,math,os,shutil,subprocess,wave
from review_fibonacci_speech import review,local,sha
from review_fibonacci_acoustics import review as acoustic_review
from build_geometric_audio import sources,make_plan,validate,deliveries
from build_fibonacci_episode import probe_loudness
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'output/geometric-sequence-counting-001-v001/audio-build/revision-v003'
OUT=ROOT/'output/geometric-sequence-counting-001-v002/audio-build'
DETAIL=ROOT/'design/geometric-sequence-counting-v1/recheck-20261112-v002/audio-detail'
def read(p):return json.loads(Path(p).read_text())
def ref(p):return {'path':local(p),'sha256':sha(p)}
def write(p,d):
 with Path(p).open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
def prepare():
 OUT.mkdir(parents=True,exist_ok=False)
 candidate=read(DETAIL/'replacement-candidate-v002.json'); original_manifest=read(BASE/'measurements.json');old_gate=read(BASE/'speech-acceptance.json')
 assert candidate['sha256']=='0b5ee47e429095e7bb1c8846b710a56334d6e2c3d6d395aa6990b0a42f2d0161'
 assert read(DETAIL/'replacement-v002-ctc.json')['results'][0]['recognized_phonemes']=='t uː s ɪ k s eɪ t iː n f ɪ f t i f ɔːɹ'
 assert all(b['jump_pcm16']==0 for b in candidate['boundaries']) and candidate['clipped_samples']==0
 destination=OUT/'D016-clear-six.wav';shutil.copyfile(candidate['path'],destination);assert sha(destination)==candidate['sha256']
 manifest=copy.deepcopy(original_manifest)
 for r in manifest['numbers']+manifest['dialogue']:
  p=(BASE/r['path']).resolve();r['path']=os.path.relpath(p,OUT)
  if r['id']=='D016':
   r.update(path=destination.name,sha256=candidate['sha256'],duration_s=candidate['duration_s'],sample_frames_24k=candidate['sample_frames_24k'],
     candidate_take_id='D016-word-replacement-candidate-v002',selection_reason='Resolve vowel ambiguity in list Six with independently clear accepted N002. Preserve both source lineages and focused new whole-line evidence.',
     generation={'provider':'provenance-tracked-edit-of-local-kokoro','model_id':'onnx-community/Kokoro-82M-v1.0-ONNX','voice_id':'af_heart','speed':.98,'dtype':'fp32','status':'new-reviewed-edited-source','operation':ref(DETAIL/'replacement-candidate-v002.json')})
 manifest.update(adoption_status='revision-v004-one-new-D016-plus109exact-source-adoptions-inherited',selection_evidence=[ref(BASE/'measurements.json'),ref(BASE/'speech-acceptance.json'),ref(DETAIL/'replacement-candidate-v002.json'),ref(DETAIL/'replacement-v002-asr.json'),ref(DETAIL/'replacement-v002-ctc.json')])
 write(OUT/'measurements.json',manifest);binding=sha(OUT/'measurements.json')
 for name,newname in [('asr.json','replacement-v002-asr.json'),('phonemes.json','replacement-v002-ctc.json')]:
  data=read(BASE/name);fresh=read(DETAIL/newname)['results'][0]
  data['results']=[fresh if r['id']=='D016' else r for r in data['results']]
  data.update(kind='geometric-v004-exact-source-inherited-plus-one-new-inference',source_manifest=str((OUT/'measurements.json').resolve()),source_manifest_sha256=binding,
   source_inference_counts={'inherited_adopted_source_records':109,'newly_inferred_changed_source_records':1},composition_method='Fresh recognition for changed D016 exact bytes,109 prior adopted records whose source SHA is unchanged. No repeat inference claim for those109.',composed_from=[ref(BASE/name),ref(DETAIL/newname),ref(BASE/'speech-acceptance.json')])
  if name=='asr.json':
   data['warnings']=[r for r in data['results'] if r['status']!='asr-match'];data['summary'].update(asr_matches=110-len(data['warnings']),warnings=len(data['warnings']))
  write(OUT/name,data)
 single_acoustic=acoustic_review(DETAIL/'replacement-v002-manifest.json',DETAIL/'replacement-v002-ctc.json');write(OUT/'new-D016-acoustics.json',single_acoustic)
 ac=read(BASE/'acoustics.json');ac['source_manifest_sha256']=binding;ac['source_phonemes_sha256']=sha(OUT/'phonemes.json');ac['onset_waveform']['source_manifest_sha256']=binding
 for label,parent in [('results','onset_waveform'),('terminal_results',None)]:
  fresh=(single_acoustic[parent][label] if parent else single_acoustic[label])[0]
  if parent:ac[parent][label]=[fresh if r['id']=='D016' else r for r in ac[parent][label]]
  else:ac[label]=[fresh if r['id']=='D016' else r for r in ac[label]]
 ac.update(kind='geometric-v004-one-new-acoustic-record-plus109inherited',record_scope={'new':['D016'],'inherited_unchanged_SHA':109},composed_from=[ref(BASE/'acoustics.json'),ref(OUT/'new-D016-acoustics.json')]);write(OUT/'acoustics.json',ac)
 decisions=read(BASE/'individual-decisions.json');selected={r['id']:r for r in manifest['numbers']+manifest['dialogue']}
 for r in decisions['results']:
  if r['id']=='D016':r.update(source_sha256=selected['D016']['sha256'],decision='accepted-after-fresh-whole-line-recognition-seam-level-and-vowel-review',notes=[
   'Resolve the former list Six vowel ambiguity with the separately adopted clear N002 sɪks. This is a new edited D016, not an inherited approval for its changed bytes; the old line remains preserved. No definitive claim that every listener heard the old word incorrectly.',
   'Fresh whole-line CTC t uː s ɪ k s eɪ t iː n f ɪ f t i f ɔːɹ preserves all four list values. Fresh isolated ASR2-6-1854 has adjacent eighteen/fifty-four digit concatenation; the complete phoneme sequence distinguishes them and Six isɪ.',
   'Documented2ms join fades,0PCM16 jumps at both seams,0 clipping, and per-word level match to already adopted N002. No time stretch, compression or limiting. Measured line grows0.08s; subsequent cue times are recomputed, not padded to the old length.',
   'Agent review of lexical, phonetic and waveform evidence. No human full-episode listening or perfect-articulation claim.'])
  else:
   assert r['source_sha256']==selected[r['id']]['sha256'];r['decision']='inherited-adoption-for-unchanged-exact-source-SHA';r['notes']=['Inherited exact source evidence/adoption, not newly inferred in revision-v004.']+r['notes']
 decisions.update(kind='geometric-v004-one-new-D016-plus109inherited-source-decisions',source_manifest_sha256=binding,supporting_evidence=[ref(BASE/'speech-acceptance.json'),ref(BASE/'measurements.json'),ref(DETAIL/'replacement-candidate-v002.json'),ref(DETAIL/'replacement-v002-asr.json'),ref(DETAIL/'replacement-v002-ctc.json'),ref(OUT/'new-D016-acoustics.json')]);write(OUT/'individual-decisions.json',decisions)
 gate=review(OUT/'measurements.json',OUT/'asr.json',OUT/'phonemes.json',OUT/'acoustics.json',OUT/'individual-decisions.json');assert gate['accepted'] and not gate['unresolved']
 gate.update(kind='hash-bound-geometric-source-speech-revision-v004',source_inference_counts={'inherited_adopted_source_records':109,'newly_inferred_changed_source_records':1});gate['inputs']['revision_implementation']=ref(Path(__file__));write(OUT/'speech-acceptance.json',gate)
 plan=make_plan(sources(OUT/'measurements.json',OUT/'speech-acceptance.json'),True);plan.update(revision_id='geometric-sequence-audio-v004',speech_manifest=ref(OUT/'measurements.json'),speech_acceptance=ref(OUT/'speech-acceptance.json'),base_audio_revision={'timeline':ref(BASE/'timeline.json'),'master':ref(BASE/'master.wav'),'source_gate':ref(BASE/'speech-acceptance.json')})
 write(OUT/'draft-timeline.json',plan)
 write(OUT/'selection.json',{'kind':'D016-clear-six-revision-v004','changed_source':'D016','source_sha256':candidate['sha256'],'new_duration_s':candidate['duration_s'],'duration_increase_s':.08,'unchanged_sources':109,'source_gate':ref(OUT/'speech-acceptance.json'),'timeline':ref(OUT/'draft-timeline.json'),'schedule':validate(plan),'old_media_and_records_preserved':True,'ambiguity_correction_not_certainty_claim':True})
 print(json.dumps({'stage':'source-gate-and-draft-ready','timeline':ref(OUT/'draft-timeline.json'),'source_gate':ref(OUT/'speech-acceptance.json'),'duration_s':plan['duration_s'],'duration_frames':plan['duration_frames']}),flush=True)
 return plan

def mix(plan):
 ffmpeg=str(ROOT/'.venv/bin/ffmpeg');old=read(BASE/'timeline.json');old_events={r['id']:r for r in old['voice_events']};common=old['master']['common_gain_db'];work=OUT/'.work/preserved-adopted-scalars';work.mkdir(parents=True)
 data=bytearray(round(plan['duration_s']*48000)*6);measurements=[]
 for e in plan['voice_events']:
  prev=old_events[e['id']];assert e['source_sha256']==prev['source_sha256'] or e['id']=='D016'
  with wave.open(str(ROOT/e['source_path'])) as w:a=array.array('h',w.readframes(w.getnframes()))
  e.update(source_peak_dbfs=20*math.log10(max(abs(x) for x in a)/32768),source_rms_dbfs=20*math.log10(math.sqrt(sum(x*x for x in a)/len(a))/32768),mix_gain_db=prev['mix_gain_db'],per_source_truepeak_calibration_db=prev['per_source_truepeak_calibration_db'],aac_codec_calibration_gain_db=prev.get('aac_codec_calibration_gain_db',0))
  raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(ROOT/e['source_path']),'-af',f'volume={e["mix_gain_db"]:.12f}dB:precision=double','-ar','48000','-ac','2','-c:a','pcm_s24le','-f','s24le','pipe:1'])
  assert len(raw)==e['sample_frames_24k']*12;start=e['start_sample_24k']*12;data[start:start+len(raw)]=raw
  measurements.append({'id':e['id'],'source_sha256':e['source_sha256'],'mix_gain_db':e['mix_gain_db'],'same_adopted_gain_as_v003':True})
 raw=work/'balanced.wav'
 with wave.open(str(raw),'wb') as w:w.setnchannels(2);w.setsampwidth(3);w.setframerate(48000);w.writeframes(data)
 before=probe_loudness(ffmpeg,raw);master=OUT/'master.wav';subprocess.run([ffmpeg,'-v','error','-n','-i',str(raw),'-af',f'volume={common:.12f}dB:precision=double','-c:a','pcm_s24le',str(master)],check=True);after=probe_loudness(ffmpeg,master)
 assert -17<=float(after['input_i'])<=-15 and float(after['input_tp'])<=-1.8,after
 receipt={'kind':'geometric-v004-unchanged-adopted-constant-scalars-new-master-gate','accepted':True,'criteria':{'integrated_lufs':[-17,-15],'true_peak_max_dbtp':-1.8},'base_timeline':ref(BASE/'timeline.json'),'new_source_gate':ref(OUT/'speech-acceptance.json'),'source_gains':measurements,'common_gain_db':common,'before':before,'after':after,'master':ref(master),'processing':'Same adopted per-source and common constant scalars. Fresh final PCM loudness/truepeak/sample count. D016 source contains documented local word edit; other109 sources unchanged. No time stretch/compression/limiter; all source durations are measured.'}
 write(OUT/'pcm-level-acceptance.json',receipt)
 level={'path':local(master),'sha256':sha(master),'sample_rate_hz':48000,'channels':2,'sample_width_bits':24,'duration_s':plan['duration_s'],'source_gain_db':common,'common_gain_db':common,'per_source_balancing_applied':True,'source_gains':[{'id':e['id'],'source_sha256':e['source_sha256'],'gain_db':e['mix_gain_db']} for e in plan['voice_events']],'master_level_acceptance':local(OUT/'pcm-level-acceptance.json'),'before':before,'after':after,'method':receipt['processing']}
 plan['master']=plan['audio']=plan['master_audio']=level;write(OUT/'timeline.json',plan);deliveries(plan,OUT)
 write(OUT/'build-record.json',{'status':'revision-v004-D016-clear-six-accepted-master-complete','timeline':ref(OUT/'timeline.json'),'master':level,'source_gate':plan['speech_acceptance'],'source_manifest':plan['speech_manifest'],'validation':validate(plan),'changed_source':'D016','other109_source_evidence_inherited':True,'builder':ref(Path(__file__))});print(json.dumps({'stage':'master-complete','timeline':ref(OUT/'timeline.json'),'master':level['after'],'duration_s':plan['duration_s'],'frames':plan['duration_frames']}),flush=True)
if __name__=='__main__':mix(prepare())
