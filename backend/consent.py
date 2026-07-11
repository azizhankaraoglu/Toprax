"""consent.py -- PR-15: KVKK Aciк Riza Kayit Mekanizmasi (genel amacli).

docs/legal/KVKK-AYDINLATMA-METNI.md'nin Bolum 6'sinda ("Acik Riza
Gerektiren Islemler") atifta bulunulan kayit mekanizmasi. Her modul
(pazarlama SMS'i, kampanya vb.) kendi riza mantigini YAZMAZ -- bu
generic uc kullanilir (CLAUDE.md #3.4 'tek mekanizma' prensibiyle ayni
ruh: onay zinciri nasil tek merkezi bir motorsa, riza kaydi da oyle).

Geri alinabilirlik: bir riza kaydi FIZIKSEL SILINMEZ (KVKK m.11 kapsaminda
"ne zaman/nasil riza verildigi" ispat yukumlulugu icin) -- yeni bir kayitla
(granted=False) GERI ALINIR, tarihce korunur (ledger.py'deki 'silinmezlik'
prensibiyle ayni desen).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Request
from pydantic import BaseModel


class ConsentRecord(BaseModel):
    subject_type: str          # "farmer" | "user" | "contact" ...
    subject_id: str
    consent_type: str          # "marketing_sms" | "marketing_email" | "data_processing" ...
    granted: bool
    text_version: str = "v1"   # docs/legal/KVKK-AYDINLATMA-METNI.md'nin hangi sürümü gösterildi


def register_consent_routes(api_router, db, current_user, log_audit):
    @api_router.post("/consent")
    async def record_consent(body: ConsentRecord, request: Request, user=Depends(current_user)):
        doc = {
            "id": str(uuid.uuid4()),
            "subject_type": body.subject_type,
            "subject_id": body.subject_id,
            "consent_type": body.consent_type,
            "granted": body.granted,
            "text_version": body.text_version,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "recorded_by": user.get("email"),
            "ip_address": request.client.host if request.client else None,
        }
        await db.consent_records.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="record", entity="consent", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.get("/consent/{subject_type}/{subject_id}")
    async def get_consent_history(subject_type: str, subject_id: str, user=Depends(current_user)):
        """En güncel durumu (her consent_type için son kayıt) + tam tarihçeyi döner."""
        history = await db.consent_records.find(
            {"subject_type": subject_type, "subject_id": subject_id}, {"_id": 0}
        ).sort("recorded_at", -1).to_list(500)
        current = {}
        for rec in history:
            current.setdefault(rec["consent_type"], rec)
        return {"current": current, "history": history}
