"""システム図の生成スクリプト(mingrammer/diagrams + Graphviz)。

実行:  ../../.venv/bin/python generate_diagrams.py
出力:  docs/images/architecture.png    … 全体アーキテクチャ(Docker Compose 6サービス)
       docs/images/chat_flow.png       … AIチャットのデータフロー(番号付き)
       docs/images/search_pipeline.png … ハイブリッド検索+補正層のパイプライン

依存:  pip install diagrams / brew install graphviz
"""
from __future__ import annotations

import os

from diagrams import Cluster, Diagram, Edge
from diagrams.custom import Custom  # noqa: F401(アイコン差し替え用に例示)
from diagrams.generic.storage import Storage
from diagrams.onprem.client import Users
from diagrams.onprem.compute import Server
from diagrams.onprem.database import Postgresql
from diagrams.onprem.network import Internet, Nginx
from diagrams.programming.framework import Fastapi, React

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "images")
os.makedirs(OUT, exist_ok=True)

# 日本語ラベル用フォント(macOS)。Linux では "Noto Sans CJK JP" 等に変更。
GRAPH_ATTR = {"fontname": "Hiragino Sans", "fontsize": "14", "pad": "0.4"}
NODE_ATTR = {"fontname": "Hiragino Sans", "fontsize": "11"}
EDGE_ATTR = {"fontname": "Hiragino Sans", "fontsize": "10"}

AMBER = "#E58A17"
CYAN = "#0089AD"
GRAY = "#5B6878"


# ---------------------------------------------------------------- 全体構成図
with Diagram(
    "DefectReport AI — 全体アーキテクチャ",
    filename=os.path.join(OUT, "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    user = Users("ブラウザ\n(受講者)")

    with Cluster("Docker Compose", graph_attr={"fontname": "Hiragino Sans"}):
        with Cluster("frontend :5373", graph_attr={"fontname": "Hiragino Sans"}):
            nginx = Nginx("nginx")
            spa = React("React SPA\nMUI / Recharts")

        with Cluster("backend :8000", graph_attr={"fontname": "Hiragino Sans"}):
            api = Fastapi("FastAPI\n報告書CRUD / 統計 / 取込\nチャット / CAPA / 週次 / 写真")
            mcp = Server("MCPサーバー /mcp\nツール22本\n(読取8+書込2+CAPA6+画面6)")

        with Cluster("opencode :4096", graph_attr={"fontname": "Hiragino Sans"}):
            oc = Server("OpenCode serve\n(エージェント)")

        db = Postgresql("PostgreSQL\n報告書 / マスタ / チャット履歴\nCAPA / 週次 / フィードバック")
        chroma = Storage("Chroma\nベクトル索引 + BM25\n+ 関連グラフ(相互kNN)")

        with Cluster("langfuse :3390", graph_attr={"fontname": "Hiragino Sans"}):
            lf = Server("Langfuse\nトレース / スコア")
            lfdb = Postgresql("langfuse-db")

    openrouter = Internet("OpenRouter\n(LLM API)")

    user >> Edge(label="HTTP :5373") >> nginx
    nginx >> Edge(label="配信") >> spa
    nginx >> Edge(label="/api, /health\nプロキシ(SSE対応)") >> api
    api >> Edge(label="SQLAlchemy") >> db
    api >> Edge(label="検索 / upsert") >> chroma
    api >> Edge(color=AMBER, label="チャット/抽出/4M\nsession + prompt_async") >> oc
    oc >> Edge(color=AMBER, label="モデル呼び出し\n(OPENROUTER_API_KEY)") >> openrouter
    oc >> Edge(color=CYAN, style="dashed", label="MCPツール呼び出し\n(streamable HTTP)") >> mcp
    mcp >> Edge(color=CYAN, style="dashed") >> db
    api >> Edge(color=CYAN, style="dashed", label="WebMCP: ui_* →\nSSE /api/ui/events\n(画面を直接操作)") >> spa
    api >> Edge(color=GRAY, style="dotted", label="トレース+👍/👎スコア") >> lf
    lf >> Edge(color=GRAY, style="dotted") >> lfdb


# ---------------------------------------------------------- チャットのデータフロー
with Diagram(
    "AIチャットのデータフロー(履歴・ツール・ストリーミング)",
    filename=os.path.join(OUT, "chat_flow"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    browser = Users("ブラウザ\n/chat")
    api = Fastapi("FastAPI\n/api/chat/stream")
    oc = Server("OpenCode\nエージェント")
    openrouter = Internet("OpenRouter")
    db = Postgresql("chat_sessions\nchat_messages")
    chroma = Storage("Chroma")
    mcp = Server("MCPツール(22本)\n読取8 / 書込2 / CAPA6 /\n画面操作6(ui_navigate等)")

    # 主鎖(左→右): 双方向ラベルで往路①④⑤ / 復路⑦⑧を1本にまとめる
    browser >> Edge(dir="both", label="① message + session_id →\n← ⑧ SSE (session→sources→\ntool→thinking→token→done)") >> api
    api >> Edge(dir="both", color=AMBER, label="④ prompt_async(system+文脈+履歴) →\n← ⑦ /event SSE(tool/thinking/token)") >> oc
    oc >> Edge(color=AMBER, label="⑤ 推論\n(OPENROUTER_API_KEY)") >> openrouter

    # FastAPI の下段: 永続化と事前検索
    api >> Edge(label="② 履歴20件ロード\n⑨ 会話を保存(sources/tools/thinking込み)") >> db
    api >> Edge(label="③ 事前検索(sources用)") >> chroma

    # OpenCode の下段: ツールによる実データ参照
    oc >> Edge(color=CYAN, style="dashed", label="⑥ 実データ参照\n(依頼時のみ登録・更新)") >> mcp
    mcp >> Edge(color=CYAN, style="dashed") >> db



# ---------------------------------------------------- 検索パイプライン(補正層)
from diagrams.generic.blank import Blank  # noqa: E402

with Diagram(
    "ハイブリッド検索 + 決定論補正層(services/hybrid.py + graph.py)",
    filename=os.path.join(OUT, "search_pipeline"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    q = Users("クエリ\n(人間 / AIツール)")
    syn = Server("同義語展開\n手書き23群 +\n自動生成辞書")
    with Cluster("並行検索", graph_attr={"fontname": "Hiragino Sans"}):
        bm25 = Server("形態素BM25\n(SudachiPy /\nバイグラム)")
        dense = Storage("密ベクトル\n(e5-small,\nChroma)")
    rrf = Server("RRF融合\n(k=60)")
    facet = Server("ファセット補正\n機械/工程/重大度/4M\n不一致×0.55 一致×1.15")
    graphx = Server("グラフ展開\n相互kNNの強い縁へ\nα=0.25 1ホップ伝播")
    phrase = Server("フレーズ一致\n12文字窓の逐語出現\n×1.8〜×4.2")
    out = Blank("上位k件\n(ID+スコア+抜粋)")

    q >> syn
    syn >> bm25
    syn >> dense
    bm25 >> rrf
    dense >> rrf
    rrf >> facet >> graphx >> phrase >> out
