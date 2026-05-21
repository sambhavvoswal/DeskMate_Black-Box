# DeskMate: Automated IT Helpdesk AI Assistant (POC)

Welcome to **DeskMate**, a production-grade Proof of Concept (POC) for an intelligent, multi-step IT Helpdesk AI Assistant. DeskMate allows users to check software entitlements, request software access via automatically generated tickets, and query ticket statuses using natural language.

DeskMate features a dual-provider orchestration (preferring **OpenRouter/Gemini** to conserve API tokens, with automatic fallback to **Anthropic/Claude**), interactive suggestion chips, dynamic AI provider badges, connection resilience (degrades gracefully if database is offline), and a split-screen execution trace observability pane.

---

## 🚀 Quick Start & Local Run Guide

This section is designed to help you get DeskMate up and running on your local machine in under 5 minutes.

### 1. Prerequisites
Before starting, ensure you have:
*   **Python 3.8+** installed.
*   **An API Key** for one (or both) of:
    *   **OpenRouter** (For Gemini 2.0 Flash - recommended)
    *   **Anthropic** (For Claude 3.5 Sonnet)
*   **A MongoDB Atlas Connection String**.
    *   *Note: If MongoDB is offline or unreachable, DeskMate will still launch and run in **degraded mode** so you can interact with the chat interface.*

---

### 2. Installation Steps

#### Step A: Clone & Prepare Workspace
Clone this repository to your local machine, open your terminal, and navigate to the project directory:
```bash
cd DeskMate_Black-Box
```

#### Step B: Set Up a Virtual Environment (Recommended)
Create and activate a Python virtual environment to isolate dependencies:
```bash
# On Windows
python -m venv .venv
.venv\Scripts\activate

# On macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

#### Step C: Install Dependencies
Install all required libraries using the package manager:
```bash
pip install -r requirements.txt
```

---

### 3. Environment Configuration

Create a `.env` file in the root of the project. You can copy the provided `.env.example` file:
```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in your connection details and API keys:

```env
# --- AI Providers (Provide at least one) ---
# If both keys are set, OpenRouter (Gemini) is preferred to conserve Claude credits.
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=google/gemini-2.0-flash-001

ANTHROPIC_API_KEY=your_anthropic_api_key_here

# --- Database Configuration ---
# Your MongoDB connection URI (e.g. from MongoDB Atlas)
MONGO_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/deskmate?retryWrites=true&w=majority
MONGO_DB_NAME=deskmate
```

---

### 4. Running the Application

