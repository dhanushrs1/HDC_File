import os
import logging
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
import sys

load_dotenv()

def get_env_var(name, is_int=False, is_float=False, default=None, required=False):
    """
    A helper function to safely get environment variables.
    It will exit the bot if a required variable is missing.
    """
    value = os.environ.get(name)
    
    if value is None:
        if required:
            print(f"FATAL ERROR: Required environment variable '{name}' is not set. Please add it to your .env file or deployment secrets.")
            sys.exit(1)
        return default

    if is_int:
        try:
            return int(value)
        except ValueError:
            print(f"FATAL ERROR: Environment variable '{name}' is expected to be an integer, but got '{value}'.")
            sys.exit(1)
    elif is_float:
        try:
            return float(value)
        except ValueError:
            print(f"FATAL ERROR: Environment variable '{name}' is expected to be a float, but got '{value}'.")
            sys.exit(1)
    
    return value

# ================================================================
#                       *** CORE SETTINGS ***
#       These are essential for the bot to run. Do not leave blank.
# ================================================================

TG_BOT_TOKEN = get_env_var("TG_BOT_TOKEN", required=True)
APP_ID = get_env_var("APP_ID", is_int=True, required=True)
API_HASH = get_env_var("API_HASH", required=True)
OWNER_ID = get_env_var("OWNER_ID", is_int=True, required=True)
CHANNEL_ID = get_env_var("CHANNEL_ID", is_int=True, required=True)

# ================================================================
#                   *** DATABASE & WEB SETTINGS ***
# ================================================================

DB_URI = get_env_var("DATABASE_URL", required=True)
DB_NAME = get_env_var("DATABASE_NAME", default="filesharexbot")
PORT = get_env_var("PORT", default="8080")
REDIRECT_URL = get_env_var("REDIRECT_URL", required=True)

# ================================================================
#                  *** FEATURE CUSTOMIZATION ***
# ================================================================

# --- General ---
START_MSG = get_env_var("START_MESSAGE", default="👋 Hello {first}!\n\nWelcome to <b>HD Cinema by FilmyStop Movies</b>.")
START_PIC = get_env_var("START_PIC", default="")
CUSTOM_CAPTION = get_env_var("CUSTOM_CAPTION", default=None)
USER_REPLY_TEXT = get_env_var("USER_REPLY_TEXT", default="❌ Don't send me messages directly. I am only a File Share bot!")
BOT_STATS_TEXT = get_env_var("BOT_STATS_TEXT", default="📊 <b>Bot Uptime:</b> {uptime}") # This was the missing variable

# --- Security & Access ---
PROTECT_CONTENT = get_env_var('PROTECT_CONTENT', default="False").lower() == "true"
DISABLE_CHANNEL_BUTTON = get_env_var("DISABLE_CHANNEL_BUTTON", default="False").lower() == 'true'

# --- Force Subscribe ---
FORCE_SUB_CHANNEL = get_env_var("FORCE_SUB_CHANNEL", is_int=True, default=0)
JOIN_REQUEST_ENABLE = get_env_var("JOIN_REQUEST_ENABLED", default="False").lower() == "true"
FORCE_MSG = get_env_var("FORCE_SUB_MESSAGE", default="Hello {first}\n\n<b>You need to join my Channel/Group to use me.</b>")

# --- Video Workspace Settings ---
SCREENSHOT_WATERMARK = get_env_var("SCREENSHOT_WATERMARK", default="HDCinema")
SCREENSHOT_FONT_SCALE = get_env_var("SCREENSHOT_FONT_SCALE", is_float=True, default=1.0)
SESSION_TIMEOUT = get_env_var("SESSION_TIMEOUT", is_int=True, default=1800)

# --- Smart File Expiry Settings ---
AUTO_DELETE_TIME = get_env_var("AUTO_DELETE_TIME", is_int=True, default=600)
INITIAL_DELETE_MSG = get_env_var("INITIAL_DELETE_MSG", default="⚠️ This file is temporary and will expire in {time}.")
EXPIRED_MSG = get_env_var("EXPIRED_MSG", default="⏳ <b>This file has expired.</b>\n\nYou can request the file again within the next {hours} hours.")
RE_REQUEST_EXPIRY_HOURS = get_env_var("RE_REQUEST_EXPIRY_HOURS", is_int=True, default=24)
FINAL_EXPIRED_MSG = get_env_var("FINAL_EXPIRED_MSG", default="🚫 <b>This re-request link has also expired.</b>")

# ================================================================
#                      *** BOT INTERNALS ***
#                 (Generally do not need to be changed)
# ================================================================

TG_BOT_WORKERS = get_env_var("TG_BOT_WORKERS", is_int=True, default=4)

# --- Admins List ---
ADMINS = []
raw_admins = get_env_var("ADMINS", default="").split()
for admin_id in raw_admins:
    if admin_id: # Ensure empty strings are not processed
        try:
            ADMINS.append(int(admin_id))
        except ValueError:
            print(f"Warning: Invalid ADMIN ID '{admin_id}' found in environment variables. It has been ignored.")
if OWNER_ID not in ADMINS:
    ADMINS.append(OWNER_ID)

# --- Logging ---
LOG_FILE_NAME = "filesharingbot.txt"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(
            LOG_FILE_NAME,
            maxBytes=50000000,
            backupCount=10
        ),
        logging.StreamHandler()
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)

