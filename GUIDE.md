# MCP Factory — User Guide

A simple, step-by-step guide to build your own MCP servers using MCP Factory.

---

## What is MCP Factory?

MCP Factory lets you create **MCP servers** by just describing what you want in plain English. No need to write boilerplate code, config files, or Dockerfiles — it does everything for you.

**What is an MCP server?**
An MCP (Model Context Protocol) server gives AI assistants like Claude superpowers — the ability to read your files, query databases, call APIs, and more. Think of it as a plugin that Claude can use.

---

## Step 1: Install MCP Factory

Open your terminal (Command Prompt, PowerShell, or any terminal) and run:

```bash
pip install "prompt2mcp[web]"
```

> **Note:** You need Python 3.10 or newer. Check with `python --version`.

To verify it installed correctly:

```bash
mcpfactory --help
```

You should see a list of commands like `create`, `templates`, `list-servers`, etc.

---

## Step 2: Create Your First MCP Server

Just describe what you want your server to do:

```bash
mcpfactory create "read and search local files"
```

That's it! MCP Factory will:
1. Analyze your prompt
2. Pick the right template
3. Ask follow-up questions if needed (like file formats, operations, etc.)
4. Generate a complete, working MCP server
5. Auto-register it with Claude Desktop

### More Examples

```bash
# A server that connects to your PostgreSQL database
mcpfactory create "connect to my PostgreSQL database and run queries"

# A server that wraps the GitHub API
mcpfactory create "create tools for the GitHub API"

# A server that scrapes web pages
mcpfactory create "scrape product prices from websites"

# A server that processes PDF documents
mcpfactory create "extract text from PDF invoices and summarize them"

# A server that sends notifications
mcpfactory create "send notifications via email and webhooks"
```

### Options You Can Use

| Option | Short | What it does | Default |
|--------|-------|-------------|---------|
| `--name` | `-n` | Give your server a custom name | auto-generated |
| `--lang` | `-l` | Choose language: `typescript` or `python` | typescript |
| `--output` | `-o` | Where to save the generated files | `./output` |
| `--no-interactive` | | Skip follow-up questions | interactive |

**Example with options:**

```bash
mcpfactory create "read CSV files" --name csv-reader --lang python --output ./my-servers
```

---

## Step 3: Build the Generated Server

After creating, MCP Factory tells you the output folder. Go there and build it:

**For TypeScript servers (default):**

```bash
cd output/your-server-name
npm install
npm run build
```

**For Python servers:**

```bash
cd output/your-server-name
pip install -r requirements.txt
```

---

## Step 4: Connect to Claude Desktop

MCP Factory **automatically** adds your server to Claude Desktop's config when you create it. But here's how to do it manually if needed:

### Automatic (recommended)

```bash
# Add a single server
mcpfactory config-add your-server-name

# Or export all servers at once
mcpfactory config-export
```

### Manual

1. Open Claude Desktop
2. Go to **Settings → Developer**
3. Click **"Edit Config"**
4. Add your server:

```json
{
  "mcpServers": {
    "your-server-name": {
      "command": "node",
      "args": ["C:\\full\\path\\to\\output\\your-server-name\\dist\\index.js"]
    }
  }
}
```

> **Important:** Use the **full absolute path** to `dist/index.js` (TypeScript) or `server.py` (Python). Relative paths won't work.

### After Adding

1. **Quit Claude Desktop completely** (right-click the system tray icon → Quit)
2. **Reopen** Claude Desktop
3. Go to **Settings → Developer** — you should see your server with a **"running"** badge
4. Start a **New Chat** — you'll see a tools icon (🔨) at the bottom
5. Ask Claude to use your tools!

---

## Step 5: Use Your Server in Claude

Once connected, just chat with Claude naturally. It will automatically use your MCP tools when relevant.

**Examples:**

If you created a file-reader server:
> "List all files in my Documents folder"
> "Read the contents of report.csv"
> "Search for 'revenue' in my spreadsheet"

If you created a GitHub API server:
> "Show me the issues in my repo"
> "List my GitHub repositories"

If you created a database server:
> "Show me all tables in the database"
> "Run a query to find users who signed up this week"

Claude will ask for your **permission** before using each tool. Click **"Allow"** to let it proceed.

---

## Managing Your Servers

### See all servers you've created

```bash
mcpfactory list-servers
```

### Get details about a specific server

```bash
mcpfactory info your-server-name
```

### Delete a server

```bash
mcpfactory delete your-server-name
```

### Remove from Claude Desktop config

```bash
mcpfactory config-remove your-server-name
```

### See current Claude Desktop config

```bash
mcpfactory config-show
```

---

## Available Templates

MCP Factory picks the right template automatically, but here's what's available:

