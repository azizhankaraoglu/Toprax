"""
=====================================================================
TOPRAX — Sezon Parametreleri (B3)
=====================================================================
Sezon + ürün bazlı PARAMETRİK katsayılar. Tek gerçek kaynak; iş kuralları
(kod içinde sabit YAZILMAZ) bunları okur:

  - #7 Sözleşme kota→alan kuralı:
        `ton_per_dekar`  → gereken alan = kota_ton / ton_per_dekar
        `sapma_yuzde`    → izin verilen aşağı sapma yüzdesi (onaya düşer)
  - #2 Ekili/söküm tespiti (uydu eşikleri):
        `ndvi_ekili_esigi`  → bu değer ve üstü "ekili" sayılır
        `ndvi_sokum_esigi`  → yüksekten bu değerin altına düşüş "söküldü" sinyali

Kural CROP'a göre parametriktir: bir (sezon, ürün) için parametre TANIMLI
DEĞİLSE o ürün için kural UYGULANMAZ. Böylece "sadece pancarda geçerli"
bir yeni kod dalı yerine yalnızca pancar için parametre seed'lenerek sağlanır.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel


# Varsayılanlar (kullanıcının verdiği örnek: 100 ton kota → en az 25 dekar =
# 4 ton/dekar; sapma %10). NDVI eşikleri #2 için makul başlangıç.
DEFAULT_PANCAR = {
    "ton_per_dekar": 4.0,
    "sapma_yuzde": 10.0,
    "ndvi_ekili_esigi": 0.55,
    "ndvi_sokum_esigi": 0.25,
}


async def get_season_params(db, season: int, crop: str) -> Optional[dict]:
    """Bir (sezon, ürün) için aktif parametre kaydını döner (yoksa None →
    çağıran kural UYGULAMAZ). crop eşleşmesi büyük/küçük harf duyarsız."""
    if season is None or not crop:
        return None
    docs = await db.season_parameters.find(
        {"season": season, "is_active": {"$ne": False}}, {"_id": 0}).to_list(200)
    cl = str(crop).strip().lower()
    for d in docs:
        if str(d.get("crop", "")).strip().lower() == cl:
            return d
    return None


class SeasonParameterUpsert(BaseModel):
    season: int
    crop: str = "Şeker Pancarı"
    ton_per_dekar: float
    sapma_yuzde: float = 10.0
    ndvi_ekili_esigi: float = 0.55
    ndvi_sokum_esigi: float = 0.25


def register_season_parameter_routes(api_router, db, current_user, require_permission, log_audit):

    def _now():
        return datetime.now(timezone.utc).isoformat()

    @api_router.get("/season-parameters")
    async def list_season_params(season: Optional[int] = None, user=Depends(current_user)):
        q = {"is_active": {"$ne": False}}
        if season is not None:
            q["season"] = season
        return await db.season_parameters.find(q, {"_id": 0}).sort([("season", -1), ("crop", 1)]).to_list(500)

    @api_router.post("/season-parameters")
    async def upsert_season_param(body: SeasonParameterUpsert, request: Request,
                                  user=Depends(require_permission("contracts:create"))):
        """(sezon, ürün) çiftine göre upsert — aynı sezon+ürün için ikinci kayıt
        oluşmaz, mevcut güncellenir."""
        existing = await get_season_params(db, body.season, body.crop)
        payload = body.model_dump()
        if existing:
            await db.season_parameters.update_one(
                {"id": existing["id"]}, {"$set": {**payload, "updated_at": _now()}})
            new = await db.season_parameters.find_one({"id": existing["id"]}, {"_id": 0})
            await log_audit(db, user, action="update", entity="season_parameter",
                            entity_id=existing["id"], new_value=new, request=request)
            return new
        doc = {**payload, "id": str(uuid.uuid4()), "is_active": True, "created_at": _now()}
        await db.season_parameters.insert_one(dict(doc))
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="season_parameter",
                        entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.delete("/season-parameters/{param_id}")
    async def delete_season_param(param_id: str, request: Request,
                                  user=Depends(require_permission("contracts:create"))):
        res = await db.season_parameters.update_one({"id": param_id}, {"$set": {"is_active": False}})
        if res.matched_count == 0:
            raise HTTPException(404, "Parametre bulunamadı")
        await log_audit(db, user, action="delete", entity="season_parameter", entity_id=param_id, request=request)
        return {"status": "deactivated"}

    @api_router.post("/season-parameters/seed-defaults")
    async def seed_defaults(season: int, request: Request,
                            user=Depends(require_permission("contracts:create"))):
        """Verilen sezon için 'Şeker Pancarı' varsayılan parametrelerini oluşturur
        (idempotent — zaten varsa dokunmaz)."""
        existing = await get_season_params(db, season, "Şeker Pancarı")
        if existing:
            return {"status": "exists", "param": existing}
        doc = {"id": str(uuid.uuid4()), "season": season, "crop": "Şeker Pancarı",
               **DEFAULT_PANCAR, "is_active": True, "created_at": _now()}
        await db.season_parameters.insert_one(dict(doc))
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="season_parameter",
                        entity_id=doc["id"], new_value=doc, request=request)
        return {"status": "created", "param": doc}
