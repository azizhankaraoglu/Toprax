"""
=====================================================================
Toprax — Destek Kataloğu + Destek Talep Süreci Modülü (IT-18 / FAZ 7 — UFYD)
=====================================================================
UFYD (Üretim Finans Yaşam Döngüsü) omurgasının ilk halkası:

    Destek Talebi → Onay → Teslim → Çiftçi Onayı → Cari Hareket → ...
    (Cari Hareket/Hakediş/Mahsup/Ödeme zinciri IT-19/IT-20'nin kapsamı)

Tüm SupportRequest kayıtları **ProductionCycle (Üretim Sezonu) bazlıdır**,
Parcel'e değil (IT-05'ten beri süregelen omurga kuralı).

SupportType: admin tanımlı, kod gerektirmeyen destek tipi kataloğu
(Mazot/Gübre/Tohum/... ) — soft delete (convention #3: is_active).

SupportRequest: 9 durumlu, SIRALI durum makinesi (atlama yok — geriye
dönüş sadece Reddedildi/İptal Edildi ile, her adımdan mümkün). Çiftçi
onayı adımı bir doğrulama yöntemi ister; ilk fazda sadece "mobil_onay"
ve "fotograf" ZORUNLU/desteklenen yöntemler, "qr_kod"/"dijital_imza"/
"gps_konumu" şimdilik sadece enum'da yer alan (UI'da seçilebilir ama
endpoint'çe henüz doğrulanmayan) altyapı — ROADMAP'in "diğerleri
altyapı olarak hazır" notuyla tutarlı.

Comm Hub (IT-25) henüz yok — durum değişikliklerinde bildirim, mevcut
hafif `notifications` koleksiyonuna (server.py'deki irrigation_events
akışıyla AYNI desen) insert edilerek "tetiklenebilir" kriteri karşılanır;
gerçek çok-kanallı gönderim IT-25 sonrası bu insert'in üzerine kurulacak.

Reddedilen/iptal edilen bir talep hiçbir Ledger/cari hesap yan etkisi
ÜRETMEZ. **(IT-19 entegrasyonu):** bir SupportRequest "muhasebelesti"
durumuna geçtiğinde (omurga akışındaki "Cari Hareket" adımı — bu durum
adı zaten bunu ima ediyordu) `ledger.create_ledger_entry()` ile OTOMATİK
bir `entry_type="destek_teslimi"` kaydı açılır: tutar = `requested_amount
* support_type.default_price` (fiyat 0/tanımsızsa 0 TL — admin katalogdan
fiyat girmeden gerçek parasal etki oluşmaz, bilinçli varsayılan), işaret
NEGATİF (çiftçiye verilen destek onun cari hesabından düşülür/borç
yazılır — ileride IT-20'nin hakediş/mahsup zincirinde geri kapanır).
`reddedildi`/`iptal_edildi` durumları bu zincire HİÇ girmez (transition
handler'ında SADECE "muhasebelesti" dalında tetiklenir).
"""
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List

from ledger import create_ledger_entry
from event_bus import publish, subscribe
from approval import maybe_start_approval

DEFAULT_SUPPORT_TYPES = [
    {"name": "Mazot", "unit": "lt"},
    {"name": "Gübre", "unit": "kg"},
    {"name": "Tohum", "unit": "kg"},
    {"name": "İlaç", "unit": "lt"},
    {"name": "Makine Hizmeti", "unit": "saat"},
    {"name": "Sulama", "unit": "saat"},
    {"name": "Nakliye", "unit": "sefer"},
    {"name": "Avans", "unit": "TL"},
    {"name": "Diğer", "unit": "adet"},
]

# Sıralı akış — atlama yok, geriye dönüş sadece reddedildi/iptal_edildi ile.
STATUS_FLOW = [
    "taslak", "gonderildi", "inceleniyor", "onaylandi", "hazirlaniyor",
    "teslim_edildi", "ciftci_onayladi", "muhasebelesti", "tamamlandi",
]

STATUS_LABELS = {
    "taslak": "Taslak", "gonderildi": "Gönderildi", "inceleniyor": "İnceleniyor",
    "onaylandi": "Onaylandı", "hazirlaniyor": "Hazırlanıyor", "teslim_edildi": "Teslim Edildi",
    "ciftci_onayladi": "Çiftçi Onayladı", "muhasebelesti": "Muhasebeleşti", "tamamlandi": "Tamamlandı",
    "reddedildi": "Reddedildi", "iptal_edildi": "İptal Edildi",
}

