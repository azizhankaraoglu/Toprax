"""
=====================================================================
Toprax — Elastik Rapor Modülü (Denetim raporu, madde #7 / Faz 6)
=====================================================================
Personelin kod yazmadan kendi raporunu tasarlayabildiği bir katman:
şablon (hangi modül, hangi kolonlar, hangi filtre, opsiyonel gruplama/
toplama) + paylaşım (kanal veya link) + periyodik gönderim.

Bilinçli tasarım kararları:

- Veri kaynağı DOĞRUDAN query_engine.execute_query() — YENİ bir sorgu
  motoru İCAT EDİLMEDİ. Bir şablonun `module`'ü Query Engine'in zaten
  bildiği bir modülse (ör. "support_requests", bu iterasyonda Query
  Engine'e eklendi) rapor onun üzerinden okur; execute_query'nin izin/
  maskeleme kontrolleri (IT-07/IT-08) rapor tarafından ASLA bypass
  edilmez — bir kullanıcı bir modülü Query Engine'den göremiyorsa o
  modülü raporlayamaz da (bkz. `_run_report`).
- Şablon sahiplik kalıbı `saved_queries.py` (IT-09) ile BİREBİR AYNI:
  özel/paylaşılan (`is_shared`), sadece sahibi düzenler/siler, admin+
  sistem katmanı (`config_service.get_system_tier`) moderasyon için
  silebilir.
- Paylaşım `communications.send_via_channel()` (IT-25/26/27) ÜZERİNDEN
  gider — Kara Liste/Tercih Merkezi/Feature Flag gate'i otomatik
  uygulanır, DUPLİKE bir gönderim mantığı yazılmadı.
  message_kind="operational" (kampanya DEĞİL — kişiye özel bir rapor
  paylaşımı, IT-27'nin kampanya/operasyonel ayrımıyla tutarlı).
- Bir "run" (report_runs), paylaşım/zamanlanmış gönderim ANINDA render
  edilmiş bir SNAPSHOT'tır (canlı sorgu değil) — public link (anonim,
  tenant context'siz) erişiminde execute_query'yi (izin kontrolü user
  ister) tekrar çalıştırmak mümkün/güvenli olmadığından, ROADMAP'in
  `report_runs` veri modelindeki "stored_name" fikri burada bir dosya
  yerine DOĞRUDAN DB'de saklanan JSON snapshot'a (`snapshot` alanı)
  sadeleştirildi — yeni bir dosya deposu/format İCAT EDİLMEDİ.
- PDF üretimi reportlab ile — extras.py/reconciliation.py'nin ASCII-yakın
  Helvetica kalıbının AKSİNE, bu YENİ modül reportlab'in KENDİ paketiyle
  gelen `Vera.ttf`'i (Bitstream Vera Sans, ayrı bir pip bağımlılığı
  GEREKTİRMEZ, serbest lisanslı) kayıt ederek GERÇEK Türkçe karakter
  desteği sağlar (çğıöşü/ÇĞİÖŞÜ) — eski PDF uçlarına dokunulmadı.
- CSV export `crud_base.py`'nin `io.StringIO`+`csv.DictWriter`+
  `StreamingResponse` kalıbıyla AYNI.
- Zamanlama: gerçek bir OS cron/Celery KURULU DEĞİL (CLAUDE.md'nin
  "Redis/RabbitMQ kurulu değil" kararıyla AYNI aile) — `POST
  /reports/run-scheduled` campaigns.py'nin tick deseniyle AYNI, ama
  TEK SEFERLİK değil TEKRARLI: her çalıştırmada `next_run_at`
  frekansa göre yeniden hesaplanır (remote_sensing/scheduler.py'nin
  `_is_due` felsefesiyle aynı aile, ayrı bir doküman).
"""
import csv
import io
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from query_engine import MODULE_COLLECTIONS, MODULE_PERMISSIONS, execute_query, FilterCondition
from communications import send_via_channel
from tenant_context import current_tenant_id

