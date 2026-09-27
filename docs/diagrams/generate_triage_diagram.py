"""報告書トリアージ(判断モデル Jev + LangGraph)の図(mingrammer/diagrams + Graphviz)。

実行:  ../../.venv/bin/python generate_triage_diagram.py
出力:  docs/images/triage_graph.png
2026-09-27: 採否を「1位の確率＋2位との差」に、処置案の確かめを3問に、版の固定・データを残さない経路・
使い回し・続けて測る(/api/triage/metrics)を足した。1列だと横に長すぎるので U 字の2段に折り返す
(上の段は判断まで左→右、merge の下で折り返して、下の段は CAPA まで右→左)。
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

import diagrams
from diagrams import Cluster, Diagram, Edge, getdiagram
from diagrams.onprem.client import Users
from diagrams.onprem.compute import Server
from diagrams.onprem.database import Postgresql
from diagrams.programming.flowchart import Document
from diagrams.programming.framework import React
from diagrams.programming.language import Python

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "images")
os.makedirs(OUT, exist_ok=True)

FONT = "Hiragino Sans"
CL = {"fontname": FONT, "fontsize": "15", "margin": "22"}
CODE = "#3E5C72"   # コード(決定論)
JEV = "#2E7D32"    # 判断モデル
LLM = "#C55A11"    # LLM(例外だけ)
HUMAN = "#2E75B6"  # 人
OBS = "#6B7785"    # 記録と測定


def fit(cls, label, size=13, width=1.4):
    """アイコンを上に置き、文字の行数に合わせて高さを決める(文字がアイコンにかからない)。"""
    icon = Path(diagrams.__file__).resolve().parent.parent / cls._icon_dir / cls._icon
    iw, ih = struct.unpack(">II", icon.read_bytes()[16:24])
    height = width * ih / iw + 0.15 + (label.count("\n") + 1) * size * 1.3 / 72
    return cls(label, height=f"{height:.2f}", imagepos="tc")


with Diagram(
    "\n報告書トリアージ — 流れはコード、判断は Jev、例外だけ LLM と人(LangGraph)\n"
    "線:緑=判断モデル Jev オレンジ=LLM(閾値に届かないときだけ) 青=人の承認 灰=コード 点線=測定",
    filename=os.path.join(OUT, "triage_graph"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr={"fontname": FONT, "fontsize": "20", "pad": "0.6", "nodesep": "0.55", "ranksep": "0.9", "splines": "spline",
                "newrank": "true"},
    node_attr={"fontname": FONT, "fontsize": "13"},
    edge_attr={"fontname": FONT, "fontsize": "12"},
):
    start = fit(Document, "報告書\n登録済み・新規の入力")
    with Cluster("LangGraph(状態を毎ステップ SQLite に保存。止まっても同じ run_id で再開)",
                 graph_attr={**CL, "labeljust": "r"}):
        prepare = Python("prepare\n判断に要る項目\nだけ取り出す")
        with Cluster("judge:Jev に7問を2回で並列に聞く(約0.4秒)\n版を固定・データを残さない経路・同じ入力は使い回す",
                     graph_attr={**CL, "bgcolor": "#EEF6EE"}):
            desc = Server("不具合内容だけを見せる\n現象(Choice)\n重要度(Score)\n客先流出・記述不足(Noul)")
            cause = Server("原因の文だけを見せる\n要因(Choice)\n4M(Choice)\n仕組みの原因(Noul)")
        gate = Python("閾値(コード)\n1位の確率 ≥ 0.8\nかつ2位との差 ≥ 0.6\n版が違えば採らない\n重要度は採らない(参考)")
        llm = Server("llm_review\n届かなかった項目だけ\nLLM が選ぶ(理由つき)")
        merge = Python("merge\n登録値と照合\n→ 見直し候補")
        plan = Python("plan\n客先流出、または\n仕組みの原因＋\n重要度 高 → CAPA へ")
        draft = Server("draft_capa\nLLM が処置案を下書き\nJev が1案ずつ3問で確かめる\n(原因・再発・具体的)")
        human = Users("human_review\ninterrupt で止まり\n承認・却下と\n採る案を待つ")
        apply = Python("apply\n承認された案だけ\nCAPA に登録")
    db = Postgresql("DB\ntriage_runs\ncapa_actions")
    end = React("終わり\n結果は triage_runs に\n保存して画面へ")
    watch = Python("続けて測る\n/api/triage/metrics\n最新の判定と\nいまの登録値を比べる")

    start >> Edge(color=CODE) >> prepare
    prepare >> Edge(color=JEV) >> desc
    prepare >> Edge(color=JEV) >> cause
    desc >> Edge(color=JEV) >> gate
    cause >> Edge(color=JEV) >> gate
    gate >> Edge(color=LLM, style="dashed", label="閾値未満") >> llm
    llm >> Edge(color=LLM, style="dashed") >> merge
    gate >> Edge(color=CODE, label="すべて採用") >> merge
    # 下の段は右から左へ(U 字)。<< は「矢印の向きだけ逆」なので、段の位置は左へ詰まる
    merge >> Edge(color=CODE) >> plan
    draft << Edge(color=LLM, label="当たる") << plan
    human << Edge(color=HUMAN) << draft
    apply << Edge(color=HUMAN, label="承認") << human
    db << Edge(color=CODE) << apply
    end << Edge(color=CODE, label="当たらない") << plan
    end << Edge(color=HUMAN, style="dashed", label="却下") << human
    watch << Edge(color=OBS, style="dotted") << db
    with getdiagram().dot.subgraph() as sg:
        sg.attr(rank="same")
        sg.node(merge._id)
        sg.node(plan._id)
