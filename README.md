# MCP Factory 🏭

[![PyPI version](https://img.shields.io/pypi/v/prompt2mcp.svg)](https://pypi.org/project/prompt2mcp/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Build MCP servers from natural language prompts — local-first, privacy-focused

## What is MCP Factory?

MCP Factory is a CLI tool that generates fully functional [Model Context Protocol](https://modelcontextprotocol.io/) servers from plain English descriptions. Describe what you want, get production-ready TypeScript or Python code — complete with tool annotations, auth setup, and MCP best practices.

## Installation

```bash
pip install prompt2mcp
```

Or install from source:

```bash
git clone https://github.com/jatin/mcp-factory.git
cd mcp-factory
pip install -e ".[dev]"
```

## Quick Start

```bash
# Create your first MCP server
mcpfactory create "Read my CSV files and answer questions about the data"

# Generate a GitHub API server (auto-detects API, generates auth + SETUP.md)
mcpfactory create "Create tools for the GitHub API" --name github-tools

# Python server with interactive refinement
mcpfactory create "Build a Slack bot" --lang python --interactive

# List your servers
mcpfactory list-servers

# See available templates
mcpfactory templates

# See supported APIs with auto-setup
mcpfactory supported-apis
```

## Features

### 🎯 Prompt-to-Server
Describe what you want → get a working MCP server with tools, schemas, and error handling.

### 📦 8 Built-in Templates

| Template | Description | Example Prompt |
|----------|-------------|----------------|
| **File Reader** | Read, search, list local files | *"Read and search through my project files"* |
| **Database Connector** | Query SQL/NoSQL databases | *"Connect to PostgreSQL and run queries"* |
| **API Wrapper** | Wrap any REST API with tools | *"Create tools for the GitHub API"* |
| **Web Scraper** | Extract data from websites | *"Scrape product prices from websites"* |
| **Document Processor** | Parse PDFs, DOCX, Markdown | *"Extract text from PDF documents"* |
| **Auth Server** | JWT auth, user management, RBAC | *"Build an authentication server with JWT"* |
| **Data Pipeline** | ETL, transform, aggregate data | *"ETL pipeline to ingest CSV and transform"* |
| **Notification Hub** | Email, webhook, multi-channel alerts | *"Send notifications via email and webhooks"* |

### 🤖 LLM-Powered Intelligence

MCP Factory uses a multi-tier generation pipeline:

1. **LLM Prompt Analysis** — Understands your intent using Ollama (local) or OpenAI/Claude (cloud)
2. **API-Specific Tool Generation** — Pre-built tool implementations for 5 APIs (GitHub, Slack, Stripe, Notion, Discord)
3. **LLM Code Review** — Auto-reviews generated code for quality, security, and MCP compliance
4. **Interactive Mode** — Asks follow-up questions for vague prompts to generate better servers
5. **Keyword Fallback** — Works fully offline without any LLM when needed

### 🔑 11 APIs with Auto-Setup

When your prompt mentions a supported API, MCP Factory automatically generates:

- **`.env.example`** — API-specific environment variables
- **`SETUP.md`** — Step-by-step guide to get API keys
- **Auth validation** — Startup checks with actionable error messages
- **Pre-configured headers** — Bearer, Basic, or OAuth2

| API | Auth | Env Variable | Free Tier |
|-----|------|-------------|-----------|
| GitHub | Bearer | `GITHUB_TOKEN` | ✅ |
| Slack | Bearer | `SLACK_BOT_TOKEN` | ✅ |
| OpenAI | Bearer | `OPENAI_API_KEY` | ❌ |
| Stripe | Bearer | `STRIPE_SECRET_KEY` | ✅ |
| Notion | Bearer | `NOTION_API_KEY` | ✅ |
| Spotify | OAuth2 | `SPOTIFY_CLIENT_ID` | ✅ |
| Google | Bearer | `GOOGLE_API_KEY` | ✅ |
| Twitter/X | Bearer | `TWITTER_BEARER_TOKEN` | ✅ |
| Discord | Bearer | `DISCORD_BOT_TOKEN` | ✅ |
| Linear | Bearer | `LINEAR_API_KEY` | ✅ |
| Jira | Basic | `JIRA_API_TOKEN` | ✅ |

### 💬 Interactive Mode

For vague prompts, MCP Factory asks targeted follow-up questions to generate better servers:

```bash
mcpfactory create "build something for files" --interactive

# MCP Factory asks:
# 1. What file types? (code, documents, data files, all)
# 2. What operations? (read, write, search, all)
# → Generates a refined, specific server
```

### ✅ MCP Best Practices

Generated servers follow [MCP best practices](https://modelcontextprotocol.io/):

- **Tool annotations** — `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`
- **Prefixed naming** — Consistent tool prefixes (e.g., `gh_`, `slack_`)
- **Schema descriptions** — Zod `.describe()` / Pydantic `Field(description=...)` on every parameter
- **Actionable errors** — Errors include what went wrong + what to do next
- **Pagination** — List operations support `cursor`/`maxResults` parameters
- **Secrets via env vars** — Never hardcoded, always from `.env`

### 🌍 TypeScript & Python

Generate servers in your preferred language:

```bash
mcpfactory create "..." --lang typescript  # default
mcpfactory create "..." --lang python
```

### 🔒 Privacy First

- All generated code stays on your local filesystem
- Server metadata stored in local SQLite (`~/.mcpfactory/servers.db`)
- No telemetry, no cloud, no data collection
- LLM calls can use local Ollama models for complete offline privacy

## CLI Reference

```
mcpfactory create <prompt>     Create a new MCP server
  --name, -n        Server name
  --lang, -l        Language: typescript | python (default: typescript)
  --output, -o      Output directory (default: ./output)
  --provider, -p    LLM provider: ollama | openai (default: ollama)
  --model, -m       Model name (e.g., llama3, gpt-4)
  --interactive      Enable follow-up questions for vague prompts
  --no-interactive   Skip interactive refinement

mcpfactory list-servers        List all generated servers
mcpfactory templates           Show available templates
mcpfactory supported-apis      Show APIs with auto-setup
```

## Architecture

```
User Prompt
    │
    ├─► Interactive Refinement (follow-up questions if vague)
    │
    ├─► LLM Prompt Analyzer (Ollama/OpenAI/Claude)
    │       │
    │       └─► Keyword Fallback (offline)
    │
    ├─► API Detector (11 APIs with auth info)
    │
    ├─► Template Matcher (8 templates)
    │
    ├─► Code Generator
    │       ├─► Pre-built API tools (GitHub, Slack, Stripe, Notion, Discord)
    │       ├─► LLM tool generation
    │       └─► Template-based generation
    │
    ├─► Validator (syntax + structure checks)
    │
    ├─► LLM Code Reviewer (quality, security, MCP compliance)
    │
    └─► Local Storage (SQLite)
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
```

## License

[MIT](LICENSE)