Start the FastAPI application server by executing:
```bash
cd backend
python app.py
```
*Alternatively, you can run it using Uvicorn directly from the backend folder:*
```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

#### What happens at startup:
1.  **Database Connection Check**: The server runs a ping check to verify if MongoDB is online.
2.  **Graceful Degraded Mode**: If MongoDB is offline, the server logs a warning and proceeds to run. Users can still chat, but database lookups degrade gracefully.
3.  **Automatic Seeding**: If the database is connected and empty, it automatically seeds two test employee profiles (`employee_one` & `employee_two`) into the `employee_entitlements` collection.

---

### 5. Interacting with the Web Interface

Once the server is running, open your web browser and go to:
👉 **[http://localhost:8000](http://localhost:8000)**

The interface is split into two visual panes:
1.  **Left (Chat Column)**: Select a mock employee profile, use suggested query chips, send message prompts, and view responses.
2.  **Right (Observability Column)**: Watch the raw multi-step agent reasoning steps, tool calls, execution tokens, and timing durations render in real time.

---

## 🧪 Verification & Testing Scenarios

Use the following step-by-step scenarios to verify the application features:

### Scenario 1: Access Granted (Single-Step Entitlement Query)
1.  Select **Bob Smith (employee_two)** from the employee dropdown.
2.  Type: `"Do I have access to Photoshop?"` or click the suggestion chip: **Check my Adobe access**.
3.  **Expected Response**: The agent will sanitize "Photoshop" to `adobe_creative_suite`, call `check_software_entitlement`, and reply:
    > *"Bob Smith, you currently have access to Adobe Creative Suite."*
4.  **Trace Check**: Verify in the right-side execution trace pane that the tool call ran, returned `has_access: true`, and finished in 1 turn.

### Scenario 2: Access Denied + Ticket Creation Flow (Multi-Step Logic)
1.  Select **Alice Johnson (employee_one)** from the employee dropdown.
2.  Type: `"I need access to Adobe Creative Suite. Please check my access and if I don't have it, create a high priority ticket."`
3.  **Expected Response**: The agent will check her access (which is `False`), see that she does not have access, automatically call `create_access_ticket` with priority `high`, and output:
    > *"I checked your entitlements and you do not have access to Adobe Creative Suite. I have created a high priority access request ticket for you: **TKT-XXXXXX**."*
4.  **Trace Check**: Observe the multi-step chain in the execution trace pane showing:
    *   Step 1: API Call requesting entitlement check.
    *   Step 2: Tool Call `check_software_entitlement` returning `has_access: False`.
    *   Step 3: API Call deciding to create a ticket.
    *   Step 4: Tool Call `create_access_ticket` returning `TKT-XXXXXX`.
    *   Step 5: API Call summarizing the resolution.

### Scenario 3: Checking Ticket Status
1.  Copy the ticket ID (e.g. `TKT-123456`) generated in Scenario 2.
2.  Type: `"What is the status of ticket TKT-123456?"`
3.  **Expected Response**: The agent will run `get_ticket_status` and output:
    > *"Ticket TKT-123456 is currently open. Priority: high. Assignee: Unassigned."*

### Scenario 4: Conversation Cap & History Recovery
1.  Chat history is persisted in the database. When you select a user, their history is loaded.
2.  To protect token budgets, the conversation is capped at **10 messages**.
3.  Once the limit is reached, input controls are disabled. Click the **New Chat** button in the header to clear history and reset.

---

## 🛠️ Project Structure & Architecture

```
├── backend/              # Python backend folder (deployed to HF Spaces)
│   ├── app.py            # FastAPI Application Server & API endpoints
│   ├── agent.py          # Agent reasoning loop orchestration (Claude & Gemini router)
│   ├── tools.py          # Helpdesk agent tool definitions (entitlements, ticket operations)
│   ├── schemas.py        # Pydantic schemas validating API requests & responses
│   ├── mongo_client.py   # MongoDB database client wrapper & seeding logic
│   ├── config.py         # Configuration loader validating environment keys
│   └── requirements.txt  # Python package dependencies
├── frontend/
│   └── index.html        # Single-page HTML5/Vanilla JS app with premium styling
└── .github/
    └── workflows/
        └── deploy-backend.yml # CI/CD deployment workflow to Hugging Face
```

---

## 🌐 Deployment Architecture (Deployment in process)

The DeskMate application is designed as a split-architecture application:

### 1. Frontend Hosting (Vercel / Static Host)
The [frontend/index.html] file is a pure, single-file HTML5 client with CSS and Vanilla JS. It can be hosted on **Vercel**, Netlify, GitHub Pages, or any static file hosting service. 

*   **Dynamic API Auto-Detection**: When the frontend loads, it automatically tests if a local backend is active at `http://localhost:8000`. If active, it routes requests locally. If offline, it dynamically falls back to your remote Hugging Face Space backend URL (`https://sambhavvoswal-deskmate-api.hf.space`). You can customize the fallback URL inside the `HF_BACKEND_URL` variable in `index.html`.

### 2. Backend Hosting (Hugging Face Spaces)
The [backend/] folder contains the FastAPI application code, package requirements, and docker instructions. 
*   **Docker SDK**: Deploy the backend to a Hugging Face Space configured with the **Docker SDK** (which binds automatically to dynamic port `7860`).
*   **Secrets**: Remember to configure the required environment variables (e.g. `MONGO_URI`, `ANTHROPIC_API_KEY`) inside your Hugging Face Space Settings.

### 3. Automated CI/CD (GitHub Actions)
A pre-configured CI/CD workflow is included at [.github/workflows/deploy-backend.yml]. 
Whenever you push changes inside the `backend/` folder to GitHub:
1. GitHub Actions triggers and checks out the codebase.
2. It pushes the contents of the `backend/` directory directly to the Hugging Face Space git repository.
3. Hugging Face automatically rebuilds the Docker container and restarts your API.

*Note: You only need to add `HF_TOKEN` (your Hugging Face User Access Write Token) as a repository secret under your GitHub Repository Settings.*

