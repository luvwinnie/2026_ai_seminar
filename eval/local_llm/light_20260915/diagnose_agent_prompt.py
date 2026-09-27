"""Post-hoc matched prompt diagnostic for all five selected Qwen3.5 small tags."""
import asyncio,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import httpx
from fastmcp import Client
import run_generation as g
from preflight import save
HERE=Path(__file__).resolve().parent
CLARIFICATION='\n次のJSON形式指定は最終回答にだけ適用します。まず必要なツールを実際に呼び、実行結果を受け取ってから最終JSONを作成してください。途中のツール呼び出しは最終回答ではありません。'

async def main():
    gm=json.loads((HERE/'generation/metadata.json').read_text())
    if not gm.get('finished_at'):raise RuntimeError('main generation not finished')
    inv=json.loads((HERE/'inventory.json').read_text());ds=json.loads((HERE/'dataset.json').read_text())
    models=sorted([m for m in inv['models'] if m['selected'] and m['name'].startswith('qwen3.5:')],key=lambda m:m['size'])
    assert len(models)==5
    cases=[c for c in ds['cases'] if c['suite']=='ontology'];assert len(cases)==14
    defs=json.loads((HERE/'tools.json').read_text());schemas={d['function']['name']:d['function']['parameters'] for d in defs}
    mcp,_=g.b.setup_runtime();before=g.b.digest_file(g.b.HERE/'benchmark.db')
    path=HERE/'agent_prompt_diagnostic.json'
    out={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'clarification':CLARIFICATION,'settings':g.SETTINGS,'models':[m['name'] for m in models],'case_ids':[c['id'] for c in cases],
         'note':'Post-hoc diagnostic after observing direct final answers without tools; all five selected Qwen3.5 tags, same 14 ontology cases. Does not replace main scores.',
         'db_sha256_before':before,'records':[]}
    original=g.instructions
    def clarified(case,adapter=False):return CLARIFICATION+original(case,adapter)
    g.instructions=clarified
    try:
        async with Client(mcp) as mc,httpx.AsyncClient(base_url=g.b.OLLAMA) as http:
            for m in models:
                try:await g.api(http,m['name'],[{'role':'user','content':'準備完了とだけ返してください。'}],[],m['capabilities'],128,120)
                except Exception as e:out.setdefault('warmup_errors',{})[m['name']]=repr(e)
                for case in cases:
                    r=await g.run_case(http,mc,m,case,gm['system'],defs,schemas,'native')
                    out['records'].append(r);save(path,out)
                    print('PROMPT DIAGNOSTIC',m['name'],case['id'],r['score']['correct'],r['status'],flush=True)
    finally:g.instructions=original
    out['finished_at']=datetime.now(timezone.utc).isoformat();out['db_sha256_after']=g.b.digest_file(g.b.HERE/'benchmark.db')
    out['database_unchanged']=out['db_sha256_after']==before;save(path,out)

if __name__=='__main__':asyncio.run(main())
