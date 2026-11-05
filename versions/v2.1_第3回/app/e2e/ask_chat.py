"""【LLM】チャットの API に1問送り、SSE を .logs/llm_q<番号>.sse に記録して要約を出す（07_試験・運用仕様書.md §2.3）。

起動中の backend（Docker Compose の 8120、または画面の 5220 を通す）に対して、リポジトリの直下から動かす。
backend の venv の Python を使う（httpx2 が入っている）：

    app/backend/.venv/bin/python app/e2e/ask_chat.py http://localhost:8120/api/chat/stream 1 "KZ25-0043 の内容を教えて" [session_id]
"""
import json
import sys
import time
from pathlib import Path

import httpx2

LOG_DIR = Path(__file__).resolve().parents[2] / ".logs"

url, no, question = sys.argv[1], sys.argv[2], sys.argv[3]
session_id = int(sys.argv[4]) if len(sys.argv) > 4 else None
start = time.monotonic()
events, raw = [], []
with httpx2.stream("POST", url, json={"message": question, "session_id": session_id}, timeout=httpx2.Timeout(10, read=600)) as r:
    name = None
    for line in r.iter_lines():
        raw.append(line)
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            events.append((round(time.monotonic() - start, 1), name, json.loads(line[6:])))
LOG_DIR.mkdir(exist_ok=True)
(LOG_DIR / f"llm_q{no}.sse").write_text("\n".join(raw))
first = {}
for t, n, _ in events:
    first.setdefault(n, t)
tools = [f"{d['name'].replace('defect-reports_', '')}:{d['status']}" + (f"({d['title']})" if d.get('title') else "") for _, n, d in events if n == "tool"]
answer = "".join(d["text"] for _, n, d in events if n == "token")
thinking = "".join(d["text"] for _, n, d in events if n == "thinking")
print(f"Q{no}: {question}")
print(f"  順番: {[n for n in dict.fromkeys(n for _, n, _ in events)]}  最後: {events[-1][1]} {json.dumps(events[-1][2], ensure_ascii=False)}")
print(f"  session: {events[0][2]}  最初に届いた時刻(秒): {first}  全体: {events[-1][0]}秒  token数: {sum(1 for _, n, _ in events if n == 'token')}")
print(f"  道具: {tools}")
print(f"  思考: {len(thinking)}文字")
print(f"  回答: {answer}")
