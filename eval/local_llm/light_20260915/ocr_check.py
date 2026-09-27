"""OCR-specialist smoke test with three generated Japanese document images."""
import os
import argparse,base64,hashlib,html,json,re,time,unicodedata
from datetime import datetime,timezone
from pathlib import Path
import httpx
from preflight import save
HERE=Path(__file__).resolve().parent

def prepare():
    from playwright.sync_api import sync_playwright
    out=HERE/'ocr';out.mkdir(exist_ok=True)
    fixtures=[('KZ25-9001','BENCH設備A','100','10','100','open'),('KZ25-9002','BENCH設備A','900','9','200','open'),('KZ25-9003','BENCH設備B','0','0','未入力','open')]
    docs=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1024,'height':900},device_scale_factor=1)
        for i,(did,machine,prod,bad,cost,status) in enumerate(fixtures,1):
            pairs=[('報告書ID',did),('機械名',machine),('発生日',f'2026年1月{i}日'),('工程','BENCH工程'),('加工数',prod),('不適合数',bad),('損失額（円）',cost),('状態',status)]
            doc='<html lang="ja"><meta charset="utf-8"><style>body{margin:0;padding:52px;background:#fff;color:#17232b;font:26px "Hiragino Kaku Gothic ProN",sans-serif}h1{font-size:34px}p{font-size:22px;line-height:1.8}table{width:100%;border-collapse:collapse}td{border:1px solid #687785;padding:17px}td:first-child{background:#edf1f4;width:42%}</style><main><h1>評価用 不適合報告書</h1><p>これはOCR動作確認用の合成資料です。</p><table>'+''.join('<tr><td>'+html.escape(k)+'</td><td>'+html.escape(v)+'</td></tr>' for k,v in pairs)+'</table><p>記録内容：加工後の検査で傷を確認した。<br>処置内容：対象品を隔離し、再検査する。</p></main></html>'
            path=out/f'document_{i}.html';path.write_text(doc);page.goto(path.as_uri());page.screenshot(path=str(out/f'document_{i}.png'),full_page=True)
            docs.append({'id':f'V{i:02}','image':f'document_{i}.png','image_sha256':hashlib.sha256((out/f'document_{i}.png').read_bytes()).hexdigest(),'expected_text':page.locator('main').inner_text(),'required_ids':[did,machine]})
        browser.close()
    save(out/'dataset.json',{'documents':docs,'note':'Three clean synthetic Japanese pages; smoke test, not general OCR benchmark.'})

def normalize(text):
    text=re.sub(r'<\|ref\|>.*?<\|/ref\|>','',text,flags=re.S)
    text=re.sub(r'<\|det\|>[^<]*<\|/det\|>','',text)
    text=re.sub(r'<[^>]*>','',text)
    text=re.sub(r'^\s{0,3}#{1,6}\s+','',text,flags=re.M)
    text=re.sub(r'^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$','',text,flags=re.M)
    text=text.replace('|','').replace('**','').replace('`','')
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',html.unescape(text)))

def distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]

def run():
    for directory in ['generation','embeddings']:
        if not json.loads((HERE/directory/'metadata.json').read_text()).get('finished_at'):raise RuntimeError('Other inference still running')
    data=json.loads((HERE/'ocr/dataset.json').read_text());out={'started_at':datetime.now(timezone.utc).isoformat(),'model':'unlimited-ocr:q8',
          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'source':'https://github.com/baidu/Unlimited-OCR','note':'Official document parsing prompt adapted to installed Ollama image API; runtime does not expose the official custom no-repeat-ngram processor.','records':[]}
    with httpx.Client(base_url=os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434'),timeout=160) as c:
        for d in data['documents']:
            p={'model':out['model'],'messages':[{'role':'user','content':'document parsing.','images':[base64.b64encode((HERE/'ocr'/d['image']).read_bytes()).decode()]}],
               'stream':False,'keep_alive':'3m','options':{'temperature':0,'num_ctx':32768,'num_predict':4096}}
            t=time.perf_counter();r={'case_id':d['id'],'image':d['image'],'image_sha256':d['image_sha256'],'status':'completed','request_without_image':{**p,'messages':[{'role':'user','content':'document parsing.','image_path':d['image']}]}}
            try:
                response=c.post('/api/chat',json=p)
                if response.status_code!=200:raise RuntimeError(f'HTTP {response.status_code}: {response.text[:1500]}')
                payload=response.json();r['response']=payload;answer=payload.get('message',{}).get('content','')
                if payload.get('done_reason')=='length':r['status']='output_truncated'
                expected=normalize(d['expected_text']);actual=normalize(answer)
                r['character_error_rate']=distance(expected,actual)/len(expected)
                r['required_ids_found']={k:k in actual for k in d['required_ids']};r['identifiers_correct']=all(r['required_ids_found'].values()) and r['status']=='completed'
            except Exception as e:r['status']='error';r['error']=repr(e)
            r['elapsed_s']=time.perf_counter()-t;out['records'].append(r);save(HERE/'ocr/results.json',out)
            print('OCR',d['id'],r['status'],r.get('identifiers_correct'),r.get('character_error_rate'),flush=True)
    out['finished_at']=datetime.now(timezone.utc).isoformat();save(HERE/'ocr/results.json',out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');args=p.parse_args()
    prepare() if args.prepare else run()
