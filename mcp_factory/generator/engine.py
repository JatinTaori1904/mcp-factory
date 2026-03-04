"""MCP Generator Engine — Analyzes prompts and generates production-quality MCP server code.

Follows MCP Best Practices:
- Tool annotations (readOnlyHint, destructiveHint, idempotentHint, openWorldHint)
- Zod schemas with .describe() on every field (TypeScript)
- Pydantic/typed parameters with docstrings (Python)
- Actionable error messages
- Consistent tool naming with prefixes
- Pagination on list operations
- Structured output schemas
- Input validation and security
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import os

from mcp_factory.generator.api_registry import detect_api, generate_env_file, generate_setup_guide, APIInfo
from mcp_factory.generator.api_tools import has_custom_tools, get_ts_tools, get_py_tools
from mcp_factory.generator.docker import generate_dockerfile, generate_dockerignore
from mcp_factory.llm.client import LLMClient
from mcp_factory.llm.prompts import (
    SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, parse_analysis_response,
    TOOL_LOGIC_SYSTEM_PROMPT, build_tool_logic_prompt,
)
from mcp_factory.llm.reviewer import CodeReviewer, CodeReview


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ToolAnnotations:
    """MCP tool annotations per the specification."""
    read_only: bool = True
    destructive: bool = False
    idempotent: bool = True
    open_world: bool = False


@dataclass
class ToolDefinition:
    """Full definition of an MCP tool to generate."""
    name: str
    description: str
    annotations: ToolAnnotations = field(default_factory=ToolAnnotations)
    prefix: str = ""  # e.g. "file_", "db_", "api_"


@dataclass
class PromptAnalysis:
    """Result of analyzing a user's prompt."""
    intent: str
    template: str
    tools: list[ToolDefinition] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    suggested_name: str = ""
    prefix: str = ""
    parameters: dict = field(default_factory=dict)
    api_info: Optional[APIInfo] = None  # detected API details (for api-wrapper template)


@dataclass
class GenerationResult:
    """Result of generating an MCP server."""
    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None
    files_created: list[str] = field(default_factory=list)
    review: Optional[CodeReview] = None  # Stage 3: LLM code review


# ---------------------------------------------------------------------------
# Template catalogue with full tool definitions + annotations
# ---------------------------------------------------------------------------

TEMPLATE_KEYWORDS = {
    "file-reader": [
        "file", "csv", "json", "read", "text", "document", "pdf",
        "excel", "xlsx", "parse", "local", "folder", "directory",
    ],
    "database-connector": [
        "database", "sql", "postgres", "mysql", "sqlite", "query",
        "table", "db", "schema", "record", "insert", "select",
    ],
    "api-wrapper": [
        "api", "rest", "endpoint", "http", "webhook", "request",
        "url", "oauth", "token", "graphql",
        "github", "slack", "stripe", "notion", "discord",
        "openai", "spotify", "google", "twitter", "linear", "jira",
    ],
    "web-scraper": [
        "scrape", "crawl", "website", "web", "html", "extract",
        "browser", "page", "link", "spider",
    ],
    "document-processor": [
        "ocr", "invoice", "receipt", "scan", "extract text", "pdf",
        "image", "classify", "summarize", "contract",
    ],
    "auth-server": [
        "auth", "authentication", "login", "jwt", "token", "session",
        "user", "password", "register", "signup", "oauth", "permission",
        "role", "access", "credential", "identity",
    ],
    "data-pipeline": [
        "pipeline", "etl", "transform", "batch", "job", "schedule",
        "aggregate", "filter", "convert", "stream", "workflow", "ingest",
        "export", "migrate", "normalize", "data processing",
    ],
    "notification-hub": [
        "notification", "notify", "email", "sms", "push", "alert",
        "webhook", "send", "broadcast", "channel", "subscribe",
        "message", "reminder",
    ],
}

