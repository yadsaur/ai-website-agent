#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_status(url: str) -> int:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            return response.status
    except HTTPError as exc:
        return exc.code
    except URLError as exc:
        raise SystemExit(f"Network error: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded deployment readiness check")
    parser.add_argument("--url", required=True, help="Endpoint to probe")
    parser.add_argument("--expect", type=int, default=200)
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay", type=int, default=15)
    args = parser.parse_args()

    for attempt in range(1, args.attempts + 1):
        status = fetch_status(args.url)
        print(f"Attempt {attempt}/{args.attempts}: {status}")
        if status == args.expect:
            print("Deployment check passed.")
            return 0
        if attempt < args.attempts:
            time.sleep(args.delay)

    print("Deployment check failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
