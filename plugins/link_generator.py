#(©)CodeXBotz

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import ADMINS
from helper_func import encode, get_message_id

# This filter ensures that only forwarded media files are accepted for link generation
media_filter = filters.forwarded & (filters.document | filters.video | filters.photo)

@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('batch'))
async def batch(client: Client, message: Message):
    if not client.config.REDIRECT_URL:
        await message.reply_text("<b>Error:</b> <code>REDIRECT_URL</code> is not set in your config.")
        return

    while True:
        try:
            first_message = await client.ask(
                text="🔗 <b>Batch Link Generation: Step 1 of 2</b>\n\nPlease forward the <b>first media file</b> from your database channel.",
                chat_id=message.from_user.id,
                filters=media_filter,
                timeout=60
            )
        except:
            return # Timeout
        f_msg_id = await get_message_id(client, first_message)
        if f_msg_id:
            break
        else:
            await first_message.reply("❌ <b>Error:</b> This file is not from your database channel. Please forward a valid file.", quote=True)
            continue

    while True:
        try:
            second_message = await client.ask(
                text="🔗 <b>Batch Link Generation: Step 2 of 2</b>\n\nExcellent. Now, please forward the <b>last media file</b> from your database channel.",
                chat_id=message.from_user.id,
                filters=media_filter,
                timeout=60
            )
        except:
            return # Timeout
        s_msg_id = await get_message_id(client, second_message)
        if s_msg_id:
            break
        else:
            await second_message.reply("❌ <b>Error:</b> This file is not from your database channel. Please forward a valid file.", quote=True)
            continue


    string = f"get-{f_msg_id * abs(client.db_channel.id)}-{s_msg_id * abs(client.db_channel.id)}"
    base64_string = await encode(string)
    link = f"{client.config.REDIRECT_URL}?start={base64_string}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]])
    
    await second_message.reply_text(
        f"✅ <b>Batch Link Generated!</b>\n\nYour permanent link is ready to be shared.\n\n<code>{link}</code>",
        quote=True,
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
async def link_generator(client: Client, message: Message):
    if not client.config.REDIRECT_URL:
        await message.reply_text("<b>Error:</b> <code>REDIRECT_URL</code> is not set in your config.")
        return
        
    while True:
        try:
            channel_message = await client.ask(
                text="🔗 <b>Single Link Generation</b>\n\nPlease forward the media file (Photo, Video, or Document) from your database channel.",
                chat_id=message.from_user.id,
                filters=media_filter,
                timeout=60
            )
        except:
            return # Timeout
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            break
        else:
            await channel_message.reply("❌ <b>Error:</b> This file is not from your database channel. Please forward a valid file.", quote=True)
            continue

    base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
    link = f"{client.config.REDIRECT_URL}?start={base64_string}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share Link", url=f'https://telegram.me/share/url?url={link}')]])

    await channel_message.reply_text(
        f"✅ <b>Link Generated!</b>\n\nYour permanent link is ready to be shared.\n\n<code>{link}</code>",
        quote=True,
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
