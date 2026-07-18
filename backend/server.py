"""
=====================================================================
DİJİTAL TARIM EKOSİSTEMİ — KOOPERATİF EDİSYONU
Backend API (FastAPI)
=====================================================================

Bu dosya tüm backend mantığını içerir:
- Kimlik doğrulama (JWT tabanlı)
- Çiftçi/Parsel/Sözleşme/Ekim/Sulama/Operasyon/Verimlilik modülleri
- Çiftçi self-servis (kendi hesabıyla giriş + veri ekleme)
- Dashboard analitikleri
- Seed data (200+ çiftçi, 300+ parsel)

Mimari Notu:
- Tüm endpoint'ler /api prefix'i ile başlar (Kubernetes ingress için)
- MongoDB üzerinde async motor kullanılıyor (performans için)
- Pydantic v2 ile veri doğrulama yapılıyor
"""

# ============ TEMEL KÜTÜPHANELER ============
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api_keys import resolve_api_key_user, KEY_PREFIX as API_KEY_PREFIX
from auth_lockout import is_locked, record_failed_attempt, record_successful_login
from dotenv import load_dotenv                              # .env dosyasını okur
from starlette.middleware.cors import CORSMiddleware        # CORS kuralları
from motor.motor_asyncio import AsyncIOMotorClient          # Async MongoDB sürücüsü
import logging                                              # Log altyapısı
import time                                                 # API çağrı süre ölçümü (God Mode Faz 2)
import jwt                                                  # JSON Web Token (giriş tokeni)
from pathlib import Path                                    # Dosya yolu (cross-platform)
from pydantic import BaseModel, Field                       # Veri model doğrulama
from typing import List, Optional, Dict, Any                # Tip ipucu
from datetime import datetime, timezone, timedelta          # Tarih/saat (UTC)
import uuid                                                 # Benzersiz ID üretimi
import random                                               # Seed data için (sabit seed kullanılır)

# ============ KONFİGÜRASYON ============
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')                               # .env dosyasını yükle (MONGO_URL, DB_NAME burada)

from config_service import (APP_NAME, APP_FULL_NAME, APP_VERSION, JWT_SECRET, JWT_ALG,
                             CORS_ORIGINS, ADMIN_TIER_ROLES, ROLE_HIERARCHY, ROLE_LABELS,
                             has_min_role, MONGO_URL, DB_NAME, PLATFORM_ADMIN_EMAIL,
                             PLATFORM_ADMIN_PASSWORD, install_secret_masking, ALLOW_DATA_SEEDING,
                             SENTRY_DSN, IS_PRODUCTION, ENVIRONMENT)
from security import (hash_password, verify_password, needs_rehash,
                       make_access_token, make_refresh_token, decode_token)
from totp import verify_totp
from audit import log_audit, register_audit_routes
from integrations import register_integration_routes
from tenant_context import TenantScopedDB, current_tenant_id
from public_contact import resolve_bootstrap_tenant, create_public_contact_case
from search_utils import safe_regex, TR_COLLATION            # BULGU 2/4: güvenli arama + TR collation

# MongoDB bağlantısı kur (MONGO_URL/DB_NAME artık config_service.py'den okunur)
client = AsyncIOMotorClient(MONGO_URL)                      # Async client
raw_db = client[DB_NAME]                                    # HAM veritabanı handle (tenant filtresi YOK)

# Uygulamanın geri kalanı `db` üzerinden çalışır — bu, raw_db'nin tenant'a
# göre otomatik filtreleyen bir sarmalayıcısıdır (bkz. tenant_context.py).
# Mevcut hiçbir sorgu satırı değişmeden tenant-izole hale gelir.
db = TenantScopedDB(raw_db)

# PR-12 (ROADMAP-URUNLESTIRME.md): Gozlemlenebilirlik -- SENTRY_DSN bos ise
# TAMAMEN devre disi (sifir davranis degisikligi, sifir performans etkisi).
# Doldurulursa Sentry VEYA self-hosted GlitchTip (Sentry API-uyumlu) hata
# izleme baglanir. Loglara token/sifre yazilmaz kurali (CLAUDE.md #3.1) ile
# tutarli: send_default_pii=False -- kullanici PII'si otomatik gonderilmez.
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        release=APP_VERSION,
        send_default_pii=False,
        traces_sample_rate=0.1 if IS_PRODUCTION else 1.0,
    )
    logging.getLogger(__name__).info("Sentry/GlitchTip hata izleme aktif (environment=%s)", ENVIRONMENT)

# FastAPI uygulaması
app = FastAPI(title=APP_FULL_NAME, version=APP_VERSION)


@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    """
    Her istek başında Authorization header'ındaki JWT'yi (varsa) hafifçe
    çözüp tenant_id'yi context'e yazar. Token geçersiz/yoksa sessizce
    geçilir — asıl yetki kontrolü zaten current_user dependency'sinde
    yapılıyor, buradaki tek amaç tenant filtresini hazırlamak.
    """
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    tenant_id = None
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            tenant_id = payload.get("tenant_id")
        except jwt.PyJWTError:
            pass  # current_user dependency zaten 401 dönecek

    reset_token = current_tenant_id.set(tenant_id)
    start = time.monotonic()
    try:
        response = await call_next(request)
    finally:
        current_tenant_id.reset(reset_token)
    duration_ms = (time.monotonic() - start) * 1000

    # Faz 2 — God Mode API çağrı istatistikleri (`GET /god-mode/api-stats`).
    # Fire-and-forget DEĞİL (asyncio.create_task ile kaybolma riski yerine
    # doğrudan await) ama HATA yutulur — bu log'un asıl isteği ASLA
    # etkilememesi gerekir (bkz. event_bus.py'nin "otomasyon bir yan
    # etkidir" felsefesiyle AYNI karar).
    try:
        await raw_db.api_call_logs.insert_one({
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "tenant_id": tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:  # noqa: BLE001
        pass
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Merkezi hata yakalayıcı. Beklenmeyen tüm hataları loglar ve istemciye
    stack trace sızdırmadan temiz bir JSON hata döner.
    """
    logging.getLogger("toprax.errors").exception(f"Beklenmeyen hata: {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Sunucu tarafında beklenmeyen bir hata oluştu.", "path": str(request.url.path)},
    )

# /api prefix'li router — tüm endpoint'ler buraya bağlanacak
api_router = APIRouter(prefix="/api")

# Bearer token şeması (Authorization: Bearer <token>)
# auto_error=False → token yoksa otomatik 401 fırlatma, biz kontrol edelim
security = HTTPBearer(auto_error=False)


# =====================================================================
#                       KİMLİK DOĞRULAMA YARDIMCILARI
# =====================================================================

# hash_pw / make_token artık security.py içinde (bcrypt + refresh token
# desteğiyle) — geriye dönük çağrı uyumluluğu için ince sarmalayıcılar:

def hash_pw(pw: str) -> str:
    """Geriye dönük uyumluluk için ince sarmalayıcı — artık bcrypt kullanır."""
    return hash_password(pw)


def make_token(user_id: str, role: str, farmer_id: Optional[str] = None, tenant_id: Optional[str] = None) -> str:
    """Geriye dönük uyumluluk için ince sarmalayıcı."""
    return make_access_token(user_id, role, farmer_id, tenant_id)


async def current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    """
    Her korunan endpoint'in başında çağrılan dependency.
    Bearer token'ı doğrular, kullanıcı objesini geri döner.
    Token yoksa veya geçersizse 401 fırlatır.

    PR-24 (ROADMAP-URUNLESTIRME.md): Authorization header'i "toprax_key_"
    ile basliyorsa bu bir JWT degil, makine-makine API key'idir (bkz.
    api_keys.py). TEK entegrasyon noktasi burasi -- boylece asagidaki JWT
    kodu hic degismeden, ~370 mevcut endpoint API key'i de otomatik kabul
    eder (require_permission zaten current_user'i sarmalıyor).
    """
    if not creds:
        raise HTTPException(401, "Token gerekli")

    if creds.credentials.startswith(API_KEY_PREFIX):
        api_user = await resolve_api_key_user(raw_db, creds.credentials)
        if not api_user:
            raise HTTPException(401, "Geçersiz, süresi dolmuş veya iptal edilmiş API anahtarı")
        return api_user

    try:
        # Token'ı çöz (imza doğrulaması + süre kontrolü otomatik)
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])

        # Refresh token'lar API çağrılarında kullanılamaz — sadece /auth/refresh'te.
        if payload.get("type") == "refresh":
            raise HTTPException(401, "Refresh token API çağrılarında kullanılamaz")

        # DB'den kullanıcıyı çek (şifre hash'ini geri dönmüyoruz)
        user = await db.users.find_one(
            {"id": payload["user_id"]},
            {"_id": 0, "password": 0, "totp_secret": 0}                       # _id ve password'ü hariç tut
        )
        if not user:
            raise HTTPException(401, "Kullanıcı yok")
        if user.get("active") is False:
            raise HTTPException(403, "Hesabınız pasif duruma alınmış")
        
        # Token'daki farmer_id'yi user objesine ekle (çiftçi self-servis için)
        user["farmer_id"] = payload.get("farmer_id")
        return user
    except jwt.PyJWTError:
        # Token geçersiz veya süresi dolmuş
        raise HTTPException(401, "Geçersiz token")


def is_admin(user: dict) -> bool:
    """Kullanıcı admin yetkisinde mi? (Tam erişim için)"""
    return user.get("role") in ("super_admin", "fabrika_muduru", "ziraat_muhendisi",
                                 "kurum_yoneticisi", "il_yoneticisi", "ilce_yoneticisi")


# current_user/db tanımlandıktan hemen sonra kurulur ki dosyanın devamındaki
# TÜM endpoint'ler (farmers/parcels dahil) require_permission(...) kullanabilsin
# — modül kaydı bölümünde (aşağıda) TEKRAR oluşturulmaz, sadece import edilir.
from permissions import make_require_permission
require_permission = make_require_permission(current_user, db)

# IT-33 — Feature Flags guard'ı (permissions.make_require_permission ile AYNI factory kalıbı).
from platform_core import make_require_feature, check_and_consume_limit
require_feature = make_require_feature(db)


def require_min_role(required_role: str):
    """
    Rol hiyerarşisine göre minimum yetki denetimi yapan dependency üretici.
    Kullanım: user=Depends(require_min_role("fabrika_muduru"))
    required_role veya daha yetkili (hiyerarşide daha üst) roller geçer.
    """
    async def _checker(user: dict = Depends(current_user)) -> dict:
        if not has_min_role(user.get("role"), required_role):
            raise HTTPException(403, f"Bu işlem için en az '{ROLE_LABELS.get(required_role, required_role)}' yetkisi gerekir")
        return user
    return _checker


# =====================================================================
#                       PYDANTIC MODELLER (Veri Doğrulama)
# =====================================================================

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


class FarmerCreate(BaseModel):
    """Yeni çiftçi oluşturma için body şeması"""
    full_name: str
    tc_no: str
    phone: str
    email: Optional[str] = None
    village: str
    region_id: str
    iban: Optional[str] = None
    notes: Optional[str] = None

    # ============ Sprint A1 — Form Yönetimi ile eşleşen ek alanlar ============
    # Bu alanların ekranda zorunlu/görünür/sıra/lookup davranışı
    # field_definitions (module="farmers") tarafından yönetilir; burada
    # sadece gerçek, tipli DB kolonları olarak tanımlanırlar.

    # --- Kimlik Bilgileri ---
    birth_date: Optional[str] = None                        # YYYY-MM-DD
    gender: Optional[str] = None                             # lookup: cinsiyet
    marital_status: Optional[str] = None                     # lookup: medeni_durum
    tax_no: Optional[str] = None                              # Vergi No (firma unvanlı çiftçiler için)

    # --- İletişim ---
    phone_alt: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None                                # İl
    district: Optional[str] = None                            # İlçe

    # --- Tarımsal Bilgiler ---
    cks_no: Optional[str] = None                               # ÇKS Kayıt No
    cks_status: Optional[str] = None                           # lookup: cks_durumu
    isletme_no: Optional[str] = None
    cooperative_member: Optional[bool] = None                  # Kooperatif Üyeliği
    chamber_member: Optional[bool] = None                      # Ziraat Odası Üyeliği
    producer_union: Optional[str] = None                       # Üretici Birliği

    # --- Finansal ---
    bank_name: Optional[str] = None
    support_payments_total: Optional[float] = None             # Destek Ödemeleri (toplam)
    debt_status: Optional[str] = None                           # lookup: borc_durumu
    debt_amount: Optional[float] = None

    # --- Operasyon ---
    last_visit_date: Optional[str] = None                       # Son Ziyaret
    responsible_personnel: Optional[str] = None                 # Sorumlu Personel
    risk_score: Optional[int] = None                            # Risk Skoru (AI)


class FarmerUpdate(BaseModel):
    """Çiftçi güncelleme — tüm alanlar opsiyonel"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    village: Optional[str] = None
    iban: Optional[str] = None
    notes: Optional[str] = None

    # --- Kimlik Bilgileri ---
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    tax_no: Optional[str] = None

    # --- İletişim ---
    phone_alt: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    # --- Tarımsal Bilgiler ---
    cks_no: Optional[str] = None
    cks_status: Optional[str] = None
    isletme_no: Optional[str] = None
    cooperative_member: Optional[bool] = None
    chamber_member: Optional[bool] = None
    producer_union: Optional[str] = None

    # --- Finansal ---
    bank_name: Optional[str] = None
    support_payments_total: Optional[float] = None
    debt_status: Optional[str] = None
    debt_amount: Optional[float] = None

    # --- Operasyon ---
    last_visit_date: Optional[str] = None
    responsible_personnel: Optional[str] = None
    risk_score: Optional[int] = None


class ParcelCreate(BaseModel):
    """Yeni parsel oluşturma"""
    farmer_id: str
    name: str
    village: str
    region_id: str
    area_dekar: float
    # B6 (#7) — EKİLEBİLİR alan (dekar). Parselin toplam alanı ≠ ekilebilir alanı
    # (yol/dere/kayalık düşülür). Sözleşme kota→alan kuralı BUNU baz alır; boşsa
    # kural toplam area_dekar'a düşer (bkz. data_entry.py create_contract).
    ekilebilir_alan_dekar: Optional[float] = None
    soil_type: str
    irrigation: str
    geometry: Optional[Dict[str, Any]] = None               # GeoJSON Polygon

    # ============ IT-02 — Form Yönetimi ile eşleşen ek alanlar ============
    # Ekranda zorunlu/görünür/sıra/lookup davranışı field_definitions
    # (module="parcels") tarafından yönetilir; burada sadece gerçek,
    # tipli DB kolonları olarak tanımlanırlar (Sprint A1 kuralı).

    # --- Kadastro Bilgileri ---
    ada_no: Optional[str] = None
    parsel_no_tapu: Optional[str] = None                     # Tapudaki parsel no (parcel_code ile karıştırılmamalı)
    il: Optional[str] = None                                  # lookup: il
    ilce: Optional[str] = None                                # lookup: ilce (parent_id ile il'e bağlı)
    mahalle: Optional[str] = None                              # Mahalle/Köy — düz metin (Sprint A1 kuralı: national veri seti yok)

    # --- Coğrafi Özellikler ---
    rakim_m: Optional[int] = None                             # Rakım (metre)
    egim_yuzde: Optional[float] = None                        # Eğim (%)

    # --- Sahiplik & Kira ---
    sahiplik_durumu: Optional[str] = None                     # lookup: sahiplik_durumu
    tapu_no: Optional[str] = None
    kira_sozlesmesi_var_mi: Optional[bool] = None
    kira_baslangic: Optional[str] = None                       # YYYY-MM-DD
    kira_bitis: Optional[str] = None                           # YYYY-MM-DD
    kiraci_adi: Optional[str] = None

    # --- Altyapı ---
    yol_durumu: Optional[str] = None                           # lookup: yol_durumu
    elektrik_baglantisi: Optional[bool] = None
    su_kaynagi: Optional[str] = None                           # lookup: su_kaynagi
    sondaj_kuyu_derinligi_m: Optional[float] = None


class IrrigationEventCreate(BaseModel):
    """Çiftçi sulama olayı ekler — bu dashboard'u günceller!"""
    parcel_id: str
    date: str                                               # YYYY-MM-DD
    method: str                                             # damla/yağmurlama/karık
    water_m3: float
    moisture_before: Optional[int] = None
    moisture_after: Optional[int] = None


class SoilSampleCreate(BaseModel):
    """Toprak analizi sonucu ekleme"""
    parcel_id: str
    date: str
    lab_name: str
    ph: float
    ec: float
    organic_matter_pct: float
    n_ppm: int
    p_ppm: int
    k_ppm: int
    recommendation: Optional[str] = None


# =====================================================================
#                       AUTH ENDPOINT'LERİ
# =====================================================================

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
    candidates = await db.users.find({"email": body.email.lower()}).to_list(20)
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
    if needs_rehash(user["password"]):
        await db.users.update_one({"id": user["id"]}, {"$set": {"password": hash_password(body.password)}})

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

    user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0, "password": 0, "totp_secret": 0})
    if not user:
        raise HTTPException(401, "Kullanıcı bulunamadı")

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


