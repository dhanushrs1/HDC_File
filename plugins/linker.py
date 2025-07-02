"""
(©) HD Cinema Bot

This new, unified plugin handles all file storage and link generation.
- It introduces a single /genlink command.
- Provides an interactive menu for Single or Bulk link generation.
- The Bulk Mode is stateful, allowing admins to forward multiple files
  before generating a single link for the entire batch.
"""

import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import Bot
from config import ADMINS, DISABLE_CHANNEL_BUTTON, CHANNEL_ID
from helper_func import encode
from database.database import add_file_to_index

# Set up a logger for this module
logger = logging.getLogger(__name__)

# In-memory dictionary to manage bulk link generation sessions for each admin
BULK_SESSIONS = {}

# --- Main /genlink Command ---

@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
async def link_generator_command(client: Bot, message: Message):
    """Presents the main menu for link generation."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Single File", callback_data="linker_single")],
        [InlineKeyboardButton("🗂️ Bulk Mode", callback_data="linker_bulk_start")]
    ])
    await message.reply_text(
        "🔗 <b>Link Generator</b>\n\n"
        "How would you like to generate a link?",
        reply_markup=keyboard
    )

# --- Callback Handler for the Menu ---

@Bot.on_callback_query(filters.regex("^linker_") & filters.user(ADMINS))
async def linker_callback_handler(client: Bot, query: CallbackQuery):
    """Handles button presses from the /genlink menu."""
    action = query.data.split("_")[1]
    user_id = query.from_user.id

    if action == "single":
        await query.message.edit_text("➡️ Please forward the media file you want to generate a link for.")
        # The main message handler will now wait for the forwarded file.
    
    elif action == "bulk":
        sub_action = query.data.split("_")[2]
        if sub_action == "start":
            BULK_SESSIONS[user_id] = [] # Initialize a new bulk session
            await query.message.edit_text(
                "🗂️ <b>You are now in Bulk Mode.</b>\n\n"
                "Forward all the media you want to include in the batch. "
                "I will reply to each file to confirm it's been added.\n\n"
                "When you are finished, click the 'Done' button below.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Done & Generate Link", callback_data="linker_bulk_done")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="linker_bulk_cancel")]
                ])
            )
        
        elif sub_action == "done":
            if user_id not in BULK_SESSIONS or not BULK_SESSIONS[user_id]:
                return await query.answer("You haven't added any files to the bulk session yet!", show_alert=True)
            
            files = BULK_SESSIONS[user_id]
            # Ensure files are sorted numerically to get the correct range
            files.sort()
            first_msg_id = files[0]
            last_msg_id = files[-1]

            string_to_encode = f"get-{first_msg_id * abs(client.db_channel.id)}-{last_msg_id * abs(client.db_channel.id)}"
            base64_string = await encode(string_to_encode)
            link = f"{client.config.REDIRECT_URL}?start={base64_string}"
            
            await query.message.edit_text(
                f"✅ <b>Batch Link Generated!</b>\n\n"
                f"Total files in batch: <code>{len(files)}</code>\n\n"
                f"Your permanent link is ready:\n<code>{link}</code>",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]])
            )
            del BULK_SESSIONS[user_id] # Clean up the session

        elif sub_action == "cancel":
            if user_id in BULK_SESSIONS:
                del BULK_SESSIONS[user_id]
            await query.message.edit_text("❌ Bulk link generation has been cancelled.")

# --- Main File Handler for Admins ---

@Bot.on_message(
    filters.private &
    filters.user(ADMINS) &
    (filters.document | filters.video | filters.photo | filters.audio)
)
async def admin_file_handler(client: Bot, message: Message):
    """
    Handles all media sent by an admin.
    - If in bulk mode, adds the file to the session.
    - Otherwise, processes it as a single file.
    """
    user_id = message.from_user.id

    # --- Handle Bulk Mode Session ---
    if user_id in BULK_SESSIONS:
        try:
            post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
            await add_file_to_index(post_message)
            BULK_SESSIONS[user_id].append(post_message.id)
            # FIXED: Replaced .react() with .reply_text() as bots cannot use reactions.
            await message.reply_text("👍 Added to batch.", quote=True)
        except Exception as e:
            logger.error(f"Failed to save file to DB channel during bulk session. Error: {e}", exc_info=True)
            await message.reply_text("❌ Something went wrong while saving this file.")
        return

    # --- Handle Single File Link Generation ---
    if not client.config.REDIRECT_URL:
        return await message.reply_text("<b>Error:</b> <code>REDIRECT_URL</code> is not configured.")
        
    reply_msg = await message.reply_text("<code>Processing...</code>", quote=True)
    
    try:
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
        await add_file_to_index(post_message)
    except Exception as e:
        logger.error(f"Failed to save file to DB channel. Error: {e}", exc_info=True)
        return await reply_msg.edit_text("❌ <b>Something went wrong!</b>\nCould not save the file.")

    unique_id = post_message.id * abs(client.db_channel.id)
    encoded_string = await encode(f"get-{unique_id}")
    link = f"{client.config.REDIRECT_URL}?start={encoded_string}"

    share_button = InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')
    reply_markup = InlineKeyboardMarkup([[share_button]])

    await reply_msg.edit(
        f"✅ <b>File Saved & Link Generated!</b>\n\n"
        f"Your permanent link is ready:\n<code>{link}</code>",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

    if not DISABLE_CHANNEL_BUTTON:
        try:
            await post_message.edit_reply_markup(reply_markup)
        except Exception as e:
            logger.warning(f"Could not edit message in DB channel to add button. Error: {e}")

# --- Auto-Indexing for New Posts in DB Channel ---

@Bot.on_message(
    filters.channel &
    filters.chat(CHANNEL_ID) & # FIXED: Use the ID from config
    (filters.document | filters.video | filters.photo | filters.audio)
)
async def auto_index_channel_post(client: Bot, message: Message):
    """Automatically indexes any new media posted directly in the database channel."""
    status = await add_file_to_index(message)
    logger.info(f"Auto-indexed new post in DB channel. File ID: {message.id}, Status: {status}")
