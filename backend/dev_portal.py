"""dev_portal.py -- PR-26: Gelistirici / Entegrasyon Portali (backend).

Integration Center'in (IT-01/IT-32) disariya acik yuzunu tamamlar: Swagger
UI zaten FastAPI varsayilaniyla /docs'ta acik (server.py'de docs_url
override edilmedi) -- bu modul sadece Postman collection indirme ucunu ve
portal sayfasinin ihtiyac duydugu ozet bilgiyi (rate limit, changelog)
saglar. Webhook dokumantasyonu zaten integration_hub.py'de var (IT-32) --
burada tekrar YAZILMAZ, portal sayfasi ona link verir.
"""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

POSTMAN_DIR = Path(__file__).resolve().parent.parent / "postman"
CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def register_dev_portal_routes(api_router):
    @api_router.get("/dev-portal/info")
    async def dev_portal_info():
        """Kimlik dogrulamasiz -- portal sayfasinin genel bilgi bolumu icin.
        Hassas bilgi icermez (API key SAYISI bile donmez, sadece statik
        meta bilgi)."""
        return {
            "swagger_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
            "postman_collection_url": "/api/dev-portal/postman-collection",
            "postman_environment_url": "/api/dev-portal/postman-environment",
            "default_rate_limit_per_minute": 60,
            "rate_limit_note": "API Key başına ayarlanabilir (varsayılan 60/dakika) -- bkz. Ayarlar > Entegrasyonlar > API Anahtarlarım.",
            "webhook_docs_note": "Webhook kuralları için Ayarlar > Entegrasyonlar > Webhook Kuralları ekranına bakın (IT-32).",
        }

    @api_router.get("/dev-portal/postman-collection")
    async def download_postman_collection():
        path = POSTMAN_DIR / "toprax.postman_collection.json"
        if not path.exists():
            raise HTTPException(404, "Postman collection henüz üretilmemiş -- "
                                       "scripts/generate_postman_collection.py çalıştırın")
        return FileResponse(path, media_type="application/json",
                              filename="toprax.postman_collection.json")

    @api_router.get("/dev-portal/postman-environment")
    async def download_postman_environment():
        path = POSTMAN_DIR / "toprax.postman_environment.json"
        if not path.exists():
            raise HTTPException(404, "Postman environment henüz üretilmemiş")
        return FileResponse(path, media_type="application/json",
                              filename="toprax.postman_environment.json")

    @api_router.get("/dev-portal/changelog")
    async def get_changelog():
        if not CHANGELOG_PATH.exists():
            return {"markdown": "# Değişiklik Günlüğü\n\nHenüz kayıt yok."}
        return {"markdown": CHANGELOG_PATH.read_text(encoding="utf-8")}
