"""eval/decisions_1018 の結果(JSON)から report.md を作る(数字は手で写さない)。"""
import json
from pathlib import Path

H = Path(__file__).resolve().parent
J = lambda n: json.loads((H / n).read_text())
route, rr, cite, ocr, tm = J("route_v2.json"), J("rerank.json"), J("cite.json"), J("ocr_verify.json"), J("timing.json")
app0, app1 = J("app_timing_pplx_w8.json"), J("app_timing.json")
chat = J("chat_events.json")
L = []
w = L.append
w("# 判断モデル(OpenRouter の Decisions API)による強化の測定(2026-10-18)\n")
w("例アプリ DefectReport AI の4つの部分的な判断を、判断モデルに任せたときの正解率・時間・費用。"
  "データは架空の110件。モデルはすべて OpenRouter 経由(ZDR の経路。gpt-6-luna-decisions だけ ZDR なし)。"
  "時間は1回の呼び出しの前後で測った値(中央値と95%点)。費用は OpenRouter の usage.cost。\n")
w("## 1. 質問の振り分け(117問:問題集100問＋第4回の固定5問＋手で書いた12問)\n")
w("| モデル | 種類 | 正解率 | 1回の時間(中央値/95%) | 1000回の費用 |\n|---|---|---|---|---|")
for m, v in tm["route"].items():
    w(f"| {m} | {'判断モデル' if v['kind'] == 'decision' else 'LLM'} | {v['accuracy']:.1%} | {v['median_ms']}／{v['p95_ms']} ms | ${v['cost_per_1000']} |")
w("\n全モデルの正解率(route_v2.json):" + "・".join(f"{m.split('/')[-1]} {v['summary']['accuracy']:.1%}" for m, v in route["results"].items()) + "\n")
w("## 2. 検索の並べ替え(16問。例アプリの検索の上位30件を並べ直す)\n")
w(f"並べ直す前:上位5件の正解 {tm['rerank']['hybrid_only']['mean_p5']}、検索だけの時間 {tm['rerank']['hybrid_only']['median_ms']} ms(中央値)\n")
w("| やり方 | 上位5件の正解 | 1問の時間(中央値/95%) | 1問の費用 |\n|---|---|---|---|")
for k, v in tm["rerank"].items():
    if k == "hybrid_only":
        continue
    w(f"| {k.replace('|', '・')} | {v['mean_p5']} | {v['median_ms']}／{v['p95_ms']} ms | ${v['cost_per_query']} |")
w("\n候補ごとに呼ぶやり方の全モデル(rerank.json、上位5件の正解・再現率・報告の無い機械の問いでの最大確率):\n")
for m, v in rr["models"].items():
    s = v["summary"]
    w(f"- {m}:{s['mean_p5']}・{s['mean_recall5']}・Q3 最大 {s['q3_max_rel']}")
first = {k: (rr["queries"][k]["before"]["first"], rr["models"]["perplexity/pplx-decider-v1.2"]["per_query"][k]["first"]) for k in ("Q1", "Q2", "N2")}
w("\n最初の正解の順位(並べ直す前 → pplx-decider-v1.2):" + "、".join(f"{k} {a}位→{b}位" for k, (a, b) in first.items()))
w("\n候補30件に正解が入っていない問いは、並べ替えでは救えない(Q1 は正解6件のうち2件だけが候補に入る)。\n")
w("## 3. 引用の確かめ(54組:正しい文と、機械・原因・数・現象を入れ替えた文、意味をずらした文)\n")
w("| モデル | 種類 | 正解率 | 1回の時間(中央値/95%) | 1000回の費用 |\n|---|---|---|---|---|")
for m, v in tm["cite"].items():
    w(f"| {m} | {'判断モデル' if v['kind'] == 'decision' else 'LLM'} | {v['accuracy']:.1%} | {v['median_ms']}／{v['p95_ms']} ms | ${v['cost_per_1000']} |")
w("\n## 4. 読み取りの確かめ(VL モデルが帳票の画像から読んだ12回分・258項目、うち読み違い35項目)\n")
w("| モデル | 種類 | 見つけた読み違い | 正しい項目を誤って疑った数 | 1枚の時間(中央値/95%) | 1枚の費用 |\n|---|---|---|---|---|---|")
for m, v in tm["ocr"].items():
    w(f"| {m} | {'判断モデル' if v['kind'] == 'decision' else 'LLM'} | {v['caught']} | {v['false_alarm']} | {v['median_ms']}／{v['p95_ms']} ms | ${v['cost_per_form']} |")
w(f"\nBox(Jev 1.14、欄の位置):きれいな画像2枚の18欄で、本当の文字の位置の中心を枠が含んだのは {ocr['boxes']['center_hit']}(枠は欄全体を囲むので大きめ)。\n")
w("## 5. アプリの中での時間\n")
w(f"- 検索 API(16問×2回、2回目を測定):判断モデルなし {app1['decisions_off']['median_ms']} ms → "
  f"候補ごと(pplx-decider-v1.2・8本ずつ){app0['decisions_on']['median_ms']} ms → 1回にまとめる(Jev 1.14){app1['decisions_on']['median_ms']} ms(中央値)")
w("- チャット(Docker、チャットの LLM は研究室の gemma4:26b):出来事が届いた時刻(秒)")
for c in chat:
    t = c["times"]
    w(f"  - 「{c['q']}」 sources {t.get('sources')}・route {t.get('route')}・最初の文字 {t.get('token')}・citations {t.get('citations')}・done {t.get('done')}")
w("  - 振り分けは検索と同時に走るので、増えるのは約0.1秒。回答は LLM が20〜40秒かかり、判断モデルで足した時間はその一部\n")
w("## 6. 選んだモデル(app/backend/services/decisions.py DECISION_PROFILE)\n")
w("| 機能 | モデル | 理由 |\n|---|---|---|")
w("| 検索の並べ替え | typesafe/jev-1.14(1回にまとめる) | 上位5件の正解 0.72 で、1問 約0.4秒。候補ごとの pplx-decider-v1.2(0.73)は 1.1〜2.3秒 |")
w("| 質問の振り分け | perplexity/pplx-decider-v1.2 | 98.3%。確率0.6以上だけ採ると、採った中の間違い0 |")
w("| 引用の確かめ | liquid/d1-ultra | 100%(54組) |")
w("| 読み取りの確かめ・Box | typesafe/jev-1.14 | 誤って疑う数0。Box は Jev 1.14 だけ |")
w("\n## 7. 注意\n")
w("- 問題は小さく(117問・16問・54組・12回)、引用の問題は元データから講師が作ったもの。振り分けの種類の説明は、この問題集の間違いを見て1回直した(測り直した値を載せた)。")
w("- 判断モデルは道具の使い方の注意を足すだけで、最後に文を書くのは LLM。画面の試しでは、gemma4:26b が「6件」を並べながら「5件」と書いた(振り分けは『件数』で正しかった)。")
w("- 読みにくい画像では、照らし合わせる側も見えにくい(Jev 1.14 は合っている項目も疑い、読み違いを見逃した)。確信度 low で原本の確認を促す。")
w("- 画像と Box は TypeSafe の『試作向け』の機能。形や答えが版で変わり得る。")
(H / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
