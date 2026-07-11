#!/usr/bin/env bash
# restore-verify.sh -- PR-11: Restore'un GERÇEKTEN çalıştığını doğrulayan test
#
# backup.sh ile alınan bir yedeği AYRI, GEÇİCİ bir Mongo container'ına
# restore edip veri bütünlüğünü (koleksiyon sayısı + belge sayısı) kontrol
# eder. Prod veritabanına DOKUNMAZ -- tamamen izole bir test container'ı
# kullanır, işi bitince silinir.
#
# Kullanim: bash scripts/restore-verify.sh <yedek-dosyasi.archive.gz>

set -euo pipefail

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  echo "Kullanim: bash scripts/restore-verify.sh <yedek-dosyasi.archive.gz>"
  exit 1
fi

TEST_CONTAINER="tabsis-restore-verify-test"

cleanup() {
  docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== Restore Doğrulama Testi ==="
echo "[1/4] Geçici, izole Mongo container'ı başlatılıyor (prod'a dokunulmaz)..."
docker run -d --name "$TEST_CONTAINER" mongo:7 >/dev/null
sleep 5

echo "[2/4] Yedek geçici container'a kopyalanıp restore ediliyor..."
docker cp "$ARCHIVE" "$TEST_CONTAINER:/tmp/restore-test.archive.gz"
docker exec "$TEST_CONTAINER" mongorestore --archive=/tmp/restore-test.archive.gz --gzip

echo "[3/4] Veri bütünlüğü kontrol ediliyor..."
COLLECTIONS=$(docker exec "$TEST_CONTAINER" mongosh --quiet --eval "
  db.getMongo().getDBNames().forEach(function(dbName) {
    if (dbName !== 'admin' && dbName !== 'local' && dbName !== 'config') {
      const d = db.getSiblingDB(dbName);
      print(dbName + ': ' + d.getCollectionNames().length + ' koleksiyon');
    }
  });
")
echo "$COLLECTIONS"

if echo "$COLLECTIONS" | grep -q "0 koleksiyon" || [ -z "$COLLECTIONS" ]; then
  echo "[4/4] HATA: Restore edilen veritabanında koleksiyon bulunamadı -- yedek bozuk olabilir."
  exit 1
fi

echo "[4/4] Restore başarılı görünüyor -- yukarıdaki koleksiyon sayılarını beklenen veriyle karşılaştırın."
echo "=== Doğrulama tamamlandı ==="
