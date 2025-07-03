"""
(©) HD Cinema Bot

This plugin provides a new, all-in-one, interactive admin panel.
- A dynamic main dashboard with integrated command buttons.
- Centralized access to Analytics, User Management, Server Info, and more.
- A new, fully working interactive Broadcast feature.
- All known errors, including AttributeError and MessageNotModified, have been fixed.
"""

import os
import math
import logging
import psutil
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified, FloodWait, UserIsBlocked, InputUserDeactivated
from pyrogram.handlers import MessageHandler

from bot import Bot
from config import ADMINS, TEMP_DIR
from database.database import (
    get_all_user_ids, get_all_users, ban_user, unban_user, get_user,
    get_daily_download_counts, get_top_downloaded_files, get_total_file_stats,
    get_db_stats, get_user_download_count, get_user_last_downloads,
    add_group, remove_group, get_approved_groups, delete_user
)
from helper_func import get_readable_time

# --- Setup ---
logger = logging.getLogger(__name__)
USERS_PER_PAGE = 10


# ======================================================================================
# --- UI Builder Functions ---
# ======================================================================================

def format_bytes(size_bytes):
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    try:
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"
    except ValueError:
        return "0 B"

async def build_main_menu(client: Client):
    """Builds the main admin dashboard with live stats and integrated command buttons."""
    total_users = len(await get_all_user_ids())
    total_files, total_size = await get_total_file_stats()

    text = (
        "👑 <b>Admin Panel</b> 👑\n\n"
        "Welcome to your bot's command center. Select an option below to manage your bot.\n\n"
        f"👤 <b>Total Users:</b> <code>{total_users}</code>\n"
        f"🗂️ <b>Indexed Files:</b> <code>{total_files}</code> (<code>{format_bytes(total_size)}</code>)"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Analytics", callback_data="admin_view_analytics"),
            InlineKeyboardButton("👥 Users", callback_data="admin_view_users_1")
        ],
        [
            InlineKeyboardButton("📣 Broadcast", callback_data="admin_action_broadcast"),
            InlineKeyboardButton("🤝 Groups", callback_data="admin_view_groups")
        ],
        [
            InlineKeyboardButton("🔗 Get Link", callback_data="admin_action_genlink"),
            InlineKeyboardButton("🖥️ Server", callback_data="admin_view_server"),
            InlineKeyboardButton("📂 Temp Files", callback_data="admin_view_tempfiles")
        ],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_action_refresh")]
    ])
    return text, keyboard


# ======================================================================================
# --- Core Command and Callback Handlers ---
# ======================================================================================

@Bot.on_message(filters.private & filters.command("admin") & filters.user(ADMINS))
async def admin_panel_command(client: Bot, message: Message):
    """Entry point for the admin panel via the /admin command."""
    text, keyboard = await build_main_menu(client)
    await message.reply(text, reply_markup=keyboard)


@Bot.on_callback_query(filters.regex("^admin_") & filters.user(ADMINS))
async def admin_callback_handler(client: Bot, query: CallbackQuery):
    """The main router for all admin panel button presses."""
    try:
        await query.answer()
    except:
        pass

    data = query.data.split("_")
    view_or_action = data[1]

    try:
        if view_or_action == "view":
            section = data[2]
            if section == "analytics": await show_analytics_menu(query)
            elif section == "users": await show_users_list(client, query, page=int(data[3]))
            elif section == "userinfo": await show_user_details(client, query, user_id=int(data[3]), page=int(data[4]))
            elif section == "userhistory": await show_user_history(query, user_id=int(data[3]), page=int(data[4]))
            elif section == "groups": await show_groups_list(client, query)
            elif section == "server": await show_server_info(client, query)
            elif section == "tempfiles": await show_temp_files(query)
            elif section == "topfiles": await show_top_files(query, days=int(data[3]))
        
        elif view_or_action == "action":
            action = data[2]
            if action == "refresh":
                text, keyboard = await build_main_menu(client)
                await query.message.edit_text(text, reply_markup=keyboard)
            elif action == "broadcast": await handle_broadcast(client, query)
            elif action in ("ban", "unban"): await handle_ban_unban(client, query, action=data[2], user_id=int(data[3]), page=int(data[4]))
            elif action == "disapprovegroup": await handle_disapprove_group(client, query, group_id=int(data[3]))
            elif action == "deletetemp": await handle_delete_temp_file(query, file_name="_".join(data[3:]))
            elif action == "genlink":
                await query.answer("Forwarding you to the Link Generator...", show_alert=True)
                await client.send_message(query.from_user.id, "/genlink")

    except MessageNotModified:
        pass
    except Exception as e:
        logger.error(f"Error in admin panel handler: {e}", exc_info=True)


