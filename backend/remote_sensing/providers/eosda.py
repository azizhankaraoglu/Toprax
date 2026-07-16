"""
=====================================================================
TOPRAX — EOSDAProvider (ilk gerçek Uzaktan Algılama sağlayıcısı)
=====================================================================
EOSDA API'nin GERÇEK davranışına göre tasarlandı (doc.eos.com/docs/
quickstart — REMOTE-SENSING-EOSDA-PROMPT.md "EOSDA API'nin Gerçek
Davranışı" bölümü), varsayımla DEĞİL:

- Auth: OAuth DEĞİL, sabit `x-api-key` header'ı.
- Görüntü indirme 3 adımlı (search → download → status), asenkron/
  polling tabanlı, webhook YOK.
- İstatistik (NDVI vb.) 2 adımlı (task creation → status). Bir istekte
  1 parsel, 365 güne kadar, ~5 indeks, ~3 uydu.
- `field_id` yeniden kullanılabilir (AOI her seferinde gönderilmez).
- Rate limit endpoint'e göre değişir (Weather 10/dk vb.).
- Trial hesap 1000 istekle sınırlı.

Kritik kural (satellite_provider.py ile AYNI): `mock_mode=True` iken
(varsayılan) HİÇBİR gerçek dış çağrı yapılmaz — deterministik simüle
sonuç döner (DemoSatelliteProvider deseniyle aynı CRC32-seed). Gerçek
anahtar Integration Center'dan girilip mock_mode kapatılınca çağıran kod
DEĞİŞMEDEN gerçek EOSDA'ya geçer.
"""
import random
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from .base import IRemoteSensingProvider
from ..dto import TaskStatus, TaskState, WeatherData


