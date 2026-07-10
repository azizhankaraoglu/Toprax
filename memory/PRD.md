# Dijital Tarım Ekosistemi — Kooperatif Edisyonu
## Ürün Gereksinim Dokümanı (PRD) — v1.0

**Tarih:** Ocak 2026  
**Hedef İlk Müşteri:** Türk Şeker A.Ş. (ve benzeri büyük tarım kooperatifleri)  
**Dağıtım Modeli:** Kooperatifin kendi sunucusunda (on-premise) çalışan, Docker tabanlı paket yazılım  
**Lisans Modeli:** Tek seferlik lisans + yıllık bakım (B2B)

---

## 1. VİZYON & AMAÇ

### 1.1 Tek cümlelik vizyon
Kooperatiflerin sözleşmeli üreticilerini, parsellerini, ekim-hasat döngülerini, lojistiğini ve finansal akışlarını tek bir dijital ekosistemde, kendi sunucularında yönetmelerini sağlayan uçtan uca platform.

### 1.2 Çözeceği problem
- Çiftçi/parsel/sözleşme verisi hâlâ Excel ve kâğıt formlarda
- Hasat döneminde kantar/lojistik kaosu
- Üretim planlama veriye dayalı değil
- Devlet teşvik/sigorta süreçleri manuel
- Bölge müdürlüğü ile çiftçi arasında iletişim parçalı
- Üst yönetimin gerçek zamanlı KPI görünürlüğü yok

### 1.3 Hedefler (1. yıl)
- Tek bir büyük kooperatife satılabilir, kurulabilir MVP teslimi
- Pilot fabrika bölgesinde 500+ çiftçi ile saha testi
- 5.000+ parsel kaydı, 1+ ekim sezonu canlı operasyon
- %85+ kullanıcı memnuniyeti, %90+ uptime

---

## 2. KULLANICI ROLLERİ & PERSONALAR

### 2.1 Roller
| Rol | Yetki Düzeyi | Erişim |
|---|---|---|
| **Süper Admin** | Tam yetki | Tüm modüller, sistem ayarları, kullanıcı yönetimi |
| **Genel Müdürlük** | Okuma + onay | Tüm bölge verileri, üst düzey KPI, raporlar |
| **Fabrika/Bölge Müdürü** | Bölge bazında tam yetki | Kendi bölgesinin çiftçileri, parselleri, lojistiği |
| **Ziraat Mühendisi (Saha)** | Bölge bazında operasyon | Mobil PWA; çiftçi ziyareti, parsel inceleme, foto, görev |
| **Muhasebe** | Finansal modüller | Avans, hakediş, müstahsil makbuzu, raporlar |
| **Çiftçi/Üye** | Sadece kendi verisi | Kendi parselleri, sözleşmesi, ödemeleri, randevuları |
| **Kantar Operatörü** | Sadece kantar modülü | Kamyon kabul, tartı, kalite girişi |

### 2.2 Personalar
- **Ahmet — Fabrika Müdürü (52 yaş):** Excel'i bilir, web kullanır, ofis bilgisayarı başında 8 saat. Hedefi: bölgenin verim hedefini tutturmak.
- **Mehmet — Ziraat Mühendisi (34 yaş):** Sahada arabayla gezer, mobil ağırlıklı, internet zayıf bölgelerde çalışır. Hedefi: günlük 8-12 çiftçi ziyareti yapmak.
- **Hasan — Çiftçi (58 yaş):** Akıllı telefon var ama uygulama indirmekte zorlanır, WhatsApp kullanır. Hedefi: avansını almak, hasat randevusunu öğrenmek.
- **Ayşe — Muhasebeci (41 yaş):** E-fatura/e-müstahsil sistemine alışkın. Hedefi: hatasız ödeme kayıtları, dönem sonu raporları.

---

## 3. MVP MODÜLLERİ — DETAYLI

### M01. Kimlik Doğrulama & Yetkilendirme
**Amaç:** Güvenli giriş, rol bazlı erişim, denetim izi.

