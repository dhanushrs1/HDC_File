#(©)CodeXBotz

import os
import logging
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

load_dotenv()

#Bot token @Botfather
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")

#Your API ID from my.telegram.org
APP_ID = int(os.environ.get("APP_ID", ""))

#Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", "")

#Your db channel Id
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", ""))

#OWNER ID
OWNER_ID = int(os.environ.get("OWNER_ID", ""))

#Port
PORT = os.environ.get("PORT", "8080")

#Database
DB_URI = os.environ.get("DATABASE_URL", "")
DB_NAME = os.environ.get("DATABASE_NAME", "filesharexbot")

# Web Redirector URL
REDIRECT_URL = os.environ.get("REDIRECT_URL", "")

# --- Feature Customization ---
START_MSG = os.environ.get("START_MESSAGE", "👋 **Hello {first}!**\n\nI am the File Sharing Bot from CodeXBotz. I can store your files securely and provide a permanent, shareable link.\n\nUse the buttons below to learn more about my features or get help.")
START_PIC = os.environ.get("START_PIC","")
FORCE_MSG = os.environ.get("FORCE_SUB_MESSAGE", "Hello {first}\n\n<b>You need to join in my Channel/Group to use me\n\nKindly Please join Channel</b>")
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)
PROTECT_CONTENT = True if os.environ.get('PROTECT_CONTENT', "False") == "True" else False
DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", None) == 'True'
USER_REPLY_TEXT = "❌Don't send me messages directly I'm only File Share bot!"
# This variable was missing, causing the error. It is now included.
BOT_STATS_TEXT = "<b>BOT UPTIME</b>\n{uptime}"


# --- Video Workspace Settings ---
SCREENSHOT_WATERMARK = os.environ.get("SCREENSHOT_WATERMARK", "HDCinema")
SCREENSHOT_FONT_SCALE = float(os.environ.get("SCREENSHOT_FONT_SCALE", "1.0"))
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "1800"))

# --- Smart File Expiry Settings ---
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "10"))
INITIAL_DELETE_MSG = os.environ.get("INITIAL_DELETE_MSG", "⚠️ This file is temporary and will expire in {time}. Please save it.")
EXPIRED_MSG = os.environ.get("EXPIRED_MSG", "⏳ <b>This file has expired.</b>\n\nYou can request the file again within the next {hours} hours.")
RE_REQUEST_EXPIRY_HOURS = int(os.environ.get("RE_REQUEST_EXPIRY_HOURS", "24"))
FINAL_EXPIRED_MSG = os.environ.get("FINAL_EXPIRED_MSG", "🚫 <b>This re-request link has also expired.</b>\n\nPlease get a fresh link to access this file.")


# --- Bot Internals ---
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "-1001632709359"))
JOIN_REQUEST_ENABLE = os.environ.get("JOIN_REQUEST_ENABLED", None)
TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "4"))
ADMINS=[]
try:
    for x in (os.environ.get("ADMINS", "").split()):
        ADMINS.append(int(x))
except ValueError:
        raise Exception("Your Admins list does not contain valid integers.")
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
