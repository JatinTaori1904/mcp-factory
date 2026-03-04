<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/JatinTaori1904/mcp-factory/ci.yml?branch=main&style=for-the-badge&label=CI&color=%2300B894" alt="CI">
  <img src="https://img.shields.io/pypi/v/prompt2mcp?color=%236C5CE7&label=PyPI&style=for-the-badge" alt="PyPI">
  <img src="https://img.shields.io/pypi/pyversions/prompt2mcp?color=%2300B894&style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-%2300B894?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/MCP-Compatible-%236C5CE7?style=for-the-badge" alt="MCP">
  <img src="https://img.shields.io/pypi/dm/prompt2mcp?color=%23e17055&label=Downloads&style=for-the-badge" alt="Downloads">
</p>

<p align="center">
  <b>Generate production-ready MCP servers from natural language prompts.</b><br>
  <sub>8 templates · 11 APIs · TypeScript & Python · Docker · Web Dashboard · Claude Desktop integration</sub>
</p>

---

# MCP Factory

MCP Factory is a CLI + web tool that takes a plain English description and generates a fully working [Model Context Protocol](https://modelcontextprotocol.io/) server — with tools, types, error handling, validation, code review, and best practices baked in.

```bash
pip install "prompt2mcp[web]"
mcpfactory create "a server that reads CSV files and runs SQL queries on them"
```

**No boilerplate. No manual wiring. Just describe what you want.**

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Web Dashboard](#web-dashboard)
- [Features](#features)
- [Claude Desktop Integration](#claude-desktop-integration)
- [CLI Reference](#cli-reference)
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Prerequisites

| Requirement | Minimum Version | Why | Check |
|-------------|----------------|-----|-------|
| **Python** | 3.10+ | Runs MCP Factory itself | `python --version` |
| **pip** | latest | Installs MCP Factory | `pip --version` |
| **Node.js** | 18+ | Needed to build/run TypeScript servers | `node --version` |
| **npm** | 9+ | Installs TypeScript server dependencies | `npm --version` |

> **Note:** Node.js and npm are only required if you generate **TypeScript** servers (the default). Python-only servers don't need them.
>
> After installing, run `mcpfactory doctor` to verify everything is set up correctly.

---

## Installation

**From PyPI (recommended):**

```bash
# Core CLI only
pip install prompt2mcp

# With web dashboard
pip install "prompt2mcp[web]"
```

**From source:**

```bash
git clone https://github.com/JatinTaori1904/mcp-factory.git
cd mcp-factory
pip install -e ".[dev,web]"
```

---

## Quick Start

### 1. Create your first server

```bash
mcpfactory create "github repo manager with issues and PRs"
```

This generates a complete MCP server in `./output/github-repo-manager/` with:

```
github-repo-manager/
├── src/
│   └── index.ts          # Full MCP server with tools
├── package.json           # Dependencies configured
├── tsconfig.json          # TypeScript config
├── .env.example           # Environment variables needed
├── Dockerfile             # Container-ready deployment
├── .dockerignore          # Docker build exclusions
└── README.md              # Usage instructions
```

### 2. Run the generated server

```bash
cd output/github-repo-manager
npm install
npm start
```

### 2b. Or run with Docker

```bash
cd output/github-repo-manager
docker build -t github-repo-manager .
docker run -i --env-file .env github-repo-manager
```

### 3. Connect to Claude Desktop

```bash
mcpfactory config-add github-repo-manager
# → Automatically adds the server to Claude Desktop's config
```

That's it — your server is now available as tools in Claude.

---

## More Examples

```bash
# Python server for Slack
mcpfactory create "slack bot that posts messages and manages channels" --lang python

# Use OpenAI for smarter analysis
mcpfactory create "stripe payment processor with refunds" --provider openai --model gpt-4

# Interactive mode — MCP Factory asks follow-up questions
mcpfactory create "something for files" --interactive

# Custom name and output directory
mcpfactory create "notion wiki manager" --name my-wiki --output ./servers

# Browse all available templates
mcpfactory templates

# See supported APIs with auth details
mcpfactory supported-apis
```

---

## Web Dashboard

MCP Factory includes a built-in web dashboard for managing your servers visually.

```bash
mcpfactory web
# → Opens at http://localhost:8000
```

**Dashboard features:**

| Page | What it does |
|------|-------------|
| **Home** | Overview with stats — servers created, templates, APIs, total tools |
| **Create** | Generate servers from the browser with real-time feedback |
| **API Registry** | Browse all 11 supported APIs with auth info and free tier status |
| **Config** | Manage Claude Desktop integration — add/remove servers, export config |

The dashboard uses a modern glassmorphism UI with dark theme, gradient accents, and smooth animations.

```bash
# Custom host/port
mcpfactory web --host 0.0.0.0 --port 3000
```

---

## Features

### 🧠 Smart Prompt Analysis

A 5-tier LLM pipeline ensures your prompt is always understood:

| Tier | Provider | When |
|------|----------|------|
| 1 | **Ollama** (local) | Default — private, free, offline |
| 2 | **OpenAI** | `--provider openai` |
| 3 | **Claude** | `--provider claude` |
| 4 | **Keyword fallback** | Auto if all LLMs unavailable |
| 5 | **Default template** | Ultimate safety net |

### 📦 8 Built-in Templates

| Template | Use Case | Tools Generated |
|----------|----------|-----------------|
| `file-reader` | Read, search, and watch files | `file_read`, `file_search`, `file_watch` |
| `database-connector` | Query PostgreSQL, MySQL, SQLite | `db_query`, `db_list_tables`, `db_describe` |
| `api-wrapper` | Wrap any REST API | `api_get`, `api_post`, `api_list` |
| `web-scraper` | Scrape and parse web content | `scrape_url`, `extract_links`, `parse_html` |
| `document-processor` | Parse PDFs, DOCX, Markdown | `doc_parse`, `doc_convert`, `doc_extract` |
| `auth-server` | OAuth2 / JWT authentication | `auth_login`, `auth_verify`, `auth_refresh` |
| `data-pipeline` | ETL: extract, transform, load | `pipeline_extract`, `pipeline_transform`, `pipeline_load` |
| `notification-hub` | Send via email, Slack, webhooks | `notify_send`, `notify_broadcast`, `notify_schedule` |

### 🔌 11 APIs with Auto-Setup

When your prompt mentions a supported API, MCP Factory auto-generates **pre-built, production-ready tools** — not generic wrappers.

| API | Auth | Env Variable | Free Tier | Pre-built Tools |
|-----|------|-------------|-----------|-----------------|
| **GitHub** | Token | `GITHUB_TOKEN` | ✅ | `gh_list_repos`, `gh_create_issue`, `gh_get_pr` |
| **Slack** | Bot Token | `SLACK_BOT_TOKEN` | ✅ | `slack_post`, `slack_list_channels`, `slack_reply` |
| **OpenAI** | API Key | `OPENAI_API_KEY` | ❌ | `openai_complete`, `openai_embed` |
| **Stripe** | Secret Key | `STRIPE_SECRET_KEY` | ✅ Test | `stripe_create_charge`, `stripe_list_customers` |
| **Notion** | Integration | `NOTION_API_KEY` | ✅ | `notion_query_db`, `notion_create_page` |
| **Spotify** | OAuth2 | `SPOTIFY_CLIENT_ID` | ✅ | — |
| **Google** | API Key | `GOOGLE_API_KEY` | ✅ Ltd | — |
| **Twitter** | Bearer | `TWITTER_BEARER_TOKEN` | ✅ Ltd | — |
| **Discord** | Bot Token | `DISCORD_BOT_TOKEN` | ✅ | `discord_send`, `discord_list_channels` |
| **Linear** | API Key | `LINEAR_API_KEY` | ✅ | — |
| **Jira** | API Token | `JIRA_API_TOKEN` | ✅ | — |

### 💬 Interactive Mode

For vague prompts, MCP Factory asks targeted follow-up questions:

```bash
mcpfactory create "build something for files" --interactive

# MCP Factory asks:
# 1. What file types? (code, documents, data files, all)
# 2. What operations? (read, write, search, all)
# → Generates a refined, specific server
```

### ✅ MCP Best Practices

Every generated server follows the [official MCP best practices](https://modelcontextprotocol.io/):

- **Tool annotations** — `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`
- **Prefixed naming** — Consistent tool prefixes (`gh_`, `slack_`, `stripe_`)
- **Schema descriptions** — Zod `.describe()` / Pydantic `Field(description=...)` on every parameter
- **Actionable errors** — Errors include what went wrong + what to do next
- **Pagination** — List operations support `cursor` / `maxResults`
- **Secrets via env vars** — Never hardcoded, always from `.env`

### 🔍 LLM Code Review

After generation, an LLM reviews the code for:

- Security issues (hardcoded secrets, injection risks)
- MCP compliance (missing annotations, naming violations)
- Code quality (error handling, edge cases)
- Performance (unnecessary loops, missing pagination)

### 🌍 TypeScript & Python

```bash
mcpfactory create "..." --lang typescript  # default
mcpfactory create "..." --lang python
```

Both languages get the same quality: proper types, error handling, and MCP compliance.

### 🔒 Privacy First

- All code stays on your local filesystem
- Metadata in local SQLite (`~/.mcpfactory/servers.db`)
- No telemetry, no cloud, no tracking
- Use Ollama for 100% offline, private generation

---

## Claude Desktop Integration

MCP Factory can automatically configure your servers for Claude Desktop:

```bash
# Add a server to Claude Desktop
mcpfactory config-add my-server

# Remove a server
mcpfactory config-remove my-server

# Show current Claude config
mcpfactory config-show

# Export full configuration
mcpfactory config-export
```

The `config-add` command:
1. Locates your Claude Desktop config file
2. Adds the server entry with the correct command and args
3. Your server immediately appears in Claude's tool list

---

## CLI Reference

```
COMMAND                        DESCRIPTION
─────────────────────────────────────────────────────────────
mcpfactory create <prompt>     Generate a new MCP server
  -n, --name                     Server name (auto-generated if omitted)
  -l, --lang                     typescript | python (default: typescript)
  -o, --output                   Output directory (default: ./output)
  -p, --provider                 LLM: ollama | openai | claude (default: ollama)
  -m, --model                    Model name (e.g., llama3, gpt-4)
  --interactive / --no-interactive  Follow-up questions for vague prompts

mcpfactory list-servers        List all generated servers
mcpfactory templates           Show available templates
mcpfactory supported-apis      Browse APIs with auth details
mcpfactory info <name>         Show details for a specific server
mcpfactory delete <name>       Delete a server

mcpfactory config-add <name>   Add server to Claude Desktop
mcpfactory config-remove <name> Remove server from Claude Desktop
mcpfactory config-show         Show Claude Desktop config
mcpfactory config-export       Export full configuration

mcpfactory web                 Launch web dashboard
  --host                         Bind address (default: 127.0.0.1)
  --port                         Port number (default: 8000)
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  User Input                      │
│         (CLI prompt or Web Dashboard)            │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │  Interactive Refinement  │  ← Follow-up questions
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   LLM Prompt Analyzer   │  ← Ollama / OpenAI / Claude
          │   (Keyword Fallback)    │  ← Offline safety net
          └────────────┬────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────────┐
  │   API    │  │ Template │  │  LLM Tool    │
  │ Detector │  │ Matcher  │  │  Generator   │
  │ (11 APIs)│  │(8 templ) │  │              │
  └────┬─────┘  └────┬─────┘  └──────┬───────┘
       │              │               │
       └──────────────┼───────────────┘
                      ▼
          ┌───────────────────────┐
          │    Code Generator     │
          │  ├─ Pre-built API tools│
          │  ├─ LLM-generated tools│
          │  └─ Template code      │
          └───────────┬───────────┘
                      │
          ┌───────────▼───────────┐
          │   Validator + Linter  │  ← Syntax + structure checks
          └───────────┬───────────┘
                      │
          ┌───────────▼───────────┐
          │   LLM Code Reviewer   │  ← Security, quality, MCP
          └───────────┬───────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
  ┌──────────┐ ┌───────────┐ ┌──────────┐
  │  File    │ │  SQLite   │ │  Claude  │
  │  System  │ │  Storage  │ │  Config  │
  └──────────┘ └───────────┘ └──────────┘
```

---

## Development

```bash
# Clone and install
git clone https://github.com/JatinTaori1904/mcp-factory.git
cd mcp-factory
pip install -e ".[dev,web]"

# Run all tests (142 tests)
pytest

# Run with verbose output
pytest -v

# Lint
ruff check .
```

### Project Structure

```
mcp-factory/
├── mcp_factory/
│   ├── cli/              # Typer CLI commands
│   ├── generator/        # Core engine (prompt analysis, code gen, review)
│   ├── storage/          # SQLite database layer
│   └── config/           # Claude Desktop config management
├── web/
│   ├── app.py            # FastAPI application
│   ├── templates/        # Jinja2 HTML templates
│   └── static/           # CSS with glassmorphism theme
├── tests/
│   └── test_generator.py # 142 tests across 21 test classes
├── pyproject.toml        # Build config (Hatchling)
└── README.md
```

---

## Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `pip install -e ".[dev,web]"`
4. Make your changes and add tests
5. Run the test suite: `pytest`
6. Submit a pull request

---

## License

[MIT](LICENSE) — Built by [Jatin Taori](https://github.com/JatinTaori1904)
