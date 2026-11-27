"""Structured Scout reports shared by the availability and publication gates."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


@dataclass(frozen=True)
class Finding:
    cve: str
    package: str
    version: str
    fixed: str

    @property
    def identity(self) -> tuple[str, str]:
        # Versions change during upgrades; package identity must not.
        return self.cve, self.package


def read_findings(path: Path) -> set[Finding]:
    document = json.loads(path.read_text())
    if document.get("version") != "2.1.0" or not document.get("runs"):
        raise ValueError(f"Invalid Scout SARIF report: {path}")
    findings = set()
    for run in document["runs"]:
        rules = run["tool"]["driver"]["rules"]
        for result in run["results"]:
            rule = rules[result["ruleIndex"]]
            if rule["id"] != result["ruleId"]:
                raise ValueError(f"Mismatched SARIF rule: {path}")
            properties = rule["properties"]
            purls = properties["purls"]
            if not purls:
                raise ValueError(f"Missing package identity: {path}")
            for purl in purls:
                package, separator, version = purl.split("?", 1)[0].rpartition("@")
                if not separator or not package.startswith("pkg:"):
                    raise ValueError(f"Invalid package URL: {purl}")
                findings.add(Finding(rule["id"], unquote(package), unquote(version),
                                     properties.get("fixed_version", "")))
    return findings


def scan(reference: str, platform: str, report: Path, *, only_fixed: bool = False) -> set[Finding]:
    command = [
        "docker", "scout", "cves", f"registry://{reference}",
        "--platform", platform, "--only-severity", "high,critical",
        # Attached VEX statements can differ between otherwise identical images.
        # Compare package findings consistently, without author-based suppressions.
        "--vex-author", "^$",
        "--exit-code", "--format", "sarif", "--output", str(report),
    ]
    if only_fixed:
        command.append("--only-fixed")
    # Never consume a report left by an earlier attempt if this scan fails.
    report.unlink(missing_ok=True)
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    report.with_suffix(".log").write_text(result.stdout + result.stderr)
    if result.returncode not in (0, 2):
        raise RuntimeError(f"Scout failed for {reference} ({platform}): {result.stderr}")
    findings = read_findings(report)
    if (result.returncode == 2) != bool(findings):
        raise ValueError(f"Scout exit status disagrees with report: {report}")
    return findings
