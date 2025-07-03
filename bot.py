"""
(©) HD Cinema Bot

This file defines the main Bot class, which inherits from pyrogram.Client.
It handles the bot's startup, shutdown, and initialization of core components.
"""

import asyncio
import sys
import platform
from datetime import datetime

from pyrogram import Client, __version__ as pyrogram_version
from pyrogram.enums import ParseMode

# Import our custom configuration
import config

# --- Unique Startup Banner ---
ASCII_ART = """
╔══════════════════════════════════════════════════════════╗
║        🎬 HD CINEMA BOT - FileShareX 🎬                ║
║  Your Ultimate Telegram File & Movie Indexing Partner   ║
║  Fast • Secure • Reliable • Powered by Pyrogram+MongoDB ║
╚══════════════════════════════════════════════════════════╝
"""

class Bot(Client):
    """
    The main Bot class for the HD Cinema application.
    
    This class handles:
    - Initialization with settings from config.py.
    - Graceful startup and shutdown procedures.
    - Verification of essential channels and settings.
    - Running background tasks.
    """
    def __init__(self):
        # Initialize the Pyrogram Client
        super().__init__(
            name="HD_Cinema_Bot",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.TG_BOT_TOKEN,
            workers=config.TG_BOT_WORKERS,
            plugins={"root": "plugins"}
        )
        
        # --- Initialize Bot Attributes ---
        self.config = config
        self.LOGGER = config.LOGGER
        self.uptime: datetime = None
        self.db_channel = None
        self.invitelink = None
        self.workspace_sessions = {} # For the video processing workspace

    async def start(self):
        """
        Starts the bot, verifies connections, and launches background tasks.
        """
        await super().start()
        self.uptime = datetime.now()
        
        # Get bot's own information
        usr_bot_me = await self.get_me()
        self.username = usr_bot_me.username
        self.set_parse_mode(ParseMode.HTML)
        
        self.LOGGER(__name__).info(f"Pyrogram v{pyrogram_version} running.")
        self.LOGGER(__name__).info(f"Bot @{self.username} is starting...")
        print(ASCII_ART)

        # --- Verify Database Channel ---
        try:
            self.db_channel = await self.get_chat(self.config.CHANNEL_ID)
            # Send and delete a test message to confirm write permissions
            test_msg = await self.send_message(chat_id=self.db_channel.id, text="<code>Bot is online.</code>")
            await test_msg.delete()
            self.LOGGER(__name__).info(f"Successfully connected to DB Channel: {self.db_channel.title}")
        except Exception as e:
            self.LOGGER(__name__).critical(f"FATAL: Bot can't access DB Channel ({self.config.CHANNEL_ID}). Error: {e}")
            sys.exit("Bot cannot access the specified database channel. Please check the CHANNEL_ID and bot permissions.")

        # --- Handle Force Subscribe Channel ---
        if self.config.FORCE_SUB_CHANNEL:
            try:
                # Try to get an existing invite link first
                chat = await self.get_chat(self.config.FORCE_SUB_CHANNEL)
                self.invitelink = chat.invite_link
                if not self.invitelink:
                    # If no link exists, create one
                    self.invitelink = await self.export_chat_invite_link(self.config.FORCE_SUB_CHANNEL)
                self.LOGGER(__name__).info(f"Force Subscribe is enabled for: {chat.title}")
            except Exception as e:
                self.LOGGER(__name__).error(f"Could not get invite link for Force Sub Channel ({self.config.FORCE_SUB_CHANNEL}). Error: {e}")
                self.LOGGER(__name__).error("Disabling Force Subscribe due to the error above.")
                self.config.FORCE_SUB_CHANNEL = 0 # Disable if there's an issue

        # --- Start Background Tasks ---
        asyncio.create_task(self.notify_admin_on_restart())
        
        # FIXED: Removed the emoji from the log message to prevent UnicodeEncodeError on Windows
        self.LOGGER(__name__).info(f"Bot @{self.username} is now online and ready!")

    async def stop(self, *args):
        """Gracefully stops the bot."""
        self.LOGGER(__name__).info("Bot is stopping...")
        await super().stop()
        self.LOGGER(__name__).info("Bot has stopped.")

    async def notify_admin_on_restart(self):
        """Sends a formatted notification to the owner when the bot restarts."""
        try:
            if not self.config.OWNER_ID:
                self.LOGGER(__name__).warning("No OWNER_ID found for restart notification.")
                return
            
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            msg = (
                f"🎬 <b>HD Cinema Bot Restarted</b>\n\n"
                f"<b>Time:</b> <code>{now}</code>\n"
                f"<b>Host:</b> <code>{platform.node()}</code>\n"
                f"<b>Python:</b> <code>{sys.version.split()[0]}</code>\n"
                f"<b>Pyrogram:</b> <code>{pyrogram_version}</code>\n"
                f"<b>Status:</b> <code>Online & Ready!</code>"
            )
            
            await self.send_message(chat_id=self.config.OWNER_ID, text=msg)
            
        except Exception as e:
            self.LOGGER(__name__).error(f"Admin restart notification failed: {e}")
            self.LOGGER(__name__).error(f"Admin restart notification failed: {e}")
