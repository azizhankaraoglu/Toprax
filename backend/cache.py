"""
=====================================================================
TabSIS — Cache Soyutlaması (IT-33 / FAZ 11 — Platform Core)
=====================================================================
Redis KURULU DEĞİL (bkz. CLAUDE.md "Uyarlama Kararları") — bilinçli
olarak basit, tek-process, in-process bir TTL cache. Arayüz (`cache_get_
or_set`/`cache_invalidate*`) KORUNUR; ileride gerçek Redis'e geçilirse
SADECE bu dosyanın içi değişir, çağıran kod (permissions.py, server.py'nin
/regions ucu vb.) DEĞİŞMEZ — `satellite_provider.py`/`channel_providers.py`
ile AYNI "arayüz sabit, arkası değişebilir" felsefesi.

Çoklu worker/yatay ölçekleme senaryosu BİLİNÇLİ OLARAK kapsam dışı
(event_bus.py'nin aynı gerekçesiyle AYNI — tek process/tek worker'lı
Windows dev ortamı için yeterli).
"""
import time
from typing import Any, Awaitable, Callable, Dict, Tuple

_store: Dict[str, Tuple[float, Any]] = {}


async def cache_get_or_set(key: str, ttl_seconds: int, factory: Callable[[], Awaitable[Any]]) -> Any:
    """`key` cache'te ve süresi geçmemişse onu döner; aksi halde `factory()`'yi
    (async) çağırıp sonucu `ttl_seconds` süreyle saklar."""
    now = time.monotonic()
    cached = _store.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    value = await factory()
    _store[key] = (now + ttl_seconds, value)
    return value


def cache_invalidate(key: str) -> None:
    _store.pop(key, None)


def cache_invalidate_prefix(prefix: str) -> None:
    """Bir kullanıcının/rolün izinleri değiştiğinde (users.py `update_user_role`)
    ilgili anahtarları temizlemek için — TTL'nin kendiliğinden dolmasını
    beklemeden ANINDA tutarlılık gerektiren tek nokta."""
    for k in [k for k in _store if k.startswith(prefix)]:
        _store.pop(k, None)
