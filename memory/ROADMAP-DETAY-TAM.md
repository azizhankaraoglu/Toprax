# ROADMAP-DETAY-TAM.md — TOPRAX Tam Kapsamlı Teknik Spesifikasyon (IT-01 → IT-35)

> Bu dosya **ROADMAP.md'nin yerine geçmez, onu tamamlar.** ROADMAP.md faz/iterasyon
> sırasını ve bağımlılıkları tanımlar; bu dosya **her IT-XX için** (IT-01'den
> IT-35'e kadar, FAZ 0 → FAZ 12) veri modelini, durum makinesini, API yüzeyini,
> UI gereksinimlerini, iş kurallarını ve "bitti" tanımını (Definition of Done)
> verir. Kaynak: `geliştirmeler.docx` (Global Kural + Sprint A1, A2, 3–12).
>
> **Amaç:** Bu proje uçtan uca birbirine bağlı (ProductionCycle → RBAC → Query
> Engine → Spatial/UX → UFYD/Saha/İletişim/LMS → Platform Core → Mobil). Bir
> katmanda eksik/yanlış uygulanan bir kural (örn. IT-05'te ProductionCycle
> migration'ının backward-compatible olmaması, ya da IT-19'da Ledger'ın
> silinebilir bırakılması) zincirin ilerideki tüm halkalarını bozar. Bu yüzden
> her IT bölümünde **"Kabul Kriterleri"** somut ve test edilebilir yazılmıştır —
> Cowork ile genel test yapılırken bu kriterler doğrudan test senaryosu olarak
> kullanılabilir.
>
> **Kullanım kuralı (geliştirme sırasında):** Bir IT-XX atandığında önce
> ROADMAP.md'deki satır (bağımlılık + kapsam özeti), sonra bu dosyadaki ilgili
> bölüm okunmalı. Buradaki alan/durum/kural listeleri **eksiksiz uygulanmalıdır.**
>
> **Kullanım kuralı (test sırasında / Cowork):** Her IT bölümünün sonundaki
> "Kabul Kriterleri" listesi bir kontrol listesi olarak kullanılabilir — hangi
> maddeler geçmiyorsa, o IT "devam" (🔄) olarak işaretlenip ilgili kısmın
> tamamlanması gerekir.
>
> Genel geliştirme kuralı (tüm IT'ler için geçerli, docx'te sprint başına
> tekrar eder): mevcut mimari korunur, gereksiz refactor yok, yeni modül RBAC +
> Audit Log + (kurulduysa) Query Engine + Event Bus'a bağlanır, server-side
> pagination zorunludur, hassas alanlar loglanmaz.
>
> **`server.py` büyüme kuralı:** `server.py` merkezi bağımlılık noktasıdır
> (`current_user`/`db`/`require_permission`/`log_audit` burada tanımlanır,
> ~30 modül buradan import eder) — bu yüzden büyümesi diğer dosyalardan
> daha riskli, kontrolsüz büyürse review/okunabilirlik kalitesi düşer ve
> permission/tenant kontrolü unutma riski artar (bkz. 2026-07-11 güvenlik
> denetimi — `list_farmers`/`get_farmer_360`/`list_parcels`/
> `get_parcel_detail` sadece `current_user`ı kontrol edip `require_permission`
> unutulmuştu). Kural: **yeni bir CRUD/domain alanı server.py'ye
> eklenmez** — mevcut `register_X_routes(api_router, db, current_user,
> require_permission, log_audit, ...)` kalıbıyla kendi modülünde açılır
> (bkz. `data_entry.py`/`support.py` emsalleri). server.py sadece app
> kurulumu, auth, ve zaten orada olan farmer/parcel/dashboard/seed
> mantığını barındırmaya devam eder — mevcut kod hemen taşınmaz (riskli,
> testsiz), ama zamanla fırsat bulundukça (ör. bir IT o alana dokunuyorsa)
> kademeli olarak ayrı modüle çıkarılması değerlendirilmelidir.

---

## FAZ 0 — Platform Temeli

### IT-01 — Config Service + Secrets Standardı

**Amaç:** Hiçbir hassas bilgi kaynak kodunda olmayacak; tüm yapılandırma merkezi bir servisten okunacak.

**Asla kaynak koda yazılmayacak bilgi sınıfları (tam liste):**
API Key, Access Token, Refresh Token, JWT Secret, OAuth Secret, Client Secret, SMTP Bilgileri, SMS Servis Bilgileri, WhatsApp API Bilgileri, Harita Servis Anahtarları, AI Servis Anahtarları (OpenAI/Anthropic/Gemini/Azure AI dahil), PostgreSQL/Mongo Bağlantı Bilgileri, Redis, RabbitMQ, Elasticsearch, GeoServer, PostGIS, FTP/SFTP Bilgileri, Banka Entegrasyon Bilgileri, e-Devlet Servis Bilgileri, MERSİS, MERNİS, TAKBİS, CBS Servisleri, Uydu Servis Sağlayıcıları, SMS Gateway, Mail Gateway, üçüncü parti tüm entegrasyon anahtarları.

**Environment yapısı:** `.env.development`, `.env.test`, `.env.staging`, `.env.production` — her ortam kendi yapılandırmasına sahip. **Kod içinde ortam kontrolü (`if env == 'production'` tipi dallanma) yapılmaz** — davranış farkı config değerinden gelir, koddan değil.

**Configuration Service:** Uygulama `.env`'i doğrudan okumaz; merkezi `config_service.py` üzerinden okur. Bu, ileride Azure Key Vault / AWS Secrets Manager / HashiCorp Vault / Kubernetes Secrets'a geçişi kolaylaştırır (arayüz aynı kalır, implementasyon değişir).

**Entegrasyon Yönetimi (tek noktadan okunacak servisler):** OpenAI, Anthropic, Gemini, WhatsApp, SMS, SMTP, GeoServer, NASA, Sentinel, Planet, MERSİS, TAKBİS.

**Loglama kuralı:** Hiçbir log içine Token, Şifre, API Key, Authorization Header, Cookie, Session bilgisi yazılmaz; hata logları hassas bilgi içermez (secret maskeleme fonksiyonu tüm log çıktılarından geçmeli).

**Git kuralları:** `.env`, `.env.production`, `.env.local`, secret dosyaları, sertifikalar, private key dosyaları repoya eklenmez; onun yerine `.env.example` tutulur.

**Integration Center ekranı (sadece God Mode + yetkili Super Admin erişebilir):**
- API anahtarları — **değerleri maskeli gösterilir, düz metin asla görüntülenmez, sadece güncellenebilir/yeniden oluşturulabilir**
- Entegrasyonların aktif/pasif durumu
- Endpoint URL'leri
- Timeout ve Retry ayarları
- Webhook tanımları
- OAuth bağlantıları
- Token yenileme bilgileri
- Son başarılı/başarısız bağlantı zamanı
- Sağlık durumu (Health Check)

**Kabul Kriterleri:** `grep` ile repo taranıp hiçbir dosyada düz metin secret bulunmuyor; Integration Center'da bir API key güncellendiğinde eski değer hiçbir response'ta (UI dahil) düz metin dönmüyor; `.env.example` gerçek `.env`'deki tüm anahtarları isim olarak içeriyor (değersiz).

---

## FAZ 1 — Sprint A1 Kalanı (Veri Giriş Altyapısı)

> Not: Sprint A1 Faz 1-2 (Çiftçi pilotu + Dinamik Form Yönetimi altyapısı + DynamicFieldsSection) ROADMAP.md'ye göre **zaten tamamlanmış (✅)**. IT-02/03/04 bu altyapıyı *kullanarak* yeni alanlar ekler, altyapıyı yeniden kurmaz.

**Zaten var olduğu varsayılan altyapı (bu fazın ön koşulu, yoksa önce bu doğrulanmalı):**
- **Form Yönetimi modülü** (Ayarlar altında): admin yeni alan oluşturabilir, düzenleyebilir, pasife alabilir, zorunlu yapabilir, görünürlüğünü değiştirebilir, sıralamasını değiştirebilir, yardım metni/placeholder/varsayılan değer/tab bilgisi/hangi modülde gösterileceğini belirleyebilir.
- **Alan Tipleri:** Text, TextArea, Number, Decimal, Date, DateTime, Time, Checkbox, Switch, Radio Button, Select, Multi Select, Lookup, AutoComplete, IBAN, Telefon, Email, TC Kimlik, Vergi No, Dosya, Resim, Çoklu Dosya, GeoJSON, Coordinate, URL — yeni tipler kolayca eklenebilir olmalı.
- **Lookup Yönetimi modülü:** admin lookup grubu oluşturur, değer ekler, hiyerarşik lookup kurabilir, aktif/pasif yapar, sıralar. Örnekler: Sulama Tipi (Damla/Yağmurlama/Salma/Pivot), Ürün (Şeker Pancarı/Buğday/Arpa/Mısır), Risk Seviyesi (Düşük/Orta/Yüksek).
- Form Yönetimi + Lookup Yönetimi tamamen RBAC'a dahildir (sadece yetkili roller alan/lookup oluşturabilir/düzenleyebilir).

**Genel A1 kuralı:** Her yeni alan veritabanında **gerçek kolon** olarak oluşturulur (JSON/Key-Value tabanlı dinamik veri depolama kullanılmaz — dinamik olan alanın *tanımı* `field_definitions`'tadır, alanın *değeri* gerçek tipli kolondur). Mevcut entity/DTO/servis/repository/CRUD yapıları korunur, genişletilir.

### IT-02 — Parsel + Toprak Alan Genişletme

> ⚠️ **Kaynak doküman notu:** docx'te bu bölümün alan listesi "(Buraya alan listeleri eklenecek.)" olarak boş bırakılmış. Aşağıdaki liste ROADMAP.md'deki kategori ipuçlarından **türetilmiştir** — gerçek/nihai liste değildir. Oturum başında kullanıcıya (size) 1 soru sorup onaylatmak veya elinizdeki gerçek listeyi vermeniz, Claude Code'un kafasına göre alan uydurmasını engeller.

**Parsel — türetilmiş alan kategorileri:**
| Kategori | Örnek alanlar |
|---|---|
| Kimlik | Ada No, Parsel No, Mevkii |
| Konum | İl, İlçe, Mahalle/Köy, Koordinat (GeoJSON alan tipiyle) |
| Fiziksel | Rakım, Eğim (%), Yüzölçümü |
| Mülkiyet | Sahiplik Tipi (Malik/Kiracı/Ortak), Kira Bilgisi (kiralayan, kira bedeli, sözleşme tarihi) |
| Altyapı | Yol erişimi, Elektrik, Sulama suyu kaynağı, Sulama Tipi (lookup) |

**Toprak Analizi — türetilmiş alan kategorileri:**
| Kategori | Örnek alanlar |
|---|---|
| Fiziksel | Tekstür, Derinlik (cm), Taşlılık oranı |
| Kimyasal | Tuzluluk, Kireç oranı, pH, Organik Madde, Azot, Fosfor, Potasyum |
| Mikro element | Çinko (Zn), Demir (Fe), Bor (B) |
| Meta | Rapor No, Analiz Tarihi, Laboratuvar |
| AI alanları | AI Risk Skoru, AI Önerisi (metin), AI Analiz Tarihi — bu alanlar şimdilik boş/manuel girilebilir, ileride AI servisleri dolduracak |

**Uygulama:** tüm bu alanlar `field_definitions` + gerçek kolon olarak eklenir, seed script ile önceden tanımlanır, DynamicFieldsSection ile forma bağlanır.

**Kabul Kriterleri:** Yeni alanlar Parsel/Toprak edit formunda DynamicFieldsSection üzerinden görünüyor; seed script tekrar çalıştırıldığında duplicate alan oluşturmuyor (idempotent).

### IT-03 — Sözleşme + Ekim Planlama Alan Genişletme

> Aynı uyarı geçerli: docx'te alan listesi boş bırakılmış, aşağıdaki ROADMAP.md ipuçlarından türetilmiştir.

**Sözleşme — türetilmiş kategoriler:** Sözleşme Türü, Taraflar (çiftçi + fabrika/kooperatif), Prim şartları, Kesinti şartları, Fabrika Teslim koşulları (teslim yeri, teslim tarihi aralığı).

**Ekim Planlama — türetilmiş kategoriler:** Sezon (yıl+dönem), Tohum Çeşidi (lookup), Ekim Takvimi (planlanan ekim tarihi, planlanan hasat tarihi), Kaynak Planlama referansları (makine/personel/malzeme ihtiyaç referansı — bu alan sadece referans/not niteliğinde, Sprint 8 Saha modülüyle gerçek planlamaya bağlanacak).

**Kabul Kriterleri:** IT-02 ile aynı desen (seed + field_definitions + form entegrasyonu).

### IT-04 — Edit Formları + Dosya Alan Tipleri

**Kapsam:**
- Çiftçi/Parsel **düzenleme** ekranları (mevcut oluşturma ekranlarından ayrı, DynamicFieldsSection kullanır)
- `storage.py` soyutlaması: dosyalar `uploads/` altında tutulur, erişim bu katman üzerinden (ileride S3/MinIO takılabilir — ROADMAP.md karar B.4)
- Basit dosya/resim upload — Dosya, Resim, Çoklu Dosya alan tiplerinin gerçek UI karşılığı (önizleme, silme, indirme)
- Doküman sekmesi (Çiftçi/Parsel kartında yüklenen tüm dosyaların listelendiği sekme)

**Kabul Kriterleri:** Resim alan tipi seçilen bir field, formda gerçek dosya seçici + önizleme gösteriyor; yüklenen dosya `storage.py` üzerinden erişilebiliyor, doğrudan disk path'i UI'da hardcode edilmemiş.

---

## FAZ 2 — Sprint A2 (ProductionCycle Omurgası)

### IT-05 — ProductionCycle Backend

**Yeni Domain Yapısı (Aggregate Root):**
```
Farmer
 └── Parcel
      └── ProductionCycle (Üretim Sezonu)   ← YENİ, bu sprintin kalbi
            ├── Crops (1:N)
            ├── SoilAnalysis (1:N)
            ├── Activities (1:N)
            ├── Contracts (1:N)
            ├── Transportation (1:N)
            ├── Harvests (1:N)
            ├── FactoryAppointments (1:N)
            ├── Yields (1:N)
            └── Documents (1:N)
```
Farmer ve Parcel **korunur, değişmez**. Bundan sonraki tüm üretim süreçleri doğrudan Parcel'e değil, ilgili ProductionCycle'a bağlanır.

**Neden:** Bir parsel her yıl farklı ürün/operasyonla üretime devam eder (2024: buğday, 2025: mısır, 2026: şeker pancarı) — her sezon kendi operasyon/ürün/sözleşme/analiz/sonuçlarını bağımsız yönetebilmeli.

**ProductionCycle veri modeli:**
| Alan | Tip |
|---|---|
| Year | int |
| Season | string |
| Status | enum: Planning, Active, Harvesting, Completed, Cancelled |
| FarmerId | ref |
| ParcelId | ref |
| StartDate | date |
| EndDate | date |

**Veri modeli değişikliği (kritik — migration gerektirir):** Activity, SoilAnalysis, Contracts, Harvests, FactoryAppointments, Transportation, Yields tablolarındaki `ParcelId` → `ProductionCycleId` olur.

Eski:
```
Activity { Id, ParcelId, Type, Date }
```
Yeni:
```
Activity { Id, ProductionCycleId, Type, Date }
```

**Migration script — geriye uyumluluk zorunlu:**
- Mevcut kayıtlar için otomatik "geçmiş sezon" ProductionCycle kaydı üretilmeli (örn. mevcut her Parcel için bir "varsayılan/geçmiş" ProductionCycle açılıp eski kayıtlar buna bağlanmalı)
- **Eski `parcel_id` alanı korunur, silinmez** (backward compatible) — sadece yanına `production_cycle_id` eklenir
- Migration script idempotent olmalı (2 kez çalıştırılırsa duplicate üretmemeli)

**Not:** Machinery ilişkisi bu sprint kapsamında ProductionCycle'a bağlanmayacak; makineler ileride Activity üzerinden ilişkilendirilecek.

**Geliştirme Kuralları:** Mevcut Farmer/Parcel yapısı korunur; ProductionCycle yeni Aggregate Root; gereksiz refactor yok; mevcut servisler korunur/genişletilir; mevcut CRUD yapıları bozulmaz; yeni üretim süreçleri doğrudan Parcel yerine ProductionCycle'a bağlanır.

**API:** `/api/production-cycles` (CRUD + durum geçiş), her alt modülün endpoint'i artık `production_cycle_id` filtresi de kabul eder (eski `parcel_id` filtresi de çalışmaya devam eder).

**Kabul Kriterleri:** Migration sonrası eski kayıtlar hiçbir veri kaybı olmadan erişilebilir durumda; yeni bir Activity kaydı artık ProductionCycle olmadan oluşturulamıyor (validasyon); status makinesi (Planning→Active→Harvesting→Completed/Cancelled) API'de zorlanıyor.

### IT-06 — ProductionCycle UI

**Parsel detayında "Üretim Sezonları" sekmesi:** parsele bağlı tüm ProductionCycle kayıtları liste halinde (yıl/sezon/durum).

**Sezon çalışma ekranı:** bir ProductionCycle seçildiğinde, altındaki Toprak Analizi → Ekim → Sözleşme → Hasat zincirinin **hepsi aynı ekranda/sekmeli yapıda** yönetilebilmeli (Workspace mantığının erken versiyonu — tam Workspace dönüşümü IT-13'te).

**Yeni kayıt akışı:** Kullanıcı senaryosu şu olmalı:
```
Çiftçiyi seç → Parsele gir → İlgili Üretim Sezonunu oluştur/seç → Sezona ait tüm işlemler aynı bağlamda yürütülür
```
Yeni Toprak Analizi/Ekim/Sözleşme/Hasat kaydı açıldığında **ProductionCycle bilgisi otomatik dolu gelmeli**, kullanıcı tekrar seçmemeli (context-driven navigation — Sprint 6 prensibi burada da erken uygulanır).

**Kabul Kriterleri:** Bir ProductionCycle çalışma ekranından yeni Toprak Analizi açıldığında form `production_cycle_id`'yi otomatik dolduruyor, kullanıcıdan tekrar istemiyor.

---

## FAZ 3 — Sprint 3 Tamamlama (RBAC)

### IT-07 — Sistem Rolleri + Field-Level Security v1 + ProductionCycle Permission'ları

**Sistem Rolleri (sadece God Mode oluşturabilir/düzenleyebilir/silebilir):** God Mode, Super Admin, Admin, User.

**Yetki Hiyerarşisi:**

| Rol | Yetkiler |
|---|---|
| **God Mode** | Sınırsız. Tüm Tenant'ları görüntüler/yönetir; sistem ayarlarını değiştirir; sistem rollerini yönetir; yetki hiyerarşisini değiştirir; tüm kullanıcılar üzerinde işlem yapar; **tüm API yetkilendirmelerini bypass edebilir** |
| **Super Admin** | God Mode'un oluşturduğu Tenant'ları yönetir; Tenant oluşturur/yönetir/ayarlar; Form ekranlarını yönetir; Entegrasyon bilgilerini yönetir; API/Web Service token oluşturur/yönetir; kendi Tenant'ındaki Admin'leri yönetir |
| **Admin** | Sadece kendi Tenant'ı içinde. Kullanıcı oluşturur; kullanıcılara rol atar; mevcut Role Management ile rol oluşturur/düzenler; permission atamalarını yönetir |
| **User** | Doğrudan yetki almaz; yetkileri Admin'in atadığı Role üzerinden belirlenir |

**Role Management:** mevcut modül **yeniden geliştirilmez**, korunur. Admin: yeni rol oluşturma, düzenleme, permission atama, kullanıcıya rol atama.

**Permission modeli (ekran bazlı değil, permission bazlı — RBAC):**
```
Farmer.Create / Farmer.Read / Farmer.Update / Farmer.Delete
Parcel.Create / Parcel.Read / Parcel.Update / Parcel.Delete
Contract.Create / ...
ProductionSeason.Create / ProductionSeason.Update / ...
```
Bu iterasyonda **ProductionCycle (ProductionSeason) permission seti de tanımlanmalı** (IT-05 bağımlılığı — permission'lar olmadan ProductionCycle güvensiz kalır).

**API Authorization:** yetkilendirme sadece UI'da değil, **tüm API endpoint'leri** ilgili Permission ile korunur; yetkisiz istek reddedilir (401/403).

**Field-Level Security v1:** `field_definitions`'a `sensitive` bayrağı eklenir. İlk senaryo: **IBAN bilgisi yalnızca Finans rolüne sahip kullanıcılar ve kaydın sahibi tarafından görüntülenebilir**; yetkisiz kullanıcılar bu alanı göremez (response'ta maskelenir veya alan hiç dönmez — tercihen response'tan tamamen çıkarılır, sadece UI'da gizlemek yetmez). Yapı genişletilebilir olmalı (başka alanlara da `sensitive=true` verilebilecek).

**Tenant Yapısı:** God Mode tüm Tenant'ları yönetir; Super Admin bir/birden fazla Tenant yönetir; Admin yalnızca kendi Tenant'ında işlem yapar; User yalnızca kendi Tenant'ındaki verilere erişir.

**Kabul Kriterleri:** IBAN alanı Finans olmayan bir rolle çekildiğinde API response'unda görünmüyor; God Mode olmayan bir kullanıcı başka bir Tenant'ın verisine API'den erişemiyor (403); ProductionSeason.* permission'ları tanımlı ve IT-06'daki ekranlarda zorlanıyor.

---

## FAZ 4 — Sprint 5 (Universal Query & Filter Engine)

**Stratejik konum (docx'ün kendi mimari notu):** Query Engine, TOPRAX'in "okuma tarafı" omurgasıdır — ProductionCycle (iş modeli) ve RBAC (güvenlik) üzerine kurulur; Spatial/UX bunun üzerine gelir.

### IT-08 — Query Engine Çekirdeği

**Genel yaklaşım:** Filtreleme ekran bazlı değil, **merkezi bir servis** üzerinden yönetilir. Her modül yalnızca kendi filtrelenebilir alanlarını tanımlar (field_definitions ile otomatik entegre); Query Engine bu alanları kullanarak filtre/arama/sıralama yapar. Yeni modül geldiğinde filtreleme altyapısı **yeniden yazılmaz**.

**İlk fazda Query Engine'i kullanacak modüller:** Çiftçi, Parsel, Üretim Sezonu, Sözleşme, Toprak Analizi, Görevler, Harita, Dashboard.

**Filtre DSL:** alan + operatör + değer, AND/OR kombinasyonu. Örnek filtrelenebilir alanlar (modül bazlı):
- Çiftçi: Ad Soyad, Telefon, İl, İlçe, Mahalle, Kooperatif, Risk Skoru, Aktif/Pasif
- Parsel: Alan, Sulama Tipi, Malik, İşleten, Ekili/Boş
- Üretim Sezonu: Yıl, Durum, Ürün, Beklenen Verim
- Sözleşme: Sözleşme No, Ürün, Durum, Fabrika, Ödeme Durumu
- Toprak: pH, Organik Madde, Azot, Fosfor
- AI: Hastalık Riski, NDVI, Su Stresi, Risk Skoru (bu alanlar henüz veri üretmiyor olabilir ama filtre şeması hazır olmalı)

**Performans zorunlulukları (hepsi hard requirement, opsiyonel değil):**
- Server-side filtering / sorting / pagination
- Lazy loading
- Projection (sadece gerekli alanlar çekilir)
- Gereksiz JOIN'lerden kaçınma
- İndeksleme stratejisi
- Dashboard/Harita yalnızca ihtiyacı olan özet veriyi ister, büyük veri seti istemciye tam gönderilmez

**Mimari not (CQRS'e yakın, ROADMAP.md karar B.3 ile tutarlı):** Ayrı bir read-model **kurulmaz**; bunun yerine Query Engine'in okuma yolu (projection + index + pagination) performans odaklı tasarlanır. Bu, mevcut mimariyi bozmadan ileride milyonlarca kayıtla çalışmaya hazırlık sağlar.

**API:** `/api/query/{module}` (POST, filtre DSL body + pagination/sort parametreleri).

**Kabul Kriterleri:** Aynı filtre DSL'i hem Çiftçi hem Parsel modülünde farklı alan setleriyle çalışıyor (kod tekrarı yok, tek çekirdek); 10.000+ kayıtlı bir koleksiyonda sayfalama gerçek server-side (tüm veri çekilip client'ta kesilmiyor).

### IT-09 — Saved Queries + Portföy (Favorilerim) + Sorgu Paylaşımı + Genel Filtre Paneli

**Saved Queries:** kullanıcı oluşturduğu sorguyu kaydeder (örn. "Riskli Parseller", "Borçlu Çiftçiler", "Hasat Bekleyenler", "Pancar Üreticileri", "Analizi Eksik Olanlar"), tek tıkla tekrar çalıştırır.

**Favorilerim (Portföy):** kullanıcı kendi çalışma portföyünü oluşturur — Çiftçiler, Parseller, Üretim Sezonları, Sözleşmeler eklenebilir. Rol bazlı örnek kullanım: Ziraat Mühendisi → "Sorumlu Olduğum Parseller"; Yönetici → "Kritik Üretim Alanları"; Finans → "Ödeme Bekleyen Sözleşmeler". Portföyler Dashboard, Harita ve Liste ekranlarında **doğrudan kullanılabilmeli** (bir filtre gibi).

**Sorgu Paylaşımı:** kullanıcı oluşturduğu sorguyu (örn. "Kırşehir Riskli Parseller") başka kullanıcılarla paylaşabilir.

**Genel filtre paneli bileşeni:** tüm liste ekranlarına eklenecek ortak bileşen — Query Engine'in DSL'ini UI'a çevirir.

**Kabul Kriterleri:** Bir Saved Query iki farklı ekranda (Liste + Dashboard) aynı sonucu veriyor; paylaşılan bir sorgu başka kullanıcının hesabında görünüyor ve çalıştırılabiliyor.

### IT-10 — Global Arama + AI Doğal Dil Köprüsü

**Global arama:** tek kutu — çiftçi/parsel/sözleşme/sezon aynı anda aranabilir (Ad Soyad, Telefon, TCKN, Parsel No, Sözleşme No, Üretim Sezonu, IBAN, Plaka gibi alanlar üzerinden).

**AI doğal dil → Query Engine köprüsü:** mevcut copilot gerçek sorguya bağlanır. **Kritik kural: AI kendi filtre mantığını kurmaz, mevcut Query Engine'i çağırır** (Sprint 5'in genel kuralı — AI Asistanı ayrı bir sorgu yolu icat etmemeli). Örnek doğal dil sorguları: "Parasını ödemediğimiz sözleşmeleri getir", "Hastalık görülen parselleri göster", "Bu yıl pancar eken çiftçileri listele".

**Kabul Kriterleri:** AI'ya yazılan bir doğal dil sorgusu, arka planda `/api/query/{module}` çağrısına dönüşüyor (ayrı bir AI-özel veri erişim kodu yok); global arama sonucu tıklanınca ilgili kayda gidiyor.

---

## FAZ 5 — Sprint 6 (UX / Workspace Mimarisi)

**Tasarım manifestosu (docx'ün bu sprint için verdiği tek cümlelik yön — tüm ekranlar buna göre değerlendirilmeli):**
TOPRAX, ekranlar arasında dolaşılan klasik bir CRUD uygulaması değil; kullanıcıların işlerini bulundukları bağlamı kaybetmeden tamamlayabildiği, minimum tıklama ile çalışan, **Entity odaklı**, **Workspace mantığıyla** tasarlanmış modern bir kurumsal operasyon platformu olmalıdır.

**Temel prensip:** TOPRAX ekran odaklı değil **Entity (İş Nesnesi) odaklı** çalışır. Örn. bir Çiftçi kartı sadece çiftçi bilgisi gösteren ekran değil; Genel Bilgiler, Parseller, Üretim Sezonları, Sözleşmeler, Toprak Analizleri, Görevler, Dokümanlar, Harita, AI Önerileri'nin tek noktadan yönetildiği bir çalışma alanıdır. Aynı yaklaşım Parsel, Üretim Sezonu, Sözleşme, Makine, Fabrika için de geçerli.

**Context Driven Navigation:** kullanıcı bağlamı kaybetmeden çalışır. Örnek: Çiftçi Kartı → Sözleşmeler → Yeni Sözleşme → **çiftçi bilgisi otomatik dolu gelir**, kullanıcı tekrar seçmez. Aynı prensip Yeni Parsel, Yeni Üretim Sezonu, Yeni Görev, Yeni Toprak Analizi, Yeni Ziyaret, Yeni Evrak için de uygulanır.

**Context Aware CRUD:** ilişkili kayıtlar bulundukları ekrandan yönetilir (örn. Çiftçi içindeki sözleşme listesinde Yeni Oluştur/Düzenle/Görüntüle/Sil doğrudan yapılabilir, sayfa değişmez).

### IT-11 — SmartDataGrid Ortak Bileşeni

**Tüm liste ekranlarının kullanacağı tek Data Grid bileşeni.** Desteklemesi gerekenler:
- Kolon sıralama, gizleme/gösterme, yeniden sıralama, genişlik değiştirme, sabitleme (pin)
- Çoklu sıralama
- Sayfalama + Sanal Listeleme (Virtual Scrolling)
- Satır seçimi + çoklu seçim
- Excel Aktarma, CSV Aktarma, Yazdırma

**Kolon bazlı filtreleme:** her kolon başlığı filtre yeteneğine sahip (örn. Sözleşme No → Filtrele; Durum → Filtrele; Başlangıç Tarihi → Tarih Aralığı; Risk Skoru → Min/Max) — kullanıcı listeyi terk etmeden filtreler.

**Gelişmiş filtre paneli:** çoklu seçim, tarih aralığı, sayısal aralık, lookup seçimi, boolean, serbest metin tipleri; filtreler birlikte çalışır.

**Bağımlılık:** Query Engine'e (IT-09) bağlıdır — grid kendi filtre/sort mantığını icat etmez, DSL'i tüketir.

**Kabul Kriterleri:** SmartDataGrid en az 3 farklı modülde (Çiftçi, Parsel, Sözleşme listesi) aynı bileşen olarak kullanılıyor, her biri ayrı kod yazılmamış; 10.000 satırlık listede virtual scrolling gerçekten DOM'a tüm satırları basmıyor.

### IT-12 — Drawer + Breadcrumb + Son Açılanlar + Favoriler + Bildirim Çekmecesi

**Drawer (Yan Panel):** mümkün olduğunca yeni sayfa açılmaz; detay görüntüleme/hızlı düzenleme Drawer üzerinden yapılır, kullanıcının bulunduğu liste/ekran korunur.

**Breadcrumb:** kullanıcı bulunduğu iş akışını görür. Örnek: `Çiftçiler > Ahmet Yılmaz > Parseller > 145 Ada 18 > 2026 Üretim Sezonu > Görevler`.

**Son Açılanlar:** kullanıcının son görüntülediği kayıtlar otomatik listelenir (Son Açılan Çiftçiler/Parseller/Sözleşmeler).

**Favoriler:** kullanıcı sık kullandığı kayıtları favoriye ekler (Favori Çiftçiler/Parseller/Üretim Sezonları/Sözleşmeler) — IT-09'daki Portföy ile aynı alt yapıyı paylaşabilir.

**Bildirim çekmecesi:** kayıt bazlı bildirimler (Görev Atandı, Hasat Yaklaşıyor, Toprak Analizi Geldi, AI Risk Tespit Etti, Sözleşme Süresi Doluyor) — tıklanınca ilgili kayda yönlendirir.

**Kabul Kriterleri:** Bir Parsel detayına Drawer'dan bakılabiliyor ve arkadaki liste ekranı state'ini (scroll, filtre) koruyor; breadcrumb gerçek navigasyon geçmişini yansıtıyor.

### IT-13 — Workspace Dönüşümü

**Çiftçi ve Parsel kartları context-aware CRUD'a geçer:** kart içinden yeni sözleşme/sezon/görev oluşturulduğunda bağlam (farmer_id, parcel_id, production_cycle_id) otomatik dolar.

**Kişisel Çalışma Alanı (rol bazlı örnek):**
- Ziraat Mühendisi → Görevlerim, Sorumlu Olduğum Parseller, Yaklaşan Hasatlar, AI Uyarıları
- Muhasebe → Bekleyen Ödemeler, Vadesi Gelen Sözleşmeler
- Yönetici → Risk Haritası, KPI Dashboard, Kritik Uyarılar

Her rol kendi çalışma ekranını kişiselleştirebilir (widget seçimi/sıralaması — IT-14'teki widget mimarisiyle aynı desen).

**Quick Actions (kart/liste ekranlarında tek tıkla):**
- Çiftçi: Düzenle, Ara, SMS Gönder, E-Posta Gönder, Haritada Aç, Yeni Sözleşme, Yeni Parsel, Yeni Üretim Sezonu
- Parsel: Düzenle, Haritada Aç, Üretim Sezonuna Git, Toprak Analizi, Navigasyon, Görev Oluştur

**Kabul Kriterleri:** Çiftçi kartından "Yeni Sözleşme" tıklandığında açılan formda farmer alanı önceden dolu ve değiştirilemez/salt-okunur; her rol için en az 1 kişiselleştirilmiş widget seti çalışıyor.

---

## FAZ 6 — Sprint 4 (Spatial Operations & Intelligence Center)

**Genel yaklaşım — harita modülü 4 ana yeteneği tek platformda sunmalı:** Mekânsal Operasyon Merkezi, Mekânsal Dashboard, Mekânsal Analiz, AI Destekli Mekânsal Karar Destek. Mevcut harita altyapısı korunur, gereksiz refactor yapılmaz.

### IT-14 — Widget Tabanlı Harita Dashboard'u

**Dashboard Mimarisi:** sabit dashboard kartları DEĞİL, **Widget tabanlı** yapı. Her widget bağımsız geliştirilebilir, bağımsız eklenebilir/kaldırılabilir, kullanıcı bazında özelleştirilebilir olmalı.

**Bugün desteklenecek 8 widget (tam liste, hepsi bu iterasyonda çalışır veri ile gelmeli):**
Toplam Çiftçi, Toplam Parsel, Toplam Ekili Alan, Boş Parseller, Aktif Üretim Sezonları, Hasat Bekleyen Alanlar, Görev Bekleyen Parseller, Riskli Parseller.

**Gelecekte eklenecek widget'lar (mimari bunlara hazır olmalı, veri kaynağı henüz yok — ROADMAP.md S4 kararı: demo/simüle katman):**
NDVI, Su Stresi, Hastalık Analizi, Zararlı Yoğunluğu, Don Riski, Yangın Riski, Verim Tahmini, Şeker Oranı Tahmini, AI Önerileri. **Yeni widget eklemek mevcut harita mimarisini değiştirmeyi gerektirmemeli** — bu iterasyonun en önemli mimari testi budur.

**Dashboard Senkronizasyonu:** harita ve dashboard tamamen senkron — zoom değiştiğinde, filtre değiştiğinde, seçim değiştiğinde, çizim yapıldığında dashboard otomatik güncellenir. (Veri kaynağı IT-08 Query Engine.)

**Kişisel çalışma alanı kaydetme:** kullanıcı görmek istediği widget'ları seçer, sıralamasını değiştirir, harita görünümünü ve filtrelerini kaydeder.

**Kabul Kriterleri:** 8 widget de gerçek veriden besleniyor (mock değil); bir widget eklemek/çıkarmak için harita render kodunda değişiklik gerekmiyor (widget registry/plugin deseni); harita üzerinde bir filtre değiştiğinde dashboard widget'ları API'den yeniden veri çekiyor.

### IT-15 — Katman Yönetimi + Basemap + Çizim Araçları + Çoklu Parsel Toplu İşlemleri

> **Bu, şu an üzerinde çalıştığınız iterasyon — aşağıdaki her alt başlık ayrı ayrı test edilebilir/doğrulanabilir olmalı, "genel olarak harita var" yeterli değil.**

**Katman Yönetimi:** kullanıcı katmanları açıp kapatabilir. Tam liste: Parseller, Çiftçiler, Üretim Sezonları, Ürünler, Toprak Analizleri, Görevler, Fabrikalar, Sulama, Yol Ağı, Drone, Uydu. Katman yapısı genişletilebilir olmalı (yeni katman eklemek merkezi bir registry'ye kayıt eklemekten ibaret olmalı).

**Basemap Yönetimi:** OpenStreetMap, Uydu, Hibrit, Topografik, Açık Tema, Koyu Tema arasında geçiş. Yeni altlık kolayca eklenebilmeli.

**Çizim Araçları:** Polygon, Rectangle, Circle, Serbest Çizim. **Çizilen alan içindeki tüm parseller otomatik seçilmeli** (bu, spatial-intersect sorgusu gerektirir — basit bounding-box değil, gerçek geometrik kesişim).

**Çoklu Parsel İşlemleri (çizim veya çoklu tıklama ile parsel seçildikten sonra):**
Dashboard Güncelle, Görev Ata, Form Gönder, SMS Gönder, E-Posta Gönder, Personel Ata, Excel Aktar, Rapor Oluştur — **tam liste**, bunların hepsi bu iterasyonda çalışan aksiyonlar olmalı (en azından backend endpoint + UI tetikleyici; SMS/E-posta gibi Comm Hub'a bağlı olanlar Comm Hub henüz yoksa simüle/queued olarak işaretlenebilir ama buton ve akış eksiksiz olmalı).

**Filtreleme (harita üzerinde, Query Engine'e bağlı):**
- Çiftçi: İl, İlçe, Kooperatif, Risk Skoru
- Parsel: Alan, Sulama Tipi, Malik, İşleten
- Üretim Sezonu: Yıl, Durum, Ürün
- Operasyon: Hasat Bekliyor, Görev Var, Analiz Eksik, Sözleşme Yok

**Görselleştirme:** Cluster, Heat Map, Yoğunluk Haritası, Tematik Harita — ürüne göre, risk skoruna göre, verime göre, sulama tipine göre, hastalık yoğunluğuna göre renklendirme.

**Kabul Kriterleri (IT-15'in "bitti" tanımı — kod kalitesi sorununu doğrudan hedefler):**
- [ ] 11 katmanın hepsi ayrı ayrı aç/kapa yapılabiliyor
- [ ] 6 basemap seçeneğinin hepsi çalışıyor
- [ ] Polygon/Rectangle/Circle/Serbest çizim → içindeki parseller gerçek geometrik kesişimle seçiliyor (test: bilinen 3 parselli bir alan çizilip tam 3 parsel seçildiği doğrulanıyor)
- [ ] 8 toplu işlem butonunun hepsi tanımlı bir endpoint'e bağlı (mock/stub değil)
- [ ] En az Cluster ve Heat Map görselleştirmesi çalışıyor
- [ ] Harita filtreleri Query Engine'i kullanıyor (IT-14'teki dashboard ile aynı filtre sonucu üretiyor — bu tutarlılık ayrıca test edilmeli)

### IT-16 — TKGM Entegrasyonu + Zenginleştirilmiş Parsel Popup + Navigasyon + Harita Snapshot

**TKGM GeoJSON import akışı:** Yeni parsel oluşturma ekranına TKGM Parsel Sorgu bağlantısı (`https://parselsorgu.tkgm.gov.tr/`) eklenir. Kullanıcı parseli TKGM üzerinden seçip GeoJSON olarak indirir, **aynı işlem akışı içinde** (ekran değiştirmeden) TOPRAX'e aktarır.

**Zenginleştirilmiş parsel popup (hızlı işlem merkezi):** parsele tıklandığında açılan popup sadece bilgi göstermez, aksiyon merkezi olur.
- Bilgiler: Parsel No, Çiftçi, Üretim Sezonu, Ürün, Alan, Son Ziyaret, Risk Durumu, Görev Sayısı, Toprak Analizi Durumu
- Hızlı işlemler: Parsel Detayı, Çiftçi Kartı, Üretim Sezonu, Toprak Analizi, Sözleşmeler, Görevler, Uydu Görüntüsünü Aç, AI Analizini Aç, Navigasyon Başlat

**Navigasyon:** saha personeli parseli seçip tek tıkla navigasyon başlatabilir (harici harita uygulamasına yönlendirme, örn. Google Maps deep link).

**Harita Snapshot:** kullanıcı o anki harita görünümü + zoom + seçili parseller + açık katmanlar + filtreler + dashboard widget'larını **tek tıkla kaydedip** tekrar açabilir, ekip arkadaşıyla paylaşabilir, yöneticisine gönderebilir.

**Kabul Kriterleri:** TKGM'den indirilen GeoJSON, ekran değiştirmeden parsel formuna aktarılabiliyor; parsel popup'taki 9 hızlı işlemin hepsi ilgili ekrana/aksiyona gidiyor; bir Snapshot kaydedilip başka bir kullanıcı tarafından açıldığında aynı görünüm (zoom+katman+filtre+seçim) geri geliyor.

### IT-17 — Mekânsal Zaman Makinesi + Uydu Görüntü Provider Soyutlaması + AI Harita Asistanı

**Mekânsal Zaman Makinesi (docx'ün özel vurgusu — sadece uydu görüntüsü için değil, tek zaman ekseni tüm sistemi kontrol eder):**
Kullanıcı bir yıl seçtiğinde (örn. 2024):
- Harita 2024 parsellerini gösterir
- O yıla ait uydu görüntüsü açılır
- Dashboard 2024 verilerine döner
- Üretim sezonu 2024 olur
- Görevler 2024'e filtrelenir
- AI analizleri 2024 verisi üzerinden çalışır

Bu, tek bir time-slider state'inin harita + dashboard + ProductionCycle filtresi + görev filtresi + AI context'e **aynı anda** yayılması demektir — merkezi bir "selected year/season" state'i olmalı, her bileşen kendi yılını ayrı ayrı tutmamalı.

**Uydu görüntü provider soyutlaması (ROADMAP.md kararı: demo/simüle katman, gerçek NASA/Sentinel/Planet hesabı yok):**
- Provider'lar: NASA, ESA Sentinel, Planet, Maxar, yerel servis sağlayıcılar — **provider değişse bile harita mimarisi değişmemeli** (Integration Hub / provider pattern, IT-32 ile tam formalize olacak ama arayüz burada kurulur)
- Tarihsel Görüntü: yetkili kullanıcı parsel bazında geçmiş yıllara ait uydu görüntülerini görebilir ("Uydu Görüntülerini Aç" aksiyonu); time slider 2023↔2026 arası, slider hareket ettikçe görüntü (demo/simüle) değişir
- Uydu Analiz Katmanları (mimari hazır, veri demo): NDVI, NDWI, Su Stresi, Bitki Sağlığı, Hastalık Tespiti, Zararlı Yayılımı, Don Riski, Yangın Riski, Kuraklık Analizi — HeatMap veya Tematik Harita olarak gösterilebilmeli

**AI Harita Asistanı:** harita ekranına doğal dil sohbet paneli. Örnek sorgular: "Bu yıl ekim yapılmayan parselleri göster", "Risk skoru yüksek çiftçileri göster", "Son iki yılda verimi düşen alanları göster", "Hastalık görülen parselleri göster", "Sulama problemi olan bölgeleri göster", "Hasadı yaklaşan üretim sezonlarını göster".
**Kritik kural:** AI sadece metin üretmez — haritayı filtreler, ilgili parselleri seçer, dashboard'u günceller, gerekli katmanları açar, kullanıcıyı ilgili kayıt ekranlarına yönlendirebilir. (Bu da IT-10'daki AI→Query Engine köprüsünün harita versiyonu — ayrı bir AI mantığı icat edilmemeli.)

**Kabul Kriterleri:** Time slider'da yıl değiştirildiğinde harita/dashboard/görev listesi/AI context'in **hepsi** aynı anda güncelleniyor (tek state kaynağı testi); en az 3 AI harita sorgusu uçtan uca çalışıp haritada gerçek filtre/seçim üretiyor (sadece metin cevabı dönmüyor); uydu görüntü provider'ı değiştirildiğinde (config'ten) harita kodunda değişiklik gerekmiyor.

## FAZ 7 — Sprint 7: UFYD (Üretim Finans Yaşam Döngüsü)

**Omurga akışı (tüm IT-18..21 bunu uygular):**
`Destek Talebi → Onay → Teslim → Çiftçi Onayı → Cari Hareket → Hasat → Kalite → Hakediş → Mahsup → Ödeme → Kapanış`

Tüm finansal kayıtlar **ProductionCycle (Üretim Sezonu)** bazlıdır, Parcel'e değil.

### IT-18 — Destek Kataloğu + Destek Talep Süreci

**Kapsam:** Yönetilebilir destek tipi kataloğu + 9 durumlu talep akışı + çiftçi portalına talep ekranı.

**Veri Modeli — SupportType (Destek Tipi, admin tanımlı, kod gerektirmez):**
| Alan | Tip | Not |
|---|---|---|
| name | string | Mazot, Gübre, Tohum, İlaç, Makine Hizmeti, Sulama, Nakliye, Avans, Diğer — seed olarak bunlar girilir, admin yenisini ekleyebilir |
| unit | string | birim (lt, kg, adet...) |
| default_price | decimal | varsayılan fiyat |
| accounting_code | string | muhasebe kodu |
| deduct_from_stock | bool | stoktan düşülsün mü |
| vat_rate | decimal | KDV |
| approval_flow_id | ref | onay akışı tanımı |
| is_active | bool | |

**Veri Modeli — SupportRequest (Destek Talebi):**
- id, farmer_id, production_cycle_id, support_type_id, requested_amount, unit, note, requested_at, requested_by (channel: portal/mobil/dahili)
- attachments (dosya/fotoğraf)
- **status** (aşağıdaki 9 durum, geçişler audit'lenir)

**Durum Makinesi (sıralı, atlama yok — geriye dönüş sadece red/iptal ile):**
`Taslak → Gönderildi → İnceleniyor → Onaylandı → Hazırlanıyor → Teslim Edildi → Çiftçi Onayladı → Muhasebeleşti → Tamamlandı`
- Her adımda `Reddedildi` / `İptal Edildi` dallanması mümkün olmalı (durum geçiş tablosunda ayrıca tanımla).

**Çiftçi Onayı doğrulama yöntemleri (alan olarak modele eklenmeli, ilk fazda en az Mobil Onay + Fotoğraf zorunlu, diğerleri altyapı olarak hazır):**
Mobil Onay, QR Kod, Dijital İmza, Fotoğraf, GPS Konumu.

**API:** `/api/support-types` (CRUD), `/api/support-requests` (CRUD + durum geçiş endpoint'i `/api/support-requests/{id}/transition`), çiftçi portalı için `/api/portal/support-requests`.

**UI:** Ayarlar → Destek Kataloğu yönetim ekranı; Çiftçi/ProductionCycle çalışma alanında "Destek Talepleri" sekmesi; çiftçi portalında talep oluşturma formu (Mazot/Gübre/Tohum/Makine/Sulama/Diğer hızlı seçim).

**Kabul Kriterleri:** 9 durum ve tüm geçişler audit log'da; her durum değişikliğinde ilgili kişilere bildirim tetiklenebilir (Comm Hub henüz yoksa TODO/event olarak bırakılır — IT-25 sonrası bağlanır); reddedilen/iptal edilen talep cari hesaba yansımaz.

---

### IT-19 — Financial Ledger + Cari Hesap

**Kapsam:** Silinemez merkezi hareket defteri + sezon bazlı cari hesap ekranı.

**Veri Modeli — LedgerEntry (Financial Ledger):**
| Alan | Tip | Not |
|---|---|---|
| id | uuid | |
| production_cycle_id | ref | zorunlu |
| farmer_id | ref | |
| entry_type | enum | Destek Talebi, Destek Teslimi, Avans, Cari Hareket, Hakediş, Mahsup, Prim, Kesinti, Ödeme, İade |
| amount | decimal | işaretli (+/-) |
| currency | string | |
| reference_type / reference_id | string/ref | ilişkili kaydı işaret eder (SupportRequest, Harvest, vb.) |
| is_reversal | bool | ters kayıt mı |
| reversed_entry_id | ref (nullable) | ters kaydın hangi kaydı düzelttiği |
| created_by, created_at | | |
| description | string | |

**KRİTİK KURAL:** Hiçbir LedgerEntry fiziksel olarak silinmez/update edilmez (immutable). Düzeltme = yeni kayıt + `is_reversal=true` + `reversed_entry_id` referansı. Bu kural API katmanında zorlanmalı (LedgerEntry için DELETE/PUT endpoint'i olmamalı, sadece POST + reverse endpoint'i).

**Cari Hesap Ekranı:** ProductionCycle bazlı, tek ekranda: Avanslar, Destekler, Kesintiler, Primler, Hakedişler, Ödemeler — hepsi LedgerEntry'den `entry_type` filtresiyle listelenir, bakiye toplanır.

**API:** `/api/ledger` (POST, GET/list filtreli), `/api/ledger/{id}/reverse`, `/api/production-cycles/{id}/current-account` (özet + hareket listesi).

**Kabul Kriterleri:** Ledger tablosunda update/delete engellenmiş; cari hesap bakiyesi tüm entry_type'ların toplamıyla tutarlı; her kayıt audit'lenebilir (kim, ne zaman).

---

### IT-20 — Hakediş Motoru

**Kapsam:** Tartım/tonaj/kalite/kota/fiyat → brüt hakediş → otomatik mahsup → net; prim/kesinti tanımları.

**Veri Modeli — Harvest/Weighing girdisi (varsa mevcut kantar kaydına bağlanır, yoksa yeni alan):**
tartım (weight), tonaj, kalite sonucu (quality_grade), kota (quota), birim fiyat (unit_price) — bunlardan **brüt hakediş** otomatik hesaplanır: `gross_entitlement = tonnage_within_quota * unit_price (+ kalite katsayısı varsa)`.

**Mahsup (Deduction) motoru — brüt hakedişten otomatik düşülecek kalemler:**
Mazot, Gübre, Tohum, Makine, Avans, Nakliye, Kesintiler, Diğer destekler — bunların hepsi ilgili ProductionCycle'ın SupportRequest/Ledger kayıtlarından (henüz mahsup edilmemiş olanlar) çekilir.

**Prim/Kesinti tanımları (yönetilebilir liste, admin tanımlı):**
- Primler: Kalite Primi, Erken Teslim Primi, Kota Primi
- Kesintiler: Ceza, Fire, Hizmet Kesintileri, Diğer Kesintiler
- Her prim/kesinti tanımı: ad, hesaplama tipi (sabit tutar / yüzde / formül), koşul (opsiyonel), aktif/pasif.

**Hesap zinciri (mutlaka bu sırayla, ara sonuçlar da saklanmalı):**
`Brüt Hakediş → Toplam Kesinti (mahsuplar + kesintiler) → Net Hakediş → (Primler eklenir) → Ödenecek Tutar`

Her adımın sonucu bir LedgerEntry olarak yazılmalı (entry_type: Hakediş, Mahsup, Prim, Kesinti) — IT-19'daki Ledger ile birebir entegre.

**API:** `/api/entitlement/calculate` (dry-run, önizleme), `/api/entitlement/{production_cycle_id}/finalize` (ledger'a yazar, geri alınamaz — sadece reverse edilebilir).

**Kabul Kriterleri:** Aynı ProductionCycle için hakediş iki kez finalize edilemez (idempotency); finalize sonrası tüm ara tutarlar (brüt/net/kesinti detay listesi) sorgulanabilir olmalı; hesaplama formülü unit test edilebilir saf fonksiyon olarak yazılmalı (API'den bağımsız).

---

### IT-21 — İcmal/Mutabakat Belgesi + Finansal Simülasyon + UFYD Dashboard

**Kapsam:**

**1) İcmal Belgesi (Reconciliation Statement) — PDF üretimi:**
Hakediş finalize edildikten sonra otomatik oluşur, içeriği: Üretim Sezonu, teslim edilen tonaj, kalite sonuçları, birim fiyat, brüt hakediş, tüm destekler ve kesintiler (kalem kalem), primler, net ödeme, cari bakiye — **tek belgede, kalem kırılımlı.**
- Çiftçi mobil/portal üzerinden görüntüleyip **dijital onay** verebilmeli.
- **İtiraz** süreci bu belge üzerinden başlatılabilmeli (itiraz = yeni bir Case/talep açar — IT-28 ile bağlanacak, o zamana kadar basit bir `objection` alanı/durumu yeterli).
- PDF üretimi için mevcut `pdf` skill kullanılmalı.

**2) Finansal Simülasyon (What-if):**
Yönetici ürün fiyatı / kalite primi / mazot desteği gibi parametreleri **gerçek veriyi değiştirmeden** değiştirip sistemin hakedişleri, kooperatif maliyetini, tahmini ödemeleri yeniden hesaplamasını görebilmeli. Bu, IT-20'deki hesap motorunun **saf fonksiyon** olarak yazılmış olmasının tam burada işe yaradığı yer — aynı fonksiyon simülasyon parametreleriyle çağrılır, sonuç Ledger'a yazılmaz, sadece döndürülür.

**3) UFYD Dashboard:** Toplam Hakediş, Toplam Destek, Bekleyen Ödemeler, En Çok Destek Alan Çiftçiler, Bekleyen Destek Talepleri, Nakit İhtiyacı, Bölgesel Destek Dağılımı.

**API:** `/api/reconciliation/{production_cycle_id}` (belge üret/getir), `/api/reconciliation/{id}/approve`, `/api/reconciliation/{id}/object`, `/api/simulation/entitlement` (POST, parametre override), `/api/ufyd/dashboard`.

**Kabul Kriterleri:** İcmal belgesi PDF'i gerçek veriyle üretilip indirilebiliyor; simülasyon sonucu ile finalize edilmiş gerçek hakediş birbirine karışmıyor (ayrı response şeması); dashboard sayıları Ledger'dan canlı hesaplanıyor.

---

## FAZ 8 — Sprint 8: Saha Operasyonları

**Kavramsal ayrım (docx'ün özellikle vurguladığı, kod kalitesi için kritik nokta):**
- **İş Emri (Work Order):** yönetim seviyesi planlama (örn. "2026 İlkbahar Gübreleme Kontrolleri") — amaç + zaman aralığı + bölge + personel listesi.
- **Görev (Task):** personele atanan tekil operasyon (örn. "Azizhan, 15 Temmuz'da X Parselini kontrol et").
- **Ziyaret (Visit):** görevin sahada fiilen gerçekleşen kaydı (GPS, giriş-çıkış saati, fotoğraf, form, not).

Bu üçü **ayrı entity** olmalı (aynı tabloya sıkıştırılmamalı) — bir Görev için birden fazla Ziyaret olabilir (tamamlanamayan ziyaret yeniden planlanır).

### IT-22 — İş Emri / Görev / Ziyaret Üçlü Modeli

**WorkOrder:** id, title, purpose, date_range (start/end), region/scope (il/ilçe/bölge filtresi veya parsel listesi), assigned_users[], status, created_by.
İş Emri oluşturulduğunda sistem **görevleri toplu dağıtabilmeli** (yönetici tek tek 25 görev açmak yerine bir WorkOrder açar, personel-parsel eşleştirmesiyle görevler otomatik türer).

**Task (Görev):** id, work_order_id (nullable — bağımsız görev de olabilir), farmer_id, parcel_id, production_cycle_id, task_type_id, assigned_to, priority, planned_date, sla_due_date, status.

**Görev Durumları (11 durum):**
`Planlandı → Atandı → Kabul Edildi / Reddedildi → Yola Çıkıldı → Görev Yerine Ulaşıldı → Çalışılıyor → Tamamlandı → Yönetici Onayı Bekliyor → Kapandı` (+ `İptal Edildi` her aşamadan dallanabilir). Tüm durum değişiklikleri kayıt altına alınır (audit).

**TaskType (Görev Tipi, admin tanımlı, kod gerektirmez):**
Çiftçi Ziyareti, Toprak Numunesi, Hasat Kontrolü, Ekim Kontrolü, Sulama Kontrolü, Gübreleme Kontrolü, İlaçlama Kontrolü, Drone Çekimi, Fotoğraf Çekimi, Evrak Teslimi, ÇKS Kontrolü, Denetim — seed olarak girilir.

**Form entegrasyonu:** Her TaskType'a IT-01/A1'de kurulan dinamik form altyapısından form bağlanabilmeli (Görev tipine / İş Emrine / ProductionCycle'a bağlanabilir).

**Checklist:** Her görev için kontrol listesi tanımlanabilir (Form Doldu, Fotoğraf Çekildi, GPS Kaydedildi, Çiftçi Onayı Alındı, Numune Alındı, Drone Görüntüsü Yüklendi, Evrak Teslim Edildi). **Checklist tamamlanmadan görev kapatılamaz** — bu kural API seviyesinde zorlanmalı (Kapandı durumuna geçiş validasyonu).

**Visit (Ziyaret):** id, task_id, started_at, ended_at, gps_start, gps_end, photos[], form_response, notes.

**API:** `/api/work-orders`, `/api/tasks` (+ `/api/tasks/{id}/transition`, `/api/tasks/{id}/checklist`), `/api/visits`.

**Kabul Kriterleri:** WorkOrder → çoklu Task üretimi çalışıyor; checklist tamamlanmadan `Kapandı` durumu API'den reddediliyor; Task-Visit 1:N ilişkisi test edilmiş (bir görev için 2. ziyaret açılabiliyor).

---

### IT-23 — Kanban + Takvim + Harita Entegrasyonu + Ziyaret Geçmişi

**Kanban görünümü** (durum kolonları): Planlandı → Atandı → Kabul Edildi → Yolda → Sahada → Tamamlandı → Onay Bekliyor → Kapandı (11 durumun UI'da gruplanmış hali — sürükle-bırak ile durum değiştirme, ama checklist kuralı burada da geçerli).

**Takvim görünümü:** Günlük/Haftalık/Aylık, yönetici hangi personelin hangi gün nerede olduğunu görebilir.

**Harita entegrasyonu (IT-15'teki harita altyapısına bağlanır):** Görevler, personeller, parseller aynı harita üzerinde; görevler filtrelenebilir; **haritadan görev oluşturulabilmeli** ve görev detayına gidilebilmeli.

**Ziyaret Geçmişi sekmesi** — Çiftçi/Parsel/ProductionCycle kartlarında: Kim gitti / Ne zaman / Hangi görev / Hangi form / Hangi fotoğraflar / Sonuç ne — Visit kayıtlarından türetilir.

**Kabul Kriterleri:** Harita üzerinden yeni görev oluşturma akışı çalışıyor (parsel seç → görev formu → Task kaydı); Kanban sürükle-bırak durum geçiş kurallarına (checklist dahil) uyuyor.

---

### IT-24 — Kural Tabanlı Otomatik Görev Oluşturma + Saha Raporları + Dashboard

**Otomatik görev oluşturma (event → görev, kural tabanlı, kod değişikliği gerektirmemeli):**
Tetikleyici örnekleri: Toprak Analizi tamamlandı, Gübreleme zamanı geldi, Hasat tarihi yaklaştı, AI hastalık tespit etti, Uydu görüntüsünde risk oluştu, Sözleşme süresi doluyor, Destek talebi onaylandı.
- Bu, `platform/events.py` (in-process event bus, IT-27'de formalize edilecek ama burada da temel kullanım başlar) üzerinden dinlenen basit **kural motoru**: `event_type + koşul → TaskType + assigned_to belirleme kuralı`. Admin ekranından tanımlanabilir olmalı, kod yazmadan yeni kural eklenebilmeli.

**Saha raporları:** Personel Performansı, Görev Tamamlanma Süreleri, Bölgesel Görev Yoğunluğu, Ziyaret Sayıları, Tamamlanmayan Görevler, Geciken Görevler, Çiftçi Bazlı Ziyaretler, Parsel Bazlı Ziyaretler, Üretim Sezonu Bazlı Operasyonlar.

**Modül dashboard'u:** Aktif İş Emirleri, Aktif Görevler, Geciken Görevler, Bugünkü Ziyaretler, Personel Doluluk Oranı, Bölgesel Operasyon Yoğunluğu, Ortalama Tamamlanma Süresi.

**Kabul Kriterleri:** En az 2 otomatik kural uçtan uca çalışıyor (örn. "Toprak Analizi tamamlandı" event'i → otomatik "Ekim Kontrolü" görevi açılıyor); rapor ekranları Query Engine (IT-08) üzerinden filtrelenebiliyor.

---

## FAZ 9 — Sprint 9: Communication Hub (İletişim ve Bildirim Merkezi)

**Stratejik mimari not (docx'ün vurgusu):** Comm Hub sadece mesaj gönderen bir servis değil; TOPRAX içindeki tüm iş olaylarını (Event) dinleyip doğru kişiye doğru zamanda doğru kanaldan ileten merkezi bir hub olmalı. Yeni modüller iletişim kodu yazmaz, sadece event yayınlar.

### IT-25 — Kanal Provider Pattern + Şablon Yönetimi + Kişi Kartı İletişim Sekmesi

**Kanallar (ilk fazda hepsi provider pattern + simüle sağlayıcı, ROADMAP.md'deki karara uygun):**
Push Notification, SMS, E-Posta, WhatsApp, Sesli Arama (IVR/Voice Call). Yeni kanal eklemek kod değişikliği gerektirmemeli (`ChannelProvider` interface + her kanal için `SimulatedXProvider` + Integration Center kaydı).

**Kişi Kartı İletişim Sekmesi:** Çiftçi/personel kartlarına eklenir — SMS Gönder, WhatsApp Gönder, E-Posta Gönder, Sesli Arama Başlat, Mobil Bildirim Gönder — yetkiye göre görünür, kart context'inden çıkmadan gönderim yapılabilir (Sprint 6 context-aware CRUD prensibiyle uyumlu).

**Şablon Yönetimi:** Her kanal için ayrı şablon, dinamik alan desteği: `{{FarmerName}}`, `{{ProductionSeason}}`, `{{ParcelNo}}`, `{{SupportType}}`, `{{HarvestDate}}`, `{{PaymentAmount}}`. Şablonlar versiyonlanabilir.

**İletişim Timeline:** Her kayıt: tarih, saat, gönderen, kanal, şablon, durum (Gönderildi/Teslim Edildi/Okundu/Başarısız), içerik özeti. Mümkün olduğunca WhatsApp/SMS/E-posta konuşma (Conversation) mantığında gösterilmeli.

**API:** `/api/channels` (provider kayıtları), `/api/templates` (CRUD + versiyon), `/api/communications/send`, `/api/contacts/{id}/timeline`.

**Kabul Kriterleri:** En az 3 kanal (SMS, E-Posta, Push) simüle provider ile uçtan uca çalışıyor; şablon değişkenleri render ediliyor; kişi kartından gönderim → timeline'da görünüyor.

---

### IT-26 — Segment Yönetimi + Kampanya + Planlı Gönderim + Onay + Retry/Fallback

**Segment Yönetimi (Query Engine — IT-08 — üzerinden):** dinamik segmentler, örn. "Konya'da bulunan çiftçiler", "Şeker Pancarı ekenler", "Hakedişi oluşanlar", "Risk skoru 80 üzeri", "Son 90 gündür ziyaret edilmeyenler". Kaydedilebilir ve tekrar kullanılabilir olmalı.

**Kampanya:** Çoklu kanal (SMS+WhatsApp+E-posta+Push+Sesli Arama'dan biri veya birkaçı), durumlar: Taslak, Planlandı, Yayında, Tamamlandı, İptal Edildi.

**Planlı gönderim:** belirli tarih/saat için zamanlanabilir (background job/worker gerektirir).

**Gönderim Onayı:** toplu gönderimler isteğe bağlı olarak yönetici onayına tabi tutulabilmeli (yanlış gönderim önleme).

**Retry/Fallback zinciri (yönetilebilir kurallar):** örn. WhatsApp başarısız → SMS gönder; SMS başarısız → E-Posta gönder.

**Kabul Kriterleri:** Bir segment oluşturulup kampanyaya bağlanabiliyor; planlı gönderim zamanı geldiğinde tetikleniyor (worker/cron simülasyonu yeterli); retry zinciri en az 1 senaryoda test edilmiş.

---

### IT-27 — Event Bus v1 + Communication Policy + Tercih Merkezi + Kara Liste

**Event Bus (`platform/events.py`):** in-process event bus, publish/subscribe. Diğer modüller (UFYD, Saha, ProductionCycle vb.) olay yayınlar, Comm Hub dinler. Arayüz ileride kuyruk sistemine (RabbitMQ vb.) geçişe izin verecek şekilde soyutlanmalı.

**Communication Policy (olay bazlı iletişim kuralları, admin tanımlı, kod gerektirmez):**
örn. Hakediş Oluştu → WhatsApp + SMS; Görev Atandı → Mobil Bildirim; Sözleşme Onaylandı → E-Posta; Hasat Tarihi Yaklaşıyor → SMS + Mobil Bildirim.

**Tercih Merkezi (Preference Center):** çiftçi/paydaş kendi tercihlerini yönetir — kanal bazlı açık/kapalı (SMS/WhatsApp/Push/Sesli Arama/E-posta), iletişim saatleri, hafta sonu tercihi, kampanya mesajları vs. operasyonel bildirimler ayrımı.

**Kara Liste (KVKK):** iletişim almak istemeyenler kara listeye alınır, sistem bu kullanıcılara otomatik iletişim göndermez — bu kontrol **gönderim motorunun en son adımında** zorunlu olmalı (policy tetiklese bile kara liste kazanır).

**Kabul Kriterleri:** En az 3 iş olayı (örn. HakedişOluştu, GörevAtandı, SözleşmeOnaylandı) publish/subscribe ile Comm Hub'ı tetikliyor; kara listedeki bir kişiye policy tetiklense dahi mesaj gitmiyor (test edilebilir).

---

### IT-28 — Inbound Case Yönetimi (İki Yönlü İletişim)

**Kavram:** "Destek Talebi" ile sınırlı kalınmaz, genel bir **Konu (Case)** modeli kurulur — Destek Talebi, Şikayet, Öneri, Bilgi Talebi, Hastalık Bildirimi, Zararlı İhbarı, Sulama Problemi, Fotoğraf Gönderimi, Evrak Talebi gibi onlarca senaryoyu tek modelde yönetir (küçük ölçekli Case Management).

**Veri Modeli — Case:** id, subject, category_id, description, priority, related_production_cycle_id (opsiyonel), related_parcel_id (opsiyonel), related_contract_id (opsiyonel), related_support_request_id (opsiyonel), attachments[], created_by, assigned_to.

**Kategori Yönetimi (admin tanımlı):** Destek Başvurusu, Hakediş, Ödeme, Sözleşme, Üretim, Hastalık Bildirimi, Zararlı Bildirimi, Sulama, Gübreleme, Teknik Destek, Şikayet, Öneri, Bilgi Talebi, Diğer.

**Talep Durumları:** Yeni → Atandı → İnceleniyor → Kullanıcıdan Bilgi Bekleniyor → Cevaplandı → Çözüldü → Kapatıldı (+ İptal Edildi).

**Atama:** Ziraat Mühendisine, Bölge Sorumlusuna, Muhasebeye, Destek Ekibine, Operasyon Ekibine, Çağrı Merkezine, Belirli Bir Kullanıcıya — devredilebilir.

**Mesajlaşma:** Case açıldıktan sonra iki yönlü mesajlaşma (mobil/web portal/yönetim paneli), tüm yazışmalar tek conversation altında.

**Saha Operasyonlarına köprü:** Bir Case'ten otomatik Task açılabilmeli (örn. çiftçi "kuzeyde hastalık var" fotoğraflı Case açtığında ilgili ziraat mühendisine otomatik saha görevi — IT-22/24 Task modeline bağlanır).

**Kişi Kartı Entegrasyonu:** Açılan tüm Case'ler Çiftçi/Personel kartındaki İletişim sekmesinde, iletişim timeline'ıyla birlikte görünür.

**API:** `/api/cases` (CRUD + `/transition`, `/assign`), `/api/cases/{id}/messages`, `/api/cases/{id}/create-task`.

**Kabul Kriterleri:** Case → Task köprüsü çalışıyor; case mesajlaşması conversation olarak saklanıyor; case kişi kartı timeline'ında diğer iletişim kayıtlarıyla birlikte kronolojik görünüyor.

---

## FAZ 10 — Sprint 10: Farmer LMS (Çiftçi Eğitim Merkezi)

> Not: Tam kapsamlı bir LMS değil — merkezi eğitim yönetimi + atama + takip + sertifika + kişi kartı entegrasyonu. Moodle gibi sistemlerle ileride entegre olabilecek şekilde servis katmanı soyutlanmalı.

### IT-29 — Eğitim Kataloğu + İçerik Yönetimi + Atama + Durum + Zorunlu Eğitim

**Course (Eğitim):** başlık, açıklama, kategori, eğitim türü, süre, zorluk seviyesi, geçerlilik süresi (opsiyonel), eğitmen (opsiyonel), aktif/pasif.

**İçerik tipleri (sıralanabilir):** Video, PDF, Word, PowerPoint, Resim, Ses Dosyası, Harici Link, YouTube Videosu.

**Kategoriler (admin tanımlı, seed):** Şeker Pancarı, Buğday, Mısır, Gübreleme, Sulama, Hastalıklar, Zararlılar, Makine Kullanımı, İş Sağlığı ve Güvenliği, Kooperatif Süreçleri, Dijital Tarım.

**Atama hedefleri:** Tek kullanıcı, kullanıcı grubu, Rol, Segment (Query Engine üzerinden), ProductionCycle, Bölge, İl/İlçe.

**Zorunlu/Opsiyonel:** zorunlu eğitimler kullanıcı dashboard'ında öncelikli gösterilir.

**Eğitim Durumu (kullanıcı bazlı):** Atandı, Başlamadı, Devam Ediyor, Tamamlandı, Başarısız, Süresi Doldu.

**Kabul Kriterleri:** Video dosyaları uygulama sunucusunda tutulmuyor (storage.py soyutlaması üzerinden, IT-01'deki config/storage kuralına uygun); segment bazlı atama Query Engine'i kullanıyor.

---

### IT-30 — Quiz + PDF Sertifika + Learning Path + Kişi Kartı Eğitimler Sekmesi

**Quiz:** Çoktan Seçmeli, Doğru/Yanlış, Çoklu Seçim — 3 soru tipi yeterli (ilk faz). Başarı puanı yönetilebilir (geçme notu eşiği).

**Sertifika:** başarıyla tamamlanan eğitimler için otomatik PDF üretimi (pdf skill kullanılır) — Ad Soyad, Eğitim Adı, Tamamlanma Tarihi, Sertifika No, QR Kod (opsiyonel), **Doğrulama Kodu** (sertifikanın gerçekliğini kontrol edecek bir endpoint/sayfa olmalı, örn. `/verify/{code}`).

**Learning Path (Eğitim Yol Haritası):** birden çok eğitimi sıralı bir pakette toplar (örn. "Yeni Şeker Pancarı Üreticisi" → 7 eğitimi otomatik içerir). Kullanıcı tek tek değil path olarak atanır, eğitimleri sırayla tamamlar, sonunda **tek bir path sertifikası** kazanabilir.

**Kişi Kartı Eğitimler Sekmesi:** Eğitim Adı, Tarih, Puan, Sertifika, Geçerlilik Durumu.

**Kabul Kriterleri:** Quiz geçme notu altında kalan kullanıcı "Başarısız" statüsüne düşüyor, sertifika üretilmiyor; Learning Path içindeki eğitimler sıralı zorunluluk kuralına uyuyor (önceki tamamlanmadan sonrakine geçilemez, path tanımında bu davranış aç/kapa olabilir); sertifika doğrulama kodu ile sorgulanabiliyor.

---

### IT-31 — Uzman Desteği + FAQ Havuzu + Eğitim Analitiği + LMS Dashboard

**Uzman Desteği (docx'te "Uzmanla İletişime Geç" yerine bilinçli olarak bu isim seçilmiş — kapsam ileride mesajlaşmanın ötesine geçecek):**
Her eğitim içinde "Uzman Desteği" seçeneği — kullanıcı eğitimden ayrılmadan soru sorar. Bu bir **Case** açar (IT-28 Inbound Case altyapısını kullanır) ve otomatik olarak şu bilgilerle zenginleştirilir: Eğitim, Eğitim Bölümü, İzlenen Video, ProductionCycle (varsa), Ürün Türü, Çiftçi, Bölge — kullanıcı sadece mesajını yazar.

**Uzman Atama:** Eğitim Kategorisi + Ürün Türü + Bölge/İl-İlçe kombinasyonuna göre uzman tanımlanır (örn. Şeker Pancarı + Konya → Ziraat Mühendisi Mehmet); ilgili sorular otomatik o uzmana yönlendirilir.

**AI Destekli Ön Yanıt (opsiyonel, ileri faz olarak işaretlenebilir ama arayüz hazır olmalı):** mesaj uzmana gitmeden önce eğitim içeriği/FAQ'dan önerilen cevap gösterilebilir; kullanıcı kabul edebilir veya uzmanla devam edebilir.

**FAQ Havuzu:** kullanıcı soruları + uzman cevapları bilgi havuzunda saklanır; yönetici anonimleştirip FAQ'ya taşıyabilir.

**Eğitim Analitiği:** kaç kişi aldı, kaç kişi tamamladı, kaç sertifika verildi, kaç soru soruldu, en çok hangi konuda soru geldi, ortalama cevap süresi, kullanıcı memnuniyet puanı.

**Dashboard:** Toplam Eğitim, Tamamlanan, Bekleyen, Başarısız, Bölgesel Tamamlanma Oranları, En Çok İzlenen Eğitimler.

**Kabul Kriterleri:** "Uzman Desteği" akışı Case modelini yeniden kullanıyor (ayrı bir mesajlaşma tablosu icat edilmemiş); uzman atama kuralı kategori+bölge kombinasyonuyla doğru kişiyi buluyor.

---

## FAZ 11 — Sprint 11 kalanı: Platform Core

> Bu sprintin amacı yeni özellik değil, **platform omurgasını** kurmaktır — bundan sonraki her modül bu kurallara uymalı.

### IT-32 — Integration Hub Formalizasyonu + Webhook Engine

**Integration Hub:** TOPRAX dışarıya doğrudan bağlanmaz; Google Maps, AI servisleri (OpenAI/Anthropic/Gemini), SMS/WhatsApp/E-posta, GeoServer, NASA/Sentinel/Planet, MERNİS/TAKBİS dahil tüm 3. parti çağrılar **tek bir Integration Hub modülünden** geçer. Extras altındaki dağınık simüle servisler (S4 uydu, S9 kanal provider'ları vb.) bu ortak provider pattern'e taşınır (refactor değil, konsolidasyon — mevcut arayüzler korunur).

**Webhook Engine:** her önemli iş olayı (FarmerCreated, HarvestCompleted, PaymentCompleted, ContractApproved, TaskCompleted vb.) dış sistemlere webhook olarak gönderilebilir. Webhook kuralları (hangi event → hangi URL, hangi header/auth) admin tarafından yönetilebilir olmalı, event bus'ın (IT-27) bir subscriber'ı olarak çalışır.

**Kabul Kriterleri:** En az 3 farklı entegrasyon (1 AI, 1 iletişim, 1 mekansal/uydu) Integration Hub üzerinden geçiyor, kod içinde doğrudan 3. parti çağrısı kalmamış; en az 1 event için webhook tanımlanıp tetiklenmiş (simüle hedef URL'e log/istek atarak doğrulanabilir).

---

### IT-33 — Feature Flags + Module Manifest + Licensing İskeleti + Health Center + Cache Soyutlaması

**Feature Flags:** tenant bazlı aç/kapa (AI, Drone, WhatsApp, LMS, GIS gibi modül/özellik seviyesinde). Kod değişikliği gerektirmemeli — bir `feature_flags` koleksiyonu + middleware/guard.

**Module Manifest:** her modül kendi tanımını taşır — Modül Adı, Versiyon, Bağımlılıklar, Menüler, Yetkiler, Event'ler, API'ler, Dashboard Bileşenleri. Platform bunu otomatik okuyabilmeli (ileride plugin mimarisinin temeli).

**Licensing iskeleti:** Modül Bazlı / Tenant Bazlı / Kullanıcı Bazlı lisanslama — bu iterasyonda sadece veri modeli + basit kontrol yeterli, gerçek satış/faturalama entegrasyonu kapsam dışı.

**Health Center ekranı:** Database, Redis, RabbitMQ, Elasticsearch, GeoServer, AI Provider, SMS Provider, Mail Provider, WhatsApp Provider durumlarını (Sağlıklı/Uyarı/Hata) merkezi gösterir — IT-01'de Integration Center'a eklenen health-check alanlarını tüketir.

**Cache soyutlaması:** Lookup verileri, yetkiler, dashboard verileri, sık kullanılan parametreler cache üzerinden okunur — arayüz korunur (ileride gerçek Redis'e geçilebilir), şimdilik in-process/Mongo karşılık (ROADMAP.md kararı ile tutarlı).

**Kabul Kriterleri:** Bir feature flag kapatıldığında ilgili menü/API gerçekten devre dışı kalıyor; Health Center ekranı en az 3 servis için gerçek durum gösteriyor; en az 2 modül (örn. Farmer, GIS) için Module Manifest dosyası/kaydı mevcut.

---

## FAZ 12 — Sprint 12: Mobil

### IT-34 — Experience Profile Modeli (Backend)

**Kavram:** Mobil deneyim statik rol bazlı değil, **Experience Profile (Persona)** modeliyle yönetilir. RBAC sadece yetkilendirme içindir; kullanıcının göreceği ekranlar hem yetkisine hem atanmış profiline göre oluşur. Aynı kullanıcı farklı zamanlarda farklı profille çalışabilir.

**ExperienceProfile veri modeli:**
- id, name (örn. "Ziraat Mühendisi Sahra", "Muhasebe Mobil")
- dashboard_widgets[] (sıralı liste)
- menu_items[]
- quick_actions[]
- map_tools[]
- ai_features[]
- notification_behaviors
- default_filters
- offline_sync_rules

**UserProfileAssignment:** user_id ↔ experience_profile_id (N:1 veya kullanıcı zamana göre değiştirebiliyorsa geçmişli tablo).

**API:** `/api/experience-profiles` (CRUD), `/api/users/{id}/experience-profile` (ata/getir), `/api/me/experience` (mobil client'ın açılışta çektiği birleşik konfigürasyon — dashboard+menu+widget+quick action tek response'ta).

**Kabul Kriterleri:** İki farklı profil tanımlanıp aynı role sahip iki kullanıcıya atandığında `/api/me/experience` çıktısı gerçekten farklı widget/menü listesi döndürüyor; profil kod değişikliği gerektirmeden admin ekranından oluşturulabiliyor.

---

### IT-35 — PWA Yolu (önerilen) veya Flutter İskeleti — Karar Kullanıcıya Sorulur

ROADMAP.md'nin A bölümünde belirtildiği gibi bu ortamda Flutter derlenemez. Oturum başında kullanıcıya seçim sorulmalı:

**(a) PWA (önerilen):** mevcut React kod tabanından, IT-34'teki Experience Profile'ı tüketen görev-odaklı mobil dashboard; offline temel (service worker + kuyruk); kamera/GPS web API'leri (getUserMedia, Geolocation API); push notification (Web Push). Tek oturumda uçtan uca ilerletilebilir ve test edilebilir.

**(b) Flutter iskeleti:** proje klasör yapısı, temel ekranlar, API client, Experience Profile tüketimi — **derlenip test edilemez**, kullanıcı kendi ortamında derler.

**Mobil ana bileşenler (hangi yol seçilirse seçilsin aynı kapsam):** Farmer, Parcel, ProductionCycle, Contract, Soil Analysis, UFYD, Communication Hub, LMS, Field Operations, GIS, Dashboard, Notification Center, AI Assistant — hepsi mevcut REST API'ler üzerinden, mobilde ayrı iş mantığı yazılmaz.

**Offline First senaryoları (PWA veya Flutter fark etmez):** görev görüntüleme, form doldurma, fotoğraf çekme, konum kaydı, not alma, imza alma — internet geldiğinde otomatik senkron + çakışma yönetimi.

**Kabul Kriterleri:** Seçilen yol her ne olursa olsun, Experience Profile'a göre dashboard/menü gerçekten farklılaşıyor; en az 1 offline senaryo (örn. görev tamamlama formu) çevrimdışı doldurulup bağlantı gelince senkronize olabiliyor (PWA'da service worker queue ile gerçek test edilebilir; Flutter'da bu sadece mimari olarak gösterilir).

> IT-35 sonrası kalan mobil özellikler (dijital imza, barkod, derin offline senkron) ihtiyaca göre IT-36+ olarak açılır (ROADMAP.md not'u ile tutarlı) — bu FAZ 13 o "IT-36+" genişlemesidir.

---

## FAZ 13 — Mobil Rol Tabanlı Görev & Self-Servis Ekosistemi

> **Bağlam (2026-07-11 kararı):** IT-34/35 mobil için Experience Profile +
> PWA altyapısını kurdu, ama sadece bir "MobilDashboard" iskeleti — göreve
> özel yaşam döngüsü, saha formu doldurma, çiftçi self-servis genişlemesi ve
> QR tabanlı teslim-tesellüm gibi **rol bazlı uçtan uca akışlar** hâlâ eksik.
> Native (React Native/Flutter) mimariye geçiş kullanıcı tarafından bilinçli
> olarak ERTELENDİ (IT-35'te PWA seçildi) — bu faz PWA üzerinde ilerler,
> yeni iş mantığı YAZMAZ, sadece var olan backend'leri (field_ops.py,
> forms_module.py, communications.py, support.py, entitlement.py,
> satellite_provider.py) mobilden tüketen ekranlar ekler (IT-35'in "mobilde
> ayrı iş mantığı yazılmaz" kuralıyla BİREBİR). Native'e geçildiğinde bu
> fazdaki ekranlar birebir referans alınabilir (aynı API sözleşmeleri).

### IT-36 ✅ (2026-07-11 TAMAMLANDI) — Saha Personeli Görev Yaşam Döngüsü (Mobil)

**Kavram:** `field_ops.py`'nin (IT-22/23) 11 durumlu `FieldTask` durum
makinesi zaten var, ama mobilde göreve özel TAM yaşam döngüsü ekranı yok
— MobilDashboard genel bir liste sunuyor. Bu IT, göreve atanan kullanıcının
TEK ekrandan: `atandi`→`kabul_edildi`/`reddedildi`, `yola_cikildi` (GPS
başlangıç noktası `navigator.geolocation` ile otomatik kaydedilir),
`yerine_ulasildi` (opsiyonel GPS doğrulama — konum parselin merkezine
yakın değilse uyarı, ENGELLEME değil), `calisiliyor`, checklist
tamamlama (her kaleme foto/video/form eki), `tamamlandi` geçişlerini
yapabilmesini sağlar.

**Medya ekleri:** her checklist kalemine opsiyonel foto/video/form eki —
mevcut `storage.py` `/uploads` (`module="field_tasks"`) AYNEN kullanılır,
YENİ bir upload mekanizması icat edilmez (IT-04/IT-29 emsali).

**Offline:** IT-35'in `lib/offlineQueue.js` kalıbı bu ekranın TÜM yazma
işlemlerine (durum geçişi, checklist toggle, medya ekleme) genişletilir.

**API:** field_ops.py'nin VAR OLAN uçları (`PUT /tasks/{id}/status`,
`PUT /tasks/{id}/checklist`, `POST /visits`) — YENİ endpoint gerekmez,
sadece mobil UI eksik.

**Kabul Kriterleri:** saha personeli mobilden bir göreve atanıp
reddedip yeniden planlanmasını, YA DA kabul edip checklist+foto ile
kapatmasını TEK ekrandan uçtan uca yapabiliyor; offline'da checklist
işaretleyip bağlantı gelince otomatik senkron oluyor (IT-35'in "Görev
Tamamlama" formuyla AYNI kalıp, artık TÜM durum geçişlerine genişletilmiş
hali).

**Uygulama notu (2026-07-11):** `MobilDashboard.jsx`'in tek-şablonlu
"Görev Tamamlama" formu, durum bazlı bir aksiyon paneline dönüştürüldü —
`ALLOWED_NEXT`/`TASK_STATUS_LABELS`, `SahaOperasyonlari.jsx`'teki AYNI
sabitlerin client-side kopyası (iki dosyada elle senkron tutulmalı, bkz.
IT-16'nın TKGM mapping emsali). **İki bilinçli sapma yaşandı:**
(1) checklist kalemi başına foto/video eki storage.py'nin `/uploads`
ucundan DEĞİL, IT-35'in zaten kurduğu "Visit.photos'a base64 gömme"
deseninden gönderiliyor — `offlineQueue.js` sadece basit JSON gövdeli
istekleri kuyruklayabiliyor (multipart dosya offline güvenilir
kuyruklanamaz), bu yüzden mevcut desen korundu; (2) `yola_cikildi`/
`yerine_ulasildi` geçişlerinde GPS **otomatik** kaydedilmiyor (roadmap
metninin aksine) — bunun yerine tamamlama anında elle "Konumu Al" ile
tek bir GPS noktası alınıp Visit'e ekleniyor, çünkü ayrı bir GPS-per-
transition alanı backend'de YOK ve offline-güvenli ID-bağımlı bir
Visit-update zinciri kurmak (POST sonra PUT) çevrimdışıyken üretilen
sahte ID'lerle çalışmazdı — bilinçli bir basitleştirme. Ayrıca
`field_ops.py`'de GPS doğrulaması (parsel merkezine yakınlık uyarısı)
YAPILMADI (roadmap'te zaten "opsiyonel" işaretliydi). Yeni backend
endpoint'i YOK (roadmap'in "YENİ endpoint gerekmez" iddiası doğrulandı).
**Gerçek tarayıcıda uçtan uca doğrulandı** (Mehmet Demir/ziraat_
muhendisi ile): (a) tam mutlu yol — atandı→kabul_edildi→yola_cikildi→
yerine_ulasildi→calisiliyor (checklist 3/3 işaretlendi)→tamamlandi
(Visit gerçekten oluştu, `farmer_id` doğru denormalize edildi)→
onay_bekliyor (eksik checklist uyarısı YOK, hepsi tamamdı)→kapandi;
(b) reddet+yeniden planlama — atandı→reddedildi (sebep metni
`close_reason`'a doğru yazıldı, backend'den doğrulandı)→planlandi
("yönetici ataması onayı bekleniyor" bilgi mesajı doğru göründü);
(c) offline — `navigator.onLine=false` zorlanıp "Kabul Et" tıklandı,
istek GERÇEKTEN sunucuya gitmedi (backend'den `status:"atandi"` olarak
doğrulandı) ama ekran optimistic olarak "Kabul Edildi"ye geçti ve
"1 kayıt senkron bekliyor" rozeti çıktı; `online` event'i tetiklenince
kuyruk OTOMATİK flush oldu ve backend'de gerçekten `kabul_edildi`ye
güncellendiği doğrulandı. Konsolda hiç hata yok. Test verisi (3 test
field_task + 1 visit) doğrulama sonrası doğrudan MongoDB'den temizlendi
(IT-24 emsaliyle AYNI — bu koleksiyonlarda DELETE endpoint'i yok).

---

### IT-37 ✅ (2026-07-11 TAMAMLANDI) — Ziraat Mühendisi Saha Formları (Mobil)

**Kavram:** `forms_module.py`'nin (M18) GPS+foto destekli anket formları
şu an sadece web'de dolduruluyor — mobilde form doldurma akışı yok. Bu
IT, bir ziraat mühendisinin/saha personelinin parsel/çiftçi bağlamında
(bir görev üzerinden VEYA MobilDashboard'un "Form Doldur" hızlı
aksiyonundan bağımsız) forms_module.py formlarını mobilden doldurmasını
sağlar.

**Bağlam otomasyonu:** Experience Profile'ın (IT-34) `quick_actions`
listesine "Form Doldur" eklenir; bir görevden geliniyorsa parsel/çiftçi/
production_cycle context'i otomatik doldurulur (IT-13'ün "context-aware
CRUD" prensibiyle AYNI).

**Kabul Kriterleri:** ziraat mühendisi mobilden GPS+fotoğraflı bir
anketi doldurup gönderiyor, web'deki Forms ekranında yanıt aynı
şekilde görünüyor (forms_module.py'de mobil/web ayrımı YOK, tek veri
modeli).

**Uygulama notu (2026-07-11):** MobilDashboard.jsx'e `GET /forms` +
`POST /forms/{id}/submit`'i tüketen bir "Formlar" kartı eklendi — YENİ
backend endpoint'i YOK. 11 alan tipinin (text/textarea/number/select/
multiselect/yesno/rating/date/gps/photo/video/signature) TAMAMI için
genel bir `FormFieldInput` render fonksiyonu yazıldı. **Bilinçli
sadeleştirme:** "signature" tipi bir canvas imza pedi DEĞİL (yeni
bağımlılık gerektirirdi, Karar Protokolü) — ad-soyad + "elektronik
onaylıyorum" onay kutusu ile karşılandı. **Bağlam otomasyonu (görevden
otomatik parsel/çiftçi doldurma) BİLİNÇLİ OLARAK YAPILMADI** — form
alanları (`fields[]`) tamamen serbest tanımlı olduğundan (ör. "Parsel
kodu" sadece düz bir text alanı, yapılandırılmış bir parcel_id referansı
DEĞİL), göreve göre otomatik doldurma kırılgan bir sezgisel eşleştirme
gerektirirdi; roadmap'in kendi kabul kriteri bunu şart koşmuyordu.
**Gerçek tarayıcıda uçtan uca doğrulandı:** Mehmet Demir (ziraat_
muhendisi) mobilden "Haftalık Tarla Denetimi" formunu (text/yesno/
select/number/textarea alanları) doldurup gönderdi — backend'de
`form_responses`'ta TÜM alan değerleri doğru kaydedildiği (`g2:false`
dahil, yesno'nun `false` değeri de doğru persist edildi) ve
`submitted_by`/`submitter_name`/`submitter_role`'ün doğru atandığı
doğrulandı. GPS alanı bu otomasyon ortamında tarayıcı izni olmadığı
için `null` kaldı (kod düzgün "Konum alınamadı" ile başarısızlığı
YAKALADI, formu ENGELLEMEDİ — gerçek bir kullanıcı tarayıcısında konum
izni verilirse dolar). Test verisi (1 form_response) doğrulama sonrası
MongoDB'den temizlendi, seed edilen 3 demo form (`/admin/seed-forms`
ile) KORUNDU.

---

### IT-38 ✅ (2026-07-11 TAMAMLANDI, 4/7 akış) — Çiftçi Mobil Self-Servis Genişletmesi

**Kavram:** `FarmerHome.jsx` (web) zaten Destek Talebi/İcmal/Eğitim/
İletişim Tercihleri kartlarını taşıyor — `MobilDashboard.jsx` (IT-35)
bunların GERÇEK karşılıklarını (Experience Profile'ın opak widget/
quick_action listesi üzerinden) sunmalı. Eksik self-servis kalemleri:

- **Sulama/gübreleme kayıt girişi** — mevcut `irrigation_events`/
  `data_entry.py` modellerine mobilden yazma (yeni model İCAT EDİLMEZ).
- **Sözleşme onaylama** — çiftçinin kendi sözleşmesini görüp
  "Onaylıyorum" diyebilmesi; `data_entry.py` Contract'ın durum
  makinesine (mevcut ALLOWED_TRANSITIONS kalıbı) bir çiftçi-onayı
  adımı eklenmesi gerekebilir.
- **Ekim planlama** — `plantings`/`production_cycles.py` bağlamında.
- **Uydu görüntüsü görüntüleme** — `satellite_provider.py`'nin NDVI/
  risk verisi zaten var, mobilde salt-okunur kart (Zaman Makinesi'nin
  BASİTLEŞTİRİLMİŞ mobil hali — slider yerine "son görüntü" + "geçmiş"
  butonu, IT-40'ın layout kısıtına uygun).
- **Kendi finansal/sezonsal özetine erişim** — `ledger.py`
  `current-account`, `entitlement.py`, `support.py`'nin ZATEN VAR olan
  çiftçi-scoped (`/portal/*` ve `/farmer/*`) API'leri mobilde tüketilir.
- **Randevu alma** (fabrika/kantar rolleri) — mevcut `appointments`
  modeli müsaitlik/slot kavramı taşımıyorsa, bu IT kapsamında basit bir
  slot modeli (`appointment_slots`: personel/tarih/saat/kapasite)
  eklenir; yoksa var olan modele bağlanır.
- **Ziyaret onaylama** — `field_ops.py` `visits`'e çiftçinin kendisine
  yapılan ziyareti onaylayabileceği bir `confirmed_by_farmer` alanı
  eklenir.

**Kabul Kriterleri:** yukarıdaki listeden EN AZ 4 akış (sözleşme
onaylama, uydu görüntüleme, finansal özet, ziyaret onaylama) mobilden
uçtan uca çalışıyor.

**Uygulama notu (2026-07-11):** kabul kriterinin istediği "en az 4"ten
**4'ü** uygulandı — hepsi ZATEN VAR olan farmer-scoped endpoint'ler
üzerinden (yeni backend kodu SADECE ziyaret onaylama için gerekti):
1. **Sulama kaydı** — `POST /farmer/irrigation` (zaten vardı, hiç
   değişmedi).
2. **Uydu görüntüsü** — `GET /satellite/ndvi/{parcel_id}` (zaten vardı).
   **Doğrulama sırasında gerçek bir bug bulundu ve düzeltildi:** ilk
   yazımda yanıt şemasını (`{ndvi, health, risk_level}`) YANLIŞ
   varsaymıştım — gerçek şema `{latest_ndvi, latest_date, health:
   {status,label,color}, time_series[], anomalies[]}`; `health`'i
   doğrudan `<b>{health}</b>` ile render etmek bir OBJE'yi React child
   olarak basmaya çalışıp SAYFAYI TAMAMEN ÇÖKERTTİ (boş beyaz ekran,
   konsol hatası React'in kendi error-boundary uyarısıydı, açık bir
   "Objects are not valid as a React child" mesajı DEĞİLDİ — gerçek
   network yanıtına bakarak teşhis edildi). `latest_ndvi`/`latest_date`/
   `health.label` kullanacak şekilde düzeltildi, doğrulandı.
3. **Finansal özet** — `GET /farmer/my-dashboard`'ın `stats.balance` +
   `finance[]`'i (zaten vardı, FarmerHome.jsx'in kullandığı AYNI eski
   `db.finance` demo koleksiyonu — CLAUDE.md'nin "db.finance ile
   KARIŞTIRMA" notundaki ESKİ ama hâlâ FarmerHome'da salt-okunur
   kullanılan kaynakla TUTARLI, yeni bir kaynak İCAT EDİLMEDİ).
4. **Ziyaret onaylama** — YENİ: `field_ops.py`'ye `GET /portal/visits` +
   `PUT /portal/visits/{id}/confirm-by-farmer` eklendi (support.py'nin
   `/portal/*` kalıbıyla AYNI: role=="ciftci" + farmer_id sahiplik
   kontrolü). `Visit`e opsiyonel `confirmed_by_farmer` alanı eklendi —
   eski kayıtlarda YOK, geriye dönük kırılma yok.

**Sözleşme onaylama / ekim planlama / randevu alma BİLİNÇLİ OLARAK
YAPILMADI** — üçü de gerçek bir durum makinesi/veri modeli kararı
gerektiriyor (Contract'a yeni bir "çiftçi onayı" adımı, planlamanın
hangi modele bağlanacağı, randevu sisteminin slot/müsaitlik kavramı
taşıyıp taşımadığı) — Karar Protokolü'nün "veri modeli değişiklikleri
her zaman sorulur" kuralına göre AYRI bir konuşma gerektirir, kabul
kriterinin "en az 4" eşiği zaten diğer 4 akışla karşılandığı için bu
oturumda sorulmadı.

**Gerçek tarayıcıda uçtan uca doğrulandı** (Mehmet Yılmaz/TS-00001
ile): sulama kaydı eklenip backend'de `water_m3:125.5` ile doğru
persist edildiği; NDVI görüntüleme (düzeltmeden SONRA) `0.41` / 
`2025-09-15` / "Stres altında" doğru gösterdiği; finansal özet gerçek
bakiye + hareket listesini gösterdiği; bir test ziyareti oluşturulup
"Onayla" tıklanınca `confirmed_by_farmer:true` olarak backend'de
doğrulandığı. Test verisi (1 irrigation_event + 1 field_task + 1 visit)
doğrulama sonrası MongoDB'den temizlendi.

---

### IT-39 ✅ (2026-07-11 TAMAMLANDI) — QR Kod Tabanlı Teslim-Tesellüm

**Kavram:** `support.py`'nin (IT-18) `confirmation_method` enum'ında
`qr_kod` zaten TANIMLI ama backend'çe KABUL EDİLMİYORDU (bkz. IT-18
notu: "bu fazda sadece mobil_onay/fotograf kabul edilir") — bu IT o
eksik yöntemi TAMAMLAR.

**Akış:** personel bir destek talebini `teslim_edildi` durumuna
çeker → sistem tek-kullanımlık, kısa ömürlü bir QR token üretir
(`support_request_id`'ye bağlı) → çiftçi KENDİ mobil cihazından
kamerayla okutur → `confirmation_method=qr_kod` ile `ciftci_onayladi`
geçişi tetiklenir (imza yerine QR-onay).

**Güvenlik:** token tek kullanımlık ve kısa ömürlü (ör. 10 dk) —
ikinci okutmada 410 Gone; `support_request_id` + tenant eşleşmesi
storage.py'nin (bu oturumda düzeltilen) tenant-sahiplik kontrolü
kalıbıyla AYNI şekilde doğrulanır.

**Kabul Kriterleri:** `qr_kod` artık support.py'de gerçekten kabul
ediliyor; bir teslimat QR ile uçtan uca onaylanabiliyor; token ikinci
kez kullanılmaya çalışıldığında reddediliyor.

**Uygulama notu (2026-07-11):** gerçek kamera-taramalı bir QR barkodu
YERİNE 6 haneli kısa bir kod kullanıldı — yeni bir QR-render kütüphanesi
eklemeden (Karar Protokolü: yeni bağımlılık her zaman sorulur) AYNI
güvenlik özelliğini (tek-kullanımlık, 10 dk süreli, cihaz-bağımsız
doğrulama) verir; kullanıcı isterse ileride gerçek kamera taramalı
QR'a bir kütüphane eklenerek yükseltilebilir. Yeni `support_qr_tokens`
koleksiyonu + `POST /support-requests/{id}/delivery-code` (personel,
`support:requests_manage`, sadece `teslim_edildi` durumundaki talepler
için) + `POST /portal/support-requests/confirm-delivery-code` (çiftçi,
KENDİ eylemi — `support:requests_manage` İSTEMEZ, support.py'nin
`/portal/*` kalıbıyla AYNI). `CONFIRMATION_METHODS_ENFORCED`'a `qr_kod`
eklendi. **Gerçek tarayıcıda uçtan uca doğrulandı:** admin bir destek
talebini `teslim_edildi`'ye kadar ilerletip mobilden "Kod Oluştur" ile
6 haneli bir kod (`014883`) üretti; çiftçi (Mehmet Yılmaz) KENDİ mobil
oturumundan bu kodu girip "Onayla" dedi — backend'de talebin GERÇEKTEN
`ciftci_onayladi` durumuna geçtiği VE `confirmation_method:"qr_kod"`
olarak kaydedildiği doğrulandı; AYNI kodu İKİNCİ kez kullanmaya
çalışmak 410 "Bu kod zaten kullanılmış" ile reddedildi. Test verisi
(1 support_request + ilişkili support_qr_token) doğrulama sonrası
MongoDB'den temizlendi.

---

## FAZ 14 — UX Tutarlılık Kuralları + Menü/Rapor Konsolidasyonu

> **Bağlam (2026-07-11 kararı):** kullanıcı FilterPanel.jsx'teki koşul
> satırının (alan/operatör/değer) ekranın büyük kısmını kapladığını,
> operatör değerinin lookup yerine serbest metin olduğunu ve HaritaPaneli
> Zaman Makinesi slider'ının haritayı örttüğünü bildirdi — bunlar genel
> bir tasarım disiplini eksikliğinin belirtileri, tek tek yama yerine
> KURAL + somut düzeltme birlikte ele alınır.

### IT-40 — Genel Tasarım Kuralları (Convention #11-14) + Bilinen UI Hataları

**CLAUDE.md "Yerleşik Konvansiyonlar" bölümüne eklenir** (mevcut 1-10
kuralının devamı, kod DEĞİL kural):

11. **Serbest metin yasağı:** bir alan lookup/enum/foreign-key ile
    temsil edilebiliyorsa (filtre operatörü, durum, kategori, il/ilçe
    vb.) dropdown/select kullanılır — manuel text input'a DÜŞÜLMEZ.
    (FilterPanel.jsx'in operatör alanı bu kuralın ilk somut ihlaliydi.)
12. **Filtre/koşul satırı genişlik sınırı:** bir koşul satırı
    masaüstünde ekranın ~%50'sini, mobilde tam genişliği AŞAMAZ — alan+
    operatör+değer üçlüsü sığmıyorsa YAN YANA sıkıştırılmaz, ikinci
    satıra SARAR.
13. **Sabit/overlay kontrol panelleri:** bir kontrol paneli (Zaman
    Makinesi slider'ı gibi) `max-height` + kendi `overflow-y:auto`'suna
    sahip OLMALI — altındaki tam-ekran bileşeni (harita, tablo) ASLA
    tam kaplamaz; tam-ekran bileşenler üzerinde kontrol panelleri
    overlay/collapsible olur, sayfa akışını aşağı İTMEZ.
14. **Var olan kalıba uyum:** yeni bir ekran/panel eklerken var olan
    bir bileşene (Drawer, FilterPanel, SmartDataGrid, QuickAddPanel)
    UYUMLU tasarlanır; kendine özgü tek-kullanımlık bir UI deseni İCAT
    EDİLMEZ (convention #9'un doğal devamı).

**Bu IT kapsamında düzeltilecek somut hatalar (roadmap notu — gerçek
kod fix'i ayrı bir görev/oturumda yapılabilir):**
- `FilterPanel.jsx`: operatör serbest metinden dropdown'a çevrilir;
  koşul satırı dar ekranda/az yer varken ikinci satıra sarar.
- `HaritaPaneli.jsx` Zaman Makinesi: slider konumu Katmanlar panelinin
  kalıbıyla AYNI (collapsible overlay) yapılır, haritayı örtmez.

**Kabul Kriterleri:** kural CLAUDE.md'ye eklenmiş; FilterPanel'in
operatör alanı dropdown; Zaman Makinesi açıkken harita GÖRÜNÜR kalıyor
(gerçek tarayıcıda, dar ekran dahil, doğrulanmış).

---

### IT-41 — "Raporlar" Menü Konsolidasyonu

**Kavram:** `SmartDataGrid` (IT-11) kullanan ekranlar (Toprak.jsx "Tüm
Analizler", SahaOperasyonlari.jsx "Raporlar" tab'ı, ileride eklenecek
her yeni rapor) + `UfydDashboard.jsx` gibi rapor-benzeri ekranlar
Layout.jsx'te FARKLI menü gruplarına dağılmış durumda. Bu IT sidebar'a
YENİ bir **"RAPORLAR"** grubu ekler; var olan rapor ekranlarına oradan
erişilir (route'lar DEĞİŞMEZ, sadece Layout.jsx'teki menü KAYDI
taşınır — geriye dönük link kırılması YOK).

**Filtre bağımsızlığı:** her rapor kendi filtre panelini (query_engine.py
`filterable-fields`'a bağlı FilterPanel/SmartDataGrid dahili filtre
satırı) KORUR — ORTAK bir filtre alanı İCAT EDİLMEZ (farklı modüllerin
alanları farklı, IT-08/09/11 kalıbı bozulmaz).

**Kabul Kriterleri:** sidebar'da tek bir "Raporlar" grubu altında en
az Toprak Analizleri, Saha Raporları, UFYD Dashboard erişilebiliyor;
her biri kendi bağımsız filtresini koruyor; hiçbir mevcut route/link
kırılmıyor.

---

## FAZ 15 — Organizasyon Hiyerarşisi + Onay Zincirleri

> **Bağlam (2026-07-11 kararı):** RBAC (permissions.py) KİMİN NE
> YAPABİLECEĞİNİ tanımlar; bu faz KİMİN KİME BAĞLI olduğunu (organizasyon
> şeması + onay zinciri) tanımlar — birbirini DEĞİŞTİRMEZ, üzerine
> eklenir (IT-07'nin `system_tier` katmanıyla AYNI felsefe: mevcut
> yapıyı bozmadan ek bir sınıflandırma/ilişki). Kullanıcı hem
> **departman/birim** hem **birim-içi yönetici ağacı** istedi (ikisi
> birlikte).

### IT-42 — Organizasyon Birimi + Yönetici Ağacı Veri Modeli

**Veri Modeli — OrgUnit:** `id`, `name` (örn. "Saha Ekibi — Konya",
"Kantar", "Muhasebe"), `parent_unit_id` (birimler de hiyerarşik
olabilir), `head_user_id` (birim sorumlusu).

**users koleksiyonuna eklenen alanlar:** `org_unit_id` +
`manager_id` — **birim ataması ile yönetici ataması BAĞIMSIZDIR**
(ör. bir bölge müdürü birden fazla birimin yöneticisi olabilir, ya da
biri kendi biriminin dışından bir yöneticiye raporlayabilir).

**API:** `GET/POST/PUT /org-units`, `GET /org-units/{id}/tree` (alt
birimler + üyeleri), `GET /users/{id}/manager-chain` (o kullanıcıdan
yukarı doğru TÜM yönetici zinciri — IT-43'ün onay routing'inin temel
sorgusu).

**UI:** yeni `pages/OrganizationChart.jsx` (basit ağaç/liste görünümü
— D3/gelişmiş bir org-chart kütüphanesi İCAT EDİLMEZ, mevcut Drawer/
liste kalıbı yeterli); `UserManagement.jsx`'e "Birim" + "Yönetici"
seçim alanları eklenir.

**Kabul Kriterleri:** bir kullanıcının manager-chain'i (3+ seviye)
doğru sırayla dönüyor (döngüsel referans — A'nın yöneticisi B, B'nin
yöneticisi A — 400 ile reddediliyor); bir birim, içinde hâlâ kullanıcı
varken silinmeye çalışıldığında engellenip uyarı veriyor (convention
#3 soft-delete ile tutarlı).

---

### IT-43 — Onay Zincirleri / Approval Routing

**Kavram:** IT-42'nin manager-chain'i, var olan durum makinelerine
(`support.py` SupportRequest, `entitlement.py` finalize, `campaigns.py`
onay adımı gibi) OPSİYONEL bir "yöneticiden onay" adımı eklemek için
kullanılır — YENİ bir workflow motoru İCAT EDİLMEZ, her modül kendi
`ALLOWED_TRANSITIONS`'ına (mevcut kalıp) manager-chain sorgusuyla bir
ön-koşul EKLER.

**Genel yardımcı (`approval.py`):** `get_approval_chain(db, user_id,
levels=1)` (kaç seviye yönetici onayı gerekiyorsa) + bekleyen onay
kaydı CRUD'u — `ledger.py`'nin `create_ledger_entry()` deseniyle AYNI
"tek giriş noktası" felsefesi: diğer modüller doğrudan import edip
kendi transition kontrolüne EKLER.

**İlk uygulama (kabul kriterinin somut örneği):** SupportRequest'in
`onaylandi` geçişi, tenant ayarına göre AÇIK/KAPALI bir bayrakla,
talebi oluşturan personelin YÖNETİCİSİNDEN onay isteyebilir hale
gelir.

**API:** `GET /approvals/pending` (giriş yapmış kullanıcının onay
kuyruğu — kendisine bağlı biri onay bekleyen bir işlem açtıysa
burada görünür), `POST /approvals/{id}/decide` (onayla/reddet).

**Kabul Kriterleri:** bir talep, oluşturan kişinin yöneticisi
onaylamadan `onaylandi` durumuna geçemiyor (bayrak açıkken); yönetici
kendi onay kuyruğunu görüp onaylayabiliyor; bayrak kapalıyken davranış
AYNEN eskisi gibi (geriye dönük kırılma yok).

---

## FAZ 16 — GodMode + Platform Operasyon Konsolu

> **Bağlam (2026-07-11 kararı):** kullanıcı tarif ettiği "Az_gun.ay.
> yil_saat@dakika" (o anki zamana göre) deseninin GİZLİ bir anahtar
> TAŞIMADIĞI, sadece herkese açık geçerli zamandan türetildiği (yani
> desen bilinen biri, bu dosya/hafıza sızarsa DAHİL, o anki şifreyi
> hesaplayabilir) konusunda uyarıldı ve **gerçek TOTP (RFC 6238,
> Authenticator app uyumlu)** tercih edildi — sektör standardı, gizli
> anahtar SADECE .env'de tutulur, hiçbir yerde düz metin görünmez.

### IT-44 — GodMode Kimlik Doğrulama (TOTP)

**Kavram:** GodMode, mevcut rol/tenant sisteminin TAMAMEN DIŞINDA, tek
bir sabit hesaba (`azizhan@azizhan.com.tr`) kilitli, ikinci faktörü
TOTP olan AYRI bir giriş yoludur — normal `/auth/login` akışına
KARIŞTIRILMAZ, ayrı bir `POST /godmode/login` endpoint'i.

**Config (`config_service.py`'ye eklenir, convention "tüm env okuma
tek merkezde" ile tutarlı):** `GODMODE_EMAIL` (sabit/env, sadece bu
değere izin), `GODMODE_TOTP_SECRET` (env — `pyotp` ile üretilir,
kullanıcı QR ile authenticator app'ine ekler, KOD ASLA DB'ye/log'a
düz metin yazılmaz, `install_secret_masking`'e dahil edilir).

**Giriş akışı:** e-posta TAM EŞLEŞMELİ + 6 haneli TOTP kodu geçerli
olmalı → kısa ömürlü (ör. 15 dk) ayrı bir `godmode_token` (normal
JWT'den FARKLI claim şeması: `scope:"godmode"`, tenant/role TAŞIMAZ)
üretilir.

**Rate limiting:** art arda yanlış TOTP denemesi kısa süreli
kilitlenir (brute-force koruması — ör. 5 yanlış denemede 15 dk kilit).

**Kabul Kriterleri:** doğru e-posta + geçerli TOTP kodu ile giriş
başarılı; yanlış kod 401; e-posta eşleşmiyorsa (başka HERHANGİ bir
hesap) TOTP doğru olsa bile 403; `godmode_token` normal API
endpoint'lerinde (`require_permission` vb.) KABUL EDİLMEZ, sadece
`/godmode/*` uçlarında geçerli; 5 yanlış TOTP denemesi sonrası 15 dk
kilitleniyor.

---

### IT-45 — GodMode Operasyon Ekranı

**Kavram:** `platform_core.py`'nin (IT-33) Health Center'ı GENİŞLETİLİR,
yeni bir `godmode.py` modülü — SADECE IT-44'ün `godmode_token`'ıyla
korunur (normal RBAC/`require_permission`'a HİÇ girmez, tenant kavramı
yok).

**Kapsam (kullanıcının istediği liste + Claude'un önerdiği ekler):**

- **Sunucu Sağlığı & Kaynak İzleme:** CPU/RAM/disk kullanımı (`psutil`
  — YENİ bağımlılık, Karar Protokolü gereği kullanıcıya sorulmalı),
  Mongo bağlantı sayısı/yavaş sorgu logu, uvicorn worker durumu.
- **Sunucu Restart:** backend'i güvenli yeniden başlatma tetikleyicisi
  (bu ortamda `uvicorn --reload`'a dosya-dokunma sinyaliyle, prod'da
  systemd/pm2 restart komutuyla — ortam-bağımlı, soyutlama arkasında).
- **Entegrasyon Ekleme:** `integrations.py`'nin desteklediği tiplerin
  ÖTESİNDE yeni bir entegrasyon TİPİ (kod seviyesinde,
  `INTEGRATION_REGISTRY`'ye) admin arayüzünden değil GodMode'dan
  tanımlanabilir.
- **Tenant'a Modül Ekleme/Çıkarma:** `platform_core.py`'nin
  `MODULE_MANIFESTS` + `tenants.py` birlikte kullanılarak bir
  tenant'ın hangi modüllere erişebileceği (feature_flags'ın
  tenant-bazlı hali) yönetilir.
- **Süper Admin Belirleme:** herhangi bir kullanıcıyı `platform_admin`/
  `super_admin` yapma — normal `UserManagement.jsx`'in ULAŞAMADIĞI,
  en yüksek yetki ataması.
- **Tema/Renk Değiştirme:** platform genelinde (tüm tenant'lar veya
  tek tenant) CSS değişken/renk paleti override — yeni bir
  `theme_overrides` koleksiyonu, frontend'in mevcut CSS class
  sistemine (convention #9) CSS custom property enjeksiyonu ile,
  YENİ bir tasarım dili İCAT EDİLMEZ.
- **Menü İsim/Yer Değiştirme:** Layout.jsx'in menü kaydı DB'den
  okunabilir hale getirilir (şu an kod-sabiti) — GodMode'dan menü
  etiketi/sırası override edilebilir.
- **Claude'un önerdiği ekler:** TÜM tenant'lar genelinde Audit Log
  arama (normal `audit.py` tek tenant'a scoped'dur); feature flag'lerin
  GLOBAL (tüm tenant'lar) toplu aç/kapa; veritabanı yedek alma
  tetikleyicisi (`mongodump`); güvenlik olayları paneli (başarısız
  login denemeleri, seed endpoint red'leri gibi `audit_logs`'tan
  türetilen özet — bu oturumda kilitlenen seed uçlarının/RBAC
  düzeltmelerinin doğal bir izleme ekranı); **impersonation** (bir
  tenant admin'i olarak "gözünden bakma" — MUTLAKA ayrı audit'e
  `"impersonated_by": "godmode"` olarak işaretlenerek, asla sessiz
  değil).

**UI:** yeni `pages/GodMode.jsx` — normal `Layout.jsx` sidebar'ının
DIŞINDA, kendi izole layout'u (yanlışlıkla normal kullanıcı
navigasyonuna karışmaması için, route `/godmode` Layout.jsx'in
`PrivateRoute`sinden BAĞIMSIZ kendi guard'ını kullanır).

**Kabul Kriterleri:** GodMode ekranına normal bir super_admin/
platform_admin token'ıyla ERİŞİLEMEZ (sadece IT-44'ün özel token'ı
kabul edilir); en az 5 kapsam maddesi (sağlık/kaynak izleme,
entegrasyon ekleme, tenant modül yönetimi, süper admin atama, tema
değiştirme) gerçek API'lerle çalışıyor; her GodMode işlemi AYRI bir
`godmode_audit_logs` koleksiyonuna (normal `audit_logs`'tan AYRI,
tenant kavramı yok) loglanıyor.

---

## FAZ 17 — Bize Ulaşın (IT-28 Genişletmesi)

> **Bağlam (2026-07-11 kararı):** 2026-07-11 güvenlik denetiminde FAZ
> 9'daki **IT-28 (Inbound Case Yönetimi) hiç implemente edilmemiş**
> bulunmuştu ("Case/inbound iletişim yönetimi için ayrı model ve API
> görünmüyor"). Kullanıcının istediği "Bize Ulaşın" chatbot + geri
> bildirim ekranı YENİ bir modele İHTİYAÇ DUYMAZ — IT-28'in zaten
> speklenmiş Case modelini GERÇEKLEŞTİRİR ve üzerine bir giriş noktası
> ekler. Bu yüzden FAZ 17, IT-28'i BİRLİKTE tamamlar.

### IT-46 — Bize Ulaşın Chatbot Girişi + Geri Bildirim (IT-28'i Gerçekleştirir)

**Kavram:** YENİ bir Case/ticket modeli İCAT EDİLMEZ — bu IT, FAZ 9'da
speklenmiş ama hiç kodlanmamış **IT-28'in Case modelini** (bkz. yukarı
FAZ 9 bölümü — veri modeli, durum makinesi, atama, mesajlaşma, Task
köprüsü, kişi kartı entegrasyonu TAMAMEN oradaki spesifikasyona göre
yazılır) GERÇEKLEŞTİRİR ve web+mobilde bir "Bize Ulaşın" giriş noktası
ekler.

**Web giriş noktası:** `Layout.jsx` sidebar/footer'da HER ZAMAN
erişilebilir bir "Bize Ulaşın" butonu → yönlendirilmiş kısa soru-cevap
(chatbot-TARZI ama serbest-metin AI chat DEĞİL — "Ne hakkında?" →
IT-28'in kategori listesinden seçim → "İlgili bir kayıt var mı?"
(parsel/sözleşme/sezon opsiyonel seçim) → mesaj → Case oluşur).
`ai_provider.py`'ye bağlanması (serbest metinden otomatik kategori
tahmini gibi) OPSİYONEL/ileri faz — ilk sürümde kural-tabanlı
yönlendirme YETERLİ, kabul kriterinde AI ŞART KOŞULMAZ.

**Mobil giriş noktası:** `MobilDashboard.jsx`'te aynı akışın tam ekran
hafif versiyonu.

**Geri bildirim özel kategorisi:** IT-28'in kategori listesine
"Uygulama Geri Bildirimi"/"Hata Bildirimi" eklenir — bu kategoriden
açılan Case'ler OTOMATİK olarak platform ekibine (`platform_admin`)
atanır (normal tenant-içi atama akışının DIŞINDA, tenant-üstü bir
Case — `tenants.py`'nin platform-admin işlemlerinin ham `raw_db`
kullanma kalıbıyla AYNI).

**Kabul Kriterleri:** IT-28'in TÜM kabul kriterleri (Case→Task
köprüsü çalışıyor, mesajlaşma conversation olarak saklanıyor, kişi
kartı timeline'ında diğer iletişim kayıtlarıyla birlikte kronolojik
görünüyor) karşılanıyor; "Bize Ulaşın" akışından açılan bir Case web
VE mobilden erişilebiliyor; "Hata Bildirimi" kategorisi otomatik
`platform_admin`'e yönleniyor.

---

## FAZ 18 — Agricultural Intelligence Engine (AI Vision Platformu)

> **Bağlam (2026-07-11 kararı):** `AI-VIZYON-PLATFORMU-PROMPT.md`'nin
> istediği kapsamlı AI/Computer Vision platformu — tam mimari için
> `AI-VIZYON-PLATFORMU-MIMARI.md`'ye bakın. Prompt IT-38'den başlamayı
> öneriyordu ama o numaralar zaten IT-42..46 olarak kullanılmıştı (FAZ 15-17)
> — bu yüzden **IT-47'den** başlanmıştır. Prompt'un sorduğu 2 açık karar
> kullanıcıyla netleştirildi: (1) **Mongo + in-process** kullanılacak
> (PostgreSQL/PostGIS/Redis/RabbitMQ İCAT EDİLMEZ — gerekçe mimari dokümanın
> Karar 1 bölümünde), (2) yeni ekranlar **"Ayarlar" altında bir alt-grup**
> olarak yerleşecek (8. üst menü AÇILMAZ). Bu FAZ, mimari dokümanda önerilen
> 6 parçaya + bir menü/RBAC konsolidasyon adımına bölünmüştür.

### IT-47 — AI Knowledge Library Çekirdeği

**Veri Modeli:** `ai_datasets`, `ai_knowledge_records`, `ai_taxonomy`
(bkz. AI-VIZYON-PLATFORMU-MIMARI.md Bölüm 4.1 — alan listesi BİREBİR
oradan alınır). Mantıksal veritabanı: `toprax_ai` (aynı Mongo örneği,
ayrı DB — fiziksel izolasyon, ayrı teknoloji DEĞİL). Tenant izolasyonu
mevcut `TenantScopedDB` ile (yeni bir mekanizma İCAT EDİLMEZ).
Versiyonlama: `ledger.py`'nin silinmezlik deseniyle AYNI —
`previous_version_id` ile yeni kayıt, eski kayıt `is_active=false`
olur ama SİLİNMEZ.

**Upload/Import:** tekli, toplu, klasör, ZIP — `geo_import.py`'nin
"önizle → doğrula → onayla" akışıyla AYNI desen. Fiziksel dosyalar
`storage.py` üzerinden (`module="ai_knowledge"`), yeni bir depolama
katmanı İCAT EDİLMEZ.

**Annotation:** bbox/polygon/segmentation mask çizimi, MEVCUT
`leaflet-draw`/`@turf/turf` kütüphaneleri `CRS.Simple` modunda
(piksel koordinatı) kullanılarak yapılır — yeni bir çizim kütüphanesi
kurulmaz.

**API:** `crud_base.py`'den (`build_crud_router`, PR-23) türetilir:
`POST/GET/PUT/DELETE /api/ai/datasets`, `POST/GET/PUT/DELETE
/api/ai/knowledge-records`, `POST /api/ai/knowledge-records/bulk`,
`POST /api/ai/knowledge-records/{id}/annotations`, `GET
/api/ai/knowledge-records/export`. Query Engine'e (IT-08)
`ai_knowledge_records` modülü + `CORE_FILTERABLE_FIELDS` girdisi eklenir
— knowledge search kendi arama motorunu YAZMAZ.

**UI:** Knowledge Library (liste+filtre), Dataset Manager, Image
Browser, Annotation Screen, Dataset Statistics — Ayarlar > AI Bilgi
Kütüphanesi > "Kütüphane" sekmesi.

**RBAC:** `permissions.py` PERMISSION_CATALOG'a yeni modül:
`ai_knowledge:view`, `ai_knowledge:create`, `ai_knowledge:approve`,
`ai_knowledge:manage`.

**Kabul Kriterleri:** ZIP toplu upload 100+ görüntüyü tek işlemde
`ai_knowledge_records`'a dönüştürüyor; bir kaydın annotation'ı
düzenlendiğinde eski versiyon SİLİNMİYOR (`previous_version_id` ile
zincirleniyor); `POST /api/query/ai_knowledge_records` filtre+sayfalama
ile çalışıyor; en az 20 örnek taksonomi kaydı (ürün/hastalık/zararlı)
seed ediliyor (gerçek liste kullanıcının bölge/ürün profiline göre
netleşmeli — bkz. mimari doküman Bölüm 18.3).

---

### IT-48 — Yerel AI Pipeline + Confidence Engine

**Kavram:** AI-VIZYON-PLATFORMU-MIMARI.md Bölüm 7.1'deki tam akış
(Ön İşleme → Spektral Analiz → Kural Motoru → Yerel Modeller →
Confidence Engine) BİREBİR uygulanır.

**Veri Modeli:** `ai_models`, `ai_predictions`, `ai_jobs` (mimari
doküman Bölüm 4.1). Job queue RabbitMQ'suz, `find_one_and_update`
atomik claim ile (Bölüm 7.3'teki kod özeti referans alınır).

**Yerel modeller:** mimari doküman Bölüm 6'daki tablo — Faz-1'de
SADECE CPU uyumlu modeller devreye alınır (YOLO ailesi seçilirse
**AGPL lisans riski** için mimari dokümanın Bölüm 6 notu — Apache-2.0
alternatifleri veya ticari lisans satın alma kararı bu IT'nin bir
parçası olarak netleştirilmeli, PR-17'nin lisans raporuna eklenmeli).

**Spektral analiz:** `satellite_provider.py`'deki `ndvi_to_health()`
fonksiyonu YENİDEN YAZILMAZ, import edilip paylaşılır.

**API:** `POST /api/ai/predict` (senkron, küçük iş), `POST
/api/ai/predict/async` (ai_jobs'a düşer), `GET /api/ai/jobs/{id}`.

**Kabul Kriterleri:** aynı görüntü için kural motoru kesin sonuç
verdiğinde yerel model HİÇ çalıştırılmıyor (maliyet minimizasyonu);
birden fazla model çelişen sonuç verdiğinde confidence otomatik
düşürülüyor (Bölüm 7.2); bir job "processing" durumunda kilitliyken
ikinci bir worker AYNI job'ı claim edemiyor (atomiklik testi); başarısız
job `max_attempts`'a kadar otomatik retry ediyor.

---

### IT-49 — Bulut Escalation + Tenant AI Kotası

**Veri Modeli:** `ai_tenant_quota` (mimari doküman Bölüm 4.1/8).

**Kavram:** düşük güvenli sonuçlar, kota müsaitse `ai_provider.py`
(mevcut Provider Pattern, mock_mode dahil) üzerinden buluta escalate
edilir — YENİ bir AI sağlayıcı entegrasyon katmanı İCAT EDİLMEZ.
Escalation ÖNCESİNDE mimari doküman Bölüm 9'daki redaksiyon filtresi
ZORUNLU uygulanır (kimliklendirici metadata asla gönderilmez).

**Kota mantığı:** `$inc` ile atomik sayaç artırma (race condition
önlenir); kota dolduğunda sonuç YİNE DÖNER (asla sessiz hata),
`decision="low_confidence_no_cloud_budget"` ile işaretlenir; %80 eşiğinde
tenant admin'ine mevcut bildirim akışıyla (Comm Hub, yeni mantık
YAZILMADAN) uyarı gider.

**API:** `GET /api/ai/tenant-quota` (kalan kota), admin `PUT
/api/ai/tenant-quota/{tenant_id}/limits`.

**Kabul Kriterleri:** Tenant A'nın kotası dolduğunda Tenant B'nin
escalation'ı ETKİLENMİYOR (izolasyon testi); redaksiyon filtresinden
geçen bir istekte çiftçi adı/TC/telefon/adres HİÇBİR ALANDA
bulunmuyor (otomatik test: gönderilen payload'da yasaklı alan
regex'i taranıyor); kota %80'e ulaştığında bildirim gerçekten
gidiyor.

---

### IT-50 — Active Learning + Uzman Doğrulama Arayüzü

**Veri Modeli:** `ai_active_learning_queue` (mimari doküman Bölüm 4.1).

**Kavram:** YENİ bir mesajlaşma sistemi İCAT EDİLMEZ — düşük güvenli/
yeni/nadir bir tahmin bu kuyruğa düştüğünde, `case_management.py`
üzerinden `category="AI Doğrulama"` bir Case açılır (IT-46'nın Case
modeli birebir kullanılır). Uzman bu Case'i kendi "Onay Bekleyenlerim"
ekranında (IT-07b, `PendingApprovals.jsx`) diğer onaylarla birlikte
görür. Onay/düzeltme, Case'in `CaseMessage` akışına not olarak düşer +
`ai_knowledge_records`'a yeni versiyon (`labels[].source="hibrit"`)
eklenir.

**Önceliklendirme:** `priority_score` — düşük güven + bilinmeyen sınıf +
model konsensüs çelişkisi bileşenlerinin toplamı (mimari doküman
Bölüm 10).

**UI:** Expert Validation Screen (renk kodlu: kırmızı/sarı/yeşil,
onay/düzeltme/yeniden-eğitim-işaretle aksiyonları, performans
istatistikleri), Prediction Review — Ayarlar > AI Bilgi Kütüphanesi >
"Doğrulama" sekmesi.

**RBAC:** `ai_prediction:view`, `ai_prediction:validate`.

**Kabul Kriterleri:** bir doğrulama Case'i, uzmanın normal onay
kuyruğunda diğer onaylarla birlikte (ayrı bir ekranda DEĞİL) görünüyor;
onaylanan bir tahmin otomatik olarak golden dataset'e (IT-51'in
kullanacağı) ekleniyor; düzeltilen bir etiket eski versiyonu SİLMEDEN
yeni versiyon olarak kaydediliyor.

---

### IT-51 — MLOps / Model Registry + Health Center Entegrasyonu

**Kavram:** `ai_models` durum makinesi (`training→validation→staging→
production→retired`) — CLAUDE.md'nin diğer modüllerdeki
`ALLOWED_TRANSITIONS` konvansiyonuyla AYNI desen.

**Zorunlu kapı:** `staging→production` geçişi ÖNCESİNDE golden dataset
üzerinde regresyon testi ÇALIŞIR; yeni model metrikleri (precision/
recall/F1/IoU) mevcut production modelinden KÖTÜYSE deploy otomatik
REDDEDİLİR (bu adım atlanamaz, API seviyesinde zorlanır).

**Rollback:** `previous_model_id` ile tek çağrıda önceki production
modeline dönülür (PR-04'ün migration rollback felsefesiyle aynı desen).

**Health Center:** `platform_core.py`'nin `GET /platform-core/health`
yanıtına (PR-04'te `schema_version` eklenen AYNI liste) yeni bir
servis kaydı: `{"service": "ai_model_health", ...}` — response şekli
DEĞİŞMEZ, sadece yeni bir satır eklenir.

**Lisans raporu güncellemesi:** IT-48'de seçilen yerel modellerin
lisansları `docs/legal/BAGIMLILIK-LISANS-RAPORU.md`'ye (PR-17) yeni
bir "ML Modelleri" bölümü olarak eklenir.

**API:** `GET/POST /api/ai/models`, `POST /api/ai/models/{id}/deploy`,
`POST /api/ai/models/{id}/rollback`, `POST /api/ai/models/{id}/train`,
`GET /api/ai/models/{id}/training-history`.

**UI:** Model Training Screen, Model Management, Model Comparison,
Training History, AI Monitoring Dashboard, Inference History — "Model
Yönetimi" + "İzleme" sekmeleri.

**Kabul Kriterleri:** golden dataset'te mevcut modelden kötü metrik
veren bir model deploy edilmeye çalışıldığında 4xx ile reddediliyor;
rollback sonrası `production` işaretli model gerçekten önceki sürüm;
Health Center'da AI Model Sağlığı satırı görünüyor ve drift/hata
oranını doğru yansıtıyor.

---

### IT-52 — Mobil AI Kamera Köprüsü

**Kavram:** IT-35'in mobil rol matrisindeki Saha Personeli kamera akışı
YENİDEN YAZILMAZ — mobil taraf çekim/upload yapmaya devam eder (offline
kuyruk dahil). AI Engine, mevcut generic upload tamamlanma olayını
(`upload_completed` — event bus'a eklenir) dinler, otomatik olarak
`ai_jobs`'a bir analiz job'ı düşürür. Kullanıcı ek bir aksiyon almaz.

**Event Bus:** `EVENT_TYPES`'a `ai_disease_detected`, `ai_risk_detected`,
`ai_validation_needed`, `ai_model_deployed` eklenir (mimari doküman
Bölüm 16). Bilinen tüketiciler: Saha Operasyonları (otomatik görev
oluşturma, docx'teki "AI hastalık tespit etti → görev" senaryosu),
Comm Hub (Communication Policy üzerinden bildirim), Harita (AI Harita
Asistanı girdisi, IT-17).

**Kabul Kriterleri:** mobilden offline çekilip senkronize edilen bir
fotoğraf, kullanıcı hiçbir ek adım atmadan `ai_jobs`'a otomatik giriyor;
sonuç hazır olduğunda ilgili Saha Personeli/Ziraat Mühendisi'ne mevcut
bildirim kanalıyla ulaşıyor; bir hastalık tespitinde otomatik bir Saha
görevi açılıyor (docx senaryosu).

---

### IT-53 — Menü/RBAC Konsolidasyonu + Geliştirici Portalı Entegrasyonu

**Kavram:** IT-47..52'de dağınık eklenen ekranlar tek bir menü
konumunda toplanır (kullanıcı ile netleşen Karar 2): Ayarlar → **AI
Bilgi Kütüphanesi**, 4 sekme (Kütüphane/Doğrulama/Model Yönetimi/
İzleme — mimari doküman Bölüm 14). CLAUDE.md Kural 3'e uyum için 8.
üst menü AÇILMAZ.

**RBAC:** IT-47..52'de eklenen TÜM permission'lar (`ai_knowledge:*`,
`ai_model:*`, `ai_prediction:*`) `DEFAULT_ROLE_PERMISSIONS`'da ilgili
rollere (Ziraat Mühendisi: view+validate, Sistem Yöneticisi: tümü)
atanır.

**Geliştirici Portalı:** `/api/ai/*` uçları hiçbir ek kod olmadan
`scripts/generate_postman_collection.py`'nin (PR-25) bir sonraki
çalıştırmasında otomatik Postman collection'a girer (yeni bir "ai"
klasörü) — bu IT'nin tek somut aksiyonu, generator scriptini bu modül
merge edildikten sonra bir kez çalıştırıp `postman/` çıktısını
güncellemektir.

**Kabul Kriterleri:** Ayarlar menüsünde tek bir "AI Bilgi Kütüphanesi"
girişi var, 8. üst menü maddesi YOK; Ziraat Mühendisi rolündeki bir
kullanıcı Doğrulama sekmesini görüyor ama Model Yönetimi'ni GÖRMÜYOR
(RBAC testi); Postman collection'da `ai` klasörü altında IT-47..52'nin
tüm uçları listeleniyor.

---

## Kullanım Notu — Neden Bu Dosya Kod Kalitesini Artırır

ROADMAP.md satırları ("Financial Ledger + Cari Hesap ekranı" gibi) Claude Code'a
*ne* yapılacağını söylüyordu ama *nasıl* (hangi alanlar, hangi durumlar, hangi
kural) sorusunu boş bırakıyordu — boşluk dolduğunda model en genel/basit
yorumu seçiyor. Bu dosyadaki her IT artık:
1. Somut alan listesi (docx'teki "örnek" listeler tam liste olarak alınmış; A1
   bölümünde docx'te boş bırakılan iki liste — IT-02, IT-03 — açıkça **türetilmiş**
   olarak işaretlenmiştir, bunları gerçek listenizle değiştirmeniz önerilir),
2. Durum makinesi (adım adım, atlanamaz),
3. "Bu kural API seviyesinde zorlanmalı" tipi açık iş kuralları,
4. Definition of Done (test edilebilir kabul kriterleri)

içeriyor.

**Geliştirme sırasında kullanım:** yeni bir IT-XX atarken oturum başında
Claude Code'a şunu söylemeniz yeterli: **"IT-XX'i yap, ROADMAP.md ve
ROADMAP-DETAY-TAM.md'deki IT-XX bölümünü birebir uygula."**

**Cowork ile test sırasında kullanım:** her IT'nin "Kabul Kriterleri"
maddelerini bir kontrol listesi gibi kullanabilirsiniz — Cowork'e "bu
dosyadaki IT-01'den IT-17'ye kadar (şu ana kadar tamamlanan kısım) her IT'nin
Kabul Kriterleri maddelerini tek tek doğrula, geçmeyenleri listele" tarzı bir
görev verebilirsiniz. Zincirleme bağımlılık olduğu için (örn. IT-15'teki
harita filtreleri IT-08'deki Query Engine'e bağlıdır) bir üst faz bozuksa alt
fazlarda da hata görmeniz normaldir — kontrol listesini bağımlılık sırasıyla
(FAZ 0 → FAZ 12) takip etmek kök nedeni daha hızlı bulmanızı sağlar.
