import logging
import datetime
import shortuuid
from pymongo import MongoClient, DESCENDING
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait, AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan
import asyncio
import signal

# Import configuration from the root directory
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config # This should now reliably find config.py in the project_root

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING) # Quieten Pyrogram for cleaner logs

app_client_instance: Client = None # Renamed to avoid conflict with flask 'app'

async def graceful_shutdown(signal_received, loop):
    logger.info(f"Shutdown signal {signal_received} received. Starting graceful shutdown...")
    global app_client_instance
    if app_client_instance and app_client_instance.is_initialized:
        if app_client_instance.is_connected:
            logger.info("Stopping Pyrogram client...")
            try:
                await app_client_instance.stop()
                logger.info("Pyrogram client stopped.")
            except Exception as e:
                logger.error(f"Error stopping Pyrogram client: {e}", exc_info=True)
        else:
            logger.info("Pyrogram client was initialized but not connected, or already stopped.")
    else:
        logger.info("Pyrogram client was not initialized or instance is None.")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        logger.info(f"Cancelling {len(tasks)} outstanding tasks...")
        [task.cancel() for task in tasks]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Outstanding tasks cancelled.")
        except asyncio.CancelledError:
            logger.info("Tasks were cancelled as part of shutdown.")
        except Exception as e:
            logger.error(f"Error during task cancellation: {e}", exc_info=True)

    if loop.is_running():
        loop.stop()
    logger.info("Bot shutdown sequence complete.")


def init_mongodb_client():
    logger.info("Initializing MongoDB connection for bot...")
    if not config.MONGO_URI:
        logger.error("MONGO_URI is not set in config. Cannot connect to MongoDB.")
        return None, None, None
    try:
        mongo_client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')
        logger.info(f"Bot MongoDB connection successful to URI ending with: ...{config.MONGO_URI[-30:]}")
        db = mongo_client[config.MONGO_DB_NAME]
        
        files_collection = db["files"]
        if "files" not in db.list_collection_names() or not files_collection.index_information():
            logger.info("Creating MongoDB indexes for 'files' collection (bot)...")
            files_collection.create_index("file_id", unique=True)
            files_collection.create_index("upload_timestamp")
            files_collection.create_index("view_count")
            files_collection.create_index("uploaded_by_user_id")
            logger.info("MongoDB indexes for 'files' created/verified (bot).")
        return mongo_client, db, files_collection
    except Exception as e:
        logger.error(f"Bot MongoDB connection/setup failed: {e}", exc_info=True)
        logger.error(f"Mongo URI used by bot: {config.MONGO_URI}")
        return None, None, None

mongo_client_conn, db_conn, files_collection_conn = init_mongodb_client()

def generate_file_id_str(): # Renamed to avoid conflict
    return shortuuid.uuid()[:10]

async def get_file_details_dict(message: Message): # Renamed
    file_type, file_ob, original_file_name = None, None, None
    if message.document:
        file_type, file_ob, original_file_name = "document", message.document, message.document.file_name
    elif message.video:
        file_type, file_ob, original_file_name = "video", message.video, message.video.file_name or f"video_{message.id}.mp4"
    elif message.photo:
        file_type = "photo"
        file_ob = message.photo.sizes[-1] if message.photo.sizes else message.photo
        original_file_name = f"photo_{message.id}.jpg"
    elif message.audio:
        file_type, file_ob, original_file_name = "audio", message.audio, message.audio.file_name or f"audio_{message.id}.mp3"
    elif message.voice:
        file_type, file_ob, original_file_name = "voice", message.voice, f"voice_{message.id}.ogg"
    
    if file_ob:
        return {"tg_file_id": file_ob.file_id, "file_type": file_type, "original_file_name": original_file_name,
                "mime_type": getattr(file_ob, 'mime_type', None), "file_size": getattr(file_ob, 'file_size', None)}
    return None

