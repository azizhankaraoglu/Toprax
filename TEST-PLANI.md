# TEST-PLANI.md — TABSİS Tam Kapsamlı QA ve Standart Denetimi

> Bu doküman `ROADMAP-DETAY-TAM.md`'deki Kabul Kriterleri'nin **yerine
> geçmez**, onları test senaryosuna çevirir ve üstüne TABSİS'e özgü riskli
> noktaları (çok kiracılılık izolasyonu, finansal veri bütünlüğü, onay
> zinciri, GodMode, Türkçe locale) hedefleyen ek kontroller ekler. Referans
> sırası: `CLAUDE.md` (kural) → `ROADMAP-DETAY-TAM.md` (fonksiyonel kabul
> kriterleri) → bu dosya (test metodolojisi + kesişen kontroller + standart
> denetimi).

## Nasıl Kullanılır

- Modül modül verin: **"T-06'yı çalıştır"** (FAZ 2 — ProductionCycle testi).
- Ya da tamamını sırayla: FAZ 0'dan FAZ 13'e, sonra Kesişen Kontroller, sonra
  Backend/Frontend Standart Denetimi.
- Her test bloğunun sonunda **Bulgu Raporlama Formatı**'nı kullanarak bulunan
  her sorun ayrı ayrı raporlanır — "genel olarak çalışıyor" gibi özet
  değerlendirme kabul edilmez, her fonksiyon tek tek işaretlenir.
- Testler hem **UI üzerinden** hem **doğrudan API'ye istek atarak** (Postman
  collection — PR-25) yapılmalı; sadece UI testi RBAC/validasyon
  bypass'larını yakalayamaz (bkz. Kesişen Kontroller).

## Bulgu Raporlama Formatı (her bulgu için)

```
**Şiddet:** Kritik / Yüksek / Orta / Düşük
**Modül/IT:** (örn. IT-19 — Financial Ledger)
**Kategori:** Fonksiyon Hatası / Eksik Veri Alanı / Mantık Hatası /
              Rapor Boşluğu / Tasarım-Kullanılabilirlik / Standart İhlali
**Ne bekleniyordu:**
**Ne gözlemlendi:**
**Tekrar adımları:** 1. ... 2. ... 3. ...
**Öneri:**
```

Şiddet tanımı: **Kritik** = veri kaybı/bütünlük/güvenlik/çok-kiracılık
sızıntısı → yayına engel. **Yüksek** = ana iş akışını bloke eder ama
workaround var. **Orta** = kullanılabilirliği düşürür. **Düşük** = kozmetik.

Tüm bulgular tek bir `BULGULAR.md` dosyasında toplanır, şiddete göre
sıralanır; Kritik/Yüksek bulgular yeni IT-XX/PR-XX olarak ROADMAP.md'ye geri
beslenmeli (bu test kendi başına bir teslimat değil, düzeltme roadmap'inin
girdisidir).

---

## Genel Test Metodolojisi (her modülde uygulanır)

1. **Fonksiyonel:** İlgili IT'nin `ROADMAP-DETAY-TAM.md`'deki Kabul
   Kriterleri maddeleri tek tek, gerçek veriyle işaretlenir.
2. **Veri giriş alanı eksikliği:** Modülün gerçek iş akışında (docx'teki
   senaryolar + sizin bildiğiniz saha gerçeği) ihtiyaç duyulup formda
   olmayan bir alan var mı? Özellikle IT-02/IT-03 — bu alanlar dokümanda
   "türetilmiş" işaretliydi, gerçek ihtiyaçla karşılaştırılmalı.
3. **Mantık hatası:** Durum makineleri (her geçiş gerçekten tanımlı sırayı
   izliyor mu, atlama mümkün mü olmamalı ama mümkün mü?), hesaplama
   motorları (Hakediş — IT-20 — elle hesapla, sistemin sonucuyla karşılaştır),
   onay zincirleri (adım atlanabiliyor mu?).
4. **Rapor boşluğu:** Her raporda — boş veri durumu (0 kayıt varken ekran
   çöküyor mu?), filtre kombinasyonlarının tümü doğru sonuç veriyor mu,
   toplam/özet satırları gerçek veriyle tutarlı mı?
5. **Kullanılabilirlik/Tasarım:** `CLAUDE.md` Bölüm 4'teki Kural 1-4'e göre
   denetim (filtre paneli genişliği, harita floating kontroller, menü grubu,
   responsive).
