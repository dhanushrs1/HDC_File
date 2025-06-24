import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, START_PIC, AUTO_DELETE_TIME, INITIAL_DELETE_MSG, JOIN_REQUEST_ENABLE, FORCE_SUB_CHANNEL
from helper_func import subscribed, decode, get_messages, handle_file_expiry, get_readable_time
from database.database import add_user, del_user, full_userbase, get_user, log_file_download

@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if user and user.get('banned', False):
        await message.reply_text("Sorry, you have been banned from using this bot.")
        return

    if not user:
        try:
            await add_user(user_id)
        except:
            pass
            
    text = message.text
    if len(text) > 7:
        # This block handles file link processing and remains unchanged.
        try:
            base64_string = text.split(" ", 1)[1]
        except:
            return
        string = await decode(base64_string)
        argument = string.split("-")
        if len(argument) == 3:
            try:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
            except: return
            if start <= end: ids = range(start, end + 1)
            else:
                ids = []
                i = start
                while True:
                    ids.append(i)
                    i -= 1
                    if i < end: break
        elif len(argument) == 2:
            try: ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            except: return

        temp_msg = await message.reply("<b>Please wait, processing your request...</b>")
        try:
            messages = await get_messages(client, ids)
        except:
            await message.reply_text("Something went wrong..!")
            return
        await temp_msg.delete()

        for msg in messages:
            await log_file_download(file_id=msg.id, user_id=user_id)
            if bool(CUSTOM_CAPTION) & bool(msg.document):
                caption = CUSTOM_CAPTION.format(previouscaption = getattr(msg.caption, 'html', ''), filename=msg.document.file_name)
            else:
                caption = getattr(msg.caption, 'html', '')
            reply_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None
            try:
                sent_message = await msg.copy(chat_id=user_id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:
                    timer_message = await sent_message.reply_text(text=f"⏳ This file will expire in: <b>{get_readable_time(AUTO_DELETE_TIME)}</b>", quote=True)
                    asyncio.create_task(handle_file_expiry(client, timer_message, sent_message, msg.id))
                await asyncio.sleep(0.5)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await start_command(client, message)
                return
        return
    else:
        # --- NEW: Enhanced & Role-Based Welcome Message ---
        
        # Base keyboard for all users
        keyboard = [
            [InlineKeyboardButton("🎬 Request a Movie", callback_data="request_info")],
            [
                InlineKeyboardButton("💬 Support", url="https://t.me/YourSupportGroup"), # Replace with your URL
                InlineKeyboardButton("📣 Updates", url="https://t.me/YourUpdatesChannel")  # Replace with your URL
            ]
        ]

        # Add "Admin Panel" button only if the user is an admin
        if user_id in ADMINS:
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_main_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_text = START_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username=None if not message.from_user.username else '@' + message.from_user.username,
            mention=message.from_user.mention,
            id=message.from_user.id
        )

        if START_PIC:
            await message.reply_photo(photo=START_PIC, caption=start_text, reply_markup=reply_markup, quote=True)
        else:
            await message.reply_text(text=start_text, reply_markup=reply_markup, disable_web_page_preview=True, quote=True)
        return

#=====================================================================================##
WAIT_MSG = """<b>Processing ...</b>"""
REPLY_ERROR = """<code>Use this command as a reply to any telegram message without any spaces.</code>"""
#=====================================================================================##

@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    if bool(JOIN_REQUEST_ENABLE):
        invite = await client.create_chat_invite_link(chat_id=FORCE_SUB_CHANNEL, creates_join_request=True)
        ButtonUrl = invite.invite_link
    else:
        ButtonUrl = client.invitelink
    buttons = [[InlineKeyboardButton("Join Channel", url=ButtonUrl)]]
    try:
        buttons.append([InlineKeyboardButton(text='Try Again', url=f"https://t.me/{client.username}?start={message.command[1]}")])
    except IndexError:
        pass
    await message.reply(
        text=FORCE_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username=None if not message.from_user.username else '@' + message.from_user.username,
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True,
        disable_web_page_preview=True
    )

@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await full_userbase()
    await msg.edit(f"<b>Total Active Users:</b> <code>{len(users)}</code>")

@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):
    pls_wait = await message.reply("<i>Broadcasting Message... This will Take Some Time</i>")
    query = await full_userbase()
    successful = 0
    blocked = 0
    deleted = 0
    unsuccessful = 0
    button_pattern = r"\[(.+?)\]\((.+?)\)"
    if message.reply_to_message:
        broadcast_msg = message.reply_to_message
        match = re.search(button_pattern, message.text)
        reply_markup = None
        if match:
            button_text = match.group(1)
            button_url = match.group(2)
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=button_text, url=button_url)]])
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id, reply_markup=reply_markup)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id, reply_markup=reply_markup)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
    else:
        full_pattern = r"/broadcast \[(.+?)\]\((.+?)\) - (.+)"
        match = re.match(full_pattern, message.text, re.DOTALL)
        if match:
            button_text = match.group(1)
            button_url = match.group(2)
            text_to_send = match.group(3)
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=button_text, url=button_url)]])
            for chat_id in query:
                try:
                    await client.send_message(chat_id=chat_id, text=text_to_send, reply_markup=reply_markup)
                    successful += 1
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await client.send_message(chat_id=chat_id, text=text_to_send, reply_markup=reply_markup)
                    successful += 1
                except UserIsBlocked:
                    await del_user(chat_id)
                    blocked += 1
                except InputUserDeactivated:
                    await del_user(chat_id)
                    deleted += 1
                except:
                    unsuccessful += 1
        else:
            await pls_wait.edit("<b>Invalid Format.</b>\n\nRefer to the `/help` command for broadcast usage.")
            return
    status = f"""<b><u>Broadcast Completed</u></b>\n\n<b>Total Users:</b> <code>{len(query)}</code>\n<b>Successful:</b> <code>{successful}</code>\n<b>Blocked Users:</b> <code>{blocked}</code>\n<b>Deleted Accounts:</b> <code>{deleted}</code>\n<b>Unsuccessful:</b> <code>{unsuccessful}</code>"""
    await pls_wait.edit(status)
