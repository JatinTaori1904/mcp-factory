"""Interactive Prompt Refiner — Asks follow-up questions to improve vague prompts.

When a user's prompt is too short or ambiguous, this module generates
targeted follow-up questions and combines the answers into an enriched
prompt that yields higher-quality MCP server generation.

Works with or without an LLM:
  - With LLM:  generates context-aware questions based on the initial analysis
  - Without LLM: uses rule-based heuristics per detected template
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mcp_factory.llm.client import LLMClient


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FollowUpQuestion:
    """A single follow-up question with optional choices."""
    question: str
    key: str  # short identifier (e.g. "data_source")
    choices: list[str] = field(default_factory=list)  # pre-defined options; empty = free text
    default: str = ""


@dataclass
class RefinementResult:
    """Result of the interactive prompt refinement."""
    original_prompt: str
    enhanced_prompt: str
    questions_asked: list[FollowUpQuestion]
    answers: dict[str, str]  # key -> answer
    was_refined: bool  # True if prompt was actually refined


# ---------------------------------------------------------------------------
# Prompts for LLM-powered question generation
# ---------------------------------------------------------------------------

QUESTION_SYSTEM_PROMPT = """\
You are an expert MCP server architect helping a user clarify their request. \
The user gave a vague or incomplete prompt for generating an MCP server. \

Your job: ask 2-4 short, focused follow-up questions that will help \
generate a much better MCP server.

Rules:
  - Each question should target ONE specific missing detail.
  - Provide 2-4 predefined answer choices where appropriate.
  - Focus on: data sources, auth requirements, specific operations needed, \
    output format, and scale/limits.
  - Keep questions short (one sentence).
  - Do NOT ask about programming language or framework — that's already chosen.

Return ONLY valid JSON:\
"""

QUESTION_USER_PROMPT = """\
The user wants to build an MCP server. Their prompt:

"{prompt}"

I detected template: {template}
Detected intent: {intent}

Generate follow-up questions to clarify what they need:

