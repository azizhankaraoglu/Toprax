"""
=====================================================================
TOPRAX — Güneş / Gölge Analizi (Copernicus DEM + ERA5 + Open-Meteo)
=====================================================================
Kullanıcı isteği: "Copernicus uydularının verdiği ücretsiz güneş/gölge
bilgilerini tarlalarımızda kullanmak istiyorum — gelen UV/ışın o bitki için
yeterli mi, saat kaç arasında ne kadar güneş alıyor, hangi tarafları gölgede
kalıyor ve ekim planlarken bu göz önünde bulundurulsun."

NE ÖLÇÜLÜYOR, NASIL
-------------------
1. **Arazi (topografya)** — `COPERNICUS/DEM/GLO30` (30 m küresel sayısal
   yükseklik modeli, ücretsiz). Buradan parselin **eğimi** ve **bakısı**
   (aspect: kuzey/güney/doğu/batı) hesaplanır. Kuzey bakılı ve eğimli bir
   parsel, aynı ilçedeki güney bakılı komşusundan belirgin daha az ışık alır.
2. **Gölgelenme profili** — günün saatlerine göre güneşin azimut/yükseklik
   açısı hesaplanır (saf astronomi, ek servis gerekmez) ve her saat için
   `ee.Terrain.hillshade` ile parselin ne kadarının gölgede kaldığı ölçülür.
   Böylece "sabah 07-09 arası doğu yamacı gölgede" gibi bir profil çıkar.
3. **Gerçek ışınım** — bulutluluk dahil gelen enerji topografyadan değil
   meteorolojiden gelir: `weather.py` üzerinden Open-Meteo (güncel/tahmin)
   ve ERA5-Land (geçmiş). Topografya "ne kadarını alabilir", meteoroloji
   "ne kadarı geldi" sorusunu yanıtlar; ikisi ayrı ve birlikte anlamlı.

DÜRÜSTLÜK KURALI: Earth Engine kimlik bilgisi yoksa bu modül SAYI UYDURMAZ —
`available: False` ve sebebini döner (gee_hls/service.py ile AYNI kural).
UV indeksi de ışınımdan TÜRETİLMEZ; Open-Meteo ayrı bir UV alanı verir,
onu vermiyorsa alan boş kalır.
"""
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

DEM_COLLECTION = "COPERNICUS/DEM/GLO30"

#: Analizde kullanılan saatler (yerel saat). 05-19 aralığı Türkiye'de
#: büyüme mevsimi boyunca güneşin ufuk üstünde olduğu bandı kapsar.
ANALYSIS_HOURS = list(range(5, 20))

#: Ürün bazlı GÜNLÜK asgari doğrudan güneşlenme ihtiyacı (saat).
#: Kaynak: tam güneş isteyen tarla bitkileri için yaygın agronomik kabul;
#: şeker pancarı C3 bir bitki olmasına rağmen yüksek ışık doygunluk noktası
#: ister — gölgede kalan parselde kök verimi ve şeker birikimi düşer.
CROP_SUN_REQUIREMENT_HOURS = {
    "pancar": 8.0, "misir": 8.0, "aycicegi": 8.0,
    "bugday": 6.0, "arpa": 6.0, "patates": 6.0, "yonca": 6.0,
}
DEFAULT_SUN_REQUIREMENT = 7.0


# =====================================================================
# SAF ASTRONOMİ — dış servis gerektirmez, test edilebilir
# =====================================================================

def solar_position(when: datetime, lat: float, lon: float) -> Tuple[float, float]:
    """Güneşin (yükseklik, azimut) açısı — derece.

    NOAA'nın basitleştirilmiş algoritması. Yükseklik (elevation) 0'ın altındaysa
    güneş ufkun altındadır. Azimut kuzeyden saat yönünde ölçülür (0=K, 90=D,
    180=G, 270=B) — `ee.Terrain.hillshade` de bu tanımı kullanır.
    """
    day_of_year = when.timetuple().tm_yday
    frac_year = 2 * math.pi / 365.0 * (day_of_year - 1 + (when.hour - 12) / 24.0)
    # Zaman denklemi (dakika) ve deklinasyon (radyan)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(frac_year)
                       - 0.032077 * math.sin(frac_year)
                       - 0.014615 * math.cos(2 * frac_year)
                       - 0.040849 * math.sin(2 * frac_year))
    decl = (0.006918 - 0.399912 * math.cos(frac_year) + 0.070257 * math.sin(frac_year)
            - 0.006758 * math.cos(2 * frac_year) + 0.000907 * math.sin(2 * frac_year)
            - 0.002697 * math.cos(3 * frac_year) + 0.00148 * math.sin(3 * frac_year))
    time_offset = eqtime + 4 * lon                      # dakika (UTC bazlı)
    true_solar_time = (when.hour * 60 + when.minute + when.second / 60.0 + time_offset) % 1440
    hour_angle = math.radians(true_solar_time / 4.0 - 180.0)
    lat_r = math.radians(lat)
    zenith = math.acos(max(-1.0, min(1.0,
        math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(decl) * math.cos(hour_angle))))
    elevation = 90.0 - math.degrees(zenith)
    # Azimut
    denom = math.sin(zenith) * math.cos(lat_r)
    if abs(denom) < 1e-9:
        azimuth = 180.0
    else:
        cos_az = (math.sin(decl) - math.sin(lat_r) * math.cos(zenith)) / denom
        azimuth = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        if hour_angle > 0:
            azimuth = 360.0 - azimuth
    return round(elevation, 2), round(azimuth, 2)


