import mongo_client
import config

def check_software_entitlement(username: str, software_name: str) -> dict:
    """Check if an employee has access to specific software."""
    config.logger.info(f"Tool check_software_entitlement called: username='{username}', software_name='{software_name}'")
    try:
        res = mongo_client.check_entitlement(username, software_name)
        if "error" in res:
            config.logger.error(f"check_software_entitlement error: {res['error']}")
            return {
                "username": username,
                "software_name": software_name,
                "has_access": False,
                "employee_name": "Unknown",
                "employee_department": "Unknown",
                "message": f"Error checking software entitlement: {res['error']}",
                "error": res["error"]
            }
        
        has_access = res["has_access"]
        employee_name = res["employee_name"]
        
        # Get department if profile exists
        profile = mongo_client.get_employee_profile(username)
        dept = profile.get("department", "Unknown") if profile else "Unknown"
        
        msg = f"Employee {employee_name} ({username}) has access to {software_name}." if has_access else f"Employee {employee_name} ({username}) does NOT have access to {software_name}."
        
        formatted_res = {
            "username": username,
            "software_name": software_name,
            "has_access": has_access,
            "employee_name": employee_name,
            "employee_department": dept,
            "message": msg
        }
        config.logger.info(f"check_software_entitlement tool output: {formatted_res}")
        return formatted_res
    except Exception as e:
        config.logger.error(f"Exception in check_software_entitlement tool: {e}", exc_info=True)
        return {
            "username": username,
            "software_name": software_name,
            "has_access": False,
            "employee_name": "Unknown",
            "employee_department": "Unknown",
            "message": f"Unexpected error checking entitlement: {str(e)}",
            "error": str(e)
        }

def create_access_ticket(username: str, software_name: str, priority: str, description: str) -> dict:
    """Create an IT ticket for software access. Priority must be one of low, medium, high, critical."""
    config.logger.info(f"Tool create_access_ticket called: username='{username}', software_name='{software_name}', priority='{priority}'")
    try:
        valid_priorities = ["low", "medium", "high", "critical"]
        norm_priority = priority.lower().strip()
        if norm_priority not in valid_priorities:
            err_msg = f"Invalid priority. Must be one of: {', '.join(valid_priorities)}"
            config.logger.warning(f"create_access_ticket validation failed: {err_msg}")
            return {
                "ticket_id": "ERROR",
                "username": username,
                "software_name": software_name,
                "priority": priority,
                "status": "error",
                "message": err_msg,
                "error": err_msg
            }
            
        res = mongo_client.create_ticket(username, software_name, norm_priority, description)
        if "error" in res:
            config.logger.error(f"create_access_ticket error: {res['error']}")
            return {
                "ticket_id": "ERROR",
                "username": username,
                "software_name": software_name,
                "priority": norm_priority,
                "status": "error",
                "message": f"Error creating ticket: {res['error']}",
                "error": res["error"]
            }
            
        formatted_res = {
            "ticket_id": res["ticket_id"],
            "username": username,
            "software_name": software_name,
            "priority": norm_priority,
            "status": res["status"],
            "message": f"Successfully created ticket {res['ticket_id']} with priority '{norm_priority}' for {software_name}."
        }
        config.logger.info(f"create_access_ticket tool output: {formatted_res}")
        return formatted_res
    except Exception as e:
        config.logger.error(f"Exception in create_access_ticket tool: {e}", exc_info=True)
        return {
            "ticket_id": "ERROR",
            "username": username,
            "software_name": software_name,
            "priority": priority,
            "status": "error",
            "message": f"Unexpected error creating ticket: {str(e)}",
            "error": str(e)
        }

def get_ticket_status(ticket_id: str) -> dict:
    """Retrieve the status of an existing IT ticket."""
    config.logger.info(f"Tool get_ticket_status called: ticket_id='{ticket_id}'")
    try:
        res = mongo_client.get_ticket_status(ticket_id)
        if "error" in res:
            config.logger.error(f"get_ticket_status error: {res['error']}")
            return {
                "ticket_id": ticket_id,
                "username": "Unknown",
                "software_name": "Unknown",
                "priority": "Unknown",
                "status": "error",
                "created_at": "Unknown",
                "assignee": None,
                "message": f"Error retrieving ticket: {res['error']}",
                "error": res["error"]
            }
            
        formatted_res = {
            "ticket_id": res["ticket_id"],
            "username": res["username"],
            "software_name": res["software_name"],
            "priority": res["priority"],
            "status": res["status"],
            "created_at": res["created_at"],
            "assignee": res["assignee"],
            "message": f"Ticket {ticket_id} is currently '{res['status']}'. Priority: '{res['priority']}'. Assignee: {res['assignee'] or 'Unassigned'}."
        }
        config.logger.info(f"get_ticket_status tool output: {formatted_res}")
        return formatted_res
    except Exception as e:
        config.logger.error(f"Exception in get_ticket_status tool: {e}", exc_info=True)
        return {
            "ticket_id": ticket_id,
            "username": "Unknown",
            "software_name": "Unknown",
            "priority": "Unknown",
            "status": "error",
            "created_at": "Unknown",
            "assignee": None,
            "message": f"Unexpected error retrieving ticket: {str(e)}",
            "error": str(e)
        }

def get_tools_list() -> list:
    """Return tool configurations formatted for the Anthropic Messages API."""
    return [
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
        {
            "name": "create_access_ticket",
            "description": "Create an IT access request ticket for an employee for a specific software application.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "The employee's username (e.g., 'employee_one')"
                    },
                    "software_name": {
                        "type": "string",
                        "description": "The name of the software (e.g., 'Adobe Creative Suite')"
                    },
                    "priority": {
                        "type": "string",
                        "description": "The severity/priority of the ticket. Must be one of: 'low', 'medium', 'high', 'critical'."
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed explanation of why access is needed or context of request."
                    }
                },
                "required": ["username", "software_name", "priority", "description"]
            }
        },
        {
            "name": "get_ticket_status",
            "description": "Retrieve the current status of an IT helpdesk ticket.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "The ticket identifier (e.g., 'TKT-123456')"
                    }
                },
                "required": ["ticket_id"]
            }
        }
    ]
