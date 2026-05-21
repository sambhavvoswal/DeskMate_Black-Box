# DeskMate Production Deployment Strategy (Enterprise Scaling)

This document details the production design architecture for deploying the DeskMate IT Helpdesk AI Assistant at scale, emphasizing security, auditing compliance, and high availability.

---

## 1. Startup Connectivity Checks & Degraded Mode

To prevent API gateways or container orchestration nodes from marking containers as unhealthy if the database is temporarily unreachable, DeskMate implements a **resilient startup sequence**:

1.  **Ping Health Check**: On startup, the FastAPI server invokes `mongo_client.check_db_health()`, executing a ping command with a short server-selection timeout (`serverSelectionTimeoutMS`).
2.  **Warn, Don't Crash**: If MongoDB Atlas is offline:
    *   FastAPI logs a critical warning.
    *   The server continues booting successfully rather than raising a system exit crash.
3.  **Graceful Degraded Mode Fallback**:
    *   The web app remains online.
    *   When queries require MongoDB connectivity (e.g., loading history or running tool entitlement checks), the mongo client intercepts PyMongo errors.
    *   It returns standard error structures (`{"error": "Database offline"}`) rather than throwing internal unhandled 500 errors.
    *   The AI agent receives the error description in its tool reasoning history and generates a polite, contextual warning for the user, allowing the chat screen to remain fully responsive.

---

## 2. Auditing, Compliance & Logging Architecture

For regulatory compliance and operations monitoring, all agent actions are logged to a dedicated audit collection:

```
[Agent Loop Execution]
       │
       ├──► Execute Tool (e.g. check_software_entitlement)
       │
       └──► Invoke log_audit()
                 │
                 └──► Write to deskmate_history.audit_logs collection
```

### Telemetry Schema:
Every tool execution writes an entry containing:
*   `timestamp`: ISO 8601 string.
*   `username`: Session ID of the employee executing the query.
*   `tool_name`: Exact python tool name.
*   `input`: Dictionary of arguments passed to the tool.
*   `output`: Dictionary of values returned by the tool.
*   `response_time_ms`: Duration of the tool execution in milliseconds.

This database-level audit log is separate from system logs, ensuring that security audits have a tamper-resistant record of all ticket actions.

---

## 3. Dual-Provider AI Orchestration

To conserve API token costs and balance response speeds, DeskMate supports dynamic orchestration across two different AI providers:

| Priority | Provider | Model Identifier | Config Key |
|---|---|---|---|
| **1 (Primary)** | OpenRouter (Gemini) | `google/gemini-2.0-flash-001` | `OPENROUTER_API_KEY` |
| **2 (Fallback)** | Anthropic (Claude) | `claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |

### Provider Selection Flow:
1.  **Config Initialization**: The application inspects `.env` configuration keys at startup.
2.  **Key-based Routing**:
    *   If `OPENROUTER_API_KEY` is present, it uses OpenRouter completions (requesting Gemini 2.0 Flash) to process requests.
    *   If the OpenRouter key is missing but `ANTHROPIC_API_KEY` is available, it routes queries to the Anthropic Messages API.
    *   If neither is present, it logs a critical error and raises an exception.
3.  **UI Badge Sync**: The endpoint `/api/provider` exposes this state. The frontend header reads this config to display an active provider badge (Amber for Claude, Blue for OpenRouter/Gemini).

---

## 4. Observability & Latency Tracking

Telemetry timing metrics are generated in-memory during the agent loop execution in [agent.py]
*   **API Latency**: Timed using `datetime.utcnow()` markers surrounding the completions endpoint request, recorded as `duration_ms` in the trace.
*   **Tool Latency**: Timed surrounding tool execution, recorded as `duration_ms` inside trace steps.
*   **Provider Tracking**: Every step includes the provider name metadata. This is returned to the client and rendered in the frontend Execution Trace panel, giving administrators a clear view of where bottlenecks occur.

---

## 5. Security & Rate Limiting

To transition from this POC to enterprise-grade operations:
1.  **Identity Management**: Integrate FastAPI with **Microsoft Entra ID** (Azure AD). Replace mock username selectors with JWT token verification.
2.  **Inbound Rate Limiting**: Apply rate-limiting policies at the API gateway layer (e.g. Azure API Management) to restrict employees to a maximum number of prompts per hour, protecting API token budgets from abuse.
