"""Wait until a released version is visible from a Python package index."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--index", choices=("pypi", "testpypi"), default="pypi")
    parser.add_argument("--attempts", type=int, default=12)
    args = parser.parse_args()
    host = "pypi.org" if args.index == "pypi" else "test.pypi.org"
    url = f"https://{host}/pypi/freelance-dev-suite/{args.version}/json"

    for attempt in range(1, args.attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310
                payload = json.load(response)
            if payload.get("info", {}).get("version") == args.version:
                print(f"Verified freelance-dev-suite {args.version} on {args.index}.")
                return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        if attempt < args.attempts:
            time.sleep(10)
    raise SystemExit(f"Package version {args.version} was not visible at {url}")


if __name__ == "__main__":
    main()
