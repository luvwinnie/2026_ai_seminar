"""画面の受け入れ条件（07_試験・運用仕様書.md）。API で確かめた値が、画面にも同じく出ることを見る。"""

import re

from playwright.sync_api import Page, expect

UC1_URL = "/reports?machine=a61nx&date_from=2025-09-01&date_to=2025-09-30"


def rows(page: Page):
    return page.get_by_test_id("report-row")


def row_ids(page: Page) -> list[str]:
    return rows(page).locator("td:first-child").all_inner_texts()


def choose(page: Page, label: str, option: str) -> None:
    page.get_by_role("combobox", name=label).click()
    page.get_by_role("option", name=option, exact=True).click()


def test_AC_v10_01_health_badge(page: Page):
    page.goto("/reports")
    expect(page.get_by_test_id("health-badge")).to_have_text("110件 · AI: OpenCode")


def test_AC_v10_02_list_default(page: Page):
    page.goto("/")
    expect(page).to_have_url(re.compile(r"/reports$"))
    expect(page.get_by_test_id("pagination")).to_contain_text("1–25（全110件）")
    expect(rows(page)).to_have_count(25)
    assert row_ids(page)[0] == "KZ25-0110"


def test_AC_v10_03_machine_select(page: Page):
    page.goto("/reports")
    expect(rows(page)).to_have_count(25)
    choose(page, "機械", "a61nx")
    expect(page).to_have_url(re.compile(r"machine=a61nx"))
    expect(rows(page)).to_have_count(3)
    assert row_ids(page) == ["KZ25-0056", "KZ25-0043", "KZ25-0019"]


def test_AC_v10_04_period_input(page: Page):
    page.goto("/reports")
    expect(rows(page)).to_have_count(25)
    page.get_by_test_id("date-from").fill("2025-09-01")
    page.get_by_test_id("date-to").fill("2025-09-30")
    expect(page).to_have_url(re.compile(r"date_from=2025-09-01&date_to=2025-09-30"))
    expect(page.get_by_test_id("pagination")).to_contain_text("全7件")
    assert sorted(row_ids(page)) == [f"KZ25-00{n}" for n in range(42, 49)]


def test_AC_v10_05_url_reproduces_list(page: Page):
    page.goto(UC1_URL)
    expect(rows(page)).to_have_count(1)
    assert row_ids(page) == ["KZ25-0043"]
    page.reload()
    expect(rows(page)).to_have_count(1)
    assert row_ids(page) == ["KZ25-0043"]


def test_AC_v10_06_zero_view(page: Page):
    page.goto("/reports?machine=a61nx&date_from=2025-10-01&date_to=2025-10-31")
    expect(page.get_by_test_id("empty-state")).to_have_text("条件に一致する報告書がありません")
    expect(page.get_by_test_id("pagination")).to_contain_text("全0件")
    expect(rows(page)).to_have_count(0)
    expect(page.get_by_test_id("error-state")).to_have_count(0)


def test_AC_v10_07_detail(page: Page):
    page.goto(UC1_URL)
    rows(page).first.click()
    expect(page).to_have_url(re.compile(r"/reports/KZ25-0043$"))
    expected = {
        "報告書ID": "KZ25-0043",
        "発生日": "2025-09-13",
        "報告日": "2025-09-24",
        "客先": "翠峰重工業",
        "発見者名": "祢津",
        "発生工程": "マシニング",
        "使用機械": "a61nx",
        "作業者名": "荻原",
        "部品番号": "KRS-A58-5211-D",
        "部品名称": "補機マウントリブ",
        "加工数": "12",
        "不適合数": "3",
        "不良率": "25.00%",
        "現象分類": "表面キズ",
        "要因": "習熟不足",
        "4M分類": "人 (Man)",
        "重要度": "中",
        "ステータス": "完了",
        "材料費": "¥20,179",
        "社内加工費": "¥40,402",
        "外注加工費": "¥0",
        "その他費用": "¥0",
        "合計損失": "¥60,581",
        "再発案件": "いいえ",
        "手順書": "あり",
    }
    for label, value in expected.items():
        expect(page.get_by_test_id(f"field-{label}")).to_have_text(value)
    # 一覧へ戻ると、同じ条件の一覧になる
    page.get_by_role("link", name="一覧へ戻る").click()
    expect(page).to_have_url(re.compile(re.escape(UC1_URL) + "$"))
    expect(rows(page)).to_have_count(1)


