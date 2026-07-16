# AI-VIZYON-PLATFORMU-MIMARI.md — TOPRAX Agricultural Intelligence Engine

> Bu doküman `AI-VIZYON-PLATFORMU-PROMPT.md`'nin çıktısıdır. CLAUDE.md,
> ROADMAP.md, ROADMAP-DETAY-TAM.md okunduktan sonra, TOPRAX'in mevcut
> mimari kurallarına (Config Service, RBAC, Query Engine, Event Bus,
> Integration Hub, Provider Pattern, Standard API) **uyarak** yazılmıştır.
> Bağımsız bir sistem değil, TOPRAX'in bir admin modülüdür.

---

## 0. Karar Özeti (prompt'un sorduğu 2 açık karar)

### Karar 1 — Veritabanı/Kuyruk Yığını: **Mongo + in-process** (PostgreSQL/PostGIS/Redis/RabbitMQ DEĞİL)

Kullanıcı bu kararı mimariye en uygun teknik çözümü seçmem için bana
bıraktı. Gerekçe:

1. **Ölçek gerçek değil, varsayımsal:** Faz-1 hedefi 3000-5000 parsel —
   PostGIS'in Mongo'nun 2dsphere index'lerine göre asıl avantaj sağladığı
   nokta (yüz milyonlarca geometri, karmaşık raster-vektör join'leri)
   bu ölçekte devreye girmez. TOPRAX zaten `parcels`/`admin_areas`'ta
   2dsphere index kullanıyor ve `$geoIntersects`/`$geoWithin` ile idari
   alan-parsel kesişimi gibi sorguları bu ölçekte sorunsuz karşılıyor.
2. **Ops yükü, tam da bu projenin öncelik sırasına ters:**
   ROADMAP-URUNLESTIRME.md'nin FAZ P0'ı ("on-premise kurulumun sorunsuz/
   kolay/profesyonel olması EN KRİTİK nokta") bir tek `docker-compose.yml`,
   tek backup scripti (`scripts/backup.sh`), tek migration runner
   (`migrations_engine.py`), tek health-check (`/api/health`) inşa etti.
   İkinci bir veritabanı teknolojisi (Postgres+PostGIS) ve ikinci bir
   mesajlaşma altyapısı (RabbitMQ) eklemek, kurulum sihirbazını, yedekleme
   scriptini, kurulum kılavuzunu, offline bundle'ı — hepsini ikiye katlar.
   Bir kooperatifin IT ekibi artık iki veritabanını da yedeklemeyi,
   yükseltmeyi, izlemeyi öğrenmek zorunda kalır.
3. **CLAUDE.md #6.1 ("mevcut mimari korunur, gereksiz refactoring
   yapılmaz") ilkesiyle doğrudan çelişir** — bu ilke bu projede baştan
   sona tutarlı şekilde uygulandı (Approval Engine, Case Management,
   Satellite Provider hep mevcut desenlerin üzerine inşa edildi, paralel
   sistem açılmadı).
4. **Job queue ihtiyacı RabbitMQ gerektirmeyecek kadar mütevazı:** Faz-1
   tek sunucuda, günde binlerce değil yüzlerce görüntü işlenecek. Mongo
   tabanlı bir "kuyruk koleksiyonu" deseni (`ai_jobs` — durum makinesi:
   `pending → processing → done/failed`, `worker_id` ile kilitleme,
   `FindOneAndUpdate` atomik claim) bu hacimde RabbitMQ'ya eşdeğer
   güvenilirlik sağlar — bkz. Bölüm 8.
5. **Kaçış yolu açık bırakıldı:** Faz 2+'da (bkz. Bölüm 15) AI Engine
   zaten ayrı bir süreç/container olarak çalışacak ve Service Registry
   üzerinden keşfedilecek. İleride gerçek ölçek (onbinlerce parsel,
   yoğun raster analitiği) PostGIS'i haklı çıkarırsa, AI Engine'in KENDİ
   veritabanı bu noktada değiştirilebilir — geri kalan TOPRAX'e dokunmadan
   (mikroservis izolasyonu zaten bu kaçışı sağlıyor). Bugün bunu seçmemek,
   yarın seçememek anlamına gelmiyor.

**Sonuç:** AI Engine, TOPRAX'in geri kalanıyla AYNI MongoDB örneğinde
kendi koleksiyonlarını kullanır (ayrı bir `toprax_ai` mantıksal veritabanı
önerilir — bkz. Bölüm 4 — fiziksel izolasyon için, ama fiziksel sunucu/
teknoloji AYRI DEĞİL). Ham raster/görüntü dosyaları `storage.py`
soyutlaması üzerinden diskte/nesne depoda tutulur (PostGIS de seçilse
raster BLOB'ları zaten veritabanında tutulmazdı — bu karar o boyutu
etkilemiyor). Redis yerine `cache.py`'nin in-process TTL cache'i, RabbitMQ
yerine Mongo tabanlı `ai_jobs` kuyruğu kullanılır.

### Karar 2 — Menü Yerleşimi: **"Ayarlar" altında alt-grup** (kullanıcı onayladı)

"AI Bilgi Kütüphanesi" adıyla **Ayarlar** menüsü altında bir alt-grup
açılır, 8. bir üst menü maddesi AÇILMAZ (CLAUDE.md Kural 3'e tam uyum).
13 ekran, kendi içinde 4 mantıksal sekmeye gruplanır (bkz. Bölüm 14).

---

## 1. Sistem Mimarisi — Genel Bakış (Faz 1)

```
                         ┌─────────────────────────────────────────┐
                         │           TOPRAX Ana Sistemi             │
                         │  (mevcut — değişmedi)                    │
                         │                                           │
                         │  FastAPI api_router (/api/*)              │
                         │   ├─ farmers, parcels, production_cycles  │
                         │   ├─ field_ops, communications, lms       │
                         │   ├─ Query Engine (/api/query/{module})   │
                         │   ├─ Event Bus (platform: event_bus.py)   │
                         │   ├─ Integration Hub (Provider Pattern)   │
                         │   ├─ storage.py (dosya soyutlaması)       │
                         │   └─ RBAC / Audit Log / TenantScopedDB    │
                         └───────────────┬───────────────────────────┘
                                         │  (1) REST çağrısı + (2) Event Bus
                                         │      abone/yayıncı
                         ┌───────────────▼───────────────────────────┐
                         │        AI Engine (YENİ — bu prompt)        │
                         │  Ayrı Python süreci/container, AYNI Mongo   │
                         │  örneğine bağlanır (toprax_ai veritabanı)   │
                         │                                             │
                         │  ┌───────────────────────────────────────┐  │
                         │  │  API Katmanı (FastAPI, /ai/* prefix,   │  │
                         │  │  Standard API sözleşmesine uyar)       │  │
                         │  └───────────────┬───────────────────────┘  │
                         │                  │                          │
                         │  ┌───────────────▼───────────────────────┐  │
                         │  │  Orchestration & Job Queue              │  │
                         │  │  (ai_jobs koleksiyonu, worker havuzu)    │  │
                         │  └───────────────┬───────────────────────┘  │
                         │                  │                          │
                         │  ┌───────────────▼───────────────────────┐  │
                         │  │  Pipeline: Ön İşleme → Spektral Analiz  │  │
                         │  │  → Kural Motoru → Yerel AI Modelleri    │  │
                         │  │  → Confidence Engine                    │  │
                         │  └───────────────┬───────────────────────┘  │
                         │         yüksek güven │  düşük güven         │
                         │                  │    └──────────┐          │
                         │                  ▼               ▼          │
                         │            sonucu döndür   Cloud Escalation │
                         │                             (tenant kota +   │
                         │                              redaksiyon)     │
                         │                  │               │          │
                         │                  ▼               ▼          │
                         │        ┌──────────────────────────────┐    │
                         │        │  Agricultural Knowledge Library │  │
                         │        │  (dataset/annotation/versiyon)  │  │
                         │        └──────────────────────────────┘    │
                         └─────────────────────────────────────────────┘
                                         │
                         ┌───────────────▼───────────────────────────┐
                         │  Görüntü Kaynakları (mevcut soyutlamalar)   │
                         │  Uydu (IT-17/satellite_provider.py)         │
                         │  Mobil (IT-35 Saha Personeli kamera)        │
                         │  Drone / Lab / Sensör (Integration Hub —    │
                         │  yeni Provider'lar)                         │
                         └─────────────────────────────────────────────┘
```

**Neden ayrı süreç, ama aynı veritabanı?** "Bağımsız mikroservis"
gereksinimi (prompt Bölüm "Faz-1 Altyapı Kısıtı") CPU/GPU izolasyonu ve
bağımsız deploy/restart döngüsü içindir — bunun için ayrı bir
veritabanı teknolojisi GEREKMEZ, ayrı bir **süreç/container** ve ayrı
bir **kod tabanı** yeterlidir. Bu, Faz 2'de AI Engine'i başka bir
sunucuya taşırken sadece `MONGO_URL`'i (aynı protokolle, uzaktaki aynı
Mongo'ya veya kendi yeni Mongo'suna) değiştirmeyi gerektirir —
mimari değişmez (bkz. Bölüm 15, Service Registry).

---

## 2. Modül Hiyerarşisi ve Bileşen Sorumlulukları

```
backend/ai_engine/                      # YENİ, ayrı bir Python paketi (ayrı süreç olarak da çalışabilir)
├── server.py                           # FastAPI app, /ai prefix'i, TOPRAX api_router'a mount edilir (Faz 1)
├── config.py                           # config_service.py'den DERİVE eder (aynı MONGO_URL, aynı JWT_SECRET) — ayrı bir config sistemi İCAT EDİLMEZ
├── knowledge_library/
│   ├── models.py                       # Dataset, KnowledgeRecord, Annotation, Taxonomy
│   ├── routes.py                       # CRUD (crud_base.py'den türetilir — PR-23)
│   └── search.py                       # Query Engine filter DSL genişletmesi (yeni search değil)
├── pipeline/
│   ├── preprocessing.py                # format normalize, resize, renk kalibrasyonu
│   ├── spectral.py                     # NDVI/NDRE/spektral indeks hesaplama (satellite_provider.py'nin ndvi_to_health'iyle PAYLAŞILIR)
│   ├── rule_engine.py                  # eşik/kural bazlı ön-filtre (örn. "NDVI<0.3 → su stresi şüphesi")
│   └── local_models/
│       ├── registry.py                 # hangi model hangi görev için (bkz. Bölüm 7)
│       ├── runners/                    # her model ailesi için ince bir çalıştırıcı (YOLO/SAM2/U-Net/...)
│       └── inference.py                # ortak inference arayüzü (girdi: görüntü+bbox, çıktı: standart Prediction şeması)
├── confidence/
│   ├── engine.py                       # güven skoru birleştirme + eşik kararı
│   ├── tenant_quota.py                 # aylık AI bütçe/kota takibi (tenant bazlı)
│   └── cloud_escalation.py             # ai_provider.py (mevcut Provider Pattern) üzerinden GPT/Claude/Gemini'ye escalate + redaksiyon filtresi
├── active_learning/
│   ├── validation_queue.py             # düşük güven/yeni/nadir durum önceliklendirme
│   └── case_bridge.py                  # case_management.py'ye "AI Doğrulama" kategorisiyle KÖPRÜ (yeni mesajlaşma İCAT EDİLMEZ)
├── mlops/
│   ├── model_registry.py               # versiyon/deploy/rollback/golden-dataset regresyon testi
│   └── health.py                       # platform_core.py Health Center'a "AI Model Sağlığı" satırı ekler
├── jobs/
│   └── queue.py                        # ai_jobs koleksiyonu üzerinden atomik claim + retry + öncelik
└── events.py                           # event_bus.py'ye AIHastalikTespitEdildi/AIRiskOlustu yayınlar (TEK yayın noktası)
```

**Sorumluluk sınırları (kritik):**
- Bu paket **kendi kimlik doğrulamasını, kendi RBAC'ını, kendi audit
  log'unu, kendi arama motorunu, kendi depolamasını, kendi bildirim
  mekanizmasını YAZMAZ.** Her biri için TOPRAX'in mevcut modülünü
  import eder (server.py'deki `register_*_routes` deseniyle aynı
  şekilde `register_ai_engine_routes(api_router, db, current_user,
  require_permission, log_audit)` olarak TEK bir noktadan bağlanır).
- Ana `server.py`, AI Engine paketinin `register_ai_engine_routes`'unu
  tıpkı `organization.py`/`approval.py`/`satellite_provider.py` gibi
  import edip çağırır (Faz 1'de aynı process içinde). Faz 2'de bu satır
  yerini bir HTTP proxy/Service Registry lookup'ına bırakır (Bölüm 15).

---

## 3. Görüntü Kaynakları — Provider Pattern Genişlemesi

| Kaynak | Mevcut mu? | Bu platformdaki rolü |
|---|---|---|
| Uydu | ✅ `satellite_provider.py` (IT-28.1) | AI Engine'in GİRDİSİ — kendi entegrasyonu yazılmaz, `get_satellite_provider()` çıktısı pipeline'a beslenir. |
| Mobil (Saha Personeli) | ✅ IT-35 mobil rol matrisi, "AI Kamera" planlı | AI Engine bu akışın BACKEND'idir — mobil çekim/upload yapar, offline kuyruğa eklenmiş fotoğraf senkron olunca `ai_jobs`'a otomatik girer (bkz. IT-52). |
| Drone | ⬜ Yeni | Integration Hub'a yeni bir `DroneProvider` (Provider Pattern, `integration_hub.py`'deki mock_mode konvansiyonuyla). |
| Laboratuvar | ⬜ Yeni | Manuel upload (Knowledge Library'nin genel upload ucu) — canlı bir API entegrasyonu YOKSA gerek de yok. |
| Sensör/IoT | ⬜ Yeni | Mevcut `iot_sensors` koleksiyonu zaten var (extras.py) — görüntü değil sayısal veri ürettiği için pipeline'a "ek bağlam" (context) olarak beslenir, görüntü pipeline'ından geçmez. |

Her yeni kaynak (Drone/Lab/Sensör), `satellite_provider.py`'deki
`SatelliteProvider` ABC desenine benzer şekilde bir `ImageSourceProvider`
ABC'sine uyar — `get_images(parcel_id, date_range)` tek ortak arayüz.

---

## 4. Veritabanı Tasarımı

Mantıksal veritabanı adı: `toprax_ai` (aynı Mongo örneği, ayrı DB — hem
izolasyon hem de "AI Engine'in verisi hangi koleksiyonlarda" sorusuna
net cevap için). Tenant izolasyonu AYNI `TenantScopedDB` sarmalayıcısı
ile sağlanır (yeni bir izolasyon mekanizması İCAT EDİLMEZ).

### 4.1 Çekirdek Koleksiyonlar

```
ai_datasets                 { id, name, description, source_type (uydu|drone|mobil|lab|sensor),
                               tenant_id, created_at, version, status (draft|active|archived),
                               tag_taxonomy_id, record_count, quality_score_avg }

ai_knowledge_records         { id, dataset_id, tenant_id,
                               source_type, source_ref (uploads koleksiyonuna FK — storage.py),
                               captured_at, gps: {lat,lon} (opsiyonel),
                               # TOPRAX varlık bağlantıları (opsiyonel, prompt'un istediği eklenti):
                               parcel_id, production_cycle_id, farmer_id,
                               object_type (urun|gelisim_evresi|hastalik|zararli|besin_eksikligi|
                                            su_stresi|yabani_ot|yangin|sel|hasat_olgunlugu|
                                            toprak_durumu|hava_durumu),
                               labels: [ {taxonomy_key, confidence, source (insan|model|hibrit)} ],
                               annotations: [ {type (bbox|polygon|mask|classification),
                                               geometry, class_id, created_by, created_at} ],
                               quality_score, expert_notes, comments: [...],
                               approval_status (taslak|incelemede|onayli|reddedildi),
                               version, previous_version_id,
                               created_at, updated_at, is_active }

ai_taxonomy                  { id, tenant_id (null = platform-geneli), parent_id, key, label,
                               object_type, description, icon, is_active }
                              # Ürün/Hastalık/Zararlı/... ontolojisi — knowledge graph'a evrilebilir
                              # (parent_id zaten basit bir ağaç kurar; "knowledge graph olasılığı"
                              # ai_taxonomy_relations adında AYRI, opsiyonel bir koleksiyonla
                              # (relation_type: "sebep_olur"|"benzer"|"ile_karistirilir") Faz 3'te açılır)

ai_models                    { id, name, task_type (detection|segmentation|classification|
                               change_detection|anomaly_detection), framework, version,
                               file_ref (storage.py), status (training|validation|staging|
                               production|retired|rolled_back), golden_dataset_id,
                               metrics: {precision, recall, f1, iou, drift_score},
                               deployed_at, deployed_by, previous_model_id }

ai_predictions                { id, tenant_id, knowledge_record_id, model_id, task_type,
                               raw_output, confidence, decision (auto_approved|
                               escalated_to_cloud|pending_expert_review|expert_corrected),
                               cloud_provider_used (null|"gpt-4-vision"|"claude"|"gemini"),
                               cloud_cost_estimate, case_id (bkz. active_learning köprüsü),
                               created_at }

ai_jobs                       { id, tenant_id, job_type, payload_ref, status
                               (pending|claimed|processing|done|failed|retrying),
                               priority, worker_id, claimed_at, attempts, max_attempts,
                               error, created_at, completed_at }
                               # RabbitMQ yerine: FindOneAndUpdate({status:"pending"},
                               # {$set:{status:"claimed", worker_id, claimed_at}}) ATOMIK claim

ai_tenant_quota               { tenant_id, month (YYYY-MM), cloud_calls_used, cloud_cost_used,
                               monthly_limit_calls, monthly_limit_cost, alert_threshold_pct }

ai_active_learning_queue      { id, tenant_id, knowledge_record_id, prediction_id, priority_score,
                               reason (dusuk_guven|bilinmeyen_nesne|yeni_hastalik|nadir_durum|
                               anomali), status (bekliyor|incelemede|tamamlandi), case_id }

ai_audit_extension             # AYRI koleksiyon YOK — TOPRAX'in mevcut audit_logs'u kullanılır,
                                # entity="ai_knowledge_record"/"ai_model"/"ai_prediction" olarak.
```

### 4.2 İlişki Diyagramı (özet)

```
ai_datasets ──1:N── ai_knowledge_records ──N:1── ai_taxonomy (labels üzerinden)
                         │                              │
                         │ (opsiyonel FK)                └─ parent_id (ağaç/ontoloji)
                         ▼
        TOPRAX: parcels / production_cycles / farmers
                         │
                         ▼
              ai_predictions ──N:1── ai_models
                    │
                    ├─ decision=escalated_to_cloud → ai_tenant_quota (düşülür)
                    └─ decision=pending_expert_review → ai_active_learning_queue → case_management.py (Case, category="AI Doğrulama")
```

### 4.3 Versiyonlama

`ai_knowledge_records` ve `ai_models` **kendi kaydını mutasyona
uğratmaz** — TOPRAX'in ledger.py'deki "silinmezlik" felsefesiyle aynı
ruh: bir düzeltme/yeniden etiketleme, `previous_version_id`'si eski
kayda işaret eden YENİ bir doküman olarak eklenir, `version` artırılır.
Eski versiyon `is_active=false` olur ama SİLİNMEZ (denetim izi + model
regresyonunda "eski etiketle ne olurdu" sorusuna cevap verebilmek için).

---

## 5. Agricultural Knowledge Library — Mimari Detay

**Upload akışları:** tekli, toplu (çoklu dosya seçimi), klasör
(webkitdirectory), ZIP (sunucu tarafında açılıp her dosya ayrı
`ai_knowledge_records` kaydına dönüştürülür — `geo_import.py`'nin toplu
parsel import deseniyle AYNI "önizle → doğrula → onayla" akışı).
Fiziksel dosyalar **storage.py** üzerinden yazılır (`module="ai_knowledge"`,
`entity_id=knowledge_record_id`) — yeni bir depolama katmanı YOK.

**Annotation editörü:** bbox/polygon/segmentation mask çizimi için
frontend'de **mevcut `leaflet-draw`/`@turf/turf` kütüphaneleri
(zaten kurulu — parsel çizim aracı IT-14/15) görüntü-üzeri annotation'a
uyarlanır** (raster üzerinde piksel koordinatlı çizim — Leaflet'in
`CRS.Simple` modu görüntü/piksel koordinat sistemleri için tam olarak
bunun için var, coğrafi CRS değil). Yeni bir çizim kütüphanesi
kurulmaz.

**Onay iş akışı:** `approval_status` alanı (taslak→incelemede→onaylı/
reddedildi) — bu geçişler **approval.py'nin `maybe_start_approval()`**
fonksiyonuyla (opsiyonel, tenant ayarına göre) Organizasyon
Hiyerarşisi'ndeki onay zincirine bağlanabilir (örn. "yeni bir hastalık
taksonomisi eklemek Ziraat Müdürü onayı gerektirir").

**Versiyon geçmişi / kalite skoru / yorumlar:** Bölüm 4.1'deki şema
zaten bunları taşıyor; UI'da `CaseManagement.jsx`'teki mesajlaşma
bileşeni (`case_id` üzerinden) yorumlar için yeniden kullanılır.

---

## 6. Yerel AI Modelleri — Öneriler

| Görev | Önerilen model(ler) | GPU gerek. | CPU uyumlu | Bellek | Inference hızı (CPU) | Eğitim zorluğu | Lisans / **Ticari on-premise uygunluğu** |
|---|---|---|---|---|---|---|---|
| Object Detection (zararlı, meyve sayımı) | **YOLOv8/v11** (Ultralytics) | Orta (eğitimde) | ✅ (inference, yavaş) | ~200MB-2GB | Orta (nano/small modelde kabul edilebilir) | Düşük-Orta (transfer learning) | **AGPL-3.0 (Ultralytics)** ⚠️ — ticari on-premise dağıtımda AGPL yükümlülüğü doğurabilir, Ultralytics'in **ticari lisansı** satın alınmalı (bkz. PR-17 girdisi) VEYA Apache-2.0 lisanslı alternatif (örn. YOLOX, MMDetection modelleri) tercih edilmeli. |
| Segmentation (parsel/yaprak alanı) | **SAM2** (Meta) | Yüksek (büyük varyant) / Orta (tiny) | ✅ (tiny/small) | 1-4GB | Yavaş-Orta | Düşük (zero-shot, fine-tune opsiyonel) | Apache-2.0 — ✅ ticari on-premise için sorunsuz. |
| Segmentation (piksel-hassas hastalık alanı) | **U-Net / SegFormer** | Orta | ✅ | 200MB-1GB | Orta | Orta-Yüksek (etiketli veri gerekir) | Genelde MIT/Apache (uygulamaya göre değişir — model kartı kontrol edilmeli) — ✅. |
| Classification (hastalık/ürün türü) | **Vision Transformer (ViT-B) / EfficientNet** | Düşük-Orta | ✅ | 100-500MB | Hızlı | Düşük-Orta | Apache-2.0/MIT — ✅. |
| Change Detection (zaman serisi NDVI/parsel değişimi) | **Siamese U-Net** veya kural-tabanlı fark analizi (spektral eşik) | Düşük | ✅ | <500MB | Hızlı | Düşük (çoğunlukla kural motoruyla çözülebilir, model şart değil) | Kendi eğitilen model — lisans sorunu yok. |
| Anomaly Detection (beklenmeyen desen — hastalık/yangın erken uyarı) | **Autoencoder tabanlı (basit CNN-AE)** + istatistiksel eşik | Düşük | ✅ | <300MB | Hızlı | Orta | Kendi eğitilen model. |
| Coğrafi/Uydu Foundation Model (gelecek, büyük ölçek NDVI/arazi sınıflandırma) | **Prithvi (IBM/NASA)** veya **Clay Foundation Model** | Yüksek (fine-tune), Orta (inference) | Kısmi | 1-4GB+ | Yavaş (CPU'da pratik değil, Faz 3+ GPU'ya ertelenir) | Yüksek | Prithvi: Apache-2.0 ✅. Clay: Apache-2.0 ✅. Faz-1'de kullanılmaz (CPU-only kısıtı), Faz 3+ için işaretlenir. |

**Genel lisans notu (PR-17 girdisi):** Yukarıdaki tablodaki **⚠️
işaretli AGPL-3.0** tek gerçek risk noktasıdır — Ultralytics YOLO
ailesi en olgun/hızlı seçenek olduğu için cazip, ama TOPRAX ticari
olarak on-premise satılacağı için (ROADMAP-URUNLESTIRME.md), ya
Ultralytics Enterprise lisansı satın alınmalı ya da Apache-2.0
lisanslı bir detection modeline (YOLOX, RT-DETR — Apache-2.0)
geçilmeli. Bu karar `docs/legal/BAGIMLILIK-LISANS-RAPORU.md`'ye
(PR-17, zaten var) bir "ML modelleri" bölümü olarak eklenmelidir
(bkz. IT-51 kabul kriterleri).

---

## 7. Confidence Engine ve AI Orchestration

### 7.1 Karar Akışı

```
1. Görüntü ai_jobs'a girer (kaynak: upload / satellite_provider / mobil senkron)
2. Worker (jobs/queue.py) FindOneAndUpdate ile job'ı atomik claim eder
3. pipeline/preprocessing.py  — format normalize, boyutlandırma
4. pipeline/spectral.py       — varsa NDVI/spektral indeks (uydu/drone görüntüsü)
5. pipeline/rule_engine.py    — ucuz, deterministik ön-eleme
     ├─ kural kesin sonuç veriyorsa → SONUÇ (confidence=1.0, cloud'a gitmez)
     └─ belirsizse → adım 6
6. local_models/inference.py  — 1+ yerel model çalışır (görev tipine göre Bölüm 6 tablosu)
7. confidence/engine.py       — model(ler)in çıktısını birleştirir (tek modelse
                                 kendi skoru, birden çoksa ağırlıklı konsensüs —
                                 modeller anlaşmıyorsa güven otomatik düşürülür)
8. Eşik karşılaştırması:
     ├─ confidence >= tenant'ın "otomatik onay eşiği" → SONUÇ (auto_approved)
     ├─ confidence < eşik VE tenant kotası müsaitse → confidence/cloud_escalation.py
     │      └─ ai_provider.py (mevcut Provider Pattern) üzerinden GPT/Claude/Gemini
     │         ÖNCESİNDE: redaksiyon filtresi (Bölüm 9) uygulanır
     └─ confidence < eşik VE kota dolu → SONUÇ (confidence düşük olarak işaretli,
            kullanıcıya "bütçe nedeniyle bulut doğrulaması yapılmadı" uyarısı)
9. Düşük güvenli/anomali/nadir sonuçlar → active_learning/validation_queue.py
   → case_bridge.py → case_management.py (Case, category="AI Doğrulama")
10. Sonuç: ai_predictions'a yazılır + event_bus.py'ye ilgili olay yayınlanır (Bölüm 16)
```

### 7.2 Çoklu Model Konsensüsü

Aynı görev için birden fazla yerel model varsa (örn. hem YOLO hem
kural-tabanlı bir ön-filtre), `confidence/engine.py` şu stratejiyi
uygular: modeller AYNI sınıfta hemfikirse güven ortalaması + bonus
(+%10, tavan %99); modeller ÇELİŞİYORSA güven otomatik olarak
en düşük skorun altına çekilir (belirsizlik saklanmaz, escalation'a
zorlanır). Bu, "sessizce yanlış ama kendinden emin" bir sonucun
otomatik onaylanmasını engeller.

### 7.3 Job Queue Detayı (RabbitMQ karşılığı)

```python
# jobs/queue.py — kavramsal özet, gerçek kod IT-48'de yazılacak
async def claim_next_job(db, worker_id: str, job_types: list[str]):
    return await db.ai_jobs.find_one_and_update(
        {"status": "pending", "job_type": {"$in": job_types}},
        {"$set": {"status": "claimed", "worker_id": worker_id, "claimed_at": now()}},
        sort=[("priority", -1), ("created_at", 1)],   # yüksek öncelik + FIFO
        return_document=AFTER,
    )
```

Retry: `attempts < max_attempts` ise `status="retrying"` + üstel geri
çekilme (backoff) ile yeniden `pending`'e döner (twilio-reliability
desenindeki 429 backoff mantığıyla aynı prensip). Batch processing:
worker'lar `job_type` bazlı havuzlarda çalışır (örn. "hafif" CPU
job'ları vs "ağır" GPU job'ları — Faz 3'te GPU worker'ları ayrı bir
havuz olarak eklenir, mimari değişmez).

---

## 8. Tenant Bazlı Maliyet İzolasyonu

`ai_tenant_quota` koleksiyonu, her tenant+ay için `cloud_calls_used`/
`cloud_cost_used` sayaçlarını tutar. `cloud_escalation.py`, her
escalation ÖNCESİNDE bu sayacı kontrol eder — **atomik increment**
(`$inc`) ile race condition'lar engellenir. Kota %80'e ulaştığında
tenant admin'ine bildirim (Comm Hub üzerinden, kendi mantığı
YAZILMADAN — mevcut bildirim akışı kullanılır). Kota dolduğunda:
sonuç YİNE DÖNER (asla sessiz hata), ama `decision` alanı
`"low_confidence_no_cloud_budget"` olarak işaretlenir ve kullanıcı
arayüzünde (Prediction Review ekranı) açıkça bu uyarı gösterilir.
Bir tenant'ın kotası dolması, DİĞER tenant'ların sayaçlarını
etkilemez (her sayaç `tenant_id` ile izole, TenantScopedDB zaten bunu
garanti eder).

