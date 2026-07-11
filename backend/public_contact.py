"""public_contact.py -- Giris sayfasindaki (Login.jsx) 'Hesabiniz yok mu?
Talep olusturun' formu icin backend mantigi (2026-07-11).

Neden ayri bir modul: server.py'deki /public/contact-request route'u
KIMLIK DOGRULAMASI GEREKTIRMEZ (auth/login gibi bir "oncesi" endpoint'i).
Mantik burada testable/saf fonksiyonlara ayristirildi ki mongomock_motor
ile tek basina test edilebilsin -- server.py'yi ithal etmeden (bu
kod tabanindaki DIGER tum testler de AYNI yaklasimi kullaniyor, bkz.
tests/test_ledger_immutability.py, tests/test_api_keys.py).

Case Management'a (case_management.py / IT-28) yazar -- yeni bir "talep
kutusu" ICAT ETMEZ, mevcut Bize Ulasin ekraninda "Hesap / Giris Talebi"
kategorisiyle gorunur, admin/yonetici oradan devam eder.

Tenant cozumleme: cagiran (server.py) current_tenant_id'yi BU MODUL
CAGRILMADAN ONCE set etmis olmalidir (resolve_bootstrap_tenant ile
bulunan tenant'a) -- /admin/seed'deki AYNI "default tenant" kalibi.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

PUBLIC_CONTACT_CATEGORY_NAME = "Hesap / Giriş Talebi"


async def resolve_bootstrap_tenant(raw_db) -> dict:
    """Token yokken (current_tenant_id None) yazilacak tenant'i bulur --
    /admin/seed'deki ile AYNI 'default' kalibi: once slug="default" aranir,
    yoksa var olan herhangi bir tenant kullanilir (tek-tenant on-premise
    kurulumda -- dokumante edilen asil senaryo -- zaten tek tenant vardir).
    Hicbir tenant yoksa 503 firlatir (sistem henuz kurulmamis demektir)."""
    tenant = await raw_db.tenants.find_one({"slug": "default"}, {"_id": 0})
    if not tenant:
        tenant = await raw_db.tenants.find_one({}, {"_id": 0})
    if not tenant:
        raise HTTPException(503, "Sistem henüz kurulum aşamasında — lütfen kurulum sihirbazını tamamlayın")
    return tenant


async def create_public_contact_case(db, full_name: str, phone: Optional[str], email: Optional[str], message: str) -> dict:
    """Tenant baglami cagiran tarafindan ONCEDEN dogru set edilmis
    (TenantScopedDB) `db` ile cagrilir -- bu fonksiyon SADECE case/kategori
    yazma mantigini icerir, tenant cozumlemesiyle ilgilenmez (ayri sorumluluk,
    bkz. resolve_bootstrap_tenant) -- boylece mongomock ile tek basina
    test edilebilir.
    """
    category = await db.case_categories.find_one({"name": PUBLIC_CONTACT_CATEGORY_NAME}, {"_id": 0})
    if not category:
        category = {"id": str(uuid.uuid4()), "name": PUBLIC_CONTACT_CATEGORY_NAME}
        await db.case_categories.insert_one(dict(category))

    contact_line = f"İletişim: {phone or '—'} / {email or '—'}"
    now = datetime.now(timezone.utc).isoformat()
    case_doc = {
        "id": str(uuid.uuid4()),
        "subject": f"Web formu talebi — {full_name.strip()}",
        "category_id": category["id"],
        "description": f"{contact_line}\n\n{message.strip()}",
        "priority": "orta",
        "farmer_id": None,
        "related_production_cycle_id": None,
        "related_parcel_id": None,
        "related_contract_id": None,
        "related_support_request_id": None,
        "attachments": [],
        "status": "yeni",
        "assigned_to": None,
        "source_channel": "giris_sayfasi_web_formu",
        "created_by_user_id": None,
        "created_at": now,
        "status_updated_at": now,
    }
    await db.cases.insert_one(case_doc)
    case_doc.pop("_id", None)
    return case_doc
