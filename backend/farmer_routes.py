"""
=====================================================================
Toprax — Çiftçi Portalı (/farmer/*) + Çiftçi CRUD
=====================================================================
Denetim A6 (2026-07-24): server.py (~2900 satır) modülerleştirmesi —
bu dosyadaki endpoint'ler server.py'den BİREBİR taşındı, davranış
değişikliği YOK. Route kayıt SIRASI korunur: register çağrısı server.py
içinde bloğun orijinal konumundan yapılır (Starlette route-order tuzağı,
bkz. CLAUDE.md /parcels/bulk-update notu).
"""
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
from field_definitions import mask_sensitive_fields, mask_sensitive_fields_many, is_masked_value
from search_utils import safe_regex, TR_COLLATION


class FarmerCreate(BaseModel):
    """Yeni çiftçi oluşturma için body şeması"""
    full_name: str
    tc_no: str
    phone: str
    email: Optional[str] = None
    village: str
    region_id: str
    iban: Optional[str] = None
    notes: Optional[str] = None

    # ============ Sprint A1 — Form Yönetimi ile eşleşen ek alanlar ============
    # Bu alanların ekranda zorunlu/görünür/sıra/lookup davranışı
    # field_definitions (module="farmers") tarafından yönetilir; burada
    # sadece gerçek, tipli DB kolonları olarak tanımlanırlar.

    # --- Kimlik Bilgileri ---
    birth_date: Optional[str] = None                        # YYYY-MM-DD
    gender: Optional[str] = None                             # lookup: cinsiyet
    marital_status: Optional[str] = None                     # lookup: medeni_durum
    tax_no: Optional[str] = None                              # Vergi No (firma unvanlı çiftçiler için)

    # --- İletişim ---
    phone_alt: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None                                # İl
    district: Optional[str] = None                            # İlçe

    # --- Tarımsal Bilgiler ---
    cks_no: Optional[str] = None                               # ÇKS Kayıt No
    cks_status: Optional[str] = None                           # lookup: cks_durumu
    isletme_no: Optional[str] = None
    cooperative_member: Optional[bool] = None                  # Kooperatif Üyeliği
    chamber_member: Optional[bool] = None                      # Ziraat Odası Üyeliği
    producer_union: Optional[str] = None                       # Üretici Birliği

    # --- Finansal ---
    bank_name: Optional[str] = None
    support_payments_total: Optional[float] = None             # Destek Ödemeleri (toplam)
    debt_status: Optional[str] = None                           # lookup: borc_durumu
    debt_amount: Optional[float] = None

    # --- Operasyon ---
    last_visit_date: Optional[str] = None                       # Son Ziyaret
    responsible_personnel: Optional[str] = None                 # Sorumlu Personel
    risk_score: Optional[int] = None                            # Risk Skoru (AI)


class FarmerUpdate(BaseModel):
    """Çiftçi güncelleme — tüm alanlar opsiyonel"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    village: Optional[str] = None
    iban: Optional[str] = None
    notes: Optional[str] = None

    # --- Kimlik Bilgileri ---
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    tax_no: Optional[str] = None

    # --- İletişim ---
    phone_alt: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    # --- Tarımsal Bilgiler ---
    cks_no: Optional[str] = None
    cks_status: Optional[str] = None
    isletme_no: Optional[str] = None
    cooperative_member: Optional[bool] = None
    chamber_member: Optional[bool] = None
    producer_union: Optional[str] = None

    # --- Finansal ---
    bank_name: Optional[str] = None
    support_payments_total: Optional[float] = None
    debt_status: Optional[str] = None
    debt_amount: Optional[float] = None

    # --- Operasyon ---
    last_visit_date: Optional[str] = None
    responsible_personnel: Optional[str] = None
    risk_score: Optional[int] = None




class IrrigationEventCreate(BaseModel):
    """Çiftçi sulama olayı ekler — bu dashboard'u günceller!"""
    parcel_id: str
    date: str                                               # YYYY-MM-DD
    method: str                                             # damla/yağmurlama/karık
    water_m3: float
    moisture_before: Optional[int] = None
    moisture_after: Optional[int] = None


