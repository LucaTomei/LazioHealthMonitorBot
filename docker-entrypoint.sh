#!/bin/bash
set -e

# Docker entrypoint script
# Ensures all necessary directories exist and have correct permissions

echo "=== Lazio Health Monitor Bot Entrypoint ==="
echo "Running as user: $(whoami)"

# Create directories if they don't exist (for mounted volumes)
echo "Creating directories..."
mkdir -p /app/logs
mkdir -p /app/data
mkdir -p /app/debug_responses
mkdir -p /app/reports_pdf
mkdir -p /app/prenotazioni_pdf

# Fix ownership and permissions for mounted volumes
# This runs as root before switching to botuser
echo "Fixing permissions..."
chown -R botuser:botuser /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf 2>/dev/null || {
    echo "Warning: Could not change ownership (might be running as non-root)"
}

# Set write permissions for all users to ensure botuser can write
chmod -R 777 /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf 2>/dev/null || {
    echo "Warning: Could not change permissions"
}

echo "Directory setup complete"
echo "Switching to botuser and starting application..."

# Switch to botuser and execute the main command
exec gosu botuser "$@"
