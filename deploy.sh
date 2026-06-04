#!/bin/bash

# LegacyVerse Backend Deployment Script

echo "Starting LegacyVerse Backend Deployment..."

# Navigate to project directory
cd /var/legacyverse-backend

# Pull latest changes (if using git)
# git pull origin main

# Sync dependencies using uv
UV_CMD="uv"
if ! command -v uv &> /dev/null; then
    if [ -f "/root/.local/bin/uv" ]; then
        UV_CMD="/root/.local/bin/uv"
    else
        echo "Error: uv is not installed!"
        exit 1
    fi
fi

echo "Syncing dependencies with uv..."
$UV_CMD sync

# Run database migrations
echo "Running database migrations..."
$UV_CMD run python manage.py migrate

# Collect static files
echo "Collecting static files..."
$UV_CMD run python manage.py collectstatic --noinput

# Restart services
echo "Restarting services..."
sudo systemctl restart legacyverse.service
sudo systemctl restart nginx

# Check service status
echo "Checking service status..."
sudo systemctl status legacyverse.service --no-pager
sudo systemctl status nginx --no-pager

echo "Deployment completed!"
echo "Application is available at: http://localhost"
echo "Admin panel: http://localhost/admin/"
echo "API endpoints: http://localhost/api/"
