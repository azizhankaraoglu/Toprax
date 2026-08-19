"""
=====================================================================
TOPRAX — Polar (Şeker) Tahmini + Ekim/Söküm Zamanı Motoru
=====================================================================
Kullanıcının hedefi: "Polar oranını maksimize etmek… ne zaman ekmeliyim
(iklim, yağış, toprak bilgisi), ne zaman sökmeliyim (yaprak olgunlaşma
verilerinden kök sağlığı ve olgunlaşma endeksi)."

ÜÇ ÇIKTI
--------
1. **Polar tahmini** — geçmiş polar kayıtları + sezon ortası uydu indeksleri
   + toprak analizi ile. Model: küçük veriye uygun, AÇIKLANABİLİR bir
   ağırlıklı regresyon (kara kutu değil; her katkı ayrı gösterilir).
   Sonuç HER ZAMAN güven aralığıyla döner.
2. **Ekim penceresi** — toprak sıcaklığı, don riski, yağış penceresi ve
   toprak tavı. Pancar 5-7 °C toprak sıcaklığında çimlenmeye başlar; erken
   ekim don riski, geç ekim kısa vejetasyon (düşük polar) demektir.
3. **Olgunlaşma endeksi / söküm zamanı** — yaprak yaşlanmasının uydu
   imzası: NDVI/EVI zirveden düşüş, NDRE-CCCI ile azot çekilmesi, LAI
   gerilemesi. Pancarda bu üçü birlikte "bitki artık yaprağa değil köke
   şeker yolluyor" demektir; polar zirvesi bunu 2-4 hafta izler.

NEDEN "KARA KUTU ML" DEĞİL: eldeki etiketli veri parsel başına 5-6 sezon.
Bu boyutta gradient boosting gibi bir model ezberler ve neden-sonuç
gösteremez. Çiftçi/fabrika "neden bu tahmin?" diye sorduğunda cevap
verebilmek, birkaç puanlık doğruluktan daha değerlidir.
"""
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException

#: Şeker pancarında tipik polar aralığı (%). Türkiye ortalaması ~%16-17.
POLAR_MIN, POLAR_MAX = 12.0, 21.0
POLAR_BASELINE = 16.5

#: Ekim penceresi eşikleri (şeker pancarı, Konya koşulları).
SOWING = {
    "min_toprak_sicakligi_c": 6.0,      # çimlenme başlangıcı
    "ideal_toprak_sicakligi_c": 8.0,
    "don_riski_esik_c": -2.0,           # çıkış sonrası fide donar
    "en_erken_ay_gun": (3, 1),
    "en_gec_ay_gun": (5, 10),           # sonrası vejetasyon kısalır → polar düşer
    "hedef_vejetasyon_gun": 180,
}

#: Olgunlaşma göstergeleri — hepsi uydu indekslerinden ölçülür.
MATURITY_WEIGHTS = {
    "ndvi_dususu": 0.35,        # zirveden düşüş oranı
    "ndre_dususu": 0.25,        # azot çekilmesi (yaprak yaşlanması)
    "lai_dususu": 0.20,         # yaprak alanı gerilemesi
    "gdd_birikimi": 0.20,       # ısı birikimi hedefe ulaştı mı
}
TARGET_GDD_HARVEST = 2400.0     # pancar için tipik hasat GDD birikimi (baz 3 °C)


# =====================================================================
# POLAR TAHMİNİ
# =====================================================================

def _clamp_polar(v: float) -> float:
    return round(max(POLAR_MIN, min(POLAR_MAX, v)), 2)


