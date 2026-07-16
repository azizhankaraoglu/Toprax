"""
=====================================================================
Toprax — God Mode (Platform Admin genişletmesi, Faz 1 + Faz 2)
=====================================================================
`tenants.py`'nin (platform_admin-only, ham/raw_db kullanan) AYNI
felsefesinin devamı — burada TEK bir platform_admin hesabının
(`azizhan@azizhan.com.tr`, gerçek TOTP ile korunur) ihtiyaç duyduğu
üst-düzey kontrol paneli toplanır:

1) **Tenant olarak gir** — o tenant'ın en yetkili AKTİF kullanıcısı
   adına bir access token üretir (gerçek bir "impersonation" — yeni
   bir kullanıcı YARATMAZ, var olanı kullanır); audit_logs'a hem
   platform admin'in hem hedef tenant'ın izini bırakır.
2) **Tenant sil** — convention #3 (hiçbir kayıt fiziksel silinmez)
   gereği GERÇEK silme değil, `status="silindi"` + `deleted_at/by` —
   "askıya al"dan (geri açılabilir) bilinçli olarak AYRI, kalıcı bir
   son durumdur (varsayılan listede görünmez, `include_deleted=true`
   ile geri getirilebilir arşiv görünümü).
3) **Tenant sağlık + kullanım istatistikleri** — `audit_logs`'taki
   son "login" kaydından `last_active_at`, veri hacmi sayaçları.
4) **Modül Yönetimi** — `platform_core.py`'nin `feature_flags`
   koleksiyonunu (TenantScopedDB'nin normal tenant-içi kullanımıyla
   AYNI koleksiyon) raw_db ile tenant_id EXPLICIT vererek yönetir —
   platform_admin'in kendi context'inde tenant_id olmadığından
   context-var'lı otomatik filtreye güvenilemez (bkz. tenant_context.py).
5) **God Mode istatistik dashboard'u** — kullanıcı/veri/iletişim/
   güvenlik sayaçları, TÜM tenant'lar toplamında (raw_db, filtresiz).
6) **Sistem sağlığı (Faz 2)** — `psutil` ile gerçek CPU/RAM/disk;
   `platform_core.py`'nin Health Center'ıyla KARIŞTIRILMAZ, o ayrı
   kalır (entegrasyon durumları), bu SADECE işletim sistemi metrikleri.
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from security import make_access_token
from platform_core import get_tenant_license, LicenseUpdate


class TenantLicenseCreate(BaseModel):
    """`platform_core.LicenseCreate`'in scope_type/scope_value İSTEMEYEN
    hafif karşılığı — bu uçta hedef tenant zaten URL'den geliyor, scope
    God Mode tarafından OTOMATİK set edilir (bkz. create_tenant_license)."""
    plan: str = "standard"
    expires_at: Optional[str] = None
    note: Optional[str] = None
    user_limit: Optional[int] = None
    parcel_limit: Optional[int] = None
    storage_limit_mb: Optional[int] = None
    ai_limit: Optional[int] = None
    sms_limit: Optional[int] = None
    whatsapp_limit: Optional[int] = None

# God Mode'un yönettiği "Modül Yönetimi" — platform_core.py'nin kendi
# FEATURE_FLAG_LABELS'ından (ai/gis/lms) BİLİNÇLİ OLARAK ayrı bir sözlük
# DEĞİL, AYNI `feature_flags` koleksiyonunu (tenant_id+key) kullanır —
# ai/gis/lms anahtarları platform_core.py ile ORTAK (tek kaynak), geri
# kalan 6'sı (farmer/parcel/production/factory/ufyd/communication) burada
# ilk kez tanımlanır.
MODULE_TOGGLE_LABELS = {
    "farmer": "Çiftçi Yönetimi",
    "parcel": "Parsel / GIS Veri Girişi",
    "production": "Üretim Sezonu",
    "factory": "Fabrika / Kantar Operasyonları",
    "ufyd": "UFYD (Destek / Ledger / Hakediş)",
    "communication": "İletişim Merkezi",
    "lms": "Eğitim Merkezi (LMS)",
    "gis": "Harita Paneli",
    "ai": "Yapay Zeka",
}


async def _require_platform_admin(user):
    if user.get("role") != "platform_admin":
        raise HTTPException(403, "Bu işlem sadece platform yöneticileri içindir")


async def _last_login_at(raw_db, tenant_id: str) -> Optional[str]:
    doc = await raw_db.audit_logs.find_one(
        {"tenant_id": tenant_id, "action": "login"}, {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )
    return doc.get("created_at") if doc else None


def register_god_mode_routes(api_router, raw_db, current_user, log_audit):

    # ================= 1) Tenant Yönetimi (genişletilmiş liste) =================
    @api_router.get("/god-mode/tenants")
    async def list_tenants_extended(include_deleted: bool = False, user=Depends(current_user)):
        await _require_platform_admin(user)
        q = {} if include_deleted else {"status": {"$ne": "silindi"}}
        docs = await raw_db.tenants.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
        for t in docs:
            tid = t["id"]
            t["user_count"] = await raw_db.users.count_documents({"tenant_id": tid})
            t["active_user_count"] = await raw_db.users.count_documents({"tenant_id": tid, "active": {"$ne": False}})
            t["farmer_count"] = await raw_db.farmers.count_documents({"tenant_id": tid})
            t["parcel_count"] = await raw_db.parcels.count_documents({"tenant_id": tid})
            last_login = await _last_login_at(raw_db, tid)
            t["last_active_at"] = last_login
            t["is_healthy"] = bool(
                last_login and
                datetime.fromisoformat(last_login) > datetime.now(timezone.utc) - timedelta(days=30)
            ) if last_login else False
            lic = await raw_db.licenses.find_one(
                {"scope_type": "tenant", "scope_value": tid, "is_active": True}, {"_id": 0}
            )
            t["license"] = lic
            t["license_expiring_soon"] = bool(
                lic and lic.get("expires_at") and
                datetime.fromisoformat(lic["expires_at"]) < datetime.now(timezone.utc) + timedelta(days=14)
            ) if lic else False
        return docs

    # ================= 2) Tenant sil (soft) =================
    @api_router.delete("/god-mode/tenants/{tenant_id}")
    async def delete_tenant(tenant_id: str, request: Request, user=Depends(current_user)):
        """Kalıcı bir son durum — `status="silindi"`. "Askıya Al"ın aksine
        geri açma ekranı YOK (bilinçli — silme kararı geri döndürülebilir
        olsaydı "askıya al"dan farkı kalmazdı); veri fiziksel olarak
        SİLİNMEZ, sadece tenant listede görünmez olur (convention #3)."""
        await _require_platform_admin(user)
        old = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Tenant bulunamadı")
        await raw_db.tenants.update_one({"id": tenant_id}, {"$set": {
            "status": "silindi",
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user.get("email"),
        }})
        await log_audit(raw_db, user, action="delete", entity="tenant", entity_id=tenant_id,
                         old_value=old, request=request)
        return {"status": "deleted"}

    # ================= 3) Tenant olarak gir (impersonation) =================
    @api_router.post("/god-mode/tenants/{tenant_id}/enter")
    async def enter_tenant(tenant_id: str, request: Request, user=Depends(current_user)):
        """O tenant'ın en yetkili AKTİF kullanıcısı (önce super_admin, yoksa
        rol seviyesine göre en üst) adına GERÇEK bir access token üretir —
        yeni bir hesap YARATMAZ. Tenant'ta hiç kullanıcı yoksa 404 (önce
        `İlk Admini Oluştur` kullanılmalı)."""
        await _require_platform_admin(user)
        tenant = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        if not tenant:
            raise HTTPException(404, "Tenant bulunamadı")

        from config_service import ROLE_HIERARCHY
        candidates = await raw_db.users.find(
            {"tenant_id": tenant_id, "active": {"$ne": False}}, {"_id": 0, "password": 0, "totp_secret": 0}
        ).to_list(500)
        if not candidates:
            raise HTTPException(404, "Bu tenant'ta henüz aktif bir kullanıcı yok — önce 'İlk Admini Oluştur'")
        candidates.sort(key=lambda u: ROLE_HIERARCHY.get(u.get("role"), 99))
        target = candidates[0]

        token = make_access_token(target["id"], target["role"], target.get("farmer_id"), tenant_id)
        await log_audit(raw_db, user, action="god_mode_impersonate", entity="tenant", entity_id=tenant_id,
                         new_value={"impersonated_user_id": target["id"], "impersonated_email": target.get("email")},
                         request=request)
        return {"token": token, "access_token": token, "user": target, "tenant": tenant}

    # ================= 4) Modül Yönetimi (tenant bazlı) =================
    @api_router.get("/god-mode/tenants/{tenant_id}/modules")
    async def get_tenant_modules(tenant_id: str, user=Depends(current_user)):
        await _require_platform_admin(user)
        docs = await raw_db.feature_flags.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(50)
        by_key = {d["key"]: d for d in docs}
        return [
            {"key": k, "label": label, "enabled": by_key.get(k, {}).get("enabled", True)}
            for k, label in MODULE_TOGGLE_LABELS.items()
        ]

    class ModuleToggle(BaseModel):
        enabled: bool

    @api_router.put("/god-mode/tenants/{tenant_id}/modules/{key}")
    async def set_tenant_module(tenant_id: str, key: str, body: ModuleToggle, request: Request,
                                 user=Depends(current_user)):
        await _require_platform_admin(user)
        if key not in MODULE_TOGGLE_LABELS:
            raise HTTPException(404, f"Bilinmeyen modül: {key}")
        old = await raw_db.feature_flags.find_one({"tenant_id": tenant_id, "key": key}, {"_id": 0})
        await raw_db.feature_flags.update_one(
            {"tenant_id": tenant_id, "key": key},
            {"$set": {"enabled": body.enabled, "updated_at": datetime.now(timezone.utc).isoformat(),
                      "updated_by": user.get("email")},
             "$setOnInsert": {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "key": key}},
            upsert=True,
        )
        new = await raw_db.feature_flags.find_one({"tenant_id": tenant_id, "key": key}, {"_id": 0})
        await log_audit(raw_db, user, action="update", entity="tenant_module", entity_id=f"{tenant_id}:{key}",
                         old_value=old, new_value=new, request=request)
        return new

    # ================= 5) Tenant Lisansı (God Mode-only, limitli) =================
    @api_router.get("/god-mode/tenants/{tenant_id}/license")
    async def get_tenant_license_gm(tenant_id: str, user=Depends(current_user)):
        await _require_platform_admin(user)
        lic = await raw_db.licenses.find_one(
            {"scope_type": "tenant", "scope_value": tenant_id, "is_active": True}, {"_id": 0}
        )
        if not lic:
            return None
        usage = {
            "user_count": await raw_db.users.count_documents({"tenant_id": tenant_id, "active": {"$ne": False}}),
            "parcel_count": await raw_db.parcels.count_documents({"tenant_id": tenant_id}),
        }
        agg = await raw_db.uploads.aggregate([
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": None, "total_bytes": {"$sum": "$size_bytes"}}},
        ]).to_list(1)
        usage["storage_mb"] = round((agg[0]["total_bytes"] if agg else 0) / (1024 * 1024), 2)
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        usage["ai_count_this_month"] = await raw_db.ai_usage_logs.count_documents(
            {"tenant_id": tenant_id, "created_at": {"$gte": month_start}}
        )
        usage["sms_count_this_month"] = await raw_db.communications.count_documents(
            {"tenant_id": tenant_id, "channel": "sms", "sent_at": {"$gte": month_start}}
        )
        usage["whatsapp_count_this_month"] = await raw_db.communications.count_documents(
            {"tenant_id": tenant_id, "channel": "whatsapp", "sent_at": {"$gte": month_start}}
        )
        return {"license": lic, "usage": usage}

    @api_router.post("/god-mode/tenants/{tenant_id}/license")
    async def create_tenant_license(tenant_id: str, body: TenantLicenseCreate, request: Request,
                                     user=Depends(current_user)):
        await _require_platform_admin(user)
        tenant = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        if not tenant:
            raise HTTPException(404, "Tenant bulunamadı")
        existing = await raw_db.licenses.find_one(
            {"scope_type": "tenant", "scope_value": tenant_id, "is_active": True}
        )
        if existing:
            raise HTTPException(409, "Bu tenant için zaten aktif bir lisans var — güncellemek için PUT kullanın")
        doc = body.model_dump()
        doc["scope_type"] = "tenant"
        doc["scope_value"] = tenant_id
        doc["tenant_id"] = tenant_id       # bkz. platform_core.get_tenant_license — normal db üzerinden okunabilsin diye
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await raw_db.licenses.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(raw_db, user, action="create", entity="license", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/god-mode/tenants/{tenant_id}/license")
    async def update_tenant_license(tenant_id: str, body: LicenseUpdate, request: Request,
                                     user=Depends(current_user)):
        await _require_platform_admin(user)
        old = await raw_db.licenses.find_one(
            {"scope_type": "tenant", "scope_value": tenant_id, "is_active": True}, {"_id": 0}
        )
        if not old:
            raise HTTPException(404, "Bu tenant için aktif bir lisans yok — önce oluşturun")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await raw_db.licenses.update_one({"id": old["id"]}, {"$set": updates})
        new = await raw_db.licenses.find_one({"id": old["id"]}, {"_id": 0})
        await log_audit(raw_db, user, action="update", entity="license", entity_id=old["id"],
                         old_value=old, new_value=new, request=request)
        return new

    # ================= 6) God Mode İstatistik Dashboard'u (Faz 1) =================
    @api_router.get("/god-mode/stats")
    async def god_mode_stats(user=Depends(current_user)):
        await _require_platform_admin(user)
        now = datetime.now(timezone.utc)
        since_30d = (now - timedelta(days=30)).isoformat()
        since_1d = (now - timedelta(days=1)).isoformat()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        tenants_total = await raw_db.tenants.count_documents({})
        tenants_active = await raw_db.tenants.count_documents({"status": "aktif"})
        tenants_suspended = await raw_db.tenants.count_documents({"status": "askida"})
        tenants_deleted = await raw_db.tenants.count_documents({"status": "silindi"})
        tenants_trial = await raw_db.tenants.count_documents({"plan": "deneme", "status": {"$ne": "silindi"}})
        active_licenses = await raw_db.licenses.find(
            {"scope_type": "tenant", "is_active": True, "expires_at": {"$ne": None}}, {"_id": 0}
        ).to_list(500)
        expired = sum(1 for l in active_licenses if l["expires_at"] < now.isoformat())
        expiring_soon = sum(1 for l in active_licenses
                             if now.isoformat() <= l["expires_at"] < (now + timedelta(days=14)).isoformat())

        users_total = await raw_db.users.count_documents({})
        users_active = await raw_db.users.count_documents({"active": {"$ne": False}})
        users_inactive = users_total - users_active
        logins_30d = await raw_db.audit_logs.distinct("user_id", {"action": "login", "created_at": {"$gte": since_30d}})
        logins_1d = await raw_db.audit_logs.distinct("user_id", {"action": "login", "created_at": {"$gte": since_1d}})
        mau = len([u for u in logins_30d if u])
        dau = len([u for u in logins_1d if u])

        data_counts = {
            "farmers": await raw_db.farmers.count_documents({}),
            "parcels": await raw_db.parcels.count_documents({}),
            "production_cycles": await raw_db.production_cycles.count_documents({}),
            "contracts": await raw_db.contracts.count_documents({}),
            "entitlements": await raw_db.entitlements.count_documents({}),
            "tasks": (await raw_db.tasks.count_documents({})) + (await raw_db.field_tasks.count_documents({})),
            "form_responses": await raw_db.form_responses.count_documents({}),
            "uploads": await raw_db.uploads.count_documents({}),
        }
        storage_agg = await raw_db.uploads.aggregate(
            [{"$group": {"_id": None, "total_bytes": {"$sum": "$size_bytes"}}}]
        ).to_list(1)
        data_counts["storage_mb"] = round((storage_agg[0]["total_bytes"] if storage_agg else 0) / (1024 * 1024), 2)

        comm_agg = await raw_db.communications.aggregate([
            {"$group": {"_id": {"channel": "$channel", "status": "$status"}, "count": {"$sum": 1}}}
        ]).to_list(200)
        communications = {}
        for row in comm_agg:
            ch = row["_id"]["channel"]
            communications.setdefault(ch, {"sent": 0, "failed": 0})
            if row["_id"]["status"] == "teslim_edildi":
                communications[ch]["sent"] += row["count"]
            else:
                communications[ch]["failed"] += row["count"]

        security = {
            "successful_logins_30d": await raw_db.audit_logs.count_documents(
                {"action": "login", "created_at": {"$gte": since_30d}}),
            "failed_logins_30d": await raw_db.audit_logs.count_documents(
                {"action": {"$in": ["login_failed", "login_failed_totp"]}, "created_at": {"$gte": since_30d}}),
            "audit_log_count": await raw_db.audit_logs.count_documents({}),
        }
        from auth_lockout import _locked_until
        security["locked_accounts_now"] = len(_locked_until)

        ai_usage = {
            "total_requests": await raw_db.ai_usage_logs.count_documents({}),
            "requests_this_month": await raw_db.ai_usage_logs.count_documents({"created_at": {"$gte": month_start}}),
        }
        ai_by_feature = await raw_db.ai_usage_logs.aggregate(
            [{"$group": {"_id": "$feature", "count": {"$sum": 1}}}]
        ).to_list(20)
        ai_usage["by_feature"] = {r["_id"]: r["count"] for r in ai_by_feature}

        return {
            "tenants": {
                "total": tenants_total, "active": tenants_active, "suspended": tenants_suspended,
                "deleted": tenants_deleted, "trial": tenants_trial,
                "license_expired": expired, "license_expiring_soon": expiring_soon,
            },
            "users": {
                "total": users_total, "active": users_active, "inactive": users_inactive,
                "logged_in_last_30d": mau, "dau": dau, "mau": mau,
            },
            "data": data_counts,
            "communications": communications,
            "security": security,
            "ai_usage": ai_usage,
        }

    # ================= 7) Sistem Sağlığı (Faz 2 — gerçek OS metrikleri) =================
    @api_router.get("/god-mode/system-health")
    async def system_health(user=Depends(current_user)):
        await _require_platform_admin(user)
        try:
            import psutil
            disk = psutil.disk_usage(".")
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.3),
                "ram_percent": psutil.virtual_memory().percent,
                "ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024), 1),
                "ram_total_mb": round(psutil.virtual_memory().total / (1024 * 1024), 1),
                "disk_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024 ** 3), 1),
                "disk_total_gb": round(disk.total / (1024 ** 3), 1),
                "process_count": len(psutil.pids()),
            }
        except Exception as e:  # noqa: BLE001 — psutil kurulu değil/erişim sorunu, dürüstçe bildir
            return {"error": str(e)}

    # ================= 8) API çağrı istatistikleri (Faz 2) =================
    @api_router.get("/god-mode/api-stats")
    async def api_stats(user=Depends(current_user)):
        await _require_platform_admin(user)
        total = await raw_db.api_call_logs.count_documents({})
        if total == 0:
            return {"total": 0, "success": 0, "error": 0, "avg_duration_ms": 0, "top_paths": [], "top_errors": []}
        success = await raw_db.api_call_logs.count_documents({"status_code": {"$lt": 400}})
        avg_agg = await raw_db.api_call_logs.aggregate(
            [{"$group": {"_id": None, "avg": {"$avg": "$duration_ms"}}}]
        ).to_list(1)
        top_paths = await raw_db.api_call_logs.aggregate([
            {"$group": {"_id": "$path", "count": {"$sum": 1}, "avg_ms": {"$avg": "$duration_ms"}}},
            {"$sort": {"count": -1}}, {"$limit": 10},
        ]).to_list(10)
        top_errors = await raw_db.api_call_logs.aggregate([
            {"$match": {"status_code": {"$gte": 400}}},
            {"$group": {"_id": {"path": "$path", "status": "$status_code"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}, {"$limit": 10},
        ]).to_list(10)
        return {
            "total": total, "success": success, "error": total - success,
            "avg_duration_ms": round(avg_agg[0]["avg"], 1) if avg_agg else 0,
            "top_paths": [{"path": r["_id"], "count": r["count"], "avg_ms": round(r["avg_ms"], 1)} for r in top_paths],
            "top_errors": [{"path": r["_id"]["path"], "status": r["_id"]["status"], "count": r["count"]} for r in top_errors],
        }
