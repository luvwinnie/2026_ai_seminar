"""Final completeness, reproducibility, raw-score, database, and HTML checks."""
import csv,hashlib,json,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote,urlparse
import httpx
import numpy as np
import run_generation as g
from preflight import save

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    inv=read(HERE/'inventory.json');ds=read(HERE/'dataset.json');case_byid={c['id']:c for c in ds['cases']}
    gm=read(HERE/'generation/metadata.json');em=read(HERE/'embeddings/metadata.json');diag=read(HERE/'diagnostics.json');ocr=read(HERE/'ocr/results.json')
    assert gm.get('finished_at') and em.get('finished_at') and diag.get('finished_at') and ocr.get('finished_at')
    selected=[m for m in inv['models'] if m['selected']];assert len(selected)==31
    gens=[m for m in selected if m['kind']=='generation' and m['name']!='unlimited-ocr:q8'];embs=[m for m in selected if m['kind']=='embedding']
    assert len(gens)==23 and len(embs)==7
    checks={};sources_changed=[]
    for path,digest in gm['source_sha256'].items():
        if sha(g.b.ROOT/path)!=digest:sources_changed.append(path)
    assert not sources_changed,sources_changed
    checks['source_hashes_match']=True
    records=0;unavailable=[];models_complete=[]
    for m in gens:
        key=hashlib.sha256(m['name'].encode()).hexdigest()[:12];d=read(HERE/'generation'/(key+'.json'))
        assert d['digest']==m['digest']
        if d.get('unavailable'):
            assert d.get('warmup_error') and not d['cases'];unavailable.append(m['name']);continue
        assert {r['case_id'] for r in d['cases']}==set(case_byid)
        assert len(d['cases'])==50
        for r in d['cases']:
            assert 'scoring_error' not in r['score'],(m['name'],r['case_id'])
            assert g.score(case_byid[r['case_id']],r)==r['score'],(m['name'],r['case_id'])
            assert r['elapsed_s']>=0
        records+=len(d['cases']);models_complete.append(m['name'])
    assert gm['database_unchanged'] and gm['db_sha256_before']==sha(g.b.HERE/'benchmark.db')
    with sqlite3.connect(f'file:{g.b.HERE}/benchmark.db?mode=ro',uri=True) as db:
        counts={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ['defect_reports','capa_actions']}
    assert counts=={'defect_reports':120,'capa_actions':3},counts
    er=0;emb_complete=[];emb_errors=[]
    edata=read(HERE/'retrieval_dataset.json');assert len(edata['documents'])==117 and len(edata['queries'])==24
    assert em['script_sha256']==sha(HERE/'run_embeddings.py')
    assert em['dataset_sha256']==sha(HERE/'retrieval_dataset.json')
    assert len({d['id'] for d in edata['documents']})==117
    docids=[d['id'] for d in edata['documents']]
    bm25={r['case_id']:r['ranking'] for r in read(HERE/'retrieval_baselines.json')['bm25']}
    for q in edata['queries']:assert set(q['gold_ids'])<={d['id'] for d in edata['documents']}
    from run_embeddings import metrics
    for m in embs:
        key=hashlib.sha256(m['name'].encode()).hexdigest()[:12];d=read(HERE/'embeddings'/(key+'.json'))
        assert d['digest']==m['digest'];assert d['status'] in {'completed','error'}
        if d['status']=='error':
            assert d.get('error') and ('diagnostic_retry_error' in d or 'diagnostic_retry' in d);emb_errors.append(m['name'])
        else:
            assert len(d['records'])==48 and len({(r['case_id'],r['repetition']) for r in d['records']})==48
            assert (HERE/'embeddings'/(key+'.npz')).exists();emb_complete.append(m['name'])
            with np.load(HERE/'embeddings'/(key+'.npz')) as vectors:
                docs=vectors['documents'];queries=vectors['queries']
                assert docs.shape==(117,d['dimensions']) and queries.shape==(48,d['dimensions'])
                assert np.isfinite(docs).all() and np.isfinite(queries).all()
                assert np.allclose(np.linalg.norm(docs,axis=1),1) and np.allclose(np.linalg.norm(queries,axis=1),1)
                for i,r in enumerate(d['records']):
                    scores=docs@queries[i];order=np.argsort(-scores,kind='stable')
                    assert [docids[j] for j in order]==r['ranking'],(m['name'],r['case_id'])
                    assert np.allclose(scores[order],r['scores'])
                    fused={did:1/(60+rank) for rank,did in enumerate(r['ranking'][:50],1)}
                    for rank,did in enumerate(bm25[r['case_id']][:50],1):fused[did]=fused.get(did,0)+1/(60+rank)
                    assert sorted(fused,key=lambda did:(-fused[did],did))==r['rrf_ranking']
        for r in d['records']:
            assert metrics(r['ranking'],r['gold_ids'])==r['metrics']
            assert metrics(r['rrf_ranking'],r['gold_ids'])==r['rrf_metrics']
        er+=len(d['records'])
    assert len(diag['gemma_structured'])==48 and len(diag['raw_probes'])==2
    assert diag['script_sha256']==sha(HERE/'diagnostics.py')
    for r in diag['gemma_structured']:assert g.score(case_byid[r['case_id']],r)==r['score']
    pd=read(HERE/'agent_prompt_diagnostic.json');assert pd.get('finished_at') and pd['database_unchanged'] and len(pd['records'])==70
    assert pd['script_sha256']==sha(HERE/'diagnose_agent_prompt.py')
    for r in pd['records']:assert g.score(case_byid[r['case_id']],r)==r['score']
    assert len(ocr['records'])==3
    assert ocr['script_sha256']==sha(HERE/'ocr_check.py')
    od=read(HERE/'ocr/dataset.json')
    for d in od['documents']:assert sha(HERE/'ocr'/d['image'])==d['image_sha256']
    from analyze_ocr import text_only
    from ocr_check import normalize,distance
    oa=read(HERE/'ocr/analysis.json');assert oa['raw_sha256']==sha(HERE/'ocr/results.json') and oa['script_sha256']==sha(HERE/'analyze_ocr.py')
    assert len(oa['records'])==3
    for r in oa['records']:
        source=next(x for x in ocr['records'] if x['case_id']==r['case_id'])
        if 'response' not in source:continue
        expected=normalize(next(x['expected_text'] for x in od['documents'] if x['id']==r['case_id']))
        actual=source['response']['message']['content']
        assert source['character_error_rate']==distance(expected,normalize(actual))/len(expected)
        assert r['corrected_text_cer']==distance(expected,text_only(actual))/len(expected)
    ta=read(HERE/'tool_execution_audit.json');assert ta['database_unchanged']
    assert ta['script_sha256']==sha(HERE/'audit_tool_execution.py')
    assert ta['db_sha256_before']==gm['db_sha256_before']
    assert len(ta['records'])==len(models_complete)*10
    raw=read(HERE/'raw_transport.json')
    assert raw.get('finished_at') and raw['database_unchanged'] and len(raw['cases'])==50
    assert raw['script_sha256']==sha(HERE/'run_raw_transport.py') and raw['main_source_sha256']==gm['source_sha256']
    assert raw['db_sha256_before']==gm['db_sha256_before'] and raw['settings']==gm['settings']
    assert raw['digest']==next(m['digest'] for m in selected if m['name']==raw['model'])
    assert {r['case_id'] for r in raw['cases']}==set(case_byid)
    for r in raw['cases']:
        assert 'scoring_error' not in r['score'] and g.score(case_byid[r['case_id']],r)==r['score']
        for response in r['responses']:
            assert response['request']['raw'] and response['raw_response']['response']==response['response']['message']['content']
    summary=read(HERE/'report/summary.json');assert summary['complete']
    assert summary['generation_records']==records and summary['embedding_records']==er
    # Read-only end inventory and actual application health; no model/config mutation.
    with httpx.Client(timeout=30) as c:
        end_tags=c.get(g.b.OLLAMA+'/api/tags').json();live=c.get('http://localhost:8000/health').json();end_version=c.get(g.b.OLLAMA+'/api/version').json()
    assert end_version==inv['version'],end_version
    assert live['status']=='ok' and live['reports']==117
    end={m['name']:m for m in end_tags['models']}
    assert set(end)=={m['name'] for m in inv['models']},'model tag inventory changed during the run'
    changed=[m['name'] for m in selected if m['name'] not in end or end[m['name']]['digest']!=m['digest']]
    assert not changed,changed
    save(HERE/'inventory_end_tags.json',end_tags)
    checks.update(generation_records=records,generation_complete_models=models_complete,generation_unavailable=unavailable,
                  embedding_records=er,embedding_complete_models=emb_complete,embedding_errors=emb_errors,
                  structured_diagnostic_records=48,agent_prompt_diagnostic_records=70,ocr_records=3,tool_execution_audit_records=len(ta['records']),raw_transport_records=50,
                  dataset_unique_cases=50,database_counts=counts,database_unchanged=True,model_digests_unchanged=True,app_health=live)
    from playwright.sync_api import sync_playwright
    errors=[];qa={};report=HERE/'report/report.html'
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(report.as_uri());assert page.title()=='軽量ローカルモデル全件評価'
        assert page.locator('details.model').count()==23
        qa['desktop_no_page_overflow']=page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(HERE/'report/report_desktop.png'))
        page.get_by_text('生成・ツール評価の結果',exact=True).scroll_into_view_if_needed();page.screenshot(path=str(HERE/'report/report_table.png'))
        for e in page.locator('a[href]').all():
            href=e.get_attribute('href')
            if href.startswith(('#','http:','https:')):continue
            target=report.parent/unquote(urlparse(href).path)
            assert target.exists(),str(target)
        page.locator('details.model').first.locator('summary').first.click()
        page.locator('details.model').first.locator('details.case').first.locator('summary').first.click()
        assert page.locator('details.case[open]').count()>=1
        page.set_viewport_size({'width':390,'height':844});page.goto(report.as_uri());qa['mobile_no_page_overflow']=page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(HERE/'report/report_mobile.png'));browser.close()
    assert all(qa.values()) and not errors
    checks.update(html_qa=qa,browser_errors=errors,validated_at=datetime.now(timezone.utc).isoformat())
    save(HERE/'report/validation.json',checks)
    print(json.dumps({k:v for k,v in checks.items() if not k.endswith('_models')},ensure_ascii=False))

if __name__=='__main__':main()
