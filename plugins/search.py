"""
(©) HD Cinema Bot

Interactive, command-less file search experience:
- Searches for files based on message content.
- In groups, replies with a button linking to private chat.
- In private chat, displays paginated results and secure access links.
"""

import logging
import math
from urllib.parse import quote_plus
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, UserIsBlocked

from bot import Bot
from config import ADMINS, GROUP_SEARCH_PIC
from database.database import search_files, get_approved_groups
from helper_func import encode, format_bytes

logger = logging.getLogger(__name__)

# Constants
RESULTS_PER_PAGE = 5
MIN_QUERY_LENGTH = 3

# ============================================================================
# Group approval check (bot must be admin and group must be approved)
# ============================================================================

async def is_approved_admin_group(_, client: Bot, message: Message):
    approved_group_ids = [group['_id'] for group in await get_approved_groups()]
    if message.chat.id not in approved_group_ids:
        return False
    try:
        me = await client.get_chat_member(message.chat.id, client.me.id)
        return me.status == ChatMemberStatus.ADMINISTRATOR
    except Exception:
        return False

approved_group_filter = filters.create(is_approved_admin_group)

# ============================================================================
# Main search handler: works in both group and private
# ============================================================================

@Bot.on_message(filters.text & (filters.private | approved_group_filter) & ~filters.via_bot, group=1)
async def universal_search_handler(client: Bot, message: Message):
    if message.text.startswith('/'):
        return

    query = message.text.strip()
    if len(query) < MIN_QUERY_LENGTH:
        return

    results = await search_files(query, limit=50)
    if not results:
        return

    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        # Group: Reply with a direct deep link to the bot PM
        bot_username = client.me.username
        # URL-encode the search query to handle spaces and special characters
        encoded_query = quote_plus(query)

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                f"✅ Found {len(results)} result(s). Tap to view.",
                url=f"https://t.me/{bot_username}?start=search_{encoded_query}"
            )]]
        )

        caption = (
            f"👋 Hey {message.from_user.mention}, I found some results for your query.\n\n"
            "Tap the button below to view them in your private chat."
        )
        if GROUP_SEARCH_PIC:
            await message.reply_photo(GROUP_SEARCH_PIC, caption=caption, reply_markup=keyboard, quote=True)
        else:
            await message.reply_text(caption, reply_markup=keyboard, quote=True)

    else:
        # Private chat: Show results immediately
        await send_search_results(message, query, results, page=1)

# ============================================================================
# Results Renderer (pagination & buttons)
# ============================================================================

async def send_search_results(source, query, results, page):
    total_results = len(results)
    total_pages = math.ceil(total_results / RESULTS_PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * RESULTS_PER_PAGE
    end_idx = start_idx + RESULTS_PER_PAGE
    display_results = results[start_idx:end_idx]

    keyboard = []
    for doc in display_results:
        name = doc['file_name']
        size = format_bytes(doc.get('file_size', 0))
        keyboard.append([
            InlineKeyboardButton(
                f"📄 {name[:40]} ({size})",
                callback_data=f"selectfile_{doc['_id']}"
            )
        ])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"spage_{page - 1}_{query}"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"spage_{page + 1}_{query}"))
    if nav_row:
        keyboard.append(nav_row)

    text = f"🔎 <b>Results for '{query}'</b> (Page {page}/{total_pages})\n\nPlease select a file below:"

    try:
        if isinstance(source, Message):
            await source.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        elif isinstance(source, CallbackQuery):
            await source.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except (UserIsBlocked, UserNotParticipant):
        if isinstance(source, CallbackQuery):
            await source.answer("I can't message you. Please start me in private first.", show_alert=True)

# ============================================================================
# Callback handler: pagination
# ============================================================================

@Bot.on_callback_query(filters.regex("^spage_"))
async def handle_page_switch(client: Bot, query: CallbackQuery):
    _, page_str, search_term = query.data.split("_", 2)
    page = int(page_str)
    await query.answer()
    results = await search_files(search_term, limit=50)
    await send_search_results(query, search_term, results, page)

# ============================================================================
# Callback handler: file selected
# ============================================================================

@Bot.on_callback_query(filters.regex("^selectfile_"))
async def handle_file_selection(client: Bot, query: CallbackQuery):
    file_id = int(query.data.split("_")[-1])
    await query.answer("Generating your link...", show_alert=False)

    unique_id = file_id * abs(client.db_channel.id)
    encoded = await encode(f"get-{unique_id}")
    link = f"{client.config.REDIRECT_URL}?start={encoded}"

    await query.message.edit_text(
        f"✅ <b>Your Link is Ready!</b>\n\n"
        f"Click below to access your file:\n\n"
        f"<code>{link}</code>",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Get File", url=link)]
        ])
    )