def predict_polar(history: List[Dict[str, Any]], indices: Optional[Dict[str, Any]] = None,
                  soil: Optional[Dict[str, Any]] = None,
                  water_stress_days: Optional[int] = None) -> Dict[str, Any]:
    """Hasat poları tahmini + katkı dökümü.

    Katkılar (hepsi baz değerin ÜZERİNE eklenir/çıkarılır):
      * parselin kendi geçmiş ortalaması — en güçlü sinyal
      * sezon ortası NDRE/CCCI: yüksek azot = geç yaprak gelişimi = DÜŞÜK polar
      * geç dönem NDVI düşüşü: erken yaşlanma = şeker birikimi başlamış
      * toprak K (potasyum): şeker taşınımının anahtarı
      * ölçülü su stresi: hasat öncesi hafif stres poları YÜKSELTİR
    """
    contributions: List[Dict[str, Any]] = []
    gaps: List[str] = []

    past = [h.get("polar_oran") for h in (history or []) if h.get("polar_oran")]
    if past:
        base = statistics.mean(past)
        contributions.append({"etken": "Parselin geçmiş polar ortalaması",
                              "deger": round(base, 2), "katki": 0.0,
                              "aciklama": f"{len(past)} sezonluk kayıt"})
        spread = statistics.pstdev(past) if len(past) > 1 else 1.2
    else:
        base = POLAR_BASELINE
        spread = 1.5
        gaps.append("Geçmiş polar kaydı yok — bölge ortalaması baz alındı")

    value = base

    if indices:
        ndre = indices.get("ndre")
        ccci = indices.get("ccci")
        ndvi = indices.get("ndvi")
        if ndre is not None:
            # Geç dönemde YÜKSEK NDRE = bitki hâlâ azot çekiyor, yaprakta
            # kalıyor → köke şeker gitmiyor. Negatif katkı.
            delta = -(ndre - 0.25) * 4.0
            delta = max(-1.5, min(1.5, delta))
            value += delta
            contributions.append({"etken": "NDRE (azot durumu)", "deger": ndre,
                                  "katki": round(delta, 2),
                                  "aciklama": "Geç dönemde yüksek azot polar oranını düşürür"})
        else:
            gaps.append("NDRE ölçümü yok")
        if ndvi is not None:
            # Geç dönemde DÜŞÜK NDVI = yaprak yaşlanmış = şeker birikimi ileri.
            delta = (0.55 - ndvi) * 2.0
            delta = max(-1.0, min(1.2, delta))
            value += delta
            contributions.append({"etken": "NDVI (yaprak yaşlanması)", "deger": ndvi,
                                  "katki": round(delta, 2),
                                  "aciklama": "Yaprak yaşlandıkça bitki şekeri köke taşır"})
        if ccci is not None:
            delta = max(-0.8, min(0.8, (0.65 - ccci) * 1.5))
            value += delta
            contributions.append({"etken": "CCCI (klorofil/azot dengesi)", "deger": ccci,
                                  "katki": round(delta, 2)})
    else:
        gaps.append("Uydu indeks ölçümü yok")

    if soil:
        k = soil.get("k_ppm")
        if k is not None:
            # Potasyum şeker taşınımının doğrudan girdisi (K eksikliğinde
            # şeker yaprakta kalır). 250 ppm üstü yeterli kabul edilir.
            delta = max(-1.0, min(0.8, (k - 250) / 250.0))
            value += delta
            contributions.append({"etken": "Toprak potasyumu (K)", "deger": k,
                                  "katki": round(delta, 2),
                                  "aciklama": "K, şekerin yapraktan köke taşınmasını sağlar"})
        n = soil.get("n_ppm")
        if n is not None and n > 35:
            delta = -min(1.2, (n - 35) / 25.0)
            value += delta
            contributions.append({"etken": "Toprak azotu (yüksek)", "deger": n,
                                  "katki": round(delta, 2),
                                  "aciklama": "Fazla azot yaprak büyütür, polar düşürür"})
    else:
        gaps.append("Toprak analizi yok")

    if water_stress_days is not None:
        # Hasat öncesi ÖLÇÜLÜ su kısıtı poları yükseltir; aşırısı verim düşürür.
        if 5 <= water_stress_days <= 20:
            value += 0.4
            contributions.append({"etken": "Hasat öncesi ölçülü su kısıtı",
                                  "deger": water_stress_days, "katki": 0.4,
                                  "aciklama": "Kontrollü su kesimi şeker birikimini artırır"})
        elif water_stress_days > 35:
            value -= 0.6
            contributions.append({"etken": "Uzun süreli su stresi",
                                  "deger": water_stress_days, "katki": -0.6,
                                  "aciklama": "Aşırı stres kök gelişimini durdurur"})

    # Güven aralığı: veri eksikliği arttıkça genişler.
    margin = round(spread + 0.4 * len(gaps), 2)
    return {
        "tahmin_polar": _clamp_polar(value),
        "alt_sinir": _clamp_polar(value - margin),
        "ust_sinir": _clamp_polar(value + margin),
        "guven": round(max(0.15, 1.0 - 0.15 * len(gaps)), 2),
        "katkilar": contributions,
        "veri_bosluklari": gaps,
        "yontem": "Açıklanabilir ağırlıklı model — her katkı ayrı gösterilir",
    }


