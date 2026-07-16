"""
=====================================================================
Toprax — Farmer LMS: Eğitim Kataloğu + İçerik Yönetimi + Atama +
Durum + Zorunlu Eğitim (IT-29 / FAZ 10 başlangıç)
=====================================================================
ROADMAP notu: "Tam kapsamlı bir LMS değil — merkezi eğitim yönetimi +
atama + takip + sertifika + kişi kartı entegrasyonu." Bu iterasyon
katalog+atama+durum kısmını kurar; Quiz/Sertifika/Learning Path IT-30'un,
Uzman Desteği/FAQ/Analitik IT-31'in kapsamıdır.

**İçerik dosyaları (Video/PDF/Word/PowerPoint/Resim/Ses) YENİ bir dosya
yükleme mekanizması İCAT ETMEZ** — mevcut genel `storage.py` (IT-04)
uçlarını AYNEN kullanır: bir CourseContent oluşturulduktan SONRA dosyası
`POST /uploads` (module="lms_contents", entity_id=content.id) ile
yüklenir, `GET /uploads?module=lms_contents&entity_id=<content_id>` ile
okunur. Bu, "video dosyaları uygulama sunucusunda tutulmuyor, storage.py
soyutlaması üzerinden" kabul kriterini SIFIR yeni kod ile karşılar (IT-04
zaten yerel disk arkasında bir soyutlama kurmuştu, ileride S3/MinIO'ya
geçilirse lms.py hiç değişmez). `harici_link`/`youtube` içerik tipleri
zaten dosya değildir, `external_url` alanına düz metin olarak yazılır.

Kategori kataloğu (`course_categories`) support.py'nin `SupportType`
kataloğuyla AYNI desen (idempotent seed + basit CRUD + soft delete) —
field_definitions'ın lookup_groups/lookup_values sistemine BİLİNÇLİ
OLARAK BAĞLANMADI, çünkü o sistem "dinamik alan" kavramına hizmet eder
(bkz. field_definitions.py docstring'i); eğitim kategorisi kavramsal
olarak support_types/task_types'a daha yakın bağımsız bir kataloğdur.

Atama (`course_assignments` + `user_course_status`): bir atama YEDİ
hedef tipinden birine göre KULLANICI id listesine çözülür (bkz.
`_resolve_target_user_ids`) ve HER kullanıcı için (varsa zaten) bir
`user_course_status` kaydı (yoksa) oluşturulur — idempotent, aynı
kullanıcı aynı eğitime iki kez atansa da tek kayıt kalır (favorites.py/
saved_queries emsalleriyle AYNI "tekrar atarsan kopya oluşmaz" ilkesi).
"segment" hedefi Query Engine'i (IT-08) DOĞRUDAN kullanır — kabul
kriteri buradan karşılanır. "farmers" modülünde segment seçilirse
(kampanyalarınkiyle AYNI mantık, IT-26) sonuç farmer_id listesine, oradan
da `users.role="ciftci"` + `farmer_id` eşleşmesiyle gerçek kullanıcı
id'lerine çevrilir (eğitim ATANAN her zaman bir user_id'dir, Farmer
DEĞİL — çiftçi de dahil olmak üzere HERKES sistemde bir `users` kaydı).

Durum makinesi 6 değer taşır (ROADMAP'in verdiği BİREBİR isimler:
Atandı/Başlamadı/Devam Ediyor/Tamamlandı/Başarısız/Süresi Doldu) ama
BİLİNÇLİ bir sadeleştirmeyle sadece 4'ü gerçek DB durumu olarak
saklanır: `atandi` (başlangıç — "Başlamadı" bu durumun EŞ ANLAMLI UI
etiketidir, ayrı bir saklı durum değildir çünkü aradaki fark sadece
kullanıcının ekranı hiç açıp açmadığıdır, ayrı bir geçiş olayı yok),
`devam_ediyor`, `tamamlandi`, `basarisiz` (IT-30'un quiz'i başarısızsa
kullanılacak — bu iterasyonda quiz yok, o yüzden hiç üretilmez),
`suresi_doldu` (computed: `expires_at` geçmiş VE hâlâ terminal olmayan
kayıtlar `GET /lms/my-courses` her okunduğunda hesaplanır, ayrıca
`POST /lms/recompute-expirations` ile DB'ye de yazılabilir — support.py/
campaigns.py'deki "tick" endpoint'i kalıbıyla AYNI aile, gerçek bir OS
cron YOK).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List, Any

from query_engine import execute_query

CONTENT_TYPES = ["video", "pdf", "word", "powerpoint", "resim", "ses", "harici_link", "youtube"]
CONTENT_TYPE_LABELS = {
    "video": "Video", "pdf": "PDF", "word": "Word", "powerpoint": "PowerPoint",
    "resim": "Resim", "ses": "Ses Dosyası", "harici_link": "Harici Link", "youtube": "YouTube Videosu",
}
# Bu ikisi dosya DEĞİL, düz bir URL'dir — CourseContent.external_url'e yazılır,
# diğer 6 tip `uploads` koleksiyonu (module="lms_contents") üzerinden yönetilir.
URL_BASED_CONTENT_TYPES = {"harici_link", "youtube"}

DIFFICULTY_LABELS = {"baslangic": "Başlangıç", "orta": "Orta", "ileri": "İleri"}
EDUCATION_TYPE_LABELS = {"online": "Online", "yuz_yuze": "Yüz Yüze", "karma": "Karma"}

STATUS_LABELS = {
    "atandi": "Atandı", "devam_ediyor": "Devam Ediyor", "tamamlandi": "Tamamlandı",
    "basarisiz": "Başarısız", "suresi_doldu": "Süresi Doldu",
}

DEFAULT_CATEGORIES = [
    "Şeker Pancarı", "Buğday", "Mısır", "Gübreleme", "Sulama", "Hastalıklar",
    "Zararlılar", "Makine Kullanımı", "İş Sağlığı ve Güvenliği",
    "Kooperatif Süreçleri", "Dijital Tarım",
]

TARGET_TYPES = {"user", "user_group", "role", "segment", "production_cycle", "region", "il_ilce"}
TARGET_TYPE_LABELS = {
    "user": "Tek Kullanıcı", "user_group": "Kullanıcı Grubu", "role": "Rol",
    "segment": "Segment (Kayıtlı Sorgu)", "production_cycle": "Üretim Sezonu",
    "region": "Bölge", "il_ilce": "İl / İlçe",
}


# =====================================================================
# Modeller
# =====================================================================
class CourseCategoryCreate(BaseModel):
    name: str
    order: int = 0


class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: str
    education_type: str                      # online | yuz_yuze | karma
    duration_minutes: Optional[int] = None
    difficulty: str = "baslangic"             # baslangic | orta | ileri
    validity_months: Optional[int] = None     # sertifika/eğitim geçerlilik süresi
    instructor: Optional[str] = None
    is_mandatory: bool = False


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    education_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    difficulty: Optional[str] = None
    validity_months: Optional[int] = None
    instructor: Optional[str] = None
    is_mandatory: Optional[bool] = None
    is_active: Optional[bool] = None


class CourseContentCreate(BaseModel):
    content_type: str
    title: str
    external_url: Optional[str] = None        # harici_link/youtube İÇİN ZORUNLU, diğerlerinde yok sayılır
    duration_minutes: Optional[int] = None


class ContentReorderItem(BaseModel):
    id: str
    order: int


class ContentReorderRequest(BaseModel):
    items: List[ContentReorderItem]


class UserGroupCreate(BaseModel):
    name: str
    member_user_ids: List[str] = []


class UserGroupUpdate(BaseModel):
    name: Optional[str] = None
    member_user_ids: Optional[List[str]] = None


class CourseAssignmentCreate(BaseModel):
    target_type: str
    target_value: Any                         # bkz. modül docstring'i — tipe göre str veya dict
    note: Optional[str] = None


class ContentCompleteRequest(BaseModel):
    completed: bool = True


async def _resolve_target_user_ids(db, user: dict, target_type: str, target_value: Any) -> List[str]:
    """Yedi hedef tipinden birini gerçek `users.id` listesine çözer.
    farmer bazlı hedeflerde (segment/production_cycle/region/il_ilce)
    HER ZAMAN role="ciftci" + farmer_id eşleşmesiyle user'a atlanır —
    eğitim ataması bir Farmer'a değil bir User'a yapılır (bkz. docstring)."""
    if target_type == "user":
        u = await db.users.find_one({"id": target_value}, {"_id": 0, "id": 1})
        if not u:
            raise HTTPException(404, "Kullanıcı bulunamadı")
        return [u["id"]]

    if target_type == "user_group":
        grp = await db.lms_user_groups.find_one({"id": target_value}, {"_id": 0})
        if not grp:
            raise HTTPException(404, "Kullanıcı grubu bulunamadı")
        return list(grp.get("member_user_ids", []))

    if target_type == "role":
        from config_service import ROLE_HIERARCHY
        if target_value not in ROLE_HIERARCHY:
            raise HTTPException(400, f"Geçersiz rol: {target_value}")
        docs = await db.users.find({"role": target_value, "active": {"$ne": False}}, {"_id": 0, "id": 1}).to_list(5000)
        return [d["id"] for d in docs]

    if target_type == "segment":
        sq = await db.saved_queries.find_one({"id": target_value}, {"_id": 0})
        if not sq:
            raise HTTPException(404, "Segment (kayıtlı sorgu) bulunamadı")
        module = sq["module"]
        if module not in ("farmers", "users"):
            raise HTTPException(400, "Eğitim segmenti sadece 'farmers' veya 'users' modülünde bir kayıtlı sorgu olabilir")
        result = await execute_query(db, module, user, sq["filters"], logic=sq.get("logic", "AND"),
                                      page=1, page_size=2000, fields=["id"])
        ids = [item["id"] for item in result["items"]]
        if module == "users":
            return ids
        docs = await db.users.find({"role": "ciftci", "farmer_id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(5000)
        return [d["id"] for d in docs]

    if target_type == "production_cycle":
        cycle = await db.production_cycles.find_one({"id": target_value}, {"_id": 0})
        if not cycle:
            raise HTTPException(404, "Üretim sezonu bulunamadı")
        docs = await db.users.find({"role": "ciftci", "farmer_id": cycle["farmer_id"]}, {"_id": 0, "id": 1}).to_list(10)
        return [d["id"] for d in docs]

    if target_type == "region":
        farmers = await db.farmers.find({"region_id": target_value}, {"_id": 0, "id": 1}).to_list(5000)
        farmer_ids = [f["id"] for f in farmers]
        docs = await db.users.find({"role": "ciftci", "farmer_id": {"$in": farmer_ids}}, {"_id": 0, "id": 1}).to_list(5000)
        return [d["id"] for d in docs]

    if target_type == "il_ilce":
        if not isinstance(target_value, dict) or not target_value.get("il_value_id"):
            raise HTTPException(400, "il_ilce hedefi için {'il_value_id': ..., 'ilce_value_id': ...} gerekli")
        filt = {"il": target_value["il_value_id"]}
        if target_value.get("ilce_value_id"):
            filt["ilce"] = target_value["ilce_value_id"]
        parcels = await db.parcels.find(filt, {"_id": 0, "farmer_id": 1}).to_list(5000)
        farmer_ids = list({p["farmer_id"] for p in parcels if p.get("farmer_id")})
        docs = await db.users.find({"role": "ciftci", "farmer_id": {"$in": farmer_ids}}, {"_id": 0, "id": 1}).to_list(5000)
        return [d["id"] for d in docs]

    raise HTTPException(400, f"Bilinmeyen hedef tipi: {target_type}")


def _effective_status(doc: dict) -> str:
    """DB'deki `status` ile expires_at'e göre GÖRÜNÜR durumu hesaplar
    (DB'yi mutasyona uğratmaz — bkz. modül docstring'i, `recompute-
    expirations` bunu kalıcı hale getiren ayrı bir adımdır)."""
    if doc["status"] in ("tamamlandi", "basarisiz", "suresi_doldu"):
        return doc["status"]
    if doc.get("expires_at") and doc["expires_at"] < datetime.now(timezone.utc).isoformat():
        return "suresi_doldu"
    return doc["status"]


def register_lms_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    # IT-33 — "lms" feature flag'i kapatılınca eğitim uçları GERÇEKTEN 403 döner.
    require_feature = require_feature or (lambda key: (lambda: True))

    # ---------------- Kategoriler ----------------
    @api_router.get("/course-categories")
    async def list_course_categories(user=Depends(require_permission("lms:catalog_view"))):
        return await db.course_categories.find({}, {"_id": 0}).sort("order", 1).to_list(200)

    @api_router.post("/course-categories/seed-defaults")
    async def seed_course_categories(user=Depends(require_permission("lms:catalog_manage"))):
        created = 0
        for i, name in enumerate(DEFAULT_CATEGORIES):
            existing = await db.course_categories.find_one({"name": name})
            if existing:
                continue
            await db.course_categories.insert_one({
                "id": str(uuid.uuid4()), "name": name, "order": i, "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            created += 1
        return {"status": "seeded", "created": created}

    @api_router.post("/course-categories")
    async def create_course_category(body: CourseCategoryCreate, request: Request,
                                       user=Depends(require_permission("lms:catalog_manage"))):
        doc = {"id": str(uuid.uuid4()), "name": body.name, "order": body.order, "is_active": True,
               "created_at": datetime.now(timezone.utc).isoformat()}
        await db.course_categories.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="course_category", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.delete("/course-categories/{category_id}")
    async def delete_course_category(category_id: str, request: Request,
                                      user=Depends(require_permission("lms:catalog_manage"))):
        old = await db.course_categories.find_one({"id": category_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kategori bulunamadı")
        await db.course_categories.update_one({"id": category_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="delete", entity="course_category", entity_id=category_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # ---------------- Kullanıcı Grupları ----------------
    @api_router.get("/lms-user-groups")
    async def list_user_groups(user=Depends(require_permission("lms:groups_manage"))):
        return await db.lms_user_groups.find({"is_active": True}, {"_id": 0}).to_list(200)

    @api_router.post("/lms-user-groups")
    async def create_user_group(body: UserGroupCreate, request: Request,
                                 user=Depends(require_permission("lms:groups_manage"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.lms_user_groups.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="lms_user_group", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/lms-user-groups/{group_id}")
    async def update_user_group(group_id: str, body: UserGroupUpdate, request: Request,
                                 user=Depends(require_permission("lms:groups_manage"))):
        old = await db.lms_user_groups.find_one({"id": group_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kullanıcı grubu bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.lms_user_groups.update_one({"id": group_id}, {"$set": updates})
        new = await db.lms_user_groups.find_one({"id": group_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="lms_user_group", entity_id=group_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/lms-user-groups/{group_id}")
    async def delete_user_group(group_id: str, request: Request, user=Depends(require_permission("lms:groups_manage"))):
        old = await db.lms_user_groups.find_one({"id": group_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kullanıcı grubu bulunamadı")
        await db.lms_user_groups.update_one({"id": group_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="delete", entity="lms_user_group", entity_id=group_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # ---------------- Eğitimler (Course) ----------------
    @api_router.get("/courses")
    async def list_courses(category_id: Optional[str] = None, is_active: Optional[bool] = None,
                            user=Depends(require_permission("lms:catalog_view")), _feat=Depends(require_feature("lms"))):
        filt: Dict[str, Any] = {}
        if category_id:
            filt["category_id"] = category_id
        if is_active is not None:
            filt["is_active"] = is_active
        return await db.courses.find(filt, {"_id": 0}).sort("created_at", -1).to_list(500)

    @api_router.get("/courses/{course_id}")
    async def get_course(course_id: str, user=Depends(require_permission("lms:catalog_view"))):
        doc = await db.courses.find_one({"id": course_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Eğitim bulunamadı")
        doc["contents"] = await db.course_contents.find({"course_id": course_id}, {"_id": 0}).sort("order", 1).to_list(200)
        return doc

    @api_router.post("/courses")
    async def create_course(body: CourseCreate, request: Request, user=Depends(require_permission("lms:catalog_manage"))):
        if body.education_type not in EDUCATION_TYPE_LABELS:
            raise HTTPException(400, f"Geçersiz eğitim türü: {body.education_type}")
        if body.difficulty not in DIFFICULTY_LABELS:
            raise HTTPException(400, f"Geçersiz zorluk seviyesi: {body.difficulty}")
        category = await db.course_categories.find_one({"id": body.category_id})
        if not category:
            raise HTTPException(404, "Kategori bulunamadı")

        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user.get("full_name") or user.get("email")
        await db.courses.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="course", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/courses/{course_id}")
    async def update_course(course_id: str, body: CourseUpdate, request: Request,
                             user=Depends(require_permission("lms:catalog_manage"))):
        old = await db.courses.find_one({"id": course_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Eğitim bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "education_type" in updates and updates["education_type"] not in EDUCATION_TYPE_LABELS:
            raise HTTPException(400, f"Geçersiz eğitim türü: {updates['education_type']}")
        if "difficulty" in updates and updates["difficulty"] not in DIFFICULTY_LABELS:
            raise HTTPException(400, f"Geçersiz zorluk seviyesi: {updates['difficulty']}")
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.courses.update_one({"id": course_id}, {"$set": updates})
        new = await db.courses.find_one({"id": course_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="course", entity_id=course_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/courses/{course_id}")
    async def delete_course(course_id: str, request: Request, user=Depends(require_permission("lms:catalog_manage"))):
        old = await db.courses.find_one({"id": course_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Eğitim bulunamadı")
        await db.courses.update_one({"id": course_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="delete", entity="course", entity_id=course_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # ---------------- İçerik (CourseContent) ----------------
    @api_router.post("/courses/{course_id}/contents")
    async def add_course_content(course_id: str, body: CourseContentCreate, request: Request,
                                  user=Depends(require_permission("lms:catalog_manage"))):
        course = await db.courses.find_one({"id": course_id})
        if not course:
            raise HTTPException(404, "Eğitim bulunamadı")
        if body.content_type not in CONTENT_TYPES:
            raise HTTPException(400, f"Geçersiz içerik tipi: {body.content_type}")
        if body.content_type in URL_BASED_CONTENT_TYPES and not body.external_url:
            raise HTTPException(400, f"'{CONTENT_TYPE_LABELS[body.content_type]}' için external_url zorunlu")

        current_count = await db.course_contents.count_documents({"course_id": course_id})
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["course_id"] = course_id
        doc["order"] = current_count
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.course_contents.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="course_content", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.post("/courses/{course_id}/contents/reorder")
    async def reorder_course_contents(course_id: str, body: ContentReorderRequest, request: Request,
                                       user=Depends(require_permission("lms:catalog_manage"))):
        for item in body.items:
            await db.course_contents.update_one({"id": item.id, "course_id": course_id}, {"$set": {"order": item.order}})
        await log_audit(db, user, action="update", entity="course_content", entity_id="bulk_reorder",
                         new_value={"course_id": course_id, "items": [i.model_dump() for i in body.items]}, request=request)
        return {"status": "reordered", "count": len(body.items)}

    @api_router.delete("/courses/{course_id}/contents/{content_id}")
    async def delete_course_content(course_id: str, content_id: str, request: Request,
                                     user=Depends(require_permission("lms:catalog_manage"))):
        old = await db.course_contents.find_one({"id": content_id, "course_id": course_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "İçerik bulunamadı")
        await db.course_contents.delete_one({"id": content_id})
        await log_audit(db, user, action="delete", entity="course_content", entity_id=content_id, old_value=old, request=request)
        return {"status": "deleted"}

    # ---------------- Atama ----------------
    @api_router.post("/courses/{course_id}/assign")
    async def assign_course(course_id: str, body: CourseAssignmentCreate, request: Request,
                             user=Depends(require_permission("lms:assign"))):
        course = await db.courses.find_one({"id": course_id}, {"_id": 0})
        if not course:
            raise HTTPException(404, "Eğitim bulunamadı")
        if not course.get("is_active", True):
            raise HTTPException(400, "Pasif bir eğitim atanamaz")
        if body.target_type not in TARGET_TYPES:
            raise HTTPException(400, f"Geçersiz hedef tipi: {body.target_type}")

        user_ids = await _resolve_target_user_ids(db, user, body.target_type, body.target_value)
        if not user_ids:
            raise HTTPException(400, "Bu hedefe uyan hiç kullanıcı bulunamadı")

        assignment = {
            "id": str(uuid.uuid4()), "course_id": course_id, "target_type": body.target_type,
            "target_value": body.target_value, "note": body.note,
            "resolved_user_count": len(user_ids),
            "assigned_by": user.get("full_name") or user.get("email"),
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.course_assignments.insert_one(assignment)
        assignment.pop("_id", None)

        now = datetime.now(timezone.utc)
        expires_at = None
        if course.get("validity_months"):
            # basit ay ekleme (takvim kütüphanesi eklenmedi — 30 gün/ay yaklaşıklığı,
            # entitlement.py'nin "formül" sadeleştirmesiyle AYNI aile bir bilinçli tercih)
            from datetime import timedelta
            expires_at = (now + timedelta(days=30 * course["validity_months"])).isoformat()

        new_count = 0
        for uid in user_ids:
            existing = await db.user_course_status.find_one({"course_id": course_id, "user_id": uid})
            if existing:
                continue
            await db.user_course_status.insert_one({
                "id": str(uuid.uuid4()), "course_id": course_id, "user_id": uid,
                "assignment_id": assignment["id"], "status": "atandi",
                "content_progress": {}, "assigned_at": now.isoformat(),
                "started_at": None, "completed_at": None, "expires_at": expires_at,
            })
            new_count += 1

        await log_audit(db, user, action="assign", entity="course", entity_id=course_id,
                         new_value={"target_type": body.target_type, "resolved": len(user_ids), "new_assignments": new_count},
                         request=request)
        return {"assignment": assignment, "resolved_user_count": len(user_ids), "new_assignments": new_count}

    @api_router.get("/courses/{course_id}/assignments")
    async def list_course_assignments(course_id: str, user=Depends(require_permission("lms:status_view_all"))):
        return await db.course_assignments.find({"course_id": course_id}, {"_id": 0}).sort("assigned_at", -1).to_list(200)

    @api_router.get("/courses/{course_id}/status-summary")
    async def course_status_summary(course_id: str, user=Depends(require_permission("lms:status_view_all"))):
        docs = await db.user_course_status.find({"course_id": course_id}, {"_id": 0}).to_list(5000)
        summary = {k: 0 for k in STATUS_LABELS}
        for d in docs:
            summary[_effective_status(d)] = summary.get(_effective_status(d), 0) + 1
        return {"course_id": course_id, "total": len(docs), "by_status": summary}

    # ---------------- Kullanıcının Kendi Eğitimleri (herhangi bir rol) ----------------
    @api_router.get("/lms/my-courses")
    async def my_courses(user=Depends(current_user), _feat=Depends(require_feature("lms"))):
        docs = await db.user_course_status.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
        out = []
        for d in docs:
            course = await db.courses.find_one({"id": d["course_id"]}, {"_id": 0})
            if not course:
                continue
            course["contents"] = await db.course_contents.find({"course_id": d["course_id"]}, {"_id": 0}).sort("order", 1).to_list(200)
            d["status"] = _effective_status(d)
            d["course"] = course
            out.append(d)
        # zorunlu VE tamamlanmamış eğitimler dashboard'da öncelikli (kabul kriteri)
        out.sort(key=lambda d: (not d["course"].get("is_mandatory"), d["status"] == "tamamlandi"))
        return out

    @api_router.get("/lms/my-courses/{status_id}")
    async def my_course_detail(status_id: str, user=Depends(current_user)):
        doc = await db.user_course_status.find_one({"id": status_id}, {"_id": 0})
        if not doc or doc["user_id"] != user["id"]:
            raise HTTPException(404, "Kayıt bulunamadı")
        course = await db.courses.find_one({"id": doc["course_id"]}, {"_id": 0})
        contents = await db.course_contents.find({"course_id": doc["course_id"]}, {"_id": 0}).sort("order", 1).to_list(200)
        doc["status"] = _effective_status(doc)
        doc["course"] = course
        doc["contents"] = contents
        return doc

    @api_router.post("/lms/my-courses/{status_id}/start")
    async def start_course(status_id: str, request: Request, user=Depends(current_user)):
        doc = await db.user_course_status.find_one({"id": status_id}, {"_id": 0})
        if not doc or doc["user_id"] != user["id"]:
            raise HTTPException(404, "Kayıt bulunamadı")
        if _effective_status(doc) != "atandi":
            raise HTTPException(400, f"'{STATUS_LABELS[_effective_status(doc)]}' durumundaki bir eğitim başlatılamaz")
        updates = {"status": "devam_ediyor", "started_at": datetime.now(timezone.utc).isoformat()}
        await db.user_course_status.update_one({"id": status_id}, {"$set": updates})
        new = await db.user_course_status.find_one({"id": status_id}, {"_id": 0})
        await log_audit(db, user, action="status_change", entity="user_course_status", entity_id=status_id,
                         old_value={"status": doc["status"]}, new_value={"status": new["status"]}, request=request)
        return new

    @api_router.post("/lms/my-courses/{status_id}/contents/{content_id}/complete")
    async def complete_content(status_id: str, content_id: str, body: ContentCompleteRequest, request: Request,
                                user=Depends(current_user)):
        doc = await db.user_course_status.find_one({"id": status_id}, {"_id": 0})
        if not doc or doc["user_id"] != user["id"]:
            raise HTTPException(404, "Kayıt bulunamadı")
        if _effective_status(doc) not in ("atandi", "devam_ediyor"):
            raise HTTPException(400, f"'{STATUS_LABELS[_effective_status(doc)]}' durumundaki bir eğitimde ilerleme kaydedilemez")
        content = await db.course_contents.find_one({"id": content_id, "course_id": doc["course_id"]})
        if not content:
            raise HTTPException(404, "İçerik bu eğitime ait değil")

        progress = dict(doc.get("content_progress") or {})
        progress[content_id] = body.completed
        updates: Dict[str, Any] = {"content_progress": progress}
        if doc["status"] == "atandi":
            updates["status"] = "devam_ediyor"
            updates["started_at"] = doc.get("started_at") or datetime.now(timezone.utc).isoformat()

        all_contents = await db.course_contents.find({"course_id": doc["course_id"]}, {"_id": 0, "id": 1}).to_list(200)
        all_done = all(progress.get(c["id"]) for c in all_contents) if all_contents else False
        if all_done:
            # IT-30'da quiz varsa bu otomatik "tamamlandi" ataması quiz sonucuna
            # göre koşullanacak (bu iterasyonda quiz yok, hepsi bittiyse tamam).
            updates["status"] = "tamamlandi"
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()

        await db.user_course_status.update_one({"id": status_id}, {"$set": updates})
        new = await db.user_course_status.find_one({"id": status_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="user_course_status", entity_id=status_id,
                         old_value={"status": doc["status"]}, new_value={"status": new["status"]}, request=request)
        return new

    @api_router.post("/lms/recompute-expirations")
    async def recompute_expirations(request: Request, user=Depends(require_permission("lms:status_view_all"))):
        """"Süresi Doldu" kontrolünü kalıcı hale getiren tick — support.py/
        campaigns.py'deki run-scheduled kalıbıyla AYNI aile, gerçek bir OS
        cron KURULU DEĞİL (bkz. modül docstring'i)."""
        now = datetime.now(timezone.utc).isoformat()
        candidates = await db.user_course_status.find(
            {"status": {"$in": ["atandi", "devam_ediyor"]}, "expires_at": {"$ne": None, "$lte": now}}, {"_id": 0},
        ).to_list(5000)
        for c in candidates:
            await db.user_course_status.update_one({"id": c["id"]}, {"$set": {"status": "suresi_doldu"}})
        if candidates:
            await log_audit(db, user, action="update", entity="user_course_status", entity_id="bulk_expire",
                             new_value={"count": len(candidates)}, request=request)
        return {"expired": len(candidates)}
