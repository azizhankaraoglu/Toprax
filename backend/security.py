"""
=====================================================================
Toprax — Güvenlik Yardımcıları
=====================================================================
Şifre hash'leme (bcrypt) ve refresh token üretimi.

NOT: Eski sistemde SHA256 kullanılıyordu. Bu dosya bcrypt'e geçişi
sağlar. Geriye dönük uyumluluk için verify_password hem bcrypt hem
eski SHA256 hash'lerini tanıyabilir; SHA256 ile doğrulanan bir şifre
otomatik olarak bcrypt'e yükseltilir (login sırasında, server.py'de).
"""
import bcrypt
import hashlib
import secrets
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from config_service import JWT_SECRET, JWT_ALG, ACCESS_TOKEN_EXPIRE_HOURS, REFRESH_TOKEN_EXPIRE_DAYS


def hash_password(plain: str) -> str:
    """Yeni şifreleri bcrypt ile hash'ler."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _legacy_sha256(plain: str) -> str:
    """Eski (zayıf) SHA256 hash — sadece geriye dönük doğrulama için."""
    return hashlib.sha256(plain.encode()).hexdigest()


def verify_password(plain: str, stored_hash: str) -> bool:
    """
    Şifreyi doğrular. bcrypt hash'i ($2b$ ile başlar) veya eski SHA256
    hash'ini destekler.
    """
    if not stored_hash:
        return False
    if stored_hash.startswith("$2a$") or stored_hash.startswith("$2b$") or stored_hash.startswith("$2y$"):
        try:
            return bcrypt.checkpw(plain.encode(), stored_hash.encode())
        except ValueError:
            return False
    # Eski SHA256 hash ile geriye dönük uyumluluk
    return secrets.compare_digest(_legacy_sha256(plain), stored_hash)


def needs_rehash(stored_hash: str) -> bool:
    """Şifre hâlâ eski SHA256 formatındaysa True döner (login sonrası bcrypt'e yükseltilmeli)."""
    return not (stored_hash.startswith("$2a$") or stored_hash.startswith("$2b$") or stored_hash.startswith("$2y$"))


def make_access_token(user_id: str, role: str, farmer_id: str = None, tenant_id: str = None) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "farmer_id": farmer_id,
        "tenant_id": tenant_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def make_refresh_token(user_id: str, tenant_id: str = None) -> str:
    """
    Refresh token — sadece user_id + uzun ömür içerir, rol bilgisi taşımaz
    (rol değişse bile refresh sırasında DB'den güncel rol çekilir).
    tenant_id de taşınır ki refresh sonrası yeni access token doğru
    tenant'a ait olsun.
    """
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "type": "refresh",
        "jti": secrets.token_hex(16),  # tekil id — istenirse iptal listesi için kullanılabilir
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    """Süresi dolmuş veya geçersizse jwt.PyJWTError fırlatır (çağıran yakalamalı)."""
    return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
