#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch(url: str) -> tuple[int, str]:
    request = Request(url, headers={"Accept": "application/json,text/html"})
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise SystemExit(f"Network error: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded live smoke test")
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    checks = [
        ("/", 200),
        ("/dashboard", 200),
        ("/api/billing/plans", 200),
    ]

    failures: list[str] = []
    for path, expected in checks:
        url = f"{args.base_url.rstrip('/')}{path}"
        status, body = fetch(url)
        print(f"{path}: {status}")
        if status != expected:
            snippet = body[:240].replace("\n", " ")
            failures.append(f"{path} -> expected {expected}, got {status}: {snippet}")

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nLive smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
