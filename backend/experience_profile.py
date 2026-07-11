"""
=====================================================================
TabSIS — Experience Profile Modeli (IT-34 / FAZ 12 — Mobil başlangıç)
=====================================================================
ROADMAP: "Mobil deneyim statik rol bazlı değil, Experience Profile
(Persona) modeliyle yönetilir. RBAC sadece yetkilendirme içindir;
kullanıcının göreceği ekranlar hem yetkisine hem atanmış profiline göre
oluşur." Yani bu modül RBAC'ın (permissions.py) YERİNE geçmez — üstüne
biner: bir kullanıcı belirli bir menüyü GÖRME yetkisine sahip olabilir
AMA mobil deneyiminde o menü profilinde yoksa mobil client'ta görünmez
(masaüstü admin panelini ETKİLEMEZ — Experience Profile SADECE `GET
/me/experience`'ı tüketen mobil PWA'nın (IT-35) okuduğu bir konfigürasyon
katmanıdır, Layout.jsx'in masaüstü menüsünü DEĞİŞTİRMEZ).

`dashboard_widgets`/`menu_items`/`quick_actions`/`map_tools`/`ai_features`
listeleri BİLİNÇLİ OLARAK OPAK string listeleridir — `map_workspace.py`nin
(IT-14) `widget_keys`/`visible_layers` ile AYNI kalıp: backend bu key'lerin
anlamını bilmez/doğrulamaz, sadece admin'in girdiği listeyi saklar ve
`/me/experience` ile geri döner. Yeni bir mobil widget/menü eklemek bu
dosyayı DEĞİŞTİRMEYİ gerektirmez — sadece PWA tarafında yeni bir key
tanınır hale gelir.

Atama tek bir alanla tutulur — `users.experience_profile_id` (`custom_
role_id` ile AYNI desen, users.py). Roadmap'in "geçmişli tablo" seçeneği
BİLİNÇLİ OLARAK atlandı: `custom_role_id` değişikliklerinde de ayrı bir
geçmiş tablosu yok, sadece `log_audit` — Experience Profile ataması da
AYNI tutarlılıkla sadece audit log'a yazılır (permissions.py/users.py
emsaliyle tutarlı bilinçli sadelik).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

# Hiç profil atanmamış (veya atanan profil silinmiş/pasif) bir kullanıcı
# için mobil client'ın kırılmaması adına GÜVENLİ bir varsayılan — gerçek
# bir ExperienceProfile KAYDI DEĞİLDİR, sadece response fallback'i.
DEFAULT_EXPERIENCE = {
    "profile_id": None,
    "profile_name": "Varsayılan (Profil Atanmamış)",
    "dashboard_widgets": ["toplam_ciftci", "aktif_uretim_sezonlari"],
    "menu_items": ["ciftciler", "parseller", "harita-paneli"],
    "quick_actions": ["sulama-ekle", "destek-talebi"],
    "map_tools": ["sekille-sec"],
    "ai_features": [],
    "notification_behaviors": {"push": True, "sound": False},
    "default_filters": {},
    "offline_sync_rules": {"gorev_tamamlama": True},
}

PROFILE_FIELDS = [
    "dashboard_widgets", "menu_items", "quick_actions", "map_tools", "ai_features",
    "notification_behaviors", "default_filters", "offline_sync_rules",
]


class ExperienceProfileCreate(BaseModel):
    name: str
    dashboard_widgets: List[str] = []
    menu_items: List[str] = []
    quick_actions: List[str] = []
    map_tools: List[str] = []
    ai_features: List[str] = []
    notification_behaviors: Dict[str, Any] = {}
    default_filters: Dict[str, Any] = {}
    offline_sync_rules: Dict[str, Any] = {}


class ExperienceProfileUpdate(BaseModel):
    name: Optional[str] = None
    dashboard_widgets: Optional[List[str]] = None
    menu_items: Optional[List[str]] = None
    quick_actions: Optional[List[str]] = None
    map_tools: Optional[List[str]] = None
    ai_features: Optional[List[str]] = None
    notification_behaviors: Optional[Dict[str, Any]] = None
    default_filters: Optional[Dict[str, Any]] = None
    offline_sync_rules: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ProfileAssignRequest(BaseModel):
    experience_profile_id: Optional[str] = None   # None = atamayı kaldır


def register_experience_profile_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/experience-profiles")
    async def list_experience_profiles(user=Depends(require_permission("experience_profiles:view"))):
        return await db.experience_profiles.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @api_router.get("/experience-profiles/{profile_id}")
    async def get_experience_profile(profile_id: str, user=Depends(require_permission("experience_profiles:view"))):
        doc = await db.experience_profiles.find_one({"id": profile_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Experience Profile bulunamadı")
        return doc

    @api_router.post("/experience-profiles")
    async def create_experience_profile(body: ExperienceProfileCreate, request: Request,
                                         user=Depends(require_permission("experience_profiles:manage"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.experience_profiles.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="experience_profile", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/experience-profiles/{profile_id}")
    async def update_experience_profile(profile_id: str, body: ExperienceProfileUpdate, request: Request,
                                         user=Depends(require_permission("experience_profiles:manage"))):
        old = await db.experience_profiles.find_one({"id": profile_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Experience Profile bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.experience_profiles.update_one({"id": profile_id}, {"$set": updates})
        new = await db.experience_profiles.find_one({"id": profile_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="experience_profile", entity_id=profile_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/experience-profiles/{profile_id}")
    async def delete_experience_profile(profile_id: str, request: Request,
                                         user=Depends(require_permission("experience_profiles:manage"))):
        """Soft delete (convention #3) — bu profile atanmış kullanıcılar
        ETKİLENMEZ, sadece `/me/experience` onlar için DEFAULT_EXPERIENCE'a
        düşer (bkz. modül docstring'i)."""
        old = await db.experience_profiles.find_one({"id": profile_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Experience Profile bulunamadı")
        await db.experience_profiles.update_one({"id": profile_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="deactivate", entity="experience_profile", entity_id=profile_id, old_value=old, request=request)
        return {"status": "deactivated"}

    @api_router.get("/users/{user_id}/experience-profile")
    async def get_user_experience_profile(user_id: str, user=Depends(require_permission("experience_profiles:view"))):
        target = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
        if not target:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        return {"user_id": user_id, "experience_profile_id": target.get("experience_profile_id")}

    @api_router.put("/users/{user_id}/experience-profile")
    async def assign_experience_profile(user_id: str, body: ProfileAssignRequest, request: Request,
                                         user=Depends(require_permission("experience_profiles:manage"))):
        target = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
        if not target:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        if body.experience_profile_id:
            profile = await db.experience_profiles.find_one({"id": body.experience_profile_id, "is_active": True})
            if not profile:
                raise HTTPException(404, "Experience Profile bulunamadı veya pasif")
        await db.users.update_one({"id": user_id}, {"$set": {"experience_profile_id": body.experience_profile_id}})
        await log_audit(db, user, action="assign", entity="user_experience_profile", entity_id=user_id,
                         old_value={"experience_profile_id": target.get("experience_profile_id")},
                         new_value={"experience_profile_id": body.experience_profile_id}, request=request)
        return {"user_id": user_id, "experience_profile_id": body.experience_profile_id}

    @api_router.get("/me/experience")
    async def my_experience(user=Depends(current_user)):
        """Mobil PWA'nın (IT-35) açılışta çektiği BİRLEŞİK konfigürasyon —
        dashboard+menu+widget+quick action TEK response'ta (kabul kriteri)."""
        profile_id = user.get("experience_profile_id")
        if not profile_id:
            return DEFAULT_EXPERIENCE
        profile = await db.experience_profiles.find_one({"id": profile_id, "is_active": True}, {"_id": 0})
        if not profile:
            return DEFAULT_EXPERIENCE
        return {"profile_id": profile["id"], "profile_name": profile["name"],
                **{f: profile.get(f, DEFAULT_EXPERIENCE[f]) for f in PROFILE_FIELDS}}
