#!/usr/bin/env python3
"""Scan published Apache HTTPD images for fixable CVEs using Docker Scout."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from scout_reports import Finding, scan

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


def available_fixes(reference: str, platform: str, findings: set[Finding], log: Path) -> set[str]:
    """Try package upgrades in an isolated, disposable copy of the published image.

    Scout's fixed_version is advisory metadata, not proof that the configured
    Alpine repositories have published that revision for this architecture.
    Non-APK fixes need an upstream image/version update, handled separately.
    """
    packages: dict[str, set[str]] = {}
    for finding in findings:
        if finding.package.startswith("pkg:apk/alpine/"):
            package = finding.package.rsplit("/", 1)[1]
            if not re.fullmatch(r"[a-zA-Z0-9+_.-]+", package):
                raise ValueError(f"Invalid APK package: {package}")
            if not re.fullmatch(r"[a-zA-Z0-9+_.-]+", finding.fixed):
                raise ValueError(f"Invalid APK fixed version: {finding.fixed!r}")
            packages.setdefault(package, set()).add(finding.fixed)
    if not packages:
        log.write_text("No APK fixes to probe; upstream version update required.\n")
        return set()

    script = r'''
set -eu
apk update >&2
apk upgrade >&2
apk info -v > /tmp/scout-installed-packages
while [ "$#" -gt 0 ]; do
    package=$1
    fixed=$2
    shift 2
    installed=$(awk -v prefix="$package-" 'index($0, prefix) == 1 {version = substr($0, length(prefix) + 1); if (version ~ /^[0-9]/) print version}' /tmp/scout-installed-packages)
    [ -n "$installed" ] || exit 1
    printf '%s installed=%s required=%s\n' "$package" "$installed" "$fixed" >&2
    comparison=$(apk version -t "$installed" "$fixed")
    case "$comparison" in
        '='|'>') printf '%s\t%s\n' "$package" "$fixed" ;;
        '<') : ;;
        *) exit 1 ;;
    esac
done
'''
    arguments = [value for package, versions in sorted(packages.items())
                 for version in sorted(versions) for value in (package, version)]
    result = subprocess.run(
        ["docker", "run", "--rm", "--pull=always", "--platform", platform,
         "--user", "0", "--entrypoint", "sh", reference, "-c", script,
         "scout-availability", *arguments],
        capture_output=True, text=True, timeout=600,
    )
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"APK availability check failed: {reference} ({platform}); see {log}")
    available = {tuple(line.split("\t")) for line in result.stdout.splitlines()}
    return {finding.cve for finding in findings
            if finding.package.startswith("pkg:apk/alpine/")
            and (finding.package.rsplit("/", 1)[1], finding.fixed) in available}


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
            report = reports_dir / f"{variant_name}-{arch}.sarif.json"
            try:
                findings = scan(f"{reference}@{digest}", platform, report, only_fixed=True)
                if not findings:
                    status = "No fixable CVEs"
                else:
                    available = available_fixes(
                        f"{reference}@{digest}", platform, findings,
                        reports_dir / f"{variant_name}-{arch}-availability.log",
                    )
                    if available:
                        status = "Package fixes available; verified rebuild requested"
                        fixable = True
                        all_cves.update(available)
                    else:
                        status = "Fixes reported but unavailable from configured repositories; waiting for upstream"
            except (subprocess.SubprocessError, RuntimeError, ValueError, KeyError, OSError) as exc:
                status = "Scan or package availability check failed"
                errors.append(f"{reference} ({platform}): {exc}")
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
