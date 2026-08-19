"""
=====================================================================
TOPRAX — Hava Servisi (Open-Meteo + ERA5-Land) ve Büyüme Derece-Gün
=====================================================================
CLAUDE.md konvansiyon #1: `register_weather_routes(api_router, db,
current_user, require_permission, log_audit, require_feature)`.

NEDEN İKİ KAYNAK (kullanıcı kararı: "ikisi birlikte"):
  * **Open-Meteo** — anahtar GEREKTİRMEZ, güncel gözlem + 16 günlük TAHMİN
    verir (sıcaklık, yağış, referans buharlaşma ET0, güneş radyasyonu).
    Karar desteğinin "önümüzdeki hafta ne yapmalıyım" tarafı buna dayanır.
  * **ERA5-Land** (Google Earth Engine üzerinden) — geçmiş/iklim normalleri.
    Tahmin ÜRETMEZ ve ~5 gün gecikmelidir; buna karşılık 1950'ye kadar giden
    tutarlı bir arşivdir, "bu yıl normalin ne kadar üstünde/altında" sorusu
    ancak bununla yanıtlanır.

MİMARİ KURAL: Bu modül SADECE hava verisi getirir ve saf tarımsal hesapları
(GDD, etkili yağış) yapar. Tavsiye ÜRETMEZ — onu kural motoru (agronomy.py) ve
Sezon Karar Takvimi (season_planner.py) yapar. Böylece "veri katmanı" ile
"karar katmanı" ayrı kalır (satellite_provider/remote_sensing ayrımıyla AYNI).

ÖNBELLEK: Aynı parsel için günde onlarca istek gelebilir (harita, karar
takvimi, mobil). `weather_cache` koleksiyonunda koordinat+gün bazlı saklanır;
`cache.py`'nin süreç-içi TTL'i YETMEZ çünkü veri süreçler arası paylaşılmalı
ve gün boyu geçerli.
"""
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import Depends, HTTPException

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
ERA5_COLLECTION = "ECMWF/ERA5_LAND/DAILY_AGGR"
HTTP_TIMEOUT = 20
CACHE_HOURS = 6

#: Şeker pancarı taban sıcaklığı (°C). Literatürde 3-5 °C aralığı kullanılır;
#: 3 °C, Türkiye şeker pancarı üretiminde yaygın kabul edilen değerdir.
#: Ürün bazlı taban sıcaklıklar — GDD hesabı ürüne göre değişir.
CROP_BASE_TEMP = {
    "pancar": 3.0, "bugday": 0.0, "arpa": 0.0, "misir": 10.0,
    "aycicegi": 6.0, "patates": 7.0, "yonca": 5.0,
}
DEFAULT_BASE_TEMP = 5.0


# =====================================================================
# SAF FONKSİYONLAR — DB/HTTP bağımsız, test edilebilir
# =====================================================================

def growing_degree_days(t_max: Optional[float], t_min: Optional[float],
                        base: float = DEFAULT_BASE_TEMP,
                        upper: Optional[float] = 30.0) -> Optional[float]:
    """Tek günün büyüme derece-günü (GDD).

    Klasik formül: ((Tmax + Tmin) / 2) − Tbase, negatifse 0.
    `upper` (üst kesme) verilirse Tmax bu değere kırpılır — sıcaklık bitkinin
    optimum aralığının üstüne çıktığında büyüme artık hızlanmaz, hatta durur;
    kırpma yapılmazsa sıcak günler birikimi yapay olarak şişirir.
    """
    if t_max is None or t_min is None:
        return None
    hi = min(t_max, upper) if upper is not None else t_max
    lo = max(t_min, base)          # taban altındaki saatler büyümeye katkı vermez
    mean = (hi + lo) / 2.0
    return round(max(0.0, mean - base), 2)


def accumulate_gdd(daily: List[Dict[str, Any]], base: float = DEFAULT_BASE_TEMP) -> float:
    """Günlük kayıtlardan toplam GDD (birikim)."""
    total = 0.0
    for d in daily:
        g = growing_degree_days(d.get("t_max"), d.get("t_min"), base)
        if g:
            total += g
    return round(total, 1)


def effective_rain_mm(rain_mm: Optional[float]) -> float:
    """Etkili yağış (bitkinin gerçekten kullanabildiği kısım).

    USDA-SCS basitleştirmesi: 5 mm'nin altındaki yağış yüzeyden buharlaşır ve
    bitkiye ulaşmaz; büyük yağışların bir kısmı yüzey akışı/derine sızma ile
    kaybolur. Ham yağışı olduğu gibi su bütçesinden düşmek sulama ihtiyacını
    sistematik olarak OLDUĞUNDAN AZ gösterirdi.
    """
    if not rain_mm or rain_mm < 5:
        return 0.0
    return round(min(rain_mm * 0.8, rain_mm - 2.0), 2)


