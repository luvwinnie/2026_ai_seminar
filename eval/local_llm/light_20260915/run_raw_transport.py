"""Post-hoc full task evaluation of the tag whose chat renderer is unavailable.

Uses raw generation and an explicitly described JSON tool adapter. Main native
results stay frozen. All original 50 cases, same scoring and execution boundary.
"""
import asyncio,copy,hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path
import httpx
from fastmcp import Client
import run_generation as g
from preflight import save

HERE=Path(__file__).resolve().parent
MODEL='qwen3.8:27b-mtp-q4_K_M'
TEMPLATE_NOTE='ChatML role delimiters; assistant prefix ends with an empty closed <think> block. Native tool parser is bypassed; JSON adapter instructions are visible in each initial system message.'

def render(messages):
    return ''.join('<|im_start|>'+m['role']+'\n'+m.get('content','')+'<|im_end|>\n' for m in messages)+'<|im_start|>assistant\n<think>\n\n</think>\n\n'

async def raw_api(http,model,messages,defs,cap,max_tokens,timeout):
    assert not defs,'Raw transport must use the explicit JSON adapter, not native tools'
    payload={'model':model,'prompt':render(messages),'raw':True,'stream':False,'keep_alive':'3m',
             'options':{k:g.SETTINGS[k] for k in ['temperature','seed','num_ctx']}}
    payload['options']['num_predict']=max_tokens
    start=time.perf_counter();response=await http.post('/api/generate',json=payload,timeout=timeout)
    if response.status_code!=200:raise RuntimeError(f'HTTP {response.status_code}: {response.text[:1600]}')
    raw=response.json()
    if raw.get('error'):raise RuntimeError(str(raw['error']))
    normalized=copy.deepcopy(raw)
    normalized['message']={'role':'assistant','content':raw.get('response','')}
    return {'elapsed_s':time.perf_counter()-start,'response':normalized,'raw_response':raw,
            'request':payload,'num_predict':max_tokens,'transport':'raw_chatml_json_adapter'}

async def main():
    # The queue's last line is written only after embedding, diagnostics and OCR finish.
    deadline=time.monotonic()+7200
    while 'DONE report.py' not in (HERE/'after.log').read_text():
        if time.monotonic()>deadline:raise RuntimeError('Previous inference queue did not finish')
        await asyncio.sleep(10)
    gm=json.loads((HERE/'generation/metadata.json').read_text())
    inv=json.loads((HERE/'inventory.json').read_text());m=next(m for m in inv['models'] if m['name']==MODEL)
    ds=json.loads((HERE/'dataset.json').read_text());defs=json.loads((HERE/'tools.json').read_text())
    schemas={d['function']['name']:d['function']['parameters'] for d in defs}
    mcp,_=g.b.setup_runtime();before=g.b.digest_file(g.b.HERE/'benchmark.db')
    out={'started_at':datetime.now(timezone.utc).isoformat(),'model':MODEL,'digest':m['digest'],
         'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'settings':g.SETTINGS,
         'template':TEMPLATE_NOTE,'track':'raw_chatml_json_adapter','source':'https://docs.ollama.com/api/generate',
         'note':'Post-hoc alternative transport after raw startup succeeded. All 50 unchanged tasks. Does not replace the unavailable native chat result.',
         'main_source_sha256':gm['source_sha256'],'db_sha256_before':before,'cases':[]}
    path=HERE/'raw_transport.json'
    if path.exists():raise RuntimeError('Refusing to overwrite an existing raw transport run')
    save(path,out)
    original=g.api;g.api=raw_api
    try:
        async with Client(mcp) as mc,httpx.AsyncClient(base_url=g.b.OLLAMA) as h:
            try:out['warmup']=await raw_api(h,MODEL,[{'role':'user','content':'準備完了とだけ返してください。'}],[],m['capabilities'],128,120)
            except Exception as e:out['warmup_error']=repr(e)
            for case in ds['cases']:
                result=await g.run_case(h,mc,m,case,gm['system'],defs,schemas,'json_adapter')
                result['transport']='raw_chatml_json_adapter';out['cases'].append(result);save(path,out)
                print('RAW FULL',case['id'],result['score']['correct'],result['status'],round(result['elapsed_s'],1),flush=True)
            try:out['runtime']=(await h.get('/api/ps',timeout=15)).json()
            except Exception as e:out['runtime_error']=repr(e)
    finally:g.api=original
    out['finished_at']=datetime.now(timezone.utc).isoformat();out['db_sha256_after']=g.b.digest_file(g.b.HERE/'benchmark.db')
    out['database_unchanged']=out['db_sha256_after']==before;save(path,out)
    print('RAW FULL DONE',len(out['cases']),'DB unchanged',out['database_unchanged'],flush=True)

if __name__=='__main__':asyncio.run(main())
