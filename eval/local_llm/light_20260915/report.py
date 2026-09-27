"""Offline, auditable report. Never calls an LLM and never changes measured scores."""
import csv,hashlib,html,json,math,statistics
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
OUT=HERE/'report'
SUITES={'rag':'RAG回答','ontology_context':'Ontology資料読解','tool':'ツール選択・引数','ontology':'Ontology実行'}
SIZES={'rag':12,'ontology_context':10,'tool':8,'ontology':10}
def read(p):return json.loads(p.read_text())
def esc(v):return html.escape(str(v))
def csvwrite(name,rows):
    if not rows:return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def ratio(k,n):return f'{k}/{n} ({100*k/n:.1f}%)' if n else '測定不能'
def median(xs):return round(statistics.median(xs),3) if xs else None
def pct(k,n):return round(100*k/n,2) if n else None
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def collect():
    inventory=read(HERE/'inventory.json');ds=read(HERE/'dataset.json');cases={c['id']:c for c in ds['cases']}
    meta=read(HERE/'generation/metadata.json')
    data={}
    for p in list((HERE/'generation').glob('*.json'))+list((HERE/'generation_remaining').glob('*.json')):
        d=read(p)
        if 'model' in d:data[d['model']]=d
    rows=[];detail=[]
    for m in sorted([m for m in inventory['models'] if m['selected'] and m['kind']=='generation' and m['name']!='unlimited-ocr:q8'],key=lambda m:m['size']):
        d=data.get(m['name'],{});cs=d.get('cases',[])
        row={'model':m['name'],'size_GB':round(m['size']/1e9,3),'parameter_size':m['details'].get('parameter_size'),
             'quantization':m['details'].get('quantization_level'),'track':d.get('track','pending'),
             'status':'unavailable' if d.get('unavailable') else 'completed' if len(cs)==50 else 'pending',
             'recorded_cases':len(cs),'error':d.get('warmup_error','')}
        for suite in SUITES:
            rs=[r for r in cs if r['suite']==suite and r['variant']=='original'];k=sum(r['score'].get('correct',False) for r in rs)
            row.update({suite+'_correct':k,suite+'_n':len(rs),suite+'_pct':pct(k,len(rs)),
                        suite+'_values_only':sum(r['score'].get('values_correct',False) for r in rs) if suite!='tool' else None,
                        suite+'_median_s':median([r['elapsed_s'] for r in rs])})
        variants=[r for r in cs if r['variant']=='paraphrase'];paired={r['case_id']:r for r in cs if r['variant']=='original'}
        row['robustness_correct']=sum(r['score'].get('correct',False) for r in variants);row['robustness_n']=len(variants)
        row['pairs_both_correct']=sum(r['score'].get('correct',False) and paired.get(r['base_id'],{}).get('score',{}).get('correct',False) for r in variants)
        row['pairs_changed_correctness']=sum(bool(r['score'].get('correct'))!=bool(paired.get(r['base_id'],{}).get('score',{}).get('correct')) for r in variants)
        row['elapsed_median_s']=median([r['elapsed_s'] for r in cs]);row['elapsed_p95_s']=round(float(np.percentile([r['elapsed_s'] for r in cs],95)),3) if cs else None
        row['errors']=sum(r['status']=='error' for r in cs);row['truncated']=sum(r['status']=='output_truncated' for r in cs)
        row['step_or_repeat_limit']=sum(r['status'] in {'step_limit','repeated_call_limit'} for r in cs)
        row['length_retries']=sum(bool(x.get('retry_reason')) for r in cs for x in r['responses'])
        calls=[c for r in cs if r['suite']=='ontology' for c in r['calls']]
        row['blocked_calls']=sum(bool(c.get('blocked')) for c in calls);row['schema_invalid_calls']=sum(not c.get('schema_valid') for c in calls)
        row['mcp_failed_calls']=sum(not c.get('success') for c in calls)
        row['warmup_s']=d.get('warmup',{}).get('elapsed_s')
        runtime=next((x for x in d.get('runtime',{}).get('models',[]) if x['name']==m['name']),{})
        row['observed_context_length']=runtime.get('context_length');row['observed_VRAM_GB']=round(runtime.get('size_vram',0)/1e9,3) if runtime else None
        responses=[r['response'] for c in cs for r in c['responses']]
        tok=sum(r.get('eval_count',0) for r in responses);ns=sum(r.get('eval_duration',0) for r in responses)
        row['generation_tokens_s']=round(tok/(ns/1e9),2) if ns else None
        row['output_tokens']=tok;row['thinking_chars']=sum(len(r.get('message',{}).get('thinking','')) for r in responses)
        rows.append(row)
        for r in cs:
            detail.append({'model':m['name'],'case_id':r['case_id'],'suite':r['suite'],'variant':r['variant'],'track':r['track'],
                          'correct':r['score'].get('correct',False),'values_correct':r['score'].get('values_correct'),'format_schema_valid':r['score'].get('schema_valid'),
                          'evidence_valid':r['score'].get('evidence_valid'),'status':r['status'],'elapsed_s':round(r['elapsed_s'],3),
                          'call_count':len(r['calls']),'question':cases[r['case_id']]['question'],'expected':json.dumps(cases[r['case_id']].get('expected',cases[r['case_id']].get('expected_call')),ensure_ascii=False),
                          'answer':r['answer'],'error':r.get('error') or '', 'scoring_error':r['score'].get('scoring_error','')})
    return inventory,ds,meta,data,rows,detail