class SoilSampleCreate(BaseModel):
    """Toprak analizi sonucu ekleme"""
    parcel_id: str
    date: str
    lab_name: str
    ph: float
    ec: float
    organic_matter_pct: float
    n_ppm: int
    p_ppm: int
    k_ppm: int
    recommendation: Optional[str] = None




def register_farmer_routes(api_router, db, current_user, require_permission, require_feature, is_admin, log_audit):
    @api_router.get("/farmer/my-dashboard")
    async def my_dashboard(user=Depends(current_user)):
        """
        Çiftçinin kendi dashboard'u — sadece kendi verilerini görür.
    
        Çiftçi giriş yapınca burayı görür.
        Veri eklediğinde (sulama, vs.) bu sayfa anlık güncellenir.
        """
        # Çiftçi değilse veya farmer_id yoksa erişim engelle
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi hesapları erişebilir")
    
        farmer_id = user["farmer_id"]
    
        # Çiftçi bilgisi
        farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi profili bulunamadı")
    
        # Çiftçinin tüm parselleri
        parcels = await db.parcels.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
    
        # Aktif sözleşmeler
        contracts = await db.contracts.find(
            {"farmer_id": farmer_id, "season": 2025},
            {"_id": 0}
        ).to_list(50)
    
        # Verim geçmişi
        yields = await db.yields.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(50)
    
        # Sulama olayları (son 30 gün)
        irrigation_events = await db.irrigation_events.find(
            {"farmer_id": farmer_id},
            {"_id": 0}
        ).sort([("date", -1)]).to_list(50)
    
        # Toprak analizleri
        parcel_ids = [p["id"] for p in parcels]
        soil_samples = await db.soil_samples.find(
            {"parcel_id": {"$in": parcel_ids}},
            {"_id": 0}
        ).to_list(50)
    
        # Finansal hareketler
        finance = await db.finance.find(
            {"farmer_id": farmer_id},
            {"_id": 0}
        ).sort([("date", -1)]).to_list(50)
    
        # Toplam balance hesabı (gelir - gider)
        balance = sum(f.get("amount", 0) for f in finance)
    
        # Yaklaşan kantar randevuları
        appts = await db.appointments.find(
            {"farmer_id": farmer_id},
            {"_id": 0}
        ).sort([("scheduled_at", 1)]).to_list(20)
    
        # Toplam alan
        total_area = sum(p.get("area_dekar", 0) for p in parcels)
    
        # Bu yılın tahmini hasat
        expected_ton_2025 = sum(c.get("kota_ton", 0) for c in contracts)
    
        # Toplam su tüketimi (m³)
        total_water = sum(e.get("water_m3", 0) for e in irrigation_events)
    
        return {
            "farmer": farmer,
            "stats": {
                "parcels_count": len(parcels),
                "total_area_dekar": round(total_area, 1),
                "active_contracts": len(contracts),
                "expected_ton_2025": round(expected_ton_2025, 1),
                "total_water_m3": round(total_water, 1),
                "irrigation_events_count": len(irrigation_events),
                "balance": round(balance, 2),
                "soil_samples_count": len(soil_samples),
                "upcoming_appointments": len([a for a in appts if a.get("status") == "planlı"])
            },
            "parcels": parcels,
            "contracts": contracts,
            "yields": yields,
            "irrigation_events": irrigation_events[:10],         # Son 10
            "soil_samples": soil_samples[:10],
            "finance": finance[:10],
            "appointments": appts
        }


    @api_router.post("/farmer/irrigation")
    async def add_irrigation(body: IrrigationEventCreate, request: Request, user=Depends(current_user)):
        """
        Çiftçi kendi parseline sulama olayı ekler.
        Bu sayede dashboard'lar (genel + bireysel) anlık güncellenir.

        Denetim Faz 8 — offlineQueue.js replay'i aynı sulama kaydını iki kez
        yazmasın diye idempotency korumalı (bkz. idempotency.py).
        """
        from idempotency import get_cached_response, save_response
        idem_key, cached = await get_cached_response(db, request, "farmer_irrigation:create")
        if cached is not None:
            return cached

        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi ekleyebilir")
    
        # Parsel gerçekten bu çiftçiye mi ait? (yetki kontrolü)
        parcel = await db.parcels.find_one({"id": body.parcel_id})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        if parcel.get("farmer_id") != user["farmer_id"]:
            raise HTTPException(403, "Bu parsel size ait değil")
    
        # Kayıt oluştur
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["farmer_id"] = user["farmer_id"]
        doc["region_id"] = parcel.get("region_id")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
    
        await db.irrigation_events.insert_one(doc)
        doc.pop("_id", None)
    
        # Bildirim oluştur (kooperatif yönetimine bilgi)
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "type": "sulama_kayit",
            "title": "Yeni sulama kaydı",
            "message": f"{user.get('full_name', 'Çiftçi')} {body.water_m3} m³ sulama kaydetti",
            "channel": "in_app",
            "status": "okundu",
            "farmer_id": user["farmer_id"],
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        await save_response(db, idem_key, "farmer_irrigation:create", doc)
        return doc


    @api_router.post("/farmer/soil-sample")
    async def add_soil_sample(body: SoilSampleCreate, user=Depends(current_user)):
        """Çiftçi toprak analizi sonucu ekler"""
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi ekleyebilir")
    
        parcel = await db.parcels.find_one({"id": body.parcel_id})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        if parcel.get("farmer_id") != user["farmer_id"]:
            raise HTTPException(403, "Bu parsel size ait değil")
    
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.soil_samples.insert_one(doc)
        doc.pop("_id", None)
        return doc


    # =====================================================================
    #                       ÇİFTÇİ YÖNETİMİ (Admin)
    # =====================================================================

    @api_router.get("/farmers")
    async def list_farmers(
        q: Optional[str] = None,
        region_id: Optional[str] = None,
        karne: Optional[str] = None,
        limit: int = 500,
        user=Depends(require_permission("farmers:view")),
        _feature=Depends(require_feature("farmer")),
    ):
        """
        Çiftçi listesi — admin arar/filtreler.
        Query parametreleri ile filtreleme yapılır:
        - q: ad/TC/telefon/üye no araması (regex)
        - region_id: belirli bölge
        - karne: A/B/C/D
        """
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
        if region_id:
            filt["region_id"] = region_id
        if karne:
            filt["karne_score"] = karne
        if q:
            # BULGU 2 düzeltmesi: kullanıcı girdisi $regex'e KAÇIŞSIZ verilmez.
            # safe_regex() re.escape + uzunluk limiti uygular (regex injection/ReDoS).
            rq = safe_regex(q)
            # OR araması — birden fazla alanda eşleşme
            filt["$or"] = [
                {"full_name": {"$regex": rq, "$options": "i"}},   # i = case-insensitive
                {"tc_no": {"$regex": rq}},
                {"phone": {"$regex": rq}},
                {"member_no": {"$regex": rq, "$options": "i"}}
            ]
        # BULGU 4 düzeltmesi: Türkçe collation — 'istanbul' aratınca 'İstanbul'
        # bulunur, sıralama Türk alfabesine uygun yapılır. collation, find()
        # kwarg'ı olarak verilir (zincirleme .collation() yerine).
        docs = await db.farmers.find(filt, {"_id": 0}, collation=TR_COLLATION).limit(limit).to_list(limit)
        docs = await mask_sensitive_fields_many(db, "farmers", docs, user)
        return docs


    @api_router.get("/farmers/{farmer_id}")
    async def get_farmer_360(farmer_id: str, user=Depends(require_permission("farmers:view")),
                              _feature=Depends(require_feature("farmer"))):
        """
        Çiftçi 360° GÖRÜNÜM:
        - Çiftçi temel bilgileri
        - Tüm parselleri (geometri ile)
        - Tüm sözleşmeleri
        - Verim geçmişi
        - Sulama olayları
        - Toprak analizleri
        - Finansal hareketler
        - Kantar randevuları
        - Karne detayı + tarihçe
    
        Bu sayfa müşteri demosunda gerçek hayattaki kullanımı gösterir.
        """
        farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        farmer = await mask_sensitive_fields(db, "farmers", farmer, user)

        parcels = await db.parcels.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
        parcel_ids = [p["id"] for p in parcels]
    
        contracts = await db.contracts.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
        yields = await db.yields.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
        irrigation = await db.irrigation_events.find(
            {"farmer_id": farmer_id}, {"_id": 0}
        ).sort([("date", -1)]).to_list(100)
        soil = await db.soil_samples.find(
            {"parcel_id": {"$in": parcel_ids}}, {"_id": 0}
        ).sort([("date", -1)]).to_list(50)
        finance = await db.finance.find(
            {"farmer_id": farmer_id}, {"_id": 0}
        ).sort([("date", -1)]).to_list(100)
        appointments = await db.appointments.find(
            {"farmer_id": farmer_id}, {"_id": 0}
        ).sort([("scheduled_at", -1)]).to_list(50)
        tasks = await db.tasks.find(
            {"farmer_id": farmer_id}, {"_id": 0}
        ).sort([("scheduled_date", -1)]).to_list(50)
    
        # Hesaplanmış metrikler
        total_area = sum(p.get("area_dekar", 0) for p in parcels)
        total_water = sum(e.get("water_m3", 0) for e in irrigation)
        balance = sum(f.get("amount", 0) for f in finance)
    
        # Verim trendi (yıl × ton)
        yield_by_year = {}
        for y in yields:
            yr = y.get("season")
            if yr not in yield_by_year:
                yield_by_year[yr] = {"expected": 0, "actual": 0, "area": 0}
            yield_by_year[yr]["expected"] += y.get("expected_ton", 0)
            yield_by_year[yr]["actual"] += y.get("actual_ton", 0)
            yield_by_year[yr]["area"] += y.get("area_dekar", 0)
    
        yield_trend = sorted(
            [{"year": yr, **vals} for yr, vals in yield_by_year.items()],
            key=lambda x: x["year"]
        )
    
        # #6 — SORUMLU (portföy): çiftçinin köyünden MİRAS (isimle eşleştirme).
        from admin_areas import resolve_responsible
        farmer_responsible = await resolve_responsible(db, (farmer or {}).get("village"))

        return {
            "farmer": farmer,
            "responsible": farmer_responsible,
            "summary": {
                "parcel_count": len(parcels),
                "total_area_dekar": round(total_area, 1),
                "active_contracts": len([c for c in contracts if c.get("status") == "imzalı"]),
                "total_water_m3": round(total_water, 1),
                "balance": round(balance, 2),
                "soil_samples_count": len(soil)
            },
            "parcels": parcels,
            "contracts": contracts,
            "yields": yields,
            "yield_trend": yield_trend,
            "irrigation": irrigation,
            "soil_samples": soil,
            "finance": finance,
            "appointments": appointments,
            "tasks": tasks
        }


    @api_router.post("/farmers")
    async def create_farmer(body: FarmerCreate, user=Depends(current_user), _feature=Depends(require_feature("farmer"))):
        """Yeni çiftçi ekle (admin yetkisi)"""
        if not is_admin(user):
            raise HTTPException(403, "Yetkiniz yok")
    
        # Duplicate TC kontrolü
        existing = await db.farmers.find_one({"tc_no": body.tc_no})
        if existing:
            raise HTTPException(400, "Bu TC No ile çiftçi zaten kayıtlı")
    
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
    
        # Üye no otomatik (TS-00001, TS-00002...)
        count = await db.farmers.count_documents({})
        doc["member_no"] = f"TS-{(count+1):05d}"
    
        doc["karne_score"] = "C"                                 # Yeni üye → orta puan
        doc["karne_points"] = 65
        doc["status"] = "aktif"
        doc["membership_year"] = datetime.now().year
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
    
        await db.farmers.insert_one(doc)
        doc.pop("_id", None)
        return doc


    @api_router.put("/farmers/{farmer_id}")
    async def update_farmer(farmer_id: str, body: FarmerUpdate, request: Request,
                             user=Depends(require_permission("farmers:edit")),
                             _feature=Depends(require_feature("farmer"))):
        """Çiftçi bilgi güncelle (IT-04: is_admin() yerine granüler farmers:edit izni)"""
        old = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Çiftçi bulunamadı")

        # Sadece dolu (None olmayan) alanları güncelle
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        # IT-07 — maskeli alan (örn. IBAN) düzenleme formunda değiştirilmeden
        # geri gönderilmişse ("•••• MASKELİ ••••"), bunu değişiklik SAYMA —
        # yoksa maskeyi görmeyen kullanıcı kendi kaydını farkında olmadan siler.
        updates = {k: v for k, v in updates.items() if not is_masked_value(v)}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")

        await db.farmers.update_one({"id": farmer_id}, {"$set": updates})
        updated = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="farmer", entity_id=farmer_id,
                         old_value=old, new_value=updated, request=request)
        return updated


    @api_router.delete("/farmers/{farmer_id}")
    async def delete_farmer(farmer_id: str, request: Request,
                            user=Depends(require_permission("farmers:delete")),
                            _feature=Depends(require_feature("farmer"))):
        """
        Çiftçiyi siler (soft delete, konvansiyon #3). Bağlı aktif parsel/sözleşme
        varsa engellenir — parseldeki 409 deseniyle aynı; önce o kayıtların
        kapatılması/taşınması gerekir (veri bütünlüğü).
        """
        old = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Çiftçi bulunamadı")

        linked_parcels = await db.parcels.count_documents(
            {"farmer_id": farmer_id, "is_active": {"$ne": False}}
        )
        if linked_parcels > 0:
            raise HTTPException(
                409,
                f"Bu çiftçiye bağlı {linked_parcels} parsel var. Önce parselleri "
                "başka çiftçiye atayın veya silin, sonra çiftçiyi silin."
            )
        linked_contracts = await db.contracts.count_documents(
            {"farmer_id": farmer_id, "is_active": {"$ne": False}}
        )
        if linked_contracts > 0:
            raise HTTPException(
                409,
                f"Bu çiftçiye bağlı {linked_contracts} sözleşme var. Önce sözleşmeleri "
                "kapatın/taşıyın, sonra çiftçiyi silin."
            )
        # Denetim A5 (2026-07-24): aktif (terminal olmayan) üretim sezonları da
        # yetim kalmasın — parsel/sözleşme guard'ıyla AYNI 409 deseni.
        linked_cycles = await db.production_cycles.count_documents(
            {"farmer_id": farmer_id, "status": {"$nin": ["completed", "cancelled"]}}
        )
        if linked_cycles > 0:
            raise HTTPException(
                409,
                f"Bu çiftçiye bağlı {linked_cycles} aktif üretim sezonu var. Önce "
                "sezonları tamamlayın veya iptal edin, sonra çiftçiyi silin."
            )

        await db.farmers.update_one(
            {"id": farmer_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }},
        )
        # Denetim A5: çiftçiye bağlı (guard gereği zaten pasif/terminal olan)
        # kayıtlar `farmer_inactive: true` ile işaretlenir — arşiv görünümleri
        # ve raporlar "sahibi pasif" kaydı ayırt edebilsin (kendi is_active/
        # status alanlarına DOKUNULMAZ, yetim işaretidir sadece).
        now_iso = datetime.now(timezone.utc).isoformat()
        for coll_name in ("parcels", "contracts", "production_cycles"):
            res = await db[coll_name].update_many(
                {"farmer_id": farmer_id},
                {"$set": {"farmer_inactive": True, "farmer_inactive_at": now_iso}},
            )
            if res.modified_count:
                await log_audit(db, user, action="cascade_farmer_inactive", entity=coll_name,
                                 entity_id=farmer_id,
                                 new_value={"farmer_id": farmer_id, "modified": res.modified_count},
                                 request=request)
        await log_audit(db, user, action="soft_delete", entity="farmer", entity_id=farmer_id, old_value=old, request=request)
        return {"status": "deactivated"}



