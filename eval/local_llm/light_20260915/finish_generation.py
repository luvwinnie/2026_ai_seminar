"""Continue unchanged generation protocol after routing the OCR specialist to image tests.

The first segment and partial off-label OCR failures remain available, and this
amendment is explicit. No already measured score or model setting is replaced.
"""
import hashlib,json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from preflight import save
HERE=Path(__file__).resolve().parent

def main():
    run=HERE/'generation';meta=json.loads((run/'metadata.json').read_text());specialist='unlimited-ocr:q8'
    oldmeta=run/'segment1_metadata.json'
    if not oldmeta.exists():shutil.copyfile(run/'metadata.json',oldmeta)
    existing={}
    for p in run.glob('*.json'):
        d=json.loads(p.read_text())
        if 'model' in d:existing[d['model']]=d
    amendment={'recorded_at':datetime.now(timezone.utc).isoformat(),'model':specialist,'role':'ocr_specialist',
               'reason':'Official model is trained for document image parsing, not a general chat agent. Repeated off-label text responses do not measure its intended OCR function.',
               'source':'https://github.com/baidu/Unlimited-OCR','completed_off_label_cases':len(existing.get(specialist,{}).get('cases',[])),
               'preserve_partial_text_cases':True,'replacement_test':'ocr_check.py: three clean Japanese document images with explicit ground truth',
               'other_models_protocol':'unchanged; all 50 cases for each usable generation tag'}
    save(HERE/'scope_amendment.json',amendment)
    remaining=[n for n in meta['models'] if n!=specialist and not existing.get(n,{}).get('unavailable') and len(existing.get(n,{}).get('cases',[]))<50]
    if remaining:
        subprocess.run([sys.executable,'-u',str(HERE/'run_generation.py'),'--models',','.join(remaining),'--output','generation_remaining'],check=True)
        part=HERE/'generation_remaining';partmeta=json.loads((part/'metadata.json').read_text())
        for field in ['settings','source_sha256','case_ids','system','db_sha256_before']:
            if partmeta[field]!=meta[field]:raise RuntimeError('protocol changed between segments: '+field)
        for p in part.glob('*.json'):
            d=json.loads(p.read_text())
            if 'model' not in d:continue
            dest=run/p.name
            if dest.exists():raise RuntimeError('refusing to overwrite a measured model: '+d['model'])
            shutil.copyfile(p,dest)
        meta['db_sha256_after']=partmeta['db_sha256_after'];meta['database_unchanged']=partmeta['database_unchanged']
    meta['finished_at']=datetime.now(timezone.utc).isoformat()
    meta['segments']=['generation/segment1_metadata.json','generation_remaining/metadata.json']
    meta['scope_amendment']='scope_amendment.json';meta['generation_models']=[n for n in meta['models'] if n!=specialist]
    meta['ocr_specialist']=specialist
    save(run/'metadata.json',meta)
    print('ALL GENERATION SEGMENTS COMPLETE',flush=True)

if __name__=='__main__':main()
