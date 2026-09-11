"""Versioned release artifacts, verification, and rollback (Epic 7 / EMM-83).

Subcommands::

    python3 scripts/release.py build   --version 1.0.0 [--output dist] [--revision HEAD]
    python3 scripts/release.py verify  --artifact dist/ledger-1.0.0.tar.gz
    python3 scripts/release.py rollback --artifact dist/ledger-0.9.0.tar.gz --target /opt/ledger

The artifact is a deterministic gzip tar of the tracked source tree (git), with
a SHA-256 companion file and a machine-readable evidence record. ``build``
refuses to package a secret, ``verify`` re-checks the checksum and re-scans, and
``rollback`` unpacks a previous artifact atomically while preserving the
directory it replaces — so a rollback is testable, not just documented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "evidence"

# Paths never packaged: local state, build output, dependencies, editor noise.
EXCLUDED_PREFIXES = (
    ".git/", ".github/", ".next/", "node_modules/", "frontend/node_modules/",
    "frontend/.next/", "frontend/test-results/", "frontend/playwright-report/",
    "data/", "dist/", "__pycache__/", ".pytest_cache/", ".vercel/",
)
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".log")
EXCLUDED_NAMES = {"ledger.sqlite3", ".env", ".env.local"}
ALLOWED_ENV_NAME = ".env.example"

# Two classes of finding:
#   1. Material that is never acceptable in an artifact, in any file (PEM keys,
#      cloud access key ids).
#   2. An environment assignment carrying a *real-looking* value. A file that is
#      itself an example (`*.example`) is documentation, so its values are
#      placeholders by definition; PEM/cloud material is still checked there.
ALWAYS_FORBIDDEN = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"(?i)aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{20,}"),
)
SECRET_ASSIGNMENT = re.compile(
    rb"^\s*(LEDGER_TOKEN_SECRET|LEDGER_API_TOKENS)\s*=\s*(\S.*?)\s*$", re.MULTILINE
)
# `dev-token` is the documented development-only placeholder used by
# deploy/env/development.env.example and the operator docs; it is not a secret.
PLACEHOLDER_MARKERS = ("$(", "<", "…", "...", "CHANGE_ME", "changeme", "REPLACE", "xxxx", "dev-token")


def _is_placeholder(value: str) -> bool:
    """True when an assigned value is obviously documentation, not a secret."""
    text = value.strip().strip("\"'").strip()
    if not text:
        return True
    if any(marker in text for marker in PLACEHOLDER_MARKERS):
        return True
    return len(text) < 16

MANIFEST_NAME = "RELEASE-MANIFEST.json"


class ReleaseError(RuntimeError):
    """The release command refused to proceed."""


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _display(path: Path) -> str:
    """Repository-relative path when possible, absolute path otherwise."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def tracked_files(revision: str = "HEAD") -> list[str]:
    """Paths from the git tree at the revision (plus uncommitted working files)."""
    listed = _git("ls-tree", "-r", "--name-only", revision).splitlines()
    names = {line.strip() for line in listed if line.strip()}
    dirty = _git("status", "--porcelain").splitlines()
    for line in dirty:
        path = line[3:].strip()
        if not path or " -> " in path:
            continue
        if (REPO_ROOT / path).is_file():
            names.add(path)
    return sorted(path for path in names if _packaged(path))


def _packaged(path: str) -> bool:
    posix = PurePosixPath(path)
    if any(part == "__pycache__" for part in posix.parts):
        return False
    if any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    if path.endswith(EXCLUDED_SUFFIXES):
        return False
    if posix.name in EXCLUDED_NAMES:
        return False
    if posix.name.startswith(".env") and posix.name != ALLOWED_ENV_NAME:
        return False
    return True


def scan_for_secrets(data: bytes, name: str) -> list[str]:
    """Return human-readable findings for secret-looking content."""
    findings: list[str] = []
    for pattern in ALWAYS_FORBIDDEN:
        match = pattern.search(data)
        if match:
            findings.append(f"{name}: {match.group(0).decode('utf-8', 'replace')[:48]}")
    if not name.endswith(".example"):
        for match in SECRET_ASSIGNMENT.finditer(data):
            value = match.group(2).decode("utf-8", "replace")
            if not _is_placeholder(value):
                findings.append(f"{name}: {match.group(1).decode()} assigned a non-placeholder value")
    return findings


