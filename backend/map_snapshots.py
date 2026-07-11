"""
=====================================================================
TabSIS — Harita Snapshot (IT-16)
=====================================================================
"Harita Snapshot (kaydet/paylaş)" — HaritaPaneli'ndeki o anki görünümü
(harita merkezi/zoom, aktif widget'lar, basemap, katmanlar, seçili
parseller) ADLANDIRILMIŞ bir kayıt olarak saklar.

`map_workspace.py` (IT-14) ile KARIŞTIRILMAMALI: o kullanıcı başına TEK,
adsız, opak "son durumu hatırla" kaydıdır (sayfa her açıldığında sessizce
uygulanır). Snapshot ise `saved_queries.py` (IT-09) ile AYNI kalıpta —
adlandırılmış, ÇOKLU, paylaşılabilir (`is_shared`) "an" kayıtlarıdır;
bir meslektaşla "şu anki görünüme bak" demek için kullanılır.

Bu proje bir ekran görüntüsü/canvas kütüphanesi (html2canvas vb.)
KULLANMAZ — bilinçli tercih (yeni bağımlılık gerektirmemek için,
Karar Protokolü: yeni bağımlılık her zaman sorulur). "Paylaş" ihtiyacı
DURUM PAYLAŞIMI ile karşılanıyor: bir snapshot açıldığında
(`GET /map-snapshots/{id}`, frontend `/harita-paneli?snapshot=<id>`
linkiyle tetikler) harita o ANA (merkez/zoom/widget/basemap/katman/
seçim) BİREBİR geri yüklenir — statik bir görüntü DEĞİLDİR
(saved_queries'in "sorguyu değil DSL'i saklar" ilkesiyle aynı aile).

`filters` alanı bilinçli olarak var ama frontend'den DOLDURULMAZ —
map_workspace.py'deki AYNI kısıtlama burada da geçerli: FilterPanel'in
kendi iç {rows, logic} state'ini dışarı sızdırmaması gerekiyordu
(bkz. CLAUDE.md Bilinen Tuzaklar). İleride FilterPanel bu state'i dışa
verebilir hale gelirse bu alan zaten hazır.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel


class MapSnapshotCreate(BaseModel):
    name: str
    map_center: List[float]
    map_zoom: int
    widget_keys: List[str] = []
    basemap_key: Optional[str] = None
    visible_layers: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    selected_parcel_ids: Optional[List[str]] = None
    is_shared: bool = False


def register_map_snapshot_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/map-snapshots")
    async def list_map_snapshots(user=Depends(require_permission("parcels:view"))):
        """Kendi snapshot'larım + tenant içinde PAYLAŞILANLAR (saved_queries'teki
        is_shared kalıbıyla aynı — modül-bazlı ek izin kontrolüne gerek yok,
        Harita Paneli'nin kendisi zaten parcels:view gerektiriyor)."""
        docs = await db.map_snapshots.find(
            {"$or": [{"created_by_id": user["id"]}, {"is_shared": True}]}, {"_id": 0}
        ).sort("created_at", -1).to_list(200)
        for d in docs:
            d["is_owner"] = d.get("created_by_id") == user["id"]
        return docs

    @api_router.get("/map-snapshots/{snapshot_id}")
    async def get_map_snapshot(snapshot_id: str, user=Depends(require_permission("parcels:view"))):
        """Tek bir snapshot'ı açar — paylaşım linkinden (?snapshot=<id>) gelindiğinde
        kullanılır. Sahibi DEĞİLSE sadece is_shared=True ise erişilebilir."""
        doc = await db.map_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Snapshot bulunamadı")
        if doc.get("created_by_id") != user["id"] and not doc.get("is_shared"):
            raise HTTPException(403, "Bu snapshot paylaşılmamış")
        return doc

    @api_router.post("/map-snapshots")
    async def create_map_snapshot(body: MapSnapshotCreate, request: Request,
                                   user=Depends(require_permission("parcels:view"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_by_id"] = user["id"]
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.map_snapshots.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="map_snapshot", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.delete("/map-snapshots/{snapshot_id}")
    async def delete_map_snapshot(snapshot_id: str, request: Request,
                                   user=Depends(require_permission("parcels:view"))):
        """Gerçek silme (soft-delete DEĞİL) — saved_queries.py ile aynı gerekçe:
        bir görünüm tercihidir, finansal/tarihsel veri değildir."""
        from config_service import get_system_tier
        old = await db.map_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Snapshot bulunamadı")
        is_owner = old.get("created_by_id") == user["id"]
        is_moderator = get_system_tier(user.get("role")) in ("god_mode", "super_admin", "admin")
        if not (is_owner or is_moderator):
            raise HTTPException(403, "Sadece snapshot sahibi veya admin silebilir")
        await db.map_snapshots.delete_one({"id": snapshot_id})
        await log_audit(db, user, action="delete", entity="map_snapshot", entity_id=snapshot_id, old_value=old, request=request)
        return {"status": "deleted"}
