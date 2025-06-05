import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
# This is mainly for local development. Systemd's EnvironmentFile handles it in production.
load_dotenv()

# Telegram Bot Configuration
try:
    API_ID = int(os.getenv("API_ID"))
    STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID"))
    ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
except (TypeError, ValueError) as e:
    print(f"Error: Ensure API_ID, STORAGE_CHANNEL_ID, and ADMIN_USER_ID are valid integers in .env: {e}")
    # Optionally raise an error or exit if these are critical and missing
    # For now, let it proceed and Pyrogram/other parts might fail later if these are None
    API_ID = None
    STORAGE_CHANNEL_ID = None
    ADMIN_USER_ID = None


API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")


# Web Application Configuration
WEB_APP_BASE_URL = os.getenv("WEB_APP_BASE_URL", "http://localhost:5000")
FLASK_ADMIN_PASSWORD = os.getenv("FLASK_ADMIN_PASSWORD", "admin")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "telegram_file_store")

if not all([API_ID, API_HASH, BOT_TOKEN, STORAGE_CHANNEL_ID, ADMIN_USER_ID, MONGO_URI, MONGO_DB_NAME, WEB_APP_BASE_URL]):
    print("Warning: One or more critical environment variables are missing. Check your .env file or environment setup.")

def get_telegram_link_channel_id(channel_id: int) -> int:
    if not channel_id: # Handle case where channel_id might be None due to parsing error
        return 0 # Or raise an error, or return a default that will clearly fail
    s_channel_id = str(channel_id)
    if s_channel_id.startswith("-100"):
        return int(s_channel_id[4:])
    elif s_channel_id.startswith("-"):
         return int(s_channel_id[1:])
    return channel_id