MODULE_LABELS = {
    "farmers": "Çiftçiler",
    "parcels": "Parseller",
    "contracts": "Sözleşmeler",
    "plantings": "Ekim Kayıtları",
    "soil": "Toprak Analizleri",
    "production_cycles": "Üretim Sezonları",
    "admin_areas": "İdari Alanlar",
    "field_tasks": "Saha Görevleri",
    "visits": "Ziyaretler",
    "irrigation_events": "Sulama Kayıtları",
    "operations_tasks": "Operasyon Görevleri",
    "agronomy_rules": "Agronomi Kuralları (Ekim Karar Motoru)",
    "support_requests": "Destek Talepleri",
    "users": "Kullanıcılar (Personel)",
    "ai_knowledge_records": "AI Bilgi Kütüphanesi Kayıtları",
}

AGG_OPS = {"sum": "sum", "avg": "mean", "count": "count", "min": "min", "max": "max"}
AGG_OP_LABELS = {"sum": "Toplam", "avg": "Ortalama", "count": "Adet", "min": "Minimum", "max": "Maksimum"}
FREQUENCY_DAYS = {"gunluk": 1, "haftalik": 7, "aylik": 30}
FREQUENCY_LABELS = {"gunluk": "Günlük", "haftalik": "Haftalık", "aylik": "Aylık"}


class ReportAggregation(BaseModel):
    field: str
    op: str
    label: str


class ReportTemplateCreate(BaseModel):
    name: str
    module: str
    columns: List[str] = []
    filters: List[FilterCondition] = []
    logic: str = "AND"
    sort_by: Optional[str] = None
    sort_dir: str = "asc"
    group_by: Optional[str] = None
    aggregations: List[ReportAggregation] = []
    is_shared: bool = False


class ReportTemplateUpdate(BaseModel):
    name: Optional[str] = None
    columns: Optional[List[str]] = None
    filters: Optional[List[FilterCondition]] = None
    logic: Optional[str] = None
    sort_by: Optional[str] = None
    sort_dir: Optional[str] = None
    group_by: Optional[str] = None
    aggregations: Optional[List[ReportAggregation]] = None
    is_shared: Optional[bool] = None


class ShareRecipient(BaseModel):
    contact_type: str          # "farmer" | "personnel"
    contact_id: str
    channel: str                # sms | email | whatsapp | push | voice


class ReportShareRequest(BaseModel):
    recipients: List[ShareRecipient] = []
    expires_days: int = 7
    message: Optional[str] = None


class ReportScheduleCreate(BaseModel):
    template_id: str
    frequency: str               # gunluk | haftalik | aylik
    recipients: List[ShareRecipient] = []
    active: bool = True


class ReportScheduleUpdate(BaseModel):
    frequency: Optional[str] = None
    recipients: Optional[List[ShareRecipient]] = None
    active: Optional[bool] = None


def _check_module(module: str):
    if module not in MODULE_COLLECTIONS:
        raise HTTPException(404, f"Bilinmeyen modül: {module}")


