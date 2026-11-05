#!/bin/bash
# チャットの測定(6つの組み合わせ)→ RAGAS の採点、を順番に流す。途中で止めても、もう一度流せば続きから。
cd "$(dirname "$0")"
ROOT="$(cd ../../.. && pwd)"  # 例アプリの1つ上の作業フォルダ
for M in gemma4:26b gpt-oss:20b qwen3.6:35b-a3b; do
  for D in on off; do
    echo "=== chat $M $D $(date '+%H:%M')" >> run_all.log
    ./run_config.sh "$M" "$D" >> "runs/$(echo $M | tr ':/' '__')_dec-$D.log" 2>&1
  done
done
for f in runs/*_dec-*.jsonl; do
  case "$f" in *.ragas.jsonl) continue;; esac
  echo "=== ragas $f $(date '+%H:%M')" >> run_all.log
  "$ROOT"/tmp/series6/s4/ragas_venv/bin/python ragas_score.py "$f" --judge gpt-oss:120b >> "${f%.jsonl}.ragas.log" 2>&1
done
echo "=== ALL DONE $(date '+%H:%M')" >> run_all.log
