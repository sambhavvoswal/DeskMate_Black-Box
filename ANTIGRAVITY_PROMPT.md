# DeskMate Antigravity Generation Prompt

## Project Brief
Build a Python POC for DeskMate, an AI-powered IT helpdesk. The system uses Claude's native tool calling to handle multi-step employee queries (e.g., "Check my Adobe access and create a ticket if I don't have it"), integrates with a live MongoDB Atlas cluster, and provides full observability.

---

## Technology Stack
- **LLM & Tool Calling:** Anthropic Claude API + `anthropic` SDK
- **Backend:** FastAPI
- **Database:** MongoDB Atlas + `pymongo`
- **Frontend:** Single HTML file (vanilla JS)
- **Config:** `python-dotenv`
- **Logging:** Python `logging` module

---

## Files to Generate

### 1. `config.py`
- Load ANTHROPIC_API_KEY, MONGO_URI, MONGO_DB_NAME from `.env` using `python-dotenv`
- Configure Python logger with timestamps and INFO level
- Export: CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
- Validate required keys; raise ValueError if missing

### 2. `mongo_client.py`
- `get_mongo_client()` → MongoClient
- `get_database()` → Database
- `seed_database_if_empty()` → Create employee_entitlements collection with test profiles (employee_one, employee_two with realistic entitlements like adobe_creative_suite, vpn_access, etc.)
- `get_employee_profile(username)` → dict or None
- `check_entitlement(username, software_name)` → {"has_access": bool, "entitlements": dict, "employee_name": str}
- `create_ticket(username, software_name, priority, description)` → {"ticket_id": "TKT-XXXXX", ...}
- `get_ticket_status(ticket_id)` → dict
- **All functions wrapped in try-except for pymongo.errors.PyMongoError; return error dicts, never raise**

### 3. `tools.py`
Define 3 tool functions for Claude:
- `check_software_entitlement(username, software_name)` → calls mongo_client.check_entitlement(), returns formatted response
- `create_access_ticket(username, software_name, priority, description)` → calls mongo_client.create_ticket(), validates priority is one of [low, medium, high, critical], returns formatted response
- `get_ticket_status(ticket_id)` → calls mongo_client.get_ticket_status(), returns formatted response

Also create `get_tools_list()` function that returns the tool definitions in Anthropic SDK format:
```python
tools = [
    {
        "name": "check_software_entitlement",
        "description": "Check if an employee has access to specific software",
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "Employee username"},
                "software_name": {"type": "string", "description": "Software name (e.g., 'Adobe Creative Suite')"}
            },
            "required": ["username", "software_name"]
        }
    },
    # ... create_access_ticket with properties: username, software_name, priority, description
    # ... get_ticket_status with property: ticket_id
]
```

### 4. `agent.py`
Implement `run_agent(user_message: str, username: str) -> dict`:
- Initialize Anthropic client with ANTHROPIC_API_KEY
- System prompt: "You are DeskMate, an IT helpdesk assistant. You handle software access checks, ticket creation, and ticket status queries. Refuse out-of-scope requests politely. Current employee: {username}"
- Initialize messages = [{"role": "user", "content": user_message}]
- Initialize execution_trace = []
- **Loop (max 10 iterations):**
  - Call client.messages.create(model=CLAUDE_MODEL, max_tokens=1024, system=system_prompt, tools=tools_list, messages=messages)
  - Log the API call to execution_trace
  - Check response.stop_reason:
    - If "end_turn": Extract text response, break
    - If "tool_use": For each tool_use in response.content:
      - Extract tool_name and tool_input
      - Call corresponding function from tools.py
      - Log tool call + result to execution_trace
      - Append assistant message to messages
      - Append tool result to messages as new "user" message with type "tool_result"
- Return {"response": final_text, "execution_trace": execution_trace, "username": username, "status": "success" | "error"}
- **Error handling:** Catch anthropic.APIError, anthropic.RateLimitError, etc. Return error dict with status "error"

