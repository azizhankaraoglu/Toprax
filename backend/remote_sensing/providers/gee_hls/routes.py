"""
GEE/HLS — HTTP yüzeyi. CLAUDE.md konvansiyon #1 (modül kayıt kalıbı):
`register_gee_hls_routes(api_router, db, current_user, require_permission,
log_audit, require_feature)`. `server.py`'ye yeni domain kodu EKLENMEZ.

`POST /v1/analyze-field` — kullanıcının verdiği LİTERAL spesifikasyonun
istek/yanıt şeması harfiyen korunur (TOPRAX'ın standart {status,data,...}
zarfı KULLANILMAZ). Mevcut `api_router` zaten `/api` önekiyle mount
edildiğinden dışarıdan tam olarak `POST /api/v1/analyze-field` adresinden
erişilir.
"""
from fastapi import Depends, HTTPException, Request

from .schemas import AnalyzeFieldRequest, ThumbnailRequest
from .service import (analyze_field, get_latest_thumbnail_url, InvalidFieldRequest,
                      NoCleanImageFound, GeeRuntimeError)


def register_gee_hls_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.post("/v1/analyze-field")
    async def gee_analyze_field(body: AnalyzeFieldRequest, request: Request,
                                user=Depends(require_permission("remote_sensing:manual_sync")),
                                _feat=Depends(require_feature("remote_sensing"))):
        try:
            result = await analyze_field(db, body.polygon, body.start_date, body.end_date, body.indices)
        except InvalidFieldRequest as e:
            raise HTTPException(400, str(e))
        except NoCleanImageFound as e:
            raise HTTPException(404, str(e))
        except GeeRuntimeError as e:
            raise HTTPException(502, str(e))
        await log_audit(db, user, action="gee_analyze_field", entity="remote_sensing",
                        entity_id=f"{body.start_date}..{body.end_date}",
                        new_value={"points": len(result.get("ndvi_history", [])),
                                   "indices": result.get("meta", {}).get("indices", [])}, request=request)
        return result

    @api_router.post("/v1/field-thumbnail")
    async def gee_field_thumbnail(body: ThumbnailRequest,
                                  user=Depends(require_permission("remote_sensing:view")),
                                  _feat=Depends(require_feature("remote_sensing"))):
        """Sayısal seri ÜRETMEDEN sadece güncel gerçek-renkli görüntü.

        Analiz ucundan (`/v1/analyze-field`) ayrı tutulmasının sebebi
        maliyet/izin: bu uç yalnızca `remote_sensing:view` ister (analiz
        `manual_sync` istiyor) ve GEE'de tek bir sahne render'ı yapar —
        harita popup'ı gibi salt-görüntüleme yerlerinde tam bir zaman
        serisi analizi tetiklemek gereksizdir. Görüntü üretilemezse HATA
        DEĞİL, `{"latest_image_url": null}` döner."""
        url = await get_latest_thumbnail_url(db, body.polygon, body.days)
        return {"latest_image_url": url}
