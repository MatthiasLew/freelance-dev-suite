# Model Context Protocol (MCP) Server

`freelance-dev-suite` includes a local STDIO-based Model Context Protocol (MCP) server. This allows AI assistants and coding environments (such as Cursor, Claude Desktop, Copilot, and Continue.dev) to interact directly with your freelance workspace, jobs, requirements, scope, and timeline.

---

## 1. Starting the Server

The server communicates via JSON-RPC 2.0 over standard input/output (`stdio`).

```bash
freelance mcp serve
# or targeting a custom workspace:
freelance mcp serve --workspace /path/to/custom/workspace
```

---

## 2. Editor Configuration

### Cursor (`~/.cursor/mcp.json` or Project Settings)
```json
{
  "mcpServers": {
    "freelance": {
      "command": "freelance",
      "args": ["mcp", "serve"]
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "freelance": {
      "command": "freelance",
      "args": ["mcp", "serve"]
    }
  }
}
```

---

## 3. Available Tools

The MCP server exposes 9 specialized tools covering the entire business lifecycle:

| Tool Name | Type | Description | Required Arguments |
| :--- | :---: | :--- | :--- |
| `list_jobs` | Query | List active (and optionally completed) freelance jobs. | `include_finished` (bool, optional) |
| `get_job_status` | Query | Get detailed metadata and status for a specific job. | `job_id` (string) |
| `get_requirements` | Query | Retrieve acceptance criteria and functional specifications. | `job_id` (string) |
| `get_scope_changes`| Query | Retrieve detected scope changes and surcharges. | `job_id` (string) |
| `get_work_sessions`| Query | List tracked implementation sessions, diffs, and notes. | `job_id` (string) |
| `get_profitability`| Query | Retrieve financial breakdown, billable vs actual margin. | `job_id` (string) |
| `get_timeline` | Query | Retrieve chronological append-only audit event log. | `job_id` (string) |
| `create_job` | Mutation | Create a new client engagement workspace. | `client` (string), `description` (string) |
| `check_scope` | Mutation | Check client request text against scope and calculate surcharge. | `job_id` (string), `request_text` (string) |

---

## 4. Privacy & Secret Masking

All data returned through tool calls is automatically sanitized through `mask_text`. API keys, tokens, and database credentials are automatically redacted before reaching the AI model context.
