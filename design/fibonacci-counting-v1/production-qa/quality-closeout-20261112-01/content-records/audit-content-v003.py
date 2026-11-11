"""Standalone content audit. No builder, renderer or video verifier imports."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,math,re,wave

ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'output/fibonacci-counting-001-v003'
HERE=Path(__file__).parent
checks=[]
def check(name,condition,**facts):
    checks.append(dict(name=name,passed=bool(condition),**facts))
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def close(a,b):return abs(a-b)<1e-8
def fib(n):
    if not n:return (0,1)
    a,b=fib(n//2);c=a*(2*b-a);d=a*a+b*b
    return (d,c+d) if n%2 else (c,d)
def matrix(n):
    def mul(a,b):return tuple(sum(a[r*2+k]*b[k*2+c] for k in range(2)) for r in range(2) for c in range(2))
    a=(1,0,0,1);b=(1,1,1,0)
    while n:
        if n&1:a=mul(a,b)
        b=mul(b,b);n//=2
    return a[1]
SMALL='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS='zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()
def triad(n):
    if n<20:return SMALL[n]
    if n<100:return TENS[n//10]+('-'+SMALL[n%10] if n%10 else '')
    return SMALL[n//100]+' hundred'+(' '+triad(n%100) if n%100 else '')
def cardinal(n):
    if not n:return 'zero'
    parts=[]
    for unit,name in [(10**9,'billion'),(10**6,'million'),(1000,'thousand'),(1,'')]:
        count,n=divmod(n,unit)
        if count:parts.append(triad(count)+(' '+name if name else ''))
    return ' '.join(parts)
def parse_cardinal(text):
    total=group=0
    for w in text.replace('-',' ').split():
        if w in SMALL:group+=SMALL.index(w)
        elif w in TENS:group+=10*TENS.index(w)
        elif w=='hundred':group*=100
        elif w in ('thousand','million','billion'):
            unit={'thousand':1000,'million':10**6,'billion':10**9}[w];total+=group*unit;group=0
        else:raise ValueError(w)
    return total+group
def ms(text):
    h,m,s,z=map(int,re.split('[:,]',text));return ((h*60+m)*60+s)*1000+z

top=read(OUT/'timeline.json');base=read(ROOT/top['source_timeline']['path'])
old=read(ROOT/'output/fibonacci-counting-001-v001/timeline.json')
script=read(ROOT/'design/fibonacci-counting-v1/narration.json')
lines=read(ROOT/'design/fibonacci-counting-v1/count-lines.json')
motion=read(OUT/'character-motion.json')
prior=read(ROOT/'design/fibonacci-counting-v1/production-qa/recheck-20261112-01/content/content-review.json')
events=base['voice_events'];byid={e['id']:e for e in events};oldbyid={e['id']:e for e in old['voice_events']}
values=[fib(n)[0] for n in range(43)]
check('Independent fast doubling and matrix power agree F0..F42',all(values[n]==matrix(n) for n in range(43)))
check('Sum identity agrees with F42-1',sum(values[:41])==values[42]-1)
check('Zero, two distinct ones, 41 terms and final value',values[:4]==[0,1,1,2] and len(base['counted_states'])==41 and values[40]==102334155)
check('First value strictly above 100 million is F40',next(n for n,v in enumerate(values) if v>10**8)==40)
check('First value at least one million is F31',next(n for n,v in enumerate(values) if v>=10**6)==31)
check('Authored 104 IDs and measured sequence',len(script)==len(events)==104 and [e['id'] for e in events]==[e['id'] for e in script])
check('Categories 8 introductory /41 counts /39 expressions /12 replay /4 outro',sum(e['id'].startswith('I') for e in events)==8 and sum(e['id'].startswith('N') for e in events)==41 and sum(e['id'].startswith('E') for e in events)==39 and sum(e['id'].startswith('T') for e in events)==12 and sum(e['id'].startswith('O') for e in events)==4)
terms=[];handoffs=[];carry_cases=[]
for n,(line,state) in enumerate(zip(lines,base['counted_states'])):
    v=values[n];word=cardinal(v);event=byid[f'N{n:03d}']
    check(f'F{n}: table value, ordinal, English, display and state',line['index']==n and line['ordinal']==n+1 and line['value']==v and line['display_value']==f'{v:,}' and line['text']==word and state['value']==v and state['index']==n and state['ordinal']==n+1 and state['spoken_text']==word and event['text']==word and parse_cardinal(word)==v)
    check(f'F{n}: display and reading 120ms before result speech',close(state['result_start_s'],event['start_s']-.12) and close(state['display_start_s'],event['start_s']-.12))
    if n>=2:
        a,b=values[n-2:n];e=byid[f'E{n:03d}'];expected=f'{cardinal(a)} plus {cardinal(b)} equals'
        check(f'F{n}: independently generated addition operands, indices and expression prefix',a+b==v and line['a']==a and line['b']==b and line['a_index']==n-2 and line['b_index']==n-1 and line['equation_text']==f'{a:,} + {b:,} = {v:,}' and line['formula_prefix_text']==expected and e['text']==expected and state['operands']==[a,b])
        check(f'F{n}: prefix ends 160ms before result and no appended result',close(event['start_s']-e['end_s'],.16) and e['text'].endswith(' equals') and close(state['formula_start_s'],e['start_s']) and close(state['formula_end_s'],e['end_s']))
    else:check(f'F{n}: initial value has no fabricated sum',state['formula_start_s'] is None and state['operands']==[])
    if 2<=n<40:
        nextstate=base['counted_states'][n+1]
        check(f'F{n}: next pair preserves b,c and their distinct positions',nextstate['operands']==[values[n-1],v] and nextstate['index']==n+1)
        checkpoint=next((x for x in base['teaching'] if x['index']==n),None)
        anchor=byid[checkpoint['voice_event_ids'][-1]]['end_s'] if checkpoint else event['end_s']
        offset=.6 if checkpoint else .35
        check(f'F{n}: handoff duration and anchor',close(state['transfer_start_s'],anchor+offset) and close(state['transfer_end_s'],anchor+offset+1.2))
        check(f'F{n}: next expression start after ordinary 2s or replay 2.6s',close(nextstate['formula_start_s'],anchor+(2.6 if checkpoint else 2)))
        handoffs.append(dict(index=n,pair=[values[n-1],v],start_s=state['transfer_start_s'],end_s=state['transfer_end_s']))
    terms.append(dict(n=n,value=v,ordinal=n+1,English=word,passed=True))
for teaching in base['teaching']:
    ids=teaching['voice_event_ids'];n=teaching['index']
    check(f'Replay after F{n}: two explanations and progress unchanged',len(ids)==2 and all(byid[i]['kind']=='explanation' and byid[i]['index']==n for i in ids) and close(byid[ids[0]]['start_s'],byid[f'N{n:03d}']['end_s']+.6) and close(byid[ids[1]]['start_s'],byid[ids[0]]['end_s']+.6))
for n in (8,13,18):
    a,b=values[n-2:n];carry=0;steps=[];reconstructed=0
    for power in range(len(str(values[n]))):
        x=(a//10**power)%10;y=(b//10**power)%10;incoming=carry;total=x+y+carry;carry,digit=divmod(total,10)
        reconstructed+=digit*10**power
        check(f'F{n} decimal column {power}: digit and carry into next adjacent place',digit==(values[n]//10**power)%10 and carry in (0,1))
        steps.append(dict(power=power,a_digit=x,b_digit=y,carry_in=incoming,column_total=total,written_digit=digit,carry_out=carry,carry_target_power=power+1 if carry else None))
    check(f'F{n}: decimal columns reconstruct full result',reconstructed==values[n] and carry==0)
    carry_cases.append(dict(index=n,a=a,b=b,result=values[n],steps_ones_first=steps))
all_cues=[];delta=8182/24000
for authored,e in zip(script,events):
    path=ROOT/e['source_path'];previous=oldbyid[e['id']]
    with wave.open(str(path)) as wav:params=(wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())
    check(e['id']+': authored text and measured PCM binding',e['text']==authored['text'] and e['spoken_text']==authored['text'] and sha(path)==e['source_sha256'] and params[:3]==(1,2,24000) and params[3]==e['sample_frames_24k'] and close(params[3]/24000,e['duration_s']) and close(e['end_s']-e['start_s'],params[3]/24000))
    if e['id']=='N024':
        check('N024 is a whole new source; length increases exactly8182 samples',e['source_sha256']!=previous['source_sha256'] and params[3]-previous['sample_frames_24k']==8182 and close(e['start_s'],previous['start_s']) and close(e['end_s'],previous['end_s']+delta))
    else:
        shift=delta if previous['start_s']>oldbyid['N024']['start_s'] else 0
        check(e['id']+': original source retained and timing changed only by N024 delta',e['source_sha256']==previous['source_sha256'] and e['sample_frames_24k']==previous['sample_frames_24k'] and close(e['start_s'],previous['start_s']+shift) and close(e['end_s'],previous['end_s']+shift))
    all_cues.append(dict(id=e['id'],text=e['text'],source_sha256=e['source_sha256'],source_frames_24k=params[3],start_s=e['start_s'],end_s=e['end_s']))
check('No voice overlap',all(a['end_s']<=b['start_s'] for a,b in zip(events,events[1:])))
check('Measured speech sum plus107.04s equals new timeline',close(sum(e['duration_s'] for e in events)+107.04,base['duration_s']))
check('Frame grid is ceiling of timeline seconds',base['duration_frames']==math.ceil(base['duration_s']*30)==16104)
for field in ('voice_events','events','counted_states','visual_segments','scenes','duration_s','duration_frames','master_audio','timing','teaching','intro','finale'):
    check('Top/base invariant: '+field,top[field]==base[field])
check('Hash DAG: immutable audio base -> motion -> top',top['source_timeline']==motion['source_timeline'] and top['source_timeline']['sha256']==sha(ROOT/top['source_timeline']['path']) and top['character_motion']['sha256']==sha(OUT/'character-motion.json'))
captions=[]
blocks=(OUT/'english-captions.srt').read_text().strip().split('\n\n')
check('Two subtitle aliases are byte identical and104 events',sha(OUT/'english-captions.srt')==sha(OUT/'subtitles.srt') and len(blocks)==104)
for e,block in zip(events,blocks):
    number,times,*text=block.splitlines();a,b=times.split(' --> ')
    ok=abs(ms(a)-e['start_s']*1000)<=.500001 and abs(ms(b)-e['end_s']*1000)<=.500001 and ' '.join(text)==e['text']
    check(e['id']+': subtitle text and both rounded boundaries',ok)
    captions.append(dict(id=e['id'],start_ms=ms(a),end_ms=ms(b),text=' '.join(text),passed=ok))
chapters=[]
for line in (OUT/'chapters.txt').read_text().strip().splitlines():
    time,title=line.split(' ',1);parts=list(map(int,time.split(':')));seconds=parts[-1]+parts[-2]*60+(parts[-3]*3600 if len(parts)==3 else 0)
    chapters.append(dict(time=time,seconds=seconds,title=title))
check('Seven chapter starts, from zero, increasing and all at least10seconds',len(chapters)==7 and chapters[0]['seconds']==0 and all(b['seconds']-a['seconds']>=10 for a,b in zip(chapters,chapters[1:])) and base['duration_s']-chapters[-1]['seconds']>=10)
chapter_anchors=[0,base['counted_states'][0]['cycle_start_s'],byid['T008a']['start_s'],base['counted_states'][21]['formula_start_s'],base['counted_states'][31]['formula_start_s'],base['counted_states'][40]['formula_start_s'],base['finale']['start_s']]
for c,anchor in zip(chapters,chapter_anchors):check('Chapter '+c['time']+' begins within1s of intended scene',abs(c['seconds']-anchor)<1,anchor_s=anchor,title=c['title'])
title=(OUT/'youtube-title.txt').read_text().strip();description=(OUT/'youtube-description.txt').read_text().strip()
check('Metadata title endpoint and upload concatenation','102,334,155' in title and (OUT/'upload-details.txt').read_text().strip()==title+'\n\n'+description)
check('Description all chapters and mathematically correct endpoint/recurrence',all((c['time']+' '+c['title']) in description for c in chapters) and 'all 41 terms through F40 = 102,334,155' in description and '39 additions' in description and 'Fn = F(n-2) + F(n-1)' in description)
check('No music/effects claim agrees with timeline',base['bgm'] is False and base['sound_effects']==[] and 'No background music or sound effects.' in description)
check('Educational claims are word-for-word unchanged from prior audited narration',all(e['text']==oldbyid[e['id']]['text'] for e in events) and prior['passed'])
claims=prior['educational_claim_review']
inputs=[OUT/name for name in ['paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4','timeline.json','character-motion.json','english-captions.srt','subtitles.srt','chapters.txt','youtube-title.txt','youtube-description.txt','upload-details.txt']]
inputs += [ROOT/top['source_timeline']['path'],ROOT/base['master_audio']['path']]
inputs += [ROOT/'design/fibonacci-counting-v1/narration.json',ROOT/'design/fibonacci-counting-v1/count-lines.json',Path(__file__)]
failures=[c for c in checks if not c['passed']]
report=dict(schema_version=1,kind='independent-fibonacci-v003-quality-closeout-content-review',checked_at_utc=datetime.now(timezone.utc).isoformat(),passed=not failures,status='PASS' if not failures else 'FAIL',video_sha256=sha(inputs[0]),inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p),bytes=p.stat().st_size) for p in inputs],methods=['Independent fast doubling and2x2 matrix powers, with independent US cardinal generation and inverse parser.','Fresh original PCM file SHA/header/length audit of all104 cues, SRT104 text and both boundaries, seven chapter anchors, metadata and immutable-base DAG.','Full source-text review is unchanged from prior independently reviewed narration; all mathematical claims recalculated here. No renderer/builder/verifier imported.'],summary=dict(checks=len(checks),failed=len(failures),terms=41,additions=39,narration_cues=104,subtitle_cues=104,chapters=7,handoffs=len(handoffs),carry_columns=sum(len(c['steps_ones_first']) for c in carry_cases),changed_source_id='N024',changed_source_delta_samples_24k=8182,other_original_sources_reused=103),all_terms=terms,all_cues=all_cues,handoffs=handoffs,carry_cases=carry_cases,caption_results=captions,chapter_results=chapters,educational_claim_review=claims,informational_observations=prior['informational_observations'],checks=checks,failures=failures,limitations=['This is a content/text/PCM-binding audit; pronunciation and final AAC acoustic quality are checked by separate fresh inference and waveform reports.','Motion/rendered pixels are checked by separate independent motion and generic video QA. This record does not claim a human continuous viewing or listening session.','The two previously documented preproduction visual-cue differences remain historical planning notes; rendered vertical carrying/final value scene are the approved implementation.'])
(HERE/'fresh-v003-content-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
(HERE/'fresh-v003-content-review.txt').write_text(f'Fibonacci v003 内容再監査: {report["status"]}\n検査 {len(checks)}件、不合格 {len(failures)}件。\nF0..F40 全41項、39式、104原音/字幕、7章、38受渡し、9繰上がり列を独立再検算。\nN024全文新takeのみ8182samples長く、他103原音SHAは同一。後続時刻の差分、top/base/motionのSHA結合も確認。\n数学/英語本文は変更なく教育上の新しい不正確な主張なし。過去の企画cue差分2件は履歴として保持。\n完成MP4 SHA: '+report['video_sha256']+'\n音声の発音・最終AACと描画の最終合格は各専用の新規検査へ分離。全編人視聴・試聴の記録ではない。\n')
print(json.dumps(dict(passed=report['passed'],checks=len(checks),failures=failures),ensure_ascii=False))
raise SystemExit(bool(failures))
