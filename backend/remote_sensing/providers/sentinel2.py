"""
=====================================================================
TOPRAX — Sentinel2Provider (Denetim Faz 5, 2026-07-24)
=====================================================================
Copernicus Data Space Ecosystem (CDSE) — ÜCRETSİZ Sentinel-2 L2A verisi.
`satellite_provider.SentinelHubProvider`'ın OAuth2 client_credentials
token mantığı BURADA TEKRAR KURULUR (ayrı modül, ortak bir taban sınıfa
çıkarmak bu iterasyonun kapsamı dışı — iki kullanım şekli farklı: biri
`SatelliteProvider` ABC'sine, biri `IRemoteSensingProvider` ABC'sine bağlı).

**Kimlik bilgisi kaynağı — YENİ bir entegrasyon tipi EKLENMEDİ:** mevcut
`sentinel_hub` entegrasyon dokümanındaki `client_id`/`client_secret`
(Ayarlar > Entegrasyonlar > Sentinel Hub) AYNEN kullanılır — CDSE hesabı
zaten hem Statistics API (NDVI) hem Process API (görüntü) için tek
kimlik doğrulamasıdır. `providers/__init__.py`'deki factory bunu okur.

**Senkron→asenkron uyarlama:** CDSE Process/Statistics API'leri
SENKRON'dur (tek HTTP isteğinde sonucu döner) — ama `IRemoteSensingProvider`
arayüzü EOSDA'nın 3 adımlı asenkron modeline göre tasarlı (search→
download→poll). Bu sınıf işi `request_image_download`/`request_statistics`
İÇİNDE senkron olarak TAMAMLAR, sonucu örnek-seviyesi bir sözlükte
(`self._cache`) task_id'ye göre saklar; `get_task_status` bu cache'ten
ANINDA "completed" döner (gerçek polling gerekmez). Bu adaptör deseni
`tasks.py`/`scheduler.py`'yi TEK SATIR DEĞİŞTİRMEDEN Sentinel-2'yi
mevcut kuyruk mimarisine bağlar.

**30 m tampon (buffer):** Parsel geometrisi Process API'ye DOĞRUDAN clip
geometrisi olarak gönderilir (CDSE tarafında gerçek kırpma) — çerçeve
(bbox) `pyproj` ile parselin UTM diliminde 30 m genişletilir, sonra
WGS84'e geri döndürülür (shapely YOK, bilinçli — Karar Protokolü,
mevcut `geo_import.py`'nin pyproj kullanımıyla AYNI aile).
"""
import io
import zlib
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
from pyproj import Transformer, CRS

from .base import IRemoteSensingProvider
from ..dto import TaskStatus, TaskState


TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

# NDVI renk haritalı (kırmızı→sarı→yeşil) görsel çıktı — EOSDA'nın true-color
# görüntüsünü TEKRARLAMAK yerine tamamlayıcı bir ürün: sayısal NDVI değerini
# doğrudan görselleştirir (kullanıcı bir bakışta "kırmızı = kötü" görür).
_NDVI_COLOR_EVALSCRIPT = """
//VERSION=3
function setup() {
  return { input: [{ bands: ["B04", "B08", "dataMask"] }],
           output: { bands: 4 } };
}
function ramp(ndvi) {
  // -1..1 -> kirmizi(kotu)..sari..yesil(iyi), basit lineer enterpolasyon
  var stops = [
    [-1.0, [165, 0, 38]], [0.0, [215, 48, 39]], [0.2, [244, 109, 67]],
    [0.35, [253, 174, 97]], [0.5, [254, 224, 139]], [0.65, [166, 217, 106]],
    [0.8, [102, 189, 99]], [1.0, [26, 152, 80]]
  ];
  for (var i = 1; i < stops.length; i++) {
    if (ndvi <= stops[i][0]) {
      var a = stops[i - 1], b = stops[i];
      var t = (ndvi - a[0]) / (b[0] - a[0] + 1e-9);
      return [
        a[1][0] + t * (b[1][0] - a[1][0]),
        a[1][1] + t * (b[1][1] - a[1][1]),
        a[1][2] + t * (b[1][2] - a[1][2]),
      ];
    }
  }
  return stops[stops.length - 1][1];
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 0.0001);
  if (s.dataMask === 0) return [1, 1, 1, 0];
  var rgb = ramp(ndvi);
  return [rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1];
}
"""

