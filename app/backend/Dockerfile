FROM python:3.12-slim

WORKDIR /app

# 埋め込みライブラリをビルドに含めるか(EMBEDDINGS=off でスキップし軽量化)
ARG EMBEDDINGS=on
ENV EMBEDDINGS=${EMBEDDINGS}

# シード用 CSV は /seed-data に read-only マウントされる。
# DB / Chroma は既定の ./data(= /app/data ボリューム)を使う。
ENV DATA_CSV=/seed-data/defect_reports.csv

# 依存関係を先にインストール(レイヤキャッシュを活かす)
COPY requirements.txt requirements-embeddings.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$EMBEDDINGS" != "off" ]; then \
        pip install --no-cache-dir -r requirements-embeddings.txt; \
    fi

# アプリ本体
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
