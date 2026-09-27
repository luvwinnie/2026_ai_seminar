# OpenCode サーバー(チャットの生成エンジン。モデルは OpenRouter 経由)
FROM node:22-slim

RUN npm install -g opencode-ai && npm cache clean --force

WORKDIR /work
COPY opencode.json /work/opencode.json
# OpenCode はプロジェクトの AGENTS.md を常設指示として読み込む
COPY AGENTS.md /work/AGENTS.md
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 4096
ENTRYPOINT ["/entrypoint.sh"]
