import argparse
import concurrent.futures
import json
import os
import statistics
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description="Measure API overview latency without mutating data")
    parser.add_argument("--api", default="http://127.0.0.1:8010")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    if args.requests < 1 or not 1 <= args.concurrency <= 100:
        parser.error("requests must be positive; concurrency must be 1..100")
    with httpx.Client(base_url=args.api, headers={"X-API-Key": os.getenv("API_KEY", "")},
                      timeout=15, trust_env=False) as client:
        def request(_):
            start = time.perf_counter()
            try:
                response = client.get("/api/v1/overview")
                return (time.perf_counter() - start) * 1000, response.status_code == 200
            except httpx.HTTPError:
                return (time.perf_counter() - start) * 1000, False

        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            results = list(pool.map(request, range(args.requests)))
        duration = time.perf_counter() - started
    times = sorted(result[0] for result in results)
    report = {"requests": len(results), "concurrency": args.concurrency,
              "errors": sum(not result[1] for result in results),
              "rps": round(len(results) / duration, 2), "p50_ms": round(statistics.median(times), 2),
              "p95_ms": round(times[max(0, int(len(times) * .95 + .999) - 1)], 2)}
    print(json.dumps(report, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
