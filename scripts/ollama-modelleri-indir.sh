#!/usr/bin/env bash
# Denetim Faz 4 — Ollama yerel LLM model indirme scripti (Linux/macOS).
# Ön koşul: Ollama kurulu (https://ollama.com/download) VEYA
# docker-compose.ollama.yml ile konteynerde çalışıyor olmalı.
#
# Kullanım:
#   ./scripts/ollama-modelleri-indir.sh              # yerel kurulum (varsayılan)
#   ./scripts/ollama-modelleri-indir.sh --container   # docker-compose.ollama.yml konteynerine indir
set -euo pipefail

TEXT_MODEL="llama3.1:8b"
VISION_MODEL="llava:7b"

echo "Toprax — Ollama model indirme"
echo "Metin modeli   : ${TEXT_MODEL}"
echo "Görüntü modeli : ${VISION_MODEL}"
echo

if [[ "${1:-}" == "--container" ]]; then
    echo "Konteyner modunda indiriliyor (toprax-ollama)..."
    docker exec toprax-ollama ollama pull "${TEXT_MODEL}"
    docker exec toprax-ollama ollama pull "${VISION_MODEL}"
else
    if ! command -v ollama >/dev/null 2>&1; then
        echo "HATA: 'ollama' komutu bulunamadı. https://ollama.com/download adresinden kurun." >&2
        exit 1
    fi
    ollama pull "${TEXT_MODEL}"
    ollama pull "${VISION_MODEL}"
fi

echo
echo "Tamamlandı. Ayarlar > Entegrasyonlar > AI Servisi > Yerel LLM (Ollama) bölümünden"
echo "modelleri etkinleştirip URL'i girin (varsayılan: http://localhost:11434)."
