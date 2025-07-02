"""
(©) HD Cinema Bot

This new, advanced plugin handles all group management features.
- Proactively notifies the owner when the bot is added to a new group.
- Provides an interactive UI for approving or disapproving groups.
- A new /groups command for a UI-based management panel.
"""

import logging
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import Bot
from config import OWNER_ID
from database.database import add_group, remove_group, get_approved_groups

# Set up a logger for this module
logger = logging.getLogger(__name__)

# ======================================================================================
#                              *** Proactive Group Detection ***
# ======================================================================================

@Bot.on_chat_member_updated(filters.group, group=2)
async def on_bot_added_to_group(client: Bot, update: Message):
    """
    Notifies the owner when the bot is added to a new group,
    allowing for quick approval or disapproval.
    """
    if not update.new_chat_member or update.new_chat_member.user.id != client.me.id:
        return # Ignore if the update is not about the bot being added.

    chat = update.chat
    
    # Get the bot's own status in the group
    try:
        me = await chat.get_member(client.me.id)
        is_admin = me.status == ChatMemberStatus.ADMINISTRATOR
    except Exception:
        # If the bot can't get its own status (e.g., in a restricted group), assume it's not admin
        is_admin = False
    
    text = (
        f"🔔 <b>New Group Alert</b> 🔔\n\n"
        f"I have been added to a new group:\n\n"
        f"<b>Name:</b> {chat.title}\n"
        f"<b>ID:</b> <code>{chat.id}</code>\n"
        f"<b>Members:</b> {chat.members_count}\n\n"
        f"<b>My Status:</b> {'Admin' if is_admin else 'Member'}\n"
        f"<i>(I need admin rights to delete my own messages for the auto-search feature)</i>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve Group", callback_data=f"grp_approve_{chat.id}"),
            InlineKeyboardButton("❌ Disapprove & Leave", callback_data=f"grp_disapprove_{chat.id}")
        ]
    ])
    
    try:
        await client.send_message(OWNER_ID, text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Could not send new group alert to owner. Error: {e}")

# ======================================================================================
#                              *** Interactive Group Management ***
# ======================================================================================

@Bot.on_message(filters.private & filters.command("groups") & filters.user(OWNER_ID))
async def list_groups_command(client: Bot, message: Message):
    """Displays an interactive list of all approved groups."""
    groups = await get_approved_groups()
    if not groups:
        return await message.reply_text("There are no approved groups yet.")
    
    keyboard = []
    for group in groups:
        group_id = group['_id']
        group_name = group.get('name', 'Unknown Name')
        keyboard.append([
            InlineKeyboardButton(f"G: {group_name}", callback_data="noop"),
            InlineKeyboardButton("❌ Disapprove & Leave", callback_data=f"grp_disapprove_{group_id}")
        ])
        
    await message.reply_text(
        "📝 <b>Approved Groups for Auto-Search:</b>\n\n"
        "Here is the list of all groups where the auto-search feature is currently active. "
        "You can disapprove a group at any time.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@Bot.on_callback_query(filters.regex("^grp_") & filters.user(OWNER_ID))
async def group_management_callback(client: Bot, query: CallbackQuery):
    """Handles the approve/disapprove buttons."""
    action = query.data.split("_")[1]
    group_id = int(query.data.split("_")[2])
    
    try:
        chat = await client.get_chat(group_id)
        group_name = chat.title
    except Exception as e:
        logger.error(f"Could not get chat info for {group_id}: {e}")
        group_name = "this group"

    if action == "approve":
        await add_group(group_id, group_name)
        await query.message.edit_text(f"✅ <b>Group Approved!</b>\n<b>{group_name}</b> (<code>{group_id}</code>) is now enabled for auto-search.")
        await query.answer("Approved!", show_alert=False)
    
    elif action == "disapprove":
        await remove_group(group_id)
        await query.message.edit_text(f"❌ <b>Group Disapproved.</b>\nAuto-search has been disabled for <b>{group_name}</b> (<code>{group_id}</code>). I will now leave the group.")
        await client.leave_chat(group_id)
        await query.answer("Disapproved and Left!", show_alert=False)
