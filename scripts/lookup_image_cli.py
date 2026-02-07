from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from urllib import request


def _make_multipart(field_name: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = f"----photolookup-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    lines = [
        f"--{boundary}",
        f'Content-Disposition: form-data; name="{field_name}"; filename="{os.path.basename(filename)}"',
        f"Content-Type: {content_type}",
        "",
    ]
    body = "\r\n".join(lines).encode("utf-8") + b"\r\n" + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return body, boundary


def _post_multipart(url: str, field_name: str, filename: str) -> dict:
    with open(filename, "rb") as f:
        data = f.read()
    body, boundary = _make_multipart(field_name, filename, data)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Lookup image against PhotoLookup server")
    parser.add_argument("server", help="Server host:port, e.g. 127.0.0.1:8000")
    parser.add_argument("image", help="Path to image file")
    args = parser.parse_args()

    base_url = args.server
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        base_url = f"http://{base_url}"

    try:
        bbox = _post_multipart(f"{base_url}/api/bbox", "file", args.image)
        lookup = _post_multipart(f"{base_url}/api/lookup", "file", args.image)
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    print("/bbox:")
    print(json.dumps(bbox, indent=2, sort_keys=True))
    print("\n/lookup:")
    print(json.dumps(lookup, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
