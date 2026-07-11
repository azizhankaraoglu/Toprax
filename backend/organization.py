"""
=====================================================================
TabSIS — Organizasyon Hiyerarşisi (IT-07b / FAZ 3 devam)
=====================================================================
ROADMAP: "Kullanıcılara sadece bir Role (yetki seti) değil, aynı zamanda
bir Organizasyon Pozisyonu atanmalı — kim kime bağlı, kim kimin onayını
alacak, hangi süreç kimden geçecek sistematik olarak tanımlanabilmeli."

Bu modül permissions.py'nin (RBAC — YETKİ) YERİNE geçmez, üstüne biner:
RBAC "ne yapabilirsin" sorusunu yanıtlar, Organizasyon Hiyerarşisi "kime
bağlısın / kim senin onayını verir" sorusunu yanıtlar. approval.py
(Onay Zinciri Motoru) "hiyerarşi bazlı" onay hedeflerini ÇÖZERKEN
BURADAKİ `get_manager_user_id()` fonksiyonunu çağırır — organization.py
onay mantığı BİLMEZ, sadece "kim kimin yöneticisi" verisini tutar
(bilinçli katman ayrımı, event_bus.py/automation.py emsaliyle tutarlı).

Veri modeli (ROADMAP'teki üç varlık, birebir):
- OrganizationUnit: id, name, parent_unit_id (nullable — hiyerarşik ağaç)
- Position: id, title, organization_unit_id, level (onay zincirinde
  KULLANILABİLECEK sayısal seviye — bu iterasyonda sadece bilgi amaçlı
  saklanır, approval.py şu an sadece "requester_manager" hedefini çözer;
  "level bazlı" hedef çözümleme ileride aynı fonksiyona eklenebilir).
- UserPosition: user_id, position_id, manager_user_id, start_date,
  end_date (nullable — DOLDURULMADAN kayıt SİLİNMEZ, geçmiş atamalar
  saklanır — convention: "migration'lar geriye uyumlu" ilkesiyle aynı
  ruh, burada "atama geçmişi asla silinmez" olarak uygulanır), is_primary.

Bir kullanıcının YÖNETİCİSİ değiştiğinde (yeni UserPosition kaydı açılıp
eskisi end_date ile kapatıldığında) o kullanıcının AÇACAĞI YENİ onay
gerektiren kayıtlar otomatik yeni yöneticiye gider — çünkü approval.py
her seferinde get_manager_user_id()'yi ANLIK çağırır, eski değeri
CACHE'LEMEZ (ROADMAP'in "org chart'taki yöneticisi değiştirildiğinde
yeni Destek Talebi otomatik yeni yöneticiye düşüyor" kabul kriteri budur).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List


class OrgUnitCreate(BaseModel):
    name: str
    parent_unit_id: Optional[str] = None


class OrgUnitUpdate(BaseModel):
    name: Optional[str] = None
    parent_unit_id: Optional[str] = None
    is_active: Optional[bool] = None


class PositionCreate(BaseModel):
    title: str
    organization_unit_id: str
    level: int = 0


class PositionUpdate(BaseModel):
    title: Optional[str] = None
    organization_unit_id: Optional[str] = None
    level: Optional[int] = None
    is_active: Optional[bool] = None


class UserPositionAssign(BaseModel):
    position_id: str
    manager_user_id: Optional[str] = None   # None = zincirin en tepesi (yöneticisi yok)
    is_primary: bool = True


# =====================================================================
# Diğer modüllerin (approval.py başta olmak üzere) çağırdığı yardımcılar
# =====================================================================
async def get_active_position(db, user_id: str) -> Optional[dict]:
    """Kullanıcının GÜNCEL (end_date=None) ataması — birden fazlaysa
    is_primary=True olanı öncelenir (ROADMAP: "biri birincil")."""
    return await db.user_positions.find_one(
        {"user_id": user_id, "end_date": None},
        {"_id": 0},
        sort=[("is_primary", -1), ("start_date", -1)],
    )


async def get_manager_user_id(db, user_id: str) -> Optional[str]:
    assignment = await get_active_position(db, user_id)
    return assignment.get("manager_user_id") if assignment else None


async def get_manager_chain(db, user_id: str, max_depth: int = 12) -> List[str]:
    """Kullanıcıdan yukarı doğru TÜM yönetici zinciri (döngü koruması ile).
    approval.py çok adımlı "sıradaki yöneticinin yöneticisi" gibi ileri
    seviye senaryolar için kullanabilir; bu iterasyonda approval.py sadece
    zincirin ilk halkasını (doğrudan yönetici) tüketir."""
    chain, current, seen = [], user_id, {user_id}
    for _ in range(max_depth):
        mgr = await get_manager_user_id(db, current)
        if not mgr or mgr in seen:
            break
        chain.append(mgr)
        seen.add(mgr)
        current = mgr
    return chain


async def get_direct_reports(db, manager_user_id: str) -> List[str]:
    """"Kendisine Bağlı Çalışanlar" — ROADMAP'in "ters ilişki, otomatik
    hesaplanır, ayrı alan tutulmaz" notu birebir: sorgu ile hesaplanır."""
    cursor = db.user_positions.find(
        {"manager_user_id": manager_user_id, "end_date": None}, {"_id": 0, "user_id": 1}
    )
    return [d["user_id"] async for d in cursor]


