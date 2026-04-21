#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_json(url: str) -> tuple[int, dict]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body or "{}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            payload = {"raw": body}
        return exc.code, payload
    except URLError as exc:
        raise SystemExit(f"Network error: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Small local API smoke check")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    checks = [
        ("/api/health", False),
        ("/api/sites", False),
        ("/api/billing/plans", False),
    ]

    failures: list[str] = []
    for path, required in checks:
        url = f"{args.base_url.rstrip('/')}{path}"
        status, payload = fetch_json(url)
        ok = 200 <= status < 300 or (not required and status in {401, 403, 404})
        print(f"{path}: {status}")
        if not ok:
            failures.append(f"{path} -> {status} {payload}")

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nLocal smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