# =====================================================================
# EKİM PENCERESİ
# =====================================================================

def soil_temperature_estimate(t_mean_c: Optional[float]) -> Optional[float]:
    """Hava sıcaklığından 10 cm toprak sıcaklığı tahmini.

    İlkbaharda toprak havadan yavaş ısınır; pratikte 10 cm derinlik günlük
    ortalama hava sıcaklığının ~1-2 °C altındadır. Gerçek toprak sensörü
    varsa (IoT) o kullanılmalı — bu yalnızca sensörsüz parseller içindir.
    """
    if t_mean_c is None:
        return None
    return round(t_mean_c - 1.5, 1)


def sowing_window(daily: List[Dict[str, Any]], today: Optional[date] = None) -> Dict[str, Any]:
    """Önümüzdeki günler için ekim uygunluğu.

    Bir gün 'uygun' sayılır ise: toprak sıcaklığı ≥ 6 °C, sonraki 5 günde
    ciddi don riski yok, o gün ve ertesi gün ağır yağış yok (tav/ıslak
    toprakta ekim makinesi çalışmaz, toprak sıkışır).
    """
    today = today or date.today()
    scored = []
    for i, d in enumerate(daily):
        try:
            day = date.fromisoformat(d["date"])
        except (KeyError, ValueError):
            continue
        if day < today:
            continue
        soil_t = soil_temperature_estimate(d.get("t_mean"))
        if soil_t is None:
            continue
        next5 = daily[i:i + 5]
        min_temp = min([x.get("t_min") for x in next5 if x.get("t_min") is not None], default=None)
        rain_2d = sum((x.get("rain_mm") or 0) for x in daily[i:i + 2])
        engeller = []
        if soil_t < SOWING["min_toprak_sicakligi_c"]:
            engeller.append(f"Toprak sıcaklığı düşük ({soil_t} °C < {SOWING['min_toprak_sicakligi_c']})")
        if min_temp is not None and min_temp <= SOWING["don_riski_esik_c"]:
            engeller.append(f"Önümüzdeki 5 günde don riski ({min_temp} °C)")
        if rain_2d > 15:
            engeller.append(f"Ekim gününde/ertesinde ağır yağış ({round(rain_2d, 1)} mm) — toprak tavı bozulur")
        if not (SOWING["en_erken_ay_gun"] <= (day.month, day.day) <= SOWING["en_gec_ay_gun"]):
            engeller.append("Takvim penceresi dışında (1 Mart – 10 Mayıs)")

        puan = 100
        if soil_t < SOWING["ideal_toprak_sicakligi_c"]:
            puan -= 15
        puan -= 25 * len(engeller)
        scored.append({"tarih": d["date"], "toprak_sicakligi_c": soil_t,
                       "min_sicaklik_5gun": min_temp, "yagis_2gun_mm": round(rain_2d, 1),
                       "uygun": not engeller, "puan": max(0, puan), "engeller": engeller})

    uygun = [s for s in scored if s["uygun"]]
    return {
        "gunler": scored,
        "ilk_uygun_gun": uygun[0]["tarih"] if uygun else None,
        "uygun_gun_sayisi": len(uygun),
        "en_iyi_gun": max(scored, key=lambda s: s["puan"])["tarih"] if scored else None,
        "oneri": ("Ekim için uygun pencere açık." if uygun else
                  "Tahmin döneminde ekim için uygun gün yok — koşullar izleniyor."),
    }


# =====================================================================
# OLGUNLAŞMA ENDEKSİ / SÖKÜM ZAMANI
# =====================================================================

