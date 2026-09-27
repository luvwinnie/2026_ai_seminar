"""Ontologyの実行層。LLM生成SQLを使わず、定義済み関係を現在のRDBへ対応付ける。"""
from __future__ import annotations

import base64
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from models import CapaAction, DefectReport
from services.ontology_contract import definition

ObjectType = Literal["DefectReport", "MachineLabel", "Process", "Customer", "CapaAction"]
LABEL_FIELDS = {r["to"]: r["binding"] for r in definition()["relations"] if r["to"] != "CapaAction"}
LABEL_COLUMNS = {k: getattr(DefectReport, v) for k, v in LABEL_FIELDS.items()}


class OntologyError(ValueError):
    pass


class QualityScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    defect_id: str | None = Field(None, min_length=1, max_length=100)
    machine_id: str | None = Field(None, min_length=1, max_length=1500)
    process_id: str | None = Field(None, min_length=1, max_length=1500)
    customer_id: str | None = Field(None, min_length=1, max_length=1500)
    date_from: date | None = None
    date_to: date | None = None
    status: Literal["open", "in_progress", "completed"] | None = None
    severity: Literal["critical", "high", "medium", "low"] | None = None
    has_open_capa: bool | None = Field(None, strict=True)

    @model_validator(mode="after")
    def check_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_fromはdate_to以前にしてください")
        return self


class QualityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: QualityScope = Field(default_factory=QualityScope)
    group_by: Literal["MachineLabel", "Process", "Customer"] = "MachineLabel"
    limit: int = Field(20, ge=1, le=100, strict=True)
    offset: int = Field(0, ge=0, le=1000000, strict=True)


