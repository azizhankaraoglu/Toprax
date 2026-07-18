"""
=====================================================================
Toprax — Universal Query & Filter Engine, çekirdek (IT-08)
=====================================================================
Modül bazlı liste ekranlarının (Çiftçi/Parsel/Sözleşme/Ekim Planlama/
Toprak/Üretim Sezonu) tek bir generic sorgu ucuna indirgenmesini
sağlar: alan+operatör+değer koşulları (tek seviye AND/OR), server-side
sayfalama/sıralama/projection.

Filtre paneli UI'sı (liste ekranlarına genel filtre bileşeni) ve
Kayıtlı Sorgular/Favoriler IT-09'un kapsamıdır — bu modül SADECE
backend çekirdeğidir (IT-05'in production_cycles.py'de backend/UI
ayrımı yapması gibi).

Güvenlik: filtre/sıralama/projection edilebilecek alanlar İKİ
kaynaktan whitelist'lenir — keyfi bir `field` string'i asla doğrudan
Mongo sorgusuna sızmaz:
  1. CORE_FILTERABLE_FIELDS — modülün Sprint A1 öncesi "temel" (gerçek
     Pydantic model) alanlarından elle seçilmiş, sorgulanması mantıklı
     bir alt küme. Bilinçli olarak DIŞARIDA bırakılanlar: iban gibi
     field_definitions'ta sensitive=True olan alanlar (bkz. IT-07).
  2. field_definitions'ta filterable=True işaretlenmiş satırlar (Form
     Yönetimi ekranından yönetici tarafından genişletilebilir —
     field_definitions.py'deki `sensitive` bayrağıyla AYNI desen,
     bkz. get_filterable_field_defs()).
Bu whitelist dışındaki bir `field`/`sort_by`/`fields` projection
girişi 400 ile reddedilir.

Sonuçlara ayrıca IT-07'nin mask_sensitive_fields_many'i uygulanır —
bir alan hem filterable hem sensitive işaretlenmiş olsa bile (ör.
ileride biri iban'ı filtrelenebilir de yaparsa) ham değer sızmaz.
"""
import re
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Any, List, Optional

from field_definitions import get_filterable_field_defs, mask_sensitive_fields_many

# =====================================================================
# MODÜL KAYDI — sorgulanabilir modüller, gerçek Mongo koleksiyonu ve
# görüntüleme izni. field_definitions modülleriyle (MODULE_LABELS)
# BİREBİR AYNI DEĞİL — production_cycles field_definitions'ta yok ama
# Query Engine'de sorgulanabilir olmalı (ikinci omurga, bkz. CLAUDE.md).
# =====================================================================
MODULE_COLLECTIONS = {
    "farmers": "farmers",
    "parcels": "parcels",
    "contracts": "contracts",
    "plantings": "plantings",
    "soil": "soil_samples",
    "production_cycles": "production_cycles",
    "admin_areas": "admin_areas",
    "field_tasks": "field_tasks",
    "visits": "visits",
    # IT-29 — LMS Segment atamasının "users" hedefini (personel/rol bazlı
    # eğitim ataması) Query Engine üzerinden yapabilmesi için.
    "users": "users",
    # IT-47 — AI Bilgi Kütüphanesi araması KENDİ motorunu yazmaz; Query
    # Engine'in genişletilmiş MODULE_COLLECTIONS'ına girer.
    "ai_knowledge_records": "ai_knowledge_records",
}

MODULE_PERMISSIONS = {
    "farmers": "farmers:view",
    "parcels": "parcels:view",
    "contracts": "contracts:view",
    "plantings": "plantings:view",
    "soil": "soil:view",
    "production_cycles": "production_cycles:view",
    "admin_areas": "admin_areas:view",
    # IT-24 — field_ops.py'nin (IT-22) field_tasks/visits koleksiyonları,
    # Saha Raporları ekranının SmartDataGrid ile filtreleyebilmesi için.
    "field_tasks": "field_ops:view",
    "visits": "field_ops:view",
    "users": "settings:users_view",
    "ai_knowledge_records": "ai_knowledge:view",
}
# (FAZ 18 IT-47 kaydı — ai_knowledge_records Query Engine'e bağlandı)

