"""
(©) HD Cinema Bot

This plugin provides a comprehensive and interactive admin panel.
- A dynamic main dashboard with at-a-glance stats.
- Advanced, time-filtered analytics for file trends.
- Full, paginated user management with ban/unban and info lookup.
- Server resource monitoring (CPU, RAM, Disk).
- A complete temporary file manager to clean up the server.
"""

import os
import math
import logging
import psutil
from datetime import datetime
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified

from bot import Bot
from config import ADMINS, TEMP_DIR
from database.database import (
    get_all_user_ids, get_all_users, ban_user, unban_user, get_user,
    get_daily_download_counts, get_top_downloaded_files, get_total_file_stats, 
    get_db_stats, get_user_download_count, get_user_last_downloads
)
from helper_func import get_readable_time

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- Constants ---
USERS_PER_PAGE = 10

# ======================================================================================
#                              *** UI Helper Functions ***
# ======================================================================================

def format_bytes(size_bytes):
    """Converts bytes to a human-readable format (KB, MB, GB)."""
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

async def build_main_menu():
    """Builds the main admin dashboard with live stats."""
    total_users = len(await get_all_user_ids())
    total_files = await get_total_file_stats()
    storage_size, data_size = await get_db_stats()
    
    now = datetime.now().strftime("%I:%M:%S %p")
    
    text = (
        f"👑 <b>Admin Panel</b> 👑\n\n"
        f"Here's a quick overview of your bot's status:\n\n"
        f"👤 <b>Users:</b> <code>{total_users}</code>\n"
        f"🗂️ <b>Files Indexed:</b> <code>{total_files}</code>\n"
        f"💽 <b>Data Size:</b> <code>{format_bytes(data_size)}</code>\n"
        f"💾 <b>Storage Size:</b> <code>{format_bytes(storage_size)}</code>\n\n"
        f"<i>Last Updated: {now}</i>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Analytics", callback_data="admin_analytics_menu"),
            InlineKeyboardButton("👥 Users", callback_data="admin_users_menu")
        ],
        [
            InlineKeyboardButton("🖥️ Server", callback_data="admin_server_menu"),
            InlineKeyboardButton("📂 Temp Files", callback_data="admin_temp_files_menu")
        ],
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_main_menu_refresh")]
    ])
    return text, keyboard

async def build_users_keyboard(client: Client, page: int = 1) -> InlineKeyboardMarkup:
    """Builds the paginated keyboard for the user management list."""
    users_data = await get_all_users()
    total_users = len(users_data)
    total_pages = math.ceil(total_users / USERS_PER_PAGE)
    
    start_index = (page - 1) * USERS_PER_PAGE
    end_index = start_index + USERS_PER_PAGE
    users_to_display = users_data[start_index:end_index]
    
    keyboard = []
    
    user_ids = [user['_id'] for user in users_to_display]
    try:
        tg_users = await client.get_users(user_ids)
        tg_users_dict = {user.id: user for user in tg_users}
    except Exception as e:
        logger.error(f"Failed to fetch user details for pagination: {e}")
        tg_users_dict = {}

    for user_doc in users_to_display:
        user_id = user_doc['_id']
        is_banned = user_doc.get('banned', False)
        tg_user = tg_users_dict.get(user_id)
        
        display_text = f"👤 {tg_user.first_name}" if tg_user else f"👤 ID: {user_id}"
        action_text = "✅ Unban" if is_banned else "🚫 Ban"
        
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"admin_user_{user_id}_{page}"),
            InlineKeyboardButton(action_text, callback_data=f"admin_{'unban' if is_banned else 'ban'}_{user_id}_{page}")
        ])
        
    pagination_row = []
    if page > 1: pagination_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_list_users_{page-1}"))
    if page < total_pages: pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_list_users_{page+1}"))
    if pagination_row: keyboard.append(pagination_row)
        
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_main_menu")])
    return InlineKeyboardMarkup(keyboard)

