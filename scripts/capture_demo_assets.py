"""Capture demo assets for the README: PNG screenshots + a WebM walkthrough.

Run while the API/frontend is up on http://127.0.0.1:8010. Requires:
    pip install playwright imageio-ffmpeg && playwright install chrome
The WebM is later transcoded to docs/images/demo.gif by build_demo_gif.py.
"""
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "images"
RAW = ROOT / "demo_video_raw"
SOURCE_NAME = "演示截图路段"


def shot(page, name):
    target = IMG / name
    page.screenshot(path=str(target))
    print("saved", target.name)


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    if RAW.exists():
        shutil.rmtree(RAW)
    RAW.mkdir(parents=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context(
            record_video_dir=str(RAW),
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1600, "height": 900},
        )
        page = context.new_page()

        # 1. Overview + real map
        page.goto(BASE, wait_until="load")
        page.wait_for_function('document.getElementById("stat-sources").textContent !== "-"', timeout=15000)
        page.wait_for_selector(".leaflet-tile", timeout=15000)
        page.wait_for_timeout(3000)
        shot(page, "shot-overview.png")

        # 2. Sources view + create a monitoring point
        page.click('button.nav[data-view="sources"]')
        page.wait_for_timeout(1500)
        shot(page, "shot-sources.png")
        page.fill('#source-form input[name="name"]', SOURCE_NAME)
        page.fill('#source-form input[name="latitude"]', "30.2741")
        page.fill('#source-form input[name="longitude"]', "120.1551")
        page.fill('#source-form input[name="baseline_speed"]', "60")
        page.click('#source-form button:has-text("创建监测点")')
        page.wait_for_timeout(2500)

        # 3. Submit anomalous metric
        page.select_option("#ingest-source", label=SOURCE_NAME)
        page.fill('#metric-form input[name="speed"]', "11")
        page.fill('#metric-form input[name="congestion"]', "0.92")
        page.fill('#metric-form input[name="volume"]', "55")
        page.click('#metric-form button:has-text("提交当前指标")')
        page.wait_for_timeout(3000)

        # 4. Overview: event queue with the new event
        page.click('button.nav[data-view="monitor"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(1500)
        page.query_selector("#events-body").scroll_into_view_if_needed()
        page.wait_for_timeout(2000)
        shot(page, "shot-events.png")

        # 5. Event dialog — wait for async LLM analysis to land
        page.click('#events-body [data-event] >> nth=0')
        page.wait_for_selector("#event-dialog[open], #event-dialog:not([hidden])", timeout=5000)
        page.wait_for_timeout(18000)
        shot(page, "shot-event-ai.png")
        page.click("#event-dialog .close")
        page.wait_for_timeout(800)

        # 6. Image detection
        page.click('button.nav[data-view="inference"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(2500)
        shot(page, "shot-inference.png")

        # 7. Video detection
        page.click('button.nav[data-view="video"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(2500)
        shot(page, "shot-video.png")

        # 8. Datasets / annotation
        page.click('button.nav[data-view="datasets"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(2500)
        shot(page, "shot-datasets.png")

        # Back to overview for the closing frames
        page.click('button.nav[data-view="monitor"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(2000)

        page.close()
        context.close()
        browser.close()

    webm = next(RAW.glob("*.webm"))
    print("webm:", webm)


if __name__ == "__main__":
    main()
