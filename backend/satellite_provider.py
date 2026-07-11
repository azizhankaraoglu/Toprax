"""
=====================================================================
TabSIS — Uydu Görüntü Provider Soyutlaması (IT-17 → gerçek çoklu-
sağlayıcı mimarisi, 2026-07-11 araştırma raporuna göre genişletildi)
=====================================================================
Bu dosya artık TEK bir mock sağlayıcı değil, gerçek bir **Provider
Abstraction Layer**: `TABSIS_Uydu_Goruntu_Ekosistemi_Arastirma.md`
raporunun §5 (Kurumsal Mimari Önerisi) ve §8 (Kod Tabanına Entegrasyon
Notu) bölümlerinde tanımlanan öncelik sırasıyla üç GERÇEK sağlayıcı
eklendi:

  1. **Sentinel Hub / Copernicus Data Space Ecosystem** (varsayılan,
     "ndvi" yeteneği) — ücretsiz kotalı, en olgun API (rapor sıralaması #1).
  2. **NASA FIRMS** (yangın, "fire" yeteneği) — tamamen ücretsiz, gerçek
     zamanlı (rapor sıralaması #5).
  3. **UP42** (VHR tasking talebi, "tasking" yeteneği) — onlarca VHR
     sağlayıcıya (Airbus/SkySat/ICEYE/Capella) TEK entegrasyonla erişim
     (rapor sıralaması #3).

**Kritik kural (planet_labs/integrations.py ile AYNI kalıp):** Hiçbir
sağlayıcı için Integration Center'da (integrations.py, `db.integrations`)
kimlik bilgisi girilip `mock_mode` KAPATILMADAN gerçek bir dış API
çağrısı YAPILMAZ — `get_satellite_provider()` her zaman
`DemoSatelliteProvider`'a düşer. Kullanıcı ("Hepsinin keylerini en son
giricem") Integration Center'dan (Ayarlar > Entegrasyonlar) anahtarları
girip mock_mode'u kapattığında, ÇAĞIRAN KOD (extras.py, HaritaPaneli.jsx)
HİÇ DEĞİŞMEDEN gerçek veriye geçer — bu, ROADMAP'in "provider değişse
bile harita mimarisi değişmemeli" ilkesinin bu iterasyondaki somut
uygulamasıdır.

**Yeni yetenek ayrımı (`capability` parametresi):** Tüm sağlayıcılar
`get_ndvi_time_series` uygulamak ZORUNDA değil — NASA FIRMS NDVI
üretmez, UP42 (bu iterasyonda) sadece tasking talebi oluşturur. Bu
yüzden registry `capability="ndvi"|"fire"|"tasking"` alır ve HER
yetenek için Integration Center'da AYRI bir entegrasyon tipi
(`sentinel_hub` / `nasa_firms` / `up42`) okur.

**Bilinçli kapsam dışı (bu iterasyonda):** Gerçek COG/STAC tabanlı harita
katmanı (tile servisi), Planet/Maxar/Airbus gerçek entegrasyonu, AI
pipeline (IT-28.2/28.3) — rapor §5'teki mimarinin sonraki katmanları.
Bu dosya sadece "Katman 1 — Provider Abstraction" + tek bir somut tüketim
noktasını (NDVI zaman serisi + yangın alarmı + tasking talebi) kurar.
"""
import random
import zlib
import requests
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


class SatelliteProvider(ABC):
    """Araştırma raporu §Teknik Beklentiler'deki ortak arayüzün TABSİS'e
    uyarlanmış asgari alt kümesi. Yeni bir yetenek (ör. calculate_index,
    search_images) eklemek isteyen gelecek bir iterasyon SADECE bu sınıfa
    yeni bir metot ekler + ilgili sağlayıcı(lar)da uygular — registry ve
    çağıran kod değişmez."""

    name = "base"

    @abstractmethod
    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        """[{date: 'YYYY-MM-DD', ndvi: float, cloud_pct: int}, ...] döner."""
        raise NotImplementedError

    def get_fire_alerts(self, bbox: Tuple[float, float, float, float], days: int = 1) -> List[Dict]:
        """Varsayılan: hiç alarm yok. Şu an SADECE NasaFirmsProvider gerçek veri döner."""
        return []

    def request_tasking(self, geometry: Optional[dict], resolution_cm: int, priority: str = "standard") -> Dict:
        """Varsayılan: tasking desteklenmiyor. Şu an SADECE Up42Provider gerçekleştirir."""
        return {"status": "desteklenmiyor", "message": f"'{self.name}' sağlayıcısı tasking desteklemiyor"}


