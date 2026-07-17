"""
=====================================================================
TOPRAX — Remote Sensing (Uzaktan Algılama) DTO'ları
(REMOTE-SENSING-EOSDA-PROMPT.md — FAZ 9.5 / IT-28.1 nihai spesifikasyon)
=====================================================================
Bu modül SADECE Pydantic veri modellerini içerir — iş mantığı YOK.
Diğer TOPRAX modüllerindeki (support.py durum makinesi, communication_
policy.py kural modeli) tipli-model disiplininin AYNISI (CLAUDE.md
konvansiyon #8: JSON blob YASAK, tipli alanlar).
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    SEARCH = "search"            # Single Dataset Search → view_id
    DOWNLOAD = "download"        # Download Visual → task_id (görüntü)
    STATISTICS = "statistics"    # İstatistik (NDVI vb.) task+polling
    ZONING = "zoning"            # Zonlama/verimlilik haritası (30-300 sn)
    TASKING = "tasking"          # Yüksek çözünürlük (VHR) talebi
    WEATHER = "weather"          # Hava durumu


class TaskState(str, Enum):
    QUEUED = "queued"            # Kuyruğa alındı, henüz başlamadı
    RUNNING = "running"          # Background worker atomik claim etti
    POLLING = "polling"          # Dış sağlayıcı task'ı bekleniyor (EOSDA polling)
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanFrequency(str, Enum):
    GUNLUK = "gunluk"
    IKI_GUNDE_BIR = "iki_gunde_bir"
    HAFTADA_BIR = "haftada_bir"
    AYDA_BIR = "ayda_bir"
    MANUEL_ONLY = "manuel_only"


# Sıklık → gün aralığı (scheduler kotayı/tazeliği bu tablodan hesaplar,
# kod dallanması yok — SATELLITE_TIERS deseniyle AYNI felsefe).
FREQUENCY_DAYS = {
    ScanFrequency.GUNLUK: 1,
    ScanFrequency.IKI_GUNDE_BIR: 2,
    ScanFrequency.HAFTADA_BIR: 7,
    ScanFrequency.AYDA_BIR: 30,
    ScanFrequency.MANUEL_ONLY: None,   # otomatik taranmaz
}


class TaskStatus(BaseModel):
    """Provider'ın get_task_status() dönüşü — EOSDA polling durumunun
    TOPRAX-nötr karşılığı (EOSDA'ya özgü alanlar `raw`da saklanır)."""
    task_id: str
    state: TaskState
    progress_pct: Optional[int] = None
    result_url: Optional[str] = None
    # Mock modda dict ({"series": [...]}) döner; GERÇEK EOSDA mt_stats bir LIST
    # ([{date, indexes:{NDVI:{average,...}}}, ...]) döndürdüğünden tip Any olmalı
    # (parse_statistics her iki şekli de çözer).
    result: Optional[Any] = None
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class WeatherData(BaseModel):
    field_id: str
    current: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)


class Anomaly(BaseModel):
    """Provider anomali döndürürse Parsel'e kaydedilir + Communication
    Policy'ye event olarak yayınlanır (KENDİ bildirim mantığı YOK)."""
    detected: bool = False
    severity: Optional[str] = None       # dusuk|orta|yuksek
    confidence: Optional[float] = None
    reason: Optional[str] = None
    date: Optional[str] = None


class TaramaPolicy(BaseModel):
    """Tarama Politikası (Karar 2) — Communication Policy (IT-27) ile AYNI
    desen: kural = Query Engine filtresi + sıklık + indeks + öncelik.
    Admin KOD YAZMADAN yeni kural tanımlar."""
    id: Optional[str] = None
    name: str
    filter: Dict[str, Any] = Field(default_factory=dict)   # QueryEngine filter DSL
    frequency: ScanFrequency = ScanFrequency.HAFTADA_BIR
    indices: List[str] = Field(default_factory=lambda: ["ndvi"])
    priority: int = 0                    # yüksek öncelik kazanır (çakışan politikalarda)
    provider_override: Optional[str] = None
    is_active: bool = True


class RemoteSensingTaskCreate(BaseModel):
    parcel_id: str
    task_type: TaskType
    indices: List[str] = Field(default_factory=lambda: ["ndvi"])
    date_range_days: int = 365           # EOSDA tek istekte 365 güne kadar
    priority: int = 0
    trigger: str = "manual"              # manual | scheduled | auto_tasking


# EOSDA'nın "1 görüntü = parsel+indeks başına 3 istek" maliyet gerçeği
# (Cost Management için tek kaynak — düz "1 istek = 1 birim" YANLIŞ olur).
EOSDA_REQUESTS_PER_INDEX = 3

# EOSDA trial hesap limiti — Monitoring ekranı kalan kotayı gösterir.
EOSDA_TRIAL_REQUEST_LIMIT = 1000

# Alan sınırı: bir istek en fazla 200 km² / 20.000 dekar (çok büyük
# parsel/bölge tek istekte gönderilemez, bölünmesi gerekir).
EOSDA_MAX_AREA_KM2 = 200.0

# Endpoint tipine göre ayrı rate limit (dakikada istek) — tek global
# limit YETERSİZ (prompt: "endpoint tipine göre ayrı rate limit").
EOSDA_RATE_LIMITS_PER_MIN = {
    "weather": 10,
    "statistics": 30,
    "imagery": 30,
    "search": 60,
    "tasking": 10,
}
