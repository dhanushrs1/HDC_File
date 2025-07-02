import base64
import re
import asyncio
import time
import logging
import math
from pyrogram import filters, Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait, MessageNotModified, UserNotParticipant

from config import (
    FORCE_SUB_CHANNEL, 
    ADMINS, 
    AUTO_DELETE_TIME, 
    RE_REQUEST_EXPIRY_HOURS, 
    EXPIRED_MSG,
    FINAL_EXPIRED_MSG
)

# Set up a logger for this module
logger = logging.getLogger(__name__)

def format_bytes(size_bytes):
    """Converts bytes to a human-readable format (KB, MB, GB)."""
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

async def is_subscribed(filter, client: Client, update: Message):
    """
    Checks if a user is subscribed to the force subscription channel.
    Admins are always exempt.
    """
    if not FORCE_SUB_CHANNEL:
        return True
    
    user_id = update.from_user.id
    if user_id in ADMINS:
        return True
        
    try:
        member = await client.get_chat_member(chat_id=FORCE_SUB_CHANNEL, user_id=user_id)
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Could not check subscription for user {user_id}: {e}")
        return False

    if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
        return False
    else:
        return True

async def encode(string: str) -> str:
    """Encodes a string to a URL-safe base64 string."""
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    base64_string = base64_bytes.decode("ascii").strip("=")
    return base64_string

async def decode(base64_string: str) -> str:
    """Decodes a URL-safe base64 string back to a string."""
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes) 
    string = string_bytes.decode("ascii")
    return string

async def get_messages(client: Client, message_ids) -> list:
    """
    Fetches messages in batches of 200 from the database channel.
    Handles FloodWait and logs other errors gracefully.
    """
    messages = []
    total_messages = 0
    
    if isinstance(message_ids, range):
        message_ids = list(message_ids)
    elif not isinstance(message_ids, list):
        message_ids = [message_ids]
        
    while total_messages != len(message_ids):
        batch_ids = message_ids[total_messages : total_messages + 200]
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=batch_ids
            )
            messages.extend(msgs)
        except FloodWait as e:
            logger.warning(f"FloodWait of {e.value} seconds, sleeping...")
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            logger.error(f"Error getting messages from DB channel: {e}", exc_info=True)
            
        total_messages += len(batch_ids)
        
    return messages


async def get_message_id(client: Client, message: Message) -> int:
    """
    Parses a message to find the message ID of a file from the database channel.
    Accepts forwarded messages or direct links.
    """
    if message.forward_from_chat:
        if message.forward_from_chat.id == client.db_channel.id:
            return message.forward_from_message_id
    elif message.text:
        pattern = r"https://t.me/(?:c/)?(.+?)/(\d+)"
        match = re.match(pattern, message.text)
        if match:
            channel_identifier = match.group(1)
            msg_id = int(match.group(2))
            if channel_identifier.isdigit() and f"-100{channel_identifier}" == str(client.db_channel.id):
                return msg_id
            elif channel_identifier == client.db_channel.username:
                return msg_id
                
    return 0

def get_readable_time(seconds: int) -> str:
    """Converts seconds into a human-readable format (e.g., 1d 2h 3m 4s)."""
    result = ""
    if seconds <= 0:
        return "0s"
        
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    
    if days > 0: result += f"{days}d "
    if hours > 0: result += f"{hours}h "
    if minutes > 0: result += f"{minutes}m "
    if seconds > 0: result += f"{seconds}s"
    
    return result.strip()

async def handle_file_expiry(client: Client, timer_message: Message, file_to_delete: Message, db_message_id: int, is_rerequest: bool = False):
    """
    Manages a live countdown for temporary files.
    """
    start_time = time.time()
    end_time = start_time + AUTO_DELETE_TIME

    while time.time() < end_time:
        remaining_time = int(end_time - time.time())
        update_interval = 15 if remaining_time > 60 else 5
        
        try:
            await timer_message.edit_text(f"⏳ This file will expire in: <b>{get_readable_time(remaining_time)}</b>")
        except MessageNotModified:
            pass
        except Exception as e:
            logger.error(f"Error updating timer for message {timer_message.id}: {e}")
            break
        
        await asyncio.sleep(update_interval)

    try:
        await file_to_delete.delete()
        
        if is_rerequest:
            await timer_message.edit(FINAL_EXPIRED_MSG)
        else:
            expiry_timestamp = int(time.time()) + (RE_REQUEST_EXPIRY_HOURS * 3600)
            callback_data = f"rerequest_{db_message_id}_{expiry_timestamp}"
            
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔄 Request File Again", callback_data=callback_data)]]
            )
            expiry_message_text = EXPIRED_MSG.format(hours=RE_REQUEST_EXPIRY_HOURS)
            
            await timer_message.edit(expiry_message_text, reply_markup=keyboard)
            
    except Exception as e:
        logger.error(f"Could not finalize file expiry for message {timer_message.id}: {e}")
        try:
            await timer_message.edit("This file has expired.")
        except Exception as final_e:
            logger.error(f"Failed to edit final expiry message for {timer_message.id}: {final_e}")

subscribed = filters.create(is_subscribed)
