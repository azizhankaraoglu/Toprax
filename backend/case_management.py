"""
=====================================================================
Toprax — Inbound Case Yönetimi (IT-28 / FAZ 9 devam — Comm Hub üstü)
=====================================================================
ROADMAP: "'Destek Talebi' ile sınırlı kalınmaz, genel bir Konu (Case)
modeli kurulur — Destek Talebi, Şikayet, Öneri, Bilgi Talebi, Hastalık
Bildirimi, Zararlı İhbarı, Sulama Problemi, Fotoğraf Gönderimi, Evrak
Talebi gibi onlarca senaryoyu TEK modelde yönetir."

SupportRequest (support.py / IT-18) ile KARIŞTIRILMAMALI: SupportRequest
9 durumlu, KATI bir malzeme/nakit akışıdır (Ledger'a bağlanır). Case çok
daha genel, SERBEST biçimli bir "konu/talep" kaydıdır — durumları da
DALLANABİLİR (linear değil): İnceleniyor'dan hem "Bilgi Bekleniyor" hem
doğrudan "Cevaplandı"ya gidilebilir, "Cevaplandı"dan memnuniyetsizlik
halinde tekrar "İnceleniyor"a dönülebilir (ROADMAP'te bu geri dönüşler
açıkça yasaklanmamış, support.py'nin KATI SIRALI akışının aksine).

Saha Operasyonlarına köprü (create-task): field_ops.py'nin `IT-24` için
yazdığı `create_field_task_from_rule()` YARDIMCI fonksiyonu AYNEN
kullanılır — Case kendi Task oluşturma mantığını İCAT ETMEZ.

Kişi Kartı Entegrasyonu: communications.py'nin `/contacts/{id}/timeline`
ucu bu modülün case kayıtlarını da (iletişim kayıtlarıyla birlikte,
kronolojik) döndürecek şekilde AYRICA güncellendi (bkz. communications.py
içindeki "Case entegrasyonu" bloğu) — case_management.py bunun için
communications.py'yi import ETMEZ, tersine communications.py bu modülün
koleksiyonunu okur (tek yönlü bağımlılık, döngü yok).

Onay Zinciri (approval.py) entegrasyonu: "Case atama/devir" (process=
"case_assignment") onay motoruna KAYITLIDIR ama bu iterasyonda hiçbir
tenant'ta varsayılan bir kural TANIMLI DEĞİL — admin isterse Ayarlar'dan
bu süreç için bir onay kuralı tanımlayabilir (o zaman atama/devir önce
onaya düşer), tanımlamazsa atama doğrudan uygulanır (geriye uyumlu).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List

from event_bus import publish
from approval import maybe_start_approval

DEFAULT_CATEGORIES = [
    "Destek Başvurusu", "Hakediş", "Ödeme", "Sözleşme", "Üretim",
    "Hastalık Bildirimi", "Zararlı Bildirimi", "Sulama", "Gübreleme",
    "Teknik Destek", "Şikayet", "Öneri", "Bilgi Talebi", "Diğer",
]

# Doğrusal DEĞİL — dallanabilen bir durum grafiği (ROADMAP'in metni buna izin veriyor).
ALLOWED_TRANSITIONS = {
    "yeni": {"atandi", "iptal_edildi"},
    "atandi": {"inceleniyor", "iptal_edildi"},
    "inceleniyor": {"bilgi_bekleniyor", "cevaplandi", "iptal_edildi"},
    "bilgi_bekleniyor": {"cevaplandi", "inceleniyor", "iptal_edildi"},
    "cevaplandi": {"inceleniyor", "cozuldu", "iptal_edildi"},
    "cozuldu": {"kapatildi", "inceleniyor"},
    "kapatildi": set(),
    "iptal_edildi": set(),
}

STATUS_LABELS = {
    "yeni": "Yeni", "atandi": "Atandı", "inceleniyor": "İnceleniyor",
    "bilgi_bekleniyor": "Kullanıcıdan Bilgi Bekleniyor", "cevaplandi": "Cevaplandı",
    "cozuldu": "Çözüldü", "kapatildi": "Kapatıldı", "iptal_edildi": "İptal Edildi",
}


class CaseCategoryCreate(BaseModel):
    name: str


class CaseCreate(BaseModel):
    subject: str
    category_id: str
    description: Optional[str] = None
    priority: str = "orta"          # dusuk | orta | yuksek
    farmer_id: Optional[str] = None
    related_production_cycle_id: Optional[str] = None
    related_parcel_id: Optional[str] = None
    related_contract_id: Optional[str] = None
    related_support_request_id: Optional[str] = None
    attachments: List[str] = []


class CasePortalCreate(BaseModel):
    subject: str
    category_id: str
    description: Optional[str] = None
    related_production_cycle_id: Optional[str] = None
    related_parcel_id: Optional[str] = None
    attachments: List[str] = []


class CaseAssign(BaseModel):
    assigned_to: str
    note: Optional[str] = None


class CaseTransition(BaseModel):
    status: str
    reason: Optional[str] = None


class CaseMessageCreate(BaseModel):
    message: str
    attachments: List[str] = []


class CaseTaskCreate(BaseModel):
    task_type_id: str
    assigned_to: str
    priority: str = "normal"
    planned_date: Optional[str] = None


def register_case_routes(api_router, db, current_user, require_permission, log_audit):

    # ---------------- Kategori Yönetimi ----------------
    @api_router.get("/case-categories")
    async def list_categories(user=Depends(current_user)):
        return await db.case_categories.find({"is_active": {"$ne": False}}, {"_id": 0}).sort("name", 1).to_list(200)

    @api_router.post("/case-categories")
    async def create_category(body: CaseCategoryCreate, request: Request,
                               user=Depends(require_permission("cases:categories_manage"))):
        doc = {"id": str(uuid.uuid4()), "name": body.name, "is_active": True,
               "created_at": datetime.now(timezone.utc).isoformat()}
        await db.case_categories.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="case_category", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.post("/case-categories/seed-defaults")
    async def seed_categories(request: Request, user=Depends(require_permission("cases:categories_manage"))):
        created = []
        for name in DEFAULT_CATEGORIES:
            if await db.case_categories.find_one({"name": name}):
                continue
            doc = {"id": str(uuid.uuid4()), "name": name, "is_active": True,
                   "created_at": datetime.now(timezone.utc).isoformat()}
            await db.case_categories.insert_one(doc)
            created.append(name)
        return {"created": created}

    # ---------------- Case CRUD (dahili) ----------------
    @api_router.get("/cases")
    async def list_cases(
        status: Optional[str] = None, category_id: Optional[str] = None,
        assigned_to: Optional[str] = None, farmer_id: Optional[str] = None,
        user=Depends(require_permission("cases:view")),
    ):
        filt = {}
        if status: filt["status"] = status
        if category_id: filt["category_id"] = category_id
        if assigned_to: filt["assigned_to"] = assigned_to
        if farmer_id: filt["farmer_id"] = farmer_id
        return await db.cases.find(filt, {"_id": 0}).sort("created_at", -1).to_list(500)

    @api_router.get("/cases/{case_id}")
    async def get_case(case_id: str, user=Depends(require_permission("cases:view"))):
        doc = await db.cases.find_one({"id": case_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Case bulunamadı")
        return doc

    async def _create_case(body: dict, source_channel: str, created_by_user_id: Optional[str], farmer_id: Optional[str]) -> dict:
        category = await db.case_categories.find_one({"id": body["category_id"]}, {"_id": 0})
        if not category:
            raise HTTPException(404, "Kategori bulunamadı")
        now = datetime.now(timezone.utc).isoformat()
        doc = {**body, "id": str(uuid.uuid4()), "status": "yeni", "assigned_to": None,
               "source_channel": source_channel, "created_by_user_id": created_by_user_id,
               "farmer_id": farmer_id or body.get("farmer_id"),
               "created_at": now, "status_updated_at": now}
        await db.cases.insert_one(doc)
        doc.pop("_id", None)
        await publish(db, "case_created", {"case_id": doc["id"], "category_id": doc["category_id"], "farmer_id": doc.get("farmer_id")})
        return doc

    @api_router.post("/cases")
    async def create_case(body: CaseCreate, request: Request, user=Depends(require_permission("cases:create"))):
        doc = await _create_case(body.model_dump(), "dahili", user["id"], body.farmer_id)
        await log_audit(db, user, action="create", entity="case", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/cases/{case_id}/assign")
    async def assign_case(case_id: str, body: CaseAssign, request: Request,
                           user=Depends(require_permission("cases:manage"))):
        old = await db.cases.find_one({"id": case_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Case bulunamadı")
        target = await db.users.find_one({"id": body.assigned_to}, {"_id": 0})
        if not target:
            raise HTTPException(404, "Atanacak kullanıcı bulunamadı")

        # Onay Zinciri Motoru — SADECE process="case_assignment" için aktif bir
        # kural tanımlıysa devreye girer (bkz. modül docstring'i); yoksa doğrudan atanır.
        approval = await maybe_start_approval(
            db, process="case_assignment", entity_type="case", entity_id=case_id,
            requester_user_id=user["id"], context={"assigned_to": body.assigned_to},
        )
        if approval:
            return {"status": "onay_bekliyor", "approval_instance": approval}

        new_status = "atandi" if old["status"] == "yeni" else old["status"]
        await db.cases.update_one({"id": case_id}, {"$set": {
            "assigned_to": body.assigned_to, "status": new_status,
            "status_updated_at": datetime.now(timezone.utc).isoformat(),
        }})
        new = await db.cases.find_one({"id": case_id}, {"_id": 0})
        await log_audit(db, user, action="assign", entity="case", entity_id=case_id, old_value=old, new_value=new, request=request)
        await publish(db, "case_created", {"case_id": case_id, "assigned_to": body.assigned_to})
        return new

    @api_router.put("/cases/{case_id}/transition")
    async def transition_case(case_id: str, body: CaseTransition, request: Request,
                               user=Depends(require_permission("cases:manage"))):
        old = await db.cases.find_one({"id": case_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Case bulunamadı")
        current = old["status"]
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if body.status not in allowed:
            raise HTTPException(
                400,
                f"'{STATUS_LABELS.get(current, current)}' durumundan "
                f"'{STATUS_LABELS.get(body.status, body.status)}' durumuna geçilemez"
                + (f" (izin verilenler: {', '.join(STATUS_LABELS[s] for s in allowed)})" if allowed else " (bu durum terminaldir)"),
            )
        updates = {"status": body.status, "status_updated_at": datetime.now(timezone.utc).isoformat()}
        if body.status == "iptal_edildi" and body.reason:
            updates["close_reason"] = body.reason
        await db.cases.update_one({"id": case_id}, {"$set": updates})
        new = await db.cases.find_one({"id": case_id}, {"_id": 0})
        await log_audit(db, user, action="status_change", entity="case", entity_id=case_id,
                         old_value={"status": current}, new_value={"status": body.status}, request=request)
        return new

    # ---------------- Mesajlaşma (iki yönlü) ----------------
    @api_router.get("/cases/{case_id}/messages")
    async def list_messages(case_id: str, user=Depends(require_permission("cases:view"))):
        return await db.case_messages.find({"case_id": case_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)

    @api_router.post("/cases/{case_id}/messages")
    async def send_message(case_id: str, body: CaseMessageCreate, request: Request,
                            user=Depends(require_permission("cases:view"))):
        case = await db.cases.find_one({"id": case_id}, {"_id": 0})
        if not case:
            raise HTTPException(404, "Case bulunamadı")
        doc = {
            "id": str(uuid.uuid4()), "case_id": case_id, "sender_type": "user", "sender_id": user["id"],
            "sender_name": user.get("full_name") or user.get("email"), "message": body.message,
            "attachments": body.attachments, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.case_messages.insert_one(doc)
        doc.pop("_id", None)
        # Personel yanıtladığında durum otomatik "Cevaplandı"ya taşınır (İnceleniyor
        # veya Bilgi Bekleniyor'daysa) — ROADMAP'in "Cevaplandı" durumunun doğal tetikleyicisi.
        if case["status"] in ("inceleniyor", "bilgi_bekleniyor", "atandi"):
            await db.cases.update_one({"id": case_id}, {"$set": {
                "status": "cevaplandi", "status_updated_at": datetime.now(timezone.utc).isoformat()}})
        return doc

    # ---------------- Saha Operasyonlarına Köprü ----------------
    @api_router.post("/cases/{case_id}/create-task")
    async def create_task_from_case(case_id: str, body: CaseTaskCreate, request: Request,
                                     user=Depends(require_permission("cases:manage"))):
        case = await db.cases.find_one({"id": case_id}, {"_id": 0})
        if not case:
            raise HTTPException(404, "Case bulunamadı")
        from field_ops import create_field_task_from_rule
        task = await create_field_task_from_rule(
            db, task_type_id=body.task_type_id, assigned_to=body.assigned_to,
            farmer_id=case.get("farmer_id"), parcel_id=case.get("related_parcel_id"),
            production_cycle_id=case.get("related_production_cycle_id"),
            priority=body.priority, planned_date=body.planned_date,
            created_by=f"Case #{case_id[:8]} köprüsü ({user.get('full_name') or user.get('email')})",
        )
        if not task:
            raise HTTPException(400, "Görev tipi bulunamadı/pasif — görev oluşturulamadı")
        await db.cases.update_one({"id": case_id}, {"$set": {"bridged_task_id": task["id"]}})
        await log_audit(db, user, action="create-task", entity="case", entity_id=case_id, new_value={"task_id": task["id"]}, request=request)
        return task

    # ---------------- Çiftçi Portalı (iki yönlü — "Bize Ulaşın") ----------------
    @api_router.get("/portal/cases")
    async def portal_list_cases(user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        return await db.cases.find({"farmer_id": user["farmer_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/portal/cases")
    async def portal_create_case(body: CasePortalCreate, request: Request, user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi case açabilir")
        doc = await _create_case(body.model_dump(), "portal", None, user["farmer_id"])
        return doc

    @api_router.get("/portal/cases/{case_id}/messages")
    async def portal_list_messages(case_id: str, user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        case = await db.cases.find_one({"id": case_id, "farmer_id": user["farmer_id"]}, {"_id": 0})
        if not case:
            raise HTTPException(404, "Case bulunamadı")
        return await db.case_messages.find({"case_id": case_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)

    @api_router.post("/portal/cases/{case_id}/messages")
    async def portal_send_message(case_id: str, body: CaseMessageCreate, request: Request, user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi mesaj gönderebilir")
        case = await db.cases.find_one({"id": case_id, "farmer_id": user["farmer_id"]}, {"_id": 0})
        if not case:
            raise HTTPException(404, "Case bulunamadı")
        doc = {
            "id": str(uuid.uuid4()), "case_id": case_id, "sender_type": "farmer", "sender_id": user["farmer_id"],
            "sender_name": user.get("full_name") or "Çiftçi", "message": body.message,
            "attachments": body.attachments, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.case_messages.insert_one(doc)
        doc.pop("_id", None)
        # Çiftçi tekrar yazdığında (ör. "Cevaplandı" sonrası memnun değilse) case
        # otomatik "İnceleniyor"a döner — personelin dikkatine tekrar düşsün.
        if case["status"] == "cevaplandi":
            await db.cases.update_one({"id": case_id}, {"$set": {
                "status": "inceleniyor", "status_updated_at": datetime.now(timezone.utc).isoformat()}})
        return doc
