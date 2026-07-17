"""
=====================================================================
Toprax — İdari Alanlar + Demografi + Layer v1 (IT-13.6)
=====================================================================
İl/İlçe/Mahalle sınır geometrilerini (GeoJSON Polygon/MultiPolygon)
saklar. Sınır verisi SİSTEME GÖMÜLMEZ/SEED EDİLMEZ — kullanıcı
IT-13.5'in Geo Dosya İçe Aktarma akışıyla (geo_import.py) kendi SHP/
GeoJSON/KML/DXF dosyasını yükleyip haritada onaylar; tekli onay
`PUT /admin-areas/{id}` (`geometry` alanı) ile, TOPLU onay ise bu
modülün kendi `POST /admin-areas/bulk-import` ucuyla yapılır (tek
SHP'den çok sayıda idari alan — ad/tip alan eşleştirmesiyle).

"IT-01.5 lookup'larıyla tek kaynak ilkesi": il/ilçe İSİMLERİ zaten
field_definitions.py'nin `seed_il_ilce_lookup`'ıyla lookup_groups/
lookup_values'da tutuluyor (bkz. CLAUDE.md "İl/İlçe lookup verisi").
Bu modül o isimleri TEKRAR YAZMAZ — `lookup_value_id` alanıyla ilgili
lookup_value'ya REFERANS verir (isim orada tek yerde yönetilir).
`name` alanı sadece lookup'ta karşılığı olmayan seviyeler (mahalle,
veya lookup dışı özel bölgeler) için serbestçe girilir.

Demografi (nüfus/tarım alanı/tahmini çiftçi sayısı) convention #8
gereği gerçek tipli Pydantic kolonlarıdır (JSON blob YASAK) — bu
modülde SABİT tanımlıdır ama field_definitions (module="admin_areas")
üzerinden zorunlu/görünür/sıra davranışı yönetilir, tıpkı Farmer'ın
19 ek alanı gibi.
"""
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

AREA_TYPES = ("il", "ilce", "mahalle")
MAX_SIMPLIFY_POINTS = 300  # Layer v1 harita performansı için — sadece LİSTE/harita yanıtına uygulanır


def _simplify_ring(ring: List[List[float]], max_points: int) -> List[List[float]]:
    """Basit nokta atlama (decimation) — Douglas-Peucker DEĞİL, yeni bir
    kütüphane (shapely vb.) gerektirmeden 'haritada gösterim için yeterince
    hafif' bir sadeleştirme sağlar. İlk/son nokta (kapanış) her zaman kalır."""
    n = len(ring)
    if n <= max_points:
        return ring
    step = math.ceil(n / max_points)
    simplified = ring[::step]
    if simplified[-1] != ring[-1]:
        simplified.append(ring[-1])
    return simplified


def _simplify_geometry(geometry: Optional[Dict[str, Any]], max_points: int = MAX_SIMPLIFY_POINTS) -> Optional[Dict[str, Any]]:
    if not geometry:
        return geometry
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        return {"type": "Polygon", "coordinates": [_simplify_ring(ring, max_points) for ring in coords]}
    if gtype == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [[_simplify_ring(ring, max_points) for ring in poly] for poly in coords]}
    return geometry


class AdminAreaCreate(BaseModel):
    name: str
    area_type: str                                   # il | ilce | mahalle
    parent_id: Optional[str] = None                  # üst idari alan (admin_areas.id)
    lookup_value_id: Optional[str] = None             # IT-01.5 tek kaynak ilkesi — il/ilçe lookup_value referansı
    geometry: Optional[Dict[str, Any]] = None          # GeoJSON Polygon/MultiPolygon
    # ============ B1 (portföy) — köy/mahalle SORUMLUSU ============
    # Bir köye/mahalleye atanan sorumlu personel (users.id). O alandaki çiftçi
    # ve parseller bu sorumluyu DEVRALIR (köy bazlı miras — bkz. #6). Boş olabilir.
    responsible_user_id: Optional[str] = None

    # ============ IT-13.6 — Demografi (field_definitions module="admin_areas") ============
    population: Optional[int] = None
    agricultural_area_dekar: Optional[float] = None
    farmer_count_est: Optional[int] = None


class AdminAreaUpdate(BaseModel):
    name: Optional[str] = None
    area_type: Optional[str] = None
    parent_id: Optional[str] = None
    lookup_value_id: Optional[str] = None
    responsible_user_id: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    population: Optional[int] = None
    agricultural_area_dekar: Optional[float] = None
    farmer_count_est: Optional[int] = None
    is_active: Optional[bool] = None


class BulkImportRequest(BaseModel):
    area_type: str                                    # bu importtaki TÜM feature'lar aynı tip (il/ilçe/mahalle)
    name_field: str                                    # SHP/DXF attribute'larından hangisi "ad" (ör. "ad", "ILCE_ADI")
    parent_id: Optional[str] = None                    # opsiyonel — hepsi aynı üst alana bağlanacaksa
    features: List[Dict[str, Any]] = []                 # geo_import.py'nin /geo-import/parse çıktısı (features listesi)


