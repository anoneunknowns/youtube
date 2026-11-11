import array,hashlib,json,sys,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'output/odd-counting-001-v002/speech'
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import frame_metrics
manifest=json.loads((OUT/'initial-measurements-v001.json').read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def screen(row):
    p=Path(row['path']);assert sha(p)==row['sha256']
    with wave.open(str(p),'rb') as f:
        rate=f.getframerate();raw=array.array('h',f.readframes(f.getnframes()))
    vals=[v/32768 for v in raw];frames=[]
    for tick in range(29):
        center=round(tick*.01*rate);half=round(.01*rate)
        frames.append({'time_s':tick*.01,**frame_metrics(vals[max(0,center-half):center+half],rate)})
    voiced=[r for r in frames if r['rms_dbfs']>-45 and r['low_ratio_under_1khz']>=.6 and r['periodicity']>=.6]
    strong=[r for r in frames if r['rms_dbfs']>-45 and r['high_ratio_2khz_up']>=.35 and r['periodicity']<.4]
    weak=[r for r in frames if r['rms_dbfs']>-65 and r['high_ratio_2khz_up']>=.35 and r['periodicity']<.4]
    first=strong[0]['time_s'] if strong else None
    weakfirst=weak[0]['time_s'] if weak else None
    prefix=[r for r in voiced if first is not None and r['time_s']<first]
    weakprefix=[r for r in voiced if weakfirst is not None and r['time_s']<weakfirst]
    return {'id':row['id'],'number':row.get('number'),'text':row['spoken_text'],'source_sha256':row['sha256'],
       'frames':frames,'first_strong_frication_s':first,'first_weak_frication_s':weakfirst,
       'voiced_prefix_s':len(prefix)*.01,'voiced_before_weak_frication_s':len(weakprefix)*.01,
       'voiced_prefix_times_s':[r['time_s'] for r in prefix],
       'prefix_max_rms_dbfs':max((r['rms_dbfs'] for r in prefix),default=None)}
heads=('three','thirteen','thirty','four','five','fifteen','forty','fifty','six','seven','sixty','seventy','from','thanks')
rows=[r for r in manifest['numbers']+manifest['dialogue'] if r['spoken_text'].lower().startswith(heads)]
results=[screen(r) for r in rows]
flags=[{k:r[k] for k in ('id','number','text','voiced_prefix_s','voiced_before_weak_frication_s','prefix_max_rms_dbfs','first_strong_frication_s','first_weak_frication_s')} for r in results if r['voiced_prefix_s']>=.03]
report={'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(OUT/'initial-measurements-v001.json'),
 'method':'Fresh source PCM,20ms windows10ms hop first280ms. Strong voicing RMS>-45,periodicity>=.6,lowband>=.6 before strong highband aperiodic frication. Weak frication threshold-65 helps interpret falsely late strong-onset detections. No lexical recognition used in signal decisions.',
 'screened':len(results),'results':results,'candidates':flags,'scope':'Review heuristic; a flagged initial interval requires individual inspection, not automatic rejection or acceptance.'}
with (OUT/'initial-fricative-screen-v002.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'screened':len(results),'candidates':flags}))

