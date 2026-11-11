from array import array
import json,math
from pathlib import Path

work=Path(__file__).parent
out=Path('D:/codex_projects/youtube/output/four-base-counting-001-v002-to-200')
plan=json.loads((out/'timeline.json').read_text(encoding='utf-8'))
def load(path):
    a=array('h')
    with path.open('rb') as f:a.fromfile(f,path.stat().st_size//2)
    return a
a=load(work/'aac-stereo.s16le')
b=load(work/'master-gained-stereo.s16le')
records=[]
for e in plan['events']:
    begin,end=round(e['start_s']*48000)*2,round(e['end_s']*48000)*2
    ls,rs,ref=a[begin:end:2],a[begin+1:end:2],b[begin:end:2]
    ll=sum(x*x for x in ls);rr=sum(x*x for x in rs);re=sum(x*x for x in ref)
    lr=sum(x*y for x,y in zip(ls,rs));lre=sum(x*y for x,y in zip(ls,ref));rre=sum(x*y for x,y in zip(rs,ref))
    diff=sum((x-y)**2 for x,y in zip(ls,rs))
    records.append({'id':e['id'],'type':e['type'],'lr_correlation':lr/math.sqrt(ll*rr),
      'left_reference_correlation':lre/math.sqrt(ll*re),'right_reference_correlation':rre/math.sqrt(rr*re),
      'channel_level_delta_db':10*math.log10(ll/rr),'side_to_mid_rms_db':10*math.log10(diff/(ll+rr+2*lr)) if diff else -999,
      'channel_max_difference_pcm16':max(abs(x-y) for x,y in zip(ls,rs))})
global_ll=sum(x*x for x in a[::2]);global_rr=sum(x*x for x in a[1::2]);global_lr=sum(x*y for x,y in zip(a[::2],a[1::2]))
report={'global_lr_correlation':global_lr/math.sqrt(global_ll*global_rr),'maximum_channel_level_delta_db':max(abs(r['channel_level_delta_db']) for r in records),
    'minimum_left_reference_correlation':min(r['left_reference_correlation'] for r in records),'minimum_right_reference_correlation':min(r['right_reference_correlation'] for r in records),'records':records}
(work/'stereo-difference-analysis.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='records'}))
print(json.dumps(sorted(records,key=lambda r:r['lr_correlation'])[:8]))
