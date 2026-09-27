"""保存済み出力だけで集計。追加のLLM/API呼び出しは行わない。"""
from __future__ import annotations
import csv
import html
import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path

from benchmark import HERE, fact_equal, matches_call

RUN = HERE / 'runs/native_v1_20260915'
OUT = HERE / 'reports/20260915'
SUITES = ('rag', 'tool', 'ontology')
LABELS = {'rag': 'RAG回答', 'tool': 'ツール選択・引数', 'ontology': 'Ontology Q&A'}


def value_score(case, result):
    """補助指標: 単一要素配列だけを正規化。複数候補から正解を選び出さない。

    初期実行で形式違反を発見した後に追加した分析。元の厳密採点は保存する。
    """
    if case['suite'] == 'tool':
        return result['score']['correct']
    text = result.get('answer', '')
    fenced = re.findall(r'```(?:json)?\s*([\s\S]*?)```', text)
    try:
        if fenced:
            obj = json.loads(fenced[-1])
        else:
            from benchmark import parse_json
            obj = parse_json(text)
    except ValueError:
        return False
    if isinstance(obj, list) and len(obj) == 1:
        obj = obj[0]
    if not isinstance(obj, dict):
        return False
    for key, expected in case['expected'].items():
        if key not in obj:
            return False
        actual = obj[key]
        if not isinstance(expected, list) and isinstance(actual, list) and len(actual) == 1:
            actual = actual[0]
        if not fact_equal(actual, expected):
            return False
    return True


def passed(case, result):
    if result['status'] != 'completed' or result.get('error'):
        return False
    if not value_score(case, result):
        return False
    if case['suite'] == 'rag':
        return bool(result['score']['citation_supported'])
    if case['suite'] == 'ontology':
        return bool(result['score']['tool_workflow_correct'])
    return True


def grounded(case, result):
    """事後追加した根拠取得の監査。文字列の完全一致以外の同等経路も許容。

    数値だけの偶然の一致、本文での実行主張、別対象・条件落ちを正解にしない。
    元のscoreとpassedは変更しない。
    """
    if case['suite']!='ontology':return passed(case,result)
    if result['status']!='completed' or result.get('error') or not value_score(case,result):return False
    if result['score'].get('forbidden_called'):return False
    cs=[c for c in result.get('calls',[]) if c.get('success') and c.get('schema_valid')]
    cid=case['id']
    if cid in {'O01','O02','O03','O04','O09'}:
        required=next(c for c in case['required_calls'] if c.get('name')=='query_quality_ontology')
        return any(matches_call(c,required) and isinstance(c.get('output'),dict)
                   and all(k in c['output'].get('metrics',{}) and fact_equal(c['output']['metrics'][k],v)
                           for k,v in case['expected'].items()) for c in cs)
    if cid in {'O05','O06','O08'}:
        return bool(result['score'].get('tool_workflow_correct'))
    if cid=='O07':
        needed={'BENCH設備A','BENCH設備B'}
        for c in cs:
            args=c['arguments'];out=c.get('output')
            if c['name']=='resolve_ontology_entity' and args.get('object_type')=='MachineLabel' and isinstance(out,dict):
                names={x.get('label') for x in out.get('candidates',[]) if isinstance(x,dict)}
                if out.get('can_auto_select') is False and needed<=names:return True
            if c['name']=='list_masters' and args.get('category')=='machine':
                # マスター全件はAPIにページングがない。機械名2候補の存在を実出力で確認。
                def names_in(node):
                    if isinstance(node,dict):
                        return ({node['name']} if isinstance(node.get('name'),str) else set()) | set().union(*(names_in(v) for v in node.values()))
                    if isinstance(node,list):return set().union(*(names_in(v) for v in node))
                    if isinstance(node,str):return {node}
                    return set()
                if needed<=names_in(out):return True
        return False
    if cid=='O10':
        if result['score'].get('tool_workflow_correct'):return True
        target=case['expected']['report_id'];machine=case['expected']['machine_name']
        def has_field(node,key,value):
            if isinstance(node,dict):
                return node.get(key)==value or any(has_field(v,key,value) for v in node.values())
            if isinstance(node,list):return any(has_field(v,key,value) for v in node)
            return False
        for i,c in enumerate(cs):
            a=c['arguments']
            capa=(c['name']=='get_ontology_object' and a.get('object_type')=='CapaAction' and a.get('object_id')=='CA-BENCH-1') or (c['name']=='resolve_ontology_entity' and a.get('object_type')=='CapaAction' and a.get('query')=='CA-BENCH-1')
            if not capa or not has_field(c.get('output'),'defect_id',target):continue
            for following in cs[i+1:]:
                a=following['arguments']
                report=(following['name']=='get_ontology_object' and a.get('object_type')=='DefectReport' and a.get('object_id')==target) or (following['name']=='get_defect_report' and a.get('defect_id')==target)
                if report and has_field(following.get('output'),'machine_name',machine):return True
        return False
    return False