# field_definitions'a sahip modüller — sadece bunlar için filterable
# field_definitions satırları + Field-Level Security maskesi sorgulanır.
FIELD_DEFINITIONS_MODULES = {"farmers", "parcels", "contracts", "plantings", "soil", "admin_areas"}

# IT-29 — "users" modülünde field_definitions/sensitive mekanizması yok,
# ama `password` (hash de olsa) projection verilmeden ASLA dönmemeli —
# `fields` parametresi boşsa varsayılan projection'dan elle çıkarılır
# (aşağıdaki execute_query'de kullanılır).
DEFAULT_EXCLUDED_FIELDS = {"users": {"password"}}

# Modülün Sprint A1 öncesi "temel" (kod-seviyesi Pydantic) alanlarından
# elle seçilmiş, sorgulanması mantıklı bir alt küme. field_definitions'a
# taşınmamış alanlar (full_name, status, season, ph vb.) buradan gelir.
CORE_FILTERABLE_FIELDS = {
    "farmers": [
        {"key": "full_name", "label": "Ad Soyad", "type": "text"},
        {"key": "tc_no", "label": "TC Kimlik No", "type": "text"},
        {"key": "phone", "label": "Telefon", "type": "text"},
        {"key": "email", "label": "E-posta", "type": "text"},
        {"key": "village", "label": "Köy", "type": "text"},
        {"key": "region_id", "label": "Bölge", "type": "text"},
        {"key": "status", "label": "Durum", "type": "text"},
        {"key": "karne_score", "label": "Karne Skoru", "type": "text"},
        {"key": "membership_year", "label": "Üyelik Yılı", "type": "number"},
        {"key": "member_no", "label": "Üye No", "type": "text"},
    ],
    "parcels": [
        {"key": "name", "label": "Parsel Adı", "type": "text"},
        {"key": "farmer_id", "label": "Çiftçi", "type": "text"},
        {"key": "village", "label": "Köy", "type": "text"},
        {"key": "region_id", "label": "Bölge", "type": "text"},
        {"key": "area_dekar", "label": "Alan (dekar)", "type": "number"},
        {"key": "soil_type", "label": "Toprak Tipi", "type": "text"},
        {"key": "irrigation", "label": "Sulama", "type": "text"},
        # IT-10 — AI Copilot köprüsü (extras.py) bu üç alanı da sorgular;
        # ParcelCreate Pydantic modelinde YOK (extras.py'nin simüle uydu/AI
        # özelliği parsel dokümanına doğrudan yazıyor, bkz. CLAUDE.md
        # "extras.py'deki AI/uydu/IoT verileri SİMÜLEDİR") — yine de gerçek
        # doküman alanları oldukları için burada filtrelenebilir/sıralanabilir.
        {"key": "ndvi_latest", "label": "NDVI (son ölçüm)", "type": "number"},
        {"key": "risk_level", "label": "Risk Seviyesi", "type": "text"},
        {"key": "expected_yield_ton", "label": "Beklenen Verim (ton)", "type": "number"},
        # #2 — ekili/söküm durumu (uydu+manuel) + ekilebilir alan
        {"key": "ekim_durumu", "label": "Ekim Durumu (ekili/sokuldu/ekili_degil)", "type": "text"},
        {"key": "son_ndvi", "label": "Son NDVI (ekim durumu)", "type": "number"},
        {"key": "ekilebilir_alan_dekar", "label": "Ekilebilir Alan (dekar)", "type": "number"},
        # "Her bilgisiyle sorgulanabilsin" — IT-02'nin gerçek parsel kolonları
        # (kadastro/coğrafi/sahiplik/altyapı) + uzaktan algılama son NDVI'si.
        # Bunlar doğrudan doküman alanı olduğundan filtre/sıralamada güvenli.
        {"key": "parcel_code", "label": "Parsel Kodu", "type": "text"},
        {"key": "current_crop", "label": "Mevcut Ürün", "type": "text"},
        {"key": "active_season", "label": "Aktif Sezon (Yıl)", "type": "number"},
        {"key": "ada_no", "label": "Ada No", "type": "text"},
        {"key": "parsel_no_tapu", "label": "Parsel No (Tapu)", "type": "text"},
        {"key": "il", "label": "İl", "type": "text"},
        {"key": "ilce", "label": "İlçe", "type": "text"},
        {"key": "mahalle", "label": "Mahalle/Köy", "type": "text"},
        {"key": "rakim_m", "label": "Rakım (m)", "type": "number"},
        {"key": "egim_yuzde", "label": "Eğim (%)", "type": "number"},
        {"key": "sahiplik_durumu", "label": "Sahiplik Durumu", "type": "text"},
        {"key": "tapu_no", "label": "Tapu No", "type": "text"},
        {"key": "yol_durumu", "label": "Yol Durumu", "type": "text"},
        {"key": "su_kaynagi", "label": "Su Kaynağı", "type": "text"},
        {"key": "remote_sensing.last_ndvi", "label": "Uzaktan Algılama NDVI", "type": "number"},
        {"key": "remote_sensing.last_image_date", "label": "Son Uydu Görüntü Tarihi", "type": "text"},
    ],
    "contracts": [
        {"key": "farmer_id", "label": "Çiftçi", "type": "text"},
        {"key": "parcel_id", "label": "Parsel", "type": "text"},
        {"key": "season", "label": "Sezon (Yıl)", "type": "number"},
        {"key": "crop", "label": "Ürün", "type": "text"},
        {"key": "variety", "label": "Çeşit", "type": "text"},
        {"key": "status", "label": "Durum", "type": "text"},
        {"key": "kota_ton", "label": "Kota (ton)", "type": "number"},
    ],
    "plantings": [
        {"key": "farmer_id", "label": "Çiftçi", "type": "text"},
        {"key": "parcel_id", "label": "Parsel", "type": "text"},
        {"key": "season", "label": "Sezon (Yıl)", "type": "number"},
        {"key": "crop", "label": "Ürün", "type": "text"},
        {"key": "variety", "label": "Çeşit", "type": "text"},
        {"key": "stage", "label": "Aşama", "type": "text"},
    ],
    "soil": [
        {"key": "parcel_id", "label": "Parsel", "type": "text"},
        {"key": "date", "label": "Tarih", "type": "date"},
        {"key": "lab_name", "label": "Laboratuvar", "type": "text"},
        {"key": "ph", "label": "pH", "type": "number"},
        {"key": "ec", "label": "EC (dS/m)", "type": "number"},
        {"key": "organic_matter_pct", "label": "Organik Madde %", "type": "number"},
        {"key": "n_ppm", "label": "N (ppm)", "type": "number"},
        {"key": "p_ppm", "label": "P (ppm)", "type": "number"},
        {"key": "k_ppm", "label": "K (ppm)", "type": "number"},
        {"key": "recommendation", "label": "Öneri", "type": "text"},
    ],
    "production_cycles": [
        {"key": "farmer_id", "label": "Çiftçi", "type": "text"},
        {"key": "parcel_id", "label": "Parsel", "type": "text"},
        {"key": "year", "label": "Yıl", "type": "number"},
        {"key": "season", "label": "Sezon", "type": "text"},
        {"key": "crop", "label": "Ürün", "type": "text"},
        {"key": "status", "label": "Durum", "type": "text"},
    ],
    "admin_areas": [
        {"key": "name", "label": "Ad", "type": "text"},
        {"key": "area_type", "label": "Tip", "type": "text"},
        {"key": "parent_id", "label": "Üst Alan", "type": "text"},
        {"key": "population", "label": "Nüfus", "type": "number"},
        {"key": "agricultural_area_dekar", "label": "Tarım Alanı (dekar)", "type": "number"},
        {"key": "farmer_count_est", "label": "Tahmini Çiftçi Sayısı", "type": "number"},
    ],
    # IT-24 — Saha Raporları (field_ops.py'nin IT-22 modeli).
    # IT-29 — LMS'in "Segment" atama hedefi (rol/e-posta/ad bazlı personel
    # segmentasyonu) için. `password` BİLİNÇLİ OLARAK burada YOK (whitelist
    # dışı alan asla filtrelenemez/projection'a giremez — IT-08'in temel
    # güvenlik kuralı, bkz. modül docstring'i).
    "users": [
        {"key": "full_name", "label": "Ad Soyad", "type": "text"},
        {"key": "email", "label": "E-posta", "type": "text"},
        {"key": "phone", "label": "Telefon", "type": "text"},
        {"key": "role", "label": "Rol", "type": "text"},
        {"key": "active", "label": "Aktif mi", "type": "text"},
    ],
    "field_tasks": [
        {"key": "task_type_id", "label": "Görev Tipi", "type": "text"},
        {"key": "assigned_to", "label": "Atanan Personel", "type": "text"},
        {"key": "status", "label": "Durum", "type": "text"},
        {"key": "priority", "label": "Öncelik", "type": "text"},
        {"key": "farmer_id", "label": "Çiftçi", "type": "text"},
        {"key": "parcel_id", "label": "Parsel", "type": "text"},
        {"key": "production_cycle_id", "label": "Üretim Sezonu", "type": "text"},
        {"key": "work_order_id", "label": "İş Emri", "type": "text"},
        {"key": "planned_date", "label": "Planlanan Tarih", "type": "date"},
        {"key": "sla_due_date", "label": "SLA Bitiş", "type": "date"},
    ],
    "visits": [
        {"key": "task_id", "label": "Görev", "type": "text"},
        {"key": "farmer_id", "label": "Çiftçi", "type": "text"},
        {"key": "parcel_id", "label": "Parsel", "type": "text"},
        {"key": "production_cycle_id", "label": "Üretim Sezonu", "type": "text"},
        {"key": "task_type_id", "label": "Görev Tipi", "type": "text"},
        {"key": "started_at", "label": "Başlangıç", "type": "date"},
        {"key": "ended_at", "label": "Bitiş", "type": "date"},
    ],
    # IT-47 — AI Bilgi Kütüphanesi (Knowledge Search) filtre şeması.
    "ai_knowledge_records": [
        {"key": "dataset_id", "label": "Dataset", "type": "text"},
        {"key": "object_type", "label": "Nesne Tipi", "type": "text"},
        {"key": "approval_status", "label": "Onay Durumu", "type": "text"},
        {"key": "source_type", "label": "Kaynak", "type": "text"},
        {"key": "parcel_id", "label": "Parsel", "type": "text"},
        {"key": "production_cycle_id", "label": "Üretim Sezonu", "type": "text"},
        {"key": "farmer_id", "label": "Çiftçi", "type": "text"},
        {"key": "quality_score", "label": "Kalite Skoru", "type": "number"},
        {"key": "version", "label": "Versiyon", "type": "number"},
    ],
}