# Her sıradaki durumdan: bir sonraki adım VEYA red/iptal dallanması.
ALLOWED_TRANSITIONS = {}
for _i, _s in enumerate(STATUS_FLOW[:-1]):
    ALLOWED_TRANSITIONS[_s] = {STATUS_FLOW[_i + 1], "reddedildi", "iptal_edildi"}
ALLOWED_TRANSITIONS[STATUS_FLOW[-1]] = set()   # "tamamlandi" terminal
ALLOWED_TRANSITIONS["reddedildi"] = set()      # terminal
ALLOWED_TRANSITIONS["iptal_edildi"] = set()    # terminal

TERMINAL_NEGATIVE = {"reddedildi", "iptal_edildi"}

# Çiftçi onayı doğrulama yöntemleri — tam enum (altyapı), ama bu fazda
# SADECE ilk ikisi (mobil_onay, fotograf) endpoint tarafından zorunlu
# kılınıp kabul edilir; diğerleri UI'da seçilebilir hale gelmeden önce
# ayrı bir iterasyonda (QR üretimi, dijital imza akışı, GPS doğrulama)
# gerçek doğrulama mantığına bağlanmalı.
CONFIRMATION_METHODS_ALL = ["mobil_onay", "qr_kod", "dijital_imza", "fotograf", "gps_konumu"]
# (IT-39 / FAZ 13) qr_kod eklendi — personel `teslim_edildi` durumundaki
# talep için tek-kullanımlık, kısa ömürlü bir teslim kodu üretir
# (`POST /support-requests/{id}/delivery-code`), çiftçi KENDİ mobil
# cihazından bu kodu girip `POST /portal/support-requests/confirm-delivery-code`
# ile ciftci_onayladi geçişini KENDİSİ tetikler — mobil_onay/fotograf'ın
# aksine bu YÖNETİCİ değil ÇİFTÇİNİN kendi eylemidir (bkz. aşağıdaki
# support_qr_tokens uçları). Gerçek kamera-taramalı barkod YERİNE kısa
# alfanümerik kod kullanıldı — yeni bir QR-render kütüphanesi eklemeden
# (Karar Protokolü: yeni bağımlılık her zaman sorulur) aynı güvenlik
# özelliğini (tek-kullanımlık, süreli, cihaz-bağımsız doğrulama) verir;
# kullanıcı isterse ileride gerçek kamera taramalı QR'a kütüphane
# eklenerek yükseltilebilir.
CONFIRMATION_METHODS_ENFORCED = {"mobil_onay", "fotograf", "qr_kod"}
DELIVERY_CODE_TTL_MINUTES = 10


class SupportTypeCreate(BaseModel):
    name: str
    unit: str
    default_price: float = 0
    accounting_code: Optional[str] = None
    deduct_from_stock: bool = False
    vat_rate: float = 0
    approval_flow_id: Optional[str] = None


class SupportTypeUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    default_price: Optional[float] = None
    accounting_code: Optional[str] = None
    deduct_from_stock: Optional[bool] = None
    vat_rate: Optional[float] = None
    approval_flow_id: Optional[str] = None
    is_active: Optional[bool] = None


class SupportRequestCreate(BaseModel):
    """Admin/dahili oluşturma — /support-requests. `taslak` durumunda açılır."""
    farmer_id: str
    production_cycle_id: str
    support_type_id: str
    requested_amount: float
    unit: Optional[str] = None
    note: Optional[str] = None


class SupportRequestPortalCreate(BaseModel):
    """Çiftçi portalı oluşturma — /portal/support-requests. farmer_id token'dan gelir."""
    production_cycle_id: str
    support_type_id: str
    requested_amount: float
    note: Optional[str] = None


class SupportRequestTransition(BaseModel):
    status: str
    confirmation_method: Optional[str] = None   # sadece hedef "ciftci_onayladi" ise gerekli
    reason: Optional[str] = None                # sadece reddedildi/iptal_edildi için (opsiyonel)


class DeliveryCodeConfirm(BaseModel):
    code: str


