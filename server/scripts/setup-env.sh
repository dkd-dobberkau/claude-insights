#!/bin/bash
# Setup script for Claude Insights Server
# Run this after deployment to generate secure environment variables

set -e

ENV_FILE="${1:-.env}"

# Check if .env already exists
if [ -f "$ENV_FILE" ]; then
    read -p ".env file already exists. Overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

echo "Generating secure environment variables..."

# Generate secure random values
DB_PASSWORD=$(openssl rand -hex 16)
API_SECRET_KEY=$(openssl rand -hex 32)
FLASK_SECRET_KEY=$(openssl rand -hex 32)

# Write .env file
cat > "$ENV_FILE" << EOF
# Claude Insights Server Configuration
# Generated on $(date -u +"%Y-%m-%d %H:%M:%S UTC")

# Database
DB_PASSWORD=$DB_PASSWORD

# API (JWT tokens)
API_SECRET_KEY=$API_SECRET_KEY

# Dashboard (Flask sessions)
FLASK_SECRET_KEY=$FLASK_SECRET_KEY
EOF

echo "Created $ENV_FILE with secure credentials."
echo ""
echo "Next steps:"
echo "  1. docker compose down"
echo "  2. docker compose up -d"
echo "  3. docker compose exec api python -m app.cli create-user <username> --email <email>"
