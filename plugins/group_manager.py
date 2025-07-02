"""
(©) HD Cinema Bot

This new, advanced plugin handles all group management features.
- Proactively notifies the owner about the bot's status changes in groups.
- Provides a smart, context-aware UI for group management.
- A new /groups command for a centralized UI-based management panel.
"""

import logging
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

from bot import Bot
from config import OWNER_ID
from database.database import add_group, remove_group, get_approved_groups

# Set up a logger for this module
logger = logging.getLogger(__name__)

# ======================================================================================
#                              *** Proactive Group Detection ***
# ======================================================================================

@Bot.on_chat_member_updated(filters.group, group=2)
async def on_bot_status_change(client: Bot, update: ChatMemberUpdated):
    """
    This intelligent handler tracks when the bot is added, removed,
    promoted, or demoted in a group and sends a specific notification to the owner.
    """
    if not update.new_chat_member or update.new_chat_member.user.id != client.me.id:
        return # Ignore if the update is not about the bot.

    chat = update.chat
    
    # --- Scenario 1: Bot is ADDED to a group ---
    if update.new_chat_member.status == ChatMemberStatus.MEMBER:
        try:
            # Check if the bot is an admin upon being added
            me = await chat.get_member(client.me.id)
            is_admin = me.status == ChatMemberStatus.ADMINISTRATOR
        except Exception:
            is_admin = False
        
        if is_admin:
            # If added as admin, send the approval message
            text = (
                f"🔔 <b>Admin Promotion Alert</b> 🔔\n\n"
                f"I have been added and promoted to admin in a new group:\n\n"
                f"<b>Name:</b> {chat.title}\n"
                f"<b>ID:</b> <code>{chat.id}</code>\n"
                f"<b>Members:</b> {chat.members_count or 'N/A'}"
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve Group", callback_data=f"grp_approve_{chat.id}"),
                    InlineKeyboardButton("❌ Disapprove & Leave", callback_data=f"grp_disapprove_{chat.id}")
                ]
            ])
        else:
            # If added as a regular member, send a warning
            text = (
                f"⚠️ <b>Permissions Needed</b> ⚠️\n\n"
                f"I have been added to a new group, but I am not an admin.\n\n"
                f"<b>Name:</b> {chat.title}\n"
                f"<b>ID:</b> <code>{chat.id}</code>\n\n"
                "Please promote me to admin so I can function correctly."
            )
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Leave Group", callback_data=f"grp_disapprove_{chat.id}")]])
        
        try: await client.send_message(OWNER_ID, text, reply_markup=keyboard)
        except Exception as e: logger.error(f"Could not send new group alert to owner. Error: {e}")

    # --- Scenario 2: Bot is PROMOTED to admin ---
    elif update.new_chat_member.status == ChatMemberStatus.ADMINISTRATOR:
        text = (
            f"✅ <b>Promoted to Admin</b> ✅\n\n"
            f"I have been promoted to admin in the group:\n\n"
            f"<b>Name:</b> {chat.title}\n"
            f"<b>ID:</b> <code>{chat.id}</code>\n\n"
            "You can now approve this group for auto-search."
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve Group", callback_data=f"grp_approve_{chat.id}"),
                InlineKeyboardButton("❌ Leave Group", callback_data=f"grp_disapprove_{chat.id}")
            ]
        ])
        try: await client.send_message(OWNER_ID, text, reply_markup=keyboard)
        except Exception as e: logger.error(f"Could not send promotion alert to owner. Error: {e}")

    # --- Scenario 3: Bot is KICKED or LEAVES a group ---
    elif update.new_chat_member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT]:
        await remove_group(chat.id) # Clean up from DB
        text = (
            f"❌ <b>Removed from Group</b> ❌\n\n"
            f"I have been removed from the group:\n\n"
            f"<b>Name:</b> {chat.title}\n"
            f"<b>ID:</b> <code>{chat.id}</code>"
        )
        try: await client.send_message(OWNER_ID, text)
        except Exception as e: logger.error(f"Could not send removal alert to owner. Error: {e}")

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
            InlineKeyboardButton(f"{group_name}", url=f"https://t.me/c/{abs(group_id)}/1"),
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
        try:
            await client.leave_chat(group_id)
        except Exception as e:
            logger.error(f"Failed to leave chat {group_id}. Maybe I was already removed? Error: {e}")
        await query.answer("Disapproved and Left!", show_alert=False)