def frost_risk(t_min: Optional[float]) -> Optional[str]:
    """Don riski sınıfı — ekim penceresi kararının girdisi."""
    if t_min is None:
        return None
    if t_min <= -2:
        return "yuksek"
    if t_min <= 0:
        return "orta"
    if t_min <= 2:
        return "dusuk"
    return None


def base_temp_for(crop_key: Optional[str]) -> float:
    return CROP_BASE_TEMP.get((crop_key or "").lower(), DEFAULT_BASE_TEMP)


def centroid_of(geometry: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float]]:
    """GeoJSON geometrisinin kaba merkezi (lon, lat)."""
    if not geometry:
        return None
    pts: List[List[float]] = []

    def walk(node):
        if isinstance(node, (int, float)):
            return
        if node and isinstance(node[0], (int, float)):
            pts.append(node)
            return
        for child in node:
            walk(child)

    walk(geometry.get("coordinates") or [])
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


# =====================================================================
# OPEN-METEO
# =====================================================================

def fetch_open_meteo(lat: float, lon: float, past_days: int = 30,
                     forecast_days: int = 16) -> Dict[str, Any]:
    """Günlük hava serisi (geçmiş + tahmin) — TEK istekte.

    `past_days` Open-Meteo'nun tahmin ucunda desteklenen bir parametredir
    (92 güne kadar); ayrı bir arşiv çağrısı gerekmez, böylece hem istek sayısı
    hem gecikme yarıya iner.
    """
    params = {
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
            "precipitation_sum", "et0_fao_evapotranspiration",
            "shortwave_radiation_sum", "wind_speed_10m_max",
            "relative_humidity_2m_mean",
        ]),
        "timezone": "Europe/Istanbul",
        "past_days": min(past_days, 92),
        "forecast_days": min(forecast_days, 16),
    }
    resp = requests.get(OPEN_METEO_FORECAST, params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json().get("daily") or {}
    days = data.get("time") or []
    out = []
    for i, day in enumerate(days):
        def _get(key):
            arr = data.get(key) or []
            return arr[i] if i < len(arr) else None
        out.append({
            "date": day,
            "t_max": _get("temperature_2m_max"),
            "t_min": _get("temperature_2m_min"),
            "t_mean": _get("temperature_2m_mean"),
            "rain_mm": _get("precipitation_sum"),
            "et0_mm": _get("et0_fao_evapotranspiration"),
            "radiation_mj_m2": _get("shortwave_radiation_sum"),
            "wind_max_kmh": _get("wind_speed_10m_max"),
            "humidity_pct": _get("relative_humidity_2m_mean"),
        })
    return {"source": "open-meteo", "daily": out}


# =====================================================================
# ERA5-LAND (Google Earth Engine) — geçmiş iklim normalleri
# =====================================================================

async def era5_normals(db, geometry: Dict[str, Any], years: int = 10) -> Dict[str, Any]:
    """Son `years` yılın aylık sıcaklık/yağış normalleri.

    GEE kimlik bilgisi yoksa/başarısızsa BOŞ döner — çağıran ekran bunu
    "normal verisi yok" olarak gösterir, uydurma bir ortalama üretilmez
    (gee_hls/service.py'nin AYNI dürüstlük kuralı).
    """
    from remote_sensing.providers.gee_hls.service import _ee_initialize, _gee_credentials
    real, email, key_json, project = await _gee_credentials(db)
    if not real:
        return {"available": False, "reason": "Earth Engine kimlik bilgisi yok", "monthly": []}
    try:
        _ee_initialize(email, key_json, project)
        import ee
        geom = ee.Geometry(geometry)
        end = date.today()
        start = date(end.year - years, 1, 1)
        coll = (ee.ImageCollection(ERA5_COLLECTION)
                .filterDate(start.isoformat(), end.isoformat())
                .select(["temperature_2m", "total_precipitation_sum"]))

        def _monthly(month):
            month = ee.Number(month)
            sub = coll.filter(ee.Filter.calendarRange(month, month, "month"))
            img = sub.mean()
            stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom,
                                     scale=11132, maxPixels=1e9)
            return ee.Feature(None, {
                "month": month,
                "t_mean_k": stats.get("temperature_2m"),
                "rain_m": stats.get("total_precipitation_sum"),
            })

        feats = ee.FeatureCollection(ee.List.sequence(1, 12).map(_monthly)).getInfo()
        monthly = []
        for f in feats.get("features", []):
            p = f.get("properties") or {}
            t_k = p.get("t_mean_k")
            rain_m = p.get("rain_m")
            monthly.append({
                "month": int(p.get("month") or 0),
                # ERA5 sıcaklığı KELVIN, yağışı METRE cinsindendir — ham
                # değerleri göstermek "23000 mm yağış" gibi saçmalık üretir.
                "t_mean_c": round(t_k - 273.15, 1) if t_k is not None else None,
                "rain_mm_gun": round(rain_m * 1000, 2) if rain_m is not None else None,
            })
        return {"available": True, "years": years, "monthly": monthly}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"ERA5 sorgusu başarısız: {e}", "monthly": []}


