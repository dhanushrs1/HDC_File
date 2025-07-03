"""
(©) HD Cinema Bot

This plugin handles the /start command with a robust security model.
- FIX: Banned users are now correctly blocked from all bot functions.
- Processes deep links to serve files only to authorized users.
- Manages the force subscription feature.
- Displays a role-based welcome message.
"""

import asyncio
import hashlib
import logging
import random
from urllib.parse import unquote_plus
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
# --- FIX: Import get_user in addition to other functions ---
from database.database import add_user, get_user, delete_user, get_all_user_ids, log_file_download, search_files
from plugins.search import send_search_results

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
#                              *** Core /start Logic with Security Fix ***
# ======================================================================================

@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Bot, message: Message):
    """
    Handles the /start command with a strict ban check.
    1. Checks if the user is banned.
    2. Checks for force subscription.
    3. Processes deep links or shows the welcome menu.
    """
    user = message.from_user
    
    # --- 1. CRITICAL SECURITY FIX: Check for ban first ---
    db_user = await get_user(user.id)
    if db_user and db_user.get("banned", False):
        await message.reply_text(
            "<b>Access Denied</b> ❌\n\nYou are banned from using this bot. Please contact the admin if you believe this is a mistake."
        )
        return

    # --- 2. If not banned, check force subscription ---
    if not await subscribed(client, message):
        return await force_sub_handler(client, message)

    # --- 3. If not banned and subscribed, add the user if they are new ---
    if not db_user:
        await add_user(user.id)
        logger.info(f"New user added: {user.id}")

    # --- 4. Process deep link or show welcome message ---
    if len(message.command) > 1:
        payload = message.command[1]

        # Handle Search Payload from a group deep link
        if payload.startswith("search_"):
            query = unquote_plus(payload.split("_", 1)[1])
            results = await search_files(query, limit=50)
            
            # De-duplication Logic
            unique_results = [doc for i, doc in enumerate(results) if doc.get('file_name') not in {d.get('file_name') for d in results[:i]}]

            if unique_results:
                # --- FIX: Generate query_hash for deep-link search ---
                query_hash = hashlib.md5(query.encode()).hexdigest()[:10]
                await send_search_results(message, query, query_hash, unique_results, page=1)
            else:
                await message.reply_text(f"❌ No results found for '<code>{query}</code>'.")
            return

        # Handle File/Batch Payload
        else:
            try:
                string = await decode(payload)
                args = string.split("-")
                
                if len(args) == 3: # Batch link
                    start, end = int(int(args[1]) / abs(client.db_channel.id)), int(int(args[2]) / abs(client.db_channel.id))
                    ids = range(start, end + 1)
                elif len(args) == 2: # Single file link
                    ids = [int(int(args[1]) / abs(client.db_channel.id))]
                else:
                    return await send_welcome_message(client, message)

                await process_file_request(client, message, ids)
            except Exception as e:
                logger.error(f"Error processing deep link for user {user.id}: {e}")
                await message.reply_text("<b>Error:</b> The link seems to be invalid or expired.")
            return

    # --- 5. No Payload: Show Welcome Message ---
    await send_welcome_message(client, message)


async def send_welcome_message(client: Bot, message: Message):
    """Displays a professional and feature-rich welcome message."""
    user = message.from_user
    
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Disclaimer", callback_data="help_info"),
            InlineKeyboardButton("📊 My Stats", callback_data="my_stats")
        ],
        [
            InlineKeyboardButton("💬 Support", url="https://t.me/YourSupportGroup"),
            InlineKeyboardButton("📣 Updates", url="https://t.me/YourUpdatesChannel")
        ]
    ]

    if user.id in ADMINS:
        keyboard.insert(0, [InlineKeyboardButton("👑 Admin Panel", callback_data="admin_action_refresh")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
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
        return await temp_msg.edit("Something went wrong while fetching the files!")
        
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
                # Inform the user about file expiry and re-request instructions
                expiry_text = (
                    f"⏳ <b>This file will be deleted in: {get_readable_time(AUTO_DELETE_TIME)}</b>\n\n"
                    "You can forward or save this file elsewhere before it expires.\n"
                    "After expiry, you can request this file <b>one more time</b> using the same link."
                )
                expiry_msg = await sent_message.reply_text(expiry_text, quote=True)
                asyncio.create_task(handle_file_expiry(
                    client,
                    expiry_msg,
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

async def force_sub_handler(client: Bot, message: Message):
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
        except (UserIsBlocked, InputUserDeactivated) as e:
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