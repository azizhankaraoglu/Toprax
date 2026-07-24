"""
=====================================================================
Toprax — İstek İdempotency (Denetim raporu #2 / Faz 8 — Rol Bazlı Offline)
=====================================================================
`lib/offlineQueue.js`'in (IT-35) internet geldiğinde kuyruktaki istekleri
TEKRAR gönderme deseni — istek sunucuya ULAŞIP başarıyla işlendiği HALDE
yanıt istemciye dönmezse (bağlantı o anda koptuysa), kuyruk isteği "başarısız"
sanıp bir sonraki `flush()`'ta AYNI isteği TEKRAR gönderir. Sonuç: aynı
ziyaret/toprak numunesi/destek talebi/kantar kaydı İKİ KEZ yazılır.

Bu modül `X-Idempotency-Key` header'ına (frontend her kuyruğa eklemede
`crypto.randomUUID()` ile ÜRETİR, bkz. `lib/offlineQueue.js`) göre "bu
anahtarla daha önce işlenmiş bir istek var mı" kontrolü yapar — varsa
kaydedilmiş YANITI AYNEN döner (yeni bir kayıt YAZMADAN), yoksa çağıran
işini yapar ve sonucu bu anahtarla saklar.

Geriye dönük uyumlu: header YOKSA (eski/masaüstü istemciler, veya bu
mekanizmayı henüz kullanmayan uçlar) `get_cached_response` sessizce
`(None, None)` döner — davranış AYNEN eskisi gibi kalır, hiçbir endpoint
bu header'ı ZORUNLU kılmaz.

TTL: `idempotency_keys.created_at` üzerinde 7 günlük bir TTL index (server.py
startup'ında kurulur) — kuyruk kalıcı olarak büyümez, 7 gün sonra otomatik silinir.
"""
from datetime import datetime, timezone


async def get_cached_response(db, request, endpoint: str):
    """(key, cached_response) döner. `request` None VEYA header yoksa
    (key=None, cached=None) — çağıran normal akışına devam eder."""
    if request is None:
        return None, None
    key = request.headers.get("x-idempotency-key")
    if not key:
        return None, None
    doc = await db.idempotency_keys.find_one({"key": key, "endpoint": endpoint}, {"_id": 0})
    return key, (doc["response"] if doc else None)


async def save_response(db, key, endpoint: str, response) -> None:
    """`key` None ise (header hiç gönderilmemiş) no-op."""
    if not key:
        return
    await db.idempotency_keys.update_one(
        {"key": key, "endpoint": endpoint},
        {"$setOnInsert": {"response": response, "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
