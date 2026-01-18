#!/usr/bin/env python3
"""Web interface for video downloader."""

import os
import re
import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# Import downloaders
try:
    from xhs_downloader import download_xhs_content
    XHS_AVAILABLE = True
except ImportError:
    XHS_AVAILABLE = False

app = FastAPI(title="Video Downloader")

# Download directory
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Store download tasks
downloads = {}


class DownloadRequest(BaseModel):
    url: str


def extract_url(text: str) -> str | None:
    """Extract URL from text that may contain extra content."""
    # Pattern to match URLs
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    if urls:
        return urls[0]
    return None


def get_video_dimensions(video_path: str) -> tuple[int, int] | tuple[None, None]:
    """Get video dimensions using ffprobe."""
    import subprocess
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


def is_xiaohongshu_url(url: str) -> bool:
    """Check if URL is from Xiaohongshu."""
    xhs_domains = ['xiaohongshu.com', 'xhslink.com']
    url_lower = url.lower()
    return any(domain in url_lower for domain in xhs_domains)


async def download_with_ytdlp(url: str, download_dir: Path) -> str | None:
    """Download video using yt-dlp."""
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
        print(f"yt-dlp output: {stderr.decode()[:500]}")
    except Exception as e:
        print(f"yt-dlp error: {e}")
        return None

    # Find downloaded file
    for ext in ["*.mp4", "*.mkv", "*.webm"]:
        files = list(download_dir.glob(ext))
        if files:
            return str(files[0])
    return None


async def download_video(url: str, task_id: str):
    """Download video and update task status."""
    task_dir = DOWNLOAD_DIR / task_id
    task_dir.mkdir(exist_ok=True)

    try:
        downloads[task_id]["status"] = "downloading"

        video_path = None

        # Try XHS downloader for Xiaohongshu URLs
        if is_xiaohongshu_url(url) and XHS_AVAILABLE:
            video_path = await download_xhs_content(url, task_dir)
            if video_path:
                video_path = str(video_path)

        # Fall back to yt-dlp for other URLs
        if not video_path:
            video_path = await download_with_ytdlp(url, task_dir)

        if video_path and os.path.exists(video_path):
            file_size = os.path.getsize(video_path)
            width, height = get_video_dimensions(video_path)
            downloads[task_id]["status"] = "completed"
            downloads[task_id]["file_path"] = video_path
            downloads[task_id]["file_name"] = os.path.basename(video_path)
            downloads[task_id]["file_size"] = file_size
            downloads[task_id]["width"] = width
            downloads[task_id]["height"] = height
        else:
            downloads[task_id]["status"] = "failed"
            downloads[task_id]["error"] = "ไม่สามารถดาวน์โหลดวิดีโอได้"

    except Exception as e:
        downloads[task_id]["status"] = "failed"
        downloads[task_id]["error"] = str(e)


