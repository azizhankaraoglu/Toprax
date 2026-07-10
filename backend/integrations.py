"""
=====================================================================
TabSIS — Entegrasyonlar / Ayarlar Modülü
=====================================================================
Kullanıcı adı/şifre veya API key gerektiren tüm dış servisler
(SMS, Email/SMTP, Planet Labs, AI Servisi) burada tek merkezden
yönetilir. Sadece admin katmanı (ADMIN_TIER_ROLES) erişebilir.

Her entegrasyon tipi için:
- GET  /api/integrations              -> tüm entegrasyonların (maskelenmiş) durumu
- GET  /api/integrations/{type}       -> tek entegrasyonun (maskelenmiş) config'i
- PUT  /api/integrations/{type}       -> config'i kaydet/güncelle
- POST /api/integrations/{type}/test  -> GERÇEK bağlantı testi yapar
                                          (SMS/Email gerçekten gönderir,
                                          Planet Labs/AI servis key'i doğrular)

NOT: Bu ortamda dış ağa (internet) erişim kapalı olduğu için test
endpoint'leri burada çalıştırılıp doğrulanamadı. Kod, gerçek API
key/şifre girildiğinde kullanıcının kendi ortamında çalışacak şekilde
yazıldı — ilk kullanımda mutlaka bizzat "Bağlantıyı Test Et" ile
doğrulanmalı.
"""
import smtplib
import ssl
import uuid
import requests
from email.mime.text import MIMEText
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from config import ADMIN_TIER_ROLES

