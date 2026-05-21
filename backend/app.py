import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import config
import mongo_client
import schemas
from agent import run_agent

# Initialize FastAPI App
app = FastAPI(
    title="DeskMate IT Helpdesk AI Assistant",
    version="1.0.0",
    description="A multi-step reasoning POC powered by Claude tool calling and MongoDB Atlas."
)

# Enable CORS for local testing/development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Run startup checks and seed database if it's empty."""
    config.logger.info("Starting DeskMate API Server...")
    try:
        # Check database connectivity
        db_online = mongo_client.check_db_health()
        if db_online:
            config.logger.info("MongoDB connection is healthy. Seeding database if empty...")
            mongo_client.seed_database_if_empty()
            config.logger.info("API Startup sequence completed successfully.")
        else:
            config.logger.warning(
                "⚠️ WARNING: MongoDB is currently unreachable. DeskMate will run in degraded mode: "
                "chat history and entitlement checking will be unavailable, but the chat interface remains interactive."
            )
    except Exception as e:
        config.logger.error(f"Unexpected error during server startup checks: {e}", exc_info=True)

@app.get("/api/history/{username}", response_model=schemas.HistoryResponse)
async def get_history(username: str):
    """Retrieve chat history for a user."""
    user = username.strip()
    if not user:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    history = mongo_client.get_chat_history(user)
    return {"messages": history, "limit_reached": len(history) >= 10}

@app.post("/api/chat/new")
async def new_chat(req: schemas.NewChatRequest):
    """Clear chat history for a user."""
    user = req.username.strip()
    if not user:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    mongo_client.clear_chat_history(user)
    return {"status": "success"}

@app.post("/api/chat", response_model=schemas.ChatResponse)
async def chat(req: schemas.ChatRequest):
    """Main chat endpoint that processes messages through the Agentic loop with history context."""
    msg = req.message.strip()
    user = req.username.strip()
    
    if not msg:
        config.logger.warning("Received chat request with empty message.")
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if not user:
        config.logger.warning("Received chat request with empty username.")
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
        
    try:
        config.logger.info(f"Received request from user '{user}': '{msg[:55]}'")
        
        # Load full history from MongoDB
        full_history = mongo_client.get_chat_history(user)
        
        # 10 message limit check
        if len(full_history) >= 10:
            return {
                "response": "Conversation limit reached (10 messages). Please start a new chat.",
                "execution_trace": [],
                "username": user,
                "status": "limit_reached",
                "limit_reached": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "provider": "None"
            }
            
        # Get active context (last 8 messages)
        active_context = full_history[-8:]
        
        # Run agent loop with active context
        result = run_agent(msg, user, history=active_context)
        result["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        if result.get("status") == "success":
            # Append user message and agent response to full history
            full_history.append({"role": "user", "content": msg})
            full_history.append({"role": "assistant", "content": result.get("response")})
            
            # Save back to database
            mongo_client.save_chat_history(user, full_history)
            
            # Update limit_reached flag in result
            result["limit_reached"] = len(full_history) >= 10
        else:
            result["limit_reached"] = len(full_history) >= 10
            
        return result
    except Exception as e:
        config.logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error occurred.")

@app.get("/api/provider", response_model=schemas.ActiveProviderResponse)
async def get_active_provider():
    """Return the active AI provider based on loaded keys."""
    if config.OPENROUTER_API_KEY:
        return {
            "provider": "Gemini 2.0 Flash (OpenRouter)",
            "model": config.OPENROUTER_MODEL
        }
    elif config.ANTHROPIC_API_KEY:
        return {
            "provider": "Claude 3.5 Sonnet",
            "model": config.CLAUDE_MODEL
        }
    else:
        return {
            "provider": "None (No API keys configured)",
            "model": "None"
        }

@app.get("/api/tickets/{username}")
async def get_user_tickets(username: str):
    """Retrieve all tickets raised by a user."""
    user = username.strip()
    if not user:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    tickets = mongo_client.get_user_tickets(user)
    return {"tickets": tickets}


API_STATUS_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>DeskMate API Service</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            background-color: #0b0f19;
            color: #f1f5f9;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            text-align: center;
            padding: 2.5rem;
            border-radius: 16px;
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            max-width: 450px;
        }
        h1 {
            color: #818cf8;
            margin-top: 0;
            margin-bottom: 0.75rem;
            font-size: 1.75rem;
            font-weight: 700;
        }
        p {
            color: #94a3b8;
            line-height: 1.6;
            margin-bottom: 1.5rem;
            font-size: 0.95rem;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1.25rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 600;
            background-color: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .pulse {
            width: 8px;
            height: 8px;
            background-color: #10b981;
            border-radius: 50%;
            animation: pulse-animation 2s infinite;
        }
        @keyframes pulse-animation {
            0% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            }
            70% {
                transform: scale(1);
                box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
            }
            100% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 DeskMate API Service</h1>
        <p>The backend AI orchestration and database connectivity services are online and running successfully on Hugging Face Spaces.</p>
        <div class="status-badge">
            <span class="pulse"></span>
            Status: Online & Healthy
        </div>
    </div>
</body>
</html>
"""

@app.get("/")
async def read_root():
    """Serve the single-page HTML frontend or API status landing page."""
    # 1. Try relative to current working directory
    frontend_path = os.path.join("frontend", "index.html")
    
    # 2. Try relative to app.py location (e.g., ../frontend/index.html)
    if not os.path.exists(frontend_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        frontend_path = os.path.join(base_dir, "..", "frontend", "index.html")
        
    # 3. Try inside the same folder as app.py (if frontend is copied directly next to it)
    if not os.path.exists(frontend_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        frontend_path = os.path.join(base_dir, "frontend", "index.html")
        
    if not os.path.exists(frontend_path):
        config.logger.info("Serving default API status landing page because frontend file was not found.")
        return HTMLResponse(content=API_STATUS_HTML)
    return FileResponse(frontend_path)

@app.get("/api/health")
async def health_check():
    """Standard health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 7860))
    config.logger.info(f"Starting server with uvicorn on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