def test_AC_v10_08_not_found(page: Page):
    page.goto("/reports/KZ25-9999")
    expect(page.get_by_test_id("error-state")).to_contain_text("報告書が見つかりません")


def test_AC_v10_09_sort_select(page: Page):
    page.goto("/reports")
    expect(rows(page)).to_have_count(25)
    choose(page, "並び順", "損失額が大きい順")
    expect(page).to_have_url(re.compile(r"sort=-total_cost"))
    expect(rows(page).first.locator("td").first).to_have_text("KZ25-0042")
    choose(page, "並び順", "古い順")
    expect(rows(page).first.locator("td").first).to_have_text("KZ25-0001")


def test_AC_v10_10_paging(page: Page):
    page.goto("/reports")
    expect(page.get_by_test_id("pagination")).to_contain_text("1–25（全110件）")
    next_page = page.get_by_role("button", name=re.compile("next page", re.I))
    # 1回押すごとに、そのページが出るのを待ってから次を押す
    for label in ["26–50", "51–75", "76–100", "101–110"]:
        next_page.click()
        expect(page.get_by_test_id("pagination")).to_contain_text(f"{label}（全110件）")
    expect(page).to_have_url(re.compile(r"page=5"))
    expect(rows(page)).to_have_count(10)
    expect(next_page).to_be_disabled()


def test_AC_v10_11_keyword(page: Page):
    page.goto("/reports")
    expect(rows(page)).to_have_count(25)
    page.get_by_label("キーワード").fill("補機マウントリブ")
    expect(page).to_have_url(re.compile(r"q=%E8%A3%9C%E6%A9%9F"))  # 「補機」
    expect(page.get_by_test_id("pagination")).to_contain_text("全5件")


def test_AC_v11_01_invalid_date_message(page: Page):
    page.goto("/reports?date_from=2025-13-01")
    error = page.get_by_test_id("error-state")
    expect(error).to_contain_text("開始日が日付として読めません")
    expect(page.get_by_test_id("report-table")).to_have_count(0)
    expect(page.get_by_role("button", name="再試行")).to_have_count(0)


def test_AC_v11_02_reversed_period_message(page: Page):
    page.goto("/reports?date_from=2025-10-01&date_to=2025-09-01")
    expect(page.get_by_test_id("error-state")).to_contain_text("開始日が終了日より後です")
    expect(page.get_by_test_id("report-table")).to_have_count(0)
    expect(page.get_by_test_id("empty-state")).to_have_count(0)


def test_AC_v11_04_loading_view(page: Page):
    held = []
    page.route(re.compile(r"/api/reports\?"), lambda route: held.append(route))
    page.goto("/reports")
    expect(page.get_by_text("読み込み中…")).to_be_visible()
    expect(page.get_by_test_id("report-table")).to_have_count(0)
    expect(page.get_by_test_id("empty-state")).to_have_count(0)
    page.unroute(re.compile(r"/api/reports\?"))
    for route in held:
        try:
            route.continue_()
        except Exception:
            pass  # 画面が取り消した（StrictMode で2回目に送り直した）要求
    expect(rows(page)).to_have_count(25)


def test_AC_v11_07_machine_options(page: Page):
    masters = page.request.get("/api/masters").json()
    names = [m["name"] for m in masters["machine"]]
    assert len(names) == 10
    page.goto("/reports")
    expect(rows(page)).to_have_count(25)
    page.get_by_role("combobox", name="機械").click()
    options = page.get_by_role("option").all_inner_texts()
    assert options == ["すべて", *names]
    page.get_by_role("option", name="a61nx", exact=True).click()
    expect(rows(page)).to_have_count(3)


def test_AC_v11_04_failure_vs_empty(page: Page, backend):
    page.goto("/reports")
    expect(rows(page)).to_have_count(25)
    backend.stop()
    try:
        choose(page, "ステータス", "未対応")
        error = page.get_by_test_id("error-state")
        expect(error).to_contain_text("読み込みに失敗しました")
        expect(page.get_by_role("button", name="再試行")).to_be_visible()
        expect(page.get_by_test_id("report-table")).to_have_count(0)
        expect(page.get_by_test_id("pagination")).to_have_count(0)
        expect(page.get_by_test_id("empty-state")).to_have_count(0)
    finally:
        backend.start()
    page.get_by_role("button", name="再試行").click()
    expect(rows(page)).to_have_count(4)
    assert sorted(row_ids(page)) == ["KZ25-0001", "KZ25-0005", "KZ25-0051", "KZ25-0090"]
