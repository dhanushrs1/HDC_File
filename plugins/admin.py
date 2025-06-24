import asyncio
import os
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserIsBlocked, PeerIdInvalid, MessageNotModified
from datetime import datetime
import math

from bot import Bot
from config import ADMINS
from database.database import (
    full_userbase, get_all_users_data, ban_user, unban_user,
    get_daily_download_counts, get_top_downloaded_files, get_user
)
from helper_func import get_readable_time

USERS_PER_PAGE = 10
TEMP_DIR = "temp_downloads/"

# --- Helper function for text-based bar chart ---
def create_bar_chart(data):
    max_val = max(data.values()) if data else 0
    if max_val == 0:
        return "\n<code>No download data yet.</code>"
    chart = ""
    for label, value in data.items():
        percent = (value / max_val) * 15
        bar = "█" * int(percent)
        padding = " " * (15 - len(bar))
        chart += f"<code>{label.ljust(11)}:</code> <code>[{bar}{padding}]</code> <code>{value}</code>\n"
    return chart

# --- Helper function for user list keyboard ---
async def build_users_keyboard(client: Client, page=1):
    users_data = await get_all_users_data()
    start_index = (page - 1) * USERS_PER_PAGE
    end_index = start_index + USERS_PER_PAGE
    users_to_display = users_data[start_index:end_index]
    keyboard = []
    user_ids = [user['_id'] for user in users_to_display]
    try:
        tg_users = await client.get_users(user_ids)
        tg_users_dict = {user.id: user for user in tg_users}
    except Exception:
        tg_users_dict = {}
    for user_doc in users_to_display:
        user_id = user_doc['_id']
        is_banned = user_doc.get('banned', False)
        tg_user = tg_users_dict.get(user_id)
        if tg_user:
            username = f"(@{tg_user.username})" if tg_user.username else "(No username)"
            display_text = f"👤 {tg_user.first_name} {username}"
        else:
            display_text = f"👤 {user_id} (Unavailable)"
        
        user_button = InlineKeyboardButton(display_text, callback_data=f"admin_user_info_{user_id}_{page}")
        action_button = InlineKeyboardButton("✅ Unban", callback_data=f"admin_unban_{user_id}_{page}") if is_banned else InlineKeyboardButton("🚫 Ban", callback_data=f"admin_ban_{user_id}_{page}")
        keyboard.append([user_button, action_button])
        
    total_pages = math.ceil(len(users_data) / USERS_PER_PAGE)
    pagination_row = []
    if page > 1: pagination_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_list_users_{page-1}"))
    if page < total_pages: pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_list_users_{page+1}"))
    if pagination_row: keyboard.append(pagination_row)
    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_main_menu")])
    return InlineKeyboardMarkup(keyboard)

