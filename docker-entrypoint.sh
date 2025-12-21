#!/bin/bash
set -e

# Docker entrypoint script
# Ensures all necessary directories exist and have correct permissions

echo "Starting Lazio Health Monitor Bot..."

# Create directories if they don't exist (for mounted volumes)
mkdir -p /app/logs
mkdir -p /app/data
mkdir -p /app/debug_responses
mkdir -p /app/reports_pdf
mkdir -p /app/prenotazioni_pdf

# Fix ownership and permissions for mounted volumes
# This runs as root before switching to botuser
chown -R botuser:botuser /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf 2>/dev/null || true
chmod -R 755 /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf 2>/dev/null || true

echo "Directory setup complete"
echo "Starting application as botuser..."

# Switch to botuser and execute the main command
exec gosu botuser "$@"
