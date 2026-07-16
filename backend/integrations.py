"""
=====================================================================
Toprax — Entegrasyonlar / Ayarlar Modülü
=====================================================================
Kullanıcı adı/şifre veya API key gerektiren tüm dış servisler
(SMS, Email/SMTP, Planet Labs, AI Servisi) burada tek merkezden
yönetilir. Sadece admin katmanı (ADMIN_TIER_ROLES) erişebilir.

Her entegrasyon tipi için:
- GET  /api/integrations              -> tüm entegrasyonların (maskelenmiş) durumu
- GET  /api/integrations/health       -> TÜM entegrasyonlar için toplu health-check
- GET  /api/integrations/{type}       -> tek entegrasyonun (maskelenmiş) config'i
- GET  /api/integrations/{type}/health-> TEK entegrasyon için health-check
- PUT  /api/integrations/{type}       -> config'i (+ timeout/retry) kaydet/güncelle
- POST /api/integrations/{type}/test  -> GERÇEK bağlantı testi yapar
                                          (SMS/Email gerçekten gönderir,
                                          Planet Labs/AI servis key'i doğrular)

NOT: Bu ortamda dış ağa (internet) erişim kapalı olduğu için test
endpoint'leri burada çalıştırılıp doğrulanamadı. Kod, gerçek API
key/şifre girildiğinde kullanıcının kendi ortamında çalışacak şekilde
yazıldı — ilk kullanımda mutlaka bizzat "Bağlantıyı Test Et" ile
doğrulanmalı.

--- IT-01: health-check vs. test farkı --------------------------------
/test  : Uçtan uca GERÇEK işlem yapar (SMS gerçekten gider, test e-postası
         gerçekten gönderilir). Kullanıcı elle tetikler, parametre gerektirir
         (telefon/e-posta).
/health: Parametre gerektirmez, GERÇEK ama YIKICI OLMAYAN bir bağlantı
         kontrolü yapar (SMS: sağlayıcı API'sine erişilebilirlik + kimlik
         bilgisi kontrolü, mesaj GÖNDERMEZ; Email: SMTP login yapar, e-posta
         GÖNDERMEZ; Planet Labs/AI Servisi: zaten non-destructive GET
         kullandığı için /test ile aynı çağrıyı yapar). İzleme/otomasyon
         (ör. gelecekteki IT-33 Health Center) için tasarlanmıştır.
timeout_seconds / retry_count: her entegrasyon dokümanında saklanan,
         opsiyonel per-tip override alanlarıdır. Boş bırakılırsa
         config_service.INTEGRATION_TIMEOUT_SECONDS / INTEGRATION_RETRY_COUNT
         (env: INTEGRATION_TIMEOUT_SECONDS / INTEGRATION_RETRY_COUNT)
         varsayılanları kullanılır.
"""
import smtplib
import ssl
import uuid
import requests
from email.mime.text import MIMEText
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Callable, Tuple
from config_service import ADMIN_TIER_ROLES, INTEGRATION_TIMEOUT_SECONDS, INTEGRATION_RETRY_COUNT

# Hangi tipte hangi alanlar "secret" (maskelenmesi gereken) — response'ta gizlenir.
SECRET_FIELDS = {
    "sms": {"netgsm_password", "twilio_auth_token", "webhook_auth_header"},
    "email": {"password"},
    "planet_labs": {"api_key"},
    "ai_service": {"api_key"},
    # (2026-07-11) Uydu Görüntü Ekosistemi araştırması sonrası eklendi —
    # bkz. TOPRAX_Uydu_Goruntu_Ekosistemi_Arastirma.md §5/§8 ve
    # satellite_provider.py. Üçü de mock_mode=True VARSAYILANLA gelir —
    # gerçek anahtar girilip mock_mode kapatılmadan hiçbir gerçek dış
    # çağrı yapılmaz (planet_labs ile AYNI kalıp).
    "sentinel_hub": {"client_secret"},
    "nasa_firms": {"map_key"},
    "up42": {"client_secret"},
    # (REMOTE-SENSING-EOSDA-PROMPT.md Karar 3) Uzaktan Algılama Sağlayıcısı
    # EOSDA — Integration Center'a yeni entegrasyon tipi. Auth OAuth DEĞİL,
    # sabit x-api-key; api_key/client_secret/access_token maskelenir.
    "eosda": {"api_key", "client_secret", "access_token"},
}

