import logging
import datetime
import shortuuid
from pymongo import MongoClient, DESCENDING
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait, AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan
import asyncio
import signal # For signal handling

# Import configuration from the root directory
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s', # Added module and lineno
    handlers=[
        logging.StreamHandler(sys.stdout) # Ensure logs go to stdout for journalctl
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING) # Quieten Pyrogram's own INFO logs if too verbose

# Global variable for the client, to be accessible by signal handler
app_client: Client = None

async def graceful_shutdown(signal_received, loop):
    logger.info(f"Shutdown signal {signal_received} received. Starting graceful shutdown...")
    if app_client and app_client.is_initialized and not app_client.is_stopped:
        logger.info("Stopping Pyrogram client...")
        try:
            await app_client.stop()
            logger.info("Pyrogram client stopped.")
        except Exception as e:
            logger.error(f"Error stopping Pyrogram client: {e}", exc_info=True)
    
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
    logger.info("Bot shutdown complete.")


def init_mongodb():
    logger.info("Initializing MongoDB connection...")
    try:
        mongo_client_instance = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client_instance.admin.command('ping')
        logger.info(f"MongoDB connection successful to URI ending with: ...{config.MONGO_URI[-30:] if config.MONGO_URI else 'N/A'}")
        db_instance = mongo_client_instance[config.MONGO_DB_NAME]
        
        # Ensure indexes for MongoDB
        files_collection_instance = db_instance["files"]
        if "files" not in db_instance.list_collection_names() or not files_collection_instance.index_information():
            logger.info("Creating MongoDB indexes for 'files' collection...")
            files_collection_instance.create_index("file_id", unique=True)
            files_collection_instance.create_index("upload_timestamp")
            files_collection_instance.create_index("view_count")
            files_collection_instance.create_index("uploaded_by_user_id")
            logger.info("MongoDB indexes for 'files' created/verified.")
        return mongo_client_instance, db_instance, files_collection_instance
    except Exception as e:
        logger.error(f"MongoDB connection/setup failed: {e}", exc_info=True)
        logger.error(f"Mongo URI used: {config.MONGO_URI}")
        return None, None, None

mongo_client, db, files_collection = init_mongodb()

def generate_file_id():
    return shortuuid.uuid()[:10]

async def get_file_details(message: Message):
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

async def main():
    global app_client # Make sure we're assigning to the global variable
    logger.info("Bot main function started.")
    if not all([config.API_ID, config.API_HASH, config.BOT_TOKEN]):
        logger.critical("Telegram API_ID, API_HASH, or BOT_TOKEN is missing in config. Exiting.")
        return
    if not mongo_client or not db or not files_collection:
        logger.critical("MongoDB is not initialized. Bot cannot start. Exiting.")
        return

    app_client = Client("file_storage_bot_session", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)

    # Add handlers
    @app_client.on_message(filters.command("start") & filters.private)
    async def start_command_handler(client: Client, message: Message):
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

    @app_client.on_message((filters.document | filters.video | filters.photo | filters.audio | filters.voice) & filters.private)
    async def file_handler(client: Client, message: Message):
        user_id = message.from_user.id
        logger.info(f"Received file from user {user_id} (username: @{message.from_user.username}), type: {message.media}")
        
        file_details_extracted = await get_file_details(message)
        if not file_details_extracted:
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
            unique_file_id = generate_file_id()
            while files_collection.count_documents({"file_id": unique_file_id}) > 0: # More robust check
                unique_file_id = generate_file_id()

            file_metadata = {
                "file_id": unique_file_id, "tg_file_id_ref": file_details_extracted["tg_file_id"],
                "original_file_name": file_details_extracted["original_file_name"], "file_type": file_details_extracted["file_type"],
                "mime_type": file_details_extracted["mime_type"], "file_size": file_details_extracted["file_size"],
                "message_id_in_storage": forwarded_message.id, "storage_channel_id": config.STORAGE_CHANNEL_ID,
                "uploaded_by_user_id": user_id, "uploaded_by_user_firstname": message.from_user.first_name,
                "upload_timestamp": datetime.datetime.utcnow(), "view_count": 0}

            files_collection.insert_one(file_metadata)
            logger.info(f"Stored metadata for file: {unique_file_id} from user {user_id}")

            access_link = f"{config.WEB_APP_BASE_URL}/file/{unique_file_id}"
            reply_text = (f"File uploaded successfully!\n\nName: {file_details_extracted['original_file_name']}\n"
                          f"Type: {file_details_extracted['file_type']}\nAccess Link: {access_link}")
            await processing_msg.edit_text(reply_text)

            admin_notify_text = (f"🆕 New File Uploaded!\n👤 By: {message.from_user.first_name} (ID: {user_id})\n"
                                 f"📄 File: {file_details_extracted['original_file_name']}\n🔗 Link: {access_link}\n🆔 File ID: {unique_file_id}")
            if config.ADMIN_USER_ID:
                await client.send_message(chat_id=config.ADMIN_USER_ID, text=admin_notify_text)
        except FloodWait as e:
            logger.warning(f"FloodWait for {e.value}s encountered for user {user_id}. Sleeping...")
            await asyncio.sleep(e.value)
            await file_handler(client, message) # Retry
        except Exception as e:
            logger.error(f"Error in file_handler for user {user_id}: {e}", exc_info=True)
            await processing_msg.edit_text("An error occurred. Please try again later.")

    logger.info("Attempting to start Pyrogram client...")
    try:
        await app_client.start()
        me = await app_client.get_me()
        logger.info(f"Pyrogram client started successfully as @{me.username} (ID: {me.id}). Bot is now listening.")
        await idle() # Keep the bot alive until stopped
        logger.info("Pyrogram client idle() returned, bot might be stopping.")

    except (AuthKeyUnregistered, UserDeactivated, UserDeactivatedBan) as e:
        logger.critical(f"Critical Telegram authentication error: {e}. BOT_TOKEN might be invalid or bot banned. Exiting.", exc_info=True)
    except ConnectionError as e:
         logger.critical(f"Connection error during Pyrogram startup: {e}. Check network or Telegram service. Exiting.", exc_info=True)
    except Exception as e:
        logger.critical(f"An unexpected error occurred during Pyrogram client lifecycle: {e}", exc_info=True)
    # `finally` block for cleanup is handled by the signal handler's call to graceful_shutdown
    # when using asyncio.run with signal handling.


if __name__ == "__main__":
    logger.info(f"Bot script __main__ started. Python version: {sys.version.split()[0]}")
    loop = asyncio.get_event_loop()

    # Add signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM): # SIGINT is Ctrl+C
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(graceful_shutdown(s, loop)))
    
    try:
        logger.info("Running main coroutine...")
        loop.run_until_complete(main())
    except asyncio.CancelledError:
        logger.info("Main coroutine was cancelled (likely during shutdown).")
    except KeyboardInterrupt: # Should be caught by signal handler, but as a fallback
        logger.info("KeyboardInterrupt caught at top level. Initiating shutdown if not already.")
        # Ensure graceful_shutdown is called if loop didn't handle it
        if not loop.is_closed() and not any(isinstance(h, asyncio.TimerHandle) and h._callback.__name__ == 'graceful_shutdown' for h in loop._scheduled): # crude check
             loop.run_until_complete(graceful_shutdown("KeyboardInterrupt_Fallback", loop))
    except Exception as e:
        logger.critical(f"Unhandled exception in __main__ run: {e}", exc_info=True)
    finally:
        if loop.is_running(): # If shutdown didn't stop it
            loop.stop()
        if not loop.is_closed():
            loop.close()
        logger.info("Event loop closed. Script finished.")
