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

from fastapi import Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse

from .dto import (TaramaPolicy, RemoteSensingTaskCreate, ScanFrequency)
from .indices import ALL_INDEX_CODES, INDEX_CATALOG
from .providers import (get_remote_sensing_provider, SATELLITE_BRAND,
                        PROVIDER_INTEGRATION_TYPES)
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
    m = {
        "avg": round(sum(ndvis) / len(ndvis), 3),
        "min": min(ndvis), "max": max(ndvis),
        "latest_ndvi": latest.get("ndvi"), "latest_date": latest.get("date"),
        "first_ndvi": series[0].get("ndvi"), "points": len(series),
    }
    # Denetim eklentisi (2026-07-25) — kök NDVI alanları KIRILMADAN (mevcut
    # frontend interp.metrics.avg vb. çalışmaya devam eder), diğer 8
    # indeksin de ortalama/son değeri `by_index` altında toplanır.
    by_index = {}
    for code in ALL_INDEX_CODES:
        if code == "ndvi":
            continue
        vals = [p.get(code) for p in series if p.get(code) is not None]
        if vals:
            by_index[code] = {"avg": round(sum(vals) / len(vals), 3), "min": min(vals),
                              "max": max(vals), "latest": series[-1].get(code)}
    m["by_index"] = by_index
    return m


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

    # Denetim eklentisi (2026-07-25) — su stresi (NDWI/MSI) ve klorofil/azot
    # (NDRE/RECI/CCCI) bulguları, veri MEVCUTSA veri-güdümlü olarak eklenir
    # (mevcut NDVI paragrafı DEĞİŞMEDEN kalır).
    bi = m.get("by_index", {})
    if "ndwi" in bi or "msi" in bi:
        ndwi_l = bi.get("ndwi", {}).get("latest")
        msi_l = bi.get("msi", {}).get("latest")
        if (ndwi_l is not None and ndwi_l < 0) or (msi_l is not None and msi_l > 1.3):
            lines.append(f"Su Stresi: NDWI={ndwi_l}, MSI={msi_l} — bitki su içeriği düşük/nem stresi "
                         "göstergeleri var, sulama zamanlaması gözden geçirilmeli.")
        else:
            lines.append(f"Su Stresi: NDWI={ndwi_l}, MSI={msi_l} — mevcut nem durumu normal aralıkta.")
    if "ndre" in bi or "reci" in bi or "ccci" in bi:
        lines.append(f"Klorofil/Azot: NDRE={bi.get('ndre', {}).get('latest')}, "
                     f"RECI={bi.get('reci', {}).get('latest')} — erken azot/klorofil stresini "
                     "NDVI'den daha erken gösterebilir.")
    if "lai" in bi:
        lines.append(f"Yaprak Alan İndeksi (TAHMİNİ): {bi['lai'].get('latest')} — NDVI'den ampirik "
                     "olarak türetilmiştir, kesin ölçüm değildir.")
    return " ".join(lines)


def _rs_ai_prompt(parcel, m, series):
    crop = parcel.get("current_crop") or "ürün"
    seri = ", ".join(f"{p.get('date')}={p.get('ndvi')}" for p in series if p.get("ndvi") is not None)
    # Denetim eklentisi (2026-07-25) — mevcut NDVI istemi DEĞİŞMEDEN, her ek
    # indeks için (veri varsa) tek satırlık bir zaman serisi metni eklenir.
    extra_series = []
    bi = m.get("by_index", {})
    for code, label in (("ndwi", "NDWI"), ("msi", "MSI"), ("ndre", "NDRE"), ("reci", "RECI"), ("lai", "LAI (tahmini)")):
        if code in bi:
            vals = ", ".join(f"{p.get('date')}={p.get(code)}" for p in series if p.get(code) is not None)
            if vals:
                extra_series.append(f"{label} zaman serisi: {vals}.")
    extra_block = ("\n" + "\n".join(extra_series) + "\n") if extra_series else "\n"
    ek_talimat = ("(5) varsa su stresi (NDWI/MSI) ve klorofil/azot (NDRE/RECI) bulgularını da yorumuna kat."
                  if extra_series else "")
    return (
        f"Parsel: {parcel.get('name') or parcel.get('parcel_code')} "
        f"({parcel.get('area_dekar')} dekar), ürün: {crop}.\n"
        f"NDVI ortalaması: {m['avg']}, en düşük: {m['min']}, en yüksek: {m['max']}, "
        f"son ölçüm: {m['latest_ndvi']} (tarih {m['latest_date']}), toplam {m['points']} tarih.\n"
        f"NDVI zaman serisi: {seri}.{extra_block}"
        f"Referans: sağlıklı bir {crop} tarlasında bu dönemde NDVI ~0.65-0.80 olmalı.\n"
        "Şunları açıkla: (1) NDVI nedir, yüksek/düşük olması ne anlama gelir; "
        "(2) bu tarlanın durumu (sağlıklı mı, su/besin stresi veya susuzluk var mı); "
        "(3) GEREKÇE olarak beklenen NDVI ile bu tarlanın değerini KARŞILAŞTIR; "
        f"(4) 1-2 somut öneri (ör. sulama). {ek_talimat} En fazla 6-7 cümle, sade Türkçe."
    )