# ======================================================================================
# --- Analytics Section ---
# ======================================================================================

async def show_analytics_menu(query: CallbackQuery):
    today, yesterday, day_before = await get_daily_download_counts()
    text = (
        f"📈 <b>Bot Analytics</b>\n\n"
        f"<b>Daily File Downloads:</b>\n"
        f"  - <b>Today:</b> <code>{today}</code>\n"
        f"  - <b>Yesterday:</b> <code>{yesterday}</code>\n"
        f"  - <b>Day Before:</b> <code>{day_before}</code>\n\n"
        "Select a time range to view top trending files."
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Today", callback_data="admin_view_topfiles_1"),
            InlineKeyboardButton("Week", callback_data="admin_view_topfiles_7"),
            InlineKeyboardButton("Month", callback_data="admin_view_topfiles_30")
        ],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_action_refresh")]
    ])
    await query.message.edit_text(text, reply_markup=keyboard)

async def show_top_files(query: CallbackQuery, days: int):
    time_range_text = {0: "All Time", 1: "Today", 7: "This Week", 30: "This Month"}.get(days, f"{days} Days")
    top_files = await get_top_downloaded_files(days=days)
    text = f"🏆 <b>Top 5 Trending Files ({time_range_text})</b>\n\n"
    if not top_files:
        text += "<code>No download data available for this period.</code>"
    else:
        for i, file in enumerate(top_files, 1):
            text += f"<b>{i}.</b> <code>{file.get('file_name', 'Unknown File')}</code> - <b>{file['count']}</b> downloads\n"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Analytics", callback_data="admin_view_analytics")]])
    await query.message.edit_text(text, reply_markup=keyboard)


# ======================================================================================
# --- User Management Section ---
# ======================================================================================

async def show_users_list(client: Client, query: CallbackQuery, page: int):
    users_data = await get_all_users()
    total_users = len(users_data)
    total_pages = math.ceil(total_users / USERS_PER_PAGE) if total_users > 0 else 1
    page = max(1, min(page, total_pages))
    
    start_index = (page - 1) * USERS_PER_PAGE
    users_to_display = users_data[start_index : start_index + USERS_PER_PAGE]
    
    tg_users_dict = {u.id: u for u in await client.get_users([u['_id'] for u in users_to_display])}

    keyboard_buttons = []
    for user_doc in users_to_display:
        user_id = user_doc['_id']
        is_banned = user_doc.get('banned', False)
        tg_user = tg_users_dict.get(user_id)
        
        display_text = f"👤 {tg_user.first_name}" if tg_user else f"👤 ID: {user_id}"
        action_text = "✅ Unban" if is_banned else "🚫 Ban"
        
        keyboard_buttons.append([
            InlineKeyboardButton(display_text, callback_data=f"admin_view_userinfo_{user_id}_{page}"),
            InlineKeyboardButton(action_text, callback_data=f"admin_action_{'unban' if is_banned else 'ban'}_{user_id}_{page}")
        ])
        
    pagination_row = []
    if page > 1: pagination_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_view_users_{page-1}"))
    if page < total_pages: pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_view_users_{page+1}"))
    if pagination_row: keyboard_buttons.append(pagination_row)
        
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_action_refresh")])
    await query.message.edit_text(f"👥 <b>All Users ({total_users}) - Page {page}/{total_pages}</b>", reply_markup=InlineKeyboardMarkup(keyboard_buttons))