_NDVI_STATS_EVALSCRIPT = """
//VERSION=3
function setup() {
  return { input: [{ bands: ["B04", "B08", "dataMask"] }],
           output: [{ id: "data", bands: 1 }, { id: "dataMask", bands: 1 }] };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 0.0001);
  return { data: [ndvi], dataMask: [s.dataMask] };
}
"""


def _expand_bbox_by_meters(geometry: dict, margin_m: float = 30.0) -> Tuple[float, float, float, float]:
    """Parsel geometrisinin bbox'ını, geometrinin merkezindeki UTM diliminde
    `margin_m` metre genişletip WGS84'e geri döndürür (pyproj — shapely YOK).
    Gerçek KIRPMA CDSE tarafında `geometry`'nin kendisiyle yapılır; bu bbox
    sadece görüntü ÇERÇEVESİDİR (parselin biraz dışını da göstermek için)."""
    coords = geometry.get("coordinates")
    pts: List[Tuple[float, float]] = []

    def _flatten(c):
        if isinstance(c[0], (int, float)):
            pts.append((c[0], c[1]))
        else:
            for sub in c:
                _flatten(sub)

    _flatten(coords)
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    center_lon = (min_lon + max_lon) / 2

    utm_zone = int((center_lon + 180) / 6) + 1
    hemisphere = "north" if (min_lat + max_lat) / 2 >= 0 else "south"
    utm_crs = CRS.from_dict({"proj": "utm", "zone": utm_zone, hemisphere: True})
    to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True)

    x_min, y_min = to_utm.transform(min_lon, min_lat)
    x_max, y_max = to_utm.transform(max_lon, max_lat)
    x_min -= margin_m; y_min -= margin_m
    x_max += margin_m; y_max += margin_m

    lon1, lat1 = to_wgs84.transform(x_min, y_min)
    lon2, lat2 = to_wgs84.transform(x_max, y_max)
    return (min(lon1, lon2), min(lat1, lat2), max(lon1, lon2), max(lat1, lat2))


