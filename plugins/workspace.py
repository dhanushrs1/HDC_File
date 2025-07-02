"""
(©) HD Cinema Bot

This plugin provides the /process command for the Video Workspace,
allowing admins to generate screenshots and clips from video files.
This is a complete, rewritten version with a redesigned UI and full functionality.
"""

import asyncio
import cv2
import math
import os
import random
import time
import ffmpeg
import logging
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, InputMediaVideo
from pyrogram.errors import MessageNotModified

from bot import Bot
from config import ADMINS, TEMP_DIR, SCREENSHOT_WATERMARK
from helper_func import get_readable_time, format_bytes
from plugins.linker import CONVERSATION_STATE # Import the state manager

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- In-memory storage for active workspace sessions ---
WORKSPACE_SESSIONS = {}

# ======================================================================================
#                              *** UI & Core Logic ***
# ======================================================================================

def get_session_info_text(session: dict) -> str:
    """Generates the main text for the workspace menu with the new UI."""
    file_name = session.get('file_name', 'Unknown File')
    file_size = format_bytes(session.get('file_size', 0))
    duration = get_readable_time(session.get('duration', 0))

    return (
        f"🎬 <b>Workspace Initialized</b>\n\n"
        f"📁 <b>File:</b> <code>{file_name}</code>\n"
        f"📦 <b>Size:</b> <code>{file_size}</code> | 🕒 <b>Duration:</b> <code>{duration}</code>\n\n"
        "📌 Select a task below to get started ⬇️"
    )

def get_main_workspace_markup(msg_id: int) -> InlineKeyboardMarkup:
    """Generates the main keyboard for the workspace with the new compact layout."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 Screenshots", callback_data=f"ws|menu|ss|{msg_id}"),
            InlineKeyboardButton("✂️ Clip", callback_data=f"ws|menu|clip|{msg_id}")
        ],
        [InlineKeyboardButton("🗑️ Close Session", callback_data=f"ws|menu|cleanup|{msg_id}")]
    ])

def parse_callback_data(data: str) -> dict:
    """Parses the new callback data format."""
    parts = data.split("|")
    return {
        "type": parts[0],
        "action": parts[1],
        "subaction": parts[2],
        "msg_id": int(parts[3]),
        "value": parts[4] if len(parts) > 4 else None
    }

# ======================================================================================
#                              *** Command & Message Handlers ***
# ======================================================================================

@Bot.on_message(filters.private & filters.command("process") & filters.user(ADMINS))
async def process_command_handler(client: Bot, message: Message):
    """Entry point for the /process command. Sets the user's state."""
    user_id = message.from_user.id
    
    if user_id in WORKSPACE_SESSIONS:
        session = WORKSPACE_SESSIONS.pop(user_id, None)
        if session and 'file_path' in session and os.path.exists(session['file_path']):
            try: os.remove(session['file_path'])
            except Exception as e: logger.error(f"Cleanup Error: Could not delete previous session file for {user_id}. {e}")

    CONVERSATION_STATE[user_id] = 'awaiting_process_video'
    await message.reply_text("➡️ Please send the video file you want to work on...")

@Bot.on_message(filters.private & (filters.video | filters.document) & filters.user(ADMINS))
async def workspace_video_handler(client: Bot, message: Message):
    """Catches the video sent ONLY after the /process command has been used."""
    user_id = message.from_user.id
    if CONVERSATION_STATE.get(user_id) != 'awaiting_process_video':
        return

    CONVERSATION_STATE.pop(user_id, None)

    if not (message.video or (getattr(message.document, 'mime_type', '').startswith('video/'))):
        return await message.reply_text("This is not a valid video file.")
    
    video = message.video or message.document
    WORKSPACE_SESSIONS[user_id] = {
        'msg_id': message.id,
        'file_name': getattr(video, 'file_name', f"File_{message.id}"),
        'file_size': getattr(video, 'file_size', 0),
        'duration': getattr(video, 'duration', 0) or 0,
        'file_path': None,
        'last_active': time.time()
    }
    
    text = get_session_info_text(WORKSPACE_SESSIONS[user_id])
    markup = get_main_workspace_markup(message.id)
    await message.reply_text(text, reply_markup=markup, quote=True)

