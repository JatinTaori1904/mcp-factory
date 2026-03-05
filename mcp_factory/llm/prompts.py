"""LLM Prompt Templates — Structured prompts for MCP Factory stages.

Each prompt is designed to return reliable JSON that maps directly
to our internal data models (PromptAnalysis, ToolDefinition, etc.).
"""

from __future__ import annotations

from typing import Optional

# ------------------------------------------------------------------
# Stage 1: Prompt → Analysis JSON
# ------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert MCP (Model Context Protocol) server architect. Your job is to \
analyze a user's natural language request and produce a precise JSON plan for \
generating an MCP server.

You know these templates:
  1. file-reader     — Read/search/write local files (csv, json, txt, etc.)
  2. database-connector — SQL database queries (PostgreSQL, MySQL, SQLite)
  3. api-wrapper     — Wrap a REST/GraphQL API as MCP tools
  4. web-scraper     — Scrape & extract data from web pages
  5. document-processor — Process documents (PDF, DOCX, images, OCR)
  6. auth-server     — JWT authentication, user registration, token management
  7. data-pipeline   — ETL / data ingestion, transformation, aggregation, export
  8. notification-hub — Multi-channel notifications (email, webhook, log)

You know these APIs (use the exact name if detected):
  github, slack, openai, stripe, notion, spotify, google, twitter, discord, linear, jira

Rules:
  - Pick exactly ONE template that best matches the request.
  - Design 3-7 specific, well-named tools (not generic ones).
  - Tool names use snake_case with a consistent prefix (e.g., gh_, slack_, file_).
  - Each tool gets MCP annotations: read_only, destructive, idempotent, open_world.
  - Set read_only=false and destructive=true for any tool that modifies data.
  - Set open_world=true for tools that reach external services.
  - If the request mentions known APIs, list ALL of them in api_names (e.g. ["github", "slack"]).
  - If only one API is mentioned, still use an array: ["github"].
  - If no known API is mentioned, set api_names to [].
  - prefix should be 2-5 chars + underscore, derived from the primary API or domain.
  - For multi-API servers, include tools for EACH API with distinct prefixes (gh_, slack_, etc.).

Return ONLY valid JSON with NO extra text.\
"""

USER_PROMPT_TEMPLATE = """\
Analyze this request and return a JSON plan:

"{prompt}"

Return exactly this JSON structure:
{{
  "intent": "one-line summary of what the user wants",
  "template": "file-reader|database-connector|api-wrapper|web-scraper|document-processor|auth-server|data-pipeline|notification-hub",
  "api_names": ["github", "slack"],
  "prefix": "short_",
  "suggested_name": "kebab-case-server-name",
  "tools": [
    {{
      "name": "prefix_action_noun",
      "description": "Clear description of what the tool does, including inputs and outputs",
      "read_only": true,
      "destructive": false,
      "idempotent": true,
      "open_world": false
    }}
  ]
}}\
"""


# ------------------------------------------------------------------
# Response parser
# ------------------------------------------------------------------

def parse_analysis_response(data: dict) -> Optional[dict]:
    """Validate and normalize a parsed JSON response from the LLM.

    Returns ``None`` if the data is malformed or missing required fields.
    Otherwise returns a clean dict ready for ``PromptAnalysis`` construction.
    """
    if not isinstance(data, dict):
        return None

    # Required top-level fields
    intent = data.get("intent")
    template = data.get("template")
    tools_raw = data.get("tools")

    if not intent or not template or not isinstance(tools_raw, list):
        return None

    # Validate template
    valid_templates = {
        "file-reader", "database-connector", "api-wrapper",
        "web-scraper", "document-processor",
        "auth-server", "data-pipeline", "notification-hub",
    }
    if template not in valid_templates:
        return None

    # Validate & normalize tools
    tools = []
    for t in tools_raw:
        if not isinstance(t, dict):
            continue
        name = t.get("name", "").strip()
        description = t.get("description", "").strip()
        if not name or not description:
            continue

        tools.append({
            "name": name,
            "description": description,
            "read_only": bool(t.get("read_only", True)),
            "destructive": bool(t.get("destructive", False)),
            "idempotent": bool(t.get("idempotent", True)),
            "open_world": bool(t.get("open_world", False)),
        })

    if not tools:
        return None

    # Normalize api_names (support both old "api_name" and new "api_names")
    valid_apis = {
        "github", "slack", "openai", "stripe", "notion",
        "spotify", "google", "twitter", "discord", "linear", "jira",
    }

    api_names: list[str] = []
    raw_names = data.get("api_names", data.get("api_name"))
    if isinstance(raw_names, list):
        api_names = [n for n in raw_names if isinstance(n, str) and n in valid_apis]
    elif isinstance(raw_names, str) and raw_names not in ("null", "none", ""):
        if raw_names in valid_apis:
            api_names = [raw_names]

    # Normalize prefix
    prefix = data.get("prefix", "").strip()
    if not prefix:
        prefix = tools[0]["name"].split("_")[0] + "_" if "_" in tools[0]["name"] else ""

    # Normalize suggested_name
    suggested_name = data.get("suggested_name", "").strip()
    if not suggested_name:
        primary = api_names[0] if api_names else template
        suggested_name = f"{primary}-mcp-server"

    return {
        "intent": intent.strip(),
        "template": template,
        "api_names": api_names,
        "prefix": prefix,
        "suggested_name": suggested_name[:30],
        "tools": tools,
    }


# ------------------------------------------------------------------
# Stage 2: LLM-generated tool logic
# ------------------------------------------------------------------

TOOL_LOGIC_SYSTEM_PROMPT = """\
You are an expert MCP server developer. Given a tool specification, you write \
the complete implementation code — real, working, production-quality code.

