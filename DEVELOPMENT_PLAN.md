# DeskMate IT Helpdesk AI Assistant — Development Plan

## Project Overview

Build a production-grade Python POC for DeskMate, an AI-powered IT helpdesk assistant. The system handles natural-language employee queries, uses Claude's native tool calling to decide what actions to take, reads/writes to a live MongoDB Atlas cluster, and replies with intelligent, context-aware responses.

**Core Example Query:**
```
"I need access to Adobe Creative Suite — if I'm not already entitled, please raise a high-priority ticket for it."
```

The system must:
- Orchestrate multi-step reasoning (check entitlement → conditionally create ticket → respond)
- Gracefully refuse out-of-scope queries
- Handle errors (missing data, network timeouts, malformed input)
- Provide full observability (trace every decision end-to-end)

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| LLM + Tool Use | Anthropic Claude API + `anthropic` SDK | Native function calling, battle-tested, clear error messages, easy to trace |
| Backend | FastAPI | Minimal boilerplate, async-ready, built-in request validation |
| Database | MongoDB Atlas + `pymongo` | Live data storage, realistic IT system simulation, easy seed/reset |
| Frontend | Single HTML file (vanilla JS + fetch) | No build step, ships with repo, clean separation of concerns |
| Environment | `python-dotenv` for secrets | Clean env var management, no hardcoded keys |
| Logging | Python `logging` module | Observable execution, trace tool calls and decisions |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (HTML/JS)                       │
│         Chat UI with observability sidebar                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ POST /api/chat
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              FASTAPI BACKEND (app.py)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. Validate user input & employee context           │  │
│  │  2. Call Agent (agent.py)                            │  │
│  │  3. Return response + execution trace                │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────┬───────────────────────────────────────────────┘
               │
               ├─────────────────┬────────────────────┐
               ▼                 ▼                    ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │  Agent Loop  │  │   Tools      │  │   Logging    │
         │ (agent.py)   │  │ (tools.py)   │  │ (config.py)  │
         └──────┬───────┘  └──────┬───────┘  └──────────────┘
                │                 │
                │                 │
                └────────┬────────┘
                         ▼
         ┌───────────────────────────────────┐
         │    MongoDB Atlas Connection       │
         │         (mongo_client.py)         │
         │                                   │
         │  Collections:                     │
         │  • employee_entitlements          │
         │  • it_tickets                     │
         │  • audit_logs (optional)          │
         └───────────────────────────────────┘