def _demo_png_bytes(seed_str: str, size: int = 256) -> bytes:
    """Demo mod — CRC32-tohumlu deterministik bir NDVI-renk-haritası gradyanı
    (satellite_provider.DemoSatelliteProvider ile AYNI teknik). Pillow zaten
    proje bağımlılığı (reportlab/PDF üretimi + IT-04 image alanları) —
    yeni bir bağımlılık EKLENMEDİ."""
    from PIL import Image
    seed = zlib.crc32(seed_str.encode("utf-8"))
    rnd = random.Random(seed)
    base_ndvi = rnd.uniform(0.35, 0.75)
    img = Image.new("RGB", (size, size))
    px = img.load()
    stops = [(-1.0, (165, 0, 38)), (0.0, (215, 48, 39)), (0.35, (253, 174, 97)),
             (0.5, (254, 224, 139)), (0.65, (166, 217, 106)), (1.0, (26, 152, 80))]

    def ramp(ndvi):
        for i in range(1, len(stops)):
            if ndvi <= stops[i][0]:
                a, b = stops[i - 1], stops[i]
                t = (ndvi - a[0]) / (b[0] - a[0] + 1e-9)
                return tuple(int(a[1][k] + t * (b[1][k] - a[1][k])) for k in range(3))
        return stops[-1][1]

    for y in range(size):
        for x in range(size):
            noise = rnd.uniform(-0.06, 0.06) if (x + y) % 7 == 0 else 0
            ndvi = base_ndvi + 0.15 * ((x - size / 2) / size) + noise
            px[x, y] = ramp(max(-1, min(1, ndvi)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Sentinel2Provider(IRemoteSensingProvider):
    name = "sentinel2"
    capabilities = ["imagery", "statistics"]

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None,
                 mock_mode: bool = True, timeout: int = 30):
        self.client_id = client_id
        self.client_secret = client_secret
        self.mock_mode = mock_mode
        self.timeout = timeout
        self._token = None
        self._token_expires_at = None
        # Bu provider örneği bir tek task'ın search→download veya
        # request_statistics→get_task_status zincirinde YAŞAR (bkz. modül
        # docstring'i) — cache'in ömrü tam olarak buna yeter.
        self._cache: Dict[str, dict] = {}

    # --- OAuth2 (SentinelHubProvider ile aynı desen) --------------------------
    def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token
        resp = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id, "client_secret": self.client_secret,
        }, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = now + timedelta(seconds=max(int(data.get("expires_in", 300)) - 30, 30))
        return self._token

    # --- Field (AOI) — CDSE'de kalıcı bir "field" kavramı yok, deterministik id yeterli
    def create_field(self, geometry: dict) -> str:
        return "s2-" + str(zlib.crc32(str(geometry).encode()) % 10_000_000)

    # --- Görüntü: search + download tek adımda senkron yürütülür --------------
    def search_scenes(self, field_id: str, date_range: tuple, geometry: Optional[dict] = None) -> List[Dict]:
        start, end = date_range
        if self.mock_mode or not geometry:
            # Demo: ~5 günlük aralıklarla, en yeni tarihi bugüne yakın tut.
            rnd = random.Random(zlib.crc32(field_id.encode()) % 100000)
            scenes, d = [], start
            while d <= end:
                scenes.append({"view_id": f"S2-DEMO/{d:%Y%m%d}",
                               "date": d.strftime("%Y-%m-%d"),
                               "cloud_pct": rnd.randint(0, 25), "satellite": "Sentinel-2 (demo)"})
                d += timedelta(days=5)
            return scenes
        # Gerçek: CDSE OData Catalog — geometriyi kesişen, en az bulutlu sahneler.
        token = self._get_token()
        bbox_geom = {"type": "Polygon", "coordinates": geometry.get("coordinates")}
        filter_str = (
            f"Collection/Name eq 'SENTINEL-2' and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;{self._wkt(bbox_geom)}') and "
            f"ContentDate/Start gt {start:%Y-%m-%d}T00:00:00.000Z and "
            f"ContentDate/Start lt {end:%Y-%m-%d}T23:59:59.000Z and "
            f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value lt 60)"
        )
        resp = requests.get(
            "https://catalogue.dataspace.copernicus.eu/odata/v1/Products",
            params={"$filter": filter_str, "$orderby": "ContentDate/Start desc", "$top": 10},
            headers={"Authorization": f"Bearer {token}"}, timeout=self.timeout,
        )
        resp.raise_for_status()
        scenes = []
        for item in resp.json().get("value", []):
            content_date = (item.get("ContentDate") or {}).get("Start", "")[:10]
            if not content_date:
                continue
            scenes.append({"view_id": item.get("Id"), "date": content_date,
                           "cloud_pct": None, "satellite": "Sentinel-2"})
        return scenes

    @staticmethod
    def _wkt(geometry: dict) -> str:
        coords = geometry["coordinates"][0]
        ring = ", ".join(f"{lon} {lat}" for lon, lat in coords)
        return f"POLYGON(({ring}))"

    def request_image_download(self, view_id: str, geometry: Optional[dict] = None, fmt: str = "png") -> str:
        """CDSE Process API SENKRONdur — sonucu burada hemen üretip cache'e
        koyar, `get_task_status` sadece cache'ten okur (bkz. modül docstring'i)."""
        task_id = "s2-img-" + uuid.uuid4().hex[:12]
        try:
            if self.mock_mode or not geometry:
                png_bytes = _demo_png_bytes(view_id)
            else:
                bbox = _expand_bbox_by_meters(geometry, margin_m=30.0)
                token = self._get_token()
                body = {
                    "input": {
                        "bounds": {
                            "bbox": list(bbox),
                            "geometry": geometry,   # gerçek kırpma CDSE tarafında
                            "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                        },
                        "data": [{"type": "sentinel-2-l2a",
                                  "dataFilter": {"maxCloudCoverage": 60}}],
                    },
                    "output": {"width": 512, "height": 512,
                               "responses": [{"identifier": "default",
                                             "format": {"type": "image/png"}}]},
                    "evalscript": _NDVI_COLOR_EVALSCRIPT,
                }
                resp = requests.post(PROCESS_URL, json=body,
                                     headers={"Authorization": f"Bearer {token}"}, timeout=self.timeout)
                resp.raise_for_status()
                png_bytes = resp.content
            self._cache[task_id] = {"kind": "image", "bytes": png_bytes, "ok": True}
        except Exception as e:  # noqa: BLE001
            self._cache[task_id] = {"kind": "image", "ok": False, "error": str(e)}
        return task_id

    def download_image_bytes(self, url: str) -> bytes:
        """`url` burada gerçek bir URL değil, `request_image_download`'ın
        döndürdüğü task_id'nin kendisi (get_task_status onu result_url
        olarak geçirir) — cache'ten okunur."""
        entry = self._cache.get(url) or {}
        if not entry.get("ok"):
            raise RuntimeError(entry.get("error") or "Sentinel-2 görüntüsü üretilemedi")
        return entry["bytes"]

    # --- İstatistik (NDVI zaman serisi) — senkron, cache'e gömülür ------------
    def request_statistics(self, field_id: str, indices: List[str], date_range: tuple,
                           geometry: Optional[dict] = None) -> str:
        start, end = date_range
        task_id = "s2-stat-" + uuid.uuid4().hex[:12]
        try:
            if self.mock_mode or not geometry:
                rnd = random.Random(zlib.crc32(field_id.encode()) % 100000)
                base = rnd.uniform(0.4, 0.75)
                series, d = [], start
                while d <= end:
                    ndvi = max(0.1, min(0.95, base + rnd.uniform(-0.08, 0.08)))
                    series.append({"date": d.strftime("%Y-%m-%d"), "ndvi": round(ndvi, 3),
                                   "cloud_pct": rnd.randint(0, 20)})
                    d += timedelta(days=5)
                self._cache[task_id] = {"kind": "stats", "ok": True, "series": series}
            else:
                token = self._get_token()
                body = {
                    "input": {"bounds": {"geometry": geometry},
                             "data": [{"type": "sentinel-2-l2a",
                                       "dataFilter": {
                                           "timeRange": {"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
                                           "maxCloudCoverage": 60}}]},
                    "aggregation": {
                        "timeRange": {"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
                        "aggregationInterval": {"of": "P5D"},
                        "evalscript": _NDVI_STATS_EVALSCRIPT, "resx": 10, "resy": 10,
                    },
                }
                resp = requests.post(STATS_URL, json=body,
                                     headers={"Authorization": f"Bearer {token}"}, timeout=self.timeout)
                resp.raise_for_status()
                series = []
                for interval in resp.json().get("data", []):
                    bands = interval.get("outputs", {}).get("data", {}).get("bands", {})
                    stats = (bands.get("B0") or {}).get("stats", {})
                    if not stats or not stats.get("sampleCount"):
                        continue
                    series.append({"date": interval["interval"]["from"][:10],
                                   "ndvi": round(stats.get("mean", 0), 3), "cloud_pct": 0})
                self._cache[task_id] = {"kind": "stats", "ok": bool(series), "series": series,
                                        "error": None if series else "Bu aralıkta veri yok"}
        except Exception as e:  # noqa: BLE001
            self._cache[task_id] = {"kind": "stats", "ok": False, "error": str(e)}
        return task_id

    # --- Ortak "polling" — CDSE zaten senkron, cache'ten anında döner ---------
    def get_task_status(self, task_id: str) -> TaskStatus:
        entry = self._cache.get(task_id)
        if not entry:
            return TaskStatus(task_id=task_id, state=TaskState.FAILED, error="Bilinmeyen task")
        if entry["kind"] == "image":
            if entry.get("ok"):
                return TaskStatus(task_id=task_id, state=TaskState.COMPLETED, result_url=task_id)
            return TaskStatus(task_id=task_id, state=TaskState.FAILED, error=entry.get("error"))
        # stats
        if entry.get("ok"):
            return TaskStatus(task_id=task_id, state=TaskState.COMPLETED,
                              result={"series": entry.get("series", [])})
        return TaskStatus(task_id=task_id, state=TaskState.FAILED, error=entry.get("error"))
