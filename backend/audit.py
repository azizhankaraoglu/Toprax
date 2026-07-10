"""
=====================================================================
TabSIS — Audit Log Modülü
=====================================================================
Kim / ne yaptı / eski değer / yeni değer / IP / tarayıcı / tarih
kaydını tutar. server.py ve diğer modüller `log_audit()` çağırarak
mutasyon işlemlerini kaydeder. Bu modül ayrıca audit kayıtlarını
listelemek için admin-only bir endpoint sağlar.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Query, Request, Depends
from config import ADMIN_TIER_ROLES


async def log_audit(db, user: dict, action: str, entity: str, entity_id: str = None,
                     old_value: dict = None, new_value: dict = None, request: Request = None):
    """
    Bir işlemi audit_logs koleksiyonuna kaydeder.

    action: "create" | "update" | "delete" | "login" | "test_integration" vb.
    entity: "farmer" | "parcel" | "integration" | "user" vb.
    """
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user.get("id") if user else None,
        "user_email": user.get("email") if user else None,
        "user_role": user.get("role") if user else None,
        "tenant_id": user.get("tenant_id") if user else None,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "old_value": old_value,
        "new_value": new_value,
        "ip": request.client.host if (request and request.client) else None,
        "user_agent": request.headers.get("user-agent") if request else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.audit_logs.insert_one(record)


def register_audit_routes(api_router, db, current_user, is_admin, require_permission=None):
    """server.py içindeki register_* pattern'iyle tutarlı: audit endpoint'lerini bağlar."""

    @api_router.get("/audit/logs")
    async def list_audit_logs(
        entity: str = Query(None),
        user_id: str = Query(None),
        limit: int = Query(100, le=500),
        user=Depends(current_user),
    ):
        allowed = user.get("role") in ADMIN_TIER_ROLES
        if not allowed and require_permission:
            from permissions import get_effective_permissions
            perms = await get_effective_permissions(user, db)
            allowed = "settings:audit_view" in perms
        if not allowed:
            raise HTTPException(403, "Bu kayıtları görme yetkiniz yok")
        q = {}
        if entity:
            q["entity"] = entity
        if user_id:
            q["user_id"] = user_id
        logs = await db.audit_logs.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return {"count": len(logs), "logs": logs}
