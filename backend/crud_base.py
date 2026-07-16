"""crud_base.py -- PR-23: Standart CRUD + Soft-Delete Sablonu (Generic Base).

docx'in Sprint 11 "Standard API" karari (Create/Update/Delete-Soft/Get/
GetById/Search/Filter/Bulk/Import/Export) burada TEK bir generic fabrika
fonksiyonu olarak kodlanir. Yeni bir modul CRUD'u elle yazmak yerine
`build_crud_router(...)` cagirip donen router'i `api_router.include_router(...)`
ile bagliyor (bkz. asagidaki ornek -- PR-23 kabul kriteri: "10 satirin
altinda ek kodla tam calisiyor").

BILINCLI SINIRLAMA: bu, VAR OLAN ~30 modulun (farmers.py, parcels.py vb.)
CRUD'unu YENIDEN YAZMAK icin degildir -- CLAUDE.md Bolum 6.1 ("mevcut
mimari korunur, gereksiz refactoring yapilmaz") geregi onlar oldugu gibi
birakildi. Bu base class SADECE BUNDAN SONRA eklenecek yeni modüller
icindir.

Baglantilar (CLAUDE.md Bolum 6.2 -- "her yeni modul RBAC/Audit/Query
Engine/Event Bus'a baglanir"):
  - RBAC: her endpoint `require_permission(f"{permission_prefix}:{action}")`
    kullanir.
  - Audit Log: create/update/soft-delete `log_audit()` cagirir.
  - Tenant izolasyonu: `db` parametresi TenantScopedDB oldugu icin otomatik.
  - Query Engine: gelismis AND/OR/operator filtreleme icin modulunuzu AYRICA
    query_engine.py MODULE_COLLECTIONS'a kaydedin -- bu base'in GET listesi
    KASITLI OLARAK basit (tek alan esitlik filtresi + serbest metin arama)
    tutuldu, cunku gelismis filtre whitelist'i merkezi bir guvenlik
    kararidir (bkz. query_engine.py basligindaki whitelist notu) ve bu
    generic fabrika o merkezi listeye kendiliginden yazamaz.
  - Event Bus: create/update/delete sonrasi olay yayinlamak isterseniz
    `on_created`/`on_updated`/`on_deleted` callback'lerini (opsiyonel,
    asagida) kullanin.

ORNEK KULLANIM (< 10 satir, PR-23 kabul kriteri):

    from crud_base import build_crud_router, CrudConfig

    router = build_crud_router(CrudConfig(
        module_name="ornek_modul",
        collection_name="ornek_modul",
        permission_prefix="ornek_modul",
        search_fields=["name"],
        filter_fields=["status"],
    ), db=db, current_user=current_user, require_permission=require_permission, log_audit=log_audit)
    api_router.include_router(router)
"""
import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

# BULGU 2 (güvenli arama regex'i) + BULGU 4 (Türkçe collation)
from search_utils import safe_regex, TR_COLLATION


@dataclass
class CrudConfig:
    module_name: str                      # URL segmenti: /{module_name}
    collection_name: str                  # Mongo koleksiyon adi (genelde ayni)
    permission_prefix: str                # "{prefix}:view" / ":create" / ":edit" / ":delete"
    search_fields: List[str] = field(default_factory=list)   # serbest metin arama alanlari
    filter_fields: List[str] = field(default_factory=list)   # ?field=value tam esitlik filtreleri
    id_field: str = "id"
    default_page_size: int = 50
    max_page_size: int = 500


