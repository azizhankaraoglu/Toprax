"""
=====================================================================
TabSIS — Merkezi Konfigürasyon
=====================================================================
Tüm sabit değerler, ortam değişkenleri ve rol hiyerarşisi burada
toplanır. server.py ve diğer modüller buradan import eder.
"""
import os
import logging

APP_NAME = "TabSIS"
APP_FULL_NAME = "TabSIS — Tarımsal Operasyon ve Karar Destek Platformu"
APP_VERSION = "2.0.0"

# ============ JWT ============
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    # Prod'da .env'de mutlaka tanımlanmalı. Yoksa dev için sabit bir
    # değer kullanılır ama uyarı loglanır (sessizce zayıf secret kullanmak yerine).
    JWT_SECRET = "tabsis-dev-only-secret-DEGISTIR"
    logging.getLogger(__name__).warning(
        "⚠️  JWT_SECRET .env dosyasında tanımlı değil! Geliştirme secret'ı kullanılıyor. "
        "ÜRETİMDE MUTLAKA .env içinde güçlü bir JWT_SECRET tanımlayın."
    )

JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 30

# ============ CORS ============
# .env içinde CORS_ORIGINS="https://tabsis.example.com,https://app.example.com"
# şeklinde virgülle ayrılmış domain listesi verilebilir.
# Tanımlı değilse yerel geliştirme domain'lerine düşer (wildcard KULLANILMAZ,
# çünkü allow_credentials=True ile allow_origins=["*"] birlikte tarayıcılar
# tarafından reddedilir ve güvenlik açığıdır).
_cors_env = os.environ.get("CORS_ORIGINS", "")
if _cors_env.strip():
    CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    CORS_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

# ============ ROL HİYERARŞİSİ ============
# Sayı küçüldükçe yetki artar (0 = en yetkili).
# Eski roller (super_admin, fabrika_muduru, ziraat_muhendisi, ciftci) korunuyor,
# yeni kurumsal katman rolleri eklendi.
ROLE_HIERARCHY = {
    "super_admin":        0,   # Sistem Yöneticisi
    "kurum_yoneticisi":   1,   # Kurum (örn. Türkşeker genel merkez)
    "il_yoneticisi":      2,   # İl
    "ilce_yoneticisi":    3,   # İlçe
    "fabrika_muduru":     4,   # Kooperatif / Fabrika Müdürü
    "ziraat_muhendisi":   5,   # Ziraat Mühendisi
    "saha_personeli":     6,   # Saha Personeli (genel)
    "kantar_personeli":   6,   # Kantar / Tartı Operatörü (saha ile aynı kademe, farklı uzmanlık)
    "toprak_personeli":   6,   # Toprak/Numune Alma Personeli (saha ile aynı kademe, farklı uzmanlık)
    "ciftci":             7,   # Çiftçi
}

ROLE_LABELS = {
    "platform_admin": "Platform Yöneticisi (tenant'lar-arası)",
    "super_admin": "Sistem Yöneticisi",
    "kurum_yoneticisi": "Kurum Yöneticisi",
    "il_yoneticisi": "İl Yöneticisi",
    "ilce_yoneticisi": "İlçe Yöneticisi",
    "fabrika_muduru": "Kooperatif / Fabrika Müdürü",
    "ziraat_muhendisi": "Ziraat Mühendisi",
    "saha_personeli": "Saha Personeli",
    "kantar_personeli": "Kantar Personeli",
    "toprak_personeli": "Toprak / Numune Personeli",
    "ciftci": "Çiftçi",
}

# "Admin katmanı" olarak kabul edilen roller (ayarlar/entegrasyonlar gibi
# kurum-geneli işlemlere erişebilir).
ADMIN_TIER_ROLES = {"super_admin", "kurum_yoneticisi", "il_yoneticisi", "fabrika_muduru"}


def role_level(role: str) -> int:
    """Bilinmeyen rol için en düşük yetkiyi (en büyük sayı) döner — güvenli varsayılan."""
    return ROLE_HIERARCHY.get(role, 99)


def has_min_role(user_role: str, required_role: str) -> bool:
    """user_role, required_role veya daha yetkili bir seviyede mi?"""
    return role_level(user_role) <= role_level(required_role)
