import asyncio
import os
import time
from aiohttp import web
from plugins import web_server

import pyromod.listen
from pyrogram import Client
from pyrogram.enums import ParseMode
import sys
from datetime import datetime
from threading import Thread

import config

# --- Background task to clean up inactive/stale workspace sessions ---
async def cleanup_stale_workspaces(bot_instance):
    while True:
        # Check every 5 minutes
        await asyncio.sleep(300)
        current_time = time.time()
        stale_sessions = []
        
        # Safely iterate over a copy of the items
        for user_id, session in list(bot_instance.workspace_sessions.items()):
            # Check if the session has been inactive for longer than the timeout
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
        # The bot itself now holds the session data
        self.workspace_sessions = {}

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()

        if self.config.FORCE_SUB_CHANNEL:
            try:
                link = (await self.get_chat(self.config.FORCE_SUB_CHANNEL)).invite_link
                if not link:
                    await self.export_chat_invite_link(self.config.FORCE_SUB_CHANNEL)
                    link = (await self.get_chat(self.config.FORCE_SUB_CHANNEL)).invite_link
                self.invitelink = link
            except Exception as a:
                self.LOGGER(__name__).warning(a)
                sys.exit(f"Bot can't get invite link from Force Sub Channel: {self.config.FORCE_SUB_CHANNEL}")
        
        try:
            db_channel = await self.get_chat(self.config.CHANNEL_ID)
            self.db_channel = db_channel
            test = await self.send_message(chat_id = db_channel.id, text = "Test Message")
            await test.delete()
        except Exception as e:
            self.LOGGER(__name__).warning(e)
            sys.exit(f"Bot can't access DB Channel: {self.config.CHANNEL_ID}")

        self.set_parse_mode(ParseMode.HTML)
        self.LOGGER(__name__).info(f"Bot Running..!")
        print(ascii_art)
        print("""Welcome to HD Cinema Bot""")
        self.username = usr_bot_me.username
        
        # Start the background task to clean up stale sessions
        asyncio.create_task(cleanup_stale_workspaces(self))
        
        # The user-facing web server is currently disabled.
        # app = web.AppRunner(await web_server())
        # await app.setup()
        # bind_address = "0.0.0.0"
        # await web.TCPSite(app, bind_address, self.config.PORT).start()

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")
