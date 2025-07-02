"""
(©) HD Cinema Bot

This plugin handles the /start command and other essential user commands.
- Processes deep links to serve files.
- Displays a welcome message with a role-based UI.
- Manages the force subscription feature.
- Includes admin commands for user management and broadcasting.
"""

import asyncio
import logging
import random
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, MessageNotModified
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot import Bot
from config import (
    ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON,
    PROTECT_CONTENT, START_PIC, AUTO_DELETE_TIME, JOIN_REQUEST_ENABLE,
    FORCE_SUB_CHANNEL
)
from helper_func import subscribed, decode, get_messages, handle_file_expiry, get_readable_time
from database.database import add_user, delete_user, get_all_user_ids, is_user_present, log_file_download

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- Inspirational Quotes for the Start Message ---
QUOTES = [
    "The secret of getting ahead is getting started.",
    "All our dreams can come true, if we have the courage to pursue them.",
    "The best way to predict the future is to create it.",
    "Your limitation is only your imagination.",
    "Push yourself, because no one else is going to do it for you."
]

# ======================================================================================
#                              *** Core /start Logic ***
# ======================================================================================

@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Bot, message: Message):
    """
    Handles the /start command.
    - If a deep link is present, it serves the corresponding file(s).
    - Otherwise, it shows a welcome message.
    """
    user_id = message.from_user.id
    
    if not await is_user_present(user_id):
        await add_user(user_id)
        logger.info(f"New user added: {user_id}")

    if len(message.command) > 1:
        try:
            base64_string = message.command[1]
            string = await decode(base64_string)
            args = string.split("-")
            
            if len(args) == 3:
                start, end = int(int(args[1]) / abs(client.db_channel.id)), int(int(args[2]) / abs(client.db_channel.id))
                ids = range(start, end + 1)
            elif len(args) == 2:
                ids = [int(int(args[1]) / abs(client.db_channel.id))]
            else:
                await send_welcome_message(client, message)
                return

            await process_file_request(client, message, ids)
        except Exception as e:
            logger.error(f"Error processing deep link for user {user_id}: {e}")
            await message.reply_text("<b>Error:</b> The link seems to be invalid or expired.")
        return

    await send_welcome_message(client, message)

