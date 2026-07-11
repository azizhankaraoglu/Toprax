"""
PR-09 — Financial Ledger'ın silinmezlik kuralı testi. Kabul kriteri
(ROADMAP-URUNLESTIRME.md PR-09): "Auth/RBAC, Financial Ledger'ın
silinmezlik kuralı, ... için unit + entegrasyon testleri." Bu dosya
ledger.py'nin İKİ garantisini doğrular:
  1) Router'da HİÇBİR update/delete endpoint'i YOK (yapısal olarak
     silinmez/değiştirilemez -- CLAUDE.md #3.9 ruhuyla aynı).
  2) reverse() orijinal kaydı DEĞİŞTİRMEZ, ters işaretli YENİ bir kayıt
     ekler; aynı kayıt iki kez ters kayıtla düzeltilemez (409).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from ledger import register_ledger_routes, create_ledger_entry


class _FakeUser(dict):
    pass


def _require_permission(_perm):
    async def _dep():
        return _FakeUser(email="test@test.local", role="super_admin", tenant_id="t1", full_name="Test Kullanıcı")
    return _dep


async def _current_user():
    return _FakeUser(email="test@test.local")


async def _log_audit(db, user, **kwargs):
    pass


class _FakeRouter:
    """FastAPI APIRouter'ın gerçeğini kurmadan sadece hangi path+method
    kombinasyonlarının kaydedildiğini toplayan minimal sahte -- yapısal
    'silme ucu yok' iddiasını gerçek router nesnesi kurmadan test eder."""
    def __init__(self):
        self.registered = []  # (method, path, func)

    def _capture(self, method):
        def decorator(path):
            def wrapper(func):
                self.registered.append((method, path, func))
                return func
            return wrapper
        return decorator

    def get(self, path, **kw):
        return self._capture("GET")(path)

    def post(self, path, **kw):
        return self._capture("POST")(path)

    def put(self, path, **kw):
        return self._capture("PUT")(path)

    def delete(self, path, **kw):
        return self._capture("DELETE")(path)


def test_no_update_or_delete_endpoint_exists():
    router = _FakeRouter()
    db = AsyncMongoMockClient()["t"]
    register_ledger_routes(router, db, _current_user, _require_permission, _log_audit)

    methods_registered = {method for method, _, _ in router.registered}
    assert "DELETE" not in methods_registered, "Ledger'da DELETE ucu OLMAMALI (silinmezlik kuralı)"
    assert "PUT" not in methods_registered, "Ledger'da PUT/update ucu OLMAMALI (silinmezlik kuralı)"
    assert "POST" in methods_registered  # create + reverse (ikisi de yeni kayıt ekler)


@pytest.mark.asyncio
async def test_reverse_creates_new_entry_without_touching_original():
    db = AsyncMongoMockClient()["t"]
    original = await create_ledger_entry(
        db, production_cycle_id="pc1", farmer_id="f1", entry_type="hakedis", amount=1000.0,
    )

    router = _FakeRouter()
    register_ledger_routes(router, db, _current_user, _require_permission, _log_audit)
    reverse_fn = next(f for m, p, f in router.registered if m == "POST" and "reverse" in p)

    from ledger import LedgerReverseRequest
    from starlette.requests import Request as StarletteRequest
    fake_request = StarletteRequest(scope={"type": "http", "method": "POST", "headers": [], "query_string": b""})

    reversal = await reverse_fn(original["id"], LedgerReverseRequest(reason="test düzeltme"),
                                  fake_request, user=await _current_user())

    # Orijinal kayıt HİÇ değişmedi
    still_original = await db.ledger_entries.find_one({"id": original["id"]}, {"_id": 0})
    assert still_original["amount"] == 1000.0
    assert still_original["is_reversal"] is False

    # Ters kayıt YENİ ve ters işaretli
    assert reversal["id"] != original["id"]
    assert reversal["amount"] == -1000.0
    assert reversal["is_reversal"] is True
    assert reversal["reversed_entry_id"] == original["id"]

    total_entries = await db.ledger_entries.count_documents({})
    assert total_entries == 2  # silme YOK, sadece ekleme

    # Aynı kaydı ikinci kez ters kayıtla düzeltmek 409 vermeli
    with pytest.raises(HTTPException) as excinfo:
        await reverse_fn(original["id"], LedgerReverseRequest(), fake_request, user=await _current_user())
    assert excinfo.value.status_code == 409
