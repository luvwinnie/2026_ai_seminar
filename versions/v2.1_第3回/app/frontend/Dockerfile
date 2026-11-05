# 画面（Vite の開発サーバー）。/api と /health を backend へ転送する（API_TARGET）。04_API設計書.md §3.3
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV WEB_HOST=0.0.0.0 WEB_PORT=5173
EXPOSE 5173
CMD ["npm", "run", "dev"]
