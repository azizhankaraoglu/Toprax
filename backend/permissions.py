"""
=====================================================================
TabSIS — Granüler Yetkilendirme (Permission) Sistemi (Sprint 4d)
=====================================================================
Önceki sistem (config.py'deki ROLE_HIERARCHY + require_min_role) kaba
bir "seviye" mantığıydı: "en az X seviyesinde ol". Bu modül onun YERİNE
DEĞİL, ÜZERİNE ince taneli bir katman ekler:

  Modül × Fonksiyon  →  Permission (örn. "parcels:split_merge")
  Permission'lar      →  Rol altında gruplanır (built-in veya custom)
  Rol                 →  Kullanıcıya atanır
  Kullanıcı           →  Ayrıca tekil permission grant/revoke alabilir

Neden require_min_role tamamen kaldırılmadı: Onlarca endpoint'in TAMAMINI
tek seferde bu yeni sisteme geçirmek, test edemediğimiz bu ortamda çok
riskli olurdu (bir satır atlanırsa güvenlik açığı doğar). Bunun yerine:
  - require_permission() yeni ve en granüler kontrol olarak eklendi,
    veri giriş modülündeki (data_entry.py) ve ayarlar/audit uçlarında
    kullanılmaya başlandı.
  - require_min_role() olduğu gibi duruyor (server.py'nin geri kalanında).
  - super_admin / kurum_yoneticisi / il_yoneticisi / fabrika_muduru
    varsayılan olarak TÜM permission'lara sahip (ALL_PERMISSIONS) —
    yani üst rollerde davranış değişmedi, sadece ALT rollerde artık
    "hangi modülün hangi fonksiyonu" bazında ince ayar mümkün.

Bir sonraki sprint'te kalan require_min_role çağrıları da tek tek
require_permission'a taşınabilir (mekanik ama zaman alan bir iş).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional, Dict


# =====================================================================
# PERMISSION KATALOĞU — Modül × Fonksiyon
# =====================================================================
PERMISSION_CATALOG = {
    "farmers": {
        "label": "Çiftçiler",
        "permissions": [
            {"key": "farmers:view", "label": "Görüntüle"},
            {"key": "farmers:create", "label": "Yeni çiftçi ekle"},
            {"key": "farmers:edit", "label": "Düzenle"},
        ],
    },
    "parcels": {
        "label": "Parseller",
        "permissions": [
            {"key": "parcels:view", "label": "Görüntüle"},
            {"key": "parcels:create", "label": "Yeni parsel (form ile)"},
            {"key": "parcels:edit", "label": "Düzenle"},
            {"key": "parcels:delete", "label": "Sil"},
            {"key": "parcels:draw_tools", "label": "Harita çizim araçları (çiz/düzenle)"},
            {"key": "parcels:split_merge", "label": "Böl / Birleştir"},
            {"key": "parcels:import_geojson", "label": "GeoJSON toplu içe aktarma"},
        ],
    },
    "contracts": {
        "label": "Sözleşmeler",
        "permissions": [
            {"key": "contracts:view", "label": "Görüntüle"},
            {"key": "contracts:create", "label": "Oluştur"},
            {"key": "contracts:edit", "label": "Düzenle"},
            {"key": "contracts:delete", "label": "Sil"},
        ],
    },
    "plantings": {
        "label": "Ekim Planlama",
        "permissions": [
            {"key": "plantings:view", "label": "Görüntüle"},
            {"key": "plantings:create", "label": "Kayıt ekle/düzenle"},
        ],
    },
    "soil_irrigation": {
        "label": "Toprak & Sulama",
        "permissions": [
            {"key": "soil:view", "label": "Toprak analizlerini görüntüle"},
            {"key": "soil:create", "label": "Toprak analizi ekle"},
            {"key": "irrigation:view", "label": "Sulama kayıtlarını görüntüle"},
            {"key": "irrigation:create", "label": "Sulama kaydı ekle"},
        ],
    },
    "operations": {
        "label": "Operasyon",
        "permissions": [
            {"key": "operations:view", "label": "Görüntüle"},
            {"key": "operations:machines_manage", "label": "Makine ekle/düzenle/sil"},
            {"key": "operations:workers_manage", "label": "İşçi ekle/sil"},
            {"key": "operations:tasks_manage", "label": "Görev ekle/düzenle/sil"},
        ],
    },
    "logistics_kantar": {
        "label": "Lojistik & Kantar",
        "permissions": [
            {"key": "logistics:view", "label": "Randevuları görüntüle"},
            {"key": "logistics:create", "label": "Randevu oluştur/düzenle"},
            {"key": "kantar:view", "label": "Kantar kayıtlarını görüntüle"},
            {"key": "kantar:create", "label": "Kantar kaydı gir"},
        ],
    },
    "e_belge": {
        "label": "E-Fatura / E-İrsaliye",
        "permissions": [
            {"key": "ebelge:view", "label": "Görüntüle"},
            {"key": "ebelge:create", "label": "Belge oluştur"},
        ],
    },
    "iot_drone": {
        "label": "IoT & Drone",
        "permissions": [
            {"key": "iot:view", "label": "Sensörleri görüntüle"},
            {"key": "iot:manage", "label": "Sensör kaydet/güncelle/sil"},
            {"key": "drone:view", "label": "Görevleri görüntüle"},
            {"key": "drone:manage", "label": "Görev kaydet"},
        ],
    },
    "ai": {
        "label": "Yapay Zeka",
        "permissions": [
            {"key": "ai:copilot_use", "label": "AI Copilot kullan"},
            {"key": "ai:disease_detect_use", "label": "AI hastalık tespiti kullan"},
        ],
    },
    "saha": {
        "label": "Saha Mobil",
        "permissions": [
            {"key": "saha:submit", "label": "Saha ziyaret raporu gönder"},
        ],
    },
    "forms": {
        "label": "Formlar & Anket",
        "permissions": [
            {"key": "forms:view", "label": "Görüntüle"},
            {"key": "forms:manage", "label": "Oluştur/düzenle/sil"},
        ],
    },
    "reports": {
        "label": "Raporlar",
        "permissions": [
            {"key": "reports:view", "label": "Verimlilik/Karne raporlarını görüntüle"},
        ],
    },
    "settings": {
        "label": "Ayarlar",
        "permissions": [
            {"key": "settings:integrations_view", "label": "Entegrasyonları görüntüle"},
            {"key": "settings:integrations_manage", "label": "Entegrasyon ayarlarını değiştir + test et"},
            {"key": "settings:audit_view", "label": "Audit log görüntüle"},
            {"key": "settings:users_view", "label": "Kullanıcıları görüntüle"},
            {"key": "settings:users_manage", "label": "Kullanıcı ekle/rol ata"},
            {"key": "settings:roles_manage", "label": "Özel rol oluştur/düzenle"},
        ],
    },
}

# Tüm permission key'lerinin düz listesi
ALL_PERMISSIONS = [p["key"] for mod in PERMISSION_CATALOG.values() for p in mod["permissions"]]

# =====================================================================
# VARSAYILAN ROL → PERMISSION SETLERİ
# =====================================================================
# Not: config.py'deki ROLE_HIERARCHY'deki 8 rolle bire bir eşleşir.
# Üst 4 rol (super_admin, kurum/il_yoneticisi, fabrika_muduru) TÜM
# yetkilere sahiptir — bu satırların DEĞİŞTİRİLMESİ beklenmiyor, onlar
# zaten "kooperatifin patronu" seviyesinde. İnce ayar asıl ALT rollerde
# (ziraat_muhendisi, saha_personeli) ve custom role'lerde yapılır.
DEFAULT_ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "super_admin": ALL_PERMISSIONS,
    "kurum_yoneticisi": ALL_PERMISSIONS,
    "il_yoneticisi": ALL_PERMISSIONS,
    "fabrika_muduru": ALL_PERMISSIONS,
    "ilce_yoneticisi": [
        "farmers:view", "farmers:create", "farmers:edit",
        "parcels:view", "parcels:create", "parcels:edit", "parcels:draw_tools", "parcels:split_merge", "parcels:import_geojson",
        "contracts:view", "contracts:create", "contracts:edit",
        "plantings:view", "plantings:create",
        "soil:view", "soil:create", "irrigation:view", "irrigation:create",
        "operations:view", "operations:machines_manage", "operations:workers_manage", "operations:tasks_manage",
        "logistics:view", "logistics:create", "kantar:view", "kantar:create",
        "ebelge:view", "ebelge:create",
        "iot:view", "iot:manage", "drone:view", "drone:manage",
        "ai:copilot_use", "ai:disease_detect_use",
        "forms:view", "forms:manage", "reports:view",
        "settings:integrations_view", "settings:audit_view", "settings:users_view",
    ],
    "ziraat_muhendisi": [
        "farmers:view", "farmers:edit",
        "parcels:view", "parcels:create", "parcels:edit", "parcels:draw_tools", "parcels:split_merge", "parcels:import_geojson",
        "contracts:view",
        "plantings:view", "plantings:create",
        "soil:view", "soil:create", "irrigation:view", "irrigation:create",
        "operations:view", "operations:tasks_manage",
        "logistics:view", "kantar:view",
        "ebelge:view",
        "iot:view", "iot:manage", "drone:view", "drone:manage",
        "ai:copilot_use", "ai:disease_detect_use",
        "forms:view", "forms:manage", "reports:view",
    ],
    "saha_personeli": [
        "farmers:view", "parcels:view",
        "soil:view", "irrigation:view",
        "operations:view",
        "iot:view", "drone:view",
        "ai:disease_detect_use",
        "saha:submit",
        "forms:view",
    ],
    "kantar_personeli": [
        # Kantar/tartı operatörü — sadece tartı ve ilgili randevu/lojistik
        # işlemlerine odaklı, diğer modüllere erişimi yok.
        "farmers:view",
        "logistics:view", "logistics:create",
        "kantar:view", "kantar:create",
        "ebelge:view", "ebelge:create",
    ],
    "toprak_personeli": [
        # Saha/numune personeli — toprak analizi ve sulama kaydı girişi,
        # parsel/çiftçi bilgisine sadece görüntüleme erişimi.
        "farmers:view", "parcels:view",
        "soil:view", "soil:create",
        "irrigation:view", "irrigation:create",
        "saha:submit", "forms:view",
    ],
    "ciftci": [],   # Çiftçiler ayrı /farmer/* self-servis uçlarını kullanır, bu sisteme dahil değil
}


class CustomRoleCreate(BaseModel):
    name: str
    permissions: List[str]


class CustomRoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[List[str]] = None


class UserRoleAssign(BaseModel):
    role: Optional[str] = None                    # built-in rol (config.ROLE_HIERARCHY'deki)
    custom_role_id: Optional[str] = None           # verilirse built-in rolün YERİNE bu kullanılır
    grant: List[str] = []                          # role/custom_role'e EK olarak verilen izinler
    revoke: List[str] = []                         # role/custom_role'den ÇIKARILAN izinler


async def get_effective_permissions(user: dict, db) -> set:
    """Bir kullanıcının fiili (role + custom_role + override) permission setini hesaplar."""
    if user.get("custom_role_id"):
        custom = await db.custom_roles.find_one({"id": user["custom_role_id"]}, {"_id": 0})
        base = set(custom["permissions"]) if custom else set()
    else:
        base = set(DEFAULT_ROLE_PERMISSIONS.get(user.get("role"), []))

    overrides = user.get("permission_overrides") or {}
    base |= set(overrides.get("grant", []))
    base -= set(overrides.get("revoke", []))
    return base


def make_require_permission(current_user, db):
    """
    server.py'de current_user/db tanımlandıktan SONRA çağrılır ve gerçek
    çalışan require_permission fonksiyonunu üretir (current_user'a Depends
    edebilmek için closure gerekiyor).
    """
    def require_permission(permission_key: str):
        async def _checker(user: dict = Depends(current_user)) -> dict:
            perms = await get_effective_permissions(user, db)
            if permission_key not in perms:
                label = permission_key
                for mod in PERMISSION_CATALOG.values():
                    for p in mod["permissions"]:
                        if p["key"] == permission_key:
                            label = p["label"]
                raise HTTPException(403, f"'{label}' yetkiniz yok")
            return user
        return _checker
    return require_permission


def register_permission_routes(api_router, db, current_user, require_min_role, log_audit):
    """Permission kataloğu + custom role CRUD + kullanıcının kendi izinlerini görme."""

    @api_router.get("/permissions/catalog")
    async def get_permission_catalog(user=Depends(current_user)):
        """Tüm sistemdeki modül/fonksiyon/permission listesi — rol editörü UI'sı için."""
        return {"catalog": PERMISSION_CATALOG, "default_role_permissions": DEFAULT_ROLE_PERMISSIONS}

    @api_router.get("/permissions/me")
    async def my_permissions(user=Depends(current_user)):
        """Giriş yapmış kullanıcının kendi fiili yetkileri (frontend'de buton gizleme için)."""
        perms = await get_effective_permissions(user, db)
        return {"role": user.get("role"), "custom_role_id": user.get("custom_role_id"), "permissions": sorted(perms)}

    @api_router.get("/roles/custom")
    async def list_custom_roles(user=Depends(require_min_role("fabrika_muduru"))):
        return await db.custom_roles.find({}, {"_id": 0}).to_list(100)

    @api_router.post("/roles/custom")
    async def create_custom_role(body: CustomRoleCreate, request: Request, user=Depends(require_min_role("fabrika_muduru"))):
        invalid = [p for p in body.permissions if p not in ALL_PERMISSIONS]
        if invalid:
            raise HTTPException(400, f"Geçersiz permission key'ler: {invalid}")
        doc = {
            "id": str(uuid.uuid4()),
            "name": body.name,
            "permissions": body.permissions,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.get("email"),
        }
        await db.custom_roles.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="custom_role", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/roles/custom/{role_id}")
    async def update_custom_role(role_id: str, body: CustomRoleUpdate, request: Request, user=Depends(require_min_role("fabrika_muduru"))):
        old = await db.custom_roles.find_one({"id": role_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Rol bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "permissions" in updates:
            invalid = [p for p in updates["permissions"] if p not in ALL_PERMISSIONS]
            if invalid:
                raise HTTPException(400, f"Geçersiz permission key'ler: {invalid}")
        await db.custom_roles.update_one({"id": role_id}, {"$set": updates})
        await log_audit(db, user, action="update", entity="custom_role", entity_id=role_id, old_value=old, new_value=updates, request=request)
        return {**old, **updates}

    @api_router.delete("/roles/custom/{role_id}")
    async def delete_custom_role(role_id: str, request: Request, user=Depends(require_min_role("fabrika_muduru"))):
        in_use = await db.users.count_documents({"custom_role_id": role_id})
        if in_use > 0:
            raise HTTPException(409, f"Bu rol {in_use} kullanıcıya atanmış, önce onları başka role taşıyın")
        old = await db.custom_roles.find_one({"id": role_id}, {"_id": 0})
        await db.custom_roles.delete_one({"id": role_id})
        await log_audit(db, user, action="delete", entity="custom_role", entity_id=role_id, old_value=old, request=request)
        return {"status": "deleted"}
