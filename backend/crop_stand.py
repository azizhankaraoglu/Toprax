"""
=====================================================================
TOPRAX — Bitki Sıklığı / Kök Sayısı ve Ürün Tespiti
=====================================================================
Kullanıcı isteği: "Eklenen her tarlada ne ekili olduğunu, kaç adet kök
ekildiğini sisteme işlememiz gerekli."

FİZİKSEL GERÇEK (kapsamın neden böyle çizildiği):
  Sentinel-2 10 m, NASA HLS 30 m çözünürlüktedir — 1 piksel 100-900 m².
  Bir şeker pancarı bitkisi çıkışta 2-5 cm, olgunlukta ~30 cm kanopidir.
  Yani UYDUDAN TEK BİTKİ SAYILAMAZ; en iyi ticari uydular (WorldView-3
  31 cm, Pléiades Neo 30 cm) bile pancarda tek bitki çözemez (ağaç sayabilir).
  Bu yüzden kök sayısı ÜÇ katmanlı ele alınır:

    1. **Agronomik hesap** (bu modül) — sıra arası × sıra üzeri × alan ×
       çimlenme oranı. Tarımda standart yöntem budur; ekim makinesinin
       ayarından doğrudan türetilir.
    2. **Saha/manuel düzeltme** — çiftçi veya mühendis sayım yaparsa
       (`plant_count_source="manuel"`) hesap onun üzerine YAZILMAZ.
    3. **Drone/VHR doğrulama** — mevcut `drone_missions` modülüyle; VHR
       fizibilitesi ayrı raporda (`docs/vhr-fizibilite.md`).

ÜRÜN TESPİTİ: uydu indeks eğrisinden (fenolojik imza) tahmin edilir ve
HER ZAMAN "öneri" olarak döner — kaydı otomatik değiştirmez.
"""
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

#: Ürün bazlı tipik ekim geometrisi (sıra arası cm, sıra üzeri cm) ve
#: literatürdeki hedef bitki sıklığı (bitki/dekar).
#: Şeker pancarı: 45 cm sıra arası, 18-20 cm sıra üzeri → ~11.000 bitki/da.
CROP_GEOMETRY = {
    "pancar": {"row_cm": 45, "seed_cm": 19, "hedef_bitki_dekar": 11000,
               "tohum_cesidi": "monogerm"},
    "misir": {"row_cm": 70, "seed_cm": 18, "hedef_bitki_dekar": 8000},
    "aycicegi": {"row_cm": 70, "seed_cm": 30, "hedef_bitki_dekar": 4800},
    "patates": {"row_cm": 75, "seed_cm": 30, "hedef_bitki_dekar": 4400},
}
DEFAULT_GEOMETRY = {"row_cm": 45, "seed_cm": 20, "hedef_bitki_dekar": 11000}


# =====================================================================
# SAF HESAPLAR
# =====================================================================

def plants_per_dekar(row_spacing_cm: float, seed_spacing_cm: float,
                     germination_pct: Optional[float] = None) -> Optional[float]:
    """Dekara düşen bitki sayısı.

    1 dekar = 1.000 m² = 10.000.000 cm². Bir bitkinin kapladığı alan
    (sıra arası × sıra üzeri) cm² cinsindendir; bölüm doğrudan bitki
    sayısını verir. Çimlenme oranı verilirse EKİLEN tohumdan ÇIKAN bitkiye
    düşülür — ekim normu ile gerçek sıklık farklı şeylerdir.
    """
    if not row_spacing_cm or not seed_spacing_cm:
        return None
    if row_spacing_cm <= 0 or seed_spacing_cm <= 0:
        return None
    per_da = 10_000_000.0 / (row_spacing_cm * seed_spacing_cm)
    if germination_pct is not None:
        per_da *= max(0.0, min(germination_pct, 100.0)) / 100.0
    return round(per_da, 1)


