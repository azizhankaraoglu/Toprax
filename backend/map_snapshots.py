"""
=====================================================================
Toprax — Harita Snapshot (IT-16)
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
    # KONU 2.2 — Workspace paylaşımı 3 kapsamda:
    #   "private"  → sadece sahibi (varsayılan),
    #   "org_unit" → organizasyon hiyerarşisindeki (IT-07b) belirli bir birim
    #                 ve ALT birimlerindeki herkes (shared_unit_id),
    #   "tenant"   → tüm tenant (şirket geneli).
    # `is_shared` (IT-16) geriye uyumluluk için korunur: True ≡ "tenant".
    share_scope: str = "private"
    shared_unit_id: Optional[str] = None
    is_shared: bool = False


async def _user_unit_chain(db, user_id: str) -> set:
    """KONU 2.2 — kullanıcının ait olduğu organizasyon birimi + TÜM ÜST
    birimleri (ata zinciri). Bir snapshot bir üst birime (ör. "Konya Bölgesi")
    paylaşılmışsa, o birimin ALT birimindeki kullanıcı da görebilmeli: yani
    paylaşılan birim kullanıcının ata zincirinde olmalı. Aktif atama/pozisyon
    yoksa boş küme (sadece kendi + tenant paylaşımlarını görür)."""
    from organization import get_active_position
    assignment = await get_active_position(db, user_id)
    if not assignment or not assignment.get("position_id"):
        return set()
    position = await db.positions.find_one({"id": assignment["position_id"]}, {"_id": 0})
    unit_id = (position or {}).get("organization_unit_id")
    chain, seen, depth = set(), set(), 0
    while unit_id and unit_id not in seen and depth < 12:
        chain.add(unit_id)
        seen.add(unit_id)
        unit = await db.organization_units.find_one({"id": unit_id}, {"_id": 0})
        unit_id = (unit or {}).get("parent_unit_id")
        depth += 1
    return chain


def _can_access(doc: dict, user_id: str, unit_chain: set) -> bool:
    if doc.get("created_by_id") == user_id:
        return True
    scope = doc.get("share_scope") or ("tenant" if doc.get("is_shared") else "private")
    if scope == "tenant" or doc.get("is_shared"):
        return True
    if scope == "org_unit" and doc.get("shared_unit_id") in unit_chain:
        return True
    return False


def register_map_snapshot_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/map-snapshots")
    async def list_map_snapshots(user=Depends(require_permission("parcels:view"))):
        """Kendi snapshot'larım + tenant içinde paylaşılanlar + organizasyon
        birimime (veya üst birimlerimden birine) paylaşılanlar (KONU 2.2)."""
        unit_chain = await _user_unit_chain(db, user["id"])
        query = {"$or": [
            {"created_by_id": user["id"]},
            {"is_shared": True},
            {"share_scope": "tenant"},
            {"share_scope": "org_unit", "shared_unit_id": {"$in": list(unit_chain)}},
        ]}
        docs = await db.map_snapshots.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
        for d in docs:
            d["is_owner"] = d.get("created_by_id") == user["id"]
        return docs

    @api_router.get("/map-snapshots/{snapshot_id}")
    async def get_map_snapshot(snapshot_id: str, user=Depends(require_permission("parcels:view"))):
        """Tek bir snapshot'ı açar — paylaşım linkinden (?snapshot=<id>) gelindiğinde
        kullanılır. Sahibi DEĞİLSE sadece kendisine paylaşılmışsa (tenant veya
        org_unit kapsamında) erişilebilir; alıcı tarafta salt-okunur açılır."""
        doc = await db.map_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Snapshot bulunamadı")
        unit_chain = await _user_unit_chain(db, user["id"])
        if not _can_access(doc, user["id"], unit_chain):
            raise HTTPException(403, "Bu snapshot size paylaşılmamış")
        doc["is_owner"] = doc.get("created_by_id") == user["id"]
        return doc

    @api_router.post("/map-snapshots/{snapshot_id}/copy")
    async def copy_map_snapshot(snapshot_id: str, request: Request,
                                user=Depends(require_permission("parcels:view"))):
        """KONU 2.2 — "Kendime kopyala": paylaşılan (salt-okunur) bir snapshot'ı
        kullanıcının kendi private workspace'ine klonlar (yeni id, yeni sahip,
        paylaşım sıfırlanır). Alıcı böylece kopyayı serbestçe düzenleyebilir."""
        src = await db.map_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
        if not src:
            raise HTTPException(404, "Snapshot bulunamadı")
        unit_chain = await _user_unit_chain(db, user["id"])
        if not _can_access(src, user["id"], unit_chain):
            raise HTTPException(403, "Bu snapshot size paylaşılmamış")
        clone = {k: v for k, v in src.items() if k not in (
            "id", "created_by_id", "created_by", "created_at", "is_owner",
            "share_scope", "shared_unit_id", "is_shared")}
        clone["id"] = str(uuid.uuid4())
        clone["name"] = f"{src.get('name', 'Görünüm')} (kopya)"
        clone["created_by_id"] = user["id"]
        clone["created_by"] = user.get("full_name") or user.get("email")
        clone["created_at"] = datetime.now(timezone.utc).isoformat()
        clone["share_scope"] = "private"
        clone["shared_unit_id"] = None
        clone["is_shared"] = False
        await db.map_snapshots.insert_one(dict(clone))
        clone.pop("_id", None)
        await log_audit(db, user, action="copy", entity="map_snapshot", entity_id=clone["id"],
                        new_value={"source_id": snapshot_id}, request=request)
        clone["is_owner"] = True
        return clone

    @api_router.post("/map-snapshots")
    async def create_map_snapshot(body: MapSnapshotCreate, request: Request,
                                   user=Depends(require_permission("parcels:view"))):
        doc = body.model_dump()
        # KONU 2.2 — kapsam normalizasyonu + doğrulama (is_shared ile senkron).
        scope = doc.get("share_scope") or "private"
        if doc.get("is_shared") and scope == "private":
            scope = "tenant"   # IT-16 geriye uyumluluk
        if scope not in ("private", "org_unit", "tenant"):
            raise HTTPException(400, "Geçersiz share_scope (private|org_unit|tenant)")
        if scope == "org_unit" and not doc.get("shared_unit_id"):
            raise HTTPException(400, "org_unit paylaşımı için shared_unit_id gerekli")
        if scope != "org_unit":
            doc["shared_unit_id"] = None
        doc["share_scope"] = scope
        doc["is_shared"] = scope == "tenant"
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
