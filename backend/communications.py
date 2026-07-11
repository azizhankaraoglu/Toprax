"""
=====================================================================
TabSIS — Communication Hub: Kanallar + Şablon Yönetimi + Gönderim +
Kişi Kartı İletişim Timeline'ı (IT-25 / FAZ 9 — Sprint 9 başlangıç)
=====================================================================
Stratejik mimari not (ROADMAP): Comm Hub sadece mesaj gönderen bir
servis değil, TabSİS içindeki iş olaylarını dinleyip doğru kişiye doğru
zamanda doğru kanaldan ileten merkezi bir hub olacak. IT-25 SADECE elle
tetiklenen (kişi kartından "Gönder" butonu) gönderim akışını + şablon
yönetimini + timeline'ı kurmuştu; event bus'a (`event_bus.py`) gerçek
olay-tetiklemeli bağlanma `communication_policy.py`'de (IT-27) eklendi —
o modül de gönderim için BURADAKİ `send_via_channel()`'ı çağırır, DUPLİKE
bir gönderim mantığı YOK. `support.py`'nin basit `notifications` insert'i
(in-app bildirim) bu modülle KARIŞTIRILMAMALI — AYRI/önceki bir kalıp,
dokunulmadı.

**(IT-27) Kara Liste + Tercih Merkezi — gönderim motorunun EN SON adımı:**
`send_via_channel()` içindeki `_final_gate_check()` — sağlayıcı ÇAĞRILMADAN
HEMEN ÖNCE çalışır, `communication_policy.py`'nin Communication Policy'si
(otomatik, olay tetiklemeli) tetiklese BİLE kara listedeki/tercihi kapalı
bir kişiye mesaj GİTMEZ (ROADMAP'in "bu kontrol gönderim motorunun en son
adımında zorunlu olmalı" kararı BİREBİR). `message_kind` ("operational" |
"campaign") — kişi kartından elle gönderim VE policy tetiklemeli gönderim
"operational" sayılır, `campaigns.py`'nin (IT-26) toplu gönderimi
"campaign" geçer; Tercih Merkezi'nin kampanya/operasyonel ayrımı buradan
çözülür.

Kanallar: `channel_providers.py`'deki `ChannelProvider` soyutlaması —
ilk fazda TÜMÜ simüle (bkz. o dosyanın docstring'i).

Şablon versiyonlama: `templates` koleksiyonundaki doküman HER ZAMAN
güncel sürümü tutar (`version` int); `subject`/`body` değişen her
PUT'tan ÖNCE eski hali `template_versions`'a bir anlık görüntü olarak
yazılır — event sourcing DEĞİL, basit "önceki sürümü sakla" (production_
cycles.py'nin durum makinesi kadar karmaşık bir versiyon zinciri
gerekmiyor, sadece "hangi sürüm ne zamandı" sorusuna cevap verir).

Değişken render'ı BİLİNÇLİ OLARAK basit `{{Ad}}` -> değer string
replace'i — entitlement.py'nin `formul` kesintisi gibi bir mini-DSL
İSTENMEDİ, ROADMAP'in listelediği 6 değişken (FarmerName/
ProductionSeason/ParcelNo/SupportType/HarvestDate/PaymentAmount) sabit
bir küme, koşullu mantık/döngü gerekmiyor. `FarmerName` kişi
kaydından (contact) OTOMATİK doldurulur, diğerleri çağıran tarafın
(frontend) context'ten (üretim sezonu/parsel/destek talebi ekranı)
gönderdiği `variables` sözlüğünden gelir.
"""
import re
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict

from channel_providers import CHANNELS, get_channel_provider

TEMPLATE_VARIABLES = [
    "FarmerName", "ProductionSeason", "ParcelNo",
    "SupportType", "HarvestDate", "PaymentAmount",
]

VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _render(text: Optional[str], variables: Dict[str, str]) -> Optional[str]:
    if not text:
        return text
    return VAR_PATTERN.sub(lambda m: str(variables.get(m.group(1), m.group(0))), text)


class TemplateCreate(BaseModel):
    name: str
    channel: str
    subject: Optional[str] = None
    body: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_active: Optional[bool] = None