def maturity_index(series: List[Dict[str, Any]], gdd_total: Optional[float] = None) -> Dict[str, Any]:
    """0-100 olgunlaşma endeksi — 100 = söküm olgunluğu.

    Girdi `series`: tarih sıralı çok-indeksli uydu ölçümleri (ndvi/ndre/lai).
    """
    points = [p for p in (series or []) if p.get("date")]
    points.sort(key=lambda p: p["date"])
    if len(points) < 3:
        return {"endeks": None, "guven": 0.0,
                "sebep": "Yeterli uydu ölçümü yok (en az 3 gözlem)"}

    def _peak_and_last(key: str) -> Tuple[Optional[float], Optional[float]]:
        vals = [(p["date"], p.get(key)) for p in points if p.get(key) is not None]
        if not vals:
            return None, None
        peak = max(v for _, v in vals)
        return peak, vals[-1][1]

    parts, weights_used = {}, 0.0
    score = 0.0

    ndvi_peak, ndvi_last = _peak_and_last("ndvi")
    if ndvi_peak and ndvi_last is not None and ndvi_peak > 0:
        drop = max(0.0, (ndvi_peak - ndvi_last) / ndvi_peak)
        # %30 düşüş ≈ tam olgunlaşma sinyali
        part = min(1.0, drop / 0.30)
        score += part * MATURITY_WEIGHTS["ndvi_dususu"]
        weights_used += MATURITY_WEIGHTS["ndvi_dususu"]
        parts["ndvi_dususu"] = {"zirve": round(ndvi_peak, 3), "guncel": round(ndvi_last, 3),
                                "dusus_yuzde": round(drop * 100, 1)}

    ndre_peak, ndre_last = _peak_and_last("ndre")
    if ndre_peak and ndre_last is not None and ndre_peak > 0:
        drop = max(0.0, (ndre_peak - ndre_last) / ndre_peak)
        part = min(1.0, drop / 0.35)
        score += part * MATURITY_WEIGHTS["ndre_dususu"]
        weights_used += MATURITY_WEIGHTS["ndre_dususu"]
        parts["ndre_dususu"] = {"zirve": round(ndre_peak, 3), "guncel": round(ndre_last, 3),
                                "dusus_yuzde": round(drop * 100, 1),
                                "anlam": "Azot çekilmesi — yaprak yaşlanıyor, şeker köke gidiyor"}

    lai_peak, lai_last = _peak_and_last("lai")
    if lai_peak and lai_last is not None and lai_peak > 0:
        drop = max(0.0, (lai_peak - lai_last) / lai_peak)
        part = min(1.0, drop / 0.35)
        score += part * MATURITY_WEIGHTS["lai_dususu"]
        weights_used += MATURITY_WEIGHTS["lai_dususu"]
        parts["lai_dususu"] = {"zirve": round(lai_peak, 2), "guncel": round(lai_last, 2),
                               "dusus_yuzde": round(drop * 100, 1)}

    if gdd_total is not None:
        part = min(1.0, gdd_total / TARGET_GDD_HARVEST)
        score += part * MATURITY_WEIGHTS["gdd_birikimi"]
        weights_used += MATURITY_WEIGHTS["gdd_birikimi"]
        parts["gdd_birikimi"] = {"birikim": round(gdd_total, 1), "hedef": TARGET_GDD_HARVEST,
                                 "tamamlanma_yuzde": round(part * 100, 1)}

    if weights_used == 0:
        return {"endeks": None, "guven": 0.0, "sebep": "Olgunlaşma göstergesi hesaplanamadı"}

    index = round(score / weights_used * 100, 1)
    return {
        "endeks": index,
        "guven": round(weights_used, 2),
        "bilesenler": parts,
        "sinif": ("olgun" if index >= 80 else "olgunlaşıyor" if index >= 55 else
                  "gelişme" if index >= 30 else "erken"),
        "son_olcum_tarihi": points[-1]["date"],
    }


def harvest_window(maturity: Dict[str, Any], polar: Dict[str, Any],
                   daily: Optional[List[Dict[str, Any]]] = None,
                   last_measurement: Optional[str] = None) -> Dict[str, Any]:
    """Optimum söküm tarih aralığı.

    Mantık: olgunlaşma endeksi 100'e yaklaştıkça söküm yaklaşır. Endeks
    ilerleme hızı (son ölçümlerden) ile 100'e kalan gün kestirilir; hava
    (yağış/don) uygun olmayan günler pencereden çıkarılır — ıslak toprakta
    söküm hem makineyi batırır hem kökte toprak/fire oranını yükseltir.
    """
    idx = maturity.get("endeks")
    if idx is None:
        return {"available": False, "sebep": maturity.get("sebep", "Olgunlaşma endeksi yok")}

    # Kaba ilerleme: pancarda olgunlaşma son 6 haftada hızlanır, günde ~1,2 puan.
    remaining = max(0.0, 100.0 - idx)
    days_to_maturity = int(round(remaining / 1.2))
    base = date.fromisoformat(last_measurement) if last_measurement else date.today()
    start = base + timedelta(days=days_to_maturity)
    end = start + timedelta(days=21)          # söküm penceresi ~3 hafta açık kalır

    engeller = []
    if daily:
        window_days = [d for d in daily if start.isoformat() <= d.get("date", "") <= end.isoformat()]
        heavy_rain = [d["date"] for d in window_days if (d.get("rain_mm") or 0) > 20]
        frost = [d["date"] for d in window_days if (d.get("t_min") is not None and d["t_min"] <= -3)]
        if heavy_rain:
            engeller.append(f"Ağır yağış beklenen günler: {', '.join(heavy_rain[:3])}")
        if frost:
            engeller.append(f"Kök donma riski: {', '.join(frost[:3])}")

    return {
        "available": True,
        "olgunlasma_endeksi": idx,
        "tahmini_olgunluk_tarihi": start.isoformat(),
        "onerilen_baslangic": start.isoformat(),
        "onerilen_bitis": end.isoformat(),
        "kalan_gun": days_to_maturity,
        "beklenen_polar": polar.get("tahmin_polar"),
        "polar_araligi": [polar.get("alt_sinir"), polar.get("ust_sinir")],
        "engeller": engeller,
        "oneri": ("Söküm olgunluğuna ulaşıldı — hasat planlanabilir." if idx >= 80 else
                  f"Olgunlaşma sürüyor; tahminen {days_to_maturity} gün sonra söküm penceresi açılır."),
    }


