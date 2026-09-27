# -*- coding: utf-8 -*-
"""レスポンシブ検証 — 375/768/1280/1680px でレイアウト崩れ・操作性を確認しスクショ保存。"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5373"
S = "e2e/shots"

with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # --- モバイル(375) ---
    m = browser.new_page(viewport={"width": 375, "height": 812})
    m.goto(BASE + "/dashboard")
    m.wait_for_selector("text=DefectReport AI")
    time.sleep(1.5)
    assert m.locator('button[aria-label="メニューを開く"]').is_visible(), "ハンバーガー無し"
    hscroll = m.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
    m.screenshot(path=f"{S}/60_mobile_dashboard.png")
    m.get_by_label("メニューを開く").click()
    time.sleep(0.6)
    m.screenshot(path=f"{S}/61_mobile_nav.png")
    m.keyboard.press("Escape")
    time.sleep(0.4)
    m.get_by_label("AIアシスタントを開閉").click()
    time.sleep(0.6)
    assert m.locator('textarea[placeholder*="質問を入力"]').is_visible(), "モバイルでチャット開けず"
    m.screenshot(path=f"{S}/62_mobile_chat_overlay.png")
    m.get_by_label("チャットパネルをたたむ").click()  # 閉じるのはパネル内ボタン or バックドロップ
    time.sleep(0.5)
    m.goto(BASE + "/reports")
    time.sleep(1.5)
    m.screenshot(path=f"{S}/63_mobile_reports.png")
    print(f"mobile OK (横スクロール={'あり!' if hscroll else 'なし'})")
    m.close()

    # --- タブレット(768) ---
    t = browser.new_page(viewport={"width": 768, "height": 1024})
    t.goto(BASE + "/dashboard")
    t.wait_for_selector("text=DefectReport AI")
    time.sleep(1.5)
    t.screenshot(path=f"{S}/64_tablet_dashboard.png")
    print("tablet OK")
    t.close()

    # --- ノートPC(1280: lg以上なので3カラム) ---
    l = browser.new_page(viewport={"width": 1280, "height": 800})
    l.goto(BASE + "/reports")
    l.wait_for_selector('textarea[placeholder*="質問を入力"]')
    time.sleep(1.5)
    l.screenshot(path=f"{S}/65_laptop_reports.png")
    print("laptop OK")
    l.close()

    # --- デスクトップ(1680) + リサイズハンドル ---
    d = browser.new_page(viewport={"width": 1680, "height": 950})
    d.goto(BASE + "/dashboard")
    d.wait_for_selector('textarea[placeholder*="質問を入力"]')
    time.sleep(1)
    handle = d.locator('[aria-label="チャットパネルの幅を変更"]')
    assert handle.count() == 1, "リサイズハンドル無し"
    box = handle.bounding_box()
    x0 = box["x"] + 3
    y = box["y"] + 300
    d.mouse.move(x0, y)
    d.mouse.down()
    d.mouse.move(x0 + 180, y, steps=12)
    d.mouse.up()
    time.sleep(0.5)
    w = d.evaluate("localStorage.getItem('chatPanelWidth')")
    d.screenshot(path=f"{S}/66_desktop_resized.png")
    assert w and int(w) > 500, f"リサイズ保存されず: {w}"
    # ダブルクリックで既定幅へ
    handle2 = d.locator('[aria-label="チャットパネルの幅を変更"]')
    handle2.dblclick()
    time.sleep(0.5)
    w2 = d.evaluate("localStorage.getItem('chatPanelWidth')")
    assert w2 == "400", f"リセットされず: {w2}"
    print(f"desktop resize OK (drag→{w}px, dblclick→{w2}px)")
    d.close()
    browser.close()

print("RESPONSIVE ALL OK")
