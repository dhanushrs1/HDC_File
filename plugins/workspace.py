import asyncio
import cv2
import math
import os
import random
import time
import ffmpeg
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, InputMediaVideo
from pyrogram.errors import MessageNotModified

from bot import Bot
from config import ADMINS
from helper_func import get_readable_time

# --- In-memory storage for active workspace sessions ---
WORKSPACE_SESSIONS = {}
SESSION_TIMEOUT_SECONDS = 1800

# --- Helper Functions ---
def get_file_size_str(size_bytes):
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def format_timestamp_for_display(seconds):
    return time.strftime('%H:%M:%S', time.gmtime(seconds))

# --- UI Helper: Shows the main workspace menu ---
async def show_main_workspace_menu(message: Message, video_message: Message, text_prefix=""):
    file_name = getattr(video_message.video, 'file_name', getattr(video_message.document, 'file_name', 'Unknown File'))
    main_menu_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Take Screenshots (Random)", callback_data=f"ws_ss_menu_random_{video_message.id}")],
        [InlineKeyboardButton("📸 Take Screenshots (Manual)", callback_data=f"ws_ss_menu_manual_{video_message.id}")],
        [InlineKeyboardButton("✂️ Generate Clip", callback_data=f"ws_clip_menu_{video_message.id}")],
        [InlineKeyboardButton("✅ Done & Delete Original Video", callback_data=f"ws_cleanup_{video_message.id}")]
    ])
    try:
        main_text = f"<b>Video Workspace</b>\n\n<b>File:</b> <code>{file_name}</code>\n\nWhat would you like to do?"
        if text_prefix:
            main_text = f"{text_prefix}\n{main_text}"
        await message.edit_text(main_text, reply_markup=main_menu_markup)
    except MessageNotModified:
        pass

# --- Entry Point: /process command ---
@Bot.on_message(filters.private & filters.command("process") & filters.user(ADMINS))
async def process_command_handler(client: Bot, message: Message):
    try:
        video_message = await client.ask(
            chat_id=message.chat.id,
            text="Please send the video file you want to work on...",
            filters=filters.video | filters.document,
            timeout=300
        )
    except asyncio.TimeoutError:
        await message.reply_text("Request timed out.")
        return
    if not (video_message.video or (getattr(video_message.document, 'mime_type', '').startswith('video/'))):
        await message.reply_text("This is not a valid video file.")
        return
    await show_main_workspace_menu(await video_message.reply_text("Creating workspace..."), video_message)

