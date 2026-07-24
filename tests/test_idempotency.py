"""
2026-07-24 -- Denetim raporu #2 / Faz 8 (Rol Bazlı Offline) testleri.

`lib/offlineQueue.js`'in aynı isteği (X-Idempotency-Key ile) TEKRAR
göndermesi durumunda `backend/idempotency.py`'nin ikinci denemede
kaydedilmiş yanıtı AYNEN dönüp yeni bir yazma YAPMADIĞINI doğrular.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from mongomock_motor import AsyncMongoMockClient

from tenant_context import TenantScopedDB, current_tenant_id
from idempotency import get_cached_response, save_response


class _FakeRequest:
    """FastAPI'nin Request.headers'ının (case-insensitive dict benzeri)
    testte ihtiyaç duyulan minimal karşılığı."""
    def __init__(self, headers: dict):
        self._headers = {k.lower(): v for k, v in headers.items()}

    class _Headers:
        def __init__(self, d):
            self._d = d

        def get(self, key):
            return self._d.get(key.lower())

    @property
    def headers(self):
        return self._Headers(self._headers)


def _fresh_db():
    raw = AsyncMongoMockClient()["test_db"]
    return TenantScopedDB(raw)


@pytest.mark.asyncio
async def test_replay_returns_cached_response_without_duplicate():
    db = _fresh_db()
    current_tenant_id.set("tenant-a")
    req = _FakeRequest({"X-Idempotency-Key": "test-key-1"})

    # İLK deneme — henüz kayıt yok.
    key, cached = await get_cached_response(db, req, "visits:create")
    assert key == "test-key-1"
    assert cached is None

    # Çağıran normal işini yapar (bir ziyaret "yazar") ve yanıtı saklar.
    fake_response = {"id": "visit-1", "notes": "ilk yazım"}
    await save_response(db, key, "visits:create", fake_response)

    # İKİNCİ deneme (offlineQueue.js'in replay'i) — AYNI anahtar.
    key2, cached2 = await get_cached_response(db, req, "visits:create")
    assert key2 == "test-key-1"
    assert cached2 == fake_response

    # idempotency_keys koleksiyonunda TEK bir kayıt olmalı (tekrar save_response
    # çağrılsa bile ikinci kez YAZILMAZ -- $setOnInsert).
    await save_response(db, key2, "visits:create", {"id": "should-not-overwrite"})
    count = await db.idempotency_keys.count_documents({"key": "test-key-1"})
    assert count == 1
    doc = await db.idempotency_keys.find_one({"key": "test-key-1"})
    assert doc["response"] == fake_response  # ilk yanıt korunmuş, ezilmemiş


@pytest.mark.asyncio
async def test_no_header_means_no_caching():
    """Header hiç gönderilmemişse (eski istemci) mekanizma devre dışı kalır —
    her istek normal şekilde işlenir, hiçbir şey saklanmaz."""
    db = _fresh_db()
    current_tenant_id.set("tenant-a")
    req = _FakeRequest({})

    key, cached = await get_cached_response(db, req, "visits:create")
    assert key is None
    assert cached is None

    await save_response(db, key, "visits:create", {"id": "irrelevant"})
    count = await db.idempotency_keys.count_documents({})
    assert count == 0


@pytest.mark.asyncio
async def test_different_endpoints_do_not_collide():
    """Aynı anahtar farklı bir uca (endpoint) gönderilirse ÇAPRAZ cevap
    dönmemeli -- (key, endpoint) çifti birlikte anahtar."""
    db = _fresh_db()
    current_tenant_id.set("tenant-a")
    req = _FakeRequest({"X-Idempotency-Key": "shared-key"})

    await save_response(db, "shared-key", "visits:create", {"id": "visit-x"})
    key, cached = await get_cached_response(db, req, "kantar:create")
    assert cached is None  # farklı endpoint -- kendi kaydı yok