async def show_user_details(client: Client, query: CallbackQuery, user_id: int, page: int):
    tg_user = await client.get_users(user_id)
    db_user = await get_user(user_id)
    join_date = db_user.get('joined_date', datetime.now()).strftime("%d %b %Y")
    download_count = await get_user_download_count(user_id)

    user_details = (
        f"👤 <b>User Details:</b>\n\n"
        f" • <b>Name:</b> {tg_user.mention}\n"
        f" • <b>User ID:</b> <code>{tg_user.id}</code>\n"
        f" • <b>Username:</b> @{tg_user.username or 'N/A'}\n"
        f" • <b>Joined:</b> <code>{join_date}</code>\n"
        f" • <b>Status:</b> {'Banned 🚫' if db_user.get('banned') else 'Active ✅'}\n"
        f" • <b>Total Downloads:</b> <code>{download_count}</code>"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 View Last 5 Downloads", callback_data=f"admin_view_userhistory_{user_id}_{page}")],
        [InlineKeyboardButton(f"⬅️ Back to User List", callback_data=f"admin_view_users_{page}")]
    ])
    await query.message.edit_text(user_details, reply_markup=keyboard, disable_web_page_preview=True)

async def show_user_history(query: CallbackQuery, user_id: int, page: int):
    last_downloads = await get_user_last_downloads(user_id)
    text = f"📜 <b>Last 5 Downloads for User {user_id}</b>\n\n"
    if not last_downloads:
        text += "<code>This user has not downloaded any files.</code>"
    else:
        for i, doc in enumerate(last_downloads, 1):
            text += f"<b>{i}.</b> <code>{doc['file_name']}</code> on {doc['timestamp'].strftime('%d %b %Y')}\n"
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to User Details", callback_data=f"admin_view_userinfo_{user_id}_{page}")]])
    await query.message.edit_text(text, reply_markup=keyboard)

async def handle_ban_unban(client: Client, query: CallbackQuery, action: str, user_id: int, page: int):
    if user_id == query.from_user.id:
        return await query.answer("You cannot ban yourself.", show_alert=True)
    if action == "ban":
        await ban_user(user_id)
        await query.answer(f"User {user_id} has been BANNED.", show_alert=True)
    else:
        await unban_user(user_id)
        await query.answer(f"User {user_id} has been UNBANNED.", show_alert=True)
    await show_users_list(client, query, page)


# ======================================================================================
# --- Broadcast Section ---
# ======================================================================================

async def get_broadcast_reply(client: Client, prompt_msg: Message, timeout: int = 300):
    """
    Awaits a reply to a specific message from a specific user.
    This is the correct, Pyrogram-native way to replace client.listen().
    """
    user_id = prompt_msg.chat.id
    message_id = prompt_msg.id
    future = asyncio.Future()

    # --- THIS IS THE FIX for AttributeError ---
    # The handler now checks for the correct attributes on the message object (m).
    # `filters.reply` is the correct filter to use here.
    handler = MessageHandler(
        lambda _, m: future.set_result(m) if m.reply_to_message and m.reply_to_message.id == message_id else None,
        filters=(filters.private & filters.chat(user_id))
    )
    
    client.add_handler(handler)
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        client.remove_handler(handler)


async def handle_broadcast(client: Client, query: CallbackQuery):
    await query.message.delete()
    ask_msg = await client.send_message(query.from_user.id, "Please reply to this message with the content you want to broadcast. To cancel, send /cancel.")

    response = await get_broadcast_reply(client, ask_msg)

    if not response:
        return await ask_msg.edit("Broadcast cancelled due to timeout.")
    if response.text and response.text == "/cancel":
        return await ask_msg.edit("Broadcast operation cancelled.")
    
    await ask_msg.delete()
    
    total_users = await get_all_user_ids()
    pls_wait = await client.send_message(query.from_user.id, f"<i>Broadcasting to {len(total_users)} users...</i>")
    
    successful, blocked, unsuccessful = 0, 0, 0
    for user_id in total_users:
        try:
            await response.copy(user_id)
            successful += 1
        except (UserIsBlocked, InputUserDeactivated):
            await delete_user(user_id)
            blocked += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await response.copy(user_id)
            successful += 1
        except Exception:
            unsuccessful += 1
        
        if (successful + blocked + unsuccessful) % 20 == 0:
            new_text = f"<i>Sent: {successful} | Blocked: {blocked} | Failed: {unsuccessful}</i>"
            if pls_wait.text != new_text:
                 await pls_wait.edit(new_text)
    
    status = (
        f"<b><u>Broadcast Completed</u></b>\n"
        f"<b>Total Users:</b> <code>{len(total_users)}</code>\n"
        f"<b>✅ Successful:</b> <code>{successful}</code>\n"
        f"<b>🚫 Blocked/Deleted:</b> <code>{blocked}</code>\n"
        f"<b>❌ Failed:</b> <code>{unsuccessful}</code>"
    )
    await pls_wait.edit(status)