---

## 9. Cloud Escalation — Redaksiyon Filtresi

`cloud_escalation.py`, `ai_provider.py`'ye (mevcut AI Provider Pattern)
görüntüyü göndermeden ÖNCE zorunlu bir redaksiyon adımından geçirir:
- Gönderilen: SADECE görüntünün kendisi (kırpılmış/gerekliyse
  yeniden boyutlandırılmış) + teknik metadata (çekim tarihi, GPS
  **opsiyonel** — parsel bazlı analiz gerekmiyorsa gönderilmez).
- Gönderilmeyen: çiftçi adı, TC kimlik no, telefon, adres, IBAN,
  üye no — hiçbiri prompt'a veya dosya adına eklenmez (dosya adı
  `ai_knowledge_record.id` (UUID) olarak yeniden adlandırılır, orijinal
  dosya adı sızmaz).
Bu, field_definitions.py'nin `sensitive` alan maskeleme prensibiyle
(IT-07) aynı ruhtadır — sadece response'ta değil, DIŞARI giden
istekte de uygulanır.

---

## 10. Active Learning ve Human-in-the-Loop

**Önceliklendirme (`validation_queue.py`):** düşük güven, bilinmeyen
taksonomi sınıfı, yeni/nadir `object_type`, model konsensüsünde
çelişki — her biri bir `priority_score` bileşeni, toplamı sıralamayı
belirler.

