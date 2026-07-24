"""
=====================================================================
Toprax — Auth Endpoint'leri (login/refresh/me/public-contact)
=====================================================================
Denetim A6 (2026-07-24): server.py (~2900 satır) modülerleştirmesi —
bu dosyadaki endpoint'ler server.py'den BİREBİR taşındı, davranış
değişikliği YOK. Route kayıt SIRASI korunur: register çağrısı server.py
içinde bloğun orijinal konumundan yapılır (Starlette route-order tuzağı,
bkz. CLAUDE.md /parcels/bulk-update notu).
"""
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
import jwt
from security import make_access_token, make_refresh_token, decode_token, hash_password, verify_password, needs_rehash
from totp import verify_totp
from auth_lockout import is_locked, record_failed_attempt, record_successful_login
from public_contact import resolve_bootstrap_tenant, create_public_contact_case
from tenant_context import current_tenant_id


class LoginReq(BaseModel):
    """Login endpoint'i için body şeması"""
    email: str
    password: str
    totp_code: Optional[str] = None   # SADECE totp_enabled=True hesaplarda (God Mode) zorunlu


class RefreshTokenReq(BaseModel):
    """Refresh token endpoint'i için body şeması"""
    refresh_token: str


class PublicContactRequest(BaseModel):
    """Giriş sayfasındaki 'Hesabınız yok mu? Talep oluşturun' formu için
    body şeması (2026-07-11) -- kimlik doğrulama GEREKTİRMEZ, bkz.
    /public/contact-request endpoint'inin docstring'i."""
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    message: str




