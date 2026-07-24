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
from geo_validation import validate_geometry
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
        # Denetim düzeltmesi (2026-07-24): middleware API key'lerde JWT
        # çözemediği için tenant bağlamı BOŞ kalıyordu — endpoint kodu
        # `db` üzerinden TÜM tenant'ları okuyabiliyordu (fail-closed
        # sonrası ise hiçbir şey okuyamazdı). Bağlam burada, anahtarın
        # ait olduğu tenant'la kurulur (middleware finally bloğu isteğin
        # sonunda kendi reset'ini yapar, ek sızıntı olmaz).
        if api_user.get("tenant_id"):
            current_tenant_id.set(api_user["tenant_id"])
        return api_user

    try:
        # Token'ı çöz (imza doğrulaması + süre kontrolü otomatik)
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])

        # Refresh token'lar API çağrılarında kullanılamaz — sadece /auth/refresh'te.
        if payload.get("type") == "refresh":
            raise HTTPException(401, "Refresh token API çağrılarında kullanılamaz")

        # DB'den kullanıcıyı çek (şifre hash'ini geri dönmüyoruz).
        # raw_db (2026-07-24 A3 düzeltmesi): kimlik JWT ile doğrulanmış
        # user_id'den çekilir — bu, tenant bağlamı HENÜZ kurulmadan çalışır
        # ve platform_admin gibi tenant_id=None taşıyan hesaplar fail-closed
        # `db` ile HİÇ bulunamaz, her istek 401'e düşerdi. user_id kriptografik
        # olarak imzalı olduğundan çapraz-tenant sızıntı yoktur (yalnızca
        # kendi kaydınızı getirir); asıl veri sorguları hâlâ scoped `db`'den
        # geçer. Bağlam AŞAĞIDA token'ın tenant_id'siyle kurulur.
        user = await raw_db.users.find_one(
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

# ==== Denetim A6: bu blok auth_routes.py'ye taşındı (route sırası korunur) ====
from auth_routes import register_auth_routes
register_auth_routes(api_router, db, raw_db, current_user, require_permission, log_audit)
# ==== Denetim A6: bu blok dashboard_routes.py'ye taşındı (route sırası korunur) ====
from dashboard_routes import register_dashboard_routes
register_dashboard_routes(api_router, db, current_user, require_feature)
# ==== Denetim A6: bu blok farmer_routes.py'ye taşındı (route sırası korunur) ====
from farmer_routes import register_farmer_routes
register_farmer_routes(api_router, db, current_user, require_permission, require_feature, is_admin, log_audit)
# ==== Denetim A6: bu blok parcel_routes.py'ye taşındı (route sırası korunur) ====
from parcel_routes import register_parcel_routes
register_parcel_routes(api_router, db, current_user, require_permission, require_feature, require_min_role, is_admin, log_audit)
# ==== Denetim A6: bu blok listing_routes.py'ye taşındı (route sırası korunur) ====
from listing_routes import register_listing_routes
register_listing_routes(api_router, db, current_user, require_feature)
# ==== Denetim A6: bu blok seed_routes.py'ye taşındı (route sırası korunur) ====
from seed_routes import register_seed_routes
register_seed_routes(api_router, db, raw_db, current_user, hash_pw)

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
register_satellite_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Saha veri toplama (form builder) modülü
from forms_module import register_form_routes
register_form_routes(api_router, db, current_user, is_admin, security, require_feature)

# Audit log görüntüleme
register_audit_routes(api_router, db, current_user, is_admin, require_permission=require_permission, require_feature=require_feature)

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
register_geo_import_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# İdari Alanlar + Demografi + Layer v1 (IT-13.6) — il/ilçe/mahalle sınır
# geometrileri, IT-13.5 ile içe aktarılır (sistemde hazır sınır YOK).
from admin_areas import register_admin_area_routes
register_admin_area_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Sezon Parametreleri (B3) — #7 kota→alan kuralı + #2 NDVI eşikleri için parametrik katsayılar
from season_parameters import register_season_parameter_routes
register_season_parameter_routes(api_router, db, current_user, require_permission, log_audit)

# Genel Kişi Grupları (B2) — #5 anomali bildirimi fan-out + #8 form atama
from groups import register_group_routes
register_group_routes(api_router, db, current_user, require_permission, log_audit)

# Ekim Planlama Karar Motoru (#10) — parsel arama + çeşit lookup'ı +
# düzenlenebilir agronomik bilgi/prompt kütüphanesi + polar odaklı analiz.
from agronomy import register_agronomy_routes
register_agronomy_routes(api_router, db, current_user, require_permission, log_audit)

# Karne Puanlama Motoru (SON HAL) — rastgele seed skorların yerine gerçek
# verilerden parametrik ağırlıklı hesap + "neden bu skor?" breakdown'u.
from karne_engine import register_karne_engine_routes
register_karne_engine_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Dosya Depolama (IT-04) — basit dosya/resim upload + field_definitions
# file/image/multifile alan tiplerinin ve "Belgeler" sekmesinin backend'i.
from storage import register_storage_routes
register_storage_routes(api_router, db, current_user, log_audit, raw_db=raw_db)

# Harita Paneli — Kişisel Çalışma Alanı (IT-14) — widget seçimi + harita
# görünümü + aktif filtrenin kullanıcı başına tek kayıt olarak saklanması.
from map_workspace import register_map_workspace_routes
register_map_workspace_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Harita Snapshot (IT-16) — map_workspace'ten AYRI: adlandırılmış, çoklu,
# paylaşılabilir harita görünümü kayıtları (saved_queries ile aynı kalıp).
from map_snapshots import register_map_snapshot_routes
register_map_snapshot_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

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
register_organization_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Onay Zinciri Motoru (IT-07b / FAZ 3 devam) — TEK ortak onay servisi;
# support.py/campaigns.py bunu import edip kullanır, kendi onay mantığını YAZMAZ.
from approval import register_approval_routes
register_approval_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Destek Kataloğu + Destek Talep Süreci (IT-18 / FAZ 7 — UFYD başlangıcı) —
# SupportType katalog CRUD + 9 durumlu SupportRequest akışı + çiftçi
# portalı uçları (current_user role=="ciftci" kontrolü /farmer/* ile aynı desen).
from support import register_support_routes
register_support_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Hakediş Motoru (IT-20 / FAZ 7 — UFYD devam) — Prim/Kesinti katalog CRUD +
# /entitlement/calculate (dry-run) + /entitlement/{id}/finalize (Ledger'a
# yazar, idempotent) + /entitlement/{id} (sonuç sorgulama).
from entitlement import register_entitlement_routes
register_entitlement_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# İcmal/Mutabakat Belgesi + Finansal Simülasyon + UFYD Dashboard
# (IT-21 / FAZ 7 — UFYD TAMAMLANIYOR).
from reconciliation import register_reconciliation_routes
register_reconciliation_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Saha Operasyonları: İş Emri / Görev / Ziyaret Üçlü Modeli
# (IT-22 / FAZ 8 — Sprint 8 başlangıcı).
from field_ops import register_field_ops_routes
register_field_ops_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Kural Tabanlı Otomatik Görev Oluşturma (event_bus.py'nin TEMEL kullanımı)
# + Saha Raporları (query_engine.py'ye field_tasks/visits modülleri) +
# Modül Dashboard'u (field_ops.py'deki GET /field-ops/dashboard)
# (IT-24 / FAZ 8 TAMAMLANDI).
from automation import register_automation_routes
register_automation_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Inbound Case Yönetimi (IT-28 / FAZ 9 devam) — genel "Konu/Case" modeli +
# iki yönlü mesajlaşma + field_ops.py'ye (Task) otomatik köprü. communications.py
# kişi kartı timeline'ına bu modülün case kayıtlarını AYRICA okur (tek yönlü).
from case_management import register_case_routes
register_case_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

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
register_api_key_routes(api_router, raw_db, require_permission, log_audit, require_feature)

# PR-26 (ROADMAP-URUNLESTIRME.md): Gelistirici Portali backend destegi --
# Swagger (/docs) FastAPI varsayilaniyla zaten acik, burada sadece Postman
# collection indirme + changelog uclari eklenir.
from dev_portal import register_dev_portal_routes
register_dev_portal_routes(api_router, require_feature)

# PR-15 (ROADMAP-URUNLESTIRME.md): KVKK acik riza kayit mekanizmasi
# (genel amacli -- bkz. docs/legal/KVKK-AYDINLATMA-METNI.md Bolum 6).
from consent import register_consent_routes
register_consent_routes(api_router, db, current_user, log_audit)

# Communication Hub: Kanal Provider Pattern + Şablon Yönetimi + Gönderim +
# Kişi Kartı İletişim Timeline'ı (IT-25 / FAZ 9 başlangıç).
from communications import register_communication_routes
register_communication_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Kampanya + Segment (saved_queries üzerinden) + Planlı Gönderim + Onay +
# Retry/Fallback Zinciri (IT-26 / FAZ 9 devam).
from campaigns import register_campaign_routes
register_campaign_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Event Bus'a bağlı Communication Policy + Tercih Merkezi + Kara Liste
# (IT-27 / FAZ 9 TAMAMLANDI).
from communication_policy import register_communication_policy_routes
register_communication_policy_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Farmer LMS — Eğitim Kataloğu + İçerik Yönetimi + Atama + Durum (IT-29 / FAZ 10 başlangıç).
from lms import register_lms_routes
register_lms_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Integration Hub Formalizasyonu + Webhook Engine (IT-32 / FAZ 11).
from integration_hub import register_integration_hub_routes
register_integration_hub_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

# Platform Core — Feature Flags + Module Manifest + Licensing İskeleti +
# Health Center (IT-33 / FAZ 11 TAMAMLANDI).
from platform_core import register_platform_core_routes
register_platform_core_routes(api_router, db, current_user, require_permission, log_audit)

# Experience Profile Modeli (IT-34 / FAZ 12 — Mobil başlangıç).
from experience_profile import register_experience_profile_routes
register_experience_profile_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

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
register_remote_sensing_routes(api_router, db, current_user, require_permission, log_audit, require_feature)

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
        # SON HAL — yeni sorgu kalıpları: sözleşme detayı + parsel popup'ı
        # (parcel_id→sözleşme), Ekim Kaydı ?parcel= filtresi, karne motoru
        # (parsel bazlı sulama/toprak taramaları) ve karne trend geçmişi.
        await db.contracts.create_index([("parcel_id", 1), ("season", -1)])
        await db.plantings.create_index([("parcel_id", 1), ("season", -1)])
        await db.irrigation_events.create_index("parcel_id")
        await db.soil_samples.create_index("parcel_id")
        await db.kantar_records.create_index("production_cycle_id")
        await db.karne_history.create_index([("farmer_id", 1), ("computed_at", 1)])

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

        # ============ BİLEŞİK İNDEKSLER (denetim A4, 2026-07-24) ============
        # Query Engine + liste ekranları ağırlıklı olarak tenant_id +
        # created_at/status/farmer_id kombinasyonlarıyla sorgular — tek
        # alanlı tenant_id index'i yüksek veri hacminde yetersiz kalır.
        # İsimli (name=) tanımlandılar: create_index idempotenttir, her
        # startup'ta güvenle tekrar çalışır.
        _TS = [("tenant_id", 1), ("created_at", -1)]
        for coll in ["farmers", "parcels", "contracts", "plantings", "soil_samples",
                     "field_tasks", "visits", "support_requests", "ledger_entries",
                     "communications", "kantar_records", "production_cycles",
                     "notifications", "irrigation_events"]:
            await raw_db[coll].create_index(_TS, name="tenant_created_idx")
        # Durum makineli koleksiyonlar — kanban/dashboard "duruma göre say/filtrele"
        for coll in ["field_tasks", "support_requests", "production_cycles",
                     "campaigns", "cases", "work_orders"]:
            await raw_db[coll].create_index([("tenant_id", 1), ("status", 1)],
                                            name="tenant_status_idx")
        # Çiftçi-çocuk koleksiyonlar — 360 görünümü/detay sayfaları farmer_id ile çeker
        for coll in ["parcels", "contracts", "support_requests", "ledger_entries",
                     "visits", "kantar_records", "entitlements"]:
            await raw_db[coll].create_index([("tenant_id", 1), ("farmer_id", 1)],
                                            name="tenant_farmer_idx")

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
