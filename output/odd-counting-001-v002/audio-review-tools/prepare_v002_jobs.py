import json
from pathlib import Path
OUT=Path('D:/codex_projects/youtube/output/odd-counting-001-v002/speech')
OUT.mkdir(parents=True,exist_ok=True)
ones=('zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen')
tens=('','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety')
def words(n):
    if n<20:return ones[n]
    if n<100:return tens[n//10]+('-'+ones[n%10] if n%10 else '')
    return ones[n//100]+' hundred'+(' '+words(n%100) if n%100 else '')
jobs=[{'id':'I07','text':"We'll count all the way to two hundred ninety-nine."},
      {'id':'F02','text':'We counted by twos, all the way to two hundred ninety-nine!'}]
jobs += [{'id':f'N{n:03d}','number':n,'text':words(n)} for n in range(201,300,2)]
with (OUT/'generation-jobs.json').open('x',encoding='utf-8') as f:json.dump(jobs,f,indent=2);f.write('\n')
print(json.dumps({'jobs':len(jobs),'out':str(OUT/'generation-jobs.json')}))
