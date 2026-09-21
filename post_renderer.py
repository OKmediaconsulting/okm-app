"""
Rendert einen Post (Foto + Logo + Headline + Subtext + CTA) direkt als PNG
via Playwright (HTML/CSS -> Screenshot). Ersetzt die Canva-Autofill-API,
die Canva Enterprise voraussetzt und auf diesem Konto nicht verfuegbar ist.
"""

from __future__ import annotations

import html
import os
import tempfile
import urllib.parse

from playwright.async_api import async_playwright


def _file_url(path: str) -> str:
    return "file://" + urllib.parse.quote(os.path.abspath(path))

WIDTH = 1080
HEIGHT = 1350

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; }}
  body {{ width: {width}px; height: {height}px; overflow: hidden; background: #fff; }}
  .photo {{ width: {width}px; height: 918px; object-fit: cover; display: block; }}
  .panel {{ width: {width}px; height: {panel_height}px; background: #fff; padding: 48px 56px; position: relative; }}
  .logo {{ position: absolute; top: -50px; left: 56px; width: 100px; height: 100px; border-radius: 50%;
           object-fit: cover; box-shadow: 0 4px 16px rgba(0,0,0,.18); border: 4px solid #fff; background: #fff; }}
  .headline {{ margin-top: 62px; font-size: 58px; font-weight: 800; color: #111; line-height: 1.15; }}
  .subtext {{ margin-top: 20px; font-size: 30px; color: #444; line-height: 1.4; max-width: 950px; }}
  .cta {{ display: inline-block; margin-top: 32px; padding: 16px 40px; background: #1a5c3a; color: #fff;
          font-size: 26px; font-weight: 700; border-radius: 50px; }}
</style>
</head>
<body>
  <img class="photo" src="{photo_path}">
  <div class="panel">
    {logo_html}
    <div class="headline">{headline}</div>
    <div class="subtext">{subtext}</div>
    <div class="cta">{cta}</div>
  </div>
</body>
</html>
"""


async def render_post(photo_path: str, logo_path: str | None, headline: str, subtext: str, cta: str, output_path: str) -> str:
    logo_html = f'<img class="logo" src="{_file_url(logo_path)}">' if logo_path else ""
    page_html = TEMPLATE.format(
        width=WIDTH,
        height=HEIGHT,
        panel_height=HEIGHT - 918,
        photo_path=_file_url(photo_path),
        logo_html=logo_html,
        headline=html.escape(headline),
        subtext=html.escape(subtext),
        cta=html.escape(cta),
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(page_html)
        html_path = f.name

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            await page.goto(f"file://{html_path}")
            await page.evaluate(
                """() => Promise.all(Array.from(document.images)
                    .filter(img => !img.complete)
                    .map(img => new Promise(resolve => { img.onload = img.onerror = resolve; })))"""
            )
            await page.screenshot(path=output_path)
            await browser.close()
    finally:
        os.remove(html_path)

    return output_path
