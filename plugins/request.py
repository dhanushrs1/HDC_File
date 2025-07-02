"""
(©) HD Cinema Bot

This plugin manages the entire user file request system.
- /request: Allows users to submit a request for content.
- Admins receive an interactive notification to manage the request.
- Admins can accept, decline (with pre-defined reasons), or reply.
"""

import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserIsBlocked, InputUserDeactivated
from pyrogram.handlers import MessageHandler

from bot import Bot
from config import ADMINS

# Set up a logger for this module
logger = logging.getLogger(__name__)

async def ask_for_reply(client: Client, chat_id: int, text: str, filters, timeout: int = 300) -> Message:
    """A robust replacement for the old .ask() method for getting replies."""
    response_future = asyncio.Future()

    async def get_response(c, m):
        if m.chat.id == chat_id:
            response_future.set_result(m)

    handler = MessageHandler(get_response, filters)
    client.add_handler(handler)
    
    await client.send_message(chat_id, text)

    try:
        return await asyncio.wait_for(response_future, timeout=timeout)
    finally:
        client.remove_handler(handler)

@Bot.on_message(filters.private & filters.command("request"))
async def file_request_command(client: Bot, message: Message):
    """Handles the initial /request command from a user."""
    if len(message.command) < 2:
        return await message.reply_text(
            "🎬 <b>How to Request Content</b>\n\n"
            "Please use the <code>/request</code> command followed by a description of what you're looking for.\n\n"
            "<b>Example:</b>\n"
            "<code>/request The Dark Knight (2008) 4K</code>\n\n"
            "<i>💡 Being specific helps us find it faster!</i>"
        )

    request_text = " ".join(message.command[1:]).strip()
    if len(request_text) > 500:
        return await message.reply_text("❌ <b>Request too long!</b>\nPlease keep your request under 500 characters.")

    user = message.from_user
    
    request_details = (
        f"📩 <b>New File Request</b> 📩\n\n"
        f"<b>From:</b> {user.mention} (<code>{user.id}</code>)\n"
        f"<b>Username:</b> @{user.username or 'N/A'}\n\n"
        f"<b>Request:</b>\n<blockquote><i>{request_text}</i></blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"req_accept_{user.id}_{message.id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"req_decline_{user.id}_{message.id}")
        ],
        [
            InlineKeyboardButton("💬 Reply to User", callback_data=f"req_reply_{user.id}_{message.id}")
        ]
    ])

    request_sent = False
    for admin_id in ADMINS:
        try:
            await client.send_message(
                chat_id=admin_id, text=request_details, reply_markup=keyboard, disable_web_page_preview=True
            )
            request_sent = True
        except Exception as e:
            logger.error(f"Failed to send request to admin {admin_id}: {e}")
    
    if request_sent:
        await message.reply_text(
            "✅ <b>Request Sent!</b>\n\n"
            "Your request has been forwarded to our admin team. We'll review it shortly. 😊"
        )
    else:
        await message.reply_text("❌ <b>Unable to Send Request</b>\n\nSorry, we couldn't forward your request right now.")

