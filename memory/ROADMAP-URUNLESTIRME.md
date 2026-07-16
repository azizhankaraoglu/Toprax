# ROADMAP-ÜRÜNLEŞTİRME.md — TOPRAX'i On-Premise Satılabilir Ürüne Dönüştürme

> ROADMAP.md ve ROADMAP-DETAY-TAM.md ile aynı format: kullanıcı bir **PR-XX**
> kodu verir, Claude Code o iterasyonu tek oturumda tamamlar. Fark: buradaki
> her iterasyon **"Claude Code Yapar"** ve **"Sizin Yapmanız Gerekir"** olarak
> ikiye ayrılmıştır. Genel prensip: **kod/script/config/doküman taslağı ne
> kadar otomatikleştirilebiliyorsa Claude Code yazar; hesap açma, gerçek
> sunucuya erişim, imza/onay, iş kararı gerektiren adımlar size kalır.**
>
> **Öncelik sıranız (siz belirttiniz):** on-premise kurulumun sorunsuz/kolay/
> profesyonel olması en kritik nokta — bu yüzden FAZ P0 diğer her şeyden önce
> gelir, hatta bazı sertleştirme (FAZ P1) maddelerinden bile önce ele alınabilir
> çünkü kurulum deneyimi kötüyse pilot müşteri kaybedersiniz.

---

## Sizin Üzerinize Kalan İşin Özeti (tek bakışta)

Aşağıdaki roadmap'te ~26 iterasyon var. Bunların büyük çoğunluğunda sizin
payınıza düşen iş **"gerçek ortamda çalıştır ve doğrula"** veya **"bir hesap
aç / bir karar ver"** — kod yazmak değil. Gerçekten sizin yapmanız gereken
(başka kimsenin yapamayacağı) tek tük şey şunlar:
- 3. parti hesap açma (Sentry/uptime servisi, sertifika otoritesi vb.)
- Hukuki metinlerin bir avukata onaylatılması (taslağı Claude Code yazar)
- Pentest firması seçimi ve sonucun değerlendirilmesi
- Pilot müşteri bulma/görüşme/fiyat kararı (iş kararı, otomatikleştirilemez)
- Gerçek prod sunucusunda kurulum scriptini ilk kez çalıştırmak (script hazır, tuşa siz basarsınız)

Gerisi — Docker paketleme, kurulum sihirbazı, testler, CI/CD, yedekleme
scripti, dokümantasyon taslağı, demo veri, tenant provisioning — Claude Code
tarafından uçtan uca yazılabilir.

---

## FAZ P0 — On-Premise Kurulum Paketleme (ÖNCELİK)

### PR-01 — Dockerization + docker-compose

**Kapsam:** Tüm servisler (API, Worker, Mongo, Nginx reverse proxy, gerekirse Redis) tek `docker-compose.yml` ile ayağa kalkacak şekilde paketlenir. Multi-stage Dockerfile'lar (küçük imaj boyutu), `.env.example` üzerinden config (IT-01 ile uyumlu).

**Claude Code Yapar:** Dockerfile'lar, docker-compose.yml (dev/prod ayrı profil), `.dockerignore`, imaj boyutu optimizasyonu, container health-check tanımları.

**Sizin Yapmanız Gerekir:** `docker-compose up` komutunu gerçek bir test sunucusunda (veya kendi makinenizde) çalıştırıp gerçekten ayağa kalktığını gözle doğrulamak — Claude Code'un container'ı sizin ortamınızda test etme imkanı yok.

**Bağımlılık:** — · **Kabul Kriterleri:** Sıfır elle adım olmadan `docker-compose up -d` sonrası tüm servisler `healthy` durumda; API `/health` endpoint'i 200 dönüyor.

---

### PR-02 — Kurulum Sihirbazı (Web-Based Setup Wizard)

**Kapsam:** İlk `docker-compose up` sonrası tarayıcıdan açılan, kod bilmeyen bir IT admininin dolduracağı sihirbaz: DB bağlantısı doğrulama, ilk tenant + ilk Super Admin oluşturma, SMTP/temel entegrasyon ayarları, lisans anahtarı girişi. Bu, `config_service.py`'nin (IT-01) kullanıcı dostu ön yüzüdür.

