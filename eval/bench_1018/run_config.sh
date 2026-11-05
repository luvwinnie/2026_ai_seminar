#!/bin/bash
# 使い方: run_config.sh <ollama のモデル> <on|off> [bench_run.py の引数…]
# 例アプリ(Docker)のチャットの LLM を研究室の Ollama のモデルにし、判断モデル(無料の mercury-decide:free)をあり・なしにして全問を流す。
set -e
MODEL="$1"; DEC="$2"; shift 2
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"  # 例アプリの1つ上の作業フォルダ
OV="$ROOT/tmp/series6/s4/shots/override_bench.yml"
EN=$([ "$DEC" = on ] && echo 1 || echo 0)
# 「提供元/モデル」ならそのまま、名前だけなら研究室の Ollama
case "$MODEL" in */*) PROV="${MODEL%%/*}"; MID="${MODEL#*/}";; *) PROV=ollama; MID="$MODEL";; esac
OM="$PROV/$MID"
FREE="inception/mercury-decide:free"
cat > "$OV" <<YML
# ベンチマーク用の一時上書き(リポジトリは変えない)。チャットの LLM は研究室の Ollama、判断モデルは無料のもの(ZDR なし・架空データだけ)
services:
  backend:
    environment:
      - ANTHROPIC_API_KEY=
      - OPENCODE_PROVIDER=$PROV
      - OPENCODE_MODEL=$MID
      - JEV_ENABLED=0
      - DECISIONS_ENABLED=$EN
      - DECISION_ZDR=0
      - DECISION_MODEL_ROUTE=$FREE
      - DECISION_MODEL_RERANK=$FREE
      - DECISION_MODEL_CITE=$FREE
      - DECISION_MODEL_OCR=$FREE
  opencode:
    environment:
      - OPENROUTER_API_KEY=
      - OPENCODE_MODEL=$OM
    volumes:
      - $ROOT/tmp/series6/tunnel/opencode_bench.json:/work/opencode.json:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
YML
cd "$ROOT/example_app/app"
docker compose -p app -f docker-compose.yml -f "$OV" up -d backend opencode >/dev/null 2>&1
until [ "$(docker inspect -f '{{.State.Health.Status}}' app-opencode-1 2>/dev/null)" = healthy ]; do sleep 3; done
NAME="$(echo "$MODEL" | tr ':/' '__')_dec-$DEC"
cd "$HERE" && ../../.venv/bin/python -u bench_run.py "$NAME" "$@"