def aspect_label(aspect_deg: Optional[float]) -> Optional[str]:
    """Bakı derecesini yöne çevirir (çiftçi "212°" değil "güneybatı" anlar)."""
    if aspect_deg is None:
        return None
    dirs = ["Kuzey", "Kuzeydoğu", "Doğu", "Güneydoğu",
            "Güney", "Güneybatı", "Batı", "Kuzeybatı"]
    idx = int((aspect_deg % 360) / 45.0 + 0.5) % 8
    return dirs[idx]


def daylight_hours(day: date, lat: float, lon: float) -> float:
    """O gün güneşin ufuk üstünde geçirdiği saat (topografya HARİÇ)."""
    count = 0
    for hour in range(24):
        elev, _ = solar_position(datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc), lat, lon)
        if elev > 0:
            count += 1
    return float(count)


def sun_adequacy(effective_hours: Optional[float], crop_key: Optional[str]) -> Dict[str, Any]:
    """Güneşlenme yeterli mi — ürünün ihtiyacına göre.

    Yüzde, "ihtiyacın ne kadarı karşılanıyor" demektir; 100'ü aşan değerler
    100'e kırpılmaz (fazla güneş bilgi olarak değerlidir) ama karar sınıfı
    yeterli/sınırda/yetersiz olarak üç kademedir.
    """
    need = CROP_SUN_REQUIREMENT_HOURS.get((crop_key or "").lower(), DEFAULT_SUN_REQUIREMENT)
    if effective_hours is None:
        return {"gerekli_saat": need, "durum": "bilinmiyor", "karsilanma_yuzde": None}
    pct = round(effective_hours / need * 100, 1)
    if pct >= 100:
        durum = "yeterli"
    elif pct >= 85:
        durum = "sinirda"
    else:
        durum = "yetersiz"
    return {"gerekli_saat": need, "olculen_saat": round(effective_hours, 2),
            "karsilanma_yuzde": pct, "durum": durum}


# =====================================================================
# EARTH ENGINE — topografya ve gölge
# =====================================================================

