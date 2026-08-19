"""
TOPRAX — Güneş/Gölge HTTP yüzeyi (CLAUDE.md konvansiyon #1).

İş mantığı `solar.py`'de; bu dosya SADECE route kaydı yapar (gee_hls'in
service/routes ayrımıyla AYNI disiplin).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request

from .solar import analyze_parcel_solar, CROP_SUN_REQUIREMENT_HOURS


def register_solar_routes(api_router, db, current_user, require_permission,
                          log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/solar/parcels/{parcel_id}")
    async def parcel_solar(parcel_id: str, crop: str = "pancar", tarih: Optional[str] = None,
                           yenile: bool = False,
                           user=Depends(require_permission("parcels:view"))):
        """Parselin güneşlenme/gölge profili.

        Kayıtlı analiz varsa ONDAN döner (`yenile=true` ile zorlanır) —
        Earth Engine çağrısı kotalıdır ve arazi (eğim/bakı) yıllar içinde
        değişmez; her ekran açılışında yeniden hesaplamak anlamsız olurdu.
        """
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        saved = parcel.get("solar")
        if saved and saved.get("available") and not yenile and not tarih:
            return {**saved, "onbellekten": True}

        result = await analyze_parcel_solar(db, parcel, crop, tarih)
        if result.get("available"):
            await db.parcels.update_one({"id": parcel_id}, {"$set": {
                "solar": {**result, "hesaplandi": datetime.now(timezone.utc).isoformat()}}})
        return result

    @api_router.get("/solar/requirements")
    async def sun_requirements(user=Depends(current_user)):
        """Ürün bazlı günlük güneşlenme ihtiyacı — ekran hardcode etmez."""
        return {"gereksinimler": CROP_SUN_REQUIREMENT_HOURS}
