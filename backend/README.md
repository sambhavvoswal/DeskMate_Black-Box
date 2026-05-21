---
title: DeskMate Backend
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
---

# DeskMate IT Helpdesk AI Assistant - Backend

This is the backend API service for the DeskMate IT Helpdesk AI Assistant, packaged to run on Hugging Face Spaces using the Docker SDK.

## ⚙️ Hugging Face Space Configuration

To run this backend successfully, you must configure the following **Secrets** under your Hugging Face Space **Settings** page:

| Secret Name | Description |
|---|---|
| `MONGO_URI` | Your MongoDB Atlas connection string (e.g. `mongodb+srv://...`). |
| `MONGO_DB_NAME` | The MongoDB database name to connect to (defaults to `deskmate`). |
| `ANTHROPIC_API_KEY` | (Optional) Your Anthropic API key to enable Claude 3.5 Sonnet routing. |
| `OPENROUTER_API_KEY` | (Optional) Your OpenRouter API key to enable Gemini routing fallback. |

*Note: At least one AI API key (`ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`) is required for the agentic reasoning loop.*

## 🚀 API Endpoints

Once running, the Space exposes the following REST API endpoints:

*   `GET /api/health`: Standard server status and health check.
*   `GET /api/provider`: Returns the currently active LLM provider based on loaded keys.
*   `POST /api/chat`: Processes user message payloads through the agentic reasoning loop.
*   `GET /api/history/{username}`: Retrieves persisted chat history for a specific user.
*   `POST /api/chat/new`: Clears chat history for a session.
*   `GET /api/tickets/{username}`: Returns all raised support tickets for the user.
