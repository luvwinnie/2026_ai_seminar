"""動いている例アプリ(Docker)のチャットに質問を送り、SSE の出来事ごとの時刻を記録する(判断モデルの追加時間を見る)。
作った会話は最後に消す。使い方：python chat_events.py http://localhost:8010   → chat_events.json"""
import json
import sys
import time

import httpx

from common import save

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010"
QS = ["主軸のクランプ圧低下が原因の報告は何件？", "KZ25-0043 の内容を教えて", "搬送中に隣の品物と当たって付いたキズの事例は？"]
out = []
for q in QS:
    t0 = time.monotonic()
    ev, data, first = {}, {}, {}
    answer = ""
    sid = None
    with httpx.stream("POST", f"{BASE}/api/chat/stream", json={"message": q}, timeout=600) as r:
        name = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:") and name:
                t = round(time.monotonic() - t0, 2)
                d = json.loads(line[5:].strip() or "{}")
                first.setdefault(name, t)
                if name == "session":
                    sid = d.get("id")
                if name == "token":
                    answer += d.get("text", "")
                if name in ("route", "citations", "sources", "error", "done"):
                    data[name] = d
                name = None
    rec = {"q": q, "times": first, "route": data.get("route"), "citations": data.get("citations"),
           "sources": [s["defect_id"] for s in (data.get("sources") or {}).get("items", [])], "answer": answer[:600],
           "error": data.get("error")}
    out.append(rec)
    print(json.dumps({k: rec[k] for k in ("q", "times", "sources")}, ensure_ascii=False))
    print("  route", (rec["route"] or {}).get("intent"), (rec["route"] or {}).get("p"), "| citations",
          [(c["defect_id"], c["p"], c["supported"]) for c in (rec["citations"] or {}).get("checks", [])])
    if sid:
        httpx.delete(f"{BASE}/api/chat/sessions/{sid}", timeout=30)
save("chat_events.json", out)
