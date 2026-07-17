"""
=====================================================================
Toprax — Hakediş Motoru (IT-20 / FAZ 7 — UFYD)
=====================================================================
UFYD omurgasının üçüncü halkası:

    ... → Cari Hareket → Hasat → Kalite → **Hakediş** → **Mahsup** →
    Ödeme → Kapanış

Girdiler:
- **Tartım/Tonaj/Kalite** — `kantar_records`'tan (IT-20 ile bu koleksiyona
  opsiyonel `production_cycle_id` eklendi; CLAUDE.md'nin IT-05 notunda
  öngörülen "ileride kantar kaydı bir sezon bağlamından oluşturulursa
  elle set edilebilir" anı budur — geriye dönük uyumlu, eski `parcel_id`
  bazlı kayıtlar bozulmaz, sadece yeni alan eklendi).
- **Kota** — `contracts.kota_ton` (o production_cycle_id'ye bağlı tüm
  sözleşmelerin toplamı).
- **Birim fiyat** — ROADMAP'te ayrı bir alan olarak listelenmiş
  (Contract/kantar'da YOK); bilinçli olarak calculate/finalize
  isteğinin bir PARAMETRESİ (fabrika/kooperatif fiyatı genelde
  sözleşme imzalandıktan aylar sonra, sezon geneli açıklanır — kontrata
  gömülü sabit bir alan olsaydı her fiyat güncellemesinde tüm
  sözleşmeleri elle güncellemek gerekirdi). Kullanılan değer finalize
  sonucunda kalıcı olarak saklanır (`entitlements.unit_price`).

**Hesap zinciri (ROADMAP'teki sırayla BİREBİR):**
    Brüt Hakediş → Toplam Kesinti (mahsup+kesintiler) → Net Hakediş →
    (Primler eklenir) → Ödenecek Tutar
`calculate_gross_entitlement()` ve `calculate_entitlement_chain()` SAF
fonksiyonlardır (DB/HTTP'den bağımsız) — bkz. `tests/test_entitlement.py`.

**Ledger entegrasyonu (IT-19 üzerine):** finalize'da YENİ yazılan
kayıtlar: `hakedis` (+brüt), her uygulanan kesinti tanımı için `kesinti`
(-tutar), her uygulanan prim tanımı için `prim` (+tutar). **`mahsup`
kaydı BİLİNÇLİ OLARAK 0 TUTARLI (audit/bilgi amaçlı)** — bu sezonun
destek borcu (IT-18/19'un otomatik yazdığı `destek_teslimi` negatif
kayıtları) zaten Ledger bakiyesine dahil (basit toplama ile net
otomatik çıkıyor); ايrı bir "mahsup" kaydına gerçek (negatif) tutar
yazmak bu borcu İKİNCİ KEZ düşürüp bakiyeyi bozardı (double-counting).
`mahsup` kaydı sadece "bu hakediş hangi destek borcunu mahsup etti"
bilgisini `description`/`reference_id` ile iz bırakır, bakiyeye 0 katkı
yapar — bilinçli, riskli bir varsayımın yerine güvenli taraf seçildi.

**Kabul kriteri — idempotency:** `entitlements` koleksiyonunda bir
production_cycle_id için kayıt varsa `finalize` 409 döner (aynı sezon
iki kez sonuçlandırılamaz). Düzeltme gerekirse ilgili LedgerEntry'ler
tek tek `/ledger/{id}/reverse` ile düzeltilir (IT-19), entitlement
kaydının kendisi güncellenmez/silinmez (immutable ledger felsefesiyle
tutarlı).

**Kapsam notu:** ROADMAP'in IT-20 bölümünde (IT-18'in aksine) ayrı bir
"UI:" maddesi YOK — IT-05→IT-06 emsaliyle tutarlı, bu iterasyon BİLİNÇLİ
OLARAK sadece backend'dir; İcmal/Mutabakat belgesi + UFYD Dashboard
(IT-21) bu motoru tüketen asıl UI katmanı olacak.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict

from ledger import create_ledger_entry
from event_bus import publish

# Kantar kalite notu -> katsayı. v1'de sabit (admin tarafından yönetilmiyor) —
# ileride Prim/Kesinti tanımları gibi yönetilebilir hale getirilebilir.
QUALITY_COEFFICIENTS = {"A": 1.05, "B": 1.0, "C": 0.9}

DEFAULT_DEFINITIONS = [
    {"name": "Kalite Primi", "kind": "prim"},
    {"name": "Erken Teslim Primi", "kind": "prim"},
    {"name": "Kota Primi", "kind": "prim"},
    {"name": "Ceza", "kind": "kesinti"},
    {"name": "Fire", "kind": "kesinti"},
    {"name": "Hizmet Kesintileri", "kind": "kesinti"},
    {"name": "Diğer Kesintiler", "kind": "kesinti"},
]

CALCULATION_TYPES = ["sabit_tutar", "yuzde", "formul"]


# =====================================================================
# SAF FONKSİYONLAR (DB/HTTP'DEN BAĞIMSIZ — unit test edilebilir)
# =====================================================================
def calculate_gross_entitlement(
    net_tonnage_by_quality: Dict[str, float], kota_ton: Optional[float], unit_price: float,
) -> dict:
    """tonnage_within_quota * unit_price * kalite_katsayısı (tonaj-ağırlıklı ortalama)."""
    total_tonnage = sum(net_tonnage_by_quality.values())
    tonnage_within_quota = min(total_tonnage, kota_ton) if kota_ton else total_tonnage
    if total_tonnage > 0:
        quality_coefficient = sum(
            QUALITY_COEFFICIENTS.get(q, 1.0) * t for q, t in net_tonnage_by_quality.items()
        ) / total_tonnage
    else:
        quality_coefficient = 1.0
    gross = round(tonnage_within_quota * unit_price * quality_coefficient, 2)
    return {
        "total_tonnage": round(total_tonnage, 2),
        "tonnage_within_quota": round(tonnage_within_quota, 2),
        "quality_coefficient": round(quality_coefficient, 4),
        "gross_entitlement": gross,
    }


def resolve_definition_amount(definition: dict, gross_entitlement: float, override_amount: Optional[float]) -> float:
    """Bir Prim/Kesinti tanımının BU hesaplama için tutarını çözer.
    "formul" tipi HER ZAMAN override_amount ister (gerçek bir formül motoru
    bu iterasyonun kapsamı dışı — bilinçli sadeleştirme)."""
    if definition["calculation_type"] == "formul":
        if override_amount is None:
            raise ValueError(f"'{definition['name']}' formül tipi manuel tutar (override_amount) gerektirir")
        return round(override_amount, 2)
    if override_amount is not None:
        return round(override_amount, 2)
    if definition["calculation_type"] == "sabit_tutar":
        return round(definition["value"], 2)
    if definition["calculation_type"] == "yuzde":
        return round(gross_entitlement * definition["value"] / 100, 2)
    raise ValueError(f"Bilinmeyen hesaplama tipi: {definition['calculation_type']}")


def calculate_entitlement_chain(
    gross_entitlement: float, destek_mahsup_total: float, kesintiler: List[dict], primler: List[dict],
) -> dict:
    """Brüt Hakediş → Toplam Kesinti (mahsup+kesintiler) → Net Hakediş → (+Primler) → Ödenecek Tutar."""
    total_kesinti = round(sum(k["amount"] for k in kesintiler), 2)
    total_deduction = round(destek_mahsup_total + total_kesinti, 2)
    net_entitlement = round(gross_entitlement - total_deduction, 2)
    total_prim = round(sum(p["amount"] for p in primler), 2)
    payable_amount = round(net_entitlement + total_prim, 2)
    return {
        "destek_mahsup_total": round(destek_mahsup_total, 2),
        "kesintiler": kesintiler,
        "total_kesinti": total_kesinti,
        "total_deduction": total_deduction,
        "net_entitlement": net_entitlement,
        "primler": primler,
        "total_prim": total_prim,
        "payable_amount": payable_amount,
    }


class DefinitionCreate(BaseModel):
    name: str
    kind: str  # "prim" | "kesinti"
    calculation_type: str  # "sabit_tutar" | "yuzde" | "formul"
    value: float = 0
    condition: Optional[str] = None


class DefinitionUpdate(BaseModel):
    name: Optional[str] = None
    calculation_type: Optional[str] = None
    value: Optional[float] = None
    condition: Optional[str] = None
    is_active: Optional[bool] = None


class AppliedItem(BaseModel):
    definition_id: str
    override_amount: Optional[float] = None


class EntitlementRequest(BaseModel):
    production_cycle_id: str
    unit_price: float
    applied_items: List[AppliedItem] = []


# =====================================================================
# HESAPLAMA ÇEKİRDEĞİ (DB'den girdi toplar, saf fonksiyonları çağırır)
# =====================================================================
# Modül seviyesinde (register_entitlement_routes closure'ı İÇİNDE DEĞİL) —
# IT-21'in simulation.py'si (bkz. reconciliation.py) bunu DOĞRUDAN import
# edip override parametreleriyle çağırır (query_engine.py'nin execute_query()'i
# extras.py'ye açmasıyla AYNI desen, IT-10).
async def gather_and_compute_entitlement(
    db, body: "EntitlementRequest",
    tonnage_override: Optional[Dict[str, float]] = None,
    kota_override: Optional[float] = None,
    destek_mahsup_override: Optional[float] = None,
) -> dict:
    """override parametreleri SADECE simülasyon (IT-21) tarafından kullanılır —
    gerçek calculate/finalize akışı bunları hiç geçirmez (None kalır, gerçek
    DB verisi kullanılır)."""
    cycle = await db.production_cycles.find_one({"id": body.production_cycle_id}, {"_id": 0})
    if not cycle:
        raise HTTPException(404, "Üretim sezonu bulunamadı")

    if tonnage_override is not None:
        net_tonnage_by_quality: Dict[str, float] = dict(tonnage_override)
    else:
        kantar_records = await db.kantar_records.find(
            {"production_cycle_id": body.production_cycle_id, "is_active": {"$ne": False}}, {"_id": 0}
        ).to_list(500)
        net_tonnage_by_quality = {}
        for k in kantar_records:
            q = k.get("kalite", "B")
            net_tonnage_by_quality[q] = net_tonnage_by_quality.get(q, 0) + k.get("net_ton", 0)

    if kota_override is not None:
        kota_ton = kota_override
    else:
        contracts = await db.contracts.find(
            {"production_cycle_id": body.production_cycle_id}, {"_id": 0}
        ).to_list(50)
        kota_ton = sum(c.get("kota_ton", 0) for c in contracts) or None

    gross = calculate_gross_entitlement(net_tonnage_by_quality, kota_ton, body.unit_price)

    if destek_mahsup_override is not None:
        destek_mahsup_total = destek_mahsup_override
    else:
        # Mahsup — bu sezona ait, IT-18/19'un OTOMATİK yazdığı destek_teslimi
        # kayıtları (zaten negatif) — bilgi amaçlı toplanır, YENİDEN yazılmaz.
        destek_entries = await db.ledger_entries.find(
            {"production_cycle_id": body.production_cycle_id, "entry_type": "destek_teslimi"}, {"_id": 0}
        ).to_list(500)
        destek_mahsup_total = -sum(e["amount"] for e in destek_entries)  # negatifi pozitife çevir

    applied_by_id = {a.definition_id: a.override_amount for a in body.applied_items}
    definitions = []
    if applied_by_id:
        definitions = await db.entitlement_definitions.find(
            {"id": {"$in": list(applied_by_id.keys())}}, {"_id": 0}
        ).to_list(200)
    found_ids = {d["id"] for d in definitions}
    missing = set(applied_by_id.keys()) - found_ids
    if missing:
        raise HTTPException(404, f"Tanım(lar) bulunamadı: {', '.join(missing)}")

    kesintiler, primler = [], []
    for d in definitions:
        try:
            amount = resolve_definition_amount(d, gross["gross_entitlement"], applied_by_id[d["id"]])
        except ValueError as e:
            raise HTTPException(400, str(e))
        item = {"definition_id": d["id"], "name": d["name"], "amount": amount}
        (kesintiler if d["kind"] == "kesinti" else primler).append(item)

    chain = calculate_entitlement_chain(gross["gross_entitlement"], destek_mahsup_total, kesintiler, primler)

    return {
        "production_cycle_id": body.production_cycle_id,
        "farmer_id": cycle["farmer_id"],
        "unit_price": body.unit_price,
        "net_tonnage_by_quality": net_tonnage_by_quality,
        "kota_ton": kota_ton,
        **gross,
        **chain,
    }


def register_entitlement_routes(api_router, db, current_user, require_permission, log_audit):

    # =================================================================
    # PRİM / KESİNTİ TANIMLARI (yönetilebilir katalog — SupportType ile AYNI desen)
    # =================================================================
    @api_router.get("/entitlement/definitions")
    async def list_definitions(
        kind: Optional[str] = None, include_inactive: bool = False,
        user=Depends(require_permission("entitlement:view")),
    ):
        filt = {} if include_inactive else {"is_active": True}
        if kind:
            filt["kind"] = kind
        return await db.entitlement_definitions.find(filt, {"_id": 0}).sort("name", 1).to_list(200)

    @api_router.post("/entitlement/definitions")
    async def create_definition(
        body: DefinitionCreate, request: Request, user=Depends(require_permission("entitlement:definitions_manage")),
    ):
        if body.kind not in ("prim", "kesinti"):
            raise HTTPException(400, "kind 'prim' veya 'kesinti' olmalı")
        if body.calculation_type not in CALCULATION_TYPES:
            raise HTTPException(400, f"calculation_type: {', '.join(CALCULATION_TYPES)}")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.entitlement_definitions.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="entitlement_definition", entity_id=doc["id"],
                         new_value=doc, request=request)
        return doc

    @api_router.put("/entitlement/definitions/{def_id}")
    async def update_definition(
        def_id: str, body: DefinitionUpdate, request: Request,
        user=Depends(require_permission("entitlement:definitions_manage")),
    ):
        old = await db.entitlement_definitions.find_one({"id": def_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Tanım bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if body.calculation_type and body.calculation_type not in CALCULATION_TYPES:
            raise HTTPException(400, f"calculation_type: {', '.join(CALCULATION_TYPES)}")
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.entitlement_definitions.update_one({"id": def_id}, {"$set": updates})
        new = await db.entitlement_definitions.find_one({"id": def_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="entitlement_definition", entity_id=def_id,
                         old_value=old, new_value=new, request=request)
        return new

    @api_router.post("/entitlement/definitions/seed-defaults")
    async def seed_default_definitions(
        request: Request, user=Depends(require_permission("entitlement:definitions_manage")),
    ):
        created = []
        for d in DEFAULT_DEFINITIONS:
            existing = await db.entitlement_definitions.find_one({"name": d["name"]}, {"_id": 0})
            if existing:
                continue
            doc = {
                "id": str(uuid.uuid4()), "name": d["name"], "kind": d["kind"],
                "calculation_type": "sabit_tutar", "value": 0, "condition": None,
                "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.entitlement_definitions.insert_one(doc)
            created.append(d["name"])
        if created:
            await log_audit(db, user, action="seed", entity="entitlement_definition", entity_id="bulk",
                             new_value={"created": created}, request=request)
        return {"status": "ok", "created": created}

    @api_router.post("/entitlement/calculate")
    async def calculate_entitlement(
        body: EntitlementRequest, user=Depends(require_permission("entitlement:calculate")),
    ):
        """Dry-run — hiçbir şey yazmaz, sadece önizleme döner."""
        return await gather_and_compute_entitlement(db, body)

    @api_router.post("/entitlement/{production_cycle_id}/finalize")
    async def finalize_entitlement(
        production_cycle_id: str, body: EntitlementRequest, request: Request,
        user=Depends(require_permission("entitlement:finalize")),
    ):
        if body.production_cycle_id != production_cycle_id:
            raise HTTPException(400, "URL ve body'deki production_cycle_id eşleşmiyor")

        existing = await db.entitlements.find_one({"production_cycle_id": production_cycle_id}, {"_id": 0})
        if existing:
            raise HTTPException(409, "Bu üretim sezonu için hakediş zaten sonuçlandırılmış (idempotency)")

        result = await gather_and_compute_entitlement(db, body)
        created_by = user.get("full_name") or user.get("email")
        entitlement_id = str(uuid.uuid4())  # önceden üretilir — ledger kayıtları buna referans verir

        hakedis_entry = await create_ledger_entry(
            db, production_cycle_id=production_cycle_id, farmer_id=result["farmer_id"],
            entry_type="hakedis", amount=result["gross_entitlement"], currency="TRY",
            reference_type="entitlement", reference_id=entitlement_id,
            description=f"Brüt hakediş — {result['tonnage_within_quota']} ton x {body.unit_price} TL "
                        f"(kalite katsayısı {result['quality_coefficient']})",
            created_by=created_by,
        )

        kesinti_entry_ids, prim_entry_ids = [], []
        for k in result["kesintiler"]:
            e = await create_ledger_entry(
                db, production_cycle_id=production_cycle_id, farmer_id=result["farmer_id"],
                entry_type="kesinti", amount=-k["amount"], currency="TRY",
                reference_type="entitlement_definition", reference_id=k["definition_id"],
                description=k["name"], created_by=created_by,
            )
            kesinti_entry_ids.append(e["id"])
        for p in result["primler"]:
            e = await create_ledger_entry(
                db, production_cycle_id=production_cycle_id, farmer_id=result["farmer_id"],
                entry_type="prim", amount=p["amount"], currency="TRY",
                reference_type="entitlement_definition", reference_id=p["definition_id"],
                description=p["name"], created_by=created_by,
            )
            prim_entry_ids.append(e["id"])

        # Mahsup — BİLİNÇLİ OLARAK 0 tutarlı (bkz. modül docstring'i):
        # destek borcu zaten `destek_teslimi` ile Ledger'da; burada tekrar
        # negatif yazmak bakiyeyi ikinci kez düşürürdü. Sadece iz bırakır.
        mahsup_entry = await create_ledger_entry(
            db, production_cycle_id=production_cycle_id, farmer_id=result["farmer_id"],
            entry_type="mahsup", amount=0, currency="TRY",
            reference_type="entitlement", reference_id=entitlement_id,
            description=f"Bu hakedişte mahsup edilen destek borcu: {result['destek_mahsup_total']} TL "
                        f"(zaten destek_teslimi kayıtlarında düşülmüştür, bu kayıt sadece bilgi amaçlıdır)",
            created_by=created_by,
        )

        entitlement_doc = {
            "id": entitlement_id,
            **result,
            "ledger_entry_ids": {
                "hakedis": hakedis_entry["id"], "mahsup": mahsup_entry["id"],
                "kesinti": kesinti_entry_ids, "prim": prim_entry_ids,
            },
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "finalized_by": created_by,
        }
        await db.entitlements.insert_one(entitlement_doc)
        entitlement_doc.pop("_id", None)

        await log_audit(db, user, action="finalize", entity="entitlement", entity_id=entitlement_doc["id"],
                         new_value=entitlement_doc, request=request)

        # (IT-27) Communication Policy tetikleyicisi — "Hakediş Oluştu" örneği.
        await publish(db, "entitlement_created", {
            "farmer_id": result["farmer_id"],
            "production_cycle_id": production_cycle_id,
            "payable_amount": result["payable_amount"],
        })
        return entitlement_doc

    @api_router.get("/entitlement/{production_cycle_id}")
    async def get_entitlement(production_cycle_id: str, user=Depends(require_permission("entitlement:view"))):
        doc = await db.entitlements.find_one({"production_cycle_id": production_cycle_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Bu üretim sezonu için henüz hakediş sonuçlandırılmamış")
        return doc
