"""
=====================================================================
Toprax — Yönetilebilir Sabit Katalogları (2026-08-19)
=====================================================================
Kullanıcı isteği: *"geçmiş oturum yaptığın her geliştirmenin sabitlerini ya da
lookup verilerini (Ör: Tespit Edilen Organizmalar) admin tarafımdan
eklenebilir / değiştirilebilir / silinebilir olmalı."*

**Sorun.** Platformda iki farklı "sabit veri" dünyası var:
  1. `lookup_groups` / `lookup_values` (field_definitions.py) — form dropdown'ları,
     zaten Lookup Yönetimi ekranından tam yönetilebiliyor.
  2. **Kod-seviyesi registry'ler** — `soil_biology.ORGANISM_CATALOG`,
     `MEASUREMENT_SPEC` gibi. Bunlar sadece bir etiket listesi DEĞİL: skor
     ağırlıkları, eşik değerleri, "engelleyici mi" bayrakları taşıyorlar,
     yani motorların davranışını belirliyorlar. Lookup sistemine sığmıyorlar
     (lookup_values yalnızca value/label/parent tutar) ve şu ana kadar
     yalnızca kod değiştirilerek güncellenebiliyorlardı.

**Çözüm — kod varsayılanı + DB katmanı (override).** Kod sabiti VARSAYILAN
olarak kalır (yeni kurulumda seed gerekmez, sistem her zaman çalışır); admin'in
yaptığı ekleme/düzenleme/silme `managed_catalog_items` koleksiyonuna yazılır ve
okuma anında kodun üzerine BİNDİRİLİR:

    get_catalog(db, "soil_organisms")
      → kod varsayılanları
        ∪ DB'de aynı `key` ile kayıtlı override'lar (alan bazında birleşir)
        ∪ DB'de eklenmiş TAMAMEN yeni kayıtlar
        ∖ DB'de `is_active=False` yapılmış (silinmiş) kayıtlar

`platform_core.FEATURE_FLAG_LABELS`'ın "kod-seviyesi registry" felsefesiyle
ÇELİŞMEZ: orada anahtar kümesi sabit olmalıydı (kod o anahtarlara göre dallanır);
burada ise katalog zaten VERİ — motor kalemleri tek tek bilmez, listeyi gezer.

**Silme:** convention #3 (soft delete) uygulanır. Kod varsayılanı fiziksel
olarak silinemez zaten — DB'ye `is_active: False` bir "gölge kayıt" yazılır;
"Varsayılana Döndür" bu gölgeyi kaldırır ve kalem geri gelir.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel


# =====================================================================
# REGISTRY — hangi katalog yönetilebilir, alanları ne
# =====================================================================
# `fields`: admin formunun üreteceği alanlar. `type`: text | number | select | bool
# `defaults_from`: (modül, değişken) — kod varsayılanlarının okunacağı yer.
CATALOG_REGISTRY: Dict[str, Dict[str, Any]] = {
    "soil_organisms": {
        "label": "Toprak Biyolojisi — Tespit Edilen Organizmalar",
        "description": "Saha/lab kaydında işaretlenebilen organizmalar ve skora etkileri.",
        "defaults_from": ("soil_biology", "ORGANISM_CATALOG"),
        "fields": [
            {"key": "key", "label": "Sistem Anahtarı", "type": "text", "required": True, "immutable": True},
            {"key": "label", "label": "Görünen Ad", "type": "text", "required": True},
            {"key": "grup", "label": "Grup", "type": "select",
             "options": ["bakteri", "mantar", "nematod", "makrofauna", "mikrofauna", "diger"]},
            {"key": "etki", "label": "Etki", "type": "select",
             "options": ["faydali", "zararli", "notr"], "required": True},
            {"key": "engelleyici", "label": "Tek başına ekimi engeller", "type": "bool"},
            {"key": "aciklama", "label": "Açıklama", "type": "text"},
        ],
    },
    "crop_signatures": {
        "label": "Ürün Tanıma — Fenolojik NDVI İmzaları",
        "description": "Uydu ile ürün tespitinde kullanılan aylık NDVI eğrileri. "
                       "Bölgeye göre kalibrasyon gerekir — Ürün Tanıma ekranındaki "
                       "'İmzaları Kalibre Et' bu değerleri etiketli örneklerden "
                       "otomatik günceller.",
        "defaults_from": ("crop_classification", "CROP_SIGNATURES"),
        "fields": [
            {"key": "key", "label": "Sistem Anahtarı", "type": "text", "required": True, "immutable": True},
            {"key": "label", "label": "Ürün Adı", "type": "text", "required": True},
            {"key": "renk", "label": "Harita Rengi (hex)", "type": "text"},
            {"key": "aylik_ndvi", "label": "Aylık NDVI (12 değer, virgülle)", "type": "text"},
            {"key": "aciklama", "label": "Fenolojik Açıklama", "type": "text"},
        ],
    },
    "soil_measurements": {
        "label": "Toprak Biyolojisi — Ölçüm Eşikleri",
        "description": "Skor hesabında kullanılan ölçüm alanları, sağlıklı aralıklar ve ağırlıklar.",
        "defaults_from": ("soil_biology", "MEASUREMENT_SPEC"),
        "fields": [
            {"key": "key", "label": "Sistem Anahtarı", "type": "text", "required": True, "immutable": True},
            {"key": "label", "label": "Görünen Ad", "type": "text", "required": True},
            {"key": "birim", "label": "Birim", "type": "text"},
            {"key": "dusuk", "label": "Düşük Eşik", "type": "number"},
            {"key": "hedef", "label": "Hedef Değer", "type": "number"},
            {"key": "agirlik", "label": "Skor Ağırlığı", "type": "number"},
            {"key": "aciklama", "label": "Açıklama", "type": "text"},
        ],
    },
}

COLLECTION = "managed_catalog_items"


def _code_defaults(catalog_key: str) -> List[Dict[str, Any]]:
    """Kod-seviyesi varsayılanları dinamik import ile okur.

    Import BURADA (fonksiyon içinde) yapılır — modül seviyesinde yapılsaydı
    `soil_biology` ↔ `catalog_registry` çevrimsel import'u oluşurdu (soil_biology
    bu modülün `get_catalog`'ını çağıracak).
    """
    spec = CATALOG_REGISTRY.get(catalog_key)
    if not spec:
        return []
    mod_name, var_name = spec["defaults_from"]
    try:
        mod = __import__(mod_name)
        return [dict(x) for x in getattr(mod, var_name, [])]
    except Exception:  # noqa: BLE001
        return []


async def get_catalog(db, catalog_key: str, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Kod varsayılanları + DB override/ekleme/silmelerinin BİRLEŞİMİ.

    Motorlar (soil_biology vb.) HER ZAMAN bunu çağırmalı — ham kod sabitini
    doğrudan kullanan bir yer kalırsa admin'in değişikliği o yolda görünmez.
    """
    defaults = _code_defaults(catalog_key)
    rows = await db[COLLECTION].find({"catalog_key": catalog_key}, {"_id": 0}).to_list(1000)
    by_key = {r["key"]: r for r in rows}

    out: List[Dict[str, Any]] = []
    seen = set()
    for item in defaults:
        k = item.get("key")
        seen.add(k)
        ov = by_key.get(k)
        if ov:
            if ov.get("is_active") is False and not include_inactive:
                continue                      # admin sildi
            merged = {**item, **{kk: vv for kk, vv in ov.items()
                                 if kk not in ("catalog_key", "id", "created_at", "updated_at",
                                               "updated_by", "is_custom")}}
            merged["_source"] = "override"
            out.append(merged)
        else:
            out.append({**item, "_source": "default"})

    # DB'de olup kodda OLMAYANLAR — admin'in eklediği tamamen yeni kalemler.
    for k, r in by_key.items():
        if k in seen:
            continue
        if r.get("is_active") is False and not include_inactive:
            continue
        out.append({**{kk: vv for kk, vv in r.items() if kk != "catalog_key"}, "_source": "custom"})
    return out


