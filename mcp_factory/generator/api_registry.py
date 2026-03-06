"""API Registry — Detects which API the user wants and generates
setup instructions with correct env vars, key URLs, and auth code.

Supports 11 popular APIs out of the box. For unknown APIs, falls back
to generic API_KEY / API_BASE_URL configuration.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class APIInfo:
    """Everything needed to authenticate with and set up a specific API."""
    name: str                       # e.g. "github"
    display_name: str               # e.g. "GitHub"
    base_url: str                   # e.g. "https://api.github.com"
    auth_type: str                  # "bearer" | "basic" | "oauth2" | "query_param"
    env_var_name: str               # e.g. "GITHUB_TOKEN"
    key_url: str                    # URL where user can create a key
    docs_url: str                   # API documentation URL
    free_tier: bool                 # Whether a free tier exists
    scopes: list[str] = field(default_factory=list)
    setup_steps: list[str] = field(default_factory=list)
    rate_limit: str = ""
    notes: str = ""
    extra_env_vars: dict[str, str] = field(default_factory=dict)  # additional env vars needed


# ---------------------------------------------------------------------------
# Registry of 11 popular APIs
# ---------------------------------------------------------------------------

API_REGISTRY: dict[str, APIInfo] = {

    "github": APIInfo(
        name="github",
        display_name="GitHub",
        base_url="https://api.github.com",
        auth_type="bearer",
        env_var_name="GITHUB_TOKEN",
        key_url="https://github.com/settings/tokens",
        docs_url="https://docs.github.com/en/rest",
        free_tier=True,
        scopes=["repo", "read:user", "read:org"],
        setup_steps=[
            "Go to https://github.com/settings/tokens",
            "Click 'Generate new token' → 'Generate new token (classic)'",
            "Give it a descriptive name like 'MCP Server'",
            "Select scopes: repo, read:user, read:org",
            "Click 'Generate token'",
            "Copy the token (starts with ghp_...)",
            "Paste it in your .env file as GITHUB_TOKEN=ghp_your_token_here",
        ],
        rate_limit="5,000 requests/hour (authenticated)",
        notes="Classic tokens are simplest. Fine-grained tokens offer more control but require more setup.",
    ),

    "slack": APIInfo(
        name="slack",
        display_name="Slack",
        base_url="https://slack.com/api",
        auth_type="bearer",
        env_var_name="SLACK_BOT_TOKEN",
        key_url="https://api.slack.com/apps",
        docs_url="https://api.slack.com/methods",
        free_tier=True,
        scopes=["channels:read", "chat:write", "users:read"],
        setup_steps=[
            "Go to https://api.slack.com/apps",
            "Click 'Create New App' → 'From scratch'",
            "Name your app and select your workspace",
            "Go to 'OAuth & Permissions' in the sidebar",
            "Under 'Bot Token Scopes', add: channels:read, chat:write, users:read",
            "Click 'Install to Workspace' at the top of the page",
            "Copy the 'Bot User OAuth Token' (starts with xoxb-...)",
            "Paste it in your .env file as SLACK_BOT_TOKEN=xoxb-your-token-here",
        ],
        rate_limit="Tier 1-4 depending on method (1-100+ req/min)",
        notes="Bot tokens are recommended over user tokens for MCP servers.",
    ),

    "openai": APIInfo(
        name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        auth_type="bearer",
        env_var_name="OPENAI_API_KEY",
        key_url="https://platform.openai.com/api-keys",
        docs_url="https://platform.openai.com/docs/api-reference",
        free_tier=False,
        scopes=[],
        setup_steps=[
            "Go to https://platform.openai.com/api-keys",
            "Sign in or create an account",
            "Click '+ Create new secret key'",
            "Name it 'MCP Server'",
            "Copy the key (starts with sk-...)",
            "Paste it in your .env file as OPENAI_API_KEY=sk-your-key-here",
            "Add billing at https://platform.openai.com/account/billing (required)",
        ],
        rate_limit="Varies by model and tier",
        notes="Requires a paid account. Free trial credits may be available for new accounts.",
    ),

    "stripe": APIInfo(
        name="stripe",
        display_name="Stripe",
        base_url="https://api.stripe.com/v1",
        auth_type="bearer",
        env_var_name="STRIPE_SECRET_KEY",
        key_url="https://dashboard.stripe.com/apikeys",
        docs_url="https://stripe.com/docs/api",
        free_tier=True,
        scopes=[],
        setup_steps=[
            "Go to https://dashboard.stripe.com/apikeys",
            "Sign in or create a Stripe account",
            "Use the 'Test mode' toggle (top-right) for development",
            "Copy the 'Secret key' (starts with sk_test_...)",
            "Paste it in your .env file as STRIPE_SECRET_KEY=sk_test_your_key_here",
            "IMPORTANT: NEVER use live keys during development!",
        ],
        rate_limit="100 read requests/sec, 100 write requests/sec",
        notes="Always use test-mode keys during development. Live keys process real payments.",
    ),

    "notion": APIInfo(
        name="notion",
        display_name="Notion",
        base_url="https://api.notion.com/v1",
        auth_type="bearer",
        env_var_name="NOTION_API_KEY",
        key_url="https://www.notion.so/my-integrations",
        docs_url="https://developers.notion.com/reference",
        free_tier=True,
        scopes=["read_content", "update_content", "insert_content"],
        setup_steps=[
            "Go to https://www.notion.so/my-integrations",
            "Click '+ New integration'",
            "Name it 'MCP Server' and select your workspace",
            "Click 'Submit'",
            "Copy the 'Internal Integration Secret' (starts with ntn_...)",
            "Paste it in your .env file as NOTION_API_KEY=ntn_your_key_here",
            "IMPORTANT: Open the Notion pages you want to access",
            "Click '...' menu → 'Connections' → Add your integration",
        ],
        rate_limit="3 requests/sec",
        notes="You must explicitly share each page/database with the integration inside Notion.",
    ),

    "spotify": APIInfo(
        name="spotify",
        display_name="Spotify",
        base_url="https://api.spotify.com/v1",
        auth_type="oauth2",
        env_var_name="SPOTIFY_CLIENT_ID",
        key_url="https://developer.spotify.com/dashboard",
        docs_url="https://developer.spotify.com/documentation/web-api",
        free_tier=True,
        scopes=["user-read-private", "playlist-read-private", "user-library-read"],
        setup_steps=[
            "Go to https://developer.spotify.com/dashboard",
            "Log in and click 'Create App'",
            "Name it 'MCP Server', set redirect URI to http://localhost:8888/callback",
            "Copy the Client ID and Client Secret",
            "Paste them in your .env file:",
            "  SPOTIFY_CLIENT_ID=your_client_id",
            "  SPOTIFY_CLIENT_SECRET=your_client_secret",
        ],
        rate_limit="Variable — generally generous for authenticated requests",
        notes="OAuth2 flow required. User authorization needed for personal data access.",
        extra_env_vars={"SPOTIFY_CLIENT_SECRET": "your_client_secret"},
    ),

    "google": APIInfo(
        name="google",
        display_name="Google APIs",
        base_url="https://www.googleapis.com",
        auth_type="bearer",
        env_var_name="GOOGLE_API_KEY",
        key_url="https://console.cloud.google.com/apis/credentials",
        docs_url="https://developers.google.com/apis-explorer",
        free_tier=True,
        scopes=[],
        setup_steps=[
            "Go to https://console.cloud.google.com/",
            "Create a new project (or select existing)",
            "Go to 'APIs & Services' → 'Credentials'",
            "Click '+ CREATE CREDENTIALS' → 'API key'",
            "Copy the API key",
            "Paste it in your .env file as GOOGLE_API_KEY=your_key_here",
            "Go to 'APIs & Services' → 'Library' to enable specific APIs you need",
        ],
        rate_limit="Varies by API (Sheets, Drive, Maps all have different quotas)",
        notes="Different Google APIs have different quotas and must be enabled individually.",
    ),

    "twitter": APIInfo(
        name="twitter",
        display_name="Twitter / X",
        base_url="https://api.twitter.com/2",
        auth_type="bearer",
        env_var_name="TWITTER_BEARER_TOKEN",
        key_url="https://developer.twitter.com/en/portal/dashboard",
        docs_url="https://developer.twitter.com/en/docs/twitter-api",
        free_tier=False,
        scopes=["tweet.read", "users.read"],
        setup_steps=[
            "Go to https://developer.twitter.com/en/portal/dashboard",
            "Apply for a developer account (may require approval)",
            "Create a new Project and App",
            "Go to 'Keys and tokens'",
            "Generate a 'Bearer Token'",
            "Paste it in your .env file as TWITTER_BEARER_TOKEN=your_token_here",
        ],
        rate_limit="Free tier: very limited | Basic ($100/mo): moderate limits",
        notes="Free tier is extremely limited. Basic plan costs $100/month.",
    ),

    "discord": APIInfo(
        name="discord",
        display_name="Discord",
        base_url="https://discord.com/api/v10",
        auth_type="bearer",
        env_var_name="DISCORD_BOT_TOKEN",
        key_url="https://discord.com/developers/applications",
        docs_url="https://discord.com/developers/docs/intro",
        free_tier=True,
        scopes=["bot"],
        setup_steps=[
            "Go to https://discord.com/developers/applications",
            "Click 'New Application' and give it a name",
            "Go to the 'Bot' tab → click 'Add Bot'",
            "Click 'Reset Token' to get your bot token",
            "Copy the token",
            "Paste it in your .env file as DISCORD_BOT_TOKEN=your_token_here",
            "Go to 'OAuth2' → 'URL Generator' to create a server invite link",
            "Invite the bot to your Discord server",
        ],
        rate_limit="50 requests/sec globally",
        notes="Bot token must be kept secret. Never commit it to version control.",
    ),

    "linear": APIInfo(
        name="linear",
        display_name="Linear",
        base_url="https://api.linear.app",
        auth_type="bearer",
        env_var_name="LINEAR_API_KEY",
        key_url="https://linear.app/settings/api",
        docs_url="https://developers.linear.app/docs",
        free_tier=True,
        scopes=[],
        setup_steps=[
            "Go to https://linear.app/settings/api",
            "Click 'Create key'",
            "Name it 'MCP Server'",
            "Copy the API key (starts with lin_api_...)",
            "Paste it in your .env file as LINEAR_API_KEY=lin_api_your_key_here",
        ],
        rate_limit="1,500 requests/hour",
        notes="Personal API keys have full access to your Linear workspace.",
    ),

    "jira": APIInfo(
        name="jira",
        display_name="Jira (Atlassian)",
        base_url="https://your-domain.atlassian.net/rest/api/3",
        auth_type="basic",
        env_var_name="JIRA_API_TOKEN",
        key_url="https://id.atlassian.com/manage-profile/security/api-tokens",
        docs_url="https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/",
        free_tier=True,
        scopes=[],
        setup_steps=[
            "Go to https://id.atlassian.com/manage-profile/security/api-tokens",
            "Click 'Create API token'",
            "Name it 'MCP Server'",
            "Copy the token",
            "In your .env file, set all three:",
            "  JIRA_API_TOKEN=your_token_here",
            "  JIRA_EMAIL=your-email@example.com",
            "  JIRA_BASE_URL=https://your-domain.atlassian.net",
        ],
        rate_limit="Varies by endpoint",
        notes="Uses Basic auth with email + API token (NOT your Atlassian password).",
        extra_env_vars={
            "JIRA_EMAIL": "your-email@example.com",
            "JIRA_BASE_URL": "https://your-domain.atlassian.net",
        },
    ),
    "linkedin": APIInfo(
        name="linkedin",
        display_name="LinkedIn",
        base_url="https://api.linkedin.com/v2",
        auth_type="oauth2",
        env_var_name="LINKEDIN_ACCESS_TOKEN",
        key_url="https://www.linkedin.com/developers/apps",
        docs_url="https://learn.microsoft.com/en-us/linkedin/",
        free_tier=True,
        scopes=["r_liteprofile", "r_emailaddress", "w_member_social"],
        setup_steps=[
            "Go to https://www.linkedin.com/developers/apps",
            "Click 'Create App' and fill in the details",
            "Under 'Auth' tab, add OAuth 2.0 redirect URL",
            "Request access to 'Share on LinkedIn' and 'Sign In with LinkedIn' products",
            "Copy the Client ID and Client Secret",
            "Complete the OAuth 2.0 flow to obtain an access token",
            "In your .env file, set:",
            "  LINKEDIN_ACCESS_TOKEN=your_access_token_here",
        ],
        rate_limit="100 requests/day for most endpoints",
        notes="Requires OAuth 2.0 three-legged flow. Access tokens expire; use refresh tokens for long-lived access.",
    ),
}

# Keyword → API mapping for indirect detection
_KEYWORD_MAP: dict[str, list[str]] = {
    "github":  ["repository", "repos", "pull request", "pr ", "git issues", "commits", "github actions"],
    "slack":   ["slack channel", "slack message", "slack bot", "workspace messages"],
    "openai":  ["chatgpt", "gpt-4", "gpt-3", "dall-e", "whisper", "embeddings"],
    "stripe":  ["payments", "subscriptions", "invoices", "billing api", "checkout"],
    "notion":  ["notion page", "notion database", "notion workspace"],
    "spotify": ["music", "playlist", "songs", "tracks", "albums"],
    "google":  ["gmail", "google sheets", "google drive", "google calendar", "youtube"],
    "twitter": ["tweets", "x.com", "twitter api"],
    "discord": ["discord bot", "discord server", "discord channel"],
    "linear":  ["linear issues", "linear projects", "linear tickets"],
    "jira":    ["jira ticket", "jira issue", "jira board", "atlassian", "confluence"],
    "linkedin": ["linkedin post", "linkedin profile", "linkedin share", "linkedin company", "linkedin article"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_api(prompt: str) -> Optional[APIInfo]:
    """Detect which API the user wants from their natural language prompt.

    Returns the matching APIInfo or None for non-API templates.
    """
    apis = detect_apis(prompt)
    return apis[0] if apis else None


def detect_apis(prompt: str) -> list[APIInfo]:
    """Detect ALL APIs mentioned in the user's prompt.

    Returns a list of matching APIInfo objects, ordered by confidence
    (direct name matches first, then keyword matches).
    """
    prompt_lower = prompt.lower()
    found: list[APIInfo] = []
    found_names: set[str] = set()

    # 1. Direct name matching (highest confidence)
    for key, info in API_REGISTRY.items():
        if key in prompt_lower or info.display_name.lower() in prompt_lower:
            if key not in found_names:
                found.append(info)
                found_names.add(key)

    # 2. Keyword / synonym matching (require at least 2 hits for confidence)
    for api_name, keywords in _KEYWORD_MAP.items():
        if api_name in found_names:
            continue  # Already matched by direct name
        hits = sum(1 for keyword in keywords if keyword in prompt_lower)

        # 2+ keyword hits = confident match
        if hits >= 2:
            found.append(API_REGISTRY[api_name])
            found_names.add(api_name)
            continue

        # 1 hit allowed only for multi-word phrases (very specific)
        if hits == 1:
            for keyword in keywords:
                if keyword in prompt_lower and " " in keyword:
                    found.append(API_REGISTRY[api_name])
                    found_names.add(api_name)
                    break

    return found


def generate_env_file(api: Optional[APIInfo] = None, apis: Optional[list[APIInfo]] = None) -> str:
    """Generate .env.example content with API-specific variable names.

    Supports a single API (backward compat) or a list of APIs (multi-API).
    """
    # Normalize to a list
    api_list: list[APIInfo] = []
    if apis:
        api_list = apis
    elif api:
        api_list = [api]

    if not api_list:
        return (
            "# Configuration — copy this file to .env and fill in values\n"
            "# Never commit .env to git!\n"
            "\n"
            "API_KEY=your-api-key-here\n"
            "API_BASE_URL=https://api.example.com\n"
            "\n"
            "# How to get your API key:\n"
            "# 1. Go to your API provider's developer portal\n"
            "# 2. Create an account or sign in\n"
            "# 3. Navigate to API keys / credentials section\n"
            "# 4. Generate a new key and paste it above\n"
        )

    lines = [
        "# API Configuration",
        "# Copy this file to .env and fill in your values:",
        "#   cp .env.example .env",
        "",
    ]

    for i, a in enumerate(api_list):
        if i > 0:
            lines.append("")
        lines.append(f"# ── {a.display_name} ──")
        lines.append(f"# Get your key at: {a.key_url}")
        lines.append(f"# Docs: {a.docs_url}")
        lines.append(f"{a.env_var_name}=your-key-here")

        # Add any extra env vars (e.g. JIRA_EMAIL, SPOTIFY_CLIENT_SECRET)
        for var_name, placeholder in a.extra_env_vars.items():
            lines.append(f"{var_name}={placeholder}")

        lines.append(f"# Rate limit: {a.rate_limit}")
        if not a.free_tier:
            lines.append("# ⚠️  WARNING: This API requires a PAID plan")

    lines.append("")
    return "\n".join(lines) + "\n"


def generate_setup_guide(api: Optional[APIInfo] = None, server_name: str = "", language: str = "typescript", apis: Optional[list[APIInfo]] = None) -> str:
    """Generate a SETUP.md with step-by-step instructions for getting
    the API key, configuring the server, and connecting to Claude Desktop.

    Supports a single API (backward compat) or a list of APIs (multi-API).
    """
    # Normalize to a list
    api_list: list[APIInfo] = []
    if apis:
        api_list = apis
    elif api:
        api_list = [api]

    if not api_list:
        return _generic_setup_guide(server_name, language)

    install_cmd = "npm install" if language == "typescript" else "pip install -r requirements.txt"
    run_cmd = "npm start" if language == "typescript" else "python server.py"
    entry_file = "dist/index.js" if language == "typescript" else "server.py"
    runtime = "node" if language == "typescript" else "python"

    api_names = " + ".join(a.display_name for a in api_list)

    lines = [
        f"# {server_name} — Setup Guide",
        "",
        f"This MCP server connects to: **{api_names}**",
        "",
    ]

    # Step 1: API keys for each
    step_num = 1
    for a in api_list:
        lines.extend([
            "---",
            "",
            f"## Step {step_num}: Get Your {a.display_name} API Key",
            "",
            f"{'✅ Free tier available' if a.free_tier else '⚠️ Paid plan required'}",
            "",
        ])

        for i, step in enumerate(a.setup_steps, 1):
            lines.append(f"{i}. {step}")

        if a.scopes:
            lines.extend([
                "",
                "### Required Permissions / Scopes",
                "",
            ])
            for scope in a.scopes:
                lines.append(f"- `{scope}`")

        lines.append("")
        step_num += 1

    # Step N: Configure
    lines.extend([
        "---",
        "",
        f"## Step {step_num}: Configure Your Server",
        "",
        "```bash",
        "cp .env.example .env",
        "```",
        "",
        "Open `.env` in your editor and fill in all your API keys.",
        "",
    ])
    step_num += 1

    # Step N+1: Install & Run
    lines.extend([
        "---",
        "",
        f"## Step {step_num}: Install Dependencies & Run",
        "",
        "```bash",
        install_cmd,
        run_cmd,
        "```",
        "",
    ])
    step_num += 1

    # Step N+2: Test
    lines.extend([
        "---",
        "",
        f"## Step {step_num}: Test with MCP Inspector",
        "",
        "```bash",
        "npx @modelcontextprotocol/inspector",
        "```",
        "",
        "This opens a web UI where you can test each tool interactively.",
        "",
    ])
    step_num += 1

    # Step N+3: Claude Desktop
    env_block = ",\n".join(f'        "{a.env_var_name}": "your-key-here"' for a in api_list)
    lines.extend([
        "---",
        "",
        f"## Step {step_num}: Add to Claude Desktop",
        "",
        "Edit your Claude Desktop config file (`claude_desktop_config.json`):",
        "",
        "```json",
        "{",
        '  "mcpServers": {',
        f'    "{server_name}": {{',
        f'      "command": "{runtime}",',
        f'      "args": ["{entry_file}"],',
        '      "env": {',
        f'{env_block}',
        '      }',
        '    }',
        '  }',
        "}",
        "```",
        "",
        "**Config file locations:**",
        "- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`",
        "- Windows: `%APPDATA%\\Claude\\claude_desktop_config.json`",
        "",
    ])

    # Rate limits
    lines.extend(["---", "", "## Rate Limits", ""])
    for a in api_list:
        lines.append(f"- **{a.display_name}:** {a.rate_limit}")
    lines.append("")

    # Notes
    notes = [a for a in api_list if a.notes]
    if notes:
        lines.extend(["---", "", "## Notes", ""])
        for a in notes:
            lines.append(f"**{a.display_name}:** {a.notes}")
            lines.append("")

    lines.extend([
        "---",
        "",
        f"*Generated by [MCP Factory](https://github.com/jatin/mcp-factory)*",
        "",
    ])

    return "\n".join(lines)


def _generic_setup_guide(server_name: str, language: str) -> str:
    """Fallback setup guide for unknown/generic APIs."""
    install_cmd = "npm install" if language == "typescript" else "pip install -r requirements.txt"
    run_cmd = "npm start" if language == "typescript" else "python server.py"

    return f"""# {server_name} — Setup Guide

## Step 1: Get Your API Key

Check your API provider's documentation for how to obtain credentials.

## Step 2: Configure

```bash
cp .env.example .env
# Open .env and paste your API key
```

## Step 3: Install & Run

```bash
{install_cmd}
{run_cmd}
```

## Step 4: Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

---

*Generated by [MCP Factory](https://github.com/jatin/mcp-factory)*
"""


def get_supported_apis() -> list[dict]:
    """Return a list of all supported APIs for display in CLI."""
    return [
        {
            "name": name,
            "display_name": info.display_name,
            "auth_type": info.auth_type,
            "env_var": info.env_var_name,
            "free_tier": info.free_tier,
            "key_url": info.key_url,
        }
        for name, info in API_REGISTRY.items()
    ]
