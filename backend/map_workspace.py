"""
=====================================================================
Toprax — Harita Paneli: Kişisel Çalışma Alanı (IT-14)
=====================================================================
IT-14'ün "kişisel çalışma alanı kaydetme" maddesi: kullanıcının Harita
Paneli'ndeki tercihini (hangi widget'lar açık, harita merkezi/zoom,
aktif Gelişmiş Filtre) hatırlar. saved_queries.py'nin aksine burada
İSİMLENDİRİLMİŞ/ÇOKLU kayıt YOK — roadmap metni tekil "bir çalışma
alanı" diyor, bu yüzden kullanıcı başına TEK kayıt (upsert) yeterli;
gereksiz karmaşıklık (adlandırma, favori, paylaşım) eklenmedi.

`widget_keys` ve `filters` bu modül için OPAK'tır — hangi widget'ların
var olduğunu veya filtre şemasını bilmez/doğrulamaz, sadece frontend'in
gönderdiği listeyi/objeyi saklar. Bu bilinçli: yeni bir widget eklemek
(frontend/src/lib/mapWidgets/) bu backend modülünü DEĞİŞTİRMEYİ
gerektirmez — IT-14'ün "yeni widget eklemek harita mimarisini
değiştirmeyi gerektirmemeli" ilkesi backend'e de taşınmış olur.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Depends
from pydantic import BaseModel


class MapWorkspaceSave(BaseModel):
    widget_keys: List[str] = []
    map_center: Optional[List[float]] = None   # [lat, lng]
    map_zoom: Optional[int] = None
    filters: Optional[Dict[str, Any]] = None    # FilterPanel'in {rows, logic} durumu — opak
    basemap_key: Optional[str] = None           # IT-15 — seçili basemap ("dark"/"light"/...), opak
    visible_layers: Optional[List[str]] = None  # IT-15 — açık katman anahtarları, opak


def register_map_workspace_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/map-workspaces/me")
    async def get_my_map_workspace(user=Depends(require_permission("parcels:view"))):
        """Kayıtlı bir çalışma alanı yoksa null döner — frontend varsayılanları kullanır."""
        return await db.map_workspaces.find_one({"user_id": user["id"]}, {"_id": 0})

    @api_router.put("/map-workspaces/me")
    async def save_my_map_workspace(body: MapWorkspaceSave, user=Depends(require_permission("parcels:view"))):
        """Idempotent upsert — kullanıcı başına tek kayıt."""
        existing = await db.map_workspaces.find_one({"user_id": user["id"]}, {"_id": 0})
        updates = body.model_dump()
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        if existing:
            await db.map_workspaces.update_one({"id": existing["id"]}, {"$set": updates})
            return {**existing, **updates}
        doc = {"id": str(uuid.uuid4()), "user_id": user["id"], **updates}
        await db.map_workspaces.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @api_router.delete("/map-workspaces/me")
    async def reset_my_map_workspace(user=Depends(require_permission("parcels:view"))):
        """Kayıtlı çalışma alanını siler — frontend varsayılanlara döner."""
        result = await db.map_workspaces.delete_one({"user_id": user["id"]})
        return {"status": "deleted" if result.deleted_count else "not_found"}