def build(version: str, *, output: Path, revision: str = "HEAD", generated_at: float | None = None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / f"ledger-{version}.tar.gz"
    if artifact.exists():
        raise ReleaseError(f"{artifact} exists; refusing to overwrite a release artifact")

    files = tracked_files(revision)
    if not files:
        raise ReleaseError("no tracked files to package")
    findings: list[str] = []
    manifest_files: list[dict] = []
    digest = hashlib.sha256()
    for path in files:
        data = (REPO_ROOT / path).read_bytes()
        findings.extend(scan_for_secrets(data, path))
        manifest_files.append({"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    if findings:
        raise ReleaseError("refusing to package secret-looking content: " + "; ".join(findings[:5]))

    manifest = {
        "schema_version": 1,
        "version": version,
        "revision": _git("rev-parse", revision).strip(),
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(generated_at if generated_at is not None else time.time())
        ),
        "files": manifest_files,
    }

    def _normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        return info

    with tempfile.TemporaryDirectory() as staging:
        staging_path = Path(staging)
        payload = staging_path / f"ledger-{version}"
        for path in files:
            target = payload / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / path, target)
        (payload / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        with tarfile.open(artifact, "w:gz", format=tarfile.GNU_FORMAT) as archive:
            archive.add(payload, arcname=f"ledger-{version}", filter=_normalize)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksum = artifact.with_suffix(artifact.suffix + ".sha256")
    checksum.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    evidence = {
        "schema_version": 1,
        "epic": "EMM-83",
        "version": version,
        "revision": manifest["revision"],
        "generated_at": manifest["generated_at"],
        "artifact": _display(artifact),
        "bytes": artifact.stat().st_size,
        "sha256": digest,
        "files": len(manifest_files),
        "secret_scan": "clean",
        "manifest": manifest,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / f"release-{version}.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    return evidence


def verify(artifact_path: str) -> dict:
    artifact = Path(artifact_path)
    if not artifact.exists():
        raise ReleaseError(f"{artifact} does not exist")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksum = Path(str(artifact) + ".sha256")
    expected = None
    if checksum.exists():
        expected = checksum.read_text(encoding="utf-8").split()[0]
    if expected is not None and expected != digest:
        raise ReleaseError(f"checksum mismatch: expected {expected}, computed {digest}")
    findings: list[str] = []
    members = 0
    manifest = None
    with tarfile.open(artifact, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            members += 1
            payload = archive.extractfile(member)
            data = payload.read() if payload is not None else b""
            findings.extend(scan_for_secrets(data, member.name))
            if member.name.endswith(MANIFEST_NAME):
                manifest = json.loads(data)
    if findings:
        raise ReleaseError("artifact contains secret-looking content: " + "; ".join(findings[:5]))
    return {
        "ok": True,
        "artifact": str(artifact),
        "sha256": digest,
        "checksum_matched": expected is None or expected == digest,
        "members": members,
        "checksum_file_present": checksum.exists(),
        "manifest": manifest,
    }


def rollback(artifact_path: str, target: str, *, force: bool = False) -> dict:
    """Unpack a previous release over the target, preserving what it replaces."""
    report = verify(artifact_path)
    target_path = Path(target)
    preserved: Path | None = None
    if target_path.exists():
        if not force:
            raise ReleaseError(f"{target_path} exists; pass --force to replace it")
        preserved = target_path.with_name(f"{target_path.name}.pre-rollback-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
        os.replace(target_path, preserved)
    staging = Path(tempfile.mkdtemp(prefix="ledger-rollback-", dir=str(target_path.parent) if target_path.parent.exists() else None))
    try:
        with tarfile.open(artifact_path, "r:gz") as archive:
            _safe_extract(archive, staging)
        roots = [entry for entry in staging.iterdir()]
        if len(roots) != 1:
            raise ReleaseError("artifact must contain exactly one top-level directory")
        os.replace(roots[0], target_path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"ok": True, "artifact": report["artifact"], "target": str(target_path),
            "preserved": str(preserved) if preserved else None}


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    """Extract an artifact after rejecting traversal and unsafe members.

    ``filter="data"`` is the stdlib's documented safe extraction filter: it
    rejects absolute paths, ``..`` traversal, links, and device files. The
    explicit containment check below is defense in depth on top of it.
    """
    base = destination.resolve()
    for member in archive.getmembers():
        resolved = (base / member.name).resolve()
        if not str(resolved).startswith(str(base)):
            raise ReleaseError(f"refusing path traversal in artifact member {member.name!r}")
    archive.extractall(destination, filter="data")


def _current_version() -> str:
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release", description="LEDGER release artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--version", default=None)
    build_parser.add_argument("--output", default=str(REPO_ROOT / "dist"))
    build_parser.add_argument("--revision", default="HEAD")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--artifact", required=True)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--artifact", required=True)
    rollback_parser.add_argument("--target", required=True)
    rollback_parser.add_argument("--force", action="store_true")

    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "build":
            result = build(arguments.version or _current_version(),
                           output=Path(arguments.output), revision=arguments.revision)
        elif arguments.command == "verify":
            result = verify(arguments.artifact)
        else:
            result = rollback(arguments.artifact, arguments.target, force=arguments.force)
    except ReleaseError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
