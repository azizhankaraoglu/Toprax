# Toprax — Değişiklik Günlüğü

Bu dosya [Keep a Changelog](https://keepachangelog.com/tr/1.0.0/) ruhuyla tutulur.

## [Yayınlanmamış] — Faz 3: MERNİS + TAKBİS Entegrasyonları (2026-07-24, Build 24072026-1800)

### Eklendi
- Yeni `backend/gov_providers.py` — `satellite_provider.py`/`channel_providers.py`
  ile aynı ABC+factory kalıbı: `IdentityProvider` (MERNİS/KPS) +
  `CadastreProvider` (TAKBİS). `validate_tc_checksum()` gerçek TC Kimlik No
  algoritmasıyla (resmi 11-hane formülü) doğrulama yapar. `DemoMernisProvider`/
  `DemoTakbisProvider` CRC32-tohumlu deterministik demo veri üretir
  (`DemoSatelliteProvider` ile aynı teknik); `RealMernisProvider` KPS
  `TCKimlikNoDogrula` SOAP 1.1 zarfını elle kurar (`zeep` bağımlılığı
  eklenmedi), `RealTakbisProvider` kurumsal REST/SOAP servisine bağlanır.
  Gerçek sağlayıcılar sadece kimlik bilgisi (`username`/`password`/
  `service_url`) girilip `mock_mode` kapatılınca devreye girer — mevcut
  eosda/sentinel_hub mock-capable deseniyle birebir.
- `integrations.py`: `SECRET_FIELDS`/`MOCK_CAPABLE_TYPES`'a `mernis`/`takbis`
  eklendi; `_has_credentials`, yıkıcı olmayan health probe'ları
  (`_probe_mernis`/`_probe_takbis`) ve `/integrations/{mernis,takbis}/test`
  uçları eklendi — mevcut Ayarlar > Entegrasyonlar akışıyla (maskeleme,
  demo→aktif otomatik geçiş, health-check) tam uyumlu.
- `platform_core.py FEATURE_FLAG_LABELS`'a `mernis`/`takbis` eklendi — God
  Mode'un modül aç/kapa listesi (`MODULE_TOGGLE_LABELS = FEATURE_FLAG_LABELS`
  referansı sayesinde) otomatik olarak bu iki modülü de kapsıyor.
- Yeni `backend/gov_integration_routes.py` — `POST /gov/mernis/verify`
  (`farmers:edit` + feature `mernis`; `farmer_id` verilirse başarılı
  doğrulamada `Farmer.mernis_verified`/`mernis_verified_at` yazar + audit),
  `POST /gov/takbis/query` (`parcels:edit` + feature `takbis`; sadece
  sorgu sonucunu döner, kaydetme çağıranın işi — `geo_import.py`'nin
  "ayrıştırır ama kaydetmez" felsefesiyle aynı ayrım).
- Frontend: `FarmerDetail.jsx`'e TC alanının yanına "MERNİS ile Doğrula"
  mini-formu (doğum yılı + doğrula) + başarılı doğrulamada yeşil "✓ MERNİS
  Doğrulandı" rozeti; `ParcelDetail.jsx`'in düzenleme moduna "TAKBİS Tapu
  Sorgu" kutusu (il/ilçe/ada/parsel → malik/nitelik/alan/tapu tarihi
  gösterimi + `il`/`ilce`/`ada_no`/`parsel_no_tapu`/`area_dekar` alanlarını
  otomatik doldurur, kullanıcı gözden geçirip Kaydet'e basar); `Extras.jsx`
  AyarlarEntegrasyon'a MERNİS + TAKBİS kimlik kartları (eosda kartıyla aynı
  düzen: kullanıcı adı/şifre/servis URL'i + demo mod checkbox'ı + Test Et).

### Doğrulama
- Backend: `py_compile` + pyflakes (0 undefined name) + 47 pytest yeşil.
- Gerçek TC checksum algoritması bilinen geçerli/geçersiz TC no'larla
  doğrulandı; demo sağlayıcıların deterministik olduğu (aynı girdi → aynı
  çıktı) doğrulandı.
