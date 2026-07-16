# DEMO-ÖNCESİ-3-ÖNCELİK.md — Mevcut Projede Tara, Eksikse Ekle/Düzelt

> **Cowork için görev tanımı:** Bu proje daha önce fazlar halinde ayrı
> projelerde geliştirildi, şimdi tek bir güncel projede birleşti. Bu üç konu
> için önce **mevcut kod tabanında ne var ne yok tespit et** (bazı parçalar
> eski fazlardan hiç taşınmamış/unutulmuş olabilir), sonra spesifikasyona göre
> eksik/hatalı olanı tamamla. Her konu için önce bir **Durum Tespiti**
> (mevcut ne, eksik ne) raporu üret, sonra düzeltmeye geç — kör kör
> "baştan yaz" değil, var olanı bul ve tamamla.
>
> Referans: `CLAUDE.md` (tasarım kuralları), `ROADMAP-DETAY-TAM.md` (IT-13,
> IT-14-17 — bu üç konunun daha önce yazılmış temel spesifikasyonu, burası
> onu genişletiyor/somutlaştırıyor).

---

## KONU 1 — Uydu Görüntü Sistemi (Parsel Bazlı, Maliyet Optimizasyonlu)

**Zaten spesifiye edilmiş temel (IT-17):** provider soyutlaması (NASA/
Sentinel/Planet/Maxar), tarihsel görüntü + time slider, uydu analiz
katmanları (NDVI/NDWI/Su Stresi/Hastalık vb.), AI'nin katmanlı karar mimarisi
(yerel model → düşük güvende bulut escalation) `AI-VIZYON-PLATFORMU-PROMPT.md`'de
detaylandırılmıştı. **Aşağıdakiler bu temele eklenen, demo için kritik yeni
davranışlar:**

### 1.1 — "Eldeki En İyi Görüntüyle Çalış" Davranışı
Her analiz, o parsel için o an erişilebilir **en iyi** görüntüyle yapılır —
"görüntü yok" diye analiz bloklanmaz. Her analiz sonucunun yanında **her
zaman** şu üçü etiketlenir: **kaynak** (hangi provider/uydu), **tarih**
(görüntünün çekildiği gün — analiz tarihinden farklı olabilir), **çözünürlük**
(kaç metre/piksel). UI'da bu üçü küçük bir "görüntü künyesi" olarak sonucun
yanında her zaman görünür — kullanıcı hangi veriye dayanarak karar
verdiğini bilmeli.

### 1.2 — Kademeli Kalite (Abonelik Bazlı, Kod Değişmeden)
Tenant'ın abonelik seviyesi (Feature Flags/Licensing — IT-33) hangi
provider'lara/hangi sıklıkta/hangi çözünürlükte erişebileceğini belirler.
Kod tarafı **tek bir Provider Pattern arayüzü** kullanır; hangi provider'ın
aktif olduğu config'ten gelir. Düşük abonelik → düşük çözünürlük/seyrek
güncelleme kaynağı; yüksek abonelik → yüksek çözünürlük/sık güncelleme —
ama hepsi aynı kod yolundan geçer, provider değişince kod değişmez.

### 1.3 — Akıllı Tasking (Anomali Şüphesinde Otomatik Yüksek Çözünürlük Talebi)
**Bu, maliyet mimarisinin can alıcı noktası.** Normal akışta sistem ucuz/
zaten-var-olan görüntüyü kullanır. Ama yerel analiz (Rule Engine + Yerel AI
Vision — `AI-VIZYON-PLATFORMU-PROMPT.md`'deki Confidence Engine) bir
parselde **anomali şüphesi** (hastalık/su stresi/beklenmedik değişim)
tespit ederse, sistem otomatik olarak o **tek parsel** için yüksek
çözünürlüklü/güncel bir kare **talep eder (tasking request)** — bu, Provider
soyutlamasına eklenecek yeni bir capability: `request_tasking(parcel_id,
priority, reason)`. Böylece pahalı/yüksek çözünürlüklü veri **her parselde
sürekli değil, sadece şüphe oluşan yerde** harcanır. Tasking isteği de
tenant'ın aylık bütçesine/kotasına tabidir (AI-VIZYON prompt'undaki tenant
kota mantığıyla aynı).