# =====================================================================
#                       DASHBOARD (Admin Görünümü)
# =====================================================================

@api_router.get("/dashboard/overview")
async def dashboard_overview(user=Depends(current_user)):
    """
    Admin dashboard verileri:
    - KPI kartları (toplam çiftçi, parsel, alan, sözleşme, hasat)
    - 5 yıllık trend grafiği
    - Bölge bazlı performans
    - Çiftçi karne dağılımı
    
    Bu endpoint herhangi bir veri ekleme/silme sonrası
    otomatik güncel rakamları dönecektir (canlı veri hissi).
    """
    # Temel sayımlar
    farmers_total = await db.farmers.count_documents({})
    parcels_total = await db.parcels.count_documents({})
    contracts_active = await db.contracts.count_documents({"status": "imzalı"})
    
    # Tüm parsel verilerini çek (alan hesabı için)
    parcels = await db.parcels.find({}, {"_id": 0}).to_list(10000)
    total_area = sum(p.get("area_dekar", 0) for p in parcels)
    
    # Verim verisi (beklenen vs gerçekleşen)
    yields = await db.yields.find({}, {"_id": 0}).to_list(10000)
    expected_ton = sum(y.get("expected_ton", 0) for y in yields)
    actual_ton = sum(y.get("actual_ton", 0) for y in yields)
    
    # Bölge bazlı istatistik
    regions = await db.regions.find({}, {"_id": 0}).to_list(100)
    region_stats = []
    for r in regions:
        r_parcels = [p for p in parcels if p.get("region_id") == r["id"]]
        r_yields = [y for y in yields if y.get("region_id") == r["id"]]
        r_area = sum(p.get("area_dekar", 0) for p in r_parcels)
        r_ton = sum(y.get("actual_ton", 0) for y in r_yields)
        region_stats.append({
            "name": r["name"],
            "farmers": await db.farmers.count_documents({"region_id": r["id"]}),
            "area_dekar": r_area,
            "yield_ton": r_ton,
            "avg_yield_per_dekar": r_ton / max(r_area, 1)    # 0'a bölme koruması
        })
    
    # 5 yıllık verim trendi
    trend = []
    for yr in range(2021, 2026):
        y_year = [y for y in yields if y.get("season") == yr]
        trend.append({
            "year": yr,
            "ton": sum(yy.get("actual_ton", 0) for yy in y_year),
            "expected": sum(yy.get("expected_ton", 0) for yy in y_year)
        })
    
    # Karne dağılımı
    farmers = await db.farmers.find({}, {"_id": 0}).to_list(10000)
    karne_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
    for f in farmers:
        s = f.get("karne_score", "C")
        karne_dist[s] = karne_dist.get(s, 0) + 1

    # ============ YENİ KPI'LAR (Sprint 2 — GIS/IoT/Drone) ============
    # Roadmap dashboard kartları: Riskli Parsel, IoT Sensörü, Drone Görevi,
    # Son Uydu Analizi, Son IoT Verisi. Hepsi GERÇEK veriden hesaplanır.
    risky_parcels_count = sum(1 for p in parcels if p.get("risk_level") in ("turuncu", "kirmizi"))
    avg_ndvi = round(sum(p.get("ndvi_latest", 0) for p in parcels) / max(len(parcels), 1), 3)

    iot_total = await db.iot_sensors.count_documents({})
    iot_active = await db.iot_sensors.count_documents({"status": "aktif"})
    iot_last = await db.iot_sensors.find({}, {"_id": 0}).sort("last_reading_at", -1).limit(1).to_list(1)

    drone_total = await db.drone_missions.count_documents({})
    drone_last = await db.drone_missions.find({}, {"_id": 0}).sort("flight_date", -1).limit(1).to_list(1)

    last_satellite_scan = max((p.get("last_satellite_scan") for p in parcels if p.get("last_satellite_scan")), default=None)

    # ============ EKİLİ / SÖKÜM DURUMU (#2 — uydu+manuel, crop_status.py) ============
    active_parcels = [p for p in parcels if p.get("is_active") is not False]
    def _plantable(p):
        e = p.get("ekilebilir_alan_dekar")
        return e if isinstance(e, (int, float)) and e else (p.get("area_dekar") or 0)
    ekili_count = sum(1 for p in active_parcels if p.get("ekim_durumu") == "ekili")
    sokulen_count = sum(1 for p in active_parcels if p.get("ekim_durumu") == "sokuldu")
    ekili_degil_count = sum(1 for p in active_parcels if p.get("ekim_durumu") not in ("ekili", "sokuldu"))
    sokulen_alan = sum(_plantable(p) for p in active_parcels if p.get("ekim_durumu") == "sokuldu")
    kalan_alan = sum(_plantable(p) for p in active_parcels if p.get("ekim_durumu") == "ekili")

    return {
        "kpis": {
            "farmers_total": farmers_total,
            "parcels_total": parcels_total,
            "active_contracts": contracts_active,
            "total_area_dekar": round(total_area, 1),
            "expected_ton": round(expected_ton, 1),
            "actual_ton": round(actual_ton, 1),
            "yield_completion_pct": round(actual_ton / max(expected_ton, 1) * 100, 1),
            # --- Sprint 2 eklentileri ---
            "risky_parcels": risky_parcels_count,
            "avg_ndvi": avg_ndvi,
            "iot_sensors_total": iot_total,
            "iot_sensors_active": iot_active,
            "iot_last_reading_at": iot_last[0]["last_reading_at"] if iot_last else None,
            "drone_missions_total": drone_total,
            "drone_last_flight_at": drone_last[0]["flight_date"] if drone_last else None,
            "last_satellite_scan": last_satellite_scan,
            # --- #2 Ekili / Söküm durumu (uydu + manuel) ---
            "ekili_parcels": ekili_count,
            "sokulen_parcels": sokulen_count,
            "ekili_degil_parcels": ekili_degil_count,
            "sokulen_alan_dekar": round(sokulen_alan, 1),
            "kalan_alan_dekar": round(kalan_alan, 1),
        },
        "regions": region_stats,
        "yield_trend": trend,
        "karne_distribution": karne_dist
    }


# =====================================================================
#                       ÇİFTÇİ DASHBOARD (Self-Servis)
# =====================================================================

@api_router.get("/farmer/my-dashboard")
async def my_dashboard(user=Depends(current_user)):
    """
    Çiftçinin kendi dashboard'u — sadece kendi verilerini görür.
    
    Çiftçi giriş yapınca burayı görür.
    Veri eklediğinde (sulama, vs.) bu sayfa anlık güncellenir.
    """
    # Çiftçi değilse veya farmer_id yoksa erişim engelle
    if user.get("role") != "ciftci" or not user.get("farmer_id"):
        raise HTTPException(403, "Sadece çiftçi hesapları erişebilir")
    
    farmer_id = user["farmer_id"]
    
    # Çiftçi bilgisi
    farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
    if not farmer:
        raise HTTPException(404, "Çiftçi profili bulunamadı")
    
    # Çiftçinin tüm parselleri
    parcels = await db.parcels.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
    
    # Aktif sözleşmeler
    contracts = await db.contracts.find(
        {"farmer_id": farmer_id, "season": 2025},
        {"_id": 0}
    ).to_list(50)
    
    # Verim geçmişi
    yields = await db.yields.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(50)
    
    # Sulama olayları (son 30 gün)
    irrigation_events = await db.irrigation_events.find(
        {"farmer_id": farmer_id},
        {"_id": 0}
    ).sort([("date", -1)]).to_list(50)
    
    # Toprak analizleri
    parcel_ids = [p["id"] for p in parcels]
    soil_samples = await db.soil_samples.find(
        {"parcel_id": {"$in": parcel_ids}},
        {"_id": 0}
    ).to_list(50)
    
    # Finansal hareketler
    finance = await db.finance.find(
        {"farmer_id": farmer_id},
        {"_id": 0}
    ).sort([("date", -1)]).to_list(50)
    
    # Toplam balance hesabı (gelir - gider)
    balance = sum(f.get("amount", 0) for f in finance)
    
    # Yaklaşan kantar randevuları
    appts = await db.appointments.find(
        {"farmer_id": farmer_id},
        {"_id": 0}
    ).sort([("scheduled_at", 1)]).to_list(20)
    
    # Toplam alan
    total_area = sum(p.get("area_dekar", 0) for p in parcels)
    
    # Bu yılın tahmini hasat
    expected_ton_2025 = sum(c.get("kota_ton", 0) for c in contracts)
    
    # Toplam su tüketimi (m³)
    total_water = sum(e.get("water_m3", 0) for e in irrigation_events)
    
    return {
        "farmer": farmer,
        "stats": {
            "parcels_count": len(parcels),
            "total_area_dekar": round(total_area, 1),
            "active_contracts": len(contracts),
            "expected_ton_2025": round(expected_ton_2025, 1),
            "total_water_m3": round(total_water, 1),
            "irrigation_events_count": len(irrigation_events),
            "balance": round(balance, 2),
            "soil_samples_count": len(soil_samples),
            "upcoming_appointments": len([a for a in appts if a.get("status") == "planlı"])
        },
        "parcels": parcels,
        "contracts": contracts,
        "yields": yields,
        "irrigation_events": irrigation_events[:10],         # Son 10
        "soil_samples": soil_samples[:10],
        "finance": finance[:10],
        "appointments": appts
    }