def register_auth_routes(api_router, db, raw_db, current_user, require_permission, log_audit):
    @api_router.post("/auth/login")
    async def login(body: LoginReq, request: Request):
        """
        Kullanıcı girişi. E-posta + şifre alır, JWT access + refresh token döner.

        Çiftçi girişi: çiftçinin oluşturulmuş bir user kaydı varsa email/şifre ile.
        Demo'da her çiftçinin email'i: <member_no>@ciftci.tr / şifre: ciftci123

        PR-13 (ROADMAP-URUNLESTIRME.md): brute-force koruması -- aynı e-posta+IP
        kombinasyonu 15 dakika içinde 5 başarısız denemeden sonra 15 dakika
        kilitlenir (bkz. auth_lockout.py).
        """
        client_ip = request.client.host if request.client else "unknown"
        locked_remaining = is_locked(body.email, client_ip)
        if locked_remaining > 0:
            raise HTTPException(429, f"Çok fazla başarısız deneme -- {int(locked_remaining // 60) + 1} dakika sonra tekrar deneyin")

        # E-posta küçük harfe çevir (case-insensitive arama). Email artık tenant
        # bazlı benzersiz (bkz. P1 index düzeltmesi) — aynı e-posta birden fazla
        # kurumda kayıtlı olabilir, bu yüzden TÜM eşleşmeler çekilip şifre her
        # birine karşı denenir (login sırasında current_tenant_id henüz bilinmediği
        # için tenant'a göre daraltamayız — bkz. tenant_context.py'nin bu
        # senaryo için bilinçli "filtre eklenmez" notu).
        # raw_db (sarmalanmamış) — login anında tenant bağlamı henüz YOK;
        # tenant_context.py artık fail-closed olduğu için bağlamsız `db`
        # sorgusu boş dönerdi. Platform-admin kodundaki raw_db konvansiyonuyla
        # aynı bilinçli istisna (bkz. UNAUTHORIZED_TENANT_SENTINEL).
        candidates = await raw_db.users.find({"email": body.email.lower()}).to_list(20)
        user = None
        for candidate in candidates:
            if verify_password(body.password, candidate.get("password", "")):
                user = candidate
                break

        # Kullanıcı yoksa VEYA şifre hiçbir aday ile eşleşmiyorsa hata (bcrypt + eski SHA256 destekli)
        if not user:
            record_failed_attempt(body.email, client_ip)
            await log_audit(db, {"email": body.email}, action="login_failed", entity="user", request=request)
            raise HTTPException(401, "Hatalı e-posta veya şifre")

        # Pasif hale getirilmiş kullanıcılar giriş yapamaz (veri geçmişi silinmez,
        # sadece erişimi kapatılır — bkz. users.py update_user_status)
        if user.get("active") is False:
            await log_audit(db, user, action="login_blocked_inactive", entity="user", entity_id=user["id"], request=request)
            raise HTTPException(403, "Hesabınız pasif duruma alınmış, sistem yöneticinizle iletişime geçin")

        # God Mode ikinci faktör (TOTP) — SADECE totp_enabled=True taşıyan
        # hesaplarda devreye girer (bkz. totp.py docstring), diğer TÜM
        # kullanıcılar bu bloktan hiç etkilenmez.
        if user.get("totp_enabled"):
            if not body.totp_code:
                raise HTTPException(401, "TOTP_REQUIRED")
            if not verify_totp(user.get("totp_secret", ""), body.totp_code):
                record_failed_attempt(body.email, client_ip)
                await log_audit(db, user, action="login_failed_totp", entity="user", entity_id=user["id"], request=request)
                raise HTTPException(401, "Geçersiz TOTP kodu")

        # Şifre hâlâ eski SHA256 formatındaysa sessizce bcrypt'e yükselt
        # (raw_db — login'de tenant bağlamı yok, fail-closed `db` eşleşmezdi)
        if needs_rehash(user["password"]):
            await raw_db.users.update_one({"id": user["id"]}, {"$set": {"password": hash_password(body.password)}})

        record_successful_login(body.email, client_ip)
        access_token = make_access_token(user["id"], user["role"], user.get("farmer_id"), user.get("tenant_id"))
        refresh_token = make_refresh_token(user["id"], user.get("tenant_id"))

        await log_audit(db, user, action="login", entity="user", entity_id=user["id"], request=request)

        user_safe = {k: v for k, v in user.items() if k not in ("_id", "password", "totp_secret")}
        return {"token": access_token, "access_token": access_token, "refresh_token": refresh_token, "user": user_safe}


    @api_router.post("/auth/refresh")
    async def refresh_access_token(body: RefreshTokenReq):
        """
        Refresh token ile yeni bir access token üretir. Access token süresi
        dolduğunda kullanıcı yeniden şifre girmeden oturumu uzatabilir.
        Body: {"refresh_token": "..."}
        """
        token = body.refresh_token
        try:
            payload = decode_token(token)
            if payload.get("type") != "refresh":
                raise HTTPException(401, "Geçersiz token tipi")
        except jwt.PyJWTError:
            raise HTTPException(401, "Geçersiz veya süresi dolmuş refresh token")

        # raw_db — refresh isteği geçerli bir access token TAŞIMAZ (süresi
        # dolmuştur), middleware tenant bağlamı kuramaz; fail-closed `db`
        # sorgusu kullanıcıyı asla bulamazdı. Kimlik id + token'daki tenant
        # eşleşmesiyle doğrulanır.
        user = await raw_db.users.find_one({"id": payload["user_id"]}, {"_id": 0, "password": 0, "totp_secret": 0})
        if not user:
            raise HTTPException(401, "Kullanıcı bulunamadı")
        if user.get("tenant_id") != payload.get("tenant_id"):
            raise HTTPException(401, "Token tenant uyuşmazlığı")
        if user.get("active") is False:
            raise HTTPException(403, "Hesabınız pasif duruma alınmış")

        new_access = make_access_token(user["id"], user["role"], user.get("farmer_id"), user.get("tenant_id"))
        return {"token": new_access, "access_token": new_access}


    @api_router.get("/auth/me")
    async def me(user=Depends(current_user)):
        """Mevcut giriş yapmış kullanıcının bilgilerini döner"""
        return user


    @api_router.post("/public/contact-request")
    async def public_contact_request(body: PublicContactRequest, request: Request):
        """
        Giriş sayfasındaki (Login.jsx) 'Giriş için kullanıcınız yok ise burada
        talep oluşturabilirsiniz' formu (2026-07-11). KİMLİK DOĞRULAMASI
        GEREKTİRMEZ -- /auth/login gibi bu da bir "öncesi" endpoint'i: henüz
        hesabı olmayan biri başvuruyor, current_user/require_permission
        KULLANILAMAZ (login ile AYNI gerekçe).

        Asıl mantık public_contact.py'de (tenant çözümleme + case/kategori
        yazma) -- mongomock ile tek başına test edilebilsin diye ayrıştırıldı
        (bkz. tests/test_public_contact_request.py). Bu route sadece girdi
        doğrulama + kötüye kullanım freni + tenant bağlamını kurup/söküyor.

        Kötüye kullanım freni: auth_lockout.py'deki (PR-13) AYNI IP bazlı
        sayaç yeniden kullanılır -- aynı IP 15 dakikada 5'ten fazla talep
        oluşturamaz (Redis/ek bağımlılık YOK, login brute-force korumasıyla
        aynı in-process tasarım).
        """
        if not body.phone and not body.email:
            raise HTTPException(400, "Telefon veya e-posta adreslerinden en az biri gerekli (size dönüş yapılabilmesi için)")
        if not body.full_name.strip() or not body.message.strip():
            raise HTTPException(400, "Ad Soyad ve mesaj alanları zorunludur")

        client_ip = request.client.host if request.client else "unknown"
        lock_key = "public-contact-form"
        locked_remaining = is_locked(lock_key, client_ip)
        if locked_remaining > 0:
            raise HTTPException(429, f"Çok fazla talep oluşturuldu -- {int(locked_remaining // 60) + 1} dakika sonra tekrar deneyin")
        record_failed_attempt(lock_key, client_ip)

        reset_token = None
        if current_tenant_id.get() is None:
            tenant = await resolve_bootstrap_tenant(raw_db)
            reset_token = current_tenant_id.set(tenant["id"])

        try:
            case_doc = await create_public_contact_case(db, body.full_name, body.phone, body.email, body.message)
            await log_audit(db, {"email": body.email or body.phone or "anonim"}, action="create",
                             entity="case", entity_id=case_doc["id"], new_value=case_doc, request=request)
        finally:
            if reset_token is not None:
                current_tenant_id.reset(reset_token)

        return {"ok": True, "message": "Talebiniz alındı. Kurumunuzun yetkilisi en kısa sürede sizinle iletişime geçecektir."}



