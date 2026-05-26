#!/bin/bash
# SSL証明書取得 & Nginx設定切り替えスクリプト
# DNSレコードをこのサーバーに向けた後に実行してください

set -e

echo "=== SSL証明書を取得します ==="
certbot certonly \
  --webroot -w /var/www/certbot \
  -d 1qaz.jp -d www.1qaz.jp \
  --email "${LETSENCRYPT_EMAIL:?set LETSENCRYPT_EMAIL env var}" \
  --agree-tos \
  --non-interactive

echo "=== Nginx設定をHTTPS版に切り替えます ==="
rm -f /etc/nginx/sites-enabled/ichikazu
ln -sf /etc/nginx/sites-available/ichikazu /etc/nginx/sites-enabled/ichikazu

nginx -t && systemctl reload nginx

echo "=== 自動更新の設定 ==="
# certbot は /etc/cron.d/certbot で自動更新されます
systemctl status certbot.timer 2>/dev/null || echo "cron.d/certbot を確認してください"

echo ""
echo "完了！ https://1qaz.jp にアクセスして確認してください。"