class DemoSatelliteProvider(SatelliteProvider):
    """
    MOCK veri — Integration Center'da hiçbir gerçek sağlayıcı aktif
    değilken (varsayılan durum) HER zaman bu kullanılır. Parsel_id'ye
    göre DETERMİNİSTİK (aynı parsel için her zaman aynı seri) — sunucu
    yeniden başladığında değerler değişmesin diye Python'un güvenlik
    amaçlı rastgele salt'lı `hash()`'i değil, süreçten bağımsız
    `zlib.crc32` + yerel bir `random.Random` örneği kullanılır.
    """
    name = "demo"

    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        rnd = random.Random(zlib.crc32(parcel_id.encode()) % 10000)
        time_series = []
        base_ndvi = rnd.uniform(0.4, 0.75)
        # 5 aylık NDVI zaman serisi (Mayıs-Eylül 2025), ayda 2 örnek (1 ve 15'i)
        for month in range(5, 10):
            for day in [1, 15]:
                if month <= 7:
                    ndvi = base_ndvi + rnd.uniform(0, 0.15)
                else:
                    ndvi = base_ndvi - (month - 7) * 0.08 + rnd.uniform(-0.05, 0.05)
                time_series.append({
                    "date": f"2025-{month:02d}-{day:02d}",
                    "ndvi": round(max(0.1, min(0.95, ndvi)), 3),
                    "cloud_pct": rnd.randint(0, 25),
                })
        return time_series


