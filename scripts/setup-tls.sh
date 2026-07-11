#!/usr/bin/env bash
# setup-tls.sh -- PR-06: Ilk kez Let's Encrypt sertifikasi alma
#
# ON-KOSUL: domain'in DNS A/AAAA kaydi bu sunucunun IP'sine isaret ediyor
# olmali, ve 80 portu disaridan erisilebilir olmali (ACME HTTP-01 dogrulamasi
# icin). Bu adim SADECE internete acik kurulumlar icindir -- air-gapped
# kurulumlarda kullanilmaz (bkz. docker-compose.tls.yml basindaki not).
#
# Kullanim: bash scripts/setup-tls.sh <domain> <eposta>
#   ornek:  bash scripts/setup-tls.sh tabsis.ornekkooperatif.com.tr admin@ornekkooperatif.com.tr

set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN="${1:-}"
EMAIL="${2:-}"

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Kullanim: bash scripts/setup-tls.sh <domain> <eposta>"
  exit 1
fi

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.tls.yml"
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose -f docker-compose.yml -f docker-compose.tls.yml"
fi

echo "=== TABSIS TLS Kurulumu: $DOMAIN ==="
mkdir -p nginx/certs nginx/webroot

echo "[1/4] nginx/reverse-proxy.conf sablon uzerinden uretiliyor (DOMAIN=$DOMAIN)..."
DOMAIN="$DOMAIN" envsubst '${DOMAIN}' < nginx/reverse-proxy.conf.template > nginx/reverse-proxy.conf

echo "[2/4] Gecici self-signed sertifika olusturuluyor (ilk nginx aciliş icin -- certbot HTTP-01 dogrulamasi bunu gerektirir)..."
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -keyout nginx/certs/privkey.pem -out nginx/certs/fullchain.pem \
  -subj "/CN=$DOMAIN" 2>/dev/null

echo "[3/4] reverse-proxy baslatiliyor..."
$COMPOSE up -d reverse-proxy

echo "[4/4] Let's Encrypt sertifikasi isteniyor (certbot, webroot yontemi)..."
docker run --rm \
  -v "$(pwd)/nginx/webroot:/var/www/certbot" \
  -v "tabsis_certbot_conf:/etc/letsencrypt" \
  certbot/certbot:latest certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive

echo "Gercek sertifika nginx/certs/ altina kopyalaniyor..."
docker run --rm \
  -v "tabsis_certbot_conf:/etc/letsencrypt" \
  -v "$(pwd)/nginx/certs:/out" \
  certbot/certbot:latest sh -c "cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /out/fullchain.pem && cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /out/privkey.pem"

echo "nginx yeniden yukleniyor..."
$COMPOSE exec reverse-proxy nginx -s reload

echo "Otomatik yenileme icin certbot servisi baslatiliyor (12 saatte bir kontrol, sertifika sonuna <30 gun kalinca yeniler)..."
$COMPOSE up -d certbot

echo
echo "=== Tamamlandi === https://$DOMAIN adresinden erisebilirsiniz."
echo "HTTP->HTTPS zorunlu yonlendirmeyi acmak icin nginx/reverse-proxy.conf.template"
echo "icindeki 'return 301' satirinin yorumunu kaldirip nginx/reverse-proxy.conf'u yeniden uretin."