async def _run_report(db, user: dict, template: dict) -> dict:
    """Şablonu ANLIK çalıştırır (query_engine.execute_query üzerinden —
    izin/maske kontrolü ATLANMAZ). group_by verilmişse pandas ile
    gruplanır/toplanır. İlk 500 kayıtla sınırlıdır (crud_base.py'nin CSV
    export'undaki "ilk 500 kayıt" bilinçli sınırlamasıyla AYNI aile) —
    `truncated` alanı bunu dürüstçe bildirir, sessiz kesme YOK."""
    _check_module(template["module"])
    result = await execute_query(
        db, template["module"], user, template.get("filters") or [],
        logic=template.get("logic", "AND"),
        sort_by=template.get("sort_by"), sort_dir=template.get("sort_dir", "asc"),
        page=1, page_size=500,
    )
    items = result["items"]
    truncated = result["total"] > len(items)

    columns = template.get("columns") or (list(items[0].keys()) if items else [])
    group_by = template.get("group_by")
    aggregations = template.get("aggregations") or []

    if group_by and items:
        import pandas as pd
        df = pd.DataFrame(items)
        if group_by not in df.columns:
            raise HTTPException(400, f"'{group_by}' ile gruplanamaz — veri bu alanı içermiyor")
        agg_map: Dict[str, tuple] = {}
        rename: Dict[str, str] = {}
        for agg in aggregations:
            field = agg["field"] if isinstance(agg, dict) else agg.field
            op = agg["op"] if isinstance(agg, dict) else agg.op
            label = agg["label"] if isinstance(agg, dict) else agg.label
            if op not in AGG_OPS:
                raise HTTPException(400, f"Bilinmeyen agregasyon: {op}")
            col_key = f"{field}__{op}"
            if op == "count":
                agg_map[col_key] = (field if field in df.columns else group_by, "count")
            else:
                if field not in df.columns:
                    raise HTTPException(400, f"'{field}' bu modülde yok")
                agg_map[col_key] = (field, AGG_OPS[op])
            rename[col_key] = label
        if agg_map:
            grouped = df.groupby(group_by, dropna=False).agg(**agg_map).reset_index()
            grouped = grouped.rename(columns=rename)
        else:
            grouped = df.groupby(group_by, dropna=False).size().reset_index(name="Kayıt Sayısı")
        out_columns = list(grouped.columns)
        rows = grouped.to_dict(orient="records")
        return {"columns": out_columns, "rows": rows, "total": result["total"], "truncated": truncated, "grouped": True}

    if columns:
        rows = [{k: it.get(k) for k in columns} for it in items]
    else:
        rows = items
    return {"columns": columns, "rows": rows, "total": result["total"], "truncated": truncated, "grouped": False}


def _csv_stream(columns: List[str], rows: List[dict], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    fieldnames = columns or (sorted({k for r in rows for k in r.keys()}) if rows else [])
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                              headers={"Content-Disposition": f"attachment; filename={filename}.csv"})


_VERA_FONT_REGISTERED = False


def _ensure_vera_font():
    """reportlab'in kendi paketiyle gelen Vera.ttf'i (Bitstream Vera Sans)
    kayıt eder — Türkçe glifleri (çğıöşü/ÇĞİÖŞÜ) doğru render eder, YENİ
    bir pip bağımlılığı GEREKTİRMEZ. Modül import edilirken değil, İLK PDF
    isteğinde (lazy) kayıt edilir."""
    global _VERA_FONT_REGISTERED
    if _VERA_FONT_REGISTERED:
        return
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font_path = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
    pdfmetrics.registerFont(TTFont("Vera", font_path))
    _VERA_FONT_REGISTERED = True


def _pdf_bytes(title: str, generated_at: str, columns: List[str], rows: List[dict]) -> bytes:
    _ensure_vera_font()
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin

    c.setFont("Vera", 14)
    c.drawString(margin, y, title)
    y -= 18
    c.setFont("Vera", 9)
    c.drawString(margin, y, f"Oluşturulma: {generated_at}")
    y -= 20

    col_width = max(60, int((width - 2 * margin) / max(1, len(columns))))
    c.setFont("Vera", 8)
    for i, col in enumerate(columns):
        c.drawString(margin + i * col_width, y, str(col)[:28])
    y -= 4
    c.line(margin, y, width - margin, y)
    y -= 12

    for row in rows:
        if y < margin + 20:
            c.showPage()
            c.setFont("Vera", 8)
            y = height - margin
        for i, col in enumerate(columns):
            val = row.get(col, "")
            c.drawString(margin + i * col_width, y, str(val)[:28] if val is not None else "")
        y -= 14

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


SAMPLE_TEMPLATES = [
    {
        "name": "Çiftçi Listesi", "module": "farmers",
        "columns": ["full_name", "phone", "village", "status", "karne_score"],
        "filters": [], "logic": "AND", "sort_by": "full_name", "sort_dir": "asc",
        "group_by": None, "aggregations": [],
    },
    {
        "name": "Parsel Envanteri (Risk Seviyesine Göre)", "module": "parcels",
        "columns": ["name", "farmer_id", "village", "area_dekar", "risk_level"],
        "filters": [], "logic": "AND", "sort_by": None, "sort_dir": "asc",
        "group_by": "risk_level",
        "aggregations": [{"field": "area_dekar", "op": "sum", "label": "Toplam Alan (dekar)"}],
    },
    {
        "name": "Destek Talepleri Özeti (Duruma Göre)", "module": "support_requests",
        "columns": ["farmer_id", "support_type_id", "requested_amount", "status", "requested_at"],
        "filters": [], "logic": "AND", "sort_by": None, "sort_dir": "asc",
        "group_by": "status",
        "aggregations": [{"field": "requested_amount", "op": "sum", "label": "Toplam Talep Tutarı"}],
    },
]


