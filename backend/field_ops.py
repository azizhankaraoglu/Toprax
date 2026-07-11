"""
=====================================================================
TabSIS — Saha Operasyonları: İş Emri / Görev / Ziyaret Üçlü Modeli
(IT-22 / FAZ 8 — Sprint 8, Saha Operasyonları başlangıcı)
=====================================================================
ROADMAP'in özellikle vurguladığı kavramsal ayrım — ÜÇÜ AYRI ENTITY,
aynı tabloya sıkıştırılmaz:

- **WorkOrder (İş Emri):** yönetim seviyesi planlama (amaç + zaman
  aralığı + bölge/parsel kapsamı + personel listesi). Oluşturulduğunda
  personel×parsel eşleştirmesiyle görevleri TOPLU türetir (round-robin).
- **FieldTask (Görev):** personele atanan TEKİL operasyon, 11 durumlu
  SIRALI durum makinesi. work_order_id NULLABLE — bağımsız (ad-hoc)
  görev de olabilir.
- **Visit (Ziyaret):** görevin sahada fiilen gerçekleştiği kayıt(lar) —
  bir görev için BİRDEN FAZLA ziyaret olabilir (tamamlanamayan ziyaret
  yeniden planlanır).

**BİLİNÇLİ OLARAK YENİ/AYRI KOLEKSİYONLAR** (`work_orders`, `field_tasks`,
`visits`) — Sprint 4'ten kalma `db.tasks` (data_entry.py'deki basit
Operasyon Görevi: düz `task_type` metni, 4 durum, work order/checklist/
visit kavramı YOK, Operasyon.jsx + Hızlı İşlemler + Harita "+ Görev"
tarafından kullanılıyor) ile KARIŞTIRILMAZ/BİRLEŞTİRİLMEZ — ROADMAP'in
"aynı tabloya sıkıştırılmamalı" ilkesi zaten bunu ima ediyor, ayrıca bu
iki sistem farklı olgunluk seviyesinde (biri hızlı/serbest metin, diğeri
katalogtan TaskType + 11 durum + checklist zorunluluğu).

**Checklist kuralı (API seviyesinde zorlanır):** bir FieldTask
`kapandi` durumuna SADECE tüm checklist kalemleri tamamlanmışsa
geçebilir — `transition_task()` içinde kontrol edilir.

**Form entegrasyonu:** TaskType'a opsiyonel `form_id` (forms_module.py'nin
`db.forms` koleksiyonundaki bir M18 saha anket formuna referans) —
YENİ bir form-doldurma mekanizması İCAT EDİLMEDİ, mevcut forms_module.py
altyapısı (assignment/response) kullanılmaya devam eder, burada sadece
"bu görev tipine hangi form önerilir" bilgisi taşınır.

**Kapsam notu:** ROADMAP'in IT-22 bölümünde ayrı bir "UI:" maddesi YOK
ve IT-23 ZATEN bu modelin Kanban/Takvim/Harita UI'ını kapsıyor — bu
iterasyon BİLİNÇLİ OLARAK sadece backend (IT-05→IT-06, IT-20 emsalleriyle
tutarlı).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict

from event_bus import publish

DEFAULT_TASK_TYPES = [
    "Çiftçi Ziyareti", "Toprak Numunesi", "Hasat Kontrolü", "Ekim Kontrolü",
    "Sulama Kontrolü", "Gübreleme Kontrolü", "İlaçlama Kontrolü", "Drone Çekimi",
    "Fotoğraf Çekimi", "Evrak Teslimi", "ÇKS Kontrolü", "Denetim",
]

# ROADMAP'in verdiği TAM checklist kalemi listesi — TaskType bunların bir
# alt kümesini varsayılan olarak taşır, admin Form Yönetimi benzeri bir
# ekranda değiştirebilir (bu iterasyonda API üzerinden).
CHECKLIST_CATALOG = [
    "Form Dolduruldu", "Fotoğraf Çekildi", "GPS Kaydedildi", "Çiftçi Onayı Alındı",
    "Numune Alındı", "Drone Görüntüsü Yüklendi", "Evrak Teslim Edildi",
]

# 11 durum, SIRALI ana akış + her aşamadan iptal + reddedildi'den yeniden planlama.
TASK_STATUS_FLOW = [
    "planlandi", "atandi", "kabul_edildi", "yola_cikildi", "yerine_ulasildi",
    "calisiliyor", "tamamlandi", "onay_bekliyor", "kapandi",
]
TASK_STATUS_LABELS = {
    "planlandi": "Planlandı", "atandi": "Atandı", "kabul_edildi": "Kabul Edildi",
    "reddedildi": "Reddedildi", "yola_cikildi": "Yola Çıkıldı",
    "yerine_ulasildi": "Görev Yerine Ulaşıldı", "calisiliyor": "Çalışılıyor",
    "tamamlandi": "Tamamlandı", "onay_bekliyor": "Yönetici Onayı Bekliyor",
    "kapandi": "Kapandı", "iptal_edildi": "İptal Edildi",
}
TASK_ALLOWED_TRANSITIONS: Dict[str, set] = {}
for _i, _s in enumerate(TASK_STATUS_FLOW[:-1]):
    TASK_ALLOWED_TRANSITIONS[_s] = {TASK_STATUS_FLOW[_i + 1], "iptal_edildi"}
TASK_ALLOWED_TRANSITIONS["atandi"].add("reddedildi")
TASK_ALLOWED_TRANSITIONS["reddedildi"] = {"planlandi", "iptal_edildi"}  # yeniden planlama
TASK_ALLOWED_TRANSITIONS["kapandi"] = set()       # terminal
TASK_ALLOWED_TRANSITIONS["iptal_edildi"] = set()  # terminal


class TaskTypeCreate(BaseModel):
    name: str
    form_id: Optional[str] = None
    default_checklist: List[str] = []


class TaskTypeUpdate(BaseModel):
    name: Optional[str] = None
    form_id: Optional[str] = None
    default_checklist: Optional[List[str]] = None
    is_active: Optional[bool] = None


class WorkOrderCreate(BaseModel):
    title: str
    purpose: Optional[str] = None
    start_date: str
    end_date: str
    region_id: Optional[str] = None
    parcel_ids: List[str] = []
    assigned_users: List[str] = []
    task_type_id: str
    priority: str = "normal"  # dusuk | normal | yuksek


class TaskCreate(BaseModel):
    """Bağımsız (ad-hoc) görev — work_order_id YOK, tek tek oluşturulur."""
    farmer_id: Optional[str] = None
    parcel_id: Optional[str] = None
    production_cycle_id: Optional[str] = None
    task_type_id: str
    assigned_to: str
    priority: str = "normal"
    planned_date: str
    sla_due_date: Optional[str] = None


class TaskTransition(BaseModel):
    status: str
    reason: Optional[str] = None  # reddedildi/iptal_edildi için opsiyonel


class ChecklistToggle(BaseModel):
    item: str
    done: bool


class VisitCreate(BaseModel):
    task_id: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    gps_start: Optional[Dict[str, float]] = None
    gps_end: Optional[Dict[str, float]] = None
    photos: List[str] = []
    form_response: Optional[dict] = None
    notes: Optional[str] = None


class VisitUpdate(BaseModel):
    ended_at: Optional[str] = None
    gps_end: Optional[Dict[str, float]] = None
    photos: Optional[List[str]] = None
    form_response: Optional[dict] = None
    notes: Optional[str] = None


async def create_field_task_from_rule(
    db, *, task_type_id: str, assigned_to: str, farmer_id: Optional[str] = None,
    parcel_id: Optional[str] = None, production_cycle_id: Optional[str] = None,
    priority: str = "normal", planned_date: Optional[str] = None,
    created_by: str = "otomasyon (IT-24)",
) -> Optional[dict]:
    """(IT-24) `automation.py`'nin kural motoru tarafından çağrılır — `POST /tasks`
    (create_field_task) ile AYNI doküman şemasını üretir, tek fonksiyona
    çıkarılmıştır (event handler'da HTTP request/user context'i olmadığı için
    endpoint'in kendisi DEĞİL bu fonksiyon çağrılır). `task_type_id` yok/pasifse
    sessizce None döner — otomasyon bir HTTPException fırlatamaz, sadece
    `automation.py`'nin kural sonuç kaydına "atlandı" olarak işlenir."""
    task_type = await db.task_types.find_one({"id": task_type_id, "is_active": True}, {"_id": 0})
    if not task_type:
        return None
    if parcel_id and not farmer_id:
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        farmer_id = parcel.get("farmer_id") if parcel else None
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "farmer_id": farmer_id,
        "parcel_id": parcel_id,
        "production_cycle_id": production_cycle_id,
        "task_type_id": task_type_id,
        "assigned_to": assigned_to,
        "priority": priority,
        "planned_date": planned_date or now,
        "sla_due_date": None,
        "work_order_id": None,
        "status": "planlandi",
        "checklist": [{"item": c, "done": False} for c in task_type.get("default_checklist", [])],
        "close_reason": None,
        "created_by": created_by,
        "created_at": now,
        "status_updated_at": now,
    }
    await db.field_tasks.insert_one(doc)
    doc.pop("_id", None)
    # (IT-27) Communication Policy tetikleyicisi — "Görev Atandı" örneği.
    await publish(db, "task_assigned", {
        "assigned_to": assigned_to, "farmer_id": farmer_id, "parcel_id": parcel_id,
        "task_type_id": task_type_id,
    })
    return doc


