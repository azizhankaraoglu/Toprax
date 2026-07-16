#!/usr/bin/env bash
# backup.sh -- PR-11: Otomatik MongoDB Yedekleme
#
# Kullanim: bash scripts/backup.sh [cikti-dizini]
#           (varsayilan: ./backups/)
#
# Cron ornegi (her gece 03:00'te, son 14 yedegi tutar):
#   0 3 * * * cd /path/to/toprax && bash scripts/backup.sh >> /var/log/toprax-backup.log 2>&1

set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RETENTION_DAYS=14

COMPOSE="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi

mkdir -p "$BACKUP_DIR"
DUMP_PATH="$BACKUP_DIR/toprax-$TIMESTAMP"

echo "=== TOPRAX Yedekleme: $TIMESTAMP ==="

# .env'den kimlik bilgilerini oku (docker-compose ile ayni kaynak)
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

echo "[1/3] mongodump calistiriliyor (container icinde)..."
docker exec toprax-mongo mongodump \
  --username "${MONGO_ROOT_USERNAME:?}" --password "${MONGO_ROOT_PASSWORD:?}" \
  --authenticationDatabase admin \
  --archive="/tmp/toprax-backup-$TIMESTAMP.archive" --gzip

echo "[2/3] Yedek container'dan host'a kopyalaniyor..."
docker cp "toprax-mongo:/tmp/toprax-backup-$TIMESTAMP.archive" "$DUMP_PATH.archive.gz"
docker exec toprax-mongo rm -f "/tmp/toprax-backup-$TIMESTAMP.archive"

echo "[3/3] ${RETENTION_DAYS} günden eski yedekler temizleniyor..."
find "$BACKUP_DIR" -name "toprax-*.archive.gz" -mtime +$RETENTION_DAYS -delete

BACKUP_SIZE=$(du -h "$DUMP_PATH.archive.gz" | cut -f1)
echo "=== Tamamlandı: $DUMP_PATH.archive.gz ($BACKUP_SIZE) ==="
echo "Restore'un GERÇEKTEN çalıştığını doğrulamak için: bash scripts/restore-verify.sh $DUMP_PATH.archive.gz"
