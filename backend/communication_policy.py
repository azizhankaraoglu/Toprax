"""
=====================================================================
Toprax — Communication Policy + Tercih Merkezi + Kara Liste
(IT-27 / FAZ 9 TAMAMLANDI — Communication Hub)
=====================================================================
`event_bus.py`'nin (IT-24'te temeli atıldı) üzerine kurulu, admin
tanımlı (kod gerektirmeyen) "olay → kanal(lar)" kuralları: bir
`CommunicationPolicy` event_type + kanal listesi + kanal başına şablon
taşır; ilgili event yayınlandığında (`publish()`) eşleşen TÜM aktif
politikalar `communications.send_via_channel()` ile GERÇEK bir gönderim
üretir — `automation.py`'nin (IT-24) kural motoruyla AYNI mimari desen
(event_bus dinler, DB'den kural okur, gerçek bir yan etki üretir).

**Olay → kişi çözümleme (EVENT_CONTACT_RESOLVERS):** her event_type'ın
payload'ında kimin (çiftçi mi personel mi, hangi alan) hedef olduğu
SABİT bir sözlükte tutulur — admin'in her politika için "bu event'te
kişi hangi alanda" diye elle seçmesi İSTENMEDİ (automation.py'nin basit
eşitlik koşulu kadar sade bir sadeleştirme): yeni bir comm-policy event'i
eklemek SADECE bu sözlüğe + `event_bus.EVENT_TYPES`'a birer satır demektir.

**Kara Liste + Tercih Merkezi'nin GERÇEK uygulaması `communications.py`
içindedir** (`_final_gate_check()`) — bu modül SADECE bu iki koleksiyonun
(`communication_blacklist`, `communication_preferences`) CRUD/self-servis
uçlarını sağlar; gönderim motorunun kendisi HER ZAMAN oradan geçtiği için
(elle gönderim / kampanya / policy — hepsi `send_via_channel()`'ı çağırır)
kara liste/tercih kontrolü BURADA TEKRAR YAZILMADI (tek gerçek kaynak).

Tercih Merkezi'nin çiftçi self-servisi `support.py`'nin `/portal/*` kalıbıyla
AYNI: `GET/PUT /portal/communication-preferences` (farmer_id token'dan gelir,
permission sistemine dahil değil — ciftci rolü zaten bu sisteme dahil değil,
bkz. permissions.py "ciftci": [] notu).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List

from event_bus import subscribe
from channel_providers import CHANNELS
from communications import send_via_channel

# event_type -> (contact_type, payload_field) — hangi olayda hedef kişi
# hangi alanda/tipte. Yeni bir comm-policy event'i eklemek SADECE burada
# ve event_bus.EVENT_TYPES'ta birer satır demektir.
EVENT_CONTACT_RESOLVERS = {
    "entitlement_created": ("farmer", "farmer_id"),
    "contract_approved": ("farmer", "farmer_id"),
    "task_assigned": ("personnel", "assigned_to"),
    # Remote Sensing anomali bildirimi — hedef, parselin çiftçisi (payload'da
    # farmer_id gelir). KONU 1.4: bu event için tanımlanan politikada
    # requires_approval=True ise önce Ziraat Mühendisi onayına düşer.
    "remote_sensing_anomaly_detected": ("farmer", "farmer_id"),
}

DEFAULT_CHANNELS_ENABLED = {k: True for k in CHANNELS}


class CommunicationPolicyCreate(BaseModel):
    name: str
    event_type: str
    channels: List[str]
    template_ids: Dict[str, str]
    # KONU 1.4 — onaylı/onaysız bildirim akışı: True ise bu olayın bildirimi
    # DOĞRUDAN gönderilmez, önce onay kuyruğuna (Seçenek A) düşer; yetkili
    # onaylayınca gönderilir. False (varsayılan) = doğrudan gönderim (Seçenek B).
    requires_approval: bool = False


class CommunicationPolicyUpdate(BaseModel):
    name: Optional[str] = None
    channels: Optional[List[str]] = None
    template_ids: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    requires_approval: Optional[bool] = None


class BlacklistCreate(BaseModel):
    contact_type: str
    contact_id: str
    reason: Optional[str] = None


class PreferenceUpdate(BaseModel):
    channels_enabled: Optional[Dict[str, bool]] = None
    allow_campaign_messages: Optional[bool] = None
    allow_operational_messages: Optional[bool] = None
    allow_weekend: Optional[bool] = None
    quiet_hours_start: Optional[str] = None   # "HH:MM" (UTC) — None ise sessiz saat yok
    quiet_hours_end: Optional[str] = None


async def _handle_policy_event(db, event_type: str, payload: dict) -> None:
    """`event_bus.subscribe()` ile EVENT_CONTACT_RESOLVERS'taki HER event_type'a
    bağlanan tek handler — hangi politikanın hangi event'e ait olduğu DB'den
    (communication_policies) okunur, event_bus.py kural bilmez (automation.py'nin
    `_handle_automation_event()` ile AYNI katman ayrımı)."""
    resolver = EVENT_CONTACT_RESOLVERS.get(event_type)
    if not resolver:
        return
    contact_type, field = resolver
    contact_id = payload.get(field)
    if not contact_id:
        return

    policies = await db.communication_policies.find(
        {"event_type": event_type, "is_active": True}, {"_id": 0},
    ).to_list(100)
    for policy in policies:
        # KONU 1.4 — Seçenek A (onaylı): doğrudan göndermek yerine onay kuyruğuna
        # düşür; yetkili `/communication-policies/pending-approvals/{id}/approve`
        # ile onaylayınca gerçek gönderim yapılır. Seçenek B (onaysız) = eski akış.
        if policy.get("requires_approval"):
            await db.pending_notifications.insert_one({
                "id": str(uuid.uuid4()), "policy_id": policy["id"], "policy_name": policy["name"],
                "event_type": event_type, "contact_type": contact_type, "contact_id": contact_id,
                "channels": policy["channels"], "template_ids": policy.get("template_ids") or {},
                "payload": {k: str(v) for k, v in payload.items()},
                "status": "onay_bekliyor", "created_at": datetime.now(timezone.utc).isoformat(),
            })
            continue
        for channel in policy["channels"]:
            template_id = (policy.get("template_ids") or {}).get(channel)
            if not template_id:
                continue   # bu kanal için şablon tanımlanmamış — politika o kanalı atlar
            await send_via_channel(
                db, channel=channel, contact_type=contact_type, contact_id=contact_id,
                template_id=template_id, variables={k: str(v) for k, v in payload.items()},
                sent_by=f"iletişim politikası: {policy['name']}", message_kind="operational",
            )


def register_communication_policy_routes(api_router, db, current_user, require_permission, log_audit):
    for event_type in EVENT_CONTACT_RESOLVERS:
        subscribe(event_type, _handle_policy_event)

    # =================================================================
    # COMMUNICATION POLICY
    # =================================================================
    @api_router.get("/communication-policies/event-types")
    async def list_policy_event_types(user=Depends(require_permission("communications:view"))):
        from event_bus import EVENT_TYPES
        return [{"key": k, "label": EVENT_TYPES.get(k, k)} for k in EVENT_CONTACT_RESOLVERS]

    @api_router.get("/communication-policies")
    async def list_policies(user=Depends(require_permission("communications:view"))):
        return await db.communication_policies.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/communication-policies")
    async def create_policy(body: CommunicationPolicyCreate, request: Request,
                             user=Depends(require_permission("communications:policies_manage"))):
        if body.event_type not in EVENT_CONTACT_RESOLVERS:
            raise HTTPException(400, f"Bilinmeyen/desteklenmeyen event_type: {body.event_type}")
        invalid_channels = [c for c in body.channels if c not in CHANNELS]
        if invalid_channels:
            raise HTTPException(400, f"Bilinmeyen kanal(lar): {invalid_channels}")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.communication_policies.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="communication_policy", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/communication-policies/{policy_id}")
    async def update_policy(policy_id: str, body: CommunicationPolicyUpdate, request: Request,
                             user=Depends(require_permission("communications:policies_manage"))):
        old = await db.communication_policies.find_one({"id": policy_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Politika bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "channels" in updates:
            invalid_channels = [c for c in updates["channels"] if c not in CHANNELS]
            if invalid_channels:
                raise HTTPException(400, f"Bilinmeyen kanal(lar): {invalid_channels}")
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.communication_policies.update_one({"id": policy_id}, {"$set": updates})
        new = await db.communication_policies.find_one({"id": policy_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="communication_policy", entity_id=policy_id, old_value=old, new_value=new, request=request)
        return new

    # =================================================================
    # KONU 1.4 — ONAY BEKLEYEN BİLDİRİMLER (Seçenek A akışı)
    # =================================================================
    @api_router.get("/communication-policies/pending-approvals")
    async def list_pending_notifications(user=Depends(require_permission("communications:view"))):
        return await db.pending_notifications.find(
            {"status": "onay_bekliyor"}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/communication-policies/pending-approvals/{item_id}/approve")
    async def approve_pending_notification(item_id: str, request: Request,
                                            user=Depends(require_permission("communications:policies_manage"))):
        item = await db.pending_notifications.find_one({"id": item_id}, {"_id": 0})
        if not item:
            raise HTTPException(404, "Onay bekleyen bildirim bulunamadı")
        if item["status"] != "onay_bekliyor":
            raise HTTPException(409, "Bu bildirim zaten işlenmiş")
        sent = 0
        for channel in item["channels"]:
            template_id = (item.get("template_ids") or {}).get(channel)
            if not template_id:
                continue
            await send_via_channel(
                db, channel=channel, contact_type=item["contact_type"], contact_id=item["contact_id"],
                template_id=template_id, variables=item.get("payload") or {},
                sent_by=f"onaylı bildirim: {item['policy_name']} ({user.get('email')})", message_kind="operational",
            )
            sent += 1
        await db.pending_notifications.update_one({"id": item_id}, {"$set": {
            "status": "onaylandi", "approved_by": user.get("email"),
            "approved_at": datetime.now(timezone.utc).isoformat(), "sent_channels": sent,
        }})
        await log_audit(db, user, action="approve", entity="pending_notification", entity_id=item_id,
                         new_value={"sent_channels": sent}, request=request)
        return {"status": "onaylandi", "sent_channels": sent}

    @api_router.post("/communication-policies/pending-approvals/{item_id}/reject")
    async def reject_pending_notification(item_id: str, request: Request,
                                           user=Depends(require_permission("communications:policies_manage"))):
        item = await db.pending_notifications.find_one({"id": item_id}, {"_id": 0})
        if not item:
            raise HTTPException(404, "Onay bekleyen bildirim bulunamadı")
        await db.pending_notifications.update_one({"id": item_id}, {"$set": {
            "status": "reddedildi", "approved_by": user.get("email"),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }})
        await log_audit(db, user, action="reject", entity="pending_notification", entity_id=item_id, request=request)
        return {"status": "reddedildi"}

    # =================================================================
    # KARA LİSTE (KVKK)
    # =================================================================
    @api_router.get("/communications/blacklist")
    async def list_blacklist(user=Depends(require_permission("communications:blacklist_manage"))):
        return await db.communication_blacklist.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

    @api_router.post("/communications/blacklist")
    async def add_to_blacklist(body: BlacklistCreate, request: Request,
                                user=Depends(require_permission("communications:blacklist_manage"))):
        existing = await db.communication_blacklist.find_one(
            {"contact_type": body.contact_type, "contact_id": body.contact_id}, {"_id": 0},
        )
        if existing:
            raise HTTPException(409, "Bu kişi zaten kara listede")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.communication_blacklist.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="communication_blacklist", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.delete("/communications/blacklist/{entry_id}")
    async def remove_from_blacklist(entry_id: str, request: Request,
                                     user=Depends(require_permission("communications:blacklist_manage"))):
        old = await db.communication_blacklist.find_one({"id": entry_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kayıt bulunamadı")
        await db.communication_blacklist.delete_one({"id": entry_id})
        await log_audit(db, user, action="delete", entity="communication_blacklist", entity_id=entry_id, old_value=old, request=request)
        return {"status": "deleted"}

    # =================================================================
    # TERCİH MERKEZİ — dahili/admin (staff bir çiftçi/personel adına yönetir)
    # =================================================================
    @api_router.get("/communications/preferences/{contact_type}/{contact_id}")
    async def get_preferences(contact_type: str, contact_id: str,
                               user=Depends(require_permission("communications:preferences_manage"))):
        pref = await db.communication_preferences.find_one(
            {"contact_type": contact_type, "contact_id": contact_id}, {"_id": 0},
        )
        return pref or {
            "contact_type": contact_type, "contact_id": contact_id,
            "channels_enabled": DEFAULT_CHANNELS_ENABLED, "allow_campaign_messages": True,
            "allow_operational_messages": True, "allow_weekend": True,
            "quiet_hours_start": None, "quiet_hours_end": None,
        }

    @api_router.put("/communications/preferences/{contact_type}/{contact_id}")
    async def set_preferences(contact_type: str, contact_id: str, body: PreferenceUpdate, request: Request,
                               user=Depends(require_permission("communications:preferences_manage"))):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        updates["contact_type"] = contact_type
        updates["contact_id"] = contact_id
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.communication_preferences.update_one(
            {"contact_type": contact_type, "contact_id": contact_id}, {"$set": updates}, upsert=True,
        )
        new = await db.communication_preferences.find_one(
            {"contact_type": contact_type, "contact_id": contact_id}, {"_id": 0},
        )
        await log_audit(db, user, action="update", entity="communication_preference",
                         entity_id=f"{contact_type}:{contact_id}", new_value=new, request=request)
        return new

    # =================================================================
    # TERCİH MERKEZİ — çiftçi self-servisi (/portal/*, support.py kalıbı)
    # =================================================================
    @api_router.get("/portal/communication-preferences")
    async def portal_get_preferences(user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        pref = await db.communication_preferences.find_one(
            {"contact_type": "farmer", "contact_id": user["farmer_id"]}, {"_id": 0},
        )
        return pref or {
            "contact_type": "farmer", "contact_id": user["farmer_id"],
            "channels_enabled": DEFAULT_CHANNELS_ENABLED, "allow_campaign_messages": True,
            "allow_operational_messages": True, "allow_weekend": True,
            "quiet_hours_start": None, "quiet_hours_end": None,
        }

    @api_router.put("/portal/communication-preferences")
    async def portal_set_preferences(body: PreferenceUpdate, request: Request, user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        updates["contact_type"] = "farmer"
        updates["contact_id"] = user["farmer_id"]
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.communication_preferences.update_one(
            {"contact_type": "farmer", "contact_id": user["farmer_id"]}, {"$set": updates}, upsert=True,
        )
        return await db.communication_preferences.find_one(
            {"contact_type": "farmer", "contact_id": user["farmer_id"]}, {"_id": 0},
        )
