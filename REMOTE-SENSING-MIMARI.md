# REMOTE-SENSING-MIMARI.md — TOPRAX Uzaktan Algılama Modülü (EOSDA)

> FAZ 9.5 / **IT-28.1 nihai spesifikasyonu**. Kaynak: `REMOTE-SENSING-EOSDA-PROMPT.md`.
> Bu belge, `backend/remote_sensing/` paketinin uygulanmış mimarisini belgeler.
> IT-28.2 / 28.3 / 28.4 bu temelin üstüne AYNI numaralandırmayla gelir.

## 1. Kararlar (bağlayıcı)

1. EOSDA ayrı bir üçüncü sistem DEĞİLDİR — mevcut `satellite_provider.py`'nin
   (IT-17) `SatelliteProvider` ABC'si KIRILMAZ; `IRemoteSensingProvider` onunla
   UYUMLU (aynı `get_ndvi_time_series` imzası) ve `EOSDAProvider` yeni bir alt
   sınıf gibi eklenir. FAZ 18 AI Engine (IT-47-53) bu modülün ürettiği veriyi
   TÜKETİR.
2. Tarama sıklığı hardcode değil — admin **Tarama Politikası** ekranından
   filtre bazlı tanımlar (Communication Policy / IT-27 deseni).
3. EOSDA API key'i mevcut **Integration Center**'a (IT-01) `type="eosda"` olarak
   eklenir — ayrı key ekranı icat edilmez, secret maskeleme aynı kuralla çalışır.
4. Yeni backend paketi `backend/remote_sensing/` (tek dosyaya sığmayacak kapsam).

## 2. Paket Yapısı (uygulandı)

```
backend/remote_sensing/
├── __init__.py            register_remote_sensing_routes + get_remote_sensing_provider
├── dto.py                 Pydantic modelleri + maliyet/limit sabitleri
├── providers/
│   ├── __init__.py        get_remote_sensing_provider(db, provider_override) factory
│   ├── base.py            IRemoteSensingProvider (ABC) — SatelliteProvider ile UYUMLU
│   ├── eosda.py           EOSDAProvider — x-api-key, 3-adımlı asenkron akış
│   └── placeholders.py    Planet/Airbus/UP42 İSKELET (prompt: iskelet yeterli)
├── tasks.py               Task entity + polling job (ai_jobs atomik claim deseni)
├── scheduler.py           Tarama Politikası motoru (filtre → sıklık → kuyruk)
├── monitoring.py          API çağrı/kota/hata izleme (Health Center ailesi)
├── notifications.py       Communication Policy köprüsü (KENDİ bildirim mantığı YOK)
└── services.py            register_remote_sensing_routes(...) — HTTP yüzeyi
```

