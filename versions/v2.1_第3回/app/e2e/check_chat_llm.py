"""【LLM】チャットの画面を、実際の LLM で確かめる（07_試験・運用仕様書.md AC-v20-04、UC-2）。料金・時間がかかるので1回1問。

起動中の画面（Docker Compose の 5220）に対して動かす。質問を1つ送り、回答が終わったら再読込して、会話が戻ることを見る。
画面の写真を docs/evidence/v21/ に保存する。

    cd app/e2e && .venv/bin/python check_chat_llm.py "汎用フライスのバリ残りは何件？"
"""

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_DIR = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_DIR / "docs" / "evidence" / "v21"
WEB = "http://localhost:5220"
API = "http://localhost:8120"
ANSWER_TIMEOUT = 300_000  # ミリ秒。ローカル LLM は1問に数十秒かかる


def main(question: str) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{WEB}/chat")
        page.get_by_role("button", name="新しいチャット").click()
        box = page.get_by_test_id("chat-input")
        box.fill(question)
        box.press("Enter")
        # 回答が終わる（入力欄が戻る）まで待つ
        expect(box).to_be_enabled(timeout=ANSWER_TIMEOUT)
        error = page.get_by_test_id("chat-error")
        if error.count():
            print("error:", error.inner_text())
        answer = page.get_by_test_id("chat-assistant").last
        print("道具:", answer.get_by_test_id("tool-line").all_inner_texts())
        print("回答:", answer.inner_text())
        page.screenshot(path=str(EVIDENCE_DIR / "07_chat_llm_answer.png"))

        # 再読込しても会話が残り、開き直せる（AC-v20-04）
        page.reload()
        item = page.get_by_test_id("session-item").filter(has_text=question[:30]).first
        print("一覧の行:", item.inner_text().replace("\n", " "))
        item.click()
        expect(page.get_by_test_id("chat-assistant")).to_have_count(1)
        print("戻した道具:", page.get_by_test_id("chat-assistant").get_by_test_id("tool-line").all_inner_texts())
        page.screenshot(path=str(EVIDENCE_DIR / "07_chat_llm_restored.png"))
        browser.close()

    # API でも、user と assistant の発言があることを見る
    sessions = json.load(urllib.request.urlopen(f"{API}/api/chat/sessions"))
    session = next(s for s in sessions if (s["title"] or "") == question[:30])
    detail = json.load(urllib.request.urlopen(f"{API}/api/chat/sessions/{session['id']}"))
    print("API の発言:", [(m["role"], m["content"][:30], m["tools"]) for m in detail["messages"]])


if __name__ == "__main__":
    main(sys.argv[1])