def build_temp_files_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for the temporary file manager."""
    keyboard = []
    os.makedirs(TEMP_DIR, exist_ok=True)
    files = os.listdir(TEMP_DIR)
    
    if not files:
        keyboard.append([InlineKeyboardButton("✅ No temporary files found.", callback_data="noop")])
    else:
        for file_name in files[:20]: # Show max 20 files to avoid overly large keyboards
            keyboard.append([
                InlineKeyboardButton(f"📄 {file_name[:30]}", callback_data="noop"),
                InlineKeyboardButton("🗑️ Delete", callback_data=f"admin_temp_delete_{file_name}")
            ])
        keyboard.append([InlineKeyboardButton("⚠️ DELETE ALL FILES ⚠️", callback_data="admin_temp_delete_all")])
        
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_main_menu")])
    return InlineKeyboardMarkup(keyboard)

# ======================================================================================
#                              *** Command & Callback Handlers ***
# ======================================================================================

@Bot.on_message(filters.private & filters.command("admin") & filters.user(ADMINS))
async def admin_panel_command(client: Bot, message: Message):
    """Entry point for the admin panel via the /admin command."""
    text, keyboard = await build_main_menu()
    await message.reply(text, reply_markup=keyboard)

@Bot.on_callback_query(filters.regex("^admin_") & filters.user(ADMINS))
async def admin_callback_handler(client: Bot, query: CallbackQuery):
    """Handles all button presses within the admin panel."""
    try:
        parts = query.data.split("_")
        action = parts[1]
    except IndexError:
        return await query.answer("Invalid callback data.", show_alert=True)

    try:
        # --- Main Menu ---
        if action == "main":
            is_refresh = "refresh" in query.data
            await query.answer("Refreshing stats...", show_alert=False) if is_refresh else await query.answer()
            text, keyboard = await build_main_menu()
            await query.message.edit_text(text, reply_markup=keyboard)

        # --- Analytics Menu ---
        elif action == "analytics":
            await query.answer()
            today, yesterday, day_before = await get_daily_download_counts()
            text = (
                f"📈 <b>Bot Analytics</b>\n\n"
                f"<b>File Requests (Downloads):</b>\n"
                f"  - <b>Today:</b> <code>{today}</code>\n"
                f"  - <b>Yesterday:</b> <code>{yesterday}</code>\n"
                f"  - <b>Day Before:</b> <code>{day_before}</code>\n\n"
                "Select a time range to view top trending files."
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Today", callback_data="admin_top_1"),
                    InlineKeyboardButton("Week", callback_data="admin_top_7"),
                    InlineKeyboardButton("Month", callback_data="admin_top_30"),
                    InlineKeyboardButton("All Time", callback_data="admin_top_0")
                ],
                [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_main_menu")]
            ])
            await query.message.edit_text(text, reply_markup=keyboard)

        # --- Top Files Handler ---
        elif action == "top":
            days = int(parts[2])
            await query.answer("Fetching top files...", show_alert=False)
            time_range_text = {0: "All Time", 1: "Today", 7: "This Week", 30: "This Month"}.get(days, f"{days} Days")
            top_files = await get_top_downloaded_files(days=days)
            text = f"🏆 <b>Top 5 Trending Files ({time_range_text})</b>\n\n"
            if not top_files:
                text += "<code>No download data available for this period.</code>"
            else:
                for i, file in enumerate(top_files, 1):
                    text += f"<b>{i}.</b> <code>{file.get('file_name', 'Unknown File')}</code> - <b>{file['count']}</b> requests\n"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Analytics", callback_data="admin_analytics_menu")]])
            await query.message.edit_text(text, reply_markup=keyboard)

        # --- Server Info Menu ---
        elif action == "server":
            await query.answer()
            uptime_str = get_readable_time((datetime.now() - client.uptime).seconds)
            text = (
                f"🖥️ <b>Server Information</b>\n\n"
                f"<b>Uptime:</b> <code>{uptime_str}</code>\n"
                f"<b>CPU Usage:</b> <code>{psutil.cpu_percent()}%</code>\n"
                f"<b>Memory Usage:</b> <code>{psutil.virtual_memory().percent}%</code>\n"
                f"<b>Disk Usage:</b> <code>{psutil.disk_usage('/').percent}%</code>"
            )
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_main_menu")]])
            await query.message.edit_text(text, reply_markup=keyboard)

        # --- User Management ---
        elif action == "users":
            await query.answer()
            await query.message.edit_text("👥 <b>User Management</b>", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 List All Users", callback_data="admin_list_users_1")],
                [InlineKeyboardButton("⬅️ Back", callback_data="admin_main_menu")]
            ]))
            
        elif action == "list":
            page = int(parts[-1])
            await query.answer("Fetching user details...", show_alert=False)
            keyboard = await build_users_keyboard(client, page)
            total_users_count = len(await get_all_users())
            await query.message.edit_text(f"👥 <b>All Users ({total_users_count}) - Page {page}</b>", reply_markup=keyboard)
        
        elif action == "user":
            user_id, page = int(parts[2]), int(parts[3])
            tg_user = await client.get_users(user_id)
            db_user = await get_user(user_id)
            status = "Banned 🚫" if db_user and db_user.get('banned', False) else "Active ✅"
            join_date = db_user.get('joined_date')
            join_date_str = join_date.strftime("%d %b %Y") if join_date else "N/A"
            download_count = await get_user_download_count(user_id)
            
            user_details = (
                f"👤 <b>User Details:</b>\n\n"
                f" • <b>Name:</b> {tg_user.mention}\n"
                f" • <b>User ID:</b> <code>{tg_user.id}</code>\n"
                f" • <b>Username:</b> @{tg_user.username or 'N/A'}\n"
                f" • <b>Joined:</b> <code>{join_date_str}</code>\n"
                f" • <b>Bot Status:</b> {status}\n"
                f" • <b>Total Requests:</b> <code>{download_count}</code>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 View Last 5 Downloads", callback_data=f"admin_history_{user_id}_{page}")],
                [InlineKeyboardButton(f"⬅️ Back to Page {page}", callback_data=f"admin_list_users_{page}")]
            ])
            await query.message.edit_text(user_details, reply_markup=keyboard, disable_web_page_preview=True)

        elif action == "history":
            user_id, page = int(parts[2]), int(parts[3])
            last_downloads = await get_user_last_downloads(user_id)
            text = f"📜 <b>Last 5 Downloads for User {user_id}</b>\n\n"
            if not last_downloads:
                text += "<code>This user has not downloaded any files yet.</code>"
            else:
                for i, doc in enumerate(last_downloads, 1):
                    timestamp = doc['timestamp'].strftime("%d %b %Y")
                    text += f"<b>{i}.</b> <code>{doc['file_name']}</code>\n     <i>(On {timestamp})</i>\n"
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"⬅️ Back to User Details", callback_data=f"admin_user_{user_id}_{page}")]])
            await query.message.edit_text(text, reply_markup=keyboard)

        elif action in ["ban", "unban"]:
            user_id, page = int(parts[2]), int(parts[3])
            if user_id == query.from_user.id:
                return await query.answer("You cannot ban yourself.", show_alert=True)
            if action == "ban":
                await ban_user(user_id)
                await query.answer(f"User {user_id} has been BANNED.", show_alert=True)
            else:
                await unban_user(user_id)
                await query.answer(f"User {user_id} has been UNBANNED.", show_alert=True)
            keyboard = await build_users_keyboard(client, page)
            await query.message.edit_reply_markup(reply_markup=keyboard)
        
        # --- Temp File Manager ---
        elif action == "temp":
            sub_action = parts[2] if len(parts) > 2 else "menu"
            if sub_action == "files":
                os.makedirs(TEMP_DIR, exist_ok=True)
                await query.message.edit_text(f"<b>📂 Temp File Manager</b>", reply_markup=build_temp_files_keyboard())
            
            elif sub_action == "delete":
                file_name_to_delete = "_".join(parts[3:])
                if file_name_to_delete == "all":
                    count = 0
                    for file_name in os.listdir(TEMP_DIR):
                        os.remove(os.path.join(TEMP_DIR, file_name))
                        count += 1
                    await query.answer(f"All {count} temporary files have been deleted.", show_alert=True)
                else:
                    file_path = os.path.join(TEMP_DIR, file_name_to_delete)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        await query.answer(f"Deleted: {file_name_to_delete}", show_alert=True)
                    else:
                        await query.answer("File not found.", show_alert=True)
                
                await query.message.edit_text(f"<b>📂 Temp File Manager</b>", reply_markup=build_temp_files_keyboard())
            else: # Go to menu
                await query.answer()
                await query.message.edit_text("<b>📂 Temp File Manager</b>\n\nThis tool allows you to clean up temporary files created by the bot.", reply_markup=build_temp_files_keyboard())

    except MessageNotModified:
        await query.answer("No changes to show.")
    except Exception as e:
        logger.error(f"Error in admin panel: {e}", exc_info=True)
        await query.answer("An error occurred. Please check the logs.", show_alert=True)
