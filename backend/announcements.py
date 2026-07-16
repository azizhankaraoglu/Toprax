"""
=====================================================================
Toprax — Duyurular (Announcements)
=====================================================================
Yöneticinin tüm kullanıcılara (personel + çiftçi) tek seferlik bir
mesaj yayınlayabilmesi için: kullanıcı giriş yaptığında (veya panele
girdiğinde) aktif/okunmamış duyurular bir popup ile gösterilir,
"Okudum" ile kapatılır ve bir daha o kullanıcıya gösterilmez —
ayrıca Bildirimler çekmecesindeki (WorkspaceDrawer.jsx) yeni
"Duyurular" sekmesinden geçmişe dönük tekrar okunabilir.

`notifications` koleksiyonuyla KARIŞTIRILMAMALI — o sistem
olay-tetiklemeli, tekil/otomatik kayıtlardır (bkz. support.py,
irrigation_events). Duyuru ise yönetici tarafından ELLE yazılan,
TÜM kullanıcılara yayılan, kişi başına okundu/okunmadı durumu tutan
ayrı bir kavramdır (`saved_queries.py`/`map_snapshots.py`'nin
"adlandırılmış, çoklu kayıt" ailesine yakın, ama okuma-takibi kendine
özgü — bu yüzden ayrı bir `announcement_reads` koleksiyonu).

Çiftçi erişimi: support.py/lms.py'nin `/portal/*` ayrımının AKSİNE,
duyuru HER ROL için aynı anlama geldiğinden (staff hem çiftçi) okuma
uçları permission İSTEMEZ — sadece `current_user` (giriş yapmış olmak)
yeterli. Sadece OLUŞTURMA/DÜZENLEME (`announcements:manage`) admin
katmanına kapalıdır (bkz. permissions.py).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    priority: str = "normal"   # normal | onemli | kritik


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    priority: Optional[str] = None
    is_active: Optional[bool] = None


PRIORITIES = {"normal", "onemli", "kritik"}


def register_announcement_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/announcements")
    async def list_announcements(user=Depends(require_permission("announcements:manage"))):
        """Yönetim ekranı — aktif + pasif TÜM duyurular (en yeni önce)."""
        return await db.announcements.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/announcements")
    async def create_announcement(body: AnnouncementCreate, request: Request,
                                   user=Depends(require_permission("announcements:manage"))):
        if body.priority not in PRIORITIES:
            raise HTTPException(400, f"Geçersiz öncelik: {body.priority}")
        doc = {
            "id": str(uuid.uuid4()),
            "title": body.title,
            "body": body.body,
            "priority": body.priority,
            "is_active": True,
            "created_by": user.get("full_name") or user.get("email"),
            "created_by_id": user["id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.announcements.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="announcement", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/announcements/{announcement_id}")
    async def update_announcement(announcement_id: str, body: AnnouncementUpdate, request: Request,
                                   user=Depends(require_permission("announcements:manage"))):
        old = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Duyuru bulunamadı")
        if body.priority is not None and body.priority not in PRIORITIES:
            raise HTTPException(400, f"Geçersiz öncelik: {body.priority}")
        changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
        if not changes:
            return old
        await db.announcements.update_one({"id": announcement_id}, {"$set": changes})
        new = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="announcement", entity_id=announcement_id,
                         old_value=old, new_value=new, request=request)
        return new

    @api_router.get("/announcements/active")
    async def list_active_announcements(unread_only: bool = True, user=Depends(current_user)):
        """Popup (unread_only=true, varsayılan) VE Duyurular sekmesi
        (unread_only=false, okundu/okunmadı rozetiyle TÜM aktif duyurular)
        AYNI uçtan beslenir — permission GEREKTİRMEZ, herkes (çiftçi dahil)
        kendi okuma durumunu görür."""
        active = await db.announcements.find({"is_active": True}, {"_id": 0}).sort("created_at", -1).to_list(100)
        read_ids = set(
            r["announcement_id"] for r in
            await db.announcement_reads.find({"user_id": user["id"]}, {"_id": 0, "announcement_id": 1}).to_list(1000)
        )
        for a in active:
            a["is_read"] = a["id"] in read_ids
        if unread_only:
            active = [a for a in active if not a["is_read"]]
        return active

    @api_router.get("/announcements/unread-count")
    async def announcements_unread_count(user=Depends(current_user)):
        active = await db.announcements.find({"is_active": True}, {"_id": 0, "id": 1}).to_list(100)
        if not active:
            return {"count": 0}
        read_ids = set(
            r["announcement_id"] for r in
            await db.announcement_reads.find({"user_id": user["id"]}, {"_id": 0, "announcement_id": 1}).to_list(1000)
        )
        count = sum(1 for a in active if a["id"] not in read_ids)
        return {"count": count}

    @api_router.post("/announcements/{announcement_id}/read")
    async def mark_announcement_read(announcement_id: str, user=Depends(current_user)):
        """İdempotent — aynı duyuru tekrar 'okundu' işaretlenirse kopya oluşmaz."""
        exists = await db.announcements.find_one({"id": announcement_id}, {"_id": 0, "id": 1})
        if not exists:
            raise HTTPException(404, "Duyuru bulunamadı")
        already = await db.announcement_reads.find_one({"announcement_id": announcement_id, "user_id": user["id"]})
        if already:
            return {"status": "already_read"}
        await db.announcement_reads.insert_one({
            "id": str(uuid.uuid4()),
            "announcement_id": announcement_id,
            "user_id": user["id"],
            "read_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "read"}
