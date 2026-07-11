"""
=====================================================================
TabSIS — İcmal/Mutabakat Belgesi + Finansal Simülasyon + UFYD Dashboard
(IT-21 / FAZ 7 — UFYD, son halka)
=====================================================================
UFYD omurgasının kapanışı:

    ... → Hakediş → Mahsup → **Ödeme → Kapanış** (İcmal bu adımı belgeler)

Üç ayrı ama birbirine bağlı özellik (ROADMAP'te tek IT altında toplanmış):

1) **İcmal Belgesi** — bir ProductionCycle'ın hakedişi (IT-20) finalize
   edildikten SONRA üretilir; PDF üretimi `extras.py`'deki
   `/musthsil/{farmer_id}/{season}` ile AYNI kütüphaneyi (reportlab)
   ve AYNI kalıbı kullanır — Helvetica varsayılan font Türkçe karakter
   desteklemediği için (İ/ş/ğ/ü/ö/ç) metin BİLİNÇLİ OLARAK ASCII'ye
   yakın tutulur (müstahsil makbuzuyla TUTARLI, yeni bir font gömme
   bağımlılığı eklenmedi). Çiftçi portalından görüntülenip dijital
   onay/itiraz verilebilir — itiraz, IT-28'in Case modeline BAĞLANANA
   kadar basit bir `status`/`objection_reason` alanıdır (ROADMAP'in
   kendi notuyla tutarlı bir bilinçli sadeleştirme).

2) **Finansal Simülasyon** — `entitlement.py`'nin `gather_and_compute_
   entitlement()` fonksiyonu tam da bunun için SAF/yan-etkisiz yazılmıştı
   (IT-20): aynı fonksiyon override parametreleriyle (varsayımsal tonaj/
   kota/destek/fiyat/prim-kesinti) çağrılır, SONUÇ HİÇBİR YERE YAZILMAZ.
   Kabul kriteri "simülasyon sonucu ile gerçek hakediş birbirine
   karışmıyor (ayrı response şeması)" — bu yüzden yanıt HER ZAMAN
   `{"simulation": true, ...}` zarfı içinde döner, asla `entitlements`
   koleksiyonundaki gerçek bir kayıtla aynı şekle sahip değildir.

3) **UFYD Dashboard** — Ledger/SupportRequest/Entitlement'tan CANLI
   hesaplanır (statik/önbelleklenmiş değil) — kabul kriteri gereği.
"""
import io
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List, Dict

from entitlement import EntitlementRequest, gather_and_compute_entitlement
from permissions import get_effective_permissions

RECONCILIATION_STATUS_LABELS = {
    "beklemede": "Beklemede", "onaylandi": "Onaylandı", "itiraz_edildi": "İtiraz Edildi",
}


class ObjectionRequest(BaseModel):
    reason: str


class SimulationRequest(BaseModel):
    production_cycle_id: str
    unit_price: float
    applied_items: List[dict] = []           # [{"definition_id":..., "override_amount":...}]
    tonnage_override: Optional[Dict[str, float]] = None
    kota_override: Optional[float] = None
    destek_mahsup_override: Optional[float] = None


