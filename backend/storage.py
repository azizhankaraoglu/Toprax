"""
=====================================================================
Toprax — Dosya Depolama Soyutlaması (IT-04)
=====================================================================
Şimdilik dosyalar yerel diske (`backend/uploads/`) yazılır. İleride
S3/MinIO gibi bir sağlayıcıya geçilirse SADECE bu dosya değişir —
çağıran kod (`save_upload`/`delete_upload_file`) aynı kalır (bkz.
ROADMAP.md "Uyarlama Kararları" — Object Storage soyutlaması).

Dosya meta verisi (`uploads` koleksiyonu) `(module, entity_id)` ile
ilişkilendirilir; opsiyonel `field_key` verilirse belirli bir dinamik
alanın (field_definitions field_type="file"/"image"/"multifile")
değeri olarak kullanılır — verilmezse genel "Belgeler" sekmesine ait
serbest bir dokümandır. Tek depolama, iki kullanım biçimi.

Tenant izolasyonu: `db` parametresi (diğer modüllerde olduğu gibi)
TenantScopedDB sarmalayıcısıdır — meta veri sorguları otomatik
tenant'a göre filtrelenir. Fiziksel dosya diskte tahmin edilemez bir
UUID adıyla saklanır (basit erişim koruması); indirme endpoint'i
kimlik doğrulaması ister VE (P0 güvenlik düzeltmesi) `uploads`
kaydının tenant'ının çağıranın tenant'ıyla eşleştiğini doğrular —
`?token=` ile gelen isteklerde `tenant_context_middleware` Authorization
header'ı görmediği için `current_tenant_id` set edilmez, bu yüzden
tenant eşleşmesi burada AYRICA elle kontrol edilir (TenantScopedDB'nin
otomatik filtresine güvenilemez, bkz. `_authorize_file_access`).
"""
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse

from security import decode_token

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",           # resim
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",            # doküman
}
MAX_FILE_SIZE_MB = 10

# =====================================================================
# BULGU 3 (Orta) düzeltmesi — GERÇEK içerik tipi doğrulaması
# =====================================================================
# Uzantı allow-list'i TEK BAŞINA yetmez: kötü niyetli içerik `shell.jpg`
# olarak yeniden adlandırılıp uzantı kontrolünden geçebiliyordu. Artık
# dosyanın ilk baytlarındaki "sihirli bayt" (magic byte) imzasından gerçek
# tip tespit edilir ve beyan edilen uzantıyla uyuşması ZORUNLUDUR. Ayrıca
# saklanan content_type istemcinin beyanına değil, tespit sonucuna göre
# belirlenir (istemci content_type'ı spooflanabilir).

# Beyan edilen uzantı -> kabul edilen içerik "türü" (magic'ten çıkan)
_EXT_ALLOWED_KIND = {
    ".jpg": {"jpg"}, ".jpeg": {"jpg"}, ".png": {"png"},
    ".gif": {"gif"}, ".webp": {"webp"}, ".pdf": {"pdf"},
    ".docx": {"zip"}, ".xlsx": {"zip"},         # OOXML = ZIP kabı
    ".doc": {"ole"}, ".xls": {"ole"},           # eski Office = OLE2 kabı
}

# Beyan edilen uzantı -> saklanacak (güvenilir) MIME tipi
_EXT_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword", ".xls": "application/vnd.ms-excel",
}


