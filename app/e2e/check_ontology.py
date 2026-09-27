"""起動中のアプリでOntologyの閲覧操作を検証。業務データは変更しない。"""
import json
import os
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

BASE = os.getenv("APP_BASE_URL", "http://localhost:5373")
OUT = Path(__file__).resolve().parents[2] / "docs" / "validation" / "ontology_20260915"
OUT.mkdir(parents=True, exist_ok=True)

data = httpx.post(BASE + "/api/ontology/query", json={"limit": 1}).raise_for_status().json()
machine = data["objects"][0]["properties"]["machine_name"]
errors = []
checks = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/analysis/ontology")
    expect(page.get_by_role("heading", name="業務Ontology", exact=True)).to_be_visible()
    expect(page.get_by_text("2. 該当する報告と指標", exact=True)).to_be_visible()
    page.get_by_label("名前を検索", exact=True).fill(machine)
    page.get_by_role("button", name="名前を確認", exact=True).click()
    expect(page.get_by_text("名前が一致しました。期間などを指定して照会できます。", exact=True)).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith('/api/ontology/query') and r.request.method == 'POST') as resp:
        page.get_by_role("button", name="条件で照会", exact=True).click()
    result = resp.value.json()
    assert result["total"] > 0
    assert all(o['properties']['machine_name'] == machine for o in result['objects'])
    expect(page.get_by_text(f"全{result['total']}件のうち、このページに{len(result['objects'])}件を表示。集計は全該当報告を対象とします。", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "desktop_query.png"), full_page=True)
    page.get_by_role("button", name="関連CAPAをたどる", exact=True).first.click()
    capa_total = httpx.get(BASE + f"/api/ontology/graph/{result['objects'][0]['object_id']}").raise_for_status().json()['relation_counts']['has_capa']
    expect(page.get_by_text(f"{capa_total}件の関連CAPA。報告書IDが一致する処置を表示しています。", exact=True)).to_be_visible()
    checks.append('名前解決→条件付き照会→報告書からCAPAを探索（0件を捏造しない）')
    page.get_by_label("名前を検索", exact=True).fill("存在しない機械-ontology-e2e")
    page.get_by_role("button", name="名前を確認", exact=True).click()
    expect(page.get_by_text("該当する名前はありません。指定条件の照会は実行していません。", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="条件で照会", exact=True)).to_be_disabled()
    checks.append('不存在名で条件付き照会を停止')
    page.get_by_role("tab", name="定義と計算方法", exact=True).click()
    expect(page.get_by_text("SUM(defect_count) / SUM(production_count)", exact=True)).to_be_visible()
    page.get_by_role("button", name="機械名（MachineLabel）の定義", exact=True).click()
    expect(page.get_by_text("報告書に記録された機械名による集合。設備個体・シリアル番号・工場を識別しない。", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "desktop_definitions.png"), full_page=True)
    checks.append('関係と計算式・対象定義の閲覧')
    page.get_by_role('tab', name='グラフで見る', exact=True).click()
    expect(page.get_by_role('group', name='Ontology構造グラフ', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='機械名ノード：機械名', exact=True)).to_be_visible()
    page.get_by_role('button', name='機械名ノード：機械名', exact=True).click()
    expect(page.get_by_role('heading', name='選択中：機械名', exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / 'schema_graph.png'), full_page=True, animations='disabled')
    page.get_by_role('button', name='実データの関係', exact=True).click()
    expect(page.get_by_role('group', name='Ontology実データグラフ', exact=True)).to_be_visible()
    if capa_total == 0:
        expect(page.get_by_text('この報告書にはCAPAが登録されていません。CAPAのノードと線は表示していません。', exact=True)).to_be_visible()
    page.get_by_role('button', name=f'機械名ノード：{machine}', exact=True).click()
    expect(page.get_by_role('heading', name=f'選択中：{machine}', exact=True)).to_be_visible()
    page.get_by_role('button', name='グラフを拡大', exact=True).click()
    expect(page.get_by_text('120%', exact=True)).to_be_visible()
    page.get_by_role('button', name='リセット', exact=True).click()
    page.screenshot(path=str(OUT / 'data_graph.png'), full_page=True, animations='disabled')
    checks.append('構造グラフ・実データグラフ・ノード選択・拡大縮小')
    mobile = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark")
    mobile.on("pageerror", lambda e: errors.append(str(e)))
    mobile.goto(BASE + "/analysis/ontology")
    expect(mobile.get_by_text("2. 該当する報告と指標", exact=True)).to_be_visible()
    assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
    mobile.screenshot(path=str(OUT / "mobile.png"), full_page=True)
    mobile.goto(BASE + '/analysis/ontology?view=graph')
    expect(mobile.get_by_role('group', name='Ontology構造グラフ', exact=True)).to_be_visible()
    assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
    mobile.screenshot(path=str(OUT / 'mobile_graph.png'), full_page=True)
    checks.append('390px幅で横はみ出しなし')
    browser.close()
assert not errors, errors
(OUT / "ui_checks.json").write_text(json.dumps({"base": BASE, "checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2))
print(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2))