@api_router.post("/farmer/irrigation")
async def add_irrigation(body: IrrigationEventCreate, user=Depends(current_user)):
    """
    Çiftçi kendi parseline sulama olayı ekler.
    Bu sayede dashboard'lar (genel + bireysel) anlık güncellenir.
    """
    if user.get("role") != "ciftci" or not user.get("farmer_id"):
        raise HTTPException(403, "Sadece çiftçi ekleyebilir")
    
    # Parsel gerçekten bu çiftçiye mi ait? (yetki kontrolü)
    parcel = await db.parcels.find_one({"id": body.parcel_id})
    if not parcel:
        raise HTTPException(404, "Parsel bulunamadı")
    if parcel.get("farmer_id") != user["farmer_id"]:
        raise HTTPException(403, "Bu parsel size ait değil")
    
    # Kayıt oluştur
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["farmer_id"] = user["farmer_id"]
    doc["region_id"] = parcel.get("region_id")
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.irrigation_events.insert_one(doc)
    doc.pop("_id", None)
    
    # Bildirim oluştur (kooperatif yönetimine bilgi)
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()),
        "type": "sulama_kayit",
        "title": "Yeni sulama kaydı",
        "message": f"{user.get('full_name', 'Çiftçi')} {body.water_m3} m³ sulama kaydetti",
        "channel": "in_app",
        "status": "okundu",
        "farmer_id": user["farmer_id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return doc


@api_router.post("/farmer/soil-sample")
async def add_soil_sample(body: SoilSampleCreate, user=Depends(current_user)):
    """Çiftçi toprak analizi sonucu ekler"""
    if user.get("role") != "ciftci" or not user.get("farmer_id"):
        raise HTTPException(403, "Sadece çiftçi ekleyebilir")
    
    parcel = await db.parcels.find_one({"id": body.parcel_id})
    if not parcel:
        raise HTTPException(404, "Parsel bulunamadı")
    if parcel.get("farmer_id") != user["farmer_id"]:
        raise HTTPException(403, "Bu parsel size ait değil")
    
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.soil_samples.insert_one(doc)
    doc.pop("_id", None)
    return doc


# =====================================================================
#                       ÇİFTÇİ YÖNETİMİ (Admin)
# =====================================================================

@api_router.get("/farmers")
async def list_farmers(
    q: Optional[str] = None,
    region_id: Optional[str] = None,
    karne: Optional[str] = None,
    limit: int = 500,
    user=Depends(require_permission("farmers:view")),
    _feature=Depends(require_feature("farmer")),
):
    """
    Çiftçi listesi — admin arar/filtreler.
    Query parametreleri ile filtreleme yapılır:
    - q: ad/TC/telefon/üye no araması (regex)
    - region_id: belirli bölge
    - karne: A/B/C/D
    """
    filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
    if region_id:
        filt["region_id"] = region_id
    if karne:
        filt["karne_score"] = karne
    if q:
        # BULGU 2 düzeltmesi: kullanıcı girdisi $regex'e KAÇIŞSIZ verilmez.
        # safe_regex() re.escape + uzunluk limiti uygular (regex injection/ReDoS).
        rq = safe_regex(q)
        # OR araması — birden fazla alanda eşleşme
        filt["$or"] = [
            {"full_name": {"$regex": rq, "$options": "i"}},   # i = case-insensitive
            {"tc_no": {"$regex": rq}},
            {"phone": {"$regex": rq}},
            {"member_no": {"$regex": rq, "$options": "i"}}
        ]
    # BULGU 4 düzeltmesi: Türkçe collation — 'istanbul' aratınca 'İstanbul'
    # bulunur, sıralama Türk alfabesine uygun yapılır. collation, find()
    # kwarg'ı olarak verilir (zincirleme .collation() yerine).
    docs = await db.farmers.find(filt, {"_id": 0}, collation=TR_COLLATION).limit(limit).to_list(limit)
    docs = await mask_sensitive_fields_many(db, "farmers", docs, user)
    return docs


@api_router.get("/farmers/{farmer_id}")
async def get_farmer_360(farmer_id: str, user=Depends(require_permission("farmers:view"))):
    """
    Çiftçi 360° GÖRÜNÜM:
    - Çiftçi temel bilgileri
    - Tüm parselleri (geometri ile)
    - Tüm sözleşmeleri
    - Verim geçmişi
    - Sulama olayları
    - Toprak analizleri
    - Finansal hareketler
    - Kantar randevuları
    - Karne detayı + tarihçe
    
    Bu sayfa müşteri demosunda gerçek hayattaki kullanımı gösterir.
    """
    farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
    if not farmer:
        raise HTTPException(404, "Çiftçi bulunamadı")
    farmer = await mask_sensitive_fields(db, "farmers", farmer, user)

    parcels = await db.parcels.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
    parcel_ids = [p["id"] for p in parcels]
    
    contracts = await db.contracts.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
    yields = await db.yields.find({"farmer_id": farmer_id}, {"_id": 0}).to_list(100)
    irrigation = await db.irrigation_events.find(
        {"farmer_id": farmer_id}, {"_id": 0}
    ).sort([("date", -1)]).to_list(100)
    soil = await db.soil_samples.find(
        {"parcel_id": {"$in": parcel_ids}}, {"_id": 0}
    ).sort([("date", -1)]).to_list(50)
    finance = await db.finance.find(
        {"farmer_id": farmer_id}, {"_id": 0}
    ).sort([("date", -1)]).to_list(100)
    appointments = await db.appointments.find(
        {"farmer_id": farmer_id}, {"_id": 0}
    ).sort([("scheduled_at", -1)]).to_list(50)
    tasks = await db.tasks.find(
        {"farmer_id": farmer_id}, {"_id": 0}
    ).sort([("scheduled_date", -1)]).to_list(50)
    
    # Hesaplanmış metrikler
    total_area = sum(p.get("area_dekar", 0) for p in parcels)
    total_water = sum(e.get("water_m3", 0) for e in irrigation)
    balance = sum(f.get("amount", 0) for f in finance)
    
    # Verim trendi (yıl × ton)
    yield_by_year = {}
    for y in yields:
        yr = y.get("season")
        if yr not in yield_by_year:
            yield_by_year[yr] = {"expected": 0, "actual": 0, "area": 0}
        yield_by_year[yr]["expected"] += y.get("expected_ton", 0)
        yield_by_year[yr]["actual"] += y.get("actual_ton", 0)
        yield_by_year[yr]["area"] += y.get("area_dekar", 0)
    
    yield_trend = sorted(
        [{"year": yr, **vals} for yr, vals in yield_by_year.items()],
        key=lambda x: x["year"]
    )
    
    # #6 — SORUMLU (portföy): çiftçinin köyünden MİRAS (isimle eşleştirme).
    from admin_areas import resolve_responsible
    farmer_responsible = await resolve_responsible(db, (farmer or {}).get("village"))

    return {
        "farmer": farmer,
        "responsible": farmer_responsible,
        "summary": {
            "parcel_count": len(parcels),
            "total_area_dekar": round(total_area, 1),
            "active_contracts": len([c for c in contracts if c.get("status") == "imzalı"]),
            "total_water_m3": round(total_water, 1),
            "balance": round(balance, 2),
            "soil_samples_count": len(soil)
        },
        "parcels": parcels,
        "contracts": contracts,
        "yields": yields,
        "yield_trend": yield_trend,
        "irrigation": irrigation,
        "soil_samples": soil,
        "finance": finance,
        "appointments": appointments,
        "tasks": tasks
    }


@api_router.post("/farmers")
async def create_farmer(body: FarmerCreate, user=Depends(current_user)):
    """Yeni çiftçi ekle (admin yetkisi)"""
    if not is_admin(user):
        raise HTTPException(403, "Yetkiniz yok")
    
    # Duplicate TC kontrolü
    existing = await db.farmers.find_one({"tc_no": body.tc_no})
    if existing:
        raise HTTPException(400, "Bu TC No ile çiftçi zaten kayıtlı")
    
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    
    # Üye no otomatik (TS-00001, TS-00002...)
    count = await db.farmers.count_documents({})
    doc["member_no"] = f"TS-{(count+1):05d}"
    
    doc["karne_score"] = "C"                                 # Yeni üye → orta puan
    doc["karne_points"] = 65
    doc["status"] = "aktif"
    doc["membership_year"] = datetime.now().year
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.farmers.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/farmers/{farmer_id}")
async def update_farmer(farmer_id: str, body: FarmerUpdate, request: Request,
                         user=Depends(require_permission("farmers:edit"))):
    """Çiftçi bilgi güncelle (IT-04: is_admin() yerine granüler farmers:edit izni)"""
    old = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Çiftçi bulunamadı")

    # Sadece dolu (None olmayan) alanları güncelle
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    # IT-07 — maskeli alan (örn. IBAN) düzenleme formunda değiştirilmeden
    # geri gönderilmişse ("•••• MASKELİ ••••"), bunu değişiklik SAYMA —
    # yoksa maskeyi görmeyen kullanıcı kendi kaydını farkında olmadan siler.
    updates = {k: v for k, v in updates.items() if not is_masked_value(v)}
    if not updates:
        raise HTTPException(400, "Güncellenecek alan yok")

    await db.farmers.update_one({"id": farmer_id}, {"$set": updates})
    updated = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
    await log_audit(db, user, action="update", entity="farmer", entity_id=farmer_id,
                     old_value=old, new_value=updated, request=request)
    return updated


@api_router.delete("/farmers/{farmer_id}")
async def delete_farmer(farmer_id: str, request: Request,
                        user=Depends(require_permission("farmers:delete"))):
    """
    Çiftçiyi siler (soft delete, konvansiyon #3). Bağlı aktif parsel/sözleşme
    varsa engellenir — parseldeki 409 deseniyle aynı; önce o kayıtların
    kapatılması/taşınması gerekir (veri bütünlüğü).
    """
    old = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Çiftçi bulunamadı")

    linked_parcels = await db.parcels.count_documents(
        {"farmer_id": farmer_id, "is_active": {"$ne": False}}
    )
    if linked_parcels > 0:
        raise HTTPException(
            409,
            f"Bu çiftçiye bağlı {linked_parcels} parsel var. Önce parselleri "
            "başka çiftçiye atayın veya silin, sonra çiftçiyi silin."
        )
    linked_contracts = await db.contracts.count_documents(
        {"farmer_id": farmer_id, "is_active": {"$ne": False}}
    )
    if linked_contracts > 0:
        raise HTTPException(
            409,
            f"Bu çiftçiye bağlı {linked_contracts} sözleşme var. Önce sözleşmeleri "
            "kapatın/taşıyın, sonra çiftçiyi silin."
        )

    await db.farmers.update_one(
        {"id": farmer_id},
        {"$set": {
            "is_active": False,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user.get("full_name") or user.get("email"),
        }},
    )
    await log_audit(db, user, action="soft_delete", entity="farmer", entity_id=farmer_id, old_value=old, request=request)
    return {"status": "deactivated"}


# =====================================================================
#                       PARSEL YÖNETİMİ
# =====================================================================

@api_router.get("/parcels")
async def list_parcels(
    region_id: Optional[str] = None,
    farmer_id: Optional[str] = None,
    limit: int = 500,
    user=Depends(require_permission("parcels:view")),
    _feature=Depends(require_feature("parcel")),
):
    """Parsel listesi (filtreli)"""
    # BULGU 1 düzeltmesi: soft-delete edilmiş (is_active=False) parseller
    # listede gösterilmez.
    filt: Dict[str, Any] = {"is_active": {"$ne": False}}
    if region_id: filt["region_id"] = region_id
    if farmer_id: filt["farmer_id"] = farmer_id
    docs = await db.parcels.find(filt, {"_id": 0}).limit(limit).to_list(limit)
    return docs


@api_router.get("/parcels/{parcel_id}")
async def get_parcel_detail(parcel_id: str, user=Depends(require_permission("parcels:view"))):
    """
    Parsel detay sayfası:
    - Parsel bilgisi (harita, alan, toprak)
    - Sahip çiftçi
    - Bu parselin ekim geçmişi
    - Toprak analizleri
    - Sulama olayları
    - Verim kayıtları
    - Yapılan görevler
    """
    p = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Parsel bulunamadı")
    
    farmer = await db.farmers.find_one({"id": p["farmer_id"]}, {"_id": 0})
    plantings = await db.plantings.find(
        {"parcel_id": parcel_id}, {"_id": 0}
    ).sort([("season", -1)]).to_list(50)
    soil = await db.soil_samples.find(
        {"parcel_id": parcel_id}, {"_id": 0}
    ).sort([("date", -1)]).to_list(20)
    irrigation = await db.irrigation_events.find(
        {"parcel_id": parcel_id}, {"_id": 0}
    ).sort([("date", -1)]).to_list(100)
    yields = await db.yields.find(
        {"parcel_id": parcel_id}, {"_id": 0}
    ).sort([("season", -1)]).to_list(20)
    tasks = await db.tasks.find(
        {"parcel_id": parcel_id}, {"_id": 0}
    ).sort([("scheduled_date", -1)]).to_list(50)
    iot_sensors = await db.iot_sensors.find(
        {"parcel_id": parcel_id}, {"_id": 0}
    ).to_list(20)
    drone_missions = await db.drone_missions.find(
        {"parcel_id": parcel_id}, {"_id": 0}
    ).sort([("flight_date", -1)]).to_list(20)

    # #6 — SORUMLU (portföy): köy adından MİRAS alınır (isimle eşleştirme).
    from admin_areas import resolve_responsible
    responsible = await resolve_responsible(db, p.get("village") or p.get("mahalle"))

    return {
        "parcel": p,
        "farmer": farmer,
        "responsible": responsible,
        "plantings": plantings,
        "soil_samples": soil,
        "irrigation_events": irrigation,
        "yields": yields,
        "tasks": tasks,
        "iot_sensors": iot_sensors,
        "drone_missions": drone_missions,
    }


@api_router.post("/parcels")
async def create_parcel(body: ParcelCreate, request: Request, user=Depends(current_user)):
    """Yeni parsel oluştur (manuel form veya harita çizim aracıyla)"""
    if not is_admin(user):
        raise HTTPException(403, "Yetkiniz yok")
    
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())

    count = await db.parcels.count_documents({})
    await check_and_consume_limit(db, user.get("tenant_id"), "parcel_limit", count, "Parsel")
    doc["parcel_code"] = f"PRS-{(count+1):05d}"
    doc["current_crop"] = "Şeker Pancarı"
    doc["active_season"] = datetime.now().year
    # Yeni çizilen/oluşturulan parselde henüz uydu verisi yok — dashboard
    # KPI'larının (risky_parcels, avg_ndvi) bu parseli de sayabilmesi için
    # nötr bir varsayılan atanıyor (import-geojson ile aynı mantık).
    doc.setdefault("ndvi_latest", 0.65)
    doc.setdefault("risk_level", "sari")
    doc.setdefault("risk_label", "İzlemeye Değer (henüz uydu taraması yok)")
    doc.setdefault("expected_yield_ton", round(body.area_dekar * 5.5, 1))
    doc.setdefault("last_satellite_scan", None)
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.parcels.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(db, user, action="create", entity="parcel", entity_id=doc["id"], new_value=doc, request=request)
    return doc


class ParcelUpdate(BaseModel):
    """Parsel bilgi güncelleme — harita çizim aracı da bu endpoint'i kullanacak"""
    farmer_id: Optional[str] = None                          # sonradan çiftçi atama (atanmamış import edilen parseller için)
    name: Optional[str] = None
    village: Optional[str] = None
    area_dekar: Optional[float] = None
    ekilebilir_alan_dekar: Optional[float] = None            # B6 (#7) — ekilebilir alan
    soil_type: Optional[str] = None
    irrigation: Optional[str] = None
    current_crop: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None               # GeoJSON Polygon (harita düzenlemesi)
    risk_level: Optional[str] = None                        # yesil|sari|turuncu|kirmizi (manuel override)
    ndvi_latest: Optional[float] = None

    # ============ IT-02 — ek alanlar (bkz. ParcelCreate) ============
    # --- Kadastro Bilgileri ---
    ada_no: Optional[str] = None
    parsel_no_tapu: Optional[str] = None
    il: Optional[str] = None
    ilce: Optional[str] = None
    mahalle: Optional[str] = None
    # --- Coğrafi Özellikler ---
    rakim_m: Optional[int] = None
    egim_yuzde: Optional[float] = None
    # --- Sahiplik & Kira ---
    sahiplik_durumu: Optional[str] = None
    tapu_no: Optional[str] = None
    kira_sozlesmesi_var_mi: Optional[bool] = None
    kira_baslangic: Optional[str] = None
    kira_bitis: Optional[str] = None
    kiraci_adi: Optional[str] = None
    # --- Altyapı ---
    yol_durumu: Optional[str] = None
    elektrik_baglantisi: Optional[bool] = None
    su_kaynagi: Optional[str] = None
    sondaj_kuyu_derinligi_m: Optional[float] = None


class ParcelBulkUpdateFields(BaseModel):
    """IT-15 — toplu işlemde anlamlı olan alt küme (isim/alan/geometri gibi parsele özgü alanlar kasıtlı olarak YOK)"""
    soil_type: Optional[str] = None
    irrigation: Optional[str] = None
    risk_level: Optional[str] = None
    current_crop: Optional[str] = None


class ParcelBulkUpdateRequest(BaseModel):
    parcel_ids: List[str]
    updates: ParcelBulkUpdateFields


@api_router.put("/parcels/bulk-update")
async def bulk_update_parcels(body: ParcelBulkUpdateRequest, request: Request,
                               user=Depends(require_permission("parcels:edit"))):
    """
    IT-15 — çoklu parsel toplu işlem (haritada şekille/tıklayarak seçilen parseller).
    update_parcel ile AYNI iş mantığı (risk_level->risk_label senkronu dahil), sadece
    N parsel için tek istekte toplanmış hali. Her parsel için AYRI log_audit çağrılır
    (convention #6 — tek bir "bulk" audit kaydı old/new'i anlamsızlaştırırdı).
    Bu route parcel_id path parametresini yakalayan `/parcels/{parcel_id}` PUT'undan
    ÖNCE tanımlı olmalı, yoksa Starlette "bulk-update"i bir parcel_id sanıp oraya yönlendirir.
    """
    if not body.parcel_ids:
        raise HTTPException(400, "Parsel seçilmedi")
    updates = {k: v for k, v in body.updates.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Güncellenecek alan yok")

    if "risk_level" in updates:
        risk_labels = {
            "yesil": "Düşük Risk", "sari": "İzlemeye Değer",
            "turuncu": "Riskli", "kirmizi": "Acil Müdahale"
        }
        updates["risk_label"] = risk_labels.get(updates["risk_level"], updates["risk_level"])

    updated_count = 0
    for pid in body.parcel_ids:
        old = await db.parcels.find_one({"id": pid}, {"_id": 0})
        if not old:
            continue
        await db.parcels.update_one({"id": pid}, {"$set": updates})
        new = await db.parcels.find_one({"id": pid}, {"_id": 0})
        await log_audit(db, user, action="update", entity="parcel", entity_id=pid, old_value=old, new_value=new, request=request)
        updated_count += 1
    return {"updated_count": updated_count, "requested_count": len(body.parcel_ids)}


class ParcelBulkDeleteRequest(BaseModel):
    parcel_ids: List[str]


@api_router.post("/parcels/bulk-delete")
async def bulk_delete_parcels(body: ParcelBulkDeleteRequest, request: Request,
                              user=Depends(require_min_role("fabrika_muduru"))):
    """
    Çoklu parsel toplu SOFT-delete (#3). Bağlı AKTİF sözleşmesi olan parseller
    silinmez — atlanıp raporlanır (tekil DELETE'in 409 guard'ı ile AYNI kural).
    Her gerçekten silinen parsel için ayrı log_audit (convention #6).
    """
    if not body.parcel_ids:
        raise HTTPException(400, "Parsel seçilmedi")
    deleted, skipped = [], []
    for pid in body.parcel_ids:
        old = await db.parcels.find_one({"id": pid}, {"_id": 0})
        if not old:
            continue
        linked = await db.contracts.count_documents({"parcel_id": pid, "is_active": {"$ne": False}})
        if linked > 0:
            skipped.append({"id": pid, "name": old.get("name") or old.get("parcel_code"),
                            "reason": f"{linked} bağlı sözleşme"})
            continue
        await db.parcels.update_one({"id": pid}, {"$set": {
            "is_active": False,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user.get("full_name") or user.get("email"),
        }})
        await log_audit(db, user, action="soft_delete", entity="parcel", entity_id=pid, old_value=old, request=request)
        deleted.append(pid)
    return {"deleted_count": len(deleted), "skipped": skipped, "requested_count": len(body.parcel_ids)}


@api_router.put("/parcels/{parcel_id}")
async def update_parcel(parcel_id: str, body: ParcelUpdate, request: Request,
                         user=Depends(require_permission("parcels:edit"))):
    """Parsel bilgilerini günceller (harita üzerinden geometri düzenleme dahil; IT-04: granüler parcels:edit izni)"""
    old = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Parsel bulunamadı")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Güncellenecek alan yok")

    # Çiftçi atanıyor/değiştiriliyorsa region_id'yi o çiftçiden türet (bölge
    # bazlı sorgular tutarlı kalsın) + parselin köyü boşsa çiftçinin köyünü ata.
    if updates.get("farmer_id"):
        farmer = await db.farmers.find_one({"id": updates["farmer_id"]}, {"_id": 0})
        if not farmer:
            raise HTTPException(400, "Seçilen çiftçi bulunamadı")
        updates["region_id"] = farmer.get("region_id")
        if not old.get("village") and not updates.get("village"):
            updates["village"] = farmer.get("village", "")

    # risk_level manuel değiştirildiyse etiketini de eşitle (tutarlılık için)
    if "risk_level" in updates:
        risk_labels = {
            "yesil": "Düşük Risk", "sari": "İzlemeye Değer",
            "turuncu": "Riskli", "kirmizi": "Acil Müdahale"
        }
        updates["risk_label"] = risk_labels.get(updates["risk_level"], updates["risk_level"])

    await db.parcels.update_one({"id": parcel_id}, {"$set": updates})
    new = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
    await log_audit(db, user, action="update", entity="parcel", entity_id=parcel_id, old_value=old, new_value=new, request=request)
    return new


@api_router.delete("/parcels/{parcel_id}")
async def delete_parcel(parcel_id: str, request: Request, user=Depends(require_min_role("fabrika_muduru"))):
    """
    Parseli siler. Bağlı sözleşme/ekim/verim kaydı varsa engellenir —
    veri bütünlüğü için önce o kayıtların kapatılması/taşınması gerekir.
    """
    old = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Parsel bulunamadı")

    linked_contracts = await db.contracts.count_documents(
        {"parcel_id": parcel_id, "is_active": {"$ne": False}}
    )
    if linked_contracts > 0:
        raise HTTPException(
            409,
            f"Bu parsele bağlı {linked_contracts} sözleşme var. Önce sözleşmeleri "
            "kapatın/taşıyın, sonra parseli silin."
        )

    # BULGU 1 (Kritik) düzeltmesi: hard-delete -> soft-delete. Parsel geçmişi
    # (geometri, ekim/verim ilişkisi) korunur; sadece görünürlük kapanır.
    await db.parcels.update_one(
        {"id": parcel_id},
        {"$set": {
            "is_active": False,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user.get("full_name") or user.get("email"),
        }},
    )
    await log_audit(db, user, action="soft_delete", entity="parcel", entity_id=parcel_id, old_value=old, request=request)
    return {"status": "deactivated"}