def embeddings():
    out=[];detail=[];raw={}
    inv=read(HERE/'inventory.json')
    for m in sorted([m for m in inv['models'] if m['selected'] and m['kind']=='embedding'],key=lambda m:m['size']):
        p=HERE/'embeddings'/(hashlib.sha256(m['name'].encode()).hexdigest()[:12]+'.json')
        d=read(p) if p.exists() else {};raw[m['name']]=d
        cs=[r for r in d.get('records',[]) if r['repetition']==0]
        row={'model':m['name'],'size_GB':round(m['size']/1e9,3),'status':d.get('status','pending'),'dimensions':d.get('dimensions'),
             'queries':len(cs),'hit1':sum(r['metrics']['hit_at_1'] for r in cs),'hit5':sum(r['metrics']['hit_at_5'] for r in cs),
             'MRR10':round(sum(r['metrics']['mrr_at_10'] for r in cs)/len(cs),4) if cs else None,
             'nDCG10':round(sum(r['metrics']['ndcg_at_10'] for r in cs)/len(cs),4) if cs else None,
             'RRF_hit1':sum(r['rrf_metrics']['hit_at_1'] for r in cs),'RRF_hit5':sum(r['rrf_metrics']['hit_at_5'] for r in cs),
             'query_median_ms':round(statistics.median(r['elapsed_s'] for r in cs)*1000,2) if cs else None,
             'indexing_warm_s':round(sum(b['elapsed_s'] for b in d.get('batches',[])),3) if d.get('batches') else None,
             'warmup_s':d.get('warmup',{}).get('elapsed_s'),'error':d.get('error','')}
        repeated={r['case_id']:r for r in d.get('records',[]) if r['repetition']==1}
        row['repeat_top5_same']=sum(r['ranking'][:5]==repeated.get(r['case_id'],{}).get('ranking',[])[:5] for r in cs)
        out.append(row)
        for r in d.get('records',[]):
            detail.append({'model':m['name'],'case_id':r['case_id'],'repetition':r['repetition'],'query':r['query'],
                          'gold_ids':';'.join(r['gold_ids']),'rank':r['metrics']['rank'],'hit1':r['metrics']['hit_at_1'],'hit5':r['metrics']['hit_at_5'],
                          'rrf_rank':r['rrf_metrics']['rank'],'elapsed_ms':round(r['elapsed_s']*1000,2),'top5':';'.join(r['ranking'][:5])})
    return out,detail,raw

