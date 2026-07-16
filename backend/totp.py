"""
=====================================================================
Toprax — TOTP (RFC 6238) — God Mode ikinci faktör
=====================================================================
Google Authenticator/Authy/Microsoft Authenticator ile uyumlu, standart
zaman tabanlı tek kullanımlık kod doğrulaması. BİLİNÇLİ OLARAK yeni bir
pip bağımlılığı (`pyotp` vb.) EKLENMEDİ — RFC 4226 (HOTP) + RFC 6238
(TOTP) sadece `hmac`/`hashlib`/`struct`/`base64` ile ~30 satırda doğru
şekilde uygulanabilir, Karar Protokolü'nün "yeni bağımlılık her zaman
sorulur" ilkesiyle tutarlı bir sadelik.

Bu modül SADECE `azizhan@azizhan.com.tr` (God Mode) hesabı için
kullanılır — normal kullanıcı girişini ETKİLEMEZ (`server.py`'nin
login'i `user.get("totp_enabled")` bayrağına göre bu kontrolü SADECE
bu bayrağı taşıyan hesaplarda devreye sokar).
"""
import base64
import hashlib
import hmac
import os
import struct
import time


def generate_secret() -> str:
    """160 bit (20 bayt) rastgele anahtar, base32 (authenticator app'lerin
    beklediği format) — `secrets`/`os.urandom` kriptografik olarak güvenli."""
    return base64.b32encode(os.urandom(20)).decode("ascii")


def _hotp(secret_bytes: bytes, counter: int, digits: int = 6) -> str:
    msg = struct.pack(">Q", counter)
    h = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code_int = (struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code_int).zfill(digits)


def _decode_secret(secret_b32: str) -> bytes:
    s = secret_b32.strip().upper().replace(" ", "")
    padding = "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s + padding)


def totp_now(secret_b32: str, step: int = 30, digits: int = 6, for_time: float = None) -> str:
    t = for_time if for_time is not None else time.time()
    counter = int(t // step)
    return _hotp(_decode_secret(secret_b32), counter, digits)


def verify_totp(secret_b32: str, code: str, window: int = 1, step: int = 30) -> bool:
    """`window=1` — saat sürüklenmesine karşı bir önceki/sonraki 30sn'lik
    adımı da kabul eder (authenticator app'lerin standart toleransı)."""
    if not secret_b32 or not code:
        return False
    code = code.strip()
    now = time.time()
    for w in range(-window, window + 1):
        expected = totp_now(secret_b32, step=step, for_time=now + w * step)
        if hmac.compare_digest(expected, code):
            return True
    return False


def provisioning_uri(secret_b32: str, account_name: str, issuer: str = "Toprax") -> str:
    """`otpauth://` URI — bazı authenticator app'leri QR yerine bu linki
    de kabul eder ("Add via URI/link" seçeneği); pratikte çoğu kullanıcı
    yine de "gizli anahtarı elle gir" akışını kullanır (bkz. secret)."""
    import urllib.parse
    label = urllib.parse.quote(f"{issuer}:{account_name}")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={urllib.parse.quote(issuer)}&digits=6&period=30"
