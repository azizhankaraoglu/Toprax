"""
=====================================================================
Toprax — ProductionCycle (Üretim Sezonu) Modülü (IT-05 / Sprint A2)
=====================================================================
İkinci omurga: Farmer → Parcel → ProductionCycle → (Contract/Planting/
SoilSample/...). Bir parselin belirli bir yıl+sezonundaki üretim
döngüsünü temsil eder ve bir durum makinesiyle takip edilir:

    planning → active → harvesting → completed
                  \\___________\\___________\\──→ cancelled

`cancelled` ve `completed` terminal durumlardır. Ayrı bir "sil"
endpoint'i YOKTUR — Sprint A1/convention #3 (soft delete) gereği,
bir sezonu sonlandırmak `status=cancelled` geçişiyle yapılır.

`season` alanı bir yıl içinde birden fazla üretim döngüsü olabileceği
(ör. "Ana Ürün" / "İkinci Ürün") ihtimaline karşı serbest metin bir
etiket olarak tasarlandı; tek-sezonluk ürünlerde (şeker pancarı gibi)
varsayılan "Ana Ürün" yeterlidir.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

DEFAULT_SEASON_LABEL = "Ana Ürün"


async def ensure_cycle_for(db, parcel_id: str, year: int, farmer_id: str) -> str:
    """(parcel_id, year, DEFAULT_SEASON_LABEL) için ProductionCycle bulur/oluşturur
    — idempotent. IT-05: alt kayıtlar (sözleşme/toprak/ekim) oluşturulurken
    production_cycle_id verilmediyse, çağıran modül (data_entry.py) bunu çağırıp
    o parselin ilgili yıl/varsayılan sezonunu otomatik bağlar. Böylece hiçbir
    üretim kaydı ProductionCycle'sız (orphan) kalmaz, ama eski `parcel_id`
    KORUNUR (backward-compatible — mevcut mobil/portal akışları bozulmaz).
    Modül seviyesindedir ki `register_*_routes` closure'ı DIŞINDAN import
    edilebilsin (migration + data_entry AYNI tek yardımcıyı kullanır)."""
    cycle = await db.production_cycles.find_one(
        {"parcel_id": parcel_id, "year": year, "season": DEFAULT_SEASON_LABEL}, {"_id": 0}
    )
    if cycle:
        return cycle["id"]
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()), "farmer_id": farmer_id, "parcel_id": parcel_id,
        "year": year, "season": DEFAULT_SEASON_LABEL, "crop": "Şeker Pancarı",
        "status": "completed" if year < datetime.now().year else "active",
        "status_updated_at": now,
        "notes": "Alt kayıt oluşturulurken otomatik bağlandı (IT-05)",
        "created_at": now, "created_by": "auto (IT-05)",
    }
    await db.production_cycles.insert_one(doc)
    return doc["id"]


STATUS_LABELS = {
    "planning": "Planlama",
    "active": "Aktif",
    "harvesting": "Hasat",
    "completed": "Tamamlandı",
    "cancelled": "İptal",
}

# İzin verilen geçişler: sıradaki durum VEYA (terminal olmayan durumdan) iptal.
ALLOWED_TRANSITIONS = {
    "planning": {"active", "cancelled"},
    "active": {"harvesting", "cancelled"},
    "harvesting": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class ProductionCycleCreate(BaseModel):
    farmer_id: str
    parcel_id: str
    year: int
    season: str = DEFAULT_SEASON_LABEL
    crop: str = "Şeker Pancarı"
    notes: Optional[str] = None


class ProductionCycleUpdate(BaseModel):
    season: Optional[str] = None
    crop: Optional[str] = None
    notes: Optional[str] = None


class ProductionCycleStatusUpdate(BaseModel):
    status: str


def register_production_cycle_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    # God Mode Modül Yönetimi — "production" flag'i kapatılınca liste GERÇEKTEN 403 döner.
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/production-cycles")
    async def list_production_cycles(
        farmer_id: Optional[str] = None,
        parcel_id: Optional[str] = None,
        year: Optional[int] = None,
        status: Optional[str] = None,
        user=Depends(require_permission("production_cycles:view")),
        _feat=Depends(require_feature("production")),
    ):
        filt = {}
        if farmer_id:
            filt["farmer_id"] = farmer_id
        if parcel_id:
            filt["parcel_id"] = parcel_id
        if year:
            filt["year"] = year
        if status:
            filt["status"] = status
        return await db.production_cycles.find(filt, {"_id": 0}).sort("year", -1).to_list(1000)

    @api_router.get("/production-cycles/{cycle_id}")
    async def get_production_cycle(cycle_id: str, user=Depends(require_permission("production_cycles:view"))):
        """
        Sezon detayı: kendisi + sahibi çiftçi/parsel (ParcelDetail'in `GET
        /parcels/{id}` kalıbıyla tutarlı — ilişkili çekirdek varlıklar
        gömülü döner) + bu sezona bağlı sözleşme/ekim/toprak kayıtları.
        """
        cycle = await db.production_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not cycle:
            raise HTTPException(404, "Üretim sezonu bulunamadı")
        farmer = await db.farmers.find_one({"id": cycle["farmer_id"]}, {"_id": 0})
        parcel = await db.parcels.find_one({"id": cycle["parcel_id"]}, {"_id": 0})
        contracts = await db.contracts.find({"production_cycle_id": cycle_id}, {"_id": 0}).to_list(50)
        plantings = await db.plantings.find({"production_cycle_id": cycle_id}, {"_id": 0}).to_list(50)
        soil_samples = await db.soil_samples.find({"production_cycle_id": cycle_id}, {"_id": 0}).to_list(50)
        return {
            "cycle": cycle,
            "farmer": farmer,
            "parcel": parcel,
            "contracts": contracts,
            "plantings": plantings,
            "soil_samples": soil_samples,
        }

    @api_router.post("/production-cycles")
    async def create_production_cycle(
        body: ProductionCycleCreate, request: Request,
        user=Depends(require_permission("production_cycles:create")),
    ):
        farmer = await db.farmers.find_one({"id": body.farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        if parcel["farmer_id"] != body.farmer_id:
            raise HTTPException(400, "Parsel bu çiftçiye ait değil")

        existing = await db.production_cycles.find_one(
            {"parcel_id": body.parcel_id, "year": body.year, "season": body.season,
             "status": {"$ne": "cancelled"}},
            {"_id": 0},
        )
        if existing:
            raise HTTPException(409, f"Bu parsel için {body.year} / {body.season} zaten mevcut (iptal edilmemiş)")

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["status"] = "planning"
        doc["status_updated_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_at"] = doc["status_updated_at"]
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.production_cycles.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="production_cycle", entity_id=doc["id"],
                         new_value=doc, request=request)
        return doc

    @api_router.put("/production-cycles/{cycle_id}")
    async def update_production_cycle(
        cycle_id: str, body: ProductionCycleUpdate, request: Request,
        user=Depends(require_permission("production_cycles:edit")),
    ):
        old = await db.production_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Üretim sezonu bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.production_cycles.update_one({"id": cycle_id}, {"$set": updates})
        new = await db.production_cycles.find_one({"id": cycle_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="production_cycle", entity_id=cycle_id,
                         old_value=old, new_value=new, request=request)
        return new

    @api_router.put("/production-cycles/{cycle_id}/status")
    async def update_production_cycle_status(
        cycle_id: str, body: ProductionCycleStatusUpdate, request: Request,
        user=Depends(require_permission("production_cycles:edit")),
    ):
        old = await db.production_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Üretim sezonu bulunamadı")
        if body.status not in ALLOWED_TRANSITIONS:
            raise HTTPException(400, f"Geçersiz durum: {body.status}")
        current = old["status"]
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if body.status not in allowed:
            raise HTTPException(
                400,
                f"'{STATUS_LABELS.get(current, current)}' durumundan "
                f"'{STATUS_LABELS.get(body.status, body.status)}' durumuna geçilemez"
                + (f" (izin verilenler: {', '.join(STATUS_LABELS[s] for s in allowed)})" if allowed else " (bu durum terminaldir)"),
            )
        updates = {"status": body.status, "status_updated_at": datetime.now(timezone.utc).isoformat()}
        await db.production_cycles.update_one({"id": cycle_id}, {"$set": updates})
        new = await db.production_cycles.find_one({"id": cycle_id}, {"_id": 0})
        await log_audit(db, user, action="status_change", entity="production_cycle", entity_id=cycle_id,
                         old_value={"status": current}, new_value={"status": body.status}, request=request)
        return new

    # =================================================================
    # MİGRASYON — mevcut kayıtları sezona bağlar (IT-05)
    # =================================================================
    async def _ensure_cycle_for(parcel_id: str, year: int, farmer_id: str) -> str:
        """(parcel_id, year, DEFAULT_SEASON_LABEL) için ProductionCycle bulur/oluşturur — idempotent."""
        cycle = await db.production_cycles.find_one(
            {"parcel_id": parcel_id, "year": year, "season": DEFAULT_SEASON_LABEL}, {"_id": 0}
        )
        if cycle:
            return cycle["id"]
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()), "farmer_id": farmer_id, "parcel_id": parcel_id,
            "year": year, "season": DEFAULT_SEASON_LABEL, "crop": "Şeker Pancarı",
            "status": "completed" if year < datetime.now().year else "active",
            "status_updated_at": now,
            "notes": "Migrasyon ile otomatik oluşturuldu (IT-05)",
            "created_at": now, "created_by": "migration (IT-05)",
        }
        await db.production_cycles.insert_one(doc)
        return doc["id"]

    @api_router.post("/production-cycles/migrate-existing")
    async def migrate_existing_records(
        request: Request, user=Depends(require_permission("production_cycles:create")),
    ):
        """
        Idempotent migrasyon: `production_cycle_id` alanı HENÜZ olmayan
        contracts/plantings/soil_samples kayıtlarını (parcel_id + yıl'a
        göre) uygun bir ProductionCycle'a bağlar — yoksa otomatik
        oluşturur. Eski `parcel_id` alanı KORUNUR, sadece yeni
        `production_cycle_id` eklenir (geriye dönük uyumlu).

        Kantar kayıtları (`kantar_records`) BİLİNÇLİ OLARAK KAPSAM
        DIŞI: bu kayıtlar `farmer_id` bazlıdır, `parcel_id` taşımaz —
        bir çiftçinin aynı yıl birden fazla parseli/sezonu olabileceği
        için hangi ProductionCycle'a ait olduğu kayıttan çıkarılamaz.
        Yanlış bir eşleştirme yapmaktansa hiç yapmamak tercih edildi
        (bkz. CLAUDE.md Bilinen Tuzaklar).
        """
        stats = {"contracts": 0, "plantings": 0, "soil_samples": 0, "cycles_created": 0}
        before_cycles = await db.production_cycles.count_documents({})

        async for c in db.contracts.find({"production_cycle_id": {"$exists": False}}, {"_id": 0}):
            cid = await _ensure_cycle_for(c["parcel_id"], c["season"], c["farmer_id"])
            await db.contracts.update_one({"id": c["id"]}, {"$set": {"production_cycle_id": cid}})
            stats["contracts"] += 1

        async for p in db.plantings.find({"production_cycle_id": {"$exists": False}}, {"_id": 0}):
            cid = await _ensure_cycle_for(p["parcel_id"], p["season"], p["farmer_id"])
            await db.plantings.update_one({"id": p["id"]}, {"$set": {"production_cycle_id": cid}})
            stats["plantings"] += 1

        async for s in db.soil_samples.find({"production_cycle_id": {"$exists": False}}, {"_id": 0}):
            parcel = await db.parcels.find_one({"id": s.get("parcel_id")}, {"_id": 0})
            if not parcel:
                continue
            year = int(s["date"][:4]) if s.get("date") else datetime.now().year
            cid = await _ensure_cycle_for(s["parcel_id"], year, parcel["farmer_id"])
            await db.soil_samples.update_one({"id": s["id"]}, {"$set": {"production_cycle_id": cid}})
            stats["soil_samples"] += 1

        after_cycles = await db.production_cycles.count_documents({})
        stats["cycles_created"] = after_cycles - before_cycles

        await log_audit(db, user, action="migrate", entity="production_cycle", entity_id="bulk",
                         new_value=stats, request=request)
        return {"status": "migrated", "stats": stats}
