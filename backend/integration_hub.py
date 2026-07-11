"""
=====================================================================
TabSIS — Integration Hub Formalizasyonu + Webhook Engine (IT-32 / FAZ 11)
=====================================================================
ROADMAP: "TABSİS dışarıya doğrudan bağlanmaz; Google Maps, AI servisleri,
SMS/WhatsApp/E-posta, GeoServer, NASA/Sentinel/Planet, MERNİS/TAKBİS dahil
tüm 3. parti çağrılar tek bir Integration Hub modülünden geçer."

Bu KONSOLİDASYONDUR, refactor değil (mevcut arayüzler korunur):
  - AI: `ai_provider.py` (bu iterasyonda YENİ — extras.py'nin iki yerde
    tekrarladığı doğrudan OpenAI/Gemini/Anthropic çağrısı buraya taşındı).
  - İletişim: `channel_providers.py` (IT-25'te ZATEN ABC+factory).
  - Mekânsal/Uydu: `satellite_provider.py` (IT-17'de ZATEN ABC+factory).
Üçü de zaten "provider pattern" kullanıyordu — bu modülün asıl katkısı
onları TEK bir cepheden (facade) yeniden dışa açmak (`INTEGRATION_REGISTRY`
+ `GET /integration-hub/registry`, admin'in "hangi entegrasyon hangi
modülden geçiyor" görebildiği tek yer) ve Webhook Engine'i eklemek.

Webhook Engine — event_bus.py'nin (IT-24/27) bir subscriber'ı:
`automation.py`'nin "event → DB'den kural oku → yan etki üret" kalıbının
BİREBİR AYNISI, yan etki bu sefer bir FieldTask değil GERÇEK bir dış HTTP
POST isteği. `requests` (extras.py'de zaten bağımlı) senkron kullanılır —
codebase'in mevcut deseniyle tutarlı (yeni bir async http kütüphanesi
eklenmedi). Her deneme (başarılı/başarısız, gerçek ağ hatası dahil)
`webhook_deliveries`'e loglanır — automation_rule_runs'ın izleme
kalıbıyla AYNI aile.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List
import requests

from event_bus import subscribe, EVENT_TYPES
from channel_providers import CHANNELS

# Admin'e "hangi kategori hangi modülden geçiyor" gösteren sabit bir envanter —
# kod değişmeden yeni bir provider eklendiğinde bu satırın altına bir tane
# daha eklenir (channel/satellite zaten çoklu-implementasyon destekliyor,
# burada tek satır olarak görünmeleri "kaç farklı sağlayıcı var" değil
# "bu kategori Hub'a bağlı mı" sorusuna cevap verir).
INTEGRATION_REGISTRY = [
    {"category": "ai", "label": "Yapay Zeka (AI Copilot / Hastalık Tespiti)",
     "module": "ai_provider.py", "implementations": ["openai", "gemini", "anthropic"]},
    {"category": "iletisim", "label": "İletişim (SMS/E-Posta/WhatsApp/Push/Sesli Arama)",
     "module": "channel_providers.py", "implementations": list(CHANNELS.keys())},
    {"category": "mekansal", "label": "Mekânsal / Uydu (NDVI Zaman Serisi)",
     "module": "satellite_provider.py", "implementations": ["demo"]},
]


class WebhookRuleCreate(BaseModel):
    name: str
    event_type: str
    target_url: str
    headers: Dict[str, str] = {}


class WebhookRuleUpdate(BaseModel):
    name: Optional[str] = None
    target_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None


def _deliver_webhook(rule: dict, event_type: str, payload: dict) -> dict:
    """Tek bir kurala GERÇEK bir HTTP POST dener, sonucu (log'lanacak
    şekilde) döner — hedef URL erişilemez/yanıt vermezse istisna burada
    yutulur (bir kuralın başarısızlığı diğerlerini etkilemez)."""
    delivery = {
        "id": str(uuid.uuid4()), "webhook_rule_id": rule["id"], "rule_name": rule["name"],
        "event_type": event_type, "target_url": rule["target_url"], "payload": payload,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = requests.post(
            rule["target_url"], json={"event_type": event_type, "payload": payload},
            headers=rule.get("headers") or {}, timeout=5,
        )
        delivery["ok"] = resp.ok
        delivery["status_code"] = resp.status_code
        delivery["response_snippet"] = resp.text[:500]
    except Exception as e:
        delivery["ok"] = False
        delivery["status_code"] = None
        delivery["error"] = str(e)
    return delivery


async def _handle_webhook_event(db, event_type: str, payload: dict) -> None:
    """`event_bus.subscribe()` ile HER `EVENT_TYPES` girdisine bağlanan tek
    handler — automation.py'nin `_handle_automation_event` kalıbıyla AYNI:
    hangi kuralın hangi event'e ait olduğunu DB'den okur, event_bus.py
    webhook kuralı bilmez (bilinçli katman ayrımı)."""
    rules = await db.webhook_rules.find({"event_type": event_type, "is_active": True}, {"_id": 0}).to_list(100)
    for rule in rules:
        delivery = _deliver_webhook(rule, event_type, payload)
        await db.webhook_deliveries.insert_one(delivery)


def register_integration_hub_routes(api_router, db, current_user, require_permission, log_audit):
    # server.py başlangıcında BİR KEZ çağrılır (automation.py'nin register_*
    # çağrı yeriyle AYNI kalıp) — her bilinen event_type için AYNI handler'ı bağlar.
    for event_type in EVENT_TYPES:
        subscribe(event_type, _handle_webhook_event)

    @api_router.get("/integration-hub/registry")
    async def get_registry(user=Depends(require_permission("integration_hub:view"))):
        return INTEGRATION_REGISTRY

    @api_router.get("/integration-hub/event-types")
    async def get_event_types(user=Depends(require_permission("integration_hub:view"))):
        return [{"key": k, "label": v} for k, v in EVENT_TYPES.items()]

    @api_router.get("/webhook-rules")
    async def list_webhook_rules(user=Depends(require_permission("integration_hub:view"))):
        return await db.webhook_rules.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/webhook-rules")
    async def create_webhook_rule(body: WebhookRuleCreate, request: Request,
                                   user=Depends(require_permission("integration_hub:manage"))):
        if body.event_type not in EVENT_TYPES:
            raise HTTPException(400, f"Bilinmeyen event_type: {body.event_type}")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.webhook_rules.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="webhook_rule", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/webhook-rules/{rule_id}")
    async def update_webhook_rule(rule_id: str, body: WebhookRuleUpdate, request: Request,
                                   user=Depends(require_permission("integration_hub:manage"))):
        old = await db.webhook_rules.find_one({"id": rule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Webhook kuralı bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.webhook_rules.update_one({"id": rule_id}, {"$set": updates})
        new = await db.webhook_rules.find_one({"id": rule_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="webhook_rule", entity_id=rule_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/webhook-rules/{rule_id}")
    async def delete_webhook_rule(rule_id: str, request: Request,
                                   user=Depends(require_permission("integration_hub:manage"))):
        """Soft delete (convention #3)."""
        old = await db.webhook_rules.find_one({"id": rule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Webhook kuralı bulunamadı")
        await db.webhook_rules.update_one({"id": rule_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="deactivate", entity="webhook_rule", entity_id=rule_id, old_value=old, new_value={"is_active": False}, request=request)
        return {"status": "ok"}

    @api_router.post("/webhook-rules/{rule_id}/test")
    async def test_webhook_rule(rule_id: str, request: Request,
                                 user=Depends(require_permission("integration_hub:manage"))):
        """Admin ekrandan "Test Et" — event_bus'ı beklemeden GERÇEK bir HTTP
        isteğini örnek bir payload ile hemen dener (kabul kriterinin
        "simüle hedef URL'e log/istek atarak doğrulanabilir" maddesi için)."""
        rule = await db.webhook_rules.find_one({"id": rule_id}, {"_id": 0})
        if not rule:
            raise HTTPException(404, "Webhook kuralı bulunamadı")
        delivery = _deliver_webhook(rule, rule["event_type"], {"test": True, "triggered_by": user.get("full_name") or user.get("email")})
        await db.webhook_deliveries.insert_one(dict(delivery))
        delivery.pop("_id", None)
        return delivery

    @api_router.get("/webhook-rules/{rule_id}/deliveries")
    async def list_webhook_deliveries(rule_id: str, user=Depends(require_permission("integration_hub:view"))):
        return await db.webhook_deliveries.find({"webhook_rule_id": rule_id}, {"_id": 0}).sort("attempted_at", -1).to_list(200)