class SentinelHubProvider(SatelliteProvider):
    """
    Gerçek Copernicus Data Space Ecosystem / Sentinel Hub entegrasyonu
    (araştırma raporu §2.1, §4 sıralama #1). OAuth2 client_credentials
    ile token alır, Statistics API üzerinden parsel geometrisi + son
    ~150 gün için 15 günlük aralıklarla NDVI ortalaması hesaplatır
    (piksel piksel görüntü İNDİRİLMEZ — sadece istatistik, PU maliyeti
    minimumda tutulur, bkz. rapor §2.1 "Lisanslama").

    NOT (mevcut projenin dış-ağ-kapalı ortam disclaimeri ile AYNI ruh —
    bkz. integrations.py docstring'i): Bu sınıf gerçek bir Sentinel Hub
    hesabı + `mock_mode=False` OLMADAN asla çağrılmaz (registry bkz.
    aşağıda). İlk gerçek kullanımda "Bağlantıyı Test Et" ile doğrulanmalı.
    """
    name = "sentinel_hub"
    TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

    _NDVI_EVALSCRIPT = """
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

    def __init__(self, client_id: str, client_secret: str, timeout: int = 20):
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._token = None
        self._token_expires_at = None

    def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token
        resp = requests.post(self.TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id, "client_secret": self.client_secret,
        }, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = now + timedelta(seconds=max(int(data.get("expires_in", 300)) - 30, 30))
        return self._token

    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        if not geometry:
            raise ValueError("Sentinel Hub için parsel geometrisi (GeoJSON Polygon) gerekli")
        token = self._get_token()
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=150)
        body = {
            "input": {
                "bounds": {"geometry": geometry},
                "data": [{
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
                        "maxCloudCoverage": 40,
                    },
                }],
            },
            "aggregation": {
                "timeRange": {"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
                "aggregationInterval": {"of": "P15D"},
                "evalscript": self._NDVI_EVALSCRIPT,
                "resx": 10, "resy": 10,
            },
        }
        resp = requests.post(self.STATS_URL, json=body,
                              headers={"Authorization": f"Bearer {token}"}, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        series = []
        for interval in data.get("data", []):
            bands = interval.get("outputs", {}).get("data", {}).get("bands", {})
            stats = (bands.get("B0") or {}).get("stats", {})
            if not stats or not stats.get("sampleCount"):
                continue
            series.append({
                "date": interval["interval"]["from"][:10],
                "ndvi": round(stats.get("mean", 0), 3),
                # Statistics API bulut oranını ayrı bir alan olarak dönmez —
                # maxCloudCoverage filtresiyle zaten elenmiş kabul edilir.
                "cloud_pct": 0,
            })
        if not series:
            raise ValueError("Sentinel Hub bu tarih aralığı/geometri için veri döndürmedi")
        return series


class NasaFirmsProvider(SatelliteProvider):
    """
    NASA FIRMS (Fire Information for Resource Management System) — TAMAMEN
    ÜCRETSİZ, gerçek-zamanlı yangın/sıcak-nokta tespiti (araştırma raporu
    §2.16, §4 sıralama #5, "Yangın İzleme" stratejisi §6). NDVI ÜRETMEZ.
    """
    name = "nasa_firms"
    AREA_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    def __init__(self, map_key: str, timeout: int = 15):
        self.map_key = map_key
        self.timeout = timeout

    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        raise NotImplementedError("NASA FIRMS NDVI üretmez — get_fire_alerts kullanın")

    def get_fire_alerts(self, bbox: Tuple[float, float, float, float], days: int = 1) -> List[Dict]:
        min_lon, min_lat, max_lon, max_lat = bbox
        days = max(1, min(days, 10))   # FIRMS area API 1-10 gün destekler
        url = f"{self.AREA_URL}/{self.map_key}/VIIRS_SNPP_NRT/{min_lon},{min_lat},{max_lon},{max_lat}/{days}"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        lines = resp.text.strip().splitlines()
        if len(lines) < 2:
            return []
        header = lines[0].split(",")
        alerts = []
        for line in lines[1:]:
            values = line.split(",")
            if len(values) != len(header):
                continue
            row = dict(zip(header, values))
            try:
                alerts.append({
                    "lat": float(row.get("latitude", 0)),
                    "lon": float(row.get("longitude", 0)),
                    "date": row.get("acq_date"),
                    "confidence": row.get("confidence"),
                    "brightness": row.get("bright_ti4") or row.get("brightness"),
                })
            except (TypeError, ValueError):
                continue
        return alerts


class Up42Provider(SatelliteProvider):
    """
    UP42 pazaryeri — TABSİS'in kendi başına onlarca VHR sağlayıcıya
    (Airbus Pléiades Neo, Planet SkySat, ICEYE, Capella) ayrı ayrı entegre
    olmak yerine TEK API'den eriştiği katman (araştırma raporu §2.10,
    §4 sıralama #3). Bu iterasyonda SADECE tasking TALEBİ kimlik
    doğrulaması + kayıt altına alınması uygulanır — gerçek sipariş/ödeme
    akışı (AOI+collection+parametre seçimi, UP42 kredi sistemi) UP42 hesabı
    aktive edildikten sonra tamamlanmalı (bkz. rapor §8, bilinen sınır).
    """
    name = "up42"
    TOKEN_URL = "https://api.up42.com/oauth/token"

    def __init__(self, client_id: str, client_secret: str, mock_mode: bool = True, timeout: int = 15):
        self.client_id = client_id
        self.client_secret = client_secret
        self.mock_mode = mock_mode
        self.timeout = timeout

    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        raise NotImplementedError("UP42 bu iterasyonda sadece tasking talebi için kullanılıyor")

    def request_tasking(self, geometry: Optional[dict], resolution_cm: int = 50, priority: str = "standard") -> Dict:
        if self.mock_mode:
            return {
                "status": "simule_edildi",
                "message": "[MOCK MOD] Talep TABSİS içinde kaydedildi, UP42'ye GÖNDERİLMEDİ "
                           "(mock_mode kapatılmadan gerçek sipariş oluşturulmaz).",
            }
        resp = requests.post(
            self.TOKEN_URL, data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret), timeout=self.timeout,
        )
        resp.raise_for_status()
        if "access_token" not in resp.json():
            return {"status": "hata", "message": "UP42 kimlik doğrulaması başarısız"}
        # Gerçek "create order/job" çağrısı AOI + collection + fiyat onayı
        # gerektiren çok adımlı bir UP42 akışıdır (rapor §8) — bu iterasyonda
        # sadece kimlik doğrulamanın çalıştığı doğrulanır.
        return {
            "status": "kimlik_dogrulandi",
            "message": "UP42 kimlik doğrulaması başarılı — sipariş oluşturma akışı hesap "
                       "aktivasyonu sonrası tamamlanacak (bkz. TABSIS_Uydu_Goruntu_Ekosistemi_Arastirma.md §8).",
        }


# =====================================================================
# Registry — Integration Center'dan (db.integrations) hangi sağlayıcının
# aktif olduğunu okuyup seçer. Anahtar/hesap yoksa VEYA mock_mode açıksa
# HER ZAMAN DemoSatelliteProvider'a düşer.
# =====================================================================
_CAPABILITY_TO_INTEGRATION_TYPE = {"ndvi": "sentinel_hub", "fire": "nasa_firms", "tasking": "up42"}


async def get_satellite_provider(db, capability: str = "ndvi") -> SatelliteProvider:
    """
    capability:
      - "ndvi"    → Sentinel Hub (varsayılan) → Demo
      - "fire"    → NASA FIRMS → Demo (boş liste)
      - "tasking" → UP42 → Demo ("desteklenmiyor")
    """
    itype = _CAPABILITY_TO_INTEGRATION_TYPE.get(capability)
    doc = await db.integrations.find_one({"type": itype}, {"_id": 0}) if itype else None
    cfg = (doc or {}).get("config", {})
    enabled = bool(doc and doc.get("enabled"))
    mock_mode = cfg.get("mock_mode", True)

    if capability == "fire" and enabled and cfg.get("map_key") and not mock_mode:
        return NasaFirmsProvider(map_key=cfg["map_key"])

    if capability == "tasking" and enabled and cfg.get("client_id") and cfg.get("client_secret"):
        # Tasking talebi mock_mode açıkken de "çalışır" (simüle sonuç döner,
        # kimlik bilgisi zorunlu değil) — bu yüzden mock_mode kontrolü
        # request_tasking'in İÇİNDE, registry'de DEĞİL.
        return Up42Provider(client_id=cfg["client_id"], client_secret=cfg["client_secret"],
                             mock_mode=mock_mode)

    if capability == "ndvi" and enabled and cfg.get("client_id") and cfg.get("client_secret") and not mock_mode:
        return SentinelHubProvider(client_id=cfg["client_id"], client_secret=cfg["client_secret"])

    return DemoSatelliteProvider()


def ndvi_to_health(ndvi: float) -> Dict:
    """extras.py'nin `/satellite/ndvi/{parcel_id}` ucundaki mevcut eşik/etiketler."""
    if ndvi > 0.65:
        return {"status": "iyi", "label": "Sağlıklı gelişim", "color": "#4ade80"}
    elif ndvi > 0.45:
        return {"status": "orta", "label": "İzlemeye değer", "color": "#fbbf24"}
    return {"status": "kötü", "label": "Stres altında", "color": "#ef4444"}


def ndvi_to_risk_level(ndvi: float) -> Tuple[str, str]:
    """
    IT-17 — Mekânsal Zaman Makinesi'nin "o tarihteki" risk_level/risk_label'ı
    parcels.risk_level ile AYNI 4 seviyeyi (yesil/sari/turuncu/kirmizi)
    kullanır — görsel dil tutarlı kalsın diye (Parcels.jsx/HaritaPaneli.jsx
    RISK_COLORS ile aynı anahtarlar). Eşikler `ndvi_to_health`'ten BAĞIMSIZ
    seçildi (health 3 seviyeli, risk_level 4 seviyeli — ayrı sınıflandırma
    amaçları farklı, birebir eşlenemez).
    """
    if ndvi > 0.65:
        return "yesil", "Düşük Risk"
    elif ndvi > 0.5:
        return "sari", "İzlemeye Değer"
    elif ndvi > 0.35:
        return "turuncu", "Riskli"
    return "kirmizi", "Acil Müdahale"


def _geometry_bbox(geometry: Optional[dict]) -> Optional[Tuple[float, float, float, float]]:
    """GeoJSON geometriden basit bbox çıkarır (Polygon/MultiPolygon) —
    NASA FIRMS'in alan sorgusu için gerekli."""
    if not geometry or not geometry.get("coordinates"):
        return None

    def _flatten(c):
        if isinstance(c[0], (int, float)):
            yield c
        else:
            for sub in c:
                yield from _flatten(sub)

    points = list(_flatten(geometry["coordinates"]))
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return (min(lons), min(lats), max(lons), max(lats))


def register_satellite_routes(api_router, db, current_user, require_permission, log_audit):
    """
    Mevcut `/satellite/ndvi/*` uçları (extras.py) DEĞİŞMEDEN kalıyor —
    bu fonksiyon SADECE araştırma raporunun getirdiği YENİ yetenekler
    için (yangın alarmı + VHR tasking talebi + sağlayıcı durumu) uç ekler.
    """
    from fastapi import HTTPException, Depends, Request
    from pydantic import BaseModel

    @api_router.get("/satellite/providers/status")
    async def satellite_providers_status(user=Depends(current_user)):
        """Ayarlar/Uydu ekranının hangi yeteneğin GERÇEK mi DEMO mu
        çalıştığını göstermesi için (Integration Center kartlarının yanında)."""
        result = {}
        for capability in ("ndvi", "fire", "tasking"):
            provider = await get_satellite_provider(db, capability)
            result[capability] = {"active_provider": provider.name, "is_real": provider.name != "demo"}
        return result

    @api_router.get("/satellite/fire-alerts/{parcel_id}")
    async def fire_alerts(parcel_id: str, days: int = 3, user=Depends(current_user)):
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        geometry = parcel.get("geometry") or parcel.get("geojson")
        bbox = _geometry_bbox(geometry)
        if not bbox:
            return {"parcel_id": parcel_id, "provider": "demo", "alerts": [],
                    "note": "Parsel geometrisi yok — yangın kontrolü yapılamadı"}
        # Parsel çevresine ~2km tampon eklenir (küçük parsellerde FIRMS'in
        # 375m piksel çözünürlüğü tek başına parseli kapsamayabilir).
        buffered = (bbox[0] - 0.02, bbox[1] - 0.02, bbox[2] + 0.02, bbox[3] + 0.02)
        provider = await get_satellite_provider(db, "fire")
        try:
            alerts = provider.get_fire_alerts(buffered, days=days)
        except Exception as e:
            raise HTTPException(502, f"Yangın verisi alınamadı: {e}")
        return {"parcel_id": parcel_id, "provider": provider.name, "alerts": alerts}

    class TaskingRequestBody(BaseModel):
        parcel_id: str
        resolution_cm: int = 50
        priority: str = "standard"

    @api_router.post("/satellite/tasking-request")
    async def tasking_request(body: TaskingRequestBody, request: Request,
                               user=Depends(require_permission("field_ops:view"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        geometry = parcel.get("geometry") or parcel.get("geojson")
        provider = await get_satellite_provider(db, "tasking")
        result = provider.request_tasking(geometry, body.resolution_cm, body.priority)
        await log_audit(db, user, action="request", entity="satellite_tasking", entity_id=body.parcel_id,
                         new_value={"provider": provider.name, **result}, request=request)
        return {"parcel_id": body.parcel_id, "provider": provider.name, **result}