def _build_reconciliation_pdf(cycle: dict, farmer: dict, entitlement: dict, balance: float) -> bytes:
    """extras.py'deki müstahsil makbuzuyla AYNI kalıp: reportlab, ASCII-yakın metin."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = 800

    def line(text, size=10, bold=False, gap=15):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(50, y, text)
        y -= gap

    def hr():
        nonlocal y
        c.line(50, y, 545, y)
        y -= 15

    line("ICMAL / MUTABAKAT BELGESI", size=16, bold=True, gap=20)
    line(f"Uretim Sezonu: {cycle.get('year')} - {cycle.get('season')} ({cycle.get('crop')})")
    line(f"Belge No: IC-{cycle.get('year')}-{entitlement['id'][:8].upper()}")
    line(f"Duzenleme: {datetime.now().strftime('%d.%m.%Y')}")
    hr()

    line("CIFTCI:", bold=True, size=11)
    line(f"Ad Soyad: {farmer.get('full_name')}")
    line(f"Uye No: {farmer.get('member_no')}")
    hr()

    line("TESLIM EDILEN TONAJ VE KALITE:", bold=True, size=11)
    for kalite, tonaj in entitlement.get("net_tonnage_by_quality", {}).items():
        line(f"  Kalite {kalite}: {tonaj:.2f} ton")
    line(f"Toplam Tonaj: {entitlement.get('total_tonnage', 0):.2f} ton")
    line(f"Kota Ici Tonaj: {entitlement.get('tonnage_within_quota', 0):.2f} ton")
    line(f"Kalite Katsayisi: {entitlement.get('quality_coefficient', 1)}")
    line(f"Birim Fiyat: {entitlement.get('unit_price', 0):,.2f} TL/ton")
    hr()

    line(f"BRUT HAKEDIS: {entitlement.get('gross_entitlement', 0):,.2f} TL", bold=True, size=11)
    hr()

    line("DESTEK MAHSUBU VE KESINTILER:", bold=True, size=11)
    line(f"  Destek Mahsubu: -{entitlement.get('destek_mahsup_total', 0):,.2f} TL")
    for k in entitlement.get("kesintiler", []):
        line(f"  {k['name']}: -{k['amount']:,.2f} TL")
    line(f"Toplam Kesinti: -{entitlement.get('total_deduction', 0):,.2f} TL")
    hr()

    line(f"NET HAKEDIS: {entitlement.get('net_entitlement', 0):,.2f} TL", bold=True, size=11)
    hr()

    line("PRIMLER:", bold=True, size=11)
    if entitlement.get("primler"):
        for p in entitlement["primler"]:
            line(f"  {p['name']}: +{p['amount']:,.2f} TL")
    else:
        line("  (Uygulanan prim yok)")
    hr()

    line(f"ODENECEK TUTAR: {entitlement.get('payable_amount', 0):,.2f} TL", bold=True, size=13)
    line(f"CARI BAKIYE (sezon geneli): {balance:,.2f} TL", bold=True, size=11)

    y -= 20
    line("Bu belge dijital olarak uretilmistir. Demo amaclidir.", size=8)
    line(f"Belge ID: {uuid.uuid4().hex[:12].upper()}", size=8)

    c.save()
    buffer.seek(0)
    return buffer.read()


async def _check_reconciliation_access(db, user: dict, reconciliation: dict, require_manage: bool = False):
    if user.get("role") == "ciftci":
        if user.get("farmer_id") != reconciliation["farmer_id"]:
            raise HTTPException(403, "Bu icmal belgesi size ait değil")
        return
    perms = await get_effective_permissions(user, db)
    needed = "reconciliation:manage" if require_manage else "reconciliation:view"
    if needed not in perms:
        raise HTTPException(403, f"'{needed}' izniniz yok")


def register_reconciliation_routes(api_router, db, current_user, require_permission, log_audit):

    # =================================================================
    # İCMAL BELGESİ
    # =================================================================
    @api_router.post("/reconciliation/{production_cycle_id}")
    async def generate_reconciliation(
        production_cycle_id: str, request: Request,
        user=Depends(require_permission("reconciliation:manage")),
    ):
        """İdempotent — zaten üretilmişse mevcut kaydı döner (yeniden üretmez)."""
        existing = await db.reconciliations.find_one({"production_cycle_id": production_cycle_id}, {"_id": 0})
        if existing:
            return existing

        entitlement = await db.entitlements.find_one({"production_cycle_id": production_cycle_id}, {"_id": 0})
        if not entitlement:
            raise HTTPException(404, "Bu üretim sezonu için henüz hakediş sonuçlandırılmamış (önce finalize edin)")

        doc = {
            "id": str(uuid.uuid4()),
            "production_cycle_id": production_cycle_id,
            "farmer_id": entitlement["farmer_id"],
            "entitlement_id": entitlement["id"],
            "status": "beklemede",
            "objection_reason": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": user.get("full_name") or user.get("email"),
            "approved_at": None,
            "objected_at": None,
        }
        await db.reconciliations.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="reconciliation", entity_id=doc["id"],
                         new_value=doc, request=request)
        return doc

    @api_router.get("/reconciliation/{production_cycle_id}")
    async def get_reconciliation_by_cycle(
        production_cycle_id: str, user=Depends(require_permission("reconciliation:view")),
    ):
        doc = await db.reconciliations.find_one({"production_cycle_id": production_cycle_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Bu üretim sezonu için icmal belgesi henüz üretilmemiş")
        return doc

    @api_router.get("/reconciliation/{reconciliation_id}/pdf")
    async def get_reconciliation_pdf(reconciliation_id: str, user=Depends(current_user)):
        doc = await db.reconciliations.find_one({"id": reconciliation_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "İcmal belgesi bulunamadı")
        await _check_reconciliation_access(db, user, doc, require_manage=False)

        entitlement = await db.entitlements.find_one({"id": doc["entitlement_id"]}, {"_id": 0})
        cycle = await db.production_cycles.find_one({"id": doc["production_cycle_id"]}, {"_id": 0})
        farmer = await db.farmers.find_one({"id": doc["farmer_id"]}, {"_id": 0})
        ledger = await db.ledger_entries.find({"production_cycle_id": doc["production_cycle_id"]}, {"_id": 0}).to_list(1000)
        balance = sum(e["amount"] for e in ledger)

        pdf_bytes = _build_reconciliation_pdf(cycle, farmer, entitlement, balance)
        return Response(
            content=pdf_bytes, media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="icmal-{cycle.get("year")}-{farmer.get("member_no")}.pdf"'},
        )

    @api_router.post("/reconciliation/{reconciliation_id}/approve")
    async def approve_reconciliation(reconciliation_id: str, request: Request, user=Depends(current_user)):
        doc = await db.reconciliations.find_one({"id": reconciliation_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "İcmal belgesi bulunamadı")
        await _check_reconciliation_access(db, user, doc, require_manage=True)
        if doc["status"] != "beklemede":
            raise HTTPException(400, f"Bu belge zaten '{RECONCILIATION_STATUS_LABELS.get(doc['status'], doc['status'])}' durumunda")

        updates = {"status": "onaylandi", "approved_at": datetime.now(timezone.utc).isoformat()}
        await db.reconciliations.update_one({"id": reconciliation_id}, {"$set": updates})
        new = await db.reconciliations.find_one({"id": reconciliation_id}, {"_id": 0})
        await log_audit(db, user, action="approve", entity="reconciliation", entity_id=reconciliation_id,
                         old_value={"status": doc["status"]}, new_value=updates, request=request)
        return new

    @api_router.post("/reconciliation/{reconciliation_id}/object")
    async def object_reconciliation(
        reconciliation_id: str, body: ObjectionRequest, request: Request, user=Depends(current_user),
    ):
        """İtiraz — IT-28'in Case modeline bağlanana kadar basit bir durum/sebep alanı (ROADMAP notu)."""
        doc = await db.reconciliations.find_one({"id": reconciliation_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "İcmal belgesi bulunamadı")
        await _check_reconciliation_access(db, user, doc, require_manage=True)
        if doc["status"] != "beklemede":
            raise HTTPException(400, f"Bu belge zaten '{RECONCILIATION_STATUS_LABELS.get(doc['status'], doc['status'])}' durumunda")

        updates = {
            "status": "itiraz_edildi", "objected_at": datetime.now(timezone.utc).isoformat(),
            "objection_reason": body.reason,
        }
        await db.reconciliations.update_one({"id": reconciliation_id}, {"$set": updates})
        new = await db.reconciliations.find_one({"id": reconciliation_id}, {"_id": 0})
        await log_audit(db, user, action="object", entity="reconciliation", entity_id=reconciliation_id,
                         old_value={"status": doc["status"]}, new_value=updates, request=request)
        return new

    @api_router.get("/portal/reconciliations")
    async def portal_list_reconciliations(user=Depends(current_user)):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        return await db.reconciliations.find(
            {"farmer_id": user["farmer_id"]}, {"_id": 0}
        ).sort("generated_at", -1).to_list(200)

    # =================================================================
    # FİNANSAL SİMÜLASYON (What-if) — Ledger'a HİÇBİR ŞEY YAZMAZ
    # =================================================================
    @api_router.post("/simulation/entitlement")
    async def simulate_entitlement(
        body: SimulationRequest, user=Depends(require_permission("entitlement:calculate")),
    ):
        req = EntitlementRequest(
            production_cycle_id=body.production_cycle_id,
            unit_price=body.unit_price,
            applied_items=body.applied_items,
        )
        result = await gather_and_compute_entitlement(
            db, req,
            tonnage_override=body.tonnage_override,
            kota_override=body.kota_override,
            destek_mahsup_override=body.destek_mahsup_override,
        )
        return {
            "simulation": True,
            "production_cycle_id": body.production_cycle_id,
            "overrides_applied": {
                "tonnage_override": body.tonnage_override,
                "kota_override": body.kota_override,
                "destek_mahsup_override": body.destek_mahsup_override,
            },
            "result": result,
        }

    # =================================================================
    # UFYD DASHBOARD — canlı hesaplanır (Ledger/SupportRequest/Entitlement)
    # =================================================================
    @api_router.get("/ufyd/dashboard")
    async def ufyd_dashboard(user=Depends(require_permission("ledger:view"))):
        entitlements = await db.entitlements.find({}, {"_id": 0}).to_list(2000)
        total_hakedis = sum(e.get("gross_entitlement", 0) for e in entitlements)
        total_payable = sum(e.get("payable_amount", 0) for e in entitlements)

        destek_entries = await db.ledger_entries.find({"entry_type": "destek_teslimi"}, {"_id": 0}).to_list(5000)
        total_destek = -sum(e["amount"] for e in destek_entries)

        by_farmer: Dict[str, float] = {}
        for e in destek_entries:
            fid = e.get("farmer_id")
            if fid:
                by_farmer[fid] = by_farmer.get(fid, 0) - e["amount"]
        top_farmer_ids = sorted(by_farmer.items(), key=lambda x: x[1], reverse=True)[:5]
        top_farmers = []
        for fid, amount in top_farmer_ids:
            farmer = await db.farmers.find_one({"id": fid}, {"_id": 0, "full_name": 1, "member_no": 1})
            if farmer:
                top_farmers.append({"farmer_id": fid, "full_name": farmer["full_name"],
                                     "member_no": farmer.get("member_no"), "total_destek": round(amount, 2)})

        pending_requests = await db.support_requests.count_documents(
            {"status": {"$nin": ["tamamlandi", "reddedildi", "iptal_edildi"]}}
        )

        # Bölgesel destek dağılımı — farmer.region_id üzerinden gruplanır.
        by_region: Dict[str, float] = {}
        farmer_ids = list(by_farmer.keys())
        if farmer_ids:
            farmers = await db.farmers.find({"id": {"$in": farmer_ids}}, {"_id": 0, "id": 1, "region_id": 1}).to_list(2000)
            region_by_farmer = {f["id"]: f.get("region_id") for f in farmers}
            for fid, amount in by_farmer.items():
                region = region_by_farmer.get(fid) or "bilinmeyen"
                by_region[region] = by_region.get(region, 0) + amount

        return {
            "total_hakedis": round(total_hakedis, 2),
            "total_destek": round(total_destek, 2),
            "pending_payments": round(total_payable, 2),
            "top_destek_farmers": top_farmers,
            "pending_support_requests": pending_requests,
            "cash_need": round(total_payable, 2),  # v1: bekleyen ödemelerle aynı — bkz. modül docstring'i
            "destek_by_region": {k: round(v, 2) for k, v in by_region.items()},
        }
