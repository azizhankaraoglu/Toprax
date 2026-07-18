"""
=====================================================================
TOPRAX — Genel Kişi Grupları (B2 / #5)
=====================================================================
Bir grup, KARMA üyelik taşır: kooperatif personeli (`users.id`) VE/VEYA
çiftçiler (`farmers.id`). Böylece "Ziraat Mühendisleri", "Kuzucu Köyü
Çiftçileri", "Kriz Ekibi" gibi listeler tek bir yapıda tanımlanır.

Neden yeni bir koleksiyon: `lms_user_groups` SADECE LMS'e özeldi (yalnızca
users), kampanya segmentleri ise Query Engine filtreleridir (dinamik) —
ikisi de "adlandırılmış, karma, tekrar kullanılabilir dağıtım listesi"
ihtiyacını karşılamıyordu. Bu modül o boşluğu doldurur ve İKİ yerden
tüketilir:
  - #5 Communication Policy → anomali/olay bildirimlerinin çok-gruplu,
    çok-kanallı fan-out'u
  - #8 Form atama → forma grup hedefi

`resolve_group_recipients()` tüketicilerin çağırdığı TEK giriş noktasıdır;
`(contact_type, contact_id)` ikilileri döner — communications.py'nin
`send_via_channel()` imzasıyla birebir uyumlu.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    member_user_ids: List[str] = []
    member_farmer_ids: List[str] = []


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    member_user_ids: Optional[List[str]] = None
    member_farmer_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None


async def resolve_group_recipients(db, group_ids: List[str]) -> List[Tuple[str, str]]:
    """Grup id'lerini `(contact_type, contact_id)` alıcı ikililerine çevirir.
    Personel üyeler "personnel", çiftçi üyeler "farmer" olur. Pasif gruplar
    atlanır. Tüketiciler (policy fan-out, form atama) SADECE bunu çağırır."""
    if not group_ids:
        return []
    groups = await db.groups.find(
        {"id": {"$in": list(group_ids)}, "is_active": {"$ne": False}}, {"_id": 0}).to_list(500)
    out: List[Tuple[str, str]] = []
    for g in groups:
        for uid in (g.get("member_user_ids") or []):
            out.append(("personnel", uid))
        for fid in (g.get("member_farmer_ids") or []):
            out.append(("farmer", fid))
    return out


def register_group_routes(api_router, db, current_user, require_permission, log_audit):

    def _now():
        return datetime.now(timezone.utc).isoformat()

    @api_router.get("/groups")
    async def list_groups(user=Depends(current_user)):
        """Okuma herkese açık (giriş yapmış) — form atama/politika ekranları
        grup listesini görebilmeli. Üye listeleri kişisel veri içermez (sadece id)."""
        return await db.groups.find({"is_active": {"$ne": False}}, {"_id": 0}).sort("name", 1).to_list(500)

    @api_router.post("/groups")
    async def create_group(body: GroupCreate, request: Request,
                           user=Depends(require_permission("communications:policies_manage"))):
        doc = body.model_dump()
        doc.update({"id": str(uuid.uuid4()), "is_active": True, "created_at": _now(),
                    "created_by": user.get("full_name") or user.get("email")})
        await db.groups.insert_one(dict(doc))
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="group", entity_id=doc["id"],
                        new_value={"name": doc["name"]}, request=request)
        return doc

    @api_router.put("/groups/{group_id}")
    async def update_group(group_id: str, body: GroupUpdate, request: Request,
                           user=Depends(require_permission("communications:policies_manage"))):
        old = await db.groups.find_one({"id": group_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Grup bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.groups.update_one({"id": group_id}, {"$set": {**updates, "updated_at": _now()}})
        new = await db.groups.find_one({"id": group_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="group", entity_id=group_id,
                        old_value={"name": old.get("name")}, new_value=updates, request=request)
        return new

    @api_router.delete("/groups/{group_id}")
    async def delete_group(group_id: str, request: Request,
                           user=Depends(require_permission("communications:policies_manage"))):
        res = await db.groups.update_one({"id": group_id}, {"$set": {"is_active": False}})
        if res.matched_count == 0:
            raise HTTPException(404, "Grup bulunamadı")
        await log_audit(db, user, action="delete", entity="group", entity_id=group_id, request=request)
        return {"status": "deactivated"}

    @api_router.get("/groups/{group_id}/members")
    async def group_members(group_id: str, user=Depends(current_user)):
        """Üyeleri ADLARIYLA döner (yönetim ekranı için)."""
        g = await db.groups.find_one({"id": group_id}, {"_id": 0})
        if not g:
            raise HTTPException(404, "Grup bulunamadı")
        users = await db.users.find({"id": {"$in": g.get("member_user_ids") or []}},
                                    {"_id": 0, "password": 0, "totp_secret": 0}).to_list(500)
        farmers = await db.farmers.find({"id": {"$in": g.get("member_farmer_ids") or []}},
                                        {"_id": 0, "id": 1, "full_name": 1, "member_no": 1, "village": 1}).to_list(500)
        return {"group": g, "users": users, "farmers": farmers}
