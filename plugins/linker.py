"""
(©) HD Cinema Bot

This new, unified plugin handles all file storage and link generation.
- It introduces a single /genlink command.
- Provides an interactive menu for Single or Bulk link generation.
- The Bulk Mode is stateful, allowing admins to forward multiple files
  before generating a single link for the entire batch.
- Intelligently detects and handles duplicate files to prevent re-uploading.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import Bot
from config import ADMINS, DISABLE_CHANNEL_BUTTON, CHANNEL_ID
from helper_func import encode
from database.database import add_file_to_index, find_file_by_unique_id

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- In-memory dictionaries to manage different user states ---
BULK_SESSIONS = {}
# This dictionary is shared with other plugins to manage conversations
CONVERSATION_STATE = {}

# ======================================================================================
#                              *** Link Generation Commands ***
# ======================================================================================

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

@Bot.on_callback_query(filters.regex("^linker_") & filters.user(ADMINS))
async def linker_callback_handler(client: Bot, query: CallbackQuery):
    """Handles button presses from the /genlink menu."""
    user_id = query.from_user.id
    action = query.data.split("_")[1]

    if action == "single":
        CONVERSATION_STATE[user_id] = "awaiting_single_file"
        await query.message.edit_text("➡️ Please forward the media file you want to generate a link for.")
    
    elif action == "bulk":
        sub_action = query.data.split("_")[2]
        if sub_action == "start":
            # For bulk mode, we track both the message IDs and the unique file IDs
            BULK_SESSIONS[user_id] = {'ids': [], 'unique_ids': set()}
            CONVERSATION_STATE[user_id] = "bulk_mode"
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
            session = BULK_SESSIONS.get(user_id)
            if not session or not session['ids']:
                return await query.answer("You haven't added any files to the bulk session yet!", show_alert=True)
            
            files = session['ids']
            BULK_SESSIONS.pop(user_id, None)
            CONVERSATION_STATE.pop(user_id, None)
            files.sort()
            first_msg_id = files[0]
            last_msg_id = files[-1]

            string_to_encode = f"get-{first_msg_id * abs(client.db_channel.id)}-{last_msg_id * abs(client.db_channel.id)}"
            base64_string = await encode(string_to_encode)
            link = f"{client.config.REDIRECT_URL}?start={base64_string}"
            
            await query.message.edit_text(
                f"✅ <b>Batch Link Generated!</b>\n\n"
                f"Total unique files in batch: <code>{len(files)}</code>\n\n"
                f"Your permanent link is ready:\n<code>{link}</code>",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]])
            )

        elif sub_action == "cancel":
            BULK_SESSIONS.pop(user_id, None)
            CONVERSATION_STATE.pop(user_id, None)
            await query.message.edit_text("❌ Bulk link generation has been cancelled.")

# ======================================================================================
#                              *** Main File Handlers ***
# ======================================================================================

@Bot.on_message(
    filters.private &
    filters.user(ADMINS) &
    (filters.document | filters.video | filters.photo | filters.audio),
    group=2 # Lowest priority handler
)
async def general_file_handler(client: Bot, message: Message):
    """
    This is the general file handler. It only runs if no other,
    more specific file handler (like for a conversation) is active.
    """
    user_id = message.from_user.id
    current_state = CONVERSATION_STATE.get(user_id)
    
    media = message.document or message.video or message.photo or message.audio
    if not media: return

    file_unique_id = media.file_unique_id

    # --- Handle Bulk Mode Session ---
    if current_state == "bulk_mode":
        # Check for duplicates WITHIN the current session only
        if file_unique_id in BULK_SESSIONS[user_id]['unique_ids']:
            return await message.reply_text("⚠️ You've already added this exact file to the current batch. Skipped.", quote=True)

        try:
            # Save the file and add it to the session
            post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
            await add_file_to_index(post_message) # This still prevents DB-level duplicates
            BULK_SESSIONS[user_id]['ids'].append(post_message.id)
            BULK_SESSIONS[user_id]['unique_ids'].add(file_unique_id)
            await message.reply_text("👍 Added to batch.", quote=True)
        except Exception as e:
            logger.error(f"Failed to save file during bulk session. Error: {e}", exc_info=True)
        return

    # --- Handle Single File Link Generation ---
    # This runs if state is 'awaiting_single_file' or if there is no active conversation state.
    if current_state == "awaiting_single_file" or current_state is None:
        # Check for duplicates across the ENTIRE database
        existing_file = await find_file_by_unique_id(file_unique_id)
        if existing_file:
            existing_msg_id = existing_file['_id']
            unique_id = existing_msg_id * abs(client.db_channel.id)
            encoded_string = await encode(f"get-{unique_id}")
            link = f"{client.config.REDIRECT_URL}?start={encoded_string}"
            
            CONVERSATION_STATE.pop(user_id, None)
            return await message.reply_text(
                f"⚠️ <b>This file already exists in the database.</b>\n\n"
                f"Here is the existing shareable link:\n<code>{link}</code>",
                quote=True,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]])
            )

        # --- If Not a Duplicate, Proceed with Saving ---
        CONVERSATION_STATE.pop(user_id, None) # Clear state
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
    filters.chat(CHANNEL_ID) &
    (filters.document | filters.video | filters.photo | filters.audio)
)
async def auto_index_channel_post(client: Bot, message: Message):
    """Automatically indexes any new media posted directly in the database channel."""
    status = await add_file_to_index(message)
    logger.info(f"Auto-indexed new post in DB channel. File ID: {message.id}, Status: {status}")
