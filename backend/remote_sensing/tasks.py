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

# Kota + süre koruması: bir "download" turunda EN FAZLA bu kadar sahne render
# edilir (her render 1 EOSDA task'ı ≈ 1-2 dk sürer, senkron işlenir). En yeni +
# düşük bulutlu sahne seçilir. Daha fazla geçmiş görüntü istenirse artırılır.
IMAGE_SCENES_LIMIT = 1


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
        field_id = rs.get("eosda_field_id")

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=task.get("date_range_days", 365))
        ttype = task["task_type"]

        if ttype in (TaskType.STATISTICS.value, "statistics"):
            # İstatistik geometry ile DOĞRUDAN çalışır — gerçek EOSDA mt_stats
            # field zorunlu tutmaz, gereksiz avca/fields çağrısı yapılmaz.
            indices = task.get("indices") or ["ndvi"]
            task_id = provider.request_statistics(field_id or task["parcel_id"], indices, (start, end), geometry=geometry)
            api_calls += len(indices) * EOSDA_REQUESTS_PER_INDEX
            status = _poll(provider, task_id)
            series = provider.parse_statistics(status.result)
            summary = {"points": len(series), "indices": indices}
            await _apply_statistics(db, parcel, provider, series)
            success = status.state == TaskState.COMPLETED and len(series) > 0
        elif ttype in (TaskType.DOWNLOAD.value, "download"):
            # Görüntü akışı da geometry ile DOĞRUDAN çalışır (field zorunlu değil).
            scenes = provider.search_scenes(field_id or task["parcel_id"], (start, end), geometry=geometry)
            api_calls += EOSDA_REQUESTS_PER_INDEX      # search = 1 mt_stats çağrısı
            if not scenes:
                raise RuntimeError("Tarih aralığında görüntü bulunamadı")
            # Kota koruması: en yeni + düşük bulutlu (≤%20) EN FAZLA N sahne render.
            clear = [s for s in scenes if (s.get("cloud_pct") or 0) <= 20]
            picks = sorted(clear or scenes, key=lambda s: s.get("date", ""))[-IMAGE_SCENES_LIMIT:]
            stored = 0
            for sc in picks:
                img_task = provider.request_image_download(sc["view_id"], geometry=geometry)
                api_calls += 1
                st = _poll(provider, img_task)
                if await _store_image(db, parcel, provider, sc, st):
                    stored += 1
            summary = {"scenes": len(picks), "stored": stored}
            success = stored > 0
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
        if field_id and geometry and not rs.get("eosda_field_id"):
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


async def _store_image(db, parcel: dict, provider, scene: dict, status) -> bool:
    """Render sonucundaki imzalı URL'den PNG'yi indirip yerel diske kaydeder
    (storage.py `backend/uploads/` deseni), metadata'yı remote_sensing_images'a
    yazar. Görüntü indirilemezse metadata yine yazılır (stored_name=None) —
    panel o durumda 'görüntü yok' gösterir. Görüntü SİLİNMEZ (is_active ile
    eskitilir). Döner: PNG gerçekten kaydedildi mi?"""
    from storage import UPLOAD_DIR
    url = getattr(status, "result_url", None)
    stored_name = None
    if getattr(status, "state", None) == TaskState.COMPLETED and url:
        try:
            data = provider.download_image_bytes(url)
            if data and len(data) > 100:
                d = UPLOAD_DIR / "remote_sensing"
                d.mkdir(parents=True, exist_ok=True)
                stored_name = f"{uuid.uuid4()}.png"
                with open(d / stored_name, "wb") as f:
                    f.write(data)
        except Exception:
            stored_name = None
    doc = {
        "id": str(uuid.uuid4()), "parcel_id": parcel.get("id"),
        "provider": provider.name, "capture_date": scene.get("date"),
        "cloud_pct": scene.get("cloud_pct"), "satellite": scene.get("satellite"),
        "image_type": "rgb", "format": "png", "view_id": scene.get("view_id"),
        "stored_name": stored_name,
        "result_url": url,
        "is_active": True, "created_at": _now(),
    }
    await db.remote_sensing_images.insert_one(dict(doc))
    await db.parcels.update_one(
        {"id": parcel.get("id")},
        {"$set": {"remote_sensing.last_image_date": scene.get("date"),
                  "remote_sensing.last_updated": _now()}})
    return stored_name is not None


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
