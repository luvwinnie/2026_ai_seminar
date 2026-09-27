"""既存backend内でBM25/e5/RRF/アプリ最終順位を比較。LLMは呼ばない。"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
CODE=r'''
import json,sys,time,statistics,hashlib
from collections import defaultdict
from database import SessionLocal
from models import DefectReport
from services import rag,hybrid

data=json.load(sys.stdin)
records=[]
with SessionLocal() as db:
    actual={r[0] for r in db.query(DefectReport.defect_id).all()}
    if actual!=set(data['report_ids']):raise RuntimeError('live report IDs differ from frozen snapshot')
    idx=hybrid._get_index(db)
    # 索引・埋め込みモデルの初回初期化は検索時間から分離する。
    t=time.perf_counter();rag._dense_search('品質検査',n_results=30);warm=time.perf_counter()-t
    for c in data['cases']:
        q=c['query'];gold=set(c['gold_ids'])
        t=time.perf_counter();bm=idx.bm25(hybrid.tokenize(hybrid.expand_query(q)),top_n=50);bm_s=time.perf_counter()-t
        t=time.perf_counter();dense=rag._dense_search(q,n_results=30);dense_s=time.perf_counter()-t
        scores=defaultdict(float)
        for rank,(did,_) in enumerate(bm,1):scores[did]+=1/(60+rank)
        for rank,r in enumerate(dense,1):scores[r['defect_id']]+=1/(60+rank)
        rrf=sorted(scores,key=scores.get,reverse=True)[:5]
        t=time.perf_counter();full=hybrid.fuse(db,q,dense,top_k=5);fuse_s=time.perf_counter()-t
        variants={'BM25 + synonym expansion':([x[0] for x in bm[:5]],bm_s),
                  'e5 dense only':([x['defect_id'] for x in dense[:5]],dense_s),
                  'RRF only k=60':(rrf,None),
                  'Application full hybrid':([x['defect_id'] for x in full],dense_s+fuse_s)}
        for name,(ids,elapsed) in variants.items():
            rank=next((i+1 for i,x in enumerate(ids) if x in gold),None)
            records.append({'case_id':c['id'],'method':name,'query':q,'gold_ids':list(gold),
                'ids':ids,'rank':rank,'hit_at_1':rank==1,'hit_at_5':rank is not None,
                'reciprocal_rank':1/rank if rank else 0,'elapsed_s':elapsed})
out={'report_count':len(actual),'embedding_mode':rag.get_mode(),'embedding_model':rag.MODEL_NAME,
     'bm25_k1':hybrid._K1,'bm25_b':hybrid._B,'rrf_k':hybrid._RRF_K,'embedding_warmup_s':warm,
     'records':records,'note':'同じ6問・1試行。BM25は同義語展開込み、RRF単独は後段の補正なし。Application fullにはファセット補正・近傍グラフ展開等の既存処理を含む。'}
print('BENCH_JSON:'+json.dumps(out,ensure_ascii=False))
'''

if __name__=='__main__':
    dataset=json.loads((HERE/'dataset.json').read_text())
    snapshot=json.loads((HERE/'snapshot.json').read_text())
    payload={'cases':dataset['retrieval'],'report_ids':[r['defect_id'] for r in snapshot['reports']]}
    result=subprocess.run(['docker','exec','-i','app-backend-1','python','-c',CODE],input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,timeout=180)
    (HERE/'retrieval_stderr.log').write_text(result.stderr)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])
    raw=result.stdout.split('BENCH_JSON:')[-1].strip()
    data=json.loads(raw)
    data['measured_at']=datetime.now(timezone.utc).isoformat()
    (HERE/'retrieval_comparison.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    for method in dict.fromkeys(r['method'] for r in data['records']):
        rs=[r for r in data['records'] if r['method']==method]
        print(method,'Hit@1',sum(r['hit_at_1'] for r in rs),'Hit@5',sum(r['hit_at_5'] for r in rs),'MRR',sum(r['reciprocal_rank'] for r in rs)/len(rs))
