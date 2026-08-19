"""
=====================================================================
TOPRAX — GEE/HLS iş mantığı (Faz 9C, 2026-07-25)
=====================================================================
Kullanıcının verdiği tam spesifikasyona göre: NASA HLS (HLSS30+HLSL30)
birleştirilir, %20 üzeri bulut filtrelenir, 30 m dışa tampon uygulanır,
tampon HEM istatistik alanı HEM kırpma geometrisi olarak kullanılır,
en güncel+temiz görüntü True Color kırpılıp getThumbURL() ile PNG
linkine çevrilir.

Kimlik doğrulama LAZY'dir (ilk gerçek istekte) — uygulama açılışında
`ee.Initialize()` ÇAĞRILMAZ, bu yüzden GEE kimlik bilgisi hiç
girilmemiş/hatalı olsa bile TOPRAX arka ucu ÇÖKMEZ (mock/demo moda düşer,
projenin her yerdeki "kimlik yoksa mock, girilince otomatik gerçek"
kuralıyla AYNI — bkz. integrations.py _probe_google_earth_engine).

---------------------------------------------------------------------
ÇOK-İNDEKSLİ GENİŞLETME (2026-08-18) — Çiftçi AI'nın GEE servisinden
port edildi
---------------------------------------------------------------------
Bu modül ilk yazıldığında (Faz 9C) BİLİNÇLİ olarak yalnızca NDVI
üretiyordu. Çiftçi AI projesinde (`backend/services/satellite_service.py`)
aynı HLS boru hattı 10 indeks + sensör ayrımı + gerçek-renkli küçük resim
üretecek şekilde olgunlaşmış ve orada canlı olarak doğrulanmıştı; bu tur
o davranışı TOPRAX'a taşır. Taşınırken korunan üç ÖNEMLİ ders (hepsi
Çiftçi AI'da canlı hata olarak yaşandı, bkz. o dosyadaki uzun notlar):

  1. **HLS bant adları TEK HANELİDİR ve S30/L30'da AYNI ADIN ANLAMI
     FARKLIDIR.** L30'da (Landsat 8/9 OLI) B5 = NIR; S30'da (Sentinel-2
     MSI) B5 = Red Edge 1, NIR ise B8A'dır. Bu yüzden iki koleksiyon
     ÖNCE ortak bir bant setine (`_HARMONIZED_BANDS`) yeniden
     adlandırılmadan BİRLEŞTİRİLMEZ.
     ⚠️ Bu, TOPRAX'ın önceki NDVI'sinde GERÇEK bir hataydı: merge edilmiş
     koleksiyonda `normalizedDifference(["B5","B4"])` kullanılıyordu —
     Landsat sahnelerinde doğru, Sentinel-2 sahnelerinde ise (NIR yerine
     Red Edge okuduğu için) SİSTEMATİK OLARAK YANLIŞ NDVI üretiyordu.
     Harmonizasyon bunu da düzeltir.
  2. **Yansıma değerleri GEE tarafında ZATEN 0-1 ölçeğindedir.** Ek bir
     `.multiply(0.0001)` uygulamak oranlı indeksleri (NDVI/NDWI/NDRE)
     etkilemez ama SABİT içeren formülleri (SAVI/MSAVI/EVI → dolayısıyla
     LAI) ve RGB render'ını sıfıra düşürür. Ölçekleme YAPILMAZ.
  3. **Landsat'ta Red Edge bandı YOKTUR.** Ortak bant setini tutturmak
     için sabit (`ee.Image.constant`) sahte Red Edge bantları eklenir —
     ama bu bantlar PROJEKSİYONSUZDUR: görüntüye eklendiklerinde
     görüntünün varsayılan projeksiyonu "1 derece/piksel"e düşer ve
     `getThumbURL` tüm tarlayı tek bir devasa pikselden örnekleyip SİYAH
     bir resim döndürür. Çözüm: küçük resim üretilirken RGB bantları
     ÖNCE seçilir (`select` → sabit bantlar görüntüden çıkar → gerçek
     30 m projeksiyon korunur). Aynı sebeple Landsat sahnelerinde Red
     Edge'e dayalı indeksler (NDRE/RECI/CCCI) sayı olarak DEĞİL, `None`
     olarak döner — sıfır yazmak "ölçüldü ve sıfır çıktı" anlamına
     gelirdi (projenin "veri yoksa sayı uydurma" ilkesi).
"""
import logging
import math
import random
import zlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pyproj import CRS, Transformer

from ..base import IRemoteSensingProvider
from ...dto import TaskState, TaskStatus
from ...indices import ALL_INDEX_CODES, estimate_lai

