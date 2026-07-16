"""api_keys.py -- PR-24: Bearer Token / API Key Mekanizmasi (M2M kimlik dogrulama).

Kullanici login JWT'sinden AYRI, makine-makine entegrasyonlar icin. Anahtar
formati: "toprax_key_<url-safe-32-byte-secret>". DB'de SADECE sha256 hash'i
tutulur -- gercek deger SADECE uretim aninda bir kez donulur, bir daha
gosterilmez (IT-01 secret maskeleme kurali ile ayni ruh).

MIMARI KARAR (tek entegrasyon noktasi): server.py'deki `current_user`
dependency'sine KUCUK bir dal eklenir -- Authorization header'i
"toprax_key_" ile basliyorsa JWT degil API key'dir, burada dogrulanip
SENTETIK bir 'user' dict'i donulur. Boylece TUM mevcut ~370 endpoint
(hepsi zaten current_user/require_permission kullaniyor) SIFIR ek
degisiklikle API key'i de kabul eder -- ayni RBAC/Permission mekanizmasi
(permissions.get_effective_permissions) kullanilir: sentetik user'da
role=None birakilip key'in scope'lari dogrudan permission_overrides.grant
olarak enjekte edilir (get_effective_permissions zaten bu alani okuyor,
degisiklik gerekmedi).

Rate limit: in-process kayan pencere (Redis bu ortamda yok -- CLAUDE.md
'in-process cache' konvansiyonuyla ayni tradeoff, container yeniden
baslarsa sayac sifirlanir; coklu backend replikasi senaryosunda paylasimli
bir store'a (Redis) tasinmasi gerekir, bu bilinen bir sinirdir).
"""
import hashlib
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel

KEY_PREFIX = "toprax_key_"
MANAGE_PERMISSION = "settings:integrations_manage"

_rate_windows: Dict[str, deque] = defaultdict(deque)


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _generate_key() -> str:
    return f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"


class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str]                      # permissions.py PERMISSION_CATALOG anahtarlarıyla aynı format
    expires_at: Optional[str] = None       # ISO8601, None = süresiz
    rate_limit_per_minute: int = 60


async def resolve_api_key_user(raw_db, plaintext_key: str) -> Optional[dict]:
    """Bir API key'i doğrular; geçerliyse get_effective_permissions'ın
    doğrudan tüketebileceği SENTETİK bir user dict'i döner, geçersizse None.
    Rate limit aşılırsa doğrudan HTTPException(429) fırlatır."""
    key_hash = _hash_key(plaintext_key)
    doc = await raw_db.api_keys.find_one({"key_hash": key_hash})
    if not doc or doc.get("revoked"):
        return None
    if doc.get("expires_at"):
        try:
            expires = datetime.fromisoformat(doc["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                return None
        except ValueError:
            pass

    now = time.monotonic()
    window = _rate_windows[doc["id"]]
    limit = doc.get("rate_limit_per_minute", 60)
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(429, f"Rate limit aşıldı (dakikada {limit} istek)")
    window.append(now)

    await raw_db.api_keys.update_one({"id": doc["id"]}, {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}})

    return {
        "id": f"apikey:{doc['id']}",
        "email": f"apikey:{doc['name']}",
        "role": None,
        "tenant_id": doc.get("tenant_id"),
        "farmer_id": None,
        "custom_role_id": None,
        "permission_overrides": {"grant": doc.get("scopes", []), "revoke": []},
        "is_api_key": True,
        "api_key_id": doc["id"],
        "active": True,
    }


def register_api_key_routes(api_router, raw_db, require_permission, log_audit):
    """Entegrasyon Merkezi'nin (Ayarlar > Entegrasyonlar) 'API Anahtarlarım'
    ekranı bu uçları kullanır (bkz. PR-26 Geliştirici Portalı)."""

    @api_router.post("/api-keys")
    async def create_api_key(body: ApiKeyCreate, request: Request,
                               user=Depends(require_permission(MANAGE_PERMISSION))):
        plaintext = _generate_key()
        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": user.get("tenant_id"),
            "name": body.name,
            "key_hash": _hash_key(plaintext),
            "key_prefix": plaintext[:len(KEY_PREFIX) + 6] + "…",
            "scopes": body.scopes,
            "rate_limit_per_minute": body.rate_limit_per_minute,
            "expires_at": body.expires_at,
            "revoked": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.get("email"),
            "last_used_at": None,
        }
        await raw_db.api_keys.insert_one(doc)
        safe_doc = {k: v for k, v in doc.items() if k not in ("_id", "key_hash")}
        await log_audit(raw_db, user, action="create", entity="api_key", entity_id=doc["id"],
                         new_value=safe_doc, request=request)
        # `key` SADECE bu yanıtta bir kez döner -- bundan sonra bir daha gösterilmez.
        return {**safe_doc, "key": plaintext}

    @api_router.get("/api-keys")
    async def list_api_keys(user=Depends(require_permission(MANAGE_PERMISSION))):
        return await raw_db.api_keys.find(
            {"tenant_id": user.get("tenant_id")}, {"_id": 0, "key_hash": 0}
        ).sort("created_at", -1).to_list(200)

    @api_router.delete("/api-keys/{key_id}")
    async def revoke_api_key(key_id: str, request: Request,
                               user=Depends(require_permission(MANAGE_PERMISSION))):
        old = await raw_db.api_keys.find_one({"id": key_id, "tenant_id": user.get("tenant_id")}, {"_id": 0, "key_hash": 0})
        if not old:
            raise HTTPException(404, "API anahtarı bulunamadı")
        await raw_db.api_keys.update_one({"id": key_id}, {"$set": {"revoked": True}})
        await log_audit(raw_db, user, action="revoke", entity="api_key", entity_id=key_id, old_value=old, request=request)
        return {"status": "revoked"}