def register_report_builder_routes(api_router, db, current_user, require_permission, log_audit,
                                    require_feature=None, raw_db=None):
    require_feature = require_feature or (lambda key: (lambda: True))
    _unscoped = raw_db if raw_db is not None else getattr(db, "_real_db", db)

    async def _owned_template_or_404(template_id: str) -> dict:
        doc = await db.report_templates.find_one({"id": template_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Rapor şablonu bulunamadı")
        return doc

    def _check_edit_access(doc: dict, user: dict):
        from config_service import get_system_tier
        is_owner = doc.get("created_by_id") == user["id"]
        is_moderator = get_system_tier(user.get("role")) in ("god_mode", "super_admin", "admin")
        if not (is_owner or is_moderator):
            raise HTTPException(403, "Sadece şablonun sahibi veya admin düzenleyebilir/silebilir")

    # =================================================================
    # ŞABLON CRUD
    # =================================================================
    @api_router.get("/report-templates")
    async def list_report_templates(
        module: Optional[str] = None,
        user=Depends(require_permission("report_builder:read")),
        _feat=Depends(require_feature("report_builder")),
    ):
        query: dict = {"$or": [{"created_by_id": user["id"]}, {"is_shared": True}]}
        if module:
            query["module"] = module
        docs = await db.report_templates.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
        for d in docs:
            d["is_owner"] = d.get("created_by_id") == user["id"]
            d["module_label"] = MODULE_LABELS.get(d["module"], d["module"])
        return docs

    @api_router.get("/report-templates/modules")
    async def list_reportable_modules(
        user=Depends(require_permission("report_builder:read")),
        _feat=Depends(require_feature("report_builder")),
    ):
        """Kullanıcının GERÇEKTEN görüntüleyebildiği (Query Engine izni olan)
        modüller — rapor tasarımcısının modül seçici dropdown'ı buradan
        beslenir, yetkisi olmayan bir modülü seçip 403 almaz."""
        from permissions import get_effective_permissions
        perms = await get_effective_permissions(user, db)
        return [
            {"key": k, "label": MODULE_LABELS.get(k, k)}
            for k, perm in MODULE_PERMISSIONS.items() if perm in perms
        ]

    @api_router.post("/report-templates")
    async def create_report_template(body: ReportTemplateCreate, request: Request,
                                      user=Depends(require_permission("report_builder:create")),
                                      _feat=Depends(require_feature("report_builder"))):
        _check_module(body.module)
        from permissions import get_effective_permissions
        perms = await get_effective_permissions(user, db)
        if MODULE_PERMISSIONS[body.module] not in perms:
            raise HTTPException(403, f"'{MODULE_PERMISSIONS[body.module]}' yetkiniz yok")
        doc = body.model_dump()
        doc["filters"] = [f if isinstance(f, dict) else f for f in doc["filters"]]
        doc["aggregations"] = [a if isinstance(a, dict) else a for a in doc["aggregations"]]
        doc["id"] = str(uuid.uuid4())
        doc["created_by_id"] = user["id"]
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.report_templates.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="report_template", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/report-templates/{template_id}")
    async def update_report_template(template_id: str, body: ReportTemplateUpdate, request: Request,
                                      user=Depends(require_permission("report_builder:create")),
                                      _feat=Depends(require_feature("report_builder"))):
        old = await _owned_template_or_404(template_id)
        _check_edit_access(old, user)
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "filters" in updates:
            updates["filters"] = [f if isinstance(f, dict) else f for f in updates["filters"]]
        if "aggregations" in updates:
            updates["aggregations"] = [a if isinstance(a, dict) else a for a in updates["aggregations"]]
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.report_templates.update_one({"id": template_id}, {"$set": updates})
        new = await db.report_templates.find_one({"id": template_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="report_template", entity_id=template_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/report-templates/{template_id}")
    async def delete_report_template(template_id: str, request: Request,
                                      user=Depends(require_permission("report_builder:create")),
                                      _feat=Depends(require_feature("report_builder"))):
        old = await _owned_template_or_404(template_id)
        _check_edit_access(old, user)
        await db.report_templates.delete_one({"id": template_id})
        await log_audit(db, user, action="delete", entity="report_template", entity_id=template_id, old_value=old, request=request)
        return {"status": "deleted"}

    @api_router.post("/report-templates/seed-samples")
    async def seed_sample_templates(request: Request,
                                     user=Depends(require_permission("report_builder:create")),
                                     _feat=Depends(require_feature("report_builder"))):
        """İdempotent — (created_by_id=None, name) çiftine göre var olan bir
        örnek şablon tekrar oluşturulmaz (field_definitions.py'nin `_ensure_*`
        kalıbıyla AYNI aile). Örnek şablonlar `is_shared=True` + sahipsiz
        (`created_by_id=None`) olarak yaratılır — tenant içindeki HERKESİN
        kullanabildiği, ama kimsenin "sahibi" olmadığı için düzenlenemeyen
        (sadece admin+ silebilir) salt-okunur bir başlangıç kütüphanesi."""
        created = []
        for tpl in SAMPLE_TEMPLATES:
            exists = await db.report_templates.find_one({"name": tpl["name"], "created_by_id": None})
            if exists:
                continue
            doc = dict(tpl)
            doc["id"] = str(uuid.uuid4())
            doc["created_by_id"] = None
            doc["created_by"] = "Sistem (örnek şablon)"
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            doc["is_shared"] = True
            await db.report_templates.insert_one(doc)
            created.append(doc["name"])
        return {"status": "ok", "created": created}

    # =================================================================
    # ÖNİZLEME / DIŞA AKTARMA (anlık, query_engine üzerinden)
    # =================================================================
    @api_router.get("/report-templates/{template_id}/preview")
    async def preview_report(template_id: str,
                              user=Depends(require_permission("report_builder:read")),
                              _feat=Depends(require_feature("report_builder"))):
        template = await _owned_template_or_404(template_id)
        rendered = await _run_report(db, user, template)
        return {**rendered, "template_name": template["name"], "generated_at": datetime.now(timezone.utc).isoformat()}

    @api_router.get("/report-templates/{template_id}/export.csv")
    async def export_report_csv(template_id: str,
                                 user=Depends(require_permission("report_builder:read")),
                                 _feat=Depends(require_feature("report_builder"))):
        template = await _owned_template_or_404(template_id)
        rendered = await _run_report(db, user, template)
        return _csv_stream(rendered["columns"], rendered["rows"], template["name"])

    @api_router.get("/report-templates/{template_id}/export.pdf")
    async def export_report_pdf(template_id: str,
                                 user=Depends(require_permission("report_builder:read")),
                                 _feat=Depends(require_feature("report_builder"))):
        template = await _owned_template_or_404(template_id)
        rendered = await _run_report(db, user, template)
        pdf = _pdf_bytes(template["name"], datetime.now(timezone.utc).isoformat(), rendered["columns"], rendered["rows"])
        return StreamingResponse(iter([pdf]), media_type="application/pdf",
                                  headers={"Content-Disposition": f"attachment; filename={template['name']}.pdf"})

    # =================================================================
    # PAYLAŞIM — kanal (mail/SMS/WhatsApp) veya link, snapshot + report_runs
    # =================================================================
    async def _create_run(template: dict, user: dict, rendered: dict, expires_days: int) -> dict:
        run = {
            "id": str(uuid.uuid4()),
            "template_id": template["id"],
            "template_name": template["name"],
            "generated_by": user.get("full_name") or user.get("email"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "public_token": secrets.token_urlsafe(12),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=max(1, expires_days))).isoformat(),
            "snapshot": rendered,
        }
        await db.report_runs.insert_one(run)
        run.pop("_id", None)
        return run

    @api_router.post("/report-templates/{template_id}/share")
    async def share_report(template_id: str, body: ReportShareRequest, request: Request,
                            user=Depends(require_permission("report_builder:share")),
                            _feat=Depends(require_feature("report_builder"))):
        template = await _owned_template_or_404(template_id)
        rendered = await _run_report(db, user, template)
        run = await _create_run(template, user, rendered, body.expires_days)
        link = f"/rapor/{run['public_token']}"
        message = body.message or f"'{template['name']}' raporu hazır: {link}"

        results = []
        for r in body.recipients:
            doc, ok = await send_via_channel(
                db, channel=r.channel, contact_type=r.contact_type, contact_id=r.contact_id,
                content=message, sent_by=f"rapor paylaşımı: {template['name']}",
                message_kind="operational",
            )
            results.append({"contact_id": r.contact_id, "channel": r.channel, "ok": ok, "detail": doc.get("provider_detail")})

        await log_audit(db, user, action="share", entity="report_template", entity_id=template_id,
                         new_value={"run_id": run["id"], "recipients": len(body.recipients)}, request=request)
        return {"run_id": run["id"], "public_token": run["public_token"], "link": link,
                "expires_at": run["expires_at"], "results": results}

    @api_router.get("/report-runs")
    async def list_report_runs(template_id: Optional[str] = None,
                                user=Depends(require_permission("report_builder:read")),
                                _feat=Depends(require_feature("report_builder"))):
        filt: dict = {}
        if template_id:
            filt["template_id"] = template_id
        return await db.report_runs.find(filt, {"_id": 0, "snapshot": 0}).sort("generated_at", -1).to_list(200)

    # =================================================================
    # PUBLIC GÖRÜNTÜLEYİCİ — login GEREKMEZ, forms_module.py'nin (Denetim
    # regresyon düzeltmesi) _unscoped token-arama kalıbıyla AYNI: tenant
    # HENÜZ bilinmediği için önce `_unscoped` ile bul, sonra `current_
    # tenant_id`'yi GEÇİCİ set et (bu run'ın ait olduğu tenant'ı belirlemek
    # için — snapshot zaten JSON'da hazır, ayrıca bir sorgu ATILMAZ).
    # =================================================================
    async def _public_run_or_404(token: str) -> dict:
        run = await _unscoped.report_runs.find_one({"public_token": token}, {"_id": 0})
        if not run:
            raise HTTPException(404, "Rapor bulunamadı veya bağlantının süresi dolmuş")
        if run.get("expires_at") and run["expires_at"] < datetime.now(timezone.utc).isoformat():
            raise HTTPException(410, "Bu rapor bağlantısının süresi dolmuş")
        template = await _unscoped.report_templates.find_one({"id": run["template_id"]}, {"_id": 0})
        reset_tok = current_tenant_id.set(template.get("tenant_id") if template else None)
        try:
            from platform_core import is_feature_enabled
            if not await is_feature_enabled(db, "report_builder"):
                raise HTTPException(403, "'Rapor Oluşturucu' özelliği bu kurum için kapatılmış")
        finally:
            current_tenant_id.reset(reset_tok)
        return run

    @api_router.get("/public/reports/{token}")
    async def get_public_report(token: str):
        run = await _public_run_or_404(token)
        return {
            "template_name": run["template_name"], "generated_at": run["generated_at"],
            "expires_at": run["expires_at"], **run["snapshot"],
        }

    @api_router.get("/public/reports/{token}/export.csv")
    async def export_public_report_csv(token: str):
        run = await _public_run_or_404(token)
        snap = run["snapshot"]
        return _csv_stream(snap["columns"], snap["rows"], run["template_name"])

    # =================================================================
    # ZAMANLAMA — report_schedules CRUD + tick (campaigns.py'nin run-
    # scheduled deseniyle AYNI aile, ama TEKRARLI: her tetiklemede
    # next_run_at frekansa göre yeniden hesaplanır).
    # =================================================================
    @api_router.get("/report-schedules")
    async def list_report_schedules(user=Depends(require_permission("report_builder:schedule")),
                                     _feat=Depends(require_feature("report_builder"))):
        return await db.report_schedules.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)

    @api_router.post("/report-schedules")
    async def create_report_schedule(body: ReportScheduleCreate, request: Request,
                                      user=Depends(require_permission("report_builder:schedule")),
                                      _feat=Depends(require_feature("report_builder"))):
        if body.frequency not in FREQUENCY_DAYS:
            raise HTTPException(400, f"Bilinmeyen frekans: {body.frequency}")
        await _owned_template_or_404(body.template_id)
        doc = body.model_dump()
        doc["recipients"] = [r if isinstance(r, dict) else r for r in doc["recipients"]]
        doc["id"] = str(uuid.uuid4())
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["next_run_at"] = (datetime.now(timezone.utc) + timedelta(days=FREQUENCY_DAYS[body.frequency])).isoformat()
        doc["last_run_at"] = None
        await db.report_schedules.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="report_schedule", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/report-schedules/{schedule_id}")
    async def update_report_schedule(schedule_id: str, body: ReportScheduleUpdate, request: Request,
                                      user=Depends(require_permission("report_builder:schedule")),
                                      _feat=Depends(require_feature("report_builder"))):
        old = await db.report_schedules.find_one({"id": schedule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Zamanlama bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "frequency" in updates and updates["frequency"] not in FREQUENCY_DAYS:
            raise HTTPException(400, f"Bilinmeyen frekans: {updates['frequency']}")
        if "recipients" in updates:
            updates["recipients"] = [r if isinstance(r, dict) else r for r in updates["recipients"]]
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.report_schedules.update_one({"id": schedule_id}, {"$set": updates})
        new = await db.report_schedules.find_one({"id": schedule_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="report_schedule", entity_id=schedule_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/report-schedules/{schedule_id}")
    async def delete_report_schedule(schedule_id: str, request: Request,
                                      user=Depends(require_permission("report_builder:schedule")),
                                      _feat=Depends(require_feature("report_builder"))):
        old = await db.report_schedules.find_one({"id": schedule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Zamanlama bulunamadı")
        await db.report_schedules.delete_one({"id": schedule_id})
        await log_audit(db, user, action="delete", entity="report_schedule", entity_id=schedule_id, old_value=old, request=request)
        return {"status": "deleted"}

    @api_router.post("/reports/run-scheduled")
    async def run_scheduled_reports(request: Request,
                                     user=Depends(require_permission("report_builder:schedule")),
                                     _feat=Depends(require_feature("report_builder"))):
        """"Zamanı gelmiş rapor zamanlamalarını çalıştır" tick'i — gerçek bir
        OS cron/Celery KURULU DEĞİL, prod'da bir scheduler tarafından
        periyodik çağrılacak SİMÜLASYONDUR (campaigns.py'nin run-scheduled'ıyla
        AYNI aile). `db` TenantScopedDB olduğundan bu uç çağıranın KENDİ
        tenant'ının zamanlamalarını çalıştırır."""
        now_iso = datetime.now(timezone.utc).isoformat()
        due = await db.report_schedules.find(
            {"active": True, "next_run_at": {"$lte": now_iso}}, {"_id": 0},
        ).to_list(200)
        executed = []
        for sched in due:
            template = await db.report_templates.find_one({"id": sched["template_id"]}, {"_id": 0})
            if not template:
                continue
            rendered = await _run_report(db, user, template)
            run = await _create_run(template, user, rendered, expires_days=FREQUENCY_DAYS[sched["frequency"]] + 2)
            link = f"/rapor/{run['public_token']}"
            message = f"'{template['name']}' raporu hazır (otomatik gönderim): {link}"
            for r in sched.get("recipients") or []:
                await send_via_channel(
                    db, channel=r["channel"], contact_type=r["contact_type"], contact_id=r["contact_id"],
                    content=message, sent_by=f"rapor zamanlaması: {template['name']}",
                    message_kind="operational",
                )
            next_run_at = (datetime.now(timezone.utc) + timedelta(days=FREQUENCY_DAYS[sched["frequency"]])).isoformat()
            await db.report_schedules.update_one({"id": sched["id"]}, {"$set": {
                "next_run_at": next_run_at, "last_run_at": now_iso,
            }})
            executed.append({"schedule_id": sched["id"], "template_name": template["name"], "run_id": run["id"]})
        return {"executed": executed}
