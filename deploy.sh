#!/bin/bash

# LegacyVerse Backend Deployment Script

echo "Starting LegacyVerse Backend Deployment..."

# Activate virtual environment
source /var/legacyverse-backend/venv/bin/activate

# Navigate to project directory
cd /var/legacyverse-backend

# Pull latest changes (if using git)
# git pull origin main

# Install/update dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Restart services
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