ALLOWED_OPERATORS = {
    "eq", "ne", "gt", "gte", "lt", "lte", "contains", "in", "between", "is_null", "is_not_null",
}

# IT-10 — Global arama (tek kutu): her modülde "içerir" ile taranacak metin
# alanları. CORE_FILTERABLE_FIELDS'ın bir alt kümesi — sadece insan
# tarafından yazılıp arandığı düşünülebilecek alanlar (ör. farmer_id gibi
# UUID'ler burada yok, kimse UUID yazıp aramaz).
GLOBAL_SEARCH_FIELDS = {
    "farmers": ["full_name", "tc_no", "phone", "member_no", "village"],
    "parcels": ["name", "village"],
    "contracts": ["crop", "variety"],
    "production_cycles": ["season", "crop"],
}


class FilterCondition(BaseModel):
    field: str
    operator: str
    value: Any = None


class SortSpec(BaseModel):
    """IT-11 — SmartDataGrid'in çoklu sıralaması için. `sort` verilirse
    `sort_by`/`sort_dir` (IT-08'in tek alanlı, geriye dönük uyumlu sözleşmesi)
    YOK SAYILIR."""
    field: str
    dir: str = "asc"                           # asc | desc


class QueryRequest(BaseModel):
    filters: List[FilterCondition] = []
    logic: str = "AND"                        # AND | OR — tek seviye (v1, nested grup yok)
    sort_by: Optional[str] = None             # legacy tek-alan sıralama (IT-08, geriye uyumlu)
    sort_dir: str = "asc"                      # asc | desc
    sort: Optional[List[SortSpec]] = None      # IT-11 — çoklu sıralama, verilirse sort_by'a öncelikli
    page: int = 1
    page_size: int = 50
    fields: Optional[List[str]] = None         # projection — boşsa tüm alanlar döner


