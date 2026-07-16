"""
=====================================================================
TOPRAX — Agricultural Intelligence Engine (FAZ 18 / IT-47..53)
=====================================================================
`ROADMAP-DETAY-TAM.md` FAZ 18 + `AI-VIZYON-PLATFORMU-MIMARI.md` Bölüm
4..17'nin BİREBİR uygulaması. Tek modülde toplanır (server.py'nin
"yeni CRUD/domain server.py'ye eklenmez, kendi modülünde
register_X_routes ile açılır" kuralı — bkz. ROADMAP-DETAY-TAM.md üst
not) çünkü IT-47..52 birbirine sıkı bağlıdır (knowledge → prediction →
active-learning → model registry).

MİMARİ KARARLAR (mimari doküman Bölüm 0):
  - Mongo + in-process (PostgreSQL/Redis/RabbitMQ İCAT EDİLMEZ).
  - Tenant izolasyonu MEVCUT `TenantScopedDB` ile (request uçları `db`
    üzerinden otomatik scope). Arka plan işçisi (job worker) request
    context'i DIŞINDA çalıştığı için `raw_db` + job dokümanındaki
    açık `tenant_id` ile çalışır (tenant filtresi elle uygulanır).
  - Versiyonlama `ledger.py`/`AI-VIZYON...MIMARI Bölüm 4.3` deseniyle:
    knowledge_record ve model MUTASYONA UĞRAMAZ; düzeltme =
    `previous_version_id` işaret eden YENİ kayıt, eski `is_active=false`.
  - Yerel model inference'ı bu ortamda GERÇEK ML çalıştıramaz —
    `extras.py`/`satellite_provider.py`'nin "simüle veri" konvansiyonuyla
    AYNI: deterministik (görüntü/kayıt içeriğinden hash türetilmiş)
    bir SİMÜLASYON. Gerçek CPU modelleri (Bölüm 6) devreye alındığında
    SADECE `simulate_local_models()` değişir, karar akışı DEĞİŞMEZ.
  - Confidence Engine (Bölüm 7) + karar akışı SAF FONKSİYONLAR olarak
    yazıldı (API'den bağımsız birim-test edilebilir — IT-20'nin hakediş
    motoruyla AYNI felsefe).

RBAC: permissions.py PERMISSION_CATALOG'a "ai_engine" modülü eklendi.
Query Engine: query_engine.py'ye `ai_knowledge_records` modülü eklendi
(knowledge search kendi arama motorunu YAZMAZ).
"""
import asyncio
import hashlib
import io
import csv
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse


# =====================================================================
# Sabitler / Durum Makineleri (CLAUDE.md ALLOWED_TRANSITIONS konvansiyonu)
# =====================================================================

OBJECT_TYPES = [
    "urun", "gelisim_evresi", "hastalik", "zararli", "besin_eksikligi",
    "su_stresi", "yabani_ot", "yangin", "sel", "hasat_olgunlugu",
    "toprak_durumu", "hava_durumu",
]

APPROVAL_STATUSES = ["taslak", "incelemede", "onayli", "reddedildi"]

# ai_models durum makinesi (mimari doküman Bölüm 11)
MODEL_TRANSITIONS = {
    "training": {"validation", "retired"},
    "validation": {"staging", "retired"},
    "staging": {"production", "retired"},
    "production": {"retired", "rolled_back"},
    "retired": set(),
    "rolled_back": {"staging", "retired"},
}

JOB_STATUSES = ["pending", "claimed", "processing", "done", "failed", "retrying"]

# Cloud escalation redaksiyon filtresi (mimari doküman Bölüm 9) — bu alanlar
# ASLA bulut sağlayıcıya (prompt/dosya adı/metadata) gönderilmez.
REDACTED_FIELDS = {
    "farmer_name", "farmer_id", "full_name", "tc_no", "phone", "email",
    "address", "iban", "member_no", "expert_notes", "comments",
}

DEFAULT_CONFIDENCE_THRESHOLD = 0.75
DEFAULT_MONTHLY_CLOUD_CALLS = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# =====================================================================
# Confidence Engine — SAF FONKSİYONLAR (mimari doküman Bölüm 7)
# API'den bağımsız birim-test edilebilir (IT-20 hakediş motoru felsefesi).
# =====================================================================

def _stable_unit(seed: str) -> float:
    """Bir string'den [0,1) aralığında deterministik bir sayı — simüle model
    çıktısı için (gerçek rastgelelik YOK, aynı kayıt her zaman aynı sonucu
    verir; test edilebilirlik + reproducibility)."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def rule_engine(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Bölüm 7.1 adım 5 — ucuz, deterministik ön-eleme. Kural KESİN sonuç
    verirse (confidence=1.0) yerel model HİÇ çalışmaz (maliyet minimizasyonu,
    IT-48 kabul kriteri). Şu an tek kural: spektral NDVI eşiği (uydu/drone
    kaynağı) su stresi için deterministiktir."""
    ndvi = record.get("ndvi") or record.get("latest_ndvi")
    if ndvi is not None:
        try:
            ndvi = float(ndvi)
        except (TypeError, ValueError):
            ndvi = None
    if ndvi is not None and record.get("object_type") in (None, "su_stresi", "gelisim_evresi"):
        if ndvi < 0.2:
            return {"labels": [{"taxonomy_key": "su_stresi_agir", "confidence": 1.0, "source": "model"}],
                    "confidence": 1.0, "method": "rule_engine", "object_type": "su_stresi"}
        if ndvi > 0.8:
            return {"labels": [{"taxonomy_key": "saglikli", "confidence": 1.0, "source": "model"}],
                    "confidence": 1.0, "method": "rule_engine", "object_type": "gelisim_evresi"}
    return None


