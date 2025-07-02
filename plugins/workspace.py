"""
(©) HD Cinema Bot

This plugin provides the /process command for the Video Workspace,
allowing admins to generate screenshots and clips from video files.
This is a complete, rewritten version with full functionality and an enhanced UI.
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

def get_session_info_text(session: dict, prefix: str = "") -> str:
    """Generates the main text for the workspace menu with an improved UI."""
    file_name = session.get('file_name', 'Unknown File')
    file_size = format_bytes(session.get('file_size', 0))
    duration = get_readable_time(session.get('duration', 0))

    text = (
        f"🛠️ <b>Video Workspace</b>\n\n"
        f"<b>File:</b> <code>{file_name}</code>\n"
        f"<b>Size:</b> <code>{file_size}</code> | <b>Duration:</b> <code>{duration}</code>\n\n"
        "Select an option below to begin processing."
    )
    if prefix:
        text = f"{prefix}\n\n{text}"
    return text

def get_main_workspace_markup(video_message_id: int) -> InlineKeyboardMarkup:
    """Generates the main keyboard for the workspace."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Take Screenshots", callback_data=f"ws_ss_menu_{video_message_id}")],
        [InlineKeyboardButton("✂️ Generate Clip", callback_data=f"ws_clip_menu_{video_message_id}")],
        [InlineKeyboardButton("✅ Done & Delete Session", callback_data=f"ws_cleanup_{video_message_id}")]
    ])

# ======================================================================================
#                              *** Command & Message Handlers ***
# ======================================================================================

@Bot.on_message(filters.private & filters.command("process") & filters.user(ADMINS))
async def process_command_handler(client: Bot, message: Message):
    """Entry point for the /process command. Sets the user's state."""
    user_id = message.from_user.id
    
    # Clean up any previous session for this user
    if user_id in WORKSPACE_SESSIONS:
        session = WORKSPACE_SESSIONS.pop(user_id, None)
        if session and 'file_path' in session and os.path.exists(session['file_path']):
            try: os.remove(session['file_path'])
            except Exception as e: logger.error(f"Cleanup Error: Could not delete previous session file for {user_id}. {e}")

    # Set the user's state to expect a video for the workspace
    CONVERSATION_STATE[user_id] = 'awaiting_process_video'
    await message.reply_text("➡️ Please send the video file you want to work on...")

# This handler has high priority (group 0) and will only run for users in the correct state.
@Bot.on_message(
    filters.private &
    filters.user(ADMINS) &
    (filters.video | filters.document)
)
async def workspace_video_handler(client: Bot, message: Message):
    """
    This specific handler catches the video sent ONLY after the
    /process command has been used.
    """
    user_id = message.from_user.id
    
    # Only proceed if the user is in the correct conversation state
    if CONVERSATION_STATE.get(user_id) != 'awaiting_process_video':
        return

    # Clear the state now that we've received the video
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
    
    session = WORKSPACE_SESSIONS[user_id]
    text = get_session_info_text(session)
    markup = get_main_workspace_markup(message.id)
    
    await message.reply_text(text, reply_markup=markup, quote=True)

# ======================================================================================
#                              *** Callback & Backend Logic ***
# ======================================================================================

