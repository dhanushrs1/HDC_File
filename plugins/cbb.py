from pyrogram import __version__, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import Bot
from config import OWNER_ID, START_MSG, ADMINS
@Bot.on_callback_query(filters.regex("^(start_menu|request_info|close)$"))
async def cb_handler(client: Bot, query: CallbackQuery):
    data = query.data
    
    # --- New Request Info Button ---
    if data == "request_info":
        await query.answer()
        await query.message.edit_text(
            text="🎬 To request a movie, please use the request command followed by the movie name and year.\n\n"
                 "<b>Example:</b>\n"
                 "<code>/request The Dark Knight (2008)</code>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start_menu")]]
            )
        )

    # --- Back to Start Menu ---
    elif data == "start_menu":
        # We must check if the user is an admin again to show the correct keyboard
        is_admin = query.from_user.id in ADMINS
        
        keyboard = [
            [InlineKeyboardButton("🎬 Request a Movie", callback_data="request_info")],
            [
                InlineKeyboardButton("💬 Support", url="https://t.me/YourSupportGroup"), # Replace with your URL
                InlineKeyboardButton("📣 Updates", url="https://t.me/YourUpdatesChannel")  # Replace with your URL
            ]
        ]
        if is_admin:
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_main_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_text = START_MSG.format(
            first=query.from_user.first_name,
            last=query.from_user.last_name,
            username=None if not query.from_user.username else '@' + query.from_user.username,
            mention=query.from_user.mention,
            id=query.from_user.id
        )
        await query.message.edit_text(
            text=start_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )

    # --- Close Button (if used elsewhere) ---
    elif data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass
