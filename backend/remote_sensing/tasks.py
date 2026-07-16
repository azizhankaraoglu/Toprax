"""
TOPRAX Remote Sensing — Task entity + polling background job yönetimi.

Her EOSDA çağrısı bir Task kaydı (`remote_sensing_tasks`). FAZ 18'in
(IT-48) `ai_jobs`'ından KAVRAMSAL olarak farklı (biri dış API çağrı
geçmişi, diğeri iç AI kuyruğu) ama AYNI atomik claim deseniyle
(`find_one_and_update`) yönetilir — iki ayrı kuyruk mimarisi İCAT
EDİLMEZ. Görüntü akışının 3 adımı (search→download→status) tek bir
background job içinde zincirlenir; kullanıcı sadece "beklemede/hazır" görür.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .dto import TaskState, TaskType, EOSDA_REQUESTS_PER_INDEX
from .monitoring import record_task_metric
from .notifications import publish_anomaly


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_task(db, parcel_id: str, task_type: str, indices: List[str],
                      date_range_days: int = 365, trigger: str = "manual",
                      priority: int = 0) -> dict:
    """Yeni RS task'ı kuyruğa alır (state=queued). Worker sonra claim eder."""
    doc = {
        "id": str(uuid.uuid4()),
        "provider": "eosda",
        "parcel_id": parcel_id,
        "task_type": task_type,
        "indices": indices,
        "date_range_days": date_range_days,
        "trigger": trigger,          # manual | scheduled | auto_tasking
        "priority": priority,
        "state": TaskState.QUEUED.value,
        "retry_count": 0,
        "api_calls": 0,
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "response_summary": None,
        "error": None,
        "created_at": _now(),
    }
    await db.remote_sensing_tasks.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def claim_next_task(db) -> Optional[dict]:
    """Atomik claim (ai_jobs deseni) — queued bir task'ı running'e çeker."""
    return await db.remote_sensing_tasks.find_one_and_update(
        {"state": TaskState.QUEUED.value},
        {"$set": {"state": TaskState.RUNNING.value, "started_at": _now()}},
        sort=[("priority", -1), ("created_at", 1)],
        return_document=True, projection={"_id": 0},
    )


async def run_task(db, task: dict, provider) -> dict:
    """Bir task'ı sağlayıcı üzerinden yürütür: field oluştur/kullan → istatistik
    veya görüntü akışını zincirle → polling → sonucu + Parcel.remote_sensing'i
    güncelle → anomali varsa Communication Policy'ye köprüle."""
    t0 = time.monotonic()
    parcel = await db.parcels.find_one({"id": task["parcel_id"]}, {"_id": 0}) or {}
    geometry = parcel.get("geometry") or parcel.get("geojson")
    api_calls = 0
    success = False
    summary = None
    error = None
    try:
        rs = parcel.get("remote_sensing") or {}
        field_id = rs.get("eosda_field_id") or provider.create_field(geometry or {})
        api_calls += 1

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=task.get("date_range_days", 365))
        ttype = task["task_type"]

        if ttype in (TaskType.STATISTICS.value, "statistics"):
            indices = task.get("indices") or ["ndvi"]
            task_id = provider.request_statistics(field_id, indices, (start, end))
            api_calls += len(indices) * EOSDA_REQUESTS_PER_INDEX
            status = _poll(provider, task_id)
            series = (status.result or {}).get("series", [])
            summary = {"points": len(series), "indices": indices}
            await _apply_statistics(db, parcel, provider, series)
            success = status.state == TaskState.COMPLETED
        elif ttype in (TaskType.DOWNLOAD.value, "download"):
            scenes = provider.search_scenes(field_id, (start, end))
            api_calls += 1
            if not scenes:
                raise RuntimeError("Tarih aralığında görüntü bulunamadı")
            newest = sorted(scenes, key=lambda s: s.get("date", ""))[-1]
            img_task = provider.request_image_download(newest["view_id"])
            api_calls += 1
            status = _poll(provider, img_task)
            await _store_image(db, parcel, provider, newest, status)
            summary = {"view_id": newest["view_id"], "date": newest.get("date")}
            success = status.state == TaskState.COMPLETED
        elif ttype in (TaskType.WEATHER.value, "weather"):
            wd = provider.get_weather(field_id, (start, end))
            api_calls += 1
            summary = {"weather": bool(wd)}
            success = wd is not None
        elif ttype in (TaskType.TASKING.value, "tasking"):
            res = provider.request_tasking(field_id, priority="high", reason="manual/auto")
            api_calls += 1
            summary = res
            success = res.get("status") not in ("hata", "desteklenmiyor")
        else:
            raise ValueError(f"Bilinmeyen task_type: {ttype}")

        # field_id'yi ilk oluşturduysak sakla (yeniden kullanılabilir).
        if geometry and not rs.get("eosda_field_id"):
            await db.parcels.update_one(
                {"id": parcel.get("id")},
                {"$set": {"remote_sensing.eosda_field_id": field_id,
                          "remote_sensing.provider": provider.name,
                          "remote_sensing.last_updated": _now()}})
    except Exception as e:
        error = str(e)
        success = False

    dur_ms = int((time.monotonic() - t0) * 1000)
    await db.remote_sensing_tasks.update_one(
        {"id": task["id"]},
        {"$set": {
            "state": TaskState.COMPLETED.value if success else TaskState.FAILED.value,
            "finished_at": _now(), "duration_ms": dur_ms,
            "api_calls": api_calls, "response_summary": summary, "error": error,
        }})
    await record_task_metric(db, task["task_type"], success, dur_ms, api_calls)
    return {"id": task["id"], "success": success, "api_calls": api_calls,
            "duration_ms": dur_ms, "error": error, "summary": summary}