@Bot.on_callback_query(filters.regex("^ws_") & filters.user(ADMINS))
async def workspace_callback_handler(client: Bot, query: CallbackQuery):
    """Handles all button presses within the workspace."""
    user_id = query.from_user.id
    data = query.data.split("_")
    action = data[1]
    original_msg_id = int(data[-1])

    if user_id not in WORKSPACE_SESSIONS or WORKSPACE_SESSIONS[user_id]['msg_id'] != original_msg_id:
        return await query.answer("This workspace session has expired. Please start a new one with /process.", show_alert=True)
    
    session = WORKSPACE_SESSIONS[user_id]
    session['last_active'] = time.time()

    if action == "main":
        await query.answer()
        text = get_session_info_text(session)
        markup = get_main_workspace_markup(original_msg_id)
        await query.message.edit_text(text, reply_markup=markup)

    elif action == "ss":
        if data[2] == "menu":
            keyboard = [[InlineKeyboardButton("Auto (Random)", callback_data=f"ws_ss_random_{original_msg_id}")], [InlineKeyboardButton("Manual (Timestamps)", callback_data=f"ws_ss_manual_{original_msg_id}")], [InlineKeyboardButton("⬅️ Back", callback_data=f"ws_main_{original_msg_id}")]]
            await query.message.edit_text("<b>📸 Screenshot Options</b>", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data[2] == "random":
            keyboard = [[InlineKeyboardButton(f"{n}", callback_data=f"ws_ss_take_random_{n}_{original_msg_id}") for n in [2, 4, 6, 10]], [InlineKeyboardButton("⬅️ Back", callback_data=f"ws_ss_menu_{original_msg_id}")]]
            await query.message.edit_text("How many <b>random</b> screenshots would you like?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data[2] == "manual":
            CONVERSATION_STATE[user_id] = 'awaiting_ss_timestamps'
            await query.message.edit_text("Please reply to this message with the timestamps, separated by commas.\n\n<b>Example:</b> <code>00:01:30, 00:45:10</code>")
            
        elif data[2] == "take" and data[3] == "random":
            num_screenshots = int(data[4])
            await query.answer(f"✅ Task accepted! Generating {num_screenshots} screenshots...", show_alert=False)
            await query.message.delete()
            asyncio.create_task(run_process_and_notify(client, user_id, screenshot_job={'count': num_screenshots, 'timestamps': None}))

    elif action == "clip":
        CONVERSATION_STATE[user_id] = 'awaiting_clip_details'
        await query.message.edit_text("Please reply to this message with the clip details in the format: <code>start_time duration</code>\n\n<b>Example:</b> <code>00:01:30 15</code> (Max duration is 60s)")

    elif action == "cleanup":
        await query.answer("Closing session...", show_alert=False)
        if session and session.get('file_path') and os.path.exists(session['file_path']):
            try: os.remove(session['file_path'])
            except Exception as e: logger.error(f"Cleanup Error: Could not delete session file for user {user_id}: {e}")
        WORKSPACE_SESSIONS.pop(user_id, None)
        await query.message.edit_text("✅ <b>Session Closed.</b>\nAll temporary files have been deleted.")

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
            if duration_sec > 60:
                return await message.reply_text("Maximum clip duration is 60 seconds. Please try again.")
        except Exception:
            return await message.reply_text("<b>Invalid format.</b> Reply with <code>start_time duration</code> (e.g., <code>00:01:30 15</code>)")
        
        await message.delete()
        clip_job = {"start_time": start_time, "duration": duration_sec}
        asyncio.create_task(run_process_and_notify(client, user_id, clip_job=clip_job))

    elif state == 'awaiting_ss_timestamps':
        timestamps = [ts.strip() for ts in message.text.split(',')]
        await message.delete()
        screenshot_job = {'count': 0, 'timestamps': timestamps}
        asyncio.create_task(run_process_and_notify(client, user_id, screenshot_job=screenshot_job))

async def run_process_and_notify(client: Bot, user_id: int, screenshot_job=None, clip_job=None):
    """The main backend processing function."""
    if user_id not in WORKSPACE_SESSIONS:
        return await client.send_message(user_id, "❌ Error: Your workspace session was not found. It might have timed out.")
    
    session = WORKSPACE_SESSIONS[user_id]
    video_message_id = session['msg_id']
    
    status_update_msg = None
    file_path = ""
    cap = None
    generated_media_paths = []

    try:
        if not session.get('file_path') or not os.path.exists(session.get('file_path')):
            status_update_msg = await client.send_message(user_id, "<code>Step 1/4:</code> <b>Downloading video for session...</b>")
            video_message = await client.get_messages(user_id, video_message_id)
            file_path = os.path.join(TEMP_DIR, f"{video_message.id}.mp4")
            os.makedirs(TEMP_DIR, exist_ok=True)
            
            start_download_time = time.time()
            last_update_time = time.time()
            async def progress(current, total):
                nonlocal last_update_time
                if time.time() - last_update_time > 2:
                    percentage = current * 100 / total
                    try:
                        await status_update_msg.edit_text(f"<code>Step 1/4:</code> <b>Downloading...</b> <code>{percentage:.1f}%</code>")
                    except MessageNotModified:
                        pass
                    last_update_time = time.time()
            
            await client.download_media(video_message, file_name=file_path, progress=progress)
            session['file_path'] = file_path
        else:
            status_update_msg = await client.send_message(user_id, "<b>Using cached video from current session...</b>")
            file_path = session['file_path']
        
        session['last_active'] = time.time()
        
        await status_update_msg.edit_text("<code>Step 2/4:</code> <b>Processing video...</b>")
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
            else: # Random screenshots
                frames_to_capture = sorted(random.sample(range(0, total_frames), min(screenshot_job['count'], total_frames)))
            
            for i, frame_num in enumerate(frames_to_capture):
                await status_update_msg.edit_text(f"<code>Step 2/4:</code> <b>Generating screenshot {i+1} of {len(frames_to_capture)}...</b>")
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
            await status_update_msg.edit_text("<code>Step 2/4:</code> <b>Generating video clip...</b>")
            clip_path = os.path.join(TEMP_DIR, f"clip_{int(time.time())}.mp4")
            (
                ffmpeg.input(file_path, ss=clip_job['start_time'])
                .output(clip_path, t=clip_job['duration'], vcodec='libx264', acodec='copy')
                .run(quiet=True, overwrite_output=True)
            )
            generated_media.append(InputMediaVideo(clip_path, caption=f"Clip: {clip_job['start_time']} for {clip_job['duration']}s"))
            generated_media_paths.append(clip_path)

        if not generated_media: raise ValueError("Failed to generate any media.")
            
        await status_update_msg.edit_text(f"<code>Step 3/4:</code> <b>Uploading {len(generated_media)} items...</b>")
        await client.send_media_group(user_id, media=generated_media)
        
        await status_update_msg.delete()
        # After completing the task, show the main workspace menu again
        final_text = get_session_info_text(session, prefix="✅ <b>Task Complete!</b>")
        final_markup = get_main_workspace_markup(video_message_id)
        await client.send_message(user_id, final_text, reply_markup=final_markup)


    except Exception as e:
        error_text = f"❌ <b>An error occurred:</b>\n<code>{e}</code>"
        if status_update_msg: await status_update_msg.edit_text(error_text)
        else: await client.send_message(user_id, error_text)
    finally:
        if cap is not None: cap.release()
        for path in generated_media_paths:
            if os.path.exists(path): os.remove(path)