class EOSDAProvider(IRemoteSensingProvider):
    name = "eosda"
    capabilities = ["imagery", "statistics", "weather", "tasking"]

    # EOSDA API tabanları (doc.eos.com). mock_mode kapatılmadan çağrılmaz;
    # ilk gerçek kullanımda "Bağlantıyı Test Et" ile doğrulanmalı.
    BASE = "https://api-connect.eos.com/api"
    STATISTICS_URL = BASE + "/gdw/api"        # Statistics/zoning task API
    RENDER_URL = BASE + "/render"             # Görüntü (search/download visual)
    FIELD_URL = BASE + "/avca/fields"         # Field (AOI) yönetimi
    WEATHER_URL = BASE + "/forecast/weather"  # Hava durumu

    def __init__(self, api_key: str = "", mock_mode: bool = True, timeout: int = 20):
        self.api_key = api_key
        self.mock_mode = mock_mode
        self.timeout = timeout

    # --- Ortak HTTP yardımcıları ---------------------------------------------
    @property
    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "Content-Type": "application/json"}

    def _rnd(self, seed_str: str) -> random.Random:
        return random.Random(zlib.crc32((seed_str or "seed").encode()) % 100000)

    # --- Field (AOI) ----------------------------------------------------------
    def create_field(self, geometry: dict) -> str:
        if self.mock_mode:
            # Deterministik sahte field_id (aynı geometri → aynı id).
            return "mock-field-" + str(zlib.crc32(str(geometry).encode()) % 10_000_000)
        resp = requests.post(self.FIELD_URL, json={"geometry": geometry},
                             headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        return str(resp.json().get("id"))

    # --- Görüntü: (1) search --------------------------------------------------
    def search_scenes(self, field_id: str, date_range: tuple) -> List[Dict]:
        start, end = date_range
        if self.mock_mode:
            rnd = self._rnd(field_id)
            scenes = []
            d = start
            while d <= end:
                scenes.append({
                    "view_id": f"S2/{d:%Y%m%d}/{rnd.randint(1000,9999)}",
                    "date": d.strftime("%Y-%m-%d"),
                    "cloud_pct": rnd.randint(0, 30),
                    "satellite": rnd.choice(["Sentinel-2", "Landsat-8"]),
                })
                d += timedelta(days=rnd.randint(4, 9))
            return scenes
        body = {"field_id": field_id,
                "date": {"from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d")}}
        resp = requests.post(self.RENDER_URL + "/search", json=body,
                             headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("results", [])

    # --- Görüntü: (2) download ------------------------------------------------
    def request_image_download(self, view_id: str, fmt: str = "png") -> str:
        if self.mock_mode:
            return "mock-imgtask-" + uuid.uuid4().hex[:12]
        body = {"view_id": view_id, "format": fmt}
        resp = requests.post(self.RENDER_URL + "/download", json=body,
                             headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        return str(resp.json().get("task_id"))

    # --- İstatistik: task creation --------------------------------------------
    def request_statistics(self, field_id: str, indices: List[str], date_range: tuple) -> str:
        start, end = date_range
        if self.mock_mode:
            # Sonucu task_id'ye göm (get_task_status deterministik üretsin).
            token = f"{field_id}|{','.join(indices)}|{start:%Y%m%d}|{end:%Y%m%d}"
            return "mock-stattask-" + str(zlib.crc32(token.encode()) % 10_000_000)
        body = {
            "type": "mt_stats",
            "params": {
                "bm_type": indices,
                "date_start": start.strftime("%Y-%m-%d"),
                "date_end": end.strftime("%Y-%m-%d"),
                "geometry": {"field_id": field_id},
                "sensors": ["sentinel2", "landsat8"],
            },
        }
        resp = requests.post(self.STATISTICS_URL, json=body,
                             headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        return str(resp.json().get("task_id"))

    # --- Ortak polling: (3) task status ---------------------------------------
    def get_task_status(self, task_id: str) -> TaskStatus:
        if self.mock_mode:
            return self._mock_status(task_id)
        resp = requests.get(f"{self.STATISTICS_URL}/{task_id}",
                            headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        raw_state = (data.get("status") or "").lower()
        state = {"created": TaskState.POLLING, "processing": TaskState.POLLING,
                 "finished": TaskState.COMPLETED, "error": TaskState.FAILED}.get(
                     raw_state, TaskState.POLLING)
        return TaskStatus(task_id=task_id, state=state, result=data.get("result"),
                          error=data.get("error"), raw=data)

    def _mock_status(self, task_id: str) -> TaskStatus:
        """Mock modda task ANINDA tamamlanır; istatistik task'ları için
        deterministik NDVI/indeks serisi üretir."""
        if task_id.startswith("mock-stattask-"):
            rnd = random.Random(int(task_id.rsplit("-", 1)[-1]))
            base = rnd.uniform(0.4, 0.75)
            series = []
            for month in range(5, 10):
                for day in (1, 15):
                    ndvi = base + (rnd.uniform(0, 0.15) if month <= 7
                                   else -(month - 7) * 0.08 + rnd.uniform(-0.05, 0.05))
                    series.append({"date": f"2025-{month:02d}-{day:02d}",
                                   "ndvi": round(max(0.1, min(0.95, ndvi)), 3),
                                   "ndre": round(max(0.05, min(0.8, ndvi - 0.1)), 3),
                                   "cloud_pct": rnd.randint(0, 25)})
            return TaskStatus(task_id=task_id, state=TaskState.COMPLETED,
                              result={"series": series})
        # Görüntü task'ı — hazır bir thumbnail url'i simüle et.
        return TaskStatus(task_id=task_id, state=TaskState.COMPLETED,
                          result_url=f"/uploads/remote_sensing/{task_id}.png",
                          result={"format": "png"})

    # --- Tasking (VHR) --------------------------------------------------------
    def request_tasking(self, field_id: Optional[str], priority: str = "standard",
                        reason: str = "") -> Dict:
        if self.mock_mode:
            return {"status": "simule_edildi",
                    "message": "[MOCK MOD] VHR tasking talebi TOPRAX içinde kaydedildi, "
                               "EOSDA'ya GÖNDERİLMEDİ (mock_mode kapatılmadan gerçek "
                               "sipariş oluşturulmaz).",
                    "priority": priority, "reason": reason}
        body = {"field_id": field_id, "priority": priority}
        resp = requests.post(self.RENDER_URL + "/tasking", json=body,
                             headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        return {"status": "talep_edildi", "provider_task_id": resp.json().get("task_id"),
                "priority": priority, "reason": reason}

    # --- Hava durumu ----------------------------------------------------------
    def get_weather(self, field_id: str, date_range: tuple) -> Optional[WeatherData]:
        if self.mock_mode:
            rnd = self._rnd(field_id + "w")
            hist = [{"date": (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d"),
                     "temp_c": round(rnd.uniform(12, 34), 1),
                     "rain_mm": round(max(0, rnd.uniform(-4, 12)), 1),
                     "humidity_pct": rnd.randint(30, 90)} for i in range(7, 0, -1)]
            return WeatherData(field_id=field_id,
                               current={"temp_c": hist[-1]["temp_c"], "rain_mm": hist[-1]["rain_mm"]},
                               history=hist)
        resp = requests.get(f"{self.WEATHER_URL}/{field_id}",
                            headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        d = resp.json()
        return WeatherData(field_id=field_id, current=d.get("current"),
                           history=d.get("history", []))

    # --- IT-17 uyumluluğu: NDVI zaman serisi ----------------------------------
    def get_ndvi_time_series(self, parcel_id: str, geometry: Optional[dict] = None) -> List[Dict]:
        """satellite_provider.SatelliteProvider ile AYNI imza — Time Slider/
        Time Series bu metod üzerinden gerçek EOSDA verisine geçebilir."""
        field_id = self.create_field(geometry) if geometry else (parcel_id or "seed")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=150)
        task_id = self.request_statistics(field_id, ["ndvi"], (start, end))
        status = self.get_task_status(task_id)
        if status.state == TaskState.COMPLETED and status.result:
            return [{"date": p["date"], "ndvi": p["ndvi"], "cloud_pct": p.get("cloud_pct", 0)}
                    for p in status.result.get("series", [])]
        return []
