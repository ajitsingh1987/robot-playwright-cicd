FROM python:3.12-slim

WORKDIR /app

# Install Node.js, npm and Chromium system dependencies
RUN apt-get update && \
    apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libcairo-gobject2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libgdk-pixbuf-2.0-0 \
    libxcursor1 \
    fonts-liberation \
    && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    node --version && \
    npm --version && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Initialize Robot Framework Browser / Playwright
RUN rfbrowser init

# Copy project files
COPY . .

# Run deterministic framework tests before Robot. A broken orchestrator must never
# be hidden by a browser-only result.
CMD ["sh", "-c", "rm -rf results/run && mkdir -p results/run/allure-results && python -m pytest orchestra/tests -q && python -m orchestra arch && python -m robot --outputdir results/run --listener allure_robotframework:results/run/allure-results tests"]