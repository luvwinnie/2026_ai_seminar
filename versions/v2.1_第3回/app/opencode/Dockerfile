# OpenCode をヘッドレス（opencode serve）で動かす（06_AI設計書.md §0.1.1）。版は 1.19.0 に固定する
FROM node:22-slim
RUN npm install -g opencode-ai@1.19.0 && npm cache clean --force
WORKDIR /workspace
COPY opencode.json AGENTS.md ./
EXPOSE 4096
CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