**Uzman Doğrulama Ekranı:** renk kodlu (kırmızı=acil/düşük güven,
sarı=orta, yeşil=rutin), onay/düzeltme/"yeniden eğitim için işaretle"
aksiyonları, performans istatistikleri (uzmanın ne kadar süredeyse
kaç kayıt işlediği). **Ayrı bir mesajlaşma sistemi İCAT EDİLMEZ** —
`case_bridge.py`, her doğrulama-bekleyen tahmin için `case_management.py`
üzerinden `category="AI Doğrulama"` bir Case açar; uzman bu Case'i
KENDİ "Onay Bekleyenlerim" (IT-07b, `PendingApprovals.jsx`) ekranında,
diğer onaylarıyla aynı yerde görür. Onay/düzeltme, Case'in mesajlaşma
akışına (`CaseMessage`) bir not olarak düşer + `ai_knowledge_records`'a
`labels[].source="hibrit"` (insan düzeltmesi) olarak yeni bir versiyon
eklenir (Bölüm 4.3).

**Otomatik eğitim verisi üretimi:** onaylanan/düzeltilen her kayıt,
`mlops/model_registry.py`'nin bir sonraki eğitim döngüsünde
kullanacağı "altın standart" (golden) veri setine otomatik eklenir
(`ai_knowledge_records.approval_status="onayli"` filtre koşulu).