6. **Standart:** aşağıdaki Backend/Frontend Standart Denetimi listesine göre.

---

## FAZ Bazlı Test Odak Noktaları

> Fonksiyonel checklist zaten `ROADMAP-DETAY-TAM.md`'de var — burada sadece
> **o modüle özgü, gözden kaçması muhtemel** riskli noktalar listelenir.

**T-01 (FAZ 0 — Config/Secrets):** `.env` dosyaları repoda mı sızmış kontrol
et; bir API key güncellendiğinde eski değerin hiçbir response'ta (network
tab dahil) düz metin görünmediğini doğrula; log dosyalarında `grep -i
"token\|password\|secret"` çalıştırıp sonuç çıkmadığını doğrula.

**T-02/03/04 (FAZ 1 — Veri Giriş):** Form Yönetimi'nden yeni bir alan
eklenip formda gerçekten göründüğünü doğrula (dinamik alan altyapısı canlı
mı yoksa hardcode mu); dosya upload'da yanlış tip/aşırı büyük dosya
denenerek server-side validasyon (client-side değil) olduğunu doğrula.

**T-05/06 (FAZ 2 — ProductionCycle):** Migration sonrası **eski kayıtların
hiçbiri kaybolmamış** mı (kayıt sayısı migration öncesi/sonrası eşleşiyor
mu?); aynı migration script'i ikinci kez çalıştırılınca duplicate
üretmediğini doğrula; bir Activity artık ProductionCycle olmadan
oluşturulmaya çalışılınca reddedildiğini doğrula.

**T-07/07b (FAZ 3 — RBAC + Onay):** **Kritik —** Tenant A'daki bir kullanıcı
API'den doğrudan ID tahmin ederek Tenant B'nin kaydına erişebiliyor mu
(IDOR testi)? IBAN gibi hassas alan, yetkisiz rolle çekilince response'ta
tamamen yok mu (sadece UI'da mı gizli)? Onay zincirinde bir adım
atlanabiliyor mu (örn. adım 1 onaylanmadan adım 2'nin API'sine doğrudan
istek atılırsa ne olur)? Bir kullanıcının org chart'taki yöneticisi
değişince açık onay talepleri yeni yöneticiye mi düşüyor, eski talepler ne
oluyor?

**T-08/09/10 (FAZ 4 — Query Engine):** Filtre DSL'ine özel karakter/injection
benzeri girdi (`$where`, regex bombası, çok uzun string) verilip sistemin
çökmediğini/güvenli davrandığını doğrula; büyük veri setinde (10k+ kayıt)
sayfalamanın gerçekten server-side olduğunu (network tab'da tüm veri tek
seferde gelmiyor) doğrula; AI doğal dil sorgusunun gerçekten Query Engine'i
çağırdığını (ayrı bir veri yolu olmadığını) doğrula.

**T-11/12/13/13b (FAZ 5 — UX/Workspace):** **Kural 1 ihlali:** gelişmiş
filtre paneli ekranın %40'ından fazlasını mı kaplıyor, operatör alanı
serbest metin mi? **Kural 3 ihlali:** ana menüde 7'den fazla üst madde var
mı, rapor ekranları dağınık mı? Context-aware CRUD gerçekten bağlamı
otomatik dolduruyor mu yoksa kullanıcı hâlâ tekrar mı seçiyor?

**T-14/15/16/17 (FAZ 6 — Harita):** **Kural 2 ihlali:** time slider haritayı
kapatıyor mu? Polygon/çizim ile seçilen alan **gerçek geometrik kesişimle**
mi parsel seçiyor (bounding-box ile yanlış parsel seçilip seçilmediğini
komşu parselli bir alanda test et); 11 katmanın hepsi bağımsız aç/kapa
çalışıyor mu; time slider yıl değiştirince harita+dashboard+görev+AI
context'in **hepsi** aynı anda güncelleniyor mu (tek tek mi, gecikmeli mi)?

**T-18/19/20/21 (FAZ 7 — UFYD):** **Kritik —** bir LedgerEntry'yi API'den
doğrudan PUT/DELETE ile değiştirmeye çalış, reddedilmeli; aynı
ProductionCycle için Hakediş iki kez finalize edilmeye çalışılınca engelleniyor
mu (idempotency); Hakediş hesabını elle (kağıt üzerinde) yapıp sistem
sonucuyla birebir eşleştiğini doğrula (yuvarlama hatası, kesinti sırası
hatası ara); simülasyon (what-if) sonucu gerçek Ledger'a hiç yazılmadığını
doğrula (simülasyon çalıştırıldıktan sonra cari bakiye değişmemeli).

**T-22/23/24 (FAZ 8 — Saha):** Checklist tamamlanmadan görev "Kapandı"
durumuna API'den zorlanmaya çalışılınca reddediliyor mu; aynı görev için
2. bir Ziyaret açılabiliyor mu (Task-Visit 1:N); otomatik görev kuralı
(örn. Toprak Analizi tamamlandı → görev) gerçekten tetikleniyor mu yoksa
sadece dokümante mi edilmiş?

**T-25/26/27/28 (FAZ 9 — Comm Hub):** Kara listedeki bir kişiye Communication
Policy tetiklenince mesaj **gerçekten gitmiyor** mu (kural her zaman kara
listeyi eziyor mu, tam tersi mi)? Retry/fallback zinciri (WhatsApp başarısız
→ SMS) gerçek bir başarısızlık simülasyonunda çalışıyor mu? Case → Task
köprüsü uçtan uca test edilmiş mi?

**T-29/30/31 (FAZ 10 — LMS):** Learning Path'te sıralı zorunluluk gerçekten
işliyor mu (önceki tamamlanmadan sonrakine geçilebiliyor mu)? Sertifika
doğrulama kodu sahte bir kodla sorgulanınca doğru şekilde reddediyor mu?

**T-32/33 (FAZ 11 — Platform Core):** Bir feature flag kapatılınca ilgili
menü **hem UI'da hem API'de** gerçekten kapanıyor mu (sadece UI'da gizlenip
API açık kalmış olabilir)? Health Center'daki durumlar gerçek servis
durumunu mu yansıtıyor yoksa hep "sağlıklı" mı gösteriyor (mock kontrol)?

**T-34/35 (FAZ 12 — Mobil):** Offline'da doldurulan bir form/QR onayı,
internet gelince gerçekten senkronize oluyor mu; iki cihaz aynı görevi
offline'da güncelleyip senkron olunca çakışma nasıl çözülüyor (veri kaybı
var mı)? Aynı QR kod ikinci kez okutulunca reddediliyor mu (tekil kullanım)?
Bir kullanıcıya 2 Experience Profile atanıp profil değiştirilince ekran
seti gerçekten değişiyor mu?

