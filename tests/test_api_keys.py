"""
PR-24 — API Key mekanizması testleri. Kabul kriteri (ROADMAP-URUNLESTIRME.md):
"Scope'u sadece Farmer.Read olan bir key ile Parcel.Write denemesi 403
dönüyor; süresi dolmuş key otomatik reddediliyor; rate limit aşıldığında
429 dönüyor." Bu dosya üçünü de gerçek (mongomock) bir DB'ye karşı çalıştırıp
doğrular.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from api_keys import ApiKeyCreate, resolve_api_key_user, register_api_key_routes, _generate_key, _hash_key
from permissions import get_effective_permissions


async def _log_audit(db, user, **kwargs):
    pass


def _require_permission(perm):
    async def _dep(user):
        return user
    return _dep


async def _make_key(raw_db, scopes, expires_at=None, rate_limit_per_minute=60):
    import uuid
    plaintext = _generate_key()
    doc = {
        "id": str(uuid.uuid4()), "tenant_id": "t1", "name": "test-key",
        "key_hash": _hash_key(plaintext), "key_prefix": "toprax_key_xxxxxx…",
        "scopes": scopes, "rate_limit_per_minute": rate_limit_per_minute,
        "expires_at": expires_at, "revoked": False,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "test",
        "last_used_at": None,
    }
    await raw_db.api_keys.insert_one(doc)
    return plaintext


@pytest.mark.asyncio
async def test_scope_limited_key_rejected_for_out_of_scope_permission():
    raw_db = AsyncMongoMockClient()["t"]
    plaintext = await _make_key(raw_db, scopes=["farmers:view"])

    user = await resolve_api_key_user(raw_db, plaintext)
    assert user is not None

    perms = await get_effective_permissions(user, raw_db)
    assert "farmers:view" in perms
    assert "parcels:edit" not in perms  # Farmer.Read scope'u Parcel.Write'a izin vermez


@pytest.mark.asyncio
async def test_expired_key_rejected():
    raw_db = AsyncMongoMockClient()["t"]
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    plaintext = await _make_key(raw_db, scopes=["farmers:view"], expires_at=past)

    user = await resolve_api_key_user(raw_db, plaintext)
    assert user is None  # süresi dolmuş -- reddedildi


@pytest.mark.asyncio
async def test_revoked_key_rejected():
    raw_db = AsyncMongoMockClient()["t"]
    plaintext = await _make_key(raw_db, scopes=["farmers:view"])
    await raw_db.api_keys.update_one({"key_hash": _hash_key(plaintext)}, {"$set": {"revoked": True}})

    user = await resolve_api_key_user(raw_db, plaintext)
    assert user is None


@pytest.mark.asyncio
async def test_rate_limit_exceeded_returns_429():
    raw_db = AsyncMongoMockClient()["t"]
    plaintext = await _make_key(raw_db, scopes=["farmers:view"], rate_limit_per_minute=3)

    # ilk 3 istek serbest
    for _ in range(3):
        user = await resolve_api_key_user(raw_db, plaintext)
        assert user is not None

    # 4. istek rate limit'e takılmalı
    with pytest.raises(HTTPException) as excinfo:
        await resolve_api_key_user(raw_db, plaintext)
    assert excinfo.value.status_code == 429


@pytest.mark.asyncio
async def test_invalid_key_returns_none():
    raw_db = AsyncMongoMockClient()["t"]
    user = await resolve_api_key_user(raw_db, "toprax_key_bu-hic-var-olmayan-bir-anahtar")
    assert user is None