@Bot.on_callback_query(filters.regex("^req_") & filters.user(ADMINS))
async def request_callback_handler(client: Bot, query: CallbackQuery):
    """Handles all admin actions on a request notification."""
    parts = query.data.split("_")
    action = parts[1]
    admin_info = query.from_user
    
    # --- Handler for Decline Reasons ---
    if action == "reason":
        # Correctly parse the callback data for reasons
        reason_code = parts[2]
        requester_id = int(parts[3])
        original_msg_id = int(parts[4])
        
        if reason_code == "cancel":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Accept", callback_data=f"req_accept_{requester_id}_{original_msg_id}")],
                [InlineKeyboardButton("❌ Decline", callback_data=f"req_decline_{requester_id}_{original_msg_id}")],
                [InlineKeyboardButton("💬 Reply to User", callback_data=f"req_reply_{requester_id}_{original_msg_id}")],
            ])
            await query.message.edit_text(query.message.text.split("─" * 20)[0].strip(), reply_markup=keyboard)
            return await query.answer("Action cancelled.")

        reasons = {
            "na": ("📵 Not Available", "The content you requested is not available in our collection."),
            "ir": ("❓ Invalid Request", "Your request was not specific enough. Please provide more details."),
            "pv": ("🚫 Policy Violation", "Your request violates our content policy and cannot be fulfilled.")
        }
        reason_title, reason_text = reasons.get(reason_code, ("Unknown", "Your request could not be fulfilled."))
        
        try:
            original_request_text = query.message.text.split("Request:")[1].split("─" * 20)[0].replace("<blockquote><i>", "").replace("</i></blockquote>", "").strip()
            await client.send_message(
                chat_id=requester_id,
                text=f"❌ <b>Request Declined</b>\n\nYour request for \"<i>{original_request_text}</i>\" was declined.\n\n<b>Reason:</b> {reason_text}"
            )
            updated_text = (
                f"{query.message.text.split('─' * 20)[0].strip()}\n\n"
                + "─" * 20
                + f"\n<b>❌ DECLINED</b> ({reason_title}) by {admin_info.mention}"
            )
            await query.message.edit_text(updated_text, reply_markup=None)
            await query.answer(f"✅ User notified: {reason_title}", show_alert=False)
        except (UserIsBlocked, InputUserDeactivated):
            await query.message.edit_text(
                f"{query.message.text.split('─' * 20)[0].strip()}\n\n" + "─" * 20 + "\n<b>⚠️ STATUS:</b> User has blocked the bot."
            )
        return

    # --- Handlers for main actions (accept, decline, reply) ---
    try:
        requester_id = int(parts[2])
        original_msg_id = int(parts[3])
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid request callback data: {query.data}, Error: {e}")
        return await query.answer("Invalid callback data.", show_alert=True)

    original_request_text = query.message.text.split("Request:")[1].split("</blockquote>")[0].replace("<blockquote><i>", "").strip()

    if action == "accept":
        try:
            await client.send_message(
                chat_id=requester_id,
                text=f"🎉 <b>Great News!</b>\n\nYour request has been <b>accepted</b>:\n<blockquote><i>{original_request_text}</i></blockquote>\n\nOur team will upload the content soon."
            )
            updated_text = f"{query.message.text}\n\n" + "─" * 20 + f"\n<b>✅ ACCEPTED</b> by {admin_info.mention}"
            await query.message.edit_text(updated_text, reply_markup=None)
            await query.answer("✅ User notified of acceptance!", show_alert=False)
        except (UserIsBlocked, InputUserDeactivated):
            await query.message.edit_text(f"{query.message.text}\n\n" + "─" * 20 + "\n<b>⚠️ STATUS:</b> User has blocked the bot.")
            await query.answer("⚠️ User has blocked the bot!", show_alert=True)

    elif action == "decline":
        decline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📵 Not Available", callback_data=f"req_reason_na_{requester_id}_{original_msg_id}")],
            [InlineKeyboardButton("❓ Invalid Request", callback_data=f"req_reason_ir_{requester_id}_{original_msg_id}")],
            [InlineKeyboardButton("🚫 Policy Violation", callback_data=f"req_reason_pv_{requester_id}_{original_msg_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"req_reason_cancel_{requester_id}_{original_msg_id}")]
        ])
        await query.message.edit_text(f"{query.message.text}\n\n" + "─" * 20 + "\n<b>🔽 SELECT DECLINE REASON:</b>", reply_markup=decline_keyboard)
        await query.answer()

    elif action == "reply":
        try:
            await query.answer("📝 Send your message...", show_alert=False)
            response_prompt = await ask_for_reply(
                client,
                chat_id=admin_info.id,
                text="📝 Please send the message you want to forward to the user.\n\nYou have 5 minutes.",
                filters=filters.text
            )
            await client.send_message(
                chat_id=requester_id,
                text=f"💬 <b>A message from our admin team regarding your request:</b>\n\n<i>{response_prompt.text}</i>"
            )
            await response_prompt.reply_text("✅ Message sent successfully!")
            updated_text = f"{query.message.text}\n\n" + "─" * 20 + f"\n<b>💬 REPLY SENT</b> by {admin_info.mention}"
            await query.message.edit_text(updated_text, reply_markup=None)
        except asyncio.TimeoutError:
            await client.send_message(admin_info.id, "⏰ <b>Timeout!</b> The reply operation was cancelled.")
        except (UserIsBlocked, InputUserDeactivated):
            await query.message.edit_text(f"{query.message.text}\n\n" + "─" * 20 + "\n<b>⚠️ STATUS:</b> User has blocked the bot.")
