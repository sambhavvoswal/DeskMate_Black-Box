import os
import logging
from dotenv import load_dotenv

# Load env variables from .env if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("deskmate")

# Constants
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
TOOL_TIMEOUT_SECONDS = 30

# Retrieve environment variables
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "deskmate")

# Validation
missing_keys = []
if not MONGO_URI:
    missing_keys.append("MONGO_URI")

if missing_keys:
    error_msg = f"Missing required environment variables: {', '.join(missing_keys)}"
    logger.critical(error_msg)
    raise ValueError(error_msg)

if not ANTHROPIC_API_KEY and not OPENROUTER_API_KEY:
    error_msg = "Missing required API keys: At least one of ANTHROPIC_API_KEY or OPENROUTER_API_KEY must be provided."
    logger.critical(error_msg)
    raise ValueError(error_msg)

logger.info("Configuration loaded successfully.")
