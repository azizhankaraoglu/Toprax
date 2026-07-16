"""
=====================================================================
Toprax — Merkezi Konfigürasyon Servisi (IT-01)
=====================================================================
Tüm ortam değişkenleri, sabitler ve rol hiyerarşisi burada toplanır.
Diğer TÜM backend modülleri ayarlarını buradan import eder — env
değişkeni okuma (os.environ) başka hiçbir dosyada YAPILMAMALIDIR.

Geriye dönük uyumluluk: `config.py` bu modülü re-export eden ince bir
shim'e dönüştürüldü (eski `from config import X` importları bozulmadan
çalışmaya devam eder). Yeni kod doğrudan `config_service`'ten import
etmeli.
"""
import os
import re
import logging

APP_NAME = "Toprax"
APP_FULL_NAME = "Toprax — Tarımsal Operasyon ve Karar Destek Platformu"
APP_VERSION = "2.0.0"


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Zorunlu ortam değişkeni eksik: {key}. "
            f".env dosyasını .env.example'a göre doldurun."
        )
    return value


# ============ VERİTABANI ============
MONGO_URL = _require_env("MONGO_URL")
DB_NAME = _require_env("DB_NAME")

# ============ ORTAM ============
# ENVIRONMENT=production iken aşağıdaki zayıf/varsayılan secret'lar ve
# seed uçları fail-fast ile reddedilir — sessizce zayıf bir üretim
# ortamına izin vermek yerine uygulama hiç açılmaz.
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# ============ JWT ============
_DEV_JWT_SECRET = "toprax-dev-only-secret-DEGISTIR"
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    if IS_PRODUCTION:
        raise RuntimeError(
            "JWT_SECRET .env dosyasında tanımlı değil. ENVIRONMENT=production iken "
            "zorunludur — zayıf/varsayılan bir secret ile üretime çıkılamaz."
        )
    # Sadece geliştirme ortamında sabit bir değere düşülür, uyarı loglanır.
    JWT_SECRET = _DEV_JWT_SECRET
    logging.getLogger(__name__).warning(
        "⚠️  JWT_SECRET .env dosyasında tanımlı değil! Geliştirme secret'ı kullanılıyor. "
        "ÜRETİMDE MUTLAKA .env içinde güçlü bir JWT_SECRET tanımlayın."
    )
elif IS_PRODUCTION and JWT_SECRET == _DEV_JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET geliştirme değeriyle (toprax-dev-only-secret-DEGISTIR) üretimde "
        "çalıştırılamaz. .env dosyasında güçlü, benzersiz bir secret tanımlayın."
    )

JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 30

# ============ CORS ============
# .env içinde CORS_ORIGINS="https://toprax.example.com,https://app.example.com"
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

# ============ GOZLEMLENEBILIRLIK (PR-12) ============
# Bos ise hata izleme devre disi kalir (varsayilan, sifir davranis
# degisikligi). Doldurulursa herhangi bir Sentry-uyumlu servise (Sentry'nin
# kendisi VEYA self-hosted GlitchTip -- on-premise/KVKK hassasiyeti olan
# musteriler icin onerilir, ROADMAP-URUNLESTIRME.md PR-12 notu) baglanir.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()

# ============ PLATFORM ADMIN BOOTSTRAP ============
# İlk açılışta hiç platform_admin yoksa bu bilgilerle otomatik oluşturulur.
_DEV_PLATFORM_ADMIN_PASSWORD = "DEGISTIR-platform-admin-2026"
PLATFORM_ADMIN_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "platform@toprax.local")
PLATFORM_ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD")
if not PLATFORM_ADMIN_PASSWORD:
    if IS_PRODUCTION:
        raise RuntimeError(
            "PLATFORM_ADMIN_PASSWORD .env dosyasında tanımlı değil. ENVIRONMENT=production "
            "iken zorunludur — kaynak kodundaki varsayılan şifreyle üretime çıkılamaz."
        )
    PLATFORM_ADMIN_PASSWORD = _DEV_PLATFORM_ADMIN_PASSWORD
elif IS_PRODUCTION and PLATFORM_ADMIN_PASSWORD == _DEV_PLATFORM_ADMIN_PASSWORD:
    raise RuntimeError(
        "PLATFORM_ADMIN_PASSWORD geliştirme varsayılanıyla üretimde çalıştırılamaz. "
        ".env dosyasında güçlü, benzersiz bir şifre tanımlayın."
    )

