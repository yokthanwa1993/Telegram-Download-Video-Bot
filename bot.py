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

# Import XHS downloader
try:
    from xhs_downloader import download_xhs_content, resolve_short_url
    XHS_AVAILABLE = True
except ImportError:
    XHS_AVAILABLE = False
    print("Warning: xhs_downloader not available, Xiaohongshu downloads will use fallback")

# Bot Token - Set via environment variable
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Directory for downloads
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# URL pattern
URL_PATTERN = re.compile(r'https?://[^\s]+')

# Supported video platforms
SUPPORTED_DOMAINS = [
    # TikTok
    'tiktok.com', 'vm.tiktok.com',
    # Douyin
    'douyin.com', 'iesdouyin.com', 'v.douyin.com',
    # Xiaohongshu
    'xiaohongshu.com', 'xhslink.com',
    # YouTube
    'youtube.com', 'youtu.be', 'youtube.com/shorts',
    # Bilibili
    'bilibili.com', 'b23.tv',
    # Weibo
    'weibo.com', 'weibo.cn',
    # Facebook
    'facebook.com', 'fb.watch', 'fb.com',
    # Twitter/X
    'twitter.com', 'x.com',
    # Instagram
    'instagram.com',
    # Others
    'vimeo.com', 'dailymotion.com', 'twitch.tv',
]


def is_supported_url(url: str) -> bool:
    """Check if URL is from a supported video platform."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in SUPPORTED_DOMAINS)


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


def find_audio_file(download_dir: Path) -> str | None:
    """Find downloaded audio file."""
    for ext in ["*.m4a", "*.mp3", "*.aac", "*.wav", "*.opus", "*.ogg"]:
        audio_files = list(download_dir.rglob(ext))
        if audio_files:
            return str(audio_files[0])
    return None


def video_has_audio(video_path: str) -> bool:
    """Check if video file has audio stream."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a',
             '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path],
            capture_output=True, text=True, timeout=10
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


