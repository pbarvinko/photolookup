from __future__ import annotations

import argparse
import json
import sys
import time
from urllib import request
from urllib.error import HTTPError


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or update index on PhotoLookup server")
    parser.add_argument("server", help="Server host:port, e.g. 127.0.0.1:8000")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild index from scratch (default: incremental update)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )
    args = parser.parse_args()

    base_url = args.server
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        base_url = f"http://{base_url}"

    # Start build
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
            start_payload = json.loads(resp.read().decode("utf-8"))
            print(f"Build started: {start_payload['operation']}")
            print(f"Status: {start_payload['status']}")
    except HTTPError as exc:
        if exc.code == 409:
            print("Error: Build already in progress", file=sys.stderr)
        else:
            print(f"Request failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    # Poll for completion
    status_url = f"{base_url}/api/index/status"
    last_progress = 0

    while True:
        time.sleep(args.poll_interval)

        try:
            with request.urlopen(status_url) as resp:
                status_payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"Status request failed: {exc}", file=sys.stderr)
            return 1

        build_status = status_payload.get("build_status")
        if not build_status:
            # No build status means build completed and was cleared
            print("\nBuild completed")
            print(json.dumps(status_payload, indent=2, sort_keys=True))
            return 0

        status = build_status["status"]
        progress = build_status["progress"]
        total = build_status.get("total")

        # Print progress update
        if progress != last_progress:
            if total:
                print(f"Progress: {progress}/{total} files processed")
            else:
                print(f"Progress: {progress} files processed")
            last_progress = progress

        if status == "completed":
            print("\nBuild completed successfully")
            print(json.dumps(status_payload, indent=2, sort_keys=True))
            return 0

        if status == "failed":
            error = build_status.get("error", "Unknown error")
            print(f"\nBuild failed: {error}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
