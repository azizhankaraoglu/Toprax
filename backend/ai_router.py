"""
=====================================================================
Toprax — AI Hibrit Yönlendirici: Yerel LLM (Ollama) + Dış API (Denetim Faz 4)
=====================================================================
`ai_provider.py`'nin ABC+factory kalıbının BİR ÜST katmanı: `integrations.py`
`ai_service` dokümanına yeni, GERİYE DÖNÜK UYUMLU alanlar ekler (hiçbiri
girilmezse davranış AYNEN eskisi gibi — dış sağlayıcıya gider):

  local_llm_enabled    : bool (varsayılan False)
  ollama_base_url      : str (varsayılan "http://localhost:11434")
  ollama_text_model    : str (varsayılan "llama3.1:8b")
  ollama_vision_model  : str (varsayılan "llava:7b")
  strategy             : "local_only" | "external_only" | "hybrid_confidence"
                          (varsayılan "external_only")
  confidence_threshold : float, 0-1 (varsayılan 0.6)

Üç strateji:
  - external_only     : ai_provider.py'nin sağlayıcısına gider (DEĞİŞMEYEN davranış)
  - local_only         : SADECE Ollama'ya gider, dış API'ye asla düşmez
  - hybrid_confidence  : önce Ollama dener, kendi ürettiği güven skorunu (0-1)
                         okur; eşiğin altındaysa dış API'ye ESKALE eder
                         (`ai_engine.py`'nin REDACTED_FIELDS felsefesiyle aynı
                         ruh — çağıranın prompt'unda PII olmaması beklenir,
                         eskalasyon isteğine bir hatırlatma notu eklenir)

`HybridAIRouter`, `ai_provider.AIProvider` ile AYNI arayüzü (generate_text/
generate_vision) sunar — çağıran kod (`extras.py`/`agronomy.py`) `get_ai_provider(...)`
yerine `get_ai_router(db)` kullanır, geri kalan her şey aynı kalır. Çağrı
sonrası `router.routed_as` ("local"|"external"|"escalated") metering/log
için okunabilir.
"""
import re
from typing import Optional

import requests

from ai_provider import get_ai_provider, AIProvider

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_TEXT_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_VISION_MODEL = "llava:7b"
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

CLOUD_ESCALATION_NOTICE = (
    "\n\n[NOT: Bu istek yerel modelin güven skoru düşük olduğu için dış servise "
    "yönlendirildi. Kişisel veri (TC no, tam ad, telefon) İÇERMEDİĞİNDEN emin olun.]"
)

_CONFIDENCE_INSTRUCTION = (
    "\n\nYanıtının SONUNA, ayrı bir satırda, SADECE şu formatta bir güven puanı ekle "
    "(o satırda başka hiçbir şey yazma): GUVEN: 0.0-1.0 arası bir sayı (ör. GUVEN: 0.8). "
    "Bu satır kullanıcıya gösterilmeyecek, sistem tarafından okunup metinden çıkarılacak."
)

_CONFIDENCE_LINE_RE = re.compile(r"GUVEN:\s*([01](?:\.\d+)?)", re.IGNORECASE)