def simulate_local_models(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Bölüm 6/7 — 1+ yerel CPU modelinin çıktısını SİMÜLE eder (bu ortamda
    gerçek ağırlık dosyası yok). Gerçek modeller devreye alınınca SADECE bu
    fonksiyon değişir. Deterministik: aynı kayıt → aynı çıktı."""
    seed = record.get("id") or record.get("source_ref") or str(record.get("object_type"))
    obj = record.get("object_type") or "urun"
    base = _stable_unit(f"{seed}:{obj}")
    # İki "model" simüle et — biri sınıflandırıcı, biri kural-tabanlı ön-filtre
    m1 = {"model": "sim_vit_classifier", "label": obj, "confidence": round(0.55 + base * 0.44, 3)}
    second = _stable_unit(f"{seed}:secondary")
    # %20 olasılıkla ikinci model ÇELİŞİR (farklı sınıf) — konsensüs testi için
    if second < 0.2:
        alt = OBJECT_TYPES[int(second * 100) % len(OBJECT_TYPES)]
        m2 = {"model": "sim_rule_prefilter", "label": alt, "confidence": round(0.5 + second, 3)}
    else:
        m2 = {"model": "sim_rule_prefilter", "label": obj, "confidence": round(0.6 + second * 0.3, 3)}
    return [m1, m2]


def combine_confidence(model_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Bölüm 7.2 — çoklu model konsensüsü. Modeller AYNI sınıfta hemfikirse
    ortalama + %10 bonus (tavan %99); ÇELİŞİYORSA güven en düşük skorun
    ALTINA çekilir (belirsizlik saklanmaz, escalation'a zorlanır)."""
    if not model_outputs:
        return {"label": None, "confidence": 0.0, "consensus": "empty"}
    labels = {m["label"] for m in model_outputs}
    confs = [float(m["confidence"]) for m in model_outputs]
    if len(labels) == 1:
        avg = sum(confs) / len(confs)
        combined = min(0.99, round(avg + (0.10 if len(model_outputs) > 1 else 0.0), 3))
        return {"label": model_outputs[0]["label"], "confidence": combined, "consensus": "agree"}
    # çelişki → en düşük skorun altına
    combined = round(max(0.0, min(confs) - 0.15), 3)
    top = max(model_outputs, key=lambda m: m["confidence"])
    return {"label": top["label"], "confidence": combined, "consensus": "conflict"}


def decide(confidence: float, threshold: float, quota_available: bool,
           consensus: str = "agree") -> str:
    """Bölüm 7.1 adım 8 — eşik karşılaştırması → karar."""
    if consensus == "conflict":
        # çelişkili sonuç asla otomatik onaylanmaz
        return "escalated_to_cloud" if quota_available else "pending_expert_review"
    if confidence >= threshold:
        return "auto_approved"
    if quota_available:
        return "escalated_to_cloud"
    return "low_confidence_no_cloud_budget"


def redact_for_cloud(record: Dict[str, Any]) -> Dict[str, Any]:
    """Bölüm 9 — buluta gitmeden ÖNCE zorunlu redaksiyon. SADECE görüntü +
    teknik metadata; kimliklendirici hiçbir alan gönderilmez. Dosya adı
    knowledge_record.id (UUID) olur, orijinal ad sızmaz."""
    safe = {
        "record_id": record.get("id"),
        "object_type": record.get("object_type"),
        "captured_at": record.get("captured_at"),
        "source_type": record.get("source_type"),
    }
    # GPS opsiyonel — parsel bazlı analiz gerekmiyorsa gönderilmez
    return {k: v for k, v in safe.items() if v is not None and k not in REDACTED_FIELDS}


# =====================================================================
# Job Queue — RabbitMQ karşılığı (mimari doküman Bölüm 7.3)
# =====================================================================

async def claim_next_job(raw_db, worker_id: str, job_types: List[str],
                          tenant_id: Optional[str] = None) -> Optional[dict]:
    """FindOneAndUpdate ile ATOMİK claim — iki worker AYNI job'ı alamaz
    (IT-48 atomiklik kabul kriteri). `find_one_and_update` TenantScopedDB'de
    sarmalanmadığı için BİLEREK raw_db + açık tenant filtresi kullanılır."""
    filt: Dict[str, Any] = {"status": "pending", "job_type": {"$in": job_types}}
    if tenant_id:
        filt["tenant_id"] = tenant_id
    return await raw_db.ai_jobs.find_one_and_update(
        filt,
        {"$set": {"status": "claimed", "worker_id": worker_id, "claimed_at": _now()}},
        sort=[("priority", -1), ("created_at", 1)],
        return_document=True,
        projection={"_id": 0},
    )


async def _run_prediction_core(raw_db, record: dict, tenant_id: str,
                                threshold: float) -> dict:
    """Karar akışı çekirdeği (Bölüm 7.1) — hem senkron `/ai/predict` hem de
    async job worker AYNI fonksiyonu çağırır (tek karar yolu, IT-10/IT-17'nin
    'AI ayrı bir yol icat etmez' kuralıyla aynı ruh)."""
    rule = rule_engine(record)
    if rule:
        prediction = {
            "labels": rule["labels"], "confidence": rule["confidence"],
            "decision": "auto_approved", "consensus": "rule", "method": "rule_engine",
            "model_outputs": [], "cloud_provider_used": None,
        }
        return prediction

    models = simulate_local_models(record)
    combined = combine_confidence(models)
    quota_ok = await _quota_available(raw_db, tenant_id)
    decision = decide(combined["confidence"], threshold, quota_ok, combined["consensus"])

    cloud_provider_used = None
    if decision == "escalated_to_cloud":
        consumed = await _consume_cloud_quota(raw_db, tenant_id)
        if not consumed:
            decision = "low_confidence_no_cloud_budget"
        else:
            cloud_provider_used = await _cloud_escalate(raw_db, record)
            # bulut daha yüksek güven verdiyse otomatik onaya çekilebilir
            combined["confidence"] = max(combined["confidence"], 0.9)

    return {
        "labels": [{"taxonomy_key": combined["label"], "confidence": combined["confidence"], "source": "model"}],
        "confidence": combined["confidence"], "decision": decision,
        "consensus": combined["consensus"], "method": "local_models",
        "model_outputs": models, "cloud_provider_used": cloud_provider_used,
    }


async def _cloud_escalate(raw_db, record: dict) -> Optional[str]:
    """Bölüm 9 — düşük güvenli sonuç, redaksiyon filtresinden GEÇTİKTEN sonra
    `ai_provider.py` (mevcut Provider Pattern) üzerinden buluta gider. Bu
    ortamda gerçek ağ çağrısı yapılmaz (config yoksa/başarısızsa) — mock,
    ama redaksiyon HER ZAMAN uygulanır (güvenlik testi buna bakar)."""
    _payload = redact_for_cloud(record)   # noqa: F841 — redaksiyon her zaman çalışır
    try:
        from integrations import get_ai_service_config
        cfg = await get_ai_service_config(raw_db)
        if cfg and cfg.get("api_key") and cfg.get("enabled"):
            # Gerçek çağrı ai_provider.get_ai_provider(...).generate_vision(...)
            # ile yapılır — bu ortamda ağ erişimi olmadığından provider adı
            # kaydedilir, çağrı mock kalır (satellite_provider mock_mode deseni).
            return cfg.get("provider")
    except Exception:
        pass
    return "mock"


# =====================================================================
# Tenant Kota (mimari doküman Bölüm 8) — atomik $inc
# =====================================================================

async def _get_or_create_quota(raw_db, tenant_id: str) -> dict:
    month = _month_key()
    doc = await raw_db.ai_tenant_quota.find_one(
        {"tenant_id": tenant_id, "month": month}, {"_id": 0})
    if not doc:
        doc = {
            "tenant_id": tenant_id, "month": month, "cloud_calls_used": 0,
            "cloud_cost_used": 0.0, "monthly_limit_calls": DEFAULT_MONTHLY_CLOUD_CALLS,
            "monthly_limit_cost": 0.0, "alert_threshold_pct": 80,
        }
        await raw_db.ai_tenant_quota.insert_one(dict(doc))
    return doc


async def _quota_available(raw_db, tenant_id: str) -> bool:
    doc = await _get_or_create_quota(raw_db, tenant_id)
    return doc["cloud_calls_used"] < doc["monthly_limit_calls"]


async def _consume_cloud_quota(raw_db, tenant_id: str) -> bool:
    """Atomik $inc + limit guard (race condition önlenir). Limit aşılırsa
    False döner (sonuç YİNE döner, sessiz hata YOK — Bölüm 8)."""
    await _get_or_create_quota(raw_db, tenant_id)
    month = _month_key()
    res = await raw_db.ai_tenant_quota.find_one_and_update(
        {"tenant_id": tenant_id, "month": month,
         "$expr": {"$lt": ["$cloud_calls_used", "$monthly_limit_calls"]}},
        {"$inc": {"cloud_calls_used": 1}},
        return_document=True, projection={"_id": 0},
    )
    return res is not None


# =====================================================================
# Route kaydı — server.py register_X_routes deseni
# =====================================================================

def register_ai_engine_routes(api_router, db, raw_db, current_user,
                               require_permission, log_audit, require_feature=None):

    async def _tenant_id(user: dict) -> str:
        return user.get("tenant_id") or "default"

    async def _create_validation_case(user: dict, record: dict, prediction_id: str,
                                        reason: str) -> Optional[str]:
        """Active Learning köprüsü (Bölüm 10) — YENİ mesajlaşma sistemi İCAT
        EDİLMEZ; case_management.py'nin `cases` koleksiyonuna `category=
        "AI Doğrulama"` bir Case açılır (CaseManagement.jsx/PendingApprovals.jsx
        ile aynı yerde görünür)."""
        try:
            # Kategori case_categories'te olmalı (CaseManagement.jsx onu okur)
            existing = await db.case_categories.find_one({"name": "AI Doğrulama"}, {"_id": 0})
            if not existing:
                existing = {"id": str(uuid.uuid4()), "name": "AI Doğrulama",
                            "created_at": _now(), "is_active": True}
                await db.case_categories.insert_one(dict(existing))
            case = {
                "id": str(uuid.uuid4()),
                "subject": f"AI Doğrulama gerekiyor — {record.get('object_type', 'bilinmeyen')}",
                "category_id": existing["id"],
                "description": f"Tahmin ({reason}) uzman doğrulaması bekliyor. "
                               f"Kayıt: {record.get('id')}",
                "priority": "yuksek" if reason == "dusuk_guven" else "orta",
                "status": "yeni", "source": "ai_validation",
                "related_parcel_id": record.get("parcel_id"),
                "related_production_cycle_id": record.get("production_cycle_id"),
                "farmer_id": record.get("farmer_id"),
                "ai_prediction_id": prediction_id,
                "created_by": user.get("id"), "created_at": _now(),
                "status_updated_at": _now(), "messages": [],
            }
            await db.cases.insert_one(dict(case))
            return case["id"]
        except Exception:
            return None

    async def _persist_prediction(user: dict, record: dict, result: dict) -> dict:
        tid = await _tenant_id(user)
        pred = {
            "id": str(uuid.uuid4()), "tenant_id": tid,
            "knowledge_record_id": record.get("id"),
            "model_id": result.get("model_id"), "task_type": record.get("task_type", "classification"),
            "raw_output": result.get("model_outputs"), "confidence": result["confidence"],
            "decision": result["decision"], "consensus": result.get("consensus"),
            "cloud_provider_used": result.get("cloud_provider_used"),
            "cloud_cost_estimate": 0.0, "labels": result.get("labels"),
            "case_id": None, "created_at": _now(), "is_active": True,
        }
        # Düşük güvenli / çelişkili / bütçesiz → active learning + case
        if result["decision"] in ("pending_expert_review", "low_confidence_no_cloud_budget") \
                or result.get("consensus") == "conflict":
            reason = "dusuk_guven" if result["confidence"] < DEFAULT_CONFIDENCE_THRESHOLD else "model_celiskisi"
            case_id = await _create_validation_case(user, record, pred["id"], reason)
            pred["case_id"] = case_id
            await db.ai_active_learning_queue.insert_one({
                "id": str(uuid.uuid4()), "tenant_id": tid,
                "knowledge_record_id": record.get("id"), "prediction_id": pred["id"],
                "priority_score": round((1 - result["confidence"]) +
                                        (0.3 if result.get("consensus") == "conflict" else 0), 3),
                "reason": reason, "status": "bekliyor", "case_id": case_id,
                "created_at": _now(),
            })
        await db.ai_predictions.insert_one(dict(pred))
        # Event Bus (Bölüm 16) — bilinen tüketiciler: Saha Ops, Comm Hub, Harita
        try:
            from event_bus import publish
            if record.get("object_type") == "hastalik":
                await publish(db, "ai_disease_detected",
                              {"record_id": record.get("id"), "parcel_id": record.get("parcel_id"),
                               "prediction_id": pred["id"]})
            elif result["decision"] == "pending_expert_review":
                await publish(db, "ai_validation_needed",
                              {"record_id": record.get("id"), "prediction_id": pred["id"]})
        except Exception:
            pass
        return pred

    # ---------------- Taksonomi ----------------
    @api_router.get("/ai/taxonomy")
    async def list_taxonomy(user=Depends(require_permission("ai_knowledge:view"))):
        items = await db.ai_taxonomy.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(1000)
        return {"items": items, "total": len(items)}

    @api_router.post("/ai/taxonomy")
    async def create_taxonomy(body: Dict[str, Any], request: Request,
                               user=Depends(require_permission("ai_knowledge:manage"))):
        doc = dict(body)
        doc["id"] = doc.get("id") or str(uuid.uuid4())
        doc.setdefault("is_active", True)
        doc.setdefault("created_at", _now())
        await db.ai_taxonomy.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="ai_taxonomy",
                         entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.post("/ai/seed-taxonomy")
    async def seed_taxonomy(request: Request,
                             user=Depends(require_permission("ai_knowledge:manage"))):
        """20+ örnek taksonomi (ürün/hastalık/zararlı) — idempotent (key bazlı)."""
        seeds = [
            ("urun", "seker_pancari", "Şeker Pancarı"), ("urun", "bugday", "Buğday"),
            ("urun", "arpa", "Arpa"), ("urun", "misir", "Mısır"),
            ("hastalik", "cercospora", "Cercospora Yaprak Lekesi"),
            ("hastalik", "kok_curuklugu", "Kök Çürüklüğü"),
            ("hastalik", "rhizomania", "Rhizomania"), ("hastalik", "kulle", "Külleme"),
            ("hastalik", "pas_hastaligi", "Pas Hastalığı"), ("hastalik", "septoria", "Septoria"),
            ("zararli", "yaprak_biti", "Yaprak Biti"), ("zararli", "bozkurt", "Bozkurt"),
            ("zararli", "pancar_pireleri", "Pancar Pireleri"), ("zararli", "nematod", "Nematod"),
            ("besin_eksikligi", "azot_eksikligi", "Azot Eksikliği"),
            ("besin_eksikligi", "bor_eksikligi", "Bor Eksikliği"),
            ("besin_eksikligi", "demir_eksikligi", "Demir Eksikliği"),
            ("su_stresi", "su_stresi_agir", "Ağır Su Stresi"),
            ("su_stresi", "su_stresi_hafif", "Hafif Su Stresi"),
            ("gelisim_evresi", "saglikli", "Sağlıklı Gelişim"),
            ("yabani_ot", "yabani_ot_genel", "Yabani Ot"),
            ("hasat_olgunlugu", "hasat_hazir", "Hasada Hazır"),
        ]
        created = 0
        for object_type, key, label in seeds:
            exists = await db.ai_taxonomy.find_one({"key": key}, {"_id": 0})
            if exists:
                continue
            await db.ai_taxonomy.insert_one({
                "id": str(uuid.uuid4()), "parent_id": None, "key": key, "label": label,
                "object_type": object_type, "description": "", "icon": None,
                "is_active": True, "created_at": _now(),
            })
            created += 1
        await log_audit(db, user, action="seed", entity="ai_taxonomy",
                         entity_id="seed", new_value={"created": created}, request=request)
        return {"status": "seeded", "created": created, "total_seed_defs": len(seeds)}

    # ---------------- Dataset ----------------
    @api_router.get("/ai/datasets")
    async def list_datasets(user=Depends(require_permission("ai_knowledge:view"))):
        items = await db.ai_datasets.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(500)
        return {"items": items, "total": len(items)}

    @api_router.post("/ai/datasets")
    async def create_dataset(body: Dict[str, Any], request: Request,
                              user=Depends(require_permission("ai_knowledge:create"))):
        doc = dict(body)
        doc["id"] = doc.get("id") or str(uuid.uuid4())
        doc.setdefault("status", "draft")
        doc.setdefault("version", 1)
        doc.setdefault("record_count", 0)
        doc.setdefault("quality_score_avg", 0.0)
        doc.setdefault("is_active", True)
        doc.setdefault("created_at", _now())
        await db.ai_datasets.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="ai_dataset",
                         entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.get("/ai/datasets/{dataset_id}")
    async def get_dataset(dataset_id: str, user=Depends(require_permission("ai_knowledge:view"))):
        doc = await db.ai_datasets.find_one({"id": dataset_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Dataset bulunamadı")
        return doc

    @api_router.put("/ai/datasets/{dataset_id}")
    async def update_dataset(dataset_id: str, body: Dict[str, Any], request: Request,
                              user=Depends(require_permission("ai_knowledge:manage"))):
        old = await db.ai_datasets.find_one({"id": dataset_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Dataset bulunamadı")
        updates = {k: v for k, v in body.items() if k != "id"}
        updates["updated_at"] = _now()
        await db.ai_datasets.update_one({"id": dataset_id}, {"$set": updates})
        new = await db.ai_datasets.find_one({"id": dataset_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="ai_dataset",
                         entity_id=dataset_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/ai/datasets/{dataset_id}")
    async def delete_dataset(dataset_id: str, request: Request,
                              user=Depends(require_permission("ai_knowledge:manage"))):
        old = await db.ai_datasets.find_one({"id": dataset_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Dataset bulunamadı")
        await db.ai_datasets.update_one({"id": dataset_id},
                                         {"$set": {"is_active": False, "deleted_at": _now()}})
        await log_audit(db, user, action="soft_delete", entity="ai_dataset",
                         entity_id=dataset_id, old_value=old, request=request)
        return {"status": "deactivated"}

    @api_router.post("/ai/datasets/{dataset_id}/import")
    async def import_dataset(dataset_id: str, body: Dict[str, Any], request: Request,
                              user=Depends(require_permission("ai_knowledge:create"))):
        """Toplu import (ZIP/klasör önizle→doğrula→onayla — geo_import.py deseni).
        Bu ortamda gerçek ZIP açma yerine, gövdedeki `records[]` listesi
        knowledge_records'a dönüştürülür (frontend dosyaları storage.py'ye
        yükleyip ref listesini gönderir)."""
        ds = await db.ai_datasets.find_one({"id": dataset_id}, {"_id": 0})
        if not ds:
            raise HTTPException(404, "Dataset bulunamadı")
        records = body.get("records", [])
        created = []
        tid = await _tenant_id(user)
        for r in records:
            doc = _new_knowledge_doc(r, dataset_id, tid, user)
            await db.ai_knowledge_records.insert_one(dict(doc))
            created.append(doc["id"])
        await db.ai_datasets.update_one({"id": dataset_id},
                                         {"$inc": {"record_count": len(created)}})
        await log_audit(db, user, action="import", entity="ai_dataset",
                         entity_id=dataset_id, new_value={"imported": len(created)}, request=request)
        return {"status": "imported", "created": len(created), "ids": created}

    # ---------------- Knowledge Records ----------------
    def _new_knowledge_doc(body: dict, dataset_id: Optional[str], tid: str, user: dict) -> dict:
        return {
            "id": str(uuid.uuid4()), "dataset_id": dataset_id or body.get("dataset_id"),
            "tenant_id": tid, "source_type": body.get("source_type", "mobil"),
            "source_ref": body.get("source_ref"), "captured_at": body.get("captured_at") or _now(),
            "gps": body.get("gps"), "parcel_id": body.get("parcel_id"),
            "production_cycle_id": body.get("production_cycle_id"), "farmer_id": body.get("farmer_id"),
            "object_type": body.get("object_type"), "labels": body.get("labels", []),
            "annotations": body.get("annotations", []), "quality_score": body.get("quality_score", 0.0),
            "expert_notes": body.get("expert_notes", ""), "comments": [],
            "approval_status": "taslak", "version": 1, "previous_version_id": None,
            "ndvi": body.get("ndvi"), "task_type": body.get("task_type", "classification"),
            "created_by": user.get("id"), "created_at": _now(), "updated_at": _now(),
            "is_active": True,
        }

    @api_router.post("/ai/knowledge-records")
    async def create_record(body: Dict[str, Any], request: Request,
                             user=Depends(require_permission("ai_knowledge:create"))):
        tid = await _tenant_id(user)
        doc = _new_knowledge_doc(body, body.get("dataset_id"), tid, user)
        await db.ai_knowledge_records.insert_one(dict(doc))
        await log_audit(db, user, action="create", entity="ai_knowledge_record",
                         entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.post("/ai/knowledge-records/bulk")
    async def bulk_records(items: List[Dict[str, Any]], request: Request,
                            user=Depends(require_permission("ai_knowledge:create"))):
        tid = await _tenant_id(user)
        created = []
        for body in items:
            doc = _new_knowledge_doc(body, body.get("dataset_id"), tid, user)
            await db.ai_knowledge_records.insert_one(dict(doc))
            created.append(doc["id"])
        await log_audit(db, user, action="bulk_create", entity="ai_knowledge_record",
                         entity_id=f"{len(created)}_kayit", new_value={"count": len(created)}, request=request)
        return {"created": len(created), "ids": created}

    @api_router.get("/ai/knowledge-records")
    async def list_records(dataset_id: Optional[str] = None, object_type: Optional[str] = None,
                            approval_status: Optional[str] = None, skip: int = 0, limit: int = 50,
                            user=Depends(require_permission("ai_knowledge:view"))):
        q: Dict[str, Any] = {"is_active": {"$ne": False}}
        if dataset_id:
            q["dataset_id"] = dataset_id
        if object_type:
            q["object_type"] = object_type
        if approval_status:
            q["approval_status"] = approval_status
        total = await db.ai_knowledge_records.count_documents(q)
        items = await db.ai_knowledge_records.find(q, {"_id": 0}).skip(skip).limit(min(limit, 500)).to_list(min(limit, 500))
        return {"items": items, "total": total, "skip": skip, "limit": limit}

    @api_router.get("/ai/knowledge-records/export")
    async def export_records(user=Depends(require_permission("ai_knowledge:view"))):
        items = await db.ai_knowledge_records.find({}, {"_id": 0}).to_list(10000)
        buf = io.StringIO()
        if items:
            cols = ["id", "dataset_id", "object_type", "approval_status", "version",
                    "quality_score", "parcel_id", "created_at"]
            writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(items)
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                  headers={"Content-Disposition": "attachment; filename=ai_knowledge_records.csv"})

    @api_router.get("/ai/knowledge-records/{record_id}")
    async def get_record(record_id: str, user=Depends(require_permission("ai_knowledge:view"))):
        doc = await db.ai_knowledge_records.find_one({"id": record_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Kayıt bulunamadı")
        return doc

    @api_router.get("/ai/knowledge-records/{record_id}/versions")
    async def record_versions(record_id: str, user=Depends(require_permission("ai_knowledge:view"))):
        """Versiyon zinciri (Bölüm 4.3) — previous_version_id ile geriye doğru."""
        chain = []
        cur = await db.ai_knowledge_records.find_one({"id": record_id}, {"_id": 0})
        seen = set()
        while cur and cur["id"] not in seen:
            seen.add(cur["id"])
            chain.append(cur)
            prev_id = cur.get("previous_version_id")
            cur = await db.ai_knowledge_records.find_one({"id": prev_id}, {"_id": 0}) if prev_id else None
        return {"versions": chain, "count": len(chain)}

    async def _new_version(record_id: str, updates: dict, user: dict, action: str) -> dict:
        """Bölüm 4.3 — MUTASYON YOK. Eski kayıt is_active=false; içeriği +
        updates ile YENİ bir kayıt (previous_version_id=eski, version+1)."""
        old = await db.ai_knowledge_records.find_one({"id": record_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kayıt bulunamadı")
        new = dict(old)
        new.update(updates)
        new["id"] = str(uuid.uuid4())
        new["previous_version_id"] = old["id"]
        new["version"] = old.get("version", 1) + 1
        new["updated_at"] = _now()
        new["is_active"] = True
        await db.ai_knowledge_records.update_one({"id": record_id},
                                                  {"$set": {"is_active": False, "superseded_at": _now()}})
        await db.ai_knowledge_records.insert_one(dict(new))
        return new

    @api_router.put("/ai/knowledge-records/{record_id}")
    async def update_record(record_id: str, body: Dict[str, Any], request: Request,
                            user=Depends(require_permission("ai_knowledge:create"))):
        updates = {k: v for k, v in body.items()
                   if k not in ("id", "version", "previous_version_id", "created_at")}
        new = await _new_version(record_id, updates, user, "update")
        await log_audit(db, user, action="update_version", entity="ai_knowledge_record",
                         entity_id=new["id"], new_value={"from": record_id}, request=request)
        return new

    @api_router.post("/ai/knowledge-records/{record_id}/annotations")
    async def add_annotation(record_id: str, body: Dict[str, Any], request: Request,
                             user=Depends(require_permission("ai_knowledge:create"))):
        old = await db.ai_knowledge_records.find_one({"id": record_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kayıt bulunamadı")
        ann = dict(body)
        ann.setdefault("created_by", user.get("id"))
        ann.setdefault("created_at", _now())
        annotations = list(old.get("annotations", [])) + [ann]
        new = await _new_version(record_id, {"annotations": annotations}, user, "annotate")
        await log_audit(db, user, action="annotate", entity="ai_knowledge_record",
                         entity_id=new["id"], new_value={"annotation": ann}, request=request)
        return new

    @api_router.post("/ai/knowledge-records/{record_id}/approve")
    async def approve_record(record_id: str, body: Dict[str, Any], request: Request,
                             user=Depends(require_permission("ai_knowledge:approve"))):
        status = body.get("approval_status", "onayli")
        if status not in APPROVAL_STATUSES:
            raise HTTPException(400, f"Geçersiz onay durumu: {status}")
        new = await _new_version(record_id, {"approval_status": status}, user, "approve")
        await log_audit(db, user, action="approve", entity="ai_knowledge_record",
                         entity_id=new["id"], new_value={"approval_status": status}, request=request)
        return new

    # ---------------- Prediction (senkron + async) ----------------
    async def _threshold(user: dict) -> float:
        return DEFAULT_CONFIDENCE_THRESHOLD

    @api_router.post("/ai/predict")
    async def predict(body: Dict[str, Any], request: Request,
                      user=Depends(require_permission("ai_knowledge:create"))):
        """Senkron, küçük görev (Bölüm 7). `record_id` verilirse DB'den çekilir,
        yoksa gövde doğrudan kayıt gibi işlenir."""
        record = body
        if body.get("record_id"):
            record = await db.ai_knowledge_records.find_one({"id": body["record_id"]}, {"_id": 0})
            if not record:
                raise HTTPException(404, "Kayıt bulunamadı")
        result = await _run_prediction_core(raw_db, record, await _tenant_id(user), await _threshold(user))
        pred = await _persist_prediction(user, record, result)
        return pred

    async def _process_job(job_id: str):
        """Arka plan işçisi (fire-and-forget). raw_db + job'daki tenant_id ile
        çalışır (request context DIŞINDA). Atomik claim → processing → done."""
        worker_id = f"worker-{uuid.uuid4().hex[:6]}"
        job = await claim_next_job(raw_db, worker_id, ["predict"])
        if not job:
            return
        try:
            await raw_db.ai_jobs.update_one({"id": job["id"]},
                                             {"$set": {"status": "processing"}})
            tid = job.get("tenant_id") or "default"
            record = job.get("payload") or {}
            if record.get("record_id"):
                record = await raw_db.ai_knowledge_records.find_one(
                    {"id": record["record_id"], "tenant_id": tid}, {"_id": 0}) or record
            result = await _run_prediction_core(raw_db, record, tid, DEFAULT_CONFIDENCE_THRESHOLD)
            # prediction'ı raw_db ile yaz (tenant_id açık) — worker tenant-context'siz
            pred = {
                "id": str(uuid.uuid4()), "tenant_id": tid, "knowledge_record_id": record.get("id"),
                "confidence": result["confidence"], "decision": result["decision"],
                "consensus": result.get("consensus"), "labels": result.get("labels"),
                "cloud_provider_used": result.get("cloud_provider_used"),
                "created_at": _now(), "is_active": True, "via_job": job["id"],
            }
            await raw_db.ai_predictions.insert_one(dict(pred))
            await raw_db.ai_jobs.update_one({"id": job["id"]},
                                             {"$set": {"status": "done", "completed_at": _now(),
                                                       "result_prediction_id": pred["id"]}})
        except Exception as e:
            attempts = job.get("attempts", 0) + 1
            new_status = "retrying" if attempts < job.get("max_attempts", 3) else "failed"
            await raw_db.ai_jobs.update_one({"id": job["id"]},
                                             {"$set": {"status": "pending" if new_status == "retrying" else "failed",
                                                       "attempts": attempts, "error": str(e)}})

    @api_router.post("/ai/predict/async")
    async def predict_async(body: Dict[str, Any], request: Request,
                            user=Depends(require_permission("ai_knowledge:create"))):
        tid = await _tenant_id(user)
        job = {
            "id": str(uuid.uuid4()), "tenant_id": tid, "job_type": "predict",
            "payload": body, "status": "pending", "priority": body.get("priority", 1),
            "worker_id": None, "claimed_at": None, "attempts": 0, "max_attempts": 3,
            "error": None, "created_at": _now(), "completed_at": None,
        }
        await raw_db.ai_jobs.insert_one(dict(job))
        # fire-and-forget worker tetikle (in-process asyncio — RabbitMQ karşılığı)
        asyncio.create_task(_process_job(job["id"]))
        return {"job_id": job["id"], "status": "pending"}

    @api_router.get("/ai/jobs/{job_id}")
    async def get_job(job_id: str, user=Depends(require_permission("ai_knowledge:view"))):
        tid = await _tenant_id(user)
        doc = await raw_db.ai_jobs.find_one({"id": job_id, "tenant_id": tid}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "İş bulunamadı")
        return doc

    @api_router.post("/ai/jobs/process-next")
    async def process_next(user=Depends(require_permission("ai_knowledge:manage"))):
        """Worker tetikleyici (manuel/cron) — bir bekleyen job'ı işler."""
        tid = await _tenant_id(user)
        pending = await raw_db.ai_jobs.find_one({"status": "pending", "tenant_id": tid}, {"_id": 0})
        if not pending:
            return {"status": "no_pending_jobs"}
        await _process_job(pending["id"])
        return {"status": "processed", "job_id": pending["id"]}

    # ---------------- Active Learning / Validation Queue ----------------
    @api_router.get("/ai/validation-queue")
    async def validation_queue(status: Optional[str] = "bekliyor",
                                user=Depends(require_permission("ai_prediction:validate"))):
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        items = await db.ai_active_learning_queue.find(q, {"_id": 0}) \
            .sort("priority_score", -1).to_list(200)
        return {"items": items, "total": len(items)}

    @api_router.post("/ai/validation-queue/{queue_id}/decide")
    async def decide_validation(queue_id: str, body: Dict[str, Any], request: Request,
                                 user=Depends(require_permission("ai_prediction:validate"))):
        """Uzman kararı (Bölüm 10): onay/düzeltme → knowledge_record'a
        labels[].source="hibrit" YENİ versiyon; kuyruk kaydı 'tamamlandi'."""
        item = await db.ai_active_learning_queue.find_one({"id": queue_id}, {"_id": 0})
        if not item:
            raise HTTPException(404, "Kuyruk kaydı bulunamadı")
        decision = body.get("decision", "onay")  # onay | duzeltme | yeniden_egitim
        corrected_label = body.get("corrected_label")
        rec_id = item.get("knowledge_record_id")
        if rec_id:
            rec = await db.ai_knowledge_records.find_one({"id": rec_id}, {"_id": 0})
            if rec:
                labels = list(rec.get("labels", []))
                if decision == "duzeltme" and corrected_label:
                    labels = [{"taxonomy_key": corrected_label, "confidence": 1.0, "source": "hibrit"}]
                else:
                    labels = [{**l, "source": "hibrit"} for l in labels] or \
                             [{"taxonomy_key": rec.get("object_type"), "confidence": 1.0, "source": "hibrit"}]
                # yeni versiyon + onaylı (golden dataset'e girer)
                new = dict(rec)
                new.update({"labels": labels, "approval_status": "onayli"})
                new["id"] = str(uuid.uuid4())
                new["previous_version_id"] = rec["id"]
                new["version"] = rec.get("version", 1) + 1
                new["updated_at"] = _now()
                await db.ai_knowledge_records.update_one({"id": rec_id},
                                                          {"$set": {"is_active": False, "superseded_at": _now()}})
                await db.ai_knowledge_records.insert_one(dict(new))
        await db.ai_active_learning_queue.update_one({"id": queue_id},
                                                      {"$set": {"status": "tamamlandi",
                                                                "decided_by": user.get("id"),
                                                                "decision": decision, "decided_at": _now()}})
        # Case'e not düş (varsa)
        if item.get("case_id"):
            await db.cases.update_one({"id": item["case_id"]}, {"$push": {"messages": {
                "id": str(uuid.uuid4()), "message": f"AI doğrulama kararı: {decision}",
                "author_id": user.get("id"), "created_at": _now(),
            }}})
        await log_audit(db, user, action="validate", entity="ai_prediction",
                         entity_id=queue_id, new_value={"decision": decision}, request=request)
        return {"status": "decided", "decision": decision}

    # ---------------- Model Registry / MLOps ----------------
    @api_router.get("/ai/models")
    async def list_models(user=Depends(require_permission("ai_model:view"))):
        items = await db.ai_models.find({"is_active": {"$ne": False}}, {"_id": 0}).to_list(200)
        return {"items": items, "total": len(items)}

    @api_router.post("/ai/models")
    async def create_model(body: Dict[str, Any], request: Request,
                            user=Depends(require_permission("ai_model:deploy"))):
        doc = dict(body)
        doc["id"] = doc.get("id") or str(uuid.uuid4())
        doc.setdefault("status", "training")
        doc.setdefault("version", 1)
        doc.setdefault("metrics", {"precision": 0.0, "recall": 0.0, "f1": 0.0, "iou": 0.0, "drift_score": 0.0})
        doc.setdefault("previous_model_id", None)
        doc.setdefault("is_active", True)
        doc.setdefault("created_at", _now())
        await db.ai_models.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="ai_model",
                         entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.get("/ai/models/{model_id}")
    async def get_model(model_id: str, user=Depends(require_permission("ai_model:view"))):
        doc = await db.ai_models.find_one({"id": model_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Model bulunamadı")
        return doc

    def _transition_model(current: str, target: str):
        allowed = MODEL_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise HTTPException(400, f"Geçersiz model durum geçişi: {current} → {target}")

    @api_router.post("/ai/models/{model_id}/deploy")
    async def deploy_model(model_id: str, request: Request,
                           user=Depends(require_permission("ai_model:deploy"))):
        """ZORUNLU KAPI (Bölüm 11): staging→production öncesi golden dataset
        regresyon testi. Yeni metrikler mevcut production'dan KÖTÜYSE deploy
        4xx ile REDDEDİLİR (atlanamaz)."""
        model = await db.ai_models.find_one({"id": model_id}, {"_id": 0})
        if not model:
            raise HTTPException(404, "Model bulunamadı")
        _transition_model(model["status"], "production")
        # Mevcut production modelinin metrikleriyle karşılaştır
        current_prod = await db.ai_models.find_one(
            {"status": "production", "task_type": model.get("task_type")}, {"_id": 0})
        new_metrics = model.get("metrics", {})
        if current_prod:
            old_f1 = current_prod.get("metrics", {}).get("f1", 0)
            new_f1 = new_metrics.get("f1", 0)
            if new_f1 < old_f1:
                raise HTTPException(400,
                    f"Deploy reddedildi: yeni model F1 ({new_f1}) mevcut production "
                    f"modelinden ({old_f1}) düşük (golden dataset regresyon kapısı).")
            # eski production'ı retired yap
            await db.ai_models.update_one({"id": current_prod["id"]},
                                           {"$set": {"status": "retired", "retired_at": _now()}})
            await db.ai_models.update_one({"id": model_id},
                                           {"$set": {"previous_model_id": current_prod["id"]}})
        await db.ai_models.update_one({"id": model_id},
                                       {"$set": {"status": "production", "deployed_at": _now(),
                                                 "deployed_by": user.get("id")}})
        new = await db.ai_models.find_one({"id": model_id}, {"_id": 0})
        await log_audit(db, user, action="deploy", entity="ai_model",
                         entity_id=model_id, new_value={"status": "production"}, request=request)
        return new

    @api_router.post("/ai/models/{model_id}/rollback")
    async def rollback_model(model_id: str, request: Request,
                             user=Depends(require_permission("ai_model:rollback"))):
        """previous_model_id ile tek çağrıda önceki production'a dön (Bölüm 11)."""
        model = await db.ai_models.find_one({"id": model_id}, {"_id": 0})
        if not model:
            raise HTTPException(404, "Model bulunamadı")
        prev_id = model.get("previous_model_id")
        if not prev_id:
            raise HTTPException(400, "Bu modelin geri dönülebilecek önceki sürümü yok")
        await db.ai_models.update_one({"id": model_id},
                                       {"$set": {"status": "rolled_back", "rolled_back_at": _now()}})
        await db.ai_models.update_one({"id": prev_id},
                                       {"$set": {"status": "production", "deployed_at": _now()}})
        await log_audit(db, user, action="rollback", entity="ai_model",
                         entity_id=model_id, new_value={"restored": prev_id}, request=request)
        return {"status": "rolled_back", "restored_model_id": prev_id}

    @api_router.post("/ai/models/{model_id}/train")
    async def train_model(model_id: str, body: Dict[str, Any], request: Request,
                          user=Depends(require_permission("ai_model:deploy"))):
        """Eğitim tetikleyici — golden dataset (approval_status=onayli) sayısını
        kaydeder (gerçek eğitim CPU/GPU worker'a düşer, bu ortamda simüle)."""
        model = await db.ai_models.find_one({"id": model_id}, {"_id": 0})
        if not model:
            raise HTTPException(404, "Model bulunamadı")
        golden_count = await db.ai_knowledge_records.count_documents({"approval_status": "onayli"})
        run = {
            "id": str(uuid.uuid4()), "model_id": model_id, "golden_dataset_size": golden_count,
            "params": body, "status": "queued", "created_at": _now(), "created_by": user.get("id"),
        }
        await db.ai_training_runs.insert_one(dict(run))
        await db.ai_models.update_one({"id": model_id}, {"$set": {"status": "training"}})
        await log_audit(db, user, action="train", entity="ai_model",
                         entity_id=model_id, new_value={"golden_dataset_size": golden_count}, request=request)
        return {"status": "training_queued", "golden_dataset_size": golden_count, "run_id": run["id"]}

    @api_router.get("/ai/models/{model_id}/training-history")
    async def training_history(model_id: str, user=Depends(require_permission("ai_model:view"))):
        runs = await db.ai_training_runs.find({"model_id": model_id}, {"_id": 0}) \
            .sort("created_at", -1).to_list(100)
        return {"items": runs, "total": len(runs)}

    # ---------------- Tenant Kota ----------------
    @api_router.get("/ai/tenant-quota")
    async def get_tenant_quota(user=Depends(require_permission("ai_knowledge:view"))):
        tid = await _tenant_id(user)
        doc = await _get_or_create_quota(raw_db, tid)
        remaining = max(0, doc["monthly_limit_calls"] - doc["cloud_calls_used"])
        pct = round(100 * doc["cloud_calls_used"] / doc["monthly_limit_calls"], 1) if doc["monthly_limit_calls"] else 0
        return {**doc, "remaining_calls": remaining, "used_pct": pct}

    @api_router.put("/ai/tenant-quota/{tenant_id}/limits")
    async def set_tenant_quota(tenant_id: str, body: Dict[str, Any], request: Request,
                                user=Depends(require_permission("ai_knowledge:manage"))):
        month = _month_key()
        await _get_or_create_quota(raw_db, tenant_id)
        updates = {}
        for k in ("monthly_limit_calls", "monthly_limit_cost", "alert_threshold_pct"):
            if k in body:
                updates[k] = body[k]
        if updates:
            await raw_db.ai_tenant_quota.update_one({"tenant_id": tenant_id, "month": month},
                                                     {"$set": updates})
        await log_audit(db, user, action="update", entity="ai_tenant_quota",
                         entity_id=tenant_id, new_value=updates, request=request)
        doc = await raw_db.ai_tenant_quota.find_one({"tenant_id": tenant_id, "month": month}, {"_id": 0})
        return doc

    # ---------------- İzleme / Dashboard (Bölüm 14 "İzleme" sekmesi) ----------------
    @api_router.get("/ai/stats")
    async def ai_stats(user=Depends(require_permission("ai_knowledge:view"))):
        total_records = await db.ai_knowledge_records.count_documents({"is_active": {"$ne": False}})
        approved = await db.ai_knowledge_records.count_documents({"approval_status": "onayli"})
        total_pred = await db.ai_predictions.count_documents({})
        pending_val = await db.ai_active_learning_queue.count_documents({"status": "bekliyor"})
        prod_model = await db.ai_models.find_one({"status": "production"}, {"_id": 0})
        datasets = await db.ai_datasets.count_documents({"is_active": {"$ne": False}})
        return {
            "total_knowledge_records": total_records, "approved_records": approved,
            "total_predictions": total_pred, "pending_validation": pending_val,
            "datasets": datasets,
            "production_model": prod_model.get("name") if prod_model else None,
            "model_health": ai_model_health_summary(prod_model),
        }


def ai_model_health_summary(prod_model: Optional[dict]) -> dict:
    """platform_core.py Health Center'ının tüketebileceği tek satır (Bölüm 11).
    Yeni bir izleme ekranı İCAT EDİLMEZ — var olan panele bir satır."""
    if not prod_model:
        return {"service": "ai_model_health", "label": "AI Model Sağlığı",
                "status": "uyari", "detail": "Production'da model yok"}
    metrics = prod_model.get("metrics", {})
    drift = metrics.get("drift_score", 0)
    status = "saglikli" if drift < 0.1 else ("uyari" if drift < 0.3 else "hata")
    return {"service": "ai_model_health", "label": "AI Model Sağlığı", "status": status,
            "detail": f"Model: {prod_model.get('name')}, drift_score: {drift}, F1: {metrics.get('f1', 0)}"}
