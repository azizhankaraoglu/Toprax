"""setup_wizard.py -- PR-02: Web-Based Kurulum Sihirbazı (ince katman).

Onemli tasarim karari: bu modul YENI is mantigi YAZMAZ. Tenant olusturma
(tenants.py: POST /platform/tenants), ilk super admin atama (tenants.py:
POST /platform/tenants/{id}/bootstrap-admin), SMTP/entegrasyon ayari
(integrations.py: PUT /integrations/{itype}) ve lisans anahtari
(platform_core.py: POST /licenses) icin zaten calisan, yetkilendirilmis
uçlar var -- sihirbaz frontend'i (SetupWizard.jsx) bunlari SIRAYLA cagirir.

Bu modulun tek sorumlulugu: sihirbazin "tamamlandi mi" durumunu tutmak
(PR-02 kabul kriteri: "sihirbaz tamamlaninca kendini kilitler, tekrar
calistirilamaz").
"""
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from typing import Optional
from pydantic import BaseModel

SETUP_DOC_ID = "singleton"


class SetupCompleteBody(BaseModel):
    tenant_id: Optional[str] = None
    notes: Optional[str] = None


async def is_setup_completed(raw_db) -> bool:
    doc = await raw_db.platform_setup.find_one({"id": SETUP_DOC_ID})
    return bool(doc and doc.get("completed"))


def register_setup_wizard_routes(api_router, raw_db, current_user, log_audit):
    @api_router.get("/setup/status")
    async def setup_status():
        """Kimlik dogrulamasiz -- kurulum sihirbazi (frontend) ilk acilista
        bu ucu kontrol edip tamamlanmissa dogrudan /login'e yonlendirir."""
        doc = await raw_db.platform_setup.find_one({"id": SETUP_DOC_ID}, {"_id": 0})
        tenant_count = await raw_db.tenants.count_documents({})
        return {
            "completed": bool(doc and doc.get("completed")),
            "completed_at": (doc or {}).get("completed_at"),
            "tenant_count": tenant_count,
        }

    @api_router.post("/setup/complete")
    async def setup_complete(body: SetupCompleteBody, request: Request, user=Depends(current_user)):
        """Sihirbazi kilitler. platform_admin disinda kimse cagiramaz --
        bir kez tamamlandiktan sonra GET /setup/status hep completed=true
        doner, frontend /kurulum rotasini bir daha gostermez (self-lock)."""
        if user.get("role") != "platform_admin":
            raise HTTPException(403, "Bu işlem sadece platform yöneticileri içindir")

        existing = await raw_db.platform_setup.find_one({"id": SETUP_DOC_ID})
        if existing and existing.get("completed"):
            raise HTTPException(409, "Kurulum sihirbazı zaten tamamlanmış -- tekrar çalıştırılamaz")

        doc = {
            "id": SETUP_DOC_ID,
            "completed": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "completed_by": user.get("email"),
            "tenant_id": body.tenant_id,
            "notes": body.notes,
        }
        await raw_db.platform_setup.update_one({"id": SETUP_DOC_ID}, {"$set": doc}, upsert=True)
        await log_audit(raw_db, user, action="complete", entity="setup_wizard", entity_id=SETUP_DOC_ID,
                         new_value=doc, request=request)
        return {"status": "completed"}