class OllamaProvider(AIProvider):
    """Yerel Ollama sunucusu — API key gerektirmez, aynı makinede/ağda
    `ollama serve` (veya `docker-compose.ollama.yml`) ile çalışır."""

    def __init__(self, base_url: str, text_model: str, vision_model: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.text_model = text_model
        self.vision_model = vision_model
        self.timeout = timeout

    def _chat(self, model: str, system_prompt: str, user_text: str, images=None) -> str:
        message = {"role": "user", "content": user_text}
        if images:
            message["images"] = images
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}, message],
                "stream": False,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def generate_text(self, system_prompt: str, user_text: str) -> str:
        return self._chat(self.text_model, system_prompt, user_text)

    def generate_vision(self, system_prompt: str, user_text: str, image_b64: str) -> str:
        return self._chat(self.vision_model, system_prompt, user_text, images=[image_b64])

    def ping(self) -> bool:
        """Ayarlar > Entegrasyonlar 'Bağlantıyı Test Et' için — model listesi
        çeker, hiçbir üretim yapmaz (yıkıcı olmayan kontrol)."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False


def _extract_confidence(raw_response: str):
    """Yanıttan `GUVEN: 0.x` satırını ayrıştırıp (temiz_metin, skor) döner.
    Satır bulunamazsa VEYA yanıt şüpheli kısaysa (olası refusal/boş yanıt)
    düşük bir varsayılan skor (0.3) döner — belirsizlikte dış API'ye eskale
    etmek, yanlışlıkla düşük kaliteli yerel yanıtta kalmaktan daha güvenlidir."""
    m = _CONFIDENCE_LINE_RE.search(raw_response or "")
    if not m:
        fallback = 0.3 if len((raw_response or "").strip()) < 20 else 0.5
        return (raw_response or "").strip(), fallback
    score = min(1.0, max(0.0, float(m.group(1))))
    clean_text = _CONFIDENCE_LINE_RE.sub("", raw_response).strip()
    return clean_text, score


class HybridAIRouter(AIProvider):
    """`ai_provider.AIProvider` ile AYNI arayüz. `routed_as` son çağrının
    nereye gittiğini taşır ("local"|"external"|"escalated") — çağıran bunu
    `ai_usage_logs` kaydına ekleyebilir."""

    def __init__(self, strategy: str, local: Optional[OllamaProvider],
                 external: Optional[AIProvider], confidence_threshold: float):
        self.strategy = strategy
        self.local = local
        self.external = external
        self.confidence_threshold = confidence_threshold
        self.routed_as = None

    def _run(self, method: str, *args) -> str:
        if self.strategy == "local_only":
            if not self.local:
                raise ValueError("Yerel LLM (Ollama) yapılandırılmamış ama strateji 'Sadece Yerel'.")
            self.routed_as = "local"
            return getattr(self.local, method)(*args)

        if self.strategy == "hybrid_confidence" and self.local:
            try:
                args_with_conf = list(args)
                args_with_conf[0] = args_with_conf[0] + _CONFIDENCE_INSTRUCTION
                raw = getattr(self.local, method)(*args_with_conf)
                clean_text, confidence = _extract_confidence(raw)
                if confidence >= self.confidence_threshold:
                    self.routed_as = "local"
                    return clean_text
                if self.external:
                    self.routed_as = "escalated"
                    args_escalated = list(args)
                    args_escalated[0] = args_escalated[0] + CLOUD_ESCALATION_NOTICE
                    return getattr(self.external, method)(*args_escalated)
                # Dış API yoksa yerel sonucu (düşük güvenli de olsa) döndür.
                self.routed_as = "local"
                return clean_text
            except Exception:  # noqa: BLE001 — Ollama erişilemez/hata verdi
                if self.external:
                    self.routed_as = "escalated"
                    return getattr(self.external, method)(*args)
                raise

        # external_only (varsayılan, geriye dönük uyumlu davranış)
        if not self.external:
            raise ValueError("Dış AI servisi yapılandırılmamış.")
        self.routed_as = "external"
        return getattr(self.external, method)(*args)

    def generate_text(self, system_prompt: str, user_text: str) -> str:
        return self._run("generate_text", system_prompt, user_text)

    def generate_vision(self, system_prompt: str, user_text: str, image_b64: str) -> str:
        return self._run("generate_vision", system_prompt, user_text, image_b64)


async def get_ai_router(db) -> HybridAIRouter:
    """`integrations.get_ai_service_config(db)`'in genişletilmiş sürümü —
    hem dış sağlayıcıyı hem yerel LLM ayarlarını okuyup TEK bir
    `HybridAIRouter` döner. `local`/`external` ikisi de yoksa router yine
    döner ama ilk `generate_*` çağrısında ValueError fırlatır (çağıran
    "AI yapılandırılmamış" hatasını mevcut deseniyle üretir)."""
    from integrations import get_ai_service_config
    doc = await db.integrations.find_one({"type": "ai_service"}, {"_id": 0})
    cfg = (doc or {}).get("config", {}) or {}

    external = None
    ext_cfg = await get_ai_service_config(db)
    if ext_cfg and ext_cfg.get("provider") and ext_cfg.get("api_key"):
        try:
            external = get_ai_provider(ext_cfg["provider"], ext_cfg["api_key"], ext_cfg.get("model"))
        except ValueError:
            external = None

    local = None
    if cfg.get("local_llm_enabled"):
        local = OllamaProvider(
            cfg.get("ollama_base_url") or DEFAULT_OLLAMA_BASE_URL,
            cfg.get("ollama_text_model") or DEFAULT_OLLAMA_TEXT_MODEL,
            cfg.get("ollama_vision_model") or DEFAULT_OLLAMA_VISION_MODEL,
        )

    strategy = cfg.get("strategy") or "external_only"
    if strategy == "local_only" and not local:
        strategy = "external_only"  # yerel kapalıyken zorla yerel moda düşülmez
    threshold = cfg.get("confidence_threshold")
    threshold = float(threshold) if threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD

    return HybridAIRouter(strategy, local, external, threshold)


async def is_ai_available(db) -> bool:
    """Çağıranın (extras.py/agronomy.py) 'AI mi yoksa anahtar-kelime fallback'i
    mi kullanılsın' kararı için — router'ı kurmadan hafif bir kontrol.
    Eskiden `get_ai_service_config(db)` truthy'liğine bakılıyordu; artık
    yerel LLM AÇIKSA da AI 'yapılandırılmış' sayılır (dış anahtar olmasa da)."""
    router = await get_ai_router(db)
    return bool(router.local or router.external)