class CommunicationSendRequest(BaseModel):
    channel: str
    contact_type: str                          # "farmer" | "personnel"
    contact_id: str
    template_id: Optional[str] = None
    variables: Dict[str, str] = {}
    content: Optional[str] = None               # template_id verilmezse zorunlu (serbest metin)
    subject: Optional[str] = None
    recipient_override: Optional[str] = None    # kayıttaki adres/numara yerine elle girilen hedef


async def _resolve_contact(db, contact_type: str, contact_id: str) -> dict:
    if contact_type == "farmer":
        doc = await db.farmers.find_one({"id": contact_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Çiftçi bulunamadı")
    elif contact_type == "personnel":
        doc = await db.users.find_one({"id": contact_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Personel bulunamadı")
    else:
        raise HTTPException(400, "Geçersiz contact_type (farmer | personnel)")
    return {"name": doc.get("full_name"), "phone": doc.get("phone"), "email": doc.get("email")}


def _recipient_for_channel(channel: str, contact: dict) -> Optional[str]:
    if channel in ("sms", "whatsapp", "voice"):
        return contact.get("phone")
    if channel == "email":
        return contact.get("email")
    if channel == "push":
        # Push simülasyonda gerçek cihaz token'ı yok — kişinin kendisi hedef kabul edilir.
        return contact.get("name")
    return None


async def _final_gate_check(db, contact_type: str, contact_id: str, channel: str, message_kind: str) -> Optional[str]:
    """
    Kara Liste + Tercih Merkezi kontrolü (IT-27) — `send_via_channel()`nin
    sağlayıcıyı ÇAĞIRMADAN HEMEN ÖNCEKİ son adımı. Engellenirse KISA bir
    Türkçe blok sebebi döner (bu, `communications.provider_detail`'e
    doğrudan yazılır), engel yoksa None. Kara liste HER ZAMAN kazanır —
    Communication Policy (IT-27) tetiklese, hatta kişinin kendi tercihi
    o kanalı açık bıraksa bile, kara listedeyse mesaj gitmez.
    """
    # IT-33 — Feature Flag kontrolü de AYNI "son adım" felsefesiyle burada:
    # WhatsApp'ın kendi URL'i/route'u olmadığından (kanal seçimi body
    # parametresiyle yapılır) platform_core.py'nin URL-prefix bazlı
    # require_feature'ı burada işe yaramaz — kanal bazlı kontrol gerekir.
    if channel == "whatsapp":
        from platform_core import is_feature_enabled
        if not await is_feature_enabled(db, "whatsapp"):
            return "'WhatsApp Kanalı' özelliği bu kurum için kapatılmış"

    blacklisted = await db.communication_blacklist.find_one(
        {"contact_type": contact_type, "contact_id": contact_id}, {"_id": 0},
    )
    if blacklisted:
        return "Kara listede — gönderim engellendi (KVKK)"

    pref = await db.communication_preferences.find_one(
        {"contact_type": contact_type, "contact_id": contact_id}, {"_id": 0},
    )
    if not pref:
        return None
    if not (pref.get("channels_enabled") or {}).get(channel, True):
        return f"Tercih: '{CHANNELS.get(channel, channel)}' kanalı kişi tarafından kapatılmış"
    if message_kind == "campaign" and not pref.get("allow_campaign_messages", True):
        return "Tercih: kampanya mesajları kişi tarafından kapatılmış"
    if message_kind == "operational" and not pref.get("allow_operational_messages", True):
        return "Tercih: operasyonel bildirimler kişi tarafından kapatılmış"
    if not pref.get("allow_weekend", True) and datetime.now(timezone.utc).weekday() >= 5:
        return "Tercih: hafta sonu iletişim kişi tarafından kapatılmış"
    quiet_start, quiet_end = pref.get("quiet_hours_start"), pref.get("quiet_hours_end")
    if quiet_start and quiet_end:
        now_hm = datetime.now(timezone.utc).strftime("%H:%M")
        # quiet_start < quiet_end ise gün-içi aralık; DEĞİLSE (ör. 22:00-07:00)
        # gece yarısını aşan aralık — iki durumu da doğru kapsar.
        in_quiet_hours = (quiet_start <= now_hm < quiet_end) if quiet_start < quiet_end else (now_hm >= quiet_start or now_hm < quiet_end)
        if in_quiet_hours:
            return "Tercih: sessiz saatler içinde"
    return None


async def send_via_channel(
    db, *, channel: str, contact_type: str, contact_id: str,
    template_id: Optional[str] = None, variables: Optional[Dict[str, str]] = None,
    content: Optional[str] = None, subject: Optional[str] = None,
    recipient_override: Optional[str] = None, sent_by: str, campaign_id: Optional[str] = None,
    message_kind: str = "operational",
) -> tuple:
    """
    Gerçek gönderim çekirdeği — hem `POST /communications/send` (tek kişi,
    kişi kartından) hem de `campaigns.py`'nin (IT-26) retry/fallback
    zinciri BURADAN çağırır (query_engine.execute_query()'nin hem
    `POST /query/{module}` hem AI Copilot'tan çağrılmasıyla AYNI desen —
    "çekirdek fonksiyon dışa açık, route ince bir sarmalayıcı"). HTTPException
    SADECE girdi hatalarında (bilinmeyen kanal/şablon bulunamadı/içerik yok)
    fırlatılır — sağlayıcı başarısızlığı (ör. alıcı adresi eksik) exception
    DEĞİLDİR, `(doc, ok)` ile döner; kampanya zinciri bunu yakalayıp bir
    sonraki kanalı dener.

    `(doc, ok)` döner — `doc` HER durumda (başarılı/başarısız) `communications`
    koleksiyonuna yazılmış timeline kaydıdır.
    """
    if channel not in CHANNELS:
        raise HTTPException(400, f"Bilinmeyen kanal: {channel}")

    contact = await _resolve_contact(db, contact_type, contact_id)

    template = None
    if template_id:
        template = await db.templates.find_one({"id": template_id}, {"_id": 0})
        if not template or not template.get("is_active", True):
            raise HTTPException(404, "Şablon bulunamadı veya pasif")
        if template["channel"] != channel:
            raise HTTPException(400, "Şablon bu kanal için tanımlı değil")

    merged_variables = {"FarmerName": contact.get("name") or "", **(variables or {})}
    rendered_subject = _render(template["subject"] if template else subject, merged_variables)
    rendered_content = _render(template["body"] if template else content, merged_variables)
    if not rendered_content:
        raise HTTPException(400, "Gönderilecek içerik yok (template_id veya content gerekli)")

    recipient = recipient_override or _recipient_for_channel(channel, contact)

    # (IT-27) Kara Liste + Tercih Merkezi — sağlayıcı ÇAĞRILMADAN ÖNCE son
    # gate. Engellenirse sağlayıcıya HİÇ gidilmez (kara listedeki birine
    # simüle sağlayıcı bile "gönderim" YAPMAMALI — gerçek bir SMS/e-posta
    # entegrasyonunda bu davranış BİREBİR aynı olacak).
    block_reason = await _final_gate_check(db, contact_type, contact_id, channel, message_kind)
    if block_reason:
        ok, status, detail, provider_ref = False, "basarisiz", block_reason, None
    else:
        result = get_channel_provider(channel).send(recipient, rendered_content, rendered_subject)
        ok = result["ok"]
        status = result["status"] if ok else "basarisiz"
        detail = result["detail"]
        provider_ref = result.get("provider_ref")

    doc = {
        "id": str(uuid.uuid4()),
        "channel": channel,
        "contact_type": contact_type,
        "contact_id": contact_id,
        "recipient": recipient,
        "template_id": template_id,
        "template_name": template["name"] if template else None,
        "subject": rendered_subject,
        "content": rendered_content,
        "status": status,
        "provider_detail": detail,
        "provider_ref": provider_ref,
        "message_kind": message_kind,
        "campaign_id": campaign_id,
        "sent_by": sent_by,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.communications.insert_one(doc)
    doc.pop("_id", None)
    return doc, ok


def register_communication_routes(api_router, db, current_user, require_permission, log_audit):

    # =================================================================
    # KANALLAR
    # =================================================================
    @api_router.get("/channels")
    async def list_channels(user=Depends(require_permission("communications:view"))):
        return [{"key": k, "label": v} for k, v in CHANNELS.items()]

    # =================================================================
    # ŞABLON YÖNETİMİ
    # =================================================================
    @api_router.get("/templates/variables")
    async def list_template_variables(user=Depends(require_permission("communications:view"))):
        return TEMPLATE_VARIABLES

    @api_router.get("/templates")
    async def list_templates(
        channel: Optional[str] = None, include_inactive: bool = False,
        user=Depends(require_permission("communications:view")),
    ):
        filt = {}
        if channel:
            filt["channel"] = channel
        if not include_inactive:
            filt["is_active"] = True
        return await db.templates.find(filt, {"_id": 0}).sort("name", 1).to_list(300)

    @api_router.get("/templates/{template_id}/versions")
    async def list_template_versions(template_id: str, user=Depends(require_permission("communications:view"))):
        return await db.template_versions.find({"template_id": template_id}, {"_id": 0}).sort("version", -1).to_list(100)

    @api_router.post("/templates")
    async def create_template(
        body: TemplateCreate, request: Request,
        user=Depends(require_permission("communications:templates_manage")),
    ):
        if body.channel not in CHANNELS:
            raise HTTPException(400, f"Bilinmeyen kanal: {body.channel}")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["version"] = 1
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.templates.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="template", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/templates/{template_id}")
    async def update_template(
        template_id: str, body: TemplateUpdate, request: Request,
        user=Depends(require_permission("communications:templates_manage")),
    ):
        old = await db.templates.find_one({"id": template_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Şablon bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")

        if "subject" in updates or "body" in updates:
            await db.template_versions.insert_one({
                "id": str(uuid.uuid4()), "template_id": template_id, "version": old["version"],
                "name": old["name"], "subject": old.get("subject"), "body": old["body"],
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "archived_by": user.get("full_name") or user.get("email"),
            })
            updates["version"] = old["version"] + 1

        await db.templates.update_one({"id": template_id}, {"$set": updates})
        new = await db.templates.find_one({"id": template_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="template", entity_id=template_id, old_value=old, new_value=new, request=request)
        return new

    # =================================================================
    # GÖNDERİM
    # =================================================================
    @api_router.post("/communications/send")
    async def send_communication(
        body: CommunicationSendRequest, request: Request,
        user=Depends(require_permission("communications:send")),
    ):
        doc, ok = await send_via_channel(
            db, channel=body.channel, contact_type=body.contact_type, contact_id=body.contact_id,
            template_id=body.template_id, variables=body.variables, content=body.content, subject=body.subject,
            recipient_override=body.recipient_override, sent_by=user.get("full_name") or user.get("email"),
        )
        await log_audit(db, user, action="send", entity="communication", entity_id=doc["id"], new_value=doc, request=request)
        if not ok:
            raise HTTPException(422, doc["provider_detail"])
        return doc

    # =================================================================
    # KİŞİ KARTI İLETİŞİM TIMELINE'I
    # =================================================================
    @api_router.get("/contacts/{contact_id}/timeline")
    async def contact_timeline(
        contact_id: str, contact_type: str = "farmer",
        user=Depends(require_permission("communications:view")),
    ):
        comms = await db.communications.find(
            {"contact_id": contact_id, "contact_type": contact_type}, {"_id": 0}
        ).sort("sent_at", -1).to_list(300)
        for c in comms:
            c["kind"] = "communication"
            c["timeline_at"] = c.get("sent_at")

        # (IT-28) Case kayıtları da AYNI timeline'da, kronolojik karışık görünür
        # (ROADMAP kabul kriteri: "case kişi kartı timeline'ında diğer iletişim
        # kayıtlarıyla birlikte kronolojik görünüyor") — SADECE contact_type=
        # "farmer" için (Case modelinde şu an farmer_id alanı var, personel
        # case'i henüz yok), communications koleksiyonuna YAZILMAZ (ayrı
        # koleksiyon kalır, burada sadece OKUMA sırasında birleştirilir).
        cases = []
        if contact_type == "farmer":
            cases = await db.cases.find({"farmer_id": contact_id}, {"_id": 0}).sort("created_at", -1).to_list(300)
            for cs in cases:
                cs["kind"] = "case"
                cs["timeline_at"] = cs.get("created_at")

        merged = comms + cases
        merged.sort(key=lambda x: x.get("timeline_at") or "", reverse=True)
        return merged
