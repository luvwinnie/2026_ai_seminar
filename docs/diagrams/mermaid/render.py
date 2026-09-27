"""このフォルダの .mmd を PNG にする(Mermaid 11 を Playwright の Chromium で描く)。
実行: example_app/.venv/bin/python docs/diagrams/mermaid/render.py → docs/images/mermaid_*.png
"""
import html
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "images"
ok = True
with sync_playwright() as p:
    br = p.chromium.launch()
    for f in sorted(HERE.glob("*.mmd")):
        page = br.new_page(viewport={"width": 1800, "height": 1200}, device_scale_factor=2)
        page.set_content('<html><body style="margin:0;background:#fff">'
                         f'<pre class="mermaid">{html.escape(f.read_text(encoding="utf-8"))}</pre>'
                         '<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>'
                         '<script>mermaid.initialize({startOnLoad:true, theme:"default",'
                         ' fontFamily:"Hiragino Sans, Meiryo, sans-serif", flowchart:{htmlLabels:true}});</script>'
                         '</body></html>')
        try:
            page.wait_for_selector("pre.mermaid svg", timeout=20000)
            err = page.locator("text=Syntax error").count()
            out = OUT / f"mermaid_{f.stem}.png"
            page.locator("pre.mermaid svg").screenshot(path=str(out))
            print(out.name, "OK" if not err else "SYNTAX ERROR")
            ok = ok and not err
        except Exception as e:  # noqa: BLE001
            print(f.name, "FAILED", str(e)[:200])
            ok = False
        page.close()
    br.close()
sys.exit(0 if ok else 1)
