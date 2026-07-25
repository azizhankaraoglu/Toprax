"""
=====================================================================
TOPRAX — Google Earth Engine + NASA HLS (Faz 9C, 2026-07-25)
=====================================================================
Kullanıcının verdiği tam spesifikasyona göre: NASA HLS (Harmonized
Landsat Sentinel-2) veri setinden 2-3 günlük sıklıkta NDVI zaman serisi
+ kesilmiş uydu görüntüsü. `routes.py`'nin `POST /v1/analyze-field`'i
(dışarıdan `POST /api/v1/analyze-field` — mevcut `api_router` zaten
`/api` önekiyle mount edilir) LİTERAL sözleşmeyi (istenen tam istek/
yanıt şeması) korur; `GEEHLSProvider` AYNI mantığı `IRemoteSensingProvider`
arayüzüne sararak mevcut Tarama Politikası/scheduler/AI-yorumu/bildirim
boru hattına da bağlar (bkz. service.py).
"""
from .service import GEEHLSProvider, analyze_field
from .routes import register_gee_hls_routes

__all__ = ["GEEHLSProvider", "analyze_field", "register_gee_hls_routes"]
