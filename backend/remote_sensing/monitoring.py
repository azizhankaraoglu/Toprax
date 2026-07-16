"""
TOPRAX Remote Sensing — Monitoring (API çağrı/kota/hata izleme).

Health Center (IT-33) ile AYNI aile — ayrı bir üst menü DEĞİL, Sistem/
Ayarlar altında. `remote_sensing_tasks` koleksiyonundan CANLI hesaplar
(yeniden ağ çağrısı YAPMAZ, platform_core Health Center deseniyle aynı).
EOSDA trial 1000 istek limiti + "1 görüntü = parsel+indeks başına 3 istek"
maliyet gerçeği burada raporlanır.
"""
from datetime import datetime, timezone
from typing import Dict

from .dto import EOSDA_TRIAL_REQUEST_LIMIT, EOSDA_REQUESTS_PER_INDEX


async def record_task_metric(db, task_type: str, success: bool,
                             duration_ms: int, api_calls: int = 1) -> None:
    """Her EOSDA çağrısı sonrası çağrılır — aylık sayaç (monitoring özeti
    için hızlı okuma; ham geçmiş `remote_sensing_tasks`'te zaten var)."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    await db.remote_sensing_metrics.update_one(
        {"month": month},
        {"$inc": {
            "total_api_calls": api_calls,
            "success": 1 if success else 0,
            "failed": 0 if success else 1,
            "total_duration_ms": duration_ms,
        }},
        upsert=True,
    )


async def get_monitoring_summary(db) -> Dict:
    """Monitoring ekranının tükettiği tek çağrı — provider durumu + kota +
    task istatistikleri + rate/response özeti."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    m = await db.remote_sensing_metrics.find_one({"month": month}, {"_id": 0}) or {}

    total_calls = m.get("total_api_calls", 0)
    success = m.get("success", 0)
    failed = m.get("failed", 0)
    total_dur = m.get("total_duration_ms", 0)
    done = success + failed

    # Task durum kırılımı (canlı).
    pipeline = [{"$group": {"_id": "$state", "n": {"$sum": 1}}}]
    by_state = {}
    async for row in db.remote_sensing_tasks.aggregate(pipeline):
        by_state[row["_id"]] = row["n"]

    # Integration Center'dan provider sağlığı (yeniden ağ çağrısı YOK).
    integ = await db.integrations.find_one({"type": "eosda"}, {"_id": 0}) or {}
    cfg = integ.get("config", {})
    provider_status = "hata" if failed > success and done > 0 else (
        "saglikli" if integ.get("enabled") else "pasif")

    return {
        "month": month,
        "provider": "eosda",
        "provider_status": provider_status,
        "enabled": bool(integ.get("enabled")),
        "mock_mode": cfg.get("mock_mode", True),
        "last_success_at": integ.get("last_success_at"),
        "total_api_calls": total_calls,
        "success": success,
        "failed": failed,
        "pending": by_state.get("queued", 0) + by_state.get("running", 0) + by_state.get("polling", 0),
        "queue_by_state": by_state,
        "avg_response_ms": round(total_dur / done, 1) if done else 0,
        # Trial kota: "1 görüntü = parsel+indeks başına 3 istek" gerçeğiyle.
        "trial_request_limit": EOSDA_TRIAL_REQUEST_LIMIT,
        "requests_per_index": EOSDA_REQUESTS_PER_INDEX,
        "trial_remaining": max(0, EOSDA_TRIAL_REQUEST_LIMIT - total_calls),
        "trial_used_pct": round(100 * total_calls / EOSDA_TRIAL_REQUEST_LIMIT, 1),
    }
