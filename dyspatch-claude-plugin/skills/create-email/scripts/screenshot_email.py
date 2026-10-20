#!/usr/bin/env python3
"""Render a Dyspatch email to a PNG/JPG preview with an inbox-style header (sender, subject, preheader).

Usage:
    python screenshot_email.py email.html preview.png \
        --subject "Spring into savings" --preheader "72 hours only" \
        --from-name "Brand Co" --from-email "news@brandco.com" [--width 700] [--mobile]

email.html is the `html` field from Dyspatch `render_template_version` (a raw saved MCP JSON response also works).
Prints a JSON line: {"out": ..., "images_total": N, "images_broken": M, "broken_hosts": [...]}.
If images_broken > 0, the environment can't reach those hosts (usually Dyspatch's image CDN), so tell the user
the preview is missing images and how to fix it (see SKILL.md).

Requires Playwright + Chromium (`pip install playwright && playwright install chromium`) and Pillow.
"""
import argparse
import html as htmllib
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


def load_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        try:
            stack = [json.loads(text)]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    if isinstance(cur.get("html"), str) and "<" in cur["html"]:
                        return cur["html"]
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
        except json.JSONDecodeError:
            pass
    return text


def header_html(a, width: int) -> str:
    e = lambda s: htmllib.escape(s or "")
    sender = e(a.from_name) or "<span style='color:#b00'>Sender not set</span>"
    addr = f"&lt;{e(a.from_email)}&gt;" if a.from_email else ""
    subj = e(a.subject) or "<span style='color:#b00'>No subject</span>"
    pre = e(a.preheader) or "<span style='color:#b00'>No preheader</span>"
    initial = (a.from_name or "?")[:1].upper()
    return f"""<html><body style="margin:0;background:#fff;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="width:{width}px;box-sizing:border-box;padding:16px 20px;border-bottom:1px solid #e3e3e3">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="width:40px;height:40px;border-radius:50%;background:#5b6cff;color:#fff;font-weight:600;
                display:flex;align-items:center;justify-content:center;font-size:18px;flex:none">{e(initial)}</div>
    <div style="min-width:0">
      <div style="font-size:14px;color:#222"><b>{sender}</b> <span style="color:#666">{addr}</span></div>
      <div style="font-size:13px;color:#888">to {e(a.to)}</div>
    </div>
  </div>
  <div style="font-size:19px;font-weight:600;color:#111;margin:14px 0 4px">{subj}</div>
  <div style="font-size:13px;color:#666"><span style="text-transform:uppercase;font-size:11px;letter-spacing:.5px;
       color:#999;margin-right:6px">Preheader</span>{pre}</div>
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("out")
    ap.add_argument("--subject", default="")
    ap.add_argument("--preheader", default="")
    ap.add_argument("--from-name", default="")
    ap.add_argument("--from-email", default="")
    ap.add_argument("--to", default="me")
    ap.add_argument("--width", type=int, default=700)
    ap.add_argument("--mobile", action="store_true", help="375px viewport")
    ap.add_argument("--no-header", action="store_true")
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image
    except ImportError as exc:
        print(f"missing dependency: {exc}. pip install playwright pillow", file=sys.stderr)
        return 2

    width = 375 if a.mobile else a.width
    tmp = Path(tempfile.mkdtemp())
    body_png, head_png = tmp / "body.png", tmp / "head.png"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 200}, device_scale_factor=2)
        page.set_content(load_html(Path(a.html)), wait_until="networkidle", timeout=45000)
        imgs = page.evaluate(
            "Array.from(document.images).map(i => ({src: i.currentSrc || i.src, ok: i.complete && i.naturalWidth > 0}))"
        )
        page.screenshot(path=str(body_png), full_page=True)
        if not a.no_header:
            hp = browser.new_page(viewport={"width": width, "height": 200}, device_scale_factor=2)
            hp.set_content(header_html(a, width))
            hp.locator("div").first.screenshot(path=str(head_png))
        browser.close()

    body = Image.open(body_png).convert("RGB")
    if a.no_header:
        final = body
    else:
        head = Image.open(head_png).convert("RGB")
        final = Image.new("RGB", (max(head.width, body.width), head.height + body.height), "white")
        final.paste(head, (0, 0))
        final.paste(body, (0, head.height))
    out = Path(a.out)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        final.save(out, "JPEG", quality=85)
    else:
        final.save(out)

    broken = [i["src"] for i in imgs if not i["ok"] and i["src"] and not i["src"].startswith("data:")]
    print(json.dumps({
        "out": str(out),
        "images_total": len(imgs),
        "images_broken": len(broken),
        "broken_hosts": sorted({urlparse(s).hostname or "" for s in broken}),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