def pct(k, n):
    return f'{100*k/n:.1f}%' if n else '—'


def cell(k, n):
    return f'{k}/{n} ({pct(k,n)})' if n else '測定不能'


def percentile(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    idx = (len(xs)-1)*p
    lo = math.floor(idx)
    hi = math.ceil(idx)
    return xs[lo] + (xs[hi]-xs[lo])*(idx-lo)


def wilson(k, n):
    if not n:
        return None, None
    z = 1.96
    p = k/n
    den = 1+z*z/n
    mid = (p+z*z/(2*n))/den
    d = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return mid-d, mid+d


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def collect():
    dataset = json.loads((HERE/'dataset.json').read_text())
    cases = {c['id']:c for c in dataset['cases']}
    meta = json.loads((RUN/'metadata.json').read_text())
    data = {}
    for p in RUN.glob('*.json'):
        d = json.loads(p.read_text())
        if 'model' in d:
            data[d['model']] = d
    summary = []
    detail = []
    for name in meta['models']:
        d = data.get(name, {'cases':[]})
        results = d.get('cases', [])
        row = {'model':name, 'completed_cases':len(results), 'load_error':d.get('warmup_error','')}
        for suite in SUITES:
            rs = [r for r in results if r['suite'] == suite]
            n = len(rs)
            k = sum(passed(cases[r['case_id']], r) for r in rs)
            row.update({suite+'_correct':k, suite+'_n':n, suite+'_pct':round(k/n*100,2) if n else None,
                        suite+'_strict':sum(bool(r['score']['correct']) for r in rs),
                        suite+'_values_only':sum(value_score(cases[r['case_id']],r) for r in rs),
                        suite+'_median_s':round(statistics.median(r['elapsed_s'] for r in rs),2) if rs else None})
            lo,hi = wilson(k,n)
            row[suite+'_wilson_low'] = lo
            row[suite+'_wilson_high'] = hi
        calls = [c for r in results if r['suite']=='ontology' for c in r['calls']]
        row['tool_name_correct'] = sum(bool(r['score']['tool_name_correct']) for r in results if r['suite']=='tool')
        row['ontology_calls'] = len(calls)
        row['ontology_schema_valid'] = sum(bool(c.get('schema_valid')) for c in calls)
        row['ontology_calls_succeeded'] = sum(bool(c.get('success')) for c in calls)
        row['ontology_calls_failed'] = sum(not c.get('success') for c in calls)
        row['ontology_workflow_correct'] = sum(bool(r['score']['tool_workflow_correct']) for r in results if r['suite']=='ontology')
        row['ontology_grounded_correct'] = sum(grounded(cases[r['case_id']],r) for r in results if r['suite']=='ontology')
        row['ontology_grounded_pct'] = 100*row['ontology_grounded_correct']/row['ontology_n'] if row['ontology_n'] else None
        row['ontology_grounded_wilson_low'],row['ontology_grounded_wilson_high'] = wilson(row['ontology_grounded_correct'],row['ontology_n'])
        row['errors'] = sum(r['status'] != 'completed' for r in results)
        row['truncated'] = sum(r['status']=='output_truncated' for r in results)
        row['step_limit'] = sum(r['status']=='step_limit' for r in results)
        row['warmup_s'] = d.get('warmup',{}).get('elapsed_s')
        row['latency_p95_s'] = percentile([r['elapsed_s'] for r in results],.95)
        generated = [x['response'] for r in results for x in r['responses']]
        total_tokens = sum(x.get('eval_count',0) for x in generated)
        eval_ns = sum(x.get('eval_duration',0) for x in generated)
        row['generation_tok_s'] = total_tokens/(eval_ns/1e9) if eval_ns else None
        row['input_tokens_sum'] = sum(x.get('prompt_eval_count',0) for x in generated)
        row['output_tokens_sum'] = total_tokens
        summary.append(row)
        for r in results:
            case = cases[r['case_id']]
            detail.append({'model':name,'case_id':r['case_id'],'suite':r['suite'],
                'correct_normalized':passed(case,r),'correct_strict':r['score']['correct'],
                'correct_with_evidence':grounded(case,r),
                'values_only':value_score(case,r),'workflow_correct':r['score'].get('tool_workflow_correct'),
                'status':r['status'],'elapsed_s':round(r['elapsed_s'],3),'call_count':len(r['calls']),
                'schema_errors':sum(not c.get('schema_valid') for c in r['calls']),
                'question':case['question'], 'answer':r.get('answer',''), 'error':r.get('error') or '',
                'calls':json.dumps(r['calls'],ensure_ascii=False)})
    return dataset, meta, data, summary, detail


def chart(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family'] = ['Hiragino Sans', 'DejaVu Sans']
    selected = [r for r in rows if r['completed_cases']==24]
    if not selected:
        return
    fig, axes = plt.subplots(1,3,figsize=(15,max(5,len(selected)*.40)),sharey=True)
    colors = ['#34566d','#608097','#91a5b3']
    for ax,suite,color in zip(axes,SUITES,colors):
        values = [100*r['ontology_grounded_correct']/r['ontology_n'] if suite=='ontology' else r[suite+'_pct'] for r in selected]
        ax.barh(range(len(selected)),values,color=color,height=.64)
        for i,r in enumerate(selected):
            k=r['ontology_grounded_correct'] if suite=='ontology' else r[suite+'_correct']
            ax.text(min(values[i]+2,104),i,f"{k}/{r[suite+'_n']}",va='center',fontsize=9)
        ax.set_xlim(0,120)
        ax.set_xticks([0,25,50,75,100],['0','25','50','75','100%'])
        ax.grid(axis='x',alpha=.15)
        ax.set_axisbelow(True)
        ax.set_title({'rag':'RAG：回答値＋引用（6問）',
                      'tool':'初回ツール：名前＋引数（8問）',
                      'ontology':'Ontology：根拠付きQ&A（10問）'}[suite],fontsize=11,pad=14)
        for spine in ax.spines.values():
            spine.set_visible(False)
    axes[0].set_yticks(range(len(selected)),[r['model'] for r in selected],fontsize=9)
    axes[0].invert_yaxis()
    fig.suptitle('ローカルOllamaの実測比較｜単一要素配列・同等の取得経路を許容',fontsize=14,x=.57)
    fig.tight_layout(rect=[0,0,1,.96])
    fig.savefig(OUT/'accuracy.png',dpi=170,bbox_inches='tight')
    fig.savefig(OUT/'accuracy.svg',bbox_inches='tight')
    plt.close(fig)


def report(dataset, meta, data, rows, details):
    finished = bool(meta.get('finished_at'))
    completed = [r for r in rows if r['completed_cases']==24]
    retrieval = dataset['retrieval']
    n = len(retrieval)
    txt = [f'# ローカルLLMベンチマーク — 2026年9月15日', '',
      '実測結果。'+('測定完了。' if finished else '**測定途中の暫定出力。**'),
      f"研究室の Ollama(OLLAMA_BASE_URL)のローカル・ツール対応20タグを対象に、各24問を1回ずつ実行。{len(completed)} タグで全設問の試行が終わり、{sum(r['completed_cases'] for r in rows)} 問の出力を保存（応答エラーを含む）。",'',
      'この小規模試験では、**Gemma 4 31B**がRAG 6/6・初回ツール8/8・根拠付きOntology Q&A 10/10。**Qwen 3.5 35B**は6/6・7/8・10/10だった。固定した規定手順への一致まで要求すると、それぞれ9/10・8/10。実際の出力から同等の取得経路も確認し、両方の指標を残した。', '',
      '## 結果の読み方','',
      '- **RAG**: アプリの検索上位5件を固定し、報告ID・機械・工程がすべて正しく、無関係な報告IDを引用しない回答の割合（6問）。検索処理の速さは含めない。',
      '- **ツール**: 最初の実tool callの名前・JSON Schema・指定引数がすべて正しい割合（8問）。ここでは呼び出しを採点し、UI操作・更新は実行しない。',
      '- **Ontology 根拠付きQ&A**: 回答値が正しく、実MCPの出力にも根拠がある割合（10問）。集計は指定scopeと返されたmetricsを照合。曖昧名の確認は候補2件の実取得、逆方向の関係取得はCAPA→報告の実キーと取得結果も確認する。妥当な別解を監査した後に追加した事後指標で、元の厳密採点とは別に保存。',
      '- **Ontology 規定手順**: 固定したツール名・引数・必要な呼び出し順序と回答値が一致する割合。検索語を短くした場合や、同じ関連先を別ツールで取得した場合も不一致になり得る。両指標とも、制限内のエラー修正を認め、ツールを使ったという本文の主張だけでは正解にしない。',
      '- 主表の回答値は、JSON外側の単一要素配列・スカラー値を包む単一要素配列だけを正規化。複数候補から正解だけを選ぶ処理は行わない。**形式を含む厳密採点は別表**。この正規化は初期出力に形式違反が見つかった後に追加した補助分析であり、元の採点と出力は変更していない。',
      '- 正解値の照合は決定的なルールで行い、LLMを採点者に使っていない。JSON以外の説明文全体の正しさを保証する指標でも、RAGASスコアでもない。','',
      '## モデル別の実測値','',
      '| モデルタグ | RAG /6 | ツール /8 | Ontology 根拠付き /10 | 規定手順＋値 /10 | Ontology中央値 |',
      '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        median=r['ontology_median_s']
        txt.append(f"| `{r['model']}` | {cell(r['rag_correct'],r['rag_n'])} | {cell(r['tool_correct'],r['tool_n'])} | {cell(r['ontology_grounded_correct'],r['ontology_n'])} | {cell(r['ontology_correct'],r['ontology_n'])} | {str(median)+' 秒' if median is not None else '—'} |")
    txt += ['', '中央値は不正解・中断も含む10問の所要時間。速く誤答するケースも含むため、速度だけで選定しない。', '', '![モデル別の正解率](accuracy.png)', '',
      'モデル名は接続先が返したタグそのまま。公開モデルとの同一性は独立検証していない。完全なdigest・量子化方式・サイズ・申告capabilitiesは `model_inventory.csv` と `inventory.json` に保存。', '',
      '## 形式・ツール実行を分けた診断','',
      '| モデル | RAG厳密 /6 | 初回ツール名のみ /8 | Ontology値のみ /10 | Ontology厳密 /10 | 実行成功call / 全call | エラー終了 /24 |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for r in completed:
        txt.append(f"| `{r['model']}` | {r['rag_strict']}/6 | {r['tool_name_correct']}/8 | {r['ontology_values_only']}/10 | {r['ontology_strict']}/10 | {r['ontology_calls_succeeded']}/{r['ontology_calls']} | {r['errors']}/24 |")
    txt += ['', '「値のみ」はツールを呼ばずに数値を述べた場合も含む診断値。主表のOntology成功率には必要なツール実行を課す。実行成功callはサーバーが受理した呼び出しであり、質問に適切だった割合ではない。例えば誤った対象型への検索が0件で正常終了する場合がある。', '',
      '## 検索そのものの評価','',
      f"凍結した6質問について、アプリのハイブリッド検索は Hit@5 = {sum(x['hit_at_5'] for x in retrieval)}/{n}、Hit@1 = {sum(x['rank']==1 for x in retrieval)}/{n}、MRR@5 = {statistics.mean(x['reciprocal_rank'] for x in retrieval):.4f}。",'',
      '正解が上位5件に含まれることと、LLMがその正解を選び出すことを別々に測定した。各モデルへ同じ5件の固定フィールドを渡すため、このRAG試験はアプリ画面からの完全なE2E試験ではない。文書の検索・読解を扱う6例の結果で、一般的な検索品質を証明するものではない。', '',
      '| ID | 正解ID | 正解順位 | 検索上位5件 |','|---|---|---:|---|']
    for r in retrieval:
        txt.append(f"| {r['id']} | {', '.join(r['gold_ids'])} | {r['rank']} | {', '.join(r['retrieved_ids'])} |")
    retrieval_file=HERE/'retrieval_comparison.json'
    if retrieval_file.exists():
        comparison=json.loads(retrieval_file.read_text())
        names={'BM25 + synonym expansion':'BM25＋同義語展開', 'e5 dense only':'e5ベクトル検索のみ',
               'RRF only k=60':'RRFのみ（k=60）','Application full hybrid':'アプリ最終順位（補正・近傍展開を含む）'}
        txt += ['', '### 検索方式別の追加比較','',
          '| 検索方法 | Hit@1 | Hit@5 | MRR@5 |','|---|---:|---:|---:|']
        for method in dict.fromkeys(r['method'] for r in comparison['records']):
            rs=[r for r in comparison['records'] if r['method']==method]
            txt.append(f"| {names[method]} | {sum(r['hit_at_1'] for r in rs)}/{len(rs)} | {sum(r['hit_at_5'] for r in rs)}/{len(rs)} | {statistics.mean(r['reciprocal_rank'] for r in rs):.4f} |")
        txt += ['',
          'この6問では、BM25とRRF単独が全件を1位に置き、アプリ最終順位では2問の順位が下がった。したがって、後段の補正・近傍展開が常に検索を改善するとはいえない。補正と近傍展開の個別の寄与までは分離していない。数値・部品名を含む少数の事例検索なので、曖昧な概念検索でもBM25が優位とは一般化できない。',
          f"埋め込みは `{comparison['embedding_model']}`、BM25 k1={comparison['bm25_k1']} / b={comparison['bm25_b']}。全方式は同じ117報告・6質問。RRFはBM25上位50件とdense上位30件を `1/(60+順位)` で加算。生順位は `../../retrieval_comparison.json`。"]
    txt += ['', '## 評価問題と正解','',
      '| ID | 区分 | 質問 | 正解値／期待する初回呼び出し |','|---|---|---|---|']
    for c in dataset['cases']:
        gold=json.dumps(c.get('expected',c.get('expected_call')),ensure_ascii=False)
        txt.append(f"| {c['id']} | {LABELS[c['suite']]} | {c['question'].replace(chr(10),'<br>')} | `{gold}` |")
    txt += ['', '## 測定条件と範囲','',
      '- Ollama 0.32.11。温度0、seed=20260915、context=32768、1生成768 tokens、最大6生成段階、1問150秒／1リクエスト75秒。モデル切替時に短いウォームアップを実行し、その時間は設問の応答時間から除外。GPU機種・RAM容量・他利用者の負荷は未確認。',
      '- thinking=false。GPT-OSSだけlow（Ollamaでは完全無効化できない）。従って推論計算量がすべてのモデルで同じとはいえない。モデル内の推論も出力トークン上限の影響を受ける。[Ollamaのthinking仕様](https://docs.ollama.com/capabilities/thinking)',
      '- 同時実行1。`/api/chat` が返した `message.tool_calls` を検証し、アプリの実FastMCP関数へ渡す独自の小さな評価ハーネス。本文に書かれたtool-call風JSONは実行しない。[Ollamaのtool calling仕様](https://docs.ollama.com/capabilities/tool-calling)',
      '- LLMにはアプリの28ツールの定義とOntology契約を提示。Ontology試験で実行可能なのは15個の読み取り・プレビュー用ツールに限定。誤った型・引数はエラーとしてLLMに戻し、上限内での修正を認める。',
      '- 例アプリのDBに登録されていた117報告の固定コピー＋検証用3報告・3CAPAを隔離SQLiteに構築。BENCH設備Aに2報告・CAPAを複数、設備Bにゼロ分母・金額欠損を用意。CAPAとのJOINで損失が二重計上されないか、平均率ではなく19/1000を使うか、nullを0と混同しないかを検査。',
      '- RAG固定コンテキストは稼働アプリの検索結果。隔離MCP内での動的な類似検索はEMBEDDINGS=offのBM25。Ontologyの主課題は構造化検索・集計。RAGの固定コンテキスト試験と動的検索を混同しない。',
      '- 金額・件数は絶対誤差1e-6、0〜1の率は5e-5以内。nullと0、falseと数値0、率と百分率を区別。指定scopeへの余分な条件追加も不正解。O05のCAPA取得はtraverseまたはlist、O06の不存在確認はresolveまたはmachineマスター確認を許容。それ以外の呼び出し要件はdataset.jsonに固定。',
      '- O07で単に「確認が必要」と述べる回答は値のみ正解。根拠付きQ&Aでは、名前解決またはマスターから実候補を取得したことを確認する。規定手順の列は、固定した検索語・経路への適合率として解釈する。',
      '- 入力は日本語、各設問1試行。6/8/10問の小規模評価で、差の統計的有意性や汎用的なモデル順位は主張しない。CSVのWilson 95%区間は二項近似の参考値で、実測の反復ばらつきではない。',
      '- 外部クラウド転送タグ、埋め込み専用、completion-onlyのタグはツール対応20モデルの主比較から除外。クラウドモデルとの比較、画像理解、並列負荷、長時間安定性、プロンプトインジェクション耐性、書き込み成功率は今回の測定対象外。',
      '- RAG導入前／Ontology導入前との同一問題での対照実験はしていないため、導入による改善幅を示す結果ではない。', '',
      f"開始: `{meta['started_at']}`（UTC）、終了: `{meta.get('finished_at','測定中')}`（UTC）。隔離DBの測定前後一致: `{meta.get('database_unchanged','確認待ち')}`。", '',
      '## 会話APIの初期確認で失敗したタグ','']
    bad=[r for r in rows if r['load_error']]
    if bad:
        for r in bad:
            txt += [f"- `{r['model']}`: {r['load_error'].splitlines()[0]}"]
    else:
        txt += ['なし（測定途中の場合は暫定）。']
    diagfile=HERE/'runs/diagnostics_20260915.json'
    if diagfile.exists():
        diags=json.loads(diagfile.read_text())['records']
        txt += ['', '### エラーと出力上限の追加診断','']
        for d in diags:
            if d.get('api')=='native':
                txt.append(f"- `{d['model']}` の再確認: HTTP {d.get('http_status','エラー')}、`{d.get('body',d.get('error','')).strip()[:180]}`。")
        if any(d.get('api')=='compatible' for d in diags):
            txt.append('- 上記2タグはOpenAI互換の `/v1/chat/completions` でも同じrendererエラー。モデルタグのrenderer定義とサーバーの対応を確認する必要がある。今回タグやサーバー設定は変更していない。')
        probes=[d for d in diags if d.get('num_predict')]
        if probes:
            txt += ['', '| モデル・設問 | 768 tokensの主比較 | 3072 tokensの追加確認 |','|---|---|---|']
            for d in probes:
                original=next(r for r in data[d['model']]['cases'] if r['case_id']==d['case_id'])
                case=next(c for c in dataset['cases'] if c['id']==d['case_id'])
                txt.append(f"| `{d['model']}` / {d['case_id']} | {original['status']}・{'規定達成' if passed(case,original) else '規定未達'} | {d['status']}・{'規定達成' if d['correct_normalized'] else '規定未達'} |")
            txt += ['', '出力上限だけを1生成768から3072へ増やした、モデルごとに1問の追加診断。推論に上限を使い切る影響を確認するためのもので、主比較の正解率には混ぜない。生出力は `../../runs/diagnostics_20260915.json`。']
    op=HERE/'runs/opencode_20260915/summary.md'
    if op.exists():
        txt += ['',op.read_text()]
        txt += ['', '同等の取得経路を許容した、根拠付きQ&Aの追加集計：','',
                '| モデル | 根拠付きQ&A |','|---|---:|']
        op_records=[]
        case_map={c['id']:c for c in dataset['cases']}
        for filename in op.parent.glob('*.json'):
            record=json.loads(filename.read_text())
            if not isinstance(record,dict) or 'cases' not in record:continue
            op_records.append(record)
        op_detail=[]
        for record in sorted(op_records,key=lambda r:['gemma4:31b','gpt-oss:20b','qwen3.5:35b'].index(r['model'])):
            k=sum(grounded(case_map[r['case_id']],r) for r in record['cases'])
            txt.append(f"| `{record['model']}` | {cell(k,len(record['cases']))} |")
            for r in record['cases']:
                op_detail.append({'model':record['model'],'case_id':r['case_id'],
                    'grounded_correct':grounded(case_map[r['case_id']],r),
                    'prescribed_workflow_correct':r['correct_normalized'],
                    'elapsed_s':r['elapsed_s'],'answer':r['answer'],
                    'calls':json.dumps(r['calls'],ensure_ascii=False)})
        write_csv(OUT/'opencode_cases.csv',op_detail)
        txt += ['',
          '今回のOpenCode構成の候補としては、追加5問すべてで根拠付き回答に成功したGemma 4 31Bが有力。GPT-OSS 20BはO03でscopeの引数誤りを繰り返して段階上限に達した。Qwen 3.5 35BはO03で設備名へ空白を加えて取得に失敗し、O07ではツール実行後の最終回答が空、O08ではプレビューを呼ばず検証結果を述べた。直接APIの成績からOpenCodeでの成績を推定しない。',
          'Gemma 4 31Bの実行中に `/api/ps` でcontext=131072を観測した。設定ファイルに書いたcontext上限と、サーバーが確保するcontextは同一とは限らない。この追加試験を、context=32768・thinking指定を固定した主比較との速度の対照実験として扱わない。観測値は `../../runs/opencode_20260915/runtime_observations.json`。']
    findings=HERE/'findings.md'
    if findings.exists():
        txt += ['',findings.read_text()]
    txt += ['', '## 保存物と再現','',
      '- [モデル別集計CSV](model_summary.csv): 指標、速度、正解率の分母、参考区間。',
      '- [全432問の結果CSV](case_results.csv): 質問・回答・実ツール呼び出し・採点。',
      '- [OpenCodeの15問の結果CSV](opencode_cases.csv): 別構成での追加確認。',
      '- [全モデル一覧CSV](model_inventory.csv): 全43タグと選定／除外理由。',
      '- `../../runs/native_v1_20260915/`: 生のLLM応答、ツール引数・結果、トークン数・時間・エラー、SHA256。',
      '- [評価データセット](../../dataset.json): 正解・質問・固定検索文脈・fixture。[README](../../README.md) に再実行手順。',
      '- `pilot_20260915` と `native_20260915` は準備・中断実行であり、この集計には含めていない。','']
    md='\n'.join(txt)
    (OUT/'report.md').write_text(md)
    import markdown
    body=markdown.markdown(md,extensions=['tables','fenced_code'])
    body=re.sub(r'<img alt="([^"]*)" src="accuracy.png"\s*/?>',r'<img alt="\1" src="accuracy.svg">',body)
    # SVGを埋め込み、ファイル単体でも図を読めるようにする。
    if (OUT/'accuracy.svg').exists():
        svg=(OUT/'accuracy.svg').read_text()
        svg=svg[svg.index('<svg'):]
        body=re.sub(r'<img alt="[^"]*" src="accuracy.svg">',lambda _:svg,body)
    cases={c['id']:c for c in dataset['cases']}
    body += '<h2>各モデルの回答と実ツール呼び出し</h2><p>クリックして展開できます。全出力はCSV・JSONにも保存しています。</p>'
    for name,d in data.items():
        body += '<details><summary>'+html.escape(name)+'</summary>'
        for r in d.get('cases',[]):
            case=cases[r['case_id']]
            label='規定達成' if passed(case,r) else '規定未達'
            trace=[{k:c.get(k) for k in ['name','arguments','schema_valid','success','validation_error','output']} for c in r['calls']]
            body += '<details><summary>'+html.escape(f"{r['case_id']} {label} {r['elapsed_s']:.1f}秒 — {case['question']}")+'</summary>'
            body += '<h4>回答</h4><pre>'+html.escape(r['answer'])+'</pre><h4>ツール呼び出し</h4><pre>'+html.escape(json.dumps(trace,ensure_ascii=False,indent=2))+'</pre></details>'
        body+='</details>'
    css='''body{font:15px/1.8 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif;color:#243641;background:#f4f6f7;margin:0}main{max-width:1320px;margin:24px auto;padding:36px;background:white}h1{font-size:29px}h2{font-size:22px;margin-top:38px;border-bottom:2px solid #bccbd4;padding-bottom:8px}table{border-collapse:collapse;display:block;overflow-x:auto;font-size:13px;margin:18px 0}th{background:#e4ebef;color:#29475a;text-align:left}td,th{padding:9px 12px;border:1px solid #d4dde2;vertical-align:top}tr:nth-child(even){background:#f7f9fa}code{font-size:12px;overflow-wrap:anywhere}a{color:#315e7b}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f7;padding:16px;font-size:12px}svg,img{width:100%;height:auto}details{margin:10px 0;border:1px solid #d4dde2;padding:10px 16px}summary{cursor:pointer;font-weight:600}details details{background:#fafbfc}@media(max-width:700px){main{margin:0;padding:18px}h1{font-size:23px}td,th{padding:7px}}@media print{body{background:white}main{margin:0;padding:0}details{display:none}table{font-size:10px}h2{break-after:avoid}}'''
    (OUT/'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ローカルLLMベンチマーク 2026-09-15</title><style>'+css+'</style><main>'+body+'</main></html>')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    dataset,meta,data,summary,details=collect()
    write_csv(OUT/'model_summary.csv',summary)
    write_csv(OUT/'case_results.csv',details)
    inventory=[]
    for m in meta['model_inventory']:
        selected=m['name'] in meta['models']
        reason='評価対象' if selected else 'クラウド転送' if m.get('remote_host') else 'tools capabilityなし'
        inventory.append({'model':m['name'],'selected':selected,'reason':reason,'size_bytes':m['size'],
            'digest':m['digest'],'parameter_size':m['details'].get('parameter_size'),
            'quantization':m['details'].get('quantization_level'),'capabilities':','.join(m.get('capabilities',[]))})
    write_csv(OUT/'model_inventory.csv',inventory)
    import hashlib
    (OUT/'analysis_metadata.json').write_text(json.dumps({
        'analyzed_at':datetime.now().astimezone().isoformat(),
        'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'native_metadata_sha256':hashlib.sha256((RUN/'metadata.json').read_bytes()).hexdigest(),
        'dataset_sha256':hashlib.sha256((HERE/'dataset.json').read_bytes()).hexdigest(),
        'posthoc_rules':['singleton-array normalization','grounded equivalent routes'],
        'original_scores_preserved':True},ensure_ascii=False,indent=2))
    chart(summary)
    report(dataset,meta,data,summary,details)
    print(json.dumps({'models_complete':sum(r['completed_cases']==24 for r in summary),
        'cases':len(details),'finished':bool(meta.get('finished_at')),'report':str(OUT/'report.html')},ensure_ascii=False))


if __name__=='__main__':
    main()