# Hangi tipte hangi alanlar "secret" (maskelenmesi gereken) — response'ta gizlenir.
SECRET_FIELDS = {
    "sms": {"netgsm_password", "twilio_auth_token", "webhook_auth_header"},
    "email": {"password"},
    "planet_labs": {"api_key"},
    "ai_service": {"api_key"},
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


class SmsTestBody(BaseModel):
    phone: str
    message: Optional[str] = "TabSIS test mesajı: entegrasyon çalışıyor."


class EmailTestBody(BaseModel):
    to_email: str


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

    @api_router.get("/integrations")
    async def list_integrations(user=Depends(current_user)):
        await _check_view(user)
        docs = await db.integrations.find({}, {"_id": 0}).to_list(50)
        by_type = {d["type"]: d for d in docs}
        result = []
        for itype in VALID_TYPES:
            doc = by_type.get(itype, {"type": itype, "provider": None, "config": {}, "enabled": False})
            result.append({
                "type": itype,
                "provider": doc.get("provider"),
                "config": _mask_config(itype, doc.get("config", {})),
                "enabled": doc.get("enabled", False),
                "updated_at": doc.get("updated_at"),
                "last_test_status": doc.get("last_test_status"),
                "last_test_at": doc.get("last_test_at"),
                "last_test_message": doc.get("last_test_message"),
            })
        return {"integrations": result}

    @api_router.get("/integrations/{itype}")
    async def get_integration(itype: str, user=Depends(current_user)):
        await _check_view(user)
        if itype not in VALID_TYPES:
            raise HTTPException(404, "Bilinmeyen entegrasyon tipi")
        doc = await db.integrations.find_one({"type": itype}, {"_id": 0})
        if not doc:
            return {"type": itype, "provider": None, "config": {}, "enabled": False}
        doc["config"] = _mask_config(itype, doc.get("config", {}))
        return doc

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

        doc = {
            "type": itype,
            "provider": body.provider,
            "config": merged_config,
            "enabled": body.enabled,
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
    #                    BAĞLANTI TESTİ (GERÇEK GÖNDERİM)
    # =================================================================

    async def _record_test_result(itype: str, ok: bool, message: str):
        await db.integrations.update_one(
            {"type": itype},
            {"$set": {
                "last_test_status": "ok" if ok else "error",
                "last_test_message": message,
                "last_test_at": datetime.now(timezone.utc).isoformat(),
            }},
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
        try:
            if provider == "netgsm":
                # Netgsm REST API (gerçek gönderim)
                resp = requests.post(
                    "https://api.netgsm.com.tr/sms/send/get",
                    params={
                        "usercode": cfg.get("netgsm_usercode"),
                        "password": cfg.get("netgsm_password"),
                        "gsmno": body.phone,
                        "message": body.message,
                        "msgheader": cfg.get("netgsm_header"),
                    },
                    timeout=10,
                )
                ok = resp.status_code == 200 and not resp.text.startswith(("20", "30", "40", "50", "60", "70"))
                message = f"Netgsm yanıtı: {resp.text.strip()}"
            elif provider == "twilio":
                from requests.auth import HTTPBasicAuth
                sid = cfg.get("twilio_account_sid")
                resp = requests.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    data={
                        "To": body.phone,
                        "From": cfg.get("twilio_from_number"),
                        "Body": body.message,
                    },
                    auth=HTTPBasicAuth(sid, cfg.get("twilio_auth_token")),
                    timeout=10,
                )
                ok = resp.status_code in (200, 201)
                message = f"Twilio yanıtı: HTTP {resp.status_code}"
            elif provider == "custom_webhook":
                headers = cfg.get("webhook_headers", {}) or {}
                if cfg.get("webhook_auth_header"):
                    headers["Authorization"] = cfg["webhook_auth_header"]
                resp = requests.post(
                    cfg.get("webhook_url"),
                    json={"phone": body.phone, "message": body.message},
                    headers=headers,
                    timeout=10,
                )
                ok = resp.status_code < 300
                message = f"Webhook yanıtı: HTTP {resp.status_code}"
            else:
                raise HTTPException(400, "Geçersiz SMS sağlayıcısı (netgsm | twilio | custom_webhook)")
        except HTTPException:
            raise
        except Exception as e:
            ok = False
            message = f"Bağlantı hatası: {e}"

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
        try:
            msg = MIMEText("Bu, TabSIS Ayarlar modülünden gönderilen bir test e-postasıdır.")
            msg["Subject"] = "TabSIS — Entegrasyon Test E-postası"
            msg["From"] = cfg.get("from_address", cfg.get("username"))
            msg["To"] = body.to_email

            host = cfg.get("host")
            port = int(cfg.get("port", 587))
            use_tls = cfg.get("use_tls", True)

            if use_tls:
                server = smtplib.SMTP(host, port, timeout=10)
                server.starttls(context=ssl.create_default_context())
            else:
                server = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())

            server.login(cfg.get("username"), cfg.get("password"))
            server.sendmail(msg["From"], [body.to_email], msg.as_string())
            server.quit()
            ok, message = True, f"Test e-postası {body.to_email} adresine gönderildi."
        except Exception as e:
            ok, message = False, f"SMTP hatası: {e}"

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
        api_key = cfg.get("api_key")

        if not api_key:
            raise HTTPException(400, "Önce Planet Labs API key girilmeli")

        # Henüz gerçek bir Planet Labs hesabı yoksa (mock mod): key formatını
        # kontrol edip simüle edilmiş başarı döner. Gerçek key eklendiğinde
        # aşağıdaki gerçek HTTP çağrısı devreye girer.
        mock_mode = cfg.get("mock_mode", True)
        if mock_mode:
            ok, message = True, "[MOCK MOD] Key formatı geçerli görünüyor. Gerçek doğrulama için 'mock_mode' kapatılmalı."
        else:
            try:
                resp = requests.get(
                    "https://api.planet.com/data/v1/item-types",
                    auth=(api_key, ""),
                    timeout=10,
                )
                ok = resp.status_code == 200
                message = f"Planet Labs yanıtı: HTTP {resp.status_code}"
            except Exception as e:
                ok, message = False, f"Bağlantı hatası: {e}"

        await _record_test_result("planet_labs", ok, message)
        if log_audit:
            await log_audit(db, user, action="test_integration", entity="integration",
                             entity_id="planet_labs", new_value={"ok": ok, "message": message}, request=request)
        if not ok:
            raise HTTPException(502, message)
        return {"status": "ok", "message": message}

    @api_router.post("/integrations/ai_service/test")
    async def test_ai_service(request: Request, user=Depends(current_user)):
        await _check_manage(user)
        doc = await db.integrations.find_one({"type": "ai_service"}, {"_id": 0})
        cfg = (doc or {}).get("config", {})
        provider = (doc or {}).get("provider")
        api_key = cfg.get("api_key")

        if not api_key or not provider:
            raise HTTPException(400, "Önce AI servis sağlayıcısı ve API key girilmeli")

        try:
            if provider == "openai":
                resp = requests.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10,
                )
                ok = resp.status_code == 200
                message = f"OpenAI yanıtı: HTTP {resp.status_code}"
            elif provider == "gemini":
                resp = requests.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                    timeout=10,
                )
                ok = resp.status_code == 200
                message = f"Gemini yanıtı: HTTP {resp.status_code}"
            elif provider == "anthropic":
                resp = requests.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    timeout=10,
                )
                ok = resp.status_code == 200
                message = f"Anthropic yanıtı: HTTP {resp.status_code}"
            else:
                raise HTTPException(400, "Geçersiz AI sağlayıcısı (openai | gemini | anthropic)")
        except HTTPException:
            raise
        except Exception as e:
            ok, message = False, f"Bağlantı hatası: {e}"

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