# ======================================================================================
#                              *** Callback & Backend Logic ***
# ======================================================================================

@Bot.on_callback_query(filters.regex("^ws|") & filters.user(ADMINS))
async def workspace_callback_handler(client: Bot, query: CallbackQuery):
    """Handles all button presses within the workspace using the new data format."""
    user_id = query.from_user.id
    data = parse_callback_data(query.data)
    msg_id = data['msg_id']

    if user_id not in WORKSPACE_SESSIONS or WORKSPACE_SESSIONS[user_id]['msg_id'] != msg_id:
        return await query.answer("This workspace session has expired. Please start a new one with /process.", show_alert=True)
    
    session = WORKSPACE_SESSIONS[user_id]
    session['last_active'] = time.time()

    action = data['action']
    subaction = data['subaction']

    if action == "main": # Return to main menu
        await query.answer()
        text = get_session_info_text(session)
        markup = get_main_workspace_markup(msg_id)
        await query.message.edit_text(text, reply_markup=markup)

    elif action == "menu": # Main menu options
        if subaction == "ss":
            keyboard = [[InlineKeyboardButton("🎲 Auto (Random)", callback_data=f"ws|ss|random|{msg_id}")], [InlineKeyboardButton("🕓 Manual (Timestamps)", callback_data=f"ws|ss|manual|{msg_id}")], [InlineKeyboardButton("⬅️ Back", callback_data=f"ws|main|menu|{msg_id}")]]
            await query.message.edit_text("<b>📸 Screenshot Options</b>", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif subaction == "clip":
            keyboard = [[InlineKeyboardButton("🎲 Auto (Random)", callback_data=f"ws|clip|random|{msg_id}")], [InlineKeyboardButton("🕓 Manual (Timestamp)", callback_data=f"ws|clip|manual|{msg_id}")], [InlineKeyboardButton("⬅️ Back", callback_data=f"ws|main|menu|{msg_id}")]]
            await query.message.edit_text("<b>✂️ Clip Generation Options</b>", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif subaction == "cleanup":
            await query.answer("Closing session...", show_alert=False)
            if session and session.get('file_path') and os.path.exists(session['file_path']):
                try: os.remove(session['file_path'])
                except Exception as e: logger.error(f"Cleanup Error: Could not delete session file for user {user_id}: {e}")
            WORKSPACE_SESSIONS.pop(user_id, None)
            await query.message.edit_text("🗑️ <b>Workspace Closed</b>\nAll temporary files have been removed.")

    elif action == "ss": # Screenshot actions
        if subaction == "random":
            keyboard = [
                [InlineKeyboardButton("4 🖼️", callback_data=f"ws|ss|take_random|{msg_id}|4"), InlineKeyboardButton("8 🖼️", callback_data=f"ws|ss|take_random|{msg_id}|8")],
                [InlineKeyboardButton("12 🖼️", callback_data=f"ws|ss|take_random|{msg_id}|12"), InlineKeyboardButton("16 🖼️", callback_data=f"ws|ss|take_random|{msg_id}|16")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"ws|menu|ss|{msg_id}")]
            ]
            await query.message.edit_text("How many <b>random</b> screenshots would you like?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif subaction == "manual":
            CONVERSATION_STATE[user_id] = 'awaiting_ss_timestamps'
            await query.message.edit_text("📝 <b>Send Timestamps</b>\n\nReply with timestamps separated by commas.\n<b>Example:</b> <code>00:01:30, 00:45:10</code>")
            
        elif subaction == "take_random":
            num_screenshots = int(data['value'])
            await query.answer(f"✅ Task accepted! Generating {num_screenshots} screenshots...", show_alert=False)
            await query.message.delete()
            asyncio.create_task(run_process_and_notify(client, user_id, screenshot_job={'count': num_screenshots}))

    elif action == "clip": # Clip actions
        if subaction == "random":
            keyboard = [
                [InlineKeyboardButton("15s", callback_data=f"ws|clip|take_random|{msg_id}|15"), InlineKeyboardButton("30s", callback_data=f"ws|clip|take_random|{msg_id}|30")],
                [InlineKeyboardButton("45s", callback_data=f"ws|clip|take_random|{msg_id}|45"), InlineKeyboardButton("60s", callback_data=f"ws|clip|take_random|{msg_id}|60")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"ws|menu|clip|{msg_id}")]
            ]
            await query.message.edit_text("Select a <b>random</b> clip duration:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif subaction == "manual":
            CONVERSATION_STATE[user_id] = 'awaiting_clip_details'
            await query.message.edit_text("📝 <b>Send Clip Details</b>\n\nReply like: <code>00:01:30 20</code> to clip 20s from 1m30s.\n(Max duration: 60s)")
        
        elif subaction == "take_random":
            duration = int(data['value'])
            await query.answer(f"✅ Task accepted! Generating a random {duration}s clip...", show_alert=False)
            await query.message.delete()
            asyncio.create_task(run_process_and_notify(client, user_id, clip_job={'duration': duration, 'random': True}))

@Bot.on_message(filters.private & filters.text & filters.user(ADMINS), group=0)
async def details_handler(client: Bot, message: Message):
    """Handles text replies from the admin for timestamps or clip details."""
    user_id = message.from_user.id
    state = CONVERSATION_STATE.get(user_id)
    
    if not state or state not in ['awaiting_clip_details', 'awaiting_ss_timestamps']:
        return

    CONVERSATION_STATE.pop(user_id, None)
    
    if state == 'awaiting_clip_details':
        try:
            start_time, duration_str = message.text.split(" ", 1)
            duration_sec = int(duration_str)
            if duration_sec > 60: return await message.reply_text("Maximum clip duration is 60 seconds. Please try again.")
        except Exception: return await message.reply_text("<b>Invalid format.</b> Reply with <code>start_time duration</code> (e.g., <code>00:01:30 15</code>)")
        
        await message.delete()
        asyncio.create_task(run_process_and_notify(client, user_id, clip_job={"start_time": start_time, "duration": duration_sec, "random": False}))

    elif state == 'awaiting_ss_timestamps':
        timestamps = [ts.strip() for ts in message.text.split(',')]
        await message.delete()
        asyncio.create_task(run_process_and_notify(client, user_id, screenshot_job={'count': 0, 'timestamps': timestamps}))

async def run_process_and_notify(client: Bot, user_id: int, screenshot_job=None, clip_job=None):
    """The main backend processing function."""
    if user_id not in WORKSPACE_SESSIONS:
        return await client.send_message(user_id, "❌ Error: Your workspace session was not found. It might have timed out.")
    
    session = WORKSPACE_SESSIONS[user_id]
    video_message_id = session['msg_id']
    
    status_update_msg = None
    generated_media_paths = []

    try:
        if not session.get('file_path') or not os.path.exists(session.get('file_path')):
            status_update_msg = await client.send_message(user_id, "📥 <b>Starting download...</b>")
            video_message = await client.get_messages(user_id, video_message_id)
            file_path = os.path.join(TEMP_DIR, f"{video_message.id}.mp4")
            os.makedirs(TEMP_DIR, exist_ok=True)
            
            start_download_time = time.time()
            
            async def progress(current, total):
                try:
                    now = time.time()
                    elapsed = now - start_download_time
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0
                    
                    progress_str = (
                        f"<b>Downloading Video...</b>\n\n"
                        f"<b>Progress:</b> {current * 100 / total:.1f}%\n"
                        f"<b>Speed:</b> {format_bytes(speed)}/s\n"
                        f"<b>Downloaded:</b> {format_bytes(current)} / {format_bytes(total)}\n"
                        f"<b>ETA:</b> {get_readable_time(int(eta))}"
                    )
                    
                    await status_update_msg.edit_text(progress_str)
                except MessageNotModified:
                    pass
            
            await client.download_media(video_message, file_name=file_path, progress=progress)
            session['file_path'] = file_path
        else:
            status_update_msg = await client.send_message(user_id, "<b>Using cached video from current session...</b>")
            file_path = session['file_path']
        
        session['last_active'] = time.time()
        
        await status_update_msg.edit_text("<code>Processing video... This may take a moment.</code>")
        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
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
                    if 0 <= frame_num < total_frames: frames_to_capture.append(frame_num)
            else:
                frames_to_capture = sorted(random.sample(range(0, total_frames), min(screenshot_job['count'], total_frames)))
            
            for i, frame_num in enumerate(frames_to_capture):
                await status_update_msg.edit_text(f"<code>Generating screenshot {i+1} of {len(frames_to_capture)}...</code>")
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if ret:
                    timestamp_display = get_readable_time(frame_num / fps)
                    cv2.putText(frame, timestamp_display, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 6, cv2.LINE_AA)
                    cv2.putText(frame, timestamp_display, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
                    if SCREENSHOT_WATERMARK:
                        (w, h), _ = cv2.getTextSize(SCREENSHOT_WATERMARK, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                        cv2.putText(frame, SCREENSHOT_WATERMARK, (frame.shape[1] - w - 15, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 6, cv2.LINE_AA)
                        cv2.putText(frame, SCREENSHOT_WATERMARK, (frame.shape[1] - w - 15, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
                    ss_path = os.path.join(TEMP_DIR, f"ss_{i+1}_{video_message_id}.jpg")
                    cv2.imwrite(ss_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    generated_media.append(InputMediaPhoto(ss_path))
                    generated_media_paths.append(ss_path)

        if clip_job:
            duration = clip_job['duration']
            start_time_sec = 0
            if clip_job.get('random'):
                max_start_time = max(0, (total_frames / fps) - duration)
                start_time_sec = random.uniform(0, max_start_time)
            else:
                time_parts = list(map(int, clip_job['start_time'].split(':')))
                while len(time_parts) < 3: time_parts.insert(0, 0)
                h, m, s = time_parts
                start_time_sec = h * 3600 + m * 60 + s
            
            start_time_str = get_readable_time(start_time_sec)
            await status_update_msg.edit_text(f"<code>Generating {duration}s clip from {start_time_str}...</code>")
            clip_path = os.path.join(TEMP_DIR, f"clip_{int(time.time())}.mp4")
            (
                ffmpeg.input(file_path, ss=start_time_sec)
                .output(clip_path, t=duration, vcodec='libx264', acodec='copy', strict='-2')
                .run(quiet=True, overwrite_output=True)
            )
            generated_media.append(InputMediaVideo(clip_path, caption=f"Clip from {start_time_str} ({duration}s)"))
            generated_media_paths.append(clip_path)

        if not generated_media: raise ValueError("Failed to generate any media.")
            
        for i in range(0, len(generated_media), 10):
            chunk = generated_media[i:i + 10]
            await status_update_msg.edit_text(f"<code>Uploading batch {i//10 + 1} of {math.ceil(len(generated_media)/10)}...</code>")
            await client.send_media_group(user_id, media=chunk)
            if len(generated_media) > 10:
                await asyncio.sleep(5)
        
        await status_update_msg.delete()

        completion_text = "✅ <b>Task Complete!</b>\n\n🎬 Ready for another operation or close the session."
        completion_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Return to Menu", callback_data=f"ws|main|menu|{video_message_id}")],
            [InlineKeyboardButton("🗑️ Close Session", callback_data=f"ws|menu|cleanup|{video_message_id}")]
        ])
        await client.send_message(user_id, completion_text, reply_markup=completion_markup)

    except Exception as e:
        error_text = f"❌ <b>An error occurred:</b>\n<code>{e}</code>"
        if status_update_msg: await status_update_msg.edit_text(error_text)
        else: await client.send_message(user_id, error_text)
    finally:
        if 'cap' in locals() and cap is not None: cap.release()
        for path in generated_media_paths:
            if os.path.exists(path): os.remove(path)
