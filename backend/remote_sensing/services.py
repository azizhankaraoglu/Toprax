"""
TOPRAX Remote Sensing — HTTP yüzeyi + modül kayıt fonksiyonu.

CLAUDE.md konvansiyon #1 (modül kayıt kalıbı): `register_remote_sensing_
routes(api_router, db, current_user, require_permission, log_audit)`.
server.py'ye YENİ domain kodu eklenmez — bu paket kendi register'ıyla bağlanır.
Kendi RBAC/audit/bildirim/depolama mekanizmasını YAZMAZ — mevcut
permissions/audit/Communication Policy/storage'dan kullanır.
"""
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request

from .dto import (TaramaPolicy, RemoteSensingTaskCreate, ScanFrequency)
from .providers import get_remote_sensing_provider
from .tasks import create_task, process_pending_tasks
from .scheduler import run_scheduler_tick, find_uncovered_parcels
from .monitoring import get_monitoring_summary


def register_remote_sensing_routes(api_router, db, current_user, require_permission, log_audit):

    async def _provider_factory(provider_override=None):
        return await get_remote_sensing_provider(db, provider_override=provider_override)

    def _now():
        return datetime.now(timezone.utc).isoformat()

    # ---- Sağlayıcı durumu ----------------------------------------------------
    @api_router.get("/remote-sensing/providers/status")
    async def rs_provider_status(user=Depends(require_permission("remote_sensing:view"))):
        provider = await get_remote_sensing_provider(db)
        integ = await db.integrations.find_one({"type": "eosda"}, {"_id": 0}) or {}
        return {
            "active_provider": provider.name,
            "is_real": not getattr(provider, "mock_mode", True),
            "enabled": bool(integ.get("enabled")),
            "capabilities": provider.capabilities,
        }

    # ---- Tarama Politikaları (Karar 2) --------------------------------------
    @api_router.get("/remote-sensing/policies")
    async def rs_list_policies(user=Depends(require_permission("remote_sensing:view"))):
        return await db.remote_sensing_policies.find({}, {"_id": 0}).sort("priority", -1).to_list(500)

    @api_router.post("/remote-sensing/policies")
    async def rs_create_policy(body: TaramaPolicy, request: Request,
                               user=Depends(require_permission("remote_sensing:settings"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = _now()
        await db.remote_sensing_policies.insert_one(dict(doc))
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="remote_sensing_policy",
                        entity_id=doc["id"], new_value={"name": doc["name"]}, request=request)
        return doc

    @api_router.put("/remote-sensing/policies/{policy_id}")
    async def rs_update_policy(policy_id: str, body: TaramaPolicy, request: Request,
                               user=Depends(require_permission("remote_sensing:settings"))):
        upd = body.model_dump(exclude_unset=True)
        upd.pop("id", None)
        res = await db.remote_sensing_policies.update_one({"id": policy_id}, {"$set": upd})
        if res.matched_count == 0:
            raise HTTPException(404, "Politika bulunamadı")
        await log_audit(db, user, action="update", entity="remote_sensing_policy",
                        entity_id=policy_id, new_value=upd, request=request)
        return await db.remote_sensing_policies.find_one({"id": policy_id}, {"_id": 0})

    @api_router.delete("/remote-sensing/policies/{policy_id}")
    async def rs_delete_policy(policy_id: str, request: Request,
                               user=Depends(require_permission("remote_sensing:settings"))):
        # Soft delete (CLAUDE.md konvansiyon #3).
        res = await db.remote_sensing_policies.update_one({"id": policy_id}, {"$set": {"is_active": False}})
        if res.matched_count == 0:
            raise HTTPException(404, "Politika bulunamadı")
        await log_audit(db, user, action="delete", entity="remote_sensing_policy",
                        entity_id=policy_id, request=request)
        return {"ok": True}

    @api_router.get("/remote-sensing/uncovered-parcels")
    async def rs_uncovered(user=Depends(require_permission("remote_sensing:view"))):
        """"Politikasız Parseller" — kapsam dışı kalan parsel uyarı listesi."""
        return await find_uncovered_parcels(db)

    # ---- Manuel Senaryo ("Uydu Analizi Güncelle") ----------------------------
    @api_router.post("/remote-sensing/manual-sync")
    async def rs_manual_sync(body: dict, request: Request,
                             user=Depends(require_permission("remote_sensing:manual_sync"))):
        """Tekli/çoklu parsel için anlık analiz — Tarama Politikası'nı BYPASS
        eder, tenant kotasına 'manuel' işaretlenir (normal taramadan pahalı)."""
        parcel_ids = body.get("parcel_ids") or ([body["parcel_id"]] if body.get("parcel_id") else [])
        if not parcel_ids:
            raise HTTPException(400, "parcel_ids veya parcel_id gerekli")
        indices = body.get("indices") or ["ndvi"]
        # task_types listesi verilirse (ör. ["statistics","download"]) her parsel
        # için hem NDVI istatistiği hem uydu görüntüsü tek çağrıda kuyruğa alınır;
        # geriye dönük uyumlu: tekil task_type hâlâ desteklenir.
        task_types = body.get("task_types") or [body.get("task_type", "statistics")]
        created = []
        for pid in parcel_ids:
            for tt in task_types:
                created.append(await create_task(db, parcel_id=pid, task_type=tt,
                                                 indices=indices, trigger="manual",
                                                 priority=100))  # manuel = yüksek öncelik
        result = await process_pending_tasks(db, _provider_factory)
        await log_audit(db, user, action="manual_sync", entity="remote_sensing",
                        entity_id=",".join(parcel_ids)[:120],
                        new_value={"count": len(parcel_ids), "trigger": "manual"}, request=request)
        return {"queued": len(created), **result}

    # ---- Scheduler (otomatik tarama turu) ------------------------------------
    @api_router.post("/remote-sensing/scheduler/run")
    async def rs_run_scheduler(request: Request,
                               user=Depends(require_permission("remote_sensing:automatic_sync"))):
        result = await run_scheduler_tick(db, _provider_factory)
        await log_audit(db, user, action="scheduler_run", entity="remote_sensing",
                        entity_id="tick", new_value=result, request=request)
        return result

    # ---- Task kuyruğu --------------------------------------------------------
    @api_router.get("/remote-sensing/tasks")
    async def rs_list_tasks(limit: int = 100,
                            user=Depends(require_permission("remote_sensing:view"))):
        return await db.remote_sensing_tasks.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)

    # ---- Monitoring ----------------------------------------------------------
    @api_router.get("/remote-sensing/monitoring")
    async def rs_monitoring(user=Depends(require_permission("remote_sensing:view"))):
        return await get_monitoring_summary(db)

    # ---- Parsel Time Series + Görüntü arşivi ---------------------------------
    @api_router.get("/remote-sensing/parcels/{parcel_id}/timeseries")
    async def rs_timeseries(parcel_id: str,
                            user=Depends(require_permission("remote_sensing:statistics"))):
        stats = await db.remote_sensing_statistics.find(
            {"parcel_id": parcel_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
        return {"parcel_id": parcel_id, "statistics": stats}

    @api_router.get("/remote-sensing/parcels/{parcel_id}/images")
    async def rs_images(parcel_id: str, include_inactive: bool = False,
                        user=Depends(require_permission("remote_sensing:images"))):
        q = {"parcel_id": parcel_id}
        if not include_inactive:
            q["is_active"] = True
        return await db.remote_sensing_images.find(q, {"_id": 0}).sort("capture_date", -1).to_list(200)