class ParcelSplitRequest(BaseModel):
    """Bir parseli iki (veya daha fazla) yeni parsele böler — harita çizim aracı kullanır"""
    new_geometries: list[Dict[str, Any]]              # Her biri bağımsız bir GeoJSON Polygon
    new_areas_dekar: list[float]                       # new_geometries ile aynı sırada alan (dekar)
    new_names: Optional[list[str]] = None              # Her parça için ayrı isim (verilmezse otomatik "(Parça N)" eklenir)


@api_router.post("/parcels/{parcel_id}/split")
async def split_parcel(parcel_id: str, body: ParcelSplitRequest, request: Request,
                        user=Depends(require_min_role("ziraat_muhendisi"))):
    """
    Parseli böler: orijinal parsel silinir (veya arşivlenir), yerine
    verilen geometrilerle N yeni parsel oluşturulur. Sözleşme/ekim geçmişi
    orijinal parsel siliniyorsa kaybolacağından, bağlı kayıt varsa engellenir.

    Yeni parseller varsayılan olarak orijinalin adını + "(Parça N)" ekiyle
    alır (new_names verilmezse) — böylece liste görünümünde birbirinden
    ayırt edilebilirler; öncesinde ikisi de orijinalle AYNI isme sahip
    olduğundan "yeni parsel oluşmamış" gibi görünüyordu, bu düzeltildi.
    """
    if len(body.new_geometries) < 2:
        raise HTTPException(400, "Bölme için en az 2 yeni geometri gerekli")
    if len(body.new_geometries) != len(body.new_areas_dekar):
        raise HTTPException(400, "new_geometries ve new_areas_dekar sayıları eşleşmeli")
    if body.new_names and len(body.new_names) != len(body.new_geometries):
        raise HTTPException(400, "new_names verildiyse new_geometries ile aynı sayıda olmalı")

    old = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Parsel bulunamadı")

    linked_contracts = await db.contracts.count_documents(
        {"parcel_id": parcel_id, "is_active": {"$ne": False}}
    )
    if linked_contracts > 0:
        raise HTTPException(409, "Bu parsele bağlı sözleşme var, bölünmeden önce kapatılmalı")

    count = await db.parcels.count_documents({})
    new_parcels = []
    for i, (geom, area) in enumerate(zip(body.new_geometries, body.new_areas_dekar)):
        piece_name = (body.new_names[i] if body.new_names else f"{old['name']} (Parça {i+1})")
        new_parcels.append({
            **{k: v for k, v in old.items() if k not in ("id", "parcel_code", "geometry", "area_dekar", "name")},
            "id": str(uuid.uuid4()),
            "parcel_code": f"PRS-{(count + i + 1):05d}",
            "name": piece_name,
            "geometry": geom,
            "area_dekar": area,
            "split_from": parcel_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    await db.parcels.insert_many(new_parcels)
    # BULGU 1 düzeltmesi: orijinal parsel fiziksel silinmez; is_active=False +
    # split_to ile arşivlenir (böl/birleştir izi ve eski geometri korunur).
    await db.parcels.update_one(
        {"id": parcel_id},
        {"$set": {
            "is_active": False,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user.get("full_name") or user.get("email"),
            "split_to": [p["id"] for p in new_parcels],
        }},
    )

    for p in new_parcels:
        p.pop("_id", None)
    # Tam eski/yeni karşılaştırması için new_value'ya sadece ID değil,
    # oluşturulan parsellerin TAMAMI (isim, alan, geometri) yazılıyor —
    # "kim ne zaman neyi neye böldü" audit log'dan net okunabilsin diye.
    await log_audit(db, user, action="split", entity="parcel", entity_id=parcel_id,
                     old_value=old, new_value={"new_parcels": new_parcels}, request=request)
    return {"status": "split", "new_parcels": new_parcels}


class ParcelMergeRequest(BaseModel):
    """Birden fazla parseli tek parselde birleştirir — harita çizim aracı kullanır"""
    parcel_ids: list[str]                              # Birleştirilecek parseller (2+)
    merged_geometry: Dict[str, Any]                     # Birleşik alanın GeoJSON Polygon'u


@api_router.post("/parcels/merge")
async def merge_parcels(body: ParcelMergeRequest, request: Request,
                         user=Depends(require_min_role("ziraat_muhendisi"))):
    """
    Birden fazla parseli tek parselde birleştirir. Birleştirilecek
    parsellerin AYNI ÇİFTÇİYE ait olması zorunludur (farklı çiftçilerin
    parselleri birleştirilemez — mülkiyet karışıklığı olur).
    """
    if len(body.parcel_ids) < 2:
        raise HTTPException(400, "Birleştirme için en az 2 parsel gerekli")

    parcels_to_merge = await db.parcels.find({"id": {"$in": body.parcel_ids}}, {"_id": 0}).to_list(len(body.parcel_ids))
    if len(parcels_to_merge) != len(body.parcel_ids):
        raise HTTPException(404, "Bazı parseller bulunamadı")

    farmer_ids = {p["farmer_id"] for p in parcels_to_merge}
    if len(farmer_ids) > 1:
        raise HTTPException(409, "Farklı çiftçilere ait parseller birleştirilemez")

    for p in parcels_to_merge:
        linked = await db.contracts.count_documents(
            {"parcel_id": p["id"], "is_active": {"$ne": False}}
        )
        if linked > 0:
            raise HTTPException(409, f"{p['parcel_code']} parseline bağlı sözleşme var, önce kapatılmalı")

    total_area = sum(p["area_dekar"] for p in parcels_to_merge)
    base = parcels_to_merge[0]
    count = await db.parcels.count_documents({})
    merged = {
        **{k: v for k, v in base.items() if k not in ("id", "parcel_code", "geometry", "area_dekar")},
        "id": str(uuid.uuid4()),
        "parcel_code": f"PRS-{(count + 1):05d}",
        "geometry": body.merged_geometry,
        "area_dekar": round(total_area, 1),
        "merged_from": body.parcel_ids,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.parcels.insert_one(merged)
    # BULGU 1 düzeltmesi: birleştirilen parseller fiziksel silinmez; is_active=
    # False + merged_to ile arşivlenir (eski geometri ve birleştirme izi kalır).
    await db.parcels.update_many(
        {"id": {"$in": body.parcel_ids}},
        {"$set": {
            "is_active": False,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user.get("full_name") or user.get("email"),
            "merged_to": merged["id"],
        }},
    )
    merged.pop("_id", None)

    await log_audit(db, user, action="merge", entity="parcel", entity_id=merged["id"],
                     old_value={"merged_parcels": parcels_to_merge}, new_value=merged, request=request)
    return {"status": "merged", "parcel": merged}


class GeoJSONImportRequest(BaseModel):
    """Toplu parsel import — GeoJSON FeatureCollection kabul eder"""
    geojson: Dict[str, Any]
    farmer_id: Optional[str] = None                     # Verilmezse her feature.properties.farmer_id kullanılır
    default_soil_type: str = "Tınlı"
    default_irrigation: str = "Damla"


@api_router.post("/parcels/import-geojson")
async def import_parcels_geojson(body: GeoJSONImportRequest, request: Request,
                                  user=Depends(require_min_role("ziraat_muhendisi"))):
    """
    GeoJSON FeatureCollection'dan toplu parsel oluşturur. Her feature'ın
    geometry'si Polygon olmalı. properties içinde farmer_id/name/village
    varsa kullanılır, yoksa body.farmer_id / varsayılanlar kullanılır.

    Alan (dekar), geometrinin enlem/boylamından basit bir düzlemsel
    (shoelace) yaklaşıklıkla hesaplanır — kadastral hassasiyet gerektiren
    durumlarda gerçek bir GIS kütüphanesiyle (örn. shapely) yeniden
    hesaplanması önerilir.
    """
    features = body.geojson.get("features", [])
    if not features:
        raise HTTPException(400, "GeoJSON içinde 'features' bulunamadı")

    def _shoelace_area_dekar(coords) -> float:
        """
        Basit düzlemsel alan yaklaşıklığı (shoelace formülü).
        NOT: Enlem/boylam derecelerini düz kabul eder — kutuplara yakın
        ya da çok büyük parsellerde hata payı artar. Kadastral hassasiyet
        gerekiyorsa shapely + pyproj ile gerçek projeksiyonlu hesaplama
        yapılmalı. Küçük tarla ölçeğinde (<1000 dekar) yeterince yakındır.
        """
        ring = coords[0]
        area_deg2 = 0.0
        for i in range(len(ring) - 1):
            # Koordinat 3B olabilir ([lng,lat,alt]) — sadece ilk iki bileşeni al.
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[i + 1][0], ring[i + 1][1]
            area_deg2 += x1 * y2 - x2 * y1
        area_deg2 = abs(area_deg2) / 2.0
        # 1° ≈ 111 km → 1 derece² ≈ 111² km² = 12321 km²
        # 1 km² = 1000 dekar (1 dekar = 1000 m²)
        km2 = area_deg2 * (111 ** 2)
        return round(km2 * 1000, 1)

    def _to_2d_coords(coords):
        """GeoJSON koordinatlarındaki 3. boyutu (yükseklik) atar:
        [lng,lat,alt] -> [lng,lat]. Google Earth/KML kaynaklı dosyalar
        genelde 3B gelir; 3B koordinat hem alan hesabını hem MongoDB
        2dsphere index'ini bozabildiği için içe aktarmada 2B'ye indirilir."""
        if coords and isinstance(coords[0], (int, float)):
            return [coords[0], coords[1]]
        return [_to_2d_coords(c) for c in coords]

    def _extract_tkgm_fields(props: dict) -> dict:
        """
        IT-16 — TKGM (Tapu ve Kadastro Genel Müdürlüğü) kamuya açık "Parsel
        Sorgu" haritasından (parselsorgu.tkgm.gov.tr) dışa aktarılan GeoJSON
        özellik adlarını (il/ilce/mahalle/ada/parsel) IT-02'nin ParcelCreate
        alanlarına eşler. Resmi bir API/anahtar GEREKMEZ — kullanıcı bu genel
        haritadan manuel export/kopyala-yapıştır yapar; MERNİS/TAKBİS gibi
        resmi API entegrasyonlarından FARKLI (bkz. ROADMAP "Yapılabilirlik
        Değerlendirmesi", bunlar ⏸ ertelendi). Anahtar adları normalize
        edilip birkaç yaygın varyasyon tek bir alana eşlenir; hiçbiri
        bulunamazsa boş sözlük döner (mevcut davranış DEĞİŞMEZ).
        """
        norm = {str(k).strip().lower(): v for k, v in props.items()}

        def pick(*keys):
            for k in keys:
                v = norm.get(k)
                if v not in (None, ""):
                    return v
            return None

        out = {}
        il = pick("il", "il_adi", "il_ad")
        ilce = pick("ilce", "ilce_adi", "ilce_ad")
        mahalle = pick("mahalle", "mahalle_adi", "mahalle_ad", "koy", "koy_adi")
        ada = pick("ada_no", "ada", "adano")
        parsel = pick("parsel_no_tapu", "parsel", "parselno", "pin")
        if il is not None:
            out["il"] = str(il)
        if ilce is not None:
            out["ilce"] = str(ilce)
        if mahalle is not None:
            out["mahalle"] = str(mahalle)
        if ada is not None:
            out["ada_no"] = str(ada)
        if parsel is not None:
            out["parsel_no_tapu"] = str(parsel)
        return out

    count = await db.parcels.count_documents({})
    created = []
    errors = []
    for i, feat in enumerate(features):
        try:
            geom = feat.get("geometry")
            props = feat.get("properties", {}) or {}
            if not geom or geom.get("type") != "Polygon":
                gtype = (geom or {}).get("type") or "geometri yok"
                # Nokta/çizgi bir parsel OLAMAZ (alanı yok) — kullanıcı KML/GeoJSON
                # export'unda parsellerin yanında etiket (Point) / sınır çizgisi
                # (LineString) da olabilir; bunlar sessizce değil, AÇIK nedenle atlanır.
                errors.append({"index": i, "error": f"Parsel değil ({gtype}) — sadece Polygon içe aktarılır"})
                continue

            # 3B koordinatları (yükseklik) 2B'ye indir — hem alan hesabı hem
            # 2dsphere index için gerekli (Google Earth/KML dosyaları 3B gelir).
            geom = {"type": "Polygon", "coordinates": _to_2d_coords(geom["coordinates"])}

            # Çiftçi ARTIK OPSİYONEL — dosyada veya istekte farmer_id yoksa parsel
            # "atanmamış" olarak oluşturulur; kullanıcı sonra parselden çiftçi atar.
            farmer_id = props.get("farmer_id") or body.farmer_id
            farmer = None
            if farmer_id:
                farmer = await db.farmers.find_one({"id": farmer_id}, {"_id": 0})
                if not farmer:
                    # Anahtar verilmiş ama geçersiz -> bu bir hatadır (sessizce atanmamış yapma).
                    errors.append({"index": i, "error": f"Çiftçi bulunamadı: {farmer_id}"})
                    continue

            # IT-16 — TKGM export'u alanı genelde "alan"/"yuzolcum" adıyla
            # ve m² cinsinden verir (area_dekar YOK) — bu durumda dekara çevrilir.
            area = props.get("area_dekar")
            if area is None:
                alan_m2 = props.get("alan") or props.get("yuzolcum")
                if alan_m2 is not None:
                    try:
                        area = round(float(alan_m2) / 1000, 1)
                    except (TypeError, ValueError):
                        area = None
            if area is None:
                area = _shoelace_area_dekar(geom["coordinates"])

            tkgm_fields = _extract_tkgm_fields(props)

            # Yeni import edilen parsellerde henüz uydu/AI verisi yok —
            # "veri yok" yerine nötr bir varsayılan atanıyor ki dashboard
            # KPI'ları (risky_parcels, avg_ndvi) bu parselleri de sayabilsin.
            # İlk gerçek uydu taraması geldiğinde bu değer güncellenecek.
            default_ndvi = 0.65
            default_name = f"İçe Aktarılan Parsel {i+1}"
            if "ada_no" in tkgm_fields or "parsel_no_tapu" in tkgm_fields:
                default_name = f"Ada {tkgm_fields.get('ada_no', '?')} Parsel {tkgm_fields.get('parsel_no_tapu', '?')}"
            doc = {
                "id": str(uuid.uuid4()),
                "parcel_code": f"PRS-{(count + len(created) + 1):05d}",
                "name": props.get("name", default_name),
                "farmer_id": farmer_id,                       # None ise "atanmamış"
                "village": props.get("village", (farmer.get("village", "") if farmer else "")),
                "region_id": (farmer["region_id"] if farmer else None),
                "area_dekar": area,
                "soil_type": props.get("soil_type", body.default_soil_type),
                "irrigation": props.get("irrigation", body.default_irrigation),
                "geometry": geom,
                **tkgm_fields,
                "current_crop": props.get("crop", "Şeker Pancarı"),
                "active_season": datetime.now().year,
                "ndvi_latest": default_ndvi,
                "risk_level": "sari",
                "risk_label": "İzlemeye Değer (henüz uydu taraması yok)",
                "expected_yield_ton": round(area * 5.5, 1),
                "last_satellite_scan": None,
                "imported": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            created.append(doc)
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    if created:
        await db.parcels.insert_many(created)
        for d in created:
            d.pop("_id", None)

    await log_audit(db, user, action="import", entity="parcel", entity_id=None,
                     new_value={"created_count": len(created), "error_count": len(errors)}, request=request)
    return {"created_count": len(created), "error_count": len(errors), "created": created, "errors": errors}


# =====================================================================
#                       TOPRAK BİLGİSİ MODÜLÜ (M06)
# =====================================================================

@api_router.get("/soil-samples")
async def list_soil_samples(user=Depends(current_user)):
    """Tüm toprak analizleri (admin)"""
    docs = await db.soil_samples.find({"is_active": {"$ne": False}}, {"_id": 0}).sort([("date", -1)]).to_list(500)
    return docs


@api_router.get("/soil-samples/summary")
async def soil_summary(user=Depends(current_user)):
    """
    Toprak analiz özeti — admin dashboard için.
    
    Toplam numune, ortalama pH/EC/OM,
    pH dağılımı (asitli/nötr/alkalin),
    önerilen gübre tipleri.
    """
    samples = await db.soil_samples.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(5000)

    if not samples:
        return {"total": 0, "avg_ph": 0, "ph_distribution": [], "recent": []}
    
    avg_ph = sum(s.get("ph", 0) for s in samples) / len(samples)
    avg_ec = sum(s.get("ec", 0) for s in samples) / len(samples)
    avg_om = sum(s.get("organic_matter_pct", 0) for s in samples) / len(samples)
    
    # pH bantları
    ph_dist = {"Asitli (<6.5)": 0, "Nötr (6.5-7.5)": 0, "Hafif Alkalin (7.5-8.0)": 0, "Alkalin (>8.0)": 0}
    for s in samples:
        ph = s.get("ph", 7)
        if ph < 6.5:
            ph_dist["Asitli (<6.5)"] += 1
        elif ph < 7.5:
            ph_dist["Nötr (6.5-7.5)"] += 1
        elif ph < 8.0:
            ph_dist["Hafif Alkalin (7.5-8.0)"] += 1
        else:
            ph_dist["Alkalin (>8.0)"] += 1
    
    return {
        "total": len(samples),
        "avg_ph": round(avg_ph, 2),
        "avg_ec": round(avg_ec, 2),
        "avg_om": round(avg_om, 2),
        "ph_distribution": [{"label": k, "count": v} for k, v in ph_dist.items()],
        "recent": sorted(samples, key=lambda s: s.get("date", ""), reverse=True)[:15]
    }


# =====================================================================
#                       SÖZLEŞMELER (M04)
# =====================================================================

@api_router.get("/contracts")
async def list_contracts(season: Optional[int] = None, status: Optional[str] = None, user=Depends(current_user)):
    # BULGU 1 düzeltmesi: soft-delete edilmiş sözleşmeler listelenmez.
    filt: Dict[str, Any] = {"is_active": {"$ne": False}}
    if season: filt["season"] = season
    if status: filt["status"] = status
    docs = await db.contracts.find(filt, {"_id": 0}).to_list(5000)
    return docs


# =====================================================================
#                       EKİM (M05)
# =====================================================================

@api_router.get("/plantings")
async def list_plantings(season: Optional[int] = None, user=Depends(current_user)):
    filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
    if season: filt["season"] = season
    docs = await db.plantings.find(filt, {"_id": 0}).to_list(5000)
    return docs


# =====================================================================
#                       SULAMA (M15)
# =====================================================================

@api_router.get("/irrigation/summary")
async def irrigation_summary(user=Depends(current_user)):
    """
    Sulama modülü özet verileri.
    Bu endpoint çiftçiler veri eklediğinde otomatik güncellenir.
    """
    events = await db.irrigation_events.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(20000)
    sources = await db.water_sources.find({}, {"_id": 0}).to_list(100)
    regions = await db.regions.find({}, {"_id": 0}).to_list(100)
    
    total_m3 = sum(e.get("water_m3", 0) for e in events)
    
    # Bölge bazlı
    by_region = []
    for r in regions:
        r_events = [e for e in events if e.get("region_id") == r["id"]]
        by_region.append({
            "name": r["name"],
            "water_m3": sum(e.get("water_m3", 0) for e in r_events),
            "events": len(r_events)
        })
    
    # Yönteme göre
    by_method = {}
    for e in events:
        m = e.get("method", "diğer")
        by_method[m] = by_method.get(m, 0) + e.get("water_m3", 0)
    
    # Kuraklık risk (her bölge için random + tutarlı seed)
    # Üretim sürümünde Sentinel Hub + hava verileriyle hesaplanır
    random.seed(2026)
    drought_risk = [
        {"region": r["name"], "risk_pct": random.randint(15, 85), "level": random.choice(["düşük", "orta", "yüksek"])}
        for r in regions
    ]
    
    return {
        "total_m3": round(total_m3, 1),
        "events_count": len(events),
        "water_sources": sources,
        "by_region": by_region,
        "by_method": [{"method": k, "m3": v} for k, v in by_method.items()],
        "drought_risk": drought_risk
    }


@api_router.get("/irrigation/events")
async def list_irrigation_events(farmer_id: Optional[str] = None, limit: int = 200, user=Depends(current_user)):
    """Sulama olayları listesi (filtreli)"""
    filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
    if farmer_id: filt["farmer_id"] = farmer_id
    docs = await db.irrigation_events.find(filt, {"_id": 0}).sort([("date", -1)]).limit(limit).to_list(limit)
    return docs


# =====================================================================
#                       OPERASYON (M16)
# =====================================================================

@api_router.get("/operations/tasks")
async def list_tasks(status: Optional[str] = None, user=Depends(current_user)):
    # BULGU 1 düzeltmesi: soft-delete edilmiş görevler listelenmez.
    filt: Dict[str, Any] = {"is_active": {"$ne": False}}
    if status: filt["status"] = status
    docs = await db.tasks.find(filt, {"_id": 0}).sort([("scheduled_date", 1)]).to_list(1000)
    return docs


@api_router.get("/operations/machines")
async def list_machines(user=Depends(current_user)):
    # BULGU 1 düzeltmesi: soft-delete edilmiş makineler listelenmez.
    return await db.machines.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(500)


@api_router.get("/operations/workers")
async def list_workers(user=Depends(current_user)):
    # BULGU 1 düzeltmesi: soft-delete edilmiş işçiler listelenmez.
    return await db.workers.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(500)


@api_router.get("/operations/summary")
async def operations_summary(user=Depends(current_user)):
    tasks = await db.tasks.find({}, {"_id": 0}).to_list(5000)
    machines = await db.machines.find({}, {"_id": 0}).to_list(500)
    status_count = {}
    type_count = {}
    for t in tasks:
        status_count[t.get("status", "planlı")] = status_count.get(t.get("status", "planlı"), 0) + 1
        type_count[t.get("task_type", "diğer")] = type_count.get(t.get("task_type", "diğer"), 0) + 1
    return {
        "tasks_total": len(tasks),
        "by_status": status_count,
        "by_type": type_count,
        "machines_total": len(machines),
        "machines_active": len([m for m in machines if m.get("status") == "aktif"]),
        "machines_maintenance": len([m for m in machines if m.get("status") == "bakım"])
    }


# =====================================================================
#                       VERİMLİLİK ANALİTİK (M17)
# =====================================================================

@api_router.get("/analytics/yields")
async def yields_analytics(season: Optional[int] = None, user=Depends(current_user)):
    filt: Dict[str, Any] = {}
    if season: filt["season"] = season
    yields = await db.yields.find(filt, {"_id": 0}).to_list(10000)
    
    # Bölge bazlı toplama
    by_region = {}
    for y in yields:
        rid = y.get("region_id")
        if rid not in by_region:
            by_region[rid] = {"ton": 0, "dekar": 0, "polar_sum": 0, "count": 0}
        by_region[rid]["ton"] += y.get("actual_ton", 0)
        by_region[rid]["dekar"] += y.get("area_dekar", 0)
        by_region[rid]["polar_sum"] += y.get("polar_oran", 16)
        by_region[rid]["count"] += 1
    
    regions = await db.regions.find({}, {"_id": 0}).to_list(100)
    region_stats = []
    for r in regions:
        b = by_region.get(r["id"], {"ton": 0, "dekar": 0, "polar_sum": 0, "count": 0})
        region_stats.append({
            "region": r["name"],
            "ton": round(b["ton"], 1),
            "dekar": round(b["dekar"], 1),
            "ton_per_dekar": round(b["ton"] / max(b["dekar"], 1), 2),
            "avg_polar": round(b["polar_sum"] / max(b["count"], 1), 2)
        })
    
    # 5 yıllık trend
    trend = []
    all_y = await db.yields.find({}, {"_id": 0}).to_list(10000)
    for yr in range(2021, 2026):
        y_year = [y for y in all_y if y.get("season") == yr]
        if y_year:
            t_ton = sum(y.get("actual_ton", 0) for y in y_year)
            t_dekar = sum(y.get("area_dekar", 0) for y in y_year)
            trend.append({
                "year": yr,
                "ton_per_dekar": round(t_ton / max(t_dekar, 1), 2),
                "total_ton": round(t_ton, 1)
            })
    
    top_parcels = sorted(yields, key=lambda y: y.get("actual_ton", 0) / max(y.get("area_dekar", 1), 1), reverse=True)[:10]
    
    return {
        "by_region": region_stats,
        "trend": trend,
        "top_parcels": top_parcels[:10],
        "total_parcels": len(yields)
    }


@api_router.get("/analytics/scenario")
async def scenario_simulation(drought_pct: int = 0, price_pct: int = 0, cost_pct: int = 0, user=Depends(current_user)):
    """What-if senaryo simülasyonu — kuraklık/fiyat/maliyet etkisi"""
    yields = await db.yields.find({"season": 2025}, {"_id": 0}).to_list(10000)
    base_ton = sum(y.get("actual_ton", 0) for y in yields)
    base_revenue = base_ton * 1800                          # Ortalama pancar fiyatı TL/ton
    base_cost = base_revenue * 0.55                         # Tahmini maliyet oranı %55
    
    new_ton = base_ton * (1 - drought_pct / 100)
    new_price = 1800 * (1 + price_pct / 100)
    new_revenue = new_ton * new_price
    new_cost = base_cost * (1 + cost_pct / 100)
    
    return {
        "base": {"ton": round(base_ton, 1), "revenue": round(base_revenue), "cost": round(base_cost), "profit": round(base_revenue - base_cost)},
        "scenario": {
            "ton": round(new_ton, 1),
            "revenue": round(new_revenue),
            "cost": round(new_cost),
            "profit": round(new_revenue - new_cost),
            "profit_delta_pct": round(((new_revenue - new_cost) - (base_revenue - base_cost)) / max(base_revenue - base_cost, 1) * 100, 1)
        }
    }


# =====================================================================
#                       DİĞER (Lojistik, Karne, Bildirim)
# =====================================================================

@api_router.get("/regions")
async def list_regions(user=Depends(current_user)):
    """IT-33 — lookup verisi (nadiren değişir) cache.py üzerinden okunur
    (bkz. cache.py docstring'i — arayüz Redis'e geçilirse aynı kalır)."""
    from cache import cache_get_or_set
    return await cache_get_or_set("regions:list", 60, lambda: db.regions.find({}, {"_id": 0}).to_list(100))


@api_router.get("/logistics/appointments")
async def list_appointments(farmer_id: Optional[str] = None, user=Depends(current_user)):
    filt: Dict[str, Any] = {"is_active": {"$ne": False}}   # soft-delete edilenleri gizle
    if farmer_id: filt["farmer_id"] = farmer_id
    return await db.appointments.find(filt, {"_id": 0}).sort([("scheduled_at", 1)]).to_list(500)


@api_router.get("/notifications")
async def list_notifications(user=Depends(current_user)):
    return await db.notifications.find({}, {"_id": 0}).sort([("created_at", -1)]).to_list(200)


@api_router.get("/notifications/unread-count")
async def unread_notification_count(user=Depends(current_user)):
    """IT-12 — Bildirim çekmecesindeki zil rozeti için. Bildirimler tenant
    genelidir (kullanıcı bazlı gelen kutusu değil — mevcut veri modeliyle
    tutarlı), yani bu sayı tüm kooperatif için ortaktır."""
    count = await db.notifications.count_documents({"status": {"$ne": "okundu"}})
    return {"count": count}


@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user=Depends(current_user)):
    old = await db.notifications.find_one({"id": notification_id}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Bildirim bulunamadı")
    await db.notifications.update_one({"id": notification_id}, {"$set": {"status": "okundu"}})
    return {"status": "ok"}


@api_router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(user=Depends(current_user)):
    result = await db.notifications.update_many({"status": {"$ne": "okundu"}}, {"$set": {"status": "okundu"}})
    return {"status": "ok", "updated": result.modified_count}


@api_router.get("/karne/top")
async def karne_top(limit: int = 10, user=Depends(current_user)):
    return await db.farmers.find({}, {"_id": 0}).sort([("karne_points", -1)]).limit(limit).to_list(limit)


@api_router.get("/karne/bottom")
async def karne_bottom(limit: int = 10, user=Depends(current_user)):
    return await db.farmers.find({}, {"_id": 0}).sort([("karne_points", 1)]).limit(limit).to_list(limit)


# =====================================================================
#                       SEED VERİSİ
# =====================================================================

def _require_seed_authority(user: dict):
    """Seed uçları sadece platform_admin / super_admin / kurumsal admin
    katmanı (ADMIN_TIER_ROLES) tarafından çağrılabilir — bkz. ROADMAP P0
    bulgusu: kimlik doğrulaması olmayan çağrılar demo verisini silip
    yeniden oluşturabiliyordu. platform_admin uygulama açılışında zaten
    otomatik bootstrap edildiği için (bkz. startup event) bu kontrol
    "ilk kurulum" akışını KIRMAZ — operatör önce platform_admin ile giriş
    yapıp aldığı token'la bu uca çağrı yapar."""
    role = user.get("role")
    if role != "platform_admin" and role not in ADMIN_TIER_ROLES and role != "super_admin":
        raise HTTPException(403, "Bu işlem için yönetici yetkisi gerekir")


@api_router.post("/admin/seed")
async def seed_data(force: bool = False, user=Depends(current_user)):
    """
    Idempotent seed işlemi.

    `force=true` parametresi geçilirse mevcut veriyi temizleyip yeniden yükler.
    Aksi halde sadece veri yoksa yükler.

    Tenant davranışı: bu çağrı zaten giriş yapmış bir tenant admin'i
    tarafından (Authorization header ile) yapılıyorsa, seed verisi O
    tenant'a yazılır (kendi kooperatifinin demo verisini oluşturur/sıfırlar).
    Platform admin tenant_id taşımadığı için (current_tenant_id None kalır),
    "default" adlı bir tenant otomatik bulunur/oluşturulur ve veri oraya
    yazılır — mevcut demo giriş bilgileri (admin@kooperatif.com vb.)
    böylece değişmeden çalışmaya devam eder.

    Kimlik doğrulaması ve yönetici yetkisi ZORUNLUDUR (P0 güvenlik
    düzeltmesi — daha önce anonim çağrılar mevcut tenant'ın verisini
    silip yeniden oluşturabiliyordu). Ayrıca ALLOW_DATA_SEEDING=false
    (üretimde varsayılan) iken bu uç tamamen kapalıdır.
    """
    if not ALLOW_DATA_SEEDING:
        raise HTTPException(403, "Demo veri yükleme bu ortamda kapalı (ALLOW_DATA_SEEDING=false)")
    _require_seed_authority(user)

    reset_token = None
    if current_tenant_id.get() is None:
        default_tenant = await raw_db.tenants.find_one({"slug": "default"}, {"_id": 0})
        if not default_tenant:
            default_tenant = {
                "id": str(uuid.uuid4()),
                "name": "Toprax Demo Kooperatifi",
                "slug": "default",
                "contact_email": "demo@toprax.local",
                "plan": "deneme",
                "status": "aktif",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "system-bootstrap",
            }
            await raw_db.tenants.insert_one(dict(default_tenant))
        reset_token = current_tenant_id.set(default_tenant["id"])

    try:
        return await _run_seed(force)
    finally:
        if reset_token is not None:
            current_tenant_id.reset(reset_token)


async def _run_seed(force: bool = False):
    if not force and await db.users.count_documents({}) > 0:
        return {"status": "already_seeded", "hint": "Sıfırlamak için ?force=true ekleyin"}
    
    # Force ise tüm koleksiyonları temizle (SADECE mevcut tenant'ınkiler —
    # db zaten tenant-scoped olduğu için delete_many otomatik filtrelenir)
    if force:
        collections = ["users", "regions", "farmers", "parcels", "contracts",
                       "plantings", "yields", "soil_samples", "water_sources",
                       "irrigation_plans", "irrigation_events", "machines",
                       "workers", "tasks", "appointments", "finance", "notifications",
                       "iot_sensors", "drone_missions"]
        for c in collections:
            await db[c].delete_many({})
    
    now = datetime.now(timezone.utc).isoformat()
    random.seed(42)  # Tekrarlanabilir veri için sabit seed
    
    # ============ ADMİN KULLANICILARI ============
    admin_users = [
        {"id": str(uuid.uuid4()), "email": "admin@turkseker.com.tr", "password": hash_pw("admin123"),
         "full_name": "Sistem Yöneticisi", "role": "super_admin", "created_at": now},
        {"id": str(uuid.uuid4()), "email": "ahmet.yilmaz@turkseker.com.tr", "password": hash_pw("ahmet123"),
         "full_name": "Ahmet Yılmaz", "role": "fabrika_muduru", "region": "Konya", "created_at": now},
        {"id": str(uuid.uuid4()), "email": "mehmet.demir@turkseker.com.tr", "password": hash_pw("mehmet123"),
         "full_name": "Mehmet Demir", "role": "ziraat_muhendisi", "region": "Konya", "created_at": now},
        {"id": str(uuid.uuid4()), "email": "ayse.kaya@turkseker.com.tr", "password": hash_pw("ayse123"),
         "full_name": "Ayşe Kaya", "role": "saha_personeli", "region": "Konya", "created_at": now},
        {"id": str(uuid.uuid4()), "email": "kantar@turkseker.com.tr", "password": hash_pw("kantar123"),
         "full_name": "Hasan Kantarcı", "role": "kantar_personeli", "region": "Konya", "created_at": now},
        {"id": str(uuid.uuid4()), "email": "toprak@turkseker.com.tr", "password": hash_pw("toprak123"),
         "full_name": "Fatma Toprakçı", "role": "toprak_personeli", "region": "Konya", "created_at": now},
    ]
    await db.users.insert_many(admin_users)
    
    # ============ BÖLGELER ============
    region_names = [
        ("Konya", "Konya / İç Anadolu"), ("Eskişehir", "Eskişehir Bölgesi"),
        ("Kayseri", "Kayseri / Boğazlıyan"), ("Erzurum", "Erzurum / Doğu Anadolu"),
        ("Afyon", "Afyonkarahisar"), ("Çorum", "Çorum / Karadeniz"),
        ("Ankara", "Ankara / Polatlı"), ("Yozgat", "Yozgat / Boğazlıyan")
    ]
    regions = [{"id": str(uuid.uuid4()), "name": n, "description": d, "active": True} for n, d in region_names]
    await db.regions.insert_many(regions)
    
    # ============ ÇİFTÇİLER ============
    first_names = ["Ahmet", "Mehmet", "Mustafa", "Ali", "Hasan", "Hüseyin", "İbrahim", "Osman",
                   "Yusuf", "Ramazan", "Recep", "Süleyman", "Kadir", "Mahmut", "Bekir", "Cemal",
                   "Halil", "İsmail", "Ömer", "Ekrem", "Sabri", "Veli", "Murat", "Salih", "Adem"]
    last_names = ["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Yıldırım", "Öztürk",
                  "Aydın", "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara",
                  "Koç", "Kurt", "Özkan", "Şimşek", "Tekin", "Polat", "Bulut", "Acar", "Erdoğan"]
    villages = ["Hacıveli", "Kuzucu", "Yenidoğan", "Aşağıçiğil", "Sarıkamış", "Karaköy", "Çamlıdere",
                "Pınarbaşı", "Akpınar", "Yeşilköy", "Doğanca", "Gümüşpınar", "Boyalıca", "Ovacık",
                "Beyköy", "Karaağaç"]
    
    farmers = []
    farmer_user_records = []                                # Her çiftçi için bir login hesabı
    
    for i in range(200):
        farmer_id = str(uuid.uuid4())
        rid = random.choice(regions)["id"]
        karne_pt = random.randint(35, 98)
        karne = "A" if karne_pt >= 85 else "B" if karne_pt >= 70 else "C" if karne_pt >= 55 else "D"
        member_no = f"TS-{(i+1):05d}"
        full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        
        farmer = {
            "id": farmer_id,
            "member_no": member_no,
            "full_name": full_name,
            "tc_no": f"{random.randint(10000000000, 99999999999)}",
            "phone": f"05{random.randint(30, 59)}{random.randint(1000000, 9999999)}",
            "email": f"{member_no.lower()}@ciftci.tr",      # Çiftçi giriş email'i
            "village": random.choice(villages),
            "region_id": rid,
            "iban": f"TR{random.randint(10**23, 10**24 - 1)}",
            "karne_score": karne,
            "karne_points": karne_pt,
            "status": "aktif" if random.random() > 0.05 else "pasif",
            "membership_year": random.choice([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]),
            "created_at": now
        }
        farmers.append(farmer)
        
        # Her çiftçi için login kullanıcısı oluştur (ÖNEMLİ — self-servis için)
        # Email: ts-00001@ciftci.tr / Şifre: ciftci123
        farmer_user_records.append({
            "id": str(uuid.uuid4()),
            "email": f"{member_no.lower()}@ciftci.tr",
            "password": hash_pw("ciftci123"),
            "full_name": full_name,
            "role": "ciftci",
            "farmer_id": farmer_id,                         # Hangi çiftçi profiline bağlı
            "created_at": now
        })
    
    await db.farmers.insert_many(farmers)
    await db.users.insert_many(farmer_user_records)
    
    # ============ PARSELLER ============
    soil_types = ["Killi", "Kumlu", "Tınlı", "Kireçli", "Killi-Tınlı"]
    irrigation_types = ["Damla", "Yağmurlama", "Karık", "Yok"]
    parcels = []

    # Her bölge için gerçekçi bir merkez koordinat (Türkiye şeker pancarı
    # kuşağı — Konya/Çumra ağırlıklı, roadmap'te belirtildiği gibi).
    # Böylece parseller "Türkiye'nin her yerine rastgele saçılmış" değil,
    # köy/bölge bazında gerçekçi kümeler halinde oluşur.
    region_centers = {
        "Konya": (37.51, 32.77),        # Çumra/Konya
        "Eskişehir": (39.78, 30.52),
        "Kayseri": (38.73, 35.49),
        "Erzurum": (39.90, 41.27),
        "Afyon": (38.76, 30.54),
        "Çorum": (40.55, 34.95),
        "Ankara": (39.58, 32.13),       # Polatlı
        "Yozgat": (39.82, 34.80),
    }
    # Köy başına küçük bir ofset — aynı köydeki parseller birbirine yakın olsun
    village_offsets = {v: (random.uniform(-0.06, 0.06), random.uniform(-0.06, 0.06)) for v in villages}

    # ÖNEMLİ: Her çiftçiye en az 1 parsel ver (ilk 200 parsel sırayla)
    # Kalan parseller rastgele çiftçilere ek olarak dağıtılır (bazı
    # çiftçiler 2-6 parselli olur — gerçek kooperatif dağılımına benzer).
    TOTAL_PARCELS = 1000
    for i in range(TOTAL_PARCELS):
        if i < len(farmers):
            farmer = farmers[i]                              # İlk 200'ü sırayla → herkese 1 parsel
        else:
            farmer = random.choice(farmers)                  # Kalanlar random (bazı çiftçiler çok parselli olur)

        region = next(r for r in regions if r["id"] == farmer["region_id"])
        center_lat, center_lng = region_centers.get(region["name"], (39.0, 33.0))
        voff_lat, voff_lng = village_offsets[farmer["village"]]

        # Gerçek bir tarla ölçeğinde konum: bölge merkezi + köy ofseti +
        # küçük rastgele sapma (birkaç km içinde, GERÇEKÇİ tarla kümesi)
        base_lat = center_lat + voff_lat + random.uniform(-0.015, 0.015)
        base_lng = center_lng + voff_lng + random.uniform(-0.015, 0.015)

        area_dekar = round(random.uniform(15, 350), 1)
        # Polygon boyutunu alana göre orantıla (100 dekar ≈ 0.001° kare civarı)
        d = 0.0008 + (area_dekar / 350) * 0.0025
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [base_lng, base_lat],
                [base_lng + d, base_lat],
                [base_lng + d, base_lat + d],
                [base_lng, base_lat + d],
                [base_lng, base_lat]                        # İlk noktaya geri dön (kapalı polygon)
            ]]
        }

        # NDVI ve risk skoru — birbirleriyle TUTARLI üretiliyor (düşük NDVI
        # → yüksek risk), rastgele bağımsız değerler değil.
        ndvi_latest = round(random.uniform(0.35, 0.92), 3)
        if ndvi_latest > 0.72:
            risk_level, risk_label = "yesil", "Düşük Risk"
        elif ndvi_latest > 0.55:
            risk_level, risk_label = "sari", "İzlemeye Değer"
        elif ndvi_latest > 0.42:
            risk_level, risk_label = "turuncu", "Riskli"
        else:
            risk_level, risk_label = "kirmizi", "Acil Müdahale"

        parcels.append({
            "id": str(uuid.uuid4()),
            "parcel_code": f"KNY-{(i+1):04d}" if region["name"] == "Konya" else f"PRS-{(i+1):05d}",
            "name": f"{farmer['village']} Tarlası {i+1}",
            "farmer_id": farmer["id"],
            "village": farmer["village"],
            "region_id": farmer["region_id"],
            "area_dekar": area_dekar,
            "soil_type": random.choice(soil_types),
            "irrigation": random.choice(irrigation_types),
            "geometry": geometry,
            "current_crop": "Şeker Pancarı",
            "active_season": 2025,
            "ndvi_latest": ndvi_latest,
            "risk_level": risk_level,          # yesil | sari | turuncu | kirmizi
            "risk_label": risk_label,
            "expected_yield_ton": round(area_dekar * random.uniform(4.5, 7.2) * (0.7 + ndvi_latest * 0.5), 1),
            "last_satellite_scan": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 12))).isoformat(),
            "created_at": now
        })
    await db.parcels.insert_many(parcels)
    
    # ============ SÖZLEŞMELER ============
    contracts = []
    for p in parcels:
        for season in [2024, 2025]:
            contracts.append({
                "id": str(uuid.uuid4()),
                "contract_no": f"SZ-{season}-{p['parcel_code'][-5:]}",
                "season": season,
                "farmer_id": p["farmer_id"],
                "parcel_id": p["id"],
                "region_id": p["region_id"],
                "crop": "Şeker Pancarı",
                "variety": random.choice(["Lider", "Adrianna KWS", "Marbella", "Vivianna"]),
                "kota_dekar": p["area_dekar"],
                "kota_ton": round(p["area_dekar"] * random.uniform(5, 7), 1),
                "advance_seed_kg": round(p["area_dekar"] * 0.18, 1),
                "advance_fertilizer_kg": round(p["area_dekar"] * 35, 1),
                "status": "imzalı" if random.random() > 0.08 else random.choice(["taslak", "imzalı", "imzalı"]),
                "created_at": now
            })
    await db.contracts.insert_many(contracts)
    
    # ============ EKİM + VERİM ============
    plantings = []
    yields_list = []
    for c in contracts:
        plantings.append({
            "id": str(uuid.uuid4()),
            "contract_id": c["id"],
            "parcel_id": c["parcel_id"],
            "farmer_id": c["farmer_id"],
            "region_id": c["region_id"],
            "season": c["season"],
            "crop": c["crop"],
            "variety": c["variety"],
            "planting_date": f"{c['season']}-03-{random.randint(10, 28):02d}",
            "expected_harvest_date": f"{c['season']}-10-{random.randint(1, 30):02d}",
            "actual_harvest_date": f"{c['season']}-10-{random.randint(5, 30):02d}" if c["season"] < 2026 else None,
            "stage": "hasat" if c["season"] < 2025 else random.choice(["ekim", "gelişim", "olgunlaşma", "hasat"])
        })
        if c["season"] <= 2025:
            actual_ton = c["kota_ton"] * random.uniform(0.65, 1.15)
            yields_list.append({
                "id": str(uuid.uuid4()), "parcel_id": c["parcel_id"], "farmer_id": c["farmer_id"],
                "region_id": c["region_id"], "season": c["season"], "crop": c["crop"],
                "area_dekar": c["kota_dekar"], "expected_ton": c["kota_ton"],
                "actual_ton": round(actual_ton, 2), "polar_oran": round(random.uniform(14.5, 18.5), 2)
            })
    # Geçmiş yıl verim
    for yr in [2021, 2022, 2023]:
        for p in random.sample(parcels, 500):
            actual_ton = p["area_dekar"] * random.uniform(4.8, 6.8)
            yields_list.append({
                "id": str(uuid.uuid4()), "parcel_id": p["id"], "farmer_id": p["farmer_id"],
                "region_id": p["region_id"], "season": yr, "crop": "Şeker Pancarı",
                "area_dekar": p["area_dekar"], "expected_ton": round(p["area_dekar"] * 6, 1),
                "actual_ton": round(actual_ton, 2), "polar_oran": round(random.uniform(14, 18), 2)
            })
    await db.plantings.insert_many(plantings)
    await db.yields.insert_many(yields_list)
    
    # ============ TOPRAK ANALİZLERİ ============
    soil_samples = []
    for p in random.sample(parcels, 400):
        ph = round(random.uniform(6.5, 8.2), 2)
        n = random.randint(15, 80)
        # Akıllı öneri: pH ve N seviyesine göre
        if n < 30:
            rec = "Acil azot uygulaması — Üre 40 kg/dekar"
        elif ph > 7.8:
            rec = "Alkalin toprak — Asit içerikli DAP tercih et, 25 kg/dekar"
        else:
            rec = "Standart DAP 25 kg/dekar + Üre 30 kg/dekar"
        
        soil_samples.append({
            "id": str(uuid.uuid4()),
            "parcel_id": p["id"],
            "date": f"2025-{random.randint(1, 6):02d}-{random.randint(1, 28):02d}",
            "lab_name": random.choice(["Konya Tarım Lab", "Eskişehir Toprak Analiz", "TÜBİTAK MAM"]),
            "ph": ph,
            "ec": round(random.uniform(0.3, 1.8), 2),
            "organic_matter_pct": round(random.uniform(1.2, 4.5), 2),
            "n_ppm": n,
            "p_ppm": random.randint(8, 45),
            "k_ppm": random.randint(120, 380),
            "recommendation": rec
        })
    await db.soil_samples.insert_many(soil_samples)
    
    # ============ SU KAYNAKLARI ============
    water_sources = []
    for r in regions:
        for i in range(random.randint(2, 5)):
            water_sources.append({
                "id": str(uuid.uuid4()),
                "name": f"{r['name']} {random.choice(['Artezyen', 'Kanal', 'Göl', 'Yer Altı'])} {i+1}",
                "type": random.choice(["artezyen", "kanal", "göl", "yer altı"]),
                "region_id": r["id"],
                "capacity_m3_per_day": random.randint(500, 5000),
                "current_level_pct": random.randint(30, 95),
                "status": "aktif"
            })
    await db.water_sources.insert_many(water_sources)
    
    # ============ SULAMA PLANLARI + OLAYLARI ============
    irrigation_plans = []
    irrigation_events = []
    methods = ["damla", "yağmurlama", "karık"]
    for p in random.sample(parcels, 450):
        method = random.choice(methods)
        irrigation_plans.append({
            "id": str(uuid.uuid4()), "parcel_id": p["id"], "farmer_id": p["farmer_id"],
            "region_id": p["region_id"], "season": 2025, "method": method,
            "planned_turns": random.randint(4, 12),
            "planned_m3": round(p["area_dekar"] * random.uniform(35, 65), 1),
            "start_date": "2025-05-15", "end_date": "2025-09-15"
        })
        for ev in range(random.randint(2, 8)):
            irrigation_events.append({
                "id": str(uuid.uuid4()), "parcel_id": p["id"], "farmer_id": p["farmer_id"],
                "region_id": p["region_id"],
                "date": f"2025-{random.randint(5, 9):02d}-{random.randint(1, 28):02d}",
                "method": method,
                "water_m3": round(p["area_dekar"] * random.uniform(4, 8), 1),
                "moisture_before": random.randint(15, 35), "moisture_after": random.randint(55, 85)
            })
    await db.irrigation_plans.insert_many(irrigation_plans)
    await db.irrigation_events.insert_many(irrigation_events)
    
    # ============ MAKİNELER ============
    machine_types = [
        ("Traktör", ["John Deere 6120M", "Case IH Maxxum 130", "New Holland T6.140", "Massey Ferguson 5713 S"]),
        ("Pulluk", ["Lemken Juwel 8", "Kverneland LB 100", "Özkardeşler 4'lü Pulluk"]),
        ("Biçerdöver", ["Claas Lexion 5500", "John Deere S780", "New Holland CR8.90"]),
        ("Pülverizatör", ["Tezel 600 lt", "Hardi 1000 lt", "Berthoud 800 lt"]),
        ("Ekim Makinası", ["Monosem NG Plus", "Kverneland Optima", "Mater Macc MS 8000"])
    ]
    machines = []
    for r in regions:
        for cat, models in machine_types:
            for _ in range(random.randint(1, 3)):
                machines.append({
                    "id": str(uuid.uuid4()), "type": cat, "model": random.choice(models),
                    "serial_no": f"MK-{random.randint(10000, 99999)}",
                    "region_id": r["id"],
                    "status": random.choices(["aktif", "bakım", "boşta"], weights=[0.65, 0.15, 0.2])[0],
                    "owner": random.choice(["kooperatif", "çiftçi"]),
                    "total_hours": random.randint(500, 8000),
                    "last_maintenance": f"2025-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
                })
    await db.machines.insert_many(machines)
    
    # ============ İŞÇİLER ============
    workers = []
    for r in regions:
        for _ in range(random.randint(8, 20)):
            workers.append({
                "id": str(uuid.uuid4()),
                "full_name": f"{random.choice(first_names)} {random.choice(last_names)}",
                "phone": f"05{random.randint(30, 59)}{random.randint(1000000, 9999999)}",
                "region_id": r["id"],
                "skill": random.choice(["traktör sürücüsü", "saha işçisi", "biçerdöver operatörü", "ekipman uzmanı"]),
                "daily_wage": random.choice([800, 900, 1000, 1100, 1200]),
                "status": "aktif"
            })
    await db.workers.insert_many(workers)
    
    # ============ GÖREVLER ============
    task_types = ["toprak işleme", "ekim", "gübreleme", "ilaçlama", "sulama", "hasat", "nakliye"]
    statuses = ["planlı", "devam ediyor", "tamamlandı", "iptal"]
    tasks = []
    for _ in range(150):
        p = random.choice(parcels)
        task_date = datetime.now(timezone.utc) + timedelta(days=random.randint(-30, 30))
        tasks.append({
            "id": str(uuid.uuid4()), "task_type": random.choice(task_types),
            "parcel_id": p["id"], "farmer_id": p["farmer_id"], "region_id": p["region_id"],
            "scheduled_date": task_date.isoformat(),
            "status": random.choices(statuses, weights=[0.35, 0.15, 0.45, 0.05])[0],
            "machine_id": random.choice(machines)["id"] if random.random() > 0.3 else None,
            "worker_id": random.choice(workers)["id"] if random.random() > 0.3 else None,
            "notes": "", "created_at": now
        })
    await db.tasks.insert_many(tasks)
    
    # ============ KANTAR RANDEVU ============
    appts = []
    for _ in range(80):
        f = random.choice(farmers)
        appt_date = datetime.now(timezone.utc) + timedelta(days=random.randint(-10, 30))
        appts.append({
            "id": str(uuid.uuid4()), "farmer_id": f["id"], "region_id": f["region_id"],
            "scheduled_at": appt_date.isoformat(),
            "truck_plate": f"{random.choice(['06', '34', '35', '42', '38'])} {random.choice(['ABC', 'XYZ', 'KMN'])} {random.randint(100, 999)}",
            "estimated_ton": round(random.uniform(8, 28), 1),
            "actual_ton": round(random.uniform(7, 30), 1) if random.random() > 0.5 else None,
            "polar_oran": round(random.uniform(14.5, 18), 2) if random.random() > 0.5 else None,
            "status": random.choice(["planlı", "geldi", "tartıldı", "tamamlandı"])
        })
    await db.appointments.insert_many(appts)
    
    # ============ FİNANS HAREKETLERİ ============
    finance = []
    for f in farmers:
        finance.append({
            "id": str(uuid.uuid4()), "farmer_id": f["id"], "date": "2025-03-15",
            "type": "avans", "amount": -round(random.uniform(5000, 45000), 2),
            "description": "Tohum + gübre avansı"
        })
        if random.random() > 0.3:
            finance.append({
                "id": str(uuid.uuid4()), "farmer_id": f["id"], "date": "2025-11-15",
                "type": "hakediş", "amount": round(random.uniform(40000, 280000), 2),
                "description": "Hasat hakediş"
            })
    await db.finance.insert_many(finance)

    # ============ IoT SENSÖRLER ============
    # Roadmap: "150 sensör IoT — Her sensörde Nem, Sıcaklık, Pil, Sinyal"
    iot_sensors = []
    sensor_parcels = random.sample(parcels, min(150, len(parcels)))
    for idx, p in enumerate(sensor_parcels):
        battery = random.randint(8, 100)
        signal = random.randint(1, 5)
        is_active = battery > 15 and random.random() > 0.05   # ~%5'i arızalı/offline
        iot_sensors.append({
            "id": str(uuid.uuid4()),
            "sensor_code": f"IOT-{idx+1:04d}",
            "parcel_id": p["id"],
            "parcel_code": p["parcel_code"],
            "farmer_id": p["farmer_id"],
            "region_id": p["region_id"],
            "type": random.choice(["nem_sicaklik", "toprak_nemi", "hava_istasyonu"]),
            "nem_pct": round(random.uniform(15, 85), 1),
            "sicaklik_c": round(random.uniform(8, 38), 1),
            "battery_pct": battery,
            "signal_strength": signal,               # 1-5 çubuk
            "status": "aktif" if is_active else random.choice(["offline", "bakım_gerekli"]),
            "last_reading_at": (datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 720))).isoformat(),
            "installed_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(30, 400))).isoformat(),
        })
    await db.iot_sensors.insert_many(iot_sensors)

    # ============ DRONE GÖREVLERİ ============
    # Roadmap: "45 Drone Görevi — Hastalık, Yabancı Ot, Su Stresi, Hava Durumu"
    drone_missions = []
    drone_finding_types = ["hastalık_tespiti", "yabancı_ot", "su_stresi", "genel_tarama"]
    mission_parcels = random.sample(parcels, min(45, len(parcels)))
    for idx, p in enumerate(mission_parcels):
        finding = random.choice(drone_finding_types)
        severity = random.choice(["düşük", "orta", "yüksek"]) if finding != "genel_tarama" else "yok"
        drone_missions.append({
            "id": str(uuid.uuid4()),
            "mission_code": f"DRN-{idx+1:03d}",
            "parcel_id": p["id"],
            "parcel_code": p["parcel_code"],
            "farmer_id": p["farmer_id"],
            "region_id": p["region_id"],
            "flight_date": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 45))).isoformat(),
            "pilot": random.choice(["Ahmet Yıldız (Saha)", "Otonom Uçuş", "Kemal Aydın (Saha)"]),
            "altitude_m": random.choice([50, 80, 100, 120]),
            "coverage_dekar": p["area_dekar"],
            "finding_type": finding,
            "severity": severity,
            "notes": {
                "hastalık_tespiti": "Yaprak lekesi belirtileri tespit edildi, ziraat mühendisi kontrolü önerilir.",
                "yabancı_ot": "Parsel kenarlarında yabancı ot yoğunluğu artışı gözlemlendi.",
                "su_stresi": "Bitki örtüsünde su stresine işaret eden renk değişimi tespit edildi.",
                "genel_tarama": "Anomali tespit edilmedi, gelişim normal seyrediyor.",
            }[finding],
            "status": "tamamlandı",
        })
    await db.drone_missions.insert_many(drone_missions)

    # ============ BİLDİRİMLER ============
    # Roadmap: "Her gün değişen bildirimler — Parsel KNY-742 → Nem kritik
    # seviyeye düştü" gibi SOMUT, gerçek parsel koduna bağlı mesajlar.
    notifs = []

    # 1) Genel sistem bildirimleri (hava durumu, kantar, avans, görev)
    types = ["hava_uyarısı", "sulama_hatırlatma", "kantar_randevu", "avans_bilgi", "görev_atandı"]
    titles = ["Don uyarısı - Konya bölgesi", "Sulama zamanı yaklaşıyor",
              "Kantar randevunuz onaylandı", "Avans hesabınıza yatırıldı", "Yeni görev atandı"]
    for _ in range(30):
        notifs.append({
            "id": str(uuid.uuid4()), "type": random.choice(types),
            "title": random.choice(titles),
            "message": "Sistem tarafından otomatik oluşturuldu.",
            "channel": random.choice(["sms", "whatsapp", "push", "in_app"]),
            "status": random.choice(["gönderildi", "okundu", "beklemede"]),
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 200))).isoformat()
        })

    # 2) Riskli/düşük NDVI'lı parsellerden gerçek uyarılar
    risky_parcels = [p for p in parcels if p["risk_level"] in ("turuncu", "kirmizi")]
    for p in random.sample(risky_parcels, min(25, len(risky_parcels))):
        msg = random.choice([
            f"Parsel {p['parcel_code']} → Nem kritik seviyeye düştü.",
            f"Parsel {p['parcel_code']} → NDVI değeri düşüş gösteriyor, kontrol önerilir.",
            f"Parsel {p['parcel_code']} → Yabancı ot riski oluştu.",
        ])
        notifs.append({
            "id": str(uuid.uuid4()), "type": "risk_uyarisi", "title": "Parsel Risk Uyarısı",
            "message": msg, "parcel_id": p["id"], "parcel_code": p["parcel_code"],
            "channel": "in_app", "status": random.choice(["gönderildi", "okundu"]),
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 72))).isoformat()
        })

    # 3) Hasat/verim ile ilgili olumlu bildirimler (sağlıklı parseller)
    healthy_parcels = [p for p in parcels if p["risk_level"] == "yesil"]
    for p in random.sample(healthy_parcels, min(15, len(healthy_parcels))):
        pct = random.randint(3, 12)
        msg = random.choice([
            f"Parsel {p['parcel_code']} → Hasat için uygun dönem başladı.",
            f"Parsel {p['parcel_code']} → Beklenen verim %{pct} arttı.",
        ])
        notifs.append({
            "id": str(uuid.uuid4()), "type": "hasat_bilgi", "title": "Hasat / Verim Bilgisi",
            "message": msg, "parcel_id": p["id"], "parcel_code": p["parcel_code"],
            "channel": "in_app", "status": "gönderildi",
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 48))).isoformat()
        })

    await db.notifications.insert_many(notifs)
    
    return {
        "status": "seeded",
        "counts": {
            "users": len(admin_users) + len(farmer_user_records),
            "admin_users": len(admin_users),
            "farmer_login_accounts": len(farmer_user_records),
            "regions": len(regions), "farmers": len(farmers), "parcels": len(parcels),
            "contracts": len(contracts), "plantings": len(plantings), "yields": len(yields_list),
            "soil_samples": len(soil_samples), "machines": len(machines), "workers": len(workers),
            "tasks": len(tasks), "appointments": len(appts), "irrigation_events": len(irrigation_events),
            "iot_sensors": len(iot_sensors), "drone_missions": len(drone_missions),
            "risky_parcels": len(risky_parcels)
        },
        "demo_logins": {
            "super_admin": "admin@turkseker.com.tr / admin123",
            "fabrika_muduru": "ahmet.yilmaz@turkseker.com.tr / ahmet123",
            "ziraat_muhendisi": "mehmet.demir@turkseker.com.tr / mehmet123",
            "ciftci_ornek": "ts-00001@ciftci.tr / ciftci123  (her çiftçi member_no@ciftci.tr ile)"
        }
    }


