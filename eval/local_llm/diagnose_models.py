"""起動失敗と出力上限の追加診断。主比較の結果を差し替えない。"""
import asyncio
import json
import time
from datetime import datetime, timezone
import httpx
from benchmark import HERE, OLLAMA, generate, final_format, score
from analyze import passed


async def main():
    native=json.loads((HERE/'runs/native_v1_20260915/metadata.json').read_text())
    if not native.get('finished_at'):raise RuntimeError('native比較の終了を待ってください')
    dataset=json.loads((HERE/'dataset.json').read_text())
    records=[]
    out=HERE/'runs/diagnostics_20260915.json'
    async with httpx.AsyncClient(base_url=OLLAMA,timeout=90) as client:
        for model in ['qwen3.8:27b-mtp-q4_K_M','qwen3.8:27b-mtp-q8_0']:
            for api in ['native','compatible']:
                payload={'model':model,'messages':[{'role':'user','content':'OKとだけ答えてください。'}],'stream':False}
                if api=='native':
                    payload.update(think=False,options={'temperature':0,'seed':20260915,'num_predict':32,'num_ctx':32768})
                    path='/api/chat'
                else:
                    payload.update(temperature=0,max_tokens=32)
                    path='/v1/chat/completions'
                t=time.perf_counter()
                try:
                    r=await client.post(path,json=payload,timeout=90)
                    records.append({'model':model,'api':api,'payload':payload,'http_status':r.status_code,
                                    'body':r.text,'elapsed_s':time.perf_counter()-t})
                    print(model,api,r.status_code,r.text[:250],flush=True)
                except Exception as e:
                    records.append({'model':model,'api':api,'error':f'{type(e).__name__}: {e}','elapsed_s':time.perf_counter()-t})
                out.write_text(json.dumps({'records':records},ensure_ascii=False,indent=2))
        c=next(c for c in dataset['cases'] if c['id']=='R02')
        for model in ['qwen3-vl:8b']:
            system='あなたは製造品質の質問に答えるアシスタントです。提示された検索結果だけを根拠に答えてください。情報がなければ不明と答え、推測しないでください。'
            question=c['question']+'\n検索結果:\n'+json.dumps(c['context'],ensure_ascii=False)+final_format(c)
            t=time.perf_counter()
            result={'model':model,'case_id':c['id'],'suite':'rag','calls':[],'status':'completed','error':None,'answer':''}
            try:
                response,elapsed=await generate(client,model,[{'role':'system','content':system},{'role':'user','content':question}],[],3072,timeout=90)
                result['response']=response;result['answer']=response.get('message',{}).get('content','')
                if response.get('done_reason')=='length':result['status']='output_truncated'
            except Exception as e:result.update(status='error',error=f'{type(e).__name__}: {e}')
            result['elapsed_s']=time.perf_counter()-t
            result['score']=score(c,result)
            if result['status']!='completed':result['score']['correct']=False
            result['correct_normalized']=passed(c,result)
            result['num_predict']=3072
            result['note']='主比較R02の768から3072へ拡大した1問の診断。主比較の採点には含めない。切替起動時間込み。'
            records.append(result)
            out.write_text(json.dumps({'measured_at':datetime.now(timezone.utc).isoformat(),'records':records},ensure_ascii=False,indent=2))
            print(model,'R02/3072',result['status'],result['correct_normalized'],flush=True)
        # 30BはRAGが既に6/6だったため、実際に途切れたOntology O01を再確認する。
        # 保存済み主比較コードは変更せず、この追加診断内だけ生成上限を差し替える。
        import benchmark as bench
        from fastmcp import Client
        mcp,_=bench.setup_runtime()
        defs=json.loads((HERE/'runs/native_v1_20260915/tools.json').read_text())
        schemas={d['function']['name']:d['function']['parameters'] for d in defs}
        original_generate=bench.generate
        async def with_larger_budget(client,model,messages,tools,max_tokens,timeout=75):
            return await original_generate(client,model,messages,tools,3072,timeout=timeout)
        bench.generate=with_larger_budget
        try:
            async with Client(mcp) as mc:
                c=next(c for c in dataset['cases'] if c['id']=='O01')
                result=await bench.run_case(client,mc,'qwen3-vl:30b',c,native['system'],defs,schemas)
            result['correct_normalized']=passed(c,result)
            result['num_predict']=3072
            result['note']='O01を1生成768から3072 tokensへ拡大。同じ最大6段階・1問150秒、同じ実MCP。主比較へ混ぜない。'
            records.append(result)
            out.write_text(json.dumps({'measured_at':datetime.now(timezone.utc).isoformat(),'records':records},ensure_ascii=False,indent=2))
            print('qwen3-vl:30b','O01/3072',result['status'],result['correct_normalized'],flush=True)
        finally:
            bench.generate=original_generate


if __name__=='__main__':asyncio.run(main())
