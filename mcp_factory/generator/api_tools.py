"""API-specific tool templates — Real working tools for known APIs.

Instead of generic api_get/api_post, this module generates API-specific
tools (e.g., gh_list_repos, slack_send_message) with real endpoints,
proper parameters, and correct auth headers.

Supported APIs with custom tools: GitHub, Slack, Stripe, Notion, Discord
Others fall through to generic api-wrapper tools.
"""

from __future__ import annotations

from typing import Optional

from mcp_factory.generator.api_registry import APIInfo


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def has_custom_tools(api_name: str) -> bool:
    """Check if we have pre-built custom tools for this API."""
    return api_name in _TS_TOOLS and api_name in _PY_TOOLS


def get_custom_tool_defs(api_name: str) -> list[dict]:
    """Return tool definition dicts for an API (name, description, annotations, prefix)."""
    return _TOOL_DEFS.get(api_name, [])


def get_ts_tools(api_name: str) -> Optional[str]:
    """Return TypeScript tool code for a known API, or None."""
    return _TS_TOOLS.get(api_name)


def get_py_tools(api_name: str) -> Optional[str]:
    """Return Python tool code for a known API, or None."""
    return _PY_TOOLS.get(api_name)


# ---------------------------------------------------------------------------
# Tool definitions (used to build ToolDefinition objects)
# ---------------------------------------------------------------------------

