# CLAUDE.md — TABSİS Proje Hafızası

> Bu dosya her oturumun başında okunmalıdır. Amaç: yeni bir Claude oturumunun
> projeyi sıfırdan keşfetmeden doğru kararlar verebilmesi.
> Son güncelleme: 2026-07-10 (IT-24 sonrası — FAZ 8 TAMAMLANDI: Otomasyon Motoru + Saha Raporları + Modül Dashboard'u)

---

## 1. Proje Kimliği

**TABSİS (Dijital Tarım Platformu)** — kooperatif/fabrika/kamu kurumlarının
çiftçi, parsel, sözleşme, üretim, finans ve saha operasyonlarını yönettiği
multi-tenant tarımsal operasyon platformu.

- **Merkezi varlık: Farmer (Çiftçi).** Sprint A2 sonrası ikinci omurga:
  **ProductionCycle (Üretim Sezonu)** — Farmer → Parcel → ProductionCycle → her şey.
- Uzun vadeli hedef: modüler lisanslanabilir, API-first, event-driven,
  on-premise kurulabilir kurumsal platform (bkz. `memory/ROADMAP.md`).

## 2. Teknoloji Yığını (GERÇEK — dokümanlardakiyle karıştırma!)

| Katman | Teknoloji | Not |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** | Tek uygulama, `server.py` ana giriş |
| DB | **MongoDB (Motor async)** | Doküman bazı yerlerde PostgreSQL/PostGIS der — **bizim stack Mongo**, kavramlar Mongo'ya uyarlanır |
| Frontend | **React (CRA) + Tailwind + shadcn/ui benzeri custom CSS** | `frontend/src`, alias `@/` → `src/` |
| Harita | react-leaflet | |
| Grafik | recharts | |
| Auth | JWT (kendi implementasyonu, `security.py`) | |
| Test | `tests/` + `test_reports/` | pytest tabanlı |

Dokümanlarda geçen Redis/RabbitMQ/Elasticsearch/GeoServer **kurulu değildir** —
bu kavramlar soyutlama arkasında Mongo/in-process karşılıklarla geliştirilir
(bkz. ROADMAP "Uyarlama Kararları").

## 3. Dosya Haritası (backend)

| Dosya | Sorumluluk |
|---|---|
| `server.py` (~2300 satır) | App kurulumu, auth, Farmer/Parcel/Region/SoilSample CRUD, dashboard, seed_data; **(IT-15)** `PUT /parcels/bulk-update` (çoklu parsel toplu alan güncelleme — `/parcels/{parcel_id}` PUT'undan ÖNCE tanımlı, yoksa Starlette "bulk-update"i parcel_id sanır); **(IT-16)** `POST /parcels/import-geojson` içindeki `_extract_tkgm_fields` (TKGM Parsel Sorgu GeoJSON özelliklerini il/ilçe/mahalle/ada_no/parsel_no_tapu'ya eşler + "alan" m²→dekar dönüşümü) — frontend'deki `lib/tkgmMapping.js`'in AYNI mantığının backend karşılığı, tek-parsel (GeoFileImport) akışı frontend'de, toplu import akışı burada, iki yerde ELLE senkron tutulmalı |
| `data_entry.py` | Contract, Planting, Machine, Worker, Task, Appointment (logistics), Kantar; **(IT-20)** `KantarRecordCreate`'e opsiyonel `production_cycle_id` eklendi (geriye uyumlu — CLAUDE.md'nin IT-05 notunda öngörülen "ileride sezon bağlamından oluşturulursa elle set edilebilir" anı, entitlement.py'nin tartım/tonaj/kalite girdisi bunu kullanır) |
| `extras.py` | AI copilot + disease detect, satellite NDVI, IoT, drone, e-belge, müstahsil, field visits (hepsi simüle/demo veri); **(IT-17)** NDVI üretimi artık `satellite_provider.py`'den okunur (DRY), yeni `POST /satellite/ndvi-snapshot` — ÇOKLU parsel için TEK bir tarihteki NDVI/risk anlık görüntüsü (Mekânsal Zaman Makinesi) |
| `satellite_provider.py` | **(IT-17) Uydu Görüntü Provider Soyutlaması** — `SatelliteProvider` (ABC) + `DemoSatelliteProvider` (MOCK, parcel_id'ye göre deterministik CRC32 seed'li), `get_satellite_provider()` factory (şimdilik hep demo döner), `ndvi_to_health`/`ndvi_to_risk_level` yardımcıları. Gerçek sağlayıcı (Sentinel-2/Planet) FAZ 9.5 (IT-28.1) kapsamında — o zaman SADECE yeni bir alt sınıf + factory'de seçim eklenir, extras.py DEĞİŞMEZ |
| `forms_module.py` | **M18 Saha Anket Formları** (çiftçiye gönderilen GPS/foto destekli anketler) |
| `field_definitions.py` | **Sprint A1 Dinamik Form Yönetimi + Lookup Yönetimi** (entity alan metadata'sı) — forms_module ile KARIŞTIRMA; **(IT-07) Field-Level Security v1** — `sensitive` bayrağı + `mask_sensitive_fields`/`mask_sensitive_fields_many`/`is_masked_value` (diğer modüller import edip kendi GET/PUT'larında çağırır); **(IT-01.5) Lookup v2** — `lookup_groups.parent_group_id` (çapraz-grup kaskad, örn. ilçe→il), `field_definitions.depends_on_field` (alan-alan kaskad bağımlılığı), `POST /lookups/groups/{id}/values/bulk-import` (kopyala-yapıştır toplu değer girişi, `_slugify_tr` ile) |
| `permissions.py` | RBAC permission katalogu + 8 rol varsayılan setleri |
| `users.py` | Kullanıcı yönetimi, rol atama |
| `tenants.py` + `tenant_context.py` | Multi-tenant izolasyon (ContextVar + TenantScopedDB sarmalayıcı — sorgulara otomatik tenant_id) |
| `integrations.py` | Entegrasyon Merkezi (SMS/Email/Planet/AI config, secret maskeleme, test endpoint'leri, **(IT-01) health-check + timeout/retry alanları**) |
| `audit.py` | Audit log (`log_audit`) |
| `security.py` | JWT, hash |
| `config_service.py` | **(IT-01) Merkezi konfigürasyon** — TÜM env okuma burada: Mongo, JWT, CORS, platform admin, ROLE_HIERARCHY (8 rol), entegrasyon timeout/retry varsayılanları, log secret-maskeleme (`install_secret_masking`); **(IT-07) `get_system_tier(role)`** — 8-rol + platform_admin yapısının üzerine 4 kademeli sınıflandırma (god_mode/super_admin/admin/user) |
| `config.py` | **DEPRECATED shim** — geriye dönük uyumluluk için `config_service.py`'yi re-export eder. Yeni kod `config_service`'ten import etmeli |
| `storage.py` | **(IT-04) Dosya Depolama** — basit yerel disk upload (`backend/uploads/`), `uploads` koleksiyonu (module/entity_id/field_key), field_definitions'ın file/image/multifile alan tiplerinin VE genel "Belgeler" sekmesinin ortak backend'i |
| `production_cycles.py` | **(IT-05) ProductionCycle** — Farmer→Parcel'den sonraki ikinci omurga: yıl/sezon/durum makinesi (planning→active→harvesting→completed/cancelled), CRUD, mevcut contract/planting/soil_samples kayıtlarını geriye dönük bağlayan idempotent migrasyon endpoint'i |
| `query_engine.py` | **(IT-08) Universal Query & Filter Engine çekirdeği** — `POST /query/{module}` (filter DSL + tek seviye AND/OR + sayfalama/sıralama/projection) ve `GET /query/{module}/filterable-fields`; CORE_FILTERABLE_FIELDS (kod-seviyesi) + field_definitions'ta filterable=True (yönetici tarafından genişletilebilir) birleşimini whitelist olarak kullanır, sonuçlara IT-07'nin Field-Level Security maskesini de uygular; **(IT-24)** `field_tasks`/`visits` modülleri eklendi (field_ops.py'nin IT-22 koleksiyonları) — `FIELD_DEFINITIONS_MODULES`'a DAHİL DEĞİL (bu ikisinin field_definitions'ı yok), Saha Raporları ekranı (SahaOperasyonlari.jsx "Raporlar" sekmesi) bunları SmartDataGrid ile tüketir |
| `saved_queries.py` | **(IT-09) Saved Queries / Portföy** — query_engine'in filter DSL'ini adlandırılmış kayıt olarak saklar; özel/paylaşılan (`is_shared`) + favori (`favorited_by`) + sadece sahibi düzenler/siler (admin+ sistem katmanı moderasyon için silebilir) |
| `favorites.py` | **(IT-12) Favoriler** — herhangi bir modüldeki TEK bir kaydı (çiftçi/parsel/...) favorileme, saved_queries'in sorgu favorilerinden AYRI; `GET/POST /favorites`, `DELETE /favorites/{id}`, `DELETE /favorites/by-entity/{module}/{entity_id}` |
| `geo_import.py` | **(IT-13.5) Geo Dosya İçe Aktarma** — SHP(.zip)/GeoJSON/KML/DXF ayrıştırıp WGS84'e çevirir (pyshp/ezdxf/pyproj); `POST /geo-import/parse` SADECE ayrıştırır, HİÇBİR ŞEY KAYDETMEZ (önizleme+onay akışı — kaydetme ayrı bir çağrı, ör. parsel için mevcut `PUT /parcels/{id}`); NCZ parse edilmez (415) |
| `admin_areas.py` | **(IT-13.6) İdari Alanlar** — il/ilçe/mahalle sınır+demografi; `admin_areas` koleksiyonu (2dsphere index); `POST /admin-areas/bulk-import` (geo_import.py çıktısını çok sayıda kayda çevirir); `GET /admin-areas/{id}/summary` GERÇEK `$geoIntersects` ile o alandaki çiftçi/parseli hesaplar (village/region yaklaşıklığı DEĞİL); liste yanıtı geometri sadeleştirir (Layer v1 performansı), detay yanıtı tam hassasiyet döner |
| `map_workspace.py` | **(IT-14) Harita Paneli — Kişisel Çalışma Alanı** — kullanıcı başına TEK kayıt (adlandırma/çoklu görünüm YOK, saved_queries'ten bilinçli farklı): `GET/PUT/DELETE /map-workspaces/me` — `widget_keys`/`map_center`/`map_zoom`/`filters` bu modül için OPAKTIR (hangi widget'lar var bilmez/doğrulamaz, sadece frontend'in gönderdiği listeyi saklar) — yeni bir widget eklemek bu backend modülünü DEĞİŞTİRMEYİ gerektirmez; **(IT-15)** aynı opak mantıkla `basemap_key`/`visible_layers` de eklendi (seçili basemap + açık katman anahtarları) |
| `map_snapshots.py` | **(IT-16) Harita Snapshot** — map_workspace'ten BİLİNÇLİ AYRI: adlandırılmış/ÇOKLU/paylaşılabilir (`is_shared`) harita görünümü kayıtları, saved_queries.py ile AYNI kalıp (sahibi düzenler/siler, admin+ moderasyon için silebilir); `GET/POST /map-snapshots`, `GET /map-snapshots/{id}` (paylaşım linkinden açma — sahibi değilse sadece `is_shared=True` ise erişilebilir), `DELETE /map-snapshots/{id}`; ekran görüntüsü/canvas KULLANMAZ (yeni bağımlılık yok) — "paylaşım" durum paylaşımıdır (`?snapshot=<id>` linki açılınca harita o duruma birebir geri yüklenir) |
| `support.py` | **(IT-18 / FAZ 7 UFYD başlangıcı) Destek Kataloğu + Destek Talep Süreci** — `SupportType` katalog CRUD (soft delete, `is_active`) + idempotent `POST /support-types/seed-defaults` (Mazot/Gübre/Tohum/İlaç/Makine Hizmeti/Sulama/Nakliye/Avans/Diğer); `SupportRequest` 9 durumlu SIRALI durum makinesi (`taslak→gonderildi→inceleniyor→onaylandi→hazirlaniyor→teslim_edildi→ciftci_onayladi→muhasebelesti→tamamlandi`, her adımdan `reddedildi`/`iptal_edildi` dallanabilir, production_cycles.py'deki ALLOWED_TRANSITIONS kalıbıyla AYNI); `ciftci_onayladi` geçişi `confirmation_method` ister — enum'da 5 yöntem var (mobil_onay/qr_kod/dijital_imza/fotograf/gps_konumu) ama BU FAZDA sadece `mobil_onay`/`fotograf` endpoint'çe kabul edilir (diğerleri altyapı, ROADMAP'in "ilk fazda en az bu ikisi zorunlu" notuyla tutarlı); durum değişikliklerinde Comm Hub (IT-25) henüz yok — mevcut hafif `notifications` koleksiyonuna insert edilir (irrigation_events ile AYNI desen). Çiftçi portalı: `GET /portal/production-cycles` (SADECE iptal edilmemiş sezonlar — yeni destek talebi iptal bir sezona bağlanmamalı), `GET /portal/support-types` (aktif tipler, `/support-types`'ın `support:catalog_view` izni ciftci'ye kapalı olduğu için ayrı), `GET/POST /portal/support-requests` — hepsi `/farmer/*` ile AYNI desen (`current_user.role=="ciftci"` + `farmer_id` kontrolü, permission sistemine dahil değil). `permissions.py`'ye yeni `support` modülü (`catalog_view/manage`, `requests_view/manage`) — ilce_yoneticisi/ziraat_muhendisi'ne view+manage, saha_personeli'ne sadece view verildi. **(IT-19 entegrasyonu):** `muhasebelesti` geçişinde `ledger.create_ledger_entry()` doğrudan import edilip çağrılır — bkz. `ledger.py` satırı. |
| `ledger.py` | **(IT-19 / FAZ 7 UFYD devam) Financial Ledger + Cari Hesap** — `ledger_entries` koleksiyonu **IMMUTABLE**: bilinçli olarak `PUT`/`DELETE /ledger/{id}` YOK (405 döner), sadece `POST /ledger` (yeni kayıt) ve `POST /ledger/{id}/reverse` (orijinali BOZMADAN ters işaretli YENİ kayıt ekler, `is_reversal`/`reversed_entry_id` ile referans verir; aynı kayıt iki kez reverse edilmeye çalışılırsa 409). `create_ledger_entry()` — diğer modüllerin (support.py, ileride IT-20) doğrudan import edip çağırdığı tek giriş noktası, whitelist (`ENTRY_TYPES`: destek_talebi/destek_teslimi/avans/cari_hareket/hakedis/mahsup/prim/kesinti/odeme/iade) HER ZAMAN buradan geçer. `GET /production-cycles/{id}/current-account` — `by_type` (entry_type→toplam) + `balance` (tüm kayıtların toplamı) + `entries` listesi döner. **`db.finance` ile KARIŞTIRMA** — Sprint 1-4d'den kalma, farmer_id bazlı (ProductionCycle'a bağlı DEĞİL), sadece seed_data'da statik üretilen, Dashboard/FarmerHome bakiye özetinde salt-okunur kullanılan ESKİ bir demo koleksiyonu; bu iterasyon ona DOKUNMADI (kantar_records'ın IT-05'te bilinçli kapsam dışı bırakılmasıyla AYNI karar). Yeni gerçek UFYD Ledger'ı `db.ledger_entries`'tir. |
| `entitlement.py` | **(IT-20 / FAZ 7 UFYD devam) Hakediş Motoru** — girdiler: tartım/tonaj/kalite `kantar_records`'tan (bu iterasyonla eklenen opsiyonel `production_cycle_id` alanı üzerinden — bkz. `data_entry.py` notu), kota `contracts.kota_ton` toplamından, **birim fiyat bilinçli olarak Contract'a GÖMÜLMEDİ** — calculate/finalize isteğinin bir parametresi (fabrika fiyatı sezon geneli açıklanır, sözleşmeye gömülü olsaydı her güncellemede tüm sözleşmeler elle güncellenirdi). `calculate_gross_entitlement()`/`calculate_entitlement_chain()`/`resolve_definition_amount()` SAF fonksiyonlar (DB/HTTP'den bağımsız, bkz. `tests/test_entitlement.py` — 12 test, hepsi geçiyor). Hesap zinciri ROADMAP'teki sırayla BİREBİR: Brüt Hakediş → Toplam Kesinti (mahsup+kesintiler) → Net Hakediş → (+Primler) → Ödenecek Tutar. `POST /entitlement/calculate` dry-run (hiçbir şey yazmaz); `POST /entitlement/{id}/finalize` idempotent (aynı production_cycle_id için `entitlements` koleksiyonunda kayıt varsa 409) — `hakedis`(+brüt)/`kesinti`(-tutar,her tanım için ayrı)/`prim`(+tutar,her tanım için ayrı) YENİ LedgerEntry'ler yazar. **`mahsup` kaydı BİLİNÇLİ OLARAK 0 TUTARLIDIR** (audit/iz amaçlı) — bu sezonun destek borcu zaten IT-18/19'un otomatik yazdığı `destek_teslimi` negatif kayıtlarında Ledger bakiyesine dahil; ayrıca negatif bir "mahsup" kaydı daha yazmak borcu İKİNCİ KEZ düşüp bakiyeyi bozardı (double-counting) — bu modülün en kritik tasarım kararı, bkz. modül docstring'i. Prim/Kesinti tanımları (`entitlement_definitions`) `calculation_type`: `sabit_tutar`/`yuzde`/`formul` — `formul` HER ZAMAN `override_amount` ister (gerçek formül motoru kapsam dışı, bilinçli sadeleştirme). **Kapsam notu:** ROADMAP'in IT-20 bölümünde IT-18'in aksine ayrı bir "UI:" maddesi YOK — IT-05→IT-06 emsaliyle tutarlı, bu iterasyon BİLİNÇLİ OLARAK sadece backend. |
| `reconciliation.py` | **(IT-21 / FAZ 7 UFYD TAMAMLANDI) İcmal Belgesi + Finansal Simülasyon + UFYD Dashboard** — `entitlement.py`'nin closure DIŞINA taşınan `gather_and_compute_entitlement()`'ı (query_engine.py'nin `execute_query()`'i extras.py'ye açmasıyla AYNI desen, IT-10) DOĞRUDAN import edip override parametreleriyle (tonnage/kota/destek_mahsup) çağırır — sonuç ASLA yazılmaz, yanıt HER ZAMAN `{"simulation": true, ...}` zarfında döner (kabul kriteri: "simülasyon ile gerçek hakediş ayrı response şeması"). İcmal PDF'i `extras.py`'deki `/musthsil/{farmer_id}/{season}` ile AYNI reportlab deseni — Helvetica Türkçe karakter desteklemediği için metin BİLİNÇLİ OLARAK ASCII'ye yakın (müstahsil makbuzuyla tutarlı, yeni font bağımlılığı YOK). `POST /reconciliation/{cycle_id}` idempotent (zaten üretilmişse mevcut kaydı döner, entitlement yoksa 404); `GET /reconciliation/{id}/pdf`+`/approve`+`/object` — sahiplik kontrolü `_check_reconciliation_access()` ile (ciftci rolü SADECE kendi farmer_id'si, staff `reconciliation:view`/`manage` permission'ı ile) — cross-farmer erişim denemesi gerçek tarayıcıda 403 ile doğrulandı. İtiraz (`objection_reason`) IT-28'in Case modeline bağlanana kadar basit bir alan (ROADMAP notuyla tutarlı bilinçli sadeleştirme). `GET /ufyd/dashboard` Ledger/SupportRequest/Entitlement'tan CANLI hesaplanır — `cash_need` v1'de bilinçli olarak `pending_payments` ile AYNI (henüz ayrı bir ödeme-takip mekanizması yok). |
| `field_ops.py` | **(IT-22 / FAZ 8 Saha Operasyonları başlangıcı) İş Emri / Görev / Ziyaret Üçlü Modeli** — BİLİNÇLİ OLARAK YENİ/AYRI koleksiyonlar (`work_orders`/`field_tasks`/`visits`) — Sprint 4'ten kalma `db.tasks` (data_entry.py'deki basit Operasyon Görevi: düz `task_type` metni, 4 durum, work order/checklist/visit YOK, Operasyon.jsx+Hızlı İşlemler+Harita "+ Görev" kullanıyor) ile KARIŞTIRILMAZ/BİRLEŞTİRİLMEZ (ROADMAP'in "aynı tabloya sıkıştırılmamalı" ilkesi). `task_types` kataloğu (idempotent 12 varsayılan seed) — `default_checklist` her yeni FieldTask'a KOPYALANIR (task'ın kendi checklist'i sonradan bağımsız değişir). 11 durumlu SIRALI `TASK_ALLOWED_TRANSITIONS` (production_cycles.py/support.py'deki ALLOWED_TRANSITIONS kalıbıyla AYNI) — `reddedildi`'den `planlandi`'ye YENİDEN PLANLAMA dalı özel olarak eklendi (roadmap'te tek yönlü örnekler farklı, burada "atandi"dan hem kabul_edildi hem reddedildi'ye dallanabiliyor). **KRİTİK KURAL:** `kapandi` geçişi checklist'teki TÜM kalemler `done=true` DEĞİLSE 400 döner (kabul kriteri). Sahiplik modeli — `_check_task_access()`: görevi ÜSTLENEN kullanıcı (`assigned_to`) kendi görevini (transition/checklist/visit) `field_ops:manage` OLMADAN yönetebilir (reconciliation.py'nin `_check_reconciliation_access()` ile AYNI desen); başkasının görevine dokunmak `field_ops:manage` ister — gerçek backend'de saha_personeli kendi görevini yönetip BAŞKASININ görevinde 403 aldı, doğrulandı. `POST /work-orders` parcel_ids × assigned_users round-robin dağıtımıyla TOPLU FieldTask üretir (her task TaskType'ın default_checklist'ini miras alır). Visit 1:N (bir task için birden fazla ziyaret) gerçek veriyle doğrulandı. **Kapsam notu:** ROADMAP'in IT-22 bölümünde ayrı bir "UI:" maddesi YOK ve IT-23 zaten bu modelin Kanban/Takvim/Harita UI'ını kapsıyor — bu iterasyon BİLİNÇLİ OLARAK sadece backend (IT-05→IT-06, IT-20 emsalleriyle tutarlı). **(IT-23 eklemeleri):** `GET /field-ops/assignable-users` (personel seçim listesi — `settings:users_view` İSTEMEZ, field_ops:manage sahibi bir ziraat_muhendisi kullanıcı yönetimi izni olmadan da saha personelini görüp atayabilmeli, bilinçli bir izin-kapsamı ayrımı); `create_visit` artık `farmer_id`/`parcel_id`/`production_cycle_id`/`task_type_id`'yi task'tan DENORMALİZE ediyor (Ziyaret Geçmişi sekmesinin join'süz filtrelenebilmesi için) ve `GET /visits` bu üç alanı da filtre olarak kabul ediyor. |

**Frontend sayfaları:** Dashboard, GlobalSearch (IT-10 — tek kutu arama, route
`/arama`), Farmers, FarmerDetail, FarmerHome (çiftçi portalı),
Parcels, ParcelDetail, ProductionCycleDetail (IT-06 — "Üretim Sezonu" çalışma
ekranı, route `/uretim-sezonlari/:id`), Toprak, Sulama, Verimlilik, Operasyon,
Forms (M18), FormYonetimi (A1), UserManagement, PlatformAdmin (tenant yönetimi),
Extras, Other, Login.
Ortak bileşenler: `components/Layout.jsx` (menü), `components/QuickAdd.jsx`
(A1 dinamik alan render + IT-02/03 `extraModule` desteği), `components/
DynamicFieldsSection.jsx` (A1 dinamik alan render + IT-04 file/image/
multifile widget), `components/DocumentsTab.jsx` (IT-04 genel "Belgeler"
sekmesi), `components/FilterPanel.jsx` (IT-09 — Query Engine üzerine
genel filtre paneli + Kayıtlı Sorgular/Favoriler, herhangi bir liste
ekranına `<FilterPanel module="..." onResults={...} />` ile eklenir,
şu an Farmers.jsx'te "Gelişmiş Filtre" olarak kullanımda),
`components/SmartDataGrid.jsx` (IT-11 — Query Engine'e bağlı genel veri
tablosu: kolon göster/gizle/sırala/sabitle, kolon bazlı hızlı filtre,
çoklu sıralama, sayfalama, CSV export, satır çoklu seçim; `<SmartDataGrid
module="..." columns={[...]} />`, şu an Toprak.jsx'te "Tüm Analizler"
olarak kullanımda), `components/Drawer.jsx` (IT-12 — genel sağdan kayan
yan panel altyapısı, backdrop/ESC ile kapanır), `components/Breadcrumb.jsx`
(IT-12 — genel breadcrumb, FarmerDetail/ParcelDetail'de kullanımda),
`components/FavoriteButton.jsx` (IT-12 — entity favorileme yıldızı,
backend/favorites.py'ye bağlı), `components/WorkspaceDrawer.jsx`
(IT-12 — Drawer.jsx üzerine kurulu, sidebar'daki zil ikonundan açılan
TEK panel: Bildirimler/Son Açılanlar/Favoriler 3 sekmesi, Layout.jsx'e
`<WorkspaceDrawer />` ile bağlı). `lib/recentlyViewed.js` (IT-12 —
"Son Açılanlar" için localStorage tabanlı, cihazlar arası senkronsuz
kayıt — mevcut token deseniyle tutarlı) ve `lib/moduleRoutes.js`
(IT-10/12 ortak — modül+kayıt → detay sayfası rotası eşlemesi,
GlobalSearch.jsx ve WorkspaceDrawer.jsx paylaşır), `components/
GeoFileImport.jsx` (IT-13.5 — dosya yükle → backend'de ayrıştır →
haritada önizle → onayla; `onConfirm(geometry, tkgmFields)` prop'uyla
asıl kaydetme işini çağıran tarafa bırakır, şu an ParcelDetail.jsx'te
kullanımda; **(IT-16)** seçili feature'ın properties'i `lib/
tkgmMapping.js`'teki `mapTkgmProperties` ile TKGM Parsel Sorgu tarzı
il/ilçe/mahalle/ada/parsel için taranır, algılanırsa önizlemede
gösterilir + "Bu bilgileri de uygula" checkbox'ı (varsayılan işaretli)
ile `onConfirm`'ün ikinci argümanı olarak geçirilir — ikinci argümanı
YOK SAYAN eski çağıranlarda davranış DEĞİŞMEZ).

**Sayfalar (devam):** `AdminAreaManagement.jsx` (IT-13.6, route
`/idari-alanlar` — SmartDataGrid liste + QuickAddPanel tekli oluşturma
+ kendi toplu yükleme formu (geo_import.py + admin-areas/bulk-import
zincirlemesi) + Drawer'da detay: sınır önizleme haritası + $geoIntersects
özeti + DynamicFieldsSection demografi + GeoFileImport ile sınır
değiştirme — IT-11/12/13.5'in TÜMÜNÜ yeniden kullanan bir "showcase"
ekranı, yeni bir UI kalıbı icat edilmedi). Parcels.jsx'e "İdari
Sınırlar" katman aç/kapa butonu eklendi (Layer v1 — kesikli çizgi,
dolgu yok, parsel poligonlarından görsel olarak ayrışır).

**Sayfalar (devam):** `HaritaPaneli.jsx` (IT-14, route `/harita-paneli`
— **Widget Kayıt Altyapısı**'nın vitrini, FAZ 6 "Spatial Operations
Center"ın ilk parçası). Asıl teslim widget'ların KENDİSİ değil, `lib/
mapWidgets/` altındaki REGISTRY: her widget bağımsız bir dosyada
`{key, title, icon, accent, compute(ctx)}` sözleşimiyle tanımlanır,
`lib/mapWidgets/index.js` bunları `MAP_WIDGET_REGISTRY` dizisinde
toplar — yeni bir widget eklemek SADECE yeni bir dosya + index.js'e
bir import satırı demektir, harita/sayfa/backend hiçbiri değişmez.
8 referans widget (Toplam Çiftçi, Toplam Parsel, Toplam Ekili Alan,
Boş Parseller, Aktif Üretim Sezonları, Hasat Bekleyen Alanlar, Görev
Bekleyen Parseller, Riskli Parseller) bu registry'nin ilk sakinleri;
NDVI/Su Stresi gibi FAZ 9.5'te gelecek widget'lar `ctx.parcels`'ın
zaten taşıdığı `ndvi_latest`/`risk_level` alanlarını kullanarak AYNI
şekilde eklenecek (bilinçli olarak IT-14 kapsamına ALINMADI).
**(IT-15 eklemeleri, aynı sayfa):** "Katmanlar" paneli (widget picker
ile aynı desende — Parseller/İdari Sınırlar aç-kapa; sadece 2 katman
olduğu için widget'lardaki gibi ayrı bir dosya-registry'si KURULMADI,
`LAYER_CATALOG` sabit bir dizi, bilinçli sadelik); "Basemap" seçici
(Koyu/Açık/Sokak/Uydu — hepsi anahtarsız genel XYZ servisleri, Uydu
Esri World Imagery'nin genel ortofoto katmanı, extras.py'deki simüle
NDVI'yle KARIŞTIRILMAMALI); "Şekille Seç" (polygon/rectangle/circle,
`MapDrawTools`'a yeni `mode="select"` — otomatik tetiklemez, üç aracı
da L.Control.Draw toolbar'ında sunar, kullanıcı seçer); çizilen şeklin
içindeki parseller `turf.booleanPointInPolygon` ile (daire için
`layer.getLatLng()/getRadius()`'tan kurulan `turf.circle`) o anki
**`filteredParcels`** (mapBounds ∩ Gelişmiş Filtre, SEÇİMDEN bağımsız
— `scopedParcels`'ten ayrıştırıldı) havuzundan otomatik seçilir; seçili
parsel varken "Çoklu Parsel Toplu İşlemleri" kartı belirir: "Toplu Alan
Güncelle" (yeni `PUT /parcels/bulk-update`, sulama/toprak tipi/risk
seviyesi) ve "Toplu Görev Oluştur" (yeni endpoint YOK, mevcut `POST
/operations/tasks`'ı seçili her parsel için tekrarlar).
**(IT-16 eklemeleri, aynı sayfa):** parsel popup'ı "hızlı işlem merkezi"ne
dönüştürüldü — çiftçi adı (`farmersById`), toprak/sulama/risk, en güncel
üretim sezonu (`latestCycleByParcel`) gösterilir; üç hızlı işlem: "Detaya
Git" (parsel detayına navigasyon, `lib/moduleRoutes.js`'teki
`moduleDetailPath` ile), "Yol Tarifi" (`lib/directions.js` —
anahtarsız Google Maps yön linki, parselin centroid'ine), "+ Görev"
(popup içinde AÇILAN mini form — bulk task panelinin TEKLİ karşılığı,
aynı `POST /operations/tasks`'ı çağırır). **Harita Snapshot** — "Anlık
Görüntü" panelinde adlandırıp (+ opsiyonel "Tenant içinde paylaş")
kaydeder (`POST /map-snapshots`), kayıtlı görünümler listesinde
Aç/Kopyala/Sil; "Aç" VEYA kopyalanan link (`?snapshot=<id>`) sayfayı
TAM YENİDEN yükler (`window.location.href`) — bilinçli: `initialView`
react-leaflet'te SADECE ilk mount'ta okunur (bkz. aşağıdaki gotcha),
mevcut sayfadaki state'i değiştirmek haritayı otomatik kaydırmaz, bu
yüzden state-güncelleme yerine URL parametresiyle TAM sayfa yenileme
tercih edildi — ilk yükleme effect'i `?snapshot=` parametresini görüp
kişisel çalışma alanının ÜZERİNE yazar (snapshot fetch'i `setLoading
(false)`'DAN ÖNCE await edilir, aksi halde MapContainer yanlış merkez/
zoom ile mount olurdu).
**(IT-17 eklemeleri, aynı sayfa — FAZ 6'nın son parçası):** "Zaman
Makinesi" aç/kapa düğmesi — açılınca toolbar altında SÜREKLİ GÖRÜNÜR bir
slider çubuğu belirir (Katmanlar/Basemap/Anlık Görüntü'nün aksine bir
dropdown DEĞİL, bilinçli — "tek time-slider" ifadesi kalıcı bir kontrol
gerektiriyordu). Slider `backend/satellite_provider.py`'nin ürettiği 10
SABİT tarihi (Mayıs-Eylül 2025, ayda 1/15'i) gezer; Oynat/Duraklat
düğmesi 1.5s'de bir otomatik ilerletir (loop). Slider her değiştiğinde
`POST /satellite/ndvi-snapshot` ile o tarihteki NDVI/risk anlık
görüntüsü çekilir ve YENİ bir `timeAdjustedParcels` katmanı (parcelsWith
Centroid → timeAdjustedParcels → filteredParcels/scopedParcels zincirinin
BAŞINA eklendi) parsellerin `ndvi_latest`/`risk_level`/`risk_label`'ını
GEÇİCİ OLARAK (DB'yi etkilemeden, sadece render/widget hesaplamasında)
o tarihe göre günceller — harita renkleri VE tüm widget'lar (ör. Riskli
Parseller) otomatik olarak "o günkü" değerleri yansıtır, TEK widget
dosyasında değişiklik gerekmedi. "Sezon senkron": Zaman Makinesi
açıkken `ctx.productionCycles` `year===2025`'e süzülür (demo uydu
verisinin ait olduğu tek yıl). **AI Harita Asistanı** — yeni bir AI
entegrasyonu DEĞİL, mevcut `/ai/copilot`'u (IT-10) çağırır; dönen
`parcels` listesinin id'leri `setSelectedIds`'e verilir ("Şekille
Seç"in coğrafi değil doğal-dil sürümü) — AI servisi yapılandırılmamışsa
extras.py'nin anahtar-kelime fallback'i sessizce devreye girer, panel
bunu `ai_powered:false` ile kullanıcıya bildirir.
`components/WidgetCard.jsx` — widget-agnostik render bileşeni
(`widget.compute(ctx)` çağırıp sonucu Dashboard.jsx'in KPI kartıyla
aynı görsel dilde basar, `compute` hata verirse try/catch ile "—"
gösterip TÜM paneli çökertmez). **Harita↔dashboard senkron:** sayfa
`parcels`/`production_cycles`/`operations/tasks`/`farmers`'ı TEK
seferde yükler (Parcels.jsx'teki "hepsini çek, client-side filtrele"
kalıbıyla tutarlı — yeni bir bbox sorgu endpoint'i icat edilmedi);
görünen parsel kümesi ("scoped") üç boyutun KESİŞİMİ: harita sınırları
(moveend/zoomend + turf.centroid + Leaflet `bounds.contains`) ∩ (varsa)
`FilterPanel` (IT-09, module="parcels") sonucu ∩ (varsa, ÖNCELİKLİ)
haritada tıklanarak seçilen parseller — seçim varsa bounds/filtre
görmezden gelinir. Harita da (widget'larla TUTARLI olsun diye) tüm
`parcels` yerine bu SCOPED kümeyi çizer. Kişisel çalışma alanı
(`map_workspace.py`) widget seçimini + harita merkez/zoom'unu
kaydeder/sıfırlar (aktif filtre SPESİFİK OLARAK kaydedilmez — bilinçli
kapsam daraltması, FilterPanel'in kendi filtre state'ini dışa
sızdırmaması gerekiyordu, bkz. Bilinen Tuzaklar). **ÖNEMLİ (react-leaflet
gotcha):** `useMapEvents(handlers)` (node_modules/react-leaflet/lib/
hooks.js) verdiğiniz handlers nesnesini `useEffect(...,[map,handlers])`
bağımlılığında tutar — `handlers` her render'da YENİ bir obje/fonksiyon
ise (örn. bileşen gövdesinde satır-içi tanımlanırsa) sürekli off/on
ile yeniden bağlanır; `MapSync` bileşeni bunu `useRef` ile TEK SEFER
oluşturulan sabit bir handlers nesnesi + en güncel callback'i okuyan
bir `onChangeRef` ile çözüyor — FAZ 6'nın kalanında (IT-15/16/17) harita
etkileşimi eklerken bu kalıp tekrar kullanılmalı.

**Sayfalar (devam — IT-18, FAZ 7 UFYD başlangıcı):** yeni `pages/
SupportCatalog.jsx` (`DestekKatalogu` export, route `/destek-katalogu`,
Layout.jsx SİSTEM grubunda "Ayarlar"ın hemen üstünde, `adminTierOnly`)
— `KullaniciYonetimi`/`OzelRoller` ile AYNI basit liste+QuickAddPanel
kalıbı, "Varsayılanları Yükle" butonu sadece katalog boşken görünür
(`POST /support-types/seed-defaults`). `ProductionCycleDetail.jsx`'e
Sözleşmeler/Ekim/Toprak ile AYNI desende bir "Destek Talepleri" kartı
eklendi — `QuickAddPanel` ile yeni talep (farmer_id/production_cycle_id
otomatik, cycle'dan miras — context-driven navigation, Sprint 6
prensibi), her satırda o anki duruma göre izin verilen sonraki durum
butonları (client-side `SUPPORT_ALLOWED_NEXT`, backend `ALLOWED_
TRANSITIONS` ile birebir — `ProductionCycleDetail`'in kendi `ALLOWED_
NEXT` desteğiyle AYNI), `teslim_edildi` durumundayken bir "Mobil Onay/
Fotoğraf" seçici belirir (sadece bu ikisi — backend'in enforce ettiği
küme). `FarmerHome.jsx`'e "Destek Talebi" hızlı aksiyonu + modal form
(üretim sezonu + destek tipi seçimi `/portal/production-cycles` ve
`/portal/support-types`'tan gelir) + "Destek Taleplerim" listesi
(diğer "Son Kayıtlar" kartlarıyla AYNI görsel dil) eklendi.

**Sayfalar (devam — IT-19, FAZ 7 UFYD devam):** `ProductionCycleDetail.jsx`'e
"Destek Talepleri" kartının ALTINA bir "Cari Hesap" kartı eklendi —
üstte bakiye (`account.balance`, pozitifse yeşil/negatifse kırmızı) +
`entry_type` bazlı özet rozetleri (`account.by_type`), `QuickAddPanel`
ile serbest hareket ekleme ("Yeni Hareket Ekle" — `entry_type` seçimi
`ledger.py`'nin `ENTRY_TYPE_LABELS`'ından türetilir), altında tam hareket
listesi (tarih/tip/tutar/açıklama/kaynak) + her satırda "Ters Kayıt"
butonu (`POST /ledger/{id}/reverse`, `window.prompt` ile opsiyonel sebep
sorar — DİKKAT: bazı otomasyon/headless tarayıcı ortamlarında native
`window.prompt` sessizce iptal/no-op olabilir, gerçek kullanıcı
tarayıcısında sorun değil, sadece otomatik test senaryolarında
`window.prompt` override edilerek doğrulanmalı). Destek Talepleri
kartındaki durum-geçiş fonksiyonu (`transitionSupportRequest`) artık
geçiş sonrası `loadAccount()`'u da çağırıyor — "muhasebelesti" geçişi
otomatik bir Ledger kaydı açabileceği için Cari Hesap kartı ayrıca
yenilenmeden eski bakiyeyi göstermiş olurdu.

**Sayfalar (devam — IT-21, FAZ 7 UFYD TAMAMLANDI):** `ProductionCycleDetail.jsx`'e
Cari Hesap'ın ALTINA bir "İcmal Belgesi" kartı eklendi — üç durum: (1)
entitlement yok → sadece bilgi mesajı (finalize UI'dan yapılamıyor,
IT-20 bilinçli olarak backend-only bırakılmıştı, bkz. o notlar), (2)
entitlement var ama reconciliation yok → "İcmal Belgesi Oluştur" butonu
(`POST /reconciliation/{cycle_id}`), (3) reconciliation var → durum
rozeti (Beklemede/Onaylandı/İtiraz Edildi) + "PDF Görüntüle" (axios
`responseType:"blob"` ile — `?token=` query fallback'i storage.py'de
VAR ama bu yeni endpoint onu KULLANMIYOR, `Depends(current_user)`
standart header-only auth, bu yüzden `window.open` ile DEĞİL blob
fetch ile açılıyor). Yeni `pages/UfydDashboard.jsx` (route `/ufyd-
dashboard`, Layout.jsx "BELGE & FİNANS" grubu) — Dashboard.jsx'teki
`KPI` bileşeninin AYNI görsel dilinde kendi kopyası (ayrı dosya,
paylaşılan bir bileşene çıkarılmadı — bilinçli, iki KPI grid'i
farklı büyüklükte/farklı sayıda kart gösteriyor). `FarmerHome.jsx`'e
"İcmal Belgelerim" listesi (durum rozeti + PDF Görüntüle + sadece
`beklemede` durumundayken Onayla/İtiraz Et butonları — PDF görüntüleme
`downloadMustahsil`'in AYNI fetch+blob+Authorization-header desenini
kullanıyor, `window.open(blobUrl)` ile yeni sekmede açılıyor, indirme
ZORLANMIYOR — müstahsil makbuzundan BİLİNÇLİ FARK, o indirir bu
görüntüler). **ÖNEMLİ (bu oturumda gözlemlendi):** `preview_click`
bazı butonlarda (özellikle `window.prompt` içermeyen "İcmal Belgesi
Oluştur" gibi düz butonlarda BİLE) tıklamayı DOM'a iletmiyor gibi
görünüyor — API çağrısı hiç tetiklenmiyor; `document.querySelector(...)
.click()` ile DOĞRUDAN DOM click() çağrıldığında sorunsuz çalışıyor.
Gerçek kullanıcı tıklamasında sorun YOK, sadece bu otomasyon ortamının
sentetik click event'i React'in event handler'ına bazen ulaşmıyor —
ileride bu ortamda bir buton testi "çalışmıyor" gibi görünürse ÖNCE
`.click()` ile doğrudan DOM tetiklemesi denenmeli, koda bağlamadan önce.

## 4. Yerleşik Konvansiyonlar (UYULMASI ZORUNLU)

1. **Modül kayıt kalıbı:** her backend modülü
   `register_X_routes(api_router, db, current_user, require_permission, log_audit, ...)`
   fonksiyonu sunar; `server.py` sonunda çağrılır. Yeni modüller de böyle eklenir.
2. **ID'ler:** Mongo `_id` DIŞARI SIZDIRILMAZ; her dokümanda `id = str(uuid4())`.
   Response'larda `{"_id": 0}` projection kullanılır.
3. **Soft delete:** hiçbir kayıt fiziksel silinmez → `is_active: False`.
   Finansal kayıtlar (UFYD) ters kayıt (reverse transaction) ile düzeltilir.
4. **Permission kalıbı:** `"modul:eylem"` (ör. `farmers:view`, `settings:fields_manage`).
   Yeni permission'lar `permissions.py` PERMISSION_CATALOG'a eklenir;
   endpoint'ler `Depends(require_permission("..."))` kullanır.
5. **Tenant:** sorgulara elle tenant_id EKLEME — TenantScopedDB otomatik yapar.
   Tenant-üstü işlemler (platform admin) ham db kullanır.
6. **Audit:** yazma işlemlerinden sonra `log_audit(db, user, action, entity, entity_id, old_value, new_value, request)`.
7. **Tarihler:** ISO string (`datetime.now(timezone.utc).isoformat()`).
8. **Dinamik alanlar:** gerçek, tipli kolonlar olarak Pydantic modele eklenir
   (JSON blob YASAK — Sprint A1 kuralı). `field_definitions` sadece ekran
   davranışını (zorunlu/görünür/sıra/lookup/tab) yönetir.
   **İSTİSNA (IT-04):** `file`/`image`/`multifile` tipleri entity'de KOLON
   OLMAZ — dosyalar ayrı `uploads` koleksiyonunda (module, entity_id,
   field_key) ile ilişkili kayıtlardır (bkz. `storage.py`). Sebep: dosya
   eki doğası gereği ilişkiseldir (1-e-çok + metadata), skaler/JSON-temsil
   edilebilir veri değildir; ayrıca "entity_id" gerektirdiğinden CREATE
   akışında henüz doldurulamaz, sadece kayıt oluştuktan sonra (edit) aktif olur.
9. **Frontend:** mevcut CSS sınıfları (`card`, `btn`, `btn-primary`, `input`,
   `badge-a..d`, `badge-neutral`) ve mevcut sayfa kalıpları yeniden kullanılır.
   Yeni tasarım dili YASAK. `data-testid` eklenir.
10. **Idempotent seed:** her modülün seed endpoint'i tekrar çağrılabilir olmalı
    (`_ensure_*` kalıbı, bkz. field_definitions.py).

## 5. Bilinen Tuzaklar

- `forms_module.py` (saha anketleri) ≠ `field_definitions.py` (entity alan
  metadata). İkisini birleştirme/karıştırma girişimi geçmişte bilinçli reddedildi.
- Doküman metinleri .NET/PostgreSQL varsayabilir → her zaman mevcut
  FastAPI+Mongo kalıbına çevir.
- `pip install` → `--break-system-packages` gerekli (geliştirme ortamında).
- Frontend'te `localStorage` KULLANILMAZ (Claude artifact kuralı değil,
  mevcut kod `api.js` içinde token'ı nasıl tutuyorsa ona uyulur).
- `extras.py`'deki AI/uydu/IoT verileri SİMÜLEDİR — gerçek entegrasyon
  Integration Hub (IT-32) ile provider pattern'e taşınacak.
- `config.py` ≠ `config_service.py` (IT-01 sonrası): `config.py` artık sadece
  geriye dönük uyumluluk shim'i, gerçek kaynak `config_service.py`. Yeni env
  değişkeni eklerken SADECE `config_service.py`'ye eklenir, `os.environ`
  başka hiçbir dosyada doğrudan okunmaz.
- Integration Center'da `/test` (gerçek gönderim, parametreli) ile `/health`
  (parametresiz, yıkıcı olmayan bağlantı kontrolü) birbirinden farklı —
  health endpoint'leri SMS/e-posta GÖNDERMEZ, sadece erişilebilirlik/kimlik
  doğrulama kontrolü yapar.
- **İki ayrı SoilSample create modeli var:** `server.py` içindeki
  `SoilSampleCreate` SADECE çiftçi self-servisi (`POST /farmer/soil-sample`)
  içindir; admin/mühendis girişi `data_entry.py` içindeki
  `SoilSampleAdminCreate` (`POST /soil-samples`) kullanır. IT-02'nin toprak
  alanları (tekstür/derinlik/Zn-Fe-B/AI vb.) SADECE `SoilSampleAdminCreate`'e
  eklendi — çiftçi self-servis formuna bilinçli olarak eklenmedi (çiftçi
  bu düzeyde teknik veri girmez, admin/mühendis girer).
- `QuickAddPanel` (`components/QuickAdd.jsx`) artık opsiyonel `extraModule`
  prop'u kabul eder — verilirse kendi içinde `DynamicFieldsSection` render
  eder ve doldurulan alanları `onSubmit`'e düz obje olarak birleştirir
  (bkz. Parcels.jsx/Toprak.jsx/Other.jsx kullanımı, IT-02/IT-03). Prop
  verilmezse davranış tamamen eskisi gibidir.
- **İl/İlçe lookup verisi** `field_definitions.py` içinde `seed_il_ilce_lookup`
  fonksiyonunun içindeki `TR_IL_ILCE` sözlüğünde tutulur (fonksiyon-lokal,
  modül seviyesinde DEĞİL). Yeni il/ilçe eklemek için bu sözlüğe satır
  eklenip `POST /field-definitions/seed-il-ilce-lookup` tekrar çağrılır
  (idempotent). Şimdilik sadece Konya ve Ankara dolu.
- **Dosya indirme endpoint'i (`GET /uploads/file/{module}/{stored_name}`)
  Authorization header YERİNE `?token=` query param'ı da kabul eder** (IT-04)
  — `<img src>`/`<a href>` gibi tarayıcı navigasyonları özel header
  gönderemez. Frontend bu URL'leri HER ZAMAN `?token=${localStorage.getItem
  ("token")}` ekleyerek kurar (bkz. `DynamicFieldsSection.jsx`'teki
  `FileFieldWidget` ve `DocumentsTab.jsx`'teki `fileUrl()`). Bu endpoint
  tenant/permission kontrolü YAPMAZ, sadece JWT imza/süre doğrular — dosya
  adı tahmin edilemez UUID olduğu için "basit dosya/resim upload" kapsamında
  bilinçli bir sadeleştirme (bkz. `storage.py` docstring'i).
- `update_farmer`/`update_parcel` (server.py) artık `is_admin()` yerine
  `require_permission("farmers:edit"/"parcels:edit")` kullanıyor (IT-04) —
  bu permission key'leri zaten `PERMISSION_CATALOG`'ta tanımlıydı ama hiç
  bağlanmamıştı. `update_farmer`'a ayrıca eksik olan `log_audit(...)` çağrısı
  eklendi (convention #6 zaten zorunlu kılıyordu, IT-04'e kadar unutulmuştu).
- **`kantar_records` ProductionCycle'a BAĞLANMAZ** (IT-05 migrasyon kapsamı
  dışı, bilinçli) — bu koleksiyon `farmer_id` bazlıdır, `parcel_id` taşımaz;
  bir çiftçinin aynı yılda birden fazla parseli/sezonu olabileceğinden hangi
  ProductionCycle'a ait olduğu kayıttan çıkarılamaz. Yanlış eşleştirme
  yapmaktansa hiç yapılmadı. `production_cycle_id` alanı ileride kantar
  kaydı bir sezon bağlamından (UI'dan) oluşturulursa elle set edilebilir.
- **ProductionCycle durum makinesi TEK YÖNLÜ** (planning→active→harvesting→
  completed) + her aşamadan `cancelled`'a geçiş serbest; `completed`/
  `cancelled` terminal — bunlardan hiçbir yere geçilemez (yanlış bir sezonu
  düzeltmek gerekirse yeni kayıt açılır, terminal durum elle değiştirilmez).
- **field_definitions tenant'a bağlıdır — bir tenant reseed/force-reset
  edilirse (bkz. eski "dummy veri kayboldu" olayı) o tenant'ın TÜM
  field_definitions/lookup_groups/lookup_values kayıtları da silinmiş olur**,
  DynamicFieldsSection sessizce boş döner (hata vermez, sadece "ek alanlar"
  görünmez olur). IT-07 sırasında keşfedildi: farmers/parcels/contracts/
  plantings/soil'in TAMAMI silinmişti, sadece `seed-*-pilot` + `seed-il-
  ilce-lookup` uçlarını (hepsi idempotent) tekrar çağırarak onarıldı. Böyle
  bir reseed sonrası bu 6 seed endpoint'ini tekrar çağırmak rutin olmalı.
- **(IT-07) Sistem Rolleri Katmanı** — `config_service.get_system_tier(role)`
  mevcut 8-rol + `platform_admin`'i god_mode/super_admin/admin/user olmak
  üzere 4 kademeye indirger (`admin` = mevcut `ADMIN_TIER_ROLES` kümesi,
  yani `ilce_yoneticisi` ve altı "user" sayılır). Rol hiyerarşisini/
  permission sistemini DEĞİŞTİRMEZ, sadece çapraz-kesen kararlar
  (Field-Level Security eşiği gibi) için ek bir sınıflandırmadır.
  `GET /permissions/me` artık `system_tier` alanı da döner.
- **(IT-07) Field-Level Security v1** — field_definitions'a `sensitive: bool`
  eklendi. `mask_sensitive_fields(db, module, doc, user)` / `_many` (aynı
  dosyada) system_tier "admin" ve üzeri OLMAYAN kullanıcılar için o modülün
  sensitive=True alanlarını `"•••• MASKELİ ••••"` ile değiştirir — DB'deki
  gerçek değer ETKİLENMEZ, sadece response serileştirme. Örnek: Farmer.iban
  (`seed-farmers-pilot`te `sensitive: True, visible: False` ile kaydedildi
  — `visible: False` BİLİNÇLİ: IBAN zaten FarmerDetail'in "Temel Bilgiler"
  bölümünde elle yazılmış ayrı bir input, field_definitions'a visible=True
  ile eklemek DynamicFieldsSection'da MÜKERRER alan yaratırdı; bu satırın
  tek amacı sensitive bayrağını kaydetmek). Edit formu prefill'i maskeli
  değeri gösterdiği için, kullanıcı değiştirmeden kaydederse gerçek veri
  ezilmesin diye `update_farmer` artık `is_masked_value(v)` ile eşleşen
  alanları güncellemeden ATLAR (şifre alanlarındaki "değişmedi" sentinel'i
  ile aynı desen). Yeni bir alanı hassas işaretlemek için: Form Yönetimi
  UI'daki "Hassas" checkbox'ı VEYA field_definitions PUT'unda
  `sensitive: true` — DynamicFieldsSection kullanan modüllerde otomatik
  çalışır, iban gibi ÖZEL (dynamic olmayan, elle yazılmış) alanlarda ilgili
  GET/PUT endpoint'ine `mask_sensitive_fields`/`is_masked_value` elle
  bağlanmalı (bkz. server.py `list_farmers`/`get_farmer_360`/`update_farmer`).
- **(IT-10) `POST /ai/copilot` artık `parcels:view` izni istiyor** — IT-10
  öncesi bu endpoint sadece `current_user` (giriş yapmış olmak) yeterliydi,
  çünkü elle kurduğu Mongo sorgusu hiçbir izin kontrolünden geçmiyordu.
  Query Engine'e (`execute_query`) bağlandıktan sonra bu kontrol otomatik
  geldi. Kantar/toprak personeli gibi `parcels:view`'i olmayan roller artık
  copilot'u kullanamaz — bilinçli, davranış değişikliği ama güvenlik açığı
  kapatan bir yan etki, geri alınmadı.
- **(IT-13.5) requirements.txt'e pyshp/ezdxf/pyproj eklendi** — kullanıcıdan
  onay alınarak (Karar Protokolü: yeni bağımlılık her zaman sorulur).
  `geo_import.py` DIŞINDA hiçbir modül bu kütüphaneleri kullanmamalı —
  GIS dosya ayrıştırma tek bir modülde toplanmış durumda.
- **(IT-11 sırasında keşfedildi) `uvicorn --reload`'ın WatchFiles reloader'ı
  Windows'ta bazen eski çalışan (worker) süreci öldüremiyor** —
  `OSError: [WinError 233] Borunun diğer ucunda işlem yok` ile reloader
  çöküyor ama ESKİ worker süreci portu (8001) elinde tutmaya devam ediyor
  ve YENİ kod hiç yüklenmeden eski koda göre yanıt vermeye devam ediyor
  (sessizce — hata vermez, sadece değişiklikler etkisiz kalır). Belirti:
  bir endpoint'i değiştirip test ettiğinizde "çalışmıyor" gibi görünen ama
  aslında kodu doğru olan bir davranış. **Çözüm:** `netstat -ano | grep
  :8001` ile portu tutan PID'i bulmak YETMEZ (reloader'ın PID'ini
  gösterebilir) — `tasklist | grep python` ile TÜM python.exe süreçlerini
  listeleyip HEPSİNİ `taskkill //F //PID <pid>` ile öldürüp öyle yeniden
  başlatmak gerekir. Şüpheli bir test sonucunda önce bunu kontrol edin.
- **(IT-14 sırasında "her sayfada ~450x Maximum update depth exceeded"
  şüphesiyle raporlanmıştı — ayrı bir oturumda ARAŞTIRILDI VE KOD HATASI
  OLMADIĞI DOĞRULANDI, kapatıldı.)** Bulgu: hata React kodunda DEĞİL,
  o oturumun `craco start` dev server sürecinin (aynı process, IT-14
  boyunca react-leaflet/Leaflet map instance'larının defalarca mount/
  unmount edildiği onlarca Fast Refresh döngüsünden geçmişti) BİRİKMİŞ
  HMR durumunda oturuyordu. Doğrulama: `index.js`'e geçici bir
  `console.error` monkey-patch'i eklenip tam argümanlar yakalandı; PATCH
  İLE bile hata 0 kez tetiklendi. Kuşkuyu netleştirmek için dev server
  tamamen durdurulup (`preview_stop` + `preview_start`, yani sıfırdan
  `yarn start`) TAMAMEN TEMİZ bir süreçle Dashboard ("/"), Çiftçiler
  ("/ciftciler") ve Harita Paneli ("/harita-paneli") sayfaları arka
  arkaya birçok kez hard-reload edildi — HİÇBİRİNDE hata reprodüklenmedi
  (`preview_console_logs level:error` → "No console logs."). **Sonuç:**
  gerçek bir React memoization bug'ı YOK; "~450 kez" rakamı o oturuma
  özgü, HMR birikimine bağlı bir seferliktik semptomdu. **Ders:** bu
  projede uzun bir HMR oturumundan (özellikle react-leaflet sayfalarında
  çok sayıda hot-reload'dan) sonra şüpheli bir konsol hatası görülürse,
  hatayı koda bağlamadan ÖNCE dev server'ı temiz yeniden başlatıp
  tekrarlanıp tekrarlanmadığı kontrol edilmeli (bkz. yukarıdaki
  `uvicorn --reload` stale-worker maddesiyle aynı aile — Windows'ta hem
  backend hem frontend dev server'ları uzun oturumlarda "hayalet" durum
  biriktirebiliyor).

- **(IT-15 sırasında keşfedildi) `MapDrawTools.jsx`'in `handleCreated`/
  `handleEdited` olay dinleyicileri `onCreated`/`onEdited` prop'larını
  STALE (bayat) closure ile yakalıyordu** — bu component'in ana kurulum
  `useEffect`'i SADECE `[map]`'e bağımlı (bilinçli, kontrolü her render'da
  yeniden kurmamak için), ama `map.on(L.Draw.Event.CREATED, handleCreated)`
  içindeki `handleCreated` İLK render'daki `onCreated` parametresine
  kilitleniyordu — çağıran taraf (HaritaPaneli) her render'da callback'i
  tazelese de dinleyici hiç yeniden bağlanmadığı için hep ESKİ closure
  çalışıyordu (MapSync'teki `onChangeRef` bug'ıyla AYNI aile). IT-15'in
  "Şekille Seç" özelliğinde bu, çizilen şeklin içindeki parselleri o anki
  `mapBounds`/filtre durumuna göre DEĞİL, component ilk mount olduğundaki
  (genelde boş/sınırsız) duruma göre seçmesine yol açıyordu — canlı
  tarayıcıda `window.__debugMap` ile bounds-sınırlı beklenen sayı (675)
  yerine sınırsız havuzdan gelen bir sayı (865) görülerek yakalandı.
  Düzeltme: `onCreatedRef`/`onEditedRef` ile MapSync'teki AYNI ref kalıbı
  uygulandı. Bu düzeltme sadece IT-15'in yeni "select" modunu değil,
  Parcels.jsx'in ÖNCEDEN VAR OLAN "polygon"/"edit" çizim akışlarını da
  (aynı component, aynı bug ailesi) etkiler — geriye dönük kırılma YOK,
  davranış sadece artık doğru (güncel) closure'ı kullanıyor.
- **(IT-16) TKGM özellik-eşleme mantığı İKİ YERDE var, bilinçli:**
  `frontend/src/lib/tkgmMapping.js` (`mapTkgmProperties`, GeoFileImport'un
  tek-parsel önizlemesi için) ve `backend/server.py`'deki
  `_extract_tkgm_fields` (toplu `/parcels/import-geojson` için). Aynı
  anahtar (il/ilce/mahalle/ada/parsel) ve alan-dönüşüm mantığını taşırlar
  ama BAĞIMSIZ kod parçalarıdır (biri sadece önizleme için client-side,
  diğeri gerçek kayıt için server-side) — ortak bir modüle çıkarılmadı
  çünkü diller farklı (JS/Python). **TKGM'nin anahtar adları değişirse
  veya yeni bir alan eklenirse HER İKİSİ de elle güncellenmeli.**
- **(IT-16 doğrulaması sırasında yeniden gözlemlendi) "Maximum update
  depth exceeded" hatası HaritaPaneli.jsx'te uzun bir HMR oturumundan
  sonra tekrar ortaya çıktı** (bu oturumda ~15 ardışık düzenleme/hot-
  reload sonrası, `/harita-paneli` → parsel popup'ından "Detaya Git" ile
  ParcelDetail'e geçişte) — IT-14'teki BULGUYLA TUTARLI: dev server'ı
  temiz yeniden başlatınca (`preview_stop`+`preview_start`) AYNI akış
  (harita → popup → Detaya Git → geri) HİÇBİR hata vermeden çalıştı.
  Gerçek bir kod hatası DEĞİL — bu proje türünde (react-leaflet + uzun
  HMR oturumu) tekrar eden bilinen bir dev-server semptomu, koda
  bağlamadan önce HER ZAMAN önce temiz restart ile doğrulanmalı.
- **(IT-17 sırasında keşfedildi) `uvicorn --reload`'ın WatchFiles'ı
  BAZI backend dosyalarındaki değişikliği SESSİZCE hiç yakalamayabiliyor**
  (önceki maddedeki "eski worker öldürülemiyor" senaryosundan FARKLI bir
  semptom — burada reload LOG'U bile hiç basılmıyor). Bu oturumda
  `satellite_provider.py` (yeni dosya) reload'u tetikledi ama AYNI ANDA
  değiştirilen `extras.py` tetiklemedi — yeni eklenen `POST /satellite/
  ndvi-snapshot` bir süre 404 döndü. **Belirti:** yeni bir endpoint/route
  eklediniz, backend log'unda o dosya için "WatchFiles detected changes"
  satırı YOK, istek 404/eski davranış veriyor. **Çözüm:** aynı öneri —
  `preview_stop`+`preview_start` ile backend'i TAM yeniden başlatın,
  sadece "reload oldu mu" log'una güvenmeyin, YENİ eklenen endpoint'i
  gerçekten curl/fetch ile bir kez deneyip 404 almadığınızı doğrulayın.

## 6. Mevcut Durum (tamamlananlar)

- ✅ Sprint 1-4d (önceki çalışma): CRUD modülleri, harita, tenant, RBAC, roller,
  Integration Center v1, audit, M18 formlar, kullanıcı yönetimi
- ✅ **Sprint A1 Faz 1:** `field_definitions.py` altyapı (alan tanımları CRUD +
  reorder + lookup grupları/değerleri hiyerarşili) + FormYonetimi.jsx ekranları +
  permission'lar (`settings:fields_manage`, `settings:lookups_manage`)
- ✅ **Sprint A1 Faz 2 (Çiftçi pilotu):** FarmerCreate/Update'e 19 gerçek alan,
  idempotent seed endpoint'i (`POST /field-definitions/seed-farmers-pilot`),
  `DynamicFieldsSection.jsx` ortak bileşeni, Farmers.jsx entegrasyonu,
  FarmerDetail'e "Genel Bilgiler" sekmesi
- ✅ **IT-01 (FAZ 0 — Platform Temeli, TAMAMLANDI):** `config_service.py`
  eklendi (tüm env okuma tek merkezde: Mongo, JWT, CORS, platform admin,
  roller, entegrasyon timeout/retry varsayılanları); `config.py` geriye
  dönük uyumluluk shim'ine dönüştürüldü; log'larda secret maskeleme
  (`install_secret_masking`, server.py başlangıcında kurulur); Integration
  Center'a per-tip `timeout_seconds`/`retry_count` override, `last_success_at`
  ve aktif health-check endpoint'leri (`GET /integrations/health`,
  `GET /integrations/{type}/health`) eklendi; `.env.example`'a
  `INTEGRATION_TIMEOUT_SECONDS`/`INTEGRATION_RETRY_COUNT` eklendi.
- ✅ **IT-02 (FAZ 1 — Parsel + Toprak alan genişletme):** `ParcelCreate`/
  `ParcelUpdate`'e 16 gerçek alan (Kadastro Bilgileri, Coğrafi Özellikler,
  Sahiplik & Kira, Altyapı sekmeleri); `SoilSampleAdminCreate`'e 11 gerçek
  alan (Fiziksel/Kimyasal Özellikler, Mikro Besin Elementleri, Rapor & AI
  sekmeleri); idempotent seed endpoint'leri (`POST /field-definitions/seed-
  parcels-pilot`, `POST /field-definitions/seed-soil-pilot`); `QuickAddPanel`
  bileşenine `extraModule` desteği eklendi ve Parcels.jsx (manuel + çizim
  panelleri) ile Toprak.jsx'e bağlandı; ParcelDetail.jsx'e salt-okunur
  "Genel Bilgiler" kartı eklendi (FarmerDetail'deki "Genel Bilgiler"
  sekmesiyle aynı kalıp, tab yerine tekil kart olarak — sayfanın mevcut
  düz-kart yapısına uyumlu). SoilSample listeleme tablolarına (Toprak.jsx,
  ParcelDetail.jsx) yeni alanlar için kolon EKLENMEDİ — bilinçli kapsam dışı,
  bkz. IT-02 teslim raporu.
- ✅ **IT-02 eki — İl/İlçe/Mahalle lookup altyapısı:** Parsel'in `il`/`ilce`
  alanları düz text'ten hiyerarşik LOOKUP'a yükseltildi (`ilce.parent_id` ->
  `il`'in lookup_value id'si); yeni `POST /field-definitions/seed-il-ilce-
  lookup` endpoint'i (idempotent, TR_IL_ILCE sözlüğü) — **şimdilik sadece
  Konya (31 ilçe) ve Ankara (25 ilçe) dolu**, kalan iller TR_IL_ILCE
  sözlüğüne eklenip endpoint tekrar çağrılarak genişletilir. Yeni `mahalle`
  alanı (düz text, ulusal veri seti yok) eklendi. `_ensure_lookup_value`
  artık `parent_id`'yi benzersizlik anahtarına dahil ediyor (farklı illerin
  aynı adlı ilçeleri çakışmasın diye) ve id döndürüyor. ~~**Bilinen sınırlama:**
  DynamicFieldsSection'da İl seçilince İlçe listesi filtrelenmiyordu~~ —
  **IT-01.5 ile kapatıldı**, bkz. aşağıdaki IT-01.5 maddesi.
- ✅ **IT-03 (FAZ 1 — Sözleşme + Ekim Planlama alan genişletme):**
  `ContractCreate`/`ContractUpdate`'e 11 gerçek alan (Sözleşme Türü &
  Taraflar, Prim & Kesinti, Fabrika Teslim); `PlantingCreate`/`PlantingUpdate`'e
  10 gerçek alan (Tohum & Ekim Detayı, Takvim, Kaynak Planlama); idempotent
  seed endpoint'leri (`POST /field-definitions/seed-contracts-pilot`,
  `POST /field-definitions/seed-plantings-pilot`, 3 yeni lookup grubu:
  sozlesme_turu, nakliye_sorumlusu, ekim_yontemi); Other.jsx'teki
  Sözleşme ve Ekim `QuickAddPanel`'lerine `extraModule` bağlandı (onSubmit
  zaten `...v` spread ettiği için başka değişiklik gerekmedi). Detay sayfası
  (salt-okunur "Genel Bilgiler" kartı) eklenmedi — Sözleşme/Ekim'in
  ParcelDetail/FarmerDetail gibi ayrı bir detay sayfası yok, sadece liste var.
- ✅ **IT-04 (FAZ 1 TAMAMLANDI — Edit formları + dosya alan tipleri):**
  `storage.py` eklendi (yerel disk upload, `uploads` koleksiyonu, path-
  traversal korumalı indirme endpoint'i, JWT header VEYA `?token=` query
  param ile kimlik doğrulama); `DynamicFieldsSection.jsx`'e `file`/`image`/
  `multifile` için gerçek yükleme widget'ı (`FileFieldWidget`, `entityId`
  prop'una bağlı — create akışında "kayıttan sonra doldurulur" notu, edit
  akışında aktif); yeni `DocumentsTab.jsx` (genel "Belgeler" sekmesi);
  FarmerDetail.jsx ve ParcelDetail.jsx'e gerçek DÜZENLEME modu eklendi
  (temel alanlar + DynamicFieldsSection, tek ekranda) — daha önce HİÇBİR
  entity'nin edit UI'ı yoktu (Parcels.jsx'teki "Düzenle" aracı sadece harita
  geometrisi içindi). `update_farmer`/`update_parcel` artık `is_admin()`
  yerine granüler `farmers:edit`/`parcels:edit` iznini kullanıyor;
  `update_farmer`'a eksik olan audit log çağrısı eklendi. Örnek dosya alanı
  olarak Farmer'a `kimlik_fotokopisi` (image), Parcel'e `tapu_belgesi`
  (file) eklendi. `Farmers.jsx`/`Parcels.jsx` liste sayfaları DOKUNULMADI —
  düzenleme sadece detay sayfalarından yapılıyor (parsel oluşturma sonrası
  otomatik detaya yönlendirme yok, çiftçide var — bilinçli, küçük bir UX
  asimetrisi, kapsam dışı bırakıldı).
- ✅ **IT-05 (FAZ 2 devam ediyor — ProductionCycle backend):** yeni
  `production_cycles.py` modülü — `ProductionCycle` modeli (farmer_id/
  parcel_id/year/season/crop/status/notes), tam CRUD (`GET/POST/PUT
  /production-cycles`, `GET /production-cycles/{id}` — bağlı contract/
  planting/soil_sample kayıtlarını da döner), ayrı bir durum-geçiş
  endpoint'i (`PUT /production-cycles/{id}/status`) ile durum makinesi
  (planning→active→harvesting→completed, her aşamadan cancelled'a geçiş
  serbest, terminal durumlardan çıkış yok — sunucu tarafında doğrulanır).
  `ContractCreate/Update`, `PlantingCreate/Update`, `SoilSampleAdminCreate`'e
  opsiyonel `production_cycle_id` eklendi (geriye uyumlu, eski parcel_id
  korunur). İdempotent migrasyon endpoint'i (`POST /production-cycles/
  migrate-existing`) mevcut contract/planting/soil_samples kayıtlarını
  (parcel_id+yıl eşleşmesiyle) uygun bir ProductionCycle'a bağlar, yoksa
  oluşturur — **gerçek demo veri üzerinde çalıştırılıp doğrulandı** (2000
  sözleşme, 2000 ekim, 400 toprak analizi → 2000 ProductionCycle). `kantar_
  records` bilinçli olarak kapsam dışı (bkz. Bilinen Tuzaklar). Yeni
  `production_cycles` permission modülü (`:view`/`:create`/`:edit`)
  eklendi. **Sadece backend** — UI (Parsel'de "Üretim Sezonları" sekmesi)
  IT-06'nın kapsamı.
- ✅ **IT-06 (FAZ 2 TAMAMLANDI — ProductionCycle UI):** ParcelDetail.jsx'e
  "Üretim Sezonları" kartı eklendi (o parselin tüm cycle'larını listeler,
  durum rozetiyle, tıklanınca detaya gider; "+ Yeni Sezon" ile yıl/sezon/
  ürün formu — farmer_id/parcel_id otomatik dolar). Yeni `ProductionCycle
  Detail.jsx` sayfası (route `/uretim-sezonlari/:id`): sezon özeti + durum
  rozeti + sadece o anki duruma göre izin verilen durum-geçiş butonları
  (client-side ALLOWED_NEXT haritası backend'deki ALLOWED_TRANSITIONS ile
  birebir), altında Sözleşmeler/Ekim Kayıtları/Toprak Analizleri tabloları
  — her birinin kendi `QuickAddPanel`'i var ve **parcel_id/farmer_id/sezon
  formda hiç sorulmaz**, cycle'dan miras alınıp otomatik gönderilir (asıl
  "sezon bağlamında açılma" gereksinimi). Backend'de `GET /production-
  cycles/{id}` artık `farmer`/`parcel` özet nesnelerini de gömüyor (ParcelDetail
  `GET /parcels/{id}` kalıbıyla tutarlı). **Gerçek tarayıcıda uçtan uca
  doğrulandı:** migrasyonla oluşan sezonlar doğru listelendi, yeni sezon
  oluşturuldu, planning→active durum geçişi yapıldı (buton seçenekleri
  doğru güncellendi), sezon bağlamında yeni sözleşme eklendi ve
  `production_cycle_id`/`farmer_id`/`parcel_id`/`season`'ın doğru otomatik
  dolduğu POST body'sinden teyit edildi — konsolda hiç hata yok.
- ✅ **IT-07 (FAZ 3 TAMAMLANDI — Sistem rolleri katmanı + Field-Level
  Security v1):** `config_service.get_system_tier(role)` — 8-rol +
  platform_admin yapısının üzerine god_mode/super_admin/admin/user 4
  kademesi (mevcut `ADMIN_TIER_ROLES` ile aynı sınırı kullanır, rol
  hiyerarşisini değiştirmez); `GET /permissions/me` artık `system_tier`
  döner. `field_definitions.py`'a `sensitive: bool` bayrağı (Form
  Yönetimi UI'da "Hassas" checkbox'ı ile de işaretlenebilir) +
  `mask_sensitive_fields`/`mask_sensitive_fields_many`/`is_masked_value`
  yardımcı fonksiyonları (response serileştirmede maskeler, DB'yi
  değiştirmez). Örnek/ilk uygulama: Farmer.iban `sensitive: True` ile
  seed edildi (`visible: False` — zaten ayrı elle yazılmış bir input
  olduğu için DynamicFieldsSection'da mükerrer render önlendi),
  `list_farmers`/`get_farmer_360` maskeli döner, `update_farmer` maskeli
  placeholder'ı "değişmedi" sayıp gerçek veriyi ezmez. ProductionCycle
  permission'ları (`production_cycles:view/create/edit`) IT-05'te zaten
  eklenmiş ve rol setlerine doğru dağıtılmış olduğu doğrulandı, ek
  değişiklik gerekmedi. **Yan keşif/onarım:** bu tenant'ın TÜM
  field_definitions/lookup verisi (farmers/parcels/contracts/plantings/
  soil) önceki bir reseed'de silinmiş bulundu — 6 idempotent seed
  endpoint'i tekrar çağrılarak onarıldı (bkz. Bilinen Tuzaklar).
  Gerçek tarayıcıda uçtan uca doğrulandı: super_admin/fabrika_muduru
  (admin+) gerçek IBAN'ı görüyor, ziraat_muhendisi (user tier) maskeli
  görüyor, maskeli değerle PUT gönderildiğinde gerçek IBAN değişmiyor,
  Form Yönetimi'nde IBAN satırı "Gizli" + "Hassas" olarak doğru
  görünüyor, FarmerDetail edit formunda tek (mükerrer olmayan) IBAN
  input'u maskeli değeri gösteriyor.
- ✅ **IT-08 (FAZ 4 devam ediyor — Query Engine çekirdeği):** yeni
  `query_engine.py` modülü — `POST /query/{module}` (filter DSL: alan+
  operatör+değer, tek seviye AND/OR; operatörler eq/ne/gt/gte/lt/lte/
  contains/in/between/is_null/is_not_null; server-side sayfalama/
  sıralama/projection) ve `GET /query/{module}/filterable-fields`
  (filtre paneli — IT-09 — için meta). Modüller: farmers/parcels/
  contracts/plantings/soil/production_cycles (production_cycles
  field_definitions'ta yok ama Query Engine'de sorgulanabilir).
  Filtrelenebilir/sıralanabilir/projection alanları İKİ whitelist'in
  birleşimi: CORE_FILTERABLE_FIELDS (kod-seviyesi, modülün Sprint A1
  öncesi temel alanlarından elle seçilmiş alt küme) + field_definitions'a
  eklenen yeni `filterable: bool` bayrağı (Form Yönetimi'nde "Hassas"
  ile aynı desende yeni bir checkbox — `sensitive`'ın kardeşi). Whitelist
  dışı `field`/`sort_by`/`fields` → 400 (keyfi Mongo alan/operatör
  enjeksiyonu engellenir, `$where` gibi bilinmeyen operatörler de 400).
  Sonuçlara IT-07'nin `mask_sensitive_fields_many`'i de uygulanır — bir
  alan hem hassas hem (ileride) filtrelenebilir işaretlense bile ham
  değer sızmaz (projection olmadan tam doküman dönse dahi). Örnek:
  farmers modülünde gender/cks_status/debt_status `filterable: True`
  ile seed edildi. Gerçek backend'de uçtan uca doğrulandı: contains/OR/
  between/sort çalışıyor, iban filtre/projection'da 400 ile reddediliyor,
  `$where` operatörü reddediliyor, ciftci rolü 403 alıyor, non-admin
  sorgusunda iban maskeli dönüyor. **Sadece backend** — filtre paneli UI
  bileşeni + Saved Queries IT-09'un kapsamı.
- ✅ **IT-09 (FAZ 4 devam ediyor — Saved Queries + filtre paneli UI):**
  yeni `saved_queries.py` modülü — `GET/POST /saved-queries`,
  `PUT/DELETE /saved-queries/{id}`, `POST /saved-queries/{id}/favorite`.
  Bir sorgu özel (varsayılan) veya paylaşılan (`is_shared: True`, aynı
  modül izni olan HERKES tenant içinde görür/kullanır) olabilir; sadece
  SAHİBİ düzenler/siler, admin+ sistem katmanı (IT-07 `get_system_tier`)
  moderasyon amacıyla silebilir. Favoriler (Portföy) `favorited_by`
  listesi ile tutulur, `GET /saved-queries?favorites_only=true`.
  Gerçek silme (soft-delete değil — bir görünüm tercihi, finansal/
  tarihsel veri değil). Frontend'e yeni `components/FilterPanel.jsx`
  (genel, yeniden kullanılabilir — `GET /query/{module}/filterable-
  fields`'i okuyup koşul satırları + AND/OR üretir, `POST /query/
  {module}` çalıştırır, kayıtlı sorgu seçimi/kaydetme/favorileme/silme
  UI'ı dahil) eklendi ve Farmers.jsx'e mevcut basit arama/filtrenin
  ALTINA "Gelişmiş Filtre" olarak bağlandı (mevcut `q`/`region`/`karne`
  davranışı DEĞİŞMEDİ, ayrı bir ek katman). Backend uçtan uca curl ile
  doğrulandı: oluştur/listele/favorile/favorites_only/paylaşılan sorgu
  başka kullanıcıya görünüyor ama sadece sahibi düzenleyip silebiliyor
  (non-owner 403), sorgu gerçekten query_engine'e round-trip ediyor.
  **Not:** bu oturumda tarayıcı önizleme (preview_*) araçları
  bağlantısı koptuğu için FilterPanel.jsx'in GERÇEK tarayıcıda
  tıklanarak doğrulanması YAPILAMADI — sadece Babel syntax kontrolü +
  lucide-react ikon varlığı + backend API sözleşmesinin curl ile
  doğrulanması yapıldı. Bir sonraki oturumda tarayıcı erişimi varsa
  Farmers.jsx'te "Gelişmiş Filtre" ucuna gidip gerçek bir filtre
  çalıştırmak, kaydetmek, favorilemek öncelik olmalı.
- ✅ **IT-10 (FAZ 4 TAMAMLANDI — Global arama + AI Copilot köprüsü):**
  `query_engine.py`'nin çekirdeği (`_filterable_map`/`run_query` iç mantığı)
  modül seviyesine `get_filterable_map(db, module)` ve `execute_query(db,
  module, user, filters, ...)` olarak çıkarıldı — `POST /query/{module}`
  artık bu fonksiyonun ince bir sarmalayıcısı, DIŞARIDAN da (extras.py)
  çağrılabiliyor. Yeni `GET /search?q=...&limit=5` (GLOBAL_SEARCH_FIELDS
  ile farmers/parcels/contracts/production_cycles'ta OR+contains taraması,
  kullanıcının izni olmayan modül sessizce atlanır, 2 karakterden kısa
  sorgu boş döner). `extras.py`'deki `/ai/copilot` artık elle Mongo sorgusu
  kurmuyor — `filt_spec`'i query_engine'in filter DSL'ine çevirip
  `execute_query()` çağırıyor; bu YAN ETKİ olarak copilot'a artık
  `parcels:view` izni ZORUNLU oldu (önceden `current_user` yeterliydi,
  ham sorgu hiç izin kontrolü yapmıyordu — bilinçli, güvenlik açısından
  olumlu bir sıkılaştırma, bkz. Bilinen Tuzaklar). `query_engine.py`'nin
  parcels CORE_FILTERABLE_FIELDS'ına `ndvi_latest`/`risk_level`/
  `expected_yield_ton` eklendi (extras.py'nin simüle uydu verisiyle
  eşleşsin diye — ParcelCreate modelinde YOK, doğrudan doküman alanı).
  Frontend'e yeni `GlobalSearch.jsx` sayfası (route `/arama`, sidebar'da
  "ANA" grubunun en üstünde) — sonuçlar modül bazlı gruplanır, tıklanınca
  ilgili detay sayfasına gider (contracts'ın detay sayfası yok, parsel
  sayfasına yönlendirir). Backend uçtan uca curl ile doğrulandı: "Konya
  bölgesinde riskli 5 parsel göster" → doğru region/risk_level/NDVI-artan
  sıralama ile 5 sonuç; `parcels:view`'i olmayan kantar_personeli artık
  copilot'tan 403 alıyor (önceden alamıyordu); global arama "Mehmet"
  sorgusu farmers'ta 10 eşleşme buluyor. **Not:** GlobalSearch.jsx yine
  Babel syntax kontrolü ile doğrulandı, gerçek tarayıcıda tıklanmadı (bkz.
  IT-09'daki aynı not — preview_* araçları bu oturumda kullanılamadı).
- ✅ **IT-11 (FAZ 5 devam ediyor — SmartDataGrid):** `query_engine.py`'ye
  geriye dönük uyumlu çoklu sıralama eklendi (`QueryRequest.sort:
  List[SortSpec]` — verilirse eski tek-alanlı `sort_by`/`sort_dir`'a
  önceliklidir, `execute_query`'nin yeni `sort` parametresi Mongo'nun
  `.sort([(alan,yön), ...])`'una direkt eşlenir). `soil` modülünün
  CORE_FILTERABLE_FIELDS'ına ec/n_ppm/p_ppm/k_ppm/recommendation eklendi
  (SmartDataGrid'in tüm kolonları filtrelenebilir/sıralanabilir olsun
  diye). Yeni `components/SmartDataGrid.jsx` — kolon göster/gizle
  (sürükle-bırak DEĞİL, basit ↑/↓ sıralama butonları — görsel test
  imkânı olmadığı için bilinçli sadeleştirme), sabitleme (kolonu sıraya
  en başa taşır — gerçek CSS sticky-scroll efekti değil, aynı sebeple),
  başlığa tıkla → asc/desc/kapalı döngüsü ile çoklu sıralama (öncelik
  sırası tıklama sırası), kolon başına hızlı filtre satırı (text→contains,
  number/date→eq; FilterPanel'in AND/OR koşul kurucusundan FARKLI, o ayrı
  kalır), sayfalama, satır çoklu seçim, CSV dışa aktarma (mevcut filtre/
  sıralamayla eşleşen ilk 500 kayıt — tam/streaming export v1 kapsamı
  dışı, Excel binary .xlsx değil CSV — yeni bir kütüphane bağımlılığı
  eklememek için bilinçli tercih). Toprak.jsx'teki eski "Son Analizler"
  (samples.slice(0,30) ile sabit kolonlu) tablosu SmartDataGrid'e
  taşındı, artık `key={gridRefreshKey}` ile QuickAddPanel'den yeni kayıt
  eklenince yeniden mount edilip taze veri çekiyor. Backend curl ile
  uçtan uca doğrulandı: çoklu sıralama (karne_score sonra full_name)
  doğru çalışıyor, soil filterable-fields tüm grid kolonlarını dönüyor,
  filtre+sıralama+projection birlikte doğru sonuç veriyor. **Önemli
  keşif:** bu doğrulama sırasında `uvicorn --reload`'ın Windows'ta eski
  worker sürecini öldürememesi hatası bulundu ve giderildi (bkz. Bilinen
  Tuzaklar) — birkaç test turu YANLIŞLIKLA stale kod üzerinde çalıştı,
  süreçler temizlenip yeniden başlatıldıktan sonra hepsi doğrulandı.
  **Not:** SmartDataGrid.jsx yine Babel + backend curl ile doğrulandı,
  gerçek tarayıcıda tıklanmadı (preview_* araçları bu oturumda hiç
  erişilebilir olmadı).
- ✅ **IT-12 (FAZ 5 devam ediyor — Drawer altyapısı + breadcrumb + Son
  Açılanlar + Favoriler + bildirim çekmecesi):** `server.py`'ye bildirim
  okundu uçları eklendi (`PUT /notifications/{id}/read`, `POST
  /notifications/mark-all-read`, `GET /notifications/unread-count`) —
  bildirimler tenant genelidir (kullanıcı bazlı gelen kutusu değil,
  mevcut veri modeliyle tutarlı bir tercih). Yeni `favorites.py` —
  herhangi bir modüldeki tek bir KAYDI favorileme (saved_queries'in
  SORGU favorilerinden ayrı bir sistem), idempotent POST (aynı kayıt
  tekrar favorilenirse mevcut satırı döner, kopya oluşturmaz),
  `DELETE /favorites/by-entity/{module}/{entity_id}` frontend'in
  favorite_id hatırlamasına gerek kalmadan yıldız butonunu basitleştirir.
  Frontend'e `Drawer.jsx` (genel sağdan kayan panel), `Breadcrumb.jsx`
  (genel), `FavoriteButton.jsx`, `WorkspaceDrawer.jsx` (Drawer üzerine
  kurulu TEK panel — 3 sekme: Bildirimler/Son Açılanlar/Favoriler,
  Layout.jsx'in sidebar footer'ına zil ikonu + okunmamış rozeti olarak
  bağlandı), `lib/recentlyViewed.js` (localStorage — "Son Açılanlar",
  cihazlar arası senkron YOK, bilinçli — kritik olmayan bir kolaylık)
  ve `lib/moduleRoutes.js` (GlobalSearch.jsx'in IT-10'da yazdığı modül→
  rota eşlemesi buraya taşınıp WorkspaceDrawer.jsx ile paylaşıldı,
  GlobalSearch.jsx da bunu kullanacak şekilde güncellendi — kod
  tekrarını önledi). FarmerDetail.jsx ve ParcelDetail.jsx'e Breadcrumb +
  FavoriteButton (isim yanında yıldız) + `pushRecentlyViewed()` (sayfa
  yüklenince) bağlandı. Backend curl ile uçtan uca doğrulandı: favori
  ekleme/idempotent tekrar ekleme/entity ile silme, bildirim tek/toplu
  okundu işaretleme + unread-count doğru düşüyor (46→45→0). Frontend
  CANLI webpack derlemesinden (yeniden başlatma değil, gerçek çalışan
  dev server hot-reload) "webpack compiled with 7 warnings" (hata YOK,
  sadece önceden var olan uyarılar) ile doğrulandı — bu, tüm yeni
  dosyaların (Layout.jsx dahil, HER sayfayı etkileyen ortak bileşen)
  gerçekten derlendiğinin güçlü kanıtı. **Not:** yine de gerçek
  tarayıcıda tıklanarak (Drawer açma/kapama, favori ekleme UI'dan,
  vb.) test edilemedi — preview_* araçları bu oturumda hiç
  erişilebilir olmadı.
- ✅ **IT-13 (FAZ 5 TAMAMLANDI — Workspace dönüşümü: context-aware CRUD +
  Quick Actions):** Yeni backend YOK — mevcut `/contracts`, `/operations/
  tasks`, `/production-cycles` uçları (zaten `farmer_id` opsiyonel/
  parselden türetilebilir) frontend'den context ile çağrıldı. FarmerDetail.
  jsx ve ParcelDetail.jsx'e "Hızlı İşlemler" kartı eklendi (mevcut
  `QuickAddPanel` bileşeni yeniden kullanıldı — yeni bir form altyapısı
  icat edilmedi): ParcelDetail'de "Yeni Sözleşme"/"Yeni Görev" (`parcel_id`
  = sayfanın kendi id'si, `farmer_id` = `parcel.farmer_id`, hiçbiri
  formda SORULMAZ); FarmerDetail'de "Yeni Sözleşme"/"Yeni Görev"/"Yeni
  Sezon" (`farmer_id` = sayfanın kendi id'si otomatik, sadece `parcel_id`
  seçilir — çünkü bir çiftçinin birden fazla parseli olabilir, bu tek
  gerçek zorunlu seçim). ParcelDetail'in IT-06'dan beri var olan "+ Yeni
  Sezon" inline formuna dokunulmadı (zaten context-aware'di, IT-13 onu
  YENİDEN yapmadı — sadece eksik olan sözleşme/görev'i tamamladı).
  Backend curl ile uçtan uca doğrulandı: FarmerDetail bağlamından
  sözleşme/görev/sezon oluşturma üçü de doğru `farmer_id`/`parcel_id`
  ile başarıyla POST edildi (sonra temizlendi — sözleşme/görev silindi,
  sezon `cancelled`'a çekildi). Frontend canlı webpack hot-reload
  çıktısından doğrulandı (yine "compiled with 7 warnings", hata yok).
  **FAZ 5 TAMAMEN BİTTİ (IT-11+IT-12+IT-13)** — kullanıcı bu fazın
  sonunda zip ALINMAMASINI istedi (istisna, standart protokolün dışında;
  sıradaki fazlarda protokol normal şekilde devam eder).
- ✅ **IT-13.5 (FAZ 5.5 devam ediyor — Geo Dosya İçe Aktarma):** Kullanıcı
  onayıyla `requirements.txt`'e `pyshp`/`ezdxf`/`pyproj` eklendi. Yeni
  `geo_import.py` — `GET /geo-import/epsg-codes` (Türkiye'de sık kullanılan
  ITRF96/TUREF 3° dilim + ED50 UTM EPSG kodları, frontend dropdown'ı için)
  ve `POST /geo-import/parse` (`parcels:import_geojson` izni — mevcut
  permission, yeni eklenmedi): dosya uzantısına göre GeoJSON/KML/SHP(.zip
  içinde .shp+.shx+.dbf+opsiyonel .prj)/DXF ayrıştırır, WGS84'e (EPSG:4326)
  çevirir. SHP'de `.prj` varsa kaynak CRS otomatik algılanır (pyproj
  `CRS.from_wkt`); yoksa VEYA DXF'te (DXF'in hiç CRS bilgisi yoktur)
  `source_epsg` form alanı ZORUNLU, verilmezse 400. NCZ dosyaları
  PARSE EDİLMEZ (415, NetCAD'den SHP/DXF export yönlendirmesi). Endpoint
  SADECE ayrıştırır, hiçbir şey kaydetmez — "önizleme+onay" akışı frontend
  React state'inde tutulur, sunucu tarafında ayrı bir preview-session
  state/TTL yönetimi YOK (bilinçli sadelik, v1 için yeterli). Frontend'e
  yeni `GeoFileImport.jsx` (dosya seç → EPSG seç varsa gerekiyorsa →
  "Ayrıştır" → haritada önizle (react-leaflet, Polygon/Polyline/
  CircleMarker) → "Onayla ve Kaydet") — ParcelDetail.jsx'e bağlandı,
  onaylanan geometri mevcut `PUT /parcels/{id}`'nin `geometry` alanına
  yazılıyor (IT-02'den beri var olan alan, yeni endpoint gerekmedi).
  **Kapsam notu:** idari alana bağlama (IT-13.6'nın `admin_areas`
  koleksiyonu henüz yok) ve NCZ'nin Belgeler sekmesine arşivlenmesi
  (storage.py zaten var, ayrı bir UI teli gerektirir) bu iterasyonda
  YAPILMADI, sonraki bir adımda bağlanabilir. Backend'i GERÇEK dosyalarla
  (pyshp/ezdxf'in kendisiyle üretilmiş SHP/DXF fixture'ları — elle
  yazılmış sahte veri değil) uçtan uca doğruladım: GeoJSON/KML tam
  eşleşme; SHP `.prj`'li ve `.prj`'siz+source_epsg=5254 ikisi de
  ITRF96→WGS84 dönüşümünü doğru yaptı (orijinal WGS84 kareye ~1e-14
  hassasiyetle geri döndü); DXF aynı şekilde doğru; NCZ 415, eksik EPSG
  400, yetkisiz rol 403 — hepsi doğru. Frontend canlı webpack hot-reload
  ile doğrulandı (yine hata yok, sadece önceden var olan uyarılar).
- ✅ **IT-13.6 (FAZ 5.5 TAMAMLANDI — İdari Alanlar + Demografi + Layer v1):**
  Yeni `admin_areas.py` — `admin_areas` koleksiyonu (il/ilçe/mahalle,
  `parent_id` hiyerarşi, GeoJSON Polygon/MultiPolygon). **IT-01.5
  bağımlılığı kararı:** roadmap IT-13.6'yı hem IT-13.5'e hem IT-01.5'e
  bağımlı gösteriyor, ama IT-01.5 (Lookup v2 — kaskad UI + toplu değer
  girişi + parent_group_id) henüz YAPILMADI. Bu bağımlılığın İT-13.6
  için asıl gerekli kısmı — il/ilçe isimlerinin "tek kaynak" olması —
  IT-02 ekinde (bu dosyanın "İl/İlçe lookup verisi" notu) ZATEN
  karşılanmış durumda (`lookup_groups`/`lookup_values`, `ilce.parent_id`
  hiyerarşisiyle). Bu yüzden IT-13.6, admin_areas'a `lookup_value_id`
  alanı ekleyerek (isimleri TEKRAR YAZMADAN) bu mevcut altyapıya
  referans verecek şekilde ilerletildi; IT-01.5'in kendi kapsamı
  (kaskad select UI, toplu değer girişi ekranı, genel `depends_on_field`
  mekanizması) hâlâ AYRI VE BEKLEMEDE — bu karar kullanıcıya
  sorulmadı, mevcut kod tabanı zaten yeterli veriyi sağladığı için
  (Karar Protokolü: "önce mevcut kod tabanını incele" maddesi).
  Yeni permission modülü `admin_areas` (`:view`/`:manage`) —
  `:view` parcels:view sahiplerine, `:manage` parcels:import_geojson
  sahiplerine (ilce_yoneticisi, ziraat_muhendisi + üst 4 rol) verildi.
  Demografi alanları (`population`/`agricultural_area_dekar`/
  `farmer_count_est`) convention #8 gereği GERÇEK Pydantic kolonları
  (JSON blob değil), field_definitions (module="admin_areas") ile
  ekranda yönetiliyor — yeni `seed-admin-areas-pilot` ucu. `POST
  /admin-areas/bulk-import` geo_import.py'nin (IT-13.5) parse çıktısını
  (birden fazla feature) tek seferde çok sayıda admin_area kaydına
  çevirir — idempotent DEĞİL (aynı dosya iki kez yüklenirse iki kez
  kayıt oluşur, bilinçli). `GET /admin-areas/{id}/summary` GERÇEK
  MongoDB `$geoIntersects` (2dsphere index — parcels.geometry'de daha
  önce hiç index YOKTU, bu iterasyonda eklendi) ile o sınırın içindeki
  çiftçi/parselleri hesaplar; village/region eşleştirmesi gibi bir
  yaklaşıklık DEĞİLDİR. Liste yanıtı (`GET /admin-areas`) basit nokta-
  atlama (decimation, Douglas-Peucker DEĞİL — yeni bir kütüphane
  eklememek için bilinçli sadeleştirme) ile geometriyi sadeleştirir
  (max 300 nokta/ring), detay yanıtı (`GET /admin-areas/{id}`) tam
  hassasiyet döner. Query Engine'e (IT-08) de bağlandı (`admin_areas`
  modülü — filterable-fields CORE+field_definitions birleşimi diğer
  modüllerle aynı desende). Frontend'e yeni `AdminAreaManagement.jsx`
  (route `/idari-alanlar`) — SmartDataGrid (IT-11) liste, QuickAddPanel
  tekli oluşturma, kendi toplu-yükleme formu, Drawer'da (IT-12) detay:
  sınır haritası + $geoIntersects özeti + DynamicFieldsSection demografi
  + GeoFileImport (IT-13.5) ile sınır değiştirme — IT-11/12/13.5'in
  TÜMÜNÜ yeniden kullanan bir ekran, yeni bir UI kalıbı icat edilmedi.
  Parcels.jsx'e "İdari Sınırlar" katman aç/kapa butonu (Layer v1).
  Backend'i uçtan uca doğruladım: gerçek bir parselin koordinatlarını
  kapsayan bir test admin_area oluşturup `$geoIntersects` özetinin O
  parseli VE aynı çiftçinin başka bir parselini doğru bulduğunu
  (2 parsel, 1 çiftçi) gördüm; IT-13.5'in SHP fixture'ıyla bulk-import
  test edildi (1 feature → 1 mahalle kaydı, ad SHP attribute'undan
  doğru okundu); Query Engine filterable-fields CORE+field_definitions
  birleşimini doğru döndü. Frontend canlı webpack hot-reload ile
  doğrulandı (yine hata yok). **FAZ 5.5 TAMAMEN BİTTİ (IT-13.5+
  IT-13.6)** — zip alınacak (FAZ 5'in aksine burada kullanıcıdan zip
  atlama talimatı YOK, protokol normal işliyor).
- ✅ **IT-01.5 (FAZ 0 TAMAMLANDI — Lookup v2 / Kaskad Bağımlılık, İl-İlçe
  seed genişletmesi hariç):** Başlamadan önce IT-13.6'nın "tek kaynak
  ilkesi" iddiasını kod düzeyinde doğruladım — `admin_areas.py` gerçekten
  il/ilçe isimlerini kopyalamıyor (`lookup_value_id` ile referans veriyor),
  AMA bunu incelerken ayrı bir tutarsızlık buldum: il→ilçe ilişkisi
  `lookup_values.parent_id` ile ÇAPRAZ-GRUP kuruluyordu (ilçe değerinin
  parent_id'si il grubundaki bir değerin id'si) ama resmi API
  (`POST /lookups/groups/{id}/values`) parent'ı hep AYNI GRUPTA arıyordu
  — yani bu veri SADECE seed fonksiyonunun API'yi bypass edip DB'ye elle
  yazmasıyla var olabiliyordu, Lookup Yönetimi ekranından biri elle
  aynısını yapamazdı. Bu iterasyon bunu formelleştirdi: `lookup_groups`'a
  `parent_group_id` eklendi; `create_lookup_value`/`update_lookup_value`
  artık grup `parent_group_id` taşıyorsa parent'ı ÜST GRUPTA, taşımıyorsa
  eskisi gibi AYNI GRUPTA arıyor (`_validate_value_parent` — geriye dönük
  kırılma yok); `seed_il_ilce_lookup` artık idempotent bir
  `_upgrade_lookup_group("ilce", parent_group_id=il_id)` çağrısıyla daha
  önce (bu iterasyondan ÖNCE) oluşmuş "ilce" grubunu da geriye dönük
  işaretliyor — ayrı bir migration script'i gerekmedi. `field_definitions`'a
  `depends_on_field` eklendi (aynı modülde, lookup_group_id'si olan başka
  bir field_key'e referans; create/update'te `_validate_depends_on_field`
  ile doğrulanıyor); `parcels.ilce` artık `depends_on_field="il"` ile
  işaretli (seed_parcels_pilot'taki mevcut upgrade çağrısına eklendi).
  Yeni `POST /lookups/groups/{id}/values/bulk-import` — kopyala-yapıştır
  metni (satır başına bir değer, `"sistem_degeri|Görünen Ad"` veya sadece
  `"Görünen Ad"`), `_slugify_tr` ile otomatik value üretimi, (group_id,
  value, parent_id) üçlüsüne göre idempotent (zaten varsa atlanır).
  Frontend: `FormYonetimi.jsx`'in `FieldFormDialog`'ına "Bağımlı Olduğu
  Alan (Kaskad)" seçimi (aynı modüldeki, kendisi de lookup_group_id'si
  olan diğer alanlarla sınırlı bir dropdown); `LookupYonetimi`'ye grup
  oluştururken "Üst Grup" seçimi, grup/değer listelerinde üst grup
  rozeti, "Üst Değer" kaynağının (hem tekli ekleme hem toplu ekleme için)
  `parent_group_id` varsa ÜST GRUBUN değerlerinden gelecek şekilde
  düzeltilmesi, tablodaki "Üst Değer" kolonunun artık çapraz-grup
  etiketini de çözebilmesi (`valuesById` kendi + üst grup değerlerinin
  birleşimi), ve "Toplu Değer Girişi" (textarea + varsa üst değer seçimi)
  bölümü. `DynamicFieldsSection.jsx`'e kaskad select davranışı: bir alan
  `depends_on_field` taşıyorsa üst alanın seçili "value"su üst alanın
  lookup grubundaki karşılık gelen `lookup_value.id`'ye çevrilir
  (`fieldsByKey` + `lookupValuesByGroup` ile), bu id kendi grubumuzdaki
  değerlerin `parent_id`'siyle eşleştirilir; üst alan boşken select
  DISABLED + `Önce "X" seçin` ipucu gösterir; üst alan değiştiğinde artık
  geçersiz olan alt seçim otomatik temizlenir (`cascadeReady` bayrağıyla
  — lookup verisi henüz async yüklenmeden ÖNCEKİ geçici render'da edit
  ekranındaki geçerli bir eşleşmenin yanlışlıkla temizlenmesi önlendi).
  **Kapsam notu:** kullanıcı bu oturumda kapsamı ROADMAP'teki IT-01.5
  tanımından biraz daraltıp "İl-İlçe seed verisi" (TR_IL_ILCE sözlüğünü
  81 ile genişletme) maddesini dışarıda bıraktı — TR_IL_ILCE hâlâ sadece
  Konya+Ankara, bu ayrı bir iterasyon olarak kalabilir.
  **Gerçek tarayıcıda uçtan uca doğrulandı** (Docker mongo + uvicorn +
  craco dev server, Windows'ta port 8001/3000'i tutan eski stale
  python.exe/node.exe süreçleri `taskkill` ile temizlendi — bkz. Bilinen
  Tuzaklar): Lookup Yönetimi'nde "İlçe" grubu "İlçe → İl" rozetiyle
  görünüyor, tablo "Ahırlı" için üst değeri artık "—" değil "Konya"
  gösteriyor (migration öncesi "—"idi, `seed-il-ilce-lookup` tekrar
  çağrılınca düzeldi); toplu ekleme ile 3 satır eklendi (idempotent tekrar
  denemede aynı satır atlandı); Parsel "Manuel Ekle" formunda İlçe select'i
  İl boşken DISABLED + "Önce İl seçin" gösterdi, Konya seçilince SADECE
  Konya'nın 30 ilçesi listelendi, bir ilçe seçilip İl "Ankara"ya
  değiştirilince eski seçim otomatik temizlendi ve liste Ankara'nın 25
  ilçesine güncellendi; Form Yönetimi'nde "İlçe" alanının düzenleme
  diyaloğu "Bağımlı Olduğu Alan" olarak doğru şekilde "İl"i seçili
  gösterdi. **Doğrulama sırasında bulunup düzeltilen bug:** `_slugify_tr`
  büyük "İ" harfini yanlış işliyordu (Python'un Unicode `.lower()`'ı
  "İ"yi önce "i" + birleşik nokta işaretine (U+0307) açıyor, bu da
  translate tablosundaki tekil "İ"->"i" eşlemesini atlayıp "_" üretiyordu
  — `"Test İlçesi"` -> `"test_i_lcesi"` yerine doğrusu `"test_ilcesi"`);
  düzeltme: Türkçe karakter çevirisi ÖNCE, `.lower()` SONRA yapılacak
  şekilde sıra değiştirildi. Doğrulama sırasında oluşan test verileri
  (3 geçici ilçe kaydı) temizlendi, kalıcı veri değişikliği sadece
  `ilce.parent_group_id` migration'ı ve `parcels.ilce.depends_on_field`
  upgrade'i (ikisi de idempotent, tekrar seed çağrılarında zararsız).
- ✅ **IT-14 (FAZ 6 devam ediyor — Widget Kayıt Altyapısı + Harita Paneli):**
  Kullanıcı ROADMAP'teki belirsiz "8 temel widget"i somutlaştırdı: Toplam
  Çiftçi, Toplam Parsel, Toplam Ekili Alan, Boş Parseller, Aktif Üretim
  Sezonları, Hasat Bekleyen Alanlar, Görev Bekleyen Parseller, Riskli
  Parseller — VE bunların birer REFERANS implementasyon olduğunu, asıl
  teslimin widget kayıt+render altyapısı olduğunu, yeni widget eklemenin
  harita mimarisini değiştirmeyi gerektirmemesi gerektiğini netleştirdi
  (NDVI/Su Stresi gibi FAZ 9.5 widget'ları BİLİNÇLİ OLARAK bu iterasyona
  alınmadı). Yeni `lib/mapWidgets/` — her widget kendi dosyasında
  `{key, title, icon, accent, compute(ctx)}`, `index.js` bunları
  `MAP_WIDGET_REGISTRY`'de toplar (yeni widget = yeni dosya + 1 import
  satırı). `components/WidgetCard.jsx` — widget-agnostik render (compute
  hata verirse try/catch ile "—", tüm paneli çökertmez). Yeni
  `pages/HaritaPaneli.jsx` (route `/harita-paneli`, Layout.jsx'e "ANA"
  grubunda "Parseller"in yanına eklendi) — parcels/production_cycles/
  operations/tasks/farmers'ı tek seferde yükler (Parcels.jsx'teki
  "hepsini çek, client-side filtrele" kalıbı); **harita↔dashboard senkron**
  üç boyutun kesişimi: harita sınırları (moveend/zoomend + turf.centroid +
  Leaflet bounds.contains) ∩ FilterPanel (IT-09, module="parcels") sonucu
  ∩ (varsa, ÖNCELİKLİ) tıklanarak seçilen parseller; harita da widget'larla
  TUTARLI olsun diye tüm parcels yerine bu kapsamlı kümeyi çizer. Backend'e
  yeni `map_workspace.py` — kullanıcı başına TEK "kişisel çalışma alanı"
  kaydı (`GET/PUT/DELETE /map-workspaces/me`, widget_keys/map_center/
  map_zoom OPAK saklanır, backend widget bilmez/doğrulamaz). **Gerçek
  tarayıcıda uçtan uca doğrulandı** (aynı Docker mongo + uvicorn + craco
  ortamı, yine port 8001'i tutan eski stale python.exe süreçleri
  `taskkill` ile temizlendi): `window.__debugMap` (React fiber üzerinden
  Leaflet map instance'ına erişim — preview_click Leaflet zoom kontrollerini
  bu ortamda tetiklemiyor, programatik `setZoom`/`setView` ile doğrulandı)
  ile zoom 7→12 (484→0 parsel), Konya'ya pan (0, veri o bölgede yok),
  zoom 7'ye geri dönüş (484 — tekrarlanabilir); harita üzerinde parsel
  tıklama → "1 parsel seçili" + widget 1'e düştü; risk_level=kirmizi
  filtresi → 61 parsel hem haritada hem widget'ta; widget picker'dan
  "Riskli Parseller" kapatıldı (8→7); "Görünümü Kaydet" → reload sonrası
  7 widget + kaydedilen merkez/zoom GERİ GELDİ; "Sıfırla" → 8 widget'a
  ve backend kaydının silinmesine dönüldü. **Doğrulama sırasında bulunup
  düzeltilen bug:** `MapSync` bileşeni `useMapEvents`'e her render'da YENİ
  bir handlers nesnesi veriyordu — react-leaflet'in kendi useEffect'i
  `[map, handlers]`'a bağımlı olduğundan (bkz. node_modules/react-leaflet/
  lib/hooks.js) bu sürekli off/on tetikliyordu; `useRef` ile TEK SEFER
  oluşturulan sabit handlers + `onChangeRef` ile en güncel callback kalıbına
  geçildi (bkz. Bilinen Tuzaklar — FAZ 6'nın kalanında tekrar kullanılacak).
  **Kapsam dışı bulunan, AYRI bir arka plan görevine işaretlenen sorun:**
  HER sayfada (Dashboard, Farmers dahil — IT-14'ün kodu DEĞİL) her tam
  yenilemede ~450 kez "Maximum update depth exceeded" konsol hatası —
  önceden var olan bir bug, bu iterasyonda düzeltilmedi (bkz. Bilinen
  Tuzaklar).
- ✅ **IT-15 (FAZ 6 devam ediyor — Katman Yönetimi + Basemap + Şekille
  Seç + Toplu İşlemler):** HaritaPaneli.jsx'e "Katmanlar" paneli
  (Parseller/İdari Sınırlar aç-kapa — İdari Sınırlar açılınca Parcels.jsx
  ile aynı tembel-yükleme kalıbıyla `GET /admin-areas` çeker), "Basemap"
  seçici (Koyu/Açık/Sokak/Uydu — 4 anahtarsız genel XYZ servisi), "Şekille
  Seç" (polygon/rectangle/circle — `MapDrawTools`'a yeni `mode="select"`,
  L.Control.Draw toolbar'ında üç aracı da sunar, otomatik tetiklemez)
  eklendi. Seçim mantığı netleştirildi: yeni `filteredParcels` (mapBounds
  ∩ Gelişmiş Filtre, SEÇİMDEN bağımsız) `scopedParcels`'ten ayrıştırıldı —
  "Şekille Seç" bu havuzdan seçer (turf.booleanPointInPolygon; daire için
  `layer.getLatLng()/getRadius()`'tan turf.circle kurulur, leaflet'in
  circle→GeoJSON'ı bir Point döndüğünden geometriyi bundan TÜRETMEK
  gerekiyordu). Kişisel çalışma alanına (`map_workspace.py`) aynı opak
  desende `basemap_key`/`visible_layers` eklendi. Yeni `PUT /parcels/
  bulk-update` (server.py, `/parcels/{parcel_id}`'den ÖNCE tanımlı —
  route sırası önemli) — soil_type/irrigation/risk_level alt kümesini
  seçili TÜM parsellere uygular, her parsel için AYRI `log_audit` çağırır
  (convention #6, tek bir "bulk" kaydı old/new'i anlamsızlaştırırdı).
  Toplu görev oluşturma için yeni bir endpoint YOK — mevcut `POST
  /operations/tasks` seçili her parsel için tekrarlanır (bilinçli, N
  ayrı istek beklenen seçim boyutları için makul). **Yan keşif/onarım
  (gerçek bug, bkz. Bilinen Tuzaklar):** `MapDrawTools.jsx`'in olay
  dinleyicileri `onCreated`/`onEdited`'i STALE closure ile yakalıyordu
  (MapSync'teki `onChangeRef` bug'ıyla aynı aile) — `onCreatedRef`/
  `onEditedRef` ile düzeltildi, hem yeni "select" modunu hem Parcels.jsx'in
  önceden var olan çizim akışlarını etkiler. **Gerçek tarayıcıda uçtan uca
  doğrulandı** (native Windows MongoDB servisi + uvicorn + craco dev
  server — bu oturumda Docker Desktop çalışmıyordu, `backend/.env`'in
  zaten `mongodb://localhost:27017`'ye işaret ettiği, halihazırda çalışan
  yerel MongoDB servisine bağlandığı keşfedildi): Katmanlar panelinden
  İdari Sınırlar açılınca `GET /admin-areas` doğru tetiklendi; Basemap
  "Uydu" seçilince Esri tile'ları 200 ile yüklendi ve `map-workspaces/me`
  round-trip'i ile kalıcılığı doğrulandı; `window.__debugMap` (geçici,
  test sonrası kaldırıldı) ile programatik rectangle/circle çizimleri
  ateşlenip haritanın gerçek `mapBounds`'una göre doğru alt kümeyi
  seçtiği (220/484 gibi tutarlı sayılarla) doğrulandı — DÜZELTMEDEN
  ÖNCE aynı test (400km çember) stale closure yüzünden mapBounds'u
  YOK SAYIP 865 (sınırsız havuz) döndürüyordu, düzeltmeden SONRA 484
  (bounds-sınırlı, manuel haversine hesabıyla birebir) döndü; toplu alan
  güncelleme 220 parselde `PUT /parcels/bulk-update` ile 200 döndü ve
  audit log'da HER parsel için ayrı old/new kaydı doğrulandı; toplu görev
  oluşturma 4 parselde 4 ayrı `POST /operations/tasks` ile 200 döndü.
  **Doğrulama sonrası test verisi temizlendi:** 4 test görevi silindi,
  bulk-update'in gerçekten değiştirdiği 165 parselin `irrigation`'ı audit
  log'daki `old_value`'dan okunup tek tek geri yüklendi (spot-check ile
  doğrulandı); kişisel çalışma alanı "Sıfırla" ile varsayılana döndürüldü.
  Konsol boyunca HİÇ hata yok.
- ✅ **IT-16 (FAZ 6 devam ediyor — TKGM İçe Aktarma + Zenginleştirilmiş
  Popup + Navigasyon Linki + Harita Snapshot):** `POST /parcels/
  import-geojson`'a `_extract_tkgm_fields` eklendi — TKGM Parsel Sorgu
  (parselsorgu.tkgm.gov.tr, resmi API DEĞİL, kullanıcının manuel export
  ettiği genel bir harita) GeoJSON'undaki il/ilçe/mahalle/ada/parsel
  özellik adlarını IT-02'nin parsel alanlarına eşler, "alan" (m²) yoksa
  area_dekar'a çevrilir, isim yoksa "Ada X Parsel Y" varsayılanı üretilir.
  Aynı mantığın tek-parsel karşılığı frontend'de: yeni `lib/
  tkgmMapping.js` (`mapTkgmProperties`) — `GeoFileImport.jsx`'e entegre
  edildi (`onConfirm(geometry, tkgmFields)`, geriye dönük uyumlu ikinci
  argüman), ParcelDetail.jsx'in mevcut sınır-değiştirme akışı artık
  TKGM alanlarını da PUT body'sine ekliyor; Parcels.jsx'in "GeoJSON İçe
  Aktar" aracı "GeoJSON / TKGM İçe Aktar" olarak yeniden adlandırıldı +
  TKGM alanı algılanan kayıt sayısını önizlemede gösteriyor.
  HaritaPaneli.jsx'in parsel popup'ı "hızlı işlem merkezi"ne dönüştü:
  çiftçi adı/toprak/sulama/risk/en güncel sezon bilgisi + üç hızlı işlem
  ("Detaya Git", yeni `lib/directions.js` ile "Yol Tarifi" — anahtarsız
  Google Maps linki, ve popup içi "+ Görev" mini formu — bulk task
  panelinin tekli karşılığı). Yeni backend modülü `map_snapshots.py`
  (**Harita Snapshot**) — `saved_queries.py` ile AYNI kalıpta
  adlandırılmış/çoklu/paylaşılabilir (`is_shared`) görünüm kayıtları,
  `map_workspace.py`'nin kullanıcı-başına-tek-kayıt modelinden BİLİNÇLİ
  AYRI; "paylaşım" bir ekran görüntüsü değil DURUM paylaşımı —
  `?snapshot=<id>` linki açılınca harita merkez/zoom/widget/basemap/
  katman/seçimi birebir geri yükler (yeni bir görüntü/canvas kütüphanesi
  KULLANILMADI, Karar Protokolü gereği). **Yan bulgu/onarım (gerçek
  bug):** `MapDrawTools.jsx`'in olay dinleyicileri stale closure ile
  `onCreated`/`onEdited`'i yakalıyordu (bkz. Bilinen Tuzaklar, IT-15'te
  bulunup düzeltilmişti) — bu iterasyonda TEKRAR doğrulandı, sorun yok.
  **Gerçek tarayıcıda uçtan uca doğrulandı:** TKGM property mapping'i
  sentetik bir GeoJSON ile `/parcels/import-geojson`'a POST edilip
  il/ilçe/mahalle/ada_no/parsel_no_tapu/area_dekar'ın (8500 m²→8.5 dekar)
  ve otomatik ismin ("Ada 123 Parsel 45") doğru üretildiği doğrulandı;
  route sırası (`/parcels/bulk-update` hâlâ doğru handler'a gidiyor)
  yeniden test edildi; haritada bir parsele tıklayıp zenginleştirilmiş
  popup içeriği (çiftçi/toprak/sulama/risk/sezon) + üç hızlı işlem
  gözlemlendi, "Detaya Git" ParcelDetail'e temiz geçiş yaptı, "Yol
  Tarifi" doğru Google Maps URL'i üretti, "+ Görev" gerçek bir görev
  oluşturdu (`POST /operations/tasks` 200); Harita Snapshot kaydedildi
  (`is_shared:true` ile), `?snapshot=<id>` linkiyle YENİDEN açılınca
  doğru widget/basemap/merkez/zoom'la geri yüklendiği ve bunun HEADER'da
  görünür bir onay mesajıyla (ilk halinde panel kapalıyken görünmeyen
  bir kusur bulunup HEMEN düzeltildi) bildirildiği doğrulandı; snapshot
  silindi. **Doğrulama sırasında bulunup düzeltilen bug:** ilk
  implementasyonda `snapshotMsg` sadece (varsayılan KAPALI) Anlık
  Görüntü panelinin İÇİNDE render ediliyordu — `?snapshot=` linkiyle
  gelen bir kullanıcı panel kapalıyken "X görünümü yüklendi" mesajını
  HİÇ göremezdi; mesaj artık her zaman görünen header satırına taşındı
  (`saveMsg` ile aynı yerde). **Test verisi temizliği:** oluşturulan
  test görevi/snapshot/parsel hepsi doğrulama sonrası silindi.
- ✅ **IT-17 (FAZ 6 TAMAMLANDI — Mekânsal Zaman Makinesi + Uydu Provider
  Soyutlaması + AI Harita Asistanı):** Yeni `backend/satellite_provider.py`
  — `SatelliteProvider` (ABC) + `DemoSatelliteProvider` (extras.py'nin
  `/satellite/ndvi/{parcel_id}` ucundaki MOCK üretim mantığı buraya
  taşındı, DRY) + `get_satellite_provider()` factory + `ndvi_to_health`/
  `ndvi_to_risk_level` yardımcıları — gerçek Sentinel-2/Planet FAZ 9.5
  (IT-28.1) kapsamında, o zaman SADECE yeni bir alt sınıf eklenir,
  extras.py DEĞİŞMEZ. Yeni `POST /satellite/ndvi-snapshot` — ÇOKLU
  parsel için TEK bir tarihteki NDVI/risk anlık görüntüsü (parcel
  varlığı DB'den doğrulanmaz, hesaplama saf fonksiyon — `/parcels/
  bulk-update` emsaliyle aynı). HaritaPaneli.jsx'e "Zaman Makinesi"
  (10 sabit tarih üzerinde gezen slider + Oynat/Duraklat, açılınca
  SÜREKLİ görünür bir çubuk — dropdown DEĞİL) ve "AI Harita Asistanı"
  (mevcut `/ai/copilot`'u çağırıp sonucu `setSelectedIds`'e bağlayan
  NL arayüzü) eklendi. `timeAdjustedParcels` katmanı parsellerin ndvi/
  risk'ini Zaman Makinesi açıkken GEÇİCİ OLARAK günceller — harita
  renkleri VE TÜM widget'lar (tek dosya değişmeden) otomatik yansıtır;
  `ctx.productionCycles` aynı anda `year===2025`'e süzülür ("sezon
  senkron"). **Gerçek tarayıcıda uçtan uca doğrulandı:** aynı parsel_id+
  tarih ikilisi için NDVI'nin deterministik (iki ayrı çağrıda birebir
  aynı) olduğu doğrulandı; Zaman Makinesi açılıp "15 Eylül 2025"te
  Riskli Parseller widget'ı 267'den 518'e çıktı, slider "1 Mayıs 2025"e
  çekilince (sezon başı, düşük risk) 0'a düştü — üç FARKLI, tutarlı
  sayı aynı verinin gerçekten tarihe göre yeniden hesaplandığını
  kanıtladı; kapatılınca 267'ye (orijinal) tam geri döndü. AI Harita
  Asistanı "Konya'daki en riskli 10 parseli göster" sorgusuyla test
  edildi (AI servisi yapılandırılmamış, anahtar-kelime fallback devreye
  girdi) — 10 parsel doğru şekilde haritada seçildi, özet mesajı
  gösterildi. **Yan bulgu (operasyonel, gerçek bug DEĞİL):** aynı anda
  değiştirilen `extras.py` + `satellite_provider.py`'den sadece ikincisi
  `uvicorn --reload`'ı tetikledi, extras.py'nin yeni endpoint'i bir süre
  404 döndü — backend'in TAM yeniden başlatılmasıyla (bkz. Bilinen
  Tuzaklar) çözüldü. **FAZ 6 TAMAMEN BİTTİ (IT-14+IT-15+IT-16+IT-17)** —
  Oturum Teslim Protokolü'ne göre bir fazın tüm IT'leri bittiğinde zip
  alınır; bu ortamda (yerel Windows dev, `/mnt/user-data/outputs` yok)
  zip'in nereye/nasıl paketleneceği kullanıcıya sorulmalı.
- ✅ **IT-18 (FAZ 7 başladı — Destek Kataloğu + Destek Talep Süreci):**
  Yeni `backend/support.py` — `SupportType` katalog (9 varsayılan tip
  idempotent seed: Mazot/Gübre/Tohum/İlaç/Makine Hizmeti/Sulama/Nakliye/
  Avans/Diğer) + `SupportRequest` 9 durumlu SIRALI durum makinesi
  (production_cycles.py'nin ALLOWED_TRANSITIONS kalıbıyla birebir —
  atlama yok, her adımdan `reddedildi`/`iptal_edildi` dallanabilir,
  `tamamlandi`/`reddedildi`/`iptal_edildi` terminal). `ciftci_onayladi`
  geçişi `confirmation_method` zorunlu kılar — enum'da 5 yöntem
  (mobil_onay/qr_kod/dijital_imza/fotograf/gps_konumu) tanımlı ama BU
  FAZDA sadece mobil_onay/fotograf kabul edilir (ROADMAP'in "ilk fazda
  en az bu ikisi" notu). Her durum geçişinde `notifications`
  koleksiyonuna insert (Comm Hub/IT-25 henüz yok — irrigation_events'teki
  AYNI hafif desen). Çiftçi portalı: `GET /portal/production-cycles`
  (iptal edilmiş sezonlar HARİÇ), `GET /portal/support-types`,
  `GET/POST /portal/support-requests` — `/farmer/*` ile AYNI desen
  (`current_user.role=="ciftci"` + `farmer_id` sahiplik kontrolü, ayrı
  permission gerektirmez, ownership çapraz-çiftçi denemesiyle test
  edildi → 403). `permissions.py`'ye yeni `support` modülü eklendi
  (catalog_view/manage, requests_view/manage) — ilce_yoneticisi/
  ziraat_muhendisi'ne view+manage, saha_personeli'ne sadece view.
  Frontend: `pages/SupportCatalog.jsx` (`/destek-katalogu`, admin-tier),
  `ProductionCycleDetail.jsx`'e "Destek Talepleri" kartı (yeni talep +
  durum-geçiş butonları + çiftçi onayı doğrulama yöntemi seçici),
  `FarmerHome.jsx`'e "Destek Talebi" hızlı aksiyonu + modal + "Destek
  Taleplerim" listesi. **Gerçek tarayıcıda uçtan uca doğrulandı:** admin
  tarafında bir talep taslak→gönderildi→...→çiftçi onayladı (fotoğraf
  yöntemiyle)→muhasebeleşti→tamamlandı zincirinin TAMAMI UI'dan
  tıklanarak yürütüldü (backend curl ile ayrıca atlama/terminal-durum/
  eksik-onay-yöntemi/red+sebep senaryoları da 400 ile doğru reddedildi);
  çiftçi portalından gerçek bir talep oluşturuldu ve "Destek
  Taleplerim"de + admin tarafında aynı kayıt göründü. **Doğrulama
  sırasında bulunup düzeltilen küçük bir kapsam eksikliği:** `/portal/
  production-cycles` başlangıçta `cancelled` sezonları da listeliyordu —
  DB'de rastlanan (bu iterasyondan ÖNCE, başka bir test oturumundan
  kalma) iptal edilmiş bir sezon (`2027 — "Ana Urun"`, ASCII karakterli)
  destek talebi formunda seçenek olarak görününce fark edildi, filtre
  `status != cancelled` olarak eklendi (tamamlanmış sezonlar dahil kaldı
  — hasat sonrası nakliye gibi destekler hâlâ anlamlı). Test verisi
  (oluşturulan support_requests + ilgili notifications) doğrulama
  sonrası temizlendi, `support_types` seed'i (gerçek katalog verisi)
  korundu.
- ✅ **IT-19 (FAZ 7 devam — Financial Ledger + Cari Hesap):** Yeni
  `backend/ledger.py` — `ledger_entries` koleksiyonu **IMMUTABLE**:
  bilinçli olarak `PUT`/`DELETE /ledger/{id}` YOK (405 döner, kabul
  kriteri "update/delete engellenmiş" doğrudan buradan sağlanıyor),
  sadece `POST /ledger` (yeni kayıt) ve `POST /ledger/{id}/reverse`
  (orijinali BOZMADAN ters işaretli YENİ kayıt — `is_reversal`/
  `reversed_entry_id`; aynı kayıt iki kez reverse edilmeye çalışılırsa
  409). `create_ledger_entry()` — diğer modüllerin doğrudan import edip
  çağırdığı tek giriş noktası (whitelist HER ZAMAN buradan geçer, `POST
  /ledger` da sadece ince bir sarmalayıcı). `GET /production-cycles/
  {id}/current-account` — `by_type` (entry_type→toplam) + `balance`
  (TÜM kayıtların toplamı, ters kayıtlar dahil) + `entries` listesi.
  **IT-18→IT-19 geriye dönük entegrasyon (kullanıcı onayıyla, "geriye
  dönük bağımlılık" talimatı kapsamında):** `support.py`'nin transition
  endpoint'i artık `ledger.create_ledger_entry()`'yi doğrudan import
  edip çağırıyor — bir SupportRequest **SADECE** "muhasebelesti"
  durumuna geçtiğinde (omurga akışındaki "Cari Hareket" adımı — bu
  durum adı zaten bunu ima ediyordu) otomatik bir `entry_type=
  "destek_teslimi"` kaydı açılır: tutar = `requested_amount *
  support_type.default_price` (fiyat 0/tanımsızsa 0 TL — admin katalogda
  fiyat girmeden gerçek parasal etki oluşmaz, bilinçli varsayılan),
  işaret NEGATİF; bu otomatik kayıt için de (convention #6 gereği,
  manuel `POST /ledger` ile AYNI) ayrı bir `log_audit` çağrısı eklendi.
  `reddedildi`/`iptal_edildi` durumları bu zincire HİÇ girmez (kabul
  kriteri "reddedilen/iptal edilen talep cari hesaba yansımaz" böylece
  IT-19 tarafında da somutlaşmış oldu). `permissions.py`'ye yeni `ledger`
  modülü (`view`/`create`/`reverse`) — ilce_yoneticisi'ne tam yetki
  (view+create+reverse), ziraat_muhendisi'ne sadece `view` (ters kayıt/
  manuel hareket ekleme gibi hassas finansal işlemler bilinçli olarak
  daha üst role bırakıldı). **`db.finance` ile KARIŞTIRILMADI** — bu
  Sprint 1-4d'den kalma, farmer_id bazlı (ProductionCycle'a bağlı
  DEĞİL), sadece seed_data'da statik üretilen, Dashboard/FarmerHome
  bakiye özetinde salt-okunur kullanılan ESKİ bir demo koleksiyonu; bu
  iterasyon ona dokunmadı (kantar_records'ın IT-05'teki bilinçli kapsam
  dışı bırakılmasıyla AYNI karar — yanlış bir geriye-dönük eşleştirme
  yapmaktansa iki ayrı veri kaynağı olarak bırakıldı). Frontend:
  `ProductionCycleDetail.jsx`'e "Cari Hesap" kartı (bakiye + entry_type
  özet rozetleri + `QuickAddPanel` ile serbest hareket ekleme + hareket
  listesi + her satırda "Ters Kayıt" butonu). **Gerçek tarayıcıda uçtan
  uca doğrulandı** (backend curl/PowerShell ile de ayrıca): Mazot'un
  `default_price`'ı 25 TL/lt yapılıp bir destek talebi taslak→...→
  muhasebeleşti zincirinin TAMAMI çalıştırıldı, ledger'da OTOMATİK
  `100 lt × 25 TL = -2500 TL` kaydının doğru oluştuğu doğrulandı; manuel
  `avans` (-1000) + `prim` (+300) kayıtları eklenip cari hesap
  bakiyesinin (-2500-1000+300=-3200) matematiksel olarak doğru
  toplandığı doğrulandı; geçersiz `entry_type` 400 ile reddedildi;
  `PUT`/`DELETE /ledger/{id}` 405 ile reddedildi; bir `avans` kaydı
  ters kayıtla düzeltilip (+1000) orijinalin DEĞİŞMEDİĞİ ve bakiyenin
  doğru yeniden hesaplandığı (-2200) doğrulandı; aynı kaydı İKİNCİ kez
  reverse etmeye çalışmak 409 ile reddedildi; hem manuel hem otomatik
  ledger kayıtları için `audit_logs`'ta "kim, ne zaman" doğrulandı.
  Tarayıcıda "Yeni Hareket Ekle" formuyla gerçek bir avans kaydı
  eklendi, "Ters Kayıt" butonu tıklanarak (bu ortamda `window.prompt`
  override edilerek doğrulandı — gerçek kullanıcı tarayıcısında sorun
  değil) bakiyenin 0'a döndüğü ve orijinal kaydın "AVANS" rozetiyle,
  ters kaydın "TERS KAYIT" rozetiyle ayrı ayrı listelendiği gözlemlendi.
  Test verisi (support_requests/notifications/ledger_entries + Mazot'un
  test fiyatı) doğrulama sonrası temizlendi.
- ✅ **IT-20 (FAZ 7 devam — Hakediş Motoru):** Yeni `backend/entitlement.py`
  — girdiler: tartım/tonaj/kalite `kantar_records`'tan (bkz. `data_entry.py`
  satırındaki yeni opsiyonel `production_cycle_id` alanı), kota
  `contracts.kota_ton` toplamından, birim fiyat calculate/finalize
  isteğinin parametresi (Contract'a gömülü DEĞİL — bilinçli karar, bkz.
  modül docstring'i). SAF fonksiyonlar: `calculate_gross_entitlement()`
  (tonnage_within_quota × unit_price × kalite katsayısı — A=1.05/B=1.0/
  C=0.9, tonaj-ağırlıklı ortalama), `resolve_definition_amount()`
  (sabit_tutar/yüzde/formül — formül HER ZAMAN override_amount ister),
  `calculate_entitlement_chain()` (Brüt→Kesinti→Net→+Prim→Ödenecek) —
  `tests/test_entitlement.py` ile 12 unit test, hepsi geçiyor (kota
  aşımı, ağırlıklı kalite katsayısı, boş tonaj, formül override zorunlu
  vb. dahil). `POST /entitlement/calculate` dry-run; `POST /entitlement/
  {id}/finalize` idempotent (`entitlements` koleksiyonunda kayıt varsa
  409) — `hakedis`(+brüt)/`kesinti`(-tutar)/`prim`(+tutar) YENİ
  LedgerEntry'ler yazar, **`mahsup` kaydı BİLİNÇLİ OLARAK 0 TUTARLI**
  (destek borcu zaten `destek_teslimi` ile Ledger'da — ikinci kez
  negatif yazmak bakiyeyi bozardı, bu double-counting riskini önlemek
  bu iterasyonun en kritik tasarım kararıydı). Prim/Kesinti kataloğu
  (`entitlement_definitions`) SupportType ile AYNI desen (idempotent
  7 varsayılan: Kalite/Erken Teslim/Kota Primi + Ceza/Fire/Hizmet/Diğer
  Kesintiler). `permissions.py`'ye yeni `entitlement` modülü — ilce_
  yoneticisi'ne tam yetki (calculate+finalize+definitions_manage),
  ziraat_muhendisi'ne sadece view+calculate (finalize gibi Ledger'a
  kalıcı yazan hassas işlem daha üst role bırakıldı — `ledger:reverse`
  kısıtlamasıyla AYNI mantık). **Gerçek backend'de curl/PowerShell ile
  uçtan uca doğrulandı:** 50 ton A + 30 ton C kalite kantar kaydı + kota
  1159 ton + 25 TL/ton ile dry-run brüt hakedişin ELLE hesaplanan
  1987.5 TL'ye (80 ton × 25 × 0.9938 ağırlıklı katsayı) TAM eşleştiği;
  Fire (sabit 50 TL kesinti) + Kalite Primi (%4 = 79.5 TL) uygulanarak
  finalize edilip ödenecek tutarın (2017 TL) ELLE hesapla birebir
  eşleştiği; 4 ledger kaydının (hakedis/kesinti/prim/mahsup=0) toplamının
  cari hesap bakiyesiyle (2017 TL) BİREBİR tutarlı olduğu; aynı sezon
  için İKİNCİ finalize denemesinin 409 ile reddedildiği; ayrı bir
  sezonda ÖNCEDEN VAR OLAN bir destek_teslimi borcunun (-300 TL)
  dry-run'da `destek_mahsup_total` olarak doğru yansıdığı AMA ledger
  bakiyesini dry-run'ın hiç etkilemediği (double-write riski YOK);
  tanımsız definition_id 404, formül tipi override olmadan 400, override
  ile başarılı; `ciftci` rolünün `entitlement:calculate`'ten 403 aldığı
  doğrulandı. Test verisi (ledger_entries/entitlements/test kantar
  kayıtları + tanımların test değerleri) doğrulama sonrası temizlendi,
  `entitlement_definitions` seed'i (gerçek katalog) korundu.
- ✅ **IT-21 (FAZ 7 TAMAMLANDI — İcmal Belgesi + Finansal Simülasyon +
  UFYD Dashboard):** `entitlement.py`'nin `_gather_and_compute` closure'ı
  modül seviyesine `gather_and_compute_entitlement()` olarak taşındı
  (tonnage/kota/destek_mahsup override parametreleriyle) — hem
  `/entitlement/calculate`+`/finalize` (override'sız, gerçek veri) hem
  yeni `reconciliation.py`'nin `/simulation/entitlement`'ı (override'lı,
  what-if) AYNI fonksiyonu çağırır. Simülasyon yanıtı HER ZAMAN
  `{"simulation": true, "overrides_applied": {...}, "result": {...}}`
  zarfında döner — gerçek `entitlements` kaydıyla (finalized_at/
  finalized_by/ledger_entry_ids alanları var) ASLA karışmaz (kabul
  kriteri). Yeni `backend/reconciliation.py`: İcmal PDF'i (reportlab,
  müstahsil makbuzuyla AYNI ASCII-yakın metin deseni) — Üretim Sezonu/
  tonaj/kalite/birim fiyat/brüt hakediş/destek mahsubu+kesintiler
  (kalem kalem)/primler/net ödeme/cari bakiye TEK belgede; `POST
  /reconciliation/{cycle_id}` idempotent (entitlement yoksa 404);
  onay/itiraz sahiplik kontrolü (`_check_reconciliation_access` —
  ciftci sadece kendi farmer_id'si, staff `reconciliation:view`/
  `manage`). `GET /ufyd/dashboard` Ledger/SupportRequest/Entitlement'tan
  CANLI hesaplanır (kabul kriteri) — `cash_need` v1'de bilinçli olarak
  `pending_payments`'la AYNI (ayrı ödeme-takip mekanizması henüz yok).
  `permissions.py`'ye yeni `reconciliation` modülü. Frontend:
  `ProductionCycleDetail.jsx`'e "İcmal Belgesi" kartı (oluştur/durum/
  PDF), `FarmerHome.jsx`'e "İcmal Belgelerim" (PDF+Onayla+İtiraz Et),
  yeni `pages/UfydDashboard.jsx` (route `/ufyd-dashboard`). **Gerçek
  tarayıcıda uçtan uca doğrulandı:** 50 ton A + 30 ton C ile finalize
  edilmiş bir hakedişten İcmal PDF'i üretilip indirildi (2410 bayt,
  geçerli `%PDF-1.3` header); çiftçi portalından PDF görüntülendi ve
  ONAYLANDI; farklı bir sezonda İTİRAZ EDİLDİ akışı test edildi;
  cross-farmer erişim denemesi 403 ile reddedildi; simülasyonda
  unit_price=40 ile brüt 3180 TL hesaplanırken GERÇEK finalize edilmiş
  kaydın (unit_price=25, brüt 1987.5 TL) HİÇ etkilenmediği doğrulandı;
  UFYD Dashboard'da toplam hakediş (2387.5 TL = iki test sezonunun
  toplamı) ve bekleyen ödemeler canlı doğru hesaplandı; ziraat_muhendisi
  kısıtlamaları ve idempotency (aynı sezon için ikinci "İcmal Belgesi
  Oluştur" çağrısı AYNI kaydı döndü, kopya OLUŞMADI) doğrulandı. **Yan
  bulgu:** bu otomasyon ortamında `preview_click`'in bazı düğmelerde DOM
  event'ini React'e iletmediği gözlemlendi (bkz. yukarıdaki Sayfalar
  notu) — gerçek kullanıcı tıklamasını etkilemez. Test verisi (ledger_
  entries/entitlements/reconciliations/test kantar kayıtları) doğrulama
  sonrası temizlendi.
  **FAZ 7 (UFYD) TAMAMEN BİTTİ (IT-18+IT-19+IT-20+IT-21)** — Oturum
  Teslim Protokolü'ne göre bir fazın tüm IT'leri bittiğinde zip alınır.
- ✅ **IT-22 (FAZ 8 başladı — İş Emri / Görev / Ziyaret Üçlü Modeli):**
  Yeni `backend/field_ops.py` — `work_orders`/`field_tasks`/`visits`
  (Sprint 4'ün basit `db.tasks`'ından BİLİNÇLİ AYRI, bkz. dosya haritası
  notu). `task_types` kataloğu (idempotent 12 varsayılan: Çiftçi Ziyareti/
  Toprak Numunesi/Hasat Kontrolü/Ekim Kontrolü/Sulama Kontrolü/Gübreleme
  Kontrolü/İlaçlama Kontrolü/Drone Çekimi/Fotoğraf Çekimi/Evrak Teslimi/
  ÇKS Kontrolü/Denetim) — her tip `default_checklist` taşır, yeni bir
  FieldTask oluşurken bu KOPYALANIR. 11 durumlu SIRALI durum makinesi
  (planlandi→atandi→kabul_edildi/reddedildi→yola_cikildi→yerine_ulasildi→
  calisiliyor→tamamlandi→onay_bekliyor→kapandi, +iptal_edildi her
  aşamadan, reddedildi→planlandi yeniden planlama dalı) — production_
  cycles.py/support.py'nin ALLOWED_TRANSITIONS kalıbıyla AYNI. **KRİTİK
  KURAL:** checklist tamamlanmadan `kapandi`'ya geçiş 400 ile reddedilir.
  Sahiplik modeli (`_check_task_access`) — görevi ÜSTLENEN kullanıcı
  `field_ops:manage` OLMADAN kendi görevini yönetebilir (reconciliation.
  py'nin `_check_reconciliation_access` ile AYNI desen), başkasının
  görevine dokunmak `field_ops:manage` ister. `POST /work-orders`
  parcel_ids × assigned_users ROUND-ROBIN dağıtımıyla toplu FieldTask
  üretir. `permissions.py`'ye yeni `field_ops` modülü (view/manage) —
  ilce_yoneticisi/ziraat_muhendisi tam yetki, saha_personeli/toprak_
  personeli sadece view (kendi görevlerini sahiplik bypass'ıyla
  yönetirler). **Gerçek backend'de curl/PowerShell ile uçtan uca
  doğrulandı:** 2 parsel + 2 personelle bir İş Emri açılıp round-robin
  ile 2 FieldTask (her biri kendi TaskType'ının checklist'iyle) doğru
  üretildiği; bir görev planlandi'dan onay_bekliyor'a kadar TÜM 11
  durumun sırayla çalıştığı; checklist TAMAMLANMADAN kapandi denemesi
  400 ile reddedilip, checklist tamamlandıktan SONRA başarıyla kapandığı;
  kapalı (terminal) durumdan çıkış denemesi 400; skip-ahead (planlandi
  →calisiliyor gibi) 400; saha_personeli (Ayşe Kaya, field_ops:manage
  YOK) KENDİ görevini sahiplik bypass'ıyla başarıyla ilerletirken
  BAŞKASININ (Mehmet Demir'in) görevinin checklist'ini değiştirmeye
  çalışınca 403 aldığı; bir görev için 2 ayrı Visit açılıp (Task-Visit
  1:N) `GET /visits?task_id=...`'nin ikisini de doğru döndürdüğü;
  bağımsız (work_order_id=null) ad-hoc görev oluşturmanın çalıştığı
  doğrulandı. **Kapsam notu:** IT-05→IT-06/IT-20 emsalleriyle tutarlı,
  bu iterasyon BİLİNÇLİ OLARAK sadece backend — IT-23 zaten Kanban/
  Takvim/Harita UI'ını kapsıyor. Test verisi (work_orders/field_tasks/
  visits) doğrulama sonrası temizlendi, `task_types` seed'i (gerçek
  katalog) korundu.
- ✅ **IT-23 (FAZ 8 devam — Kanban + Takvim + Harita Entegrasyonu +
  Ziyaret Geçmişi):** IT-22'nin field_tasks/work_orders/visits modelini
  TÜKETEN ilk UI. Yeni `pages/SahaOperasyonlari.jsx` (route `/saha-
  operasyonlari`, Layout.jsx "SAHA & LOJİSTİK" grubunda "Görev Yönetimi"):
  Kanban (9 sütun — ROADMAP'in 8 görünür grubu + "Sahada" birleşik
  yerine_ulasildi/calisiliyor + ayrı bir "Reddedildi/İptal" sütunu, TÜM
  görevler görünür kalsın diye), native HTML5 sürükle-bırak (yeni
  kütüphane YOK) — bırakma SADECE client-side `ALLOWED_NEXT` tahminiyle
  bir hedef durum ÖNERİR, gerçek doğrulama HER ZAMAN backend'de
  (checklist dahil — kabul kriteri). Basit Takvim (`planned_date`'e göre
  gün gruplu liste, yeni bir takvim kütüphanesi eklenmedi, bilinçli
  sadelik). Görev Detay Drawer (mevcut `Drawer.jsx` — IT-12 — yeniden
  kullanıldı) — checklist toggle + durum geçiş butonları. `?task=<id>`
  query param'ı ile DOĞRUDAN bir görevin drawer'ını açar (haritadan
  "Detaya Git" linki bunu kullanır — kabul kriteri: "görev detayına
  gidilebilmeli"). Yeni `components/VisitHistory.jsx` — farmer_id/
  parcel_id/production_cycle_id filtrelerinden biriyle çağrılır (bkz.
  field_ops.py'nin denormalize ettiği alanlar); `FarmerDetail.jsx`'e
  yeni "Ziyaret Geçmişi" TAB'ı, `ParcelDetail.jsx`'e (tab yapısı yok,
  IT-02 emsaliyle tutarlı) tekil kart olarak, `ProductionCycleDetail.jsx`'e
  Cari Hesap/İcmal'in ALTINA kart olarak eklendi. `HaritaPaneli.jsx`'e
  (IT-15'in LAYER_CATALOG'una) "Saha Görevleri" katmanı — `CircleMarker`
  (yeni import, react-leaflet'te zaten mevcut bir bileşen) her field_
  task'ın PARSEL CENTROID'İNDE, `FIELD_TASK_STATUS_COLOR`'a göre
  renklendirilmiş; popup'ta "Detaya Git" → `/saha-operasyonlari?task=
  <id>`. Parsel popup'ına AYRI bir "+ Saha Görevi" butonu/mini-form
  eklendi (mevcut "+ Görev" — ESKİ operations/tasks — İLE
  KARIŞTIRILMADI, iki ayrı buton yan yana durur) — `task_type_id`/
  `assigned_to` (yeni `GET /field-ops/assignable-users`'tan) / `planned_
  date` ile `POST /tasks` çağırır (kabul kriteri: "parsel seç → görev
  formu → Task kaydı"). **Gerçek tarayıcıda uçtan uca doğrulandı:** 2
  parsel + 2 personelle bir İş Emri açılıp Kanban'da "Planlandı"
  sütununda 2 kart (doğru parsel/personel bilgisiyle) göründüğü; bir
  kartın Drawer'ını açıp "Atandı"ya geçiş butonuna tıklanınca kartın
  gerçekten "Atandı" sütununa taşındığı (backend round-trip + yeniden
  render); Harita Paneli'nde "Katmanlar" panelinden "Saha Görevleri"
  açılınca konsolda hata çıkmadığı ve interactive path sayısının
  737 (parsel)+2 (görev marker'ı)=739'a çıktığı (marker'ların gerçekten
  render olduğunun dolaylı kanıtı) doğrulandı. Test verisi doğrulama
  sonrası temizlendi.
- ✅ **IT-24 (FAZ 8 TAMAMLANDI — Kural Tabanlı Otomatik Görev Oluşturma +
  Saha Raporları + Modül Dashboard'u):** Yeni `backend/event_bus.py` —
  IT-27'de formalize edilecek genel event-driven altyapının TEMEL
  kullanımı, basit süreç-içi (in-process, Redis/RabbitMQ YOK) pub/sub:
  `subscribe(event_type, handler)` + `await publish(db, event_type,
  payload)`. Her `publish` çağrısı `automation_events`'e bir iz kaydı
  bırakır (handler hiç olmasa/hata verse bile) — asıl yayınlayan işlem
  (ör. toprak analizi kaydı) ETKİLENMEZ, otomasyon bir yan etkidir.
  Yeni `backend/automation.py` — `AutomationRule` (event_type + basit
  eşitlik koşulları `[{field,value}, ...]` HEPSİ (AND) + hedef
  `task_type_id` + `assigned_to` + `priority`) admin ekrandan kod
  yazmadan tanımlanır; `register_automation_routes` server.py
  başlangıcında HER `EVENT_TYPES` girdisine AYNI handler'ı bağlar
  (`_handle_automation_event` — hangi kuralın hangi event'e ait olduğu
  DB'den okunur, event_bus.py kural bilmez, bilinçli katman ayrımı).
  Koşul dili BİLİNÇLİ OLARAK sadeleştirilmiş (entitlement.py'nin
  `formul` kesintisindeki override_amount zorunluluğu gibi bir
  sadeleştirme) — tam bir filtre DSL'i (query_engine.py'nin operatör
  kümesi) İSTENMEDİ, event payload'ları küçük/sabit şekilli. Her
  eşleşen kural çalıştığında `automation_rule_runs`'a iz düşülür
  (Modül Dashboard'unun/rules ekranının "Son Otomatik Görev Üretimleri"
  listesi buradan). `field_ops.py`'ye yeni modül seviyesi
  `create_field_task_from_rule()` — `POST /tasks` (create_field_task)
  ile AYNI FieldTask şemasını üretir, event handler'da HTTP request/
  user context'i olmadığı için endpoint'in KENDİSİ değil bu fonksiyon
  çağrılır; `task_type_id` yok/pasifse sessizce None döner (HTTPException
  fırlatamaz). **İKİ gerçek event tetikleyicisi** (kabul kriterinin "en
  az 2 kural" şartı için) uçtan uca bağlandı: `data_entry.py`'nin
  `POST /soil-samples`'ı artık `soil_analysis_completed` event'i
  yayınlıyor (roadmap'in verdiği ÖRNEĞİN AYNISI: "Toprak Analizi
  Tamamlandı" → otomatik "Ekim Kontrolü" görevi); `support.py`'nin
  transition endpoint'i `tamamlandi` durumuna geçişte
  `support_request_completed` yayınlıyor. `field_ops.py`'ye yeni
  `GET /field-ops/dashboard` (Modül Dashboard'u) — `reconciliation.py`'nin
  `ufyd/dashboard`'ı ile AYNI desen (canlı hesaplanır, önceden-toplanmış
  istatistik koleksiyonu YOK): aktif iş emri/görev sayısı, geciken görev
  sayısı (`sla_due_date < now`), bugünkü ziyaret sayısı, personel doluluk
  oranı (aktif görev sayısı/personel), bölgesel operasyon yoğunluğu
  (`parcel.region_id` üzerinden — admin_areas'ın $geoIntersects'i bu
  basit sayım için gereksiz maliyet), ortalama tamamlanma süresi (SADECE
  `kapandi` görevler, created_at→status_updated_at farkı, saat cinsinden).
  `query_engine.py`'ye `field_tasks`/`visits` modülleri eklendi
  (`FIELD_DEFINITIONS_MODULES`'a DAHİL DEĞİL — ikisinin de field_definitions'ı
  yok). `permissions.py`'ye yeni `automation` modülü (`view`/`manage`) —
  ilce_yoneticisi/ziraat_muhendisi tam yetki, saha_personeli/toprak_
  personeli sadece view. Frontend: yeni `pages/AutomationRules.jsx`
  (route `/otomasyon-kurallari`, "SAHA & LOJİSTİK" grubu, "Görev
  Yönetimi"nin hemen altında) — kural CRUD'u (koşul builder'ı FilterPanel'in
  AND koşul satırlarıyla AYNI aile, QuickAddPanel'in düz alan listesine
  SIĞMADIĞI için bilinçli olarak kendi basit satır listesi yazıldı) + Son
  Otomatik Görev Üretimleri listesi. `SahaOperasyonlari.jsx`'e (IT-23'ün
  Kanban/Takvim sayfası) İKİ yeni sekme eklendi (view state'e "dashboard"/
  "raporlar" eklendi — YENİ bir sayfa/route AÇILMADI, UfydDashboard.jsx'in
  ayrı-route emsalinin AKSİNE, çünkü bu sayfa zaten bir view-switcher
  kalıbı kullanıyordu): "Dashboard" (GET /field-ops/dashboard'ın KPI
  kartları, UfydDashboard.jsx'teki KPI bileşeninin AYNI görsel dili) ve
  "Raporlar" (`<SmartDataGrid module="field_tasks" .../>`, satır tıklanınca
  AYNI görev detay Drawer'ı açılır — SmartDataGrid JOIN YAPMAZ, bu yüzden
  farmer_id/parcel_id/assigned_to gibi alanlar HAM UUID görünür, diğer
  modüllerdeki SmartDataGrid kullanımlarıyla TUTARLI bilinçli bir sınırlama).
  **Gerçek tarayıcıda uçtan uca doğrulandı:** "Toprak Analizi Tamamlandı"
  → "Ekim Kontrolü" (Mehmet Demir'e atanan) kuralı UI'dan oluşturuldu;
  gerçek bir `POST /soil-samples` çağrısı yapıldı; `automation_rule_runs`
  kaydının `status:"created"` ile doğru oluştuğu, YENİ bir FieldTask'ın
  gerçekten `field_tasks` koleksiyonuna yazıldığı (round-robin/work-order
  OLMADAN, doğrudan otomasyon motorundan) doğrulandı; `GET /field-ops/
  dashboard`'ın `active_tasks:1`, `staff_utilization:[Mehmet Demir, 1]`,
  `regional_density` doğru güncellediği hem API hem SahaOperasyonlari.jsx
  "Dashboard" sekmesinde (KPI kartları + iki liste) gözlemlendi; "Raporlar"
  sekmesinde SmartDataGrid'in bu görevi 1 kayıt olarak listelediği ve
  Query Engine filtre satırının (`filtrele…`) göründüğü doğrulandı;
  Otomasyon Kuralları ekranındaki "Son Otomatik Görev Üretimleri"
  listesinin "GÖREV OLUŞTURULDU" rozetiyle doğru göründüğü doğrulandı.
  Test verisi (soil_sample/field_task/automation_rule/rule_run/
  automation_event) doğrulama sonrası doğrudan MongoDB'den temizlendi
  (bu koleksiyonların hiçbirinde bir DELETE endpoint'i yok — convention
  #3 "soft delete" ile tutarlı, ama test verisi temizliği için bu
  iterasyonda ilk kez API yerine doğrudan Mongo'ya elle silme kullanıldı,
  önceki iterasyonlardaki "test verisi temizlendi" notlarıyla AYNI amaç).
  **FAZ 8 (Saha Operasyonları) TAMAMEN BİTTİ (IT-22+IT-23+IT-24)** —
  Oturum Teslim Protokolü'ne göre bir fazın tüm IT'leri bittiğinde zip
  alınır.
- ⏭️ Sıradaki iş: `ROADMAP-DETAY-FAZ7-12.md` (veya güncel roadmap dosyası)
  → FAZ 9 (Sprint 9 — Communication Hub), IT-25'ten başlayarak.

## 7. Çalıştırma

```bash
# Backend
cd backend && pip install -r requirements.txt --break-system-packages
uvicorn server:app --reload            # .env: MONGO_URL, DB_NAME gerekli

# Frontend
cd frontend && npm install && npm start   # veya yarn

# Seed
POST /api/admin/seed  (demo veri)
POST /api/field-definitions/seed-farmers-pilot  (A1 çiftçi alanları)
```

## 8. Oturum Teslim Protokolü

Her iterasyon (oturum) sonunda:
1. Değişen tüm dosyalar `python3 -m py_compile` / `esbuild` ile doğrulanır.
2. `git commit` atılır.
3. Bu dosyanın (CLAUDE.md) "Mevcut Durum" bölümü ve ROADMAP.md'deki
   durum panosu güncellenir.
4. Değişen dosyalar, mimari kararlar ve bilinçli kapsam dışı bırakılanlar
   kısa bir tabloyla raporlanır.

**Zip paketleme artık her iterasyonda YAPILMAZ.** Zip sadece bir **faz**
tamamen bittiğinde (o fazdaki tüm IT'ler ✅ olduğunda) alınır: `__pycache__`
temizlenir, proje `dijital-tarim-<faz-id>.zip` olarak paketlenir ve kullanıcıya
sunulur.

## 9. Oturum Notu — 2026-07-11 (IT-42/43/46 uygulandı)

- **IT-42/IT-43 (FAZ 15 — Organizasyon Hiyerarşisi + Onay Zincirleri):**
  `backend/organization.py` (OrganizationUnit/Position/UserPosition + org-chart
  + manager-chain resolver) ve `backend/approval.py` (çok adımlı, role/
  hierarchy/user hedefli Onay Zinciri Motoru) eklendi. `support.py`
  ("onaylandi" geçişi) ve `campaigns.py` (`/campaigns/{id}/approve`) bu ortak
  motoru KULLANACAK şekilde güncellendi — bir tenant için ilgili `process`
  için aktif kural TANIMLI DEĞİLSE eski doğrudan davranış AYNEN çalışır
  (geriye uyumlu). Frontend: `OrganizationChart.jsx`, `PendingApprovals.jsx`.
- **IT-46 (FAZ 17 — Bize Ulaşın / IT-28 Case Yönetimi):** `backend/
  case_management.py` — Case + CaseCategory + CaseMessage, dallanabilen durum
  makinesi, atama (onay motoruna opsiyonel bağlı), `field_ops.
  create_field_task_from_rule()` üzerinden Saha görevi köprüsü, çiftçi portalı
  uçları. `communications.py`'nin `/contacts/{id}/timeline`'ı case kayıtlarını
  da (kronolojik karışık) döndürecek şekilde güncellendi. Frontend:
  `CaseManagement.jsx`.
- **Bilinen borç (bu oturumda YAPILMADI):** IT-46'nın "Hata Bildirimi
  kategorisine otomatik platform_admin ataması" kuralı henüz eklenmedi —
  şu an her case manuel atanıyor. Menü konsolidasyonu (IT-13b/IT-40/IT-41,
  Genel Tasarım Kuralları Kural 1-3) ve harita/dashboard click-through/
  NetCAD/gerçek uydu entegrasyonu bu oturumun kapsamı DIŞINDA — kullanıcı
  ile sıradaki oturum için planlandı.
- **Doğrulama:** `server.py` gerçek bir Python ortamında (fastapi/motor/
  pydantic kurulu) import edilip 264 route'un çakışmasız kaydolduğu
  doğrulandı; yeni/değişen 3 frontend sayfası + `App.js`/`Layout.jsx`
  esbuild ile sözdizimi doğrulamasından geçirildi.

## 10. Oturum Notu — 2026-07-11 (devam) — Uydu Sağlayıcı Araştırması + Provider Katmanı

- Kullanıcı için ayrı bir araştırma raporu üretildi:
  `TABSIS_Uydu_Goruntu_Ekosistemi_Arastirma.md` (proje kök dizininde) — 18+
  uydu/EO sağlayıcısının (Copernicus/Sentinel Hub, Landsat, Planet, Maxar,
  Airbus, BlackSky, ICEYE, Capella, EOSDA, UP42, SkyFi, Satellogic/EarthDaily,
  OneSoil, Microsoft Planetary Computer, Google Earth Engine, NASA
  AppEEARS/FIRMS/POWER, OpenAerialMap, Agromonitoring) karşılaştırması +
  mimari öneri + çoklu-sağlayıcı stratejisi + sıralama.
- **`satellite_provider.py` tamamen yeniden yazıldı** (IT-28.1'in provider
  katmanı kısmı — 🔄, tam kapsam değil): `SatelliteProvider` ABC + üç GERÇEK
  sağlayıcı (`SentinelHubProvider` — OAuth2 + Statistics API NDVI,
  `NasaFirmsProvider` — ücretsiz yangın alarmı, `Up42Provider` — VHR tasking
  talebi kimlik doğrulama) + `DemoSatelliteProvider` (mevcut, değişmedi).
  `get_satellite_provider(db, capability)` artık ASYNC — Integration Center'da
  (`db.integrations`, tip: `sentinel_hub`/`nasa_firms`/`up42`) kayıtlı
  `mock_mode` kapatılmadan/anahtar girilmeden HER ZAMAN Demo'ya düşer
  (planet_labs ile AYNI kalıp — hiçbir mevcut davranış bozulmadı).
- `integrations.py`: 3 yeni entegrasyon tipi (`sentinel_hub`, `nasa_firms`,
  `up42`) + probe fonksiyonları + `/test` uçları eklendi.
- `extras.py`: `/satellite/ndvi/*` uçları artık `await get_satellite_provider
  (db, "ndvi")` kullanıyor, geometri bulunamazsa/gerçek sağlayıcı geçici
  hata verirse SESSİZCE Demo'ya düşer (kullanıcı ekranı hiç kırılmaz).
- `satellite_provider.py` kendi `register_satellite_routes`'unu kazandı:
  `/satellite/fire-alerts/{parcel_id}`, `/satellite/tasking-request`,
  `/satellite/providers/status`.
- Frontend: `Extras.jsx`'teki Entegrasyonlar ekranına 3 yeni kart (Sentinel
  Hub, NASA FIRMS, UP42) eklendi — Planet Labs kartıyla AYNI mock_mode deseni.
- **Bilinen borç / bu oturumda YAPILMAYAN (IT-28.1'in geri kalanı):**
  Periyodik/otomatik görüntü alım işi (ingestion background job),
  `parcel_index_series` koleksiyonu, bulutlu kare eleme otomasyonu, gerçek
  COG/STAC tabanlı harita tile katmanı — bunlar sıradaki "harita komple
  yenileme" fazının kapsamında ele alınacak.
- **Doğrulama:** `server.py` yine gerçek ortamda import edildi (270 route,
  çakışmasız); `Extras.jsx` esbuild ile sözdizimi doğrulamasından geçti.
