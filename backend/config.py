"""
=====================================================================
Toprax — config.py (DEPRECATED — geriye dönük uyumluluk shim'i)
=====================================================================
IT-01 ile tüm ayarlar `config_service.py`'ye taşındı. Bu dosya sadece
eski `from config import X` importlarının kırılmaması için var.

YENİ KOD BURADAN IMPORT ETMEMELİ — doğrudan `config_service` kullanın.
"""
from config_service import (  # noqa: F401
    APP_NAME, APP_FULL_NAME, APP_VERSION,
    MONGO_URL, DB_NAME,
    JWT_SECRET, JWT_ALG, ACCESS_TOKEN_EXPIRE_HOURS, REFRESH_TOKEN_EXPIRE_DAYS,
    CORS_ORIGINS,
    PLATFORM_ADMIN_EMAIL, PLATFORM_ADMIN_PASSWORD,
    INTEGRATION_TIMEOUT_SECONDS, INTEGRATION_RETRY_COUNT,
    ROLE_HIERARCHY, ROLE_LABELS, ADMIN_TIER_ROLES,
    role_level, has_min_role,
)
