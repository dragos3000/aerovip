#!/bin/bash
# Deployment script for Aero Vip Academy on start-line.ro
# Run as root or with sudo

set -e

APP_DIR="/opt/aerovip"
APP_USER="www-data"
DB_NAME="aerovip"
DB_USER="aerovip"
DB_PASS="aerovip"
DOMAIN="start-line.ro"

echo "=== Aero Vip Academy Deployment ==="

# 1. Install system dependencies
echo "[1/8] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip postgresql nginx certbot python3-certbot-nginx

# 2. Setup PostgreSQL
echo "[2/8] Setting up PostgreSQL..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

# 3. Deploy application
echo "[3/8] Deploying application..."
mkdir -p $APP_DIR
cp -r . $APP_DIR/
cd $APP_DIR

# 4. Setup Python venv
echo "[4/8] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# 5. Initialize database
echo "[5/8] Initializing database..."
export FLASK_APP=run.py
flask db init 2>/dev/null || true
flask db migrate -m "Initial migration" 2>/dev/null || true
flask db upgrade
flask seed

# 6. Setup log directory
echo "[6/8] Setting up logs..."
mkdir -p /var/log/aerovip
chown $APP_USER:$APP_USER /var/log/aerovip

# 7. Setup systemd service
echo "[7/8] Setting up systemd service..."
cp aerovip.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable aerovip
systemctl restart aerovip

# 8. Setup Nginx + SSL
echo "[8/8] Setting up Nginx with SSL..."
cp nginx.conf /etc/nginx/sites-available/aerovip
ln -sf /etc/nginx/sites-available/aerovip /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx config
nginx -t

# Get SSL certificate (will modify nginx config automatically)
certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || \
    echo "Note: SSL cert request failed. Run manually: certbot --nginx -d $DOMAIN -d www.$DOMAIN"

systemctl reload nginx

echo ""
echo "=== Deployment Complete ==="
echo "App running at: https://$DOMAIN"
echo "Admin login: admin@aerovip.ro / admin123"
echo ""
echo "Useful commands:"
echo "  systemctl status aerovip     - Check app status"
echo "  journalctl -u aerovip -f     - View app logs"
echo "  systemctl restart aerovip    - Restart app"