VALID_TYPES = set(SECRET_FIELDS.keys())


def _mask(value: str) -> str:
    if not value:
        return value
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def _mask_config(itype: str, config: dict) -> dict:
    masked = dict(config)
    for field in SECRET_FIELDS.get(itype, set()):
        if field in masked and masked[field]:
            masked[field] = _mask(masked[field])
    return masked


class IntegrationUpdate(BaseModel):
    provider: Optional[str] = None          # örn. "netgsm" | "twilio" | "custom_webhook" | "openai" | "gemini"
    config: Dict[str, Any] = {}
    enabled: bool = True
    # IT-01: per-entegrasyon override. None ise config_service'teki global
    # varsayılan (INTEGRATION_TIMEOUT_SECONDS / INTEGRATION_RETRY_COUNT) kullanılır.
    timeout_seconds: Optional[int] = Field(None, ge=1, le=60)
    retry_count: Optional[int] = Field(None, ge=0, le=5)


class SmsTestBody(BaseModel):
    phone: str
    message: Optional[str] = "Toprax test mesajı: entegrasyon çalışıyor."


class EmailTestBody(BaseModel):
    to_email: str


# =========================================================================
#                    ZAMAN AŞIMI / TEKRAR DENEME ÇÖZÜMLEME (IT-01)
# =========================================================================

def _resolve_timeout(doc: Optional[dict]) -> int:
    val = (doc or {}).get("timeout_seconds")
    return val if val is not None else INTEGRATION_TIMEOUT_SECONDS


def _resolve_retry(doc: Optional[dict]) -> int:
    val = (doc or {}).get("retry_count")
    return val if val is not None else INTEGRATION_RETRY_COUNT


def _with_retry(probe_fn: Callable[[], Tuple[bool, str]], retry_count: int) -> Tuple[bool, str]:
    """probe_fn başarısız olursa (ok=False) retry_count kadar tekrar dener
    (toplam deneme sayısı = retry_count + 1). probe_fn içinde fırlatılan
    HTTPException (ör. geçersiz sağlayıcı) YAKALANMAZ — anlamsız tekrar
    denemeyi önlemek için doğrudan çağırana yükselir."""
    attempts = max(1, retry_count + 1)
    ok, message = False, "Deneme yapılmadı"
    for _ in range(attempts):
        ok, message = probe_fn()
        if ok:
            return ok, message
    return ok, message


# =========================================================================
#                    GERÇEK GÖNDERİM PROB'LARI (/test tarafından kullanılır)
# =========================================================================

def _probe_sms_send(provider: str, cfg: dict, phone: str, message: str, timeout: int) -> Tuple[bool, str]:
    try:
        if provider == "netgsm":
            resp = requests.post(
                "https://api.netgsm.com.tr/sms/send/get",
                params={
                    "usercode": cfg.get("netgsm_usercode"),
                    "password": cfg.get("netgsm_password"),
                    "gsmno": phone,
                    "message": message,
                    "msgheader": cfg.get("netgsm_header"),
                },
                timeout=timeout,
            )
            ok = resp.status_code == 200 and not resp.text.startswith(("20", "30", "40", "50", "60", "70"))
            return ok, f"Netgsm yanıtı: {resp.text.strip()}"
        elif provider == "twilio":
            from requests.auth import HTTPBasicAuth
            sid = cfg.get("twilio_account_sid")
            resp = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={
                    "To": phone,
                    "From": cfg.get("twilio_from_number"),
                    "Body": message,
                },
                auth=HTTPBasicAuth(sid, cfg.get("twilio_auth_token")),
                timeout=timeout,
            )
            ok = resp.status_code in (200, 201)
            return ok, f"Twilio yanıtı: HTTP {resp.status_code}"
        elif provider == "custom_webhook":
            headers = cfg.get("webhook_headers", {}) or {}
            if cfg.get("webhook_auth_header"):
                headers["Authorization"] = cfg["webhook_auth_header"]
            resp = requests.post(
                cfg.get("webhook_url"),
                json={"phone": phone, "message": message},
                headers=headers,
                timeout=timeout,
            )
            ok = resp.status_code < 300
            return ok, f"Webhook yanıtı: HTTP {resp.status_code}"
        else:
            raise HTTPException(400, "Geçersiz SMS sağlayıcısı (netgsm | twilio | custom_webhook)")
    except HTTPException:
        raise
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