**T-36 (FAZ 13 — GodMode):** Doğru e-posta + **yanlış zamanlı** parola
denemesi reddediliyor mu; 5 başarısız denemeden sonra geçici kilitleniyor
mu; GodMode route'u normal navigasyonun/menünün hiçbir yerinde linklenmemiş
mi (kaynak koddan URL arayarak da doğrula); Impersonation kullanıldığında
audit log'da görünüyor mu.

---

## Kesişen Kontroller (Cross-Cutting — modülden bağımsız, tüm sistemi kapsar)

Bunlar tek bir modülde değil, sistemin geneline yayılı riskler — atlanması
en muhtemel olanlar bunlar çünkü hiçbir modül testi tek başına yakalamaz:

- [ ] **Çok kiracılık izolasyonu:** Farklı tenant'lara ait 2 test hesabı
      açıp, her endpoint'te birinin diğerinin ID'sini tahmin ederek veri
      görüp göremediğini sistematik tarayın (en az Çiftçi/Parsel/Sözleşme/
      Ledger/Case üzerinde).
- [ ] **RBAC bypass:** Her rol için, UI'da gizli olan ama API'de açık kalmış
      bir işlem var mı? (UI'da buton yok diye güvenli sanmayın — doğrudan
      API isteği atarak test edin.)
- [ ] **Türkçe karakter/locale:** Arama ve sıralamada "İ/ı", "Ş/ş", "Ğ/ğ",
      "Ç/ç", "Ö/ö", "Ü/ü" doğru çalışıyor mu (örn. "istanbul" aratınca
      "İstanbul" bulunuyor mu, "i" ile "İ" karışıyor mu)? Tarih formatı
      GG.AA.YYYY mi, sayı/para formatı Türkçe (1.234,56) mi tutarlı?
- [ ] **Silme tutarlılığı:** Sistemde "silme" dediğimiz her yerde gerçekten
      soft-delete mi uygulanmış, yoksa bir yerde unutulup hard-delete mi
      kalmış? (Özellikle Financial Ledger, Audit Log, Görev geçmişi.)
