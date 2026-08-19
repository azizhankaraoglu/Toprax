"""
=====================================================================
Toprax — Uydu Görüntü Provider Soyutlaması (IT-17 → gerçek çoklu-
sağlayıcı mimarisi, 2026-07-11 araştırma raporuna göre genişletildi)
=====================================================================
Bu dosya artık TEK bir mock sağlayıcı değil, gerçek bir **Provider
Abstraction Layer**: `TOPRAX_Uydu_Goruntu_Ekosistemi_Arastirma.md`
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
import math
import random
import time
import zlib
import requests
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


class SatelliteProvider(ABC):
    """Araştırma raporu §Teknik Beklentiler'deki ortak arayüzün TOPRAX'e
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

    def __init__(self, map_key: str, timeout: int = 30):
        self.map_key = map_key
        # 15 sn NASA'nın yavaş anlarında yetmiyordu (bkz. get_fire_alerts).
        self.timeout = timeout

    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        raise NotImplementedError("NASA FIRMS NDVI üretmez — get_fire_alerts kullanın")

    def get_fire_alerts(self, bbox: Tuple[float, float, float, float], days: int = 1) -> List[Dict]:
        min_lon, min_lat, max_lon, max_lat = bbox
        days = max(1, min(days, 10))   # FIRMS area API 1-10 gün destekler
        url = f"{self.AREA_URL}/{self.map_key}/VIIRS_SNPP_NRT/{min_lon},{min_lat},{max_lon},{max_lat}/{days}"
        # 2026-08-19 — TEKRAR DENEME. NASA FIRMS zaman zaman birkaç saniyeliğine
        # yanıt vermiyor (canlıda görüldü: aynı istek önce ConnectTimeout,
        # 2 dakika sonra 0,7 sn'de HTTP 200). Tek denemede pes etmek, çalışan
        # bir entegrasyonu ekranda "veri alınamadı" gibi gösteriyordu.
        last_err = None
        resp = None
        for attempt in range(3):
            try:
                resp = requests.get(url, timeout=self.timeout)
                resp.raise_for_status()
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        if resp is None:
            raise last_err
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
    UP42 pazaryeri — TOPRAX'in kendi başına onlarca VHR sağlayıcıya
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
                "message": "[MOCK MOD] Talep TOPRAX içinde kaydedildi, UP42'ye GÖNDERİLMEDİ "
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
                       "aktivasyonu sonrası tamamlanacak (bkz. TOPRAX_Uydu_Goruntu_Ekosistemi_Arastirma.md §8).",
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


# =====================================================================
# KONU 1 (3ONCELIK.md) — Görüntü Künyesi + Kademeli Kalite + Akıllı Tasking
# =====================================================================

# 1.1 — Her sağlayıcının nominal yer çözünürlüğü (metre/piksel). Görüntü
# künyesinde HER ZAMAN gösterilir; kullanıcı hangi çözünürlükteki veriye
# dayanarak karar verdiğini bilmeli.
PROVIDER_RESOLUTION_M = {"demo": 10.0, "sentinel_hub": 10.0, "nasa_firms": 375.0, "up42": 0.5}


def provider_resolution_m(provider) -> float:
    return PROVIDER_RESOLUTION_M.get(getattr(provider, "name", ""), 10.0)


def build_image_meta(provider, date: Optional[str], tier: Optional[str] = None) -> Dict:
    """1.1 — Görüntü künyesi: her analiz sonucunun yanında kaynak + tarih +
    çözünürlük (+ gerçek/mock + abonelik seviyesi). UI küçük bir künye gösterir."""
    name = getattr(provider, "name", "demo")
    return {
        "source": name, "date": date, "resolution_m": provider_resolution_m(provider),
        "is_real": name != "demo", "tier": tier,
    }


# 1.2 — Kademeli kalite: abonelik seviyesi (Feature Flags/Licensing, IT-33)
# hangi sağlayıcıya/çözünürlüğe/tazeliğe erişileceğini belirler. KOD DALLANMASI
# YOK — davranış bu tablodan gelir (provider değişince kod değişmez).
SATELLITE_TIERS = {
    "basic":    {"allowed": ["demo"], "max_resolution_m": 10.0, "min_refresh_days": 30, "tasking": False},
    "standard": {"allowed": ["sentinel_hub", "nasa_firms", "demo"], "max_resolution_m": 10.0, "min_refresh_days": 7, "tasking": False},
    "premium":  {"allowed": ["sentinel_hub", "nasa_firms", "up42", "demo"], "max_resolution_m": 0.5, "min_refresh_days": 1, "tasking": True},
}
DEFAULT_TIER = "standard"


