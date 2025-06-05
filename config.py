import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Telegram Bot Configuration
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID")) # Must be an integer
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID")) # Must be an integer

# Web Application Configuration
WEB_APP_BASE_URL = os.getenv("WEB_APP_BASE_URL", "http://localhost:5000")
FLASK_ADMIN_PASSWORD = os.getenv("FLASK_ADMIN_PASSWORD", "admin") # Default for local dev
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev_secret_key") # Default for local dev

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "telegram_file_store")

# Helper to get the numeric part of channel ID for t.me/c/ links
def get_telegram_link_channel_id(channel_id: int) -> int:
    if str(channel_id).startswith("-100"):
        return int(str(channel_id)[4:])
    elif str(channel_id).startswith("-"):
         return int(str(channel_id)[1:]) # For older chat IDs, though less common for channels
    return channel_id