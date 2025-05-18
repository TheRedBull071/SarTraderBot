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

# Add Google Chrome repository
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list

# Install Google Chrome
RUN apt-get update && apt-get install -y google-chrome-stable && rm -rf /var/lib/apt/lists/*

# Install Chromedriver with error handling
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+' || echo "not-found") \
    && if [ "$CHROME_VERSION" = "not-found" ]; then echo "Failed to get Chrome version"; exit 1; fi \
    && echo "Detected Chrome version: $CHROME_VERSION" \
    && wget -q --spider "https://storage.googleapis.com/chrome-for-testing-public/$CHROME_VERSION/linux64/chromedriver-linux64.zip" \
    && if [ $? -ne 0 ]; then echo "Chromedriver not found for version $CHROME_VERSION"; exit 1; fi \
    && wget -q "https://storage.googleapis.com/chrome-for-testing-public/$CHROME_VERSION/linux64/chromedriver-linux64.zip" \
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