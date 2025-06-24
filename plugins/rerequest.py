import time
import asyncio
from pyrogram import filters, Client
from pyrogram.types import CallbackQuery
from pyrogram.enums import ParseMode

from bot import Bot
from config import CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, AUTO_DELETE_TIME, FINAL_EXPIRED_MSG, INITIAL_DELETE_MSG
from helper_func import get_messages, handle_file_expiry, get_readable_time
from database.database import log_file_download

@Bot.on_callback_query(filters.regex("^rerequest_"))
async def rerequest_handler(client: Client, query: CallbackQuery):
    """
    Handles the 'Request File Again' button clicks.
    """
    try:
        _, db_message_id_str, expiry_timestamp_str = query.data.split("_")
        db_message_id = int(db_message_id_str)
        expiry_timestamp = int(expiry_timestamp_str)
    except ValueError:
        await query.answer("Invalid button data.", show_alert=True)
        return

    if time.time() > expiry_timestamp:
        await query.answer("This re-request link has expired.", show_alert=True)
        await query.message.edit(FINAL_EXPIRED_MSG, reply_markup=None)
        return

    try:
        messages = await get_messages(client, [db_message_id])
        if not messages:
            await query.answer("Sorry, I couldn't find the original file.", show_alert=True)
            return
        
        msg = messages[0]
        user_id = query.from_user.id
        
        await log_file_download(file_id=msg.id, user_id=user_id)
        
        if bool(CUSTOM_CAPTION) & bool(msg.document):
            caption = CUSTOM_CAPTION.format(previouscaption = "" if not msg.caption else msg.caption.html, filename = msg.document.file_name)
        else:
            caption = "" if not msg.caption else msg.caption.html
        
        reply_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None

        new_sent_message = await msg.copy(
            chat_id=user_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            protect_content=PROTECT_CONTENT
        )

        await query.message.delete()
        
        if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:
            # --- THE FIX IS HERE ---
            # Call the expiry handler for the re-requested file
            timer_message = await new_sent_message.reply_text(
                text=f"⏳ This file will expire in: <b>{get_readable_time(AUTO_DELETE_TIME)}</b>",
                quote=True
            )
            asyncio.create_task(
                handle_file_expiry(client, timer_message, new_sent_message, msg.id, is_rerequest=True)
            )

    except Exception as e:
        await query.answer(f"An error occurred: {e}", show_alert=True)
