"""
TOPRAX Remote Sensing — Provider factory.

`get_remote_sensing_provider(db, tenant_id)` Integration Center'dan (IT-01,
`db.integrations` type="eosda") hangi provider'ın aktif olduğunu okur.
Kimlik yoksa VEYA mock_mode açıksa EOSDAProvider mock modda döner (gerçek
dış çağrı yapılmaz) — satellite_provider.get_satellite_provider() ile AYNI
kural. Karar 1: EOSDA `SatelliteProvider`'ın yeni bir alt sınıfı gibi eklenir,
ABC kırılmaz.
"""
from .base import IRemoteSensingProvider
from .eosda import EOSDAProvider
from .sentinel2 import Sentinel2Provider
from .gee_hls import GEEHLSProvider
from .placeholders import PlanetProvider, AirbusProvider, UP42RSProvider

_PROVIDERS = {
    "eosda": EOSDAProvider,
    "sentinel2": Sentinel2Provider,
    "gee_hls": GEEHLSProvider,
    "planet": PlanetProvider,
    "airbus": AirbusProvider,
    "up42": UP42RSProvider,
}

#: Uzaktan algılamanın kullanıcıya görünen ADI. Ekranlarda sağlayıcı adı
#: (EOSDA/Sentinel-2/GEE) DEĞİL bu marka gösterilir — sağlayıcı bir
#: uygulama detayıdır ve değişebilir; kullanıcı için hizmetin adı sabittir.
#: Frontend bu değeri `GET /remote-sensing/providers/status` üzerinden
#: okur, HİÇBİR ekranda metin olarak tekrarlanmaz (indices.py'nin "tek
#: kaynak" ilkesiyle AYNI).
SATELLITE_BRAND = "Toprax Uydu"

#: Sağlayıcı seçilmediğinde kullanılan varsayılan.
#: 2026-08-18 — EOSDA'dan `gee_hls`'e alındı: GEE/HLS ücretsiz kotayla
#: çalışır, TEK taramada 10 indeksin hepsini üretir (EOSDA'da indeks
#: başına 3 istek maliyeti vardır, bkz. dto.EOSDA_REQUESTS_PER_INDEX) ve
#: Sentinel-2 + Landsat 8/9'u birlikte kullandığı için ziyaret sıklığı
#: daha yüksektir. EOSDA sınıfı KALDIRILMADI — Tarama Politikası'nda
#: `provider_override:"eosda"` ile hâlâ seçilebilir.
DEFAULT_PROVIDER = "gee_hls"

#: Sağlayıcı adı → Integration Center'daki entegrasyon tipi. Durum/monitoring
#: uçları hangi kaydın `enabled`/`mock_mode` bayrağına bakacağını buradan
#: çözer; sabit "eosda" varsayımı varsayılan değişince yanlış olurdu.
#: BURADA durur (services.py'de değil) — monitoring.py de kullanıyor ve
#: services.py zaten monitoring'i import ediyor (döngüsel import olurdu).
PROVIDER_INTEGRATION_TYPES = {
    "gee_hls": "google_earth_engine",
    "sentinel2": "sentinel_hub",
    "eosda": "eosda",
    "planet": "planet_labs",
    "up42": "up42",
}


async def get_remote_sensing_provider(db, tenant_id: str = None,
                                      provider_override: str = None) -> IRemoteSensingProvider:
    """Tenant'ın aktif RS sağlayıcısını döner. provider_override (Tarama
    Politikası) verilmişse onu dener; yoksa varsayılan (DEFAULT_PROVIDER)."""
    itype = provider_override or DEFAULT_PROVIDER

    if itype == "sentinel2":
        # Denetim Faz 5 — YENİ bir entegrasyon tipi EKLENMEDİ, mevcut
        # `sentinel_hub` (Ayarlar > Entegrasyonlar) kimlik bilgisi aynen
        # kullanılır (satellite_provider.SentinelHubProvider ile AYNI CDSE hesabı).
        doc = await db.integrations.find_one({"type": "sentinel_hub"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        enabled = bool(doc and doc.get("enabled"))
        mock_mode = cfg.get("mock_mode", True)
        real = enabled and cfg.get("client_id") and cfg.get("client_secret") and not mock_mode
        return Sentinel2Provider(client_id=cfg.get("client_id"), client_secret=cfg.get("client_secret"),
                                 mock_mode=not real)

    if itype == "gee_hls":
        # Denetim Faz 9C — Integration Center'da AYRI bir "google_earth_engine"
        # tipi (sentinel2'nin sentinel_hub'ı yeniden kullanmasından farklı,
        # çünkü GEE service account kimliği hiçbir mevcut entegrasyonla
        # ÖRTÜŞMÜYOR).
        doc = await db.integrations.find_one({"type": "google_earth_engine"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        enabled = bool(doc and doc.get("enabled"))
        mock_mode = cfg.get("mock_mode", True)
        real = enabled and cfg.get("service_account_email") and cfg.get("service_account_key_json") and not mock_mode
        return GEEHLSProvider(email=cfg.get("service_account_email"),
                              key_json=cfg.get("service_account_key_json"),
                              project=cfg.get("project"), mock_mode=not real)

    doc = await db.integrations.find_one({"type": "eosda"}, {"_id": 0})
    cfg = (doc or {}).get("config", {})
    enabled = bool(doc and doc.get("enabled"))
    mock_mode = cfg.get("mock_mode", True)

    cls = _PROVIDERS.get(itype, EOSDAProvider)
    if cls is EOSDAProvider:
        # Gerçek çağrı SADECE aktif + anahtar var + mock kapalı iken.
        real = enabled and bool(cfg.get("api_key")) and not mock_mode
        return EOSDAProvider(api_key=cfg.get("api_key", ""), mock_mode=not real)
    return cls()


__all__ = ["IRemoteSensingProvider", "EOSDAProvider", "Sentinel2Provider", "GEEHLSProvider",
           "get_remote_sensing_provider", "SATELLITE_BRAND", "DEFAULT_PROVIDER",
           "PROVIDER_INTEGRATION_TYPES"]
