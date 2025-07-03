"""
(©) HD Cinema Bot

This plugin provides an intelligent, command-less file search experience.
- NEW: Automatically de-duplicates search results, showing only one file for each name.
- NEW: Adds a new configuration option (ADMIN_SEARCH_IN_PM) to enable or disable searching for admins in private messages.
- FIX: Retains the caching system to prevent the ButtonDataInvalid error for long search queries.
"""

import logging
import math
import time
import hashlib
from urllib.parse import quote_plus
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, UserIsBlocked

from bot import Bot
# --- MODIFICATION: Import new config variable ---
from config import ADMINS, GROUP_SEARCH_PIC
import config as config_module  # <-- Add this line
from database.database import search_files, get_approved_groups, get_setting
from helper_func import encode, format_bytes

logger = logging.getLogger(__name__)

# --- Constants ---
RESULTS_PER_PAGE = 5
MIN_QUERY_LENGTH = 3

# --- In-memory cache to store search results and solve the ButtonDataInvalid error ---
SEARCH_RESULTS_CACHE = {}

# ============================================================================
# Group approval check (bot must be admin and group must be approved)
# ============================================================================

async def is_approved_admin_group(_, client: Bot, message: Message):
    """Checks if the message is from a group where the bot is an approved admin."""
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

    # Only block admin file search in PM if disabled, but do not handle any user search prompt logic here
    if (
        not await get_setting("ADMIN_SEARCH_IN_PM", default=True)
        and message.from_user.id in ADMINS
        and message.chat.type == ChatType.PRIVATE
    ):
        return await message.reply_text("ℹ️ Admin search in PM is currently disabled by the bot owner.")

    query = message.text.strip()
    if len(query) < MIN_QUERY_LENGTH:
        return

    # Generate a short, unique hash for the search query to use as a cache key
    query_hash = hashlib.md5(query.encode()).hexdigest()[:10]
    
    # Check cache first to avoid unnecessary database calls
    cached = SEARCH_RESULTS_CACHE.get(query_hash)
    if cached and (time.time() - cached['timestamp'] < 3600): # 1 hour cache
        results = cached['results']
    else:
        db_results = await search_files(query, limit=100) # Fetch more to account for duplicates
        
        # --- NEW: De-duplication Logic ---
        # This ensures that if multiple files have the same name, only the first one is shown.
        unique_results = []
        seen_filenames = set()
        for doc in db_results:
            filename = doc.get('file_name')
            if filename and filename not in seen_filenames:
                unique_results.append(doc)
                seen_filenames.add(filename)
        
        results = unique_results
        if results:
            SEARCH_RESULTS_CACHE[query_hash] = {"results": results, "timestamp": time.time()}

    if not results:
        return # Don't reply if no results are found

    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        bot_username = client.me.username
        encoded_query = quote_plus(query) # URL-encode for safety in deep links

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                f"✅ Found {len(results)} unique result(s). Tap to view.",
                url=f"https://t.me/{bot_username}?start=search_{encoded_query}"
            )]]
        )
        caption = (
            f"👋 Hey {message.from_user.mention}, I found results for your query.\n\n"
            "Tap the button below to view them privately."
        )
        if GROUP_SEARCH_PIC:
            await message.reply_photo(GROUP_SEARCH_PIC, caption=caption, reply_markup=keyboard, quote=True)
        else:
            await message.reply_text(caption, reply_markup=keyboard, quote=True)

    else:
        # Private chat: Show results immediately, passing the query hash
        await send_search_results(message, query, query_hash, results, page=1)

# ============================================================================
# Results Renderer (pagination & buttons)
# ============================================================================

async def send_search_results(source, query: str, query_hash: str, results: list, page: int):
    total_results = len(results)
    total_pages = math.ceil(total_results / RESULTS_PER_PAGE) if total_results > 0 else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * RESULTS_PER_PAGE
    display_results = results[start_idx : start_idx + RESULTS_PER_PAGE]

    keyboard = []
    for doc in display_results:
        name = doc['file_name']
        size = format_bytes(doc.get('file_size', 0))
        keyboard.append([
            InlineKeyboardButton(f"📄 {name[:40]} ({size})", callback_data=f"selectfile_{doc['_id']}")
        ])

    # Use the short query_hash in the callback data to prevent errors
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"spage_{page - 1}_{query_hash}"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"spage_{page + 1}_{query_hash}"))
    if nav_row:
        keyboard.append(nav_row)

    text = f"🔎 <b>Results for '<code>{query}</code>'</b> (Page {page}/{total_pages})\n\nPlease select a file below:"

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
    _, page_str, query_hash = query.data.split("_", 2)
    page = int(page_str)
    
    cached_data = SEARCH_RESULTS_CACHE.get(query_hash)
    if not cached_data:
        return await query.answer("This search has expired. Please search again.", show_alert=True)
    
    await query.answer()
    results = cached_data['results']
    original_query_text = "your search" # We don't need the original text for pagination
    await send_search_results(query, original_query_text, query_hash, results, page)

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