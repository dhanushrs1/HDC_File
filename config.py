"""
(©) HD Cinema Bot

This file holds all the configuration for the bot.

- It uses python-dotenv to load environment variables from a .env file.
- It includes robust error handling for missing or invalid variables.
- All settings are clearly documented.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Helper Functions for Safe Configuration Loading ---

def get_env_var(name: str, default=None, required: bool = False, is_int: bool = False, is_float: bool = False):
    """
    Safely retrieves an environment variable.
    Exits the application if a required variable is missing or has an invalid type.
    """
    value = os.environ.get(name)
    
    if value is None:
        if required:
            logging.critical(f"FATAL ERROR: Required environment variable '{name}' is not set.")
            sys.exit(1)
        return default

    if is_int:
        try:
            return int(value)
        except ValueError:
            logging.critical(f"FATAL ERROR: Env var '{name}' must be an integer, but got '{value}'.")
            sys.exit(1)
            
    if is_float:
        try:
            return float(value)
        except ValueError:
            logging.critical(f"FATAL ERROR: Env var '{name}' must be a float, but got '{value}'.")
            sys.exit(1)
            
    return value

def get_bool_env_var(name: str, default: bool = False) -> bool:
    """
    Retrieves a boolean environment variable, accepting 'true', '1', or 'yes' as True.
    """
    value = os.environ.get(name, str(default)).lower()
    return value in ['true', '1', 'yes']

# ======================================================================================
#                               *** CORE BOT SETTINGS ***
#                  These are essential for the bot to run. Do not leave blank.
# ======================================================================================

# --- Telegram API Credentials ---
API_ID = get_env_var("APP_ID", required=True, is_int=True)
API_HASH = get_env_var("API_HASH", required=True)
TG_BOT_TOKEN = get_env_var("TG_BOT_TOKEN", required=True)

# --- Bot Owner and Database ---
OWNER_ID = get_env_var("OWNER_ID", required=True, is_int=True)
CHANNEL_ID = get_env_var("CHANNEL_ID", required=True, is_int=True) # ID of the private channel for storing files

# ======================================================================================
#                             *** DATABASE & WEB SETTINGS ***
# ======================================================================================

DB_URI = get_env_var("DATABASE_URL", required=True)
DB_NAME = get_env_var("DATABASE_NAME", default="HD_Cinema_Bot")
PORT = get_env_var("PORT", default="8080")
# The base URL of your web redirector (e.g., your Blogger or Render URL)
REDIRECT_URL = get_env_var("REDIRECT_URL", required=True)

# ======================================================================================
#                              *** FEATURE CUSTOMIZATION ***
# ======================================================================================

# --- User-Facing Messages ---
START_MSG = get_env_var("START_MESSAGE", default="👋 Hello {first}!\n\nI am the <b>HD Cinema File Bot</b>. I can store your files securely and generate permanent, shareable links. This service is for authorized admins only.")
START_PIC = get_env_var("START_PIC", default="") # URL for a start image
CUSTOM_CAPTION = get_env_var("CUSTOM_CAPTION", default=None) # Custom caption for files
GROUP_SEARCH_PIC = get_env_var("GROUP_SEARCH_PIC", default="") # URL for the image sent with group search results

# --- Security & Access Control ---
PROTECT_CONTENT = get_bool_env_var('PROTECT_CONTENT', default=False) # Prevent forwarding of bot's messages
DISABLE_CHANNEL_BUTTON = get_bool_env_var("DISABLE_CHANNEL_BUTTON", default=True) # Disable the "Share Link" button in the DB channel

# --- Force Subscribe ---
FORCE_SUB_CHANNEL = get_env_var("FORCE_SUB_CHANNEL", default=0, is_int=True) # Set to 0 to disable
JOIN_REQUEST_ENABLE = get_bool_env_var("JOIN_REQUEST_ENABLED", default=False)
FORCE_MSG = get_env_var("FORCE_SUB_MESSAGE", default="Hello {first},\n\n<b>To use this bot, you must join our channel.</b>\n\nThis helps us continue providing great content. Please join and try again! 😊")

# --- Video Workspace & Temp File Manager ---
TEMP_DIR = get_env_var("TEMP_DIR", default="temp_downloads/") # Directory for temporary files
SESSION_TIMEOUT = get_env_var("SESSION_TIMEOUT", default=1800, is_int=True) # In seconds (30 minutes)

# --- Smart File Expiry ---
AUTO_DELETE_TIME = get_env_var("AUTO_DELETE_TIME", default=600, is_int=True) # In seconds (10 minutes)
EXPIRED_MSG = get_env_var("EXPIRED_MSG", default="⏳ <b>This file has expired.</b>\n\nYou can request it again within the next {hours} hours.")
RE_REQUEST_EXPIRY_HOURS = get_env_var("RE_REQUEST_EXPIRY_HOURS", default=24, is_int=True)
FINAL_EXPIRED_MSG = get_env_var("FINAL_EXPIRED_MSG", default="🚫 <b>This re-request link has also expired.</b>")

# ======================================================================================
#                                *** BOT INTERNALS ***
#                      (You should not need to change these settings)
# ======================================================================================

# --- Performance ---
TG_BOT_WORKERS = get_env_var("TG_BOT_WORKERS", default=4, is_int=True)

# --- Admin List ---
# Automatically creates a list of admins from the ADMINS env var and always includes the OWNER_ID.
ADMINS = []
raw_admins = get_env_var("ADMINS", default="").split()
for admin_id in raw_admins:
    if admin_id.isdigit():
        ADMINS.append(int(admin_id))
    else:
        logging.warning(f"Invalid ADMIN ID '{admin_id}' found in environment variables. It has been ignored.")

if OWNER_ID not in ADMINS:
    ADMINS.append(OWNER_ID)

# --- Logging Setup ---
LOG_FILE_NAME = "hd_cinema_bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(
            LOG_FILE_NAME,
            maxBytes=50_000_000,  # 50 MB
            backupCount=10
        ),
        logging.StreamHandler(sys.stdout) # Also log to console
    ]
)
# Reduce verbosity of pyrogram's logs
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def LOGGER(name: str) -> logging.Logger:
    """A helper function to get a logger instance for any module."""
    return logging.getLogger(name)
