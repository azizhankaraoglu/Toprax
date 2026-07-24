"""
=====================================================================
Toprax — MERNİS / TAKBİS Uçları (Denetim Faz 3)
=====================================================================
`gov_providers.py`'nin ürettiği sonuçları HTTP'ye bağlar. İki uç:
  POST /gov/mernis/verify   — TC kimlik doğrulama (Farmer.mernis_verified'ı günceller)
  POST /gov/takbis/query    — ada/parsel → tapu bilgisi (yalnızca DÖNER, PUT
                               /parcels/{id} ile kaydetme çağıranın işidir —
                               geo_import.py'nin "sadece ayrıştırır, kaydetmez"
                               felsefesiyle AYNI ayrım).
"""
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from gov_providers import get_identity_provider, get_cadastre_provider


class MernisVerifyRequest(BaseModel):
    tc_no: str
    ad: str
    soyad: str
    dogum_yili: int
    farmer_id: Optional[str] = None  # verilirse başarılı doğrulama Farmer kaydına yazılır


class TakbisQueryRequest(BaseModel):
    il: str
    ilce: str
    ada: str
    parsel: str


def register_gov_routes(api_router, db, current_user, require_permission, require_feature, log_audit):

    @api_router.post("/gov/mernis/verify")
    async def mernis_verify(body: MernisVerifyRequest, request: Request,
                             user=Depends(require_permission("farmers:edit")),
                             _feat=Depends(require_feature("mernis"))):
        provider = await get_identity_provider(db)
        result = provider.verify(body.tc_no, body.ad, body.soyad, body.dogum_yili)

        if result["verified"] and body.farmer_id:
            now = datetime.now(timezone.utc).isoformat()
            farmer = await db.farmers.find_one({"id": body.farmer_id}, {"_id": 0})
            if not farmer:
                raise HTTPException(404, "Çiftçi bulunamadı")
            await db.farmers.update_one(
                {"id": body.farmer_id},
                {"$set": {"mernis_verified": True, "mernis_verified_at": now}},
            )
            await log_audit(db, user, action="mernis_verify", entity="farmer", entity_id=body.farmer_id,
                             old_value={"mernis_verified": farmer.get("mernis_verified", False)},
                             new_value={"mernis_verified": True, "mernis_verified_at": now},
                             request=request)

        return result

    @api_router.post("/gov/takbis/query")
    async def takbis_query(body: TakbisQueryRequest,
                            user=Depends(require_permission("parcels:edit")),
                            _feat=Depends(require_feature("takbis"))):
        provider = await get_cadastre_provider(db)
        return provider.query(body.il, body.ilce, body.ada, body.parsel)