| Template | Use Case | Example Prompt |
|----------|----------|---------------|
| **file-reader** | Read, list, search local files | "Read my CSV files and answer questions" |
| **database-connector** | SQL databases (SQLite, PostgreSQL, MySQL) | "Connect to my PostgreSQL database" |
| **api-wrapper** | Wrap any REST API as MCP tools | "Create tools for the GitHub API" |
| **web-scraper** | Scrape and extract web data | "Scrape product prices from Amazon" |
| **document-processor** | Process PDFs, DOCX files | "Extract text from PDF invoices" |
| **auth-server** | JWT authentication & user management | "Build a login system with JWT tokens" |
| **data-pipeline** | ETL data processing | "Ingest CSV, filter rows, export results" |
| **notification-hub** | Send emails, webhooks, logs | "Send notifications via email and webhook" |

To see this list anytime:

```bash
mcpfactory templates
```

---

## Supported APIs (Auto-Detected)

When you mention any of these APIs in your prompt, MCP Factory automatically generates the right auth code, environment variables, and setup instructions:

| API | Free? | What you need |
|-----|-------|--------------|
| GitHub | Yes | `GITHUB_TOKEN` — get from [github.com/settings/tokens](https://github.com/settings/tokens) |
| Slack | Yes | `SLACK_BOT_TOKEN` — get from [api.slack.com](https://api.slack.com/apps) |
| Notion | Yes | `NOTION_API_KEY` — get from [notion.so/my-integrations](https://www.notion.so/my-integrations) |
| Stripe | Yes | `STRIPE_SECRET_KEY` — get from [dashboard.stripe.com](https://dashboard.stripe.com/apikeys) |
| Discord | Yes | `DISCORD_BOT_TOKEN` — get from [discord.com/developers](https://discord.com/developers/applications) |
| Spotify | Yes | `SPOTIFY_CLIENT_ID` — get from [developer.spotify.com](https://developer.spotify.com/dashboard) |
| Google APIs | Yes | `GOOGLE_API_KEY` — get from [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| Linear | Yes | `LINEAR_API_KEY` — get from [linear.app/settings/api](https://linear.app/settings/api) |
| Jira | Yes | `JIRA_API_TOKEN` — get from [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |
| OpenAI | No | `OPENAI_API_KEY` — get from [platform.openai.com](https://platform.openai.com/api-keys) |
| Twitter / X | No | `TWITTER_BEARER_TOKEN` — get from [developer.x.com](https://developer.x.com/en/portal/dashboard) |

API keys go in the `.env` file inside your generated server folder. There's also a `.env.example` showing what's needed.

To see this list anytime:

```bash
mcpfactory supported-apis
```

---

## Web Dashboard (Optional)

MCP Factory also comes with a visual web dashboard:

```bash
mcpfactory web
```

This opens a browser UI where you can:
- Create servers by filling out a form
- View and manage all your servers
- See generated tools and their details

---

## Docker Support

Every generated server comes with a `Dockerfile`. To run your server in a container:

```bash
cd output/your-server-name
docker build -t your-server-name .
docker run -it your-server-name
```

---

## Troubleshooting

### "No servers added" in Claude Desktop
- Make sure you used the **full absolute path** in the config
- Quit Claude Desktop from the **system tray** (not just closing the window) and reopen it

### Server shows "running" but no tools icon
- Start a **new chat** — the tools icon only appears in new conversations
- Look for a small icon (🔨, wrench, or plug) near the `+` button in the chat input

### Build fails with TypeScript errors
- Make sure you ran `npm install` before `npm run build`
- Check that Node.js 18+ is installed: `node --version`

### API server says "unauthorized"
- Create a `.env` file in the server folder with your API key
- Check the `SETUP.md` file in the server folder for step-by-step instructions

### Server not connecting
- Check that `node` is in your system PATH: `node --version`
- Try using the full path to node in the config: `"command": "C:\\Program Files\\nodejs\\node.exe"`

---

## Quick Reference

```bash
# Install
pip install "prompt2mcp[web]"

# Create a server
mcpfactory create "your description here"

# Build it
cd output/server-name && npm install && npm run build

# List your servers
mcpfactory list-servers

# See templates
mcpfactory templates

# See supported APIs
mcpfactory supported-apis

# Launch web dashboard
mcpfactory web

# Add to Claude Desktop
mcpfactory config-add server-name

# Show Claude config
mcpfactory config-show
```

---

## Links

- **PyPI:** [pypi.org/project/prompt2mcp](https://pypi.org/project/prompt2mcp/)
- **GitHub:** [github.com/JatinTaori1904/mcp-factory](https://github.com/JatinTaori1904/mcp-factory)
- **MCP Docs:** [modelcontextprotocol.io](https://modelcontextprotocol.io/)

---

*Built with MCP Factory by [Jatin](https://github.com/JatinTaori1904)*
