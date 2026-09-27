"""Offline OCR text-score correction; original API outputs and scores remain frozen."""
import hashlib,json,re
from pathlib import Path
from datetime import datetime,timezone
from ocr_check import normalize,distance
from preflight import save
HERE=Path(__file__).resolve().parent

def text_only(text):
    # The installed API strips special <|det|> delimiters but leaves type/bbox.
    # Remove only a recognized layout prefix with exactly four numeric bounds.
    text=re.sub(r'^(?:header|text|table)\s+\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]', '', text, flags=re.M)
    return normalize(text)

def main():
    raw=json.loads((HERE/'ocr/results.json').read_text());assert raw.get('finished_at')
    ds={d['id']:d for d in json.loads((HERE/'ocr/dataset.json').read_text())['documents']}
    out={'analyzed_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'raw_sha256':hashlib.sha256((HERE/'ocr/results.json').read_bytes()).hexdigest(),
         'reason':'The installed API returns header/text/table [x1,y1,x2,y2] without <|det|> delimiters. Initial normalization left these metadata prefixes in document text. Correct the intended metadata removal offline, retaining original responses and CER values. Applies to all three images; no new inference.',
         'records':[]}
    for r in raw['records']:
        record={'case_id':r['case_id'],'status':r['status'],'initial_cer_including_plain_layout_prefixes':r.get('character_error_rate')}
        if 'response' in r:
            expected=normalize(ds[r['case_id']]['expected_text']);actual=text_only(r['response']['message']['content'])
            record.update(expected_text_normalized=expected,actual_text_normalized=actual,edit_distance=distance(expected,actual),
                          expected_characters=len(expected),corrected_text_cer=distance(expected,actual)/len(expected))
        out['records'].append(record)
    save(HERE/'ocr/analysis.json',out)
    print(json.dumps(out['records'],ensure_ascii=False))

if __name__=='__main__':main()
