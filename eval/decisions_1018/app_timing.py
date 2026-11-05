"""アプリの検索 API(/api/reports/search)の応答時間を、判断モデルなし・ありで比べる。
backend を別のポートで2つ起動して(DECISIONS_ENABLED=0 と 1)、同じ16問を2回ずつ送る(1回目は温め)。
使い方：S4_WORK=… SUDACHI=… python app_timing.py   → app_timing.json"""
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

from common import APP, load_env, save

load_env()
S = Path(os.environ["S4_WORK"])
QS = ["表面がざらざらして仕上がりが悪い", "QUICK TURN 250MSY の工具破損", "GENOS M560-V の寸法不良の傾向と原因は?", "バリが取り切れていなかった",
      "主軸のクランプ圧低下が原因の報告は何件で、どの現象に出ている?", "ドリルやエンドミルが折れた", "部品が曲がって反ってしまった",
      "穴の位置が図面と合わない", "加工面に段がついてしまった", "加工プログラムの設定を間違えた", "寸法が公差から外れていた",
      "刻印の番号が間違っていた", "部品を逆向きに取り付けた", "搬送中に隣の品物と当たって付いたキズ", "治具の固定が甘くてずれた事例は？",
      "チャックに切粉が噛み込んで付いた傷の対策は？"]


def start(port, on):
    env = dict(os.environ, DB_PATH=str(S / "exp.db"), CHROMA_PATH=str(S / "chroma"), EMBEDDINGS="on", HF_HUB_OFFLINE="1",
               TRANSFORMERS_OFFLINE="1", DECISIONS_ENABLED="1" if on else "0", DECISION_CACHE_TTL="0", OPENCODE_URL="",
               JEV_ENABLED="0", PYTHONPATH=os.environ.get("SUDACHI", ""), LANGFUSE_HOST="", LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="")
    p = subprocess.Popen([str(APP / ".venv/bin/uvicorn"), "main:app", "--port", str(port), "--log-level", "warning"],
                         cwd=str(APP / "app/backend"), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                return p
        except httpx.HTTPError:
            pass
        time.sleep(1)
    p.kill()
    raise RuntimeError("backend did not start")


out = {}
for name, port, on in (("decisions_off", 8026, False), ("decisions_on", 8027, True)):
    p = start(port, on)
    try:
        ms, modes = [], set()
        for rep in range(2):
            for q in QS:
                t0 = time.monotonic()
                r = httpx.get(f"http://127.0.0.1:{port}/api/reports/search", params={"q": q, "top_k": 5}, timeout=120)
                t = int((time.monotonic() - t0) * 1000)
                if rep == 1:
                    ms.append(t)
                    modes.add(r.json().get("search_mode"))
        ms.sort()
        out[name] = {"median_ms": int(statistics.median(ms)), "p95_ms": ms[int(len(ms) * 0.95) - 1], "max_ms": ms[-1],
                     "search_mode": sorted(m for m in modes if m)}
        print(name, out[name])
    finally:
        p.terminate()
        p.wait(10)
save("app_timing.json", out)