### 1.4 — Onaylı/Onaysız Bildirim Akışı
Bir anomali tespit edildiğinde bildirim akışı **konfigüre edilebilir** olmalı,
tek bir sabit davranış değil:
- **Seçenek A (onaylı):** sonuç önce Ziraat Mühendisinin "Onay Bekleyenlerim"
  ekranına düşer (IT-07b Onay Zinciri), mühendis onaylayınca çiftçiye/ilgili
  kişiye bildirim gider (Comm Hub — IT-25/27).
- **Seçenek B (onaysız/doğrudan):** yüksek güven eşiğini geçen sonuçlar
  doğrudan bildirime dönüşür, mühendis sadece bilgilendirilir.
- Bu ikisi arasındaki eşik ve kimin hangi tenant/hastalık tipi için hangi
  modda çalışacağı **admin tarafından ayarlanabilir** olmalı (hardcode
  edilmiş tek bir davranış olmamalı) — Communication Policy (IT-27) kural
  tablosuna yeni bir alan: `requires_approval: true/false`.

**Durum Tespiti İstenen Sorular (Cowork önce bunları cevaplasın):**
- IT-17'nin provider soyutlaması gerçekten kodda var mı, yoksa sadece UI'da
  mock/placeholder mı?
- Görüntü künyesi (kaynak/tarih/çözünürlük) herhangi bir ekranda gösteriliyor mu?
- Tasking kavramı (on-demand yüksek çözünürlük talebi) hiç kodlanmış mı —
  büyük ihtimalle **hayır**, bu tamamen yeni bir capability, sıfırdan
  eklenmesi gerekir.
- Onay akışı (Seçenek A/B) var mı, varsa hangisi hardcode?

---

## KONU 2 — Harita/GIS Modülü (Orta Seviye GIS Hedefi)

**Zaten spesifiye edilmiş temel (IT-14-16):** widget dashboard, katman
yönetimi (11 katman), basemap değiştirici, çizim araçları (polygon/rect/
circle → geometrik kesişimle parsel seçimi), TKGM import, parsel popup,
harita snapshot. **Şu an "çok kötü" dediğiniz — muhtemelen bu temel bile tam
oturmamış; aşağıdakiler hem eksik olabilecek temel hem de eklenmesi gereken
yeni yetenekler:**

### 2.1 — Parsel Bölme (Parcel Splitting) — YENİ, spec'te yoktu
Kullanıcı harita üzerinde bir parseli çizim aracıyla ikiye (veya daha
fazlaya) bölebilmeli. Bölme sonrası: orijinal parsel pasife alınır (silinmez
— geçmiş kayıtları korumak için), yeni oluşan parsellerin her biri kendi
ID'sini alır ama `split_from_parcel_id` ile orijinale referans tutar (soy
kütüğü/lineage). **Kritik:** bölünen parselin bağlı ProductionCycle/
Sözleşme/Toprak Analizi gibi geçmiş kayıtları ne olacak — bunlar orijinal
(artık pasif) parsele bağlı kalır, yeni parseller sıfırdan başlar (bu bir
tasarım kararı, Cowork uygulamadan önce onaylatmalı).

### 2.2 — Workspace Bazlı Katman Hazırlama + Organizasyon İçinde Paylaşım
Kullanıcı kendi harita çalışma alanında (IT-14'teki "kişisel çalışma alanı
kaydetme" zaten temel bunu karşılıyordu ama **paylaşım** eksikti) katman
kombinasyonu/stil/filtre hazırlar, sonra bunu:
- Sadece kendine saklayabilir (mevcut davranış),
- **Organizasyon hiyerarşisindeki (IT-07b) belirli bir birime/pozisyona
  paylaşabilir** (örn. "Konya Bölgesi" birimindeki herkes görsün),
- Veya tüm tenant'a (şirket geneli) paylaşabilir.
Paylaşılan bir workspace, alıcı tarafta salt-okunur açılır, isterse
"kendime kopyala" ile kendi workspace'ine klonlayabilir.

### 2.3 — Basemap Seçimi (spec'te vardı, muhtemelen eksik implementasyon)
IT-15'teki 6 basemap seçeneğinin (OpenStreetMap/Uydu/Hibrit/Topografik/Açık
Tema/Koyu Tema) gerçekten hepsi çalışıyor mu — Durum Tespiti'nde kontrol
edilmeli, muhtemelen sadece 1-2'si gerçekten bağlı.

