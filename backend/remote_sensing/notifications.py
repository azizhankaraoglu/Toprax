"""
TOPRAX Remote Sensing — Communication Policy köprüsü.

KENDİ bildirim mantığı YOK (prompt: "notifications.py — Communication
Policy köprüsü, KENDİ bildirim mantığı YOK"). Anomali tespit edilince
mevcut event_bus'a `remote_sensing_anomaly_detected` event'i yayınlar;
hangi kanaldan/kime/hangi koşulda gideceğini (SMS/WhatsApp/Mail/Push +
opsiyonel otomatik görev) admin IT-27 kural ekranından tanımlar. Onaylı/
onaysız akış (KONU 1.4) o kuralın `requires_approval` alanıyla çalışır —
burada YENİ bir policy ekranı/mantığı İCAT EDİLMEZ.
"""
from datetime import datetime, timezone

from event_bus import publish
from .dto import Anomaly


async def publish_anomaly(db, parcel: dict, anomaly: Anomaly, provider: str) -> None:
    """Parsel'e anomaliyi işler + Communication Policy'ye event yayınlar."""
    if not anomaly.detected:
        return
    payload = {
        "parcel_id": parcel.get("id"),
        "farmer_id": parcel.get("farmer_id"),
        "severity": anomaly.severity,
        "confidence": anomaly.confidence,
        "reason": anomaly.reason,
        "date": anomaly.date,
        "provider": provider,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    # Parcel.remote_sensing.last_anomaly güncellenir (izlenebilirlik).
    await db.parcels.update_one(
        {"id": parcel.get("id")},
        {"$set": {"remote_sensing.last_anomaly": payload,
                  "remote_sensing.last_updated": payload["detected_at"]}},
    )
    await publish(db, "remote_sensing_anomaly_detected", payload)
