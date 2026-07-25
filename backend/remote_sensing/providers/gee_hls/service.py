"""
=====================================================================
TOPRAX — GEE/HLS iş mantığı (Faz 9C, 2026-07-25)
=====================================================================
Kullanıcının verdiği tam spesifikasyona göre: NASA HLS (HLSS30+HLSL30)
birleştirilir, %20 üzeri bulut filtrelenir, 30 m dışa tampon uygulanır,
tampon HEM istatistik alanı HEM kırpma geometrisi olarak kullanılır,
NDVI = (B5-B4)/(B5+B4) (HLS bant adlandırması — Sentinel-2'nin B08/B04'ünden
FARKLI), en güncel+temiz görüntü True Color (B4,B3,B2) kırpılıp
getThumbURL() ile PNG linkine çevrilir.

Kimlik doğrulama LAZY'dir (ilk gerçek istekte) — uygulama açılışında
`ee.Initialize()` ÇAĞRILMAZ, bu yüzden GEE kimlik bilgisi hiç
girilmemiş/hatalı olsa bile TOPRAX arka ucu ÇÖKMEZ (mock/demo moda düşer,
projenin her yerdeki "kimlik yoksa mock, girilince otomatik gerçek"
kuralıyla AYNI — bkz. integrations.py _probe_google_earth_engine).
"""
import logging
import math
import random
import zlib
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pyproj import CRS, Transformer

from ..base import IRemoteSensingProvider
from ...dto import TaskState, TaskStatus

logger = logging.getLogger("toprax.gee_hls")

HLS_S30 = "NASA/HLS/HLSS30/v002"
HLS_L30 = "NASA/HLS/HLSL30/v002"
CLOUD_COVERAGE_MAX = 20
BUFFER_M = 30.0


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

def _mock_analyze(ring: List[List[float]], start: date, end: date, area_ha: float) -> Dict[str, Any]:
    """Kimlik bilgisi yok/mock_mode açık — CRC32-tohumlu deterministik NDVI
    serisi (2-3 günlük sıklık, kullanıcının 'yüksek sıklık' isteğiyle
    tutarlı) + base64 data-URI bir PNG (harici barındırma/token gerekmez,
    doğrudan <img> etiketine basılabilir — gerçek modda GEE'nin kendi
    imzalı googleapis.com linkiyle AYNI kullanım şekli)."""
    seed = zlib.crc32(str(ring).encode()) % 100000
    rnd = random.Random(seed)
    base_ndvi = rnd.uniform(0.4, 0.75)
    history = []
    d = start
    day_idx = 0
    while d <= end:
        ndvi = max(0.05, min(0.95, base_ndvi + rnd.uniform(-0.06, 0.06) - day_idx * 0.002))
        history.append({"date": d.isoformat(), "ndvi": round(ndvi, 4)})
        d += timedelta(days=rnd.choice([2, 3]))
        day_idx += 1
    if not history:
        raise NoCleanImageFound("Belirtilen tarih aralığında temiz görüntü bulunamadı (mock mod)")
    return {
        "status": "success",
        "meta": {"requested_area_ha": area_ha, "buffer_applied": "30 meters"},
        "latest_image_url": _demo_thumb_data_uri(seed),
        "ndvi_history": history,
    }


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


