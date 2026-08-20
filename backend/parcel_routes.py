"""
=====================================================================
Toprax — Parsel Yönetimi (CRUD + geo işlemler + import)
=====================================================================
Denetim A6 (2026-07-24): server.py (~2900 satır) modülerleştirmesi —
bu dosyadaki endpoint'ler server.py'den BİREBİR taşındı, davranış
değişikliği YOK. Route kayıt SIRASI korunur: register çağrısı server.py
içinde bloğun orijinal konumundan yapılır (Starlette route-order tuzağı,
bkz. CLAUDE.md /parcels/bulk-update notu).
"""
import re
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
from pymongo.errors import BulkWriteError
from geo_validation import validate_geometry
from geo_import import _close_linestring_to_polygon
from platform_core import check_and_consume_limit
from admin_areas import _clean_geometry


class ParcelCreate(BaseModel):
    """Yeni parsel oluşturma"""
    farmer_id: str
    name: str
    village: str
    region_id: str
    area_dekar: float
    # B6 (#7) — EKİLEBİLİR alan (dekar). Parselin toplam alanı ≠ ekilebilir alanı
    # (yol/dere/kayalık düşülür). Sözleşme kota→alan kuralı BUNU baz alır; boşsa
    # kural toplam area_dekar'a düşer (bkz. data_entry.py create_contract).
    ekilebilir_alan_dekar: Optional[float] = None
    soil_type: str
    irrigation: str
    geometry: Optional[Dict[str, Any]] = None               # GeoJSON Polygon

    # ============ IT-02 — Form Yönetimi ile eşleşen ek alanlar ============
    # Ekranda zorunlu/görünür/sıra/lookup davranışı field_definitions
    # (module="parcels") tarafından yönetilir; burada sadece gerçek,
    # tipli DB kolonları olarak tanımlanırlar (Sprint A1 kuralı).

    # --- Kadastro Bilgileri ---
    ada_no: Optional[str] = None
    parsel_no_tapu: Optional[str] = None                     # Tapudaki parsel no (parcel_code ile karıştırılmamalı)
    il: Optional[str] = None                                  # lookup: il
    ilce: Optional[str] = None                                # lookup: ilce (parent_id ile il'e bağlı)
    mahalle: Optional[str] = None                              # Mahalle/Köy — düz metin (Sprint A1 kuralı: national veri seti yok)

    # --- Coğrafi Özellikler ---
    rakim_m: Optional[int] = None                             # Rakım (metre)
    egim_yuzde: Optional[float] = None                        # Eğim (%)

    # --- Sahiplik & Kira ---
    sahiplik_durumu: Optional[str] = None                     # lookup: sahiplik_durumu
    tapu_no: Optional[str] = None
    kira_sozlesmesi_var_mi: Optional[bool] = None
    kira_baslangic: Optional[str] = None                       # YYYY-MM-DD
    kira_bitis: Optional[str] = None                           # YYYY-MM-DD
    kiraci_adi: Optional[str] = None

    # --- Altyapı ---
    yol_durumu: Optional[str] = None                           # lookup: yol_durumu
    elektrik_baglantisi: Optional[bool] = None
    su_kaynagi: Optional[str] = None                           # lookup: su_kaynagi
    sondaj_kuyu_derinligi_m: Optional[float] = None




