#!/usr/bin/env python3
"""
Telegram Bot for downloading videos from various platforms.
Supports: TikTok, Douyin, Xiaohongshu, YouTube, Bilibili, Weibo and more.
"""

import os
import re
import shutil
import asyncio
import time
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Bot Token - Set via environment variable
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Directory for downloads
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# URL pattern
URL_PATTERN = re.compile(r'https?://[^\s]+')


def format_time(seconds: float) -> str:
    """Format seconds to readable time."""
    if seconds < 60:
        return f"{seconds:.1f} วินาที"
    else:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins} นาที {secs} วินาที"


def format_size(bytes_val: float) -> str:
    """Format bytes to human readable size."""
    if bytes_val is None or bytes_val < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} TB"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "สวัสดี! 👋 ส่งลิงก์วิดีโอมาได้เลย\n\n"
        "รองรับ: TikTok, Douyin, Xiaohongshu, YouTube, Bilibili, Weibo และอื่นๆ"
    )


async def update_elapsed_time(status_msg, start_time: float, stop_event: asyncio.Event):
    """Update message with elapsed time."""
    dots = ["", ".", "..", "..."]
    i = 0

    while not stop_event.is_set():
        elapsed = time.time() - start_time
        dot = dots[i % 4]
        i += 1

        msg = f"⏳ กำลังดาวน์โหลด{dot}\n⏱ เวลา: {format_time(elapsed)}"

        try:
            await status_msg.edit_text(msg)
        except Exception:
            pass

        await asyncio.sleep(0.8)


async def download_video(url: str, download_dir: Path) -> str | None:
    """Download video using videodl CLI."""
    try:
        process = await asyncio.create_subprocess_exec(
            "videodl", "-i", url,
            cwd=str(download_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(process.communicate(), timeout=300)
    except Exception as e:
        print(f"videodl error: {e}")
        return None

    # Find downloaded file
    video_files = list(download_dir.rglob("*.mp4"))
    if video_files:
        return str(video_files[0])

    for ext in ["*.mkv", "*.webm", "*.avi", "*.mov"]:
        video_files = list(download_dir.rglob(ext))
        if video_files:
            return str(video_files[0])

    return None


def get_video_dimensions(video_path: str) -> tuple[int, int] | tuple[None, None]:
    """Get video dimensions using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=p=0', video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            dims = result.stdout.strip().split(',')
            return int(dims[0]), int(dims[1])
    except Exception:
        pass
    return None, None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages with URLs."""
    text = update.message.text
    urls = URL_PATTERN.findall(text)

    if not urls:
        await update.message.reply_text("กรุณาส่งลิงก์วิดีโอมา")
        return

    url = urls[0]

    # Clean download directory
    for f in DOWNLOAD_DIR.glob("*"):
        if f.is_file():
            f.unlink()
        elif f.is_dir():
            shutil.rmtree(f)

    # Initial message
    start_time = time.time()
    status_msg = await update.message.reply_text("⏳ กำลังดาวน์โหลด...\n⏱ เวลา: 0.0 วินาที")

    # Start elapsed time updater
    stop_event = asyncio.Event()
    updater_task = asyncio.create_task(
        update_elapsed_time(status_msg, start_time, stop_event)
    )

    try:
        # Download video
        video_path = await download_video(url, DOWNLOAD_DIR)

        # Stop updater
        stop_event.set()
        await updater_task

        elapsed = time.time() - start_time

        if video_path and os.path.exists(video_path):
            file_size = os.path.getsize(video_path)

            await status_msg.edit_text(
                f"✅ ดาวน์โหลดเสร็จ!\n"
                f"📦 ขนาด: {format_size(file_size)}\n"
                f"⏱ ใช้เวลา: {format_time(elapsed)}"
            )
            await asyncio.sleep(0.5)

            if file_size > 50 * 1024 * 1024:
                await status_msg.edit_text(
                    f"❌ ไฟล์ใหญ่เกิน 50MB ({file_size // (1024*1024)}MB)\n"
                    "Telegram Bot จำกัดที่ 50MB"
                )
                return

            await status_msg.edit_text("📤 กำลังส่งวิดีโอ...")

            # Get video dimensions for correct preview
            width, height = get_video_dimensions(video_path)

            with open(video_path, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption="✅ ดาวน์โหลดสำเร็จ!",
                    width=width,
                    height=height
                )

            await status_msg.delete()
            os.remove(video_path)
        else:
            await status_msg.edit_text(
                f"❌ ไม่สามารถดาวน์โหลดวิดีโอได้\n"
                f"⏱ ใช้เวลา: {format_time(elapsed)}\n"
                "ลองตรวจสอบลิงก์อีกครั้ง"
            )

    except Exception as e:
        stop_event.set()
        print(f"Error: {e}")
        await status_msg.edit_text(f"❌ เกิดข้อผิดพลาด: {str(e)[:100]}")


def main():
    """Start the bot."""
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("Please set it: export TELEGRAM_BOT_TOKEN='your-token-here'")
        return

    print("Starting Video Download Bot...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