def total_plant_count(area_dekar: Optional[float], row_spacing_cm: Optional[float],
                      seed_spacing_cm: Optional[float],
                      germination_pct: Optional[float] = None) -> Optional[int]:
    """Parseldeki toplam kök/bitki sayısı."""
    if not area_dekar:
        return None
    per_da = plants_per_dekar(row_spacing_cm or 0, seed_spacing_cm or 0, germination_pct)
    if per_da is None:
        return None
    return int(round(per_da * area_dekar))


def stand_uniformity(measured_per_dekar: Optional[float],
                     target_per_dekar: Optional[float]) -> Optional[float]:
    """Çıkış düzgünlüğü (%) — sayılan sıklığın hedefe oranı."""
    if not measured_per_dekar or not target_per_dekar:
        return None
    return round(min(measured_per_dekar / target_per_dekar * 100.0, 150.0), 1)


def seed_requirement_kg(area_dekar: Optional[float], row_spacing_cm: Optional[float],
                        seed_spacing_cm: Optional[float],
                        thousand_seed_weight_g: float = 12.0) -> Optional[float]:
    """Gerekli tohum miktarı (kg) — monogerm pancar tohumu ~10-14 g/1000 tohum.

    Sözleşmedeki `advance_seed_kg` (tohum avansı) ile karşılaştırmak için:
    avans, hesaplanan ihtiyacın çok altındaysa ekim normu tutmaz.
    """
    per_da = plants_per_dekar(row_spacing_cm or 0, seed_spacing_cm or 0)
    if per_da is None or not area_dekar:
        return None
    seeds = per_da * area_dekar
    return round(seeds * thousand_seed_weight_g / 1000.0 / 1000.0, 2)


def geometry_for(crop_key: Optional[str]) -> Dict[str, Any]:
    return CROP_GEOMETRY.get((crop_key or "").lower(), DEFAULT_GEOMETRY)


def compute_stand(planting: Dict[str, Any], area_dekar: Optional[float],
                  crop_key: Optional[str] = None) -> Dict[str, Any]:
    """Bir ekim kaydından tam bitki sıklığı özeti.

    Kaynak önceliği: manuel/drone sayım > hesap. Elle girilen sayım varsa
    hesap onu EZMEZ, yalnızca "hesaplanan" alanında referans olarak kalır.
    """
    geo = geometry_for(crop_key or planting.get("crop"))
    row = planting.get("row_spacing_cm") or geo["row_cm"]
    seed = planting.get("seed_spacing_cm") or geo["seed_cm"]
    germ = planting.get("germination_pct")

    hesap_per_da = plants_per_dekar(row, seed, germ)
    hesap_total = total_plant_count(area_dekar, row, seed, germ)

    manual = planting.get("plant_count_manual")
    source = planting.get("plant_count_source") or ("manuel" if manual else "hesap")
    final = manual if manual else hesap_total

    measured_per_da = (manual / area_dekar) if (manual and area_dekar) else hesap_per_da
    return {
        "sira_arasi_cm": row,
        "sira_uzeri_cm": seed,
        "cimlenme_yuzde": germ,
        "hedef_bitki_dekar": geo["hedef_bitki_dekar"],
        "hesaplanan_bitki_dekar": hesap_per_da,
        "hesaplanan_toplam_kok": hesap_total,
        "kayitli_toplam_kok": final,
        "kaynak": source,
        "cikis_duzgunlugu_yuzde": stand_uniformity(measured_per_da, geo["hedef_bitki_dekar"]),
        "tohum_ihtiyaci_kg": seed_requirement_kg(area_dekar, row, seed),
    }


