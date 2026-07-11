"""
=====================================================================
TabSIS — Dosya Depolama Soyutlaması (IT-04)
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


def _safe_ext(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Desteklenmeyen dosya türü ({ext or 'uzantısız'}). "
                                  f"İzin verilenler: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    return ext


async def save_upload(file: UploadFile, subfolder: str) -> dict:
    """Dosyayı diske kaydeder, meta bilgi (id, stored_name, url, size_bytes, content_type) döner."""
    ext = _safe_ext(file.filename)
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"Dosya çok büyük (maksimum {MAX_FILE_SIZE_MB}MB)")

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
        "content_type": file.content_type,
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
            {"id": payload.get("user_id")}, {"_id": 0, "password": 0}
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
