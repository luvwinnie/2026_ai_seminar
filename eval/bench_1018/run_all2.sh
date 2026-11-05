#!/bin/bash
# 10-18 夜の2回目。gpt-oss:20b と qwen3.6:35b-a3b は研究室のサーバから消えていたので、いまあるモデルで測る。
# トンネルは使わず、研究室の Ollama(11434)と DeepSeek V4 Flash(ds4、11600)に直接つなぐ。
cd "$(dirname "$0")"
ROOT="$(cd ../../.. && pwd)"  # 例アプリの1つ上の作業フォルダ
export OLLAMA_V1="${OLLAMA_V1:?研究室の Ollama の URL を入れる（例 http://<サーバ>:11434/v1）}"
for M in ds4/deepseek-v4-flash qwen3.8:27b qwen3.5:9b; do
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
