"""Ollama native API + アプリ実MCPによる再現可能なローカル評価。

RAG固定コンテキスト、最初のtool call、複数段階Ontology QAを別指標で測定。
モデル本文に書かれたtool-call風JSONは実行しない。実MCPは隔離SQLiteを使用。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import jsonschema

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKEND = ROOT/'app/backend'
OLLAMA = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')  # 研究室の Ollama は環境変数で渡す
READ_TOOLS = {'get_ontology_definition','resolve_ontology_entity','get_ontology_object',
              'traverse_ontology_relation','query_quality_ontology','preview_capa_update',
              'get_defect_report','list_defect_reports','search_defect_reports','list_capa_actions',
              'list_masters','get_statistics','get_similar_reports','get_active_alerts','get_control_chart'}


def setup_runtime():
    logging.getLogger('fastmcp').setLevel(logging.CRITICAL)
    os.environ.pop('DATABASE_URL',None)
    os.environ['DB_PATH']=str(HERE/'benchmark.db')
    os.environ['EMBEDDINGS']='off'
    os.environ['OPENCODE_URL']=''
    sys.path.insert(0,str(BACKEND))
    from database import Base,engine,SessionLocal
    from models import DefectReport,CapaAction,MasterItem
    from services.mcp_server import mcp
    from services.ontology_contract import agent_context
    dataset=json.loads((HERE/'dataset.json').read_text())
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.query(DefectReport.id).first():
            rows=json.loads((HERE/'snapshot.json').read_text())['reports']+dataset['fixture_reports']
            columns={c.name:c for c in DefectReport.__table__.columns}
            for r in rows:
                values={k:v for k,v in r.items() if k in columns and k not in {'id','created_at','updated_at'}}
                for k in ('occurrence_date','report_date'):
                    if values.get(k):values[k]=date.fromisoformat(values[k])
                db.add(DefectReport(**values))
            db.add_all([CapaAction(**r) for r in dataset['fixture_capas']])
            db.commit()
        if not db.query(MasterItem.id).first():
            for category,field in [('machine','machine_name'),('process','process'),('customer','customer'),
                                   ('operator','operator_name'),('phenomenon','phenomenon'),('factor','factor')]:
                for (name,) in db.query(getattr(DefectReport,field)).distinct().all():
                    if name:db.add(MasterItem(category=category,name=name,is_active=True))
            db.commit()
    return mcp,agent_context()


def digest_file(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_json(text):
    fenced=re.findall(r'```(?:json)?\s*([\s\S]*?)```',text)
    if fenced:
        try:
            obj=json.loads(fenced[-1])
            return obj if isinstance(obj,dict) else None
        except ValueError:return None
    decoder=json.JSONDecoder()
    for match in re.finditer(r'\{',text):
        try:
            obj,_=decoder.raw_decode(text[match.start():])
            if isinstance(obj,dict):return obj
        except ValueError:pass
    return None


def fact_equal(actual, expected):
    if expected is None:return actual is None
    if isinstance(expected,bool):return type(actual) is bool and actual==expected
    if isinstance(expected,(int,float)):
        if isinstance(actual,bool):return False
        try:
            return math.isclose(float(str(actual).replace(',','')),expected,rel_tol=0,
                                abs_tol=5e-5 if 0<abs(expected)<1 else 1e-6)
        except (ValueError,TypeError):return False
    if isinstance(expected,list):return isinstance(actual,list) and sorted(actual)==sorted(expected)
    return actual==expected


def matches_call(call, expected, case_id=''):
    if 'alternatives' in expected:
        return any(matches_call(call,option,case_id) for option in expected['alternatives'])
    if call.get('name')!=expected['name']:return False
    args=call.get('arguments')
    if not isinstance(args,dict):return False
    for k,v in expected['arguments'].items():
        if k=='query' and case_id=='T08':
            if not all(word in str(args.get(k,'')) for word in ('工具','摩耗','寸法')):return False
        elif k=='scope':
            # フィルタ追加・省略で母集団を変える回答は不正解。
            actual={key:value for key,value in args.get(k,{}).items() if value is not None}
            if actual!=v:return False
        elif args.get(k)!=v:return False
    if expected['name']=='preview_capa_update' and str(args.get('effect_note') or '').strip():return False
    return True


def score(case, result):
    calls=result.get('calls',[])
    if case['suite']=='tool':
        first=calls[0] if calls else {}
        name_ok=first.get('name')==case['expected_call']['name']
        exact=bool(first.get('schema_valid')) and matches_call(first,case['expected_call'],case['id'])
        return dict(correct=exact,tool_name_correct=name_ok,tool_arguments_correct=exact,
                    tool_call_present=bool(calls))
    parsed=parse_json(result.get('answer',''))
    facts={k: parsed is not None and k in parsed and fact_equal(parsed[k],v) for k,v in case['expected'].items()}
    factual=all(facts.values())
    required=case.get('required_calls',[])
    matched=[any(c.get('success') and matches_call(c,exp) for c in calls) for exp in required]
    cursor=0
    for expected_call in required:
        next_index=next((i for i in range(cursor,len(calls)) if calls[i].get('success') and matches_call(calls[i],expected_call)),None)
        if next_index is None:
            order_ok=False
            break
        cursor=next_index+1
    else:order_ok=True
    forbidden=set(case.get('forbidden_calls',[]))
    forbidden_called=any(c.get('name') in forbidden or c.get('blocked') for c in calls)
    tool_ok=all(matched) and order_ok and not forbidden_called if required else None
    cited=set(re.findall(r'KZ25-\d{4}',result.get('answer','')))
    gold=set(case.get('gold_ids',[]))
    citation_gold=bool(gold & cited) if gold else None
    citation_supported=bool(cited) and cited<=gold if gold else None
    return dict(correct=factual and (tool_ok if tool_ok is not None else True) and not result.get('error')
                       and (citation_supported if gold else True),
                factual_correct=factual,fields=facts,parseable_json=parsed is not None,
                tool_workflow_correct=tool_ok,required_call_matches=matched,forbidden_called=forbidden_called,
                cited_ids=sorted(cited),gold_citation_present=citation_gold,citation_supported=citation_supported,
                required_call_order_correct=order_ok if required else None)


def final_format(case):
    keys=case.get('output_keys',[])
    return ('\n日本語で短く説明した後、最後に次のキーだけのJSONオブジェクトをコードブロックで出してください。'
            '配列のキーは配列、不明値はnull、率は百分率でなく0〜1の比率、金額は円単位の数値とします。'
            'キー: '+', '.join(keys)) if keys else ''


async def generate(client, model, messages, tools, max_tokens, timeout=75):
    thinking='low' if model.startswith('gpt-oss:') else False
    p={'model':model,'messages':messages,'stream':False,'think':thinking,'keep_alive':'5m',
       'options':{'temperature':0,'seed':20260915,'num_predict':max_tokens,'num_ctx':32768}}
    if tools:p['tools']=tools
    t=time.perf_counter()
    r=await client.post('/api/chat',json=p,timeout=timeout)
    r.raise_for_status()
    data=r.json()
    if data.get('error'):raise RuntimeError(data['error'])
    return data,time.perf_counter()-t


def normalize_calls(message, schemas):
    out=[]
    for t in message.get('tool_calls') or []:
        f=t.get('function') or {}
        args=f.get('arguments',{})
        if isinstance(args,str):
            try:args=json.loads(args)
            except ValueError:pass
        call={'name':f.get('name',''),'arguments':args,'schema_valid':False}
        try:
            if call['name'] not in schemas:raise ValueError('unknown tool')
            jsonschema.Draft202012Validator(schemas[call['name']]).validate(args)
            call['schema_valid']=True
        except (jsonschema.ValidationError,ValueError) as e:call['validation_error']=str(e)[:400]
        out.append(call)
    return out


async def run_case(client, mcp_client, model, case, system, tool_defs, schemas):
    t=time.perf_counter()
    calls=[]; responses=[];answer='';error=None;status='completed'
    if case['suite']=='rag':
        sys_prompt='あなたは製造品質の質問に答えるアシスタントです。提示された検索結果だけを根拠に答えてください。情報がなければ不明と答え、推測しないでください。'
        question=case['question']+'\n検索結果:\n'+json.dumps(case['context'],ensure_ascii=False)+final_format(case)
        tools=[];steps=1
    else:
        sys_prompt=system
        question=case['question']+final_format(case)
        tools=tool_defs;steps=1 if case['suite']=='tool' else 6
    messages=[{'role':'system','content':sys_prompt},{'role':'user','content':question}]
    try:
        for step in range(steps):
            remaining=150-(time.perf_counter()-t)
            if remaining<=0:raise TimeoutError('case exceeded 150 seconds')
            data,elapsed=await generate(client,model,messages,tools,768,timeout=min(75,remaining))
            responses.append({'elapsed_s':elapsed,'response':data})
            message=data.get('message',{})
            step_calls=normalize_calls(message,schemas)
            answer=message.get('content','')
            if case['suite']=='tool':
                calls.extend(step_calls);break
            if not step_calls:
                if data.get('done_reason')=='length':status='output_truncated'
                break
            messages.append(message)
            for call in step_calls:
                begin=time.perf_counter()
                if call['name'] not in READ_TOOLS:
                    call.update(blocked=True,success=False,output={'error':'評価環境では書き込み・画面操作を実行しません'})
                elif not call['schema_valid']:
                    call.update(success=False,output={'error':call.get('validation_error')})
                else:
                    try:
                        result=await mcp_client.call_tool(call['name'],call['arguments'],raise_on_error=False)
                        output=result.data
                        if output is None:
                            output=[getattr(c,'text','') for c in result.content]
                        success=not result.is_error and not (isinstance(output,dict) and output.get('error'))
                        call.update(success=bool(success),output=output)
                    except Exception as e:call.update(success=False,output={'error':str(e)[:500]})
                call['elapsed_s']=time.perf_counter()-begin
                calls.append(call)
                rendered=json.dumps(call['output'],ensure_ascii=False,default=str)
                if len(rendered)>60000:
                    rendered=json.dumps({'error':'tool output exceeds benchmark 60000-character limit; narrow the query'},ensure_ascii=False)
                    call['output_limit']=True
                messages.append({'role':'tool','tool_name':call['name'],'content':rendered})
            if step==steps-1:status='step_limit'
    except Exception as e:
        error=f'{type(e).__name__}: {str(e)[:700]}'
        status='error'
    result={'case_id':case['id'],'suite':case['suite'],'model':model,'status':status,'error':error,
            'answer':answer,'calls':calls,'responses':responses,'elapsed_s':time.perf_counter()-t}
    result['score']=score(case,result)
    if status!='completed':result['score']['correct']=False
    return result


async def run(args):
    from fastmcp import Client
    mcp,context=setup_runtime()
    dataset=json.loads((HERE/'dataset.json').read_text())
    inventory=json.loads((HERE/'inventory.json').read_text())['models']
    models=[m['name'] for m in inventory if not m.get('remote_host') and 'tools' in m.get('capabilities',[])]
    priority=['gpt-oss:20b','qwen3.8:27b-mtp-q4_K_M','gemma4:26b','qwen3.5:4b','qwen3.5:9b','qwen3.6:35b-a3b',
              'gemma4:31b','qwen3.5:2b','qwen3.5:0.8b','gemma4:26b-a4b','glm-4.7-flash:q4_K_M',
              'qwen3.8:27b-mtp-q8_0','qwen3.6:35b-a3b-mtp-q8_0','qwen3.5:35b','qwen3.5:9b-nothink',
              'qwen3-vl:8b','qwen3-vl:30b','gpt-oss:120b','laguna-s-2.1:q4_K_M','llama4:scout']
    models=sorted(models,key=lambda m:priority.index(m) if m in priority else 999)
    if args.models:models=args.models.split(',')
    cases=[c for c in dataset['cases'] if not args.suites or c['suite'] in args.suites.split(',')]
    if args.limit:cases=cases[:args.limit]
    output=HERE/args.output;output.mkdir(parents=True,exist_ok=True)
    db_before=digest_file(HERE/'benchmark.db')
    metadata={'started_at':datetime.now(timezone.utc).isoformat(),'ollama':OLLAMA,'harness':'native Ollama + actual FastMCP in-process',
        'benchmark_sha256':digest_file(Path(__file__)), 'ontology_contract_sha256':digest_file(BACKEND/'ontology/quality.json'),
        'dataset_sha256':digest_file(HERE/'dataset.json'),'snapshot_sha256':digest_file(HERE/'snapshot.json'),
        'models':models,'model_inventory':inventory,'case_ids':[c['id'] for c in cases],
        'settings':{'temperature':0,'seed':20260915,'num_ctx':32768,'num_predict':768,'max_steps':6,
                    'think':'false; GPT-OSS low','case_timeout_s':150,'request_timeout_s':75,'concurrency':1},
        'database_sha256_before':db_before,'database':'isolated SQLite:117 snapshot reports + 3 synthetic reports + 3 synthetic CAPAs'}
    system='あなたは製造品質アシスタントです。日本語で回答。ツールの説明・型・引数を厳密に守り、データが必要ならそのターンで取得してください。未定義の名前や項目を作らないでください。\n'+context
    system+='\n個別報告全文はget_defect_report。曖昧な内容の類似検索はsearch_defect_reports。Ontologyグラフはui_navigate(page="ontology_graph")、テーマ変更はui_set_theme(mode="dark"/"light")。'
    async with Client(mcp) as mc, httpx.AsyncClient(base_url=OLLAMA,timeout=75) as http:
        listed=await mc.list_tools()
        defs=[{'type':'function','function':{'name':t.name,'description':t.description or '', 'parameters':t.inputSchema}} for t in listed]
        schemas={t.name:t.inputSchema for t in listed}
        metadata['tool_count']=len(defs)
        metadata['system']=system
        if args.resume and (output/'metadata.json').exists():
            old=json.loads((output/'metadata.json').read_text())
            for field in ('dataset_sha256','snapshot_sha256','benchmark_sha256','ontology_contract_sha256','settings','system','case_ids'):
                if old.get(field)!=metadata[field]:
                    raise RuntimeError(f'resume rejected: {field} changed; use a new output directory')
            metadata['started_at']=old['started_at']
        (output/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
        (output/'tools.json').write_text(json.dumps(defs,ensure_ascii=False,indent=2))
        for model in models:
            key=hashlib.sha256(model.encode()).hexdigest()[:12]
            target=output/f'{key}.json'
            existing=json.loads(target.read_text()) if target.exists() and args.resume else {'model':model,'cases':[]}
            done={r['case_id'] for r in existing['cases']}
            todo=[c for c in cases if c['id'] not in done]
            if not todo:continue
            print(f'MODEL {model} remaining={len(todo)}',flush=True)
            try:
                warm,elapsed=await generate(http,model,[{'role':'user','content':'こんにちは。OKとだけ返してください。'}],[],32,timeout=120)
                existing['warmup']={'elapsed_s':elapsed,'response':warm}
            except Exception as e:
                existing['warmup_error']=f'{type(e).__name__}: {str(e)[:700]}'
                target.write_text(json.dumps(existing,ensure_ascii=False,indent=2))
                print('WARMUP ERROR',model,existing['warmup_error'],flush=True)
                continue
            for case in todo:
                result=await run_case(http,mc,model,case,system,defs,schemas)
                existing['cases'].append(result)
                target.write_text(json.dumps(existing,ensure_ascii=False,indent=2))
                print(f"{model} {case['id']} correct={result['score']['correct']} calls={len(result['calls'])} sec={result['elapsed_s']:.1f} {result.get('error') or ''}",flush=True)
            print(f'DONE {model}',flush=True)
    metadata['finished_at']=datetime.now(timezone.utc).isoformat()
    metadata['database_sha256_after']=digest_file(HERE/'benchmark.db')
    metadata['database_unchanged']=metadata['database_sha256_after']==db_before
    (output/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--models',default='')
    ap.add_argument('--suites',default='')
    ap.add_argument('--limit',type=int,default=0)
    ap.add_argument('--output',default='runs/native_20260915')
    ap.add_argument('--resume',action='store_true')
    asyncio.run(run(ap.parse_args()))