# =====================================================================
# ÜRÜN TESPİTİ — uydu indeks eğrisinden
# =====================================================================
# Yaklaşım: her ürünün NDVI eğrisi karakteristik bir "imza" taşır —
# ekim/çıkış tarihi, zirve zamanı, zirve yüksekliği ve sezon uzunluğu.
# Veritabanındaki ETİKETLİ ekim kayıtları (plantings.crop) ile aynı
# parsellerin uydu serileri karşılaştırılarak en yakın imza seçilir.
#
# Bu bir sınıflandırıcıdır, KESİN bilgi değildir — bu yüzden sonuç her zaman
# `guven` (0-1) ile birlikte ve "öneri" olarak döner.

CROP_SIGNATURES = {
    "pancar": {"zirve_ay": 8, "zirve_ndvi": 0.80, "sezon_ay": (4, 10),
               "aciklama": "Geç zirve (Ağustos), uzun sezon, yüksek NDVI platosu"},
    "bugday": {"zirve_ay": 5, "zirve_ndvi": 0.75, "sezon_ay": (11, 7),
               "aciklama": "Kışlık: Mayıs zirvesi, Haziran-Temmuz'da hızlı sararma"},
    "arpa": {"zirve_ay": 5, "zirve_ndvi": 0.72, "sezon_ay": (11, 6),
             "aciklama": "Buğdaya benzer ama 2-3 hafta erken olgunlaşır"},
    "misir": {"zirve_ay": 7, "zirve_ndvi": 0.85, "sezon_ay": (5, 9),
              "aciklama": "Temmuz zirvesi, çok yüksek NDVI"},
    "aycicegi": {"zirve_ay": 7, "zirve_ndvi": 0.78, "sezon_ay": (5, 9),
                 "aciklama": "Temmuz zirvesi, Ağustos'ta hızlı düşüş"},
    "yonca": {"zirve_ay": 6, "zirve_ndvi": 0.70, "sezon_ay": (3, 10),
              "aciklama": "Biçim nedeniyle testere dişli, çok zirveli eğri"},
}


def classify_crop(series: List[Dict[str, Any]]) -> Dict[str, Any]:
    """NDVI zaman serisinden ürün tahmini.

    `series`: [{date: "YYYY-MM-DD", ndvi: float}, ...] — remote_sensing
    istatistiklerinin doğrudan şekli.
    """
    points = [(p["date"], p.get("ndvi")) for p in series if p.get("date") and p.get("ndvi") is not None]
    if len(points) < 4:
        return {"tahmin": None, "guven": 0.0,
                "sebep": "Yeterli uydu ölçümü yok (en az 4 gözlem gerekir)"}

    peak_date, peak_ndvi = max(points, key=lambda x: x[1])
    peak_month = int(peak_date[5:7])
    months = sorted({int(d[5:7]) for d, _ in points})
    active_months = sorted({int(d[5:7]) for d, v in points if v >= 0.35})
    # Testere dişi (çok zirveli) tespiti — yonca ayırt edici özelliği
    rises = sum(1 for i in range(1, len(points))
                if points[i][1] - points[i - 1][1] > 0.15)

    scored = []
    for crop, sig in CROP_SIGNATURES.items():
        # Ay farkı (dairesel): zirve ayı ne kadar tutuyor
        diff = min(abs(peak_month - sig["zirve_ay"]), 12 - abs(peak_month - sig["zirve_ay"]))
        month_score = max(0.0, 1.0 - diff / 4.0)
        # Zirve yüksekliği ne kadar tutuyor
        ndvi_score = max(0.0, 1.0 - abs(peak_ndvi - sig["zirve_ndvi"]) / 0.35)
        score = 0.6 * month_score + 0.4 * ndvi_score
        if crop == "yonca" and rises >= 3:
            score += 0.2          # çok zirveli eğri yoncaya işaret eder
        scored.append((crop, min(score, 1.0)))

    scored.sort(key=lambda x: x[1], reverse=True)
    best, confidence = scored[0]
    runner_up = scored[1] if len(scored) > 1 else (None, 0.0)
    # İki aday çok yakınsa güven düşer — "kararsızım" demek uydurmaktan iyidir.
    if runner_up[0] and confidence - runner_up[1] < 0.1:
        confidence *= 0.7

    return {
        "tahmin": best,
        "guven": round(confidence, 2),
        "zirve_tarihi": peak_date,
        "zirve_ndvi": round(peak_ndvi, 3),
        "aktif_aylar": active_months,
        "alternatif": runner_up[0],
        "sebep": CROP_SIGNATURES[best]["aciklama"],
        "not": "Uydu eğrisinden TAHMİNDİR — kaydı otomatik değiştirmez, "
               "saha doğrulaması ile teyit edilmelidir.",
    }


