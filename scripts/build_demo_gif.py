"""Convert the captured WebM walkthrough into an optimized GIF for the README."""
import subprocess
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
WEBM = next((ROOT / "demo_video_raw").glob("*.webm"))
OUT = ROOT / "docs" / "images" / "demo.gif"
PALETTE = ROOT / "demo_video_raw" / "palette.png"

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
# 720p-ish width, 8 fps keeps the GIF small enough for GitHub while staying readable
FILTER = "fps=8,scale=720:-2:flags=lanczos"


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    run([FFMPEG, "-y", "-i", str(WEBM), "-vf", FILTER + ",palettegen=stats_mode=diff", str(PALETTE)])
    run([FFMPEG, "-y", "-i", str(WEBM), "-i", str(PALETTE),
         "-lavfi", FILTER + "[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
         str(OUT)])
    mb = OUT.stat().st_size / 1024 / 1024
    print(f"{OUT} = {mb:.1f} MB")


if __name__ == "__main__":
    main()
