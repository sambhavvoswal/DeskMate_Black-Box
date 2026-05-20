import anthropic
import json
import httpx
from datetime import datetime
import config
import tools

def run_agent(user_message: str, username: str, history: list = None) -> dict:
    """Core orchestrator routing requests to OpenRouter (Gemini) or Anthropic (Claude) depending on API key availability."""
    config.logger.info(f"Starting agent run for user: '{username}' with message: '{user_message}'")
    
    execution_trace = []
    
    system_prompt = (
        "You are DeskMate, an IT helpdesk assistant. You help employees with:\n"
        "- Checking software entitlements\n"
        "- Requesting access to software\n"
        "- Checking ticket status\n\n"
        "You can ONLY handle IT-related requests. For anything outside IT scope "
        "(e.g., HR questions, personal advice), politely refuse.\n\n"
        "When an employee asks for software access they don't have, always offer "
        "to create a ticket with priority 'high'.\n\n"
        "Be concise, helpful, and always include relevant details in your response.\n\n"
        f"Current employee: {username}"
    )
    
    # Check key priority: OpenRouter first (to save Claude credits as requested by user), then Anthropic.
    if config.OPENROUTER_API_KEY:
        config.logger.info("Using OpenRouter (Gemini 2.0 Flash) as the AI provider.")
        return run_openrouter_agent(user_message, username, system_prompt, execution_trace, history=history)
    else:
        config.logger.info("Using Anthropic (Claude 3.5 Sonnet) as the AI provider.")
        return run_claude_agent(user_message, username, system_prompt, execution_trace, history=history)

def run_claude_agent(user_message: str, username: str, system_prompt: str, execution_trace: list, history: list = None) -> dict:
    messages = []
    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    try:
        # Initialize Anthropic client
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        
        max_iterations = 10
        final_text = ""
        
        for iteration in range(1, max_iterations + 1):
            config.logger.info(f"Iteration {iteration}: Sending request to Claude...")
            
            # API Call Trace
            api_call_start = datetime.utcnow()
            
            # Call Anthropic API
            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=tools.get_tools_list(),
                messages=messages
            )
            
            api_call_duration = (datetime.utcnow() - api_call_start).total_seconds()
            config.logger.info(f"Iteration {iteration}: Received response from Claude in {api_call_duration:.2f}s. Stop reason: '{response.stop_reason}'")
            
            # Record api_call in execution_trace
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0
            
            # Format content summary for logging/observability
            response_content_summary = []
            for block in response.content:
                if block.type == "text":
                    response_content_summary.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    response_content_summary.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })
            
            execution_trace.append({
                "step": len(execution_trace) + 1,
                "type": "api_call",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "data": {
                    "model": config.CLAUDE_MODEL,
                    "stop_reason": response.stop_reason,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "content": response_content_summary,
                    "duration_seconds": api_call_duration
                }
            })
            
            # Process response content
            assistant_message_content = []
            tool_use_blocks = []
            
            for block in response.content:
                if block.type == "text":
                    assistant_message_content.append({"type": "text", "text": block.text})
                    final_text = block.text
                elif block.type == "tool_use":
                    assistant_message_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })
                    tool_use_blocks.append(block)
            
            messages.append({"role": "assistant", "content": assistant_message_content})
            
            if response.stop_reason == "end_turn":
                config.logger.info("Claude finished reasoning. End turn.")
                break
                
            elif response.stop_reason == "tool_use":
                config.logger.info(f"Claude requested {len(tool_use_blocks)} tool executions.")
                
                tool_results_content = []
                for tool_block in tool_use_blocks:
                    tool_name = tool_block.name
                    tool_input = tool_block.input
                    tool_use_id = tool_block.id
                    
                    config.logger.info(f"Executing tool '{tool_name}' with input: {tool_input}")
                    
                    tool_start_time = datetime.utcnow()
                    tool_result = {}
                    
                    try:
                        if tool_name == "check_software_entitlement":
                            tool_result = tools.check_software_entitlement(
                                username=tool_input.get("username", username),
                                software_name=tool_input.get("software_name", "")
                            )
                        elif tool_name == "create_access_ticket":
                            tool_result = tools.create_access_ticket(
                                username=tool_input.get("username", username),
                                software_name=tool_input.get("software_name", ""),
                                priority=tool_input.get("priority", "high"),
                                description=tool_input.get("description", "")
                            )
                        elif tool_name == "get_ticket_status":
                            tool_result = tools.get_ticket_status(
                                ticket_id=tool_input.get("ticket_id", "")
                            )
                        else:
                            error_msg = f"Unknown tool name: {tool_name}"
                            config.logger.error(error_msg)
                            tool_result = {"error": error_msg}
                    except Exception as tool_ex:
                        error_msg = f"Exception running tool {tool_name}: {str(tool_ex)}"
                        config.logger.error(error_msg, exc_info=True)
                        tool_result = {"error": error_msg}
                        
                    tool_duration = (datetime.utcnow() - tool_start_time).total_seconds()
                    
                    execution_trace.append({
                        "step": len(execution_trace) + 1,
                        "type": "tool_call",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "data": {
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                            "tool_use_id": tool_use_id,
                            "result": tool_result,
                            "duration_seconds": tool_duration
                        }
                    })
                    
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(tool_result)
                    })
                    
                messages.append({
                    "role": "user",
                    "content": tool_results_content
                })
            else:
                config.logger.warning(f"Unexpected stop reason: {response.stop_reason}")
                break
        else:
            config.logger.warning(f"Agent reached max iterations ({max_iterations}) without natural stop.")
            
        config.logger.info(f"Agent finished run successfully. Response: '{final_text[:60]}...'")
        return {
            "response": final_text or "I have processed your request.",
            "execution_trace": execution_trace,
            "username": username,
            "status": "success"
        }
    except (anthropic.APIError, anthropic.RateLimitError, anthropic.APIConnectionError) as ae:
        error_msg = f"Anthropic API Error: {str(ae)}"
        config.logger.error(error_msg, exc_info=True)
        execution_trace.append({
            "step": len(execution_trace) + 1,
            "type": "error",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": {"error": error_msg}
        })
        return {
            "response": "I encountered an error connecting to the AI service. Please try again in a moment.",
            "execution_trace": execution_trace,
            "username": username,
            "status": "error",
            "error": str(ae)
        }
    except Exception as e:
        error_msg = f"Unexpected Agent Error: {str(e)}"
        config.logger.error(error_msg, exc_info=True)
        execution_trace.append({
            "step": len(execution_trace) + 1,
            "type": "error",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": {"error": error_msg}
        })
        return {
            "response": "An unexpected error occurred while processing your request. Please contact IT support.",
            "execution_trace": execution_trace,
            "username": username,
            "status": "error",
            "error": str(e)
        }

