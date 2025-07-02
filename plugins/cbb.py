"""
(©) HD Cinema Bot

This plugin handles the core callback queries for the bot's main menu navigation.
- start_menu: Returns the user to the main start menu.
- request_info: Shows the user how to properly format a /request.
- help_info: Provides a detailed help and about message.
- my_stats: Shows a user their personal download statistics.
"""

import logging
import random
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import Bot
from config import ADMINS, START_MSG, START_PIC
from database.database import get_user_download_count

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

@Bot.on_callback_query(filters.regex("^(start_menu|request_info|help_info|my_stats)$"))
async def main_menu_callback_handler(client: Bot, query: CallbackQuery):
    """Handles all main navigation button presses."""
    
    action = query.data
    user = query.from_user

    # --- "Request Content" Info Page ---
    if action == "request_info":
        await query.answer()
        await query.message.edit_text(
            text="🎬 <b>How to Request Content</b>\n\n"
                 "To request a movie or show, please use the <code>/request</code> command followed by the title and year.\n\n"
                 "<b>Example:</b>\n"
                 "<code>/request The Dark Knight (2008)</code>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start_menu")]]
            )
        )

    # --- "Help & About" Page ---
    elif action == "help_info":
        await query.answer()
        await query.message.edit_text(
            text="❓ <b>Help & About</b>\n\n"
                 "Welcome to the <b>HD Cinema Bot</b>! I am designed to provide you with permanent, secure links to files.\n\n"
                 "<b>How it works:</b>\n"
                 "1. You click a special link.\n"
                 "2. I will send you the corresponding file directly.\n"
                 "3. You can request new content using the <code>/request</code> command.\n\n"
                 "If you encounter any issues, please contact our support group.",
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
                 f"You have requested a total of <b>{download_count}</b> files from me.\n\n"
                 "Keep exploring!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start_menu")]]
            )
        )

    # --- "Back to Main Menu" Action ---
    elif action == "start_menu":
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("🎬 Request Content", callback_data="request_info")],
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
            keyboard.insert(0, [InlineKeyboardButton("👑 Admin Panel", callback_data="admin_main_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_text = (
            f"👋 Hello {user.mention}!\n\n"
            f"{START_MSG}\n\n"
            f"<i>\"{random.choice(QUOTES)}\"</i>"
        )
        
        if START_PIC and query.message.photo:
            await query.message.edit_caption(caption=start_text, reply_markup=reply_markup)
        else:
            await query.message.edit_text(
                text=start_text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
