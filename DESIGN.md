# DeskMate Architectural Choices & Design Decisions

This document outlines the architectural decisions and design patterns implemented in the DeskMate IT Helpdesk AI Assistant.

---

## 1. Native Tool Calling & Dynamic Dispatch Routing

Instead of hardcoded conditional logic (e.g. nested if-else blocks checking for requested tool names), DeskMate utilizes a **Centralized Tool Registry** in `agent.py` combined with Python's reflection capabilities (`inspect` module) to run tools dynamically.

### Implementation Architecture:
```python
TOOL_REGISTRY = {
    "check_software_entitlement": tools.check_software_entitlement,
    "create_access_ticket": tools.create_access_ticket,
    "get_ticket_status": tools.get_ticket_status
}
```

### Dynamic Dispatch Engine:
When the LLM decides to call a tool, `execute_tool()` handles parameter resolution:
1.  **Registry Match**: The tool name is validated against `TOOL_REGISTRY`.
2.  **Signature Inspection**: Using `inspect.signature(func)`, the engine examines the parameters that the Python function actually expects.
3.  **Context-Aware Binding**:
    *   If the function expects a parameter name present in the LLM's arguments (e.g. `software_name` or `priority`), it maps it directly.
    *   If the function expects `username` (which the LLM might omit or spoof), it is bound dynamically using the backend's authenticated username session context.
    *   Parameters that have default values in Python are resolved, and safe fallbacks are applied for missing arguments to prevent runtime errors.
4.  **Execution**: The function is executed with the resolved arguments: `func(**kwargs)`.

### Benefits:
*   **Extensibility**: Adding a new tool is a one-liner: define the function in `tools.py` and register it in `TOOL_REGISTRY`. The dispatch engine handles the rest.
*   **Decoupled Logic**: System parameters (like session-authenticated usernames) are injected in a secure boundary without relying on the LLM to provide them.

---

## 2. Strong Schema Validation with Pydantic

To enforce type-safety and request-response consistency, DeskMate defines all data shapes in [schemas.py]using Pydantic (v2).

### Models Defined:
*   `ChatRequest`: Validates inbound query text and session username from the frontend client.
*   `ChatResponse`: Enforces a uniform response schema, including the agent's reply, execution traces, timing metadata, and provider parameters.
*   `TicketCreate` & `EmployeeProfile`: Standardize MongoDB document representations.
*   `ActiveProviderResponse`: Models configuration data returned by the configuration endpoint.

By declaring these at the FastAPI controller layer, DeskMate prevents malformed payloads from penetrating the agent system, avoiding useless, expensive API calls to LLM providers.

---

## 3. Database Architecture: MongoDB Atlas

DeskMate utilizes MongoDB Atlas across two logical namespaces to store entitlements and manage chat states.

### A. Core Operational Database (`deskmate`):
*   `employee_entitlements`: Houses employee profile metadata (department, name) and a dictionary mapping software keys to access booleans (e.g., `{"jira": true, "adobe_creative_suite": false}`).
*   `it_tickets`: Records created tickets with fields for `ticket_id`, `software_name`, `priority`, `description`, `status`, and `created_at`.

### B. User Session & History Database (`deskmate_history`):
*   `chat_history`: Stores conversational records per user.
    *   **Context Optimization**: To optimize token consumption and prevent context window exhaustion, DeskMate retrieves the full history but only sends the **last 8 messages** (4 user turns) to the LLM.
    *   **Conversation Caps**: A session limit of **10 messages** is enforced. If a session reaches this size, the FastAPI endpoint returns a message indicating the limit has been reached, disabling further inputs until the user clicks the "New Chat" button to clear history.
*   `audit_logs`: A compliance collection logging every tool invocation.
    ```json
    {
      "timestamp": "2026-05-21T15:00:00Z",
      "username": "employee_one",
      "tool_name": "check_software_entitlement",
      "input": { "software_name": "adobe_creative_suite" },
      "output": { "has_access": false },
      "response_time_ms": 120
    }
    ```

---

## 4. Input Sanitization & Soft Aliasing

LLMs and end-users often submit varied names for software (e.g., "photoshop", "Adobe", "Creative Suite"). If query parameters were mapped directly to database keys, lookups would fail.

DeskMate addresses this via `SOFTWARE_ALIAS_MAP` in [tools.py]:
*   Before calling any database lookup or creating a ticket, user-facing inputs are passed through `sanitize_software_name(software_name)`.
*   Common variations are resolved to canonical database keys:
    *   `"photoshop"` / `"illustrator"` / `"adobe"` ──► `"adobe_creative_suite"`
    *   `"excel"` / `"word"` / `"m365"` / `"office"` ──► `"office_365"`
    *   `"cisco vpn"` / `"anyconnect"` ──► `"vpn_access"`
*   This mapping preserves natural language flexibility while guaranteeing strict database key matches.

---

## 5. Observability Execution Trace

Every backend chat response contains an `execution_trace` list, tracking:
1.  **API Latency & Consumption**: Records API request durations in milliseconds (`duration_ms`), input/output token counts, and target model versions.
2.  **Tool Latency & Parameters**: Records tool execution runtimes in milliseconds (`duration_ms`), input arguments, and raw returned values.
3.  **Active AI Provider Configuration**: Appends the active provider name (`provider`) to each trace block for compliance tracking.

---

## 6. Ticket History Modal & Query Endpoint

To enable employees to view their raised tickets asynchronously without talking to the AI agent:
*   **Decoupled Retrieval Endpoint**: A dedicated GET route `/api/tickets/{username}` fetches tickets directly from MongoDB `it_tickets` collection, bypassing LLM processing entirely to save tokens.
*   **Client-Side Overlay (Modal)**: A responsive popup overlay rendering details (Ticket ID, Software Name, Priority, and Status) is managed in [index.html] with Vanilla JS and styled using CSS transitions.

