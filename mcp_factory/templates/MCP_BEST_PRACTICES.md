# MCP Server Development — Best Practices Reference

> Stored locally for MCP Factory code generation. Source: Claude Desktop MCP Builder Skill.

---

## Core Principles

### 1. Tool Naming & Discoverability
- Use consistent prefixes: `github_create_issue`, `github_list_repos`
- Action-oriented naming: verb_noun format
- Clear, descriptive names help agents find the right tools quickly

### 2. Tool Annotations (REQUIRED on all generated tools)
Every tool must include annotations:
```json
{
  "readOnlyHint": true,      // Does this tool only read data?
  "destructiveHint": false,  // Could this tool delete/modify data?
  "idempotentHint": true,    // Is calling this multiple times safe?
  "openWorldHint": false     // Does this interact with external systems?
}
```

### 3. Input Schemas
- TypeScript: Use Zod with `.describe()` on every field
- Python: Use Pydantic models or type hints with `Field(description=...)`
- Include constraints (min/max, patterns, enums)
- Add examples in field descriptions

### 4. Output Schemas
- Define `outputSchema` where possible for structured data
- Use `structuredContent` in tool responses (TypeScript SDK)
- Return both text content and structured data

### 5. Error Handling
- Actionable error messages that guide toward solutions
- Include specific suggestions and next steps
- Use `isError: true` in responses for error conditions
- Never expose raw stack traces

### 6. Response Format
- JSON for structured data that agents will process
- Markdown for human-readable responses
- Keep responses concise — agents benefit from focused data

### 7. Pagination
- Support pagination on list operations
- Use cursor-based pagination where possible
- Include total count when available
- Default to reasonable page sizes (20-50 items)

### 8. Transport
- **stdio**: For local servers (Claude Desktop, local tools)
- **Streamable HTTP**: For remote/deployed servers
- Default to stdio for local-first approach

### 9. Security
- Validate all inputs
- Never expose credentials in responses
- Use environment variables for secrets
- Sanitize file paths to prevent directory traversal

---

## TypeScript Patterns

### Server Setup
```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({
  name: "server-name",
  version: "1.0.0",
});
```

### Tool Registration with Annotations
```typescript
server.tool(
  "tool_name",
  "Clear description of what this tool does",
  {
    param: z.string().describe("Description of parameter"),
  },
  async ({ param }) => {
    // Implementation
    return {
      content: [{ type: "text", text: result }],
    };
  },
  {
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  }
);
```

### Dependencies
```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "zod": "^3.22.0"
  }
}
```

---

## Python Patterns

### Server Setup (FastMCP)
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("server-name")
```

### Tool Registration
```python
@mcp.tool()
async def tool_name(param: str) -> str:
    """Clear description of what this tool does.
    
    Args:
        param: Description of parameter
    """
    # Implementation
    return result
```

### Dependencies
```toml
[project]
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0.0",
    "httpx>=0.27.0",
]
```

---

## Quality Checklist

- [ ] All tools have clear, descriptive names with consistent prefixes
- [ ] All tools have annotations (readOnlyHint, destructiveHint, etc.)
- [ ] All parameters have Zod/Pydantic descriptions
- [ ] Error messages are actionable with next steps
- [ ] List operations support pagination
- [ ] No duplicated code (DRY)
- [ ] Full type coverage
- [ ] Input validation on all parameters
- [ ] Secrets via environment variables only
- [ ] README with setup + Claude Desktop config
