# In plugins/search.py

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import ADMINS
from database.database import get_user, search_indexed_files
from helper_func import encode, get_readable_time
import math

def get_file_size_str(size_bytes):
    if size_bytes == 0: return ""
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

@Bot.on_message(filters.private & filters.command("search") & filters.user(ADMINS))
async def search_handler(client: Bot, message: Message):
    # Command usage: /search user <id or username> OR /search file <keyword>
    if len(message.command) < 3:
        await message.reply_text(
            "<b>Invalid Search Format</b>\n\n"
            "Please use one of the following formats:\n"
            "» <code>/search user &lt;user_id or @username&gt;</code>\n"
            "» <code>/search file &lt;keyword&gt;</code>"
        )
        return

    search_type = message.command[1].lower()
    query = " ".join(message.command[2:])

    if search_type == "user":
        # --- User Search Logic ---
        await message.reply_text(f"Searching for user: <code>{query}</code>")
        try:
            user = await client.get_users(query)
        except Exception:
            await message.reply_text("❌ Could not find a user with that ID or username.")
            return

        user_db_info = await get_user(user.id)
        
        status = "Not in DB"
        if user_db_info:
            if user_db_info.get('banned', False):
                status = "Banned 🚫"
            else:
                status = "Active ✅"
        
        is_admin = "Yes 👑" if user.id in ADMINS else "No"

        user_details = (
            f"👤 <b>User Details:</b>\n\n"
            f" • <b>Name:</b> {user.mention}\n"
            f" • <b>User ID:</b> <code>{user.id}</code>\n"
            f" • <b>Username:</b> @{user.username if user.username else 'N/A'}\n"
            f" • <b>Bot Status:</b> {status}\n"
            f" • <b>Admin:</b> {is_admin}"
        )
        await message.reply_text(user_details, disable_web_page_preview=True)

    elif search_type == "file":
        # --- File Search Logic (Using local index) ---
        await message.reply_text(f"Searching my index for files matching: <code>{query}</code>")
        
        results = await search_indexed_files(query, limit=15)
        
        if not results:
            await message.reply_text("No files found in my index matching your query. To build the index, use `/start_indexing` and forward files to me.")
            return

        found_files_text = f"🔎 <b>Search Results for '{query}':</b>\n\n"
        for i, doc in enumerate(results):
            file_id = doc['_id']
            file_name = doc['file_name']
            
            # Create a shareable link for each file
            converted_id = file_id * abs(client.db_channel.id)
            string = f"get-{converted_id}"
            base64_string = await encode(string)
            link = f"{client.config.REDIRECT_URL}?start={base64_string}"

            found_files_text += f"<b>{i+1}.</b> <code>{file_name}</code>\n[Get Link]({link})\n\n"
        
        await message.reply_text(found_files_text, disable_web_page_preview=True)

    else:
        await message.reply_text("Invalid search type. Use 'user' or 'file'.")