# =====================================================================
# ANA GİRİŞ NOKTASI + HTTP
# =====================================================================

async def analyze_parcel_harvest(db, parcel: Dict[str, Any], season: Optional[int] = None,
                                 crop_key: str = "pancar") -> Dict[str, Any]:
    from weather import get_parcel_weather

    season = season or date.today().year
    history = await db.yields.find({"parcel_id": parcel["id"]}, {"_id": 0}).sort(
        [("season", -1)]).limit(8).to_list(8)
    stat = await db.remote_sensing_statistics.find_one(
        {"parcel_id": parcel["id"]}, {"_id": 0}, sort=[("created_at", -1)])
    series = (stat or {}).get("series") or []
    latest_indices = (parcel.get("remote_sensing") or {}).get("last_indices") or {}
    soil = await db.soil_samples.find_one({"parcel_id": parcel["id"]}, {"_id": 0},
                                          sort=[("sample_date", -1)])

    weather = await get_parcel_weather(db, parcel, crop_key)
    daily = weather.get("daily") if weather.get("available") else []
    gdd_total = (weather.get("summary") or {}).get("gdd_son_30_gun")

    # Sezon başından bu yana GDD birikimi — ekim tarihinden itibaren.
    planting = await db.plantings.find_one({"parcel_id": parcel["id"], "season": season},
                                           {"_id": 0}, sort=[("season", -1)])
    season_gdd = None
    if planting and planting.get("planting_date") and daily:
        pd = planting["planting_date"]
        from weather import accumulate_gdd, base_temp_for
        season_days = [d for d in daily if d["date"] >= pd]
        # Not: Open-Meteo yalnızca son ~90 günü veriyor; daha eski dönem için
        # ERA5 gerekir. Bu yüzden değer "en az bu kadar" anlamındadır.
        season_gdd = accumulate_gdd(season_days, base_temp_for(crop_key))

    polar = predict_polar(history, latest_indices, soil,
                          water_stress_days=None)
    maturity = maturity_index(series, season_gdd if season_gdd else gdd_total)
    window = harvest_window(maturity, polar, daily, maturity.get("son_olcum_tarihi"))

    return {
        "available": True,
        "parcel_id": parcel["id"],
        "season": season,
        "polar_tahmini": polar,
        "olgunlasma": maturity,
        "sokum_penceresi": window,
        "gdd_sezon": season_gdd,
    }


def register_polar_routes(api_router, db, current_user, require_permission,
                          log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/polar/parcels/{parcel_id}")
    async def parcel_polar(parcel_id: str, season: Optional[int] = None, crop: str = "pancar",
                           user=Depends(require_permission("parcels:view"))):
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        return await analyze_parcel_harvest(db, parcel, season, crop)

    @api_router.get("/polar/parcels/{parcel_id}/sowing-window")
    async def parcel_sowing(parcel_id: str, crop: str = "pancar",
                            user=Depends(require_permission("parcels:view"))):
        from weather import get_parcel_weather
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        weather = await get_parcel_weather(db, parcel, crop)
        if not weather.get("available"):
            return {"available": False, "reason": weather.get("reason")}
        return {"available": True, **sowing_window(weather["daily"])}
