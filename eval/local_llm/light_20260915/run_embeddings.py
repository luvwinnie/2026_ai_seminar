"""Seven local embedding tags, same frozen 117-document corpus and 24 human-written queries."""
import os
import argparse,hashlib,json,math,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
import httpx,numpy as np
from preflight import save

HERE=Path(__file__).resolve().parent
EXTRA=[
('KZ25-0111','駆動プーリの位置決め穴が幅方向に68ミクロン広く、測り直しても規格を超えていた例'),
('KZ25-0110','運搬中に隣の製品とぶつかった形跡がある、ギヤケースのキー溝側面の8ミリの線傷'),
('KZ25-0109','溶接したインペラハウジングのダボ位置決め部が反ってしまい、研磨でも直せなかった例'),
('KZ25-0108','ロータシャフトで3つある取付穴の1つだけが約92ミクロンずれ、組付けできない問題'),
('KZ25-0106','グランド押えナットを洗ったあと、外周リブに17ミリの曲がった傷が見つかった件'),
('KZ25-0107','ガイドレールブロックの6か所の取付穴のうち1か所が220ミクロンずれて相手部品に合わない'),
('KZ25-0105','バルブボディの初品で穴のグループが48ミクロンずれたが、初品確認で出荷を防げたケース'),
('KZ25-0103','メカニカルシール座のOリングを入れる溝で、つかみ直した継ぎ目に段ができて修正できない'),
('KZ25-0104','ローラブラケットの7穴中1穴が位置決め基準から169ミクロン離れ、組み合わなくなった'),
('KZ25-0102','チェーンテンショナのポケット隅の丸み部分で、直径16の箇所が204ミクロン太く加工された'),
('KZ25-0100','搬送用トレーでの接触が疑われる、カップリングハブのシールが摺動する面の直線的な傷'),
('KZ25-0101','グランド押えナットのM5ねじ切り工具が中で折れ、取り出そうとして皿モミ面も傷つけ廃棄した'),
('KZ25-0099','駆動プーリのねじ下穴の交差する縁にバリが残り、装着するOリングが切れそうになった'),
('KZ25-0096','バルブボディのねじ穴の入口の面取りが足りず、7個中3個でバリを噛み込む問題'),
('KZ25-0098','ステムガイドの位置決め用の穴に、隣の製品との接触でできたような25ミリのまっすぐな傷'),
('KZ25-0097','インペラハウジングのフランジの合わせ面を再把持して削ったら継ぎ目に111ミクロンの段ができた'),
('KZ25-0095','マニホールドブロックのベアリング嵌合面に、切粉を噛んだ爪が原因らしい14ミリの弧状傷'),
('KZ25-0094','ガイドレールブロックの下穴の入口交差部のバリが原因で、シール用Oリングの損傷が心配された例'),
]
PREFIXES={
 'jina':('Query: ','Document: ','https://huggingface.co/jinaai/jina-embeddings-v5-text-small-retrieval'),
 'qwen':('Instruct: Given a question about manufacturing defects, retrieve relevant reports that answer the question\nQuery: ','','https://huggingface.co/Qwen/Qwen3-Embedding-0.6B'),
 'nemotron':('query: ','passage: ','https://huggingface.co/nvidia/Nemotron-3-Embed-1B-BF16'),
 'embeddinggemma':('task: search result | query: ','title: none | text: ','https://ai.google.dev/gemma/docs/embeddinggemma/model_card'),
}

def prepare():
    snapshot=json.loads((HERE.parent/'snapshot.json').read_text())
    old=json.loads((HERE.parent/'dataset.json').read_text())
    docs=[{'id':r['defect_id'],'text':f"{r.get('defect_description') or ''}\n原因: {r.get('cause') or ''}\n対策: {r.get('countermeasure') or ''}"} for r in snapshot['reports']]
    qs=[{'id':f'E{i:02}','query':r['query'],'gold_ids':r['gold_ids']} for i,r in enumerate(old['retrieval'],1)]
    qs += [{'id':f'E{i:02}','query':q,'gold_ids':[did]} for i,(did,q) in enumerate(EXTRA,7)]
    data={'documents':docs,'queries':qs,'snapshot_sha256':hashlib.sha256((HERE.parent/'snapshot.json').read_bytes()).hexdigest(),
          'note':'24 known-answer questions, paraphrased by the benchmark author; 117 fixed documents. Query phrasing is not an independent relevance annotation.'}
    save(HERE/'retrieval_dataset.json',data)
    return data

