"""
2026-07-11 -- Giris sayfasindaki (Login.jsx) 'Hesabiniz yok mu? Talep
olusturun' formu testleri (public_contact.py). Kabul kriteri: kimlik
dogrulama gerektirmeyen bu uc (a) case'i DOGRU tenant'a yazmali (b)
diger tenant'lardan IZOLE olmali (c) kategoriyi SADECE BIR KEZ olusturmali.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from tenant_context import TenantScopedDB, current_tenant_id
from public_contact import (
    PUBLIC_CONTACT_CATEGORY_NAME,
    resolve_bootstrap_tenant,
    create_public_contact_case,
)


def _fresh_db():
    raw = AsyncMongoMockClient()["test_db"]
    return raw, TenantScopedDB(raw)


@pytest.mark.asyncio
async def test_resolve_bootstrap_tenant_503_when_no_tenant_exists():
    raw, _db = _fresh_db()
    with pytest.raises(HTTPException) as exc_info:
        await resolve_bootstrap_tenant(raw)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_resolve_bootstrap_tenant_prefers_default_slug():
    raw, _db = _fresh_db()
    await raw.tenants.insert_one({"id": "t-other", "slug": "baska-kurum"})
    await raw.tenants.insert_one({"id": "t-default", "slug": "default"})
    tenant = await resolve_bootstrap_tenant(raw)
    assert tenant["id"] == "t-default"


@pytest.mark.asyncio
async def test_create_public_contact_case_stamps_correct_tenant_and_fields():
    raw, db = _fresh_db()
    tenant_id = str(uuid.uuid4())
    reset_token = current_tenant_id.set(tenant_id)
    try:
        case_doc = await create_public_contact_case(
            db, full_name="Ayşe Yılmaz", phone="0555 000 00 00", email=None,
            message="Hesabım yok, giriş yapamıyorum.",
        )
    finally:
        current_tenant_id.reset(reset_token)

    assert case_doc["status"] == "yeni"
    assert case_doc["assigned_to"] is None
    assert case_doc["created_by_user_id"] is None
    assert case_doc["source_channel"] == "giris_sayfasi_web_formu"
    assert "Ayşe Yılmaz" in case_doc["subject"]
    assert "0555 000 00 00" in case_doc["description"]

    # Ham DB'de dogru tenant_id ile damgalanmis mi
    raw_case = await raw.cases.find_one({"id": case_doc["id"]}, {"_id": 0})
    assert raw_case["tenant_id"] == tenant_id


@pytest.mark.asyncio
async def test_create_public_contact_case_creates_category_only_once():
    raw, db = _fresh_db()
    tenant_id = str(uuid.uuid4())
    reset_token = current_tenant_id.set(tenant_id)
    try:
        await create_public_contact_case(db, "Kişi Bir", "111", None, "mesaj 1")
        await create_public_contact_case(db, "Kişi İki", "222", None, "mesaj 2")
    finally:
        current_tenant_id.reset(reset_token)

    count = await raw.case_categories.count_documents({"name": PUBLIC_CONTACT_CATEGORY_NAME, "tenant_id": tenant_id})
    assert count == 1
    cases_count = await raw.cases.count_documents({"tenant_id": tenant_id})
    assert cases_count == 2


@pytest.mark.asyncio
async def test_case_isolated_from_other_tenants():
    raw, db = _fresh_db()
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())

    reset_token = current_tenant_id.set(tenant_a)
    try:
        case_doc = await create_public_contact_case(db, "Tenant A Kişisi", "111", None, "A tenantından mesaj")
    finally:
        current_tenant_id.reset(reset_token)

    reset_token = current_tenant_id.set(tenant_b)
    try:
        visible_to_b = await db.cases.find_one({"id": case_doc["id"]}, {"_id": 0})
    finally:
        current_tenant_id.reset(reset_token)

    assert visible_to_b is None, "Izolasyon ihlali: baska tenant'in case'i gorunuyor"
