#!/usr/bin/env python3
"""Scan published Apache HTTPD images for fixable CVEs using Docker Scout."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
IMAGE_REPO = "mxmd/httpd"
PLATFORMS = ("linux/amd64", "linux/arm64")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def image_variants(apache_version: str) -> list[tuple[str, str]]:
    """Return (name, tag) pairs for each image variant."""
    return [
        ("base", apache_version),
        ("hardened", f"{apache_version}-hardened"),
        ("hardened-nonroot", f"{apache_version}-hardened-nonroot"),
    ]


def resolve_digest(reference: str) -> str:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", reference, "--format", "{{.Manifest.Digest}}"],
        capture_output=True, text=True, check=True, timeout=120,
    )
    digest = result.stdout.strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(f"Invalid manifest digest: {digest!r}")
    return digest


def extract_cve_ids(report_path: Path) -> list[str]:
    if not report_path.exists():
        return []
    return sorted(set(re.findall(r"CVE-\d{4}-\d+", report_path.read_text())))


def scan_images(reports_dir: Path) -> tuple[bool, list[str], str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    env = parse_env_file(REPO_ROOT / ".env")
    apache_version = env["APACHE_VERSION"]

    has_fixes = False
    all_cves: set[str] = set()
    errors: list[str] = []
    summary = ["| Image | Platform | Result |", "| --- | --- | --- |"]

    for variant_name, tag in image_variants(apache_version):
        reference = f"{IMAGE_REPO}:{tag}"
        try:
            digest = resolve_digest(reference)
        except (subprocess.SubprocessError, ValueError) as exc:
            detail = getattr(exc, "stderr", None) or str(exc)
            (reports_dir / f"{variant_name}-resolve.log").write_text(str(detail))
            errors.append(f"Could not resolve {reference}")
            summary.append(f"| `{reference}` | both | Registry lookup failed |")
            continue

        fixable = False
        for platform in PLATFORMS:
            arch = platform.split("/")[1]
            report = reports_dir / f"{variant_name}-{arch}.md"
            command = [
                "docker", "scout", "cves", f"registry://{reference}@{digest}",
                "--platform", platform, "--only-fixed", "--ignore-base",
                "--only-severity", "high,critical", "--exit-code",
                "--format", "markdown", "--output", str(report),
            ]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=600)
                report.with_suffix(".log").write_text(result.stdout + result.stderr)
                if result.returncode == 0:
                    status = "No fixable CVEs"
                elif result.returncode == 2:
                    status = "Fixes available; rebuild requested"
                    fixable = True
                    all_cves.update(extract_cve_ids(report))
                else:
                    status = f"Scan failed (exit {result.returncode})"
                    errors.append(f"{reference} ({platform}): {status}")
            except subprocess.TimeoutExpired:
                status = "Scan timed out"
                errors.append(f"{reference} ({platform}): timed out")
            summary.append(f"| `{reference}@{digest}` | {platform} | {status} |")
            print(f"{reference} ({platform}): {status}", flush=True)
        if fixable:
            has_fixes = True

    if errors:
        summary.extend(["", "Scans were incomplete. Automatic rebuilds are skipped for this run."])

    summary_text = "\n".join(summary) + "\n"
    (reports_dir / "summary.md").write_text(summary_text)
    if summary_file := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_file, "a") as out:
            out.write(summary_text)

    cve_list = ",".join(sorted(all_cves)) if all_cves else ""
    return has_fixes and not errors, errors, cve_list


def main() -> int:
    reports_dir = Path("scout-reports")
    has_fixes, errors, cve_list = scan_images(reports_dir)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    if output_file := os.environ.get("GITHUB_OUTPUT"):
        with open(output_file, "a") as out:
            out.write(f"has_fixes={str(has_fixes).lower()}\n")
            out.write(f"cve_list={cve_list}\n")
    print(f"Has fixes: {has_fixes}")
    if cve_list:
        print(f"CVEs to patch: {cve_list}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