logger = logging.getLogger("toprax.gee_hls")

HLS_S30 = "NASA/HLS/HLSS30/v002"
HLS_L30 = "NASA/HLS/HLSL30/v002"
CLOUD_COVERAGE_MAX = 20
BUFFER_M = 30.0

#: HLS sensör kodlarının kullanıcıya gösterilecek karşılıkları (Çiftçi
#: AI'daki `SATELLITE_SENSOR_LABELS` ile AYNI) — hangi ölçümün hangi
#: uydudan geldiği yanıt içinde kalır, "kaynak" alanı uydurulmaz.
SENSOR_LABELS = {
    "S30": "Sentinel-2 (HLS S30)",
    "L30": "Landsat 8/9 (HLS L30)",
}

#: İki koleksiyonun ortak bant seti — indeks formülleri SADECE bu adları
#: kullanır, ham B2/B5/B8A adları formüllere HİÇ sızmaz.
_HARMONIZED_BANDS = ["Blue", "Green", "Red", "RedEdge1", "RedEdge2", "RedEdge3",
                     "NIR", "SWIR1", "SWIR2"]

#: Landsat (L30) sahnelerinde ölçülemeyen — kırmızı kenar bandı gerektiren —
#: indeksler. Bu sahnelerde `None` döner (bkz. modül başlığı, madde 3).
RED_EDGE_DEPENDENT = ("ndre", "reci", "ccci")


class InvalidFieldRequest(ValueError):
    """Tarih formatı hatalı / koordinatlar geçersiz — route 400'e çevirir."""


class NoCleanImageFound(Exception):
    """Aralıkta hiç temiz (bulut<%20) görüntü yok — route 404'e çevirir."""


class GeeRuntimeError(Exception):
    """GEE kimlik doğrulandı ama çağrı sırasında hata oluştu — route 502'ye çevirir."""


# --- Girdi doğrulama --------------------------------------------------------

def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise InvalidFieldRequest(f"Geçersiz tarih formatı: '{value}' — YYYY-MM-DD bekleniyor")


def extract_ring(polygon: Any) -> List[List[float]]:
    """Hem çıplak koordinat dizisini ([[lon,lat],...]) hem GeoJSON Polygon
    ({"type":"Polygon","coordinates":[[...]]}) kabul eder (kullanıcının
    spesifikasyonu: "polygon: ... GeoJSON formatında Polygon (veya
    koordinat dizisi)")."""
    if isinstance(polygon, dict):
        if polygon.get("type") != "Polygon":
            raise InvalidFieldRequest("polygon GeoJSON ise type='Polygon' olmalı")
        coords = polygon.get("coordinates")
        if not coords or not isinstance(coords, list):
            raise InvalidFieldRequest("polygon.coordinates eksik/geçersiz")
        ring = coords[0]
    elif isinstance(polygon, list):
        ring = polygon
    else:
        raise InvalidFieldRequest("polygon GeoJSON Polygon veya koordinat dizisi olmalı")
    try:
        ring = [[float(pt[0]), float(pt[1])] for pt in ring]
    except (TypeError, IndexError, ValueError):
        raise InvalidFieldRequest("polygon koordinatları [lon, lat] çiftleri olmalı")
    if len(ring) < 3:
        raise InvalidFieldRequest("polygon en az 3 nokta içermeli")
    for lon, lat in ring:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise InvalidFieldRequest(f"Geçersiz koordinat: [{lon}, {lat}]")
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]  # GeoJSON/ee.Geometry.Polygon halkanın kapalı olmasını bekler
    return ring


def _utm_transformer(ring: List[List[float]]) -> Tuple[Transformer, Transformer]:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    center_lon = (min(lons) + max(lons)) / 2
    center_lat = (min(lats) + max(lats)) / 2
    utm_zone = int((center_lon + 180) / 6) + 1
    hemisphere = "north" if center_lat >= 0 else "south"
    utm_crs = CRS.from_dict({"proj": "utm", "zone": utm_zone, hemisphere: True})
    to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True)
    return to_utm, to_wgs84


