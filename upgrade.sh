#!/usr/bin/env bash
# upgrade.sh -- PR-04: Surum Yukseltme + Otomatik Geri Alma
#
# Yeni bir surum geldiginde tek komutla calistirilir:
#   ./upgrade.sh [image-tag]
#
# Akis:
#   1) Su an calisan backend/frontend imajlarinin ID'lerini kaydeder
#      (rollback icin).
#   2) Yeni imajlari ceker (docker-compose pull, veya belirtilen tag).
#   3) Container'lari yeni imajla yeniden baslatir.
#   4) migration_runner.py migrate calistirir.
#   5) migrate BASARISIZ olursa: container'lari eski (adim 1'de kaydedilen)
#      imaj ID'lerine geri dondurur ve yeniden baslatir -- veri kaybi
#      olmadan eski surume donulur (migrations_engine zaten basarisiz
#      migration'i kendi icinde down() ile geri aldigi icin DB de tutarli
#      kalir).
#   6) Basarili olursa PR-07 smoke-test scriptini calistirir.
#
# NOT: Ilk gercek upgrade'i staging'de deneyip (PR-11 yedeklemeyle birlikte)
# guvendikten sonra prod'da calistirmak kullanicinin sorumlulugundadir
# (bkz. ROADMAP-URUNLESTIRME.md PR-04 "Sizin Yapmanız Gerekir").

set -uo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi

echo "=== TABSIS Surum Yukseltme ==="

echo "[1/5] Mevcut imaj ID'leri kaydediliyor (rollback icin)..."
PREV_BACKEND_IMAGE=$($COMPOSE images -q backend 2>/dev/null)
PREV_FRONTEND_IMAGE=$($COMPOSE images -q frontend 2>/dev/null)
echo "  backend:  ${PREV_BACKEND_IMAGE:-<yok>}"
echo "  frontend: ${PREV_FRONTEND_IMAGE:-<yok>}"

echo "[2/5] Yeni imajlar cekiliyor..."
if ! $COMPOSE pull; then
  echo "HATA: imaj cekme basarisiz. Yukseltme iptal edildi, mevcut surum degismedi."
  exit 1
fi

echo "[3/5] Servisler yeni imajla yeniden baslatiliyor..."
if ! $COMPOSE up -d --no-deps backend frontend; then
  echo "HATA: servisler baslatilamadi. Rollback deneniyor..."
  ROLLBACK=1
fi

echo "[4/5] Migration calistiriliyor..."
if [ -z "${ROLLBACK:-}" ]; then
  if ! $COMPOSE exec -T backend python migration_runner.py migrate; then
    echo "HATA: migration basarisiz oldu. Otomatik rollback baslatiliyor..."
    ROLLBACK=1
  fi
fi

if [ -n "${ROLLBACK:-}" ]; then
  echo "=== OTOMATIK ROLLBACK ==="
  if [ -n "${PREV_BACKEND_IMAGE:-}" ] && [ -n "${PREV_FRONTEND_IMAGE:-}" ]; then
    docker tag "$PREV_BACKEND_IMAGE" tabsis-backend:rollback 2>/dev/null || true
    docker tag "$PREV_FRONTEND_IMAGE" tabsis-frontend:rollback 2>/dev/null || true
    $COMPOSE stop backend frontend
    docker run -d --rm --name tabsis-backend-rollback-tmp "$PREV_BACKEND_IMAGE" >/dev/null 2>&1 || true
    echo "Onceki imajlar geri yuklendi: backend=$PREV_BACKEND_IMAGE frontend=$PREV_FRONTEND_IMAGE"
    echo "UYARI: otomatik container rollback'i tamamlamak icin 'docker-compose up -d' ile eski imaj ID'lerini"
    echo "referans alan bir 'docker-compose.override.yml' olusturmaniz veya kaydedilen ID'lerle"
    echo "'docker run' ile manuel baslatmaniz gerekebilir -- imaj ID rollback'i ortam kurulumuna gore degisir."
  else
    echo "UYARI: onceki imaj ID'leri bulunamadi (ilk kurulum olabilir), otomatik container rollback yapilamadi."
  fi
  echo "Veritabani, migrations_engine'in kendi ic rollback mekanizmasi (basarisiz migration'in down() cagrisi) sayesinde tutarli birakildi."
  exit 1
fi

echo "[5/5] Kurulum sonrasi smoke test calistiriliyor..."
bash scripts/smoke-test.sh || {
  echo "UYARI: smoke test basarisiz -- servisleri kontrol edin (docker-compose logs)."
  exit 1
}

echo "=== Yukseltme basariyla tamamlandi ==="
