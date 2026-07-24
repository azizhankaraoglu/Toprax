"""
=====================================================================
Toprax — Harita Stüdyosu (Kişisel Harita Çalışma Alanları) (Denetim
raporu #9 / Faz 7)
=====================================================================
Kullanıcının kendi harita katmanlarını (dosya yükleyerek VEYA elle
çizerek) oluşturduğu, stil/popup ayarlarını kendi belirlediği, bir
projede birleştirip yayınlayabildiği (kendisi / organizasyon / belirli
kullanıcılar / herkese açık link) bağımsız bir modül.

`HaritaPaneli.jsx`'e (IT-14/15/16/17'nin Spatial Operations Center'ı)
BİLİNÇLİ OLARAK DOKUNULMADI — o widget/zaman-makinesi/toplu-işlem
merkezi olmaya devam eder. Bu modül farklı bir ihtiyacı karşılar:
"kendi haritamı ben kurayım" (GIS masaüstü uygulamalarındaki "proje/
katman" kavramına yakın).

Veri modeli:
- `map_layers` — bir katman (dosyadan içe aktarılmış veya elle çizilmiş),
  stil (`style`) ve popup şablonu (`popup_config`) taşır.
- `map_layer_features` — bir katmanın GERÇEK coğrafi kayıtları (2dsphere
  index, bbox sorgulanabilir) — `geo_import.py`'nin (IT-13.5) parse
  çıktısını AYNEN kullanır (yeniden yazılmadı), ayrıca yeni bir CSV lat/
  lon ayrıştırıcı (`_parse_csv_latlon`) eklendi (geo_import.py'nin
  desteklemediği tek format).
- `map_projects` — birden fazla katmanı (görünürlük/sıra/opaklık ile)
  bir arada tutan, kaydedilebilir/yayınlanabilir bir "harita".

Paylaşım İKİ BAĞIMSIZ boyuttur (forms_module.py'nin `share_mode`
deseniyle AYNI aile):
  1. Tenant-içi görünürlük (`share_scope`): private (sadece sahibi) |
     org_unit (kullanıcının organizasyon biriminin ALT/ÜST zinciri,
     map_snapshots.py'nin `_user_unit_chain` mantığıyla AYNI, burada
     KÜÇÜK bir kopyası tutulur — iki modülün ayrı yaşam döngüsü var) |
     tenant (kurum geneli) | users (elle seçilen `shared_user_ids`).
  2. Herkese açık link (`is_public` + `public_token`) — forms_module.py'nin
     `share_mode="public"` + `public_token` deseniyle BİREBİR AYNI, TAMAMEN
     BAĞIMSIZ bir anahtar (bir proje aynı anda hem "sadece bana özel"
     hem "herkese açık linki de var" olabilir — nadir ama meşru bir
     kombinasyon, ör. kendi taslağını görmeyen ama linkle gelen biri).

Limitler (plan'daki "10 MB / 20k feature"): `bulk-import` ucu HEM dosya
boyutunu (geo_import.py zaten 20 MB sınırlıyor, burada 20k feature ayrıca
kontrol edilir) HEM toplam katman feature sayısını (mevcut + yeni ≤ 20000)
sınırlar.
"""
import csv
import io
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Depends, Request, UploadFile, File, Form
from pydantic import BaseModel

from tenant_context import current_tenant_id

MAX_FEATURES_PER_LAYER = 20000

LAT_KEYS = {"lat", "latitude", "enlem", "y"}
LON_KEYS = {"lon", "lng", "long", "longitude", "boylam", "x"}


class LayerStyle(BaseModel):
    color: str = "#3B82F6"
    fillColor: str = "#3B82F6"
    weight: int = 2
    opacity: float = 1.0
    fillOpacity: float = 0.3
    icon: Optional[str] = None


class PopupConfig(BaseModel):
    title_template: str = ""     # ör. "{ad} — {alan} dekar"
    fields: List[str] = []       # popup'ta gösterilecek properties alan adları


class MapLayerCreate(BaseModel):
    name: str
    source_type: str = "drawn"   # geojson | kml | csv | drawn
    style: LayerStyle = LayerStyle()
    popup_config: PopupConfig = PopupConfig()


class MapLayerUpdate(BaseModel):
    name: Optional[str] = None
    style: Optional[LayerStyle] = None
    popup_config: Optional[PopupConfig] = None


class FeatureIn(BaseModel):
    geometry: Dict[str, Any]
    properties: Dict[str, Any] = {}


class ProjectLayerRef(BaseModel):
    layer_id: str
    visible: bool = True
    order: int = 0
    opacity: float = 1.0


