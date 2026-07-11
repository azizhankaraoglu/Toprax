"""
=====================================================================
TabSIS — Dinamik Form Yönetimi & Lookup Yönetimi (Sprint A1)
=====================================================================
Bu modül forms_module.py (M18 — GPS/foto destekli saha anket formları)
İLE KARIŞTIRILMAMALIDIR. Farklı bir problemi çözer:

  forms_module.py     → çiftçiye/saha personeline gönderilen ANKET formu
  field_definitions.py → Çiftçi/Parsel/Sözleşme/Ekim/Toprak gibi ÇEKİRDEK
                          entity ekranlarındaki alanların METADATA'sını
                          yönetir (zorunlu mu, görünür mü, sırası, tipi,
                          hangi lookup'a bağlı vb.)

Önemli: Bu modül veritabanında gerçek kolon YARATMAZ. Sprint A1'in
"her yeni alan gerçek kolon olacak" kuralı gereği, gerçek alanlar
ilgili entity'nin Pydantic modeline (server.py / data_entry.py) elle
eklenir. Bu modül sadece o alanların EKRANDA nasıl davranacağını
(zorunlu/görünür/sıra/yardım metni/lookup bağlantısı) tanımlar — yani
form render metadata katmanıdır, veri deposu değil.

Kapsanan modüller: farmers, parcels, contracts, plantings, soil
(bu key'ler MODULE_LABELS altında sabit tutulur; yeni bir entity
modülü eklenmek istenirse sadece bu sözlüğe satır eklemek yeterlidir).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Any


# =====================================================================
# SABİTLER
# =====================================================================

# Form Yönetimi'nin alan tanımı ekleyebileceği çekirdek entity modülleri.
# Yeni bir entity modülü eklenirse (örn. Sprint A2'de "irrigation")
# sadece burada yeni bir satır açmak yeterli — kod başka yerde değişmez.
MODULE_LABELS = {
    "farmers": "Çiftçi",
    "parcels": "Parsel",
    "contracts": "Sözleşme",
    "plantings": "Ekim Planlama",
    "soil": "Toprak",
    "admin_areas": "İdari Alan",  # IT-13.6 — demografik alanlar bu modül üzerinden yönetilir
}

# Sprint A1'de listelenen alan tipleri. Yeni tip eklemek için sadece
# buraya satır eklenir — validasyon otomatik güncellenir.
FIELD_TYPES = [
    "text", "textarea", "number", "decimal", "date", "datetime", "time",
    "checkbox", "switch", "radio", "select", "multiselect",
    "lookup", "autocomplete",
    "iban", "phone", "email", "tckn", "vergino",
    "file", "image", "multifile",
    "geojson", "coordinate", "url",
]

# Bu tipler bir lookup grubuna bağlanabilir (opsiyonel ama tipik kullanım).
LOOKUP_CAPABLE_TYPES = {"select", "multiselect", "radio", "lookup", "autocomplete"}

_TR_CHAR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
    "ş": "s", "Ş": "s", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def _slugify_tr(text: str) -> str:
    """IT-01.5 — toplu değer girişinde etiketten sistemsel `value` üretir
    (örn. "Seydişehir" -> "seydisehir"). Sadece [a-z0-9_] bırakır.
    ÖNCE Türkçe karakter çevirisi, SONRA .lower() yapılır — tersi sırada
    Python'un Unicode "İ" (nokta) küçültmesi "i" + birleşik nokta işareti
    (U+0307) gibi iki karaktere açar ve bu, translate tablosundaki tek
    karakterlik "İ"->"i" eşlemesini atlayıp yanlışlıkla "_" üretir
    (örn. "İlçe" -> "i_lce" yerine doğrusu "ilce")."""
    s = text.strip().translate(_TR_CHAR_MAP).lower()
    s = "".join(c if c.isalnum() else "_" for c in s)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


# =====================================================================
# FIELD-LEVEL SECURITY v1 (IT-07)
# =====================================================================
# field_definitions'ta sensitive=True işaretlenen alanlar, sistem
# katmanı (config_service.get_system_tier) "admin" ve üzeri olmayan
# kullanıcılara MASKELENMİŞ döner. Gerçek değer DB'de değişmez —
# maskeleme sadece response serileştirmede uygulanır. Diğer modüller
# (server.py, data_entry.py vb.) kendi GET endpoint'lerinde bu
# fonksiyonları çağırarak entegre eder; register_field_definition_routes
# içindeki `db` closure'ından bağımsızdır (çağıran kendi `db`'sini geçer).
MASK_PLACEHOLDER = "•••• MASKELİ ••••"


def is_masked_value(value: Any) -> bool:
    """update endpoint'lerinde: kullanıcı maskeli değeri değiştirmeden geri
    gönderirse (edit formu prefill'i maskeli göstermişse) bunu 'değişmedi'
    olarak algılayıp gerçek veriyi ezmemek için kullanılır."""
    return value == MASK_PLACEHOLDER


def _mask(value: Any) -> Any:
    if value is None or value == "":
        return value
    return MASK_PLACEHOLDER


async def get_sensitive_field_keys(db, module: str) -> set:
    rows = await db.field_definitions.find(
        {"module": module, "sensitive": True, "is_active": True}, {"_id": 0, "field_key": 1}
    ).to_list(200)
    return {r["field_key"] for r in rows}


async def mask_sensitive_fields(db, module: str, doc: Optional[dict], user: dict) -> Optional[dict]:
    """Tek bir entity dokümanına (örn. GET /farmers/{id}) maskeleme uygular."""
    from config_service import get_system_tier
    if doc is None or get_system_tier(user.get("role")) in ("god_mode", "super_admin", "admin"):
        return doc
    keys = await get_sensitive_field_keys(db, module)
    if not keys:
        return doc
    out = dict(doc)
    for k in keys:
        if k in out:
            out[k] = _mask(out[k])
    return out


async def get_filterable_field_defs(db, module: str) -> List[dict]:
    """IT-08 — Query Engine'in field_definitions tarafını besler: bir modülde
    yönetici tarafından filterable=True işaretlenmiş (dinamik/ek) alanların
    {key, label, type} listesini döner. query_engine.py bunu modülün
    CORE_FILTERABLE_FIELDS (temel/kod-seviyesi) listesiyle birleştirir."""
    rows = await db.field_definitions.find(
        {"module": module, "filterable": True, "is_active": True}, {"_id": 0}
    ).to_list(500)
    return [{"key": r["field_key"], "label": r["label"], "type": r["field_type"]} for r in rows]


async def mask_sensitive_fields_many(db, module: str, docs: List[dict], user: dict) -> List[dict]:
    """Bir liste entity dokümanına (örn. GET /farmers) maskeleme uygular."""
    from config_service import get_system_tier
    if get_system_tier(user.get("role")) in ("god_mode", "super_admin", "admin"):
        return docs
    keys = await get_sensitive_field_keys(db, module)
    if not keys:
        return docs
    for d in docs:
        for k in keys:
            if k in d:
                d[k] = _mask(d[k])
    return docs


# =====================================================================
# MODELLER — ALAN TANIMI (Form Yönetimi)
# =====================================================================

class FieldDefinitionCreate(BaseModel):
    module: str                                    # MODULE_LABELS key'lerinden biri
    field_key: str                                  # snake_case, modül içinde benzersiz — DB kolon adıyla eşleşmeli
    label: str
    field_type: str
    required: bool = False
    visible: bool = True
    order: int = 0
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    tab: Optional[str] = None                       # örn. "Kimlik Bilgileri", "İletişim"
    lookup_group_id: Optional[str] = None            # field_type lookup-capable ise
    options: Optional[List[str]] = None              # statik select/radio için (lookup kullanılmıyorsa)
    sensitive: bool = False                          # IT-07 — Field-Level Security v1
    filterable: bool = False                         # IT-08 — Query Engine'de filtrelenebilir
    depends_on_field: Optional[str] = None           # IT-01.5 — aynı modülde başka bir field_key; DynamicFieldsSection o alanın seçimine göre bu alanın lookup değerlerini kaskad filtreler


class FieldDefinitionUpdate(BaseModel):
    label: Optional[str] = None
    field_type: Optional[str] = None
    required: Optional[bool] = None
    visible: Optional[bool] = None
    order: Optional[int] = None
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    tab: Optional[str] = None
    lookup_group_id: Optional[str] = None
    options: Optional[List[str]] = None
    is_active: Optional[bool] = None                 # pasife alma — soft delete
    sensitive: Optional[bool] = None                 # IT-07 — Field-Level Security v1
    filterable: Optional[bool] = None                # IT-08 — Query Engine'de filtrelenebilir
    depends_on_field: Optional[str] = None           # IT-01.5 — kaskad bağımlılık (bkz. FieldDefinitionCreate)


class FieldReorderItem(BaseModel):
    id: str
    order: int


class FieldReorderRequest(BaseModel):
    items: List[FieldReorderItem]


# =====================================================================
# MODELLER — LOOKUP YÖNETİMİ
# =====================================================================

class LookupGroupCreate(BaseModel):
    key: str                                        # örn. "sulama_tipi" — field_definitions.lookup_group_id ile referans alınır
    label: str                                       # örn. "Sulama Tipi"
    order: int = 0
    parent_group_id: Optional[str] = None            # IT-01.5 — kaskad: bu grubun değerleri üst gruptaki bir değere bağlanır (örn. ilçe -> il)


class LookupGroupUpdate(BaseModel):
    label: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None
    parent_group_id: Optional[str] = None


class LookupValueCreate(BaseModel):
    value: str                                       # sistemsel değer, örn. "damla"
    label: str                                        # görünen değer, örn. "Damla Sulama"
    parent_id: Optional[str] = None                   # hiyerarşik lookup için — grubun parent_group_id'si varsa ÜST GRUPTAKİ, yoksa AYNI GRUPTAKİ bir değerin id'si olmalı
    order: int = 0


class LookupValueUpdate(BaseModel):
    label: Optional[str] = None
    parent_id: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class LookupValueBulkImportRequest(BaseModel):
    text: str                                         # kopyala-yapıştır — satır başına bir değer ("sistem_degeri|Görünen Ad" veya sadece "Görünen Ad")
    parent_id: Optional[str] = None                   # tüm satırlar için ortak üst değer (grup parent_group_id taşıyorsa üst gruptan, yoksa aynı gruptan)


# =====================================================================
# ROUTE KAYDI
# =====================================================================

def register_field_definition_routes(api_router, db, current_user, require_permission, log_audit):
    """Form Yönetimi (alan tanımları) + Lookup Yönetimi endpoint'lerini kaydet."""

    # -----------------------------------------------------------------
    # META — modül listesi + alan tipi listesi (form builder UI'sı için)
    # -----------------------------------------------------------------
    @api_router.get("/field-definitions/meta")
    async def get_field_definitions_meta(user=Depends(current_user)):
        return {
            "modules": [{"key": k, "label": v} for k, v in MODULE_LABELS.items()],
            "field_types": FIELD_TYPES,
            "lookup_capable_types": sorted(LOOKUP_CAPABLE_TYPES),
        }

    # -----------------------------------------------------------------
    # ALAN TANIMLARI — CRUD
    # -----------------------------------------------------------------
    @api_router.get("/field-definitions")
    async def list_field_definitions(module: Optional[str] = None, user=Depends(current_user)):
        """
        Tüm kullanıcılar okuyabilir — bu liste entity formlarını dinamik
        render etmek için kullanılır (sadece yönetimi yetki gerektirir).
        """
        query = {}
        if module:
            query["module"] = module
        items = await db.field_definitions.find(query, {"_id": 0}).sort("order", 1).to_list(1000)
        return items

    @api_router.post("/field-definitions")
    async def create_field_definition(body: FieldDefinitionCreate, request: Request,
                                       user=Depends(require_permission("settings:fields_manage"))):
        if body.module not in MODULE_LABELS:
            raise HTTPException(400, f"Geçersiz modül: {body.module}. Geçerli değerler: {list(MODULE_LABELS.keys())}")
        if body.field_type not in FIELD_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {body.field_type}")
        if body.lookup_group_id and body.field_type not in LOOKUP_CAPABLE_TYPES:
            raise HTTPException(400, f"'{body.field_type}' tipi lookup grubuna bağlanamaz")
        if body.lookup_group_id:
            group = await db.lookup_groups.find_one({"id": body.lookup_group_id}, {"_id": 0})
            if not group:
                raise HTTPException(404, "Lookup grubu bulunamadı")
        if body.depends_on_field:
            await _validate_depends_on_field(body.module, body.field_key, body.depends_on_field)

        existing = await db.field_definitions.find_one(
            {"module": body.module, "field_key": body.field_key}, {"_id": 0}
        )
        if existing:
            raise HTTPException(409, f"'{body.field_key}' alanı '{body.module}' modülünde zaten tanımlı")

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["updated_at"] = doc["created_at"]
        await db.field_definitions.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="field_definition", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/field-definitions/{field_id}")
    async def update_field_definition(field_id: str, body: FieldDefinitionUpdate, request: Request,
                                       user=Depends(require_permission("settings:fields_manage"))):
        old = await db.field_definitions.find_one({"id": field_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Alan tanımı bulunamadı")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        new_type = updates.get("field_type", old["field_type"])
        if "field_type" in updates and new_type not in FIELD_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {new_type}")
        if updates.get("lookup_group_id") and new_type not in LOOKUP_CAPABLE_TYPES:
            raise HTTPException(400, f"'{new_type}' tipi lookup grubuna bağlanamaz")
        if "depends_on_field" in updates:
            await _validate_depends_on_field(old["module"], old["field_key"], updates["depends_on_field"])

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.field_definitions.update_one({"id": field_id}, {"$set": updates})
        new = await db.field_definitions.find_one({"id": field_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="field_definition", entity_id=field_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.post("/field-definitions/reorder")
    async def reorder_field_definitions(body: FieldReorderRequest, request: Request,
                                         user=Depends(require_permission("settings:fields_manage"))):
        """Sürükle-bırak sıralama — birden fazla alanın order'ını tek seferde günceller."""
        for item in body.items:
            await db.field_definitions.update_one({"id": item.id}, {"$set": {"order": item.order}})
        await log_audit(db, user, action="update", entity="field_definition", entity_id="bulk_reorder",
                         new_value={"items": [i.model_dump() for i in body.items]}, request=request)
        return {"status": "reordered", "count": len(body.items)}

    @api_router.delete("/field-definitions/{field_id}")
    async def delete_field_definition(field_id: str, request: Request,
                                       user=Depends(require_permission("settings:fields_manage"))):
        """
        Alan tanımını PASİFE alır (hard delete yapılmaz — Sprint A1 /
        domain kuralı: "Historical data should never be deleted").
        Zaten girilmiş veri etkilenmez, sadece formda görünmez olur.
        """
        old = await db.field_definitions.find_one({"id": field_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Alan tanımı bulunamadı")
        await db.field_definitions.update_one({"id": field_id}, {"$set": {"is_active": False, "visible": False}})
        await log_audit(db, user, action="delete", entity="field_definition", entity_id=field_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # -----------------------------------------------------------------
    # LOOKUP GRUPLARI
    # -----------------------------------------------------------------
    @api_router.get("/lookups/groups")
    async def list_lookup_groups(user=Depends(current_user)):
        return await db.lookup_groups.find({}, {"_id": 0}).sort("order", 1).to_list(500)

    @api_router.post("/lookups/groups")
    async def create_lookup_group(body: LookupGroupCreate, request: Request,
                                   user=Depends(require_permission("settings:lookups_manage"))):
        existing = await db.lookup_groups.find_one({"key": body.key}, {"_id": 0})
        if existing:
            raise HTTPException(409, f"'{body.key}' anahtarlı lookup grubu zaten var")
        if body.parent_group_id:
            parent_group = await db.lookup_groups.find_one({"id": body.parent_group_id}, {"_id": 0})
            if not parent_group:
                raise HTTPException(404, "Üst lookup grubu bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.lookup_groups.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="lookup_group", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/lookups/groups/{group_id}")
    async def update_lookup_group(group_id: str, body: LookupGroupUpdate, request: Request,
                                   user=Depends(require_permission("settings:lookups_manage"))):
        old = await db.lookup_groups.find_one({"id": group_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Lookup grubu bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates.get("parent_group_id"):
            if updates["parent_group_id"] == group_id:
                raise HTTPException(400, "Bir grup kendi kendinin üst grubu olamaz")
            parent_group = await db.lookup_groups.find_one({"id": updates["parent_group_id"]}, {"_id": 0})
            if not parent_group:
                raise HTTPException(404, "Üst lookup grubu bulunamadı")
        if updates:
            await db.lookup_groups.update_one({"id": group_id}, {"$set": updates})
        new = await db.lookup_groups.find_one({"id": group_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="lookup_group", entity_id=group_id, old_value=old, new_value=new, request=request)
        return new

    # -----------------------------------------------------------------
    # LOOKUP DEĞERLERİ (hiyerarşi destekli — parent_id ile)
    # -----------------------------------------------------------------
    @api_router.get("/lookups/groups/{group_id}/values")
    async def list_lookup_values(group_id: str, parent_id: Optional[str] = None, user=Depends(current_user)):
        """
        parent_id verilmezse gruptaki TÜM değerler döner (düz liste — form
        builder / basit select için). parent_id verilirse sadece o üst
        değerin altındakiler döner (hiyerarşik kaskad select için, örn.
        İl seçilince İlçe listesini filtrelemek).
        """
        query = {"group_id": group_id}
        if parent_id is not None:
            query["parent_id"] = parent_id
        return await db.lookup_values.find(query, {"_id": 0}).sort("order", 1).to_list(2000)

    async def _validate_value_parent(group: dict, parent_id: Optional[str]) -> None:
        """
        IT-01.5 — bir değerin parent_id'sinin hangi GRUPTA aranacağını
        grubun parent_group_id'sine göre belirler:
          - grup parent_group_id taşıyorsa (örn. "ilce" -> "il"): parent
            ÜST GRUPTA aranır (çapraz-grup kaskad — İl/İlçe kalıbı).
          - taşımıyorsa: parent AYNI GRUPTA aranır (kendi kendine ağaç,
            eski davranış — geriye dönük uyumluluk).
        """
        if not parent_id:
            return
        target_group_id = group.get("parent_group_id") or group["id"]
        parent = await db.lookup_values.find_one({"id": parent_id, "group_id": target_group_id}, {"_id": 0})
        if not parent:
            where = "üst grupta" if group.get("parent_group_id") else "aynı grupta"
            raise HTTPException(404, f"Üst lookup değeri bulunamadı ({where} olmalı)")

    @api_router.post("/lookups/groups/{group_id}/values")
    async def create_lookup_value(group_id: str, body: LookupValueCreate, request: Request,
                                   user=Depends(require_permission("settings:lookups_manage"))):
        group = await db.lookup_groups.find_one({"id": group_id}, {"_id": 0})
        if not group:
            raise HTTPException(404, "Lookup grubu bulunamadı")
        await _validate_value_parent(group, body.parent_id)

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["group_id"] = group_id
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.lookup_values.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="lookup_value", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/lookups/values/{value_id}")
    async def update_lookup_value(value_id: str, body: LookupValueUpdate, request: Request,
                                   user=Depends(require_permission("settings:lookups_manage"))):
        old = await db.lookup_values.find_one({"id": value_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Lookup değeri bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates.get("parent_id"):
            group = await db.lookup_groups.find_one({"id": old["group_id"]}, {"_id": 0})
            await _validate_value_parent(group, updates["parent_id"])
        if updates:
            await db.lookup_values.update_one({"id": value_id}, {"$set": updates})
        new = await db.lookup_values.find_one({"id": value_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="lookup_value", entity_id=value_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/lookups/values/{value_id}")
    async def delete_lookup_value(value_id: str, request: Request,
                                   user=Depends(require_permission("settings:lookups_manage"))):
        """Soft delete — geçmiş kayıtlarda bu değer kullanılmış olabilir, veri bütünlüğü için korunur."""
        old = await db.lookup_values.find_one({"id": value_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Lookup değeri bulunamadı")
        await db.lookup_values.update_one({"id": value_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="delete", entity="lookup_value", entity_id=value_id, old_value=old, request=request)
        return {"status": "deactivated"}

    @api_router.post("/lookups/groups/{group_id}/values/bulk-import")
    async def bulk_import_lookup_values(group_id: str, body: LookupValueBulkImportRequest, request: Request,
                                         user=Depends(require_permission("settings:lookups_manage"))):
        """
        IT-01.5 — Toplu değer girişi: kopyala-yapıştır metni, satır başına
        bir değer. Satır formatı "sistem_degeri|Görünen Ad" (elle kontrollü
        value için) VEYA sadece "Görünen Ad" (value otomatik slugify edilir,
        bkz. _slugify_tr). Idempotent: (group_id, value, parent_id) üçlüsü
        zaten varsa o satır atlanır (created değil skipped_existing sayılır).
        """
        group = await db.lookup_groups.find_one({"id": group_id}, {"_id": 0})
        if not group:
            raise HTTPException(404, "Lookup grubu bulunamadı")
        await _validate_value_parent(group, body.parent_id)

        max_order_doc = await db.lookup_values.find(
            {"group_id": group_id, "parent_id": body.parent_id}, {"_id": 0, "order": 1}
        ).sort("order", -1).limit(1).to_list(1)
        next_order = (max_order_doc[0]["order"] + 1) if max_order_doc else 0

        created, skipped, invalid = [], [], []
        for raw_line in body.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "|" in line:
                value_part, _, label_part = line.partition("|")
                value, label = _slugify_tr(value_part), label_part.strip() or value_part.strip()
            else:
                value, label = _slugify_tr(line), line
            if not value:
                invalid.append(raw_line)
                continue
            existing = await db.lookup_values.find_one(
                {"group_id": group_id, "value": value, "parent_id": body.parent_id}, {"_id": 0}
            )
            if existing:
                skipped.append(label)
                continue
            doc = {
                "id": str(uuid.uuid4()), "group_id": group_id, "value": value, "label": label,
                "parent_id": body.parent_id, "order": next_order, "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.lookup_values.insert_one(doc)
            next_order += 1
            created.append(label)

        await log_audit(db, user, action="bulk_import", entity="lookup_value", entity_id=group_id,
                         new_value={"created": created, "skipped": skipped, "invalid": invalid}, request=request)
        return {"status": "imported", "created": len(created), "skipped_existing": len(skipped), "invalid": invalid}

    # -----------------------------------------------------------------
    # PİLOT SEED — Çiftçi modülü (Sprint A1 Faz 2)
    # -----------------------------------------------------------------
    async def _ensure_lookup_group(key: str, label: str, order: int, parent_group_id: Optional[str] = None) -> str:
        """Lookup grubu yoksa oluşturur, varsa mevcut id'sini döner (idempotent).
        CREATE-ONLY: grup zaten varsa parent_group_id'yi GÜNCELLEMEZ — daha önce
        (IT-01.5 öncesi) oluşturulmuş bir gruba sonradan parent_group_id eklemek
        için _upgrade_lookup_group kullanılır (bkz. seed_il_ilce_lookup)."""
        existing = await db.lookup_groups.find_one({"key": key}, {"_id": 0})
        if existing:
            return existing["id"]
        doc = {"id": str(uuid.uuid4()), "key": key, "label": label, "order": order,
               "parent_group_id": parent_group_id,
               "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()}
        await db.lookup_groups.insert_one(doc)
        return doc["id"]

    async def _upgrade_lookup_group(key: str, **updates):
        """VAR OLAN bir lookup grubunun belirli alanlarını (örn. parent_group_id)
        sonradan günceller — bkz. _upgrade_field_definition ile aynı desen."""
        await db.lookup_groups.update_one({"key": key}, {"$set": updates})

    async def _validate_depends_on_field(module: str, own_field_key: str, depends_on_field: str) -> None:
        if depends_on_field == own_field_key:
            raise HTTPException(400, "Bir alan kendi kendine bağımlı olamaz")
        target = await db.field_definitions.find_one(
            {"module": module, "field_key": depends_on_field, "is_active": True}, {"_id": 0}
        )
        if not target:
            raise HTTPException(404, f"Bağımlı olunacak alan bulunamadı: '{depends_on_field}' ({module} modülünde)")
        if not target.get("lookup_group_id"):
            raise HTTPException(400, f"'{depends_on_field}' bir lookup grubuna bağlı değil, kaskad için kullanılamaz")

    async def _ensure_lookup_value(group_id: str, value: str, label: str, order: int, parent_id: Optional[str] = None) -> str:
        """
        Idempotent — (group_id, value, parent_id) üçlüsüne göre benzersizdir.
        parent_id dahil edilerek karşılaştırılır ki hiyerarşik lookup'larda
        (İl -> İlçe) farklı üst değerler altında aynı isimli alt değerler
        (örn. iki farklı ilin aynı adlı bir ilçesi) birbirini ezmesin.
        Döndürdüğü id, hiyerarşik alt değerler için parent_id olarak kullanılır.
        """
        existing = await db.lookup_values.find_one({"group_id": group_id, "value": value, "parent_id": parent_id}, {"_id": 0})
        if existing:
            return existing["id"]
        new_id = str(uuid.uuid4())
        await db.lookup_values.insert_one({
            "id": new_id, "group_id": group_id, "value": value, "label": label,
            "parent_id": parent_id, "order": order, "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return new_id

    async def _ensure_field_definition(module: str, field_key: str, **kwargs):
        existing = await db.field_definitions.find_one({"module": module, "field_key": field_key}, {"_id": 0})
        if existing:
            return
        doc = {
            "id": str(uuid.uuid4()), "module": module, "field_key": field_key,
            "required": False, "visible": True, "order": 0, "help_text": None,
            "placeholder": None, "default_value": None, "tab": None, "lookup_group_id": None,
            "options": None, "is_active": True, "sensitive": False, "filterable": False, "depends_on_field": None,
            "created_by": "sistem (seed)", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        doc["updated_at"] = doc["created_at"]
        doc.update(kwargs)
        await db.field_definitions.insert_one(doc)

    async def _upgrade_field_definition(module: str, field_key: str, **updates):
        """
        _ensure_field_definition CREATE-ONLY'dir (alan zaten varsa dokunmaz).
        Bu fonksiyon VAR OLAN bir alan tanımının belirli özelliklerini
        (örn. field_type/lookup_group_id) sonradan değiştirmek için kullanılır
        — örn. bir alan önce düz text olarak seed edilmiş, sonra bir lookup'a
        bağlanmak istenmiş olabilir. Alan yoksa no-op (yeni bir seed'de zaten
        _ensure_field_definition doğru tiple oluşturmuş olur).
        """
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.field_definitions.update_one({"module": module, "field_key": field_key}, {"$set": updates})

    @api_router.post("/field-definitions/seed-farmers-pilot")
    async def seed_farmers_pilot(user=Depends(require_permission("settings:fields_manage"))):
        """
        Sprint A1 — Faz 2 pilot seed. Çiftçi modülü için lookup grupları +
        field_definitions kayıtlarını oluşturur. Idempotent: zaten var olan
        grup/değer/alan tekrar oluşturulmaz, güvenle tekrar çağrılabilir.
        """
        gender_id = await _ensure_lookup_group("cinsiyet", "Cinsiyet", 1)
        for i, (v, l) in enumerate([("erkek", "Erkek"), ("kadin", "Kadın"), ("belirtilmemis", "Belirtilmemiş")]):
            await _ensure_lookup_value(gender_id, v, l, i)

        marital_id = await _ensure_lookup_group("medeni_durum", "Medeni Durum", 2)
        for i, (v, l) in enumerate([("bekar", "Bekar"), ("evli", "Evli"), ("dul", "Dul"), ("bosanmis", "Boşanmış")]):
            await _ensure_lookup_value(marital_id, v, l, i)

        cks_id = await _ensure_lookup_group("cks_durumu", "ÇKS Durumu", 3)
        for i, (v, l) in enumerate([("kayitli", "Kayıtlı"), ("kayitsiz", "Kayıtsız"), ("beklemede", "Beklemede")]):
            await _ensure_lookup_value(cks_id, v, l, i)

        debt_id = await _ensure_lookup_group("borc_durumu", "Borç Durumu", 4)
        for i, (v, l) in enumerate([("temiz", "Temiz"), ("borclu", "Borçlu"), ("takipte", "Takipte")]):
            await _ensure_lookup_value(debt_id, v, l, i)

        # (module, field_key, label, field_type, tab, order, extra kwargs)
        FIELDS = [
            ("farmers", "birth_date", "Doğum Tarihi", "date", "Kimlik Bilgileri", 1, {}),
            ("farmers", "gender", "Cinsiyet", "select", "Kimlik Bilgileri", 2, {"lookup_group_id": gender_id}),
            ("farmers", "marital_status", "Medeni Durum", "select", "Kimlik Bilgileri", 3, {"lookup_group_id": marital_id}),
            ("farmers", "tax_no", "Vergi No", "text", "Kimlik Bilgileri", 4, {}),
            ("farmers", "kimlik_fotokopisi", "Kimlik Fotokopisi", "image", "Kimlik Bilgileri", 5,
             {"help_text": "IT-04 — sadece kayıt oluşturulduktan sonra (Düzenle ekranından) yüklenebilir."}),

            ("farmers", "phone_alt", "Alternatif Telefon", "phone", "İletişim", 1, {}),
            ("farmers", "address", "Adres", "textarea", "İletişim", 2, {}),
            ("farmers", "city", "İl", "text", "İletişim", 3, {}),
            ("farmers", "district", "İlçe", "text", "İletişim", 4, {}),

            ("farmers", "cks_no", "ÇKS Kayıt No", "text", "Tarımsal Bilgiler", 1, {}),
            ("farmers", "cks_status", "ÇKS Durumu", "select", "Tarımsal Bilgiler", 2, {"lookup_group_id": cks_id}),
            ("farmers", "isletme_no", "İşletme No", "text", "Tarımsal Bilgiler", 3, {}),
            ("farmers", "cooperative_member", "Kooperatif Üyeliği", "checkbox", "Tarımsal Bilgiler", 4, {}),
            ("farmers", "chamber_member", "Ziraat Odası Üyeliği", "checkbox", "Tarımsal Bilgiler", 5, {}),
            ("farmers", "producer_union", "Üretici Birliği", "text", "Tarımsal Bilgiler", 6, {}),

            ("farmers", "bank_name", "Banka", "text", "Finansal", 1, {}),
            ("farmers", "support_payments_total", "Destek Ödemeleri (Toplam)", "decimal", "Finansal", 2, {}),
            ("farmers", "debt_status", "Borç Durumu", "select", "Finansal", 3, {"lookup_group_id": debt_id}),
            ("farmers", "debt_amount", "Borç Tutarı", "decimal", "Finansal", 4, {}),
            # visible=False: IBAN zaten FarmerDetail'in "Temel Bilgiler" bölümünde
            # ayrı, elle yazılmış bir input olarak var (Sprint A1 öncesi) — burada
            # DynamicFieldsSection'a render ettirmek MÜKERRER alan yaratırdı. Bu
            # satırın TEK amacı field_definitions'a sensitive=True kaydını eklemek;
            # get_sensitive_field_keys() visible'a bakmaz, sadece sensitive+is_active'e bakar.
            ("farmers", "iban", "IBAN", "iban", "Finansal", 5,
             {"sensitive": True, "visible": False,
              "help_text": "IT-07 — Admin ve üzeri sistem katmanı dışında maskeli görünür."}),

            ("farmers", "last_visit_date", "Son Ziyaret", "date", "Operasyon", 1, {}),
            ("farmers", "responsible_personnel", "Sorumlu Personel", "text", "Operasyon", 2, {}),
            ("farmers", "risk_score", "Risk Skoru (AI)", "number", "Operasyon", 3,
             {"help_text": "AI tarafından hesaplanır, elle de girilebilir."}),
        ]
        created = 0
        for module, key, label, ftype, tab, order, extra in FIELDS:
            before = await db.field_definitions.count_documents({"module": module, "field_key": key})
            await _ensure_field_definition(module, key, label=label, field_type=ftype, tab=tab, order=order, **extra)
            if before == 0:
                created += 1

        # IT-08 — Query Engine örneği: birkaç iyi filtre adayı (select/lookup
        # tipli) filterable=True işaretlenir. _upgrade_field_definition
        # kullanılır çünkü bu alanlar yukarıdaki _ensure_field_definition
        # (create-only) ile zaten daha önce oluşturulmuş olabilir.
        for key in ("gender", "cks_status", "debt_status"):
            await _upgrade_field_definition("farmers", key, filterable=True)

        return {"status": "seeded", "new_field_definitions": created, "lookup_groups": ["cinsiyet", "medeni_durum", "cks_durumu", "borc_durumu"]}

    # -----------------------------------------------------------------
    # PİLOT SEED — Parsel modülü (IT-02)
    # -----------------------------------------------------------------
    @api_router.post("/field-definitions/seed-parcels-pilot")
    async def seed_parcels_pilot(user=Depends(require_permission("settings:fields_manage"))):
        """
        IT-02 — Parsel modülü için lookup grupları + field_definitions
        kayıtlarını oluşturur. Idempotent: tekrar çağrılabilir.
        """
        sahiplik_id = await _ensure_lookup_group("sahiplik_durumu", "Sahiplik Durumu", 1)
        for i, (v, l) in enumerate([("sahibi", "Sahibi"), ("kiraci", "Kiracı"),
                                     ("ortakci", "Ortakçı"), ("aile_arazisi", "Aile Arazisi")]):
            await _ensure_lookup_value(sahiplik_id, v, l, i)

        yol_id = await _ensure_lookup_group("yol_durumu", "Yol Durumu", 2)
        for i, (v, l) in enumerate([("asfalt", "Asfalt"), ("stabilize", "Stabilize"),
                                     ("toprak", "Toprak"), ("yok", "Yol Yok")]):
            await _ensure_lookup_value(yol_id, v, l, i)

        su_id = await _ensure_lookup_group("su_kaynagi", "Su Kaynağı", 3)
        for i, (v, l) in enumerate([("sebeke", "Şebeke"), ("kuyu", "Kuyu"),
                                     ("golet", "Gölet"), ("kanal", "Sulama Kanalı"), ("yok", "Yok")]):
            await _ensure_lookup_value(su_id, v, l, i)

        # İl/İlçe — ortak, hiyerarşik lookup (bkz. seed-il-ilce-lookup). Burada
        # sadece grup id'leri alınır (yoksa boş oluşturulur); değerler ayrı
        # endpoint'ten doldurulur, böylece iki seed birbirinden bağımsız
        # sırada çağrılabilir.
        il_id = await _ensure_lookup_group("il", "İl", 4)
        ilce_id = await _ensure_lookup_group("ilce", "İlçe", 5)

        # (module, field_key, label, field_type, tab, order, extra kwargs)
        FIELDS = [
            ("parcels", "ada_no", "Ada No", "text", "Kadastro Bilgileri", 1, {}),
            ("parcels", "parsel_no_tapu", "Parsel No (Tapu)", "text", "Kadastro Bilgileri", 2, {}),
            ("parcels", "il", "İl", "select", "Kadastro Bilgileri", 3, {"lookup_group_id": il_id}),
            ("parcels", "ilce", "İlçe", "select", "Kadastro Bilgileri", 4,
             {"lookup_group_id": ilce_id, "help_text": "Şimdilik sadece Konya ve Ankara ilçeleri dolu."}),
            ("parcels", "mahalle", "Mahalle/Köy", "text", "Kadastro Bilgileri", 5, {}),

            ("parcels", "rakim_m", "Rakım (m)", "number", "Coğrafi Özellikler", 1, {}),
            ("parcels", "egim_yuzde", "Eğim (%)", "decimal", "Coğrafi Özellikler", 2, {}),

            ("parcels", "sahiplik_durumu", "Sahiplik Durumu", "select", "Sahiplik & Kira", 1, {"lookup_group_id": sahiplik_id}),
            ("parcels", "tapu_no", "Tapu No", "text", "Sahiplik & Kira", 2, {}),
            ("parcels", "kira_sozlesmesi_var_mi", "Kira Sözleşmesi Var mı", "checkbox", "Sahiplik & Kira", 3, {}),
            ("parcels", "kira_baslangic", "Kira Başlangıç Tarihi", "date", "Sahiplik & Kira", 4, {}),
            ("parcels", "kira_bitis", "Kira Bitiş Tarihi", "date", "Sahiplik & Kira", 5, {}),
            ("parcels", "kiraci_adi", "Kiracı Adı Soyadı", "text", "Sahiplik & Kira", 6, {}),
            ("parcels", "tapu_belgesi", "Tapu Belgesi", "file", "Sahiplik & Kira", 7,
             {"help_text": "IT-04 — sadece kayıt oluşturulduktan sonra (Düzenle ekranından) yüklenebilir."}),

            ("parcels", "yol_durumu", "Yol Durumu", "select", "Altyapı", 1, {"lookup_group_id": yol_id}),
            ("parcels", "elektrik_baglantisi", "Elektrik Bağlantısı", "checkbox", "Altyapı", 2, {}),
            ("parcels", "su_kaynagi", "Su Kaynağı", "select", "Altyapı", 3, {"lookup_group_id": su_id}),
            ("parcels", "sondaj_kuyu_derinligi_m", "Sondaj Kuyu Derinliği (m)", "decimal", "Altyapı", 4, {}),
        ]
        created = 0
        for module, key, label, ftype, tab, order, extra in FIELDS:
            before = await db.field_definitions.count_documents({"module": module, "field_key": key})
            await _ensure_field_definition(module, key, label=label, field_type=ftype, tab=tab, order=order, **extra)
            if before == 0:
                created += 1

        # Bu seed daha önce "il"/"ilce" text olarak çalıştırılmışsa (IT-02 ilk
        # sürümü), _ensure_field_definition onlara dokunmaz — burada açıkça
        # lookup tipine yükseltiliyor.
        await _upgrade_field_definition("parcels", "il", field_type="select", lookup_group_id=il_id)
        await _upgrade_field_definition("parcels", "ilce", field_type="select", lookup_group_id=ilce_id,
                                         depends_on_field="il",
                                         help_text="Şimdilik sadece Konya ve Ankara ilçeleri dolu. "
                                                    "Önce İl seçilmelidir — İlçe listesi ona göre filtrelenir.")

        return {"status": "seeded", "new_field_definitions": created,
                "lookup_groups": ["sahiplik_durumu", "yol_durumu", "su_kaynagi", "il", "ilce"]}

    # -----------------------------------------------------------------
    # PİLOT SEED — Toprak (Soil Sample) modülü (IT-02)
    # -----------------------------------------------------------------
    @api_router.post("/field-definitions/seed-soil-pilot")
    async def seed_soil_pilot(user=Depends(require_permission("settings:fields_manage"))):
        """
        IT-02 — Toprak analizi modülü için lookup grupları + field_definitions
        kayıtlarını oluşturur. Idempotent: tekrar çağrılabilir.
        """
        tekstur_id = await _ensure_lookup_group("toprak_teksturu", "Toprak Tekstürü", 1)
        for i, (v, l) in enumerate([
            ("kumlu", "Kumlu"), ("tinli", "Tınlı"), ("killi", "Killi"), ("siltli", "Siltli"),
            ("kumlu_tin", "Kumlu-Tın"), ("killi_tin", "Killi-Tın"),
        ]):
            await _ensure_lookup_value(tekstur_id, v, l, i)

        tuzluluk_id = await _ensure_lookup_group("tuzluluk_sinifi", "Tuzluluk Sınıfı", 2)
        for i, (v, l) in enumerate([
            ("tuzsuz", "Tuzsuz"), ("hafif_tuzlu", "Hafif Tuzlu"),
            ("tuzlu", "Tuzlu"), ("cok_tuzlu", "Çok Tuzlu"),
        ]):
            await _ensure_lookup_value(tuzluluk_id, v, l, i)

        # (module, field_key, label, field_type, tab, order, extra kwargs)
        FIELDS = [
            ("soil", "toprak_teksturu", "Toprak Tekstürü", "select", "Fiziksel Özellikler", 1, {"lookup_group_id": tekstur_id}),
            ("soil", "toprak_derinligi_cm", "Toprak Derinliği (cm)", "decimal", "Fiziksel Özellikler", 2, {}),
            ("soil", "taslilik_orani_yuzde", "Taşlılık Oranı (%)", "decimal", "Fiziksel Özellikler", 3, {}),

            ("soil", "tuzluluk_sinifi", "Tuzluluk Sınıfı", "select", "Kimyasal Özellikler", 1,
             {"lookup_group_id": tuzluluk_id, "help_text": "EC ölçümünün (dS/m) yorumlanmış sınıfı."}),
            ("soil", "kirec_orani_yuzde", "Kireç Oranı (%)", "decimal", "Kimyasal Özellikler", 2, {}),

            ("soil", "zn_ppm", "Çinko (Zn, ppm)", "decimal", "Mikro Besin Elementleri", 1, {}),
            ("soil", "fe_ppm", "Demir (Fe, ppm)", "decimal", "Mikro Besin Elementleri", 2, {}),
            ("soil", "bor_ppm", "Bor (B, ppm)", "decimal", "Mikro Besin Elementleri", 3, {}),

            ("soil", "analiz_rapor_no", "Analiz Rapor No", "text", "Rapor & AI", 1, {}),
            ("soil", "ai_yorum", "AI Değerlendirmesi", "textarea", "Rapor & AI", 2,
             {"help_text": "AI tarafından otomatik oluşturulabilir, elle de düzenlenebilir."}),
            ("soil", "ai_risk_skoru", "AI Risk Skoru", "number", "Rapor & AI", 3,
             {"help_text": "0-100 arası, AI tarafından hesaplanır, elle de girilebilir."}),
        ]
        created = 0
        for module, key, label, ftype, tab, order, extra in FIELDS:
            before = await db.field_definitions.count_documents({"module": module, "field_key": key})
            await _ensure_field_definition(module, key, label=label, field_type=ftype, tab=tab, order=order, **extra)
            if before == 0:
                created += 1

        return {"status": "seeded", "new_field_definitions": created,
                "lookup_groups": ["toprak_teksturu", "tuzluluk_sinifi"]}

    # -----------------------------------------------------------------
    # İL / İLÇE LOOKUP ALTYAPISI (hiyerarşik — parent_id ile)
    # -----------------------------------------------------------------
    # Şimdilik sadece Konya ve Ankara dolu. Kalan iller/ilçeler ya bu
    # sözlüğe eklenip endpoint tekrar çağrılarak ya da Lookup Yönetimi
    # ekranından "il" grubuna yeni değer + "ilce" grubuna o değerin id'sini
    # parent_id yapan yeni değerler eklenerek genişletilebilir.
    TR_IL_ILCE = {
        "Konya": [
            "Ahırlı", "Akören", "Akşehir", "Altınekin", "Beyşehir", "Bozkır", "Cihanbeyli",
            "Çeltik", "Çumra", "Derbent", "Derebucak", "Doğanhisar", "Emirgazi", "Ereğli",
            "Güneysınır", "Hadim", "Halkapınar", "Hüyük", "Ilgın", "Kadınhanı", "Karapınar",
            "Karatay", "Kulu", "Meram", "Sarayönü", "Selçuklu", "Seydişehir", "Taşkent",
            "Tuzlukçu", "Yalıhüyük", "Yunak",
        ],
        "Ankara": [
            "Akyurt", "Altındağ", "Ayaş", "Bala", "Beypazarı", "Çamlıdere", "Çankaya",
            "Çubuk", "Elmadağ", "Etimesgut", "Evren", "Gölbaşı", "Güdül", "Haymana",
            "Kalecik", "Kazan", "Keçiören", "Kızılcahamam", "Mamak", "Nallıhan", "Polatlı",
            "Pursaklar", "Sincan", "Şereflikoçhisar", "Yenimahalle",
        ],
    }

    @api_router.post("/field-definitions/seed-il-ilce-lookup")
    async def seed_il_ilce_lookup(user=Depends(require_permission("settings:fields_manage"))):
        """
        İl -> İlçe hiyerarşik lookup verisini hazırlar ("il" ve "ilce"
        lookup grupları; ilçe değerleri kendi ilinin id'sini parent_id
        olarak taşır). Şimdilik sadece Konya ve Ankara dolu — TR_IL_ILCE
        sözlüğüne yeni il eklenip bu endpoint tekrar çağrılarak (idempotent)
        genişletilebilir. `seed-parcels-pilot` bu grupları zaten referans
        alıyor; sıra önemli değildir, hangisi önce çalışırsa boş grubu
        oluşturur, diğeri değerleri doldurur.

        IT-01.5: "ilce" grubu artık "il"i formel olarak `parent_group_id`
        ile üst grup işaretler (bu çağrı her seferinde tekrar set eder,
        zararsız — bu iterasyondan ÖNCE oluşmuş "ilce" grupları da böylece
        geriye dönük olarak işaretlenmiş olur, ayrı bir migration script'i
        gerekmez).
        """
        il_id = await _ensure_lookup_group("il", "İl", 4)
        ilce_id = await _ensure_lookup_group("ilce", "İlçe", 5)
        await _upgrade_lookup_group("ilce", parent_group_id=il_id)

        created_il = 0
        created_ilce = 0
        for il_order, (il_name, ilceler) in enumerate(TR_IL_ILCE.items()):
            before = await db.lookup_values.count_documents({"group_id": il_id, "value": il_name, "parent_id": None})
            il_value_id = await _ensure_lookup_value(il_id, il_name, il_name, il_order)
            if before == 0:
                created_il += 1
            for ilce_order, ilce_name in enumerate(ilceler):
                before = await db.lookup_values.count_documents(
                    {"group_id": ilce_id, "value": ilce_name, "parent_id": il_value_id}
                )
                await _ensure_lookup_value(ilce_id, ilce_name, ilce_name, ilce_order, parent_id=il_value_id)
                if before == 0:
                    created_ilce += 1

        return {
            "status": "seeded", "new_il": created_il, "new_ilce": created_ilce,
            "lookup_groups": ["il", "ilce"],
            "note": "Şimdilik sadece Konya ve Ankara dolu. Diğer iller TR_IL_ILCE "
                    "sözlüğüne eklenip bu endpoint tekrar çağrılarak veya Lookup "
                    "Yönetimi ekranından elle eklenebilir.",
        }

    # -----------------------------------------------------------------
    # PİLOT SEED — Sözleşme modülü (IT-03)
    # -----------------------------------------------------------------
    @api_router.post("/field-definitions/seed-contracts-pilot")
    async def seed_contracts_pilot(user=Depends(require_permission("settings:fields_manage"))):
        """
        IT-03 — Sözleşme modülü için lookup grupları + field_definitions
        kayıtlarını oluşturur. Idempotent: tekrar çağrılabilir.
        """
        turu_id = await _ensure_lookup_group("sozlesme_turu", "Sözleşme Türü", 6)
        for i, (v, l) in enumerate([("bireysel", "Bireysel"), ("kooperatif", "Kooperatif"), ("ortak", "Ortak Üretim")]):
            await _ensure_lookup_value(turu_id, v, l, i)

        nakliye_id = await _ensure_lookup_group("nakliye_sorumlusu", "Nakliye Sorumlusu", 7)
        for i, (v, l) in enumerate([("ciftci", "Çiftçi"), ("fabrika", "Fabrika"), ("kooperatif", "Kooperatif")]):
            await _ensure_lookup_value(nakliye_id, v, l, i)

        # (module, field_key, label, field_type, tab, order, extra kwargs)
        FIELDS = [
            ("contracts", "sozlesme_turu", "Sözleşme Türü", "select", "Sözleşme Türü & Taraflar", 1, {"lookup_group_id": turu_id}),
            ("contracts", "fabrika_temsilcisi", "Fabrika Temsilcisi", "text", "Sözleşme Türü & Taraflar", 2, {}),
            ("contracts", "noter_onayli_mi", "Noter Onaylı mı", "checkbox", "Sözleşme Türü & Taraflar", 3, {}),
            ("contracts", "imza_tarihi", "İmza Tarihi", "date", "Sözleşme Türü & Taraflar", 4, {}),

            ("contracts", "prim_orani_yuzde", "Prim Oranı (%)", "decimal", "Prim & Kesinti", 1, {}),
            ("contracts", "prim_tutari", "Prim Tutarı (₺)", "decimal", "Prim & Kesinti", 2, {}),
            ("contracts", "kesinti_orani_yuzde", "Kesinti Oranı (%)", "decimal", "Prim & Kesinti", 3, {}),
            ("contracts", "kesinti_aciklama", "Kesinti Açıklaması", "text", "Prim & Kesinti", 4, {}),

            ("contracts", "teslim_fabrika", "Teslim Fabrikası", "text", "Fabrika Teslim", 1, {}),
            ("contracts", "teslim_tarihi_planlanan", "Planlanan Teslim Tarihi", "date", "Fabrika Teslim", 2, {}),
            ("contracts", "nakliye_sorumlusu", "Nakliye Sorumlusu", "select", "Fabrika Teslim", 3, {"lookup_group_id": nakliye_id}),
        ]
        created = 0
        for module, key, label, ftype, tab, order, extra in FIELDS:
            before = await db.field_definitions.count_documents({"module": module, "field_key": key})
            await _ensure_field_definition(module, key, label=label, field_type=ftype, tab=tab, order=order, **extra)
            if before == 0:
                created += 1

        return {"status": "seeded", "new_field_definitions": created,
                "lookup_groups": ["sozlesme_turu", "nakliye_sorumlusu"]}

    # -----------------------------------------------------------------
    # PİLOT SEED — Ekim Planlama modülü (IT-03)
    # -----------------------------------------------------------------
    @api_router.post("/field-definitions/seed-plantings-pilot")
    async def seed_plantings_pilot(user=Depends(require_permission("settings:fields_manage"))):
        """
        IT-03 — Ekim Planlama modülü için lookup grupları + field_definitions
        kayıtlarını oluşturur. Idempotent: tekrar çağrılabilir.
        """
        yontem_id = await _ensure_lookup_group("ekim_yontemi", "Ekim Yöntemi", 8)
        for i, (v, l) in enumerate([("serpme", "Serpme"), ("sira", "Sıraya"), ("damla_ekim", "Damla Ekim Hattı ile")]):
            await _ensure_lookup_value(yontem_id, v, l, i)

        # (module, field_key, label, field_type, tab, order, extra kwargs)
        FIELDS = [
            ("plantings", "tohum_kaynagi", "Tohum Kaynağı/Tedarikçi", "text", "Tohum & Ekim Detayı", 1, {}),
            ("plantings", "tohum_parti_no", "Tohum Parti No", "text", "Tohum & Ekim Detayı", 2, {}),
            ("plantings", "tohum_miktari_kg", "Tohum Miktarı (kg)", "decimal", "Tohum & Ekim Detayı", 3, {}),
            ("plantings", "ekim_yontemi", "Ekim Yöntemi", "select", "Tohum & Ekim Detayı", 4, {"lookup_group_id": yontem_id}),

            ("plantings", "sira_araligi_cm", "Sıra Aralığı (cm)", "decimal", "Takvim", 1, {}),
            ("plantings", "sulama_plani_baslangic", "Sulama Planı Başlangıç", "date", "Takvim", 2, {}),
            ("plantings", "gubreleme_plani_tarihi", "Gübreleme Planı Tarihi", "date", "Takvim", 3, {}),

            ("plantings", "planlanan_makine", "Planlanan Makine/Ekipman", "text", "Kaynak Planlama", 1, {}),
            ("plantings", "planlanan_isci_sayisi", "Planlanan İşçi Sayısı", "number", "Kaynak Planlama", 2, {}),
            ("plantings", "kaynak_notu", "Kaynak Planlama Notu", "textarea", "Kaynak Planlama", 3, {}),
        ]
        created = 0
        for module, key, label, ftype, tab, order, extra in FIELDS:
            before = await db.field_definitions.count_documents({"module": module, "field_key": key})
            await _ensure_field_definition(module, key, label=label, field_type=ftype, tab=tab, order=order, **extra)
            if before == 0:
                created += 1

        return {"status": "seeded", "new_field_definitions": created, "lookup_groups": ["ekim_yontemi"]}

    @api_router.post("/field-definitions/seed-admin-areas-pilot")
    async def seed_admin_areas_pilot(user=Depends(require_permission("settings:fields_manage"))):
        """
        IT-13.6 — İdari Alan (admin_areas) modülü için field_definitions
        kayıtlarını oluşturur (demografi alanları). Lookup grubu gerekmez —
        il/ilçe isimleri zaten seed_il_ilce_lookup'ta (tek kaynak ilkesi).
        Idempotent: tekrar çağrılabilir.
        """
        FIELDS = [
            ("admin_areas", "population", "Nüfus", "number", "Demografi", 1, {}),
            ("admin_areas", "agricultural_area_dekar", "Tarım Alanı (dekar)", "decimal", "Demografi", 2, {}),
            ("admin_areas", "farmer_count_est", "Tahmini Çiftçi Sayısı", "number", "Demografi", 3, {}),
        ]
        created = 0
        for module, key, label, ftype, tab, order, extra in FIELDS:
            before = await db.field_definitions.count_documents({"module": module, "field_key": key})
            await _ensure_field_definition(module, key, label=label, field_type=ftype, tab=tab, order=order, **extra)
            if before == 0:
                created += 1

        return {"status": "seeded", "new_field_definitions": created}