def chart(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    installed={f.name for f in font_manager.fontManager.ttflist}
    font=next((f for f in ['Hiragino Sans','Noto Sans CJK JP','IPAexGothic'] if f in installed),'DejaVu Sans')
    plt.rcParams.update({'font.family':font,'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(1,4,figsize=(15,10.4),sharey=True)
    y=np.arange(len(rows));labels=[r['model'].replace('hf.co/mmnga-o/NVIDIA-Nemotron-Nano-9B-v2-Japanese-gguf:Q8_0','Nemotron-Nano-9B Japanese Q8')+(' *' if r['track']=='json_adapter' else '') for r in rows]
    titles=['RAG回答（12問）','Ontology資料読解（10問）','ツール選択・引数（8問）','Ontology実行（10問）']
    for ax,(s,title) in zip(axs,zip(SUITES,titles)):
        vals=[r[s+'_pct'] or 0 for r in rows]
        ax.barh(y,vals,height=.65,color=['#7c8996' if r['track']=='json_adapter' else '#315976' for r in rows])
        for i,r in enumerate(rows):
            label=f"{r[s+'_correct']}/{r[s+'_n']}" if r[s+'_n'] else 'N/A'
            ax.text(min(vals[i]+2,103),i,label,va='center',fontsize=8)
        ax.set_xlim(0,120);ax.set_xticks([0,50,100]);ax.set_xticklabels(['0%','50%','100%']);ax.set_title(title,loc='left',fontweight='bold');ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    axs[0].set_yticks(y,labels);axs[0].invert_yaxis()
    fig.suptitle('保存20GB以下のローカルモデル｜同じ資料・同じ課題で比較',x=.01,ha='left',fontsize=15,fontweight='bold')
    fig.text(.01,.008,'* ツール利用はJSON補助ハーネス。他はnative API。N/Aは通常APIで測定不能。raw APIによる追加測定は別表。',fontsize=9,color='#4b5660')
    fig.tight_layout(rect=(0,.025,1,.965));fig.savefig(OUT/'accuracy.svg',bbox_inches='tight');fig.savefig(OUT/'accuracy.png',dpi=180,bbox_inches='tight');plt.close(fig)

def main():
    OUT.mkdir(exist_ok=True)
    inv,ds,meta,data,rows,detail=collect();ers,edetail,eraw=embeddings()
    csvwrite('generation_summary.csv',rows);csvwrite('generation_cases.csv',detail);csvwrite('embedding_summary.csv',ers);csvwrite('retrieval_cases.csv',edetail)
    catalog=[{'id':c['id'],'base_id':c['base_id'],'suite':c['suite'],'variant':c['variant'],'question':c['question'],
              'expected':json.dumps(c.get('expected',c.get('expected_call')),ensure_ascii=False)} for c in ds['cases']]
    csvwrite('case_catalog.csv',catalog)
    csvwrite('coverage.csv',[{'model':m['name'],'size_GB':round(m['size']/1e9,3),'kind':'ocr_specialist' if m['name']=='unlimited-ocr:q8' else m['kind'],'selected':m['selected'],'reason':m['selection_reason'],'digest':m['digest']} for m in sorted(inv['models'],key=lambda m:m['size'])])
    chart(rows)
    completed=sum(r['status']=='completed' for r in rows);unavailable=sum(r['status']=='unavailable' for r in rows)
    embdone=sum(r['status']=='completed' for r in ers);emberrors=sum(r['status']=='error' for r in ers)
    ocr_data=read(HERE/'ocr/results.json') if (HERE/'ocr/results.json').exists() else {}
    diag_data=read(HERE/'diagnostics.json') if (HERE/'diagnostics.json').exists() else {}
    prompt_data=read(HERE/'agent_prompt_diagnostic.json') if (HERE/'agent_prompt_diagnostic.json').exists() else {}
    audit_data=read(HERE/'tool_execution_audit.json') if (HERE/'tool_execution_audit.json').exists() else {}
    raw_data=read(HERE/'raw_transport.json') if (HERE/'raw_transport.json').exists() else {}
    finished=all(r['status'] in {'completed','unavailable'} for r in rows) and all(r['status'] in {'completed','error'} for r in ers) and bool(ocr_data.get('finished_at')) and bool(diag_data.get('finished_at')) and bool(prompt_data.get('finished_at')) and bool(audit_data.get('database_unchanged')) and bool(raw_data.get('finished_at'))
    cards=f'<div class="cards"><div><b>31</b>対象タグ<br>生成23・埋め込み7・OCR 1</div><div><b>{len(detail):,}</b>主比較の回答・ツール記録</div><div><b>{len(edetail):,}</b>埋め込み検索記録</div><div><b>{completed} / 23</b>通常APIで50ケース完走<br>通常APIでは測定不能 {unavailable}</div></div>'
    intro='<p class="eyebrow">生成AIセミナー2026 / example_app</p><h1>軽量ローカルモデルの全件評価</h1>'
    intro+=f'<p>2026年9月15日開始。研究室の Ollama {esc(inv["version"]["version"])}。状態：<strong>{"全対象の測定・実行可否確認が完了" if finished else "測定中（暫定値）"}</strong>。</p>'+cards
    intro+='<p>この評価では軽量の範囲を<strong>ローカルに保存されたモデルのサイズが20GB以下（十進GB）</strong>と定義しました。小さなGemma 3、ツール非対応のVLM、日本語Nemotron、1bit量子化のBonsaiも対象です。保存サイズは必要RAM・VRAMとは異なります。全43タグの対象・除外理由は<a href="coverage.csv">coverage.csv</a>で確認できます。クラウド3タグと20GB超9タグは今回の対象外です。</p>'
    intro+='<p>completion能力を申告した24タグすべてに実APIで会話・ツールのプローブを実施。そのうちUnlimited-OCRは文書画像専用と確認したため画像試験に振り分け、残る生成23タグの利用可能なものに同じ50ケースを割り当てます。埋め込み7タグは24検索質問を2回ずつ実行。タグ名はサーバー上の名前で、公式配布モデルとの同一性や別タグ間の独立した重みを保証するものではありません。</p>'
    intro+=f'<p>通常APIが未対応のQwen3.8 MTP版には、raw APIとJSON補助ハーネスによる別条件の全50ケースも追加しています（記録済み {len(raw_data.get("cases",[]))}/50）。起動プローブだけで終えず、利用できた経路での結果を下の補助比較に掲載します。</p>'
    intro+='<p class="notice">ネイティブ呼び出しとJSON補助ハーネスは別の実装条件です。今回の主表はOllama＋実MCPの評価であり、OpenCodeアプリ全体・画面操作のE2E成績ではありません。前回のOpenCode測定は<a href="../../reports/20260915/report.html">前回レポート</a>に残しています。</p>'
    methods='<h2>何を正解とするか</h2>'+table(['評価','基本問題数','成功条件'],[
      ['RAG回答','12','固定した検索結果から回答。正しい値・JSON型・参照ID。該当なし、資料欠落、未記録項目、異なる部品の似た不具合、参照文書中の偽命令も評価。'],
      ['Ontology資料読解','10','ホストが実MCPから事前取得した構造化資料を読み、値を返す。モデル自身によるツール利用は不要。'],
      ['ツール選択・引数','8','最初の応答に正しいツールを1個だけ指定。名前・引数・JSON Schemaを検証。この8問ではツールを実行しない。'],
      ['Ontology実行','10','モデル自身が実MCPを使い、正しい対象・期間・集計条件・関係に基づいて回答。数値だけの偶然の一致は不合格。'],
      ['言い換え確認','10','基本問題のうち10件を言い換えて再実施。RAGは資料順も逆にする。独立した新規問題10問とは扱わない。']])
    methods+='<p>117件の固定報告に、複数CAPAによる二重集計、不適合率の分母ゼロ、損失額未入力を検証する評価専用3報告・3CAPAを加えた隔離SQLiteを使用します。金額・率の正解は固定データから独立に計算済み。LLMによる採点は行っていません。保存・UI操作の実行はハーネスで遮断し、その試行も失敗に含めます。</p>'
    methods+='<p>温度0.2・seed 20260915・コンテキスト32,768・最大8ターン・同一ツール28個。出力上限は4,096、上限到達時だけ8,192で同じ要求を1回再試行し、両応答を保存。Qwen3-VLは事前確認で推論出力を確認したため最初から8,192。thinkingは対応モデルにfalse、GPT-OSSにはlow。1リクエスト160秒・1ケース300秒を上限とし、同一ツール同一引数を3回連続で呼ぶ場合は停止します。タイムアウトなどの上限条件はモデル能力の上限を意味しません。</p>'
    methods+='<p>32,768はAPIへ要求したcontextです。実際に観測したcontextとVRAMは各モデルの詳細・CSVに記録しています。明示していないtop_k・top_p等は、開始時に保存した各タグの <code>show.parameters</code> を継承します。全設定を同一にした重みだけの比較ではなく、このサーバーのタグを記載した条件で使った場合の評価です。</p>'
    methods+='<p>最終JSONは余分な項目を禁止し、数字の文字列・スカラーを包んだ配列は形式不正とします。「値だけ一致」は補助指標として別表に残します。単一のJSONコードブロックは受理します。Ontologyの同等な正解経路は前回の根拠監査規則を測定前に固定して使用。今回の結果を見て正解規則を追加していません。再試行時間を含む待ち時間を記録し、ウォームアップは主表の中央値から除外しています。</p>'
    methods+='<p>「値だけ一致」も単一JSONから採点できた値の指標です。JSONにならない自然文の意味的正しさは全件採点していません。例えばQwen3.5:2bのO01は正しい根拠と数値を自然文で返しましたが、JSON形式に失敗しています。<a href="../lecture_examples.md">講義用の実測例</a>で、形式違反・値の誤り・対象条件の欠落を分けて説明します。Ontology資料読解10問と実行10問は同じ業務質問の対応比較で、資料を事前に渡すか自分で取得するかを変えています。</p>'
    head=['モデル / 保存GB','ツール経路','RAG /12','資料読解 /10','選択・引数 /8','Ontology実行 /10','言い換え /10','Ontology中央値']
    trs=[]
    for i,r in enumerate(rows):
        vals=[f'<a href="#model-{i}">{esc(r["model"])}</a><br><small>{r["size_GB"]} GB</small>', 'JSON補助' if r['track']=='json_adapter' else 'ネイティブ']
        for s in SUITES:vals.append(ratio(r[s+'_correct'],r[s+'_n']))
        vals.append(ratio(r['robustness_correct'],r['robustness_n']));vals.append(f'{r["ontology_median_s"]} 秒' if r['ontology_median_s'] is not None else '—')
        trs.append(vals)
    result='<h2>生成・ツール評価の結果</h2><p>基本40問の結果を主表に示し、言い換え10件を別列にしています。通常の会話APIを使えないタグは主表では測定不能と表示し、raw APIによる補助実験を別に掲載します。</p>'+table(head,trs)
    if completed+unavailable==23:
        small=next(r for r in rows if r['model']=='qwen3.5:4b')
        full=[r['model'] for r in rows if r['ontology_n']==10 and r['ontology_correct']==10]
        if small['status']=='completed':
            result+=f'<p>例えば保存サイズ{small["size_GB"]} GBの <b>qwen3.5:4b</b> は、固定資料からのRAG回答 {ratio(small["rag_correct"],12)}、最初のツール選択 {ratio(small["tool_correct"],8)}、実際のOntology処理 {ratio(small["ontology_correct"],10)} でした。選択ができることと、一連の処理を根拠付きで完了できることを分けて読む必要があります。</p>'
        if full:result+='<p>Ontologyの基本10問をすべて通過したタグは <b>'+esc('、'.join(full))+'</b>。これは今回の小規模な業務課題と設定での結果であり、未知の質問への100%の正答を保証するものではありません。</p>'
    svg=(OUT/'accuracy.svg').read_text();svg=svg[svg.index('<svg'):]
    result+='<div class="chart">'+svg+'</div>'
    value_rows=[]
    for r in rows:
        value_rows.append([esc(r['model'])]+[ratio(r[s+'_values_only'],r[s+'_n']) for s in ['rag','ontology_context','ontology']]+[str(r['errors']),str(r['truncated']),str(r['step_or_repeat_limit']),str(r['blocked_calls']),str(r['length_retries'])])
    result+='<details><summary>値だけの一致・実行エラー・上限到達・遮断された操作</summary><p>値だけの一致には型違反や根拠未取得の回答も含まれます。主表の成功率に置き換えてはいけません。</p>'+table(['モデル','RAG値','資料値','Ontology値','APIエラー','出力上限','反復/手数上限','遮断操作','出力再試行'],value_rows)+'</details>'
    if (HERE/'tool_execution_audit.json').exists():
        ta=read(HERE/'tool_execution_audit.json');tr=[];tc=[]
        for r in rows:
            cs=[c for c in ta['records'] if c['model']==r['model'] and c['variant']=='original' and c['status']!='ui_not_executed']
            tr.append([esc(r['model']),ratio(sum(c['main_first_call_correct'] for c in cs),len(cs)),ratio(sum(c['execution_validated_success'] for c in cs),len(cs))])
        for c in ta['records']:
            tc.append({'model':c['model'],'case_id':c['case_id'],'variant':c['variant'],'status':c['status'],'main_first_call_correct':c['main_first_call_correct'],
                       'execution_validated_success':c['execution_validated_success'],'actual_call':json.dumps(c.get('call'),ensure_ascii=False)})
        csvwrite('tool_execution_audit.csv',tc)
        result+='<details><summary>追加監査：単発サービスツールを実際に実行できるか（基本6問）</summary><p>公開JSON Schemaが表現していないアプリ内部の制約も確認するため、保存済みの最初のツール指示を隔離MCPへ再送しました。UIの2問を除く参照・事前検証6問が対象。許可外の操作は実行しません。主表の最初の選択・Schema成績は置き換えず、実行も受理された件数を併記します。</p>'+table(['モデル','選択・Schema','選択・Schema＋実MCP実行'],tr)+'<p><a href="../tool_execution_audit.json">追加監査の実出力</a> / <a href="tool_execution_audit.csv">監査CSV</a></p></details>'
    emb='<h2>埋め込みモデルと検索精度</h2><p>117文書×24質問。本文・原因・対策の同じテキストを全モデルへ渡し、モデルごとの公式推奨query/document接頭辞を付けます。ベクトルをL2正規化して全件とcosine比較。各質問は2回測定し、主表は1回目、再現性は上位5件の一致で示します。RRFはBM25上位50件とdense上位50件を k=60・同じ重みで融合。正解を見て重みを調整していません。</p>'
    emb+='<p>文書は8件ずつAPIへ送り、バッチ要求がHTTPエラーになった場合はエラーを保存して同じ入力を1件ずつ再送します。その時間も索引作成時間に含めます。入力の切り捨ては禁止し、検索順位・ベクトル・再送記録を保存しています。</p>'
    emb+='<p>検索24問は前回の6問と、今回のCodexが固定報告を読んで作成した言い換え18問です。独立した人間の評価者による関連性アノテーションは行っていません。正解は対象の報告IDとして固定し、評価対象のOllamaモデルに正解を作らせたり、LLM judgeに採点させたりしていません。固定ソース中の作成主体の誤記は<a href="../README.md">評価仕様</a>で訂正しています。</p>'
    erows=[]
    for r in ers:
        erows.append([esc(r['model']),str(r['size_GB']),str(r['dimensions'] or '—'),ratio(r['hit1'],r['queries']),ratio(r['hit5'],r['queries']),str(r['MRR10'] if r['MRR10'] is not None else '—'),ratio(r['RRF_hit1'],r['queries']),ratio(r['RRF_hit5'],r['queries']),str(r['query_median_ms'] or '—'),ratio(r['repeat_top5_same'],r['queries'])])
    emb+=table(['モデル','GB','次元','Hit@1','Hit@5','MRR@10','RRF Hit@1','RRF Hit@5','query中央値ms','再試行Top5一致'],erows)
    if all(r['status'] in {'completed','error'} for r in ers):
        eg=next(r for r in ers if r['model']=='embeddinggemma:latest')
        if eg['queries']==24:
            emb+=f'<p>例えばEmbeddingGemmaは、dense単独からRRFへ変更するとHit@1が {eg["hit1"]}/24 → {eg["RRF_hit1"]}/24、Hit@5が {eg["hit5"]}/24 → {eg["RRF_hit5"]}/24 でした。最上位の正確さと、上位候補に正解を残すことは別の指標です。融合を追加する場合も両方を確認します。</p>'
    if (HERE/'retrieval_baselines.json').exists():
        bas=read(HERE/'retrieval_baselines.json');br=[]
        for key,name in [('bm25','BM25（同義語追加なし）'),('e5','既存 e5-small（CPU・別ホスト）')]:
            cs=bas[key];br.append([name,ratio(sum(c['hit_at_1'] for c in cs),len(cs)),ratio(sum(c['hit_at_5'] for c in cs),len(cs)),f'{sum(c["mrr_at_10"] for c in cs)/len(cs):.4f}'])
        emb+='<p>同じ検索問題・本文で測定した比較用ベースライン：</p>'+table(['手法','Hit@1','Hit@5','MRR@10'],br)
    for r in ers:
        if r['error']:emb+=f'<p class="notice"><b>{esc(r["model"])}</b>：{esc(r["error"])}</p>'
    emb+='<p>Hit@kは正解の報告が上位k件に入る割合、MRR@10は最上位正解の順位の逆数（10位以内）、nDCG@10は順位に対する対数割引です。このセットは各質問に正解1件を付けた小規模評価で、未知の業務質問全般への性能を保証しません。数値や部品名を含む質問が多く、BM25に有利な性質も残ります。</p>'
    audit='<h2>各モデルの質問・回答・実ツール呼び出し</h2><p>質問を展開すると回答、採点結果、ツールの引数と実出力を確認できます。全system/user入力とOllamaの生応答（推論出力・トークン数を含む）は各モデルのJSONに保存しています。</p>'
    for i,r in enumerate(rows):
        d=data.get(r['model'],{});key=hashlib.sha256(r['model'].encode()).hexdigest()[:12]
        rawpath=next((HERE/directory/(key+'.json') for directory in ['generation','generation_remaining'] if (HERE/directory/(key+'.json')).exists()),None)
        rawlink=f'<a href="../{rawpath.relative_to(HERE)}">生の測定JSON</a>' if rawpath else '測定待ち'
        audit+=f'<details id="model-{i}" class="model"><summary>{esc(r["model"])} — {r["recorded_cases"]}/50 ケース</summary><p>{rawlink} / 観測context {esc(r["observed_context_length"])} / 観測VRAM {esc(r["observed_VRAM_GB"])} GB</p>'
        if r['error']:audit+='<p class="notice">'+esc(r['error'])+'</p>'
        for c in d.get('cases',[]):
            case=next(x for x in ds['cases'] if x['id']==c['case_id'])
            audit+='<details class="case"><summary>'+esc(c['case_id']+' '+('成功' if c['score'].get('correct') else '不成功')+' / '+c['status']+f' / {c["elapsed_s"]:.2f}s — '+case['question'])+'</summary>'
            audit+='<p>出力：</p><pre>'+esc(c['answer'])+'</pre><p>採点：</p><pre>'+esc(json.dumps(c['score'],ensure_ascii=False,indent=2))+'</pre>'
            if c['calls']:audit+='<p>実呼び出し（tool選択問題は未実行）：</p><pre>'+esc(json.dumps(c['calls'],ensure_ascii=False,indent=2))+'</pre>'
            if c.get('error'):audit+='<p>'+esc(c['error'])+'</p>'
            audit+='</details>'
        audit+='</details>'
    ocr='<h2>OCR専用モデル：画像入力の動作確認</h2>'
    amendment=read(HERE/'scope_amendment.json') if (HERE/'scope_amendment.json').exists() else {}
    ocr+=f'<p>Unlimited-OCRは<a href="https://github.com/baidu/Unlimited-OCR">文書画像を解析する専用モデル</a>です。通常Q&Aを{amendment.get("completed_off_label_cases",0)}件実施した時点で反復出力が続いたため、このタグの汎用Q&A連続測定を打ち切り、合成した日本語文書画像3枚の試験へ切り替えました。この変更は<a href="../scope_amendment.json">適用範囲の変更記録</a>に残しています。</p>'
    ocrkey=hashlib.sha256('unlimited-ocr:q8'.encode()).hexdigest()[:12]
    ocr+=f'<p><a href="../generation/{ocrkey}.json">打ち切り前のQ&A失敗ログ</a>は保存し、生成モデルの順位表には混ぜません。画像では公式の <code>document parsing.</code> 指示を使い、報告書ID・機械名の一致と文字誤り率CERを確認します。CERは全文の編集距離÷正解文字数で、0が完全一致。空白・Unicode幅・検出座標と領域ラベル・HTML/Markdownの装飾を正規化し、挿入が多い場合は1を超えます。Ollamaでは公式例の独自no-repeat-ngram processorを同条件で適用していません。</p>'
    if ocr_data.get('records'):
        oa=read(HERE/'ocr/analysis.json') if (HERE/'ocr/analysis.json').exists() else {}
        oa={r['case_id']:r for r in oa.get('records',[])}
        ocr+=table(['画像','状態','IDと機械名','本文の文字誤り率 CER','待ち時間'],[[f'<a href="../ocr/{esc(r["image"])}">{esc(r["case_id"])}</a>',esc(r['status']),str(r.get('identifiers_correct','—')),f'{oa[r["case_id"]]["corrected_text_cer"]:.4f}' if r['case_id'] in oa and 'corrected_text_cer' in oa[r['case_id']] else '本文抽出の確認待ち',f'{r["elapsed_s"]:.2f} 秒'] for r in ocr_data['records']])
        if oa:
            ocr+='<p>本文抽出の訂正：このAPIは領域種別と座標を <code>header [47, 62, 361, 105]</code> のように返し、初期集計はこれを本文に混入させていました。既知の領域接頭辞を除いて全3件の保存済み出力からCERを再計算しています。元の高いCER・生応答を残し、変更理由と抽出前後のテキストを<a href="../ocr/analysis.json">再集計記録</a>に示します。本文では3枚とも「評価」が「評估」となる1文字の誤りがあり、IDと設備名は一致しました。</p>'
        ocr+='<p><a href="../ocr/results.json">画像試験の全応答</a> / <a href="../ocr/dataset.json">画像の正解文字列</a>。清潔な合成画像3枚の動作確認であり、実帳票のOCR一般性能やRAG回答精度を示すものではありません。</p>'
    else:ocr+='<p>画像試験は測定待ち。</p>'
    diagnostics='<h2>設定を変えた補助実験</h2>'
    if (HERE/'diagnostics.json').exists():
        diag=read(HERE/'diagnostics.json');cr=diag.get('gemma_structured',[]);dr=[]
        for r in rows:
            if not r['model'].startswith('gemma3:'):continue
            cs=[c for c in cr if c['model']==r['model']]
            dr.append([esc(r['model']),ratio(r['rag_correct'],r['rag_n']),ratio(sum(c['score']['correct'] for c in cs),len(cs))])
        diagnostics+='<p>主測定でGemma 3の小型タグが回答の代わりにSchemaを返したため、事後の切り分けとして<strong>Gemma 3の全4タグ・基本RAG全12問</strong>を、簡潔な質問文＋APIの <code>format: JSON Schema</code> で再実行しました。本文プロンプトとAPI制約を同時に変更した補助実験です。元の失敗記録と主表を置き換えず、設定次第で使える範囲が変わるかを確認します。</p>'
        diagnostics+=table(['モデル','主測定 RAG','簡潔な指示＋API形式制約 RAG'],dr)
        for r in diag.get('raw_probes',[]):
            diagnostics+='<p><b>'+esc(r['model'])+'</b> の <code>/api/generate raw:true</code> 起動診断：HTTP '+esc(r.get('http_status','—'))+'。</p><pre>'+esc(json.dumps(r.get('response',r.get('error')),ensure_ascii=False,indent=2))+'</pre>'
        diagnostics+='<p>この2件のraw API呼び出しは短い起動確認です。全要求・応答は<a href="../diagnostics.json">診断JSON</a>に保存しています。Qwen3.8 MTP版は応答できたため、下記の別条件で全50ケースの追加測定へ進めました。ネイティブツール対応の証明にはなりません。</p>'
        csvwrite('structured_diagnostics.csv',[{'model':r['model'],'case_id':r['case_id'],'correct':r['score']['correct'],'status':r['status'],'elapsed_s':r['elapsed_s'],'answer':r['answer']} for r in cr])
    else:diagnostics+='<p>測定待ち。主測定と推論を同時実行しません。</p>'
    if (HERE/'agent_prompt_diagnostic.json').exists():
        pd=read(HERE/'agent_prompt_diagnostic.json');pr=[];pc=[]
        for r in rows:
            if r['model'] not in pd['models']:continue
            cs=[c for c in pd['records'] if c['model']==r['model'] and c['variant']=='original']
            bs=[c for c in pd['records'] if c['model']==r['model'] and c['variant']=='paraphrase']
            pr.append([esc(r['model']),ratio(r['ontology_correct'],r['ontology_n']),ratio(sum(c['score']['correct'] for c in cs),len(cs)),ratio(sum(c['score']['correct'] for c in bs),len(bs))])
        diagnostics+='<p><strong>Qwen3.5の小型5タグ：ツール実行を先に行う指示の明確化。</strong>主測定でツールを呼ばず最終JSONを作る例を観測したため、事後の追加実験として全5タグ・同じOntology14ケースに、形式指定は最終回答だけに適用する旨を明記しました。他の設定・採点は共通。元の主表を置き換えるものではなく、プロンプトの伝わり方に対する診断です。</p><pre>'+esc(pd['clarification'])+'</pre>'+table(['モデル','主測定 基本10問','明確化後 基本10問','明確化後 言い換え4件'],pr)
        diagnostics+='<p><a href="../agent_prompt_diagnostic.json">明確化したプロンプトと全応答</a></p>'
        csvwrite('agent_prompt_diagnostics.csv',[{'model':r['model'],'case_id':r['case_id'],'variant':r['variant'],'correct':r['score']['correct'],'status':r['status'],'elapsed_s':r['elapsed_s'],'answer':r['answer']} for r in pd['records']])
    diagnostics+='<h2>通常の会話APIを迂回したMTP版の全50ケース</h2><p><code>qwen3.8:27b-mtp-q4_K_M</code> の会話APIはunknown rendererエラーでしたが、<a href="https://docs.ollama.com/api/generate">raw generation API</a>では応答しました。そのため、手動のChatMLテンプレートと、明示したJSON補助ハーネスで全50ケースを追加測定しています。思考区間を閉じたassistant接頭辞を用い、ネイティブのツール解析を迂回します。問題・採点・ターン上限・出力上限・実MCPの許可範囲は共通ですが、通信とプロンプト整形の経路が異なる補助比較です。元の通常APIのエラーは残します。</p>'
    if raw_data.get('cases'):
        rc=raw_data['cases'];rr=[];csvrows=[]
        for s in SUITES:
            cs=[c for c in rc if c['suite']==s and c['variant']=='original'];k=sum(c['score']['correct'] for c in cs)
            rr.append([SUITES[s],ratio(k,len(cs)),str(median([c['elapsed_s'] for c in cs]))+' 秒'])
            csvrows.append({'model':raw_data['model'],'track':raw_data['track'],'suite':s,'correct':k,'n':len(cs),'median_s':median([c['elapsed_s'] for c in cs])})
        vs=[c for c in rc if c['variant']=='paraphrase'];rr.append(['言い換え',ratio(sum(c['score']['correct'] for c in vs),len(vs)),'—'])
        csvrows.append({'model':raw_data['model'],'track':raw_data['track'],'suite':'paraphrase','correct':sum(c['score']['correct'] for c in vs),'n':len(vs),'median_s':median([c['elapsed_s'] for c in vs])})
        diagnostics+=table(['評価','成功','待ち時間中央値'],rr)+'<p><a href="../raw_transport.json">全要求・応答と実MCP出力</a> / <a href="raw_transport_summary.csv">集計CSV</a> / <a href="../run_raw_transport.py">追加経路の実装</a></p>'
        csvwrite('raw_transport_summary.csv',csvrows)
        for c in rc:
            diagnostics+='<details><summary>'+esc(c['case_id']+' / '+str(c['score']['correct'])+' / '+c['status'])+'</summary><pre>'+esc(json.dumps({'question':next(x['question'] for x in ds['cases'] if x['id']==c['case_id']),'answer':c['answer'],'score':c['score'],'calls':c['calls']},ensure_ascii=False,indent=2))+'</pre></details>'
    else:diagnostics+='<p>全50ケースの追加測定待ち。</p>'
    limitations='<h2>解釈上の限界と再現</h2><p>これは example_app の日本語品質管理データに対する回帰評価です。40基本問題・固定seed1つであり、モデル一般のランキングや厳密な統計的優劣を示すものではありません。言い換え10件は対応のある確認で、母数を50独立問題に水増ししません。RAGASのLLM judgeや自由文全体のfaithfulness評価、網羅的な画像/OCR精度評価、同時接続負荷試験、OpenCodeの本番UI操作は今回の測定対象外です。OCR専用タグには合成画像3枚の動作確認を別途実施しています。</p>'
    limitations+='<p>同じサーバーに対してこのベンチマークの推論は直列に実行しています。他利用者の負荷とGPU機種・総RAMは未確認。観測VRAMはAPI報告値でピーク値ではありません。温度やcontext、ツール数を変更すれば結果は変わります。前回の768トークン上限の結果とは設問・形式・上限が異なり、単純な差分を改善効果と解釈しません。</p>'
    limitations+='<p>検索と回答生成を分離した評価であり、全埋め込みモデル×全生成モデルの組合せでRAG全体を測定したものではありません。生成時は固定コンテキスト、検索時は固定24問で比較しています。実行環境と依存バージョンは<a href="../environment.json">environment.json</a>に保存しました。</p>'
    limitations+='<p><a href="../README.md">再実行手順・設定</a> / <a href="generation_summary.csv">生成モデル集計CSV</a> / <a href="generation_cases.csv">全回答ケースCSV</a> / <a href="embedding_summary.csv">埋め込み集計CSV</a> / <a href="retrieval_cases.csv">検索ケースCSV</a> / <a href="case_catalog.csv">設問・正解一覧</a> / <a href="../dataset.json">固定データセット</a></p>'
    limitations+='<p>一次資料：<a href="https://docs.ollama.com/capabilities/tool-calling">Ollama Tool calling</a>、<a href="https://docs.ollama.com/capabilities/thinking">Thinking</a>、<a href="https://docs.ollama.com/api/embed">Embed API</a>、<a href="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B">Qwen3 Embedding</a>、<a href="https://ai.google.dev/gemma/docs/embeddinggemma/model_card">EmbeddingGemma</a>、<a href="https://huggingface.co/jinaai/jina-embeddings-v5-text-nano-retrieval">Jina nano retrieval</a>、<a href="https://huggingface.co/jinaai/jina-embeddings-v5-text-small-retrieval">Jina small retrieval</a>、<a href="https://huggingface.co/nvidia/Nemotron-3-Embed-1B-BF16">Nemotron 3 Embed</a>。実際の評価対象は保存したdigestのローカルタグです。</p>'
    css='''body{margin:0;background:#f5f6f7;color:#26333c;font-family:-apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN",sans-serif;line-height:1.75}main{max-width:1480px;padding:40px 32px;margin:auto}h1{font-size:32px;letter-spacing:.02em;margin:.2em 0}h2{font-size:24px;margin-top:52px;border-bottom:2px solid #315976;padding-bottom:8px}p{max-width:1100px}.eyebrow{font-size:13px;color:#657480}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}.cards>div{background:white;border:1px solid #d7dfe5;padding:18px}.cards b{display:block;font-size:32px;color:#315976}a{color:#245b7d;overflow-wrap:anywhere}.scroll{overflow-x:auto;max-width:100%}table{border-collapse:collapse;background:white;width:100%;font-size:13px;margin:12px 0}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid #d7dfe5;vertical-align:top}th{background:#e8edf1;white-space:nowrap}td:first-child{max-width:320px;overflow-wrap:anywhere}td:not(:first-child){min-width:65px}tr:hover{background:#f2f5f7}details{background:white;border:1px solid #d7dfe5;padding:14px;margin:12px 0}summary{cursor:pointer;overflow-wrap:anywhere;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f4f6;padding:15px;font-size:12px;line-height:1.65}.case{margin:10px 0}.notice{padding:14px 18px;background:#e8edf1;border-left:4px solid #56718a}.chart svg{width:100%;height:auto}.chart{background:#fff;padding:12px;margin-top:24px}small{color:#657480}@media(max-width:700px){main{padding:20px 14px}h1{font-size:25px}.cards{grid-template-columns:repeat(2,1fr);gap:8px}.cards>div{padding:12px}.cards b{font-size:26px}h2{font-size:21px}.chart{overflow-x:auto}.chart svg{min-width:950px}details{padding:10px}}'''
    doc='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>軽量ローカルモデル全件評価</title><style>'+css+'</style><main>'+intro+methods+result+emb+ocr+diagnostics+audit+limitations+'</main></html>'
    (OUT/'report.html').write_text(doc)
    save={'generated_at':datetime.now(timezone.utc).isoformat(),'report_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'complete':finished,'generation_completed_models':completed,'generation_unavailable_models':unavailable,'generation_records':len(detail),
          'embedding_completed_models':embdone,'embedding_error_models':emberrors,'embedding_records':len(edetail),'database_unchanged':meta.get('database_unchanged'),
          'ocr_records':len(ocr_data.get('records',[])),'off_label_ocr_records':amendment.get('completed_off_label_cases',0),'structured_diagnostic_records':len(diag_data.get('gemma_structured',[])),
          'raw_transport_records':len(raw_data.get('cases',[])),
          'agent_prompt_diagnostic_records':len(read(HERE/'agent_prompt_diagnostic.json').get('records',[])) if (HERE/'agent_prompt_diagnostic.json').exists() else 0}
    (OUT/'summary.json').write_text(json.dumps(save,ensure_ascii=False,indent=2));print(json.dumps(save,ensure_ascii=False))

if __name__=='__main__':main()