**Claude Code Yapar:** Sihirbaz ekranları (React), adım adım doğrulama, hatalı girişte anlaşılır Türkçe hata mesajları, sihirbaz tamamlanınca kendini kilitleme (tekrar çalıştırılamaz, güvenlik).

**Sizin Yapmanız Gerekir:** Sihirbazı gerçek bir "sıfırdan kurulum" senaryosunda uçtan uca kendiniz doldurup akışın gerçekten sezgisel olduğunu onaylamak (bu bir UX doğrulaması, kod yazmıyorsunuz).

**Bağımlılık:** PR-01, IT-01, IT-07 · **Kabul Kriterleri:** Teknik bilgisi sınırlı biri (kendinizi o yerine koyarak test edin) hiç terminal açmadan sihirbazı tamamlayıp sisteme giriş yapabiliyor.

---

### PR-03 — Kurulum Öncesi Sistem Gereksinimleri Kontrolcüsü

**Kapsam:** Kurulumdan önce çalıştırılan bir script/sayfa: RAM/disk/CPU, Docker versiyonu, gerekli portların boş olup olmadığını kontrol eder, eksikse net talimat verir ("Docker 24+ gerekli, şu an 20 kurulu").

**Claude Code Yapar:** Kontrol scripti + kurulum sihirbazının ilk ekranı olarak entegrasyonu.

**Sizin Yapmanız Gerekir:** Minimum donanım gereksinimlerini belirlemek (kaç kullanıcı/tenant için ne kadar RAM — bu bir iş/kapasite kararı, Claude Code tahmin verebilir ama nihai rakamı siz onaylarsınız).

**Bağımlılık:** PR-01 · **Kabul Kriterleri:** Eksik bir gereksinimde kurulum sihirbazı bir adım öteye geçmiyor, sorunu net söylüyor.

---

### PR-04 — Migration Runner + Sürüm Yükseltme/Geri Alma Mekanizması

**Kapsam:** Yeni bir sürüm geldiğinde (`docker-compose pull` + tek komut) veritabanı migration'ları otomatik ve sırayla çalışır; hata olursa **otomatik rollback**. Versiyon numarası UI'da görünür (Health Center / GodMode).

**Claude Code Yapar:** Migration framework kurulumu, versiyon takip tablosu, rollback script'i, upgrade script'i (`./upgrade.sh`).

**Sizin Yapmanız Gerekir:** İlk gerçek upgrade'i staging'de deneyip (bkz. PR-11 yedekleme ile birlikte) güvendiğinizde prod'da çalıştırmak.

**Bağımlılık:** PR-01 · **Kabul Kriterleri:** Kasıtlı olarak bozulan bir migration'da sistem otomatik eski sürüme dönüyor, veri kaybı olmuyor.

---

### PR-05 — Offline/Air-Gapped Kurulum Paketi

**Kapsam:** ROADMAP.md'nin "On-Premise Kurulum Standardı" kararıyla uyumlu — müşteri ortamı internete kapalı olabilir (docx'teki Integration Hub kararı gereği zaten dış bağlantı sınırlı). Tüm Docker imajları + npm/pip bağımlılıkları önceden indirilip tek bir `.tar` bundle'a paketlenir, internetsiz sunucuda `docker load` ile kurulabilir.

**Claude Code Yapar:** Bundle oluşturma scripti (`build-offline-bundle.sh`), bundle'dan kurulum scripti, boyut optimizasyonu.

**Sizin Yapmanız Gerekir:** Bundle'ı gerçekten internetsiz bir makinede (örn. VM'de internet kartını kapatıp) test etmek — Claude Code'un böyle izole bir ortamı yok.

**Bağımlılık:** PR-01 · **Kabul Kriterleri:** İnternet bağlantısı olmayan bir VM'de bundle'dan kurulum eksiksiz tamamlanıyor.

---

### PR-06 — TLS/Sertifika Otomasyonu

