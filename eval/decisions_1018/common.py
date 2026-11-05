"""eval/decisions_1018 の共通部品：鍵の読み込み、backend の import、比べるモデル、結果の保存。"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent
sys.path.insert(0, str(APP / "app" / "backend"))


def load_env():
    """example_app/.env から OPENROUTER_API_KEY を読む(値は表示しない)。"""
    for line in (APP / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    os.environ.setdefault("DECISION_CACHE_TTL", "0")   # 測るときは使い回さない


# 比べるモデル(OpenRouter の判断モデル。2026-10-18 に probe_models.py で呼べることを確認)
TEXT_MODELS = ["typesafe/jev-1.14", "typesafe/jev-1.13", "perplexity/pplx-decider-flash-v1.2", "perplexity/pplx-decider-v1.2",
               "microsoft/microsoft-decision-1", "liquid/d1-ultra", "inception/mercury-decide", "cloudflare/clef-flash",
               "openai/gpt-6-luna-decisions"]
IMAGE_MODELS = ["typesafe/jev-1.14", "typesafe/jev-1.13", "perplexity/pplx-decider-flash-v1.2", "perplexity/pplx-decider-v1.2",
                "liquid/d1-ultra", "inception/mercury-decide", "cloudflare/clef-flash", "openai/gpt-6-luna-decisions"]
NO_ZDR = {"openai/gpt-6-luna-decisions", "inception/mercury-decide:free", "respan/span-01-lite:free", "respan/span-01-lite"}
# ↑ ZDR の経路が無い(probe.json)。比べるだけで、アプリの既定にはしない
FREE_MODELS = ["inception/mercury-decide:free", "respan/span-01-lite:free"]   # 無料(span-01 は Noul だけ・文字だけ)


def zdr_for(model: str) -> bool:
    return model not in NO_ZDR


def save(name: str, obj):
    name = os.environ.get("OUT_PREFIX", "") + name
    (HERE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
