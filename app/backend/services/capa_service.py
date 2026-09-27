"""CAPA(是正・予防処置)と8Dレポート(docs/10 A-3)。

- CAPA: 起票→対応→効果確認→クローズのライフサイクル。CA-XXXX で採番
- AIドラフト: 類似事例(ハイブリッド検索)の「当時の対策」を根拠に処置案を生成
  (OpenCode 不通時は類似事例の対策をそのまま整形する決定論フォールバック)
- 8D: 報告書+CAPA+類似事例から D1〜D8 の Markdown を生成(同じく二層構成)
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy.orm import Session

from models import CapaAction, DefectReport, EightDReport
from services import opencode_client, rag
from services.ontology_contract import definition

_ACTION = definition()["actions"]["update_capa_action"]
VALID_STATUS = tuple(_ACTION["statuses"])
VALID_TYPE = tuple(_ACTION["action_types"])


class CapaError(Exception):
    pass


def next_capa_id(db: Session) -> str:
    max_n = 0
    for (cid,) in db.query(CapaAction.capa_id).all():
        m = re.match(r"CA-(\d+)", cid or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"CA-{max_n + 1:04d}"


def to_dict(a: CapaAction) -> dict:
    ref = date.today()
    return {
        "capa_id": a.capa_id,
        "defect_id": a.defect_id,
        "action_type": a.action_type,
        "title": a.title,
        "description": a.description,
        "owner": a.owner,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "status": a.status,
        "effect_note": a.effect_note,
        "overdue": bool(a.due_date and a.status != "closed" and a.due_date < ref),
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def create(db: Session, data: dict) -> CapaAction:
    defect_id = data.get("defect_id")
    if not db.query(DefectReport).filter_by(defect_id=defect_id).first():
        raise CapaError(f"報告書 {defect_id} が見つかりません")
    if not data.get("title"):
        raise CapaError("title は必須です")
    if data.get("action_type", "corrective") not in VALID_TYPE:
        raise CapaError(f"action_type は {VALID_TYPE}")
    a = CapaAction(
        capa_id=next_capa_id(db),
        defect_id=defect_id,
        action_type=data.get("action_type", "corrective"),
        title=data["title"],
        description=data.get("description"),
        owner=data.get("owner"),
        due_date=date.fromisoformat(data["due_date"]) if data.get("due_date") else None,
        status="open",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def validate_update(db: Session, a: CapaAction, patch: dict) -> dict:
    """プレビューと実行の共通検証。フィールド単体ではなく更新後の状態を検証。"""
    allowed = {"title", "description", "owner", "status", "effect_note", "action_type", "due_date"}
    if set(patch) - allowed:
        raise CapaError("更新可能なCAPAの項目を指定してください")
    clean = {k: v for k, v in patch.items() if v is not None}
    if not db.query(DefectReport.id).filter_by(defect_id=a.defect_id).first():
        raise CapaError("対象報告書が存在しないCAPAは更新できません")
    state = {**to_dict(a), **clean}
    if state["status"] not in VALID_STATUS:
        raise CapaError(f"status は {VALID_STATUS}")
    if state["action_type"] not in VALID_TYPE:
        raise CapaError(f"action_type は {VALID_TYPE}")
    if not isinstance(state["title"], str) or not state["title"].strip():
        raise CapaError("title は空白以外の文字が必要です")
    if state["status"] == "closed":
        for field in _ACTION["required_when_closed"]:
            if not isinstance(state.get(field), str) or not state[field].strip():
                raise CapaError(f"closed には {field}(効果確認メモ)が必要です")
    if "due_date" in clean:
        try:
            clean["due_date"] = date.fromisoformat(clean["due_date"])
        except (ValueError, TypeError):
            raise CapaError("due_date は有効なYYYY-MM-DDで指定してください")
    return clean


def preview_update(db: Session, capa_id: str, patch: dict) -> dict:
    from services.ontology import provenance
    a = db.query(CapaAction).filter_by(capa_id=capa_id).first()
    if a is None:
        raise CapaError(f"{capa_id} が見つかりません")
    before = to_dict(a)
    try:
        clean = validate_update(db, a, patch)
    except CapaError as e:
        return {"valid": False, "saved": False, "errors": [str(e)], "before": before,
                "provenance": provenance()}
    changes = {k: v.isoformat() if isinstance(v, date) else v for k, v in clean.items()}
    after = {**before, **changes}
    due = date.fromisoformat(after["due_date"]) if after["due_date"] else None
    after["overdue"] = bool(due and after["status"] != "closed" and due < date.today())
    return {"valid": True, "saved": False, "errors": [], "before": before, "after": after,
            "changes": changes, "execute_tool": "update_capa_action", "provenance": provenance(),
            "note": "保存・承認ではありません。明示された依頼に基づき実行時に再検証します。競合検出は未実装です。"}


def update(db: Session, capa_id: str, patch: dict) -> CapaAction:
    a = db.query(CapaAction).filter_by(capa_id=capa_id).first()
    if a is None:
        raise CapaError(f"{capa_id} が見つかりません")
    clean = validate_update(db, a, patch)
    for k, value in clean.items():
        setattr(a, k, value)
    db.commit()
    db.refresh(a)
    return a


def list_actions(db: Session, *, status: str | None = None, defect_id: str | None = None,
                 overdue: bool | None = None, limit: int = 100) -> list[dict]:
    q = db.query(CapaAction).order_by(CapaAction.id.desc())
    if status:
        q = q.filter(CapaAction.status == status)
    if defect_id:
        q = q.filter(CapaAction.defect_id == defect_id)
    items = [to_dict(a) for a in q.limit(limit).all()]
    if overdue is not None:
        items = [i for i in items if i["overdue"] == overdue]
    return items


# ---------------------------------------------------------------------------
# AI ドラフト / 8D
# ---------------------------------------------------------------------------

def _similar(db: Session, r: DefectReport, top_k: int = 3) -> list[dict]:
    query = " ".join(filter(None, [r.phenomenon, r.defect_description, r.cause]))
    hits = [h for h in rag.search(db, query, top_k=top_k + 2) if h["defect_id"] != r.defect_id][:top_k]
    rows = {x.defect_id: x for x in db.query(DefectReport).filter(
        DefectReport.defect_id.in_([h["defect_id"] for h in hits])).all()}
    out = []
    for h in hits:
        x = rows.get(h["defect_id"])
        if x:
            out.append({"defect_id": x.defect_id, "phenomenon": x.phenomenon,
                        "cause": x.cause, "countermeasure": x.countermeasure})
    return out


def draft_actions(db: Session, defect_id: str) -> dict:
    """類似事例に基づく処置ドラフト(保存はしない)。"""
    r = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if r is None:
        raise CapaError(f"報告書 {defect_id} が見つかりません")
    similar = _similar(db, r)

    if opencode_client.is_configured():
        try:
            res = opencode_client.ask_json(
                "あなたは製造業の品質保証エンジニアです。与えられた情報のみに基づき、"
                "実行可能で具体的な是正・予防処置を提案してください。捏造禁止。",
                "次の不適合と類似事例を踏まえ、処置案をJSONで返してください。\n"
                '形式: {"actions": [{"action_type": "corrective|preventive", "title": "要約", '
                '"description": "具体的な手順", "based_on": "根拠にした類似事例ID或いは本件"}]}\n'
                "是正2件+予防1件程度。\n\n"
                f"# 本件\n{r.defect_id}: {r.phenomenon} / {r.machine_name} / {r.process}\n"
                f"内容: {r.defect_description}\n原因: {r.cause}\n要因: {r.factor}\n\n"
                f"# 類似事例と当時の対策\n" + "\n".join(
                    f"- {s['defect_id']}({s['phenomenon']}): 対策={s['countermeasure']}" for s in similar),
            )
            actions = res.get("actions") or []
            if actions:
                return {"defect_id": defect_id, "actions": actions, "similar": similar,
                        "ai_backend": "opencode"}
        except Exception:
            pass

    # フォールバック: 類似事例の対策を整形して提示(決定論)
    actions = [
        {"action_type": "corrective",
         "title": f"類似事例 {s['defect_id']} の対策を本件に適用",
         "description": s["countermeasure"] or "(対策記載なし)",
         "based_on": s["defect_id"]}
        for s in similar if s.get("countermeasure")
    ][:3]
    return {"defect_id": defect_id, "actions": actions, "similar": similar, "ai_backend": "none"}


_8D_HEADS = [
    ("D1 チーム編成", "品質保証・製造・技術の関係者でチームを編成する。"),
    ("D2 問題の記述", None),
    ("D3 暫定対策(封じ込め)", None),
    ("D4 根本原因分析", None),
    ("D5 恒久対策の選定", None),
    ("D6 恒久対策の実施と検証", None),
    ("D7 再発防止(横展開)", None),
    ("D8 チームの労い", "対応にあたったメンバーの貢献を確認し、学びを共有する。"),
]


def generate_8d(db: Session, defect_id: str) -> EightDReport:
    r = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if r is None:
        raise CapaError(f"報告書 {defect_id} が見つかりません")
    similar = _similar(db, r)
    capas = list_actions(db, defect_id=defect_id)

    facts = (
        f"報告書 {r.defect_id}\n発生日: {r.occurrence_date} / 客先: {r.customer} / "
        f"工程: {r.process} / 機械: {r.machine_name} / 部品: {r.part_name}({r.part_number})\n"
        f"現象: {r.phenomenon} / 重大度: {r.severity} / 数量: {r.defect_count}/{r.production_count}\n"
        f"内容: {r.defect_description}\n原因: {r.cause}\n要因: {r.factor} / 4M: {r.category_4m}\n"
        f"対策: {r.countermeasure}\n"
        f"CAPA: " + ("; ".join(f"{c['capa_id']}({c['status']}): {c['title']}" for c in capas) or "なし") + "\n"
        f"類似事例: " + ("; ".join(f"{s['defect_id']}: {s['countermeasure'] or ''}" for s in similar) or "なし")
    )

    md = None
    backend = "none"
    if opencode_client.is_configured():
        try:
            md = opencode_client.ask(
                "あなたは自動車部品サプライヤの品質保証エンジニアです。与えられた事実のみを使い、"
                "8Dレポートを日本語Markdownで作成してください。不明な項目は「(要確認)」と書き、捏造しないこと。",
                f"次の不適合について、# 8Dレポート {r.defect_id} を見出しに、D1〜D8の8章構成で"
                f"作成してください。\n\n{facts}",
            ).strip()
            if md:
                backend = "opencode"
        except Exception:
            md = None

    if not md:
        # 決定論フォールバック: 事実をD1〜D8テンプレートに整形
        parts = [f"# 8Dレポート {r.defect_id}(ドラフト)", ""]
        fills = {
            "D2 問題の記述": f"{r.occurrence_date} {r.machine_name}({r.process})で {r.phenomenon}。{r.defect_description}",
            "D3 暫定対策(封じ込め)": r.notes or "(要確認: 同一ロットの選別・隔離状況を記載)",
            "D4 根本原因分析": f"原因: {r.cause or '(要確認)'} / 要因: {r.factor or '-'} / 4M: {r.category_4m or '-'}",
            "D5 恒久対策の選定": r.countermeasure or "(要確認)",
            "D6 恒久対策の実施と検証": "; ".join(f"{c['capa_id']}: {c['title']}({c['status']})" for c in capas) or "(CAPA未登録)",
            "D7 再発防止(横展開)": "類似事例: " + (", ".join(s["defect_id"] for s in similar) or "なし") + " — 同種工程への横展開を検討",
        }
        for head, default in _8D_HEADS:
            parts += [f"## {head}", fills.get(head, default or "(要確認)"), ""]
        md = "\n".join(parts)

    rep = EightDReport(defect_id=defect_id, content_md=md, ai_backend=backend)
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep
