"""
(©) HD Cinema Bot

This plugin handles the callback for the 'Request File Again' button.
This button appears after a temporary file, sent to a user, has expired.
"""

import time
import asyncio
import logging
from pyrogram import filters, Client
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified

from bot import Bot
from config import (
    CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT,
    AUTO_DELETE_TIME, FINAL_EXPIRED_MSG
)
from helper_func import get_messages, handle_file_expiry, get_readable_time

# Set up a logger for this module
logger = logging.getLogger(__name__)

@Bot.on_callback_query(filters.regex("^rerequest_"))
async def rerequest_callback_handler(client: Client, query: CallbackQuery):
    """
    Handles the 'Request File Again' button click.
    - Validates the expiry timestamp in the callback data.
    - Re-sends the original file to the user.
    - Starts a new, final expiry timer for the re-sent file.
    """
    try:
        _, db_message_id_str, expiry_timestamp_str = query.data.split("_")
        db_message_id = int(db_message_id_str)
        expiry_timestamp = int(expiry_timestamp_str)
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid re-request callback data: {query.data}. Error: {e}")
        return await query.answer("This button seems to be broken. Please try requesting the content again.", show_alert=True)

    # Check if the re-request link itself has expired
    if time.time() > expiry_timestamp:
        try:
            await query.message.edit(FINAL_EXPIRED_MSG, reply_markup=None)
        except MessageNotModified:
            pass
        return await query.answer("This re-request link has also expired.", show_alert=True)

    try:
        # Fetch the original message from the database channel
        messages = await get_messages(client, [db_message_id])
        if not messages:
            await query.answer("Sorry, I couldn't find the original file. It might have been deleted.", show_alert=True)
            return await query.message.edit("❌ **File Not Found**\nThe original file could not be retrieved from our database.")

        msg = messages[0]
        user_id = query.from_user.id

        # --- Re-send the file ---
        caption = CUSTOM_CAPTION.format(
            filename=getattr(msg.document or msg.video, 'file_name', ''),
            previous_caption=getattr(msg.caption, 'html', '')
        ) if CUSTOM_CAPTION else getattr(msg.caption, 'html', '')
        
        reply_markup = msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None

        new_sent_message = await msg.copy(
            chat_id=user_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            protect_content=PROTECT_CONTENT
        )

        # Delete the old "Request Again" message
        await query.message.delete()
        
        # --- Start a new, final expiry timer ---
        if AUTO_DELETE_TIME > 0:
            timer_message = await new_sent_message.reply_text(
                text=f"⏳ This re-requested file will expire in: <b>{get_readable_time(AUTO_DELETE_TIME)}</b>",
                quote=True
            )
            # The 'is_rerequest=True' flag ensures it performs a final deletion
            asyncio.create_task(
                handle_file_expiry(client, timer_message, new_sent_message, msg.id, is_rerequest=True)
            )

    except Exception as e:
        logger.error(f"Error during re-request process for user {query.from_user.id}: {e}", exc_info=True)
        await query.answer(f"An unexpected error occurred. Please try again.", show_alert=True)