- **Canlı mongo'ya bağlı boot ile uçtan uca:** `/gov/mernis/verify` gerçek
  bir çiftçiye `farmer_id` ile çağrıldı — `mernis_verified:true` +
  `mernis_verified_at` DB'ye yazıldığı `GET /farmers/{id}` ile ve audit
  log'daki old/new değerleriyle doğrulandı; geçersiz checksum'lı TC no
  `verified:false` ile reddedildi. `/gov/takbis/query` gerçek bir
  il/ilçe/ada/parsel ile çağrılıp tutarlı (deterministik) tapu verisi
  döndürdüğü doğrulandı. `PUT /integrations/mernis` ve `/takbis` ile
  kimlik bilgisi kaydedilip `mock_mode` açıkken DEMO, kapatılınca gerçek
  kimlik bilgisiyle otomatik AKTİF'e geçtiği (`active`/`is_demo` alanları)
  doğrulandı; `/health` ve `/test` uçları mock modda başarıyla çalıştı.
  Test verisi (mernis/takbis config'leri) doğrulama sonrası boşaltıldı.

## [Yayınlanmamış] — Denetim Düzeltmeleri Faz 2 (2026-07-24, Build 24072026-1600)

### Değişti (A6 — server.py modülerleştirme)
- `server.py` **3273 → 684 satır**. Endpoint blokları BİREBİR (davranış
  değişikliği YOK) 6 yeni modüle taşındı, `register_X_routes(...)` konvansiyonu
  ve **route kayıt sırası korunarak** (register çağrısı bloğun orijinal
  konumundan yapılır — Starlette route-order tuzağı):
  - `auth_routes.py` (login/refresh/me/public-contact)
  - `farmer_routes.py` (/farmer/* portalı + Çiftçi CRUD)
  - `parcel_routes.py` (Parsel CRUD + geo işlemler + import)
  - `dashboard_routes.py` (dashboard/bildirim/bölge/lojistik/karne)
  - `listing_routes.py` (toprak/sözleşme/ekim/sulama/operasyon/analitik listeleri)
  - `seed_routes.py` (/admin/seed + /, /health, /roles)
- Doğrulama: `py_compile` + `import server` (509 route) + pyflakes (0 undefined
  name) + 47 pytest yeşil + **gerçek mongo'ya bağlı canlı boot** ile taşınan her
  modülden temsili endpoint'lerin gerçekten çalıştığı (login → /farmers arama +
  detay + mask, /parcels detay, /dashboard/overview, /regions cache) 200/403 ile
  teyit edildi.

### Düzeltildi (A3 regresyonu — canlı boot'ta yakalandı)
- `server.py current_user`: kullanıcı DB araması `db.users` (tenant-scoped) →
  `raw_db.users`. Faz 0'daki fail-closed değişikliği, tenant_id=None taşıyan
  platform_admin hesabının kullanıcı kaydını bulamamasına ve HER authenticated
  isteğin 401'e düşmesine yol açıyordu. Kimlik JWT ile imzalı user_id'den
  çekildiği için çapraz-tenant sızıntı yok; asıl veri sorguları hâlâ scoped
  `db`'den geçer. **Bu regresyon yalnız gerçek boot + curl ile görülebilirdi;
  unit testler yakalamadı.**

## [Yayınlanmamış] — Denetim Düzeltmeleri Faz 1 (2026-07-24, Build 24072026-1400)

### Eklendi
- **A8 Sunucu tarafı şekille seçim**: yeni `POST /parcels/select-by-geometry`
  (`$geoIntersects`, `/parcels/{parcel_id}`'den önce tanımlı);
  `HaritaPaneli.jsx` "Şekille Seç" artık Turf.js tarayıcı taraması yerine bu
  ucu kullanır (1000+ parselde donma giderildi; sunucu hatasında eski
  yönteme sessiz geri dönüş).
- **A9 Topoloji doğrulaması**: yeni `backend/geo_validation.py` (saf Python
  self-intersection/halka kontrolü, shapely bağımlılığı YOK) — parsel
  create/update/split/import-geojson uçlarında 400; `Parcels.jsx` çiziminde
  `turf.kinks` ile erken uyarı.
- **A10 Görev erteleme**: `field_ops.py` yeni `ertelendi` durumu — saha
  aşamalarından geçilebilir, checklist zorunluluğundan muaf (yalnız `kapandi`
  ister), `ertelendi → planlandi` yeniden planlama; kanban'a "Ertelendi"
  sütunu; `SahaOperasyonlari.jsx` + `MobilDashboard.jsx` ALLOWED_NEXT senkron.
- **A12 Kantar hızlı giriş**: Kantar Kayıtları'na klavye-öncelikli "Hızlı
  Giriş" formu (Enter alan geçişi, Ctrl+Enter/F2 kayıt, kayıt sonrası odak
  başa) + `docs/kantar-rs232-kopru.md` (RS232 keyboard-wedge köprü kılavuzu,
  pyserial örneğiyle).
- **A14 Gerçek iletişim sağlayıcıları**: `channel_providers.py`'ye
  `RealSmsProvider` (Netgsm/Twilio/webhook — integrations._probe_sms_send
  yeniden kullanımı) + `SmtpEmailProvider`; yeni async
  `get_channel_provider_for(db, channel)` factory'si entegrasyon kaydı
  etkin+dolu ise gerçek, değilse simüle döner; `communications.
  send_via_channel` bu factory'ye geçti (KVKK gate değişmedi).
- **A15 Test seti**: `tests/test_audit_fixes_faz1.py` (12 test — A9 topoloji,
  A10 geçiş kuralları, A11 düzeltme işareti). Toplam 47 test yeşil.

### Düzeltildi
- **A7 (STAB-B1)**: `/admin-areas/bulk-import` Point/LineString kayıtları
  artık sessizce atlamaz — tip başına sayılıp Türkçe `warnings[]` döner,
  `AdminAreaManagement.jsx` gösterir.
- **A11 Ledger düzeltme takibi**: `POST /ledger/{id}/reverse` bağlı kaynak
  belgeyi (`support_request`/`entitlement`/`reconciliation`/`einvoice`)
  `correction_status: "Düzeltildi"` ile işaretler (belgenin kendi durum
  makinesine dokunmaz) + audit; `ProductionCycleDetail.jsx` rozet gösterir.
- **A13 KPI drill-down**: Dashboard'da hedefsiz 4 kart bağlandı
  (Hedef Hasat/Gerçekleşen → /verimlilik vb.); `UfydDashboard.jsx` KPI
  bileşenine `to` desteği eklendi (global liste sayfası olmayan finans
  kartları bilinçli olarak tıklamasız bırakıldı).

## [Yayınlanmamış] — Denetim Düzeltmeleri Faz 0 (2026-07-24, Build 24072026-1200)

### Güvenlik
- **A3 Tenant izolasyonu FAIL-CLOSED** (`tenant_context.py`): `current_tenant_id`
  None iken artık filtre atlanmıyor — `{"tenant_id": "__UNAUTHORIZED__"}`
  sentinel'i enjekte edilir, bağlamsız sorgu HER ZAMAN boş döner. Meşru
  bağlamsız yollar `raw_db`'ye taşındı: login e-posta araması + SHA256→bcrypt
  rehash (`server.py`), `/auth/refresh` kullanıcı sorgusu (+ token-tenant
  eşleşme ve aktiflik kontrolü eklendi), `storage.py` `?token=` dosya indirme
  yetkilendirmesi, `remote_sensing/services.py` görüntü sunumu. Aggregate
  pipeline'ları da fail-closed. Yeni `tests/test_tenant_fail_closed.py` (6 test).
- **API key isteklerinde tenant bağlamı** (`server.py current_user`):
  middleware yalnız JWT çözdüğü için `toprax_key_` isteklerinde bağlam boş
  kalıyordu — makine anahtarı TÜM tenant'ların verisini okuyabiliyordu.
  Bağlam artık anahtarın tenant'ıyla kurulur.

### Düzeltildi
- **A1 Impersonation redirect loop**: `god_mode.py /god-mode/tenants/{id}/enter`
  artık gerçek bir `refresh_token` da döner; `PlatformAdmin.jsx` boş string
  yerine bunu saklar; `api.js` refresh yanıtında dönebilecek yeni refresh
  token'ı persist eder. "Kooperatif olarak gir" sonrası sayfa geçişlerinde
  login'e fırlatılma sorunu giderildi.
- **A2 Saved Queries `title`/`name`**: kod düzeyinde doğrulandı —
  `FilterPanel.jsx` zaten `name` gönderiyor, `saved_queries.py` `name`
  bekliyor; denetim raporundaki uyumsuzluk daha önce kapatılmış. Değişiklik yok.
- **H/UI Bildirim çekmecesi**: başlıklar `truncate` yerine `line-clamp-2`
  ile 2 satıra sarılır (`WorkspaceDrawer.jsx`).
- **H/UI Ekim Planlama Karar Motoru**: sayfanın kullandığı `.page/.tabs/.tab/
  .table/.muted/.page-header` sınıfları CSS'te hiç tanımlı değildi — tablolar
  stilsiz render olup metinler üst üste biniyordu; `index.css`'e mevcut
  tasarım diliyle tanımlandı.

### Eklendi
- **A4 Bileşik indeksler** (`server.py` startup): 14 koleksiyona
  `(tenant_id, created_at)`, durum makineli 6 koleksiyona `(tenant_id, status)`,
  çiftçi-çocuk 7 koleksiyona `(tenant_id, farmer_id)` isimli idempotent indeks.
- **A5 Yetim kayıt koruması** (`server.py delete_farmer`): aktif üretim
  sezonu varken çiftçi silinemez (409, parsel/sözleşme guard'ına ek);
  silinen çiftçinin bağlı kayıtları `farmer_inactive: true` ile işaretlenir
  (kendi durum alanlarına dokunulmaz) + koleksiyon başına audit.

## [Yayınlanmamış] — FAZ 18: Agricultural Intelligence Engine (IT-47..53)

### Eklendi
- **IT-47** AI Knowledge Library çekirdeği — `ai_datasets` / `ai_knowledge_records` /
  `ai_taxonomy` koleksiyonları, versiyonlama (`previous_version_id`, ledger silinmezlik
  deseni), toplu import, annotation, onay iş akışı, 20+ örnek taksonomi seed'i
  (`backend/ai_engine.py`).
- **IT-48** Yerel AI pipeline + Confidence Engine — kural motoru → simüle yerel model →
  çoklu-model konsensüsü (çelişki güveni düşürür) → karar; SAF FONKSİYONLAR (birim-test
  edilebilir); atomik `find_one_and_update` job claim + in-process async worker.
- **IT-49** Bulut escalation + tenant AI kotası — `ai_tenant_quota` atomik `$inc`,
  zorunlu redaksiyon filtresi (çiftçi kimlik alanları buluta gitmez), kota dolunca sessiz
  hata YOK (`low_confidence_no_cloud_budget`).
- **IT-50** Active Learning — `ai_active_learning_queue` + `case_management.py` köprüsü
  (`category="AI Doğrulama"` Case), uzman kararı knowledge_record'a `source="hibrit"` yeni
  versiyon yazar (golden dataset).
- **IT-51** MLOps model registry — `ai_models` durum makinesi, golden dataset regresyon
  kapısı (yeni F1 < production F1 → deploy reddi), `previous_model_id` rollback, Health
  Center'a "AI Model Sağlığı" satırı (`platform_core.py`).
- **IT-53** Menü/RBAC konsolidasyonu — `permissions.py` PERMISSION_CATALOG'a `ai_engine`
  modülü (ai_knowledge/ai_model/ai_prediction:*), Query Engine'e `ai_knowledge_records`,
  Ayarlar altında tek "AI Bilgi Kütüphanesi" ekranı (4 sekme, `AiKnowledgeLibrary.jsx`).
- Not: GodMode (FAZ 16) ve açılış popup/duyuru bildirimleri bu çalışmada KORUNDU, dokunulmadı.

## [2.1.0] — On-Premise Ürünleştirme (ROADMAP-URUNLESTIRME.md)

### Eklendi
- **PR-01** Multi-stage Docker paketleme, healthcheck'ler, `/api/health`.
- **PR-02** Web tabanlı kurulum sihirbazı (`/kurulum`) — tenant + süper admin + SMTP + lisans, self-lock.
- **PR-03** Kurulum ön-koşul kontrolcüsü (`scripts/check-requirements.sh`).
- **PR-04** Versiyonlu migration runner + otomatik rollback (`migrations_engine.py`, `upgrade.sh`).
- **PR-05** Offline/air-gapped kurulum paketi (`build-offline-bundle.sh`, `install-from-bundle.sh`).
- **PR-06** TLS/sertifika otomasyonu (Let's Encrypt + certbot otomatik yenileme).
- **PR-07** Kurulum sonrası smoke test (`scripts/smoke-test.sh`).
- **PR-08** Kapsamlı IT admin kurulum kılavuzu (`docs/KURULUM-KILAVUZU.md`).
- **PR-22** Versiyonlu, standart zarflı API yüzeyi (`/api/v1/*`), mevcut `/api/*` değişmeden korundu.
- **PR-23** Generic CRUD + Soft-Delete base class (`crud_base.py`) — yeni modüller için.
- **PR-24** Tenant'a bağlı, scope'lu, rate limitli API Key mekanizması (`api_keys.py`).
- **PR-25** OpenAPI'den otomatik Postman/Insomnia collection üretimi.
- **PR-26** Geliştirici Portalı (Swagger, Postman indirme, API Key yönetimi, changelog).

### Önceki oturum (bu sürümden hemen önce)
- Organizasyon Hiyerarşisi + Onay Zinciri Motoru + Case Management (IT-42/43/46).
- Uydu görüntü sağlayıcı mimarisi (Sentinel Hub, NASA FIRMS, UP42, Demo fallback).

## [2.0.0]

- Rebranding, bcrypt, refresh token, rol hiyerarşisi, merkezi audit log, Entegrasyonlar modülü.