# ============ KÖK ENDPOINT (Sağlık kontrolü) ============
@api_router.get("/")
async def root():
    return {"app": APP_NAME, "full_name": APP_FULL_NAME, "version": APP_VERSION, "status": "ok"}


@api_router.get("/health")
async def health_check():
    """Kimlik dogrulamasiz, hafif liveness/readiness endpoint'i.

    PR-07 (kurulum sonrasi smoke test) ve Docker/Compose HEALTHCHECK
    tarafindan kullanilir. Kasitli olarak require_permission/current_user
    kullanmaz -- orkestrasyon katmani (Docker, k8s, load balancer) bu uca
    auth olmadan erisebilmeli. Hassas bilgi donmez (bkz. CLAUDE.md #3.1).
    """
    checks = {}
    overall_ok = True

    try:
        await raw_db.command("ping")
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        overall_ok = False
        checks["database"] = {"status": "error", "detail": "veritabanina baglanilamadi"}

    return {
        "status": "healthy" if overall_ok else "unhealthy",
        "app": APP_NAME,
        "version": APP_VERSION,
        "checks": checks,
    }


@api_router.get("/roles")
async def list_roles(user=Depends(current_user)):
    """Rol hiyerarşisini ve etiketlerini döner (frontend'de yetki gösterimi için)."""
    return {"hierarchy": ROLE_HIERARCHY, "labels": ROLE_LABELS}


