# -*- coding: utf-8 -*-
"""GUI E2E 確認 — ChatAssistant の応答と WebMCP 画面操作(Playwright)。

前提: FRONTEND_PORT=5373 docker compose up -d 済み。
実行: example_app/.venv/bin/python e2e/test_chat_webmcp.py
シナリオ:
  1. ダッシュボードが表示される
  2. チャットで質問 → [KZ25-XXXX] 引用付きの回答がストリーミングされる
  3. 「ダッシュボードを画面に出して」→ AIが ui_navigate で /dashboard へ遷移させる
  4. 「KZ25-0001を画面で開いて」→ ui_open_report で /reports/KZ25-0001 へ遷移
各ステップでスクリーンショットを e2e/shots/ に保存する。
"""
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5373"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)
CHAT_INPUT = 'textarea[placeholder*="質問を入力"]'


def send_chat(page, text):
    box = page.locator(CHAT_INPUT).first
    box.fill(text)
    box.press("Enter")


def main():
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(45000)
        console_logs = []
        page.on("console", lambda m: console_logs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console_logs.append(f"[pageerror] {e}"))
        globals()["_dbg"] = (page, console_logs)

        # --- 1. ダッシュボード表示 ---
        page.goto(BASE + "/dashboard")
        expect(page.locator("text=不良").first).to_be_visible(timeout=45000)
        page.screenshot(path=str(SHOTS / "01_dashboard.png"))
        results.append("1. ダッシュボード表示: OK")

        # --- 2. チャットで根拠付き回答 ---
        page.goto(BASE + "/chat")
        page.wait_for_selector(CHAT_INPUT)
        send_chat(page, "GENOS M560-Vで多い不良は何ですか?簡潔に。")
        page.wait_for_function(
            "() => /KZ25-\\d{4}/.test(document.body.innerText)", timeout=180000
        )
        # ストリーミング完了(送信ボタンのスピナーが消える)を待つ
        page.wait_for_function(
            "() => !document.querySelector('.MuiCircularProgress-root')", timeout=180000
        )
        body = page.inner_text("body")
        cites = sorted(set(re.findall(r"KZ25-\d{4}", body)))
        page.screenshot(path=str(SHOTS / "02_chat_answer.png"), full_page=True)
        results.append(f"2. チャット回答: OK (引用 {', '.join(cites[:5])})")

        # --- 3. WebMCP: ダッシュボードへ遷移させる ---
        send_chat(page, "ダッシュボードを画面に出して")
        page.wait_for_url("**/dashboard", timeout=180000)
        time.sleep(1)
        page.screenshot(path=str(SHOTS / "03_ui_navigate_dashboard.png"))
        results.append("3. ui_navigate(dashboard): OK — AIの指示で画面遷移")

        # --- 4. WebMCP: 報告書詳細を開かせる ---
        page.goto(BASE + "/chat")
        page.wait_for_selector(CHAT_INPUT)
        send_chat(page, "KZ25-0001を画面で開いて")
        page.wait_for_url("**/reports/KZ25-0001", timeout=180000)
        time.sleep(1)
        page.screenshot(path=str(SHOTS / "04_ui_open_report.png"))
        results.append("4. ui_open_report(KZ25-0001): OK — 詳細画面へ遷移")

        browser.close()

    print("\n".join(results))
    print("ALL E2E PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"E2E FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        dbg = globals().get("_dbg")
        if dbg:
            page, logs = dbg
            try:
                page.screenshot(path=str(SHOTS / "99_failure.png"), full_page=True)
                print("failure screenshot saved", file=sys.stderr)
                print("console:", "\n".join(logs[-15:]), file=sys.stderr)
            except Exception:
                pass
        sys.exit(1)