async def merge_video_audio(video_path: str, audio_path: str, output_dir: Path) -> str | None:
    """Merge separate video and audio files."""
    output_path = str(output_dir / "merged.mp4")

    try:
        process = await asyncio.create_subprocess_exec(
            'ffmpeg',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y',
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(process.communicate(), timeout=600)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # Remove original files
            os.remove(video_path)
            os.remove(audio_path)
            return output_path
    except Exception as e:
        print(f"FFmpeg merge error: {e}")

    return None


def is_xiaohongshu_url(url: str) -> bool:
    """Check if URL is from Xiaohongshu."""
    xhs_domains = ['xiaohongshu.com', 'xhslink.com']
    url_lower = url.lower()
    return any(domain in url_lower for domain in xhs_domains)


def should_use_ytdlp(url: str) -> bool:
    """Check if URL should use yt-dlp (better for these sites)."""
    ytdlp_domains = [
        'facebook.com', 'fb.watch', 'fb.com',
        'youtube.com', 'youtu.be',
        'twitter.com', 'x.com',
        'instagram.com',
        'vimeo.com',
        'dailymotion.com',
        'twitch.tv',
    ]
    url_lower = url.lower()
    return any(domain in url_lower for domain in ytdlp_domains)


async def download_with_ytdlp(url: str, download_dir: Path) -> str | None:
    """Download video using yt-dlp (better for Facebook, YouTube, etc.)."""
    output_template = str(download_dir / "%(title).50s.%(ext)s")

    # Use format 18 (360p mp4) or 22 (720p mp4) which have audio built-in
    # This avoids issues with YouTube's SABR streaming
    try:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "-f", "22/18/best[ext=mp4]/best",  # 720p mp4 > 360p mp4 > best mp4 > best
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-playlist",
            "--socket-timeout", "30",
            "--retries", "3",
            url,
            cwd=str(download_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        print(f"yt-dlp stdout: {stdout.decode()[:500]}")
        print(f"yt-dlp stderr: {stderr.decode()[:500]}")
    except Exception as e:
        print(f"yt-dlp error: {e}")
        return None

    return find_video_file(download_dir)


async def download_with_videodl(url: str, download_dir: Path) -> str | None:
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

    return find_video_file(download_dir)


def find_video_file(download_dir: Path) -> str | None:
    """Find downloaded video file."""
    video_files = list(download_dir.rglob("*.mp4"))
    if video_files:
        return str(video_files[0])

    for ext in ["*.mkv", "*.webm", "*.avi", "*.mov"]:
        video_files = list(download_dir.rglob(ext))
        if video_files:
            return str(video_files[0])

    return None


async def download_with_xhs(url: str, download_dir: Path) -> str | None:
    """Download video using Xiaohongshu downloader with Playwright."""
    if not XHS_AVAILABLE:
        return None

    try:
        result = await download_xhs_content(url, download_dir)
        if result:
            if isinstance(result, list):
                # Multiple images - return first one for now
                return str(result[0]) if result else None
            return str(result)
    except Exception as e:
        print(f"XHS downloader error: {e}")
    return None


async def download_video(url: str, download_dir: Path) -> str | None:
    """Download video using best available method."""
    # Try Xiaohongshu downloader first for XHS URLs
    if is_xiaohongshu_url(url) and XHS_AVAILABLE:
        result = await download_with_xhs(url, download_dir)
        if result:
            return result
        print("XHS downloader failed, trying videodl...")

    if should_use_ytdlp(url):
        # Try yt-dlp first for supported sites
        result = await download_with_ytdlp(url, download_dir)
        if result:
            return result
        # Fall back to videodl if yt-dlp fails
        print("yt-dlp failed, trying videodl...")

    return await download_with_videodl(url, download_dir)


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


def is_telegram_compatible(video_path: str) -> bool:
    """Check if video is H.264 MP4 (Telegram compatible)."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', video_path],
            capture_output=True, text=True, timeout=10
        )
        codec = result.stdout.strip().lower()
        is_mp4 = video_path.lower().endswith('.mp4')
        return codec == 'h264' and is_mp4
    except Exception:
        return False


async def convert_to_mp4(input_path: str, output_dir: Path) -> str | None:
    """Convert video to MP4 H.264 for Telegram compatibility."""
    output_path = str(output_dir / "converted.mp4")

    try:
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-i', input_path,
            '-c:v', 'libx264',      # H.264 video codec
            '-preset', 'fast',       # Faster encoding
            '-crf', '23',            # Quality (lower = better, 23 is default)
            '-c:a', 'aac',           # AAC audio codec
            '-b:a', '128k',          # Audio bitrate
            '-movflags', '+faststart',  # Enable streaming
            '-y',                    # Overwrite output
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(process.communicate(), timeout=600)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # Remove original file
            os.remove(input_path)
            return output_path
    except Exception as e:
        print(f"FFmpeg conversion error: {e}")

    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages with URLs."""
    text = update.message.text
    urls = URL_PATTERN.findall(text)

    if not urls:
        await update.message.reply_text("กรุณาส่งลิงก์วิดีโอมา")
        return

    url = urls[0]

    # Check if URL is supported
    if not is_supported_url(url):
        await update.message.reply_text(
            "❌ ลิงก์นี้ไม่รองรับ\n\n"
            "รองรับเฉพาะ:\n"
            "• TikTok, Douyin\n"
            "• Xiaohongshu (小红书)\n"
            "• YouTube\n"
            "• Bilibili\n"
            "• Weibo\n"
            "• Facebook, Instagram\n"
            "• Twitter/X"
        )
        return

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

        if video_path and os.path.exists(video_path):
            # Check if there's a separate audio file to merge
            audio_path = find_audio_file(DOWNLOAD_DIR)

            if audio_path and not video_has_audio(video_path):
                # Video has no audio, merge with separate audio file
                try:
                    await status_msg.edit_text("🔊 กำลังรวมเสียง...\n⏱ เวลา: " + format_time(time.time() - start_time))
                except Exception:
                    pass

                merged_path = await merge_video_audio(video_path, audio_path, DOWNLOAD_DIR)
                if merged_path:
                    video_path = merged_path
            elif not is_telegram_compatible(video_path):
                # Check if conversion needed
                try:
                    await status_msg.edit_text("🔄 กำลังแปลงวิดีโอ...\n⏱ เวลา: " + format_time(time.time() - start_time))
                except Exception:
                    pass

                converted_path = await convert_to_mp4(video_path, DOWNLOAD_DIR)
                if converted_path:
                    video_path = converted_path

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
