import asyncio
import logging
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserIsBlocked, InputUserDeactivated, MessageNotModified

from bot import Bot
from config import ADMINS

# Configure logging
logger = logging.getLogger(__name__)

# --- Main command for users to make a request ---
@Bot.on_message(filters.private & filters.command("request"))
async def file_request_handler(client: Bot, message: Message):
    """Handle user file requests"""
    if len(message.command) < 2:
        await message.reply_text(
            "🎬 <b>How to use the request command:</b>\n\n"
            "Type <code>/request</code> followed by a description of the content you're looking for.\n\n"
            "<b>Examples:</b>\n"
            "• <code>/request The Dark Knight (2008)</code>\n"
            "• <code>/request Avengers Endgame 4K</code>\n"
            "• <code>/request Breaking Bad Season 1</code>\n\n"
            "💡 <i>Be specific for better results!</i>"
        )
        return

    request_text = " ".join(message.command[1:])
    user_info = message.from_user
    
    # Validate request length
    if len(request_text) > 500:
        await message.reply_text(
            "❌ <b>Request too long!</b>\n\n"
            "Please keep your request under 500 characters."
        )
        return
    
    # Clean and format the request
    request_text = request_text.strip()
    
    request_details = (
        f"📩 <b>New File Request</b> 📩\n\n"
        f"<b>From:</b> {user_info.mention}\n"
        f"<b>User ID:</b> <code>{user_info.id}</code>\n"
        f"<b>Username:</b> @{user_info.username or 'N/A'}\n"
        f"<b>Date:</b> {message.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"<b>Request:</b>\n<blockquote><i>{request_text}</i></blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"req_accept_{user_info.id}_{message.id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"req_decline_menu_{user_info.id}_{message.id}")
        ],
        [
            InlineKeyboardButton("💬 Reply Text", callback_data=f"req_reply_text_{user_info.id}_{message.id}"),
            InlineKeyboardButton("📁 Send Media", callback_data=f"req_reply_media_{user_info.id}_{message.id}")
        ],
        [
            InlineKeyboardButton("👤 User Info", callback_data=f"req_user_info_{user_info.id}_{message.id}")
        ]
    ])

    request_sent = False
    failed_admins = []
    
    for admin_id in ADMINS:
        try:
            await client.send_message(
                chat_id=admin_id, 
                text=request_details, 
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            request_sent = True
        except Exception as e:
            logger.error(f"Failed to send request to admin {admin_id}: {e}")
            failed_admins.append(admin_id)
    
    if request_sent:
        await message.reply_text(
            "✅ <b>Request Sent Successfully!</b>\n\n"
            "📤 Your request has been forwarded to our admin team.\n"
            "⏱️ We'll review it shortly and get back to you.\n\n"
            "💡 <i>You can send another request anytime using /request</i>"
        )
    else:
        await message.reply_text(
            "❌ <b>Unable to Send Request</b>\n\n"
            "Sorry, we couldn't forward your request to any admins right now.\n"
            "Please try again later or contact support."
        )

# --- Handler for "Accept" button ---
@Bot.on_callback_query(filters.regex("^req_accept_"))
async def accept_request_handler(client: Bot, query: CallbackQuery):
    """Handle request acceptance"""
    try:
        data_parts = query.data.split("_")
        if len(data_parts) != 4:
            await query.answer("❌ Invalid callback data format", show_alert=True)
            return
            
        _, _, requester_id_str, original_msg_id_str = data_parts
        requester_id = int(requester_id_str)
        
        admin_info = query.from_user
        
        # Extract original request text safely
        try:
            message_text = query.message.text
            if "Request:" in message_text:
                original_request_text = message_text.split("Request:")[1].strip()
                # Remove blockquote tags if present
                original_request_text = original_request_text.replace("<blockquote><i>", "").replace("</i></blockquote>", "")
            else:
                original_request_text = "[Request details not found]"
        except (IndexError, AttributeError):
            original_request_text = "[Request details not available]"

        # Send acceptance message to user
        try:
            await client.send_message(
                chat_id=requester_id,
                text=(
                    "🎉 <b>Great News!</b>\n\n"
                    f"✅ Your request has been <b>accepted</b>:\n"
                    f"<blockquote><i>{original_request_text}</i></blockquote>\n\n"
                    "📤 Our team will upload the content soon.\n"
                    "🔔 You'll be notified once it's ready!\n\n"
                    "Thanks for your patience! 😊"
                )
            )
            
            # Update admin message
            updated_text = f"{query.message.text}\n\n" + "─" * 30 + f"\n<b>✅ ACCEPTED</b>\n<b>Admin:</b> {admin_info.mention}\n<b>Time:</b> {query.message.date.strftime('%H:%M:%S')}"
            
            await query.message.edit_text(updated_text, reply_markup=None)
            await query.answer("✅ User notified of acceptance!", show_alert=True)
            
        except (UserIsBlocked, InputUserDeactivated):
            await query.message.edit_text(
                f"{query.message.text}\n\n" + "─" * 30 + "\n<b>⚠️ STATUS:</b> User has blocked the bot or deactivated account",
                reply_markup=None
            )
            await query.answer("⚠️ User has blocked the bot", show_alert=True)
            
    except ValueError as e:
        logger.error(f"Error in accept_request_handler: {e}")
        await query.answer("❌ Invalid data format", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in accept_request_handler: {e}")
        await query.answer("❌ An error occurred", show_alert=True)

# --- Handler for "Decline" button (shows reason menu) ---
@Bot.on_callback_query(filters.regex("^req_decline_menu_"))
async def decline_menu_handler(client: Bot, query: CallbackQuery):
    """Show decline reason menu"""
    try:
        data_parts = query.data.split("_")
        if len(data_parts) != 5:
            await query.answer("❌ Invalid callback data format", show_alert=True)
            return
            
        _, _, _, requester_id_str, original_msg_id_str = data_parts
        requester_id = int(requester_id_str)
        original_msg_id = int(original_msg_id_str)
        
        decline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📵 Not Available", callback_data=f"req_reason_na_{requester_id}_{original_msg_id}")],
            [InlineKeyboardButton("❓ Invalid Request", callback_data=f"req_reason_ir_{requester_id}_{original_msg_id}")],
            [InlineKeyboardButton("🚫 Policy Violation", callback_data=f"req_reason_cp_{requester_id}_{original_msg_id}")],
            [InlineKeyboardButton("🔍 Need More Info", callback_data=f"req_reason_mi_{requester_id}_{original_msg_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"req_reason_cancel_{requester_id}_{original_msg_id}")]
        ])
        
        await query.message.edit_text(
            f"{query.message.text}\n\n" + "─" * 30 + "\n<b>🔽 SELECT DECLINE REASON:</b>", 
            reply_markup=decline_keyboard
        )
        await query.answer()
        
    except ValueError as e:
        logger.error(f"Error in decline_menu_handler: {e}")
        await query.answer("❌ Invalid data format", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in decline_menu_handler: {e}")
        await query.answer("❌ An error occurred", show_alert=True)

# --- Handler for "Reply with Text" button ---
@Bot.on_callback_query(filters.regex("^req_reply_text_"))
async def reply_text_handler(client: Bot, query: CallbackQuery):
    """Handle text reply to user"""
    try:
        data_parts = query.data.split("_")
        if len(data_parts) != 5:
            await query.answer("❌ Invalid callback data format", show_alert=True)
            return
            
        _, _, _, requester_id_str, original_msg_id_str = data_parts
        requester_id = int(requester_id_str)
        admin_info = query.from_user
        
        # Ask admin for custom message
        try:
            await query.answer("📝 Send your message...")
            custom_msg_prompt = await client.ask(
                chat_id=query.from_user.id,
                text=(
                    "📝 <b>Send Custom Message</b>\n\n"
                    "Type the message you want to send to the user.\n"
                    "You can include text, links, or instructions.\n\n"
                    "⏱️ <i>You have 5 minutes to respond.</i>"
                ),
                filters=filters.text,
                timeout=300
            )
            
            # Send custom message to user
            await client.send_message(
                chat_id=requester_id,
                text=(
                    "💬 <b>Message from Admin</b>\n\n"
                    f"{custom_msg_prompt.text}\n\n"
                    "────────────────\n"
                    "<i>Regarding your recent request</i>"
                )
            )
            
            await custom_msg_prompt.reply_text("✅ Message sent successfully!")
            
            # Update admin message
            updated_text = f"{query.message.text}\n\n" + "─" * 30 + f"\n<b>💬 CUSTOM REPLY SENT</b>\n<b>Admin:</b> {admin_info.mention}\n<b>Time:</b> {query.message.date.strftime('%H:%M:%S')}"
            await query.message.edit_text(updated_text, reply_markup=None)
            
        except asyncio.TimeoutError:
            await client.send_message(
                query.from_user.id, 
                "⏰ <b>Timeout!</b>\n\nYou took too long to respond. Please try again."
            )
        except (UserIsBlocked, InputUserDeactivated):
            await query.message.edit_text(
                f"{query.message.text}\n\n" + "─" * 30 + "\n<b>⚠️ STATUS:</b> User has blocked the bot",
                reply_markup=None
            )
            
    except ValueError as e:
        logger.error(f"Error in reply_text_handler: {e}")
        await query.answer("❌ Invalid data format", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in reply_text_handler: {e}")
        await query.answer("❌ An error occurred", show_alert=True)

# --- Handler for "Send Media" button ---
@Bot.on_callback_query(filters.regex("^req_reply_media_"))
async def reply_media_handler(client: Bot, query: CallbackQuery):
    """Handle media reply to user"""
    try:
        data_parts = query.data.split("_")
        if len(data_parts) != 5:
            await query.answer("❌ Invalid callback data format", show_alert=True)
            return
            
        _, _, _, requester_id_str, original_msg_id_str = data_parts
        requester_id = int(requester_id_str)
        admin_info = query.from_user

        try:
            await query.answer("📁 Send your media...")
            custom_media_prompt = await client.ask(
                chat_id=query.from_user.id,
                text=(
                    "📁 <b>Send Media File</b>\n\n"
                    "Send the media file you want to share with the user:\n"
                    "• 📷 Photo\n"
                    "• 🎥 Video\n"
                    "• 📄 Document\n"
                    "• 🎵 Audio\n\n"
                    "⏱️ <i>You have 5 minutes to send the file.</i>"
                ),
                filters=filters.media | filters.document,
                timeout=300
            )
            
            # Forward media to user with custom caption
            if custom_media_prompt.caption:
                caption = f"📁 <b>File from Admin</b>\n\n{custom_media_prompt.caption}\n\n────────────────\n<i>Regarding your recent request</i>"
            else:
                caption = "📁 <b>File from Admin</b>\n\n────────────────\n<i>Regarding your recent request</i>"
            
            await custom_media_prompt.copy(
                chat_id=requester_id,
                caption=caption
            )
            
            await custom_media_prompt.reply_text("✅ Media sent successfully!")
            
            # Update admin message
            media_type = "📷 Photo" if custom_media_prompt.photo else "🎥 Video" if custom_media_prompt.video else "📄 Document"
            updated_text = f"{query.message.text}\n\n" + "─" * 30 + f"\n<b>📁 MEDIA SENT</b> ({media_type})\n<b>Admin:</b> {admin_info.mention}\n<b>Time:</b> {query.message.date.strftime('%H:%M:%S')}"
            await query.message.edit_text(updated_text, reply_markup=None)
            
        except asyncio.TimeoutError:
            await client.send_message(
                query.from_user.id, 
                "⏰ <b>Timeout!</b>\n\nYou took too long to send the media. Please try again."
            )
        except (UserIsBlocked, InputUserDeactivated):
            await query.message.edit_text(
                f"{query.message.text}\n\n" + "─" * 30 + "\n<b>⚠️ STATUS:</b> User has blocked the bot",
                reply_markup=None
            )
            
    except ValueError as e:
        logger.error(f"Error in reply_media_handler: {e}")
        await query.answer("❌ Invalid data format", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in reply_media_handler: {e}")
        await query.answer("❌ An error occurred", show_alert=True)

# --- Handler for User Info button ---
@Bot.on_callback_query(filters.regex("^req_user_info_"))
async def user_info_handler(client: Bot, query: CallbackQuery):
    """Show detailed user information"""
    try:
        data_parts = query.data.split("_")
        if len(data_parts) != 5:
            await query.answer("❌ Invalid callback data format", show_alert=True)
            return
            
        _, _, _, requester_id_str, original_msg_id_str = data_parts
        requester_id = int(requester_id_str)
        
        try:
            user = await client.get_users(requester_id)
            user_info_text = (
                f"👤 <b>User Information</b>\n\n"
                f"<b>Name:</b> {user.first_name} {user.last_name or ''}\n"
                f"<b>Username:</b> @{user.username or 'None'}\n"
                f"<b>User ID:</b> <code>{user.id}</code>\n"
                f"<b>Is Bot:</b> {'Yes' if user.is_bot else 'No'}\n"
                f"<b>Is Premium:</b> {'Yes' if user.is_premium else 'No'}\n"
                f"<b>Language:</b> {user.language_code or 'Unknown'}\n"
                f"<b>Status:</b> {user.status or 'Unknown'}"
            )
            
            back_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Request", callback_data=f"req_back_to_main_{requester_id}_{original_msg_id_str}")]
            ])
            
            await query.message.edit_text(user_info_text, reply_markup=back_keyboard)
            await query.answer()
            
        except Exception as e:
            await query.answer(f"❌ Could not fetch user info: {str(e)}", show_alert=True)
            
    except ValueError as e:
        logger.error(f"Error in user_info_handler: {e}")
        await query.answer("❌ Invalid data format", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in user_info_handler: {e}")
        await query.answer("❌ An error occurred", show_alert=True)

# --- Handler for back to main request ---
@Bot.on_callback_query(filters.regex("^req_back_to_main_"))
async def back_to_main_handler(client: Bot, query: CallbackQuery):
    """Go back to main request view"""
    try:
        data_parts = query.data.split("_")
        if len(data_parts) != 6:
            await query.answer("❌ Invalid callback data format", show_alert=True)
            return
            
        _, _, _, _, requester_id_str, original_msg_id_str = data_parts
        requester_id = int(requester_id_str)
        original_msg_id = int(original_msg_id_str)
        
        # Restore original keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Accept", callback_data=f"req_accept_{requester_id}_{original_msg_id}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"req_decline_menu_{requester_id}_{original_msg_id}")
            ],
            [
                InlineKeyboardButton("💬 Reply Text", callback_data=f"req_reply_text_{requester_id}_{original_msg_id}"),
                InlineKeyboardButton("📁 Send Media", callback_data=f"req_reply_media_{requester_id}_{original_msg_id}")
            ],
            [
                InlineKeyboardButton("👤 User Info", callback_data=f"req_user_info_{requester_id}_{original_msg_id}")
            ]
        ])
        
        # Get original message text (remove any status updates)
        original_text = query.message.text.split("─" * 30)[0].strip()
        
        await query.message.edit_text(original_text, reply_markup=keyboard)
        await query.answer()
        
    except Exception as e:
        logger.error(f"Error in back_to_main_handler: {e}")
        await query.answer("❌ An error occurred", show_alert=True)

# --- Handler for Decline Reason buttons ---
@Bot.on_callback_query(filters.regex("^req_reason_"))
async def decline_reason_handler(client: Bot, query: CallbackQuery):
    """Handle decline reasons"""
    try:
        data_parts = query.data.split("_")
        logger.info(f"Decline reason callback data: {query.data}, parts: {data_parts}")
        
        # Expected format: req_reason_[code]_[requester_id]_[original_msg_id]
        if len(data_parts) < 4:
            await query.answer("❌ Invalid callback data format", show_alert=True)
            return
            
        _, _, reason_code = data_parts[:3]
        requester_id = int(data_parts[3])
        original_msg_id = int(data_parts[4]) if len(data_parts) > 4 else 0
        
        admin_info = query.from_user
        
        # Extract original request text
        try:
            message_text = query.message.text
            if "Request:" in message_text:
                original_request_text = message_text.split("Request:")[1].split("─" * 30)[0].strip()
                original_request_text = original_request_text.replace("<blockquote><i>", "").replace("</i></blockquote>", "")
            else:
                original_request_text = "[Request details not found]"
        except (IndexError, AttributeError):
            original_request_text = "[Request details not available]"

        # Handle cancel action
        if reason_code == "cancel":
            # Restore original message and keyboard
            original_text = query.message.text.split("─" * 30)[0].strip()
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Accept", callback_data=f"req_accept_{requester_id}_{original_msg_id}"),
                    InlineKeyboardButton("❌ Decline", callback_data=f"req_decline_menu_{requester_id}_{original_msg_id}")
                ],
                [
                    InlineKeyboardButton("💬 Reply Text", callback_data=f"req_reply_text_{requester_id}_{original_msg_id}"),
                    InlineKeyboardButton("📁 Send Media", callback_data=f"req_reply_media_{requester_id}_{original_msg_id}")
                ],
                [
                    InlineKeyboardButton("👤 User Info", callback_data=f"req_user_info_{requester_id}_{original_msg_id}")
                ]
            ])
            await query.message.edit_text(original_text, reply_markup=keyboard)
            await query.answer("Action cancelled")
            return

        # Map reason codes to messages
        reason_messages = {
            "na": "📵 The content you requested is currently not available in our collection.",
            "ir": "❓ Your request was not specific enough. Please provide more details like year, quality, or episode number.",
            "cp": "🚫 Your request violates our content policy and cannot be fulfilled.",
            "mi": "🔍 We need more information about your request. Please be more specific about what you're looking for."
        }
        
        reason_emojis = {
            "na": "📵 Not Available",
            "ir": "❓ Invalid Request", 
            "cp": "🚫 Policy Violation",
            "mi": "🔍 Need More Info"
        }

        reason_text = reason_messages.get(reason_code, "Your request could not be fulfilled.")
        reason_title = reason_emojis.get(reason_code, "Request Declined")

        try:
            # Send decline message to user
            await client.send_message(
                chat_id=requester_id,
                text=(
                    f"❌ <b>Request Declined</b>\n\n"
                    f"Your request:\n<blockquote><i>{original_request_text}</i></blockquote>\n\n"
                    f"<b>Reason:</b> {reason_text}\n\n"
                    "💡 <i>You can submit a new request with /request</i>"
                )
            )
            
            # Update admin message
            updated_text = f"{query.message.text.split('─' * 30)[0]}\n\n" + "─" * 30 + f"\n<b>❌ DECLINED</b> ({reason_title})\n<b>Admin:</b> {admin_info.mention}\n<b>Time:</b> {query.message.date.strftime('%H:%M:%S')}"
            await query.message.edit_text(updated_text, reply_markup=None)
            await query.answer(f"✅ User notified: {reason_title}", show_alert=True)
            
        except (UserIsBlocked, InputUserDeactivated):
            await query.message.edit_text(
                f"{query.message.text.split('─' * 30)[0]}\n\n" + "─" * 30 + "\n<b>⚠️ STATUS:</b> User has blocked the bot",
                reply_markup=None
            )
            await query.answer("⚠️ User has blocked the bot", show_alert=True)
            
    except (ValueError, IndexError) as e:
        logger.error(f"Error in decline_reason_handler: {e}, callback_data: {query.data}")
        await query.answer("❌ Invalid data format", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in decline_reason_handler: {e}")
        await query.answer("❌ An error occurred", show_alert=True)