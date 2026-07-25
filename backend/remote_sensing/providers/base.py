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
from ..indices import ALL_INDEX_CODES


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

    def parse_statistics(self, result, indices: Optional[List[str]] = None) -> List[Dict]:
        """Sağlayıcı istatistik sonucunu ortak seriye çevirir:
        `[{date, ndvi, ndre?, ..., cloud_pct}]`. İki şekli de kabul eder:
          - Mock/Sentinel2: `{"series": [{date, ndvi, ...}]}` — zaten çok-
            indeksli, olduğu gibi geçer.
          - Gerçek EOSDA: `[{date, cloud, indexes: {NDVI: {average, median, ...}}}, ...]`
        (bkz. https://doc.eos.com/docs/statistics/ — mt_stats yanıt şeması).

        Denetim düzeltmesi (2026-07-25) — önceden SADECE ndvi/ndre'yi
        hardcoded olarak okuyordu; artık `indices` (verilmezse TÜM katalog)
        üzerinden döngüyle keyfi sayıda indeksi `idx` dict'inden çeker.

        ÖNEMLİ (2026-07-25, ikinci düzeltme): önceden bir nokta SADECE NDVI
        değeri varsa kabul ediliyordu (`if ndvi is None: continue`). EOSDA
        9-indeks isteği 3'lük gruplara BÖLÜNÜP birden çok istekle
        karşılandığında (bkz. eosda.py request_statistics), 1. grup DIŞINDAKİ
        gruplar NDVI TAŞIMAZ — eski mantık bu grupların TÜM noktalarını
        sessizce SİLERDİ. Artık bir nokta, istenen indekslerden HERHANGİ
        BİRİ mevcutsa kabul edilir (NDVI zorunlu değil); nihai birleştirilmiş
        seride NDVI'nin var olması `tasks.py`'nin "ndvi her zaman dahil et"
        garantisiyle sağlanır.
        """
        if not result:
            return []
        if isinstance(result, dict):
            return result.get("series", [])
        codes = indices or ALL_INDEX_CODES
        out: List[Dict] = []
        for sc in result:
            if not isinstance(sc, dict):
                continue
            idx = sc.get("indexes") or {}
            point = {"date": sc.get("date"), "cloud_pct": round(float(sc.get("cloud", 0) or 0))}
            found_any = False
            for code in codes:
                stats = idx.get(code.upper()) or idx.get(code)
                if not stats:
                    continue
                val = stats.get("average", stats.get("median"))
                if val is not None:
                    point[code] = round(float(val), 3)
                    found_any = True
            if found_any:
                out.append(point)
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

    def detect_anomaly(self, series: List[Dict], index: str = "ndvi") -> Anomaly:
        """Basit yerel anomali sezgisi (FAZ 18 Confidence Engine devralana
        kadar) — seride ani/derin düşüş varsa şüphe işaretler. `index`
        parametrik (varsayılan ndvi, geriye uyumlu — çağrı yerleri değişmez)."""
        vals = [p.get(index) for p in series if p.get(index) is not None]
        if len(vals) < 2:
            return Anomaly(detected=False)
        latest, prev = vals[-1], vals[-2]
        drop = prev - latest
        if latest < 0.35 or drop > 0.20:
            sev = "yuksek" if (latest < 0.25 or drop > 0.30) else "orta"
            return Anomaly(detected=True, severity=sev, confidence=min(0.5 + drop, 0.95),
                           reason=f"{index.upper()} düşüşü: {prev:.2f} → {latest:.2f}",
                           date=series[-1].get("date"))
        return Anomaly(detected=False)

    def detect_water_stress(self, series: List[Dict]) -> Anomaly:
        """Denetim eklentisi (2026-07-25) — MSI yükselişi VEYA NDWI düşüşünde
        su stresi işaretler (detect_anomaly'nin 'ani değişim' sezgisiyle
        simetrik, yön tersine çevrilmiş: burada YÜKSELİŞ/DÜŞÜŞ stres demek)."""
        msi_vals = [p.get("msi") for p in series if p.get("msi") is not None]
        ndwi_vals = [p.get("ndwi") for p in series if p.get("ndwi") is not None]
        if len(msi_vals) >= 2:
            latest, prev = msi_vals[-1], msi_vals[-2]
            rise = latest - prev
            if latest > 1.3 or rise > 0.25:
                sev = "yuksek" if (latest > 1.6 or rise > 0.4) else "orta"
                return Anomaly(detected=True, severity=sev, confidence=min(0.5 + rise, 0.95),
                               reason=f"MSI (nem stresi) yükselişi: {prev:.2f} → {latest:.2f}",
                               date=series[-1].get("date"))
        if len(ndwi_vals) >= 2:
            latest, prev = ndwi_vals[-1], ndwi_vals[-2]
            drop = prev - latest
            if latest < -0.05 or drop > 0.15:
                sev = "yuksek" if (latest < -0.15 or drop > 0.25) else "orta"
                return Anomaly(detected=True, severity=sev, confidence=min(0.5 + drop, 0.95),
                               reason=f"NDWI (bitki su içeriği) düşüşü: {prev:.2f} → {latest:.2f}",
                               date=series[-1].get("date"))
        return Anomaly(detected=False)
