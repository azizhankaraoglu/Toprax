"""
=====================================================================
TabSIS — Süreç-İçi Event Bus (IT-24 / FAZ 8 devam)
=====================================================================
ROADMAP'in IT-27'de formalize edeceği genel event-driven altyapının
TEMEL kullanımı — bu iterasyon SADECE `automation.py`'nin (kural tabanlı
otomatik görev oluşturma) ihtiyaç duyduğu asgari pub/sub'ı sağlar.
Redis/RabbitMQ KURULU DEĞİL (bkz. CLAUDE.md "Uyarlama Kararları") —
bilinçli olarak basit, tek-process, in-process bir kayıt defteri:
`subscribe(event_type, handler)` + `await publish(db, event_type, payload)`.

Tek bir global registry (`_subscribers`) modül seviyesinde tutulur —
`server.py` tek process/tek worker çalıştırdığı için (uvicorn --reload,
Windows dev ortamı) bu yeterlidir; çoklu worker/yatay ölçekleme senaryosu
BİLİNÇLİ OLARAK bu iterasyonun kapsamı dışında (IT-27'nin kapsamı).

Her `publish` çağrısı, hangi handler'lar tetiklenirse tetiklensin,
`automation_events` koleksiyonuna bir iz kaydı bırakır — bu hem otomasyon
geçmişinin denetlenebilir olmasını sağlar hem de HENÜZ hiçbir kural
tanımlanmamış bir event_type için bile "olay gerçekleşti" kanıtı tutar.
"""
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List

# Yeni bir event türü eklemek isteyen bir entegrasyon noktası (ör. IT-25/26/
# başka bir modül) SADECE bu sözlüğe bir satır ekler — event_bus.py'nin
# geri kalanı DEĞİŞMEZ.
EVENT_TYPES = {
    "soil_analysis_completed": "Toprak Analizi Tamamlandı",
    "support_request_completed": "Destek Talebi Tamamlandı",
    # IT-27 — Communication Policy'nin (communication_policy.py) admin
    # tanımlı "olay → kanal(lar)" kurallarının tetikleyicisi olan 3 iş olayı
    # (ROADMAP'in "en az 3 iş olayı" kabul kriteri).
    "entitlement_created": "Hakediş Oluştu",
    "task_assigned": "Görev Atandı",
    "contract_approved": "Sözleşme Onaylandı",
    # IT-07b — Onay Zinciri Motoru'nun (approval.py) TEK yayınladığı olay;
    # payload["process"] alanına göre ilgili tüketici modül (support.py,
    # campaigns.py, ...) kendi entity'sini günceller.
    "approval_decided": "Onay Kararı Verildi",
    # IT-28 — Inbound Case Yönetimi (case_management.py).
    "case_created": "Case Oluşturuldu / Atandı",
}

_subscribers: Dict[str, List[Callable[..., Awaitable[None]]]] = {}


def subscribe(event_type: str, handler: Callable[..., Awaitable[None]]) -> None:
    """`register_X_routes` içinde, server.py başlangıcında BİR KEZ çağrılır."""
    _subscribers.setdefault(event_type, []).append(handler)


async def publish(db, event_type: str, payload: dict) -> None:
    """Event'i `automation_events`'e loglar, sonra kayıtlı TÜM handler'ları
    sırayla çalıştırır. Bir handler hata verirse DİĞERLERİ etkilenmez ve asıl
    yayınlayan işlem (ör. toprak analizi kaydı) hata almadan devam eder —
    otomasyon bir yan etkidir, ana iş akışını kilitlememelidir."""
    log_doc = {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "payload": payload,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "handler_errors": [],
    }
    await db.automation_events.insert_one(log_doc)
    for handler in _subscribers.get(event_type, []):
        try:
            await handler(db, event_type, payload)
        except Exception as e:
            await db.automation_events.update_one(
                {"id": log_doc["id"]}, {"$push": {"handler_errors": str(e)}}
            )