**Özellikler:**
- E-posta + şifre giriş (bcrypt)
- 2FA opsiyonu (TOTP — Google Authenticator)
- "Beni hatırla" + 30 dakika inaktif çıkış
- Şifre sıfırlama (e-posta linki)
- Audit log: giriş/çıkış/yetki değişikliği
- IP/cihaz bazlı şüpheli aktivite uyarısı
- KVKK aydınlatma metni onayı

**Ekranlar:**
- Giriş, şifre unuttum, ilk giriş şifre değiştir, 2FA kurulum, profil

**Sınırlar:**
- LDAP/Active Directory entegrasyonu Faz 2

---

### M02. Çiftçi & Üye Yönetimi
**Amaç:** Sözleşmeli üretici sicilinin merkezi yönetimi.

**Veri Modeli:**
- Kimlik: Ad, TC No, doğum tarihi, baba adı
- İletişim: telefon (zorunlu), e-posta, adres, köy/mahalle
- Finansal: IBAN, vergi no
- Sicil: üyelik no, sözleşme yılı, üyelik tarihi
- Aile/çiftlik: bağlı kişi sayısı, mevsimlik işçi
- Belgeler: nüfus, ikametgah, tapu (PDF upload)
- Skor: çiftçi karne notu (A/B/C/D)
- Durum: aktif/pasif/askıda

**Özellikler:**
- Liste, arama (TC/ad/telefon/üye no), filtre (bölge/köy/skor)
- Toplu Excel içe aktarma (mevcut Excel kayıtları için)
- Excel/PDF dışa aktarma
- Çiftçi 360° görünüm (parseller, sözleşmeler, ödemeler, ziyaretler)
- Duplicate TC kontrolü
- Yumuşak silme + audit

**Ekranlar:**
- Çiftçi listesi, çiftçi detay (sekmeli), yeni çiftçi formu, içe aktarma sihirbazı

---

### M03. Parsel & Arazi Yönetimi
**Amaç:** Her parselin coğrafi, hukuki, tarımsal durumunu tek yerde tutmak.

**Veri Modeli:**
- Parsel kodu (auto/manuel)
- Sahip çiftçi (FK)
- Konum: il/ilçe/köy, koordinatlar (GeoJSON Polygon)
- Tapu/kira durumu: maliki, kira sözleşmesi süresi
- Toprak: tipi, drenaj, eğim
- Sulama: var/yok, kaynak tipi (artezyen/kanal/yağmurlama/damla)
- Alan: hesaplanan dekar/hektar
- Aktif ekim: ürün, sezon
- Geçmiş: tüm önceki yılların ürünleri
- Komşu parseller (otomatik bul)

**Özellikler:**
- Leaflet/Mapbox harita: çoklu katman (OSM, uydu)
- Çokgen çizim (manuel) + KML/SHP import (Faz 2)
- GPS damgası ile saha tarafından çizim (mobil)
- Alan otomatik hesabı (turf.js)
- Parsel kümeleme (köy/bölge bazlı renk)
- Filtre: ürüne göre, sulamaya göre, skoruna göre
- Sentinel-2 NDVI katmanı (prototipte mock görsel)

**Ekranlar:**
- Harita ana ekran, parsel detay drawer, parsel çiz/düzenle, parsel-çiftçi ilişkilendir

---

### M04. Sözleşme & Kota Yönetimi
**Amaç:** Üretici–kooperatif arası yıllık ekim sözleşmesi, kotanın takibi.

**Veri Modeli:**
- Sözleşme no, sezon (örn. 2026)
- Çiftçi (FK), bölge müdürlüğü
- Ürün tipi (örn. şeker pancarı)
- Kota: dekar + tonaj
- Çeşit (tohum çeşidi)
- Avans hakları: tohum/gübre/ilaç
- Sözleşme PDF (auto-generate, imza alanı)
- Durum: taslak/imzalı/iptal/kapalı

