"""Record a real demo video with Playwright's built-in video recorder.

Drives the system Chrome through the full demo flow and saves a WebM video,
which is then transcoded to MP4 via the imageio-ffmpeg binary.
"""
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "demo_video_raw"
FINAL = ROOT / "roadwatch_demo_recording.mp4"
SOURCE_NAME = "演示视频路段"


def main():
    if VIDEO_DIR.exists():
        shutil.rmtree(VIDEO_DIR)
    VIDEO_DIR.mkdir(parents=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context(
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1600, "height": 900},
            viewport={"width": 1600, "height": 900},
        )
        page = context.new_page()
        page.goto(BASE, wait_until="load")
        page.wait_for_function('document.getElementById("stat-sources").textContent !== "—"',
                               timeout=15000)
        page.wait_for_selector(".leaflet-tile", timeout=15000)
        page.wait_for_timeout(3000)  # 1. overview + map

        # 2. create source
        page.click('button.nav[data-view="sources"]')
        page.wait_for_timeout(1200)
        page.fill('#source-form input[name="name"]', SOURCE_NAME)
        page.fill('#source-form input[name="latitude"]', "31.2304")
        page.fill('#source-form input[name="longitude"]', "121.4737")
        page.fill('#source-form input[name="baseline_speed"]', "60")
        page.click('#source-form button:has-text("创建监测点")')
        page.wait_for_timeout(2500)

        # 3. submit anomalous metric (form is on the sources view)
        page.select_option("#ingest-source", label=SOURCE_NAME)
        page.fill('#metric-form input[name="speed"]', "12")
        page.fill('#metric-form input[name="congestion"]', "0.9")
        page.fill('#metric-form input[name="volume"]', "50")
        page.click('#metric-form button:has-text("提交当前指标")')
        page.wait_for_timeout(3000)

        # 4. back to overview, show event queue
        page.click('button.nav[data-view="monitor"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(2000)
        page.query_selector("#events-body").scroll_into_view_if_needed()
        page.wait_for_timeout(3000)

        # 5. event handling: open -> note -> acknowledge
        page.click('#events-body [data-event] >> nth=0')
        page.wait_for_selector("#event-dialog[open], #event-dialog:not([hidden])", timeout=5000)
        page.wait_for_timeout(1500)
        page.fill("#action-note", "已通知路政现场处置")
        page.wait_for_timeout(1000)
        page.click('#event-buttons [data-action="acknowledged"]')
        page.wait_for_timeout(3000)
        page.click("#event-dialog .close")
        page.wait_for_timeout(1500)

        # 6. image detection view
        page.click('button.nav[data-view="inference"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(3500)

        # 7. video detection view
        page.click('button.nav[data-view="video"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(3500)

        # 8. back to overview
        page.click('button.nav[data-view="monitor"]')
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(3000)

        page.close()
        context.close()
        browser.close()

    webms = list(VIDEO_DIR.glob("*.webm"))
    if not webms:
        raise RuntimeError("No webm produced by Playwright")
    webm = webms[0]
    print(f"Recorded webm: {webm} ({webm.stat().st_size/1024/1024:.1f} MB)")

    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if FINAL.exists():
        FINAL.unlink()
    cmd = [ffmpeg, "-y", "-i", str(webm), "-c:v", "mpeg4", "-q:v", "5",
           "-vf", "fps=15", str(FINAL)]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"Final mp4: {FINAL} ({FINAL.stat().st_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
