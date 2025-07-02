import asyncio
import os
import time
import sys
import platform  # Import the platform module
from datetime import datetime

import pyromod.listen
from pyrogram import Client, __version__ as pyrogram_version  # Import the version directly
from pyrogram.enums import ParseMode

import config

# --- Helper Function for Restart Notification ---

async def notify_admin_on_restart(bot_instance: "Bot"):
    """
    Sends a formatted notification to the primary admin when the bot restarts.
    This function is now platform-independent and more robust.
    """
    try:
        # Simplified and safer way to get the admin ID
        admin_id = bot_instance.config.ADMINS[0] if bot_instance.config.ADMINS else bot_instance.config.OWNER_ID

        if not admin_id:
            print("[WARN] No admin ID found for restart notification.")
            return
            
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Using platform.node() works on both Windows and Unix-like systems
        hostname = platform.node()

        msg = (
            f"🚀 <b>Bot Restarted Successfully</b>\n\n"
            f"<b>Time:</b> <code>{now}</code>\n"
            f"<b>Host:</b> <code>{hostname}</code>\n"
            f"<b>Python:</b> <code>{sys.version.split()[0]}</code>\n"
            f"<b>Pyrogram:</b> <code>{pyrogram_version}</code>"
        )
        
        await bot_instance.send_message(
            chat_id=admin_id, 
            text=msg
        )
        
    except Exception as e:
        print(f"[ERROR] Could not notify admin on restart: {e}")


# --- Background Task to Clean Up Stale Workspace Sessions ---

async def cleanup_stale_workspaces(bot_instance: "Bot"):
    """Periodically cleans up inactive workspace sessions and temporary files."""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        current_time = time.time()
        stale_sessions = []
        
        if not hasattr(bot_instance, 'workspace_sessions'):
            continue

        for user_id, session in list(bot_instance.workspace_sessions.items()):
            if current_time - session.get('last_active', 0) > config.SESSION_TIMEOUT:
                stale_sessions.append(user_id)
        
        for user_id in stale_sessions:
            session = bot_instance.workspace_sessions.pop(user_id, None)
            if session and 'file_path' in session and os.path.exists(session['file_path']):
                try:
                    os.remove(session['file_path'])
                    print(f"[INFO] Cleaned up stale workspace for user {user_id}")
                except Exception as e:
                    print(f"[ERROR] Could not clean up stale file for user {user_id}: {e}")


# --- ASCII Art for "HD CINEMA" ---
ascii_art = """
 __    __   _______       ______  __  .__   __.  _______ .___  ___.      ___         
|  |  |  | |       \     /      ||  | |  \ |  | |   ____||   \/   |     /   \        
|  |__|  | |  .--.  |   |  ,----'|  | |   \|  | |  |__   |  \  /  |    /  ^  \       
|   __   | |  |  |  |   |  |     |  | |  . `  | |   __|  |  |\/|  |   /  /_\  \      
|  |  |  | |  '--'  |   |  `----.|  | |  |\   | |  |____ |  |  |  |  /  _____  \     
|__|  |__| |_______/     \______||__| |__| \__| |_______||__|  |__| /__/     \__\    
"""

# --- Main Bot Class ---

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=config.API_HASH,
            api_id=config.APP_ID,
            plugins={"root": "plugins"},
            workers=config.TG_BOT_WORKERS,
            bot_token=config.TG_BOT_TOKEN
        )
        self.config = config
        self.LOGGER = config.LOGGER
        # Initialize session-related attributes here for clarity
        self.workspace_sessions = {}
        self.uptime = None
        self.db_channel = None
        self.invitelink = None

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()
        self.username = usr_bot_me.username

        if self.config.FORCE_SUB_CHANNEL:
            try:
                link = (await self.get_chat(self.config.FORCE_SUB_CHANNEL)).invite_link
                if not link:
                    link = await self.export_chat_invite_link(self.config.FORCE_SUB_CHANNEL)
                self.invitelink = link
            except Exception as a:
                self.LOGGER(__name__).warning(a)
                sys.exit(f"Bot can't get invite link from Force Sub Channel: {self.config.FORCE_SUB_CHANNEL}")
        
        try:
            db_channel = await self.get_chat(self.config.CHANNEL_ID)
            self.db_channel = db_channel
            test = await self.send_message(chat_id=db_channel.id, text="Test Message")
            await test.delete()
        except Exception as e:
            self.LOGGER(__name__).warning(e)
            sys.exit(f"Bot can't access DB Channel: {self.config.CHANNEL_ID}")

        self.set_parse_mode(ParseMode.HTML)
        self.LOGGER(__name__).info(f"Bot @{self.username} Running..!")
        print(ascii_art)
        
        # Start background tasks
        asyncio.create_task(cleanup_stale_workspaces(self))
        asyncio.create_task(notify_admin_on_restart(self))

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")