def register_remote_sensing_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    # God Mode Modül Yönetimi — "remote_sensing" flag'i kapatılınca 403 döner.
    require_feature = require_feature or (lambda key: (lambda: True))

    async def _provider_factory(provider_override=None):
        return await get_remote_sensing_provider(db, provider_override=provider_override)

    def _now():
        return datetime.now(timezone.utc).isoformat()

    # ---- İndeks kataloğu (2026-07-25) — frontend'in TR etiket/açıklama'yı
    # hardcode ETMEDEN çekmesi için (tek kaynak ilkesi, bkz. indices.py).
    @api_router.get("/remote-sensing/index-catalog")
    async def rs_index_catalog(user=Depends(require_permission("remote_sensing:view"))):
        return {code: {"label_tr": v["label_tr"], "category": v["category"].value,
                       "description_tr": v["description_tr"], "is_estimated": v["is_estimated"],
                       "chart_default_visible": v["chart_default_visible"]}
                for code, v in INDEX_CATALOG.items()}

    # ---- Sağlayıcı durumu ----------------------------------------------------
    @api_router.get("/remote-sensing/providers/status")
    async def rs_provider_status(user=Depends(require_permission("remote_sensing:view")),
                                  _feat=Depends(require_feature("remote_sensing"))):
        """Aktif uzaktan algılama sağlayıcısının durumu.

        2026-08-18 — iki değişiklik:
          * `enabled` artık AKTİF sağlayıcının kendi entegrasyon kaydından
            okunur (önceden HER ZAMAN `eosda` kaydına bakıyordu; varsayılan
            GEE'ye geçtikten sonra bu, gerçek modda çalışan bir sistemi
            ekranda "entegrasyon pasif" gösterirdi).
          * `brand` — ekranlarda gösterilecek ad. Sağlayıcı adı bir uygulama
            detayıdır; kullanıcı arayüzü markayı gösterir (bkz.
            providers/__init__.py SATELLITE_BRAND).
        """
        provider = await get_remote_sensing_provider(db)
        integ = await db.integrations.find_one({"type": PROVIDER_INTEGRATION_TYPES.get(provider.name, "eosda")},
                                               {"_id": 0}) or {}
        return {
            "brand": SATELLITE_BRAND,
            "active_provider": provider.name,
            "integration_type": PROVIDER_INTEGRATION_TYPES.get(provider.name, "eosda"),
            "is_real": not getattr(provider, "mock_mode", True),
            "enabled": bool(integ.get("enabled")),
            "capabilities": provider.capabilities,
        }

    # ---- Tarama Politikaları (Karar 2) --------------------------------------
    @api_router.get("/remote-sensing/policies")
    async def rs_list_policies(user=Depends(require_permission("remote_sensing:view")),
                                _feat=Depends(require_feature("remote_sensing"))):
        return await db.remote_sensing_policies.find({}, {"_id": 0}).sort("priority", -1).to_list(500)

    @api_router.post("/remote-sensing/policies")
    async def rs_create_policy(body: TaramaPolicy, request: Request,
                               user=Depends(require_permission("remote_sensing:settings")),
                               _feat=Depends(require_feature("remote_sensing"))):
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
                               user=Depends(require_permission("remote_sensing:settings")),
                               _feat=Depends(require_feature("remote_sensing"))):
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
                               user=Depends(require_permission("remote_sensing:settings")),
                               _feat=Depends(require_feature("remote_sensing"))):
        # Soft delete (CLAUDE.md konvansiyon #3).
        res = await db.remote_sensing_policies.update_one({"id": policy_id}, {"$set": {"is_active": False}})
        if res.matched_count == 0:
            raise HTTPException(404, "Politika bulunamadı")
        await log_audit(db, user, action="delete", entity="remote_sensing_policy",
                        entity_id=policy_id, request=request)
        return {"ok": True}

    @api_router.get("/remote-sensing/uncovered-parcels")
    async def rs_uncovered(user=Depends(require_permission("remote_sensing:view")),
                            _feat=Depends(require_feature("remote_sensing"))):
        """"Politikasız Parseller" — kapsam dışı kalan parsel uyarı listesi."""
        return await find_uncovered_parcels(db)

    # ---- Manuel Senaryo ("Uydu Analizi Güncelle") ----------------------------
    @api_router.post("/remote-sensing/manual-sync")
    async def rs_manual_sync(body: dict, request: Request,
                             user=Depends(require_permission("remote_sensing:manual_sync")),
                             _feat=Depends(require_feature("remote_sensing"))):
        """Tekli/çoklu parsel için anlık analiz — Tarama Politikası'nı BYPASS
        eder, tenant kotasına 'manuel' işaretlenir (normal taramadan pahalı)."""
        parcel_ids = body.get("parcel_ids") or ([body["parcel_id"]] if body.get("parcel_id") else [])
        if not parcel_ids:
            raise HTTPException(400, "parcel_ids veya parcel_id gerekli")
        # 2026-08-18 — varsayılan indeks kümesi NDVI'den TÜM kataloğa çıktı:
        # varsayılan sağlayıcı artık GEE/HLS ve orada 10 indeksin hepsi TEK
        # sahne taramasında hesaplanıyor (ek istek/kota maliyeti YOK, bkz.
        # gee_hls/service.py _add_indices ve tasks.py'deki maliyet istisnası).
        # Sentinel-2 manuel getirme ucu bunu zaten yapıyordu; iki akış artık
        # aynı davranışta. EOSDA'ya `provider_override` ile düşen bir tarama
        # pahalıya gelirse politika kendi `indices` listesini verebilir.
        indices = body.get("indices") or list(ALL_INDEX_CODES)
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

    # ---- Sentinel-2 manuel görüntü getirme (Denetim Faz 5) --------------------
    @api_router.post("/remote-sensing/sentinel2/fetch")
    async def rs_sentinel2_fetch(body: dict, request: Request,
                                 user=Depends(require_permission("remote_sensing:manual_sync")),
                                 _feat=Depends(require_feature("remote_sensing"))):
        """"Yeni Görüntü Getir" — manual-sync ile AYNI mantık, SADECE
        provider_override="sentinel2" ile (EOSDA'ya dokunmaz, ayrı bir görüntü
        + NDVI istatistiği üretir). ~5 günde bir otomatik tazelenme için
        Tarama Politikası'na `provider_override:"sentinel2"` + sıklık
        `bes_gunde_bir` ile bağlanabilir (scheduler.py bu politikayı
        işlerken hem statistics hem download task'ı otomatik kuyruğa alır)."""
        parcel_id = body.get("parcel_id")
        if not parcel_id:
            raise HTTPException(400, "parcel_id gerekli")
        created = [
            # Denetim eklentisi (2026-07-25) — Sentinel-2 TEK istekte tüm 9
            # indeksi hesaplayabildiğinden (ücretsiz, ek maliyet yok — bkz.
            # sentinel2.py _build_stats_evalscript) varsayılan artık NDVI
            # değil, TÜM katalog.
            await create_task(db, parcel_id=parcel_id, task_type="statistics",
                              indices=ALL_INDEX_CODES, trigger="manual", priority=100,
                              provider_override="sentinel2"),
            await create_task(db, parcel_id=parcel_id, task_type="download",
                              indices=["ndvi"], trigger="manual", priority=100,
                              provider_override="sentinel2"),
        ]
        result = await process_pending_tasks(db, _provider_factory)
        await log_audit(db, user, action="sentinel2_fetch", entity="remote_sensing",
                        entity_id=parcel_id, new_value={"trigger": "manual"}, request=request)
        return {"queued": len(created), **result}

    # ---- Ekili/Söküm durumu toplu yeniden-hesaplama (#2) ---------------------
    @api_router.post("/remote-sensing/recompute-crop-status")
    async def rs_recompute_crop_status(request: Request,
                                       user=Depends(require_permission("remote_sensing:manual_sync")),
                                       _feat=Depends(require_feature("remote_sensing"))):
        """TÜM aktif parseller için ekili/söküm durumunu (manuel ekim + son
        NDVI'dan, EOSDA çağrısı YAPMADAN) yeniden hesaplar — Dashboard'u besler."""
        from .crop_status import recompute_all
        result = await recompute_all(db)
        await log_audit(db, user, action="recompute_crop_status", entity="remote_sensing",
                        entity_id="all", new_value=result.get("counts"), request=request)
        return result

    # ---- Scheduler (otomatik tarama turu) ------------------------------------
    @api_router.post("/remote-sensing/scheduler/run")
    async def rs_run_scheduler(request: Request,
                               user=Depends(require_permission("remote_sensing:automatic_sync")),
                               _feat=Depends(require_feature("remote_sensing"))):
        result = await run_scheduler_tick(db, _provider_factory)
        await log_audit(db, user, action="scheduler_run", entity="remote_sensing",
                        entity_id="tick", new_value=result, request=request)
        return result

    # ---- Task kuyruğu --------------------------------------------------------
    @api_router.get("/remote-sensing/tasks")
    async def rs_list_tasks(limit: int = 100,
                            user=Depends(require_permission("remote_sensing:view")),
                            _feat=Depends(require_feature("remote_sensing"))):
        return await db.remote_sensing_tasks.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)

    # ---- Monitoring ----------------------------------------------------------
    @api_router.get("/remote-sensing/monitoring")
    async def rs_monitoring(user=Depends(require_permission("remote_sensing:view")),
                             _feat=Depends(require_feature("remote_sensing"))):
        return await get_monitoring_summary(db)

    # ---- Parsel Time Series + Görüntü arşivi ---------------------------------
    @api_router.get("/remote-sensing/parcels/{parcel_id}/timeseries")
    async def rs_timeseries(parcel_id: str,
                            user=Depends(require_permission("remote_sensing:statistics")),
                            _feat=Depends(require_feature("remote_sensing"))):
        stats = await db.remote_sensing_statistics.find(
            {"parcel_id": parcel_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
        return {"parcel_id": parcel_id, "statistics": stats}

    @api_router.get("/remote-sensing/parcels/{parcel_id}/images")
    async def rs_images(parcel_id: str, include_inactive: bool = False,
                        user=Depends(require_permission("remote_sensing:images")),
                        _feat=Depends(require_feature("remote_sensing"))):
        q = {"parcel_id": parcel_id}
        if not include_inactive:
            q["is_active"] = True
        return await db.remote_sensing_images.find(q, {"_id": 0}).sort("capture_date", -1).to_list(200)

    @api_router.get("/remote-sensing/images/file/{stored_name}")
    async def rs_image_file(stored_name: str, request: Request, token: str = Query(None)):
        """Yerel diske kaydedilmiş uydu görüntüsünü (PNG) sunar. <img src>
        özel header gönderemediği için ?token= de kabul edilir (storage.py'nin
        dosya-indirme deseniyle AYNI: JWT imza/aktiflik + tenant kontrolü).

        MİMARİ DÜZELTME (2026-07-24): eskiden burada
        `_feat=Depends(require_feature("remote_sensing"))` vardı ama <img>
        etiketi Authorization header GÖNDEREMEZ (bu yüzden zaten ?token=
        deseni var) — tenant_context_middleware `current_tenant_id`'yi SADECE
        Authorization header'ından okur, ?token= query param'ını GÖRMEZ. Yani
        `current_tenant_id` None kalıyordu ve flag kontrolü tenant filtresiz,
        rastgele bir tenant'ın kaydına göre karar veriyordu (bkz. forms_module.
        py'deki AYNI düzeltme). Doğrusu: token'ı çöz, görüntünün GERÇEK
        tenant_id'sini bul, `current_tenant_id`'yi GEÇİCİ olarak ona set et,
        ANCAK O ZAMAN flag'i kontrol et."""
        from security import decode_token
        from storage import UPLOAD_DIR
        from tenant_context import current_tenant_id
        from platform_core import is_feature_enabled, FEATURE_FLAG_LABELS
        if "/" in stored_name or ".." in stored_name or "\\" in stored_name:
            raise HTTPException(400, "Geçersiz dosya adı")
        auth = request.headers.get("authorization", "")
        raw = auth[7:] if auth.startswith("Bearer ") else token
        if not raw:
            raise HTTPException(401, "Token gerekli")
        try:
            payload = decode_token(raw)
        except Exception:
            raise HTTPException(401, "Geçersiz veya süresi dolmuş token")
        # Sarmalanmamış erişim (2026-07-24 fail-closed düzeltmesi): bu iki
        # sorgu ContextVar set edilmeden ÖNCE çalışır — tenant_context.py
        # artık fail-closed olduğu için bağlamsız `db` sorgusu boş dönerdi
        # (tüm uydu görüntüleri 403/404 olurdu). Tenant eşleşmesi hemen
        # altta ELLE kontrol ediliyor (storage.py ile aynı desen).
        _unscoped = getattr(db, "_real_db", db)
        u = await _unscoped.users.find_one({"id": payload.get("user_id")}, {"_id": 0, "password": 0})
        if not u or u.get("active") is False:
            raise HTTPException(403, "Yetkisiz")
        img = await _unscoped.remote_sensing_images.find_one({"stored_name": stored_name}, {"_id": 0})
        if not img:
            raise HTTPException(404, "Görüntü bulunamadı")
        if u.get("role") != "platform_admin" and img.get("tenant_id") not in (None, payload.get("tenant_id")):
            raise HTTPException(404, "Görüntü bulunamadı")
        effective_tenant_id = img.get("tenant_id") or payload.get("tenant_id")
        reset_tok = current_tenant_id.set(effective_tenant_id)
        try:
            if not await is_feature_enabled(db, "remote_sensing"):
                raise HTTPException(403, f"'{FEATURE_FLAG_LABELS.get('remote_sensing', 'remote_sensing')}' özelliği bu kurum için kapatılmış")
        finally:
            current_tenant_id.reset(reset_tok)
        path = UPLOAD_DIR / "remote_sensing" / stored_name
        if not path.is_file():
            raise HTTPException(404, "Dosya bulunamadı")
        return FileResponse(path, media_type="image/png")

    # ---- AI Yorumlama (EOSDA/NDVI verisini anlamlandırır) --------------------
    @api_router.post("/remote-sensing/parcels/{parcel_id}/interpret")
    async def rs_interpret(parcel_id: str,
                           user=Depends(require_permission("remote_sensing:statistics")),
                           _feat=Depends(require_feature("remote_sensing"))):
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
        # 2026-08-19 — İKİ düzeltme birden:
        #  (1) Bu uç `get_ai_provider`'ı DOĞRUDAN çağırıyordu, yani yalnızca DIŞ
        #      API ile çalışıyor, yerel LLM (Ollama) yapılandırılmışsa AI yorumu
        #      hiç üretilmiyordu. Artık ai_router'ın hibrit yönlendiricisinden
        #      geçiyor (yerel/dış/hibrit strateji).
        #  (2) Çağrı `governed_generate()` üzerinden geçer — admin'in
        #      guardrail'leri ve RAG bilgi bankası burada da uygulanır.
        try:
            from ai_governance import governed_generate
            res = await governed_generate(
                db, "remote_sensing", _rs_ai_prompt(parcel, m, series),
                base_system_prompt=_AI_SYSTEM, use_rag=True, user=user,
            )
            if res.get("blocked"):
                ai_error = f"Guardrail: {res.get('blocked_by')}"
            elif res.get("error"):
                ai_error = str(res["error"])[:220]
            else:
                ai_text = res.get("answer")
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

    # ---- Google Earth Engine + NASA HLS (Faz 9C, 2026-07-25) ------------------
    # Ayrı bir domain (server.py'ye yeni kod eklenmez) ama AYNI api_router'a
    # bağlanır — literal `POST /v1/analyze-field` sözleşmesi bu şekilde
    # `/api` önekiyle birlikte `POST /api/v1/analyze-field` olarak dışa açılır.
    from .providers.gee_hls import register_gee_hls_routes
    register_gee_hls_routes(api_router, db, current_user, require_permission, log_audit, require_feature)
