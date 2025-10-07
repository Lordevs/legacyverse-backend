# Start services
sudo systemctl start legacyverse.service
sudo systemctl start nginx

# Stop services
sudo systemctl stop legacyverse.service
sudo systemctl stop nginx

# Restart services
sudo systemctl restart legacyverse.service
sudo systemctl restart nginx

# Check status
sudo systemctl status legacyverse.service
sudo systemctl status nginx

# View logs
sudo journalctl -u legacyverse.service -f
sudo tail -f /var/log/gunicorn/legacyverse_error.log