**Kapsam:** Nginx reverse proxy önünde HTTPS. İnternete açık kurulumlarda Let's Encrypt otomatik yenileme; tamamen kapalı (air-gapped) kurulumlarda müşterinin kendi sertifikasını yükleyeceği net bir adım.

**Claude Code Yapar:** certbot entegrasyonu + otomatik yenileme cron'u, manuel sertifika yükleme için doküman + config şablonu.

**Sizin Yapmanız Gerekir:** Gerçek bir domain üzerinde Let's Encrypt akışını uçtan uca test etmek (domain sahipliği/DNS gerektirir, sizin elinizde bir şey).

**Bağımlılık:** PR-01 · **Kabul Kriterleri:** Sertifika süresi dolmadan otomatik yenileniyor; manuel sertifika senaryosu dokümanla eksiksiz takip edilebiliyor.

---

### PR-07 — Kurulum Sonrası Health-Check + Smoke Test

**Kapsam:** Kurulum bittiğinde otomatik çalışan bir script: tüm servisler ayakta mı, DB bağlantısı var mı, ilk API çağrısı başarılı mı, kritik endpoint'ler (login, health) yanıt veriyor mu — "kurulum başarılı ✅" veya "şurada sorun var ❌" net raporu.

**Claude Code Yapar:** Smoke test script'i, kurulum sihirbazının son adımı olarak otomatik çalıştırma.

**Sizin Yapmanız Gerekir:** Yok — bu tamamen otomatik, sizin doğrulamanız sadece raporu okumak.

**Bağımlılık:** PR-02 · **Kabul Kriterleri:** Kasıtlı olarak bozuk bir kurulumda (örn. yanlış DB şifresi) script sorunu doğru tespit edip raporluyor.

---

### PR-08 — Kurulum Dokümantasyonu (IT Admin Seviyesi)

**Kapsam:** Müşteri tarafındaki IT ekibinin hiç sizinle konuşmadan kurulumu tamamlayabileceği adım adım kılavuz: gereksinimler, indirme, `docker-compose up`, sihirbaz, sorun giderme (SSS).

**Claude Code Yapar:** Dokümanın tamamı (Markdown/PDF, docx skill ile profesyonel formatta), sorun giderme bölümü (yaygın hatalar + çözümleri).

**Sizin Yapmanız Gerekir:** Gerçek ekran görüntülerini eklemek (Claude Code placeholder bırakır, "[Ekran görüntüsü: Sihirbaz Adım 2]" gibi) ve dokümanı bir kez de siz baştan sona takip ederek doğrulamak.

**Bağımlılık:** PR-02, PR-03, PR-07 · **Kabul Kriterleri:** Sistemi hiç tanımayan biri (test için: farklı bir cihazda, sadece dokümanı takip ederek) kurulumu tamamlayabiliyor.

---

## FAZ P0b — API Standardizasyonu ve Entegrasyon Portalı

> On-premise satışta kurumsal alıcının IT ekibi genelde ilk soracağı şeylerden
> biri "API'niz / Postman collection'ınız var mı" olur — bu yüzden bu blok
> FAZ P0 kadar öncelikli. **Collection dosyaları elle yazılmaz, koddan
> (OpenAPI şemasından) otomatik üretilir** — aksi halde her kod değişikliğinde
> elle güncelleme yükü doğar ve collection kısa sürede eskir/güvenilmez olur.

### PR-22 — API Konvansiyon Standardizasyonu

**Kapsam:** Tüm endpoint'ler tek response şeması kullanır (data/meta/error zarfı), hata formatı standart, pagination formatı Query Engine (IT-08) ile birebir, tarih formatı ISO8601, isimlendirme tek tip (snake_case önerilir — Python/Mongo tarafıyla tutarlı).

**Claude Code Yapar:** Response wrapper middleware, mevcut endpoint'lerin bu şemaya geçirilmesi (IT-33'teki API Versioning ile — `/api/v1` sabitlenip değişiklik geriye uyumlu yapılır, mevcut istemciler kırılmaz).

**Sizin Yapmanız Gerekir:** Naming convention tercihini onaylamak (hızlı bir karar, ~5 dakika).

