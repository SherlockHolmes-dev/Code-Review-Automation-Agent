# 🔍 Code Review Automation Agent

An automated Python code review tool that combines static analysis with AI-powered review to flag risks, suggest improvements, and give an advisory push-readiness recommendation.

> **Disclaimer:** This review covers only the submitted file. It does not run your code or tests and cannot guarantee that the full project is safe to push.

## How the Pipeline Works

```
User Input → Validate → AST Parse → Ruff + Bandit → AI Review → Combine → Verdict
```

1. **Input Validation** — Rejects empty, oversized (>500 lines / >30 KB), or invalid input
2. **Syntax Check** — Parses with `ast.parse` (never executes code). On syntax error, skips remaining checks
3. **Ruff** — Runs `F` + `E9` rule groups for correctness issues (undefined names, unused imports, syntax errors)
4. **Bandit** — Scans for security issues (shell injection, pickle, eval, weak crypto, etc.)
5. **AI Review** — Sends code + static findings to Gemini for logic bugs, edge cases, and maintainability review
6. **Validation** — Validates AI response with Pydantic; drops invalid line references
7. **Verdict** — Computes recommendation in Python (AI cannot override):
   - 🔴 **Fix before pushing** — syntax error or high-severity finding
   - 🟡 **Review incomplete** — any check failed, timed out, or was skipped
   - 🟠 **Review warnings before pushing** — medium-severity findings
   - 🟢 **Looks OK within reviewed scope** — no significant issues found

### Severity Mapping

| Source | Rule | Severity |
|--------|------|----------|
| Ruff | E9xx (syntax), F821/F822 (undefined name) | High |
| Ruff | F811 (redefined name), other F rules | Medium |
| Ruff | F401 (unused import), F841 (unused variable) | Low |
| Bandit | Preserved from Bandit's own severity + confidence | As reported |
| AI | As returned by model | As returned |

## Installation

### Prerequisites

- Python 3.10+ (tested with 3.12)
- A [free Gemini API key](https://aistudio.google.com/apikey) (for AI review)

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/code-review-agent.git
cd code-review-agent

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### API Key Setup

Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey).

**Option A: Environment variable**
```bash
export GEMINI_API_KEY="your-key-here"
```

**Option B: Streamlit secrets (recommended for deployment)**
```bash
# Copy the example file
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Edit with your key
# GEMINI_API_KEY = "your-actual-key-here"
```

> ⚠️ **Never commit** `.streamlit/secrets.toml` — it's in `.gitignore`.

### Free Tier Notes

- The default model is `gemini-2.0-flash-lite` (free tier eligible)
- Override with: `export GEMINI_MODEL="gemini-2.5-flash-preview-05-20"` or any available model
- The spec asked for `gemini-3.5-flash-lite` which does not exist; we use `gemini-2.0-flash-lite` instead
- Free tier has rate limits (~15 RPM, ~1M TPM) — the app makes only one API call per review
- If quota is exhausted, static findings are still shown with an "incomplete AI review" status

## Running the App

```bash
source venv/bin/activate
streamlit run app.py
```

The app opens at `http://localhost:8501`. You can:
- **Paste code** directly into the text area
- **Upload a `.py` file**
- **Load an example** from the dropdown (clean, buggy, or syntax error)
- Click **Review Code** and view findings sorted by severity
- **Download** the full Markdown report

## Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

All tests use mocked Gemini API calls — **no API key required** for testing.

### What's Tested

| Category | Tests |
|----------|-------|
| Input validation | Empty, whitespace-only, oversized (lines + bytes), null bytes |
| Syntax check | Clean code, syntax errors |
| Ruff | Undefined names (high), unused imports (low), tool timeout/missing |
| Bandit | Security findings (shell=True), tool timeout/missing |
| AI review | Missing key, quota error, model unavailable, invalid JSON, invalid lines |
| Verdict logic | All precedence rules, high overrides incomplete |
| Pipeline | Full flow with mocked AI, syntax error skips AI |
| Safety | Submitted code is never executed, imports are never triggered |
| Prompt injection | Code with reviewer-instruction comments still gets flagged |
| Report | Markdown output contains verdict, findings, disclaimer |

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub (ensure `.streamlit/secrets.toml` is in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub account and select the repository
4. Set **Main file path** to `app.py`
5. Under **Advanced Settings → Secrets**, add:
   ```toml
   GEMINI_API_KEY = "your-actual-api-key"
   ```
6. Deploy — the app will install from `requirements.txt` automatically

> Secrets added in the Streamlit Cloud dashboard are never committed to your repo.

## Demonstration

### Clean Code Example
Load "Clean FizzBuzz" from the example dropdown → expect few or no findings, verdict "Looks OK within reviewed scope".

### Problematic Code Example
Load "Problematic Processor" → expect multiple high/medium findings:
- Bandit flags: `pickle.load`, `shell=True`, `eval()`, weak MD5 hashing
- Ruff flags: unused variable
- AI flags: SQL injection, missing error handling, unclosed DB connection, division by zero

### Syntax Error Example
Load "Syntax Error" → expect one high-severity syntax finding, verdict "Fix before pushing", all other checks skipped.

## Architecture

```
├── app.py                  # Streamlit UI
├── reviewer.py             # Review pipeline + AI integration + verdict
├── checks.py               # Static checks: AST, Ruff, Bandit
├── schemas.py              # Pydantic models for findings and reports
├── examples/               # Sample .py files for demonstration
│   ├── clean_fizzbuzz.py
│   ├── problematic_processor.py
│   └── syntax_error.py
├── tests/
│   └── test_reviewer.py    # Comprehensive mocked test suite
├── requirements.txt        # Pinned dependency ranges
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example
└── README.md
```

## Design Decisions

### Why submitted suppression comments are ignored
We run Ruff and Bandit without respecting inline `# noqa` or `# nosec` comments in the submitted code. This prevents a user from silencing findings by adding suppression comments. The review should reflect the actual state of the code. This is documented here for transparency.

### Why the AI cannot override the verdict
The final verdict is computed deterministically in Python based on finding severities and check statuses. The AI model contributes findings but cannot directly set or override the verdict. This prevents prompt injection or model hallucination from producing misleading recommendations.

### Prompt injection defense
The system prompt instructs the model to treat all submitted content (code, comments, strings, description) as untrusted review material and ignore any embedded instructions. The problematic example includes a deliberate prompt injection attempt to verify this. Note: prompt engineering reduces this risk but cannot guarantee complete immunity against adversarial inputs.

## Known Limitations

- **Single file only** — does not analyze imports from other project files
- **No execution** — cannot detect runtime-only bugs or integration issues
- **AI limitations** — may produce false positives/negatives; limited by model capabilities
- **Rate limits** — free tier has quotas; the app makes one API call per review
- **No persistence** — results are session-only; code is not stored
- **Privacy** — AI-enabled review sends code to Google's Gemini API; use only with non-sensitive sample code on the free tier

## Data Handling

- Submitted code is **not logged or persisted** on disk or in any database
- API keys are read from environment variables or Streamlit secrets only
- Code is sent to Google's Gemini API for AI review (one request per review)
- Temporary files for Ruff/Bandit use generated filenames and are cleaned up immediately
- No shared caching of user content across sessions

## License

MIT