def cleanup_old_downloads():
    """Clean up old download directories."""
    import time
    current_time = time.time()
    for task_id, task in list(downloads.items()):
        # Remove tasks older than 1 hour
        if current_time - task.get("created_at", current_time) > 3600:
            task_dir = DOWNLOAD_DIR / task_id
            if task_dir.exists():
                shutil.rmtree(task_dir)
            del downloads[task_id]


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main page."""
    return """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Prompt', sans-serif; }
        .gradient-bg {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .card-shadow {
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }
        .pulse-animation {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: .5; }
        }
        .slide-up {
            animation: slideUp 0.5s ease-out;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body class="min-h-screen gradient-bg">
    <div class="min-h-screen flex items-center justify-center p-4">
        <div class="bg-white rounded-3xl card-shadow w-full max-w-lg p-8 slide-up">
            <!-- Header -->
            <div class="text-center mb-8">
                <div class="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-r from-purple-500 to-pink-500 rounded-2xl mb-4">
                    <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"/>
                    </svg>
                </div>
                <h1 class="text-2xl font-bold text-gray-800">Video Downloader</h1>
                <p class="text-gray-500 mt-2">ดาวน์โหลดวิดีโอจาก TikTok, Xiaohongshu, YouTube และอื่นๆ</p>
            </div>

            <!-- Input Form -->
            <div class="space-y-4">
                <div class="relative">
                    <input
                        type="text"
                        id="urlInput"
                        placeholder="วางลิงก์วิดีโอที่นี่..."
                        class="w-full px-5 py-4 bg-gray-50 border-2 border-gray-200 rounded-xl focus:border-purple-500 focus:bg-white focus:outline-none transition-all text-gray-700"
                    >
                    <button
                        onclick="pasteFromClipboard()"
                        class="absolute right-3 top-1/2 -translate-y-1/2 px-3 py-1.5 text-sm text-purple-600 hover:bg-purple-50 rounded-lg transition-colors"
                    >
                        วาง
                    </button>
                </div>

                <button
                    id="downloadBtn"
                    onclick="startDownload()"
                    class="w-full py-4 bg-gradient-to-r from-purple-500 to-pink-500 text-white font-semibold rounded-xl hover:opacity-90 transition-all transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
                >
                    <span id="btnText">ดาวน์โหลด</span>
                    <span id="btnLoading" class="hidden">
                        <svg class="animate-spin inline w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        กำลังดาวน์โหลด...
                    </span>
                </button>
            </div>

            <!-- Status -->
            <div id="status" class="mt-6 hidden">
                <div id="statusContent"></div>
            </div>

            <!-- Supported Platforms -->
            <div class="mt-8 pt-6 border-t border-gray-100">
                <p class="text-center text-sm text-gray-400 mb-3">รองรับ</p>
                <div class="flex justify-center gap-4 text-gray-400">
                    <span class="px-3 py-1 bg-gray-50 rounded-full text-xs">TikTok</span>
                    <span class="px-3 py-1 bg-gray-50 rounded-full text-xs">Xiaohongshu</span>
                    <span class="px-3 py-1 bg-gray-50 rounded-full text-xs">YouTube</span>
                    <span class="px-3 py-1 bg-gray-50 rounded-full text-xs">Douyin</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentTaskId = null;
        let pollInterval = null;

        function extractUrl(text) {
            // Extract URL from text that may contain extra content
            const urlPattern = /https?:\/\/[^\s<>"{}|\\^`\[\]]+/g;
            const urls = text.match(urlPattern);
            return urls ? urls[0] : text;
        }

        async function pasteFromClipboard() {
            try {
                const text = await navigator.clipboard.readText();
                // Extract just the URL from pasted text
                const url = extractUrl(text);
                document.getElementById('urlInput').value = url;
            } catch (err) {
                console.log('Cannot paste from clipboard');
            }
        }

        async function startDownload() {
            const url = document.getElementById('urlInput').value.trim();
            if (!url) {
                showStatus('error', 'กรุณาใส่ลิงก์วิดีโอ');
                return;
            }

            setLoading(true);
            hideStatus();

            try {
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });

                const data = await response.json();

                if (data.task_id) {
                    currentTaskId = data.task_id;
                    showStatus('info', 'กำลังดาวน์โหลด...');
                    pollInterval = setInterval(checkStatus, 1500);
                } else {
                    showStatus('error', data.error || 'เกิดข้อผิดพลาด');
                    setLoading(false);
                }
            } catch (err) {
                showStatus('error', 'ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้');
                setLoading(false);
            }
        }

        async function checkStatus() {
            if (!currentTaskId) return;

            try {
                const response = await fetch(`/api/status/${currentTaskId}`);
                const data = await response.json();

                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    setLoading(false);
                    showDownloadReady(data);
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval);
                    setLoading(false);
                    showStatus('error', data.error || 'ดาวน์โหลดไม่สำเร็จ');
                }
            } catch (err) {
                console.log('Status check error');
            }
        }

        function showDownloadReady(data) {
            const sizeInMB = (data.file_size / (1024 * 1024)).toFixed(2);
            const statusEl = document.getElementById('status');
            const contentEl = document.getElementById('statusContent');
            // Sanitize filename for display
            const safeFileName = data.file_name.replace(/[<>&"']/g, '');

            // Determine video orientation and size display
            const width = data.width || 0;
            const height = data.height || 0;
            const isPortrait = height > width;
            const resolution = width && height ? width + 'x' + height : '';

            // Set max height based on orientation
            const videoClass = isPortrait
                ? 'rounded-xl max-h-72 shadow-lg'
                : 'rounded-xl max-h-56 max-w-full shadow-lg';

            contentEl.innerHTML = `
                <div class="bg-green-50 border border-green-200 rounded-xl p-4 slide-up">
                    <div class="flex items-center gap-3 mb-4">
                        <div class="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0">
                            <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                            </svg>
                        </div>
                        <div>
                            <p class="font-medium text-green-800">ดาวน์โหลดสำเร็จ!</p>
                            <p class="text-sm text-green-600">${sizeInMB} MB ${resolution ? '• ' + resolution : ''}</p>
                        </div>
                    </div>
                    <!-- Video Preview -->
                    <div class="mb-4 flex justify-center">
                        <video
                            class="${videoClass}"
                            controls
                            playsinline
                            preload="metadata"
                            src="/api/preview/${currentTaskId}"
                        >
                            Your browser does not support video playback.
                        </video>
                    </div>
                    <a
                        href="/api/file/${currentTaskId}"
                        download="${safeFileName}"
                        class="block w-full py-3 bg-green-500 text-white text-center font-semibold rounded-lg hover:bg-green-600 transition-colors"
                    >
                        <svg class="inline w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                        </svg>
                        บันทึกวิดีโอ
                    </a>
                </div>
            `;
            statusEl.classList.remove('hidden');
        }

        function showStatus(type, message) {
            const statusEl = document.getElementById('status');
            const contentEl = document.getElementById('statusContent');

            const colors = {
                error: 'bg-red-50 border-red-200 text-red-700',
                info: 'bg-blue-50 border-blue-200 text-blue-700',
                success: 'bg-green-50 border-green-200 text-green-700'
            };

            contentEl.innerHTML = `
                <div class="${colors[type]} border rounded-xl p-4 slide-up">
                    <p class="text-center">${message}</p>
                </div>
            `;
            statusEl.classList.remove('hidden');
        }

        function hideStatus() {
            document.getElementById('status').classList.add('hidden');
        }

        function setLoading(loading) {
            const btn = document.getElementById('downloadBtn');
            const btnText = document.getElementById('btnText');
            const btnLoading = document.getElementById('btnLoading');

            btn.disabled = loading;
            btnText.classList.toggle('hidden', loading);
            btnLoading.classList.toggle('hidden', !loading);
        }

        // Allow Enter key to submit
        document.getElementById('urlInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') startDownload();
        });
    </script>
</body>
</html>
"""


@app.post("/api/download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Start a download task."""
    import time

    cleanup_old_downloads()

    # Extract URL from text (handles pasted text with extra content)
    url = extract_url(request.url)
    if not url:
        return {"error": "ไม่พบลิงก์ในข้อความ"}

    task_id = str(uuid.uuid4())[:8]
    downloads[task_id] = {
        "status": "pending",
        "url": url,
        "created_at": time.time()
    }

    background_tasks.add_task(download_video, url, task_id)

    return {"task_id": task_id, "extracted_url": url}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """Get download task status."""
    if task_id not in downloads:
        raise HTTPException(status_code=404, detail="Task not found")

    return downloads[task_id]


@app.get("/api/file/{task_id}")
async def get_file(task_id: str):
    """Download the video file."""
    if task_id not in downloads:
        raise HTTPException(status_code=404, detail="Task not found")

    task = downloads[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Download not ready")

    file_path = task["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=task["file_name"]
    )


@app.get("/api/preview/{task_id}")
async def get_preview(task_id: str):
    """Stream video for preview."""
    if task_id not in downloads:
        raise HTTPException(status_code=404, detail="Task not found")

    task = downloads[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Download not ready")

    file_path = task["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"}
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
