"""
=====================================================================
TOPRAX — Su Bütçesi Danışmanı (FAO-56 toprak su dengesi)
=====================================================================
Kullanıcının şartı: "Elimizdeki verilerle birlikte değerlendirilebilsin —
ürün çeşidi + tohum türü + laboratuvar sonuçları + güneş vb."

Bu modül tam olarak bunu yapar: sulama önerisi TEK bir kaynaktan değil,
dört ölçümün birleşiminden çıkar.

  ETc  = ET0 × Kc(fenolojik aşama)        ← ET0: Open-Meteo, Kc: ürün/aşama
  TAW  = (FC − WP) × kök derinliği         ← FC/WP: laboratuvar toprak dokusu
  RAW  = TAW × p                           ← p: ürünün izin verdiği tüketim payı
  Denge= önceki açık + ETc − etkili yağış − uygulanan sulama
  Öneri= açık ≥ RAW olduğunda sula, miktar = açığı kapatacak mm → m³

FAO-56 (Allen ve ark., 1998) yöntemi budur; her adım ölçülmüş bir girdiye
dayanır, hiçbir sabit "tahmin" yerine geçmez. Ölçüm eksikse o adım için
tipik değer kullanılır AMA çıktıda `varsayimlar` listesinde AÇIKÇA bildirilir
(veri güven rozetinin — confidence.py — girdisi).
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException

# =====================================================================
# ÜRÜN KATSAYILARI (FAO-56 Tablo 12 + Türkiye koşullarına uyarlama)
# =====================================================================
# Kc: bitki katsayısı — ETc = ET0 × Kc. Aşamalar:
#   baslangic (ekim-çıkış), gelisme (yaprak gelişimi),
#   orta (tam örtü / kök büyümesi), son (olgunlaşma-hasat)
# p: toprakta tutulan suyun bitki strese girmeden kullanabildiği payı.
# kok_derinlik_m: etkin kök derinliği (su alınan katman).
CROP_WATER = {
    "pancar": {"kc": {"baslangic": 0.35, "gelisme": 0.80, "orta": 1.20, "son": 0.90},
               "p": 0.55, "kok_derinlik_m": 1.0,
               "not": "Şeker pancarı yüksek su isteyen bir üründür; orta dönemde Kc 1.2'ye çıkar. "
                      "Hasat öncesi son 3-4 hafta su kesilir — bu, polar (şeker) oranını yükseltir."},
    "bugday": {"kc": {"baslangic": 0.40, "gelisme": 0.75, "orta": 1.15, "son": 0.35},
               "p": 0.55, "kok_derinlik_m": 1.2},
    "arpa": {"kc": {"baslangic": 0.40, "gelisme": 0.75, "orta": 1.10, "son": 0.30},
             "p": 0.55, "kok_derinlik_m": 1.1},
    "misir": {"kc": {"baslangic": 0.35, "gelisme": 0.80, "orta": 1.20, "son": 0.60},
              "p": 0.50, "kok_derinlik_m": 1.0},
    "aycicegi": {"kc": {"baslangic": 0.35, "gelisme": 0.75, "orta": 1.15, "son": 0.45},
                 "p": 0.45, "kok_derinlik_m": 1.2},
    "patates": {"kc": {"baslangic": 0.45, "gelisme": 0.80, "orta": 1.15, "son": 0.75},
                "p": 0.35, "kok_derinlik_m": 0.5},
    "yonca": {"kc": {"baslangic": 0.40, "gelisme": 0.85, "orta": 1.05, "son": 0.90},
              "p": 0.55, "kok_derinlik_m": 1.3},
}
DEFAULT_WATER = {"kc": {"baslangic": 0.40, "gelisme": 0.80, "orta": 1.10, "son": 0.60},
                 "p": 0.50, "kok_derinlik_m": 1.0}

#: Toprak dokusuna göre tarla kapasitesi (FC) ve solma noktası (WP), hacim %.
#: Laboratuvar analizi (kum/kil/silt yüzdesi) varsa doku BUNDAN türetilir.
SOIL_WATER = {
    "kumlu":        {"fc": 0.12, "wp": 0.05},
    "kumlu-tinli":  {"fc": 0.18, "wp": 0.08},
    "tinli":        {"fc": 0.26, "wp": 0.12},
    "killi-tinli":  {"fc": 0.32, "wp": 0.17},
    "killi":        {"fc": 0.38, "wp": 0.22},
    "organik":      {"fc": 0.40, "wp": 0.18},
}
DEFAULT_SOIL = {"fc": 0.28, "wp": 0.14}

#: Sulama yönteminin uygulama randımanı — tarlaya verilen suyun bitkiye
#: ulaşan oranı. Aynı açığı kapatmak karıkta damladan ~%40 fazla su ister.
IRRIGATION_EFFICIENCY = {
    "damla": 0.90, "yagmurlama": 0.75, "karik": 0.60, "salma": 0.50,
}
DEFAULT_EFFICIENCY = 0.65


# =====================================================================
# SAF HESAPLAR
# =====================================================================

def soil_texture_from_lab(sample: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, float], bool]:
    """Laboratuvar kum/kil/silt yüzdesinden toprak dokusu.

    Döner: (doku adı, {fc, wp}, ölçüldü mü). Analiz yoksa parselin
    `soil_type` alanına, o da yoksa tipik değere düşülür — ve `False`
    döndürerek "bu bir varsayım" bilgisi çağırana taşınır.
    """
    if sample:
        kil = sample.get("kil_yuzde")
        kum = sample.get("kum_yuzde")
        if kil is not None and kum is not None:
            if kil >= 40:
                name = "killi"
            elif kil >= 27:
                name = "killi-tinli"
            elif kum >= 70:
                name = "kumlu"
            elif kum >= 50:
                name = "kumlu-tinli"
            else:
                name = "tinli"
            return name, SOIL_WATER[name], True
    return "bilinmiyor", DEFAULT_SOIL, False


def normalize_soil_name(soil_type: Optional[str]) -> Optional[str]:
    if not soil_type:
        return None
    s = soil_type.lower().replace("ı", "i").replace("ğ", "g").replace("ş", "s")
    s = s.replace("ö", "o").replace("ü", "u").replace("ç", "c").replace(" ", "")
    return s if s in SOIL_WATER else None


def total_available_water_mm(fc: float, wp: float, root_depth_m: float) -> float:
    """TAW — kök bölgesinde tutulabilen toplam yarayışlı su (mm).

    (FC − WP) hacimsel oran; × derinlik(m) × 1000 → mm.
    """
    return round(max(0.0, (fc - wp)) * root_depth_m * 1000.0, 1)


def readily_available_water_mm(taw_mm: float, p: float) -> float:
    """RAW — bitki strese GİRMEDEN kullanabileceği kısım. Sulama eşiği budur."""
    return round(taw_mm * p, 1)


def stage_for(days_after_planting: Optional[int], crop_key: str = "pancar") -> str:
    """Ekimden geçen güne göre fenolojik aşama (Kc bundan seçilir).

    Şeker pancarı için tipik uzunluklar: başlangıç 30 gün, gelişme 45 gün,
    orta dönem 90 gün, son dönem 30 gün (~195 gün toplam vejetasyon).
    """
    if days_after_planting is None:
        return "orta"
    d = days_after_planting
    if d < 30:
        return "baslangic"
    if d < 75:
        return "gelisme"
    if d < 165:
        return "orta"
    return "son"


def water_balance(daily: List[Dict[str, Any]], kc: float, raw_mm: float,
                  taw_mm: float, applied_mm_by_date: Optional[Dict[str, float]] = None,
                  start_depletion_mm: float = 0.0) -> Dict[str, Any]:
    """Gün gün toprak su açığı takibi.

    Açık (depletion) 0 = tarla kapasitesi (dolu), TAW = solma noktası.
    Açık RAW'ı geçtiğinde bitki su stresine girer — sulama tam bu noktada
    önerilir, "takvime göre" değil.
    """
    depletion = start_depletion_mm
    applied = applied_mm_by_date or {}
    timeline, stress_days, first_stress = [], 0, None
    for d in daily:
        et0 = d.get("et0_mm") or 0.0
        etc = et0 * kc
        rain = d.get("effective_rain_mm")
        if rain is None:
            from weather import effective_rain_mm
            rain = effective_rain_mm(d.get("rain_mm"))
        irr = applied.get(d["date"], 0.0)
        depletion = max(0.0, min(taw_mm, depletion + etc - rain - irr))
        stressed = depletion > raw_mm
        if stressed:
            stress_days += 1
            if first_stress is None:
                first_stress = d["date"]
        timeline.append({
            "date": d["date"], "etc_mm": round(etc, 2), "etkili_yagis_mm": round(rain, 2),
            "sulama_mm": round(irr, 2), "acik_mm": round(depletion, 1), "stres": stressed,
        })
    return {"acik_mm": round(depletion, 1), "zaman_cizgisi": timeline,
            "stres_gun_sayisi": stress_days, "ilk_stres_tarihi": first_stress}


def irrigation_recommendation(depletion_mm: float, raw_mm: float, taw_mm: float,
                              area_dekar: Optional[float], efficiency: float,
                              timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sulama önerisi: ne zaman, kaç mm, kaç m³.

    Net ihtiyaç açığın tamamını kapatır (tarla kapasitesine getirir); brüt
    ihtiyaç bunu yöntem randımanına böler — çiftçinin pompadan geçirmesi
    gereken gerçek su miktarı budur.
    """
    net_mm = round(max(0.0, depletion_mm), 1)
    gross_mm = round(net_mm / efficiency, 1) if efficiency else None
    # 1 mm = 1 L/m² → 1 dekar (1000 m²) için 1 m³
    net_m3 = round(net_mm * area_dekar, 1) if area_dekar else None
    gross_m3 = round(gross_mm * area_dekar, 1) if (gross_mm and area_dekar) else None

    gerekli = depletion_mm >= raw_mm
    next_stress = next((t["date"] for t in timeline if t["stres"]), None)
    if gerekli:
        aciliyet, mesaj = "acil", "Toprak su açığı kritik eşiği (RAW) aştı — sulama şimdi yapılmalı."
    elif next_stress:
        aciliyet = "yaklasiyor"
        mesaj = f"Tahmine göre {next_stress} tarihinde su stresi bekleniyor; sulama o güne planlanmalı."
    else:
        aciliyet, mesaj = "gerekmiyor", "Önümüzdeki tahmin döneminde su stresi beklenmiyor."

    return {
        "sulama_gerekli": gerekli,
        "aciliyet": aciliyet,
        "mesaj": mesaj,
        "net_ihtiyac_mm": net_mm,
        "brut_ihtiyac_mm": gross_mm,
        "net_ihtiyac_m3": net_m3,
        "brut_ihtiyac_m3": gross_m3,
        "randiman": efficiency,
        "kritik_esik_mm": raw_mm,
        "toplam_kapasite_mm": taw_mm,
        "doluluk_yuzde": round(max(0.0, (1 - depletion_mm / taw_mm)) * 100, 1) if taw_mm else None,
        "beklenen_stres_tarihi": next_stress,
    }


