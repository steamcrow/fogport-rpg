"""Restore an approved binary from an ordered, continuous base64 chunk stream."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
from pathlib import Path


def restore(parts: list[Path], output: Path, expected_sha256: str) -> int:
    if not parts:
        raise SystemExit("No base64 image chunks found.")
    encoded = b"".join(part.read_bytes() for part in parts)
    if not encoded:
        raise SystemExit("Base64 image chunks are empty.")
    allowed = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    if any(byte not in allowed for byte in encoded):
        raise SystemExit("Base64 image chunks contain non-base64 data; the stored artifact may be truncated or corrupted.")
    try:
        image = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SystemExit("Base64 image chunks do not form one valid continuous stream; the stored artifact may be truncated or corrupted.") from exc
    actual_sha256 = hashlib.sha256(image).hexdigest()
    if actual_sha256 != expected_sha256.lower():
        raise SystemExit(f"Restored image checksum mismatch: expected {expected_sha256}, got {actual_sha256}.")
    output.write_bytes(image)
    print(f"Restored {len(parts)} base64 chunks ({len(image)} bytes); SHA-256 verified.")
    return len(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("parts", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    restore(sorted(args.parts), args.output, args.expected_sha256)


if __name__ == "__main__":
    main()
