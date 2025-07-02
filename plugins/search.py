"""
(©) HD Cinema Bot

This plugin provides a powerful, command-less, and interactive search experience.
- Listens to all messages in private chat and approved groups.
- Automatically searches for files based on message text.
- In groups, replies with a button to view results in private chat.
- In private chat, displays a clean, paginated list of results.
- Allows users to select a file and receive a secure access link.
"""

import logging
import math
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, UserIsBlocked

from bot import Bot
from config import ADMINS, GROUP_SEARCH_PIC
from database.database import search_files, get_approved_groups
from helper_func import encode, format_bytes

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- Constants ---
RESULTS_PER_PAGE = 5
MIN_QUERY_LENGTH = 3

# ======================================================================================
#                              *** Main Search Handler ***
# ======================================================================================

# Custom filter to check if a message is from an approved group where the bot is an admin
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

@Bot.on_message(filters.text & (filters.private | approved_group_filter) & ~filters.via_bot, group=1)
async def universal_search_handler(client: Bot, message: Message):
    """
    This is the main handler that listens to every message and triggers a search.
    """
    if message.text.startswith('/'):
        return

    query = message.text
    if len(query) < MIN_QUERY_LENGTH:
        return

    results = await search_files(query, limit=50)
    if not results:
        return

    # --- Group Context: Reply with a button to view results in PM ---
    if message.chat.type in ["group", "supergroup"]:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"✅ Found {len(results)} results. Click to view.", callback_data=f"showresults_{query}")]]
        )
        caption = (
            f"👋 Hey {message.from_user.mention}, I found some results for your query!\n\n"
            "Click the button below and I'll send them to you in a private message."
        )
        if GROUP_SEARCH_PIC:
            await message.reply_photo(photo=GROUP_SEARCH_PIC, caption=caption, reply_markup=keyboard, quote=True)
        else:
            await message.reply_text(caption, reply_markup=keyboard, quote=True)
            
    # --- Private Chat Context: Directly show the results ---
    else:
        await send_search_results(message, query, results, page=1)

# ======================================================================================
#                              *** Interactive UI Functions ***
# ======================================================================================

async def send_search_results(source, query, results, page):
    """
    Sends a paginated list of search results to the user in a private message.
    'source' can be a Message or a CallbackQuery.
    """
    total_results = len(results)
    total_pages = math.ceil(total_results / RESULTS_PER_PAGE)
    
    start_index = (page - 1) * RESULTS_PER_PAGE
    end_index = start_index + RESULTS_PER_PAGE
    results_to_show = results[start_index:end_index]

    keyboard = []
    for doc in results_to_show:
        file_name = doc['file_name']
        file_size = doc.get('file_size', 0)
        # Add file size to the button for a better user experience
        button_text = f"📄 {file_name[:35]} ({format_bytes(file_size)})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"selectfile_{doc['_id']}")])

    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"spage_{page-1}_{query}"))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"spage_{page+1}_{query}"))
    if pagination_row:
        keyboard.append(pagination_row)

    text = f"🔎 <b>Search Results for '{query}'</b> (Page {page}/{total_pages})\n\nPlease select the file you want:"
    
    try:
        if isinstance(source, Message):
            await source.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        elif isinstance(source, CallbackQuery):
            await source.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except (UserIsBlocked, UserNotParticipant):
        if isinstance(source, CallbackQuery):
            await source.answer("I can't send you messages. Please start me in private first!", show_alert=True)

# ======================================================================================
#                              *** Callback Handlers ***
# ======================================================================================

@Bot.on_callback_query(filters.regex("^showresults_"))
async def show_results_callback(client: Bot, query: CallbackQuery):
    """Handles the 'Click to view' button from a group."""
    search_query = query.data.split("_", 1)[1]
    
    await query.answer("Searching... I'll send the results to your private chat.", show_alert=False)
    
    results = await search_files(search_query, limit=50)
    if not results:
        try:
            await client.send_message(query.from_user.id, "Sorry, I couldn't find any results for that query anymore.")
        except UserIsBlocked:
            await query.answer("I can't send you messages. Please start me in private first!", show_alert=True)
        return
        
    await send_search_results(query, search_query, results, page=1)

@Bot.on_callback_query(filters.regex("^spage_"))
async def search_page_callback(client: Bot, query: CallbackQuery):
    """Handles the pagination buttons."""
    parts = query.data.split("_", 2)
    page = int(parts[1])
    search_query = parts[2]
    
    await query.answer()
    
    results = await search_files(search_query, limit=50)
    await send_search_results(query, search_query, results, page=page)

@Bot.on_callback_query(filters.regex("^selectfile_"))
async def select_file_callback(client: Bot, query: CallbackQuery):
    """Handles the final file selection and sends the access link."""
    file_id = int(query.data.split("_")[-1])
    
    await query.answer("Generating your secure link...", show_alert=False)
    
    unique_id = file_id * abs(client.db_channel.id)
    encoded_string = await encode(f"get-{unique_id}")
    link = f"{client.config.REDIRECT_URL}?start={encoded_string}"
    
    await query.message.edit_text(
        f"✅ <b>Your Link is Ready!</b>\n\n"
        f"Click the link below to get your file.\n\n"
        f"<code>{link}</code>",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Get File", url=link)]])
    )
