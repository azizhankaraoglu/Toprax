"""
=====================================================================
TOPRAX — Karne Puanlama Motoru (SON HAL)
=====================================================================
Önceki durum: `farmers.karne_points`/`karne_score` seed sırasında RASTGELE
atanıyordu ve hiçbir yerde hesaplanmıyordu — "neden 9.5 aldı?" sorusunun
cevabı yoktu. Bu modül skoru GERÇEK verilerden, PARAMETRİK ağırlıklarla
hesaplar ve bileşen bileşen açıklar.

BİLEŞENLER (varsayılan ağırlıklar `karne_parameters` koleksiyonunda,
admin ekrandan değiştirilebilir — season_parameters.py kalıbı):
  - kota  %30 — Kota gerçekleşme (yields.actual_ton / contracts.kota_ton)
  - polar %25 — Polar ortalaması vs BÖLGE ortalaması (yields.polar_oran)
  - sulama %15 — Sulama disiplini (son sezonda parsel başına kayıt)
  - toprak %15 — Toprak analizi güncelliği (en yeni analiz yaşı)
  - finans %15 — Cari bakiye (db.finance amount toplamı)

DÜRÜSTLÜK KURALI: verisi olmayan bileşen 50 (nötr) SAYILMAZ — o bileşen
hesaptan ÇIKARILIR ve kalan ağırlıklar yeniden normalize edilir; açıklamada
"veri yok" olarak işaretlenir. Eksik veri ceza da ödül de değildir.

Harf eşikleri seed'dekiyle AYNI: A>=85, B>=70, C>=55, D.
`POST /karne/recompute` mevcut (rastgele) skorları `karne_points_seed`
alanına BİR KEZ yedekleyip üzerine yazar — geri dönüş izi kalır.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

DEFAULT_WEIGHTS = {
    "kota": 30.0, "polar": 25.0, "sulama": 15.0, "toprak": 15.0, "finans": 15.0,
}
COMPONENT_LABELS = {
    "kota": "Kota Gerçekleşme",
    "polar": "Polar (Bölgeye Göre)",
    "sulama": "Sulama Disiplini",
    "toprak": "Toprak Analizi Güncelliği",
    "finans": "Finansal Durum (Cari Bakiye)",
}


def points_to_letter(points: float) -> str:
    if points >= 85:
        return "A"
    if points >= 70:
        return "B"
    if points >= 55:
        return "C"
    return "D"


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def register_karne_engine_routes(api_router, db, current_user, require_permission, log_audit):

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _get_weights() -> Dict[str, float]:
        doc = await db.karne_parameters.find_one({"key": "default"}, {"_id": 0})
        w = dict(DEFAULT_WEIGHTS)
        if doc and isinstance(doc.get("weights"), dict):
            for k in w:
                try:
                    w[k] = float(doc["weights"].get(k, w[k]))
                except (TypeError, ValueError):
                    pass
        return w

    # -----------------------------------------------------------------
    # ÇEKİRDEK HESAP — bir çiftçinin bileşen bileşen karnesi
    # -----------------------------------------------------------------
    async def compute_farmer_karne(farmer: Dict[str, Any],
                                   region_polar_avg: Optional[float] = None) -> Dict[str, Any]:
        fid = farmer["id"]
        weights = await _get_weights()
        comps: List[Dict[str, Any]] = []

        yields = await db.yields.find({"farmer_id": fid}, {"_id": 0}).to_list(200)
        contracts = await db.contracts.find(
            {"farmer_id": fid, "is_active": {"$ne": False}}, {"_id": 0}).to_list(200)
        parcels = await db.parcels.find(
            {"farmer_id": fid, "is_active": {"$ne": False}}, {"_id": 0, "id": 1}).to_list(200)
        parcel_ids = [p["id"] for p in parcels]

        # --- 1) Kota gerçekleşme ---
        kota_total = sum(float(c.get("kota_ton") or 0) for c in contracts)
        actual_total = sum(float(y.get("actual_ton") or 0) for y in yields)
        if kota_total > 0:
            ratio = actual_total / kota_total
            score = _clamp(ratio * 100)
            comps.append({
                "key": "kota", "has_data": True, "score": round(score, 1),
                "raw": f"{actual_total:.0f} / {kota_total:.0f} ton (%{ratio*100:.0f})",
                "explanation": (f"Sözleşme kotası toplam {kota_total:.0f} ton; gerçekleşen teslim "
                                f"{actual_total:.0f} ton (%{ratio*100:.0f} gerçekleşme)."),
            })
        else:
            comps.append({"key": "kota", "has_data": False, "score": None, "raw": None,
                          "explanation": "Kota tanımlı sözleşme yok — bu bileşen hesaba katılmadı."})

        # --- 2) Polar vs bölge ortalaması ---
        polars = [float(y["polar_oran"]) for y in yields if y.get("polar_oran")]
        if polars and region_polar_avg:
            avg = sum(polars) / len(polars)
            diff = avg - region_polar_avg
            score = _clamp(50 + diff * 20)          # bölgeden +2.5 puan polar = 100
            comps.append({
                "key": "polar", "has_data": True, "score": round(score, 1),
                "raw": f"%{avg:.2f} (bölge: %{region_polar_avg:.2f})",
                "explanation": (f"Çiftçinin polar ortalaması %{avg:.2f}, bölge ortalaması "
                                f"%{region_polar_avg:.2f} — fark {diff:+.2f} puan."),
            })
        else:
            comps.append({"key": "polar", "has_data": False, "score": None, "raw": None,
                          "explanation": "Polar ölçümü (verim kaydı) yok — bu bileşen hesaba katılmadı."})

        # --- 3) Sulama disiplini (son verim sezonu bazında) ---
        if parcel_ids:
            seasons = [y.get("season") for y in yields if y.get("season")]
            last_season = max(seasons) if seasons else None
            irr_filt: Dict[str, Any] = {"parcel_id": {"$in": parcel_ids},
                                        "is_active": {"$ne": False}}
            if last_season:
                irr_filt["date"] = {"$regex": f"^{last_season}"}
            irr_count = await db.irrigation_events.count_documents(irr_filt)
            per_parcel = irr_count / len(parcel_ids)
            score = _clamp(per_parcel / 3.0 * 100)  # sezonda parsel başına 3 sulama = tam puan
            comps.append({
                "key": "sulama", "has_data": True, "score": round(score, 1),
                "raw": f"{irr_count} kayıt / {len(parcel_ids)} parsel"
                       + (f" ({last_season})" if last_season else ""),
                "explanation": (f"{'%s sezonunda ' % last_season if last_season else ''}parsel başına "
                                f"{per_parcel:.1f} sulama kaydı (hedef: ≥3)."),
            })
        else:
            comps.append({"key": "sulama", "has_data": False, "score": None, "raw": None,
                          "explanation": "Kayıtlı parsel yok — bu bileşen hesaba katılmadı."})

        # --- 4) Toprak analizi güncelliği ---
        if parcel_ids:
            latest = await db.soil_samples.find(
                {"parcel_id": {"$in": parcel_ids}, "is_active": {"$ne": False}},
                {"_id": 0, "date": 1, "sample_date": 1, "created_at": 1},
            ).sort([("date", -1)]).to_list(1)
            age_days = None
            if latest:
                ds = latest[0].get("date") or latest[0].get("sample_date") or latest[0].get("created_at")
                try:
                    d = datetime.fromisoformat(str(ds).replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - d).days
                except (ValueError, TypeError):
                    age_days = None
            if age_days is None:
                score, raw, expl = 0.0, "analiz yok", "Hiç toprak analizi yaptırılmamış."
            elif age_days <= 365:
                score, raw = 100.0, f"{age_days} gün önce"
                expl = f"Son toprak analizi {age_days} gün önce — güncel."
            elif age_days <= 730:
                score, raw = 60.0, f"{age_days} gün önce"
                expl = f"Son toprak analizi {age_days} gün önce — yenilenmesi önerilir."
            else:
                score, raw = 20.0, f"{age_days} gün önce"
                expl = f"Son toprak analizi {age_days} gün önce — 2 yıldan eski."
            comps.append({"key": "toprak", "has_data": True, "score": score,
                          "raw": raw, "explanation": expl})
        else:
            comps.append({"key": "toprak", "has_data": False, "score": None, "raw": None,
                          "explanation": "Kayıtlı parsel yok — bu bileşen hesaba katılmadı."})

        # --- 5) Finansal durum ---
        fin = await db.finance.find({"farmer_id": fid}, {"_id": 0, "amount": 1}).to_list(1000)
        if fin:
            balance = sum(float(f.get("amount") or 0) for f in fin)
            if balance >= 0:
                score = 100.0
            else:
                score = _clamp(100.0 + (balance / 50000.0) * 100.0)  # -50.000 TL ve altı = 0
            comps.append({
                "key": "finans", "has_data": True, "score": round(score, 1),
                "raw": f"{balance:,.0f} TL",
                "explanation": ("Cari bakiye pozitif — borç yok." if balance >= 0
                                else f"Cari bakiye {balance:,.0f} TL (borçlu)."),
            })
        else:
            comps.append({"key": "finans", "has_data": False, "score": None, "raw": None,
                          "explanation": "Finansal hareket kaydı yok — bu bileşen hesaba katılmadı."})

        # --- Ağırlıklı toplam (verisi olmayanlar hariç, yeniden normalize) ---
        active = [c for c in comps if c["has_data"]]
        total_w = sum(weights[c["key"]] for c in active)
        if total_w > 0:
            points = sum(c["score"] * weights[c["key"]] for c in active) / total_w
        else:
            points = float(farmer.get("karne_points") or 50)   # hiç veri yoksa mevcut skor korunur

        for c in comps:
            c["label"] = COMPONENT_LABELS[c["key"]]
            c["weight"] = weights[c["key"]]
            c["effective_weight"] = round(weights[c["key"]] / total_w * 100, 1) if (c["has_data"] and total_w) else 0
            c["contribution"] = round(c["score"] * weights[c["key"]] / total_w, 1) if (c["has_data"] and total_w) else None

        points = round(points, 1)
        return {
            "farmer_id": fid, "points": points, "letter": points_to_letter(points),
            "components": comps,
            "computed_at": _now(),
            "no_data": total_w == 0,
        }

    async def _region_polar_averages() -> Dict[str, float]:
        """Bölge bazında polar ortalaması — tüm breakdown/recompute çağrıları
        için tek seferde hesaplanır (yields.region_id üzerinden)."""
        out: Dict[str, List[float]] = {}
        async for y in db.yields.find({}, {"_id": 0, "region_id": 1, "polar_oran": 1}):
            if y.get("polar_oran") and y.get("region_id"):
                out.setdefault(y["region_id"], []).append(float(y["polar_oran"]))
        return {rid: sum(v) / len(v) for rid, v in out.items() if v}

    # -----------------------------------------------------------------
    # UÇLAR
    # -----------------------------------------------------------------
    @api_router.get("/karne/parameters")
    async def get_karne_parameters(user=Depends(require_permission("farmers:view"))):
        doc = await db.karne_parameters.find_one({"key": "default"}, {"_id": 0})
        return doc or {"key": "default", "weights": DEFAULT_WEIGHTS,
                       "labels": COMPONENT_LABELS}

    class KarneParamsUpdate(BaseModel):
        weights: Dict[str, float]

    @api_router.put("/karne/parameters")
    async def update_karne_parameters(body: KarneParamsUpdate, request: Request,
                                      user=Depends(require_permission("karne:manage"))):
        unknown = set(body.weights) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise HTTPException(400, f"Bilinmeyen bileşen: {', '.join(unknown)}")
        if any(v < 0 for v in body.weights.values()):
            raise HTTPException(400, "Ağırlık negatif olamaz")
        old = await db.karne_parameters.find_one({"key": "default"}, {"_id": 0})
        merged = {**DEFAULT_WEIGHTS, **body.weights}
        await db.karne_parameters.update_one(
            {"key": "default"},
            {"$set": {"weights": merged, "updated_at": _now(),
                      "updated_by": user.get("full_name")},
             "$setOnInsert": {"id": str(uuid.uuid4()), "key": "default"}},
            upsert=True)
        new = await db.karne_parameters.find_one({"key": "default"}, {"_id": 0})
        await log_audit(db, user, action="update", entity="karne_parameters",
                        entity_id="default", old_value=old, new_value=new, request=request)
        return new

    @api_router.get("/karne/{farmer_id}/history")
    async def karne_history(farmer_id: str,
                            user=Depends(require_permission("farmers:view"))):
        """SON HAL — karne trendi: her recompute'ta düşülen anlık görüntüler.
        KarneDetail'deki 'skor nasıl değişmiş' grafiğinin veri kaynağı."""
        return await db.karne_history.find(
            {"farmer_id": farmer_id}, {"_id": 0}
        ).sort([("computed_at", 1)]).to_list(200)

    @api_router.get("/karne/{farmer_id}/breakdown")
    async def karne_breakdown(farmer_id: str,
                              user=Depends(require_permission("farmers:view"))):
        """"Neden bu skoru aldı?" — bileşen bileşen CANLI hesap. DB'deki
        karne_points'i DEĞİŞTİRMEZ (o sadece recompute ile yazılır);
        stored_points ile karşılaştırma yanıtta ayrıca döner."""
        farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        region_avgs = await _region_polar_averages()
        result = await compute_farmer_karne(farmer, region_avgs.get(farmer.get("region_id")))
        result["farmer"] = {"id": farmer["id"], "full_name": farmer.get("full_name"),
                            "member_no": farmer.get("member_no"), "village": farmer.get("village")}
        result["stored_points"] = farmer.get("karne_points")
        result["stored_letter"] = farmer.get("karne_score")
        result["stored_is_stale"] = (farmer.get("karne_points") != result["points"])
        return result

    @api_router.post("/karne/recompute")
    async def karne_recompute(request: Request,
                              user=Depends(require_permission("karne:manage"))):
        """TÜM çiftçilerin karne_points/karne_score'unu motorla yeniden yazar.
        İlk çalıştırmada eski (seed) skor `karne_points_seed`e yedeklenir."""
        region_avgs = await _region_polar_averages()
        updated = 0
        letters = {"A": 0, "B": 0, "C": 0, "D": 0}
        async for farmer in db.farmers.find({"is_active": {"$ne": False}}, {"_id": 0}):
            result = await compute_farmer_karne(farmer, region_avgs.get(farmer.get("region_id")))
            sets = {"karne_points": result["points"],
                    "karne_score": result["letter"],
                    "karne_computed_at": result["computed_at"]}
            if "karne_points_seed" not in farmer and farmer.get("karne_points") is not None:
                sets["karne_points_seed"] = farmer["karne_points"]
            await db.farmers.update_one({"id": farmer["id"]}, {"$set": sets})
            # SON HAL — trend için anlık görüntü (bileşen özetleriyle birlikte)
            await db.karne_history.insert_one({
                "id": str(uuid.uuid4()), "farmer_id": farmer["id"],
                "points": result["points"], "letter": result["letter"],
                "computed_at": result["computed_at"],
                "components": [{"key": c["key"], "score": c["score"],
                                "has_data": c["has_data"]} for c in result["components"]],
            })
            letters[result["letter"]] += 1
            updated += 1
        await log_audit(db, user, action="recompute", entity="karne",
                        entity_id="all", new_value={"updated": updated, "letters": letters},
                        request=request)
        return {"updated": updated, "letters": letters}