---

## 11. MLOps Stratejisi

**Model Registry (`ai_models` koleksiyonu, Bölüm 4.1):** her model
sürümü `training→validation→staging→production→retired` durum
makinesinden geçer (CLAUDE.md'nin diğer modüllerdeki durum makinesi
konvansiyonuyla — `ALLOWED_TRANSITIONS` deseni — AYNI).

**Golden Dataset Regresyon Testi (zorunlu kapı):** yeni bir model
`staging`'den `production`'a geçmeden ÖNCE, `golden_dataset_id`
üzerinde çalıştırılır; metrikleri (precision/recall/F1/IoU) MEVCUT
production modelinin metriklerinden **kötüyse** deploy otomatik
reddedilir (kabul kriteri — Bölüm "Beklenen Çıktı" bunu zorunlu
kılıyor). Bu kontrol `mlops/model_registry.py`'de `deploy_model()`
fonksiyonunun ilk adımıdır.

**Rollback:** `previous_model_id` alanı sayesinde tek komutla önceki
production modeline dönülür (migrations_engine.py'nin PR-04'teki
otomatik rollback felsefesiyle aynı desen: hatalı bir değişiklik veri
kaybı olmadan geri alınabilir olmalı).

**Health Center Entegrasyonu:** `mlops/health.py`, `platform_core.py`
Health Center'ına (`GET /platform-core/health` — PR-04'te zaten
`schema_version` satırı eklenmişti, AYNI desenle) yeni bir servis
kaydı ekler: `{"service": "ai_model_health", "label": "AI Model Sağlığı",
"status": "saglikli|uyari|hata", "detail": "drift_score: 0.03, hata
oranı: %2.1"}`. Yeni bir izleme ekranı İCAT EDİLMEZ, var olan panele
bir satır eklenir.