def run_openrouter_agent(user_message: str, username: str, system_prompt: str, execution_trace: list, history: list = None) -> dict:
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    
    def get_openai_tools():
        anthropic_tools = tools.get_tools_list()
        openai_tools = []
        for t in anthropic_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"]
                }
            })
        return openai_tools
    
    try:
        max_iterations = 10
        final_text = ""
        openai_tools = get_openai_tools()
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "DeskMate"
        }
        
        for iteration in range(1, max_iterations + 1):
            config.logger.info(f"Iteration {iteration}: Sending request to OpenRouter...")
            
            # API Call Trace
            api_call_start = datetime.utcnow()
            
            payload = {
                "model": config.OPENROUTER_MODEL,
                "messages": messages,
                "tools": openai_tools,
                "tool_choice": "auto"
            }
            
            # Make direct HTTP request to OpenRouter API
            with httpx.Client(timeout=config.TOOL_TIMEOUT_SECONDS) as client:
                response = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                
            api_call_duration = (datetime.utcnow() - api_call_start).total_seconds()
            
            if response.status_code != 200:
                error_msg = f"OpenRouter API Error (Status {response.status_code}): {response.text}"
                config.logger.error(error_msg)
                raise Exception(error_msg)
                
            res_data = response.json()
            config.logger.info(f"Iteration {iteration}: Received response from OpenRouter in {api_call_duration:.2f}s.")
            
            choices = res_data.get("choices", [])
            if not choices:
                raise Exception("Empty response choice from OpenRouter completions.")
                
            choice = choices[0]
            choice_msg = choice.get("message", {})
            finish_reason = choice.get("finish_reason")
            
            content = choice_msg.get("content")
            tool_calls = choice_msg.get("tool_calls", [])
            
            if content:
                final_text = content
                
            # Log api_call in execution_trace
            input_tokens = res_data.get("usage", {}).get("prompt_tokens", 0)
            output_tokens = res_data.get("usage", {}).get("completion_tokens", 0)
            
            # Format content summary for logging/observability
            response_content_summary = []
            if content:
                response_content_summary.append({"type": "text", "text": content})
            for tc in tool_calls:
                try:
                    tc_args = json.loads(tc["function"]["arguments"])
                except Exception:
                    tc_args = tc["function"]["arguments"]
                response_content_summary.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": tc_args
                })
                
            execution_trace.append({
                "step": len(execution_trace) + 1,
                "type": "api_call",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "data": {
                    "model": config.OPENROUTER_MODEL,
                    "finish_reason": finish_reason,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "content": response_content_summary,
                    "duration_seconds": api_call_duration
                }
            })
            
            # Append Assistant message to messages list
            assistant_msg = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)
            
            # If no tool calls requested, we are done
            if not tool_calls:
                config.logger.info("OpenRouter finished reasoning. End turn.")
                break
                
            config.logger.info(f"OpenRouter requested {len(tool_calls)} tool executions.")
            
            for tc in tool_calls:
                tool_use_id = tc["id"]
                tool_name = tc["function"]["name"]
                tool_args_str = tc["function"]["arguments"]
                
                try:
                    tool_input = json.loads(tool_args_str)
                except Exception as parse_ex:
                    config.logger.error(f"Error parsing tool args string '{tool_args_str}': {str(parse_ex)}")
                    tool_input = {}
                    
                config.logger.info(f"Executing tool '{tool_name}' with input: {tool_input}")
                
                tool_start_time = datetime.utcnow()
                tool_result = {}
                
                try:
                    if tool_name == "check_software_entitlement":
                        tool_result = tools.check_software_entitlement(
                            username=tool_input.get("username", username),
                            software_name=tool_input.get("software_name", "")
                        )
                    elif tool_name == "create_access_ticket":
                        tool_result = tools.create_access_ticket(
                            username=tool_input.get("username", username),
                            software_name=tool_input.get("software_name", ""),
                            priority=tool_input.get("priority", "high"),
                            description=tool_input.get("description", "")
                        )
                    elif tool_name == "get_ticket_status":
                        tool_result = tools.get_ticket_status(
                            ticket_id=tool_input.get("ticket_id", "")
                        )
                    else:
                        error_msg = f"Unknown tool name: {tool_name}"
                        config.logger.error(error_msg)
                        tool_result = {"error": error_msg}
                except Exception as tool_ex:
                    error_msg = f"Exception running tool {tool_name}: {str(tool_ex)}"
                    config.logger.error(error_msg, exc_info=True)
                    tool_result = {"error": error_msg}
                    
                tool_duration = (datetime.utcnow() - tool_start_time).total_seconds()
                
                # Append tool result to execution trace
                execution_trace.append({
                    "step": len(execution_trace) + 1,
                    "type": "tool_call",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "data": {
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "tool_use_id": tool_use_id,
                        "result": tool_result,
                        "duration_seconds": tool_duration
                    }
                })
                
                # Append tool result message to messages history
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_use_id,
                    "name": tool_name,
                    "content": json.dumps(tool_result)
                })
        else:
            config.logger.warning(f"Agent reached max iterations ({max_iterations}) without natural stop.")
            
        config.logger.info(f"Agent finished run successfully. Response: '{final_text[:60]}...'")
        return {
            "response": final_text or "I have processed your request.",
            "execution_trace": execution_trace,
            "username": username,
            "status": "success"
        }
        
    except Exception as e:
        error_msg = f"Unexpected OpenRouter Agent Error: {str(e)}"
        config.logger.error(error_msg, exc_info=True)
        execution_trace.append({
            "step": len(execution_trace) + 1,
            "type": "error",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": {"error": error_msg}
        })
        return {
            "response": "An unexpected error occurred while processing your request via OpenRouter. Please contact IT support.",
            "execution_trace": execution_trace,
            "username": username,
            "status": "error",
            "error": str(e)
        }
