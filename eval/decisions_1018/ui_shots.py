"""判断モデルによる強化の画面を撮る(動いている例アプリ http://localhost:5373)。
作ったチャットの会話は最後に消す。取込は確認画面まで(登録しない)。
使い方：python ui_shots.py   → shots/*.png"""
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE, API = "http://localhost:5373", "http://localhost:8010"
OUT = Path(__file__).resolve().parent / "shots"
OUT.mkdir(exist_ok=True)
ROOT = Path(__file__).resolve().parents[3]  # 例アプリの1つ上の作業フォルダ
SCAN = ROOT / ("tmp/series6/s4/ocr/scan/KZ25-0050_scan.jpg")


def wait_text(page, text, timeout=180):
    page.get_by_text(text).first.wait_for(timeout=timeout * 1000)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.5, locale="ja-JP")
    page = ctx.new_page()

    # 1) スマート検索(当てはまる確率の列)
    from urllib.parse import quote
    page.goto(f"{BASE}/reports?mode=smart&q={quote('QUICK TURN 250MSY の工具破損')}", wait_until="domcontentloaded")
    wait_text(page, "当てはまる確率", 60)
    time.sleep(1)
    page.screenshot(path=str(OUT / "smart_search_rerank.png"))
    print("ok smart")

    # 2) チャット(質問の種類・引用の確かめ)
    before = {s["id"] for s in httpx.get(f"{API}/api/chat/sessions", timeout=30).json()}
    page.goto(f"{BASE}/chat", wait_until="domcontentloaded")
    time.sleep(2)
    box = page.get_by_role("textbox").last
    box.fill("主軸のクランプ圧低下が原因の報告は何件で、どの現象に出ている？")
    box.press("Enter")
    page.get_by_test_id("route-chip").first.wait_for(timeout=60000)
    page.get_by_test_id("citation-checks").first.wait_for(timeout=240000)
    time.sleep(1.5)
    page.screenshot(path=str(OUT / "chat_route_citations.png"))
    print("ok chat")
    after = {s["id"] for s in httpx.get(f"{API}/api/chat/sessions", timeout=30).json()}
    for sid in after - before:
        httpx.delete(f"{API}/api/chat/sessions/{sid}", timeout=30)

    # 3) 帳票の画像の取込(読み取りの確かめ)
    page.goto(f"{BASE}/reports/new", wait_until="domcontentloaded")
    time.sleep(1.5)
    page.set_input_files("input[type=file]", str(SCAN))
    page.get_by_test_id("field-checks").wait_for(timeout=420000)
    time.sleep(1.5)
    page.get_by_test_id("field-checks").scroll_into_view_if_needed()
    page.screenshot(path=str(OUT / "ingest_field_checks.png"), full_page=True)
    print("ok ingest")
    b.close()