_TOOL_DEFS: dict[str, list[dict]] = {
    "github": [
        {"name": "gh_list_repos", "description": "List repositories for a user or organization with pagination", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "gh_get_repo", "description": "Get detailed info about a specific repository", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "gh_list_issues", "description": "List issues for a repository with state and label filters", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "gh_create_issue", "description": "Create a new issue in a repository", "read_only": False, "destructive": False, "idempotent": False, "open_world": True},
        {"name": "gh_list_prs", "description": "List pull requests for a repository with state filter", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
    ],
    "slack": [
        {"name": "slack_list_channels", "description": "List public channels in the Slack workspace with pagination", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "slack_send_message", "description": "Send a message to a Slack channel", "read_only": False, "destructive": False, "idempotent": False, "open_world": True},
        {"name": "slack_channel_history", "description": "Get recent messages from a channel", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "slack_channel_info", "description": "Get detailed information about a channel", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
    ],
    "stripe": [
        {"name": "stripe_list_customers", "description": "List Stripe customers with pagination and email filter", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "stripe_get_customer", "description": "Get details of a specific customer by ID", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "stripe_list_payments", "description": "List payment intents with status filter and pagination", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "stripe_create_customer", "description": "Create a new customer with email and name", "read_only": False, "destructive": False, "idempotent": False, "open_world": True},
    ],
    "notion": [
        {"name": "notion_search", "description": "Search across all pages and databases in the workspace", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "notion_get_page", "description": "Get a Notion page by ID with its properties and content blocks", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "notion_query_database", "description": "Query a Notion database with optional filter and sort", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "notion_create_page", "description": "Create a new page in a Notion database", "read_only": False, "destructive": False, "idempotent": False, "open_world": True},
    ],
    "discord": [
        {"name": "discord_list_guilds", "description": "List all guilds (servers) the bot is a member of", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "discord_list_channels", "description": "List channels in a guild", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
        {"name": "discord_send_message", "description": "Send a message to a Discord channel", "read_only": False, "destructive": False, "idempotent": False, "open_world": True},
        {"name": "discord_get_messages", "description": "Get recent messages from a channel", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
    ],
}


# ---------------------------------------------------------------------------
# TypeScript implementations
# ---------------------------------------------------------------------------

_TS_TOOLS: dict[str, str] = {}

_TS_TOOLS["github"] = '''
server.tool(
  "gh_list_repos",
  "List repositories for a GitHub user or organization. Returns name, description, stars, language, and URLs. Supports pagination.",
  {
    owner: z.string().describe("GitHub username or org name. Example: 'octocat'"),
    type: z.enum(["all", "owner", "member"]).optional().describe("Filter by repo type (default 'owner')"),
    sort: z.enum(["created", "updated", "pushed", "full_name"]).optional().describe("Sort field (default 'updated')"),
    page: z.number().int().min(1).optional().describe("Page number for pagination (default 1)"),
    perPage: z.number().int().min(1).max(100).optional().describe("Results per page, max 100 (default 30)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ owner, type = "owner", sort = "updated", page = 1, perPage = 30 }) => {
    try {
      const url = `${BASE_URL}/users/${owner}/repos?type=${type}&sort=${sort}&page=${page}&per_page=${perPage}`;
      const res = await fetch(url, { headers });
      if (res.status === 404) return errorResponse(`User "${owner}" not found.`, "Check the username spelling.");
      if (!res.ok) return errorResponse(`GitHub API error: ${res.status}`, res.status === 401 ? "Check your GITHUB_TOKEN." : undefined);
      const repos = await res.json();
      const result = repos.map((r: any) => ({
        name: r.name, fullName: r.full_name, description: r.description,
        stars: r.stargazers_count, forks: r.forks_count, language: r.language,
        private: r.private, url: r.html_url, updatedAt: r.updated_at,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: result.length, page, repos: result }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list repos: ${err.message}`);
    }
  }
);

server.tool(
  "gh_get_repo",
  "Get detailed information about a specific GitHub repository including description, stats, default branch, and license.",
  {
    owner: z.string().describe("Repository owner (user or org)"),
    repo: z.string().describe("Repository name"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ owner, repo }) => {
    try {
      const res = await fetch(`${BASE_URL}/repos/${owner}/${repo}`, { headers });
      if (res.status === 404) return errorResponse(`Repository "${owner}/${repo}" not found.`);
      if (!res.ok) return errorResponse(`GitHub API error: ${res.status}`);
      const r = await res.json();
      const info = {
        name: r.full_name, description: r.description, stars: r.stargazers_count,
        forks: r.forks_count, openIssues: r.open_issues_count, language: r.language,
        defaultBranch: r.default_branch, license: r.license?.spdx_id || null,
        private: r.private, archived: r.archived, url: r.html_url,
        createdAt: r.created_at, updatedAt: r.updated_at,
      };
      return { content: [{ type: "text", text: JSON.stringify(info, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to get repo: ${err.message}`);
    }
  }
);

server.tool(
  "gh_list_issues",
  "List issues for a GitHub repository. Supports filtering by state, labels, and assignee. Returns title, number, state, labels, and author.",
  {
    owner: z.string().describe("Repository owner"),
    repo: z.string().describe("Repository name"),
    state: z.enum(["open", "closed", "all"]).optional().describe("Issue state filter (default 'open')"),
    labels: z.string().optional().describe("Comma-separated label names to filter by"),
    assignee: z.string().optional().describe("Filter by assignee username"),
    page: z.number().int().min(1).optional().describe("Page number (default 1)"),
    perPage: z.number().int().min(1).max(100).optional().describe("Results per page (default 30)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ owner, repo, state = "open", labels, assignee, page = 1, perPage = 30 }) => {
    try {
      let url = `${BASE_URL}/repos/${owner}/${repo}/issues?state=${state}&page=${page}&per_page=${perPage}`;
      if (labels) url += `&labels=${encodeURIComponent(labels)}`;
      if (assignee) url += `&assignee=${encodeURIComponent(assignee)}`;
      const res = await fetch(url, { headers });
      if (!res.ok) return errorResponse(`GitHub API error: ${res.status}`);
      const issues = await res.json();
      const result = issues
        .filter((i: any) => !i.pull_request)
        .map((i: any) => ({
          number: i.number, title: i.title, state: i.state,
          author: i.user?.login, labels: i.labels?.map((l: any) => l.name),
          comments: i.comments, createdAt: i.created_at, url: i.html_url,
        }));
      return { content: [{ type: "text", text: JSON.stringify({ total: result.length, page, issues: result }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list issues: ${err.message}`);
    }
  }
);

server.tool(
  "gh_create_issue",
  "Create a new issue in a GitHub repository. Returns the created issue number and URL.",
  {
    owner: z.string().describe("Repository owner"),
    repo: z.string().describe("Repository name"),
    title: z.string().describe("Issue title"),
    body: z.string().optional().describe("Issue body (Markdown supported)"),
    labels: z.array(z.string()).optional().describe("Labels to apply to the issue"),
    assignees: z.array(z.string()).optional().describe("GitHub usernames to assign"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ owner, repo, title, body, labels, assignees }) => {
    try {
      const res = await fetch(`${BASE_URL}/repos/${owner}/${repo}/issues`, {
        method: "POST", headers,
        body: JSON.stringify({ title, body, labels, assignees }),
      });
      if (res.status === 404) return errorResponse(`Repository "${owner}/${repo}" not found.`);
      if (res.status === 403) return errorResponse("Permission denied.", "Your GITHUB_TOKEN needs 'repo' scope to create issues.");
      if (!res.ok) return errorResponse(`GitHub API error: ${res.status} — ${await res.text()}`);
      const issue = await res.json();
      return { content: [{ type: "text", text: JSON.stringify({ number: issue.number, url: issue.html_url, title: issue.title }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to create issue: ${err.message}`);
    }
  }
);

server.tool(
  "gh_list_prs",
  "List pull requests for a GitHub repository. Returns title, number, state, author, branch, and review status.",
  {
    owner: z.string().describe("Repository owner"),
    repo: z.string().describe("Repository name"),
    state: z.enum(["open", "closed", "all"]).optional().describe("PR state filter (default 'open')"),
    page: z.number().int().min(1).optional().describe("Page number (default 1)"),
    perPage: z.number().int().min(1).max(100).optional().describe("Results per page (default 30)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ owner, repo, state = "open", page = 1, perPage = 30 }) => {
    try {
      const url = `${BASE_URL}/repos/${owner}/${repo}/pulls?state=${state}&page=${page}&per_page=${perPage}`;
      const res = await fetch(url, { headers });
      if (!res.ok) return errorResponse(`GitHub API error: ${res.status}`);
      const prs = await res.json();
      const result = prs.map((p: any) => ({
        number: p.number, title: p.title, state: p.state,
        author: p.user?.login, branch: p.head?.ref, baseBranch: p.base?.ref,
        draft: p.draft, mergeable: p.mergeable, createdAt: p.created_at, url: p.html_url,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: result.length, page, pullRequests: result }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list PRs: ${err.message}`);
    }
  }
);'''

_TS_TOOLS["slack"] = '''
server.tool(
  "slack_list_channels",
  "List public channels in the Slack workspace. Returns channel name, ID, topic, and member count.",
  {
    limit: z.number().int().min(1).max(200).optional().describe("Max channels to return (default 100)"),
    cursor: z.string().optional().describe("Pagination cursor from a previous response"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ limit = 100, cursor }) => {
    try {
      let url = `${BASE_URL}/conversations.list?types=public_channel&limit=${limit}`;
      if (cursor) url += `&cursor=${cursor}`;
      const res = await fetch(url, { headers });
      const data = await res.json();
      if (!data.ok) return errorResponse(`Slack API error: ${data.error}`, data.error === "invalid_auth" ? "Check your SLACK_BOT_TOKEN." : undefined);
      const channels = data.channels.map((c: any) => ({
        id: c.id, name: c.name, topic: c.topic?.value || "",
        memberCount: c.num_members, isArchived: c.is_archived,
      }));
      const result: any = { total: channels.length, channels };
      if (data.response_metadata?.next_cursor) result.nextCursor = data.response_metadata.next_cursor;
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list channels: ${err.message}`);
    }
  }
);

server.tool(
  "slack_send_message",
  "Send a text message to a Slack channel. Returns the message timestamp and channel ID.",
  {
    channel: z.string().describe("Channel ID (e.g., 'C01234ABCDE'). Use slack_list_channels to find IDs."),
    text: z.string().describe("Message text. Supports Slack markdown (mrkdwn)."),
    threadTs: z.string().optional().describe("Thread timestamp to reply in a thread"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ channel, text, threadTs }) => {
    try {
      const body: any = { channel, text };
      if (threadTs) body.thread_ts = threadTs;
      const res = await fetch(`${BASE_URL}/chat.postMessage`, {
        method: "POST", headers, body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.ok) return errorResponse(`Slack API error: ${data.error}`, data.error === "channel_not_found" ? "Use slack_list_channels to find valid channel IDs." : undefined);
      return { content: [{ type: "text", text: JSON.stringify({ channel: data.channel, ts: data.ts, message: "Message sent successfully" }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to send message: ${err.message}`);
    }
  }
);

server.tool(
  "slack_channel_history",
  "Get recent messages from a Slack channel. Returns message text, author, and timestamp.",
  {
    channel: z.string().describe("Channel ID"),
    limit: z.number().int().min(1).max(100).optional().describe("Number of messages to return (default 20)"),
    cursor: z.string().optional().describe("Pagination cursor for older messages"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ channel, limit = 20, cursor }) => {
    try {
      let url = `${BASE_URL}/conversations.history?channel=${channel}&limit=${limit}`;
      if (cursor) url += `&cursor=${cursor}`;
      const res = await fetch(url, { headers });
      const data = await res.json();
      if (!data.ok) return errorResponse(`Slack API error: ${data.error}`);
      const messages = data.messages.map((m: any) => ({
        text: m.text, user: m.user, ts: m.ts, type: m.type,
        threadTs: m.thread_ts, replyCount: m.reply_count || 0,
      }));
      const result: any = { total: messages.length, messages };
      if (data.response_metadata?.next_cursor) result.nextCursor = data.response_metadata.next_cursor;
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to get channel history: ${err.message}`);
    }
  }
);

server.tool(
  "slack_channel_info",
  "Get detailed information about a Slack channel: name, topic, purpose, member count.",
  {
    channel: z.string().describe("Channel ID (e.g., 'C01234ABCDE')"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ channel }) => {
    try {
      const res = await fetch(`${BASE_URL}/conversations.info?channel=${channel}`, { headers });
      const data = await res.json();
      if (!data.ok) return errorResponse(`Slack API error: ${data.error}`);
      const c = data.channel;
      const info = {
        id: c.id, name: c.name, topic: c.topic?.value || "", purpose: c.purpose?.value || "",
        memberCount: c.num_members, isArchived: c.is_archived, isPrivate: c.is_private,
        created: new Date(c.created * 1000).toISOString(),
      };
      return { content: [{ type: "text", text: JSON.stringify(info, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to get channel info: ${err.message}`);
    }
  }
);'''

_TS_TOOLS["stripe"] = '''
server.tool(
  "stripe_list_customers",
  "List Stripe customers with optional email filter and pagination. Returns customer name, email, and metadata.",
  {
    email: z.string().email().optional().describe("Filter by exact email address"),
    limit: z.number().int().min(1).max(100).optional().describe("Max customers to return (default 10)"),
    startingAfter: z.string().optional().describe("Cursor: customer ID to start after (for pagination)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ email, limit = 10, startingAfter }) => {
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (email) params.set("email", email);
      if (startingAfter) params.set("starting_after", startingAfter);
      const res = await fetch(`${BASE_URL}/customers?${params}`, { headers });
      if (!res.ok) return errorResponse(`Stripe API error: ${res.status}`, res.status === 401 ? "Check your STRIPE_SECRET_KEY." : undefined);
      const data = await res.json();
      const customers = data.data.map((c: any) => ({
        id: c.id, name: c.name, email: c.email, created: new Date(c.created * 1000).toISOString(),
        currency: c.currency, balance: c.balance, metadata: c.metadata,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: customers.length, hasMore: data.has_more, customers }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list customers: ${err.message}`);
    }
  }
);

server.tool(
  "stripe_get_customer",
  "Get detailed information about a Stripe customer by their ID.",
  {
    customerId: z.string().describe("Stripe customer ID (starts with 'cus_')"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ customerId }) => {
    try {
      const res = await fetch(`${BASE_URL}/customers/${customerId}`, { headers });
      if (res.status === 404) return errorResponse(`Customer "${customerId}" not found.`);
      if (!res.ok) return errorResponse(`Stripe API error: ${res.status}`);
      const c = await res.json();
      return { content: [{ type: "text", text: JSON.stringify({
        id: c.id, name: c.name, email: c.email, phone: c.phone,
        created: new Date(c.created * 1000).toISOString(),
        currency: c.currency, balance: c.balance,
        defaultSource: c.default_source, metadata: c.metadata,
      }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to get customer: ${err.message}`);
    }
  }
);

server.tool(
  "stripe_list_payments",
  "List Stripe payment intents with optional status filter. Returns amount, currency, status, and customer info.",
  {
    limit: z.number().int().min(1).max(100).optional().describe("Max results (default 10)"),
    startingAfter: z.string().optional().describe("Payment intent ID to start after (for pagination)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ limit = 10, startingAfter }) => {
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (startingAfter) params.set("starting_after", startingAfter);
      const res = await fetch(`${BASE_URL}/payment_intents?${params}`, { headers });
      if (!res.ok) return errorResponse(`Stripe API error: ${res.status}`);
      const data = await res.json();
      const payments = data.data.map((p: any) => ({
        id: p.id, amount: p.amount / 100, currency: p.currency, status: p.status,
        customer: p.customer, created: new Date(p.created * 1000).toISOString(),
        description: p.description,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: payments.length, hasMore: data.has_more, payments }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list payments: ${err.message}`);
    }
  }
);

server.tool(
  "stripe_create_customer",
  "Create a new Stripe customer. Returns the new customer ID and details.",
  {
    email: z.string().email().describe("Customer email address"),
    name: z.string().optional().describe("Customer full name"),
    description: z.string().optional().describe("Internal description/notes"),
    metadata: z.record(z.string()).optional().describe("Key-value metadata pairs"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ email, name, description, metadata }) => {
    try {
      const body = new URLSearchParams();
      body.set("email", email);
      if (name) body.set("name", name);
      if (description) body.set("description", description);
      if (metadata) Object.entries(metadata).forEach(([k, v]) => body.set(`metadata[${k}]`, v));
      const res = await fetch(`${BASE_URL}/customers`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      if (!res.ok) return errorResponse(`Stripe API error: ${res.status} — ${await res.text()}`);
      const c = await res.json();
      return { content: [{ type: "text", text: JSON.stringify({ id: c.id, email: c.email, name: c.name, created: new Date(c.created * 1000).toISOString() }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to create customer: ${err.message}`);
    }
  }
);'''

_TS_TOOLS["notion"] = '''
server.tool(
  "notion_search",
  "Search across all pages and databases in the Notion workspace. Returns page titles, IDs, and last edited time.",
  {
    query: z.string().describe("Search query text"),
    filter: z.enum(["page", "database"]).optional().describe("Filter by object type"),
    pageSize: z.number().int().min(1).max(100).optional().describe("Max results (default 10)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ query, filter, pageSize = 10 }) => {
    try {
      const body: any = { query, page_size: pageSize };
      if (filter) body.filter = { property: "object", value: filter };
      const res = await fetch(`${BASE_URL}/search`, {
        method: "POST", headers: { ...headers, "Notion-Version": "2022-06-28" },
        body: JSON.stringify(body),
      });
      if (!res.ok) return errorResponse(`Notion API error: ${res.status}`, res.status === 401 ? "Check your NOTION_API_KEY and integration permissions." : undefined);
      const data = await res.json();
      const results = data.results.map((r: any) => ({
        id: r.id, type: r.object,
        title: r.properties?.title?.title?.[0]?.plain_text || r.properties?.Name?.title?.[0]?.plain_text || "(untitled)",
        url: r.url, lastEdited: r.last_edited_time,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: results.length, hasMore: data.has_more, results }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Search failed: ${err.message}`);
    }
  }
);

server.tool(
  "notion_get_page",
  "Get a Notion page by its ID. Returns the page properties and metadata.",
  {
    pageId: z.string().describe("Notion page ID (UUID format)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ pageId }) => {
    try {
      const res = await fetch(`${BASE_URL}/pages/${pageId}`, {
        headers: { ...headers, "Notion-Version": "2022-06-28" },
      });
      if (res.status === 404) return errorResponse(`Page not found: ${pageId}`, "Check the page ID and that your integration has access.");
      if (!res.ok) return errorResponse(`Notion API error: ${res.status}`);
      const page = await res.json();
      return { content: [{ type: "text", text: JSON.stringify(page, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to get page: ${err.message}`);
    }
  }
);

server.tool(
  "notion_query_database",
  "Query a Notion database. Returns database entries with their properties.",
  {
    databaseId: z.string().describe("Notion database ID (UUID format)"),
    pageSize: z.number().int().min(1).max(100).optional().describe("Max results (default 10)"),
    startCursor: z.string().optional().describe("Pagination cursor from previous response"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ databaseId, pageSize = 10, startCursor }) => {
    try {
      const body: any = { page_size: pageSize };
      if (startCursor) body.start_cursor = startCursor;
      const res = await fetch(`${BASE_URL}/databases/${databaseId}/query`, {
        method: "POST", headers: { ...headers, "Notion-Version": "2022-06-28" },
        body: JSON.stringify(body),
      });
      if (!res.ok) return errorResponse(`Notion API error: ${res.status}`);
      const data = await res.json();
      return { content: [{ type: "text", text: JSON.stringify({ total: data.results.length, hasMore: data.has_more, nextCursor: data.next_cursor, results: data.results }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to query database: ${err.message}`);
    }
  }
);

server.tool(
  "notion_create_page",
  "Create a new page in a Notion database with title and optional content.",
  {
    databaseId: z.string().describe("Parent database ID to create the page in"),
    title: z.string().describe("Page title"),
    content: z.string().optional().describe("Initial page content (plain text)"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ databaseId, title, content }) => {
    try {
      const body: any = {
        parent: { database_id: databaseId },
        properties: { Name: { title: [{ text: { content: title } }] } },
      };
      if (content) {
        body.children = [{ object: "block", type: "paragraph", paragraph: { rich_text: [{ type: "text", text: { content } }] } }];
      }
      const res = await fetch(`${BASE_URL}/pages`, {
        method: "POST", headers: { ...headers, "Notion-Version": "2022-06-28" },
        body: JSON.stringify(body),
      });
      if (!res.ok) return errorResponse(`Notion API error: ${res.status} — ${await res.text()}`);
      const page = await res.json();
      return { content: [{ type: "text", text: JSON.stringify({ id: page.id, url: page.url, title }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to create page: ${err.message}`);
    }
  }
);'''

_TS_TOOLS["discord"] = '''
server.tool(
  "discord_list_guilds",
  "List all guilds (servers) the bot is a member of. Returns guild name, ID, owner status, and member count.",
  {},
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async () => {
    try {
      const res = await fetch(`${BASE_URL}/users/@me/guilds`, { headers });
      if (!res.ok) return errorResponse(`Discord API error: ${res.status}`, res.status === 401 ? "Check your DISCORD_BOT_TOKEN." : undefined);
      const guilds = await res.json();
      const result = guilds.map((g: any) => ({
        id: g.id, name: g.name, icon: g.icon, owner: g.owner,
        permissions: g.permissions,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: result.length, guilds: result }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list guilds: ${err.message}`);
    }
  }
);

server.tool(
  "discord_list_channels",
  "List all channels in a Discord guild. Returns channel name, ID, type, and position.",
  {
    guildId: z.string().describe("Discord guild (server) ID"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ guildId }) => {
    try {
      const res = await fetch(`${BASE_URL}/guilds/${guildId}/channels`, { headers });
      if (!res.ok) return errorResponse(`Discord API error: ${res.status}`);
      const channels = await res.json();
      const typeMap: Record<number, string> = { 0: "text", 2: "voice", 4: "category", 5: "announcement", 13: "stage", 15: "forum" };
      const result = channels.map((c: any) => ({
        id: c.id, name: c.name, type: typeMap[c.type] || `type_${c.type}`, position: c.position,
        topic: c.topic || null, parentId: c.parent_id,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: result.length, channels: result }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to list channels: ${err.message}`);
    }
  }
);

server.tool(
  "discord_send_message",
  "Send a text message to a Discord channel. Returns the sent message ID.",
  {
    channelId: z.string().describe("Discord channel ID"),
    content: z.string().describe("Message text content"),
  },
  { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  async ({ channelId, content }) => {
    try {
      const res = await fetch(`${BASE_URL}/channels/${channelId}/messages`, {
        method: "POST", headers, body: JSON.stringify({ content }),
      });
      if (!res.ok) return errorResponse(`Discord API error: ${res.status}`, res.status === 403 ? "Bot needs SEND_MESSAGES permission in this channel." : undefined);
      const msg = await res.json();
      return { content: [{ type: "text", text: JSON.stringify({ id: msg.id, channelId: msg.channel_id, content: msg.content, timestamp: msg.timestamp }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to send message: ${err.message}`);
    }
  }
);

server.tool(
  "discord_get_messages",
  "Get recent messages from a Discord channel. Returns message content, author, and timestamp.",
  {
    channelId: z.string().describe("Discord channel ID"),
    limit: z.number().int().min(1).max(100).optional().describe("Number of messages to return (default 25)"),
    before: z.string().optional().describe("Get messages before this message ID (for pagination)"),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  async ({ channelId, limit = 25, before }) => {
    try {
      let url = `${BASE_URL}/channels/${channelId}/messages?limit=${limit}`;
      if (before) url += `&before=${before}`;
      const res = await fetch(url, { headers });
      if (!res.ok) return errorResponse(`Discord API error: ${res.status}`);
      const messages = await res.json();
      const result = messages.map((m: any) => ({
        id: m.id, content: m.content, author: m.author?.username,
        timestamp: m.timestamp, editedTimestamp: m.edited_timestamp,
      }));
      return { content: [{ type: "text", text: JSON.stringify({ total: result.length, messages: result }, null, 2) }] };
    } catch (err: any) {
      return errorResponse(`Failed to get messages: ${err.message}`);
    }
  }
);'''


# ---------------------------------------------------------------------------
# Python implementations
# ---------------------------------------------------------------------------

_PY_TOOLS: dict[str, str] = {}

_PY_TOOLS["github"] = '''
import httpx


@mcp.tool()
async def gh_list_repos(
    owner: str,
    type: str = "owner",
    sort: str = "updated",
    page: int = 1,
    per_page: int = 30,
) -> str:
    """List repositories for a GitHub user or organization.

    Returns name, description, stars, language, and URLs with pagination.

    Args:
        owner: GitHub username or org name. Example: 'octocat'
        type: Filter by repo type: all, owner, member (default 'owner')
        sort: Sort by: created, updated, pushed, full_name (default 'updated')
        page: Page number for pagination (default 1)
        per_page: Results per page, max 100 (default 30)
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/users/{owner}/repos",
                headers=HEADERS,
                params={"type": type, "sort": sort, "page": page, "per_page": per_page},
                timeout=30,
            )
        if r.status_code == 404:
            return _error(f\'User "{owner}" not found.\', "Check the username spelling.")
        if r.status_code != 200:
            return _error(f"GitHub API error: {r.status_code}", "Check your GITHUB_TOKEN." if r.status_code == 401 else None)
        repos = [
            {"name": repo["name"], "fullName": repo["full_name"], "description": repo.get("description"),
             "stars": repo["stargazers_count"], "forks": repo["forks_count"], "language": repo.get("language"),
             "private": repo["private"], "url": repo["html_url"], "updatedAt": repo["updated_at"]}
            for repo in r.json()
        ]
        return json.dumps({"total": len(repos), "page": page, "repos": repos}, indent=2)
    except Exception as e:
        return _error(f"Failed to list repos: {e}")


@mcp.tool()
async def gh_get_repo(owner: str, repo: str) -> str:
    """Get detailed information about a specific GitHub repository.

    Args:
        owner: Repository owner (user or org)
        repo: Repository name
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/repos/{owner}/{repo}", headers=HEADERS, timeout=30)
        if r.status_code == 404:
            return _error(f\'Repository "{owner}/{repo}" not found.\')
        data = r.json()
        info = {
            "name": data["full_name"], "description": data.get("description"), "stars": data["stargazers_count"],
            "forks": data["forks_count"], "openIssues": data["open_issues_count"], "language": data.get("language"),
            "defaultBranch": data["default_branch"], "license": (data.get("license") or {}).get("spdx_id"),
            "private": data["private"], "archived": data["archived"], "url": data["html_url"],
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return _error(f"Failed to get repo: {e}")


@mcp.tool()
async def gh_list_issues(
    owner: str,
    repo: str,
    state: str = "open",
    labels: str | None = None,
    page: int = 1,
    per_page: int = 30,
) -> str:
    """List issues for a GitHub repository with filters.

    Args:
        owner: Repository owner
        repo: Repository name
        state: Issue state: open, closed, all (default 'open')
        labels: Comma-separated label names to filter by
        page: Page number (default 1)
        per_page: Results per page, max 100 (default 30)
    """
    try:
        params: dict = {"state": state, "page": page, "per_page": per_page}
        if labels:
            params["labels"] = labels
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/repos/{owner}/{repo}/issues", headers=HEADERS, params=params, timeout=30)
        if r.status_code != 200:
            return _error(f"GitHub API error: {r.status_code}")
        issues = [
            {"number": i["number"], "title": i["title"], "state": i["state"],
             "author": i["user"]["login"], "labels": [l["name"] for l in i.get("labels", [])],
             "comments": i["comments"], "createdAt": i["created_at"], "url": i["html_url"]}
            for i in r.json() if "pull_request" not in i
        ]
        return json.dumps({"total": len(issues), "page": page, "issues": issues}, indent=2)
    except Exception as e:
        return _error(f"Failed to list issues: {e}")


@mcp.tool()
async def gh_create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> str:
    """Create a new issue in a GitHub repository.

    Args:
        owner: Repository owner
        repo: Repository name
        title: Issue title
        body: Issue body (Markdown supported)
        labels: Labels to apply
        assignees: GitHub usernames to assign
    """
    try:
        payload: dict = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/repos/{owner}/{repo}/issues",
                headers=HEADERS, json=payload, timeout=30,
            )
        if r.status_code == 403:
            return _error("Permission denied.", "Your GITHUB_TOKEN needs 'repo' scope to create issues.")
        if r.status_code not in (200, 201):
            return _error(f"GitHub API error: {r.status_code} - {r.text}")
        issue = r.json()
        return json.dumps({"number": issue["number"], "url": issue["html_url"], "title": issue["title"]}, indent=2)
    except Exception as e:
        return _error(f"Failed to create issue: {e}")


@mcp.tool()
async def gh_list_prs(
    owner: str,
    repo: str,
    state: str = "open",
    page: int = 1,
    per_page: int = 30,
) -> str:
    """List pull requests for a GitHub repository.

    Args:
        owner: Repository owner
        repo: Repository name
        state: PR state: open, closed, all (default 'open')
        page: Page number (default 1)
        per_page: Results per page, max 100 (default 30)
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/repos/{owner}/{repo}/pulls",
                headers=HEADERS, params={"state": state, "page": page, "per_page": per_page}, timeout=30,
            )
        if r.status_code != 200:
            return _error(f"GitHub API error: {r.status_code}")
        prs = [
            {"number": p["number"], "title": p["title"], "state": p["state"],
             "author": p["user"]["login"], "branch": p["head"]["ref"], "baseBranch": p["base"]["ref"],
             "draft": p.get("draft", False), "createdAt": p["created_at"], "url": p["html_url"]}
            for p in r.json()
        ]
        return json.dumps({"total": len(prs), "page": page, "pullRequests": prs}, indent=2)
    except Exception as e:
        return _error(f"Failed to list PRs: {e}")
'''

_PY_TOOLS["slack"] = '''
import httpx


@mcp.tool()
async def slack_list_channels(limit: int = 100, cursor: str | None = None) -> str:
    """List public channels in the Slack workspace.

    Args:
        limit: Max channels to return, 1-200 (default 100)
        cursor: Pagination cursor from a previous response
    """
    try:
        params: dict = {"types": "public_channel", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/conversations.list", headers=HEADERS, params=params, timeout=30)
        data = r.json()
        if not data.get("ok"):
            return _error(f\'Slack API error: {data.get("error")}\', "Check your SLACK_BOT_TOKEN." if data.get("error") == "invalid_auth" else None)
        channels = [
            {"id": c["id"], "name": c["name"], "topic": c.get("topic", {}).get("value", ""),
             "memberCount": c.get("num_members", 0), "isArchived": c.get("is_archived", False)}
            for c in data["channels"]
        ]
        result: dict = {"total": len(channels), "channels": channels}
        next_cursor = data.get("response_metadata", {}).get("next_cursor")
        if next_cursor:
            result["nextCursor"] = next_cursor
        return json.dumps(result, indent=2)
    except Exception as e:
        return _error(f"Failed to list channels: {e}")


@mcp.tool()
async def slack_send_message(channel: str, text: str, thread_ts: str | None = None) -> str:
    """Send a text message to a Slack channel.

    Args:
        channel: Channel ID (e.g., 'C01234ABCDE'). Use slack_list_channels to find IDs.
        text: Message text. Supports Slack markdown (mrkdwn).
        thread_ts: Thread timestamp to reply in a thread
    """
    try:
        payload: dict = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BASE_URL}/chat.postMessage", headers=HEADERS, json=payload, timeout=30)
        data = r.json()
        if not data.get("ok"):
            hint = "Use slack_list_channels to find valid channel IDs." if data.get("error") == "channel_not_found" else None
            return _error(f\'Slack API error: {data.get("error")}\', hint)
        return json.dumps({"channel": data["channel"], "ts": data["ts"], "message": "Message sent successfully"}, indent=2)
    except Exception as e:
        return _error(f"Failed to send message: {e}")


@mcp.tool()
async def slack_channel_history(channel: str, limit: int = 20, cursor: str | None = None) -> str:
    """Get recent messages from a Slack channel.

    Args:
        channel: Channel ID
        limit: Number of messages to return, 1-100 (default 20)
        cursor: Pagination cursor for older messages
    """
    try:
        params: dict = {"channel": channel, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/conversations.history", headers=HEADERS, params=params, timeout=30)
        data = r.json()
        if not data.get("ok"):
            return _error(f\'Slack API error: {data.get("error")}\')
        messages = [
            {"text": m.get("text"), "user": m.get("user"), "ts": m.get("ts"),
             "threadTs": m.get("thread_ts"), "replyCount": m.get("reply_count", 0)}
            for m in data["messages"]
        ]
        result: dict = {"total": len(messages), "messages": messages}
        next_cursor = data.get("response_metadata", {}).get("next_cursor")
        if next_cursor:
            result["nextCursor"] = next_cursor
        return json.dumps(result, indent=2)
    except Exception as e:
        return _error(f"Failed to get channel history: {e}")


@mcp.tool()
async def slack_channel_info(channel: str) -> str:
    """Get detailed information about a Slack channel.

    Args:
        channel: Channel ID (e.g., 'C01234ABCDE')
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/conversations.info", headers=HEADERS, params={"channel": channel}, timeout=30)
        data = r.json()
        if not data.get("ok"):
            return _error(f\'Slack API error: {data.get("error")}\')
        c = data["channel"]
        info = {
            "id": c["id"], "name": c["name"], "topic": c.get("topic", {}).get("value", ""),
            "purpose": c.get("purpose", {}).get("value", ""), "memberCount": c.get("num_members", 0),
            "isArchived": c.get("is_archived", False), "isPrivate": c.get("is_private", False),
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return _error(f"Failed to get channel info: {e}")
'''

_PY_TOOLS["stripe"] = '''
import httpx


@mcp.tool()
async def stripe_list_customers(
    email: str | None = None, limit: int = 10, starting_after: str | None = None
) -> str:
    """List Stripe customers with optional email filter.

    Args:
        email: Filter by exact email address
        limit: Max customers to return, 1-100 (default 10)
        starting_after: Customer ID to start after (for pagination)
    """
    try:
        params: dict = {"limit": limit}
        if email:
            params["email"] = email
        if starting_after:
            params["starting_after"] = starting_after
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/customers", headers=HEADERS, params=params, timeout=30)
        if r.status_code != 200:
            return _error(f"Stripe API error: {r.status_code}", "Check your STRIPE_SECRET_KEY." if r.status_code == 401 else None)
        data = r.json()
        customers = [
            {"id": c["id"], "name": c.get("name"), "email": c.get("email"),
             "currency": c.get("currency"), "balance": c.get("balance", 0)}
            for c in data["data"]
        ]
        return json.dumps({"total": len(customers), "hasMore": data["has_more"], "customers": customers}, indent=2)
    except Exception as e:
        return _error(f"Failed to list customers: {e}")


@mcp.tool()
async def stripe_get_customer(customer_id: str) -> str:
    """Get detailed information about a Stripe customer.

    Args:
        customer_id: Stripe customer ID (starts with 'cus_')
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/customers/{customer_id}", headers=HEADERS, timeout=30)
        if r.status_code == 404:
            return _error(f\'Customer "{customer_id}" not found.\')
        c = r.json()
        return json.dumps({
            "id": c["id"], "name": c.get("name"), "email": c.get("email"), "phone": c.get("phone"),
            "currency": c.get("currency"), "balance": c.get("balance", 0), "metadata": c.get("metadata", {}),
        }, indent=2)
    except Exception as e:
        return _error(f"Failed to get customer: {e}")


@mcp.tool()
async def stripe_list_payments(limit: int = 10, starting_after: str | None = None) -> str:
    """List Stripe payment intents.

    Args:
        limit: Max results, 1-100 (default 10)
        starting_after: Payment intent ID to start after (for pagination)
    """
    try:
        params: dict = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/payment_intents", headers=HEADERS, params=params, timeout=30)
        if r.status_code != 200:
            return _error(f"Stripe API error: {r.status_code}")
        data = r.json()
        payments = [
            {"id": p["id"], "amount": p["amount"] / 100, "currency": p["currency"],
             "status": p["status"], "customer": p.get("customer"), "description": p.get("description")}
            for p in data["data"]
        ]
        return json.dumps({"total": len(payments), "hasMore": data["has_more"], "payments": payments}, indent=2)
    except Exception as e:
        return _error(f"Failed to list payments: {e}")


@mcp.tool()
async def stripe_create_customer(email: str, name: str | None = None, description: str | None = None) -> str:
    """Create a new Stripe customer.

    Args:
        email: Customer email address
        name: Customer full name
        description: Internal description/notes
    """
    try:
        payload: dict = {"email": email}
        if name:
            payload["name"] = name
        if description:
            payload["description"] = description
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/customers", headers=HEADERS,
                data=payload, timeout=30,  # Stripe uses form encoding
            )
        if r.status_code not in (200, 201):
            return _error(f"Stripe API error: {r.status_code} - {r.text}")
        c = r.json()
        return json.dumps({"id": c["id"], "email": c.get("email"), "name": c.get("name")}, indent=2)
    except Exception as e:
        return _error(f"Failed to create customer: {e}")
'''

_PY_TOOLS["notion"] = '''
import httpx

_NOTION_VERSION = "2022-06-28"


def _notion_headers() -> dict[str, str]:
    return {**HEADERS, "Notion-Version": _NOTION_VERSION}


@mcp.tool()
async def notion_search(query: str, filter_type: str | None = None, page_size: int = 10) -> str:
    """Search across all pages and databases in the Notion workspace.

    Args:
        query: Search query text
        filter_type: Filter by 'page' or 'database'
        page_size: Max results, 1-100 (default 10)
    """
    try:
        payload: dict = {"query": query, "page_size": page_size}
        if filter_type in ("page", "database"):
            payload["filter"] = {"property": "object", "value": filter_type}
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BASE_URL}/search", headers=_notion_headers(), json=payload, timeout=30)
        if r.status_code != 200:
            return _error(f"Notion API error: {r.status_code}", "Check your NOTION_API_KEY." if r.status_code == 401 else None)
        data = r.json()
        results = []
        for item in data["results"]:
            title_prop = item.get("properties", {}).get("title", {}).get("title", [])
            name_prop = item.get("properties", {}).get("Name", {}).get("title", [])
            title = (title_prop or name_prop or [{}])[0].get("plain_text", "(untitled)") if (title_prop or name_prop) else "(untitled)"
            results.append({"id": item["id"], "type": item["object"], "title": title, "url": item.get("url"), "lastEdited": item.get("last_edited_time")})
        return json.dumps({"total": len(results), "hasMore": data.get("has_more", False), "results": results}, indent=2)
    except Exception as e:
        return _error(f"Search failed: {e}")


@mcp.tool()
async def notion_get_page(page_id: str) -> str:
    """Get a Notion page by its ID. Returns page properties and metadata.

    Args:
        page_id: Notion page ID (UUID format)
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/pages/{page_id}", headers=_notion_headers(), timeout=30)
        if r.status_code == 404:
            return _error(f"Page not found: {page_id}", "Check the page ID and integration access.")
        return json.dumps(r.json(), indent=2)
    except Exception as e:
        return _error(f"Failed to get page: {e}")


@mcp.tool()
async def notion_query_database(database_id: str, page_size: int = 10, start_cursor: str | None = None) -> str:
    """Query a Notion database. Returns entries with their properties.

    Args:
        database_id: Notion database ID (UUID format)
        page_size: Max results, 1-100 (default 10)
        start_cursor: Pagination cursor from previous response
    """
    try:
        payload: dict = {"page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BASE_URL}/databases/{database_id}/query", headers=_notion_headers(), json=payload, timeout=30)
        if r.status_code != 200:
            return _error(f"Notion API error: {r.status_code}")
        data = r.json()
        return json.dumps({"total": len(data["results"]), "hasMore": data.get("has_more"), "nextCursor": data.get("next_cursor"), "results": data["results"]}, indent=2)
    except Exception as e:
        return _error(f"Failed to query database: {e}")


@mcp.tool()
async def notion_create_page(database_id: str, title: str, content: str | None = None) -> str:
    """Create a new page in a Notion database.

    Args:
        database_id: Parent database ID
        title: Page title
        content: Initial page content (plain text)
    """
    try:
        payload: dict = {
            "parent": {"database_id": database_id},
            "properties": {"Name": {"title": [{"text": {"content": title}}]}},
        }
        if content:
            payload["children"] = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]}}]
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BASE_URL}/pages", headers=_notion_headers(), json=payload, timeout=30)
        if r.status_code not in (200, 201):
            return _error(f"Notion API error: {r.status_code} - {r.text}")
        page = r.json()
        return json.dumps({"id": page["id"], "url": page.get("url"), "title": title}, indent=2)
    except Exception as e:
        return _error(f"Failed to create page: {e}")
'''

_PY_TOOLS["discord"] = '''
import httpx


@mcp.tool()
async def discord_list_guilds() -> str:
    """List all guilds (servers) the bot is a member of."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/users/@me/guilds", headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return _error(f"Discord API error: {r.status_code}", "Check your DISCORD_BOT_TOKEN." if r.status_code == 401 else None)
        guilds = [{"id": g["id"], "name": g["name"], "owner": g.get("owner", False)} for g in r.json()]
        return json.dumps({"total": len(guilds), "guilds": guilds}, indent=2)
    except Exception as e:
        return _error(f"Failed to list guilds: {e}")


@mcp.tool()
async def discord_list_channels(guild_id: str) -> str:
    """List channels in a Discord guild.

    Args:
        guild_id: Discord guild (server) ID
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/guilds/{guild_id}/channels", headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return _error(f"Discord API error: {r.status_code}")
        type_map = {0: "text", 2: "voice", 4: "category", 5: "announcement", 13: "stage", 15: "forum"}
        channels = [
            {"id": c["id"], "name": c["name"], "type": type_map.get(c["type"], f"type_{c['type']}"),
             "position": c.get("position"), "topic": c.get("topic")}
            for c in r.json()
        ]
        return json.dumps({"total": len(channels), "channels": channels}, indent=2)
    except Exception as e:
        return _error(f"Failed to list channels: {e}")


@mcp.tool()
async def discord_send_message(channel_id: str, content: str) -> str:
    """Send a message to a Discord channel.

    Args:
        channel_id: Discord channel ID
        content: Message text content
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/channels/{channel_id}/messages",
                headers=HEADERS, json={"content": content}, timeout=30,
            )
        if r.status_code == 403:
            return _error("Permission denied.", "Bot needs SEND_MESSAGES permission.")
        if r.status_code not in (200, 201):
            return _error(f"Discord API error: {r.status_code}")
        msg = r.json()
        return json.dumps({"id": msg["id"], "channelId": msg["channel_id"], "content": msg["content"]}, indent=2)
    except Exception as e:
        return _error(f"Failed to send message: {e}")


@mcp.tool()
async def discord_get_messages(channel_id: str, limit: int = 25, before: str | None = None) -> str:
    """Get recent messages from a Discord channel.

    Args:
        channel_id: Discord channel ID
        limit: Number of messages, 1-100 (default 25)
        before: Get messages before this message ID (for pagination)
    """
    try:
        params: dict = {"limit": limit}
        if before:
            params["before"] = before
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/channels/{channel_id}/messages", headers=HEADERS, params=params, timeout=30)
        if r.status_code != 200:
            return _error(f"Discord API error: {r.status_code}")
        messages = [
            {"id": m["id"], "content": m.get("content"), "author": m.get("author", {}).get("username"),
             "timestamp": m.get("timestamp")}
            for m in r.json()
        ]
        return json.dumps({"total": len(messages), "messages": messages}, indent=2)
    except Exception as e:
        return _error(f"Failed to get messages: {e}")
'''
