"""
=====================================================================
Toprax — Dashboard + Bildirimler + Bölgeler + Lojistik randevu + Karne
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
from cache import cache_get_or_set


def register_dashboard_routes(api_router, db, current_user, require_feature):
    @api_router.get("/dashboard/overview")
    async def dashboard_overview(user=Depends(current_user)):
        """
        Admin dashboard verileri:
        - KPI kartları (toplam çiftçi, parsel, alan, sözleşme, hasat)
        - 5 yıllık trend grafiği
        - Bölge bazlı performans
        - Çiftçi karne dağılımı
    
        Bu endpoint herhangi bir veri ekleme/silme sonrası
        otomatik güncel rakamları dönecektir (canlı veri hissi).
        """
        # Temel sayımlar
        farmers_total = await db.farmers.count_documents({})
        parcels_total = await db.parcels.count_documents({})
        contracts_active = await db.contracts.count_documents({"status": "imzalı"})
    
        # Tüm parsel verilerini çek (alan hesabı için)
        parcels = await db.parcels.find({}, {"_id": 0}).to_list(10000)
        total_area = sum(p.get("area_dekar", 0) for p in parcels)
    
        # Verim verisi (beklenen vs gerçekleşen)
        yields = await db.yields.find({}, {"_id": 0}).to_list(10000)
        expected_ton = sum(y.get("expected_ton", 0) for y in yields)
        actual_ton = sum(y.get("actual_ton", 0) for y in yields)
    
        # Bölge bazlı istatistik
        regions = await db.regions.find({}, {"_id": 0}).to_list(100)
        region_stats = []
        for r in regions:
            r_parcels = [p for p in parcels if p.get("region_id") == r["id"]]
            r_yields = [y for y in yields if y.get("region_id") == r["id"]]
            r_area = sum(p.get("area_dekar", 0) for p in r_parcels)
            r_ton = sum(y.get("actual_ton", 0) for y in r_yields)
            region_stats.append({
                "name": r["name"],
                "farmers": await db.farmers.count_documents({"region_id": r["id"]}),
                "area_dekar": r_area,
                "yield_ton": r_ton,
                "avg_yield_per_dekar": r_ton / max(r_area, 1)    # 0'a bölme koruması
            })
    
        # 5 yıllık verim trendi
        trend = []
        for yr in range(2021, 2026):
            y_year = [y for y in yields if y.get("season") == yr]
            trend.append({
                "year": yr,
                "ton": sum(yy.get("actual_ton", 0) for yy in y_year),
                "expected": sum(yy.get("expected_ton", 0) for yy in y_year)
            })
    
        # Karne dağılımı
        farmers = await db.farmers.find({}, {"_id": 0}).to_list(10000)
        karne_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
        for f in farmers:
            s = f.get("karne_score", "C")
            karne_dist[s] = karne_dist.get(s, 0) + 1

        # ============ YENİ KPI'LAR (Sprint 2 — GIS/IoT/Drone) ============
        # Roadmap dashboard kartları: Riskli Parsel, IoT Sensörü, Drone Görevi,
        # Son Uydu Analizi, Son IoT Verisi. Hepsi GERÇEK veriden hesaplanır.
        risky_parcels_count = sum(1 for p in parcels if p.get("risk_level") in ("turuncu", "kirmizi"))
        avg_ndvi = round(sum(p.get("ndvi_latest", 0) for p in parcels) / max(len(parcels), 1), 3)

        iot_total = await db.iot_sensors.count_documents({})
        iot_active = await db.iot_sensors.count_documents({"status": "aktif"})
        iot_last = await db.iot_sensors.find({}, {"_id": 0}).sort("last_reading_at", -1).limit(1).to_list(1)

        drone_total = await db.drone_missions.count_documents({})
        drone_last = await db.drone_missions.find({}, {"_id": 0}).sort("flight_date", -1).limit(1).to_list(1)

        last_satellite_scan = max((p.get("last_satellite_scan") for p in parcels if p.get("last_satellite_scan")), default=None)

        # ============ EKİLİ / SÖKÜM DURUMU (#2 — uydu+manuel, crop_status.py) ============
        active_parcels = [p for p in parcels if p.get("is_active") is not False]
        def _plantable(p):
            e = p.get("ekilebilir_alan_dekar")
            return e if isinstance(e, (int, float)) and e else (p.get("area_dekar") or 0)
        ekili_count = sum(1 for p in active_parcels if p.get("ekim_durumu") == "ekili")
        sokulen_count = sum(1 for p in active_parcels if p.get("ekim_durumu") == "sokuldu")
        ekili_degil_count = sum(1 for p in active_parcels if p.get("ekim_durumu") not in ("ekili", "sokuldu"))
        sokulen_alan = sum(_plantable(p) for p in active_parcels if p.get("ekim_durumu") == "sokuldu")
        kalan_alan = sum(_plantable(p) for p in active_parcels if p.get("ekim_durumu") == "ekili")

        return {
            "kpis": {
                "farmers_total": farmers_total,
                "parcels_total": parcels_total,
                "active_contracts": contracts_active,
                "total_area_dekar": round(total_area, 1),
                "expected_ton": round(expected_ton, 1),
                "actual_ton": round(actual_ton, 1),
                "yield_completion_pct": round(actual_ton / max(expected_ton, 1) * 100, 1),
                # --- Sprint 2 eklentileri ---
                "risky_parcels": risky_parcels_count,
                "avg_ndvi": avg_ndvi,
                "iot_sensors_total": iot_total,
                "iot_sensors_active": iot_active,
                "iot_last_reading_at": iot_last[0]["last_reading_at"] if iot_last else None,
                "drone_missions_total": drone_total,
                "drone_last_flight_at": drone_last[0]["flight_date"] if drone_last else None,
                "last_satellite_scan": last_satellite_scan,
                # --- #2 Ekili / Söküm durumu (uydu + manuel) ---
                "ekili_parcels": ekili_count,
                "sokulen_parcels": sokulen_count,
                "ekili_degil_parcels": ekili_degil_count,
                "sokulen_alan_dekar": round(sokulen_alan, 1),
                "kalan_alan_dekar": round(kalan_alan, 1),
            },
            "regions": region_stats,
            "yield_trend": trend,
            "karne_distribution": karne_dist
        }



    @api_router.get("/regions")
    async def list_regions(user=Depends(current_user)):
        """IT-33 — lookup verisi (nadiren değişir) cache.py üzerinden okunur
        (bkz. cache.py docstring'i — arayüz Redis'e geçilirse aynı kalır)."""
        from cache import cache_get_or_set
        return await cache_get_or_set("regions:list", 60, lambda: db.regions.find({}, {"_id": 0}).to_list(100))


    @api_router.get("/logistics/appointments")
    async def list_appointments(farmer_id: Optional[str] = None, user=Depends(current_user),
                                 _feat=Depends(require_feature("logistics"))):
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
        if farmer_id: filt["farmer_id"] = farmer_id
        return await db.appointments.find(filt, {"_id": 0}).sort([("scheduled_at", 1)]).to_list(500)


    @api_router.get("/notifications")
    async def list_notifications(user=Depends(current_user)):
        return await db.notifications.find({}, {"_id": 0}).sort([("created_at", -1)]).to_list(200)


    @api_router.get("/notifications/unread-count")
    async def unread_notification_count(user=Depends(current_user)):
        """IT-12 — Bildirim çekmecesindeki zil rozeti için. Bildirimler tenant
        genelidir (kullanıcı bazlı gelen kutusu değil — mevcut veri modeliyle
        tutarlı), yani bu sayı tüm kooperatif için ortaktır."""
        count = await db.notifications.count_documents({"status": {"$ne": "okundu"}})
        return {"count": count}


    @api_router.put("/notifications/{notification_id}/read")
    async def mark_notification_read(notification_id: str, user=Depends(current_user)):
        old = await db.notifications.find_one({"id": notification_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Bildirim bulunamadı")
        await db.notifications.update_one({"id": notification_id}, {"$set": {"status": "okundu"}})
        return {"status": "ok"}


    @api_router.post("/notifications/mark-all-read")
    async def mark_all_notifications_read(user=Depends(current_user)):
        result = await db.notifications.update_many({"status": {"$ne": "okundu"}}, {"$set": {"status": "okundu"}})
        return {"status": "ok", "updated": result.modified_count}


    # SON HAL #8 — bildirim çekmecesinde (WorkspaceDrawer) tıklanan bildirimin
    # yönlendirileceği detay sayfası (NotificationDetail.jsx) için. BİLİNÇLİ
    # OLARAK yukarıdaki /notifications/unread-count ve /notifications/mark-all-
    # read'DEN SONRA tanımlı — route sırası tuzağı (bkz. CLAUDE.md
    # "/parcels/bulk-update" notu): {notification_id} önce tanımlansaydı bu iki
    # sabit path'i id sanırdı. Bildirimler tenant genelidir (unread-count ile
    # AYNI varsayım) — sahiplik kontrolü yok.
    @api_router.get("/notifications/{notification_id}")
    async def get_notification(notification_id: str, user=Depends(current_user)):
        doc = await db.notifications.find_one({"id": notification_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Bildirim bulunamadı")
        return doc


    @api_router.get("/karne/top")
    async def karne_top(limit: int = 10, user=Depends(current_user), _feat=Depends(require_feature("reports"))):
        return await db.farmers.find({}, {"_id": 0}).sort([("karne_points", -1)]).limit(limit).to_list(limit)


    @api_router.get("/karne/bottom")
    async def karne_bottom(limit: int = 10, user=Depends(current_user)):
        return await db.farmers.find({}, {"_id": 0}).sort([("karne_points", 1)]).limit(limit).to_list(limit)



