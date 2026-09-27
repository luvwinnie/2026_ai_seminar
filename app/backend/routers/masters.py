"""マスタ管理 — /api/masters(docs/04 §2.5)。

ドロップダウン選択肢を DB マスタ化して CRUD する。対象は6カテゴリ。
リネーム時は過去の報告書へ値を伝播し、Chroma メタデータ対象カテゴリは再索引する。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import DefectReport, MasterItem
from schemas import MasterCreate, MasterOut, MasterUpdate, MasterUpdateOut
from services import rag

router = APIRouter(prefix="/api/masters", tags=["masters"])

# カテゴリ → 報告書カラム(集計・伝播に使う)
CATEGORY_COLUMNS = {
    "customer": DefectReport.customer,
    "process": DefectReport.process,
    "machine": DefectReport.machine_name,
    "operator": DefectReport.operator_name,
    "phenomenon": DefectReport.phenomenon,
    "factor": DefectReport.factor,
}

# カテゴリ → 報告書の属性名(ORM オブジェクトから値を取り出す)
CATEGORY_FIELDS = {
    "customer": "customer",
    "process": "process",
    "machine": "machine_name",
    "operator": "operator_name",
    "phenomenon": "phenomenon",
    "factor": "factor",
}

# Chroma メタデータに含まれるカテゴリ(リネーム時に該当報告書を再 upsert する)
METADATA_CATEGORIES = {"customer", "machine", "phenomenon", "process"}

# 既定語彙(docs/03 §2)。operator は自由記述のため既定リストなし(DISTINCT で投入)。
DEFAULT_VOCAB: dict[str, list[str]] = {
    "customer": ["翠峰重工業", "六花電機工業", "蒼井田機器工業", "遠原精密工業", "汐峰造機", "楠里ポンプ工業", "深名電子工業", "綿鍋機工", "鷹森航空部品", "霞岡バルブ工業"],
    "process": ["旋盤", "フライス", "マシニング", "研磨", "溶接", "組立", "検査", "バリ取り"],
    "machine": ["QUICK TURN 250MSY", "GENOS M560-V", "GENOS M660-V", "VARIAXIS i-800 NEO", "TSL-550", "MX-520", "WT-150II", "YZ-8WR", "汎用フライス"],
    "phenomenon": [
        "表面キズ", "寸法公差外れ", "バリ残り", "穴位置ずれ", "加工段差", "面粗さ不良",
        "NCプログラム誤り", "ひずみ変形", "工具破損", "刻印・表示誤り", "角部欠け", "取付方向誤り",
    ],
    "factor": [
        "確認不足", "知識不足", "経験不足", "手順逸脱", "工具摩耗",
        "機械故障", "プログラム誤り", "材料不良", "図面誤読", "連絡不足",
    ],
}


def _column(category: str):
    """カテゴリに対応する報告書カラムを返す。不正カテゴリは 404。"""
    col = CATEGORY_COLUMNS.get(category)
    if col is None:
        raise HTTPException(status_code=404, detail="カテゴリが不正です")
    return col


def _usage_count(db: Session, category: str, name: str) -> int:
    """指定カテゴリ・名称の使用件数(報告書での出現数)。"""
    col = CATEGORY_COLUMNS[category]
    return db.query(func.count(DefectReport.id)).filter(col == name).scalar() or 0


def _usage_map(db: Session, category: str) -> dict[str, int]:
    """カテゴリ内の値ごとの使用件数をまとめて取得する。"""
    col = CATEGORY_COLUMNS[category]
    rows = db.query(col, func.count(DefectReport.id)).group_by(col).all()
    return {value: count for value, count in rows if value is not None}


def _to_out(m: MasterItem, usage_count: int) -> MasterOut:
    return MasterOut(
        id=m.id,
        category=m.category,
        name=m.name,
        sort_order=m.sort_order,
        is_active=m.is_active,
        usage_count=usage_count,
    )


def _find(db: Session, category: str, name: str) -> MasterItem | None:
    """同一カテゴリ内で名称を大文字小文字・前後空白を無視して検索する。"""
    key = name.strip().lower()
    return (
        db.query(MasterItem)
        .filter(MasterItem.category == category, func.lower(MasterItem.name) == key)
        .first()
    )


def ensure_masters(db: Session, report: DefectReport) -> int:
    """報告書の6カテゴリ値のうち、マスタ未登録のものを自動追加する(is_active=True, sort_order=500)。"""
    added = 0
    for category, field in CATEGORY_FIELDS.items():
        value = getattr(report, field, None)
        if value is None:
            continue
        name = str(value).strip()
        if not name or _find(db, category, name):
            continue
        db.add(MasterItem(category=category, name=name, sort_order=500, is_active=True))
        added += 1
    if added:
        db.commit()
    return added


def seed_masters(db: Session) -> int:
    """masters が空のとき、既定語彙 + 報告書の DISTINCT 値を投入する。"""
    if db.query(MasterItem).count() > 0:
        return 0

    inserted = 0
    seen: dict[str, set[str]] = {}

    # (a) 既定語彙(sort_order = リスト順)
    for category, names in DEFAULT_VOCAB.items():
        bucket = seen.setdefault(category, set())
        for i, name in enumerate(names):
            db.add(MasterItem(category=category, name=name, sort_order=i, is_active=True))
            bucket.add(name.strip().lower())
            inserted += 1

    # (b) 報告書の DISTINCT 値(既定に無いものを 900番台で追加)
    for category, col in CATEGORY_COLUMNS.items():
        bucket = seen.setdefault(category, set())
        distinct_vals = sorted(
            {v for (v,) in db.query(col).distinct().all() if v not in (None, "")}
        )
        order = 900
        for v in distinct_vals:
            key = v.strip().lower()
            if key in bucket:
                continue
            db.add(MasterItem(category=category, name=v, sort_order=order, is_active=True))
            bucket.add(key)
            order += 1
            inserted += 1

    db.commit()
    return inserted


@router.get("")
def list_all(db: Session = Depends(get_db)) -> dict[str, list[MasterOut]]:
    """全カテゴリのマスタを返す(各項目に usage_count を付与)。"""
    result: dict[str, list[MasterOut]] = {}
    for category in CATEGORY_COLUMNS:
        usage = _usage_map(db, category)
        items = (
            db.query(MasterItem)
            .filter(MasterItem.category == category)
            .order_by(MasterItem.sort_order, MasterItem.name)
            .all()
        )
        result[category] = [_to_out(m, usage.get(m.name, 0)) for m in items]
    return result


@router.get("/{category}", response_model=list[MasterOut])
def list_category(category: str, active_only: bool = False, db: Session = Depends(get_db)):
    """指定カテゴリの一覧(sort_order, name 順)。active_only=true で有効のみ。"""
    _column(category)  # カテゴリ検証(不正なら 404)
    usage = _usage_map(db, category)
    q = db.query(MasterItem).filter(MasterItem.category == category)
    if active_only:
        q = q.filter(MasterItem.is_active.is_(True))
    items = q.order_by(MasterItem.sort_order, MasterItem.name).all()
    return [_to_out(m, usage.get(m.name, 0)) for m in items]


@router.post("/{category}", response_model=MasterOut, status_code=201)
def create_master(category: str, payload: MasterCreate, db: Session = Depends(get_db)):
    """新規登録。重複(strip + 大文字小文字無視)は 409。"""
    _column(category)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称を入力してください")
    if _find(db, category, name):
        raise HTTPException(status_code=409, detail="その名称は既に存在します")

    item = MasterItem(category=category, name=name, sort_order=500, is_active=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item, _usage_count(db, category, item.name))


@router.put("/{category}/{item_id}", response_model=MasterUpdateOut)
def update_master(
    category: str, item_id: int, payload: MasterUpdate, db: Session = Depends(get_db)
):
    """更新。リネーム時は過去の報告書へ伝播し、メタデータ対象は再索引する。"""
    col = _column(category)
    item = (
        db.query(MasterItem)
        .filter(MasterItem.category == category, MasterItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="マスタが見つかりません")

    updated_reports = 0
    reindex_ids: list[str] = []

    # --- リネーム処理 ---
    if payload.name is not None:
        new_name = payload.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="名称を空にできません")
        if new_name != item.name:
            # 同カテゴリの別マスタと衝突したら 409
            dup = _find(db, category, new_name)
            if dup and dup.id != item.id:
                raise HTTPException(status_code=409, detail="その名称は既に存在します")

            old_name = item.name
            reindex_ids = [
                defect_id
                for (defect_id,) in db.query(DefectReport.defect_id).filter(col == old_name).all()
            ]
            updated_reports = (
                db.query(DefectReport)
                .filter(col == old_name)
                .update({col: new_name}, synchronize_session=False)
            )
            item.name = new_name

    # --- 有効/無効の切替 ---
    if payload.is_active is not None:
        item.is_active = payload.is_active

    db.commit()
    db.refresh(item)

    # Chroma メタデータ対象カテゴリは、伝播した報告書を再 upsert
    if reindex_ids and category in METADATA_CATEGORIES:
        for report in (
            db.query(DefectReport).filter(DefectReport.defect_id.in_(reindex_ids)).all()
        ):
            rag.upsert(report)

    out = _to_out(item, _usage_count(db, category, item.name))
    return MasterUpdateOut(**out.model_dump(), updated_reports=updated_reports)


@router.delete("/{category}/{item_id}", status_code=204)
def delete_master(category: str, item_id: int, db: Session = Depends(get_db)):
    """削除。使用中(usage_count>0)は 409、未使用は物理削除。"""
    _column(category)
    item = (
        db.query(MasterItem)
        .filter(MasterItem.category == category, MasterItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="マスタが見つかりません")

    if _usage_count(db, category, item.name) > 0:
        raise HTTPException(
            status_code=409, detail="使用中のため削除できません。無効化してください。"
        )

    db.delete(item)
    db.commit()
    return None