async def run_bot_main_logic(): # Renamed
    global app_client_instance
    logger.info("Bot main function (run_bot_main_logic) started.")

    if not all([config.API_ID, config.API_HASH, config.BOT_TOKEN]):
        logger.critical("Telegram API_ID, API_HASH, or BOT_TOKEN is missing in config. Exiting.")
        return
    if not mongo_client_conn or not db_conn or not files_collection_conn:
        logger.critical("MongoDB is not initialized for bot. Bot cannot start. Exiting.")
        return

    app_client_instance = Client(
        "file_storage_bot_session", # Session name
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN
    )

    # Add handlers
    @app_client_instance.on_message(filters.command("start") & filters.private)
    async def start_command_handler_func(client: Client, message: Message): # Renamed
        logger.info(f"Received /start from user {message.from_user.id} (username: @{message.from_user.username}) in chat {message.chat.id}")
        try:
            reply_text = (
                "Hello! I am your personal file storage bot.\n"
                "Send me any file, and I will store it and give you a permanent link.\n"
                f"Make sure I am an admin in the storage channel (ID: {config.STORAGE_CHANNEL_ID}) "
                "with rights to post messages."
            )
            await message.reply_text(reply_text, quote=True)
            logger.info(f"Replied to /start for user {message.from_user.id}")
        except Exception as e:
            logger.error(f"Error in start_command_handler for user {message.from_user.id}: {e}", exc_info=True)

    @app_client_instance.on_message((filters.document | filters.video | filters.photo | filters.audio | filters.voice) & filters.private)
    async def file_handler_func(client: Client, message: Message): # Renamed
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
        logger.info(f"Received file from user {user_id} (username: {username}), type: {message.media}")
        
        if not files_collection_conn: # Check if DB connection is still valid
            logger.error(f"Database connection lost. Cannot process file for user {user_id}.")
            await message.reply_text("Internal error: Database connection issue. Please try again later.")
            return

        file_details = await get_file_details_dict(message)
        if not file_details:
            logger.warning(f"Could not extract file details for message {message.id} from user {user_id}")
            await message.reply_text("Sorry, I couldn't process this file type.")
            return

        processing_msg = await message.reply_text("Processing your file...", quote=True)
        try:
            forwarded_messages = await client.forward_messages(
                chat_id=config.STORAGE_CHANNEL_ID, from_chat_id=message.chat.id, message_ids=message.id)
            
            if not forwarded_messages:
                logger.error(f"Failed to forward message {message.id} to channel {config.STORAGE_CHANNEL_ID} for user {user_id}")
                await processing_msg.edit_text("Failed to forward file. Check bot permissions in storage channel.")
                return

            forwarded_message = forwarded_messages[0]
            unique_id = generate_file_id_str()
            # Ensure uniqueness in DB, though shortuuid makes collisions rare
            while files_collection_conn.count_documents({"file_id": unique_id}) > 0:
                unique_id = generate_file_id_str()

            file_metadata = {
                "file_id": unique_id, "tg_file_id_ref": file_details["tg_file_id"],
                "original_file_name": file_details["original_file_name"], "file_type": file_details["file_type"],
                "mime_type": file_details["mime_type"], "file_size": file_details["file_size"],
                "message_id_in_storage": forwarded_message.id, "storage_channel_id": config.STORAGE_CHANNEL_ID,
                "uploaded_by_user_id": user_id, "uploaded_by_user_firstname": message.from_user.first_name,
                "upload_timestamp": datetime.datetime.utcnow(), "view_count": 0}

            files_collection_conn.insert_one(file_metadata)
            logger.info(f"Stored metadata for file: {unique_id} (orig: {file_details['original_file_name']}) from user {user_id}")

            access_link = f"{config.WEB_APP_BASE_URL}/file/{unique_id}"
            reply_text = (f"File uploaded successfully!\n\nName: {file_details['original_file_name']}\n"
                          f"Type: {file_details['file_type']}\nAccess Link: {access_link}")
            await processing_msg.edit_text(reply_text)

            admin_notify_text = (f"🆕 New File Uploaded!\n👤 By: {message.from_user.first_name} (ID: {user_id}, User: {username})\n"
                                 f"📄 File: {file_details['original_file_name']}\n🔗 Link: {access_link}\n🆔 File ID: {unique_id}")
            if config.ADMIN_USER_ID:
                await client.send_message(chat_id=config.ADMIN_USER_ID, text=admin_notify_text)
        except FloodWait as e:
            logger.warning(f"FloodWait for {e.value}s encountered for user {user_id}. Sleeping...")
            await asyncio.sleep(e.value)
            await file_handler_func(client, message) # Retry
        except Exception as e:
            logger.error(f"Error in file_handler for user {user_id}, file {file_details.get('original_file_name', 'N/A')}: {e}", exc_info=True)
            try:
                await processing_msg.edit_text("An error occurred while processing your file. Please try again later or contact support.")
            except Exception as e_edit:
                logger.error(f"Failed to edit processing message after error: {e_edit}")


    logger.info("Attempting to start Pyrogram client instance...")
    try:
        await app_client_instance.start()
        me = await app_client_instance.get_me()
        logger.info(f"Pyrogram client started successfully as @{me.username} (ID: {me.id}). Bot is now listening for messages.")
        await idle() # Keep the bot alive until SIGINT/SIGTERM or unhandled error in loop
        logger.info("Pyrogram client idle() returned. Bot is preparing to stop or has been stopped.")

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan) as e:
        logger.critical(f"CRITICAL TELEGRAM AUTH ERROR: {e}. BOT_TOKEN might be invalid or bot banned/deleted. Exiting.", exc_info=True)
    except ConnectionError as e:
         logger.critical(f"PYROGRAM CONNECTION ERROR during startup: {e}. Check network or Telegram service status. Exiting.", exc_info=True)
    except Exception as e:
        logger.critical(f"UNEXPECTED ERROR during Pyrogram client lifecycle: {e}", exc_info=True)
    # `finally` block for cleanup is handled by the signal handler's call to graceful_shutdown