**Özellikler:**
- Sözleşme şablonu (parametreli Word/PDF)
- Toplu sözleşme üretimi (sezon başında binlerce çiftçi için)
- E-imza opsiyonu (KEP/SecureKEP entegrasyonu — Faz 2, prototipte manuel upload)
- Kota dağıtım optimizasyonu (geçmiş verim bazlı öneri)
- Ekim alanı / kota karşılaştırma (mevcut)
- Sezon kapatma & arşivleme

**Ekranlar:**
- Sözleşme listesi, sözleşme detay, toplu üretim sihirbazı, sezon yönetimi

---

### M05. Ekim Planlama & Geçmiş
**Amaç:** Her parsel için yıllık ekim takvimi ve geçmiş kayıtları.

**Veri Modeli:**
- Ekim kaydı: parsel (FK), sezon, ürün, çeşit
- Tarihler: ekim, sürme, çiçeklenme, beklenen hasat, gerçekleşen hasat
- Tohum: marka, miktar, kg/dekar
- Münavebe önerisi: bir önceki ürün, önerilen sonraki

**Özellikler:**
- Yıllık ekim takvimi (Gantt benzeri görünüm)
- Münavebe kuralları motoru (aynı parsele 3 yıl üst üste pancar = uyarı)
- Geçmiş yıl verim grafiği (parsel + çiftçi bazlı)
- Toplu güncelleme (köy bazlı ekim tarihi)
- Hava şartlarına göre ideal ekim aralığı önerisi

**Ekranlar:**
- Ekim takvimi (timeline), parsel-sezon detay, geçmiş analiz

---

### M06. Toprak Bilgisi
**Amaç:** Lab analiz sonuçlarını saklamak ve aksiyon önerileri üretmek.

**Veri Modeli:**
- Numune: parsel (FK), tarih, lab adı
- Sonuçlar: pH, EC, organik madde, N/P/K, kireç, toprak tipi
- Öneri: gübre tipi, dozu, ilaç önerisi
- PDF rapor upload

**Özellikler:**
- Manuel sonuç girişi + PDF ekleme
- Kural tabanlı gübre/ilaç öneri motoru (ürün × toprak)
- Lab API entegrasyonu (Faz 2)
- Karşılaştırma: parselin önceki yıllarla farkı
- Bölge ortalamasıyla benchmark

**Ekranlar:**
- Numune listesi, numune detay, yeni numune formu, öneri raporu

---

### M07. Saha Mobil (Ziraat Mühendisi PWA)
**Amaç:** Sahada çalışan mühendisin offline bile çalışabilen mobil arayüzü.

**Özellikler:**
- Günlük görev listesi (atanmış ziyaretler)
- Harita üzerinde ziyaret edilecek parseller
- GPS damgalı ziyaret raporu
- Fotoğraf çekme + AI hastalık tespiti (Gemini Vision API)
- Çiftçi imzası (parmak/stylus)
- Offline kayıt → bağlantı geldiğinde otomatik senkron
- Sesli not (Whisper STT — opsiyonel)
- Rota optimizasyonu (en yakından başla)

**Ekranlar:**
- Bugünkü görevler, harita, parsel hızlı kayıt, foto upload, çiftçi imza ekranı

**Teknik:**
- React PWA (Service Worker, IndexedDB)
- Push Notification (FCM)
- Konum izni zorunlu

---

### M08. Lojistik & Kantar Yönetimi
**Amaç:** Hasat dönemi kamyon-randevu kaosunu çözmek.

**Veri Modeli:**
- Randevu: çiftçi, parsel, tarih/saat aralığı, kamyon plakası
- Kantar kaydı: brüt/dara/net tonaj, kalite (polar, vb.), kabul/red
- Kamyon havuzu (kooperatif aracı + dış araç)
- Sefer maliyet (km, yakıt, sürücü)

**Özellikler:**
- Randevu takvimi (drag-drop)
- Otomatik slot optimizasyonu (kantar kapasitesine göre)
- Çiftçiye SMS/WhatsApp ile randevu bildirimi
- QR kod ile kantar kabul
- Kantar cihazı entegrasyonu (CSV/Modbus — prototipte CSV mock)
- Lab sonuç entegrasyonu (polar oranı)
- Sefer maliyet raporu

