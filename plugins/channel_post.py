#(©)CodeXBotz

import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from bot import Bot
from config import ADMINS, CHANNEL_ID, DISABLE_CHANNEL_BUTTON
from helper_func import encode
from database.database import add_to_search_index

# A simple in-memory store for indexing sessions
INDEXING_SESSIONS = {}

@Bot.on_message(filters.private & filters.command("start_indexing") & filters.user(ADMINS))
async def start_indexing_command(client: Bot, message: Message):
    user_id = message.from_user.id
    # Reset session stats when starting
    INDEXING_SESSIONS[user_id] = {"new": 0, "duplicate": 0}
    await message.reply_text(
        "✅ <b>Indexing Session Started</b>\n\n"
        "Please forward all media from your database channel to me now. "
        "I will process them in the background.\n\n"
        "Send /stop_indexing when you are finished to see the results."
    )

@Bot.on_message(filters.private & filters.command("stop_indexing") & filters.user(ADMINS))
async def stop_indexing_command(client: Bot, message: Message):
    user_id = message.from_user.id
    if user_id in INDEXING_SESSIONS:
        session = INDEXING_SESSIONS.pop(user_id)
        await message.reply_text(
            f"⏹️ <b>Indexing Session Stopped</b>\n\n"
            f"<b>Total files processed in this session:</b>\n"
            f"  •  New Files Added: <code>{session['new']}</code>\n"
            f"  •  Duplicate Files Updated: <code>{session['duplicate']}</code>"
        )
    else:
        await message.reply_text("You are not currently in an indexing session. Use /start_indexing to begin.")

# This filter handles any media forwarded by an admin.
# It checks if an indexing session is active.
@Bot.on_message(
    filters.private &
    filters.user(ADMINS) &
    (filters.photo | filters.video | filters.document)
)
async def channel_post(client: Client, message: Message):
    user_id = message.from_user.id

    # If user is in an indexing session, just index the file and stop.
    if user_id in INDEXING_SESSIONS:
        status = await add_to_search_index(message)
        if status in ["new", "duplicate"]:
            INDEXING_SESSIONS[user_id][status] += 1
        return # Don't generate links during indexing

    # --- Regular Link Generation Logic (if not indexing) ---
    if not client.config.REDIRECT_URL:
        await message.reply_text("<b>Error:</b> <code>REDIRECT_URL</code> is not set in your config.")
        return
        
    reply_text = await message.reply_text("Processing and adding to database...", quote=True)
    try:
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
        # Also add the file to our search index during normal operation
        await add_to_search_index(post_message)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
        await add_to_search_index(post_message)
    except Exception as e:
        print(e)
        await reply_text.edit_text("❌ <b>Something went Wrong!</b>\nCould not save the file to the database channel.")
        return

    converted_id = post_message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    
    link = f"{client.config.REDIRECT_URL}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]])

    await reply_text.edit(
        f"✅ <b>File Saved & Link Generated!</b>\n\nYour permanent link is ready to be shared.\n\n<code>{link}</code>",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

    if not DISABLE_CHANNEL_BUTTON:
        try:
            await post_message.edit_reply_markup(reply_markup)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await post_message.edit_reply_markup(reply_markup)
        except Exception:
            pass

# This filter handles new media posted directly in the database channel
@Bot.on_message(
    filters.channel &
    filters.incoming &
    filters.chat(CHANNEL_ID) &
    (filters.photo | filters.video | filters.document)
)
async def new_post(client: Client, message: Message):
    # Add new files from the channel to our search index automatically
    await add_to_search_index(message)

    if not client.config.REDIRECT_URL or DISABLE_CHANNEL_BUTTON:
        return

    converted_id = message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    
    link = f"{client.config.REDIRECT_URL}?start={base64_string}"
    
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]])
    try:
        await message.edit_reply_markup(reply_markup)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.edit_reply_markup(reply_markup)
    except Exception:
        pass