### 2.4 — "Orta Seviye GIS" İçin Somut Ek Yetenekler
"Bildiğin orta seviye bir GIS sistemi" dediğiniz hedefi somutlaştırıyorum,
aşağıdakiler olmadan bir GIS "orta seviye" sayılmaz:
- **Ölçüm araçları:** alan (m²/dönüm) ve mesafe ölçümü, harita üzerinde
  canlı gösterim.
- **Koordinat gösterimi:** imleç konumunun koordinatını (WGS84) canlı
  gösterme.
- **Dışa aktarma:** seçili parsel(ler)i Shapefile/KML/GeoJSON olarak
  indirme.
- **Katman stilizasyonu:** kullanıcı bir katmanın rengini/opaklığını/
  sınır kalınlığını değiştirebilmeli (özellikle Tematik Harita/renklendirme
  ile örtüşüyor, IT-15'te vardı ama kullanıcı kontrolü net değildi).
- **Topoloji/geçerlilik kontrolü:** parsel bölme/çizim sırasında
  kendi kendini kesen (self-intersecting) geçersiz geometri oluşmasını
  engelleme.

**Durum Tespiti İstenen Sorular:**
- Mevcut projede harita hangi kütüphaneyle yapılmış (Leaflet/Mapbox/
  OpenLayers)? Bu, parsel bölme ve ölçüm araçlarının nasıl ekleneceğini
  belirler.
- Çizim aracıyla seçilen alanın gerçekten geometrik kesişimle mi (yoksa
  bounding-box ile mi) parsel seçtiği — önceki test planında (TEST-PLANI.md
  T-14/15/16/17) zaten bunu özellikle sorgulamıştık, hâlâ doğrulanmadıysa
  şimdi doğrulanmalı.
- Kaç basemap gerçekten çalışıyor, kaçı sadece listede duruyor.

---

## KONU 3 — Dashboard Kartları Tıklanabilir/Drill-down Olmalı

**Kapsam (belirttiğiniz ekranların hepsi):** Ana Dashboard, Harita Paneli,
Sulama Kaynak, Operasyon, Toprak Analizi, UFYD Dashboard.

**Kural:** Her widget/kart sadece bir sayı/özet göstermez — **tıklandığında
ilgili detay ekranına veya o widget'ın temsil ettiği veriyle önceden
filtrelenmiş listeye götürür.** Örnekler:
- Ana Dashboard'daki "Riskli Parseller: 12" kartı → tıklanınca Parsel
  listesi, "Risk: Yüksek" filtresi otomatik uygulanmış halde açılır.
- UFYD Dashboard'daki "Bekleyen Ödemeler: 8" kartı → Cari Hesap/Ledger
  listesi, "Durum: Bekliyor" filtreli açılır.
- Toprak Analizi dashboard'ındaki "Analizi Eksik: 5" kartı → ilgili parsel
  listesi filtreli açılır.
- Sulama/Operasyon kartlarında da aynı desen.

**Bu genel bir UX kuralı olarak `CLAUDE.md`'ye de eklenmeli** (aşağıdaki
"Cowork'ün Ek Görevi" bölümünde bu talimat var) — çünkü bu sadece bugünkü
6 ekranla sınırlı kalmamalı, gelecekte eklenecek her dashboard/widget için
varsayılan davranış olmalı.

