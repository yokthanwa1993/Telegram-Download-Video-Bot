# Telegram Video Download Bot

Telegram Bot สำหรับดาวน์โหลดวิดีโอจากหลายแพลตฟอร์ม

## รองรับแพลตฟอร์ม

- TikTok
- Douyin (抖音)
- Xiaohongshu (小红书)
- YouTube
- Bilibili
- Weibo
- และอื่นๆ อีก 50+ แพลตฟอร์ม

## ความต้องการ

- Python 3.10+
- ffmpeg (สำหรับอ่านขนาดวิดีโอ)

## การติดตั้ง

1. Clone repository:
```bash
git clone https://github.com/YOUR_USERNAME/Telegram-Download-Video-Bot.git
cd Telegram-Download-Video-Bot
```

2. สร้าง virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# หรือ venv\Scripts\activate  # Windows
```

3. ติดตั้ง dependencies:
```bash
pip install -r requirements.txt
```

4. ติดตั้ง ffmpeg:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# ดาวน์โหลดจาก https://ffmpeg.org/download.html
```

## การใช้งาน

1. สร้าง Bot ผ่าน [@BotFather](https://t.me/botfather) บน Telegram

2. ตั้งค่า Bot Token:
```bash
export TELEGRAM_BOT_TOKEN="your-bot-token-here"
```

3. รัน Bot:
```bash
python bot.py
```

## การใช้งาน Bot

1. เปิด Bot บน Telegram
2. กด /start
3. ส่งลิงก์วิดีโอ
4. รอรับวิดีโอ!

## ข้อจำกัด

- ขนาดไฟล์สูงสุด 50MB (ข้อจำกัดของ Telegram Bot API)

## License

MIT
