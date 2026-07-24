# Toprax — Değişiklik Günlüğü

Bu dosya [Keep a Changelog](https://keepachangelog.com/tr/1.0.0/) ruhuyla tutulur.

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