def provenance(**extra) -> dict:
    return {"ontology_version": definition()["version"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source": "application_database", **extra}


def label_id(object_type: str, name: str) -> str:
    encoded = base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")
    return f"{object_type}:{encoded}"


def _decode_label(object_type: str, object_id: str) -> str:
    try:
        prefix, encoded = object_id.split(":", 1)
        if prefix != object_type:
            raise ValueError()
        value = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True).decode()
        if not value or label_id(object_type, value) != object_id:
            raise ValueError()
        return value
    except (ValueError, UnicodeError) as e:
        raise OntologyError("型に対応する正しいIDをresolve_ontology_entityから取得してください") from e


def _assert_type(object_type: str):
    if object_type not in definition()["objects"]:
        raise OntologyError(f"未定義のobject_type: {object_type}")


def _page(limit: int, offset: int = 0):
    if not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
        raise OntologyError("limitは1〜100、offsetは0〜1000000です")


def _label(object_type: str, name: str) -> dict:
    return {"object_type": object_type, "object_id": label_id(object_type, name),
            "label": name, "properties": {"name": name},
            "source": {"table": "defect_reports", "field": LABEL_FIELDS[object_type], "value": name}}


def _object(row) -> dict:
    if isinstance(row, DefectReport):
        from services.report_service import report_to_dict
        return {"object_type": "DefectReport", "object_id": row.defect_id,
                "label": f"{row.defect_id} / {row.phenomenon}", "properties": report_to_dict(row),
                "source": {"table": "defect_reports", "key": row.defect_id, "citation": f"[{row.defect_id}]"}}
    from services.capa_service import to_dict
    return {"object_type": "CapaAction", "object_id": row.capa_id, "label": row.title,
            "properties": to_dict(row), "source": {"table": "capa_actions", "key": row.capa_id,
                                                       "report_id": row.defect_id}}


def get_object(db: Session, object_type: str, object_id: str) -> dict:
    _assert_type(object_type)
    if object_type in LABEL_COLUMNS:
        name = _decode_label(object_type, object_id)
        if not db.query(DefectReport.id).filter(LABEL_COLUMNS[object_type] == name).first():
            raise OntologyError("このIDの対象は現在の報告書データに存在しません")
        obj = _label(object_type, name)
    else:
        model, key = (DefectReport, DefectReport.defect_id) if object_type == "DefectReport" else (CapaAction, CapaAction.capa_id)
        row = db.query(model).filter(key == object_id).first()
        if row is None:
            raise OntologyError(f"{object_type} {object_id} が見つかりません")
        obj = _object(row)
    return {"object": obj, "provenance": provenance()}


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def resolve(db: Session, object_type: str, query: str, limit: int = 20) -> dict:
    _assert_type(object_type)
    _page(limit)
    if not query.strip() or len(query) > 300:
        raise OntologyError("queryは1〜300文字で指定してください")
    # 元の名前の同一性は維持。正規化一致が複数あれば選ばない。
    if object_type in LABEL_COLUMNS:
        col = LABEL_COLUMNS[object_type]
        candidates = [_label(object_type, name) for (name,) in db.query(col).distinct().order_by(col).all() if name]
    else:
        model = DefectReport if object_type == "DefectReport" else CapaAction
        key = model.defect_id if object_type == "DefectReport" else model.capa_id
        rows = db.query(model).filter(key == query).all()
        candidates = [_object(r) for r in rows]
    normalized = _normalized(query)
    exact = [o for o in candidates if query in (o["object_id"], o["label"])]
    same = [o for o in candidates if _normalized(o["label"]) == normalized]
    partial = [o for o in candidates if normalized in _normalized(o["label"])]
    matches = exact or same or partial
    match = "exact" if exact else "normalized" if same else "candidate" if partial else "none"
    return {"query": query, "match": match, "can_auto_select": len(matches) == 1 and match in ("exact", "normalized"),
            "total": len(matches), "candidates": matches[:limit], "truncated": len(matches) > limit,
            "provenance": provenance(), "note": "候補一致は同一性の証明ではありません。自動選択不可ならユーザーに確認してください。"}


def traverse(db: Session, object_type: str, object_id: str, relation: str, limit: int = 20, offset: int = 0) -> dict:
    _page(limit, offset)
    source = get_object(db, object_type, object_id)["object"]
    rules = definition()["relations"]
    forward = next((r for r in rules if r["from"] == object_type and r["name"] == relation), None)
    reverse = next((r for r in rules if r["to"] == object_type and r["inverse"] == relation), None)
    if not forward and not reverse:
        raise OntologyError("この型に定義されていない関係です。get_ontology_definitionで確認してください")
    quality = []
    if forward and forward["to"] in LABEL_COLUMNS:
        name = source["properties"].get(forward["binding"])
        items = [_label(forward["to"], name)] if name else []
        total = len(items)
        items = items[offset:offset + limit]
    else:
        if forward:
            q = db.query(CapaAction).filter(CapaAction.defect_id == object_id).order_by(CapaAction.capa_id)
        elif object_type in LABEL_COLUMNS:
            q = db.query(DefectReport).filter(LABEL_COLUMNS[object_type] == source["properties"]["name"]).order_by(DefectReport.defect_id)
        else:
            q = db.query(DefectReport).filter(DefectReport.defect_id == source["properties"]["defect_id"]).order_by(DefectReport.defect_id)
        total = q.count()
        items = [_object(r) for r in q.offset(offset).limit(limit).all()]
        if object_type == "CapaAction" and not total:
            quality.append("対象報告書が存在しない孤立CAPAです。リンクを推測で補いません。")
    return {"source_object": source, "relation": relation, "objects": items, "total": total,
            "next_offset": offset + limit if offset + limit < total else None,
            "quality": quality, "provenance": provenance()}


def _report_query(db: Session, scope: QualityScope):
    q = db.query(DefectReport)
    if scope.defect_id:
        get_object(db, "DefectReport", scope.defect_id)
        q = q.filter(DefectReport.defect_id == scope.defect_id)
    for kind, object_id in (("MachineLabel", scope.machine_id), ("Process", scope.process_id), ("Customer", scope.customer_id)):
        if object_id:
            obj = get_object(db, kind, object_id)["object"]
            q = q.filter(LABEL_COLUMNS[kind] == obj["properties"]["name"])
    for key in ("status", "severity"):
        if getattr(scope, key) is not None:
            q = q.filter(getattr(DefectReport, key) == getattr(scope, key))
    if scope.date_from:
        q = q.filter(DefectReport.occurrence_date >= scope.date_from)
    if scope.date_to:
        q = q.filter(DefectReport.occurrence_date <= scope.date_to)
    if scope.has_open_capa is not None:
        exists = db.query(CapaAction.id).filter(CapaAction.defect_id == DefectReport.defect_id,
                                               CapaAction.status != "closed").exists()
        q = q.filter(exists if scope.has_open_capa else ~exists)
    return q


def _metrics(q) -> tuple[dict, list[str]]:
    r = DefectReport
    invalid = or_(r.production_count < 0, r.defect_count < 0, r.defect_count > r.production_count,
                  r.production_count.is_(None), r.defect_count.is_(None))
    count, defects, production, loss, missing, bad = q.with_entities(
        func.count(r.id), func.sum(r.defect_count), func.sum(r.production_count), func.sum(r.total_cost),
        func.sum(case((r.total_cost.is_(None), 1), else_=0)), func.sum(case((invalid, 1), else_=0)),
    ).one()
    quality = []
    if missing:
        quality.append(f"損失額が未入力の報告が{missing}件あります。既知の金額のみ集計しています。")
    if bad:
        quality.append(f"個数に矛盾・欠損のある報告が{bad}件あります。不適合率は算出しません。")
    if count and not production:
        quality.append("記録加工数の合計が0のため、不適合率は算出できません。")
    return {"report_count": count, "defect_units": defects or 0,
            "recorded_production_units": production or 0,
            "recorded_defect_rate": float(Decimal(defects) / Decimal(production)) if production and count and not bad else None,
            "known_loss_jpy": str(loss) if loss is not None else "0" if not count else None,
            "missing_loss_reports": missing or 0, "invalid_quantity_reports": bad or 0}, quality


def query_quality(db: Session, request: QualityQuery) -> dict:
    q = _report_query(db, request.scope)
    metrics, quality = _metrics(q)
    ids = q.with_entities(DefectReport.defect_id)
    capas = db.query(CapaAction).filter(CapaAction.defect_id.in_(ids))
    metrics["open_capa_count"] = capas.filter(CapaAction.status != "closed").count()
    metrics["overdue_capa_count"] = capas.filter(CapaAction.status != "closed", CapaAction.due_date < date.today()).count()
    # グループ集計にもCAPAをJOINしない。報告書の粒度を維持する。
    col = LABEL_COLUMNS[request.group_by]
    group_query = q.with_entities(col, func.count(DefectReport.id), func.sum(DefectReport.total_cost),
                                  func.sum(case((DefectReport.total_cost.is_(None), 1), else_=0))).group_by(col)
    group_total = group_query.count()
    groups = [{"object": _label(request.group_by, name) if name else None, "report_count": count,
               "known_loss_jpy": str(loss) if loss is not None else None, "missing_loss_reports": missing}
              for name, count, loss, missing in group_query.order_by(func.count(DefectReport.id).desc(), col).limit(100).all()]
    rows = q.order_by(DefectReport.occurrence_date.desc(), DefectReport.defect_id).offset(request.offset).limit(request.limit).all()
    total = metrics["report_count"]
    return {"scope": request.scope.model_dump(mode="json", exclude_none=True), "metrics": metrics,
            "metric_definitions": definition()["metrics"], "group_by": request.group_by, "groups": groups,
            "group_total": group_total, "groups_truncated": group_total > 100,
            "objects": [_object(r) for r in rows], "total": total,
            "next_offset": request.offset + request.limit if request.offset + request.limit < total else None,
            "quality": quality, "limitations": definition()["limitations"][1:2],
            "provenance": provenance(aggregation="全該当報告をSQL集計。objectsはページ内の根拠例。",
                                     as_of_date=date.today().isoformat(), date_field="occurrence_date",
                                     query=request.model_dump(mode="json"))}


def report_graph(db: Session, defect_id: str, capa_limit: int = 50) -> dict:
    """1報告を中心にした実関係グラフ。定義を列挙し、共通traverseでDBリンクを取得。"""
    _page(capa_limit)
    root = get_object(db, "DefectReport", defect_id)["object"]
    def node_key(obj):
        return f"{obj['object_type']}:{obj['object_id']}"
    root_key = node_key(root)
    nodes = {root_key: {"id": root_key, **root}}
    edges = []
    relation_counts = {}
    truncated_relations = []
    quality = []
    for relation in definition()["relations"]:
        result = traverse(db, "DefectReport", defect_id, relation["name"], capa_limit)
        relation_counts[relation["name"]] = result["total"]
        if result["next_offset"] is not None:
            truncated_relations.append({"relation": relation["name"], "next_offset": result["next_offset"],
                                        "total": result["total"]})
        quality.extend(result["quality"])
        for obj in result["objects"]:
            key = node_key(obj)
            nodes[key] = {"id": key, **obj}
            edges.append({"id": f"{root_key}/{relation['name']}/{key}", "source": root_key,
                          "target": key, "relation": relation["name"], "meaning": relation["meaning"],
                          "cardinality": relation["cardinality"], "binding": relation["binding"],
                          "evidence": {"report_id": defect_id, "field": relation["binding"],
                                       "value": root["properties"].get(relation["binding"])}})
    return {"root": root_key, "nodes": list(nodes.values()), "edges": edges,
            "relation_counts": relation_counts, "truncated_relations": truncated_relations,
            "quality": quality, "provenance": provenance(graph_kind="定義済みの実データ関係。類似度・因果推論ではない。")}
