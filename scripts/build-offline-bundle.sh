#!/usr/bin/env bash
# build-offline-bundle.sh -- PR-05: Offline/Air-Gapped Kurulum Paketi
#
# Internet erisimi olan bir makinede calistirilir. Tum Docker imajlarini
# (mongo:7 + derlenmis toprax-backend/toprax-frontend -- npm/pip
# bagimliliklari zaten imaj icine gomulu oldugu icin ayrica indirilmez)
# tek bir .tar.gz paketine toplar. Bu paket USB/harici disk ile internetsiz
# hedef sunucuya tasinip install-from-bundle.sh ile kurulur.
#
# Kullanim: bash scripts/build-offline-bundle.sh [cikti-dizini]
#           (varsayilan cikti: ./offline-bundle/)

set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${1:-./offline-bundle}"
IMAGES_DIR="$OUT_DIR/images"
BUNDLE_NAME="toprax-offline-bundle-$(date +%Y%m%d).tar.gz"

COMPOSE="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi

echo "=== TOPRAX Offline Bundle Olusturuluyor ==="
mkdir -p "$IMAGES_DIR"

echo "[1/4] mongo:7 imaji cekiliyor..."
docker pull mongo:7

echo "[2/4] backend/frontend imajlari derleniyor (image: toprax-backend:latest / toprax-frontend:latest)..."
$COMPOSE build backend frontend

echo "[3/4] Imajlar .tar dosyalarina kaydediliyor (docker save)..."
docker save mongo:7 -o "$IMAGES_DIR/mongo-7.tar"
docker save toprax-backend:latest -o "$IMAGES_DIR/toprax-backend.tar"
docker save toprax-frontend:latest -o "$IMAGES_DIR/toprax-frontend.tar"

echo "[4/4] Kurulum dosyalari kopyalaniyor ve paket sikistiriliyor..."
cp docker-compose.yml "$OUT_DIR/"
cp .env.example "$OUT_DIR/"
cp -r scripts "$OUT_DIR/"
cp upgrade.sh "$OUT_DIR/" 2>/dev/null || true
cp README.md "$OUT_DIR/" 2>/dev/null || true

tar -czf "$BUNDLE_NAME" -C "$(dirname "$OUT_DIR")" "$(basename "$OUT_DIR")"

BUNDLE_SIZE=$(du -h "$BUNDLE_NAME" | cut -f1)
echo
echo "=== Tamamlandi ==="
echo "Paket: $BUNDLE_NAME ($BUNDLE_SIZE)"
echo "Bu dosyayi USB/harici diskle hedef sunucuya tasiyip icinden cikan"
echo "'$(basename "$OUT_DIR")/scripts/install-from-bundle.sh' scriptini calistirin."
