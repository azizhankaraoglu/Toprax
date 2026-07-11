"""
=====================================================================
TabSIS — Platform Core: Feature Flags + Module Manifest + Licensing
İskeleti + Health Center (IT-33 / FAZ 11 TAMAMLANDI)
=====================================================================
Bu iterasyonun amacı yeni bir özellik DEĞİL, bundan sonraki her modülün
uyması gereken platform omurgasıdır (ROADMAP'in FAZ 11 girişindeki not).
Dört BİLİNÇLİ OLARAK aynı dosyada toplanan alt konu (IT-27'nin Communication
Policy+Tercih Merkezi+Kara Liste'yi tek dosyada topladığı emsalle AYNI —
hepsi tek bir IT'de doğdu ve birbirini tamamlıyor):

1) **Feature Flags** — tenant bazlı aç/kapa (`feature_flags` koleksiyonu).
   `is_feature_enabled(db, key)` + `make_require_feature(db)` (permissions.
   py'nin `make_require_permission` kalıbıyla AYNI factory deseni) —
   kapatılan bir flag ilgili endpoint'lerde GERÇEKTEN 403 döner (`extras.py`
   AI uçlarına, `lms.py`'nin bir kaç ucuna eklendi — TÜM endpoint'lere
   değil, roadmap'in "ilgili menü/API devre dışı kalıyor" kabul kriterini
   kanıtlayacak birer temsilci). WhatsApp gibi URL'i olmayan bir "kanal"
   için ayrıca `communications.py`'nin `send_via_channel`'ında kanal
   bazlı bir kontrol var (bkz. o dosyadaki IT-33 notu).
2) **Module Manifest** — `MODULE_MANIFESTS` sabit bir liste (yeni bir DB
   koleksiyonu İCAT EDİLMEDİ — `PERMISSION_CATALOG`/`INTEGRATION_REGISTRY`
   ile AYNI "kod-seviyesi registry" kalıbı, ROADMAP'in "Platform bunu
   otomatik okuyabilmeli" kriterini `GET /platform-core/module-manifests`
   ile karşılar).
3) **Licensing İskeleti** — `licenses` koleksiyonu (scope_type: module/
   tenant/user + plan + opsiyonel expires_at) + basit CRUD + `check_
   license()` yardımcı fonksiyonu. ROADMAP'in "sadece veri modeli + basit
   kontrol yeterli" notuyla tutarlı — hiçbir endpoint'e ZORUNLU olarak
   BAĞLANMADI (gerçek satış/faturalama entegrasyonu kapsam dışı).
4) **Health Center** — IT-01'in Integration Center'a eklediği `enabled`/
   `last_success_at` alanlarını (integrations.py) TÜKETİR, YENİDEN bir
   ağ çağrısı YAPMAZ (health-check zaten `GET /integrations/{type}/health`
   ile var — burası SON BİLİNEN durumun merkezi özeti). Redis/RabbitMQ/
   Elasticsearch/GeoServer bu ortamda KURULU DEĞİL (CLAUDE.md) — bunlar
   için "Hata" YERİNE dürüst bir 4. durum (`kurulu_degil`) döner, gerçek
   bir servis eksikliğiyle "kurulu değil, zaten böyle tasarlandı" arasındaki
   farkı karıştırmamak için.

Cache soyutlaması bu dosyada DEĞİL — ayrı, küçük, yeniden kullanılabilir
`cache.py`'de (permissions.py ve server.py'nin `/regions` ucu ORADAN
import eder, burada tekrar edilmedi).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List

FEATURE_FLAG_LABELS = {
    "ai": "Yapay Zeka (AI Copilot / Hastalık Tespiti)",
    "drone": "Drone Entegrasyonu",
    "whatsapp": "WhatsApp Kanalı",
    "lms": "Eğitim Merkezi (Farmer LMS)",
    "gis": "Coğrafi Bilgi Sistemi (Harita Paneli / Uydu)",
}

HEALTH_STATUS_LABELS = {"saglikli": "Sağlıklı", "uyari": "Uyarı", "hata": "Hata", "kurulu_degil": "Kurulu Değil"}

MODULE_MANIFESTS = [
    {
        "name": "Farmer", "version": "1.0.0", "dependencies": [],
        "menus": ["Çiftçiler"], "permissions": ["farmers:view", "farmers:create", "farmers:edit"],
        "events": [], "apis": ["/farmers", "/farmers/{id}"],
        "dashboard_components": ["Toplam Çiftçi widget'ı"],
    },
    {
        "name": "GIS", "version": "1.0.0", "dependencies": ["Farmer"],
        "menus": ["Harita Paneli", "İdari Alanlar"],
        "permissions": ["parcels:view", "admin_areas:view"],
        "events": [], "apis": ["/parcels", "/admin-areas", "/satellite/ndvi-snapshot"],
        "dashboard_components": ["Harita Paneli Widget Registry (8 referans widget)"],
    },
    {
        "name": "Farmer LMS", "version": "1.0.0", "dependencies": ["Farmer"],
        "menus": ["Eğitim Yönetimi"],
        "permissions": ["lms:catalog_view", "lms:catalog_manage", "lms:assign"],
        "events": [], "apis": ["/courses", "/lms/my-courses"],
        "dashboard_components": ["Eğitimlerim kartı (FarmerHome)"],
    },
]


async def is_feature_enabled(db, key: str) -> bool:
    """Flag hiç seed edilmemiş/bilinmeyen bir key ise varsayılan AÇIK döner
    (geriye dönük uyumluluk — yeni bir flag eklemek var olan davranışı
    aniden kapatmaz)."""
    doc = await db.feature_flags.find_one({"key": key}, {"_id": 0})
    if not doc:
        return True
    return doc.get("enabled", True)


def make_require_feature(db):
    """`permissions.make_require_permission` ile AYNI factory kalıbı."""
    def require_feature(key: str):
        async def _checker() -> bool:
            if not await is_feature_enabled(db, key):
                raise HTTPException(403, f"'{FEATURE_FLAG_LABELS.get(key, key)}' özelliği bu kurum için kapatılmış")
            return True
        return _checker
    return require_feature


async def check_license(db, scope_type: str, scope_value: str) -> bool:
    """Basit kontrol — lisans tanımlanmamışsa varsayılan SERBEST (bilinçli
    iskelet, gerçek satış/faturalama entegrasyonu kapsam dışı)."""
    doc = await db.licenses.find_one({"scope_type": scope_type, "scope_value": scope_value, "is_active": True}, {"_id": 0})
    if not doc:
        return True
    if doc.get("expires_at") and doc["expires_at"] < datetime.now(timezone.utc).isoformat():
        return False
    return True


class FeatureFlagUpdate(BaseModel):
    enabled: bool


class LicenseCreate(BaseModel):
    scope_type: str                    # module | tenant | user
    scope_value: str
    plan: str = "standard"             # trial | standard | premium
    expires_at: Optional[str] = None
    note: Optional[str] = None


class LicenseUpdate(BaseModel):
    plan: Optional[str] = None
    expires_at: Optional[str] = None
    is_active: Optional[bool] = None


async def _integration_status(db, itype: str) -> dict:
    """Integration Center'ın (integrations.py, IT-01) `enabled`/`last_
    success_at` alanlarını TÜKETİR — yeniden bir ağ çağrısı yapmaz (bkz.
    modül docstring'i, madde 4)."""
    doc = await db.integrations.find_one({"type": itype}, {"_id": 0})
    if not doc or not doc.get("enabled"):
        return {"status": "hata", "detail": "Yapılandırılmamış veya devre dışı"}
    if doc.get("last_success_at"):
        return {"status": "saglikli", "detail": f"Son başarılı bağlantı: {doc['last_success_at']}"}
    return {"status": "uyari", "detail": "Yapılandırılmış ama henüz hiç test edilmemiş"}


def register_platform_core_routes(api_router, db, current_user, require_permission, log_audit):

    # ---------------- Feature Flags ----------------
    @api_router.get("/feature-flags")
    async def list_feature_flags(user=Depends(require_permission("platform_core:view"))):
        docs = await db.feature_flags.find({}, {"_id": 0}).to_list(100)
        by_key = {d["key"]: d for d in docs}
        return [
            {"key": k, "label": label, "enabled": by_key.get(k, {}).get("enabled", True)}
            for k, label in FEATURE_FLAG_LABELS.items()
        ]

    @api_router.post("/feature-flags/seed-defaults")
    async def seed_feature_flags(user=Depends(require_permission("platform_core:manage"))):
        created = 0
        for key in FEATURE_FLAG_LABELS:
            existing = await db.feature_flags.find_one({"key": key})
            if existing:
                continue
            await db.feature_flags.insert_one({
                "id": str(uuid.uuid4()), "key": key, "enabled": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            created += 1
        return {"status": "seeded", "created": created}

    @api_router.put("/feature-flags/{key}")
    async def update_feature_flag(key: str, body: FeatureFlagUpdate, request: Request,
                                   user=Depends(require_permission("platform_core:manage"))):
        if key not in FEATURE_FLAG_LABELS:
            raise HTTPException(404, f"Bilinmeyen özellik: {key}")
        old = await db.feature_flags.find_one({"key": key}, {"_id": 0})
        await db.feature_flags.update_one(
            {"key": key}, {"$set": {"enabled": body.enabled, "updated_at": datetime.now(timezone.utc).isoformat(),
                                     "updated_by": user.get("full_name") or user.get("email")}},
            upsert=True,
        )
        new = await db.feature_flags.find_one({"key": key}, {"_id": 0})
        await log_audit(db, user, action="update", entity="feature_flag", entity_id=key, old_value=old, new_value=new, request=request)
        return new

    # ---------------- Module Manifest ----------------
    @api_router.get("/platform-core/module-manifests")
    async def list_module_manifests(user=Depends(require_permission("platform_core:view"))):
        return MODULE_MANIFESTS

    # ---------------- Licensing İskeleti ----------------
    @api_router.get("/licenses")
    async def list_licenses(user=Depends(require_permission("platform_core:view"))):
        return await db.licenses.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/licenses")
    async def create_license(body: LicenseCreate, request: Request,
                              user=Depends(require_permission("platform_core:manage"))):
        if body.scope_type not in ("module", "tenant", "user"):
            raise HTTPException(400, f"Geçersiz scope_type: {body.scope_type}")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.licenses.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="license", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/licenses/{license_id}")
    async def update_license(license_id: str, body: LicenseUpdate, request: Request,
                              user=Depends(require_permission("platform_core:manage"))):
        old = await db.licenses.find_one({"id": license_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Lisans bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.licenses.update_one({"id": license_id}, {"$set": updates})
        new = await db.licenses.find_one({"id": license_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="license", entity_id=license_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/licenses/{license_id}")
    async def delete_license(license_id: str, request: Request,
                              user=Depends(require_permission("platform_core:manage"))):
        old = await db.licenses.find_one({"id": license_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Lisans bulunamadı")
        await db.licenses.update_one({"id": license_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="deactivate", entity="license", entity_id=license_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # ---------------- Health Center ----------------
    @api_router.get("/platform-core/health")
    async def health_center(user=Depends(require_permission("platform_core:view"))):
        try:
            await db.regions.count_documents({})
            db_status = {"status": "saglikli", "detail": "MongoDB bağlantısı çalışıyor"}
        except Exception as e:
            db_status = {"status": "hata", "detail": str(e)}

        results = [
            {"service": "database", "label": "MongoDB", **db_status},
            {"service": "ai_service", "label": "AI Provider", **(await _integration_status(db, "ai_service"))},
            {"service": "sms", "label": "SMS Sağlayıcı", **(await _integration_status(db, "sms"))},
            {"service": "email", "label": "E-Posta Sağlayıcı", **(await _integration_status(db, "email"))},
            {"service": "planet_labs", "label": "Uydu Sağlayıcı (Planet Labs)", **(await _integration_status(db, "planet_labs"))},
            {"service": "whatsapp", "label": "WhatsApp Sağlayıcı", "status": "kurulu_degil",
             "detail": "Şimdilik simüle kanal (channel_providers.py) — gerçek sağlayıcı henüz bağlı değil"},
            {"service": "redis", "label": "Redis", "status": "kurulu_degil",
             "detail": "Bu ortamda kurulu değil — in-process cache kullanılıyor (bkz. cache.py)"},
            {"service": "rabbitmq", "label": "RabbitMQ", "status": "kurulu_degil",
             "detail": "Bu ortamda kurulu değil — in-process event bus kullanılıyor (bkz. event_bus.py)"},
            {"service": "elasticsearch", "label": "Elasticsearch", "status": "kurulu_degil",
             "detail": "Bu ortamda kurulu değil — MongoDB sorguları kullanılıyor"},
            {"service": "geoserver", "label": "GeoServer", "status": "kurulu_degil",
             "detail": "Bu ortamda kurulu değil — react-leaflet + genel XYZ servisleri kullanılıyor"},
        ]
        for r in results:
            r["status_label"] = HEALTH_STATUS_LABELS.get(r["status"], r["status"])
        return results
