"""Security scanning gate and evidence (Epic 7 / EMM-83).

Runs the available scanners over the repository and writes a machine-readable
record to ``evidence/security-scan.json``:

* **bandit**  — static analysis of the Python source (SAST)
* **pip-audit** — known vulnerabilities in declared Python dependencies
* **trivy**   — filesystem and container findings (dependency + OS + secret)

Tools that are not installed are reported as ``skipped`` with a reason. In CI
(``--require-tools``) a missing tool fails the gate, so the pipeline cannot
silently stop scanning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "evidence" / "security-scan.json"
TIMEOUT_SECONDS = 600


def _run(command: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True,
                                timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {TIMEOUT_SECONDS}s"
    return result.returncode, result.stdout or "", result.stderr or ""


def _json_or_none(text: str):
    """Parse the first JSON value in ``text``, ignoring surrounding output."""
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character in "{[":
            try:
                value, _end = decoder.raw_decode(text[index:])
                return value
            except json.JSONDecodeError:
                continue
    return None


def bandit() -> dict:
    if shutil.which("bandit") is None:
        return {"tool": "bandit", "status": "skipped", "reason": "bandit is not installed"}
    code, stdout, stderr = _run(["bandit", "-r", "src", "scripts", "-f", "json", "-ll"])
    payload = _json_or_none(stdout)
    findings = len(payload.get("results", [])) if payload else None
    return {"tool": "bandit", "status": "ran", "exit_code": code, "findings": findings,
            "files_scanned": payload.get("metrics", {}).get("_totals", {}).get("loc") if payload else None,
            "error": None if payload else stderr.strip()[:400]}


def pip_audit() -> dict:
    if shutil.which("pip-audit") is None:
        return {"tool": "pip-audit", "status": "skipped", "reason": "pip-audit is not installed"}
    targets = [str(path.relative_to(REPO_ROOT)) for path in
               (REPO_ROOT / "requirements.txt", REPO_ROOT / "requirements-server.txt") if path.exists()]
    command = ["pip-audit", "-f", "json"]
    for target in targets:
        command += ["-r", target]
    code, stdout, stderr = _run(command)
    payload = _json_or_none(stdout)
    vulnerabilities = 0
    if isinstance(payload, dict):
        dependencies = payload.get("dependencies", [])
        vulnerabilities = sum(len(item.get("vulns", [])) for item in dependencies)
    elif isinstance(payload, list):
        vulnerabilities = sum(len(item.get("vulns", [])) for item in payload)
    return {"tool": "pip-audit", "status": "ran", "exit_code": code,
            "requirements": targets, "vulnerabilities": vulnerabilities,
            "error": None if payload is not None else stderr.strip()[:400]}


def trivy() -> dict:
    if shutil.which("trivy") is None:
        return {"tool": "trivy", "status": "skipped", "reason": "trivy is not installed"}
    code, stdout, stderr = _run(["trivy", "fs", "--quiet", "--format", "json", "--severity", "HIGH,CRITICAL",
                                "--skip-dirs", "frontend/node_modules", "--skip-dirs", ".git", "."])
    payload = _json_or_none(stdout)
    findings = 0
    if payload:
        for result in payload.get("Results", []) or []:
            findings += len(result.get("Vulnerabilities", []) or [])
            findings += len(result.get("Secrets", []) or [])
            findings += len(result.get("Misconfigurations", []) or [])
    return {"tool": "trivy", "status": "ran", "exit_code": code, "high_or_critical_findings": findings,
            "error": None if payload is not None else stderr.strip()[:400]}


def scan(*, require_tools: bool = False) -> dict:
    results = [bandit(), pip_audit(), trivy()]
    missing = [item["tool"] for item in results if item["status"] == "skipped"]
    findings = 0
    for item in results:
        findings += item.get("findings") or 0
        findings += item.get("vulnerabilities") or 0
        findings += item.get("high_or_critical_findings") or 0
    problems: list[str] = []
    if require_tools and missing:
        problems.append(f"required scanners are not installed: {', '.join(missing)}")
    # A scanner that ran but produced no parseable report must not be allowed to
    # look like a clean scan: an unread report and an empty report are not the
    # same evidence.
    for item in results:
        if item["status"] == "ran" and item.get("error"):
            problems.append(f"{item['tool']} produced no parseable report: {item['error']}")
    if findings:
        problems.append(f"{findings} finding(s) reported")
    return {
        "schema_version": 1,
        "epic": "EMM-83",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "require_tools": require_tools,
        "scanners": results,
        "findings": findings,
        "problems": problems,
        "ok": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan", description="LEDGER security scanning gate")
    parser.add_argument("--require-tools", action="store_true",
                        help="fail when a scanner is not installed (use in CI)")
    parser.add_argument("--output", default=str(EVIDENCE_PATH))
    arguments = parser.parse_args(argv)
    result = scan(require_tools=arguments.require_tools)
    target = Path(arguments.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "findings": result["findings"],
                      "problems": result["problems"], "evidence": str(target)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