# ============ ROUTER'I UYGULAMAYA BAĞLA ============
# Ek modülleri kaydet (AI, audit, NDVI, müstahsil PDF, vb.)
# Granüler yetkilendirme (Sprint 4d) — diğer modüllerden ÖNCE kurulmalı
# çünkü integrations/audit/data_entry require_permission'ı kullanıyor.
from permissions import register_permission_routes  # require_permission zaten yukarıda oluşturuldu
register_permission_routes(api_router, db, current_user, require_min_role, log_audit)

from extras import register_extra_routes
register_extra_routes(api_router, db, current_user, is_admin, require_feature)

# Uydu Görüntü Ekosistemi — Provider Abstraction (2026-07-11 araştırma raporuna
# göre genişletildi): yangın alarmı + VHR tasking talebi + sağlayıcı durumu
# uçları. Mevcut /satellite/ndvi/* uçları extras.py'de KALIYOR (yukarıda).
from satellite_provider import register_satellite_routes
register_satellite_routes(api_router, db, current_user, require_permission, log_audit)

# Saha veri toplama (form builder) modülü
from forms_module import register_form_routes
register_form_routes(api_router, db, current_user, is_admin, security)

# Audit log görüntüleme
register_audit_routes(api_router, db, current_user, is_admin, require_permission=require_permission)

