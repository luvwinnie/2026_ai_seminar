"""Read-only capability probes. No model creation, server config, or real tools."""
import os
import json,time,datetime,hashlib
from pathlib import Path
import httpx

HERE=Path(__file__).resolve().parent
def save(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)

def main():
    inventory=json.loads((HERE/'inventory.json').read_text())
    results=[]
    c=httpx.Client(base_url=os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434'),timeout=120)
    for m in sorted(inventory['models'],key=lambda m:m['size']):
        if not m['selected'] or m['kind']!='generation':continue
        row={'model':m['name'],'digest':m['digest'],'probes':[]}
        for mode in ['chat','tools']:
            p={'model':m['name'],'messages':[{'role':'user','content':'日本語で「準備完了」とだけ返してください。' if mode=='chat' else 'echo_textツールを使い、textに「確認」を指定してください。'}],
               'stream':False,'keep_alive':'2m','options':{'temperature':0,'num_ctx':32768,'num_predict':256}}
            if 'thinking' in m['capabilities']:p['think']='low' if m['name'].startswith('gpt-oss:') else False
            if mode=='tools':p['tools']=[{'type':'function','function':{'name':'echo_text','description':'指定した文字列を返すテスト用ツール','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}}]
            t=time.perf_counter()
            try:
                r=c.post('/api/chat',json=p)
                result={'mode':mode,'http_status':r.status_code,'elapsed_s':time.perf_counter()-t,'request':p,'response':r.json()}
            except Exception as e:result={'mode':mode,'elapsed_s':time.perf_counter()-t,'request':p,'error':repr(e)}
            row['probes'].append(result)
            print(m['name'],mode,result.get('http_status'),result.get('response',{}).get('error',''),flush=True)
        row['runtime']=c.get('/api/ps').json()
        results.append(row)
        save(HERE/'preflight.json',{'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'models':results})
    print('DONE',len(results),flush=True)

if __name__=='__main__':main()
