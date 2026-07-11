"""
Ek Modüller — MVP Tamamlama
============================
Bu dosya, mevcut server.py'a ek olarak yeni endpoint'leri ve özellikleri içerir.
server.py içine import edilerek aktive edilir.

Eklenenler:
- AI Hastalık Tespiti (OpenAI/Gemini/Anthropic vision — Ayarlar > Entegrasyonlar'dan yapılandırılır)
- Audit log altyapısı
- Sentinel Hub MOCK NDVI verisi
- E-fatura/İrsaliye demo verileri
- Müstahsil makbuzu PDF üretimi
- Saha ziyaret raporu (mobil, GPS + fotoğraf)
- Çiftçi profil güncelleme
- Çiftçi toprak analizi formu zaten /api/farmer/soil-sample altında var

NOT: SMS/Email/Planet Labs entegrasyon ayarları artık bu dosyada değil,
merkezi Ayarlar modülünde (integrations.py).
"""
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid
import io
import base64
import os
import random
import json
import re
from tenant_context import current_tenant_id
from satellite_provider import get_satellite_provider, ndvi_to_health, ndvi_to_risk_level, DemoSatelliteProvider
from ai_provider import get_ai_provider
from config_service import ALLOW_DATA_SEEDING


def register_extra_routes(api_router, db, current_user, is_admin, require_feature=None):
    # IT-33 — "ai" feature flag'i kapatılınca AI uçları GERÇEKTEN 403 döner.
    # require_feature verilmezse (geriye dönük uyumluluk) hiç kontrol edilmez.
    _no_check = lambda key: (lambda: True)
    require_feature = require_feature or _no_check
    """Bu fonksiyon ana server.py tarafından çağrılır, tüm yeni endpoint'leri ekler"""

    # =====================================================================
    # AI HASTALIK TESPİTİ — Gemini Vision
    # =====================================================================
    
    class DiseaseDetectReq(BaseModel):
        image_base64: str                                    # data:image/jpeg;base64,xxx VEYA sadece base64
        parcel_id: Optional[str] = None
        notes: Optional[str] = None
    
    @api_router.post("/ai/disease-detect")
    async def ai_disease_detect(body: DiseaseDetectReq, user=Depends(current_user), _feat=Depends(require_feature("ai"))):
        """
        Yüklenen bitki fotoğrafından hastalık tespiti yapar.

        AI servis sağlayıcısı (OpenAI / Gemini / Anthropic) ve API key
        "Ayarlar > Entegrasyonlar > AI Servisi" ekranından admin tarafından
        girilir (bkz. integrations.py). Sağlayıcıya göre uygun vision API'si
        çağrılır.
        """
        from integrations import get_ai_service_config

        ai_cfg = await get_ai_service_config(db)
        if not ai_cfg:
            raise HTTPException(
                500,
                "AI servisi yapılandırılmamış. Lütfen Ayarlar > Entegrasyonlar > AI Servisi "
                "bölümünden bir sağlayıcı (OpenAI/Gemini/Anthropic) ve API key girin."
            )

        # Base64'ün "data:image/..." prefix'ini temizle
        img_b64 = body.image_base64
        if "," in img_b64:
            img_b64 = img_b64.split(",", 1)[1]

        system_prompt = (
            "Sen bir tarım uzmanı ziraat mühendisisin. "
            "Sana gönderilen bitki fotoğrafını analiz et ve şunları Türkçe olarak yaz: "
            "1) Görünen bitki türü, 2) Tespit edilen hastalık/zararlı (varsa), "
            "3) Şiddet (düşük/orta/yüksek), 4) Önerilen aksiyon (ilaç, gübre, sulama vb.), "
            "5) Aciliyet seviyesi. Sadece JSON formatında dön: "
            '{"plant": "...", "disease": "...", "severity": "...", "action": "...", "urgency": "..."}'
        )

        # IT-32 — Integration Hub: doğrudan OpenAI/Gemini/Anthropic HTTP çağrısı
        # burada YOK, tek bir ai_provider.py üzerinden geçer (bkz. modül docstring'i).
        try:
            ai = get_ai_provider(ai_cfg.get("provider"), ai_cfg.get("api_key"), ai_cfg.get("model"))
            response = ai.generate_vision(system_prompt, "Bu bitki fotoğrafını analiz et.", img_b64)
        except ValueError as e:
            raise HTTPException(500, str(e))
        except Exception as e:
            raise HTTPException(500, f"AI hatası: {str(e)}")

        # AI'nin ham metin yanıtını yapısal alanlara ayrıştır (JSON bloğu
        # ```json ... ``` içinde gelebilir veya düz metinle karışık olabilir).
        # Ayrıştırma başarısız olursa alanlar boş kalır, ham metin (`result`)
        # her durumda korunur — hiçbir tüketici veri kaybetmez.
        parsed = {}
        try:
            m = re.search(r"\{[\s\S]*\}", response)
            if m:
                parsed = json.loads(m.group(0))
        except (json.JSONDecodeError, AttributeError):
            parsed = {}

        # Kayıt oluştur
        record = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "farmer_id": user.get("farmer_id"),
            "parcel_id": body.parcel_id,
            "result": response,                # ham AI metni (geriye dönük uyumluluk)
            "plant": parsed.get("plant"),
            "disease": parsed.get("disease"),
            "severity": parsed.get("severity"),
            "action": parsed.get("action"),
            "urgency": parsed.get("urgency"),
            "notes": body.notes,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.disease_detections.insert_one(record)
        record.pop("_id", None)
        
        return record

    @api_router.get("/ai/disease-history")
    async def disease_history(user=Depends(current_user)):
        """Geçmiş hastalık tespit kayıtları"""
        filt = {}
        if user.get("role") == "ciftci":
            filt["farmer_id"] = user.get("farmer_id")
        docs = await db.disease_detections.find(filt, {"_id": 0}).sort([("created_at", -1)]).limit(50).to_list(50)
        return docs

    # =====================================================================
    # AI COPILOT — Doğal dil ile parsel/çiftçi sorgusu
    # =====================================================================
    # Roadmap örneği: "Çumra'daki en riskli 20 parseli göster" veya
    # "Hasadı yaklaşan pancarları listele" gibi serbest metin sorguları.
    #
    # Nasıl çalışır: Kullanıcının doğal dil sorgusu + veritabanı şeması
    # AI servisine gönderilir, AI SADECE yapısal bir JSON filtre üretir
    # (serbestçe metin üretmez) — bu filtre MongoDB sorgusuna çevrilip
    # GERÇEK veritabanı üzerinde çalıştırılır. Böylece AI "halüsinasyon"
    # ile uydurma parsel listesi vermez, sadece gerçek veriyi filtreler.

    class CopilotQuery(BaseModel):
        query: str

    COPILOT_SCHEMA_PROMPT = """Sen bir tarım veritabanı sorgu asistanısın. Kullanıcının Türkçe
doğal dil sorgusunu, aşağıdaki alanlara sahip bir "parcels" koleksiyonu için
SADECE JSON formatında bir filtreye çevir. Başka hiçbir açıklama, markdown
veya metin ekleme — SADECE geçerli JSON döndür.

Alanlar:
- region_name: string (Konya, Eskişehir, Kayseri, Erzurum, Afyon, Çorum, Ankara, Yozgat)
- village: string (köy adı, biliyorsan)
- risk_level: "yesil" | "sari" | "turuncu" | "kirmizi" (turuncu+kirmizi = "riskli")
- min_ndvi / max_ndvi: 0.0-1.0 arası sayı
- crop: string (şimdilik hep "Şeker Pancarı")
- soil_type: "Killi" | "Kumlu" | "Tınlı" | "Kireçli" | "Killi-Tınlı"
- irrigation: "Damla" | "Yağmurlama" | "Karık" | "Yok"
- sort_by: "risk" | "ndvi" | "area_dekar" | "expected_yield_ton" (varsayılan: risk)
- sort_dir: "asc" | "desc" (riskli/düşük NDVI için "asc", en yüksek verim için "desc")
- limit: sayı (varsayılan 20, "en riskli 20" gibi ifadelerden çıkar)
- summary: kullanıcıya gösterilecek KISA (1 cümle) Türkçe özet — ne aradığını açıkla

Sadece anlamlı olan alanları JSON'a dahil et, gereksiz alanları hiç ekleme.
Örnek çıktı: {"region_name": "Konya", "risk_level": ["turuncu", "kirmizi"], "sort_by": "ndvi", "sort_dir": "asc", "limit": 20, "summary": "Konya bölgesindeki en riskli 20 parsel"}
"""

    async def _call_ai_text(ai_cfg: dict, system_prompt: str, user_text: str) -> str:
        """AI servisine metin isteği gönderir, ham metin yanıtını döner (sağlayıcı-agnostik).
        IT-32 — Integration Hub: gerçek çağrı ai_provider.py'ye taşındı, burada
        sadece config'i o modülün factory'sine geçirmekten ibaret."""
        try:
            ai = get_ai_provider(ai_cfg.get("provider"), ai_cfg.get("api_key"), ai_cfg.get("model"))
        except ValueError as e:
            raise HTTPException(500, str(e))
        return ai.generate_text(system_prompt, user_text)

    REGION_NAMES = ["Konya", "Eskişehir", "Kayseri", "Erzurum", "Afyon", "Çorum", "Ankara", "Yozgat"]

    def _rule_based_parse(query: str) -> dict:
        """
        AI servisi yapılandırılmamışken devreye giren basit anahtar-kelime
        tabanlı sorgu ayrıştırıcı. Roadmap'teki örnek sorguları ("Çumra'daki
        en riskli 20 parseli göster", "Hasadı yaklaşan pancarları listele")
        AI key olmadan da çalıştırabilmek için — Copilot'un temel deneyimi
        API key gerektirmeden de demo edilebilsin diye.
        """
        q = query.lower()
        spec: Dict[str, Any] = {}

        # Bölge / köy (Çumra → Konya bölgesi, bilinen bir eşleme)
        if "çumra" in q:
            spec["region_name"] = "Konya"
        else:
            for r in REGION_NAMES:
                if r.lower() in q:
                    spec["region_name"] = r
                    break

        # Risk / NDVI
        if any(w in q for w in ["riskli", "risk altında", "kırmızı", "turuncu", "acil"]):
            spec["risk_level"] = ["turuncu", "kirmizi"]
            spec["sort_by"] = "ndvi"
            spec["sort_dir"] = "asc"
        elif any(w in q for w in ["sağlıklı", "düşük risk", "iyi durumda"]):
            spec["risk_level"] = ["yesil"]

        # Hasat yaklaşan (basitçe: risk_level yeşil + expected_yield_ton'a göre sırala,
        # gerçek hasat tarihi mantığı plantings koleksiyonunda — burada basitleştirilmiş)
        if "hasa" in q or "hasat" in q:
            spec["sort_by"] = "expected_yield_ton"
            spec["sort_dir"] = "desc"

        # "en N" kalıbı — sayı yakala
        m = re.search(r"(\d+)\s*(parsel|tane|adet)?", q)
        if m:
            spec["limit"] = min(int(m.group(1)), 200)
        else:
            spec["limit"] = 20

        spec["summary"] = f"“{query}” sorgusu anahtar kelime eşleştirmeyle yorumlandı (AI servisi yapılandırılmamış)."
        return spec

    @api_router.post("/ai/copilot")
    async def ai_copilot(body: CopilotQuery, user=Depends(current_user), _feat=Depends(require_feature("ai"))):
        """
        Doğal dil sorgusunu yapısal filtreye çevirip GERÇEK parsel verisi
        üzerinde çalıştırır. AI sadece filtre üretir, veriyi uydurmaz.

        AI servisi (Ayarlar > Entegrasyonlar) yapılandırılmamışsa, basit
        anahtar-kelime eşleştirmeli bir fallback devreye girer — Copilot
        temel senaryolarda API key olmadan da çalışır.
        """
        from integrations import get_ai_service_config
        ai_cfg = await get_ai_service_config(db)

        if ai_cfg:
            raw = await _call_ai_text(ai_cfg, COPILOT_SCHEMA_PROMPT, body.query)
            # AI bazen JSON'u ```json ... ``` bloğu içinde döner — temizle
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            try:
                filt_spec = json.loads(cleaned.strip())
            except json.JSONDecodeError:
                # AI geçerli JSON üretemedi — fallback'e düş (sert hata vermek yerine)
                filt_spec = _rule_based_parse(body.query)
                filt_spec["summary"] = "AI yanıtı ayrıştırılamadı, anahtar kelime eşleştirmesine geçildi. " + filt_spec["summary"]
        else:
            filt_spec = _rule_based_parse(body.query)

        # AI'nin ürettiği filtreyi GÜVENLİ şekilde Query Engine'in (IT-08)
        # filter DSL'ine çevir — AI'nin ürettiği metni doğrudan sorguya
        # sokmuyoruz, sadece beklenen alan adlarını okuyup query_engine'in
        # whitelist'inden geçen koşullar inşa ediyoruz (IT-10 köprüsü —
        # elle Mongo sorgusu kurmak yerine execute_query() çağrılır, böylece
        # aynı whitelist/izin/Field-Level Security maskesi burada da geçerli).
        from query_engine import execute_query

        filters: List[Dict[str, Any]] = []
        if filt_spec.get("region_name"):
            region = await db.regions.find_one({"name": filt_spec["region_name"]}, {"_id": 0, "id": 1})
            if region:
                filters.append({"field": "region_id", "operator": "eq", "value": region["id"]})
        if filt_spec.get("village"):
            filters.append({"field": "village", "operator": "eq", "value": filt_spec["village"]})
        if filt_spec.get("risk_level"):
            rl = filt_spec["risk_level"]
            filters.append({"field": "risk_level", "operator": "in", "value": rl if isinstance(rl, list) else [rl]})
        if filt_spec.get("soil_type"):
            filters.append({"field": "soil_type", "operator": "eq", "value": filt_spec["soil_type"]})
        if filt_spec.get("irrigation"):
            filters.append({"field": "irrigation", "operator": "eq", "value": filt_spec["irrigation"]})
        if "min_ndvi" in filt_spec and "max_ndvi" in filt_spec:
            filters.append({"field": "ndvi_latest", "operator": "between",
                             "value": [float(filt_spec["min_ndvi"]), float(filt_spec["max_ndvi"])]})
        elif "min_ndvi" in filt_spec:
            filters.append({"field": "ndvi_latest", "operator": "gte", "value": float(filt_spec["min_ndvi"])})
        elif "max_ndvi" in filt_spec:
            filters.append({"field": "ndvi_latest", "operator": "lte", "value": float(filt_spec["max_ndvi"])})

        sort_field_map = {"risk": "ndvi_latest", "ndvi": "ndvi_latest", "area_dekar": "area_dekar",
                           "expected_yield_ton": "expected_yield_ton"}
        sort_field = sort_field_map.get(filt_spec.get("sort_by"), "ndvi_latest")
        sort_dir = "desc" if filt_spec.get("sort_dir") == "desc" else "asc"
        limit = min(int(filt_spec.get("limit", 20)), 200)

        result = await execute_query(db, "parcels", user, filters, logic="AND",
                                      sort_by=sort_field, sort_dir=sort_dir, page=1, page_size=limit)
        results = result["items"]

        return {
            "query": body.query,
            "interpreted_filter": filt_spec,
            "summary": filt_spec.get("summary", f"{len(results)} parsel bulundu."),
            "result_count": len(results),
            "parcels": results,
            "ai_powered": bool(ai_cfg),
        }

    # =====================================================================
    # AUDIT LOG — Sistem aktivite kaydı
    # =====================================================================
    
    # NOT: Audit log listeleme endpoint'i artık audit.py modülünde
    # (/api/audit/logs, register_audit_routes ile bağlanıyor). Buradaki eski
    # kopya kaldırıldı — tek kaynak (single source of truth) için.
    from audit import log_audit as _log_audit

    async def _log_action(action: str, user_id: str, details: dict = None, request=None):
        """
        Geriye dönük uyumluluk sarmalayıcısı: eski çağrı imzasını korur
        ama artık merkezi audit.log_audit()'i kullanır.
        """
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0}) or {"id": user_id}
        await _log_audit(db, user, action=action, entity="misc", new_value=details, request=request)

    # =====================================================================
    # SENTINEL HUB MOCK — Uydu/NDVI verisi
    # =====================================================================
    
    @api_router.get("/satellite/ndvi/{parcel_id}")
    async def get_ndvi_data(parcel_id: str, user=Depends(current_user)):
        """
        Parselin son uydu görüntüsünden NDVI değeri. (2026-07-11) Artık
        Integration Center'da Sentinel Hub GERÇEK/aktif ise gerçek veri
        döner; aksi halde (varsayılan) DemoSatelliteProvider mock veri
        döndürmeye devam eder — bkz. satellite_provider.py.
        """
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")

        geometry = parcel.get("geometry") or parcel.get("geojson")
        provider = await get_satellite_provider(db, "ndvi")
        try:
            time_series = provider.get_ndvi_time_series(parcel_id, geometry)
            data_source = f"CANLI ({provider.name})" if provider.name != "demo" else "MOCK (Sentinel Hub aktivasyonu sözleşme sonrası)"
        except Exception:
            # Gerçek sağlayıcı yapılandırılmış ama GEÇİCİ olarak ulaşılamıyor
            # (ör. ağ hatası, kota) — kullanıcının ekranı KIRILMAZ, sessizce
            # Demo'ya düşer (aynı davranış Integration Hub'ın diğer
            # provider'larındaki resilience yaklaşımıyla tutarlı).
            time_series = DemoSatelliteProvider().get_ndvi_time_series(parcel_id, geometry)
            data_source = "MOCK (gerçek sağlayıcıya şu an ulaşılamadı, geçici olarak demo veriye düşüldü)"
        latest = time_series[-1]
        health = ndvi_to_health(latest["ndvi"])

        return {
            "parcel_id": parcel_id,
            "parcel_code": parcel.get("parcel_code"),
            "area_dekar": parcel.get("area_dekar"),
            "latest_ndvi": latest["ndvi"],
            "latest_date": latest["date"],
            "health": health,
            "time_series": time_series,
            "anomalies": [
                {"date": "2025-07-15", "type": "Düşük NDVI sapması", "severity": "orta"}
            ] if latest["ndvi"] < 0.55 else [],
            "data_source": data_source,
        }

    class NdviSnapshotRequest(BaseModel):
        parcel_ids: List[str]
        date: str  # "YYYY-MM-DD" — get_satellite_provider()'ın ürettiği 10 sabit tarihten biri olmalı

    @api_router.post("/satellite/ndvi-snapshot")
    async def get_ndvi_snapshot(body: NdviSnapshotRequest, user=Depends(current_user)):
        """
        IT-17 — Mekânsal Zaman Makinesi: ÇOKLU parsel için TEK bir tarihteki
        NDVI/risk anlık görüntüsü. `/satellite/ndvi/{parcel_id}`'nin tersine
        (tek parsel, tam zaman serisi) burada çok sayıda parsel için SADECE
        istenen tarihteki değer hesaplanır — harita widget'ları/renkleri bu
        anlık görüntüyle "o günkü hale" geri sarılabilsin diye.

        Parsel varlığı/tenant sahipliği DOĞRULANMAZ tek tek (1000+ parsel
        için gereksiz sorgu) — hesaplama saf bir fonksiyon (parcel_id+tarih
        → NDVI), veritabanına hiç gitmez; TenantScopedDB zaten `/parcels`
        listesini tenant'a göre süzdüğü için frontend'e SADECE kendi
        gördüğü parcel_id'leri gönderme sorumluluğu düşer (aynı `/parcels/
        bulk-update`'in id listesi doğrulaması yapmamasıyla aynı emsal).
        """
        provider = await get_satellite_provider(db, "ndvi")
        # (2026-07-11) Sentinel Hub GERÇEK aktifse geometriye ihtiyacı var —
        # performans için TEK sorguda tüm parsellerin geometrisi toplu çekilir
        # (endpoint'in "1000+ parsel için tek tek sorgu yapma" ilkesi korunur,
        # sadece N ayrı sorgu yerine TEK toplu sorguya çevrildi).
        geometries_by_id = {}
        if provider.name != "demo":
            async for p in db.parcels.find({"id": {"$in": body.parcel_ids}}, {"_id": 0, "id": 1, "geometry": 1, "geojson": 1}):
                geometries_by_id[p["id"]] = p.get("geometry") or p.get("geojson")
        items = []
        for pid in body.parcel_ids:
            try:
                series = provider.get_ndvi_time_series(pid, geometries_by_id.get(pid))
            except Exception:
                series = DemoSatelliteProvider().get_ndvi_time_series(pid)
            match = next((s for s in series if s["date"] == body.date), None)
            if not match:
                continue
            risk_level, risk_label = ndvi_to_risk_level(match["ndvi"])
            items.append({
                "parcel_id": pid,
                "ndvi": match["ndvi"],
                "risk_level": risk_level,
                "risk_label": risk_label,
            })
        return {"date": body.date, "items": items}

    @api_router.get("/satellite/regional-overview")
    async def satellite_regional_overview(user=Depends(current_user)):
        """Bölge geneli NDVI özet — admin haritası için"""
        regions = await db.regions.find({}, {"_id": 0}).to_list(100)
        rnd = random.Random(2026)
        return [
            {
                "region_id": r["id"],
                "region_name": r["name"],
                "avg_ndvi": round(rnd.uniform(0.45, 0.78), 3),
                "scanned_parcels": rnd.randint(80, 250),
                "anomaly_count": rnd.randint(0, 12),
                "last_scan": "2025-09-15"
            } for r in regions
        ]

    # =====================================================================
    # IoT SENSÖRLER
    # =====================================================================

    @api_router.get("/iot/sensors")
    async def list_iot_sensors(status: str = None, region_id: str = None, parcel_id: str = None, user=Depends(current_user)):
        """IoT sensör listesi — durum/bölge/parsele göre filtrelenebilir"""
        q = {}
        if status:
            q["status"] = status
        if region_id:
            q["region_id"] = region_id
        if parcel_id:
            q["parcel_id"] = parcel_id
        docs = await db.iot_sensors.find(q, {"_id": 0}).sort("last_reading_at", -1).to_list(500)
        return docs

    @api_router.get("/iot/summary")
    async def iot_summary(user=Depends(current_user)):
        """Dashboard kartı için IoT özet: toplam/aktif sensör, son okuma"""
        total = await db.iot_sensors.count_documents({})
        active = await db.iot_sensors.count_documents({"status": "aktif"})
        low_battery = await db.iot_sensors.count_documents({"battery_pct": {"$lt": 20}})
        last = await db.iot_sensors.find({}, {"_id": 0}).sort("last_reading_at", -1).limit(1).to_list(1)
        return {
            "total_sensors": total,
            "active_sensors": active,
            "low_battery_sensors": low_battery,
            "last_reading_at": last[0]["last_reading_at"] if last else None,
        }

    # =====================================================================
    # DRONE GÖREVLERİ
    # =====================================================================

    @api_router.get("/drone/missions")
    async def list_drone_missions(finding_type: str = None, parcel_id: str = None, user=Depends(current_user)):
        """Drone görev listesi — bulgu tipine/parsele göre filtrelenebilir"""
        q = {}
        if finding_type:
            q["finding_type"] = finding_type
        if parcel_id:
            q["parcel_id"] = parcel_id
        docs = await db.drone_missions.find(q, {"_id": 0}).sort("flight_date", -1).to_list(200)
        return docs

    @api_router.get("/drone/summary")
    async def drone_summary(user=Depends(current_user)):
        """Dashboard kartı için drone özet"""
        total = await db.drone_missions.count_documents({})
        with_findings = await db.drone_missions.count_documents({"finding_type": {"$ne": "genel_tarama"}})
        last = await db.drone_missions.find({}, {"_id": 0}).sort("flight_date", -1).limit(1).to_list(1)
        return {
            "total_missions": total,
            "missions_with_findings": with_findings,
            "last_flight_date": last[0]["flight_date"] if last else None,
        }
    
    # =====================================================================
    # E-FATURA / İRSALİYE / KANTAR
    # =====================================================================
    
    @api_router.get("/e-belge/invoices")
    async def list_einvoices(user=Depends(current_user)):
        """E-fatura listesi (demo data)"""
        docs = await db.einvoices.find({}, {"_id": 0}).sort([("date", -1)]).to_list(200)
        return docs

    @api_router.get("/e-belge/irsaliyeler")
    async def list_irsaliyeler(user=Depends(current_user)):
        """E-irsaliye listesi"""
        docs = await db.irsaliyeler.find({}, {"_id": 0}).sort([("date", -1)]).to_list(200)
        return docs
    
    @api_router.get("/kantar/records")
    async def list_kantar_records(user=Depends(current_user)):
        """Kantar tartı kayıtları"""
        docs = await db.kantar_records.find({}, {"_id": 0}).sort([("weighing_at", -1)]).to_list(300)
        return docs

    # =====================================================================
    # MÜSTAHSİL MAKBUZU PDF
    # =====================================================================
    
    @api_router.get("/musthsil/{farmer_id}/{season}")
    async def generate_mustahsil_pdf(farmer_id: str, season: int, user=Depends(current_user)):
        """Çiftçi için müstahsil makbuzu PDF üret"""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            raise HTTPException(500, "PDF kütüphanesi yüklü değil")
        
        farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        
        yields = await db.yields.find({"farmer_id": farmer_id, "season": season}, {"_id": 0}).to_list(100)
        finance = await db.finance.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
        total_ton = sum(y.get("actual_ton", 0) for y in yields)
        unit_price = 1800                                    # TL/ton
        gross = total_ton * unit_price
        kesinti = gross * 0.04                              # Stopaj %4
        net = gross - kesinti
        
        # PDF oluştur (basit format — Türk Şeker'in örnek müstahsil makbuzu)
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, "MUSTAHSIL MAKBUZU")
        c.setFont("Helvetica", 10)
        c.drawString(50, 780, f"Sezon: {season}    Belge No: MM-{season}-{farmer.get('member_no', '')}")
        c.drawString(50, 765, f"Düzenleme: {datetime.now().strftime('%d.%m.%Y')}")
        
        c.line(50, 755, 545, 755)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, 740, "USTAHSIL (CIFTCI):")
        c.setFont("Helvetica", 10)
        c.drawString(50, 725, f"Ad Soyad: {farmer.get('full_name')}")
        c.drawString(50, 710, f"Uye No: {farmer.get('member_no')}")
        c.drawString(50, 695, f"TC: {farmer.get('tc_no')}")
        c.drawString(50, 680, f"Koy: {farmer.get('village')}")
        c.drawString(50, 665, f"IBAN: {farmer.get('iban', '-')}")
        
        c.line(50, 655, 545, 655)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, 640, "URUN BILGISI:")
        c.setFont("Helvetica", 10)
        c.drawString(50, 625, f"Urun: Seker Pancari")
        c.drawString(50, 610, f"Toplam Miktar: {total_ton:.2f} TON")
        c.drawString(50, 595, f"Birim Fiyat: {unit_price:,.2f} TL/TON")
        
        c.line(50, 585, 545, 585)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, 570, "HESAPLAMA:")
        c.setFont("Helvetica", 10)
        c.drawString(50, 555, f"Brut Tutar: {gross:,.2f} TL")
        c.drawString(50, 540, f"Stopaj (%4): -{kesinti:,.2f} TL")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 520, f"NET ODENECEK: {net:,.2f} TL")
        
        c.setFont("Helvetica", 8)
        c.drawString(50, 100, "Bu belge dijital olarak uretilmistir. Demo amaclidir.")
        c.drawString(50, 88, f"Belge ID: {uuid.uuid4().hex[:12].upper()}")
        c.save()
        
        buffer.seek(0)
        return Response(
            content=buffer.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="mustahsil-{farmer.get("member_no")}-{season}.pdf"'}
        )
    
    # NOT: SMS/Email/Planet Labs/AI servis entegrasyon ayarları artık
    # merkezi "Ayarlar > Entegrasyonlar" modülünde: bkz. integrations.py
    # (/api/integrations/* endpoint'leri). Eski /api/settings/integrations
    # uç noktaları kaldırıldı, karışıklığı önlemek için tek kaynak korunuyor.

    # =====================================================================
    # SAHA ZİYARET RAPORU (Mobil PWA)
    # =====================================================================
    
    class FieldVisitCreate(BaseModel):
        parcel_id: str
        farmer_id: str
        notes: str
        gps_lat: float
        gps_lng: float
        photo_base64: Optional[str] = None
        observation_type: str                                # genel/hastalık/sulama/zararlı
        client_id: Optional[str] = None                       # Offline kuyruktan tekrar deneme (dedup) için
        client_created_at: Optional[str] = None                # Cihazda oluşturulma zamanı (offline iken)
        analyze_with_ai: bool = False                          # Fotoğraf varsa otomatik AI analizi iste

    @api_router.post("/field/visits")
    async def create_field_visit(body: FieldVisitCreate, request: Request, user=Depends(current_user)):
        """
        Saha mühendisi ziyaret raporu kaydeder (mobil PWA'dan).

        Offline-first destek: PWA, internet yokken raporu kendi IndexedDB
        kuyruğunda tutar ve bağlantı geldiğinde `client_id` ile gönderir.
        Aynı `client_id` ile tekrar gönderim (retry) yapılırsa DUPLICATE
        kayıt oluşturulmaz — mevcut kayıt döndürülür.
        """
        if body.client_id:
            existing = await db.field_visits.find_one(
                {"client_id": body.client_id, "engineer_id": user["id"]}, {"_id": 0, "photo_base64": 0}
            )
            if existing:
                return {**existing, "deduplicated": True}

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["engineer_id"] = user["id"]
        doc["engineer_name"] = user.get("full_name")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["ai_analysis"] = None

        # Fotoğraf varsa ve istenmişse AI analizi otomatik çalıştır
        if body.photo_base64 and body.analyze_with_ai:
            try:
                from integrations import get_ai_service_config
                ai_cfg = await get_ai_service_config(db)
                if ai_cfg:
                    fake_req = DiseaseDetectReq(image_base64=body.photo_base64, parcel_id=body.parcel_id)
                    result = await ai_disease_detect(fake_req, user=user)
                    doc["ai_analysis"] = result
            except Exception as e:
                doc["ai_analysis"] = {"error": f"AI analizi başarısız: {e}"}

        await db.field_visits.insert_one(doc)
        doc.pop("_id", None)
        await _log_action("field.visit.created", user["id"], {"parcel_id": body.parcel_id}, request=request)
        return doc

    @api_router.get("/field/visits")
    async def list_field_visits(farmer_id: Optional[str] = None, limit: int = 100, user=Depends(current_user)):
        """Ziyaret listesi"""
        filt = {}
        if farmer_id: filt["farmer_id"] = farmer_id
        docs = await db.field_visits.find(filt, {"_id": 0, "photo_base64": 0}).sort([("created_at", -1)]).limit(limit).to_list(limit)
        return docs

    # =====================================================================
    # ÇİFTÇİ PROFİL GÜNCELLEME
    # =====================================================================
    
    class FarmerProfileUpdate(BaseModel):
        phone: Optional[str] = None
        email: Optional[str] = None
        iban: Optional[str] = None
        village: Optional[str] = None
    
    @api_router.put("/farmer/my-profile")
    async def update_my_profile(body: FarmerProfileUpdate, user=Depends(current_user)):
        """Çiftçi kendi profil bilgisini günceller"""
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi kendi profilini güncelleyebilir")
        
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        
        await db.farmers.update_one({"id": user["farmer_id"]}, {"$set": updates})
        await _log_action("profile.updated", user["id"], updates)
        
        updated = await db.farmers.find_one({"id": user["farmer_id"]}, {"_id": 0})
        return updated
    
    # =====================================================================
    # EK SEED — E-fatura, İrsaliye, Kantar, Audit, Field Visits
    # =====================================================================
    
    @api_router.post("/admin/seed-extras")
    async def seed_extras(user=Depends(current_user)):
        """Ek demo verileri yükle (e-fatura, irsaliye, kantar, audit, ziyaret)

        P0 güvenlik düzeltmesi: bu uç önceden kimlik doğrulaması
        gerektirmiyordu. Artık giriş yapmış bir yönetici (is_admin) ve
        ALLOW_DATA_SEEDING=true (üretimde varsayılan kapalı) gerektirir.
        """
        if not ALLOW_DATA_SEEDING:
            raise HTTPException(403, "Demo veri yükleme bu ortamda kapalı (ALLOW_DATA_SEEDING=false)")
        if not is_admin(user) and user.get("role") != "platform_admin":
            raise HTTPException(403, "Bu işlem için yönetici yetkisi gerekir")
        # server.py'deki /admin/seed ile aynı bootstrap mantığı: platform_admin
        # tenant_id taşımadığı için "default" tenant'a yazılır.
        reset_token = None
        if current_tenant_id.get() is None:
            default_tenant = await db.tenants.find_one({"slug": "default"}, {"_id": 0})
            if default_tenant:
                reset_token = current_tenant_id.set(default_tenant["id"])
            # default_tenant hiç yoksa (yani /admin/seed hiç çalıştırılmamışsa)
            # context None kalır — aşağıdaki sorgular zaten boş dönecektir.

        try:
            return await _run_seed_extras()
        finally:
            if reset_token is not None:
                current_tenant_id.reset(reset_token)

    async def _run_seed_extras():
        if await db.einvoices.count_documents({}) > 0:
            return {"status": "already_seeded_extras"}
        
        random.seed(99)
        farmers = await db.farmers.find({}, {"_id": 0}).to_list(500)
        parcels = await db.parcels.find({}, {"_id": 0}).to_list(500)
        admin = await db.users.find_one({"role": "super_admin"})
        
        # E-FATURALAR (kooperatif → çiftçiye gübre/tohum faturası)
        einvoices = []
        for _ in range(120):
            f = random.choice(farmers)
            net = round(random.uniform(2500, 45000), 2)
            kdv = round(net * 0.20, 2)
            einvoices.append({
                "id": str(uuid.uuid4()),
                "invoice_no": f"EFT-2025-{random.randint(100000, 999999)}",
                "type": random.choice(["tohum", "gübre", "ilaç", "kombine"]),
                "date": f"2025-{random.randint(1, 11):02d}-{random.randint(1, 28):02d}",
                "farmer_id": f["id"],
                "farmer_name": f["full_name"],
                "member_no": f["member_no"],
                "net_amount": net,
                "kdv": kdv,
                "total": net + kdv,
                "status": random.choice(["onaylandı", "onaylandı", "onaylandı", "beklemede"]),
                "uuid_no": uuid.uuid4().hex[:32].upper(),
                "gib_status": "gönderildi"
            })
        await db.einvoices.insert_many(einvoices)
        
        # E-İRSALİYE (sevkiyat)
        irsaliyeler = []
        for _ in range(80):
            f = random.choice(farmers)
            irsaliyeler.append({
                "id": str(uuid.uuid4()),
                "irsaliye_no": f"İRS-2025-{random.randint(100000, 999999)}",
                "date": f"2025-{random.randint(3, 11):02d}-{random.randint(1, 28):02d}",
                "farmer_id": f["id"],
                "farmer_name": f["full_name"],
                "member_no": f["member_no"],
                "product": random.choice(["Şeker Pancarı Tohumu", "DAP Gübre 50kg", "Üre Gübre 50kg", "İlaç-Herbisit", "Mazot"]),
                "quantity": random.randint(5, 200),
                "unit": random.choice(["kg", "lt", "çuval"]),
                "truck_plate": f"{random.choice(['06', '34', '35', '42', '38'])} {random.choice(['ABC', 'XYZ', 'KMN'])} {random.randint(100, 999)}",
                "status": random.choice(["taşımada", "teslim edildi", "teslim edildi"])
            })
        await db.irsaliyeler.insert_many(irsaliyeler)
        
        # KANTAR KAYITLARI (hasat dönemi tartı kayıtları)
        kantar = []
        for _ in range(180):
            f = random.choice(farmers)
            brut = round(random.uniform(18, 32), 2)         # ton
            dara = round(random.uniform(8, 12), 2)
            kantar.append({
                "id": str(uuid.uuid4()),
                "fis_no": f"K-2025-{random.randint(10000, 99999)}",
                "weighing_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 60), hours=random.randint(0, 23))).isoformat(),
                "farmer_id": f["id"],
                "farmer_name": f["full_name"],
                "member_no": f["member_no"],
                "truck_plate": f"{random.choice(['06', '34', '35', '42', '38'])} {random.choice(['ABC', 'XYZ', 'KMN'])} {random.randint(100, 999)}",
                "brut_ton": brut,
                "dara_ton": dara,
                "net_ton": round(brut - dara, 2),
                "polar_oran": round(random.uniform(14.5, 18.5), 2),
                "fire_pct": round(random.uniform(2, 8), 2),
                "kalite": random.choice(["A", "A", "B", "B", "C"]),
                "kantar_no": random.choice(["K-1", "K-2", "K-3"]),
                "operator": random.choice(["Hüseyin Çelik", "Mustafa Demir", "Ali Yılmaz"])
            })
        await db.kantar_records.insert_many(kantar)
        
        # AUDIT LOG (geçmiş aktivite)
        actions = ["login", "farmer.created", "parcel.updated", "contract.signed",
                   "irrigation.added", "report.exported", "user.role_changed",
                   "settings.updated", "data.exported", "logout"]
        audit = []
        users = await db.users.find({}, {"_id": 0}).to_list(50)
        for _ in range(200):
            u = random.choice(users)
            audit.append({
                "id": str(uuid.uuid4()),
                "action": random.choice(actions),
                "user_id": u["id"],
                "user_email": u["email"],
                "user_role": u["role"],
                "details": {"info": f"İşlem detayı #{random.randint(1000, 9999)}"},
                "ip": f"10.0.{random.randint(0, 5)}.{random.randint(1, 254)}",
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 720))).isoformat()
            })
        await db.audit_logs.insert_many(audit)
        
        # SAHA ZİYARET KAYITLARI
        visits = []
        engineer = await db.users.find_one({"role": "ziraat_muhendisi"})
        if engineer:
            for _ in range(35):
                p = random.choice(parcels)
                visits.append({
                    "id": str(uuid.uuid4()),
                    "parcel_id": p["id"],
                    "farmer_id": p["farmer_id"],
                    "engineer_id": engineer["id"],
                    "engineer_name": engineer.get("full_name", "Ziraat Müh."),
                    "notes": random.choice([
                        "Genel kontrol - bitki gelişimi iyi.",
                        "Yaprak sararması gözlemlendi. Azot eksikliği ihtimali.",
                        "Damla sulama hattında tıkanma - operatör bilgilendirildi.",
                        "Tarla kenarında yabancı ot — herbisit önerildi.",
                        "Hasat hazırlığı tamam. Önümüzdeki hafta kantar randevusu."
                    ]),
                    "gps_lat": round(39.0 + random.uniform(-1.5, 1.5), 6),
                    "gps_lng": round(33.0 + random.uniform(-3, 4), 6),
                    "observation_type": random.choice(["genel", "hastalık", "sulama", "zararlı"]),
                    "created_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30))).isoformat()
                })
            await db.field_visits.insert_many(visits)
        
        return {
            "status": "extras_seeded",
            "counts": {
                "einvoices": len(einvoices),
                "irsaliyeler": len(irsaliyeler),
                "kantar_records": len(kantar),
                "audit_logs": len(audit),
                "field_visits": len(visits)
            }
        }