**Ekranlar:**
- Randevu takvimi, kantar operatör ekranı (büyük buton odaklı), günlük tonaj özet

---

### M09. Finansal Akış
**Amaç:** Avanstan hakedişe çiftçi cüzdanını yönetmek.

**Veri Modeli:**
- Hesap hareketi: çiftçi, tarih, tip (avans/hakediş/kesinti/iade), tutar, açıklama
- Müstahsil makbuzu: hasat × birim fiyat
- Avans planı: ürün/gübre/tohum/nakit
- Kesinti kuralları: avans geri ödeme, kooperatif aidatı, sigorta

**Özellikler:**
- Çiftçi cüzdan ekstresi
- Toplu hakediş hesaplama (hasat × fiyat)
- Müstahsil makbuzu PDF üretimi (e-Müstahsil uyumlu format)
- Dönem kapatma
- E-fatura/e-müstahsil entegrasyonu (Logo/Mikro köprü — Faz 2)
- Banka dosyası dışa aktarma (toplu havale için)

**Ekranlar:**
- Çiftçi ekstre, toplu hakediş sihirbazı, müstahsil makbuzu önizleme, dönem kapatma

---

### M10. Yönetim Dashboard & KPI
**Amaç:** Üst yönetime gerçek zamanlı bölge/genel resim.

**KPI Kartları:**
- Toplam sözleşmeli çiftçi
- Toplam ekim alanı (dekar)
- Beklenen tonaj vs gerçekleşen
- Avans dağıtımı / hasat ilerleme
- Bölge bazlı verim sıralaması
- Geç ekim/risk altında parsel sayısı
- Çiftçi karne dağılımı

**Grafikler:**
- Yıllık verim trendi (5 yıl)
- Bölge × ürün ısı haritası
- Hasat ilerleme S-curve
- Maliyet/gelir hava şartı korelasyonu

**Özellikler:**
- Tarih/bölge/ürün filtreleri
- PDF/Excel rapor dışa aktarma
- E-posta ile haftalık özet
- Power BI / Metabase için API endpoint

**Ekranlar:**
- Ana dashboard, bölge detay, ürün detay, rapor merkezi

---

### M11. Bildirim Merkezi
**Amaç:** Sistem içi + dış kanal (SMS/WhatsApp/Push) bildirim altyapısı.

**Bildirim Tipleri:**
- Hava uyarısı (don/dolu/kuraklık)
- Sulama hatırlatma
- Kantar randevu
- Avans/hakediş bilgilendirme
- Sözleşme imza hatırlatma
- Görev atama (saha ekibi)
- Anormal verim/bitki sağlığı uyarısı

**Kanallar:**
- Sistem içi (uygulama)
- SMS (Twilio/NetGSM/İletiMerkezi)
- WhatsApp Business (Twilio/Meta)
- Push (FCM)
- E-posta (SendGrid)

**Özellikler:**
- Şablonlar (parametreli)
- Kanal tercihi (kullanıcı bazlı)
- Toplu gönderim (bölge/köy bazlı)
- Teslim raporları
- Rate limiting

**Ekranlar:**
- Bildirim listesi, şablon yönetici, toplu gönderim sihirbazı

**Prototip notu:** SMS/WhatsApp gerçek gönderim olmadan, panelde "gönderildi" simülasyonu olarak gösterilir.

---

### M12. Çiftçi Karne (Performans Skoru)
**Amaç:** Veriye dayalı çiftçi sınıflandırması, kota dağıtım önceliği.

**Skor Bileşenleri:**
- Geçmiş verim (kota karşılama oranı) — %30
- Ödeme disiplini (avans geri ödeme) — %20
- Kalite (polar/şeker oranı) — %20
- Saha uyumu (ziraat müh. ziyaret notları) — %15
- Sözleşme süresi/sadakat — %15

**Özellikler:**
- Otomatik aylık hesaplama
- A/B/C/D harf notu + 0-100 puan
- Çiftçi kendi karnesini görebilir
- Bölge müdürü neden düştüğünü görebilir
- Karne tarihçesi

