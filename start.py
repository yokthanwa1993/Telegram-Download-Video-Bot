#!/usr/bin/env python3
"""Start both web app and telegram bot."""

import asyncio
import subprocess
import sys
import os


def main():
    # Start uvicorn web server in background
    web_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "80"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"Started web server (PID: {web_process.pid})")

    # Start telegram bot (blocking)
    print("Starting Telegram bot...")
    try:
        # Import and run bot
        from bot import main as bot_main
        bot_main()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        web_process.terminate()
        web_process.wait()


if __name__ == "__main__":
    main()
