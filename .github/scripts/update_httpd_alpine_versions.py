#!/usr/bin/env python3
"""Update tracked Apache HTTPD Alpine base version from Docker official-images metadata."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/docker-library/official-images/refs/heads/master/library/httpd"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"

TAG_PATTERN = re.compile(r"^(?P<apache>\d+\.\d+\.\d+)-alpine(?P<alpine>\d+\.\d+)$")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def fetch_source(input_file: Path | None) -> str:
    if input_file is not None:
        return input_file.read_text()
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        return response.read().decode("utf-8")


def _version_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def parse_upstream_versions(source: str) -> dict[str, str]:
    """Return a mapping of alpine_version -> latest apache_version."""
    versions: dict[str, str] = {}
    for line in source.splitlines():
        if not line.startswith("Tags:"):
            continue
        for tag in re.split(r"[\s,]+", line[5:].strip()):
            m = TAG_PATTERN.match(tag)
            if m:
                apache = m.group("apache")
                alpine = m.group("alpine")
                if alpine not in versions or _version_key(apache) > _version_key(versions[alpine]):
                    versions[alpine] = apache
    return versions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path)
    args = parser.parse_args()

    current = parse_env_file(ENV_FILE)
    required = {"APACHE_VERSION", "APACHE_VERSION_MAJOR", "ALPINE_VERSION"}
    missing = sorted(required - current.keys())
    if missing:
        print(f"ERROR: {ENV_FILE}: missing keys: {', '.join(missing)}", file=sys.stderr)
        return 1

    current_apache = current["APACHE_VERSION"]
    current_alpine = current["ALPINE_VERSION"]

    source = fetch_source(args.input_file)
    upstream = parse_upstream_versions(source)

    latest = upstream.get(current_alpine)
    if not latest:
        print(f"No upstream httpd version found for Alpine {current_alpine}", file=sys.stderr)
        return 1

    if latest == current_apache:
        print(f"Already up to date: httpd {current_apache} on Alpine {current_alpine}")
        return 0

    if _version_key(latest) < _version_key(current_apache):
        print(f"Upstream {latest} is older than current {current_apache}, skipping")
        return 0

    print(f"Updating: httpd {current_apache} -> {latest} on Alpine {current_alpine}")
    content = ENV_FILE.read_text()
    content = re.sub(r"^APACHE_VERSION=.*$", f"APACHE_VERSION={latest}", content, flags=re.MULTILINE)
    ENV_FILE.write_text(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
