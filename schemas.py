"""Pydantic schemas for review findings, AI response, and final report."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    MAINTAINABILITY = "maintainability"
    PERFORMANCE = "performance"


class CheckStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Verdict(str, Enum):
    FIX = "Fix before pushing"
    INCOMPLETE = "Review incomplete"
    WARNINGS = "Review warnings before pushing"
    OK = "Looks OK within reviewed scope"


# ---------------------------------------------------------------------------
# Individual finding
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    """One review finding from any source."""
    source: str = Field(description="Tool or reviewer that produced this finding")
    severity: Severity
    category: Category
    line: Optional[int] = Field(default=None, description="1-based line number, if applicable")
    title: str
    explanation: str
    suggestion: str = ""
    code_suggestion: str = Field(default="", description="Suggested code, only when useful")


# ---------------------------------------------------------------------------
# AI response schema (what we ask the model to return)
# ---------------------------------------------------------------------------

class AIFinding(BaseModel):
    """Single finding returned by the AI reviewer."""
    severity: Severity
    category: Category
    line: Optional[int] = None
    title: str
    explanation: str
    suggestion: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: str) -> str:
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        if isinstance(v, str):
            return v.lower().strip()
        return v


class AIReviewResponse(BaseModel):
    """Expected structured response from the AI model."""
    summary: str
    findings: list[AIFinding] = Field(default_factory=list, max_length=8)
    suggested_tests: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Overall report
# ---------------------------------------------------------------------------

class CheckResult(BaseModel):
    """Status of a single check in the pipeline."""
    name: str
    status: CheckStatus
    detail: str = ""


class ReviewReport(BaseModel):
    """Complete review report combining all checks."""
    verdict: Verdict
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    suggested_tests: list[str] = Field(default_factory=list)
    ai_summary: str = ""

    @property
    def sorted_findings(self) -> list[Finding]:
        """Findings sorted by severity: high → medium → low."""
        order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
        return sorted(self.findings, key=lambda f: order.get(f.severity, 3))

    @property
    def has_high(self) -> bool:
        return any(f.severity == Severity.HIGH for f in self.findings)

    @property
    def has_medium(self) -> bool:
        return any(f.severity == Severity.MEDIUM for f in self.findings)
