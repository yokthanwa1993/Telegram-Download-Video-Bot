#!/usr/bin/env python3
"""Xiaohongshu downloader using Playwright to bypass captcha."""

import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright
import httpx


# Default cookies - update these from browser if needed
DEFAULT_COOKIES = [
    {"name": "a1", "value": "19a90f6bc56svf6e84o8s43lqt5jhn8fo6hcjfvpb30000518932", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "webId", "value": "7adabb4b2bc4bfdd80f18f30754b1728", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "web_session", "value": "040069b2a37562cb56388332593b4b7d7dd974", "domain": ".xiaohongshu.com", "path": "/"},
    {"name": "xsecappid", "value": "xhs-pc-web", "domain": ".xiaohongshu.com", "path": "/"},
]


async def resolve_short_url(short_url: str, cookies: list = None) -> str | None:
    """Resolve xhslink.com short URL to full URL."""
    if "xhslink.com" not in short_url and "xiaohongshu.com" in short_url:
        return short_url  # Already full URL

    if cookies is None:
        cookies = DEFAULT_COOKIES

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        try:
            await page.goto(short_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            return page.url
        except Exception as e:
            print(f"Error resolving URL: {e}")
            return None
        finally:
            await browser.close()


async def get_xhs_video_url(url: str, cookies: list = None) -> dict | None:
    """Extract video/image URLs from Xiaohongshu page."""
    if cookies is None:
        cookies = DEFAULT_COOKIES

    result = {
        "video_urls": [],
        "image_urls": [],
        "title": None,
        "author": None,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        # Intercept network requests for video URLs
        async def handle_response(response):
            resp_url = response.url
            if "sns-video" in resp_url and ".mp4" in resp_url:
                if resp_url not in result["video_urls"]:
                    result["video_urls"].append(resp_url)
            elif "sns-webpic" in resp_url or "sns-img" in resp_url:
                if ".jpg" in resp_url or ".png" in resp_url or ".webp" in resp_url:
                    if resp_url not in result["image_urls"]:
                        result["image_urls"].append(resp_url)

        page.on("response", handle_response)

        try:
            # Navigate to URL (short URLs will auto-redirect)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Wait for video to load and network requests to complete
            await asyncio.sleep(5)

            # Try to get title
            try:
                title_el = await page.query_selector('meta[name="og:title"], meta[property="og:title"], .title, h1')
                if title_el:
                    result["title"] = await title_el.get_attribute("content") or await title_el.inner_text()
            except:
                pass

            return result

        except asyncio.TimeoutError:
            # Even if timeout, we might have captured video URLs
            if result["video_urls"] or result["image_urls"]:
                return result
            return None
        except Exception as e:
            print(f"Error: {e}")
            if result["video_urls"] or result["image_urls"]:
                return result
            return None
        finally:
            await browser.close()


async def download_xhs_content(url: str, output_dir: Path, cookies: list = None) -> Path | list[Path] | None:
    """Download video or images from Xiaohongshu URL."""
    if cookies is None:
        cookies = DEFAULT_COOKIES

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Get media URLs
    result = await get_xhs_video_url(url, cookies)
    if not result:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }

    async with httpx.AsyncClient() as client:
        # Download video if available
        if result["video_urls"]:
            video_url = result["video_urls"][0]  # Get first (usually best quality)

            # Extract note ID from URL
            note_id_match = re.search(r'/explore/([a-f0-9]+)', url)
            note_id = note_id_match.group(1) if note_id_match else "video"

            video_path = output_dir / f"xhs_{note_id}.mp4"

            try:
                resp = await client.get(video_url, headers=headers, follow_redirects=True, timeout=120)
                resp.raise_for_status()
                video_path.write_bytes(resp.content)
                return video_path
            except Exception as e:
                print(f"Error downloading video: {e}")
                return None

        # Download images if no video
        elif result["image_urls"]:
            downloaded = []
            for i, img_url in enumerate(result["image_urls"][:10]):  # Limit to 10 images
                img_path = output_dir / f"xhs_image_{i+1}.jpg"
                try:
                    resp = await client.get(img_url, headers=headers, follow_redirects=True, timeout=60)
                    resp.raise_for_status()
                    img_path.write_bytes(resp.content)
                    downloaded.append(img_path)
                except Exception as e:
                    print(f"Error downloading image {i+1}: {e}")
            return downloaded if downloaded else None

    return None


# For testing
if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python xhs_downloader.py <url>")
            sys.exit(1)

        url = sys.argv[1]
        output_dir = Path("downloads")

        print(f"Downloading from: {url}")
        result = await download_xhs_content(url, output_dir)

        if result:
            if isinstance(result, list):
                print(f"Downloaded {len(result)} images:")
                for p in result:
                    print(f"  - {p}")
            else:
                print(f"Downloaded video: {result}")
        else:
            print("Failed to download")
            sys.exit(1)

    asyncio.run(main())
