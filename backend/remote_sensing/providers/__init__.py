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
from .placeholders import PlanetProvider, AirbusProvider, UP42RSProvider

_PROVIDERS = {
    "eosda": EOSDAProvider,
    "sentinel2": Sentinel2Provider,
    "planet": PlanetProvider,
    "airbus": AirbusProvider,
    "up42": UP42RSProvider,
}


async def get_remote_sensing_provider(db, tenant_id: str = None,
                                      provider_override: str = None) -> IRemoteSensingProvider:
    """Tenant'ın aktif RS sağlayıcısını döner. provider_override (Tarama
    Politikası) verilmişse onu dener; yoksa varsayılan EOSDA."""
    itype = provider_override or "eosda"

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


__all__ = ["IRemoteSensingProvider", "EOSDAProvider", "Sentinel2Provider", "get_remote_sensing_provider"]
