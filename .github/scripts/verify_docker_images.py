#!/usr/bin/env python3
"""Compare local OCI candidates with published images before publishing Scout rebuilds."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scan_docker_images import IMAGE_REPO, PLATFORMS, image_variants, parse_env_file, resolve_digest
from scout_reports import Finding, scan


def compare(before: set[Finding], after: set[Finding]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    previous = {finding.identity for finding in before}
    current = {finding.identity for finding in after}
    return previous - current, current - previous


def verify(candidates: dict[str, str], reports_dir: Path, layouts: dict[str, str]) -> tuple[str, str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    version = parse_env_file(Path(".env"))["APACHE_VERSION"]
    rows = ["| Image | Platform | Removed findings | New findings | Remaining findings |",
            "| --- | --- | --- | --- | --- |"]
    evidence = []
    errors = []
    removed_count = 0
    previous_cves: set[str] = set()
    remaining_cves: set[str] = set()
    for variant, tag in image_variants(version):
        try:
            candidate = candidates[variant]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate):
                raise ValueError(f"Invalid candidate digest: {candidate}")
            layout = Path(layouts[variant]).resolve()
            index = json.loads((layout / "index.json").read_text())
            if [entry["digest"] for entry in index["manifests"]] != [candidate]:
                raise ValueError(f"Local OCI layout does not match candidate digest: {variant}")
            baseline = resolve_digest(f"{IMAGE_REPO}:{tag}")
            evidence.append({"variant": variant, "baseline": baseline, "candidate": candidate})
            for platform in PLATFORMS:
                arch = platform.split("/")[1]
                # Include unfixed findings: a change in fix metadata must not count
                # as remediation or hide a newly introduced high/critical issue.
                before = scan(f"{IMAGE_REPO}@{baseline}", platform,
                              reports_dir / f"{variant}-{arch}-before.sarif.json")
                after = scan(f"oci-dir://{layout}", platform,
                             reports_dir / f"{variant}-{arch}-after.sarif.json")
                removed, added = compare(before, after)
                previous_cves.update(f.cve for f in before)
                remaining_cves.update(f.cve for f in after)
                removed_count += len(removed)
                rows.append(f"| `{tag}` | {platform} | {len(removed)} | {len(added)} | {len(after)} |")
                if added:
                    errors.append(f"{tag} ({platform}) introduced findings: {sorted(added)}")
        except (OSError, ValueError, KeyError, RuntimeError, IndexError) as exc:
            errors.append(f"{tag}: {exc}")
        except subprocess.SubprocessError as exc:
            errors.append(f"{tag}: {exc}")

    if removed_count == 0:
        errors.append("The rebuild removed no high/critical findings; public tags were not promoted.")
    fixed = sorted(previous_cves - remaining_cves)
    remaining = sorted(remaining_cves)
    rows.extend(["", "CVEs absent from every candidate platform/variant: " + (", ".join(fixed) or "none"),
                 "", "Remaining high/critical CVEs: " + (", ".join(remaining) or "none")])
    if errors:
        rows.extend(["", "Publication blocked:", *[f"- {error}" for error in errors]])
    summary = "\n".join(rows) + "\n"
    (reports_dir / "summary.md").write_text(summary)
    (reports_dir / "digests.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if summary_file := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_file, "a") as out:
            out.write(summary)
    print(summary)
    if errors:
        raise RuntimeError("Candidate verification failed; see scout-verification/summary.md")
    return ",".join(fixed), ",".join(remaining)


def main() -> int:
    try:
        fixed, remaining = verify(json.loads(os.environ["CANDIDATE_DIGESTS"]), Path("scout-verification"),
                                  json.loads(os.environ["CANDIDATE_LAYOUTS"]))
        if output_file := os.environ.get("GITHUB_OUTPUT"):
            with open(output_file, "a") as out:
                out.write(f"verified_cves={fixed}\nremaining_cves={remaining}\n")
        return 0
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
