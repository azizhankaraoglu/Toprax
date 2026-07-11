"""
PR-23 — Generic CRUD/Soft-Delete Base Class testi. Kabul kriteri:
"Yeni bir modül eklerken CRUD endpoint'leri elle yazılmadan base class'tan
miras alınarak 10 satırın altında ek kodla tam çalışıyor." Bu dosya hem o
iddiayı fiilen çalıştırıp doğrular, hem de mongomock_motor ile gerçek bir
Mongo'ya ihtiyaç duymadan (CI'da da çalışabilir) yapar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from mongomock_motor import AsyncMongoMockClient

from crud_base import build_crud_router, CrudConfig


class _FakeUser(dict):
    pass


def _require_permission(_perm):
    async def _dep():
        return _FakeUser(email="test@test.local", role="super_admin", tenant_id="t1")
    return _dep


async def _current_user():
    return _FakeUser(email="test@test.local", role="super_admin", tenant_id="t1")


_audit_calls = []


async def _log_audit(db, user, **kwargs):
    _audit_calls.append(kwargs)


# ---- PR-23 kabul kriteri: <10 satırlık yeni modül tanımı ----
db = AsyncMongoMockClient()["test_db"]
router = build_crud_router(CrudConfig(
    module_name="ornek_modul",
    collection_name="ornek_modul",
    permission_prefix="ornek_modul",
    search_fields=["name"],
    filter_fields=["status"],
), db=db, current_user=_current_user, require_permission=_require_permission, log_audit=_log_audit)
# ---- (9 satır) ----


def _find_route(path_suffix, method):
    for r in router.routes:
        if r.path.endswith(path_suffix) and method in r.methods:
            return r
    raise AssertionError(f"route bulunamadı: {method} *{path_suffix}")


@pytest.mark.asyncio
async def test_create_list_get_update_soft_delete():
    from starlette.requests import Request as StarletteRequest

    fake_request = StarletteRequest(scope={"type": "http", "method": "POST", "headers": [], "query_string": b""})

    create_route = _find_route("/ornek_modul", "POST")
    created = await create_route.endpoint({"name": "Test Kayıt", "status": "aktif"}, fake_request,
                                            user=await _current_user())
    assert created["name"] == "Test Kayıt"
    assert created["is_active"] is True
    item_id = created["id"]

    list_route = _find_route("/ornek_modul", "GET")
    listing = await list_route.endpoint(fake_request, q=None, skip=0, limit=50, include_inactive=False,
                                          user=await _current_user())
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == item_id

    get_route = _find_route("/ornek_modul/{item_id}", "GET")
    fetched = await get_route.endpoint(item_id, user=await _current_user())
    assert fetched["id"] == item_id

    update_route = _find_route("/ornek_modul/{item_id}", "PUT")
    updated = await update_route.endpoint(item_id, {"status": "pasif"}, fake_request, user=await _current_user())
    assert updated["status"] == "pasif"

    delete_route = _find_route("/ornek_modul/{item_id}", "DELETE")
    result = await delete_route.endpoint(item_id, fake_request, user=await _current_user())
    assert result["status"] == "deactivated"

    listing_after = await list_route.endpoint(fake_request, q=None, skip=0, limit=50, include_inactive=False,
                                                 user=await _current_user())
    assert listing_after["total"] == 0  # soft-delete edilen kayıt varsayılan listede görünmez

    listing_incl = await list_route.endpoint(fake_request, q=None, skip=0, limit=50, include_inactive=True,
                                                user=await _current_user())
    assert listing_incl["total"] == 1  # include_inactive=True ile hâlâ erişilebilir (veri kaybı yok)

    assert len(_audit_calls) == 3  # create, update, soft_delete
