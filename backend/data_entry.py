"""
=====================================================================
Toprax — Veri Giriş Modülü (Sprint 4)
=====================================================================
Denetimde tespit edilen "sadece görüntüleme" ekranları için eksik
CREATE/UPDATE/DELETE endpoint'leri burada toplanır:

  - Sözleşmeler (contracts)
  - Ekim Planlama (plantings)
  - Toprak Analizi — admin/mühendis girişi (soil_samples)
  - Sulama Olayı — admin/mühendis girişi (irrigation_events)
  - Operasyon: Makine / İşçi / Görev (machines/workers/tasks)
  - Lojistik Randevu (appointments)
  - Kantar Kaydı (kantar_records)
  - E-Fatura / E-İrsaliye (einvoices/irsaliyeler)
  - IoT Sensör — manuel kayıt/güncelleme (iot_sensors)
  - Drone Görevi — manuel log (drone_missions)
  - Parsel düzenleme/silme (parcels) — temel alanlar; harita tabanlı
    geometry düzenleme (böl/birleştir/çiz) Sprint 4b'de ayrıca ele alınacak

Tüm endpoint'ler audit log'a yazar. Yetkilendirme artık granüler
permission sistemi (permissions.py) üzerinden yapılır — örn. kantar
personeli sadece "kantar:create" iznine sahipse kantar kaydı girebilir,
ziraat mühendisi olması ŞART DEĞİLDİR (bkz. permissions.py
DEFAULT_ROLE_PERMISSIONS).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from event_bus import publish


def register_data_entry_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    # God Mode Modül Yönetimi — "factory" flag'i kapatılınca kantar kaydı GERÇEKTEN 403 döner.
    require_feature = require_feature or (lambda key: (lambda: True))

    # =====================================================================
    # SÖZLEŞMELER
    # =====================================================================
    class ContractCreate(BaseModel):
        farmer_id: Optional[str] = None           # boşsa parseldeki çiftçiden türetilir
        parcel_id: str
        season: int
        crop: str = "Şeker Pancarı"
        variety: str
        kota_dekar: float
        kota_ton: float
        advance_seed_kg: Optional[float] = None
        advance_fertilizer_kg: Optional[float] = None
        status: str = "taslak"                    # taslak | imzalı | iptal

        # ============ IT-03 — Form Yönetimi ile eşleşen ek alanlar ============
        # --- Sözleşme Türü & Taraflar ---
        sozlesme_turu: Optional[str] = None                     # lookup: sozlesme_turu
        fabrika_temsilcisi: Optional[str] = None
        noter_onayli_mi: Optional[bool] = None
        imza_tarihi: Optional[str] = None                        # YYYY-MM-DD

        # --- Prim & Kesinti ---
        prim_orani_yuzde: Optional[float] = None
        prim_tutari: Optional[float] = None
        kesinti_orani_yuzde: Optional[float] = None
        kesinti_aciklama: Optional[str] = None

        # --- Fabrika Teslim ---
        teslim_fabrika: Optional[str] = None
        teslim_tarihi_planlanan: Optional[str] = None             # YYYY-MM-DD
        nakliye_sorumlusu: Optional[str] = None                   # lookup: nakliye_sorumlusu

        # --- IT-05 — ProductionCycle bağlantısı (opsiyonel, geriye uyumlu) ---
        production_cycle_id: Optional[str] = None

    class ContractUpdate(BaseModel):
        variety: Optional[str] = None
        kota_ton: Optional[float] = None
        advance_seed_kg: Optional[float] = None
        advance_fertilizer_kg: Optional[float] = None
        status: Optional[str] = None

        # --- IT-03 — ek alanlar (bkz. ContractCreate) ---
        sozlesme_turu: Optional[str] = None
        fabrika_temsilcisi: Optional[str] = None
        noter_onayli_mi: Optional[bool] = None
        imza_tarihi: Optional[str] = None
        prim_orani_yuzde: Optional[float] = None
        prim_tutari: Optional[float] = None
        kesinti_orani_yuzde: Optional[float] = None
        kesinti_aciklama: Optional[str] = None
        teslim_fabrika: Optional[str] = None
        teslim_tarihi_planlanan: Optional[str] = None
        nakliye_sorumlusu: Optional[str] = None
        production_cycle_id: Optional[str] = None

    @api_router.post("/contracts")
    async def create_contract(body: ContractCreate, request: Request,
                               user=Depends(require_permission("contracts:create"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["farmer_id"] = body.farmer_id or parcel["farmer_id"]
        doc["region_id"] = parcel["region_id"]

        # ---- #7 KOTA → EKİLEBİLİR ALAN KURALI (parametrik) --------------------
        # Yalnızca (sezon, ürün) için season_parameters TANIMLIYSA uygulanır
        # (böylece "sadece pancarda" ayrı bir kod dalı yerine veriyle sağlanır).
        #   gereken alan = kota_ton / ton_per_dekar
        #   yeterli  → normal (taslak)
        #   sapma içinde eksik → "onay_bekliyor" (yetkili onaylayana dek geçersiz)
        #   sapma dışında eksik → 400 (sözleşme yapılamaz)
        from season_parameters import get_season_params
        params = await get_season_params(db, body.season, doc.get("crop") or parcel.get("current_crop") or "")
        deviation = None
        if params and float(params.get("ton_per_dekar") or 0) > 0 and float(body.kota_ton or 0) > 0:
            tpd = float(params["ton_per_dekar"])
            sapma = float(params.get("sapma_yuzde") or 0)
            _e = parcel.get("ekilebilir_alan_dekar")
            ekilebilir = float(_e) if _e not in (None, "") else float(parcel.get("area_dekar") or 0)
            required = body.kota_ton / tpd
            min_with_dev = required * (1 - sapma / 100.0)
            if ekilebilir + 1e-9 >= required:
                pass  # yeterli alan
            elif ekilebilir + 1e-9 >= min_with_dev:
                deviation = {
                    "required_area_dekar": round(required, 2),
                    "ekilebilir_alan_dekar": round(ekilebilir, 2),
                    "sapma_yuzde": sapma, "ton_per_dekar": tpd, "kota_ton": body.kota_ton,
                    "aciklama": (f"Ekilebilir alan {ekilebilir:.1f} dekar; {body.kota_ton} ton kota için "
                                 f"gereken {required:.1f} dekarın altında ama %{sapma:.0f} sapma içinde — "
                                 f"ziraat mühendisi/bölge sorumlusu onayı gerekir."),
                }
            else:
                raise HTTPException(400,
                    f"Sözleşme yapılamaz: {body.kota_ton} ton kota için en az {required:.1f} dekar "
                    f"(±%{sapma:.0f} sapmayla {min_with_dev:.1f} dekar) ekilebilir alan gerekir; "
                    f"parselin ekilebilir alanı {ekilebilir:.1f} dekar.")
        if deviation:
            doc["status"] = "onay_bekliyor"
            doc["deviation"] = deviation

        # IT-05: production_cycle_id verilmediyse otomatik bağla (orphan kayıt
        # kalmaz; eski parcel_id KORUNUR — backward-compatible).
        if not doc.get("production_cycle_id"):
            from production_cycles import ensure_cycle_for
            doc["production_cycle_id"] = await ensure_cycle_for(db, body.parcel_id, body.season, doc["farmer_id"])
        doc["contract_no"] = f"SZ-{body.season}-{parcel['parcel_code'][-5:]}"
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.contracts.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="contract", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/contracts/{contract_id}")
    async def update_contract(contract_id: str, body: ContractUpdate, request: Request,
                               user=Depends(require_permission("contracts:edit"))):
        old = await db.contracts.find_one({"id": contract_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Sözleşme bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.contracts.update_one({"id": contract_id}, {"$set": updates})
        new = await db.contracts.find_one({"id": contract_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="contract", entity_id=contract_id, old_value=old, new_value=new, request=request)

        # (IT-27) Communication Policy tetikleyicisi — "Sözleşme Onaylandı"
        # örneği, SADECE status GERÇEKTEN "imzalı"ya değiştiyse (zaten imzalı
        # bir sözleşmenin başka bir alanının güncellenmesi yeniden tetiklemez).
        if updates.get("status") == "imzalı" and old.get("status") != "imzalı":
            await publish(db, "contract_approved", {
                "farmer_id": new["farmer_id"], "parcel_id": new["parcel_id"], "contract_id": new["id"],
            })
        return new

    class DeviationDecision(BaseModel):
        decision: str                     # onayla | reddet
        note: Optional[str] = None

    @api_router.post("/contracts/{contract_id}/deviation-decision")
    async def contract_deviation_decision(contract_id: str, body: DeviationDecision, request: Request,
                                          user=Depends(require_permission("contracts:edit"))):
        """#7 — Kota→alan sapması nedeniyle 'onay_bekliyor'da bekleyen sözleşmeyi
        yetkili (ziraat mühendisi/bölge sorumlusu; contracts:edit) onaylar/reddeder.
        Onay → 'taslak' (geçerli sözleşme); Red → 'iptal'."""
        c = await db.contracts.find_one({"id": contract_id}, {"_id": 0})
        if not c:
            raise HTTPException(404, "Sözleşme bulunamadı")
        if c.get("status") != "onay_bekliyor":
            raise HTTPException(400, "Bu sözleşme sapma onayı beklemiyor")
        if body.decision not in ("onayla", "reddet"):
            raise HTTPException(400, "decision 'onayla' veya 'reddet' olmalı")
        new_status = "taslak" if body.decision == "onayla" else "iptal"
        await db.contracts.update_one({"id": contract_id}, {"$set": {
            "status": new_status,
            "deviation_decided_by": user.get("full_name") or user.get("email"),
            "deviation_decided_at": datetime.now(timezone.utc).isoformat(),
            "deviation_decision_note": body.note,
        }})
        new = await db.contracts.find_one({"id": contract_id}, {"_id": 0})
        await log_audit(db, user, action="deviation_decision", entity="contract", entity_id=contract_id,
                        old_value={"status": "onay_bekliyor"},
                        new_value={"status": new_status, "decision": body.decision}, request=request)
        return new

    @api_router.delete("/contracts/{contract_id}")
    async def delete_contract(contract_id: str, request: Request,
                               user=Depends(require_permission("contracts:delete"))):
        # BULGU 1 (Kritik) düzeltmesi: fiziksel silme YAPILMAZ. CLAUDE.md
        # Bölüm 4 Konvansiyon #3 gereği çekirdek/finansal-yakın kayıtlar
        # is_active=False ile pasife alınır; audit izi + kayıt gövdesi DB'de
        # kalır, geri alınabilir.
        old = await db.contracts.find_one({"id": contract_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Sözleşme bulunamadı")

        # Bağlı-kayıt (orphan) koruması — parseldeki 409 deseniyle aynı:
        # sözleşmeye bağlı ekim veya ledger (hakediş/finans) hareketi varsa
        # önce onlar kapatılmalı, aksi halde veri bütünlüğü bozulur.
        linked_plantings = await db.plantings.count_documents(
            {"contract_id": contract_id, "is_active": {"$ne": False}}
        )
        if linked_plantings > 0:
            raise HTTPException(
                409,
                f"Bu sözleşmeye bağlı {linked_plantings} ekim kaydı var. Önce ekim "
                "kayıtlarını kapatın/taşıyın, sonra sözleşmeyi silin."
            )
        linked_ledger = await db.ledger_entries.count_documents(
            {"reference_type": "contract", "reference_id": contract_id}
        )
        if linked_ledger > 0:
            raise HTTPException(
                409,
                f"Bu sözleşmeye bağlı {linked_ledger} finansal (ledger) hareket var. "
                "Finansal kayıtlar ters kayıtla düzeltilir; sözleşme silinemez."
            )

        await db.contracts.update_one(
            {"id": contract_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }},
        )
        await log_audit(db, user, action="soft_delete", entity="contract", entity_id=contract_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # EKİM PLANLAMA
    # =====================================================================
    class PlantingCreate(BaseModel):
        contract_id: Optional[str] = None
        parcel_id: str
        farmer_id: Optional[str] = None            # boşsa parseldeki çiftçiden türetilir
        season: int
        crop: str = "Şeker Pancarı"
        variety: str
        planting_date: str
        expected_harvest_date: str
        stage: str = "ekim"                        # ekim | gelişim | olgunlaşma | hasat

        # ============ IT-03 — Form Yönetimi ile eşleşen ek alanlar ============
        # --- Tohum & Ekim Detayı ---
        tohum_kaynagi: Optional[str] = None                       # Tedarikçi/kaynak
        tohum_parti_no: Optional[str] = None
        tohum_miktari_kg: Optional[float] = None
        ekim_yontemi: Optional[str] = None                         # lookup: ekim_yontemi

        # --- Takvim ---
        sira_araligi_cm: Optional[float] = None
        sulama_plani_baslangic: Optional[str] = None                # YYYY-MM-DD
        gubreleme_plani_tarihi: Optional[str] = None                 # YYYY-MM-DD

        # --- Kaynak Planlama ---
        planlanan_makine: Optional[str] = None
        planlanan_isci_sayisi: Optional[int] = None
        kaynak_notu: Optional[str] = None

        # --- IT-05 — ProductionCycle bağlantısı (opsiyonel, geriye uyumlu) ---
        production_cycle_id: Optional[str] = None

    class PlantingUpdate(BaseModel):
        stage: Optional[str] = None
        actual_harvest_date: Optional[str] = None
        expected_harvest_date: Optional[str] = None

        # --- IT-03 — ek alanlar (bkz. PlantingCreate) ---
        tohum_kaynagi: Optional[str] = None
        tohum_parti_no: Optional[str] = None
        tohum_miktari_kg: Optional[float] = None
        ekim_yontemi: Optional[str] = None
        sira_araligi_cm: Optional[float] = None
        sulama_plani_baslangic: Optional[str] = None
        gubreleme_plani_tarihi: Optional[str] = None
        planlanan_makine: Optional[str] = None
        planlanan_isci_sayisi: Optional[int] = None
        kaynak_notu: Optional[str] = None
        production_cycle_id: Optional[str] = None

    @api_router.post("/plantings")
    async def create_planting(body: PlantingCreate, request: Request,
                               user=Depends(require_permission("plantings:create"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["farmer_id"] = body.farmer_id or parcel["farmer_id"]
        doc["region_id"] = parcel["region_id"]
        doc["actual_harvest_date"] = None
        # IT-05: production_cycle_id verilmediyse otomatik bağla (backward-compatible).
        if not doc.get("production_cycle_id"):
            from production_cycles import ensure_cycle_for
            doc["production_cycle_id"] = await ensure_cycle_for(db, body.parcel_id, body.season, doc["farmer_id"])
        await db.plantings.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="planting", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/plantings/{planting_id}")
    async def update_planting(planting_id: str, body: PlantingUpdate, request: Request,
                               user=Depends(require_permission("plantings:edit"))):
        old = await db.plantings.find_one({"id": planting_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Ekim kaydı bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.plantings.update_one({"id": planting_id}, {"$set": updates})
        new = await db.plantings.find_one({"id": planting_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="planting", entity_id=planting_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/plantings/{planting_id}")
    async def delete_planting(planting_id: str, request: Request,
                               user=Depends(require_permission("plantings:delete"))):
        # Konvansiyon #3 — soft delete (is_active=False); kayıt + audit izi DB'de kalır.
        old = await db.plantings.find_one({"id": planting_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Ekim kaydı bulunamadı")
        await db.plantings.update_one(
            {"id": planting_id},
            {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat(),
                      "deleted_by": user.get("full_name") or user.get("email")}},
        )
        await log_audit(db, user, action="soft_delete", entity="planting", entity_id=planting_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # TOPRAK ANALİZİ (admin/mühendis girişi — çiftçi self-servisten ayrı)
    # =====================================================================
    class SoilSampleAdminCreate(BaseModel):
        parcel_id: str
        date: str
        lab_name: str
        ph: float
        ec: float                                            # Tuzluluğun ham ölçümü de budur (dS/m)
        organic_matter_pct: float
        n_ppm: int
        p_ppm: int
        k_ppm: int
        recommendation: Optional[str] = None

        # ============ IT-02 — Form Yönetimi ile eşleşen ek alanlar ============
        # Ekranda zorunlu/görünür/sıra/lookup davranışı field_definitions
        # (module="soil") tarafından yönetilir; burada sadece gerçek, tipli
        # DB kolonları olarak tanımlanırlar (Sprint A1 kuralı).

        # --- Fiziksel Özellikler ---
        toprak_teksturu: Optional[str] = None                  # lookup: toprak_teksturu
        toprak_derinligi_cm: Optional[float] = None
        taslilik_orani_yuzde: Optional[float] = None

        # --- Kimyasal Özellikler ---
        tuzluluk_sinifi: Optional[str] = None                  # lookup: tuzluluk_sinifi (ec'nin yorumlanmış sınıfı)
        kirec_orani_yuzde: Optional[float] = None               # CaCO3 %

        # --- Mikro Besin Elementleri ---
        zn_ppm: Optional[float] = None                          # Çinko
        fe_ppm: Optional[float] = None                          # Demir
        bor_ppm: Optional[float] = None                         # Bor

        # --- Rapor & AI ---
        analiz_rapor_no: Optional[str] = None
        ai_yorum: Optional[str] = None                          # AI değerlendirme metni
        ai_risk_skoru: Optional[int] = None                     # 0-100, AI hesaplar veya elle girilir

        # --- IT-05 — ProductionCycle bağlantısı (opsiyonel, geriye uyumlu) ---
        production_cycle_id: Optional[str] = None

    def _auto_recommendation(ph: float) -> str:
        if ph < 6.0:
            return "Asitli toprak — Kireçleme önerilir, nötr pH'a yakın gübre tercih et"
        elif ph > 7.8:
            return "Alkalin toprak — Asit içerikli DAP tercih et, 25 kg/dekar"
        return "Standart DAP 25 kg/dekar + Üre 30 kg/dekar"

    @api_router.post("/soil-samples")
    async def create_soil_sample(body: SoilSampleAdminCreate, request: Request,
                                  user=Depends(require_permission("soil:create"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        if not doc.get("recommendation"):
            doc["recommendation"] = _auto_recommendation(body.ph)
        doc["entered_by"] = user.get("full_name")
        # IT-05: production_cycle_id verilmediyse otomatik bağla. Toprak analizinde
        # yıl alanı yok — analiz tarihinden (date) türetilir, olmazsa mevcut yıl.
        if not doc.get("production_cycle_id"):
            from production_cycles import ensure_cycle_for
            try:
                _yr = int(str(body.date)[:4])
            except Exception:
                _yr = datetime.now(timezone.utc).year
            doc["production_cycle_id"] = await ensure_cycle_for(db, body.parcel_id, _yr, parcel.get("farmer_id"))
        await db.soil_samples.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="soil_sample", entity_id=doc["id"], new_value=doc, request=request)
        # (IT-24) Otomasyon tetikleyicisi — roadmap'in verdiği örnek: "Toprak
        # Analizi tamamlandı" -> otomatik "Ekim Kontrolü" görevi. Bu bir
        # yan etkidir, admin bu event_type için hiç kural tanımlamamışsa
        # publish() sessizce hiçbir şey yapmaz (bkz. event_bus.py).
        await publish(db, "soil_analysis_completed", {
            "farmer_id": parcel.get("farmer_id"),
            "parcel_id": doc["parcel_id"],
            "production_cycle_id": doc.get("production_cycle_id"),
        })
        return doc

    class SoilSampleAdminUpdate(BaseModel):
        date: Optional[str] = None
        lab_name: Optional[str] = None
        ph: Optional[float] = None
        ec: Optional[float] = None
        organic_matter_pct: Optional[float] = None
        n_ppm: Optional[int] = None
        p_ppm: Optional[int] = None
        k_ppm: Optional[int] = None
        recommendation: Optional[str] = None
        toprak_teksturu: Optional[str] = None
        toprak_derinligi_cm: Optional[float] = None
        taslilik_orani_yuzde: Optional[float] = None
        tuzluluk_sinifi: Optional[str] = None
        kirec_orani_yuzde: Optional[float] = None
        zn_ppm: Optional[float] = None
        fe_ppm: Optional[float] = None
        bor_ppm: Optional[float] = None
        analiz_rapor_no: Optional[str] = None
        ai_yorum: Optional[str] = None
        ai_risk_skoru: Optional[int] = None

    @api_router.put("/soil-samples/{sample_id}")
    async def update_soil_sample(sample_id: str, body: SoilSampleAdminUpdate, request: Request,
                                 user=Depends(require_permission("soil:edit"))):
        old = await db.soil_samples.find_one({"id": sample_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Toprak analizi bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.soil_samples.update_one({"id": sample_id}, {"$set": updates})
        new = await db.soil_samples.find_one({"id": sample_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="soil_sample", entity_id=sample_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/soil-samples/{sample_id}")
    async def delete_soil_sample(sample_id: str, request: Request,
                                 user=Depends(require_permission("soil:delete"))):
        old = await db.soil_samples.find_one({"id": sample_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Toprak analizi bulunamadı")
        await db.soil_samples.update_one(
            {"id": sample_id},
            {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat(),
                      "deleted_by": user.get("full_name") or user.get("email")}},
        )
        await log_audit(db, user, action="soft_delete", entity="soil_sample", entity_id=sample_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # SULAMA OLAYI (admin/mühendis girişi)
    # =====================================================================
    class IrrigationEventAdminCreate(BaseModel):
        parcel_id: str
        date: str
        method: str                                 # damla | yağmurlama | karık
        water_m3: float
        moisture_before: Optional[int] = None
        moisture_after: Optional[int] = None

    @api_router.post("/irrigation/events")
    async def create_irrigation_event(body: IrrigationEventAdminCreate, request: Request,
                                       user=Depends(require_permission("irrigation:create"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["farmer_id"] = parcel["farmer_id"]
        doc["region_id"] = parcel["region_id"]
        doc["entered_by"] = user.get("full_name")
        await db.irrigation_events.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="irrigation_event", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    class IrrigationEventAdminUpdate(BaseModel):
        date: Optional[str] = None
        method: Optional[str] = None
        water_m3: Optional[float] = None
        moisture_before: Optional[int] = None
        moisture_after: Optional[int] = None

    @api_router.put("/irrigation/events/{event_id}")
    async def update_irrigation_event(event_id: str, body: IrrigationEventAdminUpdate, request: Request,
                                      user=Depends(require_permission("irrigation:edit"))):
        old = await db.irrigation_events.find_one({"id": event_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Sulama kaydı bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.irrigation_events.update_one({"id": event_id}, {"$set": updates})
        new = await db.irrigation_events.find_one({"id": event_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="irrigation_event", entity_id=event_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/irrigation/events/{event_id}")
    async def delete_irrigation_event(event_id: str, request: Request,
                                      user=Depends(require_permission("irrigation:delete"))):
        old = await db.irrigation_events.find_one({"id": event_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Sulama kaydı bulunamadı")
        await db.irrigation_events.update_one(
            {"id": event_id},
            {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat(),
                      "deleted_by": user.get("full_name") or user.get("email")}},
        )
        await log_audit(db, user, action="soft_delete", entity="irrigation_event", entity_id=event_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # OPERASYON — MAKİNE
    # =====================================================================
    class MachineCreate(BaseModel):
        type: str
        model: str
        serial_no: str
        region_id: str
        owner: str = "kooperatif"                   # kooperatif | çiftçi
        status: str = "aktif"                        # aktif | bakım | boşta
        total_hours: int = 0
        last_maintenance: Optional[str] = None

    class MachineUpdate(BaseModel):
        status: Optional[str] = None
        total_hours: Optional[int] = None
        last_maintenance: Optional[str] = None

    @api_router.post("/operations/machines")
    async def create_machine(body: MachineCreate, request: Request,
                              user=Depends(require_permission("operations:machines_manage"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        await db.machines.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="machine", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/operations/machines/{machine_id}")
    async def update_machine(machine_id: str, body: MachineUpdate, request: Request,
                              user=Depends(require_permission("operations:machines_manage"))):
        old = await db.machines.find_one({"id": machine_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Makine bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.machines.update_one({"id": machine_id}, {"$set": updates})
        new = await db.machines.find_one({"id": machine_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="machine", entity_id=machine_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/operations/machines/{machine_id}")
    async def delete_machine(machine_id: str, request: Request,
                              user=Depends(require_permission("operations:machines_manage"))):
        old = await db.machines.find_one({"id": machine_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Makine bulunamadı")
        # BULGU 1 düzeltmesi: hard-delete -> soft-delete
        await db.machines.update_one(
            {"id": machine_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }},
        )
        await log_audit(db, user, action="soft_delete", entity="machine", entity_id=machine_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # OPERASYON — İŞÇİ
    # =====================================================================
    class WorkerCreate(BaseModel):
        full_name: str
        phone: str
        region_id: str
        skill: str
        daily_wage: float
        status: str = "aktif"

    class WorkerUpdate(BaseModel):
        status: Optional[str] = None
        daily_wage: Optional[float] = None
        skill: Optional[str] = None

    @api_router.post("/operations/workers")
    async def create_worker(body: WorkerCreate, request: Request,
                             user=Depends(require_permission("operations:workers_manage"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        await db.workers.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="worker", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/operations/workers/{worker_id}")
    async def update_worker(worker_id: str, body: WorkerUpdate, request: Request,
                             user=Depends(require_permission("operations:workers_manage"))):
        old = await db.workers.find_one({"id": worker_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "İşçi bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.workers.update_one({"id": worker_id}, {"$set": updates})
        new = await db.workers.find_one({"id": worker_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="worker", entity_id=worker_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/operations/workers/{worker_id}")
    async def delete_worker(worker_id: str, request: Request,
                             user=Depends(require_permission("operations:workers_manage"))):
        old = await db.workers.find_one({"id": worker_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "İşçi bulunamadı")
        # BULGU 1 düzeltmesi: hard-delete -> soft-delete
        await db.workers.update_one(
            {"id": worker_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }},
        )
        await log_audit(db, user, action="soft_delete", entity="worker", entity_id=worker_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # OPERASYON — GÖREV
    # =====================================================================
    class TaskCreate(BaseModel):
        task_type: str
        parcel_id: str
        scheduled_date: str
        machine_id: Optional[str] = None
        worker_id: Optional[str] = None
        notes: Optional[str] = ""

    class TaskUpdate(BaseModel):
        status: Optional[str] = None                # planlı | devam ediyor | tamamlandı | iptal
        notes: Optional[str] = None
        machine_id: Optional[str] = None
        worker_id: Optional[str] = None
        scheduled_date: Optional[str] = None

    @api_router.post("/operations/tasks")
    async def create_task(body: TaskCreate, request: Request,
                           user=Depends(require_permission("operations:tasks_manage"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["farmer_id"] = parcel["farmer_id"]
        doc["region_id"] = parcel["region_id"]
        doc["status"] = "planlı"
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.tasks.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="task", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/operations/tasks/{task_id}")
    async def update_task(task_id: str, body: TaskUpdate, request: Request,
                           user=Depends(require_permission("operations:tasks_manage"))):
        old = await db.tasks.find_one({"id": task_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Görev bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.tasks.update_one({"id": task_id}, {"$set": updates})
        new = await db.tasks.find_one({"id": task_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="task", entity_id=task_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/operations/tasks/{task_id}")
    async def delete_task(task_id: str, request: Request,
                           user=Depends(require_permission("operations:tasks_manage"))):
        old = await db.tasks.find_one({"id": task_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Görev bulunamadı")
        # BULGU 1 düzeltmesi: hard-delete -> soft-delete
        await db.tasks.update_one(
            {"id": task_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }},
        )
        await log_audit(db, user, action="soft_delete", entity="task", entity_id=task_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # LOJİSTİK RANDEVU
    # =====================================================================
    class AppointmentCreate(BaseModel):
        farmer_id: str
        scheduled_at: str
        truck_plate: str
        estimated_ton: float

    class AppointmentUpdate(BaseModel):
        status: Optional[str] = None                # planlı | geldi | tartıldı | tamamlandı
        actual_ton: Optional[float] = None
        polar_oran: Optional[float] = None
        scheduled_at: Optional[str] = None

    @api_router.post("/logistics/appointments")
    async def create_appointment(body: AppointmentCreate, request: Request,
                                  user=Depends(require_permission("logistics:create"))):
        farmer = await db.farmers.find_one({"id": body.farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["region_id"] = farmer["region_id"]
        doc["status"] = "planlı"
        doc["actual_ton"] = None
        doc["polar_oran"] = None
        await db.appointments.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="appointment", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/logistics/appointments/{appt_id}")
    async def update_appointment(appt_id: str, body: AppointmentUpdate, request: Request,
                                  user=Depends(require_permission("logistics:create"))):
        old = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Randevu bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.appointments.update_one({"id": appt_id}, {"$set": updates})
        new = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="appointment", entity_id=appt_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/logistics/appointments/{appt_id}")
    async def delete_appointment(appt_id: str, request: Request,
                                 user=Depends(require_permission("logistics:delete"))):
        old = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Randevu bulunamadı")
        await db.appointments.update_one(
            {"id": appt_id},
            {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat(),
                      "deleted_by": user.get("full_name") or user.get("email")}},
        )
        await log_audit(db, user, action="soft_delete", entity="appointment", entity_id=appt_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # KANTAR KAYDI
    # =====================================================================
    class KantarRecordCreate(BaseModel):
        farmer_id: str
        truck_plate: str
        brut_ton: float
        dara_ton: float
        polar_oran: float
        fire_pct: float = 0
        kalite: str = "B"                            # A | B | C
        kantar_no: str = "K-1"
        weighing_at: Optional[str] = None             # boşsa şimdi kullanılır

        # --- IT-20 — Hakediş Motoru bağlantısı (opsiyonel, geriye uyumlu) ---
        # Bir çiftçinin aynı yılda birden fazla parseli/sezonu olabileceğinden
        # (bkz. CLAUDE.md IT-05 notu) bu alan sadece kayıt bir ProductionCycle
        # bağlamından (UI'dan) oluşturulursa elle set edilir; boş bırakılan
        # eski/yeni kayıtlar entitlement.py'nin hesaplamasına dahil OLMAZ.
        production_cycle_id: Optional[str] = None

    @api_router.post("/kantar/records")
    async def create_kantar_record(body: KantarRecordCreate, request: Request,
                                    user=Depends(require_permission("kantar:create")),
                                    _feat=Depends(require_feature("factory"))):
        farmer = await db.farmers.find_one({"id": body.farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        if body.dara_ton >= body.brut_ton:
            raise HTTPException(400, "Dara, brüt ağırlıktan küçük olmalı")

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["fis_no"] = f"K-{datetime.now().year}-{uuid.uuid4().hex[:5].upper()}"
        doc["weighing_at"] = body.weighing_at or datetime.now(timezone.utc).isoformat()
        doc["farmer_name"] = farmer["full_name"]
        doc["member_no"] = farmer.get("member_no")
        doc["net_ton"] = round(body.brut_ton - body.dara_ton, 2)
        doc["operator"] = user.get("full_name")
        await db.kantar_records.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="kantar_record", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    class KantarRecordUpdate(BaseModel):
        truck_plate: Optional[str] = None
        brut_ton: Optional[float] = None
        dara_ton: Optional[float] = None
        polar_oran: Optional[float] = None
        fire_pct: Optional[float] = None
        kalite: Optional[str] = None
        kantar_no: Optional[str] = None
        weighing_at: Optional[str] = None

    @api_router.put("/kantar/records/{record_id}")
    async def update_kantar_record(record_id: str, body: KantarRecordUpdate, request: Request,
                                   user=Depends(require_permission("kantar:edit"))):
        old = await db.kantar_records.find_one({"id": record_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kantar kaydı bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        # brut/dara değiştiyse net_ton yeniden hesaplanır (tutarlılık).
        brut = updates.get("brut_ton", old.get("brut_ton"))
        dara = updates.get("dara_ton", old.get("dara_ton"))
        if brut is not None and dara is not None:
            if dara >= brut:
                raise HTTPException(400, "Dara, brüt ağırlıktan küçük olmalı")
            updates["net_ton"] = round(brut - dara, 2)
        if updates:
            await db.kantar_records.update_one({"id": record_id}, {"$set": updates})
        new = await db.kantar_records.find_one({"id": record_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="kantar_record", entity_id=record_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/kantar/records/{record_id}")
    async def delete_kantar_record(record_id: str, request: Request,
                                   user=Depends(require_permission("kantar:delete"))):
        # Kantar kaydı hakedişe (entitlement) girdi olur — konvansiyon #3 gereği
        # soft delete; silinen kayıt entitlement hesabından da düşer (is_active filtresi).
        old = await db.kantar_records.find_one({"id": record_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kantar kaydı bulunamadı")
        await db.kantar_records.update_one(
            {"id": record_id},
            {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat(),
                      "deleted_by": user.get("full_name") or user.get("email")}},
        )
        await log_audit(db, user, action="soft_delete", entity="kantar_record", entity_id=record_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # E-FATURA
    # =====================================================================
    class EInvoiceCreate(BaseModel):
        farmer_id: str
        type: str                                     # tohum | gübre | ilaç | kombine
        net_amount: float
        date: Optional[str] = None                    # boşsa bugün

    @api_router.post("/e-belge/invoices")
    async def create_einvoice(body: EInvoiceCreate, request: Request,
                               user=Depends(require_permission("ebelge:create"))):
        farmer = await db.farmers.find_one({"id": body.farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["invoice_no"] = f"EFT-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"
        doc["farmer_name"] = farmer["full_name"]
        doc["member_no"] = farmer.get("member_no")
        doc["kdv"] = round(body.net_amount * 0.20, 2)
        doc["total"] = round(body.net_amount + doc["kdv"], 2)
        doc["status"] = "beklemede"                   # manuel girilenler GİB'e otomatik gönderilmez
        doc["uuid_no"] = uuid.uuid4().hex[:32].upper()
        doc["gib_status"] = "gönderilmedi"
        if not doc.get("date"):
            doc["date"] = datetime.now(timezone.utc).date().isoformat()
        await db.einvoices.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="einvoice", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    # =====================================================================
    # E-İRSALİYE
    # =====================================================================
    class IrsaliyeCreate(BaseModel):
        farmer_id: str
        product: str
        quantity: float
        unit: str = "kg"
        truck_plate: Optional[str] = None

    @api_router.post("/e-belge/irsaliyeler")
    async def create_irsaliye(body: IrsaliyeCreate, request: Request,
                               user=Depends(require_permission("ebelge:create"))):
        farmer = await db.farmers.find_one({"id": body.farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["irsaliye_no"] = f"İRS-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"
        doc["farmer_name"] = farmer["full_name"]
        doc["member_no"] = farmer.get("member_no")
        doc["date"] = datetime.now(timezone.utc).date().isoformat()
        doc["status"] = "taşımada"
        await db.irsaliyeler.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="irsaliye", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    # =====================================================================
    # IoT SENSÖR — Manuel kayıt (gerçek donanım kurulumu sonrası)
    # =====================================================================
    class IotSensorCreate(BaseModel):
        parcel_id: str
        type: str = "nem_sicaklik"                    # nem_sicaklik | toprak_nemi | hava_istasyonu
        sensor_code: Optional[str] = None             # boşsa otomatik üretilir

    class IotReadingUpdate(BaseModel):
        """Gerçek donanım entegrasyonu gelene kadar sensör okumalarını manuel güncellemek için."""
        nem_pct: Optional[float] = None
        sicaklik_c: Optional[float] = None
        battery_pct: Optional[int] = None
        signal_strength: Optional[int] = None
        status: Optional[str] = None                  # aktif | offline | bakım_gerekli

    @api_router.post("/iot/sensors")
    async def register_iot_sensor(body: IotSensorCreate, request: Request,
                                   user=Depends(require_permission("iot:manage"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        total = await db.iot_sensors.count_documents({})
        doc = {
            "id": str(uuid.uuid4()),
            "sensor_code": body.sensor_code or f"IOT-{total + 1:04d}",
            "parcel_id": body.parcel_id,
            "parcel_code": parcel["parcel_code"],
            "farmer_id": parcel["farmer_id"],
            "region_id": parcel["region_id"],
            "type": body.type,
            "nem_pct": None,
            "sicaklik_c": None,
            "battery_pct": 100,
            "signal_strength": 5,
            "status": "aktif",
            "last_reading_at": None,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.iot_sensors.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="iot_sensor", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/iot/sensors/{sensor_id}")
    async def update_iot_reading(sensor_id: str, body: IotReadingUpdate, request: Request,
                                  user=Depends(require_permission("iot:manage"))):
        old = await db.iot_sensors.find_one({"id": sensor_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Sensör bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        updates["last_reading_at"] = datetime.now(timezone.utc).isoformat()
        await db.iot_sensors.update_one({"id": sensor_id}, {"$set": updates})
        new = await db.iot_sensors.find_one({"id": sensor_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="iot_sensor", entity_id=sensor_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/iot/sensors/{sensor_id}")
    async def delete_iot_sensor(sensor_id: str, request: Request,
                                 user=Depends(require_permission("iot:manage"))):
        old = await db.iot_sensors.find_one({"id": sensor_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Sensör bulunamadı")
        # BULGU 1 düzeltmesi: hard-delete -> soft-delete
        await db.iot_sensors.update_one(
            {"id": sensor_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user.get("full_name") or user.get("email"),
            }},
        )
        await log_audit(db, user, action="soft_delete", entity="iot_sensor", entity_id=sensor_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =====================================================================
    # DRONE GÖREVİ — Manuel log (gerçek entegrasyon gelene kadar)
    # =====================================================================
    class DroneMissionCreate(BaseModel):
        parcel_id: str
        flight_date: str
        pilot: str
        altitude_m: int = 80
        finding_type: str                             # hastalık_tespiti | yabancı_ot | su_stresi | genel_tarama
        severity: str = "yok"                         # düşük | orta | yüksek | yok
        notes: Optional[str] = None

    @api_router.post("/drone/missions")
    async def create_drone_mission(body: DroneMissionCreate, request: Request,
                                    user=Depends(require_permission("drone:manage"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        total = await db.drone_missions.count_documents({})
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["mission_code"] = f"DRN-{total + 1:03d}"
        doc["parcel_code"] = parcel["parcel_code"]
        doc["farmer_id"] = parcel["farmer_id"]
        doc["region_id"] = parcel["region_id"]
        doc["coverage_dekar"] = parcel["area_dekar"]
        doc["status"] = "tamamlandı"
        if not doc.get("notes"):
            doc["notes"] = {
                "hastalık_tespiti": "Yaprak lekesi belirtileri tespit edildi, ziraat mühendisi kontrolü önerilir.",
                "yabancı_ot": "Parsel kenarlarında yabancı ot yoğunluğu artışı gözlemlendi.",
                "su_stresi": "Bitki örtüsünde su stresine işaret eden renk değişimi tespit edildi.",
                "genel_tarama": "Anomali tespit edilmedi, gelişim normal seyrediyor.",
            }.get(body.finding_type, "")
        await db.drone_missions.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="drone_mission", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    # NOT: Parsel düzenleme (PUT) ve silme (DELETE) endpoint'leri server.py
    # içinde tanımlı — orada geometry alanı, risk_level manuel override'ı ve
    # bağlı sözleşme kontrolü ile birlikte, split/merge/import-geojson'la
    # aynı yerde toplanmış durumda. Burada tekrar tanımlamıyoruz (route
    # çakışması olurdu).
