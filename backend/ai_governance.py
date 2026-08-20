"""
=====================================================================
Toprax — AI Yönetişimi: Sistem Promptları + Guardrail'ler + RAG
Bilgi Bankası (2026-08-19)
=====================================================================
Kullanıcı isteği: *"kendi LLM'imizi yönetecek bir prompt ekranı ve RAG
ekranı; sadece adminlerin görebileceği, verilecek cevapların guardrail'lerinin
belirleneceği bir prompt + RAG ekranı. Bu ekran TÜM AI için EN ÜST DÜZEY
YÖNETİCİ olacak. Ayrıca dosya + döküman vb. eklenerek de eğitebileceğim."*

Bu modül YENİ bir AI sağlayıcısı DEĞİLDİR. `ai_router.py` (yerel Ollama +
dış API hibrit yönlendirici) olduğu gibi kalır; burası onun ÖNÜNE geçen bir
yönetişim katmanıdır:

    çağıran modül → governed_generate() → [prompt] → [RAG] → [girdi guardrail]
                  → ai_router.generate_text() → [çıktı guardrail] → [log]

Dört alt konu BİLİNÇLİ OLARAK tek dosyada (platform_core.py'nin dört konuyu,
IT-27'nin Policy+Tercih+Kara Liste'yi tek dosyada toplamasıyla AYNI emsal —
hepsi tek bir istekte doğdu ve birbirini tamamlıyor):

1) **Sistem Promptları** (`ai_system_prompts`) — kapsam (`scope`) başına TEK
   aktif prompt. `global` kapsamı HER üretimin başına eklenir; özel kapsam
   (copilot/disease/agronomy/...) onun ARDINA eklenir. Versiyonlama
   `communications.py`'nin şablon versiyonlama deseniyle AYNI: `body`
   değişince eski hali `ai_prompt_versions`'a yazılır.

2) **Guardrail'ler** (`ai_guardrails`) — admin tanımlı kurallar. BİLİNÇLİ
   OLARAK basit ve denetlenebilir: anahtar kelime/regex tabanlı engelleme
   (`blocked_input`/`blocked_output`), zorunlu ek metin (`required_notice`)
   ve serbest metinli politika talimatı (`policy_text`, prompt'a eklenir).
   Bir LLM-tabanlı "yargıç" modeli KULLANILMADI — yerel modelin kendisini
   denetlemesi güvenlik açısından zayıf, ayrıca her istekte ikinci bir
   üretim maliyeti getirirdi (automation.py'nin "tam filtre DSL'i yerine
   basit eşitlik koşulu" sadeleştirmesiyle AYNI aile).

3) **RAG Bilgi Bankası** (`ai_rag_documents` + `ai_rag_chunks`) — dosya
   veya yapıştırılan metin parçalara bölünür, Ollama ile embedding üretilir,
   vektör Mongo'da chunk kaydının İÇİNDE saklanır. **Kullanıcı kararı:
   Ollama + Mongo** — Redis/Qdrant gibi yeni bir servis KURULMADI (CLAUDE.md
   "Redis/RabbitMQ kurulu değil" kararıyla tutarlı). Benzerlik numpy ile
   süreç içinde hesaplanır; binlerce chunk'a kadar fazlasıyla yeterli.
   Embedding modeli yoksa/erişilemezse **anahtar kelime skorlamasına düşer**
   ve bunu `rag_mode` alanıyla DÜRÜSTÇE bildirir (extras.py'nin "AI yoksa
   keyword fallback" deseniyle AYNI).

4) **Denetim İzi** (`ai_governance_logs`) — her governed üretim için hangi
   prompt sürümü, hangi guardrail'in tetiklendiği, hangi kaynakların
   getirildiği kaydedilir.

**Kapsam notu:** dış AI sağlayıcı anahtarları burada YÖNETİLMEZ — o hâlâ
Integration Center'ın (`integrations.py`) işidir. Burası "ne söylenecek"i
yönetir, "nereye bağlanılacak"ı değil.
"""
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

# =====================================================================
# KAPSAM (SCOPE) REGISTRY — kod seviyesi, platform_core.FEATURE_FLAG_LABELS
# ile AYNI kalıp. Yeni bir AI özelliği eklendiğinde buraya BİR satır eklenir;
# yönetim ekranı listeyi buradan okur, ayrı bir DB kataloğu tutulmaz.
# =====================================================================
AI_SCOPES: Dict[str, str] = {
    "global": "Global (TÜM AI çağrılarının başına eklenir)",
    "copilot": "AI Copilot (doğal dil sorgu)",
    "disease": "AI Hastalık Tespiti (görsel)",
    "agronomy": "Ekim Karar Motoru (agronomi yorumu)",
    "season_planner": "Sezon Karar Takvimi",
    "remote_sensing": "Uzaktan Algılama yorumu",
    "report": "Rapor özetleme",
    "chat": "Serbest sohbet / Test Konsolu",
}