- [ ] **Eşzamanlı işlem/race condition:** Aynı kaydı (örn. bir görevi) iki
      farklı kullanıcı aynı anda güncellemeye çalışınca ne oluyor — veri
      kaybı mı, hata mı, son yazan mı kazanıyor?
- [ ] **Oturum/yetki değişikliği anlık yansıyor mu:** Bir kullanıcının rolü
      admin tarafından değiştirildiğinde, o kullanıcı zaten açık oturumda
      eski yetkilerle işlem yapmaya devam edebiliyor mu (session'ın yeni
      yetkiyi görmesi için ne kadar sürüyor)?
- [ ] **Silme/iptal sonrası ilişkili kayıtlar:** Bir Çiftçi/Parsel pasife
      alındığında ona bağlı ProductionCycle/Sözleşme/Görev kayıtları ne
      oluyor — tutarsız/yetim (orphan) kayıt kalıyor mu?
- [ ] **Dosya/görsel güvenliği:** Yüklenen bir dosyanın uzantısı değiştirilip
      (örn. `.php` → `.jpg`) sistemin gerçek içerik tipini kontrol edip
      etmediği.
- [ ] **Uzun/aşırı veri girişi:** Bir metin alanına 10.000 karakter, bir
      sayısal alana negatif/aşırı büyük değer girilince sistem nasıl
      davranıyor (validasyon mu, 500 hatası mı)?

---

## Backend Standart Denetimi

- [ ] Tüm mutasyon endpoint'lerinde server-side validasyon var (client-side
      validasyona güvenilmemiş).
- [ ] Hata response formatı tüm modüllerde tutarlı (PR-22 standardına uygun).
- [ ] Kritik yazma işlemleri (Ledger, Hakediş finalize, durum geçişleri)
      atomik/transaction'lı — yarıda kesilen bir işlemde tutarsız veri
      kalmıyor.
- [ ] Idempotency gereken yerlerde (ödeme/hakediş finalize, webhook alma)
      gerçekten sağlanmış.
- [ ] N+1 sorgu deseni yok (bir liste ekranı her satır için ayrı sorgu
      atmıyor); kritik koleksiyonlarda index var.
- [ ] Loglarda hassas veri yok (bkz. T-01), yapılandırılmış (structured) log
      formatı tutarlı.
- [ ] Arka plan işleri (background job) başarısız olduğunda sessizce
      kaybolmuyor — retry/dead-letter mekanizması var.
- [ ] API versioning (`/api/v1`) tüm endpoint'lerde tutarlı uygulanmış.
- [ ] Bağımlılık güvenlik taraması (PR-13) temiz.

## Frontend Standart Denetimi

- [ ] Her veri çeken ekranda 3 durum da var: yüklenirken (loading), boşken
      (empty state — "kayıt yok" mesajı, çökmüyor), hata durumunda.
- [ ] Form validasyon mesajları backend validasyonuyla birebir tutarlı
      (frontend "geçerli" dediği bir şeyi backend reddetmiyor, tersi de).
- [ ] Yıkıcı işlemlerin (silme, iptal, onaylama) hepsinde onay diyaloğu var.
- [ ] SmartDataGrid (IT-11) gerçekten her liste ekranında tekrar kullanılmış,
      bazı ekranlarda ayrı/özel tablo bileşeni "unutulmamış."
      kullanılıyor.
- [ ] Tarayıcı konsolunda (DevTools) error/warning yok.
- [ ] Responsive kırılım noktaları (1024px, 768px) gerçekten test edilmiş,
      sadece CSS'te tanımlı değil.
- [ ] Oturum süresi dolduğunda kullanıcı sessizce hata almıyor, anlaşılır
      şekilde login'e yönlendiriliyor.
- [ ] `CLAUDE.md` Kural 1-4 (filtre kompaktlığı, harita floating kontroller,
      7 sabit menü grubu, responsive) tüm ekranlarda uygulanmış — spot check
      değil, ekran ekran taranmış.

---

## Teslimat

Test tamamlandığında tek bir `BULGULAR.md` üretilir: her bulgu yukarıdaki
formatta, şiddete göre sıralı (Kritik → Düşük). Kritik/Yüksek bulgular için
Claude Code, ROADMAP.md'ye eklenecek düzeltme iterasyonları (yeni IT-XX veya
"IT-XX — devam/düzeltme" notu) önerir; siz onaylayınca uygulanır. Bu, "test
et → bulgu bul → düzelt" döngüsünü mevcut IT/PR sisteminize entegre eder,
ayrı bir süreç olarak dışarıda kalmaz.