def register_field_ops_routes(api_router, db, current_user, require_permission, log_audit):

    async def _check_task_access(user: dict, task: dict, require_manage: bool = False):
        """Görevi ÜSTLENEN kullanıcı kendi görevini yönetebilir (permission gerekmez);
        başkasının görevine dokunmak için field_ops:manage gerekir."""
        if not require_manage and user.get("id") == task.get("assigned_to"):
            return
        from permissions import get_effective_permissions
        perms = await get_effective_permissions(user, db)
        if "field_ops:manage" not in perms:
            raise HTTPException(403, "Bu göreve erişim izniniz yok")

    @api_router.get("/field-ops/assignable-users")
    async def list_assignable_users(user=Depends(require_permission("field_ops:view"))):
        """(IT-23) Görev atama formlarında personel seçimi — `settings:users_view`
        (ayrı/daha geniş bir izin) İSTEMEZ BİLİNÇLİ OLARAK: field_ops:manage sahibi
        (örn. ziraat_muhendisi) kullanıcı yönetimi iznine sahip olmadan da saha
        personelini görüp göreve atayabilmeli — sadece id/full_name/role döner."""
        docs = await db.users.find(
            {"role": {"$in": ["ziraat_muhendisi", "saha_personeli", "toprak_personeli", "kantar_personeli"]}},
            {"_id": 0, "id": 1, "full_name": 1, "role": 1},
        ).to_list(500)
        return docs

    # =================================================================
    # TASK TYPE KATALOĞU
    # =================================================================
    @api_router.get("/task-types")
    async def list_task_types(include_inactive: bool = False, user=Depends(require_permission("field_ops:view"))):
        filt = {} if include_inactive else {"is_active": True}
        return await db.task_types.find(filt, {"_id": 0}).sort("name", 1).to_list(200)

    @api_router.post("/task-types")
    async def create_task_type(body: TaskTypeCreate, request: Request, user=Depends(require_permission("field_ops:manage"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.task_types.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="task_type", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/task-types/{type_id}")
    async def update_task_type(type_id: str, body: TaskTypeUpdate, request: Request, user=Depends(require_permission("field_ops:manage"))):
        old = await db.task_types.find_one({"id": type_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Görev tipi bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.task_types.update_one({"id": type_id}, {"$set": updates})
        new = await db.task_types.find_one({"id": type_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="task_type", entity_id=type_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.post("/task-types/seed-defaults")
    async def seed_default_task_types(request: Request, user=Depends(require_permission("field_ops:manage"))):
        created = []
        for name in DEFAULT_TASK_TYPES:
            if await db.task_types.find_one({"name": name}, {"_id": 0}):
                continue
            doc = {
                "id": str(uuid.uuid4()), "name": name, "form_id": None,
                "default_checklist": ["Form Dolduruldu", "Fotoğraf Çekildi", "GPS Kaydedildi"],
                "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.task_types.insert_one(doc)
            created.append(name)
        if created:
            await log_audit(db, user, action="seed", entity="task_type", entity_id="bulk", new_value={"created": created}, request=request)
        return {"status": "ok", "created": created}

    # =================================================================
    # İŞ EMRİ (WorkOrder) — oluşturunca TOPLU görev üretir
    # =================================================================
    @api_router.get("/work-orders")
    async def list_work_orders(status: Optional[str] = None, user=Depends(require_permission("field_ops:view"))):
        filt = {"status": status} if status else {}
        return await db.work_orders.find(filt, {"_id": 0}).sort("created_at", -1).to_list(500)

    @api_router.get("/work-orders/{work_order_id}")
    async def get_work_order(work_order_id: str, user=Depends(require_permission("field_ops:view"))):
        doc = await db.work_orders.find_one({"id": work_order_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "İş emri bulunamadı")
        tasks = await db.field_tasks.find({"work_order_id": work_order_id}, {"_id": 0}).to_list(1000)
        return {"work_order": doc, "tasks": tasks}

    @api_router.post("/work-orders")
    async def create_work_order(body: WorkOrderCreate, request: Request, user=Depends(require_permission("field_ops:manage"))):
        task_type = await db.task_types.find_one({"id": body.task_type_id, "is_active": True}, {"_id": 0})
        if not task_type:
            raise HTTPException(404, "Görev tipi bulunamadı veya pasif")
        if not body.assigned_users:
            raise HTTPException(400, "En az bir personel atanmalı")
        if not body.parcel_ids:
            raise HTTPException(400, "En az bir parsel kapsam dahilinde olmalı")

        wo = body.model_dump()
        wo["id"] = str(uuid.uuid4())
        wo["status"] = "aktif"
        wo["created_by"] = user.get("full_name") or user.get("email")
        wo["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.work_orders.insert_one(wo)
        wo.pop("_id", None)

        parcels = await db.parcels.find({"id": {"$in": body.parcel_ids}}, {"_id": 0}).to_list(len(body.parcel_ids))
        created_tasks = []
        now = datetime.now(timezone.utc).isoformat()
        for i, parcel in enumerate(parcels):
            assigned_to = body.assigned_users[i % len(body.assigned_users)]  # round-robin dağıtım
            task = {
                "id": str(uuid.uuid4()),
                "work_order_id": wo["id"],
                "farmer_id": parcel.get("farmer_id"),
                "parcel_id": parcel["id"],
                "production_cycle_id": None,
                "task_type_id": body.task_type_id,
                "assigned_to": assigned_to,
                "priority": body.priority,
                "planned_date": body.start_date,
                "sla_due_date": body.end_date,
                "status": "planlandi",
                "checklist": [{"item": c, "done": False} for c in task_type.get("default_checklist", [])],
                "close_reason": None,
                "created_by": wo["created_by"],
                "created_at": now,
                "status_updated_at": now,
            }
            await db.field_tasks.insert_one(task)
            task.pop("_id", None)
            created_tasks.append(task)
            # (IT-27) Communication Policy tetikleyicisi — "Görev Atandı" örneği,
            # iş emrinin ürettiği HER görev için ayrı ayrı yayınlanır.
            await publish(db, "task_assigned", {
                "assigned_to": task["assigned_to"], "farmer_id": task.get("farmer_id"),
                "parcel_id": task.get("parcel_id"), "task_type_id": task["task_type_id"],
            })

        await log_audit(db, user, action="create", entity="work_order", entity_id=wo["id"],
                         new_value={"work_order": wo, "tasks_created": len(created_tasks)}, request=request)
        return {"work_order": wo, "tasks": created_tasks}

    # =================================================================
    # GÖREV (FieldTask)
    # =================================================================
    @api_router.get("/tasks")
    async def list_field_tasks(
        assigned_to: Optional[str] = None, status: Optional[str] = None,
        farmer_id: Optional[str] = None, parcel_id: Optional[str] = None,
        production_cycle_id: Optional[str] = None, work_order_id: Optional[str] = None,
        user=Depends(require_permission("field_ops:view")),
    ):
        filt = {}
        if assigned_to: filt["assigned_to"] = assigned_to
        if status: filt["status"] = status
        if farmer_id: filt["farmer_id"] = farmer_id
        if parcel_id: filt["parcel_id"] = parcel_id
        if production_cycle_id: filt["production_cycle_id"] = production_cycle_id
        if work_order_id: filt["work_order_id"] = work_order_id
        return await db.field_tasks.find(filt, {"_id": 0}).sort("planned_date", 1).to_list(1000)

    @api_router.get("/tasks/{task_id}")
    async def get_field_task(task_id: str, user=Depends(require_permission("field_ops:view"))):
        doc = await db.field_tasks.find_one({"id": task_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Görev bulunamadı")
        return doc

    @api_router.post("/tasks")
    async def create_field_task(body: TaskCreate, request: Request, user=Depends(require_permission("field_ops:manage"))):
        task_type = await db.task_types.find_one({"id": body.task_type_id, "is_active": True}, {"_id": 0})
        if not task_type:
            raise HTTPException(404, "Görev tipi bulunamadı veya pasif")
        if body.parcel_id:
            parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
            if not parcel:
                raise HTTPException(404, "Parsel bulunamadı")
            farmer_id = body.farmer_id or parcel.get("farmer_id")
        else:
            farmer_id = body.farmer_id

        doc = body.model_dump()
        doc["farmer_id"] = farmer_id
        doc["id"] = str(uuid.uuid4())
        doc["work_order_id"] = None
        doc["status"] = "planlandi"
        doc["checklist"] = [{"item": c, "done": False} for c in task_type.get("default_checklist", [])]
        doc["close_reason"] = None
        doc["created_by"] = user.get("full_name") or user.get("email")
        now = datetime.now(timezone.utc).isoformat()
        doc["created_at"] = now
        doc["status_updated_at"] = now
        await db.field_tasks.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="field_task", entity_id=doc["id"], new_value=doc, request=request)
        # (IT-27) Communication Policy tetikleyicisi — "Görev Atandı" örneği.
        await publish(db, "task_assigned", {
            "assigned_to": doc["assigned_to"], "farmer_id": doc.get("farmer_id"),
            "parcel_id": doc.get("parcel_id"), "task_type_id": doc["task_type_id"],
        })
        return doc

    @api_router.put("/tasks/{task_id}/transition")
    async def transition_field_task(task_id: str, body: TaskTransition, request: Request, user=Depends(current_user)):
        old = await db.field_tasks.find_one({"id": task_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Görev bulunamadı")
        await _check_task_access(user, old, require_manage=False)

        if body.status not in TASK_ALLOWED_TRANSITIONS:
            raise HTTPException(400, f"Geçersiz durum: {body.status}")
        current = old["status"]
        allowed = TASK_ALLOWED_TRANSITIONS.get(current, set())
        if body.status not in allowed:
            raise HTTPException(
                400,
                f"'{TASK_STATUS_LABELS.get(current, current)}' durumundan "
                f"'{TASK_STATUS_LABELS.get(body.status, body.status)}' durumuna geçilemez"
                + (f" (izin verilenler: {', '.join(TASK_STATUS_LABELS[s] for s in allowed)})" if allowed else " (bu durum terminaldir)"),
            )

        # KRİTİK KURAL (kabul kriteri): checklist tamamlanmadan kapandı'ya geçilemez.
        if body.status == "kapandi":
            incomplete = [c["item"] for c in old.get("checklist", []) if not c.get("done")]
            if incomplete:
                raise HTTPException(400, f"Checklist tamamlanmadan görev kapatılamaz: {', '.join(incomplete)}")

        updates = {"status": body.status, "status_updated_at": datetime.now(timezone.utc).isoformat()}
        if body.status in ("reddedildi", "iptal_edildi") and body.reason:
            updates["close_reason"] = body.reason

        await db.field_tasks.update_one({"id": task_id}, {"$set": updates})
        new = await db.field_tasks.find_one({"id": task_id}, {"_id": 0})
        await log_audit(db, user, action="status_change", entity="field_task", entity_id=task_id,
                         old_value={"status": current}, new_value={"status": body.status}, request=request)
        return new

    @api_router.put("/tasks/{task_id}/checklist")
    async def toggle_task_checklist(task_id: str, body: ChecklistToggle, request: Request, user=Depends(current_user)):
        old = await db.field_tasks.find_one({"id": task_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Görev bulunamadı")
        await _check_task_access(user, old, require_manage=False)

        checklist = old.get("checklist", [])
        found = False
        for c in checklist:
            if c["item"] == body.item:
                c["done"] = body.done
                found = True
                break
        if not found:
            raise HTTPException(404, f"Checklist kalemi bulunamadı: {body.item}")

        await db.field_tasks.update_one({"id": task_id}, {"$set": {"checklist": checklist}})
        new = await db.field_tasks.find_one({"id": task_id}, {"_id": 0})
        await log_audit(db, user, action="checklist_update", entity="field_task", entity_id=task_id,
                         old_value={"item": body.item}, new_value={"item": body.item, "done": body.done}, request=request)
        return new

    # =================================================================
    # ZİYARET (Visit) — bir görev için 1:N
    # =================================================================
    @api_router.get("/visits")
    async def list_visits(
        task_id: Optional[str] = None, farmer_id: Optional[str] = None,
        parcel_id: Optional[str] = None, production_cycle_id: Optional[str] = None,
        user=Depends(require_permission("field_ops:view")),
    ):
        """(IT-23) farmer_id/parcel_id/production_cycle_id filtreleri — Ziyaret
        Geçmişi sekmesi (FarmerDetail/ParcelDetail/ProductionCycleDetail) için;
        create_visit bu alanları task'tan DENORMALİZE ettiği için ayrı bir
        join sorgusu gerekmez."""
        filt = {}
        if task_id: filt["task_id"] = task_id
        if farmer_id: filt["farmer_id"] = farmer_id
        if parcel_id: filt["parcel_id"] = parcel_id
        if production_cycle_id: filt["production_cycle_id"] = production_cycle_id
        return await db.visits.find(filt, {"_id": 0}).sort("started_at", -1).to_list(1000)

    @api_router.post("/visits")
    async def create_visit(body: VisitCreate, request: Request, user=Depends(current_user)):
        task = await db.field_tasks.find_one({"id": body.task_id}, {"_id": 0})
        if not task:
            raise HTTPException(404, "Görev bulunamadı")
        await _check_task_access(user, task, require_manage=False)

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["started_at"] = body.started_at or datetime.now(timezone.utc).isoformat()
        doc["visited_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        # (IT-23) Ziyaret Geçmişi sekmesinin join'süz filtrelenebilmesi için
        # task'tan denormalize edilir (task silinse/değişse bile ziyaret kaydı
        # o anki bağlamını korur — bilinçli, audit-benzeri bir tercih).
        doc["farmer_id"] = task.get("farmer_id")
        doc["parcel_id"] = task.get("parcel_id")
        doc["production_cycle_id"] = task.get("production_cycle_id")
        doc["task_type_id"] = task.get("task_type_id")
        await db.visits.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="visit", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/visits/{visit_id}")
    async def update_visit(visit_id: str, body: VisitUpdate, request: Request, user=Depends(current_user)):
        old = await db.visits.find_one({"id": visit_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Ziyaret bulunamadı")
        task = await db.field_tasks.find_one({"id": old["task_id"]}, {"_id": 0})
        await _check_task_access(user, task or {}, require_manage=False)

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.visits.update_one({"id": visit_id}, {"$set": updates})
        new = await db.visits.find_one({"id": visit_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="visit", entity_id=visit_id, old_value=old, new_value=new, request=request)
        return new

    # =================================================================
    # ÇİFTÇİ PORTALI — Ziyaret Onaylama (IT-38 / FAZ 13, mobil self-servis)
    # support.py'nin `/portal/*` kalıbıyla AYNI: role=="ciftci" + farmer_id
    # sahiplik kontrolü, permission sistemine dahil DEĞİL (field_ops:view
    # ciftci'ye zaten kapalı, bkz. permissions.py "ciftci": []). Visit
    # dokümanına yeni, opsiyonel `confirmed_by_farmer` alanı eklenir —
    # eski kayıtlarda YOK, okuyan her yer `.get(..., False)` ile ele alır,
    # geriye dönük kırılma yok.
    # =================================================================
    @api_router.get("/portal/visits")
    async def portal_list_my_visits(user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        return await db.visits.find({"farmer_id": user["farmer_id"]}, {"_id": 0}).sort("started_at", -1).to_list(100)

    @api_router.put("/portal/visits/{visit_id}/confirm-by-farmer")
    async def portal_confirm_visit(visit_id: str, request: Request, user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi onaylayabilir")
        old = await db.visits.find_one({"id": visit_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Ziyaret bulunamadı")
        if old.get("farmer_id") != user["farmer_id"]:
            raise HTTPException(404, "Ziyaret bulunamadı")  # varlığı dahi sızdırma
        await db.visits.update_one({"id": visit_id}, {"$set": {
            "confirmed_by_farmer": True,
            "confirmed_by_farmer_at": datetime.now(timezone.utc).isoformat(),
        }})
        new = await db.visits.find_one({"id": visit_id}, {"_id": 0})
        await log_audit(db, user, action="confirm", entity="visit", entity_id=visit_id,
                         old_value={"confirmed_by_farmer": old.get("confirmed_by_farmer", False)},
                         new_value={"confirmed_by_farmer": True}, request=request)
        return new

    # =================================================================
    # MODÜL DASHBOARD'U (IT-24) — ufyd/dashboard (reconciliation.py) ile
    # AYNI desen: canlı hesaplanır, ayrı bir önceden-toplanmış istatistik
    # koleksiyonu YOK.
    # =================================================================
    @api_router.get("/field-ops/dashboard")
    async def field_ops_dashboard(user=Depends(require_permission("field_ops:view"))):
        now = datetime.now(timezone.utc)
        today_str = now.date().isoformat()
        TERMINAL = {"kapandi", "iptal_edildi"}

        active_work_orders = await db.work_orders.count_documents({"status": "aktif"})
        tasks = await db.field_tasks.find({}, {"_id": 0}).to_list(5000)
        active_tasks = [t for t in tasks if t.get("status") not in TERMINAL]

        overdue_tasks = 0
        for t in active_tasks:
            due = t.get("sla_due_date")
            if not due:
                continue
            try:
                if datetime.fromisoformat(due) < now:
                    overdue_tasks += 1
            except ValueError:
                continue

        today_visits = await db.visits.count_documents({"started_at": {"$regex": f"^{today_str}"}})

        # Personel Doluluk Oranı — o an aktif görevi olan personel bazında.
        staff_load: Dict[str, int] = {}
        for t in active_tasks:
            aid = t.get("assigned_to")
            if aid:
                staff_load[aid] = staff_load.get(aid, 0) + 1
        staff_docs = (
            await db.users.find({"id": {"$in": list(staff_load.keys())}}, {"_id": 0, "id": 1, "full_name": 1}).to_list(500)
            if staff_load else []
        )
        name_by_id = {u["id"]: u["full_name"] for u in staff_docs}
        staff_utilization = [
            {"user_id": uid, "full_name": name_by_id.get(uid, uid), "active_tasks": count}
            for uid, count in sorted(staff_load.items(), key=lambda x: x[1], reverse=True)
        ]

        # Bölgesel Operasyon Yoğunluğu — parcel.region_id üzerinden (admin_areas
        # değil — parcels zaten IT-01'den beri düz bir region_id taşıyor,
        # admin_areas'ın $geoIntersects'i bu basit sayım için gereksiz maliyet).
        parcel_ids = list({t["parcel_id"] for t in active_tasks if t.get("parcel_id")})
        region_by_parcel: Dict[str, str] = {}
        if parcel_ids:
            parcels = await db.parcels.find({"id": {"$in": parcel_ids}}, {"_id": 0, "id": 1, "region_id": 1}).to_list(2000)
            region_by_parcel = {p["id"]: p.get("region_id") for p in parcels}
        regional_density: Dict[str, int] = {}
        for t in active_tasks:
            region = region_by_parcel.get(t.get("parcel_id")) or "bilinmeyen"
            regional_density[region] = regional_density.get(region, 0) + 1

        # Ortalama Tamamlanma Süresi — SADECE kapandi (terminal-başarılı) görevler.
        durations = []
        for t in tasks:
            if t.get("status") != "kapandi":
                continue
            try:
                start = datetime.fromisoformat(t["created_at"])
                end = datetime.fromisoformat(t["status_updated_at"])
                durations.append((end - start).total_seconds() / 3600)
            except (KeyError, ValueError):
                continue
        avg_completion_hours = round(sum(durations) / len(durations), 1) if durations else None

        return {
            "active_work_orders": active_work_orders,
            "active_tasks": len(active_tasks),
            "overdue_tasks": overdue_tasks,
            "today_visits": today_visits,
            "staff_utilization": staff_utilization,
            "regional_density": regional_density,
            "avg_completion_hours": avg_completion_hours,
        }
