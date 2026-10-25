"""Code Review Automation Agent — Streamlit interface.

Provides a UI to paste Python code or upload a .py file, runs the review
pipeline, and displays findings with a downloadable Markdown report.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import streamlit as st

from reviewer import generate_markdown_report, review_code, validate_input
from schemas import CheckStatus, Severity, Verdict

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Code Review Agent",
    page_icon="🔍",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Example files
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent / "examples"

EXAMPLES = {
    "Clean FizzBuzz": EXAMPLES_DIR / "clean_fizzbuzz.py",
    "Problematic Processor (bugs + security)": EXAMPLES_DIR / "problematic_processor.py",
    "Syntax Error": EXAMPLES_DIR / "syntax_error.py",
}


def _load_example(name: str) -> str:
    path = EXAMPLES[name]
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _input_hash(source: str, description: str) -> str:
    """Hash the input to detect changes."""
    return hashlib.sha256((source + "|||" + description).encode()).hexdigest()


def _clear_stale_result(source: str, description: str) -> None:
    """Clear the result if the input has changed."""
    current_hash = _input_hash(source, description)
    if st.session_state.get("last_input_hash") != current_hash:
        st.session_state.pop("report", None)
        st.session_state.pop("markdown_report", None)
        st.session_state.pop("last_input_hash", None)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🔍 Code Review Automation Agent")
st.caption("Paste Python code or upload a `.py` file for an automated review.")

# Disclaimer
st.info(
    "⚠️ **Disclaimer:** This review covers only the submitted file. "
    "It does not run your code or tests and cannot guarantee that the full project is safe to push.\n\n"
    "🔒 **Privacy:** AI-enabled review sends your code to Google's Gemini API. "
    "Use the free tier only with non-sensitive sample code.",
    icon="ℹ️",
)

# --- Input mode ---
col_mode, col_example = st.columns([2, 1])

with col_mode:
    input_mode = st.radio(
        "Input method",
        ["Paste code", "Upload .py file"],
        horizontal=True,
        label_visibility="collapsed",
    )

with col_example:
    example_choice = st.selectbox(
        "Load example",
        ["—"] + list(EXAMPLES.keys()),
        label_visibility="collapsed",
    )

# --- Code input ---
source = ""

if example_choice != "—":
    source = _load_example(example_choice)
    st.code(source, language="python", line_numbers=True)
elif input_mode == "Paste code":
    source = st.text_area(
        "Paste your Python code here",
        height=350,
        placeholder="# Paste your Python code here...",
    )
else:
    uploaded_file = st.file_uploader(
        "Upload a .py file",
        type=["py"],
        accept_multiple_files=False,
    )
    if uploaded_file is not None:
        # Validate file type
        if not uploaded_file.name.endswith(".py"):
            st.error("Only `.py` files are supported.")
        else:
            try:
                raw_bytes = uploaded_file.read()
                source = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                st.error("File contains invalid text encoding. Please upload a UTF-8 encoded `.py` file.")
                source = ""

            if source:
                st.code(source, language="python", line_numbers=True)

# --- Description ---
description = st.text_input(
    "Optional: describe what this code should do",
    placeholder="e.g., 'A function that parses CSV files and returns a list of dicts'",
)

# --- Review button ---
review_clicked = st.button("🔍 Review Code", type="primary", use_container_width=True)

if review_clicked:
    # Validate before running
    error = validate_input(source)
    if error:
        st.error(error)
    else:
        _clear_stale_result(source, description)

        with st.spinner("Running review pipeline..."):
            report = review_code(source, description)
            md_report = generate_markdown_report(report, source)

            st.session_state["report"] = report
            st.session_state["markdown_report"] = md_report
            st.session_state["last_input_hash"] = _input_hash(source, description)

# ---------------------------------------------------------------------------
# Display results
# ---------------------------------------------------------------------------

if "report" in st.session_state:
    report = st.session_state["report"]
    md_report = st.session_state["markdown_report"]

    st.divider()

    # --- Verdict banner ---
    verdict_config = {
        Verdict.FIX: ("🔴", "error"),
        Verdict.INCOMPLETE: ("🟡", "warning"),
        Verdict.WARNINGS: ("🟠", "warning"),
        Verdict.OK: ("🟢", "success"),
    }
    icon, alert_type = verdict_config.get(report.verdict, ("⚪", "info"))
    getattr(st, alert_type)(f"{icon} **{report.verdict.value}**")

    # --- Summary ---
    st.subheader("Summary")
    st.write(report.summary)

    if report.ai_summary:
        st.write(f"**AI Assessment:** {report.ai_summary}")

    # --- Check status ---
    st.subheader("Check Status")
    check_cols = st.columns(len(report.checks))
    for i, check in enumerate(report.checks):
        with check_cols[i]:
            status_icon = {
                CheckStatus.COMPLETED: "✅",
                CheckStatus.FAILED: "❌",
                CheckStatus.SKIPPED: "⏭️",
            }.get(check.status, "❓")
            st.metric(check.name, f"{status_icon} {check.status.value}")
            if check.detail:
                st.caption(check.detail)

    # --- Findings ---
    if report.sorted_findings:
        st.subheader(f"Findings ({len(report.sorted_findings)})")

        for finding in report.sorted_findings:
            severity_colors = {
                Severity.HIGH: "🔴",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "🔵",
            }
            sev_icon = severity_colors.get(finding.severity, "⚪")
            line_str = f"Line {finding.line}" if finding.line else "N/A"

            with st.expander(
                f"{sev_icon} [{finding.severity.value.upper()}] {finding.title}  "
                f"({finding.source}, {line_str})",
                expanded=(finding.severity == Severity.HIGH),
            ):
                st.markdown(f"**Source:** `{finding.source}`  \n"
                          f"**Category:** {finding.category.value}  \n"
                          f"**Line:** {line_str}")
                st.markdown(f"**Explanation:** {finding.explanation}")
                if finding.suggestion:
                    st.markdown(f"**Suggestion:** {finding.suggestion}")
                if finding.code_suggestion:
                    st.code(finding.code_suggestion, language="python")
    else:
        st.subheader("Findings")
        st.success("No issues found! 🎉")

    # --- Suggested tests ---
    if report.suggested_tests:
        st.subheader("Suggested Tests")
        for test_desc in report.suggested_tests:
            st.markdown(f"- {test_desc}")

    # --- Download report ---
    st.divider()
    st.download_button(
        label="📥 Download Markdown Report",
        data=md_report,
        file_name="code_review_report.md",
        mime="text/markdown",
        use_container_width=True,
    )
