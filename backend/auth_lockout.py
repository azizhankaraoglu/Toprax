"""auth_lockout.py -- PR-13 (kismi): Login brute-force koruma.

ROADMAP-URUNLESTIRME.md PR-13, "GodMode auth'a rate-limiting/brute-force
korumasi eklenir" diyor -- ancak bu kod tabaninda GodMode (IT-36) HENUZ
YAZILMAMIS (ayri, kapsamli bir ozellik, bu PR'in konusu degil). Bunun
yerine ayni gerekce GERCEKTEN VAR OLAN /api/auth/login ucuna uygulanir --
kurumsal bir on-premise urunde en az GodMode kadar kritik bir saldiri
yuzeyi budur.

In-process sayac (api_keys.py'deki rate limit ile ayni tasarim tercihi --
Redis yok, tek-instance varsayimi; coklu replika/HA kurulumunda paylasimli
bir store'a tasinmasi gerekir, bilinen sinir).
"""
import time
from collections import defaultdict, deque
from typing import Dict

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60          # 15 dakika
LOCKOUT_SECONDS = 15 * 60         # kilitlendiğinde 15 dakika bekleme

_failed_attempts: Dict[str, deque] = defaultdict(deque)
_locked_until: Dict[str, float] = {}


def _key(email: str, ip: str) -> str:
    return f"{email.lower()}:{ip}"


def is_locked(email: str, ip: str) -> float:
    """Kilitliyse kalan saniyeyi döner, degilse 0."""
    k = _key(email, ip)
    until = _locked_until.get(k)
    if not until:
        return 0
    remaining = until - time.monotonic()
    if remaining <= 0:
        _locked_until.pop(k, None)
        _failed_attempts.pop(k, None)
        return 0
    return remaining


def record_failed_attempt(email: str, ip: str) -> None:
    k = _key(email, ip)
    now = time.monotonic()
    window = _failed_attempts[k]
    window.append(now)
    while window and now - window[0] > WINDOW_SECONDS:
        window.popleft()
    if len(window) >= MAX_ATTEMPTS:
        _locked_until[k] = now + LOCKOUT_SECONDS


def record_successful_login(email: str, ip: str) -> None:
    k = _key(email, ip)
    _failed_attempts.pop(k, None)
    _locked_until.pop(k, None)