def register_support_routes(api_router, db, current_user, require_permission, log_audit):

    async def _handle_approval_decided(db, event_type, payload):
        """(IT-07b) approval.py'nin yayınladığı SADECE process="support_request"
        olaylarını dinler; onaylanırsa "onaylandi", reddedilirse "reddedildi"
        durumuna geçirir — transition_support_request'in AYNI durum makinesini
        kullanır (kod tekrarı yok, sadece HTTP context'i olmadığı için doğrudan
        DB güncellemesi yapılır, automation.py'nin create_field_task_from_rule
        deseniyle AYNI ayrım: endpoint = kullanıcı eylemi, handler = event eylemi)."""
        if payload.get("process") != "support_request":
            return
        request_id = payload["entity_id"]
        old = await db.support_requests.find_one({"id": request_id}, {"_id": 0})
        if not old or old["status"] != "inceleniyor":
            return
        new_status = "onaylandi" if payload.get("decision") == "onaylandi" else "reddedildi"
        await db.support_requests.update_one({"id": request_id}, {"$set": {
            "status": new_status, "status_updated_at": datetime.now(timezone.utc).isoformat(),
        }})

    subscribe("approval_decided", _handle_approval_decided)

    async def _support_type_or_404(support_type_id: str) -> dict:
        stype = await db.support_types.find_one({"id": support_type_id}, {"_id": 0})
        if not stype or not stype.get("is_active", True):
            raise HTTPException(404, "Destek tipi bulunamadı veya pasif")
        return stype

    async def _cycle_for_farmer_or_error(production_cycle_id: str, farmer_id: str, forbidden_status: int) -> dict:
        cycle = await db.production_cycles.find_one({"id": production_cycle_id}, {"_id": 0})
        if not cycle:
            raise HTTPException(404, "Üretim sezonu bulunamadı")
        if cycle["farmer_id"] != farmer_id:
            raise HTTPException(forbidden_status, "Bu üretim sezonu bu çiftçiye ait değil")
        return cycle

    async def _notify(farmer_id: Optional[str], title: str, message: str):
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "type": "destek_talebi",
            "title": title,
            "message": message,
            "channel": "in_app",
            "status": "yeni",
            "farmer_id": farmer_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # =================================================================
    # DESTEK KATALOĞU (SupportType) — Ayarlar altında yönetilir
    # =================================================================
    @api_router.get("/support-types")
    async def list_support_types(
        include_inactive: bool = False,
        user=Depends(require_permission("support:catalog_view")),
    ):
        filt = {} if include_inactive else {"is_active": True}
        return await db.support_types.find(filt, {"_id": 0}).sort("name", 1).to_list(200)

    @api_router.post("/support-types")
    async def create_support_type(
        body: SupportTypeCreate, request: Request,
        user=Depends(require_permission("support:catalog_manage")),
    ):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.support_types.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="support_type", entity_id=doc["id"],
                         new_value=doc, request=request)
        return doc

    @api_router.put("/support-types/{type_id}")
    async def update_support_type(
        type_id: str, body: SupportTypeUpdate, request: Request,
        user=Depends(require_permission("support:catalog_manage")),
    ):
        old = await db.support_types.find_one({"id": type_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Destek tipi bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.support_types.update_one({"id": type_id}, {"$set": updates})
        new = await db.support_types.find_one({"id": type_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="support_type", entity_id=type_id,
                         old_value=old, new_value=new, request=request)
        return new

    @api_router.post("/support-types/seed-defaults")
    async def seed_default_support_types(
        request: Request, user=Depends(require_permission("support:catalog_manage")),
    ):
        """Idempotent: Mazot/Gübre/Tohum/İlaç/Makine/Sulama/Nakliye/Avans/Diğer — sadece eksik olanlar eklenir."""
        created = []
        for d in DEFAULT_SUPPORT_TYPES:
            existing = await db.support_types.find_one({"name": d["name"]}, {"_id": 0})
            if existing:
                continue
            doc = {
                "id": str(uuid.uuid4()), "name": d["name"], "unit": d["unit"],
                "default_price": 0, "accounting_code": None, "deduct_from_stock": False,
                "vat_rate": 0, "approval_flow_id": None, "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.support_types.insert_one(doc)
            created.append(d["name"])
        if created:
            await log_audit(db, user, action="seed", entity="support_type", entity_id="bulk",
                             new_value={"created": created}, request=request)
        return {"status": "ok", "created": created}

    # =================================================================
    # DESTEK TALEBİ (SupportRequest) — dahili/admin taraf
    # =================================================================
    @api_router.get("/support-requests")
    async def list_support_requests(
        farmer_id: Optional[str] = None,
        production_cycle_id: Optional[str] = None,
        status: Optional[str] = None,
        user=Depends(require_permission("support:requests_view")),
    ):
        filt = {}
        if farmer_id:
            filt["farmer_id"] = farmer_id
        if production_cycle_id:
            filt["production_cycle_id"] = production_cycle_id
        if status:
            filt["status"] = status
        return await db.support_requests.find(filt, {"_id": 0}).sort("requested_at", -1).to_list(500)

    @api_router.get("/support-requests/{request_id}")
    async def get_support_request(request_id: str, user=Depends(require_permission("support:requests_view"))):
        doc = await db.support_requests.find_one({"id": request_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Destek talebi bulunamadı")
        return doc

    @api_router.post("/support-requests")
    async def create_support_request(
        body: SupportRequestCreate, request: Request,
        user=Depends(require_permission("support:requests_manage")),
    ):
        farmer = await db.farmers.find_one({"id": body.farmer_id}, {"_id": 0})
        if not farmer:
            raise HTTPException(404, "Çiftçi bulunamadı")
        await _cycle_for_farmer_or_error(body.production_cycle_id, body.farmer_id, 400)
        stype = await _support_type_or_404(body.support_type_id)

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["unit"] = body.unit or stype["unit"]
        doc["status"] = "taslak"
        doc["channel"] = "dahili"
        now = datetime.now(timezone.utc).isoformat()
        doc["requested_at"] = now
        doc["status_updated_at"] = now
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.support_requests.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="support_request", entity_id=doc["id"],
                         new_value=doc, request=request)
        return doc

    @api_router.put("/support-requests/{request_id}/transition")
    async def transition_support_request(
        request_id: str, body: SupportRequestTransition, request: Request,
        user=Depends(require_permission("support:requests_manage")),
    ):
        old = await db.support_requests.find_one({"id": request_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Destek talebi bulunamadı")
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

        # (IT-07b) Onay Zinciri Motoru — SADECE process="support_request" için aktif
        # bir kural tanımlıysa "onaylandi" geçişi onaya düşer; tanımlı DEĞİLSE
        # (varsayılan/mevcut davranış) doğrudan geçer — geriye uyumlu.
        if body.status == "onaylandi":
            approval = await maybe_start_approval(
                db, process="support_request", entity_type="support_request", entity_id=request_id,
                requester_user_id=old.get("requested_by") or user["id"],
                context={"requested_amount": old.get("requested_amount")},
            )
            if approval:
                return {"status": "onay_bekliyor", "approval_instance": approval, "support_request": old}

        updates = {"status": body.status, "status_updated_at": datetime.now(timezone.utc).isoformat()}

        if body.status == "ciftci_onayladi":
            if not body.confirmation_method or body.confirmation_method not in CONFIRMATION_METHODS_ALL:
                raise HTTPException(
                    400,
                    "Çiftçi onayı için geçerli bir doğrulama yöntemi gerekli "
                    f"({', '.join(CONFIRMATION_METHODS_ALL)})",
                )
            if body.confirmation_method not in CONFIRMATION_METHODS_ENFORCED:
                raise HTTPException(
                    400,
                    "Bu fazda çiftçi onayı sadece 'mobil_onay' veya 'fotograf' ile alınabilir "
                    "(diğer yöntemler altyapı olarak hazır, henüz aktif değil)",
                )
            updates["confirmation_method"] = body.confirmation_method
            updates["confirmed_at"] = updates["status_updated_at"]

        if body.status in TERMINAL_NEGATIVE and body.reason:
            updates["close_reason"] = body.reason

        await db.support_requests.update_one({"id": request_id}, {"$set": updates})
        new = await db.support_requests.find_one({"id": request_id}, {"_id": 0})

        await log_audit(db, user, action="status_change", entity="support_request", entity_id=request_id,
                         old_value={"status": current}, new_value={"status": body.status}, request=request)

        # (IT-19) Omurga akışındaki "Cari Hareket" adımı — sadece burada, sadece
        # bu dalda tetiklenir; reddedildi/iptal_edildi hiçbir zaman buraya girmez.
        if body.status == "muhasebelesti":
            stype = await db.support_types.find_one({"id": new["support_type_id"]}, {"_id": 0})
            unit_price = (stype or {}).get("default_price", 0) or 0
            amount = round(new["requested_amount"] * unit_price, 2)
            ledger_entry = await create_ledger_entry(
                db, production_cycle_id=new["production_cycle_id"], farmer_id=new["farmer_id"],
                entry_type="destek_teslimi", amount=-amount, currency="TRY",
                reference_type="support_request", reference_id=new["id"],
                description=f"{(stype or {}).get('name', 'Destek')} — {new['requested_amount']} {new['unit']} teslim edildi",
                created_by=user.get("full_name") or user.get("email"),
            )
            await log_audit(db, user, action="create", entity="ledger_entry", entity_id=ledger_entry["id"],
                             new_value=ledger_entry, request=request)

        # (IT-24) Otomasyon tetikleyicisi — destek süreci tamamen bittiğinde
        # (ör. "Nakliye" desteği tamamlandıysa bir "Teslim Kontrolü" saha
        # görevi otomatik açılabilir, admin bunu kural olarak tanımlarsa).
        if body.status == "tamamlandi":
            await publish(db, "support_request_completed", {
                "farmer_id": new["farmer_id"],
                "production_cycle_id": new["production_cycle_id"],
                "support_type_id": new["support_type_id"],
            })

        farmer = await db.farmers.find_one({"id": old["farmer_id"]}, {"_id": 0})
        farmer_name = farmer["full_name"] if farmer else "Çiftçi"
        await _notify(
            old["farmer_id"],
            "Destek talebi durumu güncellendi",
            f"{farmer_name} için destek talebi '{STATUS_LABELS.get(current, current)}' → "
            f"'{STATUS_LABELS.get(body.status, body.status)}' durumuna geçti",
        )
        return new

    # =================================================================
    # TESLİM KODU (IT-39 / FAZ 13) — "qr_kod" doğrulama yöntemini
    # gerçekleştirir. Personel `teslim_edildi` durumundaki bir talep için
    # tek-kullanımlık, süreli bir kod üretir; çiftçi bu kodu KENDİ
    # cihazından girip (bkz. aşağıdaki /portal/support-requests/
    # confirm-delivery-code) kendi onayını kendisi verir.
    # =================================================================
    @api_router.post("/support-requests/{request_id}/delivery-code")
    async def create_delivery_code(
        request_id: str, request: Request,
        user=Depends(require_permission("support:requests_manage")),
    ):
        req = await db.support_requests.find_one({"id": request_id}, {"_id": 0})
        if not req:
            raise HTTPException(404, "Destek talebi bulunamadı")
        if req["status"] != "teslim_edildi":
            raise HTTPException(400, "Teslim kodu sadece 'Teslim Edildi' durumundaki talepler için üretilebilir")

        code = f"{secrets.randbelow(1_000_000):06d}"
        now = datetime.now(timezone.utc)
        doc = {
            "id": str(uuid.uuid4()),
            "request_id": request_id,
            "farmer_id": req["farmer_id"],
            "code": code,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=DELIVERY_CODE_TTL_MINUTES)).isoformat(),
            "used_at": None,
        }
        await db.support_qr_tokens.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="support_qr_token", entity_id=doc["id"],
                         new_value={"request_id": request_id}, request=request)
        return {"code": code, "expires_at": doc["expires_at"], "ttl_minutes": DELIVERY_CODE_TTL_MINUTES}

    # =================================================================
    # ÇİFTÇİ PORTALI — /portal/support-requests (+ sezon seçimi için
    # yardımcı liste; production_cycles.py'nin GET /production-cycles'ı
    # require_permission("production_cycles:view") ister ve ciftci rolü
    # bu sisteme dahil DEĞİLDİR — bkz. permissions.py "ciftci": [] notu —
    # bu yüzden çiftçinin KENDİ sezonlarını görebileceği ayrı, hafif bir
    # /farmer/* tarzı uç burada tanımlanır).
    # =================================================================
    @api_router.get("/portal/support-types")
    async def portal_list_support_types(user=Depends(current_user)):
        """Çiftçi kendi talep formunda seçecek — /support-types (support:catalog_view) ciftci'ye kapalı (bkz. permissions.py "ciftci": [])."""
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        return await db.support_types.find({"is_active": True}, {"_id": 0}).sort("name", 1).to_list(200)

    @api_router.get("/portal/production-cycles")
    async def portal_list_my_production_cycles(user=Depends(current_user)):
        """İptal edilmiş sezonlar hariç — yeni bir destek talebi iptal edilmiş bir
        sezona bağlanmamalı (tamamlanmış sezonlar dahil: hasat sonrası nakliye vb.
        destek talepleri hâlâ anlamlı)."""
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        return await db.production_cycles.find(
            {"farmer_id": user["farmer_id"], "status": {"$ne": "cancelled"}}, {"_id": 0}
        ).sort("year", -1).to_list(200)

    @api_router.get("/portal/support-requests")
    async def portal_list_support_requests(
        production_cycle_id: Optional[str] = None, user=Depends(current_user),
    ):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi erişebilir")
        filt = {"farmer_id": user["farmer_id"]}
        if production_cycle_id:
            filt["production_cycle_id"] = production_cycle_id
        return await db.support_requests.find(filt, {"_id": 0}).sort("requested_at", -1).to_list(200)

    @api_router.post("/portal/support-requests")
    async def portal_create_support_request(
        body: SupportRequestPortalCreate, request: Request, user=Depends(current_user),
    ):
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi talep oluşturabilir")
        await _cycle_for_farmer_or_error(body.production_cycle_id, user["farmer_id"], 403)
        stype = await _support_type_or_404(body.support_type_id)

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["farmer_id"] = user["farmer_id"]
        doc["unit"] = stype["unit"]
        doc["status"] = "gonderildi"
        doc["channel"] = "portal"
        now = datetime.now(timezone.utc).isoformat()
        doc["requested_at"] = now
        doc["status_updated_at"] = now
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.support_requests.insert_one(doc)
        doc.pop("_id", None)

        await log_audit(db, user, action="create", entity="support_request", entity_id=doc["id"],
                         new_value=doc, request=request)
        await _notify(
            user["farmer_id"], "Yeni destek talebi",
            f"{user.get('full_name', 'Çiftçi')} '{stype['name']}' için {body.requested_amount} "
            f"{stype['unit']} destek talebi oluşturdu",
        )
        return doc

    @api_router.post("/portal/support-requests/confirm-delivery-code")
    async def portal_confirm_delivery_code(
        body: DeliveryCodeConfirm, request: Request, user=Depends(current_user),
    ):
        """(IT-39) Çiftçi personelden aldığı teslim kodunu KENDİ cihazından
        girer — bu çağrı `ciftci_onayladi` geçişini (`confirmation_method=
        qr_kod`) tetikler. `support:requests_manage` İSTEMEZ (transition_
        support_request'in aksine) — bu bilinçli olarak çiftçinin KENDİ
        eylemi, personelin çiftçi adına girdiği bir şey değil."""
        if user.get("role") != "ciftci" or not user.get("farmer_id"):
            raise HTTPException(403, "Sadece çiftçi onaylayabilir")

        token = await db.support_qr_tokens.find_one({"code": body.code}, {"_id": 0})
        if not token or token.get("farmer_id") != user["farmer_id"]:
            raise HTTPException(404, "Geçersiz kod")
        if token.get("used_at"):
            raise HTTPException(410, "Bu kod zaten kullanılmış")
        if datetime.fromisoformat(token["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(410, "Kodun süresi dolmuş — yeni bir kod isteyin")

        req = await db.support_requests.find_one({"id": token["request_id"]}, {"_id": 0})
        if not req:
            raise HTTPException(404, "Destek talebi bulunamadı")
        if req["status"] != "teslim_edildi":
            raise HTTPException(
                400,
                f"Talep '{STATUS_LABELS.get(req['status'], req['status'])}' durumunda — "
                "'Teslim Edildi' durumunda olmalı",
            )

        now = datetime.now(timezone.utc).isoformat()
        await db.support_qr_tokens.update_one({"id": token["id"]}, {"$set": {"used_at": now}})
        await db.support_requests.update_one({"id": req["id"]}, {"$set": {
            "status": "ciftci_onayladi", "status_updated_at": now,
            "confirmation_method": "qr_kod", "confirmed_at": now,
        }})
        new = await db.support_requests.find_one({"id": req["id"]}, {"_id": 0})
        await log_audit(db, user, action="status_change", entity="support_request", entity_id=req["id"],
                         old_value={"status": "teslim_edildi"}, new_value={"status": "ciftci_onayladi"}, request=request)
        await _notify(
            user["farmer_id"], "Teslimat onaylandı",
            f"{user.get('full_name', 'Çiftçi')} teslim kodunu girerek onayladı",
        )
        return new
