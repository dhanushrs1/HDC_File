"""
(©) HD Cinema Bot

This plugin handles miscellaneous commands and fallback messages.
- /stats: A quick command for admins to see bot status.
- A fallback handler for any private message that isn't a command.
"""

from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message

from bot import Bot
from config import ADMINS
from helper_func import get_readable_time
from database.database import get_all_user_ids

@Bot.on_message(filters.command('stats') & filters.user(ADMINS))
async def stats_command(bot: Bot, message: Message):
    """A simple command for admins to get bot uptime and user count."""
    now = datetime.now()
    delta = now - bot.uptime
    uptime_str = get_readable_time(delta.seconds)
    
    total_users = await get_all_user_ids()
    
    stats_text = (
        "📊 <b>HD Cinema Bot Status</b>\n\n"
        f" » <b>Bot Uptime:</b> <code>{uptime_str}</code>\n"
        f" » <b>Active Users:</b> <code>{len(total_users)}</code>"
    )
    
    await message.reply(stats_text)


# This handler is in a lower priority group. It will only run if no other
# handlers in the default group (like /start) process the message first.
@Bot.on_message(filters.private, group=1)
async def unhandled_message_handler(client: Bot, message: Message):
    """
    Handles any incoming private message that isn't a recognized command.
    Politely informs the user that the bot is not for chatting.
    """
    # This prevents the bot from replying to its own messages or edits.
    if message.from_user.id == client.me.id:
        return

    # FIXED: Explicitly ignore any message that is a command.
    # This is the most reliable way to prevent this handler from running
    # after a command like /start has already been processed.
    if message.text and message.text.startswith('/'):
        return

    # Ignore media messages from admins, as they are handled by the linker plugin.
    if message.from_user.id in ADMINS and message.media:
        return

    reply_text = (
        "👋 Hello! I am the HD Cinema File Bot.\n\n"
        "I am not designed for chatting. I can only provide files through special links "
        "or respond to commands like /start and /request.\n\n"
        "If you need help, please use the buttons from the /start command menu."
    )
    await message.reply(reply_text)
