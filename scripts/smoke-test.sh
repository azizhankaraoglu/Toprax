#!/usr/bin/env bash
# smoke-test.sh -- PR-07: Kurulum Sonrasi Health-Check + Smoke Test
#
# docker-compose up -d sonrasi (kurulum sihirbazinin son adimi olarak veya
# upgrade.sh tarafindan) calistirilir. Servislerin gercekten ayakta ve
# calisir durumda oldugunu dogrular, net "basarili/basarisiz" raporu verir.
#
# Kullanim: bash scripts/smoke-test.sh [base_url]
#   base_url varsayilan: http://localhost:8001
#
# Cikis kodu: 0 = tum kontroller basarili, 1 = en az biri basarisiz.

set -uo pipefail

BASE_URL="${1:-http://localhost:8001}"
FRONTEND_URL="${2:-http://localhost:3000}"
MAX_RETRIES=20
RETRY_DELAY=3

GREEN=$'\033[32m'; RED=$'\033[31m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
PASS=1

ok()   { echo "  ${GREEN}[OK]${RESET} $1"; }
fail() { echo "  ${RED}[HATA]${RESET} $1"; PASS=0; }

echo "${BOLD}=== TABSIS Kurulum Sonrasi Smoke Test ===${RESET}"
echo "Backend:  $BASE_URL"
echo "Frontend: $FRONTEND_URL"
echo

# ---- 1) Backend /api/health hazir olana kadar bekle ----
echo "${BOLD}1) Backend saglik kontrolu${RESET}"
ready=0
for i in $(seq 1 $MAX_RETRIES); do
  BODY=$(curl -fsS "$BASE_URL/api/health" 2>/dev/null)
  if [ $? -eq 0 ] && echo "$BODY" | grep -q '"status":"healthy"'; then
    ready=1
    break
  fi
  echo "  ...bekleniyor ($i/$MAX_RETRIES)"
  sleep "$RETRY_DELAY"
done
if [ "$ready" -eq 1 ]; then
  ok "Backend saglikli: $BODY"
else
  fail "Backend $((MAX_RETRIES * RETRY_DELAY)) saniye icinde saglikli duruma gelmedi. 'docker-compose logs backend' kontrol edin."
fi
echo

# ---- 2) Kok endpoint (versiyon bilgisi) ----
echo "${BOLD}2) API kok endpoint${RESET}"
ROOT_BODY=$(curl -fsS "$BASE_URL/api/" 2>/dev/null)
if [ $? -eq 0 ] && echo "$ROOT_BODY" | grep -q '"status":"ok"'; then
  ok "GET /api/ basarili: $ROOT_BODY"
else
  fail "GET /api/ basarisiz veya beklenmeyen yanit."
fi
echo

# ---- 3) Login endpoint erisilebilir mi (401/422 de kabul -- servisin ayakta olmasi onemli) ----
echo "${BOLD}3) Login endpoint erisilebilirligi${RESET}"
LOGIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" -d '{"email":"smoketest@invalid.local","password":"x"}' 2>/dev/null)
if [ "$LOGIN_CODE" = "401" ] || [ "$LOGIN_CODE" = "400" ] || [ "$LOGIN_CODE" = "422" ]; then
  ok "POST /api/auth/login erisilebilir (HTTP $LOGIN_CODE -- beklenen: gecersiz kimlik reddi)"
elif [ "$LOGIN_CODE" = "000" ]; then
  fail "POST /api/auth/login'e erisilemedi (baglanti hatasi)."
else
  fail "POST /api/auth/login beklenmeyen durum kodu dondu: $LOGIN_CODE"
fi
echo

# ---- 4) Frontend erisilebilir mi ----
echo "${BOLD}4) Frontend${RESET}"
FRONT_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL/" 2>/dev/null)
if [ "$FRONT_CODE" = "200" ]; then
  ok "Frontend erisilebilir (HTTP 200)"
else
  fail "Frontend'e erisilemedi (HTTP $FRONT_CODE). 'docker-compose logs frontend' kontrol edin."
fi
echo

# ---- Ozet ----
echo "${BOLD}=== Sonuc ===${RESET}"
if [ "$PASS" -eq 1 ]; then
  echo "${GREEN}Kurulum basarili -- tum kritik uclar calisiyor.${RESET}"
  exit 0
else
  echo "${RED}Kurulumda sorun tespit edildi -- yukaridaki [HATA] satirlarina bakin.${RESET}"
  exit 1
fi