# =====================================================================
# ÖNBELLEKLİ ERİŞİM — diğer modüllerin kullandığı giriş noktası
# =====================================================================

async def get_parcel_weather(db, parcel: Dict[str, Any], crop_key: Optional[str] = None,
                             force: bool = False) -> Dict[str, Any]:
    """Parselin hava serisi + GDD birikimi (önbellekli).

    Diğer modüller (su bütçesi, sezon karar takvimi, ekim penceresi) BU
    fonksiyonu çağırır; hiçbiri Open-Meteo'ya doğrudan gitmez.
    """
    center = centroid_of(parcel.get("geometry"))
    if not center:
        return {"available": False, "reason": "Parselin sınır geometrisi yok"}
    lon, lat = center
    key = f"{round(lat, 2)},{round(lon, 2)}"
    now = datetime.now(timezone.utc)

    if not force:
        cached = await db.weather_cache.find_one({"key": key}, {"_id": 0})
        if cached and cached.get("fetched_at"):
            age = now - datetime.fromisoformat(cached["fetched_at"])
            if age < timedelta(hours=CACHE_HOURS):
                return _with_gdd(cached["payload"], crop_key)

    try:
        payload = fetch_open_meteo(lat, lon)
    except Exception as e:  # noqa: BLE001
        stale = await db.weather_cache.find_one({"key": key}, {"_id": 0})
        if stale:
            # Ağ hatasında BAYAT veriyle devam etmek, hiç veri vermemekten
            # iyidir — ama bayat olduğu açıkça işaretlenir.
            out = _with_gdd(stale["payload"], crop_key)
            out["stale"] = True
            out["reason"] = f"Güncel veri alınamadı: {e}"
            return out
        return {"available": False, "reason": f"Hava servisine ulaşılamadı: {e}"}

    await db.weather_cache.update_one(
        {"key": key},
        {"$set": {"key": key, "lat": lat, "lon": lon,
                  "payload": payload, "fetched_at": now.isoformat()}},
        upsert=True)
    return _with_gdd(payload, crop_key)


def _with_gdd(payload: Dict[str, Any], crop_key: Optional[str]) -> Dict[str, Any]:
    """Ham seriye GDD birikimi ve özetleri ekler."""
    base = base_temp_for(crop_key)
    daily = payload.get("daily") or []
    today = date.today().isoformat()
    past = [d for d in daily if d["date"] <= today]
    future = [d for d in daily if d["date"] > today]

    for d in daily:
        d["gdd"] = growing_degree_days(d.get("t_max"), d.get("t_min"), base)
        d["effective_rain_mm"] = effective_rain_mm(d.get("rain_mm"))
        d["frost_risk"] = frost_risk(d.get("t_min"))

    return {
        "available": True,
        "source": payload.get("source"),
        "base_temp_c": base,
        "daily": daily,
        "summary": {
            "gdd_son_30_gun": accumulate_gdd(past, base),
            "gdd_tahmin_16_gun": accumulate_gdd(future, base),
            "yagis_son_30_gun_mm": round(sum((d.get("rain_mm") or 0) for d in past), 1),
            "etkili_yagis_son_30_gun_mm": round(sum(d.get("effective_rain_mm") or 0 for d in past), 1),
            "yagis_tahmin_mm": round(sum((d.get("rain_mm") or 0) for d in future), 1),
            "et0_son_30_gun_mm": round(sum((d.get("et0_mm") or 0) for d in past), 1),
            "et0_tahmin_mm": round(sum((d.get("et0_mm") or 0) for d in future), 1),
            "don_riski_gun_sayisi": sum(1 for d in future if d.get("frost_risk")),
            "en_dusuk_sicaklik_tahmin": min([d["t_min"] for d in future if d.get("t_min") is not None], default=None),
            "en_yuksek_sicaklik_tahmin": max([d["t_max"] for d in future if d.get("t_max") is not None], default=None),
        },
    }


# =====================================================================
# HTTP YÜZEYİ
# =====================================================================

def register_weather_routes(api_router, db, current_user, require_permission,
                            log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/weather/parcels/{parcel_id}")
    async def parcel_weather(parcel_id: str, crop: Optional[str] = None, force: bool = False,
                             user=Depends(require_permission("parcels:view"))):
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        return await get_parcel_weather(db, parcel, crop, force)

    @api_router.get("/weather/parcels/{parcel_id}/normals")
    async def parcel_normals(parcel_id: str, years: int = 10,
                             user=Depends(require_permission("parcels:view"))):
        """ERA5-Land aylık iklim normalleri (geçmiş) — tahmin DEĞİL."""
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0, "geometry": 1})
        if not parcel or not parcel.get("geometry"):
            raise HTTPException(404, "Parsel veya sınır geometrisi bulunamadı")
        return await era5_normals(db, parcel["geometry"], min(max(years, 1), 30))