def _real_analyze(ring: List[List[float]], start: date, end: date,
                  email: str, key_json: str, project: Optional[str] = None) -> Dict[str, Any]:
    _ee_initialize(email, key_json, project)
    import ee
    try:
        geom = ee.Geometry.Polygon([ring])
        buffered = geom.buffer(BUFFER_M)

        s30 = ee.ImageCollection(HLS_S30).filterBounds(buffered) \
                .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
        l30 = ee.ImageCollection(HLS_L30).filterBounds(buffered) \
                .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
        merged = s30.merge(l30)
        clean = merged.filter(ee.Filter.lt("CLOUD_COVERAGE", CLOUD_COVERAGE_MAX))

        def _with_ndvi(img):
            ndvi = img.normalizedDifference(["B5", "B4"]).rename("NDVI")
            mean = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=buffered,
                                     scale=30, maxPixels=1e9).get("NDVI")
            return img.set("ndvi_mean", mean).set("iso_date", img.date().format("YYYY-MM-dd"))

        with_ndvi = clean.map(_with_ndvi)
        n = with_ndvi.size().getInfo()
        if n == 0:
            raise NoCleanImageFound("Belirtilen tarih aralığında temiz (bulut oranı <%20) görüntü bulunamadı")

        dates = with_ndvi.aggregate_array("iso_date").getInfo()
        ndvis = with_ndvi.aggregate_array("ndvi_mean").getInfo()
        history = [{"date": d, "ndvi": round(float(v), 4)} for d, v in zip(dates, ndvis) if v is not None]
        history.sort(key=lambda p: p["date"])
        if not history:
            raise NoCleanImageFound("Bulut filtresinden geçen görüntülerde geçerli NDVI hesaplanamadı")

        latest = clean.sort("system:time_start", False).first()
        vis_params = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.3,
                      "dimensions": 512, "region": buffered}
        thumb_url = latest.clip(buffered).getThumbURL(vis_params)

        area_ha = round(buffered.area(maxError=1).divide(10_000).getInfo(), 2)

        return {
            "status": "success",
            "meta": {"requested_area_ha": area_ha, "buffer_applied": "30 meters"},
            "latest_image_url": thumb_url,
            "ndvi_history": history,
        }
    except NoCleanImageFound:
        raise
    except Exception as e:
        logger.error("GEE analyze_field çalışma zamanı hatası: %s", e)
        raise GeeRuntimeError(f"GEE sorgu hatası: {e}") from e


# --- Genel giriş noktası ------------------------------------------------------

async def analyze_field(db, polygon: Any, start_date_str: str, end_date_str: str) -> Dict[str, Any]:
    """Integration Center'dan (type='google_earth_engine') kimlik bilgisini
    okur, mock/gerçek moda göre analyze eder. `InvalidFieldRequest` → 400,
    `NoCleanImageFound` → 404, `GeeRuntimeError` → 502 (route.py bu üç
    exception'ı yakalayıp uygun HTTP koduna çevirir)."""
    start = parse_date(start_date_str)
    end = parse_date(end_date_str)
    if end < start:
        raise InvalidFieldRequest("end_date, start_date'den önce olamaz")
    ring = extract_ring(polygon)
    area_ha = buffered_area_ha(ring)

    doc = await db.integrations.find_one({"type": "google_earth_engine"}, {"_id": 0}) or {}
    cfg = doc.get("config", {}) or {}
    enabled = bool(doc.get("enabled"))
    mock_mode = cfg.get("mock_mode", True)
    email = cfg.get("service_account_email")
    key_json = cfg.get("service_account_key_json")
    project = cfg.get("project")
    real = enabled and email and key_json and not mock_mode

    if not real:
        return _mock_analyze(ring, start, end, area_ha)
    return _real_analyze(ring, start, end, email, key_json, project)


# =====================================================================
# IRemoteSensingProvider sarmalayıcı — TOPRAX'ın mevcut Tarama Politikası/
# scheduler/manuel-sync/AI-yorumu/bildirim boru hattına provider_override=
# "gee_hls" ile takılabilmesi için (Faz 9C "Ek mimari karar"). Bu turda
# SADECE NDVI (kullanıcının literal isteği — 9-indeks genişlemesi GEE/HLS'ye
# bilinçli olarak YAPILMADI, kapsam taşırılmadı).
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
        start, end = date_range
        task_id = "gee-stat-" + str(zlib.crc32(f"{field_id}{start}{end}".encode()) % 10_000_000)
        try:
            ring = extract_ring(geometry) if geometry else None
            if not ring:
                self._cache[task_id] = {"ok": False, "error": "Geometri yok"}
                return task_id
            area_ha = buffered_area_ha(ring)
            if self.mock_mode or not self.email or not self.key_json:
                result = _mock_analyze(ring, start, end, area_ha)
            else:
                result = _real_analyze(ring, start, end, self.email, self.key_json, self.project)
            series = [{"date": p["date"], "ndvi": p["ndvi"], "cloud_pct": 0} for p in result["ndvi_history"]]
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
