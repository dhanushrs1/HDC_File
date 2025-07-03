"""
(©) HD Cinema Bot

This plugin handles the core callback queries for the bot's main menu navigation
and now correctly launches the admin panel.
"""

import logging
import random
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified

from bot import Bot
from config import ADMINS, START_MSG, START_PIC
from database.database import get_user_download_count

# --- FIX: Import the function to build the admin panel menu ---
from plugins.admin import build_main_menu

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- Inspirational Quotes for the Start Message ---
QUOTES = [
    "The secret of getting ahead is getting started.",
    "All our dreams can come true, if we have the courage to pursue them.",
    "The best way to predict the future is to create it.",
    "Your limitation is only your imagination.",
    "Push yourself, because no one else is going to do it for you."
]

# --- FIX: Updated regex to include the admin_main_menu callback ---
@Bot.on_callback_query(filters.regex("^(start_menu|help_info|my_stats|admin_main_menu)$"))
async def main_menu_callback_handler(client: Bot, query: CallbackQuery):
    """Handles all main navigation button presses, including the admin panel."""
    
    action = query.data
    user = query.from_user

    # --- "Help & About" / Disclaimer Page ---
    if action == "help_info":
        await query.answer()
        await query.message.edit_text(
            text=(
                "📜 <b>Disclaimer - HD Cinema Bot</b>\n\n"
                "<b>Admin-Only Access:</b>\n"
                "🔐 Only the admin can upload or manage files. Users cannot upload or share files.\n\n"
                "<b>Content Responsibility:</b>\n"
                "📁 This bot does not host or create any files. All content is sourced from the internet.\n"
                "📎 The bot simply provides access links for convenience.\n\n"
                "<b>No Piracy or Copyright Support:</b>\n"
                "🚫 We do not encourage piracy. If any file violates copyright, the original source is responsible.\n\n"
                "<b>Bot Source:</b>\n"
                "🛠 This bot’s code is private. Contact the admin for purchase inquiries.\n\n"
                "<b>Legal Use:</b>\n"
                "📌 You are responsible for how you use the provided links/files.\n\n"
                "<b>Contact Admin:</b> @FilmySpotSupport_bot"
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start_menu")]]
            )
        )

    # --- "My Stats" Page ---
    elif action == "my_stats":
        await query.answer("Fetching your stats...", show_alert=False)
        download_count = await get_user_download_count(user.id)
        await query.message.edit_text(
            text=f"📊 <b>Your Personal Stats</b>\n\n"
                 f"Hello {user.mention}!\n\n"
                 f"You have downloaded a total of <b>{download_count}</b> files from me.\n\n"
                 "Keep exploring!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start_menu")]]
            )
        )

    # --- "Back to Main Menu" Action ---
    elif action == "start_menu":
        await query.answer()
        
        # --- FIX: Removed the "Request Content" button ---
        keyboard = [
            [
                InlineKeyboardButton("❓ Help & About", callback_data="help_info"),
                InlineKeyboardButton("📊 My Stats", callback_data="my_stats")
            ],
            [
                InlineKeyboardButton("💬 Support", url="https://t.me/YourSupportGroup"),
                InlineKeyboardButton("📣 Updates", url="https://t.me/YourUpdatesChannel")
            ]
        ]
        if user.id in ADMINS:
            # The button is still added here, but now the handler will catch it.
            keyboard.insert(0, [InlineKeyboardButton("👑 Admin Panel", callback_data="admin_action_refresh")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_text = (
            f"👋 Hello {user.mention}!\n\n"
            f"{START_MSG}\n\n"
            f"<i>\"{random.choice(QUOTES)}\"</i>"
        )
        
        try:
            if START_PIC and query.message.photo:
                await query.message.edit_caption(caption=start_text, reply_markup=reply_markup)
            else:
                await query.message.edit_text(
                    text=start_text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
        except MessageNotModified:
            pass # Ignore if the message is already the same

    # --- FIX: New handler for the Admin Panel button ---
    elif action == "admin_main_menu":
        if user.id not in ADMINS:
            return await query.answer("This is an admin-only area.", show_alert=True)
        
        await query.answer()
        text, keyboard = await build_main_menu(client)
        await query.message.edit_text(text, reply_markup=keyboard)