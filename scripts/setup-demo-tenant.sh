#!/usr/bin/env bash
# setup-demo-tenant.sh -- PR-18: Demo Tenant + Gerçekçi Sahte Veri
#
# Satış gösterimi için, GERÇEK (prod) tenant'lardan tamamen ayrı, gerçekçi
# demo veriyle dolu bir tenant oluşturur. Mevcut idempotent seed uçlarını
# (server.py /admin/seed, extras.py /admin/seed-extras, forms_module.py
# /admin/seed-forms) YENİDEN YAZMAZ -- sadece bunları doğru sırayla,
# dedike bir "Demo Kooperatifi" tenant'ı bağlamında çağırır.
#
# ÖN KOŞUL: ALLOW_DATA_SEEDING=true olmalı (.env) -- üretimde varsayılan
# kapalıdır, bu script SADECE demo/staging ortamında çalıştırılmalıdır.
#
# Kullanim: bash scripts/setup-demo-tenant.sh <base_url> <platform_admin_email> <platform_admin_password>

set -euo pipefail

BASE_URL="${1:-http://localhost:8001}"
PLATFORM_EMAIL="${2:?platform admin e-postası gerekli}"
PLATFORM_PASSWORD="${3:?platform admin şifresi gerekli}"

DEMO_EMAIL="demo-admin@tabsis-demo.local"
DEMO_PASSWORD="Demo-$(date +%s)-Sunum!"

echo "=== TABSIS Demo Tenant Kurulumu ==="

echo "[1/5] Platform yöneticisi olarak giriş yapılıyor..."
PLATFORM_TOKEN=$(curl -fsS -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$PLATFORM_EMAIL\",\"password\":\"$PLATFORM_PASSWORD\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "[2/5] 'Demo Kooperatifi' tenant'ı oluşturuluyor..."
TENANT_ID=$(curl -fsS -X POST "$BASE_URL/api/platform/tenants" \
  -H "Authorization: Bearer $PLATFORM_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"TabSIS Demo Kooperatifi (Satış Gösterimi)","contact_email":"demo@tabsis-demo.local","plan":"deneme"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  tenant_id: $TENANT_ID"

echo "[3/5] Demo tenant süper admini oluşturuluyor..."
curl -fsS -X POST "$BASE_URL/api/platform/tenants/$TENANT_ID/bootstrap-admin" \
  -H "Authorization: Bearer $PLATFORM_TOKEN" -H "Content-Type: application/json" \
  -d "{\"admin_email\":\"$DEMO_EMAIL\",\"admin_password\":\"$DEMO_PASSWORD\",\"admin_full_name\":\"Demo Yöneticisi\"}" >/dev/null

echo "[4/5] Demo admin olarak giriş yapılıp seed uçları çağrılıyor..."
DEMO_TOKEN=$(curl -fsS -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$DEMO_EMAIL\",\"password\":\"$DEMO_PASSWORD\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -fsS -X POST "$BASE_URL/api/admin/seed?force=true" -H "Authorization: Bearer $DEMO_TOKEN" >/dev/null
curl -fsS -X POST "$BASE_URL/api/admin/seed-extras" -H "Authorization: Bearer $DEMO_TOKEN" >/dev/null || true
curl -fsS -X POST "$BASE_URL/api/admin/seed-forms" -H "Authorization: Bearer $DEMO_TOKEN" >/dev/null || true

echo "[5/5] Tamamlandı."
echo
echo "=== Demo Tenant Bilgileri ==="
echo "Giriş: $DEMO_EMAIL / $DEMO_PASSWORD"
echo "Bu bilgileri güvenli bir şekilde saklayın -- şifre bir daha gösterilmez."
