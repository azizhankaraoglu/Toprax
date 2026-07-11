"""
=====================================================================
TabSIS — Onay Zinciri Motoru (IT-07b / FAZ 3 devam)
=====================================================================
ROADMAP: "Onay gerektiren her süreç (Destek Talebi, Hakediş/İcmal,
Kampanya, Görev/İş Emri kapanışı, Case atama/devir) kendi onay kuralını
İCAT ETMEZ, bu ortak motoru kullanır." Bu dosya TEK GERÇEK KAYNAK —
support.py/campaigns.py/field_ops.py gibi tüketici modüller SADECE
aşağıdaki `maybe_start_approval()` + `get_pending_for_user()` + `decide()`
fonksiyonlarını çağırır, kendi onay durumu/mantığını YENİDEN YAZMAZ
(automation.py'nin event_bus.py'yi tükettiği desenle AYNI katman ayrımı).

Onay hedefi üç şekilde tanımlanır (ROADMAP'in üç seçeneği, birebir):
  - "role"      → target_value bir rol adı (config.ROLE_HIERARCHY'deki
                  ya da custom_role_id) — o roldeki HERKES onaylayabilir
                  (ilk onaylayan kararı verir, diğerleri düşer).
  - "hierarchy" → target_value şu an SADECE "requester_manager" (talep
                  sahibinin organization.py'den ÇÖZÜLEN doğrudan
                  yöneticisi) — ROADMAP'in "hiyerarşi bazlı" hedefidir.
  - "user"      → target_value doğrudan bir user_id.

Çok adımlı onay desteklenir (`steps` sıralı liste, `order` alanına göre);
ROADMAP'in "önce Bölge Sorumlusu, sonra Finans" örneği budur. Bu
iterasyonda adımlar SIRALI (paralel onay ileride `mode` alanına yeni bir
değer eklenerek genişletilebilir — mimari buna kapalı değil).

Bir `process` için AKTİF kural yoksa `maybe_start_approval()` None döner
— çağıran modül YOLA NORMAL DEVAM EDER (onay altyapısı kurulmamış bir
tenant'ta hiçbir mevcut akış BOZULMAZ, bilinçli geriye-uyumluluk).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from event_bus import publish
from organization import get_manager_user_id

PROCESS_LABELS = {
    "support_request": "Destek Talebi",
    "campaign_publish": "Kampanya Yayını",
    "reconciliation_approval": "İcmal/Mutabakat",
    "task_closure": "Görev Kapanışı",
    "case_assignment": "Case Atama/Devir",
}


class ApprovalStep(BaseModel):
    order: int
    target_type: str          # "role" | "hierarchy" | "user"
    target_value: str         # rol adı | "requester_manager" | user_id
    label: Optional[str] = None


class ApprovalCondition(BaseModel):
    field: Optional[str] = None
    operator: Optional[str] = None   # gt/gte/lt/lte/eq/ne
    value: Optional[Any] = None


class ApprovalChainRuleCreate(BaseModel):
    process: str
    name: str
    condition: Optional[ApprovalCondition] = None
    steps: List[ApprovalStep]


class ApprovalChainRuleUpdate(BaseModel):
    name: Optional[str] = None
    condition: Optional[ApprovalCondition] = None
    steps: Optional[List[ApprovalStep]] = None
    is_active: Optional[bool] = None


class ApprovalDecision(BaseModel):
    decision: str            # "onayla" | "reddet"
    note: Optional[str] = None


def _condition_matches(rule: dict, context: Dict[str, Any]) -> bool:
    cond = rule.get("condition") or {}
    field = cond.get("field")
    if not field:
        return True
    actual = context.get(field)
    op = cond.get("operator", "eq")
    value = cond.get("value")
    if actual is None:
        return False
    if op in ("gt", "gte", "lt", "lte"):
        try:
            actual, value = float(actual), float(value)
        except (TypeError, ValueError):
            return False
        return {"gt": actual > value, "gte": actual >= value,
                "lt": actual < value, "lte": actual <= value}[op]
    if op == "ne":
        return str(actual) != str(value)
    return str(actual) == str(value)   # "eq" varsayılan


async def _resolve_step_approvers(db, step: dict, requester_user_id: str) -> List[str]:
    ttype, tval = step["target_type"], step["target_value"]
    if ttype == "user":
        return [tval]
    if ttype == "role":
        return [u["id"] async for u in db.users.find({"role": tval}, {"_id": 0, "id": 1})]
    if ttype == "hierarchy":
        manager_id = await get_manager_user_id(db, requester_user_id)
        return [manager_id] if manager_id else []
    return []


async def maybe_start_approval(
    db, *, process: str, entity_type: str, entity_id: str,
    requester_user_id: str, context: Optional[Dict[str, Any]] = None,
) -> Optional[dict]:
    """Tüketici modüllerin ÇAĞIRDIĞI tek giriş noktası. `process` için aktif
    ve koşulu tutan bir kural yoksa None döner (çağıran normal akışına
    devam etsin). Varsa, AYNI entity için zaten bekleyen bir instance
    varsa onu döner (idempotent — ikinci çağrı yeni kayıt AÇMAZ)."""
    rule = await db.approval_chain_rules.find_one({"process": process, "is_active": True}, {"_id": 0})
    if not rule or not _condition_matches(rule, context or {}):
        return None
    existing = await db.approval_instances.find_one(
        {"process": process, "entity_id": entity_id, "status": "bekliyor"}, {"_id": 0})
    if existing:
        return existing
    steps = sorted(rule["steps"], key=lambda s: s["order"])
    first_approvers = await _resolve_step_approvers(db, steps[0], requester_user_id)
    doc = {
        "id": str(uuid.uuid4()), "rule_id": rule["id"], "rule_name": rule["name"],
        "process": process, "process_label": PROCESS_LABELS.get(process, process),
        "entity_type": entity_type, "entity_id": entity_id,
        "requester_user_id": requester_user_id, "context": context or {},
        "steps": steps, "current_step_index": 0, "current_approvers": first_approvers,
        "status": "bekliyor", "decisions": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.approval_instances.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_instance_for_entity(db, process: str, entity_id: str) -> Optional[dict]:
    return await db.approval_instances.find_one(
        {"process": process, "entity_id": entity_id}, {"_id": 0}, sort=[("created_at", -1)])


def register_approval_routes(api_router, db, current_user, require_permission, log_audit):

    # ---------------- Onay Kuralı Tanımı (Ayarlar) ----------------
    @api_router.get("/approval-chains")
    async def list_rules(user=Depends(require_permission("approvals:rules_manage"))):
        return await db.approval_chain_rules.find({}, {"_id": 0}).sort("process", 1).to_list(200)

    @api_router.get("/approval-chains/processes")
    async def list_processes(user=Depends(require_permission("approvals:rules_manage"))):
        """UI'nin dropdown'ı için — yeni bir süreç eklemek SADECE PROCESS_LABELS'a
        bir satır eklemek demektir, bu endpoint DEĞİŞMEZ."""
        return [{"key": k, "label": v} for k, v in PROCESS_LABELS.items()]

    @api_router.post("/approval-chains")
    async def create_rule(body: ApprovalChainRuleCreate, request: Request,
                           user=Depends(require_permission("approvals:rules_manage"))):
        existing = await db.approval_chain_rules.find_one({"process": body.process, "is_active": True})
        if existing:
            raise HTTPException(400, "Bu süreç için zaten aktif bir onay kuralı var — önce onu pasifleştirin")
        doc = body.model_dump()
        doc.update({"id": str(uuid.uuid4()), "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat()})
        await db.approval_chain_rules.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="approval_chain_rule", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/approval-chains/{rule_id}")
    async def update_rule(rule_id: str, body: ApprovalChainRuleUpdate, request: Request,
                           user=Depends(require_permission("approvals:rules_manage"))):
        old = await db.approval_chain_rules.find_one({"id": rule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Onay kuralı bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.approval_chain_rules.update_one({"id": rule_id}, {"$set": updates})
        new = await db.approval_chain_rules.find_one({"id": rule_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="approval_chain_rule", entity_id=rule_id, old_value=old, new_value=new, request=request)
        return new

    # ---------------- Onay Bekleyenlerim (modül-bağımsız) ----------------
    @api_router.get("/approvals/pending")
    async def pending_for_me(user=Depends(require_permission("approvals:view_pending"))):
        docs = await db.approval_instances.find(
            {"status": "bekliyor", "current_approvers": user["id"]}, {"_id": 0}
        ).sort("created_at", -1).to_list(200)
        return docs

    @api_router.get("/approvals/{instance_id}")
    async def get_instance(instance_id: str, user=Depends(require_permission("approvals:view_pending"))):
        doc = await db.approval_instances.find_one({"id": instance_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Onay kaydı bulunamadı")
        return doc

    @api_router.post("/approvals/{instance_id}/decide")
    async def decide(instance_id: str, body: ApprovalDecision, request: Request,
                      user=Depends(require_permission("approvals:decide"))):
        inst = await db.approval_instances.find_one({"id": instance_id}, {"_id": 0})
        if not inst:
            raise HTTPException(404, "Onay kaydı bulunamadı")
        if inst["status"] != "bekliyor":
            raise HTTPException(400, "Bu onay zaten karara bağlanmış")
        if user["id"] not in inst.get("current_approvers", []):
            raise HTTPException(403, "Bu adımı onaylama/reddetme yetkiniz yok")
        if body.decision not in ("onayla", "reddet"):
            raise HTTPException(400, "decision 'onayla' veya 'reddet' olmalı")

        decision_entry = {
            "step_index": inst["current_step_index"], "approver_user_id": user["id"],
            "approver_name": user.get("full_name") or user.get("email"),
            "decision": body.decision, "note": body.note,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
        final_decision = None
        if body.decision == "reddet":
            await db.approval_instances.update_one(
                {"id": instance_id}, {"$set": {"status": "reddedildi"}, "$push": {"decisions": decision_entry}})
            final_decision = "reddedildi"
        else:
            next_index = inst["current_step_index"] + 1
            if next_index >= len(inst["steps"]):
                await db.approval_instances.update_one(
                    {"id": instance_id}, {"$set": {"status": "onaylandi"}, "$push": {"decisions": decision_entry}})
                final_decision = "onaylandi"
            else:
                next_approvers = await _resolve_step_approvers(db, inst["steps"][next_index], inst["requester_user_id"])
                await db.approval_instances.update_one(
                    {"id": instance_id},
                    {"$set": {"current_step_index": next_index, "current_approvers": next_approvers},
                     "$push": {"decisions": decision_entry}},
                )

        new = await db.approval_instances.find_one({"id": instance_id}, {"_id": 0})
        await log_audit(db, user, action="decide", entity="approval_instance", entity_id=instance_id,
                         old_value={"status": "bekliyor"}, new_value={"status": new["status"], "decision": body.decision},
                         request=request)

        # Sadece SÜREÇ TAMAMEN bitince (son adım onaylandı VEYA herhangi bir
        # adımda reddedildi) tüketici modül event ile haberdar edilir — ara
        # adım geçişlerinde (çok adımlı zincirde) henüz kimseye event gitmez.
        if final_decision:
            await publish(db, "approval_decided", {
                "process": inst["process"], "entity_type": inst["entity_type"],
                "entity_id": inst["entity_id"], "decision": final_decision,
                "instance_id": instance_id, "note": body.note,
            })
        return new
