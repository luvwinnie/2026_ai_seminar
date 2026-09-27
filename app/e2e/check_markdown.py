# -*- coding: utf-8 -*-
"""Markdownレンダリング検証 — 回答の太字/リストがHTMLとして描画され、生の ** が残らないこと。"""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5373"
CHAT_INPUT = 'textarea[placeholder*="質問を入力"]'

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1680, "height": 950})
    page.goto(BASE + "/dashboard")
    page.wait_for_selector(CHAT_INPUT)
    box = page.locator(CHAT_INPUT).first
    box.fill("GENOS M560-Vで多い不良を、太字と箇条書きを使ったMarkdownで簡潔にまとめて")
    box.press("Enter")
    page.wait_for_function("() => /KZ25-\\d{4}/.test(document.body.innerText)", timeout=240000)
    page.wait_for_function("() => !document.querySelector('.MuiCircularProgress-root')", timeout=240000)
    page.wait_for_timeout(1000)

    strongs = page.locator("div.MuiPaper-root strong").count()
    lis = page.locator("div.MuiPaper-root li").count()
    body = page.inner_text("body")
    raw_bold = "**" in body
    links = page.locator('a[href^="/reports/KZ25-"]').count()
    page.screenshot(path="e2e/shots/40_markdown_render.png", full_page=True)
    browser.close()

print(f"strong={strongs} li={lis} DRリンク={links} 生の'**'残存={raw_bold}")
assert strongs > 0 and not raw_bold, "Markdownが描画されていない"
print("MARKDOWN RENDER OK")