**Bağımlılık:** IT-33 · **Kabul Kriterleri:** Örnek 5 farklı modülün endpoint'i test edilip aynı response şemasını döndürdüğü doğrulanıyor.

---

### PR-23 — Standart CRUD + Soft-Delete Şablonu (Generic Base)

**Kapsam:** docx'in Sprint 11 "Standard API" kararının (Create/Update/Delete-Soft/Get/GetById/Search/Filter/Bulk/Import/Export) kod seviyesinde **tek bir generic router/service base class** olarak uygulanması; her modül (Çiftçi, Parsel, Sözleşme, ProductionCycle...) bunu miras alır, CRUD'u elle yeniden yazmaz.

**Claude Code Yapar:** Generic CRUD base class (FastAPI), mevcut modüllerin buna geçirilmesi.

**Sizin Yapmanız Gerekir:** Yok — tamamen teknik.

**Bağımlılık:** IT-33, PR-22 · **Kabul Kriterleri:** Yeni bir modül eklerken CRUD endpoint'leri elle yazılmadan base class'tan miras alınarak 10 satırın altında ek kodla tam çalışıyor.

---

### PR-24 — Bearer Token / API Key Mekanizması (Entegrasyon Kimlik Doğrulama)

**Kapsam:** Kullanıcı login JWT'sinden **ayrı**, makine-makine entegrasyonlar için API Key/Client Credentials akışı. Her key: tenant'a bağlı, scope'lu (hangi modüllere/permission'lara erişebilir — RBAC IT-07 ile aynı Permission setini kullanır), rate limit'li, süre sınırlı (expiry). Integration Center (IT-01) üzerinden üretilir/iptal edilir/görüntülenir (değeri sadece üretim anında gösterilir, sonra maskeli — IT-01'deki secret kuralıyla aynı).

**Claude Code Yapar:** API key üretim/doğrulama/scope kontrolü middleware'i, rate limiting, Integration Center'a "API Anahtarlarım" ekranı.

**Sizin Yapmanız Gerekir:** Varsayılan rate limit değerlerini onaylamak (iş kararı, örn. dakikada 60 istek).

**Bağımlılık:** IT-01, IT-07 · **Kabul Kriterleri:** Scope'u sadece `Farmer.Read` olan bir key ile `Parcel.Write` denemesi 403 dönüyor; süresi dolmuş key otomatik reddediliyor; rate limit aşıldığında 429 dönüyor.

---

### PR-25 — OpenAPI'den Otomatik Postman/Insomnia Collection Üretimi

**Kapsam:** FastAPI'nin ürettiği `/openapi.json` şemasından **otomatik** Postman Collection v2.1 (ve Insomnia export) üretimi. Her modül bir Postman "folder"ı olacak şekilde organize edilir (Query Engine modül listesiyle birebir); örnek request body'ler şemadan otomatik doldurulur; ortam değişkenleri (`{{base_url}}`, `{{bearer_token}}`) + pre-request script ile PR-24'teki API key otomatik enjekte edilir.

**Claude Code Yapar:** Üretim scripti, CI'a "her deploy'da collection yeniden üretilip Geliştirici Portalı'na (PR-26) yayınlanır" adımı.

**Sizin Yapmanız Gerekir:** Yok — koddan otomatik türediği için elle güncelleme yükü sıfırlanır, bu yaklaşımın asıl kazancı budur.

**Bağımlılık:** PR-22, PR-23, PR-24 (standardizasyon ve auth olmadan collection tutarsız/eksik olur) · **Kabul Kriterleri:** Yeni bir endpoint eklendiğinde collection elle dokunulmadan bir sonraki build'de otomatik güncelleniyor; collection'daki her istek gerçek sunucuya karşı ("Run Collection") hatasız geçiyor.

---

### PR-26 — Geliştirici / Entegrasyon Portalı

**Kapsam:** Integration Center'ın (IT-01/IT-32) genişletilmiş, dış geliştiricilere açık yüzü: Swagger UI, indirilebilir Postman/Insomnia collection linki, API key üretme ekranı (PR-24), Webhook dokümantasyonu (IT-32'deki Webhook Engine), rate limit bilgisi, değişiklik günlüğü (changelog).

