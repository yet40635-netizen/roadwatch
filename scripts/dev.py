import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main():
    parser = argparse.ArgumentParser(description="Start API, detector and worker locally")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    load_env()
    processes = []

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        for module, port in [("backend.main:app", args.port), ("inference.main:app", 8011)]:
            processes.append(subprocess.Popen([
                sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port),
            ], cwd=ROOT))
        with httpx.Client(timeout=2, trust_env=False) as client:
            for _ in range(60):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("A service exited; check startup logs")
                try:
                    if all(client.get(f"http://127.0.0.1:{p}/health").status_code == 200
                           for p in [args.port, 8011]):
                        break
                except httpx.RequestError:
                    pass
                time.sleep(.5)
            else:
                raise RuntimeError("Services did not become healthy")
            if not args.no_seed and os.getenv("DEMO_ENABLED", "true").lower() == "true":
                client.post(
                    f"http://127.0.0.1:{args.port}/api/v1/demo/seed",
                    headers={"X-API-Key": os.getenv("API_KEY", "")},
                ).raise_for_status()
        processes.append(subprocess.Popen([sys.executable, "-m", "backend.worker"], cwd=ROOT))
        print(f"RoadWatch ready: http://127.0.0.1:{args.port}", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        raise RuntimeError("A service exited; stopping the remaining services")
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
