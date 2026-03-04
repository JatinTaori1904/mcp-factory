"""Code Reviewer — LLM-powered review of generated MCP server code.

Stage 3: After generating an MCP server, the reviewer sends the main
server file to the LLM for quality analysis. It checks for:
  - Bugs and runtime errors
  - Security issues (hardcoded secrets, injection, etc.)
  - MCP best-practice violations
  - Missing error handling
  - Import completeness
  - Type safety

Returns a structured CodeReview with score, issues, and suggestions.
Gracefully skipped when no LLM is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from mcp_factory.llm.client import LLMClient


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------

@dataclass
class ReviewIssue:
    """A single issue found during code review."""
    severity: str          # "error", "warning", "info"
    category: str          # "bug", "security", "best-practice", "style", "performance"
    message: str           # human-readable description
    line_hint: Optional[str] = None   # approximate location or code snippet
    suggestion: Optional[str] = None  # how to fix it


@dataclass
class CodeReview:
    """Result of an LLM code review."""
    score: int                                      # 1-10
    summary: str                                    # one-line overall assessment
    issues: list[ReviewIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)   # things done well
    reviewed: bool = True                           # False if LLM was unavailable

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")


# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------

REVIEW_SYSTEM_PROMPT = """\
You are a senior code reviewer specializing in MCP (Model Context Protocol) servers. \
Review the provided code for quality, security, and best practices.

You check for:
1. **Bugs**: Runtime errors, logic mistakes, unhandled edge cases
2. **Security**: Hardcoded secrets, injection vulnerabilities, missing input validation
3. **MCP Best Practices**: Tool annotations, descriptive parameters, error messages with suggestions
4. **Error Handling**: Missing try/catch, unhelpful error messages
5. **Type Safety**: Missing types, any casts, unsafe operations
6. **Performance**: Unnecessary allocations, missing pagination, unbounded responses
7. **Style**: Naming conventions, code organization, documentation

Return ONLY valid JSON with NO extra text.\
"""

REVIEW_USER_PROMPT = """\
Review this {language} MCP server code:

```{language_ext}
{code}
```

Return exactly this JSON structure:
{{
  "score": 8,
  "summary": "One-line overall assessment of the code quality",
  "issues": [
    {{
      "severity": "error|warning|info",
      "category": "bug|security|best-practice|style|performance",
      "message": "Clear description of the issue",
      "line_hint": "relevant code snippet or line reference",
      "suggestion": "How to fix it"
    }}
  ],
  "strengths": [
    "Specific things the code does well"
  ]
}}

Rules:
- Score 1-10 (1=critical issues, 10=production-ready)
- Be specific — reference actual code, not generic advice
- Only report real issues, not nitpicks
- Strengths should acknowledge good patterns actually present
- If the code is solid, say so — don't invent problems\
"""


# ------------------------------------------------------------------
# Reviewer
# ------------------------------------------------------------------

class CodeReviewer:
    """Reviews generated MCP server code using an LLM."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def review(
        self,
        output_path: Path,
        language: str,
    ) -> CodeReview:
        """Review the generated server code.

        Returns a CodeReview. If the LLM is unavailable, returns a
        placeholder review with ``reviewed=False``.
        """
        if not self.llm.is_available():
            return CodeReview(
                score=0,
                summary="Review skipped — no LLM available",
                reviewed=False,
            )

        # Read the main server file
        if language == "typescript":
            server_file = output_path / "src" / "index.ts"
        else:
            server_file = output_path / "server.py"

        if not server_file.exists():
            return CodeReview(
                score=0,
                summary=f"Server file not found: {server_file.name}",
                reviewed=False,
            )

        try:
            code = server_file.read_text(encoding="utf-8")
        except Exception:
            return CodeReview(
                score=0,
                summary="Could not read server file",
                reviewed=False,
            )

        # Truncate very large files to avoid LLM token limits
        max_chars = 12000
        if len(code) > max_chars:
            code = code[:max_chars] + "\n\n// ... (truncated for review)\n"

        lang_ext = "typescript" if language == "typescript" else "python"
        user_prompt = REVIEW_USER_PROMPT.format(
            language=language,
            language_ext=lang_ext,
            code=code,
        )

        parsed, response = self.llm.chat_json(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=2048,
            timeout=60.0,
        )

        if parsed is None:
            return CodeReview(
                score=0,
                summary="LLM review failed — could not parse response",
                reviewed=False,
            )

        return self._parse_review(parsed)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_review(data: dict) -> CodeReview:
        """Parse the LLM's JSON response into a CodeReview."""
        score = data.get("score", 0)
        if not isinstance(score, (int, float)):
            score = 0
        score = max(1, min(10, int(score)))

        summary = str(data.get("summary", "No summary provided"))

        issues = []
        for item in data.get("issues", []):
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "info")).lower()
            if severity not in ("error", "warning", "info"):
                severity = "info"
            category = str(item.get("category", "style")).lower()
            valid_cats = {"bug", "security", "best-practice", "style", "performance"}
            if category not in valid_cats:
                category = "style"

            issues.append(ReviewIssue(
                severity=severity,
                category=category,
                message=str(item.get("message", "")),
                line_hint=item.get("line_hint"),
                suggestion=item.get("suggestion"),
            ))

        strengths = []
        for s in data.get("strengths", []):
            if isinstance(s, str) and s.strip():
                strengths.append(s.strip())

        return CodeReview(
            score=score,
            summary=summary,
            issues=issues,
            strengths=strengths,
            reviewed=True,
        )
