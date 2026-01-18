FROM python:3.11-slim

# Install ffmpeg and playwright browser dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application code
COPY bot.py .
COPY xhs_downloader.py .
COPY web_app.py .

# Create downloads directory
RUN mkdir -p /app/downloads

# Expose port
EXPOSE 80

# Run the web app
CMD ["python", "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "80"]
