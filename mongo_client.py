import pymongo
from pymongo.errors import PyMongoError
import random
from datetime import datetime
import config

_client = None

def get_mongo_client() -> pymongo.MongoClient:
    """Initialize and return MongoClient using MONGO_URI from config."""
    global _client
    if _client is None:
        try:
            config.logger.info("Initializing MongoDB Client...")
            # Set a server selection timeout so it fails relatively quickly if connection is down
            _client = pymongo.MongoClient(
                config.MONGO_URI,
                serverSelectionTimeoutMS=config.TOOL_TIMEOUT_SECONDS * 1000
            )
            # Trigger a simple call to verify connectivity
            _client.admin.command('ping')
            config.logger.info("MongoDB client connected successfully.")
        except PyMongoError as e:
            config.logger.error(f"Failed to connect to MongoDB: {e}", exc_info=True)
            _client = None
            raise
    return _client

def get_database() -> pymongo.database.Database:
    """Return the database object using MONGO_DB_NAME."""
    client = get_mongo_client()
    return client[config.MONGO_DB_NAME]

def seed_database_if_empty():
    """Seed employee_entitlements collection if it doesn't exist or is empty."""
    try:
        db = get_database()
        
        # Ensure it_tickets collection exists (by triggering creation if needed, or just let it auto-create on write)
        if "it_tickets" not in db.list_collection_names():
            db.create_collection("it_tickets")
            config.logger.info("Created empty 'it_tickets' collection.")

        ent_coll = db["employee_entitlements"]
        count = ent_coll.count_documents({})
        if count == 0:
            config.logger.info("Seeding database with default profiles...")
            default_profiles = [
                {
                    "username": "employee_one",
                    "name": "Alice Johnson",
                    "department": "Engineering",
                    "entitlements": {
                        "adobe_creative_suite": False,
                        "office_365": True,
                        "vpn_access": True,
                        "jira": True,
                        "slack": True
                    },
                    "created_at": "2025-01-01T00:00:00Z"
                },
                {
                    "username": "employee_two",
                    "name": "Bob Smith",
                    "department": "Marketing",
                    "entitlements": {
                        "adobe_creative_suite": True,
                        "office_365": True,
                        "vpn_access": True,
                        "jira": False,
                        "slack": True
                    },
                    "created_at": "2025-01-01T00:00:00Z"
                }
            ]
            ent_coll.insert_many(default_profiles)
            config.logger.info("Database seeded successfully with 2 employee profiles.")
        else:
            config.logger.info(f"Database already contains {count} employee profiles. Skipping seed.")
    except PyMongoError as e:
        config.logger.error(f"Error seeding database: {e}", exc_info=True)
        # We don't raise here, we want the app to start up still or handle it gracefully.

def get_employee_profile(username: str) -> dict | None:
    """Query employee_entitlements for matching username. Returns profile or None."""
    config.logger.info(f"Querying employee profile for username: '{username}'")
    try:
        db = get_database()
        profile = db["employee_entitlements"].find_one({"username": username})
        if profile:
            # Convert ObjectId to string if needed, although not strictly requested
            profile["_id"] = str(profile["_id"])
            config.logger.info(f"Successfully found profile for username: '{username}'")
            return profile
        else:
            config.logger.warning(f"Profile not found for username: '{username}'")
            return None
    except PyMongoError as e:
        config.logger.error(f"MongoDB error in get_employee_profile for '{username}': {e}", exc_info=True)
        return None

def check_entitlement(username: str, software_name: str) -> dict:
    """Check if employee has access to a software. Returns dict status, never raises."""
    config.logger.info(f"Checking entitlement for user: '{username}', software: '{software_name}'")
    try:
        profile = get_employee_profile(username)
        if not profile:
            return {"error": "Employee not found", "username": username}

        # Normalize software name to match keys in entitlements dict
        norm_software = software_name.lower().strip()
        key_map = {
            "adobe_creative_suite": "adobe_creative_suite",
            "adobe creative suite": "adobe_creative_suite",
            "adobe": "adobe_creative_suite",
            "office_365": "office_365",
            "office 365": "office_365",
            "office": "office_365",
            "vpn_access": "vpn_access",
            "vpn access": "vpn_access",
            "vpn": "vpn_access",
            "jira": "jira",
            "slack": "slack"
        }

        resolved_key = key_map.get(norm_software)
        if not resolved_key:
            # Fallback direct lookup or key check
            resolved_key = norm_software.replace(" ", "_")

        entitlements = profile.get("entitlements", {})
        has_access = entitlements.get(resolved_key, False)
        
        result = {
            "has_access": bool(has_access),
            "entitlements": entitlements,
            "employee_name": profile.get("name", "Unknown")
        }
        config.logger.info(f"Entitlement check result for '{username}' on '{software_name}' (resolved key '{resolved_key}'): {result['has_access']}")
        return result
    except PyMongoError as e:
        config.logger.error(f"MongoDB error in check_entitlement for user '{username}', software '{software_name}': {e}", exc_info=True)
        return {"error": f"Database error checking entitlement: {str(e)}", "username": username}

