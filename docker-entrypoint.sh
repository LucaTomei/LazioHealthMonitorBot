#!/bin/bash
set -e

# Docker entrypoint script
echo "=== Lazio Health Monitor Bot Entrypoint ==="
echo "Running as user: $(whoami)"

# Create all necessary directories
echo "Creating directories..."
mkdir -p /app/logs
mkdir -p /app/data
mkdir -p /app/debug_responses
mkdir -p /app/reports_pdf
mkdir -p /app/prenotazioni_pdf

# Check if TELEGRAM_BOT_TOKEN is set
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ ERROR: TELEGRAM_BOT_TOKEN environment variable is required!"
    echo ""
    echo "Please run the container with:"
    echo "  docker run -e TELEGRAM_BOT_TOKEN=your_token_here ..."
    exit 1
fi

echo "✓ TELEGRAM_BOT_TOKEN is set"

# Fix ownership and permissions
echo "Fixing permissions..."
chown -R botuser:botuser /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf 2>/dev/null || true
chmod -R 777 /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf 2>/dev/null || true

echo "✓ Directory setup complete"
echo ""
echo "Starting bot as botuser..."
echo "========================================="
echo ""

# Switch to botuser and execute the main command
exec gosu botuser "$@"
