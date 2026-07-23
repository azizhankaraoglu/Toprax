"""
=====================================================================
Toprax — Kullanıcı (Personel) Yönetimi (Sprint 4d)
=====================================================================
Rolleri/izinleri KİŞİLERE atayabilmek için gereken CRUD. Öncesinde
sistemde hiç kullanıcı listeleme/oluşturma endpoint'i yoktu — sadece
ilk seed ile gelen sabit demo kullanıcılar ve çiftçiye bağlı hesaplar
vardı. Artık bir yönetici burada:
  - Yeni personel hesabı açabilir (kantar personeli, ziraat mühendisi vb.)
  - Var olan birinin rolünü değiştirebilir
  - Birine, rolünün ÜZERİNE ek izin verebilir veya rolünden izin kısabilir
  - Birini pasif hale getirebilir (login edemez olur — veri geçmişi silinmez)
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List
from config_service import ROLE_HIERARCHY, ROLE_LABELS


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str                                  # config.ROLE_HIERARCHY'deki bir rol
    phone: Optional[str] = None


class UserRoleUpdate(BaseModel):
    role: Optional[str] = None                 # built-in rol
    custom_role_id: Optional[str] = None        # verilirse built-in rolün YERİNE kullanılır (null geçmek için "" gönderin)
    grant: List[str] = []                       # role/custom_role'e EK izinler
    revoke: List[str] = []                      # role/custom_role'den çıkarılacak izinler


class UserStatusUpdate(BaseModel):
    active: bool


# SON HAL — Profil sayfası (kullanıcının KENDİ hesabı; izin gerektirmez,
# sadece current_user — support.py'nin /portal/* sahiplik deseniyle aynı ruh)
class MyProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    # SON HAL #10 — kullanıcının seçtiği renk bloğu (frontend/src/lib/theme.js
    # ACCENT_PRESETS anahtarlarından biri, örn. "mavi"). Sunucuda saklanır ki
    # "her girişte kendi seçtiği renk bloğu gelsin" gereksinimi karşılansın
    # (sadece localStorage değil — başka bir cihazda giriş yapınca da uygulanır).
    accent_color: Optional[str] = None


class MyPasswordUpdate(BaseModel):
    current_password: str
    new_password: str


def register_user_routes(api_router, db, current_user, require_permission, hash_password, log_audit):

    # =================================================================
    # SON HAL — PROFİL (kendi hesabım). /users/* yönetici uçlarından AYRI:
    # izin GEREKTİRMEZ, kullanıcı SADECE kendi kaydını görür/değiştirir.
    # E-posta ve rol buradan DEĞİŞTİRİLEMEZ (e-posta login anahtarı +
    # tenant-unique index; rol değişimi yönetici işi — /users/{id}/role).
    # =================================================================
    @api_router.get("/me/profile")
    async def get_my_profile(user=Depends(current_user)):
        doc = await db.users.find_one(
            {"id": user["id"]}, {"_id": 0, "password": 0, "totp_secret": 0})
        if not doc:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        return doc

    @api_router.put("/me/profile")
    async def update_my_profile(body: MyProfileUpdate, request: Request,
                                user=Depends(current_user)):
        old = await db.users.find_one(
            {"id": user["id"]}, {"_id": 0, "password": 0, "totp_secret": 0})
        if not old:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        updates = {}
        if body.full_name is not None and body.full_name.strip():
            updates["full_name"] = body.full_name.strip()
        if body.phone is not None:
            updates["phone"] = body.phone.strip() or None
        if body.accent_color is not None:
            updates["accent_color"] = body.accent_color.strip()[:30] or None
        if updates:
            await db.users.update_one({"id": user["id"]}, {"$set": updates})
        new = await db.users.find_one(
            {"id": user["id"]}, {"_id": 0, "password": 0, "totp_secret": 0})
        await log_audit(db, user, action="update_profile", entity="user",
                        entity_id=user["id"], old_value=old, new_value=new, request=request)
        return new

    @api_router.put("/me/password")
    async def update_my_password(body: MyPasswordUpdate, request: Request,
                                 user=Depends(current_user)):
        from security import verify_password
        doc = await db.users.find_one({"id": user["id"]})
        if not doc:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        if not verify_password(body.current_password, doc.get("password", "")):
            # Audit'e başarısız deneme de düşülür (yanlış mevcut şifre)
            await log_audit(db, user, action="password_change_failed", entity="user",
                            entity_id=user["id"], request=request)
            raise HTTPException(400, "Mevcut şifre hatalı")
        if len(body.new_password) < 8:
            raise HTTPException(400, "Yeni şifre en az 8 karakter olmalı")
        await db.users.update_one(
            {"id": user["id"]}, {"$set": {"password": hash_password(body.new_password)}})
        await log_audit(db, user, action="password_changed", entity="user",
                        entity_id=user["id"], request=request)
        return {"status": "updated"}

    @api_router.get("/users")
    async def list_users(user=Depends(require_permission("settings:users_view"))):
        docs = await db.users.find({}, {"_id": 0, "password": 0, "totp_secret": 0}).to_list(500)
        return docs

    @api_router.get("/users/roles")
    async def list_available_roles(user=Depends(require_permission("settings:users_view"))):
        """Built-in roller + tenant'ın custom rolleri — kullanıcı ekleme/düzenleme formunda seçim için."""
        custom = await db.custom_roles.find({}, {"_id": 0}).to_list(100)
        built_in = [{"key": k, "label": ROLE_LABELS.get(k, k), "level": v} for k, v in ROLE_HIERARCHY.items()]
        return {"built_in": built_in, "custom": custom}

    @api_router.post("/users")
    async def create_user(body: UserCreate, request: Request, user=Depends(require_permission("settings:users_manage"))):
        if body.role not in ROLE_HIERARCHY:
            raise HTTPException(400, f"Geçersiz rol: {body.role}")
        existing = await db.users.find_one({"email": body.email.lower()})
        if existing:
            raise HTTPException(409, "Bu e-posta zaten kayıtlı")

        from platform_core import check_and_consume_limit
        active_count = await db.users.count_documents({"active": {"$ne": False}})
        await check_and_consume_limit(db, user.get("tenant_id"), "user_limit", active_count, "Kullanıcı")

        doc = {
            "id": str(uuid.uuid4()),
            "email": body.email.lower(),
            "password": hash_password(body.password),
            "full_name": body.full_name,
            "phone": body.phone,
            "role": body.role,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.get("email"),
        }
        await db.users.insert_one(doc)
        doc.pop("_id", None)
        doc.pop("password", None)
        await log_audit(db, user, action="create", entity="user", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/users/{user_id}/role")
    async def update_user_role(user_id: str, body: UserRoleUpdate, request: Request,
                                user=Depends(require_permission("settings:users_manage"))):
        old = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0, "totp_secret": 0})
        if not old:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        if body.role and body.role not in ROLE_HIERARCHY:
            raise HTTPException(400, f"Geçersiz rol: {body.role}")

        updates = {}
        if body.role:
            updates["role"] = body.role
            updates["custom_role_id"] = None   # built-in rol seçildiyse custom rol temizlenir
        if body.custom_role_id:
            custom = await db.custom_roles.find_one({"id": body.custom_role_id})
            if not custom:
                raise HTTPException(404, "Özel rol bulunamadı")
            updates["custom_role_id"] = body.custom_role_id
        updates["permission_overrides"] = {"grant": body.grant, "revoke": body.revoke}

        await db.users.update_one({"id": user_id}, {"$set": updates})
        new = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0, "totp_secret": 0})
        await log_audit(db, user, action="update_role", entity="user", entity_id=user_id,
                         old_value=old, new_value=new, request=request)
        # IT-33 — get_effective_permissions 30sn cache'liyor (bkz. permissions.py);
        # rol değişikliği TTL'nin dolmasını beklemeden ANINDA yansımalı.
        from cache import cache_invalidate_prefix
        cache_invalidate_prefix(f"perms:{user_id}:")
        return new

    @api_router.put("/users/{user_id}/status")
    async def update_user_status(user_id: str, body: UserStatusUpdate, request: Request,
                                  user=Depends(require_permission("settings:users_manage"))):
        old = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0, "totp_secret": 0})
        if not old:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        if user_id == user.get("id") and not body.active:
            raise HTTPException(400, "Kendi hesabınızı pasif yapamazsınız")
        await db.users.update_one({"id": user_id}, {"$set": {"active": body.active}})
        await log_audit(db, user, action="update_status", entity="user", entity_id=user_id,
                         old_value={"active": old.get("active", True)}, new_value={"active": body.active}, request=request)
        return {"status": "updated", "active": body.active}