# Ayarlar / Entegrasyonlar modülü (SMS, Email, Planet Labs, AI Servisi)
register_integration_routes(api_router, db, current_user, is_admin, log_audit=log_audit, require_permission=require_permission)

# Veri Giriş modülü (Sprint 4a) — sözleşme, ekim, toprak, sulama, operasyon,
# lojistik, kantar, e-belge, IoT, drone, parsel düzenleme
from data_entry import register_data_entry_routes
register_data_entry_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# ProductionCycle — Üretim Sezonu (IT-05 / Sprint A2) — ikinci omurga:
# Farmer → Parcel → ProductionCycle → Contract/Planting/SoilSample.
from production_cycles import register_production_cycle_routes
register_production_cycle_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Tenant (Kurum) Yönetimi (Sprint 4c) — SADECE platform_admin, BİLEREK raw_db kullanır
from tenants import register_tenant_routes
register_tenant_routes(api_router, raw_db, current_user, hash_password, log_audit)

# Kullanıcı/Personel Yönetimi (Sprint 4d) — rol/izin atama
from users import register_user_routes
register_user_routes(api_router, db, current_user, require_permission, hash_password, log_audit)

# Dinamik Form Yönetimi & Lookup Yönetimi (Sprint A1) — Çiftçi/Parsel/
# Sözleşme/Ekim/Toprak alan metadata'sı (zorunlu/görünür/sıra/lookup vb.).
# NOT: forms_module.py (M18 saha anket formu) ile karıştırılmamalı, ayrı bir modül.
from field_definitions import (register_field_definition_routes, mask_sensitive_fields,
                                mask_sensitive_fields_many, is_masked_value)
register_field_definition_routes(api_router, db, current_user, require_permission, log_audit)

# Universal Query & Filter Engine çekirdeği (IT-08) — liste ekranlarını tek
# bir generic sorgu ucuna (POST /query/{module}) indirger. Filtre paneli
# UI'sı (IT-09) bu ucu kullanacak.
from query_engine import register_query_routes
register_query_routes(api_router, db, current_user, require_permission, log_audit)

# Saved Queries / Portföy (Favorilerim) — IT-08'in filter DSL'ini
# adlandırılmış, favorilenebilir, paylaşılabilir kayıtlar olarak saklar.
from saved_queries import register_saved_query_routes
register_saved_query_routes(api_router, db, current_user, require_permission, log_audit)

# Favoriler (IT-12) — herhangi bir modüldeki tek bir KAYDI favorileme
# (Saved Queries'in sorgu favorilerinden farklı, bkz. favorites.py).
from favorites import register_favorite_routes
register_favorite_routes(api_router, db, current_user, require_permission, log_audit)

# Geo Dosya İçe Aktarma (IT-13.5) — SHP/GeoJSON/KML/DXF ayrıştırma +
# WGS84 koordinat dönüşümü. Sadece AYRIŞTIRIR, kaydetmez (bkz. geo_import.py).
from geo_import import register_geo_import_routes
register_geo_import_routes(api_router, db, current_user, require_permission, log_audit)

# İdari Alanlar + Demografi + Layer v1 (IT-13.6) — il/ilçe/mahalle sınır
# geometrileri, IT-13.5 ile içe aktarılır (sistemde hazır sınır YOK).
from admin_areas import register_admin_area_routes
register_admin_area_routes(api_router, db, current_user, require_permission, log_audit)

# Sezon Parametreleri (B3) — #7 kota→alan kuralı + #2 NDVI eşikleri için parametrik katsayılar
from season_parameters import register_season_parameter_routes
register_season_parameter_routes(api_router, db, current_user, require_permission, log_audit)

