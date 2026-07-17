"""
=====================================================================
TOPRAX — IRemoteSensingProvider (Uzaktan Algılama Provider Soyutlaması)
=====================================================================
Mevcut `satellite_provider.py`'deki `SatelliteProvider` (IT-17) ABC'si
KIRILMAZ — bu arayüz onunla UYUMLU kalır (get_ndvi_time_series /
get_fire_alerts / request_tasking imzaları korunur) ve üstüne EOSDA'nın
task/polling doğasına uygun YENİ metodlar ekler (create_field / search_
scenes / request_image_download / request_statistics / get_task_status /
get_weather).

Karar 1 (REMOTE-SENSING-EOSDA-PROMPT.md): EOSDA ayrı bir üçüncü sistem
DEĞİLDİR — `SatelliteProvider`'ın yeni bir alt sınıfı gibi davranır,
`get_remote_sensing_provider(db, tenant)` factory'si Integration Center'dan
(IT-01) hangi provider'ın aktif olduğunu okur.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from ..dto import TaskStatus, WeatherData, Anomaly


class IRemoteSensingProvider(ABC):
    """Uzaktan algılama sağlayıcı arayüzü. `SatelliteProvider` ile UYUMLU
    (aynı NDVI/fire/tasking metod adları) + EOSDA'nın 3-adımlı asenkron
    görüntü akışı için task tabanlı metodlar.

    Alt sınıf sözleşmesi: Integration Center'da geçerli kimlik + mock_mode
    KAPALI olmadan hiçbir gerçek dış çağrı yapılmaz (satellite_provider.py
    ile AYNI kural) — `mock_mode=True` iken tüm metodlar simüle sonuç döner.
    """

    name = "base"
    capabilities: List[str] = []          # örn. ["imagery", "statistics", "weather", "tasking"]

    # --- Field (AOI) yönetimi -------------------------------------------------
    @abstractmethod
    def create_field(self, geometry: dict) -> str:
        """EOSDA'da bir field_id oluşturur/döner. field_id yeniden
        kullanılabilir — AOI'yi her seferinde göndermek yerine
        Parcel.remote_sensing.eosda_field_id'de saklanır."""
        raise NotImplementedError

    # --- Görüntü (3-adımlı: search → download → status) -----------------------
    @abstractmethod
    def search_scenes(self, field_id: str, date_range: tuple) -> List[Dict]:
        """(1) Single Dataset Search → view_id listesi."""
        raise NotImplementedError

    @abstractmethod
    def request_image_download(self, view_id: str, fmt: str = "png") -> str:
        """(2) Download Visual → task_id döner (jpeg/tiff/png)."""
        raise NotImplementedError

    # --- İstatistik (2-adımlı task+polling) -----------------------------------
    @abstractmethod
    def request_statistics(self, field_id: str, indices: List[str], date_range: tuple,
                           geometry: Optional[dict] = None) -> str:
        """Task Creation → task_id. Gerçek EOSDA mt_stats geometry'yi DOĞRUDAN
        kabul eder (field zorunlu değil); mock modda field_id token'ı kullanılır."""
        raise NotImplementedError

    @abstractmethod
    def get_task_status(self, task_id: str) -> TaskStatus:
        """(3) Task Status polling — tüm asenkron task tiplerinin ortak durumu."""
        raise NotImplementedError

    def parse_statistics(self, result) -> List[Dict]:
        """Sağlayıcı istatistik sonucunu ortak seriye çevirir:
        `[{date, ndvi, ndre?, cloud_pct}]`. İki şekli de kabul eder:
          - Mock:  `{"series": [{date, ndvi, ...}]}`
          - Gerçek EOSDA: `[{date, cloud, indexes: {NDVI: {average, median, ...}}}, ...]`
        (bkz. https://doc.eos.com/docs/statistics/ — mt_stats yanıt şeması).
        """
        if not result:
            return []
        if isinstance(result, dict):
            return result.get("series", [])
        out: List[Dict] = []
        for sc in result:
            if not isinstance(sc, dict):
                continue
            idx = sc.get("indexes") or {}
            ndvi_stats = idx.get("NDVI") or idx.get("ndvi") or {}
            ndre_stats = idx.get("NDRE") or idx.get("ndre") or {}
            ndvi = ndvi_stats.get("average", ndvi_stats.get("median"))
            if ndvi is None:
                continue
            ndre = ndre_stats.get("average")
            out.append({
                "date": sc.get("date"),
                "ndvi": round(float(ndvi), 3),
                "ndre": round(float(ndre), 3) if ndre is not None else None,
                "cloud_pct": round(float(sc.get("cloud", 0) or 0)),
            })
        out.sort(key=lambda p: p.get("date") or "")
        return out

    # --- Tasking (yüksek çözünürlük) ------------------------------------------
    def request_tasking(self, field_id: Optional[str], priority: str = "standard",
                        reason: str = "") -> Dict:
        """Anomali şüphesinde tek parsel için VHR talebi. Varsayılan:
        desteklenmiyor (satellite_provider.py ile AYNI varsayılan)."""
        return {"status": "desteklenmiyor",
                "message": f"'{self.name}' sağlayıcısı tasking desteklemiyor"}

    # --- Hava durumu (opsiyonel) ----------------------------------------------
    def get_weather(self, field_id: str, date_range: tuple) -> Optional[WeatherData]:
        """Provider destekliyorsa güncel + geçmiş hava durumu (EOSDA Weather,
        dk'da 10 istek). Varsayılan: None."""
        return None

    # --- Geriye-uyumluluk: SatelliteProvider ile AYNI metodlar ----------------
    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        """IT-17 uyumluluğu — varsayılan uygulama statistics üzerinden
        NDVI serisi kurar (alt sınıf override edebilir)."""
        return []

    def get_fire_alerts(self, bbox, days: int = 1) -> List[Dict]:
        return []

    def detect_anomaly(self, series: List[Dict]) -> Anomaly:
        """Basit yerel anomali sezgisi (FAZ 18 Confidence Engine devralana
        kadar) — NDVI serisinde ani/derin düşüş varsa şüphe işaretler."""
        vals = [p.get("ndvi") for p in series if p.get("ndvi") is not None]
        if len(vals) < 2:
            return Anomaly(detected=False)
        latest, prev = vals[-1], vals[-2]
        drop = prev - latest
        if latest < 0.35 or drop > 0.20:
            sev = "yuksek" if (latest < 0.25 or drop > 0.30) else "orta"
            return Anomaly(detected=True, severity=sev, confidence=min(0.5 + drop, 0.95),
                           reason=f"NDVI düşüşü: {prev:.2f} → {latest:.2f}",
                           date=series[-1].get("date"))
        return Anomaly(detected=False)
