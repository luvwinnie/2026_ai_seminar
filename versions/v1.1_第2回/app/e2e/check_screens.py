"""受け入れ条件（07_試験・運用仕様書.md）を画面で確かめ、実際の値を表にする。画面の写真を docs/evidence/ に保存する。

起動中の backend（8110）と画面（5210）に対して動かす（README.md の「起動」のとおりに起動しておく）。
AC-v11-04 では 8110 の backend を止め、確かめたあとで起動し直す。

    cd app/e2e && .venv/bin/python check_screens.py
"""

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

REPO_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_DIR / "app" / "backend"
EVIDENCE_DIR = REPO_DIR / "docs" / "evidence"
WEB = "http://localhost:5210"
API = "http://localhost:8110"
UC1_URL = "/reports?machine=a61nx&date_from=2025-09-01&date_to=2025-09-30"

expect.set_options(timeout=5000)
results: list[tuple[str, str, str, str, str]] = []


def record(ac: str, item: str, expected, actual) -> None:
    mark = "合格" if expected == actual else "不合格"
    results.append((ac, item, str(expected), str(actual), mark))
    print(f"[{mark}] {ac} {item}: 期待 {expected} / 実際 {actual}", flush=True)


def settle(assertion) -> None:
    """期待どおりになるまで待つ。合わないときは、待ったあとの値をそのまま記録する。"""
    try:
        assertion()
    except AssertionError:
        pass


def rows(page: Page):
    return page.get_by_test_id("report-row")


def row_ids(page: Page) -> list[str]:
    return rows(page).locator("td:first-child").all_inner_texts()


def pagination(page: Page) -> str:
    loc = page.get_by_test_id("pagination").locator("p").last
    return loc.inner_text() if loc.count() else "（ページ送りなし）"


def snapshot(page: Page, name: str, whole_page: bool = False) -> None:
    """画面の写真を撮る。入力欄の選択を外し、ページ全体のときは画面の高さをページに合わせる（固定のメニューも全体に写す）。"""
    page.evaluate("document.activeElement && document.activeElement.blur()")
    expect(page.locator(".MuiPopover-root")).to_have_count(0)  # 選択肢のメニューが消えるのを待つ
    if whole_page:
        height = page.evaluate("document.documentElement.scrollHeight")
        page.set_viewport_size({"width": 1280, "height": max(900, height)})
    page.screenshot(path=EVIDENCE_DIR / name)
    page.set_viewport_size({"width": 1280, "height": 900})


def choose(page: Page, label: str, option: str) -> None:
    page.get_by_role("combobox", name=label).click()
    page.get_by_role("option", name=option, exact=True).click()