**Claude Code Yapar:** Portal sayfası + tüm parçaların bağlanması.

**Sizin Yapmanız Gerekir:** Yok.

**Bağımlılık:** PR-24, PR-25, IT-32 · **Kabul Kriterleri:** Dışarıdan bir entegratör hiç sizinle konuşmadan bu sayfadan API key alıp collection'ı indirip ilk isteği başarıyla atabiliyor.

---

## FAZ P1 — Sertleştirme (Hardening)

### PR-09 — Otomatik Test Kapsamı (Kritik Akışlar)

**Kapsam:** Auth/RBAC, Financial Ledger'ın silinmezlik kuralı, Hakediş motoru, Onay Zinciri, migration'lar için unit + entegrasyon testleri.

**Claude Code Yapar:** Testlerin tamamı.

**Sizin Yapmanız Gerekir:** Hangi akışların "iş açısından en kritik" olduğuna dair önceliklendirmeyi onaylamak (Claude Code öneri sunar, siz sıralarsınız).

**Bağımlılık:** — · **Kabul Kriterleri:** Kritik akışların test kapsamı %70+; kasıtlı bug eklenen bir PR'da testler kırmızı oluyor.

---

### PR-10 — CI/CD Pipeline

**Kapsam:** Her push'ta otomatik test + build + (opsiyonel) staging'e otomatik deploy.

**Claude Code Yapar:** Pipeline config dosyası (GitHub Actions/GitLab CI vb.), test/build adımları.

**Sizin Yapmanız Gerekir:** Git hosting hesabınızı seçmek/açmak (GitHub/GitLab), secrets'ları (deploy key vb.) panelden girmek — bunlar hesap sahipliği gerektirir, Claude Code sizin adınıza hesap açamaz.

**Bağımlılık:** PR-09 · **Kabul Kriterleri:** Bir PR açıldığında testler otomatik çalışıyor, kırmızıysa merge engelleniyor.

---

### PR-11 — Otomatik Yedekleme + Restore Testi

**Kapsam:** Mongo için düzenli otomatik backup scripti + **restore'un gerçekten çalıştığını** doğrulayan otomatik test (backup alıp ayrı bir ortama restore edip veri bütünlüğünü kontrol eden script).

**Claude Code Yapar:** Backup scripti, cron tanımı, restore-doğrulama scripti.

**Sizin Yapmanız Gerekir:** Scripti gerçek prod sunucusunda cron'a bağlamak ve ayda bir gerçek bir restore denemesi yapıp "gerçekten işe yarıyor" diye elle doğrulamak (bu adım otomatikleştirilse bile, felaket senaryosunda güvenmeniz için bir kez sizin de görmeniz önemli).

**Bağımlılık:** PR-01 · **Kabul Kriterleri:** Restore scripti farklı bir ortamda çalıştırılıp orijinal veriyle bire bir eşleşiyor.

---

### PR-12 — İzleme (Observability)

**Kapsam:** Hata takibi (exception tracking), uptime izleme, Health Center'ın (IT-33) gerçek metriklerle dolu olması.

