"""
=====================================================================
TabSIS — Favoriler (IT-12)
=====================================================================
Herhangi bir modüldeki (farmers/parcels/contracts/plantings/soil/
production_cycles) tek bir KAYDI favorileme. Saved Queries'in (IT-09)
favorileriyle KARIŞTIRILMAMALI — o SORGU favoriler, bu ENTITY (çiftçi/
parsel/...) favoriler. İkisi de "Portföy" fikrini paylaşır ama farklı
şeyleri favoriler.

`label` istemci tarafından gönderilir ve DENORMALİZE saklanır (ör.
çiftçi adı) — Favoriler panelini (IT-12 Workspace Drawer) her satır
için ayrı bir GET isteği yapmadan render edebilmek için. Kayıt daha
sonra değişirse (ör. çiftçi adı güncellenirse) burada eskisi kalır —
bilinçli, "favorilendiği andaki" bir anlık görüntü niyetinde değil,
sadece performans amaçlı; kritik değilse asıl veri detay sayfasına
gidince zaten güncel görülür.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from query_engine import MODULE_COLLECTIONS, MODULE_PERMISSIONS


class FavoriteCreate(BaseModel):
    module: str
    entity_id: str
    label: str


def register_favorite_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/favorites")
    async def list_favorites(module: Optional[str] = None, user=Depends(current_user)):
        query = {"user_id": user["id"]}
        if module:
            query["module"] = module
        return await db.favorites.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/favorites")
    async def add_favorite(body: FavoriteCreate, request: Request, user=Depends(current_user)):
        if body.module not in MODULE_COLLECTIONS:
            raise HTTPException(404, f"Bilinmeyen modül: {body.module}")
        from permissions import get_effective_permissions
        perms = await get_effective_permissions(user, db)
        if MODULE_PERMISSIONS[body.module] not in perms:
            raise HTTPException(403, f"'{MODULE_PERMISSIONS[body.module]}' yetkiniz yok")

        existing = await db.favorites.find_one(
            {"user_id": user["id"], "module": body.module, "entity_id": body.entity_id}, {"_id": 0}
        )
        if existing:
            return existing  # idempotent — zaten favoriyse tekrar oluşturmaz

        doc = {
            "id": str(uuid.uuid4()), "user_id": user["id"], "module": body.module,
            "entity_id": body.entity_id, "label": body.label,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.favorites.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @api_router.delete("/favorites/{favorite_id}")
    async def remove_favorite(favorite_id: str, user=Depends(current_user)):
        old = await db.favorites.find_one({"id": favorite_id}, {"_id": 0})
        if not old or old.get("user_id") != user["id"]:
            raise HTTPException(404, "Favori bulunamadı")
        await db.favorites.delete_one({"id": favorite_id})
        return {"status": "deleted"}

    @api_router.delete("/favorites/by-entity/{module}/{entity_id}")
    async def remove_favorite_by_entity(module: str, entity_id: str, user=Depends(current_user)):
        """Frontend'de yıldız butonunun favorite_id'yi hatırlamasına gerek
        kalmadan (module, entity_id) çiftiyle doğrudan kaldırma — FavoriteButton
        bileşeni için pratik."""
        result = await db.favorites.delete_one({"user_id": user["id"], "module": module, "entity_id": entity_id})
        return {"status": "deleted" if result.deleted_count else "not_found"}
