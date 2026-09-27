"""実OpenCode 1.18.28でのOntology機能確認。native主比較とは別集計。"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import statistics
import time
from datetime import datetime, timezone

import httpx
import jsonschema
from benchmark import HERE, setup_runtime, final_format, score, digest_file
from analyze import passed, value_score

OUT=HERE/'runs/opencode_20260915'


def unpack(history, schemas):
    calls=[]
    answer=''
    errors=[]
    for message in history:
        info=message.get('info',{})
        if info.get('role')!='assistant':
            continue
        if info.get('error'):
            errors.append(info['error'])
        pieces=[]
        for p in message.get('parts',[]):
            if p.get('type')=='text':
                pieces.append(p.get('text',''))
            if p.get('type')!='tool':
                continue
            state=p.get('state',{})
            name=p.get('tool','').removeprefix('defect-reports_')
            args=state.get('input',{})
            output=state.get('output')
            if isinstance(output,str):
                try:output=json.loads(output)
                except ValueError:pass
            if isinstance(output,list):
                parts=[x.get('text','') for x in output if isinstance(x,dict) and x.get('type')=='text']
                if len(parts)==1:
                    try:output=json.loads(parts[0])
                    except ValueError:pass
            valid=False;error=None
            try:
                if name not in schemas:raise ValueError('unknown tool')
                jsonschema.Draft202012Validator(schemas[name]).validate(args)
                valid=True
            except (jsonschema.ValidationError,ValueError) as e:error=str(e)[:400]
            success=state.get('status')=='completed' and not (isinstance(output,dict) and output.get('error'))
            calls.append({'name':name,'arguments':args,'schema_valid':valid,'validation_error':error,
                          'success':bool(success),'output':output,'state':state})
        if pieces:
            answer='\n'.join(pieces)
    return answer,calls,errors


async def run(args):
    native=json.loads((HERE/'runs/native_v1_20260915/metadata.json').read_text())
    if not native.get('finished_at'):
        raise RuntimeError('native測定が未完了です。同一Ollamaでの同時推論を避けてください。')
    setup_runtime()
    from routers.chat import _OPENCODE_SYSTEM
    dataset=json.loads((HERE/'dataset.json').read_text())
    cases=[c for c in dataset['cases'] if c['suite']=='ontology']
    if args.cases:cases=[c for c in cases if c['id'] in args.cases.split(',')]
    definitions=json.loads((HERE/'runs/native_v1_20260915/tools.json').read_text())
    schemas={d['function']['name']:d['function']['parameters'] for d in definitions}
    models=args.models.split(',')
    OUT.mkdir(exist_ok=True)
    meta={'started_at':datetime.now(timezone.utc).isoformat(),'models':models,'case_ids':[c['id'] for c in cases],
          'harness':'OpenCode HTTP + read-only remote MCP + Ollama OpenAI-compatible API',
          'system':_OPENCODE_SYSTEM,'config':json.loads((HERE/'opencode_work/opencode.json').read_text()),
          'agents_md':(HERE/'opencode_work/AGENTS.md').read_text(),'database_sha256_before':digest_file(HERE/'benchmark.db'),
          'script_sha256':digest_file(HERE/'validate_opencode.py'),'dataset_sha256':digest_file(HERE/'dataset.json'),
          'note':'native比較とは別設定: 15 tools、OpenCode system/AGENTS、最大2048 output、temperature0、steps6。thinking/実num_ctxはOpenCode・Ollamaの互換API既定。'}
    allresults=[]
    async with httpx.AsyncClient(base_url='http://localhost:4097',timeout=15) as client:
        meta['health']=(await client.get('/global/health')).json()
        meta['mcp']=(await client.get('/mcp')).json()
        if meta['mcp'].get('defect-reports',{}).get('status')!='connected':raise RuntimeError('MCP not connected')
        (OUT/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
        for model in models:
            print('MODEL',model,flush=True)
            key=hashlib.sha256(model.encode()).hexdigest()[:12]
            target=OUT/f'{key}.json'
            saved=json.loads(target.read_text()) if args.resume and target.exists() else {'model':model,'cases':[]}
            done={c['case_id'] for c in saved['cases']}
            for case in cases:
                if case['id'] in done:continue
                t=time.perf_counter()
                session=(await client.post('/session',json={'title':f"local-benchmark-{case['id']}"})).json()['id']
                payload={'model':{'providerID':'ollama','modelID':model},'agent':'build','system':_OPENCODE_SYSTEM,
                         'parts':[{'type':'text','text':case['question']+final_format(case)}]}
                result={'model':model,'case_id':case['id'],'suite':'ontology','calls':[],'responses':[],
                        'answer':'','status':'completed','error':None,'session_id':session,'payload':payload}
                try:
                    r=await client.post(f'/session/{session}/prompt_async',json=payload)
                    r.raise_for_status()
                    while True:
                        await asyncio.sleep(.5)
                        history=(await client.get(f'/session/{session}/message')).json()
                        statuses=(await client.get('/session/status')).json()
                        active=statuses.get(session,{}).get('type','idle')!='idle'
                        if any(m.get('info',{}).get('role')=='assistant' for m in history) and not active:
                            break
                        if time.perf_counter()-t>180:
                            await client.post(f'/session/{session}/abort')
                            result.update(status='timeout',error='180-second timeout')
                            history=(await client.get(f'/session/{session}/message')).json()
                            break
                    result['history']=history
                    result['answer'],result['calls'],errors=unpack(history,schemas)
                    if errors:result.update(status='error',error=json.dumps(errors,ensure_ascii=False))
                except Exception as e:
                    result.update(status='error',error=f'{type(e).__name__}: {e}')
                    await client.post(f'/session/{session}/abort')
                finally:
                    await client.delete(f'/session/{session}')
                result['elapsed_s']=time.perf_counter()-t
                result['score']=score(case,result)
                if result['status']!='completed':result['score']['correct']=False
                result['correct_normalized']=passed(case,result)
                result['values_only']=value_score(case,result)
                saved['cases'].append(result)
                target.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
                print(model,case['id'],result['correct_normalized'],'calls',len(result['calls']),f"{result['elapsed_s']:.1f}s",result['error'] or '',flush=True)
            allresults.append(saved)
    meta['finished_at']=datetime.now(timezone.utc).isoformat()
    meta['database_sha256_after']=digest_file(HERE/'benchmark.db')
    meta['database_unchanged']=meta['database_sha256_before']==meta['database_sha256_after']
    (OUT/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    text=['## OpenCode経由の追加確認','',
          f"アプリと同じOpenCode 1.18.28の別コンテナを起動し、同じ隔離DBの実MCPをHTTP接続。Ontologyの{len(cases)}問（{', '.join(c['id'] for c in cases)}）を実行した。アプリのsystemとAGENTS.mdを使用し、初期RAG参考文脈は与えていない。主比較の独自ハーネスと設定が異なるため、改善幅の比較ではなく互換性・機能の確認として扱う。",'',
          '温度0、steps=6、出力上限2048をOpenCodeに設定。thinkingと実際のcontextは互換API・サーバー既定。読み取り15ツールだけ公開。モデル切替直後の起動時間もこの表の時間に含む。本文に書かれた呼び出しではなく、OpenCode履歴の実tool partを採点した。','',
          '| モデル | 値＋実ツール手順 | 厳密JSON＋手順 | 値のみ | 中央値 |','|---|---:|---:|---:|---:|']
    for r in allresults:
        cs=r['cases'];n=len(cs)
        text.append(f"| `{r['model']}` | {sum(c['correct_normalized'] for c in cs)}/{n} | {sum(c['score']['correct'] for c in cs)}/{n} | {sum(c['values_only'] for c in cs)}/{n} | {statistics.median(c['elapsed_s'] for c in cs):.1f} 秒 |")
    text += ['',f"隔離DBの測定前後一致: `{meta['database_unchanged']}`。全履歴は `../../runs/opencode_20260915/`。",'']
    (OUT/'summary.md').write_text('\n'.join(text))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--models',default='gemma4:31b,gpt-oss:20b,qwen3.5:35b')
    parser.add_argument('--cases',default='O01,O03,O04,O07,O08')
    parser.add_argument('--resume',action='store_true')
    asyncio.run(run(parser.parse_args()))
