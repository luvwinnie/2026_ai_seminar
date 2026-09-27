"""Lecture examples from measured outputs; preserves exact questions and answers."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent

EXAMPLES=[
 ('gemma4:26b-a4b','O09','成功例：名前をIDへ解決してから、設備と未完了CAPAの両方で絞る',
  'まずMachineLabelとしてBENCH設備Aを解決し、返却されたobject_idを次のscope.machine_idへ渡す。同じscope内にhas_open_capa=trueも指定する。実サービスが報告1件・損失100円・未完了CAPA2件を返し、その値をJSONにする。名前の解決、条件付き集計、回答の整形を別の段階に分けて追える成功例。後述のQwen3.5:4bの同じ設問と比較すると、最終値が同じでも根拠取得の正しさが異なる。'),
 ('gemma4:26b-a4b','O04','成功例：ゼロ分母と未入力の金額を、ゼロ円・0%にしない',
  'BENCH設備BをIDへ解決して実集計を取得し、分母ゼロの不適合率と未入力の損失額をnullで返した。missing_loss_reports=1も保持している。Ontologyの指標定義とサービス側のNULL処理が、AIによる誤った補完を防ぐための共通契約になる。'),
 ('gemma4:26b-a4b','O07','成功例：曖昧な設備名で勝手に対象を決めない',
  'MachineLabelとしてBENCHを検索すると複数候補が返る。モデルは任意の候補で集計せず、needs_clarification=trueを返した。曖昧さを候補一覧として表現するOntologyツールと、確定できない場合に確認へ戻るエージェントの役割を説明できる。'),
 ('qwen3.5:2b','O01','値・根拠が正しくても、機械処理用の形式に失敗する',
  'この回答の件数4、損失841072円、不適合率0.12075471698113208は正しい。履歴ではID解決後に正しいmachine_idで集計できている。ただし最後が自然文であり、要求したJSON形式を満たさないため主指標では不合格。ここから「このモデルは数値を理解できない」と結論しない。主表の値一致もJSONから抽出する指標なので、この自然文の意味的正しさを自動採点したものではない。'),
 ('qwen3.5:4b','O09','答えの数値が偶然合っていても、検索条件が欠けている',
  '回答の1件・100円・CAPA2件は正解値と一致する。しかし実際のquery_quality_ontologyにはmachine_idがなく、has_open_capa=trueだけで問い合わせている。今回のfixtureでは未完了CAPAのある報告がBENCH設備Aにしかないため一致した。将来、別設備にCAPAが追加されると誤答になる。採点は値だけでなく正しい対象条件を確認し、不合格にする。'),
 ('qwen3.5:4b','O01','名前とOntology上のID・型を取り違える',
  'a61nxはこのデータでは機械名だが、初手でdefect_idに入れ、その後もDefectReportとして解決している。サービスが不正な対象を拒否し、モデルは不明値を返した。講義ではMachineLabelという型、表示名a61nx、解決後のobject_idを別々に示す。'),
 ('bonsai-27b:1bit','O03','公開Schemaの検証とアプリ内部の制約は別の検証',
  'group_byに引用符を含む文字列が渡されている。公開Schemaではstringなので通るが、内部のQualityQueryはMachineLabel / Process / Customerという選択肢を検証し拒否する。モデルは条件を落として再試行し、同一呼び出しの反復上限で停止した。公開Schemaにもenumを出す設計と、エラーを受けて修正するハーネスの両方を検討する材料になる。'),
 ('qwen3.5:2b','C03','返却済みの集計結果を再計算して取り違えない',
  '正しい既知損失は300円だが、モデルは400円を返している。2つのCAPAが同じ100円の報告に紐づくfixtureなので、関連行を重複して数えると400円になる。ただし内部の誤りの原因を出力だけから断定はできない。講義では報告2行とCAPA3行を図示し、SUMの母集団とサーバー計算済みmetricsの意味を説明する。'),
 ('qwen3.5:0.8b','O08','保存しない検証依頼でも、操作の実行境界が必要',
  '利用者はclosedにできるかの検証だけを求めているが、モデルはcreate_capa_actionを試行した。ハーネスは参照・previewの許可リストにない呼び出しを遮断し、DBは変更していない。モデルへの指示、ツール引数の検証、操作許可、サービスの業務制約、DB変更の監査を具体的に分けて説明する。'),
]

def main():
    ds={c['id']:c for c in json.loads((HERE/'dataset.json').read_text())['cases']}
    lines=['# 軽量モデル評価：講義で使う実際の質問・成功例・失敗例','',
           '[全件レポート](report/report.html) / [評価条件](README.md)','',
           '以下は実測ログを個別に確認した説明例です。主表の採点規則を変更するものでも、自然文の正しさを全件人手採点した結果でもありません。','']
    audit=[]
    for model,cid,title,explanation in EXAMPLES:
        key=hashlib.sha256(model.encode()).hexdigest()[:12]
        paths=[HERE/'generation'/(key+'.json'),HERE/'generation_remaining'/(key+'.json')]
        path=next((p for p in paths if p.exists()),None)
        if path is None:continue
        d=json.loads(path.read_text());r=next((c for c in d['cases'] if c['case_id']==cid),None)
        if r is None:continue
        lines += [f'## {title}', '',f'モデル: `{model}` / 設問: `{cid}` / 結果: `{r["status"]}`','',explanation,'',
                  '利用者の質問：','', '```text',ds[cid]['question'],'```','',
                  '測定時のuserメッセージ全文（形式指示・参照資料を含む）：','', '````text',r['initial_messages'][1]['content'],'````','',
                  '実際の最終出力：','', '````text',r['answer'],'````','',
                  '呼び出しの要約：','', '```json',json.dumps([{k:c.get(k) for k in ['name','arguments','schema_valid','success','blocked']} for c in r['calls']],ensure_ascii=False,indent=2),'```','',
                  f'[実MCPの返却内容・全モデル応答を見る](generation/{key}.json)','']
        audit.append({'model':model,'case_id':cid,'title':title,'explanation':explanation,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (HERE/'lecture_examples.md').write_text('\n'.join(lines))
    (HERE/'manual_review_examples.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print('EXAMPLES',len(audit))

if __name__=='__main__':main()