# ============ SEED VERİSİ KORUMASI ============
# /admin/seed, /admin/seed-extras, /admin/seed-forms gibi uçlar demo veri
# yükler/sıfırlar — üretimde varsayılan olarak KAPALIDIR (fail-closed).
# Geliştirmede varsayılan olarak açıktır. ENVIRONMENT ne olursa olsun
# ALLOW_DATA_SEEDING ile elle override edilebilir (ör. staging'de açmak için).
_allow_seed_env = os.environ.get("ALLOW_DATA_SEEDING")
if _allow_seed_env is None:
    ALLOW_DATA_SEEDING = not IS_PRODUCTION
else:
    ALLOW_DATA_SEEDING = _allow_seed_env.strip().lower() in ("1", "true", "yes")

# ============ ENTEGRASYON VARSAYILANLARI (IT-01) ============
# Integration Center'daki her entegrasyon tipi (SMS/Email/Planet Labs/AI)
# bu varsayılanları kullanır; entegrasyon dokümanında per-tip override
# tanımlanmışsa o değer geçerli olur (bkz. integrations.py).
INTEGRATION_TIMEOUT_SECONDS = int(os.environ.get("INTEGRATION_TIMEOUT_SECONDS", "10"))
INTEGRATION_RETRY_COUNT = int(os.environ.get("INTEGRATION_RETRY_COUNT", "1"))

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


# ============ SİSTEM ROLLERİ KATMANI (IT-07) ============
# Mevcut 8-rol + platform_admin yapısını DEĞİŞTİRMEZ — bunun ÜZERİNE kaba
# (4 kademeli) bir sınıflandırma ekler. Amaç: rol bazlı ince ayrım
# (permissions.py) gerekmeyen, sadece "ne kadar üst seviye" sorusuna
# ihtiyaç duyan çapraz-kesen kararlar (örn. Field-Level Security eşiği,
# gelecekte sistem geneli özellik bayrakları). ADMIN_TIER_ROLES ile
# bilerek aynı sınırı kullanır — "kurum-geneli işlemlere erişebilir"
# tanımı zaten var olan bir kavramdı, burada isimlendirildi.
SYSTEM_TIER_LABELS = {
    "god_mode": "God Mode (Platform)",
    "super_admin": "Süper Admin",
    "admin": "Admin",
    "user": "Kullanıcı",
}


def get_system_tier(role: str) -> str:
    """Bir rolün 4 kademeli sistem katmanını döner: god_mode / super_admin / admin / user."""
    if role == "platform_admin":
        return "god_mode"
    if role == "super_admin":
        return "super_admin"
    if role in ADMIN_TIER_ROLES:
        return "admin"
    return "user"


def has_min_role(user_role: str, required_role: str) -> bool:
    """user_role, required_role veya daha yetkili bir seviyede mi?"""
    return role_level(user_role) <= role_level(required_role)


# ============ LOG'LARDA SECRET MASKELEME (IT-01) ============
# .env'deki hassas değerler (JWT_SECRET, platform admin şifresi, Mongo
# bağlantı URI'sindeki kullanıcı/şifre) yanlışlıkla bir log satırına
# karışırsa düz metin olarak diske/konsola yazılmasın diye maskelenir.
# NOT: Integration Center'daki entegrasyon secret'ları (SMS/Email/API key)
# zaten kendi modülünde (integrations.py `_mask_config`) DB seviyesinde
# maskeleniyor — burası sadece .env kaynaklı secret'ları kapsar.

def _mask_value(value: str) -> str:
    if not value:
        return value
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def _mongo_credentials(mongo_url: str) -> list:
    """mongodb://user:pass@host şeklindeki URI'den şifre parçasını çıkarır."""
    match = re.search(r"://[^:/@]+:([^@]+)@", mongo_url)
    return [match.group(1)] if match else []


def _known_secrets() -> list:
    secrets_ = [JWT_SECRET, PLATFORM_ADMIN_PASSWORD]
    secrets_.extend(_mongo_credentials(MONGO_URL))
    # Kısa/varsayılan/boş değerleri maskeleme listesine ekleme — anlamsız
    # ve yanlışlıkla masum kısa string'leri (örn. "24") maskeler.
    return [s for s in secrets_ if s and len(s) >= 6]


class _SecretMaskingFilter(logging.Filter):
    def __init__(self, secrets_):
        super().__init__()
        self._secrets = secrets_

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        masked = msg
        for secret in self._secrets:
            if secret in masked:
                masked = masked.replace(secret, _mask_value(secret))
        if masked != msg:
            record.msg = masked
            record.args = ()
        return True


_masking_installed = False


def install_secret_masking() -> None:
    """Root logger'a secret-maskeleme filtresini ekler. Uygulama başlangıcında
    (server.py) bir kez çağrılır; tekrar çağrılırsa no-op'tur."""
    global _masking_installed
    if _masking_installed:
        return
    filt = _SecretMaskingFilter(_known_secrets())
    logging.getLogger().addFilter(filt)
    _masking_installed = True