**Ekranlar:**
- Karne kartı, bileşen kırılımı, bölge sıralama, trend grafiği

---

### M13. Raporlama & Veri İhraç
**Amaç:** Yönetim ve resmi raporlar.

**Hazır Raporlar:**
- Sezon özeti
- Çiftçi listesi (TARSİM uyumlu)
- Parsel listesi (CBS uyumlu)
- Tonaj/kalite raporu
- Finansal özet
- Bölge müdürlüğü performansı
- KVKK veri talebi raporu

**Çıktı Formatları:** PDF, Excel (xlsx), CSV, JSON API

**Özellikler:**
- Rapor şablonu özelleştirme (logo, başlık)
- Planlı rapor (haftalık/aylık otomatik e-posta)
- API endpoint (Power BI/Metabase için)

---

### M15. Sulama & Kaynak Yönetimi
**Amaç:** Su, gübre, ilaç kaynaklarını parsel bazlı planlamak ve takip etmek.

**Veri Modeli:**
- Su kaynağı: tip (artezyen/kanal/göl), kapasite, çiftçi-parsel atama
- Sulama planı: parsel, başlangıç tarihi, tur sayısı, dönüm başına su (m³)
- Sulama olayı: tarih, miktar, yöntem (yağmurlama/damla/karık)
- IoT sensör: nem (%), toprak sıcaklığı (mock veri)
- Kuraklık risk skoru: bölge × ürün × tarih
- Gübre/ilaç stok: ürün, miktar, çiftçi avans hareketleri

**Özellikler:**
- Sulama takvimi (parsel-gün matrisi)
- AI sulama önerisi (hava + toprak + ekim aşaması)
- Su kullanım raporu (m³, parsel/çiftçi/bölge bazlı)
- Kuraklık erken uyarı (SMS toplu)
- Kaynak yetersizliği uyarısı (paylaşımlı kanal vs.)
- Damla/yağmurlama verimlilik karşılaştırma

**Ekranlar:** Sulama takvimi, parsel sulama detay, kaynak haritası, kuraklık paneli

---

### M16. Operasyon Yönetimi
**Amaç:** Saha işlerinin (ekip, makine, görev) merkezi planlaması.

**Veri Modeli:**
- Görev: tip (toprak işleme/ekim/ilaçlama/hasat), parsel, çiftçi, tarih, durum
- İşçi: ad, telefon, beceri (sürücü/saha işçisi), günlük ücret
- Makine/ekipman: tip (traktör/biçerdöver/pülverizatör), seri no, durum, sahibi (kooperatif/çiftçi)
- Vardiya planı: işçi × tarih × görev
- Makine kullanım kaydı: km, saat, yakıt, görev
- Arıza/bakım kaydı

**Özellikler:**
- Görev atama dashboard'u (drag-drop)
- Makine kullanım takvimi
- İşçi vardiya planlama
- Makine kiralama içi platformu (kooperatif → çiftçi)
- Yakıt/bakım maliyet kaydı
- Operasyon ilerleme yüzdesi
- Toplu görev atama (köy bazlı)
- Görev tamamlama bildirimi (mobil saha ekibi)

**Ekranlar:** Görev tahtası (kanban), makine takvimi, vardiya planı, kiralama listesi

---

### M17. Verimlilik & Analitik
**Amaç:** Veriden içgörü çıkarmak — karar destek motoru.

**Veri Modeli:**
- Verim kaydı: parsel, sezon, ürün, dekar, toplam ton, polar/şeker oranı
- Girdi kaydı: gübre kg, ilaç lt, su m³, işçilik saat, makine saati
- Maliyet: girdi × birim fiyat
- Risk simülasyonu: senaryo (kuraklık -%20, fiyat -%15 vb.)

**Özellikler:**
- Verim raporu (parsel/çiftçi/bölge bazlı)
- 5 yıllık trend grafiği
- Bölge × ürün ısı haritası
- Maliyet/dekar analizi
- Geri dönüş oranı (gelir/maliyet)
- ML verim tahmini (prototipte kural tabanlı simülasyon)
- "What-if" senaryo simülasyonu
- Karşılaştırma: parsel vs köy ortalaması vs bölge ortalaması
- Bölge sıralaması (en verimli / en az verimli)
- En çok kaybeden 10 parsel (root cause incel.)