def build_crud_router(
    config: CrudConfig,
    db,
    current_user: Callable,
    require_permission: Callable,
    log_audit: Callable,
    on_created: Optional[Callable] = None,
    on_updated: Optional[Callable] = None,
    on_deleted: Optional[Callable] = None,
) -> APIRouter:
    router = APIRouter()
    coll = getattr(db, config.collection_name)
    perm = config.permission_prefix

    def _now():
        return datetime.now(timezone.utc).isoformat()

    @router.post(f"/{config.module_name}")
    async def create(body: Dict[str, Any], request: Request,
                      user=Depends(require_permission(f"{perm}:create"))):
        doc = dict(body)
        doc[config.id_field] = doc.get(config.id_field) or str(uuid.uuid4())
        doc.setdefault("created_at", _now())
        doc.setdefault("is_active", True)
        await coll.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity=config.module_name,
                         entity_id=doc[config.id_field], new_value=doc, request=request)
        if on_created:
            await on_created(doc)
        return doc

    @router.post(f"/{config.module_name}/bulk")
    async def bulk_create(items: List[Dict[str, Any]], request: Request,
                            user=Depends(require_permission(f"{perm}:create"))):
        created = []
        for body in items:
            doc = dict(body)
            doc[config.id_field] = doc.get(config.id_field) or str(uuid.uuid4())
            doc.setdefault("created_at", _now())
            doc.setdefault("is_active", True)
            await coll.insert_one(doc)
            doc.pop("_id", None)
            created.append(doc)
        await log_audit(db, user, action="bulk_create", entity=config.module_name,
                         entity_id=f"{len(created)}_kayit", new_value={"count": len(created)}, request=request)
        return {"created": len(created), "items": created}

    @router.get(f"/{config.module_name}")
    async def list_items(request: Request, q: Optional[str] = None,
                           skip: int = 0, limit: int = config.default_page_size,
                           include_inactive: bool = False,
                           user=Depends(require_permission(f"{perm}:view"))):
        limit = min(limit, config.max_page_size)
        query: Dict[str, Any] = {}
        if not include_inactive:
            query["is_active"] = {"$ne": False}
        for f in config.filter_fields:
            val = request.query_params.get(f)
            if val is not None:
                query[f] = val
        if q and config.search_fields:
            # BULGU 2 düzeltmesi: girdi safe_regex ile kaçışlanır (regex
            # injection/ReDoS). Bu base tüm YENİ modülleri etkilediğinden
            # düzeltme merkezi olarak burada uygulanır.
            rq = safe_regex(q)
            query["$or"] = [{f: {"$regex": rq, "$options": "i"}} for f in config.search_fields]
        total = await coll.count_documents(query)
        # BULGU 4: Türkçe collation ile arama/sıralama. collation, cursor
        # zincirleme metodu yerine find() kwarg'ı olarak verilir (hem gerçek
        # MongoDB hem de test mock'u bu biçimi güvenle kabul eder).
        cursor = coll.find(query, {"_id": 0}, collation=TR_COLLATION).skip(skip).limit(limit)
        items = await cursor.to_list(limit)
        return {"items": items, "total": total, "skip": skip, "limit": limit}

    @router.get(f"/{config.module_name}/export")
    async def export_csv(user=Depends(require_permission(f"{perm}:view"))):
        items = await coll.find({}, {"_id": 0}).to_list(10000)
        buf = io.StringIO()
        if items:
            writer = csv.DictWriter(buf, fieldnames=sorted({k for it in items for k in it.keys()}))
            writer.writeheader()
            writer.writerows(items)
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                   headers={"Content-Disposition": f"attachment; filename={config.module_name}.csv"})

    @router.post(f"/{config.module_name}/import")
    async def import_csv(rows: List[Dict[str, Any]], request: Request,
                           user=Depends(require_permission(f"{perm}:create"))):
        return await bulk_create(rows, request, user)

    @router.get(f"/{config.module_name}/{{item_id}}")
    async def get_by_id(item_id: str, user=Depends(require_permission(f"{perm}:view"))):
        doc = await coll.find_one({config.id_field: item_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, f"{config.module_name} bulunamadı")
        return doc

    @router.put(f"/{config.module_name}/{{item_id}}")
    async def update(item_id: str, body: Dict[str, Any], request: Request,
                       user=Depends(require_permission(f"{perm}:edit"))):
        old = await coll.find_one({config.id_field: item_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, f"{config.module_name} bulunamadı")
        updates = {k: v for k, v in body.items() if k != config.id_field}
        updates["updated_at"] = _now()
        await coll.update_one({config.id_field: item_id}, {"$set": updates})
        new = await coll.find_one({config.id_field: item_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity=config.module_name,
                         entity_id=item_id, old_value=old, new_value=new, request=request)
        if on_updated:
            await on_updated(new)
        return new

    @router.delete(f"/{config.module_name}/{{item_id}}")
    async def soft_delete(item_id: str, request: Request,
                            user=Depends(require_permission(f"{perm}:delete"))):
        """Fiziksel silme YAPILMAZ -- is_active=False + deleted_at (CLAUDE.md
        Bolum 3.9 'migration'lar geriye uyumlu' ruhuyla ayni: veri gecmisi
        korunur, sadece erisim/gorunurluk kapanir)."""
        old = await coll.find_one({config.id_field: item_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, f"{config.module_name} bulunamadı")
        await coll.update_one({config.id_field: item_id},
                                {"$set": {"is_active": False, "deleted_at": _now()}})
        await log_audit(db, user, action="soft_delete", entity=config.module_name,
                         entity_id=item_id, old_value=old, request=request)
        if on_deleted:
            await on_deleted(old)
        return {"status": "deactivated"}

    return router