---

## 12. Performans ve Güvenlik

- **CPU-first tasarım:** Faz-1'de TÜM yerel modeller CPU'da çalışacak
  şekilde seçilir (Bölüm 6 tablosundaki "CPU uyumlu" sütunu zorunlu
  filtre) — GPU sadece Faz 3+'ta, ayrı bir worker havuzu olarak eklenir.
- **RBAC:** yeni permission'lar `permissions.py`'nin `PERMISSION_CATALOG`'una
  eklenir (yeni bir yetkilendirme sistemi YOK): `ai_knowledge:view`,
  `ai_knowledge:create`, `ai_knowledge:approve`, `ai_knowledge:manage`,
  `ai_model:view`, `ai_model:deploy`, `ai_model:rollback`,
  `ai_prediction:view`, `ai_prediction:validate`.
- **Audit:** her create/update/approve/deploy/rollback `log_audit()`
  ile (mevcut audit.py) kaydedilir — ayrı bir log mekanizması YOK.
- **Görüntü şifreleme/güvenli depolama:** storage.py'nin mevcut
  tahmin edilemez UUID dosya adı + tenant eşleşme kontrolü (bkz.
  storage.py docstring'i) zaten uygulanıyor, AI Engine bunu miras alır.
- **API güvenliği:** tüm `/ai/*` uçları Standard API sözleşmesine
  (PR-22/23) ve API Key mekanizmasına (PR-24) tabidir — dış bir MLOps
  aracı (örn. bir CI/CD pipeline) `ai_model:deploy` scope'lu bir API
  Key ile bu uçları çağırabilir.

---

## 13. API Tasarımı

Tüm uçlar `/api/ai/*` prefix'i altında, **PR-22/23'ün Standard API
sözleşmesine** (data/meta/error zarfı `/api/v1` üzerinden, Create/
Update/Delete-Soft/Get/GetById/Search/Filter/Bulk/Import/Export)
uyar ve `crud_base.py`'den (`build_crud_router`) türetilir:

| Kaynak | Uçlar |
|---|---|
| Dataset | `POST/GET/PUT/DELETE /ai/datasets`, `POST /ai/datasets/{id}/import` (ZIP/toplu) |
| Knowledge Record | `POST/GET/PUT/DELETE /ai/knowledge-records`, `POST /ai/knowledge-records/bulk`, `GET /ai/knowledge-records/export` |
| Annotation | `POST/PUT /ai/knowledge-records/{id}/annotations` |
| Prediction | `POST /ai/predict` (senkron küçük görev) / `POST /ai/predict/async` (ai_jobs'a düşer, `GET /ai/jobs/{id}` ile durum sorgulanır) |
| Model | `GET/POST /ai/models`, `POST /ai/models/{id}/deploy`, `POST /ai/models/{id}/rollback` |
| Training | `POST /ai/models/{id}/train`, `GET /ai/models/{id}/training-history` |
| Validation (Active Learning) | `GET /ai/validation-queue`, `POST /ai/validation-queue/{id}/decide` |
| Knowledge Search | Ayrı bir arama motoru YOK — `POST /api/query/ai_knowledge_records` (Query Engine'in genişletilmiş `MODULE_COLLECTIONS`'ı, yeni `CORE_FILTERABLE_FIELDS["ai_knowledge_records"]` girdisiyle). |

**Otomatik Postman collection'a dahil olma:** `scripts/generate_postman_collection.py`
(PR-25) zaten `server.app.openapi()` introspection'ı kullandığı için
bu modül HİÇBİR ek kod olmadan otomatik collection'a girer.

---

## 14. Ekranlar (13 ekran → Ayarlar altı 4 sekme)

**Menü:** Ayarlar → **AI Bilgi Kütüphanesi** (yeni alt-grup, Layout.jsx'in
`SİSTEM` grubundaki diğer alt-öğelerle aynı desende).

| Sekme | Ekranlar |
|---|---|
| **Kütüphane** | Knowledge Library (liste+filtre), Dataset Manager, Image Browser, Annotation Screen, Dataset Statistics |
| **Doğrulama** | Expert Validation Screen (Active Learning kuyruğu), Prediction Review |
| **Model Yönetimi** | Model Training Screen, Model Management, Model Comparison, Training History |
| **İzleme** | AI Monitoring Dashboard, Inference History |

13. ekran (Knowledge Search) ayrı bir sayfa değildir — mevcut Global
Search (`GlobalSearch.jsx`) ve Query Engine tabanlı filtre panelinin
bir uzantısıdır (Bölüm 13).

---

## 15. Deployment Mimarisi ve Ölçeklenebilirlik Yol Haritası

```
Faz 1 — Tek Sunucu (mevcut hedef)
  [ Mongo | FastAPI (TOPRAX) | FastAPI (AI Engine, aynı process'e mount) | React | Nginx ]
  Job worker: aynı process içinde asyncio background task.

Faz 2 — Ayrı AI Sunucusu
  [ Sunucu A: Mongo | TOPRAX API | React | Nginx ]
  [ Sunucu B: AI Engine (ayrı container/VM), AYNI Mongo'ya uzaktan bağlanır ]
  TOPRAX → AI Engine çağrıları artık network üzerinden (mevcut /api/ai/*
  path'i DEĞİŞMEZ) — bir "Service Registry" kaydı (yeni bir koleksiyon,
  `service_registry`: {service_name, base_url, health_check_path}) TOPRAX'e
  AI Engine'in GÜNCEL adresini söyler; hiçbir modül adresi hardcode etmez.

Faz 3 — Çoklu AI Worker
  [ Sunucu B: AI Engine API (stateless) ]
  [ Sunucu C, D, ...: Job Worker havuzu (ai_jobs'tan claim eder) ]
  GPU worker'ları burada devreye girer (job_type="gpu_inference" havuzu).

Faz 4 — Dağıtık AI Cluster
  [ AI Engine API (N replika, load balancer arkasında) ]
  [ Worker havuzu (otomatik ölçeklenen, K8s/Nomad benzeri bir orkestratör) ]
  [ Mongo (replika seti — bu noktada zaten TOPRAX'in genel HA ihtiyacıyla örtüşür) ]
```

Her fazda **iş mantığı değişmez** — sadece "kaç süreç, nerede, nasıl
keşfediliyor" değişir. Bu, prompt'un "mimari değişmeden taşınabilmeli"
gereksinimini TOPRAX'in kendi diliyle (Service Registry + değişmeyen
API sözleşmesi) karşılar.

---

## 16. Event Bus Entegrasyonu

`event_bus.py`'nin `EVENT_TYPES` sözlüğüne eklenecek yeni olaylar
(TEK yayın noktası: `ai_engine/events.py`):

```python
EVENT_TYPES = {
    ...,  # mevcutlar değişmedi
    "ai_disease_detected": "AI Hastalık Tespit Etti",
    "ai_risk_detected": "AI Risk Tespit Etti",
    "ai_validation_needed": "AI Doğrulama Gerekiyor",
    "ai_model_deployed": "AI Modeli Devreye Alındı",
}
```

Bilinen tüketiciler (yeni kod YAZMADAN, sadece `subscribe()` ile
bağlanır): **Saha Operasyonları** (`ai_disease_detected` →
`field_ops.create_field_task_from_rule()` — docx'teki "AI hastalık
tespit etti → görev" senaryosu), **Comm Hub** (`ai_risk_detected` →
Communication Policy üzerinden çiftçi/mühendise bildirim), **Harita**
(AI Harita Asistanı sorgularına girdi — IT-17).

---

## 17. Mobil AI Kamera Köprüsü

Mobil taraf (IT-35) fotoğraf/video çeker + GPS/zaman damgası ekler +
(offline ise) yerel kuyruğa alır. Senkron olduğunda, mevcut upload
ucu (`storage.py` üzerinden) çağrılır ve **AI Engine bu upload'ı
event bus üzerinden dinler** (`upload_completed` olayı — mevcut
generic upload akışına eklenir) → otomatik olarak `ai_jobs`'a bir
"mobil görüntü analizi" job'ı düşer. Kullanıcı hiçbir ek aksiyon
almaz — çekim yapar, analiz arka planda biter, sonuç Case/bildirim
olarak geri gelir.

---

## 18. Bilinen Riskler / Açık Sorular (bir sonraki oturuma taşınacak)

1. **Ultralytics/YOLO lisans riski** (Bölüm 6) — nihai model seçimi
   netleşmeden `docs/legal/BAGIMLILIK-LISANS-RAPORU.md` güncellenmeli.
2. **CPU inference hızı gerçek donanımda doğrulanmalı** — Bölüm 6
   tablosundaki "hızlı/orta/yavaş" nitel tahminlerdir, IT-48
   tamamlandığında gerçek benchmark ile PR-14 (k6/yük testi) tarzı bir
   "AI inference süresi" ölçümü eklenmeli.
3. **Taksonomi/ontoloji'nin ilk içeriği** (hangi hastalık/zararlı/ürün
   listesi) kuruma özeldir — IT-47 kabul kriterlerinde "en az N örnek
   taksonomi kaydı seed edilir" şeklinde netleştirilmeli, kullanıcıdan
   bölge/ürün profili istenmeli (PR-18 demo tenant scriptindeki
   yaklaşımla aynı).
4. **Cloud AI sağlayıcı seçimi** (GPT-4V/Claude/Gemini) — `ai_provider.py`
   zaten bir Provider Pattern'e sahip (mock_mode dahil), ama hangi
   sağlayıcının varsayılan olacağı ve API anahtarlarının (yine kullanıcı
   tarafından "sonra gireceğim" dediği satellite entegrasyonu gibi)
   ne zaman gireceği netleşmeli.
