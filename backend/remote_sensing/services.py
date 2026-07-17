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


# =====================================================================
# AI YORUMLAMA — EOSDA/NDVI verisini çiftçinin anlayacağı dile çevirir
# =====================================================================
_HEALTHY_NDVI = 0.65
_AI_SYSTEM = ("Sen deneyimli bir tarımsal uzaktan algılama danışmanısın. NDVI/uydu "
              "verilerini çiftçinin anlayacağı SADE, NET Türkçe ile yorumlarsın. Kısa "
              "ve somut yaz, gereksiz teknik jargondan kaçın.")


def _rs_metrics(series):
    ndvis = [p.get("ndvi") for p in series if p.get("ndvi") is not None]
    if not ndvis:
        return None
    latest = series[-1]
    return {
        "avg": round(sum(ndvis) / len(ndvis), 3),
        "min": min(ndvis), "max": max(ndvis),
        "latest_ndvi": latest.get("ndvi"), "latest_date": latest.get("date"),
        "first_ndvi": series[0].get("ndvi"), "points": len(series),
    }


def _rs_rule_interpretation(parcel, m):
    crop = parcel.get("current_crop") or "ürün"
    latest, avg = m["latest_ndvi"], m["avg"]
    lines = ["NDVI (Bitki Örtüsü İndeksi) bitki yoğunluğunu ve sağlığını gösterir: 0'a "
             "yakın değer çıplak veya stresli toprağı, 1'e yakın değer gür ve sağlıklı "
             "bitki örtüsünü ifade eder."]
    if latest is None:
        return " ".join(lines)
    if latest >= _HEALTHY_NDVI:
        lines.append(f"Durum: SAĞLIKLI. Son ölçüm NDVI {latest} — bitki örtüsü gür ve sağlıklı görünüyor.")
    elif latest >= 0.45:
        lines.append(f"Durum: İZLEMEYE DEĞER. Son ölçüm NDVI {latest} — orta düzey; hafif su/besin stresi başlıyor olabilir.")
    else:
        lines.append(f"Durum: STRES / OLASI SUSUZLUK. Son ölçüm NDVI {latest} — düşük; tarla büyük olasılıkla su veya besin stresi altında (susuz kalmış olabilir).")
    beklenen = "beklenenin ALTINDA" if avg < _HEALTHY_NDVI else "beklenen aralıkta"
    lines.append(f"Gerekçe: Sağlıklı bir {crop} tarlasında bu dönemde NDVI genelde ~{_HEALTHY_NDVI}–0.80 olmalı; "
                 f"bu parselin ortalaması {avg} — yani {beklenen}.")
    first = m.get("first_ndvi")
    if first is not None and latest is not None:
        if latest < first - 0.1:
            lines.append(f"Eğilim: NDVI {first} → {latest} düşüşte; sulama/gübreleme gözden geçirilmeli.")
        elif latest > first + 0.1:
            lines.append(f"Eğilim: NDVI {first} → {latest} artışta; bitki gelişimi olumlu.")
    if latest < 0.45:
        lines.append("Öneri: En kısa sürede sulama ve toprak nemi kontrolü önerilir.")
    return " ".join(lines)


def _rs_ai_prompt(parcel, m, series):
    crop = parcel.get("current_crop") or "ürün"
    seri = ", ".join(f"{p.get('date')}={p.get('ndvi')}" for p in series if p.get("ndvi") is not None)
    return (
        f"Parsel: {parcel.get('name') or parcel.get('parcel_code')} "
        f"({parcel.get('area_dekar')} dekar), ürün: {crop}.\n"
        f"NDVI ortalaması: {m['avg']}, en düşük: {m['min']}, en yüksek: {m['max']}, "
        f"son ölçüm: {m['latest_ndvi']} (tarih {m['latest_date']}), toplam {m['points']} tarih.\n"
        f"NDVI zaman serisi: {seri}.\n"
        f"Referans: sağlıklı bir {crop} tarlasında bu dönemde NDVI ~0.65-0.80 olmalı.\n"
        "Şunları açıkla: (1) NDVI nedir, yüksek/düşük olması ne anlama gelir; "
        "(2) bu tarlanın durumu (sağlıklı mı, su/besin stresi veya susuzluk var mı); "
        "(3) GEREKÇE olarak beklenen NDVI ile bu tarlanın değerini KARŞILAŞTIR; "
        "(4) 1-2 somut öneri (ör. sulama). En fazla 6-7 cümle, sade Türkçe."
    )


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

    # ---- AI Yorumlama (EOSDA/NDVI verisini anlamlandırır) --------------------
    @api_router.post("/remote-sensing/parcels/{parcel_id}/interpret")
    async def rs_interpret(parcel_id: str,
                           user=Depends(require_permission("remote_sensing:statistics"))):
        """En güncel NDVI istatistiğini alır, kural-bazlı bir yorum üretir ve AI
        servisi (Ayarlar › Entegrasyonlar › AI) yapılandırılmışsa onunla
        zenginleştirir — 'tarlanız susuz' gibi gerekçeli, çiftçi-dostu çıktı."""
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0}) or {}
        stat = await db.remote_sensing_statistics.find_one(
            {"parcel_id": parcel_id}, {"_id": 0}, sort=[("created_at", -1)])
        series = (stat or {}).get("series") or []
        m = _rs_metrics(series)
        if not m:
            raise HTTPException(400, "Önce 'Uydu Analizini Güncelle' ile NDVI verisi üretin.")
        rule = _rs_rule_interpretation(parcel, m)
        ai_text, ai_powered, ai_error = None, False, None
        try:
            from integrations import get_ai_service_config
            from ai_provider import get_ai_provider
            cfg = await get_ai_service_config(db)
            if cfg and cfg.get("api_key") and cfg.get("provider"):
                provider = get_ai_provider(cfg["provider"], cfg["api_key"], cfg.get("model"))
                ai_text = provider.generate_text(_AI_SYSTEM, _rs_ai_prompt(parcel, m, series))
                ai_powered = bool(ai_text)
        except Exception as e:
            ai_error = str(e)[:220]
        return {
            "parcel_id": parcel_id, "metrics": m,
            "interpretation": (ai_text or rule).strip(),
            "rule_based": rule, "ai_powered": ai_powered, "ai_error": ai_error,
            "index": (stat or {}).get("index", "ndvi"),
            "analysis_date": (stat or {}).get("created_at"),
        }
