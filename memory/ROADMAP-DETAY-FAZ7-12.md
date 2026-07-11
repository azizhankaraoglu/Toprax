# ROADMAP-DETAY-FAZ7-12.md — TABSİS Detaylı Teknik Spesifikasyon (IT-18 → IT-35)

> Bu dosya **ROADMAP.md'nin yerine geçmez, onu tamamlar.** ROADMAP.md faz/iterasyon
> sırasını ve bağımlılıkları tanımlar; bu dosya ise IT-18'den IT-35'e kadar her
> iterasyonun **veri modelini, durum makinesini, API yüzeyini, UI gereksinimlerini,
> iş kurallarını ve "bitti" tanımını** verir. Kaynak: `geliştirmeler.docx` (Sprint 7-12).
>
> **Kullanım kuralı:** Bir IT-XX atandığında Claude Code önce ROADMAP.md'deki
> satırı (bağımlılık + kapsam özeti), sonra bu dosyadaki ilgili bölümü okumalıdır.
> Buradaki alan/durum/kural listeleri **eksiksiz uygulanmalıdır**; docx'te
> "örnek" diye geçen listeler dahi ilk sürümde tam olarak koda yansıtılmalıdır
> (yönetici ekranlarından sonradan silinebilir/eklenebilir olmaları, ilk günden
> eksik gelmeleri gerektiği anlamına gelmez).
>
> Genel geliştirme kuralı (tüm IT'ler için geçerli, docx'te sprint başına tekrar
> eder): mevcut mimari korunur, gereksiz refactor yok, yeni modül RBAC + Audit
> Log + (kurulduysa) Query Engine + Event Bus'a bağlanır, server-side pagination
> zorunludur, hassas alanlar loglanmaz.

---

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

**Stratejik mimari not (docx'ün vurgusu):** Comm Hub sadece mesaj gönderen bir servis değil; TABSİS içindeki tüm iş olaylarını (Event) dinleyip doğru kişiye doğru zamanda doğru kanaldan ileten merkezi bir hub olmalı. Yeni modüller iletişim kodu yazmaz, sadece event yayınlar.

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

**Integration Hub:** TABSİS dışarıya doğrudan bağlanmaz; Google Maps, AI servisleri (OpenAI/Anthropic/Gemini), SMS/WhatsApp/E-posta, GeoServer, NASA/Sentinel/Planet, MERNİS/TAKBİS dahil tüm 3. parti çağrılar **tek bir Integration Hub modülünden** geçer. Extras altındaki dağınık simüle servisler (S4 uydu, S9 kanal provider'ları vb.) bu ortak provider pattern'e taşınır (refactor değil, konsolidasyon — mevcut arayüzler korunur).

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

> IT-35 sonrası kalan mobil özellikler (dijital imza, barkod, derin offline senkron) ihtiyaca göre IT-36+ olarak açılır (ROADMAP.md not'u ile tutarlı).

---

## Kullanım Notu — Neden Bu Dosya Kod Kalitesini Artırır

Önceki ROADMAP.md satırları ("Financial Ledger + Cari Hesap ekranı" gibi) Claude Code'a *ne* yapılacağını söylüyordu ama *nasıl* (hangi alanlar, hangi durumlar, hangi kural) sorusunu boş bırakıyordu — boşluk dolduğunda model en genel/basit yorumu seçiyor. Bu dosyadaki her IT artık:
1. Somut alan listesi (docx'teki "örnek" listeler tam liste olarak alınmış),
2. Durum makinesi (adım adım, atlanamaz),
3. "Bu kural API seviyesinde zorlanmalı" tipi açık iş kuralları,
4. Definition of Done (test edilebilir kabul kriterleri)

içeriyor. Yeni bir IT-XX atarken oturum başında Claude Code'a şunu söylemeniz yeterli: **"IT-22'yi yap, ROADMAP.md ve ROADMAP-DETAY-FAZ7-12.md'deki IT-22 bölümünü birebir uygula."**
