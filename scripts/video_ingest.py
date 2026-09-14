import argparse
import os
import time
from pathlib import Path

import httpx


def sample_frames(path, interval):
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("Cannot open video")
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            raise ValueError("Video has no valid frame rate")
        stride = max(1, round(fps * interval))
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % stride == 0:
                encoded, image = cv2.imencode(".jpg", frame)
                if not encoded:
                    raise ValueError("Cannot encode video frame")
                yield index / fps, image.tobytes()
            index += 1
    finally:
        capture.release()


def main():
    parser = argparse.ArgumentParser(description="Sample a local video into asynchronous image jobs")
    parser.add_argument("video", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8010")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--max-frames", type=int, default=120)
    args = parser.parse_args()
    if not args.video.is_file() or args.interval <= 0 or args.max_frames < 1:
        parser.error("Provide a local video, a positive interval and a positive frame limit")
    headers = {"X-API-Key": os.getenv("API_KEY", "")}
    with httpx.Client(base_url=args.api, headers=headers, timeout=30, trust_env=False) as client:
        for count, (offset, image) in enumerate(sample_frames(args.video, args.interval)):
            if count >= args.max_frames:
                break
            response = client.post("/api/v1/inference/jobs", data={"source_id": args.source_id},
                                   files={"file": (f"frame-{offset:.2f}.jpg", image, "image/jpeg")})
            response.raise_for_status()
            job_id = response.json()["id"]
            deadline = time.monotonic() + 180
            while True:
                response = client.get(f"/api/v1/inference/jobs/{job_id}")
                response.raise_for_status()
                job = response.json()
                if job["status"] in {"succeeded", "failed"}:
                    print(f'{offset:.2f}s {job_id} {job["status"]}', flush=True)
                    if job["status"] == "failed":
                        raise RuntimeError(job["error"])
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Job {job_id} did not finish within 180 seconds")
                time.sleep(1)


if __name__ == "__main__":
    main()
