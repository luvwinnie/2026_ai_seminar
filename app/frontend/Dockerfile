# --- ビルドステージ ---
FROM node:22-alpine AS build
WORKDIR /app

# 依存インストール(キャッシュ効率のため package ファイルのみ先にコピー)
COPY package.json package-lock.json ./
RUN npm ci

# ソースをコピーしてビルド
COPY . .
RUN npm run build

# --- 配信ステージ ---
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
