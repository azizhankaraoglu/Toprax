"""
=====================================================================
TabSIS — Kural Tabanlı Otomatik Görev Oluşturma (IT-24 / FAZ 8 TAMAMLANDI)
=====================================================================
`event_bus.py`'nin (IT-24'ün TEMEL kullanımı, IT-27'de formalize edilecek)
üzerine kurulu basit bir kural motoru: admin bir `AutomationRule`
tanımlar (event_type + basit eşitlik koşulları + hedef TaskType +
atanacak personel); bir event yayınlandığında (`publish()`) eşleşen
TÜM aktif kurallar `field_ops.create_field_task_from_rule()` ile GERÇEK
bir FieldTask üretir — kod yazmadan, sadece admin ekrandan.

**Koşul dili BİLİNÇLİ OLARAK sadeleştirilmiş** (entitlement.py'nin
`formul` kesintisinde override_amount zorunlu kılması gibi bir
sadeleştirme): sadece düz eşitlik (`payload[field] == value`), hepsi
(AND) sağlanmalı; boş koşul listesi o event_type'ın HER örneğiyle eşleşir.
Roadmap'in "en az 2 otomatik kural" kabul kriteri için bu yeterli —
tam bir filtre DSL'i (query_engine.py'nin operatör kümesi) burada
İSTENMEDİ, çünkü event payload'ları küçük/sabit şekilli (farmer_id/
parcel_id/production_cycle_id vb.), zengin bir sorgu ihtiyacı yok.

Her kural çalıştığında (eşleşsin/eşleşmesin DEĞİL, sadece eşleştiğinde)
`automation_rule_runs`'a bir iz kaydı düşülür — Modül Dashboard'unun
"kaç otomatik görev oluşturuldu" göstergesi buradan gelir.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict

from event_bus import subscribe, EVENT_TYPES
from field_ops import create_field_task_from_rule


class ConditionClause(BaseModel):
    field: str
    value: str


class AutomationRuleCreate(BaseModel):
    name: str
    event_type: str
    conditions: List[ConditionClause] = []
    task_type_id: str
    assigned_to: str
    priority: str = "normal"


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    conditions: Optional[List[ConditionClause]] = None
    task_type_id: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = None
    is_active: Optional[bool] = None


def _conditions_match(conditions: List[dict], payload: dict) -> bool:
    for c in conditions:
        if str(payload.get(c["field"])) != str(c["value"]):
            return False
    return True


async def _handle_automation_event(db, event_type: str, payload: dict) -> None:
    """`event_bus.subscribe()` ile HER `EVENT_TYPES` girdisine bağlanan tek
    handler — hangi kuralın hangi event'e ait olduğunu DB'den (automation_rules)
    okur, event_bus.py'nin kendisi kural bilmez (bilinçli katman ayrımı)."""
    rules = await db.automation_rules.find(
        {"event_type": event_type, "is_active": True}, {"_id": 0}
    ).to_list(200)
    for rule in rules:
        if not _conditions_match(rule.get("conditions", []), payload):
            continue
        created = await create_field_task_from_rule(
            db,
            task_type_id=rule["task_type_id"],
            assigned_to=rule["assigned_to"],
            farmer_id=payload.get("farmer_id"),
            parcel_id=payload.get("parcel_id"),
            production_cycle_id=payload.get("production_cycle_id"),
            priority=rule.get("priority", "normal"),
            created_by=f"otomasyon: {rule['name']}",
        )
        run_doc = {
            "id": str(uuid.uuid4()),
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "event_type": event_type,
            "payload": payload,
            "created_task_id": created["id"] if created else None,
            "status": "created" if created else "skipped_gorev_tipi_yok",
            "ran_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.automation_rule_runs.insert_one(run_doc)


def register_automation_routes(api_router, db, current_user, require_permission, log_audit):
    # server.py başlangıcında BİR KEZ çağrılır (register_* çağrı kalıbıyla
    # aynı yerde) — her bilinen event_type için AYNI handler'ı bağlar,
    # hangi kuralın hangi event'e ait olduğu handler İÇİNDE (DB'den) çözülür.
    for event_type in EVENT_TYPES:
        subscribe(event_type, _handle_automation_event)

    @api_router.get("/automation/event-types")
    async def list_event_types(user=Depends(require_permission("automation:view"))):
        return [{"key": k, "label": v} for k, v in EVENT_TYPES.items()]

    @api_router.get("/automation/rules")
    async def list_rules(user=Depends(require_permission("automation:view"))):
        return await db.automation_rules.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.post("/automation/rules")
    async def create_rule(body: AutomationRuleCreate, request: Request,
                           user=Depends(require_permission("automation:manage"))):
        if body.event_type not in EVENT_TYPES:
            raise HTTPException(400, f"Bilinmeyen event_type: {body.event_type}")
        task_type = await db.task_types.find_one({"id": body.task_type_id, "is_active": True}, {"_id": 0})
        if not task_type:
            raise HTTPException(404, "Görev tipi bulunamadı veya pasif")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.automation_rules.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="automation_rule", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/automation/rules/{rule_id}")
    async def update_rule(rule_id: str, body: AutomationRuleUpdate, request: Request,
                           user=Depends(require_permission("automation:manage"))):
        old = await db.automation_rules.find_one({"id": rule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kural bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        if "task_type_id" in updates:
            task_type = await db.task_types.find_one({"id": updates["task_type_id"], "is_active": True}, {"_id": 0})
            if not task_type:
                raise HTTPException(404, "Görev tipi bulunamadı veya pasif")
        await db.automation_rules.update_one({"id": rule_id}, {"$set": updates})
        new = await db.automation_rules.find_one({"id": rule_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="automation_rule", entity_id=rule_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/automation/rules/{rule_id}")
    async def delete_rule(rule_id: str, request: Request,
                           user=Depends(require_permission("automation:manage"))):
        """Soft delete (convention #3 — hiçbir kayıt fiziksel silinmez)."""
        old = await db.automation_rules.find_one({"id": rule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kural bulunamadı")
        await db.automation_rules.update_one({"id": rule_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="deactivate", entity="automation_rule", entity_id=rule_id, old_value=old, new_value={"is_active": False}, request=request)
        return {"status": "ok"}

    @api_router.get("/automation/rule-runs")
    async def list_rule_runs(rule_id: Optional[str] = None, limit: int = 100,
                              user=Depends(require_permission("automation:view"))):
        filt = {"rule_id": rule_id} if rule_id else {}
        return await db.automation_rule_runs.find(filt, {"_id": 0}).sort("ran_at", -1).to_list(min(limit, 500))
