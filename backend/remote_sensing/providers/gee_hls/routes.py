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

from .schemas import AnalyzeFieldRequest
from .service import analyze_field, InvalidFieldRequest, NoCleanImageFound, GeeRuntimeError


def register_gee_hls_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.post("/v1/analyze-field")
    async def gee_analyze_field(body: AnalyzeFieldRequest, request: Request,
                                user=Depends(require_permission("remote_sensing:manual_sync")),
                                _feat=Depends(require_feature("remote_sensing"))):
        try:
            result = await analyze_field(db, body.polygon, body.start_date, body.end_date)
        except InvalidFieldRequest as e:
            raise HTTPException(400, str(e))
        except NoCleanImageFound as e:
            raise HTTPException(404, str(e))
        except GeeRuntimeError as e:
            raise HTTPException(502, str(e))
        await log_audit(db, user, action="gee_analyze_field", entity="remote_sensing",
                        entity_id=f"{body.start_date}..{body.end_date}",
                        new_value={"points": len(result.get("ndvi_history", []))}, request=request)
        return result
