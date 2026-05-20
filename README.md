# DeskMate IT Helpdesk AI Assistant

DeskMate is a production-grade Proof of Concept (POC) for an AI-powered IT helpdesk assistant. It enables natural language user interactions to resolve software access requests and check support ticket status using multi-step reasoning capabilities.

The assistant is powered by Anthropic's Claude 3.5 Sonnet using its native tool calling system, integrated with a live MongoDB Atlas cluster, and runs on a fast, lightweight FastAPI backend with a custom split-screen web frontend featuring full execution trace observability.

---

## Features

- **Multi-step Agentic Loop**: Leverages Claude's native function calling to evaluate entitlements, make decision-making loops (e.g. check entitlement -> conditionally create ticket -> report status), and resolve employee support issues dynamically.
- **Production-Grade Error Resilience**: Wraps database connections and API queries in comprehensive safety blocks. Database timeout errors, missing employee records, or rate-limiting are intercepted and translated into user-friendly responses without crashing the server.
- **Observability execution Pane**: Real-time logging of tool inputs, results, and LLM reasoning steps directly within the frontend.
- **Context-Aware Entitlements**: Automatic test profile switching in the frontend allows simulating queries as different employees.

---

## Setup & Installation

### 1. Prerequisites
- Python 3.8 or higher installed on your system.
- An Anthropic API Key (Claude Sonnet 3.5 access).
- A MongoDB Atlas connection URI (with database write permissions).

### 2. Install Dependencies
Clone the repository, go into the workspace root, and run:
```bash
pip install -r requirements.txt
```

### 3. Environment Setup
Create a file named `.env` in the root directory (you can copy `.env.example` as a starting template):
```env
ANTHROPIC_API_KEY=sk-ant-your-actual-api-key
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=deskmate
```
*(Do not commit `.env` to source control!)*

### 4. Running the Application
Launch the server with the following command:
```bash
python app.py
```
Upon launching:
- The server will establish a connection to your MongoDB Atlas cluster.
- It will automatically execute `seed_database_if_empty()`, seeding two default employee profiles (`employee_one` & `employee_two`) if they are not already present.
- The FastAPI application will run on `http://localhost:8000`.

---

## Verification & Testing Scenarios

Open your browser and navigate to `http://localhost:8000`. Use the employee dropdown in the bottom-left corner to test these exact scenarios:

### Scenario 1: Single-Step Entitlement Query
- **Active Employee**: `employee_one` (Alice Johnson)
- **User Query**: `"Do I have access to Jira?"`
- **Expected Outcome**:
  - Claude calls `check_software_entitlement` for `employee_one` on `Jira`.
  - Tool returns that she has access.
  - Claude responds: *"Yes, Alice Johnson, you currently have access to Jira."*

### Scenario 2: Multi-Step Ticket Creation Flow (Conditional Logic)
- **Active Employee**: `employee_one` (Alice Johnson)
- **User Query**: `"I need Adobe Creative Suite. If I don't have it, please create a ticket."`
- **Expected Outcome**:
  - Claude calls `check_software_entitlement` for `employee_one` on `Adobe Creative Suite`.
  - Tool returns that access is `False`.
  - Claude processes this result and automatically invokes `create_access_ticket` with priority `high`.
  - Claude reports the created Ticket ID (e.g. `TKT-XXXXXX`) and details to the user.

### Scenario 3: Entitlement Check for a User Who Has Access
- **Active Employee**: `employee_two` (Bob Smith)
- **User Query**: `"I need Adobe Creative Suite. If I don't have it, please create a ticket."`
- **Expected Outcome**:
  - Claude calls `check_software_entitlement` for `employee_two` on `Adobe Creative Suite`.
  - Tool returns that Bob already has access.
  - Claude responds that Bob is already entitled and does not call `create_access_ticket`.

### Scenario 4: Out-of-Scope Query Rejection
- **Active Employee**: Either
- **User Query**: `"Should I take this job offer?"` or `"What is the weather in London?"`
- **Expected Outcome**:
  - Claude identifies the query as out of the IT scope.
  - Rejects the request politely without calling any tools.

### Scenario 5: Check Ticket Status
- **Active Employee**: Either
- **User Query**: `"What is the status of ticket TKT-123456?"` (Replace with a valid ticket ID generated in Scenario 2)
- **Expected Outcome**:
  - Claude calls `get_ticket_status(ticket_id="TKT-123456")`.
  - Returns the status of the ticket retrieved from MongoDB Atlas.