async def resolve_tenant_satellite_tier(db) -> str:
    """Tenant'ın uydu abonelik seviyesi (config/flag-driven, kod dallanması değil).
    Kaynak: feature_flags `satellite_premium`/`satellite_basic` (IT-33) → yoksa
    DEFAULT_TIER."""
    try:
        flags = {f["key"]: f.get("enabled") for f in await db.feature_flags.find({}, {"_id": 0}).to_list(200)}
        if flags.get("satellite_premium"):
            return "premium"
        if flags.get("satellite_basic"):
            return "basic"
    except Exception:
        pass
    return DEFAULT_TIER


async def get_satellite_provider_tiered(db, capability: str = "ndvi"):
    """get_satellite_provider'ın abonelik-farkında sarmalayıcısı: tenant tier'ı
    seçilen sağlayıcıya izin vermiyorsa Demo'ya düşer (yüksek çözünürlük düşük
    abonelikte harcanmaz). Mevcut get_satellite_provider DEĞİŞMEDEN korunur."""
    provider = await get_satellite_provider(db, capability)
    tier = await resolve_tenant_satellite_tier(db)
    allowed = SATELLITE_TIERS.get(tier, SATELLITE_TIERS[DEFAULT_TIER])["allowed"]
    if provider.name not in allowed:
        provider = DemoSatelliteProvider()
    return provider, tier


# 1.3 — Akıllı Tasking: anomali şüphesinde TEK parsel için otomatik VHR talebi,
# tenant aylık kotasına tabi (pahalı veri sadece şüphe oluşan yerde harcanır).
DEFAULT_MONTHLY_TASKING_QUOTA = 20


async def _tasking_quota(db) -> dict:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    doc = await db.satellite_tasking_quota.find_one({"month": month}, {"_id": 0})
    if not doc:
        doc = {"month": month, "used": 0, "monthly_limit": DEFAULT_MONTHLY_TASKING_QUOTA}
        await db.satellite_tasking_quota.insert_one(dict(doc))
    return doc


async def _consume_tasking_quota(db) -> bool:
    """Atomik $inc + limit guard (race condition önlenir)."""
    await _tasking_quota(db)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    res = await db.satellite_tasking_quota.find_one_and_update(
        {"month": month, "$expr": {"$lt": ["$used", "$monthly_limit"]}},
        {"$inc": {"used": 1}}, return_document=True, projection={"_id": 0},
    )
    return res is not None


async def maybe_auto_task_on_anomaly(db, parcel: dict, reason: str) -> Dict:
    """1.3'ün can alıcı noktası — anomali şüphesinde otomatik tasking. SADECE
    tier tasking'e izin veriyorsa VE aylık kota müsaitse çalışır; aksi halde
    'atlandi' döner (sessiz hata YOK). Sonuç satellite_tasking_requests'e yazılır."""
    tier = await resolve_tenant_satellite_tier(db)
    if not SATELLITE_TIERS.get(tier, {}).get("tasking"):
        return {"status": "atlandi", "reason": "abonelik seviyesi tasking desteklemiyor", "tier": tier}
    if not await _consume_tasking_quota(db):
        return {"status": "atlandi", "reason": "aylik tasking kotasi dolu", "tier": tier}
    provider = await get_satellite_provider(db, "tasking")
    geometry = parcel.get("geometry") or parcel.get("geojson")
    result = provider.request_tasking(geometry, resolution_cm=50, priority="high")
    doc = {
        "id": str(uuid.uuid4()), "parcel_id": parcel.get("id"), "reason": reason,
        "provider": provider.name, "auto": True, "priority": "high", "tier": tier,
        "created_at": datetime.now(timezone.utc).isoformat(), **result,
    }
    await db.satellite_tasking_requests.insert_one(doc)
    doc.pop("_id", None)
    return {"status": "talep_edildi", **doc}


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