def register_parcel_routes(api_router, db, current_user, require_permission, require_feature, require_min_role, is_admin, log_audit):
    @api_router.get("/parcels")
    async def list_parcels(
        region_id: Optional[str] = None,
        farmer_id: Optional[str] = None,
        limit: int = 500,
        user=Depends(require_permission("parcels:view")),
        _feature=Depends(require_feature("parcel")),
    ):
        """Parsel listesi (filtreli)"""
        # BULGU 1 düzeltmesi: soft-delete edilmiş (is_active=False) parseller
        # listede gösterilmez.
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}
        if region_id: filt["region_id"] = region_id
        if farmer_id: filt["farmer_id"] = farmer_id
        docs = await db.parcels.find(filt, {"_id": 0}).limit(limit).to_list(limit)
        return docs


    # SON HAL — Parseller sayfasının sabit lookup filtre çubuğu için DB'deki
    # GERÇEK distinct değerler. DİKKAT: /parcels/{parcel_id}'den ÖNCE tanımlı
    # olmalı — aksi halde Starlette "filter-options"ı bir parcel_id sanır
    # (bkz. CLAUDE.md'nin /parcels/bulk-update route-sırası tuzağı).
    @api_router.get("/parcels/filter-options")
    async def parcel_filter_options(user=Depends(require_permission("parcels:view")),
                                     _feature=Depends(require_feature("parcel"))):
        base = {"is_active": {"$ne": False}}

        async def _distinct(field):
            vals = await db.parcels.distinct(field, base)
            return sorted(str(v) for v in vals if v not in (None, ""))

        il_list = await _distinct("il")
        ilce_list = await _distinct("ilce")
        mahalle_vals = set(await _distinct("mahalle")) | set(await _distinct("village"))
        ada_list = await _distinct("ada_no")
        ekim_list = await _distinct("ekim_durumu")

        # il→ilçe→mahalle kaskadı için hafif eşleme (sadece dolu alanlar)
        pairs = await db.parcels.find(
            base, {"_id": 0, "il": 1, "ilce": 1, "mahalle": 1, "village": 1}).to_list(20000)
        ilce_by_il, mahalle_by_ilce = {}, {}
        for p in pairs:
            il, ilce = p.get("il"), p.get("ilce")
            mah = p.get("mahalle") or p.get("village")
            if il and ilce:
                ilce_by_il.setdefault(il, set()).add(ilce)
            if ilce and mah:
                mahalle_by_ilce.setdefault(ilce, set()).add(mah)

        areas = [float(p["area_dekar"]) async for p in
                 db.parcels.find(base, {"_id": 0, "area_dekar": 1})
                 if p.get("area_dekar") is not None]

        return {
            "il": il_list,
            "ilce": ilce_list,
            "mahalle": sorted(mahalle_vals),
            "ada": ada_list,
            "ekim_durumu": ekim_list,
            "ilce_by_il": {k: sorted(v) for k, v in ilce_by_il.items()},
            "mahalle_by_ilce": {k: sorted(v) for k, v in mahalle_by_ilce.items()},
            "area_min": round(min(areas), 1) if areas else 0,
            "area_max": round(max(areas), 1) if areas else 0,
        }


    @api_router.get("/parcels/{parcel_id}")
    async def get_parcel_detail(parcel_id: str, user=Depends(require_permission("parcels:view")),
                                 _feature=Depends(require_feature("parcel"))):
        """
        Parsel detay sayfası:
        - Parsel bilgisi (harita, alan, toprak)
        - Sahip çiftçi
        - Bu parselin ekim geçmişi
        - Toprak analizleri
        - Sulama olayları
        - Verim kayıtları
        - Yapılan görevler
        """
        p = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not p:
            raise HTTPException(404, "Parsel bulunamadı")
    
        farmer = await db.farmers.find_one({"id": p["farmer_id"]}, {"_id": 0})
        # 2026-08-20 — is_active filtresi: çiftçinin mobilden gönderip henüz
        # personel onaylamadığı ekim kayıtları (review_status="beklemede",
        # is_active=False) burada da "resmi" gibi görünmesin.
        plantings = await db.plantings.find(
            {"parcel_id": parcel_id, "is_active": {"$ne": False}}, {"_id": 0}
        ).sort([("season", -1)]).to_list(50)
        soil = await db.soil_samples.find(
            {"parcel_id": parcel_id}, {"_id": 0}
        ).sort([("date", -1)]).to_list(20)
        irrigation = await db.irrigation_events.find(
            {"parcel_id": parcel_id}, {"_id": 0}
        ).sort([("date", -1)]).to_list(100)
        yields = await db.yields.find(
            {"parcel_id": parcel_id}, {"_id": 0}
        ).sort([("season", -1)]).to_list(20)
        tasks = await db.tasks.find(
            {"parcel_id": parcel_id}, {"_id": 0}
        ).sort([("scheduled_date", -1)]).to_list(50)
        iot_sensors = await db.iot_sensors.find(
            {"parcel_id": parcel_id}, {"_id": 0}
        ).to_list(20)
        drone_missions = await db.drone_missions.find(
            {"parcel_id": parcel_id}, {"_id": 0}
        ).sort([("flight_date", -1)]).to_list(20)

        # #6 — SORUMLU (portföy): köy adından MİRAS alınır (isimle eşleştirme).
        from admin_areas import resolve_responsible
        responsible = await resolve_responsible(db, p.get("village") or p.get("mahalle"))

        # SON HAL — parsel↔sözleşme çapraz navigasyonu: parselin sözleşmeleri
        # da detay yanıtına eklendi (ContractDetail /sozlesmeler/:id'ye link verilir).
        contracts = await db.contracts.find(
            {"parcel_id": parcel_id, "is_active": {"$ne": False}}, {"_id": 0}
        ).sort([("season", -1)]).to_list(50)

        return {
            "parcel": p,
            "farmer": farmer,
            "responsible": responsible,
            "contracts": contracts,
            "plantings": plantings,
            "soil_samples": soil,
            "irrigation_events": irrigation,
            "yields": yields,
            "tasks": tasks,
            "iot_sensors": iot_sensors,
            "drone_missions": drone_missions,
        }


    @api_router.post("/parcels")
    async def create_parcel(body: ParcelCreate, request: Request, user=Depends(current_user),
                             _feature=Depends(require_feature("parcel"))):
        """Yeni parsel oluştur (manuel form veya harita çizim aracıyla)"""
        if not is_admin(user):
            raise HTTPException(403, "Yetkiniz yok")

        # Denetim (2026-07-24): topoloji doğrulaması — self-intersecting çizim
        # coğrafi sorguları ve NDVI analizlerini bozuyordu (bkz. geo_validation.py).
        geo_errors = validate_geometry(body.model_dump().get("geometry"))
        if geo_errors:
            raise HTTPException(400, geo_errors[0])

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())

        count = await db.parcels.count_documents({})
        await check_and_consume_limit(db, user.get("tenant_id"), "parcel_limit", count, "Parsel")
        doc["parcel_code"] = f"PRS-{(count+1):05d}"
        doc["current_crop"] = "Şeker Pancarı"
        doc["active_season"] = datetime.now().year
        # Yeni çizilen/oluşturulan parselde henüz uydu verisi yok — dashboard
        # KPI'larının (risky_parcels, avg_ndvi) bu parseli de sayabilmesi için
        # nötr bir varsayılan atanıyor (import-geojson ile aynı mantık).
        doc.setdefault("ndvi_latest", 0.65)
        doc.setdefault("risk_level", "sari")
        doc.setdefault("risk_label", "İzlemeye Değer (henüz uydu taraması yok)")
        doc.setdefault("expected_yield_ton", round(body.area_dekar * 5.5, 1))
        doc.setdefault("last_satellite_scan", None)
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
    
        await db.parcels.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="parcel", entity_id=doc["id"], new_value=doc, request=request)
        return doc


    class ParcelUpdate(BaseModel):
        """Parsel bilgi güncelleme — harita çizim aracı da bu endpoint'i kullanacak"""
        farmer_id: Optional[str] = None                          # sonradan çiftçi atama (atanmamış import edilen parseller için)
        name: Optional[str] = None
        village: Optional[str] = None
        area_dekar: Optional[float] = None
        ekilebilir_alan_dekar: Optional[float] = None            # B6 (#7) — ekilebilir alan
        soil_type: Optional[str] = None
        irrigation: Optional[str] = None
        current_crop: Optional[str] = None
        geometry: Optional[Dict[str, Any]] = None               # GeoJSON Polygon (harita düzenlemesi)
        risk_level: Optional[str] = None                        # yesil|sari|turuncu|kirmizi (manuel override)
        ndvi_latest: Optional[float] = None

        # ============ IT-02 — ek alanlar (bkz. ParcelCreate) ============
        # --- Kadastro Bilgileri ---
        ada_no: Optional[str] = None
        parsel_no_tapu: Optional[str] = None
        il: Optional[str] = None
        ilce: Optional[str] = None
        mahalle: Optional[str] = None
        # --- Coğrafi Özellikler ---
        rakim_m: Optional[int] = None
        egim_yuzde: Optional[float] = None
        # --- Sahiplik & Kira ---
        sahiplik_durumu: Optional[str] = None
        tapu_no: Optional[str] = None
        kira_sozlesmesi_var_mi: Optional[bool] = None
        kira_baslangic: Optional[str] = None
        kira_bitis: Optional[str] = None
        kiraci_adi: Optional[str] = None
        # --- Altyapı ---
        yol_durumu: Optional[str] = None
        elektrik_baglantisi: Optional[bool] = None
        su_kaynagi: Optional[str] = None
        sondaj_kuyu_derinligi_m: Optional[float] = None


    class ParcelBulkUpdateFields(BaseModel):
        """IT-15 — toplu işlemde anlamlı olan alt küme (isim/alan/geometri gibi parsele özgü alanlar kasıtlı olarak YOK)"""
        soil_type: Optional[str] = None
        irrigation: Optional[str] = None
        risk_level: Optional[str] = None
        current_crop: Optional[str] = None


    class ParcelBulkUpdateRequest(BaseModel):
        parcel_ids: List[str]
        updates: ParcelBulkUpdateFields


    @api_router.put("/parcels/bulk-update")
    async def bulk_update_parcels(body: ParcelBulkUpdateRequest, request: Request,
                                   user=Depends(require_permission("parcels:edit")),
                                   _feature=Depends(require_feature("parcel"))):
        """
        IT-15 — çoklu parsel toplu işlem (haritada şekille/tıklayarak seçilen parseller).
        update_parcel ile AYNI iş mantığı (risk_level->risk_label senkronu dahil), sadece
        N parsel için tek istekte toplanmış hali. Her parsel için AYRI log_audit çağrılır
        (convention #6 — tek bir "bulk" audit kaydı old/new'i anlamsızlaştırırdı).
        Bu route parcel_id path parametresini yakalayan `/parcels/{parcel_id}` PUT'undan
        ÖNCE tanımlı olmalı, yoksa Starlette "bulk-update"i bir parcel_id sanıp oraya yönlendirir.
        """
        if not body.parcel_ids:
            raise HTTPException(400, "Parsel seçilmedi")
        updates = {k: v for k, v in body.updates.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")

        if "risk_level" in updates:
            risk_labels = {
                "yesil": "Düşük Risk", "sari": "İzlemeye Değer",
                "turuncu": "Riskli", "kirmizi": "Acil Müdahale"
            }
            updates["risk_label"] = risk_labels.get(updates["risk_level"], updates["risk_level"])

        updated_count = 0
        for pid in body.parcel_ids:
            old = await db.parcels.find_one({"id": pid}, {"_id": 0})
            if not old:
                continue
            await db.parcels.update_one({"id": pid}, {"$set": updates})
            new = await db.parcels.find_one({"id": pid}, {"_id": 0})
            await log_audit(db, user, action="update", entity="parcel", entity_id=pid, old_value=old, new_value=new, request=request)
            updated_count += 1
        return {"updated_count": updated_count, "requested_count": len(body.parcel_ids)}


    class ParcelSelectByGeometryRequest(BaseModel):
        """Denetim STAB-B3 (2026-07-24) — haritada çizilen şeklin GeoJSON geometrisi."""
        geometry: Dict[str, Any]


    @api_router.post("/parcels/select-by-geometry")
    async def select_parcels_by_geometry(body: ParcelSelectByGeometryRequest,
                                          user=Depends(require_permission("parcels:view")),
                                          _feature=Depends(require_feature("parcel"))):
        """
        Denetim STAB-B3: "Şekille Seç" kesişim hesabı eskiden tarayıcıda Turf.js
        ile yapılıyordu — 1000+ parselde donma. Artık MongoDB $geoIntersects
        (2dsphere index, startup'ta mevcut) ile sunucuda hesaplanır; yanıt sadece
        id listesidir, frontend bunu kendi filtre kümesiyle kesiştirir.
        Bu route da `/parcels/{parcel_id}`'den ÖNCE tanımlı olmalı (route sırası
        tuzağı — bkz. bulk-update notu).
        """
        geom = body.geometry or {}
        if geom.get("type") not in ("Polygon", "MultiPolygon"):
            raise HTTPException(400, "Seçim geometrisi Polygon/MultiPolygon olmalı")
        try:
            parcels = await db.parcels.find(
                {"is_active": {"$ne": False},
                 "geometry": {"$geoIntersects": {"$geometry": geom}}},
                {"_id": 0, "id": 1},
            ).to_list(10000)
        except Exception:
            raise HTTPException(400, "Geometri sorgusu çalıştırılamadı — çizilen şekil geçersiz olabilir")
        return {"parcel_ids": [p["id"] for p in parcels], "count": len(parcels)}


    class ParcelBulkDeleteRequest(BaseModel):
        parcel_ids: List[str]


    @api_router.post("/parcels/bulk-delete")
    async def bulk_delete_parcels(body: ParcelBulkDeleteRequest, request: Request,
                                  user=Depends(require_min_role("fabrika_muduru")),
                                  _feature=Depends(require_feature("parcel"))):
        """
        Çoklu parsel toplu SOFT-delete (#3). Bağlı AKTİF sözleşmesi olan parseller
        silinmez — atlanıp raporlanır (tekil DELETE'in 409 guard'ı ile AYNI kural).
        Her gerçekten silinen parsel için ayrı log_audit (convention #6).
        """
        if not body.parcel_ids:
            raise HTTPException(400, "Parsel seçilmedi")
        deleted, skipped = [], []
        for pid in body.parcel_ids:
            old = await db.parcels.find_one({"id": pid}, {"_id": 0})
            if not old:
                continue
            linked = await db.contracts.count_documents({"parcel_id": pid, "is_active": {"$ne": False}})
            if linked > 0:
                skipped.append({"id": pid, "name": old.get("name") or old.get("parcel_code"),
                                "reason": f"{linked} bağlı sözleşme"})
                continue
            await db.parcels.update_one({"id": pid}, {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }})
            await log_audit(db, user, action="soft_delete", entity="parcel", entity_id=pid, old_value=old, request=request)
            deleted.append(pid)
        return {"deleted_count": len(deleted), "skipped": skipped, "requested_count": len(body.parcel_ids)}


    @api_router.put("/parcels/{parcel_id}")
    async def update_parcel(parcel_id: str, body: ParcelUpdate, request: Request,
                             user=Depends(require_permission("parcels:edit")),
                             _feature=Depends(require_feature("parcel"))):
        """Parsel bilgilerini günceller (harita üzerinden geometri düzenleme dahil; IT-04: granüler parcels:edit izni)"""
        old = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Parsel bulunamadı")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")

        # Denetim (2026-07-24): geometri güncelleniyorsa topoloji doğrulaması
        if "geometry" in updates:
            geo_errors = validate_geometry(updates["geometry"])
            if geo_errors:
                raise HTTPException(400, geo_errors[0])

        # Çiftçi atanıyor/değiştiriliyorsa region_id'yi o çiftçiden türet (bölge
        # bazlı sorgular tutarlı kalsın) + parselin köyü boşsa çiftçinin köyünü ata.
        if updates.get("farmer_id"):
            farmer = await db.farmers.find_one({"id": updates["farmer_id"]}, {"_id": 0})
            if not farmer:
                raise HTTPException(400, "Seçilen çiftçi bulunamadı")
            updates["region_id"] = farmer.get("region_id")
            if not old.get("village") and not updates.get("village"):
                updates["village"] = farmer.get("village", "")

        # risk_level manuel değiştirildiyse etiketini de eşitle (tutarlılık için)
        if "risk_level" in updates:
            risk_labels = {
                "yesil": "Düşük Risk", "sari": "İzlemeye Değer",
                "turuncu": "Riskli", "kirmizi": "Acil Müdahale"
            }
            updates["risk_label"] = risk_labels.get(updates["risk_level"], updates["risk_level"])

        await db.parcels.update_one({"id": parcel_id}, {"$set": updates})
        new = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="parcel", entity_id=parcel_id, old_value=old, new_value=new, request=request)
        return new


    @api_router.delete("/parcels/{parcel_id}")
    async def delete_parcel(parcel_id: str, request: Request, user=Depends(require_min_role("fabrika_muduru")),
                             _feature=Depends(require_feature("parcel"))):
        """
        Parseli siler. Bağlı sözleşme/ekim/verim kaydı varsa engellenir —
        veri bütünlüğü için önce o kayıtların kapatılması/taşınması gerekir.
        """
        old = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Parsel bulunamadı")

        linked_contracts = await db.contracts.count_documents(
            {"parcel_id": parcel_id, "is_active": {"$ne": False}}
        )
        if linked_contracts > 0:
            raise HTTPException(
                409,
                f"Bu parsele bağlı {linked_contracts} sözleşme var. Önce sözleşmeleri "
                "kapatın/taşıyın, sonra parseli silin."
            )

        # BULGU 1 (Kritik) düzeltmesi: hard-delete -> soft-delete. Parsel geçmişi
        # (geometri, ekim/verim ilişkisi) korunur; sadece görünürlük kapanır.
        await db.parcels.update_one(
            {"id": parcel_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }},
        )
        await log_audit(db, user, action="soft_delete", entity="parcel", entity_id=parcel_id, old_value=old, request=request)
        return {"status": "deactivated"}


    class ParcelSplitRequest(BaseModel):
        """Bir parseli iki (veya daha fazla) yeni parsele böler — harita çizim aracı kullanır"""
        new_geometries: list[Dict[str, Any]]              # Her biri bağımsız bir GeoJSON Polygon
        new_areas_dekar: list[float]                       # new_geometries ile aynı sırada alan (dekar)
        new_names: Optional[list[str]] = None              # Her parça için ayrı isim (verilmezse otomatik "(Parça N)" eklenir)


    @api_router.post("/parcels/{parcel_id}/split")
    async def split_parcel(parcel_id: str, body: ParcelSplitRequest, request: Request,
                            user=Depends(require_min_role("ziraat_muhendisi")),
                            _feature=Depends(require_feature("parcel"))):
        """
        Parseli böler: orijinal parsel silinir (veya arşivlenir), yerine
        verilen geometrilerle N yeni parsel oluşturulur. Sözleşme/ekim geçmişi
        orijinal parsel siliniyorsa kaybolacağından, bağlı kayıt varsa engellenir.

        Yeni parseller varsayılan olarak orijinalin adını + "(Parça N)" ekiyle
        alır (new_names verilmezse) — böylece liste görünümünde birbirinden
        ayırt edilebilirler; öncesinde ikisi de orijinalle AYNI isme sahip
        olduğundan "yeni parsel oluşmamış" gibi görünüyordu, bu düzeltildi.
        """
        if len(body.new_geometries) < 2:
            raise HTTPException(400, "Bölme için en az 2 yeni geometri gerekli")
        if len(body.new_geometries) != len(body.new_areas_dekar):
            raise HTTPException(400, "new_geometries ve new_areas_dekar sayıları eşleşmeli")
        # Denetim (2026-07-24): bölme parçalarında topoloji doğrulaması
        for i, geom in enumerate(body.new_geometries):
            geo_errors = validate_geometry(geom)
            if geo_errors:
                raise HTTPException(400, f"Parça {i + 1}: {geo_errors[0]}")
        if body.new_names and len(body.new_names) != len(body.new_geometries):
            raise HTTPException(400, "new_names verildiyse new_geometries ile aynı sayıda olmalı")

        old = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Parsel bulunamadı")

        linked_contracts = await db.contracts.count_documents(
            {"parcel_id": parcel_id, "is_active": {"$ne": False}}
        )
        if linked_contracts > 0:
            raise HTTPException(409, "Bu parsele bağlı sözleşme var, bölünmeden önce kapatılmalı")

        count = await db.parcels.count_documents({})
        new_parcels = []
        for i, (geom, area) in enumerate(zip(body.new_geometries, body.new_areas_dekar)):
            piece_name = (body.new_names[i] if body.new_names else f"{old['name']} (Parça {i+1})")
            new_parcels.append({
                **{k: v for k, v in old.items() if k not in ("id", "parcel_code", "geometry", "area_dekar", "name")},
                "id": str(uuid.uuid4()),
                "parcel_code": f"PRS-{(count + i + 1):05d}",
                "name": piece_name,
                "geometry": geom,
                "area_dekar": area,
                "split_from": parcel_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        await db.parcels.insert_many(new_parcels)
        # BULGU 1 düzeltmesi: orijinal parsel fiziksel silinmez; is_active=False +
        # split_to ile arşivlenir (böl/birleştir izi ve eski geometri korunur).
        await db.parcels.update_one(
            {"id": parcel_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
                "split_to": [p["id"] for p in new_parcels],
            }},
        )

        for p in new_parcels:
            p.pop("_id", None)
        # Tam eski/yeni karşılaştırması için new_value'ya sadece ID değil,
        # oluşturulan parsellerin TAMAMI (isim, alan, geometri) yazılıyor —
        # "kim ne zaman neyi neye böldü" audit log'dan net okunabilsin diye.
        await log_audit(db, user, action="split", entity="parcel", entity_id=parcel_id,
                         old_value=old, new_value={"new_parcels": new_parcels}, request=request)
        return {"status": "split", "new_parcels": new_parcels}


    class ParcelMergeRequest(BaseModel):
        """Birden fazla parseli tek parselde birleştirir — harita çizim aracı kullanır"""
        parcel_ids: list[str]                              # Birleştirilecek parseller (2+)
        merged_geometry: Dict[str, Any]                     # Birleşik alanın GeoJSON Polygon'u


    @api_router.post("/parcels/merge")
    async def merge_parcels(body: ParcelMergeRequest, request: Request,
                             user=Depends(require_min_role("ziraat_muhendisi")),
                             _feature=Depends(require_feature("parcel"))):
        """
        Birden fazla parseli tek parselde birleştirir. Birleştirilecek
        parsellerin AYNI ÇİFTÇİYE ait olması zorunludur (farklı çiftçilerin
        parselleri birleştirilemez — mülkiyet karışıklığı olur).
        """
        if len(body.parcel_ids) < 2:
            raise HTTPException(400, "Birleştirme için en az 2 parsel gerekli")

        parcels_to_merge = await db.parcels.find({"id": {"$in": body.parcel_ids}}, {"_id": 0}).to_list(len(body.parcel_ids))
        if len(parcels_to_merge) != len(body.parcel_ids):
            raise HTTPException(404, "Bazı parseller bulunamadı")

        farmer_ids = {p["farmer_id"] for p in parcels_to_merge}
        if len(farmer_ids) > 1:
            raise HTTPException(409, "Farklı çiftçilere ait parseller birleştirilemez")

        for p in parcels_to_merge:
            linked = await db.contracts.count_documents(
                {"parcel_id": p["id"], "is_active": {"$ne": False}}
            )
            if linked > 0:
                raise HTTPException(409, f"{p['parcel_code']} parseline bağlı sözleşme var, önce kapatılmalı")

        total_area = sum(p["area_dekar"] for p in parcels_to_merge)
        base = parcels_to_merge[0]
        count = await db.parcels.count_documents({})
        merged = {
            **{k: v for k, v in base.items() if k not in ("id", "parcel_code", "geometry", "area_dekar")},
            "id": str(uuid.uuid4()),
            "parcel_code": f"PRS-{(count + 1):05d}",
            "geometry": body.merged_geometry,
            "area_dekar": round(total_area, 1),
            "merged_from": body.parcel_ids,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.parcels.insert_one(merged)
        # BULGU 1 düzeltmesi: birleştirilen parseller fiziksel silinmez; is_active=
        # False + merged_to ile arşivlenir (eski geometri ve birleştirme izi kalır).
        await db.parcels.update_many(
            {"id": {"$in": body.parcel_ids}},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
                "merged_to": merged["id"],
            }},
        )
        merged.pop("_id", None)

        await log_audit(db, user, action="merge", entity="parcel", entity_id=merged["id"],
                         old_value={"merged_parcels": parcels_to_merge}, new_value=merged, request=request)
        return {"status": "merged", "parcel": merged}


    class GeoJSONImportRequest(BaseModel):
        """Toplu parsel import — GeoJSON FeatureCollection kabul eder"""
        geojson: Dict[str, Any]
        farmer_id: Optional[str] = None                     # Verilmezse her feature.properties.farmer_id kullanılır
        default_soil_type: str = "Tınlı"
        default_irrigation: str = "Damla"


    @api_router.post("/parcels/import-geojson")
    async def import_parcels_geojson(body: GeoJSONImportRequest, request: Request,
                                      user=Depends(require_min_role("ziraat_muhendisi")),
                                      _feature=Depends(require_feature("parcel"))):
        """
        GeoJSON FeatureCollection'dan toplu parsel oluşturur. Her feature'ın
        geometry'si Polygon olmalı. properties içinde farmer_id/name/village
        varsa kullanılır, yoksa body.farmer_id / varsayılanlar kullanılır.

        Alan (dekar), geometrinin enlem/boylamından basit bir düzlemsel
        (shoelace) yaklaşıklıkla hesaplanır — kadastral hassasiyet gerektiren
        durumlarda gerçek bir GIS kütüphanesiyle (örn. shapely) yeniden
        hesaplanması önerilir.
        """
        features = body.geojson.get("features", [])
        if not features:
            raise HTTPException(400, "GeoJSON içinde 'features' bulunamadı")

        def _shoelace_area_dekar(coords) -> float:
            """
            Basit düzlemsel alan yaklaşıklığı (shoelace formülü).
            NOT: Enlem/boylam derecelerini düz kabul eder — kutuplara yakın
            ya da çok büyük parsellerde hata payı artar. Kadastral hassasiyet
            gerekiyorsa shapely + pyproj ile gerçek projeksiyonlu hesaplama
            yapılmalı. Küçük tarla ölçeğinde (<1000 dekar) yeterince yakındır.
            """
            ring = coords[0]
            area_deg2 = 0.0
            for i in range(len(ring) - 1):
                # Koordinat 3B olabilir ([lng,lat,alt]) — sadece ilk iki bileşeni al.
                x1, y1 = ring[i][0], ring[i][1]
                x2, y2 = ring[i + 1][0], ring[i + 1][1]
                area_deg2 += x1 * y2 - x2 * y1
            area_deg2 = abs(area_deg2) / 2.0
            # 1° ≈ 111 km → 1 derece² ≈ 111² km² = 12321 km²
            # 1 km² = 1000 dekar (1 dekar = 1000 m²)
            km2 = area_deg2 * (111 ** 2)
            return round(km2 * 1000, 1)

        def _to_2d_coords(coords):
            """GeoJSON koordinatlarındaki 3. boyutu (yükseklik) atar:
            [lng,lat,alt] -> [lng,lat]. Google Earth/KML kaynaklı dosyalar
            genelde 3B gelir; 3B koordinat hem alan hesabını hem MongoDB
            2dsphere index'ini bozabildiği için içe aktarmada 2B'ye indirilir."""
            if coords and isinstance(coords[0], (int, float)):
                return [coords[0], coords[1]]
            return [_to_2d_coords(c) for c in coords]

        def _extract_tkgm_fields(props: dict) -> dict:
            """
            IT-16 — TKGM (Tapu ve Kadastro Genel Müdürlüğü) kamuya açık "Parsel
            Sorgu" haritasından (parselsorgu.tkgm.gov.tr) dışa aktarılan GeoJSON
            özellik adlarını (il/ilce/mahalle/ada/parsel) IT-02'nin ParcelCreate
            alanlarına eşler. Resmi bir API/anahtar GEREKMEZ — kullanıcı bu genel
            haritadan manuel export/kopyala-yapıştır yapar; MERNİS/TAKBİS gibi
            resmi API entegrasyonlarından FARKLI (bkz. ROADMAP "Yapılabilirlik
            Değerlendirmesi", bunlar ⏸ ertelendi). Anahtar adları normalize
            edilip birkaç yaygın varyasyon tek bir alana eşlenir; hiçbiri
            bulunamazsa boş sözlük döner (mevcut davranış DEĞİŞMEZ).
            """
            norm = {str(k).strip().lower(): v for k, v in props.items()}

            def pick(*keys):
                for k in keys:
                    v = norm.get(k)
                    if v not in (None, ""):
                        return v
                return None

            out = {}
            il = pick("il", "il_adi", "il_ad")
            ilce = pick("ilce", "ilce_adi", "ilce_ad")
            mahalle = pick("mahalle", "mahalle_adi", "mahalle_ad", "koy", "koy_adi")
            ada = pick("ada_no", "ada", "adano")
            parsel = pick("parsel_no_tapu", "parsel", "parselno", "pin")
            # 2026-08-20 — bazı kaynaklar (köy sınır dosyaları) ada/parseli AYRI
            # alanlar yerine TEK bir "Name"/"name" özelliğinde "101/10" (ada/
            # parsel) formatında verir — TKGM Parsel Sorgu'nun kendi kadastro
            # gösterim biçimi. ada/parsel AYRI alanlardan zaten bulunduysa buna
            # DOKUNULMAZ (mevcut, daha spesifik alanlar önceliklidir).
            if ada is None and parsel is None:
                combined = pick("name", "isim", "ad")
                if combined and re.fullmatch(r"\d+/\d+", str(combined).strip()):
                    ada, parsel = str(combined).strip().split("/")
            if il is not None:
                out["il"] = str(il)
            if ilce is not None:
                out["ilce"] = str(ilce)
            if mahalle is not None:
                out["mahalle"] = str(mahalle)
            if ada is not None:
                out["ada_no"] = str(ada)
            if parsel is not None:
                out["parsel_no_tapu"] = str(parsel)
            return out

        count = await db.parcels.count_documents({})
        created = []
        errors = []
        for i, feat in enumerate(features):
            try:
                geom = feat.get("geometry")
                props = feat.get("properties", {}) or {}
                # 2026-08-20 — bazı kaynaklar (TKGM Parsel Sorgu dahil, bkz.
                # köy sınır dosyaları) parsel poligonunu Polygon YERİNE kapalı
                # bir LineString olarak yazar; `geo_import.py` ile AYNI ilkeyle
                # (ilk/son nokta eşitse) Polygon'a çevrilir — açık bir çizgiyse
                # (yol/kanal) dokunulmaz, aşağıdaki "Parsel değil" kontrolü onu
                # yine reddeder.
                if geom:
                    geom = _close_linestring_to_polygon(geom)
                if not geom or geom.get("type") != "Polygon":
                    gtype = (geom or {}).get("type") or "geometri yok"
                    # Nokta/çizgi bir parsel OLAMAZ (alanı yok) — kullanıcı KML/GeoJSON
                    # export'unda parsellerin yanında etiket (Point) / sınır çizgisi
                    # (LineString) da olabilir; bunlar sessizce değil, AÇIK nedenle atlanır.
                    errors.append({"index": i, "error": f"Parsel değil ({gtype}) — sadece Polygon içe aktarılır"})
                    continue

                # 3B koordinatları (yükseklik) 2B'ye indir — hem alan hesabı hem
                # 2dsphere index için gerekli (Google Earth/KML dosyaları 3B gelir).
                geom = {"type": "Polygon", "coordinates": _to_2d_coords(geom["coordinates"])}
                # 2026-08-20 — admin_areas.py'de 2026-07-25'te bulunan AYNI veri
                # kalitesi sorunu (bitişik yinelenen köşe noktaları, ör. TUİK/köy
                # sınır dosyalarında sık rastlanır) burada da görüldü: MongoDB'nin
                # 2dsphere indeksi "Loop is not valid ... Duplicate vertices" ile
                # reddediyordu. AYNI `_clean_geometry` (admin_areas.py) yeniden
                # kullanılarak köklendi.
                geom = _clean_geometry(geom)

                # Denetim (2026-07-24): topoloji doğrulaması — bozuk (self-intersecting)
                # geometri sessizce içeri alınmaz, hatalar listesinde raporlanır.
                geo_errors = validate_geometry(geom)
                if geo_errors:
                    errors.append({"index": i, "error": geo_errors[0]})
                    continue

                # Çiftçi ARTIK OPSİYONEL — dosyada veya istekte farmer_id yoksa parsel
                # "atanmamış" olarak oluşturulur; kullanıcı sonra parselden çiftçi atar.
                farmer_id = props.get("farmer_id") or body.farmer_id
                farmer = None
                if farmer_id:
                    farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
                    if not farmer:
                        # Anahtar verilmiş ama geçersiz -> bu bir hatadır (sessizce atanmamış yapma).
                        errors.append({"index": i, "error": f"Çiftçi bulunamadı: {farmer_id}"})
                        continue

                # IT-16 — TKGM export'u alanı genelde "alan"/"yuzolcum" adıyla
                # ve m² cinsinden verir (area_dekar YOK) — bu durumda dekara çevrilir.
                area = props.get("area_dekar")
                if area is None:
                    alan_m2 = props.get("alan") or props.get("yuzolcum")
                    if alan_m2 is not None:
                        try:
                            area = round(float(alan_m2) / 1000, 1)
                        except (TypeError, ValueError):
                            area = None
                if area is None:
                    area = _shoelace_area_dekar(geom["coordinates"])

                tkgm_fields = _extract_tkgm_fields(props)

                # Yeni import edilen parsellerde henüz uydu/AI verisi yok —
                # "veri yok" yerine nötr bir varsayılan atanıyor ki dashboard
                # KPI'ları (risky_parcels, avg_ndvi) bu parselleri de sayabilsin.
                # İlk gerçek uydu taraması geldiğinde bu değer güncellenecek.
                default_ndvi = 0.65
                default_name = f"İçe Aktarılan Parsel {i+1}"
                if "ada_no" in tkgm_fields or "parsel_no_tapu" in tkgm_fields:
                    default_name = f"Ada {tkgm_fields.get('ada_no', '?')} Parsel {tkgm_fields.get('parsel_no_tapu', '?')}"
                doc = {
                    "id": str(uuid.uuid4()),
                    "parcel_code": f"PRS-{(count + len(created) + 1):05d}",
                    "name": props.get("name", default_name),
                    "farmer_id": farmer_id,                       # None ise "atanmamış"
                    "village": props.get("village", (farmer.get("village", "") if farmer else "")),
                    "region_id": (farmer["region_id"] if farmer else None),
                    "area_dekar": area,
                    "soil_type": props.get("soil_type", body.default_soil_type),
                    "irrigation": props.get("irrigation", body.default_irrigation),
                    "geometry": geom,
                    **tkgm_fields,
                    "current_crop": props.get("crop", "Şeker Pancarı"),
                    "active_season": datetime.now().year,
                    "ndvi_latest": default_ndvi,
                    "risk_level": "sari",
                    "risk_label": "İzlemeye Değer (henüz uydu taraması yok)",
                    "expected_yield_ton": round(area * 5.5, 1),
                    "last_satellite_scan": None,
                    "imported": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                created.append(doc)
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        # 2026-08-20 — admin_areas.py'nin bulk-import'undaki AYNI düzeltme
        # (bkz. yukarıdaki `_clean_geometry` notu): `_clean_geometry` çoğu
        # bitişik-köşe hatasını temizler ama BAŞKA geçersizlikler (self-
        # intersection vb.) hâlâ MongoDB 2dsphere indeksinde `BulkWriteError`
        # fırlatabilir. ESKİDEN varsayılan `ordered=True` bu durumda TÜM
        # isteği 500 ile çökertiyordu — o ana kadar başarıyla toplanmış
        # kayıtlar da yanıta hiç yansımadan (ama bazen DB'ye sessizce yazılmış
        # olarak) kayboluyordu. `ordered=False` ile geçerli TÜM kayıtlar
        # yazılır, sadece geçersiz olanlar `errors` listesine (index'iyle)
        # eklenir.
        if created:
            try:
                await db.parcels.insert_many(created, ordered=False)
            except BulkWriteError as e:
                failed_idx = {err["index"] for err in e.details.get("writeErrors", [])}
                surviving = []
                for idx, d in enumerate(created):
                    if idx in failed_idx:
                        errors.append({"index": None, "error": f"Geometri veritabanına yazılamadı: {d.get('name')}"})
                    else:
                        surviving.append(d)
                created = surviving
            for d in created:
                d.pop("_id", None)

        await log_audit(db, user, action="import", entity="parcel", entity_id=None,
                         new_value={"created_count": len(created), "error_count": len(errors)}, request=request)
        return {"created_count": len(created), "error_count": len(errors), "created": created, "errors": errors}



