import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
import config
import mongo_client
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

# Request schema validation
class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's query or support request.")
    username: str = Field("employee_one", description="The context username for query.")

@app.on_event("startup")
async def startup_event():
    """Run startup checks and seed database if it's empty."""
    config.logger.info("Starting DeskMate API Server...")
    try:
        # Seed MongoDB database
        mongo_client.seed_database_if_empty()
        config.logger.info("API Startup sequence completed successfully.")
    except Exception as e:
        config.logger.error(f"Error during server startup checks: {e}", exc_info=True)

class NewChatRequest(BaseModel):
    username: str = Field(..., description="The username to clear chat history for.")

@app.get("/api/history/{username}")
async def get_history(username: str):
    """Retrieve chat history for a user."""
    user = username.strip()
    if not user:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    history = mongo_client.get_chat_history(user)
    return {"messages": history, "limit_reached": len(history) >= 10}

@app.post("/api/chat/new")
async def new_chat(req: NewChatRequest):
    """Clear chat history for a user."""
    user = req.username.strip()
    if not user:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    mongo_client.clear_chat_history(user)
    return {"status": "success"}

@app.post("/api/chat")
async def chat(req: ChatRequest):
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
                "timestamp": datetime.utcnow().isoformat() + "Z"
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

@app.get("/")
async def read_root():
    """Serve the single-page HTML frontend."""
    frontend_path = os.path.join("frontend", "index.html")
    if not os.path.exists(frontend_path):
        config.logger.error(f"Frontend file not found at: {frontend_path}")
        raise HTTPException(status_code=404, detail="Frontend file not found.")
    return FileResponse(frontend_path)

@app.get("/api/health")
async def health_check():
    """Standard health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}

if __name__ == "__main__":
    import uvicorn
    # Make sure we log the launch environment
    config.logger.info("Starting server with uvicorn on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