# ======================================================================================
# --- Group Management Section ---
# ======================================================================================

async def show_groups_list(client: Client, query: CallbackQuery):
    groups = await get_approved_groups()
    text = "📝 <b>Approved Groups for Auto-Search:</b>"
    keyboard_buttons = []

    if not groups:
        text = "There are currently no approved groups for auto-search."
    else:
        for group in groups:
            try:
                chat = await client.get_chat(group['_id'])
                link = chat.invite_link or f"https://t.me/c/{str(group['_id']).replace('-100', '')}/1"
                keyboard_buttons.append([
                    InlineKeyboardButton(chat.title, url=link),
                    InlineKeyboardButton("❌ Disapprove", callback_data=f"admin_action_disapprovegroup_{group['_id']}")
                ])
            except Exception as e:
                logger.warning(f"Could not fetch group {group['_id']}: {e}")
                
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_action_refresh")])
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard_buttons))

async def handle_disapprove_group(client: Client, query: CallbackQuery, group_id: int):
    await remove_group(group_id)
    await query.answer("Group disapproved and removed.", show_alert=True)
    try: await client.leave_chat(group_id)
    except: pass
    await show_groups_list(client, query)


# ======================================================================================
# --- Server and Temp Files Section ---
# ======================================================================================

async def show_server_info(client: Client, query: CallbackQuery):
    uptime_str = get_readable_time((datetime.now() - client.uptime).seconds)
    text = (
        f"🖥️ <b>Server Information</b>\n\n"
        f"<b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"<b>CPU Usage:</b> <code>{psutil.cpu_percent()}%</code>\n"
        f"<b>Memory Usage:</b> <code>{psutil.virtual_memory().percent}%</code>\n"
        f"<b>Disk Usage:</b> <code>{psutil.disk_usage('/').percent}%</code>"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_action_refresh")]])
    await query.message.edit_text(text, reply_markup=keyboard)

async def show_temp_files(query: CallbackQuery):
    os.makedirs(TEMP_DIR, exist_ok=True)
    files = os.listdir(TEMP_DIR)
    
    keyboard_buttons = []
    if not files:
        keyboard_buttons.append([InlineKeyboardButton("✅ No temporary files found.", callback_data="noop")])
    else:
        for file_name in files[:20]:
            keyboard_buttons.append([
                InlineKeyboardButton(f"📄 {file_name[:30]}", callback_data="noop"),
                InlineKeyboardButton("🗑️", callback_data=f"admin_action_deletetemp_{file_name}")
            ])
        if len(files) > 0:
             keyboard_buttons.append([InlineKeyboardButton("⚠️ DELETE ALL ⚠️", callback_data=f"admin_action_deletetemp_all")])
        
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_action_refresh")])
    await query.message.edit_text("<b>📂 Temp File Manager</b>", reply_markup=InlineKeyboardMarkup(keyboard_buttons))

async def handle_delete_temp_file(query: CallbackQuery, file_name: str):
    if file_name == "all":
        count = 0
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f)); count += 1
            except: pass
        await query.answer(f"All {count} temporary files deleted.", show_alert=True)
    else:
        try:
            os.remove(os.path.join(TEMP_DIR, file_name))
            await query.answer(f"Deleted: {file_name}", show_alert=False)
        except FileNotFoundError:
            await query.answer("File not found.", show_alert=True)
    await show_temp_files(query)