#!/bin/sh
# OPENROUTER_API_KEY から OpenCode の認証ファイルを生成して serve を起動する。
# (https://openrouter.ai/docs/cookbook/coding-agents/opencode-integration の方式)
set -e

if [ -z "$OPENROUTER_API_KEY" ]; then
  echo "[opencode] WARNING: OPENROUTER_API_KEY が未設定です。チャットは失敗します。" >&2
fi

AUTH_DIR="$HOME/.local/share/opencode"
mkdir -p "$AUTH_DIR"
# キー自体はログに出さない
printf '{"openrouter": {"type": "api", "key": "%s"}}\n' "$OPENROUTER_API_KEY" > "$AUTH_DIR/auth.json"
echo "[opencode] auth.json generated (provider: openrouter)"

cd /work
exec opencode serve --hostname 0.0.0.0 --port 4096