Rules:
  - Return ONLY valid JSON with a "tools" array.
  - Each tool entry has "name" (string) and "code" (string of complete source code).
  - Code must handle errors gracefully with try/catch.
  - Code must return structured JSON in MCP format.
  - Include proper input validation.
  - For API tools, use the correct endpoints, HTTP methods, and auth headers.
  - Do NOT invent placeholder URLs — use the real API endpoints.
  - TypeScript code uses fetch, Zod schemas, and MCP SDK patterns.
  - Python code uses httpx, FastMCP @mcp.tool() decorators, and returns JSON strings.
  - Match the language requested (typescript or python).
  - Do NOT include import statements — those are handled externally.
  - Do NOT wrap code in markdown code blocks.\
"""

TOOL_LOGIC_USER_PROMPT = """\
Generate {language} MCP tool implementations for this server:

Server purpose: {intent}
APIs: {api_names}

{api_vars_section}

Tools to implement:
{tool_specs}

Available variables:
  - errorResponse(msg, hint?) — helper function to return MCP error responses
  - Each API has its own prefixed constants (see above)

Return JSON:
{{
  "tools": [
    {{
      "name": "tool_name",
      "code": "server.tool(...) or @mcp.tool() complete implementation"
    }}
  ]
}}\"
"""


def build_tool_logic_prompt(
    language: str,
    intent: str,
    api_name: str | None = None,
    base_url: str = "",
    tools: list[dict] | None = None,
    *,
    api_names: list[str] | None = None,
    api_vars: dict[str, dict[str, str]] | None = None,
) -> str:
    """Build a user prompt for LLM tool logic generation.

    Supports the old single-API interface (api_name/base_url) for backward
    compatibility, and the new multi-API interface (api_names/api_vars).
    """
    tools = tools or []
    tool_specs = "\n".join(
        f"  - {t['name']}: {t['description']} "
        f"(readOnly={t.get('read_only', True)}, destructive={t.get('destructive', False)})"
        for t in tools
    )

    # Build api_vars_section
    if api_vars:
        parts = []
        for name, info in api_vars.items():
            prefix = name.upper()
            parts.append(
                f"  {name}: {prefix}_BASE_URL = \"{info.get('base_url', '')}\""
                f"  /  {prefix}_HEADERS (pre-configured auth)"
            )
        api_vars_section = "Per-API variables:\n" + "\n".join(parts)
    elif base_url:
        api_vars_section = f"Available variables:\n  BASE_URL = \"{base_url}\"\n  headers (pre-configured auth)"
    else:
        api_vars_section = "No API-specific variables."

    # Determine api_names display
    if api_names:
        api_names_str = ", ".join(api_names)
    elif api_name:
        api_names_str = api_name
    else:
        api_names_str = "custom/unknown"

    return TOOL_LOGIC_USER_PROMPT.format(
        language=language,
        intent=intent,
        api_names=api_names_str,
        api_vars_section=api_vars_section,
        tool_specs=tool_specs,
    )