```

---

## File Structure & Specifications

### 1. `config.py` — Configuration & Logging Setup

**Purpose:** Centralized environment loading, logger configuration, constants.

**Key Exports:**
- `ANTHROPIC_API_KEY` — from `os.getenv("ANTHROPIC_API_KEY")`
- `MONGO_URI` — from `os.getenv("MONGO_URI")`
- `MONGO_DB_NAME` — from `os.getenv("MONGO_DB_NAME", "deskmate")`
- `logger` — Python logger configured with timestamps and level INFO
- `CLAUDE_MODEL` — Constant: `"claude-3-5-sonnet-20241022"`
- `TOOL_TIMEOUT_SECONDS` — Constant: `30`

**Implementation Notes:**
- Use `python-dotenv` to load `.env` file
- Validate that `ANTHROPIC_API_KEY` and `MONGO_URI` are present; raise `ValueError` if missing
- Configure logger to output to console with format: `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`

---

### 2. `mongo_client.py` — MongoDB Atlas Connection

**Purpose:** Initialize MongoDB connection, seed baseline data, provide query/write wrappers.

**Key Functions:**

#### `get_mongo_client() -> pymongo.MongoClient`
- Initialize and return MongoClient using `MONGO_URI` from config
- Wrap in try-except for connection errors; log failures

#### `get_database() -> pymongo.database.Database`
- Return the database object using `MONGO_DB_NAME`

#### `seed_database_if_empty()`
- Called once at app startup
- Ensure `employee_entitlements` collection exists with baseline test profiles:
  ```json
  {
    "username": "employee_one",
    "name": "Alice Johnson",
    "department": "Engineering",
    "entitlements": {
      "adobe_creative_suite": false,
      "office_365": true,
      "vpn_access": true,
      "jira": true,
      "slack": true
    },
    "created_at": "2025-01-01T00:00:00Z"
  }
  ```
  ```json
  {
    "username": "employee_two",
    "name": "Bob Smith",
    "department": "Marketing",
    "entitlements": {
      "adobe_creative_suite": true,
      "office_365": true,
      "vpn_access": true,
      "jira": false,
      "slack": true
    },
    "created_at": "2025-01-01T00:00:00Z"
  }
  ```
- Ensure `it_tickets` collection exists (empty initially)
- Log seeding completion

#### `get_employee_profile(username: str) -> dict | None`
- Query `employee_entitlements` for matching username
- Return full profile dict or None if not found
- Log query with result status

#### `check_entitlement(username: str, software_name: str) -> dict`
- Query employee profile
- Return: `{"has_access": bool, "entitlements": dict, "employee_name": str}`
- If employee not found, return `{"error": "Employee not found", "username": username}`

#### `create_ticket(username: str, software_name: str, priority: str, description: str) -> dict`
- Insert into `it_tickets` collection:
  ```json
  {
    "ticket_id": "TKT-<random-6-digit-number>",
    "username": username,
    "software_name": software_name,
    "priority": priority,
    "description": description,
    "status": "open",
    "created_at": "ISO-8601-timestamp",
    "assignee": null
  }
  ```
- Return the inserted ticket dict (with generated ticket_id)
- Log ticket creation with ticket_id

#### `get_ticket_status(ticket_id: str) -> dict`
- Query `it_tickets` for matching ticket_id
- Return full ticket dict or `{"error": "Ticket not found"}`

**Error Handling:**
- Wrap all database operations in try-except for `pymongo.errors.PyMongoError`
- Log errors with full context (function name, input, error message)
- Return error dict to caller (do not raise; let agent handle)

---

### 3. `tools.py` — Tool Definitions for Claude

**Purpose:** Define tool functions that Claude will call via function_calling. These are the bridge between LLM reasoning and deterministic system operations.

**Tool 1: `check_software_entitlement`**
```
Input:
  - username: str
  - software_name: str

Output:
  {
    "username": str,
    "software_name": str,
    "has_access": bool,
    "employee_name": str,
    "employee_department": str,
    "message": str
  }

Implementation:
- Call mongo_client.check_entitlement(username, software_name)
- Parse response and format as above
- Log the call and result
```

**Tool 2: `create_access_ticket`**
```
Input:
  - username: str
  - software_name: str
  - priority: str (one of: "low", "medium", "high", "critical")
  - description: str

Output:
  {
    "ticket_id": str,
    "username": str,
    "software_name": str,
    "priority": str,
    "status": "open",
    "message": str
  }

Implementation:
- Validate priority is one of allowed values
- Call mongo_client.create_ticket(...)
- Return formatted response
- Log ticket creation
```

**Tool 3: `get_ticket_status`**
```
Input:
  - ticket_id: str

Output:
  {
    "ticket_id": str,
    "username": str,
    "software_name": str,
    "priority": str,
    "status": str,
    "created_at": str,
    "assignee": str | null,
    "message": str
  }

Implementation:
- Call mongo_client.get_ticket_status(ticket_id)
- Return formatted response
- Log query
```

**Tool Definitions (for Claude SDK):**
Each tool must be defined as a dict in the format that `anthropic.Anthropic.messages()` expects:
```python
tools = [
    {
        "name": "check_software_entitlement",
        "description": "Check if an employee has access to a specific software. Returns true/false and employee details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "The employee's username (e.g., 'employee_one')"
                },
                "software_name": {
                    "type": "string",
                    "description": "The name of the software (e.g., 'Adobe Creative Suite', 'Jira')"
                }
            },
            "required": ["username", "software_name"]
        }
    },
    # ... similarly for create_access_ticket, get_ticket_status
]
```

**Error Handling in Tools:**
- All functions return a dict; never raise exceptions
- Include "error" key in response if something goes wrong
- Log all errors with full context

---

### 4. `agent.py` — Claude Tool-Use Orchestration

**Purpose:** Implement the core reasoning loop where Claude decides what to do and executes tools.

**Key Function: `run_agent(user_message: str, username: str) -> dict`**

**Algorithm:**

```
1. Initialize Anthropic client: client = Anthropic(api_key=ANTHROPIC_API_KEY)

