# -*- coding: utf-8 -*-
"""ui_navigate 総当たり検証 — REST(/api/ui/*)経由でLLMを介さず全ページ・全機能を確認。
実行: ../.venv/bin/python e2e/check_ui_navigate.py
"""
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5373"

NAV_CASES = [
    ("dashboard+期間", {"page": "dashboard", "params": {"date_from": "2025-10-01", "date_to": "2025-12-31"}},
     "**/dashboard?*date_from*", "text=期間"),
    ("alerts", {"page": "alerts", "params": {}}, "**/alerts", "text=アラート"),
    ("digests(週次レポート)", {"page": "digests", "params": {}}, "**/digests", "text=週次"),
    ("capa+絞り込み", {"page": "capa", "params": {"status": "open"}}, "**/capa?*status=open*", "text=是正"),
    ("analysis_graph(関連マップ)", {"page": "analysis_graph", "params": {}}, "**/analysis/graph", "text=関連マップ"),
    ("reports+複合フィルタ", {"page": "reports", "params": {"machine": "GENOS M560-V", "severity": "high", "sort": "-total_cost"}},
     "**/reports?*machine*", "text=不適合報告書"),
    ("reports+期間", {"page": "reports", "params": {"date_from": "2025-10-01", "date_to": "2025-10-31"}},
     "**/reports?*date_from*", "text=不適合報告書"),
    ("reportsスマート検索", {"page": "reports", "params": {"mode": "smart", "q": "治具の固定が甘くてワークがずれた"}},
     "**/reports?*mode=smart*", "text=類似度"),
    ("analysis_machines+sort", {"page": "analysis_machines", "params": {"sort_by": "total_cost", "order": "desc"}},
     "**/analysis/machines?*sort_by*", "text=機械別"),
    ("analysis_operators", {"page": "analysis_operators", "params": {"date_from": "2025-04-01"}},
     "**/analysis/operators?*", "text=担当者別"),
    ("analysis_customers", {"page": "analysis_customers", "params": {}}, "**/analysis/customers", "text=顧客別"),
    ("analysis_trends+months", {"page": "analysis_trends", "params": {"months": 6}},
     "**/analysis/trends?*months=6*", "text=時系列"),
    ("masters", {"page": "masters", "params": {}}, "**/settings/masters", "text=マスタ"),
    ("chat(全画面)", {"page": "chat", "params": {}}, "**/chat", "text=AIチャット"),
]


def main():
    ok, ng = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1680, "height": 950})
        page.set_default_timeout(20000)
        page.goto(BASE + "/dashboard")
        page.wait_for_selector('textarea[placeholder*="質問を入力"]')
        time.sleep(1)  # SSE接続待ち

        for name, body, url_pat, sel in NAV_CASES:
            try:
                r = httpx.post(f"{BASE}/api/ui/navigate", json=body, timeout=10).json()
                assert r.get("ok"), r
                page.wait_for_url(url_pat, timeout=10000)
                page.wait_for_selector(sel, timeout=10000)
                ok.append(name)
                print(f"OK  {name} -> {r['path']}", flush=True)
            except Exception as e:
                ng.append((name, str(e)[:120]))
                print(f"NG  {name}: {str(e)[:120]}", flush=True)
            time.sleep(0.4)

        # open_report
        try:
            httpx.post(f"{BASE}/api/ui/open_report/KZ25-0007", timeout=10)
            page.wait_for_url("**/reports/KZ25-0007", timeout=10000)
            page.wait_for_selector("text=基本情報", timeout=10000)
            ok.append("open_report")
            print("OK  open_report", flush=True)
        except Exception as e:
            ng.append(("open_report", str(e)[:120]))

        # 新規作成の下書きプリフィル(navigate 経由)
        try:
            httpx.post(f"{BASE}/api/ui/command", json={
                "name": "noop"}, timeout=10)  # commandの疎通のみ
            r = httpx.get(f"{BASE}/api/reports/KZ25-0007", timeout=10).json()
            # ui_new_report と同じパスをブラウザで直接開いて検証
            page.goto(BASE + "/reports/new?machine_name=GENOS%20M560-V&phenomenon=表面キズ&part_name=シャフト")
            page.wait_for_selector('input[value="GENOS M560-V"]', timeout=10000)
            ok.append("new_report_prefill")
            print("OK  new_report_prefill", flush=True)
        except Exception as e:
            ng.append(("new_report_prefill", str(e)[:120]))

        # 編集モードコマンド
        try:
            httpx.post(f"{BASE}/api/ui/command", json={
                "name": "edit", "params": {"defect_id": "KZ25-0007"}, "path": "/reports/KZ25-0007"}, timeout=10)
            page.wait_for_url("**/reports/KZ25-0007", timeout=10000)
            page.wait_for_selector("text=保存", timeout=10000)
            ok.append("edit_command")
            print("OK  edit_command(編集モード起動)", flush=True)
        except Exception as e:
            ng.append(("edit_command", str(e)[:120]))

        # テーマ切替
        try:
            httpx.post(f"{BASE}/api/ui/command", json={"name": "set_theme", "params": {"mode": "dark"}}, timeout=10)
            page.wait_for_selector("text=テーマを", timeout=10000)
            httpx.post(f"{BASE}/api/ui/command", json={"name": "set_theme", "params": {"mode": "light"}}, timeout=10)
            ok.append("set_theme")
            print("OK  set_theme(dark→light)", flush=True)
        except Exception as e:
            ng.append(("set_theme", str(e)[:120]))

        browser.close()

    print(f"\n==== {len(ok)} OK / {len(ng)} NG ====")
    for n, e in ng:
        print("NG:", n, e)
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()