def metrics(ids,gold):
    ranks=[ids.index(g)+1 for g in gold if g in ids];rank=min(ranks) if ranks else None
    return {'rank':rank,'hit_at_1':rank==1,'hit_at_5':rank is not None and rank<=5,
            'mrr_at_10':1/rank if rank and rank<=10 else 0,
            'ndcg_at_10':1/math.log2(rank+1) if rank and rank<=10 else 0}

BASELINE_CODE=r'''
import sys,json,time
from types import SimpleNamespace
from services import hybrid,rag
import numpy as np
d=json.load(sys.stdin)
rows=[SimpleNamespace(defect_id=x['id'],defect_description=x['text'],cause=None,countermeasure=None,part_name=None,phenomenon=None,machine_name=None,process=None) for x in d['documents']]
t=time.perf_counter();idx=hybrid._Index(rows);init=time.perf_counter()-t
records=[]
for q in d['queries']:
 t=time.perf_counter();bm=idx.bm25(hybrid.tokenize(q['query']),top_n=117)
 records.append({'case_id':q['id'],'ranking':[x[0] for x in bm],'scores':[x[1] for x in bm],'elapsed_s':time.perf_counter()-t})
t=time.perf_counter();e=np.asarray(rag._encode_passages([x['text'] for x in d['documents']]));embed_index=time.perf_counter()-t
e5=[]
for q in d['queries']:
 t=time.perf_counter();v=np.asarray(rag._encode_query(q['query']));scores=e@v;order=np.argsort(-scores,kind='stable')
 e5.append({'case_id':q['id'],'ranking':[d['documents'][i]['id'] for i in order],'scores':scores[order].tolist(),'elapsed_s':time.perf_counter()-t})
print('RESULT_JSON:'+json.dumps({'bm25':records,'e5':e5,'bm25_initialization_s':init,'e5_indexing_including_load_s':embed_index,'tokenizer':'SudachiPy mode A' if hybrid._get_sudachi() else 'character bigrams','bm25_k1':hybrid._K1,'bm25_b':hybrid._B},ensure_ascii=False))
'''

def baseline(data):
    r=subprocess.run(['docker','exec','-i','app-backend-1','python','-c',BASELINE_CODE],input=json.dumps(data,ensure_ascii=False),text=True,capture_output=True,timeout=300)
    if r.returncode:raise RuntimeError(r.stderr[-3000:])
    out=json.loads(r.stdout.split('RESULT_JSON:')[-1]);gold={q['id']:q['gold_ids'] for q in data['queries']}
    for method in ['bm25','e5']:
        for r in out[method]:r.update(metrics(r['ranking'],gold[r['case_id']]))
    out['measured_at']=datetime.now(timezone.utc).isoformat();save(HERE/'retrieval_baselines.json',out)
    print('BASELINES',len(data['queries']),flush=True)

def embed(c,model,texts):
    p={'model':model,'input':texts,'truncate':False,'keep_alive':'3m','options':{'num_ctx':2048,'num_batch':512}}
    t=time.perf_counter();r=c.post('/api/embed',json=p,timeout=180)
    if r.status_code!=200:
        error=f'HTTP {r.status_code}: {r.text[:1800]}'
        if len(texts)>1:
            # Some installed runtimes support the model but reject batched pooling.
            # Keep the original error and retry every input singly, without changing text.
            vectors=[];children=[]
            for value in texts:
                v,info=embed(c,model,[value]);vectors.append(v);children.append(info)
            joined=np.vstack(vectors)
            return joined,{'elapsed_s':time.perf_counter()-t,'batch_fallback':'single_input_after_batch_error','batch_error':error,
                           'single_requests_metadata':children,'dimensions':joined.shape[1],
                           'norm_min':min(x['norm_min'] for x in children),'norm_max':max(x['norm_max'] for x in children),
                           'response_metadata':{'prompt_eval_count':sum(x['response_metadata'].get('prompt_eval_count',0) for x in children)}}
        raise RuntimeError(error)
    d=r.json();v=np.asarray(d['embeddings'],dtype=np.float64)
    if v.ndim!=2 or v.shape[0]!=len(texts) or not np.isfinite(v).all():raise RuntimeError('invalid embedding shape/NaN/Inf')
    norms=np.linalg.norm(v,axis=1)
    if np.any(norms<1e-12):raise RuntimeError('zero embedding')
    return v/norms[:,None],{'elapsed_s':time.perf_counter()-t,'response_metadata':{k:val for k,val in d.items() if k!='embeddings'},'dimensions':v.shape[1],'norm_min':float(min(norms)),'norm_max':float(max(norms))}