2. System prompt:
   "You are DeskMate, an IT helpdesk assistant. You help employees with:
    - Checking software entitlements
    - Requesting access to software
    - Checking ticket status
    
    You can ONLY handle IT-related requests. For anything outside IT scope
    (e.g., HR questions, personal advice), politely refuse.
    
    When an employee asks for software access you don't have, always offer
    to create a ticket with priority 'high'.
    
    Be concise, helpful, and always include relevant details in your response.
    
    Current employee: {username}"

3. Initialize messages = [{"role": "user", "content": user_message}]

4. Initialize execution_trace = [] (for observability)

5. LOOP (max iterations: 10):
   a. Call client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=system_prompt,
        tools=tools_list,
        messages=messages
      )
   
   b. Log the response (model's reasoning, tool calls)
      - Add to execution_trace
   
   c. Check response.stop_reason:
      - If "end_turn": Model is done. Extract text response. BREAK.
      - If "tool_use": Model wants to call tools. Continue to step (d).
   
   d. For each tool_use block in response.content:
      - Extract tool_name and tool_input
      - Call the corresponding function in tools.py
      - Log: "Tool called: {tool_name} with input {tool_input}, result: {result}"
      - Add to execution_trace
   
   e. Append assistant response to messages
   
   f. Append tool result to messages:
      {
        "role": "user",
        "content": [
          {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps(tool_result)
          }
        ]
      }
   
   g. Continue loop (next iteration sends updated messages to Claude)

6. AFTER LOOP:
   - Extract final text response from messages
   - Return {
       "response": final_text_response,
       "execution_trace": execution_trace,
       "username": username,
       "status": "success" | "error"
     }

Exception Handling:
- Catch anthropic.APIError, anthropic.RateLimitError, anthropic.APIConnectionError
- Log full error with context
- Return {
    "response": "I encountered an error processing your request. Please try again.",
    "execution_trace": [{error details}],
    "status": "error",
    "error": str(exception)
  }
```

**Logging:**
- Log each Claude API call (model, max_tokens, tool count)
- Log each tool invocation (name, input, output)
- Log loop iterations and stop reasons
- Log total time taken

**Observability:**
- `execution_trace` is a list of dicts, each capturing one step:
  ```python
  {
    "step": 1,
    "type": "api_call" | "tool_call" | "observation",
    "timestamp": ISO-8601,
    "data": {...}
  }
  ```

---

### 5. `app.py` — FastAPI Backend & Static File Serving

**Purpose:** REST API endpoint for chat, serve frontend, handle request validation.

**Core Endpoint: `POST /api/chat`**

```
Request Body:
{
  "message": str,
  "username": str
}

Response:
{
  "response": str,
  "execution_trace": list[dict],
  "username": str,
  "status": "success" | "error",
  "timestamp": str
}
```

**Implementation:**
```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json

app = FastAPI(title="DeskMate", version="1.0.0")

class ChatRequest(BaseModel):
    message: str
    username: str = "employee_one"

@app.post("/api/chat")
async def chat(req: ChatRequest):
    # Validate
    if not req.message or len(req.message.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if not req.username or len(req.username.strip()) == 0:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    
    # Run agent
    try:
        result = run_agent(req.message, req.username)
        return result
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Seed database
    seed_database_if_empty()
    
    # Run server
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Startup:**
- Call `seed_database_if_empty()` before starting server
- Log successful startup with model info and MongoDB connection status

---

### 6. `frontend/index.html` — Chat UI with Observability

**Purpose:** Single-file HTML chat interface with split-screen observability panel.

**Structure:**
```html
<!DOCTYPE html>
<html>
<head>
  <title>DeskMate IT Helpdesk</title>
  <style>
    /* Two-column layout: chat (2/3) + observability (1/3) */
    /* Clean, minimal design */
    /* Responsive: stack vertically on mobile */
  </style>
</head>
<body>
  <div class="container">
    <!-- LEFT: Chat Interface (2/3 width) -->
    <div class="chat-column">
      <div class="chat-header">
        <h1>DeskMate IT Helpdesk</h1>
        <p>Ask questions about software access, tickets, and IT support.</p>
      </div>
      
      <div class="chat-messages" id="chatMessages">
        <!-- Messages populated by JS -->
      </div>
      
      <div class="chat-input-area">
        <select id="employeeSelect">
          <option value="employee_one">Alice Johnson (employee_one)</option>
          <option value="employee_two">Bob Smith (employee_two)</option>
        </select>
        
        <div class="input-group">
          <input
            type="text"
            id="messageInput"
            placeholder="Ask a question (e.g., 'I need Adobe Creative Suite access')..."
            onkeypress="handleKeyPress(event)"
          />
          <button id="sendBtn" onclick="sendMessage()">Send</button>
        </div>
      </div>
    </div>
    
    <!-- RIGHT: Observability Pane (1/3 width) -->
    <div class="observability-column">
      <div class="observability-header">
        <h3>Execution Trace</h3>
        <button onclick="clearTrace()">Clear</button>
      </div>
      
      <div class="trace-content" id="traceContent">
        <p style="color: #999;">Awaiting first request...</p>
      </div>
    </div>
  </div>

  <script>
    const API_BASE = "http://localhost:8000";
    let currentUsername = "employee_one";

    async function sendMessage() {
      const messageInput = document.getElementById("messageInput");
      const message = messageInput.value.trim();
      const username = document.getElementById("employeeSelect").value;
      
      if (!message) return;
      
      currentUsername = username;
      
      // Add user message to chat
      addMessageToChat("User", message, "user");
      messageInput.value = "";
      
      // Disable send button
      document.getElementById("sendBtn").disabled = true;
      
      try {
        const response = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, username })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        // Add assistant response
        addMessageToChat("DeskMate", data.response, "assistant");
        
        // Update execution trace
        updateTrace(data.execution_trace);
        
      } catch (error) {
        addMessageToChat("DeskMate", `Error: ${error.message}`, "error");
        updateTrace([{ error: error.message }]);
      } finally {
        document.getElementById("sendBtn").disabled = false;
        document.getElementById("messageInput").focus();
      }
    }

    function addMessageToChat(sender, text, role) {
      const messagesDiv = document.getElementById("chatMessages");
      const msgDiv = document.createElement("div");
      msgDiv.className = `message ${role}`;
      msgDiv.innerHTML = `<strong>${sender}:</strong> ${escapeHtml(text)}`;
      messagesDiv.appendChild(msgDiv);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function updateTrace(trace) {
      const traceDiv = document.getElementById("traceContent");
      traceDiv.innerHTML = `<pre>${JSON.stringify(trace, null, 2)}</pre>`;
    }

    function clearTrace() {
      document.getElementById("traceContent").innerHTML = '<p style="color: #999;">Trace cleared</p>';
    }

    function handleKeyPress(event) {
      if (event.key === "Enter") {
        sendMessage();
      }
    }

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }

    // Initialize
    document.getElementById("employeeSelect").addEventListener("change", (e) => {
      currentUsername = e.target.value;
    });
  </script>

  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      height: 100vh;
      overflow: hidden;
    }
    
    .container {
      display: flex;
      height: 100vh;
    }
    
    .chat-column {
      flex: 2;
      display: flex;
      flex-direction: column;
      background: white;
      border-right: 1px solid #ddd;
      overflow: hidden;
    }
    
    .observability-column {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: #f9f9f9;
      overflow: hidden;
    }
    
    .chat-header {
      padding: 20px;
      border-bottom: 1px solid #ddd;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
    }
    
    .chat-header h1 { font-size: 24px; margin-bottom: 5px; }
    .chat-header p { font-size: 14px; opacity: 0.9; }
    
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
    }
    
    .message {
      margin-bottom: 15px;
      padding: 12px;
      border-radius: 8px;
      word-wrap: break-word;
    }
    
    .message.user {
      background: #e3f2fd;
      border-left: 4px solid #2196F3;
    }
    
    .message.assistant {
      background: #f1f1f1;
      border-left: 4px solid #999;
    }
    
    .message.error {
      background: #ffebee;
      border-left: 4px solid #f44336;
      color: #c62828;
    }
    
    .chat-input-area {
      padding: 20px;
      border-top: 1px solid #ddd;
      background: white;
    }
    
    #employeeSelect {
      width: 100%;
      padding: 10px;
      margin-bottom: 10px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
    }
    
    .input-group {
      display: flex;
      gap: 10px;
    }
    
    #messageInput {
      flex: 1;
      padding: 10px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
    }
    
    #sendBtn {
      padding: 10px 20px;
      background: #667eea;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-weight: 600;
    }
    
    #sendBtn:hover { background: #764ba2; }
    #sendBtn:disabled { opacity: 0.5; cursor: not-allowed; }
    
    .observability-header {
      padding: 15px;
      border-bottom: 1px solid #ddd;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: white;
    }
    
    .observability-header h3 { font-size: 14px; }
    .observability-header button {
      padding: 5px 10px;
      background: #f44336;
      color: white;
      border: none;
      border-radius: 3px;
      cursor: pointer;
      font-size: 12px;
    }
    
    .trace-content {
      flex: 1;
      overflow-y: auto;
      padding: 15px;
      font-family: "Courier New", monospace;
      font-size: 12px;
      background: #fafafa;
    }
    
    .trace-content pre {
      background: white;
      padding: 10px;
      border-radius: 4px;
      border: 1px solid #ddd;
      overflow-x: auto;
      max-height: 100%;
    }
    
    @media (max-width: 900px) {
      .container { flex-direction: column; }
      .observability-column { border-right: none; border-top: 1px solid #ddd; }
    }
  </style>
</body>
</html>
```

---

### 7. `requirements.txt`

```
anthropic==0.34.2
fastapi==0.109.0
uvicorn==0.27.0
pymongo==4.6.0
dnspython==2.4.2
python-dotenv==1.0.0
pydantic==2.5.0
```

---

### 8. `.env` (Template — DO NOT COMMIT)

```
ANTHROPIC_API_KEY=sk-ant-...
MONGO_URI=mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=deskmate
```

---

## Execution Flow Examples

### Example 1: Single-Step Query

```
User: "Do I have access to Jira?"
Username: "employee_one"

→ Claude receives: "Do I have access to Jira?"
→ Claude calls: check_software_entitlement(username="employee_one", software_name="Jira")
→ Tool returns: {"has_access": true, "employee_name": "Alice Johnson", ...}
→ Claude responds: "Yes, you have access to Jira. You're all set!"
→ Response sent to frontend with execution_trace showing all steps
```

### Example 2: Multi-Step Query (Conditional Logic)

```
User: "I need Adobe Creative Suite. If I don't have it, please create a ticket."
Username: "employee_one"

→ Claude receives message
→ Claude calls: check_software_entitlement(username="employee_one", software_name="Adobe Creative Suite")
→ Tool returns: {"has_access": false, ...}
→ Claude observes: User doesn't have access, so create ticket
→ Claude calls: create_access_ticket(
    username="employee_one",
    software_name="Adobe Creative Suite",
    priority="high",
    description="Employee requested access to Adobe Creative Suite via DeskMate"
  )
→ Tool returns: {"ticket_id": "TKT-892345", "status": "open", ...}
→ Claude responds: "You don't currently have access to Adobe Creative Suite, but I've created a high-priority ticket (TKT-892345) for you. The IT team will review it shortly."
→ Full execution_trace shows: check → decision → create_ticket → response
```

### Example 3: Out-of-Scope Query

```
User: "Should I take this job offer?"
Username: "employee_one"

→ Claude receives message
→ Claude recognizes: This is not IT-related
→ Claude responds: "I can only help with IT-related requests like software access, ticket status, and VPN issues. For career advice, please reach out to HR."
→ execution_trace shows no tool calls (system prompt rejection)
```

---

## Error Handling Strategy

### 1. **Malformed Input**
- Empty message → HTTP 400 with clear error message
- Missing username → Default to "employee_one" or return 400
- Logged with request context

### 2. **Database Errors**
- MongoDB connection timeout → Tool returns error dict
- Claude sees error and responds: "I encountered a temporary issue accessing employee data. Please try again."
- Error logged with full stack trace

### 3. **Invalid Tool Input**
- Claude calls `create_access_ticket` with priority="urgent" (not in allowed list)
- Tool validates and returns: `{"error": "Invalid priority. Must be one of: low, medium, high, critical"}`
- Claude sees error and asks user to clarify or retries with valid priority
- Logged as "Tool validation error"

### 4. **Tool Execution Timeout**
- If tool takes >30 seconds, Claude times out
- Tool returns: `{"error": "Request timed out. Please try again."}`
- Claude handles gracefully in response
- Logged as "Tool timeout"

### 5. **API Rate Limit**
- Catch `anthropic.RateLimitError` in agent loop
- Return: `{"status": "error", "response": "Service is temporarily busy. Please wait a moment and try again."}`
- Logged for monitoring

### 6. **Out-of-Scope Intent**
- No explicit detection; Claude's system prompt handles this
- Claude declines politely: "I can only help with IT support questions..."
- execution_trace shows "no tools called" (only LLM response)

---

## Deployment Considerations (Production Note Reference)

These are the load-bearing decisions for the production design document:

1. **Tool Safety:** Function calling is deterministic. Constraining Claude to only call predefined tools prevents prompt injection.
2. **Observability:** Every request creates an execution_trace. This is essential for auditing, debugging, and compliance.
3. **Database Isolation:** Read-only access to entitlements; write-only to tickets. Prevents accidental data mutation.
4. **Timeout Strategy:** All external calls (DB, API) have timeouts. Prevents hanging requests.
5. **Graceful Degradation:** Every tool returns a dict, never raises. Allows agent to recover and respond intelligently.
6. **Stateless Agent:** Each request is independent. Enables horizontal scaling.

---

## README Structure (To Be Written After Code)

```markdown
# DeskMate IT Helpdesk AI Assistant

## Setup

1. Clone repo
2. Create `.env` file with ANTHROPIC_API_KEY and MONGO_URI
3. `pip install -r requirements.txt`
4. `python app.py`
5. Open http://localhost:8000

## Architecture

[Describe the design: tool-calling + MongoDB + stateless agent]

## Testing

[Example queries to try]

## Observability

[Explain execution_trace]
```

---

## DESIGN.md (Load-Bearing Choices)

Document these decisions:
- Why Claude tool-calling over other approaches (ReAct, intent routing)
- Why MongoDB for IT system simulation
- Why FastAPI (not Streamlit)
- How error handling prevents failures from cascading
- How observability enables debugging in production

---

## PRODUCTION.md (1–2 Pages)

For Azure deployment:
- How to containerize (Docker)
- How to scale (Azure Container Instances, async workers)
- Authentication strategy (Azure AD, JWT tokens)
- Audit logging (all tool calls logged to cosmos DB or app insights)
- Rate limiting per employee
- Data retention policy for tickets
- Disaster recovery (MongoDB backup strategy)
- Key risks and mitigations

---

## Timeline

- **30 min:** Scaffold all files, install dependencies, test imports
- **60 min:** Implement mongo_client.py + seed data
- **30 min:** Implement tools.py (3 tool functions)
- **60 min:** Implement agent.py (Claude loop + error handling)
- **30 min:** Implement app.py (FastAPI endpoint)
- **30 min:** Implement frontend/index.html
- **30 min:** Test 5 query scenarios, verify execution traces
- **30 min:** Write README.md
- **45 min:** Write DESIGN.md (load-bearing choices)
- **60 min:** Write PRODUCTION.md (Azure production design)

---

## Success Criteria

- [ ] Repo clones and runs with single command
- [ ] Chat endpoint accepts natural language queries
- [ ] Claude correctly calls tools for multi-step queries
- [ ] Tools return realistic data from MongoDB
- [ ] Execution trace shows all decisions
- [ ] Out-of-scope queries refused gracefully
- [ ] Error scenarios handled without crashes
- [ ] Frontend displays responses + trace
- [ ] README explains architecture
- [ ] Design doc defends choices
- [ ] Production note shows production thinking
