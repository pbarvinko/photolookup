from __future__ import annotations

import argparse
import json
import sys
from urllib import request


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or update index on PhotoLookup server")
    parser.add_argument("server", help="Server host:port, e.g. 127.0.0.1:8000")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild index from scratch (default: incremental update)",
    )
    args = parser.parse_args()

    base_url = args.server
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        base_url = f"http://{base_url}"

    # Add rebuild parameter to URL if specified
    url = f"{base_url}/api/index"
    if args.rebuild:
        url += "?rebuild=true"

    req = request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
