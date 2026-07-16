#!/usr/bin/env bash
# provision-tenant.sh -- PR-19: Tenant Provisioning Otomasyonu
#
# Yeni bir GERÇEK müşteri geldiğinde tenant açma sürecini tek komuta
# indirger -- elle yapılan her adım (Postman'da elle tıklama vb.) hata
# kaynağıdır. tenants.py'deki mevcut uçları YENİDEN YAZMAZ, sadece
# doğru sırayla çağırır (aynı desen setup-demo-tenant.sh ile, farkı:
# bu GERÇEK müşteri verisi için, seed ÇAĞIRMAZ).
#
# Kullanim:
#   bash scripts/provision-tenant.sh <base_url> <platform_email> <platform_password> \
#        <kurum_adi> <kurum_email> <admin_email> <admin_ad_soyad>
#
# Admin şifresi rastgele üretilir ve SADECE ekrana bir kez yazdırılır --
# ilk girişte değiştirilmesi önerilir.

set -euo pipefail

BASE_URL="${1:?}"
PLATFORM_EMAIL="${2:?}"
PLATFORM_PASSWORD="${3:?}"
KURUM_ADI="${4:?kurum adı gerekli}"
KURUM_EMAIL="${5:?kurum iletişim e-postası gerekli}"
ADMIN_EMAIL="${6:?admin e-postası gerekli}"
ADMIN_AD_SOYAD="${7:?admin ad soyad gerekli}"

ADMIN_PASSWORD="$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits+'!@#$') for _ in range(16)))")"

echo "=== Yeni Tenant Provisioning: $KURUM_ADI ==="

echo "[1/3] Platform yöneticisi girişi..."
PLATFORM_TOKEN=$(curl -fsS -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$PLATFORM_EMAIL\",\"password\":\"$PLATFORM_PASSWORD\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "[2/3] Tenant oluşturuluyor..."
TENANT_JSON=$(curl -fsS -X POST "$BASE_URL/api/platform/tenants" \
  -H "Authorization: Bearer $PLATFORM_TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\":\"$KURUM_ADI\",\"contact_email\":\"$KURUM_EMAIL\",\"plan\":\"standard\"}")
TENANT_ID=$(echo "$TENANT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  tenant_id: $TENANT_ID"

echo "[3/3] İlk süper admin oluşturuluyor..."
curl -fsS -X POST "$BASE_URL/api/platform/tenants/$TENANT_ID/bootstrap-admin" \
  -H "Authorization: Bearer $PLATFORM_TOKEN" -H "Content-Type: application/json" \
  -d "{\"admin_email\":\"$ADMIN_EMAIL\",\"admin_password\":\"$ADMIN_PASSWORD\",\"admin_full_name\":\"$ADMIN_AD_SOYAD\"}" >/dev/null

echo
echo "=== Tamamlandı (tenant_id: $TENANT_ID) ==="
echo "İlk giriş bilgileri: $ADMIN_EMAIL / $ADMIN_PASSWORD"
echo "Bu şifreyi güvenli bir kanaldan müşteriye iletin ve ilk girişte değiştirmesini isteyin."
