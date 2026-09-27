# -*- coding: utf-8 -*-
"""目視デモ v8 — A/B強化機能(週次レポート/CAPA/類似事例/写真/音声/新データ)。
実行: ../.venv/bin/python e2e/demo_new_features.py (終了後もブラウザは10分間開いたまま)
"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5373"
CHAT_INPUT = 'textarea[placeholder*="質問を入力"]'


def step(msg):
    print(f"STEP: {msg}", flush=True)


def ask(page, text, wait_fn=None, timeout=240000, settle=3):
    step(f"送信: {text[:40]}…")
    box = page.locator(CHAT_INPUT).first
    box.click()
    box.type(text, delay=28)
    time.sleep(0.4)
    box.press("Enter")
    if wait_fn:
        wait_fn(timeout)
    page.wait_for_function("() => !document.querySelector('.MuiCircularProgress-root')", timeout=timeout)
    time.sleep(settle)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=180)
    page = browser.new_page(viewport={"width": 1680, "height": 950})
    page.set_default_timeout(60000)

    step("① 新しい完全架空データ(霧沢精機)でダッシュボード表示")
    page.goto(BASE + "/dashboard")
    page.wait_for_selector(CHAT_INPUT)
    time.sleep(2.5)
    page.screenshot(path="e2e/shots/80_v8_dashboard_newdata.png")

    step("② AIに週次レポートを開かせる(A-2)")
    ask(page, "週次レポートの画面にして",
        lambda t: page.wait_for_url("**/digests*", timeout=t), settle=3)
    page.screenshot(path="e2e/shots/81_v8_digests.png")

    step("③ AIに是正処置(CAPA)一覧を開かせる(A-3)")
    ask(page, "是正処置の一覧を見たい",
        lambda t: page.wait_for_url("**/capa*", timeout=t), settle=3)
    page.screenshot(path="e2e/shots/82_v8_capa.png")

    step("④ 報告書詳細 → 類似事例カード+CAPA+写真セクション(A-1/B-4)")
    ask(page, "KZ25-0027を開いて",
        lambda t: page.wait_for_url("**/reports/KZ25-0027", timeout=t), settle=3)
    page.wait_for_selector("text=類似", timeout=30000)
    page.locator("text=類似").first.scroll_into_view_if_needed()
    time.sleep(2)
    page.screenshot(path="e2e/shots/83_v8_detail_similar.png")

    step("⑤ チャットでCAPAドラフト(登録はしない=閲覧のみ)")
    ask(page, "KZ25-0027の是正処置のドラフト案を考えて。登録はまだしないで", settle=4)
    page.screenshot(path="e2e/shots/84_v8_capa_draft_chat.png")

    step("⑥ スマート検索: 帳票の文言をそのまま貼って該当報告書を発見(フレーズブースト)")
    ask(page, "「ギヤケースの全長が図面値45mmに対して0.179mm不足していることが判明した」に該当する報告書を一覧のスマート検索で画面に出して",
        lambda t: page.wait_for_url("**/reports?*mode=smart*", timeout=t), settle=4)
    page.screenshot(path="e2e/shots/85_v8_smart_phrase.png")

    step("完了 — ブラウザは10分間開いたままにします")
    time.sleep(600)