def _poll(provider, task_id: str, max_wait_s: int = 300, interval_s: float = 2.0):
    """3-adımlı akışın son adımı: Task Status polling (webhook YOK). Mock modda
    task anında tamamlanır; gerçek EOSDA'da 30-300 sn sürebilir (zoning)."""
    deadline = time.monotonic() + max_wait_s
    status = provider.get_task_status(task_id)
    while status.state in (TaskState.POLLING, TaskState.RUNNING, TaskState.QUEUED):
        if time.monotonic() > deadline:
            status.state = TaskState.FAILED
            status.error = "polling zaman aşımı"
            break
        time.sleep(interval_s)
        status = provider.get_task_status(task_id)
    return status


async def _apply_statistics(db, parcel: dict, provider, series: List[Dict]) -> None:
    """İstatistik sonucunu Parcel.remote_sensing'e işler + son NDVI/anomali +
    anomali varsa Communication Policy köprüsü."""
    if not series:
        return
    latest = series[-1]
    await db.parcels.update_one(
        {"id": parcel.get("id")},
        {"$set": {
            "remote_sensing.provider": provider.name,
            "remote_sensing.last_analysis_date": _now(),
            "remote_sensing.last_image_date": latest.get("date"),
            "remote_sensing.last_ndvi": latest.get("ndvi"),
            "remote_sensing.last_updated": _now(),
        }})
    # İstatistikleri arşivle (avg/min/max/median/std için ham seri).
    vals = [p["ndvi"] for p in series if p.get("ndvi") is not None]
    if vals:
        vals_sorted = sorted(vals)
        stat = {
            "id": str(uuid.uuid4()), "parcel_id": parcel.get("id"),
            "provider": provider.name, "index": "ndvi",
            "avg": round(sum(vals) / len(vals), 3), "min": min(vals), "max": max(vals),
            "median": vals_sorted[len(vals_sorted) // 2],
            "count": len(vals), "series": series, "created_at": _now(),
        }
        await db.remote_sensing_statistics.insert_one(dict(stat))
    # Anomali → Communication Policy (KONU 1.4).
    anomaly = provider.detect_anomaly(series)
    await publish_anomaly(db, parcel, anomaly, provider.name)


async def _store_image(db, parcel: dict, provider, scene: dict, status) -> None:
    """Görüntü metadata'sını arşive yazar (storage.py deseni). Hiçbir görüntü
    fiziksel SİLİNMEZ (is_active=false ile eskitilir — ledger-tarzı)."""
    doc = {
        "id": str(uuid.uuid4()), "parcel_id": parcel.get("id"),
        "provider": provider.name, "capture_date": scene.get("date"),
        "cloud_pct": scene.get("cloud_pct"), "satellite": scene.get("satellite"),
        "image_type": "rgb", "format": "png",
        "result_url": getattr(status, "result_url", None),
        "is_active": True, "created_at": _now(),
    }
    await db.remote_sensing_images.insert_one(dict(doc))
    await db.parcels.update_one(
        {"id": parcel.get("id")},
        {"$set": {"remote_sensing.last_image_date": scene.get("date"),
                  "remote_sensing.last_updated": _now()}})


async def process_pending_tasks(db, provider_factory, max_tasks: int = 25) -> Dict:
    """Worker tick — kuyruktaki task'ları sırayla işler (scheduler tick'i
    veya manuel tetikleme çağırır). provider_factory: async () -> provider."""
    processed = []
    for _ in range(max_tasks):
        task = await claim_next_task(db)
        if not task:
            break
        provider = await provider_factory(task.get("provider_override"))
        processed.append(await run_task(db, task, provider))
    return {"processed": len(processed), "results": processed}