# --- Central Callback Handler ---
@Bot.on_callback_query(filters.regex("^ws_"))
async def workspace_callback_handler(client: Bot, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data.split("_")
    action = data[1]
    original_msg_id = int(data[-1])

    try:
        video_message = await client.get_messages(user_id, original_msg_id)
    except Exception:
        await query.message.edit_text("❌ <b>Error:</b> The original video message is inaccessible.")
        return

    if action == "main":
        await show_main_workspace_menu(query.message, video_message)
    elif action == "ss":
        if data[2] == "menu":
            sub_action = data[3]
            if sub_action == "random":
                keyboard = [[InlineKeyboardButton(f"{n}", callback_data=f"ws_ss_take_random_{n}_{original_msg_id}") for n in [2, 4, 6, 10, 15]],
                            [InlineKeyboardButton("⬅️ Back", callback_data=f"ws_main_menu_{original_msg_id}")]]
                await query.message.edit_text("How many <b>random</b> screenshots would you like?", reply_markup=InlineKeyboardMarkup(keyboard))
            elif sub_action == "manual":
                back_button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Workspace", callback_data=f"ws_main_menu_{original_msg_id}")]])
                await query.message.edit_text("Please reply to this message with the timestamps, separated by commas.\n\n<b>Example:</b> <code>00:01:30, 00:45:10</code>", reply_markup=back_button_markup)
        elif data[2] == "take" and data[3] == "random":
            num_screenshots = int(data[4])
            await query.answer(f"✅ Task accepted! Generating {num_screenshots} screenshots...", show_alert=False)
            asyncio.create_task(run_process_and_notify(client, query, video_message, screenshot_job={'count': num_screenshots, 'timestamps': None}))
    elif action == "clip":
        back_button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Workspace", callback_data=f"ws_main_menu_{original_msg_id}")]])
        await query.message.edit_text("Please reply to this message with the clip details in the format: <code>start_time duration</code>\n\n<b>Example:</b> <code>00:01:30 15</code>", reply_markup=back_button_markup)
    elif action == "cleanup":
        session = client.workspace_sessions.pop(user_id, None)
        if session and session['msg_id'] == original_msg_id and os.path.exists(session['file_path']):
            try:
                os.remove(session['file_path'])
            except Exception as e:
                print(f"Cleanup Error: Could not delete session file. {e}")
        await video_message.delete()
        await query.message.edit_text("✅ <b>Session Closed & All Files Deleted.</b>\nOriginal video and all temporary files have been permanently removed from the server and your chat.")
    await query.answer()

# --- Text handler for details ---
@Bot.on_message(filters.private & filters.reply & filters.user(ADMINS))
async def details_handler(client: Bot, message: Message):
    if not message.reply_to_message or not message.reply_to_message.text: return
    workspace_msg = message.reply_to_message
    original_msg_id = int(workspace_msg.reply_markup.inline_keyboard[0][0].callback_data.split("_")[-1])
    video_message = await client.get_messages(message.chat.id, original_msg_id)

    if "clip details" in workspace_msg.text:
        try:
            start_time, duration_str = message.text.split(" ", 1)
            duration_sec = int(duration_str)
            if duration_sec > 60:
                await message.reply_text("Maximum clip duration is 60 seconds.")
                return
        except Exception:
            await message.reply_text("<b>Invalid format.</b> Reply with <code>start_time duration</code> (e.g., <code>00:01:30 15</code>)")
            return
        await message.delete()
        clip_job = {"start_time": start_time, "duration": duration_sec}
        asyncio.create_task(run_process_and_notify(client, workspace_msg, video_message, clip_job=clip_job))
    elif "timestamps" in workspace_msg.text:
        timestamps = [ts.strip() for ts in message.text.split(',')]
        await message.delete()
        screenshot_job = {'count': 0, 'timestamps': timestamps}
        asyncio.create_task(run_process_and_notify(client, workspace_msg, video_message, screenshot_job=screenshot_job))

# --- The Main Backend Processing Function ---
async def run_process_and_notify(client: Bot, trigger, video_message: Message, screenshot_job=None, clip_job=None):
    user_id = trigger.from_user.id
    status_message = trigger if isinstance(trigger, Message) else trigger.message
    
    target_chat_id = client.config.OWNER_ID if user_id == client.me.id else user_id
    session = client.workspace_sessions.get(user_id)
    temp_dir = "temp_downloads/"
    os.makedirs(temp_dir, exist_ok=True)
    generated_media_paths = []

    status_update_msg = None
    file_path = ""
    cap = None

    try:
        # --- FIX: Download file ONCE per session ---
        if not session or session.get('msg_id') != video_message.id or not os.path.exists(session.get('file_path', '')):
            status_update_msg = await client.send_message(target_chat_id, "<code>Step 1/4:</code> <b>Downloading video for session...</b>")
            file_path = os.path.join(temp_dir, f"{video_message.id}.mp4")
            
            start_download_time = time.time()
            last_update_time = time.time()
            async def progress(current, total):
                nonlocal last_update_time
                current_time = time.time()
                if current_time - last_update_time > 2:
                    elapsed_time = current_time - start_download_time
                    speed = current / elapsed_time if elapsed_time > 0 else 0
                    speed_str = f"{get_file_size_str(speed)}/s"
                    percentage = current * 100 / total
                    eta_seconds = (total - current) / speed if speed > 0 else 0
                    eta_str = get_readable_time(int(eta_seconds))
                    try:
                        await status_update_msg.edit_text(f"<code>Step 1/4:</code> <b>Downloading...</b>\n\n<b>Progress:</b> <code>{percentage:.1f}%</code> | <b>ETA:</b> <code>{eta_str}</code>")
                    except MessageNotModified: pass
                    last_update_time = current_time
            
            await client.download_media(video_message, file_name=file_path, progress=progress)
            client.workspace_sessions[user_id] = {"msg_id": video_message.id, "file_path": file_path, "last_active": time.time()}
        else:
            status_update_msg = await client.send_message(target_chat_id, "<b>Using cached video from current session...</b>")
            file_path = session['file_path']
            client.workspace_sessions[user_id]['last_active'] = time.time()
        
        await status_update_msg.edit_text("<code>Step 2/4:</code> <b>Processing video...</b>")
        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0: raise ValueError("Could not read video properties (FPS is zero).")

        generated_media = []
        if screenshot_job:
            frames_to_capture = []
            if screenshot_job.get('timestamps'):
                for ts in screenshot_job['timestamps']:
                    time_parts = list(map(int, ts.split(':')))
                    while len(time_parts) < 3: time_parts.insert(0, 0)
                    h, m, s = time_parts
                    frame_num = int((h * 3600 + m * 60 + s) * fps)
                    if 0 <= frame_num < cap.get(cv2.CAP_PROP_FRAME_COUNT): frames_to_capture.append(frame_num)
            else: # Random screenshots
                frames_to_capture = sorted(random.sample(range(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))), min(screenshot_job['count'], int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))))
            
            watermark_text = client.config.SCREENSHOT_WATERMARK
            font_scale = client.config.SCREENSHOT_FONT_SCALE
            for i, frame_num in enumerate(frames_to_capture):
                await status_update_msg.edit_text(f"<code>Step 2/4:</code> <b>Generating screenshot {i+1} of {len(frames_to_capture)}...</b>")
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if ret:
                    timestamp_display = format_timestamp_for_display(frame_num / fps)
                    # Apply a smaller font scale for timestamp and watermark
                    cv2.putText(frame, timestamp_display, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, (font_scale * 0.8), (0, 0, 0), 6, cv2.LINE_AA)
                    cv2.putText(frame, timestamp_display, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, (font_scale * 0.8), (255, 255, 255), 2, cv2.LINE_AA)
                    if watermark_text:
                        (w, h), _ = cv2.getTextSize(watermark_text, cv2.FONT_HERSHEY_SIMPLEX, (font_scale * 0.6), 2)
                        cv2.putText(frame, watermark_text, (frame.shape[1] - w - 15, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, (font_scale * 0.6), (0, 0, 0), 6, cv2.LINE_AA)
                        cv2.putText(frame, watermark_text, (frame.shape[1] - w - 15, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, (font_scale * 0.6), (255, 255, 255), 2, cv2.LINE_AA)
                    ss_path = os.path.join(temp_dir, f"ss_{i+1}_{video_message.id}.jpg")
                    cv2.imwrite(ss_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    generated_media.append(InputMediaPhoto(ss_path))
                    generated_media_paths.append(ss_path)
            
        if clip_job:
            await status_update_msg.edit_text("<code>Step 2/4:</code> <b>Generating video clip...</b>")
            clip_path = os.path.join(temp_dir, f"clip_{int(time.time())}.mp4")
            (
                ffmpeg.input(file_path, ss=clip_job['start_time'])
                .output(clip_path, t=clip_job['duration'], vcodec='libx264', acodec='copy')
                .run(quiet=True, overwrite_output=True)
            )
            generated_media.append(InputMediaVideo(clip_path, caption=f"Clip: {clip_job['start_time']} for {clip_job['duration']}s"))
            generated_media_paths.append(clip_path)

        if not generated_media: raise ValueError("Failed to generate any media.")
            
        await status_update_msg.edit_text(f"<code>Step 3/4:</code> <b>Uploading {len(generated_media)} items...</b>")
        media_group_chunks = [generated_media[i:i + 10] for i in range(0, len(generated_media), 10)]
        for chunk in media_group_chunks:
            await client.send_media_group(target_chat_id, media=chunk)
        
        await status_update_msg.delete()
        await show_main_workspace_menu(status_message, video_message, text_prefix="✅ <b>Task Complete!</b>\n\n")

    except Exception as e:
        error_text = f"❌ <b>An error occurred:</b>\n<code>{e}</code>"
        if status_update_msg:
            await status_update_msg.edit_text(error_text)
        else:
            await client.send_message(target_chat_id, error_text)
    finally:
        # --- ROBUST CLEANUP ---
        if cap is not None:
            cap.release()
        
        for path in generated_media_paths:
            if os.path.exists(path):
                os.remove(path)
