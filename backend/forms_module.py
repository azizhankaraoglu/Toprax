"""
SAHA VERİ TOPLAMA MODÜLÜ (M18)
================================
Anket vari, GPS+foto+video destekli form sistemi.

İş Akışı:
1. Admin (key user) form tasarlar (alan ekle/sırala/sil)
2. Form 3 modda paylaşılır:
   - PRIVATE: belirli çiftçilere atanır, mobil bildirim gider
   - INTERNAL: tüm kooperatif kullanıcıları (login gerekli)
   - PUBLIC: token'lı link, herkes doldurabilir (login gerekmez)
3. Çiftçi/saha kullanıcısı formu mobilden doldurur (GPS otomatik)
4. Admin yanıtları dashboard'ta görür (widget'lı)

Alan tipleri:
- text, textarea, number, select, multiselect, yesno, rating, date, gps, photo, video, signature
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import secrets
from tenant_context import current_tenant_id
from config_service import ALLOW_DATA_SEEDING


def register_form_routes(api_router, db, current_user, is_admin, security):
    """Form modülü endpoint'lerini kaydet"""
    
    # =====================================================================
    # MODELLER
    # =====================================================================
    
    class FormField(BaseModel):
        id: str                                              # field-uuid
        type: str                                            # text/textarea/number/select/multiselect/yesno/rating/date/gps/photo/video/signature
        label: str                                           # "Tarladaki yabancı ot durumu"
        required: bool = False
        placeholder: Optional[str] = None
        options: Optional[List[str]] = None                  # select/multiselect için
        min: Optional[float] = None
        max: Optional[float] = None
        order: int = 0
    
    class FormCreate(BaseModel):
        title: str
        description: Optional[str] = None
        fields: List[Dict[str, Any]]
        share_mode: str = "private"                          # private/internal/public
        category: Optional[str] = "genel"                    # tarla denetimi, çiftçi anketi, hasat raporu vb.
        target_role: Optional[str] = None                    # ciftci/saha/her
    
    class FormUpdate(BaseModel):
        title: Optional[str] = None
        description: Optional[str] = None
        fields: Optional[List[Dict[str, Any]]] = None
        share_mode: Optional[str] = None
        is_active: Optional[bool] = None
    
    class FormAssign(BaseModel):
        farmer_ids: List[str] = []
        user_ids: List[str] = []
        send_notification: bool = True
        due_date: Optional[str] = None
    
    class FormResponseSubmit(BaseModel):
        form_id: str
        answers: Dict[str, Any]                              # field_id -> value
        gps_lat: Optional[float] = None
        gps_lng: Optional[float] = None
        public_token: Optional[str] = None                   # public form için
    
    # =====================================================================
    # FORM CRUD (Admin)
    # =====================================================================
    
    @api_router.post("/forms")
    async def create_form(body: FormCreate, user=Depends(current_user)):
        """Yeni form oluştur (form builder'dan)"""
        if not is_admin(user):
            raise HTTPException(403, "Form oluşturma yetkisi gerekli")
        
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_by"] = user["id"]
        doc["creator_name"] = user.get("full_name", "")
        doc["is_active"] = True
        doc["response_count"] = 0
        doc["public_token"] = secrets.token_urlsafe(12) if body.share_mode == "public" else None
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        
        await db.forms.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @api_router.get("/forms")
    async def list_forms(user=Depends(current_user)):
        """Form listesi"""
        if is_admin(user):
            docs = await db.forms.find({}, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
        else:
            # Çiftçi sadece atanmış olanları görür
            assignments = await db.form_assignments.find(
                {"farmer_id": user.get("farmer_id")}, {"_id": 0}
            ).to_list(500)
            form_ids = [a["form_id"] for a in assignments]
            # + internal formlar
            docs = await db.forms.find(
                {"$or": [{"id": {"$in": form_ids}}, {"share_mode": "internal"}], "is_active": True},
                {"_id": 0}
            ).sort([("created_at", -1)]).to_list(500)
        
        # Her form için response sayısını hesapla
        for d in docs:
            d["response_count"] = await db.form_responses.count_documents({"form_id": d["id"]})
        return docs
    
    @api_router.get("/forms/{form_id}")
    async def get_form(form_id: str, user=Depends(current_user)):
        """Tek form detayı"""
        f = await db.forms.find_one({"id": form_id}, {"_id": 0})
        if not f:
            raise HTTPException(404, "Form bulunamadı")
        f["response_count"] = await db.form_responses.count_documents({"form_id": form_id})
        return f

    @api_router.put("/forms/{form_id}")
    async def update_form(form_id: str, body: FormUpdate, user=Depends(current_user)):
        """Form güncelle"""
        if not is_admin(user):
            raise HTTPException(403, "Yetkiniz yok")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.forms.update_one({"id": form_id}, {"$set": updates})
        return await db.forms.find_one({"id": form_id}, {"_id": 0})
    
    @api_router.delete("/forms/{form_id}")
    async def delete_form(form_id: str, user=Depends(current_user)):
        if not is_admin(user):
            raise HTTPException(403, "Yetkiniz yok")
        await db.forms.delete_one({"id": form_id})
        await db.form_responses.delete_many({"form_id": form_id})
        await db.form_assignments.delete_many({"form_id": form_id})
        return {"status": "deleted"}

    # =====================================================================
    # FORM ATAMA
    # =====================================================================
    
    @api_router.post("/forms/{form_id}/assign")
    async def assign_form(form_id: str, body: FormAssign, user=Depends(current_user)):
        """Form belirli çiftçilere/kullanıcılara atanır + bildirim gönderir"""
        if not is_admin(user):
            raise HTTPException(403, "Yetkiniz yok")
        
        form = await db.forms.find_one({"id": form_id}, {"_id": 0})
        if not form:
            raise HTTPException(404, "Form bulunamadı")
        
        # Atamaları kaydet
        assignments = []
        for fid in body.farmer_ids:
            assignments.append({
                "id": str(uuid.uuid4()),
                "form_id": form_id,
                "farmer_id": fid,
                "due_date": body.due_date,
                "status": "atandı",
                "assigned_by": user["id"],
                "assigned_at": datetime.now(timezone.utc).isoformat()
            })
        if assignments:
            await db.form_assignments.insert_many(assignments)
        
        # Bildirim oluştur (her çiftçi için)
        if body.send_notification:
            notifs = []
            for fid in body.farmer_ids:
                notifs.append({
                    "id": str(uuid.uuid4()),
                    "type": "form_atandı",
                    "title": f"Yeni görev: {form['title']}",
                    "message": form.get("description", "Lütfen formu doldurun"),
                    "channel": "push",
                    "status": "gönderildi",
                    "farmer_id": fid,
                    "form_id": form_id,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
            if notifs:
                await db.notifications.insert_many(notifs)
        
        return {"assigned": len(assignments), "notifications": len(body.farmer_ids) if body.send_notification else 0}

    # =====================================================================
    # PUBLIC FORM (token'la erişim)
    # =====================================================================
    
    @api_router.get("/public/forms/{token}")
    async def get_public_form(token: str):
        """Public form — login gerekmez"""
        form = await db.forms.find_one({"public_token": token, "share_mode": "public"}, {"_id": 0})
        if not form:
            raise HTTPException(404, "Form bulunamadı veya yayında değil")
        return form
    
    @api_router.post("/public/forms/{token}/submit")
    async def submit_public_form(token: str, body: FormResponseSubmit):
        """Public form yanıtı"""
        form = await db.forms.find_one({"public_token": token, "share_mode": "public"})
        if not form:
            raise HTTPException(404, "Form yayında değil")
        
        doc = {
            "id": str(uuid.uuid4()),
            "form_id": form["id"],
            "tenant_id": form.get("tenant_id"),   # context yok (anonim istek) — formun kendi tenant'ından al
            "answers": body.answers,
            "gps_lat": body.gps_lat,
            "gps_lng": body.gps_lng,
            "submitted_by": "public",
            "submitter_role": "anonim",
            "submitter_name": body.answers.get("__name", "Anonim"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.form_responses.insert_one(doc)
        doc.pop("_id", None)
        return {"status": "ok", "response_id": doc["id"]}
    
    # =====================================================================
    # FORM RESPONSE (login'li)
    # =====================================================================
    
    @api_router.post("/forms/{form_id}/submit")
    async def submit_form(form_id: str, body: FormResponseSubmit, user=Depends(current_user)):
        """Form yanıtı (login'li kullanıcı)"""
        form = await db.forms.find_one({"id": form_id})
        if not form:
            raise HTTPException(404, "Form bulunamadı")
        
        doc = {
            "id": str(uuid.uuid4()),
            "form_id": form_id,
            "answers": body.answers,
            "gps_lat": body.gps_lat,
            "gps_lng": body.gps_lng,
            "submitted_by": user["id"],
            "submitter_role": user.get("role"),
            "submitter_name": user.get("full_name"),
            "farmer_id": user.get("farmer_id"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.form_responses.insert_one(doc)
        
        # Atama varsa durumunu güncelle
        if user.get("farmer_id"):
            await db.form_assignments.update_one(
                {"form_id": form_id, "farmer_id": user["farmer_id"]},
                {"$set": {"status": "tamamlandı", "completed_at": datetime.now(timezone.utc).isoformat()}}
            )
        
        doc.pop("_id", None)
        return {"status": "ok", "response_id": doc["id"]}
    
    @api_router.get("/forms/{form_id}/responses")
    async def list_form_responses(form_id: str, user=Depends(current_user)):
        """Form yanıtlarını listele (admin/yönetici)"""
        if not is_admin(user):
            raise HTTPException(403, "Yetkiniz yok")
        docs = await db.form_responses.find(
            {"form_id": form_id}, {"_id": 0}
        ).sort([("created_at", -1)]).to_list(5000)
        return docs
    
    # =====================================================================
    # FORM ANALİTİK / DASHBOARD
    # =====================================================================
    
    @api_router.get("/forms/{form_id}/analytics")
    async def form_analytics(form_id: str, user=Depends(current_user)):
        """
        Form yanıtlarından otomatik widget'lar:
        - Toplam yanıt sayısı
        - Her alan için uygun görselleştirme verisi (sayı → ort/min/max, select → dağılım, gps → harita noktaları)
        """
        if not is_admin(user):
            raise HTTPException(403, "Yetkiniz yok")
        
        form = await db.forms.find_one({"id": form_id}, {"_id": 0})
        if not form:
            raise HTTPException(404, "Form bulunamadı")
        
        responses = await db.form_responses.find({"form_id": form_id}, {"_id": 0}).to_list(10000)
        
        widgets = []
        # Genel istatistik
        widgets.append({
            "type": "stat",
            "title": "Toplam Yanıt",
            "value": len(responses)
        })
        
        # Son 7 gün
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        last_7d = sum(1 for r in responses if (now - datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))).days <= 7)
        widgets.append({"type": "stat", "title": "Son 7 Gün", "value": last_7d})
        
        # GPS noktaları
        gps_points = [
            {"lat": r["gps_lat"], "lng": r["gps_lng"], "id": r["id"]}
            for r in responses if r.get("gps_lat") and r.get("gps_lng")
        ]
        if gps_points:
            widgets.append({"type": "map", "title": "Konum Haritası", "points": gps_points})
        
        # Her field için uygun widget
        for field in form.get("fields", []):
            fid = field.get("id")
            ftype = field.get("type")
            answers = [r["answers"].get(fid) for r in responses if r.get("answers") and fid in r["answers"]]
            answers = [a for a in answers if a is not None and a != ""]
            
            if not answers:
                continue
            
            if ftype in ("select", "yesno"):
                # Dağılım
                dist = {}
                for a in answers:
                    key = str(a)
                    dist[key] = dist.get(key, 0) + 1
                widgets.append({
                    "type": "pie",
                    "title": field["label"],
                    "data": [{"name": k, "value": v} for k, v in dist.items()]
                })
            elif ftype == "multiselect":
                dist = {}
                for a in answers:
                    if isinstance(a, list):
                        for item in a:
                            dist[item] = dist.get(item, 0) + 1
                widgets.append({
                    "type": "bar",
                    "title": field["label"],
                    "data": [{"name": k, "value": v} for k, v in dist.items()]
                })
            elif ftype in ("number", "rating"):
                nums = []
                for a in answers:
                    try: nums.append(float(a))
                    except: pass
                if nums:
                    widgets.append({
                        "type": "stat-trio",
                        "title": field["label"],
                        "avg": round(sum(nums) / len(nums), 2),
                        "min": round(min(nums), 2),
                        "max": round(max(nums), 2),
                        "count": len(nums)
                    })
            elif ftype in ("text", "textarea"):
                # Son 5 yanıt örneği
                widgets.append({
                    "type": "text-list",
                    "title": field["label"],
                    "samples": [str(a)[:200] for a in answers[-5:]]
                })
            elif ftype == "photo":
                widgets.append({
                    "type": "photo-gallery",
                    "title": field["label"],
                    "photos": [a for a in answers if isinstance(a, str) and a.startswith("data:")][:12]
                })
        
        return {
            "form": form,
            "total_responses": len(responses),
            "widgets": widgets
        }
    
    # =====================================================================
    # ÇİFTÇİ — Atanmış formlar
    # =====================================================================
    
    @api_router.get("/farmer/my-forms")
    async def my_assigned_forms(user=Depends(current_user)):
        """Çiftçinin atanmış formları"""
        if user.get("role") != "ciftci":
            raise HTTPException(403, "Sadece çiftçi")
        
        assignments = await db.form_assignments.find(
            {"farmer_id": user.get("farmer_id")}, {"_id": 0}
        ).sort([("assigned_at", -1)]).to_list(100)
        
        result = []
        for a in assignments:
            form = await db.forms.find_one({"id": a["form_id"]}, {"_id": 0})
            if form:
                result.append({**a, "form": form})
        return result
    
    # =====================================================================
    # SEED — Demo formlar
    # =====================================================================
    
    @api_router.post("/admin/seed-forms")
    async def seed_demo_forms(user=Depends(current_user)):
        """Demo formlar yükle

        P0 güvenlik düzeltmesi: bu uç önceden kimlik doğrulaması
        gerektirmiyordu. Artık giriş yapmış bir yönetici (is_admin) ve
        ALLOW_DATA_SEEDING=true (üretimde varsayılan kapalı) gerektirir.
        """
        if not ALLOW_DATA_SEEDING:
            raise HTTPException(403, "Demo veri yükleme bu ortamda kapalı (ALLOW_DATA_SEEDING=false)")
        if not is_admin(user) and user.get("role") != "platform_admin":
            raise HTTPException(403, "Bu işlem için yönetici yetkisi gerekir")
        reset_token = None
        if current_tenant_id.get() is None:
            default_tenant = await db.tenants.find_one({"slug": "default"}, {"_id": 0})
            if default_tenant:
                reset_token = current_tenant_id.set(default_tenant["id"])
        try:
            return await _run_seed_demo_forms()
        finally:
            if reset_token is not None:
                current_tenant_id.reset(reset_token)

    async def _run_seed_demo_forms():
        if await db.forms.count_documents({}) > 0:
            return {"status": "already_seeded_forms"}
        
        admin = await db.users.find_one({"role": "super_admin"})
        farmers = await db.farmers.find({}, {"_id": 0}).limit(50).to_list(50)
        
        # Form 1: Çiftçi Memnuniyet Anketi (PUBLIC)
        form1 = {
            "id": str(uuid.uuid4()),
            "title": "Çiftçi Memnuniyet Anketi 2025",
            "description": "Kooperatifimizden aldığınız hizmeti değerlendirin",
            "fields": [
                {"id": "f1", "type": "text", "label": "Adınız (opsiyonel)", "required": False, "order": 1},
                {"id": "f2", "type": "rating", "label": "Genel memnuniyet (1-5)", "required": True, "min": 1, "max": 5, "order": 2},
                {"id": "f3", "type": "select", "label": "En çok kullandığınız hizmet", "required": True,
                 "options": ["Avans/Kredi", "Gübre/Tohum tedariki", "Hasat lojistiği", "Eğitim", "Teknik destek"], "order": 3},
                {"id": "f4", "type": "yesno", "label": "Önümüzdeki yıl da çalışmak ister misiniz?", "required": True, "order": 4},
                {"id": "f5", "type": "textarea", "label": "Önerileriniz", "required": False, "order": 5},
                {"id": "f6", "type": "gps", "label": "Konum (otomatik)", "required": False, "order": 6}
            ],
            "share_mode": "public",
            "category": "memnuniyet",
            "is_active": True,
            "public_token": "memnuniyet2025",
            "created_by": admin["id"], "creator_name": admin["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Form 2: Tarla Denetim Formu (PRIVATE — saha mühendislerine)
        form2 = {
            "id": str(uuid.uuid4()),
            "title": "Haftalık Tarla Denetimi",
            "description": "Saha mühendisleri her hafta doldurmalıdır",
            "fields": [
                {"id": "g1", "type": "text", "label": "Parsel kodu", "required": True, "order": 1},
                {"id": "g2", "type": "yesno", "label": "Hastalık belirtisi var mı?", "required": True, "order": 2},
                {"id": "g3", "type": "select", "label": "Bitki gelişim aşaması", "required": True,
                 "options": ["Ekim sonrası", "Çimlenme", "Yaprak gelişimi", "Çiçeklenme", "Olgunlaşma", "Hasat"], "order": 3},
                {"id": "g4", "type": "number", "label": "Tahmini yabancı ot yoğunluğu (%)", "min": 0, "max": 100, "order": 4},
                {"id": "g5", "type": "photo", "label": "Tarla fotoğrafı", "required": True, "order": 5},
                {"id": "g6", "type": "textarea", "label": "Detaylı notlar", "required": False, "order": 6},
                {"id": "g7", "type": "gps", "label": "Konum (otomatik)", "required": True, "order": 7}
            ],
            "share_mode": "internal",
            "category": "tarla denetimi",
            "is_active": True,
            "created_by": admin["id"], "creator_name": admin["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Form 3: Hasat Sonu Raporu (PRIVATE çiftçilere atanır)
        form3 = {
            "id": str(uuid.uuid4()),
            "title": "Hasat Sonu Geri Bildirim",
            "description": "Hasat tamamlandıktan sonra lütfen doldurunuz",
            "fields": [
                {"id": "h1", "type": "number", "label": "Tahmini ton/dekar verim", "min": 0, "order": 1},
                {"id": "h2", "type": "multiselect", "label": "Karşılaştığınız sorunlar",
                 "options": ["Kuraklık", "Sel/aşırı yağış", "Don zararı", "Hastalık", "Zararlı böcek", "İşgücü eksikliği", "Sorun yok"], "order": 2},
                {"id": "h3", "type": "rating", "label": "Tohum kalitesi (1-5)", "min": 1, "max": 5, "order": 3},
                {"id": "h4", "type": "photo", "label": "Hasat fotoğrafı", "required": False, "order": 4},
                {"id": "h5", "type": "textarea", "label": "Eklemek istedikleriniz", "required": False, "order": 5}
            ],
            "share_mode": "private",
            "category": "hasat raporu",
            "is_active": True,
            "created_by": admin["id"], "creator_name": admin["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.forms.insert_many([form1, form2, form3])
        
        # Form3'ü tüm çiftçilere ata (demo için)
        assignments = []
        for f in farmers[:30]:
            assignments.append({
                "id": str(uuid.uuid4()),
                "form_id": form3["id"],
                "farmer_id": f["id"],
                "status": "atandı",
                "assigned_by": admin["id"],
                "assigned_at": datetime.now(timezone.utc).isoformat()
            })
        if assignments:
            await db.form_assignments.insert_many(assignments)
        
        return {
            "status": "forms_seeded",
            "forms_count": 3,
            "assignments_count": len(assignments),
            "public_form_link": f"/form-doldur/{form1['public_token']}"
        }