**Ekranlar:** Verimlilik dashboard, parsel detay analiz, senaryo simülatörü, karşılaştırma sayfası

---

### M18. Sistem Yönetimi & Audit
**Amaç:** Süper admin için sistem bakımı + güvenlik.

**Özellikler:**
- Kullanıcı yönetimi (CRUD)
- Rol & izin yönetimi (RBAC matrisi)
- Bölge/fabrika hiyerarşisi yönetimi
- Ürün/çeşit/lookup tabloları
- Sistem ayarları (sezon, kotalar)
- Audit log (her kritik işlem)
- Yedekleme & geri yükleme
- Lisans & sürüm bilgisi
- Sistem sağlık paneli (DB, disk, queue)

---

## 4. TEKNİK MİMARİ

### 4.1 Stack
- **Frontend:** React 18 (PWA), Tailwind, shadcn/ui, React-Leaflet (harita), Recharts (grafik)
- **Backend:** Python FastAPI, Pydantic v2
- **DB:** MongoDB (primary), Redis (cache/queue)
- **Storage:** MinIO (S3 uyumlu, fotoğraflar)
- **Worker:** Celery (async görevler)
- **AI:** Yapılandırılabilir sağlayıcı (OpenAI / Gemini / Anthropic — Ayarlar > Entegrasyonlar üzerinden)
- **Reverse Proxy:** Nginx
- **Container:** Docker Compose (kooperatif kurulumu için)

