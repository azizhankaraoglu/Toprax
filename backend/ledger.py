"""
=====================================================================
TabSIS — Financial Ledger + Cari Hesap Modülü (IT-19 / FAZ 7 — UFYD)
=====================================================================
UFYD omurgasının ikinci halkası (IT-18'in devamı):

    Destek Talebi → Onay → Teslim → Çiftçi Onayı → **Cari Hareket** →
    Hasat → Kalite → Hakediş → Mahsup → Ödeme → Kapanış

Tüm LedgerEntry kayıtları **ProductionCycle bazlıdır**, Parcel'e değil
(IT-05'ten beri süregelen omurga kuralı — IT-18/support.py ile aynı).

**KRİTİK KURAL — IMMUTABLE LEDGER:** Hiçbir LedgerEntry fiziksel olarak
silinmez/güncellenmez. Bu yüzden bu modülde bilinçli olarak PUT/DELETE
`/ledger/{id}` endpoint'i YOKTUR — sadece `POST /ledger` (yeni kayıt) ve
`POST /ledger/{id}/reverse` (ters kayıt: orijinali BOZMADAN, işareti ters
çevrilmiş yeni bir kayıt ekler + `is_reversal`/`reversed_entry_id` ile
orijinale referans verir). Düzeltme her zaman YENİ bir kayıttır.

**`create_ledger_entry()` — diğer modüller için doğrudan import edilebilir
yardımcı fonksiyon** (log_audit'in kullanıldığı desenle aynı): IT-18'in
support.py'si, bir SupportRequest "muhasebelesti" durumuna geçtiğinde
(omurga akışındaki "Cari Hareket" adımı) bunu doğrudan çağırıp otomatik
bir "destek_teslimi" kaydı açar — HTTP round-trip'i olmadan, aynı
doğrulama/whitelist mantığından geçerek. IT-20'nin Hakediş Motoru da
aynı şekilde bu fonksiyonu çağırarak hakediş/mahsup/prim/kesinti
kayıtlarını yazacak (henüz bu iterasyonun kapsamı değil).

**`db.finance` ile KARIŞTIRMA:** Sprint 1-4d'den kalma, farmer_id bazlı
(ProductionCycle'a bağlı OLMAYAN), sadece seed_data'da statik üretilen,
Dashboard/FarmerHome bakiye özetinde salt-okunur kullanılan ESKİ bir
demo koleksiyonu — bu iterasyon onu MİGRATE ETMEZ/dokunmaz (kantar_records'ın
IT-05'te bilinçli kapsam dışı bırakılmasıyla AYNI karar: yanlış bir
geriye-dönük eşleştirme yapmaktansa hiç yapılmamış, iki ayrı veri kaynağı
olarak bırakılmıştır). Yeni gerçek UFYD Ledger'ı `db.ledger_entries`'tir.
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List

ENTRY_TYPES = [
    "destek_talebi", "destek_teslimi", "avans", "cari_hareket",
    "hakedis", "mahsup", "prim", "kesinti", "odeme", "iade",
]

ENTRY_TYPE_LABELS = {
    "destek_talebi": "Destek Talebi", "destek_teslimi": "Destek Teslimi", "avans": "Avans",
    "cari_hareket": "Cari Hareket", "hakedis": "Hakediş", "mahsup": "Mahsup", "prim": "Prim",
    "kesinti": "Kesinti", "odeme": "Ödeme", "iade": "İade",
}


class LedgerEntryCreate(BaseModel):
    production_cycle_id: str
    farmer_id: Optional[str] = None
    entry_type: str
    amount: float
    currency: str = "TRY"
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    description: Optional[str] = None


class LedgerReverseRequest(BaseModel):
    reason: Optional[str] = None


async def create_ledger_entry(
    db, *, production_cycle_id: str, farmer_id: Optional[str], entry_type: str, amount: float,
    currency: str = "TRY", reference_type: Optional[str] = None, reference_id: Optional[str] = None,
    description: Optional[str] = None, created_by: str = "system",
    is_reversal: bool = False, reversed_entry_id: Optional[str] = None,
) -> dict:
    """Diğer modüllerin (support.py, ileride IT-20) doğrudan import edip çağırdığı
    tek giriş noktası — `POST /ledger` da bunu sarmalar, whitelist/kayıt şekli
    HER ZAMAN buradan geçer (kod tekrarı yok)."""
    if entry_type not in ENTRY_TYPES:
        raise HTTPException(400, f"Geçersiz entry_type: {entry_type} (izin verilenler: {', '.join(ENTRY_TYPES)})")
    doc = {
        "id": str(uuid.uuid4()),
        "production_cycle_id": production_cycle_id,
        "farmer_id": farmer_id,
        "entry_type": entry_type,
        "amount": amount,
        "currency": currency,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "description": description,
        "is_reversal": is_reversal,
        "reversed_entry_id": reversed_entry_id,
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ledger_entries.insert_one(doc)
    doc.pop("_id", None)
    return doc


def register_ledger_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/ledger")
    async def list_ledger_entries(
        production_cycle_id: Optional[str] = None,
        farmer_id: Optional[str] = None,
        entry_type: Optional[str] = None,
        user=Depends(require_permission("ledger:view")),
    ):
        filt = {}
        if production_cycle_id:
            filt["production_cycle_id"] = production_cycle_id
        if farmer_id:
            filt["farmer_id"] = farmer_id
        if entry_type:
            filt["entry_type"] = entry_type
        return await db.ledger_entries.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)

    @api_router.get("/ledger/{entry_id}")
    async def get_ledger_entry(entry_id: str, user=Depends(require_permission("ledger:view"))):
        doc = await db.ledger_entries.find_one({"id": entry_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Ledger kaydı bulunamadı")
        return doc

    @api_router.post("/ledger")
    async def post_ledger_entry(
        body: LedgerEntryCreate, request: Request, user=Depends(require_permission("ledger:create")),
    ):
        cycle = await db.production_cycles.find_one({"id": body.production_cycle_id}, {"_id": 0})
        if not cycle:
            raise HTTPException(404, "Üretim sezonu bulunamadı")
        farmer_id = body.farmer_id or cycle["farmer_id"]
        if farmer_id != cycle["farmer_id"]:
            raise HTTPException(400, "farmer_id bu üretim sezonuna ait değil")

        doc = await create_ledger_entry(
            db, production_cycle_id=body.production_cycle_id, farmer_id=farmer_id,
            entry_type=body.entry_type, amount=body.amount, currency=body.currency,
            reference_type=body.reference_type, reference_id=body.reference_id,
            description=body.description, created_by=user.get("full_name") or user.get("email"),
        )
        await log_audit(db, user, action="create", entity="ledger_entry", entity_id=doc["id"],
                         new_value=doc, request=request)
        return doc

    @api_router.post("/ledger/{entry_id}/reverse")
    async def reverse_ledger_entry(
        entry_id: str, body: LedgerReverseRequest, request: Request,
        user=Depends(require_permission("ledger:reverse")),
    ):
        """Orijinal kayıt HİÇ değiştirilmez/silinmez — ters işaretli YENİ bir kayıt eklenir."""
        original = await db.ledger_entries.find_one({"id": entry_id}, {"_id": 0})
        if not original:
            raise HTTPException(404, "Ledger kaydı bulunamadı")
        already = await db.ledger_entries.find_one({"reversed_entry_id": entry_id}, {"_id": 0})
        if already:
            raise HTTPException(409, "Bu kayıt zaten ters kayıtla düzeltilmiş")

        desc = f"Ters kayıt: {original.get('description') or ENTRY_TYPE_LABELS.get(original['entry_type'], original['entry_type'])}"
        if body.reason:
            desc += f" — {body.reason}"

        reversal = await create_ledger_entry(
            db, production_cycle_id=original["production_cycle_id"], farmer_id=original.get("farmer_id"),
            entry_type=original["entry_type"], amount=-original["amount"], currency=original.get("currency", "TRY"),
            reference_type=original.get("reference_type"), reference_id=original.get("reference_id"),
            description=desc, created_by=user.get("full_name") or user.get("email"),
            is_reversal=True, reversed_entry_id=entry_id,
        )
        await log_audit(db, user, action="reverse", entity="ledger_entry", entity_id=reversal["id"],
                         old_value={"reversed_entry_id": entry_id}, new_value=reversal, request=request)
        return reversal

    @api_router.get("/production-cycles/{cycle_id}/current-account")
    async def get_current_account(cycle_id: str, user=Depends(require_permission("ledger:view"))):
        cycle = await db.production_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not cycle:
            raise HTTPException(404, "Üretim sezonu bulunamadı")
        entries = await db.ledger_entries.find(
            {"production_cycle_id": cycle_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(1000)

        by_type = {}
        for e in entries:
            by_type[e["entry_type"]] = by_type.get(e["entry_type"], 0) + e["amount"]
        balance = sum(e["amount"] for e in entries)

        return {
            "production_cycle_id": cycle_id,
            "farmer_id": cycle["farmer_id"],
            "balance": balance,
            "by_type": by_type,
            "entries": entries,
        }