**Sorumluluk sınırları:** paket kendi RBAC/Audit/bildirim/depolama/arama motorunu
YAZMAZ — `permissions.py` / `log_audit` / Communication Policy (event_bus) /
`storage` desenlerinden kullanır. `server.py`'ye yeni domain kodu eklenmez; paket
kendi `register_remote_sensing_routes(api_router, db, current_user,
require_permission, log_audit)` fonksiyonuyla bağlanır (CLAUDE.md konvansiyon #1).

## 3. IRemoteSensingProvider Arayüzü

```python
class IRemoteSensingProvider(ABC):
    name: str
    capabilities: list[str]              # ["imagery","statistics","weather","tasking"]
    def create_field(geometry) -> field_id
    def search_scenes(field_id, date_range) -> [view_id, ...]      # (1) search
    def request_image_download(view_id, fmt) -> task_id           # (2) download
    def request_statistics(field_id, indices, date_range) -> task_id
    def get_task_status(task_id) -> TaskStatus                     # (3) polling
    def request_tasking(field_id, priority, reason) -> dict        # VHR
    def get_weather(field_id, date_range) -> WeatherData | None
    # IT-17 uyumluluğu:
    def get_ndvi_time_series(parcel_id, geometry) -> [{date,ndvi,cloud_pct}]
    def detect_anomaly(series) -> Anomaly
```

`EOSDAProvider` `x-api-key` header'ını Integration Center'dan okur — koda gömülü
key kullanmaz. `mock_mode=True` (varsayılan) iken hiçbir gerçek dış çağrı
yapılmaz, deterministik (CRC32-seed) simüle veri döner; anahtar girilip
`mock_mode` kapatılınca çağıran kod DEĞİŞMEDEN gerçek EOSDA'ya geçer.

## 4. EOSDA 3-Adımlı Akışın Background Job'a Eşlenmesi

EOSDA görüntü/istatistik akışı asenkron/polling tabanlı (webhook YOK). Bu üç
adım TOPRAX tarafında TEK bir background job içinde zincirlenir; kullanıcı sadece
"beklemede/hazır" görür.

```
Kullanıcı / Scheduler                remote_sensing.tasks.run_task
──────────────────────               ───────────────────────────────
"Uydu Analizi Güncelle"   ─────►  create_task(state=queued)
                                        │  (atomik claim → running)
                                        ▼
                          provider.create_field(geometry) ──► field_id  [reuse]
                                        │
              statistics: request_statistics(field_id, indices, range) ─► task_id
              imagery:    search_scenes → request_image_download        ─► task_id
                                        │
                                  _poll(provider, task_id)   ◄── (3) get_task_status
                                        │   (polling, 30-300 sn zoning)
                                        ▼
                          COMPLETED → sonucu işle:
                            • Parcel.remote_sensing güncelle (last_ndvi/last_image_date)
                            • remote_sensing_statistics / remote_sensing_images arşivle
                            • detect_anomaly → publish_anomaly (Communication Policy)
                            • record_task_metric (Monitoring)
```

## 5. Veri Modeli (ASCII)

```
integrations (type="eosda") ── config{api_key*, mock_mode, ...}   *secret-maskeli
        │
        ▼ get_remote_sensing_provider(db)
   EOSDAProvider

remote_sensing_policies { id, name, filter(QueryEngine DSL), frequency,
                          indices[], priority, provider_override, is_active }
        │  scheduler: en yüksek öncelikli politika bir parseli KAZANIR
        ▼
Parcel { ..., remote_sensing { provider, eosda_field_id, last_analysis_date,
                               last_image_date, last_ndvi, last_anomaly, last_updated } }
        │
        ├─► remote_sensing_tasks { id, task_type(search|download|statistics|
        │       zoning|tasking), trigger(manual|scheduled|auto_tasking), state,
        │       retry_count, api_calls, duration_ms, response_summary, error }
        ├─► remote_sensing_statistics { parcel_id, index, avg/min/max/median, series[] }
        ├─► remote_sensing_images { parcel_id, capture_date, cloud_pct, satellite,
        │       image_type, format, is_active }   ← hiçbir görüntü fiziksel SİLİNMEZ
        └─► remote_sensing_metrics { month, total_api_calls, success, failed, ... }
```

## 6. Maliyet & Limit Gerçekleri (dto.py — tek kaynak)

- **1 görüntü = parsel+indeks başına 3 EOSDA isteği** (`EOSDA_REQUESTS_PER_INDEX=3`)
  — düz "1 istek = 1 birim" varsayımı YANLIŞ. Monitoring bu gerçeğe göre hesaplar.
- **Trial hesap 1000 istekle sınırlı** (`EOSDA_TRIAL_REQUEST_LIMIT`) — Monitoring
  ekranında kalan kota görünür.
- **Alan sınırı 200 km²** (`EOSDA_MAX_AREA_KM2`) — çok büyük parsel bölünmeli.
- **Rate limit endpoint bazında** (`EOSDA_RATE_LIMITS_PER_MIN`: weather 10, ...)
  — tek global limit yetersiz.

## 7. Akıllı Tasking + Anomali → Communication Policy (KONU 1.4)

Normal tarama düşük maliyetli/planlı akıştan gelir. Yerel `detect_anomaly` bir
parselde şüphe tespit ederse `request_tasking()` ile o TEK parsel için VHR
talebi oluşturulur (mevcut `satellite_provider.maybe_auto_task_on_anomaly` tenant
kota mantığıyla aynı ruh). Anomali `publish_anomaly()` ile
`remote_sensing_anomaly_detected` event'i olarak yayınlanır — bildirim mantığı
KENDİ modülünde DEĞİL, admin'in IT-27 kural ekranında tanımladığı politikadadır.
Onaylı/onaysız akış o kuralın **`requires_approval`** alanıyla çalışır (KONU 1.4).

## 8. HTTP Yüzeyi (services.py)

| Endpoint | İzin | Açıklama |
|---|---|---|
| `GET /remote-sensing/providers/status` | `remote_sensing:view` | aktif sağlayıcı + mock/gerçek |
| `GET/POST/PUT/DELETE /remote-sensing/policies` | `view` / `settings` | Tarama Politikaları CRUD (soft delete) |
| `GET /remote-sensing/uncovered-parcels` | `view` | "Politikasız Parseller" uyarısı |
| `POST /remote-sensing/manual-sync` | `manual_sync` | Uydu Analizi Güncelle (politikayı bypass, trigger=manual) |
| `POST /remote-sensing/scheduler/run` | `automatic_sync` | tarama turu (kuyruğa yığ → ardışık işle) |
| `GET /remote-sensing/tasks` | `view` | task kuyruğu |
| `GET /remote-sensing/monitoring` | `view` | API/kota/response özeti |
| `GET /remote-sensing/parcels/{id}/timeseries` | `statistics` | zaman serisi |
| `GET /remote-sensing/parcels/{id}/images` | `images` | görüntü arşivi |

Frontend: `pages/RemoteSensing.jsx` (route `/uzaktan-algilama`, menü "ANALİZ & AI").

## 9. Yetkilendirme

`permissions.py` yeni `remote_sensing` modülü: `view / manual_sync /
automatic_sync / settings / provider_manage / images / statistics / download /
delete / task_manage`. **`manual_sync` ayrı bir izindir** — her kullanıcı manuel
analiz başlatamaz; varsayılan olarak Ziraat Mühendisi ve üstü rollere verildi.

## 10. Bu İterasyonda İSKELET (prompt gereği)

- Planet/Airbus/UP42 sağlayıcıları (gerçek hesap açılınca EOSDAProvider deseniyle
  doldurulur; factory/çağıran kod değişmez).
- Provider Comparison Engine, Satellite Timeline birleşik görünümü, Cost
  Management raporlama yüzü — veri modeli hazır, tam UI sonraki iterasyonda.
- Gerçek EOSDA endpoint URL'leri (`api-connect.eos.com/...`) plansal; ilk gerçek
  kullanımda "Bağlantıyı Test Et" (`/integrations/eosda/test`) ile doğrulanmalı.