async def send_welcome_message(client: Bot, message: Message):
    """Displays a professional and feature-rich welcome message."""
    user = message.from_user
    
    # Main keyboard for all users
    keyboard = [
        [InlineKeyboardButton("🎬 Request Content", callback_data="request_info")],
        [
            InlineKeyboardButton("❓ Help & About", callback_data="help_info"),
            InlineKeyboardButton("📊 My Stats", callback_data="my_stats")
        ],
        [
            InlineKeyboardButton("💬 Support", url="https://t.me/YourSupportGroup"),
            InlineKeyboardButton("📣 Updates", url="https://t.me/YourUpdatesChannel")
        ]
    ]

    # Add Admin Panel button for admins
    if user.id in ADMINS:
        keyboard.insert(0, [InlineKeyboardButton("👑 Admin Panel", callback_data="admin_main_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Create a more engaging start message
    start_text = (
        f"👋 Hello {user.mention}!\n\n"
        f"{START_MSG}\n\n"
        f"<i>\"{random.choice(QUOTES)}\"</i>"
    )

    if START_PIC:
        await message.reply_photo(photo=START_PIC, caption=start_text, reply_markup=reply_markup, quote=True)
    else:
        await message.reply_text(text=start_text, reply_markup=reply_markup, disable_web_page_preview=True, quote=True)

# ======================================================================================
#                              *** File Serving Logic ***
# ======================================================================================

async def process_file_request(client: Bot, message: Message, ids: list):
    """Fetches and sends the requested files to the user."""
    user_id = message.from_user.id
    temp_msg = await message.reply_text("<b>Please wait, processing your request...</b>", quote=True)
    
    try:
        messages = await get_messages(client, ids)
    except Exception as e:
        logger.error(f"Could not get messages for user {user_id}. Error: {e}")
        await temp_msg.edit("Something went wrong while fetching the files!")
        return
        
    await temp_msg.delete()

    for msg in messages:
        await log_file_download(file_id=msg.id, user_id=user_id)
        
        caption = CUSTOM_CAPTION.format(
            filename=getattr(msg.document or msg.video, 'file_name', ''),
            previous_caption=getattr(msg.caption, 'html', '')
        ) if CUSTOM_CAPTION else getattr(msg.caption, 'html', '')

        try:
            sent_message = await msg.copy(
                chat_id=user_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None,
                protect_content=PROTECT_CONTENT
            )
            if AUTO_DELETE_TIME > 0:
                asyncio.create_task(handle_file_expiry(
                    client,
                    await sent_message.reply_text(f"⏳ This file will expire in: <b>{get_readable_time(AUTO_DELETE_TIME)}</b>", quote=True),
                    sent_message,
                    msg.id
                ))
            await asyncio.sleep(0.5)
        except FloodWait as e:
            logger.warning(f"FloodWait for {e.value}s for user {user_id}. Retrying...")
            await asyncio.sleep(e.value)
            await sent_message.copy(chat_id=user_id, caption=caption, reply_markup=msg.reply_markup, protect_content=PROTECT_CONTENT)
        except (UserIsBlocked, InputUserDeactivated):
            logger.warning(f"User {user_id} has blocked the bot or deleted their account.")
            break
        except Exception as e:
            logger.error(f"Failed to send file {msg.id} to user {user_id}. Error: {e}")

# ======================================================================================
#                              *** Force Subscribe & Admin Commands ***
# ======================================================================================

@Bot.on_message(filters.command('start') & filters.private)
async def not_subscribed_handler(client: Bot, message: Message):
    """Handles users who have not subscribed to the force-sub channel."""
    buttons = []
    if JOIN_REQUEST_ENABLE and client.invitelink:
        invite_link = client.invitelink
        button_text = "➡️ Request to Join Channel"
    elif client.invitelink:
        invite_link = client.invitelink
        button_text = "➡️ Join Channel"
    else:
        return await message.reply_text("The bot is currently under maintenance. Please try again later.")

    buttons.append([InlineKeyboardButton(button_text, url=invite_link)])
    
    if len(message.command) > 1:
        buttons.append([InlineKeyboardButton(text='🔄 Try Again', url=f"https://t.me/{client.username}?start={message.command[1]}")])

    await message.reply(
        text=FORCE_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name or "",
            username=f"@{message.from_user.username}" if message.from_user.username else "N/A",
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True,
        disable_web_page_preview=True
    )

@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def broadcast_command(client: Bot, message: Message):
    """Broadcasts a message to all non-banned users."""
    if not message.reply_to_message:
        return await message.reply_text("<b>Usage:</b> Reply to the message you want to broadcast with <code>/broadcast</code>.")

    pls_wait = await message.reply_text("<i>Broadcasting Message... This will take some time.</i>")
    broadcast_msg = message.reply_to_message
    
    total_users = await get_all_user_ids()
    successful, blocked, deleted, unsuccessful = 0, 0, 0, 0

    for user_id in total_users:
        try:
            await broadcast_msg.copy(user_id)
            successful += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await broadcast_msg.copy(user_id)
            successful += 1
        except (UserIsBlocked, InputUserDeactivated):
            await delete_user(user_id)
            if isinstance(e, UserIsBlocked): blocked += 1
            else: deleted += 1
        except Exception as e:
            unsuccessful += 1
            logger.error(f"Failed to broadcast to {user_id}. Error: {e}")
        
        if (successful + blocked + deleted + unsuccessful) % 100 == 0:
            try:
                await pls_wait.edit(f"<i>Broadcasting...</i>\n\n<b>Sent:</b> {successful}\n<b>Blocked:</b> {blocked}\n<b>Failed:</b> {unsuccessful}")
            except MessageNotModified:
                pass
    
    status = (
        f"<b><u>Broadcast Completed</u></b>\n\n"
        f"<b>Total Users:</b> <code>{len(total_users)}</code>\n"
        f"<b>✅ Successful:</b> <code>{successful}</code>\n"
        f"<b>🚫 Blocked Users:</b> <code>{blocked}</code>\n"
        f"<b>🗑️ Deleted Accounts:</b> <code>{deleted}</code>\n"
        f"<b>❌ Unsuccessful:</b> <code>{unsuccessful}</code>"
    )
    await pls_wait.edit(status)
