import array,hashlib,json,math,statistics,sys,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'design/odd-counting-v1/production-qa/v002-recheck-20261111/audio';WORK=Path('D:/temp/odd-recheck-20261111/audio')
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import frame_metrics
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def db(v):return 20*math.log10(v+1e-30)
manifest=json.loads((OUT/'fresh-aac-manifest.json').read_text());rows=[]
plan=json.loads((ROOT/'output/odd-counting-001-v002/timeline.json').read_text());events={e['id']:e for e in plan['voice_events']}
for row in manifest['numbers']:
    with wave.open(row['path'],'rb') as stream:
        rate=stream.getframerate();values=array.array('h',stream.readframes(stream.getnframes()))
    begin=round(row['event_offset_in_clip_s']*rate);n=round((row['video_event_window_s'][1]-row['video_event_window_s'][0])*rate)
    v=[s/32768 for s in values[begin:begin+n]]
    active=[i for i,x in enumerate(v) if abs(x)>.003162]
    rms=math.sqrt(sum(x*x for x in v)/len(v));peak=max(map(abs,v))
    sampled=[]
    for fraction in (.25,.4,.6,.75):
        center=round(fraction*len(v));half=round(.02*rate)
        frame=v[center-half:center+half:3]
        sampled.append(frame_metrics(frame,rate//3))
    voiced=[r['period_hz'] for r in sampled if r['periodicity']>=.65 and r['rms_dbfs']>-45 and r['low_ratio_under_1khz']>=.6]
    rows.append({'id':row['id'],'number':row['number'],'clip_sha256':row['sha256'],'event_window_s':row['video_event_window_s'],
        'duration_s':n/rate,'activity_span_s':(active[-1]-active[0]+1)/rate,
        'rms_dbfs':db(rms),'peak_dbfs':db(peak),'voiced_pitch_median_hz':statistics.median(voiced) if voiced else None,
        'sampled_spectral_centroid_median_hz':statistics.median(r['centroid_hz'] for r in sampled),'diagnostic_frames':sampled})
by={r['number']:r for r in rows};pairs=[]
for value in range(201,300,2):
    a,b=by[value-100],by[value]
    pairs.append({'older':a['number'],'new':value,'rms_delta_db':b['rms_dbfs']-a['rms_dbfs'],
        'peak_delta_db':b['peak_dbfs']-a['peak_dbfs'],'duration_ratio':b['duration_s']/a['duration_s'],
        'pitch_delta_hz':b['voiced_pitch_median_hz']-a['voiced_pitch_median_hz'] if b['voiced_pitch_median_hz'] and a['voiced_pitch_median_hz'] else None})
old=[r for r in rows if 101<=r['number']<=199];new=[r for r in rows if r['number']>=201]
summary={}
for label,group in [('all150',rows),('101to199',old),('201to299',new)]:
    summary[label]={'events':len(group),'rms_range_dbfs':[min(r['rms_dbfs'] for r in group),max(r['rms_dbfs'] for r in group)],
        'median_rms_dbfs':statistics.median(r['rms_dbfs'] for r in group),'peak_range_dbfs':[min(r['peak_dbfs'] for r in group),max(r['peak_dbfs'] for r in group)],
        'median_duration_s':statistics.median(r['duration_s'] for r in group)}
result={'video':manifest['origin']['video'],'timeline':manifest['origin']['timeline'],
    'method':'Actual final AAC event windows without exterior guards. All150 RMS/peak/duration; paired100s/200s same suffix comparison. Four evenly spaced40ms analysis windows/event downsampled by3 solely for diagnostic pitch/spectral screening; no production edits. Pitch/spectrum samples are content-dependent, not a perceptual identity guarantee.',
    'summary':summary,'boundary_199_201':[by[199],by[201]],'same_suffix_pairs':pairs,'events':rows}
with (OUT/'event-consistency.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(summary))
