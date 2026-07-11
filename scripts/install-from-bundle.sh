#!/usr/bin/env bash
# install-from-bundle.sh -- PR-05: Air-Gapped ortamda bundle'dan kurulum
#
# build-offline-bundle.sh ile uretilen paket internetsiz hedef sunucuya
# tasindiktan sonra bu script paketin ICINDEN calistirilir:
#   tar -xzf tabsis-offline-bundle-YYYYMMDD.tar.gz
#   cd offline-bundle
#   bash scripts/install-from-bundle.sh
#
# Internet GEREKTIRMEZ -- tum imajlar images/ altindaki .tar dosyalarindan
# 'docker load' ile yuklenir.

set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi

echo "=== TABSIS Air-Gapped Kurulum ==="

echo "[1/4] On-kosul kontrolu (Docker/RAM/disk/port)..."
bash scripts/check-requirements.sh || {
  echo "HATA: on-kosul kontrolu basarisiz -- yukarida belirtilen sorunlari giderin.";
  exit 1;
}

echo "[2/4] Imajlar yukleniyor (docker load, internet gerektirmez)..."
for tar_file in images/*.tar; do
  echo "  -> $tar_file"
  docker load -i "$tar_file"
done

if [ ! -f .env ]; then
  echo "[3/4] .env dosyasi bulunamadi -- .env.example'dan olusturuluyor. SECRETLARI DEGISTIRMEYI UNUTMAYIN."
  cp .env.example .env
  echo "  UYARI: kuruluma devam etmeden once .env dosyasini acip JWT_SECRET, MONGO_ROOT_PASSWORD,"
  echo "  PLATFORM_ADMIN_PASSWORD degerlerini degistirin (varsayilanlarla ASLA prod'a alinmaz)."
  read -p "  .env dosyasini duzenlediniz mi ve devam etmek istiyor musunuz? [e/H] " confirm
  if [ "$confirm" != "e" ] && [ "$confirm" != "E" ]; then
    echo "Kurulum durduruldu. .env dosyasini duzenleyip scripti tekrar calistirin."
    exit 1
  fi
else
  echo "[3/4] Mevcut .env dosyasi kullanilacak."
fi

echo "[4/4] Servisler baslatiliyor (internet erisimi olmadan, yerel imajlarla)..."
$COMPOSE up -d

echo
echo "Servislerin saglikli olmasi bekleniyor..."
bash scripts/smoke-test.sh || {
  echo "UYARI: smoke test basarisiz. 'docker-compose logs' ile detaylara bakin."
  exit 1
}

echo
echo "=== Kurulum tamamlandi === Tarayicidan http://<sunucu-ip>:3000 adresine gidin."
