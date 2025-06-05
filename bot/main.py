import logging
import datetime
import shortuuid
from pymongo import MongoClient, DESCENDING
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
import asyncio

# Import configuration from the root directory
import sys
sys.path.append('..') # Adds the parent directory to the Python path
import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Pyrogram Client
app = Client(
    "file_storage_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# Initialize MongoDB Client
mongo_client = MongoClient(config.MONGO_URI)
db = mongo_client[config.MONGO_DB_NAME]
files_collection = db["files"]

# Ensure indexes for MongoDB
if "files" not in db.list_collection_names() or not files_collection.index_information():
    logger.info("Creating MongoDB indexes for 'files' collection...")
    files_collection.create_index("file_id", unique=True)
    files_collection.create_index("upload_timestamp")
    files_collection.create_index("view_count")
    files_collection.create_index("uploaded_by_user_id")
    logger.info("MongoDB indexes created.")


def generate_file_id():
    """Generates a short, unique, URL-friendly file ID."""
    return shortuuid.uuid()[:10] # Generate a ~10 char ID

async def get_file_details(message: Message):
    """Extracts file details from a Pyrogram message."""
    file_type = None
    file_ob = None
    original_file_name = None

    if message.document:
        file_type = "document"
        file_ob = message.document
        original_file_name = file_ob.file_name
    elif message.video:
        file_type = "video"
        file_ob = message.video
        original_file_name = file_ob.file_name or f"video_{message.id}.mp4"
    elif message.photo:
        file_type = "photo"
        # For photos, message.photo is a Photo object which contains a list of PhotoSize
        # We'll pick the largest one for file_id and size reference
        if message.photo.sizes:
            file_ob = message.photo.sizes[-1] # Largest PhotoSize
        else: # Fallback if sizes list is empty for some reason (unlikely)
            file_ob = message.photo
        original_file_name = f"photo_{message.id}.jpg" # Photos don't have file_name attribute directly
    elif message.audio:
        file_type = "audio"
        file_ob = message.audio
        original_file_name = file_ob.file_name or f"audio_{message.id}.mp3"
    elif message.voice:
        file_type = "voice"
        file_ob = message.voice
        original_file_name = f"voice_{message.id}.ogg"

    if file_ob:
        return {
            "tg_file_id": file_ob.file_id, # This is the file_id of the specific PhotoSize for photos
            "file_type": file_type,
            "original_file_name": original_file_name,
            "mime_type": getattr(file_ob, 'mime_type', None), # PhotoSize doesn't have mime_type directly
            "file_size": getattr(file_ob, 'file_size', None), # Same for file_size
        }
    return None

@app.on_message(filters.command("start") & filters.private)
async def start_command_handler(client: Client, message: Message):
    await message.reply_text(
        "Hello! I am your personal file storage bot.\n"
        "Send me any file, and I will store it and give you a permanent link.\n"
        f"Make sure I am an admin in the storage channel (ID: {config.STORAGE_CHANNEL_ID}) "
        "with rights to post messages."
    )

@app.on_message((filters.document | filters.video | filters.photo | filters.audio | filters.voice) & filters.private)
async def file_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_firstname = message.from_user.first_name

    file_details_extracted = await get_file_details(message) # Renamed to avoid conflict
    if not file_details_extracted:
        await message.reply_text("Sorry, I couldn't process this file type.")
        return

    try:
        # For photos, forward the original message, not just a PhotoSize.
        # The message object itself (message.photo) represents the photo with all its sizes.
        # When forwarding, Telegram handles sending the best representation or the full media.
        # The file_id used for metadata can be from the largest PhotoSize for reference.
        
        await message.reply_text("Processing your file...", quote=True)
        
        forwarded_messages = await client.forward_messages(
            chat_id=config.STORAGE_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_ids=message.id
        )
        
        if not forwarded_messages:
            await message.reply_text("Failed to forward the file to the storage channel. Please check my permissions.")
            logger.error(f"Failed to forward message {message.id} to channel {config.STORAGE_CHANNEL_ID}")
            return

        forwarded_message = forwarded_messages[0]
        message_id_in_storage = forwarded_message.id

        unique_file_id = generate_file_id()
        while files_collection.find_one({"file_id": unique_file_id}):
            unique_file_id = generate_file_id()

        file_metadata = {
            "file_id": unique_file_id,
            "tg_file_id_ref": file_details_extracted["tg_file_id"], # Reference TG file_id (e.g., of largest photo size)
            "original_file_name": file_details_extracted["original_file_name"],
            "file_type": file_details_extracted["file_type"],
            "mime_type": file_details_extracted["mime_type"],
            "file_size": file_details_extracted["file_size"],
            "message_id_in_storage": message_id_in_storage,
            "storage_channel_id": config.STORAGE_CHANNEL_ID,
            "uploaded_by_user_id": user_id,
            "uploaded_by_user_firstname": user_firstname,
            "upload_timestamp": datetime.datetime.utcnow(),
            "view_count": 0,
        }

        files_collection.insert_one(file_metadata)
        logger.info(f"Stored metadata for file: {unique_file_id} (Original: {file_details_extracted['original_file_name']})")

        access_link = f"{config.WEB_APP_BASE_URL}/file/{unique_file_id}"

        await message.reply_text(
            f"File uploaded successfully!\n\n"
            f"Name: {file_details_extracted['original_file_name']}\n"
            f"Type: {file_details_extracted['file_type']}\n"
            f"Access Link: {access_link}",
            quote=True
        )

        admin_message_text = ( # Renamed variable
            f"🆕 New File Uploaded!\n\n"
            f"👤 By: {user_firstname} (ID: {user_id})\n"
            f"📄 File: {file_details_extracted['original_file_name']}\n"
            f"🔗 Link: {access_link}\n"
            f"🆔 File ID: {unique_file_id}"
        )
        try:
            await client.send_message(chat_id=config.ADMIN_USER_ID, text=admin_message_text)
        except Exception as e:
            logger.error(f"Failed to send notification to admin {config.ADMIN_USER_ID}: {e}")

    except FloodWait as e:
        logger.warning(f"FloodWait: sleeping for {e.value} seconds.")
        await asyncio.sleep(e.value)
        await file_handler(client, message) 
    except Exception as e:
        logger.error(f"Error handling file from user {user_id}: {e}", exc_info=True)
        await message.reply_text("An error occurred while processing your file. Please try again later.")

async def run_bot():
    logger.info("Starting bot...")
    
    # Check MongoDB connection
    try:
        mongo_client.admin.command('ping')
        logger.info("MongoDB connection successful.")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}. Please ensure MongoDB is running and accessible.")
        logger.error(f"Mongo URI was: {config.MONGO_URI}")
        logger.error("Bot will not start without a database connection.")
        return

    # Pyrogram client startup and shutdown logic
    try:
        await app.start()
        logger.info("Bot started successfully! Press Ctrl+C to stop.")
        await asyncio.Event().wait()  # Keep the bot running
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received...")
    finally:
        logger.info("Stopping Pyrogram client...")
        if app.is_initialized and not app.is_stopped: # Check if client was started and not yet stopped
            await app.stop()
            logger.info("Pyrogram client stopped.")
        else:
            logger.info("Pyrogram client was not running or already stopped.")
        # mongo_client.close() # Generally not needed as Pymongo handles pool connections,
                             # but can be added if explicit close is desired on script exit.
        logger.info("Bot shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        # This catches Ctrl+C if it happens very early, before asyncio.run() fully sets up its own signal handling
        logger.info("Bot process terminated by user (KeyboardInterrupt at top level).")
    except Exception as e:
        logger.critical(f"An unrecoverable error occurred at the top level: {e}", exc_info=True)