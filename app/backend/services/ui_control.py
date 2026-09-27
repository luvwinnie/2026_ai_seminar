"""画面操作の共通ロジック — MCPツール(services/mcp_server.py)と
REST(routers/ui.py の POST /api/ui/*)の両方から使う単一実装。

ここに集約することで、LLMを介さない検証(全ページの総当たりE2E)と
本番のAI操作が同じコードパスを通ることを保証する。
"""
from __future__ import annotations

from urllib.parse import urlencode

from services import ui_bus

UI_PAGES = {
    "dashboard": "/dashboard",
    "alerts": "/alerts",
    "reports": "/reports",
    "chat": "/chat",
    "masters": "/settings/masters",
    "analysis_machines": "/analysis/machines",
    "analysis_operators": "/analysis/operators",
    "analysis_customers": "/analysis/customers",
    "analysis_trends": "/analysis/trends",
    "analysis_graph": "/analysis/graph",
    "ontology": "/analysis/ontology",
    "ontology_graph": "/analysis/ontology?view=graph",
    "digests": "/digests",
    "capa": "/capa",
}

# ページごとに許可するクエリパラメータ(それ以外は黙って捨てる)
PAGE_PARAMS = {
    "reports": ("q", "machine", "severity", "status", "process", "customer", "operator",
                "phenomenon", "category_4m", "sort", "mode", "date_from", "date_to"),
    "dashboard": ("date_from", "date_to"),
    "analysis_machines": ("date_from", "date_to", "sort_by", "order"),
    "analysis_operators": ("date_from", "date_to", "sort_by", "order"),
    "analysis_customers": ("date_from", "date_to", "sort_by", "order"),
    "analysis_trends": ("date_from", "date_to", "months"),
    "capa": ("status", "overdue", "defect_id"),
}

_NO_BROWSER = "ブラウザ画面が接続されていません(アプリを開いてもらってください)"


def build_path(page: str, params: dict) -> str:
    """ページ名+パラメータからアプリ内パスを組み立てる。未知ページは ValueError。"""
    if page not in UI_PAGES:
        raise ValueError(f"未知のページ: {page}(候補: {', '.join(UI_PAGES)})")
    path = UI_PAGES[page]
    allowed = PAGE_PARAMS.get(page, ())
    qs = {k: v for k, v in params.items() if k in allowed and v not in (None, "")}
    if qs:
        path += "?" + urlencode(qs)
    return path


def navigate(page: str, **params) -> dict:
    try:
        path = build_path(page, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    n = ui_bus.publish({"action": "navigate", "path": path, "reason": f"{page} へ遷移"})
    if n == 0:
        return {"ok": False, "error": _NO_BROWSER}
    return {"ok": True, "path": path, "receivers": n}


def open_report(defect_id: str) -> dict:
    path = f"/reports/{defect_id}"
    n = ui_bus.publish({"action": "navigate", "path": path, "reason": f"報告書 {defect_id} を表示"})
    if n == 0:
        return {"ok": False, "error": _NO_BROWSER}
    return {"ok": True, "path": path, "receivers": n}


def command(name: str, params: dict | None = None, path: str | None = None, reason: str = "") -> dict:
    ev: dict = {"action": "command", "name": name, "params": params or {}, "reason": reason or name}
    if path:
        ev["path"] = path
    n = ui_bus.publish(ev)
    if n == 0:
        return {"ok": False, "error": _NO_BROWSER}
    out = {"ok": True, "receivers": n}
    if path:
        out["path"] = path
    return out