if __name__ == "__main__":
    logger.info(f"Bot script __main__ execution started. Python version: {sys.version.split()[0]}")
    current_loop = asyncio.get_event_loop()

    for sig_name in (signal.SIGINT, signal.SIGTERM):
        current_loop.add_signal_handler(sig_name, lambda s=sig_name: asyncio.create_task(graceful_shutdown(s, current_loop)))
    
    try:
        logger.info("Running bot's main logic coroutine (run_bot_main_logic)...")
        current_loop.run_until_complete(run_bot_main_logic())
    except asyncio.CancelledError:
        logger.info("Main logic coroutine was cancelled (expected during shutdown).")
    # KeyboardInterrupt should ideally be handled by SIGINT signal handler.
    # This is a fallback if signals aren't caught as expected (e.g. on some Windows setups or if loop is already stopping)
    except KeyboardInterrupt: 
        logger.info("KeyboardInterrupt caught at top level of __main__. Forcing shutdown if not already handled.")
        if not current_loop.is_closed(): # Check if loop is still there to run shutdown
            # Check if graceful_shutdown is already pending or running (hard to do perfectly)
            # For simplicity, just call it if loop isn't closed. It should be idempotent enough.
            current_loop.run_until_complete(graceful_shutdown("KeyboardInterrupt_Fallback", current_loop))
    except Exception as e:
        logger.critical(f"Unhandled fatal exception in __main__ run block: {e}", exc_info=True)
    finally:
        logger.info("Main script __name__ == '__main__' block finishing.")
        if current_loop.is_running():
            logger.warning("Event loop was still running in final finally block. Stopping.")
            current_loop.stop()
        if not current_loop.is_closed():
            logger.info("Closing event loop.")
            current_loop.close()
        logger.info("Event loop closed. Bot script finished.")