def register_satellite_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    """
    Mevcut `/satellite/ndvi/*` uçları (extras.py) DEĞİŞMEDEN kalıyor —
    bu fonksiyon SADECE araştırma raporunun getirdiği YENİ yetenekler
    için (yangın alarmı + VHR tasking talebi + sağlayıcı durumu) uç ekler.

    MİMARİ DÜZELTME (2026-07-24): bu fonksiyon önceden `require_feature`
    parametresini HİÇ ALMIYORDU — "gis" (Coğrafi Bilgi Sistemi / Uydu)
    modülü God Mode'dan kapatılsa bile bu uçlar hiçbir zaman 403 dönmüyordu.
    """
    from fastapi import HTTPException, Depends, Request
    from pydantic import BaseModel
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/satellite/providers/status")
    async def satellite_providers_status(user=Depends(current_user), _feat=Depends(require_feature("gis"))):
        """Ayarlar/Uydu ekranının hangi yeteneğin GERÇEK mi DEMO mu
        çalıştığını göstermesi için (Integration Center kartlarının yanında)."""
        result = {}
        for capability in ("ndvi", "fire", "tasking"):
            provider = await get_satellite_provider(db, capability)
            result[capability] = {"active_provider": provider.name, "is_real": provider.name != "demo"}
        return result

    # =====================================================================
    # YANGIN YAKINLIK BARİYERLERİ (2026-08-19, kullanıcı isteği)
    # =====================================================================
    # "Tarla özelinde her tarla için 20 km yakınlık bariyeri çizelim ve
    #  bildirim gönderelim çiftçiye; genel olarak kooperatif tarlalarının
    #  50 km yakınındaki yangınları dashboard'da gösterelim."
    #
    # Neden iki farklı yarıçap: 20 km bir çiftçinin O GÜN müdahale/tedbir
    # kararı vereceği mesafedir (duman, kıvılcım taşınması, tahliye);
    # 50 km ise kooperatif yönetiminin bölgesel farkındalık mesafesidir.
    PARCEL_FIRE_RADIUS_KM = 20.0
    COOP_FIRE_RADIUS_KM = 50.0

    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """İki nokta arası mesafe (km). FIRMS bbox sorgusu KARE bir alan
        döndürür; gerçek 'yakınlık' dairesel olduğu için sonuçlar burada
        mesafeye göre yeniden süzülür — köşelerdeki uzak yangınlar
        'yakınımda' diye raporlanmaz."""
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1.0, math.sqrt(a)))

    def _bbox_for_radius(lat: float, lon: float, radius_km: float):
        """Yarıçapı kapsayan bbox — FIRMS alan sorgusu bbox ister."""
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
        return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)

    def _centroid_of(geometry):
        pts = []

        def walk(node):
            if isinstance(node, (int, float)):
                return
            if node and isinstance(node[0], (int, float)):
                pts.append(node)
                return
            for child in node:
                walk(child)

        walk((geometry or {}).get("coordinates") or [])
        if not pts:
            return None
        return (sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts))  # (lat, lon)

    @api_router.get("/satellite/fire-alerts/{parcel_id}")
    async def fire_alerts(parcel_id: str, days: int = 3, radius_km: float = PARCEL_FIRE_RADIUS_KM,
                          user=Depends(current_user), _feat=Depends(require_feature("gis"))):
        """Parselin `radius_km` (varsayılan 20 km) yarıçapındaki yangınlar.

        Yanıt her yangın için parsele UZAKLIĞI da taşır — ekran "12 km
        güneybatıda" diyebilsin; ham koordinat çiftçiye bir şey ifade etmez.
        """
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        geometry = parcel.get("geometry") or parcel.get("geojson")
        center = _centroid_of(geometry)
        if not center:
            return {"parcel_id": parcel_id, "provider": "demo", "alerts": [], "radius_km": radius_km,
                    "note": "Parsel geometrisi yok — yangın kontrolü yapılamadı"}
        lat, lon = center
        provider = await get_satellite_provider(db, "fire")
        try:
            raw = provider.get_fire_alerts(_bbox_for_radius(lat, lon, radius_km), days=days)
        except Exception as e:
            raise HTTPException(502, f"Yangın verisi alınamadı: {e}")

        alerts = []
        for a in raw or []:
            # ⚠️ Sağlayıcı `lat`/`lon` döndürür (bkz. NasaFirmsProvider.
            # get_fire_alerts) — `latitude`/`longitude` DEĞİL. İlk yazımda
            # uzun adlar okunuyordu ve HER yangın sessizce elenip liste boş
            # kalıyordu; FIRMS o gün hiç yangın döndürmediği için hata fark
            # edilmiyordu. Her iki ad da kabul ediliyor (ileride sağlayıcı
            # değişirse kırılmasın).
            alat = a.get("lat", a.get("latitude"))
            alon = a.get("lon", a.get("longitude"))
            if alat is None or alon is None:
                continue
            dist = _haversine_km(lat, lon, float(alat), float(alon))
            if dist <= radius_km:
                alerts.append({**a, "mesafe_km": round(dist, 1),
                               "yon": _bearing_label(lat, lon, float(alat), float(alon))})
        alerts.sort(key=lambda a: a["mesafe_km"])
        return {"parcel_id": parcel_id, "provider": provider.name, "radius_km": radius_km,
                "alerts": alerts, "en_yakin_km": alerts[0]["mesafe_km"] if alerts else None,
                "parsel_merkezi": {"lat": lat, "lon": lon}}

    def _bearing_label(lat1, lon1, lat2, lon2) -> str:
        """Yangının parsele göre yönü (kuzeydoğu, güney…)."""
        dlon = math.radians(lon2 - lon1)
        y = math.sin(dlon) * math.cos(math.radians(lat2))
        x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
             - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon))
        brng = (math.degrees(math.atan2(y, x)) + 360) % 360
        dirs = ["kuzey", "kuzeydoğu", "doğu", "güneydoğu", "güney", "güneybatı", "batı", "kuzeybatı"]
        return dirs[int((brng % 360) / 45 + 0.5) % 8]

    @api_router.get("/satellite/fire-summary")
    async def fire_summary(days: int = 2, radius_km: float = COOP_FIRE_RADIUS_KM,
                           user=Depends(current_user), _feat=Depends(require_feature("gis"))):
        """Kooperatif parsellerinin `radius_km` (varsayılan 50 km) yakınındaki
        yangınların ÖZETİ — Dashboard'daki tek satırlık uyarı bunu tüketir.

        Uygulama: tüm parsellerin kapsadığı alanın merkezinden TEK bir FIRMS
        sorgusu yapılır (5.000 parsel için ayrı ayrı sorgu FIRMS kotasını
        anında tüketirdi), sonra her yangın en yakın parsele göre süzülür.
        """
        parcels = await db.parcels.find(
            {"is_active": {"$ne": False}, "geometry": {"$ne": None}},
            {"_id": 0, "id": 1, "name": 1, "village": 1, "geometry": 1, "farmer_id": 1}
        ).limit(3000).to_list(3000)
        centers = []
        for p in parcels:
            c = _centroid_of(p.get("geometry"))
            if c:
                centers.append((c[0], c[1], p))
        if not centers:
            return {"available": False, "reason": "Sınırı tanımlı parsel yok", "yangin_sayisi": 0}

        lats = [c[0] for c in centers]
        lons = [c[1] for c in centers]
        mid_lat, mid_lon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
        # Kooperatifin yayılımı + yarıçap kadar bbox
        span_km = _haversine_km(min(lats), min(lons), max(lats), max(lons)) / 2
        provider = await get_satellite_provider(db, "fire")
        try:
            raw = provider.get_fire_alerts(
                _bbox_for_radius(mid_lat, mid_lon, span_km + radius_km), days=days)
        except Exception as e:
            return {"available": False, "reason": f"Yangın verisi alınamadı: {e}", "yangin_sayisi": 0}

        hits = []
        for a in raw or []:
            # Sağlayıcı `lat`/`lon` döndürür (yukarıdaki not).
            alat = a.get("lat", a.get("latitude"))
            alon = a.get("lon", a.get("longitude"))
            if alat is None or alon is None:
                continue
            nearest = min(centers, key=lambda c: _haversine_km(c[0], c[1], float(alat), float(alon)))
            dist = _haversine_km(nearest[0], nearest[1], float(alat), float(alon))
            if dist <= radius_km:
                hits.append({
                    **a, "mesafe_km": round(dist, 1),
                    "en_yakin_parsel": nearest[2].get("name"),
                    "en_yakin_parsel_id": nearest[2].get("id"),
                    "koy": nearest[2].get("village"),
                    "yon": _bearing_label(nearest[0], nearest[1], float(alat), float(alon)),
                })
        hits.sort(key=lambda h: h["mesafe_km"])
        kritik = [h for h in hits if h["mesafe_km"] <= PARCEL_FIRE_RADIUS_KM]
        return {
            "available": True, "provider": provider.name, "radius_km": radius_km, "gun": days,
            "yangin_sayisi": len(hits), "kritik_sayisi": len(kritik),
            "en_yakin": hits[0] if hits else None,
            "etkilenen_koyler": sorted({h["koy"] for h in kritik if h.get("koy")}),
            "yanginlar": hits[:50],
            "mesaj": (f"{len(hits)} yangın {radius_km:.0f} km çevrede"
                      + (f", en yakını {hits[0]['mesafe_km']} km {hits[0]['yon']}da "
                         f"({hits[0]['en_yakin_parsel']})" if hits else "")
                      if hits else f"{radius_km:.0f} km çevrede aktif yangın yok"),
        }

    # =====================================================================
    # Denetim eklentisi (2026-07-25) — NASA FIRMS otomatik tarama + Parsel
    # kartına yangın göstergesi + Communication Policy bildirimi. Kullanıcı
    # isteği: "sorgulama frekansı parametrik olmalı ve admin belirlemeli,
    # varsayılan 6 saat" — `karne_parameters` (karne_engine.py) ile AYNI
    # tek-doküman GET/PUT ayar deseni (yeni bir ayar mimarisi İCAT EDİLMEDİ).
    # Cron YOK (proje konvansiyonu) — bu bir TICK-ENDPOINT'tir, mevcut
    # `POST /remote-sensing/scheduler/run` deseniyle AYNI aile.
    # =====================================================================
    FIRE_SCAN_DEFAULT_HOURS = 6

    @api_router.get("/satellite/fire-scan-settings")
    async def get_fire_scan_settings(user=Depends(current_user), _feat=Depends(require_feature("gis"))):
        doc = await db.fire_scan_settings.find_one({"key": "default"}, {"_id": 0})
        return {"frequency_hours": (doc or {}).get("frequency_hours", FIRE_SCAN_DEFAULT_HOURS)}

    @api_router.put("/satellite/fire-scan-settings")
    async def update_fire_scan_settings(body: dict, request: Request,
                                        user=Depends(require_permission("remote_sensing:settings")),
                                        _feat=Depends(require_feature("gis"))):
        hours = body.get("frequency_hours")
        if not isinstance(hours, (int, float)) or hours <= 0:
            raise HTTPException(400, "frequency_hours pozitif bir sayı olmalı")
        await db.fire_scan_settings.update_one({"key": "default"}, {"$set": {"frequency_hours": hours}}, upsert=True)
        await log_audit(db, user, action="update", entity="fire_scan_settings", entity_id="default",
                        new_value={"frequency_hours": hours}, request=request)
        return {"frequency_hours": hours}

    @api_router.post("/satellite/fire-scan/run")
    async def run_fire_scan(request: Request, user=Depends(require_permission("remote_sensing:settings")),
                            _feat=Depends(require_feature("gis"))):
        """Tick-endpoint — `frequency_hours` süresi dolmuş (veya hiç
        kontrol edilmemiş) parselleri tarar, NASA FIRMS'ten yangın kontrolü
        yapar, `Parcel.fire_status`'ü günceller, tespit varsa Communication
        Policy'ye `nasa_firms_alert_detected` event'i yayınlar (KENDİ
        bildirim mantığı YOK — mevcut event_bus/communication_policy'yi
        kullanır, remote_sensing/notifications.py'nin AYNI deseni)."""
        from event_bus import publish
        # Kota/süre koruması: NASA FIRMS senkron `requests` ile çağrılıyor
        # (aiohttp değil) — çok sayıda parsel TEK tick'te taranırsa istek
        # zaman aşımına uğrar (remote_sensing/tasks.py'nin process_pending_
        # tasks(max_tasks=25) İLE AYNI kota mantığı burada da uygulanıyor).
        # Kalan parseller BİR SONRAKİ tick'te taranır — sessizce eksik
        # BIRAKILMAZ, yanıtta `more_due` ile dürüstçe bildirilir.
        MAX_PARCELS_PER_TICK = 25
        settings_doc = await db.fire_scan_settings.find_one({"key": "default"}, {"_id": 0})
        freq_hours = (settings_doc or {}).get("frequency_hours", FIRE_SCAN_DEFAULT_HOURS)
        provider = await get_satellite_provider(db, "fire")
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=freq_hours)).isoformat()
        due_filter = {
            "is_active": {"$ne": False},
            "geometry": {"$ne": None},
            "$or": [{"fire_status.checked_at": {"$exists": False}},
                    {"fire_status.checked_at": {"$lt": cutoff}}],
        }
        total_due = await db.parcels.count_documents(due_filter)
        due_parcels = await db.parcels.find(due_filter, {"_id": 0}).to_list(MAX_PARCELS_PER_TICK)

        scanned, alerts_found = 0, 0
        for parcel in due_parcels:
            bbox = _geometry_bbox(parcel.get("geometry") or parcel.get("geojson"))
            if not bbox:
                continue
            buffered = (bbox[0] - 0.02, bbox[1] - 0.02, bbox[2] + 0.02, bbox[3] + 0.02)
            try:
                alerts = provider.get_fire_alerts(buffered, days=1)
            except Exception:
                continue
            scanned += 1
            has_fire = bool(alerts)
            fire_status = {
                "active": has_fire, "checked_at": now.isoformat(),
                "alert_count": len(alerts), "latest": alerts[0] if alerts else None,
            }
            await db.parcels.update_one({"id": parcel["id"]}, {"$set": {"fire_status": fire_status}})
            if has_fire:
                alerts_found += 1
                await publish(db, "nasa_firms_alert_detected", {
                    "parcel_id": parcel["id"], "farmer_id": parcel.get("farmer_id"),
                    "alert_count": len(alerts), "detected_at": now.isoformat(),
                    "confidence": alerts[0].get("confidence") if alerts else None,
                })

        await log_audit(db, user, action="fire_scan", entity="satellite", entity_id="tick",
                        new_value={"scanned": scanned, "alerts_found": alerts_found}, request=request)
        return {"scanned": scanned, "total_due": total_due, "more_due": total_due > len(due_parcels),
                "alerts_found": alerts_found, "frequency_hours": freq_hours, "provider": provider.name}

    class TaskingRequestBody(BaseModel):
        parcel_id: str
        resolution_cm: int = 50
        priority: str = "standard"

    @api_router.post("/satellite/tasking-request")
    async def tasking_request(body: TaskingRequestBody, request: Request,
                               user=Depends(require_permission("field_ops:view")),
                               _feat=Depends(require_feature("gis"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        geometry = parcel.get("geometry") or parcel.get("geojson")
        provider = await get_satellite_provider(db, "tasking")
        result = provider.request_tasking(geometry, body.resolution_cm, body.priority)
        # Manuel tasking talebi de kayıt altına alınır (auto=False) — otomatik
        # (1.3) ile aynı koleksiyon, izlenebilirlik için.
        rec = {"id": str(uuid.uuid4()), "parcel_id": body.parcel_id, "reason": "manuel",
               "provider": provider.name, "auto": False, "priority": body.priority,
               "resolution_cm": body.resolution_cm,
               "created_at": datetime.now(timezone.utc).isoformat(), **result}
        await db.satellite_tasking_requests.insert_one(dict(rec))
        await log_audit(db, user, action="request", entity="satellite_tasking", entity_id=body.parcel_id,
                         new_value={"provider": provider.name, **result}, request=request)
        return {"parcel_id": body.parcel_id, "provider": provider.name, **result}

    @api_router.get("/satellite/tasking-quota")
    async def tasking_quota_status(user=Depends(current_user), _feat=Depends(require_feature("gis"))):
        """1.3 — Aylık VHR tasking kotası + tenant abonelik seviyesi (kademeli kalite)."""
        q = await _tasking_quota(db)
        tier = await resolve_tenant_satellite_tier(db)
        return {**q, "remaining": max(0, q["monthly_limit"] - q["used"]),
                "tier": tier, "tasking_allowed": SATELLITE_TIERS.get(tier, {}).get("tasking", False)}

    @api_router.get("/satellite/tasking-requests")
    async def list_tasking_requests(user=Depends(current_user), _feat=Depends(require_feature("gis"))):
        return await db.satellite_tasking_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