async def analyze_parcel_solar(db, parcel: Dict[str, Any], crop_key: Optional[str] = None,
                               analysis_date: Optional[str] = None) -> Dict[str, Any]:
    """Parselin eğim/bakı + saatlik gölge profili + güneşlenme yeterliliği."""
    from .providers.gee_hls.service import _ee_initialize, _gee_credentials, extract_ring, InvalidFieldRequest

    geometry = parcel.get("geometry")
    if not geometry:
        return {"available": False, "reason": "Parselin sınır geometrisi yok"}
    try:
        ring = extract_ring(geometry)
    except InvalidFieldRequest as e:
        return {"available": False, "reason": str(e)}

    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    lon_c, lat_c = sum(lons) / len(lons), sum(lats) / len(lats)
    day = date.fromisoformat(analysis_date) if analysis_date else date.today()

    real, email, key_json, project = await _gee_credentials(db)
    if not real:
        return {"available": False,
                "reason": "Earth Engine kimlik bilgisi yok — arazi analizi yapılamadı",
                "gunes_konumu": _hourly_positions(day, lat_c, lon_c)}

    try:
        _ee_initialize(email, key_json, project)
        import ee
        geom = ee.Geometry.Polygon([ring])
        # GLO30 bir ImageCollection'dır; mozaikleyip yükseklik bandını alıyoruz.
        dem = ee.ImageCollection(DEM_COLLECTION).select("DEM").mosaic()
        terrain = ee.Terrain.products(dem)
        # ⚠️ `ee.Terrain.products()` yükseklik bandını GİRDİ BANDININ ADIYLA
        # döndürür — GLO-30'da bu "DEM"dir, "elevation" DEĞİL. Canlıda
        # "Band pattern 'elevation' did not match any bands. Available bands:
        # [DEM, slope, aspect, hillshade]" hatası alındı. Bant adı burada
        # açıkça yeniden adlandırılıyor ki aşağıdaki sözlük anahtarları
        # sağlayıcıdan bağımsız kalsın.
        stats = (terrain.select(["DEM", "slope", "aspect"], ["elevation", "slope", "aspect"])
                 .reduceRegion(reducer=ee.Reducer.mean(), geometry=geom,
                               scale=30, maxPixels=1e9).getInfo())

        # Saatlik gölge: her saat için hillshade; 0'a yakın değer = gölge.
        hourly = []
        shaded_images = []
        positions = _hourly_positions(day, lat_c, lon_c)
        for pos in positions:
            if pos["yukseklik_derece"] <= 0:
                hourly.append({**pos, "golge_orani_yuzde": 100.0, "gunes_var": False})
                continue
            hs = ee.Terrain.hillshade(dem, pos["azimut_derece"], pos["yukseklik_derece"])
            # Hillshade 0-255; 30'un altı pratikte gölge kabul edilir.
            shaded = hs.lt(30).rename("shade")
            shaded_images.append(shaded.set("hour", pos["saat"]))
            hourly.append({**pos, "gunes_var": True})

        if shaded_images:
            # TEK bir reduceRegion çağrısıyla tüm saatler (her saat ayrı bant) —
            # saat başına ayrı getInfo() 15 ağ turu demekti.
            stacked = ee.Image.cat([img.rename(f"h{int(img.get('hour').getInfo())}")
                                    for img in shaded_images])
            shade_stats = stacked.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom,
                                               scale=30, maxPixels=1e9).getInfo()
            for row in hourly:
                if row.get("gunes_var"):
                    val = shade_stats.get(f"h{row['saat']}")
                    row["golge_orani_yuzde"] = round((val or 0) * 100, 1)

        sunny_hours = sum(1 for h in hourly
                          if h.get("gunes_var") and (h.get("golge_orani_yuzde") or 0) < 50)
        # Kısmi gölgeyi de hesaba kat: her saatin aydınlık oranı toplanır.
        effective = sum((100 - (h.get("golge_orani_yuzde") or 0)) / 100.0
                        for h in hourly if h.get("gunes_var"))

        aspect = stats.get("aspect")
        result = {
            "available": True,
            "tarih": day.isoformat(),
            "arazi": {
                "yukseklik_m": round(stats.get("elevation"), 1) if stats.get("elevation") is not None else None,
                "egim_yuzde": round(stats.get("slope"), 2) if stats.get("slope") is not None else None,
                "baki_derece": round(aspect, 1) if aspect is not None else None,
                "baki": aspect_label(aspect),
            },
            "gunes_saati_gunluk": round(effective, 2),
            "tam_gunesli_saat": sunny_hours,
            "golgeli_saat": sum(1 for h in hourly if h.get("gunes_var") and (h.get("golge_orani_yuzde") or 0) >= 50),
            "ortalama_golge_orani_yuzde": round(
                sum(h.get("golge_orani_yuzde") or 0 for h in hourly if h.get("gunes_var")) /
                max(1, sum(1 for h in hourly if h.get("gunes_var"))), 1),
            "saatlik": hourly,
            "yeterlilik": sun_adequacy(effective, crop_key),
            "kaynak": "Copernicus DEM GLO-30 (Google Earth Engine)",
        }
        return result
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"Arazi/gölge analizi başarısız: {e}",
                "gunes_konumu": _hourly_positions(day, lat_c, lon_c)}


def _hourly_positions(day: date, lat: float, lon: float) -> List[Dict[str, Any]]:
    """Analiz saatleri için güneş konumu (topografya olmadan da anlamlı)."""
    out = []
    for hour in ANALYSIS_HOURS:
        when = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
        elev, azim = solar_position(when, lat, lon)
        out.append({"saat": hour, "yukseklik_derece": elev, "azimut_derece": azim})
    return out


async def solar_signals(db, parcel: Dict[str, Any], crop_key: Optional[str] = None) -> Dict[str, Any]:
    """Kural motorunun (agronomy.py) tüketeceği sadeleştirilmiş sinyaller.

    Parselde saklanmış son analiz varsa ONDAN okunur (her kural çalıştırmada
    Earth Engine'e gitmek hem yavaş hem kotalı olurdu); yoksa boş döner ve
    kurallar "veri yok" dalına düşer.
    """
    saved = (parcel.get("solar") or {})
    if not saved.get("available"):
        return {"gunes_saati_gunluk": None, "baki": None, "egim_yuzde": None,
                "golge_orani_yuzde": None, "gunes_yeterlilik_yuzde": None}
    return {
        "gunes_saati_gunluk": saved.get("gunes_saati_gunluk"),
        "baki": (saved.get("arazi") or {}).get("baki"),
        "egim_yuzde": (saved.get("arazi") or {}).get("egim_yuzde"),
        "golge_orani_yuzde": saved.get("ortalama_golge_orani_yuzde"),
        "gunes_yeterlilik_yuzde": (saved.get("yeterlilik") or {}).get("karsilanma_yuzde"),
    }