def create_ticket(username: str, software_name: str, priority: str, description: str) -> dict:
    """Create an IT ticket. Returns the ticket dict, never raises."""
    config.logger.info(f"Creating access ticket for user: '{username}', software: '{software_name}', priority: '{priority}'")
    try:
        db = get_database()
        
        # Generate ticket id: TKT-<random-6-digit-number>
        ticket_id = f"TKT-{random.randint(100000, 999999)}"
        created_at = datetime.utcnow().isoformat() + "Z"
        
        ticket = {
            "ticket_id": ticket_id,
            "username": username,
            "software_name": software_name,
            "priority": priority.lower().strip(),
            "description": description,
            "status": "open",
            "created_at": created_at,
            "assignee": None
        }
        
        db["it_tickets"].insert_one(ticket)
        # Remove MongoDB internal _id before returning
        if "_id" in ticket:
            ticket["_id"] = str(ticket["_id"])
            
        config.logger.info(f"Created ticket: {ticket_id} successfully.")
        return ticket
    except PyMongoError as e:
        config.logger.error(f"MongoDB error in create_ticket for user '{username}': {e}", exc_info=True)
        return {"error": f"Database error creating ticket: {str(e)}", "username": username}

def get_ticket_status(ticket_id: str) -> dict:
    """Query it_tickets for matching ticket_id. Returns status or error dict, never raises."""
    config.logger.info(f"Querying ticket status for: '{ticket_id}'")
    try:
        db = get_database()
        ticket = db["it_tickets"].find_one({"ticket_id": ticket_id})
        if ticket:
            ticket["_id"] = str(ticket["_id"])
            config.logger.info(f"Found ticket: {ticket_id} status: '{ticket.get('status')}'")
            return ticket
        else:
            config.logger.warning(f"Ticket not found: '{ticket_id}'")
            return {"error": "Ticket not found"}
    except PyMongoError as e:
        config.logger.error(f"MongoDB error in get_ticket_status for '{ticket_id}': {e}", exc_info=True)
        return {"error": f"Database error fetching ticket status: {str(e)}"}

def get_chat_history(username: str) -> list:
    """Retrieve chat history list of dicts for user from deskmate_history database."""
    config.logger.info(f"Retrieving chat history for: '{username}'")
    try:
        client = get_mongo_client()
        db = client["deskmate_history"]
        doc = db["chat_history"].find_one({"username": username})
        if doc and "messages" in doc:
            return doc["messages"]
        return []
    except PyMongoError as e:
        config.logger.error(f"Error retrieving chat history for '{username}': {e}", exc_info=True)
        return []

def save_chat_history(username: str, messages: list) -> bool:
    """Save/update chat history list of dicts for user in deskmate_history database."""
    config.logger.info(f"Saving chat history for: '{username}' with {len(messages)} messages.")
    try:
        client = get_mongo_client()
        db = client["deskmate_history"]
        db["chat_history"].update_one(
            {"username": username},
            {"$set": {
                "messages": messages,
                "updated_at": datetime.utcnow()
            }},
            upsert=True
        )
        return True
    except PyMongoError as e:
        config.logger.error(f"Error saving chat history for '{username}': {e}", exc_info=True)
        return False

def clear_chat_history(username: str) -> bool:
    """Delete chat history document for user in deskmate_history database."""
    config.logger.info(f"Clearing chat history for: '{username}'")
    try:
        client = get_mongo_client()
        db = client["deskmate_history"]
        db["chat_history"].delete_one({"username": username})
        return True
    except PyMongoError as e:
        config.logger.error(f"Error clearing chat history for '{username}': {e}", exc_info=True)
        return False