# --- Helper for Temp File Manager ---
def build_temp_files_keyboard():
    keyboard = []
    os.makedirs(TEMP_DIR, exist_ok=True)
    files = os.listdir(TEMP_DIR)
    if not files:
        keyboard.append([InlineKeyboardButton("No temporary files found.", callback_data="noop")])
    else:
        for file_name in files:
            keyboard.append([InlineKeyboardButton(f"📄 {file_name}", callback_data="noop"), InlineKeyboardButton("🗑️ Delete", callback_data=f"admin_temp_delete_{file_name}")])
        keyboard.append([InlineKeyboardButton("⚠️ DELETE ALL ⚠️", callback_data="admin_temp_delete_all")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_main_menu")])
    return InlineKeyboardMarkup(keyboard)

# --- Main Admin Panel Command ---
@Bot.on_message(filters.private & filters.command("admin") & filters.user(ADMINS))
async def admin_panel(client: Bot, message: Message):
    main_menu_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("📈 Analytics", callback_data="admin_analytics_menu")],
        [InlineKeyboardButton("👥 User Management", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📂 Temp File Manager", callback_data="admin_temp_files_menu")]
    ])
    await message.reply("👋 Welcome to the Admin Panel.", reply_markup=main_menu_markup)

# --- Main Callback Handler for All Admin Buttons ---
@Bot.on_callback_query(filters.regex("^admin_"))
async def admin_callback_handler(client: Bot, query: CallbackQuery):
    data = query.data
    
    # --- FIX: Use a robust way to parse callback data ---
    parts = data.split("_")
    action = parts[1] if len(parts) > 1 else None

    if data == "admin_main_menu":
        # ... (logic is correct and unchanged)
        main_menu_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton("📈 Analytics", callback_data="admin_analytics_menu")],
            [InlineKeyboardButton("👥 User Management", callback_data="admin_users_menu")],
            [InlineKeyboardButton("📂 Temp File Manager", callback_data="admin_temp_files_menu")]
        ])
        try:
            await query.message.edit_text("👋 Welcome to the Admin Panel.", reply_markup=main_menu_markup)
        except MessageNotModified:
            pass

    elif action == "stats":
        # ... (logic is correct and unchanged)
        total_users = await full_userbase()
        now = datetime.now()
        delta = now - client.uptime
        uptime_str = get_readable_time(delta.seconds)
        stats_text = (f"📊 <b>Bot Statistics</b>\n\n<b>Active Users:</b> <code>{len(total_users)}</code> (Not Banned)\n<b>Bot Uptime:</b> <code>{uptime_str}</code>")
        back_button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_main_menu")]])
        await query.message.edit_text(stats_text, reply_markup=back_button_markup)
        
    elif action == "users":
        # ... (logic for user management main menu is correct and unchanged)
        users_menu_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 List All Users", callback_data="admin_list_users_1")],
            [InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_main_menu")]])
        await query.message.edit_text("👥 <b>User Management</b>", reply_markup=users_menu_markup)
        
    elif action == "list":
        # ... (logic for listing users is correct and unchanged)
        page = int(parts[-1])
        await query.answer("Fetching user details...", show_alert=False)
        keyboard = await build_users_keyboard(client, page)
        total_users_count = len(await get_all_users_data())
        await query.message.edit_text(f"👥 <b>All Users ({total_users_count}) - Page {page}</b>", reply_markup=keyboard)
    
    elif action == "user":
        # ... (logic for user info is correct and unchanged)
        user_id = int(parts[3])
        page = int(parts[4])
        try:
            tg_user = await client.get_users(user_id)
            db_user = await get_user(user_id)
            status = "Banned 🚫" if db_user and db_user.get('banned', False) else "Active ✅"
            is_admin = "Yes 👑" if user_id in ADMINS else "No"
            user_details_text = (f"👤 <b>User Details:</b>\n\n • <b>Name:</b> {tg_user.mention}\n • <b>User ID:</b> <code>{tg_user.id}</code>\n • <b>Username:</b> @{tg_user.username if tg_user.username else 'N/A'}\n • <b>Bot Status:</b> {status}\n • <b>Is Admin:</b> {is_admin}")
            back_button = InlineKeyboardMarkup([[InlineKeyboardButton(f"⬅️ Back to User List (Page {page})", callback_data=f"admin_list_users_{page}")]])
            await query.message.edit_text(user_details_text, reply_markup=back_button, disable_web_page_preview=True)
        except Exception as e:
            await query.answer(f"Could not fetch user details. Error: {e}", show_alert=True)
            
    elif action == "ban" or action == "unban":
        # --- FIX: Correctly parse and handle ban/unban actions ---
        user_id = int(parts[2])
        page = int(parts[3])
        if user_id == query.from_user.id:
            await query.answer("You cannot ban yourself.", show_alert=True)
            return
        if action == "ban":
            await ban_user(user_id)
            await query.answer(f"User {user_id} has been BANNED.", show_alert=True)
        else: # action == "unban"
            await unban_user(user_id)
            await query.answer(f"User {user_id} has been UNBANNED.", show_alert=True)
        keyboard = await build_users_keyboard(client, page)
        try:
            await query.message.edit_reply_markup(reply_markup=keyboard)
        except MessageNotModified:
            await query.answer()

    elif action == "analytics":
        # ... (logic for analytics menu is correct and unchanged)
        if len(parts) > 2 and parts[2] == "daily":
            await query.answer("Calculating daily stats...", show_alert=False)
            today, yesterday, day_before = await get_daily_download_counts()
            chart_data = {"Today": today, "Yesterday": yesterday, "Day Before": day_before}
            chart = create_bar_chart(chart_data)
            text = f"<b>📅 Daily File Receives</b>\n\n{chart}"
            back_button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Analytics", callback_data="admin_analytics_menu")]])
            await query.message.edit_text(text, reply_markup=back_button_markup)
        elif len(parts) > 2 and parts[2] == "top":
            await query.answer("Calculating top files...", show_alert=False)
            top_files = await get_top_downloaded_files(limit=5)
            text = "🏆 <b>Top 5 Most Received Files</b>\n\n"
            if not top_files:
                text += "<code>No download data yet.</code>"
            else:
                file_ids = [file['_id'] for file in top_files]
                try:
                    messages = await client.get_messages(chat_id=client.db_channel.id, message_ids=file_ids)
                    message_dict = {msg.id: msg for msg in messages}
                    for i, file in enumerate(top_files):
                        msg = message_dict.get(file['_id'])
                        filename = getattr(msg.document, 'file_name', getattr(msg.video, 'file_name', 'Unknown File'))
                        text += f"<b>{i+1}.</b> <code>{filename}</code> - <b>{file['count']}</b> receives\n"
                except Exception as e:
                    text += f"<code>Could not fetch file details. Error: {e}</code>"
            back_button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Analytics", callback_data="admin_analytics_menu")]])
            await query.message.edit_text(text, reply_markup=back_button_markup)
        else:
            analytics_menu_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Daily Stats", callback_data="admin_analytics_daily")],
                [InlineKeyboardButton("🏆 Top Files", callback_data="admin_analytics_top_files")],
                [InlineKeyboardButton("⬅️ Back to Admin Menu", callback_data="admin_main_menu")]])
            await query.message.edit_text("📈 <b>Analytics Menu</b>", reply_markup=analytics_menu_markup)

    elif action == "temp":
        # ... (logic for temp file manager is correct and unchanged)
        if len(parts) > 2 and parts[2] == "files":
            os.makedirs(TEMP_DIR, exist_ok=True)
            total_files = len(os.listdir(TEMP_DIR))
            await query.message.edit_text(f"<b>📂 Temp File Manager</b>\n\nFound <code>{total_files}</code> files.", reply_markup=build_temp_files_keyboard())
        elif len(parts) > 2 and parts[2] == "delete":
            if data == "admin_temp_delete_all":
                for file_name in os.listdir(TEMP_DIR): os.remove(os.path.join(TEMP_DIR, file_name))
                await query.answer("All temporary files have been deleted.", show_alert=True)
            else:
                file_name_to_delete = data.replace("admin_temp_delete_", "")
                file_path = os.path.join(TEMP_DIR, file_name_to_delete)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    await query.answer(f"Deleted: {file_name_to_delete}", show_alert=True)
                else:
                    await query.answer("File not found.", show_alert=True)
            total_files = len(os.listdir(TEMP_DIR))
            await query.message.edit_text(f"<b>📂 Temp File Manager</b>\n\nFound <code>{total_files}</code> files.", reply_markup=build_temp_files_keyboard())
            
    elif action == "noop":
        await query.answer()
    else:
        await query.answer()
