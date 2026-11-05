"""チャットの画面（05_UI設計書.md S3、07_試験・運用仕様書.md AC-v20-01・04・08、AC-v21-02・03）。

LLM は呼ばない。backend は OpenCode の代わり（app/backend/tests/fake_opencode.py）につながっていて、
質問の語で場面が決まる（「空応答」→ 空の応答、「402」→ モデルのエラー、それ以外 → KZ25-0043 の回答）。
"""

from playwright.sync_api import Page, expect

EMPTY = "OpenCodeが空応答を返しました(モデル未応答)。もう一度お試しください"
NO_BACKEND = "AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)"


def ask(page: Page, question: str) -> None:
    box = page.get_by_test_id("chat-input")
    box.fill(question)
    box.press("Enter")


def new_chat(page: Page) -> None:
    page.goto("/chat")
    page.get_by_role("button", name="新しいチャット").click()


def test_AC_v20_01_stream_tools_and_link(page: Page):
    new_chat(page)
    expect(page.get_by_test_id("chat-empty")).to_contain_text("質問を入力してください")
    ask(page, "KZ25-0043 の内容を教えて")
    # 回答が届いているあいだは入力を止める
    expect(page.get_by_test_id("chat-input")).to_be_disabled()
    answer = page.get_by_test_id("chat-assistant").last
    # 道具の名前は defect-reports_ を外して出し、状態と題を添える
    expect(answer.get_by_test_id("tool-line")).to_have_text("get_defect_report完了 · KZ25-0043")
    expect(answer).to_contain_text("a61nx")
    expect(answer).to_contain_text("翠峰重工業")
    expect(page.get_by_test_id("chat-input")).to_be_enabled()
    expect(answer.get_by_test_id("thinking")).to_contain_text("考えています")
    # 本文の報告書番号は詳細へのリンク（太字の KZ25-0043 と [KZ25-0043] の2つ）
    links = answer.get_by_role("link", name="KZ25-0043")
    expect(links).to_have_count(2)
    links.first.click()
    expect(page).to_have_url("http://localhost:5220/reports/KZ25-0043")
    expect(page.get_by_test_id("field-使用機械")).to_contain_text("a61nx")


def test_AC_v20_01_example_question(page: Page):
    new_chat(page)
    page.get_by_test_id("chat-empty").get_by_role("button", name="KZ25-0043 の内容を教えて").click()
    expect(page.get_by_test_id("chat-user").last).to_have_text("あなたKZ25-0043 の内容を教えて")
    expect(page.get_by_test_id("chat-assistant").last).to_contain_text("a61nx")


def test_AC_v20_01_shift_enter_is_newline(page: Page):
    new_chat(page)
    box = page.get_by_test_id("chat-input")
    box.fill("1行目")
    box.press("Shift+Enter")
    box.type("2行目")
    expect(box).to_have_value("1行目\n2行目")
    expect(page.get_by_test_id("chat-user")).to_have_count(0)


def test_AC_v20_04_reload_restores_session(page: Page):
    new_chat(page)
    ask(page, "再読込の試験：KZ25-0043 は？")
    expect(page.get_by_test_id("chat-assistant").last).to_contain_text("a61nx")
    # 回答が終わる（done で保存される）のを待ってから再読込する
    expect(page.get_by_test_id("chat-input")).to_be_enabled()
    page.reload()
    item = page.get_by_test_id("session-item").filter(has_text="再読込の試験：KZ25-0043 は？")
    expect(item).to_contain_text("2件")
    item.click()
    # 発言と回答、保存した道具の記録と思考も戻る
    expect(page.get_by_test_id("chat-user")).to_have_text(["あなた再読込の試験：KZ25-0043 は？"])
    restored = page.get_by_test_id("chat-assistant")
    expect(restored).to_have_count(1)
    expect(restored.get_by_test_id("tool-line")).to_have_text("get_defect_report完了 · KZ25-0043")
    expect(restored.get_by_test_id("thinking")).to_be_visible()
    expect(restored).to_contain_text("翠峰重工業")


def test_AC_v20_04_delete_session(page: Page):
    new_chat(page)
    ask(page, "削除の試験")
    expect(page.get_by_test_id("chat-assistant").last).to_contain_text("a61nx")
    item = page.get_by_test_id("session-item").filter(has_text="削除の試験")
    item.hover()
    item.get_by_role("button", name="削除").click()
    page.get_by_role("dialog").get_by_role("button", name="削除").click()
    expect(item).to_have_count(0)
    expect(page.get_by_test_id("chat-empty")).to_be_visible()


def test_AC_v21_02_empty_response_is_shown_as_error(page: Page):
    new_chat(page)
    ask(page, "空応答の試験")
    expect(page.get_by_test_id("chat-error")).to_have_text(EMPTY)
    # 空の回答を成功として出さない
    expect(page.get_by_test_id("chat-assistant")).to_have_count(0)


def test_AC_v21_03_model_error_is_shown_as_error(page: Page):
    new_chat(page)
    ask(page, "402 の試験")
    expect(page.get_by_test_id("chat-error")).to_contain_text("OpenCode/モデルエラー: Insufficient credits（HTTP 402）")
    expect(page.get_by_test_id("chat-assistant")).to_have_count(0)


def test_AC_v20_08_no_backend(page: Page, backend):
    # OPENCODE_URL を外して backend を起動し直す
    backend.stop()
    saved = backend.env.pop("OPENCODE_URL")
    try:
        backend.start()
        new_chat(page)
        expect(page.get_by_test_id("health-badge")).to_have_text("110件 · AI 未設定")
        ask(page, "KZ25-0043 の内容を教えて")
        expect(page.get_by_test_id("chat-error")).to_have_text(NO_BACKEND)
        # 一覧はそのまま動く
        page.goto("/reports")
        expect(page.get_by_test_id("pagination")).to_contain_text("全110件")
    finally:
        backend.stop()
        backend.env["OPENCODE_URL"] = saved
        backend.start()
