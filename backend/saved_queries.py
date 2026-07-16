"""
=====================================================================
Toprax — Saved Queries / Portföy (Favorilerim) (IT-09)
=====================================================================
query_engine.py'nin (IT-08) filter DSL'ini (filters/logic/sort/fields)
adlandırılmış kayıtlar olarak saklar. Üç kullanım:
  - Özel (private): sadece oluşturan görür/kullanır.
  - Paylaşılan (is_shared=True): modülü görüntüleme yetkisi olan HERKES
    tenant içinde görür/kullanır — ama sadece SAHİBİ düzenler/siler
    (admin+ sistem katmanı moderasyon amacıyla silebilir, bkz. IT-07
    get_system_tier).
  - Favoriler (Portföy): kullanıcı kendi favorited_by listesine
    eklenmiş sorguları "Favorilerim" görünümünde görür (kendi
    özel sorguları + başkasının paylaştığı sorgular dahil olabilir).

Bu modül SORGUYU ÇALIŞTIRMAZ — çalıştırma query_engine.py'nin işi
(POST /query/{module}). Burada sadece DSL'i saklamak/listelemek/
favorilemek var; frontend kayıtlı bir sorguyu seçtiğinde onun
filters/logic/sort/fields alanlarını okuyup query_engine'e kendisi
gönderir.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Any, List, Optional

from query_engine import MODULE_COLLECTIONS, MODULE_PERMISSIONS, FilterCondition


class SavedQueryCreate(BaseModel):
    module: str
    name: str
    filters: List[FilterCondition] = []
    logic: str = "AND"
    sort_by: Optional[str] = None
    sort_dir: str = "asc"
    fields: Optional[List[str]] = None
    is_shared: bool = False


class SavedQueryUpdate(BaseModel):
    name: Optional[str] = None
    filters: Optional[List[FilterCondition]] = None
    logic: Optional[str] = None
    sort_by: Optional[str] = None
    sort_dir: Optional[str] = None
    fields: Optional[List[str]] = None
    is_shared: Optional[bool] = None


def register_saved_query_routes(api_router, db, current_user, require_permission, log_audit):

    async def _check_module_permission(module: str, user: dict):
        if module not in MODULE_COLLECTIONS:
            raise HTTPException(404, f"Bilinmeyen modül: {module}")
        from permissions import get_effective_permissions
        perms = await get_effective_permissions(user, db)
        if MODULE_PERMISSIONS[module] not in perms:
            raise HTTPException(403, f"'{MODULE_PERMISSIONS[module]}' yetkiniz yok")

    @api_router.get("/saved-queries")
    async def list_saved_queries(
        module: Optional[str] = None,
        favorites_only: bool = False,
        user=Depends(current_user),
    ):
        """
        Kendi sorgularım + (aynı modülde görüntüleme yetkim varsa)
        başkalarının PAYLAŞTIĞI sorgular. favorites_only=True verilirse
        sadece favorited_by listemde olanlar (Portföy).
        """
        query: dict = {}
        if module:
            query["module"] = module
        if favorites_only:
            query["favorited_by"] = user["id"]
        else:
            query["$or"] = [{"created_by_id": user["id"]}, {"is_shared": True}]

        docs = await db.saved_queries.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)

        # Paylaşılan ama görüntüleme yetkim olmayan bir modülün sorgusu sızmasın
        # (ör. rolüm sonradan daraltılmış olabilir) — ikinci bir süzgeç.
        from permissions import get_effective_permissions
        perms = await get_effective_permissions(user, db)
        docs = [d for d in docs if MODULE_PERMISSIONS.get(d["module"]) in perms]
        for d in docs:
            d["is_favorite"] = user["id"] in (d.get("favorited_by") or [])
            d["is_owner"] = d.get("created_by_id") == user["id"]
        return docs

    @api_router.post("/saved-queries")
    async def create_saved_query(body: SavedQueryCreate, request: Request, user=Depends(current_user)):
        await _check_module_permission(body.module, user)
        doc = body.model_dump()
        doc["filters"] = [f if isinstance(f, dict) else f.model_dump() for f in doc["filters"]]
        doc["id"] = str(uuid.uuid4())
        doc["created_by_id"] = user["id"]
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["favorited_by"] = []
        await db.saved_queries.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="saved_query", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/saved-queries/{query_id}")
    async def update_saved_query(query_id: str, body: SavedQueryUpdate, request: Request, user=Depends(current_user)):
        old = await db.saved_queries.find_one({"id": query_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kayıtlı sorgu bulunamadı")
        if old.get("created_by_id") != user["id"]:
            raise HTTPException(403, "Sadece sorgunun sahibi düzenleyebilir")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "filters" in updates:
            updates["filters"] = [f if isinstance(f, dict) else f for f in updates["filters"]]
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.saved_queries.update_one({"id": query_id}, {"$set": updates})
        new = await db.saved_queries.find_one({"id": query_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="saved_query", entity_id=query_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/saved-queries/{query_id}")
    async def delete_saved_query(query_id: str, request: Request, user=Depends(current_user)):
        """Gerçek silme (soft-delete DEĞİL) — kayıtlı sorgu bir görünüm
        tercihidir, finansal/tarihsel veri değildir (convention #3 kapsamı
        dışında, bkz. field_definitions'ın kendi delete'i de aynı ayrımı
        yapmıyor ama burada geçmiş kayıt bütünlüğü riski yok)."""
        from config_service import get_system_tier
        old = await db.saved_queries.find_one({"id": query_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kayıtlı sorgu bulunamadı")
        is_owner = old.get("created_by_id") == user["id"]
        is_moderator = get_system_tier(user.get("role")) in ("god_mode", "super_admin", "admin")
        if not (is_owner or is_moderator):
            raise HTTPException(403, "Sadece sorgunun sahibi veya admin silebilir")
        await db.saved_queries.delete_one({"id": query_id})
        await log_audit(db, user, action="delete", entity="saved_query", entity_id=query_id, old_value=old, request=request)
        return {"status": "deleted"}

    @api_router.post("/saved-queries/{query_id}/favorite")
    async def toggle_favorite(query_id: str, user=Depends(current_user)):
        """Favorilerime ekle/çıkar (Portföy) — sorgunun kendisini değiştirmez,
        sadece favorited_by listesindeki üyeliğimi değiştirir."""
        doc = await db.saved_queries.find_one({"id": query_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Kayıtlı sorgu bulunamadı")
        await _check_module_permission(doc["module"], user)
        favorited_by = set(doc.get("favorited_by") or [])
        if user["id"] in favorited_by:
            favorited_by.discard(user["id"])
            is_favorite = False
        else:
            favorited_by.add(user["id"])
            is_favorite = True
        await db.saved_queries.update_one({"id": query_id}, {"$set": {"favorited_by": list(favorited_by)}})
        return {"status": "ok", "is_favorite": is_favorite}