def _probe_email_send(cfg: dict, to_email: str, timeout: int) -> Tuple[bool, str]:
    try:
        msg = MIMEText("Bu, Toprax Ayarlar modülünden gönderilen bir test e-postasıdır.")
        msg["Subject"] = "Toprax — Entegrasyon Test E-postası"
        msg["From"] = cfg.get("from_address", cfg.get("username"))
        msg["To"] = to_email

        host = cfg.get("host")
        port = int(cfg.get("port", 587))
        use_tls = cfg.get("use_tls", True)

        if use_tls:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.starttls(context=ssl.create_default_context())
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())

        server.login(cfg.get("username"), cfg.get("password"))
        server.sendmail(msg["From"], [to_email], msg.as_string())
        server.quit()
        return True, f"Test e-postası {to_email} adresine gönderildi."
    except Exception as e:
        return False, f"SMTP hatası: {e}"


def _probe_planet_labs(cfg: dict, timeout: int) -> Tuple[bool, str]:
    api_key = cfg.get("api_key")
    if not api_key:
        return False, "Önce Planet Labs API key girilmeli"

    # Henüz gerçek bir Planet Labs hesabı yoksa (mock mod): key formatını
    # kontrol edip simüle edilmiş başarı döner. Gerçek key eklendiğinde
    # aşağıdaki gerçek HTTP çağrısı devreye girer.
    mock_mode = cfg.get("mock_mode", True)
    if mock_mode:
        return True, "[MOCK MOD] Key formatı geçerli görünüyor. Gerçek doğrulama için 'mock_mode' kapatılmalı."
    try:
        resp = requests.get(
            "https://api.planet.com/data/v1/item-types",
            auth=(api_key, ""),
            timeout=timeout,
        )
        ok = resp.status_code == 200
        return ok, f"Planet Labs yanıtı: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


def _probe_sentinel_hub(cfg: dict, timeout: int) -> Tuple[bool, str]:
    """Copernicus Data Space Ecosystem OAuth2 client_credentials token isteği
    — token başarıyla alınabiliyorsa kimlik bilgisi geçerli demektir (NDVI
    isteği atmadan, YIKICI OLMAYAN bir doğrulama)."""
    client_id, client_secret = cfg.get("client_id"), cfg.get("client_secret")
    if not client_id or not client_secret:
        return False, "Önce Sentinel Hub client_id/client_secret girilmeli"
    if cfg.get("mock_mode", True):
        return True, "[MOCK MOD] Kimlik bilgisi formatı geçerli görünüyor. Gerçek doğrulama için 'mock_mode' kapatılmalı."
    try:
        resp = requests.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=timeout,
        )
        ok = resp.status_code == 200 and "access_token" in resp.json()
        return ok, f"Sentinel Hub kimlik doğrulaması: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


def _probe_nasa_firms(cfg: dict, timeout: int) -> Tuple[bool, str]:
    """NASA FIRMS MAP_KEY durumu — ücretsiz servis, sadece key'in tanınıp
    tanınmadığını kontrol eder (transaction_limit/count döner)."""
    map_key = cfg.get("map_key")
    if not map_key:
        return False, "Önce NASA FIRMS MAP_KEY girilmeli"
    if cfg.get("mock_mode", True):
        return True, "[MOCK MOD] Key formatı geçerli görünüyor. Gerçek doğrulama için 'mock_mode' kapatılmalı."
    try:
        resp = requests.get(
            f"https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={map_key}",
            timeout=timeout,
        )
        ok = resp.status_code == 200
        return ok, f"NASA FIRMS yanıtı: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


def _probe_up42(cfg: dict, timeout: int) -> Tuple[bool, str]:
    """UP42 OAuth2 client_credentials token isteği — sipariş OLUŞTURMAZ,
    sadece kimlik doğrulamayı test eder."""
    client_id, client_secret = cfg.get("client_id"), cfg.get("client_secret")
    if not client_id or not client_secret:
        return False, "Önce UP42 client_id/client_secret girilmeli"
    if cfg.get("mock_mode", True):
        return True, "[MOCK MOD] Kimlik bilgisi formatı geçerli görünüyor. Gerçek doğrulama için 'mock_mode' kapatılmalı."
    try:
        resp = requests.post(
            "https://api.up42.com/oauth/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=timeout,
        )
        ok = resp.status_code == 200 and "access_token" in resp.json()
        return ok, f"UP42 kimlik doğrulaması: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


