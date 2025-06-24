from bot import Bot
from pyrogram.types import Message
from pyrogram import filters
from config import ADMINS, BOT_STATS_TEXT, USER_REPLY_TEXT
from datetime import datetime
from helper_func import get_readable_time
from database.database import full_userbase

# This custom filter function checks if a message is NOT a command AND NOT a reply.
async def final_fallback_filter(_, __, message: Message):
    is_command = bool(message.text and message.text.startswith("/"))
    is_reply = bool(message.reply_to_message)
    
    # The handler should only run if it's not a command and not a reply.
    return not is_command and not is_reply

# We create a filter instance from our new, smarter function
is_unhandled_message = filters.create(final_fallback_filter)


@Bot.on_message(filters.command('stats') & filters.user(ADMINS))
async def stats(bot: Bot, message: Message):
    now = datetime.now()
    delta = now - bot.uptime
    time = get_readable_time(delta.seconds)
    
    total_users = await full_userbase()
    
    stats_text = (
        "📊 <b>HD Cinema Bot Status</b>\n\n"
        f" » <b>Bot Uptime:</b> <code>{time}</code>\n"
        f" » <b>Active Users:</b> <code>{len(total_users)}</code>"
    )
    
    # Using the BOT_STATS_TEXT variable is optional, but this shows how it could be used.
    # For now, we will use our custom, more detailed message.
    await message.reply(stats_text)


# This now uses our custom filter to prevent any conflicts with other commands.
@Bot.on_message(filters.private & filters.incoming & is_unhandled_message)
async def useless(_,message: Message):
    if USER_REPLY_TEXT:
        # Rebranded and more helpful user reply
        rebranded_reply_text = (
            "👋 Hello! I am the HD Cinema File Share bot.\n\n"
            "I can only provide files through special links. I am not able to chat directly.\n\n"
            "If you need help, please use the buttons from the /start command."
        )
        await message.reply(rebranded_reply_text)