{{
  "questions": [
    {{
      "question": "What kind of data source will this connect to?",
      "key": "data_source",
      "choices": ["PostgreSQL", "MySQL", "SQLite", "MongoDB"],
      "default": ""
    }}
  ]
}}\
"""


# ---------------------------------------------------------------------------
# Rule-based fallback questions per template
# ---------------------------------------------------------------------------

TEMPLATE_QUESTIONS: dict[str, list[FollowUpQuestion]] = {
    "file-reader": [
        FollowUpQuestion(
            "What file formats do you need to process?",
            "formats",
            ["CSV", "JSON", "Plain text", "XML/YAML", "Mixed formats"],
        ),
        FollowUpQuestion(
            "What operations do you need besides reading?",
            "operations",
            ["Search/filter content", "Write/append files", "Convert between formats", "Just read and list"],
            "Just read and list",
        ),
    ],
    "database-connector": [
        FollowUpQuestion(
            "Which database engine?",
            "db_engine",
            ["PostgreSQL", "MySQL", "SQLite", "SQL Server"],
        ),
        FollowUpQuestion(
            "Do you need write access (INSERT/UPDATE/DELETE)?",
            "write_access",
            ["Read-only queries", "Full read/write access"],
            "Read-only queries",
        ),
    ],
    "api-wrapper": [
        FollowUpQuestion(
            "Which API do you want to integrate with?",
            "api_name",
            ["GitHub", "Slack", "Stripe", "Notion", "Discord", "LinkedIn", "Other"],
        ),
        FollowUpQuestion(
            "What operations do you need?",
            "operations",
            ["Read data only", "Read and create", "Full CRUD (create/read/update/delete)"],
            "Read and create",
        ),
    ],
    "web-scraper": [
        FollowUpQuestion(
            "What kind of data do you want to extract?",
            "data_type",
            ["Text content", "Links/URLs", "Structured data (tables, prices)", "All of the above"],
        ),
        FollowUpQuestion(
            "Single page or multi-page crawling?",
            "scope",
            ["Single page extraction", "Follow links and crawl multiple pages"],
            "Single page extraction",
        ),
    ],
    "document-processor": [
        FollowUpQuestion(
            "What document types will you process?",
            "doc_types",
            ["PDF", "Plain text/Markdown", "Invoices/receipts", "Contracts/legal"],
        ),
        FollowUpQuestion(
            "What do you want to do with the documents?",
            "operations",
            ["Extract text", "Search within documents", "Summarize content", "Extract structured data"],
        ),
    ],
    "auth-server": [
        FollowUpQuestion(
            "Where should user data be stored?",
            "storage",
            ["JSON file (simple)", "SQLite database", "In-memory only"],
            "JSON file (simple)",
        ),
        FollowUpQuestion(
            "Do you need role-based access control?",
            "rbac",
            ["Yes, multiple roles (admin/user/viewer)", "No, just login/register"],
            "No, just login/register",
        ),
    ],
    "data-pipeline": [
        FollowUpQuestion(
            "What is your input data format?",
            "input_format",
            ["CSV files", "JSON/JSONL", "API responses", "Mixed sources"],
        ),
        FollowUpQuestion(
            "What transformations do you need?",
            "transforms",
            ["Filter/select rows", "Aggregate/group data", "Join/merge datasets", "All of the above"],
        ),
    ],
    "notification-hub": [
        FollowUpQuestion(
            "Which notification channels do you need?",
            "channels",
            ["Email (SMTP)", "Webhooks", "Console logging", "All of the above"],
            "All of the above",
        ),
        FollowUpQuestion(
            "Do you need notification history/logging?",
            "history",
            ["Yes, keep history of all notifications", "No, just fire and forget"],
            "Yes, keep history of all notifications",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Prompt quality heuristics
# ---------------------------------------------------------------------------

MIN_WORDS_FOR_GOOD_PROMPT = 8  # prompts shorter than this are considered vague
QUALITY_KEYWORDS = {
    "specific": ["csv", "json", "postgresql", "mysql", "sqlite", "github", "slack",
                 "stripe", "notion", "discord", "jwt", "email", "webhook", "pipeline",
                 "etl", "auth", "login"],
    "action": ["read", "write", "query", "scrape", "extract", "send", "create",
               "delete", "filter", "transform", "aggregate", "register", "login"],
}


def prompt_quality_score(prompt: str) -> float:
    """Score prompt quality from 0.0 (very vague) to 1.0 (very specific).

    Factors:
    - Word count (longer = more detail)
    - Presence of specific technology/format keywords
    - Presence of action verbs
    """
    words = prompt.lower().split()
    word_count = len(words)

    # Base score from length
    length_score = min(word_count / 15, 1.0)  # 15+ words = max length score

    # Specificity bonus
    specific_hits = sum(1 for kw in QUALITY_KEYWORDS["specific"] if kw in prompt.lower())
    specific_score = min(specific_hits / 3, 1.0)  # 3+ specific terms = max

    # Action verb bonus
    action_hits = sum(1 for kw in QUALITY_KEYWORDS["action"] if kw in prompt.lower())
    action_score = min(action_hits / 2, 1.0)  # 2+ actions = max

    # Weighted average
    return 0.4 * length_score + 0.35 * specific_score + 0.25 * action_score


def is_prompt_vague(prompt: str) -> bool:
    """Determine if a prompt needs follow-up questions.

    Returns True if the prompt is too short or lacks specifics.
    """
    words = prompt.strip().split()
    if len(words) < MIN_WORDS_FOR_GOOD_PROMPT:
        return True
    return prompt_quality_score(prompt) < 0.45


# ---------------------------------------------------------------------------
# PromptRefiner
# ---------------------------------------------------------------------------

class PromptRefiner:
    """Generates follow-up questions and builds enriched prompts.

    With an LLM available, questions are dynamically generated.
    Without an LLM, template-specific fallback questions are used.
    """

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def needs_refinement(self, prompt: str) -> bool:
        """Check if the prompt would benefit from follow-up questions."""
        return is_prompt_vague(prompt)

    def generate_questions(
        self, prompt: str, template: str, intent: str
    ) -> list[FollowUpQuestion]:
        """Generate follow-up questions for a vague prompt.

        Tries LLM first, falls back to template-specific rules.
        """
        # Try LLM-powered questions
        if self.llm and self.llm.is_available():
            llm_questions = self._generate_with_llm(prompt, template, intent)
            if llm_questions:
                return llm_questions

        # Fallback: rule-based questions
        return TEMPLATE_QUESTIONS.get(template, [
            FollowUpQuestion(
                "Can you describe what specific operations you need?",
                "operations",
            ),
            FollowUpQuestion(
                "What data sources or services will this connect to?",
                "data_source",
            ),
        ])

    def build_enhanced_prompt(
        self,
        original_prompt: str,
        questions: list[FollowUpQuestion],
        answers: dict[str, str],
    ) -> RefinementResult:
        """Combine original prompt with answers into an enhanced prompt.

        The enhanced prompt provides much richer context for the generator.
        """
        # Build context from answers
        context_parts = []
        for q in questions:
            answer = answers.get(q.key, q.default).strip()
            if answer:
                context_parts.append(f"{q.question} {answer}")

        if context_parts:
            context = ". ".join(context_parts)
            enhanced = f"{original_prompt}. Additional details: {context}"
        else:
            enhanced = original_prompt

        return RefinementResult(
            original_prompt=original_prompt,
            enhanced_prompt=enhanced,
            questions_asked=questions,
            answers=answers,
            was_refined=bool(context_parts),
        )

    # ------------------------------------------------------------------
    # LLM-powered question generation
    # ------------------------------------------------------------------

    def _generate_with_llm(
        self, prompt: str, template: str, intent: str
    ) -> Optional[list[FollowUpQuestion]]:
        """Ask the LLM to generate context-specific follow-up questions."""
        if not self.llm:
            return None

        user_prompt = QUESTION_USER_PROMPT.format(
            prompt=prompt,
            template=template,
            intent=intent,
        )

        result, _response = self.llm.chat_json(
            system_prompt=QUESTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        if not result or "questions" not in result:
            return None

        questions = []
        for q in result["questions"]:
            if not isinstance(q, dict):
                continue
            question_text = q.get("question", "").strip()
            key = q.get("key", "").strip()
            if not question_text or not key:
                continue
            questions.append(FollowUpQuestion(
                question=question_text,
                key=key,
                choices=q.get("choices", []),
                default=q.get("default", ""),
            ))

        return questions if questions else None