TEMPLATE_TOOLS: dict[str, list[ToolDefinition]] = {
    "file-reader": [
        ToolDefinition("file_read", "Read the full contents of a file by path. Supports text-based formats (txt, csv, json, md, xml, yaml, log).",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "file_"),
        ToolDefinition("file_list", "List files and sub-directories at a given path. Returns name, type and size. Supports glob filtering and pagination.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "file_"),
        ToolDefinition("file_search", "Search for a text pattern inside a file. Returns matching lines with line numbers.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "file_"),
        ToolDefinition("file_info", "Get metadata about a file: size, timestamps, extension.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "file_"),
        ToolDefinition("file_write", "Write or append text content to a file. Creates parent directories if needed.",
                        ToolAnnotations(read_only=False, destructive=True, idempotent=False, open_world=False), "file_"),
    ],
    "database-connector": [
        ToolDefinition("db_query", "Execute a read-only SQL SELECT query. Returns JSON results with parameterized queries.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "db_"),
        ToolDefinition("db_execute", "Execute a write SQL statement (INSERT, UPDATE, DELETE). Returns affected row count.",
                        ToolAnnotations(read_only=False, destructive=True, idempotent=False, open_world=False), "db_"),
        ToolDefinition("db_list_tables", "List all tables in the database with row counts.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "db_"),
        ToolDefinition("db_describe_table", "Get the full schema of a table: columns, types, keys.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "db_"),
    ],
    "api-wrapper": [
        ToolDefinition("api_get", "Make an HTTP GET request. Returns status code and body.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=True), "api_"),
        ToolDefinition("api_post", "Make an HTTP POST request with a JSON body.",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=True), "api_"),
        ToolDefinition("api_put", "Make an HTTP PUT request to update a resource.",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=True), "api_"),
        ToolDefinition("api_delete", "Make an HTTP DELETE request to remove a resource.",
                        ToolAnnotations(read_only=False, destructive=True, idempotent=True, open_world=True), "api_"),
    ],
    "web-scraper": [
        ToolDefinition("scrape_page", "Fetch a web page and extract visible text content.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=True), "scrape_"),
        ToolDefinition("scrape_links", "Extract all hyperlinks from a web page.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=True), "scrape_"),
        ToolDefinition("scrape_structured", "Extract structured data from a page using regex patterns.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=True), "scrape_"),
    ],
    "document-processor": [
        ToolDefinition("doc_extract_text", "Extract all text from a document file.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "doc_"),
        ToolDefinition("doc_info", "Get metadata: size, word count, line count, timestamps.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "doc_"),
        ToolDefinition("doc_search", "Search for a pattern inside a document with context.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "doc_"),
    ],
    "auth-server": [
        ToolDefinition("auth_register", "Register a new user with username and password. Returns user ID.",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=False), "auth_"),
        ToolDefinition("auth_login", "Authenticate a user and return a JWT access token.",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=False), "auth_"),
        ToolDefinition("auth_verify", "Verify a JWT token and return the decoded payload.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "auth_"),
        ToolDefinition("auth_refresh", "Refresh an expired JWT token. Returns a new access token.",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=False), "auth_"),
        ToolDefinition("auth_list_users", "List registered users with pagination. Does not expose passwords.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "auth_"),
    ],
    "data-pipeline": [
        ToolDefinition("pipe_ingest", "Ingest data from a file (CSV, JSON, JSONL) into the pipeline.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "pipe_"),
        ToolDefinition("pipe_transform", "Apply transformations: filter rows, rename columns, compute new fields.",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=False), "pipe_"),
        ToolDefinition("pipe_aggregate", "Aggregate data: sum, avg, count, min, max grouped by columns.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "pipe_"),
        ToolDefinition("pipe_export", "Export processed data to a file (CSV or JSON).",
                        ToolAnnotations(read_only=False, destructive=True, idempotent=False, open_world=False), "pipe_"),
        ToolDefinition("pipe_status", "Show current pipeline state: row count, columns, last operation.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "pipe_"),
    ],
    "notification-hub": [
        ToolDefinition("notify_send", "Send a notification via a specified channel (email, webhook, log).",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=True), "notify_"),
        ToolDefinition("notify_list_channels", "List all configured notification channels and their status.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "notify_"),
        ToolDefinition("notify_history", "View notification history with pagination and optional channel filter.",
                        ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False), "notify_"),
        ToolDefinition("notify_webhook", "Send a POST request to a webhook URL with a custom payload.",
                        ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=True), "notify_"),
    ],
}

INTENT_MAP = {
    "file-reader": "Local file processing and analysis",
    "database-connector": "Database querying and management",
    "api-wrapper": "REST API integration",
    "web-scraper": "Web data extraction and scraping",
    "document-processor": "Document processing and text extraction",
    "auth-server": "Authentication server with JWT tokens and user management",
    "data-pipeline": "Data pipeline for ETL, transformations and aggregations",
    "notification-hub": "Multi-channel notification hub (email, webhook, log)",
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class MCPGenerator:
    """Generates production-quality MCP servers following MCP best practices."""

    def __init__(self, provider: str = "ollama", model: Optional[str] = None):
        self.provider = provider
        self.model = model or ("llama3" if provider == "ollama" else "gpt-4")
        self.llm = LLMClient(provider=provider, model=self.model)
        self._llm_used = False  # tracks if last analysis used LLM

    @property
    def llm_available(self) -> bool:
        """Whether the configured LLM is reachable."""
        return self.llm.is_available()

    # ------------------------------------------------------------------
    # Prompt analysis — LLM-first with keyword fallback
    # ------------------------------------------------------------------

    def analyze_prompt(self, prompt: str) -> PromptAnalysis:
        """Analyze a natural language prompt to determine template, tools, and naming.

        Strategy:
          1. Try the LLM for intelligent analysis (custom tools, accurate intent).
          2. If LLM is unavailable or returns bad JSON, fall back to keyword matching.
        Both paths run ``detect_api()`` to enrich with API registry data.
        """
        self._llm_used = False

        # Always detect API from registry (fast, deterministic)
        api_info = detect_api(prompt)

        # ---- Attempt LLM analysis ----
        llm_result = self._analyze_with_llm(prompt, api_info)
        if llm_result is not None:
            self._llm_used = True
            return llm_result

        # ---- Fallback: keyword scoring ----
        return self._analyze_with_keywords(prompt, api_info)

    def _analyze_with_llm(self, prompt: str, api_info: Optional[APIInfo]) -> Optional[PromptAnalysis]:
        """Try to analyze the prompt using the configured LLM.

        Returns ``None`` if the LLM is unavailable or the response is
        unparseable, letting the caller fall back to keyword matching.
        """
        if not self.llm.is_available():
            return None

        user_msg = USER_PROMPT_TEMPLATE.format(prompt=prompt)
        parsed, response = self.llm.chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_msg,
            temperature=0.1,
            max_tokens=2048,
        )

        if parsed is None:
            return None

        # Validate structure
        clean = parse_analysis_response(parsed)
        if clean is None:
            return None

        # Build ToolDefinitions from LLM output
        tools = []
        for t in clean["tools"]:
            tools.append(ToolDefinition(
                name=t["name"],
                description=t["description"],
                annotations=ToolAnnotations(
                    read_only=t["read_only"],
                    destructive=t["destructive"],
                    idempotent=t["idempotent"],
                    open_world=t["open_world"],
                ),
                prefix=clean["prefix"],
            ))

        # If LLM detected an API name, use our registry for rich info
        if clean["api_name"] and api_info is None:
            api_info = detect_api(clean["api_name"])

        return PromptAnalysis(
            intent=clean["intent"],
            template=clean["template"],
            tools=tools,
            tool_names=[t.name for t in tools],
            suggested_name=clean["suggested_name"],
            prefix=clean["prefix"],
            parameters={"original_prompt": prompt, "source": "llm", "model": self.model},
            api_info=api_info,
        )

    def _analyze_with_keywords(self, prompt: str, api_info: Optional[APIInfo]) -> PromptAnalysis:
        """Fallback: analyze the prompt using keyword scoring."""
        prompt_lower = prompt.lower()

        # Score templates by keyword overlap
        scores: dict[str, int] = {}
        for template, keywords in TEMPLATE_KEYWORDS.items():
            scores[template] = sum(1 for kw in keywords if kw in prompt_lower)

        # If a known API was detected, boost api-wrapper score
        if api_info is not None:
            scores["api-wrapper"] = scores.get("api-wrapper", 0) + 10

        best_template = max(scores, key=scores.get)
        if scores[best_template] == 0:
            best_template = "file-reader"

        # Stage 2: Use API-specific tool defs if available
        tools = TEMPLATE_TOOLS.get(best_template, [])
        if best_template == "api-wrapper" and api_info and has_custom_tools(api_info.name):
            from mcp_factory.generator.api_tools import get_custom_tool_defs
            custom_defs = get_custom_tool_defs(api_info.name)
            if custom_defs:
                tools = [
                    ToolDefinition(
                        name=td["name"],
                        description=td["description"],
                        annotations=ToolAnnotations(
                            read_only=td.get("read_only", True),
                            destructive=td.get("destructive", False),
                            idempotent=td.get("idempotent", True),
                            open_world=td.get("open_world", True),
                        ),
                        prefix=td["name"].split("_")[0] + "_" if "_" in td["name"] else "",
                    )
                    for td in custom_defs
                ]

        prefix = tools[0].prefix if tools else ""

        # Generate a clean suggested name — prefer API name if detected
        if api_info:
            suggested_name = f"{api_info.name}-mcp-server"
        else:
            stop_words = {"a", "an", "the", "my", "and", "or", "to", "for", "from", "with", "in", "on"}
            words = [w for w in prompt_lower.split() if w.isalnum() and w not in stop_words][:4]
            suggested_name = "-".join(words)[:30] or "my-mcp-server"

        return PromptAnalysis(
            intent=INTENT_MAP.get(best_template, "General purpose"),
            template=best_template,
            tools=tools,
            tool_names=[t.name for t in tools],
            suggested_name=suggested_name,
            prefix=prefix,
            parameters={"original_prompt": prompt, "source": "keywords"},
            api_info=api_info,
        )

    # ------------------------------------------------------------------
    # Code generation
    # ------------------------------------------------------------------

    def generate(
        self,
        analysis: PromptAnalysis,
        name: str,
        language: str = "typescript",
        output_dir: Path = Path("./output"),
    ) -> GenerationResult:
        """Generate the MCP server code based on the analysis."""
        try:
            server_dir = output_dir / name
            server_dir.mkdir(parents=True, exist_ok=True)

            if language == "typescript":
                files = self._gen_typescript(analysis, name, server_dir)
            elif language == "python":
                files = self._gen_python(analysis, name, server_dir)
            else:
                return GenerationResult(success=False, error=f"Unsupported language: {language}. Use 'typescript' or 'python'.")

            # Stage 3: LLM code review (skipped gracefully if unavailable)
            review = self._review_code(server_dir, language)

            return GenerationResult(success=True, output_path=server_dir, files_created=files, review=review)
        except Exception as e:
            return GenerationResult(success=False, error=str(e))

    def _review_code(self, output_path: Path, language: str) -> Optional[CodeReview]:
        """Run LLM code review on the generated server. Returns None if skipped."""
        if not self.llm:
            return None
        reviewer = CodeReviewer(self.llm)
        review = reviewer.review(output_path, language)
        if not review.reviewed:
            return None
        return review

    # ------------------------------------------------------------------
    # TypeScript generation
    # ------------------------------------------------------------------

    def _gen_typescript(self, analysis: PromptAnalysis, name: str, out: Path) -> list[str]:
        files: list[str] = []

        # ---- package.json ----
        deps = {
            "@modelcontextprotocol/sdk": "^1.0.0",
            "zod": "^3.22.0",
            "dotenv": "^16.4.0",
        }
        if analysis.template == "database-connector":
            deps["better-sqlite3"] = "^11.0.0"
        elif analysis.template == "auth-server":
            deps["jsonwebtoken"] = "^9.0.0"
            deps["bcryptjs"] = "^2.4.3"
            deps["uuid"] = "^9.0.0"
        elif analysis.template == "notification-hub":
            deps["nodemailer"] = "^6.9.0"

        pkg = {
            "name": name,
            "version": "1.0.0",
            "description": f"MCP Server — {analysis.intent}",
            "type": "module",
            "main": "dist/index.js",
            "scripts": {
                "build": "tsc",
                "start": "node dist/index.js",
                "dev": "tsx src/index.ts",
                "inspect": "npx @modelcontextprotocol/inspector"
            },
            "dependencies": deps,
            "devDependencies": {
                "typescript": "^5.3.0",
                "tsx": "^4.7.0",
                "@types/node": "^20.0.0",
            },
        }
        if analysis.template == "database-connector":
            pkg["devDependencies"]["@types/better-sqlite3"] = "^7.6.0"

        (out / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")
        files.append("package.json")

        # ---- tsconfig.json ----
        tsconfig = {
            "compilerOptions": {
                "target": "ES2022",
                "module": "Node16",
                "moduleResolution": "Node16",
                "outDir": "./dist",
                "rootDir": "./src",
                "strict": False,
                "esModuleInterop": True,
                "declaration": True,
                "skipLibCheck": True,
            },
            "include": ["src/**/*"],
        }
        (out / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2), encoding="utf-8")
        files.append("tsconfig.json")

        # ---- .env.example (API-specific if detected) ----
        env_content = generate_env_file(analysis.api_info)
        if analysis.template == "database-connector":
            env_content = "# Database Configuration\n# Never commit .env to git!\n\nDB_PATH=database.db\n"
        elif analysis.template == "auth-server":
            env_content = "# Auth Server Configuration\n# Never commit .env to git!\n\nJWT_SECRET=change-me-to-a-strong-secret\nJWT_EXPIRY_HOURS=24\nUSERS_DB=users.json\n"
        elif analysis.template == "data-pipeline":
            env_content = "# Data Pipeline Configuration\n# Never commit .env to git!\n\nPIPELINE_DATA_DIR=./data\nMAX_ROWS=100000\n"
        elif analysis.template == "notification-hub":
            env_content = "# Notification Hub Configuration\n# Never commit .env to git!\n\nSMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_USER=\nSMTP_PASS=\nDEFAULT_FROM=noreply@example.com\nWEBHOOK_SECRET=\n"
        (out / ".env.example").write_text(env_content, encoding="utf-8")
        files.append(".env.example")

        # ---- .gitignore ----
        (out / ".gitignore").write_text("node_modules/\ndist/\n.env\n*.db\n", encoding="utf-8")
        files.append(".gitignore")

        # ---- SETUP.md (step-by-step API key instructions) ----
        setup_content = generate_setup_guide(analysis.api_info, name, "typescript")
        (out / "SETUP.md").write_text(setup_content, encoding="utf-8")
        files.append("SETUP.md")

        # ---- src/index.ts ----
        src = out / "src"
        src.mkdir(exist_ok=True)

        tools_code = self._ts_tools(analysis)
        auth_code = self._ts_auth_setup(analysis)

        index_ts = f'''#!/usr/bin/env node
/**
 * MCP Server: {name}
 * Template:   {analysis.template}
 * Intent:     {analysis.intent}
 *
 * Generated by MCP Factory — https://github.com/jatin/mcp-factory
 *
 * Best practices applied:
 *  - Tool annotations (readOnlyHint, destructiveHint, idempotentHint, openWorldHint)
 *  - Zod input schemas with .describe() on every field
 *  - Actionable error messages with next-step guidance
 *  - Consistent "{analysis.prefix}" prefixed tool naming
 *  - Pagination on list operations
 */

import {{ McpServer }} from "@modelcontextprotocol/sdk/server/mcp.js";
import {{ StdioServerTransport }} from "@modelcontextprotocol/sdk/server/stdio.js";
import {{ z }} from "zod";
import {{ config }} from "dotenv";

config();  // Load .env file

const server = new McpServer({{
  name: "{name}",
  version: "1.0.0",
}});

// ─── Helpers ────────────────────────────────────────────────────────────────

function errorResponse(message: string, suggestion?: string) {{
  const text = suggestion ? `${{message}}\\n\\nSuggestion: ${{suggestion}}` : message;
  return {{ content: [{{ type: "text" as const, text }}], isError: true }};
}}

// ─── Auth Setup ─────────────────────────────────────────────────────────────
{auth_code}
// ─── Tools ──────────────────────────────────────────────────────────────────
{tools_code}

// ─── Start server ───────────────────────────────────────────────────────────

async function main() {{
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`{name} MCP server running on stdio`);
}}

main().catch((err) => {{
  console.error("Fatal error starting server:", err);
  process.exit(1);
}});
'''
        (src / "index.ts").write_text(index_ts, encoding="utf-8")
        files.append("src/index.ts")

        # ---- README.md ----
        (out / "README.md").write_text(self._readme(analysis, name, "typescript"), encoding="utf-8")
        files.append("README.md")

        # ---- Dockerfile & .dockerignore ----
        (out / "Dockerfile").write_text(generate_dockerfile(name, "typescript", analysis.template), encoding="utf-8")
        files.append("Dockerfile")
        (out / ".dockerignore").write_text(generate_dockerignore("typescript"), encoding="utf-8")
        files.append(".dockerignore")

        return files

    # ------------------------------------------------------------------
    # Python generation
    # ------------------------------------------------------------------

    def _gen_python(self, analysis: PromptAnalysis, name: str, out: Path) -> list[str]:
        files: list[str] = []

        # ---- pyproject.toml ----
        extra_deps = '\n    "python-dotenv>=1.0.0",'
        if analysis.template == "api-wrapper":
            extra_deps += '\n    "httpx>=0.27.0",'
        elif analysis.template == "web-scraper":
            extra_deps += '\n    "httpx>=0.27.0",'
        elif analysis.template == "auth-server":
            extra_deps += '\n    "PyJWT>=2.8.0",\n    "bcrypt>=4.1.0",'
        elif analysis.template == "notification-hub":
            extra_deps += '\n    "httpx>=0.27.0",'

        pyproject = f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "1.0.0"
description = "MCP Server — {analysis.intent}"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0.0",{extra_deps}
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff>=0.1.0",
]
'''
        (out / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        files.append("pyproject.toml")

        # ---- .env.example (API-specific if detected) ----
        env_content = generate_env_file(analysis.api_info)
        if analysis.template == "database-connector":
            env_content = "# Database Configuration\n# Never commit .env to git!\n\nDB_PATH=database.db\n"
        elif analysis.template == "auth-server":
            env_content = "# Auth Server Configuration\n# Never commit .env to git!\n\nJWT_SECRET=change-me-to-a-strong-secret\nJWT_EXPIRY_HOURS=24\nUSERS_DB=users.json\n"
        elif analysis.template == "data-pipeline":
            env_content = "# Data Pipeline Configuration\n# Never commit .env to git!\n\nPIPELINE_DATA_DIR=./data\nMAX_ROWS=100000\n"
        elif analysis.template == "notification-hub":
            env_content = "# Notification Hub Configuration\n# Never commit .env to git!\n\nSMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_USER=\nSMTP_PASS=\nDEFAULT_FROM=noreply@example.com\nWEBHOOK_SECRET=\n"
        (out / ".env.example").write_text(env_content, encoding="utf-8")
        files.append(".env.example")

        # ---- .gitignore ----
        (out / ".gitignore").write_text("__pycache__/\n*.pyc\n.env\nvenv/\n.venv/\ndist/\n*.db\n", encoding="utf-8")
        files.append(".gitignore")

        # ---- SETUP.md (step-by-step API key instructions) ----
        setup_content = generate_setup_guide(analysis.api_info, name, "python")
        (out / "SETUP.md").write_text(setup_content, encoding="utf-8")
        files.append("SETUP.md")

        # ---- server.py ----
        tools_code = self._py_tools(analysis)
        auth_code = self._py_auth_setup(analysis)

        server_py = f'''#!/usr/bin/env python3
"""
MCP Server: {name}
Template:   {analysis.template}
Intent:     {analysis.intent}

Generated by MCP Factory — https://github.com/jatin/mcp-factory

Best practices applied:
  - Typed parameters with descriptive docstrings
  - Actionable error messages with next-step guidance
  - Consistent "{analysis.prefix}" prefixed tool naming
  - Pagination on list operations
  - Input validation
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # Load .env file

mcp = FastMCP("{name}")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _error(message: str, suggestion: str | None = None) -> str:
    """Return an actionable error message."""
    if suggestion:
        return f"{{message}}\\n\\nSuggestion: {{suggestion}}"
    return message


# ─── Auth Setup ──────────────────────────────────────────────────────────────
{auth_code}
# ─── Tools ───────────────────────────────────────────────────────────────────
{tools_code}

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
'''
        (out / "server.py").write_text(server_py, encoding="utf-8")
        files.append("server.py")

        # ---- README.md ----
        (out / "README.md").write_text(self._readme(analysis, name, "python"), encoding="utf-8")
        files.append("README.md")

        # ---- Dockerfile & .dockerignore ----
        (out / "Dockerfile").write_text(generate_dockerfile(name, "python", analysis.template), encoding="utf-8")
        files.append("Dockerfile")
        (out / ".dockerignore").write_text(generate_dockerignore("python"), encoding="utf-8")
        files.append(".dockerignore")

        return files

    # ------------------------------------------------------------------
    # Auth setup code generation
    # ------------------------------------------------------------------

    def _ts_auth_setup(self, analysis: PromptAnalysis) -> str:
        """Generate TypeScript auth setup code based on detected API."""
        api = analysis.api_info

        if api is None:
            if analysis.template == "api-wrapper":
                return '''
const API_KEY = process.env.API_KEY || "";
const BASE_URL = process.env.API_BASE_URL || "https://api.example.com";

if (!API_KEY) {
  console.error("⚠️  No API_KEY found in environment.");
  console.error("   Run: cp .env.example .env — then paste your key.");
}

const headers: Record<string, string> = {
  "Authorization": `Bearer ${API_KEY}`,
  "Content-Type": "application/json",
};
'''
            return "// No API credentials required for this template.\n"

        if api.auth_type == "basic" and api.name == "jira":
            return f'''
const {api.env_var_name} = process.env.{api.env_var_name} || "";
const JIRA_EMAIL = process.env.JIRA_EMAIL || "";
const JIRA_BASE_URL = process.env.JIRA_BASE_URL || "";

if (!{api.env_var_name} || !JIRA_EMAIL || !JIRA_BASE_URL) {{
  console.error("❌ Missing Jira credentials.");
  console.error("   Required env vars: {api.env_var_name}, JIRA_EMAIL, JIRA_BASE_URL");
  console.error("   Get your token at: {api.key_url}");
  console.error("   Then: cp .env.example .env and fill in all values.");
  console.error("   See SETUP.md for step-by-step instructions.");
  process.exit(1);
}}

const AUTH_HEADER = `Basic ${{Buffer.from(`${{JIRA_EMAIL}}:${{{api.env_var_name}}}`).toString("base64")}}`;
const BASE_URL = JIRA_BASE_URL;
const headers: Record<string, string> = {{
  "Authorization": AUTH_HEADER,
  "Content-Type": "application/json",
}};
'''

        # Bearer auth (most common)
        return f'''
const {api.env_var_name} = process.env.{api.env_var_name} || "";

if (!{api.env_var_name}) {{
  console.error("❌ Missing {api.env_var_name}.");
  console.error("   Get your key at: {api.key_url}");
  console.error("   Then: cp .env.example .env and paste your key.");
  console.error("   See SETUP.md for step-by-step instructions.");
  process.exit(1);
}}

const BASE_URL = "{api.base_url}";
const headers: Record<string, string> = {{
  "Authorization": `Bearer ${{{api.env_var_name}}}`,
  "Content-Type": "application/json",
}};
'''

    def _py_auth_setup(self, analysis: PromptAnalysis) -> str:
        """Generate Python auth setup code based on detected API."""
        api = analysis.api_info

        if api is None:
            if analysis.template == "api-wrapper":
                return '''
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("API_BASE_URL", "https://api.example.com")

if not API_KEY:
    print("⚠️  No API_KEY found in environment.", file=sys.stderr)
    print("   Run: cp .env.example .env — then paste your key.", file=sys.stderr)

HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
'''
            return "# No API credentials required for this template.\n"

        if api.auth_type == "basic" and api.name == "jira":
            return f'''
import base64

{api.env_var_name} = os.getenv("{api.env_var_name}", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")

if not {api.env_var_name} or not JIRA_EMAIL or not JIRA_BASE_URL:
    print("❌ Missing Jira credentials.", file=sys.stderr)
    print("   Required: {api.env_var_name}, JIRA_EMAIL, JIRA_BASE_URL", file=sys.stderr)
    print("   Get your token at: {api.key_url}", file=sys.stderr)
    print("   See SETUP.md for step-by-step instructions.", file=sys.stderr)
    sys.exit(1)

_auth = base64.b64encode(f"{{JIRA_EMAIL}}:{{{api.env_var_name}}}".encode()).decode()
BASE_URL = JIRA_BASE_URL
HEADERS: dict[str, str] = {{
    "Authorization": f"Basic {{_auth}}",
    "Content-Type": "application/json",
}}
'''

        # Bearer auth (most common)
        return f'''
{api.env_var_name} = os.getenv("{api.env_var_name}", "")

if not {api.env_var_name}:
    print("❌ Missing {api.env_var_name}.", file=sys.stderr)
    print("   Get your key at: {api.key_url}", file=sys.stderr)
    print("   Then: cp .env.example .env and paste your key.", file=sys.stderr)
    print("   See SETUP.md for step-by-step instructions.", file=sys.stderr)
    sys.exit(1)

BASE_URL = "{api.base_url}"
HEADERS: dict[str, str] = {{
    "Authorization": f"Bearer {{{api.env_var_name}}}",
    "Content-Type": "application/json",
}}
'''

    # ------------------------------------------------------------------
    # TypeScript tool code generation (with annotations)
    # ------------------------------------------------------------------

    def _ts_tools(self, analysis: PromptAnalysis) -> str:
        """Generate TypeScript MCP tools with annotations per best practices."""
        t = analysis.template
        blocks: list[str] = []

        if t == "file-reader":
            blocks.append('''
server.tool(
  "file_read",
  "Read the full contents of a text file by absolute or relative path. Supports txt, csv, json, md, xml, yaml, log and similar text formats.",
  {
    path: z.string().describe("Absolute or relative path to the file to read. Example: './data/report.csv'"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path }) => {
    const fs = await import("fs/promises");
    try {
      const content = await fs.readFile(path, "utf-8");
      return { content: [{ type: "text", text: content }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`File not found: ${path}`, "Check the path with file_list first.");
      if (err.code === "EACCES") return errorResponse(`Permission denied: ${path}`, "Ensure the file is readable by the current user.");
      return errorResponse(`Failed to read file: ${err.message}`);
    }
  }
);

server.tool(
  "file_list",
  "List files and sub-directories at a given path. Returns name, type (file/dir) and size in bytes. Supports optional glob pattern and pagination.",
  {
    path: z.string().describe("Directory path to list. Example: './data'"),
    pattern: z.string().optional().describe("Glob pattern to filter entries. Example: '*.csv'"),
    offset: z.number().int().min(0).optional().describe("Pagination offset (default 0)"),
    limit: z.number().int().min(1).max(200).optional().describe("Max entries to return (default 50, max 200)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path, pattern, offset = 0, limit = 50 }) => {
    const fs = await import("fs/promises");
    const pathMod = await import("path");
    try {
      let entries = await fs.readdir(path, { withFileTypes: true });
      if (pattern) {
        const re = new RegExp("^" + pattern.replace(/\\*/g, ".*").replace(/\\?/g, ".") + "$", "i");
        entries = entries.filter((e) => re.test(e.name));
      }
      const total = entries.length;
      const page = entries.slice(offset, offset + limit);
      const items = await Promise.all(
        page.map(async (e) => {
          const fullPath = pathMod.join(path, e.name);
          try {
            const stat = await fs.stat(fullPath);
            return { name: e.name, type: e.isDirectory() ? "directory" : "file", size: stat.size };
          } catch {
            return { name: e.name, type: e.isDirectory() ? "directory" : "file", size: 0 };
          }
        })
      );
      const result = { total, offset, limit, items };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`Directory not found: ${path}`, "Verify the path exists.");
      return errorResponse(`Failed to list directory: ${err.message}`);
    }
  }
);

server.tool(
  "file_search",
  "Search for a text pattern inside a file and return matching lines with line numbers. Case-insensitive by default.",
  {
    path: z.string().describe("Path to the file to search"),
    query: z.string().describe("Text or pattern to search for"),
    caseSensitive: z.boolean().optional().describe("Enable case-sensitive search (default false)"),
    maxResults: z.number().int().min(1).max(500).optional().describe("Max matches to return (default 50)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path, query, caseSensitive = false, maxResults = 50 }) => {
    const fs = await import("fs/promises");
    try {
      const content = await fs.readFile(path, "utf-8");
      const lines = content.split("\\n");
      const q = caseSensitive ? query : query.toLowerCase();
      const matches = lines
        .map((line, i) => ({ line: i + 1, text: line }))
        .filter(({ text }) => (caseSensitive ? text : text.toLowerCase()).includes(q))
        .slice(0, maxResults);
      if (matches.length === 0) {
        return { content: [{ type: "text", text: `No matches found for "${query}" in ${path}` }] };
      }
      return { content: [{ type: "text", text: JSON.stringify({ matchCount: matches.length, matches }, null, 2) }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`File not found: ${path}`, "Use file_list to find available files.");
      return errorResponse(`Search failed: ${err.message}`);
    }
  }
);

server.tool(
  "file_info",
  "Get metadata about a file: size in bytes, created and modified timestamps, extension.",
  {
    path: z.string().describe("Path to the file"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path }) => {
    const fs = await import("fs/promises");
    try {
      const stat = await fs.stat(path);
      const info = {
        path,
        size: stat.size,
        isDirectory: stat.isDirectory(),
        created: stat.birthtime.toISOString(),
        modified: stat.mtime.toISOString(),
        extension: path.includes(".") ? path.split(".").pop() : null,
      };
      return { content: [{ type: "text", text: JSON.stringify(info, null, 2) }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`Path not found: ${path}`);
      return errorResponse(`Failed to get file info: ${err.message}`);
    }
  }
);

server.tool(
  "file_write",
  "Write or append text content to a file. Creates the file and parent directories if they don't exist.",
  {
    path: z.string().describe("Path to the file to write"),
    content: z.string().describe("Text content to write"),
    append: z.boolean().optional().describe("If true, append to file instead of overwriting (default false)"),
  },
  { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
  async ({ path: filePath, content, append = false }) => {
    const fs = await import("fs/promises");
    const pathMod = await import("path");
    try {
      await fs.mkdir(pathMod.dirname(filePath), { recursive: true });
      if (append) {
        await fs.appendFile(filePath, content, "utf-8");
      } else {
        await fs.writeFile(filePath, content, "utf-8");
      }
      return { content: [{ type: "text", text: `Successfully ${append ? "appended to" : "wrote"} ${filePath}` }] };
    } catch (err: any) {
      return errorResponse(`Failed to write file: ${err.message}`, "Check that the directory is writable.");
    }
  }
);''')

        elif t == "database-connector":
            blocks.append('''
// NOTE: Uses SQLite via better-sqlite3. Change the import for PostgreSQL/MySQL.
import Database from "better-sqlite3";

const DB_PATH = process.env.DB_PATH || "database.db";

function getDb() {
  return new Database(DB_PATH);
}

server.tool(
  "db_query",
  "Execute a read-only SQL SELECT query and return results as JSON. Uses parameterized queries to prevent SQL injection. Returns up to 100 rows by default.",
  {
    sql: z.string().describe("SQL SELECT query. Example: 'SELECT * FROM users WHERE age > ?'"),
    params: z.array(z.union([z.string(), z.number(), z.null()])).optional().describe("Ordered parameters for ? placeholders"),
    limit: z.number().int().min(1).max(1000).optional().describe("Max rows to return (default 100)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ sql, params = [], limit = 100 }) => {
    try {
      if (!sql.trim().toUpperCase().startsWith("SELECT")) {
        return errorResponse("Only SELECT queries allowed in db_query.", "Use db_execute for INSERT/UPDATE/DELETE.");
      }
      const db = getDb();
      const stmt = db.prepare(sql);
      const rows = stmt.all(...params).slice(0, limit);
      db.close();
      return { content: [{ type: "text", text: JSON.stringify({ rowCount: rows.length, rows }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Query failed: ${err.message}`, "Check SQL syntax and table/column names with db_list_tables.");
    }
  }
);

server.tool(
  "db_execute",
  "Execute a write SQL statement (INSERT, UPDATE, DELETE). Returns the number of affected rows. Uses parameterized queries.",
  {
    sql: z.string().describe("SQL statement. Example: 'INSERT INTO users (name, age) VALUES (?, ?)'"),
    params: z.array(z.union([z.string(), z.number(), z.null()])).optional().describe("Ordered parameters for ? placeholders"),
  },
  { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
  async ({ sql, params = [] }) => {
    try {
      const db = getDb();
      const result = db.prepare(sql).run(...params);
      db.close();
      return { content: [{ type: "text", text: JSON.stringify({ changes: result.changes, lastInsertRowid: Number(result.lastInsertRowid) }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Execute failed: ${err.message}`, "Verify table exists with db_list_tables and check column types with db_describe_table.");
    }
  }
);

server.tool(
  "db_list_tables",
  "List all tables in the database with row counts.",
  {},
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async () => {
    try {
      const db = getDb();
      const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all() as { name: string }[];
      const result = tables.map((t) => {
        const count = db.prepare(`SELECT COUNT(*) as count FROM "${t.name}"`).get() as { count: number };
        return { table: t.name, rowCount: count.count };
      });
      db.close();
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list tables: ${err.message}`, `Ensure the database file exists at: ${DB_PATH}`);
    }
  }
);

server.tool(
  "db_describe_table",
  "Get the full schema of a table: column names, data types, nullable, default values, and primary key info.",
  {
    table: z.string().describe("Table name to describe. Use db_list_tables to see available tables."),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ table }) => {
    try {
      const db = getDb();
      const columns = db.prepare(`PRAGMA table_info("${table}")`).all();
      db.close();
      if ((columns as any[]).length === 0) {
        return errorResponse(`Table "${table}" not found.`, "Use db_list_tables to see available tables.");
      }
      return { content: [{ type: "text", text: JSON.stringify({ table, columns }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to describe table: ${err.message}`);
    }
  }
);''')

        elif t == "api-wrapper":
            # Stage 2: Use API-specific tools if available, else LLM, else generic
            api_name = analysis.api_info.name if analysis.api_info else None
            custom_ts = get_ts_tools(api_name) if api_name else None

            if custom_ts:
                # Pre-built API-specific tools (GitHub, Slack, Stripe, etc.)
                blocks.append(custom_ts)
            elif api_name and self._llm_available():
                # LLM-generated custom tools for known APIs without templates
                llm_code = self._generate_tools_with_llm(analysis, "typescript")
                if llm_code:
                    blocks.append(llm_code)
                else:
                    blocks.append(self._generic_ts_api_tools())
            else:
                # Fallback: generic HTTP CRUD tools
                blocks.append(self._generic_ts_api_tools())

        elif t == "web-scraper":
            blocks.append('''
server.tool(
  "scrape_page",
  "Fetch a web page and extract its visible text content by stripping HTML tags. Returns trimmed text up to maxLength characters.",
  {
    url: z.string().url().describe("Full URL of the page to scrape. Example: 'https://example.com'"),
    maxLength: z.number().int().min(100).max(50000).optional().describe("Maximum text length to return (default 5000)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ url, maxLength = 5000 }) => {
    try {
      const res = await fetch(url, { headers: { "User-Agent": "MCPFactory-Scraper/1.0" } });
      if (!res.ok) return errorResponse(`HTTP ${res.status}: ${res.statusText}`, "Check the URL is correct and accessible.");
      const html = await res.text();
      let text = html.replace(/<script[\\s\\S]*?<\\/script>/gi, "").replace(/<style[\\s\\S]*?<\\/style>/gi, "");
      text = text.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      return { content: [{ type: "text", text: text.slice(0, maxLength) }] };
    } catch (err: any) {
      return errorResponse(`Scrape failed: ${err.message}`, "Verify the URL is reachable and correctly formatted.");
    }
  }
);

server.tool(
  "scrape_links",
  "Extract all hyperlinks from a web page. Returns an array of {text, href} objects.",
  {
    url: z.string().url().describe("Full URL of the page to extract links from"),
    limit: z.number().int().min(1).max(500).optional().describe("Max links to return (default 100)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ url, limit = 100 }) => {
    try {
      const res = await fetch(url, { headers: { "User-Agent": "MCPFactory-Scraper/1.0" } });
      if (!res.ok) return errorResponse(`HTTP ${res.status}: ${res.statusText}`);
      const html = await res.text();
      const linkRegex = /<a\\s+[^>]*href=["']([^"']+)["'][^>]*>([\\s\\S]*?)<\\/a>/gi;
      const links: { text: string; href: string }[] = [];
      let match;
      while ((match = linkRegex.exec(html)) !== null && links.length < limit) {
        const href = match[1];
        const text = match[2].replace(/<[^>]+>/g, "").trim();
        if (href && text) links.push({ text, href });
      }
      return { content: [{ type: "text", text: JSON.stringify({ total: links.length, links }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Link extraction failed: ${err.message}`);
    }
  }
);

server.tool(
  "scrape_structured",
  "Extract structured data from a page by matching a regex pattern. Useful for extracting repeated data like prices, titles, etc.",
  {
    url: z.string().url().describe("Full URL of the page"),
    pattern: z.string().describe("Regex pattern with capture groups. Example: '<h2>(.*?)</h2>'"),
    limit: z.number().int().min(1).max(200).optional().describe("Max matches to return (default 50)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ url, pattern, limit = 50 }) => {
    try {
      const res = await fetch(url, { headers: { "User-Agent": "MCPFactory-Scraper/1.0" } });
      if (!res.ok) return errorResponse(`HTTP ${res.status}: ${res.statusText}`);
      const html = await res.text();
      const regex = new RegExp(pattern, "gi");
      const matches: string[] = [];
      let m;
      while ((m = regex.exec(html)) !== null && matches.length < limit) {
        matches.push(m[1] || m[0]);
      }
      return { content: [{ type: "text", text: JSON.stringify({ matchCount: matches.length, matches }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Structured scrape failed: ${err.message}`, "Check the regex pattern syntax.");
    }
  }
);''')

        elif t == "document-processor":
            blocks.append('''
server.tool(
  "doc_extract_text",
  "Extract all text from a document file. Supports txt, md, csv, json, xml, yaml. Returns the full text content.",
  {
    path: z.string().describe("Path to the document file to extract text from"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path }) => {
    const fs = await import("fs/promises");
    try {
      const content = await fs.readFile(path, "utf-8");
      return { content: [{ type: "text", text: content }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`Document not found: ${path}`, "Check the path with doc_info.");
      return errorResponse(`Failed to extract text: ${err.message}`);
    }
  }
);

server.tool(
  "doc_info",
  "Get metadata about a document: file size, word count, line count, extension, and timestamps.",
  {
    path: z.string().describe("Path to the document file"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path }) => {
    const fs = await import("fs/promises");
    try {
      const stat = await fs.stat(path);
      const content = await fs.readFile(path, "utf-8");
      const info = {
        path,
        sizeBytes: stat.size,
        extension: path.includes(".") ? path.split(".").pop() : null,
        lineCount: content.split("\\n").length,
        wordCount: content.split(/\\s+/).filter(Boolean).length,
        charCount: content.length,
        created: stat.birthtime.toISOString(),
        modified: stat.mtime.toISOString(),
      };
      return { content: [{ type: "text", text: JSON.stringify(info, null, 2) }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`Document not found: ${path}`);
      return errorResponse(`Failed to get document info: ${err.message}`);
    }
  }
);

server.tool(
  "doc_search",
  "Search for a text pattern inside a document. Returns matching lines with surrounding context (±2 lines).",
  {
    path: z.string().describe("Path to the document file"),
    query: z.string().describe("Text pattern to search for"),
    contextLines: z.number().int().min(0).max(10).optional().describe("Lines of context around each match (default 2)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path, query, contextLines = 2 }) => {
    const fs = await import("fs/promises");
    try {
      const content = await fs.readFile(path, "utf-8");
      const lines = content.split("\\n");
      const q = query.toLowerCase();
      const matches = lines
        .map((line, i) => ({ line: i + 1, text: line }))
        .filter(({ text }) => text.toLowerCase().includes(q))
        .map(({ line, text }) => {
          const start = Math.max(0, line - 1 - contextLines);
          const end = Math.min(lines.length, line + contextLines);
          const context = lines.slice(start, end).map((l, i) => `${start + i + 1}: ${l}`).join("\\n");
          return { matchLine: line, matchText: text.trim(), context };
        });
      if (matches.length === 0) {
        return { content: [{ type: "text", text: `No matches found for "${query}" in ${path}` }] };
      }
      return { content: [{ type: "text", text: JSON.stringify({ matchCount: matches.length, matches }, null, 2) }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`Document not found: ${path}`, "Use doc_info to check available documents.");
      return errorResponse(`Search failed: ${err.message}`);
    }
  }
);''')

        elif t == "auth-server":
            blocks.append('''
// ─── In-memory user store (swap with a real DB in production) ────────────────
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";
import { v4 as uuidv4 } from "uuid";
import { readFileSync, writeFileSync, existsSync } from "fs";

const JWT_SECRET = process.env.JWT_SECRET || "change-me-to-a-strong-secret";
const JWT_EXPIRY = parseInt(process.env.JWT_EXPIRY_HOURS || "24", 10);
const USERS_FILE = process.env.USERS_DB || "users.json";

interface User { id: string; username: string; hash: string; role: string; createdAt: string; }
let users: User[] = [];
if (existsSync(USERS_FILE)) {
  try { users = JSON.parse(readFileSync(USERS_FILE, "utf-8")); } catch { users = []; }
}
function persist() { writeFileSync(USERS_FILE, JSON.stringify(users, null, 2), "utf-8"); }

server.tool(
  "auth_register",
  "Register a new user with a username, password and optional role. Returns the new user ID. Passwords are bcrypt-hashed before storage.",
  {
    username: z.string().min(3).max(50).describe("Unique username (3-50 characters)"),
    password: z.string().min(8).describe("Password (minimum 8 characters)"),
    role: z.string().optional().describe("User role, e.g. 'admin' or 'user' (default: 'user')"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  async ({ username, password, role }) => {
    if (users.find(u => u.username === username)) {
      return errorResponse(`Username '${username}' already exists.`, "Choose a different username.");
    }
    const hash = await bcrypt.hash(password, 10);
    const user: User = { id: uuidv4(), username, hash, role: role || "user", createdAt: new Date().toISOString() };
    users.push(user);
    persist();
    return { content: [{ type: "text", text: JSON.stringify({ id: user.id, username, role: user.role }) }] };
  }
);

server.tool(
  "auth_login",
  "Authenticate a user by username and password. Returns a JWT access token on success.",
  {
    username: z.string().describe("The username to authenticate"),
    password: z.string().describe("The password to verify"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ username, password }) => {
    const user = users.find(u => u.username === username);
    if (!user) return errorResponse("Invalid username or password.", "Check credentials or register first with auth_register.");
    const valid = await bcrypt.compare(password, user.hash);
    if (!valid) return errorResponse("Invalid username or password.", "Check credentials or reset password.");
    const token = jwt.sign({ sub: user.id, username: user.username, role: user.role }, JWT_SECRET, { expiresIn: `${JWT_EXPIRY}h` });
    return { content: [{ type: "text", text: JSON.stringify({ token, expiresInHours: JWT_EXPIRY }) }] };
  }
);

server.tool(
  "auth_verify",
  "Verify a JWT access token. Returns the decoded payload (user ID, username, role) if valid.",
  {
    token: z.string().describe("The JWT token to verify"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ token }) => {
    try {
      const payload = jwt.verify(token, JWT_SECRET);
      return { content: [{ type: "text", text: JSON.stringify(payload, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Token verification failed: ${err.message}`, "The token may be expired. Use auth_refresh to get a new one.");
    }
  }
);

server.tool(
  "auth_refresh",
  "Refresh a JWT token. Accepts an expired (or still-valid) token and issues a new one with a fresh expiry.",
  {
    token: z.string().describe("The JWT token to refresh (can be expired)"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  async ({ token }) => {
    try {
      const payload: any = jwt.verify(token, JWT_SECRET, { ignoreExpiration: true });
      const newToken = jwt.sign({ sub: payload.sub, username: payload.username, role: payload.role }, JWT_SECRET, { expiresIn: `${JWT_EXPIRY}h` });
      return { content: [{ type: "text", text: JSON.stringify({ token: newToken, expiresInHours: JWT_EXPIRY }) }] };
    } catch (err: any) {
      return errorResponse(`Token refresh failed: ${err.message}`, "Provide a valid JWT token (even if expired).");
    }
  }
);

server.tool(
  "auth_list_users",
  "List registered users with pagination. Returns user ID, username, role, and creation date. Never exposes passwords.",
  {
    offset: z.number().int().min(0).optional().describe("Pagination offset (default 0)"),
    limit: z.number().int().min(1).max(100).optional().describe("Max users to return (default 20, max 100)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ offset = 0, limit = 20 }) => {
    const total = users.length;
    const page = users.slice(offset, offset + limit).map(({ id, username, role, createdAt }) => ({ id, username, role, createdAt }));
    return { content: [{ type: "text", text: JSON.stringify({ total, offset, limit, users: page }, null, 2) }] };
  }
);''')

        elif t == "data-pipeline":
            blocks.append('''
// ─── Pipeline state (in-memory dataset) ─────────────────────────────────────
const fs = await import("fs/promises");
const pathMod = await import("path");

interface PipelineState {
  data: Record<string, any>[];
  columns: string[];
  lastOp: string;
}

let pipeline: PipelineState = { data: [], columns: [], lastOp: "none" };
const DATA_DIR = process.env.PIPELINE_DATA_DIR || "./data";
const MAX_ROWS = parseInt(process.env.MAX_ROWS || "100000", 10);

server.tool(
  "pipe_ingest",
  "Ingest data from a CSV or JSON file into the pipeline. Replaces current pipeline data. Supports CSV with headers and JSON arrays.",
  {
    path: z.string().describe("Path to the data file (CSV or JSON)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ path }) => {
    try {
      const content = await fs.readFile(path, "utf-8");
      const ext = path.split(".").pop()?.toLowerCase();
      let rows: Record<string, any>[] = [];

      if (ext === "json" || ext === "jsonl") {
        if (ext === "jsonl") {
          rows = content.split("\\n").filter(Boolean).map(l => JSON.parse(l));
        } else {
          const parsed = JSON.parse(content);
          rows = Array.isArray(parsed) ? parsed : [parsed];
        }
      } else {
        // CSV parsing (simple: split by comma, first row = headers)
        const lines = content.split("\\n").filter(Boolean);
        if (lines.length === 0) return errorResponse("File is empty.");
        const headers = lines[0].split(",").map(h => h.trim().replace(/^"|"$/g, ""));
        rows = lines.slice(1).map(line => {
          const vals = line.split(",").map(v => v.trim().replace(/^"|"$/g, ""));
          const obj: Record<string, any> = {};
          headers.forEach((h, i) => { obj[h] = vals[i] ?? ""; });
          return obj;
        });
      }

      if (rows.length > MAX_ROWS) rows = rows.slice(0, MAX_ROWS);
      const cols = rows.length > 0 ? Object.keys(rows[0]) : [];
      pipeline = { data: rows, columns: cols, lastOp: `ingest(${rows.length} rows from ${path})` };
      return { content: [{ type: "text", text: JSON.stringify({ rows: rows.length, columns: cols }) }] };
    } catch (err: any) {
      if (err.code === "ENOENT") return errorResponse(`File not found: ${path}`, "Check the path or use a full absolute path.");
      return errorResponse(`Ingest failed: ${err.message}`);
    }
  }
);

server.tool(
  "pipe_transform",
  "Apply transformations to the pipeline data: filter rows by condition, rename columns, or add a computed column.",
  {
    operation: z.enum(["filter", "rename", "compute"]).describe("Transformation type: filter, rename, or compute"),
    column: z.string().describe("Target column name"),
    value: z.string().optional().describe("For filter: value to match. For rename: new column name. For compute: JS expression using 'row' object."),
    operator: z.enum(["eq", "neq", "gt", "lt", "gte", "lte", "contains"]).optional().describe("Comparison operator for filter (default: eq)"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ operation, column, value, operator = "eq" }) => {
    if (pipeline.data.length === 0) return errorResponse("Pipeline is empty.", "Use pipe_ingest to load data first.");
    const before = pipeline.data.length;

    if (operation === "filter") {
      pipeline.data = pipeline.data.filter(row => {
        const v = String(row[column] ?? "");
        const target = value || "";
        switch (operator) {
          case "eq": return v === target;
          case "neq": return v !== target;
          case "gt": return parseFloat(v) > parseFloat(target);
          case "lt": return parseFloat(v) < parseFloat(target);
          case "gte": return parseFloat(v) >= parseFloat(target);
          case "lte": return parseFloat(v) <= parseFloat(target);
          case "contains": return v.toLowerCase().includes(target.toLowerCase());
          default: return v === target;
        }
      });
      pipeline.lastOp = `filter(${column} ${operator} ${value}) → ${pipeline.data.length}/${before} rows`;
    } else if (operation === "rename" && value) {
      pipeline.data = pipeline.data.map(row => {
        const newRow = { ...row };
        if (column in newRow) { newRow[value] = newRow[column]; delete newRow[column]; }
        return newRow;
      });
      pipeline.columns = pipeline.columns.map(c => c === column ? value : c);
      pipeline.lastOp = `rename(${column} → ${value})`;
    } else if (operation === "compute" && value) {
      pipeline.data = pipeline.data.map(row => ({ ...row, [column]: eval(value) }));
      if (!pipeline.columns.includes(column)) pipeline.columns.push(column);
      pipeline.lastOp = `compute(${column} = ${value})`;
    }

    return { content: [{ type: "text", text: JSON.stringify({ rows: pipeline.data.length, columns: pipeline.columns, lastOp: pipeline.lastOp }) }] };
  }
);

server.tool(
  "pipe_aggregate",
  "Aggregate pipeline data: compute sum, avg, count, min, or max, optionally grouped by a column.",
  {
    column: z.string().describe("Column to aggregate"),
    operation: z.enum(["sum", "avg", "count", "min", "max"]).describe("Aggregation operation"),
    groupBy: z.string().optional().describe("Optional column to group results by"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ column, operation, groupBy }) => {
    if (pipeline.data.length === 0) return errorResponse("Pipeline is empty.", "Use pipe_ingest to load data first.");

    const agg = (rows: Record<string, any>[]) => {
      const vals = rows.map(r => parseFloat(r[column])).filter(v => !isNaN(v));
      switch (operation) {
        case "sum": return vals.reduce((a, b) => a + b, 0);
        case "avg": return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
        case "count": return rows.length;
        case "min": return vals.length ? Math.min(...vals) : null;
        case "max": return vals.length ? Math.max(...vals) : null;
      }
    };

    let result: any;
    if (groupBy) {
      const groups: Record<string, Record<string, any>[]> = {};
      pipeline.data.forEach(row => {
        const key = String(row[groupBy] ?? "null");
        (groups[key] ??= []).push(row);
      });
      result = Object.entries(groups).map(([key, rows]) => ({ [groupBy]: key, [operation]: agg(rows) }));
    } else {
      result = { [operation]: agg(pipeline.data), totalRows: pipeline.data.length };
    }

    pipeline.lastOp = `aggregate(${operation}(${column})${groupBy ? ` by ${groupBy}` : ""})`;
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "pipe_export",
  "Export the current pipeline data to a CSV or JSON file.",
  {
    path: z.string().describe("Output file path. Extension determines format (.csv or .json)"),
  },
  { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
  async ({ path }) => {
    if (pipeline.data.length === 0) return errorResponse("Pipeline is empty — nothing to export.", "Use pipe_ingest to load data first.");
    try {
      const ext = path.split(".").pop()?.toLowerCase();
      let content: string;
      if (ext === "csv") {
        const header = pipeline.columns.join(",");
        const rows = pipeline.data.map(row => pipeline.columns.map(c => JSON.stringify(String(row[c] ?? ""))).join(","));
        content = [header, ...rows].join("\\n");
      } else {
        content = JSON.stringify(pipeline.data, null, 2);
      }
      await fs.writeFile(path, content, "utf-8");
      return { content: [{ type: "text", text: JSON.stringify({ exported: pipeline.data.length, path, format: ext }) }] };
    } catch (err: any) {
      return errorResponse(`Export failed: ${err.message}`);
    }
  }
);

server.tool(
  "pipe_status",
  "Show current pipeline state: row count, column names, and last operation performed.",
  {},
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async () => {
    const preview = pipeline.data.slice(0, 3);
    return { content: [{ type: "text", text: JSON.stringify({
      rows: pipeline.data.length,
      columns: pipeline.columns,
      lastOperation: pipeline.lastOp,
      preview,
    }, null, 2) }] };
  }
);''')

        elif t == "notification-hub":
            blocks.append('''
// ─── Notification Hub ───────────────────────────────────────────────────────
import nodemailer from "nodemailer";

const SMTP_HOST = process.env.SMTP_HOST || "smtp.gmail.com";
const SMTP_PORT = parseInt(process.env.SMTP_PORT || "587", 10);
const SMTP_USER = process.env.SMTP_USER || "";
const SMTP_PASS = process.env.SMTP_PASS || "";
const DEFAULT_FROM = process.env.DEFAULT_FROM || "noreply@example.com";

interface NotifyRecord { id: number; channel: string; to: string; subject: string; status: string; timestamp: string; }
const history: NotifyRecord[] = [];
let notifyId = 0;

const transporter = nodemailer.createTransport({
  host: SMTP_HOST, port: SMTP_PORT, secure: SMTP_PORT === 465,
  auth: SMTP_USER ? { user: SMTP_USER, pass: SMTP_PASS } : undefined,
});

const channels: Record<string, { type: string; configured: boolean; description: string }> = {
  email: { type: "email", configured: !!SMTP_USER, description: "Send emails via SMTP" },
  webhook: { type: "webhook", configured: true, description: "POST to any webhook URL" },
  log: { type: "log", configured: true, description: "Log to server console" },
};

server.tool(
  "notify_send",
  "Send a notification via a specified channel (email, webhook, or log). Returns delivery status.",
  {
    channel: z.enum(["email", "webhook", "log"]).describe("Notification channel to use"),
    to: z.string().describe("Recipient: email address, webhook URL, or log label"),
    subject: z.string().describe("Notification subject / title"),
    body: z.string().describe("Notification body / message content"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ channel, to, subject, body }) => {
    const record: NotifyRecord = { id: ++notifyId, channel, to, subject, status: "pending", timestamp: new Date().toISOString() };
    try {
      if (channel === "email") {
        if (!SMTP_USER) return errorResponse("Email not configured.", "Set SMTP_USER and SMTP_PASS in .env");
        await transporter.sendMail({ from: DEFAULT_FROM, to, subject, text: body });
        record.status = "sent";
      } else if (channel === "webhook") {
        const res = await fetch(to, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subject, body, timestamp: record.timestamp }),
        });
        record.status = res.ok ? "sent" : `failed (${res.status})`;
      } else {
        console.log(`[NOTIFY] ${subject}: ${body}`);
        record.status = "logged";
      }
    } catch (err: any) {
      record.status = `error: ${err.message}`;
    }
    history.push(record);
    return { content: [{ type: "text", text: JSON.stringify({ id: record.id, channel, status: record.status }) }] };
  }
);

server.tool(
  "notify_list_channels",
  "List all configured notification channels and whether they are ready to use.",
  {},
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async () => {
    return { content: [{ type: "text", text: JSON.stringify(channels, null, 2) }] };
  }
);

server.tool(
  "notify_history",
  "View notification history with pagination. Optionally filter by channel.",
  {
    channel: z.enum(["email", "webhook", "log"]).optional().describe("Filter by channel (omit for all)"),
    offset: z.number().int().min(0).optional().describe("Pagination offset (default 0)"),
    limit: z.number().int().min(1).max(100).optional().describe("Max records to return (default 20)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  async ({ channel, offset = 0, limit = 20 }) => {
    let filtered = channel ? history.filter(r => r.channel === channel) : history;
    const total = filtered.length;
    const page = filtered.slice(offset, offset + limit);
    return { content: [{ type: "text", text: JSON.stringify({ total, offset, limit, records: page }, null, 2) }] };
  }
);

server.tool(
  "notify_webhook",
  "Send a POST request to a webhook URL with a custom JSON payload. Useful for integrations like Slack, Discord, or custom systems.",
  {
    url: z.string().url().describe("Webhook URL to POST to"),
    payload: z.string().describe("JSON payload string to send"),
    secret: z.string().optional().describe("Optional HMAC secret for signature header"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ url, payload, secret }) => {
    try {
      const hdrs: Record<string, string> = { "Content-Type": "application/json" };
      if (secret) {
        const crypto = await import("crypto");
        const sig = crypto.createHmac("sha256", secret).update(payload).digest("hex");
        hdrs["X-Signature-256"] = `sha256=${sig}`;
      }
      const res = await fetch(url, { method: "POST", headers: hdrs, body: payload });
      const resBody = await res.text();
      const record: NotifyRecord = { id: ++notifyId, channel: "webhook", to: url, subject: "webhook", status: res.ok ? "sent" : `failed (${res.status})`, timestamp: new Date().toISOString() };
      history.push(record);
      return { content: [{ type: "text", text: JSON.stringify({ status: res.status, body: resBody.slice(0, 5000) }) }] };
    } catch (err: any) {
      return errorResponse(`Webhook request failed: ${err.message}`, "Check the URL and network connectivity.");
    }
  }
);''')

        return "\n".join(blocks)

    # ------------------------------------------------------------------
    # Python tool code generation
    # ------------------------------------------------------------------

    def _py_tools(self, analysis: PromptAnalysis) -> str:
        """Generate Python MCP tools following FastMCP best practices."""
        t = analysis.template
        blocks: list[str] = []

        if t == "file-reader":
            blocks.append('''
@mcp.tool()
async def file_read(path: str) -> str:
    """Read the full contents of a text file by absolute or relative path.

    Supports txt, csv, json, md, xml, yaml, log and similar text formats.

    Args:
        path: Absolute or relative path to the file. Example: './data/report.csv'
    """
    p = Path(path)
    if not p.exists():
        return _error(f"File not found: {path}", "Use file_list to discover available files.")
    if not p.is_file():
        return _error(f"Path is not a file: {path}", "Use file_list to see directory contents.")
    try:
        return p.read_text(encoding="utf-8")
    except PermissionError:
        return _error(f"Permission denied: {path}", "Check file permissions.")
    except Exception as e:
        return _error(f"Failed to read file: {e}")


@mcp.tool()
async def file_list(
    path: str,
    pattern: str = "*",
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List files and sub-directories at a given path with pagination.

    Returns name, type (file/dir) and size in bytes as JSON.

    Args:
        path: Directory path to list. Example: './data'
        pattern: Glob pattern to filter entries. Example: '*.csv'
        offset: Pagination offset (default 0)
        limit: Max entries to return, 1-200 (default 50)
    """
    import fnmatch

    p = Path(path)
    if not p.exists():
        return _error(f"Directory not found: {path}", "Verify the path exists.")
    if not p.is_dir():
        return _error(f"Path is not a directory: {path}")
    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        if pattern != "*":
            entries = [e for e in entries if fnmatch.fnmatch(e.name, pattern)]
        total = len(entries)
        page = entries[offset : offset + min(limit, 200)]
        items = []
        for entry in page:
            try:
                size = entry.stat().st_size if entry.is_file() else 0
            except OSError:
                size = 0
            items.append({"name": entry.name, "type": "directory" if entry.is_dir() else "file", "size": size})
        return json.dumps({"total": total, "offset": offset, "limit": limit, "items": items}, indent=2)
    except Exception as e:
        return _error(f"Failed to list directory: {e}")


@mcp.tool()
async def file_search(
    path: str,
    query: str,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> str:
    """Search for a text pattern inside a file and return matching lines with numbers.

    Args:
        path: Path to the file to search
        query: Text or pattern to search for
        case_sensitive: Enable case-sensitive search (default false)
        max_results: Max matches to return, 1-500 (default 50)
    """
    p = Path(path)
    if not p.exists():
        return _error(f"File not found: {path}", "Use file_list to find available files.")
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        q = query if case_sensitive else query.lower()
        matches = [
            {"line": i + 1, "text": line.strip()}
            for i, line in enumerate(lines)
            if q in (line if case_sensitive else line.lower())
        ][:max_results]
        if not matches:
            return f\'No matches found for "{query}" in {path}\'
        return json.dumps({"matchCount": len(matches), "matches": matches}, indent=2)
    except Exception as e:
        return _error(f"Search failed: {e}")


@mcp.tool()
async def file_info(path: str) -> str:
    """Get metadata about a file: size, timestamps, and extension.

    Args:
        path: Path to the file
    """
    p = Path(path)
    if not p.exists():
        return _error(f"Path not found: {path}")
    try:
        stat = p.stat()
        info = {
            "path": str(p.resolve()),
            "size": stat.st_size,
            "isDirectory": p.is_dir(),
            "extension": p.suffix or None,
            "modified": str(stat.st_mtime),
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return _error(f"Failed to get file info: {e}")


@mcp.tool()
async def file_write(path: str, content: str, append: bool = False) -> str:
    """Write or append text content to a file. Creates parent directories if needed.

    Args:
        path: Path to the file to write
        content: Text content to write
        append: If True, append instead of overwriting (default False)
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            p.write_text(content, encoding="utf-8")
        action = "appended to" if append else "wrote"
        return f"Successfully {action} {path}"
    except Exception as e:
        return _error(f"Failed to write file: {e}", "Check that the directory is writable.")
''')

        elif t == "database-connector":
            blocks.append('''
import sqlite3 as _sqlite3

_DB_PATH = os.environ.get("DB_PATH", "database.db")


def _get_db():
    """Get a database connection."""
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    return conn


@mcp.tool()
async def db_query(sql: str, params: list | None = None, limit: int = 100) -> str:
    """Execute a read-only SQL SELECT query and return results as JSON.

    Uses parameterized queries to prevent SQL injection.

    Args:
        sql: SQL SELECT query. Example: 'SELECT * FROM users WHERE age > ?'
        params: Ordered parameters for ? placeholders
        limit: Max rows to return, 1-1000 (default 100)
    """
    if not sql.strip().upper().startswith("SELECT"):
        return _error("Only SELECT queries allowed in db_query.", "Use db_execute for INSERT/UPDATE/DELETE.")
    try:
        conn = _get_db()
        cursor = conn.execute(sql, params or [])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchmany(min(limit, 1000))]
        conn.close()
        return json.dumps({"rowCount": len(rows), "columns": columns, "rows": rows}, indent=2)
    except Exception as e:
        return _error(f"Query failed: {e}", "Check SQL syntax and table names with db_list_tables.")


@mcp.tool()
async def db_execute(sql: str, params: list | None = None) -> str:
    """Execute a write SQL statement (INSERT, UPDATE, DELETE).

    Returns the number of affected rows. Uses parameterized queries.

    Args:
        sql: SQL statement. Example: 'INSERT INTO users (name, age) VALUES (?, ?)'
        params: Ordered parameters for ? placeholders
    """
    try:
        conn = _get_db()
        cursor = conn.execute(sql, params or [])
        conn.commit()
        result = {"changes": cursor.rowcount, "lastRowId": cursor.lastrowid}
        conn.close()
        return json.dumps(result, indent=2)
    except Exception as e:
        return _error(f"Execute failed: {e}", "Verify table exists with db_list_tables.")


@mcp.tool()
async def db_list_tables() -> str:
    """List all tables in the database with row counts."""
    try:
        conn = _get_db()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type=\'table\' AND name NOT LIKE \'sqlite_%\'"
        ).fetchall()
        result = []
        for row in tables:
            name = row[0]
            count = conn.execute(f\'SELECT COUNT(*) FROM "{name}"\').fetchone()[0]
            result.append({"table": name, "rowCount": count})
        conn.close()
        return json.dumps(result, indent=2) if result else "No tables found. The database may be empty."
    except Exception as e:
        return _error(f"Failed to list tables: {e}", f"Ensure database exists at: {_DB_PATH}")


@mcp.tool()
async def db_describe_table(table: str) -> str:
    """Get the full schema of a table: column names, types, nullable, primary key info.

    Args:
        table: Table name. Use db_list_tables to see available tables.
    """
    try:
        conn = _get_db()
        columns = conn.execute(f\'PRAGMA table_info("{table}")\').fetchall()
        conn.close()
        if not columns:
            return _error(f\'Table "{table}" not found.\', "Use db_list_tables to see available tables.")
        cols = [
            {"name": c[1], "type": c[2], "nullable": not c[3], "defaultValue": c[4], "primaryKey": bool(c[5])}
            for c in columns
        ]
        return json.dumps({"table": table, "columns": cols}, indent=2)
    except Exception as e:
        return _error(f"Failed to describe table: {e}")
''')

        elif t == "api-wrapper":
            # Stage 2: Use API-specific tools if available, else LLM, else generic
            api_name = analysis.api_info.name if analysis.api_info else None
            custom_py = get_py_tools(api_name) if api_name else None

            if custom_py:
                # Pre-built API-specific tools (GitHub, Slack, Stripe, etc.)
                blocks.append(custom_py)
            elif api_name and self._llm_available():
                # LLM-generated custom tools for known APIs without templates
                llm_code = self._generate_tools_with_llm(analysis, "python")
                if llm_code:
                    blocks.append(llm_code)
                else:
                    blocks.append(self._generic_py_api_tools())
            else:
                # Fallback: generic HTTP CRUD tools
                blocks.append(self._generic_py_api_tools())

        elif t == "web-scraper":
            blocks.append('''
import httpx
import re as _re


@mcp.tool()
async def scrape_page(url: str, max_length: int = 5000) -> str:
    """Fetch a web page and extract its visible text content by stripping HTML tags.

    Args:
        url: Full URL of the page. Example: 'https://example.com'
        max_length: Maximum text length to return, 100-50000 (default 5000)
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "MCPFactory-Scraper/1.0"}, timeout=30)
        if r.status_code >= 400:
            return _error(f"HTTP {r.status_code}: {r.reason_phrase}", "Check the URL is correct and accessible.")
        text = _re.sub(r"<script[\\s\\S]*?</script>", "", r.text, flags=_re.IGNORECASE)
        text = _re.sub(r"<style[\\s\\S]*?</style>", "", text, flags=_re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"\\s+", " ", text).strip()
        return text[:max(100, min(max_length, 50000))]
    except Exception as e:
        return _error(f"Scrape failed: {e}", "Verify the URL is reachable.")


@mcp.tool()
async def scrape_links(url: str, limit: int = 100) -> str:
    """Extract all hyperlinks from a web page. Returns JSON array of {text, href}.

    Args:
        url: Full URL of the page to extract links from
        limit: Max links to return, 1-500 (default 100)
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "MCPFactory-Scraper/1.0"}, timeout=30)
        links = []
        for match in _re.finditer(r\'<a\\s+[^>]*href=["\\'](.*?)["\\'][^>]*>([\\s\\S]*?)</a>\', r.text, _re.IGNORECASE):
            href, text = match.group(1), _re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if href and text:
                links.append({"text": text, "href": href})
            if len(links) >= limit:
                break
        return json.dumps({"total": len(links), "links": links}, indent=2)
    except Exception as e:
        return _error(f"Link extraction failed: {e}")


@mcp.tool()
async def scrape_structured(url: str, pattern: str, limit: int = 50) -> str:
    """Extract structured data from a page using a regex pattern with capture groups.

    Args:
        url: Full URL of the page
        pattern: Regex pattern with capture groups. Example: '<h2>(.*?)</h2>'
        limit: Max matches to return, 1-200 (default 50)
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "MCPFactory-Scraper/1.0"}, timeout=30)
        matches = []
        for m in _re.finditer(pattern, r.text, _re.IGNORECASE):
            matches.append(m.group(1) if m.lastindex else m.group(0))
            if len(matches) >= limit:
                break
        return json.dumps({"matchCount": len(matches), "matches": matches}, indent=2)
    except Exception as e:
        return _error(f"Scrape failed: {e}", "Check the regex pattern syntax.")
''')

        elif t == "document-processor":
            blocks.append('''
@mcp.tool()
async def doc_extract_text(path: str) -> str:
    """Extract all text from a document file.

    Supports txt, md, csv, json, xml, yaml.

    Args:
        path: Path to the document file
    """
    p = Path(path)
    if not p.exists():
        return _error(f"Document not found: {path}", "Check the path with doc_info.")
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return _error(f"Failed to extract text: {e}")


@mcp.tool()
async def doc_info(path: str) -> str:
    """Get metadata about a document: file size, word count, line count, extension, timestamps.

    Args:
        path: Path to the document file
    """
    p = Path(path)
    if not p.exists():
        return _error(f"Document not found: {path}")
    try:
        stat = p.stat()
        content = p.read_text(encoding="utf-8")
        info = {
            "path": str(p.resolve()),
            "sizeBytes": stat.st_size,
            "extension": p.suffix or None,
            "lineCount": content.count("\\n") + 1,
            "wordCount": len(content.split()),
            "charCount": len(content),
            "modified": str(stat.st_mtime),
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return _error(f"Failed to get document info: {e}")


@mcp.tool()
async def doc_search(path: str, query: str, context_lines: int = 2) -> str:
    """Search for a text pattern inside a document. Returns matching lines with context.

    Args:
        path: Path to the document file
        query: Text pattern to search for
        context_lines: Lines of context around each match, 0-10 (default 2)
    """
    p = Path(path)
    if not p.exists():
        return _error(f"Document not found: {path}", "Use doc_info to check available documents.")
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        q = query.lower()
        matches = []
        for i, line in enumerate(lines):
            if q in line.lower():
                start = max(0, i - context_lines)
                end = min(len(lines), i + 1 + context_lines)
                ctx = "\\n".join(f"{j+1}: {lines[j]}" for j in range(start, end))
                matches.append({"matchLine": i + 1, "matchText": line.strip(), "context": ctx})
        if not matches:
            return f\'No matches found for "{query}" in {path}\'
        return json.dumps({"matchCount": len(matches), "matches": matches}, indent=2)
    except Exception as e:
        return _error(f"Search failed: {e}")
''')

        elif t == "auth-server":
            blocks.append('''
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-to-a-strong-secret")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
USERS_FILE = os.getenv("USERS_DB", "users.json")

# Simple in-memory user store backed by a JSON file
_users: list[dict] = []
if Path(USERS_FILE).exists():
    try:
        _users = json.loads(Path(USERS_FILE).read_text(encoding="utf-8"))
    except Exception:
        _users = []


def _persist_users():
    Path(USERS_FILE).write_text(json.dumps(_users, indent=2), encoding="utf-8")


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with PBKDF2. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return h.hex(), salt


def _create_jwt(payload: dict) -> str:
    """Create a simple HMAC-SHA256 JWT."""
    import base64 as b64
    header = b64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    exp = int(time.time()) + JWT_EXPIRY_HOURS * 3600
    body = b64.urlsafe_b64encode(json.dumps({**payload, "exp": exp}).encode()).rstrip(b"=").decode()
    sig_input = f"{header}.{body}"
    sig = hmac.new(JWT_SECRET.encode(), sig_input.encode(), hashlib.sha256).hexdigest()
    return f"{header}.{body}.{sig}"


def _verify_jwt(token: str, *, ignore_exp: bool = False) -> dict | None:
    """Verify a JWT. Returns payload dict or None."""
    import base64 as b64
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, sig = parts
        expected = hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        padding = 4 - len(body) % 4
        payload = json.loads(b64.urlsafe_b64decode(body + "=" * padding))
        if not ignore_exp and payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


@mcp.tool()
async def auth_register(username: str, password: str, role: str = "user") -> str:
    """Register a new user with username and password. Passwords are hashed with PBKDF2.

    Args:
        username: Unique username (3-50 characters)
        password: Password (minimum 8 characters)
        role: User role, e.g. \'admin\' or \'user\' (default: \'user\')
    """
    if len(username) < 3 or len(username) > 50:
        return _error("Username must be 3-50 characters.")
    if len(password) < 8:
        return _error("Password must be at least 8 characters.")
    if any(u["username"] == username for u in _users):
        return _error(f"Username \'{username}\' already exists.", "Choose a different username.")
    pw_hash, salt = _hash_password(password)
    user = {"id": secrets.token_hex(8), "username": username, "hash": pw_hash, "salt": salt, "role": role, "created_at": datetime.utcnow().isoformat()}
    _users.append(user)
    _persist_users()
    return json.dumps({"id": user["id"], "username": username, "role": role})


@mcp.tool()
async def auth_login(username: str, password: str) -> str:
    """Authenticate a user and return a JWT access token.

    Args:
        username: The username to authenticate
        password: The password to verify
    """
    user = next((u for u in _users if u["username"] == username), None)
    if not user:
        return _error("Invalid username or password.", "Check credentials or register first with auth_register.")
    pw_hash, _ = _hash_password(password, user["salt"])
    if pw_hash != user["hash"]:
        return _error("Invalid username or password.", "Check credentials.")
    token = _create_jwt({"sub": user["id"], "username": user["username"], "role": user["role"]})
    return json.dumps({"token": token, "expires_in_hours": JWT_EXPIRY_HOURS})


@mcp.tool()
async def auth_verify(token: str) -> str:
    """Verify a JWT access token and return the decoded payload.

    Args:
        token: The JWT token to verify
    """
    payload = _verify_jwt(token)
    if payload is None:
        return _error("Token verification failed.", "The token may be expired. Use auth_refresh to get a new one.")
    return json.dumps(payload, indent=2)


@mcp.tool()
async def auth_refresh(token: str) -> str:
    """Refresh a JWT token. Issues a new token with a fresh expiry.

    Args:
        token: The JWT token to refresh (can be expired)
    """
    payload = _verify_jwt(token, ignore_exp=True)
    if payload is None:
        return _error("Token refresh failed.", "Provide a valid JWT token (even if expired).")
    new_token = _create_jwt({"sub": payload["sub"], "username": payload["username"], "role": payload["role"]})
    return json.dumps({"token": new_token, "expires_in_hours": JWT_EXPIRY_HOURS})


@mcp.tool()
async def auth_list_users(offset: int = 0, limit: int = 20) -> str:
    """List registered users with pagination. Never exposes passwords.

    Args:
        offset: Pagination offset (default 0)
        limit: Max users to return, 1-100 (default 20)
    """
    limit = min(max(limit, 1), 100)
    total = len(_users)
    page = [{"id": u["id"], "username": u["username"], "role": u["role"], "created_at": u["created_at"]} for u in _users[offset:offset + limit]]
    return json.dumps({"total": total, "offset": offset, "limit": limit, "users": page}, indent=2)
''')

        elif t == "data-pipeline":
            blocks.append('''
DATA_DIR = os.getenv("PIPELINE_DATA_DIR", "./data")
MAX_ROWS = int(os.getenv("MAX_ROWS", "100000"))

# In-memory pipeline state
_pipeline: dict = {"data": [], "columns": [], "last_op": "none"}


@mcp.tool()
async def pipe_ingest(path: str) -> str:
    """Ingest data from a CSV or JSON file into the pipeline. Replaces current data.

    Supports CSV with headers, JSON arrays, and JSONL.

    Args:
        path: Path to the data file (CSV, JSON, or JSONL)
    """
    import csv as csv_mod
    from io import StringIO

    p = Path(path)
    if not p.exists():
        return _error(f"File not found: {path}", "Check the path or use a full absolute path.")
    try:
        content = p.read_text(encoding="utf-8")
        ext = p.suffix.lower()
        rows: list[dict] = []

        if ext == ".jsonl":
            rows = [json.loads(line) for line in content.splitlines() if line.strip()]
        elif ext == ".json":
            parsed = json.loads(content)
            rows = parsed if isinstance(parsed, list) else [parsed]
        else:  # CSV
            reader = csv_mod.DictReader(StringIO(content))
            rows = list(reader)

        if len(rows) > MAX_ROWS:
            rows = rows[:MAX_ROWS]
        cols = list(rows[0].keys()) if rows else []
        _pipeline["data"] = rows
        _pipeline["columns"] = cols
        _pipeline["last_op"] = f"ingest({len(rows)} rows from {p.name})"
        return json.dumps({"rows": len(rows), "columns": cols})
    except Exception as e:
        return _error(f"Ingest failed: {e}")


@mcp.tool()
async def pipe_transform(operation: str, column: str, value: str = "", operator: str = "eq") -> str:
    """Apply transformations to the pipeline data.

    Operations:
      - filter: Keep rows where column matches value using operator
      - rename: Rename column to value
      - compute: Add/overwrite column with a Python expression (use \'row\' dict)

    Args:
        operation: One of \'filter\', \'rename\', \'compute\'
        column: Target column name
        value: For filter: match value. For rename: new name. For compute: Python expression.
        operator: Comparison for filter: eq, neq, gt, lt, gte, lte, contains (default: eq)
    """
    if not _pipeline["data"]:
        return _error("Pipeline is empty.", "Use pipe_ingest to load data first.")
    data = _pipeline["data"]
    before = len(data)

    if operation == "filter":
        def match(row: dict) -> bool:
            v = str(row.get(column, ""))
            if operator == "eq": return v == value
            if operator == "neq": return v != value
            try:
                fv, ft = float(v), float(value)
                if operator == "gt": return fv > ft
                if operator == "lt": return fv < ft
                if operator == "gte": return fv >= ft
                if operator == "lte": return fv <= ft
            except ValueError:
                return False
            if operator == "contains": return value.lower() in v.lower()
            return v == value
        _pipeline["data"] = [r for r in data if match(r)]
        _pipeline["last_op"] = f"filter({column} {operator} {value}) → {len(_pipeline[\'data\'])}/{before} rows"
    elif operation == "rename" and value:
        for row in data:
            if column in row:
                row[value] = row.pop(column)
        _pipeline["columns"] = [value if c == column else c for c in _pipeline["columns"]]
        _pipeline["last_op"] = f"rename({column} → {value})"
    elif operation == "compute" and value:
        return _error("Compute is not supported in safe mode.", "Manually add computed columns.")
    else:
        return _error(f"Unknown operation: {operation}", "Use filter, rename, or compute.")

    return json.dumps({"rows": len(_pipeline["data"]), "columns": _pipeline["columns"], "last_op": _pipeline["last_op"]})


@mcp.tool()
async def pipe_aggregate(column: str, operation: str, group_by: str = "") -> str:
    """Aggregate pipeline data: sum, avg, count, min, or max, optionally grouped by a column.

    Args:
        column: Column to aggregate
        operation: One of \'sum\', \'avg\', \'count\', \'min\', \'max\'
        group_by: Optional column to group results by
    """
    if not _pipeline["data"]:
        return _error("Pipeline is empty.", "Use pipe_ingest to load data first.")

    def _agg(rows: list[dict]) -> float | int | None:
        if operation == "count":
            return len(rows)
        vals = []
        for r in rows:
            try:
                vals.append(float(r.get(column, 0)))
            except (ValueError, TypeError):
                pass
        if not vals:
            return None
        if operation == "sum": return sum(vals)
        if operation == "avg": return sum(vals) / len(vals)
        if operation == "min": return min(vals)
        if operation == "max": return max(vals)
        return None

    if group_by:
        groups: dict[str, list[dict]] = {}
        for row in _pipeline["data"]:
            key = str(row.get(group_by, "null"))
            groups.setdefault(key, []).append(row)
        result = [{group_by: k, operation: _agg(v)} for k, v in groups.items()]
    else:
        result = {operation: _agg(_pipeline["data"]), "total_rows": len(_pipeline["data"])}

    _pipeline["last_op"] = f"aggregate({operation}({column}){f\' by {group_by}\' if group_by else \'\'})"
    return json.dumps(result, indent=2)


@mcp.tool()
async def pipe_export(path: str) -> str:
    """Export the current pipeline data to a CSV or JSON file.

    Args:
        path: Output file path. Extension determines format (.csv or .json)
    """
    import csv as csv_mod

    if not _pipeline["data"]:
        return _error("Pipeline is empty — nothing to export.", "Use pipe_ingest to load data first.")
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        ext = p.suffix.lower()
        if ext == ".csv":
            with p.open("w", newline="", encoding="utf-8") as f:
                writer = csv_mod.DictWriter(f, fieldnames=_pipeline["columns"])
                writer.writeheader()
                writer.writerows(_pipeline["data"])
        else:
            p.write_text(json.dumps(_pipeline["data"], indent=2), encoding="utf-8")
        return json.dumps({"exported": len(_pipeline["data"]), "path": str(p), "format": ext.lstrip(".")})
    except Exception as e:
        return _error(f"Export failed: {e}")


@mcp.tool()
async def pipe_status() -> str:
    """Show current pipeline state: row count, column names, last operation, and a 3-row preview."""
    preview = _pipeline["data"][:3]
    return json.dumps({
        "rows": len(_pipeline["data"]),
        "columns": _pipeline["columns"],
        "last_operation": _pipeline["last_op"],
        "preview": preview,
    }, indent=2)
''')

        elif t == "notification-hub":
            blocks.append('''
import httpx

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
DEFAULT_FROM = os.getenv("DEFAULT_FROM", "noreply@example.com")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

_history: list[dict] = []
_notify_id = 0

_channels = {
    "email": {"type": "email", "configured": bool(SMTP_USER), "description": "Send emails via SMTP"},
    "webhook": {"type": "webhook", "configured": True, "description": "POST to any webhook URL"},
    "log": {"type": "log", "configured": True, "description": "Log to server console"},
}


@mcp.tool()
async def notify_send(channel: str, to: str, subject: str, body: str) -> str:
    """Send a notification via a specified channel (email, webhook, or log).

    Args:
        channel: Notification channel — \'email\', \'webhook\', or \'log\'
        to: Recipient: email address, webhook URL, or log label
        subject: Notification subject / title
        body: Notification body / message content
    """
    global _notify_id
    _notify_id += 1
    record = {"id": _notify_id, "channel": channel, "to": to, "subject": subject, "status": "pending", "timestamp": datetime.utcnow().isoformat() if \'datetime\' in dir() else ""}
    try:
        if channel == "email":
            if not SMTP_USER:
                return _error("Email not configured.", "Set SMTP_USER and SMTP_PASS in .env")
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = DEFAULT_FROM
            msg["To"] = to
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.starttls()
                smtp.login(SMTP_USER, SMTP_PASS)
                smtp.send_message(msg)
            record["status"] = "sent"
        elif channel == "webhook":
            async with httpx.AsyncClient() as client:
                r = await client.post(to, json={"subject": subject, "body": body, "timestamp": record["timestamp"]}, timeout=15)
            record["status"] = "sent" if r.is_success else f"failed ({r.status_code})"
        elif channel == "log":
            print(f"[NOTIFY] {subject}: {body}")
            record["status"] = "logged"
        else:
            return _error(f"Unknown channel: {channel}", "Use email, webhook, or log.")
    except Exception as e:
        record["status"] = f"error: {e}"
    _history.append(record)
    return json.dumps({"id": record["id"], "channel": channel, "status": record["status"]})


@mcp.tool()
async def notify_list_channels() -> str:
    """List all configured notification channels and whether they are ready to use."""
    return json.dumps(_channels, indent=2)


@mcp.tool()
async def notify_history(channel: str = "", offset: int = 0, limit: int = 20) -> str:
    """View notification history with pagination and optional channel filter.

    Args:
        channel: Filter by channel (omit or empty for all)
        offset: Pagination offset (default 0)
        limit: Max records to return, 1-100 (default 20)
    """
    limit = min(max(limit, 1), 100)
    filtered = [r for r in _history if not channel or r["channel"] == channel]
    total = len(filtered)
    page = filtered[offset:offset + limit]
    return json.dumps({"total": total, "offset": offset, "limit": limit, "records": page}, indent=2)


@mcp.tool()
async def notify_webhook(url: str, payload: str, secret: str = "") -> str:
    """Send a POST request to a webhook URL with a custom payload. Supports HMAC-SHA256 signatures.

    Args:
        url: Webhook URL to POST to
        payload: JSON payload string to send
        secret: Optional HMAC secret for X-Signature-256 header
    """
    global _notify_id
    try:
        import hashlib as _hashlib, hmac as _hmac
        hdrs: dict[str, str] = {"Content-Type": "application/json"}
        if secret:
            sig = _hmac.new(secret.encode(), payload.encode(), _hashlib.sha256).hexdigest()
            hdrs["X-Signature-256"] = f"sha256={sig}"
        async with httpx.AsyncClient() as client:
            r = await client.post(url, content=payload, headers=hdrs, timeout=15)
        _notify_id += 1
        _history.append({"id": _notify_id, "channel": "webhook", "to": url, "subject": "webhook", "status": "sent" if r.is_success else f"failed ({r.status_code})", "timestamp": ""})
        return json.dumps({"status": r.status_code, "body": r.text[:5000]})
    except Exception as e:
        return _error(f"Webhook request failed: {e}", "Check the URL and network connectivity.")
''')

        return "\n".join(blocks)

    # ------------------------------------------------------------------
    # Generic API tools (fallback when no API-specific templates exist)
    # ------------------------------------------------------------------

    def _generic_ts_api_tools(self) -> str:
        """Return generic HTTP CRUD tool code for TypeScript."""
        return '''
server.tool(
  "api_get",
  "Make an HTTP GET request to an API endpoint. Returns status code and body. Supports custom headers and query parameters.",
  {
    url: z.string().describe("Full URL or path appended to BASE_URL. Example: '/users' or 'https://api.example.com/users'"),
    extraHeaders: z.record(z.string()).optional().describe("Additional request headers"),
    queryParams: z.record(z.string()).optional().describe("URL query parameters as key-value pairs"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ url, extraHeaders, queryParams }) => {
    try {
      const fullUrl = new URL(url.startsWith("http") ? url : `${BASE_URL}${url}`);
      if (queryParams) Object.entries(queryParams).forEach(([k, v]) => fullUrl.searchParams.set(k, v));
      const h = extraHeaders ? { ...headers, ...extraHeaders } : headers;
      const res = await fetch(fullUrl.toString(), { headers: h });
      const body = await res.text();
      return { content: [{ type: "text", text: JSON.stringify({ status: res.status, body: body.slice(0, 10000) }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`GET request failed: ${err.message}`, "Check the URL format and network connectivity.");
    }
  }
);

server.tool(
  "api_post",
  "Make an HTTP POST request with a JSON body. Returns status code and response body.",
  {
    url: z.string().describe("Full URL or path appended to BASE_URL"),
    body: z.string().describe("JSON request body. Example: '{\\\\"name\\\\": \\\\"test\\\\"}'"),
    extraHeaders: z.record(z.string()).optional().describe("Additional request headers"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ url, body, extraHeaders }) => {
    try {
      const fullUrl = url.startsWith("http") ? url : `${BASE_URL}${url}`;
      const h = extraHeaders ? { ...headers, ...extraHeaders } : headers;
      const res = await fetch(fullUrl, { method: "POST", body, headers: h });
      const data = await res.text();
      return { content: [{ type: "text", text: JSON.stringify({ status: res.status, body: data.slice(0, 10000) }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`POST request failed: ${err.message}`);
    }
  }
);

server.tool(
  "api_put",
  "Make an HTTP PUT request to update a resource. Returns status code and response body.",
  {
    url: z.string().describe("Full URL or path appended to BASE_URL"),
    body: z.string().describe("JSON request body"),
    extraHeaders: z.record(z.string()).optional().describe("Additional request headers"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ url, body, extraHeaders }) => {
    try {
      const fullUrl = url.startsWith("http") ? url : `${BASE_URL}${url}`;
      const h = extraHeaders ? { ...headers, ...extraHeaders } : headers;
      const res = await fetch(fullUrl, { method: "PUT", body, headers: h });
      const data = await res.text();
      return { content: [{ type: "text", text: JSON.stringify({ status: res.status, body: data.slice(0, 10000) }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`PUT request failed: ${err.message}`);
    }
  }
);

server.tool(
  "api_delete",
  "Make an HTTP DELETE request to remove a resource. Returns status code and response body.",
  {
    url: z.string().describe("Full URL or path to the resource to delete"),
    extraHeaders: z.record(z.string()).optional().describe("Additional request headers"),
  },
  { readOnlyHint: false, destructiveHint: true, idempotentHint: true, openWorldHint: true },
  async ({ url, extraHeaders }) => {
    try {
      const fullUrl = url.startsWith("http") ? url : `${BASE_URL}${url}`;
      const h = extraHeaders ? { ...headers, ...extraHeaders } : headers;
      const res = await fetch(fullUrl, { method: "DELETE", headers: h });
      const data = await res.text();
      return { content: [{ type: "text", text: JSON.stringify({ status: res.status, body: data.slice(0, 10000) }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`DELETE request failed: ${err.message}`);
    }
  }
);'''

    def _generic_py_api_tools(self) -> str:
        """Return generic HTTP CRUD tool code for Python."""
        return '''
import httpx


@mcp.tool()
async def api_get(url: str, extra_headers: dict[str, str] | None = None, query_params: dict[str, str] | None = None) -> str:
    """Make an HTTP GET request. Returns status code and body.

    Args:
        url: Full URL or path appended to BASE_URL. Example: '/users'
        extra_headers: Additional request headers
        query_params: URL query parameters as key-value pairs
    """
    try:
        full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
        h = {**HEADERS, **(extra_headers or {})}
        async with httpx.AsyncClient() as client:
            r = await client.get(full_url, headers=h, params=query_params, timeout=30)
        return json.dumps({"status": r.status_code, "body": r.text[:10000]}, indent=2)
    except Exception as e:
        return _error(f"GET request failed: {e}", "Check the URL format and network connectivity.")


@mcp.tool()
async def api_post(url: str, body: str, extra_headers: dict[str, str] | None = None) -> str:
    """Make an HTTP POST request with a JSON body.

    Args:
        url: Full URL or path appended to BASE_URL
        body: JSON request body string
        extra_headers: Additional request headers
    """
    try:
        full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
        h = {**HEADERS, **(extra_headers or {})}
        async with httpx.AsyncClient() as client:
            r = await client.post(full_url, content=body, headers=h, timeout=30)
        return json.dumps({"status": r.status_code, "body": r.text[:10000]}, indent=2)
    except Exception as e:
        return _error(f"POST request failed: {e}")


@mcp.tool()
async def api_put(url: str, body: str, extra_headers: dict[str, str] | None = None) -> str:
    """Make an HTTP PUT request to update a resource.

    Args:
        url: Full URL or path appended to BASE_URL
        body: JSON request body string
        extra_headers: Additional request headers
    """
    try:
        full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
        h = {**HEADERS, **(extra_headers or {})}
        async with httpx.AsyncClient() as client:
            r = await client.put(full_url, content=body, headers=h, timeout=30)
        return json.dumps({"status": r.status_code, "body": r.text[:10000]}, indent=2)
    except Exception as e:
        return _error(f"PUT request failed: {e}")


@mcp.tool()
async def api_delete(url: str, extra_headers: dict[str, str] | None = None) -> str:
    """Make an HTTP DELETE request to remove a resource.

    Args:
        url: Full URL or path to the resource to delete
        extra_headers: Additional request headers
    """
    try:
        full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
        h = {**HEADERS, **(extra_headers or {})}
        async with httpx.AsyncClient() as client:
            r = await client.delete(full_url, headers=h, timeout=30)
        return json.dumps({"status": r.status_code, "body": r.text[:10000]}, indent=2)
    except Exception as e:
        return _error(f"DELETE request failed: {e}")
'''

    # ------------------------------------------------------------------
    # LLM-powered tool generation (Stage 2)
    # ------------------------------------------------------------------

    def _llm_available(self) -> bool:
        """Check if LLM client is configured and reachable."""
        return self.llm is not None and self.llm.is_available()

    def _generate_tools_with_llm(self, analysis: PromptAnalysis, language: str) -> Optional[str]:
        """Ask the LLM to generate custom tool implementations.

        Returns generated code string, or None if LLM fails.
        """
        if not self.llm:
            return None

        api_name = analysis.api_info.name if analysis.api_info else None
        base_url = analysis.api_info.base_url if analysis.api_info else "https://api.example.com"

        tool_dicts = [
            {"name": t.name, "description": t.description,
             "read_only": t.annotations.read_only, "destructive": t.annotations.destructive}
            for t in analysis.tools
        ]

        user_prompt = build_tool_logic_prompt(
            language=language,
            intent=analysis.intent,
            api_name=api_name,
            base_url=base_url,
            tools=tool_dicts,
        )

        try:
            result = self.llm.chat_json(
                system=TOOL_LOGIC_SYSTEM_PROMPT,
                user=user_prompt,
            )
            if not result or "tools" not in result:
                return None

            # Concatenate all tool code blocks
            code_blocks = []
            for tool_entry in result["tools"]:
                code = tool_entry.get("code", "").strip()
                if code:
                    code_blocks.append(code)

            return "\n\n".join(code_blocks) if code_blocks else None

        except Exception:
            return None

    # ------------------------------------------------------------------
    # README generation
    # ------------------------------------------------------------------

    def _readme(self, analysis: PromptAnalysis, name: str, language: str) -> str:
        install = "npm install" if language == "typescript" else "pip install -e ."
        run = "npm start" if language == "typescript" else "python server.py"
        dev = "npm run dev" if language == "typescript" else "python server.py"
        inspect_cmd = "npx @modelcontextprotocol/inspector" if language == "typescript" else "npx @modelcontextprotocol/inspector python server.py"
        entry = "dist/index.js" if language == "typescript" else "server.py"
        runtime = "node" if language == "typescript" else "python"

        if language == "typescript":
            prereqs_section = """## Prerequisites

Before you begin, make sure you have these installed:

| Requirement | Minimum Version | Check Command | Install |
|-------------|----------------|---------------|---------|
| **Node.js** | 18.0+ | `node --version` | [nodejs.org](https://nodejs.org) |
| **npm** | 9.0+ | `npm --version` | Comes with Node.js |

> **Tip:** Run `mcpfactory doctor` to verify your environment if you installed via MCP Factory.
"""
        else:
            prereqs_section = """## Prerequisites

Before you begin, make sure you have these installed:

| Requirement | Minimum Version | Check Command | Install |
|-------------|----------------|---------------|---------|
| **Python** | 3.10+ | `python --version` | [python.org](https://python.org) |
| **pip** | latest | `pip --version` | Comes with Python |

> **Tip:** Run `mcpfactory doctor` to verify your environment if you installed via MCP Factory.
"""

        tools_table = "\n".join(
            f"| `{t.name}` | {'Read-only' if t.annotations.read_only else 'Read/Write'} | {t.description[:80]} |"
            for t in analysis.tools
        )

        return f"""# {name}

> Generated by [MCP Factory](https://github.com/jatin/mcp-factory) — Local-first MCP server generator

## Overview

**{analysis.intent}**

- **Template:** `{analysis.template}`
- **Language:** {language}
- **Transport:** stdio (local)
- **Privacy:** 100% local — no data leaves your machine

## Tools

| Tool | Mode | Description |
|------|------|-------------|
{tools_table}

{prereqs_section}
## Quick Start

```bash
# 1. Install dependencies
{install}

# 2. Run the server
{run}

# 3. Test with MCP Inspector
{inspect_cmd}
```

## Development

```bash
# Run in dev mode
{dev}
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

{"## 🔑 API Key Setup" + chr(10) + chr(10) + f"This server requires a **{analysis.api_info.display_name}** API key." + chr(10) + chr(10) + f"| Variable | Where to get it | Free tier? |" + chr(10) + f"|----------|----------------|------------|" + chr(10) + f"| `{analysis.api_info.env_var_name}` | [{analysis.api_info.key_url}]({analysis.api_info.key_url}) | {'✅ Yes' if analysis.api_info.free_tier else '❌ No'} |" + chr(10) + chr(10) + "👉 See `SETUP.md` for detailed step-by-step instructions." + chr(10) if analysis.api_info else ""}
## Add to Claude Desktop

Edit `claude_desktop_config.json`:

```json
{{
  "mcpServers": {{
    "{name}": {{
      "command": "{runtime}",
      "args": ["{entry}"]
    }}
  }}
}}
```

## MCP Best Practices Applied

- Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`)
- Consistent `{analysis.prefix}` prefixed tool naming for discoverability
- Zod/Pydantic input validation with descriptive field documentation
- Actionable error messages with next-step suggestions
- Pagination on list operations
- Secrets via environment variables (never hardcoded)

## Privacy

This MCP server runs **100% locally**. No telemetry, no cloud, no data collection.

---

*Built with [MCP Factory](https://github.com/jatin/mcp-factory) — The local-first MCP server generator*
"""
