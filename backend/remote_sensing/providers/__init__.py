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
from .placeholders import PlanetProvider, AirbusProvider, UP42RSProvider

_PROVIDERS = {
    "eosda": EOSDAProvider,
    "planet": PlanetProvider,
    "airbus": AirbusProvider,
    "up42": UP42RSProvider,
}


async def get_remote_sensing_provider(db, tenant_id: str = None,
                                      provider_override: str = None) -> IRemoteSensingProvider:
    """Tenant'ın aktif RS sağlayıcısını döner. provider_override (Tarama
    Politikası) verilmişse onu dener; yoksa varsayılan EOSDA."""
    itype = provider_override or "eosda"
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


__all__ = ["IRemoteSensingProvider", "EOSDAProvider", "get_remote_sensing_provider"]
