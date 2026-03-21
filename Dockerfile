# ── Base image ────────────────────────────────────────────────────────────────
# Python 3.12 on Debian Bookworm (slim variant keeps image size down)
FROM python:3.12-slim-bookworm

# ── System dependencies for Playwright / Chromium ────────────────────────────
# These are the libraries Chromium needs to run headless on Linux.
# Installing them at the OS level before Playwright does its own install.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core Chromium runtime libraries
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
    libcairo2 \
    # Font support (prevents rendering issues)
    fonts-liberation \
    fonts-noto-color-emoji \
    # Required for subprocess management
    procps \
    # Clean up apt cache to keep image small
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first so Docker can cache this layer.
# Only re-runs pip install if requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright browser installation ──────────────────────────────────────────
# Install only Chromium — we do not need Firefox or WebKit.
# --with-deps is skipped here because we installed deps via apt above,
# keeping better control over what gets installed.
RUN playwright install chromium

# ── Application code ──────────────────────────────────────────────────────────
# Copy everything else after dependencies so code changes do not
# invalidate the pip/playwright cache layers.
COPY . .

# ── Streamlit configuration ───────────────────────────────────────────────────
# Disable Streamlit's file watcher in production (not needed, saves resources)
# and tell it not to open a browser window.
ENV STREAMLIT_SERVER_FILE_WATCHER_TYPE=none
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# ── Port ──────────────────────────────────────────────────────────────────────
EXPOSE 8501

# ── Healthcheck ───────────────────────────────────────────────────────────────
# Railway and Render use this to know when the app is ready.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
