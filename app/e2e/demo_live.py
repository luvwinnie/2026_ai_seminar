# -*- coding: utf-8 -*-
"""目視デモ v7 — ui_navigate改善(「〜にして」で発動)+リサイズ+レスポンシブ。
実行: ../.venv/bin/python e2e/demo_live.py (終了後もブラウザは10分間開いたまま)
"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5373"
CHAT_INPUT = 'textarea[placeholder*="質問を入力"]'


def step(msg):
    print(f"STEP: {msg}", flush=True)


def ask(page, text, wait_fn=None, timeout=240000, settle=3):
    step(f"送信: {text[:34]}…")
    box = page.locator(CHAT_INPUT).first
    box.click()
    box.type(text, delay=32)
    time.sleep(0.4)
    box.press("Enter")
    if wait_fn:
        wait_fn(timeout)
    page.wait_for_function("() => !document.querySelector('.MuiCircularProgress-root')", timeout=timeout)
    time.sleep(settle)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=200)

    # ===== デスクトップ =====
    page = browser.new_page(viewport={"width": 1680, "height": 950})
    page.set_default_timeout(60000)
    step("① デスクトップ3カラム表示")
    page.goto(BASE + "/dashboard")
    page.wait_for_selector(CHAT_INPUT)
    time.sleep(2)

    step("② チャット幅をドラッグで拡大→ダブルクリックで戻す")
    h = page.locator('[aria-label="チャットパネルの幅を変更"]')
    box = h.bounding_box()
    page.mouse.move(box["x"] + 3, box["y"] + 300)
    page.mouse.down()
    page.mouse.move(box["x"] + 200, box["y"] + 300, steps=25)
    page.mouse.up()
    time.sleep(1.5)
    page.locator('[aria-label="チャットパネルの幅を変更"]').dblclick()
    time.sleep(1.2)

    # 「画面に出して」と言わなくても表示意図で ui_navigate が発動する(改善点)
    ask(page, "2025年10月から12月のサマリーにして",
        lambda t: page.wait_for_url("**/dashboard?*date_from*", timeout=t), settle=4)

    try:
        ask(page, "機械別分析を損失額の大きい順にして",
            lambda t: page.wait_for_url("**/analysis/machines*", timeout=90000), settle=4)
    except Exception:
        step("遷移しなかったため明示表現でリトライ")
        ask(page, "機械別分析を損失額の大きい順で画面に出して",
            lambda t: page.wait_for_url("**/analysis/machines*", timeout=t), settle=4)
    page.screenshot(path="e2e/shots/70_v7_desktop.png")

    # ===== モバイル表示(同じアプリをそのまま) =====
    step("③ モバイル(375px)ウィンドウでレスポンシブ確認")
    m = browser.new_page(viewport={"width": 375, "height": 812})
    m.goto(BASE + "/dashboard")
    m.wait_for_selector("text=DefectReport AI")
    time.sleep(2)
    m.get_by_label("メニューを開く").click()
    time.sleep(1.2)
    m.keyboard.press("Escape")
    time.sleep(0.6)
    m.get_by_label("AIアシスタントを開閉").click()
    time.sleep(1.5)
    m.screenshot(path="e2e/shots/71_v7_mobile_chat.png")
    step("完了")
    print("DEMO DONE — 2つのウィンドウを10分間開いたままにします。", flush=True)
    time.sleep(600)
    browser.close()
