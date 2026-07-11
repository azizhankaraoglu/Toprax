"""api_envelope.py -- PR-22: API Konvansiyon Standardizasyonu (/api/v1).

TASARIM KARARI (kritik): Mevcut `/api/*` uçları ~370 route'tur ve frontend
bunlarin HAM (envelope'suz) JSON gövdesini dogrudan tuketir (`response.data`
bir liste/obje, `err.response.data.detail` bir hata mesaji vb.). Tum bu
uclari yeni bir data/meta/error zarfina gecirmek, PR-22'nin kendi kabul
kriteriyle CELISIR: "mevcut istemciler kirilmaz". Bu yuzden mevcut `/api`
yuzeyine HICBIR SEKILDE DOKUNULMAZ.

Bunun yerine: disaridaki entegratorlerin (Postman/PR-25, Gelistirici
Portali/PR-26, API Key ile gelen makine-makine cagrilar/PR-24) kullanacagi
YENI, sabit-versiyonlu bir yuzey eklenir: `/api/v1/*`. Bu yuzey, ayni
route'lari YENIDEN YAZMAZ -- ic ASGI transport uzerinden mevcut `/api/*`
handler'ina delege eder ve yaniti standart zarfa sarar:

    basarili:  {"data": <orijinal govde>, "meta": {...}, "error": null}
    hatali:    {"data": null, "meta": {...}, "error": {"code": <http_status>, "message": <detail>}}

Tarih formati: kod tabani zaten her yerde `datetime.now(timezone.utc).isoformat()`
kullaniyor (ISO8601) -- bu PR icin ayrica bir donusum GEREKMEZ, mevcut
konvansiyon zaten dogru.

Isimlendirme: yeni eklenecek route'lar icin snake_case onerilir (PR-22
"Sizin Yapmanız Gerekir" maddesi). Var olan bazi path'ler (orn.
/platform-core/health) kebab-case'tir -- geriye donuk uyumluluk icin
DEGISTIRILMEZ, sadece yeni endpoint'ler bu kurala tabidir.
"""
import json
import time
from datetime import datetime, timezone

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

API_V1_VERSION = "v1"


def register_api_v1_proxy(app):
    """`/api/v1/{path}` altina gelen HER istegi mevcut `/api/{path}`
    handler'ina (ayni app icinde, agsizca ASGI transport ile, ekstra ag
    turu YOK) delege eder ve yaniti standart zarfa sarar."""

    @app.api_route(
        "/api/v1/{rest_of_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def api_v1_envelope(rest_of_path: str, request: Request):
        started = time.monotonic()
        body = await request.body()

        # Authorization, Content-Type gibi basliklari oldugu gibi ilet;
        # Host/Content-Length gibi transport-seviyeli basliklar ASGI
        # transport tarafindan zaten yeniden hesaplanir.
        forward_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
        }

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://internal") as client:
            upstream = await client.request(
                request.method,
                f"/api/{rest_of_path}",
                params=request.query_params,
                content=body,
                headers=forward_headers,
            )

        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        meta = {
            "api_version": API_V1_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": elapsed_ms,
        }

        content_type = upstream.headers.get("content-type", "")
        if "application/json" not in content_type:
            # JSON olmayan yanitlar (dosya indirme vb.) zarfa SARILMAZ,
            # oldugu gibi geri dondurulur.
            return JSONResponse(
                status_code=upstream.status_code,
                content={"data": None, "meta": meta,
                         "error": {"code": upstream.status_code,
                                   "message": "Bu uc /api/v1 zarfini desteklemiyor (JSON olmayan yanit); dogrudan /api uzerinden cagirin."}},
            ) if upstream.status_code >= 400 else JSONResponse(
                status_code=upstream.status_code, content={"raw": upstream.text}
            )

        try:
            payload = upstream.json()
        except json.JSONDecodeError:
            payload = upstream.text

        if upstream.status_code >= 400:
            message = payload.get("detail") if isinstance(payload, dict) else payload
            return JSONResponse(
                status_code=upstream.status_code,
                content={"data": None, "meta": meta,
                         "error": {"code": upstream.status_code, "message": message}},
            )

        return JSONResponse(
            status_code=upstream.status_code,
            content={"data": payload, "meta": meta, "error": None},
        )