### 5. `app.py`
- FastAPI app
- `POST /api/chat` endpoint:
  - Request body: {"message": str, "username": str = "employee_one"}
  - Call run_agent(message, username)
  - Return response dict
  - Validate: message and username not empty (400 errors)
- `GET /` endpoint: Return FileResponse("frontend/index.html")
- `GET /api/health` endpoint: Return {"status": "ok"}
- **On startup:** Call seed_database_if_empty()
- **Main block:** Run with uvicorn on 0.0.0.0:8000

### 6. `frontend/index.html`
Single-file HTML with embedded CSS and JavaScript:
- **Layout:** Two-column (chat on left 2/3, observability panel on right 1/3)
- **Left column:** 
  - Header: "DeskMate IT Helpdesk"
  - Chat messages area (scrollable)
  - Employee dropdown: "employee_one" (Alice Johnson) / "employee_two" (Bob Smith)
  - Input field + Send button
- **Right column:**
  - "Execution Trace" header with Clear button
  - JSON display of execution_trace
- **JavaScript:**
  - `sendMessage()`: POST to /api/chat, add response to chat, update trace
  - `addMessageToChat(sender, text, role)`: Add message div to chat area
  - `updateTrace(trace)`: Display execution trace as formatted JSON
  - Handle Enter key in input
  - Disable send button while awaiting response

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

### 8. `.env` (Template)
```
ANTHROPIC_API_KEY=sk-ant-...
MONGO_URI=mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=deskmate
```

---

## Core Behavior

### Query: "Do I have access to Jira?"
- Claude calls check_software_entitlement("employee_one", "Jira")
- Tool returns: has_access: true
- Claude responds: "Yes, you have access to Jira."

### Query: "I need Adobe Creative Suite. Please create a ticket if I don't have it."
- Claude calls check_software_entitlement("employee_one", "Adobe Creative Suite")
- Tool returns: has_access: false
- Claude observes the result and calls create_access_ticket("employee_one", "Adobe Creative Suite", "high", "...")
- Tool returns ticket_id: "TKT-123456"
- Claude responds: "You don't have access, but I've created high-priority ticket TKT-123456."

### Query: "Should I take this job offer?"
- Claude recognizes out-of-scope
- Claude responds: "I can only help with IT-related questions."
- No tools called

---

## Key Implementation Details

1. **Tool Execution in Agent Loop:**
   - After each Claude response, check for tool_use blocks
   - Execute tools deterministically (no LLM in tool execution)
   - Feed results back to Claude in next message as tool_result type
   - Continue loop until stop_reason is "end_turn"

2. **Observability:**
   - Log every API call (timestamp, model, input tokens)
   - Log every tool invocation (name, input, output, latency)
   - Capture loop iteration count and stop reason
   - Return execution_trace as list of dicts with {step, type, timestamp, data}

3. **Error Handling:**
   - All tool functions return dicts; never raise exceptions
   - MongoDB errors caught and logged; return error dict
   - Claude API errors caught; return error response to user
   - Malformed input validated before agent call (400 errors)

4. **Graceful Degradation:**
   - If tool returns error, Claude sees it and responds accordingly
   - If database is down, tool returns {"error": "..."} and Claude tells user "temporary issue"
   - If API rate limited, catch and return "service temporarily busy"

---

## Success Criteria
- [ ] Run with: `python app.py`
- [ ] Open browser, send chat message, get response
- [ ] Execution trace shows all tool calls
- [ ] Multi-step query (check → create ticket) works
- [ ] Out-of-scope query refused
- [ ] Database errors handled gracefully
- [ ] All code is clear, modular, well-logged
- [ ] README + DESIGN.md + PRODUCTION.md written

---

## Notes for Antigravity
- Focus on **clarity and modularity**, not brevity
- Each function should have a clear single responsibility
- Logging should be verbose enough to trace execution end-to-end
- Error handling should never crash; always return structured responses
- Code should be defensible in a live technical interview
