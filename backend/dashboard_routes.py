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
import re
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
from cache import cache_get_or_set


def register_dashboard_routes(api_router, db, current_user, require_feature):
    @api_router.get("/dashboard/overview")
    async def dashboard_overview(season: Optional[int] = None, user=Depends(current_user)):
        """
        Admin dashboard verileri:
        - KPI kartları (toplam çiftçi, parsel, alan, sözleşme, hasat)
        - 5 yıllık trend grafiği
        - Bölge bazlı performans
        - Çiftçi karne dağılımı
    
        Bu endpoint herhangi bir veri ekleme/silme sonrası
        otomatik güncel rakamları dönecektir (canlı veri hissi).
        """
        # ================= SEZON BAĞLAMI (2026-08-19 düzeltmesi) =================
        # ÖNCEDEN: sözleşme ve verim toplamları TÜM SEZONLARI kapsıyordu.
        # Sonuç canlıda "23.808 aktif sözleşme" (241 çiftçiye!) ve
        # "%817,5 gerçekleşme" gibi anlamsız değerlerdi — çünkü `actual_ton`
        # 5 sezonun toplamı, `expected_ton` tek sezonluk hedefti.
        # Artık her şey TEK bir sezona göre hesaplanır.
        season = season or date.today().year

        # Temel sayımlar
        farmers_total = await db.farmers.count_documents({})
        parcels_total = await db.parcels.count_documents({})
        contracts_active = await db.contracts.count_documents({"season": season, "status": "imzalı"})

        # Tüm parsel verilerini çek (alan hesabı için)
        parcels = await db.parcels.find({}, {"_id": 0}).to_list(10000)
        total_area = sum(p.get("area_dekar", 0) for p in parcels)

        # --- Verim: SEZONA süzülür ---
        yields = await db.yields.find({"season": season}, {"_id": 0}).to_list(10000)
        actual_ton = sum(y.get("actual_ton", 0) for y in yields)

        # HEDEF tonaj sözleşmelerin kotasından okunur, `yields.expected_ton`'dan
        # DEĞİL: demo seed'inde expected_ton parsel büyüklüğünden bağımsız sabit
        # bir değer taşıyor (ortalama 39 t) ve gerçekleşenle (ortalama ~210 t)
        # kıyaslanınca %500'lük saçma oranlar üretiyor. `contracts.kota_ton`
        # fabrikanın gerçek hedefidir (entitlement.py de kotayı oradan okur).
        season_contracts = await db.contracts.find(
            {"season": season}, {"_id": 0, "kota_ton": 1}).to_list(30000)
        expected_ton = sum(c.get("kota_ton") or 0 for c in season_contracts)
        if not expected_ton:                       # kota girilmemişse eski kaynağa düş
            expected_ton = sum(y.get("expected_ton", 0) for y in yields)

        # --- Bölge bazlı istatistik ---
        # Toplama ZATEN region_id ile yapılıyordu; tablonun boş görünmesinin
        # sebebi `regions` koleksiyonunda parsel bağlanmamış (il adı taşıyan)
        # kayıtların da bulunması ve hepsinin 0 ile listelenmesiydi. Artık
        # VERİSİ OLAN bölgeler döner ve büyükten küçüğe sıralanır — boş
        # satırlar grafiği anlamsız kılmaz.
        regions = await db.regions.find({}, {"_id": 0}).to_list(100)
        region_stats = []
        for r in regions:
            r_parcels = [p for p in parcels if p.get("region_id") == r["id"]]
            r_yields = [y for y in yields if y.get("region_id") == r["id"]]
            r_area = sum(p.get("area_dekar", 0) for p in r_parcels)
            r_ton = sum(y.get("actual_ton", 0) for y in r_yields)
            r_farmers = await db.farmers.count_documents({"region_id": r["id"]})
            if not (r_parcels or r_farmers):
                continue                            # hiç verisi yok — listeleme
            # `yields` bölge taşımıyor (seed'de region_id yok); bölgenin verimi
            # o bölgedeki PARSELLERİN verim kayıtlarından toplanır.
            if not r_yields:
                pids = {p["id"] for p in r_parcels}
                r_ton = sum(y.get("actual_ton", 0) for y in yields
                            if y.get("parcel_id") in pids)
            region_stats.append({
                "name": r["name"],
                "farmers": r_farmers,
                "area_dekar": round(r_area, 1),
                "yield_ton": round(r_ton, 1),
                "avg_yield_per_dekar": round(r_ton / max(r_area, 1), 2),
            })
        region_stats.sort(key=lambda x: x["area_dekar"], reverse=True)
    
        # 5 yıllık verim trendi — SEZONDAN GERİYE doğru (sabit 2021-2025 değil;
        # sistem 2026'dayken grafiğin cari yılı hiç göstermemesi kusurdu).
        # Trend TÜM sezonları gezdiği için ayrı bir sorgu gerekiyor: yukarıdaki
        # `yields` artık tek sezona süzülü.
        all_yields = await db.yields.find({}, {"_id": 0, "season": 1, "actual_ton": 1,
                                               "expected_ton": 1}).to_list(50000)
        trend = []
        for yr in range(season - 4, season + 1):
            y_year = [y for y in all_yields if y.get("season") == yr]
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

        # --- Uydu KPI'ları (2026-08-19 düzeltmesi) ---
        # ÖNCEDEN: `parcels.ndvi_latest` toplanıyordu ama o alan HİÇBİR parselde
        # dolu değil (canlıda 0/5053) — bu yüzden dashboard hep "Ortalama NDVI 0"
        # ve "Son Uydu Analizi —" gösteriyordu. Gerçek uydu verisi
        # `remote_sensing_statistics` koleksiyonunda (polar_engine.py de oradan
        # okuyor). Artık ORADAN hesaplanıyor; `ndvi_latest` yine de yedek kalır.
        rs_stats = await db.remote_sensing_statistics.find(
            {}, {"_id": 0, "parcel_id": 1, "series": 1, "created_at": 1}).to_list(5000)
        latest_ndvi_vals, rs_dates = [], []
        for st in rs_stats:
            if st.get("created_at"):
                rs_dates.append(st["created_at"])
            pts = [p for p in (st.get("series") or []) if p.get("ndvi") is not None]
            if pts:
                pts.sort(key=lambda p: p.get("date") or "")
                latest_ndvi_vals.append(pts[-1]["ndvi"])
        if not latest_ndvi_vals:                       # yedek: eski alan
            latest_ndvi_vals = [p["ndvi_latest"] for p in parcels
                                if isinstance(p.get("ndvi_latest"), (int, float)) and p["ndvi_latest"]]
        avg_ndvi = round(sum(latest_ndvi_vals) / len(latest_ndvi_vals), 3) if latest_ndvi_vals else 0
        # Kaç parselin gerçekten uydu ölçümü var — "ortalama NDVI" tek başına
        # yanıltıcı (5053 parselin 12'sinden hesaplanmış olabilir).
        ndvi_coverage = len(latest_ndvi_vals)

        iot_total = await db.iot_sensors.count_documents({})
        iot_active = await db.iot_sensors.count_documents({"status": "aktif"})
        iot_last = await db.iot_sensors.find({}, {"_id": 0}).sort("last_reading_at", -1).limit(1).to_list(1)

        drone_total = await db.drone_missions.count_documents({})
        drone_last = await db.drone_missions.find({}, {"_id": 0}).sort("flight_date", -1).limit(1).to_list(1)

        last_satellite_scan = max(
            (p.get("last_satellite_scan") for p in parcels if p.get("last_satellite_scan")),
            default=None)
        if not last_satellite_scan and rs_dates:
            last_satellite_scan = max(rs_dates)

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
        # 2026-08-19 — alan muhasebesi açığı kapatıldı. ÖNCEDEN yalnızca
        # "sökülen" ve "kalan (ekili)" dönülüyordu; ekili OLMAYAN parsellerin
        # alanı hiçbir kalemde görünmediği için canlıda
        # 2.421,9 + 121.500,5 = 123.922,4 ≠ 179.230,4 (55.308 dekar açık) oluyordu.
        # Ayrıca `total_area_dekar` `area_dekar`, bu kalemler `ekilebilir_alan`
        # topluyordu — elma-armut. Artık üç kalem de AYNI ölçüyle hesaplanıyor
        # ve toplamları ayrıca `ekilebilir_alan_toplam` ile karşılaştırılabiliyor.
        ekili_degil_alan = sum(_plantable(p) for p in active_parcels
                               if p.get("ekim_durumu") not in ("ekili", "sokuldu"))
        ekilebilir_toplam = sum(_plantable(p) for p in active_parcels)

        return {
            "season": season,
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
                "ndvi_coverage_parcels": ndvi_coverage,
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
                "ekili_degil_alan_dekar": round(ekili_degil_alan, 1),
                "ekilebilir_alan_toplam_dekar": round(ekilebilir_toplam, 1),
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


    def _notification_scope_filter(user) -> Dict[str, Any]:
        """2026-08-20 — Kişiye özel hedefleme: bir bildirim `target_user_id`
        taşıyorsa SADECE o kullanıcıya görünür; taşımıyorsa (eski tüm
        kayıtlar + broadcast bildirimler) herkese tenant genelinde görünür
        — geriye dönük kırılma YOK (mevcut kayıtların hiçbirinde bu alan
        yok, hepsi `$exists:false` kolundan geçmeye devam eder)."""
        return {"$or": [{"target_user_id": {"$exists": False}},
                         {"target_user_id": None},
                         {"target_user_id": user["id"]}]}

    @api_router.get("/notifications")
    async def list_notifications(
        q: Optional[str] = None, channel: Optional[str] = None,
        status: Optional[str] = None, module: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        include_archived: bool = False,
        skip: int = 0, limit: int = 50,
        user=Depends(current_user),
    ):
        """Bildirim listesi — sunucu tarafı filtre + sayfalama (2026-08-19).

        Eskiden parametresiz olarak SON 200 bildirimi döndürüyordu ve ekran
        hepsini tek seferde çekip client tarafında süzüyordu; bildirim sayısı
        arttıkça hem yavaşlıyor hem eski kayıtlara hiç ulaşılamıyordu.

        `module` filtresi drill-down içindir: bildirim artık ilgili kaydı
        (`module` + `entity_id`) taşıyabilir, detay ekranı "Kayda git"
        düğmesini bu alanlardan kurar.

        2026-08-20: `include_archived` (varsayılan false — arşivlenenler
        listeden düşer, "Arşivlenenler" sekmesi ayrıca ister) +
        `_notification_scope_filter` ile kişiye özel hedefleme.
        """
        filt: Dict[str, Any] = {"$and": [_notification_scope_filter(user)]}
        if not include_archived:
            filt["$and"].append({"archived": {"$ne": True}})
        if channel:
            filt["channel"] = channel
        if status == "okunmadi":
            filt["status"] = {"$ne": "okundu"}
        elif status:
            filt["status"] = status
        if module:
            filt["module"] = module
        if date_from or date_to:
            rng: Dict[str, Any] = {}
            if date_from:
                rng["$gte"] = date_from
            if date_to:
                # Gün sonuna kadar: "2026-08-19" → "2026-08-19T23:59:59"
                rng["$lte"] = f"{date_to}T23:59:59"
            filt["created_at"] = rng
        if q:
            rx = {"$regex": re.escape(q), "$options": "i"}
            filt["$and"].append({"$or": [{"title": rx}, {"message": rx}]})

        total = await db.notifications.count_documents(filt)
        unread = await db.notifications.count_documents({**filt, "status": {"$ne": "okundu"}})
        items = await db.notifications.find(filt, {"_id": 0}).sort(
            [("created_at", -1)]).skip(max(0, skip)).limit(max(1, min(limit, 200))).to_list(200)
        return {"items": items, "total": total, "unread": unread,
                "skip": skip, "limit": limit}


    @api_router.get("/notifications/unread-count")
    async def unread_notification_count(user=Depends(current_user)):
        """IT-12 — Bildirim çekmecesindeki zil rozeti için. 2026-08-20:
        artık kişiye özel hedeflenen bildirimleri de doğru sayar (bkz.
        `_notification_scope_filter`) ve arşivlenenleri hariç tutar."""
        count = await db.notifications.count_documents({
            "$and": [_notification_scope_filter(user),
                      {"status": {"$ne": "okundu"}},
                      {"archived": {"$ne": True}}],
        })
        return {"count": count}


    @api_router.put("/notifications/{notification_id}/read")
    async def mark_notification_read(notification_id: str, user=Depends(current_user)):
        old = await db.notifications.find_one(
            {"$and": [{"id": notification_id}, _notification_scope_filter(user)]}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Bildirim bulunamadı")
        await db.notifications.update_one({"id": notification_id}, {"$set": {"status": "okundu"}})
        return {"status": "ok"}


    @api_router.post("/notifications/mark-all-read")
    async def mark_all_notifications_read(user=Depends(current_user)):
        result = await db.notifications.update_many(
            {"$and": [_notification_scope_filter(user), {"status": {"$ne": "okundu"}}]},
            {"$set": {"status": "okundu"}})
        return {"status": "ok", "updated": result.modified_count}


    @api_router.put("/notifications/{notification_id}/archive")
    async def archive_notification(notification_id: str, user=Depends(current_user)):
        """2026-08-20 — Bildirim Merkezi tamamlanması: arşivleme. Fiziksel
        silme YOK (convention #3 soft-delete) — `archived:true` işaretlenir,
        listeler varsayılan olarak hariç tutar, `/unarchive` ile geri alınır."""
        old = await db.notifications.find_one(
            {"$and": [{"id": notification_id}, _notification_scope_filter(user)]}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Bildirim bulunamadı")
        await db.notifications.update_one({"id": notification_id}, {"$set": {"archived": True}})
        return {"status": "ok"}


    @api_router.put("/notifications/{notification_id}/unarchive")
    async def unarchive_notification(notification_id: str, user=Depends(current_user)):
        old = await db.notifications.find_one(
            {"$and": [{"id": notification_id}, _notification_scope_filter(user)]}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Bildirim bulunamadı")
        await db.notifications.update_one({"id": notification_id}, {"$set": {"archived": False}})
        return {"status": "ok"}


    # SON HAL #8 — bildirim çekmecesinde (WorkspaceDrawer) tıklanan bildirimin
    # yönlendirileceği detay sayfası (NotificationDetail.jsx) için. BİLİNÇLİ
    # OLARAK yukarıdaki /notifications/unread-count ve /notifications/mark-all-
    # read'DEN SONRA tanımlı — route sırası tuzağı (bkz. CLAUDE.md
    # "/parcels/bulk-update" notu). Broadcast bildirimler (target_user_id
    # yok) tenant genelinde herkese görünür — eski davranış korunur; AMA
    # 2026-08-20'den beri bir bildirim `target_user_id` taşıyabildiğinden
    # (kişiye özel hedefleme) burada da `_notification_scope_filter` ile
    # sahiplik kontrolü eklendi — aksi halde ID'yi bilen biri başkasına
    # hedeflenmiş bir bildirimi doğrudan okuyabilirdi.
    @api_router.get("/notifications/{notification_id}")
    async def get_notification(notification_id: str, user=Depends(current_user)):
        doc = await db.notifications.find_one(
            {"$and": [{"id": notification_id}, _notification_scope_filter(user)]}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Bildirim bulunamadı")
        return doc


    @api_router.get("/karne/top")
    async def karne_top(limit: int = 10, user=Depends(current_user), _feat=Depends(require_feature("reports"))):
        return await db.farmers.find({}, {"_id": 0}).sort([("karne_points", -1)]).limit(limit).to_list(limit)


    @api_router.get("/karne/bottom")
    async def karne_bottom(limit: int = 10, user=Depends(current_user)):
        return await db.farmers.find({}, {"_id": 0}).sort([("karne_points", 1)]).limit(limit).to_list(limit)