def register_admin_area_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/admin-areas/meta")
    async def admin_area_meta(user=Depends(current_user)):
        return {"area_types": [{"key": t, "label": {"il": "İl", "ilce": "İlçe", "mahalle": "Mahalle"}[t]} for t in AREA_TYPES]}

    @api_router.get("/admin-areas")
    async def list_admin_areas(
        area_type: Optional[str] = None, parent_id: Optional[str] = None,
        user=Depends(require_permission("admin_areas:view")),
    ):
        """Liste/harita katmanı yanıtı — geometri Layer v1 performansı için sadeleştirilir."""
        query: Dict[str, Any] = {"is_active": {"$ne": False}}
        if area_type:
            query["area_type"] = area_type
        if parent_id:
            query["parent_id"] = parent_id
        docs = await db.admin_areas.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
        for d in docs:
            d["geometry"] = _simplify_geometry(d.get("geometry"))
        return docs

    @api_router.get("/admin-areas/{area_id}")
    async def get_admin_area(area_id: str, user=Depends(require_permission("admin_areas:view"))):
        """Tam hassasiyetli geometri — düzenleme/onay ekranı için sadeleştirilmez."""
        doc = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "İdari alan bulunamadı")
        return doc

    @api_router.post("/admin-areas")
    async def create_admin_area(body: AdminAreaCreate, request: Request, user=Depends(require_permission("admin_areas:manage"))):
        if body.area_type not in AREA_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {body.area_type}. Geçerli değerler: {AREA_TYPES}")
        if body.parent_id and not await db.admin_areas.find_one({"id": body.parent_id}, {"_id": 0}):
            raise HTTPException(404, "Üst idari alan bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.admin_areas.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="admin_area", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/admin-areas/{area_id}")
    async def update_admin_area(area_id: str, body: AdminAreaUpdate, request: Request, user=Depends(require_permission("admin_areas:manage"))):
        old = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "İdari alan bulunamadı")
        if body.area_type is not None and body.area_type not in AREA_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {body.area_type}. Geçerli değerler: {AREA_TYPES}")
        if body.parent_id and not await db.admin_areas.find_one({"id": body.parent_id}, {"_id": 0}):
            raise HTTPException(404, "Üst idari alan bulunamadı")
        # responsible_user_id="" → sorumluyu KALDIR (None'a çevir; boş string saklanmaz).
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "responsible_user_id" in updates and updates["responsible_user_id"] == "":
            updates["responsible_user_id"] = None
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.admin_areas.update_one({"id": area_id}, {"$set": updates})
        new = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="admin_area", entity_id=area_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/admin-areas/{area_id}")
    async def delete_admin_area(area_id: str, request: Request, user=Depends(require_permission("admin_areas:manage"))):
        """Soft delete — convention #3, alt idari alanlar/geçmiş referanslar bozulmasın diye."""
        old = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "İdari alan bulunamadı")
        await db.admin_areas.update_one({"id": area_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="delete", entity="admin_area", entity_id=area_id, old_value=old, request=request)
        return {"status": "deactivated"}

    @api_router.post("/admin-areas/bulk-import")
    async def bulk_import_admin_areas(body: BulkImportRequest, request: Request, user=Depends(require_permission("admin_areas:manage"))):
        """
        Tek bir SHP/GeoJSON/KML dosyasından ayrıştırılmış (geo_import.py
        /geo-import/parse ÇIKTISI, henüz hiçbir yere kaydedilmemiş)
        birden fazla feature'ı toplu idari alan kaydına çevirir. Idempotent
        DEĞİLDİR — aynı dosya iki kez içe aktarılırsa iki kez kayıt oluşur
        (kullanıcı önizleme ekranında bunu görüp bilinçli onaylar).
        """
        if body.area_type not in AREA_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {body.area_type}. Geçerli değerler: {AREA_TYPES}")
        if not body.features:
            raise HTTPException(400, "İçe aktarılacak feature bulunamadı")

        created = []
        for f in body.features:
            geom = f.get("geometry")
            if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                continue  # idari sınır için Point/LineString atlanır
            name = (f.get("properties") or {}).get(body.name_field) or "(adsız)"
            doc = {
                "id": str(uuid.uuid4()), "name": str(name), "area_type": body.area_type,
                "parent_id": body.parent_id, "lookup_value_id": None, "geometry": geom,
                "population": None, "agricultural_area_dekar": None, "farmer_count_est": None,
                "is_active": True, "created_by": user.get("full_name") or user.get("email"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.admin_areas.insert_one(doc)
            doc.pop("_id", None)
            created.append(doc)

        await log_audit(db, user, action="create", entity="admin_area", entity_id="bulk_import",
                         new_value={"count": len(created), "area_type": body.area_type}, request=request)
        return {"status": "imported", "count": len(created)}

    @api_router.get("/admin-areas/{area_id}/summary")
    async def admin_area_summary(area_id: str, user=Depends(require_permission("admin_areas:view"))):
        """
        O idari alanın sınırı İÇİNDEKİ çiftçi/parselleri döner —
        Mongo'nun $geoIntersects'i (2dsphere index, bkz. server.py başlangıç
        index'leri) ile GERÇEK geometrik kesişim hesaplanır, village/region
        eşleştirmesi gibi kaba bir yaklaşıklık DEĞİLDİR.
        """
        area = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not area:
            raise HTTPException(404, "İdari alan bulunamadı")
        if not area.get("geometry"):
            return {"area": area, "parcel_count": 0, "farmer_count": 0, "parcels": []}

        parcels = await db.parcels.find(
            {"geometry": {"$geoIntersects": {"$geometry": area["geometry"]}}}, {"_id": 0}
        ).to_list(2000)
        farmer_ids = {p["farmer_id"] for p in parcels if p.get("farmer_id")}
        return {
            "area": area,
            "parcel_count": len(parcels),
            "farmer_count": len(farmer_ids),
            "parcels": [{"id": p["id"], "name": p.get("name"), "parcel_code": p.get("parcel_code")} for p in parcels],
        }
