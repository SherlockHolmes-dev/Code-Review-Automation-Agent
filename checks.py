"""Static analysis checks: AST parsing, Ruff, and Bandit.

Each check function returns a tuple of (list[Finding], CheckResult).
Tools run in an isolated temp directory and never execute the submitted code.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
import uuid
from typing import Tuple

from schemas import (
    Category,
    CheckResult,
    CheckStatus,
    Finding,
    Severity,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUBPROCESS_TIMEOUT = 30  # seconds

# Ruff severity mapping: rule prefix → severity
_RUFF_SEVERITY: dict[str, Severity] = {
    "E9": Severity.HIGH,      # syntax / parse errors
    "F821": Severity.HIGH,    # undefined name
    "F822": Severity.HIGH,    # undefined name in __all__
    "F811": Severity.MEDIUM,  # redefined unused name
    "F841": Severity.LOW,     # local variable assigned but never used
    "F401": Severity.LOW,     # imported but unused
}


def _ruff_severity(code: str) -> Severity:
    """Map a Ruff rule code to a severity level."""
    if code in _RUFF_SEVERITY:
        return _RUFF_SEVERITY[code]
    if code.startswith("E9"):
        return Severity.HIGH
    if code.startswith("F"):
        return Severity.MEDIUM
    return Severity.MEDIUM


# ---------------------------------------------------------------------------
# AST syntax check
# ---------------------------------------------------------------------------

def check_syntax(source: str) -> Tuple[list[Finding], CheckResult]:
    """Parse source with ast.parse. Returns findings and check status."""
    try:
        ast.parse(source)
        return [], CheckResult(name="syntax", status=CheckStatus.COMPLETED)
    except SyntaxError as e:
        finding = Finding(
            source="ast.parse",
            severity=Severity.HIGH,
            category=Category.CORRECTNESS,
            line=e.lineno,
            title="Syntax error",
            explanation=str(e.msg) if e.msg else str(e),
            suggestion="Fix the syntax error before proceeding.",
        )
        return [finding], CheckResult(
            name="syntax",
            status=CheckStatus.COMPLETED,
            detail="Syntax error found",
        )


# ---------------------------------------------------------------------------
# Helper: write source to isolated temp file
# ---------------------------------------------------------------------------

def _write_temp_file(source: str) -> Tuple[str, str]:
    """Write source to a temp dir with a generated filename.

    Returns (temp_dir, file_path). Caller must clean up temp_dir.
    """
    temp_dir = tempfile.mkdtemp(prefix="codereview_")
    filename = f"review_{uuid.uuid4().hex[:12]}.py"
    filepath = os.path.join(temp_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(source)
    return temp_dir, filepath


def _cleanup_temp(temp_dir: str) -> None:
    """Remove the temporary directory and its contents."""
    import shutil
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Ruff check
# ---------------------------------------------------------------------------

def check_ruff(source: str) -> Tuple[list[Finding], CheckResult]:
    """Run Ruff with F and E9 rule groups. Returns findings and check status."""
    temp_dir, filepath = _write_temp_file(source)
    try:
        cmd = [
            "ruff", "check",
            "--select", "F,E9",
            "--output-format", "json",
            "--no-cache",
            filepath,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            cwd=temp_dir,
        )

        # Ruff exits 0 = no findings, 1 = findings found, 2 = error
        if result.returncode == 2:
            return [], CheckResult(
                name="ruff",
                status=CheckStatus.FAILED,
                detail=f"Ruff execution error: {result.stderr.strip()[:200]}",
            )

        try:
            raw_findings = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            return [], CheckResult(
                name="ruff",
                status=CheckStatus.FAILED,
                detail="Failed to parse Ruff JSON output",
            )

        findings: list[Finding] = []
        for item in raw_findings:
            code = item.get("code", "")
            message = item.get("message", "")
            line = item.get("location", {}).get("row")
            findings.append(Finding(
                source="ruff",
                severity=_ruff_severity(code),
                category=Category.CORRECTNESS,
                line=line,
                title=f"{code}: {message}",
                explanation=message,
                suggestion="",
            ))

        return findings, CheckResult(name="ruff", status=CheckStatus.COMPLETED)

    except subprocess.TimeoutExpired:
        return [], CheckResult(
            name="ruff",
            status=CheckStatus.FAILED,
            detail=f"Ruff timed out after {SUBPROCESS_TIMEOUT}s",
        )
    except FileNotFoundError:
        return [], CheckResult(
            name="ruff",
            status=CheckStatus.FAILED,
            detail="Ruff is not installed or not on PATH",
        )
    except Exception as e:
        return [], CheckResult(
            name="ruff",
            status=CheckStatus.FAILED,
            detail=f"Unexpected error running Ruff: {str(e)[:200]}",
        )
    finally:
        _cleanup_temp(temp_dir)


# ---------------------------------------------------------------------------
# Bandit check
# ---------------------------------------------------------------------------

# Bandit severity/confidence → our severity
_BANDIT_SEVERITY_MAP = {
    ("HIGH", "HIGH"): Severity.HIGH,
    ("HIGH", "MEDIUM"): Severity.HIGH,
    ("MEDIUM", "HIGH"): Severity.MEDIUM,
    ("MEDIUM", "MEDIUM"): Severity.MEDIUM,
    ("LOW", "HIGH"): Severity.LOW,
    ("LOW", "MEDIUM"): Severity.LOW,
}


def _bandit_severity(sev: str, conf: str) -> Severity:
    """Map Bandit severity and confidence to our severity."""
    key = (sev.upper(), conf.upper())
    return _BANDIT_SEVERITY_MAP.get(key, Severity.MEDIUM)


def check_bandit(source: str) -> Tuple[list[Finding], CheckResult]:
    """Run Bandit security scanner. Returns findings and check status."""
    temp_dir, filepath = _write_temp_file(source)
    try:
        cmd = [
            "bandit",
            "-f", "json",
            "-ll",  # medium and high severity
            filepath,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            cwd=temp_dir,
        )

        # Bandit: exit 0 = no findings, 1 = findings found
        try:
            output = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            return [], CheckResult(
                name="bandit",
                status=CheckStatus.FAILED,
                detail="Failed to parse Bandit JSON output",
            )

        # Check for errors reported by Bandit itself
        errors = output.get("errors", [])
        if errors and not output.get("results"):
            error_msgs = "; ".join(str(e)[:100] for e in errors[:3])
            return [], CheckResult(
                name="bandit",
                status=CheckStatus.FAILED,
                detail=f"Bandit reported errors: {error_msgs}",
            )

        findings: list[Finding] = []
        for item in output.get("results", []):
            sev = item.get("issue_severity", "MEDIUM")
            conf = item.get("issue_confidence", "MEDIUM")
            findings.append(Finding(
                source="bandit",
                severity=_bandit_severity(sev, conf),
                category=Category.SECURITY,
                line=item.get("line_number"),
                title=f"{item.get('test_id', '')}: {item.get('issue_text', '')}",
                explanation=(
                    f"Severity: {sev}, Confidence: {conf}. "
                    f"{item.get('issue_text', '')} "
                    "This is a potential security issue requiring context, not proof of exploitation."
                ),
                suggestion=item.get("more_info", ""),
            ))

        return findings, CheckResult(name="bandit", status=CheckStatus.COMPLETED)

    except subprocess.TimeoutExpired:
        return [], CheckResult(
            name="bandit",
            status=CheckStatus.FAILED,
            detail=f"Bandit timed out after {SUBPROCESS_TIMEOUT}s",
        )
    except FileNotFoundError:
        return [], CheckResult(
            name="bandit",
            status=CheckStatus.FAILED,
            detail="Bandit is not installed or not on PATH",
        )
    except Exception as e:
        return [], CheckResult(
            name="bandit",
            status=CheckStatus.FAILED,
            detail=f"Unexpected error running Bandit: {str(e)[:200]}",
        )
    finally:
        _cleanup_temp(temp_dir)