**Teknik not:** Bu, Query Engine'in (IT-08) filtre DSL'ini URL query
parametresi olarak taşıyabilme yeteneğine dayanır — widget'ın "arkasındaki
sorgu" zaten biliniyorsa (widget'lar zaten Query Engine'den besleniyordu,
IT-14 kuralı), tıklamada aynı sorguyu ilgili liste ekranına parametre
olarak geçirmek yeterli, yeni bir sorgu yazmaya gerek yok.

**Durum Tespiti İstenen Sorular:**
- Hangi ekranlarda kartlar tamamen statik (hiç tıklanamıyor), hangilerinde
  kısmen çalışıyor (bazı kartlar tıklanabilir, bazıları değil)?
- Widget'lar gerçekten Query Engine'den mi besleniyor, yoksa her dashboard
  kendi ayrı sorgusunu mu yazmış (öyleyse bu ayrıca bir standart ihlali,
  `ROADMAP-DETAY-TAM.md` IT-14 kuralına aykırı, o da not edilmeli).

---

## Cowork'ün Ek Görevi — CLAUDE.md Güncellemesi

Konu 3'ü kalıcı kural haline getirmek için, düzeltme tamamlandıktan sonra
`CLAUDE.md`'nin Bölüm 4'üne (Genel Tasarım Kuralları) şu kısa madde
eklenmeli:

> **Kural 5 — Dashboard widget'ları drill-down olmalı:** Hiçbir widget/kart
> sadece statik sayı göstermez; tıklandığında widget'ın temsil ettiği
> veriyle önceden filtrelenmiş ilgili liste/detay ekranına götürür. Yeni
> eklenen her dashboard için bu varsayılan davranıştır.

---

## Cowork'e Verilecek Prompt (kopyala-yapıştır)

```
Bu projede, farklı fazlar önceden ayrı projelerde geliştirildiği için
tutarsızlık/eksiklik olabilir. Önce CLAUDE.md ve ROADMAP-DETAY-TAM.md'yi oku
(genel kurallar ve IT-13/14/15/16/17 için temel spesifikasyon burada).
Sonra DEMO-ÖNCESİ-3-ÖNCELİK.md'yi oku — bu, üç öncelikli konunun (Uydu
Görüntü Sistemi, Harita/GIS Modülü, Dashboard Drill-down) genişletilmiş
spesifikasyonu.

Görev sırası:
1. Her üç konu için önce "Durum Tespiti" yap: mevcut kod tabanında bu
   konuyla ilgili ne var, ne eksik, ne yarım kalmış — kısa bir rapor olarak
   yaz (kod değiştirmeden önce).
2. Rapor bittikten sonra, spesifikasyona göre eksik/hatalı olan kısımları
   tamamla/düzelt. Var olan çalışan kodu gereksiz yere yeniden yazma, sadece
   eksik/bozuk olanı tamamla.
3. Konu 3 tamamlandıktan sonra CLAUDE.md'ye Kural 5'i ekle (dosyada tam metni
   var).
4. Bitirdiğinde değişen dosyaların listesini ve üç konu için de "önce neydi
   / şimdi ne oldu" özetini raporla.

Öncelik sırası: önce Konu 3 (en hızlı, en az riskli — demo için hızlı
kazanım), sonra Konu 2, sonra Konu 1 (en karmaşık, tasking mekanizması
sıfırdan yazılacak).
```

---

## Not — Zaman/Bütçe Kısıtı İçin Öneri

Pazartesiye kadar üçünü de eksiksiz bitirmek riskli olabilir. Önerim: Cowork'e
yukarıdaki sırayla (Konu 3 → Konu 2 → Konu 1) çalıştırın; Konu 1'deki **1.3
Akıllı Tasking** en karmaşık ve en çok token yiyecek parça — demo için
zorunlu değilse (görüntü künyesi + kademeli kalite gösterimi demo'da
yeterli olabilir), tasking'i demo sonrasına bırakıp Konu 1'i "1.1 + 1.2 + 1.4"
ile sınırlı tutmayı düşünebilirsiniz. Bu kararı siz verin, Cowork'e görev
verirken buna göre kapsamı daraltabilirsiniz.