def _shoelace_area_perimeter_m(ring_utm: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Basit shoelace formülü (alan) + kenar toplamı (çevre) — shapely YOK
    (proje konvansiyonu, bkz. sentinel2.py'nin AYNI pyproj-only yaklaşımı)."""
    area = 0.0
    perim = 0.0
    n = len(ring_utm)
    for i in range(n - 1):
        x1, y1 = ring_utm[i]
        x2, y2 = ring_utm[i + 1]
        area += x1 * y2 - x2 * y1
        perim += math.hypot(x2 - x1, y2 - y1)
    return abs(area) / 2.0, perim


def buffered_area_ha(ring: List[List[float]], buffer_m: float = BUFFER_M) -> float:
    """30 m dışa tamponlu alan TAHMİNİ (hektar) — gerçek modda otoriter
    kaynak `ee.Geometry.buffer(30).area()`dır (bkz. _real_analyze); bu
    fonksiyon mock modda VE gerçek moda düşmeden önceki hızlı kontrol için
    kullanılır. Minkowski tampon alan formülü (dışbükey poligonlar için
    TAM, içbükeylerde iyi bir yaklaşıklık): A' = A + P·d + π·d²."""
    to_utm, _ = _utm_transformer(ring)
    ring_utm = [to_utm.transform(lon, lat) for lon, lat in ring]
    area_m2, perim_m = _shoelace_area_perimeter_m(ring_utm)
    buffered_m2 = area_m2 + perim_m * buffer_m + math.pi * (buffer_m ** 2)
    return round(buffered_m2 / 10_000.0, 2)


# --- Mock/demo mod -----------------------------------------------------------

def normalize_indices(indices: Optional[List[str]]) -> List[str]:
    """İstenen indeks listesini kataloğa göre doğrular/normalize eder.

    - Verilmezse TÜM katalog döner (Çiftçi AI'nın davranışı: tek çağrıda
      10 indeksin hepsi — GEE'de ek istek maliyeti YOK, aynı sahne zaten
      indiriliyor; EOSDA'nın "indeks başına 3 istek" maliyet modeliyle
      KARIŞTIRILMAMALI, bkz. dto.EOSDA_REQUESTS_PER_INDEX).
    - `ndvi` HER ZAMAN dahildir (tasks.py'nin `last_ndvi` mirror'ı ve
      sentinel2.py'nin AYNI garantisi).
    - Katalogda olmayan kod 400'e çevrilir (sessizce yok saymak, kullanıcı
      "istediğim indeks nerede?" diye bakarken yanıltıcı olurdu).
    """
    if not indices:
        return list(ALL_INDEX_CODES)
    codes = [str(c).strip().lower() for c in indices if str(c).strip()]
    unknown = [c for c in codes if c not in ALL_INDEX_CODES]
    if unknown:
        raise InvalidFieldRequest(
            f"Bilinmeyen indeks kodu: {', '.join(unknown)} — geçerli kodlar: {', '.join(ALL_INDEX_CODES)}")
    if "ndvi" not in codes:
        codes = ["ndvi", *codes]
    return [c for c in ALL_INDEX_CODES if c in codes]   # katalog sırası korunur


def _mock_analyze(ring: List[List[float]], start: date, end: date, area_ha: float,
                  indices: Optional[List[str]] = None) -> Dict[str, Any]:
    """Kimlik bilgisi yok/mock_mode açık — CRC32-tohumlu deterministik seri
    (2-3 günlük sıklık, kullanıcının 'yüksek sıklık' isteğiyle tutarlı) +
    base64 data-URI bir PNG (harici barındırma/token gerekmez, doğrudan
    <img> etiketine basılabilir — gerçek modda GEE'nin kendi imzalı
    googleapis.com linkiyle AYNI kullanım şekli).

    Diğer indeksler NDVI'den türetilir — `sentinel2.py`'nin mock dalıyla
    AYNI yaklaşım (gerçek modda her indeks kendi bandından bağımsız
    hesaplanır). Sensör alanı da simüle edilir ki ön yüz/AI yorumu mock
    ile gerçek arasında ŞEKİL olarak fark görmesin.
    """
    codes = normalize_indices(indices)
    seed = zlib.crc32(str(ring).encode()) % 100000
    rnd = random.Random(seed)
    base_ndvi = rnd.uniform(0.4, 0.75)
    history = []
    d = start
    day_idx = 0
    while d <= end:
        ndvi = max(0.05, min(0.95, base_ndvi + rnd.uniform(-0.06, 0.06) - day_idx * 0.002))
        sensor = "S30" if day_idx % 3 else "L30"
        point = {"date": d.isoformat(), "sensor": sensor}
        for code in codes:
            # Landsat'ta kırmızı kenar yok — mock'ta da None (gerçek modla
            # AYNI şekil, bkz. modül başlığı madde 3).
            if sensor == "L30" and code in RED_EDGE_DEPENDENT:
                point[code] = None
            else:
                point[code] = _derive_mock_index(code, ndvi, rnd)
        history.append(point)
        d += timedelta(days=rnd.choice([2, 3]))
        day_idx += 1
    if not history:
        raise NoCleanImageFound("Belirtilen tarih aralığında temiz görüntü bulunamadı (mock mod)")
    return {
        "status": "success",
        "meta": {"requested_area_ha": area_ha, "buffer_applied": "30 meters",
                 "indices": codes, "sensors": _sensor_labels(history), "mock": True},
        "latest_image_url": _demo_thumb_data_uri(seed),
        "ndvi_history": history,
        "indices_history": history,
    }


def _derive_mock_index(code: str, ndvi: float, rnd: random.Random) -> Optional[float]:
    """Tek bir mock indeks değeri (sentinel2.py'deki türetme tablosunun
    AYNISI — iki sağlayıcının demo verisi birbirine benzesin diye)."""
    if code == "ndvi":
        return round(ndvi, 4)
    if code == "ndre":
        return round(max(0.0, ndvi * 0.82 + rnd.uniform(-0.03, 0.03)), 4)
    if code == "reci":
        return round(max(0.0, ndvi * 4.5 + rnd.uniform(-0.3, 0.3)), 4)
    if code == "ccci":
        return round(max(0.0, 0.55 + rnd.uniform(-0.1, 0.1)), 4)
    if code == "ndwi":
        return round(ndvi * 0.25 - 0.05 + rnd.uniform(-0.02, 0.02), 4)
    if code == "msi":
        return round(max(0.0, 1.4 - ndvi * 0.9 + rnd.uniform(-0.05, 0.05)), 4)
    if code == "msavi":
        return round(ndvi * 1.05, 4)
    if code == "savi":
        return round(ndvi * 0.92, 4)
    if code == "evi":
        return round(ndvi * 0.78, 4)
    if code == "lai":
        return estimate_lai(ndvi)
    return None


def _sensor_labels(history: List[Dict[str, Any]]) -> List[str]:
    """Serideki ölçümlerin GERÇEKTEN hangi uydulardan geldiği (Çiftçi
    AI'daki `_satellite_source_label` ile AYNI amaç — sabit bir "NASA HLS"
    etiketi yerine ölçülmüş sensörler yazılır)."""
    seen = sorted({p.get("sensor") for p in history if p.get("sensor")})
    return [SENSOR_LABELS.get(s, s) for s in seen]


def _demo_thumb_data_uri(seed: int, size: int = 256) -> str:
    import base64
    import io
    from PIL import Image
    rnd = random.Random(seed)
    base = rnd.uniform(0.35, 0.7)
    img = Image.new("RGB", (size, size), (34, 139, 34))
    px = img.load()
    for y in range(size):
        for x in range(size):
            shade = base + 0.2 * ((x + y) / (2 * size)) + rnd.uniform(-0.03, 0.03)
            shade = max(0.1, min(0.9, shade))
            px[x, y] = (int(60 * (1 - shade)), int(80 + 120 * shade), int(40 * (1 - shade)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# --- Gerçek GEE modu ----------------------------------------------------------

_ee_initialized_key = None  # son başarıyla Initialize edilen (email, key_hash) — tekrar tekrar Initialize etmemek için


def _ee_initialize(email: str, key_json: str, project: Optional[str] = None) -> None:
    """Lazy GEE kimlik doğrulama — sadece GERÇEK bir istekte çağrılır,
    uygulama açılışında ASLA (kullanıcının 'crash olmamalı' şartı budur:
    burada bir hata olsa bile sadece BU istek 502 döner, FastAPI süreci
    etkilenmez).

    `project` — Earth Engine'e KAYITLI Cloud proje ID'si (service account
    key'inin KENDİ `project_id`'sinden FARKLI olabilir — GEE, Kasım 2024
    API değişikliğinden beri `ee.Initialize()`'a HANGİ projenin kotasının
    kullanılacağını AÇIKÇA söylemeyi zorunlu kılıyor). Integration Center'da
    ayrı bir (secret olmayan) `project` alanı olarak saklanır."""
    global _ee_initialized_key
    key_hash = zlib.crc32((email + key_json + (project or "")).encode()) % 10_000_000
    if _ee_initialized_key == (email, key_hash):
        return
    try:
        import ee
    except ImportError as e:
        raise GeeRuntimeError("'earthengine-api' paketi kurulu değil") from e
    try:
        credentials = ee.ServiceAccountCredentials(email, key_data=key_json)
        if project:
            ee.Initialize(credentials, project=project)
        else:
            ee.Initialize(credentials)
        _ee_initialized_key = (email, key_hash)
    except Exception as e:
        logger.error("GEE Initialize başarısız: %s", e)
        raise GeeRuntimeError(f"GEE kimlik doğrulama hatası: {e}") from e


def _harmonized_collection(ee, buffered, start: date, end: date):
    """S30 + L30'u ORTAK bant setine çevirip birleştirir (bkz. modül
    başlığı, madde 1 — bu adım atlanırsa Sentinel-2 sahnelerinde B5 = Red
    Edge, Landsat sahnelerinde B5 = NIR olduğu için aynı formül iki farklı
    şeyi ölçer)."""
    date_from = start.isoformat()
    date_to = (end + timedelta(days=1)).isoformat()

    def rename_s30(img):
        # HLS S30 (Sentinel-2 MSI) — TEK HANELİ adlar:
        #   B2=Mavi B3=Yeşil B4=Kırmızı B5/B6/B7=Kırmızı Kenar 1-3
        #   B8A=NIR (dar) B11=SWIR1 B12=SWIR2
        return img.select(
            ["B2", "B3", "B4", "B5", "B6", "B7", "B8A", "B11", "B12"],
            _HARMONIZED_BANDS,
        ).set("sensor", "S30")

    def rename_l30(img):
        # HLS L30 (Landsat 8/9 OLI): B2=Mavi B3=Yeşil B4=Kırmızı B5=NIR
        # B6=SWIR1 B7=SWIR2 — kırmızı kenar YOK, ortak bant setini
        # tutturmak için sabit bantlar eklenir (bu bantlara dayalı
        # indeksler sonra None'a çevrilir).
        base = img.select(["B2", "B3", "B4", "B5", "B6", "B7"],
                          ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"])
        dummies = [ee.Image.constant(0).rename(n) for n in ("RedEdge1", "RedEdge2", "RedEdge3")]
        return base.addBands(dummies).set("sensor", "L30")

    s30 = (ee.ImageCollection(HLS_S30).filterBounds(buffered).filterDate(date_from, date_to)
           .filter(ee.Filter.lt("CLOUD_COVERAGE", CLOUD_COVERAGE_MAX)).map(rename_s30))
    l30 = (ee.ImageCollection(HLS_L30).filterBounds(buffered).filterDate(date_from, date_to)
           .filter(ee.Filter.lt("CLOUD_COVERAGE", CLOUD_COVERAGE_MAX)).map(rename_l30))
    return s30.merge(l30).sort("system:time_start")


def _add_indices(ee, img, codes: List[str]):
    """İstenen indeksleri görüntüye bant olarak ekler.

    Formüller `indices.py` kataloğundakiyle AYNI tanımlardır (orada
    Sentinel-2 L2A bant adlarıyla — B08/B04/B05/B11/B02 — yazılıdır,
    burada harmonize adlarla: NIR/Red/RedEdge1/SWIR1/Blue).

    ⚠️ Ölçekleme YOK (`.multiply(0.0001)` YAPILMAZ) — bkz. modül başlığı
    madde 2. `.toFloat()` yalnızca tamsayı yuvarlamasına karşı güvence.

    ⚠️ LAI: `indices.py`'nin `estimate_lai()`'si NDVI'den ampirik bir
    regresyondur (yalnızca ortalama değere uygulanabilir). GEE'de piksel
    bazında EVI'den türetilen klasik ilişki (3.618·EVI − 0.113, Boegh
    2002) kullanılır — Çiftçi AI'daki uygulamanın AYNISI. İkisi de
    TAHMİNDİR; katalogdaki `is_estimated: True` bayrağı geçerliliğini
    korur, ön yüz "(tahmini)" etiketini göstermeye devam eder.
    """
    scaled = img.toFloat()
    red = scaled.select("Red")
    nir = scaled.select("NIR")
    swir1 = scaled.select("SWIR1")
    blue = scaled.select("Blue")
    re1 = scaled.select("RedEdge1")

    bands = {}
    ndvi = scaled.normalizedDifference(["NIR", "Red"]).rename("ndvi")
    ndre = scaled.normalizedDifference(["NIR", "RedEdge1"]).rename("ndre")
    if "ndvi" in codes:
        bands["ndvi"] = ndvi
    if "ndre" in codes:
        bands["ndre"] = ndre
    if "reci" in codes:
        bands["reci"] = nir.divide(re1.add(0.0001)).subtract(1).rename("reci")
    if "ccci" in codes:
        bands["ccci"] = ndre.divide(ndvi.add(0.0001)).rename("ccci")
    if "ndwi" in codes:
        bands["ndwi"] = scaled.normalizedDifference(["NIR", "SWIR1"]).rename("ndwi")
    if "msi" in codes:
        bands["msi"] = swir1.divide(nir.add(0.0001)).rename("msi")
    if "savi" in codes:
        bands["savi"] = nir.subtract(red).divide(nir.add(red).add(0.5)).multiply(1.5).rename("savi")
    if "msavi" in codes:
        bands["msavi"] = scaled.expression(
            "(2 * NIR + 1 - sqrt(pow(2 * NIR + 1, 2) - 8 * (NIR - Red))) / 2",
            {"NIR": nir, "Red": red}).rename("msavi")
    evi = scaled.expression(
        "2.5 * ((NIR - Red) / (NIR + 6.0 * Red - 7.5 * Blue + 1.0))",
        {"NIR": nir, "Red": red, "Blue": blue}).rename("evi")
    if "evi" in codes:
        bands["evi"] = evi
    if "lai" in codes:
        bands["lai"] = evi.multiply(3.618).subtract(0.113).clamp(0, 10).rename("lai")
    return img.addBands(list(bands.values()))


def _real_analyze(ring: List[List[float]], start: date, end: date,
                  email: str, key_json: str, project: Optional[str] = None,
                  indices: Optional[List[str]] = None) -> Dict[str, Any]:
    codes = normalize_indices(indices)
    _ee_initialize(email, key_json, project)
    import ee
    try:
        geom = ee.Geometry.Polygon([ring])
        buffered = geom.buffer(BUFFER_M)

        clean = _harmonized_collection(ee, buffered, start, end)
        with_indices = clean.map(lambda img: _add_indices(ee, img, codes))

        def _stats(img):
            stats = img.select(codes).reduceRegion(
                reducer=ee.Reducer.mean(), geometry=buffered, scale=30, maxPixels=1e9)
            # ⚠️ Earth Engine tarih biçimi JODA kalıbıdır, strftime DEĞİL:
            # 'YYYY' hafta-yılı, 'DD' YILIN GÜNÜ demektir — 'YYYY-MM-DD'
            # "2026-05-129" gibi geçersiz tarihler üretir (Çiftçi AI'da
            # zaman tüneli grafiğini kıran gerçek hata). Doğrusu: yyyy-MM-dd.
            props = {"date": img.date().format("yyyy-MM-dd"), "sensor": img.get("sensor")}
            for code in codes:
                props[code] = stats.get(code)
            return ee.Feature(None, props)

        features = ee.FeatureCollection(with_indices.map(_stats)).getInfo().get("features", [])
        if not features:
            raise NoCleanImageFound(
                "Belirtilen tarih aralığında temiz (bulut oranı <%20) görüntü bulunamadı")

        history: List[Dict[str, Any]] = []
        for f in features:
            props = f.get("properties", {}) or {}
            sensor = props.get("sensor")
            point: Dict[str, Any] = {"date": props.get("date"), "sensor": sensor}
            for code in codes:
                if sensor == "L30" and code in RED_EDGE_DEPENDENT:
                    point[code] = None          # Landsat'ta ölçülemez — sıfır YAZILMAZ
                else:
                    point[code] = _clean_val(props.get(code))
            if point["date"] and point.get("ndvi") is not None:
                history.append(point)
        history.sort(key=lambda p: p["date"])
        if not history:
            raise NoCleanImageFound("Bulut filtresinden geçen görüntülerde geçerli indeks hesaplanamadı")

        thumb_url = _thumbnail_from_collection(ee, with_indices, buffered)
        area_ha = round(buffered.area(maxError=1).divide(10_000).getInfo(), 2)

        return {
            "status": "success",
            "meta": {"requested_area_ha": area_ha, "buffer_applied": "30 meters",
                     "indices": codes, "sensors": _sensor_labels(history), "mock": False},
            "latest_image_url": thumb_url,
            # `ndvi_history` LİTERAL sözleşme gereği korunur (Faz 9C'nin
            # `POST /api/v1/analyze-field` şeması) — artık her nokta diğer
            # indeksleri de taşır. `indices_history` aynı listeye okunabilir
            # bir ad verir (Çiftçi AI'nın uydu ucundaki adlandırma).
            "ndvi_history": history,
            "indices_history": history,
        }
    except NoCleanImageFound:
        raise
    except InvalidFieldRequest:
        raise
    except Exception as e:
        logger.error("GEE analyze_field çalışma zamanı hatası: %s", e)
        raise GeeRuntimeError(f"GEE sorgu hatası: {e}") from e


def _clean_val(val: Any) -> Optional[float]:
    """NaN/Inf/None'ı JSON-güvenli hale getirir (Çiftçi AI'daki
    `_clean_val` ile AYNI) — bulutla tamamen kaplı bir sahnede
    reduceRegion `None` döner, bu bir HATA DEĞİL, ölçülemedi demektir."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _thumbnail_from_collection(ee, collection, buffered) -> Optional[str]:
    """En güncel sahnenin gerçek renkli (True Color) küçük resmi.

    ⚠️ RGB bantları ÖNCE seçilir: Landsat sahnelerinde eklenen
    projeksiyonsuz sabit RedEdge bantları görüntüde kalırsa görüntünün
    varsayılan projeksiyonu 1 derece/piksele düşer ve küçük resim TAMAMEN
    SİYAH çıkar (Çiftçi AI'da canlı yaşanan hata, bkz. modül başlığı
    madde 3). `scale` parametresi `dimensions` ile BİRLİKTE verilemez —
    Earth Engine "may not be specified along with width/height" hatası
    döndürür, o yüzden çözüm bant seçiminde.
    """
    try:
        latest = collection.sort("system:time_start", False).first()
        rgb = latest.select(["Red", "Green", "Blue"]).toFloat().clip(buffered)
        return rgb.getThumbURL({
            "bands": ["Red", "Green", "Blue"],
            "min": 0.0, "max": 0.3,
            "dimensions": 512, "region": buffered, "format": "png",
        })
    except Exception as e:  # noqa: BLE001
        # Küçük resim üretilemezse ANALİZ ÇÖKMEZ — sayısal seri zaten
        # geçerli; görüntü alanı None döner, ön yüz yer tutucu gösterir.
        logger.warning("GEE küçük resmi üretilemedi: %s", e)
        return None


# --- Genel giriş noktası ------------------------------------------------------

async def _gee_credentials(db) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Integration Center'dan (type='google_earth_engine') kimlik bilgisi.
    Döner: (gerçek_mod_mu, email, key_json, project)."""
    doc = await db.integrations.find_one({"type": "google_earth_engine"}, {"_id": 0}) or {}
    cfg = doc.get("config", {}) or {}
    email = cfg.get("service_account_email")
    key_json = cfg.get("service_account_key_json")
    project = cfg.get("project")
    real = bool(doc.get("enabled")) and bool(email) and bool(key_json) and not cfg.get("mock_mode", True)
    return real, email, key_json, project


async def analyze_field(db, polygon: Any, start_date_str: str, end_date_str: str,
                        indices: Optional[List[str]] = None) -> Dict[str, Any]:
    """Integration Center'dan (type='google_earth_engine') kimlik bilgisini
    okur, mock/gerçek moda göre analyze eder. `InvalidFieldRequest` → 400,
    `NoCleanImageFound` → 404, `GeeRuntimeError` → 502 (route.py bu üç
    exception'ı yakalayıp uygun HTTP koduna çevirir).

    `indices` verilmezse TÜM katalog (10 indeks) hesaplanır — tek bir GEE
    sahne taramasında hepsi aynı anda çıktığı için ek maliyet YOKTUR."""
    start = parse_date(start_date_str)
    end = parse_date(end_date_str)
    if end < start:
        raise InvalidFieldRequest("end_date, start_date'den önce olamaz")
    ring = extract_ring(polygon)
    codes = normalize_indices(indices)
    area_ha = buffered_area_ha(ring)

    real, email, key_json, project = await _gee_credentials(db)
    if not real:
        return _mock_analyze(ring, start, end, area_ha, codes)
    return _real_analyze(ring, start, end, email, key_json, project, codes)


async def get_latest_thumbnail_url(db, polygon: Any, days: int = 90) -> Optional[str]:
    """Son `days` gün içindeki en güncel bulutsuz sahnenin gerçek renkli
    küçük resmi (yoksa None).

    Çiftçi AI'daki `SatelliteService.get_latest_thumbnail_url` ile AYNI
    işlev: parselin GÜNCEL görüntüsünü tam bir zaman serisi analizi
    koşturmadan almak (harita popup'ı/kart önizlemesi gibi yerlerde
    sayısal seriye ihtiyaç yok). Hata durumunda İSTİSNA FIRLATMAZ — bu
    bir süs öğesidir, çağıran ekranı çökertmemeli."""
    try:
        ring = extract_ring(polygon)
    except InvalidFieldRequest:
        return None
    real, email, key_json, project = await _gee_credentials(db)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(1, int(days)))
    if not real:
        return _demo_thumb_data_uri(zlib.crc32(str(ring).encode()) % 100000)
    try:
        _ee_initialize(email, key_json, project)
        import ee
        buffered = ee.Geometry.Polygon([ring]).buffer(BUFFER_M)
        clean = _harmonized_collection(ee, buffered, start, end)
        if clean.size().getInfo() <= 0:
            return None
        return _thumbnail_from_collection(ee, clean, buffered)
    except Exception as e:  # noqa: BLE001
        logger.warning("GEE küçük resmi alınamadı: %s", e)
        return None


# =====================================================================
# IRemoteSensingProvider sarmalayıcı — TOPRAX'ın mevcut Tarama Politikası/
# scheduler/manuel-sync/AI-yorumu/bildirim boru hattına provider_override=
# "gee_hls" ile takılabilmesi için (Faz 9C "Ek mimari karar").
#
# 2026-08-18: Faz 9C'de bu sarmalayıcı SADECE NDVI döndürüyordu; artık
# `indices` parametresi gerçekten kullanılıyor ve seri `sentinel2.py`
# ile AYNI şekle (çok-indeksli nokta listesi) sahip — yani Tarama
# Politikası'nda `provider_override="gee_hls"` seçmek, EOSDA/Sentinel-2
# ile aynı grafikleri/AI yorumunu/su stresi bildirimlerini üretir.
# =====================================================================

class GEEHLSProvider(IRemoteSensingProvider):
    name = "gee_hls"
    capabilities = ["imagery", "statistics"]

    def __init__(self, email: Optional[str] = None, key_json: Optional[str] = None,
                 project: Optional[str] = None, mock_mode: bool = True):
        self.email = email
        self.key_json = key_json
        self.project = project
        self.mock_mode = mock_mode
        self._cache: Dict[str, dict] = {}

    def create_field(self, geometry: dict) -> str:
        return "gee-" + str(zlib.crc32(str(geometry).encode()) % 10_000_000)

    def search_scenes(self, field_id: str, date_range: tuple, geometry: Optional[dict] = None) -> List[Dict]:
        # GEE/HLS akışı istatistik+görüntüyü TEK çağrıda üretir (bkz.
        # request_statistics) — search ayrı bir adım DEĞİL, boş döner.
        return []

    def request_image_download(self, view_id: str, geometry: Optional[dict] = None, fmt: str = "png") -> str:
        raise NotImplementedError("GEEHLSProvider görüntüyü request_statistics içinde üretir")

    def request_statistics(self, field_id: str, indices: List[str], date_range: tuple,
                           geometry: Optional[dict] = None) -> str:
        """Tek bir GEE taramasında istenen TÜM indeksleri üretir.

        `cloud_pct` 0 olarak yazılır — bir tahmin DEĞİL, sözleşme gereği
        bir alan: HLS sahneleri zaten bulut oranı %20 filtresinden GEÇMİŞ
        olanlar (bkz. CLOUD_COVERAGE_MAX); sahne bazlı gerçek yüzde
        `CLOUD_COVERAGE` metadatasında var ama nokta bazlı bulut maskesi
        uygulanmadığı için parsel-üstü gerçek bulut yüzdesi ölçülmüş
        sayılmaz."""
        start, end = date_range
        codes = normalize_indices(indices)
        task_id = "gee-stat-" + str(zlib.crc32(f"{field_id}{start}{end}{','.join(codes)}".encode()) % 10_000_000)
        try:
            ring = extract_ring(geometry) if geometry else None
            if not ring:
                self._cache[task_id] = {"ok": False, "error": "Geometri yok"}
                return task_id
            area_ha = buffered_area_ha(ring)
            if self.mock_mode or not self.email or not self.key_json:
                result = _mock_analyze(ring, start, end, area_ha, codes)
            else:
                result = _real_analyze(ring, start, end, self.email, self.key_json, self.project, codes)
            series = []
            for p in result["ndvi_history"]:
                point = {"date": p["date"], "cloud_pct": 0, "sensor": p.get("sensor")}
                for code in codes:
                    if p.get(code) is not None:
                        point[code] = p[code]
                series.append(point)
            self._cache[task_id] = {"ok": True, "series": series, "image_url": result["latest_image_url"]}
        except Exception as e:  # noqa: BLE001
            self._cache[task_id] = {"ok": False, "error": str(e)}
        return task_id

    def get_task_status(self, task_id: str) -> TaskStatus:
        entry = self._cache.get(task_id)
        if not entry:
            return TaskStatus(task_id=task_id, state=TaskState.FAILED, error="Bilinmeyen task")
        if not entry.get("ok"):
            return TaskStatus(task_id=task_id, state=TaskState.FAILED, error=entry.get("error"))
        return TaskStatus(task_id=task_id, state=TaskState.COMPLETED,
                          result={"series": entry.get("series", [])},
                          result_url=entry.get("image_url"))
