#!/usr/bin/env bash
# check-requirements.sh — TOPRAX on-premise kurulum ON-KOSUL kontrolcusu (PR-03)
#
# docker-compose up'tan ONCE calistirilir. Docker henuz kurulu/calisir
# olmayabilir, bu yuzden script yalnizca standart POSIX araclarina (bash,
# awk, df, nproc/sysctl) bagimlidir — Python/Docker gerektirmez.
#
# Kullanim:  bash scripts/check-requirements.sh
# Cikis kodu: 0 = tum kontroller gecti, 1 = en az bir zorunlu kontrol basarisiz.
#
# NOT (is karari): Asagidaki MIN_RAM_GB/MIN_DISK_GB/MIN_CPU_CORE varsayilan
# esikleridir. Gercek kapasite plani (kac tenant / kac eszamanli kullanici
# hedeflendigi) musteriye ozel bir is karari oldugu icin ROADMAP-URUNLESTIRME.md
# PR-03 notuna gore nihai rakamlari siz onaylamalisiniz; asagidaki degerler
# makul bir baslangic tahminidir, degistirmek icin bu dosyanin basindaki
# degiskenleri guncelleyin.

set -uo pipefail

MIN_CPU_CORE=2
MIN_RAM_GB=4
MIN_DISK_GB=20
REQUIRED_DOCKER_MAJOR=24
REQUIRED_PORTS=(80 443 3000 8001)

PASS=1
BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

ok()   { echo "  ${GREEN}[OK]${RESET} $1"; }
fail() { echo "  ${RED}[HATA]${RESET} $1"; PASS=0; }
warn() { echo "  ${YELLOW}[UYARI]${RESET} $1"; }

echo "${BOLD}=== TOPRAX Kurulum On-Kosul Kontrolu ===${RESET}"
echo

# ---- 1) Isletim sistemi ----
OS_NAME="$(uname -s)"
echo "${BOLD}Isletim Sistemi${RESET}"
case "$OS_NAME" in
  Linux)  ok "Linux tespit edildi." ;;
  Darwin) ok "macOS tespit edildi." ;;
  MINGW*|MSYS*|CYGWIN*) warn "Windows (Git Bash/WSL) tespit edildi — Docker Desktop + WSL2 gereklidir." ;;
  *) warn "Bilinmeyen isletim sistemi: $OS_NAME" ;;
esac
echo

# ---- 2) CPU cekirdek sayisi ----
echo "${BOLD}CPU${RESET}"
if command -v nproc >/dev/null 2>&1; then
  CPU_CORES=$(nproc)
elif command -v sysctl >/dev/null 2>&1; then
  CPU_CORES=$(sysctl -n hw.ncpu)
else
  CPU_CORES=0
fi
if [ "$CPU_CORES" -ge "$MIN_CPU_CORE" ]; then
  ok "CPU cekirdek sayisi: $CPU_CORES (min $MIN_CPU_CORE gerekli)"
else
  fail "CPU cekirdek sayisi yetersiz: $CPU_CORES bulundu, en az $MIN_CPU_CORE gerekli."
fi
echo

# ---- 3) RAM ----
echo "${BOLD}RAM${RESET}"
if [ "$OS_NAME" = "Linux" ]; then
  RAM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
  RAM_GB=$(( RAM_KB / 1024 / 1024 ))
elif [ "$OS_NAME" = "Darwin" ]; then
  RAM_BYTES=$(sysctl -n hw.memsize)
  RAM_GB=$(( RAM_BYTES / 1024 / 1024 / 1024 ))
else
  RAM_GB=0
  warn "RAM otomatik tespit edilemedi (desteklenmeyen OS) — elle dogrulayin."
fi
if [ "$RAM_GB" -ge "$MIN_RAM_GB" ]; then
  ok "Toplam RAM: ${RAM_GB}GB (min ${MIN_RAM_GB}GB gerekli)"
elif [ "$RAM_GB" -gt 0 ]; then
  fail "RAM yetersiz: ${RAM_GB}GB bulundu, en az ${MIN_RAM_GB}GB gerekli."
fi
echo

# ---- 4) Disk alani (mevcut dizin) ----
echo "${BOLD}Disk Alani${RESET}"
DISK_AVAIL_KB=$(df -Pk . | awk 'NR==2 {print $4}')
DISK_AVAIL_GB=$(( DISK_AVAIL_KB / 1024 / 1024 ))
if [ "$DISK_AVAIL_GB" -ge "$MIN_DISK_GB" ]; then
  ok "Bos disk alani: ${DISK_AVAIL_GB}GB (min ${MIN_DISK_GB}GB gerekli)"
else
  fail "Disk alani yetersiz: ${DISK_AVAIL_GB}GB bos, en az ${MIN_DISK_GB}GB gerekli."
fi
echo

# ---- 5) Docker ----
echo "${BOLD}Docker${RESET}"
if command -v docker >/dev/null 2>&1; then
  DOCKER_VERSION_RAW=$(docker version --format '{{.Server.Version}}' 2>/dev/null || docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  DOCKER_MAJOR=$(echo "$DOCKER_VERSION_RAW" | cut -d. -f1)
  if [ -z "$DOCKER_VERSION_RAW" ]; then
    fail "Docker kurulu ama versiyon tespit edilemedi — Docker daemon calisiyor mu kontrol edin (docker info)."
  elif [ "$DOCKER_MAJOR" -ge "$REQUIRED_DOCKER_MAJOR" ] 2>/dev/null; then
    ok "Docker versiyonu: $DOCKER_VERSION_RAW (min ${REQUIRED_DOCKER_MAJOR}.x gerekli)"
  else
    fail "Docker versiyonu eski: $DOCKER_VERSION_RAW bulundu, ${REQUIRED_DOCKER_MAJOR}+ gerekli. https://www.docker.com/products/docker-desktop/ adresinden guncelleyin."
  fi
else
  fail "Docker kurulu degil. https://www.docker.com/products/docker-desktop/ adresinden kurun."
fi

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    ok "docker compose (plugin) mevcut: $(docker compose version --short 2>/dev/null)"
  elif command -v docker-compose >/dev/null 2>&1; then
    ok "docker-compose (standalone) mevcut: $(docker-compose --version)"
  else
    fail "docker compose plugin veya docker-compose bulunamadi. Docker Desktop ile birlikte gelir; ayri kurulumda 'sudo apt install docker-compose-plugin' calistirin."
  fi
fi
echo

# ---- 6) Gerekli portlar bos mu ----
echo "${BOLD}Portlar${RESET}"
port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${port}\$"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  elif command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -qE "[:.]${port}[[:space:]].*LISTEN"
  else
    return 1
  fi
}
for port in "${REQUIRED_PORTS[@]}"; do
  if port_in_use "$port"; then
    fail "Port $port dolu — bu portu kullanan servisi durdurun veya docker-compose.yml'de port eslemesini degistirin."
  else
    ok "Port $port bos."
  fi
done
echo

# ---- Ozet ----
echo "${BOLD}=== Sonuc ===${RESET}"
if [ "$PASS" -eq 1 ]; then
  echo "${GREEN}Tum kontroller basarili. 'docker-compose up -d' ile kuruluma devam edebilirsiniz.${RESET}"
  exit 0
else
  echo "${RED}Bir veya daha fazla kontrol basarisiz oldu. Yukaridaki [HATA] satirlarini duzeltip scripti tekrar calistirin.${RESET}"
  exit 1
fi
