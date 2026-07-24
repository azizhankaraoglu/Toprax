"""
=====================================================================
Toprax — Salt-okunur domain listeleri (toprak/sözleşme/ekim/sulama/operasyon/analitik)
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


def register_listing_routes(api_router, db, current_user, require_feature):
    @api_router.get("/soil-samples")
    async def list_soil_samples(user=Depends(current_user), _feat=Depends(require_feature("soil"))):
        """Tüm toprak analizleri (admin)"""
        docs = await db.soil_samples.find({"is_active": {"$ne": False}}, {"_id": 0}).sort([("date", -1)]).to_list(500)
        return docs


    @api_router.get("/soil-samples/summary")
    async def soil_summary(user=Depends(current_user)):
        """
        Toprak analiz özeti — admin dashboard için.
    
        Toplam numune, ortalama pH/EC/OM,
        pH dağılımı (asitli/nötr/alkalin),
        önerilen gübre tipleri.
        """
        samples = await db.soil_samples.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(5000)

        if not samples:
            return {"total": 0, "avg_ph": 0, "ph_distribution": [], "recent": []}
    
        avg_ph = sum(s.get("ph", 0) for s in samples) / len(samples)
        avg_ec = sum(s.get("ec", 0) for s in samples) / len(samples)
        avg_om = sum(s.get("organic_matter_pct", 0) for s in samples) / len(samples)
    
        # pH bantları
        ph_dist = {"Asitli (<6.5)": 0, "Nötr (6.5-7.5)": 0, "Hafif Alkalin (7.5-8.0)": 0, "Alkalin (>8.0)": 0}
        for s in samples:
            ph = s.get("ph", 7)
            if ph < 6.5:
                ph_dist["Asitli (<6.5)"] += 1
            elif ph < 7.5:
                ph_dist["Nötr (6.5-7.5)"] += 1
            elif ph < 8.0:
                ph_dist["Hafif Alkalin (7.5-8.0)"] += 1
            else:
                ph_dist["Alkalin (>8.0)"] += 1
    
        return {
            "total": len(samples),
            "avg_ph": round(avg_ph, 2),
            "avg_ec": round(avg_ec, 2),
            "avg_om": round(avg_om, 2),
            "ph_distribution": [{"label": k, "count": v} for k, v in ph_dist.items()],
            "recent": sorted(samples, key=lambda s: s.get("date", ""), reverse=True)[:15]
        }


    # =====================================================================
    #                       SÖZLEŞMELER (M04)
    # =====================================================================

    @api_router.get("/contracts")
    async def list_contracts(season: Optional[int] = None, status: Optional[str] = None, user=Depends(current_user),
                              _feat=Depends(require_feature("contracts"))):
        # BULGU 1 düzeltmesi: soft-delete edilmiş sözleşmeler listelenmez.
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}
        if season: filt["season"] = season
        if status: filt["status"] = status
        docs = await db.contracts.find(filt, {"_id": 0}).to_list(5000)
        return docs


    # =====================================================================
    #                       EKİM (M05)
    # =====================================================================

    @api_router.get("/plantings")
    async def list_plantings(season: Optional[int] = None, parcel_id: Optional[str] = None,
                             user=Depends(current_user), _feat=Depends(require_feature("planting"))):
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
        if season: filt["season"] = season
        if parcel_id: filt["parcel_id"] = parcel_id             # SON HAL — /ekim?parcel= filtresi
        docs = await db.plantings.find(filt, {"_id": 0}).to_list(5000)
        return docs


    # =====================================================================
    #                       SULAMA (M15)
    # =====================================================================

    @api_router.get("/irrigation/summary")
    async def irrigation_summary(user=Depends(current_user)):
        """
        Sulama modülü özet verileri.
        Bu endpoint çiftçiler veri eklediğinde otomatik güncellenir.
        """
        events = await db.irrigation_events.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(20000)
        sources = await db.water_sources.find({}, {"_id": 0}).to_list(100)
        regions = await db.regions.find({}, {"_id": 0}).to_list(100)
    
        total_m3 = sum(e.get("water_m3", 0) for e in events)
    
        # Bölge bazlı
        by_region = []
        for r in regions:
            r_events = [e for e in events if e.get("region_id") == r["id"]]
            by_region.append({
                "name": r["name"],
                "water_m3": sum(e.get("water_m3", 0) for e in r_events),
                "events": len(r_events)
            })
    
        # Yönteme göre
        by_method = {}
        for e in events:
            m = e.get("method", "diğer")
            by_method[m] = by_method.get(m, 0) + e.get("water_m3", 0)
    
        # Kuraklık risk (her bölge için random + tutarlı seed)
        # Üretim sürümünde Sentinel Hub + hava verileriyle hesaplanır
        random.seed(2026)
        drought_risk = [
            {"region": r["name"], "risk_pct": random.randint(15, 85), "level": random.choice(["düşük", "orta", "yüksek"])}
            for r in regions
        ]
    
        return {
            "total_m3": round(total_m3, 1),
            "events_count": len(events),
            "water_sources": sources,
            "by_region": by_region,
            "by_method": [{"method": k, "m3": v} for k, v in by_method.items()],
            "drought_risk": drought_risk
        }


    @api_router.get("/irrigation/events")
    async def list_irrigation_events(farmer_id: Optional[str] = None, limit: int = 200, user=Depends(current_user)):
        """Sulama olayları listesi (filtreli)"""
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
        if farmer_id: filt["farmer_id"] = farmer_id
        docs = await db.irrigation_events.find(filt, {"_id": 0}).sort([("date", -1)]).limit(limit).to_list(limit)
        return docs


    # =====================================================================
    #                       OPERASYON (M16)
    # =====================================================================

    @api_router.get("/operations/tasks")
    async def list_tasks(status: Optional[str] = None, user=Depends(current_user)):
        # BULGU 1 düzeltmesi: soft-delete edilmiş görevler listelenmez.
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}
        if status: filt["status"] = status
        docs = await db.tasks.find(filt, {"_id": 0}).sort([("scheduled_date", 1)]).to_list(1000)
        return docs


    @api_router.get("/operations/machines")
    async def list_machines(user=Depends(current_user)):
        # BULGU 1 düzeltmesi: soft-delete edilmiş makineler listelenmez.
        return await db.machines.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(500)


    @api_router.get("/operations/workers")
    async def list_workers(user=Depends(current_user)):
        # BULGU 1 düzeltmesi: soft-delete edilmiş işçiler listelenmez.
        return await db.workers.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(500)


    @api_router.get("/operations/summary")
    async def operations_summary(user=Depends(current_user)):
        tasks = await db.tasks.find({}, {"_id": 0}).to_list(5000)
        machines = await db.machines.find({}, {"_id": 0}).to_list(500)
        status_count = {}
        type_count = {}
        for t in tasks:
            status_count[t.get("status", "planlı")] = status_count.get(t.get("status", "planlı"), 0) + 1
            type_count[t.get("task_type", "diğer")] = type_count.get(t.get("task_type", "diğer"), 0) + 1
        return {
            "tasks_total": len(tasks),
            "by_status": status_count,
            "by_type": type_count,
            "machines_total": len(machines),
            "machines_active": len([m for m in machines if m.get("status") == "aktif"]),
            "machines_maintenance": len([m for m in machines if m.get("status") == "bakım"])
        }


    # =====================================================================
    #                       VERİMLİLİK ANALİTİK (M17)
    # =====================================================================

    @api_router.get("/analytics/yields")
    async def yields_analytics(season: Optional[int] = None, user=Depends(current_user),
                                _feat=Depends(require_feature("reports"))):
        filt: Dict[str, Any] = {}
        if season: filt["season"] = season
        yields = await db.yields.find(filt, {"_id": 0}).to_list(10000)
    
        # Bölge bazlı toplama
        by_region = {}
        for y in yields:
            rid = y.get("region_id")
            if rid not in by_region:
                by_region[rid] = {"ton": 0, "dekar": 0, "polar_sum": 0, "count": 0}
            by_region[rid]["ton"] += y.get("actual_ton", 0)
            by_region[rid]["dekar"] += y.get("area_dekar", 0)
            by_region[rid]["polar_sum"] += y.get("polar_oran", 16)
            by_region[rid]["count"] += 1
    
        regions = await db.regions.find({}, {"_id": 0}).to_list(100)
        region_stats = []
        for r in regions:
            b = by_region.get(r["id"], {"ton": 0, "dekar": 0, "polar_sum": 0, "count": 0})
            region_stats.append({
                "region": r["name"],
                "ton": round(b["ton"], 1),
                "dekar": round(b["dekar"], 1),
                "ton_per_dekar": round(b["ton"] / max(b["dekar"], 1), 2),
                "avg_polar": round(b["polar_sum"] / max(b["count"], 1), 2)
            })
    
        # 5 yıllık trend
        trend = []
        all_y = await db.yields.find({}, {"_id": 0}).to_list(10000)
        for yr in range(2021, 2026):
            y_year = [y for y in all_y if y.get("season") == yr]
            if y_year:
                t_ton = sum(y.get("actual_ton", 0) for y in y_year)
                t_dekar = sum(y.get("area_dekar", 0) for y in y_year)
                trend.append({
                    "year": yr,
                    "ton_per_dekar": round(t_ton / max(t_dekar, 1), 2),
                    "total_ton": round(t_ton, 1)
                })
    
        top_parcels = sorted(yields, key=lambda y: y.get("actual_ton", 0) / max(y.get("area_dekar", 1), 1), reverse=True)[:10]
    
        return {
            "by_region": region_stats,
            "trend": trend,
            "top_parcels": top_parcels[:10],
            "total_parcels": len(yields)
        }


    @api_router.get("/analytics/scenario")
    async def scenario_simulation(drought_pct: int = 0, price_pct: int = 0, cost_pct: int = 0, user=Depends(current_user)):
        """What-if senaryo simülasyonu — kuraklık/fiyat/maliyet etkisi"""
        yields = await db.yields.find({"season": 2025}, {"_id": 0}).to_list(10000)
        base_ton = sum(y.get("actual_ton", 0) for y in yields)
        base_revenue = base_ton * 1800                          # Ortalama pancar fiyatı TL/ton
        base_cost = base_revenue * 0.55                         # Tahmini maliyet oranı %55
    
        new_ton = base_ton * (1 - drought_pct / 100)
        new_price = 1800 * (1 + price_pct / 100)
        new_revenue = new_ton * new_price
        new_cost = base_cost * (1 + cost_pct / 100)
    
        return {
            "base": {"ton": round(base_ton, 1), "revenue": round(base_revenue), "cost": round(base_cost), "profit": round(base_revenue - base_cost)},
            "scenario": {
                "ton": round(new_ton, 1),
                "revenue": round(new_revenue),
                "cost": round(new_cost),
                "profit": round(new_revenue - new_cost),
                "profit_delta_pct": round(((new_revenue - new_cost) - (base_revenue - base_cost)) / max(base_revenue - base_cost, 1) * 100, 1)
            }
        }