def _build_condition(field_key: str, operator: str, value: Any) -> dict:
    if operator == "eq":
        return {field_key: value}
    if operator == "ne":
        return {field_key: {"$ne": value}}
    if operator == "gt":
        return {field_key: {"$gt": value}}
    if operator == "gte":
        return {field_key: {"$gte": value}}
    if operator == "lt":
        return {field_key: {"$lt": value}}
    if operator == "lte":
        return {field_key: {"$lte": value}}
    if operator == "contains":
        return {field_key: {"$regex": re.escape(str(value)), "$options": "i"}}
    if operator == "in":
        if not isinstance(value, list):
            raise HTTPException(400, f"'{field_key}' için 'in' operatörü liste değer gerektirir")
        return {field_key: {"$in": value}}
    if operator == "between":
        if not (isinstance(value, list) and len(value) == 2):
            raise HTTPException(400, f"'{field_key}' için 'between' operatörü [min, max] gerektirir")
        return {field_key: {"$gte": value[0], "$lte": value[1]}}
    if operator == "is_null":
        return {"$or": [{field_key: None}, {field_key: {"$exists": False}}]}
    if operator == "is_not_null":
        return {field_key: {"$ne": None, "$exists": True}}
    raise HTTPException(400, f"Bilinmeyen operatör: {operator}")