# =====================================================================
# HTTP YÜZEYİ
# =====================================================================

class StandUpdate(BaseModel):
    row_spacing_cm: Optional[float] = None
    seed_spacing_cm: Optional[float] = None
    germination_pct: Optional[float] = None
    plant_count_manual: Optional[int] = None
    plant_count_source: Optional[str] = None      # hesap | manuel | drone | vhr


def register_crop_stand_routes(api_router, db, current_user, require_permission,
                               log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/crop-stand/parcels/{parcel_id}")
    async def parcel_stand(parcel_id: str, season: Optional[int] = None,
                           user=Depends(require_permission("parcels:view"))):
        """Parselin güncel ekim kaydına göre kök sayısı özeti."""
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        filt = {"parcel_id": parcel_id}
        if season:
            filt["season"] = season
        planting = await db.plantings.find_one(filt, {"_id": 0}, sort=[("season", -1)])
        if not planting:
            return {"available": False, "reason": "Bu parselde ekim kaydı yok"}
        return {"available": True, "planting_id": planting["id"], "season": planting.get("season"),
                "crop": planting.get("crop"), "variety": planting.get("variety"),
                **compute_stand(planting, parcel.get("area_dekar"), planting.get("crop"))}

    @api_router.put("/crop-stand/plantings/{planting_id}")
    async def update_stand(planting_id: str, body: StandUpdate, request: Request,
                           user=Depends(require_permission("parcels:edit"))):
        planting = await db.plantings.find_one({"id": planting_id}, {"_id": 0})
        if not planting:
            raise HTTPException(404, "Ekim kaydı bulunamadı")
        parcel = await db.parcels.find_one({"id": planting.get("parcel_id")}, {"_id": 0, "area_dekar": 1})
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates.get("plant_count_manual") and not updates.get("plant_count_source"):
            updates["plant_count_source"] = "manuel"
        merged = {**planting, **updates}
        stand = compute_stand(merged, (parcel or {}).get("area_dekar"), merged.get("crop"))
        updates["plant_count_estimated"] = stand["hesaplanan_toplam_kok"]
        updates["stand_uniformity_pct"] = stand["cikis_duzgunlugu_yuzde"]
        await db.plantings.update_one({"id": planting_id}, {"$set": updates})
        await log_audit(db, user, action="update", entity="planting_stand",
                        entity_id=planting_id, new_value=updates, request=request)
        return {"ok": True, **stand}

    @api_router.get("/crop-stand/parcels/{parcel_id}/detect-crop")
    async def detect_crop(parcel_id: str, user=Depends(require_permission("parcels:view"))):
        """Uydu indeks eğrisinden ürün tahmini (öneri)."""
        stat = await db.remote_sensing_statistics.find_one(
            {"parcel_id": parcel_id}, {"_id": 0}, sort=[("created_at", -1)])
        if not stat or not stat.get("series"):
            return {"available": False,
                    "reason": "Bu parsel için uydu ölçümü yok — önce 'Uydu Analizini Güncelle' çalıştırın"}
        result = classify_crop(stat["series"])
        planting = await db.plantings.find_one({"parcel_id": parcel_id}, {"_id": 0},
                                               sort=[("season", -1)])
        result["kayitli_urun"] = (planting or {}).get("crop")
        result["available"] = True
        return result
