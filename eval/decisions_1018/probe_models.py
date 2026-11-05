"""OpenRouter の判断モデルが、例アプリの形の質問に答えられるかを短い質問で確かめる（ZDR あり→なしの順）。
費用はモデルごとに 1 往復ぶん（数百トークン）。結果は probe.json。鍵は表示しない。"""
import json
import os
import time
from pathlib import Path

import httpx

KEY = os.environ["OPENROUTER_API_KEY"]
URL = "https://openrouter.ai/api/alpha/decisions"
MODELS = ["typesafe/jev-1.14", "typesafe/jev-1.13", "perplexity/pplx-decider-flash-v1.2", "perplexity/pplx-decider-v1.2",
          "microsoft/microsoft-decision-1", "openai/gpt-6-luna-decisions", "liquid/d1", "liquid/d1-ultra",
          "cloudflare/clef", "cloudflare/clef-flash", "inception/mercury-decide", "upstage/solar-decide",
          "togethercomputer/tev1-4b-experimental", "jaredpalmer/kev-4b", "nace-ai/drex-v2.0"]
STATE = {"質問": "表面がざらざらして仕上がりが悪い事例は？",
         "報告書": "KZ25-0072 Oリング溝の仕上げ面が要求Ra1.6に対し粗く、表面粗さ計でRa3.2相当。びびり模様も視認できる。"}
QS = {"relevant": {"type": "noul", "instructions": "`報告書` は `質問` が探している不具合に当てはまる。",
                   "criteria": {"true": "同じ種類の不具合を書いている", "false": "別の種類の不具合を書いている"}},
      "intent": {"type": "choice", "instructions": "`質問` は何を求めているか。",
                 "criteria": {"search": "似た事例を探す", "count": "件数を数える", "one": "番号が分かっている1件を読む", "other": "そのほか"}}}
out = []
for m in MODELS:
    for zdr in (True, False):
        body = {"model": m, "state": STATE, "questions": QS}
        if zdr:
            body["provider"] = {"zdr": True, "data_collection": "deny"}
        t0 = time.monotonic()
        try:
            r = httpx.post(URL, json=body, headers={"Authorization": f"Bearer {KEY}"}, timeout=30)
            ms = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                d = r.json()
                a = d.get("answers", {})
                rec = {"model": m, "zdr": zdr, "ok": True, "ms": ms, "served": d.get("model"), "provider": d.get("provider"),
                       "relevant": a.get("relevant", {}).get("noul"), "intent": a.get("intent", {}).get("choice"),
                       "intent_p": a.get("intent", {}).get("probabilities"), "cost": (d.get("usage") or {}).get("cost"),
                       "tokens": (d.get("usage") or {}).get("input_tokens")}
            else:
                rec = {"model": m, "zdr": zdr, "ok": False, "ms": ms, "status": r.status_code, "err": r.text[:160]}
        except httpx.HTTPError as e:
            rec = {"model": m, "zdr": zdr, "ok": False, "err": type(e).__name__}
        out.append(rec)
        print({k: v for k, v in rec.items() if k != "intent_p"})
        if rec["ok"]:
            break
Path("probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print("total cost", sum(r.get("cost") or 0 for r in out))