def wait_http(url: str, up: bool, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            if up:
                return
        except Exception:
            if not up:
                return
        time.sleep(0.25)
    raise RuntimeError(f"{url} が {'起動' if up else '停止'}しません")


def stop_backend() -> None:
    pids = subprocess.run(["lsof", "-t", "-iTCP:8110", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    for pid in pids:
        os.kill(int(pid), signal.SIGTERM)
    wait_http(f"{API}/health", up=False)


def start_backend() -> None:
    log = open(Path(tempfile.gettempdir()) / "defect_backend_restart.log", "a")
    subprocess.Popen(
        [str(BACKEND_DIR / ".venv/bin/uvicorn"), "main:app", "--port", "8110"],
        cwd=BACKEND_DIR, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    wait_http(f"{API}/health", up=True)


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, base_url=WEB)

        # AC-v10-01・02：一覧（既定）
        page.goto("/")
        settle(lambda: expect(page.get_by_test_id("health-badge")).to_have_text("110件"))
        record("AC-v10-01", "バッジ", "110件", page.get_by_test_id("health-badge").inner_text())
        settle(lambda: expect(rows(page)).to_have_count(25))
        record("AC-v10-02", "/ を開いたときの URL", "/reports", page.url.removeprefix(WEB))
        record("AC-v10-02", "ページ送りの総数", "1–25（全110件）", pagination(page))
        first = rows(page).first.locator("td")
        record("AC-v10-02", "先頭の行", "KZ25-0110 2026-03-15", f"{first.nth(0).inner_text()} {first.nth(1).inner_text()}")
        snapshot(page, "01_list.png")
        page.goto("/reports?page=5")
        settle(lambda: expect(rows(page)).to_have_count(10))
        last = rows(page).last.locator("td")
        record("AC-v10-02", "最後の行（5ページ目）", "KZ25-0001 2025-04-07", f"{last.nth(0).inner_text()} {last.nth(1).inner_text()}")

        # AC-v10-03〜05：機械 a61nx と期間（UC-1 の操作）
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        choose(page, "機械", "a61nx")
        settle(lambda: expect(rows(page)).to_have_count(3))
        record("AC-v10-03", "機械 a61nx の行", ["KZ25-0056", "KZ25-0043", "KZ25-0019"], row_ids(page))
        page.get_by_test_id("date-from").fill("2025-09-01")
        page.get_by_test_id("date-to").fill("2025-09-30")
        settle(lambda: expect(rows(page)).to_have_count(1))
        record("AC-v10-05", "URL", UC1_URL, page.url.removeprefix(WEB))
        record("AC-v10-05", "a61nx かつ 2025年9月の行", ["KZ25-0043"], row_ids(page))
        record("AC-v10-05", "ページ送り", "1–1（全1件）", pagination(page))
        snapshot(page, "02_filter_a61nx_2025-09.png")

        # AC-v10-06：期間を2025年10月に変える（終了日から変えて、逆向きの期間を通らないようにする）
        page.get_by_test_id("date-to").fill("2025-10-31")
        page.get_by_test_id("date-from").fill("2025-10-01")
        settle(lambda: expect(page.get_by_test_id("empty-state")).to_be_visible())
        empty = page.get_by_test_id("empty-state")
        record("AC-v10-06", "0件の表示", "条件に一致する報告書がありません", empty.inner_text() if empty.count() else "（表示なし）")
        record("AC-v10-06", "ページ送り", "0–0（全0件）", pagination(page))
        record("AC-v10-06", "表の行数／エラーの表示", "0 / 0", f"{rows(page).count()} / {page.get_by_test_id('error-state').count()}")
        snapshot(page, "03_zero_a61nx_2025-10.png")

        # AC-v10-04：期間だけ
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        page.get_by_test_id("date-from").fill("2025-09-01")
        page.get_by_test_id("date-to").fill("2025-09-30")
        settle(lambda: expect(rows(page)).to_have_count(7))
        record("AC-v10-04", "2025年9月の行（ID順）", [f"KZ25-00{n}" for n in range(42, 49)], sorted(row_ids(page)))

        # AC-v10-07：詳細（一覧の行を押して開く）
        page.goto(UC1_URL)
        settle(lambda: expect(rows(page)).to_have_count(1))
        rows(page).first.click()
        settle(lambda: expect(page.get_by_test_id("field-不良率")).to_be_visible())
        record("AC-v10-07", "URL", "/reports/KZ25-0043", page.url.removeprefix(WEB))
        expected_fields = {
            "発生日": "2025-09-13", "報告日": "2025-09-24", "客先": "翠峰重工業", "発見者名": "祢津",
            "発生工程": "マシニング", "使用機械": "a61nx", "作業者名": "荻原",
            "部品番号": "KRS-A58-5211-D", "部品名称": "補機マウントリブ", "加工数": "12", "不適合数": "3",
            "不良率": "25.00%", "現象分類": "表面キズ", "要因": "習熟不足", "4M分類": "人 (Man)",
            "重要度": "中", "ステータス": "完了", "材料費": "¥20,179", "社内加工費": "¥40,402",
            "外注加工費": "¥0", "その他費用": "¥0", "合計損失": "¥60,581", "再発案件": "いいえ", "手順書": "あり",
        }
        for label, value in expected_fields.items():
            field = page.get_by_test_id(f"field-{label}")
            record("AC-v10-07", label, value, field.inner_text() if field.count() else "（項目なし）")
        snapshot(page, "04_detail_KZ25-0043.png", whole_page=True)

        # AC-v10-08：無い番号の詳細
        page.goto("/reports/KZ25-9999")
        settle(lambda: expect(page.get_by_test_id("error-state")).to_contain_text("報告書が見つかりません"))
        error = page.get_by_test_id("error-state")
        record("AC-v10-08", "画面の理由", True, error.count() > 0 and "報告書が見つかりません" in error.inner_text())

        # AC-v10-09：並べ替え
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        choose(page, "並び順", "損失額が大きい順")
        settle(lambda: expect(rows(page).first.locator("td").first).to_have_text("KZ25-0042"))
        record("AC-v10-09", "損失額が大きい順の上位3件", ["KZ25-0042", "KZ25-0030", "KZ25-0057"], row_ids(page)[:3])
        choose(page, "並び順", "古い順")
        settle(lambda: expect(rows(page).first.locator("td").first).to_have_text("KZ25-0001"))
        record("AC-v10-09", "古い順の先頭", "KZ25-0001", row_ids(page)[0])

        # AC-v10-10：ページ送り（表示件数25で5ページ、最後のページは10行）
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        next_page = page.get_by_role("button", name=re.compile("next page", re.I))
        pages = 1
        while next_page.is_enabled():
            before = pagination(page)
            next_page.click()
            settle(lambda: expect(page.get_by_test_id("pagination")).not_to_contain_text(before))
            settle(lambda: expect(rows(page).first).to_be_visible())
            pages += 1
        record("AC-v10-10", "ページ数", 5, pages)
        record("AC-v10-10", "最後のページ", "101–110（全110件） 10行", f"{pagination(page)} {rows(page).count()}行")

        # AC-v10-11：キーワード
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        page.get_by_label("キーワード").fill("補機マウントリブ")
        settle(lambda: expect(page.get_by_test_id("pagination")).to_contain_text("全5件"))
        record("AC-v10-11", "キーワード 補機マウントリブ", "1–5（全5件）", pagination(page))

        # AC-v10-12：状態の絞り込み
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        choose(page, "ステータス", "未対応")
        settle(lambda: expect(rows(page)).to_have_count(4))
        record("AC-v10-12", "状態 未対応の行（ID順）", ["KZ25-0001", "KZ25-0005", "KZ25-0051", "KZ25-0090"], sorted(row_ids(page)))

        # AC-v11-01・02：期間の誤りは日本語の理由を出す（表は出さない）
        for ac, url, text in [
            ("AC-v11-01", "/reports?date_from=2025-13-01", "開始日が日付として読めません"),
            ("AC-v11-02", "/reports?date_from=2025-10-01&date_to=2025-09-01", "開始日が終了日より後です"),
        ]:
            page.goto(url)
            settle(lambda: expect(page.get_by_test_id("error-state")).to_be_visible())
            error = page.get_by_test_id("error-state")
            message = error.inner_text().replace("\n", " ").strip() if error.count() else "（表示なし）"
            record(ac, "画面の理由", True, text in message)
            record(ac, "表／0件の表示", "0 / 0", f"{page.get_by_test_id('report-table').count()} / {page.get_by_test_id('empty-state').count()}")

        # AC-v11-04：一覧を開いたまま backend を止め、条件を変える
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        stop_backend()
        try:
            choose(page, "ステータス", "未対応")
            settle(lambda: expect(page.get_by_test_id("error-state")).to_be_visible())
            record("AC-v11-04", "失敗の表示（原因）", True, page.get_by_test_id("error-state").count() > 0)
            record("AC-v11-04", "「再試行」", 1, page.get_by_role("button", name="再試行").count())
            record(
                "AC-v11-04", "表／件数／0件の表示", "0 / 0 / 0",
                f"{page.get_by_test_id('report-table').count()} / {page.get_by_test_id('pagination').count()} / {page.get_by_test_id('empty-state').count()}",
            )
            print("  失敗の表示：", page.get_by_test_id("error-state").inner_text().replace("\n", " "), flush=True)
        finally:
            start_backend()
        page.get_by_role("button", name="再試行").click()
        settle(lambda: expect(rows(page)).to_have_count(4))
        record("AC-v11-04", "backend を起こして「再試行」", "1–4（全4件）", pagination(page))

        # AC-v11-07：機械の選択肢はマスタと同じ
        names = [m["name"] for m in page.request.get("/api/masters").json()["machine"]]
        page.goto("/reports")
        settle(lambda: expect(rows(page)).to_have_count(25))
        page.get_by_role("combobox", name="機械").click()
        options = page.get_by_role("option").all_inner_texts()
        record("AC-v11-07", "機械の選択肢の数（「すべて」を除く）", 10, len(options) - 1)
        record("AC-v11-07", "選択肢がマスタと同じ", True, options[1:] == names)
        page.get_by_role("option", name="a61nx", exact=True).click()
        settle(lambda: expect(rows(page)).to_have_count(3))
        record("AC-v11-07", "a61nx を選んだ件数", 3, rows(page).count())

        browser.close()

    print("\n| AC | 確かめたこと | 期待値 | 実際の値 | 合否 |\n|---|---|---|---|---|")
    for row in results:
        print("| " + " | ".join(row) + " |")
    failed = [r for r in results if r[4] != "合格"]
    print(f"\n画面の確認：{len(results)}項目、合格 {len(results) - len(failed)}、不合格 {len(failed)}")
    print(f"画面の写真：{EVIDENCE_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