def register_organization_routes(api_router, db, current_user, require_permission, log_audit):

    # ---------------- Organization Units ----------------
    @api_router.get("/organization-units")
    async def list_org_units(user=Depends(require_permission("organization:view"))):
        return await db.organization_units.find({"is_active": {"$ne": False}}, {"_id": 0}).sort("name", 1).to_list(500)

    @api_router.post("/organization-units")
    async def create_org_unit(body: OrgUnitCreate, request: Request,
                               user=Depends(require_permission("organization:manage"))):
        doc = body.model_dump()
        doc.update({"id": str(uuid.uuid4()), "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat()})
        await db.organization_units.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="organization_unit", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/organization-units/{unit_id}")
    async def update_org_unit(unit_id: str, body: OrgUnitUpdate, request: Request,
                               user=Depends(require_permission("organization:manage"))):
        old = await db.organization_units.find_one({"id": unit_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Organizasyon birimi bulunamadı")
        if body.parent_unit_id == unit_id:
            raise HTTPException(400, "Bir birim kendi üst birimi olamaz")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.organization_units.update_one({"id": unit_id}, {"$set": updates})
        new = await db.organization_units.find_one({"id": unit_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="organization_unit", entity_id=unit_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/organization-units/{unit_id}")
    async def deactivate_org_unit(unit_id: str, request: Request,
                                   user=Depends(require_permission("organization:manage"))):
        old = await db.organization_units.find_one({"id": unit_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Organizasyon birimi bulunamadı")
        await db.organization_units.update_one({"id": unit_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="deactivate", entity="organization_unit", entity_id=unit_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # ---------------- Positions ----------------
    @api_router.get("/positions")
    async def list_positions(organization_unit_id: Optional[str] = None,
                              user=Depends(require_permission("organization:view"))):
        filt = {"is_active": {"$ne": False}}
        if organization_unit_id:
            filt["organization_unit_id"] = organization_unit_id
        return await db.positions.find(filt, {"_id": 0}).sort("title", 1).to_list(500)

    @api_router.post("/positions")
    async def create_position(body: PositionCreate, request: Request,
                               user=Depends(require_permission("organization:manage"))):
        unit = await db.organization_units.find_one({"id": body.organization_unit_id}, {"_id": 0})
        if not unit:
            raise HTTPException(404, "Organizasyon birimi bulunamadı")
        doc = body.model_dump()
        doc.update({"id": str(uuid.uuid4()), "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat()})
        await db.positions.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="position", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/positions/{position_id}")
    async def update_position(position_id: str, body: PositionUpdate, request: Request,
                               user=Depends(require_permission("organization:manage"))):
        old = await db.positions.find_one({"id": position_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Pozisyon bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.positions.update_one({"id": position_id}, {"$set": updates})
        new = await db.positions.find_one({"id": position_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="position", entity_id=position_id, old_value=old, new_value=new, request=request)
        return new

    # ---------------- User ↔ Position ataması ----------------
    @api_router.get("/users/{user_id}/position")
    async def get_user_position(user_id: str, user=Depends(require_permission("organization:view"))):
        current = await get_active_position(db, user_id)
        history = await db.user_positions.find({"user_id": user_id}, {"_id": 0}).sort("start_date", -1).to_list(50)
        direct_reports = await get_direct_reports(db, user_id)
        return {"current": current, "history": history, "direct_reports": direct_reports}

    @api_router.put("/users/{user_id}/position")
    async def assign_user_position(user_id: str, body: UserPositionAssign, request: Request,
                                    user=Depends(require_permission("organization:manage"))):
        target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not target_user:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        position = await db.positions.find_one({"id": body.position_id}, {"_id": 0})
        if not position:
            raise HTTPException(404, "Pozisyon bulunamadı")
        if body.manager_user_id == user_id:
            raise HTTPException(400, "Bir kullanıcı kendi yöneticisi olamaz")
        now = datetime.now(timezone.utc).isoformat()
        # Geçmiş atama SİLİNMEZ — sadece kapatılır (ROADMAP: "geçmiş atamalar saklanır").
        old_current = await get_active_position(db, user_id)
        if old_current:
            await db.user_positions.update_one({"id": old_current["id"]}, {"$set": {"end_date": now}})
        doc = {
            "id": str(uuid.uuid4()), "user_id": user_id, "position_id": body.position_id,
            "manager_user_id": body.manager_user_id, "is_primary": body.is_primary,
            "start_date": now, "end_date": None,
        }
        await db.user_positions.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="assign", entity="user_position", entity_id=doc["id"],
                         old_value=old_current, new_value=doc, request=request)
        return doc

    @api_router.get("/users/{user_id}/direct-reports")
    async def direct_reports(user_id: str, user=Depends(require_permission("organization:view"))):
        ids = await get_direct_reports(db, user_id)
        if not ids:
            return []
        return await db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1}).to_list(200)

    # ---------------- Org Chart (ağaç görselleştirme) ----------------
    @api_router.get("/org-chart")
    async def org_chart(user=Depends(require_permission("organization:view"))):
        units = await db.organization_units.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(500)
        positions = await db.positions.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(1000)
        assignments = await db.user_positions.find({"end_date": None}, {"_id": 0}).to_list(2000)
        user_ids = list({a["user_id"] for a in assignments})
        users_by_id = {}
        if user_ids:
            async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1}):
                users_by_id[u["id"]] = u

        positions_by_unit: dict = {}
        for p in positions:
            occupants = [
                {**users_by_id.get(a["user_id"], {"id": a["user_id"]}), "manager_user_id": a.get("manager_user_id"), "is_primary": a.get("is_primary")}
                for a in assignments if a["position_id"] == p["id"]
            ]
            positions_by_unit.setdefault(p["organization_unit_id"], []).append({**p, "occupants": occupants})

        nodes_by_id = {u["id"]: {**u, "positions": positions_by_unit.get(u["id"], []), "children": []} for u in units}
        roots = []
        for u in units:
            node = nodes_by_id[u["id"]]
            parent = u.get("parent_unit_id")
            if parent and parent in nodes_by_id:
                nodes_by_id[parent]["children"].append(node)
            else:
                roots.append(node)
        return {"tree": roots}