**Claude Code Yapar:** Entegrasyon kodu (SDK kurulumu, error boundary'ler, log formatlama), Health Center'ın gerçek verilerle çalışması.

**Sizin Yapmanız Gerekir:** Bir hata takip servisinde (Sentry vb.) veya kendi self-hosted çözümünüzde hesap açmak — on-premise hassasiyetiniz varsa self-hosted seçenek (örn. GlitchTip) öneririm, bu kararı siz verirsiniz.

**Bağımlılık:** PR-01 · **Kabul Kriterleri:** Kasıtlı bir hata tetiklendiğinde izleme panelinde görünüyor.

---

### PR-13 — Güvenlik Taraması Otomasyonu + Pentest

**Kapsam:** Bağımlılık zafiyet taraması CI'a eklenir (otomatik); ayrıca GodMode auth'a rate-limiting/brute-force koruması eklenir.

**Claude Code Yapar:** Dependency audit CI adımı, rate-limiting kodu.

**Sizin Yapmanız Gerekir:** Gerçek bir pentest firması seçip anlaşmak (finansal veri tuttuğunuz için bu adımı atlamamanızı öneririm) — bulunan sonuçları Claude Code'a getirirseniz düzeltmeleri ben yaparım, ama testin kendisi 3. taraf gerektirir.

**Bağımlılık:** PR-09 · **Kabul Kriterleri:** CI'da yüksek/kritik seviye zafiyet varsa build kırmızı oluyor; GodMode'a 5 başarısız denemeden sonra geçici kilitleme çalışıyor.

---

### PR-14 — Yük Testi

**Kapsam:** Query Engine, harita, toplu SMS gibi ölçek gerektiren noktalar için k6/locust senaryoları.

**Claude Code Yapar:** Test senaryolarının tamamı.

**Sizin Yapmanız Gerekir:** Gerçek/gerçeğe yakın donanımda çalıştırıp sonucu yorumlamak (kapasite kararı — kaç eşzamanlı kullanıcı hedeflediğiniz iş kararınız).

**Bağımlılık:** PR-01 · **Kabul Kriterleri:** Hedef eşzamanlı kullanıcı sayısında p95 yanıt süresi kabul edilebilir eşiğin altında.

---

## FAZ P2 — Hukuki/Uyumluluk

### PR-15 — KVKK Aydınlatma Metni + Rıza Akışları

**Kapsam:** Çiftçi/personel verisi işlediğiniz için aydınlatma metni + açık rıza ekranları + veri saklama/silme politikası.

**Claude Code Yapar:** Metin taslağı + UI akışı (onay checkbox'ları, kayıt).

**Sizin Yapmanız Gerekir:** Taslağı bir hukuk danışmanına onaylatmak (bu bir hukuki sorumluluk, Claude Code avukat değildir).

**Bağımlılık:** — · **Kabul Kriterleri:** Taslak hazır, hukuki onay bekliyor durumda teslim edilir.

---

### PR-16 — ToS / Gizlilik Politikası / SLA Taslağı

**Claude Code Yapar:** Taslak metinler.
**Sizin Yapmanız Gerekir:** Hukuki onay + ticari SLA rakamlarının (uptime %, destek süresi) belirlenmesi — iş kararı.
**Bağımlılık:** — · **Kabul Kriterleri:** Taslaklar hazır.

---

### PR-17 — Bağımlılık Lisans Uyumluluk Raporu

**Kapsam:** Kullanılan tüm açık kaynak kütüphanelerin lisanslarının ticari kullanıma uygunluğu.

**Claude Code Yapar:** Otomatik tarama scripti + rapor.
**Sizin Yapmanız Gerekir:** Riskli görülen bir lisans çıkarsa (nadir) nihai kararı vermek.
**Bağımlılık:** — · **Kabul Kriterleri:** Rapor üretildi, kırmızı bayraklı bağımlılık yok.

---

## FAZ P3 — Pilot & Demo

### PR-18 — Demo Tenant + Gerçekçi Sahte Veri

**Kapsam:** Satış gösterimi için GodMode'dan tamamen ayrı, gerçekçi (ama sahte) veriyle dolu bir tenant.

**Claude Code Yapar:** Seed script'i (çiftçi/parsel/sözleşme/görev/hakediş örnekleriyle dolu).
**Sizin Yapmanız Gerekir:** Yok — istediğiniz senaryo/bölge/ürün profilini söylerseniz veriyi ona göre kurgularım.
**Bağımlılık:** IT-05, IT-18 vb. modüllerin tamamlanmış olması · **Kabul Kriterleri:** Demo tenant, satış görüşmesinde gerçek bir kayıt gibi görünüyor.

---

### PR-19 — Tenant Provisioning Otomasyonu

**Kapsam:** Yeni müşteri geldiğinde tenant açma/modül lisanslama sürecinin (IT-33 üstüne) tek komut/tek ekrandan yapılabilmesi — elle yapılan her adım hata kaynağıdır.

**Claude Code Yapar:** Provisioning scripti/ekranı.
**Sizin Yapmanız Gerekir:** İlk gerçek müşteride bu akışı kendiniz çalıştırıp onaylamak.
**Bağımlılık:** IT-33 · **Kabul Kriterleri:** Yeni tenant 10 dakikadan kısa sürede, hatasız açılıyor.

---

### PR-20 — Pilot Müşteri (tamamen sizin işiniz)

**Kapsam:** 1 gerçek kooperatif/işletmeyle sınırlı pilot.
**Claude Code Yapar:** Pilot sırasında çıkan bug/istekleri IT-XX/PR-XX olarak işleyebilir.
**Sizin Yapmanız Gerekir:** Müşteri bulma, görüşme, beklenti yönetimi — bu iş kararı ve ilişki yönetimi, otomatikleştirilemez.

---

## FAZ P4 — Operasyon & GTM

### PR-21 — Kullanıcı Kılavuzları + API Dokümantasyonu

**Kapsam:** Rol bazlı kullanıcı kılavuzu (Experience Profile'larınızla birebir örtüşüyor — Çiftçi/Ziraat Mühendisi/Yönetici/Muhasebe ayrı ayrı) + Swagger/OpenAPI.

**Claude Code Yapar:** Tüm dokümanların taslağı.
**Sizin Yapmanız Gerekir:** Ekran görüntüsü eklemek, son okuma.
**Bağımlılık:** İlgili modüllerin bitmiş olması · **Kabul Kriterleri:** Her rol için ayrı, eksiksiz bir kılavuz var.

---

**Kalan tamamen sizin işiniz olanlar (Claude Code'un elinden gelmez):**
fiyatlandırma/paketleme kararı, satış/pazarlama, pilot müşteri ilişkisi,
hukuki metinlerin nihai onayı, pentest firması seçimi, gerçek sunucuya ilk
erişim ve tuşa basma.

---

## Kullanım

Aynı ROADMAP.md deseni: **"PR-01'i yap"** deyin, Claude Code o iterasyonu
tamamlayıp size ne yaptığını ve sizden ne beklediğini (varsa) net şekilde
raporlar. Sıra esnek — on-premise kurulum (FAZ P0) önceliğiniz olduğu için
onunla başlamanızı öneririm, sertleştirme (FAZ P1) paralel de yürütülebilir.

---

## Durum Panosu (2026-07-11 itibarıyla)

| Faz | Maddeler | Durum |
|---|---|---|
| FAZ P0 | PR-01 ✅ · PR-02 ✅ · PR-03 ✅ · PR-04 ✅ · PR-05 ✅ · PR-06 ✅ · PR-07 ✅ · PR-08 ✅ | ✅ |
| FAZ P0b | PR-22 ✅ · PR-23 ✅ · PR-24 ✅ · PR-25 ✅ · PR-26 ✅ | ✅ |
| FAZ P1 | PR-09 🔄 (kritik akışların bir kısmı test edildi: ledger silinmezliği, auth lockout) · PR-10 ✅ · PR-11 ✅ · PR-12 ✅ · PR-13 🔄 (GodMode kod tabanında yok — login brute-force + CI dependency audit yapıldı) · PR-14 ✅ | 🔄 |
| FAZ P2 | PR-15 ✅ (taslak + rıza kayıt ucu) · PR-16 ✅ (taslak) · PR-17 ✅ | ✅ (hukuki onay bekliyor) |
| FAZ P3 | PR-18 ✅ · PR-19 ✅ · PR-20 ⬜ (tamamen sizin işiniz) | 🔄 |
| FAZ P4 | PR-21 ✅ | ✅ |

**Not:** Yukarıdaki ✅ işareti sadece Claude Code'un "Claude Code Yapar"
payının bittiğini gösterir — her PR'ın kendi "Sizin Yapmanız Gerekir"
maddesi (hesap açma, gerçek sunucuda ilk çalıştırma/doğrulama, hukuki/
ticari onaylar) hâlâ geçerlidir. Detaylı oturum notları için
`memory/CLAUDE.md` Bölüm 11'e bakın.