DEFAULT_EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
RAG_TOP_K = 5


# =====================================================================
# METİN ÇIKARMA — dosyadan düz metin
# =====================================================================
def _extract_text(filename: str, raw: bytes) -> str:
    """Yüklenen dosyadan düz metin çıkarır.

    pdf/docx için opsiyonel kütüphaneler KULLANILIR AMA ZORUNLU DEĞİLDİR —
    kurulu değilse anlaşılır bir 415 döner (sessizce bozuk metin üretmektense
    dürüstçe reddetmek; geo_import.py'nin NCZ için 415 dönmesiyle AYNI kalıp).
    """
    name = (filename or "").lower()

    if name.endswith((".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log")):
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader  # opsiyonel bağımlılık
        except ImportError:
            raise HTTPException(415, "PDF okuma kütüphanesi (pypdf) sunucuda kurulu değil. "
                                     "Dosyayı .txt olarak yükleyin veya metni yapıştırın.")
        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)

    if name.endswith(".docx"):
        try:
            import docx  # opsiyonel bağımlılık (python-docx)
        except ImportError:
            raise HTTPException(415, "Word okuma kütüphanesi (python-docx) sunucuda kurulu değil. "
                                     "Dosyayı .txt olarak yükleyin veya metni yapıştırın.")
        d = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in d.paragraphs)

    raise HTTPException(415, f"Desteklenmeyen dosya türü: {filename}. "
                             f"Desteklenenler: txt, md, csv, json, yaml, pdf, docx.")


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Paragraf sınırlarını gözeten basit kaydırmalı pencere.

    Cümle/token tabanlı akıllı bölme İSTENMEDİ — yeni bir NLP bağımlılığı
    gerektirirdi ve bu boyutta pencerede kazancı marjinaldir.
    """
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # En yakın paragraf/cümle sınırına geri çek (çok geri gitmeden).
            for sep in ("\n\n", "\n", ". "):
                cut = text.rfind(sep, start + int(size * 0.5), end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


# =====================================================================
# EMBEDDING — Ollama üzerinden, yoksa anahtar kelimeye düşer
# =====================================================================
async def _embed_config(db) -> Tuple[Optional[str], Optional[str]]:
    """(base_url, embed_model) — yerel LLM kapalıysa (None, None)."""
    doc = await db.integrations.find_one({"type": "ai_service"}, {"_id": 0})
    cfg = (doc or {}).get("config", {}) or {}
    if not cfg.get("local_llm_enabled"):
        return None, None
    base = (cfg.get("ollama_base_url") or "").rstrip("/")
    if not base:
        return None, None
    return base, (cfg.get("ollama_embed_model") or DEFAULT_EMBED_MODEL)


def _embed_one(base_url: str, model: str, text: str) -> Optional[List[float]]:
    """Tek bir metin için embedding. Başarısızlıkta None — çağıran taraf
    anahtar kelime moduna düşer, ASLA istisna fırlatmaz (bilgi bankasına
    belge eklemek, embedding modeli yok diye tamamen engellenmemeli)."""
    try:
        resp = requests.post(f"{base_url}/api/embeddings",
                             json={"model": model, "prompt": text[:8000]}, timeout=120)
        if resp.status_code != 200:
            return None
        vec = resp.json().get("embedding")
        return vec if isinstance(vec, list) and vec else None
    except Exception:  # noqa: BLE001
        return None


def _cosine(a: List[float], b: List[float]) -> float:
    import numpy as np
    va, vb = np.asarray(a, dtype="float32"), np.asarray(b, dtype="float32")
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _keyword_score(query: str, text: str) -> float:
    """Embedding yokken kullanılan yedek skor — sorgudaki anlamlı kelimelerin
    metinde geçme oranı. Anlamsal DEĞİLDİR, dürüstçe böyle raporlanır."""
    words = {w for w in re.findall(r"\w{4,}", (query or "").lower())}
    if not words:
        return 0.0
    low = (text or "").lower()
    return sum(1 for w in words if w in low) / len(words)


async def retrieve_context(db, query: str, top_k: int = RAG_TOP_K,
                           tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """Bilgi bankasından en ilgili chunk'ları getirir.

    Dönen zarf HER ZAMAN `rag_mode` taşır: "embedding" | "keyword" | "bos" —
    çağıran (ve Test Konsolu) hangi kalitede bir getirme yapıldığını görür.
    """
    filt: Dict[str, Any] = {"is_active": True}
    if tags:
        filt["tags"] = {"$in": tags}
    chunks = await db.ai_rag_chunks.find(filt, {"_id": 0}).to_list(5000)
    if not chunks:
        return {"rag_mode": "bos", "sources": [], "context": ""}

    base_url, model = await _embed_config(db)
    qvec = _embed_one(base_url, model, query) if base_url else None

    scored: List[Tuple[float, Dict[str, Any]]] = []
    if qvec and any(c.get("embedding") for c in chunks):
        mode = "embedding"
        for c in chunks:
            if c.get("embedding"):
                scored.append((_cosine(qvec, c["embedding"]), c))
    else:
        mode = "keyword"
        for c in chunks:
            scored.append((_keyword_score(query, c.get("text", "")), c))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [(s, c) for s, c in scored[:top_k] if s > 0]
    sources = [{
        "document_id": c.get("document_id"), "document_title": c.get("document_title"),
        "chunk_index": c.get("chunk_index"), "score": round(s, 4),
        "excerpt": (c.get("text") or "")[:300],
    } for s, c in top]
    context = "\n\n---\n\n".join(
        f"[Kaynak: {c.get('document_title')} — bölüm {c.get('chunk_index')}]\n{c.get('text')}"
        for _, c in top
    )
    return {"rag_mode": mode if top else "bos", "sources": sources, "context": context}


# =====================================================================
# PROMPT + GUARDRAIL BİRLEŞTİRME
# =====================================================================
async def build_system_prompt(db, scope: str) -> Dict[str, Any]:
    """global + scope promptlarını ve guardrail politika metinlerini birleştirir."""
    parts: List[str] = []
    used: List[Dict[str, Any]] = []
    for key in ("global", scope):
        if key == "global" and scope == "global":
            pass  # global kapsamı iki kez eklenmesin
        doc = await db.ai_system_prompts.find_one(
            {"scope": key, "is_active": True}, {"_id": 0})
        if doc and (doc.get("body") or "").strip():
            parts.append(doc["body"].strip())
            used.append({"scope": key, "version": doc.get("version", 1), "id": doc.get("id")})
        if key == scope:
            break

    rails = await db.ai_guardrails.find({"is_active": True}, {"_id": 0}).to_list(200)
    applicable = [g for g in rails if not g.get("scopes") or scope in g["scopes"]]
    policies = [g["policy_text"].strip() for g in applicable if (g.get("policy_text") or "").strip()]
    if policies:
        parts.append("KURALLAR (bunlara HER ZAMAN uy):\n" + "\n".join(f"- {p}" for p in policies))

    return {"system_prompt": "\n\n".join(parts), "prompts_used": used, "guardrails": applicable}


def _match_patterns(text: str, rail: Dict[str, Any], field: str) -> Optional[str]:
    """Eşleşen ilk desen döner (yoksa None). Geçersiz regex bir kuralın TÜM
    üretimi çökertmemesi için sessizce düz metin araması olarak ele alınır."""
    low = (text or "").lower()
    for pat in (rail.get(field) or []):
        p = (pat or "").strip()
        if not p:
            continue
        if rail.get("is_regex"):
            try:
                if re.search(p, text or "", re.IGNORECASE):
                    return p
            except re.error:
                if p.lower() in low:
                    return p
        elif p.lower() in low:
            return p
    return None


async def governed_generate(db, scope: str, user_text: str, *,
                            use_rag: bool = True, extra_context: str = "",
                            tags: Optional[List[str]] = None,
                            user: Optional[dict] = None,
                            base_system_prompt: str = "",
                            structured: bool = False,
                            image_b64: Optional[str] = None) -> Dict[str, Any]:
    """TÜM AI üretiminin geçmesi GEREKEN tek kapı.

    Yanıt zarfı çağıranın kararı için gereken her şeyi taşır:
    `blocked` (guardrail engelledi mi), `rag_mode`, `sources`, `ai_powered`.

    Parametreler:
      base_system_prompt — çağıranın KENDİ teknik prompt'u (ör. copilot'un JSON
        şeması). Yönetişim promptlarının ARDINA eklenir; çağıranın sözleşmesi
        yönetişim metniyle ezilmez.
      structured — çağıran makine-okunur (JSON) çıktı bekliyor. Bu modda
        yönetişim promptları ve zorunlu uyarı metni EKLENMEZ (aksi halde
        "maddeler hâlinde yaz" gibi bir talimat veya sona eklenen uyarı JSON'u
        bozar), ama **girdi/çıktı engelleme ve denetim logu ÇALIŞMAYA DEVAM
        EDER** — güvenlik kontrolü asla atlanmaz, sadece biçimlendirme atlanır.
      image_b64 — verilirse görsel model kullanılır (AI Hastalık Tespiti).
    """
    from ai_router import get_ai_router

    started = datetime.now(timezone.utc)
    built = await build_system_prompt(db, scope)
    rails = built["guardrails"]

    # --- Girdi guardrail'i: engellenen bir konu ise modele HİÇ gitmeyiz.
    for rail in rails:
        hit = _match_patterns(user_text, rail, "blocked_input")
        if hit:
            result = {
                "blocked": True, "blocked_by": rail.get("name"), "matched": hit,
                "answer": rail.get("refusal_message") or
                          "Bu konu kurum politikası gereği yanıtlanmıyor.",
                "rag_mode": "bos", "sources": [], "ai_powered": False,
            }
            await _log(db, scope, user_text, result, built, started, user)
            return result

    # --- RAG bağlamı (structured modda anlamsız — JSON üretimine kurum
    #     belgesi eklemek çıktıyı bozar, faydası da yok).
    rag = {"rag_mode": "bos", "sources": [], "context": ""}
    if use_rag and not structured:
        rag = await retrieve_context(db, user_text, tags=tags)

    # --- Sistem promptunun kurulumu
    if structured:
        # Yönetişim metni EKLENMEZ: çağıranın katı şeması (ör. copilot'un
        # "SADECE JSON döndür" talimatı) tek otorite olarak kalır. Guardrail'in
        # engelleme ve loglama kısmı yukarıda/aşağıda ÇALIŞMAYA DEVAM EDER.
        system_prompt = base_system_prompt
    else:
        parts = [p for p in (built["system_prompt"], base_system_prompt) if p]
        system_prompt = "\n\n".join(parts)
        context_blocks = [b for b in (rag["context"], extra_context) if b]
        if context_blocks:
            system_prompt += (
                "\n\nAŞAĞIDAKİ KURUM BİLGİSİNİ KULLAN. Cevabın bu bilgiyle çelişmesin; "
                "bilgi yetersizse bunu açıkça söyle, UYDURMA.\n\n" + "\n\n".join(context_blocks)
            )

    # --- Üretim
    try:
        router = await get_ai_router(db)
        if image_b64:
            answer = router.generate_vision(system_prompt, user_text, image_b64)
        else:
            answer = router.generate_text(system_prompt, user_text)
        ai_powered, routed_as, error = True, router.routed_as, None
    except Exception as e:  # noqa: BLE001
        answer, ai_powered, routed_as, error = "", False, None, str(e)

    # --- Çıktı guardrail'i
    blocked_by = matched = None
    if answer:
        for rail in rails:
            hit = _match_patterns(answer, rail, "blocked_output")
            if hit:
                answer = rail.get("refusal_message") or \
                         "Üretilen yanıt kurum politikasına uymadığı için gösterilmiyor."
                blocked_by, matched = rail.get("name"), hit
                break

    # Zorunlu uyarı metni structured modda EKLENMEZ — JSON'un sonuna serbest
    # metin eklemek çıktıyı ayrıştırılamaz hale getirirdi.
    if answer and not blocked_by and not structured:
        notices = [g["required_notice"].strip() for g in rails
                   if (g.get("required_notice") or "").strip()]
        if notices:
            answer = answer.rstrip() + "\n\n" + "\n".join(notices)

    result = {
        "blocked": bool(blocked_by), "blocked_by": blocked_by, "matched": matched,
        "answer": answer, "error": error, "ai_powered": ai_powered, "routed_as": routed_as,
        "rag_mode": rag["rag_mode"], "sources": rag["sources"],
        "prompts_used": built["prompts_used"],
    }
    await _log(db, scope, user_text, result, built, started, user)
    return result


async def _log(db, scope, user_text, result, built, started, user):
    try:
        await db.ai_governance_logs.insert_one({
            "id": str(uuid.uuid4()), "scope": scope,
            "user_email": (user or {}).get("email"),
            "question": (user_text or "")[:2000],
            "answer_preview": (result.get("answer") or "")[:1000],
            "blocked": result.get("blocked"), "blocked_by": result.get("blocked_by"),
            "rag_mode": result.get("rag_mode"),
            "source_count": len(result.get("sources") or []),
            "prompts_used": built.get("prompts_used"),
            "ai_powered": result.get("ai_powered"), "error": result.get("error"),
            "duration_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
            "created_at": started.isoformat(),
        })
    except Exception:  # noqa: BLE001
        pass  # loglama asla asıl işlemi bozmaz (event_bus.py ile AYNI felsefe)


# =====================================================================
# PYDANTIC MODELLERİ
# =====================================================================
class SystemPromptUpsert(BaseModel):
    scope: str
    body: str
    note: Optional[str] = None
    is_active: bool = True


class GuardrailCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scopes: List[str] = []                 # boş = TÜM kapsamlar
    blocked_input: List[str] = []
    blocked_output: List[str] = []
    policy_text: Optional[str] = None      # sistem prompt'una eklenir
    required_notice: Optional[str] = None  # yanıtın sonuna eklenir
    refusal_message: Optional[str] = None
    is_regex: bool = False
    is_active: bool = True


class GuardrailUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    blocked_input: Optional[List[str]] = None
    blocked_output: Optional[List[str]] = None
    policy_text: Optional[str] = None
    required_notice: Optional[str] = None
    refusal_message: Optional[str] = None
    is_regex: Optional[bool] = None
    is_active: Optional[bool] = None


class RagTextCreate(BaseModel):
    title: str
    text: str
    tags: List[str] = []
    source: Optional[str] = None


class RagDocUpdate(BaseModel):
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class TestRequest(BaseModel):
    scope: str = "chat"
    question: str
    use_rag: bool = True
    tags: List[str] = []


# =====================================================================
# VARSAYILAN SEED — idempotent (convention #10)
# =====================================================================
DEFAULT_PROMPTS = {
    "global": (
        "Sen TOPRAX dijital tarım platformunun kurumsal yapay zekâ asistanısın. "
        "Şeker pancarı başta olmak üzere tarımsal üretim, parsel/çiftçi operasyonu, "
        "sulama, gübreleme, toprak analizi ve hasat konularında karar desteği verirsin.\n"
        "- HER ZAMAN Türkçe yanıtla.\n"
        "- Emin olmadığın sayısal değeri UYDURMA; veri yoksa 'veri yok' de.\n"
        "- Kısa, uygulanabilir ve maddeler hâlinde yaz.\n"
        "- Kişisel veri (TC kimlik no, IBAN, telefon) ASLA yanıtta tekrarlanmaz."
    ),
    "copilot": (
        "Kullanıcının doğal dil sorgusunu parsel/çiftçi filtresine çevirirsin. "
        "Sadece istenen kayıtları ve kısa bir gerekçe döndür."
    ),
    "disease": (
        "Bitki yaprak/kök fotoğrafından olası hastalık, zararlı veya besin "
        "eksikliğini değerlendirirsin. Kesin teşhis koymaz, olasılık ve doğrulama "
        "adımı önerirsin. İlaç önerirken mutlaka ruhsatlı ürün kontrolü uyarısı ekle."
    ),
    "agronomy": (
        "Ekim karar motorunun kural tabanlı bulgularını çiftçinin anlayacağı dile "
        "çevirirsin. KARARI DEĞİŞTİREMEZSİN — sadece açıklarsın."
    ),
}

DEFAULT_GUARDRAILS = [
    {
        "name": "Kişisel Veri Koruma (KVKK)",
        "description": "Yanıtlarda kimlik/iletişim/banka bilgisi paylaşılmasını engeller.",
        "scopes": [],
        "blocked_input": ["tc kimlik", "tc no", "iban", "kredi kartı"],
        "blocked_output": [],
        "policy_text": "Hiçbir koşulda TC kimlik numarası, IBAN, telefon veya adres bilgisi yazma.",
        "refusal_message": "Kişisel veri içeren sorular KVKK gereği yanıtlanmıyor.",
        "required_notice": None, "is_regex": False,
    },
    {
        "name": "Kapsam Dışı Konular",
        "description": "Tarım/kooperatif dışı konularda yanıt üretilmesini engeller.",
        "scopes": [],
        "blocked_input": ["siyaset", "seçim anketi", "borsa tavsiyesi", "tıbbi teşhis"],
        "blocked_output": [],
        "policy_text": "Yalnızca tarım, üretim ve kooperatif operasyonu konularında yanıt ver. "
                       "Kapsam dışı bir soru gelirse kibarca reddet.",
        "refusal_message": "Bu konu TOPRAX'ın kapsamı dışında.",
        "required_notice": None, "is_regex": False,
    },
    {
        "name": "İlaç/Gübre Sorumluluk Uyarısı",
        "description": "Kimyasal önerisi içeren yanıtların sonuna zorunlu uyarı ekler.",
        "scopes": ["disease", "agronomy", "chat"],
        "blocked_input": [], "blocked_output": [],
        "policy_text": None,
        "required_notice": "⚠️ Öneriler bilgilendirme amaçlıdır. Uygulama öncesi ziraat "
                           "mühendisinize danışın ve ürünün ruhsatlı olduğunu doğrulayın.",
        "refusal_message": None, "is_regex": False,
    },
]


# =====================================================================
# ROUTE KAYDI (convention #1)
# =====================================================================
def register_ai_governance_routes(api_router, db, current_user, require_permission,
                                  log_audit, require_feature=None):

    def _guard(perm: str):
        return require_permission(perm)

    # ---------------- Kapsamlar ----------------
    @api_router.get("/ai-governance/scopes")
    async def list_scopes(user=Depends(_guard("ai_governance:view"))):
        return [{"key": k, "label": v} for k, v in AI_SCOPES.items()]

    # ---------------- Sistem Promptları ----------------
    @api_router.get("/ai-governance/prompts")
    async def list_prompts(user=Depends(_guard("ai_governance:view"))):
        docs = await db.ai_system_prompts.find({}, {"_id": 0}).to_list(200)
        by_scope = {d["scope"]: d for d in docs}
        return [{"scope": k, "label": v, **by_scope.get(k, {})} for k, v in AI_SCOPES.items()]

    @api_router.put("/ai-governance/prompts/{scope}")
    async def upsert_prompt(scope: str, body: SystemPromptUpsert, request: Request,
                            user=Depends(_guard("ai_governance:manage"))):
        if scope not in AI_SCOPES:
            raise HTTPException(400, f"Bilinmeyen kapsam: {scope}")
        now = datetime.now(timezone.utc).isoformat()
        old = await db.ai_system_prompts.find_one({"scope": scope}, {"_id": 0})
        if old:
            # communications.py'nin şablon versiyonlama deseni: gövde
            # değiştiyse ESKİ hali saklanır, sürüm artar.
            if (old.get("body") or "") != body.body:
                await db.ai_prompt_versions.insert_one({
                    "id": str(uuid.uuid4()), "prompt_id": old["id"], "scope": scope,
                    "body": old.get("body"), "version": old.get("version", 1),
                    "archived_at": now, "archived_by": user.get("email"),
                })
            await db.ai_system_prompts.update_one({"scope": scope}, {"$set": {
                "body": body.body, "note": body.note, "is_active": body.is_active,
                "version": old.get("version", 1) + (1 if (old.get("body") or "") != body.body else 0),
                "updated_at": now, "updated_by": user.get("email"),
            }})
        else:
            await db.ai_system_prompts.insert_one({
                "id": str(uuid.uuid4()), "scope": scope, "body": body.body,
                "note": body.note, "is_active": body.is_active, "version": 1,
                "created_at": now, "updated_at": now, "updated_by": user.get("email"),
            })
        await log_audit(db, user, "update", "ai_system_prompt", scope,
                        old, {"body": body.body}, request)
        return await db.ai_system_prompts.find_one({"scope": scope}, {"_id": 0})

    @api_router.get("/ai-governance/prompts/{scope}/versions")
    async def prompt_versions(scope: str, user=Depends(_guard("ai_governance:view"))):
        return await db.ai_prompt_versions.find({"scope": scope}, {"_id": 0}) \
                                          .sort("archived_at", -1).to_list(50)

    @api_router.post("/ai-governance/seed-defaults")
    async def seed_defaults(user=Depends(_guard("ai_governance:manage"))):
        now = datetime.now(timezone.utc).isoformat()
        p_created = g_created = 0
        for scope, text in DEFAULT_PROMPTS.items():
            if await db.ai_system_prompts.find_one({"scope": scope}):
                continue
            await db.ai_system_prompts.insert_one({
                "id": str(uuid.uuid4()), "scope": scope, "body": text,
                "note": "Varsayılan", "is_active": True, "version": 1,
                "created_at": now, "updated_at": now, "updated_by": user.get("email"),
            })
            p_created += 1
        for rail in DEFAULT_GUARDRAILS:
            if await db.ai_guardrails.find_one({"name": rail["name"]}):
                continue
            await db.ai_guardrails.insert_one({
                "id": str(uuid.uuid4()), **rail, "is_active": True,
                "created_at": now, "created_by": user.get("email"),
            })
            g_created += 1
        return {"status": "seeded", "prompts_created": p_created, "guardrails_created": g_created}

    # ---------------- Guardrail'ler ----------------
    @api_router.get("/ai-governance/guardrails")
    async def list_guardrails(user=Depends(_guard("ai_governance:view"))):
        return await db.ai_guardrails.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)

    @api_router.post("/ai-governance/guardrails")
    async def create_guardrail(body: GuardrailCreate, request: Request,
                               user=Depends(_guard("ai_governance:manage"))):
        doc = {"id": str(uuid.uuid4()), **body.dict(),
               "created_at": datetime.now(timezone.utc).isoformat(),
               "created_by": user.get("email")}
        await db.ai_guardrails.insert_one(doc)
        await log_audit(db, user, "create", "ai_guardrail", doc["id"], None, doc, request)
        return {k: v for k, v in doc.items() if k != "_id"}

    @api_router.put("/ai-governance/guardrails/{rail_id}")
    async def update_guardrail(rail_id: str, body: GuardrailUpdate, request: Request,
                               user=Depends(_guard("ai_governance:manage"))):
        old = await db.ai_guardrails.find_one({"id": rail_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Guardrail bulunamadı")
        upd = {k: v for k, v in body.dict().items() if v is not None}
        upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.ai_guardrails.update_one({"id": rail_id}, {"$set": upd})
        await log_audit(db, user, "update", "ai_guardrail", rail_id, old, upd, request)
        return await db.ai_guardrails.find_one({"id": rail_id}, {"_id": 0})

    @api_router.delete("/ai-governance/guardrails/{rail_id}")
    async def delete_guardrail(rail_id: str, request: Request,
                               user=Depends(_guard("ai_governance:manage"))):
        old = await db.ai_guardrails.find_one({"id": rail_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Guardrail bulunamadı")
        # convention #3 — fiziksel silme yok, pasife alınır.
        await db.ai_guardrails.update_one({"id": rail_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, "delete", "ai_guardrail", rail_id, old, None, request)
        return {"status": "deactivated"}

    # ---------------- RAG Bilgi Bankası ----------------
    async def _ingest(title: str, text: str, tags: List[str], source: str,
                      user: dict) -> Dict[str, Any]:
        chunks = _chunk_text(text)
        if not chunks:
            raise HTTPException(400, "Belgeden metin çıkarılamadı (içerik boş).")
        now = datetime.now(timezone.utc).isoformat()
        doc_id = str(uuid.uuid4())
        base_url, model = await _embed_config(db)

        rows, embedded = [], 0
        for i, ch in enumerate(chunks):
            vec = _embed_one(base_url, model, ch) if base_url else None
            if vec:
                embedded += 1
            rows.append({
                "id": str(uuid.uuid4()), "document_id": doc_id, "document_title": title,
                "chunk_index": i, "text": ch, "embedding": vec, "tags": tags,
                "is_active": True, "created_at": now,
            })
        await db.ai_rag_chunks.insert_many(rows)

        doc = {
            "id": doc_id, "title": title, "tags": tags, "source": source,
            "char_count": len(text), "chunk_count": len(chunks),
            "embedded_chunks": embedded,
            "embed_model": model if embedded else None,
            "index_mode": "embedding" if embedded else "keyword",
            "is_active": True, "created_at": now, "created_by": user.get("email"),
        }
        await db.ai_rag_documents.insert_one(doc)
        return {k: v for k, v in doc.items() if k != "_id"}

    @api_router.get("/ai-governance/rag/documents")
    async def list_rag_docs(user=Depends(_guard("ai_governance:view"))):
        return await db.ai_rag_documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

    @api_router.post("/ai-governance/rag/documents/text")
    async def add_rag_text(body: RagTextCreate, request: Request,
                           user=Depends(_guard("ai_governance:manage"))):
        doc = await _ingest(body.title, body.text, body.tags, body.source or "manuel", user)
        await log_audit(db, user, "create", "ai_rag_document", doc["id"], None, doc, request)
        return doc

    @api_router.post("/ai-governance/rag/documents/upload")
    async def upload_rag_doc(request: Request, file: UploadFile = File(...),
                             title: str = Form(""), tags: str = Form(""),
                             user=Depends(_guard("ai_governance:manage"))):
        """Dosyadan bilgi bankası kaydı.

        `storage.py`'nin ek-dosya mekanizması BİLİNÇLİ OLARAK kullanılmadı:
        burada amaç dosyayı SAKLAMAK değil METNİNİ İNDEKSLEMEK; ikili içerik
        indekslendikten sonra bir değer taşımıyor (LMS'in içerik dosyalarıyla
        KARIŞTIRILMAMALI — orası gerçek bir dosya arşividir).
        """
        raw = await file.read()
        if len(raw) > 20 * 1024 * 1024:
            raise HTTPException(413, "Dosya çok büyük (en fazla 20 MB).")
        text = _extract_text(file.filename, raw)
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        doc = await _ingest(title or file.filename, text, tag_list, file.filename, user)
        await log_audit(db, user, "create", "ai_rag_document", doc["id"], None, doc, request)
        return doc

    @api_router.put("/ai-governance/rag/documents/{doc_id}")
    async def update_rag_doc(doc_id: str, body: RagDocUpdate, request: Request,
                             user=Depends(_guard("ai_governance:manage"))):
        old = await db.ai_rag_documents.find_one({"id": doc_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Belge bulunamadı")
        upd = {k: v for k, v in body.dict().items() if v is not None}
        await db.ai_rag_documents.update_one({"id": doc_id}, {"$set": upd})
        # Chunk'lar belge ile AYNI aktiflik/etiketi taşımalı — getirme sorgusu
        # doğrudan chunk'lar üzerinde çalışıyor (belge join'i yok).
        cupd = {k: v for k, v in upd.items() if k in ("tags", "is_active")}
        if "title" in upd:
            cupd["document_title"] = upd["title"]
        if cupd:
            await db.ai_rag_chunks.update_many({"document_id": doc_id}, {"$set": cupd})
        await log_audit(db, user, "update", "ai_rag_document", doc_id, old, upd, request)
        return await db.ai_rag_documents.find_one({"id": doc_id}, {"_id": 0})

    @api_router.delete("/ai-governance/rag/documents/{doc_id}")
    async def delete_rag_doc(doc_id: str, request: Request,
                             user=Depends(_guard("ai_governance:manage"))):
        old = await db.ai_rag_documents.find_one({"id": doc_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Belge bulunamadı")
        # Bilgi bankası kaydı finansal/tarihsel veri DEĞİL — chunk'lar gerçekten
        # silinir (saved_queries.py'nin "görünüm tercihi gerçekten silinir"
        # emsali), belge kaydı ise ize kalsın diye pasife alınır.
        await db.ai_rag_chunks.delete_many({"document_id": doc_id})
        await db.ai_rag_documents.update_one(
            {"id": doc_id}, {"$set": {"is_active": False, "chunk_count": 0, "embedded_chunks": 0}})
        await log_audit(db, user, "delete", "ai_rag_document", doc_id, old, None, request)
        return {"status": "deleted"}

    @api_router.post("/ai-governance/rag/documents/{doc_id}/reindex")
    async def reindex_rag_doc(doc_id: str, user=Depends(_guard("ai_governance:manage"))):
        """Embedding modeli sonradan kurulduğunda mevcut belgeleri yeniden
        vektörler (yeniden yükleme gerektirmez)."""
        base_url, model = await _embed_config(db)
        if not base_url:
            raise HTTPException(400, "Yerel LLM (Ollama) yapılandırılmamış — embedding üretilemez.")
        chunks = await db.ai_rag_chunks.find({"document_id": doc_id}, {"_id": 0}).to_list(5000)
        if not chunks:
            raise HTTPException(404, "Bu belgeye ait bölüm yok.")
        embedded = 0
        for c in chunks:
            vec = _embed_one(base_url, model, c.get("text", ""))
            if vec:
                embedded += 1
                await db.ai_rag_chunks.update_one({"id": c["id"]}, {"$set": {"embedding": vec}})
        await db.ai_rag_documents.update_one({"id": doc_id}, {"$set": {
            "embedded_chunks": embedded, "embed_model": model if embedded else None,
            "index_mode": "embedding" if embedded else "keyword",
        }})
        return {"status": "reindexed", "chunks": len(chunks), "embedded": embedded}

    @api_router.post("/ai-governance/rag/search")
    async def rag_search(body: TestRequest, user=Depends(_guard("ai_governance:view"))):
        """Sadece GETİRME — model çalıştırmaz. Admin'in bilgi bankasının doğru
        parçaları döndürüp döndürmediğini üretim maliyeti olmadan görmesi için."""
        return await retrieve_context(db, body.question, tags=body.tags or None)

    # ---------------- Test Konsolu ----------------
    @api_router.post("/ai-governance/test")
    async def test_console(body: TestRequest, user=Depends(_guard("ai_governance:manage"))):
        if body.scope not in AI_SCOPES:
            raise HTTPException(400, f"Bilinmeyen kapsam: {body.scope}")
        return await governed_generate(db, body.scope, body.question,
                                       use_rag=body.use_rag,
                                       tags=body.tags or None, user=user)

    @api_router.get("/ai-governance/logs")
    async def list_logs(limit: int = 100, user=Depends(_guard("ai_governance:view"))):
        return await db.ai_governance_logs.find({}, {"_id": 0}) \
                                          .sort("created_at", -1).to_list(min(limit, 500))
