"""帳票の画像の取込(読み取りの確かめ・欄の枠)の画面を撮る。登録はしない。"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "shots"
ROOT = Path(__file__).resolve().parents[3]  # 例アプリの1つ上の作業フォルダ
IMG = ROOT / ("tmp/series6/s4/ocr/scan/KZ25-0050_hard.jpg")
with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.5, locale="ja-JP").new_page()
    page.goto("http://localhost:5373/reports/new", wait_until="domcontentloaded")
    time.sleep(1.5)
    page.set_input_files("input[type=file]", str(IMG))
    page.get_by_test_id("field-checks").wait_for(timeout=300000)
    time.sleep(1)
    page.get_by_text("要確認").first.hover()
    time.sleep(0.5)
    page.get_by_test_id("field-checks").scroll_into_view_if_needed()
    page.screenshot(path=str(OUT / "ingest_field_checks.png"), full_page=False)
    page.get_by_test_id("field-checks").screenshot(path=str(OUT / "ingest_field_checks_panel.png"))
    print("ok")
    b.close()
