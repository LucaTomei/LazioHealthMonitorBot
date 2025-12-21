# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies including gosu for user switching
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entrypoint script first
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs data debug_responses reports_pdf prenotazioni_pdf

# Create non-root user for security
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Health check (runs as root, checks if Python works)
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD gosu botuser python -c "import sys; sys.exit(0)" || exit 1

# Entrypoint handles permission fixes and user switching
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Run the bot
CMD ["python", "-u", "recup_monitor.py"]