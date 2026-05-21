from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's query or support request.")
    username: str = Field("employee_one", description="The context username for query.")

class ChatResponse(BaseModel):
    response: str = Field(..., description="The agent's reply to the user.")
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list, description="Trace of execution steps.")
    username: str = Field(..., description="The username.")
    status: str = Field(..., description="The status of the response (e.g. success, error).")
    limit_reached: bool = Field(False, description="Flag indicating if the conversation limit of 10 messages was reached.")
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp of the response.")
    error: Optional[str] = Field(None, description="Error message if status is error.")
    provider: Optional[str] = Field(None, description="The name of the active AI model/provider used.")

class NewChatRequest(BaseModel):
    username: str = Field(..., description="The username to clear chat history for.")

class TicketCreate(BaseModel):
    ticket_id: str = Field(..., description="The generated ticket identifier (e.g., 'TKT-123456')")
    username: str = Field(..., description="The employee's username.")
    software_name: str = Field(..., description="The software name requested.")
    priority: str = Field(..., description="The ticket priority: 'low', 'medium', 'high', or 'critical'.")
    description: str = Field(..., description="Explanation of why access is needed.")
    status: str = Field("open", description="Status of the ticket.")
    created_at: str = Field(..., description="ISO timestamp when the ticket was created.")
    assignee: Optional[str] = Field(None, description="Assigned support agent.")

class EmployeeProfile(BaseModel):
    username: str = Field(..., description="Unique employee username.")
    name: str = Field(..., description="Employee's display name.")
    department: str = Field(..., description="Employee's department.")
    entitlements: Dict[str, bool] = Field(..., description="Map of software keys to access boolean.")
    created_at: str = Field(..., description="Creation date.")

class ActiveProviderResponse(BaseModel):
    provider: str = Field(..., description="The active AI provider name.")
    model: str = Field(..., description="The model identifier used by the active provider.")

class HistoryResponse(BaseModel):
    messages: List[Dict[str, Any]] = Field(..., description="The chat messages history.")
    limit_reached: bool = Field(..., description="Flag indicating if 10 messages limit is reached.")
