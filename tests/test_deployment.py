"""Epic 7 (EMM-83) deployment, release, and rollback tests.

These tests exercise the real release tooling, the real deployment
configuration, and the real security gate. They assert the properties the epic
must guarantee: a reproducible artifact with a verified checksum, absolute
refusal to package a secret, a tested rollback that preserves what it replaces,
deployment configurations that reference files that exist, and no committed
credential anywhere in the tracked tree.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release  # noqa: E402
import scan as scan_module  # noqa: E402


def run_release(argv: list[str]) -> tuple[int, dict]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = release.main(argv)
    text = out.getvalue() or err.getvalue()
    return status, (json.loads(text) if text.strip() else {})


class ReleaseArtifactTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="ledger-release-"))
        self.addCleanup(shutil.rmtree, str(self.directory), ignore_errors=True)
        self.evidence = self.directory / "evidence"
        self._original_evidence = release.EVIDENCE_DIR
        release.EVIDENCE_DIR = self.evidence
        self.addCleanup(setattr, release, "EVIDENCE_DIR", self._original_evidence)
        self.built: list[dict] = []

    def build(self, version: str = "9.9.9") -> dict:
        status, payload = run_release(["build", "--version", version, "--output", str(self.directory / "dist")])
        self.assertEqual(status, 0, payload)
        self.built.append(payload)
        return payload

    def test_artifact_builds_verifies_and_records_evidence(self):
        payload = self.build()
        self.assertEqual(payload["version"], "9.9.9")
        self.assertGreater(payload["files"], 50)
        self.assertEqual(payload["secret_scan"], "clean")
        artifact = Path(payload["artifact"])
        self.assertTrue(artifact.exists())
        self.assertTrue(Path(str(artifact) + ".sha256").exists())
        self.assertTrue((self.evidence / "release-9.9.9.json").exists())

        status, verified = run_release(["verify", "--artifact", str(artifact)])
        self.assertEqual(status, 0, verified)
        self.assertTrue(verified["ok"])
        self.assertTrue(verified["checksum_matched"])
        manifest = verified["manifest"]
        self.assertEqual(manifest["version"], "9.9.9")
        self.assertEqual(len(manifest["files"]), payload["files"])
        for entry in manifest["files"][:5]:
            self.assertEqual(len(entry["sha256"]), 64)

    def test_artifact_is_deterministic_for_unchanged_inputs(self):
        first = self.build("9.9.9")
        first_manifest = json.loads(
            (self.evidence / "release-9.9.9.json").read_text(encoding="utf-8")
        )["manifest"]
        # Nothing in the tree changes between builds, so every packaged file
        # digest must be identical: the packaging step adds no variance of its
        # own (owner, group, and mtime are normalized inside the archive).
        second = self.build("9.9.8")
        self.assertEqual([entry["sha256"] for entry in first_manifest["files"]],
                         [entry["sha256"] for entry in second["manifest"]["files"]])
        self.assertEqual([entry["path"] for entry in first_manifest["files"]],
                         [entry["path"] for entry in second["manifest"]["files"]])
        self.assertNotEqual(first["sha256"], second["sha256"])  # version differs in the manifest

    def test_build_refuses_to_package_a_real_looking_secret(self):
        fixture = REPO_ROOT / "tests" / "_tmp_secret_fixture.env"
        fixture.write_text("LEDGER_TOKEN_SECRET=8f3c1d9a7b2e4f6a5c8d0e1f2a3b4c5d6e7f\n", encoding="utf-8")
        self.addCleanup(fixture.unlink, True)
        original = release.tracked_files
        release.tracked_files = lambda revision="HEAD": sorted(set(original(revision)) | {"tests/_tmp_secret_fixture.env"})
        self.addCleanup(setattr, release, "tracked_files", original)
        status, payload = run_release(["build", "--version", "9.9.7", "--output", str(self.directory / "dist")])
        self.assertEqual(status, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("refusing to package secret-looking content", payload["error"])
        self.assertFalse((self.directory / "dist" / "ledger-9.9.7.tar.gz").exists())

    def test_verify_detects_a_tampered_checksum(self):
        artifact = Path(self.build("9.9.6")["artifact"])
        checksum = Path(str(artifact) + ".sha256")
        checksum.write_text("0" * 64 + "  " + artifact.name + "\n", encoding="utf-8")
        status, payload = run_release(["verify", "--artifact", str(artifact)])
        self.assertEqual(status, 1)
        self.assertIn("checksum mismatch", payload["error"])

    def test_verify_rejects_an_artifact_containing_a_secret(self):
        artifact = self.directory / "handmade.tar.gz"
        payload_dir = self.directory / "ledger-1.0.0"
        payload_dir.mkdir()
        (payload_dir / "secrets.env").write_text("LEDGER_API_TOKENS=aaaaaaaaaaaaaaaaaaaa:operator\n", encoding="utf-8")
        with tarfile.open(artifact, "w:gz") as archive:
            archive.add(payload_dir, arcname="ledger-1.0.0")
        status, payload = run_release(["verify", "--artifact", str(artifact)])
        self.assertEqual(status, 1)
        self.assertIn("secret-looking content", payload["error"])

    def test_rollback_replaces_the_target_and_preserves_the_previous_tree(self):
        artifact = Path(self.build("9.9.5")["artifact"])
        target = self.directory / "deployed"
        target.mkdir()
        (target / "VERSION").write_text("8.8.8\n", encoding="utf-8")
        (target / "stale.txt").write_text("old\n", encoding="utf-8")
        status, payload = run_release(["rollback", "--artifact", str(artifact), "--target", str(target), "--force"])
        self.assertEqual(status, 0, payload)
        self.assertTrue(payload["ok"])
        self.assertTrue((target / "VERSION").exists())
        self.assertFalse((target / "stale.txt").exists())
        preserved = Path(payload["preserved"])
        self.assertTrue((preserved / "stale.txt").exists())

    def test_rollback_refuses_path_traversal(self):
        artifact = self.directory / "evil.tar.gz"
        with tarfile.open(artifact, "w:gz") as archive:
            data = b"owned"
            info = tarfile.TarInfo("../outside.txt")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        status, payload = run_release(["rollback", "--artifact", str(artifact),
                                      "--target", str(self.directory / "never")])
        self.assertEqual(status, 1)
        self.assertFalse((self.directory.parent / "outside.txt").exists())

    def test_version_file_is_a_release_version(self):
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        parts = version.split(".")
        self.assertEqual(len(parts), 3, version)
        self.assertTrue(all(part.isdigit() for part in parts), version)


class DeploymentConfigTests(unittest.TestCase):
    def test_compose_references_exist_and_stack_parses(self):
        compose = (REPO_ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
        for referenced in (
            "../docs/observability/prometheus.yml",
            "../docs/observability/alerts",
            "../docs/observability/ledger-overview.dashboard.json",
            "./grafana/provisioning",
            "./env/${LEDGER_ENV_FILE:-development}.env",
        ):
            self.assertIn(referenced, compose)
        for real in (
            REPO_ROOT / "docs" / "observability" / "prometheus.yml",
            REPO_ROOT / "docs" / "observability" / "ledger-overview.dashboard.json",
            REPO_ROOT / "deploy" / "grafana" / "provisioning" / "dashboards" / "ledger.yml",
            REPO_ROOT / "deploy" / "grafana" / "provisioning" / "datasources" / "prometheus.yml",
        ):
            self.assertTrue(real.exists(), f"{real} is referenced but missing")

    def test_dockerfile_runs_unprivileged_and_ships_no_secret(self):
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER ledger", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("/var/lib/ledger", dockerfile)
        self.assertNotIn("LEDGER_TOKEN_SECRET=", dockerfile)
        self.assertNotIn("LEDGER_API_TOKENS=", dockerfile)

    def test_env_examples_document_the_required_secrets_without_values(self):
        for name in ("development", "staging", "production"):
            text = (REPO_ROOT / "deploy" / "env" / f"{name}.env.example").read_text(encoding="utf-8")
            if name == "development":
                self.assertIn("LEDGER_API_TOKENS=", text)
            else:
                self.assertIn("LEDGER_TOKEN_SECRET=", text)
                self.assertIn("LEDGER_REQUIRE_TLS=true", text)
        self.assertFalse((REPO_ROOT / "deploy" / "env" / "production.env").exists())

    def test_systemd_units_invoke_the_published_commands(self):
        backup = (REPO_ROOT / "deploy" / "systemd" / "ledger-backup.service").read_text(encoding="utf-8")
        self.assertIn("ledger.ops backup", backup)
        self.assertIn("--metrics-output", backup)
        self.assertIn("/bin/sh -c", backup)
        pipeline_unit = (REPO_ROOT / "deploy" / "systemd" / "ledger-pipeline.service").read_text(encoding="utf-8")
        self.assertIn("ledger.pipeline process", pipeline_unit)

    def test_ci_workflow_runs_every_documented_gate(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for gate in ("make check", "product_proof/run_product_proof.py", "make db-drill",
                     "make observability-proof", "make release-check", "scripts/scan.py --require-tools",
                     "npm run check", "npm run test:e2e"):
            self.assertIn(gate, workflow)

    def test_documented_make_targets_exist(self):
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ("db-drill", "observability-proof", "scan", "release-check"):
            self.assertIn(f"{target}:", makefile)


class SecurityGateTests(unittest.TestCase):
    def test_unparseable_scanner_report_is_not_a_green_gate(self):
        original = scan_module.bandit
        self.addCleanup(setattr, scan_module, "bandit", original)
        scan_module.bandit = lambda: {"tool": "bandit", "status": "ran", "exit_code": 1,
                                      "findings": None, "files_scanned": None,
                                      "error": "bandit produced no JSON report"}
        result = scan_module.scan()
        self.assertFalse(result["ok"])
        self.assertTrue(any("no parseable report" in problem for problem in result["problems"]))

    def test_scan_writes_evidence_and_reports_findings(self):
        directory = Path(tempfile.mkdtemp(prefix="ledger-scan-"))
        self.addCleanup(shutil.rmtree, str(directory), ignore_errors=True)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            status = scan_module.main(["--output", str(directory / "scan.json")])
        self.assertIn(status, (0, 1))
        payload = json.loads((directory / "scan.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["scanners"]), 3)
        self.assertIn("ok", payload)

    def test_required_tools_fail_the_gate_when_missing(self):
        original = shutil.which
        shutil.which = lambda name: None
        self.addCleanup(setattr, shutil, "which", original)
        result = scan_module.scan(require_tools=True)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["scanners"]), 3)
        self.assertTrue(all(item["status"] == "skipped" for item in result["scanners"]))

    def test_no_committed_secret_in_the_tracked_tree(self):
        findings: list[str] = []
        for path in release.tracked_files():
            data = (REPO_ROOT / path).read_bytes()
            findings.extend(release.scan_for_secrets(data, path))
        self.assertEqual(findings, [], findings)


if __name__ == "__main__":
    unittest.main()