def main(args):
    if args.prepare:
        data=prepare();baseline(data);return
    generation=json.loads((HERE/'generation/metadata.json').read_text())
    if not generation.get('finished_at'):raise RuntimeError('Generation benchmark still running; do not share inference hardware.')
    data=json.loads((HERE/'retrieval_dataset.json').read_text());inv=json.loads((HERE/'inventory.json').read_text())
    models=sorted([m for m in inv['models'] if m['selected'] and m['kind']=='embedding'],key=lambda m:m['size'])
    outdir=HERE/'embeddings';outdir.mkdir(exist_ok=True)
    meta={'started_at':datetime.now(timezone.utc).isoformat(),'models':[m['name'] for m in models],
          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'dataset_sha256':hashlib.sha256((HERE/'retrieval_dataset.json').read_bytes()).hexdigest(),
          'settings':{'num_ctx':2048,'num_batch':512,'document_batch_size':8,'batch_error_fallback':'individual identical inputs; error retained','truncate':False,'concurrency':1,'query_repetitions':2},'prefixes':PREFIXES}
    if (outdir/'metadata.json').exists():
        old=json.loads((outdir/'metadata.json').read_text())
        for field in ['models','script_sha256','dataset_sha256','settings','prefixes']:
            # JSON serializes tuple prefix specifications as arrays.
            if json.dumps(old[field],sort_keys=True)!=json.dumps(meta[field],sort_keys=True):raise RuntimeError('unsafe embedding resume: '+field)
        meta=old
    save(outdir/'metadata.json',meta)
    gold={q['id']:q['gold_ids'] for q in data['queries']};ids=[x['id'] for x in data['documents']]
    bm=json.loads((HERE/'retrieval_baselines.json').read_text())['bm25'];bm={r['case_id']:r['ranking'] for r in bm}
    with httpx.Client(base_url=os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')) as c:
        for m in models:
            name=m['name'];key=hashlib.sha256(name.encode()).hexdigest()[:12];path=outdir/(key+'.json')
            if path.exists():
                previous=json.loads(path.read_text())
                if previous.get('status') in {'completed','error'}:continue
                path.rename(outdir/(key+f'.interrupted_{time.time_ns()}.json'))
            kind=next(k for k in PREFIXES if name.startswith(k));qp,dp,source=PREFIXES[kind]
            row={'model':name,'digest':m['digest'],'query_prefix':qp,'document_prefix':dp,'prefix_source':source,'records':[],'batches':[]}
            print('EMBED',name,flush=True)
            try:
                _,warm=embed(c,name,[qp+'品質検査']);row['warmup']=warm
                vecs=[]
                for i in range(0,len(ids),8):
                    v,info=embed(c,name,[dp+x['text'] for x in data['documents'][i:i+8]]);vecs.extend(v);row['batches'].append(info)
                docs=np.asarray(vecs);query_vecs=[]
                for q in data['queries']:
                    repeated=[]
                    for repetition in range(2):
                        v,info=embed(c,name,[qp+q['query']]);query_vecs.append(v[0]);scores=docs@v[0]
                        order=np.argsort(-scores,kind='stable');ranking=[ids[i] for i in order];repeated.append(ranking)
                        fused={did:1/(60+rank) for rank,did in enumerate(ranking[:50],1)}
                        for rank,did in enumerate(bm[q['id']][:50],1):fused[did]=fused.get(did,0)+1/(60+rank)
                        rrf=sorted(fused,key=lambda did:(-fused[did],did))
                        row['records'].append({'case_id':q['id'],'repetition':repetition,'query':q['query'],'gold_ids':q['gold_ids'],'ranking':ranking,
                            'scores':scores[order].tolist(),'metrics':metrics(ranking,q['gold_ids']),'rrf_ranking':rrf,'rrf_metrics':metrics(rrf,q['gold_ids']),**info})
                    print(name,q['id'],row['records'][-2]['metrics'], 'repeat_top5_equal',repeated[0][:5]==repeated[1][:5],flush=True)
                    save(path,row)
                np.savez_compressed(outdir/(key+'.npz'),documents=docs,queries=np.asarray(query_vecs))
                row['status']='completed';row['dimensions']=docs.shape[1]
            except Exception as e:
                row['status']='error';row['error']=repr(e)
                try:_,row['diagnostic_retry']=embed(c,name,[qp+'品質検査',dp+'検査で傷を確認した。'])
                except Exception as e2:row['diagnostic_retry_error']=repr(e2)
                print('EMBED ERROR',name,repr(e),flush=True)
            try:row['runtime']=c.get('/api/ps',timeout=15).json()
            except Exception as e:row['runtime_error']=repr(e)
            save(path,row)
    meta['finished_at']=datetime.now(timezone.utc).isoformat();save(outdir/'metadata.json',meta)
    print('EMBED ALL DONE',len(models),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');main(p.parse_args())
