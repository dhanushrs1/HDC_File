import base64
import re
import asyncio
import time
from pyrogram import filters, Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import (
    FORCE_SUB_CHANNEL, 
    ADMINS, 
    AUTO_DELETE_TIME, 
    RE_REQUEST_EXPIRY_HOURS, 
    EXPIRED_MSG,
    FINAL_EXPIRED_MSG
)
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait, MessageNotModified

async def is_subscribed(filter, client, update):
    if not FORCE_SUB_CHANNEL:
        return True
    user_id = update.from_user.id
    if user_id in ADMINS:
        return True
    try:
        member = await client.get_chat_member(chat_id = FORCE_SUB_CHANNEL, user_id = user_id)
    except UserNotParticipant:
        return False

    if not member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
        return False
    else:
        return True

async def encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    base64_string = (base64_bytes.decode("ascii")).strip("=")
    return base64_string

async def decode(base64_string):
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes) 
    string = string_bytes.decode("ascii")
    return string

async def get_messages(client, message_ids):
    messages = []
    total_messages = 0
    while total_messages != len(message_ids):
        temb_ids = message_ids[total_messages:total_messages+200]
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temb_ids
            )
        except FloodWait as e:
            await asyncio.sleep(e.x)
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temb_ids
            )
        except:
            pass
        total_messages += len(temb_ids)
        messages.extend(msgs)
    return messages

async def get_message_id(client, message):
    if message.forward_from_chat:
        if message.forward_from_chat.id == client.db_channel.id:
            return message.forward_from_message_id
        else:
            return 0
    elif message.forward_sender_name:
        return 0
    elif message.text:
        pattern = r"https://t.me/(?:c/)?(.*)/(\d+)"
        matches = re.match(pattern,message.text)
        if not matches:
            return 0
        channel_id = matches.group(1)
        msg_id = int(matches.group(2))
        if channel_id.isdigit():
            if f"-100{channel_id}" == str(client.db_channel.id):
                return msg_id
        else:
            if channel_id == client.db_channel.username:
                return msg_id
    else:
        return 0

def get_readable_time(seconds: int) -> str:
    result = ""
    if seconds > 0:
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days > 0: result += f"{days}d "
        if hours > 0: result += f"{hours}h "
        if minutes > 0: result += f"{minutes}m "
        if seconds > 0: result += f"{seconds}s"
    else: return "0s"
    return result.strip()

# --- Upgraded Smart Expiry Function ---
async def handle_file_expiry(client: Client, timer_message: Message, file_to_delete: Message, db_message_id: int, is_rerequest: bool = False):
    """
    Creates a live countdown. If it's the initial request, it shows a 'Request Again' button.
    If it's a re-request, it performs a final deletion.
    """
    start_time = time.time()
    end_time = start_time + AUTO_DELETE_TIME

    while time.time() < end_time:
        remaining_time = int(end_time - time.time())
        update_interval = 5 if remaining_time > 10 else 1
        
        try:
            await timer_message.edit_text(f"⏳ This file will expire in: <b>{get_readable_time(remaining_time)}</b>")
        except MessageNotModified:
            pass
        except Exception as e:
            print(f"Error updating timer for message {timer_message.id}: {e}")
            break
        
        await asyncio.sleep(update_interval)

    # --- Time is up ---
    try:
        await file_to_delete.delete()
        
        if is_rerequest:
            # Final expiry for re-requested files
            await timer_message.edit(FINAL_EXPIRED_MSG)
        else:
            # Initial expiry, show the "Request Again" button
            expiry_timestamp = int(time.time()) + (RE_REQUEST_EXPIRY_HOURS * 3600)
            callback_data = f"rerequest_{db_message_id}_{expiry_timestamp}"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔄 Request File Again", callback_data=callback_data)]]
            )
            expiry_message_text = EXPIRED_MSG.format(hours=RE_REQUEST_EXPIRY_HOURS)
            await timer_message.edit(expiry_message_text, reply_markup=keyboard)
            
    except Exception as e:
        print(f"Could not finalize file expiry for message {timer_message.id}: {e}")
        try:
            await timer_message.edit("This file has expired.")
        except:
            pass

subscribed = filters.create(is_subscribed)