# Genel Kişi Grupları (B2) — #5 anomali bildirimi fan-out + #8 form atama
from groups import register_group_routes
register_group_routes(api_router, db, current_user, require_permission, log_audit)

# Dosya Depolama (IT-04) — basit dosya/resim upload + field_definitions
# file/image/multifile alan tiplerinin ve "Belgeler" sekmesinin backend'i.
from storage import register_storage_routes
register_storage_routes(api_router, db, current_user, log_audit)

# Harita Paneli — Kişisel Çalışma Alanı (IT-14) — widget seçimi + harita
# görünümü + aktif filtrenin kullanıcı başına tek kayıt olarak saklanması.
from map_workspace import register_map_workspace_routes
register_map_workspace_routes(api_router, db, current_user, require_permission, log_audit)

# Harita Snapshot (IT-16) — map_workspace'ten AYRI: adlandırılmış, çoklu,
# paylaşılabilir harita görünümü kayıtları (saved_queries ile aynı kalıp).
from map_snapshots import register_map_snapshot_routes
register_map_snapshot_routes(api_router, db, current_user, require_permission, log_audit)

# Financial Ledger + Cari Hesap (IT-19 / FAZ 7 — UFYD devam) — immutable
# ledger_entries (sadece POST + reverse, DELETE/PUT YOK); support.py bunu
# doğrudan import edip "muhasebelesti" geçişinde otomatik kayıt açar —
# bu yüzden support routes'tan ÖNCE tanımlı olmasına gerek yok (import
# zamanında çözülür) ama okunabilirlik için Ledger önce kaydedilir.
from ledger import register_ledger_routes
register_ledger_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Organizasyon Hiyerarşisi (IT-07b / FAZ 3 devam) — OrganizationUnit/Position/
# UserPosition + org-chart + manager-chain resolver. approval.py bunu tüketir.
from organization import register_organization_routes
register_organization_routes(api_router, db, current_user, require_permission, log_audit)

# Onay Zinciri Motoru (IT-07b / FAZ 3 devam) — TEK ortak onay servisi;
# support.py/campaigns.py bunu import edip kullanır, kendi onay mantığını YAZMAZ.
from approval import register_approval_routes
register_approval_routes(api_router, db, current_user, require_permission, log_audit)

# Destek Kataloğu + Destek Talep Süreci (IT-18 / FAZ 7 — UFYD başlangıcı) —
# SupportType katalog CRUD + 9 durumlu SupportRequest akışı + çiftçi
# portalı uçları (current_user role=="ciftci" kontrolü /farmer/* ile aynı desen).
from support import register_support_routes
register_support_routes(api_router, db, current_user, require_permission, log_audit)

# Hakediş Motoru (IT-20 / FAZ 7 — UFYD devam) — Prim/Kesinti katalog CRUD +
# /entitlement/calculate (dry-run) + /entitlement/{id}/finalize (Ledger'a
# yazar, idempotent) + /entitlement/{id} (sonuç sorgulama).
from entitlement import register_entitlement_routes
register_entitlement_routes(api_router, db, current_user, require_permission, log_audit)

# İcmal/Mutabakat Belgesi + Finansal Simülasyon + UFYD Dashboard
# (IT-21 / FAZ 7 — UFYD TAMAMLANIYOR).
from reconciliation import register_reconciliation_routes
register_reconciliation_routes(api_router, db, current_user, require_permission, log_audit)

# Saha Operasyonları: İş Emri / Görev / Ziyaret Üçlü Modeli
# (IT-22 / FAZ 8 — Sprint 8 başlangıcı).
from field_ops import register_field_ops_routes
register_field_ops_routes(api_router, db, current_user, require_permission, log_audit)

# Kural Tabanlı Otomatik Görev Oluşturma (event_bus.py'nin TEMEL kullanımı)
# + Saha Raporları (query_engine.py'ye field_tasks/visits modülleri) +
# Modül Dashboard'u (field_ops.py'deki GET /field-ops/dashboard)
# (IT-24 / FAZ 8 TAMAMLANDI).
from automation import register_automation_routes
register_automation_routes(api_router, db, current_user, require_permission, log_audit)

# Inbound Case Yönetimi (IT-28 / FAZ 9 devam) — genel "Konu/Case" modeli +
# iki yönlü mesajlaşma + field_ops.py'ye (Task) otomatik köprü. communications.py
# kişi kartı timeline'ına bu modülün case kayıtlarını AYRICA okur (tek yönlü).
from case_management import register_case_routes
register_case_routes(api_router, db, current_user, require_permission, log_audit)

# PR-04 (ROADMAP-URUNLESTIRME.md): Migration Runner + Surum Yukseltme/Geri
# Alma. raw_db kullanir (tenant filtresiz) -- migration'lar sema seviyesinde
# calisir. Surum numarasi Health Center'da (platform_core.py) gorunur.
from migrations_engine import register_migration_routes
register_migration_routes(api_router, raw_db, require_permission, log_audit)

# PR-02 (ROADMAP-URUNLESTIRME.md): Web tabanli kurulum sihirbazi -- ince
# katman, gercek is mantigi zaten var olan tenants.py/integrations.py/
# platform_core.py uclarinda (bkz. setup_wizard.py docstring).
from setup_wizard import register_setup_wizard_routes
register_setup_wizard_routes(api_router, raw_db, current_user, log_audit)

# PR-24 (ROADMAP-URUNLESTIRME.md): API Key CRUD (Entegrasyon Merkezi ->
# "API Anahtarlarım"). Dogrulama/rate-limit mantigi current_user icinde
# (yukarida) zaten entegre edildi -- burada sadece yonetim uclari (olustur/
# listele/iptal et) eklenir.
from api_keys import register_api_key_routes
register_api_key_routes(api_router, raw_db, require_permission, log_audit)

# PR-26 (ROADMAP-URUNLESTIRME.md): Gelistirici Portali backend destegi --
# Swagger (/docs) FastAPI varsayilaniyla zaten acik, burada sadece Postman
# collection indirme + changelog uclari eklenir.
from dev_portal import register_dev_portal_routes
register_dev_portal_routes(api_router)

# PR-15 (ROADMAP-URUNLESTIRME.md): KVKK acik riza kayit mekanizmasi
# (genel amacli -- bkz. docs/legal/KVKK-AYDINLATMA-METNI.md Bolum 6).
from consent import register_consent_routes
register_consent_routes(api_router, db, current_user, log_audit)

# Communication Hub: Kanal Provider Pattern + Şablon Yönetimi + Gönderim +
# Kişi Kartı İletişim Timeline'ı (IT-25 / FAZ 9 başlangıç).
from communications import register_communication_routes
register_communication_routes(api_router, db, current_user, require_permission, log_audit)

# Kampanya + Segment (saved_queries üzerinden) + Planlı Gönderim + Onay +
# Retry/Fallback Zinciri (IT-26 / FAZ 9 devam).
from campaigns import register_campaign_routes
register_campaign_routes(api_router, db, current_user, require_permission, log_audit)

# Event Bus'a bağlı Communication Policy + Tercih Merkezi + Kara Liste
# (IT-27 / FAZ 9 TAMAMLANDI).
from communication_policy import register_communication_policy_routes
register_communication_policy_routes(api_router, db, current_user, require_permission, log_audit)

# Farmer LMS — Eğitim Kataloğu + İçerik Yönetimi + Atama + Durum (IT-29 / FAZ 10 başlangıç).
from lms import register_lms_routes
register_lms_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Integration Hub Formalizasyonu + Webhook Engine (IT-32 / FAZ 11).
from integration_hub import register_integration_hub_routes
register_integration_hub_routes(api_router, db, current_user, require_permission, log_audit)

# Platform Core — Feature Flags + Module Manifest + Licensing İskeleti +
# Health Center (IT-33 / FAZ 11 TAMAMLANDI).
from platform_core import register_platform_core_routes
register_platform_core_routes(api_router, db, current_user, require_permission, log_audit)

# Experience Profile Modeli (IT-34 / FAZ 12 — Mobil başlangıç).
from experience_profile import register_experience_profile_routes
register_experience_profile_routes(api_router, db, current_user, require_permission, log_audit)

# FAZ 18 / IT-47..53 — Agricultural Intelligence Engine (AI Vision).
# Knowledge Library + Confidence Engine + Cloud Escalation + Tenant Kota +
# Active Learning + MLOps Model Registry. Async job worker request context
# DIŞINDA çalıştığı için hem `db` (tenant scoped uçlar) hem `raw_db` (worker)
# geçilir (god_mode.py'nin raw_db kullanma gerekçesiyle AYNI).
from ai_engine import register_ai_engine_routes
register_ai_engine_routes(api_router, db, raw_db, current_user, require_permission, log_audit, require_feature)

# FAZ 9.5 / IT-28.1 — Remote Sensing (Uzaktan Algılama, EOSDA entegrasyonu).
# Yeni backend paketi (remote_sensing/) — satellite_provider.py'yi KIRMAZ,
# EOSDA onun yeni bir alt sınıfı gibi eklenir (REMOTE-SENSING-EOSDA-PROMPT.md
# Karar 1). Tarama Politikası (Karar 2) + Integration Center EOSDA tipi
# (Karar 3) + Monitoring + Task yönetimi + Communication Policy köprüsü.
from remote_sensing import register_remote_sensing_routes
register_remote_sensing_routes(api_router, db, current_user, require_permission, log_audit)

# Duyurular — açılışta popup + Bildirimler çekmecesinde okundu-takipli yayın.
from announcements import register_announcement_routes
register_announcement_routes(api_router, db, current_user, require_permission, log_audit)

# God Mode (Faz 1 + Faz 2) — tenant olarak gir/sil/sağlık/modül/lisans +
# platform geneli istatistik + sistem sağlığı + API çağrı istatistikleri.
# BİLİNÇLİ OLARAK raw_db (tenant_context.py'nin GLOBAL_COLLECTIONS
# felsefesiyle AYNI) — platform_admin'in kendi context'inde tenant_id
# olmadığından TenantScopedDB'nin otomatik filtresine güvenilemez.
from god_mode import register_god_mode_routes
register_god_mode_routes(api_router, raw_db, current_user, log_audit)

app.include_router(api_router)

# PR-22 (ROADMAP-URUNLESTIRME.md): /api/v1 -- versiyonlu, standart zarfli
# yuzey. Mevcut /api/* uclarina DOKUNMAZ (bkz. api_envelope.py docstring),
# sadece harici entegratorler/Postman/API Key kullanicilari icin ek bir
# katmandir.
from api_envelope import register_api_v1_proxy
register_api_v1_proxy(app)

# CORS — sadece config_service.py'de tanımlı (env değişkeninden okunan) domain'lere izin ver.
# allow_credentials=True + allow_origins=["*"] KOMBİNASYONU KULLANILMAZ:
# tarayıcılar bunu reddeder ve ayrıca bir güvenlik açığıdır.
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging — secret maskeleme filtresi (IT-01) root logger'a eklenir; JWT_SECRET/
# PLATFORM_ADMIN_PASSWORD/Mongo şifresi yanlışlıkla loglara karışırsa maskelenir.
logging.basicConfig(level=logging.INFO)
install_secret_masking()
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    logger.info(f"🌱 {APP_NAME} başlatıldı — CORS origins: {CORS_ORIGINS}")

    # ============ TEMEL İNDEXLER ============
    # En sık sorgulanan alanlara index eklenmezse, veri büyüdükçe
    # her .find() koleksiyonun tamamını tarar (collection scan).
    # Burada eklenenler en kritik/sık kullanılanlar; yeni endpoint'ler
    # eklendikçe bu liste genişletilmeli.
    try:
        # P1 düzeltmesi: email GLOBAL değil TENANT BAZLI benzersiz olmalı —
        # iki farklı kurum aynı e-postayla ayrı hesap açabilmeli. Eski
        # tek-alanlı unique index (varsa) önce düşürülür, yoksa compound
        # index'i eklemek eski kısıtlamayı KALDIRMAZ (Mongo ikisini de
        # ayrı ayrı uygular). drop_index index yoksa hata fırlatır, o
        # yüzden idempotent olması için sessizce yutulur.
        try:
            await raw_db.users.drop_index("email_1")
        except Exception:
            pass
        await db.users.create_index([("tenant_id", 1), ("email", 1)], unique=True)
        await db.users.create_index("id", unique=True)
        await db.farmers.create_index("id", unique=True)
        await db.farmers.create_index("member_no")
        await db.parcels.create_index("id", unique=True)
        await db.parcels.create_index("farmer_id")
        await db.yields.create_index("farmer_id")
        await db.yields.create_index("parcel_id")
        await db.contracts.create_index("farmer_id")
        await db.audit_logs.create_index("created_at")
        await db.audit_logs.create_index("entity")
        await db.forms.create_index("id", unique=True)
        # P1 düzeltmesi: aynı gerekçeyle entegrasyon tipi de tenant bazlı
        # benzersiz olmalı — iki kurum kendi SMS/Email/AI entegrasyonunu
        # ayrı ayrı tanımlayabilmeli.
        try:
            await raw_db.integrations.drop_index("type_1")
        except Exception:
            pass
        await db.integrations.create_index([("tenant_id", 1), ("type", 1)], unique=True)
        await db.iot_sensors.create_index("parcel_id")
        await db.iot_sensors.create_index("status")
        await db.drone_missions.create_index("parcel_id")
        await db.parcels.create_index("risk_level")
        await db.field_visits.create_index("client_id")
        await db.uploads.create_index("id", unique=True)
        await db.uploads.create_index([("module", 1), ("entity_id", 1)])
        await db.production_cycles.create_index("id", unique=True)
        await db.production_cycles.create_index([("parcel_id", 1), ("year", 1)])
        await db.production_cycles.create_index("farmer_id")
        await db.contracts.create_index("production_cycle_id")
        await db.plantings.create_index("production_cycle_id")
        await db.soil_samples.create_index("production_cycle_id")

        # İdari Alanlar (IT-13.6) — $geoIntersects için 2dsphere index gerekli.
        # parcels.geometry'de daha önce hiç index yoktu (sadece Leaflet
        # görselleştirmesi için okunuyordu) — admin_areas özet endpoint'i
        # (o alandaki çiftçi/parsel kesişimi) bunu gerektiriyor.
        await db.admin_areas.create_index("id", unique=True)
        await db.admin_areas.create_index("parent_id")
        await db.admin_areas.create_index([("geometry", "2dsphere")])
        await db.parcels.create_index([("geometry", "2dsphere")])

        # Tenant izolasyonu artık her sorguda tenant_id filtresi kullanıyor —
        # bu alan üzerinde index olmadan koleksiyon taraması yapılır.
        for coll in ["users", "farmers", "parcels", "contracts", "plantings",
                     "soil_samples", "irrigation_events", "machines", "workers",
                     "tasks", "appointments", "kantar_records", "einvoices",
                     "irsaliyeler", "iot_sensors", "drone_missions", "notifications",
                     "audit_logs", "integrations", "regions", "disease_detections",
                     "field_visits", "forms", "yields", "uploads", "production_cycles", "admin_areas"]:
            await raw_db[coll].create_index("tenant_id")
        await raw_db.tenants.create_index("slug", unique=True)
        await raw_db.tenants.create_index("id", unique=True)

        # ============ PLATFORM ADMIN BOOTSTRAP ============
        # platform_admin, tenant'lar oluşturup yönetir (bkz. tenants.py).
        # Hiç yoksa .env'deki (veya varsayılan) kimlik bilgileriyle ilk kez
        # oluşturulur. ÜRETİMDE PLATFORM_ADMIN_PASSWORD MUTLAKA DEĞİŞTİRİLMELİ.
        existing_platform_admin = await raw_db.users.find_one({"role": "platform_admin"})
        if not existing_platform_admin:
            pf_email = PLATFORM_ADMIN_EMAIL
            pf_password = PLATFORM_ADMIN_PASSWORD
            await raw_db.users.insert_one({
                "id": str(uuid.uuid4()),
                "email": pf_email.lower(),
                "password": hash_password(pf_password),
                "full_name": "Platform Yöneticisi",
                "role": "platform_admin",
                "tenant_id": None,          # tenant'lara ait DEĞİL — tenant'ları yönetir
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.warning(
                f"🔑 Platform admin oluşturuldu: {pf_email} — "
                f"ÜRETİMDE .env'de PLATFORM_ADMIN_EMAIL/PASSWORD tanımlayıp bu varsayılanı değiştirin!"
            )
        logger.info("📊 MongoDB indexleri oluşturuldu/doğrulandı")
    except Exception as e:
        logger.warning(f"⚠️  Index oluşturma sırasında sorun: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    """Uygulama kapanırken DB bağlantısını düzgün kapat"""
    client.close()