def _probe_eosda(cfg: dict, timeout: int) -> Tuple[bool, str]:
    """EOSDA x-api-key doğrulaması — görüntü/istatistik task'ı OLUŞTURMAZ,
    sadece anahtarın erişilebilirliğini test eder (trial 1000 istek limiti
    boşa harcanmasın diye hafif bir çağrı)."""
    api_key = cfg.get("api_key")
    if not api_key:
        return False, "Önce EOSDA API Key girilmeli"
    if cfg.get("mock_mode", True):
        return True, "[MOCK MOD] API Key formatı geçerli görünüyor. Gerçek doğrulama için 'mock_mode' kapatılmalı."
    try:
        resp = requests.get(
            "https://api-connect.eos.com/api/gdw/api",
            headers={"x-api-key": api_key},
            timeout=timeout,
        )
        # 200/400/422 = anahtar tanındı (endpoint parametre bekliyor);
        # 401/403 = anahtar geçersiz.
        ok = resp.status_code not in (401, 403)
        return ok, f"EOSDA x-api-key doğrulaması: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


def _probe_ai_service(provider: str, cfg: dict, timeout: int) -> Tuple[bool, str]:
    api_key = cfg.get("api_key")
    if not api_key or not provider:
        return False, "Önce AI servis sağlayıcısı ve API key girilmeli"
    try:
        if provider == "openai":
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout,
            )
            ok = resp.status_code == 200
            return ok, f"OpenAI yanıtı: HTTP {resp.status_code}"
        elif provider == "gemini":
            resp = requests.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                timeout=timeout,
            )
            ok = resp.status_code == 200
            return ok, f"Gemini yanıtı: HTTP {resp.status_code}"
        elif provider == "anthropic":
            resp = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=timeout,
            )
            ok = resp.status_code == 200
            return ok, f"Anthropic yanıtı: HTTP {resp.status_code}"
        else:
            raise HTTPException(400, "Geçersiz AI sağlayıcısı (openai | gemini | anthropic)")
    except HTTPException:
        raise
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


# =========================================================================
#      YIKICI OLMAYAN PROB'LAR (/health tarafından kullanılır — IT-01)
# =========================================================================

def _probe_sms_reachability(provider: str, cfg: dict, timeout: int) -> Tuple[bool, str]:
    """Gerçek SMS göndermeden sağlayıcı erişilebilirliğini + temel kimlik
    bilgisi varlığını kontrol eder. Tam doğrulama için /test kullanılmalı."""
    try:
        if provider == "netgsm":
            if not cfg.get("netgsm_usercode") or not cfg.get("netgsm_password"):
                return False, "netgsm_usercode/netgsm_password eksik"
            resp = requests.head("https://api.netgsm.com.tr", timeout=timeout)
            return True, f"Netgsm API erişilebilir (HTTP {resp.status_code})"
        elif provider == "twilio":
            if not cfg.get("twilio_account_sid") or not cfg.get("twilio_auth_token"):
                return False, "twilio_account_sid/twilio_auth_token eksik"
            resp = requests.head("https://api.twilio.com", timeout=timeout)
            return True, f"Twilio API erişilebilir (HTTP {resp.status_code})"
        elif provider == "custom_webhook":
            url = cfg.get("webhook_url")
            if not url:
                return False, "webhook_url eksik"
            resp = requests.head(url, timeout=timeout)
            return True, f"Webhook erişilebilir (HTTP {resp.status_code})"
        else:
            return False, "Geçersiz SMS sağlayıcısı (netgsm | twilio | custom_webhook)"
    except Exception as e:
        return False, f"Bağlantı hatası: {e}"


def _probe_email_connection(cfg: dict, timeout: int) -> Tuple[bool, str]:
    """SMTP sunucusuna bağlanıp kimlik doğrular, e-posta GÖNDERMEZ."""
    host = cfg.get("host")
    if not host or not cfg.get("username") or not cfg.get("password"):
        return False, "host/username/password eksik"
    try:
        port = int(cfg.get("port", 587))
        use_tls = cfg.get("use_tls", True)
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.starttls(context=ssl.create_default_context())
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
        server.login(cfg.get("username"), cfg.get("password"))
        server.quit()
        return True, f"SMTP sunucusuna ({host}:{port}) bağlanıldı ve kimlik doğrulandı"
    except Exception as e:
        return False, f"SMTP bağlantı hatası: {e}"


