"""
2026-07-24 -- Denetim düzeltmesi A3 (tenant izolasyonu fail-closed) testleri.

Eski davranış: `current_tenant_id` None iken TenantScopedCollection filtre
EKLEMİYORDU -- auth kontrolü unutulmuş bir endpoint TÜM tenant'ların verisini
sızdırabiliyordu. Yeni davranış: bağlamsız sorguya `__UNAUTHORIZED__`
sentinel'i enjekte edilir, sonuç HER ZAMAN boştur. Meşru bağlamsız yollar
(login/refresh/platform admin) raw_db kullanır.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from mongomock_motor import AsyncMongoMockClient

from tenant_context import TenantScopedDB, current_tenant_id, UNAUTHORIZED_TENANT_SENTINEL


def _fresh_db():
    raw = AsyncMongoMockClient()["test_db"]
    return raw, TenantScopedDB(raw)


async def _seed_two_tenants(raw):
    await raw.farmers.insert_many([
        {"id": str(uuid.uuid4()), "full_name": "Tenant A Çiftçisi", "tenant_id": "tenant-a"},
        {"id": str(uuid.uuid4()), "full_name": "Tenant B Çiftçisi", "tenant_id": "tenant-b"},
    ])


@pytest.mark.asyncio
async def test_no_context_read_returns_empty():
    """Bağlamsız find/find_one/count HİÇBİR tenant'ın verisini dönmemeli."""
    raw, db = _fresh_db()
    await _seed_two_tenants(raw)
    assert current_tenant_id.get() is None

    docs = await db.farmers.find({}).to_list(100)
    assert docs == []
    assert await db.farmers.find_one({}) is None
    assert await db.farmers.count_documents({}) == 0


@pytest.mark.asyncio
async def test_no_context_aggregate_returns_empty():
    raw, db = _fresh_db()
    await _seed_two_tenants(raw)
    out = await db.farmers.aggregate([{"$group": {"_id": None, "n": {"$sum": 1}}}]).to_list(10)
    # Gerçek MongoDB boş girdide [] döner; mongomock {_id:None, n:0} dönebilir.
    # Her iki durumda da kritik olan: HİÇBİR tenant verisi sayılmamış olmalı.
    total = sum(d.get("n", 0) for d in out)
    assert total == 0


@pytest.mark.asyncio
async def test_no_context_update_delete_match_nothing():
    """Bağlamsız update/delete başka tenant'ın kaydına dokunamamalı."""
    raw, db = _fresh_db()
    await _seed_two_tenants(raw)
    res = await db.farmers.update_many({}, {"$set": {"hacked": True}})
    assert res.modified_count == 0
    res = await db.farmers.delete_many({})
    assert res.deleted_count == 0
    assert await raw.farmers.count_documents({}) == 2


@pytest.mark.asyncio
async def test_with_context_only_own_tenant_visible():
    """Bağlam kuruluyken izolasyon eskisi gibi çalışmalı (regresyon yok)."""
    raw, db = _fresh_db()
    await _seed_two_tenants(raw)
    reset = current_tenant_id.set("tenant-a")
    try:
        docs = await db.farmers.find({}).to_list(100)
        assert len(docs) == 1
        assert docs[0]["tenant_id"] == "tenant-a"
    finally:
        current_tenant_id.reset(reset)


@pytest.mark.asyncio
async def test_global_collection_exempt():
    """`tenants` koleksiyonu (GLOBAL_COLLECTIONS) bağlamsız da okunabilmeli
    -- login öncesi bootstrap bu koleksiyona muhtaç."""
    raw, db = _fresh_db()
    await raw.tenants.insert_one({"id": "t1", "slug": "default"})
    assert await db.tenants.find_one({"slug": "default"}) is not None


@pytest.mark.asyncio
async def test_sentinel_never_matches_real_data():
    """Sentinel değeriyle gerçek bir tenant_id çakışmamalı."""
    raw, db = _fresh_db()
    await raw.farmers.insert_one({"id": "x", "tenant_id": UNAUTHORIZED_TENANT_SENTINEL})
    # Böyle bir kayıt olsa bile bu bir veri hatasıdır; bağlamsız erişimin
    # gerçek tenant verisi dönmediği yukarıdaki testlerle garanti edilir.
    reset = current_tenant_id.set("tenant-a")
    try:
        assert await db.farmers.find_one({}) is None
    finally:
        current_tenant_id.reset(reset)