async def get_filterable_map(db, module: str) -> dict:
    """key -> {key, label, type} — CORE + field_definitions(filterable=True) birleşimi.
    Modül dışındaki register_query_routes çağıranların (ör. extras.py'nin AI
    Copilot köprüsü, IT-10) da kullanabilmesi için modül seviyesinde tutulur."""
    result = {f["key"]: f for f in CORE_FILTERABLE_FIELDS.get(module, [])}
    if module in FIELD_DEFINITIONS_MODULES:
        for f in await get_filterable_field_defs(db, module):
            result[f["key"]] = f
    return result


async def execute_query(
    db, module: str, user: dict, filters: List[dict],
    logic: str = "AND", sort_by: Optional[str] = None, sort_dir: str = "asc",
    sort: Optional[List[dict]] = None,
    page: int = 1, page_size: int = 50, fields: Optional[List[str]] = None,
) -> dict:
    """
    Query Engine'in çekirdeği — hem `POST /query/{module}` hem de dışarıdan
    (ör. extras.py'nin AI Copilot'u, IT-10) doğrudan çağrılabilir. `filters`
    düz dict listesidir: `[{"field": ..., "operator": ..., "value": ...}, ...]`
    (FilterCondition.model_dump() veya elle kurulmuş dict, ikisi de kabul edilir).

    Aynı whitelist/izin/maskeleme kuralları HER çağıran için geçerlidir —
    AI Copilot'un ürettiği filtre de dahil, keyfi alan/operatör giremez.
    """
    if module not in MODULE_COLLECTIONS:
        raise HTTPException(404, f"Bilinmeyen modül: {module}")

    from permissions import get_effective_permissions
    perm_key = MODULE_PERMISSIONS[module]
    perms = await get_effective_permissions(user, db)
    if perm_key not in perms:
        raise HTTPException(403, f"'{perm_key}' yetkiniz yok")

    filterable = await get_filterable_map(db, module)

    conditions = []
    for f in filters:
        field_key, operator, value = f["field"], f["operator"], f.get("value")
        if field_key not in filterable:
            raise HTTPException(400, f"'{field_key}' bu modülde filtrelenebilir değil")
        if operator not in ALLOWED_OPERATORS:
            raise HTTPException(400, f"Bilinmeyen operatör: {operator}")
        conditions.append(_build_condition(field_key, operator, value))

    # Soft-delete edilen (is_active=False) kayıtlar HİÇBİR modülde sorguya
    # girmez — is_active alanı olmayan (eski) kayıtlar {"$ne": False} ile
    # kapsanır, bu yüzden tüm modüller için güvenli.
    soft_delete_guard = {"is_active": {"$ne": False}}
    if not conditions:
        mongo_query: dict = soft_delete_guard
    elif logic.upper() == "OR":
        mongo_query = {"$and": [soft_delete_guard, {"$or": conditions}]}
    else:
        mongo_query = {"$and": [soft_delete_guard, *conditions]}

    projection = {"_id": 0, **{f: 0 for f in DEFAULT_EXCLUDED_FIELDS.get(module, set())}}
    if fields:
        invalid = [f for f in fields if f not in filterable and f != "id"]
        if invalid:
            raise HTTPException(400, f"Geçersiz projection alanı: {invalid}")
        projection = {"_id": 0, "id": 1, **{f: 1 for f in fields}}

    # IT-11 — çoklu sıralama `sort` verilmişse `sort_by`/`sort_dir`'a önceliklidir.
    sort_pairs: List[tuple] = []
    if sort:
        for s in sort:
            field_key = s["field"] if isinstance(s, dict) else s.field
            direction = (s["dir"] if isinstance(s, dict) else s.dir)
            if field_key not in filterable and field_key != "id":
                raise HTTPException(400, f"'{field_key}' ile sıralanamaz")
            sort_pairs.append((field_key, 1 if direction != "desc" else -1))
    elif sort_by:
        if sort_by not in filterable and sort_by != "id":
            raise HTTPException(400, f"'{sort_by}' ile sıralanamaz")
        sort_pairs.append((sort_by, 1 if sort_dir != "desc" else -1))

    page = max(1, page)
    page_size = min(max(1, page_size), 500)

    collection = getattr(db, MODULE_COLLECTIONS[module])
    total = await collection.count_documents(mongo_query)
    cursor = collection.find(mongo_query, projection)
    if sort_pairs:
        cursor = cursor.sort(sort_pairs)
    cursor = cursor.skip((page - 1) * page_size).limit(page_size)
    items = await cursor.to_list(page_size)

    if module in FIELD_DEFINITIONS_MODULES:
        items = await mask_sensitive_fields_many(db, module, items, user)

    return {"items": items, "total": total, "page": page, "page_size": page_size}


