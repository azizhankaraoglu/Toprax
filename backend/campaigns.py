"""
=====================================================================
TabSIS — Kampanya + Segment (saved_queries üzerinden) + Planlı Gönderim
+ Onay + Retry/Fallback Zinciri (IT-26 / FAZ 9 devam)
=====================================================================
Segment Yönetimi AYRI bir koleksiyon İCAT ETMEDİ — `saved_queries.py`'nin
(IT-09) zaten sağladığı "Query Engine (IT-08) DSL'ini adlandırılmış +
tekrar kullanılabilir + paylaşılabilir kayıt olarak saklama" işlevini
DOĞRUDAN kullanır: `Campaign.segment_query_id` bir `saved_queries`
kaydına işaret eder (`module` HER ZAMAN "farmers" olmalı — kampanyalar
çiftçi hedefler). Bu, ROADMAP'in "Kaydedilebilir ve tekrar kullanılabilir
olmalı" kabul kriterini YENİ kod yazmadan karşılar.

Not (dürüstlük notu — bkz. entitlement.py'nin benzer sadeleştirme
notları): Query Engine'in `farmers` modülünde şu an ROADMAP'in verdiği
"Hakedişi oluşanlar" / "Son 90 gündür ziyaret edilmeyenler" gibi
HESAPLANMIŞ/çapraz-modül kriterler YOK (`CORE_FILTERABLE_FIELDS` sadece
farmers dokümanının kendi alanları — ad/telefon/köy/bölge/karne/üyelik
yılı vb.). Bu iterasyon YENİ bir hesaplama motoru İCAT ETMEDİ; segment
filtreleri bugün Query Engine'in desteklediği alanlarla sınırlıdır,
ileride Query Engine'e computed-field desteği eklenirse kampanyalar
otomatik faydalanır (çağıran kod DEĞİŞMEZ).

Kampanya durum makinesi (ROADMAP'in verdiği 5 durum, BİREBİR): taslak →
planlandi → yayinda → tamamlandi (+ herhangi bir aşamadan iptal_edildi)
— `support.py`/`field_ops.py`'deki `ALLOWED_TRANSITIONS` kalıbıyla AYNI.
`requires_approval=True` ise "yayinda"ya geçiş `approved=True` OLMADAN
reddedilir (`POST /campaigns/{id}/approve` ayrı bir adım — "yanlış
gönderim önleme" kabul kriteri, approve'u AYRI bir permission'a
(`communications:campaigns_approve`) bağlı, `templates_manage` gibi
BİLİNÇLİ OLARAK sadece üst katman rollere verildi).

Planlı gönderim: `scheduled_at` alanı + `POST /campaigns/run-scheduled`.
Gerçek bir OS cron/Celery beat KURULU DEĞİL (CLAUDE.md'nin "Redis/
RabbitMQ kurulu değil" kararıyla AYNI aile) — bu endpoint "zamanı gelmiş
kampanyaları çalıştır" tick'ini SİMÜLE eder; prod'da bir scheduler
tarafından periyodik çağrılır. ROADMAP'in "worker/cron simülasyonu
yeterli" kabul kriteriyle tutarlı.

Retry/Fallback: `Campaign.channel_chain` SIRALI bir kanal listesi
(örn. `["whatsapp","sms"]`) — her alıcı için zincirdeki kanallar sırayla
denenir (o kanal için `template_ids`'te şablon tanımlıysa), İLK BAŞARILI
olanda durulur. Her deneme (başarılı/başarısız) `communications.py`'nin
`send_via_channel()`'ı ile `communications` koleksiyonuna `campaign_id`
etiketiyle loglanır — AYRI bir "kampanya sonucu" koleksiyonu İCAT
EDİLMEDİ, timeline zaten bunu taşıyor (bkz. `GET /campaigns/{id}/results`).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List

from channel_providers import CHANNELS
from communications import send_via_channel
from query_engine import execute_query
from event_bus import subscribe
from approval import maybe_start_approval

STATUS_LABELS = {
    "taslak": "Taslak", "planlandi": "Planlandı", "yayinda": "Yayında",
    "tamamlandi": "Tamamlandı", "iptal_edildi": "İptal Edildi",
}
# NOT: STATUS_FLOW'un support.py/field_ops.py'deki SIRALI (bir sonraki
# adımdan başka geçiş yok) kalıbı burada BİLİNÇLİ OLARAK uygulanmadı —
# "taslak"tan hem "planlandi" (zamanla) hem DOĞRUDAN "yayinda"ya (şimdi
# gönder) geçilebilir olmalı, ikisi de meşru kullanıcı akışı (roadmap'in
# "planlı VEYA elle Şimdi Gönder" ayrımıyla tutarlı).
ALLOWED_TRANSITIONS = {
    "taslak": {"planlandi", "yayinda", "iptal_edildi"},
    "planlandi": {"yayinda", "iptal_edildi"},
    "yayinda": set(),        # geçiş fonksiyonu içinde ANINDA "tamamlandi"ya taşınır, dışarıdan hedeflenmez
    "tamamlandi": set(),     # terminal
    "iptal_edildi": set(),   # terminal
}


class CampaignCreate(BaseModel):
    name: str
    channel_chain: List[str]              # örn. ["whatsapp","sms"] — sırayla denenir (retry/fallback)
    segment_query_id: str                 # saved_queries kaydı (module="farmers")
    template_ids: Dict[str, str]          # kanal -> template_id (her kanalın kendi şablonu)
    variables: Dict[str, str] = {}        # tüm alıcılara ORTAK ek değişkenler
    requires_approval: bool = False
    scheduled_at: Optional[str] = None    # ISO string — verilmezse elle "Şimdi Gönder" ile tetiklenir


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    channel_chain: Optional[List[str]] = None
    segment_query_id: Optional[str] = None
    template_ids: Optional[Dict[str, str]] = None
    variables: Optional[Dict[str, str]] = None
    requires_approval: Optional[bool] = None
    scheduled_at: Optional[str] = None


class CampaignTransition(BaseModel):
    status: str


async def _resolve_segment_farmer_ids(db, user: dict, segment_query_id: str) -> List[str]:
    sq = await db.saved_queries.find_one({"id": segment_query_id}, {"_id": 0})
    if not sq:
        raise HTTPException(404, "Segment (kayıtlı sorgu) bulunamadı")
    if sq["module"] != "farmers":
        raise HTTPException(400, "Kampanya segmenti sadece 'farmers' modülü için tanımlı bir kayıtlı sorgu olabilir")
    result = await execute_query(
        db, "farmers", user, sq["filters"], logic=sq.get("logic", "AND"),
        page=1, page_size=1000, fields=["id"],
    )
    return [item["id"] for item in result["items"]]


async def _execute_campaign(db, user: dict, campaign: dict) -> dict:
    """Retry/fallback zinciriyle segmentteki HER çiftçiye gönderim yapar,
    her denemeyi `communications`'a loglar, özet döner. Senkron/simüle —
    gerçek bir async worker kuyruğu YOK (bkz. modül docstring'i)."""
    recipient_ids = await _resolve_segment_farmer_ids(db, user, campaign["segment_query_id"])
    sent, failed = 0, 0
    for farmer_id in recipient_ids:
        delivered = False
        for channel in campaign["channel_chain"]:
            template_id = (campaign.get("template_ids") or {}).get(channel)
            if not template_id:
                continue   # bu kanal için şablon tanımlanmamış — zincirdeki sıradaki kanal denenir
            _, ok = await send_via_channel(
                db, channel=channel, contact_type="farmer", contact_id=farmer_id,
                template_id=template_id, variables=campaign.get("variables") or {},
                sent_by=f"kampanya: {campaign['name']}", campaign_id=campaign["id"],
                message_kind="campaign",
            )
            if ok:
                delivered = True
                break
        if delivered:
            sent += 1
        else:
            failed += 1
    return {"total": len(recipient_ids), "sent": sent, "failed": failed}


def register_campaign_routes(api_router, db, current_user, require_permission, log_audit):

    async def _handle_approval_decided(db, event_type, payload):
        """(IT-07b) approval.py'den SADECE process="campaign_publish" kararlarını
        dinler; onaylanırsa mevcut `approved` bayrağını set eder (UI/transition_
        campaign bunu zaten okuyor, davranış DEĞİŞMEDİ), reddedilirse kampanyayı
        "iptal_edildi" durumuna taşır."""
        if payload.get("process") != "campaign_publish":
            return
        campaign_id = payload["entity_id"]
        campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not campaign:
            return
        if payload.get("decision") == "onaylandi":
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {
                "approved": True, "approved_by": "Onay Zinciri", "approved_at": datetime.now(timezone.utc).isoformat(),
            }})
        else:
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {
                "status": "iptal_edildi", "status_updated_at": datetime.now(timezone.utc).isoformat(),
            }})

    subscribe("approval_decided", _handle_approval_decided)

    @api_router.get("/campaigns")
    async def list_campaigns(status: Optional[str] = None, user=Depends(require_permission("communications:campaigns_view"))):
        filt = {"status": status} if status else {}
        return await db.campaigns.find(filt, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, user=Depends(require_permission("communications:campaigns_view"))):
        doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Kampanya bulunamadı")
        return doc

    @api_router.get("/campaigns/{campaign_id}/results")
    async def campaign_results(campaign_id: str, user=Depends(require_permission("communications:campaigns_view"))):
        return await db.communications.find({"campaign_id": campaign_id}, {"_id": 0}).sort("sent_at", -1).to_list(2000)

    @api_router.post("/campaigns")
    async def create_campaign(body: CampaignCreate, request: Request, user=Depends(require_permission("communications:campaigns_manage"))):
        invalid_channels = [c for c in body.channel_chain if c not in CHANNELS]
        if invalid_channels:
            raise HTTPException(400, f"Bilinmeyen kanal(lar): {invalid_channels}")
        if not body.channel_chain:
            raise HTTPException(400, "En az bir kanal (channel_chain) gerekli")

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["status"] = "taslak"
        doc["approved"] = False
        doc["approved_by"] = None
        doc["approved_at"] = None
        doc["result_summary"] = None
        now = datetime.now(timezone.utc).isoformat()
        doc["created_at"] = now
        doc["status_updated_at"] = now
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.campaigns.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="campaign", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/campaigns/{campaign_id}")
    async def update_campaign(campaign_id: str, body: CampaignUpdate, request: Request,
                               user=Depends(require_permission("communications:campaigns_manage"))):
        old = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kampanya bulunamadı")
        if old["status"] != "taslak":
            raise HTTPException(400, "Sadece 'taslak' durumundaki kampanya düzenlenebilir")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "channel_chain" in updates:
            invalid_channels = [c for c in updates["channel_chain"] if c not in CHANNELS]
            if invalid_channels:
                raise HTTPException(400, f"Bilinmeyen kanal(lar): {invalid_channels}")
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.campaigns.update_one({"id": campaign_id}, {"$set": updates})
        new = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="campaign", entity_id=campaign_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.post("/campaigns/{campaign_id}/approve")
    async def approve_campaign(campaign_id: str, request: Request,
                                user=Depends(require_permission("communications:campaigns_approve"))):
        old = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kampanya bulunamadı")
        if old["status"] not in ("taslak", "planlandi"):
            raise HTTPException(400, "Sadece taslak/planlandı durumundaki kampanya onaylanabilir")

        # (IT-07b) Onay Zinciri Motoru — process="campaign_publish" için aktif bir
        # kural TANIMLIYSA bu uç sadece TALEP başlatır (karar /api/approvals/{id}/
        # decide ile verilir). Kural TANIMLI DEĞİLSE (varsayılan) eski doğrudan-onay
        # davranışı AYNEN çalışır — geriye uyumlu.
        approval = await maybe_start_approval(
            db, process="campaign_publish", entity_type="campaign", entity_id=campaign_id,
            requester_user_id=user["id"], context={"recipient_count": old.get("recipient_count", 0)},
        )
        if approval:
            return {"status": "onay_bekliyor", "approval_instance": approval, "campaign": old}

        updates = {"approved": True, "approved_by": user.get("full_name") or user.get("email"),
                   "approved_at": datetime.now(timezone.utc).isoformat()}
        await db.campaigns.update_one({"id": campaign_id}, {"$set": updates})
        new = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        await log_audit(db, user, action="approve", entity="campaign", entity_id=campaign_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.put("/campaigns/{campaign_id}/transition")
    async def transition_campaign(campaign_id: str, body: CampaignTransition, request: Request,
                                   user=Depends(require_permission("communications:campaigns_manage"))):
        old = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kampanya bulunamadı")
        if body.status not in ALLOWED_TRANSITIONS:
            raise HTTPException(400, f"Geçersiz durum: {body.status}")
        current = old["status"]
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if body.status not in allowed:
            raise HTTPException(
                400,
                f"'{STATUS_LABELS.get(current, current)}' durumundan "
                f"'{STATUS_LABELS.get(body.status, body.status)}' durumuna geçilemez"
                + (f" (izin verilenler: {', '.join(STATUS_LABELS[s] for s in allowed)})" if allowed else " (bu durum terminaldir)"),
            )

        if body.status == "yayinda":
            if old.get("requires_approval") and not old.get("approved"):
                raise HTTPException(400, "Bu kampanya yönetici onayı bekliyor — önce onaylanmalı")
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {
                "status": "yayinda", "status_updated_at": datetime.now(timezone.utc).isoformat(),
            }})
            summary = await _execute_campaign(db, user, old)
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {
                "status": "tamamlandi", "status_updated_at": datetime.now(timezone.utc).isoformat(),
                "executed_at": datetime.now(timezone.utc).isoformat(), "result_summary": summary,
            }})
        else:
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {
                "status": body.status, "status_updated_at": datetime.now(timezone.utc).isoformat(),
            }})

        new = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        await log_audit(db, user, action="status_change", entity="campaign", entity_id=campaign_id,
                         old_value={"status": current}, new_value={"status": new["status"]}, request=request)
        return new

    @api_router.post("/campaigns/run-scheduled")
    async def run_scheduled_campaigns(request: Request, user=Depends(require_permission("communications:campaigns_manage"))):
        """
        "Zamanı gelmiş kampanyaları çalıştır" tick'i — gerçek bir OS cron/
        Celery beat KURULU DEĞİL (bkz. modül docstring'i), bu uç prod'da bir
        scheduler tarafından periyodik çağrılacak SİMÜLASYONDUR. `planlandi`
        durumunda VE `scheduled_at <= şimdi` olan tüm kampanyaları, tek tek
        `PUT /campaigns/{id}/transition {status:"yayinda"}` ile AYNI mantıkla
        (onay kontrolü dahil) çalıştırır.
        """
        now = datetime.now(timezone.utc).isoformat()
        due = await db.campaigns.find(
            {"status": "planlandi", "scheduled_at": {"$ne": None, "$lte": now}}, {"_id": 0},
        ).to_list(200)
        executed = []
        for campaign in due:
            if campaign.get("requires_approval") and not campaign.get("approved"):
                continue   # onay bekleyen bir kampanya zamanı gelse bile OTOMATİK yayınlanmaz
            await db.campaigns.update_one({"id": campaign["id"]}, {"$set": {
                "status": "yayinda", "status_updated_at": now,
            }})
            summary = await _execute_campaign(db, user, campaign)
            await db.campaigns.update_one({"id": campaign["id"]}, {"$set": {
                "status": "tamamlandi", "status_updated_at": datetime.now(timezone.utc).isoformat(),
                "executed_at": datetime.now(timezone.utc).isoformat(), "result_summary": summary,
            }})
            await log_audit(db, user, action="status_change", entity="campaign", entity_id=campaign["id"],
                             old_value={"status": "planlandi"}, new_value={"status": "tamamlandi", "result_summary": summary},
                             request=request)
            executed.append({"id": campaign["id"], "name": campaign["name"], "result_summary": summary})
        return {"executed": executed}
