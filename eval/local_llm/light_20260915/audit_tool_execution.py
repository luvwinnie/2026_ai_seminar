"""Additional audit: actually execute the six read/preview first-tool task types.

The main first-call score is unchanged. This catches application-level validation
that the public JSON Schema does not express (e.g. group_by literal values).
"""
import asyncio,copy,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from fastmcp import Client
import run_generation as g
from preflight import save
HERE=Path(__file__).resolve().parent

async def main():
    meta=json.loads((HERE/'generation/metadata.json').read_text())
    if not meta.get('finished_at'):raise RuntimeError('generation not finished')
    mcp,_=g.b.setup_runtime();before=g.b.digest_file(g.b.HERE/'benchmark.db')
    out={'recorded_at':datetime.now(timezone.utc).isoformat(),'note':'Post-hoc execution audit of saved first calls; UI and mutations remain unexecuted. Main first-call scores are not replaced.',
         'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'records':[],'db_sha256_before':before}
    async with Client(mcp) as mc:
        for p in (HERE/'generation').glob('*.json'):
            d=json.loads(p.read_text())
            if 'model' not in d or d['model']=='unlimited-ocr:q8':continue
            for r in d['cases']:
                if r['suite']!='tool':continue
                row={'model':d['model'],'case_id':r['case_id'],'variant':r['variant'],'main_first_call_correct':r['score']['correct']}
                if r['base_id'] in {'T05','T06'}:
                    row.update(status='ui_not_executed',execution_validated_success=None)
                elif len(r['calls'])!=1:
                    row.update(status='missing_or_multiple_calls',execution_validated_success=False)
                else:
                    call=copy.deepcopy(r['calls'][0]);await g.execute(mc,call)
                    row.update(status='executed' if not call.get('blocked') else 'blocked',call=call,
                               execution_validated_success=bool(r['score']['correct'] and call.get('success')))
                out['records'].append(row)
    out['db_sha256_after']=g.b.digest_file(g.b.HERE/'benchmark.db');out['database_unchanged']=out['db_sha256_after']==before
    save(HERE/'tool_execution_audit.json',out)
    print('TOOL EXECUTION AUDIT',len(out['records']),'DB unchanged',out['database_unchanged'],flush=True)

if __name__=='__main__':asyncio.run(main())