def register_query_routes(api_router, db, current_user, require_permission, log_audit):
    """server.py'deki register_* pattern'i — db, TenantScopedDB (tenant izolasyonu otomatik)."""

    @api_router.get("/query/{module}/filterable-fields")
    async def filterable_fields(module: str, user=Depends(current_user)):
        """Filtre panelini (IT-09) besleyecek meta uç — hangi alan hangi tiple filtrelenebilir."""
        if module not in MODULE_COLLECTIONS:
            raise HTTPException(404, f"Bilinmeyen modül: {module}")
        fields = await get_filterable_map(db, module)
        return {"module": module, "fields": sorted(fields.values(), key=lambda f: f["label"])}

    @api_router.post("/query/{module}")
    async def run_query(module: str, body: QueryRequest, request: Request, user=Depends(current_user)):
        filters = [f.model_dump() for f in body.filters]
        sort = [s.model_dump() for s in body.sort] if body.sort else None
        return await execute_query(
            db, module, user, filters, logic=body.logic, sort_by=body.sort_by,
            sort_dir=body.sort_dir, sort=sort, page=body.page, page_size=body.page_size, fields=body.fields,
        )

    @api_router.get("/search")
    async def global_search(q: str, limit: int = 5, user=Depends(current_user)):
        """
        IT-10 — Tek kutu global arama: çiftçi/parsel/sözleşme/üretim sezonu
        modüllerinde GLOBAL_SEARCH_FIELDS'taki metin alanlarında OR + contains
        araması yapar. Kullanıcının görüntüleme yetkisi olmayan bir modül
        sessizce ATLANIR (arama tümden 403 olmaz, sadece o modül boş döner).
        """
        q = q.strip()
        if len(q) < 2:
            return {"query": q, "results": {}}

        from permissions import get_effective_permissions
        perms = await get_effective_permissions(user, db)

        results = {}
        for module, search_fields in GLOBAL_SEARCH_FIELDS.items():
            if MODULE_PERMISSIONS[module] not in perms:
                continue
            filters = [{"field": f, "operator": "contains", "value": q} for f in search_fields]
            try:
                res = await execute_query(db, module, user, filters, logic="OR", page=1, page_size=limit)
            except HTTPException:
                continue
            if res["total"] > 0:
                results[module] = res

        return {"query": q, "results": results}
