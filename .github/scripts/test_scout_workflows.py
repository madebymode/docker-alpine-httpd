"""Regression coverage for package availability and publication decisions.

Run with: python3 -m unittest discover -s .github/scripts -p 'test_*.py'
"""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scan_docker_images as scanner
import scout_reports
import verify_docker_images as verification
from scout_reports import Finding


SSL = Finding("CVE-2026-95691", "pkg:apk/alpine/libssl3", "3.5.9-r0", "3.5.9-r1")
MUSL = Finding("CVE-2026-107891", "pkg:apk/alpine/musl", "1.2.6-r3", "1.2.6-r6")
XML = Finding("CVE-2026-86140", "pkg:apk/alpine/libxml2", "2.13.9-r2", "not fixed")
DIGEST = "sha256:" + "a" * 64
CANDIDATES = {name: DIGEST for name in ("base", "hardened", "hardened-nonroot")}


class ScoutReportsTest(unittest.TestCase):
    def report(self, root, *, results=True):
        rules = [{"id": SSL.cve, "properties": {
            "purls": ["pkg:apk/alpine/libssl3@3.5.9-r0?arch=x86_64&upstream=openssl"],
            "fixed_version": SSL.fixed}}]
        path = root / "report.json"
        path.write_text(json.dumps({"version": "2.1.0", "runs": [{
            "tool": {"driver": {"rules": rules}},
            "results": [{"ruleId": SSL.cve, "ruleIndex": 0}] if results else [],
        }]}))
        return path

    def test_scout_sarif_retains_package_and_fixed_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(scout_reports.read_findings(self.report(Path(tmp))), {SSL})

    def test_unused_rules_are_not_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(scout_reports.read_findings(self.report(Path(tmp), results=False)), set())

    def test_malformed_report_cannot_pass_as_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            report.write_text('{"runs": []}')
            with self.assertRaises(ValueError):
                scout_reports.read_findings(report)

    def test_failed_scan_cannot_reuse_stale_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.report(Path(tmp))
            with patch.object(scout_reports.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], 1, "", "network failure")):
                with self.assertRaises(RuntimeError):
                    scout_reports.scan("image@" + DIGEST, "linux/amd64", report)
            self.assertFalse(report.exists())

    def test_exit_code_and_findings_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def run(*args, **kwargs):
                self.report(root)
                return subprocess.CompletedProcess([], 0, "", "")
            with patch.object(scout_reports.subprocess, "run", side_effect=run):
                with self.assertRaises(ValueError):
                    scout_reports.scan("image@" + DIGEST, "linux/amd64", root / "report.json")

    def test_scans_disable_attached_vex_suppressions(self):
        # Baselines and candidates can carry different VEX attestations even
        # when the vulnerable package version has not changed.
        for only_fixed in (False, True):
            with self.subTest(only_fixed=only_fixed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)

                def run(*args, **kwargs):
                    self.report(root)
                    return subprocess.CompletedProcess([], 2, "", "")

                with patch.object(scout_reports.subprocess, "run", side_effect=run) as command:
                    findings = scout_reports.scan("image@" + DIGEST, "linux/amd64",
                                                 root / "report.json", only_fixed=only_fixed)
                self.assertEqual(findings, {SSL})
                arguments = command.call_args.args[0]
                self.assertEqual(arguments[arguments.index("--vex-author") + 1], "^$")
                self.assertEqual("--only-fixed" in arguments, only_fixed)

    def test_local_oci_scan_does_not_resolve_candidate_from_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def run(*args, **kwargs):
                self.report(root)
                return subprocess.CompletedProcess([], 2, "", "")

            with patch.object(scout_reports.subprocess, "run", side_effect=run) as command:
                scout_reports.scan("oci-dir:///tmp/candidates/base", "linux/arm64", root / "report.json")
            self.assertEqual(command.call_args.args[0][3], "oci-dir:///tmp/candidates/base")



