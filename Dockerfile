# Use a Python base image with a stable Debian base
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Chrome and Chromedriver
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    curl \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libfontconfig1 \
    libx11-6 \
    libx11-xcb1 \
    libxi6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxtst6 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install specific version of Google Chrome
RUN wget -q "https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_126.0.6478.126-1_amd64.deb" \
    && apt-get update && apt-get install -y ./google-chrome-stable_126.0.6478.126-1_amd64.deb \
    && rm google-chrome-stable_126.0.6478.126-1_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Install specific version of Chromedriver
RUN wget -q "https://storage.googleapis.com/chrome-for-testing-public/126.0.6478.126/linux64/chromedriver-linux64.zip" \
    && unzip chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver-linux64.zip \
    && chromedriver --version

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (Railway assigns dynamically)
EXPOSE $PORT

# Command to run the bot
CMD ["python", "Mofid_TB.py"]