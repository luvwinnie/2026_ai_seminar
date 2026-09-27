# -*- coding: utf-8 -*-
"""アプリ紹介動画の撮影 — Playwright の録画機能で操作を webm に記録し、ffmpeg で mp4 化。
実行: ../.venv/bin/python e2e/record_video.py  → e2e/videos/defectreport_demo.mp4

構成(約2〜3分):
  ①ダッシュボード ②AIに週次レポートを開かせる ③AIへ質問(引用付き回答+👍)
  ④スマート検索(帳票文言の逐語) ⑤報告書詳細(類似事例・CAPA) ⑥関連マップ ⑦AIでダーク切替
"""
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5373"
CHAT = 'textarea[placeholder*="質問を入力"]'
OUT = Path(__file__).parent / "videos"
OUT.mkdir(exist_ok=True)


def step(msg):
    print(f"STEP: {msg}", flush=True)


def glide(page, x, y, steps=25):
    page.mouse.move(x, y, steps=steps)


def ask(page, text, wait_fn=None, timeout=300000, settle=2.5):
    step(f"送信: {text[:40]}")
    box = page.locator(CHAT).first
    box.click()
    box.type(text, delay=45)
    time.sleep(0.5)
    box.press("Enter")
    if wait_fn:
        wait_fn(timeout)
    page.wait_for_function("() => !document.querySelector('.MuiCircularProgress-root')", timeout=timeout)
    time.sleep(settle)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=120)
    ctx = browser.new_context(
        viewport={"width": 1600, "height": 900},
        record_video_dir=str(OUT),
        record_video_size={"width": 1600, "height": 900},
    )
    page = ctx.new_page()
    page.set_default_timeout(60000)

    step("① ダッシュボード(KPI・パレート図)")
    page.goto(BASE + "/dashboard")
    page.wait_for_selector(CHAT)
    time.sleep(3)
    page.mouse.wheel(0, 500); time.sleep(1.6)
    page.mouse.wheel(0, 600); time.sleep(1.6)
    page.mouse.wheel(0, -1200); time.sleep(1.2)

    step("② AIに週次レポートを開かせる(WebMCP)")
    ask(page, "週次レポートの画面にして",
        lambda t: page.wait_for_url("**/digests*", timeout=t), settle=3)

    step("③ AIへ質問 → 引用付き回答 → 👍")
    ask(page, "GENOS M560-Vで多い不具合を簡潔に教えて", settle=3)
    try:
        page.locator('[aria-label="役に立った"]').last.click(timeout=5000)
        time.sleep(1.5)
    except Exception:
        pass

    step("④ スマート検索(帳票の文言をそのまま)")
    ask(page, "「ギヤケースの全長が図面値45mmに対して0.179mm不足していることが判明した」に該当する報告書を一覧のスマート検索で画面に出して",
        lambda t: page.wait_for_url("**/reports?*mode=smart*", timeout=t), settle=3.5)

    step("⑤ 報告書詳細(類似事例・CAPA)")
    ask(page, "KZ25-0027を画面で開いて",
        lambda t: page.wait_for_url("**/reports/KZ25-0027", timeout=t), settle=2)
    page.locator("text=類似").first.scroll_into_view_if_needed()
    time.sleep(2.5)
    page.mouse.wheel(0, 300); time.sleep(2)

    step("⑥ 関連マップ(GraphRAG層の可視化)")
    page.goto(BASE + "/analysis/graph")
    page.wait_for_selector("canvas")
    time.sleep(4)
    glide(page, 800, 450); glide(page, 950, 500); glide(page, 700, 400)
    time.sleep(2)

    step("⑦ AIでダークモードに切替")
    ask(page, "ダークモードにして", settle=3)

    step("録画終了")
    video = page.video
    ctx.close()
    webm = Path(video.path())
    browser.close()

mp4 = OUT / "defectreport_demo.mp4"
subprocess.run(["ffmpeg", "-y", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "23", "-movflags", "+faststart", str(mp4)], check=True,
               capture_output=True)
webm.unlink()
print(f"saved: {mp4} ({mp4.stat().st_size/1e6:.1f} MB)")
