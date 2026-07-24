# Denetim Faz 4 — Ollama yerel LLM model indirme scripti (Windows).
# Ön koşul: Ollama Windows'a kurulu (https://ollama.com/download) VEYA
# docker-compose.ollama.yml ile konteynerde çalışıyor olmalı.
#
# Kullanım:
#   .\scripts\ollama-modelleri-indir.ps1                    # yerel kurulum (varsayılan)
#   .\scripts\ollama-modelleri-indir.ps1 -Container         # docker-compose.ollama.yml konteynerine indir

param(
    [switch]$Container
)

$TextModel = "llama3.1:8b"
$VisionModel = "llava:7b"

Write-Host "Toprax — Ollama model indirme" -ForegroundColor Cyan
Write-Host "Metin modeli   : $TextModel"
Write-Host "Görüntü modeli : $VisionModel"
Write-Host ""

if ($Container) {
    Write-Host "Konteyner modunda indiriliyor (toprax-ollama)..." -ForegroundColor Yellow
    docker exec toprax-ollama ollama pull $TextModel
    docker exec toprax-ollama ollama pull $VisionModel
} else {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Host "HATA: 'ollama' komutu bulunamadı. https://ollama.com/download adresinden kurun." -ForegroundColor Red
        exit 1
    }
    ollama pull $TextModel
    ollama pull $VisionModel
}

Write-Host ""
Write-Host "Tamamlandı. Ayarlar > Entegrasyonlar > AI Servisi > Yerel LLM (Ollama) bölümünden" -ForegroundColor Green
Write-Host "modelleri etkinleştirip URL'i girin (varsayılan: http://localhost:11434)." -ForegroundColor Green