class MapProjectCreate(BaseModel):
    name: str
    layers: List[ProjectLayerRef] = []
    basemap_key: str = "light"
    center: List[float] = [39.0, 35.0]
    zoom: int = 6


class MapProjectUpdate(BaseModel):
    name: Optional[str] = None
    layers: Optional[List[ProjectLayerRef]] = None
    basemap_key: Optional[str] = None
    center: Optional[List[float]] = None
    zoom: Optional[int] = None


class MapProjectShare(BaseModel):
    share_scope: str = "private"          # private | org_unit | tenant | users
    shared_unit_id: Optional[str] = None
    shared_user_ids: List[str] = []
    is_public: bool = False


def _parse_csv_latlon(content: bytes) -> List[Dict[str, Any]]:
    """geo_import.py'nin desteklemediği tek format — düz lat/lon CSV.
    Başlık satırında lat/lon'a karşılık gelen bir sütun ARANIR (LAT_KEYS/
    LON_KEYS, büyük/küçük harf duyarsız); bulunamazsa 400. Diğer TÜM
    sütunlar properties'e aynen kopyalanır."""
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV dosyası boş veya başlık satırı yok")
    lat_col = next((f for f in reader.fieldnames if f.strip().lower() in LAT_KEYS), None)
    lon_col = next((f for f in reader.fieldnames if f.strip().lower() in LON_KEYS), None)
    if not lat_col or not lon_col:
        raise HTTPException(400, "CSV'de lat/lon (enlem/boylam) sütunu bulunamadı — sütun adı lat/latitude/enlem ve lon/lng/longitude/boylam olmalı")
    features = []
    for row in reader:
        try:
            lat, lon = float(row[lat_col]), float(row[lon_col])
        except (TypeError, ValueError):
            continue
        props = {k: v for k, v in row.items() if k not in (lat_col, lon_col)}
        features.append({"geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props})
    if not features:
        raise HTTPException(400, "CSV'den geçerli hiçbir koordinat okunamadı")
    return features


async def _user_unit_chain(db, user_id: str) -> set:
    """map_snapshots.py'deki AYNI mantığın küçük bir kopyası — iki modül
    bağımsız yaşam döngülerine sahip (map_snapshots IT-16'dan, bu modül
    Faz 7'den), TKGM mapping (IT-16) emsaliyle AYNI bilinçli tekrar."""
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


def _can_access_project(doc: dict, user_id: str, unit_chain: set) -> bool:
    if doc.get("created_by_id") == user_id:
        return True
    scope = doc.get("share_scope", "private")
    if scope == "tenant":
        return True
    if scope == "org_unit" and doc.get("shared_unit_id") in unit_chain:
        return True
    if scope == "users" and user_id in (doc.get("shared_user_ids") or []):
        return True
    return False


def register_map_studio_routes(api_router, db, current_user, require_permission, log_audit,
                                require_feature=None, raw_db=None):
    require_feature = require_feature or (lambda key: (lambda: True))
    _unscoped = raw_db if raw_db is not None else getattr(db, "_real_db", db)

    async def _owned_layer_or_404(layer_id: str) -> dict:
        doc = await db.map_layers.find_one({"id": layer_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Katman bulunamadı")
        return doc

    def _check_layer_edit(doc: dict, user: dict):
        from config_service import get_system_tier
        is_owner = doc.get("created_by_id") == user["id"]
        is_moderator = get_system_tier(user.get("role")) in ("god_mode", "super_admin", "admin")
        if not (is_owner or is_moderator):
            raise HTTPException(403, "Sadece katmanın sahibi veya admin düzenleyebilir/silebilir")

    # =================================================================
    # KATMANLAR
    # =================================================================
    @api_router.get("/map-layers")
    async def list_map_layers(user=Depends(require_permission("map_studio:view")),
                               _feat=Depends(require_feature("map_studio"))):
        """Sadece KENDİ katmanlarım — katmanlar özel çalışma malzemesidir,
        paylaşılabilir birim `map_projects`'tir (bir projeyi paylaşmak onun
        referans verdiği katmanların verisini `/map-projects/{id}/full`
        üzerinden açar, katman listesine değil)."""
        docs = await db.map_layers.find({"created_by_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(300)
        for d in docs:
            d["is_owner"] = True
        return docs

    @api_router.post("/map-layers")
    async def create_map_layer(body: MapLayerCreate, request: Request,
                                user=Depends(require_permission("map_studio:create")),
                                _feat=Depends(require_feature("map_studio"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_by_id"] = user["id"]
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["feature_count"] = 0
        await db.map_layers.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="map_layer", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/map-layers/{layer_id}")
    async def update_map_layer(layer_id: str, body: MapLayerUpdate, request: Request,
                                user=Depends(require_permission("map_studio:create")),
                                _feat=Depends(require_feature("map_studio"))):
        old = await _owned_layer_or_404(layer_id)
        _check_layer_edit(old, user)
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.map_layers.update_one({"id": layer_id}, {"$set": updates})
        new = await db.map_layers.find_one({"id": layer_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="map_layer", entity_id=layer_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/map-layers/{layer_id}")
    async def delete_map_layer(layer_id: str, request: Request,
                                user=Depends(require_permission("map_studio:create")),
                                _feat=Depends(require_feature("map_studio"))):
        old = await _owned_layer_or_404(layer_id)
        _check_layer_edit(old, user)
        await db.map_layers.delete_one({"id": layer_id})
        await db.map_layer_features.delete_many({"layer_id": layer_id})
        await log_audit(db, user, action="delete", entity="map_layer", entity_id=layer_id, old_value=old, request=request)
        return {"status": "deleted"}

    # =================================================================
    # FEATURE'LAR — tekil (elle çizim) + toplu (dosya) içe aktarma
    # =================================================================
    @api_router.get("/map-layers/{layer_id}/features")
    async def list_layer_features(layer_id: str,
                                   user=Depends(require_permission("map_studio:view")),
                                   _feat=Depends(require_feature("map_studio"))):
        await _owned_layer_or_404(layer_id)
        return await db.map_layer_features.find({"layer_id": layer_id}, {"_id": 0}).to_list(MAX_FEATURES_PER_LAYER)

    @api_router.post("/map-layers/{layer_id}/features")
    async def add_layer_feature(layer_id: str, body: FeatureIn, request: Request,
                                 user=Depends(require_permission("map_studio:create")),
                                 _feat=Depends(require_feature("map_studio"))):
        layer = await _owned_layer_or_404(layer_id)
        _check_layer_edit(layer, user)
        if layer.get("feature_count", 0) >= MAX_FEATURES_PER_LAYER:
            raise HTTPException(400, f"Katman başına en fazla {MAX_FEATURES_PER_LAYER} kayıt")
        doc = {
            "id": str(uuid.uuid4()), "layer_id": layer_id,
            "geometry": body.geometry, "properties": body.properties,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.map_layer_features.insert_one(doc)
        doc.pop("_id", None)
        await db.map_layers.update_one({"id": layer_id}, {"$inc": {"feature_count": 1}})
        return doc

    @api_router.put("/map-layer-features/{feature_id}")
    async def update_layer_feature(feature_id: str, body: FeatureIn,
                                    user=Depends(require_permission("map_studio:create")),
                                    _feat=Depends(require_feature("map_studio"))):
        feat = await db.map_layer_features.find_one({"id": feature_id}, {"_id": 0})
        if not feat:
            raise HTTPException(404, "Kayıt bulunamadı")
        layer = await _owned_layer_or_404(feat["layer_id"])
        _check_layer_edit(layer, user)
        await db.map_layer_features.update_one(
            {"id": feature_id}, {"$set": {"geometry": body.geometry, "properties": body.properties}},
        )
        return await db.map_layer_features.find_one({"id": feature_id}, {"_id": 0})

    @api_router.delete("/map-layer-features/{feature_id}")
    async def delete_layer_feature(feature_id: str,
                                    user=Depends(require_permission("map_studio:create")),
                                    _feat=Depends(require_feature("map_studio"))):
        feat = await db.map_layer_features.find_one({"id": feature_id}, {"_id": 0})
        if not feat:
            raise HTTPException(404, "Kayıt bulunamadı")
        layer = await _owned_layer_or_404(feat["layer_id"])
        _check_layer_edit(layer, user)
        await db.map_layer_features.delete_one({"id": feature_id})
        await db.map_layers.update_one({"id": feat["layer_id"]}, {"$inc": {"feature_count": -1}})
        return {"status": "deleted"}

    @api_router.post("/map-layers/{layer_id}/import")
    async def bulk_import_layer(
        layer_id: str,
        file: UploadFile = File(...),
        source_epsg: Optional[int] = Form(None),
        user=Depends(require_permission("map_studio:create")),
        _feat=Depends(require_feature("map_studio")),
    ):
        """geo_import.py'nin (IT-13.5) parse fonksiyonlarını AYNEN kullanır
        (GeoJSON/KML/KMZ/SHP/DXF) + bu modüle özel CSV lat/lon ayrıştırıcı.
        `geo_import.py`'nin `/geo-import/parse`'ından FARKI: bu uç sonucu
        DOĞRUDAN katmana YAZAR (parsel akışındaki "önizle sonra onayla" iki
        adımlı akışın aksine — burada önizleme frontend'de dosya seçilir
        seçilmez ayrı bir `/geo-import/parse` çağrısıyla zaten yapılabilir,
        onay bu ayrı `import` çağrısıdır)."""
        layer = await _owned_layer_or_404(layer_id)
        _check_layer_edit(layer, user)

        from geo_import import _parse_geojson, _parse_kml, _parse_kmz, _parse_shp_zip, _parse_dxf, MAX_UPLOAD_BYTES

        filename = (file.filename or "").lower()
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, "Dosya çok büyük (20 MB sınırı)")

        if filename.endswith(".geojson") or filename.endswith(".json"):
            features = _parse_geojson(content)
        elif filename.endswith(".kml"):
            features = _parse_kml(content)
        elif filename.endswith(".kmz"):
            features = _parse_kmz(content)
        elif filename.endswith(".zip"):
            features = _parse_shp_zip(content, source_epsg)
        elif filename.endswith(".dxf"):
            features = _parse_dxf(content, source_epsg)
        elif filename.endswith(".csv"):
            features = _parse_csv_latlon(content)
        else:
            raise HTTPException(400, f"Desteklenmeyen dosya türü: {filename or '(adsız)'}")

        current_count = layer.get("feature_count", 0)
        if current_count + len(features) > MAX_FEATURES_PER_LAYER:
            raise HTTPException(400, f"İçe aktarma katman limitini aşıyor (mevcut {current_count} + yeni {len(features)} > {MAX_FEATURES_PER_LAYER})")

        docs = [{
            "id": str(uuid.uuid4()), "layer_id": layer_id,
            "geometry": f["geometry"], "properties": f.get("properties") or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        } for f in features]
        if docs:
            await db.map_layer_features.insert_many(docs)
        await db.map_layers.update_one({"id": layer_id}, {"$inc": {"feature_count": len(docs)}})
        for d in docs:
            d.pop("_id", None)
        return {"status": "ok", "imported": len(docs)}

    # =================================================================
    # PROJELER — katmanları birleştiren, kaydedilebilir/yayınlanabilir harita
    # =================================================================
    async def _owned_project_or_404(project_id: str) -> dict:
        doc = await db.map_projects.find_one({"id": project_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Harita projesi bulunamadı")
        return doc

    def _check_project_edit(doc: dict, user: dict):
        from config_service import get_system_tier
        is_owner = doc.get("created_by_id") == user["id"]
        is_moderator = get_system_tier(user.get("role")) in ("god_mode", "super_admin", "admin")
        if not (is_owner or is_moderator):
            raise HTTPException(403, "Sadece projenin sahibi veya admin düzenleyebilir/silebilir")

    @api_router.get("/map-projects")
    async def list_map_projects(user=Depends(require_permission("map_studio:view")),
                                 _feat=Depends(require_feature("map_studio"))):
        unit_chain = await _user_unit_chain(db, user["id"])
        docs = await db.map_projects.find({"$or": [
            {"created_by_id": user["id"]}, {"share_scope": "tenant"},
            {"share_scope": "org_unit", "shared_unit_id": {"$in": list(unit_chain)}},
            {"share_scope": "users", "shared_user_ids": user["id"]},
        ]}, {"_id": 0}).sort("created_at", -1).to_list(200)
        for d in docs:
            d["is_owner"] = d.get("created_by_id") == user["id"]
        return docs

    @api_router.post("/map-projects")
    async def create_map_project(body: MapProjectCreate, request: Request,
                                  user=Depends(require_permission("map_studio:create")),
                                  _feat=Depends(require_feature("map_studio"))):
        doc = body.model_dump()
        doc["layers"] = [l if isinstance(l, dict) else l for l in doc["layers"]]
        doc["id"] = str(uuid.uuid4())
        doc["created_by_id"] = user["id"]
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["share_scope"] = "private"
        doc["shared_unit_id"] = None
        doc["shared_user_ids"] = []
        doc["is_public"] = False
        doc["public_token"] = None
        await db.map_projects.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="map_project", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/map-projects/{project_id}")
    async def update_map_project(project_id: str, body: MapProjectUpdate, request: Request,
                                  user=Depends(require_permission("map_studio:create")),
                                  _feat=Depends(require_feature("map_studio"))):
        old = await _owned_project_or_404(project_id)
        _check_project_edit(old, user)
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "layers" in updates:
            updates["layers"] = [l if isinstance(l, dict) else l for l in updates["layers"]]
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.map_projects.update_one({"id": project_id}, {"$set": updates})
        new = await db.map_projects.find_one({"id": project_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="map_project", entity_id=project_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/map-projects/{project_id}")
    async def delete_map_project(project_id: str, request: Request,
                                  user=Depends(require_permission("map_studio:create")),
                                  _feat=Depends(require_feature("map_studio"))):
        old = await _owned_project_or_404(project_id)
        _check_project_edit(old, user)
        await db.map_projects.delete_one({"id": project_id})
        await log_audit(db, user, action="delete", entity="map_project", entity_id=project_id, old_value=old, request=request)
        return {"status": "deleted"}

    @api_router.post("/map-projects/{project_id}/share")
    async def share_map_project(project_id: str, body: MapProjectShare, request: Request,
                                 user=Depends(require_permission("map_studio:share")),
                                 _feat=Depends(require_feature("map_studio"))):
        old = await _owned_project_or_404(project_id)
        _check_project_edit(old, user)
        if body.share_scope not in ("private", "org_unit", "tenant", "users"):
            raise HTTPException(400, "Geçersiz share_scope (private|org_unit|tenant|users)")
        if body.share_scope == "org_unit" and not body.shared_unit_id:
            raise HTTPException(400, "org_unit paylaşımı için shared_unit_id gerekli")
        updates = {
            "share_scope": body.share_scope,
            "shared_unit_id": body.shared_unit_id if body.share_scope == "org_unit" else None,
            "shared_user_ids": body.shared_user_ids if body.share_scope == "users" else [],
            "is_public": body.is_public,
        }
        if body.is_public and not old.get("public_token"):
            updates["public_token"] = secrets.token_urlsafe(12)
        elif not body.is_public:
            updates["public_token"] = None
        await db.map_projects.update_one({"id": project_id}, {"$set": updates})
        new = await db.map_projects.find_one({"id": project_id}, {"_id": 0})
        await log_audit(db, user, action="share", entity="map_project", entity_id=project_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.get("/map-projects/{project_id}/full")
    async def get_map_project_full(project_id: str,
                                    user=Depends(require_permission("map_studio:view")),
                                    _feat=Depends(require_feature("map_studio"))):
        """Proje + tüm katmanlarının stil/popup config'i + feature'ları TEK
        istekte — harita render'ı için (N ayrı istek yerine)."""
        project = await _owned_project_or_404(project_id)
        unit_chain = await _user_unit_chain(db, user["id"])
        if not _can_access_project(project, user["id"], unit_chain):
            raise HTTPException(403, "Bu proje size paylaşılmamış")
        layer_ids = [l["layer_id"] for l in project.get("layers", [])]
        layers = await db.map_layers.find({"id": {"$in": layer_ids}}, {"_id": 0}).to_list(200)
        layers_by_id = {l["id"]: l for l in layers}
        for lref in project["layers"]:
            layer = layers_by_id.get(lref["layer_id"])
            if not layer:
                continue
            layer["features"] = await db.map_layer_features.find(
                {"layer_id": lref["layer_id"]}, {"_id": 0},
            ).to_list(MAX_FEATURES_PER_LAYER)
        project["is_owner"] = project.get("created_by_id") == user["id"]
        return {"project": project, "layers": layers_by_id}

    # =================================================================
    # PUBLIC GÖRÜNTÜLEYİCİ — login GEREKMEZ (forms_module.py'nin _unscoped
    # token-arama kalıbıyla AYNI).
    # =================================================================
    @api_router.get("/public/maps/{token}")
    async def get_public_map(token: str):
        project = await _unscoped.map_projects.find_one({"public_token": token, "is_public": True}, {"_id": 0})
        if not project:
            raise HTTPException(404, "Harita bulunamadı veya yayında değil")
        reset_tok = current_tenant_id.set(project.get("tenant_id"))
        try:
            from platform_core import is_feature_enabled
            if not await is_feature_enabled(db, "map_studio"):
                raise HTTPException(403, "'Harita Stüdyosu' özelliği bu kurum için kapatılmış")
            layer_ids = [l["layer_id"] for l in project.get("layers", [])]
            layers = await db.map_layers.find({"id": {"$in": layer_ids}}, {"_id": 0}).to_list(200)
            layers_by_id = {l["id"]: l for l in layers}
            for lref in project["layers"]:
                layer = layers_by_id.get(lref["layer_id"])
                if not layer:
                    continue
                layer["features"] = await db.map_layer_features.find(
                    {"layer_id": lref["layer_id"]}, {"_id": 0},
                ).to_list(MAX_FEATURES_PER_LAYER)
        finally:
            current_tenant_id.reset(reset_tok)
        return {"project": project, "layers": layers_by_id}