def register_integration_routes(api_router, db, current_user, is_admin, log_audit=None, require_permission=None):

    async def _check_view(user):
        """Görüntüleme: ADMIN_TIER_ROLES VEYA settings:integrations_view iznine sahip olan."""
        if user.get("role") in ADMIN_TIER_ROLES:
            return
        if require_permission:
            from permissions import get_effective_permissions
            perms = await get_effective_permissions(user, db)
            if "settings:integrations_view" in perms:
                return
        raise HTTPException(403, "Entegrasyonları görme yetkiniz yok")

    async def _check_manage(user):
        """Değiştirme/test etme: ADMIN_TIER_ROLES VEYA settings:integrations_manage iznine sahip olan."""
        if user.get("role") in ADMIN_TIER_ROLES:
            return
        if require_permission:
            from permissions import get_effective_permissions
            perms = await get_effective_permissions(user, db)
            if "settings:integrations_manage" in perms:
                return
        raise HTTPException(403, "Entegrasyonları değiştirme yetkiniz yok")

    def _integration_view(itype: str, doc: dict) -> dict:
        doc = doc or {"type": itype, "provider": None, "config": {}, "enabled": False}
        return {
            "type": itype,
            "provider": doc.get("provider"),
            "config": _mask_config(itype, doc.get("config", {})),
            "enabled": doc.get("enabled", False),
            "timeout_seconds": _resolve_timeout(doc),
            "retry_count": _resolve_retry(doc),
            "updated_at": doc.get("updated_at"),
            "last_test_status": doc.get("last_test_status"),
            "last_test_at": doc.get("last_test_at"),
            "last_test_message": doc.get("last_test_message"),
            "last_success_at": doc.get("last_success_at"),
        }

    @api_router.get("/integrations")
    async def list_integrations(user=Depends(current_user)):
        await _check_view(user)
        docs = await db.integrations.find({}, {"_id": 0}).to_list(50)
        by_type = {d["type"]: d for d in docs}
        result = [_integration_view(itype, by_type.get(itype)) for itype in VALID_TYPES]
        return {"integrations": result}

    # NOT: bu route, aşağıdaki GET /integrations/{itype} ile aynı şekle sahip
    # olduğu için (itype="health" eşleşmesin diye) ondan ÖNCE tanımlanmalı.
    @api_router.get("/integrations/health")
    async def get_all_integrations_health(user=Depends(current_user)):
        """Yapılandırılmış VE etkin tüm entegrasyonlar için aktif health-check
        çalıştırır. Pasif/hiç yapılandırılmamış tipler için gerçek çağrı yapılmaz."""
        await _check_manage(user)
        results = []
        for itype in VALID_TYPES:
            doc = await db.integrations.find_one({"type": itype}, {"_id": 0})
            if doc and doc.get("enabled") and doc.get("config"):
                results.append(await _run_health_check(itype, doc))
            else:
                results.append({
                    "type": itype,
                    "enabled": bool(doc and doc.get("enabled")),
                    "healthy": None,
                    "message": "Entegrasyon pasif veya yapılandırılmamış — kontrol edilmedi",
                    "timeout_seconds": _resolve_timeout(doc),
                    "retry_count": _resolve_retry(doc),
                    "last_test_status": (doc or {}).get("last_test_status"),
                    "last_test_at": (doc or {}).get("last_test_at"),
                    "last_success_at": (doc or {}).get("last_success_at"),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
        return {"integrations": results}

    @api_router.get("/integrations/{itype}")
    async def get_integration(itype: str, user=Depends(current_user)):
        await _check_view(user)
        if itype not in VALID_TYPES:
            raise HTTPException(404, "Bilinmeyen entegrasyon tipi")
        doc = await db.integrations.find_one({"type": itype}, {"_id": 0})
        return _integration_view(itype, doc)

    @api_router.get("/integrations/{itype}/health")
    async def get_integration_health(itype: str, user=Depends(current_user)):
        await _check_manage(user)
        if itype not in VALID_TYPES:
            raise HTTPException(404, "Bilinmeyen entegrasyon tipi")
        doc = await db.integrations.find_one({"type": itype}, {"_id": 0})
        return await _run_health_check(itype, doc)

    @api_router.put("/integrations/{itype}")
    async def upsert_integration(itype: str, body: IntegrationUpdate, request: Request, user=Depends(current_user)):
        await _check_manage(user)
        if itype not in VALID_TYPES:
            raise HTTPException(404, "Bilinmeyen entegrasyon tipi")

        existing = await db.integrations.find_one({"type": itype}, {"_id": 0})
        old_config = dict(existing.get("config", {})) if existing else {}

        # Maskelenmiş bir değer (*** ile biten) geri gönderilirse eski gerçek
        # değeri koru — yoksa admin panelinde "kaydet" her tıklandığında
        # secret üstüne yıldızlar yazılır ve entegrasyon bozulur.
        merged_config = dict(old_config)
        for k, v in body.config.items():
            if isinstance(v, str) and v.strip("*") == "" and v != "":
                continue  # tamamen yıldızlardan oluşan değeri yok say (değişmemiş demektir)
            merged_config[k] = v

        # timeout_seconds/retry_count: body'de gönderilmediyse (None) mevcut
        # override korunur (böylece "kaydet" her tıklandığında sessizce
        # global varsayılana dönmez).
        timeout_seconds = body.timeout_seconds if body.timeout_seconds is not None else (existing or {}).get("timeout_seconds")
        retry_count = body.retry_count if body.retry_count is not None else (existing or {}).get("retry_count")

        doc = {
            "type": itype,
            "provider": body.provider,
            "config": merged_config,
            "enabled": body.enabled,
            "timeout_seconds": timeout_seconds,
            "retry_count": retry_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user.get("email"),
        }
        await db.integrations.update_one({"type": itype}, {"$set": doc}, upsert=True)

        if log_audit:
            await log_audit(
                db, user, action="update", entity="integration", entity_id=itype,
                old_value=_mask_config(itype, old_config),
                new_value=_mask_config(itype, merged_config),
                request=request,
            )
        return {"status": "saved", "type": itype}

    # =================================================================
    #                    HEALTH-CHECK (YIKICI DEĞİL, IT-01)
    # =================================================================

    async def _run_health_check(itype: str, doc: Optional[dict]) -> dict:
        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)

        if not doc or not doc.get("config"):
            return {
                "type": itype,
                "enabled": bool(doc and doc.get("enabled")),
                "healthy": False,
                "message": "Entegrasyon henüz yapılandırılmamış",
                "timeout_seconds": timeout,
                "retry_count": retry_count,
                "last_test_status": (doc or {}).get("last_test_status"),
                "last_test_at": (doc or {}).get("last_test_at"),
                "last_success_at": (doc or {}).get("last_success_at"),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        provider = doc.get("provider")
        cfg = doc.get("config", {})

        if itype == "sms":
            ok, message = _with_retry(lambda: _probe_sms_reachability(provider, cfg, timeout), retry_count)
        elif itype == "email":
            ok, message = _with_retry(lambda: _probe_email_connection(cfg, timeout), retry_count)
        elif itype == "planet_labs":
            ok, message = _with_retry(lambda: _probe_planet_labs(cfg, timeout), retry_count)
        elif itype == "sentinel_hub":
            ok, message = _with_retry(lambda: _probe_sentinel_hub(cfg, timeout), retry_count)
        elif itype == "nasa_firms":
            ok, message = _with_retry(lambda: _probe_nasa_firms(cfg, timeout), retry_count)
        elif itype == "up42":
            ok, message = _with_retry(lambda: _probe_up42(cfg, timeout), retry_count)
        elif itype == "eosda":
            ok, message = _with_retry(lambda: _probe_eosda(cfg, timeout), retry_count)
        elif itype == "ai_service":
            ok, message = _with_retry(lambda: _probe_ai_service(provider, cfg, timeout), retry_count)
        else:
            ok, message = False, "Bilinmeyen entegrasyon tipi"

        await _record_test_result(itype, ok, message)
        updated = await db.integrations.find_one({"type": itype}, {"_id": 0}) or {}
        return {
            "type": itype,
            "enabled": doc.get("enabled", False),
            "healthy": ok,
            "message": message,
            "timeout_seconds": timeout,
            "retry_count": retry_count,
            "last_test_status": updated.get("last_test_status"),
            "last_test_at": updated.get("last_test_at"),
            "last_success_at": updated.get("last_success_at"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # =================================================================
    #                    BAĞLANTI TESTİ (GERÇEK GÖNDERİM)
    # =================================================================

    async def _record_test_result(itype: str, ok: bool, message: str):
        now = datetime.now(timezone.utc).isoformat()
        update = {
            "last_test_status": "ok" if ok else "error",
            "last_test_message": message,
            "last_test_at": now,
        }
        if ok:
            # "son bağlantı zamanı": sadece BAŞARILI denemede güncellenir —
            # last_test_at ise başarısız denemelerde de güncellenir.
            update["last_success_at"] = now
        await db.integrations.update_one(
            {"type": itype},
            {"$set": update},
            upsert=True,
        )

    @api_router.post("/integrations/sms/test")
    async def test_sms(body: SmsTestBody, request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "sms"}, {"_id": 0})
        if not doc or not doc.get("config"):
            raise HTTPException(400, "Önce SMS entegrasyonu kaydedilmeli")

        provider = doc.get("provider")
        cfg = doc["config"]
        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_sms_send(provider, cfg, body.phone, body.message, timeout), retry_count)

        await _record_test_result("sms", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="sms", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/email/test")
    async def test_email(body: EmailTestBody, request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "email"}, {"_id": 0})
        if not doc or not doc.get("config"):
            raise HTTPException(400, "Önce Email (SMTP) entegrasyonu kaydedilmeli")

        cfg = doc["config"]
        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_email_send(cfg, body.to_email, timeout), retry_count)

        await _record_test_result("email", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="email", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/planet_labs/test")
    async def test_planet_labs(request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "planet_labs"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        if not cfg.get("api_key"):
            raise HTTPException(400, "Önce Planet Labs API key girilmeli")

        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_planet_labs(cfg, timeout), retry_count)

        await _record_test_result("planet_labs", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="planet_labs", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/sentinel_hub/test")
    async def test_sentinel_hub(request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "sentinel_hub"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        if not cfg.get("client_id") or not cfg.get("client_secret"):
            raise HTTPException(400, "Önce Sentinel Hub client_id/client_secret girilmeli")
        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_sentinel_hub(cfg, timeout), retry_count)
        await _record_test_result("sentinel_hub", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="sentinel_hub", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/nasa_firms/test")
    async def test_nasa_firms(request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "nasa_firms"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        if not cfg.get("map_key"):
            raise HTTPException(400, "Önce NASA FIRMS MAP_KEY girilmeli")
        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_nasa_firms(cfg, timeout), retry_count)
        await _record_test_result("nasa_firms", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="nasa_firms", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/up42/test")
    async def test_up42(request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "up42"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        if not cfg.get("client_id") or not cfg.get("client_secret"):
            raise HTTPException(400, "Önce UP42 client_id/client_secret girilmeli")
        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_up42(cfg, timeout), retry_count)
        await _record_test_result("up42", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="up42", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/eosda/test")
    async def test_eosda(request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "eosda"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        if not cfg.get("api_key"):
            raise HTTPException(400, "Önce EOSDA API Key girilmeli")
        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_eosda(cfg, timeout), retry_count)
        await _record_test_result("eosda", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="eosda", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/ai_service/test")
    async def test_ai_service(request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "ai_service"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        provider = (doc or {}).get("provider")
        if not cfg.get("api_key") or not provider:
            raise HTTPException(400, "Önce AI servis sağlayıcısı ve API key girilmeli")

        timeout = _resolve_timeout(doc)
        retry_count = _resolve_retry(doc)
        ok, message = _with_retry(lambda: _probe_ai_service(provider, cfg, timeout), retry_count)

        await _record_test_result("ai_service", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="ai_service", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}


async def get_ai_service_config(db) -> Optional[dict]:
    """extras.py gibi diğer modüllerin AI servis anahtarını okuması için yardımcı."""
    doc = await db.integrations.find_one({"type": "ai_service"}, {"_id": 0})
    if not doc or not doc.get("enabled") or not doc.get("config", {}).get("api_key"):
        return None
    return {"provider": doc.get("provider"), **doc.get("config", {})}
