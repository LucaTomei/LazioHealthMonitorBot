#!/bin/bash
set -e

# Docker entrypoint script
# Auto-configures the bot with minimal user input

echo "=== Lazio Health Monitor Bot Entrypoint ==="
echo "Running as user: $(whoami)"

# Create all necessary directories
echo "Creating directories..."
mkdir -p /app/logs
mkdir -p /app/data
mkdir -p /app/debug_responses
mkdir -p /app/reports_pdf
mkdir -p /app/prenotazioni_pdf

# Create default config files if they don't exist
echo "Checking configuration files..."

# Create authorized_users.json if missing
if [ ! -f /app/authorized_users.json ]; then
    echo "Creating default authorized_users.json..."
    echo '[]' > /app/authorized_users.json
    echo "⚠️  WARNING: No users authorized! First user to interact with bot will become admin."
fi

# Create input_prescriptions.json if missing
if [ ! -f /app/input_prescriptions.json ]; then
    echo "Creating default input_prescriptions.json..."
    echo '[]' > /app/input_prescriptions.json
fi

# Create previous_data.json if missing
if [ ! -f /app/data/previous_data.json ]; then
    echo "Creating default previous_data.json..."
    echo '{}' > /app/data/previous_data.json
fi

# Create reports_monitoring.json if missing
if [ ! -f /app/reports_monitoring.json ]; then
    echo "Creating default reports_monitoring.json..."
    echo '[]' > /app/reports_monitoring.json
fi

# Check if TELEGRAM_BOT_TOKEN is set
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ ERROR: TELEGRAM_BOT_TOKEN environment variable is required!"
    echo ""
    echo "Please run the container with:"
    echo "  docker run -e TELEGRAM_BOT_TOKEN=your_token_here ..."
    echo ""
    echo "Or create a .env file and use:"
    echo "  docker run --env-file .env ..."
    exit 1
fi

echo "✓ TELEGRAM_BOT_TOKEN is set"

# Fix ownership and permissions
echo "Fixing permissions..."
chown -R botuser:botuser /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf /app/authorized_users.json /app/input_prescriptions.json /app/reports_monitoring.json 2>/dev/null || {
    echo "Warning: Could not change ownership (might be running as non-root)"
}

# Set write permissions
chmod -R 777 /app/logs /app/data /app/debug_responses /app/reports_pdf /app/prenotazioni_pdf 2>/dev/null || true
chmod 666 /app/authorized_users.json /app/input_prescriptions.json /app/reports_monitoring.json 2>/dev/null || true

echo "✓ Directory setup complete"
echo "✓ Configuration files ready"
echo ""
echo "Starting bot as botuser..."
echo "========================================="
echo ""

# Switch to botuser and execute the main command
exec gosu botuser "$@"