def _detect_kind(contents: bytes) -> Optional[str]:
    """İlk baytlardan gerçek dosya türünü döndürür (bilinmiyorsa None)."""
    b = contents[:16]
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if b[:4] == b"RIFF" and contents[8:12] == b"WEBP":
        return "webp"
    if b[:4] == b"%PDF":
        return "pdf"
    if b[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return "zip"      # docx / xlsx (OOXML)
    if b[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "ole"      # eski doc / xls
    return None


def _safe_ext(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Desteklenmeyen dosya türü ({ext or 'uzantısız'}). "
                                  f"İzin verilenler: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    return ext


def _verify_content(ext: str, contents: bytes) -> str:
    """Sihirli bayt doğrulaması: beyan edilen uzantı ile gerçek içerik
    uyuşmuyorsa 400 döner. Döndürdüğü: güvenilir content_type."""
    kind = _detect_kind(contents)
    allowed = _EXT_ALLOWED_KIND.get(ext, set())
    if kind is None or kind not in allowed:
        raise HTTPException(
            400,
            "Dosya içeriği beyan edilen türle uyuşmuyor. Uzantısı değiştirilmiş "
            f"veya bozuk bir dosya olabilir ({ext}).",
        )
    return _EXT_MIME.get(ext, "application/octet-stream")


async def save_upload(file: UploadFile, subfolder: str) -> dict:
    """Dosyayı diske kaydeder, meta bilgi (id, stored_name, url, size_bytes, content_type) döner."""
    ext = _safe_ext(file.filename)
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"Dosya çok büyük (maksimum {MAX_FILE_SIZE_MB}MB)")

    # BULGU 3: gerçek içerik tipini doğrula (uzantı yeniden adlandırma bypass'ı)
    verified_content_type = _verify_content(ext, contents)

    file_id = str(uuid.uuid4())
    stored_name = f"{file_id}{ext}"
    dest_dir = UPLOAD_DIR / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    with open(dest_dir / stored_name, "wb") as f:
        f.write(contents)

    return {
        "file_id": file_id,
        "stored_name": stored_name,
        "url": f"/api/uploads/file/{subfolder}/{stored_name}",
        "size_bytes": len(contents),
        "content_type": verified_content_type,   # BULGU 3: istemcinin beyanı değil, tespit
    }


def delete_upload_file(subfolder: str, stored_name: str) -> None:
    path = UPLOAD_DIR / subfolder / stored_name
    if path.exists():
        path.unlink()


def register_storage_routes(api_router: APIRouter, db, current_user, log_audit=None):

    async def _authorize_file_download(request: Request, subfolder: str, stored_name: str,
                                        token: Optional[str] = Query(None)) -> dict:
        """
        Dosya indirme endpoint'i için kimlik doğrulama + yetkilendirme.
        <img src>/<a href> gibi tarayıcı navigasyonları Authorization header'ı
        GÖNDEREMEZ — bu yüzden Authorization header'ı yoksa ?token= query
        param'ı kabul edilir (bkz. modül docstring'i).

        P0 düzeltmesi: önceden sadece JWT imzası/süresi doğrulanıyordu —
        kullanıcının aktif olup olmadığı VE dosyanın ait olduğu tenant hiç
        kontrol edilmiyordu, yani geçerli herhangi bir token BAŞKA bir
        tenant'ın/kullanıcının dosyasını indirebiliyordu. Artık: (1) kullanıcı
        DB'den çekilir ve aktif olduğu doğrulanır, (2) ilgili `uploads` kaydı
        bulunup tenant'ı çağıranın token'ındaki tenant_id ile karşılaştırılır
        (`current_tenant_id` context'ine güvenilmez — bkz. yukarıdaki not).
        """
        if "/" in subfolder or ".." in subfolder or "/" in stored_name or ".." in stored_name:
            raise HTTPException(400, "Geçersiz dosya yolu")

        auth_header = request.headers.get("authorization", "")
        raw_token = auth_header[7:] if auth_header.startswith("Bearer ") else token
        if not raw_token:
            raise HTTPException(401, "Token gerekli")
        try:
            payload = decode_token(raw_token)
        except Exception:
            raise HTTPException(401, "Geçersiz veya süresi dolmuş token")
        if payload.get("type") == "refresh":
            raise HTTPException(401, "Refresh token bu uçta kullanılamaz")

        user = await db.users.find_one(
            {"id": payload.get("user_id")}, {"_id": 0, "password": 0, "totp_secret": 0}
        )
        if not user:
            raise HTTPException(401, "Kullanıcı yok")
        if user.get("active") is False:
            raise HTTPException(403, "Hesabınız pasif duruma alınmış")

        upload_doc = await db.uploads.find_one(
            {"module": subfolder, "stored_name": stored_name}, {"_id": 0}
        )
        if not upload_doc:
            raise HTTPException(404, "Dosya bulunamadı")

        # platform_admin tenant'lar-üstü çalışır; diğer HERKES sadece kendi
        # tenant'ının dosyasına erişebilir. Kayıt/mevcut-token tenant'ı
        # eşleşmiyorsa 404 (403 değil — dosyanın varlığını dahi sızdırmamak için).
        if user.get("role") != "platform_admin" and upload_doc.get("tenant_id") != payload.get("tenant_id"):
            raise HTTPException(404, "Dosya bulunamadı")

        return user

    @api_router.post("/uploads")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        module: str = Form(...),                # "farmers" | "parcels" | ...
        entity_id: str = Form(...),
        field_key: Optional[str] = Form(None),   # verilirse belirli bir dinamik alana bağlanır
        user=Depends(current_user),
    ):
        # God Mode Lisans limiti — depolama (MB). Dosya diske YAZILMADAN önce
        # kontrol edilir (limit aşılmışsa yazma hiç denenmez).
        tenant_id = user.get("tenant_id")
        if tenant_id:
            from platform_core import get_tenant_license
            lic = await get_tenant_license(db, tenant_id)
            if lic and lic.get("storage_limit_mb") is not None:
                agg = await db.uploads.aggregate(
                    [{"$group": {"_id": None, "total_bytes": {"$sum": "$size_bytes"}}}]
                ).to_list(1)
                used_mb = (agg[0]["total_bytes"] if agg else 0) / (1024 * 1024)
                if used_mb >= lic["storage_limit_mb"]:
                    raise HTTPException(403, f"Lisans limiti aşıldı: Depolama ({used_mb:.1f}/{lic['storage_limit_mb']} MB)")

        meta = await save_upload(file, subfolder=module)
        doc = {
            "id": meta["file_id"],
            "module": module,
            "entity_id": entity_id,
            "field_key": field_key,
            "filename": file.filename,
            "stored_name": meta["stored_name"],
            "url": meta["url"],
            "size_bytes": meta["size_bytes"],
            "content_type": meta["content_type"],
            "uploaded_by": user.get("full_name") or user.get("email"),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.uploads.insert_one(doc)
        doc.pop("_id", None)
        if log_audit:
            await log_audit(db, user, action="create", entity="upload", entity_id=doc["id"],
                             new_value={"module": module, "entity_id": entity_id, "filename": file.filename},
                             request=request)
        return doc

    @api_router.get("/uploads")
    async def list_uploads(module: str, entity_id: str, field_key: Optional[str] = None, user=Depends(current_user)):
        query = {"module": module, "entity_id": entity_id}
        if field_key is not None:
            query["field_key"] = field_key
        return await db.uploads.find(query, {"_id": 0}).sort("uploaded_at", -1).to_list(200)

    @api_router.delete("/uploads/{upload_id}")
    async def delete_upload(upload_id: str, request: Request, user=Depends(current_user)):
        doc = await db.uploads.find_one({"id": upload_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Dosya bulunamadı")
        delete_upload_file(doc["module"], doc["stored_name"])
        await db.uploads.delete_one({"id": upload_id})
        if log_audit:
            await log_audit(db, user, action="delete", entity="upload", entity_id=upload_id,
                             old_value={"filename": doc["filename"]}, request=request)
        return {"status": "deleted"}

    @api_router.get("/uploads/file/{subfolder}/{stored_name}")
    async def get_upload_file(subfolder: str, stored_name: str, _user=Depends(_authorize_file_download)):
        path = UPLOAD_DIR / subfolder / stored_name
        if not path.is_file():
            raise HTTPException(404, "Dosya bulunamadı")
        return FileResponse(path)