### 4.2 Güvenlik
- HTTPS zorunlu (kooperatif kendi SSL'i)
- JWT + refresh token
- bcrypt şifre
- KVKK uyumlu loglama
- Düzenli yedek (günlük inkremental + haftalık tam)
- Veri imha politikası (silme talebi)

### 4.3 Performans Hedefleri
- API yanıt < 300ms (p95)
- Dashboard yüklenme < 2sn
- 10.000+ çiftçi, 50.000+ parsel veri ölçeğinde stabil
- Sahadan offline + senkron < 10sn

---

## 5. DAĞITIM MODELİ

### 5.1 Kurulum
- Kooperatif sunucusuna `docker-compose up -d`
- İlk kurulum sihirbazı (admin oluştur, bölge yapısı, lisans gir)
- Veri içe aktarma (Excel/CSV)

### 5.2 Donanım Önerisi (kooperatif tarafı)
- **Minimum (≤2000 çiftçi):** 4 vCPU, 8GB RAM, 100GB SSD
- **Önerilen (≤20.000 çiftçi):** 8 vCPU, 16GB RAM, 500GB SSD, ayrı DB sunucusu
- **Büyük (≥50.000 çiftçi):** 16 vCPU, 32GB RAM, 1TB SSD, MongoDB cluster

### 5.3 Güncelleme
- Yarı otomatik (kooperatif onayıyla)
- Geri alınabilir (rollback)
- DB migration scriptleri

---

## 6. YOL HARİTASI

| Faz | Süre | İçerik |
|---|---|---|
| **Faz 1 — MVP Prototip** | 2-3 hafta | Sohbette geliştirme; M01, M02, M03, M04, M05, M10 modülleri tıklanabilir + demo veri |
| **Faz 2 — Saha Demo** | +4-6 hafta | M06, M07, M08, M09, M11, M12 modülleri |
| **Faz 3 — Üretim Sınıfı** | +4 hafta | M13, M14, Docker paketleme, audit, KVKK, dokümantasyon |
| **Faz 4 — Saha Pilot** | +2-3 ay | 1 fabrika bölgesinde gerçek kullanım, hata düzeltme, kantar/lab entegrasyonu |
| **Faz 5 — Genel Yayın** | +1-2 ay | Diğer bölgelere yayılım, eğitim, %100 destek |

---

## 7. BAŞARI METRİKLERİ

- **Teknik:** Uptime ≥%99.5, API hata oranı <%1, ortalama yanıt <500ms
- **Kullanıcı:** Aylık aktif kullanıcı (ziraat müh./yönetici), günlük çiftçi giriş sayısı
- **İş:** Çiftçi karne C üstü oranı artışı, hasat planlama uyum oranı, kantar bekleme süresi düşüşü
- **Memnuniyet:** NPS ≥ 40, eğitim sonrası kullanım %70+

---

## 8. RİSKLER & ÖNLEMLER

| Risk | Önlem |
|---|---|
| Kooperatif IT mimarisi uyumsuzluğu | Erken POC, mimari onay toplantısı |
| Veri kalitesi (Excel'den taşıma) | İçe aktarma doğrulama sihirbazı, manuel düzeltme akışı |
| Çiftçi adaptasyon | Saha mühendisi üzerinden proxy kullanım, WhatsApp bot |
| Saha internet sorunu | PWA offline-first + senkron |
| Scope creep | Sözleşmede "değişiklik talebi" prosedürü, faz bazlı teslim |
| KVKK ihlali | Düzenli denetim, anonimleştirme, veri imha akışı |

---

## 9. AÇIK SORULAR (Müşteri görüşmesinde netleşecek)

1. Mevcut çiftçi/parsel verisi hangi formatta? Excel mi, başka bir sistemde mi?
2. Kantar cihazı markası/modeli? (entegrasyon detayı için)
3. Lab cihaz tedarikçisi? (polar/şeker oranı için)
4. E-fatura/e-müstahsil için kullanılan paket? (Logo/Mikro/Diğer)
5. Bölge müdürlüğü hiyerarşisi nedir? (örn. Genel Md → Bölge → İlçe Md → Köy)
6. Çiftçi giriş yöntemi: TC + SMS OTP mi, kullanıcı adı + şifre mi?
7. Hangi ürünler kapsamda? (Sadece pancar mı, mısır/buğday da var mı?)
8. Mevcut altyapı: on-premise tercih var mı, kooperatif cloud da kabul eder mi?

---

## 10. SATIŞ MATERYALİ (Pazarlama için)

### Elevator Pitch
> "Türk Şeker'in 100.000 sözleşmeli çiftçisini, parsellerini, ekim-hasat döngüsünü, kantarını ve müstahsil makbuzlarını tek bir kendi sunucunuzda çalışan platformda yönetin. Excel kaosunu bitirin, kantar kuyruklarını yarıya indirin, üst yönetime gerçek zamanlı KPI gösterin."

### Değer Önerisi (Maddesel)
- **Operasyonel:** %50 daha az kantar bekleme, %30 daha az manuel veri girişi
- **Finansal:** Avans/hakediş hatalarında %80 azalma, müstahsil makbuzu üretim süresi 10 dk → 5 sn
- **Yönetimsel:** Bölge müdürü Excel'den dashboard'a, üst yönetim gerçek zamanlı veri
- **Stratejik:** Veri ambarı sayesinde sonraki yıl planlamada %15+ verim artışı potansiyeli

### Rekabet Avantajı
- Türkiye'ye özel (TARSİM, e-müstahsil, Türkçe mevzuat)
- Kooperatifin **kendi sunucusunda** (veri sahipliği tartışmasız)
- Modüler — sadece ihtiyacı olanı al
- Saha mobil PWA offline çalışır
- Açık API (Power BI, mevcut ERP'lere köprü)

### Fiyatlandırma Önerisi
| Paket | Çiftçi Sayısı | Tek Sef. Lisans | Yıllık Bakım |
|---|---|---|---|
| Bölgesel | ≤5.000 | ₺1.500.000 | ₺300.000 |
| Kurumsal | ≤25.000 | ₺3.500.000 | ₺700.000 |
| Türk Şeker | ≤100.000 | ₺6.000.000 | ₺1.200.000 |

---

**Doküman sahibi:** [Müşteri adı]  
**Hazırlayan:** TabSIS Ekibi + [Senin adın]  
**Sürüm geçmişi:** v1.0 — İlk taslak (Ocak 2026)