# =====================================================================
# VERİ TOPLAMA + ANA GİRİŞ NOKTASI
# =====================================================================

async def analyze_parcel_water(db, parcel: Dict[str, Any], crop_key: str = "pancar",
                               season: Optional[int] = None) -> Dict[str, Any]:
    """Parselin su bütçesi — hava, toprak analizi, ekim ve sulama kayıtlarından."""
    from weather import get_parcel_weather

    weather = await get_parcel_weather(db, parcel, crop_key)
    if not weather.get("available"):
        return {"available": False, "reason": weather.get("reason", "Hava verisi alınamadı")}

    varsayimlar: List[str] = []
    season = season or date.today().year

    # --- Toprak: laboratuvar analizi > parsel toprak tipi > tipik değer ---
    sample = await db.soil_samples.find_one({"parcel_id": parcel["id"]}, {"_id": 0},
                                            sort=[("sample_date", -1)])
    texture, water_holding, measured = soil_texture_from_lab(sample)
    if not measured:
        fallback = normalize_soil_name(parcel.get("soil_type"))
        if fallback:
            texture, water_holding = fallback, SOIL_WATER[fallback]
            varsayimlar.append("Toprak su kapasitesi laboratuvar analizinden değil, "
                               f"parseldeki '{parcel.get('soil_type')}' toprak tipi kaydından türetildi.")
        else:
            varsayimlar.append("Toprak analizi yok — tipik tınlı toprak değerleri kullanıldı.")

    # --- Ekim: aşama ve Kc ---
    planting = await db.plantings.find_one({"parcel_id": parcel["id"], "season": season}, {"_id": 0},
                                           sort=[("season", -1)])
    days_after = None
    if planting and planting.get("planting_date"):
        try:
            pd = date.fromisoformat(planting["planting_date"])
            days_after = (date.today() - pd).days
        except ValueError:
            pass
    if days_after is None:
        varsayimlar.append("Ekim tarihi bilinmiyor — bitki 'orta dönem' kabul edildi (en yüksek su ihtiyacı).")
    stage = stage_for(days_after, crop_key)

    crop_cfg = CROP_WATER.get(crop_key.lower(), DEFAULT_WATER)
    kc = crop_cfg["kc"][stage]
    taw = total_available_water_mm(water_holding["fc"], water_holding["wp"], crop_cfg["kok_derinlik_m"])
    raw = readily_available_water_mm(taw, crop_cfg["p"])

    # --- Uygulanan sulamalar (son 60 gün) ---
    since = (date.today() - timedelta(days=60)).isoformat()
    events = await db.irrigation_events.find(
        {"parcel_id": parcel["id"], "date": {"$gte": since}}, {"_id": 0}).to_list(500)
    area = parcel.get("area_dekar") or 0
    applied: Dict[str, float] = {}
    for ev in events:
        # m³ → mm: 1 m³ / 1 dekar = 1 mm
        mm = (ev.get("water_m3") or 0) / area if area else 0
        applied[ev.get("date")] = applied.get(ev.get("date"), 0) + mm
    if not events:
        varsayimlar.append("Bu parselde son 60 günde sulama kaydı yok — hesap 'hiç sulanmadı' varsayar.")

    method = (parcel.get("irrigation") or "").lower()
    efficiency = IRRIGATION_EFFICIENCY.get(
        method.replace("ı", "i").replace("ğ", "g").replace("ş", "s"), DEFAULT_EFFICIENCY)

    balance = water_balance(weather["daily"], kc, raw, taw, applied)
    today = date.today().isoformat()
    past_timeline = [t for t in balance["zaman_cizgisi"] if t["date"] <= today]
    future_timeline = [t for t in balance["zaman_cizgisi"] if t["date"] > today]
    current_depletion = past_timeline[-1]["acik_mm"] if past_timeline else 0.0

    rec = irrigation_recommendation(current_depletion, raw, taw, area, efficiency, future_timeline)

    return {
        "available": True,
        "parcel_id": parcel["id"],
        "urun": crop_key,
        "fenolojik_asama": stage,
        "kc": kc,
        "toprak": {"doku": texture, "tarla_kapasitesi": water_holding["fc"],
                   "solma_noktasi": water_holding["wp"], "laboratuvardan": measured,
                   "kok_derinlik_m": crop_cfg["kok_derinlik_m"]},
        "kapasite": {"taw_mm": taw, "raw_mm": raw, "guncel_acik_mm": current_depletion},
        "oneri": rec,
        "hava_ozeti": weather.get("summary"),
        "gecmis": past_timeline[-14:],
        "tahmin": future_timeline,
        "varsayimlar": varsayimlar,
        "not": crop_cfg.get("not"),
    }


def register_water_budget_routes(api_router, db, current_user, require_permission,
                                 log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/water-budget/parcels/{parcel_id}")
    async def parcel_water(parcel_id: str, crop: str = "pancar", season: Optional[int] = None,
                           user=Depends(require_permission("parcels:view"))):
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        return await analyze_parcel_water(db, parcel, crop, season)

    @api_router.get("/water-budget/crops")
    async def water_crops(user=Depends(current_user)):
        """Ürün su katsayıları — ekran bunları gösterir, hardcode etmez."""
        return {"crops": CROP_WATER, "toprak": SOIL_WATER, "randiman": IRRIGATION_EFFICIENCY}
