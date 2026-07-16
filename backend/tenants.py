"""
=====================================================================
Toprax — Tenant (Kurum) Yönetimi
=====================================================================
Her kooperatif/kurum ayrı bir tenant olarak tanımlanır. Bu modül SADECE
"platform_admin" rolündeki kullanıcılar tarafından kullanılır — normal
kooperatif kullanıcıları (super_admin dahil) bu uçlara erişemez, onlar
zaten kendi tenant'larına otomatik olarak izole edilmiştir (bkz.
tenant_context.py).

ÖNEMLİ: Bu modül bilinçli olarak RAW (tenant-scoped OLMAYAN) db kullanır,
çünkü tenant oluşturma/listeleme doğası gereği tenant'lar-arası bir
işlemdir.
"""
import uuid
import re
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional


class TenantCreate(BaseModel):
    name: str                                   # "Konya Şeker Kooperatifi"
    slug: Optional[str] = None                  # boşsa isimden otomatik üretilir
    contact_email: str
    contact_phone: Optional[str] = None
    plan: str = "standard"                      # standard | kurumsal | deneme


class TenantStatusUpdate(BaseModel):
    status: str                                 # aktif | askida | pasif


class TenantAdminBootstrap(BaseModel):
    """Yeni tenant için ilk süper admin kullanıcısını oluşturur."""
    admin_email: str
    admin_password: str
    admin_full_name: str


def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9ğüşıöç\s-]", "", s)
    s = (s.replace("ğ", "g").replace("ü", "u").replace("ş", "s")
           .replace("ı", "i").replace("ö", "o").replace("ç", "c"))
    s = re.sub(r"\s+", "-", s.strip())
    return s[:60]


def register_tenant_routes(api_router, raw_db, current_user, hash_password, log_audit):
    """server.py'deki register_* pattern'i — raw_db burada BİLEREK
    tenant-scoped olmayan (ham) veritabanı referansıdır."""

    async def _require_platform_admin(user):
        if user.get("role") != "platform_admin":
            raise HTTPException(403, "Bu işlem sadece platform yöneticileri içindir")

    @api_router.get("/platform/tenants")
    async def list_tenants(user=Depends(current_user)):
        await _require_platform_admin(user)
        docs = await raw_db.tenants.find({}, {"_id": 0}).to_list(500)
        # Her tenant için kullanıcı sayısı gibi hafif bir özet ekle
        for t in docs:
            t["user_count"] = await raw_db.users.count_documents({"tenant_id": t["id"]})
            t["farmer_count"] = await raw_db.farmers.count_documents({"tenant_id": t["id"]})
        return docs

    @api_router.post("/platform/tenants")
    async def create_tenant(body: TenantCreate, request: Request, user=Depends(current_user)):
        await _require_platform_admin(user)
        slug = body.slug or _slugify(body.name)
        existing = await raw_db.tenants.find_one({"slug": slug})
        if existing:
            raise HTTPException(409, f"'{slug}' slug'ı zaten kullanımda")

        doc = {
            "id": str(uuid.uuid4()),
            "name": body.name,
            "slug": slug,
            "contact_email": body.contact_email,
            "contact_phone": body.contact_phone,
            "plan": body.plan,
            "status": "aktif",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.get("email"),
        }
        await raw_db.tenants.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(raw_db, user, action="create", entity="tenant", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/platform/tenants/{tenant_id}/status")
    async def update_tenant_status(tenant_id: str, body: TenantStatusUpdate, request: Request, user=Depends(current_user)):
        await _require_platform_admin(user)
        old = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Tenant bulunamadı")
        if body.status not in ("aktif", "askida", "pasif"):
            raise HTTPException(400, "Geçersiz durum (aktif|askida|pasif)")
        await raw_db.tenants.update_one({"id": tenant_id}, {"$set": {"status": body.status}})
        await log_audit(raw_db, user, action="update", entity="tenant", entity_id=tenant_id,
                         old_value=old, new_value={"status": body.status}, request=request)
        return {"status": "updated"}

    @api_router.post("/platform/tenants/{tenant_id}/bootstrap-admin")
    async def bootstrap_tenant_admin(tenant_id: str, body: TenantAdminBootstrap, request: Request, user=Depends(current_user)):
        """
        Yeni bir tenant'ın İLK süper admin kullanıcısını oluşturur. Bundan
        sonra o kullanıcı normal şekilde giriş yapıp kendi tenant'ının
        Ayarlar/Kullanıcılar ekranından diğer personeli ekleyebilir.
        """
        await _require_platform_admin(user)
        tenant = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        if not tenant:
            raise HTTPException(404, "Tenant bulunamadı")

        # P1 düzeltmesi: email artık GLOBAL değil tenant bazlı benzersiz
        # (bkz. server.py startup — users indexi (tenant_id, email) compound
        # oldu) — aynı e-posta farklı bir kurumda zaten kayıtlı olabilir,
        # kontrol SADECE hedef tenant'a göre yapılır.
        existing_user = await raw_db.users.find_one({"email": body.admin_email.lower(), "tenant_id": tenant_id})
        if existing_user:
            raise HTTPException(409, "Bu e-posta bu kurumda zaten kayıtlı")

        doc = {
            "id": str(uuid.uuid4()),
            "email": body.admin_email.lower(),
            "password": hash_password(body.admin_password),
            "full_name": body.admin_full_name,
            "role": "super_admin",
            "tenant_id": tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await raw_db.users.insert_one(doc)
        doc.pop("_id", None)
        doc.pop("password", None)
        await log_audit(raw_db, user, action="create", entity="tenant_admin", entity_id=doc["id"],
                         new_value={**doc}, request=request)
        return doc

    @api_router.get("/platform/tenants/{tenant_id}/stats")
    async def tenant_stats(tenant_id: str, user=Depends(current_user)):
        """Bir tenant'ın veri hacmi özeti — platform admin destek/faturalama için kullanır."""
        await _require_platform_admin(user)
        tenant = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        if not tenant:
            raise HTTPException(404, "Tenant bulunamadı")
        collections = ["users", "farmers", "parcels", "contracts", "iot_sensors", "drone_missions"]
        stats = {c: await getattr(raw_db, c).count_documents({"tenant_id": tenant_id}) for c in collections}
        return {"tenant": tenant, "stats": stats}