async def get_catalog_map(db, catalog_key: str) -> Dict[str, Dict[str, Any]]:
    """`{key: kalem}` — eski `X_BY_KEY` sözlüklerinin yerine geçer."""
    return {i["key"]: i for i in await get_catalog(db, catalog_key)}


class CatalogItemUpsert(BaseModel):
    key: str
    values: Dict[str, Any] = {}


def register_catalog_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/catalogs")
    async def list_catalogs(user=Depends(require_permission("settings:lookups_manage"))):
        out = []
        for key, spec in CATALOG_REGISTRY.items():
            items = await get_catalog(db, key)
            out.append({
                "key": key, "label": spec["label"], "description": spec.get("description"),
                "fields": spec["fields"], "item_count": len(items),
            })
        return out

    @api_router.get("/catalogs/{catalog_key}/items")
    async def list_items(catalog_key: str,
                         user=Depends(require_permission("settings:lookups_manage"))):
        if catalog_key not in CATALOG_REGISTRY:
            raise HTTPException(404, f"Bilinmeyen katalog: {catalog_key}")
        return {
            "catalog": {"key": catalog_key, **{k: v for k, v in CATALOG_REGISTRY[catalog_key].items()
                                               if k != "defaults_from"}},
            "items": await get_catalog(db, catalog_key, include_inactive=True),
        }

    @api_router.put("/catalogs/{catalog_key}/items/{item_key}")
    async def upsert_item(catalog_key: str, item_key: str, body: CatalogItemUpsert,
                          request: Request,
                          user=Depends(require_permission("settings:lookups_manage"))):
        """Var olan kalemi düzenler VEYA yeni kalem ekler (idempotent upsert)."""
        if catalog_key not in CATALOG_REGISTRY:
            raise HTTPException(404, f"Bilinmeyen katalog: {catalog_key}")
        allowed = {f["key"] for f in CATALOG_REGISTRY[catalog_key]["fields"]}
        unknown = set(body.values) - allowed
        if unknown:
            raise HTTPException(400, f"Bu katalogda tanımsız alan(lar): {', '.join(sorted(unknown))}")

        old = await db[COLLECTION].find_one({"catalog_key": catalog_key, "key": item_key}, {"_id": 0})
        is_default = any(d.get("key") == item_key for d in _code_defaults(catalog_key))
        doc = {
            "catalog_key": catalog_key, "key": item_key,
            **{k: v for k, v in body.values.items() if k != "key"},
            "is_active": True, "is_custom": not is_default,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user.get("email"),
        }
        if not old:
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = doc["updated_at"]
        await db[COLLECTION].update_one(
            {"catalog_key": catalog_key, "key": item_key}, {"$set": doc}, upsert=True)
        await log_audit(db, user, "update" if old else "create", "catalog_item",
                        f"{catalog_key}:{item_key}", old, doc, request)
        return await db[COLLECTION].find_one(
            {"catalog_key": catalog_key, "key": item_key}, {"_id": 0})

    @api_router.delete("/catalogs/{catalog_key}/items/{item_key}")
    async def delete_item(catalog_key: str, item_key: str, request: Request,
                          user=Depends(require_permission("settings:lookups_manage"))):
        """Soft delete (convention #3). Kod varsayılanı için `is_active: False`
        bir gölge kayıt yazılır — 'Varsayılana Döndür' ile geri alınabilir."""
        if catalog_key not in CATALOG_REGISTRY:
            raise HTTPException(404, f"Bilinmeyen katalog: {catalog_key}")
        old = await db[COLLECTION].find_one({"catalog_key": catalog_key, "key": item_key}, {"_id": 0})
        await db[COLLECTION].update_one(
            {"catalog_key": catalog_key, "key": item_key},
            {"$set": {"catalog_key": catalog_key, "key": item_key, "is_active": False,
                      "id": (old or {}).get("id") or str(uuid.uuid4()),
                      "updated_at": datetime.now(timezone.utc).isoformat(),
                      "updated_by": user.get("email")}},
            upsert=True)
        await log_audit(db, user, "delete", "catalog_item",
                        f"{catalog_key}:{item_key}", old, None, request)
        return {"status": "deactivated"}

    @api_router.post("/catalogs/{catalog_key}/items/{item_key}/reset")
    async def reset_item(catalog_key: str, item_key: str, request: Request,
                         user=Depends(require_permission("settings:lookups_manage"))):
        """DB katmanındaki override'ı KALDIRIR — kalem kod varsayılanına döner.
        Kodda karşılığı olmayan (admin'in eklediği) kalemde kayıt tamamen silinir."""
        if catalog_key not in CATALOG_REGISTRY:
            raise HTTPException(404, f"Bilinmeyen katalog: {catalog_key}")
        old = await db[COLLECTION].find_one({"catalog_key": catalog_key, "key": item_key}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Bu kalemin özel bir kaydı yok (zaten varsayılan).")
        await db[COLLECTION].delete_one({"catalog_key": catalog_key, "key": item_key})
        await log_audit(db, user, "reset", "catalog_item",
                        f"{catalog_key}:{item_key}", old, None, request)
        is_default = any(d.get("key") == item_key for d in _code_defaults(catalog_key))
        return {"status": "reset", "restored_to_default": is_default}