class AvailabilityTest(unittest.TestCase):
    def probe(self, stdout="", returncode=0):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(scanner.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], returncode, stdout, "apk output")) as run:
                result = scanner.available_fixes("image@" + DIGEST, "linux/amd64", {SSL, MUSL},
                                                 Path(tmp) / "availability.log")
            command = run.call_args.args[0]
            self.assertIn("--rm", command)
            self.assertIn("image@" + DIGEST, command)
            return result

    def test_unavailable_advisory_fixes_do_not_trigger_rebuild(self):
        self.assertEqual(self.probe(), set())

    def test_partial_package_fix_triggers_only_available_cve(self):
        self.assertEqual(self.probe("libssl3\t3.5.9-r1\n"), {SSL.cve})

    def test_repository_error_is_not_treated_as_waiting_for_upstream(self):
        with self.assertRaises(RuntimeError):
            self.probe(returncode=1)

    def test_non_apk_fix_requires_upstream_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(scanner.subprocess, "run") as run:
                self.assertEqual(scanner.available_fixes("image", "linux/amd64",
                    {Finding("CVE-2026-1234", "pkg:generic/httpd", "2.4.70", "2.4.71")},
                    Path(tmp) / "availability.log"), set())
            run.assert_not_called()

    def test_partial_scan_failure_blocks_automatic_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(scanner, "parse_env_file", return_value={"APACHE_VERSION": "2.4.71"}), \
                 patch.object(scanner, "resolve_digest", return_value=DIGEST), \
                 patch.object(scanner, "scan", side_effect=[{SSL}, RuntimeError("offline"), set(), set(), set(), set()]), \
                 patch.object(scanner, "available_fixes", return_value={SSL.cve}), \
                 patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                has_fixes, errors, _ = scanner.scan_images(Path(tmp))
            self.assertFalse(has_fixes)
            self.assertTrue(errors)


class PublicationTest(unittest.TestCase):
    def layouts(self, root):
        layouts = {}
        for variant in CANDIDATES:
            layout = root / variant
            layout.mkdir()
            (layout / "index.json").write_text(json.dumps({"manifests": [{"digest": DIGEST}]}))
            layouts[variant] = str(layout)
        return layouts

    def verify(self, pairs):
        scans = [findings for pair in pairs for findings in pair]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(verification, "parse_env_file", return_value={"APACHE_VERSION": "2.4.71"}), \
                 patch.object(verification, "resolve_digest", return_value=DIGEST), \
                 patch.object(verification, "scan", side_effect=scans) as scan, \
                 patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                result = verification.verify(CANDIDATES, Path(tmp), self.layouts(Path(tmp)))
            self.assertEqual(scan.call_count, 12)
            for call in scan.call_args_list[1::2]:
                self.assertTrue(call.args[0].startswith("oci-dir://"))
            self.assertEqual([call.args[1] for call in scan.call_args_list[1::2]],
                             ["linux/amd64", "linux/arm64"] * 3)
            return result

    def test_mismatched_local_candidate_blocks_publication_before_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            layouts = self.layouts(Path(tmp))
            with patch.object(verification, "parse_env_file", return_value={"APACHE_VERSION": "2.4.71"}), \
                 patch.object(verification, "scan") as scan, \
                 patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    verification.verify({name: "sha256:" + "b" * 64 for name in CANDIDATES},
                                        Path(tmp), layouts)
            scan.assert_not_called()

    def test_no_improvement_blocks_promotion(self):
        with self.assertRaises(RuntimeError):
            self.verify([({SSL, MUSL}, {SSL, MUSL})] * 6)

    def test_complete_fix_is_verified_across_all_six_scans(self):
        self.assertEqual(self.verify([({SSL, MUSL}, set())] * 6),
                         (",".join(sorted([SSL.cve, MUSL.cve])), ""))

    def test_partial_fix_reports_remaining_cves_including_unfixed(self):
        self.assertEqual(self.verify([({SSL, MUSL, XML}, {MUSL, XML})] * 6),
                         (SSL.cve, ",".join(sorted([MUSL.cve, XML.cve]))))

    def test_fix_on_only_one_architecture_is_not_claimed_globally(self):
        fixed, remaining = self.verify([({SSL}, set())] + [({SSL}, {SSL})] * 5)
        self.assertEqual(fixed, "")
        self.assertEqual(remaining, SSL.cve)

    def test_regression_on_one_architecture_blocks_entire_publication(self):
        with self.assertRaises(RuntimeError):
            self.verify([({SSL}, set())] * 5 + [({SSL}, {MUSL})])

    def test_version_change_with_same_cve_is_not_a_fix(self):
        upgraded = Finding(SSL.cve, SSL.package, "3.5.9-r1", "3.5.9-r2")
        self.assertEqual(verification.compare({SSL}, {upgraded}), (set(), set()))

    def test_fix_metadata_disappearing_is_not_a_fix(self):
        unfixed = Finding(SSL.cve, SSL.package, SSL.version, "not fixed")
        self.assertEqual(verification.compare({SSL}, {unfixed}), (set(), set()))

    def test_scan_error_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(verification, "parse_env_file", return_value={"APACHE_VERSION": "2.4.71"}), \
                 patch.object(verification, "resolve_digest", return_value=DIGEST), \
                 patch.object(verification, "scan", side_effect=subprocess.TimeoutExpired("scout", 600)), \
                 patch.dict("os.environ", {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    verification.verify(CANDIDATES, Path(tmp), self.layouts(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
